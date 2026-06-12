"""T9-007: Durable-queue coalescing validation under JOB_QUEUE_BACKEND=postgres.

Covers AC 7.2 (durable-queue coalescing guard) for the Postgres job-queue
backend.  Tests verify that:

  * When a job is already pending/running for (project_id, job_type), concurrent
    and sequential enqueue_durable_idempotent calls are coalesced (return None).
  * Two DIFFERENT project IDs are keyed independently: coalescing for
    project A does not suppress a new job for project B.
  * Log-level dedup events are emitted for each coalesced call.

Design note on the "concurrent" scenario:
  The coalescing check (depth > 0 → return None) is an async check-then-act
  pattern.  In CPython asyncio it is NOT atomic — all concurrent coroutines
  can observe depth=0 before any enqueue fires.  The coalescing guard therefore
  protects against SEQUENTIAL duplicate dispatches (e.g. watcher fires twice for
  the same file), not truly concurrent DB-level races (which require DB-level
  locking or advisory locks).  Tests reflect this contract:
    • "job already in queue" (depth=1 initial) → any call is coalesced
    • "queue empty" (depth=0) → enqueue proceeds; subsequent SEQUENTIAL calls
      with depth=1 are coalesced

Non-PG half (always runs):
  Uses a mock repository; no real DB required.

PG-gated half:
  Skipped when CCDASH_DATABASE_URL is not set.  Run against compose PG to
  validate live Postgres job_queue table behavior.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_pg_coalescing.py -v
"""
from __future__ import annotations

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PG_URL = os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres coalescing test requires a running "
    "Postgres instance (e.g. via docker compose up --profile postgres)."
)


def _make_mock_repo_with_depth(depth: int, enqueue_return: str = "job-id-1") -> MagicMock:
    """Mock repo where depth() always returns *depth*."""
    repo = MagicMock()
    repo.depth = AsyncMock(return_value=depth)
    repo.enqueue = AsyncMock(return_value=enqueue_return)
    return repo


def _make_scheduler_with_repo(repo: MagicMock) -> "DurableJobScheduler":
    """Build a DurableJobScheduler with an injected mock repo (bypasses _get_repo lazy init)."""
    from backend.adapters.jobs.durable_queue import DurableJobScheduler
    from backend.adapters.jobs.local import InProcessJobScheduler

    scheduler = DurableJobScheduler.__new__(DurableJobScheduler)
    scheduler._db = MagicMock()       # truthy so _get_repo() doesn't early-exit
    scheduler._backend = "sqlite"     # non-memory so _get_repo() doesn't early-exit
    scheduler._worker_id = "test-worker"
    scheduler._max_in_flight = 5
    scheduler._in_process = InProcessJobScheduler()
    scheduler._repo = repo            # inject directly; _get_repo() returns this
    return scheduler


# ---------------------------------------------------------------------------
# Unit tests (no live PG required)
# ---------------------------------------------------------------------------

class DurableQueueCoalescingTests(unittest.IsolatedAsyncioTestCase):
    """Non-PG coalescing guard unit tests using a mock repository.

    Tests the enqueue_durable_idempotent logic in DurableJobScheduler without
    any live database connection.
    """

    # ── coalescing when job already exists (depth=1) ─────────────────────────

    async def test_coalesces_when_job_already_pending(self) -> None:
        """When a pending job already exists, idempotent enqueue returns None."""
        repo = _make_mock_repo_with_depth(depth=1)
        scheduler = _make_scheduler_with_repo(repo)

        result = await scheduler.enqueue_durable_idempotent(
            "full_sync", {"path": "/p1"}, "proj-alpha"
        )
        self.assertIsNone(result, "Should be coalesced when pending depth=1")
        repo.enqueue.assert_not_called()

    async def test_coalesces_when_job_already_running(self) -> None:
        """When a running job already exists, idempotent enqueue returns None."""
        repo = MagicMock()
        # pending=0, running=1
        async def _depth(project_id: str, job_type: str, status: str) -> int:  # noqa: A002
            return 1 if status == "running" else 0
        repo.depth = AsyncMock(side_effect=_depth)
        repo.enqueue = AsyncMock(return_value="x")
        scheduler = _make_scheduler_with_repo(repo)

        result = await scheduler.enqueue_durable_idempotent(
            "full_sync", {"path": "/p1"}, "proj-alpha"
        )
        self.assertIsNone(result, "Should be coalesced when running depth=1")
        repo.enqueue.assert_not_called()

    async def test_concurrent_coalesced_when_job_already_in_queue(self) -> None:
        """Multiple concurrent calls with an existing job must all be coalesced."""
        # Depth=1 from the start — job is already in queue
        repo = _make_mock_repo_with_depth(depth=1)
        scheduler = _make_scheduler_with_repo(repo)

        results = await asyncio.gather(*[
            scheduler.enqueue_durable_idempotent("full_sync", {}, "proj-alpha")
            for _ in range(5)
        ])
        self.assertTrue(
            all(r is None for r in results),
            msg="All concurrent calls should be coalesced when job already exists",
        )
        repo.enqueue.assert_not_called()

    # ── successful enqueue when queue is empty ───────────────────────────────

    async def test_enqueues_when_queue_empty(self) -> None:
        """When the queue is empty (depth=0), a job should be enqueued."""
        repo = _make_mock_repo_with_depth(depth=0, enqueue_return="job-new")
        scheduler = _make_scheduler_with_repo(repo)

        result = await scheduler.enqueue_durable_idempotent(
            "full_sync", {"path": "/p1"}, "proj-beta"
        )
        self.assertIsNotNone(result, "Should enqueue when queue is empty")
        self.assertEqual(result, "job-new")
        repo.enqueue.assert_called_once()

    async def test_sequential_first_enqueues_second_coalesces(self) -> None:
        """Sequential calls: first call enqueues (depth=0); then depth=1; second coalesces."""
        call_count = {"depth": 0}

        async def _depth(project_id: str, job_type: str, status: str) -> int:  # noqa: A002
            # First 2 calls (pending + running for first invocation): depth=0
            # Subsequent calls: depth=1 (job is now in queue)
            n = call_count["depth"]
            call_count["depth"] += 1
            return 0 if n < 2 else 1

        repo = MagicMock()
        repo.depth = AsyncMock(side_effect=_depth)
        repo.enqueue = AsyncMock(return_value="job-seq")
        scheduler = _make_scheduler_with_repo(repo)

        r1 = await scheduler.enqueue_durable_idempotent("sync", {}, "proj-seq")
        r2 = await scheduler.enqueue_durable_idempotent("sync", {}, "proj-seq")

        self.assertIsNotNone(r1, "First call should enqueue (queue was empty)")
        self.assertIsNone(r2, "Second call should be coalesced (job now in queue)")
        repo.enqueue.assert_called_once()

    # ── two different project IDs are keyed independently ────────────────────

    async def test_two_projects_enqueue_independently(self) -> None:
        """Coalescing is project_id-keyed: empty queues for BOTH projects enqueue separately."""
        repo_a = _make_mock_repo_with_depth(depth=0, enqueue_return="job-a")
        repo_b = _make_mock_repo_with_depth(depth=0, enqueue_return="job-b")

        scheduler_a = _make_scheduler_with_repo(repo_a)
        scheduler_b = _make_scheduler_with_repo(repo_b)

        result_a = await scheduler_a.enqueue_durable_idempotent(
            "full_sync", {"path": "/pa"}, "proj-alpha"
        )
        result_b = await scheduler_b.enqueue_durable_idempotent(
            "full_sync", {"path": "/pb"}, "proj-beta"
        )

        self.assertIsNotNone(result_a, "proj-alpha job should be enqueued")
        self.assertIsNotNone(result_b, "proj-beta job should be enqueued independently")
        repo_a.enqueue.assert_called_once()
        repo_b.enqueue.assert_called_once()

    async def test_project_a_coalesced_project_b_still_enqueues(self) -> None:
        """proj-A coalescing (depth=1) must NOT affect proj-B (depth=0)."""
        repo = MagicMock()
        enqueued = {"project_ids": []}

        async def _depth(project_id: str, job_type: str, status: str) -> int:  # noqa: A002
            return 1 if project_id == "proj-a" else 0

        async def _enqueue(job_type: str, payload: dict, project_id: str, **kwargs) -> str:
            enqueued["project_ids"].append(project_id)
            return f"job-{project_id}"

        repo.depth = AsyncMock(side_effect=_depth)
        repo.enqueue = AsyncMock(side_effect=_enqueue)
        scheduler = _make_scheduler_with_repo(repo)

        r_a = await scheduler.enqueue_durable_idempotent("sync", {}, "proj-a")
        r_b = await scheduler.enqueue_durable_idempotent("sync", {}, "proj-b")

        self.assertIsNone(r_a, "proj-a should be coalesced (depth=1)")
        self.assertIsNotNone(r_b, "proj-b should enqueue independently (depth=0)")
        self.assertNotIn("proj-a", enqueued["project_ids"])
        self.assertIn("proj-b", enqueued["project_ids"])

    # ── log emission for coalesced calls ────────────────────────────────────

    async def test_coalescing_emits_info_log(self) -> None:
        """A coalesced call must emit a structured log at INFO level."""
        repo = _make_mock_repo_with_depth(depth=1)
        scheduler = _make_scheduler_with_repo(repo)

        with self.assertLogs("ccdash.jobs.durable_queue", level=logging.INFO) as log_ctx:
            await scheduler.enqueue_durable_idempotent("sync", {}, "proj-log")

        coalesced_logs = [m for m in log_ctx.output if "coalesced" in m.lower()]
        self.assertGreaterEqual(
            len(coalesced_logs), 1,
            msg="Expected at least one 'coalesced' log entry from deduped dispatch",
        )

    # ── memory backend no-op path ────────────────────────────────────────────

    async def test_memory_backend_returns_none_always(self) -> None:
        """Memory backend: enqueue_durable_idempotent is a no-op returning None."""
        from backend.adapters.jobs.durable_queue import DurableJobScheduler

        scheduler = DurableJobScheduler(db=None, backend="memory", worker_id="w")
        result = await scheduler.enqueue_durable_idempotent("sync", {}, "proj-mem")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# PG-gated live tests
# ---------------------------------------------------------------------------

@unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LivePGCoalescingTests(unittest.IsolatedAsyncioTestCase):
    """Live Postgres coalescing tests — PG-GATED.

    Skipped when CCDASH_DATABASE_URL is not set.  Run against compose PG:
        CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash \\
        backend/.venv/bin/python -m pytest backend/tests/test_pg_coalescing.py \\
          -k "LivePGCoalescingTests" -v
    """

    async def asyncSetUp(self) -> None:
        import asyncpg
        from backend.db.postgres_migrations import run_migrations

        self._pg_pool = await asyncpg.create_pool(_PG_URL)
        await run_migrations(self._pg_pool)

        import uuid as _uuid
        self._run_id = _uuid.uuid4().hex[:8]

    async def asyncTearDown(self) -> None:
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM job_queue WHERE project_id LIKE $1",
                f"pg-coal-{self._run_id}%",
            )
        await self._pg_pool.close()

    async def _make_pg_scheduler(self) -> "DurableJobScheduler":
        from backend.adapters.jobs.durable_queue import DurableJobScheduler
        from backend.db.repositories.postgres.job_queue import PostgresJobQueueRepository
        from backend.adapters.jobs.local import InProcessJobScheduler

        repo = PostgresJobQueueRepository(self._pg_pool)
        scheduler = DurableJobScheduler.__new__(DurableJobScheduler)
        scheduler._db = self._pg_pool
        scheduler._backend = "postgres"
        scheduler._worker_id = "test-worker"
        scheduler._max_in_flight = 5
        scheduler._in_process = InProcessJobScheduler()
        scheduler._repo = repo
        return scheduler

    async def test_live_pg_sequential_coalescing(self) -> None:
        """Under live Postgres: second sequential enqueue is coalesced."""
        scheduler = await self._make_pg_scheduler()
        project_id = f"pg-coal-{self._run_id}-alpha"

        r1 = await scheduler.enqueue_durable_idempotent("sync", {}, project_id)
        r2 = await scheduler.enqueue_durable_idempotent("sync", {}, project_id)

        # First should enqueue, second should be coalesced
        self.assertIsNotNone(r1, "First enqueue should succeed")
        self.assertIsNone(r2, "Second enqueue should be coalesced")

        async with self._pg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM job_queue WHERE project_id = $1 AND status IN ('pending', 'running')",
                project_id,
            )
        self.assertEqual(count, 1, msg="Expected exactly one row in PG job_queue")

    async def test_live_pg_two_projects_enqueue_independently(self) -> None:
        """Two different project IDs each get their own job row in live PG."""
        scheduler = await self._make_pg_scheduler()
        proj_a = f"pg-coal-{self._run_id}-beta"
        proj_b = f"pg-coal-{self._run_id}-gamma"

        r_a = await scheduler.enqueue_durable_idempotent("sync", {}, proj_a)
        r_b = await scheduler.enqueue_durable_idempotent("sync", {}, proj_b)

        self.assertIsNotNone(r_a, f"{proj_a} job should be enqueued")
        self.assertIsNotNone(r_b, f"{proj_b} job should be enqueued independently")

        async with self._pg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM job_queue WHERE project_id = ANY($1::text[])",
                [proj_a, proj_b],
            )
        self.assertEqual(count, 2, msg="Expected two independent rows in PG job_queue")


if __name__ == "__main__":
    unittest.main()
