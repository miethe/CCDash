"""Runtime-managed background job orchestration."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend import config
from backend.application.ports import CorePorts
from backend.application.ports.core import ProjectBinding
from backend.db.file_watcher import file_watcher
from backend.observability import otel as observability
from backend.runtime.profiles import RuntimeProfile
from backend.adapters.jobs.artifact_rollup_export_job import ArtifactRollupExportJob
from backend.adapters.jobs.telemetry_exporter import TelemetryExporterJob
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache, skillmeat_refresh_configured
from backend.services.test_config import effective_test_flags, resolve_test_sources

logger = logging.getLogger("ccdash.runtime.jobs")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _freshness_seconds(value: object) -> int | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0, int((_utc_now() - parsed).total_seconds()))


@dataclass(slots=True)
class RuntimeJobObservation:
    state: str = "idle"
    interval_seconds: int | None = None
    backlog_count: int | None = None
    backlog_unit: str | None = None
    checkpoint_at: str | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_outcome: str | None = None
    last_duration_ms: int | None = None
    last_error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeJobState:
    sync_task: asyncio.Task[None] | None = None
    analytics_snapshot_task: asyncio.Task[None] | None = None
    telemetry_export_task: asyncio.Task[None] | None = None
    artifact_rollup_export_task: asyncio.Task[None] | None = None
    cache_warming_task: asyncio.Task[None] | None = None
    watcher_started: bool = False
    job_observations: dict[str, RuntimeJobObservation] = field(default_factory=dict)


class RuntimeJobAdapter:
    """Owns runtime-specific background work behind a dedicated adapter boundary."""

    def __init__(
        self,
        *,
        profile: RuntimeProfile,
        ports: CorePorts,
        sync_engine: Any | None,
        project_binding: ProjectBinding | None = None,
        telemetry_exporter_job: TelemetryExporterJob | None = None,
        artifact_rollup_export_job: ArtifactRollupExportJob | None = None,
    ) -> None:
        self.profile = profile
        self.ports = ports
        self.sync = sync_engine
        self.project_binding = project_binding
        self.telemetry_exporter_job = telemetry_exporter_job
        self.artifact_rollup_export_job = artifact_rollup_export_job
        self.state = RuntimeJobState()
        self.state.job_observations.update(
            {
                "startupSync": RuntimeJobObservation(backlog_count=0, backlog_unit="runs"),
                "analyticsSnapshots": RuntimeJobObservation(backlog_count=0, backlog_unit="runs"),
                "telemetryExports": RuntimeJobObservation(backlog_count=0, backlog_unit="events"),
                "artifactRollupExports": RuntimeJobObservation(backlog_count=0, backlog_unit="rollups"),
                "cacheWarming": RuntimeJobObservation(backlog_count=0, backlog_unit="runs"),
            }
        )

    async def start(self) -> RuntimeJobState:
        workspace_registry = self.ports.workspace_registry
        resolved_binding = self.project_binding
        if resolved_binding is None and (
            self.profile.capabilities.sync
            or self.profile.capabilities.watch
            or self.profile.capabilities.jobs
        ):
            resolved_binding = workspace_registry.resolve_project_binding()

        active_project = resolved_binding.project if resolved_binding is not None else None
        active_bundle = resolved_binding.paths if resolved_binding is not None else None
        sessions_dir, docs_dir, progress_dir = active_bundle.as_tuple() if active_bundle is not None else (
            config.SESSIONS_DIR,
            config.DOCUMENTS_DIR,
            config.PROGRESS_DIR,
        )
        test_sources = (
            resolve_test_sources(active_project, project_root=active_bundle.root.path)
            if active_project and active_bundle is not None
            else []
        )
        flags = effective_test_flags(active_project)
        test_results_dir: Path | None = test_sources[0].resolved_dir if test_sources else None

        if active_project and self.profile.capabilities.sync and self.sync is not None:
            if bool(getattr(config, "STARTUP_SYNC_ENABLED", True)):
                self.state.sync_task = self.ports.job_scheduler.schedule(
                    self._run_startup_sync_job(
                        active_project=active_project,
                        sessions_dir=sessions_dir,
                        docs_dir=docs_dir,
                        progress_dir=progress_dir,
                        test_sources=test_sources,
                        test_results_dir=test_results_dir,
                        test_flags=flags,
                    ),
                    name=f"ccdash:{self.profile.name}:startup-sync",
                )
            else:
                observation = self.state.job_observations["startupSync"]
                observation.state = "disabled"
                observation.last_outcome = "disabled"
                observation.backlog_count = 0
                observation.details.update(
                    {
                        "projectId": str(getattr(active_project, "id", "") or ""),
                        "projectName": str(getattr(active_project, "name", "") or ""),
                        "disabledBy": "CCDASH_STARTUP_SYNC_ENABLED=false",
                    }
                )

        if active_project and self.profile.capabilities.watch and self.sync is not None:
            await file_watcher.start(
                self.sync,
                active_project.id,
                sessions_dir,
                docs_dir,
                progress_dir,
                test_results_dir=test_results_dir,
                test_sources=test_sources,
            )
            self.state.watcher_started = True

        if self.profile.capabilities.jobs:
            analytics_task = self._start_analytics_snapshot_task()
            if analytics_task is not None:
                self.state.analytics_snapshot_task = analytics_task
            telemetry_task = self._start_telemetry_export_task()
            if telemetry_task is not None:
                self.state.telemetry_export_task = telemetry_task
            artifact_rollup_task = self._start_artifact_rollup_export_task()
            if artifact_rollup_task is not None:
                self.state.artifact_rollup_export_task = artifact_rollup_task
            cache_warming_task = self._start_cache_warming_task()
            if cache_warming_task is not None:
                self.state.cache_warming_task = cache_warming_task

        return self.state

    async def stop(self) -> None:
        if self.state.sync_task is not None:
            self.state.sync_task.cancel()
            try:
                await self.state.sync_task
            except asyncio.CancelledError:
                pass
            self.state.sync_task = None

        if self.state.analytics_snapshot_task is not None:
            self.state.analytics_snapshot_task.cancel()
            try:
                await self.state.analytics_snapshot_task
            except asyncio.CancelledError:
                pass
            self.state.analytics_snapshot_task = None

        if self.state.telemetry_export_task is not None:
            self.state.telemetry_export_task.cancel()
            try:
                await self.state.telemetry_export_task
            except asyncio.CancelledError:
                pass
            self.state.telemetry_export_task = None

        if self.state.artifact_rollup_export_task is not None:
            self.state.artifact_rollup_export_task.cancel()
            try:
                await self.state.artifact_rollup_export_task
            except asyncio.CancelledError:
                pass
            self.state.artifact_rollup_export_task = None

        if self.state.cache_warming_task is not None:
            self.state.cache_warming_task.cancel()
            try:
                await self.state.cache_warming_task
            except asyncio.CancelledError:
                pass
            self.state.cache_warming_task = None

        if self.state.watcher_started:
            await file_watcher.stop()
            self.state.watcher_started = False

    def status_snapshot(self) -> dict[str, Any]:
        watcher_detail = self._watcher_probe_detail()
        snapshot: dict[str, Any] = {
            "watcher": watcher_detail["state"],
            "watcherDetail": watcher_detail,
            "startupSyncEnabled": bool(getattr(config, "STARTUP_SYNC_ENABLED", True)),
            "startupSync": "running" if self.state.sync_task is not None and not self.state.sync_task.done() else "idle",
            "analyticsSnapshots": "running"
            if self.state.analytics_snapshot_task is not None and not self.state.analytics_snapshot_task.done()
            else "idle",
            "telemetryExports": "running"
            if self.state.telemetry_export_task is not None and not self.state.telemetry_export_task.done()
            else "idle",
            "artifactRollupExports": "running"
            if self.state.artifact_rollup_export_task is not None and not self.state.artifact_rollup_export_task.done()
            else "idle",
            "cacheWarming": "running"
            if self.state.cache_warming_task is not None and not self.state.cache_warming_task.done()
            else "idle",
            "jobsEnabled": self.profile.capabilities.jobs,
        }
        if self.state.sync_task is None:
            snapshot["startupSync"] = self.state.job_observations["startupSync"].state
        if self.profile.name in {"worker", "worker-watch"}:
            worker_jobs = self._worker_probe_jobs()
            worker_summary = self._worker_probe_summary(worker_jobs)
            snapshot["workerProbe"] = {
                "schemaVersion": "ops-203-v1",
                "watcherDisabled": not self.profile.capabilities.watch,
                "watcher": watcher_detail,
                "syncLagSeconds": self._worker_probe_sync_lag_seconds(worker_jobs),
                "backpressure": self._worker_probe_backpressure(worker_jobs),
                "jobs": worker_jobs,
                "summary": worker_summary,
            }
        return snapshot

    def _watcher_probe_detail(self) -> dict[str, Any]:
        if not self.profile.capabilities.watch:
            return {
                "state": "not_expected",
                "expected": False,
                "enabled": False,
                "configured": False,
                "running": False,
                "watchPathCount": 0,
                "watchPaths": [],
                "lastChangeSyncAt": None,
                "lastChangeCount": None,
                "lastSyncStatus": None,
                "lastSyncError": None,
            }

        watcher_snapshot = file_watcher.snapshot()
        configured = bool(watcher_snapshot.get("configured", False))
        running = bool(watcher_snapshot.get("running", False)) or (self.state.watcher_started and not configured)
        watch_path_count = int(watcher_snapshot.get("watchPathCount", 0) or 0)
        if running:
            state = "running"
        elif configured and watch_path_count == 0:
            state = "configured_no_paths"
        elif configured:
            state = "stopped"
        else:
            state = "not_configured"

        return {
            "state": state,
            "expected": True,
            "enabled": True,
            "configured": configured,
            "running": running,
            "watchPathCount": watch_path_count,
            "watchPaths": list(watcher_snapshot.get("watchPaths") or []),
            "lastChangeSyncAt": watcher_snapshot.get("lastChangeSyncAt"),
            "lastChangeCount": watcher_snapshot.get("lastChangeCount"),
            "lastSyncStatus": watcher_snapshot.get("lastSyncStatus"),
            "lastSyncError": watcher_snapshot.get("lastSyncError"),
        }

    async def _run_startup_sync_job(
        self,
        *,
        active_project: Any,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        test_sources: list[Any],
        test_results_dir: Path | None,
        test_flags: Any,
    ) -> None:
        started = self._mark_job_started("startupSync", backlog_count=1)
        try:
            await self._run_startup_sync_pipeline(
                active_project=active_project,
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
                test_sources=test_sources,
                test_results_dir=test_results_dir,
                test_flags=test_flags,
            )
        except asyncio.CancelledError:
            self._mark_job_cancelled("startupSync", started, backlog_count=0)
            raise
        except Exception as exc:
            self._mark_job_failure("startupSync", started, exc, backlog_count=0)
            raise
        else:
            self._mark_job_success(
                "startupSync",
                started,
                backlog_count=0,
                details={
                    "projectId": str(getattr(active_project, "id", "") or ""),
                    "projectName": str(getattr(active_project, "name", "") or ""),
                },
            )

    def _mark_job_started(self, job_name: str, *, backlog_count: int | None = None) -> float:
        observation = self.state.job_observations[job_name]
        observation.state = "running"
        observation.last_started_at = _isoformat(_utc_now())
        observation.last_error = None
        observation.last_outcome = "running"
        if backlog_count is not None:
            observation.backlog_count = max(0, int(backlog_count))
        self._record_worker_job_metrics(job_name)
        return time.monotonic()

    def _mark_job_success(
        self,
        job_name: str,
        started: float,
        *,
        outcome: str = "success",
        backlog_count: int | None = None,
        checkpoint_at: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        observation = self.state.job_observations[job_name]
        finished_at = _isoformat(_utc_now())
        observation.state = "succeeded"
        observation.last_finished_at = finished_at
        observation.last_success_at = finished_at
        observation.last_outcome = outcome
        observation.last_duration_ms = int((time.monotonic() - started) * 1000)
        observation.last_error = None
        if backlog_count is not None:
            observation.backlog_count = max(0, int(backlog_count))
        observation.checkpoint_at = checkpoint_at or observation.last_success_at
        if details:
            observation.details.update(details)
        self._record_worker_job_metrics(job_name)

    def _mark_job_failure(
        self,
        job_name: str,
        started: float,
        exc: Exception,
        *,
        outcome: str = "failed",
        backlog_count: int | None = None,
        checkpoint_at: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        observation = self.state.job_observations[job_name]
        finished_at = _isoformat(_utc_now())
        observation.state = "failed"
        observation.last_finished_at = finished_at
        observation.last_failure_at = finished_at
        observation.last_outcome = outcome
        observation.last_duration_ms = int((time.monotonic() - started) * 1000)
        observation.last_error = str(exc) or exc.__class__.__name__
        if backlog_count is not None:
            observation.backlog_count = max(0, int(backlog_count))
        if checkpoint_at is not None:
            observation.checkpoint_at = checkpoint_at
        if details:
            observation.details.update(details)
        self._record_worker_job_metrics(job_name)

    def _mark_job_cancelled(self, job_name: str, started: float, *, backlog_count: int | None = None) -> None:
        observation = self.state.job_observations[job_name]
        observation.last_finished_at = _isoformat(_utc_now())
        observation.last_outcome = "cancelled"
        observation.last_duration_ms = int((time.monotonic() - started) * 1000)
        if observation.last_success_at is not None:
            observation.state = "succeeded"
        elif observation.last_failure_at is not None:
            observation.state = "failed"
        else:
            observation.state = "idle"
        if backlog_count is not None:
            observation.backlog_count = max(0, int(backlog_count))
        self._record_worker_job_metrics(job_name)

    def _snapshot_job_state(self, job_name: str, task: asyncio.Task[None] | None) -> str:
        if task is not None and not task.done():
            return "running"
        return self.state.job_observations[job_name].state

    def _worker_probe_jobs(self) -> dict[str, Any]:
        tasks = {
            "startupSync": self.state.sync_task,
            "analyticsSnapshots": self.state.analytics_snapshot_task,
            "telemetryExports": self.state.telemetry_export_task,
            "artifactRollupExports": self.state.artifact_rollup_export_task,
            "cacheWarming": self.state.cache_warming_task,
        }
        jobs: dict[str, Any] = {}
        for job_name, observation in self.state.job_observations.items():
            checkpoint_at = observation.checkpoint_at or observation.last_success_at
            jobs[job_name] = {
                "state": self._snapshot_job_state(job_name, tasks.get(job_name)),
                "intervalSeconds": observation.interval_seconds,
                "backlogCount": observation.backlog_count,
                "backlogUnit": observation.backlog_unit,
                "checkpointAt": checkpoint_at,
                "checkpointFreshnessSeconds": _freshness_seconds(checkpoint_at),
                "lastStartedAt": observation.last_started_at,
                "lastFinishedAt": observation.last_finished_at,
                "lastSuccessAt": observation.last_success_at,
                "lastSuccessFreshnessSeconds": _freshness_seconds(observation.last_success_at),
                "lastFailureAt": observation.last_failure_at,
                "lastOutcome": observation.last_outcome,
                "lastDurationMs": observation.last_duration_ms,
                "lastError": observation.last_error,
                "details": dict(observation.details),
            }
        return jobs

    def _worker_probe_summary(self, jobs: dict[str, Any]) -> dict[str, Any]:
        active_jobs = [name for name, payload in jobs.items() if payload.get("state") == "running"]
        backlog = {
            name: int(payload["backlogCount"])
            for name, payload in jobs.items()
            if isinstance(payload.get("backlogCount"), int)
        }
        freshness_values = [
            int(value)
            for value in (payload.get("checkpointFreshnessSeconds") for payload in jobs.values())
            if isinstance(value, int)
        ]
        last_success_markers = {
            name: payload.get("lastSuccessAt")
            for name, payload in jobs.items()
            if payload.get("lastSuccessAt")
        }
        return {
            "activeJobs": active_jobs,
            "backlogCounts": backlog,
            "lastSuccessMarkers": last_success_markers,
            "maxCheckpointFreshnessSeconds": max(freshness_values) if freshness_values else None,
        }

    def _worker_probe_sync_lag_seconds(self, jobs: dict[str, Any]) -> int | None:
        startup_sync = jobs.get("startupSync", {})
        lag_seconds = startup_sync.get("checkpointFreshnessSeconds")
        return int(lag_seconds) if isinstance(lag_seconds, int) else None

    def _worker_probe_backpressure(self, jobs: dict[str, Any]) -> dict[str, Any]:
        backlog_counts = {
            name: int(payload["backlogCount"])
            for name, payload in jobs.items()
            if isinstance(payload.get("backlogCount"), int)
        }
        congested_jobs = [name for name, backlog_count in backlog_counts.items() if backlog_count > 0]
        return {
            "hasBackpressure": bool(congested_jobs),
            "jobsWithBacklog": congested_jobs,
            "totalBacklogCount": sum(backlog_counts.values()),
            "maxBacklogCount": max(backlog_counts.values()) if backlog_counts else 0,
        }

    def _record_worker_job_metrics(self, job_name: str) -> None:
        if self.profile.name != "worker":
            return
        observation = self.state.job_observations[job_name]
        project_id = self._worker_metric_project_id(observation)
        if project_id is None:
            return

        checkpoint_at = observation.checkpoint_at or observation.last_success_at
        freshness_seconds = _freshness_seconds(checkpoint_at)
        freshness_ms = float(freshness_seconds * 1000) if isinstance(freshness_seconds, int) else None

        backlog_count = observation.backlog_count
        backpressure_ratio = None
        if isinstance(backlog_count, int):
            backpressure_ratio = 1.0 if backlog_count > 0 else 0.0

        runtime_metadata = self._worker_metric_runtime_metadata()
        observability.set_worker_job_freshness(
            job_name=job_name,
            project_id=project_id,
            freshness_ms=freshness_ms,
            runtime_metadata=runtime_metadata,
        )
        observability.set_worker_job_backpressure(
            job_name=job_name,
            project_id=project_id,
            backpressure_ratio=backpressure_ratio,
            runtime_metadata=runtime_metadata,
        )

    def _worker_metric_project_id(self, observation: RuntimeJobObservation) -> str | None:
        details_project_id = observation.details.get("projectId")
        if details_project_id:
            return str(details_project_id)
        if self.project_binding is not None and getattr(self.project_binding.project, "id", None):
            return str(self.project_binding.project.id)
        workspace_registry = getattr(self.ports, "workspace_registry", None)
        if workspace_registry is None:
            return None
        active_project = workspace_registry.get_active_project()
        if active_project is None or not getattr(active_project, "id", None):
            return None
        return str(active_project.id)

    def _worker_metric_runtime_metadata(self) -> dict[str, object]:
        environment_contract = config.resolve_runtime_environment_contract(
            self.profile.name,
            config.STORAGE_PROFILE,
        )
        return {
            "runtimeProfile": self.profile.name,
            "deploymentMode": environment_contract.deployment_mode,
            "storageProfile": config.STORAGE_PROFILE.profile,
        }

    async def _run_startup_sync_pipeline(
        self,
        *,
        active_project: Any,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        test_sources: list[Any],
        test_results_dir: Path | None,
        test_flags: Any,
    ) -> None:
        delay = max(0, int(getattr(config, "STARTUP_SYNC_DELAY_SECONDS", 0)))
        if delay > 0:
            await asyncio.sleep(delay)

        light_mode = bool(getattr(config, "STARTUP_SYNC_LIGHT_MODE", True))
        if light_mode and hasattr(self.sync, "sync_planning_artifacts"):
            planning_stats = await self.sync.sync_planning_artifacts(
                active_project.id,
                docs_dir,
                progress_dir,
                force=False,
            )
            logger.info("Startup planning artifact sync stats: %s", planning_stats)
        await self.sync.sync_project(
            active_project,
            sessions_dir,
            docs_dir,
            progress_dir,
            trigger="startup",
            rebuild_links=not light_mode,
            capture_analytics=not light_mode,
            backfill_session_intelligence=not light_mode,
        )

        if test_flags.testVisualizerEnabled and active_project.testConfig.autoSyncOnStartup:
            test_stats = await self.sync.sync_test_sources(
                active_project.id,
                test_sources,
                max_files_per_scan=active_project.testConfig.maxFilesPerScan,
                max_parse_concurrency=active_project.testConfig.maxParseConcurrency,
            )
            logger.info("Startup test result sync stats: %s", test_stats)

        if self.profile.capabilities.integrations and skillmeat_refresh_configured(active_project):
            refresh_payload = await refresh_skillmeat_cache(
                self.ports.storage.db,
                active_project,
                force_observation_recompute=True,
            )
            sync_payload = refresh_payload.get("sync", {}) if isinstance(refresh_payload, dict) else {}
            backfill_payload = refresh_payload.get("backfill", {}) if isinstance(refresh_payload, dict) else {}
            logger.info(
                "Startup SkillMeat refresh complete: definitions=%s observations=%s",
                sync_payload.get("totalDefinitions", 0) if isinstance(sync_payload, dict) else 0,
                backfill_payload.get("observationsStored", 0) if isinstance(backfill_payload, dict) else 0,
            )

        if light_mode and bool(getattr(config, "STARTUP_DEFERRED_REBUILD_LINKS", True)):
            stagger = max(0, int(getattr(config, "STARTUP_DEFERRED_REBUILD_DELAY_SECONDS", 0)))
            if stagger > 0:
                await asyncio.sleep(stagger)
            await self.sync.rebuild_links(
                active_project.id,
                docs_dir,
                progress_dir,
                trigger="startup_deferred",
                capture_analytics=bool(getattr(config, "STARTUP_DEFERRED_CAPTURE_ANALYTICS", False)),
            )

    def _start_analytics_snapshot_task(self) -> asyncio.Task[None] | None:
        if self.sync is None:
            return None
        analytics_interval = max(0, int(getattr(config, "ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0)))
        if analytics_interval <= 0:
            return None
        self.state.job_observations["analyticsSnapshots"].interval_seconds = analytics_interval
        workspace_registry = self.ports.workspace_registry
        bound_project = self.project_binding.project if self.project_binding is not None else None

        async def _run_periodic_analytics_snapshots() -> None:
            while True:
                await asyncio.sleep(analytics_interval)
                current_project = bound_project or workspace_registry.get_active_project()
                if not current_project:
                    continue
                started = self._mark_job_started("analyticsSnapshots", backlog_count=1)
                try:
                    await self.sync.capture_analytics_snapshot(
                        current_project.id,
                        trigger="periodic_timer",
                    )
                    self._mark_job_success(
                        "analyticsSnapshots",
                        started,
                        backlog_count=0,
                        details={"projectId": current_project.id, "trigger": "periodic_timer"},
                    )
                except asyncio.CancelledError:
                    self._mark_job_cancelled("analyticsSnapshots", started, backlog_count=0)
                    raise
                except Exception:
                    self._mark_job_failure(
                        "analyticsSnapshots",
                        started,
                        RuntimeError(f"analytics_snapshot_failed:{current_project.id}"),
                        backlog_count=0,
                        details={"projectId": current_project.id, "trigger": "periodic_timer"},
                    )
                    logger.exception(
                        "Periodic analytics snapshot failed for project '%s'",
                        current_project.id,
                    )

        logger.info(
            "Started periodic analytics snapshots (profile=%s interval=%ss)",
            self.profile.name,
            analytics_interval,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_analytics_snapshots(),
            name=f"ccdash:{self.profile.name}:analytics-snapshots",
        )

    def _start_cache_warming_task(self) -> asyncio.Task[None] | None:
        """Periodically warm the two heaviest memoized query caches.

        Targets: ``ProjectStatusQueryService.get_status`` and
        ``WorkflowDiagnosticsQueryService.get_diagnostics`` — the two service
        methods decorated with ``@memoized_query`` that aggregate the most DB
        reads.  (The "feature list" mentioned in the plan is not memoized; the
        next heaviest memoized pair is project-status + workflow-diagnostics.)

        A synthetic ``RequestContext`` is constructed from the active-project
        workspace registry entry.  If no active project is found the iteration
        is skipped silently.  All service errors are caught and logged; the loop
        continues regardless.
        """
        interval_seconds = max(0, int(getattr(config, "CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS", 0)))
        if interval_seconds <= 0:
            return None
        self.state.job_observations["cacheWarming"].interval_seconds = interval_seconds

        workspace_registry = self.ports.workspace_registry
        bound_project = self.project_binding.project if self.project_binding is not None else None

        async def _run_periodic_cache_warming() -> None:
            # Import here to avoid circular-import issues at module load time.
            from backend.application.context import (  # noqa: PLC0415
                Principal,
                RequestContext,
                TraceContext,
                TenancyContext,
            )
            from backend.application.services.agent_queries.project_status import (  # noqa: PLC0415
                ProjectStatusQueryService,
            )
            from backend.application.services.agent_queries.workflow_intelligence import (  # noqa: PLC0415
                WorkflowDiagnosticsQueryService,
            )

            _project_status_svc = ProjectStatusQueryService()
            _workflow_svc = WorkflowDiagnosticsQueryService()

            _warming_principal = Principal(
                subject="cache-warmer",
                display_name="Cache Warming Job",
                auth_mode="system",
                is_authenticated=True,
            )
            _warming_trace = TraceContext(
                request_id="cache-warmer",
                correlation_id="cache-warmer",
                path="/internal/cache-warm",
                method="INTERNAL",
            )

            while True:
                await asyncio.sleep(interval_seconds)
                current_project = bound_project or workspace_registry.get_active_project()
                if not current_project:
                    logger.debug("Cache warming: no active project — skipping this iteration")
                    continue

                _, project_scope = workspace_registry.resolve_scope(current_project.id)
                if project_scope is None:
                    logger.debug(
                        "Cache warming: resolve_scope returned None for project '%s' — skipping",
                        current_project.id,
                    )
                    continue
                started = self._mark_job_started("cacheWarming", backlog_count=1)

                context = RequestContext(
                    principal=_warming_principal,
                    workspace=None,
                    project=project_scope,
                    runtime_profile="worker",
                    trace=_warming_trace,
                    tenancy=TenancyContext(project_id=current_project.id),
                )
                iteration_failed = False

                # Warm project status
                try:
                    await _project_status_svc.get_status(context, self.ports)
                    logger.debug(
                        "Cache warming: project_status warmed for project '%s'",
                        current_project.id,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    iteration_failed = True
                    logger.exception(
                        "Cache warming: project_status failed for project '%s'",
                        current_project.id,
                    )

                # Warm workflow diagnostics (no feature filter — global scope)
                try:
                    await _workflow_svc.get_diagnostics(context, self.ports)
                    logger.debug(
                        "Cache warming: workflow_diagnostics warmed for project '%s'",
                        current_project.id,
                    )
                except asyncio.CancelledError:
                    self._mark_job_cancelled("cacheWarming", started, backlog_count=0)
                    raise
                except Exception:
                    iteration_failed = True
                    logger.exception(
                        "Cache warming: workflow_diagnostics failed for project '%s'",
                        current_project.id,
                    )

                if iteration_failed:
                    self._mark_job_failure(
                        "cacheWarming",
                        started,
                        RuntimeError(f"cache_warming_failed:{current_project.id}"),
                        backlog_count=0,
                        details={
                            "projectId": current_project.id,
                            "targets": ["project_status", "workflow_diagnostics"],
                        },
                    )
                else:
                    self._mark_job_success(
                        "cacheWarming",
                        started,
                        backlog_count=0,
                        details={
                            "projectId": current_project.id,
                            "targets": ["project_status", "workflow_diagnostics"],
                        },
                    )

        logger.info(
            "Started periodic cache warming (profile=%s interval=%ss targets=project_status,workflow_diagnostics)",
            self.profile.name,
            interval_seconds,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_cache_warming(),
            name=f"ccdash:{self.profile.name}:cache-warming",
        )

    def _start_telemetry_export_task(self) -> asyncio.Task[None] | None:
        if self.profile.name != "worker" or self.telemetry_exporter_job is None:
            return None
        interval_seconds = max(60, int(getattr(config, "CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS", 0)))
        self.state.job_observations["telemetryExports"].interval_seconds = interval_seconds

        async def _run_periodic_telemetry_exports() -> None:
            while True:
                started = self._mark_job_started("telemetryExports")
                try:
                    result = await self.telemetry_exporter_job.execute()
                    status = await self.telemetry_exporter_job.coordinator.status()
                    queue_stats = getattr(status, "queueStats", None)
                    backlog_count = int(getattr(queue_stats, "pending", 0) or 0)
                    checkpoint_at = str(getattr(status, "lastPushTimestamp", "") or "") or None
                    self._mark_job_success(
                        "telemetryExports",
                        started,
                        outcome=str(getattr(result, "outcome", "success") or "success"),
                        backlog_count=backlog_count,
                        checkpoint_at=checkpoint_at,
                        details={
                            "batchSize": int(getattr(result, "batch_size", 0) or 0),
                            "durationMs": int(getattr(result, "duration_ms", 0) or 0),
                            "queueDepth": backlog_count,
                            "eventsPushed24h": int(getattr(status, "eventsPushed24h", 0) or 0),
                            "configured": bool(getattr(status, "configured", False)),
                            "envLocked": bool(getattr(status, "envLocked", False)),
                            "persistedEnabled": bool(getattr(status, "persistedEnabled", False)),
                        },
                    )
                except asyncio.CancelledError:
                    self._mark_job_cancelled("telemetryExports", started)
                    raise
                except Exception:
                    self._mark_job_failure(
                        "telemetryExports",
                        started,
                        RuntimeError("telemetry_export_failed"),
                    )
                    logger.exception("Periodic telemetry export failed")
                await asyncio.sleep(interval_seconds)

        logger.info(
            "Started periodic telemetry export job (profile=%s interval=%ss)",
            self.profile.name,
            interval_seconds,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_telemetry_exports(),
            name=f"ccdash:{self.profile.name}:telemetry-export",
        )

    def _start_artifact_rollup_export_task(self) -> asyncio.Task[None] | None:
        if self.profile.name != "worker" or self.artifact_rollup_export_job is None:
            return None
        interval_seconds = max(60, int(getattr(config, "CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS", 3600)))
        self.state.job_observations["artifactRollupExports"].interval_seconds = interval_seconds

        async def _run_periodic_artifact_rollup_exports() -> None:
            while True:
                started = self._mark_job_started("artifactRollupExports")
                try:
                    result = await self.artifact_rollup_export_job.execute()
                    self._mark_job_success(
                        "artifactRollupExports",
                        started,
                        outcome=str(getattr(result, "outcome", "success") or "success"),
                        backlog_count=int(getattr(result, "failed_count", 0) or 0),
                        details={
                            "rollupCount": int(getattr(result, "rollup_count", 0) or 0),
                            "successCount": int(getattr(result, "success_count", 0) or 0),
                            "skippedCount": int(getattr(result, "skipped_count", 0) or 0),
                            "failedCount": int(getattr(result, "failed_count", 0) or 0),
                            "projectId": self.project_binding.project.id if self.project_binding is not None else None,
                        },
                    )
                except asyncio.CancelledError:
                    self._mark_job_cancelled("artifactRollupExports", started)
                    raise
                except Exception:
                    self._mark_job_failure(
                        "artifactRollupExports",
                        started,
                        RuntimeError("artifact_rollup_export_failed"),
                    )
                    logger.exception("Periodic artifact rollup export failed")
                await asyncio.sleep(interval_seconds)

        logger.info(
            "Started periodic artifact rollup export job (profile=%s interval=%ss)",
            self.profile.name,
            interval_seconds,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_artifact_rollup_exports(),
            name=f"ccdash:{self.profile.name}:artifact-rollup-export",
        )
