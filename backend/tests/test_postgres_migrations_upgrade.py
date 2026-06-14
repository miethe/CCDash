"""Tests for the Postgres migration upgrade path from schema_version=29.

Coverage:
- T1-006 (P1): upgrade path from v29 → SCHEMA_VERSION=35 raises no exception
  and applies migrations in the correct order.
- Key ordering assertion: sessions.project_id must be added (via _ensure_column)
  BEFORE any CREATE INDEX that references sessions.project_id.
- Fresh DB path (version=0): v30 block still runs; indexes created after column.

Run only as a named module (pytest collection hangs in this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_postgres_migrations_upgrade.py -v
"""
from __future__ import annotations

import asyncio
import contextlib
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Mock DB executor that records every DDL statement in order
# ---------------------------------------------------------------------------

class _RecordingDB:
    """Minimal asyncpg.Connection mock that records all executed statements.

    Implements the subset of the asyncpg Connection interface used by
    _run_migrations_inner and the functions it calls:
      - fetchrow(query, *args)   — returns None by default
      - fetch(query, *args)      — returns [] by default
      - execute(query, *args)    — records statement; no-op
    """

    def __init__(self, starting_version: int = 29) -> None:
        self._version = starting_version
        self._executed: list[str] = []
        self._schema_version_set = False

    # -- asyncpg Connection interface stubs ----------------------------------

    async def fetchrow(self, query: str, *args):
        """Return version or None depending on the query."""
        q = query.strip().upper()

        # schema_version read at the start of _run_migrations_inner
        if "FROM SCHEMA_VERSION" in q and "MAX" in q:
            if self._version == 0:
                return None  # table doesn't exist yet → except path
            row = MagicMock()
            row.__getitem__ = lambda self_, k: self._version
            row.__bool__ = lambda self_: True
            return row

        # _column_exists: information_schema.columns lookup
        if "INFORMATION_SCHEMA.COLUMNS" in q:
            table = args[0] if args else ""
            col = args[1] if len(args) > 1 else ""
            # Simulate pre-v30 state: sessions.project_id does NOT exist yet
            if table == "sessions" and col == "project_id":
                # Column doesn't exist before our ALTER adds it.
                # We simulate it existing AFTER the ALTER has been recorded.
                alter = f"ALTER TABLE sessions ADD COLUMN project_id"
                already_added = any(alter.upper() in s.upper() for s in self._executed)
                if already_added:
                    row = MagicMock()
                    row.__bool__ = lambda self_: True
                    return row
                return None
            # All other columns assumed to exist
            row = MagicMock()
            row.__bool__ = lambda self_: True
            return row

        # sessions PK check for v31 idempotency guard
        if "PRIMARY KEY" in q and "SESSIONS" in q:
            # Return None on first call so v31 thinks it needs to run,
            # but return a row after we pretend project_id exists.
            return None

        return None

    async def fetch(self, query: str, *args) -> list:
        """Return empty list for all catalog queries."""
        return []

    async def execute(self, query: str, *args) -> None:
        """Record every executed statement."""
        self._executed.append(query.strip())

    # -- Helpers for assertions -----------------------------------------------

    def executed_statements(self) -> list[str]:
        """Return the ordered list of all executed SQL statements."""
        return list(self._executed)

    def is_tables_blob(self, stmt: str) -> bool:
        """Return True if *stmt* is the _TABLES multi-statement blob.

        _TABLES starts with a SQL comment header followed by CREATE TABLE
        statements.  It is >5KB and contains many sub-statements.  We
        identify it by checking for the schema_version table definition
        somewhere in the first 512 chars (after the comment preamble).
        """
        return "CREATE TABLE IF NOT EXISTS schema_version" in stmt[:512]

    def index_of(self, fragment: str, *, skip_tables_blob: bool = True) -> int:
        """Return the index of the first *standalone* statement containing *fragment*.

        By default, skips the _TABLES blob to avoid false positives from
        comment text or DDL inside the big string literal.  Set
        skip_tables_blob=False to include the blob.
        """
        frag_upper = fragment.upper()
        for i, stmt in enumerate(self._executed):
            if skip_tables_blob and self.is_tables_blob(stmt):
                continue
            if frag_upper in stmt.upper():
                return i
        return -1

    def has_statement(self, fragment: str, **kwargs) -> bool:
        return self.index_of(fragment, **kwargs) != -1


# ---------------------------------------------------------------------------
# Helper to run _run_migrations_inner against a recording mock
# ---------------------------------------------------------------------------

def _run_migrations(starting_version: int = 29) -> _RecordingDB:
    """Run _run_migrations_inner with a mock DB at *starting_version*.

    Patches out all helper functions that need a real PG connection for
    complex multi-step operations that aren't relevant to the ordering test.
    Returns the _RecordingDB so callers can inspect executed statements.
    """
    from backend.db import postgres_migrations as pm

    db = _RecordingDB(starting_version=starting_version)

    # Patch heavy coroutine helpers that would fail without a real PG connection
    noop = AsyncMock()
    patches = [
        patch.object(pm, "_ensure_test_visualizer_tables", noop),
        patch.object(pm, "_ensure_planning_worktree_contexts_table", noop),
        patch.object(pm, "_ensure_enterprise_identity_audit_tables", noop),
        patch.object(pm, "_ensure_enterprise_session_intelligence_tables", noop),
        patch.object(pm, "_ensure_entity_link_uniqueness", noop),
        patch.object(pm, "_ensure_durable_queue_text_timestamps", noop),
        patch.object(pm, "_ensure_oq_resolutions_integer_bools", noop),
        patch.object(pm, "_migrate_v30_detail_tables_project_id", noop),
        patch.object(pm, "_migrate_v31_sessions_composite_pk_and_child_fks", noop),
        patch.object(pm, "_backfill_feature_owners_linked_docs", noop),
    ]

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        asyncio.run(pm._run_migrations_inner(db))

    return db


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestPostgresMigrationsUpgradeFromV29(unittest.TestCase):
    """Verify that upgrading from schema_version=29 to SCHEMA_VERSION=35 works."""

    def setUp(self) -> None:
        self.db = _run_migrations(starting_version=29)

    def test_no_exception_raised(self) -> None:
        """_run_migrations_inner must not raise when upgrading from v29."""
        # If we reach here, setUp() completed without exception.
        self.assertIsNotNone(self.db)

    def test_final_schema_version_recorded(self) -> None:
        """schema_version INSERT must be present in the executed statements."""
        from backend.db.postgres_migrations import SCHEMA_VERSION
        found = any(
            "INSERT INTO SCHEMA_VERSION" in s.upper()
            for s in self.db.executed_statements()
        )
        self.assertTrue(found, "Expected INSERT INTO schema_version in executed statements")

    def test_project_id_alter_before_idx_sessions_project(self) -> None:
        """sessions.project_id ALTER must precede idx_sessions_project creation."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_project_idx = self.db.index_of("idx_sessions_project")

        self.assertGreater(
            alter_idx,
            -1,
            "Expected ALTER TABLE sessions ADD COLUMN project_id in executed statements",
        )
        self.assertGreater(
            idx_project_idx,
            -1,
            "Expected CREATE INDEX idx_sessions_project in executed statements",
        )
        self.assertLess(
            alter_idx,
            idx_project_idx,
            "sessions.project_id ALTER must execute BEFORE idx_sessions_project creation; "
            f"got ALTER at position {alter_idx}, index at position {idx_project_idx}",
        )

    def test_project_id_alter_before_idx_sessions_project_status_updated(self) -> None:
        """sessions.project_id ALTER must precede idx_sessions_project_status_updated."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_status_idx = self.db.index_of("idx_sessions_project_status_updated")

        self.assertGreater(alter_idx, -1, "Expected ALTER TABLE sessions ADD COLUMN project_id")
        self.assertGreater(idx_status_idx, -1, "Expected idx_sessions_project_status_updated")
        self.assertLess(
            alter_idx,
            idx_status_idx,
            "sessions.project_id ALTER must precede idx_sessions_project_status_updated; "
            f"got ALTER at {alter_idx}, index at {idx_status_idx}",
        )

    def test_project_id_alter_before_idx_sessions_project_source_file(self) -> None:
        """sessions.project_id ALTER must precede idx_sessions_project_source_file."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_source_idx = self.db.index_of("idx_sessions_project_source_file")

        self.assertGreater(alter_idx, -1, "Expected ALTER TABLE sessions ADD COLUMN project_id")
        self.assertGreater(idx_source_idx, -1, "Expected idx_sessions_project_source_file")
        self.assertLess(
            alter_idx,
            idx_source_idx,
            "sessions.project_id ALTER must precede idx_sessions_project_source_file; "
            f"got ALTER at {alter_idx}, index at {idx_source_idx}",
        )

    def test_all_three_project_id_indexes_present(self) -> None:
        """All three project_id-dependent indexes must appear in executed statements."""
        stmts = self.db.executed_statements()
        for idx_name in (
            "idx_sessions_project",
            "idx_sessions_project_status_updated",
            "idx_sessions_project_source_file",
        ):
            found = any(idx_name.upper() in s.upper() for s in stmts)
            self.assertTrue(found, f"Expected {idx_name} in executed statements")

    def test_tables_ddl_executed(self) -> None:
        """_TABLES DDL block must run (current_version < SCHEMA_VERSION path)."""
        # _TABLES is passed as a single multi-statement string to db.execute().
        # The blob is identified by containing the schema_version CREATE TABLE header.
        found = any(
            self.db.is_tables_blob(s)
            for s in self.db.executed_statements()
        )
        self.assertTrue(found, "Expected _TABLES DDL blob to execute for v29 start")


class TestPostgresMigrationsUpgradeFromV0(unittest.TestCase):
    """Verify that a fresh DB (version=0) also gets project_id-dependent indexes correctly."""

    def setUp(self) -> None:
        self.db = _run_migrations(starting_version=0)

    def test_no_exception_raised(self) -> None:
        """_run_migrations_inner must not raise for a fresh DB."""
        self.assertIsNotNone(self.db)

    def test_v30_block_runs_for_fresh_db(self) -> None:
        """v30 block (current_version < 30) must fire for version=0."""
        # On version=0, current_version=0 < 30, so the block runs.
        # The _ensure_column call for project_id must appear.
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        self.assertGreater(
            alter_idx,
            -1,
            "v30 block must run for version=0 DB and add sessions.project_id",
        )

    def test_ordering_preserved_for_fresh_db(self) -> None:
        """Even for a fresh DB, project_id column must precede project_id indexes."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_project_idx = self.db.index_of("idx_sessions_project")
        if idx_project_idx == -1:
            self.skipTest("idx_sessions_project not found — version=0 may have different DDL path")
        self.assertLess(
            alter_idx,
            idx_project_idx,
            "sessions.project_id ALTER must precede idx_sessions_project even for fresh DB",
        )


class TestPostgresMigrationsAlreadyAtV35(unittest.TestCase):
    """Verify that an existing v35 DB is a no-op (idempotency)."""

    def setUp(self) -> None:
        self.db = _run_migrations(starting_version=35)

    def test_no_exception_raised(self) -> None:
        """_run_migrations_inner must not raise for an already-current DB."""
        self.assertIsNotNone(self.db)

    def test_no_new_schema_version_insert(self) -> None:
        """No schema_version INSERT should be emitted for an already-current DB."""
        found = any(
            "INSERT INTO SCHEMA_VERSION" in s.upper()
            for s in self.db.executed_statements()
        )
        self.assertFalse(
            found,
            "Should NOT INSERT INTO schema_version when already at SCHEMA_VERSION=35",
        )

    def test_tables_ddl_skipped(self) -> None:
        """_TABLES DDL block must be skipped for an already-current DB."""
        # _TABLES has CREATE TABLE IF NOT EXISTS schema_version as first statement
        found = any(
            "create table if not exists schema_version" in s.lower()
            for s in self.db.executed_statements()
        )
        self.assertFalse(found, "_TABLES must not run when DB is already at v35")


if __name__ == "__main__":
    unittest.main()
