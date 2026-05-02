"""Postgres LISTEN/NOTIFY publisher for cross-process live fanout."""
from __future__ import annotations

import logging
import re
import time
from collections import deque
from typing import Any, Mapping

from backend.application.live_updates.bus import (
    DEFAULT_BUS_RECOVERY_HINT,
    LiveEventBusEnvelope,
    LiveEventBusPayloadTooLarge,
    LiveEventBusPublisher,
    encode_live_event_bus_envelope,
    live_event_bus_envelope_from_message,
)
from backend.application.live_updates.contracts import (
    LiveDeliveryHint,
    LiveEventEnvelope,
    LiveEventKind,
    LiveEventMessage,
    LiveTopicCursor,
    utc_now_iso,
)
from backend.application.live_updates.topics import encode_cursor, normalize_topic

try:
    from backend.observability import otel as _otel
except ImportError:  # pragma: no cover — observability is optional
    _otel = None  # type: ignore[assignment]

DEFAULT_CCDASH_LIVE_NOTIFY_CHANNEL = "ccdash_live_events"
POSTGRES_NOTIFY_PAYLOAD_LIMIT_BYTES = 8000
DEFAULT_NOTIFY_PAYLOAD_BUDGET_BYTES = 7900

_CHANNEL_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
logger = logging.getLogger("ccdash.live.postgres")


class PostgresNotifyLiveEventBus:
    """Publish compact CCDash live event envelopes through Postgres NOTIFY."""

    def __init__(
        self,
        db: Any,
        *,
        channel: str = DEFAULT_CCDASH_LIVE_NOTIFY_CHANNEL,
        max_payload_bytes: int = DEFAULT_NOTIFY_PAYLOAD_BUDGET_BYTES,
        invalidation_only: bool = True,
    ) -> None:
        self._db = db
        self.channel = _validate_channel(channel)
        self.max_payload_bytes = max(
            1,
            min(int(max_payload_bytes), POSTGRES_NOTIFY_PAYLOAD_LIMIT_BYTES - 1),
        )
        self.invalidation_only = bool(invalidation_only)
        self._publish_attempts = 0
        self._published_count = 0
        self._publish_error_count = 0
        self._last_error: str | None = None
        self._last_error_at: str | None = None
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=10)
        self._closed = False
        logger.info(
            "Postgres live notification publisher started (channel=%s)",
            self.channel,
            extra={"event": "postgres_live_notify_started", "channel": self.channel},
        )

    async def publish(self, event: LiveEventMessage) -> LiveEventBusEnvelope:
        self._publish_attempts += 1
        envelope = live_event_bus_envelope_from_message(
            event,
            invalidation_only=self.invalidation_only,
        )
        t0 = time.monotonic()
        try:
            payload = self._encode_payload(envelope)
            await self._db.execute("SELECT pg_notify($1, $2)", self.channel, payload)
        except LiveEventBusPayloadTooLarge as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record_publish_error(exc, topic=envelope.topic, kind=envelope.kind)
            if _otel is not None:
                _otel.record_live_fanout_publish(result="too_large", latency_ms=latency_ms)
            logger.warning(
                "Failed to publish Postgres live notification "
                "(channel=%s, topic=%s, kind=%s, error=%s)",
                self.channel,
                envelope.topic,
                envelope.kind,
                exc,
                extra={
                    "event": "postgres_live_notify_publish_failed",
                    "channel": self.channel,
                    "topic": envelope.topic,
                    "kind": envelope.kind,
                    "error": str(exc),
                },
            )
            raise
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record_publish_error(exc, topic=envelope.topic, kind=envelope.kind)
            if _otel is not None:
                _otel.record_live_fanout_publish(result="error", latency_ms=latency_ms)
            logger.warning(
                "Failed to publish Postgres live notification "
                "(channel=%s, topic=%s, kind=%s, error=%s)",
                self.channel,
                envelope.topic,
                envelope.kind,
                exc,
                extra={
                    "event": "postgres_live_notify_publish_failed",
                    "channel": self.channel,
                    "topic": envelope.topic,
                    "kind": envelope.kind,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise
        latency_ms = (time.monotonic() - t0) * 1000.0
        self._published_count += 1
        if _otel is not None:
            _otel.record_live_fanout_publish(result="ok", latency_ms=latency_ms)
        return envelope

    async def close(self) -> None:
        """No owned resources; connections are managed by the runtime container."""
        self._closed = True
        logger.info(
            "Postgres live notification publisher stopped (channel=%s)",
            self.channel,
            extra={"event": "postgres_live_notify_stopped", "channel": self.channel},
        )

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "running": not self._closed,
            "connected": self._db is not None,
            "invalidationOnly": self.invalidation_only,
            "maxPayloadBytes": self.max_payload_bytes,
            "publishAttempts": self._publish_attempts,
            "published": self._published_count,
            "publishErrors": self._publish_error_count,
            "errorCount": self._publish_error_count,
            "lastError": self._last_error,
            "lastErrorAt": self._last_error_at,
            "recentErrors": list(self._recent_errors),
        }

    def _encode_payload(self, envelope: LiveEventBusEnvelope) -> str:
        payload = encode_live_event_bus_envelope(envelope, include_payload=True)
        if _payload_size(payload) <= self.max_payload_bytes:
            return payload

        payload = encode_live_event_bus_envelope(envelope, include_payload=False)
        if _payload_size(payload) <= self.max_payload_bytes:
            return payload

        raise LiveEventBusPayloadTooLarge(
            "Compact CCDash live event envelope exceeds Postgres NOTIFY payload budget "
            f"({self.max_payload_bytes} bytes) for topic '{envelope.topic}'."
        )

    def _record_publish_error(self, exc: BaseException, *, topic: str, kind: str) -> None:
        now = utc_now_iso()
        self._publish_error_count += 1
        self._last_error = str(exc)
        self._last_error_at = now
        self._recent_errors.append(
            {
                "phase": "publish",
                "topic": topic,
                "kind": kind,
                "error": str(exc),
                "at": now,
            }
        )


class PostgresNotifyLiveEventPublisher:
    """LiveEventPublisher implementation backed only by Postgres NOTIFY fanout."""

    def __init__(self, bus: LiveEventBusPublisher) -> None:
        self._bus = bus

    async def publish(
        self,
        *,
        topic: str,
        kind: LiveEventKind,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        replayable: bool = False,
        recovery_hint: str | None = None,
    ) -> LiveEventEnvelope:
        message = LiveEventMessage(
            topic=normalize_topic(topic),
            kind=kind,
            payload=dict(payload or {}),
            occurred_at=occurred_at or utc_now_iso(),
            delivery=LiveDeliveryHint(
                replayable=False,
                recovery_hint=(
                    recovery_hint
                    or (DEFAULT_BUS_RECOVERY_HINT if kind in {"append", "invalidate"} else None)
                ),
            ),
        )
        envelope = await self._bus.publish(message)
        return LiveEventEnvelope(
            topic=envelope.topic,
            kind=envelope.kind,
            cursor=encode_cursor(LiveTopicCursor(topic=envelope.topic, sequence=0)),
            sequence=0,
            occurred_at=envelope.occurred_at,
            payload=dict(envelope.payload or {}),
            delivery=LiveDeliveryHint(replayable=False, recovery_hint=envelope.recovery_hint),
        )

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
            replayable=False,
            recovery_hint=DEFAULT_BUS_RECOVERY_HINT,
        )

    async def publish_invalidation(
        self,
        *,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        recovery_hint: str | None = DEFAULT_BUS_RECOVERY_HINT,
    ) -> LiveEventEnvelope:
        return await self.publish(
            topic=topic,
            kind="invalidate",
            payload=payload,
            occurred_at=occurred_at,
            replayable=False,
            recovery_hint=recovery_hint,
        )


def _payload_size(payload: str) -> int:
    return len(payload.encode("utf-8"))


def _validate_channel(channel: str) -> str:
    normalized = str(channel or "").strip().lower()
    if not _CHANNEL_RE.fullmatch(normalized):
        raise ValueError(
            "Postgres live notify channel must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores within 63 characters."
        )
    return normalized
