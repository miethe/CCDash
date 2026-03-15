"""SSE framing and stream orchestration for live updates."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from backend.application.live_updates import (
    LiveDeliveryHint,
    LiveEventEnvelope,
    LiveReplayGap,
    LiveSubscriptionStart,
)
from backend.application.live_updates.contracts import utc_now_iso


_HEARTBEAT_TOPIC = "system.heartbeat"


def encode_sse_frame(
    *,
    event: str,
    data: dict[str, Any],
    event_id: str | None = None,
) -> bytes:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    for line in json.dumps(data, separators=(",", ":"), sort_keys=True).splitlines() or ["{}"]:
        lines.append(f"data: {line}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def encode_live_event(event: LiveEventEnvelope) -> bytes:
    return encode_sse_frame(
        event=event.kind,
        event_id=event.cursor,
        data={
            "topic": event.topic,
            "kind": event.kind,
            "cursor": event.cursor,
            "sequence": event.sequence,
            "occurredAt": event.occurred_at,
            "payload": dict(event.payload),
            "delivery": {
                "replayable": bool(event.delivery.replayable),
                "recoveryHint": event.delivery.recovery_hint,
            },
        },
    )


def encode_snapshot_required(gap: LiveReplayGap) -> bytes:
    return encode_sse_frame(
        event="snapshot_required",
        data={
            "topic": gap.topic,
            "kind": "snapshot_required",
            "cursor": None,
            "sequence": None,
            "occurredAt": utc_now_iso(),
            "payload": {
                "reason": gap.reason,
                "requestedSequence": gap.requested_sequence,
                "oldestAvailableSequence": gap.oldest_available_sequence,
                "latestSequence": gap.latest_sequence,
            },
            "delivery": {
                "replayable": False,
                "recoveryHint": "rest_snapshot",
            },
        },
    )


def encode_heartbeat(*, active_topics: tuple[str, ...]) -> bytes:
    return encode_sse_frame(
        event="heartbeat",
        data={
            "topic": _HEARTBEAT_TOPIC,
            "kind": "heartbeat",
            "cursor": None,
            "sequence": None,
            "occurredAt": utc_now_iso(),
            "payload": {"topics": list(active_topics)},
            "delivery": {
                "replayable": False,
                "recoveryHint": None,
            },
        },
    )


async def iter_live_sse_stream(
    *,
    request: Any,
    start: LiveSubscriptionStart,
    heartbeat_interval_seconds: float,
) -> AsyncIterator[bytes]:
    try:
        for event in start.replay_events:
            if await request.is_disconnected():
                return
            yield encode_live_event(event)
        for gap in start.replay_gaps:
            if await request.is_disconnected():
                return
            yield encode_snapshot_required(gap)
        while True:
            if await request.is_disconnected():
                return
            next_event = await start.subscription.next_event(timeout_seconds=heartbeat_interval_seconds)
            if next_event is None:
                yield encode_heartbeat(active_topics=start.subscription.topics)
                continue
            yield encode_live_event(next_event)
    finally:
        await start.subscription.close()
