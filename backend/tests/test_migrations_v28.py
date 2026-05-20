"""Tests for schema migration v28.

ADR-009: SessionIngestSource port + ingest_cursors watermark table;
source_ref column on sessions.

Verifies:
- source_ref column is added to sessions
- backfill populates 'fs:' + source_file for existing rows
- ix_sessions_source_ref index is created
- ingest_cursors table is created with correct schema
- ingest_cursors accepts inserts with workspace_id defaulting to 'default'
- re-running migration is a no-op (idempotency)
"""
import unittest

import aiosqlite

from backend.db import sqlite_migrations


# Minimal sessions-table DDL for a version-27 database.  We use a subset of
# columns sufficient for the migration under test; other columns are omitted so
# the fixture stays concise and resilient to future sessions additions.
_V27_SESSIONS_DDL = """
CREATE TABLE schema_version (
    version INTEGER NOT NULL,
    applied TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    status           TEXT DEFAULT 'completed',
    source_file      TEXT NOT NULL,
    started_at       TEXT DEFAULT '',
    ended_at         TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""


class MigrationV28Tests(unittest.IsolatedAsyncioTestCase):
    """Schema v28 migration unit tests (SQLite only)."""

    async def _build_v27_db(self) -> aiosqlite.Connection:
        """Return an in-memory DB seeded at schema version 27."""
        db = await aiosqlite.connect(":memory:")
        await db.executescript(_V27_SESSIONS_DDL)
        await db.execute("INSERT INTO schema_version (version) VALUES (27)")
        await db.commit()
        return db

    async def test_source_ref_backfill(self) -> None:
        """source_ref is set to 'fs:' + source_file for existing rows after v28 runs."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        # Insert a session row with source_file set and source_ref absent (column not yet added).
        await db.execute(
            "INSERT INTO sessions (id, project_id, source_file, created_at, updated_at) "
            "VALUES ('sess-1', 'proj-1', 'sessions/abc.jsonl', '2024-01-01', '2024-01-01')"
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT source_ref FROM sessions WHERE id = 'sess-1'") as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "session row not found after migration")
        self.assertEqual(row[0], "fs:sessions/abc.jsonl")

    async def test_source_ref_null_when_source_file_empty(self) -> None:
        """Rows with empty source_file do not get a source_ref backfill."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await db.execute(
            "INSERT INTO sessions (id, project_id, source_file, created_at, updated_at) "
            "VALUES ('sess-2', 'proj-1', '', '2024-01-01', '2024-01-01')"
        )
        await db.commit()

        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT source_ref FROM sessions WHERE id = 'sess-2'") as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertIsNone(row[0], "source_ref should remain NULL when source_file is empty")

    async def test_ix_sessions_source_ref_index_created(self) -> None:
        """ix_sessions_source_ref index exists after migration."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_sessions_source_ref'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "ix_sessions_source_ref index not found after migration")

    async def test_ingest_cursors_table_exists(self) -> None:
        """ingest_cursors table is created by v28 migration."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ingest_cursors'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "ingest_cursors table not found after migration")

    async def test_ingest_cursors_workspace_id_defaults(self) -> None:
        """ingest_cursors accepts inserts and workspace_id defaults to 'default'."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        await db.execute(
            "INSERT INTO ingest_cursors (source_id, project_id) VALUES ('src-1', 'proj-1')"
        )
        await db.commit()

        async with db.execute(
            "SELECT source_id, project_id, workspace_id, error_count "
            "FROM ingest_cursors WHERE source_id = 'src-1'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "src-1")
        self.assertEqual(row[1], "proj-1")
        self.assertEqual(row[2], "default", "workspace_id should default to 'default'")
        self.assertEqual(row[3], 0, "error_count should default to 0")

    async def test_ingest_cursors_ix_workspace_index_created(self) -> None:
        """ix_ingest_cursors_workspace index is created."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_ingest_cursors_workspace'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row, "ix_ingest_cursors_workspace index not found after migration")

    async def test_schema_version_bumped_to_28(self) -> None:
        """Schema version is recorded as 28 after migration."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()

        self.assertEqual(row[0], sqlite_migrations.SCHEMA_VERSION)
        # SCHEMA_VERSION is bumped by each subsequent migration version.
        # Assert that it is at least 28, not that it equals exactly 28,
        # so this test remains valid as the codebase advances.
        self.assertGreaterEqual(sqlite_migrations.SCHEMA_VERSION, 28)

    async def test_migration_is_idempotent(self) -> None:
        """Running migration twice does not raise and does not duplicate rows."""
        db = await self._build_v27_db()
        self.addAsyncCleanup(db.close)

        await db.execute(
            "INSERT INTO sessions (id, project_id, source_file, created_at, updated_at) "
            "VALUES ('sess-idem', 'proj-1', 'sessions/idem.jsonl', '2024-01-01', '2024-01-01')"
        )
        await db.commit()

        # First run
        await sqlite_migrations.run_migrations(db)
        # Second run — should be a no-op
        await sqlite_migrations.run_migrations(db)

        async with db.execute("SELECT source_ref FROM sessions WHERE id = 'sess-idem'") as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], "fs:sessions/idem.jsonl")

        async with db.execute("SELECT COUNT(*) FROM ingest_cursors") as cur:
            count_row = await cur.fetchone()
        self.assertEqual(count_row[0], 0, "No extra rows should appear on second migration run")
