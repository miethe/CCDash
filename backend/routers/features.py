"""Features API router."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.models import Feature, ProjectTask, FeaturePhase
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.factory import (
    get_entity_link_repository,
    get_feature_repository,
    get_session_repository,
    get_task_repository,
)

# Still need parsers to resolve file paths for updates?
# Write-through logic: Update frontmatter file -> FileWatcher syncs it back to DB
from backend.parsers.features import (
    resolve_file_for_feature,
    resolve_file_for_phase,
)
from backend.parsers.status_writer import update_frontmatter_field, update_task_in_frontmatter
from backend.session_mappings import classify_session_key_metadata, load_session_mappings
from backend.model_identity import derive_model_identity


features_router = APIRouter(prefix="/api/features", tags=["features"])
logger = logging.getLogger("ccdash.features")

_NON_CONSEQUENTIAL_COMMAND_PREFIXES = {"/clear", "/model"}
_KEY_WORKFLOW_COMMAND_MARKERS = (
    "/dev:execute-phase",
    "/dev:quick-feature",
    "/plan:plan-feature",
    "/dev:implement-story",
    "/dev:complete-user-story",
    "/fix:debug",
)

# ── Request models ──────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    status: str  # backlog | in-progress | review | done


# ── Status value mapping (frontend values → frontmatter values) ─────

_REVERSE_STATUS = {
    "done": "completed",
    "in-progress": "in-progress",
    "review": "review",
    "backlog": "draft",
}


# ── Response models ─────────────────────────────────────────────────

class TaskSourceResponse(BaseModel):
    filePath: str
    content: str


class FeatureSessionLink(BaseModel):
    sessionId: str
    title: str = ""
    titleSource: str = ""
    titleConfidence: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    commitHashes: list[str] = Field(default_factory=list)
    status: str = "completed"
    model: str = ""
    modelDisplayName: str = ""
    modelProvider: str = ""
    modelFamily: str = ""
    modelVersion: str = ""
    startedAt: str = ""
    totalCost: float = 0.0
    durationSeconds: int = 0
    gitCommitHash: str | None = None
    gitCommitHashes: list[str] = Field(default_factory=list)
    sessionType: str = ""
    parentSessionId: str | None = None
    rootSessionId: str = ""
    agentId: str | None = None
    isSubthread: bool = False
    isPrimaryLink: bool = False
    linkStrategy: str = ""
    workflowType: str = ""
    sessionMetadata: dict[str, Any] | None = None


def _safe_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _safe_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


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


def _normalize_link_title(title: str, commands: list[str], feature_id: str) -> str:
    normalized = " ".join((title or "").strip().split())
    if not normalized:
        return ""
    if _command_token(normalized) in _NON_CONSEQUENTIAL_COMMAND_PREFIXES:
        if commands:
            return f"{commands[0]} - {feature_id}"
        return ""
    return normalized


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


def _classify_session_workflow(strategy: str, commands: list[str], signal_types: set[str], session_type: str) -> str:
    haystack = " ".join([strategy, session_type, *commands, *sorted(signal_types)]).lower()
    if "/plan:" in haystack or "planning" in haystack or "plan" in haystack:
        return "Planning"
    if any(token in haystack for token in ("debug", "bug", "fix", "error", "traceback")):
        return "Debug"
    if any(token in haystack for token in ("enhance", "improve", "refactor", "optimiz", "cleanup")):
        return "Enhancement"
    if any(token in haystack for token in ("execute", "implement", "quick-feature", "file_write", "command_args_path")):
        return "Execution"
    if "subagent" in haystack:
        return "Execution"
    return "Related"


def _task_from_db_row(row: dict[str, Any]) -> ProjectTask:
    data = _safe_json(row.get("data_json"))
    raw_task_id = data.get("rawTaskId") or row["id"]
    return ProjectTask(
        id=str(raw_task_id),
        title=row["title"],
        description=row["description"] or "",
        status=row["status"],
        owner=row["owner"] or "",
        lastAgent=row["last_agent"] or "",
        cost=row["cost"] or 0.0,
        priority=row["priority"] or "medium",
        projectType=row["project_type"] or "",
        projectLevel=row["project_level"] or "",
        tags=data.get("tags", []),
        updatedAt=row["updated_at"] or "",
        relatedFiles=data.get("relatedFiles", []),
        sourceFile=row["source_file"] or "",
        sessionId=row["session_id"] or "",
        commitHash=row["commit_hash"] or "",
        featureId=row["feature_id"],
        phaseId=row["phase_id"]
    )


def _task_from_feature_blob(task_data: dict[str, Any], feature_id: str, phase_id: str) -> ProjectTask:
    raw_task_id = str(task_data.get("rawTaskId") or task_data.get("id") or "")
    return ProjectTask(
        id=raw_task_id,
        title=str(task_data.get("title", "")),
        description=str(task_data.get("description", "")),
        status=str(task_data.get("status", "backlog")),
        owner=str(task_data.get("owner", "")),
        lastAgent=str(task_data.get("lastAgent", "")),
        cost=float(task_data.get("cost", 0.0) or 0.0),
        priority=str(task_data.get("priority", "medium")),
        projectType=str(task_data.get("projectType", "")),
        projectLevel=str(task_data.get("projectLevel", "")),
        tags=[str(t) for t in (task_data.get("tags", []) or [])],
        updatedAt=str(task_data.get("updatedAt", "")),
        relatedFiles=[str(f) for f in (task_data.get("relatedFiles", []) or [])],
        sourceFile=str(task_data.get("sourceFile", "")),
        sessionId=str(task_data.get("sessionId", "")),
        commitHash=str(task_data.get("commitHash", "")),
        featureId=feature_id,
        phaseId=phase_id,
    )


# ── GET endpoints ───────────────────────────────────────────────────

@features_router.get("", response_model=list[Feature])
async def list_features():
    """Return all discovered features from DB."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_feature_repository(db)
    
    features_data = await repo.list_all(project.id)
    
    results = []
    for f in features_data:
        # Phases
        phases_data = await repo.get_phases(f["id"])
        phases = []
        for p in phases_data:
            phases.append({
                "id": p["id"],
                "phase": p["phase"],
                "title": p["title"],
                "status": p["status"],
                "progress": p["progress"],
                "totalTasks": p["total_tasks"],
                "completedTasks": p["completed_tasks"],
                "tasks": [], # stripped for list
            })
            
        data = _safe_json(f.get("data_json"))
        
        results.append(Feature(
            id=f["id"],
            name=f["name"],
            status=f["status"],
            totalTasks=f["total_tasks"],
            completedTasks=f["completed_tasks"],
            category=f["category"],
            tags=data.get("tags", []),
            updatedAt=f["updated_at"] or "",
            linkedDocs=data.get("linkedDocs", []),
            phases=phases,
            relatedFeatures=data.get("relatedFeatures", []),
        ))
    return results


@features_router.get("/task-source", response_model=TaskSourceResponse)
async def get_task_source(file: str):
    """Return the raw markdown content of a progress/plan file."""
    # This remains file-based for viewing raw source
    from pathlib import Path

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    project_root = progress_dir.parent

    target = project_root / file
    if not target.exists():
        target = docs_dir.parent / file
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {file}")

    # Security check
    try:
        target.resolve().relative_to(project_root.resolve())
    except ValueError:
        try:
            target.resolve().relative_to(docs_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return TaskSourceResponse(filePath=file, content=content)


@features_router.get("/{feature_id}", response_model=Feature)
async def get_feature(feature_id: str):
    """Return full feature detail from DB."""
    db = await connection.get_connection()
    repo = get_feature_repository(db)
    
    f = await repo.get_by_id(feature_id)
    if not f:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")
        
    data = _safe_json(f.get("data_json"))

    # Phases with tasks
    phases_data = await repo.get_phases(f["id"])
    phases = []
    
    task_repo = get_task_repository(db)
    all_tasks_data = await task_repo.list_by_feature(f["id"], None)
    tasks_by_phase: dict[str, list[dict[str, Any]]] = {}
    for row in all_tasks_data:
        phase_key = str(row.get("phase_id") or "")
        tasks_by_phase.setdefault(phase_key, []).append(row)
    
    blob_phase_tasks: dict[str, list[list[dict[str, Any]]]] = {}
    for phase_blob in data.get("phases", []):
        if not isinstance(phase_blob, dict):
            continue
        phase_key = str(phase_blob.get("phase", ""))
        tasks_blob = phase_blob.get("tasks", [])
        if isinstance(tasks_blob, list):
            blob_phase_tasks.setdefault(phase_key, []).append(tasks_blob)

    for p in phases_data:
        tasks_data = tasks_by_phase.get(str(p.get("id") or ""), [])

        p_tasks = []
        if tasks_data:
            p_tasks = [_task_from_db_row(t) for t in tasks_data]
        else:
            # Fallback for legacy rows where task PK collisions broke phase linkage.
            phase_key = str(p.get("phase", ""))
            candidates = blob_phase_tasks.get(phase_key, [])
            if candidates:
                raw_tasks = candidates.pop(0)
                for raw_task in raw_tasks:
                    if isinstance(raw_task, dict):
                        p_tasks.append(_task_from_feature_blob(raw_task, f["id"], p["id"]))

        phases.append(FeaturePhase(
            id=p["id"],
            phase=p["phase"],
            title=p["title"] or "",
            status=p["status"],
            progress=p["progress"] or 0,
            totalTasks=p["total_tasks"] or 0,
            completedTasks=p["completed_tasks"] or 0,
            tasks=p_tasks,
        ))

    return Feature(
        id=f["id"],
        name=f["name"],
        status=f["status"],
        totalTasks=f["total_tasks"],
        completedTasks=f["completed_tasks"],
        category=f["category"],
        tags=data.get("tags", []),
        updatedAt=f["updated_at"] or "",
        linkedDocs=data.get("linkedDocs", []),
        phases=phases,
        relatedFeatures=data.get("relatedFeatures", []),
    )


@features_router.get("/{feature_id}/linked-sessions", response_model=list[FeatureSessionLink])
async def get_feature_linked_sessions(feature_id: str):
    """Return linked sessions for a feature using confidence-scored entity links."""
    db = await connection.get_connection()
    active_project = project_manager.get_active_project()
    mappings = await load_session_mappings(db, active_project.id) if active_project else []
    feature_repo = get_feature_repository(db)
    feature = await feature_repo.get_by_id(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    link_repo = get_entity_link_repository(db)
    session_repo = get_session_repository(db)
    links = await link_repo.get_links_for("feature", feature_id, "related")

    items: list[FeatureSessionLink] = []
    for link in links:
        if link.get("source_type") != "feature" or link.get("source_id") != feature_id:
            continue
        if link.get("target_type") != "session":
            continue

        session_id = str(link.get("target_id") or "").strip()
        if not session_id:
            continue

        session_row = await session_repo.get_by_id(session_id)
        if not session_row:
            continue
        logs = await session_repo.get_logs(session_id)

        metadata = _safe_json(link.get("metadata_json"))
        reasons: list[str] = []

        strategy = str(metadata.get("linkStrategy") or "").strip()
        if strategy:
            reasons.append(strategy)
        signal_types: set[str] = set()
        signals = metadata.get("signals", [])
        if isinstance(signals, list):
            for signal in signals[:8]:
                if isinstance(signal, dict):
                    signal_type = str(signal.get("type") or "").strip()
                    if signal_type:
                        signal_types.add(signal_type)
                        reasons.append(signal_type)

        commands = metadata.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        normalized_commands = _normalize_link_commands([str(v) for v in commands if isinstance(v, str)])
        metadata_hashes = metadata.get("commitHashes", [])
        if not isinstance(metadata_hashes, list):
            metadata_hashes = []
        row_hashes = [str(v) for v in _safe_json_list(session_row.get("git_commit_hashes_json")) if isinstance(v, str)]
        merged_hashes = sorted(set([str(v) for v in metadata_hashes if isinstance(v, str)]).union(row_hashes))
        confidence = float(link.get("confidence") or 0.0)
        model_identity = derive_model_identity(session_row.get("model"))
        session_type = str(session_row.get("session_type") or "")
        parent_session_id = session_row.get("parent_session_id")
        root_session_id = str(session_row.get("root_session_id") or session_id)
        is_subthread = bool(parent_session_id) or session_type == "subagent"
        is_primary_link = _is_primary_session_link(strategy, confidence, signal_types, normalized_commands)
        workflow_type = _classify_session_workflow(strategy, normalized_commands, signal_types, session_type)
        command_events: list[dict[str, Any]] = []
        latest_summary = ""
        for log in logs:
            raw_metadata = log.get("metadata_json")
            parsed_metadata: dict[str, Any] = {}
            if isinstance(raw_metadata, str) and raw_metadata:
                parsed_metadata = _safe_json(raw_metadata)
            elif isinstance(raw_metadata, dict):
                parsed_metadata = raw_metadata
            if str(log.get("type") or "") == "system" and str(parsed_metadata.get("eventType") or "").strip().lower() == "summary":
                summary_text = str(log.get("content") or "").strip()
                if summary_text:
                    latest_summary = summary_text
            if str(log.get("type") or "") != "command":
                continue
            command_events.append({
                "name": str(log.get("content") or "").strip(),
                "args": str(parsed_metadata.get("args") or ""),
                "parsedCommand": parsed_metadata.get("parsedCommand") if isinstance(parsed_metadata.get("parsedCommand"), dict) else {},
            })
        session_metadata = classify_session_key_metadata(command_events, mappings)
        session_title = _derive_session_title(session_metadata, latest_summary, session_id)
        reasons = list(dict.fromkeys(reasons))

        items.append(
            FeatureSessionLink(
                sessionId=session_id,
                title=session_title,
                titleSource=str(metadata.get("titleSource") or ""),
                titleConfidence=float(metadata.get("titleConfidence") or 0.0),
                confidence=confidence,
                reasons=reasons,
                commands=normalized_commands[:12],
                commitHashes=merged_hashes,
                status=str(session_row.get("status") or "completed"),
                model=str(session_row.get("model") or ""),
                modelDisplayName=model_identity["modelDisplayName"],
                modelProvider=model_identity["modelProvider"],
                modelFamily=model_identity["modelFamily"],
                modelVersion=model_identity["modelVersion"],
                startedAt=str(session_row.get("started_at") or ""),
                totalCost=float(session_row.get("total_cost") or 0.0),
                durationSeconds=int(session_row.get("duration_seconds") or 0),
                gitCommitHash=session_row.get("git_commit_hash"),
                gitCommitHashes=merged_hashes,
                sessionType=session_type,
                parentSessionId=parent_session_id,
                rootSessionId=root_session_id,
                agentId=session_row.get("agent_id"),
                isSubthread=is_subthread,
                isPrimaryLink=is_primary_link,
                linkStrategy=strategy,
                workflowType=workflow_type,
                sessionMetadata=session_metadata,
            )
        )

    items.sort(key=lambda item: (item.confidence, item.startedAt), reverse=True)
    return items


# ── PATCH endpoints (Write-Through) ─────────────────────────────────

async def _sync_changed_feature_files(
    request: Request,
    project_id: str,
    file_paths: list,
    sessions_dir,
    docs_dir,
    progress_dir,
) -> None:
    """Force-sync a changed docs/progress file for immediate feature consistency."""
    sync_engine = getattr(request.app.state, "sync_engine", None)
    if sync_engine is None:
        logger.warning("Sync engine not available in app state; relying on file watcher")
        return
    changed_files = [("modified", path) for path in file_paths]
    if not changed_files:
        return
    await sync_engine.sync_changed_files(project_id, changed_files, sessions_dir, docs_dir, progress_dir)


@features_router.patch("/{feature_id}/status", response_model=Feature)
async def update_feature_status(feature_id: str, req: StatusUpdateRequest, request: Request):
    """Update a feature's top-level status."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    changed_files = []

    top_level_file = resolve_file_for_feature(feature_id, docs_dir, progress_dir)
    if top_level_file:
        update_frontmatter_field(top_level_file, "status", fm_status)
        changed_files.append(top_level_file)

    # Keep derived feature status consistent by updating any phase progress files.
    db = await connection.get_connection()
    repo = get_feature_repository(db)
    phases = await repo.get_phases(feature_id)
    for phase in phases:
        phase_num = str(phase.get("phase", ""))
        phase_file = resolve_file_for_phase(feature_id, phase_num, progress_dir)
        if phase_file:
            update_frontmatter_field(phase_file, "status", fm_status)
            if phase_file not in changed_files:
                changed_files.append(phase_file)

    if not changed_files:
        raise HTTPException(status_code=404, detail=f"No source files found for feature '{feature_id}'")

    await _sync_changed_feature_files(
        request,
        active_project.id,
        changed_files,
        sessions_dir,
        docs_dir,
        progress_dir,
    )
    return await get_feature(feature_id)


@features_router.patch("/{feature_id}/phases/{phase_id}/status", response_model=Feature)
async def update_phase_status(feature_id: str, phase_id: str, req: StatusUpdateRequest, request: Request):
    """Update a specific phase's status."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()

    file_path = resolve_file_for_phase(feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{feature_id}', phase '{phase_id}'",
        )

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    update_frontmatter_field(file_path, "status", fm_status)
    await _sync_changed_feature_files(
        request,
        active_project.id,
        [file_path],
        sessions_dir,
        docs_dir,
        progress_dir,
    )
    return await get_feature(feature_id)


@features_router.patch("/{feature_id}/phases/{phase_id}/tasks/{task_id}/status", response_model=Feature)
async def update_task_status(feature_id: str, phase_id: str, task_id: str, req: StatusUpdateRequest, request: Request):
    """Update a single task's status."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()

    file_path = resolve_file_for_phase(feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{feature_id}', phase '{phase_id}'",
        )

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    updated = update_task_in_frontmatter(file_path, task_id, "status", fm_status)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found in progress file",
        )

    await _sync_changed_feature_files(
        request,
        active_project.id,
        [file_path],
        sessions_dir,
        docs_dir,
        progress_dir,
    )
    return await get_feature(feature_id)
