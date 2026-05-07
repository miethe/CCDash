"""Tests for SqliteFeatureSessionRepository paginated linked-session queries.

Fixture layout
--------------
Feature A: 3 root sessions directly linked
  - root-1  has 4 subthread children   (total family: 5 sessions)
  - root-2  has 0 children             (total family: 1 session)
  - root-3  has 1 child                (total family: 2 sessions)
  Direct refs for A = 3; INHERITED_THREADS total = 3 + 4 + 0 + 1 = 8

Feature B: 1 root session directly linked
  - root-b  has 2 children             (total family: 3 sessions)
  Direct refs for B = 1; INHERITED_THREADS total = 3

Tests
-----
- thread_expansion=NONE: page 1 limit=2 → correct 2 rows + total=3
- thread_expansion=INHERITED_THREADS: correct rows+total=8
- root_session_id filter: narrows correctly within the feature family
- sort_by=started_at DESC: deterministic with session_id tiebreaker
- list_session_family_refs([root-1, root-2]): paginate across 6-session family
- list_session_family_refs([...51 ids...]): raises ValueError
- Regression guard: total matches filter, not raw session count
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from backend.db.repositories.feature_queries import LinkedSessionQuery, ThreadExpansionMode, SortDirection
from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
from backend.db.repositories.postgres.feature_sessions import PostgresFeatureSessionRepository
from backend.db.sqlite_migrations import run_migrations, _TEST_VISUALIZER_TABLES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = "test-project"
BASE_TIME = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)



def _ts(offset_seconds: int = 0) -> str:
    return (BASE_TIME + timedelta(seconds=offset_seconds)).isoformat()


async def _setup_db(db: aiosqlite.Connection) -> None:
    await run_migrations(db)
    try:
        await db.executescript(_TEST_VISUALIZER_TABLES)
    except Exception:
        pass
    await db.commit()


async def _seed_feature(db: aiosqlite.Connection, fid: str) -> None:
    now = _ts()
    await db.execute(
        """INSERT INTO features (id, project_id, name, status, created_at, updated_at, data_json)
           VALUES (?, ?, ?, ?, ?, ?, '{}')
           ON CONFLICT(id) DO NOTHING""",
        (fid, PROJECT_ID, f"Feature {fid}", "in-progress", now, now),
    )


async def _seed_session(
    db: aiosqlite.Connection,
    session_id: str,
    *,
    root_session_id: str | None = None,
    started_at_offset: int = 0,
) -> None:
    """Insert a minimal session row.

    root_session_id defaults to session_id (making it a root itself).
    started_at is deterministic via offset_seconds from BASE_TIME.
    """
    root = root_session_id or session_id
    ts = _ts(started_at_offset)
    await db.execute(
        """INSERT INTO sessions (
               id, project_id, task_id, status, model,
               platform_type, total_cost,
               started_at, ended_at, created_at, updated_at, source_file,
               root_session_id
           ) VALUES (?, ?, '', 'completed', 'claude-sonnet-4-5',
                     'Claude Code', 0.0,
                     ?, ?, ?, ?, ?,
                     ?)
           ON CONFLICT(id) DO NOTHING""",
        (session_id, PROJECT_ID, ts, ts, ts, ts, f"{session_id}.jsonl", root),
    )


async def _link_feature_session(
    db: aiosqlite.Connection, feature_id: str, session_id: str
) -> None:
    now = _ts()
    await db.execute(
        """INSERT INTO entity_links (
               source_type, source_id, target_type, target_id, link_type,
               origin, confidence, depth, sort_order, created_at
           ) VALUES ('feature', ?, 'session', ?, 'related', 'auto', 1.0, 0, 0, ?)
           ON CONFLICT(source_type, source_id, target_type, target_id, link_type)
           DO NOTHING""",
        (feature_id, session_id, now),
    )


async def _seed_fixture(db: aiosqlite.Connection) -> dict[str, Any]:
    """Seed the full fixture and return an ID map for assertions."""
    # Features
    fid_a = "feature-A"
    fid_b = "feature-B"
    await _seed_feature(db, fid_a)
    await _seed_feature(db, fid_b)

    # Feature A roots
    root1 = "root-1"
    root2 = "root-2"
    root3 = "root-3"

    # Feature B root
    root_b = "root-b"

    # Seed root sessions (started_at offsets ensure deterministic DESC order:
    #   root1 most recent, root3 least recent within the 3 roots)
    await _seed_session(db, root1, started_at_offset=300)
    await _seed_session(db, root2, started_at_offset=200)
    await _seed_session(db, root3, started_at_offset=100)
    await _seed_session(db, root_b, started_at_offset=50)

    # root-1 children (4 sessions)
    r1_children = [f"r1-child-{i}" for i in range(4)]
    for idx, cid in enumerate(r1_children):
        await _seed_session(db, cid, root_session_id=root1, started_at_offset=idx * 10)

    # root-3 child (1 session)
    r3_child = "r3-child-0"
    await _seed_session(db, r3_child, root_session_id=root3, started_at_offset=5)

    # root-b children (2 sessions)
    rb_children = [f"rb-child-{i}" for i in range(2)]
    for idx, cid in enumerate(rb_children):
        await _seed_session(db, cid, root_session_id=root_b, started_at_offset=idx * 5)

    # Link roots directly to features (direct entity_links)
    for rid in [root1, root2, root3]:
        await _link_feature_session(db, fid_a, rid)
    await _link_feature_session(db, fid_b, root_b)

    await db.commit()

    return {
        "fid_a": fid_a,
        "fid_b": fid_b,
        "root1": root1,
        "root2": root2,
        "root3": root3,
        "root_b": root_b,
        "r1_children": r1_children,
        "r3_child": r3_child,
        "rb_children": rb_children,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestLinkedSessionPageQuery(unittest.TestCase):

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    async def _make_db(self) -> tuple[aiosqlite.Connection, SqliteFeatureSessionRepository, dict]:
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await _setup_db(db)
        ids = await _seed_fixture(db)
        repo = SqliteFeatureSessionRepository(db)
        return db, repo, ids

    # ------------------------------------------------------------------
    # thread_expansion=NONE
    # ------------------------------------------------------------------

    def test_none_expansion_page1_returns_correct_rows_and_total(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=2,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                # Direct refs = 3 (root1, root2, root3); page1 limit=2 → 2 rows
                self.assertEqual(page.total, 3)
                self.assertEqual(len(page.rows), 2)
                self.assertTrue(page.has_more)
                # Regression guard: total must equal direct-ref count, not all sessions
                total_sessions = list(await db.execute_fetchall("SELECT COUNT(*) AS n FROM sessions WHERE project_id = ?", (PROJECT_ID,)))
                all_session_count = total_sessions[0]["n"]
                self.assertLess(page.total, all_session_count,
                    "total must reflect filter, not unfiltered session count")
            finally:
                await db.close()
        self._run(go())


    def test_none_expansion_page2_returns_last_row(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=2,
                    offset=2,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(page.total, 3)
                self.assertEqual(len(page.rows), 1)
                self.assertFalse(page.has_more)
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # thread_expansion=INHERITED_THREADS
    # ------------------------------------------------------------------

    def test_inherited_threads_total(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                # Feature A: 3 direct roots + 4 r1-children + 1 r3-child = 8
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=50,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(page.total, 8)
                self.assertEqual(len(page.rows), 8)
            finally:
                await db.close()
        self._run(go())

    def test_inherited_threads_page1_correct_order_and_rows(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=2,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(page.total, 8)
                self.assertEqual(len(page.rows), 2)
                # root1 has the highest started_at (offset=300), must come first
                self.assertEqual(page.rows[0]["session_id"], ids["root1"])
            finally:
                await db.close()
        self._run(go())

    def test_inherited_threads_feature_b_correct_total(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_b"],
                    thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                    limit=50,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                # 1 root + 2 children = 3
                self.assertEqual(page.total, 3)
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # root_session_id filter
    # ------------------------------------------------------------------

    def test_root_session_id_filter_narrows_none_expansion(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                # Only sessions in root1's family that are directly linked:
                # root1 is directly linked; its children are not.
                # With NONE expansion, root_session_id filter restricts direct
                # refs to those where s.root_session_id = root1 OR s.id = root1.
                # root1 has root_session_id = root1 (it is its own root) → 1 match.
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    root_session_id=ids["root1"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    limit=10,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(page.total, 1)
                self.assertEqual(page.rows[0]["session_id"], ids["root1"])
            finally:
                await db.close()
        self._run(go())

    def test_root_session_id_filter_inherited_threads(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                # INHERITED_THREADS + root_session_id=root1
                # Should return root1 itself + 4 children = 5
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    root_session_id=ids["root1"],
                    thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                    limit=10,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(page.total, 5)
                returned_ids = {r["session_id"] for r in page.rows}
                self.assertIn(ids["root1"], returned_ids)
                for cid in ids["r1_children"]:
                    self.assertIn(cid, returned_ids)
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # Sort determinism
    # ------------------------------------------------------------------

    def test_sort_started_at_desc_is_deterministic(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=10,
                    offset=0,
                )
                page1 = await repo.list_feature_session_refs(PROJECT_ID, query)
                page2 = await repo.list_feature_session_refs(PROJECT_ID, query)
                ids1 = [r["session_id"] for r in page1.rows]
                ids2 = [r["session_id"] for r in page2.rows]
                self.assertEqual(ids1, ids2, "Result order must be deterministic")
                # DESC: root1 (offset 300) > root2 (200) > root3 (100)
                self.assertEqual(ids1, ["root-1", "root-2", "root-3"])
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # count_feature_session_refs
    # ------------------------------------------------------------------

    def test_count_feature_session_refs_none(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    limit=1,
                    offset=0,
                )
                count = await repo.count_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(count, 3)
            finally:
                await db.close()
        self._run(go())

    def test_count_feature_session_refs_inherited(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                    limit=1,
                    offset=0,
                )
                count = await repo.count_feature_session_refs(PROJECT_ID, query)
                self.assertEqual(count, 8)
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # list_session_family_refs
    # ------------------------------------------------------------------

    def test_family_refs_root1_root2_combined(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                # root1 family: 5, root2 family: 1 → combined 6
                query = LinkedSessionQuery(
                    feature_id=ids["fid_a"],  # ignored by family query
                    limit=10,
                    offset=0,
                )
                page = await repo.list_session_family_refs(
                    PROJECT_ID,
                    [ids["root1"], ids["root2"]],
                    query,
                )
                self.assertEqual(page.total, 6)
                self.assertEqual(len(page.rows), 6)
            finally:
                await db.close()
        self._run(go())

    def test_family_refs_pagination(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                query_p1 = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    limit=3,
                    offset=0,
                )
                page1 = await repo.list_session_family_refs(
                    PROJECT_ID, [ids["root1"], ids["root2"]], query_p1
                )
                query_p2 = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    limit=3,
                    offset=3,
                )
                page2 = await repo.list_session_family_refs(
                    PROJECT_ID, [ids["root1"], ids["root2"]], query_p2
                )
                self.assertEqual(page1.total, 6)
                self.assertEqual(page2.total, 6)
                self.assertEqual(len(page1.rows), 3)
                self.assertEqual(len(page2.rows), 3)
                # No overlap
                ids1 = {r["session_id"] for r in page1.rows}
                ids2 = {r["session_id"] for r in page2.rows}
                self.assertEqual(len(ids1 & ids2), 0)
            finally:
                await db.close()
        self._run(go())

    def test_family_refs_raises_on_51_ids(self):
        async def go():
            db, repo, ids = await self._make_db()
            try:
                fake_ids = [f"fake-{i}" for i in range(51)]
                query = LinkedSessionQuery(feature_id=ids["fid_a"], limit=10, offset=0)
                with self.assertRaises(ValueError) as ctx:
                    await repo.list_session_family_refs(PROJECT_ID, fake_ids, query)
                self.assertIn("51", str(ctx.exception))
            finally:
                await db.close()
        self._run(go())

    # ------------------------------------------------------------------
    # Regression guard: total reflects filter, not unfiltered count
    # ------------------------------------------------------------------

    def test_regression_total_reflects_filter_not_all_sessions(self):
        """Fails if a future refactor does post-pagination in-memory filtering.

        The invariant: page.total must equal the filtered predicate count,
        not the total sessions in the project.
        """
        async def go():
            db, repo, ids = await self._make_db()
            try:
                # Total sessions in project
                rows = list(await db.execute_fetchall(
                    "SELECT COUNT(*) AS n FROM sessions WHERE project_id = ?",
                    (PROJECT_ID,),
                ))
                all_count = rows[0]["n"]

                query_none = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    limit=1,  # deliberately tiny to expose any post-fetch filtering
                    offset=0,
                )
                page_none = await repo.list_feature_session_refs(PROJECT_ID, query_none)
                # total must be 3 (direct refs for A), not all_count
                self.assertEqual(page_none.total, 3)
                self.assertLess(page_none.total, all_count)

                # Confirm a small limit doesn't bloat or shrink the total
                query_none_limit1 = LinkedSessionQuery(
                    feature_id=ids["fid_a"],
                    thread_expansion=ThreadExpansionMode.NONE,
                    limit=1,
                    offset=0,
                )
                page_l1 = await repo.list_feature_session_refs(PROJECT_ID, query_none_limit1)
                self.assertEqual(page_l1.total, 3,
                    "total must remain 3 regardless of limit (no in-memory filtering)")
            finally:
                await db.close()
        self._run(go())


class _PostgresCaptureDB:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchval_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        self.fetch_calls.append((sql, params))
        return []

    async def fetchval(self, sql: str, *params: Any) -> int:
        self.fetchval_calls.append((sql, params))
        return 0


class TestPostgresLinkedSessionPageQuery(unittest.TestCase):
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_inherited_thread_query_uses_distinct_limit_placeholders(self) -> None:
        async def go():
            db = _PostgresCaptureDB()
            repo = PostgresFeatureSessionRepository(db)  # type: ignore[arg-type]
            query = LinkedSessionQuery(
                feature_id="feature-A",
                thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
                sort_by="started_at",
                sort_direction=SortDirection.DESC,
                limit=20,
                offset=40,
            )

            await repo.list_feature_session_refs(PROJECT_ID, query)

            sql, params = db.fetch_calls[0]
            self.assertIn("el2.source_id = $2", sql)
            self.assertIn("LIMIT $3 OFFSET $4", sql)
            self.assertEqual(params, (PROJECT_ID, "feature-A", 20, 40))

        self._run(go())


if __name__ == "__main__":
    unittest.main()
