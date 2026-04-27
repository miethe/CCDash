"""Unit tests for the filesystem_scan_manifest migration and repository.

Covers:
- Migration idempotency on SQLite in-memory DB
- upsert_manifest + fetch_manifest round-trip
- diff_against: detects added, removed, and changed paths
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.db.repositories.scan_manifest import SqliteScanManifestRepository


class TestScanManifestMigration(unittest.IsolatedAsyncioTestCase):
    """The table must exist after migrations run and be idempotent on re-run."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_migration_creates_table(self) -> None:
        await run_migrations(self.db)
        async with self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='filesystem_scan_manifest'"
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, "filesystem_scan_manifest table should exist after migrations")

    async def test_migration_is_idempotent(self) -> None:
        """Running migrations twice must not raise."""
        await run_migrations(self.db)
        await run_migrations(self.db)  # should be a no-op, not an error


class TestScanManifestRoundTrip(unittest.IsolatedAsyncioTestCase):
    """upsert_manifest stores rows; fetch_manifest retrieves them correctly."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteScanManifestRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_fetch_empty_manifest(self) -> None:
        result = await self.repo.fetch_manifest()
        self.assertEqual(result, {})

    async def test_upsert_and_fetch(self) -> None:
        entries = [
            ("/project/src/main.py", 1_700_000_000.0, 4096),
            ("/project/src/utils.py", 1_700_000_001.5, 2048),
        ]
        await self.repo.upsert_manifest(entries)
        manifest = await self.repo.fetch_manifest()

        self.assertEqual(len(manifest), 2)
        self.assertAlmostEqual(manifest["/project/src/main.py"][0], 1_700_000_000.0)
        self.assertEqual(manifest["/project/src/main.py"][1], 4096)
        self.assertAlmostEqual(manifest["/project/src/utils.py"][0], 1_700_000_001.5)
        self.assertEqual(manifest["/project/src/utils.py"][1], 2048)

    async def test_upsert_updates_existing_entry(self) -> None:
        await self.repo.upsert_manifest([("/project/src/main.py", 1_700_000_000.0, 4096)])
        # Simulate file modification: newer mtime, different size
        await self.repo.upsert_manifest([("/project/src/main.py", 1_700_000_999.0, 5000)])
        manifest = await self.repo.fetch_manifest()

        self.assertEqual(len(manifest), 1)
        self.assertAlmostEqual(manifest["/project/src/main.py"][0], 1_700_000_999.0)
        self.assertEqual(manifest["/project/src/main.py"][1], 5000)

    async def test_upsert_empty_list_is_noop(self) -> None:
        await self.repo.upsert_manifest([])
        manifest = await self.repo.fetch_manifest()
        self.assertEqual(manifest, {})


class TestScanManifestDiff(unittest.IsolatedAsyncioTestCase):
    """diff_against correctly classifies added, removed, and changed paths."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteScanManifestRepository(self.db)
        # Seed the stored manifest with three files
        await self.repo.upsert_manifest([
            ("/project/a.py", 1_000.0, 100),
            ("/project/b.py", 2_000.0, 200),
            ("/project/c.py", 3_000.0, 300),
        ])

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_no_changes(self) -> None:
        current = {
            "/project/a.py": (1_000.0, 100),
            "/project/b.py": (2_000.0, 200),
            "/project/c.py": (3_000.0, 300),
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["removed"], [])
        self.assertEqual(diff["changed"], [])

    async def test_detects_added_file(self) -> None:
        current = {
            "/project/a.py": (1_000.0, 100),
            "/project/b.py": (2_000.0, 200),
            "/project/c.py": (3_000.0, 300),
            "/project/d.py": (4_000.0, 400),  # new
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["added"], ["/project/d.py"])
        self.assertEqual(diff["removed"], [])
        self.assertEqual(diff["changed"], [])

    async def test_detects_removed_file(self) -> None:
        current = {
            "/project/a.py": (1_000.0, 100),
            # b.py deleted
            "/project/c.py": (3_000.0, 300),
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["removed"], ["/project/b.py"])
        self.assertEqual(diff["changed"], [])

    async def test_detects_changed_file_mtime(self) -> None:
        current = {
            "/project/a.py": (1_000.0, 100),
            "/project/b.py": (9_999.0, 200),  # mtime changed
            "/project/c.py": (3_000.0, 300),
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["removed"], [])
        self.assertEqual(diff["changed"], ["/project/b.py"])

    async def test_detects_changed_file_size(self) -> None:
        current = {
            "/project/a.py": (1_000.0, 100),
            "/project/b.py": (2_000.0, 999),  # size changed
            "/project/c.py": (3_000.0, 300),
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["changed"], ["/project/b.py"])

    async def test_detects_all_change_types_simultaneously(self) -> None:
        current = {
            # a.py: unchanged
            "/project/a.py": (1_000.0, 100),
            # b.py: changed mtime
            "/project/b.py": (2_001.0, 200),
            # c.py: removed (absent)
            # d.py: added
            "/project/d.py": (4_000.0, 400),
        }
        diff = await self.repo.diff_against(current)
        self.assertEqual(diff["added"], ["/project/d.py"])
        self.assertEqual(diff["removed"], ["/project/c.py"])
        self.assertEqual(diff["changed"], ["/project/b.py"])

    async def test_diff_against_empty_current_marks_all_as_removed(self) -> None:
        diff = await self.repo.diff_against({})
        self.assertEqual(sorted(diff["removed"]), ["/project/a.py", "/project/b.py", "/project/c.py"])
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["changed"], [])

    async def test_diff_against_empty_manifest_marks_all_as_added(self) -> None:
        # Use a fresh repo with no seeded data
        db2 = await aiosqlite.connect(":memory:")
        db2.row_factory = aiosqlite.Row
        await run_migrations(db2)
        repo2 = SqliteScanManifestRepository(db2)
        try:
            current = {"/project/new.py": (5_000.0, 512)}
            diff = await repo2.diff_against(current)
            self.assertEqual(diff["added"], ["/project/new.py"])
            self.assertEqual(diff["removed"], [])
            self.assertEqual(diff["changed"], [])
        finally:
            await db2.close()


if __name__ == "__main__":
    unittest.main()
