"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.models import (
    AgentSession, PlanDocument, ProjectTask,
    PaginatedResponse,
)
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.factory import (
    get_session_repository,
    get_document_repository,
    get_task_repository,
    get_entity_link_repository,
    get_feature_repository,
)
from backend.session_mappings import (
    classify_bash_command,
    classify_session_key_metadata,
    load_session_mappings,
    workflow_command_exemptions,
    workflow_command_markers,
)
from backend.model_identity import derive_model_identity
from backend.session_badges import derive_session_badges
from backend.document_linking import (
    make_document_id,
    normalize_doc_status,
    normalize_doc_subtype,
    normalize_doc_type,
    normalize_ref_path,
)
from backend.date_utils import make_date_value

_SHELL_TOOL_NAMES = {"bash", "exec_command", "shell_command", "shell"}
_SUBAGENT_TOOL_NAMES = {"task", "agent"}


def _safe_json(raw: str | dict | None) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _safe_json_list(raw: str | list | None) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _usage_ratio(numerator: Any, denominator: Any) -> float:
    try:
        num = max(0.0, float(numerator or 0))
    except (TypeError, ValueError):
        num = 0.0
    try:
        den = max(0.0, float(denominator or 0))
    except (TypeError, ValueError):
        den = 0.0
    if den <= 0:
        return 0.0
    return round(num / den, 4)


def _session_usage_fields(row: dict[str, Any]) -> dict[str, Any]:
    model_io_tokens = int(row.get("model_io_tokens") or 0)
    cache_creation_input_tokens = int(row.get("cache_creation_input_tokens") or 0)
    cache_read_input_tokens = int(row.get("cache_read_input_tokens") or 0)
    cache_input_tokens = int(row.get("cache_input_tokens") or 0)
    observed_tokens = int(row.get("observed_tokens") or 0)
    tool_reported_tokens = int(row.get("tool_reported_tokens") or 0)
    tool_result_input_tokens = int(row.get("tool_result_input_tokens") or 0)
    tool_result_output_tokens = int(row.get("tool_result_output_tokens") or 0)
    tool_result_cache_creation_input_tokens = int(row.get("tool_result_cache_creation_input_tokens") or 0)
    tool_result_cache_read_input_tokens = int(row.get("tool_result_cache_read_input_tokens") or 0)
    return {
        "modelIOTokens": model_io_tokens,
        "cacheCreationInputTokens": cache_creation_input_tokens,
        "cacheReadInputTokens": cache_read_input_tokens,
        "cacheInputTokens": cache_input_tokens,
        "observedTokens": observed_tokens,
        "toolReportedTokens": tool_reported_tokens,
        "toolResultInputTokens": tool_result_input_tokens,
        "toolResultOutputTokens": tool_result_output_tokens,
        "toolResultCacheCreationInputTokens": tool_result_cache_creation_input_tokens,
        "toolResultCacheReadInputTokens": tool_result_cache_read_input_tokens,
        "cacheShare": _usage_ratio(cache_input_tokens, observed_tokens),
        "outputShare": _usage_ratio(row.get("tokens_out") or 0, model_io_tokens),
    }


def _string_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(v) for v in raw if isinstance(v, str) and str(v).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _linked_feature_ref_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature") or "").strip().lower()
        if not feature:
            continue
        confidence: float | None = None
        confidence_raw = item.get("confidence")
        if confidence_raw is not None:
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except Exception:
                confidence = None
        refs.append(
            {
                "feature": feature,
                "type": str(item.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_"),
                "source": str(item.get("source") or "").strip().lower().replace("-", "_").replace(" ", "_"),
                "confidence": confidence,
                "notes": str(item.get("notes") or ""),
                "evidence": _string_list(item.get("evidence")),
            }
        )
    return refs


def _extract_bash_command(metadata: dict, tool_args: str | None) -> str:
    raw = metadata.get("bashCommand")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if not tool_args:
        return ""
    try:
        parsed = json.loads(tool_args)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    for key in ("command", "cmd", "script"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_subagent_tool_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _SUBAGENT_TOOL_NAMES


def _parse_tool_args(raw_tool_args: Any) -> dict[str, Any]:
    if isinstance(raw_tool_args, dict):
        return raw_tool_args
    if not isinstance(raw_tool_args, str) or not raw_tool_args.strip():
        return {}
    try:
        parsed = json.loads(raw_tool_args)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_subagent_type(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    lowered = candidate.lower()
    if lowered in {"subagent", "agent"}:
        return ""
    if re.fullmatch(r"agent[-_][a-z0-9._:-]+", lowered):
        return ""
    return candidate


def _subagent_type_from_logs(
    logs: list[dict[str, Any]],
    target_linked_session_id: str = "",
) -> str:
    linked_target = str(target_linked_session_id or "").strip()
    for row in logs:
        row_type = str(row.get("type") or "").strip().lower()
        metadata = _safe_json(row.get("metadata_json") or row.get("metadata"))
        if row_type == "subagent_start":
            if linked_target and str(row.get("linked_session_id") or "").strip() != linked_target:
                continue
            for key in ("subagentType", "subagentName", "taskSubagentType"):
                candidate = _normalize_subagent_type(metadata.get(key))
                if candidate:
                    return candidate
        if row_type != "tool":
            continue
        if linked_target and str(row.get("linked_session_id") or "").strip() != linked_target:
            continue
        tool_name = row.get("tool_name")
        if not _is_subagent_tool_name(tool_name):
            continue
        for key in ("taskSubagentType", "subagentType", "subagentName"):
            candidate = _normalize_subagent_type(metadata.get(key))
            if candidate:
                return candidate
        args = _parse_tool_args(row.get("tool_args"))
        for key in ("subagent_type", "subagentType", "agent_name", "agentName"):
            candidate = _normalize_subagent_type(args.get(key))
            if candidate:
                return candidate
    return ""


def _is_primary_session_link(
    strategy: str,
    confidence: float,
    signal_types: set[str],
    commands: list[str],
    link_role: str = "",
) -> bool:
    normalized_link_role = str(link_role or "").strip().lower()
    if normalized_link_role == "primary":
        return True
    if normalized_link_role == "related":
        return False
    if strategy == "task_frontmatter":
        return True
    if confidence >= 0.9:
        return True
    if confidence >= 0.75 and ("file_write" in signal_types or "command_args_path" in signal_types):
        return True
    return False


def _command_token(command_name: str) -> str:
    normalized = " ".join((command_name or "").strip().split()).lower()
    if not normalized:
        return ""
    return normalized.split()[0]


def _normalize_link_commands(
    commands: list[str],
    workflow_markers: tuple[str, ...] | None = None,
) -> list[str]:
    markers = workflow_markers or workflow_command_markers()
    exclusions = workflow_command_exemptions()
    seen: set[str] = set()
    deduped: list[str] = []
    for raw in commands:
        command = " ".join((raw or "").strip().split())
        if not command:
            continue
        token = _command_token(command)
        if token in exclusions:
            continue
        lowered = command.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(command)
    deduped.sort(
        key=lambda command: (
            next((idx for idx, marker in enumerate(markers) if marker in command.lower()), len(markers)),
            command.lower(),
        )
    )
    return deduped


def _phase_label(phase_token: str) -> str:
    token = (phase_token or "").strip()
    if not token:
        return ""
    if token.lower() == "all":
        return "All Phases"
    if token.replace(" ", "").replace("&", "").replace("-", "").isdigit():
        return f"Phase {token}"
    return f"Phase {token}"


def _normalize_thread_kind(row: dict[str, Any]) -> str:
    explicit = str(row.get("thread_kind") or "").strip().lower()
    if explicit:
        return explicit
    session_type = str(row.get("session_type") or "").strip().lower()
    if session_type == "subagent":
        return "subagent"
    return "root"


def _default_context_inheritance(thread_kind: str, row: dict[str, Any]) -> str:
    explicit = str(row.get("context_inheritance") or "").strip().lower()
    if explicit:
        return explicit
    return "full" if thread_kind == "fork" else "fresh"


def _relationship_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "relationshipType": str(row.get("relationship_type") or ""),
        "parentSessionId": str(row.get("parent_session_id") or ""),
        "childSessionId": str(row.get("child_session_id") or ""),
        "contextInheritance": str(row.get("context_inheritance") or ""),
        "sourcePlatform": str(row.get("source_platform") or ""),
        "parentEntryUuid": str(row.get("parent_entry_uuid") or ""),
        "childEntryUuid": str(row.get("child_entry_uuid") or ""),
        "sourceLogId": row.get("source_log_id"),
        "metadata": _safe_json(row.get("metadata_json")),
    }


def _session_dates_payload(row: dict[str, Any]) -> dict[str, Any]:
    row_dates = _safe_json(row.get("dates_json"))
    if isinstance(row_dates, dict) and row_dates:
        return row_dates

    dates: dict[str, Any] = {}
    for key, candidate in (
        ("createdAt", make_date_value(row.get("created_at"), "medium", "repository", "session_record_created")),
        ("updatedAt", make_date_value(row.get("updated_at"), "medium", "repository", "session_record_updated")),
        ("startedAt", make_date_value(row.get("started_at"), "high", "session", "session_started")),
        ("completedAt", make_date_value(row.get("ended_at"), "high", "session", "session_completed")),
        ("endedAt", make_date_value(row.get("ended_at"), "high", "session", "session_completed")),
        ("lastActivityAt", make_date_value(row.get("ended_at") or row.get("updated_at"), "medium", "session", "last_activity")),
    ):
        if candidate:
            dates[key] = candidate
    return dates


def _derive_session_title(
    session_metadata: dict | None,
    summary: str,
    session_id: str,
    session_type: str = "",
    subagent_type: str = "",
) -> str:
    normalized_session_type = str(session_type or "").strip().lower()
    normalized_subagent_type = _normalize_subagent_type(subagent_type)
    if normalized_session_type == "subagent" and normalized_subagent_type:
        return normalized_subagent_type

    summary_text = (summary or "").strip()
    if summary_text:
        return summary_text

    metadata = session_metadata if isinstance(session_metadata, dict) else {}
    session_type = str(metadata.get("sessionTypeLabel") or "").strip()
    phases = metadata.get("relatedPhases")
    if not isinstance(phases, list):
        phases = []
    phase_values = [str(v).strip() for v in phases if str(v).strip()]
    if session_type and phase_values:
        phase_text = ", ".join(_phase_label(value) for value in phase_values)
        return f"{session_type} - {phase_text}"
    if session_type:
        return session_type
    return session_id


class SessionFeatureLink(BaseModel):
    featureId: str
    featureName: str = ""
    featureStatus: str = "backlog"
    featureCategory: str = ""
    featureUpdatedAt: str = ""
    totalTasks: int = 0
    completedTasks: int = 0
    confidence: float = 0.0
    isPrimaryLink: bool = False
    linkStrategy: str = ""
    reasons: list[str] = Field(default_factory=list)
    signals: list[dict] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    commitHashes: list[str] = Field(default_factory=list)
    ambiguityShare: float = 0.0


class SessionFeatureLinkMutationRequest(BaseModel):
    featureId: str
    linkRole: Literal["primary", "related"] = "related"


class SessionModelFacet(BaseModel):
    raw: str = ""
    modelDisplayName: str = ""
    modelProvider: str = ""
    modelFamily: str = ""
    modelVersion: str = ""
    count: int = 0


class SessionPlatformFacet(BaseModel):
    platformType: str = "Claude Code"
    platformVersion: str = ""
    count: int = 0


# ── Sessions router ─────────────────────────────────────────────────

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@sessions_router.get("", response_model=PaginatedResponse[AgentSession])
async def list_sessions(
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "started_at",
    sort_order: str = "desc",
    status: str | None = Query(None, description="Filter by session status"),
    model: str | None = Query(None, description="Filter by model name (partial match)"),
    model_provider: str | None = Query(None, description="Filter by model provider"),
    model_family: str | None = Query(None, description="Filter by model family"),
    model_version: str | None = Query(None, description="Filter by model version"),
    platform_type: str | None = Query(None, description="Filter by agent platform type"),
    platform_version: str | None = Query(None, description="Filter by agent platform version"),
    thread_kind: str | None = Query(None, description="Filter by normalized thread kind (root|fork|subagent)"),
    conversation_family_id: str | None = Query(None, description="Filter by conversation family id"),
    include_subagents: bool = Query(False, description="Include subagent sessions in list results"),
    root_session_id: str | None = Query(None, description="Filter to a specific root thread family"),
    start_date: str | None = Query(None, description="ISO timestamp for start range"),
    end_date: str | None = Query(None, description="ISO timestamp for end range"),
    created_start: str | None = Query(None, description="ISO timestamp for created-at range start"),
    created_end: str | None = Query(None, description="ISO timestamp for created-at range end"),
    completed_start: str | None = Query(None, description="ISO timestamp for completed-at range start"),
    completed_end: str | None = Query(None, description="ISO timestamp for completed-at range end"),
    updated_start: str | None = Query(None, description="ISO timestamp for updated-at range start"),
    updated_end: str | None = Query(None, description="ISO timestamp for updated-at range end"),
    min_duration: int | None = Query(None, description="Minimum duration in seconds"),
    max_duration: int | None = Query(None, description="Maximum duration in seconds"),
):
    """Return paginated sessions from DB."""
    project = project_manager.get_active_project()
    if not project:
        return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

    db = await connection.get_connection()
    repo = get_session_repository(db)
    mappings = await load_session_mappings(db, project.id)
    
    # Construct filter dict
    filters = {}
    if status: filters["status"] = status
    if model: filters["model"] = model
    if model_provider: filters["model_provider"] = model_provider
    if model_family: filters["model_family"] = model_family
    if model_version: filters["model_version"] = model_version
    if platform_type: filters["platform_type"] = platform_type
    if platform_version: filters["platform_version"] = platform_version
    if thread_kind: filters["thread_kind"] = thread_kind
    if conversation_family_id: filters["conversation_family_id"] = conversation_family_id
    filters["include_subagents"] = include_subagents
    if root_session_id: filters["root_session_id"] = root_session_id
    if start_date: filters["start_date"] = start_date
    if end_date: filters["end_date"] = end_date
    if created_start: filters["created_start"] = created_start
    if created_end: filters["created_end"] = created_end
    if completed_start: filters["completed_start"] = completed_start
    if completed_end: filters["completed_end"] = completed_end
    if updated_start: filters["updated_start"] = updated_start
    if updated_end: filters["updated_end"] = updated_end
    if min_duration is not None: filters["min_duration"] = min_duration
    if max_duration is not None: filters["max_duration"] = max_duration

    # DB returns dicts, Pydantic will validate them
    sessions_data = await repo.list_paginated(
        offset, limit, project.id, sort_by, sort_order, filters
    )
    total_count = await repo.count(project.id, filters)
    
    parent_logs_cache: dict[str, list[dict[str, Any]]] = {}
    # Hydrate items (minimal for list view)
    results = []
    for s in sessions_data:
        platform_type_value = str(s.get("platform_type") or "").strip() or "Claude Code"
        session_type_value = str(s.get("session_type") or "").strip().lower()
        session_id = str(s.get("id") or "").strip()
        logs = await repo.get_logs(s["id"])
        badge_data = derive_session_badges(
            logs,
            primary_model=str(s.get("model") or ""),
            session_agent_id=s.get("agent_id"),
        )
        command_events: list[dict] = []
        latest_summary = ""
        for log in logs:
            metadata = _safe_json(log.get("metadata_json"))
            if log.get("type") == "command":
                command_events.append({
                    "name": str(log.get("content") or "").strip(),
                    "args": str(metadata.get("args") or ""),
                    "parsedCommand": metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {},
                })
            if log.get("type") == "system" and str(metadata.get("eventType") or "").strip().lower() == "summary":
                text = str(log.get("content") or "").strip()
                if text:
                    latest_summary = text
        session_metadata = classify_session_key_metadata(
            command_events,
            mappings,
            platform_type=platform_type_value,
        )
        model_identity = derive_model_identity(s.get("model"))
        subagent_type = _subagent_type_from_logs(logs)
        if not subagent_type and session_type_value == "subagent":
            parent_session_id = str(s.get("parent_session_id") or "").strip()
            if parent_session_id:
                parent_logs = parent_logs_cache.get(parent_session_id)
                if parent_logs is None:
                    parent_logs = await repo.get_logs(parent_session_id)
                    parent_logs_cache[parent_session_id] = parent_logs
                subagent_type = _subagent_type_from_logs(parent_logs, target_linked_session_id=session_id)
        thread_kind_value = _normalize_thread_kind(s)
        conversation_family_id_value = (
            str(s.get("conversation_family_id") or "").strip()
            or str(s.get("root_session_id") or "").strip()
            or session_id
        )
        context_inheritance_value = _default_context_inheritance(thread_kind_value, s)
        session_title = _derive_session_title(
            session_metadata,
            latest_summary,
            s["id"],
            session_type=s.get("session_type") or "",
            subagent_type=subagent_type,
        )
        platform_version_value = str(s.get("platform_version") or "").strip()
        raw_platform_versions = _safe_json_list(s.get("platform_versions_json"))
        platform_versions: list[str] = []
        for value in raw_platform_versions:
            raw = str(value or "").strip()
            if raw and raw not in platform_versions:
                platform_versions.append(raw)
        if platform_version_value and platform_version_value not in platform_versions:
            platform_versions.insert(0, platform_version_value)
        platform_version_transitions = [
            event for event in _safe_json_list(s.get("platform_version_transitions_json"))
            if isinstance(event, dict)
        ]

        results.append(AgentSession(
            id=s["id"],
            title=session_title,
            taskId=s["task_id"] or "",
            status=s["status"] or "completed",
            model=s["model"] or "",
            modelDisplayName=model_identity["modelDisplayName"],
            modelProvider=model_identity["modelProvider"],
            modelFamily=model_identity["modelFamily"],
            modelVersion=model_identity["modelVersion"],
            modelsUsed=badge_data["modelsUsed"],
            platformType=platform_type_value,
            platformVersion=platform_version_value,
            platformVersions=platform_versions,
            platformVersionTransitions=platform_version_transitions,
            agentsUsed=badge_data["agentsUsed"],
            skillsUsed=badge_data["skillsUsed"],
            toolSummary=badge_data["toolSummary"],
            sessionType=s["session_type"] or "",
            parentSessionId=s["parent_session_id"],
            rootSessionId=s.get("root_session_id") or s["id"],
            agentId=s.get("agent_id"),
            threadKind=thread_kind_value,
            conversationFamilyId=conversation_family_id_value,
            contextInheritance=context_inheritance_value,
            forkParentSessionId=s.get("fork_parent_session_id"),
            forkPointLogId=s.get("fork_point_log_id"),
            forkPointEntryUuid=s.get("fork_point_entry_uuid"),
            forkPointParentEntryUuid=s.get("fork_point_parent_entry_uuid"),
            forkDepth=int(s.get("fork_depth") or 0),
            forkCount=int(s.get("fork_count") or 0),
            durationSeconds=s["duration_seconds"],
            tokensIn=s["tokens_in"],
            tokensOut=s["tokens_out"],
            **_session_usage_fields(s),
            totalCost=s["total_cost"],
            startedAt=s["started_at"] or "",
            endedAt=s.get("ended_at") or "",
            createdAt=s.get("created_at") or "",
            updatedAt=s.get("updated_at") or "",
            qualityRating=s["quality_rating"],
            frictionRating=s["friction_rating"],
            gitCommitHash=s["git_commit_hash"],
            gitCommitHashes=[str(v) for v in _safe_json_list(s.get("git_commit_hashes_json"))],
            gitAuthor=s["git_author"],
            gitBranch=s["git_branch"],
            updatedFiles=[],
            linkedArtifacts=[],
            toolsUsed=[],
            impactHistory=[],
            logs=[],
            sessionMetadata=session_metadata,
            thinkingLevel=str(s.get("thinking_level") or ""),
            sessionForensics=_safe_json(s.get("session_forensics_json")),
            dates=_session_dates_payload(s),
            timeline=[event for event in _safe_json_list(s.get("timeline_json")) if isinstance(event, dict)],
        ))
        
    return PaginatedResponse(
        items=results,
        total=total_count,
        offset=offset,
        limit=limit
    )


@sessions_router.get("/facets/models", response_model=list[SessionModelFacet])
async def get_session_model_facets(
    include_subagents: bool = Query(True, description="Include subagent sessions in facet calculations"),
):
    """Return normalized model facets for Session Forensics filters."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    rows = await repo.get_model_facets(project.id, include_subagents=include_subagents)

    items: list[SessionModelFacet] = []
    for row in rows:
        raw_model = str(row.get("model") or "")
        identity = derive_model_identity(raw_model)
        items.append(
            SessionModelFacet(
                raw=raw_model,
                modelDisplayName=identity["modelDisplayName"],
                modelProvider=identity["modelProvider"],
                modelFamily=identity["modelFamily"],
                modelVersion=identity["modelVersion"],
                count=int(row.get("count") or 0),
            )
        )
    return items


@sessions_router.get("/facets/platforms", response_model=list[SessionPlatformFacet])
async def get_session_platform_facets(
    include_subagents: bool = Query(True, description="Include subagent sessions in facet calculations"),
):
    """Return platform facets for Session Forensics platform filters."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    rows = await repo.get_platform_facets(project.id, include_subagents=include_subagents)

    return [
        SessionPlatformFacet(
            platformType=str(row.get("platform_type") or "Claude Code").strip() or "Claude Code",
            platformVersion=str(row.get("platform_version") or "").strip(),
            count=int(row.get("count") or 0),
        )
        for row in rows
    ]


@sessions_router.get("/{session_id}", response_model=AgentSession)
async def get_session(session_id: str):
    """Return a single session by ID with full details."""
    db = await connection.get_connection()
    repo = get_session_repository(db)
    project = project_manager.get_active_project()
    mappings = await load_session_mappings(db, project.id) if project else []
    
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
    # Fetch details
    logs = await repo.get_logs(session_id)
    badge_data = derive_session_badges(
        logs,
        primary_model=str(s.get("model") or ""),
        session_agent_id=s.get("agent_id"),
    )
    tools = await repo.get_tool_usage(session_id)
    files = await repo.get_file_updates(session_id)
    artifacts = await repo.get_artifacts(session_id)
    project_id_for_relationships = str(s.get("project_id") or (project.id if project else ""))
    relationship_rows = (
        await repo.list_relationships(project_id_for_relationships, session_id)
        if project_id_for_relationships
        else []
    )
    session_relationships = [_relationship_payload(row) for row in relationship_rows]
    fork_summaries: list[dict[str, Any]] = []
    for row in relationship_rows:
        if str(row.get("relationship_type") or "").strip().lower() != "fork":
            continue
        if str(row.get("parent_session_id") or "").strip() != session_id:
            continue
        child_id = str(row.get("child_session_id") or "").strip()
        if not child_id:
            continue
        child_row = await repo.get_by_id(child_id)
        child_forensics = _safe_json(child_row.get("session_forensics_json")) if child_row else {}
        child_summary = child_forensics.get("forkSummary", {}) if isinstance(child_forensics, dict) else {}
        metadata = _safe_json(row.get("metadata_json"))
        fork_summaries.append(
            {
                "sessionId": child_id,
                "label": str(metadata.get("label") or child_summary.get("label") or child_id),
                "forkPointTimestamp": str(metadata.get("forkPointTimestamp") or ""),
                "forkPointPreview": str(metadata.get("forkPointPreview") or ""),
                "entryCount": int(metadata.get("entryCount") or child_summary.get("entryCount") or 0),
                "contextInheritance": str(row.get("context_inheritance") or ""),
            }
        )
    
    # Transform details to model format
    
    # Logs
    platform_type_value = str(s.get("platform_type") or "").strip() or "Claude Code"
    session_logs = []
    command_events: list[dict] = []
    latest_summary = ""
    for l in logs:
        # Reconstruct tool call info if present
        tc = None
        if l["type"] == "tool":
            tc = {
                "id": l.get("tool_call_id"),
                "name": l["tool_name"],
                "args": l["tool_args"] or "",
                "output": l["tool_output"],
                "status": l["tool_status"],
                "isError": (l["tool_status"] or "") == "error",
            }
        metadata = _safe_json(l.get("metadata_json"))
        if l["type"] == "command":
            command_events.append({
                "name": str(l.get("content") or "").strip(),
                "args": str(metadata.get("args") or ""),
                "parsedCommand": metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {},
            })
        if l["type"] == "system" and str(metadata.get("eventType") or "").strip().lower() == "summary":
            summary_text = str(l.get("content") or "").strip()
            if summary_text:
                latest_summary = summary_text
        if tc and str(tc.get("name") or "").strip().lower() in _SHELL_TOOL_NAMES:
            command_text = _extract_bash_command(metadata, l.get("tool_args"))
            mapping = classify_bash_command(
                command_text,
                mappings,
                platform_type=platform_type_value,
            )
            if mapping:
                metadata["originalToolName"] = tc.get("name")
                metadata["toolCategory"] = mapping.get("category", "bash")
                metadata["toolMappingId"] = mapping.get("id", "")
                mapped_label = str(mapping.get("transcriptLabel") or mapping.get("label") or "Shell")
                metadata["toolLabel"] = mapped_label
                tc["name"] = mapped_label
            elif isinstance(metadata.get("toolLabel"), str) and metadata["toolLabel"].strip():
                tc["name"] = metadata["toolLabel"].strip()
            
        session_logs.append({
            "id": l.get("source_log_id") or f"log-{l['log_index']}",
            "timestamp": l["timestamp"],
            "speaker": l["speaker"],
            "type": l["type"],
            "content": l["content"],
            "agentName": l["agent_name"],
            "linkedSessionId": l.get("linked_session_id"),
            "relatedToolCallId": l.get("related_tool_call_id"),
            "metadata": metadata,
            "toolCall": tc,
        })

    session_metadata = classify_session_key_metadata(
        command_events,
        mappings,
        platform_type=platform_type_value,
    )
    model_identity = derive_model_identity(s.get("model"))
    session_type_value = str(s.get("session_type") or "").strip().lower()
    thread_kind_value = _normalize_thread_kind(s)
    conversation_family_id_value = (
        str(s.get("conversation_family_id") or "").strip()
        or str(s.get("root_session_id") or "").strip()
        or str(s.get("id") or "")
    )
    context_inheritance_value = _default_context_inheritance(thread_kind_value, s)
    subagent_type = _subagent_type_from_logs(logs)
    if not subagent_type and session_type_value == "subagent":
        parent_session_id = str(s.get("parent_session_id") or "").strip()
        if parent_session_id:
            parent_logs = await repo.get_logs(parent_session_id)
            subagent_type = _subagent_type_from_logs(parent_logs, target_linked_session_id=str(s.get("id") or ""))
    session_title = _derive_session_title(
        session_metadata,
        latest_summary,
        s["id"],
        session_type=s.get("session_type") or "",
        subagent_type=subagent_type,
    )
    platform_version_value = str(s.get("platform_version") or "").strip()
    raw_platform_versions = _safe_json_list(s.get("platform_versions_json"))
    platform_versions: list[str] = []
    for value in raw_platform_versions:
        raw = str(value or "").strip()
        if raw and raw not in platform_versions:
            platform_versions.append(raw)
    if platform_version_value and platform_version_value not in platform_versions:
        platform_versions.insert(0, platform_version_value)
    platform_version_transitions = [
        event for event in _safe_json_list(s.get("platform_version_transitions_json"))
        if isinstance(event, dict)
    ]
        
    # Tools
    tool_usage = []
    for t in tools:
        tool_usage.append({
            "name": t["tool_name"],
            "count": t["call_count"],
            "successRate": t["success_count"] / t["call_count"] if t["call_count"] > 0 else 0.0,
            "totalMs": int(t.get("total_ms") or 0),
        })
        
    # Files
    file_updates = []
    for f in files:
        file_updates.append({
            "filePath": f["file_path"],
            "action": f.get("action") or "update",
            "fileType": f.get("file_type") or "Other",
            "timestamp": f.get("action_timestamp") or "",
            "additions": f["additions"],
            "deletions": f["deletions"],
            "agentName": f["agent_name"],
            "sourceLogId": f.get("source_log_id"),
            "sourceToolName": f.get("source_tool_name"),
            "threadSessionId": f.get("thread_session_id"),
            "rootSessionId": f.get("root_session_id"),
        })
        
    # Artifacts
    linked_artifacts = []
    for a in artifacts:
        linked_artifacts.append({
            "id": a["id"],
            "title": a["title"],
            "type": a["type"],
            "description": a["description"],
            "source": a["source"],
            "url": a.get("url"),
            "sourceLogId": a.get("source_log_id"),
            "sourceToolName": a.get("source_tool_name"),
        })

    return AgentSession(
        id=s["id"],
        title=session_title,
        taskId=s["task_id"] or "",
        status=s["status"] or "completed",
        model=s["model"] or "",
        modelDisplayName=model_identity["modelDisplayName"],
        modelProvider=model_identity["modelProvider"],
        modelFamily=model_identity["modelFamily"],
        modelVersion=model_identity["modelVersion"],
        modelsUsed=badge_data["modelsUsed"],
        platformType=platform_type_value,
        platformVersion=platform_version_value,
        platformVersions=platform_versions,
        platformVersionTransitions=platform_version_transitions,
        agentsUsed=badge_data["agentsUsed"],
        skillsUsed=badge_data["skillsUsed"],
        toolSummary=badge_data["toolSummary"],
        sessionType=s["session_type"] or "",
        parentSessionId=s["parent_session_id"],
        rootSessionId=s.get("root_session_id") or s["id"],
        agentId=s.get("agent_id"),
        threadKind=thread_kind_value,
        conversationFamilyId=conversation_family_id_value,
        contextInheritance=context_inheritance_value,
        forkParentSessionId=s.get("fork_parent_session_id"),
        forkPointLogId=s.get("fork_point_log_id"),
        forkPointEntryUuid=s.get("fork_point_entry_uuid"),
        forkPointParentEntryUuid=s.get("fork_point_parent_entry_uuid"),
        forkDepth=int(s.get("fork_depth") or 0),
        forkCount=int(s.get("fork_count") or 0),
        durationSeconds=s["duration_seconds"],
        tokensIn=s["tokens_in"],
        tokensOut=s["tokens_out"],
        **_session_usage_fields(s),
        totalCost=s["total_cost"],
        startedAt=s["started_at"] or "",
        endedAt=s.get("ended_at") or "",
        createdAt=s.get("created_at") or "",
        updatedAt=s.get("updated_at") or "",
        qualityRating=s["quality_rating"],
        frictionRating=s["friction_rating"],
        gitCommitHash=s["git_commit_hash"],
        gitCommitHashes=[str(v) for v in _safe_json_list(s.get("git_commit_hashes_json"))],
        gitAuthor=s["git_author"],
        gitBranch=s["git_branch"],
        updatedFiles=file_updates,
        linkedArtifacts=linked_artifacts,
        toolsUsed=tool_usage,
        impactHistory=[event for event in _safe_json_list(s.get("impact_history_json")) if isinstance(event, dict)],
        logs=session_logs,
        sessionMetadata=session_metadata,
        thinkingLevel=str(s.get("thinking_level") or ""),
        sessionForensics=_safe_json(s.get("session_forensics_json")),
        forks=fork_summaries,
        sessionRelationships=session_relationships,
        dates=_session_dates_payload(s),
        timeline=[
            event for event in _safe_json_list(s.get("timeline_json"))
            if isinstance(event, dict)
        ] or [
            *(
                [{
                    "id": "session-started",
                    "timestamp": s.get("started_at") or "",
                    "label": "Session Started",
                    "kind": "started",
                    "confidence": "high",
                    "source": "session",
                    "description": "First session event timestamp",
                }]
                if s.get("started_at") else []
            ),
            *(
                [{
                    "id": "session-completed",
                    "timestamp": s.get("ended_at") or "",
                    "label": "Session Completed",
                    "kind": "completed",
                    "confidence": "high",
                    "source": "session",
                    "description": "Last session event timestamp",
                }]
                if s.get("ended_at") else []
            ),
        ],
    )


@sessions_router.get("/{session_id}/linked-features", response_model=list[SessionFeatureLink])
async def get_session_linked_features(session_id: str):
    """Return linked features for a session using the same confidence logic as feature→session links."""
    db = await connection.get_connection()
    project = project_manager.get_active_project()
    mappings = await load_session_mappings(db, project.id) if project else []
    workflow_markers = workflow_command_markers(mappings) if mappings else workflow_command_markers()
    session_repo = get_session_repository(db)
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    link_repo = get_entity_link_repository(db)
    feature_repo = get_feature_repository(db)
    links = await link_repo.get_links_for("session", session_id, "related")

    items: list[SessionFeatureLink] = []
    for link in links:
        if link.get("source_type") != "feature":
            continue
        if link.get("target_type") != "session" or link.get("target_id") != session_id:
            continue

        feature_id = str(link.get("source_id") or "").strip()
        if not feature_id:
            continue

        feature_row = await feature_repo.get_by_id(feature_id)
        if not feature_row:
            continue

        metadata = _safe_json(link.get("metadata_json"))
        link_role = str(metadata.get("linkRole") or "").strip().lower()
        strategy = str(metadata.get("linkStrategy") or "").strip()
        reasons: list[str] = []
        if strategy:
            reasons.append(strategy)

        signal_types: set[str] = set()
        trimmed_signals: list[dict] = []
        raw_signals = metadata.get("signals", [])
        if isinstance(raw_signals, list):
            for signal in raw_signals[:8]:
                if not isinstance(signal, dict):
                    continue
                trimmed_signals.append(signal)
                signal_type = str(signal.get("type") or "").strip()
                if signal_type:
                    signal_types.add(signal_type)
                    reasons.append(signal_type)

        commands = metadata.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        normalized_commands = _normalize_link_commands(
            [str(v) for v in commands if isinstance(v, str)],
            workflow_markers,
        )
        commit_hashes = metadata.get("commitHashes", [])
        if not isinstance(commit_hashes, list):
            commit_hashes = []
        confidence = float(link.get("confidence") or 0.0)
        is_primary = _is_primary_session_link(
            strategy,
            confidence,
            signal_types,
            normalized_commands,
            link_role=link_role,
        )

        ambiguity_share = metadata.get("ambiguityShare", 0.0)
        try:
            ambiguity_share = float(ambiguity_share or 0.0)
        except Exception:
            ambiguity_share = 0.0

        items.append(
            SessionFeatureLink(
                featureId=feature_id,
                featureName=str(feature_row.get("name") or ""),
                featureStatus=str(feature_row.get("status") or "backlog"),
                featureCategory=str(feature_row.get("category") or ""),
                featureUpdatedAt=str(feature_row.get("updated_at") or ""),
                totalTasks=int(feature_row.get("total_tasks") or 0),
                completedTasks=int(feature_row.get("completed_tasks") or 0),
                confidence=confidence,
                isPrimaryLink=is_primary,
                linkStrategy=strategy,
                reasons=list(dict.fromkeys(reasons)),
                signals=trimmed_signals,
                commands=normalized_commands[:12],
                commitHashes=[str(v) for v in commit_hashes if isinstance(v, str)],
                ambiguityShare=round(ambiguity_share, 3),
            )
        )

    items.sort(key=lambda item: (item.isPrimaryLink, item.confidence, item.featureUpdatedAt), reverse=True)
    return items


@sessions_router.post("/{session_id}/linked-features", response_model=list[SessionFeatureLink])
async def upsert_session_linked_feature(session_id: str, request: SessionFeatureLinkMutationRequest):
    """Create/update a manual session↔feature link as primary or related."""
    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    feature_id = str(request.featureId or "").strip()
    if not feature_id:
        raise HTTPException(status_code=400, detail="featureId is required")

    feature_repo = get_feature_repository(db)
    feature_row = await feature_repo.get_by_id(feature_id)
    if not feature_row:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    link_repo = get_entity_link_repository(db)
    existing_links = await link_repo.get_links_for("session", session_id, "related")

    existing_link_for_target: dict[str, Any] | None = None
    for link in existing_links:
        if link.get("source_type") != "feature":
            continue
        if link.get("target_type") != "session" or str(link.get("target_id") or "") != session_id:
            continue
        current_feature_id = str(link.get("source_id") or "").strip()
        if not current_feature_id:
            continue
        if current_feature_id == feature_id:
            existing_link_for_target = link

    if request.linkRole == "primary":
        for link in existing_links:
            if link.get("source_type") != "feature":
                continue
            if link.get("target_type") != "session" or str(link.get("target_id") or "") != session_id:
                continue

            current_feature_id = str(link.get("source_id") or "").strip()
            if not current_feature_id or current_feature_id == feature_id:
                continue

            metadata = _safe_json(link.get("metadata_json"))
            metadata["linkRole"] = "related"
            confidence = float(link.get("confidence") or 0.0)

            await link_repo.upsert(
                {
                    "source_type": "feature",
                    "source_id": current_feature_id,
                    "target_type": "session",
                    "target_id": session_id,
                    "link_type": "related",
                    "origin": str(link.get("origin") or "auto"),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "depth": int(link.get("depth") or 0),
                    "sort_order": int(link.get("sort_order") or 0),
                    "metadata_json": json.dumps(metadata),
                }
            )

    if request.linkRole == "related" and existing_link_for_target:
        existing_metadata = _safe_json(existing_link_for_target.get("metadata_json"))
        existing_role = str(existing_metadata.get("linkRole") or "").strip().lower()
        if existing_role == "primary":
            return await get_session_linked_features(session_id)

    next_metadata = _safe_json(existing_link_for_target.get("metadata_json") if existing_link_for_target else None)
    next_metadata["linkStrategy"] = "manual_set"
    next_metadata["linkRole"] = request.linkRole
    next_metadata["manualSet"] = True

    await link_repo.upsert(
        {
            "source_type": "feature",
            "source_id": feature_id,
            "target_type": "session",
            "target_id": session_id,
            "link_type": "related",
            "origin": "manual",
            "confidence": 1.0,
            "depth": 0,
            "sort_order": 0,
            "metadata_json": json.dumps(next_metadata),
        }
    )
    return await get_session_linked_features(session_id)


@sessions_router.delete("/{session_id}/linked-features/{feature_id}", response_model=list[SessionFeatureLink])
async def delete_session_linked_feature(session_id: str, feature_id: str):
    """Remove a session↔feature link."""
    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    normalized_feature_id = str(feature_id or "").strip()
    if not normalized_feature_id:
        raise HTTPException(status_code=400, detail="feature_id is required")

    link_repo = get_entity_link_repository(db)
    await link_repo.delete_link(
        "feature",
        normalized_feature_id,
        "session",
        session_id,
        "related",
    )
    return await get_session_linked_features(session_id)


# ── Documents router ────────────────────────────────────────────────

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])


def _map_document_row_to_model(row: dict, include_content: bool = False, link_counts: dict | None = None) -> PlanDocument:
    fm = _safe_json(row.get("frontmatter_json"))
    metadata = _safe_json(row.get("metadata_json"))
    if not isinstance(fm, dict):
        fm = {}
    if not isinstance(metadata, dict):
        metadata = {}

    file_path = str(row.get("file_path") or "")
    canonical_path = str(row.get("canonical_path") or file_path)
    normalized_canonical = normalize_ref_path(canonical_path) or canonical_path
    path_segments = [segment for segment in normalized_canonical.split("/") if segment]

    linked_features = _string_list(fm.get("linkedFeatures"))
    linked_feature_refs = _linked_feature_ref_list(fm.get("linkedFeatureRefs"))
    if not linked_feature_refs:
        linked_feature_refs = _linked_feature_ref_list(metadata.get("linkedFeatureRefs"))
    feature_candidates = sorted({
        *linked_features,
        *[str(v.get("feature") or "") for v in linked_feature_refs if isinstance(v, dict)],
        str(row.get("feature_slug_hint") or ""),
        str(row.get("feature_slug_canonical") or ""),
    })
    feature_candidates = [value for value in feature_candidates if value]

    metadata_task_counts = metadata.get("taskCounts")
    if not isinstance(metadata_task_counts, dict):
        metadata_task_counts = {}
    date_metadata = metadata.get("dates")
    if not isinstance(date_metadata, dict):
        date_metadata = {}
    if not date_metadata.get("createdAt") and row.get("created_at"):
        date_metadata["createdAt"] = make_date_value(row.get("created_at"), "medium", "repository", "document_record_created")
    if not date_metadata.get("updatedAt") and row.get("updated_at"):
        date_metadata["updatedAt"] = make_date_value(row.get("updated_at"), "medium", "repository", "document_record_updated")
    if not date_metadata.get("lastActivityAt"):
        last_activity = row.get("last_modified") or row.get("updated_at")
        if last_activity:
            date_metadata["lastActivityAt"] = make_date_value(last_activity, "medium", "repository", "document_last_activity")
    timeline = metadata.get("timeline")
    if not isinstance(timeline, list):
        timeline = []

    frontmatter_obj = {
        "tags": _string_list(fm.get("tags")),
        "linkedFeatures": linked_features,
        "linkedFeatureRefs": linked_feature_refs,
        "linkedSessions": _string_list(fm.get("linkedSessions")),
        "linkedTasks": _string_list(fm.get("linkedTasks")),
        "lineageFamily": str(fm.get("lineageFamily") or ""),
        "lineageParent": str(fm.get("lineageParent") or ""),
        "lineageChildren": _string_list(fm.get("lineageChildren")),
        "lineageType": str(fm.get("lineageType") or ""),
        "version": fm.get("version"),
        "commits": _string_list(fm.get("commits")),
        "prs": _string_list(fm.get("prs")),
        "requestLogIds": _string_list(fm.get("requestLogIds")),
        "commitRefs": _string_list(fm.get("commitRefs")),
        "prRefs": _string_list(fm.get("prRefs")),
        "relatedRefs": _string_list(fm.get("relatedRefs")),
        "pathRefs": _string_list(fm.get("pathRefs")),
        "slugRefs": _string_list(fm.get("slugRefs")),
        "prd": str(fm.get("prd") or ""),
        "prdRefs": _string_list(fm.get("prdRefs")),
        "sourceDocuments": _string_list(fm.get("sourceDocuments")),
        "filesAffected": _string_list(fm.get("filesAffected")),
        "filesModified": _string_list(fm.get("filesModified")),
        "contextFiles": _string_list(fm.get("contextFiles")),
        "integritySignalRefs": _string_list(fm.get("integritySignalRefs")),
        "fieldKeys": _string_list(fm.get("fieldKeys")),
        "raw": fm.get("raw") if isinstance(fm.get("raw"), dict) else fm,
    }

    raw_status_normalized = str(row.get("status_normalized") or row.get("status") or "")
    normalized_status = normalize_doc_status(raw_status_normalized, default="pending")
    raw_doc_type = str(row.get("doc_type") or "")
    normalized_doc_type = normalize_doc_type(raw_doc_type, default="document")
    normalized_subtype = normalize_doc_subtype(
        str(row.get("doc_subtype") or ""),
        root_kind=str(row.get("root_kind") or ""),
        doc_type=normalized_doc_type,
    )

    completed_at = ""
    raw_completed = date_metadata.get("completedAt")
    if isinstance(raw_completed, dict):
        completed_at = str(raw_completed.get("value") or "")

    return PlanDocument(
        id=str(row.get("id") or make_document_id(normalized_canonical)),
        title=str(row.get("title") or ""),
        filePath=file_path,
        status=str(row.get("status") or "active"),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
        completedAt=completed_at,
        lastModified=str(row.get("last_modified") or ""),
        author=str(row.get("author") or ""),
        docType=normalized_doc_type,
        category=str(row.get("category") or ""),
        docSubtype=normalized_subtype,
        rootKind=str(row.get("root_kind") or "project_plans"),  # type: ignore[arg-type]
        canonicalPath=normalized_canonical,
        hasFrontmatter=bool(row.get("has_frontmatter")),
        frontmatterType=str(row.get("frontmatter_type") or ""),
        statusNormalized=normalized_status,
        featureSlugHint=str(row.get("feature_slug_hint") or ""),
        featureSlugCanonical=str(row.get("feature_slug_canonical") or ""),
        prdRef=str(row.get("prd_ref") or ""),
        phaseToken=str(row.get("phase_token") or ""),
        phaseNumber=row.get("phase_number"),
        overallProgress=row.get("overall_progress"),
        completionEstimate=str(metadata.get("completionEstimate") or ""),
        description=str(metadata.get("description") or ""),
        summary=str(metadata.get("summary") or ""),
        priority=str(metadata.get("priority") or ""),
        riskLevel=str(metadata.get("riskLevel") or ""),
        complexity=str(metadata.get("complexity") or ""),
        track=str(metadata.get("track") or ""),
        timelineEstimate=str(metadata.get("timelineEstimate") or ""),
        targetRelease=str(metadata.get("targetRelease") or ""),
        milestone=str(metadata.get("milestone") or ""),
        decisionStatus=str(metadata.get("decisionStatus") or ""),
        executionReadiness=str(metadata.get("executionReadiness") or ""),
        testImpact=str(metadata.get("testImpact") or ""),
        primaryDocRole=str(metadata.get("primaryDocRole") or ""),
        featureSlug=str(metadata.get("featureSlug") or ""),
        featureFamily=str(metadata.get("featureFamily") or ""),
        featureVersion=str(metadata.get("featureVersion") or ""),
        planRef=str(metadata.get("planRef") or ""),
        implementationPlanRef=str(metadata.get("implementationPlanRef") or ""),
        totalTasks=int(row.get("total_tasks") or 0),
        completedTasks=int(row.get("completed_tasks") or 0),
        inProgressTasks=int(row.get("in_progress_tasks") or 0),
        blockedTasks=int(row.get("blocked_tasks") or 0),
        pathSegments=path_segments,
        featureCandidates=feature_candidates,
        frontmatter=frontmatter_obj,
        metadata={
            "phase": str(metadata.get("phase") or row.get("phase_token") or ""),
            "phaseNumber": metadata.get("phaseNumber", row.get("phase_number")),
            "overallProgress": metadata.get("overallProgress", row.get("overall_progress")),
            "completionEstimate": str(metadata.get("completionEstimate") or ""),
            "description": str(metadata.get("description") or ""),
            "summary": str(metadata.get("summary") or ""),
            "priority": str(metadata.get("priority") or ""),
            "riskLevel": str(metadata.get("riskLevel") or ""),
            "complexity": str(metadata.get("complexity") or ""),
            "track": str(metadata.get("track") or ""),
            "timelineEstimate": str(metadata.get("timelineEstimate") or ""),
            "targetRelease": str(metadata.get("targetRelease") or ""),
            "milestone": str(metadata.get("milestone") or ""),
            "decisionStatus": str(metadata.get("decisionStatus") or ""),
            "executionReadiness": str(metadata.get("executionReadiness") or ""),
            "testImpact": str(metadata.get("testImpact") or ""),
            "primaryDocRole": str(metadata.get("primaryDocRole") or ""),
            "featureSlug": str(metadata.get("featureSlug") or ""),
            "featureFamily": str(metadata.get("featureFamily") or ""),
            "featureVersion": str(metadata.get("featureVersion") or ""),
            "planRef": str(metadata.get("planRef") or ""),
            "implementationPlanRef": str(metadata.get("implementationPlanRef") or ""),
            "taskCounts": {
                "total": int(metadata_task_counts.get("total", row.get("total_tasks") or 0)),
                "completed": int(metadata_task_counts.get("completed", row.get("completed_tasks") or 0)),
                "inProgress": int(metadata_task_counts.get("inProgress", row.get("in_progress_tasks") or 0)),
                "blocked": int(metadata_task_counts.get("blocked", row.get("blocked_tasks") or 0)),
            },
            "owners": _string_list(metadata.get("owners")),
            "contributors": _string_list(metadata.get("contributors")),
            "reviewers": _string_list(metadata.get("reviewers")),
            "approvers": _string_list(metadata.get("approvers")),
            "audience": _string_list(metadata.get("audience")),
            "labels": _string_list(metadata.get("labels")),
            "linkedTasks": _string_list(metadata.get("linkedTasks")),
            "requestLogIds": _string_list(metadata.get("requestLogIds")),
            "commitRefs": _string_list(metadata.get("commitRefs")),
            "prRefs": _string_list(metadata.get("prRefs")),
            "sourceDocuments": _string_list(metadata.get("sourceDocuments")),
            "filesAffected": _string_list(metadata.get("filesAffected")),
            "filesModified": _string_list(metadata.get("filesModified")),
            "contextFiles": _string_list(metadata.get("contextFiles")),
            "integritySignalRefs": _string_list(metadata.get("integritySignalRefs")),
            "executionEntrypoints": [
                entry
                for entry in metadata.get("executionEntrypoints", [])
                if isinstance(entry, dict)
            ] if isinstance(metadata.get("executionEntrypoints"), list) else [],
            "linkedFeatureRefs": linked_feature_refs,
            "docTypeFields": metadata.get("docTypeFields", {}) if isinstance(metadata.get("docTypeFields"), dict) else {},
            "featureSlugHint": metadata.get("featureSlugHint", row.get("feature_slug_hint") or ""),
            "canonicalPath": metadata.get("canonicalPath", normalized_canonical),
        },
        linkCounts={
            "features": int((link_counts or {}).get("features", 0)),
            "tasks": int((link_counts or {}).get("tasks", 0)),
            "sessions": int((link_counts or {}).get("sessions", 0)),
            "documents": int((link_counts or {}).get("documents", 0)),
        },
        dates=date_metadata,
        timeline=[event for event in timeline if isinstance(event, dict)],
        content=(str(row.get("content") or "") if include_content else None),
    )


@documents_router.get("", response_model=PaginatedResponse[PlanDocument])
async def list_documents(
    q: str | None = Query(None),
    doc_subtype: str | None = Query(None),
    root_kind: str | None = Query(None),
    doc_type: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    feature: str | None = Query(None),
    prd: str | None = Query(None),
    phase: str | None = Query(None),
    include_progress: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=5000),
):
    """Return paginated typed documents with optional filters."""
    project = project_manager.get_active_project()
    if not project:
        return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

    db = await connection.get_connection()
    repo = get_document_repository(db)
    filters = {
        "q": q,
        "doc_subtype": doc_subtype,
        "root_kind": root_kind,
        "doc_type": doc_type,
        "category": category,
        "status": status,
        "feature": feature,
        "prd": prd,
        "phase": phase,
        "include_progress": include_progress,
    }
    rows = await repo.list_paginated(project.id, offset, limit, filters)
    total = await repo.count(project.id, filters)

    items: list[PlanDocument] = []
    for row in rows:
        items.append(_map_document_row_to_model(row, include_content=False, link_counts=None))

    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@documents_router.get("/catalog")
async def get_documents_catalog(
    q: str | None = Query(None),
    doc_subtype: str | None = Query(None),
    root_kind: str | None = Query(None),
    doc_type: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    feature: str | None = Query(None),
    prd: str | None = Query(None),
    phase: str | None = Query(None),
    include_progress: bool = Query(False),
):
    """Return DB-backed document facet counts for filters."""
    project = project_manager.get_active_project()
    if not project:
        return {"total": 0}

    db = await connection.get_connection()
    repo = get_document_repository(db)
    filters = {
        "q": q,
        "doc_subtype": doc_subtype,
        "root_kind": root_kind,
        "doc_type": doc_type,
        "category": category,
        "status": status,
        "feature": feature,
        "prd": prd,
        "phase": phase,
        "include_progress": include_progress,
    }
    return await repo.get_catalog_facets(project.id, filters)


@documents_router.get("/{doc_id}/links")
async def get_document_links(doc_id: str):
    """Return linked entities for a document."""
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project")

    db = await connection.get_connection()
    doc_repo = get_document_repository(db)
    link_repo = get_entity_link_repository(db)
    feature_repo = get_feature_repository(db)
    task_repo = get_task_repository(db)
    session_repo = get_session_repository(db)

    row = await doc_repo.get_by_id(doc_id)
    if not row:
        row = await doc_repo.get_by_path(project.id, doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    canonical_doc_id = str(row.get("id") or doc_id)
    links = await link_repo.get_links_for("document", canonical_doc_id)

    feature_ids: set[str] = set()
    task_ids: set[str] = set()
    session_ids: set[str] = set()
    document_ids: set[str] = set()

    for link in links:
        source_type = str(link.get("source_type") or "")
        source_id = str(link.get("source_id") or "")
        target_type = str(link.get("target_type") or "")
        target_id = str(link.get("target_id") or "")

        if source_type == "document" and source_id == canonical_doc_id:
            counterpart_type = target_type
            counterpart_id = target_id
        elif target_type == "document" and target_id == canonical_doc_id:
            counterpart_type = source_type
            counterpart_id = source_id
        else:
            continue

        if counterpart_type == "feature":
            feature_ids.add(counterpart_id)
        elif counterpart_type == "task":
            task_ids.add(counterpart_id)
        elif counterpart_type == "session":
            session_ids.add(counterpart_id)
        elif counterpart_type == "document" and counterpart_id != canonical_doc_id:
            document_ids.add(counterpart_id)

    features = []
    for feature_id in sorted(feature_ids):
        feature_row = await feature_repo.get_by_id(feature_id)
        if not feature_row:
            continue
        features.append({
            "id": feature_id,
            "name": feature_row.get("name", ""),
            "status": feature_row.get("status", ""),
            "category": feature_row.get("category", ""),
        })

    tasks = []
    for task_row in await task_repo.list_all(project.id):
        task_id = str(task_row.get("id") or "")
        if task_id not in task_ids:
            continue
        tasks.append({
            "id": task_id,
            "title": task_row.get("title", ""),
            "status": task_row.get("status", ""),
            "sourceFile": task_row.get("source_file", ""),
            "sessionId": task_row.get("session_id", ""),
            "featureId": task_row.get("feature_id"),
            "phaseId": task_row.get("phase_id"),
        })

    sessions = []
    for session_id in sorted(session_ids):
        session_row = await session_repo.get_by_id(session_id)
        if not session_row:
            continue
        sessions.append({
            "id": session_id,
            "status": session_row.get("status", ""),
            "model": session_row.get("model", ""),
            "startedAt": session_row.get("started_at", ""),
            "totalCost": session_row.get("total_cost", 0.0),
        })

    documents = []
    for linked_doc_id in sorted(document_ids):
        linked_row = await doc_repo.get_by_id(linked_doc_id)
        if not linked_row:
            continue
        documents.append({
            "id": linked_doc_id,
            "title": linked_row.get("title", ""),
            "filePath": linked_row.get("file_path", ""),
            "canonicalPath": linked_row.get("canonical_path", ""),
            "docType": linked_row.get("doc_type", ""),
            "docSubtype": linked_row.get("doc_subtype", ""),
        })

    return {
        "documentId": canonical_doc_id,
        "features": features,
        "tasks": tasks,
        "sessions": sessions,
        "documents": documents,
    }


@documents_router.get("/{doc_id}", response_model=PlanDocument)
async def get_document(doc_id: str):
    """Return a single document with full content."""
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project")

    db = await connection.get_connection()
    repo = get_document_repository(db)

    row = await repo.get_by_id(doc_id)
    if not row:
        row = await repo.get_by_path(project.id, doc_id)
    if not row and doc_id.startswith("DOC-"):
        legacy_hint = doc_id[4:]
        # Legacy IDs used hyphenated paths; keep a best-effort fallback.
        candidate_path = normalize_ref_path(legacy_hint.replace("-", "/"))
        if candidate_path:
            row = await repo.get_by_path(project.id, candidate_path)

    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    return _map_document_row_to_model(row, include_content=True, link_counts=None)


# ── Tasks router ────────────────────────────────────────────────────

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@tasks_router.get("", response_model=PaginatedResponse[ProjectTask])
async def list_tasks(
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
):
    """Return paginated tasks from DB."""
    project = project_manager.get_active_project()
    if not project:
        return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

    db = await connection.get_connection()
    repo = get_task_repository(db)
    tasks = await repo.list_paginated(project.id, offset, limit)
    total = await repo.count(project.id)

    results: list[ProjectTask] = []
    for t in tasks:
        data = _safe_json(t.get("data_json"))
        raw_task_id = data.get("rawTaskId") or t["id"]

        results.append(ProjectTask(
            id=str(raw_task_id),
            title=t["title"],
            description=t["description"],
            status=t["status"],
            owner=t["owner"],
            lastAgent=t["last_agent"],
            cost=t["cost"],
            priority=t["priority"],
            projectType=t["project_type"],
            projectLevel=t["project_level"],
            tags=data.get("tags", []),
            updatedAt=t["updated_at"] or "",
            relatedFiles=data.get("relatedFiles", []),
            sourceFile=t["source_file"],
            sessionId=t["session_id"],
            commitHash=t["commit_hash"],
        ))
    return PaginatedResponse(items=results, total=total, offset=offset, limit=limit)
