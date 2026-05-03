"""API router for project management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.models import Project, ProjectResolvedPathDTO, ProjectResolvedPathsDTO
from backend.request_scope import get_core_ports
from backend.runtime.dependencies import get_request_context

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])


@projects_router.get("", response_model=list[Project])
def list_projects(core_ports: CorePorts = Depends(get_core_ports)):
    """List all available projects."""
    return core_ports.workspace_registry.list_projects()


def _to_resolved_dto(core_ports: CorePorts, project_id: str) -> ProjectResolvedPathsDTO:
    project = core_ports.workspace_registry.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    bundle = core_ports.workspace_registry.resolve_project_paths(project)
    return ProjectResolvedPathsDTO(
        projectId=project_id,
        root=ProjectResolvedPathDTO(
            field="root",
            sourceKind=bundle.root.source_kind,
            path=str(bundle.root.path),
            diagnostic=bundle.root.diagnostic,
        ),
        planDocs=ProjectResolvedPathDTO(
            field="plan_docs",
            sourceKind=bundle.plan_docs.source_kind,
            path=str(bundle.plan_docs.path),
            diagnostic=bundle.plan_docs.diagnostic,
        ),
        sessions=ProjectResolvedPathDTO(
            field="sessions",
            sourceKind=bundle.sessions.source_kind,
            path=str(bundle.sessions.path),
            diagnostic=bundle.sessions.diagnostic,
        ),
        progress=ProjectResolvedPathDTO(
            field="progress",
            sourceKind=bundle.progress.source_kind,
            path=str(bundle.progress.path),
            diagnostic=bundle.progress.diagnostic,
        ),
    )


@projects_router.post("", response_model=Project)
def add_project(project: Project, core_ports: CorePorts = Depends(get_core_ports)):
    """Add a new project."""
    try:
        core_ports.workspace_registry.add_project(project)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@projects_router.put("/{project_id}", response_model=Project)
def update_project(project_id: str, project: Project, core_ports: CorePorts = Depends(get_core_ports)):
    """Update an existing project."""
    try:
        core_ports.workspace_registry.update_project(project_id, project)
        updated = core_ports.workspace_registry.get_project(project_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found after update")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@projects_router.get("/active", response_model=Project)
def get_active_project(
    core_ports: CorePorts = Depends(get_core_ports),
    request_context: RequestContext | None = Depends(get_request_context),
):
    """Get the currently active project."""
    if _request_uses_hosted_project_selection(request_context):
        if request_context is None or request_context.project is None:
            raise HTTPException(status_code=404, detail="No project selected for hosted request")
        project = core_ports.workspace_registry.get_project(request_context.project.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Selected project not found")
        return project

    project = core_ports.workspace_registry.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project found")
    return project


@projects_router.get("/active/paths", response_model=ProjectResolvedPathsDTO)
def get_active_project_paths(
    core_ports: CorePorts = Depends(get_core_ports),
    request_context: RequestContext | None = Depends(get_request_context),
):
    """Return resolved local paths for the active project."""
    if _request_uses_hosted_project_selection(request_context):
        if request_context is None or request_context.project is None:
            raise HTTPException(status_code=404, detail="No project selected for hosted request")
        try:
            return _to_resolved_dto(core_ports, request_context.project.project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    project = core_ports.workspace_registry.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project found")
    try:
        return _to_resolved_dto(core_ports, project.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@projects_router.post("/active/{project_id}", response_model=Project)
def set_active_project(
    project_id: str,
    core_ports: CorePorts = Depends(get_core_ports),
    request_context: RequestContext | None = Depends(get_request_context),
):
    """Switch the active project."""
    if _request_uses_hosted_project_selection(request_context):
        if not core_ports.workspace_registry.get_project(project_id):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        raise HTTPException(
            status_code=409,
            detail=(
                "Hosted requests must select projects explicitly per request; "
                "the process-global active project is local-only."
            ),
        )

    try:
        core_ports.workspace_registry.set_active_project(project_id)
        project = core_ports.workspace_registry.get_active_project()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found after switch")
        return project
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@projects_router.get("/{project_id}/paths", response_model=ProjectResolvedPathsDTO)
def get_project_paths(project_id: str, core_ports: CorePorts = Depends(get_core_ports)):
    """Return resolved local paths for a project."""
    try:
        return _to_resolved_dto(core_ports, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _request_uses_hosted_project_selection(request_context: object) -> bool:
    principal = getattr(request_context, "principal", None)
    provider = getattr(principal, "provider", None)
    return bool(getattr(provider, "hosted", False))
