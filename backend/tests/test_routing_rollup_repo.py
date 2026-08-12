"""Migration governance + ADR-007 direct-count tests for ``routing_rollup`` (T2-004).

``routing_rollup`` (``proof-to-routing-loop-v1`` Phase 2, v43) is the
``(project_id, source_skill_name, model)``-keyed rollup persisted by
``backend/db/repositories/routing_rollup.py``, to be populated by the Phase 3
``RoutingRollupQueryService`` (not yet built as of this module). This module
is the Phase 2 exit-gate coverage for T2-004:

1. Dual-DDL column parity (ADR-007 / ``migration_governance.py``) --
   ``routing_rollup`` must be registered in both backend migration-table
   getters and carry a structurally identical column set (after canonical
   type normalization) across SQLite and Postgres, with ZERO
   ``COLUMN_PARITY_DRIFT_ALLOWLIST`` entries (parity-clean by construction --
   every column uses an identical literal type token in both dialects, per
   T2-002's design notes -- mirroring the ``aar_reviews``/``research_runs``/
   ``rf_events`` precedent exactly).
2. ADR-007 direct-count assertion: every intended write actually lands a row,
   upsert-by-``(project_id, source_skill_name, model)`` never duplicates, and
   a change to any non-key column (or to ``window_start``/``window_end``, the
   ordinary UPDATE-in-place columns) updates the existing row in place rather
   than growing the table.

HARD INVARIANT: zero LLM/model calls anywhere on this path -- every fixture
below is a plain dict; no model/agent client is imported. This module also
never computes a rollup metric or a ``task_class``/``provider`` value -- rows
are constructed as literal, already-shaped dicts, exactly as Phase 3's
compute service is documented to hand them to the repository.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_repo.py -v
"""
from __future__ import annotations

import unittest
from typing import Any

import aiosqlite

from backend.application.services.agent_queries.routing_feedback_contract import (
    CONTRACT_VERSION,
    MAPPING_VERSION,
    TAXONOMY_VERSION,
)
from backend.db.migration_governance import (
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    column_parity_diff,
    get_column_parity_diff_all,
    get_enterprise_only_postgres_tables,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
)
from backend.db.repositories.routing_rollup import (
    ROUTING_ROLLUP_COLUMNS,
    PostgresRoutingRollupRepository,
    SqliteRoutingRollupRepository,
)
from backend.db.sqlite_migrations import run_migrations


# ── 1. Migration governance: registration + column parity ──────────────────


class RoutingRollupMigrationGovernanceTests(unittest.TestCase):
    """routing_rollup registration + static DDL column-parity assertions (T2-002/T2-004)."""

    def test_routing_rollup_registered_in_sqlite_migration_tables(self) -> None:
        self.assertIn("routing_rollup", get_sqlite_migration_tables())

    def test_routing_rollup_registered_in_postgres_migration_tables(self) -> None:
        self.assertIn("routing_rollup", get_postgres_migration_tables())

    def test_routing_rollup_is_not_enterprise_only(self) -> None:
        """routing_rollup is a shared table -- it must exist in SQLite too, never enterprise-only."""
        self.assertNotIn("routing_rollup", get_enterprise_only_postgres_tables())

    def test_routing_rollup_column_parity_diff_is_empty(self) -> None:
        """routing_rollup is parity-clean by construction -- zero structural drift.

        Every column uses an identical literal type token in both dialects
        (TEXT for strings/ISO-8601 timestamps, INTEGER for sample_count/
        eligible_for_adjustment -- deliberately NOT Postgres BOOLEAN -- and
        REAL for the four nullable metric columns -- deliberately NOT
        Postgres DOUBLE PRECISION), so no cross-backend type-normalization
        category is even needed for this table.
        """
        diff = column_parity_diff("routing_rollup")
        self.assertEqual(
            diff, {}, msg=f"routing_rollup must be column-parity-clean across backends; found drift: {diff}",
        )

    def test_routing_rollup_included_in_global_parity_sweep(self) -> None:
        merged_diff = get_column_parity_diff_all()
        self.assertNotIn(
            "routing_rollup", merged_diff,
            msg=f"routing_rollup introduced drift in the global parity sweep: {merged_diff.get('routing_rollup')}",
        )

    def test_routing_rollup_has_zero_allowlist_entries(self) -> None:
        """routing_rollup must NOT appear in COLUMN_PARITY_DRIFT_ALLOWLIST at all.

        Mirrors the rf_events/research_runs/aar_reviews precedent: because
        routing_rollup is parity-clean by construction, allowlisting any
        (routing_rollup, column) pair would silently mask a real future
        regression.
        """
        entries = {pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] == "routing_rollup"}
        self.assertEqual(
            entries, set(),
            msg=f"routing_rollup must have zero COLUMN_PARITY_DRIFT_ALLOWLIST entries; found: {sorted(entries)}",
        )

    def test_routing_rollup_column_set_matches_repository_contract(self) -> None:
        """Every column the repository writes (ROUTING_ROLLUP_COLUMNS) must exist in both DDLs."""
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns

        sqlite_cols = set(_parse_table_columns(_backend_table_blocks(sqlite_migrations)["routing_rollup"]))
        pg_cols = set(_parse_table_columns(_backend_table_blocks(postgres_migrations)["routing_rollup"]))

        for col in ROUTING_ROLLUP_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"ROUTING_ROLLUP_COLUMNS entry '{col}' missing from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"ROUTING_ROLLUP_COLUMNS entry '{col}' missing from Postgres DDL")

    def test_routing_rollup_primary_key_matches_natural_grain(self) -> None:
        """PRIMARY KEY must be (project_id, source_skill_name, model, task_class) in both
        DDLs -- schema v54 added ``task_class`` so a role-split skill's implementation and
        orchestration rows no longer collide. It must still never be keyed
        (task_class, model) first, and must never include window_start/window_end (those
        are UPDATE-in-place window columns; keying on them would grow the table
        unboundedly)."""
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import _backend_table_blocks

        for module in (sqlite_migrations, postgres_migrations):
            body = _backend_table_blocks(module)["routing_rollup"]
            self.assertIn(
                "PRIMARY KEY (project_id, source_skill_name, model, task_class)", body
            )
            self.assertNotIn("PRIMARY KEY (task_class", body)
            pk_clause = body[body.index("PRIMARY KEY ("):]
            self.assertNotIn("window_start", pk_clause)
            self.assertNotIn("window_end", pk_clause)


# ── 2. Row fixture -- plain dicts, ROUTING_ROLLUP_COLUMNS-shaped ────────────


def _make_row(
    *,
    project_id: str = "project-1",
    source_skill_name: str = "planning",
    model: str = "claude-sonnet-5",
    window_start: str = "2026-07-24T00:00:00+00:00",
    window_end: str = "2026-07-31T00:00:00+00:00",
    task_class: str = "planning",
    provider: str = "anthropic",
    sample_count: int = 12,
    success_rate: float | None = 0.9,
    cost_index: float | None = 0.42,
    cost_coverage_fraction: float | None = 0.94,
    regression_rate: float | None = 0.05,
    effort_tier: str | None = "high",
    effort_tier_source: str | None = "codex_payload_effort",
    authoritative_effort_fraction: float | None = 0.75,
    confidence: float | None = 0.8,
    eligible_for_adjustment: int = 1,
    freshness_ts: str = "2026-07-31T00:00:00+00:00",
    contract_version: str = CONTRACT_VERSION,
    taxonomy_version: str = TAXONOMY_VERSION,
    mapping_version: str = MAPPING_VERSION,
) -> dict[str, Any]:
    """Return a ROUTING_ROLLUP_COLUMNS-shaped dict, exactly the row shape Phase
    3's compute service is documented to hand this repository (no DTO/builder
    helper exists here by design -- see the module docstring in
    ``routing_rollup.py``)."""
    row = {
        "project_id": project_id,
        "source_skill_name": source_skill_name,
        "model": model,
        "window_start": window_start,
        "window_end": window_end,
        "task_class": task_class,
        "provider": provider,
        "sample_count": sample_count,
        "success_rate": success_rate,
        "cost_index": cost_index,
        "cost_coverage_fraction": cost_coverage_fraction,
        "regression_rate": regression_rate,
        "effort_tier": effort_tier,
        "effort_tier_source": effort_tier_source,
        "authoritative_effort_fraction": authoritative_effort_fraction,
        "confidence": confidence,
        "eligible_for_adjustment": eligible_for_adjustment,
        "freshness_ts": freshness_ts,
        "contract_version": contract_version,
        "taxonomy_version": taxonomy_version,
        "mapping_version": mapping_version,
    }
    assert set(row) == set(ROUTING_ROLLUP_COLUMNS)
    return row


# ── 3. ADR-007 direct-count assertion + upsert idempotency (SQLite) ────────


class SqliteRoutingRollupDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: write N rows, assert direct COUNT(*) == N; upsert stays idempotent."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteRoutingRollupRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _direct_count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM routing_rollup")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_direct_count_matches_writes(self) -> None:
        """Write N distinct (project_id, source_skill_name, model) rows; assert COUNT(*) == N."""
        n = 5
        for i in range(n):
            await self.repo.upsert(_make_row(source_skill_name=f"skill-{i}", model=f"model-{i}"))

        self.assertEqual(await self._direct_count(), n)
        self.assertEqual(await self.repo.count_by_project("project-1"), n)

    async def test_upsert_idempotency_keeps_count_stable_and_updates_row(self) -> None:
        """Re-upserting the same (project_id, source_skill_name, model) key twice must not
        duplicate -- and the resulting row must reflect the latest write, including a new
        window_start/window_end (the ordinary, UPDATE-in-place columns)."""
        row_first = _make_row(sample_count=10, success_rate=0.5, window_end="2026-07-24T06:00:00+00:00")
        await self.repo.upsert(row_first)
        self.assertEqual(await self._direct_count(), 1)

        row_second = _make_row(sample_count=25, success_rate=0.95, window_end="2026-07-31T00:00:00+00:00")
        await self.repo.upsert(row_second)

        self.assertEqual(await self._direct_count(), 1, "upsert of the same dedup key must not duplicate")
        rows = await self.repo.get_by_project("project-1")
        self.assertEqual(len(rows), 1)
        stored = rows[0]
        self.assertEqual(stored["sample_count"], 25, "the row must reflect the latest write")
        self.assertEqual(stored["success_rate"], 0.95)
        self.assertEqual(stored["window_end"], "2026-07-31T00:00:00+00:00")

    async def test_upsert_many_writes_every_row(self) -> None:
        rows = [_make_row(source_skill_name=name, model="claude-sonnet-5") for name in ("a", "b", "c", "d")]
        written = await self.repo.upsert_many(rows)
        self.assertEqual(written, 4)
        self.assertEqual(await self._direct_count(), 4)

    async def test_distinct_grain_keys_never_collapse(self) -> None:
        """Varying any one of the three key columns must produce a distinct row --
        the natural key is the full (project_id, source_skill_name, model) tuple,
        never a coarser (task_class, model) pairing."""
        # Same project + skill, different model.
        await self.repo.upsert(_make_row(source_skill_name="planning", model="claude-sonnet-5"))
        await self.repo.upsert(_make_row(source_skill_name="planning", model="claude-opus-5"))
        # Same project + model, different skill (even if task_class collapses the same).
        await self.repo.upsert(_make_row(source_skill_name="dev-execution", model="claude-sonnet-5", task_class="planning"))
        # Different project entirely, identical skill/model to the first row.
        await self.repo.upsert(_make_row(project_id="project-2", source_skill_name="planning", model="claude-sonnet-5"))

        self.assertEqual(await self._direct_count(), 4)

    async def test_get_by_project_scopes_correctly(self) -> None:
        await self.repo.upsert(_make_row(project_id="project-a", source_skill_name="skill-a"))
        await self.repo.upsert(_make_row(project_id="project-b", source_skill_name="skill-b"))

        rows_a = await self.repo.get_by_project("project-a")
        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["source_skill_name"], "skill-a")
        self.assertEqual(await self.repo.count_by_project("project-b"), 1)
        self.assertEqual(await self.repo.count_by_project("project-nonexistent"), 0)

    async def test_get_all_returns_rows_across_projects(self) -> None:
        await self.repo.upsert(_make_row(project_id="project-a", source_skill_name="skill-a"))
        await self.repo.upsert(_make_row(project_id="project-b", source_skill_name="skill-b"))

        rows = await self.repo.get_all()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(r["project_id"] for r in rows), ["project-a", "project-b"],
        )

    async def test_nullable_metric_columns_accept_none(self) -> None:
        """A coverage-only/_unclassified row may have no meaningful metric value (D5)."""
        row = _make_row(
            success_rate=None, cost_index=None, cost_coverage_fraction=None,
            regression_rate=None, confidence=None,
            eligible_for_adjustment=0, task_class="_unclassified",
        )
        await self.repo.upsert(row)

        stored = (await self.repo.get_by_project("project-1"))[0]
        self.assertIsNone(stored["success_rate"])
        self.assertIsNone(stored["cost_index"])
        self.assertIsNone(stored["cost_coverage_fraction"])
        self.assertIsNone(stored["regression_rate"])
        self.assertIsNone(stored["confidence"])
        self.assertEqual(stored["eligible_for_adjustment"], 0)

    async def test_cost_coverage_fraction_round_trips_partial_value(self) -> None:
        """v47: a persisted PARTIAL-coverage key (e.g. 2 of 50 sessions carried
        cost attribution) must read back with its real fraction, not a
        fabricated/rounded value -- direct repository round-trip companion
        to the client_v1 round-trip in test_client_v1_routing_rollup.py."""
        row = _make_row(cost_coverage_fraction=2 / 50)
        await self.repo.upsert(row)

        stored = (await self.repo.get_by_project("project-1"))[0]
        self.assertAlmostEqual(stored["cost_coverage_fraction"], 2 / 50)


# ── 4. ADR-007 direct-count assertion: Postgres (fake asyncpg-shaped conn) ──


class _FakeRoutingRollupPgConnection:
    """Minimal asyncpg.Connection fake replicating the real ON CONFLICT DO UPDATE
    full-overwrite semantics documented in
    ``backend/db/repositories/routing_rollup.py`` (every non-key column,
    including ``window_start``/``window_end``, is replaced wholesale by the
    latest write -- unlike ``research_runs``, there is no aggregation here),
    so this test exercises the same write-path contract as the SQLite tests
    above without a live Postgres.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def execute(self, query: str, *args) -> str:
        if not query.strip().upper().startswith("INSERT"):
            raise NotImplementedError(f"unsupported query in fake pg connection: {query}")
        row = dict(zip(ROUTING_ROLLUP_COLUMNS, args))
        key = (row["project_id"], row["source_skill_name"], row["model"])
        self._store[key] = row
        return "INSERT 0 1"

    async def fetchval(self, query: str, *args):
        if query.strip().upper().startswith("SELECT COUNT(*) FROM ROUTING_ROLLUP"):
            (project_id,) = args
            return sum(1 for key in self._store if key[0] == project_id)
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")

    async def fetch(self, query: str, *args):
        if query.strip().upper().startswith("SELECT * FROM ROUTING_ROLLUP WHERE PROJECT_ID"):
            (project_id,) = args[:1]
            return [row for key, row in self._store.items() if key[0] == project_id]
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")


class PostgresRoutingRollupFakeConnectionDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: upsert N distinct keys, assert SELECT COUNT(*) == N (Postgres, fake conn)."""

    async def asyncSetUp(self) -> None:
        self.conn = _FakeRoutingRollupPgConnection()
        self.repo = PostgresRoutingRollupRepository(self.conn)

    async def test_distinct_keys_direct_count_matches(self) -> None:
        n = 5
        for i in range(n):
            await self.repo.upsert(_make_row(source_skill_name=f"skill-{i}", model=f"model-{i}"))
        self.assertEqual(await self.repo.count_by_project("project-1"), n)

    async def test_same_key_upsert_overwrites_not_duplicates(self) -> None:
        for sample_count in (1, 2, 3):
            await self.repo.upsert(_make_row(sample_count=sample_count))
        self.assertEqual(await self.repo.count_by_project("project-1"), 1)

        rows = await self.repo.get_by_project("project-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sample_count"], 3, "the latest write must win, not an aggregate")


if __name__ == "__main__":
    unittest.main()
