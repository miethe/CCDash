"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

import json

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
)
from backend.model_identity import derive_model_identity

_NON_CONSEQUENTIAL_COMMAND_PREFIXES = {"/clear", "/model"}
_KEY_WORKFLOW_COMMAND_MARKERS = (
    "/dev:execute-phase",
    "/dev:quick-feature",
    "/plan:plan-feature",
    "/dev:implement-story",
    "/dev:complete-user-story",
    "/fix:debug",
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


def _is_primary_session_link(
    strategy: str,
    confidence: float,
    signal_types: set[str],
    commands: list[str],
) -> bool:
    if strategy == "task_frontmatter":
        return True
    if confidence >= 0.9:
        return True
    if confidence >= 0.75 and ("file_write" in signal_types or "command_args_path" in signal_types):
        return True
    if confidence >= 0.55 and any(
        marker in command.lower()
        for command in commands
        for marker in ("/dev:execute-phase", "/dev:quick-feature", "/plan:plan-feature")
    ):
        return True
    return False


def _command_token(command_name: str) -> str:
    normalized = " ".join((command_name or "").strip().split()).lower()
    if not normalized:
        return ""
    return normalized.split()[0]


def _normalize_link_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for raw in commands:
        command = " ".join((raw or "").strip().split())
        if not command:
            continue
        token = _command_token(command)
        if token in _NON_CONSEQUENTIAL_COMMAND_PREFIXES:
            continue
        lowered = command.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(command)
    deduped.sort(
        key=lambda command: (
            next((idx for idx, marker in enumerate(_KEY_WORKFLOW_COMMAND_MARKERS) if marker in command.lower()), len(_KEY_WORKFLOW_COMMAND_MARKERS)),
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


def _derive_session_title(session_metadata: dict | None, summary: str, session_id: str) -> str:
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
    include_subagents: bool = Query(False, description="Include subagent sessions in list results"),
    root_session_id: str | None = Query(None, description="Filter to a specific root thread family"),
    start_date: str | None = Query(None, description="ISO timestamp for start range"),
    end_date: str | None = Query(None, description="ISO timestamp for end range"),
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
    filters["include_subagents"] = include_subagents
    if root_session_id: filters["root_session_id"] = root_session_id
    if start_date: filters["start_date"] = start_date
    if end_date: filters["end_date"] = end_date
    if min_duration is not None: filters["min_duration"] = min_duration
    if max_duration is not None: filters["max_duration"] = max_duration

    # DB returns dicts, Pydantic will validate them
    sessions_data = await repo.list_paginated(
        offset, limit, project.id, sort_by, sort_order, filters
    )
    total_count = await repo.count(project.id, filters)
    
    # Hydrate items (minimal for list view)
    results = []
    for s in sessions_data:
        logs = await repo.get_logs(s["id"])
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
        session_metadata = classify_session_key_metadata(command_events, mappings)
        model_identity = derive_model_identity(s.get("model"))
        session_title = _derive_session_title(session_metadata, latest_summary, s["id"])

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
            sessionType=s["session_type"] or "",
            parentSessionId=s["parent_session_id"],
            rootSessionId=s.get("root_session_id") or s["id"],
            agentId=s.get("agent_id"),
            durationSeconds=s["duration_seconds"],
            tokensIn=s["tokens_in"],
            tokensOut=s["tokens_out"],
            totalCost=s["total_cost"],
            startedAt=s["started_at"] or "",
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
        ))
        
    return PaginatedResponse(
        items=results,
        total=total_count,
        offset=offset,
        limit=limit
    )


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
    tools = await repo.get_tool_usage(session_id)
    files = await repo.get_file_updates(session_id)
    artifacts = await repo.get_artifacts(session_id)
    
    # Transform details to model format
    
    # Logs
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
        if tc and tc.get("name") == "Bash":
            command_text = _extract_bash_command(metadata, l.get("tool_args"))
            mapping = classify_bash_command(command_text, mappings)
            if mapping:
                metadata["originalToolName"] = "Bash"
                metadata["toolCategory"] = mapping.get("category", "bash")
                metadata["toolMappingId"] = mapping.get("id", "")
                mapped_label = str(mapping.get("transcriptLabel") or mapping.get("label") or "Shell")
                metadata["toolLabel"] = mapped_label
                tc["name"] = mapped_label
            elif isinstance(metadata.get("toolLabel"), str) and metadata["toolLabel"].strip():
                tc["name"] = metadata["toolLabel"].strip()
            
        session_logs.append({
            "id": f"log-{l['log_index']}", # verify if we store the ID string or format it
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

    session_metadata = classify_session_key_metadata(command_events, mappings)
    model_identity = derive_model_identity(s.get("model"))
    session_title = _derive_session_title(session_metadata, latest_summary, s["id"])
        
    # Tools
    tool_usage = []
    for t in tools:
        tool_usage.append({
            "name": t["tool_name"],
            "count": t["call_count"],
            "successRate": t["success_count"] / t["call_count"] if t["call_count"] > 0 else 0.0,
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
        sessionType=s["session_type"] or "",
        parentSessionId=s["parent_session_id"],
        rootSessionId=s.get("root_session_id") or s["id"],
        agentId=s.get("agent_id"),
        durationSeconds=s["duration_seconds"],
        tokensIn=s["tokens_in"],
        tokensOut=s["tokens_out"],
        totalCost=s["total_cost"],
        startedAt=s["started_at"] or "",
        qualityRating=s["quality_rating"],
        frictionRating=s["friction_rating"],
        gitCommitHash=s["git_commit_hash"],
        gitCommitHashes=[str(v) for v in _safe_json_list(s.get("git_commit_hashes_json"))],
        gitAuthor=s["git_author"],
        gitBranch=s["git_branch"],
        updatedFiles=file_updates,
        linkedArtifacts=linked_artifacts,
        toolsUsed=tool_usage,
        impactHistory=[], # We didn't persist impact history separately in DB schema plan? 
                          # Ah, impacts logic was in parser but not in schema?
                          # Checking schema... no impact_history table.
                          # We can store it as JSON in metadata or add a table later.
                          # For now, return empty list.
        logs=session_logs,
        sessionMetadata=session_metadata,
    )


@sessions_router.get("/{session_id}/linked-features", response_model=list[SessionFeatureLink])
async def get_session_linked_features(session_id: str):
    """Return linked features for a session using the same confidence logic as feature→session links."""
    db = await connection.get_connection()
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
        normalized_commands = _normalize_link_commands([str(v) for v in commands if isinstance(v, str)])
        commit_hashes = metadata.get("commitHashes", [])
        if not isinstance(commit_hashes, list):
            commit_hashes = []
        confidence = float(link.get("confidence") or 0.0)
        is_primary = _is_primary_session_link(strategy, confidence, signal_types, normalized_commands)

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


# ── Documents router ────────────────────────────────────────────────

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])


@documents_router.get("", response_model=list[PlanDocument])
async def list_documents():
    """Return all parsed plan documents (frontmatter only)."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_document_repository(db)
    docs = await repo.list_all(project.id)
    
    results = []
    for d in docs:
        fm = _safe_json(d.get("frontmatter_json"))
        
        results.append(PlanDocument(
            id=d["id"],
            title=d["title"],
            filePath=d["file_path"],
            status=d["status"],
            lastModified=d["last_modified"] or "",
            author=d["author"] or "",
            frontmatter=fm,
            content=None, # Strip content
        ))
    return results


@documents_router.get("/{doc_id}", response_model=PlanDocument)
async def get_document(doc_id: str):
    """Return a single document with full content."""
    db = await connection.get_connection()
    repo = get_document_repository(db)
    
    d = await repo.get_by_id(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        
    fm = _safe_json(d.get("frontmatter_json"))
    
    return PlanDocument(
        id=d["id"],
        title=d["title"],
        filePath=d["file_path"],
        status=d["status"],
        lastModified=d["last_modified"] or "",
        author=d["author"] or "",
        frontmatter=fm,
        content=d["content"],
    )


# ── Tasks router ────────────────────────────────────────────────────

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@tasks_router.get("", response_model=list[ProjectTask])
async def list_tasks():
    """Return all tasks from DB."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_task_repository(db)
    tasks = await repo.list_all(project.id)
    
    results = []
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
    return results
