import unittest

import aiosqlite

from backend.db import sqlite_migrations


class SqliteMigrationTests(unittest.IsolatedAsyncioTestCase):
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
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'session_usage_events'"
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row)

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
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('session_usage_events', 'session_usage_attributions', 'pricing_catalog_entries')"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        self.assertEqual(tables, {"session_usage_events", "session_usage_attributions", "pricing_catalog_entries"})

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], sqlite_migrations.SCHEMA_VERSION)
