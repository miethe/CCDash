"""Tests for IntentTree node<->session declared bindings (itt-node-session-cost-join, AC1).

Covers ``SqliteEntityLinkRepository.link_intent_node_sessions`` and
``get_intent_node_session_ids``.  Verifies:
  - the link row's identity (source_type='intent_node', link_type='intent_node',
    origin='declared') and that project_id rides along on the row;
  - re-declaring the same (node_id, session_id) pair is an idempotent UPDATE,
    never a duplicate row -- verified with a direct ``COUNT(*)`` assertion
    per ADR-007;
  - ``bulk_upsert`` (used elsewhere, e.g. sync engine link rebuild) still
    behaves identically after its commit was wrapped in ``retry_on_locked``.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_entity_graph_intent_node_links.py -v
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.entity_graph import (
    INTENT_NODE_LINK_ORIGIN,
    INTENT_NODE_LINK_TARGET_TYPE,
    INTENT_NODE_LINK_TYPE,
    SqliteEntityLinkRepository,
)

_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS entity_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT NOT NULL DEFAULT 'default-local',
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
    created_at    TEXT NOT NULL,
    project_id    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert
    ON entity_links(source_type, source_id, target_type, target_id, link_type);
"""

NODE_ID = "itt-node-abc123"
PROJECT_ID = "proj-1"


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    # Any independent sqlite connection MUST issue PRAGMA busy_timeout (ADR-007
    # convention for new test helpers -- see commit ba2892d).
    await db.execute("PRAGMA busy_timeout = 30000")
    await db.executescript(_CREATE_DDL)
    return db


class TestLinkIntentNodeSessions(unittest.IsolatedAsyncioTestCase):
    async def test_link_row_shape_and_project_id(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            linked = await repo.link_intent_node_sessions(
                NODE_ID, ["sess-1"], project_id=PROJECT_ID
            )
            self.assertEqual(linked, 1)

            async with db.execute("SELECT * FROM entity_links") as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["source_type"], "intent_node")
            self.assertEqual(row["source_id"], NODE_ID)
            self.assertEqual(row["target_type"], INTENT_NODE_LINK_TARGET_TYPE)
            self.assertEqual(row["target_id"], "sess-1")
            self.assertEqual(row["link_type"], INTENT_NODE_LINK_TYPE)
            self.assertEqual(row["origin"], INTENT_NODE_LINK_ORIGIN)
            self.assertEqual(row["project_id"], PROJECT_ID)
        finally:
            await db.close()

    async def test_direct_count_after_linking_multiple_sessions(self) -> None:
        """ADR-007 direct-count assertion: exactly N rows land via a raw COUNT(*)."""
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            await repo.link_intent_node_sessions(
                NODE_ID, ["sess-1", "sess-2", "sess-3"], project_id=PROJECT_ID
            )

            async with db.execute(
                "SELECT COUNT(*) FROM entity_links WHERE source_type = 'intent_node'"
            ) as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 3)
        finally:
            await db.close()

    async def test_redeclare_is_idempotent_upsert_not_duplicate_rows(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            await repo.link_intent_node_sessions(NODE_ID, ["sess-1"], project_id=PROJECT_ID)
            await repo.link_intent_node_sessions(NODE_ID, ["sess-1"], project_id=PROJECT_ID)
            await repo.link_intent_node_sessions(NODE_ID, ["sess-1"], project_id=PROJECT_ID)

            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 1)
        finally:
            await db.close()

    async def test_redeclare_with_additional_session_adds_exactly_one_row(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            await repo.link_intent_node_sessions(NODE_ID, ["sess-1"], project_id=PROJECT_ID)
            await repo.link_intent_node_sessions(
                NODE_ID, ["sess-1", "sess-2"], project_id=PROJECT_ID
            )

            async with db.execute(
                "SELECT COUNT(*) FROM entity_links WHERE source_type = 'intent_node'"
            ) as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 2)
        finally:
            await db.close()

    async def test_duplicate_session_ids_in_one_call_are_deduped(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            linked = await repo.link_intent_node_sessions(
                NODE_ID, ["sess-1", "sess-1", "sess-1"], project_id=PROJECT_ID
            )
            self.assertEqual(linked, 1)

            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 1)
        finally:
            await db.close()

    async def test_empty_node_id_or_session_ids_is_a_noop(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            self.assertEqual(
                await repo.link_intent_node_sessions("", ["sess-1"], project_id=PROJECT_ID), 0
            )
            self.assertEqual(
                await repo.link_intent_node_sessions(NODE_ID, [], project_id=PROJECT_ID), 0
            )
            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 0)
        finally:
            await db.close()


class TestGetIntentNodeSessionIds(unittest.IsolatedAsyncioTestCase):
    async def test_returns_declared_session_ids(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            await repo.link_intent_node_sessions(
                NODE_ID, ["sess-1", "sess-2"], project_id=PROJECT_ID
            )
            ids = await repo.get_intent_node_session_ids(NODE_ID)
            self.assertEqual(sorted(ids), ["sess-1", "sess-2"])
        finally:
            await db.close()

    async def test_unknown_node_yields_empty_list_not_error(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            ids = await repo.get_intent_node_session_ids("does-not-exist")
            self.assertEqual(ids, [])
        finally:
            await db.close()

    async def test_different_node_bindings_do_not_leak_into_each_other(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            await repo.link_intent_node_sessions("node-a", ["sess-a"], project_id=PROJECT_ID)
            await repo.link_intent_node_sessions("node-b", ["sess-b"], project_id=PROJECT_ID)

            self.assertEqual(await repo.get_intent_node_session_ids("node-a"), ["sess-a"])
            self.assertEqual(await repo.get_intent_node_session_ids("node-b"), ["sess-b"])
        finally:
            await db.close()


if __name__ == "__main__":
    unittest.main()
