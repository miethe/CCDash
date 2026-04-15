"""Integration tests for the background cache warming job (Phase 4).

Tests cover:
- BG-004: The warming coroutine is invoked at least once within the configured
  interval, caches are populated after a run, and errors inside the coroutine
  do not propagate out of the asyncio Task.
- BG-005: ``CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0`` disables the job
  (``_start_cache_warming_task`` returns None and no Task is created).

All tests are hermetic — they monkeypatch config, stub out service calls, and
use an in-process asyncio event loop via ``asyncio.run`` / ``IsolatedAsyncioTestCase``.
"""
from __future__ import annotations

import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.adapters.jobs.runtime import RuntimeJobAdapter, RuntimeJobState
from backend.application.context import (
    Principal,
    ProjectScope,
    TenancyContext,
    TraceContext,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _make_project(project_id: str = "proj-warm-test") -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.name = "Warm Test"
    return project


def _make_project_scope(project_id: str) -> ProjectScope:
    return ProjectScope(
        project_id=project_id,
        project_name="Warm Test",
        root_path=Path("/tmp/warm"),
        sessions_dir=Path("/tmp/warm/sessions"),
        docs_dir=Path("/tmp/warm/docs"),
        progress_dir=Path("/tmp/warm/progress"),
    )


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        return None, _make_project_scope(self._project.id)

    def list_projects(self):
        return [self._project] if self._project else []


class _JobScheduler:
    """Captures scheduled coroutines and creates real asyncio Tasks."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self.tasks: list[asyncio.Task] = []
        self._loop = loop

    def schedule(self, coro, *, name: str = "") -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        task.set_name(name)
        self.tasks.append(task)
        return task


def _make_ports(project) -> MagicMock:
    ports = MagicMock()
    ports.workspace_registry = _WorkspaceRegistry(project)
    ports.job_scheduler = _JobScheduler()
    # storage.db is not used during the warming job itself (only inside the
    # service methods which are fully mocked in these tests).
    ports.storage = MagicMock()
    return ports


def _make_profile(jobs: bool = True) -> MagicMock:
    profile = MagicMock()
    profile.name = "worker"
    profile.capabilities.jobs = jobs
    profile.capabilities.sync = False
    profile.capabilities.watch = False
    profile.capabilities.integrations = False
    return profile


def _make_adapter(project, jobs: bool = True) -> RuntimeJobAdapter:
    ports = _make_ports(project)
    return RuntimeJobAdapter(
        profile=_make_profile(jobs=jobs),
        ports=ports,
        sync_engine=None,
        project_binding=None,
        telemetry_exporter_job=None,
    )


# ---------------------------------------------------------------------------
# BG-005: interval=0 disables the job
# ---------------------------------------------------------------------------

class TestCacheWarmingDisabledWhenIntervalZero(unittest.TestCase):
    """When interval=0 _start_cache_warming_task must return None."""

    def test_returns_none_when_interval_is_zero(self):
        project = _make_project()
        adapter = _make_adapter(project)
        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 0
            # Also satisfy the analytics / telemetry interval reads
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0
            result = adapter._start_cache_warming_task()
        self.assertIsNone(result)

    def test_returns_none_when_interval_is_negative(self):
        project = _make_project()
        adapter = _make_adapter(project)
        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = -10
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0
            result = adapter._start_cache_warming_task()
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# BG-004: warming runs and populates the cache; errors are swallowed
# ---------------------------------------------------------------------------

class TestCacheWarmingJobRuns(unittest.IsolatedAsyncioTestCase):
    """The warming task calls both service methods and swallows service errors."""

    async def _run_one_warming_cycle(
        self,
        project_status_side_effect=None,
        workflow_side_effect=None,
        interval: int = 1,
    ):
        """Helper that starts the warming task, waits long enough for one cycle,
        then cancels the task and returns (status_call_count, workflow_call_count)."""
        project = _make_project()
        adapter = _make_adapter(project)

        status_mock = AsyncMock(return_value=MagicMock())
        workflow_mock = AsyncMock(return_value=MagicMock())
        if project_status_side_effect is not None:
            status_mock.side_effect = project_status_side_effect
        if workflow_side_effect is not None:
            workflow_mock.side_effect = workflow_side_effect

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 status_mock,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 workflow_mock,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = interval
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None

            # Wait slightly beyond one interval so the loop body executes once.
            await asyncio.sleep(interval + 0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        return status_mock.call_count, workflow_mock.call_count

    async def test_warming_invokes_both_services_at_least_once(self):
        status_calls, workflow_calls = await self._run_one_warming_cycle(interval=1)
        self.assertGreaterEqual(status_calls, 1, "project_status should be called at least once")
        self.assertGreaterEqual(workflow_calls, 1, "workflow_diagnostics should be called at least once")

    async def test_service_error_does_not_crash_task(self):
        """An exception in get_status must not crash the warming task."""
        # Both services raise; the task should still be cancellable (not dead from exception).
        project = _make_project()
        adapter = _make_adapter(project)

        status_mock = AsyncMock(side_effect=RuntimeError("boom"))
        workflow_mock = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 status_mock,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 workflow_mock,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 1
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None

            # Wait for one full cycle — the errors should be caught, not re-raised.
            await asyncio.sleep(1.5)
            # Task should still be running (not done due to an exception).
            self.assertFalse(task.done(), "Task must still be alive after service errors")

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_task_is_named_correctly(self):
        project = _make_project()
        adapter = _make_adapter(project)

        status_mock = AsyncMock(return_value=MagicMock())
        workflow_mock = AsyncMock(return_value=MagicMock())

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 status_mock,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 workflow_mock,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 60
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None
            self.assertIn("cache-warming", task.get_name())

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_no_active_project_skips_gracefully(self):
        """When no active project exists the warming loop should not crash."""
        # Build adapter with a registry that returns None for the active project.
        ports = MagicMock()
        ports.workspace_registry = _WorkspaceRegistry(project=None)
        ports.job_scheduler = _JobScheduler()
        ports.storage = MagicMock()

        adapter = RuntimeJobAdapter(
            profile=_make_profile(jobs=True),
            ports=ports,
            sync_engine=None,
            project_binding=None,
            telemetry_exporter_job=None,
        )

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 1
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None

            await asyncio.sleep(1.5)
            self.assertFalse(task.done(), "Task must still be alive when no project is found")

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_status_snapshot_reflects_warming_task(self):
        """status_snapshot() should report cacheWarming=running while task is alive."""
        project = _make_project()
        adapter = _make_adapter(project)

        status_mock = AsyncMock(return_value=MagicMock())
        workflow_mock = AsyncMock(return_value=MagicMock())

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 status_mock,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 workflow_mock,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 60
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0
            # Suppress analytics + telemetry task creation so only cache task starts.
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None
            adapter.state.cache_warming_task = task

            snapshot = adapter.status_snapshot()
            self.assertEqual(snapshot["cacheWarming"], "running")

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# BG-004 (additional): stop() cancels the warming task
# ---------------------------------------------------------------------------

class TestCacheWarmingStop(unittest.IsolatedAsyncioTestCase):
    async def test_stop_cancels_warming_task(self):
        project = _make_project()
        adapter = _make_adapter(project)

        status_mock = AsyncMock(return_value=MagicMock())
        workflow_mock = AsyncMock(return_value=MagicMock())

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 status_mock,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 workflow_mock,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 60
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None
            adapter.state.cache_warming_task = task

            await adapter.stop()
            self.assertIsNone(adapter.state.cache_warming_task)
            self.assertTrue(task.done())


if __name__ == "__main__":
    unittest.main()
