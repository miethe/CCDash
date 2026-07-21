"""Migration governance + UUID-minting regression tests for ``research_runs`` (T2-001).

``research_runs`` (research-foundry-run-telemetry v1, Phase 2, v41) is the
derived rollup table folded from the raw ``rf_events`` log (T1-001). This
module is the Phase 2 exit-gate coverage for T2-001's two contracts:

1. Dual-DDL column parity (ADR-007 / ``migration_governance.py``) —
   ``research_runs`` must be registered in both backend migration-table
   getters and carry a structurally identical column set (after canonical
   type normalization) across SQLite and Postgres, with ZERO
   ``COLUMN_PARITY_DRIFT_ALLOWLIST`` entries (parity-clean by construction,
   mirroring ``rf_events``'s precedent exactly).

2. The T2-001 acceptance criterion: "Rollup derivable from seeded rf_events
   fixtures with zero live RF traffic; RF's non-UUID ids never become a
   primary/join key." Covered end-to-end against a real in-memory SQLite DB
   (``run_migrations``) plus a fake-asyncpg-shaped Postgres connection
   (mirrors ``test_rf_events_migration_governance.py``'s established
   convention — no live Postgres guaranteed in the standard CI runner).

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_research_runs_migration_governance.py -v
"""
from __future__ import annotations

import os
import unittest

import aiosqlite

from backend.db.migration_governance import (
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    column_parity_diff,
    get_column_parity_diff_all,
    get_enterprise_only_postgres_tables,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
)
from backend.db.repositories.research_runs import (
    RESEARCH_RUNS_COLUMNS,
    PostgresResearchRunsRepository,
    SqliteResearchRunsRepository,
    build_research_run_delta,
    is_uuid4,
    resolve_run_id,
)
from backend.db.repositories.rf_events import RF_EVENTS_COLUMNS, SqliteRfEventsRepository
from backend.db.sqlite_migrations import run_migrations


def _make_rf_event_row(
    event_id: str,
    run_id: str | None,
    *,
    project_id: str = "proj-1",
    workspace_id: str = "default-local",
    event_timestamp: str = "2026-07-21T10:00:00.000000Z",
    **extra,
) -> dict:
    """Minimal valid ``rf_events`` row, matching RF_EVENTS_COLUMNS shape."""
    row = {
        "event_id": event_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "event_timestamp": event_timestamp,
        "rf_project": "research-foundry",
        "run_id": run_id,
        "raw_payload_json": "{}",
    }
    row.update(extra)
    return row


# ── 1. Migration governance: registration + column parity ──────────────────


class ResearchRunsMigrationGovernanceTests(unittest.TestCase):
    """research_runs registration + static DDL column-parity assertions (T2-001/T2-002)."""

    def test_research_runs_registered_in_sqlite_migration_tables(self) -> None:
        self.assertIn("research_runs", get_sqlite_migration_tables())

    def test_research_runs_registered_in_postgres_migration_tables(self) -> None:
        self.assertIn("research_runs", get_postgres_migration_tables())

    def test_research_runs_is_not_enterprise_only(self) -> None:
        """research_runs is a shared table — it must exist in SQLite too, never enterprise-only."""
        self.assertNotIn("research_runs", get_enterprise_only_postgres_tables())

    def test_research_runs_column_parity_diff_is_empty(self) -> None:
        """research_runs is parity-clean by construction — zero structural drift.

        Mirrors the AC-2 exit-gate assertion already proven for rf_events:
        identical column set, type, nullability, and default across both DDL
        files (modulo the canonical type-normalization mapping which already
        covers INTEGER/BOOLEAN, TEXT/JSONB, REAL/DOUBLE PRECISION, and the
        timestamp_default_expression nullability case for created_at/updated_at).
        """
        diff = column_parity_diff("research_runs")
        self.assertEqual(
            diff,
            {},
            msg=f"research_runs must be column-parity-clean across backends; found drift: {diff}",
        )

    def test_research_runs_included_in_global_parity_sweep(self) -> None:
        merged_diff = get_column_parity_diff_all()
        self.assertNotIn(
            "research_runs",
            merged_diff,
            msg=f"research_runs introduced drift in the global parity sweep: {merged_diff.get('research_runs')}",
        )

    def test_research_runs_has_zero_allowlist_entries(self) -> None:
        """research_runs must NOT appear in COLUMN_PARITY_DRIFT_ALLOWLIST at all.

        Mirrors the rf_events precedent: because research_runs is
        parity-clean by construction, allowlisting any (research_runs,
        column) pair would silently mask a real future regression.
        """
        entries = {pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] == "research_runs"}
        self.assertEqual(
            entries,
            set(),
            msg=(
                "research_runs must have zero COLUMN_PARITY_DRIFT_ALLOWLIST entries "
                f"(it is parity-clean by construction); found: {sorted(entries)}"
            ),
        )

    def test_research_runs_column_set_matches_repository_contract(self) -> None:
        """Every column the repository writes (RESEARCH_RUNS_COLUMNS) must exist in both DDLs."""
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns

        sqlite_cols = set(_parse_table_columns(_backend_table_blocks(sqlite_migrations)["research_runs"]))
        pg_cols = set(_parse_table_columns(_backend_table_blocks(postgres_migrations)["research_runs"]))

        for col in RESEARCH_RUNS_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"RESEARCH_RUNS_COLUMNS entry '{col}' missing from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"RESEARCH_RUNS_COLUMNS entry '{col}' missing from Postgres DDL")


# ── 2. UUID minting contract (D2, FR-6) — pure function tests ──────────────


class UuidMintingTests(unittest.TestCase):
    """resolve_run_id / is_uuid4 — RF's non-UUID ids never become a join key."""

    def test_is_uuid4_accepts_canonical_uuid4(self) -> None:
        self.assertTrue(is_uuid4("11111111-1111-4111-8111-111111111111"))

    def test_is_uuid4_rejects_semantic_slug(self) -> None:
        self.assertFalse(is_uuid4("run-abc123"))

    def test_is_uuid4_rejects_non_v4_uuid(self) -> None:
        """A syntactically valid UUID that is NOT version 4 must still mint."""
        # UUID v1-shaped (version nibble '1', not '4').
        self.assertFalse(is_uuid4("11111111-1111-1111-8111-111111111111"))

    def test_resolve_run_id_passes_through_real_uuid4(self) -> None:
        raw = "11111111-1111-4111-8111-111111111111"
        canonical, display = resolve_run_id(raw, workspace_id="ws", project_id="proj")
        self.assertEqual(canonical, raw.lower())
        self.assertIsNone(display, "a genuine UUID4 needs no separate rf_run_id display value")

    def test_resolve_run_id_mints_for_semantic_slug(self) -> None:
        """RF's non-UUID id must never become the join key verbatim.

        The minted id is a genuine UUID (uuid.UUID parses it without error) —
        specifically UUID5 (deterministic), not UUID4 (random); FR-6 requires
        "a genuine UUID run_id", not that CCDash's own minted output must
        itself be version 4 (that constraint is about validating RF's *input*
        format, not CCDash's minting scheme).
        """
        import uuid as _uuid

        raw = "run-abc123"
        canonical, display = resolve_run_id(raw, workspace_id="ws", project_id="proj")
        parsed = _uuid.UUID(canonical)  # raises ValueError if not a genuine UUID
        self.assertEqual(parsed.version, 5, "minting uses uuid5 for determinism")
        self.assertFalse(is_uuid4(canonical), "a uuid5-minted id does not itself look like a UUID4")
        self.assertEqual(display, raw)
        self.assertNotEqual(canonical, raw, "RF's raw non-UUID id must never become the join key verbatim")

    def test_resolve_run_id_is_deterministic(self) -> None:
        """Re-deriving from the same fixture must converge on the same minted id."""
        first = resolve_run_id("run-abc123", workspace_id="ws", project_id="proj")
        second = resolve_run_id("run-abc123", workspace_id="ws", project_id="proj")
        self.assertEqual(first, second)

    def test_resolve_run_id_scopes_by_workspace_and_project(self) -> None:
        """The same raw run_id in a different (workspace, project) must mint a different id."""
        a, _ = resolve_run_id("run-abc123", workspace_id="ws-1", project_id="proj-1")
        b, _ = resolve_run_id("run-abc123", workspace_id="ws-2", project_id="proj-1")
        c, _ = resolve_run_id("run-abc123", workspace_id="ws-1", project_id="proj-2")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_build_research_run_delta_skips_events_without_run_id(self) -> None:
        """No fabricated run identity — absence of run_id means no rollup row."""
        delta = build_research_run_delta(
            {"run_id": None, "event_timestamp": "2026-07-21T10:00:00Z"},
            workspace_id="ws",
            project_id="proj",
        )
        self.assertIsNone(delta)


# ── 3. AC exit gate: rollup derivable from seeded rf_events, zero live RF traffic ──


class SqliteResearchRunsDerivationTests(unittest.IsolatedAsyncioTestCase):
    """T2-001 AC: derive/upsert one research_runs row per run from seeded rf_events."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.rf_repo = SqliteRfEventsRepository(self.db)
        self.rr_repo = SqliteResearchRunsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self, table: str) -> int:
        cursor = await self.db.execute(f"SELECT COUNT(*) FROM {table}")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_two_events_same_run_id_fold_into_one_row(self) -> None:
        run_id_a = await self.rr_repo.upsert_from_event(
            _make_rf_event_row(
                "evt-1", "run-abc123", metric_queries_executed=5,
                metric_estimated_cost_usd=0.10, metric_citation_coverage=0.8,
            ),
            workspace_id="default-local", project_id="proj-1",
        )
        run_id_b = await self.rr_repo.upsert_from_event(
            _make_rf_event_row(
                "evt-2", "run-abc123", event_timestamp="2026-07-21T10:05:00.000000Z",
                metric_queries_executed=3, metric_estimated_cost_usd=0.20,
                metric_citation_coverage=0.9, human_review_required=1,
            ),
            workspace_id="default-local", project_id="proj-1",
        )
        self.assertEqual(run_id_a, run_id_b, "same raw RF run_id must resolve to the same canonical run_id")
        self.assertEqual(await self._count("research_runs"), 1)

        row = await self.rr_repo.get_by_run_id(run_id_a)
        self.assertEqual(row["event_count"], 2)
        self.assertEqual(row["total_queries_executed"], 8)
        self.assertAlmostEqual(row["total_estimated_cost_usd"], 0.30, places=6)
        self.assertEqual(row["citation_coverage"], 0.9, "latest non-null value wins")
        self.assertEqual(row["human_review_required"], 1, "OR'd across events")
        self.assertEqual(row["rf_run_id"], "run-abc123")

    async def test_distinct_run_ids_produce_distinct_rows(self) -> None:
        await self.rr_repo.upsert_from_event(
            _make_rf_event_row("evt-1", "run-a"), workspace_id="default-local", project_id="proj-1"
        )
        await self.rr_repo.upsert_from_event(
            _make_rf_event_row("evt-2", "run-b"), workspace_id="default-local", project_id="proj-1"
        )
        self.assertEqual(await self._count("research_runs"), 2)

    async def test_genuine_uuid4_run_id_is_never_reassigned(self) -> None:
        """RF's non-UUID ids never become a primary/join key (T2-001 AC)."""
        uuid4_run = "11111111-1111-4111-8111-111111111111"
        run_id = await self.rr_repo.upsert_from_event(
            _make_rf_event_row("evt-1", uuid4_run), workspace_id="default-local", project_id="proj-1"
        )
        self.assertEqual(run_id, uuid4_run)
        row = await self.rr_repo.get_by_run_id(run_id)
        self.assertIsNone(row["rf_run_id"], "a genuine UUID4 run_id needs no separate display value")

    async def test_semantic_slug_run_id_never_becomes_join_key(self) -> None:
        import uuid as _uuid

        run_id = await self.rr_repo.upsert_from_event(
            _make_rf_event_row("evt-1", "run-abc123"), workspace_id="default-local", project_id="proj-1"
        )
        self.assertNotEqual(run_id, "run-abc123")
        _uuid.UUID(run_id)  # must be a genuine UUID (raises ValueError otherwise)
        row = await self.rr_repo.get_by_run_id(run_id)
        self.assertEqual(row["rf_run_id"], "run-abc123")

    async def test_derivable_from_seeded_rf_events_with_zero_live_rf_traffic(self) -> None:
        """The named AC: seed rf_events directly (no ingest endpoint involved),
        then derive research_runs purely by reading rf_events back."""
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-a", "run-seed-1", event_timestamp="2026-07-21T10:00:00Z", metric_estimated_cost_usd=0.1)
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-b", "run-seed-1", event_timestamp="2026-07-21T10:10:00Z", metric_estimated_cost_usd=0.2)
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-c", "run-seed-2", event_timestamp="2026-07-21T11:00:00Z", metric_estimated_cost_usd=0.3)
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-d", None, event_timestamp="2026-07-21T12:00:00Z")
        )

        processed = await self.rr_repo.backfill_from_rf_events(project_id="proj-1", workspace_id="default-local")
        self.assertEqual(processed, 4)
        self.assertEqual(await self._count("research_runs"), 2)

        row1 = await self.rr_repo.get_by_rf_run_id("run-seed-1", project_id="proj-1")
        self.assertEqual(row1["event_count"], 2)
        self.assertAlmostEqual(row1["total_estimated_cost_usd"], 0.30, places=6)

        row2 = await self.rr_repo.get_by_rf_run_id("run-seed-2", project_id="proj-1")
        self.assertEqual(row2["event_count"], 1)

    async def test_backfill_is_idempotent_across_repeated_calls(self) -> None:
        """Re-running derivation against the same fixtures must not double-count sums."""
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-a", "run-seed-1", metric_estimated_cost_usd=0.1)
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-b", "run-seed-1", event_timestamp="2026-07-21T10:10:00Z", metric_estimated_cost_usd=0.2)
        )

        await self.rr_repo.backfill_from_rf_events(project_id="proj-1", workspace_id="default-local")
        row_first = await self.rr_repo.get_by_rf_run_id("run-seed-1", project_id="proj-1")
        cost_first = row_first["total_estimated_cost_usd"]
        count_first = await self._count("research_runs")

        await self.rr_repo.backfill_from_rf_events(project_id="proj-1", workspace_id="default-local")
        row_second = await self.rr_repo.get_by_rf_run_id("run-seed-1", project_id="proj-1")
        cost_second = row_second["total_estimated_cost_usd"]
        count_second = await self._count("research_runs")

        self.assertAlmostEqual(cost_first, cost_second, places=6)
        self.assertEqual(count_first, count_second)


# ── 4. ADR-007 direct-count assertion: Postgres (fake asyncpg-shaped conn) ──


class _FakeResearchRunsPgConnection:
    """Minimal asyncpg.Connection fake replicating the real ON CONFLICT DO UPDATE
    merge semantics documented in ``backend/db/repositories/research_runs.py``
    (sum / OR / latest-wins / min-max), so this test exercises the same
    aggregation contract as the SQLite tests above without a live Postgres.
    """

    _SUMMED = (
        "total_queries_executed", "total_urls_extracted", "total_useful_source_count",
        "total_tokens_estimated", "total_claims_total", "total_claims_supported",
        "total_claims_mixed", "total_claims_contradicted", "total_unsupported_claims",
        "total_estimated_cost_usd", "total_latency_ms",
    )
    _OR = (
        "human_review_required", "reuse_meatywiki_writeback_candidate",
        "reuse_skillbom_candidate", "reuse_reusable_source_pack_candidate",
    )
    _LATEST = (
        "intent_id", "task_node_id", "rf_project", "citation_coverage", "duplicate_rate",
        "extraction_failure_rate", "quality_score", "drift_score", "governance_sensitivity",
        "governance_policy_passed", "human_review_status", "human_review_reviewer",
        "agent_postures_json", "skillbom_ids_json", "tools_json", "input_artifacts_json",
        "output_artifacts_json",
    )

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def execute(self, query: str, *args) -> str:
        if not query.strip().upper().startswith("INSERT"):
            raise NotImplementedError(f"unsupported query in fake pg connection: {query}")
        delta = dict(zip(RESEARCH_RUNS_COLUMNS, args))
        run_id = delta["run_id"]
        existing = self._store.get(run_id)
        if existing is None:
            self._store[run_id] = delta
            return "INSERT 0 1"

        for col in self._SUMMED:
            existing[col] = (existing.get(col) or 0) + (delta.get(col) or 0)
        for col in self._OR:
            existing[col] = bool(existing.get(col)) or bool(delta.get(col))
        for col in self._LATEST:
            if delta.get(col) is not None:
                existing[col] = delta[col]
        existing["first_event_at"] = min(existing["first_event_at"], delta["first_event_at"])
        existing["last_event_at"] = max(existing["last_event_at"], delta["last_event_at"])
        existing["event_count"] = existing["event_count"] + delta["event_count"]
        existing["rf_run_id"] = existing.get("rf_run_id") or delta.get("rf_run_id")
        return "INSERT 0 1"

    async def fetchval(self, query: str, *args):
        if query.strip().upper().startswith("SELECT COUNT(*) FROM RESEARCH_RUNS"):
            return len(self._store)
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")

    async def fetchrow(self, query: str, *args):
        if query.strip().upper().startswith("SELECT * FROM RESEARCH_RUNS WHERE RUN_ID"):
            return self._store.get(args[0])
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")


class PostgresResearchRunsFakeConnectionDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: insert N distinct runs, assert SELECT COUNT(*) == N (Postgres, fake conn)."""

    async def asyncSetUp(self) -> None:
        self.conn = _FakeResearchRunsPgConnection()
        self.repo = PostgresResearchRunsRepository(self.conn)

    async def _count(self) -> int:
        return await self.conn.fetchval("SELECT COUNT(*) FROM research_runs")

    async def test_distinct_runs_direct_count_matches(self) -> None:
        n = 5
        for i in range(n):
            await self.repo.upsert_from_event(
                _make_rf_event_row(f"evt-{i}", f"run-pg-{i}"),
                workspace_id="default-local", project_id="proj-pg",
            )
        self.assertEqual(await self._count(), n)

    async def test_same_run_id_aggregates_not_duplicates(self) -> None:
        for i in range(3):
            await self.repo.upsert_from_event(
                _make_rf_event_row(f"evt-{i}", "run-pg-shared", metric_queries_executed=1),
                workspace_id="default-local", project_id="proj-pg",
            )
        self.assertEqual(await self._count(), 1)
        row = await self.conn.fetchrow(
            "SELECT * FROM research_runs WHERE run_id = $1",
            resolve_run_id("run-pg-shared", workspace_id="default-local", project_id="proj-pg")[0],
        )
        self.assertEqual(row["event_count"], 3)
        self.assertEqual(row["total_queries_executed"], 3)


# ── 5. ADR-007 direct-count assertion: Postgres (live, opt-in) ─────────────

_PG_URL = os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres direct-count test for research_runs "
    "requires a running Postgres instance (e.g. via docker compose up --profile postgres)."
)


@unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LivePostgresResearchRunsDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4 on a real Postgres instance: two events, one folded run_id row."""

    async def asyncSetUp(self) -> None:
        import asyncpg

        from backend.db.postgres_migrations import run_migrations as pg_run
        from backend.db.repositories.research_runs import PostgresResearchRunsRepository

        self._pool = await asyncpg.create_pool(_PG_URL)
        await pg_run(self._pool)
        self._project_id = f"research-runs-direct-count-{id(self)}"
        self.repo_cls = PostgresResearchRunsRepository

    async def asyncTearDown(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM research_runs WHERE project_id = $1", self._project_id)
        await self._pool.close()

    async def test_two_events_same_run_fold_into_one_row(self) -> None:
        async with self._pool.acquire() as conn:
            repo = self.repo_cls(conn)
            await repo.upsert_from_event(
                _make_rf_event_row(
                    "evt-live-1", "run-live-abc", project_id=self._project_id,
                    metric_queries_executed=5, metric_estimated_cost_usd=0.1,
                ),
                workspace_id="default-local", project_id=self._project_id,
            )
            await repo.upsert_from_event(
                _make_rf_event_row(
                    "evt-live-2", "run-live-abc", project_id=self._project_id,
                    event_timestamp="2026-07-21T10:05:00.000000Z",
                    metric_queries_executed=3, metric_estimated_cost_usd=0.2,
                ),
                workspace_id="default-local", project_id=self._project_id,
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM research_runs WHERE project_id = $1", self._project_id
            )
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
