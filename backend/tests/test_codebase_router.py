import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite
from fastapi import HTTPException

from backend.db.sqlite_migrations import run_migrations
from backend.routers import codebase as codebase_router
from backend.services.codebase_explorer import clear_codebase_cache


class CodebaseRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self._create_filesystem_fixture()

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await self._seed_database()
        self.project = types.SimpleNamespace(id="project-1", path=str(self.project_root))
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

    async def test_tree_listing_returns_touched_nodes(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
            payload = await codebase_router.get_codebase_tree(prefix="", include_untouched=False, depth=8, search="")

        paths = self._flatten_tree_paths(payload["nodes"])
        self.assertIn("src", paths)
        self.assertIn("src/app.ts", paths)
        self.assertIn("src/levels.ts", paths)
        self.assertNotIn("src/untouched.ts", paths)

    async def test_untouched_toggle_affects_file_list(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
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
            )

        touched_paths = {item["filePath"] for item in touched_only["items"]}
        with_untouched_paths = {item["filePath"] for item in with_untouched["items"]}
        self.assertIn("src/app.ts", touched_paths)
        self.assertIn("src/levels.ts", touched_paths)
        self.assertNotIn("src/untouched.ts", touched_paths)
        self.assertIn("src/untouched.ts", with_untouched_paths)

    async def test_gitignore_and_builtin_excludes_are_applied(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
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
            )

        paths = {item["filePath"] for item in payload["items"]}
        self.assertNotIn("ignored.log", paths)
        self.assertFalse(any(path.startswith("node_modules/") for path in paths))
        self.assertFalse(any(path.startswith("dist/") for path in paths))
        self.assertFalse(any(path.startswith("ignored-dir/") for path in paths))

    async def test_path_traversal_rejected(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await codebase_router.get_codebase_file_detail("../secret.txt")
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_detail_aggregation_contains_actions_and_documents(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
            detail = await codebase_router.get_codebase_file_detail("src/app.ts", activity_limit=20)

        self.assertEqual(detail["filePath"], "src/app.ts")
        self.assertEqual(set(detail["actions"]), {"read", "update"})
        self.assertEqual(detail["touchCount"], 2)
        self.assertGreaterEqual(len(detail["sessions"]), 1)
        self.assertGreaterEqual(len(detail["documents"]), 1)
        self.assertGreaterEqual(len(detail["activity"]), 1)
        self.assertTrue(any(entry.get("artifactCount", 0) > 0 for entry in detail["activity"]))

    async def test_involvement_levels_follow_thresholds(self) -> None:
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
            detail = await codebase_router.get_codebase_file_detail("src/levels.ts", activity_limit=20)

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
        with (
            patch.object(codebase_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(codebase_router.connection, "get_connection", return_value=self.db),
        ):
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
            )
        self.assertTrue(isinstance(payload.get("items"), list))


if __name__ == "__main__":
    unittest.main()
