"""Session mapping configuration API."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project, require_project
from backend.db import connection
from backend.db.factory import get_session_repository
from backend.request_scope import get_core_ports, get_request_context, require_http_authorization
from backend.session_mappings import (
    classify_bash_command,
    classify_key_command,
    classify_transcript_message,
    load_session_mappings,
    save_session_mappings,
    workflow_command_exemptions,
    workflow_command_markers,
)

session_mappings_router = APIRouter(prefix="/api/session-mappings", tags=["session-mappings"])

_SHELL_TOOL_NAMES = {"bash", "exec_command", "shell_command", "shell"}


class SessionMappingRule(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    mappingType: str = "bash"
    label: str
    category: str = "bash"
    pattern: str
    transcriptLabel: str
    sessionTypeLabel: str = ""
    matchScope: str = "command"
    transcriptKind: str = "command"
    icon: str = ""
    color: str = ""
    summaryTemplate: str = "{label}: {match}"
    extractPattern: str = ""
    fieldMappings: list[dict[str, Any]] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["all"])
    commandMarker: str = ""
    enabled: bool = True
    priority: int = 10


class SessionMappingsPayload(BaseModel):
    mappings: list[SessionMappingRule]


class SessionMappingDiagnosticsRow(BaseModel):
    id: str
    label: str
    mappingType: str
    enabled: bool
    priority: int
    platforms: list[str] = Field(default_factory=list)
    matchCount: int = 0


class SessionMappingsDiagnostics(BaseModel):
    workflowCommands: list[str] = Field(default_factory=list)
    nonConsequentialCommands: list[str] = Field(default_factory=list)
    uncoveredWorkflowCommands: list[str] = Field(default_factory=list)
    neverMatchedMappings: list[str] = Field(default_factory=list)
    mappingMatches: list[SessionMappingDiagnosticsRow] = Field(default_factory=list)
    evaluatedSessions: int = 0


def _safe_json(raw: str | dict | None) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _extract_shell_command(log_row: dict[str, Any], metadata: dict[str, Any]) -> str:
    tool_name = str(log_row.get("tool_name") or "").strip().lower()
    if tool_name not in _SHELL_TOOL_NAMES:
        return ""

    command = str(metadata.get("bashCommand") or "").strip()
    if command:
        return command

    tool_args = str(log_row.get("tool_args") or "")
    parsed = _safe_json(tool_args)
    for key in ("command", "cmd", "script"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


@session_mappings_router.get("", response_model=list[SessionMappingRule])
async def list_session_mappings(
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    project = resolve_project(request_context, core_ports)
    await require_http_authorization(
        request_context,
        core_ports,
        action="session_mapping:read",
        resource=f"project:{project.id}" if project else None,
    )
    if not project:
        return []
    db = await connection.get_connection()
    mappings = await load_session_mappings(db, project.id)
    return [SessionMappingRule(**m) for m in mappings]


@session_mappings_router.get("/diagnostics", response_model=SessionMappingsDiagnostics)
async def get_session_mappings_diagnostics(
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    project = resolve_project(request_context, core_ports)
    await require_http_authorization(
        request_context,
        core_ports,
        action="session_mapping:diagnose",
        resource=f"project:{project.id}" if project else None,
    )
    if not project:
        return SessionMappingsDiagnostics()

    db = await connection.get_connection()
    mappings = await load_session_mappings(db, project.id)
    repo = get_session_repository(db)

    workflow_markers = list(workflow_command_markers(mappings))
    default_workflow_markers = set(workflow_command_markers())
    configured_markers = set(workflow_command_markers(mappings, include_disabled=True))
    uncovered = sorted(default_workflow_markers - configured_markers)

    rows_by_id: dict[str, SessionMappingDiagnosticsRow] = {}
    for mapping in mappings:
        mapping_id = str(mapping.get("id") or "").strip()
        if not mapping_id:
            continue
        rows_by_id[mapping_id] = SessionMappingDiagnosticsRow(
            id=mapping_id,
            label=str(mapping.get("label") or mapping_id),
            mappingType=str(mapping.get("mappingType") or ""),
            enabled=bool(mapping.get("enabled", True)),
            priority=int(mapping.get("priority", 0) or 0),
            platforms=[str(v) for v in (mapping.get("platforms") or []) if isinstance(v, str)],
            matchCount=0,
        )

    page = await repo.list_paginated(
        0,
        200,
        project.id,
        "started_at",
        "desc",
        {"include_subagents": True},
    )

    for session_row in page:
        session_id = str(session_row.get("id") or "").strip()
        if not session_id:
            continue
        platform_type = str(session_row.get("platform_type") or "")
        logs = await repo.get_logs(session_id)
        for log in logs:
            log_type = str(log.get("type") or "")
            metadata = _safe_json(log.get("metadata_json"))
            if log_type == "command":
                command_name = str(log.get("content") or "").strip()
                command_args = str(metadata.get("args") or "")
                parsed = metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {}
                match = classify_key_command(
                    command_name,
                    command_args,
                    parsed,
                    mappings,
                    platform_type=platform_type,
                )
                if match:
                    mapping_id = str(match.get("mappingId") or "")
                    if mapping_id in rows_by_id:
                        rows_by_id[mapping_id].matchCount += 1
                continue

            if log_type == "message":
                message_text = str(log.get("content") or "")
                match = classify_transcript_message(
                    message_text,
                    mappings,
                    platform_type=platform_type,
                )
                if match:
                    mapping_id = str(match.get("mappingId") or "")
                    if mapping_id in rows_by_id:
                        rows_by_id[mapping_id].matchCount += 1
                continue

            if log_type != "tool":
                continue

            command_text = _extract_shell_command(log, metadata)
            if not command_text:
                continue
            mapping = classify_bash_command(command_text, mappings, platform_type=platform_type)
            if mapping:
                mapping_id = str(mapping.get("id") or "")
                if mapping_id in rows_by_id:
                    rows_by_id[mapping_id].matchCount += 1

    sorted_rows = sorted(
        rows_by_id.values(),
        key=lambda row: (row.priority, row.label.lower()),
        reverse=True,
    )
    never_matched = [row.id for row in sorted_rows if row.enabled and row.matchCount <= 0]

    return SessionMappingsDiagnostics(
        workflowCommands=workflow_markers,
        nonConsequentialCommands=sorted(workflow_command_exemptions()),
        uncoveredWorkflowCommands=uncovered,
        neverMatchedMappings=never_matched,
        mappingMatches=sorted_rows,
        evaluatedSessions=len(page),
    )


@session_mappings_router.put("", response_model=list[SessionMappingRule])
async def update_session_mappings(
    payload: SessionMappingsPayload,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    project = require_project(request_context, core_ports)
    await require_http_authorization(
        request_context,
        core_ports,
        action="session_mapping:update",
        resource=f"project:{project.id}",
    )
    db = await connection.get_connection()
    mapping_dicts: list[dict[str, Any]] = [m.model_dump() for m in payload.mappings]
    saved = await save_session_mappings(db, project.id, mapping_dicts)
    return [SessionMappingRule(**m) for m in saved]
