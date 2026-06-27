"""P3-004: session detail tables carry project_id on direct INSERT.

Tests that upsert_logs, upsert_tool_usage, and upsert_file_updates write
project_id into their respective detail tables, and that project-scoped
queries on those tables return only the correct project's rows.
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

_BASE_SESSION = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "platformVersion": "2.1.52",
    "platformVersions": ["2.1.52"],
    "platformVersionTransitions": [],
    "durationSeconds": 1,
    "tokensIn": 1,
    "tokensOut": 1,
    "modelIOTokens": 2,
    "cacheCreationInputTokens": 0,
    "cacheReadInputTokens": 0,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.0,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": None,
    "startedAt": "2026-06-01T00:00:00Z",
    "endedAt": "2026-06-01T00:01:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": None,
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": None,
    "contextInheritance": "fresh",
}


class DetailTablesProjectIdTests(unittest.IsolatedAsyncioTestCase):
    """upsert_logs / upsert_tool_usage / upsert_file_updates write project_id."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # P3-003 renames sessions→_sessions_backup during migration; SQLite
        # rewrites child-table FK DDL to reference _sessions_backup, which is
        # then dropped.  FK enforcement would raise "no such table: _sessions_backup"
        # on any DELETE against the detail tables.  Disable FK checks for the
        # duration of these unit tests — we are testing project_id write
        # semantics, not FK cascade integrity.
        await self.db.execute("PRAGMA foreign_keys=OFF")
        self.repo = SqliteSessionRepository(self.db)

        # Seed a session for each project so the session_id values exist.
        for project, sid in [("proj-A", "sess-A"), ("proj-B", "sess-B")]:
            await self.repo.upsert(
                {**_BASE_SESSION, "id": sid, "rootSessionId": sid, "conversationFamilyId": sid},
                project,
            )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _fetch_all(self, table: str) -> list[aiosqlite.Row]:
        async with self.db.execute(f"SELECT * FROM {table}") as cur:
            return await cur.fetchall()

    async def _fetch_project(self, table: str, project_id: str) -> list[aiosqlite.Row]:
        async with self.db.execute(
            f"SELECT * FROM {table} WHERE project_id = ?", (project_id,)
        ) as cur:
            return await cur.fetchall()

    # ── upsert_logs ───────────────────────────────────────────────────────────

    async def test_upsert_logs_writes_project_id(self) -> None:
        logs_a = [{"id": "log-a1", "timestamp": "t1", "speaker": "human", "type": "text", "content": "hello A"}]
        logs_b = [{"id": "log-b1", "timestamp": "t2", "speaker": "human", "type": "text", "content": "hello B"}]

        await self.repo.upsert_logs("sess-A", logs_a, "proj-A")
        await self.repo.upsert_logs("sess-B", logs_b, "proj-B")

        all_rows = await self._fetch_all("session_logs")
        self.assertEqual(len(all_rows), 2)

        proj_ids = {row["session_id"]: row["project_id"] for row in all_rows}
        self.assertEqual(proj_ids["sess-A"], "proj-A")
        self.assertEqual(proj_ids["sess-B"], "proj-B")

    async def test_upsert_logs_project_scoped_query_isolation(self) -> None:
        logs_a = [{"id": "log-a2", "timestamp": "t1", "speaker": "human", "type": "text", "content": "A"}]
        logs_b = [{"id": "log-b2", "timestamp": "t2", "speaker": "human", "type": "text", "content": "B"}]

        await self.repo.upsert_logs("sess-A", logs_a, "proj-A")
        await self.repo.upsert_logs("sess-B", logs_b, "proj-B")

        rows_a = await self._fetch_project("session_logs", "proj-A")
        rows_b = await self._fetch_project("session_logs", "proj-B")

        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["session_id"], "sess-A")
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0]["session_id"], "sess-B")

    # ── upsert_tool_usage ─────────────────────────────────────────────────────

    async def test_upsert_tool_usage_writes_project_id(self) -> None:
        tools_a = [{"name": "Read", "count": 3, "successRate": 1.0, "totalMs": 200}]
        tools_b = [{"name": "Edit", "count": 5, "successRate": 0.8, "totalMs": 400}]

        await self.repo.upsert_tool_usage("sess-A", tools_a, "proj-A")
        await self.repo.upsert_tool_usage("sess-B", tools_b, "proj-B")

        all_rows = await self._fetch_all("session_tool_usage")
        self.assertEqual(len(all_rows), 2)

        proj_ids = {row["session_id"]: row["project_id"] for row in all_rows}
        self.assertEqual(proj_ids["sess-A"], "proj-A")
        self.assertEqual(proj_ids["sess-B"], "proj-B")

    async def test_upsert_tool_usage_project_scoped_query_isolation(self) -> None:
        tools_a = [{"name": "Read", "count": 1, "successRate": 1.0, "totalMs": 50}]
        tools_b = [{"name": "Write", "count": 2, "successRate": 1.0, "totalMs": 80}]

        await self.repo.upsert_tool_usage("sess-A", tools_a, "proj-A")
        await self.repo.upsert_tool_usage("sess-B", tools_b, "proj-B")

        rows_a = await self._fetch_project("session_tool_usage", "proj-A")
        rows_b = await self._fetch_project("session_tool_usage", "proj-B")

        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["tool_name"], "Read")
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0]["tool_name"], "Write")

    # ── upsert_file_updates ───────────────────────────────────────────────────

    async def test_upsert_file_updates_writes_project_id(self) -> None:
        files_a = [{"filePath": "a/file.py", "action": "edit", "fileType": "Python", "timestamp": "t1",
                    "additions": 10, "deletions": 2}]
        files_b = [{"filePath": "b/file.ts", "action": "create", "fileType": "TypeScript", "timestamp": "t2",
                    "additions": 20, "deletions": 0}]

        await self.repo.upsert_file_updates("sess-A", files_a, "proj-A")
        await self.repo.upsert_file_updates("sess-B", files_b, "proj-B")

        all_rows = await self._fetch_all("session_file_updates")
        self.assertEqual(len(all_rows), 2)

        proj_ids = {row["session_id"]: row["project_id"] for row in all_rows}
        self.assertEqual(proj_ids["sess-A"], "proj-A")
        self.assertEqual(proj_ids["sess-B"], "proj-B")

    async def test_upsert_file_updates_project_scoped_query_isolation(self) -> None:
        files_a = [{"filePath": "a/x.py", "action": "edit", "fileType": "Python", "timestamp": "t1",
                    "additions": 1, "deletions": 0}]
        files_b = [{"filePath": "b/y.ts", "action": "edit", "fileType": "TypeScript", "timestamp": "t2",
                    "additions": 1, "deletions": 0}]

        await self.repo.upsert_file_updates("sess-A", files_a, "proj-A")
        await self.repo.upsert_file_updates("sess-B", files_b, "proj-B")

        rows_a = await self._fetch_project("session_file_updates", "proj-A")
        rows_b = await self._fetch_project("session_file_updates", "proj-B")

        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["file_path"], "a/x.py")
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0]["file_path"], "b/y.ts")

    # ── backward-tolerance: default empty project_id ─────────────────────────

    async def test_upsert_logs_default_project_id_is_empty_string(self) -> None:
        """Calling without project_id still works; column value is ''."""
        logs = [{"id": "log-default", "timestamp": "t", "speaker": "human", "type": "text", "content": "x"}]
        await self.repo.upsert_logs("sess-A", logs)
        rows = await self._fetch_all("session_logs")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_id"], "")

    async def test_upsert_tool_usage_default_project_id_is_empty_string(self) -> None:
        tools = [{"name": "Bash", "count": 1, "successRate": 1.0, "totalMs": 10}]
        await self.repo.upsert_tool_usage("sess-A", tools)
        rows = await self._fetch_all("session_tool_usage")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_id"], "")

    async def test_upsert_file_updates_default_project_id_is_empty_string(self) -> None:
        files = [{"filePath": "f.py", "action": "edit", "fileType": "Python", "timestamp": "t",
                  "additions": 0, "deletions": 0}]
        await self.repo.upsert_file_updates("sess-A", files)
        rows = await self._fetch_all("session_file_updates")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_id"], "")


if __name__ == "__main__":
    unittest.main()
