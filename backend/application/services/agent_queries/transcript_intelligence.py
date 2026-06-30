"""Derived transcript orchestration intelligence helpers.

This module is intentionally pure: callers provide the session row, transcript
log payloads, and optional usage events that they already fetched. The helpers
do not read transcripts, issue SQL, or persist derived state.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from backend.models import (
    SessionEffortTransition,
    SessionInferredTitle,
    TranscriptIntelligenceIndex,
    TranscriptMarker,
    TranscriptPlanLink,
    TranscriptTaskRegisterItem,
    TranscriptTokenCoverage,
    TranscriptWorkflowRegisterItem,
)

__all__ = ["build_transcript_intelligence_index"]


_DOC_PATH_RE = re.compile(r"(docs/[^\s\"'`)>]+?\.md)", re.IGNORECASE)
_EFFORT_COMMAND_RE = re.compile(
    r"(?:^|\s)/(?:[A-Za-z0-9_-]+:)?effort\s+([A-Za-z0-9_-]+)\b",
    re.IGNORECASE,
)
_EFFORT_OUTPUT_RE = re.compile(
    r"\beffort(?:\s+tier)?(?:\s+(?:set|updated|changed)\s+to|:|=)\s*([A-Za-z0-9_-]+)\b",
    re.IGNORECASE,
)
_WORKFLOW_TERMS = (
    "workflow",
    "plan-feature",
    "execute-phase",
    "implement-story",
    "complete-user-story",
    "quick-feature",
    "create-feature",
    "new-feature",
    "plan-story",
)
_TASK_TOOL_NAMES = {"taskcreate", "taskupdate"}
_SUBAGENT_TOOL_NAMES = {"task", "agent"}
_TOKEN_KEYS = (
    "inputTokens",
    "outputTokens",
    "cacheReadInputTokens",
    "cacheCreationInputTokens",
)
_EFFORT_ALIASES = {
    "ultracode": "high",
    "ultra-code": "high",
    "ultra": "high",
    "max": "high",
    "maximum": "high",
    "high": "high",
    "medium": "medium",
    "standard": "medium",
    "normal": "medium",
    "low": "low",
    "minimal": "low",
}
_MARKER_ACCENTS = {
    "command": "blue",
    "workflow": "green",
    "task": "amber",
    "subagent": "purple",
    "unclassified_orchestration": "gray",
}


def build_transcript_intelligence_index(
    session_row: dict[str, Any],
    transcript_logs: list[dict[str, Any]] | None,
    *,
    existing_title: str | None = None,
    latest_summary: str | None = None,
    usage_events: list[dict[str, Any]] | None = None,
) -> TranscriptIntelligenceIndex:
    """Build a non-persisted transcript intelligence index from fetched data."""

    logs = list(transcript_logs or [])
    session_id = _first_text(session_row, "id", "sessionId") or ""
    plan_links = _derive_plan_links(logs)
    markers, tasks, workflows = _derive_markers_and_registers(logs, plan_links)
    return TranscriptIntelligenceIndex(
        sessionId=session_id,
        title=_derive_title(
            session_row,
            logs,
            session_id=session_id,
            existing_title=existing_title,
            latest_summary=latest_summary,
        ),
        effortTimeline=_derive_effort_timeline(session_row, logs),
        markers=markers,
        taskRegister=list(tasks.values()),
        workflowRegister=list(workflows.values()),
        planLinks=plan_links,
        tokenCoverage=_derive_token_coverage(session_row, logs, usage_events or []),
    )


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _log_id(log: dict[str, Any], index: int) -> str:
    return _first_text(log, "id", "sourceLogId", "source_log_id") or f"log-{index}"


def _metadata(log: dict[str, Any]) -> dict[str, Any]:
    return _safe_json_dict(log.get("metadata") or log.get("metadata_json"))


def _tool_call(log: dict[str, Any]) -> dict[str, Any]:
    return _safe_json_dict(log.get("toolCall") or log.get("tool_call"))


def _tool_payload(log: dict[str, Any]) -> dict[str, Any]:
    tool_call = _tool_call(log)
    metadata = _metadata(log)
    for value in (
        tool_call.get("args"),
        metadata.get("toolArgs"),
        metadata.get("tool_args"),
        metadata.get("args"),
    ):
        parsed = _safe_json_dict(value)
        if parsed:
            return parsed
    return {}


def _tool_output_text(log: dict[str, Any]) -> str:
    tool_call = _tool_call(log)
    metadata = _metadata(log)
    return " ".join(
        text
        for text in (
            str(tool_call.get("output") or "").strip(),
            str(metadata.get("toolOutput") or metadata.get("tool_output") or "").strip(),
        )
        if text
    )


def _command_text(log: dict[str, Any]) -> str:
    metadata = _metadata(log)
    log_type = str(log.get("type") or log.get("message_type") or "").strip().lower()
    content = str(log.get("content") or "").strip()
    if log_type == "command" and content:
        args = str(metadata.get("args") or "").strip()
        return f"{content} {args}".strip()
    if content.startswith("/"):
        return content
    parsed = metadata.get("parsedCommand")
    if isinstance(parsed, dict):
        name = str(parsed.get("name") or parsed.get("command") or "").strip()
        args = str(parsed.get("args") or "").strip()
        if name:
            return f"{name} {args}".strip()
    return ""


def _command_name(command_text: str) -> str:
    if not command_text:
        return ""
    return command_text.split()[0].strip()


def _is_clear_command(command_text: str) -> bool:
    name = _command_name(command_text).lower()
    return name in {"/clear", "clear"}


def _is_plan_feature_command(command_text: str) -> bool:
    name = _command_name(command_text).lower()
    return name == "/plan:plan-feature"


def _is_workflow_text(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _WORKFLOW_TERMS)


def _feature_slug_from_text(text: str) -> str | None:
    match = _DOC_PATH_RE.search(text)
    if not match:
        return None
    return PurePosixPath(match.group(1)).name.removesuffix(".md") or None


def _humanize_slug(slug: str) -> str:
    return " ".join(part for part in slug.replace("_", "-").split("-") if part).title()


def _derive_title(
    session_row: dict[str, Any],
    logs: list[dict[str, Any]],
    *,
    session_id: str,
    existing_title: str | None,
    latest_summary: str | None,
) -> SessionInferredTitle:
    plan_candidates: list[tuple[str, str | None]] = []
    workflow_candidates: list[tuple[str, str | None]] = []

    for log in logs:
        command = _command_text(log)
        if not command or _is_clear_command(command):
            continue
        slug = _feature_slug_from_text(command)
        if _is_plan_feature_command(command):
            plan_candidates.append((command, slug))
        elif _is_workflow_text(command):
            workflow_candidates.append((command, slug))

    if plan_candidates:
        command, slug = plan_candidates[0]
        display = _humanize_slug(slug) if slug else "Plan Feature"
        return SessionInferredTitle(
            displayTitle=display,
            rawSessionId=session_id,
            source="command",
            confidence=0.95,
            commandName=_command_name(command),
            featureSlug=slug,
            reason="/plan:plan-feature command selected; /clear commands ignored",
        )

    if workflow_candidates:
        command, slug = workflow_candidates[0]
        display = _humanize_slug(slug) if slug else _command_name(command).lstrip("/") or session_id
        return SessionInferredTitle(
            displayTitle=display,
            rawSessionId=session_id,
            source="workflow",
            confidence=0.8,
            commandName=_command_name(command),
            featureSlug=slug,
            reason="workflow-looking command selected",
        )

    fallback = (
        str(existing_title or "").strip()
        or str(latest_summary or "").strip()
        or _first_text(session_row, "title", "latest_summary", "summary", "badgeLatestSummary")
    )
    if fallback and fallback != session_id and not fallback.startswith("/clear"):
        return SessionInferredTitle(
            displayTitle=fallback,
            rawSessionId=session_id,
            source="existing_title",
            confidence=0.65,
            reason="existing title or summary fallback",
        )

    return SessionInferredTitle(
        displayTitle=session_id,
        rawSessionId=session_id,
        source="session_id",
        confidence=0.2,
        reason="no stronger title signal found",
    )


def _normalize_effort(value: str) -> tuple[str, str] | None:
    raw = value.strip().lower()
    if not raw:
        return None
    normalized = _EFFORT_ALIASES.get(raw)
    if not normalized:
        return None
    return raw, normalized


def _extract_effort_from_command(command: str) -> tuple[str, str] | None:
    match = _EFFORT_COMMAND_RE.search(command)
    if not match:
        return None
    return _normalize_effort(match.group(1)) or None


def _extract_effort_from_output(text: str) -> tuple[str, str] | None:
    match = _EFFORT_OUTPUT_RE.search(text)
    if not match:
        return None
    return _normalize_effort(match.group(1)) or None


def _derive_effort_timeline(
    session_row: dict[str, Any],
    logs: list[dict[str, Any]],
) -> list[SessionEffortTransition]:
    timeline: list[SessionEffortTransition] = []
    current: str | None = None

    raw_row_effort = _first_text(session_row, "effortTier", "effort_tier")
    normalized_row = _normalize_effort(raw_row_effort) if raw_row_effort else None
    if normalized_row:
        raw, normalized = normalized_row
        timeline.append(
            SessionEffortTransition(
                id="effort-session-metadata",
                timestamp=_first_text(session_row, "startedAt", "started_at") or None,
                fromEffort=None,
                toEffort=normalized,
                providerEffort=raw,
                source="session_metadata",
                confidence=0.9,
            )
        )
        current = normalized

    for index, log in enumerate(logs):
        command = _command_text(log)
        source = "command"
        extracted = _extract_effort_from_command(command) if command else None
        if extracted is None:
            output_text = " ".join(
                part
                for part in (str(log.get("content") or "").strip(), _tool_output_text(log))
                if part
            )
            extracted = _extract_effort_from_output(output_text)
            source = "stdout"
        if extracted is None:
            continue

        raw, normalized = extracted
        timeline.append(
            SessionEffortTransition(
                id=f"effort-{len(timeline)}-{_log_id(log, index)}",
                logId=_log_id(log, index),
                timestamp=str(log.get("timestamp") or log.get("event_timestamp") or "") or None,
                fromEffort=current,
                toEffort=normalized,
                providerEffort=raw,
                source=source,  # type: ignore[arg-type]
                confidence=0.9,
            )
        )
        current = normalized

    return timeline


def _derive_plan_links(logs: list[dict[str, Any]]) -> list[TranscriptPlanLink]:
    seen: set[tuple[str, str]] = set()
    links: list[TranscriptPlanLink] = []
    for index, log in enumerate(logs):
        source_log_id = _log_id(log, index)
        haystack = " ".join(
            value
            for value in (
                _command_text(log),
                str(log.get("content") or ""),
                json.dumps(_metadata(log), sort_keys=True),
                json.dumps(_tool_payload(log), sort_keys=True),
            )
            if value
        )
        for match in _DOC_PATH_RE.finditer(haystack):
            path = match.group(1)
            link_type = _plan_link_type(path)
            key = (path, source_log_id)
            if key in seen:
                continue
            seen.add(key)
            slug = PurePosixPath(path).name.removesuffix(".md")
            links.append(
                TranscriptPlanLink(
                    id=f"plan-link-{len(links)}-{source_log_id}",
                    path=path,
                    label=PurePosixPath(path).name,
                    linkType=link_type,
                    featureSlug=slug or None,
                    sourceLogId=source_log_id,
                    confidence=0.9,
                )
            )
    return links


def _plan_link_type(path: str) -> str:
    lowered = path.lower()
    if "/prds/" in lowered:
        return "prd"
    if "/implementation_plans/" in lowered:
        return "implementation_plan"
    if "/design-specs/" in lowered:
        return "design_spec"
    if "/human-briefs/" in lowered:
        return "human_brief"
    return "document"


def _token_delta(log: dict[str, Any]) -> int | None:
    usage = log.get("tokenUsage") or log.get("token_usage")
    if not isinstance(usage, dict):
        return None
    total = 0
    seen = False
    for key in _TOKEN_KEYS:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            total += int(value)
            seen = True
    return total if seen else None


def _derive_markers_and_registers(
    logs: list[dict[str, Any]],
    plan_links: list[TranscriptPlanLink],
) -> tuple[
    list[TranscriptMarker],
    dict[str, TranscriptTaskRegisterItem],
    dict[str, TranscriptWorkflowRegisterItem],
]:
    markers: list[TranscriptMarker] = []
    tasks: dict[str, TranscriptTaskRegisterItem] = {}
    workflows: dict[str, TranscriptWorkflowRegisterItem] = {}
    plan_links_by_log: dict[str, list[TranscriptPlanLink]] = {}
    for link in plan_links:
        if link.sourceLogId:
            plan_links_by_log.setdefault(link.sourceLogId, []).append(link)

    cumulative_known_tokens = 0
    for index, log in enumerate(logs):
        log_id = _log_id(log, index)
        token_delta = _token_delta(log)
        if token_delta is not None:
            cumulative_known_tokens += token_delta
        command = _command_text(log)
        tool_call = _tool_call(log)
        tool_name = str(tool_call.get("name") or log.get("tool_name") or "").strip()
        tool_name_lower = tool_name.lower()
        log_links = [
            link.model_dump(mode="json", exclude_none=True)
            for link in plan_links_by_log.get(log_id, [])
        ]
        emitted_known_marker = False

        if command:
            marker = _append_marker(
                markers,
                log,
                index,
                kind="command",
                label=_command_name(command) or "Command",
                detail=command,
                source_method="command",
                links=log_links,
                token_delta=token_delta,
                cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
            )
            emitted_known_marker = True
            if _is_workflow_text(command):
                workflow_marker = _append_marker(
                    markers,
                    log,
                    index,
                    kind="workflow",
                    label=_command_name(command) or "Workflow command",
                    detail=command,
                    source_method="workflow_command",
                    links=log_links,
                    token_delta=token_delta,
                    cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
                )
                _upsert_workflow(
                    workflows,
                    log,
                    index,
                    workflow_marker.id,
                    label=_workflow_label_from_command(command),
                    workflow_id=_feature_slug_from_text(command) or _command_name(command),
                    command_name=_command_name(command),
                    links=log_links,
                )
            elif marker.kind == "command":
                emitted_known_marker = True

        if tool_name_lower in _SUBAGENT_TOOL_NAMES:
            marker = _append_marker(
                markers,
                log,
                index,
                kind="subagent",
                label=f"{tool_name} subagent start",
                detail=_subagent_detail(log),
                source_method="subagent_tool",
                links=log_links,
                token_delta=token_delta,
                cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
            )
            _upsert_subagent_task(tasks, log, index, marker.id, tool_name)
            emitted_known_marker = True

        if tool_name_lower in _TASK_TOOL_NAMES:
            marker = _append_marker(
                markers,
                log,
                index,
                kind="task",
                label=tool_name,
                detail=_task_detail(log),
                source_method="task_tool",
                links=log_links,
                token_delta=token_delta,
                cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
            )
            _upsert_task_tool_items(tasks, log, index, marker.id, tool_name)
            emitted_known_marker = True

        workflow_text = " ".join(
            part
            for part in (
                tool_name,
                str(log.get("content") or ""),
                json.dumps(_metadata(log), sort_keys=True),
                json.dumps(_tool_payload(log), sort_keys=True),
            )
            if part
        )
        if tool_name and _is_workflow_text(workflow_text):
            marker = _append_marker(
                markers,
                log,
                index,
                kind="workflow",
                label=tool_name,
                detail=str(log.get("content") or "") or tool_name,
                source_method="workflow_tool",
                links=log_links,
                token_delta=token_delta,
                cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
            )
            _upsert_workflow(
                workflows,
                log,
                index,
                marker.id,
                label=tool_name,
                workflow_id=_workflow_id_from_log(log) or tool_name,
                tool_name=tool_name,
                links=log_links,
            )
            emitted_known_marker = True

        if not emitted_known_marker and _is_unknown_orchestration_event(log):
            _append_marker(
                markers,
                log,
                index,
                kind="unclassified_orchestration",
                label="Unclassified orchestration event",
                detail=str(log.get("content") or "")[:240],
                source_method="unknown_team_or_sidecar_event",
                links=log_links,
                token_delta=token_delta,
                cumulative_known_tokens=cumulative_known_tokens if token_delta is not None else None,
                confidence=0.4,
            )

    return markers, tasks, workflows


def _append_marker(
    markers: list[TranscriptMarker],
    log: dict[str, Any],
    index: int,
    *,
    kind: str,
    label: str,
    detail: str,
    source_method: str,
    links: list[dict[str, Any]],
    token_delta: int | None,
    cumulative_known_tokens: int | None,
    confidence: float = 0.85,
) -> TranscriptMarker:
    log_id = _log_id(log, index)
    marker = TranscriptMarker(
        id=f"{kind}-{len(markers)}-{log_id}",
        logId=log_id,
        sequence=index,
        timestamp=str(log.get("timestamp") or log.get("event_timestamp") or ""),
        kind=kind,
        label=label,
        detail=detail,
        actor=str(log.get("agentName") or log.get("agent_name") or log.get("speaker") or ""),
        accent=_MARKER_ACCENTS.get(kind, "gray"),
        confidence=confidence,
        sourceMethod=source_method,
        links=links,
        tokenDelta=token_delta,
        cumulativeKnownTokens=cumulative_known_tokens,
    )
    markers.append(marker)
    return marker


def _subagent_detail(log: dict[str, Any]) -> str:
    payload = _tool_payload(log)
    return (
        _first_text(payload, "subagent_type", "agentType", "agent")
        or _first_text(payload, "description", "task", "prompt")
        or _first_text(log, "linkedSessionId", "linked_session_id")
        or "Subagent started"
    )


def _task_detail(log: dict[str, Any]) -> str:
    payload = _tool_payload(log)
    first_task = _task_payloads(payload)[0] if _task_payloads(payload) else payload
    return _task_title(first_task) or _first_text(log, "content") or "Task update"


def _task_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("tasks", "todos", "items"):
        items = _safe_json_list(payload.get(key))
        if items:
            return [item for item in items if isinstance(item, dict)]
    return [payload] if payload else []


def _task_title(payload: dict[str, Any]) -> str:
    return _first_text(payload, "title", "content", "description", "task", "prompt")


def _task_status(payload: dict[str, Any], fallback: str = "observed") -> str:
    return _first_text(payload, "status", "state") or fallback


def _task_key(payload: dict[str, Any], fallback: str) -> str:
    return _first_text(payload, "id", "taskId", "task_id") or fallback


def _upsert_subagent_task(
    tasks: dict[str, TranscriptTaskRegisterItem],
    log: dict[str, Any],
    index: int,
    marker_id: str,
    tool_name: str,
) -> None:
    payload = _tool_payload(log)
    log_id = _log_id(log, index)
    key = (
        _first_text(log, "linkedSessionId", "linked_session_id")
        or _first_text(payload, "id", "taskId", "subagent_type", "agentType")
        or f"subagent-{log_id}"
    )
    title = (
        _first_text(payload, "subagent_type", "agentType", "description", "task")
        or _first_text(log, "linkedSessionId", "linked_session_id")
        or f"{tool_name} subagent"
    )
    item = tasks.get(key)
    if item is None:
        tasks[key] = TranscriptTaskRegisterItem(
            id=key,
            title=title,
            status=str(_tool_call(log).get("status") or "started"),
            kind="subagent",
            sourceLogIds=[log_id],
            markerIds=[marker_id],
            linkedSessionId=_first_text(log, "linkedSessionId", "linked_session_id") or None,
            agentName=_first_text(log, "agentName", "agent_name") or None,
            toolName=tool_name,
            startedAt=str(log.get("timestamp") or log.get("event_timestamp") or "") or None,
            updatedAt=str(log.get("timestamp") or log.get("event_timestamp") or "") or None,
            confidence=0.85,
        )
        return
    _append_unique(item.sourceLogIds, log_id)
    _append_unique(item.markerIds, marker_id)
    item.updatedAt = str(log.get("timestamp") or log.get("event_timestamp") or "") or item.updatedAt


def _upsert_task_tool_items(
    tasks: dict[str, TranscriptTaskRegisterItem],
    log: dict[str, Any],
    index: int,
    marker_id: str,
    tool_name: str,
) -> None:
    payload = _tool_payload(log)
    log_id = _log_id(log, index)
    timestamp = str(log.get("timestamp") or log.get("event_timestamp") or "") or None
    for task_payload in _task_payloads(payload):
        title = _task_title(task_payload) or tool_name
        key = _task_key(task_payload, f"{tool_name.lower()}-{title.lower().replace(' ', '-')}")
        item = tasks.get(key)
        if item is None:
            tasks[key] = TranscriptTaskRegisterItem(
                id=key,
                title=title,
                status=_task_status(task_payload),
                kind="task",
                sourceLogIds=[log_id],
                markerIds=[marker_id],
                linkedSessionId=_first_text(task_payload, "linkedSessionId", "linked_session_id") or None,
                agentName=_first_text(log, "agentName", "agent_name") or None,
                toolName=tool_name,
                startedAt=timestamp,
                updatedAt=timestamp,
                confidence=0.9,
            )
            continue
        item.status = _task_status(task_payload, item.status)
        item.updatedAt = timestamp or item.updatedAt
        _append_unique(item.sourceLogIds, log_id)
        _append_unique(item.markerIds, marker_id)


def _workflow_label_from_command(command: str) -> str:
    slug = _feature_slug_from_text(command)
    if slug:
        return _humanize_slug(slug)
    return _command_name(command).lstrip("/") or "Workflow"


def _workflow_id_from_log(log: dict[str, Any]) -> str:
    metadata = _metadata(log)
    payload = _tool_payload(log)
    return (
        _first_text(metadata, "workflowId", "workflow_id", "workflowRef", "workflow_ref")
        or _first_text(payload, "workflowId", "workflow_id", "workflowRef", "workflow_ref")
    )


def _upsert_workflow(
    workflows: dict[str, TranscriptWorkflowRegisterItem],
    log: dict[str, Any],
    index: int,
    marker_id: str,
    *,
    label: str,
    workflow_id: str,
    command_name: str | None = None,
    tool_name: str | None = None,
    links: list[dict[str, Any]],
) -> None:
    log_id = _log_id(log, index)
    timestamp = str(log.get("timestamp") or log.get("event_timestamp") or "") or None
    key = workflow_id or label
    status = "completed" if _looks_completed(log) else "started"
    item = workflows.get(key)
    if item is None:
        workflows[key] = TranscriptWorkflowRegisterItem(
            id=key,
            workflowId=workflow_id,
            label=label,
            status=status,
            kind="workflow",
            commandName=command_name,
            toolName=tool_name,
            sourceLogIds=[log_id],
            markerIds=[marker_id],
            startedAt=timestamp,
            completedAt=timestamp if status == "completed" else None,
            links=links,
            confidence=0.85,
        )
        return
    item.status = "completed" if status == "completed" else item.status
    item.completedAt = timestamp if status == "completed" else item.completedAt
    item.commandName = item.commandName or command_name
    item.toolName = item.toolName or tool_name
    _append_unique(item.sourceLogIds, log_id)
    _append_unique(item.markerIds, marker_id)
    for link in links:
        if link not in item.links:
            item.links.append(link)


def _looks_completed(log: dict[str, Any]) -> bool:
    text = " ".join(
        part
        for part in (
            str(log.get("content") or ""),
            _tool_output_text(log),
            str(_tool_call(log).get("status") or ""),
        )
        if part
    ).lower()
    return any(term in text for term in ("completed", "complete", "succeeded", "success", "done"))


def _is_unknown_orchestration_event(log: dict[str, Any]) -> bool:
    metadata = _metadata(log)
    text = " ".join(
        part
        for part in (
            str(log.get("type") or ""),
            str(log.get("content") or ""),
            json.dumps(metadata, sort_keys=True),
        )
        if part
    ).lower()
    if "sidecar" in text and any(term in text for term in ("team", "agent", "workflow", "task")):
        return True
    if "team" in text and any(term in text for term in ("inbox", "assigned", "member", "message")):
        return True
    return False


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _aggregate_observed_tokens(session_row: dict[str, Any]) -> int:
    observed = _safe_int(session_row.get("observedTokens") or session_row.get("observed_tokens"))
    if observed > 0:
        return observed
    model_io = _safe_int(session_row.get("modelIOTokens") or session_row.get("model_io_tokens"))
    cache = _safe_int(session_row.get("cacheInputTokens") or session_row.get("cache_input_tokens"))
    if model_io + cache > 0:
        return model_io + cache
    return _safe_int(session_row.get("tokensIn") or session_row.get("tokens_in")) + _safe_int(
        session_row.get("tokensOut") or session_row.get("tokens_out")
    )


def _usage_event_tokens(usage_events: list[dict[str, Any]]) -> int:
    total = 0
    for event in usage_events:
        total += _safe_int(event.get("deltaTokens") or event.get("delta_tokens"))
    return total


def _derive_token_coverage(
    session_row: dict[str, Any],
    logs: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
) -> TranscriptTokenCoverage:
    row_level = sum(delta for log in logs if (delta := _token_delta(log)) is not None)
    aggregate = _aggregate_observed_tokens(session_row)
    usage_event_total = _usage_event_tokens(usage_events)
    caveats: list[str] = []

    if row_level > 0:
        denominator = aggregate if aggregate > 0 else row_level
        coverage = min(1.0, row_level / denominator) if denominator > 0 else 1.0
        if aggregate > 0 and row_level < aggregate:
            caveats.append(
                "Some aggregate session tokens are not attributable to row-level transcript entries."
            )
        return TranscriptTokenCoverage(
            rowLevelKnownTokens=row_level,
            aggregateObservedTokens=aggregate or row_level,
            coveragePct=coverage,
            sourceGranularity="message",
            caveats=caveats,
        )

    if usage_event_total > 0:
        denominator = aggregate if aggregate > 0 else usage_event_total
        return TranscriptTokenCoverage(
            rowLevelKnownTokens=0,
            aggregateObservedTokens=aggregate or usage_event_total,
            coveragePct=min(1.0, usage_event_total / denominator) if denominator > 0 else 0.0,
            sourceGranularity="usage_event",
            caveats=[
                "Usage events are available, but row-level message token usage is absent."
            ],
        )

    if aggregate > 0:
        return TranscriptTokenCoverage(
            rowLevelKnownTokens=0,
            aggregateObservedTokens=aggregate,
            coveragePct=0.0,
            sourceGranularity="aggregate",
            caveats=[
                "Aggregate session token totals are available, but row-level token usage is absent; do not render per-row token totals."
            ],
        )

    return TranscriptTokenCoverage(
        rowLevelKnownTokens=0,
        aggregateObservedTokens=0,
        coveragePct=0.0,
        sourceGranularity="none",
        caveats=["No token usage data is available for this transcript."],
    )
