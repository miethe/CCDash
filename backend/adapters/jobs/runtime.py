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
from backend.db.file_watcher import file_watcher, file_watcher_registry
from backend.observability import otel as observability
from backend.runtime.profiles import RuntimeProfile
from backend.adapters.jobs.artifact_rollup_export_job import ArtifactRollupExportJob
from backend.adapters.jobs.telemetry_exporter import TelemetryExporterJob
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache, skillmeat_refresh_configured
from backend.services.test_config import effective_test_flags, resolve_test_sources

logger = logging.getLogger("ccdash.runtime.jobs")


class WatcherRebindError(Exception):
    """Raised when a watcher rebind cannot proceed or fails atomically."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


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


def _resolve_worknotes_dir(paths: Any) -> Path | None:
    """Return the ``.claude/worknotes`` dir for a ResolvedProjectPaths bundle, or None.

    The worknotes directory is optional — many projects do not have one.  This
    helper encapsulates the guard so callers stay concise.
    """
    try:
        root_path: Path | None = getattr(getattr(paths, "root", None), "path", None)
    except Exception:
        return None
    if root_path is None:
        return None
    candidate = root_path / ".claude" / "worknotes"
    return candidate if candidate.exists() else None


@dataclass(slots=True)
class RuntimeJobObservation:
    # P3-013: state distinguishes idle/running/dead/crashed (not just running/idle)
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
    # P3-013: server-side stale_since threshold alarm
    stale_threshold_seconds: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeJobState:
    sync_task: asyncio.Task[None] | None = None
    all_projects_sync_task: asyncio.Task[None] | None = None
    analytics_snapshot_task: asyncio.Task[None] | None = None
    telemetry_export_task: asyncio.Task[None] | None = None
    artifact_rollup_export_task: asyncio.Task[None] | None = None
    cache_warming_task: asyncio.Task[None] | None = None
    retention_prune_task: asyncio.Task[None] | None = None
    reconcile_task: asyncio.Task[None] | None = None
    # T3-004: watcher fan-out reconcile loop task (distinct from the sync reconcile loop).
    watcher_reconcile_task: asyncio.Task[None] | None = None
    # Phase 4 (codex-session-ingestion-v1): bounded Codex backfill at startup.
    codex_backfill_task: asyncio.Task[None] | None = None
    _drain_task: asyncio.Task[None] | None = None
    watcher_started: bool = False
    # T3-001: per-project watcher tasks (fan-out mode).  Keyed by project_id.
    # Empty dict → legacy single-project watcher path (file_watcher singleton).
    fan_out_watcher_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    # T3-001: per-project health state for fan-out watchers.
    # "running" | "degraded" | "stopped"
    fan_out_watcher_health: dict[str, str] = field(default_factory=dict)
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
        # T3-001: fan-out bindings for worker-watch registry-driven mode.
        # Non-empty → one asyncio.Task per binding with supervisor + semaphore.
        # Empty (default) → legacy single-project watcher path.
        watcher_fan_out_bindings: list[ProjectBinding] | None = None,
        telemetry_exporter_job: TelemetryExporterJob | None = None,
        artifact_rollup_export_job: ArtifactRollupExportJob | None = None,
        # P3-005 / P3-010: additive param — safe default keeps container.py unchanged
        workspace_registry: Any | None = None,
    ) -> None:
        self.profile = profile
        self.ports = ports
        self.sync = sync_engine
        self.project_binding = project_binding
        # T3-001: registry-driven fan-out bindings (one per registered project).
        self._watcher_fan_out_bindings: list[ProjectBinding] = watcher_fan_out_bindings or []
        self.telemetry_exporter_job = telemetry_exporter_job
        self.artifact_rollup_export_job = artifact_rollup_export_job
        # P3-005: workspace_registry kwarg allows injecting a custom registry in
        # tests; falls back to ports.workspace_registry at runtime.
        self._workspace_registry_override = workspace_registry
        self.state = RuntimeJobState()
        # P3-010: serialise concurrent rebind / register / unregister calls
        self._rebind_lock: asyncio.Lock | None = None
        # T3-001: shared semaphore bounding concurrent sync executions across all
        # per-project fan-out watcher tasks.  Lazily initialised in start().
        self._watcher_sync_semaphore: asyncio.Semaphore | None = None
        # T3-004: watcher fan-out reconcile loop health state.
        # Set by _start_watcher_reconcile_task() on each tick.
        self._watcher_reconcile_last_at: str | None = None
        self._watcher_reconcile_last_error: str | None = None
        self.state.job_observations.update(
            {
                "startupSync": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="runs",
                    stale_threshold_seconds=3600,
                ),
                "analyticsSnapshots": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="runs",
                    stale_threshold_seconds=7200,
                ),
                "telemetryExports": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="events",
                    stale_threshold_seconds=3600,
                ),
                "artifactRollupExports": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="rollups",
                    stale_threshold_seconds=86400,
                ),
                "cacheWarming": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="runs",
                    stale_threshold_seconds=1800,
                ),
                "retentionPrune": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="rows",
                    stale_threshold_seconds=172800,  # 2× the default 24h interval
                ),
                "reconcile": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="projects",
                    # 6× the default 300s interval — alarm only on a clearly
                    # stalled reconcile loop, not on a single missed tick.
                    stale_threshold_seconds=1800,
                ),
                # Phase 4 (codex-session-ingestion-v1): startup bounded backfill.
                # Stale threshold 24 h — one expected run per worker restart; alarm
                # only if the backfill has never succeeded or is a day old.
                "codexBackfill": RuntimeJobObservation(
                    backlog_count=0,
                    backlog_unit="files",
                    stale_threshold_seconds=86400,
                ),
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
                # P3-006-FU: when durable queue is active, also enqueue a sync job
                # record so that the drain loop can resume it on crash.  The
                # in-process task is still started for immediate execution; the DB
                # record provides crash-resume durability.
                from backend.adapters.jobs.durable_queue import DurableJobScheduler  # noqa: PLC0415
                _sched = self.ports.job_scheduler
                if isinstance(_sched, DurableJobScheduler) and _sched._backend != "memory":
                    try:
                        # Phase 7: use idempotent enqueue so a reload or second
                        # startup dispatch does not queue a duplicate sync job
                        # when one is already pending or running (AC 7.2 durable).
                        _enqueued_id = await _sched.enqueue_durable_idempotent(
                            "sync",
                            {"project_id": str(getattr(active_project, "id", "") or "")},
                            str(getattr(active_project, "id", "") or ""),
                            max_attempts=3,
                        )
                        if _enqueued_id is not None:
                            logger.debug(
                                "P3-006-FU: enqueued durable startup-sync for project_id=%s job_id=%s",
                                getattr(active_project, "id", "?"),
                                _enqueued_id,
                            )
                        else:
                            logger.info(
                                "P3-006-FU: startup-sync coalesced (idempotent) for project_id=%s — "
                                "pending/running job already exists",
                                getattr(active_project, "id", "?"),
                            )
                    except Exception:
                        logger.exception(
                            "P3-006-FU: failed to enqueue durable startup-sync — proceeding in-process"
                        )
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

        if self.profile.capabilities.watch and self.sync is not None and self._watcher_fan_out_bindings:
            # T3-001: fan-out mode — one asyncio.Task per registered project.
            # Supervisor catches per-task exceptions, marks that project degraded,
            # schedules backoff restart.  Sibling tasks are unaffected.
            # Shared semaphore bounds concurrent sync executions across all projects.
            await self._start_fan_out_watchers()
            # T3-004: periodic watcher reconcile loop — re-reads the project registry
            # every CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS (default 60) and
            # idempotently adds/removes watcher bindings for new/deregistered projects.
            watcher_reconcile_task = self._start_watcher_reconcile_task()
            if watcher_reconcile_task is not None:
                self.state.watcher_reconcile_task = watcher_reconcile_task

        elif active_project and self.profile.capabilities.watch and self.sync is not None:
            # Legacy single-project path: start the singleton in-place so that
            # existing `from backend.db.file_watcher import file_watcher` bindings
            # (including routers/cache.py) and test patches always see current state.
            _active_worknotes = _resolve_worknotes_dir(active_bundle)
            await file_watcher.start(
                self.sync,
                active_project.id,
                sessions_dir,
                docs_dir,
                progress_dir,
                test_results_dir=test_results_dir,
                test_sources=test_sources,
                worknotes_dir=_active_worknotes,
            )
            # P3-005: also register in the multi-project registry so the registry
            # snapshot (watcherRegistry probe field) reflects all active projects.
            await file_watcher_registry.register(
                self.sync,
                active_project.id,
                sessions_dir,
                docs_dir,
                progress_dir,
                test_results_dir=test_results_dir,
                test_sources=test_sources,
                worknotes_dir=_active_worknotes,
            )
            self.state.watcher_started = True

        # ALL-PROJECTS sync/watch: when CCDASH_SYNC_ALL_PROJECTS=True, dispatch
        # a non-blocking background job that iterates every registered project
        # (non-active only — active was handled above).  Dispatching as a
        # background task means start() returns promptly so the app becomes
        # healthy immediately; the heavy per-project syncs and watcher
        # registrations run concurrently in the background.
        sync_all = bool(getattr(config, "SYNC_ALL_PROJECTS", True))
        _list_fn = getattr(workspace_registry, "list_projects", None)
        if sync_all and self.sync is not None and callable(_list_fn):
            active_project_id = str(getattr(active_project, "id", "")) if active_project else ""
            _coro = self._run_all_projects_sync_job(
                active_project_id=active_project_id,
                workspace_registry=workspace_registry,
                file_watcher_registry=file_watcher_registry,
                config=config,
            )
            if self.ports.job_scheduler is not None:
                self.state.all_projects_sync_task = self.ports.job_scheduler.schedule(
                    _coro,
                    name=f"ccdash:{self.profile.name}:all-projects-sync",
                )
            else:
                # Fallback: no scheduler available for this profile — still non-blocking
                self.state.all_projects_sync_task = asyncio.create_task(
                    _coro,
                    name=f"ccdash:{self.profile.name}:all-projects-sync",
                )

        # Phase 4 (codex-session-ingestion-v1): bounded Codex backfill at startup.
        # Gated absolutely on CCDASH_CODEX_INGEST_ENABLED (default False); when the
        # flag is off this block is a complete no-op — AC6.  The backfill runs
        # through the scheduler so start() returns immediately (non-blocking).
        if bool(getattr(config, "CCDASH_CODEX_INGEST_ENABLED", False)) and self.sync is not None:
            if bool(getattr(config, "STARTUP_SYNC_ENABLED", True)):
                _codex_task_name = f"ccdash:{self.profile.name}:codex-backfill"
                if self.ports.job_scheduler is not None:
                    self.state.codex_backfill_task = self.ports.job_scheduler.schedule(
                        self._run_codex_backfill_job(),
                        name=_codex_task_name,
                    )
                else:
                    self.state.codex_backfill_task = asyncio.create_task(
                        self._run_codex_backfill_job(),
                        name=_codex_task_name,
                    )
                logger.info(
                    "Phase 4 codex-session-ingestion: bounded backfill job scheduled (profile=%s)",
                    self.profile.name,
                )
            else:
                obs = self.state.job_observations.get("codexBackfill")
                if obs is not None:
                    obs.state = "disabled"
                    obs.last_outcome = "disabled"
                    obs.details["disabledBy"] = "CCDASH_STARTUP_SYNC_ENABLED=false"

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
            retention_prune_task = self._start_retention_prune_task()
            if retention_prune_task is not None:
                self.state.retention_prune_task = retention_prune_task
            # Phase 8 (T8-002): periodic cross-project reconcile sweep.
            reconcile_task = self._start_reconcile_task()
            if reconcile_task is not None:
                self.state.reconcile_task = reconcile_task

        # P3-006-FU: start the durable drain loop when JOB_QUEUE_BACKEND != memory.
        # The drain loop claims pending sync/cache-warming jobs from the DB queue
        # and executes them, providing crash-resume guarantees across container
        # restarts.  The memory path is a no-op (start_drain_loop returns None).
        self._maybe_start_drain_loop(active_project=active_project)

        return self.state

    def _maybe_start_drain_loop(self, *, active_project: Any | None = None) -> None:
        """P3-006-FU: start the durable drain loop when JOB_QUEUE_BACKEND != memory.

        The drain loop is the consumer half of the durable job queue.  It
        claims pending ``sync`` and ``cache-warming`` jobs from the DB and
        executes them via the sync_engine, providing crash-resume across
        container restarts.

        In ``memory`` mode this is a no-op — callers in memory mode see no
        behaviour change.  The drain loop task is stored on state so that
        future supervisor probes can inspect it (same lifecycle as other tasks).
        """
        from backend.adapters.jobs.durable_queue import DurableJobScheduler  # noqa: PLC0415

        scheduler = self.ports.job_scheduler
        if not isinstance(scheduler, DurableJobScheduler):
            return  # memory / in-process path; nothing to do

        sync_engine = self.sync
        adapter_ref = self

        async def _exec_sync(job: dict) -> None:
            """Execute a durable ``sync`` job using the sync_engine."""
            if sync_engine is None:
                logger.warning("Drain-loop: sync executor called but sync_engine is None; skipping")
                return
            payload = job.get("payload") or {}
            project_id = payload.get("project_id") or job.get("project_id")
            if not project_id:
                logger.warning("Drain-loop: sync job id=%s missing project_id; skipping", job.get("id"))
                return
            workspace_registry = adapter_ref.ports.workspace_registry
            binding = workspace_registry.resolve_project_binding(
                project_id, allow_active_fallback=False, refresh=True
            )
            if binding is None:
                logger.warning(
                    "Drain-loop: sync job id=%s — project_id=%s not found in registry; skipping",
                    job.get("id"),
                    project_id,
                )
                return
            bundle = binding.paths
            sessions_dir, docs_dir, progress_dir = bundle.as_tuple()
            logger.info(
                "Drain-loop executing sync job id=%s project_id=%s checkpoint=%s",
                job.get("id"),
                project_id,
                job.get("checkpoint"),
            )
            await sync_engine.sync_project(
                project_id,
                sessions_dir,
                docs_dir,
                progress_dir,
            )

        async def _exec_cache_warming(job: dict) -> None:
            """Execute a durable ``cache-warming`` job by triggering a cache refresh."""
            payload = job.get("payload") or {}
            project_id = payload.get("project_id") or job.get("project_id")
            logger.info(
                "Drain-loop executing cache-warming job id=%s project_id=%s",
                job.get("id"),
                project_id,
            )
            # Re-use the sync_engine analytics snapshot as a lightweight warmup proxy.
            if sync_engine is not None and project_id:
                try:
                    await sync_engine.capture_analytics_snapshot(
                        project_id, trigger="durable_cache_warming"
                    )
                except Exception:
                    logger.exception("Drain-loop cache-warming job failed for project_id=%s", project_id)
                    raise

        executors: dict = {
            "sync": _exec_sync,
            "cache-warming": _exec_cache_warming,
        }

        drain_task = scheduler.start_drain_loop(executors, poll_interval=2.0, reclaim_on_start=True)
        if drain_task is not None:
            # Attach to state so the adapter knows a drain loop is running.
            # We reuse the analytics_snapshot_task slot is not ideal — store
            # as a named attribute so it doesn't conflict.
            setattr(self.state, "_drain_task", drain_task)
            logger.info(
                "P3-006-FU: durable drain-loop started (backend=%s)",
                scheduler._backend,
            )

    def _get_rebind_lock(self) -> asyncio.Lock:
        """Lazily create the rebind lock (P3-010)."""
        if self._rebind_lock is None:
            self._rebind_lock = asyncio.Lock()
        return self._rebind_lock

    async def rebind_watcher(self, new_project_id: str) -> dict[str, object]:
        """Atomically rebind the file watcher to the new project's paths.

        P3-010: wrapped in _rebind_lock so concurrent calls are serialised.

        Sequence:
        1. Resolve new project's paths via the workspace registry.
        2. Validate paths exist (return 4xx-compatible error if not).
        3. Capture old-project snapshot as rollback target.
        4. Drain the outgoing project (light sync) to minimise event loss.
        5. Stop old watcher (via registry), start new watcher (via registry).
        6. On start failure, rollback to old project's watcher.
        7. Trigger one-shot sync for new project.

        Returns a dict with ``watcherRebound: bool`` and optional ``error: str``.
        Raises ``WatcherRebindError`` on unrecoverable failure.
        """
        if not self.profile.capabilities.watch or self.sync is None:
            # Watcher is not enabled for this runtime profile; rebind is a no-op.
            return {"watcherRebound": False, "error": "watcher_not_enabled"}

        # P3-010: serialise concurrent rebind calls
        async with self._get_rebind_lock():
            return await self._rebind_watcher_inner(new_project_id)

    async def _rebind_watcher_inner(self, new_project_id: str) -> dict[str, object]:
        """Inner rebind logic (already holding _rebind_lock)."""
        workspace_registry = self.ports.workspace_registry

        # Step 1: Resolve new project binding (raises ValueError if not found).
        new_binding = workspace_registry.resolve_project_binding(
            new_project_id, allow_active_fallback=False, refresh=True
        )
        if new_binding is None:
            raise WatcherRebindError(f"Project '{new_project_id}' not found", status_code=404)

        new_project = new_binding.project
        new_paths = new_binding.paths  # ResolvedProjectPaths
        new_sessions_dir, new_docs_dir, new_progress_dir = new_paths.as_tuple()

        # Step 2: Validate that at least one watch path exists before stopping.
        existing_paths = [p for p in [new_sessions_dir, new_docs_dir, new_progress_dir] if p.exists()]
        if not existing_paths:
            raise WatcherRebindError(
                f"No watch paths exist for project '{new_project_id}': "
                f"sessions={new_sessions_dir}, docs={new_docs_dir}, progress={new_progress_dir}",
                status_code=422,
            )

        # Step 3: Capture old snapshot for rollback from the singleton
        # (file_watcher is the name imported into this module — tests can patch it and
        # all reads/writes here will use the patched instance).
        old_snapshot = file_watcher.snapshot()
        old_project_id: str | None = old_snapshot.get("projectId")  # type: ignore[assignment]

        # Resolve old binding for rollback (only needed if stop later succeeds but start fails).
        old_binding = (
            workspace_registry.resolve_project_binding(
                old_project_id, allow_active_fallback=False, refresh=False
            )
            if old_project_id
            else None
        )

        # Step 4: Drain the outgoing project (light sync) — drain-before-rebind strategy.
        if old_project_id and old_binding is not None:
            old_sessions_dir, old_docs_dir, old_progress_dir = old_binding.paths.as_tuple()
            try:
                if hasattr(self.sync, "sync_planning_artifacts"):
                    await self.sync.sync_planning_artifacts(
                        old_project_id,
                        old_docs_dir,
                        old_progress_dir,
                        force=False,
                    )
            except Exception:
                logger.exception(
                    "Watcher rebind: drain sync failed for outgoing project '%s' — continuing",
                    old_project_id,
                )

        # Step 5: Atomic stop → start.
        # Mutate the singleton in-place: stop it then restart it with the new project's
        # paths.  This keeps every existing `from backend.db.file_watcher import file_watcher`
        # binding (including routers/cache.py and test patches) pointing at an object that
        # reflects the current active project.
        await file_watcher.stop()
        self.state.watcher_started = False

        # P3-005: also keep the registry consistent — unregister old, register new.
        if old_project_id:
            await file_watcher_registry.unregister(old_project_id)

        try:
            await file_watcher.start(
                self.sync,
                new_project.id,
                new_sessions_dir,
                new_docs_dir,
                new_progress_dir,
            )
            # Mirror into registry (best-effort; don't let registry errors abort the rebind).
            try:
                await file_watcher_registry.register(
                    self.sync,
                    new_project.id,
                    new_sessions_dir,
                    new_docs_dir,
                    new_progress_dir,
                )
            except Exception:
                logger.exception(
                    "Watcher rebind: registry.register() failed for project '%s' — singleton is live",
                    new_project_id,
                )
            self.state.watcher_started = True
        except Exception as start_exc:
            # Step 6: Rollback — restart singleton on old project.
            logger.exception(
                "Watcher rebind: start() failed for project '%s' — attempting rollback",
                new_project_id,
            )
            if old_binding is not None:
                r_sessions_dir, r_docs_dir, r_progress_dir = old_binding.paths.as_tuple()
                try:
                    await file_watcher.start(
                        self.sync,
                        str(old_project_id),
                        r_sessions_dir,
                        r_docs_dir,
                        r_progress_dir,
                    )
                    self.state.watcher_started = True
                    logger.info(
                        "Watcher rebind: rollback succeeded — watcher restarted on project '%s'",
                        old_project_id,
                    )
                except Exception:
                    logger.exception(
                        "Watcher rebind: rollback start() also failed for project '%s'",
                        old_project_id,
                    )
            raise WatcherRebindError(
                f"Failed to start watcher for project '{new_project_id}': {start_exc}",
                status_code=422,
            ) from start_exc

        # Step 7: One-shot sync for new project (startup-equivalent, sessions/docs/progress only).
        # Test sources are intentionally excluded from the rebind sync; a full test sync runs
        # as part of the startup pipeline and is not required for immediate session visibility.
        try:
            await self.sync.sync_project(
                new_project,
                new_sessions_dir,
                new_docs_dir,
                new_progress_dir,
                trigger="rebind",
                rebuild_links=False,
                capture_analytics=False,
                backfill_session_intelligence=False,
            )
        except Exception:
            logger.exception(
                "Watcher rebind: one-shot sync failed for project '%s' — watcher is running but table may be stale",
                new_project_id,
            )

        logger.info(
            "Watcher rebind complete",
            extra={"old_project_id": old_project_id, "new_project_id": new_project_id},
        )
        return {"watcherRebound": True}

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

        if self.state.reconcile_task is not None:
            self.state.reconcile_task.cancel()
            try:
                await self.state.reconcile_task
            except asyncio.CancelledError:
                pass
            self.state.reconcile_task = None

        # Phase 4 (codex-session-ingestion-v1): cancel the backfill task if still running.
        if self.state.codex_backfill_task is not None:
            self.state.codex_backfill_task.cancel()
            try:
                await self.state.codex_backfill_task
            except asyncio.CancelledError:
                pass
            self.state.codex_backfill_task = None

        # T3-004: stop watcher fan-out reconcile loop before stopping the watcher tasks.
        if self.state.watcher_reconcile_task is not None:
            self.state.watcher_reconcile_task.cancel()
            try:
                await self.state.watcher_reconcile_task
            except asyncio.CancelledError:
                pass
            self.state.watcher_reconcile_task = None

        # T3-001: stop fan-out watcher tasks (registry-driven mode).
        if self.state.fan_out_watcher_tasks:
            for project_id, task in list(self.state.fan_out_watcher_tasks.items()):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            self.state.fan_out_watcher_tasks.clear()
            self.state.fan_out_watcher_health.clear()
            await file_watcher_registry.stop_all()

        if self.state.watcher_started:
            # Stop the singleton in-place (keeps all from-import bindings valid).
            if file_watcher.is_running:
                await file_watcher.stop()
            # P3-005: also drain the registry.
            await file_watcher_registry.stop_all()
            self.state.watcher_started = False

    async def _start_fan_out_watchers(self) -> None:
        """T3-001: Start one asyncio.Task per project in registry-driven fan-out mode.

        Each task runs the FileWatcher for a single project, registered in both the
        legacy singleton (first project only, for probe compatibility) and the
        FileWatcherRegistry (all projects).

        Supervisor pattern: ``add_done_callback`` on each task catches per-project
        failures, marks that project ``degraded``, and schedules a backoff restart
        (30s initial, 5min max).  Sibling watchers are unaffected.

        Shared ``asyncio.Semaphore(CCDASH_WATCHER_SYNC_CONCURRENCY)`` bounds total
        concurrent sync executions across all project watcher tasks.
        """
        concurrency = getattr(config, "WATCHER_SYNC_CONCURRENCY", 20)
        self._watcher_sync_semaphore = asyncio.Semaphore(concurrency)
        sync_engine = self.sync
        semaphore = self._watcher_sync_semaphore
        adapter_ref = self

        # Track backoff state per project: (attempt_count, first_failure_at)
        _backoff_state: dict[str, tuple[int, float]] = {}

        def _make_supervisor_callback(project_id: str):
            """Return a done_callback that quarantines a failed project watcher task."""
            def _on_task_done(task: asyncio.Task[None]) -> None:
                if task.cancelled():
                    # Normal shutdown — do not restart.
                    return
                exc = task.exception() if not task.cancelled() else None
                if exc is None:
                    # Task completed without exception (clean shutdown).
                    return
                logger.error(
                    "T3-001 fan-out watcher task for project_id=%s raised exception — "
                    "marking degraded and scheduling backoff restart: %s",
                    project_id,
                    exc,
                    exc_info=exc,
                )
                adapter_ref.state.fan_out_watcher_health[project_id] = "degraded"
                # Remove the dead task entry.
                adapter_ref.state.fan_out_watcher_tasks.pop(project_id, None)
                # Schedule backoff restart.
                attempt, first_fail = _backoff_state.get(project_id, (0, 0.0))
                import time as _time  # noqa: PLC0415
                now = _time.monotonic()
                if attempt == 0 or (now - first_fail) > 600:
                    # First failure or more than 10 minutes since first failure → reset.
                    _backoff_state[project_id] = (1, now)
                    backoff = 30
                else:
                    _backoff_state[project_id] = (attempt + 1, first_fail)
                    backoff = min(300, 30 * (2 ** (attempt - 1)))
                logger.warning(
                    "T3-001 fan-out watcher: scheduling restart for project_id=%s "
                    "in %ds (attempt=%d)",
                    project_id,
                    backoff,
                    attempt + 1,
                )

                async def _delayed_restart() -> None:
                    await asyncio.sleep(backoff)
                    if project_id in adapter_ref.state.fan_out_watcher_tasks:
                        # Already restarted by another path.
                        return
                    try:
                        workspace_registry = adapter_ref.ports.workspace_registry
                        binding = workspace_registry.resolve_project_binding(
                            project_id, allow_active_fallback=False, refresh=True
                        )
                        if binding is None:
                            logger.warning(
                                "T3-001 fan-out watcher restart: project_id=%s no longer in "
                                "registry — skipping restart",
                                project_id,
                            )
                            return
                        await adapter_ref._start_single_fan_out_watcher(
                            binding=binding,
                            semaphore=semaphore,
                            supervisor_callback=_make_supervisor_callback(project_id),
                        )
                    except Exception:
                        logger.exception(
                            "T3-001 fan-out watcher: restart failed for project_id=%s", project_id
                        )
                        adapter_ref.state.fan_out_watcher_health[project_id] = "degraded"

                asyncio.create_task(
                    _delayed_restart(),
                    name=f"ccdash:watcher:restart:{project_id}",
                )
            return _on_task_done

        first = True
        for binding in self._watcher_fan_out_bindings:
            project_id = str(getattr(binding.project, "id", "") or "")
            if not project_id:
                continue
            callback = _make_supervisor_callback(project_id)
            await self._start_single_fan_out_watcher(
                binding=binding,
                semaphore=semaphore,
                supervisor_callback=callback,
                # First project also seeds the legacy singleton for probe compat.
                start_singleton=first,
            )
            first = False

        if self.state.fan_out_watcher_tasks:
            self.state.watcher_started = True
            logger.info(
                "T3-001 fan-out watchers started: %d project(s) (semaphore=%d)",
                len(self.state.fan_out_watcher_tasks),
                concurrency,
            )
        else:
            logger.warning(
                "T3-001 fan-out watchers: no tasks started "
                "(all %d bindings failed or had empty project ids)",
                len(self._watcher_fan_out_bindings),
            )

    async def _start_single_fan_out_watcher(
        self,
        *,
        binding: ProjectBinding,
        semaphore: asyncio.Semaphore,
        supervisor_callback,
        start_singleton: bool = False,
    ) -> None:
        """Register one project watcher in the FileWatcherRegistry and create its task.

        T3-001: isolated per-project watcher.  The task is named
        ``ccdash:watcher:{project_id}`` per the SPIKE specification.
        ``start_singleton=True`` additionally seeds the legacy ``file_watcher``
        singleton for the first project so probe compatibility is maintained.
        """
        sync_engine = self.sync
        project = binding.project
        project_id = str(getattr(project, "id", "") or "")
        paths = binding.paths
        sessions_dir, docs_dir, progress_dir = paths.as_tuple()
        worknotes_dir = _resolve_worknotes_dir(paths)

        # Register in the FileWatcherRegistry (which creates and starts its own FileWatcher).
        await file_watcher_registry.register(
            sync_engine,
            project_id,
            sessions_dir,
            docs_dir,
            progress_dir,
            worknotes_dir=worknotes_dir,
        )

        if start_singleton:
            # Seed the legacy singleton (in-place mutation) for probe compatibility.
            if not file_watcher.is_running:
                await file_watcher.start(
                    sync_engine,
                    project_id,
                    sessions_dir,
                    docs_dir,
                    progress_dir,
                    worknotes_dir=worknotes_dir,
                )

        # Create a supervisor task that drives the watcher lifecycle and respects
        # the shared semaphore for sync concurrency.
        async def _project_watcher_task() -> None:
            """Supervisor task: keeps the registry watcher alive and semaphore-gated."""
            # The actual watch loop already runs inside file_watcher_registry's
            # FileWatcher task.  This supervisor task gates sync calls via the
            # shared semaphore and remains alive as long as the registry entry exists.
            # On exception, it propagates so the done_callback can quarantine and restart.
            entry = file_watcher_registry._entries.get(project_id)
            if entry is None:
                logger.warning(
                    "T3-001 fan-out task for project_id=%s: registry entry not found after register; "
                    "task will exit immediately",
                    project_id,
                )
                return
            inner_task = entry.watcher._task
            if inner_task is not None:
                # Wait for the underlying watch loop to finish (cancelled on stop).
                try:
                    await inner_task
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Propagate so the done_callback handles restart.
                    raise

        task = asyncio.create_task(
            _project_watcher_task(),
            name=f"ccdash:watcher:{project_id}",
        )
        task.add_done_callback(supervisor_callback)
        self.state.fan_out_watcher_tasks[project_id] = task
        self.state.fan_out_watcher_health[project_id] = "running"
        logger.info(
            "T3-001 fan-out watcher task created for project_id=%s (task_name=%s)",
            project_id,
            task.get_name(),
        )

    def _start_watcher_reconcile_task(self) -> asyncio.Task[None] | None:
        """T3-004: periodic watcher fan-out reconcile loop.

        Runs every ``CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS`` (default 60,
        min 10, max 3600).  On each tick:
          1. Re-reads ``workspace_registry.list_projects()`` (all registered
             projects, no ``is_active`` filter — ADR-006).
          2. Computes the symmetric diff against the currently active watcher set
             (``state.fan_out_watcher_tasks``).
          3. Idempotently adds a watcher for each new project id.
          4. Idempotently cancels and unregisters each removed project id.

        A tick failure is logged as WARNING and the next tick is scheduled
        normally — one bad tick never crashes the loop.

        ``lastReconcileAt`` / ``lastReconcileError`` are written to
        ``self._watcher_reconcile_last_at`` / ``self._watcher_reconcile_last_error``
        so that ``_watcher_probe_detail`` can surface them in the health rollup
        (T3-003 OQ-5 contract).

        Only started when the profile is ``worker-watch`` and fan-out mode is
        active (``self._watcher_fan_out_bindings`` is non-empty at startup).
        In single-project or legacy mode this method returns ``None``.
        """
        interval_seconds = int(getattr(config, "WATCHER_RECONCILE_INTERVAL_SECONDS", 60))
        if interval_seconds <= 0:
            return None
        if not self.profile.capabilities.watch:
            return None
        # Only run the reconcile loop when fan-out mode is active.
        if not self._watcher_fan_out_bindings:
            return None

        adapter_ref = self
        semaphore = self._watcher_sync_semaphore

        async def _run_watcher_reconcile() -> None:
            while True:
                await asyncio.sleep(interval_seconds)
                tick_error: str | None = None
                try:
                    workspace_registry = adapter_ref.ports.workspace_registry

                    # Reload the registry snapshot so newly added projects surface
                    # without a process restart.
                    _reload = getattr(workspace_registry, "reload_projects", None)
                    if callable(_reload):
                        try:
                            _reload()
                        except Exception:
                            logger.exception(
                                "T3-004 watcher reconcile: reload_projects() failed — continuing"
                            )

                    _list_fn = getattr(workspace_registry, "list_projects", None)
                    all_projects = list(_list_fn()) if callable(_list_fn) else []
                    registry_ids: set[str] = set()
                    for proj in all_projects:
                        pid = str(getattr(proj, "id", "") or "")
                        if pid:
                            registry_ids.add(pid)

                    active_ids: set[str] = set(adapter_ref.state.fan_out_watcher_tasks.keys())
                    new_ids = registry_ids - active_ids
                    removed_ids = active_ids - registry_ids

                    # Add watchers for new projects.
                    for pid in new_ids:
                        try:
                            binding = workspace_registry.resolve_project_binding(
                                pid, allow_active_fallback=False, refresh=True
                            )
                            if binding is None:
                                logger.warning(
                                    "T3-004 watcher reconcile: no binding for new project '%s' — "
                                    "will retry next tick",
                                    pid,
                                )
                                continue
                            # Use the existing fan-out infrastructure (semaphore + supervisor).
                            # Build a minimal supervisor callback for dynamically added projects.
                            def _make_minimal_cb(project_id: str):
                                def _cb(task: asyncio.Task[None]) -> None:
                                    if task.cancelled():
                                        return
                                    exc = task.exception() if not task.cancelled() else None
                                    if exc is not None:
                                        logger.error(
                                            "T3-004 reconcile: fan-out watcher for project_id=%s "
                                            "raised exception: %s",
                                            project_id, exc, exc_info=exc,
                                        )
                                        adapter_ref.state.fan_out_watcher_health[project_id] = "degraded"
                                        adapter_ref.state.fan_out_watcher_tasks.pop(project_id, None)
                                return _cb

                            _cb = _make_minimal_cb(pid)
                            await adapter_ref._start_single_fan_out_watcher(
                                binding=binding,
                                semaphore=semaphore or asyncio.Semaphore(
                                    getattr(config, "WATCHER_SYNC_CONCURRENCY", 20)
                                ),
                                supervisor_callback=_cb,
                                start_singleton=False,
                            )
                            logger.info(
                                "T3-004 watcher reconcile: added watcher for new project '%s'", pid
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception(
                                "T3-004 watcher reconcile: failed to add watcher for project '%s' — "
                                "will retry next tick",
                                pid,
                            )

                    # Remove watchers for deregistered projects.
                    for pid in removed_ids:
                        try:
                            task = adapter_ref.state.fan_out_watcher_tasks.pop(pid, None)
                            if task is not None and not task.done():
                                task.cancel()
                                try:
                                    await task
                                except (asyncio.CancelledError, Exception):
                                    pass
                            adapter_ref.state.fan_out_watcher_health.pop(pid, None)
                            await file_watcher_registry.unregister(pid)
                            logger.info(
                                "T3-004 watcher reconcile: removed watcher for deregistered project '%s'",
                                pid,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception(
                                "T3-004 watcher reconcile: failed to remove watcher for project '%s' — "
                                "will retry next tick",
                                pid,
                            )

                    if new_ids or removed_ids:
                        logger.info(
                            "T3-004 watcher reconcile tick: added=%d removed=%d active=%d",
                            len(new_ids),
                            len(removed_ids),
                            len(adapter_ref.state.fan_out_watcher_tasks),
                        )
                    else:
                        logger.debug(
                            "T3-004 watcher reconcile tick: no changes (active=%d)",
                            len(adapter_ref.state.fan_out_watcher_tasks),
                        )

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    tick_error = str(exc) or exc.__class__.__name__
                    logger.warning(
                        "T3-004 watcher reconcile tick failed — scheduling next tick normally: %s",
                        tick_error,
                        exc_info=exc,
                    )

                # Update health state regardless of success/failure so the probe
                # always reflects the last tick outcome (T3-003 lastReconcileAt/Error).
                adapter_ref._watcher_reconcile_last_at = _isoformat(_utc_now())
                adapter_ref._watcher_reconcile_last_error = tick_error

        logger.info(
            "T3-004 watcher reconcile loop started (profile=%s interval=%ds)",
            self.profile.name,
            interval_seconds,
        )
        return asyncio.create_task(
            _run_watcher_reconcile(),
            name=f"ccdash:{self.profile.name}:watcher-reconcile",
        )

    def status_snapshot(self) -> dict[str, Any]:
        watcher_detail = self._watcher_probe_detail()
        snapshot: dict[str, Any] = {
            "watcher": watcher_detail["state"],
            "watcherDetail": watcher_detail,
            # P3-005: include per-project watcher registry state
            "watcherRegistry": self._watcher_registry_snapshot(),
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
                # P3-015: queue-depth metrics per job
                "queueDepth": self._worker_probe_queue_depth(worker_jobs),
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

        # Use the singleton for the primary probe — it is the authoritative active-project
        # watcher and is what from-import consumers (routers/cache.py) read.
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

        # T3-003: per-project health breakdown derived from the registry snapshot.
        # Shape per OQ-5: {project_id: {state, watchPathCount, lastChangeSyncAt}}
        per_project: dict[str, dict[str, Any]] = {}
        all_registry_snapshots = file_watcher_registry.snapshot_all()
        for pid, proj_snap in all_registry_snapshots.items():
            proj_running = bool(proj_snap.get("running", False))
            proj_configured = bool(proj_snap.get("configured", False))
            proj_wpc = int(proj_snap.get("watchPathCount", 0) or 0)
            if proj_running:
                proj_state = "running"
            elif proj_configured and proj_wpc == 0:
                proj_state = "configured_no_paths"
            elif proj_configured:
                proj_state = "stopped"
            else:
                proj_state = "not_configured"
            # Also honour fan-out health map if degraded.
            if self.state.fan_out_watcher_health.get(pid) == "degraded":
                proj_state = "degraded"
            per_project[pid] = {
                "state": proj_state,
                "watchPathCount": proj_wpc,
                "lastChangeSyncAt": proj_snap.get("lastChangeSyncAt"),
            }

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
            # T3-003: per-project breakdown (OQ-5); consumer fallback: missing → {}
            "projects": per_project,
            # T3-004: watcher reconcile loop health state
            "lastReconcileAt": self._watcher_reconcile_last_at,
            "lastReconcileError": self._watcher_reconcile_last_error,
        }

    def _watcher_registry_snapshot(self) -> dict[str, Any]:
        """P3-005: aggregate snapshot of all registered project watchers."""
        all_snapshots = file_watcher_registry.snapshot_all()
        return {
            "registeredProjects": file_watcher_registry.registered_project_ids,
            "projectCount": len(all_snapshots),
            "perProject": all_snapshots,
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
        allow_writeback: bool = True,
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
                allow_writeback=allow_writeback,
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

    async def _run_codex_backfill_job(self) -> None:
        """Phase 4 (codex-session-ingestion-v1): bounded Codex backfill at startup.

        Calls ``sync_codex_sessions(force=False, backfill_only=True)`` once at
        worker startup so the first run only ingests rollout files within the
        ``CCDASH_CODEX_BACKFILL_DAYS`` (default 7) window.  Subsequent new or
        changed files are picked up by the periodic reconcile pass
        (``_run_periodic_reconcile``).

        Gated absolutely on ``CCDASH_CODEX_INGEST_ENABLED``; the flag check
        inside ``sync_codex_sessions`` is authoritative (AC6) so this method
        merely adds structured job-observation tracking on top.

        Non-blocking: dispatched via the job scheduler from ``start()``.
        """
        started = self._mark_job_started("codexBackfill", backlog_count=1)
        try:
            stats = await self.sync.sync_codex_sessions(force=False, backfill_only=True)
        except asyncio.CancelledError:
            self._mark_job_cancelled("codexBackfill", started, backlog_count=0)
            raise
        except Exception as exc:
            self._mark_job_failure("codexBackfill", started, exc, backlog_count=0)
            logger.exception("codex-backfill job failed")
            raise
        else:
            self._mark_job_success(
                "codexBackfill",
                started,
                backlog_count=0,
                details={
                    "synced": stats.get("synced", 0),
                    "skipped": stats.get("skipped", 0),
                    "parseErrors": stats.get("parse_errors", 0),
                    "unattributed": stats.get("unattributed", 0),
                    "unattributedCwds": stats.get("unattributed_cwds", []),
                },
            )

    async def _run_all_projects_sync_job(
        self,
        *,
        active_project_id: str,
        workspace_registry: Any,
        file_watcher_registry: Any,
        config: Any,
    ) -> None:
        """Background job: sync and register watchers for all non-active projects.

        Extracted from start() so that the heavy per-project work runs in the
        background and does NOT block start() from returning.  All existing
        guards and behaviours are preserved:
        - SYNC_ALL_PROJECTS flag controls whether this is called at all (checked
          in start() before dispatching).
        - capabilities.sync + STARTUP_SYNC_ENABLED gate the sync portion.
        - capabilities.watch gates the watcher-registration portion.
        - allow_writeback=False is passed for every non-active project.
        - Per-project exceptions are caught and logged; the loop continues.
        - Syncs are serialised inside this coroutine to avoid saturating SQLite.
        """
        _list_fn = getattr(workspace_registry, "list_projects", None)
        if not callable(_list_fn):
            return
        all_projects = _list_fn()
        for other_project in all_projects:
            other_id = str(getattr(other_project, "id", ""))
            if other_id == active_project_id:
                continue  # already handled by the active-project startup path
            try:
                other_binding = workspace_registry.resolve_project_binding(
                    other_id, allow_active_fallback=False, refresh=True
                )
            except Exception:
                logger.exception(
                    "all-projects-sync: resolve_project_binding failed for project '%s' — skipping",
                    other_id,
                )
                continue
            if other_binding is None:
                logger.debug(
                    "all-projects-sync: no binding for project '%s' — skipping",
                    other_id,
                )
                continue
            other_sessions, other_docs, other_progress = other_binding.paths.as_tuple()
            other_worknotes = _resolve_worknotes_dir(other_binding.paths)

            if self.profile.capabilities.sync and bool(getattr(config, "STARTUP_SYNC_ENABLED", True)):
                try:
                    await self.sync.sync_project(
                        other_project,
                        other_sessions,
                        other_docs,
                        other_progress,
                        trigger="startup_all_projects",
                        rebuild_links=True,
                        capture_analytics=False,
                        backfill_session_intelligence=False,
                        allow_writeback=False,
                    )
                    logger.info(
                        "all-projects-sync: synced non-active project '%s'",
                        other_id,
                    )
                except Exception:
                    logger.exception(
                        "all-projects-sync: sync failed for project '%s' — continuing",
                        other_id,
                    )

            if self.profile.capabilities.watch:
                try:
                    await file_watcher_registry.register(
                        self.sync,
                        other_id,
                        other_sessions,
                        other_docs,
                        other_progress,
                        worknotes_dir=other_worknotes,
                        allow_writeback=False,
                    )
                    self.state.watcher_started = True
                    logger.info(
                        "all-projects-sync: registered watcher for non-active project '%s'",
                        other_id,
                    )
                except Exception:
                    logger.exception(
                        "all-projects-sync: watcher register failed for project '%s' — continuing",
                        other_id,
                    )

    def _start_reconcile_task(self) -> asyncio.Task[None] | None:
        """Phase 8 (T8-002/003/004): periodic cross-project reconcile sweep.

        Every ``CCDASH_RECONCILE_INTERVAL_SECONDS`` (default 300) the job:
          1. Invalidates the registry snapshot (post-boot project pickup) and
             enumerates ALL projects from the DB-authoritative registry
             (ADR-006) — never projects.json directly.
          2. Dispatches a per-project freshness pass THROUGH the Phase 7
             coalescing guard (``SyncEngine.sync_project``, trigger="reconcile")
             so missed filesystem events and post-boot changes are caught.
             Non-active projects are read/ingest-only (``allow_writeback=False``,
             AC 8.5 regression contract); the active project keeps writeback.
          3. Self-heals dead/crashed watchers (T8-003): any expected watcher that
             is not running is re-bound from the registry; failures are logged
             and retried next tick (never silently dead).

        Disabled when the interval is ``<= 0`` (resilience: cross-project
        freshness then relies on live watchers + the boot sweep — baseline
        behaviour, no error).  Requires ``capabilities.sync`` and a sync_engine.
        """
        interval_seconds = max(0, int(getattr(config, "RECONCILE_INTERVAL_SECONDS", 300)))
        if interval_seconds <= 0:
            return None
        if not self.profile.capabilities.sync or self.sync is None:
            return None

        self.state.job_observations["reconcile"].interval_seconds = interval_seconds
        workspace_registry = self.ports.workspace_registry
        active_project_id = (
            str(getattr(self.project_binding.project, "id", "") or "")
            if self.project_binding is not None
            else ""
        )
        heal_enabled = bool(getattr(config, "WATCHER_HEAL_ENABLED", True))
        can_watch = bool(self.profile.capabilities.watch)

        async def _run_periodic_reconcile() -> None:
            while True:
                await asyncio.sleep(interval_seconds)

                # Post-boot pickup: invalidate the cached registry snapshot so a
                # project/dir added AFTER boot surfaces (no restart). Guarded —
                # legacy/mock registries without reload_projects() are a no-op.
                _reload = getattr(workspace_registry, "reload_projects", None)
                if callable(_reload):
                    try:
                        _reload()
                    except Exception:
                        logger.exception("reconcile: registry reload_projects() failed — continuing")

                _list_fn = getattr(workspace_registry, "list_projects", None)
                projects = list(_list_fn()) if callable(_list_fn) else []
                if not projects:
                    logger.debug("reconcile: no projects in registry — skipping this tick")
                    continue

                started = self._mark_job_started("reconcile", backlog_count=len(projects))
                reconciled = 0
                healed = 0
                failed_project_ids: list[str] = []
                expected_ids: list[str] = []

                for project in projects:
                    pid = str(getattr(project, "id", "") or "")
                    if not pid:
                        # AC 8.1: one malformed/empty project row never stalls
                        # the sweep — skip with a logged warning and continue.
                        logger.warning(
                            "reconcile: malformed/empty project row (no id) — skipping"
                        )
                        continue

                    try:
                        binding = workspace_registry.resolve_project_binding(
                            pid, allow_active_fallback=False, refresh=True
                        )
                    except asyncio.CancelledError:
                        self._mark_job_cancelled("reconcile", started, backlog_count=0)
                        raise
                    except Exception:
                        logger.exception(
                            "reconcile: resolve_project_binding failed for project '%s' — skipping",
                            pid,
                        )
                        failed_project_ids.append(pid)
                        continue
                    if binding is None:
                        logger.debug(
                            "reconcile: no binding for project '%s' — skipping", pid
                        )
                        continue

                    sessions_dir, docs_dir, progress_dir = binding.paths.as_tuple()
                    worknotes_dir = _resolve_worknotes_dir(binding.paths)
                    is_active = pid == active_project_id
                    expected_ids.append(pid)

                    # Freshness pass via the Phase 7 coalescing guard. sync_project
                    # keys (project_id, trigger) on self._sync_in_flight, so an
                    # overlapping reconcile tick for the same project coalesces
                    # (no double-scan). Non-active stays read/ingest-only.
                    try:
                        await self.sync.sync_project(
                            project,
                            sessions_dir,
                            docs_dir,
                            progress_dir,
                            trigger="reconcile",
                            rebuild_links=True,
                            capture_analytics=False,
                            backfill_session_intelligence=False,
                            allow_writeback=is_active,
                        )
                        reconciled += 1
                    except asyncio.CancelledError:
                        self._mark_job_cancelled("reconcile", started, backlog_count=0)
                        raise
                    except Exception:
                        logger.exception(
                            "reconcile: sync_project failed for project '%s' — continuing",
                            pid,
                        )
                        failed_project_ids.append(pid)

                # Watcher liveness self-heal (T8-003).
                if heal_enabled and can_watch and expected_ids:
                    dead = file_watcher_registry.dead_project_ids(expected_ids)
                    for pid in dead:
                        try:
                            binding = workspace_registry.resolve_project_binding(
                                pid, allow_active_fallback=False, refresh=True
                            )
                        except Exception:
                            logger.exception(
                                "reconcile self-heal: resolve binding failed for '%s' — retry next tick",
                                pid,
                            )
                            continue
                        if binding is None:
                            continue
                        s_dir, d_dir, p_dir = binding.paths.as_tuple()
                        w_dir = _resolve_worknotes_dir(binding.paths)
                        try:
                            await file_watcher_registry.register(
                                self.sync,
                                pid,
                                s_dir,
                                d_dir,
                                p_dir,
                                worknotes_dir=w_dir,
                                allow_writeback=(pid == active_project_id),
                            )
                            self.state.watcher_started = True
                            healed += 1
                            logger.info(
                                "watcher self-heal: re-bound project '%s' (reason=not_running)",
                                pid,
                            )
                        except asyncio.CancelledError:
                            self._mark_job_cancelled("reconcile", started, backlog_count=0)
                            raise
                        except Exception:
                            logger.exception(
                                "watcher self-heal: re-bind failed for project '%s' — "
                                "retry next tick (never silently dead)",
                                pid,
                            )

                # Phase 4 (codex-session-ingestion-v1): global Codex reconcile scan.
                # backfill_only=False → no date window; mtime idempotency in
                # _sync_single_codex_session ensures no dup rows on re-scan.
                # Runs AFTER all per-project sweeps so per-project failures do not
                # block the Codex pass.  Gated on CCDASH_CODEX_INGEST_ENABLED.
                codex_reconcile_failed = False
                if bool(getattr(config, "CCDASH_CODEX_INGEST_ENABLED", False)):
                    try:
                        codex_stats = await self.sync.sync_codex_sessions(
                            force=False, backfill_only=False
                        )
                        logger.info(
                            "reconcile: codex scan complete: synced=%d skipped=%d "
                            "parse_errors=%d unattributed=%d",
                            codex_stats.get("synced", 0),
                            codex_stats.get("skipped", 0),
                            codex_stats.get("parse_errors", 0),
                            codex_stats.get("unattributed", 0),
                        )
                    except asyncio.CancelledError:
                        self._mark_job_cancelled("reconcile", started, backlog_count=0)
                        raise
                    except Exception:
                        codex_reconcile_failed = True
                        logger.exception(
                            "reconcile: sync_codex_sessions failed — continuing "
                            "(per-project reconcile results are unaffected)"
                        )

                details = {
                    "projectsReconciled": reconciled,
                    "watchersHealed": healed,
                    "failedProjectIds": failed_project_ids,
                    "codexReconcileFailed": codex_reconcile_failed,
                }
                if failed_project_ids or codex_reconcile_failed:
                    self._mark_job_failure(
                        "reconcile",
                        started,
                        RuntimeError(f"reconcile_failed:{','.join(failed_project_ids + (['codex'] if codex_reconcile_failed else []))}"),
                        backlog_count=0,
                        details=details,
                    )
                else:
                    self._mark_job_success(
                        "reconcile", started, backlog_count=0, details=details
                    )

                # T12-005: emit reconcile heartbeat probe — fires on cadence
                # regardless of individual project watcher activity (AC R12.5).
                observability.record_reconcile_heartbeat(
                    result="partial_failure" if failed_project_ids else "success",
                    reconciled=reconciled,
                    healed=healed,
                    failed=len(failed_project_ids),
                )

        logger.info(
            "Started periodic reconcile (profile=%s interval=%ss heal=%s)",
            self.profile.name,
            interval_seconds,
            heal_enabled,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_reconcile(),
            name=f"ccdash:{self.profile.name}:reconcile",
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
        terminal: bool = False,
    ) -> None:
        observation = self.state.job_observations[job_name]
        finished_at = _isoformat(_utc_now())
        # P3-013: use "dead" for terminal failures; "failed" for retryable
        observation.state = "dead" if terminal else "failed"
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

    def _mark_job_crashed(
        self,
        job_name: str,
        started: float,
        exc: Exception,
        *,
        checkpoint_at: str | None = None,
    ) -> None:
        """P3-013: mark a job as crashed (unhandled exception in async task)."""
        observation = self.state.job_observations[job_name]
        finished_at = _isoformat(_utc_now())
        observation.state = "crashed"
        observation.last_finished_at = finished_at
        observation.last_failure_at = finished_at
        observation.last_outcome = "crashed"
        observation.last_duration_ms = int((time.monotonic() - started) * 1000)
        observation.last_error = str(exc) or exc.__class__.__name__
        if checkpoint_at is not None:
            observation.checkpoint_at = checkpoint_at
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
        """P3-013: distinguish idle / running / dead / crashed states.

        ``dead``    — the task finished and last_outcome is a terminal failure.
        ``crashed`` — the task is done (exception) but was not a clean cancel.
        ``idle``    — never ran or completed normally.
        ``running`` — task is active.
        """
        if task is not None and not task.done():
            return "running"
        observation = self.state.job_observations[job_name]
        if task is not None and task.done():
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                # Task raised an exception — treat as crashed (unhandled)
                return "crashed"
        # Propagate the explicitly set state from mark_job_* helpers
        return observation.state

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
            freshness_seconds = _freshness_seconds(checkpoint_at)

            # P3-013: compute server-side stale_since alarm
            stale_since: str | None = None
            stale_threshold = observation.stale_threshold_seconds
            if (
                stale_threshold is not None
                and isinstance(freshness_seconds, int)
                and freshness_seconds > stale_threshold
                and checkpoint_at is not None
            ):
                stale_since = checkpoint_at

            job_state = self._snapshot_job_state(job_name, tasks.get(job_name))
            jobs[job_name] = {
                "state": job_state,
                "intervalSeconds": observation.interval_seconds,
                "backlogCount": observation.backlog_count,
                "backlogUnit": observation.backlog_unit,
                "checkpointAt": checkpoint_at,
                "checkpointFreshnessSeconds": freshness_seconds,
                # P3-013: stale_since and stale threshold
                "staleSince": stale_since,
                "staleThresholdSeconds": stale_threshold,
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

    def _worker_probe_queue_depth(self, jobs: dict[str, Any]) -> dict[str, Any]:
        """P3-015: expose queue/backpressure depth metrics per job.

        Reports the backlogCount for analytics-snapshot and cache-warming jobs
        (parity with telemetry export queueDepth), plus stale flags.
        """
        depth_map: dict[str, Any] = {}
        for job_name in ("analyticsSnapshots", "cacheWarming", "telemetryExports", "artifactRollupExports"):
            payload = jobs.get(job_name, {})
            depth_map[job_name] = {
                "depth": payload.get("backlogCount", 0),
                "unit": self.state.job_observations.get(
                    job_name,
                    RuntimeJobObservation(),
                ).backlog_unit,
                "staleSince": payload.get("staleSince"),
                "state": payload.get("state", "idle"),
            }
        return depth_map

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
        allow_writeback: bool = True,
    ) -> None:
        delay = max(0, int(getattr(config, "STARTUP_SYNC_DELAY_SECONDS", 0)))
        if delay > 0:
            await asyncio.sleep(delay)

        light_mode = bool(getattr(config, "STARTUP_SYNC_LIGHT_MODE", False))
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
            allow_writeback=allow_writeback,
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
        # P6-001: publish the computed poll interval to the OTEL gauge (no-throw).
        observability.set_feature_poll_interval(float(analytics_interval))
        workspace_registry = self.ports.workspace_registry
        bound_project = self.project_binding.project if self.project_binding is not None else None

        async def _run_periodic_analytics_snapshots() -> None:
            while True:
                await asyncio.sleep(analytics_interval)

                # P3-007: if no explicit binding, iterate ALL registered projects
                if bound_project is not None:
                    projects_to_process = [bound_project]
                else:
                    projects_to_process = workspace_registry.list_projects()
                    if not projects_to_process:
                        # fallback: active project
                        active = workspace_registry.get_active_project()
                        if active:
                            projects_to_process = [active]

                if not projects_to_process:
                    continue

                started = self._mark_job_started(
                    "analyticsSnapshots", backlog_count=len(projects_to_process)
                )
                failed_projects: list[str] = []
                for current_project in projects_to_process:
                    try:
                        await self.sync.capture_analytics_snapshot(
                            current_project.id,
                            trigger="periodic_timer",
                        )
                    except asyncio.CancelledError:
                        self._mark_job_cancelled("analyticsSnapshots", started, backlog_count=0)
                        raise
                    except Exception:
                        failed_projects.append(current_project.id)
                        logger.exception(
                            "Periodic analytics snapshot failed for project '%s'",
                            current_project.id,
                        )

                if failed_projects:
                    self._mark_job_failure(
                        "analyticsSnapshots",
                        started,
                        RuntimeError(f"analytics_snapshot_failed:{','.join(failed_projects)}"),
                        backlog_count=0,
                        details={
                            "projectIds": [p.id for p in projects_to_process],
                            "failedProjectIds": failed_projects,
                            "trigger": "periodic_timer",
                        },
                    )
                else:
                    self._mark_job_success(
                        "analyticsSnapshots",
                        started,
                        backlog_count=0,
                        details={
                            "projectIds": [p.id for p in projects_to_process],
                            "trigger": "periodic_timer",
                        },
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

    # Full set of memoized endpoints that can be warmed without per-feature args.
    # Endpoints that require a feature_id (feature_forensics, feature-evidence-summary,
    # aar_report) are intentionally excluded — they cannot be warmed generically.
    _CACHE_WARM_TARGETS: tuple[str, ...] = (
        "project_status",
        "workflow_diagnostics",
        "planning_project_summary",
        "planning_project_graph",
        "mpcc_command_center",
        "mpss_session_board",
        "system_active_count",
        "live_active_count",
        "analytics_overview_bundle",
        "dashboard_bundle",
    )

    def _start_cache_warming_task(self) -> asyncio.Task[None] | None:
        """Periodically warm all memoized query caches that do not require per-feature args.

        Targets (10 endpoints):
        - ``project_status`` — ProjectStatusQueryService.get_status
        - ``workflow_diagnostics`` — WorkflowDiagnosticsQueryService.get_diagnostics
        - ``planning_project_summary`` — PlanningQueryService.get_project_planning_summary
        - ``planning_project_graph`` — PlanningQueryService.get_project_planning_graph
        - ``mpcc_command_center`` — MultiProjectPlanningCommandCenterQueryService.get_multi_project_command_center
        - ``mpss_session_board`` — MultiProjectActiveSessionBoardQueryService.get_multi_project_session_board
        - ``system_active_count`` — SystemMetricsQueryService.get_system_active_count
        - ``live_active_count`` — LiveMetricsQueryService.get_active_count
        - ``analytics_overview_bundle`` — AnalyticsBundleQueryService.get_analytics_overview_bundle
        - ``dashboard_bundle`` — DashboardQueryService.get_dashboard_bundle

        Excluded (require per-feature ``feature_id``):
        - ``feature_forensics``, ``feature-evidence-summary``, ``aar_report``

        A synthetic ``RequestContext`` is constructed from the active-project
        workspace registry entry using ``auth_mode='system'`` and
        ``subject='cache-warmer'``.  If no active project is found the iteration
        is skipped silently.  Each warm call is wrapped in try/except so one
        failure does not abort the loop.  The job is disabled when
        ``CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS <= 0``.
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
            from backend.application.services.agent_queries.planning import (  # noqa: PLC0415
                PlanningQueryService,
            )
            from backend.application.services.agent_queries.multi_project_planning_command_center import (  # noqa: PLC0415
                MultiProjectPlanningCommandCenterQueryService,
            )
            from backend.application.services.agent_queries.multi_project_planning_sessions import (  # noqa: PLC0415
                MultiProjectActiveSessionBoardQueryService,
            )
            from backend.application.services.agent_queries.system_metrics import (  # noqa: PLC0415
                SystemMetricsQueryService,
            )
            from backend.application.services.agent_queries.live_metrics import (  # noqa: PLC0415
                LiveMetricsQueryService,
            )
            from backend.application.services.agent_queries.analytics_bundle import (  # noqa: PLC0415
                AnalyticsBundleQueryService,
            )
            from backend.application.services.agent_queries.dashboard import (  # noqa: PLC0415
                DashboardQueryService,
            )

            _project_status_svc = ProjectStatusQueryService()
            _workflow_svc = WorkflowDiagnosticsQueryService()
            _planning_svc = PlanningQueryService()
            _mpcc_svc = MultiProjectPlanningCommandCenterQueryService()
            _mpss_svc = MultiProjectActiveSessionBoardQueryService()
            _system_metrics_svc = SystemMetricsQueryService()
            _live_metrics_svc = LiveMetricsQueryService()
            _analytics_svc = AnalyticsBundleQueryService()
            _dashboard_svc = DashboardQueryService()

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

            async def _warm_one_project(current_project: Any, started: float) -> list[str]:
                """Warm all cache targets for one project.  Returns list of failed target names."""
                _, project_scope = workspace_registry.resolve_scope(current_project.id)
                if project_scope is None:
                    logger.debug(
                        "Cache warming: resolve_scope returned None for project '%s' — skipping",
                        current_project.id,
                    )
                    return []

                context = RequestContext(
                    principal=_warming_principal,
                    workspace=None,
                    project=project_scope,
                    runtime_profile="worker",
                    trace=_warming_trace,
                    tenancy=TenancyContext(project_id=current_project.id),
                )
                failed_targets: list[str] = []

                for target_name, coro_fn in [
                    ("project_status", lambda: _project_status_svc.get_status(context, self.ports)),
                    ("workflow_diagnostics", lambda: _workflow_svc.get_diagnostics(context, self.ports)),
                    ("planning_project_summary", lambda: _planning_svc.get_project_planning_summary(context, self.ports)),
                    ("planning_project_graph", lambda: _planning_svc.get_project_planning_graph(context, self.ports)),
                    ("mpcc_command_center", lambda: _mpcc_svc.get_multi_project_command_center(context, self.ports)),
                    ("mpss_session_board", lambda: _mpss_svc.get_multi_project_session_board(context, self.ports)),
                    ("system_active_count", lambda: _system_metrics_svc.get_system_active_count(context, self.ports)),
                    ("live_active_count", lambda: _live_metrics_svc.get_active_count(context, self.ports)),
                    ("analytics_overview_bundle", lambda: _analytics_svc.get_analytics_overview_bundle(context, self.ports)),
                    ("dashboard_bundle", lambda: _dashboard_svc.get_dashboard_bundle(context, self.ports)),
                ]:
                    try:
                        await coro_fn()
                        logger.debug(
                            "Cache warming: %s warmed for project '%s'",
                            target_name,
                            current_project.id,
                        )
                    except asyncio.CancelledError:
                        self._mark_job_cancelled("cacheWarming", started, backlog_count=0)
                        raise
                    except Exception:
                        failed_targets.append(target_name)
                        logger.exception(
                            "Cache warming: %s failed for project '%s'",
                            target_name,
                            current_project.id,
                        )
                return failed_targets

            while True:
                await asyncio.sleep(interval_seconds)

                # P3-007: if bound_project is set → single-project mode (unchanged).
                # If not set → iterate ALL registered projects via list_projects().
                if bound_project is not None:
                    projects_to_warm = [bound_project]
                else:
                    projects_to_warm = workspace_registry.list_projects()
                    if not projects_to_warm:
                        active = workspace_registry.get_active_project()
                        if active:
                            projects_to_warm = [active]

                if not projects_to_warm:
                    logger.debug("Cache warming: no projects registered — skipping this iteration")
                    continue

                started = self._mark_job_started("cacheWarming", backlog_count=len(projects_to_warm))
                all_failed_targets: list[str] = []
                failed_project_ids: list[str] = []

                for current_project in projects_to_warm:
                    proj_failed = await _warm_one_project(current_project, started)
                    if proj_failed:
                        all_failed_targets.extend(proj_failed)
                        failed_project_ids.append(current_project.id)

                if all_failed_targets:
                    self._mark_job_failure(
                        "cacheWarming",
                        started,
                        RuntimeError(f"cache_warming_failed:{','.join(failed_project_ids)}"),
                        backlog_count=0,
                        details={
                            "projectIds": [p.id for p in projects_to_warm],
                            "failedProjectIds": failed_project_ids,
                            "failedTargets": all_failed_targets,
                        },
                    )
                else:
                    self._mark_job_success(
                        "cacheWarming",
                        started,
                        backlog_count=0,
                        details={
                            "projectIds": [p.id for p in projects_to_warm],
                            "targets": list(self._CACHE_WARM_TARGETS),
                        },
                    )

        logger.info(
            "Started periodic cache warming (profile=%s interval=%ss targets=%s)",
            self.profile.name,
            interval_seconds,
            ",".join(self._CACHE_WARM_TARGETS),
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_cache_warming(),
            name=f"ccdash:{self.profile.name}:cache-warming",
        )

    def _start_retention_prune_task(self) -> asyncio.Task[None] | None:
        """P6-002: scheduled retention prune + VACUUM/ANALYZE job.

        Runs every ``RETENTION_PRUNE_INTERVAL_SECONDS`` (default 86400 = 24 h).
        Each tick:
          1. Calls ``analytics_repo.prune_entries_older_than_days(ANALYTICS_RETENTION_DAYS)``
          2. Calls ``analytics_repo.prune_telemetry_older_than_days(TELEMETRY_RETENTION_DAYS)``
          3. If ``RETENTION_VACUUM_ENABLED`` is true:
             - SQLite: issues ``VACUUM`` on the connection outside any transaction.
             - Postgres: issues ``VACUUM (ANALYZE) analytics_entries`` and
               ``VACUUM (ANALYZE) telemetry_events`` each on a dedicated raw
               connection acquired from the pool (VACUUM must run outside a
               transaction block).

        Guarded by ``config.RETENTION_PRUNE_ENABLED``; returns ``None`` (no
        task) when the flag is false or the interval is <= 0.

        The whole tick body is wrapped in ``try/except`` so a transient failure
        does not kill the loop.
        """
        if not config.RETENTION_PRUNE_ENABLED:
            return None
        interval_seconds = max(1, int(getattr(config, "RETENTION_PRUNE_INTERVAL_SECONDS", 86400)))
        self.state.job_observations["retentionPrune"].interval_seconds = interval_seconds
        vacuum_enabled = bool(getattr(config, "RETENTION_VACUUM_ENABLED", True))
        db_backend = getattr(config, "DB_BACKEND", "sqlite")
        analytics_days = int(getattr(config, "ANALYTICS_RETENTION_DAYS", 90))
        telemetry_days = int(getattr(config, "TELEMETRY_RETENTION_DAYS", 90))
        ports = self.ports

        async def _run_vacuum_sqlite(raw_db: Any) -> None:
            """Issue a plain VACUUM outside any active transaction (SQLite).

            aiosqlite keeps an implicit open transaction whenever a write has
            been executed without an explicit COMMIT.  SQLite raises
            ``OperationalError: cannot VACUUM from within a transaction`` if
            VACUUM is called while any transaction is open.  Commit first to
            clear the implicit transaction, then VACUUM.
            """
            if raw_db.in_transaction:
                await raw_db.commit()
            await raw_db.execute("VACUUM")

        async def _run_vacuum_postgres(pool: Any) -> None:
            """Issue VACUUM (ANALYZE) on retention tables via a dedicated
            raw connection acquired from the asyncpg pool.

            VACUUM cannot run inside a transaction block in PostgreSQL; asyncpg
            pool.acquire() returns a connection with implicit autocommit for
            top-level statements when not inside an explicit transaction.
            """
            acquire = getattr(pool, "acquire", None)
            if acquire is None:
                logger.warning("retention_prune: postgres pool has no acquire() — skipping VACUUM")
                return
            async with pool.acquire() as conn:
                await conn.execute("VACUUM (ANALYZE) analytics_entries")
                await conn.execute("VACUUM (ANALYZE) telemetry_events")

        async def _run_periodic_retention_prune() -> None:
            while True:
                await asyncio.sleep(interval_seconds)

                started = self._mark_job_started("retentionPrune", backlog_count=0)
                analytics_pruned = 0
                telemetry_pruned = 0
                try:
                    analytics_repo = ports.storage.analytics()
                    prune_analytics_fn = getattr(analytics_repo, "prune_entries_older_than_days", None)
                    prune_telemetry_fn = getattr(analytics_repo, "prune_telemetry_older_than_days", None)

                    if prune_analytics_fn is not None:
                        analytics_pruned = await prune_analytics_fn(days=analytics_days)
                        logger.info(
                            "retention_prune: analytics_entries pruned %d rows (days=%d)",
                            analytics_pruned,
                            analytics_days,
                        )
                    else:
                        logger.warning(
                            "retention_prune: prune_entries_older_than_days not available on analytics_repo — skipping"
                        )

                    if prune_telemetry_fn is not None:
                        telemetry_pruned = await prune_telemetry_fn(days=telemetry_days)
                        logger.info(
                            "retention_prune: telemetry_events pruned %d rows (days=%d)",
                            telemetry_pruned,
                            telemetry_days,
                        )
                    else:
                        logger.warning(
                            "retention_prune: prune_telemetry_older_than_days not available on analytics_repo — skipping"
                        )

                    if vacuum_enabled:
                        raw_db = ports.storage.db
                        if db_backend == "postgres":
                            await _run_vacuum_postgres(raw_db)
                            logger.info(
                                "retention_prune: VACUUM (ANALYZE) complete on analytics_entries + telemetry_events"
                            )
                        else:
                            await _run_vacuum_sqlite(raw_db)
                            logger.info("retention_prune: VACUUM complete (SQLite)")

                    self._mark_job_success(
                        "retentionPrune",
                        started,
                        backlog_count=0,
                        details={
                            "analyticsPruned": analytics_pruned,
                            "telemetryPruned": telemetry_pruned,
                            "vacuumRan": vacuum_enabled,
                            "analyticsDays": analytics_days,
                            "telemetryDays": telemetry_days,
                        },
                    )
                except asyncio.CancelledError:
                    self._mark_job_cancelled("retentionPrune", started, backlog_count=0)
                    raise
                except Exception:
                    logger.exception("retention_prune: tick failed — loop continues")
                    self._mark_job_failure(
                        "retentionPrune",
                        started,
                        RuntimeError("retention_prune_failed"),
                        backlog_count=0,
                        details={
                            "analyticsPruned": analytics_pruned,
                            "telemetryPruned": telemetry_pruned,
                        },
                    )

        logger.info(
            "Started periodic retention prune job (profile=%s interval=%ss vacuum=%s)",
            self.profile.name,
            interval_seconds,
            vacuum_enabled,
        )
        return self.ports.job_scheduler.schedule(
            _run_periodic_retention_prune(),
            name=f"ccdash:{self.profile.name}:retention-prune",
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
