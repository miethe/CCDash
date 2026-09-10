"""Tests for the unattributed-bucket fold (ccdash-unattributed-0910).

Covers the node's acceptance criteria:
1. Mechanism: one frozen ``ccp-unattributed`` project row; sessions from the
   3 catch-all rows are re-pointed to it; the 3 rows are retired (never
   deleted).
2. Metrics exclusion: ``_filters.fetch_bucket_project_ids`` /
   ``exclude_bucket_projects`` are the single predicate; a system-metrics
   read excludes the bucket while a session-level read for the bucket's own
   project_id still returns its sessions.
3. Reversibility: ``sessions.prior_project_id`` records the pre-fold
   project_id for every moved session.
4. Idempotency: running the fold twice yields identical direct row counts;
   the second run moves/retires nothing.
5. Positive control: 2 unattributable sessions (one per two different
   catch-all rows) + 1 attributed session -> bucket holds 2, the attributed
   project's own count is untouched at 1.

Run as a named module (unscoped collection can hang this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_fold_unattributed_bucket.py -q -p no:cacheprovider
"""
from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries._filters import (
    exclude_bucket_projects,
    fetch_bucket_project_ids,
)
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.system_metrics import SystemMetricsQueryService
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.scripts.fold_unattributed_bucket import (
    CATCHALL_PROJECT_IDS,
    UNATTRIBUTED_BUCKET_ID,
    fold_unattributed_bucket,
)

ATTRIBUTED_PROJECT_ID = "proj-attributed"


def _context(project_id: str = ATTRIBUTED_PROJECT_ID) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Attributed",
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

    def get_active_project(self) -> Any | None:
        return self._projects[0] if self._projects else None

    def resolve_scope(self, project_id: str | None = None):
        return None, None


class _Storage:
    def __init__(self, *, db: Any, sessions_repo: Any) -> None:
        self.db = db
        self._sessions_repo = sessions_repo

    def sessions(self) -> Any:
        return self._sessions_repo


def _make_project(project_id: str, name: str | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=name or project_id)


def _make_ports(*, projects: list[Any], db: Any, sessions_repo: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(projects),
        storage=_Storage(db=db, sessions_repo=sessions_repo),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class _FoldTestBase(unittest.IsolatedAsyncioTestCase):
    """Real migrated SQLite, real upsert paths, real fold."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._tmpdir = Path(tempfile.mkdtemp())
        self.db = await aiosqlite.connect(str(self._tmpdir / "t.db"))
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def _count(self, sql: str, params: tuple = ()) -> int:
        cursor = await self.db.execute(sql, params)
        (count,) = await cursor.fetchone()
        return int(count)

    async def _seed_session(self, session_id: str, project_id: str, **overrides) -> None:
        data = {
            "id": session_id,
            "taskId": "",
            "status": "completed",
            "model": "claude-sonnet-5",
            "platformType": "Claude Code",
            "startedAt": "2026-01-01T00:00:00Z",
            "endedAt": "2026-01-01T00:10:00Z",
        }
        data.update(overrides)
        await self.session_repo.upsert(data, project_id)

    async def _seed_catchall_project(self, project_id: str, name: str) -> None:
        await self.db.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)", (project_id, name)
        )
        await self.db.commit()


class PositiveControlAndReversibilityTests(_FoldTestBase):
    async def test_positive_control_two_unattributable_one_attributed(self) -> None:
        """AC5: 2 unattributable sessions + 1 attributed -> bucket holds 2,
        the attributed project's own count stays 1."""
        catchall_a, catchall_b = CATCHALL_PROJECT_IDS[0], CATCHALL_PROJECT_IDS[1]
        await self._seed_catchall_project(catchall_a, "development")
        await self._seed_catchall_project(catchall_b, "miethe")
        await self._seed_session("s-unattr-1", catchall_a)
        await self._seed_session("s-unattr-2", catchall_b)
        await self._seed_session("s-attributed", ATTRIBUTED_PROJECT_ID)

        stats = await fold_unattributed_bucket(self.db)

        self.assertEqual(stats["sessions_moved"], 2)
        # Direct-count assertions (ADR-007) -- never trust the method's own
        # return value alone.
        self.assertEqual(
            await self._count("SELECT COUNT(*) FROM sessions WHERE project_id = ?", (UNATTRIBUTED_BUCKET_ID,)),
            2,
        )
        self.assertEqual(
            await self._count("SELECT COUNT(*) FROM sessions WHERE project_id = ?", (ATTRIBUTED_PROJECT_ID,)),
            1,
        )
        # No session was orphaned: total row count is unchanged (3 in, 3 out).
        self.assertEqual(await self._count("SELECT COUNT(*) FROM sessions"), 3)

    async def test_reversibility_prior_project_id_recorded(self) -> None:
        """AC3: prior_project_id records exactly where each moved session came from."""
        catchall = CATCHALL_PROJECT_IDS[0]
        await self._seed_catchall_project(catchall, "development")
        await self._seed_session("s1", catchall)

        await fold_unattributed_bucket(self.db)

        cursor = await self.db.execute(
            "SELECT project_id, prior_project_id FROM sessions WHERE id = ?", ("s1",)
        )
        row = await cursor.fetchone()
        self.assertEqual(row["project_id"], UNATTRIBUTED_BUCKET_ID)
        self.assertEqual(row["prior_project_id"], catchall)

    async def test_catchall_rows_retired_not_deleted(self) -> None:
        catchall = CATCHALL_PROJECT_IDS[0]
        await self._seed_catchall_project(catchall, "development")
        await self._seed_session("s1", catchall)

        await fold_unattributed_bucket(self.db)

        cursor = await self.db.execute(
            "SELECT bucket_role FROM projects WHERE id = ?", (catchall,)
        )
        row = await cursor.fetchone()
        self.assertIsNotNone(row, "the catch-all row must still exist -- never deleted")
        self.assertEqual(row["bucket_role"], "retired_catchall")

        bucket_cursor = await self.db.execute(
            "SELECT bucket_role FROM projects WHERE id = ?", (UNATTRIBUTED_BUCKET_ID,)
        )
        bucket_row = await bucket_cursor.fetchone()
        self.assertEqual(bucket_row["bucket_role"], "unattributed_bucket")


class IdempotencyTests(_FoldTestBase):
    async def test_fold_is_idempotent(self) -> None:
        """AC4: running twice yields identical direct row counts; the second
        run moves/retires nothing."""
        catchall_a, catchall_b = CATCHALL_PROJECT_IDS[0], CATCHALL_PROJECT_IDS[1]
        await self._seed_catchall_project(catchall_a, "development")
        await self._seed_catchall_project(catchall_b, "miethe")
        await self._seed_session("s1", catchall_a)
        await self._seed_session("s2", catchall_b)
        await self._seed_session("s3", ATTRIBUTED_PROJECT_ID)

        first = await fold_unattributed_bucket(self.db)
        counts_after_first = {
            "sessions": await self._count("SELECT COUNT(*) FROM sessions"),
            "bucket_sessions": await self._count(
                "SELECT COUNT(*) FROM sessions WHERE project_id = ?", (UNATTRIBUTED_BUCKET_ID,)
            ),
            "projects": await self._count("SELECT COUNT(*) FROM projects"),
        }

        second = await fold_unattributed_bucket(self.db)
        counts_after_second = {
            "sessions": await self._count("SELECT COUNT(*) FROM sessions"),
            "bucket_sessions": await self._count(
                "SELECT COUNT(*) FROM sessions WHERE project_id = ?", (UNATTRIBUTED_BUCKET_ID,)
            ),
            "projects": await self._count("SELECT COUNT(*) FROM projects"),
        }

        self.assertEqual(counts_after_first, counts_after_second)
        self.assertGreater(first["sessions_moved"], 0)
        self.assertEqual(second["sessions_moved"], 0)
        self.assertGreater(first["catchall_rows_retired"], 0)
        self.assertEqual(second["catchall_rows_retired"], 0)


class ExclusionPredicateTests(_FoldTestBase):
    async def test_fetch_bucket_project_ids_empty_before_fold(self) -> None:
        await self._seed_catchall_project(CATCHALL_PROJECT_IDS[0], "development")
        self.assertEqual(await fetch_bucket_project_ids(self.db), set())

    async def test_fetch_bucket_project_ids_after_fold(self) -> None:
        catchall = CATCHALL_PROJECT_IDS[0]
        await self._seed_catchall_project(catchall, "development")
        await self._seed_session("s1", catchall)

        await fold_unattributed_bucket(self.db)

        excluded = await fetch_bucket_project_ids(self.db)
        self.assertIn(UNATTRIBUTED_BUCKET_ID, excluded)
        self.assertIn(catchall, excluded)

    def test_exclude_bucket_projects_pure_filter(self) -> None:
        p1 = _make_project("keep-me")
        p2 = _make_project(UNATTRIBUTED_BUCKET_ID)
        result = exclude_bucket_projects([p1, p2], {UNATTRIBUTED_BUCKET_ID})
        self.assertEqual([p.id for p in result], ["keep-me"])


class MetricsExclusionAndSessionListReadTests(_FoldTestBase):
    async def test_bucket_absent_from_system_metrics_but_present_in_session_list(self) -> None:
        """AC2/AC4: per-project metrics exclude the bucket; a session-level
        read for the bucket's own project_id still lists its sessions."""
        catchall = CATCHALL_PROJECT_IDS[0]
        await self._seed_catchall_project(catchall, "development")
        await self._seed_session("s1", catchall)
        await self._seed_session("s2", ATTRIBUTED_PROJECT_ID)

        await fold_unattributed_bucket(self.db)

        bucket_project = _make_project(UNATTRIBUTED_BUCKET_ID, "Unattributed")
        attributed_project = _make_project(ATTRIBUTED_PROJECT_ID)
        ports = _make_ports(
            projects=[bucket_project, attributed_project],
            db=self.db,
            sessions_repo=self.session_repo,
        )

        svc = SystemMetricsQueryService()
        dto = await svc.get_system_active_count(_context(), ports, bypass_cache=True)
        by_id = {p.project_id: p for p in dto.per_project}

        self.assertNotIn(
            UNATTRIBUTED_BUCKET_ID, by_id,
            "the unattributed bucket must be excluded from cross-project metrics",
        )
        self.assertIn(ATTRIBUTED_PROJECT_ID, by_id)

        # Session-level view: the bucket's own sessions remain directly
        # queryable by project_id -- this predicate must never touch that path.
        bucket_sessions = await self.session_repo.list_paginated(
            offset=0, limit=50, project_id=UNATTRIBUTED_BUCKET_ID
        )
        self.assertEqual(len(bucket_sessions), 1)
        self.assertEqual(bucket_sessions[0]["id"], "s1")


if __name__ == "__main__":
    unittest.main()
