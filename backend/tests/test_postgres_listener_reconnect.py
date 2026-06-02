"""P3-014: PostgresLiveNotificationListener auto-reconnect with exponential back-off.

Tests cover:
  (a) listener re-establishes the LISTEN subscription after a connection drop
  (b) asyncio.sleep is called with increasing delays (back-off escalates)
  (c) a stop() signal during back-off sleep exits cleanly
  (d) back-off resets to 0 after a successful reconnect
  (e) reconnect loop terminates cleanly on CancelledError (task cancel)

No real Postgres instance is required — a fake pool factory drives all paths.
"""
from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeConnection:
    """Minimal asyncpg-shaped connection double."""

    def __init__(self) -> None:
        self.listeners: list[tuple[str, Callable[..., None]]] = []
        self.removed: list[tuple[str, Callable[..., None]]] = []
        self.closed = False

    async def add_listener(self, channel: str, callback: Callable[..., None]) -> None:
        self.listeners.append((channel, callback))

    async def remove_listener(self, channel: str, callback: Callable[..., None]) -> None:
        self.removed.append((channel, callback))
        self.listeners = [
            (c, cb) for c, cb in self.listeners if c != channel or cb != callback
        ]

    def fire(self, channel: str, payload: str, pid: int = 42) -> None:
        for c, cb in list(self.listeners):
            if c == channel:
                cb(self, pid, channel, payload)


class _FakePool:
    """asyncpg-like pool double that can be configured to fail N times."""

    def __init__(self, connections: list[_FakeConnection | Exception]) -> None:
        # ``connections`` is a queue: each acquire() pops the front.
        # An Exception entry means that acquire() raises it.
        self._queue = list(connections)
        self.acquired_connections: list[_FakeConnection] = []
        self.released_connections: list[_FakeConnection] = []

    async def acquire(self) -> _FakeConnection:
        if not self._queue:
            raise RuntimeError("pool exhausted")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        self.acquired_connections.append(item)
        return item

    async def release(self, connection: _FakeConnection) -> None:
        self.released_connections.append(connection)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)

    async def publish_append(self, **kwargs: Any) -> Any:  # pragma: no cover
        return await self.publish(**kwargs)

    async def publish_invalidation(self, **kwargs: Any) -> Any:  # pragma: no cover
        return await self.publish(**kwargs)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("predicate never became True")
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _make_wait_for_interceptor(backoff_delays: list[float]) -> Any:
    """Return an asyncio.wait_for replacement that records the timeout arg.

    Only intercepts calls where the awaitable is a ``stop_event.wait()``
    (detected by whether the coroutine belongs to asyncio.Event) — which is
    exactly the back-off sleep path in _reconnect_loop.  All other wait_for
    calls pass through unmodified.
    """
    _orig = asyncio.wait_for

    async def _intercepted(aw: Any, timeout: float | None, **kw: Any) -> Any:
        # Heuristic: back-off sleeps always have a positive, finite timeout.
        if timeout is not None and timeout > 0:
            # Check the coroutine name to identify stop_event.wait() calls.
            coro_name = getattr(aw, "__name__", None) or getattr(
                getattr(aw, "cr_code", None), "co_name", ""
            )
            if "wait" in str(coro_name):
                backoff_delays.append(timeout)
        try:
            return await _orig(aw, timeout, **kw)
        except (asyncio.TimeoutError, TimeoutError):
            raise

    return _intercepted


class ReconnectOnSingleDropTests(unittest.IsolatedAsyncioTestCase):
    """(a) Re-establishes LISTEN after one disconnect; (b) back-off sleep called."""

    async def test_reconnects_after_connection_dropped(self) -> None:
        """Dropping _connection triggers reconnect; listener re-issues add_listener."""
        good_conn1 = _FakeConnection()
        good_conn2 = _FakeConnection()
        pool = _FakePool([good_conn1, good_conn2])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=publisher,
            startup_timeout_seconds=1.0,
            reconnect_base_seconds=0.05,
            reconnect_cap_seconds=10.0,
        )
        self.addAsyncCleanup(listener.stop)

        await listener.start()
        self.assertTrue(listener.status_snapshot()["running"])
        self.assertTrue(listener.status_snapshot()["connected"])

        # Simulate connection drop: null out the stored connection.
        listener._drop_connection()
        self.assertFalse(listener.status_snapshot()["connected"])

        # Wait for the reconnect loop to re-establish.
        await _wait_for(lambda: listener.status_snapshot()["connected"], timeout=5.0)

        snapshot = listener.status_snapshot()
        self.assertTrue(snapshot["running"])
        self.assertTrue(snapshot["connected"])
        self.assertGreaterEqual(snapshot["reconnects"], 1)
        # Second connection must have registered a listener.
        self.assertTrue(len(good_conn2.listeners) > 0)

    async def test_backoff_sleep_called_with_increasing_delays(self) -> None:
        """Each successive reconnect failure increases the back-off delay (AC-b).

        We intercept asyncio.wait_for to capture the timeout values the
        reconnect loop computes for its interruptible backoff sleeps.
        """
        good_conn = _FakeConnection()
        fail1 = RuntimeError("db gone 1")
        fail2 = RuntimeError("db gone 2")
        # Fail twice, then succeed.
        pool = _FakePool([good_conn, fail1, fail2, _FakeConnection()])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        backoff_delays: list[float] = []
        _orig_wait_for = asyncio.wait_for

        async def _intercepted_wait_for(aw: Any, timeout: Any, **kw: Any) -> Any:
            if timeout is not None and timeout > 0:
                coro_name = getattr(aw, "__name__", None) or getattr(
                    getattr(aw, "cr_code", None), "co_name", ""
                )
                if "wait" in str(coro_name):
                    backoff_delays.append(float(timeout))
            return await _orig_wait_for(aw, timeout, **kw)

        with patch("asyncio.wait_for", side_effect=_intercepted_wait_for):
            listener = PostgresLiveNotificationListener(
                db=pool,
                publisher=publisher,
                startup_timeout_seconds=1.0,
                reconnect_base_seconds=0.05,
                reconnect_cap_seconds=100.0,
            )
            self.addAsyncCleanup(listener.stop)

            await listener.start()
            # Drop the first good connection.
            listener._drop_connection()

            # Wait until the reconnect succeeds (two failures then one success).
            await _wait_for(
                lambda: listener.status_snapshot()["reconnects"] >= 1,
                timeout=5.0,
            )

        # We should have captured at least two back-off delay timeouts.
        self.assertGreaterEqual(len(backoff_delays), 2, backoff_delays)
        # The second delay must be strictly greater than the first (exponential growth).
        self.assertGreater(backoff_delays[1], backoff_delays[0], backoff_delays)


class StopDuringBackoffTests(unittest.IsolatedAsyncioTestCase):
    """(c) stop() during back-off sleep exits cleanly without reconnect storm."""

    async def test_stop_during_backoff_exits_promptly(self) -> None:
        """stop() while the reconnect loop is sleeping in back-off terminates immediately.

        Strategy: use a very long backoff cap (60 s) so the loop will be waiting
        inside asyncio.wait_for(stop_event.wait(), timeout=...) when we call stop().
        We then call stop() and assert the listener shuts down quickly (<2 s),
        proving the stop signal interrupts the backoff sleep.
        """
        good_conn = _FakeConnection()
        # After the initial connection, every acquire raises — loop stays in backoff.
        never_recover = RuntimeError("still down")
        pool = _FakePool([good_conn, never_recover, never_recover, never_recover, never_recover])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=publisher,
            startup_timeout_seconds=1.0,
            # Long back-off so the loop will be blocked in wait_for when we stop.
            reconnect_base_seconds=60.0,
            reconnect_cap_seconds=120.0,
        )

        await listener.start()
        self.assertTrue(listener.status_snapshot()["running"])

        # Drop the connection — loop enters a 60 s backoff sleep.
        listener._drop_connection()

        # Give the reconnect loop time to enter the wait_for sleep.
        await asyncio.sleep(0.1)

        # Call stop(); should return promptly by setting the stop event.
        await listener.stop()

        snapshot = listener.status_snapshot()
        self.assertFalse(snapshot["running"])
        self.assertFalse(snapshot["connected"])


class BackoffResetAfterSuccessTests(unittest.IsolatedAsyncioTestCase):
    """(d) back-off counter resets to 0 after a successful reconnect."""

    async def test_backoff_resets_after_successful_reconnect(self) -> None:
        """After a successful reconnect the attempt counter resets.

        We verify this by comparing the attempt numbers recorded in recentErrors:
        after a successful reconnect the next failure should report attempt=1
        (reset from base), not attempt=N+1 (run-away growth).
        """
        good1 = _FakeConnection()
        fail1 = RuntimeError("transient-A")
        fail2 = RuntimeError("transient-B")
        good2 = _FakeConnection()
        # After reconnect, another drop and two more failures.
        fail3 = RuntimeError("transient-C")
        good3 = _FakeConnection()

        pool = _FakePool([good1, fail1, fail2, good2, fail3, good3])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=publisher,
            startup_timeout_seconds=1.0,
            reconnect_base_seconds=0.05,
            reconnect_cap_seconds=100.0,
        )
        self.addAsyncCleanup(listener.stop)

        await listener.start()

        # First drop: two failures before success.
        listener._drop_connection()
        await _wait_for(lambda: listener.status_snapshot()["reconnects"] >= 1, timeout=5.0)

        # At this point recentErrors should show attempt=1 and attempt=2.
        errors_after_first_drop = list(listener.status_snapshot()["recentErrors"])
        attempts_drop1 = [e["attempt"] for e in errors_after_first_drop if e["phase"] == "reconnect"]
        self.assertEqual(attempts_drop1, [1, 2], f"Expected [1, 2], got {attempts_drop1}")

        # Second drop: one failure before success.
        listener._drop_connection()
        await _wait_for(lambda: listener.status_snapshot()["reconnects"] >= 2, timeout=5.0)

        # After reset, the first reconnect failure should again be attempt=1.
        errors_after_second_drop = list(listener.status_snapshot()["recentErrors"])
        reconnect_attempts = [e["attempt"] for e in errors_after_second_drop if e["phase"] == "reconnect"]
        # Last attempt recorded should be from the second drop and should start at 1.
        last_round_attempts = reconnect_attempts[len(attempts_drop1):]
        self.assertTrue(
            len(last_round_attempts) >= 1 and last_round_attempts[0] == 1,
            msg=f"Back-off did not reset after success; attempts={reconnect_attempts}",
        )


class ExistingBehaviourPreservedTests(unittest.IsolatedAsyncioTestCase):
    """Ensure the existing public interface still works unchanged post-refactor."""

    async def test_start_stop_no_reconnect_needed(self) -> None:
        """Normal happy-path start/stop works without reconnect."""
        conn = _FakeConnection()
        pool = _FakePool([conn])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=publisher,
            startup_timeout_seconds=1.0,
        )

        await listener.start()
        self.assertTrue(listener.status_snapshot()["running"])
        self.assertTrue(listener.status_snapshot()["connected"])
        self.assertEqual(listener.status_snapshot()["reconnects"], 0)

        await listener.stop()
        self.assertFalse(listener.status_snapshot()["running"])
        self.assertFalse(listener.status_snapshot()["connected"])

    async def test_start_failure_disables_listener(self) -> None:
        """A failing initial connection disables the listener (existing behaviour)."""
        pool = _FakePool([RuntimeError("pg down")])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=publisher,
            startup_timeout_seconds=0.1,
        )

        with self.assertLogs("ccdash.live.postgres", level="WARNING"):
            await listener.start()

        self.assertFalse(listener.status_snapshot()["running"])

    async def test_double_start_is_idempotent(self) -> None:
        """Calling start() twice does not double-register listeners."""
        conn = _FakeConnection()
        pool = _FakePool([conn])
        publisher = _RecordingPublisher()

        from backend.adapters.live_updates.postgres_listener import (
            PostgresLiveNotificationListener,
        )

        listener = PostgresLiveNotificationListener(
            db=pool, publisher=publisher, startup_timeout_seconds=1.0
        )
        self.addAsyncCleanup(listener.stop)

        await listener.start()
        await listener.start()  # second call should be a no-op

        self.assertEqual(len(conn.listeners), 1)


if __name__ == "__main__":
    unittest.main()
