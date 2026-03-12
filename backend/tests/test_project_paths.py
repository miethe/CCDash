import tempfile
import unittest
from pathlib import Path

from backend import config
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.models import GitHubIntegrationSettingsUpdateRequest
from backend.services.project_paths.providers.github import GitHubProjectPathProvider
from backend.services.project_paths.resolver import ProjectPathResolver


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


if __name__ == "__main__":
    unittest.main()
