"""Phase 1 regression guard tests.

This module contains exactly the five regression tests called out in P1-007.
It intentionally avoids duplicating any coverage already present in the
per-surface test files (test_feature_list_query.py, test_phase_summary_bulk.py,
test_feature_rollup_query.py, test_linked_session_page_query.py).

Seeding helpers are imported directly from those existing modules rather than
factored into a shared fixture module.  The per-surface files already export
self-contained, minimal helpers (e.g. ``_make_feature``, ``_seed_session``,
``_seed_fixture``) so re-using them avoids divergence without requiring a new
shared module.  A shared ``_phase_1_fixtures.py`` would be justified if three
or more *new* test files needed the same helpers; for a single regression file,
the import-and-reuse approach is cheaper to maintain.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch

import aiosqlite
import pytest

# ---------------------------------------------------------------------------
# Imports from sibling production modules
# ---------------------------------------------------------------------------
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.feature_queries import (
    FeatureListQuery,
    FeatureRollupQuery,
    LinkedSessionQuery,
    PhaseSummaryBulkQuery,
    ThreadExpansionMode,
    SortDirection,
)
from backend.db.repositories.feature_rollup import SqliteFeatureRollupRepository
from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
from backend.db.sqlite_migrations import run_migrations, _TEST_VISUALIZER_TABLES

# ---------------------------------------------------------------------------
# Reuse seed helpers from the existing per-surface test files
# ---------------------------------------------------------------------------
from backend.tests.test_feature_list_query import _make_feature  # noqa: F401 (re-exported)
from backend.tests.test_feature_rollup_query import (
    _seed_feature as _rollup_seed_feature,
    _seed_session as _rollup_seed_session,
    _link_feature_session as _rollup_link_feature_session,
    PROJECT_ID as _ROLLUP_PROJECT_ID,
)
from backend.tests.test_linked_session_page_query import (
    _seed_feature as _lsp_seed_feature,
    _seed_session as _lsp_seed_session,
    _link_feature_session as _lsp_link_feature_session,
    _setup_db as _lsp_setup_db,
    PROJECT_ID as _LSP_PROJECT_ID,
)

# ---------------------------------------------------------------------------
# Helpers — shared constants / async runner
# ---------------------------------------------------------------------------

_TEST_PROJECT = "regression-project"


def _run(coro):
    """Run a coroutine in a fresh event loop (matches test_linked_session_page_query pattern)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Test 1 – list_feature_cards total reflects filter, not full table
# ---------------------------------------------------------------------------

class TestListFeatureCardsTotalReflectsFilter(unittest.TestCase):
    """Regression: status filter must be applied in SQL, not in-memory after pagination.

    The pre-fix bug caused ``total`` to equal the full table count when filters
    were evaluated post-pagination.  We seed 10 features (5 active, 5 backlog)
    and assert that filtering by status=["active"] returns total=5, not 10.
    """

    def _run(self, coro):
        return _run(coro)

    def test_list_feature_cards_total_reflects_filter_not_full_table(self):
        async def go():
            db = await aiosqlite.connect(":memory:")
            db.row_factory = aiosqlite.Row
            await run_migrations(db)
            repo = SqliteFeatureRepository(db)
            try:
                # Seed 5 "active" + 5 "backlog" features
                for i in range(1, 6):
                    await repo.upsert(
                        _make_feature(f"R-{i:03d}", f"Active Feature {i}", "active", "cat-a", 5, 2),
                        _TEST_PROJECT,
                    )
                for i in range(6, 11):
                    await repo.upsert(
                        _make_feature(f"R-{i:03d}", f"Backlog Feature {i}", "backlog", "cat-a", 3, 0),
                        _TEST_PROJECT,
                    )

                q = FeatureListQuery(status=["active"], limit=3, offset=0)
                page = await repo.list_feature_cards(_TEST_PROJECT, q)

                # Regression check: total must be the FILTERED count, not 10
                self.assertNotEqual(page.total, 10,
                    "total must NOT equal the unfiltered table count (regression guard)")
                self.assertEqual(page.total, 5,
                    "total must equal the number of 'active' features seeded")
                # Pagination sanity: only 3 rows returned, but total=5
                self.assertEqual(len(page.rows), 3)
                self.assertTrue(page.has_more)
            finally:
                await db.close()

        self._run(go())


# ---------------------------------------------------------------------------
# Test 2 – no N+1 in phase summary bulk
# ---------------------------------------------------------------------------

class TestNoNPlusOneInPhaseSummaryBulk(unittest.TestCase):
    """Regression: list_phase_summaries_for_features must issue ≤ 2 SQL statements.

    The N+1 pattern would issue one query per feature_id; the fixed implementation
    uses a single IN-clause query.  We instrument ``db.execute`` via a counter
    wrapper and assert the invocation count stays at or below 2.
    """

    def _run(self, coro):
        return _run(coro)

    def test_no_n_plus_one_in_phase_summary_bulk(self):
        async def go():
            db = await aiosqlite.connect(":memory:")
            db.row_factory = aiosqlite.Row
            # Use the minimal DDL from test_phase_summary_bulk instead of full migrations
            # so this test has no dependency on migration ordering.
            from backend.tests.test_phase_summary_bulk import DDL, FEATURES, PHASES
            await db.executescript(DDL)
            for fid, proj in FEATURES:
                await db.execute(
                    "INSERT INTO features (id, project_id, name) VALUES (?, ?, ?)",
                    (fid, proj, fid),
                )
            for row in PHASES:
                await db.execute(
                    "INSERT INTO feature_phases"
                    " (id, feature_id, phase, title, status, progress, total_tasks, completed_tasks)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
            await db.commit()

            # Wrap db.execute to count invocations.
            # aiosqlite's db.execute is a *synchronous* method that returns an
            # async context manager; our wrapper must also be synchronous so that
            # the production code's `async with db.execute(...)` still works.
            call_count: list[int] = [0]
            _original_execute = db.execute

            def _counting_execute(sql, *args, **kwargs):
                call_count[0] += 1
                return _original_execute(sql, *args, **kwargs)

            db.execute = _counting_execute  # type: ignore[assignment]

            try:
                repo = SqliteFeatureRepository(db)
                five_ids = ["FEAT-1", "FEAT-2", "FEAT-3", "FEAT-4", "FEAT-5"]
                q = PhaseSummaryBulkQuery(feature_ids=five_ids)
                await repo.list_phase_summaries_for_features("proj-A", q)
                self.assertLessEqual(
                    call_count[0], 2,
                    f"Expected ≤ 2 SQL statements but got {call_count[0]}. "
                    "N+1 queries detected — each feature_id must NOT issue its own query.",
                )
            finally:
                db.execute = _original_execute  # type: ignore[assignment]
                await db.close()

        self._run(go())


# ---------------------------------------------------------------------------
# Test 3 – feature rollup does not read session logs
# ---------------------------------------------------------------------------

class TestFeatureRollupDoesNotReadSessionLogs(unittest.TestCase):
    """Regression: rollup aggregates must aggregate from the DB, never from JSONL files.

    We monkeypatch all public callables in ``backend.parsers.sessions`` to raise
    AssertionError, then call get_feature_session_rollups.  If any rollup code
    path touches the sessions parser, the test will fail with that error.
    """

    def _run(self, coro):
        return _run(coro)

    def test_feature_rollup_does_not_read_session_logs(self):
        async def go():
            db = await aiosqlite.connect(":memory:")
            db.row_factory = aiosqlite.Row
            await run_migrations(db)
            await db.executescript(_TEST_VISUALIZER_TABLES)

            fids = ["R-ROLLUP-1", "R-ROLLUP-2", "R-ROLLUP-3"]
            for fid in fids:
                await _rollup_seed_feature(db, fid, f"Feature {fid}")
                s = f"session-{fid}"
                await _rollup_seed_session(db, s, total_cost=1.0)
                await _rollup_link_feature_session(db, fid, s)
            await db.commit()

            repo = SqliteFeatureRollupRepository(db)

            # Replace every public callable in backend.parsers.sessions with a bomb
            import backend.parsers.sessions as _sessions_module
            banned_callables = {
                name
                for name, obj in vars(_sessions_module).items()
                if callable(obj) and not name.startswith("_")
            }

            def _make_bomb(name: str):
                def _bomb(*args, **kwargs):
                    raise AssertionError(
                        f"rollup must not read session logs — "
                        f"backend.parsers.sessions.{name}() was called"
                    )
                return _bomb

            patches = {
                name: patch.object(_sessions_module, name, side_effect=_make_bomb(name))
                for name in banned_callables
            }
            for p in patches.values():
                p.start()

            try:
                q = FeatureRollupQuery(
                    feature_ids=fids,
                    include_fields={"session_counts"},
                    include_freshness=False,
                )
                batch = await repo.get_feature_session_rollups(_ROLLUP_PROJECT_ID, q)
                # Confirm valid rollup returned
                self.assertEqual(len(batch.rollups), 3,
                    "Expected rollups for all 3 features")
                for fid in fids:
                    self.assertIn(fid, batch.rollups)
            finally:
                for p in patches.values():
                    p.stop()
                await db.close()

        self._run(go())


# ---------------------------------------------------------------------------
# Test 4 – linked session pagination does not materialise all rows
# ---------------------------------------------------------------------------

class TestLinkedSessionPaginationDoesNotMaterializeAllRows(unittest.TestCase):
    """Regression: list_feature_session_refs must push LIMIT/OFFSET into SQL.

    We seed 50 sessions linked to one feature, then request limit=5.
    By intercepting ``db.execute`` we count how many result rows are produced.
    The assertion (≤ 6) is a behavioral lower bound — the true guarantee is
    that a SQL ``LIMIT`` clause appears in the generated query, which means
    the DB returns at most ``limit`` rows.  The +1 slack covers any single
    accompanying COUNT query that itself might return 1 row.

    If the implementation were to fetch all 50 rows and slice in Python, the
    counter would reach 50 and the assertion would fire.
    """

    def _run(self, coro):
        return _run(coro)

    def test_linked_session_pagination_does_not_materialize_all_rows(self):
        async def go():
            db = await aiosqlite.connect(":memory:")
            db.row_factory = aiosqlite.Row
            await _lsp_setup_db(db)

            fid = "pag-feature-1"
            await _lsp_seed_feature(db, fid)

            # Seed 50 sessions all linked to fid
            for i in range(50):
                sid = f"pag-sess-{i:03d}"
                await _lsp_seed_session(db, sid, started_at_offset=i)
                await _lsp_link_feature_session(db, fid, sid)
            await db.commit()

            # Track the maximum number of data rows fetched from the DB.
            # aiosqlite's db.execute is a synchronous method returning an async
            # context manager (ExecuteContextManager).  Our wrapper must also be
            # synchronous; we then patch fetchall on the yielded cursor object
            # inside an async context so we can count rows after the await.
            fetched_rows: list[int] = [0]
            _orig_execute = db.execute

            def _counting_execute(sql, *args, **kwargs):
                # Return the original context manager but intercept fetchall
                original_ctx = _orig_execute(sql, *args, **kwargs)

                class _WrappedCtx:
                    async def __aenter__(self_inner):
                        self_inner._cur = await original_ctx.__aenter__()
                        _orig_fetchall = self_inner._cur.fetchall

                        async def _counted_fetchall():
                            rows = list(await _orig_fetchall())
                            fetched_rows[0] += len(rows)
                            return rows

                        self_inner._cur.fetchall = _counted_fetchall  # type: ignore[method-assign]
                        return self_inner._cur

                    async def __aexit__(self_inner, *exc):
                        return await original_ctx.__aexit__(*exc)

                return _WrappedCtx()

            db.execute = _counting_execute  # type: ignore[assignment]

            try:
                repo = SqliteFeatureSessionRepository(db)
                query = LinkedSessionQuery(
                    feature_id=fid,
                    thread_expansion=ThreadExpansionMode.NONE,
                    sort_by="started_at",
                    sort_direction=SortDirection.DESC,
                    limit=5,
                    offset=0,
                )
                page = await repo.list_feature_session_refs(_LSP_PROJECT_ID, query)
                self.assertEqual(len(page.rows), 5,
                    "Should return exactly 5 rows for limit=5")
                # ≤ 6 because: up to 5 data rows (LIMIT=5) + 1 row from COUNT query
                self.assertLessEqual(
                    fetched_rows[0], 6,
                    f"Expected ≤ 6 total fetched rows (limit=5 + 1 for COUNT) "
                    f"but got {fetched_rows[0]}. "
                    "This indicates that all 50 rows were materialized in Python "
                    "before slicing — the SQL LIMIT is not being applied at the DB level.",
                )
            finally:
                db.execute = _orig_execute  # type: ignore[assignment]
                await db.close()

        self._run(go())


# ---------------------------------------------------------------------------
# Test 5 – Postgres parity scaffolding smoke
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("CCDASH_DB_BACKEND") != "postgres",
    reason=(
        "Postgres parity tests require a live database. "
        "Set CCDASH_DB_BACKEND=postgres and CCDASH_DATABASE_URL before running."
    ),
)
class TestPostgresParityScaffoldingSmoke(unittest.TestCase):
    """Scaffolding: confirm that Postgres repository classes exist and expose
    the same method surface as their SQLite counterparts.

    This is Phase 5 parity scaffolding; the tests are intentionally thin
    (hasattr checks only) until the asyncpg test fixture is in place.
    """

    def test_postgres_parity_scaffolding_smoke(self):
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        from backend.db.repositories.postgres.feature_sessions import PostgresFeatureSessionRepository
        from backend.db.repositories.feature_rollup import PostgresFeatureRollupRepository

        pairs = [
            (SqliteFeatureRepository, PostgresFeatureRepository, [
                "list_feature_cards",
                "count_feature_cards",
                "list_phase_summaries_for_features",
            ]),
            (SqliteFeatureSessionRepository, PostgresFeatureSessionRepository, [
                "list_feature_session_refs",
                "count_feature_session_refs",
                "list_session_family_refs",
            ]),
            (SqliteFeatureRollupRepository, PostgresFeatureRollupRepository, [
                "get_feature_session_rollups",
            ]),
        ]

        for sqlite_cls, pg_cls, methods in pairs:
            for method in methods:
                self.assertTrue(
                    hasattr(pg_cls, method),
                    f"{pg_cls.__name__} is missing method '{method}' "
                    f"that exists on {sqlite_cls.__name__}",
                )


if __name__ == "__main__":
    unittest.main()
