"""Database schema creation and versioning.

All CREATE TABLE statements for the caching layer.
Uses IF NOT EXISTS for idempotent runs.
"""
from __future__ import annotations

import logging

import aiosqlite

from backend import config

logger = logging.getLogger("ccdash.db")

SCHEMA_VERSION = 27

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
    model_io_tokens  INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    cache_input_tokens INTEGER DEFAULT 0,
    observed_tokens  INTEGER DEFAULT 0,
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
    display_cost_usd REAL,
    cost_provenance TEXT DEFAULT 'unknown',
    cost_confidence REAL DEFAULT 0.0,
    cost_mismatch_pct REAL,
    pricing_model_source TEXT DEFAULT '',
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
    session_forensics_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

-- Normalized log entries
CREATE TABLE IF NOT EXISTS session_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    log_index      INTEGER NOT NULL,
    source_log_id  TEXT DEFAULT '',
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
CREATE INDEX IF NOT EXISTS idx_logs_source_log_id ON session_logs(session_id, source_log_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_source_log_unique
    ON session_logs(session_id, source_log_id)
    WHERE source_log_id != '';

-- Canonical transcript seam for future enterprise-grade session intelligence.
CREATE TABLE IF NOT EXISTS session_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_index  INTEGER NOT NULL,
    source_log_id  TEXT DEFAULT '',
    message_id     TEXT DEFAULT '',
    role           TEXT NOT NULL,
    message_type   TEXT NOT NULL,
    content        TEXT DEFAULT '',
    event_timestamp TEXT NOT NULL,
    agent_name     TEXT DEFAULT '',
    tool_name      TEXT,
    tool_call_id   TEXT,
    related_tool_call_id TEXT,
    linked_session_id TEXT,
    entry_uuid     TEXT,
    parent_entry_uuid TEXT,
    root_session_id TEXT DEFAULT '',
    conversation_family_id TEXT DEFAULT '',
    thread_session_id TEXT DEFAULT '',
    parent_session_id TEXT DEFAULT '',
    source_provenance TEXT NOT NULL DEFAULT 'session_log_projection',
    metadata_json  TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cache_read_input_tokens   INTEGER,
    cache_creation_input_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_session_messages_family
    ON session_messages(conversation_family_id, root_session_id, message_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_message
    ON session_messages(session_id, message_index);

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

CREATE TABLE IF NOT EXISTS session_usage_events (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    root_session_id    TEXT NOT NULL,
    linked_session_id  TEXT DEFAULT '',
    source_log_id      TEXT DEFAULT '',
    captured_at        TEXT NOT NULL,
    event_kind         TEXT NOT NULL,
    model              TEXT DEFAULT '',
    tool_name          TEXT DEFAULT '',
    agent_name         TEXT DEFAULT '',
    token_family       TEXT NOT NULL,
    delta_tokens       INTEGER NOT NULL DEFAULT 0 CHECK (delta_tokens >= 0),
    cost_usd_model_io  REAL NOT NULL DEFAULT 0.0 CHECK (cost_usd_model_io >= 0),
    metadata_json      TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_session_usage_events_project
    ON session_usage_events(project_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_usage_events_session
    ON session_usage_events(session_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_usage_events_source
    ON session_usage_events(session_id, source_log_id);
CREATE INDEX IF NOT EXISTS idx_session_usage_events_entity_dims
    ON session_usage_events(project_id, token_family, event_kind);

CREATE TABLE IF NOT EXISTS session_usage_attributions (
    event_id            TEXT NOT NULL REFERENCES session_usage_events(id) ON DELETE CASCADE,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    attribution_role    TEXT NOT NULL,
    weight              REAL NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
    method              TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    metadata_json       TEXT DEFAULT '{}',
    PRIMARY KEY (event_id, entity_type, entity_id, attribution_role, method)
);

CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_entity
    ON session_usage_attributions(entity_type, entity_id, attribution_role);
CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_method
    ON session_usage_attributions(method, attribution_role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_usage_attributions_primary
    ON session_usage_attributions(event_id)
    WHERE attribution_role = 'primary';

-- Session lineage relationships (fork/subagent and future kinds)
CREATE TABLE IF NOT EXISTS session_relationships (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL,
    parent_session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    child_session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    relationship_type  TEXT NOT NULL,
    context_inheritance TEXT DEFAULT '',
    source_platform    TEXT DEFAULT '',
    parent_entry_uuid  TEXT DEFAULT '',
    child_entry_uuid   TEXT DEFAULT '',
    source_log_id      TEXT,
    metadata_json      TEXT DEFAULT '{}',
    source_file        TEXT DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_relationships_parent
    ON session_relationships(project_id, parent_session_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_session_relationships_child
    ON session_relationships(project_id, child_session_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_session_relationships_source
    ON session_relationships(project_id, source_file);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_relationships_unique
    ON session_relationships(project_id, parent_session_id, child_session_id, relationship_type, parent_entry_uuid, child_entry_uuid);

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
    tags_json       TEXT DEFAULT '[]',
    deferred_tasks  INTEGER DEFAULT 0,
    planned_at      TEXT DEFAULT '',
    started_at      TEXT DEFAULT '',
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

-- ── 9b. Outbound Telemetry Export Queue ────────────────────────────
CREATE TABLE IF NOT EXISTS outbound_telemetry_queue (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_slug    TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'failed', 'abandoned')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_attempt_at TEXT,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    UNIQUE(session_id)
);

CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_status
    ON outbound_telemetry_queue(status);
CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_created_at
    ON outbound_telemetry_queue(created_at);

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

CREATE TABLE IF NOT EXISTS session_sentiment_facts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id         TEXT DEFAULT '',
    root_session_id    TEXT DEFAULT '',
    thread_session_id  TEXT DEFAULT '',
    source_message_id  TEXT DEFAULT '',
    source_log_id      TEXT DEFAULT '',
    message_index      INTEGER NOT NULL DEFAULT 0,
    sentiment_label    TEXT NOT NULL DEFAULT 'neutral',
    sentiment_score    REAL NOT NULL DEFAULT 0.0,
    confidence         REAL NOT NULL DEFAULT 0.0,
    heuristic_version  TEXT DEFAULT '',
    evidence_json      TEXT DEFAULT '{}',
    computed_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_sentiment_facts_session
    ON session_sentiment_facts(session_id, message_index, source_log_id);

CREATE TABLE IF NOT EXISTS session_code_churn_facts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id               TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id               TEXT DEFAULT '',
    root_session_id          TEXT DEFAULT '',
    thread_session_id        TEXT DEFAULT '',
    file_path                TEXT NOT NULL,
    first_source_log_id      TEXT DEFAULT '',
    last_source_log_id       TEXT DEFAULT '',
    first_message_index      INTEGER NOT NULL DEFAULT 0,
    last_message_index       INTEGER NOT NULL DEFAULT 0,
    touch_count              INTEGER NOT NULL DEFAULT 0,
    distinct_edit_turn_count INTEGER NOT NULL DEFAULT 0,
    repeat_touch_count       INTEGER NOT NULL DEFAULT 0,
    rewrite_pass_count       INTEGER NOT NULL DEFAULT 0,
    additions_total          INTEGER NOT NULL DEFAULT 0,
    deletions_total          INTEGER NOT NULL DEFAULT 0,
    net_diff_total           INTEGER NOT NULL DEFAULT 0,
    churn_score              REAL NOT NULL DEFAULT 0.0,
    progress_score           REAL NOT NULL DEFAULT 0.0,
    low_progress_loop        INTEGER NOT NULL DEFAULT 0,
    confidence               REAL NOT NULL DEFAULT 0.0,
    heuristic_version        TEXT DEFAULT '',
    evidence_json            TEXT DEFAULT '{}',
    computed_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_code_churn_facts_session
    ON session_code_churn_facts(session_id, file_path);

CREATE TABLE IF NOT EXISTS session_scope_drift_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id              TEXT DEFAULT '',
    root_session_id         TEXT DEFAULT '',
    thread_session_id       TEXT DEFAULT '',
    planned_path_count      INTEGER NOT NULL DEFAULT 0,
    actual_path_count       INTEGER NOT NULL DEFAULT 0,
    matched_path_count      INTEGER NOT NULL DEFAULT 0,
    out_of_scope_path_count INTEGER NOT NULL DEFAULT 0,
    drift_ratio             REAL NOT NULL DEFAULT 0.0,
    adherence_score         REAL NOT NULL DEFAULT 0.0,
    confidence              REAL NOT NULL DEFAULT 0.0,
    heuristic_version       TEXT DEFAULT '',
    evidence_json           TEXT DEFAULT '{}',
    computed_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_scope_drift_facts_session
    ON session_scope_drift_facts(session_id, feature_id);

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

-- ── 12. SkillMeat Definition Cache + Stack Observations ───────────
CREATE TABLE IF NOT EXISTS external_definition_sources (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         TEXT NOT NULL,
    source_kind        TEXT NOT NULL DEFAULT 'skillmeat',
    enabled            INTEGER NOT NULL DEFAULT 0,
    base_url           TEXT DEFAULT '',
    project_mapping_json TEXT DEFAULT '{}',
    feature_flags_json TEXT DEFAULT '{}',
    last_synced_at     TEXT DEFAULT '',
    last_sync_status   TEXT DEFAULT 'never',
    last_sync_error    TEXT DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, source_kind)
);

CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project
    ON external_definition_sources(project_id, source_kind);

CREATE TABLE IF NOT EXISTS external_definitions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         TEXT NOT NULL,
    source_id          INTEGER NOT NULL REFERENCES external_definition_sources(id) ON DELETE CASCADE,
    definition_type    TEXT NOT NULL,
    external_id        TEXT NOT NULL,
    display_name       TEXT DEFAULT '',
    version            TEXT DEFAULT '',
    source_url         TEXT DEFAULT '',
    resolution_metadata_json TEXT DEFAULT '{}',
    raw_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    fetched_at         TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, definition_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_external_definitions_lookup
    ON external_definitions(project_id, definition_type, external_id);
CREATE INDEX IF NOT EXISTS idx_external_definitions_source
    ON external_definitions(source_id, definition_type);
CREATE INDEX IF NOT EXISTS idx_external_definitions_name
    ON external_definitions(project_id, display_name);

CREATE TABLE IF NOT EXISTS artifact_snapshot_cache (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     TEXT NOT NULL,
    collection_id  TEXT DEFAULT '',
    schema_version TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now')),
    artifact_count INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'fetched',
    raw_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_fetched
    ON artifact_snapshot_cache(project_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_collection
    ON artifact_snapshot_cache(project_id, collection_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS artifact_identity_map (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        TEXT NOT NULL,
    ccdash_name       TEXT NOT NULL,
    ccdash_type       TEXT NOT NULL DEFAULT '',
    skillmeat_uuid    TEXT DEFAULT '',
    content_hash      TEXT DEFAULT '',
    match_tier        TEXT NOT NULL DEFAULT 'unresolved',
    confidence        REAL,
    resolved_at       TEXT DEFAULT '',
    unresolved_reason TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_name
    ON artifact_identity_map(project_id, ccdash_name);
CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_uuid
    ON artifact_identity_map(project_id, skillmeat_uuid);
CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_hash
    ON artifact_identity_map(project_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_match_tier
    ON artifact_identity_map(project_id, match_tier);

CREATE TABLE IF NOT EXISTS artifact_ranking (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                TEXT NOT NULL,
    collection_id             TEXT DEFAULT '',
    user_scope                TEXT DEFAULT '',
    artifact_type             TEXT DEFAULT '',
    artifact_id               TEXT NOT NULL,
    artifact_uuid             TEXT DEFAULT '',
    version_id                TEXT DEFAULT '',
    workflow_id               TEXT DEFAULT '',
    period                    TEXT NOT NULL,
    exclusive_tokens          INTEGER NOT NULL DEFAULT 0,
    supporting_tokens         INTEGER NOT NULL DEFAULT 0,
    cost_usd                  REAL NOT NULL DEFAULT 0.0,
    session_count             INTEGER NOT NULL DEFAULT 0,
    workflow_count            INTEGER NOT NULL DEFAULT 0,
    last_observed_at          TEXT DEFAULT '',
    avg_confidence            REAL,
    confidence                REAL,
    success_score             REAL,
    efficiency_score          REAL,
    quality_score             REAL,
    risk_score                REAL,
    context_pressure          REAL,
    sample_size               INTEGER NOT NULL DEFAULT 0,
    identity_confidence       REAL,
    snapshot_fetched_at       TEXT DEFAULT '',
    recommendation_types_json TEXT NOT NULL DEFAULT '[]',
    evidence_json             TEXT NOT NULL DEFAULT '{}',
    computed_at               TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, collection_id, user_scope, artifact_id, artifact_uuid, version_id, workflow_id, period)
);

CREATE INDEX IF NOT EXISTS idx_artifact_ranking_project_period
    ON artifact_ranking(project_id, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_artifact_period
    ON artifact_ranking(artifact_uuid, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_workflow_period
    ON artifact_ranking(workflow_id, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_collection_period
    ON artifact_ranking(project_id, collection_id, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_user_period
    ON artifact_ranking(project_id, user_scope, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_version_period
    ON artifact_ranking(artifact_uuid, version_id, period);
CREATE INDEX IF NOT EXISTS idx_artifact_ranking_recommendations
    ON artifact_ranking(recommendation_types_json);

CREATE TABLE IF NOT EXISTS pricing_catalog_entries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         TEXT NOT NULL,
    platform_type      TEXT NOT NULL,
    model_id           TEXT NOT NULL DEFAULT '',
    context_window_size INTEGER,
    input_cost_per_million REAL,
    output_cost_per_million REAL,
    cache_creation_cost_per_million REAL,
    cache_read_cost_per_million REAL,
    speed_multiplier_fast REAL,
    source_type        TEXT NOT NULL DEFAULT 'bundled',
    source_updated_at  TEXT DEFAULT '',
    override_locked    INTEGER NOT NULL DEFAULT 0,
    sync_status        TEXT NOT NULL DEFAULT 'never',
    sync_error         TEXT DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, platform_type, model_id)
);

CREATE INDEX IF NOT EXISTS idx_pricing_catalog_project_platform
    ON pricing_catalog_entries(project_id, platform_type, model_id);
CREATE INDEX IF NOT EXISTS idx_pricing_catalog_source
    ON pricing_catalog_entries(project_id, source_type, sync_status);

CREATE TABLE IF NOT EXISTS session_stack_observations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         TEXT NOT NULL,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id         TEXT DEFAULT '',
    workflow_ref       TEXT DEFAULT '',
    confidence         REAL DEFAULT 0.0,
    observation_source TEXT DEFAULT 'backfill',
    evidence_json      TEXT DEFAULT '{}',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_session_stack_observations_session
    ON session_stack_observations(project_id, session_id);
CREATE INDEX IF NOT EXISTS idx_session_stack_observations_feature
    ON session_stack_observations(project_id, feature_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS session_stack_components (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         TEXT NOT NULL,
    observation_id     INTEGER NOT NULL REFERENCES session_stack_observations(id) ON DELETE CASCADE,
    component_type     TEXT NOT NULL,
    component_key      TEXT DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'explicit',
    confidence         REAL DEFAULT 0.0,
    external_definition_id INTEGER REFERENCES external_definitions(id) ON DELETE SET NULL,
    external_definition_type TEXT DEFAULT '',
    external_definition_external_id TEXT DEFAULT '',
    source_attribution TEXT DEFAULT '',
    component_payload_json TEXT DEFAULT '{}',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_stack_components_observation
    ON session_stack_components(observation_id, component_type);
CREATE INDEX IF NOT EXISTS idx_session_stack_components_resolution
    ON session_stack_components(project_id, status, component_type);

CREATE TABLE IF NOT EXISTS session_memory_drafts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id           TEXT NOT NULL,
    session_id           TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id           TEXT DEFAULT '',
    root_session_id      TEXT DEFAULT '',
    thread_session_id    TEXT DEFAULT '',
    workflow_ref         TEXT DEFAULT '',
    title                TEXT DEFAULT '',
    memory_type          TEXT NOT NULL DEFAULT 'learning',
    status               TEXT NOT NULL DEFAULT 'draft',
    module_name          TEXT NOT NULL DEFAULT '',
    module_description   TEXT DEFAULT '',
    content              TEXT NOT NULL DEFAULT '',
    confidence           REAL NOT NULL DEFAULT 0.0,
    source_message_id    TEXT DEFAULT '',
    source_log_id        TEXT DEFAULT '',
    source_message_index INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL DEFAULT '',
    evidence_json        TEXT NOT NULL DEFAULT '{}',
    publish_attempts     INTEGER NOT NULL DEFAULT 0,
    published_module_id  TEXT DEFAULT '',
    published_memory_id  TEXT DEFAULT '',
    reviewed_by          TEXT DEFAULT '',
    review_notes         TEXT DEFAULT '',
    reviewed_at          TEXT DEFAULT '',
    published_at         TEXT DEFAULT '',
    last_publish_error   TEXT DEFAULT '',
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_project_status
    ON session_memory_drafts(project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_session
    ON session_memory_drafts(project_id, session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS effectiveness_rollups (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id            TEXT NOT NULL,
    scope_type            TEXT NOT NULL,
    scope_id              TEXT NOT NULL,
    period                TEXT NOT NULL,
    metrics_json          TEXT NOT NULL DEFAULT '{}',
    evidence_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_effectiveness_rollups_scope
    ON effectiveness_rollups(project_id, scope_type, scope_id, period);
CREATE INDEX IF NOT EXISTS idx_effectiveness_rollups_period
    ON effectiveness_rollups(project_id, period, updated_at DESC);

-- ── 13. Execution Workbench Runs ──────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_runs (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT NOT NULL,
    feature_id            TEXT DEFAULT '',
    provider              TEXT NOT NULL DEFAULT 'local',
    source_command        TEXT NOT NULL,
    normalized_command    TEXT NOT NULL,
    cwd                   TEXT NOT NULL,
    env_profile           TEXT NOT NULL DEFAULT 'default',
    recommendation_rule_id TEXT DEFAULT '',
    risk_level            TEXT NOT NULL DEFAULT 'medium',
    policy_verdict        TEXT NOT NULL DEFAULT 'allow',
    requires_approval     INTEGER NOT NULL DEFAULT 0,
    approved_by           TEXT DEFAULT '',
    approved_at           TEXT DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'queued',
    exit_code             INTEGER,
    started_at            TEXT DEFAULT '',
    ended_at              TEXT DEFAULT '',
    retry_of_run_id       TEXT DEFAULT '',
    metadata_json         TEXT DEFAULT '{}',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_runs_project_feature_created
    ON execution_runs(project_id, feature_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_runs_project_status_updated
    ON execution_runs(project_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS execution_run_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES execution_runs(id) ON DELETE CASCADE,
    sequence_no   INTEGER NOT NULL,
    stream        TEXT NOT NULL DEFAULT 'system',
    event_type    TEXT NOT NULL DEFAULT 'status',
    payload_text  TEXT DEFAULT '',
    payload_json  TEXT DEFAULT '{}',
    occurred_at   TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_run_events_seq
    ON execution_run_events(run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_execution_run_events_lookup
    ON execution_run_events(run_id, sequence_no);

CREATE TABLE IF NOT EXISTS execution_approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES execution_runs(id) ON DELETE CASCADE,
    decision      TEXT NOT NULL DEFAULT 'pending',
    reason        TEXT DEFAULT '',
    requested_at  TEXT NOT NULL,
    resolved_at   TEXT DEFAULT '',
    requested_by  TEXT DEFAULT '',
    resolved_by   TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_execution_approvals_run
    ON execution_approvals(run_id, requested_at DESC);
"""

_PLANNING_WORKTREE_CONTEXTS_DDL = """
-- ── 15. Planning Worktree Contexts (PCP-501) ──────────────────────
CREATE TABLE IF NOT EXISTS planning_worktree_contexts (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL,
    feature_id        TEXT DEFAULT '',
    phase_number      INTEGER,
    batch_id          TEXT DEFAULT '',
    branch            TEXT DEFAULT '',
    worktree_path     TEXT DEFAULT '',
    base_branch       TEXT DEFAULT '',
    base_commit_sha   TEXT DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'draft',
    last_run_id       TEXT DEFAULT '',
    provider          TEXT DEFAULT 'local',
    notes             TEXT DEFAULT '',
    metadata_json     TEXT DEFAULT '{}',
    created_by        TEXT DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_planning_worktree_project_feature
    ON planning_worktree_contexts(project_id, feature_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_planning_worktree_project_status
    ON planning_worktree_contexts(project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_planning_worktree_feature_phase_batch
    ON planning_worktree_contexts(feature_id, phase_number, batch_id);

-- ── 15. Filesystem Scan Manifest ──────────────────────────────────
CREATE TABLE IF NOT EXISTS filesystem_scan_manifest (
    path       TEXT PRIMARY KEY,
    mtime      REAL NOT NULL,
    size       INTEGER NOT NULL,
    scanned_at TEXT NOT NULL
);
"""

_TEST_VISUALIZER_TABLES = """
-- ── 14. Test Visualizer ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS test_runs (
    run_id              TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    git_sha             TEXT DEFAULT '',
    branch              TEXT DEFAULT '',
    agent_session_id    TEXT DEFAULT '',
    env_fingerprint     TEXT DEFAULT '',
    trigger             TEXT DEFAULT 'local',
    status              TEXT DEFAULT 'complete',
    total_tests         INTEGER DEFAULT 0,
    passed_tests        INTEGER DEFAULT 0,
    failed_tests        INTEGER DEFAULT 0,
    skipped_tests       INTEGER DEFAULT 0,
    duration_ms         INTEGER DEFAULT 0,
    metadata_json       TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_runs_project
    ON test_runs(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_session
    ON test_runs(project_id, agent_session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_sha
    ON test_runs(project_id, git_sha);

CREATE TABLE IF NOT EXISTS test_definitions (
    test_id         TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    path            TEXT NOT NULL,
    name            TEXT NOT NULL,
    framework       TEXT DEFAULT 'pytest',
    tags_json       TEXT DEFAULT '[]',
    owner           TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_defs_project
    ON test_definitions(project_id);
CREATE INDEX IF NOT EXISTS idx_test_defs_path
    ON test_definitions(project_id, path);

CREATE TABLE IF NOT EXISTS test_results (
    run_id              TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    status              TEXT NOT NULL,
    duration_ms         INTEGER DEFAULT 0,
    error_fingerprint   TEXT DEFAULT '',
    error_message       TEXT DEFAULT '',
    artifact_refs_json  TEXT DEFAULT '[]',
    stdout_ref          TEXT DEFAULT '',
    stderr_ref          TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, test_id)
);

CREATE INDEX IF NOT EXISTS idx_test_results_test
    ON test_results(test_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_status
    ON test_results(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_fingerprint
    ON test_results(error_fingerprint) WHERE error_fingerprint != '';
CREATE INDEX IF NOT EXISTS idx_test_results_run
    ON test_results(run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_run_status
    ON test_results(run_id, status, test_id);
CREATE INDEX IF NOT EXISTS idx_test_results_test_run
    ON test_results(test_id, run_id);

CREATE TABLE IF NOT EXISTS test_domains (
    domain_id       TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    parent_id       TEXT REFERENCES test_domains(domain_id),
    description     TEXT DEFAULT '',
    tier            TEXT DEFAULT 'core',
    sort_order      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_domains_project
    ON test_domains(project_id);
CREATE INDEX IF NOT EXISTS idx_test_domains_parent
    ON test_domains(parent_id) WHERE parent_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS test_feature_mappings (
    mapping_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    feature_id          TEXT NOT NULL,
    domain_id           TEXT REFERENCES test_domains(domain_id),
    provider_source     TEXT NOT NULL,
    confidence          REAL DEFAULT 0.5,
    version             INTEGER DEFAULT 1,
    snapshot_hash       TEXT DEFAULT '',
    is_primary          INTEGER DEFAULT 0,
    metadata_json       TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mappings_test
    ON test_feature_mappings(project_id, test_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_feature
    ON test_feature_mappings(project_id, feature_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_domain
    ON test_feature_mappings(project_id, domain_id);
CREATE INDEX IF NOT EXISTS idx_mappings_primary_feature_test
    ON test_feature_mappings(project_id, is_primary, feature_id, test_id);
CREATE INDEX IF NOT EXISTS idx_mappings_primary_domain_test
    ON test_feature_mappings(project_id, is_primary, domain_id, test_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mappings_upsert
    ON test_feature_mappings(test_id, feature_id, provider_source, version);

CREATE TABLE IF NOT EXISTS test_integrity_signals (
    signal_id           TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    git_sha             TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    test_id             TEXT REFERENCES test_definitions(test_id),
    signal_type         TEXT NOT NULL,
    severity            TEXT DEFAULT 'medium',
    details_json        TEXT DEFAULT '{}',
    linked_run_ids_json TEXT DEFAULT '[]',
    agent_session_id    TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_integrity_project
    ON test_integrity_signals(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_integrity_sha
    ON test_integrity_signals(project_id, git_sha);
CREATE INDEX IF NOT EXISTS idx_integrity_test
    ON test_integrity_signals(test_id) WHERE test_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_integrity_type
    ON test_integrity_signals(project_id, signal_type, severity);
CREATE INDEX IF NOT EXISTS idx_integrity_project_agent_created
    ON test_integrity_signals(project_id, agent_session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS test_metrics (
    metric_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id           TEXT NOT NULL,
    run_id               TEXT DEFAULT '',
    platform             TEXT NOT NULL,
    metric_type          TEXT NOT NULL,
    metric_name          TEXT NOT NULL,
    metric_value         REAL DEFAULT 0,
    unit                 TEXT DEFAULT '',
    metadata_json        TEXT DEFAULT '{}',
    source_file          TEXT DEFAULT '',
    collected_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_metrics_project
    ON test_metrics(project_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_metrics_platform
    ON test_metrics(project_id, platform, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_metrics_metric_type
    ON test_metrics(project_id, metric_type, collected_at DESC);
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


async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ) as cur:
        return await cur.fetchone() is not None


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, definition: str) -> None:
    if await _column_exists(db, table, column):
        return
    await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def _migrate_outbound_telemetry_queue_add_event_type(db: aiosqlite.Connection) -> None:
    """Idempotent: add event_type column and remove the sessions FK from outbound_telemetry_queue.

    SQLite does not support ALTER TABLE DROP CONSTRAINT, so we use the
    rename-create-copy-drop pattern.  The UNIQUE(session_id) constraint is
    preserved on the new table because session-level rows still rely on it for
    idempotent inserts; artifact-level rows use a UUID primary key and a
    distinct dedup_key column instead.
    """
    if await _column_exists(db, "outbound_telemetry_queue", "event_type"):
        return  # Already migrated

    # Disable FK enforcement for the duration of this migration.
    await db.execute("PRAGMA foreign_keys=OFF")
    try:
        await db.execute("ALTER TABLE outbound_telemetry_queue RENAME TO _otq_backup")
        await db.execute(
            """
            CREATE TABLE outbound_telemetry_queue (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL,
                project_slug    TEXT NOT NULL,
                payload_json    TEXT NOT NULL,
                event_type      TEXT NOT NULL DEFAULT 'execution_outcome',
                status          TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'synced', 'failed', 'abandoned')),
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                last_attempt_at TEXT,
                attempt_count   INTEGER NOT NULL DEFAULT 0,
                last_error      TEXT,
                UNIQUE(session_id)
            )
            """
        )
        await db.execute(
            """
            INSERT INTO outbound_telemetry_queue
                (id, session_id, project_slug, payload_json, event_type,
                 status, created_at, last_attempt_at, attempt_count, last_error)
            SELECT id, session_id, project_slug, payload_json,
                   'execution_outcome',
                   status, created_at, last_attempt_at, attempt_count, last_error
            FROM _otq_backup
            """
        )
        await db.execute("DROP TABLE _otq_backup")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_status ON outbound_telemetry_queue(status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_created_at ON outbound_telemetry_queue(created_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_event_type ON outbound_telemetry_queue(event_type, status)"
        )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys=ON")


async def _ensure_column_if_table_exists(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if not await _table_exists(db, table):
        return
    await _ensure_column(db, table, column, definition)


async def _ensure_index(db: aiosqlite.Connection, ddl: str) -> None:
    await db.execute(ddl)


async def _backfill_feature_query_columns(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        UPDATE features
        SET
            tags_json = COALESCE(json_extract(data_json, '$.tags'), '[]'),
            deferred_tasks = COALESCE(CAST(json_extract(data_json, '$.deferredTasks') AS INTEGER), 0),
            planned_at = COALESCE(json_extract(data_json, '$.plannedAt'), ''),
            started_at = COALESCE(json_extract(data_json, '$.startedAt'), '')
        """
    )


async def _ensure_test_visualizer_tables(db: aiosqlite.Connection) -> None:
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        return
    await db.executescript(_TEST_VISUALIZER_TABLES)


async def _ensure_planning_worktree_contexts_table(db: aiosqlite.Connection) -> None:
    """Idempotent: create planning_worktree_contexts table and indexes if missing."""
    await db.executescript(_PLANNING_WORKTREE_CONTEXTS_DDL)


async def _prepare_legacy_tables_for_bootstrap(db: aiosqlite.Connection) -> None:
    # Legacy v18 databases can have session_logs without source_log_id, but the
    # main bootstrap script now creates indexes that depend on that column.
    await _ensure_column_if_table_exists(db, "session_logs", "source_log_id", "TEXT DEFAULT ''")


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Create all tables and seed data. Idempotent."""
    # Check current schema version
    try:
        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            current_version = row[0] if row and row[0] else 0
    except Exception:
        current_version = 0

    should_record_version = current_version < SCHEMA_VERSION
    if should_record_version:
        logger.info(f"Running migrations: {current_version} → {SCHEMA_VERSION}")
        await _prepare_legacy_tables_for_bootstrap(db)
        # Execute all CREATE TABLE statements
        await db.executescript(_TABLES)
    else:
        logger.info(f"Schema version {current_version} already recorded; running idempotent column/index checks")

    await _ensure_test_visualizer_tables(db)
    await _ensure_planning_worktree_contexts_table(db)

    # Explicit table upgrades for existing DBs.
    await _ensure_column(db, "sessions", "root_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "agent_id", "TEXT")
    await _ensure_column(db, "sessions", "git_commit_hashes_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "dates_json", "TEXT DEFAULT '{}'")
    await _ensure_column(db, "sessions", "timeline_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "impact_history_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "thinking_level", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "session_forensics_json", "TEXT DEFAULT '{}'")
    await _ensure_column(db, "sessions", "model_io_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "cache_creation_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "cache_read_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "cache_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "observed_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "current_context_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "context_window_size", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "context_utilization_pct", "REAL DEFAULT 0.0")
    await _ensure_column(db, "sessions", "context_measurement_source", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "context_measured_at", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "tool_reported_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_output_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_cache_creation_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_cache_read_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "reported_cost_usd", "REAL")
    await _ensure_column(db, "sessions", "recalculated_cost_usd", "REAL")
    await _ensure_column(db, "sessions", "display_cost_usd", "REAL")
    await _ensure_column(db, "sessions", "cost_provenance", "TEXT DEFAULT 'unknown'")
    await _ensure_column(db, "sessions", "cost_confidence", "REAL DEFAULT 0.0")
    await _ensure_column(db, "sessions", "cost_mismatch_pct", "REAL")
    await _ensure_column(db, "sessions", "pricing_model_source", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "platform_type", "TEXT DEFAULT 'Claude Code'")
    await _ensure_column(db, "sessions", "platform_version", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "platform_versions_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "platform_version_transitions_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "thread_kind", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "conversation_family_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "context_inheritance", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "fork_parent_session_id", "TEXT")
    await _ensure_column(db, "sessions", "fork_point_log_id", "TEXT")
    await _ensure_column(db, "sessions", "fork_point_entry_uuid", "TEXT")
    await _ensure_column(db, "sessions", "fork_point_parent_entry_uuid", "TEXT")
    await _ensure_column(db, "sessions", "fork_depth", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "fork_count", "INTEGER DEFAULT 0")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_sessions_root ON sessions(project_id, root_session_id, started_at DESC)")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_sessions_family ON sessions(project_id, conversation_family_id, started_at DESC)")
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_sessions_thread_kind ON sessions(project_id, thread_kind, started_at DESC)")

    await _ensure_column(db, "session_logs", "tool_call_id", "TEXT")
    await _ensure_column(db, "session_logs", "related_tool_call_id", "TEXT")
    await _ensure_column(db, "session_logs", "linked_session_id", "TEXT")
    await _ensure_column(db, "session_logs", "source_log_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_logs", "metadata_json", "TEXT")
    await db.execute(
        """
        UPDATE session_logs
        SET source_log_id = 'log-' || CAST(log_index AS TEXT)
        WHERE COALESCE(source_log_id, '') = ''
        """
    )
    await _ensure_index(db, "CREATE INDEX IF NOT EXISTS idx_logs_source_log_id ON session_logs(session_id, source_log_id)")
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_source_log_unique ON session_logs(session_id, source_log_id) WHERE source_log_id != ''",
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            message_index  INTEGER NOT NULL,
            source_log_id  TEXT DEFAULT '',
            message_id     TEXT DEFAULT '',
            role           TEXT NOT NULL,
            message_type   TEXT NOT NULL,
            content        TEXT DEFAULT '',
            event_timestamp TEXT NOT NULL,
            agent_name     TEXT DEFAULT '',
            tool_name      TEXT,
            tool_call_id   TEXT,
            related_tool_call_id TEXT,
            linked_session_id TEXT,
            entry_uuid     TEXT,
            parent_entry_uuid TEXT,
            root_session_id TEXT DEFAULT '',
            conversation_family_id TEXT DEFAULT '',
            thread_session_id TEXT DEFAULT '',
            parent_session_id TEXT DEFAULT '',
            source_provenance TEXT NOT NULL DEFAULT 'session_log_projection',
            metadata_json  TEXT,
            input_tokens   INTEGER,
            output_tokens  INTEGER,
            cache_read_input_tokens   INTEGER,
            cache_creation_input_tokens INTEGER
        )
        """
    )
    await _ensure_column(db, "session_messages", "source_log_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "message_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "role", "TEXT NOT NULL DEFAULT ''")
    await _ensure_column(db, "session_messages", "message_type", "TEXT NOT NULL DEFAULT ''")
    await _ensure_column(db, "session_messages", "content", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "event_timestamp", "TEXT NOT NULL DEFAULT ''")
    await _ensure_column(db, "session_messages", "agent_name", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "tool_name", "TEXT")
    await _ensure_column(db, "session_messages", "tool_call_id", "TEXT")
    await _ensure_column(db, "session_messages", "related_tool_call_id", "TEXT")
    await _ensure_column(db, "session_messages", "linked_session_id", "TEXT")
    await _ensure_column(db, "session_messages", "entry_uuid", "TEXT")
    await _ensure_column(db, "session_messages", "parent_entry_uuid", "TEXT")
    await _ensure_column(db, "session_messages", "root_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "conversation_family_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "thread_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "parent_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "session_messages", "source_provenance", "TEXT NOT NULL DEFAULT 'session_log_projection'")
    await _ensure_column(db, "session_messages", "metadata_json", "TEXT")
    await _ensure_column(db, "session_messages", "input_tokens", "INTEGER")
    await _ensure_column(db, "session_messages", "output_tokens", "INTEGER")
    await _ensure_column(db, "session_messages", "cache_read_input_tokens", "INTEGER")
    await _ensure_column(db, "session_messages", "cache_creation_input_tokens", "INTEGER")
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_messages_family ON session_messages(conversation_family_id, root_session_id, message_index)",
    )
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_message ON session_messages(session_id, message_index)",
    )
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
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS pricing_catalog_entries (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id         TEXT NOT NULL,
            platform_type      TEXT NOT NULL,
            model_id           TEXT NOT NULL DEFAULT '',
            context_window_size INTEGER,
            input_cost_per_million REAL,
            output_cost_per_million REAL,
            cache_creation_cost_per_million REAL,
            cache_read_cost_per_million REAL,
            speed_multiplier_fast REAL,
            source_type        TEXT NOT NULL DEFAULT 'bundled',
            source_updated_at  TEXT DEFAULT '',
            override_locked    INTEGER NOT NULL DEFAULT 0,
            sync_status        TEXT NOT NULL DEFAULT 'never',
            sync_error         TEXT DEFAULT '',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, platform_type, model_id)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_pricing_catalog_project_platform ON pricing_catalog_entries(project_id, platform_type, model_id)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_pricing_catalog_source ON pricing_catalog_entries(project_id, source_type, sync_status)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_usage_events (
            id                 TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            root_session_id    TEXT NOT NULL,
            linked_session_id  TEXT DEFAULT '',
            source_log_id      TEXT DEFAULT '',
            captured_at        TEXT NOT NULL,
            event_kind         TEXT NOT NULL,
            model              TEXT DEFAULT '',
            tool_name          TEXT DEFAULT '',
            agent_name         TEXT DEFAULT '',
            token_family       TEXT NOT NULL,
            delta_tokens       INTEGER NOT NULL DEFAULT 0 CHECK (delta_tokens >= 0),
            cost_usd_model_io  REAL NOT NULL DEFAULT 0.0 CHECK (cost_usd_model_io >= 0),
            metadata_json      TEXT DEFAULT '{}'
        )
        """,
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_usage_attributions (
            event_id            TEXT NOT NULL REFERENCES session_usage_events(id) ON DELETE CASCADE,
            entity_type         TEXT NOT NULL,
            entity_id           TEXT NOT NULL,
            attribution_role    TEXT NOT NULL,
            weight              REAL NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
            method              TEXT NOT NULL,
            confidence          REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
            metadata_json       TEXT DEFAULT '{}',
            PRIMARY KEY (event_id, entity_type, entity_id, attribution_role, method)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_project ON session_usage_events(project_id, captured_at DESC)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_session ON session_usage_events(session_id, captured_at DESC)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_source ON session_usage_events(session_id, source_log_id)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_entity_dims ON session_usage_events(project_id, token_family, event_kind)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_entity ON session_usage_attributions(entity_type, entity_id, attribution_role)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_method ON session_usage_attributions(method, attribution_role)",
    )
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_usage_attributions_primary ON session_usage_attributions(event_id) WHERE attribution_role = 'primary'",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_relationships (
            id                 TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            parent_session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            child_session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            relationship_type  TEXT NOT NULL,
            context_inheritance TEXT DEFAULT '',
            source_platform    TEXT DEFAULT '',
            parent_entry_uuid  TEXT DEFAULT '',
            child_entry_uuid   TEXT DEFAULT '',
            source_log_id      TEXT,
            metadata_json      TEXT DEFAULT '{}',
            source_file        TEXT DEFAULT '',
            created_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_parent ON session_relationships(project_id, parent_session_id, relationship_type)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_child ON session_relationships(project_id, child_session_id, relationship_type)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_source ON session_relationships(project_id, source_file)",
    )
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_relationships_unique ON session_relationships(project_id, parent_session_id, child_session_id, relationship_type, parent_entry_uuid, child_entry_uuid)",
    )

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

    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS external_definition_sources (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id         TEXT NOT NULL,
            source_kind        TEXT NOT NULL DEFAULT 'skillmeat',
            enabled            INTEGER NOT NULL DEFAULT 0,
            base_url           TEXT DEFAULT '',
            project_mapping_json TEXT DEFAULT '{}',
            feature_flags_json TEXT DEFAULT '{}',
            last_synced_at     TEXT DEFAULT '',
            last_sync_status   TEXT DEFAULT 'never',
            last_sync_error    TEXT DEFAULT '',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, source_kind)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project ON external_definition_sources(project_id, source_kind)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS external_definitions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id         TEXT NOT NULL,
            source_id          INTEGER NOT NULL REFERENCES external_definition_sources(id) ON DELETE CASCADE,
            definition_type    TEXT NOT NULL,
            external_id        TEXT NOT NULL,
            display_name       TEXT DEFAULT '',
            version            TEXT DEFAULT '',
            source_url         TEXT DEFAULT '',
            resolution_metadata_json TEXT DEFAULT '{}',
            raw_snapshot_json  TEXT NOT NULL DEFAULT '{}',
            fetched_at         TEXT NOT NULL,
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, definition_type, external_id)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_lookup ON external_definitions(project_id, definition_type, external_id)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_source ON external_definitions(source_id, definition_type)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_name ON external_definitions(project_id, display_name)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS artifact_snapshot_cache (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id     TEXT NOT NULL,
            collection_id  TEXT DEFAULT '',
            schema_version TEXT NOT NULL,
            generated_at   TEXT NOT NULL,
            fetched_at     TEXT NOT NULL DEFAULT (datetime('now')),
            artifact_count INTEGER NOT NULL DEFAULT 0,
            status         TEXT NOT NULL DEFAULT 'fetched',
            raw_json       TEXT NOT NULL DEFAULT '{}'
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_fetched ON artifact_snapshot_cache(project_id, fetched_at DESC)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_collection ON artifact_snapshot_cache(project_id, collection_id, fetched_at DESC)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS artifact_identity_map (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id        TEXT NOT NULL,
            ccdash_name       TEXT NOT NULL,
            ccdash_type       TEXT NOT NULL DEFAULT '',
            skillmeat_uuid    TEXT DEFAULT '',
            content_hash      TEXT DEFAULT '',
            match_tier        TEXT NOT NULL DEFAULT 'unresolved',
            confidence        REAL,
            resolved_at       TEXT DEFAULT '',
            unresolved_reason TEXT DEFAULT ''
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_name ON artifact_identity_map(project_id, ccdash_name)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_uuid ON artifact_identity_map(project_id, skillmeat_uuid)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_hash ON artifact_identity_map(project_id, content_hash)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_match_tier ON artifact_identity_map(project_id, match_tier)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS artifact_ranking (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id                TEXT NOT NULL,
            collection_id             TEXT DEFAULT '',
            user_scope                TEXT DEFAULT '',
            artifact_type             TEXT DEFAULT '',
            artifact_id               TEXT NOT NULL,
            artifact_uuid             TEXT DEFAULT '',
            version_id                TEXT DEFAULT '',
            workflow_id               TEXT DEFAULT '',
            period                    TEXT NOT NULL,
            exclusive_tokens          INTEGER NOT NULL DEFAULT 0,
            supporting_tokens         INTEGER NOT NULL DEFAULT 0,
            cost_usd                  REAL NOT NULL DEFAULT 0.0,
            session_count             INTEGER NOT NULL DEFAULT 0,
            workflow_count            INTEGER NOT NULL DEFAULT 0,
            last_observed_at          TEXT DEFAULT '',
            avg_confidence            REAL,
            confidence                REAL,
            success_score             REAL,
            efficiency_score          REAL,
            quality_score             REAL,
            risk_score                REAL,
            context_pressure          REAL,
            sample_size               INTEGER NOT NULL DEFAULT 0,
            identity_confidence       REAL,
            snapshot_fetched_at       TEXT DEFAULT '',
            recommendation_types_json TEXT NOT NULL DEFAULT '[]',
            evidence_json             TEXT NOT NULL DEFAULT '{}',
            computed_at               TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, collection_id, user_scope, artifact_id, artifact_uuid, version_id, workflow_id, period)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_project_period ON artifact_ranking(project_id, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_artifact_period ON artifact_ranking(artifact_uuid, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_workflow_period ON artifact_ranking(workflow_id, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_collection_period ON artifact_ranking(project_id, collection_id, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_user_period ON artifact_ranking(project_id, user_scope, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_version_period ON artifact_ranking(artifact_uuid, version_id, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_artifact_ranking_recommendations ON artifact_ranking(recommendation_types_json)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_stack_observations (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id         TEXT NOT NULL,
            session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            feature_id         TEXT DEFAULT '',
            workflow_ref       TEXT DEFAULT '',
            confidence         REAL DEFAULT 0.0,
            observation_source TEXT DEFAULT 'backfill',
            evidence_json      TEXT DEFAULT '{}',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, session_id)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_session ON session_stack_observations(project_id, session_id)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_feature ON session_stack_observations(project_id, feature_id, updated_at DESC)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_stack_components (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id         TEXT NOT NULL,
            observation_id     INTEGER NOT NULL REFERENCES session_stack_observations(id) ON DELETE CASCADE,
            component_type     TEXT NOT NULL,
            component_key      TEXT DEFAULT '',
            status             TEXT NOT NULL DEFAULT 'explicit',
            confidence         REAL DEFAULT 0.0,
            external_definition_id INTEGER REFERENCES external_definitions(id) ON DELETE SET NULL,
            external_definition_type TEXT DEFAULT '',
            external_definition_external_id TEXT DEFAULT '',
            source_attribution TEXT DEFAULT '',
            component_payload_json TEXT DEFAULT '{}',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_stack_components_observation ON session_stack_components(observation_id, component_type)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_stack_components_resolution ON session_stack_components(project_id, status, component_type)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS session_memory_drafts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id           TEXT NOT NULL,
            session_id           TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            feature_id           TEXT DEFAULT '',
            root_session_id      TEXT DEFAULT '',
            thread_session_id    TEXT DEFAULT '',
            workflow_ref         TEXT DEFAULT '',
            title                TEXT DEFAULT '',
            memory_type          TEXT NOT NULL DEFAULT 'learning',
            status               TEXT NOT NULL DEFAULT 'draft',
            module_name          TEXT NOT NULL DEFAULT '',
            module_description   TEXT DEFAULT '',
            content              TEXT NOT NULL DEFAULT '',
            confidence           REAL NOT NULL DEFAULT 0.0,
            source_message_id    TEXT DEFAULT '',
            source_log_id        TEXT DEFAULT '',
            source_message_index INTEGER NOT NULL DEFAULT 0,
            content_hash         TEXT NOT NULL DEFAULT '',
            evidence_json        TEXT NOT NULL DEFAULT '{}',
            publish_attempts     INTEGER NOT NULL DEFAULT 0,
            published_module_id  TEXT DEFAULT '',
            published_memory_id  TEXT DEFAULT '',
            reviewed_by          TEXT DEFAULT '',
            review_notes         TEXT DEFAULT '',
            reviewed_at          TEXT DEFAULT '',
            published_at         TEXT DEFAULT '',
            last_publish_error   TEXT DEFAULT '',
            created_at           TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, content_hash)
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_project_status ON session_memory_drafts(project_id, status, updated_at DESC)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_session ON session_memory_drafts(project_id, session_id, updated_at DESC)",
    )
    await _ensure_index(
        db,
        """
        CREATE TABLE IF NOT EXISTS effectiveness_rollups (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id            TEXT NOT NULL,
            scope_type            TEXT NOT NULL,
            scope_id              TEXT NOT NULL,
            period                TEXT NOT NULL,
            metrics_json          TEXT NOT NULL DEFAULT '{}',
            evidence_summary_json TEXT NOT NULL DEFAULT '{}',
            created_at            TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    )
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_effectiveness_rollups_scope ON effectiveness_rollups(project_id, scope_type, scope_id, period)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_effectiveness_rollups_period ON effectiveness_rollups(project_id, period, updated_at DESC)",
    )

    # Migrate outbound_telemetry_queue: add event_type, drop sessions FK
    await _migrate_outbound_telemetry_queue_add_event_type(db)

    # Explicit feature-column upgrades/backfill for legacy rows.
    await _ensure_column(db, "features", "tags_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "features", "deferred_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "features", "planned_at", "TEXT DEFAULT ''")
    await _ensure_column(db, "features", "started_at", "TEXT DEFAULT ''")
    await _backfill_feature_query_columns(db)

    # ── P1-006: Feature surface query indexes ─────────────────────────────────
    # features: composite for status IN-list filter + updated_at sort
    # Used by: list_feature_cards WHERE project_id=? AND status IN (...)
    #          ORDER BY updated_at DESC (eliminates full-project scan + sort B-tree)
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_status_updated"
        " ON features(project_id, status, updated_at)",
    )
    # features: category filter composite
    # Used by: list_feature_cards WHERE project_id=? AND LOWER(category) IN (...)
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_category"
        " ON features(project_id, category)",
    )
    # features: completed_at range filter + sort
    # Used by: list_feature_cards completed DateRange + FeatureSortKey.COMPLETED_AT
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_completed_at"
        " ON features(project_id, completed_at)",
    )
    # features: created_at range filter + sort
    # Used by: list_feature_cards created DateRange + FeatureSortKey.CREATED_AT
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_created_at"
        " ON features(project_id, created_at)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_planned_at"
        " ON features(project_id, planned_at)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_started_at"
        " ON features(project_id, started_at)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_deferred_tasks"
        " ON features(project_id, deferred_tasks)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_category_lower"
        " ON features(project_id, LOWER(category))",
    )
    # entity_links: composite for rollup feature→session/doc/task hot path
    # Used by: _query_session_aggregates, _query_doc_metrics, _query_freshness,
    #          list_feature_session_refs
    # Adds target_type + link_type to existing idx_links_source so residual
    # row filtering is eliminated for the dominant 4-column predicate.
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_links_feature_session"
        " ON entity_links(source_type, source_id, target_type, link_type)",
    )
    # sessions: updated_at for latest_activity aggregation
    # Used by: _query_session_aggregates MAX(s.updated_at), _query_freshness,
    #          FeatureSortKey.LATEST_ACTIVITY fallback
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at"
        " ON sessions(project_id, updated_at)",
    )

    # sessions: conversation_family_id single-column lookup
    # Used by: sessions.py:213 WHERE conversation_family_id = ?
    # (idx_sessions_family covers the 3-column form; this covers bare equality scans)
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_conversation_family"
        " ON sessions(conversation_family_id)",
    )

    # features: composite (project_id, status) for planning summary status-IN queries
    # Used by: planning summary queries that filter status IN (...) within a project
    # (idx_features_project covers project_id alone; this eliminates residual status scan)
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_features_project_status"
        " ON features(project_id, status)",
    )

    # feature_phases: composite (feature_id, status) for planning rollup status counters
    # Used by: planning rollup status-count queries grouping phases by status per feature
    # (idx_phases_feature covers feature_id alone; this eliminates residual status scan)
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_phases_feature_status"
        " ON feature_phases(feature_id, status)",
    )

    # Seed metric types
    await db.executescript(_SEED_METRIC_TYPES)

    # Seed default alert configs
    await db.executescript(_SEED_ALERT_CONFIGS)

    # Record schema version
    if should_record_version:
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    await db.commit()
    logger.info(f"Migrations complete — schema version {max(current_version, SCHEMA_VERSION)}")
