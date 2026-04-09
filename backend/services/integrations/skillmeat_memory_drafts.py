"""Deterministic session-memory draft extraction for SkillMeat review flows."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.application.services.sessions import SessionTranscriptService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_text(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hash_for_candidate(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _slug_label(value: str) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    return "-".join(part for part in token.split("-") if part) or "session-intelligence"


def _module_name(session_row: dict[str, Any], observation: dict[str, Any] | None) -> str:
    workflow_ref = _first_text(observation or {}, "workflow_ref", "workflowRef")
    feature_id = _first_text(session_row, "feature_id", "featureId", "task_id", "taskId")
    if workflow_ref:
        return f"Workflow {_slug_label(workflow_ref)} memory"
    if feature_id:
        return f"Feature {_slug_label(feature_id)} memory"
    return "Session intelligence memory"


def _module_description(session_row: dict[str, Any], observation: dict[str, Any] | None) -> str:
    workflow_ref = _first_text(observation or {}, "workflow_ref", "workflowRef")
    if workflow_ref:
        return f"Review-gated memory drafts derived from successful sessions for workflow '{workflow_ref}'."
    feature_id = _first_text(session_row, "feature_id", "featureId", "task_id", "taskId")
    if feature_id:
        return f"Review-gated memory drafts derived from successful sessions for feature '{feature_id}'."
    return "Review-gated memory drafts derived from successful CCDash sessions."


def _top_sentiment(sentiment_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in sentiment_rows if str(row.get("sentiment_label") or "") in {"positive", "negative"}]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            -abs(_safe_float(row.get("sentiment_score"))),
            -_safe_float(row.get("confidence")),
            _safe_int(row.get("message_index")),
        ),
    )[0]


def _top_churn(churn_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in churn_rows
        if bool(row.get("low_progress_loop")) or _safe_float(row.get("churn_score")) >= 0.55
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            -_safe_float(row.get("churn_score")),
            -_safe_int(row.get("touch_count")),
            str(row.get("file_path") or ""),
        ),
    )[0]


def _top_scope(scope_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in scope_rows if _safe_float(row.get("drift_ratio")) >= 0.25]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            -_safe_float(row.get("drift_ratio")),
            -_safe_int(row.get("out_of_scope_path_count")),
        ),
    )[0]


def _fallback_learning(transcript_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    assistant_logs = [row for row in transcript_logs if str(row.get("speaker") or "").lower() in {"assistant", "agent"}]
    if not assistant_logs:
        return None
    row = assistant_logs[-1]
    content = _first_text(row, "content")
    if not content:
        return None
    return {
        "kind": "learning",
        "title": "Session outcome summary",
        "content": f"Carry forward this outcome from the successful session: {content[:280]}",
        "confidence": 0.58,
        "source_message_id": _first_text(row, "id"),
        "source_log_id": _first_text(row, "id"),
        "source_message_index": 0,
        "evidence": {
            "source": "transcript_fallback",
            "contentSample": content[:280],
        },
    }


def build_memory_draft_candidates(
    session_row: dict[str, Any],
    transcript_logs: list[dict[str, Any]],
    sentiment_rows: list[dict[str, Any]],
    churn_rows: list[dict[str, Any]],
    scope_rows: list[dict[str, Any]],
    observation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    top_sentiment = _top_sentiment(sentiment_rows)
    if top_sentiment is not None:
        evidence = top_sentiment.get("evidence_json") if isinstance(top_sentiment.get("evidence_json"), dict) else {}
        label = str(top_sentiment.get("sentiment_label") or "learning")
        content_sample = str(evidence.get("contentSample") or "").strip()
        memory_type = "gotcha" if label == "negative" else "learning"
        prefix = "Watch for this failure mode" if label == "negative" else "Keep this successful pattern"
        candidates.append(
            {
                "kind": memory_type,
                "title": "Transcript-derived user signal",
                "content": f"{prefix}: {content_sample[:280]}",
                "confidence": max(0.55, _safe_float(top_sentiment.get("confidence"))),
                "source_message_id": _first_text(top_sentiment, "source_message_id"),
                "source_log_id": _first_text(top_sentiment, "source_log_id"),
                "source_message_index": _safe_int(top_sentiment.get("message_index")),
                "evidence": {
                    "source": "session_sentiment_facts",
                    "sentimentLabel": label,
                    "sentimentScore": _safe_float(top_sentiment.get("sentiment_score")),
                    "contentSample": content_sample[:280],
                    "matchedCueCount": _safe_int(evidence.get("matchedCueCount")),
                },
            }
        )

    top_churn = _top_churn(churn_rows)
    if top_churn is not None:
        candidates.append(
            {
                "kind": "gotcha",
                "title": "High rewrite churn warning",
                "content": (
                    f"Avoid repeated rewrite loops in {str(top_churn.get('file_path') or 'unknown file')}: "
                    f"{_safe_int(top_churn.get('touch_count'))} edits across "
                    f"{_safe_int(top_churn.get('distinct_edit_turn_count'))} turns produced "
                    f"churn score {_safe_float(top_churn.get('churn_score')):.2f}."
                ),
                "confidence": max(0.62, _safe_float(top_churn.get("confidence"))),
                "source_message_id": "",
                "source_log_id": _first_text(top_churn, "first_source_log_id"),
                "source_message_index": _safe_int(top_churn.get("first_message_index")),
                "evidence": {
                    "source": "session_code_churn_facts",
                    "filePath": str(top_churn.get("file_path") or ""),
                    "touchCount": _safe_int(top_churn.get("touch_count")),
                    "rewritePassCount": _safe_int(top_churn.get("rewrite_pass_count")),
                    "churnScore": _safe_float(top_churn.get("churn_score")),
                    "progressScore": _safe_float(top_churn.get("progress_score")),
                },
            }
        )

    top_scope = _top_scope(scope_rows)
    if top_scope is not None:
        scope_evidence = top_scope.get("evidence_json") if isinstance(top_scope.get("evidence_json"), dict) else {}
        out_of_scope = scope_evidence.get("outOfScopePaths")
        candidates.append(
            {
                "kind": "constraint",
                "title": "Scope boundary reminder",
                "content": (
                    f"Keep work inside the planned scope: this session touched "
                    f"{_safe_int(top_scope.get('out_of_scope_path_count'))} out-of-scope paths "
                    f"with drift ratio {_safe_float(top_scope.get('drift_ratio')):.2f}."
                ),
                "confidence": max(0.65, _safe_float(top_scope.get("confidence"))),
                "source_message_id": "",
                "source_log_id": "",
                "source_message_index": 0,
                "evidence": {
                    "source": "session_scope_drift_facts",
                    "driftRatio": _safe_float(top_scope.get("drift_ratio")),
                    "outOfScopePathCount": _safe_int(top_scope.get("out_of_scope_path_count")),
                    "outOfScopePaths": out_of_scope if isinstance(out_of_scope, list) else [],
                },
            }
        )

    if not candidates:
        fallback = _fallback_learning(transcript_logs)
        if fallback is not None:
            candidates.append(fallback)
    return candidates


async def generate_session_memory_drafts(
    context: Any,
    ports: Any,
    *,
    project: Any,
    session_id: str = "",
    limit: int = 25,
    actor: str = "system",
) -> dict[str, Any]:
    session_repo = ports.storage.sessions()
    intelligence_repo = ports.storage.session_intelligence()
    agentic_repo = ports.storage.agentic_intelligence()
    transcript_service = SessionTranscriptService()

    if session_id.strip():
        candidate_rows = [await session_repo.get_by_id(session_id.strip())]
        candidate_rows = [row for row in candidate_rows if row and str(row.get("project_id") or "") == str(project.id)]
    else:
        candidate_rows = await session_repo.list_paginated(
            0,
            limit,
            project.id,
            filters={"status": "completed", "include_subagents": False},
        )

    drafts_created = 0
    drafts_updated = 0
    drafts_skipped = 0
    stored_items: list[dict[str, Any]] = []

    for session_row in candidate_rows:
        if not session_row:
            continue
        current_session_id = _first_text(session_row, "id")
        if not current_session_id:
            drafts_skipped += 1
            continue
        transcript_logs = await transcript_service.list_session_logs(session_row, ports)
        sentiment_rows = await intelligence_repo.list_session_sentiment_facts(current_session_id)
        churn_rows = await intelligence_repo.list_session_code_churn_facts(current_session_id)
        scope_rows = await intelligence_repo.list_session_scope_drift_facts(current_session_id)
        observation = await agentic_repo.get_stack_observation(str(project.id), current_session_id)
        module_name = _module_name(session_row, observation)
        module_description = _module_description(session_row, observation)
        workflow_ref = _first_text(observation or {}, "workflow_ref", "workflowRef")
        feature_id = _first_text(session_row, "feature_id", "featureId", "task_id", "taskId")
        root_session_id = _first_text(session_row, "root_session_id", "rootSessionId", default=current_session_id)
        thread_session_id = _first_text(session_row, "thread_session_id", "threadSessionId", default=current_session_id)

        candidates = build_memory_draft_candidates(
            session_row,
            transcript_logs,
            sentiment_rows,
            churn_rows,
            scope_rows,
            observation,
        )
        if not candidates:
            drafts_skipped += 1
            continue

        for candidate in candidates:
            payload_for_hash = {
                "projectId": str(project.id),
                "sessionId": current_session_id,
                "memoryType": candidate["kind"],
                "title": candidate["title"],
                "content": candidate["content"],
                "moduleName": module_name,
                "workflowRef": workflow_ref,
                "featureId": feature_id,
            }
            content_hash = _hash_for_candidate(payload_for_hash)
            existing_total = await agentic_repo.count_session_memory_drafts(
                str(project.id),
                session_id=current_session_id,
            )
            stored = await agentic_repo.upsert_session_memory_draft(
                {
                    "project_id": str(project.id),
                    "session_id": current_session_id,
                    "feature_id": feature_id,
                    "root_session_id": root_session_id,
                    "thread_session_id": thread_session_id,
                    "workflow_ref": workflow_ref,
                    "title": candidate["title"],
                    "memory_type": candidate["kind"],
                    "status": "draft",
                    "module_name": module_name,
                    "module_description": module_description,
                    "content": candidate["content"],
                    "confidence": candidate["confidence"],
                    "source_message_id": candidate["source_message_id"],
                    "source_log_id": candidate["source_log_id"],
                    "source_message_index": candidate["source_message_index"],
                    "content_hash": content_hash,
                    "evidence": {
                        "actor": actor,
                        "sessionStatus": _first_text(session_row, "status", default="completed"),
                        "workflowRef": workflow_ref,
                        **(candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}),
                    },
                },
                str(project.id),
            )
            if stored.get("created_at") == stored.get("updated_at") and existing_total == 0:
                drafts_created += 1
            elif stored:
                drafts_updated += 1
            stored_items.append(stored)

    return {
        "projectId": str(project.id),
        "generatedAt": _now_iso(),
        "sessionsConsidered": len(candidate_rows),
        "draftsCreated": drafts_created,
        "draftsUpdated": drafts_updated,
        "draftsSkipped": drafts_skipped,
        "items": stored_items,
    }
