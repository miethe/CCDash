"""Phase 4 (T4-003) worker sweep tests for ``RoutingRollupSweepJob``.

Covers this task's three required tests (per
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-4-worker-sweep-job.md``,
Task T4-003):

  - **Multi-project sweep**: ``project=None`` construction enumerates and
    sweeps EVERY project ``ports.workspace_registry.list_projects()``
    returns in a single tick, mirroring
    ``MultiProjectAARReviewSweepTests.test_sweeps_multiple_registered_projects_in_one_tick``'s
    fixture shape from ``backend/tests/test_aar_review_worker_guards.py``.
    This same test also covers the cache-invalidation acceptance criterion
    ("fires exactly once per project that wrote at least one row, and never
    fires for a project whose tick wrote nothing") across three projects: two
    with in-window sessions (rows written) and one with none (no write, no
    invalidation) -- mirroring
    ``AARReviewSweepJobTests.test_cache_invalidation_hook_fires_only_on_write``'s
    assertion shape.
  - **Flag-off no-op**: with ``CCDASH_ROUTING_FEEDBACK_ENABLED=False``,
    ``execute()`` returns ``outcome="disabled"``, the ``routing_rollup``
    table's row count is unchanged (zero writes), and
    ``RoutingRollupQueryService`` is never even constructed -- the sweep body
    is skipped entirely, not merely gated at the write step.
  - **Flag-flip reversibility (AC-7)**: one sweep with the flag enabled
    writes rows; flipping ``CCDASH_ROUTING_FEEDBACK_ENABLED`` to ``False`` and
    running a second tick produces ZERO new writes and the row count is
    byte-for-byte unchanged from the first tick.

Per this task's own Implementation Notes ("do not treat this task's green
test as the final AC-7 sign-off, only as this phase's contribution to it"):
Phase 5's read-side transports (``GET /api/v1/routing/rollup``, the MCP tool,
the CLI command) do not exist yet as of this module -- all three are still
``pending`` in ``.claude/progress/proof-to-routing-loop/phase-5-progress.md``.
This file's reversibility test therefore asserts reversibility at the
worker/repository layer only (zero new writes across the flip boundary, row
count unchanged); the cross-transport "read surfaces report disabled
immediately after the flip" half of AC-7 is Phase 6's T6-006, not
duplicated/fabricated here against transports that do not yet exist.

HARD INVARIANT: zero LLM/model calls anywhere on this path -- every fixture
below is a plain ``types.SimpleNamespace``/dict/``AsyncMock``; no model/agent
client is imported.

Run as a named module (full collection can hang -- see this repo's
documented pytest-collection-hang caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_sweep_job.py -v
"""
from __future__ import annotations

import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.adapters.jobs.routing_rollup_sweep_job import (
    RoutingRollupSweepJob,
    RoutingRollupSweepRunResult,
)
from backend.application.context import Principal, ProjectScope
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.db.repositories.routing_rollup import SqliteRoutingRollupRepository
from backend.db.sqlite_migrations import run_migrations


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _in_window_updated_at(days_ago: int = 1) -> str:
    """A naive ``YYYY-MM-DDTHH:MM:SS`` timestamp *days_ago* days before "now",
    matching the exact naive-string convention
    ``routing_rollup.py::_iso()`` renders window boundaries in for its
    ``sessions.updated_at`` SQL comparison (see that helper's own docstring).
    Deliberately real-clock-relative (unlike
    ``test_routing_rollup_determinism.py``'s pinned fixture) because this
    module's sweep tests never patch ``resolve_time_window`` -- they exercise
    the job's real default rolling window end to end.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    skill_name: str,
    model: str = "claude-sonnet-5",
    updated_at: str | None = None,
) -> None:
    """Insert a minimal ``sessions`` row exercising the columns
    ``RoutingRollupQueryService.fetch_raw_rows`` groups/filters on. Mirrors
    ``test_routing_rollup_determinism.py::_insert_session`` exactly."""
    resolved_updated_at = updated_at if updated_at is not None else _in_window_updated_at()
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, project_id, skill_name, model, status, updated_at, created_at, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            project_id,
            skill_name,
            model,
            "completed",
            resolved_updated_at,
            resolved_updated_at,
            f"{session_id}.jsonl",
        ),
    )
    await db.commit()


class _IdentityProvider:
    """Mirrors ``test_aar_review_worker_guards.py``'s ``_IdentityProvider``
    exactly -- ``RoutingRollupSweepJob._execute_inner`` resolves an
    ``ApplicationRequest`` via the same ``resolve_application_request`` ->
    ``build_compat_request_context`` -> ``ports.identity_provider.get_principal``
    path ``AARReviewSweepJob._execute_inner`` does."""

    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(
            subject="routing-rollup-sweep", display_name="Routing Rollup Sweep", auth_mode="test"
        )


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    """Single-project workspace registry -- mirrors
    ``test_aar_review_worker_guards.py``'s ``_WorkspaceRegistry`` exactly
    (including the kwarg-less ``resolve_scope`` signature that
    ``_resolve_workspace_scope``'s ``TypeError``-retry path already tolerates)."""

    def __init__(self, project: Any):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path(f"/tmp/{resolved_id}"),
            sessions_dir=Path(f"/tmp/{resolved_id}/sessions"),
            docs_dir=Path(f"/tmp/{resolved_id}/docs"),
            progress_dir=Path(f"/tmp/{resolved_id}/progress"),
        )


class _MultiWorkspaceRegistry:
    """Multi-project registry backing ``list_projects()`` with a real,
    non-empty list, mirroring
    ``test_aar_review_worker_guards.py::_MultiWorkspaceRegistry`` exactly --
    so ``RoutingRollupSweepJob._resolve_projects_to_sweep`` fans out across
    all of them when constructed with ``project=None``."""

    def __init__(self, projects: list[Any]):
        self._by_id = {str(getattr(p, "id", "") or ""): p for p in projects}

    def list_projects(self) -> list[Any]:
        return list(self._by_id.values())

    def get_project(self, project_id):
        return self._by_id.get(project_id)

    def get_active_project(self):
        return next(iter(self._by_id.values()), None)

    def resolve_scope(self, project_id=None):
        project = self._by_id.get(project_id) if project_id else self.get_active_project()
        if project is None:
            return None, None
        return None, ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=Path(f"/tmp/{project.id}"),
            sessions_dir=Path(f"/tmp/{project.id}/sessions"),
            docs_dir=Path(f"/tmp/{project.id}/docs"),
            progress_dir=Path(f"/tmp/{project.id}/progress"),
        )


class _Storage:
    """Only ``.db`` is ever read on this path -- both
    ``RoutingRollupQueryService.fetch_raw_rows`` and
    ``RoutingRollupSweepJob._execute_inner``'s ``_routing_rollup_repo(...)``
    dispatch read raw SQL straight off ``ports.storage.db``; no
    documents/sessions/entity_links repo indirection exists for this
    feature (unlike the AAR-review precedent)."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db


def _build_ports(db: aiosqlite.Connection, *, project: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


def _build_multi_project_ports(db: aiosqlite.Connection, *, projects: list[Any]) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_MultiWorkspaceRegistry(projects),
        storage=_Storage(db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


_CACHE_CLEAR_TARGET = "backend.application.services.agent_queries.aclear_project_cache"


class RoutingRollupSweepJobTests(unittest.IsolatedAsyncioTestCase):
    """Single-project flag-off no-op + flag-flip reversibility (AC-7)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self._flag_patch = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        self._flag_patch.start()

    async def asyncTearDown(self) -> None:
        self._flag_patch.stop()
        await self.db.close()

    async def _count(self, project_id: str | None = None) -> int:
        if project_id is None:
            cursor = await self.db.execute("SELECT COUNT(*) FROM routing_rollup")
        else:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM routing_rollup WHERE project_id = ?", (project_id,)
            )
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_disabled_flag_is_a_no_op_and_skips_the_query_service_entirely(self) -> None:
        """AC (T4-001, re-verified here): a flag-off run performs zero writes
        and makes zero calls into ``RoutingRollupQueryService`` -- the sweep
        body is skipped entirely, not silently no-op-written. Fixture data
        would produce non-zero rows if the flag were honored incorrectly, so
        this is a real negative assertion, not a trivially-empty one."""
        project = types.SimpleNamespace(id="project-1", name="Project 1")
        await _insert_session(self.db, session_id="s1", project_id="project-1", skill_name="debugging")
        ports = _build_ports(self.db, project=project)

        self._flag_patch.stop()
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            with patch(
                "backend.application.services.agent_queries.routing_rollup.RoutingRollupQueryService"
            ) as mock_service_cls:
                job = RoutingRollupSweepJob(ports=ports, project=project)
                result = await job.execute()
        self._flag_patch = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        self._flag_patch.start()

        self.assertEqual(result.outcome, "disabled")
        self.assertTrue(result.success)
        self.assertEqual(await self._count(), 0)
        mock_service_cls.assert_not_called()

    async def test_flag_flip_reversibility_produces_zero_new_writes_on_next_tick(self) -> None:
        """AC-7: flip ``CCDASH_ROUTING_FEEDBACK_ENABLED`` to ``False`` mid-run
        -> the very next tick performs zero new writes and the row count is
        byte-for-byte unchanged across the flip boundary. This is Phase 4's
        own partial closure of AC-7 (worker/repository layer only) -- Phase
        6's T6-006 owns the feature-level, cross-transport final validation
        (see this task's own Implementation Notes)."""
        project = types.SimpleNamespace(id="project-1", name="Project 1")
        await _insert_session(self.db, session_id="s1", project_id="project-1", skill_name="debugging")
        await _insert_session(self.db, session_id="s2", project_id="project-1", skill_name="planning")
        ports = _build_ports(self.db, project=project)
        job = RoutingRollupSweepJob(ports=ports, project=project)

        # Tick 1 -- flag enabled -- writes rows.
        with patch(_CACHE_CLEAR_TARGET, new=AsyncMock()):
            first_result = await job.execute(trigger="scheduled")
        self.assertEqual(first_result.outcome, "success")
        self.assertGreater(first_result.rows_written, 0)
        count_after_first_tick = await self._count(project_id="project-1")
        self.assertGreater(count_after_first_tick, 0)

        rows_before_flip = await SqliteRoutingRollupRepository(self.db).get_by_project("project-1")

        # Flip the flag off mid-run (no worker restart -- same job instance,
        # same in-process watermark state -- this is exactly the scenario
        # the double-gated flag check exists to cover).
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            with patch(
                "backend.application.services.agent_queries.routing_rollup.RoutingRollupQueryService"
            ) as mock_service_cls:
                with patch(_CACHE_CLEAR_TARGET, new=AsyncMock()) as mock_clear_after_flip:
                    second_result = await job.execute(trigger="scheduled")

        self.assertEqual(second_result.outcome, "disabled")
        self.assertTrue(second_result.success)
        mock_service_cls.assert_not_called()
        mock_clear_after_flip.assert_not_awaited()

        # No residual writes survive the flag flip -- row count is
        # byte-for-byte unchanged, and every persisted row is untouched.
        count_after_flip_tick = await self._count(project_id="project-1")
        self.assertEqual(count_after_flip_tick, count_after_first_tick)
        rows_after_flip = await SqliteRoutingRollupRepository(self.db).get_by_project("project-1")
        self.assertEqual(rows_after_flip, rows_before_flip)


class MultiProjectRoutingRollupSweepTests(unittest.IsolatedAsyncioTestCase):
    """``project=None`` construction must enumerate and sweep EVERY
    registered project via ``ports.workspace_registry.list_projects()`` in a
    single tick -- not just whichever single project the worker's sync
    engine happens to be bound to. Also covers this task's cache-
    invalidation acceptance criterion (fires exactly once per project that
    wrote at least one row; never fires for a project whose tick wrote
    nothing)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self._flag_patch = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        self._flag_patch.start()

    async def asyncTearDown(self) -> None:
        self._flag_patch.stop()
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM routing_rollup")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_sweeps_every_registered_project_in_one_tick_and_invalidates_cache_only_on_write(
        self,
    ) -> None:
        project_a = types.SimpleNamespace(id="project-a", name="Project A")
        project_b = types.SimpleNamespace(id="project-b", name="Project B")
        # project-c is registered but has NO in-window sessions -- its tick
        # must write zero rows and must never trigger a cache invalidation.
        project_c = types.SimpleNamespace(id="project-c", name="Project C")

        await _insert_session(self.db, session_id="s-a1", project_id="project-a", skill_name="debugging")
        await _insert_session(self.db, session_id="s-a2", project_id="project-a", skill_name="planning")
        await _insert_session(self.db, session_id="s-b1", project_id="project-b", skill_name="codex")

        ports = _build_multi_project_ports(self.db, projects=[project_a, project_b, project_c])
        # project=None -> the job must enumerate ALL registered projects via
        # the registry rather than being scoped to a single bound project.
        job = RoutingRollupSweepJob(ports=ports, project=None)

        with patch(_CACHE_CLEAR_TARGET, new=AsyncMock()) as mock_clear:
            result = await job.execute()

        self.assertEqual(result.outcome, "success")
        self.assertTrue(result.success)
        self.assertEqual(
            sorted(result.details.get("projectIds", [])), ["project-a", "project-b", "project-c"]
        )
        self.assertEqual(result.details.get("projectCount"), 3)

        repo = SqliteRoutingRollupRepository(self.db)
        rows_a = await repo.get_by_project("project-a")
        rows_b = await repo.get_by_project("project-b")
        rows_c = await repo.get_by_project("project-c")
        self.assertGreater(len(rows_a), 0)
        self.assertGreater(len(rows_b), 0)
        self.assertEqual(rows_c, [], "project-c has no in-window sessions and must write zero rows")
        self.assertEqual(await self._count(), len(rows_a) + len(rows_b))

        # Cache invalidation fires exactly once per project that wrote at
        # least one row -- never for project-c, whose tick wrote nothing.
        self.assertEqual(mock_clear.await_count, 2)
        mock_clear.assert_any_await("project-a")
        mock_clear.assert_any_await("project-b")
        awaited_project_ids = {call.args[0] for call in mock_clear.await_args_list}
        self.assertNotIn("project-c", awaited_project_ids)

        # Watermarks are tracked independently per project that produced at
        # least one key -- project-c (zero keys) never gets a watermark
        # entry (module docstring: observational only, set only when a
        # newest window_end exists).
        self.assertIn("project-a", job._watermarks)
        self.assertIn("project-b", job._watermarks)
        self.assertNotIn("project-c", job._watermarks)


if __name__ == "__main__":
    unittest.main()
