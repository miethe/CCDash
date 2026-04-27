"""Tests for SqliteEntityLinkRepository.rebuild_for_entities (BE-203)."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

import aiosqlite

from backend.db.repositories.entity_graph import SqliteEntityLinkRepository

# Minimal DDL matching the real schema
_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS entity_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type   TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    link_type     TEXT DEFAULT 'related',
    origin        TEXT DEFAULT 'auto',
    confidence    REAL DEFAULT 1.0,
    depth         INTEGER DEFAULT 0,
    sort_order    INTEGER DEFAULT 0,
    metadata_json TEXT,
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert
    ON entity_links(source_type, source_id, target_type, target_id, link_type);
"""


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(_CREATE_DDL)
    return db


async def _insert_link(
    db: aiosqlite.Connection,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    *,
    origin: str = "auto",
    link_type: str = "related",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO entity_links
               (source_type, source_id, target_type, target_id, link_type, origin, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source_type, source_id, target_type, target_id, link_type, origin, now),
    )
    await db.commit()


async def _count_links(db: aiosqlite.Connection, where: str = "") -> int:
    query = "SELECT COUNT(*) FROM entity_links"
    if where:
        query += f" WHERE {where}"
    async with db.execute(query) as cur:
        row = await cur.fetchone()
        return row[0] if row else 0


class TestRebuildForEntitiesEmpty(unittest.IsolatedAsyncioTestCase):
    """Empty ids list is a no-op."""

    async def test_empty_ids_returns_zero_stats(self) -> None:
        db = await _make_db()
        try:
            await _insert_link(db, "feature", "feat-1", "session", "sess-1")
            repo = SqliteEntityLinkRepository(db)
            stats = await repo.rebuild_for_entities("feature", [])
            self.assertEqual(stats["entities_processed"], 0)
            self.assertEqual(stats["auto_links_rebuilt"], 0)
            # No rows were touched
            self.assertEqual(await _count_links(db), 1)
        finally:
            await db.close()

    async def test_empty_ids_does_not_raise_on_empty_table(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            stats = await repo.rebuild_for_entities("feature", [])
            self.assertEqual(stats["entities_processed"], 0)
        finally:
            await db.close()


class TestRebuildForEntitiesSingleId(unittest.IsolatedAsyncioTestCase):
    """Single id: only its auto-links are deleted; other entities are untouched."""

    async def test_only_target_entity_links_deleted(self) -> None:
        db = await _make_db()
        try:
            # feat-1 auto outbound
            await _insert_link(db, "feature", "feat-1", "session", "sess-1")
            # feat-1 inbound auto (another entity points to feat-1)
            await _insert_link(db, "session", "sess-2", "feature", "feat-1")
            # feat-1 manual link — must survive
            await _insert_link(db, "feature", "feat-1", "session", "sess-manual", origin="manual")
            # feat-2 auto link — must survive
            await _insert_link(db, "feature", "feat-2", "session", "sess-3")

            repo = SqliteEntityLinkRepository(db)
            stats = await repo.rebuild_for_entities("feature", ["feat-1"])

            self.assertEqual(stats["entities_processed"], 1)

            # feat-1 auto links (both directions) are gone
            remaining_feat1_auto = await _count_links(
                db,
                "origin = 'auto' AND "
                "((source_type='feature' AND source_id='feat-1') "
                " OR (target_type='feature' AND target_id='feat-1'))",
            )
            self.assertEqual(remaining_feat1_auto, 0)

            # feat-1 manual link survived
            manual_count = await _count_links(
                db, "origin = 'manual'"
            )
            self.assertEqual(manual_count, 1)

            # feat-2 link survived
            feat2_count = await _count_links(
                db, "source_id = 'feat-2'"
            )
            self.assertEqual(feat2_count, 1)
        finally:
            await db.close()

    async def test_inbound_auto_links_also_deleted(self) -> None:
        """Inbound auto-links where entity is the *target* must be deleted."""
        db = await _make_db()
        try:
            await _insert_link(db, "session", "sess-99", "feature", "feat-target")
            repo = SqliteEntityLinkRepository(db)
            await repo.rebuild_for_entities("feature", ["feat-target"])
            count = await _count_links(
                db,
                "target_type='feature' AND target_id='feat-target' AND origin='auto'",
            )
            self.assertEqual(count, 0)
        finally:
            await db.close()


class TestRebuildForEntitiesMultipleIds(unittest.IsolatedAsyncioTestCase):
    """Multiple ids: all are rebuilt; counts are correct."""

    async def test_all_ids_processed(self) -> None:
        db = await _make_db()
        try:
            ids = ["feat-a", "feat-b", "feat-c"]
            for fid in ids:
                await _insert_link(db, "feature", fid, "session", f"sess-{fid}")
            # Unrelated entity that must survive
            await _insert_link(db, "feature", "feat-z", "session", "sess-z")

            repo = SqliteEntityLinkRepository(db)
            stats = await repo.rebuild_for_entities("feature", ids)

            self.assertEqual(stats["entities_processed"], 3)

            # The three targeted features have no auto links
            for fid in ids:
                count = await _count_links(
                    db,
                    f"origin='auto' AND "
                    f"((source_type='feature' AND source_id='{fid}') "
                    f" OR (target_type='feature' AND target_id='{fid}'))",
                )
                self.assertEqual(count, 0, f"auto links for {fid} should be gone")

            # The untargeted entity still has its link
            z_count = await _count_links(db, "source_id='feat-z'")
            self.assertEqual(z_count, 1)
        finally:
            await db.close()

    async def test_total_link_count_correct_after_rebuild(self) -> None:
        db = await _make_db()
        try:
            # 2 auto + 1 manual for feat-1; 2 auto for feat-2; 1 auto for feat-z
            await _insert_link(db, "feature", "feat-1", "session", "s1")
            await _insert_link(db, "feature", "feat-1", "session", "s2")
            await _insert_link(db, "feature", "feat-1", "session", "s3", origin="manual")
            await _insert_link(db, "feature", "feat-2", "session", "s4")
            await _insert_link(db, "feature", "feat-2", "session", "s5")
            await _insert_link(db, "feature", "feat-z", "session", "sz")

            repo = SqliteEntityLinkRepository(db)
            await repo.rebuild_for_entities("feature", ["feat-1", "feat-2"])

            # 4 auto links deleted; 1 manual + 1 feat-z auto remain = 2 total
            total = await _count_links(db)
            self.assertEqual(total, 2)
        finally:
            await db.close()


if __name__ == "__main__":
    unittest.main()
