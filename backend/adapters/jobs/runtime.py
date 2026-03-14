"""Runtime-managed background job orchestration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import config
from backend.application.ports import CorePorts
from backend.db.file_watcher import file_watcher
from backend.runtime.profiles import RuntimeProfile
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache, skillmeat_refresh_configured
from backend.services.test_config import effective_test_flags, resolve_test_sources

logger = logging.getLogger("ccdash.runtime.jobs")


@dataclass(slots=True)
class RuntimeJobState:
    sync_task: asyncio.Task[None] | None = None
    analytics_snapshot_task: asyncio.Task[None] | None = None
    watcher_started: bool = False


class RuntimeJobAdapter:
    """Owns runtime-specific background work behind a dedicated adapter boundary."""

    def __init__(
        self,
        *,
        profile: RuntimeProfile,
        ports: CorePorts,
        sync_engine: Any,
    ) -> None:
        self.profile = profile
        self.ports = ports
        self.sync = sync_engine
        self.state = RuntimeJobState()

    async def start(self) -> RuntimeJobState:
        workspace_registry = self.ports.workspace_registry
        active_project = workspace_registry.get_active_project()
        active_bundle = workspace_registry.get_active_path_bundle() if active_project else None
        sessions_dir, docs_dir, progress_dir = self._resolve_paths(active_bundle)
        test_sources = (
            resolve_test_sources(active_project, project_root=active_bundle.root.path)
            if active_project and active_bundle is not None
            else []
        )
        flags = effective_test_flags(active_project)
        test_results_dir: Path | None = test_sources[0].resolved_dir if test_sources else None

        if active_project and self.profile.capabilities.sync:
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

        if active_project and self.profile.capabilities.watch:
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
            "jobsEnabled": self.profile.capabilities.jobs,
        }

    def _resolve_paths(self, active_bundle: Any | None) -> tuple[Path, Path, Path]:
        if active_bundle is None:
            return (
                config.SESSIONS_DIR,
                config.DOCUMENTS_DIR,
                config.PROGRESS_DIR,
            )
        return active_bundle.as_tuple()

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
        analytics_interval = max(0, int(getattr(config, "ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0)))
        if analytics_interval <= 0:
            return None
        workspace_registry = self.ports.workspace_registry

        async def _run_periodic_analytics_snapshots() -> None:
            while True:
                await asyncio.sleep(analytics_interval)
                current_project = workspace_registry.get_active_project()
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
