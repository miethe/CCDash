"""Database schema creation and versioning.

All CREATE TABLE statements for the caching layer.
Uses IF NOT EXISTS for idempotent runs.
"""
from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger("ccdash.db")

SCHEMA_VERSION = 12

_TABLES = """
-- ── Schema version tracking ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER NOT NULL,
    applied   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── 1. Sync State (Incremental Change Detection) ──────────────────
CREATE TABLE IF NOT EXISTS sync_state (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    file_mtime   REAL NOT NULL,
    entity_type  TEXT NOT NULL,
    project_id   TEXT NOT NULL,
    last_synced  TEXT NOT NULL,
    parse_ms     INTEGER DEFAULT 0
);

-- ── 2. Universal Entity Cross-Linking ──────────────────────────────
CREATE TABLE IF NOT EXISTS entity_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type   TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    link_type     TEXT DEFAULT 'related',
    origin        TEXT DEFAULT 'auto',
    confidence    REAL DEFAULT 1.0,
    depth         INTEGER DEFAULT 0,
    sort_order    INTEGER DEFAULT 0,
    metadata_json TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_links_source ON entity_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON entity_links(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_links_tree   ON entity_links(source_type, source_id, link_type, depth);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert ON entity_links(source_type, source_id, target_type, target_id, link_type);
CREATE INDEX IF NOT EXISTS idx_links_origin ON entity_links(origin) WHERE origin = 'manual';

-- External links (URLs, PRs, issues)
CREATE TABLE IF NOT EXISTS external_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    url           TEXT NOT NULL,
    link_label    TEXT DEFAULT '',
    link_category TEXT DEFAULT 'other',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ext_links ON external_links(entity_type, entity_id);

-- ── 3. Tags System ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS entity_tags (
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    PRIMARY KEY (entity_type, entity_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_tags_tag ON entity_tags(tag_id);

-- ── 4. Sessions ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
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
    total_cost       REAL DEFAULT 0.0,
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
    started_at       TEXT DEFAULT '',
    ended_at         TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    source_file      TEXT NOT NULL,
    dates_json       TEXT DEFAULT '{}',
    timeline_json    TEXT DEFAULT '[]',
    impact_history_json TEXT DEFAULT '[]',
    thinking_level   TEXT DEFAULT '',
    session_forensics_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

-- Normalized log entries
CREATE TABLE IF NOT EXISTS session_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    log_index      INTEGER NOT NULL,
    timestamp      TEXT NOT NULL,
    speaker        TEXT NOT NULL,
    type           TEXT NOT NULL,
    content        TEXT DEFAULT '',
    agent_name     TEXT,
    tool_name      TEXT,
    tool_call_id   TEXT,
    related_tool_call_id TEXT,
    linked_session_id TEXT,
    tool_args      TEXT,
    tool_output    TEXT,
    tool_status    TEXT DEFAULT 'success',
    metadata_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_session ON session_logs(session_id, log_index);
CREATE INDEX IF NOT EXISTS idx_logs_tool    ON session_logs(tool_name) WHERE tool_name IS NOT NULL;

-- Tool usage summary per session
CREATE TABLE IF NOT EXISTS session_tool_usage (
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name     TEXT NOT NULL,
    call_count    INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    total_ms      INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, tool_name)
);

-- File changes per session
CREATE TABLE IF NOT EXISTS session_file_updates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    file_path    TEXT NOT NULL,
    action       TEXT DEFAULT 'update',
    file_type    TEXT DEFAULT 'Other',
    action_timestamp TEXT DEFAULT '',
    additions    INTEGER DEFAULT 0,
    deletions    INTEGER DEFAULT 0,
    agent_name   TEXT DEFAULT '',
    thread_session_id TEXT DEFAULT '',
    root_session_id TEXT DEFAULT '',
    source_log_id TEXT,
    source_tool_name TEXT
);

CREATE INDEX IF NOT EXISTS idx_file_updates_session ON session_file_updates(session_id);
CREATE INDEX IF NOT EXISTS idx_file_updates_path   ON session_file_updates(file_path);

-- Session artifacts
CREATE TABLE IF NOT EXISTS session_artifacts (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    type         TEXT DEFAULT 'document',
    description  TEXT DEFAULT '',
    source       TEXT DEFAULT '',
    url          TEXT,
    source_log_id TEXT,
    source_tool_name TEXT
);

-- ── 5. Documents ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    title          TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    canonical_path TEXT DEFAULT '',
    root_kind      TEXT DEFAULT 'project_plans',
    doc_subtype    TEXT DEFAULT '',
    file_name      TEXT DEFAULT '',
    file_stem      TEXT DEFAULT '',
    file_dir       TEXT DEFAULT '',
    has_frontmatter INTEGER DEFAULT 0,
    frontmatter_type TEXT DEFAULT '',
    status         TEXT DEFAULT 'active',
    status_normalized TEXT DEFAULT '',
    author         TEXT DEFAULT '',
    content        TEXT,
    doc_type       TEXT DEFAULT '',
    category       TEXT DEFAULT '',
    feature_slug_hint TEXT DEFAULT '',
    feature_slug_canonical TEXT DEFAULT '',
    prd_ref        TEXT DEFAULT '',
    phase_token    TEXT DEFAULT '',
    phase_number   INTEGER,
    overall_progress REAL,
    total_tasks    INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    in_progress_tasks INTEGER DEFAULT 0,
    blocked_tasks  INTEGER DEFAULT 0,
    metadata_json  TEXT DEFAULT '{}',
    parent_doc_id  TEXT,
    created_at     TEXT DEFAULT '',
    updated_at     TEXT DEFAULT '',
    last_modified  TEXT DEFAULT '',
    frontmatter_json TEXT NOT NULL,
    source_file    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_docs_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_docs_type    ON documents(doc_type);

CREATE TABLE IF NOT EXISTS document_refs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id     TEXT NOT NULL,
    ref_kind       TEXT NOT NULL,
    ref_value      TEXT NOT NULL,
    ref_value_norm TEXT NOT NULL,
    source_field   TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_refs_unique
    ON document_refs(document_id, ref_kind, ref_value_norm, source_field);
CREATE INDEX IF NOT EXISTS idx_document_refs_query
    ON document_refs(project_id, ref_kind, ref_value_norm);

-- ── 6. Tasks ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT DEFAULT '',
    status         TEXT DEFAULT 'backlog',
    priority       TEXT DEFAULT 'medium',
    owner          TEXT DEFAULT '',
    last_agent     TEXT DEFAULT '',
    cost           REAL DEFAULT 0.0,
    task_type      TEXT DEFAULT '',
    project_type   TEXT DEFAULT '',
    project_level  TEXT DEFAULT '',
    parent_task_id TEXT,
    feature_id     TEXT,
    phase_id       TEXT,
    session_id     TEXT DEFAULT '',
    commit_hash    TEXT DEFAULT '',
    created_at     TEXT DEFAULT '',
    updated_at     TEXT DEFAULT '',
    completed_at   TEXT DEFAULT '',
    source_file    TEXT NOT NULL,
    data_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_feature ON tasks(feature_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(project_id, status);

-- ── 7. Features ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS features (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT DEFAULT 'backlog',
    category        TEXT DEFAULT '',
    total_tasks     INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    parent_feature_id TEXT,
    created_at      TEXT DEFAULT '',
    updated_at      TEXT DEFAULT '',
    completed_at    TEXT DEFAULT '',
    data_json       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_features_project ON features(project_id);

CREATE TABLE IF NOT EXISTS feature_phases (
    id              TEXT PRIMARY KEY,
    feature_id      TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    phase           TEXT NOT NULL,
    title           TEXT DEFAULT '',
    status          TEXT DEFAULT 'backlog',
    progress        INTEGER DEFAULT 0,
    total_tasks     INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_phases_feature ON feature_phases(feature_id);

-- ── 8. Analytics ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metric_types (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    unit          TEXT DEFAULT '',
    value_type    TEXT DEFAULT 'gauge',
    aggregation   TEXT DEFAULT 'sum',
    description   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS analytics_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    metric_type   TEXT NOT NULL REFERENCES metric_types(id),
    value         REAL NOT NULL,
    captured_at   TEXT NOT NULL,
    period        TEXT DEFAULT 'point',
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_analytics_lookup
    ON analytics_entries(project_id, metric_type, captured_at);
CREATE INDEX IF NOT EXISTS idx_analytics_period
    ON analytics_entries(project_id, period, captured_at);

CREATE TABLE IF NOT EXISTS analytics_entity_links (
    analytics_id  INTEGER NOT NULL REFERENCES analytics_entries(id) ON DELETE CASCADE,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    PRIMARY KEY (analytics_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_analytics_entity
    ON analytics_entity_links(entity_type, entity_id);

-- ── 9. Telemetry Events (Fact Layer) ────────────────────────────────
CREATE TABLE IF NOT EXISTS telemetry_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    root_session_id TEXT DEFAULT '',
    feature_id      TEXT DEFAULT '',
    task_id         TEXT DEFAULT '',
    commit_hash     TEXT DEFAULT '',
    pr_number       TEXT DEFAULT '',
    phase           TEXT DEFAULT '',
    event_type      TEXT NOT NULL,
    tool_name       TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    agent           TEXT DEFAULT '',
    skill           TEXT DEFAULT '',
    status          TEXT DEFAULT '',
    duration_ms     INTEGER DEFAULT 0,
    token_input     INTEGER DEFAULT 0,
    token_output    INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    occurred_at     TEXT NOT NULL,
    sequence_no     INTEGER DEFAULT 0,
    source          TEXT DEFAULT 'sync',
    source_key      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_source_key
    ON telemetry_events(project_id, source_key);
CREATE INDEX IF NOT EXISTS idx_telemetry_project_time
    ON telemetry_events(project_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_event_type
    ON telemetry_events(project_id, event_type, occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_tool
    ON telemetry_events(project_id, tool_name, occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_model
    ON telemetry_events(project_id, model, occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_feature
    ON telemetry_events(project_id, feature_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_task
    ON telemetry_events(project_id, task_id, occurred_at);

-- ── 10. Commit Correlations ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS commit_correlations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    root_session_id TEXT DEFAULT '',
    commit_hash     TEXT NOT NULL,
    feature_id      TEXT DEFAULT '',
    phase           TEXT DEFAULT '',
    task_id         TEXT DEFAULT '',
    window_start    TEXT NOT NULL,
    window_end      TEXT NOT NULL,
    event_count     INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    command_count   INTEGER DEFAULT 0,
    artifact_count  INTEGER DEFAULT 0,
    token_input     INTEGER DEFAULT 0,
    token_output    INTEGER DEFAULT 0,
    file_count      INTEGER DEFAULT 0,
    additions       INTEGER DEFAULT 0,
    deletions       INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    source          TEXT DEFAULT 'sync',
    source_key      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_commit_corr_source_key
    ON commit_correlations(project_id, source_key);
CREATE INDEX IF NOT EXISTS idx_commit_corr_project_commit
    ON commit_correlations(project_id, commit_hash, window_end);
CREATE INDEX IF NOT EXISTS idx_commit_corr_session
    ON commit_correlations(project_id, session_id, window_end);
CREATE INDEX IF NOT EXISTS idx_commit_corr_feature
    ON commit_correlations(project_id, feature_id, window_end);

-- ── 11. App Metadata + Alert Configs ───────────────────────────────
CREATE TABLE IF NOT EXISTS app_metadata (
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id, key)
);

CREATE TABLE IF NOT EXISTS alert_configs (
    id         TEXT PRIMARY KEY,
    project_id TEXT,
    name       TEXT NOT NULL,
    metric     TEXT NOT NULL,
    operator   TEXT NOT NULL,
    threshold  REAL NOT NULL,
    is_active  INTEGER DEFAULT 1,
    scope      TEXT DEFAULT 'session'
);
"""

_SEED_METRIC_TYPES = """
INSERT OR IGNORE INTO metric_types (id, display_name, unit, value_type, aggregation, description) VALUES
    ('session_cost',        'Session Cost',      '$',       'gauge',   'sum',   'Total cost per session'),
    ('session_tokens',      'Tokens Used',       'tokens',  'counter', 'sum',   'Total tokens consumed'),
    ('session_duration',    'Session Duration',   'seconds', 'gauge',   'avg',   'Average session duration'),
    ('session_count',       'Sessions',          'count',   'counter', 'count', 'Number of sessions'),
    ('task_velocity',       'Tasks Completed',   'count',   'counter', 'count', 'Tasks completed per period'),
    ('task_completion_pct', 'Completion %',      '%',       'gauge',   'avg',   'Task completion percentage'),
    ('feature_progress',    'Feature Progress',  '%',       'gauge',   'avg',   'Feature progress percentage'),
    ('tool_call_count',     'Tool Calls',        'count',   'counter', 'sum',   'Total tool invocations'),
    ('tool_success_rate',   'Tool Success Rate', '%',       'gauge',   'avg',   'Tool call success rate'),
    ('file_churn',          'Files Modified',    'count',   'counter', 'sum',   'Files changed per period');
"""

_SEED_ALERT_CONFIGS = """
INSERT OR IGNORE INTO alert_configs (id, project_id, name, metric, operator, threshold, is_active, scope) VALUES
    ('alert-cost',     NULL, 'Cost Threshold', 'cost_threshold', '>', 5.0,  1, 'session'),
    ('alert-duration', NULL, 'Long Session',   'total_tokens',   '>', 600,  1, 'session'),
    ('alert-friction', NULL, 'High Friction',  'avg_quality',    '<', 3,    0, 'weekly');
"""


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return any(row[1] == column for row in rows)


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, definition: str) -> None:
    if await _column_exists(db, table, column):
        return
    await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def _ensure_index(db: aiosqlite.Connection, ddl: str) -> None:
    await db.execute(ddl)


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Create all tables and seed data. Idempotent."""
    # Check current schema version
    try:
        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            current_version = row[0] if row and row[0] else 0
    except Exception:
        current_version = 0

    if current_version >= SCHEMA_VERSION:
        logger.info(f"Schema is up to date (version {current_version})")
        return

    logger.info(f"Running migrations: {current_version} → {SCHEMA_VERSION}")

    # Execute all CREATE TABLE statements
    await db.executescript(_TABLES)

    # Explicit table upgrades for existing DBs.
    await _ensure_column(db, "sessions", "root_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "agent_id", "TEXT")
    await _ensure_column(db, "sessions", "git_commit_hashes_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "dates_json", "TEXT DEFAULT '{}'")
    await _ensure_column(db, "sessions", "timeline_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "impact_history_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "thinking_level", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "session_forensics_json", "TEXT DEFAULT '{}'")
    await _ensure_column(db, "sessions", "platform_type", "TEXT DEFAULT 'Claude Code'")
    await _ensure_column(db, "sessions", "platform_version", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "platform_versions_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "platform_version_transitions_json", "TEXT DEFAULT '[]'")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_sessions_root ON sessions(project_id, root_session_id, started_at DESC)")

    await _ensure_column(db, "session_logs", "tool_call_id", "TEXT")
    await _ensure_column(db, "session_logs", "related_tool_call_id", "TEXT")
    await _ensure_column(db, "session_logs", "linked_session_id", "TEXT")
    await _ensure_column(db, "session_logs", "metadata_json", "TEXT")
    await _ensure_column(db, "session_tool_usage", "total_ms", "INTEGER DEFAULT 0")

    await _ensure_column(db, "session_file_updates", "source_log_id", "TEXT")
    await _ensure_column(db, "session_file_updates", "source_tool_name", "TEXT")
    await _ensure_column(db, "session_file_updates", "action", "TEXT DEFAULT 'update'")
    await _ensure_column(db, "session_file_updates", "file_type", "TEXT DEFAULT 'Other'")
    await _ensure_column(db, "session_file_updates", "action_timestamp", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_file_updates", "thread_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_file_updates", "root_session_id", "TEXT DEFAULT ''")

    await _ensure_column(db, "session_artifacts", "url", "TEXT")
    await _ensure_column(db, "session_artifacts", "source_log_id", "TEXT")
    await _ensure_column(db, "session_artifacts", "source_tool_name", "TEXT")

    await _ensure_column(db, "documents", "canonical_path", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "root_kind", "TEXT DEFAULT 'project_plans'")
    await _ensure_column(db, "documents", "doc_subtype", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "file_name", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "file_stem", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "file_dir", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "has_frontmatter", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "frontmatter_type", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "status_normalized", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "feature_slug_hint", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "feature_slug_canonical", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "prd_ref", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "phase_token", "TEXT DEFAULT ''")
    await _ensure_column(db, "documents", "phase_number", "INTEGER")
    await _ensure_column(db, "documents", "overall_progress", "REAL")
    await _ensure_column(db, "documents", "total_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "completed_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "in_progress_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "blocked_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "metadata_json", "TEXT DEFAULT '{}'")

    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_docs_canonical_path ON documents(project_id, canonical_path)")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_docs_root_subtype ON documents(project_id, root_kind, doc_subtype)")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_docs_status_norm ON documents(project_id, status_normalized)")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_docs_feature_slug ON documents(project_id, feature_slug_canonical)")
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS document_refs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            project_id     TEXT NOT NULL,
            ref_kind       TEXT NOT NULL,
            ref_value      TEXT NOT NULL,
            ref_value_norm TEXT NOT NULL,
            source_field   TEXT NOT NULL,
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_refs_unique ON document_refs(document_id, ref_kind, ref_value_norm, source_field)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_document_refs_query ON document_refs(project_id, ref_kind, ref_value_norm)",
    )

    # Seed metric types
    await db.executescript(_SEED_METRIC_TYPES)

    # Seed default alert configs
    await db.executescript(_SEED_ALERT_CONFIGS)

    # Record schema version
    await db.execute(
        "INSERT INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    await db.commit()
    logger.info(f"Migrations complete — schema version {SCHEMA_VERSION}")
