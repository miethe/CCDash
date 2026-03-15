"""Live update broker ports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from backend.application.live_updates.contracts import LiveEventEnvelope, LiveEventMessage, LiveTopicCursor


@dataclass(frozen=True, slots=True)
class LiveReplayRequest:
    topics: tuple[str, ...]
    cursors: dict[str, LiveTopicCursor] = field(default_factory=dict)
    max_pending_events: int = 100


@dataclass(frozen=True, slots=True)
class LiveReplayGap:
    topic: str
    requested_sequence: int
    oldest_available_sequence: int | None = None
    latest_sequence: int | None = None
    reason: str = "snapshot_required"


@dataclass(frozen=True, slots=True)
class LiveBrokerStats:
    active_subscribers: int = 0
    buffered_topics: int = 0
    published_events: int = 0
    dropped_events: int = 0
    buffer_evictions: int = 0


@runtime_checkable
class LiveEventSubscription(Protocol):
    @property
    def topics(self) -> tuple[str, ...]:
        """Return the normalized topics for this subscription."""

    async def next_event(self, *, timeout_seconds: float | None = None) -> LiveEventEnvelope | None:
        """Return the next queued live event or None when the wait timed out."""

    async def close(self) -> None:
        """Release any subscription resources."""


@dataclass(frozen=True, slots=True)
class LiveSubscriptionStart:
    subscription: LiveEventSubscription
    replay_events: tuple[LiveEventEnvelope, ...] = ()
    replay_gaps: tuple[LiveReplayGap, ...] = ()


@runtime_checkable
class LiveEventBroker(Protocol):
    async def publish(self, event: LiveEventMessage) -> LiveEventEnvelope:
        """Publish an event to all matching subscribers."""

    async def open_subscription(self, request: LiveReplayRequest) -> LiveSubscriptionStart:
        """Open a live subscription and resolve any replay work atomically."""

    async def close(self) -> None:
        """Release broker resources."""

    def stats(self) -> LiveBrokerStats:
        """Return broker state for observability and tests."""
