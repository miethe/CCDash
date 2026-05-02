import asyncio
import json
import unittest
from collections.abc import Callable, Mapping
from typing import Any

from backend.adapters.live_updates import InMemoryLiveEventBroker, PostgresNotifyLiveEventBus
from backend.adapters.live_updates.postgres_listener import (
    PostgresLiveNotificationListener,
    parse_postgres_live_notification,
)
from backend.application.live_updates import (
    BrokerLiveEventPublisher,
    DEFAULT_BUS_RECOVERY_HINT,
    LiveDeliveryHint,
    LiveEventBusPayloadTooLarge,
    LiveEventEnvelope,
    LiveEventMessage,
    LiveReplayRequest,
)
from backend.application.live_updates.contracts import utc_now_iso
from backend.application.live_updates.bus import (
    LiveEventBusEnvelope,
    decode_live_event_bus_envelope,
    encode_live_event_bus_envelope,
    live_event_bus_envelope_from_message,
    live_event_message_from_bus_envelope,
)
from backend.application.live_updates.runtime_state import (
    get_live_event_publisher,
    publish_live_invalidation,
    set_live_event_publisher,
)
from backend.application.live_updates.topics import execution_run_topic


class _FakeAsyncpgConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.listeners: list[tuple[str, Callable[[Any, int, str, str], None]]] = []
        self.removed: list[tuple[str, Callable[[Any, int, str, str], None]]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "SELECT 1"

    async def add_listener(self, channel: str, callback: Callable[[Any, int, str, str], None]) -> None:
        self.listeners.append((channel, callback))

    async def remove_listener(self, channel: str, callback: Callable[[Any, int, str, str], None]) -> None:
        self.removed.append((channel, callback))
        self.listeners = [(item_channel, item_callback) for item_channel, item_callback in self.listeners if item_channel != channel or item_callback != callback]

    def fire_notification(self, channel: str, payload: str, *, pid: int = 1234) -> None:
        for item_channel, callback in tuple(self.listeners):
            if item_channel == channel:
                callback(self, pid, channel, payload)


class _FakeAsyncpgPool:
    def __init__(self, connection: _FakeAsyncpgConnection) -> None:
        self.connection = connection
        self.acquired = 0
        self.released: list[_FakeAsyncpgConnection] = []

    async def acquire(self) -> _FakeAsyncpgConnection:
        self.acquired += 1
        return self.connection

    async def release(self, connection: _FakeAsyncpgConnection) -> None:
        self.released.append(connection)


def _stub_envelope(topic: str, kind: str) -> LiveEventEnvelope:
    """Build a minimal LiveEventEnvelope for use in test fakes."""
    return LiveEventEnvelope(
        topic=topic,
        kind=kind,  # type: ignore[arg-type]
        cursor="0",
        sequence=0,
        occurred_at=utc_now_iso(),
    )


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(
        self,
        *,
        topic: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        replayable: bool = True,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        self.calls.append(
            {
                "topic": topic,
                "kind": kind,
                "payload": dict(payload or {}),
                "occurred_at": occurred_at,
                "replayable": replayable,
                "recovery_hint": recovery_hint,
            }
        )
        return _stub_envelope(topic, kind)

    async def publish_append(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> LiveEventEnvelope:
        return await self.publish(topic=topic, kind="append", payload=payload, occurred_at=occurred_at)

    async def publish_invalidation(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        return await self.publish(
            topic=topic, kind="invalidate", payload=payload, occurred_at=occurred_at, recovery_hint=recovery_hint
        )


class _FailingPublisher:
    async def publish(self, **kwargs: Any) -> LiveEventEnvelope:
        raise RuntimeError("broker offline")

    async def publish_append(self, **kwargs: Any) -> LiveEventEnvelope:
        raise RuntimeError("broker offline")

    async def publish_invalidation(self, **kwargs: Any) -> LiveEventEnvelope:
        raise RuntimeError("broker offline")


class _FailingNotifyConnection:
    async def execute(self, query: str, *args: Any) -> str:
        raise RuntimeError("pg notify unavailable")


async def _wait_until(predicate: Callable[[], bool], *, timeout_seconds: float = 0.5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Timed out waiting for async listener side effect.")
        await asyncio.sleep(0.01)


class LiveEventBusEnvelopeTests(unittest.TestCase):
    def test_encode_decode_bus_envelope_round_trip_uses_compact_shape(self) -> None:
        envelope = LiveEventBusEnvelope(
            topic="Execution.Run.RUN-1",
            kind="invalidate",
            occurred_at="2026-03-14T10:00:00+00:00",
            payload={"runId": "RUN-1", "sequenceNo": 8, "ignored": {"nested": True}},
            recovery_hint=DEFAULT_BUS_RECOVERY_HINT,
            payload_compacted=True,
        )

        encoded = encode_live_event_bus_envelope(envelope)
        raw = json.loads(encoded)
        decoded = decode_live_event_bus_envelope(encoded)
        message = live_event_message_from_bus_envelope(decoded)

        self.assertEqual(raw["app"], "ccdash")
        self.assertEqual(raw["v"], 1)
        self.assertEqual(raw["t"], "execution.run.run-1")
        self.assertEqual(raw["k"], "invalidate")
        self.assertNotIn("ignored", raw["p"])
        self.assertEqual(decoded.topic, "execution.run.run-1")
        self.assertEqual(decoded.payload, {"runId": "RUN-1", "sequenceNo": 8})
        self.assertEqual(message.kind, "invalidate")
        self.assertFalse(message.delivery.replayable)
        self.assertEqual(message.delivery.recovery_hint, DEFAULT_BUS_RECOVERY_HINT)

    def test_append_message_is_downgraded_to_invalidation_for_bus(self) -> None:
        message = LiveEventMessage(
            topic=execution_run_topic("RUN-2"),
            kind="append",
            payload={"runId": "RUN-2", "sequenceNo": 3, "body": "full append body stays local"},
            occurred_at="2026-03-14T10:01:00+00:00",
            delivery=LiveDeliveryHint(replayable=True),
        )

        envelope = live_event_bus_envelope_from_message(message)

        self.assertEqual(envelope.topic, "execution.run.run-2")
        self.assertEqual(envelope.kind, "invalidate")
        self.assertEqual(envelope.source_kind, "append")
        self.assertEqual(envelope.recovery_hint, DEFAULT_BUS_RECOVERY_HINT)
        self.assertTrue(envelope.payload_compacted)
        self.assertEqual(envelope.payload, {"runId": "RUN-2", "sequenceNo": 3})


class PostgresNotifyLiveEventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_strips_payload_and_rejects_too_large_minimal_envelope(self) -> None:
        connection = _FakeAsyncpgConnection()
        bus = PostgresNotifyLiveEventBus(connection)
        event = LiveEventMessage(
            topic=execution_run_topic("RUN-COMPACT"),
            kind="invalidate",
            payload={
                "runId": "RUN-COMPACT",
                "sequenceNo": 11,
                "status": "x" * 300,
                "details": {"not": "allowed"},
                "body": "not an allowed compact key",
            },
            occurred_at="2026-03-14T10:02:00+00:00",
        )

        envelope = await bus.publish(event)
        _, args = connection.executed[0]
        sent_payload = json.loads(args[1])

        self.assertEqual(args[0], bus.channel)
        self.assertTrue(envelope.payload_compacted)
        self.assertEqual(sent_payload["p"]["runId"], "RUN-COMPACT")
        self.assertEqual(sent_payload["p"]["sequenceNo"], 11)
        self.assertEqual(len(sent_payload["p"]["status"]), 256)
        self.assertTrue(sent_payload["p"]["status"].endswith("..."))
        self.assertNotIn("details", sent_payload["p"])
        self.assertNotIn("body", sent_payload["p"])

        tiny_bus = PostgresNotifyLiveEventBus(_FakeAsyncpgConnection(), max_payload_bytes=1)
        with self.assertRaises(LiveEventBusPayloadTooLarge):
            await tiny_bus.publish(event)

    async def test_publish_failure_is_counted_logged_and_rethrown(self) -> None:
        bus = PostgresNotifyLiveEventBus(_FailingNotifyConnection())
        event = LiveEventMessage(
            topic=execution_run_topic("RUN-PUBLISH-FAIL"),
            kind="invalidate",
            payload={"runId": "RUN-PUBLISH-FAIL", "sequenceNo": 1},
            occurred_at="2026-03-14T10:02:30+00:00",
        )

        with self.assertLogs("ccdash.live.postgres", level="WARNING") as logs:
            with self.assertRaisesRegex(RuntimeError, "pg notify unavailable"):
                await bus.publish(event)

        snapshot = bus.status_snapshot()
        self.assertEqual(snapshot["publishAttempts"], 1)
        self.assertEqual(snapshot["published"], 0)
        self.assertEqual(snapshot["publishErrors"], 1)
        self.assertEqual(snapshot["errorCount"], 1)
        self.assertEqual(snapshot["lastError"], "pg notify unavailable")
        self.assertEqual(snapshot["recentErrors"][0]["phase"], "publish")
        self.assertIn("Failed to publish Postgres live notification", logs.output[0])


class PostgresLiveNotificationListenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_notifications_are_counted_and_not_republished(self) -> None:
        connection = _FakeAsyncpgConnection()
        pool = _FakeAsyncpgPool(connection)
        publisher = _RecordingPublisher()
        listener = PostgresLiveNotificationListener(db=pool, publisher=publisher, startup_timeout_seconds=0.1)
        self.addAsyncCleanup(listener.stop)

        with self.assertRaises(ValueError):
            parse_postgres_live_notification("{not-json")

        await listener.start()
        self.assertTrue(listener.status_snapshot()["running"])
        self.assertTrue(listener.status_snapshot()["connected"])
        connection.fire_notification(listener.channel, "{not-json", pid=8080)
        await _wait_until(lambda: listener.status_snapshot()["malformed"] == 1)

        snapshot = listener.status_snapshot()
        self.assertEqual(snapshot["received"], 1)
        self.assertEqual(snapshot["republished"], 0)
        self.assertEqual(snapshot["malformed"], 1)
        self.assertEqual(snapshot["errorCount"], 1)
        self.assertEqual(snapshot["recentErrors"][0]["phase"], "malformed_notification")
        self.assertEqual(publisher.calls, [])

    async def test_republish_failures_are_counted_and_do_not_stop_listener(self) -> None:
        connection = _FakeAsyncpgConnection()
        pool = _FakeAsyncpgPool(connection)
        listener = PostgresLiveNotificationListener(
            db=pool,
            publisher=_FailingPublisher(),
            startup_timeout_seconds=0.1,
        )
        self.addAsyncCleanup(listener.stop)
        payload = encode_live_event_bus_envelope(
            LiveEventBusEnvelope(
                topic="execution.run.run-republish-fail",
                kind="invalidate",
                occurred_at="2026-03-14T10:02:45+00:00",
                payload={"runId": "RUN-REPUBLISH-FAIL", "sequenceNo": 2},
                recovery_hint=DEFAULT_BUS_RECOVERY_HINT,
                payload_compacted=True,
            )
        )

        await listener.start()
        with self.assertLogs("ccdash.live.postgres", level="WARNING") as logs:
            connection.fire_notification(listener.channel, payload, pid=8081)
            await _wait_until(lambda: listener.status_snapshot()["publishErrors"] == 1)

        snapshot = listener.status_snapshot()
        self.assertTrue(snapshot["running"])
        self.assertTrue(snapshot["connected"])
        self.assertEqual(snapshot["received"], 1)
        self.assertEqual(snapshot["republished"], 0)
        self.assertEqual(snapshot["errorCount"], 1)
        self.assertEqual(snapshot["recentErrors"][0]["phase"], "republish")
        self.assertIn("Failed to republish Postgres live notification", logs.output[0])

    async def test_worker_publish_is_republished_into_in_memory_broker_by_api_listener(self) -> None:
        worker_connection = _FakeAsyncpgConnection()
        api_connection = _FakeAsyncpgConnection()
        api_pool = _FakeAsyncpgPool(api_connection)
        bus = PostgresNotifyLiveEventBus(worker_connection)
        broker = InMemoryLiveEventBroker(replay_buffer_size=5)
        api_publisher = BrokerLiveEventPublisher(broker)
        listener = PostgresLiveNotificationListener(db=api_pool, publisher=api_publisher, startup_timeout_seconds=0.1)
        topic = execution_run_topic("RUN-FANOUT")
        start = await broker.open_subscription(LiveReplayRequest(topics=(topic,), max_pending_events=2))
        self.addAsyncCleanup(listener.stop)
        self.addAsyncCleanup(start.subscription.close)
        self.addAsyncCleanup(broker.close)

        await listener.start()
        await bus.publish(
            LiveEventMessage(
                topic=topic,
                kind="append",
                payload={"runId": "RUN-FANOUT", "sequenceNo": 21, "body": "append details stay out of the bus"},
                occurred_at="2026-03-14T10:03:00+00:00",
                delivery=LiveDeliveryHint(replayable=True),
            )
        )
        _, args = worker_connection.executed[0]

        api_connection.fire_notification(bus.channel, args[1], pid=9090)
        delivered = await start.subscription.next_event(timeout_seconds=0.5)

        self.assertIsNotNone(delivered)
        assert delivered is not None
        self.assertEqual(delivered.topic, "execution.run.run-fanout")
        self.assertEqual(delivered.kind, "invalidate")
        self.assertEqual(delivered.payload, {"runId": "RUN-FANOUT", "sequenceNo": 21})
        self.assertFalse(delivered.delivery.replayable)
        self.assertEqual(delivered.delivery.recovery_hint, DEFAULT_BUS_RECOVERY_HINT)
        await _wait_until(lambda: listener.status_snapshot()["republished"] == 1)
        self.assertEqual(api_pool.acquired, 1)
        self.assertEqual(listener.status_snapshot()["received"], 1)


class PublishIsolationRegressionTests(unittest.IsolatedAsyncioTestCase):
    """FU-3: publish failures must not propagate past the caller's return boundary.

    These tests cover the isolation layer in runtime_state.publish_live_invalidation
    and publish_live_append.  A raising publisher must never abort the surrounding
    DB write or bubble an exception to the sync engine.
    """

    async def test_raising_publisher_does_not_propagate_to_caller(self) -> None:
        """publish_live_invalidation swallows RuntimeError from the publisher."""

        class _RaisingPublisher:
            async def publish_invalidation(self, **_kwargs: Any) -> None:
                raise RuntimeError("bus offline")

            async def publish_append(self, **_kwargs: Any) -> None:  # pragma: no cover
                raise RuntimeError("bus offline")

        previous = get_live_event_publisher()
        set_live_event_publisher(_RaisingPublisher())  # type: ignore[arg-type]
        try:
            # Must not raise — publish failures are logged and swallowed.
            await publish_live_invalidation(
                topic="session.test-session-id",
                payload={"sessionId": "test-session-id", "reason": "test"},
            )
        finally:
            set_live_event_publisher(previous)

    async def test_raising_postgres_bus_publish_failure_counted_not_suppressed(self) -> None:
        """PostgresNotifyLiveEventBus.publish re-raises on transport error.

        The bus itself re-raises so the caller (PostgresNotifyLiveEventPublisher)
        can handle it.  The isolation layer above (runtime_state) is what catches
        it before it reaches sync_engine callers.  This test confirms:
          (a) the error counter is incremented, and
          (b) the exception IS re-raised by the bus (expected — isolation lives one
              layer up).
        """
        bus = PostgresNotifyLiveEventBus(_FailingNotifyConnection())
        event = LiveEventMessage(
            topic=execution_run_topic("RUN-ISOLATION"),
            kind="invalidate",
            payload={"runId": "RUN-ISOLATION", "sequenceNo": 1},
            occurred_at="2026-05-02T12:00:00+00:00",
        )

        with self.assertRaises(RuntimeError):
            await bus.publish(event)

        snapshot = bus.status_snapshot()
        self.assertEqual(snapshot["publishErrors"], 1)

    async def test_sync_write_path_succeeds_when_publisher_raises(self) -> None:
        """Simulate a sync-write path: DB upsert succeeds even if publish raises.

        This is the exact scenario from the FU-3 audit requirement.  We model the
        write as a boolean committed flag that the publish failure must not flip.
        """
        db_committed = False

        class _RaisingLiveEventPublisher:
            async def publish_invalidation(self, **_kwargs: Any) -> None:
                raise RuntimeError("injected publish failure")

            async def publish_append(self, **_kwargs: Any) -> None:  # pragma: no cover
                raise RuntimeError("injected publish failure")

        previous = get_live_event_publisher()
        set_live_event_publisher(_RaisingLiveEventPublisher())  # type: ignore[arg-type]
        try:
            # --- simulate DB write ---
            db_committed = True  # DB write committed before publish call

            # --- publish (would normally fire after upsert) ---
            await publish_live_invalidation(
                topic="feature.feat-xyz",
                payload={"featureId": "feat-xyz", "reason": "sync"},
            )
        finally:
            set_live_event_publisher(previous)

        # DB write must have committed regardless of publish outcome.
        self.assertTrue(db_committed, "DB write was not committed — publish exception propagated")

    async def test_payload_too_large_publisher_does_not_propagate(self) -> None:
        """LiveEventBusPayloadTooLarge raised inside publish_live_invalidation is swallowed."""

        class _TooLargePublisher:
            async def publish_invalidation(self, **_kwargs: Any) -> None:
                raise LiveEventBusPayloadTooLarge("injected too_large")

            async def publish_append(self, **_kwargs: Any) -> None:  # pragma: no cover
                raise LiveEventBusPayloadTooLarge("injected too_large")

        previous = get_live_event_publisher()
        set_live_event_publisher(_TooLargePublisher())  # type: ignore[arg-type]
        try:
            # Must not raise.
            await publish_live_invalidation(
                topic="session.s1",
                payload={"sessionId": "s1"},
            )
        finally:
            set_live_event_publisher(previous)
