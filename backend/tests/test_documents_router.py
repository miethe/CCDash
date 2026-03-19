import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi import HTTPException

from backend.db.sqlite_migrations import run_migrations
from backend.models import GitHubIntegrationSettings, Project
from backend.routers import api as api_router
from backend.services.project_paths.models import ResolvedProjectPath, ResolvedProjectPaths


def _make_request(sync_engine: AsyncMock):
    return types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace(sync_engine=sync_engine)))


class DocumentRouterWriteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name) / "workspace"
        self.docs_dir = self.project_root / "docs" / "project_plans"
        self.progress_dir = self.project_root / ".claude" / "progress"
        self.sessions_dir = Path(self.tmpdir.name) / "sessions"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.plan_file = self.docs_dir / "plan.md"
        self.plan_file.write_text("# Initial\n", encoding="utf-8")

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await self._seed_document()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmpdir.cleanup()

    async def _seed_document(self) -> None:
        await self.db.execute(
            """
            INSERT INTO documents (
                id, project_id, title, file_path, canonical_path, root_kind,
                status, frontmatter_json, metadata_json, content, source_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DOC-plan",
                "project-1",
                "Plan",
                "docs/project_plans/plan.md",
                "docs/project_plans/plan.md",
                "project_plans",
                "active",
                "{}",
                "{}",
                "# Initial\n",
                str(self.plan_file),
            ),
        )
        await self.db.commit()

    def _local_project(self) -> Project:
        return Project.model_validate(
            {
                "id": "project-1",
                "name": "Project 1",
                "path": str(self.project_root),
                "pathConfig": {
                    "root": {
                        "field": "root",
                        "sourceKind": "filesystem",
                        "filesystemPath": str(self.project_root),
                    },
                    "planDocs": {
                        "field": "plan_docs",
                        "sourceKind": "project_root",
                        "relativePath": "docs/project_plans",
                    },
                    "sessions": {
                        "field": "sessions",
                        "sourceKind": "filesystem",
                        "filesystemPath": str(self.sessions_dir),
                    },
                    "progress": {
                        "field": "progress",
                        "sourceKind": "project_root",
                        "relativePath": ".claude/progress",
                    },
                },
            }
        )

    def _github_project(self) -> Project:
        return Project.model_validate(
            {
                "id": "project-1",
                "name": "Project 1",
                "path": str(self.project_root),
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
                        "relativePath": "docs/project_plans",
                    },
                    "sessions": {
                        "field": "sessions",
                        "sourceKind": "filesystem",
                        "filesystemPath": str(self.sessions_dir),
                    },
                    "progress": {
                        "field": "progress",
                        "sourceKind": "project_root",
                        "relativePath": ".claude/progress",
                    },
                },
            }
        )

    def _bundle(self, project: Project) -> ResolvedProjectPaths:
        return ResolvedProjectPaths(
            project_id=project.id,
            root=ResolvedProjectPath(
                field="root",
                source_kind=project.pathConfig.root.sourceKind,
                requested=project.pathConfig.root,
                path=self.project_root,
            ),
            plan_docs=ResolvedProjectPath(
                field="plan_docs",
                source_kind=project.pathConfig.planDocs.sourceKind,
                requested=project.pathConfig.planDocs,
                path=self.docs_dir,
            ),
            sessions=ResolvedProjectPath(
                field="sessions",
                source_kind=project.pathConfig.sessions.sourceKind,
                requested=project.pathConfig.sessions,
                path=self.sessions_dir,
            ),
            progress=ResolvedProjectPath(
                field="progress",
                source_kind=project.pathConfig.progress.sourceKind,
                requested=project.pathConfig.progress,
                path=self.progress_dir,
            ),
        )

    async def test_update_document_writes_local_plan_doc(self) -> None:
        project = self._local_project()
        bundle = self._bundle(project)
        sync_engine = AsyncMock()

        with (
            patch.object(api_router.connection, "get_connection", new=AsyncMock(return_value=self.db)),
            patch.object(api_router.project_manager, "get_active_project", return_value=project),
            patch.object(api_router.project_manager, "get_active_path_bundle", return_value=bundle),
        ):
            response = await api_router.update_document(
                "DOC-plan",
                api_router.DocumentUpdateRequest(content="# Updated\n"),
                _make_request(sync_engine),
            )

        self.assertEqual(self.plan_file.read_text(encoding="utf-8"), "# Updated\n")
        self.assertEqual(response.writeMode, "local")
        self.assertEqual(response.document.content, "# Updated\n")
        sync_engine.sync_changed_files.assert_awaited()

    async def test_update_document_preserves_existing_frontmatter_when_saving_body_only(self) -> None:
        project = self._local_project()
        bundle = self._bundle(project)
        sync_engine = AsyncMock()
        self.plan_file.write_text("---\ntitle: Plan\nstatus: draft\n---\n# Initial\n", encoding="utf-8")
        await self.db.execute(
            """
            UPDATE documents
            SET has_frontmatter = 1,
                frontmatter_type = ?,
                frontmatter_json = ?,
                content = ?
            WHERE id = ?
            """,
            ("yaml", '{"title":"Plan","status":"draft"}', "# Initial\n", "DOC-plan"),
        )
        await self.db.commit()

        with (
            patch.object(api_router.connection, "get_connection", new=AsyncMock(return_value=self.db)),
            patch.object(api_router.project_manager, "get_active_project", return_value=project),
            patch.object(api_router.project_manager, "get_active_path_bundle", return_value=bundle),
        ):
            response = await api_router.update_document(
                "DOC-plan",
                api_router.DocumentUpdateRequest(content="# Updated\n"),
                _make_request(sync_engine),
            )

        self.assertEqual(
            self.plan_file.read_text(encoding="utf-8"),
            "---\ntitle: Plan\nstatus: draft\n---\n# Updated\n",
        )
        self.assertEqual(response.document.content, "# Updated\n")
        sync_engine.sync_changed_files.assert_awaited()

    async def test_update_document_rejects_repo_write_when_github_disabled(self) -> None:
        project = self._github_project()
        bundle = self._bundle(project)
        sync_engine = AsyncMock()

        with (
            patch.object(api_router.connection, "get_connection", new=AsyncMock(return_value=self.db)),
            patch.object(api_router.project_manager, "get_active_project", return_value=project),
            patch.object(api_router.project_manager, "get_active_path_bundle", return_value=bundle),
            patch.object(
                api_router.GitHubSettingsStore,
                "load",
                return_value=GitHubIntegrationSettings(enabled=False, writeEnabled=True, token="secret"),
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                await api_router.update_document(
                    "DOC-plan",
                    api_router.DocumentUpdateRequest(content="# Updated\n"),
                    _make_request(sync_engine),
                )

        self.assertEqual(exc.exception.status_code, 403)
        self.assertIn("disabled", str(exc.exception.detail).lower())

    async def test_update_document_pushes_repo_backed_plan_doc(self) -> None:
        project = self._github_project()
        bundle = self._bundle(project)
        sync_engine = AsyncMock()

        def _write_side_effect(*_args, **kwargs):
            self.plan_file.write_text(kwargs["content"], encoding="utf-8")
            return "abc1234"

        with (
            patch.object(api_router.connection, "get_connection", new=AsyncMock(return_value=self.db)),
            patch.object(api_router.project_manager, "get_active_project", return_value=project),
            patch.object(api_router.project_manager, "get_active_path_bundle", return_value=bundle),
            patch.object(
                api_router.GitHubSettingsStore,
                "load",
                return_value=GitHubIntegrationSettings(enabled=True, writeEnabled=True, token="secret", cacheRoot=str(self.project_root)),
            ),
            patch.object(api_router.RepoWorkspaceManager, "ensure_workspace", return_value=self.project_root),
            patch.object(api_router.RepoWorkspaceManager, "write_file_and_push", side_effect=_write_side_effect) as write_mock,
        ):
            response = await api_router.update_document(
                "DOC-plan",
                api_router.DocumentUpdateRequest(content="# Repo Updated\n", commitMessage="ccdash: update plan"),
                _make_request(sync_engine),
            )

        self.assertEqual(response.writeMode, "github_repo")
        self.assertEqual(response.commitHash, "abc1234")
        self.assertEqual(response.document.content, "# Repo Updated\n")
        self.assertEqual(self.plan_file.read_text(encoding="utf-8"), "# Repo Updated\n")
        write_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
