"""Postgres LISTEN/NOTIFY bridge for cross-process live updates."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
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

# Reconnect backoff defaults.  Override by passing keyword args to the constructor.
_RECONNECT_BASE_SECONDS: float = 1.0
_RECONNECT_CAP_SECONDS: float = 60.0
_RECONNECT_JITTER_FACTOR: float = 0.25  # ±25 % of computed delay


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
    """Subscribe to Postgres notifications and republish them into the API SSE broker.

    On a connection drop the listener automatically re-establishes the LISTEN
    subscription using truncated exponential back-off with jitter:

        delay = min(cap, base * 2 ** attempt) * uniform(1 - jitter, 1 + jitter)

    Defaults: base=1 s, cap=60 s, jitter=±25 %.  All three are configurable via
    constructor keyword arguments; no new env-var config is required.
    A stop/cancel signal terminates any in-progress backoff sleep promptly.
    """

    def __init__(
        self,
        *,
        db: Any,
        publisher: LiveEventPublisher,
        channel: str = DEFAULT_LIVE_NOTIFY_CHANNEL,
        startup_timeout_seconds: float = 3.0,
        reconnect_base_seconds: float = _RECONNECT_BASE_SECONDS,
        reconnect_cap_seconds: float = _RECONNECT_CAP_SECONDS,
        reconnect_max_attempts: int | None = None,
    ) -> None:
        self._db = db
        self._publisher = publisher
        self._channel = channel
        self._startup_timeout_seconds = max(0.1, float(startup_timeout_seconds))
        self._reconnect_base = max(0.1, float(reconnect_base_seconds))
        self._reconnect_cap = max(self._reconnect_base, float(reconnect_cap_seconds))
        self._reconnect_max_attempts = reconnect_max_attempts  # None = infinite
        self._connection: Any | None = None
        self._running = False
        self._last_error: str | None = None
        self._received_count = 0
        self._republished_count = 0
        self._malformed_count = 0
        self._publish_error_count = 0
        self._lifecycle_error_count = 0
        self._reconnect_count = 0
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._last_error_at: str | None = None
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=10)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stop_event: asyncio.Event | None = None

    @property
    def channel(self) -> str:
        return self._channel

    async def start(self) -> None:
        """Start the listener.

        The first connection attempt is attempted synchronously (with
        ``startup_timeout_seconds``).  On success a background reconnect loop is
        launched so that any subsequent connection drop triggers automatic
        re-subscribe with exponential back-off.
        """
        if self._running:
            return
        # Create a fresh stop event for this lifecycle.
        self._stop_event = asyncio.Event()
        try:
            await asyncio.wait_for(self._connect_once(), timeout=self._startup_timeout_seconds)
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
            return

        # First connect succeeded — launch the background reconnect watcher.
        reconnect_task: asyncio.Task[None] = asyncio.create_task(
            self._reconnect_loop(), name="postgres_listener_reconnect"
        )
        self._tasks.add(reconnect_task)
        reconnect_task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        # Signal the reconnect loop to exit before cancelling tasks.
        if self._stop_event is not None:
            self._stop_event.set()

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
            "reconnects": self._reconnect_count,
            "errorCount": self._malformed_count + self._publish_error_count + self._lifecycle_error_count,
            "recentErrors": list(self._recent_errors),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect_once(self) -> None:
        """Acquire a connection, register the LISTEN callback, and mark self as running."""
        connection: Any | None = None
        try:
            connection = await self._acquire_connection()
            assert connection is not None  # _acquire_connection raises on failure
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

    async def _reconnect_loop(self) -> None:
        """Background task: detect connection loss and re-subscribe with back-off.

        The loop wakes whenever *self._connection* becomes ``None`` while the
        listener is still logically running (i.e. ``stop()`` has not been
        called).  A connection is considered lost when the asyncpg pool/connection
        surface drops it — the caller is responsible for setting
        ``self._connection = None`` in that path (handled in
        ``_drop_connection``).

        Because asyncpg's listen/notify is callback-based there is no blocking
        coroutine to ``await`` inside this loop; we instead poll ``_connection``
        at a short interval when connected, and apply back-off only during
        reconnect attempts.
        """
        stop_event = self._stop_event
        attempt = 0
        _POLL_INTERVAL = 0.5  # seconds between "am I still connected?" checks

        while True:
            # Respect stop signal.
            if stop_event is not None and stop_event.is_set():
                return

            # While connected, just sleep briefly and re-check.
            if self._connection is not None and self._running:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(stop_event.wait()) if stop_event is not None
                        else asyncio.sleep(_POLL_INTERVAL),
                        timeout=_POLL_INTERVAL,
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    pass
                except asyncio.CancelledError:
                    return
                continue

            # Connection is gone but we haven't been asked to stop → reconnect.
            if not self._running:
                return

            # Check max attempts limit.
            if self._reconnect_max_attempts is not None and attempt >= self._reconnect_max_attempts:
                logger.warning(
                    "Postgres live notification listener exhausted reconnect attempts "
                    "(channel=%s, attempts=%d)",
                    self._channel,
                    attempt,
                    extra={
                        "event": "postgres_live_listener_reconnect_exhausted",
                        "channel": self._channel,
                        "attempts": attempt,
                    },
                )
                self._running = False
                return

            # Compute back-off delay with jitter.
            raw_delay = min(self._reconnect_cap, self._reconnect_base * (2 ** attempt))
            jitter = raw_delay * _RECONNECT_JITTER_FACTOR
            delay = raw_delay + random.uniform(-jitter, jitter)
            delay = max(0.0, delay)

            logger.warning(
                "Postgres live notification listener lost connection — reconnecting in %.1fs "
                "(channel=%s, attempt=%d)",
                delay,
                self._channel,
                attempt + 1,
                extra={
                    "event": "postgres_live_listener_reconnect_backoff",
                    "channel": self._channel,
                    "attempt": attempt + 1,
                    "delay_seconds": delay,
                },
            )

            # Interruptible sleep: stop_event or task cancellation exits early.
            try:
                if stop_event is not None:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=delay)
                        return  # stop was signalled during sleep
                    except (asyncio.TimeoutError, TimeoutError):
                        pass
                else:
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            if stop_event is not None and stop_event.is_set():
                return

            # Attempt to reconnect.
            try:
                await self._connect_once()
                self._reconnect_count += 1
                attempt = 0  # reset backoff on success
                logger.info(
                    "Postgres live notification listener reconnected successfully (channel=%s)",
                    self._channel,
                    extra={
                        "event": "postgres_live_listener_reconnected",
                        "channel": self._channel,
                    },
                )
            except Exception as exc:
                attempt += 1
                self._record_error("reconnect", exc, channel=self._channel, attempt=attempt)
                logger.warning(
                    "Postgres live notification listener reconnect failed "
                    "(channel=%s, attempt=%d, error=%s)",
                    self._channel,
                    attempt,
                    exc,
                    extra={
                        "event": "postgres_live_listener_reconnect_failed",
                        "channel": self._channel,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                    exc_info=True,
                )

    def _drop_connection(self) -> None:
        """Mark the current connection as lost so the reconnect loop re-establishes it.

        Called from ``_handle_notification`` if the connection object signals an
        EOF/closed state.  External callers (e.g. a pool eviction hook) may also
        invoke this directly.
        """
        if self._connection is not None:
            self._connection = None

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
