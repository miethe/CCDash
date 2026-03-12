from __future__ import annotations

from pathlib import Path

from backend import config
from backend.models import Project, ProjectPathReference
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.project_paths.models import ResolvedProjectPath, ResolvedProjectPaths
from backend.services.project_paths.providers.base import PathResolutionError
from backend.services.project_paths.providers.filesystem import FilesystemProjectPathProvider
from backend.services.project_paths.providers.github import GitHubProjectPathProvider
from backend.services.repo_workspaces.cache import RepoWorkspaceCache
from backend.services.repo_workspaces.manager import RepoWorkspaceManager


def _normalize_relative_path(raw: str) -> str:
    text = str(raw or "").replace("\\", "/").strip().strip("/")
    if not text:
        return ""
    parts: list[str] = []
    for token in text.split("/"):
        clean = token.strip()
        if not clean or clean == ".":
            continue
        if clean == "..":
            raise PathResolutionError("invalid_relative_path", "Relative paths cannot escape the resolved project root.")
        parts.append(clean)
    return "/".join(parts)


class ProjectPathResolver:
    def __init__(
        self,
        *,
        filesystem_provider: FilesystemProjectPathProvider | None = None,
        github_provider: GitHubProjectPathProvider | None = None,
    ):
        settings_store = GitHubSettingsStore()
        workspace_cache = RepoWorkspaceCache(config.REPO_WORKSPACE_CACHE_DIR)
        self.filesystem_provider = filesystem_provider or FilesystemProjectPathProvider()
        self.github_provider = github_provider or GitHubProjectPathProvider(
            RepoWorkspaceManager(workspace_cache),
            settings_store,
        )

    def resolve_project(self, project: Project, *, refresh: bool = False) -> ResolvedProjectPaths:
        root = self.resolve_reference(project, project.pathConfig.root, refresh=refresh)
        plan_docs = self.resolve_reference(project, project.pathConfig.planDocs, root=root, refresh=refresh)
        sessions = self.resolve_reference(project, project.pathConfig.sessions, root=root, refresh=refresh)
        progress = self.resolve_reference(project, project.pathConfig.progress, root=root, refresh=refresh)
        return ResolvedProjectPaths(
            project_id=project.id,
            root=root,
            plan_docs=plan_docs,
            sessions=sessions,
            progress=progress,
        )

    def resolve_reference(
        self,
        project: Project,
        reference: ProjectPathReference,
        *,
        root: ResolvedProjectPath | None = None,
        refresh: bool = False,
    ) -> ResolvedProjectPath:
        if reference.sourceKind == "project_root":
            if root is None:
                raise PathResolutionError("missing_root", f"Field '{reference.field}' needs a resolved project root.")
            relative_path = _normalize_relative_path(reference.relativePath)
            candidate = (root.path / relative_path).resolve(strict=False)
            try:
                candidate.relative_to(root.path.resolve(strict=False))
            except ValueError as exc:
                raise PathResolutionError("invalid_relative_path", "Resolved path escapes the project root.") from exc
            return ResolvedProjectPath(
                field=reference.field,
                source_kind=reference.sourceKind,
                requested=reference,
                path=candidate,
                diagnostic="Resolved relative to the project root.",
            )
        if reference.sourceKind == "filesystem":
            return self.filesystem_provider.resolve(reference, project=project, refresh=refresh)
        if reference.sourceKind == "github_repo":
            return self.github_provider.resolve(reference, project=project, refresh=refresh)
        raise PathResolutionError("unsupported_source_kind", f"Unsupported source kind '{reference.sourceKind}'.")
