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

    async def test_upsert_populates_promoted_feature_columns(self) -> None:
        await self.repo.upsert(
            {
                "id": "quick-features-columns",
                "name": "Quick Features Columns",
                "status": "in-progress",
                "category": "ops",
                "totalTasks": 8,
                "completedTasks": 3,
                "tags": ["smoke", "release"],
                "deferredTasks": 2,
                "plannedAt": "2026-04-21T00:00:00Z",
                "startedAt": "2026-04-22T00:00:00Z",
            },
            "project-1",
        )

        row = await self.repo.get_by_id("quick-features-columns")
        assert row is not None
        self.assertEqual(row["tags_json"], '["smoke", "release"]')
        self.assertEqual(row["deferred_tasks"], 2)
        self.assertEqual(row["planned_at"], "2026-04-21T00:00:00Z")
        self.assertEqual(row["started_at"], "2026-04-22T00:00:00Z")
        self.assertIn('"plannedAt": "2026-04-21T00:00:00Z"', row["data_json"])

    async def test_run_migrations_backfills_promoted_feature_columns(self) -> None:
        legacy_db = await aiosqlite.connect(":memory:")
        legacy_db.row_factory = aiosqlite.Row
        self.addAsyncCleanup(legacy_db.close)

        await legacy_db.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER NOT NULL,
                applied TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await legacy_db.execute("INSERT INTO schema_version (version) VALUES (24)")
        await legacy_db.execute(
            """
            CREATE TABLE features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'backlog',
                category TEXT DEFAULT '',
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                parent_feature_id TEXT,
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                completed_at TEXT DEFAULT '',
                data_json TEXT NOT NULL
            )
            """
        )
        await legacy_db.execute(
            """
            INSERT INTO features (
                id, project_id, name, status, category,
                total_tasks, completed_tasks, parent_feature_id,
                created_at, updated_at, completed_at, data_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                "legacy-feature",
                "project-1",
                "Legacy Feature",
                "done",
                "ops",
                5,
                5,
                None,
                "2026-04-20T00:00:00Z",
                "2026-04-22T00:00:00Z",
                "2026-04-22T00:00:00Z",
                '{"id":"legacy-feature","name":"Legacy Feature","status":"done","category":"ops","totalTasks":5,"completedTasks":5,"tags":["legacy"],"deferredTasks":4,"plannedAt":"2026-04-18T00:00:00Z","startedAt":"2026-04-19T00:00:00Z"}',
            ),
        )
        await legacy_db.commit()

        await run_migrations(legacy_db)

        async with legacy_db.execute("PRAGMA table_info(features)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        self.assertIn("tags_json", columns)
        self.assertIn("deferred_tasks", columns)
        self.assertIn("planned_at", columns)
        self.assertIn("started_at", columns)

        async with legacy_db.execute("SELECT * FROM features WHERE id = ?", ("legacy-feature",)) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(row["tags_json"], '["legacy"]')
        self.assertEqual(row["deferred_tasks"], 4)
        self.assertEqual(row["planned_at"], "2026-04-18T00:00:00Z")
        self.assertEqual(row["started_at"], "2026-04-19T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
