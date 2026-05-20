"""Tests for schema migration v29.

ADR-008: workspace-scoped bearer auth — workspaces + workspace_tokens tables;
workspace_id column on all scoped tables; ingest_cursors default normalised.

Verifies:
- workspaces table is created with correct columns
- workspace_tokens table is created with correct columns
- Partial indexes ix_workspace_tokens_workspace and ix_workspace_tokens_hash exist
- default-local workspace seed row is present after migration
- workspace_id column is added to sessions, documents, tasks, features, entity_links
- workspace_id column is NOT required to pre-exist (net-new install path)
- ingest_cursors rows with workspace_id = 'default' are rewritten to 'default-local'
- workspace_tokens table is EMPTY after migration (bootstrap row is T4-006's job)
- Schema version is bumped to 29
- Running migrations twice is a no-op (idempotency)
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db import sqlite_migrations


class MigrationV29Tests(unittest.IsolatedAsyncioTestCase):
    """Schema v29 migration unit tests (SQLite only).

    The v28 fixture is built by running the full _TABLES DDL and then
    applying the v28 run_migrations steps in isolation.  We use a
    temporarily patched SCHEMA_VERSION=28 so that run_migrations stops
    after completing v28 work and before applying v29 steps.
    """

    async def _build_v28_db(self) -> aiosqlite.Connection:
        """Return an in-memory DB at schema version 28 (pre-v29 state).

        Strategy: patch SCHEMA_VERSION to 28, run migrations from v0, then
        restore.  This ensures the fixture has the full correct schema
        (including all columns and indexes referenced by _TABLES) and that
        ingest_cursors has the v28 DEFAULT 'default' workspace_id value.
        """
        original_version = sqlite_migrations.SCHEMA_VERSION
        sqlite_migrations.SCHEMA_VERSION = 28
        try:
            db = await aiosqlite.connect(":memory:")
            await sqlite_migrations.run_migrations(db)
        finally:
            sqlite_migrations.SCHEMA_VERSION = original_version
        return db

    # ── Table existence ─────────────────────────────────────────────────────

    async def test_workspaces_table_exists(self) -> None:
        """workspaces table is created by v29 migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspaces'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "workspaces table not found after v29 migration")

    async def test_workspace_tokens_table_exists(self) -> None:
        """workspace_tokens table is created by v29 migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_tokens'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "workspace_tokens table not found after v29 migration")

    # ── Column introspection ─────────────────────────────────────────────────

    async def _get_column_names(self, db: aiosqlite.Connection, table: str) -> set[str]:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            rows = await cur.fetchall()
        return {row[1] for row in rows}

    async def test_workspaces_columns(self) -> None:
        """workspaces table has the expected columns per ADR-008 §Schema."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        cols = await self._get_column_names(db, "workspaces")
        self.assertIn("workspace_id", cols)
        self.assertIn("name", cols)
        self.assertIn("status", cols)
        self.assertIn("created_at", cols)

    async def test_workspace_tokens_columns(self) -> None:
        """workspace_tokens table has the expected columns per ADR-008 §Schema."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        cols = await self._get_column_names(db, "workspace_tokens")
        expected = {
            "token_id",
            "workspace_id",
            "project_id",
            "hashed_token",
            "scope",
            "created_at",
            "last_used_at",
            "revoked_at",
            "description",
        }
        self.assertEqual(cols, expected)

    # ── Partial indexes ──────────────────────────────────────────────────────

    async def test_ix_workspace_tokens_workspace_index_created(self) -> None:
        """ix_workspace_tokens_workspace partial index exists after migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE type='index' AND name='ix_workspace_tokens_workspace'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "ix_workspace_tokens_workspace index not found")
        # Verify it's a partial index (WHERE clause present).
        self.assertIn("WHERE", row[1].upper(), "Expected a partial index (WHERE clause)")

    async def test_ix_workspace_tokens_hash_index_created(self) -> None:
        """ix_workspace_tokens_hash partial index exists after migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE type='index' AND name='ix_workspace_tokens_hash'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "ix_workspace_tokens_hash index not found")
        self.assertIn("WHERE", row[1].upper(), "Expected a partial index (WHERE clause)")

    # ── Seed row ─────────────────────────────────────────────────────────────

    async def test_default_local_workspace_seeded(self) -> None:
        """default-local workspace seed row exists after migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT workspace_id, name, status FROM workspaces"
            " WHERE workspace_id = 'default-local'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "default-local workspace row not found after v29 migration")
        self.assertEqual(row[1], "Default Local Workspace")
        self.assertEqual(row[2], "active")

    async def test_workspace_tokens_is_empty_after_migration(self) -> None:
        """workspace_tokens is empty after migration (bootstrap is T4-006's job)."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT COUNT(*) FROM workspace_tokens") as cur:
            row = await cur.fetchone()

        self.assertEqual(row[0], 0, "workspace_tokens should be empty after schema migration")

    # ── workspace_id column on scoped tables ─────────────────────────────────

    async def test_scoped_tables_have_workspace_id_column(self) -> None:
        """sessions, documents, tasks, features, entity_links all gain workspace_id."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        for table in ("sessions", "documents", "tasks", "features", "entity_links"):
            cols = await self._get_column_names(db, table)
            self.assertIn(
                "workspace_id",
                cols,
                f"workspace_id column missing on table '{table}' after v29 migration",
            )

    async def test_workspace_id_default_is_default_local(self) -> None:
        """Inserting a row without workspace_id gets 'default-local' via column DEFAULT."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        # Insert a sessions row without specifying workspace_id.
        await db.execute(
            "INSERT INTO sessions (id, project_id, source_file, created_at, updated_at)"
            " VALUES ('sess-default', 'proj-1', 'f.jsonl', '2024-01-01', '2024-01-01')"
        )
        await db.commit()

        async with db.execute(
            "SELECT workspace_id FROM sessions WHERE id = 'sess-default'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "default-local", "DEFAULT for workspace_id should be 'default-local'")

    # ── ingest_cursors normalisation ─────────────────────────────────────────

    async def test_ingest_cursors_legacy_default_rewritten(self) -> None:
        """v28 rows with workspace_id='default' are rewritten to 'default-local' by v29."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        # Insert a v28-style row with the old 'default' workspace_id.
        await db.execute(
            "INSERT INTO ingest_cursors (source_id, project_id, workspace_id)"
            " VALUES ('src-legacy', 'proj-1', 'default')"
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT workspace_id FROM ingest_cursors WHERE source_id = 'src-legacy'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(
            row[0],
            "default-local",
            "Legacy ingest_cursors row with workspace_id='default' was not rewritten to 'default-local'",
        )

    async def test_ingest_cursors_already_default_local_unchanged(self) -> None:
        """Rows already using 'default-local' are unaffected by the normalisation UPDATE."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await db.execute(
            "INSERT INTO ingest_cursors (source_id, project_id, workspace_id)"
            " VALUES ('src-new', 'proj-1', 'default-local')"
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT workspace_id FROM ingest_cursors WHERE source_id = 'src-new'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "default-local")

    # ── Schema version ───────────────────────────────────────────────────────

    async def test_schema_version_bumped_to_29(self) -> None:
        """Schema version is recorded as 29 after migration."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()

        self.assertEqual(row[0], sqlite_migrations.SCHEMA_VERSION)
        self.assertEqual(sqlite_migrations.SCHEMA_VERSION, 29)

    # ── Idempotency ───────────────────────────────────────────────────────────

    async def test_migration_is_idempotent(self) -> None:
        """Running migration twice produces identical post-state with no drift."""
        db = await self._build_v28_db()
        self.addAsyncCleanup(db.close)

        # Pre-seed a legacy ingest_cursors row.
        await db.execute(
            "INSERT INTO ingest_cursors (source_id, project_id, workspace_id)"
            " VALUES ('src-idem', 'proj-1', 'default')"
        )
        await db.commit()

        # First run.
        await sqlite_migrations.run_migrations(db)

        # Capture post-first-run row counts.
        async with db.execute("SELECT COUNT(*) FROM workspaces") as cur:
            count_workspaces_first = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM workspace_tokens") as cur:
            count_tokens_first = (await cur.fetchone())[0]

        # Second run — must be a no-op.
        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT COUNT(*) FROM workspaces") as cur:
            count_workspaces_second = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM workspace_tokens") as cur:
            count_tokens_second = (await cur.fetchone())[0]

        self.assertEqual(
            count_workspaces_first,
            count_workspaces_second,
            "workspaces row count drifted between first and second migration run",
        )
        self.assertEqual(
            count_tokens_first,
            count_tokens_second,
            "workspace_tokens row count drifted between first and second migration run",
        )

        # Verify the legacy row is still normalised correctly after two runs.
        async with db.execute(
            "SELECT workspace_id FROM ingest_cursors WHERE source_id = 'src-idem'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "default-local")

    async def test_migration_on_fresh_db_is_idempotent(self) -> None:
        """Running migration twice on a fresh (v0) DB produces identical post-state."""
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        # First run — starts from v0 (no schema_version table).
        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row1 = await cur.fetchone()

        # Second run.
        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row2 = await cur.fetchone()

        self.assertEqual(row1[0], row2[0], "Schema version drifted on double-run from fresh DB")
        self.assertEqual(row2[0], sqlite_migrations.SCHEMA_VERSION)

        # Both tables must exist and workspaces seed row must be present exactly once.
        async with db.execute("SELECT COUNT(*) FROM workspaces") as cur:
            count = (await cur.fetchone())[0]
        self.assertEqual(count, 1, "workspaces should have exactly 1 seed row after double-run on fresh DB")
