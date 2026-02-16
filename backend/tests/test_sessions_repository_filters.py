import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations


class SessionRepositoryFilterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

        base = {
            "taskId": "",
            "status": "completed",
            "model": "claude-sonnet",
            "durationSeconds": 1,
            "tokensIn": 1,
            "tokensOut": 1,
            "totalCost": 0.0,
            "qualityRating": 0,
            "frictionRating": 0,
            "gitCommitHash": None,
            "gitAuthor": None,
            "gitBranch": None,
            "startedAt": "2026-02-16T00:00:00Z",
            "endedAt": "2026-02-16T00:00:01Z",
            "sourceFile": "",
        }

        await self.repo.upsert(
            {
                **base,
                "id": "S-main",
                "sessionType": "session",
                "parentSessionId": None,
                "rootSessionId": "S-main",
                "agentId": None,
            },
            "project-1",
        )
        await self.repo.upsert(
            {
                **base,
                "id": "S-agent-a1",
                "sessionType": "subagent",
                "parentSessionId": "S-main",
                "rootSessionId": "S-main",
                "agentId": "a1",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_default_excludes_subagents(self) -> None:
        rows = await self.repo.list_paginated(0, 50, "project-1", "started_at", "desc", {})
        self.assertEqual([r["id"] for r in rows], ["S-main"])

    async def test_include_subagents_true_returns_both(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"include_subagents": True},
        )
        self.assertEqual({r["id"] for r in rows}, {"S-main", "S-agent-a1"})

    async def test_root_session_filter_with_subagents(self) -> None:
        rows = await self.repo.list_paginated(
            0,
            50,
            "project-1",
            "started_at",
            "desc",
            {"include_subagents": True, "root_session_id": "S-main"},
        )
        self.assertEqual({r["id"] for r in rows}, {"S-main", "S-agent-a1"})

        count = await self.repo.count(
            "project-1",
            {"include_subagents": True, "root_session_id": "S-main"},
        )
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
