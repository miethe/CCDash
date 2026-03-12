from __future__ import annotations

from pathlib import Path

from backend.models import Project, ProjectPathReference
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.project_paths.models import ResolvedProjectPath
from backend.services.project_paths.providers.base import PathResolutionError
from backend.services.repo_workspaces.manager import RepoWorkspaceError, RepoWorkspaceManager


class GitHubProjectPathProvider:
    def __init__(
        self,
        workspace_manager: RepoWorkspaceManager,
        settings_store: GitHubSettingsStore,
    ):
        self.workspace_manager = workspace_manager
        self.settings_store = settings_store

    def resolve(
        self,
        reference: ProjectPathReference,
        *,
        project: Project,
        refresh: bool = False,
    ) -> ResolvedProjectPath:
        repo_ref = reference.repoRef
        if repo_ref is None:
            raise PathResolutionError("invalid_github_url", f"Field '{reference.field}' is missing repoRef.")

        settings = self.settings_store.load()
        try:
            workspace_root = self.workspace_manager.ensure_workspace(repo_ref, settings, refresh=refresh)
        except RepoWorkspaceError as exc:
            raise PathResolutionError(exc.code, exc.detail) from exc

        repo_subpath = str(repo_ref.repoSubpath or "").strip().strip("/")
        candidate = (workspace_root / repo_subpath).resolve(strict=False) if repo_subpath else workspace_root.resolve(strict=False)
        if repo_subpath and not candidate.exists():
            raise PathResolutionError(
                "missing_subpath",
                f"Subpath '{repo_subpath}' was not found in the GitHub workspace for project '{project.id}'.",
            )

        return ResolvedProjectPath(
            field=reference.field,
            source_kind=reference.sourceKind,
            requested=reference,
            path=candidate,
            diagnostic="Resolved from managed GitHub workspace.",
        )
