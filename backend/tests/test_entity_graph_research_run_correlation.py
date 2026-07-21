"""Tests for research-run<->session correlation (T2-006, FR-9, D2).

Covers ``SqliteEntityLinkRepository.find_candidate_sessions_for_run``,
``link_research_run_sessions``, and ``correlate_research_run``. Verifies the
D2 hard boundary at the data level: link rows are keyed by the genuine-UUID
``run_id``, never by RF's raw ``rf_run_id``/``intent_id``/``task_node_id``
(those only ever appear inside ``metadata_json`` as display-only strings),
and ``aos_correlation.py`` is never imported/touched by this module.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.db.repositories.entity_graph import (
    RESEARCH_RUN_LINK_TYPE,
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
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert
    ON entity_links(source_type, source_id, target_type, target_id, link_type);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT NOT NULL,
    project_id TEXT NOT NULL,
    started_at TEXT DEFAULT '',
    ended_at   TEXT DEFAULT ''
);
"""

_RUN_UUID = "3f9c2a4e-2b6a-4a7d-8b1a-8f2c9d5e1a11"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(_CREATE_DDL)
    return db


async def _insert_session(
    db: aiosqlite.Connection,
    session_id: str,
    project_id: str,
    started_at: datetime,
    ended_at: datetime | None,
) -> None:
    await db.execute(
        "INSERT INTO sessions (id, project_id, started_at, ended_at) VALUES (?, ?, ?, ?)",
        (
            session_id,
            project_id,
            _iso(started_at),
            _iso(ended_at) if ended_at else "",
        ),
    )
    await db.commit()


def _make_run(**overrides) -> dict:
    base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
    run = {
        "run_id": _RUN_UUID,
        "project_id": "proj-1",
        "rf_run_id": "search_router_run_042",
        "intent_id": "intent_research_foundry_search_router",
        "task_node_id": "task-node-abc",
        "rf_project": "research-foundry",
        "first_event_at": _iso(base),
        "last_event_at": _iso(base + timedelta(minutes=5)),
    }
    run.update(overrides)
    return run


class TestFindCandidateSessionsForRun(unittest.IsolatedAsyncioTestCase):
    async def test_overlapping_session_is_a_candidate(self) -> None:
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(db, "sess-1", "proj-1", base, base + timedelta(minutes=10))
            repo = SqliteEntityLinkRepository(db)
            candidates = await repo.find_candidate_sessions_for_run(_make_run())
            self.assertEqual(candidates, ["sess-1"])
        finally:
            await db.close()

    async def test_disjoint_session_far_outside_tolerance_is_not_a_candidate(self) -> None:
        db = await _make_db()
        try:
            far_past = datetime(2026, 1, 1, tzinfo=timezone.utc)
            await _insert_session(
                db, "sess-old", "proj-1", far_past, far_past + timedelta(hours=1)
            )
            repo = SqliteEntityLinkRepository(db)
            candidates = await repo.find_candidate_sessions_for_run(_make_run())
            self.assertEqual(candidates, [])
        finally:
            await db.close()

    async def test_different_project_is_excluded(self) -> None:
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(db, "sess-other-proj", "proj-2", base, base + timedelta(minutes=5))
            repo = SqliteEntityLinkRepository(db)
            candidates = await repo.find_candidate_sessions_for_run(_make_run(project_id="proj-1"))
            self.assertEqual(candidates, [])
        finally:
            await db.close()

    async def test_in_flight_session_with_no_ended_at_can_still_match(self) -> None:
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 9, 55, 0, tzinfo=timezone.utc)
            await _insert_session(db, "sess-open", "proj-1", base, None)
            repo = SqliteEntityLinkRepository(db)
            candidates = await repo.find_candidate_sessions_for_run(_make_run())
            self.assertEqual(candidates, ["sess-open"])
        finally:
            await db.close()

    async def test_missing_project_id_or_window_yields_empty_list(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            self.assertEqual(
                await repo.find_candidate_sessions_for_run(_make_run(project_id=None)), []
            )
            self.assertEqual(
                await repo.find_candidate_sessions_for_run(_make_run(first_event_at=None)), []
            )
        finally:
            await db.close()


class TestLinkResearchRunSessions(unittest.IsolatedAsyncioTestCase):
    async def test_link_row_keyed_by_uuid_run_id_never_rf_raw_ids(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            run = _make_run()
            linked = await repo.link_research_run_sessions(run, ["sess-1"])
            self.assertEqual(linked, 1)

            async with db.execute("SELECT * FROM entity_links") as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            # Identity/join keys are the genuine UUID run_id, never RF's raw ids.
            self.assertEqual(row["source_type"], "research_run")
            self.assertEqual(row["source_id"], _RUN_UUID)
            self.assertEqual(row["target_type"], "session")
            self.assertEqual(row["target_id"], "sess-1")
            self.assertEqual(row["link_type"], RESEARCH_RUN_LINK_TYPE)

            # RF's raw ids are present ONLY as display-only metadata attributes.
            metadata = json.loads(row["metadata_json"])
            self.assertEqual(metadata["rf_run_id"], "search_router_run_042")
            self.assertEqual(metadata["intent_id"], "intent_research_foundry_search_router")
            self.assertEqual(metadata["task_node_id"], "task-node-abc")
        finally:
            await db.close()

    async def test_direct_count_after_linking_two_sessions(self) -> None:
        """ADR-007 direct-count assertion: exactly N rows land via a raw COUNT(*)."""
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            run = _make_run()
            await repo.link_research_run_sessions(run, ["sess-1", "sess-2"])

            async with db.execute(
                "SELECT COUNT(*) FROM entity_links WHERE source_type = 'research_run'"
            ) as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 2)
        finally:
            await db.close()

    async def test_relink_is_idempotent_upsert_not_duplicate_rows(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            run = _make_run()
            await repo.link_research_run_sessions(run, ["sess-1"])
            await repo.link_research_run_sessions(run, ["sess-1"])

            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 1)
        finally:
            await db.close()

    async def test_no_session_ids_or_no_run_id_is_a_noop(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            self.assertEqual(await repo.link_research_run_sessions(_make_run(), []), 0)
            self.assertEqual(
                await repo.link_research_run_sessions(_make_run(run_id=None), ["sess-1"]), 0
            )
            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 0)
        finally:
            await db.close()


class TestCorrelateResearchRun(unittest.IsolatedAsyncioTestCase):
    async def test_discoverable_correlated_session_gets_a_link_row(self) -> None:
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(db, "sess-1", "proj-1", base, base + timedelta(minutes=10))
            repo = SqliteEntityLinkRepository(db)
            result = await repo.correlate_research_run(_make_run())

            self.assertTrue(result["correlated"])
            self.assertEqual(result["linked_session_ids"], ["sess-1"])
            self.assertEqual(result["run_id"], _RUN_UUID)

            linked_ids = await repo.get_linked_session_ids_for_run(_RUN_UUID)
            self.assertEqual(linked_ids, ["sess-1"])
        finally:
            await db.close()

    async def test_no_discoverable_session_yields_explicit_empty_not_default(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            result = await repo.correlate_research_run(_make_run())

            self.assertFalse(result["correlated"])
            self.assertEqual(result["linked_session_ids"], [])

            async with db.execute("SELECT COUNT(*) FROM entity_links") as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 0)
        finally:
            await db.close()

    async def test_two_runs_sharing_one_session_produce_two_link_rows_not_one(self) -> None:
        """Sets up the exact shape T2-007's dedup regression test rolls up over."""
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(db, "sess-shared", "proj-1", base, base + timedelta(minutes=30))
            repo = SqliteEntityLinkRepository(db)

            run_a = _make_run(run_id="3f9c2a4e-2b6a-4a7d-8b1a-8f2c9d5e1a11")
            run_b = _make_run(run_id="7a1b3c5d-4e6f-4a8b-9c0d-1e2f3a4b5c6d")
            await repo.correlate_research_run(run_a)
            await repo.correlate_research_run(run_b)

            linked_a = await repo.get_linked_session_ids_for_run(run_a["run_id"])
            linked_b = await repo.get_linked_session_ids_for_run(run_b["run_id"])
            self.assertEqual(linked_a, ["sess-shared"])
            self.assertEqual(linked_b, ["sess-shared"])

            async with db.execute(
                "SELECT COUNT(*) FROM entity_links WHERE target_id = 'sess-shared'"
            ) as cur:
                row = await cur.fetchone()
            self.assertEqual(row[0], 2)
        finally:
            await db.close()


if __name__ == "__main__":
    unittest.main()
