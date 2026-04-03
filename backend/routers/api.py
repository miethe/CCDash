"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.common import resolve_project
from backend.application.services.documents import DocumentQueryService
from backend.application.services.session_intelligence import SessionIntelligenceReadService
from backend.application.services.sessions import SessionFacetService, SessionTranscriptService
from backend import config
from backend.models import (
    AgentSession, PlanDocument, ProjectTask, Project, ProjectPathReference,
    PaginatedResponse,
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
from backend.services.agentic_intelligence_flags import usage_attribution_enabled
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.repo_workspaces.cache import RepoWorkspaceCache
from backend.services.repo_workspaces.manager import RepoWorkspaceError, RepoWorkspaceManager
from backend.services.session_usage_analytics import get_session_usage_attribution_details
from backend.request_scope import get_core_ports, get_request_context

_SHELL_TOOL_NAMES = {"bash", "exec_command", "shell_command", "shell"}
_SUBAGENT_TOOL_NAMES = {"task", "agent"}
logger = logging.getLogger("ccdash.api")
session_facet_service = SessionFacetService()
session_transcript_service = SessionTranscriptService()
document_query_service = DocumentQueryService()
session_intelligence_read_service = SessionIntelligenceReadService()


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
):
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
    )


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


def _extract_frontmatter_block(text: str) -> tuple[str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def _preserve_document_frontmatter(
    source_file: Path,
    content: str,
    *,
    has_frontmatter: bool,
) -> str:
    if not has_frontmatter or not content or _extract_frontmatter_block(content)[0]:
        return content

    try:
        existing_content = source_file.read_text(encoding="utf-8")
    except OSError:
        return content

    frontmatter_block, _ = _extract_frontmatter_block(existing_content)
    if not frontmatter_block:
        return content

    return f"{frontmatter_block}{content}"


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
        "currentContextTokens": int(row.get("current_context_tokens") or 0),
        "contextWindowSize": int(row.get("context_window_size") or 0),
        "contextUtilizationPct": round(float(row.get("context_utilization_pct") or 0.0), 2),
        "contextMeasurementSource": str(row.get("context_measurement_source") or ""),
        "contextMeasuredAt": str(row.get("context_measured_at") or ""),
        "toolReportedTokens": tool_reported_tokens,
        "toolResultInputTokens": tool_result_input_tokens,
        "toolResultOutputTokens": tool_result_output_tokens,
        "toolResultCacheCreationInputTokens": tool_result_cache_creation_input_tokens,
        "toolResultCacheReadInputTokens": tool_result_cache_read_input_tokens,
        "cacheShare": _usage_ratio(cache_input_tokens, observed_tokens),
        "outputShare": _usage_ratio(row.get("tokens_out") or 0, model_io_tokens),
        "reportedCostUsd": row.get("reported_cost_usd"),
        "recalculatedCostUsd": row.get("recalculated_cost_usd"),
        "displayCostUsd": row.get("display_cost_usd"),
        "costProvenance": str(row.get("cost_provenance") or "unknown"),
        "costConfidence": round(float(row.get("cost_confidence") or 0.0), 4),
        "costMismatchPct": row.get("cost_mismatch_pct"),
        "pricingModelSource": str(row.get("pricing_model_source") or ""),
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
    tool_args = tool_args or str(metadata.get("toolArgs") or "").strip() or None
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
        linked_session_id = str(row.get("linked_session_id") or row.get("linkedSessionId") or "").strip()
        if row_type == "subagent_start":
            if linked_target and linked_session_id != linked_target:
                continue
            for key in ("subagentType", "subagentName", "taskSubagentType"):
                candidate = _normalize_subagent_type(metadata.get(key))
                if candidate:
                    return candidate
        if row_type != "tool":
            continue
        if linked_target and linked_session_id != linked_target:
            continue
        tool_name = row.get("tool_name")
        if not tool_name:
            tool_call = row.get("toolCall")
            if isinstance(tool_call, dict):
                tool_name = tool_call.get("name")
        if not _is_subagent_tool_name(tool_name):
            continue
        for key in ("taskSubagentType", "subagentType", "subagentName"):
            candidate = _normalize_subagent_type(metadata.get(key))
            if candidate:
                return candidate
        tool_args = row.get("tool_args")
        if tool_args in (None, ""):
            tool_args = metadata.get("toolArgs")
        if tool_args in (None, ""):
            tool_call = row.get("toolCall")
            if isinstance(tool_call, dict):
                tool_args = tool_call.get("args")
        args = _parse_tool_args(tool_args)
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return paginated sessions from DB."""
    project = resolve_project(request_context, core_ports)
    if not project:
        return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

    repo = core_ports.storage.sessions()
    mappings = await load_session_mappings(core_ports.storage.db, project.id)
    
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
        session_logs = await session_transcript_service.list_session_logs(s, core_ports)
        badge_data = derive_session_badges(
            session_logs,
            primary_model=str(s.get("model") or ""),
            session_agent_id=s.get("agent_id"),
        )
        command_events: list[dict] = []
        latest_summary = ""
        for log in session_logs:
            metadata = _safe_json(log.get("metadata_json") or log.get("metadata"))
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
        subagent_type = _subagent_type_from_logs(session_logs)
        if not subagent_type and session_type_value == "subagent":
            parent_session_id = str(s.get("parent_session_id") or "").strip()
            if parent_session_id:
                parent_logs = parent_logs_cache.get(parent_session_id)
                if parent_logs is None:
                    parent_logs = await session_transcript_service.list_session_logs(
                        {"id": parent_session_id},
                        core_ports,
                    )
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return normalized model facets for Session Forensics filters."""
    app_request = await _resolve_app_request(request_context, core_ports)
    rows = await session_facet_service.get_model_facets(
        app_request.context,
        app_request.ports,
        include_subagents=include_subagents,
    )
    return [SessionModelFacet(**row) for row in rows]


@sessions_router.get("/facets/platforms", response_model=list[SessionPlatformFacet])
async def get_session_platform_facets(
    include_subagents: bool = Query(True, description="Include subagent sessions in facet calculations"),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return platform facets for Session Forensics platform filters."""
    app_request = await _resolve_app_request(request_context, core_ports)
    rows = await session_facet_service.get_platform_facets(
        app_request.context,
        app_request.ports,
        include_subagents=include_subagents,
    )
    return [SessionPlatformFacet(**row) for row in rows]


@sessions_router.get("/{session_id}", response_model=AgentSession)
async def get_session(
    session_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return a single session by ID with full details."""
    repo = core_ports.storage.sessions()
    project = resolve_project(request_context, core_ports)
    mappings = await load_session_mappings(core_ports.storage.db, project.id) if project else []
    
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
    # Fetch details
    session_logs = await session_transcript_service.list_session_logs(s, core_ports)
    badge_data = derive_session_badges(
        session_logs,
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
    normalized_session_logs = []
    command_events: list[dict] = []
    latest_summary = ""
    for l in session_logs:
        # Reconstruct tool call info if present
        metadata = _safe_json(l.get("metadata"))
        tc = l.get("toolCall")
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
            command_text = _extract_bash_command(
                metadata,
                l.get("tool_args") or (tc.get("args") if isinstance(tc, dict) else None),
            )
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
            
        normalized_session_logs.append({
            "id": l.get("id") or l.get("source_log_id") or f"log-{l.get('log_index', l.get('message_index', 0))}",
            "timestamp": l["timestamp"],
            "speaker": l["speaker"],
            "type": l["type"],
            "content": l["content"],
            "agentName": l.get("agentName"),
            "linkedSessionId": l.get("linkedSessionId"),
            "relatedToolCallId": l.get("relatedToolCallId"),
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
    subagent_type = _subagent_type_from_logs(session_logs)
    if not subagent_type and session_type_value == "subagent":
        parent_session_id = str(s.get("parent_session_id") or "").strip()
        if parent_session_id:
            parent_logs = await session_transcript_service.list_session_logs(
                {"id": parent_session_id},
                core_ports,
            )
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
    usage_attribution_details = (
        await get_session_usage_attribution_details(
            core_ports.storage.db,
            project_id=project.id,
            session_id=session_id,
        )
        if project and usage_attribution_enabled(project)
        else {
            "usageEvents": [],
            "usageAttributions": [],
            "usageAttributionSummary": None,
            "usageAttributionCalibration": None,
        }
    )
    intelligence_detail = await session_intelligence_read_service.get_session_detail(
        request_context,
        core_ports,
        session_id=session_id,
    )
        
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
        logs=normalized_session_logs,
        sessionMetadata=session_metadata,
        thinkingLevel=str(s.get("thinking_level") or ""),
        sessionForensics=_safe_json(s.get("session_forensics_json")),
        forks=fork_summaries,
        sessionRelationships=session_relationships,
        usageEvents=usage_attribution_details["usageEvents"],
        usageAttributions=usage_attribution_details["usageAttributions"],
        usageAttributionSummary=usage_attribution_details["usageAttributionSummary"],
        usageAttributionCalibration=usage_attribution_details["usageAttributionCalibration"],
        intelligenceSummary=intelligence_detail.summary if intelligence_detail else None,
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
async def get_session_linked_features(
    session_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return linked features for a session using the same confidence logic as feature→session links."""
    project = resolve_project(request_context, core_ports)
    mappings = await load_session_mappings(core_ports.storage.db, project.id) if project else []
    workflow_markers = workflow_command_markers(mappings) if mappings else workflow_command_markers()
    session_repo = core_ports.storage.sessions()
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    link_repo = core_ports.storage.entity_links()
    feature_repo = core_ports.storage.features()
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
async def upsert_session_linked_feature(
    session_id: str,
    request: SessionFeatureLinkMutationRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Create/update a manual session↔feature link as primary or related."""
    session_repo = core_ports.storage.sessions()
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    feature_id = str(request.featureId or "").strip()
    if not feature_id:
        raise HTTPException(status_code=400, detail="featureId is required")

    feature_repo = core_ports.storage.features()
    feature_row = await feature_repo.get_by_id(feature_id)
    if not feature_row:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    link_repo = core_ports.storage.entity_links()
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
    return await get_session_linked_features(
        session_id,
        request_context=request_context,
        core_ports=core_ports,
    )


@sessions_router.delete("/{session_id}/linked-features/{feature_id}", response_model=list[SessionFeatureLink])
async def delete_session_linked_feature(
    session_id: str,
    feature_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Remove a session↔feature link."""
    session_repo = core_ports.storage.sessions()
    session_row = await session_repo.get_by_id(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    normalized_feature_id = str(feature_id or "").strip()
    if not normalized_feature_id:
        raise HTTPException(status_code=400, detail="feature_id is required")

    link_repo = core_ports.storage.entity_links()
    await link_repo.delete_link(
        "feature",
        normalized_feature_id,
        "session",
        session_id,
        "related",
    )
    return await get_session_linked_features(
        session_id,
        request_context=request_context,
        core_ports=core_ports,
    )


# ── Documents router ────────────────────────────────────────────────

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentUpdateRequest(BaseModel):
    content: str
    commitMessage: str = ""


class DocumentUpdateResponse(BaseModel):
    document: PlanDocument
    writeMode: Literal["local", "github_repo"] = "local"
    commitHash: str = ""
    message: str = ""


def _plan_docs_write_reference(project: Project) -> ProjectPathReference | None:
    plan_docs = project.pathConfig.planDocs
    root = project.pathConfig.root
    if plan_docs.sourceKind == "github_repo" and plan_docs.repoRef is not None:
        return plan_docs
    if plan_docs.sourceKind == "project_root" and root.sourceKind == "github_repo" and root.repoRef is not None:
        return root
    return None


async def _sync_changed_document_file(
    request: Request,
    project_id: str,
    file_path: Path,
    sessions_dir: Path,
    docs_dir: Path,
    progress_dir: Path,
) -> None:
    sync_engine = getattr(request.app.state, "sync_engine", None)
    if sync_engine is None:
        logger.warning("Sync engine not available in app state; relying on file watcher")
        return
    await sync_engine.sync_changed_files(
        project_id,
        [("modified", file_path)],
        sessions_dir,
        docs_dir,
        progress_dir,
    )


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
        "blockedBy": _string_list(fm.get("blockedBy") or fm.get("blocked_by")),
        "sequenceOrder": fm.get("sequenceOrder") if fm.get("sequenceOrder") is not None else fm.get("sequence_order"),
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
        blockedBy=_string_list(metadata.get("blockedBy")),
        sequenceOrder=metadata.get("sequenceOrder"),
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
            "blockedBy": _string_list(metadata.get("blockedBy")),
            "sequenceOrder": metadata.get("sequenceOrder"),
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return paginated typed documents with optional filters."""
    app_request = await _resolve_app_request(request_context, core_ports)
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
    return await document_query_service.list_documents(
        app_request.context,
        app_request.ports,
        filters=filters,
        offset=offset,
        limit=limit,
    )


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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return DB-backed document facet counts for filters."""
    app_request = await _resolve_app_request(request_context, core_ports)
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
    return await document_query_service.get_catalog(
        app_request.context,
        app_request.ports,
        filters=filters,
    )


@documents_router.get("/{doc_id}/links")
async def get_document_links(
    doc_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return linked entities for a document."""
    app_request = await _resolve_app_request(request_context, core_ports)
    return await document_query_service.get_document_links(
        app_request.context,
        app_request.ports,
        doc_id=doc_id,
    )


@documents_router.get("/{doc_id}", response_model=PlanDocument)
async def get_document(
    doc_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return a single document with full content."""
    app_request = await _resolve_app_request(request_context, core_ports)
    return await document_query_service.get_document(
        app_request.context,
        app_request.ports,
        doc_id=doc_id,
        include_content=True,
    )


@documents_router.put("/{doc_id}", response_model=DocumentUpdateResponse)
async def update_document(
    doc_id: str,
    req: DocumentUpdateRequest,
    request: Request,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Update a plan document through the local path or managed GitHub workspace."""
    active_project = resolve_project(request_context, core_ports, required=True)
    repo = core_ports.storage.documents()

    row = await repo.get_by_id(doc_id)
    if not row:
        row = await repo.get_by_path(active_project.id, doc_id)
    if not row and doc_id.startswith("DOC-"):
        legacy_hint = doc_id[4:]
        candidate_path = normalize_ref_path(legacy_hint.replace("-", "/"))
        if candidate_path:
            row = await repo.get_by_path(active_project.id, candidate_path)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    root_kind = str(row.get("root_kind") or "document")
    if root_kind != "project_plans":
        raise HTTPException(status_code=400, detail="Only plan documents can be updated in this flow.")

    source_file = Path(str(row.get("source_file") or "")).expanduser()
    if not str(source_file):
        raise HTTPException(status_code=400, detail="The document does not have a writable source file.")

    bundle = core_ports.workspace_registry.resolve_project_paths(active_project)
    source_file = source_file.resolve(strict=False)
    try:
        source_file.relative_to(bundle.plan_docs.path.resolve(strict=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="The document source file is outside the resolved plan-docs path.") from exc

    request_content = str(req.content or "").replace("\r\n", "\n")
    content = _preserve_document_frontmatter(
        source_file,
        request_content,
        has_frontmatter=bool(row.get("has_frontmatter")),
    )
    write_mode: Literal["local", "github_repo"] = "local"
    commit_hash = ""
    message = "Document saved locally."

    repo_reference = _plan_docs_write_reference(active_project)
    if repo_reference is not None:
        settings = GitHubSettingsStore().load()
        repo_ref = repo_reference.repoRef
        token_configured = bool(str(settings.token or "").strip())
        if repo_ref is None:
            raise HTTPException(status_code=400, detail="GitHub-backed plan docs require a repository reference.")
        if not settings.enabled:
            raise HTTPException(status_code=403, detail="GitHub integration is disabled.")
        if not settings.writeEnabled:
            raise HTTPException(status_code=403, detail="GitHub write support is disabled in integration settings.")
        if not repo_ref.writeEnabled:
            raise HTTPException(status_code=403, detail="GitHub writes are disabled for this project path.")
        if not token_configured:
            raise HTTPException(status_code=403, detail="A GitHub token is required for write-backed plan documents.")

        manager = RepoWorkspaceManager(RepoWorkspaceCache(Path(settings.cacheRoot or config.REPO_WORKSPACE_CACHE_DIR).expanduser()))
        try:
            workspace_root = manager.ensure_workspace(repo_ref, settings, refresh=False)
            repo_relative_path = str(source_file.relative_to(workspace_root.resolve(strict=False))).replace("\\", "/")
            commit_hash = manager.write_file_and_push(
                repo_ref,
                settings,
                workspace_relative_path=repo_relative_path,
                content=content,
                commit_message=str(req.commitMessage or "").strip() or f"ccdash: update plan document {row.get('file_path') or doc_id}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="The plan document is not inside the managed repository workspace.") from exc
        except RepoWorkspaceError as exc:
            status_code = 403 if exc.code in {"auth_failure", "write_not_allowed"} else 400
            raise HTTPException(status_code=status_code, detail=exc.detail) from exc

        write_mode = "github_repo"
        message = "Document saved and pushed via managed GitHub workspace."
    else:
        source_file.write_text(content, encoding="utf-8")

    await _sync_changed_document_file(
        request,
        active_project.id,
        source_file,
        bundle.sessions.path,
        bundle.plan_docs.path,
        bundle.progress.path,
    )

    refreshed_row = await repo.get_by_id(str(row.get("id") or doc_id))
    document = (
        _map_document_row_to_model(refreshed_row, include_content=True, link_counts=None)
        if refreshed_row
        else _map_document_row_to_model({**dict(row), "content": content}, include_content=True, link_counts=None)
    )
    if document.content != request_content:
        document = document.model_copy(update={"content": request_content})

    return DocumentUpdateResponse(
        document=document,
        writeMode=write_mode,
        commitHash=commit_hash,
        message=message,
    )


# ── Tasks router ────────────────────────────────────────────────────

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@tasks_router.get("", response_model=PaginatedResponse[ProjectTask])
async def list_tasks(
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return paginated tasks from DB."""
    project = resolve_project(request_context, core_ports)
    if not project:
        return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

    repo = core_ports.storage.tasks()
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
