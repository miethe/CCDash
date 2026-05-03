"""Workspace registry backed by the existing project manager."""
from __future__ import annotations

from backend.application.context import ProjectScope, WorkspaceScope
from backend.application.ports.core import ProjectBinding
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.services.project_paths.models import ResolvedProjectPaths


class ProjectManagerWorkspaceRegistry:
    def __init__(self, manager: ProjectManager):
        self._manager = manager

    def list_projects(self) -> list[Project]:
        return self._manager.list_projects()

    def get_project(self, project_id: str) -> Project | None:
        return self._manager.get_project(project_id)

    def add_project(self, project: Project) -> None:
        self._manager.add_project(project)

    def update_project(self, project_id: str, project: Project) -> None:
        self._manager.update_project(project_id, project)

    def set_active_project(self, project_id: str) -> None:
        self._manager.set_active_project(project_id)

    def get_active_project(self) -> Project | None:
        return self._manager.get_active_project()

    def resolve_project_paths(self, project: Project, *, refresh: bool = False) -> ResolvedProjectPaths:
        return self._manager.resolve_project_paths(project, refresh=refresh)

    def get_active_path_bundle(self, *, refresh: bool = False) -> ResolvedProjectPaths:
        return self._manager.get_active_path_bundle(refresh=refresh)

    def resolve_project_binding(
        self,
        project_id: str | None = None,
        *,
        allow_active_fallback: bool = True,
        refresh: bool = False,
    ) -> ProjectBinding | None:
        return self._manager.resolve_project_binding(
            project_id,
            allow_active_fallback=allow_active_fallback,
            refresh=refresh,
        )

    def resolve_scope(
        self,
        project_id: str | None = None,
        *,
        allow_active_fallback: bool = True,
    ) -> tuple[WorkspaceScope | None, ProjectScope | None]:
        requested_project_id = str(project_id or "").strip() or None
        if requested_project_id is not None:
            project = self._manager.get_project(requested_project_id)
        elif allow_active_fallback:
            project = self._manager.get_active_project()
        else:
            project = None
        if project is None:
            return None, None

        bundle = self._manager.resolve_project_paths(project)
        workspace = WorkspaceScope(
            workspace_id=project.id,
            root_path=bundle.root.path,
        )
        project_scope = ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=bundle.root.path,
            sessions_dir=bundle.sessions.path,
            docs_dir=bundle.plan_docs.path,
            progress_dir=bundle.progress.path,
        )
        return workspace, project_scope
