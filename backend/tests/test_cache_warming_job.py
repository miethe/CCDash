"""Integration tests for the background cache warming job (Phase 4).

Tests cover:
- BG-004: The warming coroutine is invoked at least once within the configured
  interval, caches are populated after a run, and errors inside the coroutine
  do not propagate out of the asyncio Task.
- BG-005: ``CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0`` disables the job
  (``_start_cache_warming_task`` returns None and no Task is created).
- TEST-004-C2: The warming task does not block concurrent coroutines (non-blocking).
- TEST-004-C5: The query cache contains entries after a warming cycle completes.

All tests are hermetic — they monkeypatch config, stub out service calls, and
use an in-process asyncio event loop via ``asyncio.run`` / ``IsolatedAsyncioTestCase``.
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.adapters.jobs.runtime import RuntimeJobAdapter
from backend.application.context import (
    ProjectScope,
)
from backend.runtime.bootstrap_worker import build_worker_probe_app
from fastapi.testclient import TestClient


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


def _make_adapter(project, jobs: bool = True, telemetry_exporter_job=None) -> RuntimeJobAdapter:
    ports = _make_ports(project)
    return RuntimeJobAdapter(
        profile=_make_profile(jobs=jobs),
        ports=ports,
        sync_engine=None,
        project_binding=None,
        telemetry_exporter_job=telemetry_exporter_job,
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

        return adapter, status_mock.call_count, workflow_mock.call_count

    async def test_warming_invokes_both_services_at_least_once(self):
        _, status_calls, workflow_calls = await self._run_one_warming_cycle(interval=1)
        self.assertGreaterEqual(status_calls, 1, "project_status should be called at least once")
        self.assertGreaterEqual(workflow_calls, 1, "workflow_diagnostics should be called at least once")

    async def test_worker_probe_snapshot_tracks_cache_warming_markers(self):
        adapter, _, _ = await self._run_one_warming_cycle(interval=1)

        snapshot = adapter.status_snapshot()
        worker_probe = snapshot["workerProbe"]
        cache_warming = worker_probe["jobs"]["cacheWarming"]

        self.assertEqual(worker_probe["schemaVersion"], "ops-203-v1")
        self.assertEqual(cache_warming["state"], "succeeded")
        self.assertEqual(cache_warming["backlogCount"], 0)
        self.assertIsNotNone(cache_warming["checkpointAt"])
        self.assertIsNotNone(cache_warming["lastSuccessAt"])
        self.assertEqual(
            cache_warming["details"]["targets"],
            ["project_status", "workflow_diagnostics"],
        )

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


class TestWorkerProbeTelemetry(unittest.IsolatedAsyncioTestCase):
    def test_worker_job_helpers_receive_freshness_and_backpressure_values(self):
        project = _make_project()
        adapter = _make_adapter(project)

        with patch(
            "backend.adapters.jobs.runtime.config.resolve_runtime_environment_contract",
            return_value=SimpleNamespace(deployment_mode="hosted"),
        ), \
            patch(
                "backend.adapters.jobs.runtime._freshness_seconds",
                side_effect=[None, 12],
            ), \
            patch(
                "backend.adapters.jobs.runtime.observability.set_worker_job_freshness",
            ) as freshness_mock, \
            patch(
                "backend.adapters.jobs.runtime.observability.set_worker_job_backpressure",
            ) as backpressure_mock:
            started = adapter._mark_job_started("telemetryExports")
            adapter._mark_job_success(
                "telemetryExports",
                started,
                backlog_count=7,
                checkpoint_at="2026-04-15T12:00:00Z",
                details={"projectId": project.id},
            )

        self.assertEqual(freshness_mock.call_count, 2)
        self.assertEqual(backpressure_mock.call_count, 2)

        started_freshness = freshness_mock.call_args_list[0].kwargs
        success_freshness = freshness_mock.call_args_list[1].kwargs
        started_backpressure = backpressure_mock.call_args_list[0].kwargs
        success_backpressure = backpressure_mock.call_args_list[1].kwargs

        self.assertEqual(started_freshness["job_name"], "telemetryExports")
        self.assertEqual(started_freshness["project_id"], project.id)
        self.assertIsNone(started_freshness["freshness_ms"])
        self.assertEqual(started_freshness["runtime_metadata"]["runtimeProfile"], "worker")
        self.assertEqual(started_freshness["runtime_metadata"]["deploymentMode"], "hosted")

        self.assertEqual(success_freshness["job_name"], "telemetryExports")
        self.assertEqual(success_freshness["project_id"], project.id)
        self.assertEqual(success_freshness["freshness_ms"], 12000.0)
        self.assertEqual(success_freshness["runtime_metadata"]["runtimeProfile"], "worker")
        self.assertEqual(success_freshness["runtime_metadata"]["deploymentMode"], "hosted")

        self.assertEqual(started_backpressure["job_name"], "telemetryExports")
        self.assertEqual(started_backpressure["project_id"], project.id)
        self.assertEqual(started_backpressure["backpressure_ratio"], 0.0)
        self.assertEqual(started_backpressure["runtime_metadata"]["runtimeProfile"], "worker")

        self.assertEqual(success_backpressure["job_name"], "telemetryExports")
        self.assertEqual(success_backpressure["project_id"], project.id)
        self.assertEqual(success_backpressure["backpressure_ratio"], 1.0)
        self.assertEqual(success_backpressure["runtime_metadata"]["runtimeProfile"], "worker")

    def test_worker_job_helpers_drop_backpressure_after_successful_drain(self):
        project = _make_project()
        adapter = _make_adapter(project)

        with patch(
            "backend.adapters.jobs.runtime.config.resolve_runtime_environment_contract",
            return_value=SimpleNamespace(deployment_mode="hosted"),
        ), \
            patch(
                "backend.adapters.jobs.runtime._freshness_seconds",
                side_effect=[None, 0],
            ), \
            patch(
                "backend.adapters.jobs.runtime.observability.set_worker_job_freshness",
            ) as freshness_mock, \
            patch(
                "backend.adapters.jobs.runtime.observability.set_worker_job_backpressure",
            ) as backpressure_mock:
            started = adapter._mark_job_started("cacheWarming", backlog_count=1)
            adapter._mark_job_success(
                "cacheWarming",
                started,
                backlog_count=0,
                details={"projectId": project.id},
            )

        self.assertEqual(freshness_mock.call_args_list[-1].kwargs["job_name"], "cacheWarming")
        self.assertEqual(freshness_mock.call_args_list[-1].kwargs["project_id"], project.id)
        self.assertEqual(freshness_mock.call_args_list[-1].kwargs["freshness_ms"], 0.0)
        self.assertEqual(backpressure_mock.call_args_list[0].kwargs["backpressure_ratio"], 1.0)
        self.assertEqual(backpressure_mock.call_args_list[-1].kwargs["job_name"], "cacheWarming")
        self.assertEqual(backpressure_mock.call_args_list[-1].kwargs["project_id"], project.id)
        self.assertEqual(backpressure_mock.call_args_list[-1].kwargs["backpressure_ratio"], 0.0)

    async def test_worker_probe_snapshot_tracks_telemetry_backlog_and_checkpoint(self):
        project = _make_project()
        telemetry_job = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    success=True,
                    outcome="success",
                    batch_size=3,
                    duration_ms=42,
                )
            ),
            coordinator=SimpleNamespace(
                status=AsyncMock(
                    return_value=SimpleNamespace(
                        queueStats=SimpleNamespace(pending=7),
                        lastPushTimestamp="2026-04-15T12:00:00Z",
                        eventsPushed24h=19,
                        configured=True,
                        envLocked=False,
                        persistedEnabled=True,
                    )
                )
            ),
        )
        adapter = _make_adapter(project, telemetry_exporter_job=telemetry_job)

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 0
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 1

            task = adapter._start_telemetry_export_task()
            assert task is not None
            adapter.state.telemetry_export_task = task
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        snapshot = adapter.status_snapshot()
        telemetry_probe = snapshot["workerProbe"]["jobs"]["telemetryExports"]
        worker_probe = snapshot["workerProbe"]

        self.assertEqual(telemetry_probe["state"], "succeeded")
        self.assertEqual(telemetry_probe["backlogCount"], 7)
        self.assertEqual(telemetry_probe["checkpointAt"], "2026-04-15T12:00:00Z")
        self.assertEqual(telemetry_probe["details"]["queueDepth"], 7)
        self.assertEqual(telemetry_probe["details"]["eventsPushed24h"], 19)
        self.assertTrue(worker_probe["watcherDisabled"])
        self.assertTrue(worker_probe["backpressure"]["hasBackpressure"])
        self.assertEqual(worker_probe["backpressure"]["jobsWithBacklog"], ["telemetryExports"])
        self.assertEqual(worker_probe["backpressure"]["totalBacklogCount"], 7)
        self.assertEqual(worker_probe["backpressure"]["maxBacklogCount"], 7)
        self.assertIsNone(worker_probe["syncLagSeconds"])

    async def test_worker_probe_snapshot_preserves_disabled_telemetry_markers(self):
        project = _make_project()
        telemetry_job = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    success=False,
                    outcome="not_configured",
                    batch_size=0,
                    duration_ms=7,
                )
            ),
            coordinator=SimpleNamespace(
                status=AsyncMock(
                    return_value=SimpleNamespace(
                        queueStats=SimpleNamespace(pending=0),
                        lastPushTimestamp=None,
                        eventsPushed24h=0,
                        configured=False,
                        envLocked=True,
                        persistedEnabled=False,
                    )
                )
            ),
        )
        adapter = _make_adapter(project, telemetry_exporter_job=telemetry_job)

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 0
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 1

            task = adapter._start_telemetry_export_task()
            assert task is not None
            adapter.state.telemetry_export_task = task
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        snapshot = adapter.status_snapshot()
        telemetry_probe = snapshot["workerProbe"]["jobs"]["telemetryExports"]

        self.assertEqual(telemetry_probe["state"], "succeeded")
        self.assertEqual(telemetry_probe["lastOutcome"], "not_configured")
        self.assertEqual(telemetry_probe["details"]["queueDepth"], 0)
        self.assertFalse(telemetry_probe["details"]["configured"])
        self.assertTrue(telemetry_probe["details"]["envLocked"])
        self.assertFalse(telemetry_probe["details"]["persistedEnabled"])


class TestWorkerProbeApp(unittest.TestCase):
    def test_detail_route_embeds_worker_probe_extension(self):
        container = MagicMock()
        container.runtime_status.return_value = {
            "profile": "worker",
            "probeContract": {
                "schemaVersion": "ops-201-v1",
                "runtimeProfile": "worker",
                "live": {"state": "live", "status": "pass"},
                "ready": {"state": "degraded", "status": "warn", "ready": True},
                "detail": {"state": "degraded", "status": "warn", "activities": {"jobsEnabled": True}},
            },
            "workerProbe": {
                "schemaVersion": "ops-203-v1",
                "jobs": {"telemetryExports": {"backlogCount": 4}},
                "summary": {"backlogCounts": {"telemetryExports": 4}},
            },
        }

        client = TestClient(build_worker_probe_app(container))
        response = client.get("/detailz")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schemaVersion"], "ops-201-v1")
        self.assertEqual(payload["detail"]["worker"]["schemaVersion"], "ops-203-v1")
        self.assertEqual(payload["detail"]["worker"]["summary"]["backlogCounts"]["telemetryExports"], 4)

    def test_ready_route_returns_503_when_worker_is_not_ready(self):
        container = MagicMock()
        container.runtime_status.return_value = {
            "profile": "worker",
            "probeContract": {
                "schemaVersion": "ops-201-v1",
                "runtimeProfile": "worker",
                "live": {"state": "live", "status": "pass"},
                "ready": {"state": "not_ready", "status": "fail", "ready": False, "reasons": []},
                "detail": {"state": "not_ready", "status": "fail"},
            },
            "workerProbe": {"schemaVersion": "ops-203-v1", "jobs": {}, "summary": {}},
        }

        client = TestClient(build_worker_probe_app(container))
        response = client.get("/readyz")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ready"]["ready"])

    def test_detail_route_surfaces_stale_worker_probe_backlog_and_freshness(self):
        project = _make_project()
        adapter = _make_adapter(project)
        startup_observation = adapter.state.job_observations["startupSync"]
        startup_observation.state = "succeeded"
        startup_observation.interval_seconds = 300
        startup_observation.backlog_count = 0
        startup_observation.checkpoint_at = "2026-04-15T11:45:00Z"
        startup_observation.last_success_at = "2026-04-15T11:45:00Z"
        telemetry_observation = adapter.state.job_observations["telemetryExports"]
        telemetry_observation.state = "failed"
        telemetry_observation.interval_seconds = 60
        telemetry_observation.backlog_count = 9
        telemetry_observation.checkpoint_at = "2026-04-15T10:00:00Z"
        telemetry_observation.last_success_at = "2026-04-15T09:30:00Z"
        telemetry_observation.last_failure_at = "2026-04-15T11:55:00Z"
        telemetry_observation.last_outcome = "not_configured"
        telemetry_observation.last_error = "telemetry_export_failed"
        telemetry_observation.details.update(
            {
                "queueDepth": 9,
                "configured": False,
                "envLocked": True,
                "persistedEnabled": False,
            }
        )

        with patch(
            "backend.adapters.jobs.runtime._utc_now",
            return_value=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
        ):
            worker_probe = adapter.status_snapshot()["workerProbe"]

        container = MagicMock()
        container.runtime_status.return_value = {
            "profile": "worker",
            "probeContract": {
                "schemaVersion": "ops-201-v1",
                "runtimeProfile": "worker",
                "live": {"state": "live", "status": "pass"},
                "ready": {"state": "degraded", "status": "warn", "ready": True, "reasons": []},
                "detail": {"state": "degraded", "status": "warn", "activities": {"jobsEnabled": True}},
            },
            "workerProbe": worker_probe,
        }

        client = TestClient(build_worker_probe_app(container))
        response = client.get("/detailz")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        worker_probe = payload["detail"]["worker"]
        telemetry_probe = worker_probe["jobs"]["telemetryExports"]
        self.assertEqual(telemetry_probe["state"], "failed")
        self.assertEqual(telemetry_probe["backlogCount"], 9)
        self.assertEqual(telemetry_probe["checkpointFreshnessSeconds"], 7200)
        self.assertEqual(telemetry_probe["lastSuccessFreshnessSeconds"], 9000)
        self.assertEqual(telemetry_probe["lastOutcome"], "not_configured")
        self.assertFalse(telemetry_probe["details"]["configured"])
        self.assertTrue(telemetry_probe["details"]["envLocked"])
        self.assertTrue(worker_probe["watcherDisabled"])
        self.assertEqual(worker_probe["syncLagSeconds"], 900)
        self.assertTrue(worker_probe["backpressure"]["hasBackpressure"])
        self.assertEqual(worker_probe["backpressure"]["jobsWithBacklog"], ["telemetryExports"])
        self.assertEqual(worker_probe["backpressure"]["totalBacklogCount"], 9)
        self.assertEqual(worker_probe["backpressure"]["maxBacklogCount"], 9)
        self.assertEqual(worker_probe["summary"]["backlogCounts"]["telemetryExports"], 9)
        self.assertEqual(worker_probe["summary"]["maxCheckpointFreshnessSeconds"], 7200)


# ---------------------------------------------------------------------------
# TEST-004-C2: warming task must not block concurrent coroutines (criterion 2)
# ---------------------------------------------------------------------------

class TestCacheWarmingNonBlocking(unittest.IsolatedAsyncioTestCase):
    """The warming loop must not starve the event loop between iterations.

    We run the warming task alongside a lightweight probe coroutine that
    increments a counter during the same interval.  If the warming loop were
    blocking (e.g. calling time.sleep instead of asyncio.sleep) the probe
    would not advance.
    """

    async def test_warming_does_not_starve_concurrent_coroutines(self):
        project = _make_project()
        adapter = _make_adapter(project)

        # Probe: a tight async loop counting how many times it gets the event
        # loop back during the test window.
        probe_ticks: list[int] = [0]

        async def _probe() -> None:
            while True:
                await asyncio.sleep(0)  # yield to event loop
                probe_ticks[0] += 1

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
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 1
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            warming_task = adapter._start_cache_warming_task()
            assert warming_task is not None
            probe_task = asyncio.ensure_future(_probe())

            # Run for slightly more than one interval
            await asyncio.sleep(1.3)

            probe_task.cancel()
            warming_task.cancel()
            for t in (probe_task, warming_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        # The probe should have received the event loop many times; a blocking
        # warming loop would leave probe_ticks[0] at 0 or 1.
        self.assertGreater(
            probe_ticks[0],
            5,
            f"Probe only ticked {probe_ticks[0]} times — warming may be blocking the event loop",
        )


# ---------------------------------------------------------------------------
# TEST-004-C5: cache entries present after the memoized_query decorator runs
# ---------------------------------------------------------------------------

class TestCacheWarmAfterRun(unittest.IsolatedAsyncioTestCase):
    """Criterion 5: the module-level TTLCache must contain entries after a
    ``@memoized_query``-decorated service method executes with a valid
    fingerprint.

    The warming job calls the *decorated* ``get_status`` / ``get_diagnostics``
    methods.  If those decorated calls succeed and the decorator receives a
    non-None fingerprint it writes the result to ``_query_cache``.  This test
    verifies that end-to-end path by:

    1. Calling a ``@memoized_query``-decorated function directly with a
       fingerprint-returning stub (no real DB needed).
    2. Asserting ``_query_cache`` is non-empty afterwards.

    A companion sub-test verifies that the warming job calls the services
    (and therefore exercises the decorated path) at least once per interval,
    ensuring the two halves of criterion 5 are both covered.
    """

    async def test_memoized_query_decorator_populates_cache(self):
        """The @memoized_query decorator must write to _query_cache on a cache miss."""
        from backend.application.services.agent_queries.cache import (
            clear_cache,
            get_cache,
            memoized_query,
        )
        import backend.application.services.agent_queries.cache as _cache_mod

        clear_cache()

        sentinel = object()

        # Build a minimal decorated function inline so the test does not depend
        # on the real service implementations.
        @memoized_query("test_endpoint_c5")
        async def _fake_service(context, ports):
            return sentinel

        # Stub out the fingerprint so the decorator sees a valid, stable token.
        with patch.object(
            _cache_mod,
            "get_data_version_fingerprint",
            AsyncMock(return_value="stable-fp-c5"),
        ), patch.object(_cache_mod, "config") as cfg_mock:
            cfg_mock.CCDASH_QUERY_CACHE_TTL_SECONDS = 60

            fake_context = MagicMock()
            fake_context.project.project_id = "proj-c5"
            fake_ports = MagicMock()

            result = await _fake_service(fake_context, fake_ports)

        self.assertIs(result, sentinel, "decorated function must return the underlying result")

        cache = get_cache()
        self.assertGreater(
            len(cache),
            0,
            "TTLCache must contain at least one entry after a decorated call with a valid fingerprint",
        )

        clear_cache()

    async def test_warming_job_invokes_services_enabling_cache_population(self):
        """The warming task must invoke both services at least once per interval,
        which is the necessary condition for cache population (C5 integration half)."""
        project = _make_project()
        adapter = _make_adapter(project)

        call_log: list[str] = []

        async def _record_status(self, context, ports):
            call_log.append("status")
            return MagicMock()

        async def _record_workflow(self, context, ports):
            call_log.append("workflow")
            return MagicMock()

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg, \
             patch(
                 "backend.application.services.agent_queries.project_status.ProjectStatusQueryService.get_status",
                 _record_status,
             ), \
             patch(
                 "backend.application.services.agent_queries.workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics",
                 _record_workflow,
             ):
            mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 1
            mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
            mock_cfg.CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = 0

            task = adapter._start_cache_warming_task()
            assert task is not None

            await asyncio.sleep(1.4)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.assertIn("status", call_log, "project_status must be called by the warming job")
        self.assertIn("workflow", call_log, "workflow_diagnostics must be called by the warming job")


if __name__ == "__main__":
    unittest.main()
