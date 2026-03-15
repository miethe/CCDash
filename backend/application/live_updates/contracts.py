"""Transport-agnostic live update event contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping


LiveEventKind = Literal["append", "invalidate", "heartbeat", "snapshot_required"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class LiveDeliveryHint:
    replayable: bool = True
    recovery_hint: str | None = None


@dataclass(frozen=True, slots=True)
class LiveTopicCursor:
    topic: str
    sequence: int


@dataclass(frozen=True, slots=True)
class LiveTopicAuthorization:
    topic: str
    project_id: str | None
    resource: str
    action: str = "live_updates:subscribe"


@dataclass(frozen=True, slots=True)
class LiveEventMessage:
    topic: str
    kind: LiveEventKind
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=utc_now_iso)
    delivery: LiveDeliveryHint = field(default_factory=LiveDeliveryHint)


@dataclass(frozen=True, slots=True)
class LiveEventEnvelope:
    topic: str
    kind: LiveEventKind
    cursor: str
    sequence: int
    occurred_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    delivery: LiveDeliveryHint = field(default_factory=LiveDeliveryHint)
