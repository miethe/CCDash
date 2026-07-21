import unittest

from backend.data_domains import ENTERPRISE_ONLY_POSTGRES_CONCERNS
from backend.db.migration_governance import (
    BACKEND_SCHEMA_CAPABILITIES,
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES,
    SUPPORTED_STORAGE_COMPOSITIONS,
    column_parity_diff,
    get_column_parity_diff_all,
    get_enterprise_only_postgres_table_schemas,
    get_enterprise_only_postgres_tables,
    get_postgres_migration_tables,
    resolve_storage_composition_contract,
    get_sqlite_migration_tables,
    get_table_backend_difference_matrix,
    validate_migration_governance_contract,
)
from backend.config import resolve_storage_profile_config


class MigrationGovernanceTests(unittest.TestCase):
    def test_validate_migration_governance_contract(self) -> None:
        validate_migration_governance_contract()

    def test_shared_migration_tables_match_across_backends(self) -> None:
        """Shared tables (excluding enterprise-only) must be identical in SQLite and Postgres."""
        enterprise_only = get_enterprise_only_postgres_tables()
        shared_postgres = get_postgres_migration_tables() - enterprise_only
        self.assertSetEqual(get_sqlite_migration_tables(), shared_postgres)

    def test_enterprise_only_tables_exist_only_in_postgres(self) -> None:
        enterprise_only = get_enterprise_only_postgres_tables()
        sqlite_tables = get_sqlite_migration_tables()
        self.assertTrue(enterprise_only, "Enterprise-only table set should not be empty")
        self.assertSetEqual(enterprise_only & sqlite_tables, set())

    def test_enterprise_only_tables_match_planned_concerns(self) -> None:
        enterprise_only = get_enterprise_only_postgres_tables()
        self.assertSetEqual(enterprise_only, set(ENTERPRISE_ONLY_POSTGRES_CONCERNS))

    def test_session_intelligence_facts_are_shared_tables(self) -> None:
        shared = get_sqlite_migration_tables()
        for table in (
            "session_sentiment_facts",
            "session_code_churn_facts",
            "session_scope_drift_facts",
        ):
            self.assertIn(table, shared)
            self.assertNotIn(table, get_enterprise_only_postgres_tables())

    def test_artifact_snapshot_tables_are_shared_integration_tables(self) -> None:
        shared = get_sqlite_migration_tables()
        enterprise_only = get_enterprise_only_postgres_tables()

        for table in ("artifact_snapshot_cache", "artifact_identity_map"):
            self.assertIn(table, shared)
            self.assertNotIn(table, enterprise_only)

    def test_enterprise_only_tables_are_in_expected_schemas(self) -> None:
        schema_map = get_enterprise_only_postgres_table_schemas()
        expected = {
            "session_embeddings": "app",
            "principals": "identity",
            "scope_identifiers": "identity",
            "memberships": "identity",
            "role_bindings": "identity",
            "privileged_action_audit_records": "audit",
            "access_decision_logs": "audit",
        }
        self.assertEqual(schema_map, expected)

    def test_postgres_tables_are_superset_of_sqlite(self) -> None:
        sqlite_tables = get_sqlite_migration_tables()
        postgres_tables = get_postgres_migration_tables()
        self.assertTrue(sqlite_tables.issubset(postgres_tables))
        self.assertGreater(len(postgres_tables), len(sqlite_tables))

    def test_table_difference_matrix_classifies_shared_tables(self) -> None:
        """Difference matrix covers shared tables only (not enterprise-only)."""
        matrix = get_table_backend_difference_matrix()
        self.assertSetEqual(set(matrix), set(get_sqlite_migration_tables()))

        for categories in matrix.values():
            self.assertSetEqual(
                set(categories) - set(SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES),
                set(),
            )

    def test_json_storage_differences_are_explicit(self) -> None:
        matrix = get_table_backend_difference_matrix()
        self.assertIn("json_storage", matrix["external_definition_sources"])
        self.assertIn("json_storage", matrix["external_definitions"])
        self.assertIn("json_storage", matrix["artifact_snapshot_cache"])
        self.assertIn("json_storage", matrix["execution_runs"])

    def test_supported_storage_compositions_cover_phase4_matrix(self) -> None:
        compositions = {entry.composition: entry for entry in SUPPORTED_STORAGE_COMPOSITIONS}
        self.assertSetEqual(
            set(compositions),
            {"local-sqlite", "enterprise-postgres", "shared-enterprise-postgres"},
        )

        self.assertEqual(compositions["local-sqlite"].backend, "sqlite")
        self.assertEqual(compositions["enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["shared-enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["shared-enterprise-postgres"].isolation_modes, ("schema", "tenant"))

    def test_backend_capabilities_matrix_is_explicit(self) -> None:
        self.assertSetEqual(set(BACKEND_SCHEMA_CAPABILITIES), {"sqlite", "postgres"})
        self.assertFalse(BACKEND_SCHEMA_CAPABILITIES["sqlite"].supports_gin_indexes)
        self.assertTrue(BACKEND_SCHEMA_CAPABILITIES["postgres"].supports_gin_indexes)

    def test_storage_composition_resolver_matches_shared_enterprise_posture(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                "CCDASH_STORAGE_SCHEMA": "ccdash_app",
            }
        )

        composition = resolve_storage_composition_contract(profile)

        self.assertEqual(composition.composition, "shared-enterprise-postgres")

    # ── AC-006: Column/constraint-level parity ────────────────────────

    def test_column_parity_all_shared_tables(self) -> None:
        """All shared tables must have structurally identical columns across backends.

        This is a static DDL-parsing test — no live database connection required.
        Drift items listed in COLUMN_PARITY_DRIFT_ALLOWLIST are excluded from the
        assertion; each is documented in migration_governance.py's module docstring
        and in .claude/findings/ccdash-db-design-remediation-findings.md.
        """
        diff = get_column_parity_diff_all()
        self.assertEqual(
            diff,
            {},
            msg=(
                "Column-parity drift detected across shared tables.\n"
                f"Allowlisted exclusions: {sorted(COLUMN_PARITY_DRIFT_ALLOWLIST)}\n"
                f"Unexpected drift: {diff}"
            ),
        )

    def test_column_parity_diff_returns_empty_for_identical_table(self) -> None:
        """sync_state has simple, identical column definitions on both backends."""
        result = column_parity_diff("sync_state")
        self.assertEqual(result, {})

    def test_column_parity_diff_allowlist_covers_known_drift(self) -> None:
        """The allowlist must document all known drift items (DRIFT-001 through DRIFT-006)."""
        expected_allowlist_items = {
            # DRIFT-001
            ("outbound_telemetry_queue", "event_type"),
            # DRIFT-002
            ("session_relationships", "created_at"),
            # DRIFT-003
            ("oq_resolutions", "created_at"),
            ("oq_resolutions", "updated_at"),
            # DRIFT-004/005/006
            ("session_sentiment_facts", "evidence_json"),
            ("session_code_churn_facts", "evidence_json"),
            ("session_scope_drift_facts", "evidence_json"),
        }
        self.assertTrue(
            expected_allowlist_items.issubset(COLUMN_PARITY_DRIFT_ALLOWLIST),
            msg=f"Missing expected allowlist entries: "
                f"{expected_allowlist_items - COLUMN_PARITY_DRIFT_ALLOWLIST}",
        )

    def test_column_parity_diff_nonexistent_table_returns_empty(self) -> None:
        """column_parity_diff returns {} for a table not in both backends."""
        result = column_parity_diff("this_table_does_not_exist")
        self.assertEqual(result, {})

    # ── T9-001: Phase 5/6 column inventory — static DDL assertion ─────────
    def test_phase5_detection_columns_present_in_both_backends(self) -> None:
        """Phase 5 detection columns are parity-clean in both static DDLs.

        Inventory of columns added by Phase 5 (T5-006/T5-007):
          sessions.model_slug, .workflow_id, .subagent_parent_id,
          .skill_name, .context_window
        None should appear in COLUMN_PARITY_DRIFT_ALLOWLIST.
        """
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import sqlite_migrations, postgres_migrations

        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        pg_blocks = _backend_table_blocks(postgres_migrations)
        sqlite_cols = set(_parse_table_columns(sqlite_blocks["sessions"]))
        pg_cols = set(_parse_table_columns(pg_blocks["sessions"]))

        phase5_cols = ("model_slug", "workflow_id", "subagent_parent_id", "skill_name", "context_window")
        for col in phase5_cols:
            self.assertIn(col, sqlite_cols, msg=f"Phase 5: sessions.{col} absent from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"Phase 5: sessions.{col} absent from Postgres DDL")
            self.assertNotIn(
                ("sessions", col),
                COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"Phase 5: sessions.{col} should be parity-clean, not allowlisted",
            )

    def test_phase6_pricing_columns_present_in_both_backends(self) -> None:
        """Phase 6 pricing columns are parity-clean in both static DDLs.

        Inventory of columns added by Phase 6:
          sessions.context_window_size, .pricing_model_source
        """
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import sqlite_migrations, postgres_migrations

        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        pg_blocks = _backend_table_blocks(postgres_migrations)
        sqlite_cols = set(_parse_table_columns(sqlite_blocks["sessions"]))
        pg_cols = set(_parse_table_columns(pg_blocks["sessions"]))

        phase6_cols = ("context_window_size", "pricing_model_source")
        for col in phase6_cols:
            self.assertIn(col, sqlite_cols, msg=f"Phase 6: sessions.{col} absent from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"Phase 6: sessions.{col} absent from Postgres DDL")
            self.assertNotIn(
                ("sessions", col),
                COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"Phase 6: sessions.{col} should be parity-clean, not allowlisted",
            )

    def test_phase11_capture_columns_present_in_both_backends(self) -> None:
        """Phase 11 launch-time capture columns are parity-clean in both static DDLs.

        Inventory of columns added by Phase 11 (T11-003):
          sessions.launcher, .profile, .effort_tier, .model_variant

        All four must be present in BOTH the SQLite and Postgres CREATE TABLE
        DDL (not just via _ensure_column migration procedures) so that the
        column-parity diff stays clean. None should appear in
        COLUMN_PARITY_DRIFT_ALLOWLIST — any drift here is a real regression.
        """
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import sqlite_migrations, postgres_migrations

        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        pg_blocks = _backend_table_blocks(postgres_migrations)
        sqlite_cols = set(_parse_table_columns(sqlite_blocks["sessions"]))
        pg_cols = set(_parse_table_columns(pg_blocks["sessions"]))

        phase11_cols = ("launcher", "profile", "effort_tier", "model_variant")
        for col in phase11_cols:
            self.assertIn(col, sqlite_cols, msg=f"Phase 11: sessions.{col} absent from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"Phase 11: sessions.{col} absent from Postgres DDL")
            self.assertNotIn(
                ("sessions", col),
                COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"Phase 11: sessions.{col} should be parity-clean, not allowlisted",
            )

    def test_research_runs_columns_are_parity_clean_not_allowlisted(self) -> None:
        """research_runs (T2-001/T2-002) is parity-clean in both static DDLs.

        research_runs (research-foundry-run-telemetry v1, Phase 2, v41) is the
        derived rollup table folded from rf_events. This is the ADR-007 exit
        gate named explicitly by T2-002: every column the repository writes
        (``RESEARCH_RUNS_COLUMNS``) must exist, identically typed, in BOTH the
        SQLite and Postgres CREATE TABLE DDL, and none of them may appear in
        COLUMN_PARITY_DRIFT_ALLOWLIST — research_runs has zero drift by
        construction, mirroring the rf_events precedent (T1-001/T1-002) rather
        than the sessions-table allowlisted-drift pattern. See also the
        dedicated end-to-end coverage in
        backend/tests/test_research_runs_migration_governance.py.
        """
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import sqlite_migrations, postgres_migrations
        from backend.db.repositories.research_runs import RESEARCH_RUNS_COLUMNS

        self.assertIn("research_runs", get_sqlite_migration_tables())
        self.assertIn("research_runs", get_postgres_migration_tables())

        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        pg_blocks = _backend_table_blocks(postgres_migrations)
        sqlite_cols = set(_parse_table_columns(sqlite_blocks["research_runs"]))
        pg_cols = set(_parse_table_columns(pg_blocks["research_runs"]))

        for col in RESEARCH_RUNS_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"T2-002: research_runs.{col} absent from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"T2-002: research_runs.{col} absent from Postgres DDL")
            self.assertNotIn(
                ("research_runs", col),
                COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"T2-002: research_runs.{col} should be parity-clean, not allowlisted",
            )

        diff = column_parity_diff("research_runs")
        self.assertEqual(diff, {}, msg=f"T2-002: research_runs must be column-parity-clean; found drift: {diff}")

    def test_allowlist_entries_are_all_documented(self) -> None:
        """Every allowlist entry must correspond to a DRIFT-NNN entry in the module docstring.

        This pins the audit result: no undocumented entries may be silently added.
        The known documented entries are DRIFT-001 through DRIFT-006 (7 pairs).
        Any growth beyond this set must be justified with a new DRIFT-NNN doc.
        """
        documented_entries = {
            ("outbound_telemetry_queue", "event_type"),    # DRIFT-001
            ("session_relationships", "created_at"),       # DRIFT-002
            ("oq_resolutions", "created_at"),              # DRIFT-003
            ("oq_resolutions", "updated_at"),              # DRIFT-003
            ("session_sentiment_facts", "evidence_json"),  # DRIFT-004
            ("session_code_churn_facts", "evidence_json"), # DRIFT-005
            ("session_scope_drift_facts", "evidence_json"),# DRIFT-006
        }
        undocumented = COLUMN_PARITY_DRIFT_ALLOWLIST - documented_entries
        self.assertEqual(
            undocumented,
            frozenset(),
            msg=(
                "Undocumented entries found in COLUMN_PARITY_DRIFT_ALLOWLIST.\n"
                "Every entry must map to a DRIFT-NNN item in migration_governance.py's docstring.\n"
                f"Undocumented: {sorted(undocumented)}"
            ),
        )


# ── T9-003: Live dual-backend parity test ─────────────────────────────────────
# This class is skipped when CCDASH_DATABASE_URL is not set (no PG available).
# When run against the compose Postgres, it must pass without skips.

import os as _os
import unittest as _unittest

_PG_URL = _os.environ.get("CCDASH_DATABASE_URL", "").strip()
_PG_SKIP_REASON = (
    "CCDASH_DATABASE_URL not set — live Postgres parity test requires a running "
    "Postgres instance (e.g. via docker compose up --profile postgres)."
)


@_unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class LiveSchemaParityTests(_unittest.IsolatedAsyncioTestCase):
    """Introspect LIVE schema on both SQLite and Postgres and assert column parity.

    These tests are PG-GATED: they are skipped when CCDASH_DATABASE_URL is not
    set and run green when the compose Postgres is available.

    Each test:
      1. Runs SQLite migrations on a fresh in-memory DB → inspects PRAGMA table_info
      2. Connects to the compose PG → queries information_schema.columns
      3. Asserts both column sets match the static DDL parse (governance layer)
      4. Asserts the migration head (SCHEMA_VERSION) row is in migrations_applied
         on both backends.
    """

    async def asyncSetUp(self) -> None:
        import aiosqlite
        import asyncpg
        from backend.db.sqlite_migrations import run_migrations as sqlite_run, SCHEMA_VERSION as SV_SQ
        from backend.db.postgres_migrations import run_migrations as pg_run, SCHEMA_VERSION as SV_PG

        self._sqlite_version = SV_SQ
        self._pg_version = SV_PG

        # SQLite: fresh in-memory DB
        self._sqlite = await aiosqlite.connect(":memory:")
        self._sqlite.row_factory = aiosqlite.Row
        await sqlite_run(self._sqlite)

        # Postgres: connect to compose PG
        self._pg_pool = await asyncpg.create_pool(_PG_URL)
        async with self._pg_pool.acquire() as conn:
            await pg_run(self._pg_pool)

    async def asyncTearDown(self) -> None:
        await self._sqlite.close()
        await self._pg_pool.close()

    async def _sqlite_columns(self, table: str) -> set[str]:
        cursor = await self._sqlite.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        return {r["name"] for r in rows}

    async def _pg_columns(self, table: str) -> set[str]:
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1",
                table,
            )
        return {r["column_name"] for r in rows}

    async def test_sessions_live_sqlite_columns_match_static_ddl(self) -> None:
        """Live SQLite sessions column set must match the static governance parse."""
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import sqlite_migrations as _sm

        static_cols = set(_parse_table_columns(_backend_table_blocks(_sm)["sessions"]))
        # The static DDL includes ALL columns; each ensure_column call adds them at runtime.
        live_cols = await self._sqlite_columns("sessions")
        # Live set must be a superset-or-equal of static set (migrations add columns)
        missing = static_cols - live_cols
        self.assertEqual(
            missing,
            set(),
            msg=f"Live SQLite sessions missing columns present in static DDL: {sorted(missing)}",
        )

    async def test_sessions_live_pg_columns_match_static_ddl(self) -> None:
        """Live Postgres sessions column set must match the static governance parse."""
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns
        from backend.db import postgres_migrations as _pm

        static_cols = set(_parse_table_columns(_backend_table_blocks(_pm)["sessions"]))
        live_cols = await self._pg_columns("sessions")
        missing = static_cols - live_cols
        self.assertEqual(
            missing,
            set(),
            msg=f"Live Postgres sessions missing columns present in static DDL: {sorted(missing)}",
        )

    async def test_live_parity_sqlite_vs_pg_sessions(self) -> None:
        """Live column sets for sessions must agree between SQLite and Postgres.

        Columns in COLUMN_PARITY_DRIFT_ALLOWLIST are excluded from the assertion.
        """
        sqlite_cols = await self._sqlite_columns("sessions")
        pg_cols = await self._pg_columns("sessions")

        # Build symmetric diff, excluding allowlisted pairs
        extra_in_sqlite = sqlite_cols - pg_cols
        extra_in_pg = pg_cols - sqlite_cols

        # Filter through allowlist
        unapproved_extra_sqlite = {
            c for c in extra_in_sqlite if ("sessions", c) not in COLUMN_PARITY_DRIFT_ALLOWLIST
        }
        unapproved_extra_pg = {
            c for c in extra_in_pg if ("sessions", c) not in COLUMN_PARITY_DRIFT_ALLOWLIST
        }
        self.assertEqual(
            unapproved_extra_sqlite,
            set(),
            msg=f"sessions columns present in live SQLite but not live Postgres: {sorted(unapproved_extra_sqlite)}",
        )
        self.assertEqual(
            unapproved_extra_pg,
            set(),
            msg=f"sessions columns present in live Postgres but not live SQLite: {sorted(unapproved_extra_pg)}",
        )

    async def test_migration_head_applied_on_sqlite(self) -> None:
        """SQLite migrations_applied must contain the SCHEMA_VERSION row."""
        cursor = await self._sqlite.execute(
            "SELECT COUNT(*) FROM migrations_applied WHERE version = ?",
            (self._sqlite_version,),
        )
        row = await cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row[0], 1, msg=f"SQLite migration head v{self._sqlite_version} not in migrations_applied")

    async def test_migration_head_applied_on_postgres(self) -> None:
        """Postgres migrations_applied must contain the SCHEMA_VERSION row."""
        async with self._pg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM migrations_applied WHERE version = $1",
                self._pg_version,
            )
        self.assertGreaterEqual(
            count, 1,
            msg=f"Postgres migration head v{self._pg_version} not in migrations_applied",
        )


@_unittest.skipUnless(_PG_URL, _PG_SKIP_REASON)
class UpgradePathLeftCapturedAtTests(_unittest.IsolatedAsyncioTestCase):
    """PG-gated upgrade-path safety test for the left(captured_at,10) unique index.

    Verifies that:
      1. The idx_analytics_point_daily UNIQUE index exists on the migrated schema.
      2. Rows with distinct zero-padded ISO-8601 captured_at values do NOT collide.
      3. Two rows sharing the same calendar-day prefix (same project_id, metric_type,
         scope_id, and left(captured_at, 10)) DO collide on the unique key, proving
         the index enforces daily dedup as intended.
    """

    async def asyncSetUp(self) -> None:
        import asyncpg
        from backend.db.postgres_migrations import run_migrations as pg_run

        self._pg_pool = await asyncpg.create_pool(_PG_URL)
        async with self._pg_pool.acquire() as conn:
            await pg_run(self._pg_pool)
            # analytics_entries.metric_type is a FK to metric_types(id); seed the
            # parent rows this suite references so inserts satisfy the constraint.
            await conn.execute(
                "INSERT INTO metric_types (id, display_name) VALUES "
                "('test_upgrade_path_distinct', 'Test Upgrade Path Distinct'), "
                "('test_upgrade_path_collide', 'Test Upgrade Path Collide') "
                "ON CONFLICT (id) DO NOTHING"
            )

    async def asyncTearDown(self) -> None:
        # Remove test rows inserted by this suite (identified by a unique metric_type prefix).
        # Delete the child analytics_entries first, then the metric_types parents (FK order).
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM analytics_entries WHERE metric_type LIKE 'test_upgrade_path_%'"
            )
            await conn.execute(
                "DELETE FROM metric_types WHERE id LIKE 'test_upgrade_path_%'"
            )
        await self._pg_pool.close()

    async def test_left_captured_at_index_exists(self) -> None:
        """idx_analytics_point_daily must exist on the live PG schema."""
        async with self._pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = 'idx_analytics_point_daily'"
            )
        self.assertIsNotNone(
            row,
            "idx_analytics_point_daily not found in pg_indexes — v34 migration may not have run",
        )

    async def test_distinct_iso_days_do_not_collide(self) -> None:
        """Rows with distinct ISO-8601 calendar dates must insert without a duplicate-key error."""
        import asyncpg

        async with self._pg_pool.acquire() as conn:
            # Two distinct days — must succeed.
            await conn.execute(
                "INSERT INTO analytics_entries "
                "(project_id, metric_type, scope_id, period, captured_at, value) "
                "VALUES ($1, $2, $3, 'point', $4, 1) "
                "ON CONFLICT DO NOTHING",
                "test-proj", "test_upgrade_path_distinct", "", "2025-01-01T00:00:00Z",
            )
            await conn.execute(
                "INSERT INTO analytics_entries "
                "(project_id, metric_type, scope_id, period, captured_at, value) "
                "VALUES ($1, $2, $3, 'point', $4, 2) "
                "ON CONFLICT DO NOTHING",
                "test-proj", "test_upgrade_path_distinct", "", "2025-01-02T00:00:00Z",
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM analytics_entries "
                "WHERE project_id = 'test-proj' AND metric_type = 'test_upgrade_path_distinct'",
            )
        self.assertEqual(count, 2, "Expected 2 rows for 2 distinct ISO-8601 days")

    async def test_same_day_rows_collide_on_unique_index(self) -> None:
        """Two rows with the same (project_id, metric_type, scope_id, day) must collide."""
        import asyncpg

        async with self._pg_pool.acquire() as conn:
            # Insert first row for 2025-03-15.
            await conn.execute(
                "INSERT INTO analytics_entries "
                "(project_id, metric_type, scope_id, period, captured_at, value) "
                "VALUES ($1, $2, $3, 'point', $4, 10) "
                "ON CONFLICT DO NOTHING",
                "test-proj", "test_upgrade_path_collide", "", "2025-03-15T06:00:00Z",
            )
            # Insert second row for the same calendar day (different time) — must be rejected.
            with self.assertRaises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO analytics_entries "
                    "(project_id, metric_type, scope_id, period, captured_at, value) "
                    "VALUES ($1, $2, $3, 'point', $4, 20)",
                    "test-proj", "test_upgrade_path_collide", "", "2025-03-15T18:30:00Z",
                )


if __name__ == "__main__":
    unittest.main()
