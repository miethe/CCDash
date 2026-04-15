"""Runtime-managed background job orchestration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import config
from backend.application.ports import CorePorts
from backend.application.ports.core import ProjectBinding
from backend.db.file_watcher import file_watcher
from backend.runtime.profiles import RuntimeProfile
from backend.adapters.jobs.telemetry_exporter import TelemetryExporterJob
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache, skillmeat_refresh_configured
from backend.services.test_config import effective_test_flags, resolve_test_sources

logger = logging.getLogger("ccdash.runtime.jobs")


@dataclass(slots=True)
class RuntimeJobState:
    sync_task: asyncio.Task[None] | None = None
    analytics_snapshot_task: asyncio.Task[None] | None = None
    telemetry_export_task: asyncio.Task[None] | None = None
    cache_warming_task: asyncio.Task[None] | None = None
    watcher_started: bool = False


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
    ) -> None:
        self.profile = profile
        self.ports = ports
        self.sync = sync_engine
        self.project_binding = project_binding
        self.telemetry_exporter_job = telemetry_exporter_job
        self.state = RuntimeJobState()

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
            self.state.sync_task = self.ports.job_scheduler.schedule(
                self._run_startup_sync_pipeline(
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

    def status_snapshot(self) -> dict[str, str | bool]:
        return {
            "watcher": "running" if self.state.watcher_started else "stopped",
            "startupSync": "running" if self.state.sync_task is not None and not self.state.sync_task.done() else "idle",
            "analyticsSnapshots": "running"
            if self.state.analytics_snapshot_task is not None and not self.state.analytics_snapshot_task.done()
            else "idle",
            "telemetryExports": "running"
            if self.state.telemetry_export_task is not None and not self.state.telemetry_export_task.done()
            else "idle",
            "cacheWarming": "running"
            if self.state.cache_warming_task is not None and not self.state.cache_warming_task.done()
            else "idle",
            "jobsEnabled": self.profile.capabilities.jobs,
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
        await self.sync.sync_project(
            active_project,
            sessions_dir,
            docs_dir,
            progress_dir,
            trigger="startup",
            rebuild_links=not light_mode,
            capture_analytics=not light_mode,
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
        workspace_registry = self.ports.workspace_registry
        bound_project = self.project_binding.project if self.project_binding is not None else None

        async def _run_periodic_analytics_snapshots() -> None:
            while True:
                await asyncio.sleep(analytics_interval)
                current_project = bound_project or workspace_registry.get_active_project()
                if not current_project:
                    continue
                try:
                    await self.sync.capture_analytics_snapshot(
                        current_project.id,
                        trigger="periodic_timer",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
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

                context = RequestContext(
                    principal=_warming_principal,
                    workspace=None,
                    project=project_scope,
                    runtime_profile="worker",
                    trace=_warming_trace,
                    tenancy=TenancyContext(project_id=current_project.id),
                )

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
                    raise
                except Exception:
                    logger.exception(
                        "Cache warming: workflow_diagnostics failed for project '%s'",
                        current_project.id,
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

        async def _run_periodic_telemetry_exports() -> None:
            while True:
                try:
                    await self.telemetry_exporter_job.execute()
                except asyncio.CancelledError:
                    raise
                except Exception:
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
