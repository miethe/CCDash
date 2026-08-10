"""Tests for ProviderCredentialRollupService (M3, provider-channel-credential-entities-v1).

Covers the AC evidence enumerated in the M3 milestone plan:

* spend total covers only ``attributed`` rows, exact value;
* excluded count is exactly right;
* token and session counts include the excluded sessions;
* ``include_unattributed=True`` returns the excluded rows;
* an unrecognised attribution token does not raise and is excluded from spend;
* a declared rotation pair reads as ONE series; an undeclared pair stays TWO;
* a rotation cycle terminates instead of hanging;
* totals span multiple projects.

Follows the IsolatedAsyncioTestCase + aiosqlite in-memory DB pattern
established in ``test_system_metrics.py``.
"""
from __future__ import annotations

import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.provider_credential_rollup import (
    ProviderCredentialRollupService,
    _CredentialRow,
    _group_credentials_by_series,
)
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Shared test fixtures (mirrors test_system_metrics.py's fake ports)
# ---------------------------------------------------------------------------

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
    started_at: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    started_at = started_at if started_at is not None else now
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
            started_at,
            now,
            now,
            f"{session_id}.jsonl",
        ),
    )
    await db.commit()


async def _insert_credential(
    db: aiosqlite.Connection,
    *,
    cred_id: int,
    channel: str,
    credential_name: str,
    rotated_from_id: int | None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        """
        INSERT INTO provider_credentials (
            id, channel, credential_name, provider_id, rotated_from_id,
            first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, '', ?, ?, ?, ?, ?)
        """,
        (cred_id, channel, credential_name, rotated_from_id, now, now, now, now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Union-find rotation-lineage grouping — pure unit tests, no DB
# ---------------------------------------------------------------------------

class TestGroupCredentialsBySeries(unittest.TestCase):
    def test_declared_chain_is_one_series(self) -> None:
        creds = [
            _CredentialRow(id=1, channel="ica", credential_name="CC1", rotated_from_id=None),
            _CredentialRow(id=2, channel="ica", credential_name="CC2", rotated_from_id=1),
        ]
        series = _group_credentials_by_series(creds)
        self.assertEqual(series[1], series[2])

    def test_undeclared_pair_is_two_series(self) -> None:
        creds = [
            _CredentialRow(id=3, channel="ica", credential_name="CC3", rotated_from_id=None),
            _CredentialRow(id=4, channel="ica", credential_name="CC4", rotated_from_id=None),
        ]
        series = _group_credentials_by_series(creds)
        self.assertNotEqual(series[3], series[4])

    def test_transitive_chain_a_b_c_is_one_series(self) -> None:
        creds = [
            _CredentialRow(id=1, channel="ica", credential_name="A", rotated_from_id=None),
            _CredentialRow(id=2, channel="ica", credential_name="B", rotated_from_id=1),
            _CredentialRow(id=3, channel="ica", credential_name="C", rotated_from_id=2),
        ]
        series = _group_credentials_by_series(creds)
        self.assertEqual(series[1], series[2])
        self.assertEqual(series[2], series[3])

    def test_cycle_terminates_and_yields_one_series(self) -> None:
        """A malformed declared cycle (A -> B -> A) must not hang or recurse."""
        creds = [
            _CredentialRow(id=1, channel="ica", credential_name="A", rotated_from_id=2),
            _CredentialRow(id=2, channel="ica", credential_name="B", rotated_from_id=1),
        ]
        series = _group_credentials_by_series(creds)
        self.assertEqual(series[1], series[2])

    def test_self_referential_cycle_terminates(self) -> None:
        creds = [
            _CredentialRow(id=1, channel="ica", credential_name="A", rotated_from_id=1),
        ]
        series = _group_credentials_by_series(creds)
        self.assertEqual(series[1], 1)


# ---------------------------------------------------------------------------
# Full-service integration test against a seeded multi-verdict fixture
# ---------------------------------------------------------------------------

class TestProviderCredentialRollupService(unittest.IsolatedAsyncioTestCase):
    """Seeds all four attribution verdicts + one unknown token, across two
    projects, with a declared rotation pair (CC1 -> CC2) and an undeclared
    pair (CC3, CC4).
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        # Credentials: CC2 declares rotation from CC1 (one series). CC3/CC4
        # declare no rotation between them (two series).
        await _insert_credential(self.db, cred_id=1, channel="ica", credential_name="CC1", rotated_from_id=None)
        await _insert_credential(self.db, cred_id=2, channel="ica", credential_name="CC2", rotated_from_id=1)
        await _insert_credential(self.db, cred_id=3, channel="ica", credential_name="CC3", rotated_from_id=None)
        await _insert_credential(self.db, cred_id=4, channel="ica", credential_name="CC4", rotated_from_id=None)

        self.proj_a = _make_project("proj-a")
        self.proj_b = _make_project("proj-b")

        # CC1/CC2 series (declared rotation) — spans both projects.
        await _insert_session(
            self.db, session_id="s-cc1-attributed", project_id="proj-a", ica_key="CC1",
            tokens_in=100, tokens_out=50, attribution="attributed", spend_delta="10.0",
        )
        await _insert_session(
            self.db, session_id="s-cc2-attributed", project_id="proj-b", ica_key="CC2",
            tokens_in=20, tokens_out=10, attribution="attributed", spend_delta="5.0",
        )
        await _insert_session(
            self.db, session_id="s-cc1-concurrent", project_id="proj-a", ica_key="CC1",
            tokens_in=7, tokens_out=3, attribution="concurrent_shared_key", spend_delta=None,
        )

        # CC3 (own series) — key_changed + incomplete_readings verdicts.
        await _insert_session(
            self.db, session_id="s-cc3-key-changed", project_id="proj-a", ica_key="CC3",
            tokens_in=11, tokens_out=4, attribution="key_changed", spend_delta=None,
        )
        await _insert_session(
            self.db, session_id="s-cc3-incomplete", project_id="proj-b", ica_key="CC3",
            tokens_in=2, tokens_out=1, attribution="incomplete_readings", spend_delta=None,
        )

        # CC4 (separate series from CC3 — no declared rotation) — one
        # attributed session plus one session carrying an attribution token
        # OUTSIDE the closed vocabulary (must not raise, must be excluded).
        await _insert_session(
            self.db, session_id="s-cc4-attributed", project_id="proj-a", ica_key="CC4",
            tokens_in=9, tokens_out=6, attribution="attributed", spend_delta="3.5",
        )
        await _insert_session(
            self.db, session_id="s-cc4-unknown-token", project_id="proj-b", ica_key="CC4",
            tokens_in=1, tokens_out=1, attribution="some_future_verdict", spend_delta=None,
        )

        self.ports = _make_ports(projects=[self.proj_a, self.proj_b], db=self.db)
        self.svc = ProviderCredentialRollupService()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    def _series_by_credential_name(
        self, response, name: str
    ):
        for series in response.series:
            if name in series.credential_names:
                return series
        raise AssertionError(f"no series found containing credential {name!r}")

    async def test_declared_rotation_reads_as_one_series(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc1_series = self._series_by_credential_name(response, "CC1")
        cc2_series = self._series_by_credential_name(response, "CC2")
        self.assertEqual(cc1_series.series_id, cc2_series.series_id)
        self.assertEqual(set(cc1_series.credential_names), {"CC1", "CC2"})

    async def test_undeclared_pair_stays_two_series(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc3_series = self._series_by_credential_name(response, "CC3")
        cc4_series = self._series_by_credential_name(response, "CC4")
        self.assertNotEqual(cc3_series.series_id, cc4_series.series_id)

    async def test_spend_covers_only_attributed_rows(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc1_series = self._series_by_credential_name(response, "CC1")
        # 10.0 (s-cc1-attributed) + 5.0 (s-cc2-attributed); concurrent_shared_key
        # session contributes nothing.
        self.assertAlmostEqual(cc1_series.spend_usd, 15.0, places=6)

        cc4_series = self._series_by_credential_name(response, "CC4")
        # Only s-cc4-attributed (3.5); unknown-token session excluded.
        self.assertAlmostEqual(cc4_series.spend_usd, 3.5, places=6)

        cc3_series = self._series_by_credential_name(response, "CC3")
        # Neither CC3 session is attributed.
        self.assertAlmostEqual(cc3_series.spend_usd, 0.0, places=6)

    async def test_excluded_count_is_exact(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc1_series = self._series_by_credential_name(response, "CC1")
        self.assertEqual(cc1_series.spend_excluded_count, 1)  # concurrent_shared_key

        cc3_series = self._series_by_credential_name(response, "CC3")
        self.assertEqual(cc3_series.spend_excluded_count, 2)  # key_changed + incomplete_readings

        cc4_series = self._series_by_credential_name(response, "CC4")
        self.assertEqual(cc4_series.spend_excluded_count, 1)  # unknown token

    async def test_unknown_attribution_token_does_not_raise_and_is_excluded(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc4_series = self._series_by_credential_name(response, "CC4")
        self.assertIn("some_future_verdict", cc4_series.spend_excluded_by_attribution)
        self.assertEqual(cc4_series.spend_excluded_by_attribution["some_future_verdict"], 1)

    async def test_token_and_session_counts_include_excluded_sessions(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        cc1_series = self._series_by_credential_name(response, "CC1")
        # Sessions: s-cc1-attributed(100,50) + s-cc2-attributed(20,10) + s-cc1-concurrent(7,3)
        self.assertEqual(cc1_series.session_count, 3)
        self.assertEqual(cc1_series.tokens_in, 127)
        self.assertEqual(cc1_series.tokens_out, 63)

        cc3_series = self._series_by_credential_name(response, "CC3")
        # Both CC3 sessions are excluded from spend but must still count.
        self.assertEqual(cc3_series.session_count, 2)
        self.assertEqual(cc3_series.tokens_in, 13)
        self.assertEqual(cc3_series.tokens_out, 5)

    async def test_default_response_omits_excluded_sessions(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        self.assertFalse(response.include_unattributed)
        cc1_series = self._series_by_credential_name(response, "CC1")
        self.assertIsNone(cc1_series.excluded_sessions)

    async def test_include_unattributed_returns_excluded_rows(self) -> None:
        response = await self.svc.get_rollup(
            _context(), self.ports, include_unattributed=True
        )
        self.assertTrue(response.include_unattributed)
        cc1_series = self._series_by_credential_name(response, "CC1")
        self.assertIsNotNone(cc1_series.excluded_sessions)
        self.assertEqual(len(cc1_series.excluded_sessions), 1)
        excluded = cc1_series.excluded_sessions[0]
        self.assertEqual(excluded.session_id, "s-cc1-concurrent")
        self.assertEqual(excluded.attribution, "concurrent_shared_key")
        # Per the v51 contract, non-attributed deltas are stored NULL.
        self.assertIsNone(excluded.spend_delta_raw)

    async def test_totals_span_multiple_projects(self) -> None:
        response = await self.svc.get_rollup(_context(), self.ports)
        self.assertEqual(set(response.project_ids), {"proj-a", "proj-b"})
        cc1_series = self._series_by_credential_name(response, "CC1")
        self.assertEqual(set(cc1_series.project_ids), {"proj-a", "proj-b"})
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.errors, [])


# ---------------------------------------------------------------------------
# Periodic windowing (since/until) — AC3 "cumulative AND periodic"
# ---------------------------------------------------------------------------

class TestProviderCredentialRollupWindowing(unittest.IsolatedAsyncioTestCase):
    """Dedicated fixture: one credential, four sessions spread across three
    distinct calendar days, so a window can be proven to include/exclude the
    right rows without disturbing the cumulative-behavior fixture above.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        await _insert_credential(self.db, cred_id=10, channel="ica", credential_name="CC-W", rotated_from_id=None)

        # 2026-01-01: one attributed session, outside the test window.
        await _insert_session(
            self.db, session_id="s-early", project_id="proj-a", ica_key="CC-W",
            tokens_in=10, tokens_out=5, attribution="attributed", spend_delta="2.0",
            started_at="2026-01-01T00:00:00",
        )
        # 2026-01-02: the test window — one attributed + one excluded.
        await _insert_session(
            self.db, session_id="s-mid-attributed", project_id="proj-a", ica_key="CC-W",
            tokens_in=20, tokens_out=8, attribution="attributed", spend_delta="3.0",
            started_at="2026-01-02T12:00:00",
        )
        await _insert_session(
            self.db, session_id="s-mid-excluded", project_id="proj-a", ica_key="CC-W",
            tokens_in=4, tokens_out=1, attribution="concurrent_shared_key", spend_delta=None,
            started_at="2026-01-02T13:00:00",
        )
        # 2026-01-03: one large attributed session, outside the test window.
        await _insert_session(
            self.db, session_id="s-late", project_id="proj-a", ica_key="CC-W",
            tokens_in=999, tokens_out=999, attribution="attributed", spend_delta="100.0",
            started_at="2026-01-03T00:00:00",
        )

        self.ports = _make_ports(projects=[_make_project("proj-a")], db=self.db)
        self.svc = ProviderCredentialRollupService()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    def _series(self, response):
        for series in response.series:
            if "CC-W" in series.credential_names:
                return series
        raise AssertionError("no CC-W series found")

    async def test_window_includes_only_matching_sessions(self) -> None:
        response = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-02T00:00:00Z", until="2026-01-02T23:59:59Z",
        )
        series = self._series(response)
        # Only s-mid-attributed's 3.0 — s-early and s-late are outside the
        # window even though both are 'attributed'.
        self.assertAlmostEqual(series.spend_usd, 3.0, places=6)
        self.assertEqual(series.session_count, 2)
        self.assertEqual(series.tokens_in, 24)  # 20 + 4
        self.assertEqual(series.tokens_out, 9)  # 8 + 1

    async def test_window_still_excludes_non_attributed_and_reports_count(self) -> None:
        response = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-02T00:00:00Z", until="2026-01-02T23:59:59Z",
        )
        series = self._series(response)
        self.assertEqual(series.spend_excluded_count, 1)
        self.assertEqual(series.spend_excluded_by_attribution, {"concurrent_shared_key": 1})

    async def test_omitting_both_bounds_reproduces_cumulative_result(self) -> None:
        cumulative = await self.svc.get_rollup(_context(), self.ports)
        series = self._series(cumulative)
        self.assertAlmostEqual(series.spend_usd, 105.0, places=6)  # 2 + 3 + 100
        self.assertEqual(series.session_count, 4)
        self.assertEqual(series.spend_excluded_count, 1)
        self.assertIsNone(cumulative.since)
        self.assertIsNone(cumulative.until)

    async def test_invalid_timestamp_raises_value_error_not_generic_exception(self) -> None:
        with self.assertRaises(ValueError):
            await self.svc.get_rollup(_context(), self.ports, since="not-a-timestamp")

    async def test_response_echoes_effective_window(self) -> None:
        response = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-02T00:00:00Z", until="2026-01-02T23:59:59Z",
        )
        self.assertIsNotNone(response.since)
        self.assertIsNotNone(response.until)
        self.assertEqual(response.since.year, 2026)
        self.assertEqual(response.since.month, 1)
        self.assertEqual(response.since.day, 2)

    async def test_different_windows_do_not_collide_in_cache(self) -> None:
        narrow = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-02T00:00:00Z", until="2026-01-02T23:59:59Z",
        )
        wide = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-01T00:00:00Z", until="2026-01-03T23:59:59Z",
        )
        narrow_series = self._series(narrow)
        wide_series = self._series(wide)
        self.assertEqual(narrow_series.session_count, 2)
        self.assertEqual(wide_series.session_count, 4)
        self.assertNotEqual(narrow_series.session_count, wide_series.session_count)

        # Re-issuing the narrow window again must still return the narrow
        # result -- proving the wide call's cache entry didn't clobber it.
        narrow_again = await self.svc.get_rollup(
            _context(), self.ports,
            since="2026-01-02T00:00:00Z", until="2026-01-02T23:59:59Z",
        )
        self.assertEqual(self._series(narrow_again).session_count, 2)


if __name__ == "__main__":
    unittest.main()
