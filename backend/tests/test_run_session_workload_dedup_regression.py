"""D-001-shape dedup regression test at the run<->session correlation layer.

T2-007 (research-foundry-run-telemetry-v1, Phase 2), verifies AC-3. Modeled
directly on ``docs/project_plans/design-specs/f-w6-001-correlation-
overcounting.md`` Option A ("Deduplicate at the SQL level ... SELECT DISTINCT
session_id (or GROUP BY session_id) before summing token counts, ensuring
each session contributes exactly once").

That design spec deferred the fix at the session<->feature correlation layer
(``backend/routers/analytics.py::_session_usage_metrics``, F-W6-001). This
test reproduces the *exact same over-count shape* one layer down, at the
run<->session correlation layer added by T2-006
(``backend/db/repositories/entity_graph.py``): two ``research_runs`` rows
linked to the SAME session must contribute that session's token count to a
combined workload rollup exactly ONCE, never once per linked run.

Covers ``SqliteEntityLinkRepository.get_session_workload_for_runs``.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.db.repositories.entity_graph import SqliteEntityLinkRepository

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
    ended_at   TEXT DEFAULT '',
    tokens_in  INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0
);
"""

_RUN_A = "3f9c2a4e-2b6a-4a7d-8b1a-8f2c9d5e1a11"
_RUN_B = "7a1b3c5d-4e6f-4a8b-9c0d-1e2f3a4b5c6d"


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
    *,
    tokens_in: int,
    tokens_out: int,
) -> None:
    await db.execute(
        "INSERT INTO sessions (id, project_id, started_at, ended_at, tokens_in, tokens_out) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            session_id,
            project_id,
            _iso(started_at),
            _iso(ended_at) if ended_at else "",
            tokens_in,
            tokens_out,
        ),
    )
    await db.commit()


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


class TestRunSessionWorkloadDedup(unittest.IsolatedAsyncioTestCase):
    """AC-3 regression: two runs -> one session must contribute that
    session's token total exactly ONCE to a combined rollup, never once per
    linked run -- the exact D-001 over-count shape, at the run<->session
    layer.
    """

    async def test_two_runs_linked_to_same_session_count_tokens_once(self) -> None:
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            # A single session with a known, non-trivial token total.
            await _insert_session(
                db,
                "sess-shared",
                "proj-1",
                base,
                base + timedelta(minutes=30),
                tokens_in=1_000,
                tokens_out=500,
            )
            repo = SqliteEntityLinkRepository(db)

            run_a = _make_run(_RUN_A)
            run_b = _make_run(_RUN_B)
            result_a = await repo.correlate_research_run(run_a)
            result_b = await repo.correlate_research_run(run_b)

            # Sanity: both runs genuinely correlated to the SAME session --
            # this is the exact precondition the D-001 over-count bug needs.
            self.assertEqual(result_a["linked_session_ids"], ["sess-shared"])
            self.assertEqual(result_b["linked_session_ids"], ["sess-shared"])

            # Precondition: TWO distinct link rows exist for the one session
            # (mirrors test_two_runs_sharing_one_session_produce_two_link_rows_not_one
            # in test_entity_graph_research_run_correlation.py). A naive
            # join-then-sum over these rows would double the session's
            # tokens (2 x 1500 = 3000). The rollup under test must not do
            # that.
            async with db.execute(
                "SELECT COUNT(*) FROM entity_links WHERE target_id = 'sess-shared'"
            ) as cur:
                link_row_count = (await cur.fetchone())[0]
            self.assertEqual(link_row_count, 2)

            rollup = await repo.get_session_workload_for_runs([_RUN_A, _RUN_B])

            # The session's own stored total (1000 + 500 = 1500) counted
            # exactly once -- not 3000 (once per linked run).
            self.assertEqual(rollup["total_tokens"], 1_500)
            self.assertEqual(rollup["session_count"], 1)
            self.assertEqual(rollup["session_ids"], ["sess-shared"])
        finally:
            await db.close()

    async def test_two_distinct_sessions_each_counted_once(self) -> None:
        """Contrast case: two runs -> two DIFFERENT sessions must both be
        summed (dedup must not under-count either) -- proves the fix dedupes
        by session identity, not by collapsing everything into one row.
        """
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(
                db,
                "sess-a",
                "proj-1",
                base,
                base + timedelta(minutes=10),
                tokens_in=100,
                tokens_out=50,
            )
            await _insert_session(
                db,
                "sess-b",
                "proj-1",
                base,
                base + timedelta(minutes=10),
                tokens_in=200,
                tokens_out=75,
            )
            repo = SqliteEntityLinkRepository(db)
            await repo.link_research_run_sessions(_make_run(_RUN_A), ["sess-a"])
            await repo.link_research_run_sessions(_make_run(_RUN_B), ["sess-b"])

            rollup = await repo.get_session_workload_for_runs([_RUN_A, _RUN_B])

            self.assertEqual(rollup["total_tokens"], 425)  # (100+50) + (200+75), each once
            self.assertEqual(rollup["session_count"], 2)
            self.assertEqual(sorted(rollup["session_ids"]), ["sess-a", "sess-b"])
        finally:
            await db.close()

    async def test_relinking_same_run_to_same_session_still_counts_once(self) -> None:
        """A run re-linked to the same session (idempotent upsert, T2-006)
        must not create a second contributing row either.
        """
        db = await _make_db()
        try:
            base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
            await _insert_session(
                db,
                "sess-x",
                "proj-1",
                base,
                base + timedelta(minutes=10),
                tokens_in=10,
                tokens_out=5,
            )
            repo = SqliteEntityLinkRepository(db)
            run = _make_run(_RUN_A)
            await repo.link_research_run_sessions(run, ["sess-x"])
            await repo.link_research_run_sessions(run, ["sess-x"])  # relink, idempotent

            rollup = await repo.get_session_workload_for_runs([_RUN_A])
            self.assertEqual(rollup["total_tokens"], 15)
            self.assertEqual(rollup["session_count"], 1)
        finally:
            await db.close()

    async def test_run_with_no_linked_sessions_yields_explicit_zero_not_default(self) -> None:
        """AC-3 resilience state: zero linked sessions -> explicit
        session_count=0 / session_ids=[] / total_tokens=0 -- a genuine zero
        workload, distinguishable (via session_count/session_ids) from a
        lookup failure masquerading as a coincidental zero.
        """
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            rollup = await repo.get_session_workload_for_runs([_RUN_A])
            self.assertEqual(
                rollup, {"total_tokens": 0, "session_count": 0, "session_ids": []}
            )
        finally:
            await db.close()

    async def test_empty_run_ids_yields_explicit_zero(self) -> None:
        db = await _make_db()
        try:
            repo = SqliteEntityLinkRepository(db)
            rollup = await repo.get_session_workload_for_runs([])
            self.assertEqual(
                rollup, {"total_tokens": 0, "session_count": 0, "session_ids": []}
            )
        finally:
            await db.close()


if __name__ == "__main__":
    unittest.main()
