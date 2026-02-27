"""Features API router."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.models import (
    Feature,
    ProjectTask,
    FeaturePhase,
    LinkedDocument,
    SessionModelInfo,
    FeatureExecutionAnalyticsSummary,
    FeatureExecutionContext,
    FeatureExecutionWarning,
)
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
from backend.session_badges import derive_session_badges
from backend.document_linking import canonical_slug
from backend.services.feature_execution import (
    build_execution_context,
    load_execution_analytics,
    load_execution_documents,
)


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
_EXECUTION_TELEMETRY_EVENTS = {
    "execution_workbench_opened",
    "execution_begin_work_clicked",
    "execution_recommendation_generated",
    "execution_command_copied",
    "execution_source_link_clicked",
}

# ── Request models ──────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    status: str  # backlog | in-progress | review | done | deferred


class ExecutionTelemetryRequest(BaseModel):
    eventType: str
    featureId: str = ""
    recommendationRuleId: str = ""
    command: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Status value mapping (frontend values → frontmatter values) ─────

_REVERSE_STATUS = {
    "done": "completed",
    "deferred": "deferred",
    "in-progress": "in-progress",
    "review": "review",
    "backlog": "draft",
}
_STATUS_RANK = {
    "backlog": 0,
    "in-progress": 1,
    "review": 2,
    "done": 3,
    "deferred": 3,
}


def _feature_row_score(row: dict[str, Any]) -> tuple[int, int, int, str, int]:
    status = str(row.get("status") or "backlog")
    completed = _safe_int(row.get("completed_tasks"), 0)
    total = _safe_int(row.get("total_tasks"), 0)
    updated_at = str(row.get("updated_at") or "")
    feature_id = str(row.get("id") or "")
    return (
        _STATUS_RANK.get(status, 0),
        completed,
        total,
        updated_at,
        len(feature_id),
    )


async def _resolve_feature_alias_id(repo, project_id: str, feature_id: str) -> str:
    """Choose the best canonical feature row for a requested id alias."""
    base = canonical_slug(feature_id)
    candidates = await repo.list_all(project_id)
    matches = [
        row for row in candidates
        if canonical_slug(str(row.get("id") or "")) == base
    ]
    if not matches:
        return feature_id
    matches.sort(key=_feature_row_score, reverse=True)
    return str(matches[0].get("id") or feature_id)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _normalize_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(v) for v in raw if str(v).strip()]
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    return []


def _normalize_linked_docs(raw: Any) -> list[LinkedDocument]:
    if not isinstance(raw, list):
        return []
    docs: list[LinkedDocument] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("filePath") or "").strip()
        doc_type = str(item.get("docType") or "").strip()
        title = str(item.get("title") or "").strip() or file_path or f"Document {idx + 1}"
        if not file_path or not doc_type:
            continue
        docs.append(LinkedDocument(
            id=str(item.get("id") or f"DOC-{idx}"),
            title=title,
            filePath=file_path,
            docType=doc_type,
            category=str(item.get("category") or ""),
            slug=str(item.get("slug") or ""),
            canonicalSlug=str(item.get("canonicalSlug") or ""),
            frontmatterKeys=[str(v) for v in (item.get("frontmatterKeys") or []) if isinstance(v, str)],
            relatedRefs=[str(v) for v in (item.get("relatedRefs") or []) if isinstance(v, str)],
            prdRef=str(item.get("prdRef") or ""),
            dates=item.get("dates") if isinstance(item.get("dates"), dict) else {},
            timeline=item.get("timeline") if isinstance(item.get("timeline"), list) else [],
        ))
    return docs


# ── Response models ─────────────────────────────────────────────────

class TaskSourceResponse(BaseModel):
    filePath: str
    content: str


class FeatureSessionTaskRef(BaseModel):
    taskId: str
    taskTitle: str = ""
    phaseId: str = ""
    phase: str = ""
    matchedBy: str = ""
    linkedSessionId: str = ""


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
    modelsUsed: list[SessionModelInfo] = Field(default_factory=list)
    agentsUsed: list[str] = Field(default_factory=list)
    skillsUsed: list[str] = Field(default_factory=list)
    toolSummary: list[str] = Field(default_factory=list)
    startedAt: str = ""
    endedAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""
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
    relatedPhases: list[str] = Field(default_factory=list)
    relatedTasks: list[FeatureSessionTaskRef] = Field(default_factory=list)
    sessionMetadata: dict[str, Any] | None = None


_TASK_ID_TOKEN_PATTERN = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z0-9]+)*-\d+(?:\.\d+)?)\b")
_PHASE_FROM_TEXT_PATTERN = re.compile(r"\bphase[\s:_-]*(\d+)\b", re.IGNORECASE)
_PHASE_RANGE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_TITLE_TOKEN_SANITIZER_PATTERN = re.compile(r"[^a-z0-9]+")


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


def _normalize_title_token(value: str) -> str:
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    return _TITLE_TOKEN_SANITIZER_PATTERN.sub(" ", lowered).strip()


def _extract_task_id_from_text(value: str) -> str:
    match = _TASK_ID_TOKEN_PATTERN.search(value or "")
    return match.group(1) if match else ""


def _coerce_task_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=True).strip()
        except Exception:
            return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def _extract_phase_token_from_text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return text
    match = _PHASE_FROM_TEXT_PATTERN.search(text)
    return match.group(1) if match else ""


def _normalize_feature_phase_values(raw_values: list[str], available_phase_tokens: list[str]) -> list[str]:
    available_tokens = [str(value).strip() for value in available_phase_tokens if str(value).strip()]
    available_numeric = sorted({int(value) for value in available_tokens if value.isdigit()})
    ordered: list[str] = []
    seen: set[str] = set()

    def add_token(token: str) -> None:
        clean = str(token or "").strip()
        if not clean or clean in seen:
            return
        seen.add(clean)
        ordered.append(clean)

    for raw in raw_values:
        token = str(raw or "").strip()
        if not token:
            continue
        normalized = token.lower()
        if normalized == "all":
            if available_tokens:
                for phase_token in available_tokens:
                    add_token(phase_token)
            else:
                add_token("all")
            continue

        range_match = _PHASE_RANGE_PATTERN.match(token)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start > end:
                start, end = end, start
            if available_numeric:
                for numeric in available_numeric:
                    if start <= numeric <= end:
                        add_token(str(numeric))
            else:
                for numeric in range(start, end + 1):
                    add_token(str(numeric))
            continue

        if "," in token or "&" in token:
            split_values = [part.strip() for part in re.split(r"[,&]", token) if part.strip()]
            for split_value in split_values:
                phase_token = _extract_phase_token_from_text(split_value) or split_value
                add_token(phase_token)
            continue

        phase_token = _extract_phase_token_from_text(token) or token
        add_token(phase_token)

    return ordered


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
        try:
            data = _safe_json(f.get("data_json"))
            blob_phases = data.get("phases", []) if isinstance(data.get("phases", []), list) else []
            blob_phase_deferred: dict[str, int] = {}
            for phase_blob in blob_phases:
                if not isinstance(phase_blob, dict):
                    continue
                phase_key = str(phase_blob.get("phase", ""))
                blob_phase_deferred[phase_key] = _safe_int(phase_blob.get("deferredTasks", 0), 0)

            # Phases
            phases_data = await repo.get_phases(f["id"])
            phases = []
            total_deferred = 0
            for p in phases_data:
                phase_deferred = blob_phase_deferred.get(str(p.get("phase", "")), 0)
                total_deferred += phase_deferred
                phases.append({
                    "id": p.get("id"),
                    "phase": str(p.get("phase", "")),
                    "title": str(p.get("title") or ""),
                    "status": str(p.get("status") or "backlog"),
                    "progress": _safe_int(p.get("progress"), 0),
                    "totalTasks": _safe_int(p.get("total_tasks"), 0),
                    "completedTasks": _safe_int(p.get("completed_tasks"), 0),
                    "deferredTasks": phase_deferred,
                    "tasks": [], # stripped for list
                })

            deferred_tasks = _safe_int(data.get("deferredTasks", total_deferred), total_deferred)
            related_features = data.get("relatedFeatures", [])
            if not isinstance(related_features, list):
                related_features = []

            results.append(Feature(
                id=str(f.get("id") or ""),
                name=str(f.get("name") or ""),
                status=str(f.get("status") or "backlog"),
                totalTasks=_safe_int(f.get("total_tasks"), 0),
                completedTasks=_safe_int(f.get("completed_tasks"), 0),
                deferredTasks=deferred_tasks,
                category=str(f.get("category") or ""),
                tags=_normalize_tags(data.get("tags", [])),
                updatedAt=str(f.get("updated_at") or ""),
                plannedAt=str(data.get("plannedAt") or ""),
                startedAt=str(data.get("startedAt") or ""),
                completedAt=str(data.get("completedAt") or ""),
                linkedDocs=_normalize_linked_docs(data.get("linkedDocs", [])),
                phases=phases,
                relatedFeatures=[str(v) for v in related_features if str(v).strip()],
                dates=data.get("dates") if isinstance(data.get("dates"), dict) else {},
                timeline=data.get("timeline") if isinstance(data.get("timeline"), list) else [],
            ))
        except Exception:
            logger.exception("Failed to serialize feature row '%s' in list_features", f.get("id"))
            continue
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


@features_router.post("/execution-events")
async def track_execution_event(req: ExecutionTelemetryRequest):
    """Persist execution workbench UI telemetry events."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    event_type = str(req.eventType or "").strip()
    if event_type not in _EXECUTION_TELEMETRY_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type '{event_type}'")

    db = await connection.get_connection()
    occurred_at = datetime.now(timezone.utc).isoformat()
    feature_id = str(req.featureId or "").strip()
    payload = {
        "recommendationRuleId": str(req.recommendationRuleId or "").strip(),
        "command": str(req.command or "").strip(),
        "metadata": req.metadata if isinstance(req.metadata, dict) else {},
    }
    source_key = f"ui-execution:{event_type}:{uuid4().hex}"

    if isinstance(db, aiosqlite.Connection):
        await db.execute(
            """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                active_project.id,
                "ui-execution-workbench",
                "ui-execution-workbench",
                feature_id,
                "",
                "",
                "",
                "",
                event_type,
                "",
                "",
                "frontend",
                "",
                "ok",
                0,
                0,
                0,
                0.0,
                occurred_at,
                0,
                "frontend",
                source_key,
                json.dumps(payload),
            ),
        )
        await db.commit()
    else:
        await db.execute(
            """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20, $21, $22, $23
            )
            """,
            active_project.id,
            "ui-execution-workbench",
            "ui-execution-workbench",
            feature_id,
            "",
            "",
            "",
            "",
            event_type,
            "",
            "",
            "frontend",
            "",
            "ok",
            0,
            0,
            0,
            0.0,
            occurred_at,
            0,
            "frontend",
            source_key,
            json.dumps(payload),
        )

    return {"status": "ok"}


@features_router.get("/{feature_id}/execution-context", response_model=FeatureExecutionContext)
async def get_feature_execution_context(feature_id: str):
    """Return unified context payload for the execution workbench."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    db = await connection.get_connection()
    warnings: list[FeatureExecutionWarning] = []

    feature = await get_feature(feature_id, include_tasks=False)

    sessions: list[FeatureSessionLink] = []
    try:
        sessions = await get_feature_linked_sessions(feature.id)
    except Exception:
        logger.exception("Failed to load execution sessions for '%s'", feature.id)
        warnings.append(
            FeatureExecutionWarning(
                section="sessions",
                message="Linked sessions could not be loaded; showing partial context.",
            )
        )

    documents = feature.linkedDocs
    try:
        documents = await load_execution_documents(
            db,
            active_project.id,
            feature.id,
            feature.linkedDocs,
        )
    except Exception:
        logger.exception("Failed to load execution documents for '%s'", feature.id)
        warnings.append(
            FeatureExecutionWarning(
                section="documents",
                message="Correlated documents could not be loaded; falling back to feature-linked docs.",
            )
        )

    analytics = FeatureExecutionAnalyticsSummary()
    try:
        analytics = await load_execution_analytics(
            db,
            active_project.id,
            feature.id,
            sessions,
        )
    except Exception:
        logger.exception("Failed to load execution analytics for '%s'", feature.id)
        warnings.append(
            FeatureExecutionWarning(
                section="analytics",
                message="Analytics summary is currently unavailable; recommendations are still generated.",
            )
        )

    return build_execution_context(
        feature=feature,
        documents=documents,
        sessions=sessions,
        analytics=analytics,
        warnings=warnings,
    )


@features_router.get("/{feature_id}", response_model=Feature)
async def get_feature(feature_id: str, include_tasks: bool = True):
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
    
    tasks_by_phase: dict[str, list[dict[str, Any]]] = {}
    if include_tasks:
        task_repo = get_task_repository(db)
        all_tasks_data = await task_repo.list_by_feature(f["id"], None)
        for row in all_tasks_data:
            phase_key = str(row.get("phase_id") or "")
            tasks_by_phase.setdefault(phase_key, []).append(row)
    
    blob_phase_tasks: dict[str, list[list[dict[str, Any]]]] = {}
    blob_phase_deferred: dict[str, int] = {}
    for phase_blob in data.get("phases", []):
        if not isinstance(phase_blob, dict):
            continue
        phase_key = str(phase_blob.get("phase", ""))
        deferred_raw = phase_blob.get("deferredTasks", 0)
        try:
            blob_phase_deferred[phase_key] = int(deferred_raw or 0)
        except Exception:
            blob_phase_deferred[phase_key] = 0
        tasks_blob = phase_blob.get("tasks", [])
        if isinstance(tasks_blob, list):
            blob_phase_tasks.setdefault(phase_key, []).append(tasks_blob)

    total_deferred = 0
    for p in phases_data:
        tasks_data = tasks_by_phase.get(str(p.get("id") or ""), []) if include_tasks else []
        phase_key = str(p.get("phase", ""))

        p_tasks = []
        if include_tasks:
            if tasks_data:
                p_tasks = [_task_from_db_row(t) for t in tasks_data]
            else:
                # Fallback for legacy rows where task PK collisions broke phase linkage.
                candidates = blob_phase_tasks.get(phase_key, [])
                if candidates:
                    raw_tasks = candidates.pop(0)
                    for raw_task in raw_tasks:
                        if isinstance(raw_task, dict):
                            p_tasks.append(_task_from_feature_blob(raw_task, f["id"], p["id"]))

        total_tasks = _safe_int(p.get("total_tasks"), 0)
        completed_tasks = _safe_int(p.get("completed_tasks"), 0)
        deferred_tasks = blob_phase_deferred.get(phase_key, 0)
        if include_tasks and p_tasks:
            if total_tasks == 0:
                total_tasks = len(p_tasks)
            done_count = sum(1 for t in p_tasks if t.status == "done")
            deferred_tasks = sum(1 for t in p_tasks if t.status == "deferred")
            completed_tasks = done_count + deferred_tasks
        if completed_tasks < deferred_tasks:
            completed_tasks = deferred_tasks
        total_deferred += deferred_tasks

        phases.append(FeaturePhase(
            id=p.get("id"),
            phase=str(p.get("phase", "")),
            title=str(p.get("title") or ""),
            status=str(p.get("status") or "backlog"),
            progress=_safe_int(p.get("progress"), 0),
            totalTasks=total_tasks,
            completedTasks=completed_tasks,
            deferredTasks=deferred_tasks,
            tasks=p_tasks,
        ))

    deferred_tasks = _safe_int(data.get("deferredTasks", total_deferred), total_deferred)
    related_features = data.get("relatedFeatures", [])
    if not isinstance(related_features, list):
        related_features = []

    return Feature(
        id=str(f.get("id") or ""),
        name=str(f.get("name") or ""),
        status=str(f.get("status") or "backlog"),
        totalTasks=_safe_int(f.get("total_tasks"), 0),
        completedTasks=_safe_int(f.get("completed_tasks"), 0),
        deferredTasks=deferred_tasks,
        category=str(f.get("category") or ""),
        tags=_normalize_tags(data.get("tags", [])),
        updatedAt=str(f.get("updated_at") or ""),
        plannedAt=str(data.get("plannedAt") or ""),
        startedAt=str(data.get("startedAt") or ""),
        completedAt=str(data.get("completedAt") or ""),
        linkedDocs=_normalize_linked_docs(data.get("linkedDocs", [])),
        phases=phases,
        relatedFeatures=[str(v) for v in related_features if str(v).strip()],
        dates=data.get("dates") if isinstance(data.get("dates"), dict) else {},
        timeline=data.get("timeline") if isinstance(data.get("timeline"), list) else [],
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
    task_repo = get_task_repository(db)
    links = await link_repo.get_links_for("feature", feature_id, "related")

    feature_phases = await feature_repo.get_phases(feature_id)
    phase_token_by_phase_id: dict[str, str] = {}
    available_phase_tokens: list[str] = []
    for phase_row in feature_phases:
        phase_id = str(phase_row.get("id") or "").strip()
        phase_token = str(phase_row.get("phase") or "").strip()
        if phase_id and phase_token:
            phase_token_by_phase_id[phase_id] = phase_token
        if phase_token and phase_token not in available_phase_tokens:
            available_phase_tokens.append(phase_token)

    feature_task_rows = await task_repo.list_by_feature(feature_id, None)
    tasks_by_identifier: dict[str, list[dict[str, str]]] = {}
    tasks_by_title: dict[str, list[dict[str, str]]] = {}
    for task_row in feature_task_rows:
        row_data = _safe_json(task_row.get("data_json"))
        task_id = str(task_row.get("id") or "").strip()
        raw_task_id = str(row_data.get("rawTaskId") or task_id).strip()
        task_title = str(task_row.get("title") or "").strip()
        phase_id = str(task_row.get("phase_id") or "").strip()
        phase_token = phase_token_by_phase_id.get(phase_id, "")
        record = {
            "taskId": raw_task_id or task_id,
            "taskTitle": task_title,
            "phaseId": phase_id,
            "phase": phase_token,
            "canonicalTaskId": task_id,
        }
        for raw_identifier in {task_id, raw_task_id}:
            identifier = raw_identifier.lower().strip()
            if not identifier:
                continue
            tasks_by_identifier.setdefault(identifier, []).append(record)

        title_token = _normalize_title_token(task_title)
        if title_token:
            tasks_by_title.setdefault(title_token, []).append(record)

    async def build_session_link_item(
        session_row: dict[str, Any],
        metadata: dict[str, Any],
        confidence: float,
        inherited: bool = False,
    ) -> FeatureSessionLink:
        session_id = str(session_row.get("id") or "").strip()
        logs = await session_repo.get_logs(session_id)
        badge_data = derive_session_badges(
            logs,
            primary_model=str(session_row.get("model") or ""),
            session_agent_id=session_row.get("agent_id"),
        )

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

        model_identity = derive_model_identity(session_row.get("model"))
        session_type = str(session_row.get("session_type") or "")
        parent_session_id = session_row.get("parent_session_id")
        root_session_id = str(session_row.get("root_session_id") or session_id)
        is_subthread = bool(parent_session_id) or session_type == "subagent"
        is_primary_link = False if inherited else _is_primary_session_link(strategy, confidence, signal_types, normalized_commands)
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

        phase_candidates: list[str] = []
        for command_event in command_events:
            parsed_command = command_event.get("parsedCommand") if isinstance(command_event.get("parsedCommand"), dict) else {}
            parsed_phases = parsed_command.get("phases")
            if isinstance(parsed_phases, list):
                phase_candidates.extend(str(value) for value in parsed_phases if str(value).strip())
            parsed_phase_token = str(parsed_command.get("phaseToken") or "").strip()
            if parsed_phase_token:
                phase_candidates.append(parsed_phase_token)
        if isinstance(signals, list):
            for signal in signals:
                if not isinstance(signal, dict):
                    continue
                signal_phase = str(signal.get("phaseToken") or "").strip()
                if signal_phase:
                    phase_candidates.append(signal_phase)

        related_tasks_by_key: dict[str, FeatureSessionTaskRef] = {}
        for log in logs:
            if str(log.get("type") or "") != "tool":
                continue
            if str(log.get("tool_name") or "").strip() != "Task":
                continue

            raw_metadata = log.get("metadata_json")
            parsed_metadata: dict[str, Any] = {}
            if isinstance(raw_metadata, str) and raw_metadata:
                parsed_metadata = _safe_json(raw_metadata)
            elif isinstance(raw_metadata, dict):
                parsed_metadata = raw_metadata

            parsed_tool_args = _safe_json(log.get("tool_args")) if isinstance(log.get("tool_args"), str) else {}
            task_name = str(parsed_metadata.get("taskName") or "").strip()
            if not task_name:
                task_name = str(parsed_tool_args.get("name") or "").strip()
            task_description = str(parsed_metadata.get("taskDescription") or "").strip()
            if not task_description:
                task_description = str(parsed_tool_args.get("description") or "").strip()
            task_prompt = str(parsed_metadata.get("taskPromptPreview") or "").strip()
            if not task_prompt:
                task_prompt = _coerce_task_text(parsed_tool_args.get("prompt"))
            task_id = str(parsed_metadata.get("taskId") or "").strip()
            if not task_id:
                task_id = _extract_task_id_from_text(task_name) or _extract_task_id_from_text(task_description) or _extract_task_id_from_text(task_prompt)
            linked_session_id = str(log.get("linked_session_id") or "").strip()

            matched_records: list[tuple[dict[str, str], str]] = []
            if task_id:
                for match in tasks_by_identifier.get(task_id.lower(), []):
                    matched_records.append((match, "task_id_exact"))

            if not matched_records:
                candidate_texts = [
                    ("task_title_exact", task_name),
                    ("task_description_exact", task_description),
                ]
                for match_label, candidate_text in candidate_texts:
                    candidate_token = _normalize_title_token(candidate_text)
                    if not candidate_token:
                        continue
                    for match in tasks_by_title.get(candidate_token, []):
                        matched_records.append((match, match_label))
                    if matched_records:
                        break

                    for title_token, task_matches in tasks_by_title.items():
                        if candidate_token in title_token or title_token in candidate_token:
                            for match in task_matches:
                                matched_records.append((match, match_label.replace("_exact", "_fuzzy")))
                            if matched_records:
                                break
                    if matched_records:
                        break

            for matched_record, matched_by in matched_records:
                task_token = str(matched_record.get("taskId") or "").strip()
                if not task_token:
                    continue
                related_task = FeatureSessionTaskRef(
                    taskId=task_token,
                    taskTitle=str(matched_record.get("taskTitle") or ""),
                    phaseId=str(matched_record.get("phaseId") or ""),
                    phase=str(matched_record.get("phase") or ""),
                    matchedBy=matched_by,
                    linkedSessionId=linked_session_id,
                )
                unique_key = f"{related_task.taskId}::{related_task.linkedSessionId}::{related_task.phaseId}"
                related_tasks_by_key.setdefault(unique_key, related_task)
                if related_task.phase:
                    phase_candidates.append(related_task.phase)

        session_metadata = classify_session_key_metadata(command_events, mappings)
        if session_metadata and isinstance(session_metadata.get("relatedPhases"), list):
            phase_candidates.extend(str(value) for value in session_metadata.get("relatedPhases", []) if str(value).strip())

        normalized_related_phases = _normalize_feature_phase_values(phase_candidates, available_phase_tokens)
        if session_metadata:
            session_metadata = {
                **session_metadata,
                "relatedPhases": normalized_related_phases,
            }

        related_tasks = sorted(
            related_tasks_by_key.values(),
            key=lambda item: (
                _safe_int(item.phase, 0) if item.phase.isdigit() else 0,
                item.taskId,
                item.linkedSessionId,
            ),
        )
        session_title = _derive_session_title(session_metadata, latest_summary, session_id)
        reasons = list(dict.fromkeys(reasons))

        return FeatureSessionLink(
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
            modelsUsed=badge_data["modelsUsed"],
            agentsUsed=badge_data["agentsUsed"],
            skillsUsed=badge_data["skillsUsed"],
            toolSummary=badge_data["toolSummary"],
            startedAt=str(session_row.get("started_at") or ""),
            endedAt=str(session_row.get("ended_at") or ""),
            createdAt=str(session_row.get("created_at") or ""),
            updatedAt=str(session_row.get("updated_at") or ""),
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
            relatedPhases=normalized_related_phases,
            relatedTasks=related_tasks,
            sessionMetadata=session_metadata,
        )

    items_by_session_id: dict[str, FeatureSessionLink] = {}
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
        metadata = _safe_json(link.get("metadata_json"))
        confidence = float(link.get("confidence") or 0.0)
        candidate = await build_session_link_item(session_row, metadata, confidence)
        existing = items_by_session_id.get(session_id)
        if not existing or candidate.confidence > existing.confidence:
            items_by_session_id[session_id] = candidate

    # Keep thread context coherent in the feature sessions tree by inheriting
    # all sub-threads under directly linked main/root sessions.
    if active_project and items_by_session_id:
        root_ids_to_expand: set[str] = set()
        for item in items_by_session_id.values():
            if item.isSubthread:
                continue
            root_id = (item.rootSessionId or item.sessionId or "").strip()
            if root_id:
                root_ids_to_expand.add(root_id)

        if not root_ids_to_expand:
            for item in items_by_session_id.values():
                root_id = (item.rootSessionId or item.parentSessionId or item.sessionId or "").strip()
                if root_id:
                    root_ids_to_expand.add(root_id)

        for root_id in root_ids_to_expand:
            total = await session_repo.count(
                active_project.id,
                {"include_subagents": True, "root_session_id": root_id},
            )
            if total <= 0:
                continue

            offset = 0
            while offset < total:
                page = await session_repo.list_paginated(
                    offset,
                    250,
                    active_project.id,
                    "started_at",
                    "desc",
                    {"include_subagents": True, "root_session_id": root_id},
                )
                if not page:
                    break

                for session_row in page:
                    session_id = str(session_row.get("id") or "").strip()
                    if not session_id or session_id in items_by_session_id:
                        continue
                    inherited_metadata = {
                        "linkStrategy": "thread_inheritance",
                        "signals": [{"type": "thread_inheritance", "rootSessionId": root_id}],
                        "commands": [],
                        "commitHashes": [str(v) for v in _safe_json_list(session_row.get("git_commit_hashes_json")) if isinstance(v, str)],
                        "titleSource": "thread",
                        "titleConfidence": 0.35,
                    }
                    inherited_confidence = 0.34
                    candidate = await build_session_link_item(
                        session_row,
                        inherited_metadata,
                        inherited_confidence,
                        inherited=True,
                    )
                    items_by_session_id[session_id] = candidate

                offset += len(page)
                if len(page) < 250:
                    break

    items = list(items_by_session_id.values())
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
    db = await connection.get_connection()
    repo = get_feature_repository(db)
    target_feature_id = await _resolve_feature_alias_id(repo, active_project.id, feature_id)

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    changed_files = []

    top_level_file = resolve_file_for_feature(target_feature_id, docs_dir, progress_dir)
    if top_level_file:
        update_frontmatter_field(top_level_file, "status", fm_status)
        changed_files.append(top_level_file)

    # Keep derived feature status consistent by updating any phase progress files.
    phases = await repo.get_phases(target_feature_id)
    for phase in phases:
        phase_num = str(phase.get("phase", ""))
        phase_file = resolve_file_for_phase(target_feature_id, phase_num, progress_dir)
        if phase_file:
            update_frontmatter_field(phase_file, "status", fm_status)
            if phase_file not in changed_files:
                changed_files.append(phase_file)

    if not changed_files:
        raise HTTPException(status_code=404, detail=f"No source files found for feature '{target_feature_id}'")

    await _sync_changed_feature_files(
        request,
        active_project.id,
        changed_files,
        sessions_dir,
        docs_dir,
        progress_dir,
    )
    return await get_feature(target_feature_id)


@features_router.patch("/{feature_id}/phases/{phase_id}/status", response_model=Feature)
async def update_phase_status(feature_id: str, phase_id: str, req: StatusUpdateRequest, request: Request):
    """Update a specific phase's status."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    db = await connection.get_connection()
    repo = get_feature_repository(db)
    target_feature_id = await _resolve_feature_alias_id(repo, active_project.id, feature_id)

    file_path = resolve_file_for_phase(target_feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{target_feature_id}', phase '{phase_id}'",
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
    return await get_feature(target_feature_id)


@features_router.patch("/{feature_id}/phases/{phase_id}/tasks/{task_id}/status", response_model=Feature)
async def update_task_status(feature_id: str, phase_id: str, task_id: str, req: StatusUpdateRequest, request: Request):
    """Update a single task's status."""
    active_project = project_manager.get_active_project()
    if not active_project:
        raise HTTPException(status_code=400, detail="No active project")

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    db = await connection.get_connection()
    repo = get_feature_repository(db)
    target_feature_id = await _resolve_feature_alias_id(repo, active_project.id, feature_id)

    file_path = resolve_file_for_phase(target_feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{target_feature_id}', phase '{phase_id}'",
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
    return await get_feature(target_feature_id)
