"""Phase 0 — Cross-project session correctness (ADR-007 collision fixture).

Permanent regression guard for the program's hard prerequisite: ID-based session
reads must enforce ``project_id`` so a cross-project read never returns another
project's row.

Covers:
  * T0-005 — SQLite collision/leak + NULL/'' tolerance (direct-count DB assertions).
  * T0-006 — Postgres parity (skips with an explicit reason when unreachable).
  * T0-007 — ``get_session_family_v1`` is anchor-derived/project-scoped end-to-end.

Run as a NAMED file (this repo's unscoped pytest collection hangs):

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_repository_project_scope.py -v
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

import aiosqlite
import pytest

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

# Two projects, one SHARED session id — the canonical collision scenario.
PROJ_A = "proj-alpha"
PROJ_B = "proj-beta"
SHARED_ID = "shared-session-id"
A_ONLY_ID = "alpha-only-id"
ABSENT_ID = "does-not-exist"

_BASE = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "platformVersion": "2.1.52",
    "platformVersions": ["2.1.52"],
    "platformVersionTransitions": [],
    "durationSeconds": 1,
    "tokensIn": 10,
    "tokensOut": 20,
    "modelIOTokens": 30,
    "cacheCreationInputTokens": 0,
    "cacheReadInputTokens": 0,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.0,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": None,
    "startedAt": "2026-06-01T00:00:00Z",
    "endedAt": "2026-06-01T00:01:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": "shared-root",
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": "shared-root",
    "contextInheritance": "fresh",
}


def _session(session_id: str, **overrides) -> dict:
    return {**_BASE, "id": session_id, **overrides}


# ---------------------------------------------------------------------------
# T0-005 — SQLite collision / leak / NULL-tolerance
# ---------------------------------------------------------------------------


class SqliteSessionProjectScopeTests(unittest.IsolatedAsyncioTestCase):
    """get_by_id / get_many_by_ids enforce project_id with zero cross-project leak."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

        # Seed two projects sharing SHARED_ID; A also owns A_ONLY_ID. Distinct
        # tokensIn values let us assert *which* project's row came back.
        await self.repo.upsert(_session(SHARED_ID, tokensIn=111), PROJ_A)
        await self.repo.upsert(_session(SHARED_ID, tokensIn=222), PROJ_B)
        await self.repo.upsert(_session(A_ONLY_ID, tokensIn=333), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _direct_count(self, project_id: str, session_id: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ? AND id = ?",
            (project_id, session_id),
        ) as cur:
            row = await cur.fetchone()
            return row[0]

    async def test_fixture_seeded_two_colliding_rows(self) -> None:
        """Direct-count baseline (ADR-007): the collision actually exists in the DB."""
        self.assertEqual(await self._direct_count(PROJ_A, SHARED_ID), 1)
        self.assertEqual(await self._direct_count(PROJ_B, SHARED_ID), 1)
        async with self.db.execute("SELECT COUNT(*) FROM sessions") as cur:
            total = (await cur.fetchone())[0]
        self.assertEqual(total, 3)

    async def test_get_by_id_returns_only_project_a_row(self) -> None:
        row = await self.repo.get_by_id(SHARED_ID, project_id=PROJ_A)
        self.assertIsNotNone(row)
        self.assertEqual(row["project_id"], PROJ_A)
        self.assertEqual(row["tokens_in"], 111)

    async def test_get_by_id_returns_only_project_b_row(self) -> None:
        row = await self.repo.get_by_id(SHARED_ID, project_id=PROJ_B)
        self.assertIsNotNone(row)
        self.assertEqual(row["project_id"], PROJ_B)
        self.assertEqual(row["tokens_in"], 222)

    async def test_get_by_id_present_but_wrong_project_returns_none(self) -> None:
        """Session exists only in A; querying B must return None — never A's row."""
        row = await self.repo.get_by_id(A_ONLY_ID, project_id=PROJ_B)
        self.assertIsNone(row)

    async def test_get_by_id_absent_id_returns_none(self) -> None:
        self.assertIsNone(await self.repo.get_by_id(ABSENT_ID, project_id=PROJ_A))

    async def test_get_by_id_none_project_id_unscoped_no_crash(self) -> None:
        """project_id=None resolves active/unscoped (hot path) without crashing."""
        row = await self.repo.get_by_id(A_ONLY_ID, project_id=None)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], A_ONLY_ID)

    async def test_get_by_id_empty_string_project_id_unscoped(self) -> None:
        """project_id='' is treated identically to None (unscoped active resolution)."""
        row = await self.repo.get_by_id(A_ONLY_ID, project_id="")
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], A_ONLY_ID)

    async def test_get_by_id_default_arg_matches_legacy_behaviour(self) -> None:
        """Omitting project_id (legacy call) is unchanged from pre-Phase-0."""
        row = await self.repo.get_by_id(A_ONLY_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], A_ONLY_ID)

    async def test_get_many_by_ids_scoped_to_project_a(self) -> None:
        result = await self.repo.get_many_by_ids([SHARED_ID, A_ONLY_ID], project_id=PROJ_A)
        self.assertEqual(set(result.keys()), {SHARED_ID, A_ONLY_ID})
        self.assertEqual(result[SHARED_ID]["tokens_in"], 111)
        self.assertEqual(result[SHARED_ID]["project_id"], PROJ_A)
        self.assertEqual(result[A_ONLY_ID]["project_id"], PROJ_A)

    async def test_get_many_by_ids_scoped_to_project_b_drops_a_only(self) -> None:
        """B has SHARED_ID but not A_ONLY_ID: only SHARED_ID (B's row) returns."""
        result = await self.repo.get_many_by_ids([SHARED_ID, A_ONLY_ID], project_id=PROJ_B)
        self.assertEqual(set(result.keys()), {SHARED_ID})
        self.assertEqual(result[SHARED_ID]["tokens_in"], 222)
        self.assertEqual(result[SHARED_ID]["project_id"], PROJ_B)

    async def test_get_many_by_ids_no_match_returns_empty(self) -> None:
        result = await self.repo.get_many_by_ids([ABSENT_ID], project_id=PROJ_A)
        self.assertEqual(result, {})

    async def test_get_many_by_ids_none_project_id_unscoped(self) -> None:
        """Unscoped get_many returns rows for the ids regardless of project (legacy)."""
        result = await self.repo.get_many_by_ids([SHARED_ID, A_ONLY_ID], project_id=None)
        # SHARED_ID exists in two projects; the keyed dict collapses to one entry,
        # but A_ONLY_ID must still be present and the call must not crash/leak shape.
        self.assertIn(SHARED_ID, result)
        self.assertIn(A_ONLY_ID, result)

    async def test_get_many_by_ids_empty_list_returns_empty(self) -> None:
        self.assertEqual(await self.repo.get_many_by_ids([], project_id=PROJ_A), {})


# ---------------------------------------------------------------------------
# T0-007 — get_session_family_v1 anchor-derived project scope
# ---------------------------------------------------------------------------


class _StubProject:
    def __init__(self, project_id: str | None):
        self.project_id = project_id


class _StubAppRequest:
    def __init__(self, project_id: str | None):
        self.context = SimpleNamespace(
            project=_StubProject(project_id) if project_id is not None else None
        )


class SessionFamilyProjectScopeTests(unittest.IsolatedAsyncioTestCase):
    """get_session_family_v1 derives project_id from the anchor, never the active singleton."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

        # Project A family: anchor + one descendant sharing root "root-A".
        await self.repo.upsert(
            _session("anchor-A", rootSessionId="root-A", conversationFamilyId="root-A"),
            PROJ_A,
        )
        await self.repo.upsert(
            _session("child-A", rootSessionId="root-A", conversationFamilyId="root-A"),
            PROJ_A,
        )
        # Project B has a session with the SAME id "anchor-A" but its own root/family.
        await self.repo.upsert(
            _session("anchor-A", rootSessionId="root-B", conversationFamilyId="root-B"),
            PROJ_B,
        )
        await self.repo.upsert(
            _session("child-B", rootSessionId="root-B", conversationFamilyId="root-B"),
            PROJ_B,
        )
        await self.db.commit()

        # Patch the handler's collaborators so we exercise the REAL scoping logic
        # against the real repo/DB without standing up the full DI graph.
        import backend.routers._client_v1_sessions as mod

        self._mod = mod
        self._orig_resolve = mod._resolve_app_request
        self._orig_get_repo = mod.get_session_repository
        self._requested_project: str | None = None

        async def _fake_resolve(request_context, core_ports):  # noqa: ANN001
            return _StubAppRequest(self._requested_project)

        mod._resolve_app_request = _fake_resolve  # type: ignore[assignment]
        mod.get_session_repository = lambda _db: self.repo  # type: ignore[assignment]

    async def asyncTearDown(self) -> None:
        self._mod._resolve_app_request = self._orig_resolve  # type: ignore[assignment]
        self._mod.get_session_repository = self._orig_get_repo  # type: ignore[assignment]
        await self.db.close()

    async def _family(self, session_id: str, requested_project: str | None):
        self._requested_project = requested_project
        core_ports = SimpleNamespace(storage=SimpleNamespace(db=self.db))
        return await self._mod.get_session_family_v1(
            session_id, request_context=object(), core_ports=core_ports
        )

    async def test_family_for_non_active_project_returns_only_that_tree(self) -> None:
        """Requesting project B's family returns B's tree only — never A's collision rows."""
        envelope = await self._family("anchor-A", PROJ_B)
        member_ids = {m.session_id for m in envelope.data.members}
        self.assertEqual(envelope.data.root_session_id, "root-B")
        self.assertEqual(member_ids, {"anchor-A", "child-B"})
        self.assertNotIn("child-A", member_ids)

    async def test_family_for_project_a_returns_project_a_tree(self) -> None:
        envelope = await self._family("anchor-A", PROJ_A)
        member_ids = {m.session_id for m in envelope.data.members}
        self.assertEqual(envelope.data.root_session_id, "root-A")
        self.assertEqual(member_ids, {"anchor-A", "child-A"})
        self.assertNotIn("child-B", member_ids)

    async def test_anchor_not_found_in_requested_project_raises_404_no_fallback(self) -> None:
        """Anchor missing in requested project → 404; NO fallback to the other project."""
        from fastapi import HTTPException

        # "child-A" exists only in project A; request it scoped to project B.
        with self.assertRaises(HTTPException) as ctx:
            await self._family("child-A", PROJ_B)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_unscoped_request_derives_project_from_anchor_row(self) -> None:
        """project_id=None resolves the anchor unscoped, then scopes family to the
        anchor's OWN project (not an active singleton)."""
        envelope = await self._family("child-B", None)
        member_ids = {m.session_id for m in envelope.data.members}
        self.assertEqual(envelope.data.root_session_id, "root-B")
        self.assertEqual(member_ids, {"anchor-A", "child-B"})
        self.assertNotIn("child-A", member_ids)


# ---------------------------------------------------------------------------
# T0-006 — Postgres parity (skip-with-reason when unreachable)
# ---------------------------------------------------------------------------


def _postgres_dsn() -> str | None:
    if os.environ.get("CCDASH_DB_BACKEND") != "postgres":
        return None
    return os.environ.get("CCDASH_DATABASE_URL")


class PostgresSessionProjectScopeTests(unittest.IsolatedAsyncioTestCase):
    """Mirror of the SQLite collision suite against a real Postgres backend.

    Skips (never silently passes) when Postgres is not configured/reachable.
    """

    async def asyncSetUp(self) -> None:
        dsn = _postgres_dsn()
        if not dsn:
            self.skipTest(
                "postgres unreachable: set CCDASH_DB_BACKEND=postgres and "
                "CCDASH_DATABASE_URL to a reachable server to run parity tests"
            )
        try:
            import asyncpg
        except ImportError:  # pragma: no cover - env-dependent
            self.skipTest("postgres unreachable: asyncpg not installed")

        try:
            self.conn = await asyncpg.connect(dsn, timeout=5)
        except Exception as exc:  # pragma: no cover - env-dependent
            self.skipTest(f"postgres unreachable: {exc!r}")

        from backend.db import postgres_migrations
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository

        await postgres_migrations.run_migrations(self.conn)
        self.repo = PostgresSessionRepository(self.conn)

        # Namespaced ids so we never clobber real data; cleaned up in teardown.
        self.pa = "pgscope-proj-alpha"
        self.pb = "pgscope-proj-beta"
        self.shared = "pgscope-shared-id"
        self.a_only = "pgscope-alpha-only"
        await self._cleanup()
        await self.repo.upsert(_session(self.shared, tokensIn=111), self.pa)
        await self.repo.upsert(_session(self.shared, tokensIn=222), self.pb)
        await self.repo.upsert(_session(self.a_only, tokensIn=333), self.pa)

    async def _cleanup(self) -> None:
        await self.conn.execute(
            "DELETE FROM sessions WHERE project_id = ANY($1::text[])",
            [self.pa, self.pb],
        )

    async def asyncTearDown(self) -> None:
        if getattr(self, "conn", None) is not None:
            try:
                await self._cleanup()
            finally:
                await self.conn.close()

    async def _direct_count(self, project_id: str, session_id: str) -> int:
        return await self.conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE project_id = $1 AND id = $2",
            project_id,
            session_id,
        )

    async def test_fixture_seeded_two_colliding_rows(self) -> None:
        self.assertEqual(await self._direct_count(self.pa, self.shared), 1)
        self.assertEqual(await self._direct_count(self.pb, self.shared), 1)

    async def test_get_by_id_no_cross_project_leak(self) -> None:
        row_a = await self.repo.get_by_id(self.shared, project_id=self.pa)
        row_b = await self.repo.get_by_id(self.shared, project_id=self.pb)
        self.assertEqual(row_a["tokens_in"], 111)
        self.assertEqual(row_a["project_id"], self.pa)
        self.assertEqual(row_b["tokens_in"], 222)
        self.assertEqual(row_b["project_id"], self.pb)

    async def test_get_by_id_wrong_project_returns_none(self) -> None:
        self.assertIsNone(await self.repo.get_by_id(self.a_only, project_id=self.pb))

    async def test_get_by_id_none_project_id_unscoped(self) -> None:
        row = await self.repo.get_by_id(self.a_only, project_id=None)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], self.a_only)

    async def test_get_many_by_ids_scoped_to_project_b_drops_a_only(self) -> None:
        result = await self.repo.get_many_by_ids([self.shared, self.a_only], project_id=self.pb)
        self.assertEqual(set(result.keys()), {self.shared})
        self.assertEqual(result[self.shared]["tokens_in"], 222)

    async def test_get_many_by_ids_empty_list_returns_empty(self) -> None:
        self.assertEqual(await self.repo.get_many_by_ids([], project_id=self.pa), {})


if __name__ == "__main__":
    unittest.main()
