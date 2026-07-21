"""Postgres coverage for ``get_session_workload_for_runs`` (Phase 2 reviewer fix #3).

Prior to this fix, ``PostgresEntityLinkRepository`` exposed
``find_candidate_sessions_for_run``/``link_research_run_sessions``/
``correlate_research_run``/``get_linked_session_ids_for_run`` but NOT
``get_session_workload_for_runs`` — any Postgres-backed caller of that method
(the D-001-shape dedup rollup at the run<->session correlation layer, T2-007)
raised ``AttributeError``. This file adds two tiers of coverage, mirroring
``test_run_session_workload_dedup_regression.py``'s SQLite scenarios exactly:

1. ``PostgresGetSessionWorkloadStructuralTests`` (always runs, no live DB) —
   a lightweight mock ``asyncpg``-shaped connection proves (a) the method now
   exists and is callable (the literal AttributeError regression), (b) the
   empty-``run_ids`` / zero-workload resilience states never touch the DB,
   and (c) the emitted SQL text places ``SELECT DISTINCT`` strictly BEFORE
   the ``SUM(`` aggregate — the D-001 Option A dedup-before-sum structural
   guard, verified by string inspection of the actual production SQL rather
   than a reimplementation of its semantics.

2. ``LivePGRunSessionWorkloadDedupTests`` (skipped unless
   ``CCDASH_DATABASE_URL`` is set) — the full behavioral reproduction of the
   SQLite regression test's four scenarios against a real Postgres instance:
   two runs linked to one session count that session's tokens once; two runs
   linked to two distinct sessions both get summed; re-linking a run to the
   same session doesn't double-count; zero linked sessions yields the
   explicit AC-3 zero-state.

Run (mock tier only, no PG required):
    backend/.venv/bin/python -m pytest backend/tests/test_pg_run_session_workload_dedup_regression.py -v

Run (including the live-PG tier):
    CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash \\
        backend/.venv/bin/python -m pytest backend/tests/test_pg_run_session_workload_dedup_regression.py -v
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from backend.db.repositories.postgres.entity_graph import PostgresEntityLinkRepository

_PG_URL = os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres get_session_workload_for_runs "
    "test requires a running Postgres instance (e.g. via docker compose up --profile postgres)."
)

_RUN_A = "3f9c2a4e-2b6a-4a7d-8b1a-8f2c9d5e1a11"
_RUN_B = "7a1b3c5d-4e6f-4a8b-9c0d-1e2f3a4b5c6d"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _make_run(run_id: str, **overrides) -> dict:
    base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
    run = {
        "run_id": run_id,
        "project_id": "proj-1",
        "rf_run_id": f"rf-{run_id[:8]}",
        "intent_id": "intent_research_foundry_search_router",
        "task_node_id": "task-node-abc",
        "rf_project": "research-foundry",
        "first_event_at": _iso(base),
        "last_event_at": _iso(base + timedelta(minutes=5)),
    }
    run.update(overrides)
    return run


# ---------------------------------------------------------------------------
# 1. Structural / mock tier — always runs, no live Postgres required.
# ---------------------------------------------------------------------------


class PostgresGetSessionWorkloadStructuralTests(unittest.IsolatedAsyncioTestCase):
    """AttributeError regression guard + dedup-before-sum SQL structure check."""

    async def test_method_exists_and_is_callable(self) -> None:
        """The literal reviewer-flagged bug: calling this on the Postgres repo
        used to raise AttributeError because the method didn't exist at all.
        """
        db = MagicMock()
        db.fetchrow = AsyncMock(return_value={"total_tokens": 0, "session_count": 0})
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresEntityLinkRepository(db)

        result = await repo.get_session_workload_for_runs([_RUN_A])  # must not raise

        self.assertEqual(result["total_tokens"], 0)
        self.assertEqual(result["session_count"], 0)
        self.assertEqual(result["session_ids"], [])

    async def test_empty_run_ids_short_circuits_without_touching_db(self) -> None:
        db = MagicMock()
        db.fetchrow = AsyncMock()
        db.fetch = AsyncMock()
        repo = PostgresEntityLinkRepository(db)

        result = await repo.get_session_workload_for_runs([])

        self.assertEqual(result, {"total_tokens": 0, "session_count": 0, "session_ids": []})
        db.fetchrow.assert_not_called()
        db.fetch.assert_not_called()

    async def test_sql_aggregates_over_a_distinct_derived_table_not_the_raw_join(self) -> None:
        """D-001 Option A structural guard: the outer ``SUM(``/``COUNT(``
        aggregate must run over a ``SELECT DISTINCT`` derived table (aliased
        ``distinct_sessions``), never directly over the raw
        ``entity_links JOIN sessions`` rows -- a regression back to a naive
        join-then-sum would double-count a session linked to more than one
        run, exactly the D-001/F-W6-001 over-count shape this method exists
        to prevent.

        SQL syntax dictates the outer ``SELECT SUM(...)`` list is textually
        BEFORE its own ``FROM (...)`` clause, so the assertion checks nesting
        order (``FROM (`` -> ``SELECT DISTINCT`` -> ``AS distinct_sessions``)
        rather than raw ``SUM`` vs. ``DISTINCT`` string-index order.
        """
        db = MagicMock()
        db.fetchrow = AsyncMock(return_value={"total_tokens": 0, "session_count": 0})
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresEntityLinkRepository(db)

        await repo.get_session_workload_for_runs([_RUN_A, _RUN_B])

        totals_sql: str = db.fetchrow.call_args[0][0]
        self.assertIn("SUM(", totals_sql)
        self.assertIn("SELECT DISTINCT", totals_sql)
        self.assertIn("AS distinct_sessions", totals_sql)

        idx_sum = totals_sql.index("SUM(")
        idx_from = totals_sql.index("FROM (")
        idx_distinct = totals_sql.index("SELECT DISTINCT")
        idx_alias = totals_sql.index("AS distinct_sessions")

        self.assertLess(idx_sum, idx_from, "SUM must be in the outer SELECT list, before its own FROM clause")
        self.assertLess(idx_from, idx_distinct, "the derived-table subquery must open before SELECT DISTINCT appears")
        self.assertLess(idx_distinct, idx_alias, "SELECT DISTINCT must belong to the distinct_sessions derived table")

    async def test_run_ids_bound_as_array_parameter(self) -> None:
        """asyncpg's ``ANY($n::text[])`` array-membership form is used (not a
        hand-built placeholder list) -- the run_ids list is passed through as
        a single bind parameter.
        """
        db = MagicMock()
        db.fetchrow = AsyncMock(return_value={"total_tokens": 0, "session_count": 0})
        db.fetch = AsyncMock(return_value=[])
        repo = PostgresEntityLinkRepository(db)

        await repo.get_session_workload_for_runs([_RUN_A, _RUN_B], workspace_id="ws-1")

        totals_sql, *totals_args = db.fetchrow.call_args[0]
        self.assertIn("ANY(", totals_sql)
        self.assertIn([_RUN_A, _RUN_B], totals_args)
        self.assertEqual(totals_args[0], "ws-1")


# ---------------------------------------------------------------------------
# 2. Live-Postgres tier — PG-gated, mirrors the SQLite regression exactly.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LivePGRunSessionWorkloadDedupTests(unittest.IsolatedAsyncioTestCase):
    """Live Postgres reproduction of test_run_session_workload_dedup_regression.py.

    Run against compose PG:
        CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash \\
            backend/.venv/bin/python -m pytest \\
            backend/tests/test_pg_run_session_workload_dedup_regression.py \\
            -k LivePGRunSessionWorkloadDedupTests -v
    """

    async def asyncSetUp(self) -> None:
        import asyncpg

        from backend.db.postgres_migrations import run_migrations

        self._pool = await asyncpg.create_pool(_PG_URL)
        await run_migrations(self._pool)
        self._suffix = uuid.uuid4().hex[:8]
        self._session_ids: list[str] = []
        self._run_ids: list[str] = []

    async def asyncTearDown(self) -> None:
        async with self._pool.acquire() as conn:
            if self._run_ids:
                await conn.execute(
                    "DELETE FROM entity_links WHERE source_id = ANY($1::text[])",
                    self._run_ids,
                )
            if self._session_ids:
                await conn.execute(
                    "DELETE FROM sessions WHERE id = ANY($1::text[])",
                    self._session_ids,
                )
        await self._pool.close()

    async def _insert_session(
        self,
        session_id: str,
        *,
        started_at: datetime,
        ended_at: datetime,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        now = _iso(datetime.now(timezone.utc))
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO sessions
                       (id, project_id, started_at, ended_at, tokens_in, tokens_out,
                        created_at, updated_at, source_file)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                session_id,
                f"proj-{self._suffix}",
                _iso(started_at),
                _iso(ended_at),
                tokens_in,
                tokens_out,
                now,
                now,
                f"{session_id}.jsonl",
            )
        self._session_ids.append(session_id)

    def _run(self, suffix: str, **overrides) -> dict:
        run_id = str(uuid.uuid4())
        self._run_ids.append(run_id)
        run = _make_run(run_id, project_id=f"proj-{self._suffix}", rf_run_id=f"rf-{suffix}")
        run.update(overrides)
        return run

    async def test_two_runs_linked_to_same_session_count_tokens_once(self) -> None:
        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)

            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            session_id = f"sess-shared-{self._suffix}"
            await self._insert_session(
                session_id,
                started_at=base,
                ended_at=base + timedelta(minutes=30),
                tokens_in=1_000,
                tokens_out=500,
            )

            run_a = self._run("a")
            run_b = self._run("b")
            result_a = await repo.correlate_research_run(run_a)
            result_b = await repo.correlate_research_run(run_b)

            self.assertEqual(result_a["linked_session_ids"], [session_id])
            self.assertEqual(result_b["linked_session_ids"], [session_id])

            rollup = await repo.get_session_workload_for_runs(
                [run_a["run_id"], run_b["run_id"]]
            )
            self.assertEqual(rollup["total_tokens"], 1_500)
            self.assertEqual(rollup["session_count"], 1)
            self.assertEqual(rollup["session_ids"], [session_id])

    async def test_two_distinct_sessions_each_counted_once(self) -> None:
        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)

            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            sess_a = f"sess-a-{self._suffix}"
            sess_b = f"sess-b-{self._suffix}"
            await self._insert_session(
                sess_a, started_at=base, ended_at=base + timedelta(minutes=10),
                tokens_in=100, tokens_out=50,
            )
            await self._insert_session(
                sess_b, started_at=base, ended_at=base + timedelta(minutes=10),
                tokens_in=200, tokens_out=75,
            )

            run_a = self._run("a")
            run_b = self._run("b")
            await repo.link_research_run_sessions(run_a, [sess_a])
            await repo.link_research_run_sessions(run_b, [sess_b])

            rollup = await repo.get_session_workload_for_runs(
                [run_a["run_id"], run_b["run_id"]]
            )
            self.assertEqual(rollup["total_tokens"], 425)
            self.assertEqual(rollup["session_count"], 2)
            self.assertEqual(sorted(rollup["session_ids"]), sorted([sess_a, sess_b]))

    async def test_relinking_same_run_to_same_session_still_counts_once(self) -> None:
        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)

            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            sess_x = f"sess-x-{self._suffix}"
            await self._insert_session(
                sess_x, started_at=base, ended_at=base + timedelta(minutes=10),
                tokens_in=10, tokens_out=5,
            )

            run = self._run("x")
            await repo.link_research_run_sessions(run, [sess_x])
            await repo.link_research_run_sessions(run, [sess_x])  # relink, idempotent

            rollup = await repo.get_session_workload_for_runs([run["run_id"]])
            self.assertEqual(rollup["total_tokens"], 15)
            self.assertEqual(rollup["session_count"], 1)

    async def test_run_with_no_linked_sessions_yields_explicit_zero(self) -> None:
        async with self._pool.acquire() as conn:
            repo = PostgresEntityLinkRepository(conn)
            run = self._run("none")
            rollup = await repo.get_session_workload_for_runs([run["run_id"]])
            self.assertEqual(
                rollup, {"total_tokens": 0, "session_count": 0, "session_ids": []}
            )


if __name__ == "__main__":
    unittest.main()
