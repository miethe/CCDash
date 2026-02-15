"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.models import (
    AgentSession, PlanDocument, ProjectTask,
    AnalyticsMetric, AlertConfig, Notification,
)
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.tasks import SqliteTaskRepository
# We can add AnalyticsRepository usage later

# ── Sessions router ─────────────────────────────────────────────────

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@sessions_router.get("", response_model=list[AgentSession])
async def list_sessions(
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "started_at",
    sort_order: str = "desc",
):
    """Return paginated sessions from DB."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = SqliteSessionRepository(db)
    
    # DB returns dicts, Pydantic will validate them
    sessions_data = await repo.list_paginated(
        offset, limit, project.id, sort_by, sort_order
    )
    
    # Need to hydrate detail fields? 
    # For the list view, we often don't need full logs, tools, etc.
    # But the frontend model AgentSession includes them.
    # To keep list response fast, we might return them empty or minimal.
    # The repository `list_paginated` only returns columns from `sessions` table.
    
    # Efficient approach: don't hydrate details for list view.
    # The frontend usually fetches details ID-by-ID or we can create a AgentSessionSummary model.
    # For now, satisfying the AgentSession model with empty lists is acceptable for list view performance.
    
    results = []
    for s in sessions_data:
        # Pydantic model expect camelCase for fields, but DB has snake_case
        # We need to map them or use an alias generator or construct carefully.
        # Actually our Pydantic models in models.py don't seem to use aliases for snake_case db columns...
        # Wait, the models use camelCase (taskId, totalCost).
        # We need to map DB columns to model fields.
        
        results.append(AgentSession(
            id=s["id"],
            taskId=s["task_id"] or "",
            status=s["status"] or "completed",
            model=s["model"] or "",
            durationSeconds=s["duration_seconds"],
            tokensIn=s["tokens_in"],
            tokensOut=s["tokens_out"],
            totalCost=s["total_cost"],
            startedAt=s["started_at"] or "",
            qualityRating=s["quality_rating"],
            frictionRating=s["friction_rating"],
            gitCommitHash=s["git_commit_hash"],
            gitAuthor=s["git_author"],
            gitBranch=s["git_branch"],
            updatedFiles=[], # omitted in list
            linkedArtifacts=[], # omitted in list
            toolsUsed=[], # omitted in list
            impactHistory=[], # omitted in list
            logs=[], # omitted in list
        ))
    return results


@sessions_router.get("/{session_id}", response_model=AgentSession)
async def get_session(session_id: str):
    """Return a single session by ID with full details."""
    db = await connection.get_connection()
    repo = SqliteSessionRepository(db)
    
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
                "name": l["tool_name"],
                "args": l["tool_args"] or "",
                "output": l["tool_output"],
                "status": l["tool_status"],
            }
            
        session_logs.append({
            "id": f"log-{l['log_index']}", # verify if we store the ID string or format it
            "timestamp": l["timestamp"],
            "speaker": l["speaker"],
            "type": l["type"],
            "content": l["content"],
            "agentName": l["agent_name"],
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
            "additions": f["additions"],
            "deletions": f["deletions"],
            "agentName": f["agent_name"],
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
        })

    return AgentSession(
        id=s["id"],
        taskId=s["task_id"] or "",
        status=s["status"] or "completed",
        model=s["model"] or "",
        durationSeconds=s["duration_seconds"],
        tokensIn=s["tokens_in"],
        tokensOut=s["tokens_out"],
        totalCost=s["total_cost"],
        startedAt=s["started_at"] or "",
        qualityRating=s["quality_rating"],
        frictionRating=s["friction_rating"],
        gitCommitHash=s["git_commit_hash"],
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
    repo = SqliteDocumentRepository(db)
    docs = await repo.list_all(project.id)
    
    results = []
    import json
    for d in docs:
        fm_json = d["frontmatter_json"]
        fm = json.loads(fm_json) if fm_json else {}
        
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
    repo = SqliteDocumentRepository(db)
    
    d = await repo.get_by_id(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        
    import json
    fm_json = d["frontmatter_json"]
    fm = json.loads(fm_json) if fm_json else {}
    
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
    repo = SqliteTaskRepository(db)
    tasks = await repo.list_all(project.id)
    
    results = []
    for t in tasks:
        # Re-construct from DB fields
        # Note: tags and relatedFiles were stored in data_json or we need to extract them?
        # Creating schema, we stored data_json.
        import json
        data = json.loads(t["data_json"]) if t.get("data_json") else {}
        
        # Merge DB fields with data_json for any missing fields if necessary
        # The parser populated DB columns, so prefer those.
        
        results.append(ProjectTask(
            id=t["id"],
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


# ── Analytics router ────────────────────────────────────────────────

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
async def get_metrics():
    """Derive analytics metrics from DB queries (faster than full scan)."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    # Direct queries for aggregation
    
    async with db.execute(
        "SELECT SUM(total_cost), SUM(tokens_in + tokens_out), COUNT(*) FROM sessions WHERE project_id = ?",
        (project.id,)
    ) as cur:
        row = await cur.fetchone()
        total_cost = row[0] or 0.0
        total_tokens = row[1] or 0
        total_sessions = row[2] or 0
        
    async with db.execute(
        "SELECT COUNT(*), SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) FROM tasks WHERE project_id = ?",
        (project.id,)
    ) as cur:
        row = await cur.fetchone()
        total_tasks = row[0] or 0
        done_tasks = row[1] or 0
        
    completion_pct = (done_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return [
        AnalyticsMetric(name="Total Cost", value=round(total_cost, 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=total_tokens, unit="tokens"),
        AnalyticsMetric(name="Sessions", value=total_sessions, unit="count"),
        AnalyticsMetric(name="Tasks Done", value=done_tasks, unit="count"),
        AnalyticsMetric(name="Total Tasks", value=total_tasks, unit="count"),
        AnalyticsMetric(name="Completion", value=round(completion_pct, 1), unit="%"),
    ]


@analytics_router.get("/alerts", response_model=list[AlertConfig])
async def get_alerts():
    """Return alert configurations from DB."""
    # We implemented SqliteAlertConfigRepository in links.py... wait, yes.
    # But for now, let's just query the table directly or use the repo.
    from backend.db.repositories.links import SqliteAlertConfigRepository
    db = await connection.get_connection()
    repo = SqliteAlertConfigRepository(db)
    
    configs = await repo.list_all()
    results = []
    for c in configs:
        results.append(AlertConfig(
            id=c["id"],
            name=c["name"],
            metric=c["metric"],
            operator=c["operator"],
            threshold=c["threshold"],
            isActive=bool(c["is_active"]),
            scope=c["scope"],
        ))
    return results


@analytics_router.get("/notifications", response_model=list[Notification])
async def get_notifications():
    """Generate notifications from recent session data (DB)."""
    # This logic was mostly stubbed/dynamic. Keeping it dynamic but sourced from DB.
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    # Get 5 recent sessions
    async with db.execute(
        "SELECT id, model, total_cost, duration_seconds, started_at FROM sessions WHERE project_id = ? ORDER BY started_at DESC LIMIT 5",
        (project.id,)
    ) as cur:
        sessions = await cur.fetchall()
        
    notifications: list[Notification] = []
    for i, s in enumerate(sessions):
        notifications.append(Notification(
            id=f"notif-{s['id']}",
            alertId="alert-cost",
            message=f"Session {s['id']}: Model={s['model']}, "
                    f"Cost=${s['total_cost']:.4f}, Duration={s['duration_seconds']}s",
            timestamp=s["started_at"],
            isRead=i > 0,
        ))

    return notifications

