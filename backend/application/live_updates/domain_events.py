"""Domain-oriented helpers for emitting live update payloads."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.live_updates.runtime_state import publish_live_append, publish_live_invalidation
from backend.application.live_updates.topics import (
    execution_run_topic,
    feature_topic,
    project_features_topic,
    project_ops_topic,
    project_tests_topic,
    session_topic,
    session_transcript_topic,
)


@dataclass(frozen=True, slots=True)
class SessionTranscriptAppendPayload:
    session_id: str
    entry_id: str
    sequence_no: int
    kind: str
    created_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)


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


async def publish_session_transcript_append(payload: SessionTranscriptAppendPayload) -> None:
    session_id = _as_text(payload.session_id)
    entry_id = _as_text(payload.entry_id)
    if not session_id or not entry_id:
        return
    await publish_live_append(
        topic=session_transcript_topic(session_id),
        occurred_at=_as_text(payload.created_at) or None,
        payload={
            "sessionId": session_id,
            "entryId": entry_id,
            "sequenceNo": max(0, int(payload.sequence_no or 0)),
            "kind": _as_text(payload.kind),
            "createdAt": _as_text(payload.created_at),
            "payload": dict(payload.payload or {}),
        },
    )


async def publish_feature_invalidation(
    project_id: str,
    *,
    feature_id: str | None = None,
    reason: str,
    source: str,
    payload: dict[str, Any] | None = None,
    occurred_at: str | None = None,
) -> None:
    normalized_project_id = _as_text(project_id)
    normalized_feature_id = _as_text(feature_id)
    base_payload = {
        "resource": "feature",
        "projectId": normalized_project_id,
        "featureId": normalized_feature_id,
        "reason": reason,
        "source": source,
    }
    if payload:
        base_payload.update(payload)
    if normalized_feature_id:
        await publish_live_invalidation(
            topic=feature_topic(normalized_feature_id),
            occurred_at=occurred_at,
            payload=base_payload,
        )
    if normalized_project_id:
        await publish_live_invalidation(
            topic=project_features_topic(normalized_project_id),
            occurred_at=occurred_at,
            payload=base_payload,
        )


async def publish_test_invalidation(
    project_id: str,
    *,
    reason: str,
    source: str,
    payload: dict[str, Any] | None = None,
    occurred_at: str | None = None,
) -> None:
    normalized_project_id = _as_text(project_id)
    if not normalized_project_id:
        return
    base_payload = {
        "resource": "tests",
        "projectId": normalized_project_id,
        "reason": reason,
        "source": source,
    }
    if payload:
        base_payload.update(payload)
    await publish_live_invalidation(
        topic=project_tests_topic(normalized_project_id),
        occurred_at=occurred_at,
        payload=base_payload,
    )


async def publish_ops_invalidation(
    project_id: str,
    *,
    reason: str,
    source: str,
    payload: dict[str, Any] | None = None,
    occurred_at: str | None = None,
) -> None:
    normalized_project_id = _as_text(project_id)
    if not normalized_project_id:
        return
    base_payload = {
        "resource": "ops",
        "projectId": normalized_project_id,
        "reason": reason,
        "source": source,
    }
    if payload:
        base_payload.update(payload)
    await publish_live_invalidation(
        topic=project_ops_topic(normalized_project_id),
        occurred_at=occurred_at,
        payload=base_payload,
    )
