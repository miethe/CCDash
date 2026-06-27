"""Regression test for the cursor.lastrowid / RETURNING id bug.

Root cause: On the DO-UPDATE path of the point-upsert, cursor.lastrowid fell
through to the connection-global sqlite3_last_insert_rowid().  A concurrent
INSERT into another table on the SAME connection (aiosqlite shares one
connection) clobbered that global value, so link_to_entity() received a
corrupted analytics_id that did not exist in analytics_entries, triggering a
FOREIGN KEY constraint failure.

Fix: Both INSERT branches now use RETURNING id and fetchone() so the returned
id is always the real surviving row id, independent of last_insert_rowid().
"""

import unittest

import aiosqlite

from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.sqlite_migrations import run_migrations


class AnalyticsRepoLastRowidRegressionTest(unittest.IsolatedAsyncioTestCase):
    """Verify that insert_entry returns the correct id even when concurrent
    INSERTs into other tables clobber the connection-global last_insert_rowid.
    """

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        # Create a throwaway noise table used to corrupt last_insert_rowid
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS noise (id INTEGER PRIMARY KEY AUTOINCREMENT, val TEXT)"
        )
        await self.db.commit()

        self.repo = SqliteAnalyticsRepository(self.db)

        # Seed one metric_type row (id=1) that we'll reference
        async with self.db.execute(
            "SELECT id FROM metric_types LIMIT 1"
        ) as cur:
            row = await cur.fetchone()

        if row:
            self.metric_type_id = row[0]
        else:
            # Insert a minimal metric_type if none exist
            await self.db.execute(
                """INSERT INTO metric_types (display_name, unit, value_type, aggregation)
                   VALUES ('test_metric', 'count', 'integer', 'sum')"""
            )
            await self.db.commit()
            async with self.db.execute(
                "SELECT id FROM metric_types ORDER BY rowid DESC LIMIT 1"
            ) as cur:
                row3 = await cur.fetchone()
            assert row3 is not None
            self.metric_type_id = row3[0]

        self.project_id = "proj-regression-test"
        self.captured_at = "2026-01-15T12:00:00Z"

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _insert_noise(self, count: int = 5) -> int:
        """Insert rows into the noise table so last_insert_rowid() points at
        a non-existent analytics_entries id.  Returns the last noise rowid."""
        last = 0
        for i in range(count):
            async with self.db.execute(
                "INSERT INTO noise (val) VALUES (?)", (f"noise-{i}",)
            ) as cur:
                if cur.lastrowid is not None:
                    last = int(cur.lastrowid)
        await self.db.commit()
        return last

    # ------------------------------------------------------------------
    # Test 1: plain INSERT path (non-point period) still returns correct id
    # ------------------------------------------------------------------
    async def test_non_point_insert_returns_correct_id(self) -> None:
        entry = {
            "project_id": self.project_id,
            "metric_type": self.metric_type_id,
            "value": 42.0,
            "captured_at": self.captured_at,
            "period": "daily",
            "metadata_json": None,
        }
        id1 = await self.repo.insert_entry(entry)
        self.assertGreater(id1, 0, "insert_entry must return a positive id")

        # Corrupt last_insert_rowid
        noise_id = await self._insert_noise(10)
        self.assertNotEqual(noise_id, id1, "noise ids should differ from analytics id")

        # link_to_entity must succeed (FK check)
        await self.repo.link_to_entity(id1, "project", self.project_id)

        # Verify the link row was written with the correct analytics_id
        async with self.db.execute(
            "SELECT analytics_id FROM analytics_entity_links WHERE analytics_id = ?",
            (id1,),
        ) as cur:
            link_row = await cur.fetchone()
        self.assertIsNotNone(link_row, "Link row must exist for the analytics entry")

    # ------------------------------------------------------------------
    # Test 2: DO-UPDATE path returns the original id, not the noise rowid
    # ------------------------------------------------------------------
    async def test_upsert_returns_original_id_not_noise_rowid(self) -> None:
        """The core regression: after the first insert, corrupt last_insert_rowid,
        then upsert on the same (project_id, metric_type, date) key.  The
        returned id MUST equal the original id, not the noise rowid."""
        entry = {
            "project_id": self.project_id,
            "metric_type": self.metric_type_id,
            "value": 10.0,
            "captured_at": self.captured_at,
            "period": "point",
            "metadata_json": None,
        }

        # First insert — creates the analytics row
        id1 = await self.repo.insert_entry(entry)
        self.assertGreater(id1, 0)

        # Link it (sanity check that first insert is healthy)
        await self.repo.link_to_entity(id1, "project", self.project_id)

        # Corrupt last_insert_rowid by inserting many noise rows
        noise_id = await self._insert_noise(20)
        # Ensure noise ids are genuinely higher than id1 (very likely, but assert)
        self.assertNotEqual(noise_id, id1)

        # Re-upsert on the SAME (project_id, metric_type, date) — hits DO-UPDATE
        entry_v2 = {**entry, "value": 99.0}
        id2 = await self.repo.insert_entry(entry_v2)

        # The returned id MUST be the original analytics row id, not the noise rowid
        self.assertEqual(
            id2,
            id1,
            f"DO-UPDATE path returned {id2!r} but should have returned "
            f"original id {id1!r}. Noise last rowid was {noise_id!r}.",
        )

        # link_to_entity with the returned id must NOT raise a FK constraint error
        # (use a different entity_id to avoid PRIMARY KEY conflict with the first link)
        await self.repo.link_to_entity(id2, "feature", "F-001")

        # Confirm both links exist and point at the real analytics row
        async with self.db.execute(
            "SELECT analytics_id FROM analytics_entity_links WHERE analytics_id = ?",
            (id1,),
        ) as cur:
            links = list(await cur.fetchall())
        self.assertEqual(len(links), 2, "Both entity links should be present")

    # ------------------------------------------------------------------
    # Test 3: FK would fail with the old lastrowid impl (documents the bug)
    # ------------------------------------------------------------------
    async def test_old_lastrowid_would_have_failed(self) -> None:
        """Simulate what the old code did: take last_insert_rowid() AFTER a
        concurrent noise INSERT and verify that value does NOT exist in
        analytics_entries (proving the FK would have failed)."""
        entry = {
            "project_id": self.project_id,
            "metric_type": self.metric_type_id,
            "value": 7.0,
            "captured_at": self.captured_at,
            "period": "point",
            "metadata_json": None,
        }
        id1 = await self.repo.insert_entry(entry)

        # Simulate the concurrent INSERT that clobbers last_insert_rowid
        noise_id = await self._insert_noise(10)

        # The old code would have returned noise_id here.
        # Verify noise_id does NOT exist in analytics_entries.
        async with self.db.execute(
            "SELECT id FROM analytics_entries WHERE id = ?", (noise_id,)
        ) as cur:
            ghost = await cur.fetchone()
        self.assertIsNone(
            ghost,
            f"noise rowid {noise_id} must not exist in analytics_entries — "
            "the old cursor.lastrowid impl would have returned a ghost id.",
        )

        # And confirm id1 (the real analytics row) IS in analytics_entries
        async with self.db.execute(
            "SELECT id FROM analytics_entries WHERE id = ?", (id1,)
        ) as cur:
            real = await cur.fetchone()
        self.assertIsNotNone(real, "The real analytics row must exist")


if __name__ == "__main__":
    unittest.main()
