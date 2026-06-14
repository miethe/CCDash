-- TEST FIXTURE ONLY — not production DDL.
--
-- Minimal PostgreSQL schema snapshot at schema_version=29 for use as a
-- Docker init-script in the docker:hosted:smoke:seeded-pg smoke flow.
--
-- Purpose: verify that _run_migrations_inner can upgrade a pre-v30 Postgres
-- database to SCHEMA_VERSION=35 without raising UndefinedColumnError when
-- creating project_id-dependent indexes on sessions.
--
-- This fixture intentionally omits sessions.project_id (added at v30) and
-- omits idx_sessions_project, idx_sessions_project_status_updated, and
-- idx_sessions_project_source_file (all depend on that column).
-- A correct migration run must add the column and create those indexes.
--
-- Used by: deploy/runtime/scripts/smoke-seeded-pg.sh
--          npm run docker:hosted:smoke:seeded-pg
--
-- DO NOT use as a reference for the current production schema.
-- The authoritative DDL is backend/db/postgres_migrations.py (_TABLES).

-- ── Schema version tracking ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER NOT NULL,
    applied   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES (29);

-- ── Migrations applied ledger ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS migrations_applied (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO migrations_applied (version) VALUES (1),(2),(3),(4),(5),(6),(7),(8),
    (9),(10),(11),(12),(13),(14),(15),(16),(17),(18),(19),(20),
    (21),(22),(23),(24),(25),(26),(27),(28),(29)
ON CONFLICT DO NOTHING;

-- ── Sessions table (pre-v30: no project_id column, no composite PK) ────────
-- At v29 the sessions table used a single-column TEXT primary key on id.
-- project_id is intentionally absent — this is what the v30 migration adds.
CREATE TABLE IF NOT EXISTS sessions (
    id               TEXT PRIMARY KEY,
    task_id          TEXT DEFAULT '',
    status           TEXT DEFAULT 'completed',
    model            TEXT DEFAULT '',
    platform_type    TEXT DEFAULT 'Claude Code',
    platform_version TEXT DEFAULT '',
    platform_versions_json TEXT DEFAULT '[]',
    platform_version_transitions_json TEXT DEFAULT '[]',
    duration_seconds INTEGER DEFAULT 0,
    tokens_in        INTEGER DEFAULT 0,
    tokens_out       INTEGER DEFAULT 0,
    model_io_tokens  INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    cache_input_tokens INTEGER DEFAULT 0,
    observed_tokens  INTEGER DEFAULT 0,
    current_context_tokens INTEGER DEFAULT 0,
    context_window_size INTEGER DEFAULT 0,
    context_utilization_pct DOUBLE PRECISION DEFAULT 0.0,
    context_measurement_source TEXT DEFAULT '',
    context_measured_at TEXT DEFAULT '',
    tool_reported_tokens INTEGER DEFAULT 0,
    tool_result_input_tokens INTEGER DEFAULT 0,
    tool_result_output_tokens INTEGER DEFAULT 0,
    tool_result_cache_creation_input_tokens INTEGER DEFAULT 0,
    tool_result_cache_read_input_tokens INTEGER DEFAULT 0,
    reported_cost_usd DOUBLE PRECISION,
    recalculated_cost_usd DOUBLE PRECISION,
    display_cost_usd DOUBLE PRECISION,
    cost_provenance TEXT DEFAULT 'unknown',
    cost_confidence DOUBLE PRECISION DEFAULT 0.0,
    cost_mismatch_pct DOUBLE PRECISION,
    pricing_model_source TEXT DEFAULT '',
    total_cost       DOUBLE PRECISION DEFAULT 0.0,
    quality_rating   INTEGER DEFAULT 0,
    friction_rating  INTEGER DEFAULT 0,
    git_commit_hash  TEXT,
    git_commit_hashes_json TEXT DEFAULT '[]',
    git_author       TEXT,
    git_branch       TEXT,
    session_type     TEXT DEFAULT '',
    parent_session_id TEXT,
    root_session_id  TEXT DEFAULT '',
    agent_id         TEXT,
    thread_kind      TEXT DEFAULT '',
    conversation_family_id TEXT DEFAULT '',
    context_inheritance TEXT DEFAULT '',
    fork_parent_session_id TEXT,
    fork_point_log_id TEXT,
    fork_point_entry_uuid TEXT,
    fork_point_parent_entry_uuid TEXT,
    fork_depth       INTEGER DEFAULT 0,
    fork_count       INTEGER DEFAULT 0,
    started_at       TEXT DEFAULT '',
    ended_at         TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    source_file      TEXT NOT NULL,
    dates_json       TEXT DEFAULT '{}',
    timeline_json    TEXT DEFAULT '[]',
    impact_history_json TEXT DEFAULT '[]',
    thinking_level   TEXT DEFAULT '',
    session_forensics_json TEXT DEFAULT '{}',
    -- v28 badge columns
    command_slug     TEXT DEFAULT '',
    latest_summary   TEXT DEFAULT '',
    subagent_type    TEXT DEFAULT '',
    models_used_json TEXT DEFAULT '[]',
    agents_used_json TEXT DEFAULT '[]',
    skills_used_json TEXT DEFAULT '[]'
    -- NOTE: project_id column is intentionally absent here.
    -- The v30 migration (_migrate_v30_detail_tables_project_id via
    -- _ensure_column) must add it.  Indexes that reference project_id
    -- must NOT be created before that column exists.
);

-- Source file index (no project_id dependency — safe at v29)
CREATE INDEX IF NOT EXISTS idx_sessions_source_file ON sessions(source_file);

-- ── Sync state ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_state (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    file_mtime   DOUBLE PRECISION NOT NULL,
    entity_type  TEXT NOT NULL,
    project_id   TEXT NOT NULL,
    last_synced  TEXT NOT NULL,
    parse_ms     INTEGER DEFAULT 0
);

-- ── Query cache (added at v29) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_cache_project ON query_cache(project_id);
CREATE INDEX IF NOT EXISTS idx_query_cache_expires_at ON query_cache(expires_at);
