"""Counter-injection tests for ccdash_db_write_failures_total (T2-006).

Verifies that:
(a) An sqlite3.OperationalError("database is locked") injected into a write
    callable executed via retry_on_locked causes record_db_write_failure to
    be called via the OTel counter path.
(b) The ccdash_db_write_failures_total counter increments (> 0) after failure,
    inspected via fake OTel and Prometheus counter objects injected through
    patch.object on the otel module globals.
(c) The original locked exception is re-raised after retry exhaustion.
(d) The repo and reason labels on every incremented sample match the values
    passed to retry_on_locked.

Counter values are read via a _FakeOtelCounter.add() call log and a
_FakePromCounter.labels_calls / inc_calls log — the same pattern used by
test_observability_ingestion_metrics.py.  No real Prometheus server is
started.

Sleep is patched with AsyncMock so the tests are fast.
"""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# aiosqlite: try real package first; stub only when genuinely absent.
# Never overwrite an importable real package — doing so shadows aiosqlite
# for every other test collected in the same pytest process.
# ---------------------------------------------------------------------------

try:
    import aiosqlite
except ImportError:
    _stub = types.ModuleType("aiosqlite")

    class _OperationalError(Exception):
        pass

    _stub.OperationalError = _OperationalError  # type: ignore[attr-defined]
    sys.modules["aiosqlite"] = _stub
    import aiosqlite  # noqa: E402 — now the stub

from backend.db.repositories.base import retry_on_locked  # noqa: E402
from backend.observability import otel  # noqa: E402


# ---------------------------------------------------------------------------
# Fake metric objects (mirrors pattern in test_observability_ingestion_metrics)
# ---------------------------------------------------------------------------


class _FakeOtelCounter:
    """Minimal stand-in for an OTel Counter instrument."""

    def __init__(self) -> None:
        # Each call is stored as (value, labels_dict)
        self.calls: list[tuple[int, dict[str, str]]] = []

    def add(self, value: int, labels: dict[str, str]) -> None:  # noqa: D401
        self.calls.append((value, labels))

    @property
    def total_increments(self) -> int:
        return sum(v for v, _ in self.calls)


class _FakePromLabeled:
    """Chain object returned by _FakePromCounter.labels()."""

    def __init__(self, owner: "_FakePromCounter") -> None:
        self._owner = owner

    def inc(self, amount: int = 1) -> None:
        self._owner.inc_calls.append(amount)


class _FakePromCounter:
    """Minimal stand-in for a prometheus_client Counter with label support."""

    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.inc_calls: list[int] = []

    def labels(self, **kwargs: str) -> _FakePromLabeled:
        self.labels_calls.append(kwargs)
        return _FakePromLabeled(self)

    @property
    def total_increments(self) -> int:
        return sum(self.inc_calls)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def run(coro):  # noqa: D401
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _locked_exc() -> aiosqlite.OperationalError:
    return aiosqlite.OperationalError("database is locked")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDbWriteFailuresCounterOtelPath(unittest.TestCase):
    """(a,b,c,d) OTel counter path: counter increments, labels correct, exception re-raised."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_counter_increments_on_exhaustion(self, mock_sleep: AsyncMock) -> None:
        """Counter is incremented once per locked failure including the final one."""
        otel_counter = _FakeOtelCounter()

        async def always_locked():
            raise _locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(retry_on_locked(always_locked, max_retries=3, backoff=0.1, repo="sessions"))

        # max_retries=3 means 4 calls total, each increments the counter
        self.assertGreater(otel_counter.total_increments, 0)
        self.assertEqual(otel_counter.total_increments, 4)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_exception_is_reraised(self, mock_sleep: AsyncMock) -> None:
        """The original locked OperationalError is re-raised after exhaustion (not swallowed)."""
        otel_counter = _FakeOtelCounter()

        async def always_locked():
            raise _locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError) as ctx:
                run(retry_on_locked(always_locked, max_retries=2, backoff=0.05, repo="features"))

        self.assertIn("database is locked", str(ctx.exception))

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_repo_and_reason_labels_are_populated(self, mock_sleep: AsyncMock) -> None:
        """Every counter increment carries repo=<supplied> and reason='locked'."""
        otel_counter = _FakeOtelCounter()

        async def always_locked():
            raise _locked_exc()

        repo_name = "documents"
        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(retry_on_locked(always_locked, max_retries=2, backoff=0.05, repo=repo_name))

        # Every recorded increment must have the correct labels
        self.assertGreater(len(otel_counter.calls), 0)
        for _value, labels in otel_counter.calls:
            self.assertEqual(labels.get("repo"), repo_name)
            self.assertEqual(labels.get("reason"), "locked")

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_non_locked_error_also_increments_counter_with_other_reason(
        self, mock_sleep: AsyncMock
    ) -> None:
        """Non-locked OperationalError increments counter with reason='other', no retries."""
        otel_counter = _FakeOtelCounter()

        async def non_locked():
            raise aiosqlite.OperationalError("disk I/O error")

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(retry_on_locked(non_locked, max_retries=3, backoff=0.1, repo="tasks"))

        # Counter incremented exactly once (no retries)
        self.assertEqual(otel_counter.total_increments, 1)
        _value, labels = otel_counter.calls[0]
        self.assertEqual(labels.get("repo"), "tasks")
        self.assertEqual(labels.get("reason"), "other")
        # No sleep — non-locked errors are not retried
        mock_sleep.assert_not_called()


class TestDbWriteFailuresCounterPromPath(unittest.TestCase):
    """Prometheus counter path: counter increments, labels correct, exception re-raised."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_prom_counter_increments_on_exhaustion(self, mock_sleep: AsyncMock) -> None:
        """Prometheus counter increments once per locked failure."""
        prom_counter = _FakePromCounter()

        async def always_locked():
            raise _locked_exc()

        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(retry_on_locked(always_locked, max_retries=3, backoff=0.1, repo="analytics"))

        # 4 total failures (initial + 3 retries), each increments prom counter
        self.assertGreater(prom_counter.total_increments, 0)
        self.assertEqual(prom_counter.total_increments, 4)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_prom_repo_and_reason_labels_are_populated(self, mock_sleep: AsyncMock) -> None:
        """Every Prometheus .labels() call carries repo=<supplied> and reason='locked'."""
        prom_counter = _FakePromCounter()

        async def always_locked():
            raise _locked_exc()

        repo_name = "links"
        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(retry_on_locked(always_locked, max_retries=2, backoff=0.05, repo=repo_name))

        self.assertGreater(len(prom_counter.labels_calls), 0)
        for labels in prom_counter.labels_calls:
            self.assertEqual(labels.get("repo"), repo_name)
            self.assertEqual(labels.get("reason"), "locked")


class TestDbWriteFailuresCounterBothPaths(unittest.TestCase):
    """Both OTel and Prometheus counters increment together."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_both_counters_increment(self, mock_sleep: AsyncMock) -> None:
        """With both _enabled and _prom_enabled True, both counters get incremented."""
        otel_counter = _FakeOtelCounter()
        prom_counter = _FakePromCounter()

        async def always_locked():
            raise _locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError):
                run(
                    retry_on_locked(
                        always_locked, max_retries=1, backoff=0.05, repo="sessions"
                    )
                )

        # max_retries=1 → 2 calls → 2 increments on each counter
        self.assertEqual(otel_counter.total_increments, 2)
        self.assertEqual(prom_counter.total_increments, 2)

        # Labels match on both sides
        for _v, labels in otel_counter.calls:
            self.assertEqual(labels["repo"], "sessions")
            self.assertEqual(labels["reason"], "locked")
        for labels in prom_counter.labels_calls:
            self.assertEqual(labels["repo"], "sessions")
            self.assertEqual(labels["reason"], "locked")

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_exception_re_raised_with_both_paths_active(self, mock_sleep: AsyncMock) -> None:
        """The original exception is still re-raised when both counter paths fire."""
        otel_counter = _FakeOtelCounter()
        prom_counter = _FakePromCounter()

        async def always_locked():
            raise _locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(aiosqlite.OperationalError) as ctx:
                run(retry_on_locked(always_locked, max_retries=2, backoff=0.05, repo="tasks"))

        self.assertIn("database is locked", str(ctx.exception))
        self.assertGreater(otel_counter.total_increments, 0)
        self.assertGreater(prom_counter.total_increments, 0)


class TestRecordDbWriteFailureDirectly(unittest.TestCase):
    """Unit tests for record_db_write_failure() in otel.py directly (not via retry_on_locked).

    These tests verify the public API is callable and correctly wires labels.
    """

    def test_record_db_write_failure_otel_path(self) -> None:
        """record_db_write_failure increments OTel counter with correct labels."""
        otel_counter = _FakeOtelCounter()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            otel.record_db_write_failure(repo="execution", reason="locked")

        self.assertEqual(len(otel_counter.calls), 1)
        value, labels = otel_counter.calls[0]
        self.assertEqual(value, 1)
        self.assertEqual(labels["repo"], "execution")
        self.assertEqual(labels["reason"], "locked")

    def test_record_db_write_failure_prom_path(self) -> None:
        """record_db_write_failure increments Prometheus counter with correct labels."""
        prom_counter = _FakePromCounter()

        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            otel.record_db_write_failure(repo="sessions", reason="other")

        self.assertEqual(len(prom_counter.labels_calls), 1)
        self.assertEqual(prom_counter.labels_calls[0], {"repo": "sessions", "reason": "other"})
        self.assertEqual(prom_counter.total_increments, 1)

    def test_record_db_write_failure_never_raises(self) -> None:
        """record_db_write_failure must not raise even when counter is None."""
        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_db_write_failures_counter", None),
            patch.object(otel, "_prom_db_write_failures_counter", None),
        ):
            # Must not raise
            otel.record_db_write_failure(repo="sync", reason="locked")

    def test_record_db_write_failure_empty_labels_are_normalized(self) -> None:
        """Empty repo/reason are normalized to 'unknown', not passed as empty strings."""
        otel_counter = _FakeOtelCounter()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            otel.record_db_write_failure(repo="", reason="")

        self.assertEqual(len(otel_counter.calls), 1)
        _v, labels = otel_counter.calls[0]
        self.assertEqual(labels["repo"], "unknown")
        self.assertEqual(labels["reason"], "unknown")


# ---------------------------------------------------------------------------
# Sync variant (retry_on_locked_sync) — T2-002
# ---------------------------------------------------------------------------


import sqlite3 as _sqlite3  # stdlib; always available


def _sync_locked_exc() -> _sqlite3.OperationalError:
    return _sqlite3.OperationalError("database is locked")


def _sync_other_exc() -> _sqlite3.OperationalError:
    return _sqlite3.OperationalError("disk I/O error")


from backend.db.repositories.base import retry_on_locked_sync  # noqa: E402


class TestDbWriteFailuresCounterSyncOtelPath(unittest.TestCase):
    """OTel counter path via retry_on_locked_sync."""

    @patch("time.sleep")
    def test_sync_counter_increments_on_exhaustion(self, mock_sleep) -> None:
        """Counter increments once per locked failure including the final one."""
        otel_counter = _FakeOtelCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(always_locked, max_retries=3, backoff=0.1, repo="sessions")

        # max_retries=3 → 4 calls total → 4 counter increments
        self.assertGreater(otel_counter.total_increments, 0)
        self.assertEqual(otel_counter.total_increments, 4)

    @patch("time.sleep")
    def test_sync_exception_is_reraised(self, mock_sleep) -> None:
        """Locked OperationalError is re-raised after retry exhaustion (not swallowed)."""
        otel_counter = _FakeOtelCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError) as ctx:
                retry_on_locked_sync(always_locked, max_retries=2, backoff=0.05, repo="features")

        self.assertIn("database is locked", str(ctx.exception))

    @patch("time.sleep")
    def test_sync_repo_and_reason_labels_are_populated(self, mock_sleep) -> None:
        """Every OTel increment carries repo=<supplied> and reason='locked'."""
        otel_counter = _FakeOtelCounter()

        def always_locked():
            raise _sync_locked_exc()

        repo_name = "documents"
        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(always_locked, max_retries=2, backoff=0.05, repo=repo_name)

        self.assertGreater(len(otel_counter.calls), 0)
        for _value, labels in otel_counter.calls:
            self.assertEqual(labels.get("repo"), repo_name)
            self.assertEqual(labels.get("reason"), "locked")

    @patch("time.sleep")
    def test_sync_non_locked_error_increments_with_other_reason(self, mock_sleep) -> None:
        """Non-locked OperationalError: one increment with reason='other', no sleep."""
        otel_counter = _FakeOtelCounter()

        def non_locked():
            raise _sync_other_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(non_locked, max_retries=3, backoff=0.1, repo="tasks")

        self.assertEqual(otel_counter.total_increments, 1)
        _value, labels = otel_counter.calls[0]
        self.assertEqual(labels.get("repo"), "tasks")
        self.assertEqual(labels.get("reason"), "other")
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    def test_sync_sleep_called_between_retries(self, mock_sleep) -> None:
        """time.sleep is called between retries (not asyncio.sleep)."""
        otel_counter = _FakeOtelCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(always_locked, max_retries=3, backoff=0.2, repo="sync")

        # 3 retries → 3 sleeps: 0.2, 0.4, 0.6
        self.assertEqual(mock_sleep.call_count, 3)
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertAlmostEqual(sleep_args[0], 0.2)
        self.assertAlmostEqual(sleep_args[1], 0.4)
        self.assertAlmostEqual(sleep_args[2], 0.6)


class TestDbWriteFailuresCounterSyncPromPath(unittest.TestCase):
    """Prometheus counter path via retry_on_locked_sync."""

    @patch("time.sleep")
    def test_sync_prom_counter_increments_on_exhaustion(self, mock_sleep) -> None:
        """Prometheus counter increments once per locked failure."""
        prom_counter = _FakePromCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(always_locked, max_retries=3, backoff=0.1, repo="analytics")

        self.assertGreater(prom_counter.total_increments, 0)
        self.assertEqual(prom_counter.total_increments, 4)

    @patch("time.sleep")
    def test_sync_prom_repo_and_reason_labels_are_populated(self, mock_sleep) -> None:
        """Every Prometheus .labels() call carries repo=<supplied> and reason='locked'."""
        prom_counter = _FakePromCounter()

        def always_locked():
            raise _sync_locked_exc()

        repo_name = "links"
        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(always_locked, max_retries=2, backoff=0.05, repo=repo_name)

        self.assertGreater(len(prom_counter.labels_calls), 0)
        for labels in prom_counter.labels_calls:
            self.assertEqual(labels.get("repo"), repo_name)
            self.assertEqual(labels.get("reason"), "locked")


class TestDbWriteFailuresCounterSyncBothPaths(unittest.TestCase):
    """Both OTel and Prometheus counters increment together via retry_on_locked_sync."""

    @patch("time.sleep")
    def test_sync_both_counters_increment(self, mock_sleep) -> None:
        """With both paths enabled, both counters get incremented on every failure."""
        otel_counter = _FakeOtelCounter()
        prom_counter = _FakePromCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError):
                retry_on_locked_sync(
                    always_locked, max_retries=1, backoff=0.05, repo="sessions"
                )

        # max_retries=1 → 2 calls → 2 increments each
        self.assertEqual(otel_counter.total_increments, 2)
        self.assertEqual(prom_counter.total_increments, 2)

        for _v, labels in otel_counter.calls:
            self.assertEqual(labels["repo"], "sessions")
            self.assertEqual(labels["reason"], "locked")
        for labels in prom_counter.labels_calls:
            self.assertEqual(labels["repo"], "sessions")
            self.assertEqual(labels["reason"], "locked")

    @patch("time.sleep")
    def test_sync_exception_re_raised_with_both_paths_active(self, mock_sleep) -> None:
        """Original exception re-raised when both counter paths fire."""
        otel_counter = _FakeOtelCounter()
        prom_counter = _FakePromCounter()

        def always_locked():
            raise _sync_locked_exc()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_db_write_failures_counter", otel_counter),
            patch.object(otel, "_prom_db_write_failures_counter", prom_counter),
        ):
            with self.assertRaises(_sqlite3.OperationalError) as ctx:
                retry_on_locked_sync(
                    always_locked, max_retries=2, backoff=0.05, repo="tasks"
                )

        self.assertIn("database is locked", str(ctx.exception))
        self.assertGreater(otel_counter.total_increments, 0)
        self.assertGreater(prom_counter.total_increments, 0)


if __name__ == "__main__":
    unittest.main()
