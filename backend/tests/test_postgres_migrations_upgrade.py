"""Tests for the Postgres migration upgrade path from schema_version=29.

Coverage:
- T1-006 / P1 follow-up: upgrade path from v29 → SCHEMA_VERSION=35 raises no
  exception and applies migrations in the correct order.
- Key ordering assertion: sessions.project_id must be added (via _ensure_column)
  BEFORE any CREATE INDEX that references sessions.project_id.  The mock DB
  raises UndefinedColumnError when a project_id-dependent index fires before the
  column has been ensured, proving the guard is load-bearing.
- Covered indexes:
    * idx_sessions_root (unconditional section)
    * idx_sessions_family (unconditional section)
    * idx_sessions_thread_kind (unconditional section)
    * idx_sessions_project (v30 block)
    * idx_sessions_project_status_updated (v30 block)
    * idx_sessions_project_source_file (v30 block)
- Fresh DB path (version=0): v30 block still runs; _ensure_column is a no-op
  because project_id already exists from _TABLES DDL; no ADD COLUMN emitted.
- Idempotency (version=35): _TABLES blob skipped; no schema_version INSERT.

Run only as a named module (pytest collection hangs in this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_postgres_migrations_upgrade.py -v
"""
from __future__ import annotations

import asyncio
import contextlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Simulated DB error (mirrors asyncpg.UndefinedColumnError semantics)
# ---------------------------------------------------------------------------

class _SimulatedUndefinedColumnError(Exception):
    """Raised by _RecordingDB when a CREATE INDEX references a non-existent column."""


# ---------------------------------------------------------------------------
# Mock DB executor with column-existence enforcement
# ---------------------------------------------------------------------------

# Columns that all sessions tables have at schema_version=29 (pre-v30 state).
# project_id is intentionally ABSENT — it is added by the migration fix.
_V29_SESSIONS_COLUMNS: frozenset[str] = frozenset({
    "id", "task_id", "status", "model", "platform_type", "platform_version",
    "platform_versions_json", "platform_version_transitions_json",
    "duration_seconds", "tokens_in", "tokens_out", "model_io_tokens",
    "cache_creation_input_tokens", "cache_read_input_tokens", "cache_input_tokens",
    "observed_tokens", "current_context_tokens", "context_window_size",
    "context_utilization_pct", "context_measurement_source", "context_measured_at",
    "tool_reported_tokens", "tool_result_input_tokens", "tool_result_output_tokens",
    "tool_result_cache_creation_input_tokens", "tool_result_cache_read_input_tokens",
    "reported_cost_usd", "recalculated_cost_usd", "display_cost_usd",
    "cost_provenance", "cost_confidence", "cost_mismatch_pct", "pricing_model_source",
    "total_cost", "quality_rating", "friction_rating",
    "git_commit_hash", "git_commit_hashes_json", "git_author", "git_branch",
    "session_type", "parent_session_id", "root_session_id", "agent_id",
    "thread_kind", "conversation_family_id", "context_inheritance",
    "fork_parent_session_id", "fork_point_log_id", "fork_point_entry_uuid",
    "fork_point_parent_entry_uuid", "fork_depth", "fork_count",
    "started_at", "ended_at", "created_at", "updated_at", "source_file",
    "dates_json", "timeline_json", "impact_history_json",
    "thinking_level", "session_forensics_json",
    # v28 badge columns
    "command_slug", "latest_summary", "subagent_type",
    "models_used_json", "agents_used_json", "skills_used_json",
    # NOTE: project_id is NOT in this set — it is absent at v29
})

# Columns present in the fresh-DB _TABLES DDL (project_id IS present here).
_FRESH_SESSIONS_COLUMNS: frozenset[str] = _V29_SESSIONS_COLUMNS | {
    "project_id",
    "model_slug", "workflow_id", "subagent_parent_id", "skill_name", "context_window",
    "launcher", "profile", "effort_tier", "model_variant",
}

# Index names that reference sessions.project_id and must be guarded.
_PROJECT_ID_DEPENDENT_INDEXES: frozenset[str] = frozenset({
    "idx_sessions_root",
    "idx_sessions_family",
    "idx_sessions_thread_kind",
    "idx_sessions_project",
    "idx_sessions_project_status_updated",
    "idx_sessions_project_source_file",
})


class _RecordingDB:
    """Minimal asyncpg.Connection mock that records executed statements in order
    and enforces column-existence for sessions CREATE INDEX operations.

    When a CREATE INDEX referencing sessions.project_id executes before
    _ensure_column / ALTER TABLE has added that column, the mock raises
    _SimulatedUndefinedColumnError — matching the real Postgres behaviour
    that this test exists to guard against.

    Column-tracking semantics mirror real Postgres behaviour:
    - starting_version == 0 (fresh DB, no schema_version table): _TABLES runs
      and creates sessions including project_id, so the column is present from
      the moment the blob executes.
    - starting_version > 0 (pre-existing DB): sessions already exists, so the
      CREATE TABLE IF NOT EXISTS in _TABLES is a no-op and does NOT add any
      column.  project_id only arrives via _ensure_column → ALTER TABLE.
    """

    def __init__(self, starting_version: int = 29) -> None:
        self._version = starting_version
        self._executed: list[str] = []
        # For pre-existing DBs, sessions lacks project_id until _ensure_column
        # emits ALTER TABLE sessions ADD COLUMN project_id.
        # For fresh DBs (version=0), sessions is created with all columns by
        # the _TABLES DDL blob, so project_id is present from the start.
        if starting_version == 0:
            # version=0 means no schema_version table → _TABLES runs and creates
            # sessions with project_id already present.
            self._sessions_columns: set[str] = set(_FRESH_SESSIONS_COLUMNS)
        else:
            # Pre-existing DB: sessions was created without project_id.
            self._sessions_columns = set(_V29_SESSIONS_COLUMNS)

    # -- asyncpg Connection interface -----------------------------------------

    async def fetchrow(self, query: str, *args):
        """Simulate catalog queries used by the migration runner."""
        q = query.strip().upper()

        # schema_version read at the start of _run_migrations_inner
        if "FROM SCHEMA_VERSION" in q and "MAX" in q:
            if self._version == 0:
                return None  # table doesn't exist yet → except path → current_version=0
            row = MagicMock()
            row.__getitem__ = lambda _self, _k: self._version  # type: ignore[assignment]
            row.__bool__ = lambda _self: True  # type: ignore[assignment]
            return row

        # _column_exists: information_schema.columns lookup
        if "INFORMATION_SCHEMA.COLUMNS" in q:
            table = args[0] if args else ""
            col = args[1] if len(args) > 1 else ""
            if table == "sessions":
                if col in self._sessions_columns:
                    row = MagicMock()
                    row.__bool__ = lambda _self: True  # type: ignore[assignment]
                    return row
                return None
            # All columns on other tables assumed to exist
            row = MagicMock()
            row.__bool__ = lambda _self: True  # type: ignore[assignment]
            return row

        # sessions composite PK check for v31 idempotency guard
        if "PRIMARY KEY" in q and "SESSIONS" in q:
            return None  # pretend composite PK doesn't exist yet

        return None

    async def fetch(self, _query: str, *_args) -> list:
        """Return empty list for all catalog queries (FK lookups etc.)."""
        return []

    async def execute(self, query: str, *_args) -> None:
        """Record the statement; enforce column existence for guarded indexes.

        Raises _SimulatedUndefinedColumnError if any project_id-dependent
        sessions index executes before sessions.project_id has been added.

        Column-tracking rules:
        - ALTER TABLE sessions ADD COLUMN <col>: adds <col> to the tracked set.
        - CREATE TABLE IF NOT EXISTS sessions (the _TABLES blob): only seeds
          _FRESH_SESSIONS_COLUMNS when starting_version == 0 (fresh DB that
          does not yet have a sessions table).  For pre-existing DBs this is a
          no-op in real Postgres, so the mock must not update the column set.
        """
        stmt = query.strip()

        # Detect ALTER TABLE sessions ADD COLUMN <col> and update our tracking set.
        stmt_upper = stmt.upper()
        if "ALTER TABLE SESSIONS ADD COLUMN" in stmt_upper:
            # Extract column name: "ALTER TABLE sessions ADD COLUMN <col> <def>"
            tokens = stmt.split()
            # tokens: ALTER TABLE sessions ADD COLUMN <col> ...
            if len(tokens) >= 6:
                col_name = tokens[5].lower()
                self._sessions_columns.add(col_name)

        # Detect CREATE TABLE IF NOT EXISTS sessions (the _TABLES blob).
        # On a pre-existing DB (starting_version > 0) this CREATE TABLE is a
        # no-op — Postgres does NOT add columns to an existing table.  Only
        # for starting_version == 0 does _TABLES actually create the sessions
        # table (with all modern columns including project_id).
        if "CREATE TABLE IF NOT EXISTS sessions" in stmt_upper and len(stmt) > 200:
            if self._version == 0:
                # Fresh DB: _TABLES creates sessions with project_id and all
                # modern columns.
                self._sessions_columns = set(_FRESH_SESSIONS_COLUMNS)
            # else: pre-existing DB — no-op; column set unchanged.

        # Enforce: project_id-dependent sessions indexes must not fire before
        # project_id exists in our tracked column set.
        #
        # Guard scope: skip the _TABLES blob entirely.  The blob contains some
        # of these index names in SQL comment text (e.g. the NOTE comment about
        # T1-002 P1-fix) and also contains "on sessions" from the unrelated
        # idx_sessions_source_file DDL.  The blob never contains an actual
        # "CREATE INDEX ... idx_sessions_project_* ON sessions" statement —
        # those were moved into the versioned v30 block.  Checking the blob
        # would produce false positives because the name+context match is
        # coincidental (comment text + unrelated ON SESSIONS clause).
        if not self.is_tables_blob(stmt):
            stmt_lower = stmt.lower()
            for idx_name in _PROJECT_ID_DEPENDENT_INDEXES:
                if idx_name in stmt_lower and "on sessions" in stmt_lower:
                    if "project_id" not in self._sessions_columns:
                        raise _SimulatedUndefinedColumnError(
                            f"column sessions.project_id does not exist "
                            f"(raised by _RecordingDB when executing {idx_name})"
                        )
                    break

        self._executed.append(stmt)

    # -- Introspection helpers -----------------------------------------------

    def executed_statements(self) -> list[str]:
        """Return the ordered list of all executed SQL statements."""
        return list(self._executed)

    def is_tables_blob(self, stmt: str) -> bool:
        """Return True if *stmt* is the _TABLES multi-statement blob.

        _TABLES starts with a SQL comment header followed by CREATE TABLE
        statements.  We identify it by the schema_version table definition
        appearing within the first 512 chars (after the comment preamble).
        """
        return "CREATE TABLE IF NOT EXISTS schema_version" in stmt[:512]

    def index_of(self, fragment: str, *, skip_tables_blob: bool = True) -> int:
        """Return the list-index of the first *standalone* statement containing
        *fragment* (case-insensitive).

        By default, skips the _TABLES blob to avoid false positives from
        comment text or DDL inside that single large string.
        Set skip_tables_blob=False to include the blob.
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
# Helper: run _run_migrations_inner against a _RecordingDB
# ---------------------------------------------------------------------------

def _run_migrations(starting_version: int = 29) -> _RecordingDB:
    """Run _run_migrations_inner with a mock DB at *starting_version*.

    Patches out heavy coroutine helpers that need a real PG connection.
    Returns the _RecordingDB for statement inspection.
    May raise _SimulatedUndefinedColumnError if the migration ordering is wrong.
    """
    from backend.db import postgres_migrations as pm

    db = _RecordingDB(starting_version=starting_version)
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
        asyncio.run(pm._run_migrations_inner(db))  # type: ignore[arg-type]

    return db


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestPostgresMigrationsUpgradeFromV29(unittest.TestCase):
    """Upgrade from schema_version=29 must reach v35 with correct DDL ordering."""

    def setUp(self) -> None:
        self.db = _run_migrations(starting_version=29)

    def test_no_exception_raised(self) -> None:
        """_run_migrations_inner must not raise when upgrading from v29."""
        self.assertIsNotNone(self.db)

    def test_final_schema_version_recorded(self) -> None:
        """schema_version INSERT must be present in the executed statements."""
        found = any(
            "INSERT INTO SCHEMA_VERSION" in s.upper()
            for s in self.db.executed_statements()
        )
        self.assertTrue(found, "Expected INSERT INTO schema_version in executed statements")

    # -- Unconditional section: idx_sessions_root / _family / _thread_kind ----

    def test_project_id_before_idx_sessions_root(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_root."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_root")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_root in executed statements")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_root (pos {idx_pos})",
        )

    def test_project_id_before_idx_sessions_family(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_family."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_family")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_family in executed statements")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_family (pos {idx_pos})",
        )

    def test_project_id_before_idx_sessions_thread_kind(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_thread_kind."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_thread_kind")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_thread_kind in executed statements")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_thread_kind (pos {idx_pos})",
        )

    # -- v30 block indexes ---------------------------------------------------

    def test_project_id_before_idx_sessions_project(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_project."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_project")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_project in executed statements")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_project (pos {idx_pos})",
        )

    def test_project_id_before_idx_sessions_project_status_updated(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_project_status_updated."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_project_status_updated")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_project_status_updated")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_project_status_updated (pos {idx_pos})",
        )

    def test_project_id_before_idx_sessions_project_source_file(self) -> None:
        """sessions.project_id ensure must precede idx_sessions_project_source_file."""
        alter_idx = self.db.index_of("ADD COLUMN project_id")
        idx_pos = self.db.index_of("idx_sessions_project_source_file")
        self.assertGreater(alter_idx, -1, "Expected _ensure_column sessions.project_id ALTER TABLE")
        self.assertGreater(idx_pos, -1, "Expected idx_sessions_project_source_file")
        self.assertLess(
            alter_idx, idx_pos,
            f"sessions.project_id ensure (pos {alter_idx}) must precede "
            f"idx_sessions_project_source_file (pos {idx_pos})",
        )

    def test_all_six_project_id_indexes_present(self) -> None:
        """All six project_id-dependent sessions indexes must appear."""
        stmts = self.db.executed_statements()
        for idx_name in _PROJECT_ID_DEPENDENT_INDEXES:
            found = any(idx_name.upper() in s.upper() for s in stmts)
            self.assertTrue(found, f"Expected {idx_name} in executed statements")

    def test_tables_ddl_executed(self) -> None:
        """_TABLES DDL blob must execute for v29 (current_version < SCHEMA_VERSION)."""
        found = any(self.db.is_tables_blob(s) for s in self.db.executed_statements())
        self.assertTrue(found, "Expected _TABLES DDL blob to execute for v29 start")


class TestPostgresMigrationsBugGuard(unittest.TestCase):
    """Confirm the mock raises _SimulatedUndefinedColumnError when the fix is absent.

    We simulate 'fix absent' by running with a _RecordingDB that starts with
    project_id absent but temporarily patching _ensure_column so that it never
    adds project_id to the column set.  This proves the test infrastructure
    actually guards the ordering invariant.
    """

    def test_mock_raises_without_ensure_column(self) -> None:
        """_RecordingDB must raise when a project_id index executes before the column."""
        from backend.db import postgres_migrations as pm

        db = _RecordingDB(starting_version=29)

        # Override _ensure_column to be a complete no-op that does NOT update
        # the column tracking set (simulating the bug: column never added).
        async def _noop_ensure_column(*_args, **_kwargs) -> None:
            pass

        noop = AsyncMock()
        patches = [
            patch.object(pm, "_ensure_column", _noop_ensure_column),
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
            with self.assertRaises(_SimulatedUndefinedColumnError) as ctx:
                asyncio.run(pm._run_migrations_inner(db))  # type: ignore[arg-type]

        self.assertIn("project_id", str(ctx.exception))


class TestPostgresMigrationsUpgradeFromV0(unittest.TestCase):
    """Fresh DB (version=0) must also produce a complete schema with correct ordering."""

    def setUp(self) -> None:
        self.db = _run_migrations(starting_version=0)

    def test_no_exception_raised(self) -> None:
        """_run_migrations_inner must not raise for a fresh DB."""
        self.assertIsNotNone(self.db)

    def test_v30_block_runs_for_fresh_db(self) -> None:
        """v30 block (current_version=0 < 30) must fire and the project_id indexes appear.

        On a fresh DB, project_id is already present from the _TABLES DDL, so
        _ensure_column at ~line 2408 and ~line 3093 are both no-ops — no ALTER
        TABLE is emitted.  The test confirms:
        1. No _SimulatedUndefinedColumnError is raised (setUp passes without error).
        2. The v30-block indexes (which reference project_id) are present in the
           executed statements, proving the block ran.
        3. The final schema_version INSERT is recorded.
        """
        # v30 block must have run: at least one of its project_id indexes must appear.
        v30_index_found = any(
            self.db.has_statement(idx)
            for idx in ("idx_sessions_project", "idx_sessions_project_status_updated",
                        "idx_sessions_project_source_file")
        )
        self.assertTrue(
            v30_index_found,
            "v30 block must run for version=0 DB (project_id-dependent indexes must appear)",
        )
        # Final version must be recorded.
        version_recorded = any(
            "INSERT INTO SCHEMA_VERSION" in s.upper()
            for s in self.db.executed_statements()
        )
        self.assertTrue(version_recorded, "schema_version INSERT must be recorded for fresh DB")

    def test_ordering_preserved_for_fresh_db(self) -> None:
        """For a fresh DB, no _SimulatedUndefinedColumnError means ordering is correct.

        project_id is present from _TABLES DDL (starting_version=0), so the
        mock never raises — this test passes if setUp completes without error.
        We additionally assert that all six guarded indexes are present.
        """
        stmts = self.db.executed_statements()
        for idx_name in _PROJECT_ID_DEPENDENT_INDEXES:
            found = any(idx_name.upper() in s.upper() for s in stmts)
            self.assertTrue(found, f"Expected {idx_name} in executed statements for fresh DB")


class TestPostgresMigrationsAlreadyAtV35(unittest.TestCase):
    """Idempotency: v35 DB must skip _TABLES and not re-insert schema_version."""

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
        """_TABLES DDL blob must be skipped for an already-current DB."""
        found = any(self.db.is_tables_blob(s) for s in self.db.executed_statements())
        self.assertFalse(found, "_TABLES must not run when DB is already at v35")


if __name__ == "__main__":
    unittest.main()
