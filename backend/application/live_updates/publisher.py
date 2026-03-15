"""Publisher helpers that keep domain code independent from transport details."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from backend.application.live_updates.broker import LiveEventBroker
from backend.application.live_updates.contracts import (
    LiveDeliveryHint,
    LiveEventEnvelope,
    LiveEventKind,
    LiveEventMessage,
    utc_now_iso,
)
from backend.application.live_updates.topics import normalize_topic


@runtime_checkable
class LiveEventPublisher(Protocol):
    async def publish(
        self,
        *,
        topic: str,
        kind: LiveEventKind,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        replayable: bool = True,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        """Publish a generic live event."""

    async def publish_append(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> LiveEventEnvelope:
        """Publish an append-style delta event."""

    async def publish_invalidation(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        """Publish an invalidation event."""


class BrokerLiveEventPublisher:
    def __init__(self, broker: LiveEventBroker) -> None:
        self._broker = broker

    async def publish(
        self,
        *,
        topic: str,
        kind: LiveEventKind,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        replayable: bool = True,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        message = LiveEventMessage(
            topic=normalize_topic(topic),
            kind=kind,
            payload=dict(payload or {}),
            occurred_at=occurred_at or utc_now_iso(),
            delivery=LiveDeliveryHint(replayable=replayable, recovery_hint=recovery_hint),
        )
        return await self._broker.publish(message)

    async def publish_append(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> LiveEventEnvelope:
        return await self.publish(
            topic=topic,
            kind="append",
            payload=payload,
            occurred_at=occurred_at,
            replayable=True,
        )

    async def publish_invalidation(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        return await self.publish(
            topic=topic,
            kind="invalidate",
            payload=payload,
            occurred_at=occurred_at,
            replayable=True,
            recovery_hint=recovery_hint,
        )
