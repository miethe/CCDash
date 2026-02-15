"""API router for project management."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from backend.models import Project
from backend.project_manager import project_manager

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])


@projects_router.get("", response_model=list[Project])
def list_projects():
    """List all available projects."""
    return project_manager.list_projects()


@projects_router.post("", response_model=Project)
def add_project(project: Project):
    """Add a new project."""
    try:
        project_manager.add_project(project)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@projects_router.put("/{project_id}", response_model=Project)
def update_project(project_id: str, project: Project):
    """Update an existing project."""
    try:
        project_manager.update_project(project_id, project)
        updated = project_manager.get_project(project_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found after update")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@projects_router.get("/active", response_model=Project)
def get_active_project():
    """Get the currently active project."""
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project found")
    return project


@projects_router.post("/active/{project_id}", response_model=Project)
def set_active_project(project_id: str):
    """Switch the active project."""
    try:
        project_manager.set_active_project(project_id)
        project = project_manager.get_active_project()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found after switch")
        return project
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
