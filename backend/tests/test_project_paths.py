import tempfile
import types
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend import config
from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.models import GitHubIntegrationSettingsUpdateRequest
from backend.routers import projects as projects_router
from backend.services.project_paths.providers.github import GitHubProjectPathProvider
from backend.services.project_paths.resolver import ProjectPathResolver
from backend.services.project_paths.models import ResolvedProjectPath, ResolvedProjectPaths


class _StubWorkspaceManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def ensure_workspace(self, repo_ref, settings, *, refresh=False):
        _ = repo_ref, settings, refresh
        return self.workspace_root


class ProjectPathResolverTests(unittest.TestCase):
    def test_resolve_local_project_paths(self) -> None:
        project = Project.model_validate(
            {
                "id": "project-1",
                "name": "Project 1",
                "path": "/tmp/project-1",
                "pathConfig": {
                    "root": {
                        "field": "root",
                        "sourceKind": "filesystem",
                        "filesystemPath": "/tmp/project-1",
                    },
                    "planDocs": {
                        "field": "plan_docs",
                        "sourceKind": "project_root",
                        "relativePath": "plans",
                    },
                    "sessions": {
                        "field": "sessions",
                        "sourceKind": "filesystem",
                        "filesystemPath": "/tmp/sessions",
                    },
                    "progress": {
                        "field": "progress",
                        "sourceKind": "project_root",
                        "relativePath": ".claude/progress",
                    },
                },
            }
        )

        resolved = ProjectPathResolver().resolve_project(project)

        self.assertEqual(resolved.root.path, Path("/tmp/project-1").resolve(strict=False))
        self.assertEqual(resolved.plan_docs.path, (Path("/tmp/project-1") / "plans").resolve(strict=False))
        self.assertEqual(resolved.sessions.path, Path("/tmp/sessions").resolve(strict=False))
        self.assertEqual(resolved.progress.path, (Path("/tmp/project-1") / ".claude/progress").resolve(strict=False))

    def test_resolve_github_root_uses_workspace_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace"
            (workspace_root / "plans").mkdir(parents=True)
            store = GitHubSettingsStore(Path(tmpdir) / "integrations.json")
            store.save(
                GitHubIntegrationSettingsUpdateRequest(
                    enabled=True,
                    baseUrl="https://github.com",
                    username="git",
                    token="secret-token",
                    cacheRoot=str(Path(tmpdir) / "cache"),
                    writeEnabled=True,
                )
            )

            provider = GitHubProjectPathProvider(
                _StubWorkspaceManager(workspace_root),
                store,
            )
            resolver = ProjectPathResolver(github_provider=provider)
            project = Project.model_validate(
                {
                    "id": "project-1",
                    "name": "Project 1",
                    "path": "/tmp/project-1",
                    "pathConfig": {
                        "root": {
                            "field": "root",
                            "sourceKind": "github_repo",
                            "repoRef": {
                                "provider": "github",
                                "repoUrl": "https://github.com/acme/repo",
                                "repoSlug": "acme/repo",
                                "branch": "main",
                                "repoSubpath": "",
                                "writeEnabled": True,
                            },
                        },
                        "planDocs": {
                            "field": "plan_docs",
                            "sourceKind": "project_root",
                            "relativePath": "plans",
                        },
                        "sessions": {
                            "field": "sessions",
                            "sourceKind": "filesystem",
                            "filesystemPath": "/tmp/sessions",
                        },
                        "progress": {
                            "field": "progress",
                            "sourceKind": "project_root",
                            "relativePath": ".claude/progress",
                        },
                    },
                }
            )

            resolved = resolver.resolve_project(project)

            self.assertEqual(resolved.root.path, workspace_root.resolve(strict=False))
            self.assertEqual(resolved.plan_docs.path, (workspace_root / "plans").resolve(strict=False))

    def test_default_project_manager_preserves_example_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            sessions_dir, docs_dir, progress_dir = manager.get_active_paths()

        self.assertEqual(sessions_dir, config.SESSIONS_DIR.resolve(strict=False))
        self.assertEqual(docs_dir, config.DOCUMENTS_DIR.resolve(strict=False))
        self.assertEqual(progress_dir, config.PROGRESS_DIR.resolve(strict=False))

    def test_projects_router_uses_workspace_registry_for_active_paths(self) -> None:
        project = Project.model_validate(
            {
                "id": "project-1",
                "name": "Project 1",
                "path": "/tmp/project-1",
            }
        )
        bundle = ResolvedProjectPaths(
            project_id=project.id,
            root=ResolvedProjectPath(
                field="root",
                source_kind="filesystem",
                requested=project.pathConfig.root,
                path=Path("/tmp/project-1"),
            ),
            plan_docs=ResolvedProjectPath(
                field="plan_docs",
                source_kind="filesystem",
                requested=project.pathConfig.planDocs,
                path=Path("/tmp/project-1/docs"),
            ),
            sessions=ResolvedProjectPath(
                field="sessions",
                source_kind="filesystem",
                requested=project.pathConfig.sessions,
                path=Path("/tmp/sessions"),
            ),
            progress=ResolvedProjectPath(
                field="progress",
                source_kind="filesystem",
                requested=project.pathConfig.progress,
                path=Path("/tmp/project-1/.claude/progress"),
            ),
        )
        registry = types.SimpleNamespace(
            get_active_project=lambda: project,
            get_project=lambda project_id: project if project_id == project.id else None,
            resolve_project_paths=lambda current_project: bundle,
        )
        core_ports = types.SimpleNamespace(workspace_registry=registry)

        payload = projects_router.get_active_project_paths(core_ports)

        self.assertEqual(payload.projectId, "project-1")
        self.assertEqual(payload.planDocs.path, "/tmp/project-1/docs")

    def test_projects_router_uses_hosted_request_project_for_active_paths(self) -> None:
        active_project = Project.model_validate({"id": "project-1", "name": "Project 1", "path": "/tmp/project-1"})
        hosted_project = Project.model_validate({"id": "project-2", "name": "Project 2", "path": "/tmp/project-2"})
        bundles = {
            "project-1": ResolvedProjectPaths(
                project_id=active_project.id,
                root=ResolvedProjectPath(
                    field="root",
                    source_kind="filesystem",
                    requested=active_project.pathConfig.root,
                    path=Path("/tmp/project-1"),
                ),
                plan_docs=ResolvedProjectPath(
                    field="plan_docs",
                    source_kind="filesystem",
                    requested=active_project.pathConfig.planDocs,
                    path=Path("/tmp/project-1/docs"),
                ),
                sessions=ResolvedProjectPath(
                    field="sessions",
                    source_kind="filesystem",
                    requested=active_project.pathConfig.sessions,
                    path=Path("/tmp/sessions-1"),
                ),
                progress=ResolvedProjectPath(
                    field="progress",
                    source_kind="filesystem",
                    requested=active_project.pathConfig.progress,
                    path=Path("/tmp/project-1/.claude/progress"),
                ),
            ),
            "project-2": ResolvedProjectPaths(
                project_id=hosted_project.id,
                root=ResolvedProjectPath(
                    field="root",
                    source_kind="filesystem",
                    requested=hosted_project.pathConfig.root,
                    path=Path("/tmp/project-2"),
                ),
                plan_docs=ResolvedProjectPath(
                    field="plan_docs",
                    source_kind="filesystem",
                    requested=hosted_project.pathConfig.planDocs,
                    path=Path("/tmp/project-2/docs"),
                ),
                sessions=ResolvedProjectPath(
                    field="sessions",
                    source_kind="filesystem",
                    requested=hosted_project.pathConfig.sessions,
                    path=Path("/tmp/sessions-2"),
                ),
                progress=ResolvedProjectPath(
                    field="progress",
                    source_kind="filesystem",
                    requested=hosted_project.pathConfig.progress,
                    path=Path("/tmp/project-2/.claude/progress"),
                ),
            ),
        }
        projects = {active_project.id: active_project, hosted_project.id: hosted_project}
        registry = types.SimpleNamespace(
            get_active_project=lambda: active_project,
            get_project=lambda project_id: projects.get(project_id),
            resolve_project_paths=lambda current_project: bundles[current_project.id],
        )
        core_ports = types.SimpleNamespace(workspace_registry=registry)
        request_context = RequestContext(
            principal=Principal(
                subject="oidc:user-1",
                display_name="User One",
                auth_mode="oidc",
                provider=AuthProviderMetadata(provider_id="oidc", issuer="issuer", hosted=True),
            ),
            workspace=None,
            project=ProjectScope(
                project_id="project-2",
                project_name="Project 2",
                root_path=Path("/tmp/project-2"),
                sessions_dir=Path("/tmp/sessions-2"),
                docs_dir=Path("/tmp/project-2/docs"),
                progress_dir=Path("/tmp/project-2/.claude/progress"),
            ),
            runtime_profile="api",
            trace=TraceContext(request_id="req-hosted-project"),
        )

        payload = projects_router.get_active_project_paths(core_ports, request_context)

        self.assertEqual(payload.projectId, "project-2")
        self.assertEqual(payload.planDocs.path, "/tmp/project-2/docs")

    def test_projects_router_rejects_hosted_active_project_mutation(self) -> None:
        project = Project.model_validate({"id": "project-1", "name": "Project 1", "path": "/tmp/project-1"})
        switched: list[str] = []
        registry = types.SimpleNamespace(
            get_project=lambda project_id: project if project_id == project.id else None,
            set_active_project=lambda project_id: switched.append(project_id),
        )
        core_ports = types.SimpleNamespace(workspace_registry=registry)
        request_context = RequestContext(
            principal=Principal(
                subject="oidc:user-1",
                display_name="User One",
                auth_mode="oidc",
                provider=AuthProviderMetadata(provider_id="oidc", issuer="issuer", hosted=True),
            ),
            workspace=None,
            project=None,
            runtime_profile="api",
            trace=TraceContext(request_id="req-hosted-switch"),
        )

        with self.assertRaises(HTTPException) as ctx:
            projects_router.set_active_project("project-1", core_ports, request_context)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(switched, [])

    def test_projects_router_lists_projects_from_workspace_registry(self) -> None:
        project = Project.model_validate({"id": "project-1", "name": "Project 1", "path": "/tmp/project-1"})
        registry = types.SimpleNamespace(list_projects=lambda: [project])
        core_ports = types.SimpleNamespace(workspace_registry=registry)

        payload = projects_router.list_projects(core_ports)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].id, "project-1")


if __name__ == "__main__":
    unittest.main()
