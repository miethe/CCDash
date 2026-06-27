"""Assert that the three composite indexes added for query-gap remediation exist after migration.

Each test queries sqlite_master to confirm the index was created by run_migrations().
Covers:
  - idx_sessions_conversation_family  ON sessions(conversation_family_id)
  - idx_features_project_status       ON features(project_id, status)
  - idx_phases_feature_status         ON feature_phases(feature_id, status)

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_composite_index_migration.py -v
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _index_exists(db: aiosqlite.Connection, index_name: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ) as cur:
        return await cur.fetchone() is not None


async def _index_covers_columns(
    db: aiosqlite.Connection, index_name: str, *expected_columns: str
) -> bool:
    """Return True if all expected_columns appear in the index's PRAGMA info."""
    async with db.execute(f"PRAGMA index_info({index_name!r})") as cur:
        rows = await cur.fetchall()
    actual_columns = {row[2] for row in rows}  # column (2) is the name
    return set(expected_columns) <= actual_columns


# ---------------------------------------------------------------------------
# New composite index assertions
# ---------------------------------------------------------------------------

class TestCompositeIndexMigration(unittest.IsolatedAsyncioTestCase):
    """Verify that all three gap-remediation indexes are present after migration."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # --- idx_sessions_conversation_family ---

    async def test_idx_sessions_conversation_family_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_conversation_family"),
            "Missing idx_sessions_conversation_family on sessions(conversation_family_id)",
        )

    async def test_idx_sessions_conversation_family_covers_column(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_sessions_conversation_family", "conversation_family_id"
            ),
            "idx_sessions_conversation_family does not cover conversation_family_id",
        )

    # --- idx_features_project_status ---

    async def test_idx_features_project_status_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_project_status"),
            "Missing idx_features_project_status on features(project_id, status)",
        )

    async def test_idx_features_project_status_covers_columns(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_features_project_status", "project_id", "status"
            ),
            "idx_features_project_status does not cover (project_id, status)",
        )

    # --- idx_phases_feature_status ---

    async def test_idx_phases_feature_status_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_phases_feature_status"),
            "Missing idx_phases_feature_status on feature_phases(feature_id, status)",
        )

    async def test_idx_phases_feature_status_covers_columns(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_phases_feature_status", "feature_id", "status"
            ),
            "idx_phases_feature_status does not cover (feature_id, status)",
        )

    # --- Regression guard: pre-existing single-column indexes must still exist ---

    async def test_preexisting_idx_features_project_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_project"),
            "Regression: idx_features_project was removed",
        )

    async def test_preexisting_idx_phases_feature_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_phases_feature"),
            "Regression: idx_phases_feature was removed",
        )

    async def test_preexisting_idx_sessions_family_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_family"),
            "Regression: idx_sessions_family was removed",
        )


# ---------------------------------------------------------------------------
# v31 composite PK regression: drift column + leftover staging table
# ---------------------------------------------------------------------------

# Pre-v31 sessions DDL: single-column PK + orphan drift column source_ref
_PRE_V31_SESSIONS_DDL = """
CREATE TABLE sessions (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL DEFAULT '',
    task_id           TEXT DEFAULT '',
    status            TEXT DEFAULT 'completed',
    model             TEXT DEFAULT '',
    platform_type     TEXT DEFAULT 'Claude Code',
    platform_version  TEXT DEFAULT '',
    platform_versions_json TEXT DEFAULT '[]',
    platform_version_transitions_json TEXT DEFAULT '[]',
    duration_seconds  INTEGER DEFAULT 0,
    tokens_in         INTEGER DEFAULT 0,
    tokens_out        INTEGER DEFAULT 0,
    model_io_tokens   INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    cache_input_tokens INTEGER DEFAULT 0,
    observed_tokens   INTEGER DEFAULT 0,
    current_context_tokens INTEGER DEFAULT 0,
    context_window_size INTEGER DEFAULT 0,
    context_utilization_pct REAL DEFAULT 0.0,
    context_measurement_source TEXT DEFAULT '',
    context_measured_at TEXT DEFAULT '',
    tool_reported_tokens INTEGER DEFAULT 0,
    tool_result_input_tokens INTEGER DEFAULT 0,
    tool_result_output_tokens INTEGER DEFAULT 0,
    tool_result_cache_creation_input_tokens INTEGER DEFAULT 0,
    tool_result_cache_read_input_tokens INTEGER DEFAULT 0,
    reported_cost_usd REAL,
    recalculated_cost_usd REAL,
    display_cost_usd  REAL,
    cost_provenance   TEXT DEFAULT 'unknown',
    cost_confidence   REAL DEFAULT 0.0,
    cost_mismatch_pct REAL,
    pricing_model_source TEXT DEFAULT '',
    total_cost        REAL DEFAULT 0.0,
    quality_rating    INTEGER DEFAULT 0,
    friction_rating   INTEGER DEFAULT 0,
    git_commit_hash   TEXT,
    git_commit_hashes_json TEXT DEFAULT '[]',
    git_author        TEXT,
    git_branch        TEXT,
    session_type      TEXT DEFAULT '',
    parent_session_id TEXT,
    root_session_id   TEXT DEFAULT '',
    agent_id          TEXT,
    thread_kind       TEXT DEFAULT '',
    conversation_family_id TEXT DEFAULT '',
    context_inheritance TEXT DEFAULT '',
    fork_parent_session_id TEXT,
    fork_point_log_id TEXT,
    fork_point_entry_uuid TEXT,
    fork_point_parent_entry_uuid TEXT,
    fork_depth        INTEGER DEFAULT 0,
    fork_count        INTEGER DEFAULT 0,
    started_at        TEXT DEFAULT '',
    ended_at          TEXT DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    source_file       TEXT NOT NULL DEFAULT '',
    dates_json        TEXT DEFAULT '{}',
    timeline_json     TEXT DEFAULT '[]',
    impact_history_json TEXT DEFAULT '[]',
    thinking_level    TEXT DEFAULT '',
    session_forensics_json TEXT DEFAULT '{}',
    command_slug      TEXT DEFAULT '',
    latest_summary    TEXT DEFAULT '',
    subagent_type     TEXT DEFAULT '',
    models_used_json  TEXT DEFAULT '[]',
    agents_used_json  TEXT DEFAULT '[]',
    skills_used_json  TEXT DEFAULT '[]',
    source_ref        TEXT
)
"""

# Minimal child table DDLs — just enough columns for the migration to proceed
_CHILD_TABLE_DDLS = [
    """CREATE TABLE session_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id    TEXT NOT NULL,
        log_index     INTEGER NOT NULL DEFAULT 0,
        source_log_id TEXT DEFAULT '',
        timestamp     TEXT NOT NULL DEFAULT '',
        speaker       TEXT NOT NULL DEFAULT '',
        type          TEXT NOT NULL DEFAULT '',
        content       TEXT DEFAULT '',
        tool_status   TEXT DEFAULT 'success'
    )""",
    """CREATE TABLE session_messages (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id    TEXT NOT NULL,
        message_index INTEGER NOT NULL DEFAULT 0,
        source_log_id TEXT DEFAULT '',
        message_id    TEXT DEFAULT '',
        role          TEXT NOT NULL DEFAULT '',
        message_type  TEXT NOT NULL DEFAULT '',
        content       TEXT DEFAULT '',
        event_timestamp TEXT NOT NULL DEFAULT '',
        source_provenance TEXT NOT NULL DEFAULT 'session_log_projection'
    )""",
    """CREATE TABLE session_tool_usage (
        session_id  TEXT NOT NULL,
        tool_name   TEXT NOT NULL,
        call_count  INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        total_ms    INTEGER DEFAULT 0,
        PRIMARY KEY (session_id, tool_name)
    )""",
    """CREATE TABLE session_file_updates (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT NOT NULL,
        file_path   TEXT NOT NULL,
        action      TEXT DEFAULT 'update',
        file_type   TEXT DEFAULT 'Other',
        action_timestamp TEXT DEFAULT '',
        additions   INTEGER DEFAULT 0,
        deletions   INTEGER DEFAULT 0
    )""",
    """CREATE TABLE session_artifacts (
        id          TEXT PRIMARY KEY,
        session_id  TEXT NOT NULL,
        title       TEXT NOT NULL DEFAULT '',
        type        TEXT DEFAULT 'document',
        description TEXT DEFAULT '',
        source      TEXT DEFAULT ''
    )""",
    """CREATE TABLE session_usage_events (
        id              TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL DEFAULT '',
        session_id      TEXT NOT NULL,
        root_session_id TEXT NOT NULL DEFAULT '',
        linked_session_id TEXT DEFAULT '',
        source_log_id   TEXT DEFAULT '',
        captured_at     TEXT NOT NULL DEFAULT '',
        event_kind      TEXT NOT NULL DEFAULT '',
        model           TEXT DEFAULT '',
        tool_name       TEXT DEFAULT '',
        agent_name      TEXT DEFAULT '',
        token_family    TEXT NOT NULL DEFAULT '',
        delta_tokens    INTEGER NOT NULL DEFAULT 0,
        cost_usd_model_io REAL NOT NULL DEFAULT 0.0,
        metadata_json   TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE session_relationships (
        id                TEXT PRIMARY KEY,
        project_id        TEXT NOT NULL DEFAULT '',
        parent_session_id TEXT NOT NULL DEFAULT '',
        child_session_id  TEXT NOT NULL DEFAULT '',
        relationship_type TEXT NOT NULL DEFAULT '',
        context_inheritance TEXT DEFAULT '',
        source_platform   TEXT DEFAULT '',
        parent_entry_uuid TEXT DEFAULT '',
        child_entry_uuid  TEXT DEFAULT '',
        source_log_id     TEXT,
        metadata_json     TEXT DEFAULT '{}',
        source_file       TEXT DEFAULT '',
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE session_sentiment_facts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT NOT NULL,
        feature_id      TEXT DEFAULT '',
        root_session_id TEXT DEFAULT '',
        message_index   INTEGER NOT NULL DEFAULT 0,
        sentiment_label TEXT NOT NULL DEFAULT 'neutral',
        sentiment_score REAL NOT NULL DEFAULT 0.0,
        confidence      REAL NOT NULL DEFAULT 0.0,
        computed_at     TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE session_code_churn_facts (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id        TEXT NOT NULL,
        feature_id        TEXT DEFAULT '',
        file_path         TEXT NOT NULL DEFAULT '',
        touch_count       INTEGER NOT NULL DEFAULT 0,
        churn_score       REAL NOT NULL DEFAULT 0.0,
        progress_score    REAL NOT NULL DEFAULT 0.0,
        confidence        REAL NOT NULL DEFAULT 0.0,
        first_message_index INTEGER NOT NULL DEFAULT 0,
        last_message_index  INTEGER NOT NULL DEFAULT 0,
        computed_at       TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE session_scope_drift_facts (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              TEXT NOT NULL,
        feature_id              TEXT DEFAULT '',
        planned_path_count      INTEGER NOT NULL DEFAULT 0,
        actual_path_count       INTEGER NOT NULL DEFAULT 0,
        matched_path_count      INTEGER NOT NULL DEFAULT 0,
        out_of_scope_path_count INTEGER NOT NULL DEFAULT 0,
        drift_ratio             REAL NOT NULL DEFAULT 0.0,
        adherence_score         REAL NOT NULL DEFAULT 0.0,
        confidence              REAL NOT NULL DEFAULT 0.0,
        computed_at             TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE session_stack_observations (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id         TEXT NOT NULL DEFAULT '',
        session_id         TEXT NOT NULL,
        feature_id         TEXT DEFAULT '',
        workflow_ref       TEXT DEFAULT '',
        confidence         REAL DEFAULT 0.0,
        observation_source TEXT DEFAULT 'backfill',
        evidence_json      TEXT DEFAULT '{}',
        created_at         TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(project_id, session_id)
    )""",
    """CREATE TABLE session_memory_drafts (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id           TEXT NOT NULL DEFAULT '',
        session_id           TEXT NOT NULL,
        feature_id           TEXT DEFAULT '',
        memory_type          TEXT NOT NULL DEFAULT 'learning',
        status               TEXT NOT NULL DEFAULT 'draft',
        module_name          TEXT NOT NULL DEFAULT '',
        content              TEXT NOT NULL DEFAULT '',
        confidence           REAL NOT NULL DEFAULT 0.0,
        source_message_index INTEGER NOT NULL DEFAULT 0,
        content_hash         TEXT NOT NULL DEFAULT '',
        evidence_json        TEXT NOT NULL DEFAULT '{}',
        publish_attempts     INTEGER NOT NULL DEFAULT 0,
        created_at           TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(project_id, content_hash)
    )""",
]


async def _build_pre_v31_db(db: aiosqlite.Connection) -> None:
    """Set up a pre-v31 DB state:
    - sessions with single-column PK + orphan drift column source_ref
    - 3 seed rows in sessions
    - 2 rows in session_logs (child table)
    - All other required child tables (empty)
    - A leftover sessions_new staging table to exercise the DROP guard
    """
    await db.execute(_PRE_V31_SESSIONS_DDL)
    for ddl in _CHILD_TABLE_DDLS:
        await db.execute(ddl)

    # Seed sessions rows
    for i in range(1, 4):
        await db.execute(
            "INSERT INTO sessions (id, project_id, source_file, created_at, updated_at, source_ref) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?)",
            (f"sess-{i}", "proj-a", f"/path/to/sess{i}.jsonl", f"ref-{i}"),
        )

    # Seed session_logs rows
    await db.execute(
        "INSERT INTO session_logs (session_id, log_index, timestamp, speaker, type) "
        "VALUES ('sess-1', 0, datetime('now'), 'human', 'message')"
    )
    await db.execute(
        "INSERT INTO session_logs (session_id, log_index, timestamp, speaker, type) "
        "VALUES ('sess-2', 0, datetime('now'), 'assistant', 'message')"
    )

    # Leftover staging table from a prior partial failure — exercises DROP guard
    await db.execute("CREATE TABLE sessions_new (id TEXT PRIMARY KEY)")

    await db.commit()


class TestV31DriftColumnAndIdempotencyGuard(unittest.IsolatedAsyncioTestCase):
    """Regression: v31 migration must handle a drift column (source_ref) in sessions
    and a leftover sessions_new staging table from a prior partial run.
    """

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        await _build_pre_v31_db(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_migration_completes_without_error(self) -> None:
        """The migration must not raise despite source_ref drift and leftover sessions_new."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        # Should not raise
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)

    async def test_sessions_has_composite_pk(self) -> None:
        """After migration, sessions table DDL must declare composite PK."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
        async with self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'"
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, "sessions table not found after migration")
        assert row is not None
        self.assertIn(
            "PRIMARY KEY (project_id, id)",
            row[0],
            "sessions does not have composite PRIMARY KEY (project_id, id)",
        )

    async def test_source_ref_column_dropped(self) -> None:
        """Drift column source_ref must not exist in sessions after migration."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
        async with self.db.execute("PRAGMA table_info(sessions)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        self.assertNotIn(
            "source_ref",
            cols,
            "Drift column source_ref survived the sessions rebuild",
        )

    async def test_row_count_preserved(self) -> None:
        """All 3 original sessions rows must survive the rebuild."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
        async with self.db.execute("SELECT COUNT(*) FROM sessions") as cur:
            count_row = await cur.fetchone()
        assert count_row is not None
        self.assertEqual(count_row[0], 3, f"Expected 3 sessions rows; got {count_row[0]}")

    async def test_foreign_key_check_empty(self) -> None:
        """PRAGMA foreign_key_check must return no violations after migration."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
        # Re-enable FK enforcement for the check
        await self.db.execute("PRAGMA foreign_keys=ON")
        async with self.db.execute("PRAGMA foreign_key_check") as cur:
            violations = await cur.fetchall()
        self.assertEqual(
            violations,
            [],
            f"PRAGMA foreign_key_check returned violations: {violations}",
        )

    async def test_idempotent_second_run(self) -> None:
        """Running the migration twice must be a no-op on the second call."""
        from backend.db.sqlite_migrations import _migrate_v31_sessions_composite_pk_and_child_fks
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
        # Second run should be a clean no-op (idempotency check fires)
        await _migrate_v31_sessions_composite_pk_and_child_fks(self.db)
