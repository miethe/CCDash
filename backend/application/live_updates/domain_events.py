"""Domain-oriented helpers for emitting live update payloads."""
from __future__ import annotations

from typing import Any

from backend.application.live_updates.runtime_state import publish_live_append, publish_live_invalidation
from backend.application.live_updates.topics import execution_run_topic, session_topic


def _as_text(value: Any) -> str:
    return str(value or "")


async def publish_execution_run_snapshot(run_row: dict[str, Any] | None) -> None:
    if not run_row:
        return
    run_id = _as_text(run_row.get("id"))
    if not run_id:
        return
    await publish_live_invalidation(
        topic=execution_run_topic(run_id),
        occurred_at=_as_text(run_row.get("updated_at")) or None,
        payload={
            "resource": "run",
            "runId": run_id,
            "featureId": _as_text(run_row.get("feature_id")),
            "status": _as_text(run_row.get("status")),
            "updatedAt": _as_text(run_row.get("updated_at")),
            "startedAt": _as_text(run_row.get("started_at")),
            "endedAt": _as_text(run_row.get("ended_at")),
            "exitCode": run_row.get("exit_code"),
            "requiresApproval": bool(run_row.get("requires_approval")),
        },
    )


async def publish_execution_run_events(run_id: str, events: list[dict[str, Any]]) -> None:
    topic = execution_run_topic(run_id)
    for event in events:
        await publish_live_append(
            topic=topic,
            occurred_at=_as_text(event.get("occurred_at")) or None,
            payload={
                "runId": run_id,
                "sequenceNo": int(event.get("sequence_no") or 0),
                "stream": _as_text(event.get("stream")) or "system",
                "eventType": _as_text(event.get("event_type")) or "status",
                "payloadText": _as_text(event.get("payload_text")),
                "payload": event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {},
                "occurredAt": _as_text(event.get("occurred_at")),
            },
        )


async def publish_session_snapshot(session_row: dict[str, Any], *, log_count: int, source: str) -> None:
    session_id = _as_text(session_row.get("id"))
    if not session_id:
        return
    await publish_live_invalidation(
        topic=session_topic(session_id),
        occurred_at=_as_text(session_row.get("updatedAt") or session_row.get("updated_at")) or None,
        payload={
            "resource": "session",
            "sessionId": session_id,
            "status": _as_text(session_row.get("status")),
            "updatedAt": _as_text(session_row.get("updatedAt") or session_row.get("updated_at")),
            "logCount": max(0, int(log_count or 0)),
            "source": source,
        },
    )

