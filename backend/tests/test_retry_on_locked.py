"""Unit tests for the shared retry_on_locked helper (T2-001).

Tests:
    (a) Success passthrough — fn() called once, result returned.
    (b) Retries then succeeds on locked error.
    (c) Re-raises after exhaustion of locked retries.
    (d) Non-locked OperationalError re-raised immediately without retries.

Counter-injection tests are owned by T2-006; this file does NOT test them.
Sleep is patched so tests are fast.
"""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def _locked_exc() -> aiosqlite.OperationalError:
    return aiosqlite.OperationalError("database is locked")


def _other_exc() -> aiosqlite.OperationalError:
    return aiosqlite.OperationalError("disk I/O error")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetryOnLockedSuccessPassthrough(unittest.TestCase):
    """(a) fn() succeeds on first call — result returned, no sleep."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_success_returns_value(self, mock_sleep: AsyncMock) -> None:
        async def fn():
            return 42

        result = run(retry_on_locked(fn, max_retries=3, backoff=0.1, repo="test"))
        self.assertEqual(result, 42)
        mock_sleep.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_success_returns_none(self, mock_sleep: AsyncMock) -> None:
        async def fn():
            return None

        result = run(retry_on_locked(fn))
        self.assertIsNone(result)
        mock_sleep.assert_not_called()


class TestRetryOnLockedRetryThenSucceeds(unittest.TestCase):
    """(b) fn() fails with locked on first N calls then succeeds."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_retries_once_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _locked_exc()
            return "ok"

        result = run(retry_on_locked(fn, max_retries=3, backoff=0.1, repo="test"))
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 2)
        mock_sleep.assert_called_once_with(0.1)  # backoff * 1

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_retries_three_times_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise _locked_exc()
            return "done"

        result = run(retry_on_locked(fn, max_retries=5, backoff=0.2, repo="repo_x"))
        self.assertEqual(result, "done")
        self.assertEqual(call_count, 4)
        self.assertEqual(mock_sleep.call_count, 3)
        # Sleep values: 0.2*1, 0.2*2, 0.2*3
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertAlmostEqual(calls[0], 0.2)
        self.assertAlmostEqual(calls[1], 0.4)
        self.assertAlmostEqual(calls[2], 0.6)


class TestRetryOnLockedExhaustion(unittest.TestCase):
    """(c) fn() always raises locked — re-raises after exhaustion."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_raises_after_max_retries(self, mock_sleep: AsyncMock) -> None:
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise _locked_exc()

        with self.assertRaises(aiosqlite.OperationalError) as ctx:
            run(retry_on_locked(fn, max_retries=3, backoff=0.1, repo="sessions"))

        self.assertIn("database is locked", str(ctx.exception))
        # fn called max_retries+1 times (initial + 3 retries)
        self.assertEqual(call_count, 4)
        # sleep called max_retries times
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_zero_retries_raises_immediately(self, mock_sleep: AsyncMock) -> None:
        async def fn():
            raise _locked_exc()

        with self.assertRaises(aiosqlite.OperationalError):
            run(retry_on_locked(fn, max_retries=0, backoff=0.5, repo="r"))

        mock_sleep.assert_not_called()


class TestRetryOnLockedNonLockedError(unittest.TestCase):
    """(d) Non-locked OperationalError re-raised immediately, no retries."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_non_locked_raises_immediately(self, mock_sleep: AsyncMock) -> None:
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise _other_exc()

        with self.assertRaises(aiosqlite.OperationalError) as ctx:
            run(retry_on_locked(fn, max_retries=5, backoff=0.1, repo="repo"))

        self.assertIn("disk I/O error", str(ctx.exception))
        # Only called once — no retries for non-locked errors
        self.assertEqual(call_count, 1)
        mock_sleep.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_non_locked_after_one_locked(self, mock_sleep: AsyncMock) -> None:
        """Locked retry followed by non-locked error: non-locked re-raised immediately."""
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _locked_exc()
            raise _other_exc()

        with self.assertRaises(aiosqlite.OperationalError) as ctx:
            run(retry_on_locked(fn, max_retries=5, backoff=0.1, repo="repo"))

        self.assertIn("disk I/O error", str(ctx.exception))
        self.assertEqual(call_count, 2)
        # Sleep once for the first locked error
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_non_operational_error_propagates(self, mock_sleep: AsyncMock) -> None:
        """Non-OperationalError exceptions propagate without retry or counter."""
        async def fn():
            raise ValueError("unexpected")

        with self.assertRaises(ValueError):
            run(retry_on_locked(fn, max_retries=3, backoff=0.1, repo="r"))

        mock_sleep.assert_not_called()


class TestRetryOnLockedDefaultParams(unittest.TestCase):
    """Verify default parameter values are as documented."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_default_max_retries_is_three(self, mock_sleep: AsyncMock) -> None:
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise _locked_exc()

        with self.assertRaises(aiosqlite.OperationalError):
            run(retry_on_locked(fn))

        # Default max_retries=3: fn called 4 times total
        self.assertEqual(call_count, 4)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_default_backoff(self, mock_sleep: AsyncMock) -> None:
        async def fn():
            raise _locked_exc()

        with self.assertRaises(aiosqlite.OperationalError):
            run(retry_on_locked(fn, max_retries=2))

        # Default backoff=0.5: sleep(0.5), sleep(1.0)
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertAlmostEqual(calls[0], 0.5)
        self.assertAlmostEqual(calls[1], 1.0)


# ===========================================================================
# Sync variant tests (T2-002)
# ===========================================================================

import sqlite3 as _stdlib_sqlite3

from backend.db.repositories.base import retry_on_locked_sync  # noqa: E402


def _sync_locked_exc() -> _stdlib_sqlite3.OperationalError:
    return _stdlib_sqlite3.OperationalError("database is locked")


def _sync_other_exc() -> _stdlib_sqlite3.OperationalError:
    return _stdlib_sqlite3.OperationalError("disk I/O error")


class TestRetryOnLockedSyncSuccessPassthrough(unittest.TestCase):
    """(a) sync: fn() succeeds on first call — result returned, no sleep."""

    @patch("time.sleep")
    def test_success_returns_value(self, mock_sleep) -> None:
        def fn():
            return 99

        result = retry_on_locked_sync(fn, max_retries=3, backoff=0.1, repo="test")
        self.assertEqual(result, 99)
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    def test_success_returns_none(self, mock_sleep) -> None:
        def fn():
            return None

        result = retry_on_locked_sync(fn)
        self.assertIsNone(result)
        mock_sleep.assert_not_called()


class TestRetryOnLockedSyncRetryThenSucceeds(unittest.TestCase):
    """(b) sync: fn() fails with locked on first N calls then succeeds."""

    @patch("time.sleep")
    def test_retries_once_then_succeeds(self, mock_sleep) -> None:
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _sync_locked_exc()
            return "ok"

        result = retry_on_locked_sync(fn, max_retries=3, backoff=0.1, repo="test")
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 2)
        mock_sleep.assert_called_once_with(0.1)  # backoff * 1

    @patch("time.sleep")
    def test_retries_three_times_then_succeeds(self, mock_sleep) -> None:
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise _sync_locked_exc()
            return "done"

        result = retry_on_locked_sync(fn, max_retries=5, backoff=0.2, repo="repo_x")
        self.assertEqual(result, "done")
        self.assertEqual(call_count, 4)
        self.assertEqual(mock_sleep.call_count, 3)
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertAlmostEqual(calls[0], 0.2)
        self.assertAlmostEqual(calls[1], 0.4)
        self.assertAlmostEqual(calls[2], 0.6)


class TestRetryOnLockedSyncExhaustion(unittest.TestCase):
    """(c) sync: fn() always raises locked — re-raises after exhaustion."""

    @patch("time.sleep")
    def test_raises_after_max_retries(self, mock_sleep) -> None:
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            raise _sync_locked_exc()

        with self.assertRaises(_stdlib_sqlite3.OperationalError) as ctx:
            retry_on_locked_sync(fn, max_retries=3, backoff=0.1, repo="sessions")

        self.assertIn("database is locked", str(ctx.exception))
        # fn called max_retries+1 times (initial + 3 retries)
        self.assertEqual(call_count, 4)
        # sleep called max_retries times
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("time.sleep")
    def test_zero_retries_raises_immediately(self, mock_sleep) -> None:
        def fn():
            raise _sync_locked_exc()

        with self.assertRaises(_stdlib_sqlite3.OperationalError):
            retry_on_locked_sync(fn, max_retries=0, backoff=0.5, repo="r")

        mock_sleep.assert_not_called()


class TestRetryOnLockedSyncNonLockedError(unittest.TestCase):
    """(d) sync: Non-locked OperationalError re-raised immediately, no retries."""

    @patch("time.sleep")
    def test_non_locked_raises_immediately(self, mock_sleep) -> None:
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            raise _sync_other_exc()

        with self.assertRaises(_stdlib_sqlite3.OperationalError) as ctx:
            retry_on_locked_sync(fn, max_retries=5, backoff=0.1, repo="repo")

        self.assertIn("disk I/O error", str(ctx.exception))
        self.assertEqual(call_count, 1)
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    def test_non_operational_error_propagates(self, mock_sleep) -> None:
        """Non-OperationalError exceptions propagate without retry."""
        def fn():
            raise ValueError("unexpected")

        with self.assertRaises(ValueError):
            retry_on_locked_sync(fn, max_retries=3, backoff=0.1, repo="r")

        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
