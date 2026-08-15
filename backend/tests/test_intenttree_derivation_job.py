"""Job-wrapper tests for the M2 scheduler wiring (are-we-winning-dashboard-v1).

Covers ``IntentTreeDerivationJob`` in isolation via fake derivation services
(duck-typed ``derive_all()`` stand-ins) -- this is the job-wrapper unit test
called for by the M2 scheduler-wiring task, deliberately NOT placed in
``test_runtime_bootstrap.py`` (that file hangs on import in this repo).

Run as a named module (full collection can hang in this repo):
    python3 -m pytest backend/tests/test_intenttree_derivation_job.py -v
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from backend import config
from backend.adapters.jobs.intenttree_derivation_job import (
    IntentTreeDerivationJob,
    IntentTreeDerivationJobResult,
)
from backend.runtime.container import _construct_intenttree_derivation_job


@dataclass(slots=True)
class _FakeReopenedResult:
    ok: bool
    candidate_node_ids: list[str] = field(default_factory=list)
    nodes_processed: int = 0
    reopens_written: int = 0
    error: str | None = None


@dataclass(slots=True)
class _FakeSelfCaughtResult:
    ok: bool
    candidate_node_ids: list[str] = field(default_factory=list)
    nodes_processed: int = 0
    buckets_written: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class _FakeReopenedService:
    def __init__(self, result: _FakeReopenedResult) -> None:
        self._result = result
        self.calls = 0

    async def derive_all(self) -> _FakeReopenedResult:
        self.calls += 1
        return self._result


class _FakeSelfCaughtService:
    def __init__(self, result: _FakeSelfCaughtResult) -> None:
        self._result = result
        self.calls = 0

    async def derive_all(self) -> _FakeSelfCaughtResult:
        self.calls += 1
        return self._result


class IntentTreeDerivationJobExecuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_calls_both_services_and_aggregates(self) -> None:
        reopened = _FakeReopenedService(
            _FakeReopenedResult(ok=True, candidate_node_ids=["n1", "n2"], nodes_processed=2, reopens_written=1)
        )
        self_caught = _FakeSelfCaughtService(
            _FakeSelfCaughtResult(ok=True, candidate_node_ids=["n3"], nodes_processed=1)
        )
        job = IntentTreeDerivationJob(reopened, self_caught)

        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        self.assertEqual(reopened.calls, 1)
        self.assertEqual(self_caught.calls, 1)
        self.assertIsInstance(result, IntentTreeDerivationJobResult)
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.reopens_written, 1)
        self.assertEqual(result.self_caught_processed, 1)
        self.assertIsNone(result.error)

    async def test_empty_candidate_sets_are_a_clean_no_op(self) -> None:
        """Tolerance for an empty/partial intent_tree_events cache — the
        exact scenario the M2 scheduler-wiring ordering choice relies on.
        """
        reopened = _FakeReopenedService(_FakeReopenedResult(ok=True))
        self_caught = _FakeSelfCaughtService(_FakeSelfCaughtResult(ok=True))
        job = IntentTreeDerivationJob(reopened, self_caught)

        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.reopens_written, 0)
        self.assertEqual(result.self_caught_processed, 0)

    async def test_reopened_failure_surfaces_as_partial_failure(self) -> None:
        reopened = _FakeReopenedService(_FakeReopenedResult(ok=False, error="boom"))
        self_caught = _FakeSelfCaughtService(_FakeSelfCaughtResult(ok=True))
        job = IntentTreeDerivationJob(reopened, self_caught)

        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        # Fail-soft: the self-caught service still runs even though the
        # reopened derivation failed -- the two are independent.
        self.assertEqual(self_caught.calls, 1)
        self.assertEqual(result.outcome, "partial_failure")
        self.assertEqual(result.error, "boom")

    async def test_self_caught_failure_surfaces_as_partial_failure(self) -> None:
        reopened = _FakeReopenedService(_FakeReopenedResult(ok=True))
        self_caught = _FakeSelfCaughtService(_FakeSelfCaughtResult(ok=False, error="kaboom"))
        job = IntentTreeDerivationJob(reopened, self_caught)

        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        self.assertEqual(reopened.calls, 1)
        self.assertEqual(result.outcome, "partial_failure")
        self.assertEqual(result.error, "kaboom")

    async def test_disabled_flag_short_circuits_before_calling_either_service(self) -> None:
        reopened = _FakeReopenedService(_FakeReopenedResult(ok=True))
        self_caught = _FakeSelfCaughtService(_FakeSelfCaughtResult(ok=True))
        job = IntentTreeDerivationJob(reopened, self_caught)

        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", False):
            result = await job.execute(trigger="scheduled")

        self.assertEqual(reopened.calls, 0)
        self.assertEqual(self_caught.calls, 0)
        self.assertEqual(result.outcome, "disabled")


class ConstructIntentTreeDerivationJobGateTests(unittest.TestCase):
    """Mirrors the existing gate tests one would write for
    ``_construct_intenttree_events_ingest_job`` -- directly unit-testable
    without a live DB or the full ``RuntimeContainer.startup()`` lifecycle
    (that path hangs in this repo's unscoped test collection).
    """

    def test_api_profile_never_constructs_the_job(self) -> None:
        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True), patch.object(
            config, "CCDASH_INTENTTREE_API_URL", "http://intenttree.example.invalid"
        ), patch.object(config, "CCDASH_INTENTTREE_API_TOKEN", "tok"), patch.object(
            config, "CCDASH_INTENTTREE_WORKSPACE_ID", "ws-test"
        ):
            self.assertIsNone(_construct_intenttree_derivation_job("api", db=object()))

    def test_disabled_flag_returns_none_for_worker_profile(self) -> None:
        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", False):
            self.assertIsNone(_construct_intenttree_derivation_job("worker", db=object()))

    def test_missing_config_returns_none_even_when_flag_is_true(self) -> None:
        with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True), patch.object(
            config, "CCDASH_INTENTTREE_API_URL", None
        ):
            self.assertIsNone(_construct_intenttree_derivation_job("worker", db=object()))

    def test_flag_and_config_present_constructs_a_real_job_for_worker(self) -> None:
        import aiosqlite

        async def _build() -> None:
            db = await aiosqlite.connect(":memory:")
            try:
                from backend.db.sqlite_migrations import run_migrations

                await run_migrations(db)
                with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True), patch.object(
                    config, "CCDASH_INTENTTREE_API_URL", "http://intenttree.example.invalid"
                ), patch.object(config, "CCDASH_INTENTTREE_API_TOKEN", "tok"), patch.object(
                    config, "CCDASH_INTENTTREE_WORKSPACE_ID", "ws-test"
                ):
                    job = _construct_intenttree_derivation_job("worker", db)
                self.assertIsInstance(job, IntentTreeDerivationJob)
                with patch.object(config, "CCDASH_ARE_WE_WINNING_ENABLED", True), patch.object(
                    config, "CCDASH_INTENTTREE_API_URL", "http://intenttree.example.invalid"
                ), patch.object(config, "CCDASH_INTENTTREE_API_TOKEN", "tok"), patch.object(
                    config, "CCDASH_INTENTTREE_WORKSPACE_ID", "ws-test"
                ):
                    job_watcher_worker = _construct_intenttree_derivation_job("worker-watch", db)
                self.assertIsInstance(job_watcher_worker, IntentTreeDerivationJob)
            finally:
                await db.close()

        import asyncio

        asyncio.run(_build())


if __name__ == "__main__":
    unittest.main()
