"""Tests for the live active-count feature (live-agents-count-v1).

Covers:
- SqliteSessionRepository.count_active: freshness window, stale-active defence,
  subagent exclusion, status filter.
- LiveMetricsQueryService: project-resolution, service delegation, error resilience.
- Migration: idx_sessions_project_status_updated exists and is idempotent.
"""
from __future__ import annotations

import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.live_metrics import (
    LiveActiveCountDTO,
    LiveMetricsQueryService,
)


# ── Shared test helpers ──────────────────────────────────────────────────────


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id):
        if self._project and getattr(self._project, "id", "") == project_id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        resolved_id = project_id or self._project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self._project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, sessions_repo):
        self.db = object()
        self._sessions_repo = sessions_repo

    def sessions(self):
        return self._sessions_repo

    def features(self):
        return types.SimpleNamespace(list_all=AsyncMock(return_value=[]))

    def sync_state(self):
        return types.SimpleNamespace(list_all=AsyncMock(return_value=[]))


def _context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _ports(*, project=None, sessions_repo=None) -> CorePorts:
    resolved_project = project if project is not None else types.SimpleNamespace(
        id="project-1", name="Project 1"
    )
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(resolved_project),
        storage=_Storage(sessions_repo=sessions_repo or types.SimpleNamespace(
            count_active=AsyncMock(return_value=0),
        )),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ── SqliteSessionRepository.count_active unit tests ──────────────────────────


class SqliteCountActiveTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the SQLite count_active method using an in-memory DB."""

    async def asyncSetUp(self) -> None:
        from backend.db.repositories.sessions import SqliteSessionRepository

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Create the minimal sessions schema needed for count_active
        await self.db.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                session_type TEXT
            )
        """)
        await self.db.commit()
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    def _now_iso(self, delta_seconds: int = 0) -> str:
        t = datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)
        return t.isoformat()

    async def _insert(
        self,
        session_id: str,
        project_id: str,
        status: str,
        updated_at: str,
        session_type: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO sessions (id, project_id, status, updated_at, session_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, project_id, status, updated_at, session_type),
        )
        await self.db.commit()

    async def test_counts_active_within_window(self) -> None:
        """AC-3: session with status='active' within window IS counted."""
        await self._insert("s1", "proj-1", "active", self._now_iso(-60))  # 1 min ago
        result = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result, 1)

    async def test_excludes_stale_active(self) -> None:
        """AC-3: session with status='active' but updated_at older than window is NOT counted."""
        await self._insert("s1", "proj-1", "active", self._now_iso(-700))  # 11+ min ago
        result = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result, 0)

    async def test_excludes_completed_within_window(self) -> None:
        """AC-3: session with status='completed' within window is NOT counted."""
        await self._insert("s1", "proj-1", "completed", self._now_iso(-60))
        result = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result, 0)

    async def test_empty_project_returns_zero(self) -> None:
        """AC-1 resilience: project with no sessions returns 0."""
        result = await self.repo.count_active("nonexistent-project", window_seconds=600)
        self.assertEqual(result, 0)

    async def test_excludes_subagents_by_default(self) -> None:
        """AC-3: subagent rows are excluded when include_subagents=False (default)."""
        await self._insert("s-parent", "proj-1", "active", self._now_iso(-60), session_type=None)
        await self._insert("s-sub", "proj-1", "active", self._now_iso(-60), session_type="subagent")
        result_default = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result_default, 1, "Default should exclude subagents")

    async def test_includes_subagents_when_requested(self) -> None:
        """AC-3: subagent rows are included when include_subagents=True."""
        await self._insert("s-parent", "proj-1", "active", self._now_iso(-60), session_type=None)
        await self._insert("s-sub", "proj-1", "active", self._now_iso(-60), session_type="subagent")
        result_with_subagents = await self.repo.count_active(
            "proj-1", window_seconds=600, include_subagents=True
        )
        self.assertEqual(result_with_subagents, 2, "With include_subagents=True should count both")

    async def test_project_scoping(self) -> None:
        """count_active only counts sessions in the specified project."""
        await self._insert("s1", "proj-1", "active", self._now_iso(-60))
        await self._insert("s2", "proj-2", "active", self._now_iso(-60))
        self.assertEqual(await self.repo.count_active("proj-1", window_seconds=600), 1)
        self.assertEqual(await self.repo.count_active("proj-2", window_seconds=600), 1)

    async def test_window_boundary_exact_threshold(self) -> None:
        """Sessions just inside the window boundary are counted."""
        # 599 seconds ago — just inside a 600-second window
        await self._insert("s-inside", "proj-1", "active", self._now_iso(-599))
        # 601 seconds ago — just outside
        await self._insert("s-outside", "proj-1", "active", self._now_iso(-601))
        result = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result, 1, "Only the session inside the window should be counted")

    async def test_stale_active_defence_documented_case(self) -> None:
        """OQ-3 spike defence: 57-day-old active row should NOT be counted."""
        fifty_seven_days_ago = self._now_iso(-57 * 24 * 60 * 60)
        await self._insert("s-stale", "proj-1", "active", fifty_seven_days_ago)
        result = await self.repo.count_active("proj-1", window_seconds=600)
        self.assertEqual(result, 0, "57-day-old active row must not be counted (OQ-3 defence)")


# ── SqliteSessionRepository.count_active index test ──────────────────────────


class MigrationIndexTests(unittest.IsolatedAsyncioTestCase):
    """Verify the composite index is created and idempotent."""

    async def test_index_created_by_migration(self) -> None:
        """AC-5: idx_sessions_project_status_updated exists after migration runs."""
        from backend.db.sqlite_migrations import _TABLES

        db = await aiosqlite.connect(":memory:")
        try:
            await db.executescript(_TABLES)
            await db.commit()

            # Check PRAGMA index_list
            async with db.execute("PRAGMA index_list(sessions)") as cur:
                rows = await cur.fetchall()
                index_names = {row[1] for row in rows}  # row[1] is the index name

            self.assertIn(
                "idx_sessions_project_status_updated",
                index_names,
                "Composite index must exist after running migrations",
            )
        finally:
            await db.close()

    async def test_migration_idempotent(self) -> None:
        """AC-5: Running the migration script twice must not raise an error."""
        from backend.db.sqlite_migrations import _TABLES

        db = await aiosqlite.connect(":memory:")
        try:
            await db.executescript(_TABLES)
            await db.commit()
            # Run again — IF NOT EXISTS should make this safe
            await db.executescript(_TABLES)
            await db.commit()
        finally:
            await db.close()


# ── LiveMetricsQueryService unit tests ────────────────────────────────────────


class LiveMetricsQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the transport-neutral service layer."""

    async def test_returns_count_from_repository(self) -> None:
        """AC-1: Service correctly returns count from the sessions repository."""
        sessions_repo = types.SimpleNamespace(count_active=AsyncMock(return_value=5))
        ports = _ports(sessions_repo=sessions_repo)
        ctx = _context()

        service = LiveMetricsQueryService()
        # Bypass the cache so tests are deterministic
        with patch(
            "backend.application.services.agent_queries.live_metrics.memoized_query",
            lambda name, **kw: lambda fn: fn,
        ):
            result = await service.get_active_count(ctx, ports)

        self.assertEqual(result.count, 5)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.project_id, "project-1")

    async def test_empty_project_returns_zero(self) -> None:
        """AC-1 resilience: project with no sessions returns count=0, not error."""
        sessions_repo = types.SimpleNamespace(count_active=AsyncMock(return_value=0))
        ports = _ports(sessions_repo=sessions_repo)
        ctx = _context()

        service = LiveMetricsQueryService()
        with patch(
            "backend.application.services.agent_queries.live_metrics.memoized_query",
            lambda name, **kw: lambda fn: fn,
        ):
            result = await service.get_active_count(ctx, ports)

        self.assertEqual(result.count, 0)
        self.assertEqual(result.status, "ok")

    async def test_project_not_found_returns_error_status(self) -> None:
        """AC-1 resilience: unknown project_id returns count=0, status=error."""
        sessions_repo = types.SimpleNamespace(count_active=AsyncMock(return_value=0))
        ports = _ports(project=None, sessions_repo=sessions_repo)
        # Patch workspace registry to return None project
        ports.workspace_registry._project = None
        ctx = _context()

        service = LiveMetricsQueryService()
        with patch(
            "backend.application.services.agent_queries.live_metrics.memoized_query",
            lambda name, **kw: lambda fn: fn,
        ):
            result = await service.get_active_count(ctx, ports, project_id_override="bad-project")

        # When project resolution fails, returns error DTO with count=0
        self.assertEqual(result.count, 0)
        self.assertEqual(result.status, "error")

    async def test_repository_exception_returns_partial(self) -> None:
        """Resilience: storage exception degrades to status=partial, count=0."""
        sessions_repo = types.SimpleNamespace(
            count_active=AsyncMock(side_effect=RuntimeError("DB error"))
        )
        ports = _ports(sessions_repo=sessions_repo)
        ctx = _context()

        service = LiveMetricsQueryService()
        with patch(
            "backend.application.services.agent_queries.live_metrics.memoized_query",
            lambda name, **kw: lambda fn: fn,
        ):
            result = await service.get_active_count(ctx, ports)

        self.assertEqual(result.count, 0)
        self.assertEqual(result.status, "partial")

    async def test_dto_shape(self) -> None:
        """Response DTO has all required contract fields."""
        sessions_repo = types.SimpleNamespace(count_active=AsyncMock(return_value=3))
        ports = _ports(sessions_repo=sessions_repo)
        ctx = _context()

        service = LiveMetricsQueryService()
        with patch(
            "backend.application.services.agent_queries.live_metrics.memoized_query",
            lambda name, **kw: lambda fn: fn,
        ):
            result = await service.get_active_count(ctx, ports)

        # Verify the REST response contract shape
        dto = result.model_dump(mode="json")
        self.assertIn("project_id", dto)
        self.assertIn("count", dto)
        self.assertIn("window_seconds", dto)
        self.assertIn("generated_at", dto)
        self.assertIn("status", dto)
        self.assertIsInstance(dto["count"], int)
        self.assertIsInstance(dto["window_seconds"], int)


# ── PostgresSessionRepository.list_active parity tests ───────────────────────


class PostgresListActiveTests(unittest.IsolatedAsyncioTestCase):
    """Parity tests for PostgresSessionRepository.list_active (no real DB needed).

    Uses MagicMock to simulate asyncpg.Connection and verifies that the correct
    SQL and parameters are dispatched.  These tests fail before the fix (because
    the attribute does not exist) and pass after.

    TC-PG1  Attribute guard: PostgresSessionRepository exposes list_active.
    TC-PG2  Active predicate: correct WHERE / ORDER BY SQL emitted.
    TC-PG3  include_subagents=False appends session_type exclusion to WHERE.
    TC-PG4  limit kwarg appends LIMIT $4 with the correct value.
    TC-PG5  Return shape: asyncpg Record rows are converted to plain dicts.
    TC-PG6  Empty result: returns [] when fetch returns no rows.
    """

    def _make_repo(self):
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository
        conn = MagicMock()
        conn.fetch = AsyncMock()
        return PostgresSessionRepository(conn), conn

    # TC-PG1 ──────────────────────────────────────────────────────────────────

    def test_attribute_guard(self) -> None:
        """list_active must be present on PostgresSessionRepository (fails before fix)."""
        import inspect
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository

        self.assertTrue(
            hasattr(PostgresSessionRepository, "list_active"),
            "PostgresSessionRepository is missing list_active — backend parity gap",
        )
        sig = inspect.signature(PostgresSessionRepository.list_active)
        params = sig.parameters
        self.assertIn("project_id", params)
        self.assertIn("window_seconds", params)
        self.assertIn("limit", params)
        self.assertIn("include_subagents", params)

    # TC-PG2 ──────────────────────────────────────────────────────────────────

    async def test_fetch_called_with_active_predicate(self) -> None:
        """list_active issues the correct active-predicate SQL and positional params."""
        repo, conn = self._make_repo()
        conn.fetch.return_value = []

        result = await repo.list_active("proj-1", window_seconds=300)

        self.assertEqual(result, [])
        self.assertTrue(conn.fetch.called, "db.fetch must be called")
        call_args = conn.fetch.call_args
        sql: str = call_args[0][0]
        positional_params = call_args[0][1:]

        self.assertIn("SELECT * FROM sessions", sql)
        self.assertIn("project_id = $1", sql)
        self.assertIn("status = $2", sql)
        self.assertIn("updated_at >= $3", sql)
        self.assertIn("ORDER BY updated_at DESC", sql)
        self.assertNotIn("LIMIT", sql, "No LIMIT clause expected when limit=None")

        self.assertEqual(positional_params[0], "proj-1")
        self.assertEqual(positional_params[1], "active")
        self.assertIsInstance(positional_params[2], str)
        self.assertIn("T", positional_params[2], "threshold must be an ISO datetime string")

    # TC-PG3 ──────────────────────────────────────────────────────────────────

    async def test_include_subagents_false_appends_session_type_guard(self) -> None:
        """include_subagents=False adds the session_type exclusion clause."""
        repo, conn = self._make_repo()
        conn.fetch.return_value = []
        await repo.list_active("proj-1", include_subagents=False)
        sql: str = conn.fetch.call_args[0][0]
        self.assertIn("session_type", sql)
        self.assertIn("subagent", sql)

    async def test_include_subagents_true_omits_session_type_guard(self) -> None:
        """include_subagents=True (default) must NOT add the session_type clause."""
        repo, conn = self._make_repo()
        conn.fetch.return_value = []
        await repo.list_active("proj-1", include_subagents=True)
        sql: str = conn.fetch.call_args[0][0]
        self.assertNotIn("session_type", sql)

    # TC-PG4 ──────────────────────────────────────────────────────────────────

    async def test_limit_appends_limit_clause_and_param(self) -> None:
        """When limit is not None, LIMIT $4 is appended and its value is the 4th param."""
        repo, conn = self._make_repo()
        conn.fetch.return_value = []
        await repo.list_active("proj-1", limit=10)
        call_args = conn.fetch.call_args
        sql: str = call_args[0][0]
        positional_params = call_args[0][1:]
        self.assertIn("LIMIT $4", sql, "LIMIT clause must reference $4 (4th positional param)")
        self.assertEqual(positional_params[3], 10, "4th param must be the limit value")

    # TC-PG5 ──────────────────────────────────────────────────────────────────

    async def test_rows_converted_to_dicts(self) -> None:
        """Each row returned by db.fetch is converted to a plain dict."""
        repo, conn = self._make_repo()
        row1 = {"id": "sess-1", "status": "active", "project_id": "proj-1"}
        row2 = {"id": "sess-2", "status": "active", "project_id": "proj-1"}
        conn.fetch.return_value = [row1, row2]
        result = await repo.list_active("proj-1")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]["id"], "sess-1")
        self.assertEqual(result[1]["id"], "sess-2")

    # TC-PG6 ──────────────────────────────────────────────────────────────────

    async def test_empty_result_returns_empty_list(self) -> None:
        """When fetch returns no rows, list_active returns []."""
        repo, conn = self._make_repo()
        conn.fetch.return_value = []
        result = await repo.list_active("proj-empty")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
