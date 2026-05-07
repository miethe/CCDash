import unittest
from unittest.mock import patch

import aiosqlite

from backend.data_domains import PLANNED_AUTH_AUDIT_CONCERNS
from backend.db import migrations as migration_dispatcher, sqlite_migrations
from backend.db.migration_governance import get_sqlite_migration_tables


class SqliteMigrationTests(unittest.IsolatedAsyncioTestCase):
    def test_sqlite_intentionally_lacks_identity_and_audit_tables(self) -> None:
        """SQLite is the local-first bounded compatibility story.

        Identity and audit tables are enterprise-only Postgres concerns and must
        never appear in the SQLite migration set. This test makes that boundary
        machine-checkable so accidental parity additions are caught immediately.
        """
        sqlite_tables = get_sqlite_migration_tables()
        enterprise_concerns = set(PLANNED_AUTH_AUDIT_CONCERNS)
        leaked = sqlite_tables & enterprise_concerns
        self.assertSetEqual(
            leaked,
            set(),
            f"Enterprise-only identity/audit tables leaked into SQLite: {sorted(leaked)}",
        )

    async def test_dispatcher_runs_governance_validation_before_sqlite_migrations(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        with patch("backend.db.migrations.validate_migration_governance_contract") as validate_contract:
            await migration_dispatcher.run_migrations(db)

        validate_contract.assert_called_once()

    async def test_run_migrations_creates_artifact_snapshot_tables_and_indexes(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('artifact_snapshot_cache', 'artifact_identity_map')
            """
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        self.assertEqual(tables, {"artifact_snapshot_cache", "artifact_identity_map"})

        async with db.execute("PRAGMA table_info(artifact_snapshot_cache)") as cur:
            snapshot_columns = {row[1]: row[2].upper() for row in await cur.fetchall()}
        self.assertEqual(
            set(snapshot_columns),
            {
                "id",
                "project_id",
                "collection_id",
                "schema_version",
                "generated_at",
                "fetched_at",
                "artifact_count",
                "status",
                "raw_json",
            },
        )
        self.assertEqual(snapshot_columns["raw_json"], "TEXT")

        async with db.execute("PRAGMA table_info(artifact_identity_map)") as cur:
            identity_columns = {row[1]: row[2].upper() for row in await cur.fetchall()}
        self.assertEqual(
            set(identity_columns),
            {
                "id",
                "project_id",
                "ccdash_name",
                "ccdash_type",
                "skillmeat_uuid",
                "content_hash",
                "match_tier",
                "confidence",
                "resolved_at",
                "unresolved_reason",
            },
        )

        async with db.execute("PRAGMA index_list(artifact_snapshot_cache)") as cur:
            snapshot_indexes = {row[1] for row in await cur.fetchall()}
        self.assertTrue(
            {
                "idx_artifact_snapshot_cache_project_fetched",
                "idx_artifact_snapshot_cache_project_collection",
            }.issubset(snapshot_indexes)
        )

        async with db.execute("PRAGMA index_list(artifact_identity_map)") as cur:
            identity_indexes = {row[1] for row in await cur.fetchall()}
        self.assertTrue(
            {
                "idx_artifact_identity_map_project_name",
                "idx_artifact_identity_map_project_uuid",
                "idx_artifact_identity_map_project_hash",
                "idx_artifact_identity_map_project_match_tier",
            }.issubset(identity_indexes)
        )

    async def test_run_migrations_creates_artifact_ranking_table_and_indexes(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute("PRAGMA table_info(artifact_ranking)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        self.assertTrue(
            {
                "project_id",
                "collection_id",
                "user_scope",
                "artifact_type",
                "artifact_id",
                "artifact_uuid",
                "version_id",
                "workflow_id",
                "period",
                "exclusive_tokens",
                "supporting_tokens",
                "cost_usd",
                "session_count",
                "workflow_count",
                "avg_confidence",
                "confidence",
                "success_score",
                "efficiency_score",
                "quality_score",
                "risk_score",
                "context_pressure",
                "sample_size",
                "identity_confidence",
                "snapshot_fetched_at",
                "recommendation_types_json",
                "evidence_json",
                "computed_at",
            }.issubset(columns)
        )

        async with db.execute("PRAGMA index_list(artifact_ranking)") as cur:
            indexes = {row[1] for row in await cur.fetchall()}
        self.assertTrue(
            {
                "idx_artifact_ranking_project_period",
                "idx_artifact_ranking_artifact_period",
                "idx_artifact_ranking_workflow_period",
                "idx_artifact_ranking_collection_period",
                "idx_artifact_ranking_user_period",
                "idx_artifact_ranking_version_period",
                "idx_artifact_ranking_recommendations",
            }.issubset(indexes)
        )

    async def test_run_migrations_upgrades_legacy_session_logs_before_bootstrap_indexes(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await db.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER NOT NULL,
                applied TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute("INSERT INTO schema_version (version) VALUES (18)")
        await db.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                task_id TEXT DEFAULT '',
                status TEXT DEFAULT 'completed',
                model TEXT DEFAULT '',
                duration_seconds INTEGER DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0,
                started_at TEXT DEFAULT '',
                ended_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_file TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE session_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                log_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                speaker TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT DEFAULT '',
                agent_name TEXT,
                tool_name TEXT,
                tool_args TEXT,
                tool_output TEXT,
                tool_status TEXT DEFAULT 'success'
            )
            """
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute("PRAGMA table_info(session_logs)") as cur:
            log_rows = await cur.fetchall()
        log_columns = {row[1] for row in log_rows}
        self.assertIn("source_log_id", log_columns)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('session_usage_events', 'session_messages', 'session_sentiment_facts', 'session_code_churn_facts', 'session_scope_drift_facts')"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        self.assertEqual(
            tables,
            {
                "session_usage_events",
                "session_messages",
                "session_sentiment_facts",
                "session_code_churn_facts",
                "session_scope_drift_facts",
            },
        )

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], sqlite_migrations.SCHEMA_VERSION)

    async def test_run_migrations_adds_usage_columns_even_when_schema_version_is_already_recorded(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await db.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER NOT NULL,
                applied TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute("INSERT INTO schema_version (version) VALUES (17)")
        await db.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                task_id TEXT DEFAULT '',
                status TEXT DEFAULT 'completed',
                model TEXT DEFAULT '',
                duration_seconds INTEGER DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0,
                started_at TEXT DEFAULT '',
                ended_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_file TEXT NOT NULL
            )
            """
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute("PRAGMA table_info(sessions)") as cur:
            rows = await cur.fetchall()
        columns = {row[1] for row in rows}

        self.assertIn("observed_tokens", columns)
        self.assertIn("cache_input_tokens", columns)
        self.assertIn("tool_reported_tokens", columns)
        self.assertIn("current_context_tokens", columns)
        self.assertIn("context_window_size", columns)
        self.assertIn("reported_cost_usd", columns)
        self.assertIn("display_cost_usd", columns)
        self.assertIn("cost_provenance", columns)

        async with db.execute("PRAGMA table_info(session_logs)") as cur:
            log_rows = await cur.fetchall()
        log_columns = {row[1] for row in log_rows}
        self.assertIn("source_log_id", log_columns)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('session_usage_events', 'session_usage_attributions', 'pricing_catalog_entries', 'session_messages', 'session_sentiment_facts', 'session_code_churn_facts', 'session_scope_drift_facts')"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        self.assertEqual(
            tables,
            {
                "session_usage_events",
                "session_usage_attributions",
                "pricing_catalog_entries",
                "session_messages",
                "session_sentiment_facts",
                "session_code_churn_facts",
                "session_scope_drift_facts",
            },
        )

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], sqlite_migrations.SCHEMA_VERSION)
