import unittest

import aiosqlite

from backend.db.repositories.tasks import SqliteTaskRepository
from backend.db.sqlite_migrations import run_migrations


class TaskRepositoryStatsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteTaskRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_completion_stats_count_done_deferred_and_completed(self) -> None:
        rows = [
            {"id": "T-1", "title": "One", "status": "done"},
            {"id": "T-2", "title": "Two", "status": "deferred"},
            {"id": "T-3", "title": "Three", "status": "completed"},
            {"id": "T-4", "title": "Four", "status": "in-progress"},
        ]
        for row in rows:
            await self.repo.upsert(row, "project-1")

        stats = await self.repo.get_project_stats("project-1")
        self.assertEqual(stats["completed"], 3)
        self.assertAlmostEqual(stats["completion_pct"], 75.0)


if __name__ == "__main__":
    unittest.main()
