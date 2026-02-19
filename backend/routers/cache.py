"""Cache + sync observability API."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.db.file_watcher import file_watcher
from backend.project_manager import project_manager

logger = logging.getLogger("ccdash.cache")

cache_router = APIRouter(prefix="/api/cache", tags=["cache"])
links_router = APIRouter(prefix="/api/links", tags=["links"])


class SyncRequest(BaseModel):
    force: bool = True
    background: bool = True
    trigger: str = "api"


class RebuildLinksRequest(BaseModel):
    background: bool = True
    captureAnalytics: bool = False
    trigger: str = "api"


class ChangedPathSpec(BaseModel):
    path: str = Field(..., min_length=1)
    changeType: Literal["modified", "added", "deleted"] = "modified"


class SyncPathsRequest(BaseModel):
    paths: list[ChangedPathSpec]
    background: bool = False
    trigger: str = "api"


def _get_sync_engine(request: Request):
    sync_engine = getattr(request.app.state, "sync_engine", None)
    if not sync_engine:
        raise HTTPException(status_code=503, detail="Sync engine not initialized")
    return sync_engine


def _get_active_project_context() -> tuple[Any, Path, Path, Path]:
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    return project, sessions_dir, docs_dir, progress_dir


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _resolve_changed_path(raw_path: str, project_root: Path, sessions_dir: Path, docs_dir: Path, progress_dir: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)

    allowed_roots = [project_root.resolve(strict=False), sessions_dir.resolve(strict=False), docs_dir.resolve(strict=False), progress_dir.resolve(strict=False)]
    if not any(_is_under(candidate, root) for root in allowed_roots):
        raise HTTPException(
            status_code=400,
            detail=f"Path outside allowed project roots: {raw_path}",
        )
    return candidate


@cache_router.get("/status")
async def get_cache_status(request: Request):
    """Return sync engine + watcher status, including live operations."""
    sync_engine = _get_sync_engine(request)
    project = project_manager.get_active_project()
    sessions_dir = docs_dir = progress_dir = None
    if project:
        sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    observability = await sync_engine.get_observability_snapshot()
    return {
        "status": "active",
        "sync_engine": "ready",
        "watcher": "running" if file_watcher.is_running else "stopped",
        "projectId": getattr(project, "id", ""),
        "projectName": getattr(project, "name", ""),
        "activePaths": {
            "sessionsDir": str(sessions_dir) if sessions_dir else "",
            "docsDir": str(docs_dir) if docs_dir else "",
            "progressDir": str(progress_dir) if progress_dir else "",
        },
        "operations": observability,
    }


@cache_router.get("/operations")
async def list_cache_operations(request: Request, limit: int = Query(20, ge=1, le=200)):
    """List recent sync/rebuild operations."""
    sync_engine = _get_sync_engine(request)
    operations = await sync_engine.list_operations(limit=limit)
    return {"status": "ok", "count": len(operations), "items": operations}


@cache_router.get("/operations/{operation_id}")
async def get_cache_operation(request: Request, operation_id: str):
    """Get one sync/rebuild operation by ID."""
    sync_engine = _get_sync_engine(request)
    operation = await sync_engine.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
    return operation


@cache_router.post("/sync")
async def trigger_sync(request: Request, background_tasks: BackgroundTasks, body: SyncRequest):
    """Trigger full project sync with operation tracking."""
    sync_engine = _get_sync_engine(request)
    project, sessions_dir, docs_dir, progress_dir = _get_active_project_context()

    if body.background:
        operation_id = await sync_engine.start_operation(
            "full_sync",
            project.id,
            trigger=body.trigger,
            metadata={"force": bool(body.force)},
        )
        background_tasks.add_task(
            sync_engine.sync_project,
            project,
            sessions_dir,
            docs_dir,
            progress_dir,
            body.force,
            operation_id,
            body.trigger,
        )
        return {
            "status": "ok",
            "mode": "background",
            "message": "Sync triggered in background",
            "operationId": operation_id,
        }

    stats = await sync_engine.sync_project(
        project,
        sessions_dir,
        docs_dir,
        progress_dir,
        body.force,
        None,
        body.trigger,
    )
    operation_id = str(stats.get("operation_id") or "")
    operation = await sync_engine.get_operation(operation_id) if operation_id else None
    return {
        "status": "ok",
        "mode": "foreground",
        "operationId": operation_id,
        "stats": stats,
        "operation": operation,
    }


@cache_router.post("/rescan")
async def trigger_rescan(request: Request, background_tasks: BackgroundTasks):
    """Backward-compatible alias for full force sync in background."""
    return await trigger_sync(
        request,
        background_tasks,
        SyncRequest(force=True, background=True, trigger="api"),
    )


@cache_router.post("/rebuild-links")
async def trigger_rebuild_links(
    request: Request,
    background_tasks: BackgroundTasks,
    body: RebuildLinksRequest,
):
    """Trigger entity-link rebuild with operation tracking."""
    sync_engine = _get_sync_engine(request)
    project, _, docs_dir, progress_dir = _get_active_project_context()

    if body.background:
        operation_id = await sync_engine.start_operation(
            "rebuild_links",
            project.id,
            trigger=body.trigger,
            metadata={"captureAnalytics": bool(body.captureAnalytics)},
        )
        background_tasks.add_task(
            sync_engine.rebuild_links,
            project.id,
            docs_dir,
            progress_dir,
            operation_id=operation_id,
            trigger=body.trigger,
            capture_analytics=body.captureAnalytics,
        )
        return {
            "status": "ok",
            "mode": "background",
            "message": "Link rebuild triggered in background",
            "operationId": operation_id,
        }

    stats = await sync_engine.rebuild_links(
        project.id,
        docs_dir,
        progress_dir,
        operation_id=None,
        trigger=body.trigger,
        capture_analytics=body.captureAnalytics,
    )
    operation_id = str(stats.get("operation_id") or "")
    operation = await sync_engine.get_operation(operation_id) if operation_id else None
    return {
        "status": "ok",
        "mode": "foreground",
        "operationId": operation_id,
        "stats": stats,
        "operation": operation,
    }


@cache_router.post("/sync-paths")
async def trigger_sync_paths(
    request: Request,
    background_tasks: BackgroundTasks,
    body: SyncPathsRequest,
):
    """Sync a targeted set of changed files (supports project-relative paths)."""
    if not body.paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    sync_engine = _get_sync_engine(request)
    project, sessions_dir, docs_dir, progress_dir = _get_active_project_context()
    project_root = Path(project.path).resolve(strict=False)
    changed_files: list[tuple[str, Path]] = []
    for item in body.paths:
        resolved = _resolve_changed_path(item.path, project_root, sessions_dir, docs_dir, progress_dir)
        changed_files.append((item.changeType, resolved))

    if body.background:
        operation_id = await sync_engine.start_operation(
            "sync_changed_files",
            project.id,
            trigger=body.trigger,
            metadata={"changedCount": len(changed_files)},
        )
        background_tasks.add_task(
            sync_engine.sync_changed_files,
            project.id,
            changed_files,
            sessions_dir,
            docs_dir,
            progress_dir,
            operation_id,
            body.trigger,
        )
        return {
            "status": "ok",
            "mode": "background",
            "message": "Changed-path sync triggered in background",
            "operationId": operation_id,
        }

    stats = await sync_engine.sync_changed_files(
        project.id,
        changed_files,
        sessions_dir,
        docs_dir,
        progress_dir,
        None,
        body.trigger,
    )
    return {"status": "ok", "mode": "foreground", "stats": stats}


@cache_router.get("/links/audit")
@links_router.get("/audit")
async def get_links_audit(
    request: Request,
    feature_id: str = Query("", description="Optional feature id filter"),
    primary_floor: float = Query(0.55, ge=0.0, le=1.0),
    fanout_floor: int = Query(10, ge=1, le=1000),
    limit: int = Query(50, ge=1, le=500),
):
    """Run link-audit heuristics against feature->session links for active project."""
    sync_engine = _get_sync_engine(request)
    project, _, _, _ = _get_active_project_context()
    payload = await sync_engine.run_link_audit(
        project.id,
        feature_id=feature_id,
        primary_floor=primary_floor,
        fanout_floor=fanout_floor,
        limit=limit,
    )
    payload["status"] = "ok"
    return payload
