"""Codebase explorer API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import connection
from backend.project_manager import project_manager
from backend.services.codebase_explorer import CodebaseExplorerService


codebase_router = APIRouter(prefix="/api/codebase", tags=["codebase"])


def _get_active_project():
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    return project


@codebase_router.get("/tree")
async def get_codebase_tree(
    prefix: str = Query("", description="Optional relative path prefix"),
    depth: int = Query(4, ge=1, le=32),
    include_untouched: bool = Query(False),
    search: str = Query("", description="Substring filter for names and paths"),
):
    project = _get_active_project()
    db = await connection.get_connection()
    service = CodebaseExplorerService(db, project)
    try:
        return await service.get_tree(
            prefix=prefix,
            depth=depth,
            include_untouched=include_untouched,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@codebase_router.get("/files")
async def get_codebase_files(
    prefix: str = Query("", description="Optional relative path prefix"),
    search: str = Query("", description="Substring filter for names and paths"),
    include_untouched: bool = Query(False),
    action: str = Query("", description="Filter by action: read/create/update/delete"),
    feature_id: str = Query("", description="Filter to files linked to a feature"),
    sort_by: str = Query("last_touched", description="Sort key"),
    sort_order: str = Query("desc", description="Sort order asc|desc"),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
):
    project = _get_active_project()
    db = await connection.get_connection()
    service = CodebaseExplorerService(db, project)
    try:
        return await service.list_files(
            prefix=prefix,
            search=search,
            include_untouched=include_untouched,
            action=action,
            feature_id=feature_id,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@codebase_router.get("/files/{file_path:path}")
async def get_codebase_file_detail(
    file_path: str,
    activity_limit: int = Query(100, ge=1, le=500),
):
    project = _get_active_project()
    db = await connection.get_connection()
    service = CodebaseExplorerService(db, project)
    try:
        return await service.get_file_detail(file_path=file_path, activity_limit=activity_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

