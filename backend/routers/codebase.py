"""Codebase explorer API router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project_bundle
from backend.db import connection
from backend.request_scope import get_core_ports, get_request_context, require_http_authorization
from backend.services.codebase_explorer import CodebaseExplorerService


codebase_router = APIRouter(prefix="/api/codebase", tags=["codebase"])


async def _codebase_service(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    action: str,
) -> CodebaseExplorerService:
    bundle = require_project_bundle(request_context, core_ports)
    await require_http_authorization(
        request_context,
        core_ports,
        action=action,
        resource=f"project:{bundle.project.id}",
    )
    db = await connection.get_connection()
    return CodebaseExplorerService(db, bundle.project, project_root=bundle.paths.root.path)


@codebase_router.get("/tree")
async def get_codebase_tree(
    prefix: str = Query("", description="Optional relative path prefix"),
    depth: int = Query(4, ge=1, le=32),
    include_untouched: bool = Query(False),
    search: str = Query("", description="Substring filter for names and paths"),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    service = await _codebase_service(request_context, core_ports, action="codebase:read_tree")
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    service = await _codebase_service(request_context, core_ports, action="codebase:activity_read")
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


@codebase_router.get("/file-content")
async def get_codebase_file_content(
    path: str = Query("", description="Project-relative or absolute filesystem file path"),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    service = await _codebase_service(request_context, core_ports, action="codebase:file_read")
    try:
        return await service.get_file_content(file_path=path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@codebase_router.get("/files/{file_path:path}")
async def get_codebase_file_detail(
    file_path: str,
    activity_limit: int = Query(100, ge=1, le=500),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    service = await _codebase_service(request_context, core_ports, action="codebase:activity_read")
    try:
        return await service.get_file_detail(file_path=file_path, activity_limit=activity_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
