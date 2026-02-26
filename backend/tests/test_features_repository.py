import unittest

import aiosqlite

from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.sqlite_migrations import run_migrations


class FeatureRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteFeatureRepository(self.db)
        await self.repo.upsert(
            {
                "id": "quick-features",
                "name": "Quick Features",
                "status": "backlog",
                "category": "",
                "totalTasks": 0,
                "completedTasks": 0,
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_upsert_phases_duplicate_ids_do_not_fail(self) -> None:
        await self.repo.upsert_phases(
            "quick-features",
            [
                {
                    "id": "quick-features:phase-all",
                    "phase": "all",
                    "title": "All",
                    "status": "backlog",
                    "progress": 10,
                    "totalTasks": 10,
                    "completedTasks": 1,
                },
                {
                    "id": "quick-features:phase-all",
                    "phase": "all",
                    "title": "All (updated)",
                    "status": "in-progress",
                    "progress": 20,
                    "totalTasks": 10,
                    "completedTasks": 2,
                },
            ],
        )

        rows = await self.repo.get_phases("quick-features")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "quick-features:phase-all")
        self.assertEqual(rows[0]["title"], "All (updated)")
        self.assertEqual(rows[0]["status"], "in-progress")
        self.assertEqual(rows[0]["progress"], 20)
        self.assertEqual(rows[0]["completed_tasks"], 2)


if __name__ == "__main__":
    unittest.main()
