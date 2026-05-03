import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite
from fastapi import HTTPException

from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    ProjectScope,
    RequestContext,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.ports import AuthorizationDecision
from backend.application.ports.core import ProjectBinding
from backend.db.sqlite_migrations import run_migrations
from backend.routers import codebase as codebase_router
from backend.services.codebase_explorer import clear_codebase_cache


class _AuthorizationPolicy:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[dict] = []

    async def authorize(self, context, *, action: str, resource: str | None = None):
        self.calls.append({"action": action, "resource": resource})
        return AuthorizationDecision(
            allowed=self.allowed,
            code="permission_allowed" if self.allowed else "permission_not_granted",
            reason="test policy",
        )


class _WorkspaceRegistry:
    def __init__(self, project, bundle, *, active_project=None) -> None:
        self.project = project
        self.bundle = bundle
        self.active_project = project if active_project is None else active_project
        self.active_calls = 0

    def get_project(self, project_id: str):
        return self.project if project_id == self.project.id else None

    def get_active_project(self):
        self.active_calls += 1
        return self.active_project

    def resolve_project_paths(self, project, *, refresh: bool = False):
        return self.bundle

    def resolve_project_binding(self, project_id=None, *, allow_active_fallback: bool = True, refresh: bool = False):
        if project_id:
            project = self.get_project(project_id)
            source = "explicit"
        elif allow_active_fallback:
            project = self.get_active_project()
            source = "active"
        else:
            project = None
            source = "none"
        if project is None:
            return None
        return ProjectBinding(project=project, paths=self.bundle, source=source, requested_project_id=project_id)


class CodebaseRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self._create_filesystem_fixture()

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await self._seed_database()
        self.project = types.SimpleNamespace(id="project-1", name="Project One", path=str(self.project_root))
        self.bundle = types.SimpleNamespace(
            root=types.SimpleNamespace(path=self.project_root),
            sessions=types.SimpleNamespace(path=self.project_root / "sessions"),
            plan_docs=types.SimpleNamespace(path=self.project_root / "docs"),
            progress=types.SimpleNamespace(path=self.project_root / "progress"),
        )
        self.registry = _WorkspaceRegistry(self.project, self.bundle)
        self.auth_policy = _AuthorizationPolicy()
        self.core_ports = types.SimpleNamespace(workspace_registry=self.registry, authorization_policy=self.auth_policy)
        self.request_context = self._request_context(project_id="project-1")
        clear_codebase_cache()

    async def asyncTearDown(self) -> None:
        clear_codebase_cache()
        await self.db.close()
        self.tmpdir.cleanup()

    def _create_filesystem_fixture(self) -> None:
        (self.project_root / "src").mkdir(parents=True, exist_ok=True)
        (self.project_root / "docs").mkdir(parents=True, exist_ok=True)
        (self.project_root / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
        (self.project_root / "dist").mkdir(parents=True, exist_ok=True)
        (self.project_root / "ignored-dir").mkdir(parents=True, exist_ok=True)

        (self.project_root / ".gitignore").write_text("*.log\nignored-dir/\n", encoding="utf-8")
        (self.project_root / "src" / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")
        (self.project_root / "src" / "levels.ts").write_text("export const levels = true;\n", encoding="utf-8")
        (self.project_root / "src" / "untouched.ts").write_text("export const untouched = true;\n", encoding="utf-8")
        (self.project_root / "docs" / "plan.md").write_text("# plan\n", encoding="utf-8")
        (self.project_root / "ignored.log").write_text("ignore me\n", encoding="utf-8")
        (self.project_root / "ignored-dir" / "skip.txt").write_text("skip\n", encoding="utf-8")
        (self.project_root / "node_modules" / "pkg" / "index.js").write_text("module.exports={};\n", encoding="utf-8")
        (self.project_root / "dist" / "bundle.js").write_text("console.log('dist');\n", encoding="utf-8")

    async def _seed_database(self) -> None:
        sessions = [
            ("S-main", "session", "", "S-main"),
            ("S-primary", "session", "", "S-primary"),
            ("S-support", "session", "", "S-support"),
            ("S-peripheral", "session", "", "S-peripheral"),
        ]
        for session_id, session_type, parent_id, root_id in sessions:
            await self.db.execute(
                """
                INSERT INTO sessions (
                    id, project_id, status, model, session_type,
                    parent_session_id, root_session_id,
                    started_at, ended_at, total_cost,
                    created_at, updated_at, source_file
                )
                VALUES (?, ?, 'completed', 'claude', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    "project-1",
                    session_type,
                    parent_id,
                    root_id,
                    "2026-02-25T10:00:00Z",
                    "2026-02-25T10:10:00Z",
                    0.25,
                    "2026-02-25T10:00:00Z",
                    "2026-02-25T10:10:00Z",
                    f"sessions/{session_id}.jsonl",
                ),
            )

        updates = [
            ("S-main", "src/app.ts", "read", "Read", "log-1", "2026-02-25T10:01:00Z", 0, 0, "main-agent"),
            ("S-main", "src/app.ts", "update", "Edit", "log-2", "2026-02-25T10:02:00Z", 10, 2, "main-agent"),
            ("S-primary", "src/levels.ts", "update", "Edit", "log-3", "2026-02-25T10:03:00Z", 5, 1, "coder-a"),
            ("S-support", "src/levels.ts", "update", "Edit", "log-4", "2026-02-25T10:04:00Z", 2, 2, "coder-b"),
            ("S-peripheral", "src/levels.ts", "read", "Read", "log-5", "2026-02-25T10:05:00Z", 0, 0, "reader-c"),
        ]
        for (
            session_id,
            file_path,
            action,
            source_tool,
            source_log_id,
            timestamp,
            additions,
            deletions,
            agent_name,
        ) in updates:
            await self.db.execute(
                """
                INSERT INTO session_file_updates (
                    session_id, file_path, action, file_type, action_timestamp,
                    additions, deletions, agent_name, thread_session_id,
                    root_session_id, source_log_id, source_tool_name
                )
                VALUES (?, ?, ?, 'Source', ?, ?, ?, ?, '', ?, ?, ?)
                """,
                (
                    session_id,
                    file_path,
                    action,
                    timestamp,
                    additions,
                    deletions,
                    agent_name,
                    session_id,
                    source_log_id,
                    source_tool,
                ),
            )

        await self.db.execute(
            """
            INSERT INTO session_logs (
                session_id, log_index, timestamp, speaker, type, content, tool_name, metadata_json
            )
            VALUES (?, ?, ?, 'agent', 'tool', ?, ?, ?)
            """,
            ("S-main", 2, "2026-02-25T10:02:00Z", "Applied update to src/app.ts", "Edit", "{}"),
        )
        await self.db.execute(
            """
            INSERT INTO session_artifacts (
                id, session_id, title, type, source, url, source_log_id, source_tool_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "A-1",
                "S-main",
                "Update summary",
                "command",
                "SkillMeat",
                "https://example.invalid/artifact/A-1",
                "log-2",
                "Edit",
            ),
        )

        features = [
            ("F-primary", "Primary Feature", 1.0, "S-primary", [{"type": "file_write", "path": "src/levels.ts"}]),
            ("F-support", "Supporting Feature", 0.7, "S-support", []),
            ("F-peripheral", "Peripheral Feature", 1.0, "S-peripheral", []),
        ]
        for feature_id, name, confidence, session_id, signals in features:
            await self.db.execute(
                """
                INSERT INTO features (
                    id, project_id, name, status, category, created_at, updated_at, data_json
                )
                VALUES (?, ?, ?, 'in-progress', 'enhancement', ?, ?, '{}')
                """,
                (
                    feature_id,
                    "project-1",
                    name,
                    "2026-02-25T10:00:00Z",
                    "2026-02-25T10:00:00Z",
                ),
            )
            await self.db.execute(
                """
                INSERT INTO entity_links (
                    source_type, source_id, target_type, target_id, link_type, origin,
                    confidence, depth, sort_order, metadata_json, created_at
                )
                VALUES ('feature', ?, 'session', ?, 'related', 'auto', ?, 0, 0, ?, ?)
                """,
                (
                    feature_id,
                    session_id,
                    confidence,
                    json.dumps({"signals": signals, "linkStrategy": "session_evidence"}),
                    "2026-02-25T10:00:00Z",
                ),
            )

        await self.db.execute(
            """
            INSERT INTO documents (
                id, project_id, title, file_path, status, frontmatter_json, source_file
            )
            VALUES (?, ?, ?, ?, 'active', '{}', ?)
            """,
            ("DOC-app", "project-1", "App Source", "src/app.ts", "docs/app.md"),
        )
        await self.db.execute(
            """
            INSERT INTO documents (
                id, project_id, title, file_path, status, frontmatter_json, source_file
            )
            VALUES (?, ?, ?, ?, 'active', '{}', ?)
            """,
            ("DOC-plan", "project-1", "Plan", "docs/plan.md", "docs/plan.md"),
        )
        await self.db.execute(
            """
            INSERT INTO document_refs (
                document_id, project_id, ref_kind, ref_value, ref_value_norm, source_field
            )
            VALUES (?, ?, 'path', ?, ?, 'pathRefs')
            """,
            ("DOC-plan", "project-1", "src/app.ts", "src/app.ts"),
        )

        await self.db.commit()

    def _flatten_tree_paths(self, nodes: list[dict]) -> set[str]:
        seen: set[str] = set()
        for node in nodes:
            seen.add(node.get("path", ""))
            children = node.get("children") or []
            if children:
                seen.update(self._flatten_tree_paths(children))
        return seen

    def _request_context(self, *, project_id: str | None, hosted: bool = False) -> RequestContext:
        provider = AuthProviderMetadata(provider_id="oidc", issuer="issuer", hosted=True) if hosted else None
        project = (
            ProjectScope(
                project_id=project_id,
                project_name=project_id,
                root_path=self.project_root,
                sessions_dir=self.project_root / "sessions",
                docs_dir=self.project_root / "docs",
                progress_dir=self.project_root / "progress",
            )
            if project_id
            else None
        )
        workspace = WorkspaceScope(workspace_id=project_id, root_path=self.project_root) if project_id else None
        return RequestContext(
            principal=Principal(
                subject="test-user",
                display_name="Test User",
                auth_mode="oidc" if hosted else "local",
                provider=provider,
            ),
            workspace=workspace,
            project=project,
            runtime_profile="api" if hosted else "local",
            trace=TraceContext(request_id="req-1"),
            tenancy=TenancyContext(workspace_id=project_id, project_id=project_id),
        )

    def _deps(self, *, context: RequestContext | None = None, core_ports=None) -> dict:
        return {
            "request_context": context or self.request_context,
            "core_ports": core_ports or self.core_ports,
        }

    async def test_tree_listing_returns_touched_nodes(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            payload = await codebase_router.get_codebase_tree(prefix="", include_untouched=False, depth=8, search="", **self._deps())

        paths = self._flatten_tree_paths(payload["nodes"])
        self.assertIn("src", paths)
        self.assertIn("src/app.ts", paths)
        self.assertIn("src/levels.ts", paths)
        self.assertNotIn("src/untouched.ts", paths)

    async def test_untouched_toggle_affects_file_list(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            touched_only = await codebase_router.get_codebase_files(
                prefix="",
                search="",
                include_untouched=False,
                action="",
                feature_id="",
                sort_by="last_touched",
                sort_order="desc",
                offset=0,
                limit=500,
                **self._deps(),
            )
            with_untouched = await codebase_router.get_codebase_files(
                prefix="",
                search="",
                include_untouched=True,
                action="",
                feature_id="",
                sort_by="last_touched",
                sort_order="desc",
                offset=0,
                limit=500,
                **self._deps(),
            )

        touched_paths = {item["filePath"] for item in touched_only["items"]}
        with_untouched_paths = {item["filePath"] for item in with_untouched["items"]}
        self.assertIn("src/app.ts", touched_paths)
        self.assertIn("src/levels.ts", touched_paths)
        self.assertNotIn("src/untouched.ts", touched_paths)
        self.assertIn("src/untouched.ts", with_untouched_paths)

    async def test_gitignore_and_builtin_excludes_are_applied(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            payload = await codebase_router.get_codebase_files(
                prefix="",
                search="",
                include_untouched=True,
                action="",
                feature_id="",
                sort_by="last_touched",
                sort_order="desc",
                offset=0,
                limit=500,
                **self._deps(),
            )

        paths = {item["filePath"] for item in payload["items"]}
        self.assertNotIn("ignored.log", paths)
        self.assertFalse(any(path.startswith("node_modules/") for path in paths))
        self.assertFalse(any(path.startswith("dist/") for path in paths))
        self.assertFalse(any(path.startswith("ignored-dir/") for path in paths))

    async def test_path_traversal_rejected(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            with self.assertRaises(HTTPException) as ctx:
                await codebase_router.get_codebase_file_detail("../secret.txt", **self._deps())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_detail_aggregation_contains_actions_and_documents(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            detail = await codebase_router.get_codebase_file_detail("src/app.ts", activity_limit=20, **self._deps())

        self.assertEqual(detail["filePath"], "src/app.ts")
        self.assertEqual(set(detail["actions"]), {"read", "update"})
        self.assertEqual(detail["touchCount"], 2)
        self.assertGreaterEqual(len(detail["sessions"]), 1)
        self.assertGreaterEqual(len(detail["documents"]), 1)
        self.assertGreaterEqual(len(detail["activity"]), 1)
        self.assertTrue(any(entry.get("artifactCount", 0) > 0 for entry in detail["activity"]))

    async def test_file_content_returns_text_payload(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            payload = await codebase_router.get_codebase_file_content("src/app.ts", **self._deps())

        self.assertEqual(payload["filePath"], "src/app.ts")
        self.assertIn("export const app = 1;", payload["content"])
        self.assertEqual(payload["sizeBytes"], len("export const app = 1;\n".encode("utf-8")))
        self.assertFalse(payload["truncated"])
        self.assertIsNone(payload["originalSize"])

    async def test_file_content_accepts_absolute_project_path(self) -> None:
        absolute_path = (self.project_root / "src" / "app.ts").resolve(strict=False)

        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            payload = await codebase_router.get_codebase_file_content(str(absolute_path), **self._deps())

        self.assertEqual(payload["filePath"], "src/app.ts")
        self.assertEqual(payload["absolutePath"], str(absolute_path))
        self.assertIn("export const app = 1;", payload["content"])

    async def test_file_content_accepts_absolute_external_path(self) -> None:
        with tempfile.TemporaryDirectory() as external_tmpdir:
            external_dir = Path(external_tmpdir)
            external_path = (external_dir / "shared.txt").resolve(strict=False)
            external_path.write_text("shared viewer content\n", encoding="utf-8")

            with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
                payload = await codebase_router.get_codebase_file_content(str(external_path), **self._deps())

            self.assertEqual(payload["filePath"], str(external_path))
            self.assertEqual(payload["absolutePath"], str(external_path))
            self.assertIn("shared viewer content", payload["content"])

    async def test_file_content_path_traversal_rejected(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            with self.assertRaises(HTTPException) as ctx:
                await codebase_router.get_codebase_file_content("../secret.txt", **self._deps())

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_involvement_levels_follow_thresholds(self) -> None:
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            detail = await codebase_router.get_codebase_file_detail("src/levels.ts", activity_limit=20, **self._deps())

        by_id = {item["featureId"]: item for item in detail["features"]}
        self.assertEqual(by_id["F-primary"]["involvementLevel"], "primary")
        self.assertEqual(by_id["F-support"]["involvementLevel"], "supporting")
        self.assertEqual(by_id["F-peripheral"]["involvementLevel"], "peripheral")

    async def test_dangling_symlink_does_not_crash_scan(self) -> None:
        dangling = self.project_root / "src" / "dangling-link"
        target = self.project_root / "src" / "missing-target"
        try:
            os.symlink(str(target), str(dangling))
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not supported in this environment")

        clear_codebase_cache()
        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            payload = await codebase_router.get_codebase_files(
                prefix="",
                search="",
                include_untouched=True,
                action="",
                feature_id="",
                sort_by="last_touched",
                sort_order="desc",
                offset=0,
                limit=500,
                **self._deps(),
            )
        self.assertTrue(isinstance(payload.get("items"), list))

    async def test_hosted_request_without_project_does_not_use_active_project(self) -> None:
        active_project = types.SimpleNamespace(id="active-project", name="Active", path=str(self.project_root))
        registry = _WorkspaceRegistry(self.project, self.bundle, active_project=active_project)
        core_ports = types.SimpleNamespace(workspace_registry=registry, authorization_policy=_AuthorizationPolicy())
        hosted_context = self._request_context(project_id=None, hosted=True)

        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            with self.assertRaises(HTTPException) as ctx:
                await codebase_router.get_codebase_tree(
                    prefix="",
                    include_untouched=False,
                    depth=8,
                    search="",
                    **self._deps(context=hosted_context, core_ports=core_ports),
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(registry.active_calls, 0)

    async def test_file_content_requires_file_read_permission(self) -> None:
        core_ports = types.SimpleNamespace(
            workspace_registry=self.registry,
            authorization_policy=_AuthorizationPolicy(allowed=False),
        )

        with patch.object(codebase_router.connection, "get_connection", return_value=self.db):
            with self.assertRaises(HTTPException) as ctx:
                await codebase_router.get_codebase_file_content(
                    "src/app.ts",
                    **self._deps(core_ports=core_ports),
                )

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
