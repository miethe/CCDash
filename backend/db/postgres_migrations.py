"""PostgreSQL database schema creation and versioning."""
from __future__ import annotations

import logging
import asyncpg

from backend import config

logger = logging.getLogger("ccdash.db.postgres")

SCHEMA_VERSION = 28

_TABLES = """
-- ── Schema version tracking ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER NOT NULL,
    applied   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ── 1. Sync State (Incremental Change Detection) ──────────────────
CREATE TABLE IF NOT EXISTS sync_state (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    file_mtime   DOUBLE PRECISION NOT NULL,
    entity_type  TEXT NOT NULL,
    project_id   TEXT NOT NULL,
    last_synced  TEXT NOT NULL,
    parse_ms     INTEGER DEFAULT 0
);

-- ── 2. Universal Entity Cross-Linking ──────────────────────────────
CREATE TABLE IF NOT EXISTS entity_links (
    id            SERIAL PRIMARY KEY,
    source_type   TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    link_type     TEXT DEFAULT 'related',
    origin        TEXT DEFAULT 'auto',
    confidence    DOUBLE PRECISION DEFAULT 1.0,
    depth         INTEGER DEFAULT 0,
    sort_order    INTEGER DEFAULT 0,
    metadata_json TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_links_source ON entity_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON entity_links(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_links_tree   ON entity_links(source_type, source_id, link_type, depth);
CREATE INDEX IF NOT EXISTS idx_links_origin ON entity_links(origin) WHERE origin = 'manual';

-- External links (URLs, PRs, issues)
CREATE TABLE IF NOT EXISTS external_links (
    id            SERIAL PRIMARY KEY,
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
    id    SERIAL PRIMARY KEY,
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
    session_forensics_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

-- Normalized log entries
CREATE TABLE IF NOT EXISTS session_logs (
    id             SERIAL PRIMARY KEY,
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
    id             BIGSERIAL PRIMARY KEY,
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
    id           SERIAL PRIMARY KEY,
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
    cost_usd_model_io  DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (cost_usd_model_io >= 0),
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
    weight              DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
    method              TEXT NOT NULL,
    confidence          DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
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
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    parent_session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    child_session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    relationship_type   TEXT NOT NULL,
    context_inheritance TEXT DEFAULT '',
    source_platform     TEXT DEFAULT '',
    parent_entry_uuid   TEXT DEFAULT '',
    child_entry_uuid    TEXT DEFAULT '',
    source_log_id       TEXT,
    metadata_json       TEXT DEFAULT '{}',
    source_file         TEXT DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    overall_progress DOUBLE PRECISION,
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
    id             SERIAL PRIMARY KEY,
    document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id     TEXT NOT NULL,
    ref_kind       TEXT NOT NULL,
    ref_value      TEXT NOT NULL,
    ref_value_norm TEXT NOT NULL,
    source_field   TEXT NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    cost           DOUBLE PRECISION DEFAULT 0.0,
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
    id            SERIAL PRIMARY KEY,
    project_id    TEXT NOT NULL,
    metric_type   TEXT NOT NULL REFERENCES metric_types(id),
    value         DOUBLE PRECISION NOT NULL,
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
    id              SERIAL PRIMARY KEY,
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
    cost_usd        DOUBLE PRECISION DEFAULT 0.0,
    occurred_at     TEXT NOT NULL,
    sequence_no     INTEGER DEFAULT 0,
    source          TEXT DEFAULT 'sync',
    source_key      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    event_type      TEXT NOT NULL DEFAULT 'execution_outcome',
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'failed', 'abandoned')),
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    last_attempt_at TEXT,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    UNIQUE(session_id)
);

CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_status
    ON outbound_telemetry_queue(status);
CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_created_at
    ON outbound_telemetry_queue(created_at);
CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_event_type
    ON outbound_telemetry_queue(event_type, status);

-- ── 10. Commit Correlations ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS commit_correlations (
    id              SERIAL PRIMARY KEY,
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
    cost_usd        DOUBLE PRECISION DEFAULT 0.0,
    source          TEXT DEFAULT 'sync',
    source_key      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    id                 BIGSERIAL PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id         TEXT DEFAULT '',
    root_session_id    TEXT DEFAULT '',
    thread_session_id  TEXT DEFAULT '',
    source_message_id  TEXT DEFAULT '',
    source_log_id      TEXT DEFAULT '',
    message_index      INTEGER NOT NULL DEFAULT 0,
    sentiment_label    TEXT NOT NULL DEFAULT 'neutral',
    sentiment_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    heuristic_version  TEXT DEFAULT '',
    evidence_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_session_sentiment_facts_session
    ON session_sentiment_facts(session_id, message_index, source_log_id);

CREATE TABLE IF NOT EXISTS session_code_churn_facts (
    id                       BIGSERIAL PRIMARY KEY,
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
    churn_score              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    progress_score           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    low_progress_loop        BOOLEAN NOT NULL DEFAULT FALSE,
    confidence               DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    heuristic_version        TEXT DEFAULT '',
    evidence_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_session_code_churn_facts_session
    ON session_code_churn_facts(session_id, file_path);

CREATE TABLE IF NOT EXISTS session_scope_drift_facts (
    id                      BIGSERIAL PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id              TEXT DEFAULT '',
    root_session_id         TEXT DEFAULT '',
    thread_session_id       TEXT DEFAULT '',
    planned_path_count      INTEGER NOT NULL DEFAULT 0,
    actual_path_count       INTEGER NOT NULL DEFAULT 0,
    matched_path_count      INTEGER NOT NULL DEFAULT 0,
    out_of_scope_path_count INTEGER NOT NULL DEFAULT 0,
    drift_ratio             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    adherence_score         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    heuristic_version       TEXT DEFAULT '',
    evidence_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    threshold  DOUBLE PRECISION NOT NULL,
    is_active  INTEGER DEFAULT 1,
    scope      TEXT DEFAULT 'session'
);

-- ── 12. SkillMeat Definition Cache + Stack Observations ───────────
CREATE TABLE IF NOT EXISTS external_definition_sources (
    id                  SERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    source_kind         TEXT NOT NULL DEFAULT 'skillmeat',
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    base_url            TEXT DEFAULT '',
    project_mapping_json JSONB DEFAULT '{}'::jsonb,
    feature_flags_json  JSONB DEFAULT '{}'::jsonb,
    last_synced_at      TEXT DEFAULT '',
    last_sync_status    TEXT DEFAULT 'never',
    last_sync_error     TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    UNIQUE(project_id, source_kind)
);

CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project
    ON external_definition_sources(project_id, source_kind);
CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project_mapping
    ON external_definition_sources USING GIN (project_mapping_json);

CREATE TABLE IF NOT EXISTS external_definitions (
    id                  SERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    source_id           INTEGER NOT NULL REFERENCES external_definition_sources(id) ON DELETE CASCADE,
    definition_type     TEXT NOT NULL,
    external_id         TEXT NOT NULL,
    display_name        TEXT DEFAULT '',
    version             TEXT DEFAULT '',
    source_url          TEXT DEFAULT '',
    resolution_metadata_json JSONB DEFAULT '{}'::jsonb,
    raw_snapshot_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at          TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    UNIQUE(project_id, definition_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_external_definitions_lookup
    ON external_definitions(project_id, definition_type, external_id);
CREATE INDEX IF NOT EXISTS idx_external_definitions_source
    ON external_definitions(source_id, definition_type);
CREATE INDEX IF NOT EXISTS idx_external_definitions_name
    ON external_definitions(project_id, display_name);
CREATE INDEX IF NOT EXISTS idx_external_definitions_raw_snapshot
    ON external_definitions USING GIN (raw_snapshot_json);

CREATE TABLE IF NOT EXISTS artifact_snapshot_cache (
    id             BIGSERIAL PRIMARY KEY,
    project_id     TEXT NOT NULL,
    collection_id  TEXT DEFAULT '',
    schema_version TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    fetched_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    artifact_count INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'fetched',
    raw_json       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_fetched
    ON artifact_snapshot_cache(project_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_collection
    ON artifact_snapshot_cache(project_id, collection_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_raw
    ON artifact_snapshot_cache USING GIN (raw_json);

CREATE TABLE IF NOT EXISTS artifact_identity_map (
    id                BIGSERIAL PRIMARY KEY,
    project_id        TEXT NOT NULL,
    ccdash_name       TEXT NOT NULL,
    ccdash_type       TEXT NOT NULL DEFAULT '',
    skillmeat_uuid    TEXT DEFAULT '',
    content_hash      TEXT DEFAULT '',
    match_tier        TEXT NOT NULL DEFAULT 'unresolved',
    confidence        DOUBLE PRECISION,
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

CREATE TABLE IF NOT EXISTS pricing_catalog_entries (
    id                  BIGSERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    platform_type       TEXT NOT NULL,
    model_id            TEXT NOT NULL DEFAULT '',
    context_window_size INTEGER,
    input_cost_per_million DOUBLE PRECISION,
    output_cost_per_million DOUBLE PRECISION,
    cache_creation_cost_per_million DOUBLE PRECISION,
    cache_read_cost_per_million DOUBLE PRECISION,
    speed_multiplier_fast DOUBLE PRECISION,
    source_type         TEXT NOT NULL DEFAULT 'bundled',
    source_updated_at   TEXT DEFAULT '',
    override_locked     BOOLEAN NOT NULL DEFAULT FALSE,
    sync_status         TEXT NOT NULL DEFAULT 'never',
    sync_error          TEXT DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    UNIQUE(project_id, platform_type, model_id)
);

CREATE INDEX IF NOT EXISTS idx_pricing_catalog_project_platform
    ON pricing_catalog_entries(project_id, platform_type, model_id);
CREATE INDEX IF NOT EXISTS idx_pricing_catalog_source
    ON pricing_catalog_entries(project_id, source_type, sync_status);

CREATE TABLE IF NOT EXISTS session_stack_observations (
    id                  SERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_id          TEXT DEFAULT '',
    workflow_ref        TEXT DEFAULT '',
    confidence          DOUBLE PRECISION DEFAULT 0.0,
    observation_source  TEXT DEFAULT 'backfill',
    evidence_json       JSONB DEFAULT '{}'::jsonb,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    UNIQUE(project_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_session_stack_observations_session
    ON session_stack_observations(project_id, session_id);
CREATE INDEX IF NOT EXISTS idx_session_stack_observations_feature
    ON session_stack_observations(project_id, feature_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_stack_observations_evidence
    ON session_stack_observations USING GIN (evidence_json);

CREATE TABLE IF NOT EXISTS session_stack_components (
    id                  BIGSERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    observation_id      INTEGER NOT NULL REFERENCES session_stack_observations(id) ON DELETE CASCADE,
    component_type      TEXT NOT NULL,
    component_key       TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'explicit',
    confidence          DOUBLE PRECISION DEFAULT 0.0,
    external_definition_id INTEGER REFERENCES external_definitions(id) ON DELETE SET NULL,
    external_definition_type TEXT DEFAULT '',
    external_definition_external_id TEXT DEFAULT '',
    source_attribution  TEXT DEFAULT '',
    component_payload_json JSONB DEFAULT '{}'::jsonb,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE INDEX IF NOT EXISTS idx_session_stack_components_observation
    ON session_stack_components(observation_id, component_type);
CREATE INDEX IF NOT EXISTS idx_session_stack_components_resolution
    ON session_stack_components(project_id, status, component_type);
CREATE INDEX IF NOT EXISTS idx_session_stack_components_payload
    ON session_stack_components USING GIN (component_payload_json);

CREATE TABLE IF NOT EXISTS effectiveness_rollups (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            TEXT NOT NULL,
    scope_type            TEXT NOT NULL,
    scope_id              TEXT NOT NULL,
    period                TEXT NOT NULL,
    metrics_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_effectiveness_rollups_scope
    ON effectiveness_rollups(project_id, scope_type, scope_id, period);
CREATE INDEX IF NOT EXISTS idx_effectiveness_rollups_period
    ON effectiveness_rollups(project_id, period, updated_at DESC);

CREATE TABLE IF NOT EXISTS session_memory_drafts (
    id                   BIGSERIAL PRIMARY KEY,
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
    confidence           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    source_message_id    TEXT DEFAULT '',
    source_log_id        TEXT DEFAULT '',
    source_message_index INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL DEFAULT '',
    evidence_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    publish_attempts     INTEGER NOT NULL DEFAULT 0,
    published_module_id  TEXT DEFAULT '',
    published_memory_id  TEXT DEFAULT '',
    reviewed_by          TEXT DEFAULT '',
    review_notes         TEXT DEFAULT '',
    reviewed_at          TEXT DEFAULT '',
    published_at         TEXT DEFAULT '',
    last_publish_error   TEXT DEFAULT '',
    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    UNIQUE(project_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_project_status
    ON session_memory_drafts(project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_session
    ON session_memory_drafts(project_id, session_id, updated_at DESC);

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
    metadata_json         JSONB DEFAULT '{}'::jsonb,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_runs_project_feature_created
    ON execution_runs(project_id, feature_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_runs_project_status_updated
    ON execution_runs(project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_runs_metadata_json
    ON execution_runs USING GIN (metadata_json);

CREATE TABLE IF NOT EXISTS execution_run_events (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES execution_runs(id) ON DELETE CASCADE,
    sequence_no   INTEGER NOT NULL,
    stream        TEXT NOT NULL DEFAULT 'system',
    event_type    TEXT NOT NULL DEFAULT 'status',
    payload_text  TEXT DEFAULT '',
    payload_json  JSONB DEFAULT '{}'::jsonb,
    occurred_at   TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_run_events_seq
    ON execution_run_events(run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_execution_run_events_lookup
    ON execution_run_events(run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_execution_run_events_payload_json
    ON execution_run_events USING GIN (payload_json);

CREATE TABLE IF NOT EXISTS execution_approvals (
    id            BIGSERIAL PRIMARY KEY,
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
    metadata_json     JSONB DEFAULT '{}'::jsonb,
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
CREATE INDEX IF NOT EXISTS idx_planning_worktree_metadata_json
    ON planning_worktree_contexts USING GIN (metadata_json);

-- ── 15. Filesystem Scan Manifest ──────────────────────────────────
CREATE TABLE IF NOT EXISTS filesystem_scan_manifest (
    path       TEXT PRIMARY KEY,
    mtime      DOUBLE PRECISION NOT NULL,
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
    metadata_json       JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_runs_project
    ON test_runs(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_session
    ON test_runs(project_id, agent_session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_sha
    ON test_runs(project_id, git_sha);
CREATE INDEX IF NOT EXISTS idx_test_runs_metadata_json
    ON test_runs USING GIN (metadata_json);

CREATE TABLE IF NOT EXISTS test_definitions (
    test_id         TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    path            TEXT NOT NULL,
    name            TEXT NOT NULL,
    framework       TEXT DEFAULT 'pytest',
    tags_json       JSONB DEFAULT '[]'::jsonb,
    owner           TEXT DEFAULT '',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_defs_project
    ON test_definitions(project_id);
CREATE INDEX IF NOT EXISTS idx_test_defs_path
    ON test_definitions(project_id, path);
CREATE INDEX IF NOT EXISTS idx_test_defs_tags_json
    ON test_definitions USING GIN (tags_json);

CREATE TABLE IF NOT EXISTS test_results (
    run_id              TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    status              TEXT NOT NULL,
    duration_ms         INTEGER DEFAULT 0,
    error_fingerprint   TEXT DEFAULT '',
    error_message       TEXT DEFAULT '',
    artifact_refs_json  JSONB DEFAULT '[]'::jsonb,
    stdout_ref          TEXT DEFAULT '',
    stderr_ref          TEXT DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, test_id)
);

CREATE INDEX IF NOT EXISTS idx_test_results_test
    ON test_results(test_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_status
    ON test_results(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_fingerprint
    ON test_results(error_fingerprint) WHERE error_fingerprint <> '';
CREATE INDEX IF NOT EXISTS idx_test_results_run
    ON test_results(run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_results_run_status
    ON test_results(run_id, status, test_id);
CREATE INDEX IF NOT EXISTS idx_test_results_test_run
    ON test_results(test_id, run_id);
CREATE INDEX IF NOT EXISTS idx_test_results_artifact_refs_json
    ON test_results USING GIN (artifact_refs_json);

CREATE TABLE IF NOT EXISTS test_domains (
    domain_id       TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    parent_id       TEXT REFERENCES test_domains(domain_id),
    description     TEXT DEFAULT '',
    tier            TEXT DEFAULT 'core',
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_domains_project
    ON test_domains(project_id);
CREATE INDEX IF NOT EXISTS idx_test_domains_parent
    ON test_domains(parent_id) WHERE parent_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS test_feature_mappings (
    mapping_id          BIGSERIAL PRIMARY KEY,
    project_id          TEXT NOT NULL,
    test_id             TEXT NOT NULL REFERENCES test_definitions(test_id),
    feature_id          TEXT NOT NULL,
    domain_id           TEXT REFERENCES test_domains(domain_id),
    provider_source     TEXT NOT NULL,
    confidence          DOUBLE PRECISION DEFAULT 0.5,
    version             INTEGER DEFAULT 1,
    snapshot_hash       TEXT DEFAULT '',
    is_primary          INTEGER DEFAULT 0,
    metadata_json       JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mappings_test
    ON test_feature_mappings(project_id, test_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_feature
    ON test_feature_mappings(project_id, feature_id, is_primary);
CREATE INDEX IF NOT EXISTS idx_mappings_domain
    ON test_feature_mappings(project_id, domain_id);
CREATE INDEX IF NOT EXISTS idx_mappings_primary_feature_test
    ON test_feature_mappings(project_id, feature_id, test_id)
    WHERE is_primary = 1;
CREATE INDEX IF NOT EXISTS idx_mappings_primary_domain_test
    ON test_feature_mappings(project_id, domain_id, test_id)
    WHERE is_primary = 1;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mappings_upsert
    ON test_feature_mappings(test_id, feature_id, provider_source, version);
CREATE INDEX IF NOT EXISTS idx_mappings_metadata_json
    ON test_feature_mappings USING GIN (metadata_json);

CREATE TABLE IF NOT EXISTS test_integrity_signals (
    signal_id           TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    git_sha             TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    test_id             TEXT REFERENCES test_definitions(test_id),
    signal_type         TEXT NOT NULL,
    severity            TEXT DEFAULT 'medium',
    details_json        JSONB DEFAULT '{}'::jsonb,
    linked_run_ids_json JSONB DEFAULT '[]'::jsonb,
    agent_session_id    TEXT DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
CREATE INDEX IF NOT EXISTS idx_integrity_details_json
    ON test_integrity_signals USING GIN (details_json);
CREATE INDEX IF NOT EXISTS idx_integrity_linked_runs_json
    ON test_integrity_signals USING GIN (linked_run_ids_json);

CREATE TABLE IF NOT EXISTS test_metrics (
    metric_id            BIGSERIAL PRIMARY KEY,
    project_id           TEXT NOT NULL,
    run_id               TEXT DEFAULT '',
    platform             TEXT NOT NULL,
    metric_type          TEXT NOT NULL,
    metric_name          TEXT NOT NULL,
    metric_value         DOUBLE PRECISION DEFAULT 0,
    unit                 TEXT DEFAULT '',
    metadata_json        JSONB DEFAULT '{}'::jsonb,
    source_file          TEXT DEFAULT '',
    collected_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_metrics_project
    ON test_metrics(project_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_metrics_platform
    ON test_metrics(project_id, platform, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_metrics_metric_type
    ON test_metrics(project_id, metric_type, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_metrics_metadata_json
    ON test_metrics USING GIN (metadata_json);
"""

_ENTERPRISE_IDENTITY_AUDIT_TABLES = """
-- ── Enterprise-Only: Identity & Access ────────────────────────────
-- These tables exist only in enterprise Postgres mode.
-- SQLite local mode intentionally does not include identity or audit concerns.
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS identity.principals (
    id              TEXT PRIMARY KEY,
    principal_type  TEXT NOT NULL,
    external_id     TEXT DEFAULT '',
    display_name    TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_principals_type
    ON identity.principals(principal_type, status);
CREATE INDEX IF NOT EXISTS idx_principals_external
    ON identity.principals(external_id) WHERE external_id != '';
CREATE INDEX IF NOT EXISTS idx_principals_email
    ON identity.principals(email) WHERE email != '';

CREATE TABLE IF NOT EXISTS identity.scope_identifiers (
    id              TEXT PRIMARY KEY,
    scope_type      TEXT NOT NULL,
    parent_scope_id TEXT REFERENCES identity.scope_identifiers(id),
    display_name    TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scope_identifiers_type
    ON identity.scope_identifiers(scope_type, status);
CREATE INDEX IF NOT EXISTS idx_scope_identifiers_parent
    ON identity.scope_identifiers(parent_scope_id) WHERE parent_scope_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity.memberships (
    id              TEXT PRIMARY KEY,
    principal_id    TEXT NOT NULL REFERENCES identity.principals(id) ON DELETE CASCADE,
    scope_id        TEXT NOT NULL REFERENCES identity.scope_identifiers(id) ON DELETE CASCADE,
    membership_type TEXT NOT NULL DEFAULT 'member',
    status          TEXT NOT NULL DEFAULT 'active',
    granted_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP WITH TIME ZONE,
    granted_by      TEXT DEFAULT '',
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memberships_principal
    ON identity.memberships(principal_id, status);
CREATE INDEX IF NOT EXISTS idx_memberships_scope
    ON identity.memberships(scope_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memberships_unique
    ON identity.memberships(principal_id, scope_id, membership_type);

CREATE TABLE IF NOT EXISTS identity.role_bindings (
    id              TEXT PRIMARY KEY,
    principal_id    TEXT NOT NULL REFERENCES identity.principals(id) ON DELETE CASCADE,
    scope_id        TEXT NOT NULL REFERENCES identity.scope_identifiers(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    granted_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP WITH TIME ZONE,
    granted_by      TEXT DEFAULT '',
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_role_bindings_principal
    ON identity.role_bindings(principal_id, status);
CREATE INDEX IF NOT EXISTS idx_role_bindings_scope
    ON identity.role_bindings(scope_id, role, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_bindings_unique
    ON identity.role_bindings(principal_id, scope_id, role);

-- ── Enterprise-Only: Audit & Security ─────────────────────────────

CREATE TABLE IF NOT EXISTS audit.privileged_action_audit_records (
    id              TEXT PRIMARY KEY,
    actor_id        TEXT NOT NULL,
    scope_id        TEXT NOT NULL,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL DEFAULT '',
    resource_id     TEXT DEFAULT '',
    decision        TEXT NOT NULL DEFAULT 'allowed',
    decision_reason TEXT DEFAULT '',
    ip_address      TEXT DEFAULT '',
    user_agent      TEXT DEFAULT '',
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_records_actor
    ON audit.privileged_action_audit_records(actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_records_scope
    ON audit.privileged_action_audit_records(scope_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_records_action
    ON audit.privileged_action_audit_records(action, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_records_resource
    ON audit.privileged_action_audit_records(resource_type, resource_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS audit.access_decision_logs (
    id               TEXT PRIMARY KEY,
    principal_id     TEXT NOT NULL,
    scope_id         TEXT NOT NULL,
    resource_type    TEXT NOT NULL,
    resource_id      TEXT DEFAULT '',
    requested_action TEXT NOT NULL,
    decision         TEXT NOT NULL,
    evaluator        TEXT NOT NULL DEFAULT 'policy_engine',
    matched_binding_id TEXT DEFAULT '',
    metadata_json    JSONB DEFAULT '{}'::jsonb,
    occurred_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_access_logs_principal
    ON audit.access_decision_logs(principal_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_scope
    ON audit.access_decision_logs(scope_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_resource
    ON audit.access_decision_logs(resource_type, resource_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_decision
    ON audit.access_decision_logs(decision, occurred_at DESC);
"""

_ENTERPRISE_SESSION_INTELLIGENCE_TABLES = """
-- ── Enterprise-Only: Session Intelligence ─────────────────────────
-- Transcript embedding storage is enterprise-only in Phase 2.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.session_embeddings (
    id                   BIGSERIAL PRIMARY KEY,
    session_id           TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    block_kind           TEXT NOT NULL,
    block_index          INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL,
    message_ids_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    content              TEXT NOT NULL DEFAULT '',
    embedding_model      TEXT NOT NULL DEFAULT '',
    embedding_dimensions INTEGER NOT NULL DEFAULT 0,
    embedding            vector,
    metadata_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_embeddings_content_hash
    ON app.session_embeddings(session_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_session_embeddings_lookup
    ON app.session_embeddings(session_id, block_kind, block_index);
"""

_SEED_METRIC_TYPES = """
INSERT INTO metric_types (id, display_name, unit, value_type, aggregation, description) VALUES
    ('session_cost',        'Session Cost',      '$',       'gauge',   'sum',   'Total cost per session'),
    ('session_tokens',      'Tokens Used',       'tokens',  'counter', 'sum',   'Total tokens consumed'),
    ('session_duration',    'Session Duration',   'seconds', 'gauge',   'avg',   'Average session duration'),
    ('session_count',       'Sessions',          'count',   'counter', 'count', 'Number of sessions'),
    ('task_velocity',       'Tasks Completed',   'count',   'counter', 'count', 'Tasks completed per period'),
    ('task_completion_pct', 'Completion %',      '%',       'gauge',   'avg',   'Task completion percentage'),
    ('feature_progress',    'Feature Progress',  '%',       'gauge',   'avg',   'Feature progress percentage'),
    ('tool_call_count',     'Tool Calls',        'count',   'counter', 'sum',   'Total tool invocations'),
    ('tool_success_rate',   'Tool Success Rate', '%',       'gauge',   'avg',   'Tool call success rate'),
    ('file_churn',          'Files Modified',    'count',   'counter', 'sum',   'Files changed per period')
ON CONFLICT (id) DO NOTHING;
"""

_SEED_ALERT_CONFIGS = """
INSERT INTO alert_configs (id, project_id, name, metric, operator, threshold, is_active, scope) VALUES
    ('alert-cost',     NULL, 'Cost Threshold', 'cost_threshold', '>', 5.0,  1, 'session'),
    ('alert-duration', NULL, 'Long Session',   'total_tokens',   '>', 600,  1, 'session'),
    ('alert-friction', NULL, 'High Friction',  'avg_quality',    '<', 3,    0, 'weekly')
ON CONFLICT (id) DO NOTHING;
"""


async def _column_exists(db: asyncpg.Connection, table: str, column: str) -> bool:
    row = await db.fetchrow(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = $1 AND column_name = $2
        LIMIT 1
        """,
        table,
        column,
    )
    return row is not None


async def _ensure_column(db: asyncpg.Connection, table: str, column: str, definition: str) -> None:
    if await _column_exists(db, table, column):
        return
    await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def _backfill_feature_query_columns(db: asyncpg.Connection) -> None:
    await db.execute(
        """
        UPDATE features
        SET
            tags_json = COALESCE(NULLIF(data_json, '')::jsonb->'tags', '[]'::jsonb)::text,
            deferred_tasks = COALESCE((NULLIF(data_json, '')::jsonb->>'deferredTasks')::integer, 0),
            planned_at = COALESCE(NULLIF(data_json, '')::jsonb->>'plannedAt', ''),
            started_at = COALESCE(NULLIF(data_json, '')::jsonb->>'startedAt', '')
        """
    )


async def _ensure_test_visualizer_tables(db: asyncpg.Connection) -> None:
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        return
    await db.execute(_TEST_VISUALIZER_TABLES)


async def _ensure_planning_worktree_contexts_table(db: asyncpg.Connection) -> None:
    """Idempotent: create planning_worktree_contexts table and indexes if missing."""
    await db.execute(_PLANNING_WORKTREE_CONTEXTS_DDL)


async def _ensure_enterprise_identity_audit_tables(db: asyncpg.Connection) -> None:
    """Create enterprise-only identity and audit tables (idempotent)."""
    await db.execute(_ENTERPRISE_IDENTITY_AUDIT_TABLES)


async def _ensure_enterprise_session_intelligence_tables(db: asyncpg.Connection) -> None:
    """Create enterprise-only session intelligence tables (idempotent)."""
    await db.execute(_ENTERPRISE_SESSION_INTELLIGENCE_TABLES)


async def _ensure_entity_link_uniqueness(db: asyncpg.Connection) -> None:
    # Deduplicate legacy rows before enforcing unique upsert key.
    await db.execute(
        """
        DELETE FROM entity_links a
        USING entity_links b
        WHERE a.id < b.id
          AND a.source_type = b.source_type
          AND a.source_id = b.source_id
          AND a.target_type = b.target_type
          AND a.target_id = b.target_id
          AND a.link_type = b.link_type
        """
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert
            ON entity_links(source_type, source_id, target_type, target_id, link_type)
        """
    )


async def run_migrations(db: asyncpg.Connection) -> None:
    """Create all tables and seed data. Idempotent."""
    # Check current schema version
    try:
        row = await db.fetchrow("SELECT MAX(version) FROM schema_version")
        current_version = row[0] if row and row[0] else 0
    except Exception:
        # Table doesn't exist
        current_version = 0

    should_record_version = current_version < SCHEMA_VERSION
    if should_record_version:
        logger.info(f"Running migrations: {current_version} → {SCHEMA_VERSION}")
        # Execute all CREATE TABLE statements (split by semicolon if needed, but asyncpg execute() handles multiple statements?)
        # asyncpg execute() supports multiple statements.
        await db.execute(_TABLES)
    else:
        logger.info(f"Schema version {current_version} already recorded; running idempotent column/index checks")
    await _ensure_test_visualizer_tables(db)
    await _ensure_planning_worktree_contexts_table(db)
    await _ensure_enterprise_identity_audit_tables(db)
    await _ensure_enterprise_session_intelligence_tables(db)
    await _ensure_entity_link_uniqueness(db)

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
    await _ensure_column(db, "sessions", "context_utilization_pct", "DOUBLE PRECISION DEFAULT 0.0")
    await _ensure_column(db, "sessions", "context_measurement_source", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "context_measured_at", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "tool_reported_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_output_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_cache_creation_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "tool_result_cache_read_input_tokens", "INTEGER DEFAULT 0")
    await _ensure_column(db, "sessions", "reported_cost_usd", "DOUBLE PRECISION")
    await _ensure_column(db, "sessions", "recalculated_cost_usd", "DOUBLE PRECISION")
    await _ensure_column(db, "sessions", "display_cost_usd", "DOUBLE PRECISION")
    await _ensure_column(db, "sessions", "cost_provenance", "TEXT DEFAULT 'unknown'")
    await _ensure_column(db, "sessions", "cost_confidence", "DOUBLE PRECISION DEFAULT 0.0")
    await _ensure_column(db, "sessions", "cost_mismatch_pct", "DOUBLE PRECISION")
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
    await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_root ON sessions(project_id, root_session_id, started_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_family ON sessions(project_id, conversation_family_id, started_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_thread_kind ON sessions(project_id, thread_kind, started_at DESC)")

    await _ensure_column(db, "outbound_telemetry_queue", "event_type", "TEXT NOT NULL DEFAULT 'execution_outcome'")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_outbound_telemetry_queue_event_type ON outbound_telemetry_queue(event_type, status)"
    )

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
    await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_source_log_id ON session_logs(session_id, source_log_id)")
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_source_log_unique ON session_logs(session_id, source_log_id) WHERE source_log_id != ''"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id             BIGSERIAL PRIMARY KEY,
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
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_messages_family ON session_messages(conversation_family_id, root_session_id, message_index)"
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_message ON session_messages(session_id, message_index)"
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
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_catalog_entries (
            id                  BIGSERIAL PRIMARY KEY,
            project_id          TEXT NOT NULL,
            platform_type       TEXT NOT NULL,
            model_id            TEXT NOT NULL DEFAULT '',
            context_window_size INTEGER,
            input_cost_per_million DOUBLE PRECISION,
            output_cost_per_million DOUBLE PRECISION,
            cache_creation_cost_per_million DOUBLE PRECISION,
            cache_read_cost_per_million DOUBLE PRECISION,
            speed_multiplier_fast DOUBLE PRECISION,
            source_type         TEXT NOT NULL DEFAULT 'bundled',
            source_updated_at   TEXT DEFAULT '',
            override_locked     BOOLEAN NOT NULL DEFAULT FALSE,
            sync_status         TEXT NOT NULL DEFAULT 'never',
            sync_error          TEXT DEFAULT '',
            created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            UNIQUE(project_id, platform_type, model_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_pricing_catalog_project_platform ON pricing_catalog_entries(project_id, platform_type, model_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_pricing_catalog_source ON pricing_catalog_entries(project_id, source_type, sync_status)"
    )
    await db.execute(
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
            cost_usd_model_io  DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (cost_usd_model_io >= 0),
            metadata_json      TEXT DEFAULT '{}'
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_usage_attributions (
            event_id            TEXT NOT NULL REFERENCES session_usage_events(id) ON DELETE CASCADE,
            entity_type         TEXT NOT NULL,
            entity_id           TEXT NOT NULL,
            attribution_role    TEXT NOT NULL,
            weight              DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
            method              TEXT NOT NULL,
            confidence          DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
            metadata_json       TEXT DEFAULT '{}',
            PRIMARY KEY (event_id, entity_type, entity_id, attribution_role, method)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_project ON session_usage_events(project_id, captured_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_session ON session_usage_events(session_id, captured_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_source ON session_usage_events(session_id, source_log_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_events_entity_dims ON session_usage_events(project_id, token_family, event_kind)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_entity ON session_usage_attributions(entity_type, entity_id, attribution_role)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_usage_attributions_method ON session_usage_attributions(method, attribution_role)"
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_usage_attributions_primary ON session_usage_attributions(event_id) WHERE attribution_role = 'primary'"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_relationships (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL,
            parent_session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            child_session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            relationship_type   TEXT NOT NULL,
            context_inheritance TEXT DEFAULT '',
            source_platform     TEXT DEFAULT '',
            parent_entry_uuid   TEXT DEFAULT '',
            child_entry_uuid    TEXT DEFAULT '',
            source_log_id       TEXT,
            metadata_json       TEXT DEFAULT '{}',
            source_file         TEXT DEFAULT '',
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_parent ON session_relationships(project_id, parent_session_id, relationship_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_child ON session_relationships(project_id, child_session_id, relationship_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_relationships_source ON session_relationships(project_id, source_file)"
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_relationships_unique ON session_relationships(project_id, parent_session_id, child_session_id, relationship_type, parent_entry_uuid, child_entry_uuid)"
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
    await _ensure_column(db, "documents", "overall_progress", "DOUBLE PRECISION")
    await _ensure_column(db, "documents", "total_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "completed_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "in_progress_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "blocked_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "documents", "metadata_json", "TEXT DEFAULT '{}'")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_canonical_path ON documents(project_id, canonical_path)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_root_subtype ON documents(project_id, root_kind, doc_subtype)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_status_norm ON documents(project_id, status_normalized)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_feature_slug ON documents(project_id, feature_slug_canonical)")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS document_refs (
            id             SERIAL PRIMARY KEY,
            document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            project_id     TEXT NOT NULL,
            ref_kind       TEXT NOT NULL,
            ref_value      TEXT NOT NULL,
            ref_value_norm TEXT NOT NULL,
            source_field   TEXT NOT NULL,
            created_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_refs_unique ON document_refs(document_id, ref_kind, ref_value_norm, source_field)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_refs_query ON document_refs(project_id, ref_kind, ref_value_norm)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS external_definition_sources (
            id                  SERIAL PRIMARY KEY,
            project_id          TEXT NOT NULL,
            source_kind         TEXT NOT NULL DEFAULT 'skillmeat',
            enabled             BOOLEAN NOT NULL DEFAULT FALSE,
            base_url            TEXT DEFAULT '',
            project_mapping_json JSONB DEFAULT '{}'::jsonb,
            feature_flags_json  JSONB DEFAULT '{}'::jsonb,
            last_synced_at      TEXT DEFAULT '',
            last_sync_status    TEXT DEFAULT 'never',
            last_sync_error     TEXT DEFAULT '',
            created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            UNIQUE(project_id, source_kind)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project ON external_definition_sources(project_id, source_kind)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definition_sources_project_mapping ON external_definition_sources USING GIN (project_mapping_json)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS external_definitions (
            id                  SERIAL PRIMARY KEY,
            project_id          TEXT NOT NULL,
            source_id           INTEGER NOT NULL REFERENCES external_definition_sources(id) ON DELETE CASCADE,
            definition_type     TEXT NOT NULL,
            external_id         TEXT NOT NULL,
            display_name        TEXT DEFAULT '',
            version             TEXT DEFAULT '',
            source_url          TEXT DEFAULT '',
            resolution_metadata_json JSONB DEFAULT '{}'::jsonb,
            raw_snapshot_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            UNIQUE(project_id, definition_type, external_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_lookup ON external_definitions(project_id, definition_type, external_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_source ON external_definitions(source_id, definition_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_name ON external_definitions(project_id, display_name)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_definitions_raw_snapshot ON external_definitions USING GIN (raw_snapshot_json)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_snapshot_cache (
            id             BIGSERIAL PRIMARY KEY,
            project_id     TEXT NOT NULL,
            collection_id  TEXT DEFAULT '',
            schema_version TEXT NOT NULL,
            generated_at   TEXT NOT NULL,
            fetched_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            artifact_count INTEGER NOT NULL DEFAULT 0,
            status         TEXT NOT NULL DEFAULT 'fetched',
            raw_json       JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_fetched ON artifact_snapshot_cache(project_id, fetched_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_project_collection ON artifact_snapshot_cache(project_id, collection_id, fetched_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_snapshot_cache_raw ON artifact_snapshot_cache USING GIN (raw_json)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_identity_map (
            id                BIGSERIAL PRIMARY KEY,
            project_id        TEXT NOT NULL,
            ccdash_name       TEXT NOT NULL,
            ccdash_type       TEXT NOT NULL DEFAULT '',
            skillmeat_uuid    TEXT DEFAULT '',
            content_hash      TEXT DEFAULT '',
            match_tier        TEXT NOT NULL DEFAULT 'unresolved',
            confidence        DOUBLE PRECISION,
            resolved_at       TEXT DEFAULT '',
            unresolved_reason TEXT DEFAULT ''
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_name ON artifact_identity_map(project_id, ccdash_name)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_uuid ON artifact_identity_map(project_id, skillmeat_uuid)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_hash ON artifact_identity_map(project_id, content_hash)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_identity_map_project_match_tier ON artifact_identity_map(project_id, match_tier)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_stack_observations (
            id                  SERIAL PRIMARY KEY,
            project_id          TEXT NOT NULL,
            session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            feature_id          TEXT DEFAULT '',
            workflow_ref        TEXT DEFAULT '',
            confidence          DOUBLE PRECISION DEFAULT 0.0,
            observation_source  TEXT DEFAULT 'backfill',
            evidence_json       JSONB DEFAULT '{}'::jsonb,
            created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            UNIQUE(project_id, session_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_session ON session_stack_observations(project_id, session_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_feature ON session_stack_observations(project_id, feature_id, updated_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_evidence ON session_stack_observations USING GIN (evidence_json)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_stack_components (
            id                  BIGSERIAL PRIMARY KEY,
            project_id          TEXT NOT NULL,
            observation_id      INTEGER NOT NULL REFERENCES session_stack_observations(id) ON DELETE CASCADE,
            component_type      TEXT NOT NULL,
            component_key       TEXT DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'explicit',
            confidence          DOUBLE PRECISION DEFAULT 0.0,
            external_definition_id INTEGER REFERENCES external_definitions(id) ON DELETE SET NULL,
            external_definition_type TEXT DEFAULT '',
            external_definition_external_id TEXT DEFAULT '',
            source_attribution  TEXT DEFAULT '',
            component_payload_json JSONB DEFAULT '{}'::jsonb,
            created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_components_observation ON session_stack_components(observation_id, component_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_components_resolution ON session_stack_components(project_id, status, component_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_stack_components_payload ON session_stack_components USING GIN (component_payload_json)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS effectiveness_rollups (
            id                    BIGSERIAL PRIMARY KEY,
            project_id            TEXT NOT NULL,
            scope_type            TEXT NOT NULL,
            scope_id              TEXT NOT NULL,
            period                TEXT NOT NULL,
            metrics_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
            evidence_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
        )
        """
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_effectiveness_rollups_scope ON effectiveness_rollups(project_id, scope_type, scope_id, period)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_effectiveness_rollups_period ON effectiveness_rollups(project_id, period, updated_at DESC)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS session_memory_drafts (
            id                   BIGSERIAL PRIMARY KEY,
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
            confidence           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            source_message_id    TEXT DEFAULT '',
            source_log_id        TEXT DEFAULT '',
            source_message_index INTEGER NOT NULL DEFAULT 0,
            content_hash         TEXT NOT NULL DEFAULT '',
            evidence_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
            publish_attempts     INTEGER NOT NULL DEFAULT 0,
            published_module_id  TEXT DEFAULT '',
            published_memory_id  TEXT DEFAULT '',
            reviewed_by          TEXT DEFAULT '',
            review_notes         TEXT DEFAULT '',
            reviewed_at          TEXT DEFAULT '',
            published_at         TEXT DEFAULT '',
            last_publish_error   TEXT DEFAULT '',
            created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            updated_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
            UNIQUE(project_id, content_hash)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_project_status ON session_memory_drafts(project_id, status, updated_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_session ON session_memory_drafts(project_id, session_id, updated_at DESC)"
    )

    # sessions: conversation_family_id single-column lookup
    # Used by: sessions.py:213 WHERE conversation_family_id = ?
    # (idx_sessions_family covers the 3-column form; this covers bare equality scans)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_conversation_family"
        " ON sessions(conversation_family_id)"
    )

    await _ensure_column(db, "features", "tags_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "features", "deferred_tasks", "INTEGER DEFAULT 0")
    await _ensure_column(db, "features", "planned_at", "TEXT DEFAULT ''")
    await _ensure_column(db, "features", "started_at", "TEXT DEFAULT ''")
    await _backfill_feature_query_columns(db)

    # features: promoted columns for queryable metadata and range filters
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_planned_at"
        " ON features(project_id, planned_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_started_at"
        " ON features(project_id, started_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_deferred_tasks"
        " ON features(project_id, deferred_tasks)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_category_lower"
        " ON features(project_id, LOWER(category))"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_tags_json"
        " ON features USING GIN ((COALESCE(tags_json, '[]')::jsonb))"
    )

    # features: composite (project_id, status) for planning summary status-IN queries
    # Used by: planning summary queries that filter status IN (...) within a project
    # (idx_features_project covers project_id alone; this eliminates residual status scan)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_project_status"
        " ON features(project_id, status)"
    )

    # feature_phases: composite (feature_id, status) for planning rollup status counters
    # Used by: planning rollup status-count queries grouping phases by status per feature
    # (idx_phases_feature covers feature_id alone; this eliminates residual status scan)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_phases_feature_status"
        " ON feature_phases(feature_id, status)"
    )

    # Seed metric types
    await db.execute(_SEED_METRIC_TYPES)

    # Seed default alert configs
    await db.execute(_SEED_ALERT_CONFIGS)

    # Record schema version
    if should_record_version:
        await db.execute(
            "INSERT INTO schema_version (version) VALUES ($1)",
            SCHEMA_VERSION,
        )
    logger.info(f"Migrations complete — schema version {max(current_version, SCHEMA_VERSION)}")
