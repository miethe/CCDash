import unittest

from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.application.live_updates import BrokerLiveEventPublisher, LiveEventMessage, LiveReplayRequest, LiveTopicCursor
from backend.application.live_updates.topics import decode_cursor, encode_cursor, execution_run_topic, parse_cursor_map, topic_authorization


class LiveTopicHelpersTests(unittest.TestCase):
    def test_cursor_round_trip_preserves_topic_and_sequence(self) -> None:
        cursor = LiveTopicCursor(topic=execution_run_topic("run-123"), sequence=7)

        encoded = encode_cursor(cursor)
        decoded = decode_cursor(encoded)

        self.assertEqual(decoded.topic, "execution.run.run-123")
        self.assertEqual(decoded.sequence, 7)

    def test_parse_cursor_map_rejects_conflicting_entries(self) -> None:
        first = encode_cursor(LiveTopicCursor(topic="execution.run.run-1", sequence=2))
        second = encode_cursor(LiveTopicCursor(topic="execution.run.run-1", sequence=3))

        with self.assertRaises(ValueError):
            parse_cursor_map([first, second])

    def test_topic_authorization_extracts_resource_prefix(self) -> None:
        auth = topic_authorization("execution.run.run-1", project_id="project-1")

        self.assertEqual(auth.resource, "execution.run")
        self.assertEqual(auth.project_id, "project-1")


class InMemoryLiveEventBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_subscription_replays_buffered_events(self) -> None:
        broker = InMemoryLiveEventBroker(replay_buffer_size=5)
        publisher = BrokerLiveEventPublisher(broker)
        topic = execution_run_topic("run-123")

        first = await publisher.publish_append(topic=topic, payload={"sequenceNo": 1}, occurred_at="2026-03-14T10:00:00+00:00")
        second = await publisher.publish_append(topic=topic, payload={"sequenceNo": 2}, occurred_at="2026-03-14T10:00:01+00:00")

        start = await broker.open_subscription(
            LiveReplayRequest(topics=(topic,), cursors={topic: LiveTopicCursor(topic=topic, sequence=first.sequence)})
        )

        self.assertEqual([event.sequence for event in start.replay_events], [second.sequence])
        self.assertEqual(start.replay_gaps, ())
        await start.subscription.close()

    async def test_open_subscription_returns_snapshot_required_gap_when_cursor_is_too_old(self) -> None:
        broker = InMemoryLiveEventBroker(replay_buffer_size=2)
        publisher = BrokerLiveEventPublisher(broker)
        topic = execution_run_topic("run-gap")

        await publisher.publish_append(topic=topic, payload={"sequenceNo": 1}, occurred_at="2026-03-14T10:00:00+00:00")
        await publisher.publish_append(topic=topic, payload={"sequenceNo": 2}, occurred_at="2026-03-14T10:00:01+00:00")
        third = await publisher.publish_append(topic=topic, payload={"sequenceNo": 3}, occurred_at="2026-03-14T10:00:02+00:00")

        start = await broker.open_subscription(
            LiveReplayRequest(topics=(topic,), cursors={topic: LiveTopicCursor(topic=topic, sequence=0)})
        )

        self.assertEqual(start.replay_events, ())
        self.assertEqual(len(start.replay_gaps), 1)
        self.assertEqual(start.replay_gaps[0].topic, topic)
        self.assertEqual(start.replay_gaps[0].latest_sequence, third.sequence)
        await start.subscription.close()

    async def test_subscription_queue_drops_oldest_pending_event_when_consumer_lags(self) -> None:
        broker = InMemoryLiveEventBroker(replay_buffer_size=5)
        topic = execution_run_topic("run-backpressure")
        start = await broker.open_subscription(LiveReplayRequest(topics=(topic,), max_pending_events=1))

        await broker.publish(LiveEventMessage(topic=topic, kind="append", payload={"value": 1}, occurred_at="2026-03-14T10:00:00+00:00"))
        latest = await broker.publish(LiveEventMessage(topic=topic, kind="append", payload={"value": 2}, occurred_at="2026-03-14T10:00:01+00:00"))
        delivered = await start.subscription.next_event(timeout_seconds=0.05)

        self.assertIsNotNone(delivered)
        assert delivered is not None
        self.assertEqual(delivered.sequence, latest.sequence)
        self.assertEqual(delivered.payload["value"], 2)
        self.assertEqual(broker.stats().dropped_events, 1)
        await start.subscription.close()
