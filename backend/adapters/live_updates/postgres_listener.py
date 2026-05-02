"""Postgres LISTEN/NOTIFY bridge for cross-process live updates."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, cast

from backend.application.live_updates.contracts import LiveEventKind, utc_now_iso
from backend.application.live_updates.publisher import LiveEventPublisher

try:
    from backend.adapters.live_updates.postgres_notify import DEFAULT_CCDASH_LIVE_NOTIFY_CHANNEL
except ImportError:  # pragma: no cover - supports LIVE-003 landing before LIVE-002.
    DEFAULT_CCDASH_LIVE_NOTIFY_CHANNEL = "ccdash_live_events"

try:
    from backend.application.live_updates.bus import (
        decode_live_event_bus_envelope,
        live_event_message_from_bus_envelope,
    )
except ImportError:  # pragma: no cover - supports LIVE-003 landing before LIVE-001.
    decode_live_event_bus_envelope = None  # type: ignore[assignment]
    live_event_message_from_bus_envelope = None  # type: ignore[assignment]

logger = logging.getLogger("ccdash.live.postgres")

try:
    from backend.observability import otel as _otel
except ImportError:  # pragma: no cover — observability is optional
    _otel = None  # type: ignore[assignment]

DEFAULT_LIVE_NOTIFY_CHANNEL = DEFAULT_CCDASH_LIVE_NOTIFY_CHANNEL
LIVE_EVENT_KINDS: frozenset[str] = frozenset({"append", "invalidate", "heartbeat", "snapshot_required"})
_BUS_ENVELOPE_KEYS = frozenset({"app", "v"})


@dataclass(frozen=True, slots=True)
class PostgresLiveNotification:
    topic: str
    kind: LiveEventKind
    payload: Mapping[str, Any]
    occurred_at: str | None = None
    replayable: bool = True
    recovery_hint: str | None = None


def parse_postgres_live_notification(raw_payload: str) -> PostgresLiveNotification:
    """Parse the compact JSON envelope emitted by worker-side Postgres publishers."""
    document = _json_document(raw_payload)
    if (
        _BUS_ENVELOPE_KEYS.intersection(document)
        and decode_live_event_bus_envelope is not None
        and live_event_message_from_bus_envelope is not None
    ):
        envelope = decode_live_event_bus_envelope(raw_payload)
        message = live_event_message_from_bus_envelope(envelope)
        return PostgresLiveNotification(
            topic=message.topic,
            kind=message.kind,
            payload=message.payload,
            occurred_at=message.occurred_at,
            replayable=message.delivery.replayable,
            recovery_hint=message.delivery.recovery_hint,
        )

    return _parse_compatible_notification(document)


def _json_document(raw_payload: str) -> dict[str, Any]:
    try:
        document = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Postgres live notification payload must be JSON.") from exc

    if not isinstance(document, dict):
        raise ValueError("Postgres live notification payload must be a JSON object.")
    return document


def _parse_compatible_notification(document: Mapping[str, Any]) -> PostgresLiveNotification:
    topic = _string_value(document, "topic", "t")
    if topic is None:
        raise ValueError("Postgres live notification payload is missing topic.")

    kind_value = _string_value(document, "kind", "k") or "invalidate"
    if kind_value not in LIVE_EVENT_KINDS:
        raise ValueError(f"Unsupported Postgres live notification kind '{kind_value}'.")

    payload = _value(document, "payload", "p")
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ValueError("Postgres live notification payload field must be a JSON object.")

    return PostgresLiveNotification(
        topic=topic,
        kind=cast(LiveEventKind, kind_value),
        payload=payload,
        occurred_at=_string_value(document, "occurred_at", "occurredAt", "at", "ts", "o"),
        replayable=_bool_value(document, True, "replayable", "r"),
        recovery_hint=_string_value(document, "recovery_hint", "recoveryHint", "rh", "h"),
    )


class PostgresLiveNotificationListener:
    """Subscribe to Postgres notifications and republish them into the API SSE broker."""

    def __init__(
        self,
        *,
        db: Any,
        publisher: LiveEventPublisher,
        channel: str = DEFAULT_LIVE_NOTIFY_CHANNEL,
        startup_timeout_seconds: float = 3.0,
    ) -> None:
        self._db = db
        self._publisher = publisher
        self._channel = channel
        self._startup_timeout_seconds = max(0.1, float(startup_timeout_seconds))
        self._connection: Any | None = None
        self._running = False
        self._last_error: str | None = None
        self._received_count = 0
        self._republished_count = 0
        self._malformed_count = 0
        self._publish_error_count = 0
        self._lifecycle_error_count = 0
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._last_error_at: str | None = None
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=10)
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def channel(self) -> str:
        return self._channel

    async def start(self) -> None:
        if self._running:
            return
        try:
            await asyncio.wait_for(self._start(), timeout=self._startup_timeout_seconds)
        except Exception as exc:
            self._record_error("startup", exc, channel=self._channel)
            logger.warning(
                "Postgres live notification listener disabled "
                "(channel=%s, error=%s)",
                self._channel,
                exc,
                extra={
                    "event": "postgres_live_listener_start_failed",
                    "channel": self._channel,
                    "error": str(exc),
                },
                exc_info=True,
            )
            await self.stop()

    async def stop(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

        connection = self._connection
        self._connection = None
        self._running = False
        self._stopped_at = utc_now_iso()
        if connection is None:
            logger.info(
                "Postgres live notification listener stopped without active connection (channel=%s)",
                self._channel,
                extra={
                    "event": "postgres_live_listener_stopped",
                    "channel": self._channel,
                    "connected": False,
                },
            )
            return

        try:
            await connection.remove_listener(self._channel, self._handle_notification)
        except Exception as exc:
            self._record_error("stop", exc, channel=self._channel)
            logger.warning(
                "Failed to remove Postgres live listener callback (channel=%s, error=%s)",
                self._channel,
                exc,
                extra={
                    "event": "postgres_live_listener_stop_failed",
                    "channel": self._channel,
                    "error": str(exc),
                },
                exc_info=True,
            )
        await self._release_connection(connection)
        logger.info(
            "Postgres live notification listener stopped (channel=%s)",
            self._channel,
            extra={
                "event": "postgres_live_listener_stopped",
                "channel": self._channel,
                "connected": True,
            },
        )

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "channel": self._channel,
            "running": self._running,
            "connected": self._connection is not None,
            "lastError": self._last_error,
            "lastErrorAt": self._last_error_at,
            "startedAt": self._started_at,
            "stoppedAt": self._stopped_at,
            "received": self._received_count,
            "republished": self._republished_count,
            "malformed": self._malformed_count,
            "publishErrors": self._publish_error_count,
            "lifecycleErrors": self._lifecycle_error_count,
            "errorCount": self._malformed_count + self._publish_error_count + self._lifecycle_error_count,
            "recentErrors": list(self._recent_errors),
        }

    async def _start(self) -> None:
        connection: Any | None = None
        try:
            connection = await self._acquire_connection()
            assert connection is not None  # _acquire_connection raises on failure; None is unreachable here
            await connection.add_listener(self._channel, self._handle_notification)
        except BaseException:
            if connection is not None:
                await self._release_connection(connection)
            raise
        self._connection = connection
        self._running = True
        self._last_error = None
        self._started_at = utc_now_iso()
        self._stopped_at = None
        logger.info(
            "Postgres live notification listener started (channel=%s)",
            self._channel,
            extra={
                "event": "postgres_live_listener_started",
                "channel": self._channel,
                "connected": True,
            },
        )

    def _handle_notification(self, connection: Any, pid: int, channel: str, payload: str) -> None:
        if not self._running:
            return
        self._received_count += 1
        task = asyncio.create_task(
            self._republish_notification(
                channel=channel,
                payload=payload,
                server_pid=pid,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _republish_notification(self, *, channel: str, payload: str, server_pid: int) -> None:
        try:
            notification = parse_postgres_live_notification(payload)
        except ValueError as exc:
            self._malformed_count += 1
            self._record_error("malformed_notification", exc, channel=channel, server_pid=server_pid)
            if _otel is not None:
                _otel.record_live_fanout_listener_received(result="decode_error")
            logger.warning(
                "Ignoring malformed Postgres live notification "
                "(channel=%s, server_pid=%s, error=%s)",
                channel,
                server_pid,
                exc,
                extra={
                    "event": "postgres_live_notification_malformed",
                    "channel": channel,
                    "server_pid": server_pid,
                    "error": str(exc),
                },
            )
            return

        try:
            await self._publisher.publish(
                topic=notification.topic,
                kind=notification.kind,
                payload=notification.payload,
                occurred_at=notification.occurred_at,
                replayable=notification.replayable,
                recovery_hint=notification.recovery_hint,
            )
        except Exception as exc:
            self._publish_error_count += 1
            self._record_error(
                "republish",
                exc,
                channel=channel,
                server_pid=server_pid,
                topic=notification.topic,
                kind=notification.kind,
            )
            if _otel is not None:
                _otel.record_live_fanout_listener_received(result="republish_error")
            logger.warning(
                "Failed to republish Postgres live notification "
                "(channel=%s, topic=%s, kind=%s, server_pid=%s, error=%s)",
                channel,
                notification.topic,
                notification.kind,
                server_pid,
                exc,
                extra={
                    "event": "postgres_live_notification_republish_failed",
                    "channel": channel,
                    "topic": notification.topic,
                    "kind": notification.kind,
                    "server_pid": server_pid,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return
        self._republished_count += 1
        if _otel is not None:
            _otel.record_live_fanout_listener_received(result="ok")

    async def _acquire_connection(self) -> Any:
        acquire = getattr(self._db, "acquire", None)
        if callable(acquire):
            connection = acquire()
            if inspect.isawaitable(connection):
                return await connection
            return connection
        if hasattr(self._db, "add_listener"):
            return self._db
        raise TypeError("Postgres live notification listener requires an asyncpg connection or pool.")

    async def _release_connection(self, connection: Any) -> None:
        release = getattr(self._db, "release", None)
        if callable(release) and connection is not self._db:
            result = release(connection)
            if inspect.isawaitable(result):
                await result

    def _record_error(self, phase: str, exc: BaseException, **fields: Any) -> None:
        now = utc_now_iso()
        if phase in {"startup", "stop"}:
            self._lifecycle_error_count += 1
        self._last_error = str(exc)
        self._last_error_at = now
        self._recent_errors.append(
            {
                "phase": phase,
                "error": str(exc),
                "at": now,
                **fields,
            }
        )


def _value(document: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in document:
            return document[key]
    return None


def _string_value(document: Mapping[str, Any], *keys: str) -> str | None:
    value = _value(document, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_value(document: Mapping[str, Any], default: bool, *keys: str) -> bool:
    value = _value(document, *keys)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
