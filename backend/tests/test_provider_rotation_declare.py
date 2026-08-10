"""Tests for the rotation DECLARE path (M2, provider-channel-credential-entities-v1).

``provider_credentials.rotated_from_id`` exists and the READ side
(``backend/application/services/agent_queries/provider_credential_rollup.py``'s
union-find) is complete and cycle-safe, but until this change nothing ever
WROTE that column. ``SqliteProviderDimensionsRepository.declare_rotation`` /
``PostgresProviderDimensionsRepository.declare_rotation`` (shared validation
via ``_validate_declare_rotation``) are that write path.

Covers:
1. Direct-count/direct-read assertion (ADR-007 style — never trust the
   method's own return value) that ``declare_rotation`` actually flips
   ``rotated_from_id`` / ``rotation_declared_at`` / ``rotation_declared_by``
   on the successor row.
2. A declared A -> B pair reads back as ONE series through the REAL rollup
   service (``ProviderCredentialRollupService`` / ``_group_credentials_by_series``,
   imported unmodified from the M3 module).
3. Two UNDECLARED credentials stay TWO series — the correct answer, not a
   gap.
4. Cycle rejected (A -> B -> C -> A).
5. Self-reference rejected.
6. Missing predecessor / missing successor rejected.
7. Idempotent re-declare of the same pointer is a no-op success.
8. Conflicting re-declare (different predecessor) is rejected, and does not
   overwrite the existing pointer.
9. The secret-shaped-value guard fires on every guarded field before any
   write.

Run as a named module (unscoped collection can hang this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_provider_rotation_declare.py -q -p no:cacheprovider
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.provider_credential_rollup import (
    ProviderCredentialRollupService,
)
from backend.db.repositories.provider_dimensions import (
    RotationConflictError,
    RotationCredentialNotFoundError,
    RotationCycleError,
    RotationSelfReferenceError,
    SqliteProviderDimensionsRepository,
)
from backend.db.sqlite_migrations import run_migrations


class _RotationTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteProviderDimensionsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed_credential(self, channel: str, name: str) -> None:
        await self.repo.upsert_provider_credential(channel=channel, credential_name=name)


# ── direct-count / direct-read assertion ─────────────────────────────────


class DeclareRotationDirectReadTests(_RotationTestBase):
    async def test_declare_sets_rotated_from_id_and_metadata(self) -> None:
        await self._seed_credential("ica", "CC1")
        await self._seed_credential("ica", "CC2")

        predecessor = await self.repo.get_provider_credential("ica", "CC1")
        self.assertIsNone(predecessor["rotated_from_id"])
        successor_before = await self.repo.get_provider_credential("ica", "CC2")
        self.assertIsNone(successor_before["rotated_from_id"])
        self.assertIsNone(successor_before["rotation_declared_at"])
        self.assertIsNone(successor_before["rotation_declared_by"])

        await self.repo.declare_rotation(
            channel="ica",
            predecessor_credential_name="CC1",
            successor_credential_name="CC2",
            declared_by="operator-nick",
        )

        # Direct read from a fresh query — never trust the method's own
        # (None) return value.
        successor_after = await self.repo.get_provider_credential("ica", "CC2")
        self.assertEqual(successor_after["rotated_from_id"], predecessor["id"])
        self.assertIsNotNone(successor_after["rotation_declared_at"])
        self.assertEqual(successor_after["rotation_declared_by"], "operator-nick")

        # Predecessor row itself is untouched.
        predecessor_after = await self.repo.get_provider_credential("ica", "CC1")
        self.assertIsNone(predecessor_after["rotated_from_id"])


# ── validation rejections ────────────────────────────────────────────────


class DeclareRotationValidationTests(_RotationTestBase):
    async def test_missing_predecessor_rejected(self) -> None:
        await self._seed_credential("ica", "CC2")
        with self.assertRaises(RotationCredentialNotFoundError):
            await self.repo.declare_rotation(
                channel="ica",
                predecessor_credential_name="does-not-exist",
                successor_credential_name="CC2",
            )
        row = await self.repo.get_provider_credential("ica", "CC2")
        self.assertIsNone(row["rotated_from_id"])

    async def test_missing_successor_rejected(self) -> None:
        await self._seed_credential("ica", "CC1")
        with self.assertRaises(RotationCredentialNotFoundError):
            await self.repo.declare_rotation(
                channel="ica",
                predecessor_credential_name="CC1",
                successor_credential_name="does-not-exist",
            )

    async def test_self_reference_rejected(self) -> None:
        await self._seed_credential("ica", "CC1")
        with self.assertRaises(RotationSelfReferenceError):
            await self.repo.declare_rotation(
                channel="ica",
                predecessor_credential_name="CC1",
                successor_credential_name="CC1",
            )
        row = await self.repo.get_provider_credential("ica", "CC1")
        self.assertIsNone(row["rotated_from_id"])

    async def test_cycle_rejected(self) -> None:
        # A -> B -> C declared; C -> A would close the loop.
        await self._seed_credential("ica", "A")
        await self._seed_credential("ica", "B")
        await self._seed_credential("ica", "C")
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="A", successor_credential_name="B"
        )
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="B", successor_credential_name="C"
        )
        with self.assertRaises(RotationCycleError):
            await self.repo.declare_rotation(
                channel="ica", predecessor_credential_name="C", successor_credential_name="A"
            )
        # Nothing written by the rejected call.
        row_a = await self.repo.get_provider_credential("ica", "A")
        self.assertIsNone(row_a["rotated_from_id"])

    async def test_idempotent_redeclare_same_pointer_is_noop(self) -> None:
        await self._seed_credential("ica", "CC1")
        await self._seed_credential("ica", "CC2")
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="CC1", successor_credential_name="CC2"
        )
        first = await self.repo.get_provider_credential("ica", "CC2")
        # Re-declaring the exact same pointer must not raise.
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="CC1", successor_credential_name="CC2"
        )
        second = await self.repo.get_provider_credential("ica", "CC2")
        self.assertEqual(first["rotated_from_id"], second["rotated_from_id"])

    async def test_conflicting_redeclare_rejected_and_does_not_overwrite(self) -> None:
        await self._seed_credential("ica", "CC1")
        await self._seed_credential("ica", "CC2")
        await self._seed_credential("ica", "CC3")
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="CC1", successor_credential_name="CC3"
        )
        before = await self.repo.get_provider_credential("ica", "CC3")
        with self.assertRaises(RotationConflictError):
            await self.repo.declare_rotation(
                channel="ica",
                predecessor_credential_name="CC2",
                successor_credential_name="CC3",
            )
        after = await self.repo.get_provider_credential("ica", "CC3")
        self.assertEqual(before["rotated_from_id"], after["rotated_from_id"])

    async def test_secret_shaped_declared_by_rejected_and_writes_nothing(self) -> None:
        await self._seed_credential("ica", "CC1")
        await self._seed_credential("ica", "CC2")
        with self.assertRaises(ValueError):
            await self.repo.declare_rotation(
                channel="ica",
                predecessor_credential_name="CC1",
                successor_credential_name="CC2",
                declared_by="sk-ant-totally-a-real-anthropic-key-shape-value",
            )
        row = await self.repo.get_provider_credential("ica", "CC2")
        self.assertIsNone(row["rotated_from_id"])


# ── rollup integration: declared vs undeclared pairs ─────────────────────


def _context(project_id: str = "proj-a") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name=project_id,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, projects: list[Any]) -> None:
        self._projects = projects

    def list_projects(self) -> list[Any]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Any | None:
        return next((p for p in self._projects if p.id == project_id), None)


class _Storage:
    def __init__(self, *, db: Any) -> None:
        self.db = db


def _make_project(project_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=project_id)


def _make_ports(*, projects: list[Any], db: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(projects),
        storage=_Storage(db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    ica_key: str,
    tokens_in: int,
    tokens_out: int,
    attribution: str | None,
    spend_delta: str | None,
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions (
            id, project_id, status, model, platform_type, launcher,
            tokens_in, tokens_out, ica_key, ica_spend_delta, ica_spend_attribution,
            started_at, updated_at, created_at, source_file
        ) VALUES (?, ?, 'completed', 'claude-sonnet-5', 'Claude Code', 'ica-claude.sh',
                  ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            project_id,
            tokens_in,
            tokens_out,
            ica_key,
            spend_delta,
            attribution,
            now,
            now,
            now,
            f"{session_id}.jsonl",
        ),
    )
    await db.commit()


class DeclareRotationRollupIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Proves declare_rotation's write is actually consumed by the real,
    unmodified M3 rollup service -- not just readable back off the repo."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteProviderDimensionsRepository(self.db)

        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC1")
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC2")
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC3")
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC4")

        # Declare CC1 -> CC2 as one series. CC3/CC4 left undeclared.
        await self.repo.declare_rotation(
            channel="ica", predecessor_credential_name="CC1", successor_credential_name="CC2"
        )

        project = _make_project("proj-a")
        await _insert_session(
            self.db, session_id="s-cc1", project_id="proj-a", ica_key="CC1",
            tokens_in=10, tokens_out=5, attribution="attributed", spend_delta="1.0",
        )
        await _insert_session(
            self.db, session_id="s-cc2", project_id="proj-a", ica_key="CC2",
            tokens_in=20, tokens_out=10, attribution="attributed", spend_delta="2.0",
        )
        await _insert_session(
            self.db, session_id="s-cc3", project_id="proj-a", ica_key="CC3",
            tokens_in=1, tokens_out=1, attribution="attributed", spend_delta="0.5",
        )
        await _insert_session(
            self.db, session_id="s-cc4", project_id="proj-a", ica_key="CC4",
            tokens_in=1, tokens_out=1, attribution="attributed", spend_delta="0.5",
        )

        self.ports = _make_ports(projects=[project], db=self.db)
        self.svc = ProviderCredentialRollupService()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    def _series_by_credential_name(self, response, name: str):
        for series in response.series:
            if name in series.credential_names:
                return series
        raise AssertionError(f"no series found containing credential {name!r}")

    async def test_declared_pair_reads_as_one_series_through_rollup(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc1_series = self._series_by_credential_name(response, "CC1")
        cc2_series = self._series_by_credential_name(response, "CC2")
        self.assertEqual(cc1_series.series_id, cc2_series.series_id)
        self.assertEqual(set(cc1_series.credential_names), {"CC1", "CC2"})
        self.assertAlmostEqual(cc1_series.spend_usd, 3.0, places=6)

    async def test_undeclared_pair_stays_two_series_through_rollup(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc3_series = self._series_by_credential_name(response, "CC3")
        cc4_series = self._series_by_credential_name(response, "CC4")
        self.assertNotEqual(cc3_series.series_id, cc4_series.series_id)


if __name__ == "__main__":
    unittest.main()
