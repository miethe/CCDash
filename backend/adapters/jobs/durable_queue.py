"""Durable job queue scheduler (P3-006).

Provides a ``DurableJobScheduler`` that satisfies the ``JobScheduler``
port (``backend/application/ports/core.py``).  Backend selection is
governed by the ``JOB_QUEUE_BACKEND`` config flag (read defensively so
tests are green regardless of whether the config owner has landed yet):

    ``memory``   → in-process asyncio tasks (InProcessJobScheduler, default)
    ``postgres`` → Postgres-backed durable queue (future; falls back to
                   in-process with a warning until fully wired)
    ``sqlite``   → SQLite-backed durable queue (uses job_queue table from
                   SCHEMA_VERSION 30)

The ``DurableJobScheduler`` wraps the underlying scheduler and exposes
additional queue-depth metrics so P3-015 can surface backpressure without
touching any other module.

Crash-resume strategy
─────────────────────
When a container restarts while a job is ``running`` the job remains in
that status in the DB.  On next startup the scheduler calls
``SqliteJobQueueRepository.reclaim_crashed()`` to pick up where it left
off, using the ``checkpoint`` column to resume from a known-good state.
The caller (sync_engine) must persist checkpoints at safe points via
``save_checkpoint()``.

Backpressure
────────────
``DurableJobScheduler.queue_depth()`` returns pending + running counts
that runtime.py surfaces via P3-015.

Interface compatibility
───────────────────────
``DurableJobScheduler.schedule(job, *, name)`` delegates directly to the
underlying in-process scheduler (asyncio.create_task) so the existing
``schedule()`` call-sites in runtime.py keep working unchanged.  The
durable path is opt-in: callers that want durable enqueue call
``enqueue_durable()`` explicitly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable

from backend.adapters.jobs.local import InProcessJobScheduler

logger = logging.getLogger("ccdash.jobs.durable_queue")

# ── DurableJobScheduler ──────────────────────────────────────────────────────


class DurableJobScheduler:
    """JobScheduler wrapper that optionally persists jobs to the DB.

    Parameters
    ----------
    db:
        Async DB connection (aiosqlite or asyncpg-compatible).  When
        ``None`` the scheduler runs purely in-process.
    backend:
        ``"memory"`` (default), ``"sqlite"``, or ``"postgres"``.
    worker_id:
        Identifies this container for claim / lock ownership.
    max_in_flight:
        Backpressure cap — ``claim()`` returns None once this many running
        jobs are held by this worker.
    """

    def __init__(
        self,
        db: Any | None = None,
        *,
        backend: str = "memory",
        worker_id: str = "default-worker",
        max_in_flight: int = 5,
    ) -> None:
        self._db = db
        self._backend = backend
        self._worker_id = worker_id
        self._max_in_flight = max_in_flight
        self._in_process = InProcessJobScheduler()
        self._repo: Any | None = None  # lazily initialised

        if backend not in ("memory", "sqlite", "postgres"):
            logger.warning(
                "Unknown JOB_QUEUE_BACKEND '%s' — falling back to in-process",
                backend,
            )
            self._backend = "memory"

    # ── JobScheduler port interface ──────────────────────────────────────────

    def schedule(self, job: Awaitable[Any], *, name: str | None = None) -> asyncio.Task[Any]:
        """Schedule an in-process asyncio task (existing call-sites are unchanged)."""
        return self._in_process.schedule(job, name=name)

    # ── Durable path (opt-in by callers that want persistence) ───────────────

    async def enqueue_durable(
        self,
        job_type: str,
        payload: dict[str, Any],
        project_id: str,
        *,
        priority: int = 0,
        max_attempts: int = 3,
        available_at: str | None = None,
        job_id: str | None = None,
    ) -> str | None:
        """Persist a job to the durable queue.  Returns job_id or None if
        running in memory-only mode."""
        repo = self._get_repo()
        if repo is None:
            return None
        return await repo.enqueue(
            job_type,
            payload,
            project_id,
            priority=priority,
            max_attempts=max_attempts,
            available_at=available_at,
            job_id=job_id,
        )

    async def claim_next(
        self,
        job_type: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Claim the next pending job.  Returns job dict or None."""
        repo = self._get_repo()
        if repo is None:
            return None
        return await repo.claim(
            job_type,
            project_id,
            worker_id=self._worker_id,
            max_in_flight=self._max_in_flight,
        )

    async def complete_job(self, job_id: str) -> None:
        repo = self._get_repo()
        if repo is not None:
            await repo.complete(job_id)

    async def fail_job(
        self,
        job_id: str,
        error: str,
        *,
        checkpoint: str | None = None,
    ) -> None:
        repo = self._get_repo()
        if repo is not None:
            await repo.fail(job_id, error, checkpoint=checkpoint)

    async def checkpoint_job(self, job_id: str, checkpoint: str) -> None:
        repo = self._get_repo()
        if repo is not None:
            await repo.save_checkpoint(job_id, checkpoint)

    async def reclaim_crashed(self) -> dict[str, Any] | None:
        """Reclaim a crashed job for crash-resume on startup."""
        repo = self._get_repo()
        if repo is None:
            return None
        return await repo.reclaim_crashed(
            self._worker_id,
            max_in_flight=self._max_in_flight,
        )

    # ── Queue depth / backpressure metrics (P3-015) ───────────────────────────

    async def queue_depth(
        self,
        project_id: str | None = None,
        job_type: str | None = None,
        status: str = "pending",
    ) -> int:
        """Return the number of jobs in *status* for backpressure metrics."""
        repo = self._get_repo()
        if repo is None:
            return 0
        return await repo.depth(project_id, job_type, status=status)

    async def queue_depth_by_status(
        self,
        project_id: str | None = None,
    ) -> dict[str, int]:
        """Return counts keyed by status (pending/running/done/dead/crashed)."""
        repo = self._get_repo()
        if repo is None:
            return {}
        return await repo.depth_by_status(project_id)

    # ── Drain loop (consumer) ─────────────────────────────────────────────────

    def start_drain_loop(
        self,
        executors: dict[str, Any],
        *,
        poll_interval: float = 2.0,
        reclaim_on_start: bool = True,
    ) -> "asyncio.Task[None] | None":
        """Start an asyncio drain-loop task that claims and executes durable jobs.

        The drain loop is the consumer side of the durable queue.  Periodic
        scheduler calls remain the producers (they call ``enqueue_durable()``).
        Only active when backend != 'memory'; returns None in memory mode so
        callers can skip the task reference safely.

        Parameters
        ----------
        executors:
            Mapping from ``job_type`` string to an async callable
            ``executor(job: dict) -> None``.  The callable receives the
            full job dict (including ``payload`` and ``checkpoint``).
        poll_interval:
            Seconds to sleep between drain ticks when the queue is empty.
        reclaim_on_start:
            If True, attempt to reclaim crashed jobs immediately on first tick
            (handles container-restart crash-resume).
        """
        if self._backend == "memory" or self._get_repo() is None:
            return None

        scheduler = self

        async def _drain_loop() -> None:
            first_tick = True
            while True:
                try:
                    # On startup: reclaim any jobs that were running when the
                    # previous container crashed (crash-resume).
                    if first_tick and reclaim_on_start:
                        first_tick = False
                        job = await scheduler.reclaim_crashed()
                        if job is not None:
                            logger.info(
                                "Drain-loop reclaimed crashed job id=%s type=%s checkpoint=%s",
                                job.get("id"),
                                job.get("job_type"),
                                job.get("checkpoint"),
                            )
                            await _execute_job(job)
                            continue  # go again immediately before sleeping
                        first_tick = False

                    # Claim and execute the next pending job.
                    job = await scheduler.claim_next()
                    if job is None:
                        await asyncio.sleep(poll_interval)
                        continue

                    await _execute_job(job)

                except asyncio.CancelledError:
                    logger.info("Drain-loop task cancelled — shutting down")
                    raise
                except Exception:
                    logger.exception("Drain-loop tick raised unexpectedly — continuing")
                    await asyncio.sleep(poll_interval)

        async def _execute_job(job: dict[str, Any]) -> None:
            job_id = job.get("id", "?")
            job_type = job.get("job_type", "unknown")
            executor = executors.get(job_type)
            if executor is None:
                logger.warning(
                    "Drain-loop: no executor for job_type=%s id=%s — marking dead",
                    job_type,
                    job_id,
                )
                await scheduler.fail_job(job_id, f"no executor for job_type={job_type}")
                return
            try:
                logger.debug("Drain-loop executing job id=%s type=%s", job_id, job_type)
                await executor(job)
                await scheduler.complete_job(job_id)
                logger.info("Drain-loop completed job id=%s type=%s", job_id, job_type)
            except asyncio.CancelledError:
                # Save checkpoint if executor set one, then propagate.
                await scheduler.fail_job(job_id, "cancelled")
                raise
            except Exception as exc:
                err = str(exc)
                logger.warning(
                    "Drain-loop job id=%s type=%s failed: %s",
                    job_id,
                    job_type,
                    err,
                )
                await scheduler.fail_job(job_id, err)

        return self._in_process.schedule(_drain_loop(), name="ccdash:durable:drain-loop")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_repo(self) -> Any | None:
        """Return the repository, lazily constructing it on first access."""
        if self._backend == "memory" or self._db is None:
            return None
        if self._repo is not None:
            return self._repo
        if self._backend == "sqlite":
            from backend.db.repositories.job_queue import (  # noqa: PLC0415
                SqliteJobQueueRepository,
            )
            self._repo = SqliteJobQueueRepository(self._db)
        elif self._backend == "postgres":
            # P3-006-FU: asyncpg-backed Postgres repository (live dispatch path).
            from backend.db.repositories.postgres.job_queue import (  # noqa: PLC0415
                PostgresJobQueueRepository,
            )
            self._repo = PostgresJobQueueRepository(self._db)
        return self._repo


def make_durable_scheduler(
    db: Any | None,
    *,
    backend: str | None = None,
    worker_id: str = "default-worker",
    max_in_flight: int = 5,
) -> DurableJobScheduler:
    """Factory: read JOB_QUEUE_BACKEND from config defensively and return
    a configured DurableJobScheduler.

    ``backend`` kwarg overrides config (useful in tests).
    """
    if backend is None:
        try:
            from backend import config as _cfg  # noqa: PLC0415
            backend = getattr(_cfg, "JOB_QUEUE_BACKEND", "memory")
        except Exception:  # pragma: no cover
            backend = "memory"

    return DurableJobScheduler(
        db,
        backend=str(backend),
        worker_id=worker_id,
        max_in_flight=max_in_flight,
    )
