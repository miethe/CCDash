"""Cross-process live event bus contracts and compact envelopes."""
from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from backend.application.live_updates.contracts import (
    LiveDeliveryHint,
    LiveEventKind,
    LiveEventMessage,
    utc_now_iso,
)
from backend.application.live_updates.topics import normalize_topic


CCDASH_LIVE_EVENT_APP = "ccdash"
LIVE_EVENT_BUS_VERSION = 1
DEFAULT_BUS_RECOVERY_HINT = "rest_snapshot"

_ALLOWED_KINDS = {"append", "invalidate", "heartbeat", "snapshot_required"}
# Cross-process field allowlist: only keys listed here survive Postgres NOTIFY
# fanout via compact_live_event_payload().  Any field a downstream consumer
# (frontend SSE listener, other API process) needs to receive cross-process MUST
# be added here.  Fields absent from this tuple are silently stripped before the
# envelope is serialised for transport.  Adding a key is a contract change:
# verify all SSE consumers handle the new field before landing it.
# Candidates for future addition (deferred, do not add yet):
#   runtimeProfile, agentId
_COMPACT_PAYLOAD_KEYS = (
    "resource",
    "projectId",
    "featureId",
    "sessionId",
    "entryId",
    "runId",
    "phaseNumber",
    "sequenceNo",
    "kind",
    "status",
    "reason",
    "source",
    "createdAt",
    "updatedAt",
    "occurredAt",
    "logCount",
    "stream",
    "eventType",
)
_MAX_COMPACT_STRING_CHARS = 256


class LiveEventBusError(RuntimeError):
    """Base error for cross-process live event bus failures."""


class LiveEventBusPayloadTooLarge(LiveEventBusError):
    """Raised before transport publish when a compact envelope cannot fit."""


@dataclass(frozen=True, slots=True)
class LiveEventBusEnvelope:
    """Compact event shape intended for inter-process fanout.

    The bus is not the replay buffer and does not assign cursors. For v1, append
    deltas are downgraded to invalidations before crossing process boundaries so
    listeners can recover through their normal REST snapshot paths.
    """

    topic: str
    kind: LiveEventKind
    occurred_at: str = field(default_factory=utc_now_iso)
    payload: Mapping[str, Any] = field(default_factory=dict)
    source_kind: LiveEventKind | None = None
    recovery_hint: str | None = DEFAULT_BUS_RECOVERY_HINT
    application: str = CCDASH_LIVE_EVENT_APP
    version: int = LIVE_EVENT_BUS_VERSION
    payload_compacted: bool = False


@runtime_checkable
class LiveEventBusSubscription(Protocol):
    async def next_envelope(self, *, timeout_seconds: float | None = None) -> LiveEventBusEnvelope | None:
        """Return the next cross-process live event envelope, if available."""
        ...

    async def close(self) -> None:
        """Release subscription resources."""
        ...


@runtime_checkable
class LiveEventBusPublisher(Protocol):
    async def publish(self, event: LiveEventMessage) -> LiveEventBusEnvelope:
        """Publish one live event to the cross-process bus."""
        ...


@runtime_checkable
class LiveEventBusSubscriber(Protocol):
    async def open_subscription(self) -> LiveEventBusSubscription:
        """Open a subscription to the cross-process bus."""
        ...


@runtime_checkable
class LiveEventBus(LiveEventBusPublisher, LiveEventBusSubscriber, Protocol):
    async def close(self) -> None:
        """Release bus resources."""
        ...


def compact_live_event_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic, bounded, invalidation-safe payload subset."""

    source = dict(payload or {})
    compact: dict[str, Any] = {}
    for key in _COMPACT_PAYLOAD_KEYS:
        if key not in source:
            continue
        value = _compact_payload_value(source[key])
        if value is not _SKIP_VALUE:
            compact[key] = value
    return compact


def live_event_bus_envelope_from_message(
    event: LiveEventMessage,
    *,
    invalidation_only: bool = True,
) -> LiveEventBusEnvelope:
    """Build a bus envelope from a local live event message."""

    topic = normalize_topic(event.topic)
    source_kind = event.kind
    kind: LiveEventKind = event.kind
    recovery_hint = event.delivery.recovery_hint
    payload_compacted = False
    if invalidation_only and event.kind == "append":
        kind = "invalidate"
        recovery_hint = recovery_hint or DEFAULT_BUS_RECOVERY_HINT
        payload_compacted = True
    elif invalidation_only and event.kind == "invalidate":
        recovery_hint = recovery_hint or DEFAULT_BUS_RECOVERY_HINT

    compact_payload = compact_live_event_payload(event.payload)
    if compact_payload != dict(event.payload or {}):
        payload_compacted = True

    return LiveEventBusEnvelope(
        topic=topic,
        kind=kind,
        occurred_at=event.occurred_at,
        payload=compact_payload,
        source_kind=source_kind if source_kind != kind else None,
        recovery_hint=recovery_hint,
        payload_compacted=payload_compacted,
    )


def encode_live_event_bus_envelope(
    envelope: LiveEventBusEnvelope,
    *,
    include_payload: bool = True,
) -> str:
    """Serialize a bus envelope using compact stable JSON keys."""

    body: dict[str, Any] = {
        "v": int(envelope.version),
        "app": str(envelope.application),
        "t": normalize_topic(envelope.topic),
        "k": _validate_kind(envelope.kind),
        "at": str(envelope.occurred_at or utc_now_iso()),
    }
    if envelope.source_kind:
        body["sk"] = _validate_kind(envelope.source_kind)
    if envelope.recovery_hint:
        body["rh"] = str(envelope.recovery_hint)
    if include_payload and envelope.payload:
        body["p"] = compact_live_event_payload(envelope.payload)
    if envelope.payload_compacted:
        body["pc"] = True
    return json.dumps(body, separators=(",", ":"), sort_keys=True)


def decode_live_event_bus_envelope(raw_payload: str) -> LiveEventBusEnvelope:
    """Parse a compact bus envelope emitted by the shared fanout transport."""

    try:
        raw = json.loads(str(raw_payload or ""))
    except Exception as exc:
        raise ValueError("Live event bus payload is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Live event bus payload must be a JSON object.")
    application = str(raw.get("app") or "")
    if application != CCDASH_LIVE_EVENT_APP:
        raise ValueError("Live event bus payload is not scoped to CCDash.")
    version = int(raw.get("v") or 0)
    if version != LIVE_EVENT_BUS_VERSION:
        raise ValueError(f"Unsupported live event bus version: {version}.")
    payload = raw.get("p")
    return LiveEventBusEnvelope(
        topic=normalize_topic(str(raw.get("t") or "")),
        kind=_validate_kind(raw.get("k")),
        occurred_at=str(raw.get("at") or utc_now_iso()),
        payload=compact_live_event_payload(payload if isinstance(payload, MappingABC) else {}),
        source_kind=_validate_optional_kind(raw.get("sk")),
        recovery_hint=str(raw.get("rh") or "") or None,
        application=application,
        version=version,
        payload_compacted=bool(raw.get("pc")),
    )


def live_event_message_from_bus_envelope(envelope: LiveEventBusEnvelope) -> LiveEventMessage:
    """Convert a bus envelope back to a broker publish message."""

    return LiveEventMessage(
        topic=normalize_topic(envelope.topic),
        kind=envelope.kind,
        payload=dict(envelope.payload or {}),
        occurred_at=envelope.occurred_at,
        delivery=LiveDeliveryHint(replayable=False, recovery_hint=envelope.recovery_hint),
    )


class _SkipValue:
    pass


_SKIP_VALUE = _SkipValue()


def _compact_payload_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= _MAX_COMPACT_STRING_CHARS:
            return value
        return value[: _MAX_COMPACT_STRING_CHARS - 3] + "..."
    return _SKIP_VALUE


def _validate_kind(value: Any) -> LiveEventKind:
    kind = str(value or "")
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"Invalid live event kind '{value}'.")
    return kind  # type: ignore[return-value]


def _validate_optional_kind(value: Any) -> LiveEventKind | None:
    if value is None or str(value or "") == "":
        return None
    return _validate_kind(value)
