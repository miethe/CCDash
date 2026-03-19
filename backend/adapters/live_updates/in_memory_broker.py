"""In-process live event broker with bounded replay buffers."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import replace

from backend.application.live_updates.broker import (
    LiveBrokerStats,
    LiveEventSubscription,
    LiveReplayGap,
    LiveReplayRequest,
    LiveSubscriptionStart,
)
from backend.application.live_updates.contracts import LiveEventEnvelope, LiveEventMessage, LiveTopicCursor
from backend.application.live_updates.topics import encode_cursor, normalize_topics, normalize_topic


class _QueueSubscription(LiveEventSubscription):
    def __init__(
        self,
        broker: InMemoryLiveEventBroker,
        topics: tuple[str, ...],
        *,
        max_pending_events: int,
    ) -> None:
        self._broker = broker
        self._topics = topics
        self._queue: asyncio.Queue[LiveEventEnvelope] = asyncio.Queue(maxsize=max(1, int(max_pending_events or 100)))
        self._closed = False

    @property
    def topics(self) -> tuple[str, ...]:
        return self._topics

    def push(self, event: LiveEventEnvelope) -> int:
        if self._closed:
            return 0
        dropped = 0
        while self._queue.full():
            try:
                self._queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        self._queue.put_nowait(event)
        return dropped

    async def next_event(self, *, timeout_seconds: float | None = None) -> LiveEventEnvelope | None:
        if self._closed:
            return None
        try:
            if timeout_seconds is None:
                return await self._queue.get()
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._broker._remove_subscription(self)


class InMemoryLiveEventBroker:
    def __init__(self, *, replay_buffer_size: int = 200) -> None:
        self._replay_buffer_size = max(1, int(replay_buffer_size or 200))
        self._lock = asyncio.Lock()
        self._subscriptions_by_topic: dict[str, set[_QueueSubscription]] = defaultdict(set)
        self._subscriptions: set[_QueueSubscription] = set()
        self._topic_sequences: dict[str, int] = defaultdict(int)
        self._buffers: dict[str, deque[LiveEventEnvelope]] = {}
        self._stats = LiveBrokerStats()

    async def publish(self, event: LiveEventMessage) -> LiveEventEnvelope:
        topic = normalize_topic(event.topic)
        async with self._lock:
            sequence = self._topic_sequences[topic] + 1
            self._topic_sequences[topic] = sequence
            envelope = LiveEventEnvelope(
                topic=topic,
                kind=event.kind,
                cursor=encode_cursor(LiveTopicCursor(topic=topic, sequence=sequence)),
                sequence=sequence,
                occurred_at=event.occurred_at,
                payload=dict(event.payload),
                delivery=event.delivery,
            )
            next_stats = replace(self._stats, published_events=self._stats.published_events + 1)
            if event.delivery.replayable:
                buffer = self._buffers.get(topic)
                if buffer is None:
                    buffer = deque(maxlen=self._replay_buffer_size)
                    self._buffers[topic] = buffer
                if len(buffer) == buffer.maxlen:
                    next_stats = replace(next_stats, buffer_evictions=next_stats.buffer_evictions + 1)
                buffer.append(envelope)
            subscribers = tuple(self._subscriptions_by_topic.get(topic, ()))
            dropped_events = next_stats.dropped_events
            for subscription in subscribers:
                dropped_events += subscription.push(envelope)
            self._stats = replace(
                next_stats,
                active_subscribers=len(self._subscriptions),
                buffered_topics=len(self._buffers),
                active_topic_subscriptions=sum(len(subscribers) for subscribers in self._subscriptions_by_topic.values()),
                dropped_events=dropped_events,
            )
            return envelope

    async def open_subscription(self, request: LiveReplayRequest) -> LiveSubscriptionStart:
        topics = normalize_topics(request.topics)
        subscription = _QueueSubscription(
            self,
            topics,
            max_pending_events=max(1, int(request.max_pending_events or 100)),
        )
        async with self._lock:
            self._subscriptions.add(subscription)
            for topic in topics:
                self._subscriptions_by_topic[topic].add(subscription)
            replay_events, replay_gaps = self._collect_replay(topics, request.cursors)
            self._stats = replace(
                self._stats,
                active_subscribers=len(self._subscriptions),
                buffered_topics=len(self._buffers),
                active_topic_subscriptions=sum(len(subscribers) for subscribers in self._subscriptions_by_topic.values()),
                replay_gaps=self._stats.replay_gaps + len(replay_gaps),
                subscription_opens=self._stats.subscription_opens + 1,
            )
        return LiveSubscriptionStart(
            subscription=subscription,
            replay_events=tuple(replay_events),
            replay_gaps=tuple(replay_gaps),
        )

    async def close(self) -> None:
        subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            await subscription.close()

    def stats(self) -> LiveBrokerStats:
        return self._stats

    def _collect_replay(
        self,
        topics: tuple[str, ...],
        cursors: dict[str, LiveTopicCursor],
    ) -> tuple[list[LiveEventEnvelope], list[LiveReplayGap]]:
        replay_events: list[LiveEventEnvelope] = []
        replay_gaps: list[LiveReplayGap] = []
        for topic in topics:
            cursor = cursors.get(topic)
            if cursor is None:
                continue
            sequence = int(getattr(cursor, "sequence", 0))
            latest_sequence = int(self._topic_sequences.get(topic, 0))
            if latest_sequence == 0:
                replay_gaps.append(
                    LiveReplayGap(topic=topic, requested_sequence=sequence, oldest_available_sequence=None, latest_sequence=0)
                )
                continue
            buffer = self._buffers.get(topic)
            if not buffer:
                replay_gaps.append(
                    LiveReplayGap(topic=topic, requested_sequence=sequence, oldest_available_sequence=None, latest_sequence=latest_sequence)
                )
                continue
            oldest_available = buffer[0].sequence
            if sequence > latest_sequence or sequence < oldest_available - 1:
                replay_gaps.append(
                    LiveReplayGap(
                        topic=topic,
                        requested_sequence=sequence,
                        oldest_available_sequence=oldest_available,
                        latest_sequence=latest_sequence,
                    )
                )
                continue
            replay_events.extend(event for event in buffer if event.sequence > sequence)
        replay_events.sort(key=lambda event: (event.occurred_at, event.topic, event.sequence))
        return replay_events, replay_gaps

    async def _remove_subscription(self, subscription: _QueueSubscription) -> None:
        async with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)
            for topic in subscription.topics:
                subscribers = self._subscriptions_by_topic.get(topic)
                if not subscribers:
                    continue
                subscribers.discard(subscription)
                if not subscribers:
                    self._subscriptions_by_topic.pop(topic, None)
            self._stats = replace(
                self._stats,
                active_subscribers=len(self._subscriptions),
                buffered_topics=len(self._buffers),
                active_topic_subscriptions=sum(len(subscribers) for subscribers in self._subscriptions_by_topic.values()),
                subscription_closes=self._stats.subscription_closes + 1,
            )
