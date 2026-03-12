"""Build immutable session usage events and derived attribution links."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_WORKFLOW_TOKEN_RE = re.compile(r"[^a-z0-9]+")

_PRIMARY_PRIORITY = {
    "explicit_skill_invocation": 500,
    "explicit_subthread_ownership": 450,
    "explicit_agent_ownership": 425,
    "explicit_command_context": 400,
    "explicit_artifact_link": 350,
}


def _safe_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _first_non_empty(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _normalize_command_id(raw: str) -> str:
    command = " ".join(str(raw or "").strip().split())
    if not command:
        return ""
    lowered = command.lower()
    if len(lowered) <= 160:
        return lowered
    digest = hashlib.sha1(lowered.encode("utf-8")).hexdigest()[:12]
    return f"{lowered[:120]}#{digest}"


def _normalize_workflow_id(raw: str) -> str:
    lowered = str(raw or "").strip().lower()
    if not lowered:
        return ""
    return _WORKFLOW_TOKEN_RE.sub("_", lowered).strip("_")


def _event_id(
    project_id: str,
    session_id: str,
    source_log_id: str,
    event_kind: str,
    token_family: str,
) -> str:
    raw = f"{project_id}|{session_id}|{source_log_id}|{event_kind}|{token_family}"
    return f"usage-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def _normalize_log_rows(logs: list[dict[str, Any]], fallback_timestamp: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for fallback_index, log in enumerate(logs):
        metadata = _safe_json_dict(log.get("metadata_json") or log.get("metadata"))
        tool_call = log.get("toolCall") if isinstance(log.get("toolCall"), dict) else {}
        log_index = _coerce_int(log.get("log_index") if log.get("log_index") is not None else log.get("logIndex"))
        normalized.append(
            {
                "log_index": log_index if log_index > 0 or fallback_index == 0 else fallback_index,
                "source_log_id": _first_non_empty(
                    log,
                    "source_log_id",
                    "sourceLogId",
                    "id",
                    default=f"log-{fallback_index}",
                ),
                "timestamp": _first_non_empty(log, "timestamp", default=fallback_timestamp),
                "type": _first_non_empty(log, "type"),
                "content": _first_non_empty(log, "content"),
                "agent_name": _first_non_empty(log, "agent_name", "agentName"),
                "tool_name": _first_non_empty(log, "tool_name") or str(tool_call.get("name") or "").strip(),
                "linked_session_id": _first_non_empty(log, "linked_session_id", "linkedSessionId"),
                "tool_status": _first_non_empty(log, "tool_status") or str(tool_call.get("status") or "").strip(),
                "metadata": metadata,
            }
        )
    normalized.sort(key=lambda row: (int(row["log_index"]), str(row["source_log_id"])))
    return normalized


def build_session_usage_events(
    project_id: str,
    session_payload: dict[str, Any],
    logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    session_id = _first_non_empty(session_payload, "id")
    if not session_id:
        return []

    root_session_id = _first_non_empty(session_payload, "rootSessionId", "root_session_id", default=session_id)
    session_model = _first_non_empty(session_payload, "model")
    started_at = _first_non_empty(
        session_payload,
        "startedAt",
        "started_at",
        "createdAt",
        "created_at",
    )
    normalized_logs = _normalize_log_rows(logs, started_at)
    events: list[dict[str, Any]] = []

    def push_event(
        *,
        source_log_id: str,
        captured_at: str,
        event_kind: str,
        token_family: str,
        delta_tokens: int,
        model: str = "",
        tool_name: str = "",
        agent_name: str = "",
        linked_session_id: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        if delta_tokens <= 0:
            return
        events.append(
            {
                "id": _event_id(project_id, session_id, source_log_id, event_kind, token_family),
                "project_id": project_id,
                "session_id": session_id,
                "root_session_id": root_session_id,
                "linked_session_id": linked_session_id,
                "source_log_id": source_log_id,
                "captured_at": captured_at or started_at,
                "event_kind": event_kind,
                "model": model or session_model,
                "tool_name": tool_name,
                "agent_name": agent_name,
                "token_family": token_family,
                "delta_tokens": delta_tokens,
                "cost_usd_model_io": 0.0,
                "metadata_json": metadata_json or {},
            }
        )

    for row in normalized_logs:
        metadata = row["metadata"]
        common_metadata = {
            "logIndex": row["log_index"],
            "logType": row["type"],
        }
        for key in (
            "toolLabel",
            "toolCategory",
            "bashCommand",
            "taskName",
            "taskDescription",
            "taskPromptPreview",
            "subagentAgentId",
            "planStatus",
        ):
            value = metadata.get(key)
            if value not in (None, "", [], {}):
                common_metadata[key] = value
        parsed_command = metadata.get("parsedCommand")
        if isinstance(parsed_command, dict) and parsed_command:
            common_metadata["parsedCommand"] = parsed_command

        if str(row["type"]) == "message":
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="message",
                token_family="model_input",
                delta_tokens=_coerce_int(metadata.get("inputTokens")),
                model=str(metadata.get("model") or session_model),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=common_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="message",
                token_family="model_output",
                delta_tokens=_coerce_int(metadata.get("outputTokens")),
                model=str(metadata.get("model") or session_model),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=common_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="message",
                token_family="cache_creation_input",
                delta_tokens=_coerce_int(metadata.get("cache_creation_input_tokens")),
                model=str(metadata.get("model") or session_model),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=common_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="message",
                token_family="cache_read_input",
                delta_tokens=_coerce_int(metadata.get("cache_read_input_tokens")),
                model=str(metadata.get("model") or session_model),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=common_metadata,
            )

        nested_usage = _safe_json_dict(metadata.get("toolUseResult_usage"))
        if nested_usage:
            tool_metadata = dict(common_metadata)
            for key in ("service_tier", "inference_geo", "speed", "iterations", "server_tool_use"):
                value = nested_usage.get(key)
                if value not in (None, "", [], {}):
                    tool_metadata[key] = value
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="tool_result",
                token_family="tool_result_input",
                delta_tokens=_coerce_int(nested_usage.get("input_tokens")),
                tool_name=str(row["tool_name"]),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=tool_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="tool_result",
                token_family="tool_result_output",
                delta_tokens=_coerce_int(nested_usage.get("output_tokens")),
                tool_name=str(row["tool_name"]),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=tool_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="tool_result",
                token_family="tool_result_cache_creation_input",
                delta_tokens=_coerce_int(nested_usage.get("cache_creation_input_tokens")),
                tool_name=str(row["tool_name"]),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=tool_metadata,
            )
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="tool_result",
                token_family="tool_result_cache_read_input",
                delta_tokens=_coerce_int(nested_usage.get("cache_read_input_tokens")),
                tool_name=str(row["tool_name"]),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=tool_metadata,
            )

        reported_total = _coerce_int(metadata.get("toolUseResult_totalTokens"))
        if reported_total > 0:
            push_event(
                source_log_id=str(row["source_log_id"]),
                captured_at=str(row["timestamp"]),
                event_kind="tool_result_reported",
                token_family="tool_reported_total",
                delta_tokens=reported_total,
                tool_name=str(row["tool_name"]),
                agent_name=str(row["agent_name"]),
                linked_session_id=str(row["linked_session_id"]),
                metadata_json=common_metadata,
            )

    session_forensics = _safe_json_dict(session_payload.get("sessionForensics") or session_payload.get("session_forensics_json"))
    usage_summary = _safe_json_dict(session_forensics.get("usageSummary"))
    relay_totals = _safe_json_dict(usage_summary.get("relayMirrorTotals"))
    if relay_totals:
        relay_metadata = {
            "policy": relay_totals.get("policy"),
            "excludedCount": _coerce_int(relay_totals.get("excludedCount")),
        }
        relay_timestamp = _first_non_empty(session_payload, "endedAt", "ended_at", default=started_at)
        push_event(
            source_log_id="relay-summary",
            captured_at=relay_timestamp,
            event_kind="relay_mirror_summary",
            token_family="relay_mirror_input",
            delta_tokens=_coerce_int(relay_totals.get("inputTokens")),
            metadata_json=relay_metadata,
        )
        push_event(
            source_log_id="relay-summary",
            captured_at=relay_timestamp,
            event_kind="relay_mirror_summary",
            token_family="relay_mirror_output",
            delta_tokens=_coerce_int(relay_totals.get("outputTokens")),
            metadata_json=relay_metadata,
        )
        push_event(
            source_log_id="relay-summary",
            captured_at=relay_timestamp,
            event_kind="relay_mirror_summary",
            token_family="relay_mirror_cache_creation_input",
            delta_tokens=_coerce_int(relay_totals.get("cacheCreationInputTokens")),
            metadata_json=relay_metadata,
        )
        push_event(
            source_log_id="relay-summary",
            captured_at=relay_timestamp,
            event_kind="relay_mirror_summary",
            token_family="relay_mirror_cache_read_input",
            delta_tokens=_coerce_int(relay_totals.get("cacheReadInputTokens")),
            metadata_json=relay_metadata,
        )

    model_events = [
        event for event in events
        if event["token_family"] in {"model_input", "model_output"}
    ]
    total_model_tokens = sum(int(event["delta_tokens"]) for event in model_events)
    session_cost = _coerce_float(session_payload.get("totalCost") or session_payload.get("total_cost"))
    allocated = 0.0
    for index, event in enumerate(model_events):
        if total_model_tokens <= 0 or session_cost <= 0:
            break
        if index == len(model_events) - 1:
            cost = max(0.0, session_cost - allocated)
        else:
            cost = round(session_cost * (int(event["delta_tokens"]) / total_model_tokens), 6)
            allocated += cost
        event["cost_usd_model_io"] = round(cost, 6)

    return events


def build_session_usage_attributions(
    session_payload: dict[str, Any],
    logs: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not usage_events:
        return []

    session_id = _first_non_empty(session_payload, "id")
    started_at = _first_non_empty(session_payload, "startedAt", "started_at")
    normalized_logs = _normalize_log_rows(logs, started_at)
    log_index_by_id = {
        str(row["source_log_id"]): int(row["log_index"])
        for row in normalized_logs
    }
    log_by_id = {
        str(row["source_log_id"]): row
        for row in normalized_logs
    }
    artifacts_by_log_id: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        source_log_id = _first_non_empty(artifact, "source_log_id", "sourceLogId")
        if source_log_id:
            artifacts_by_log_id.setdefault(source_log_id, []).append(artifact)

    session_forensics = _safe_json_dict(session_payload.get("sessionForensics") or session_payload.get("session_forensics_json"))
    entry_context = _safe_json_dict(session_forensics.get("entryContext"))
    skill_loads = []
    for item in entry_context.get("skillLoads", []):
        if not isinstance(item, dict):
            continue
        skill_name = _first_non_empty(item, "skill")
        source_log_id = _first_non_empty(item, "sourceLogId")
        if not skill_name or not source_log_id:
            continue
        skill_loads.append(
            {
                "skill": skill_name,
                "source_log_id": source_log_id,
                "log_index": log_index_by_id.get(source_log_id, 0),
            }
        )
    skill_loads.sort(key=lambda item: (int(item["log_index"]), str(item["skill"])))

    direct_skills: dict[str, str] = {}
    direct_commands: dict[str, dict[str, str]] = {}
    workflow_ids: set[str] = set()
    feature_ids: set[str] = set()

    session_feature_id = _first_non_empty(session_payload, "featureId", "feature_id")
    if session_feature_id:
        feature_ids.add(session_feature_id.lower())

    for row in normalized_logs:
        metadata = row["metadata"]
        source_log_id = str(row["source_log_id"])
        if str(row["tool_name"]).lower() == "skill":
            skill_label = _first_non_empty(metadata, "toolLabel")
            if skill_label:
                direct_skills[source_log_id] = skill_label

        if str(row["type"]).lower() == "command":
            command_name = _first_non_empty(row, "content")
            args_text = str(metadata.get("args") or "")
            command_id = _normalize_command_id(f"{command_name} {args_text}".strip() or command_name)
            if command_id:
                direct_commands[source_log_id] = {
                    "entity_id": command_id,
                    "label": (f"{command_name} {args_text}".strip() or command_name)[:500],
                }
            workflow_id = _normalize_workflow_id(command_name.lstrip("/"))
            if workflow_id:
                workflow_ids.add(workflow_id)
            parsed_command = metadata.get("parsedCommand")
            if isinstance(parsed_command, dict):
                for key in ("featureSlugCanonical", "featureSlug"):
                    feature_value = str(parsed_command.get(key) or "").strip().lower()
                    if feature_value:
                        feature_ids.add(feature_value)

        bash_command = str(metadata.get("bashCommand") or "").strip()
        if bash_command:
            direct_commands[source_log_id] = {
                "entity_id": _normalize_command_id(bash_command),
                "label": bash_command[:500],
            }

    session_thread_kind = _first_non_empty(session_payload, "threadKind", "thread_kind").lower()
    session_agent_id = _first_non_empty(session_payload, "agentId", "agent_id")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def emit(
        *,
        event_id: str,
        entity_type: str,
        entity_id: str,
        attribution_role: str,
        method: str,
        confidence: float,
        weight: float,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        normalized_entity_id = str(entity_id or "").strip()
        if not normalized_entity_id:
            return
        key = (event_id, entity_type, normalized_entity_id, attribution_role, method)
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "event_id": event_id,
                "entity_type": entity_type,
                "entity_id": normalized_entity_id,
                "attribution_role": attribution_role,
                "weight": round(max(0.0, weight), 4),
                "method": method,
                "confidence": round(max(0.0, min(1.0, confidence)), 4),
                "metadata_json": metadata_json or {},
            }
        )

    for event in usage_events:
        event_id = str(event["id"])
        source_log_id = str(event.get("source_log_id") or "")
        event_index = log_index_by_id.get(source_log_id, 0)
        event_metadata = _safe_json_dict(event.get("metadata_json"))

        primary_candidates: list[dict[str, Any]] = []

        if source_log_id in direct_skills:
            primary_candidates.append(
                {
                    "entity_type": "skill",
                    "entity_id": direct_skills[source_log_id],
                    "method": "explicit_skill_invocation",
                    "confidence": 1.0,
                    "weight": 1.0,
                    "metadata_json": {"sourceLogId": source_log_id},
                }
            )

        linked_session_id = str(event.get("linked_session_id") or "")
        if linked_session_id:
            primary_candidates.append(
                {
                    "entity_type": "subthread",
                    "entity_id": linked_session_id,
                    "method": "explicit_subthread_ownership",
                    "confidence": 0.99,
                    "weight": 1.0,
                    "metadata_json": {"sourceLogId": source_log_id},
                }
            )
        elif session_thread_kind == "subagent" and session_id:
            primary_candidates.append(
                {
                    "entity_type": "subthread",
                    "entity_id": session_id,
                    "method": "explicit_subthread_ownership",
                    "confidence": 0.97,
                    "weight": 1.0,
                    "metadata_json": {"scope": "session"},
                }
            )

        agent_name = str(event.get("agent_name") or "")
        if agent_name:
            primary_candidates.append(
                {
                    "entity_type": "agent",
                    "entity_id": agent_name,
                    "method": "explicit_agent_ownership",
                    "confidence": 0.95,
                    "weight": 1.0,
                    "metadata_json": {"sourceLogId": source_log_id},
                }
            )
        elif session_agent_id and session_thread_kind == "subagent":
            primary_candidates.append(
                {
                    "entity_type": "agent",
                    "entity_id": session_agent_id,
                    "method": "explicit_agent_ownership",
                    "confidence": 0.9,
                    "weight": 1.0,
                    "metadata_json": {"scope": "session"},
                }
            )

        if source_log_id in direct_commands and direct_commands[source_log_id]["entity_id"]:
            primary_candidates.append(
                {
                    "entity_type": "command",
                    "entity_id": direct_commands[source_log_id]["entity_id"],
                    "method": "explicit_command_context",
                    "confidence": 0.93,
                    "weight": 1.0,
                    "metadata_json": {
                        "label": direct_commands[source_log_id]["label"],
                        "sourceLogId": source_log_id,
                    },
                }
            )

        for artifact in artifacts_by_log_id.get(source_log_id, []):
            primary_candidates.append(
                {
                    "entity_type": "artifact",
                    "entity_id": _first_non_empty(artifact, "id"),
                    "method": "explicit_artifact_link",
                    "confidence": 0.9,
                    "weight": 1.0,
                    "metadata_json": {
                        "title": _first_non_empty(artifact, "title"),
                        "artifactType": _first_non_empty(artifact, "type"),
                    },
                }
            )

        chosen_primary: dict[str, Any] | None = None
        if primary_candidates:
            chosen_primary = max(
                primary_candidates,
                key=lambda candidate: (
                    _PRIMARY_PRIORITY.get(str(candidate["method"]), 0),
                    float(candidate["confidence"]),
                    str(candidate["entity_type"]),
                    str(candidate["entity_id"]),
                ),
            )
            emit(event_id=event_id, attribution_role="primary", **chosen_primary)
            for candidate in primary_candidates:
                if candidate is chosen_primary:
                    continue
                emit(
                    event_id=event_id,
                    entity_type=str(candidate["entity_type"]),
                    entity_id=str(candidate["entity_id"]),
                    attribution_role="supporting",
                    method=str(candidate["method"]),
                    confidence=max(0.0, float(candidate["confidence"]) - 0.05),
                    weight=min(1.0, float(candidate["weight"])),
                    metadata_json=dict(candidate.get("metadata_json") or {}),
                )

        nearest_skill: dict[str, Any] | None = None
        for skill_load in skill_loads:
            if int(skill_load["log_index"]) > event_index:
                break
            nearest_skill = skill_load
        if nearest_skill and nearest_skill.get("skill"):
            distance = max(0, event_index - int(nearest_skill["log_index"]))
            if distance <= 12:
                emit(
                    event_id=event_id,
                    entity_type="skill",
                    entity_id=str(nearest_skill["skill"]),
                    attribution_role="supporting",
                    method="skill_window",
                    confidence=max(0.55, 0.82 - (0.03 * distance)),
                    weight=max(0.25, 0.7 - (0.03 * distance)),
                    metadata_json={
                        "sourceLogId": str(nearest_skill["source_log_id"]),
                        "distance": distance,
                    },
                )

        if source_log_id:
            for artifact_source_log_id, artifact_rows in artifacts_by_log_id.items():
                distance = abs(event_index - log_index_by_id.get(artifact_source_log_id, event_index))
                if artifact_source_log_id == source_log_id or distance > 4:
                    continue
                for artifact in artifact_rows:
                    emit(
                        event_id=event_id,
                        entity_type="artifact",
                        entity_id=_first_non_empty(artifact, "id"),
                        attribution_role="supporting",
                        method="artifact_window",
                        confidence=max(0.5, 0.76 - (0.06 * distance)),
                        weight=max(0.2, 0.55 - (0.08 * distance)),
                        metadata_json={
                            "sourceLogId": artifact_source_log_id,
                            "distance": distance,
                            "title": _first_non_empty(artifact, "title"),
                        },
                    )

        for workflow_id in sorted(workflow_ids):
            emit(
                event_id=event_id,
                entity_type="workflow",
                entity_id=workflow_id,
                attribution_role="supporting",
                method="workflow_membership",
                confidence=0.65,
                weight=0.4,
                metadata_json={"source": "session_command_context"},
            )

        for feature_id in sorted(feature_ids):
            emit(
                event_id=event_id,
                entity_type="feature",
                entity_id=feature_id,
                attribution_role="supporting",
                method="feature_inheritance",
                confidence=0.6,
                weight=0.35,
                metadata_json={"source": "session_context"},
            )

        if chosen_primary and str(chosen_primary["entity_type"]) == "subthread":
            supporting_agent = agent_name or session_agent_id
            if supporting_agent:
                emit(
                    event_id=event_id,
                    entity_type="agent",
                    entity_id=supporting_agent,
                    attribution_role="supporting",
                    method="explicit_agent_ownership",
                    confidence=0.9 if agent_name else 0.82,
                    weight=0.75,
                    metadata_json={"source": "subthread_owner"},
                )

        if event_metadata.get("parsedCommand"):
            parsed_command = event_metadata["parsedCommand"]
            if isinstance(parsed_command, dict):
                feature_value = str(parsed_command.get("featureSlugCanonical") or parsed_command.get("featureSlug") or "").strip().lower()
                if feature_value:
                    emit(
                        event_id=event_id,
                        entity_type="feature",
                        entity_id=feature_value,
                        attribution_role="supporting",
                        method="feature_inheritance",
                        confidence=0.7,
                        weight=0.45,
                        metadata_json={"source": "event_parsed_command"},
                    )

    return rows
