"""Runtime container and lifecycle orchestration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend import config
from backend.db import connection, migrations, sync_engine
from backend.db.file_watcher import file_watcher
from backend.observability import initialize as initialize_observability, shutdown as shutdown_observability
from backend.project_manager import project_manager
from backend.runtime.profiles import RuntimeProfile
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache, skillmeat_refresh_configured
from backend.services.test_config import effective_test_flags, resolve_test_sources

logger = logging.getLogger("ccdash.runtime")


@dataclass(slots=True)
class RuntimeLifecycleState:
    sync_task: asyncio.Task[None] | None = None
    analytics_snapshot_task: asyncio.Task[None] | None = None
    watcher_started: bool = False


@dataclass(slots=True)
class RuntimeContainer:
    profile: RuntimeProfile
    db: Any | None = None
    sync: Any | None = None
    lifecycle: RuntimeLifecycleState = field(default_factory=RuntimeLifecycleState)

    async def startup(self, app: FastAPI) -> None:
        logger.info("CCDash backend starting up (profile=%s)", self.profile.name)
        app.state.runtime_profile = self.profile
        app.state.runtime_container = self

        initialize_observability(app)

        self.db = await connection.get_connection()
        await migrations.run_migrations(self.db)

        self.sync = sync_engine.SyncEngine(self.db)
        app.state.sync_engine = self.sync

        active_project = project_manager.get_active_project()
        active_bundle = project_manager.get_active_path_bundle() if active_project else None
        sessions_dir, docs_dir, progress_dir = self._resolve_paths(active_bundle)
        test_sources = (
            resolve_test_sources(active_project, project_root=active_bundle.root.path)
            if active_project and active_bundle is not None
            else []
        )
        flags = effective_test_flags(active_project)
        test_results_dir: Path | None = test_sources[0].resolved_dir if test_sources else None

        if active_project and self.profile.capabilities.sync:
            self.lifecycle.sync_task = asyncio.create_task(
                self._run_startup_sync_pipeline(
                    active_project=active_project,
                    sessions_dir=sessions_dir,
                    docs_dir=docs_dir,
                    progress_dir=progress_dir,
                    test_sources=test_sources,
                    test_results_dir=test_results_dir,
                    test_flags=flags,
                )
            )
            app.state.sync_task = self.lifecycle.sync_task

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
            self.lifecycle.watcher_started = True

        if self.profile.capabilities.jobs:
            analytics_task = self._start_analytics_snapshot_task()
            if analytics_task is not None:
                self.lifecycle.analytics_snapshot_task = analytics_task
                app.state.analytics_snapshot_task = analytics_task

    async def shutdown(self, app: FastAPI) -> None:
        logger.info("CCDash backend shutting down (profile=%s)", self.profile.name)

        if self.lifecycle.sync_task is not None:
            self.lifecycle.sync_task.cancel()
            try:
                await self.lifecycle.sync_task
            except asyncio.CancelledError:
                pass

        if self.lifecycle.analytics_snapshot_task is not None:
            self.lifecycle.analytics_snapshot_task.cancel()
            try:
                await self.lifecycle.analytics_snapshot_task
            except asyncio.CancelledError:
                pass

        if self.lifecycle.watcher_started:
            await file_watcher.stop()
            self.lifecycle.watcher_started = False

        shutdown_observability(app)
        await connection.close_connection()

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
                self.db,
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

        async def _run_periodic_analytics_snapshots() -> None:
            while True:
                await asyncio.sleep(analytics_interval)
                current_project = project_manager.get_active_project()
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
        return asyncio.create_task(_run_periodic_analytics_snapshots())
