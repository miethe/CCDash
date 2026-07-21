"""Migration governance + ADR-007 direct-count tests for ``rf_events`` (T1-002).

``rf_events`` (T1-001, research-foundry-run-telemetry v1, v40) is the raw
append-only mirror of RF's ``ccdash_event`` payload. This module is the
Phase 1 exit gate for two independent contracts:

1. Dual-DDL column parity (ADR-007 / migration_governance.py governance
   layer) — ``rf_events`` must be registered in both backend migration-table
   getters and carry a structurally identical column set (after canonical
   type normalization) across SQLite and Postgres. Unlike DRIFT-001..006,
   ``rf_events`` requires ZERO ``COLUMN_PARITY_DRIFT_ALLOWLIST`` entries — it
   is parity-clean by construction (see the "Phase 5 detection columns" /
   "rf_events" comment in ``migration_governance.py``'s allowlist block).
   This module pins that: adding an rf_events entry to the allowlist without
   updating this test is a governance regression, not a passing state.

2. ADR-007 §4 "Test Contract: Persistence Assertion" — every new write path
   ships a direct persistence assertion (``SELECT COUNT(*)`` immediately
   after the write, not just a return-value check). Covered here for both
   the SQLite repository (real in-memory DB) and the Postgres repository
   (fake asyncpg-shaped connection — no live Postgres available in the
   standard CI runner, mirroring ``test_ingest_cursor_repository.py``'s
   established convention). A live-Postgres-gated variant is included and
   skipped unless ``CCDASH_DATABASE_URL`` is set, mirroring
   ``test_migration_governance.py``'s ``LiveSchemaParityTests`` convention.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_migration_governance.py -v
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
from backend.db.repositories.rf_events import (
    RF_EVENTS_COLUMNS,
    PostgresRfEventsRepository,
    SqliteRfEventsRepository,
)
from backend.db.sqlite_migrations import run_migrations


def _make_row(event_id: str, project_id: str = "proj-1", workspace_id: str = "default-local", **extra) -> dict:
    """Minimal valid ``rf_events`` row: required columns + always-supplied raw_payload_json.

    ``raw_payload_json`` is NOT NULL with no usable INSERT-time default (an
    explicit column list always overrides the DDL DEFAULT), so — matching the
    real ingest service's contract documented in
    ``backend/db/repositories/rf_events.py`` — it must always be supplied here.
    """
    row = {
        "event_id": event_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "event_timestamp": "2026-07-21T10:00:00.000000Z",
        "rf_project": "research-foundry",
        "raw_payload_json": "{}",
    }
    row.update(extra)
    return row


# ── 1. Migration governance: registration + column parity ──────────────────


class RfEventsMigrationGovernanceTests(unittest.TestCase):
    """rf_events registration + static DDL column-parity assertions (T1-002)."""

    def test_rf_events_registered_in_sqlite_migration_tables(self) -> None:
        self.assertIn("rf_events", get_sqlite_migration_tables())

    def test_rf_events_registered_in_postgres_migration_tables(self) -> None:
        self.assertIn("rf_events", get_postgres_migration_tables())

    def test_rf_events_is_not_enterprise_only(self) -> None:
        """rf_events is a shared table — it must exist in SQLite too, never enterprise-only."""
        self.assertNotIn("rf_events", get_enterprise_only_postgres_tables())

    def test_rf_events_column_parity_diff_is_empty(self) -> None:
        """rf_events is parity-clean by construction — zero structural drift.

        This is the AC-2 (partial) exit-gate assertion: identical column set,
        type, nullability, and default across both DDL files (modulo the
        canonical type-normalization mapping already covers INTEGER/BOOLEAN,
        TEXT/JSONB, REAL/DOUBLE PRECISION, and the timestamp-default
        nullability case for created_at).
        """
        diff = column_parity_diff("rf_events")
        self.assertEqual(
            diff,
            {},
            msg=f"rf_events must be column-parity-clean across backends; found drift: {diff}",
        )

    def test_rf_events_included_in_global_parity_sweep(self) -> None:
        """rf_events must not introduce drift in the all-shared-tables sweep either."""
        merged_diff = get_column_parity_diff_all()
        self.assertNotIn(
            "rf_events",
            merged_diff,
            msg=f"rf_events introduced drift in the global parity sweep: {merged_diff.get('rf_events')}",
        )

    def test_rf_events_has_zero_allowlist_entries(self) -> None:
        """rf_events must NOT appear in COLUMN_PARITY_DRIFT_ALLOWLIST at all.

        Because rf_events is parity-clean by construction (previous test),
        allowlisting any (rf_events, column) pair would silently mask a real
        future regression rather than document a deliberate, harmless drift
        (the DRIFT-001..006 precedent). This mirrors the Phase 5/6/11
        "intentionally NOT allowlisted" convention already enforced for the
        `sessions` detection/pricing/capture columns.
        """
        rf_events_entries = {pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] == "rf_events"}
        self.assertEqual(
            rf_events_entries,
            set(),
            msg=(
                "rf_events must have zero COLUMN_PARITY_DRIFT_ALLOWLIST entries "
                f"(it is parity-clean by construction); found: {sorted(rf_events_entries)}"
            ),
        )

    def test_rf_events_column_set_matches_repository_contract(self) -> None:
        """Every column the repository writes (RF_EVENTS_COLUMNS) must exist in both DDLs.

        Guards against the repository's INSERT column list silently drifting
        away from either backend's CREATE TABLE statement.
        """
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns

        sqlite_cols = set(_parse_table_columns(_backend_table_blocks(sqlite_migrations)["rf_events"]))
        pg_cols = set(_parse_table_columns(_backend_table_blocks(postgres_migrations)["rf_events"]))

        for col in RF_EVENTS_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"RF_EVENTS_COLUMNS entry '{col}' missing from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"RF_EVENTS_COLUMNS entry '{col}' missing from Postgres DDL")


# ── 2. ADR-007 direct-count assertion: SQLite (real in-memory DB) ──────────


class SqliteRfEventsDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: insert N rows, assert SELECT COUNT(*) == N (SQLite)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteRfEventsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM rf_events")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_insert_n_rows_direct_count_matches(self) -> None:
        n = 5
        for i in range(n):
            inserted = await self.repo.insert_if_not_exists(_make_row(event_id=f"evt-sqlite-{i}"))
            self.assertTrue(inserted, f"row {i} should have been newly inserted")

        db_count = await self._count()
        self.assertEqual(
            db_count,
            n,
            f"SELECT COUNT(*) FROM rf_events ({db_count}) must equal the number of rows "
            f"inserted ({n}) — a mismatch means rows were lost silently (ADR-007).",
        )

    async def test_reinsert_same_event_id_does_not_increase_count(self) -> None:
        """Idempotency: re-inserting the same event_id must not change the direct count."""
        row = _make_row(event_id="evt-sqlite-dup")

        first = await self.repo.insert_if_not_exists(row)
        second = await self.repo.insert_if_not_exists(row)

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(await self._count(), 1)

    async def test_direct_count_reflects_mixed_new_and_duplicate_inserts(self) -> None:
        """N distinct rows + M duplicate re-inserts of one of them -> count == N."""
        n = 3
        for i in range(n):
            await self.repo.insert_if_not_exists(_make_row(event_id=f"evt-sqlite-mix-{i}"))
        # Re-insert one of the existing rows twice more.
        for _ in range(2):
            await self.repo.insert_if_not_exists(_make_row(event_id="evt-sqlite-mix-0"))

        self.assertEqual(await self._count(), n)


# ── 3. ADR-007 direct-count assertion: Postgres (fake asyncpg-shaped conn) ──
#
# No live Postgres is guaranteed in the standard CI runner (mirrors the
# established convention in test_ingest_cursor_repository.py). This fake
# connection exercises the exact same INSERT ... ON CONFLICT DO NOTHING /
# status-string-parsing logic PostgresRfEventsRepository actually runs.


class _FakeRfEventsPgConnection:
    """Minimal asyncpg.Connection fake for rf_events direct-count testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple] = {}

    async def execute(self, query: str, *args) -> str:
        q = query.strip().upper()
        if q.startswith("INSERT"):
            # event_id is always the first column per RF_EVENTS_COLUMNS order.
            event_id = args[0]
            if event_id in self._store:
                return "INSERT 0 0"
            self._store[event_id] = args
            return "INSERT 0 1"
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")

    async def fetchval(self, query: str, *args):
        q = query.strip().upper()
        if q.startswith("SELECT COUNT(*) FROM RF_EVENTS"):
            return len(self._store)
        raise NotImplementedError(f"unsupported query in fake pg connection: {query}")


class PostgresRfEventsFakeConnectionDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: insert N rows, assert SELECT COUNT(*) == N (Postgres, fake conn)."""

    async def asyncSetUp(self) -> None:
        self.conn = _FakeRfEventsPgConnection()
        self.repo = PostgresRfEventsRepository(self.conn)

    async def _count(self) -> int:
        return await self.conn.fetchval("SELECT COUNT(*) FROM rf_events")

    async def test_insert_n_rows_direct_count_matches(self) -> None:
        n = 5
        for i in range(n):
            inserted = await self.repo.insert_if_not_exists(_make_row(event_id=f"evt-pg-{i}"))
            self.assertTrue(inserted, f"row {i} should have been newly inserted")

        db_count = await self._count()
        self.assertEqual(
            db_count,
            n,
            f"SELECT COUNT(*) FROM rf_events ({db_count}) must equal the number of rows "
            f"inserted ({n}) — a mismatch means rows were lost silently (ADR-007).",
        )

    async def test_reinsert_same_event_id_does_not_increase_count(self) -> None:
        row = _make_row(event_id="evt-pg-dup")

        first = await self.repo.insert_if_not_exists(row)
        second = await self.repo.insert_if_not_exists(row)

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(await self._count(), 1)


# ── 4. ADR-007 direct-count assertion: Postgres (live, opt-in) ─────────────
#
# Skipped unless CCDASH_DATABASE_URL is set, mirroring
# test_migration_governance.py's LiveSchemaParityTests convention exactly.

_PG_URL = os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres direct-count test for rf_events "
    "requires a running Postgres instance (e.g. via docker compose up --profile postgres)."
)


@unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LivePostgresRfEventsDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4 on a real Postgres instance: insert N rows, assert COUNT(*) == N."""

    async def asyncSetUp(self) -> None:
        import asyncpg

        from backend.db.postgres_migrations import run_migrations as pg_run

        self._pool = await asyncpg.create_pool(_PG_URL)
        await pg_run(self._pool)
        # Isolate this test run's rows behind a unique project_id so repeated
        # live runs never collide with prior data left in a shared DB.
        self._project_id = f"rf-events-direct-count-{id(self)}"

    async def asyncTearDown(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM rf_events WHERE project_id = $1", self._project_id)
        await self._pool.close()

    async def test_insert_n_rows_direct_count_matches(self) -> None:
        n = 5
        async with self._pool.acquire() as conn:
            repo = PostgresRfEventsRepository(conn)
            for i in range(n):
                inserted = await repo.insert_if_not_exists(
                    _make_row(event_id=f"evt-live-pg-{self._project_id}-{i}", project_id=self._project_id)
                )
                self.assertTrue(inserted)

            db_count = await conn.fetchval(
                "SELECT COUNT(*) FROM rf_events WHERE project_id = $1", self._project_id
            )
        self.assertEqual(db_count, n)


if __name__ == "__main__":
    unittest.main()
