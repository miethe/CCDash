"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

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
)
from backend.session_mappings import classify_bash_command, load_session_mappings


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
    
    # Construct filter dict
    filters = {}
    if status: filters["status"] = status
    if model: filters["model"] = model
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
        results.append(AgentSession(
            id=s["id"],
            taskId=s["task_id"] or "",
            status=s["status"] or "completed",
            model=s["model"] or "",
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
        taskId=s["task_id"] or "",
        status=s["status"] or "completed",
        model=s["model"] or "",
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
    )


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
