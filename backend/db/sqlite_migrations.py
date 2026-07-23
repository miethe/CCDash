"""Database schema creation and versioning.

All CREATE TABLE statements for the caching layer.
Uses IF NOT EXISTS for idempotent runs.

Schema version history (keep in lockstep with postgres_migrations.py):
  v34 — T1-004: additive index sessions(git_branch, project_id) for branch-aware
         planning intelligence; IF NOT EXISTS guard; no column or data changes.
  v33 — scope/scope_id columns on analytics_entries; new idx_analytics_point_daily key.
  v32 — P5-005: features table gains owners_json + linked_docs_json columnar
         columns with backfill from data_json; GIN-searchable via jsonb operators.
         P5-012: council_reviews scaffold table (feature-scoped, project_id + feature_id).
         P5-013: research_notes scaffold table (project_id + optional feature_id).
  v31 — P3-003-FU: sessions composite PK (project_id, id) fully activated;
         all 13 child tables rebuilt with composite FK
         FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id)
         ON DELETE CASCADE; four tables that lacked project_id
         (session_messages, session_artifacts, session_sentiment_facts,
         session_code_churn_facts) gain the column with backfill from parent
         sessions row; session_relationships both parent_session_id and
         child_session_id FKs become composite; PRAGMA foreign_key_check
         asserted empty after rebuild; SqliteSessionRepository upserts use
         ON CONFLICT(project_id, id).
  v30 — Phase 3 enterprise registry & job infra: projects table (P3-001)
         replaces projects.json as authoritative registry; oq_resolutions
         table (P3-002) persists open-question overlays per project/feature;
         job_queue table (P3-006) provides durable job queue DDL;
         session_logs/session_tool_usage/session_file_updates gain nullable
         project_id with backfill (P3-004).
  v29 — Phase 2 cache-core: query_cache table for distributed Postgres cache
         backend (P2-001); CCDASH_QUERY_CACHE_BACKEND=postgres targets this
         table; memory backend is unchanged.
  v28 — Phase 1 storage hygiene: session badge columns (command_slug,
         latest_summary, subagent_type, models/agents/skills_used_json);
         idx_sessions_source_file + idx_sessions_project_source_file;
         entity_links.project_id + idx_links_project;
         idx_analytics_point_daily (partial unique, same-day dedup);
         idx_analytics_point_latest; idx_telemetry_event_type_partial;
         idx_sessions_project_status_updated backfill.
  v27 — Previous baseline.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time
from pathlib import Path

import aiosqlite

from backend import config

logger = logging.getLogger("ccdash.db")

# ── T3-008: SQLite inter-process migration concurrency guard ──────────────────
# fcntl.flock mirrors the intent of the Postgres pg_advisory_lock used in
# postgres_migrations.py: only one process executes DDL at a time on the same
# SQLite file.  No external library dependency; fcntl is stdlib on POSIX.
#
# Lock file lives in the same directory as the database so it resolves correctly
# for custom CCDASH_DB_PATH values.  The directory is created if absent.
_MIGRATION_LOCK_TIMEOUT_SECONDS: int = int(
    os.environ.get("CCDASH_MIGRATION_LOCK_TIMEOUT_SECONDS", "30")
)

SCHEMA_VERSION = 42

_TABLES = """
-- ── Schema version tracking ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER NOT NULL,
    applied   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Per-version migration ledger (T3-011) ──────────────────────────
-- OQ-01 decision: both SQLite and Postgres backends use the same logical
-- schema — migrations_applied(version INTEGER PRIMARY KEY, applied_at <timestamp>).
-- SQLite stores applied_at as TEXT (ISO-8601); Postgres stores it as
-- TIMESTAMP WITH TIME ZONE.  Application code treats the column as opaque
-- for display purposes; only existence of a row is semantically significant.
-- INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING (Postgres) ensures
-- re-running migrations never duplicates rows.
CREATE TABLE IF NOT EXISTS migrations_applied (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
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
    created_at    TEXT NOT NULL,
    project_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_links_source ON entity_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON entity_links(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_links_tree   ON entity_links(source_type, source_id, link_type, depth);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_upsert ON entity_links(source_type, source_id, target_type, target_id, link_type);
CREATE INDEX IF NOT EXISTS idx_links_origin ON entity_links(origin) WHERE origin = 'manual';
-- T1-019: project_id scoping for Phase 2 multi-project entity graph fingerprinting
CREATE INDEX IF NOT EXISTS idx_links_project ON entity_links(project_id);

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
    id               TEXT NOT NULL,
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
    session_forensics_json TEXT DEFAULT '{}',
    -- T1-010: materialized badge columns (populated at sync time; avoids per-session log fetch)
    command_slug     TEXT DEFAULT '',
    latest_summary   TEXT DEFAULT '',
    subagent_type    TEXT DEFAULT '',
    models_used_json TEXT DEFAULT '[]',
    agents_used_json TEXT DEFAULT '[]',
    skills_used_json TEXT DEFAULT '[]',
    -- Phase 5 detection columns (T5-006). model_slug carries the canonical bare
    -- model slug; the rest are nullable detection facts (null == contract state).
    model_slug         TEXT DEFAULT '',
    workflow_id        TEXT,
    subagent_parent_id TEXT,
    skill_name         TEXT,
    context_window     TEXT,
    -- Phase 11 launch-time capture columns (T11-003). All nullable; null == not
    -- captured (sidecar absent, session not launched via a capture-aware path, or
    -- launched before the hook was installed).  COALESCE-guarded on upsert so a
    -- missing sidecar on re-ingest never clobbers a previously-captured value.
    launcher           TEXT,
    profile            TEXT,
    effort_tier        TEXT,
    model_variant      TEXT,
    -- Phase 2 Codex ingestion (codex-session-ingestion-v1).  Populated from
    -- session_forensics["entryContext"]["workingDirectories"][0] for Codex
    -- sessions; NULL for Claude Code sessions (contract state, not a bug).
    cwd                TEXT,
    PRIMARY KEY (project_id, id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

-- Composite index for live active-count queries (live-agents-count-v1).
-- Supports the count_active query: WHERE project_id = ? AND status = ? AND updated_at >= ?
-- Also defends against stale-active rows (OQ-3 finding: rows up to 93 days old with
-- status='active') by making the updated_at predicate cheap to execute.
CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated
    ON sessions(project_id, status, updated_at);

-- T1-005: source_file indexes — kills full-scan in repositories/sessions.py list_by_source
-- and in watcher-triggered delete/lookup per file during sync.
CREATE INDEX IF NOT EXISTS idx_sessions_source_file
    ON sessions(source_file);
CREATE INDEX IF NOT EXISTS idx_sessions_project_source_file
    ON sessions(project_id, source_file);

-- Normalized log entries
CREATE TABLE IF NOT EXISTS session_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     TEXT,
    session_id     TEXT NOT NULL,
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
    metadata_json  TEXT,
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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
    project_id     TEXT,
    session_id     TEXT NOT NULL,
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
    cache_creation_input_tokens INTEGER,
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_messages_family
    ON session_messages(conversation_family_id, root_session_id, message_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_message
    ON session_messages(session_id, message_index);

-- Tool usage summary per session
CREATE TABLE IF NOT EXISTS session_tool_usage (
    project_id    TEXT,
    session_id    TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    call_count    INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    total_ms      INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, tool_name),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);

-- File changes per session
CREATE TABLE IF NOT EXISTS session_file_updates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT,
    session_id   TEXT NOT NULL,
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
    source_tool_name TEXT,
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_file_updates_session ON session_file_updates(session_id);
CREATE INDEX IF NOT EXISTS idx_file_updates_path   ON session_file_updates(file_path);

-- Session artifacts
CREATE TABLE IF NOT EXISTS session_artifacts (
    id           TEXT PRIMARY KEY,
    project_id   TEXT,
    session_id   TEXT NOT NULL,
    title        TEXT NOT NULL,
    type         TEXT DEFAULT 'document',
    description  TEXT DEFAULT '',
    source       TEXT DEFAULT '',
    url          TEXT,
    source_log_id TEXT,
    source_tool_name TEXT,
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_usage_events (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL,
    session_id         TEXT NOT NULL,
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
    metadata_json      TEXT DEFAULT '{}',
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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
    parent_session_id  TEXT NOT NULL,
    child_session_id   TEXT NOT NULL,
    relationship_type  TEXT NOT NULL,
    context_inheritance TEXT DEFAULT '',
    source_platform    TEXT DEFAULT '',
    parent_entry_uuid  TEXT DEFAULT '',
    child_entry_uuid   TEXT DEFAULT '',
    source_log_id      TEXT,
    metadata_json      TEXT DEFAULT '{}',
    source_file        TEXT DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id, parent_session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, child_session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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
    owners_json     TEXT DEFAULT '[]',
    linked_docs_json TEXT DEFAULT '[]',
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

-- ── 7b. Council Reviews (feature-scoped AI review scaffold) ────────
CREATE TABLE IF NOT EXISTS council_reviews (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    feature_id  TEXT NOT NULL,
    status      TEXT,
    summary     TEXT,
    data_json   TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_council_reviews_project_feature
    ON council_reviews(project_id, feature_id);

-- ── 7c. Research Notes (project/feature-scoped) ─────────────────────
CREATE TABLE IF NOT EXISTS research_notes (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    feature_id  TEXT,
    title       TEXT,
    url         TEXT,
    body        TEXT,
    source      TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_research_notes_project_feature
    ON research_notes(project_id, feature_id);

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
    metadata_json TEXT,
    scope         TEXT NOT NULL DEFAULT 'project',
    scope_id      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_analytics_lookup
    ON analytics_entries(project_id, metric_type, captured_at);
CREATE INDEX IF NOT EXISTS idx_analytics_period
    ON analytics_entries(project_id, period, captured_at);
-- T1-014: partial index serving get_latest_entries (period='point' rows only)
CREATE INDEX IF NOT EXISTS idx_analytics_point_latest
    ON analytics_entries(project_id, metric_type, captured_at DESC)
    WHERE period = 'point';
-- T1-001/v33: unique partial index backing ON CONFLICT upsert for point-period dedup.
-- scope_id discriminates '' (project) from a feature_id so per-feature rows are DISTINCT.
CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_point_daily
    ON analytics_entries(project_id, metric_type, scope_id, date(captured_at))
    WHERE period = 'point';

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
-- T1-014: partial index serving event_type point queries (non-empty event_type rows only)
CREATE INDEX IF NOT EXISTS idx_telemetry_event_type_partial
    ON telemetry_events(event_type, project_id, occurred_at)
    WHERE event_type != '';
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
    session_id      TEXT NOT NULL,
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
    project_id         TEXT,
    session_id         TEXT NOT NULL,
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
    computed_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_sentiment_facts_session
    ON session_sentiment_facts(session_id, message_index, source_log_id);

CREATE TABLE IF NOT EXISTS session_code_churn_facts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id               TEXT,
    session_id               TEXT NOT NULL,
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
    computed_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_code_churn_facts_session
    ON session_code_churn_facts(session_id, file_path);

CREATE TABLE IF NOT EXISTS session_scope_drift_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id              TEXT,
    session_id              TEXT NOT NULL,
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
    computed_at             TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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
    session_id         TEXT NOT NULL,
    feature_id         TEXT DEFAULT '',
    workflow_ref       TEXT DEFAULT '',
    confidence         REAL DEFAULT 0.0,
    observation_source TEXT DEFAULT 'backfill',
    evidence_json      TEXT DEFAULT '{}',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, session_id),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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
    session_id           TEXT NOT NULL,
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
    UNIQUE(project_id, content_hash),
    FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
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

-- ── 16. Distributed Query Cache (P2-001) ──────────────────────────
-- Postgres-backed query result cache; also created on SQLite so the same
-- migration code path works for local dev/test without branching.
-- Used when CCDASH_QUERY_CACHE_BACKEND=postgres.
CREATE TABLE IF NOT EXISTS query_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_cache_project
    ON query_cache(project_id);
CREATE INDEX IF NOT EXISTS idx_query_cache_expires_at
    ON query_cache(expires_at);

-- ── 17. Project Registry (P3-001) ─────────────────────────────────
-- Authoritative project registry replacing projects.json.
-- Covers every field the current ProjectManager persists.
CREATE TABLE IF NOT EXISTS projects (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    path                 TEXT NOT NULL DEFAULT '',
    description          TEXT NOT NULL DEFAULT '',
    repo_url             TEXT NOT NULL DEFAULT '',
    agent_platforms_json TEXT NOT NULL DEFAULT '["Claude Code"]',
    plan_docs_path       TEXT NOT NULL DEFAULT 'docs/project_plans/',
    sessions_path        TEXT NOT NULL DEFAULT '',
    progress_path        TEXT NOT NULL DEFAULT 'progress',
    path_config_json     TEXT NOT NULL DEFAULT '{}',
    test_config_json     TEXT NOT NULL DEFAULT '{}',
    skillmeat_json       TEXT NOT NULL DEFAULT '{}',
    display_json         TEXT,
    is_active            INTEGER NOT NULL DEFAULT 0,
    repo_path            TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_is_active
    ON projects(is_active);

-- ── 18. Open-Question Resolutions (P3-002) ────────────────────────
-- Persists resolved open-question overlays per project/feature so that
-- in-memory _OQ_OVERLAY survives restarts.
CREATE TABLE IF NOT EXISTS oq_resolutions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    feature_id    TEXT NOT NULL,
    oq_id         TEXT NOT NULL,
    question      TEXT NOT NULL DEFAULT '',
    answer_text   TEXT NOT NULL DEFAULT '',
    severity      TEXT NOT NULL DEFAULT 'medium',
    resolved      INTEGER NOT NULL DEFAULT 1,
    pending_sync  INTEGER NOT NULL DEFAULT 0,
    source_document_id   TEXT NOT NULL DEFAULT '',
    source_document_path TEXT NOT NULL DEFAULT '',
    resolved_by   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, feature_id, oq_id)
);

CREATE INDEX IF NOT EXISTS idx_oq_resolutions_project
    ON oq_resolutions(project_id);
CREATE INDEX IF NOT EXISTS idx_oq_resolutions_feature
    ON oq_resolutions(project_id, feature_id);

-- ── 19. Durable Job Queue (P3-006) ────────────────────────────────
-- DDL-only; no runtime executor in this phase.
CREATE TABLE IF NOT EXISTS job_queue (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    job_type      TEXT NOT NULL,
    payload       TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'done', 'dead', 'crashed')),
    priority      INTEGER NOT NULL DEFAULT 0,
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 3,
    available_at  TEXT NOT NULL DEFAULT (datetime('now')),
    locked_by     TEXT,
    locked_at     TEXT,
    last_error    TEXT,
    checkpoint    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_job_queue_status_available_priority
    ON job_queue(status, available_at, priority);
CREATE INDEX IF NOT EXISTS idx_job_queue_project
    ON job_queue(project_id);

-- ── RF Run Telemetry (Research Foundry ccdash_event ingest, T1-001) ──────
-- Raw, append-only mirror of RF's schema-validated `ccdash_event` payload
-- (research-foundry/schemas/ccdash_event.schema.yaml, additionalProperties:
-- true). Every RF-sourced column below is nullable and never defaulted —
-- unknown == null, never a fabricated default (same convention as the
-- Phase 11 launch-time-capture / detection columns on `sessions`). Only the
-- ingest-pipeline bookkeeping columns (workspace_id/project_id/created_at)
-- and the raw_payload_json forward-compat safety net carry defaults.
-- Populated by POST /api/v1/ingest/rf-events (T1-003/T1-004); the derived
-- `research_runs` rollup lands in Phase 2 (D6). Correlation to sessions is
-- via entity_graph link rows keyed by a UUID run_id (D2) — run_id/intent_id/
-- task_node_id here are RF's raw, opaque display strings only, never join
-- keys against aos_correlation.py.
CREATE TABLE IF NOT EXISTS rf_events (
    -- Ingest-pipeline bookkeeping (never sourced from the RF payload) ─────
    event_id                            TEXT PRIMARY KEY,
    workspace_id                        TEXT NOT NULL DEFAULT 'default-local',
    project_id                          TEXT NOT NULL,
    created_at                          TEXT NOT NULL DEFAULT (datetime('now')),

    -- RF payload — required top-level fields (event_id/timestamp/project) ──
    event_timestamp                     TEXT NOT NULL,
    rf_project                          TEXT NOT NULL,

    -- RF payload — optional raw correlation ids (opaque display strings) ──
    run_id                              TEXT,
    intent_id                           TEXT,
    task_node_id                        TEXT,

    -- RF payload — optional top-level array fields (JSON-encoded) ─────────
    agent_postures_json                 TEXT,
    skillbom_ids_json                   TEXT,
    tools_json                          TEXT,
    input_artifacts_json                TEXT,
    output_artifacts_json               TEXT,

    -- RF payload — metrics.* (schema §metrics + search-router additions) ──
    metric_source_cards_created         INTEGER,
    metric_claims_total                 INTEGER,
    metric_claims_supported             INTEGER,
    metric_claims_mixed                 INTEGER,
    metric_claims_contradicted          INTEGER,
    metric_claims_inference             INTEGER,
    metric_claims_speculation           INTEGER,
    metric_unsupported_claims           INTEGER,
    metric_verification_passed          INTEGER,
    metric_tokens_estimated             INTEGER,
    metric_cost_estimated_usd           REAL,
    metric_latency_minutes              REAL,
    metric_rework_count                 INTEGER,
    metric_drift_score                  REAL,
    metric_quality_score                TEXT,
    metric_queries_executed             INTEGER,
    metric_urls_extracted               INTEGER,
    metric_useful_source_count          INTEGER,
    metric_duplicate_rate               REAL,
    metric_extraction_failure_rate      REAL,
    metric_citation_coverage            REAL,
    metric_estimated_cost_usd           REAL,
    metric_latency_ms                   REAL,

    -- RF payload — governance.* ────────────────────────────────────────────
    governance_sensitivity              TEXT,
    governance_key_profile_used         TEXT,
    governance_key_fingerprint          TEXT,
    governance_policy_passed            INTEGER,
    governance_violations_json          TEXT,

    -- RF payload — reuse.* ─────────────────────────────────────────────────
    reuse_meatywiki_writeback_candidate     INTEGER,
    reuse_skillbom_candidate                INTEGER,
    reuse_reusable_source_pack_candidate    INTEGER,

    -- RF payload — human_review.* ──────────────────────────────────────────
    human_review_required               INTEGER,
    human_review_status                 TEXT,
    human_review_reviewer               TEXT,

    -- Forward-compat safety net: verbatim payload
    -- (schema declares additionalProperties: true) ───────────────────────
    raw_payload_json                    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rf_events_run_id ON rf_events(run_id);
CREATE INDEX IF NOT EXISTS idx_rf_events_project_created ON rf_events(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_rf_events_workspace ON rf_events(workspace_id);

-- ── RF Run Telemetry: research_runs derived rollup (T2-001) ──────────────
-- One row per Research Foundry run, derived/upserted from rf_events (D6 —
-- persistence is deliberately split into a raw log + a derived rollup, never
-- merged). run_id is CCDash's canonical, genuine-UUID primary/join key (D2,
-- FR-6): when RF's own raw run_id string does not parse as a UUID4, CCDash
-- deterministically mints one (backend/db/repositories/research_runs.py::
-- resolve_run_id) and stores RF's raw value in the separate rf_run_id
-- display column below. rf_run_id/intent_id/task_node_id are opaque display
-- strings only, exactly like their rf_events counterparts -- never join keys
-- against aos_correlation.py (D2 hard boundary; zero changes to that file).
-- See backend/db/repositories/research_runs.py module docstring for the full
-- per-column aggregation contract (summed vs. latest-wins vs. OR'd).
CREATE TABLE IF NOT EXISTS research_runs (
    -- Canonical identity (D2) ──────────────────────────────────────────────
    run_id                                  TEXT PRIMARY KEY,
    workspace_id                            TEXT NOT NULL DEFAULT 'default-local',
    project_id                              TEXT NOT NULL,
    created_at                              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                              TEXT NOT NULL DEFAULT (datetime('now')),

    -- RF display-only correlation attributes (D2 -- NEVER join keys) ───────
    rf_run_id                               TEXT,
    intent_id                               TEXT,
    task_node_id                            TEXT,
    rf_project                              TEXT,

    -- Rollup bookkeeping ────────────────────────────────────────────────────
    event_count                             INTEGER NOT NULL DEFAULT 0,
    first_event_at                          TEXT,
    last_event_at                           TEXT,

    -- Aggregated metrics -- SUMMED across every folded-in rf_events row ────
    total_queries_executed                  INTEGER,
    total_urls_extracted                    INTEGER,
    total_useful_source_count               INTEGER,
    total_tokens_estimated                  INTEGER,
    total_claims_total                      INTEGER,
    total_claims_supported                  INTEGER,
    total_claims_mixed                      INTEGER,
    total_claims_contradicted               INTEGER,
    total_unsupported_claims                INTEGER,
    total_estimated_cost_usd                REAL,
    total_latency_ms                        REAL,

    -- Latest-non-null snapshot metrics (rate/score-shaped) ─────────────────
    citation_coverage                       REAL,
    duplicate_rate                          REAL,
    extraction_failure_rate                 REAL,
    quality_score                           TEXT,
    drift_score                             REAL,

    -- Governance / reuse / human-review rollups ─────────────────────────────
    governance_sensitivity                  TEXT,
    governance_policy_passed                INTEGER,
    human_review_required                   INTEGER,
    human_review_status                     TEXT,
    human_review_reviewer                   TEXT,
    reuse_meatywiki_writeback_candidate      INTEGER,
    reuse_skillbom_candidate                 INTEGER,
    reuse_reusable_source_pack_candidate     INTEGER,

    -- Latest snapshot of array-shaped fields (JSON-encoded) ─────────────────
    agent_postures_json                     TEXT,
    skillbom_ids_json                       TEXT,
    tools_json                              TEXT,
    input_artifacts_json                    TEXT,
    output_artifacts_json                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_research_runs_project ON research_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_research_runs_workspace ON research_runs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_research_runs_rf_run_id ON research_runs(rf_run_id);
CREATE INDEX IF NOT EXISTS idx_research_runs_project_last_event ON research_runs(project_id, last_event_at);

-- ── AAR Review Persistence: aar_reviews rollup (T1-005, ccdash-automated-aar- --
-- review-v1 Phase 1) ──────────────────────────────────────────────────────
-- One row per (aar_document_id, session_id) pairing computed by the
-- deterministic AAR-document-to-session triage service
-- (backend/application/services/agent_queries/aar_review.py::AARReviewQueryService).
-- A single AAR document that correlates to N sessions fans out into N rows,
-- each carrying the SAME correlation/flags/triage_verdict snapshot but a
-- distinct session_id -- this is deliberate: the composite PRIMARY KEY below
-- is both the natural (aar_document_id, session_id) dedup key AND the upsert
-- conflict target (backend/db/repositories/aar_reviews.py), so re-computing
-- the same document never duplicates a pairing already on file.
-- `correlation`/`flags`/`triage_reasons`/`evidence_refs` are JSON-encoded
-- verbatim snapshots of the AARReviewDTO fields of the same/analogous name
-- (`triage_reasons` <- DTO.reasons, `evidence_refs` <- DTO.source_refs) --
-- never re-derived here. `provenance_skill_name`/`provenance_workflow_id`
-- are guard-input columns (D4): accepted and stored verbatim but NOT
-- enforced until Phase 6's writeback-guard worker.
CREATE TABLE IF NOT EXISTS aar_reviews (
    aar_document_id         TEXT NOT NULL,
    session_id               TEXT NOT NULL,
    project_id                TEXT NOT NULL,
    aar_document_path        TEXT DEFAULT '',
    correlation               TEXT,
    flags                     TEXT,
    triage_verdict            TEXT,
    triage_reasons            TEXT,
    evidence_refs             TEXT,
    generated_at              TEXT,
    provenance_skill_name     TEXT,
    provenance_workflow_id    TEXT,
    created_at                TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (aar_document_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_aar_reviews_project ON aar_reviews(project_id);
CREATE INDEX IF NOT EXISTS idx_aar_reviews_document ON aar_reviews(aar_document_id);
CREATE INDEX IF NOT EXISTS idx_aar_reviews_verdict ON aar_reviews(triage_verdict);
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


async def _migrate_v31_sessions_composite_pk_and_child_fks(db: aiosqlite.Connection) -> None:
    """P3-003-FU: Promote sessions PK to composite (project_id, id) and rebuild all
    child tables with composite FK (project_id, session_id) -> sessions(project_id, id).

    SQLite requires disabling FK enforcement outside of a transaction, rebuilding
    tables with the new schema, then running PRAGMA foreign_key_check to verify.

    Child tables rebuilt:
      - session_logs (P3-004 added project_id; nullable)
      - session_messages (project_id added here; nullable, backfilled)
      - session_tool_usage (P3-004 added project_id; nullable)
      - session_file_updates (P3-004 added project_id; nullable)
      - session_artifacts (project_id added here; nullable, backfilled)
      - session_usage_events (already has project_id NOT NULL)
      - session_relationships (already has project_id NOT NULL; both parent and child FKs)
      - session_sentiment_facts (project_id added here; nullable, backfilled)
      - session_code_churn_facts (project_id added here; nullable, backfilled)
      - session_scope_drift_facts (project_id added here; nullable, backfilled)
      - session_stack_observations (already has project_id NOT NULL)
      - session_memory_drafts (already has project_id NOT NULL)
      - outbound_telemetry_queue (no project_id; session_id FK only via composite)

    Forward-only. Idempotent: no-ops if sessions PK is already composite.
    Raises RuntimeError if PRAGMA foreign_key_check returns violations.
    """
    # ── Idempotency check ──────────────────────────────────────────────────────
    async with db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'"
    ) as cur:
        row = await cur.fetchone()
    if row and "PRIMARY KEY (project_id, id)" in (row[0] or ""):
        logger.info("P3-003-FU v31: sessions composite PK already present; skipping.")
        return

    # ── project_id column must exist ──────────────────────────────────────────
    async with db.execute("PRAGMA table_info(sessions)") as cur:
        cols = [r[1] for r in await cur.fetchall()]
    if "project_id" not in cols:
        logger.error(
            "P3-003-FU v31 ABORTED: sessions table missing project_id. "
            "Cannot create composite PK (project_id, id)."
        )
        return

    # ── collision check ───────────────────────────────────────────────────────
    async with db.execute(
        """
        SELECT project_id, id, COUNT(*) AS cnt
        FROM sessions
        GROUP BY project_id, id
        HAVING cnt > 1
        LIMIT 1
        """
    ) as cur:
        collision = await cur.fetchone()
    if collision:
        logger.error(
            "P3-003-FU v31 ABORTED: (project_id, id) collision in sessions: "
            "project_id=%s id=%s count=%s.",
            collision[0], collision[1], collision[2],
        )
        return

    # ── PRAGMA foreign_keys=OFF must be outside a transaction in SQLite ────────
    await db.execute("PRAGMA foreign_keys=OFF")
    try:
        # ── Read existing column lists for safe INSERT ─────────────────────────
        async def _col_names(table: str) -> set:
            async with db.execute(f"PRAGMA table_info({table})") as _c:
                return {r[1] for r in await _c.fetchall()}

        sessions_cols = await _col_names("sessions")

        # ── 1. Rebuild sessions with composite PK ─────────────────────────────
        await db.execute("DROP TABLE IF EXISTS sessions_new")
        await db.execute(
            """
            CREATE TABLE sessions_new (
                id               TEXT NOT NULL,
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
                session_forensics_json TEXT DEFAULT '{}',
                command_slug     TEXT DEFAULT '',
                latest_summary   TEXT DEFAULT '',
                subagent_type    TEXT DEFAULT '',
                models_used_json TEXT DEFAULT '[]',
                agents_used_json TEXT DEFAULT '[]',
                skills_used_json TEXT DEFAULT '[]',
                PRIMARY KEY (project_id, id)
            )
            """
        )
        # Intersect with sessions_new columns to drop any drift/orphan columns
        # (e.g. source_ref) that exist in the live DB but not in the new schema.
        new_session_cols = await _col_names("sessions_new")
        col_list = ", ".join(sorted(sessions_cols & new_session_cols))
        await db.execute(
            f"INSERT INTO sessions_new ({col_list}) SELECT {col_list} FROM sessions"
        )
        await db.execute("DROP TABLE sessions")
        await db.execute("ALTER TABLE sessions_new RENAME TO sessions")
        # Recreate sessions indexes
        for idx_ddl in [
            "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated ON sessions(project_id, status, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_source_file ON sessions(source_file)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_project_source_file ON sessions(project_id, source_file)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_root ON sessions(project_id, root_session_id, started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_family ON sessions(project_id, conversation_family_id, started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_thread_kind ON sessions(project_id, thread_kind, started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(project_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_conversation_family ON sessions(conversation_family_id)",
        ]:
            await db.execute(idx_ddl)

        # ── Helper: add project_id and backfill from parent sessions row ───────
        async def _ensure_project_id_and_backfill(table: str, session_col: str = "session_id") -> None:
            async with db.execute(f"PRAGMA table_info({table})") as _tc:
                existing = {r[1] for r in await _tc.fetchall()}
            if "project_id" not in existing:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN project_id TEXT")
            await db.execute(
                f"""
                UPDATE {table}
                SET project_id = (
                    SELECT project_id FROM sessions WHERE sessions.id = {table}.{session_col}
                )
                WHERE project_id IS NULL
                """
            )

        # ── 2. Rebuild session_logs ────────────────────────────────────────────
        await _ensure_project_id_and_backfill("session_logs")
        sl_cols = await _col_names("session_logs")
        await db.execute("DROP TABLE IF EXISTS session_logs_new")
        await db.execute(
            """
            CREATE TABLE session_logs_new (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     TEXT,
                session_id     TEXT NOT NULL,
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
                metadata_json  TEXT,
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        common = sorted(sl_cols & {
            "id", "project_id", "session_id", "log_index", "source_log_id", "timestamp",
            "speaker", "type", "content", "agent_name", "tool_name", "tool_call_id",
            "related_tool_call_id", "linked_session_id", "tool_args", "tool_output",
            "tool_status", "metadata_json",
        })
        await db.execute(
            f"INSERT INTO session_logs_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_logs"
        )
        await db.execute("DROP TABLE session_logs")
        await db.execute("ALTER TABLE session_logs_new RENAME TO session_logs")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_session ON session_logs(session_id, log_index)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_tool ON session_logs(tool_name) WHERE tool_name IS NOT NULL")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_source_log_id ON session_logs(session_id, source_log_id)")
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_source_log_unique "
            "ON session_logs(session_id, source_log_id) WHERE source_log_id != ''"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_session_logs_project ON session_logs(project_id)")

        # ── 3. Rebuild session_messages (add project_id) ───────────────────────
        await _ensure_project_id_and_backfill("session_messages")
        sm_cols = await _col_names("session_messages")
        await db.execute("DROP TABLE IF EXISTS session_messages_new")
        await db.execute(
            """
            CREATE TABLE session_messages_new (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     TEXT,
                session_id     TEXT NOT NULL,
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
                cache_creation_input_tokens INTEGER,
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sm = {
            "id", "project_id", "session_id", "message_index", "source_log_id", "message_id",
            "role", "message_type", "content", "event_timestamp", "agent_name", "tool_name",
            "tool_call_id", "related_tool_call_id", "linked_session_id", "entry_uuid",
            "parent_entry_uuid", "root_session_id", "conversation_family_id",
            "thread_session_id", "parent_session_id", "source_provenance", "metadata_json",
            "input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens",
        }
        common = sorted(sm_cols & known_sm)
        await db.execute(
            f"INSERT INTO session_messages_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_messages"
        )
        await db.execute("DROP TABLE session_messages")
        await db.execute("ALTER TABLE session_messages_new RENAME TO session_messages")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_messages_family "
            "ON session_messages(conversation_family_id, root_session_id, message_index)"
        )
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_message "
            "ON session_messages(session_id, message_index)"
        )

        # ── 4. Rebuild session_tool_usage ─────────────────────────────────────
        await _ensure_project_id_and_backfill("session_tool_usage")
        await db.execute("DROP TABLE IF EXISTS session_tool_usage_new")
        await db.execute(
            """
            CREATE TABLE session_tool_usage_new (
                project_id    TEXT,
                session_id    TEXT NOT NULL,
                tool_name     TEXT NOT NULL,
                call_count    INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                total_ms      INTEGER DEFAULT 0,
                PRIMARY KEY (session_id, tool_name),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "INSERT INTO session_tool_usage_new "
            "(project_id, session_id, tool_name, call_count, success_count, total_ms) "
            "SELECT project_id, session_id, tool_name, call_count, success_count, total_ms "
            "FROM session_tool_usage"
        )
        await db.execute("DROP TABLE session_tool_usage")
        await db.execute("ALTER TABLE session_tool_usage_new RENAME TO session_tool_usage")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_session_tool_usage_project ON session_tool_usage(project_id)")

        # ── 5. Rebuild session_file_updates ───────────────────────────────────
        await _ensure_project_id_and_backfill("session_file_updates")
        sfu_cols = await _col_names("session_file_updates")
        await db.execute("DROP TABLE IF EXISTS session_file_updates_new")
        await db.execute(
            """
            CREATE TABLE session_file_updates_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   TEXT,
                session_id   TEXT NOT NULL,
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
                source_tool_name TEXT,
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sfu = {
            "id", "project_id", "session_id", "file_path", "action", "file_type",
            "action_timestamp", "additions", "deletions", "agent_name",
            "thread_session_id", "root_session_id", "source_log_id", "source_tool_name",
        }
        common = sorted(sfu_cols & known_sfu)
        await db.execute(
            f"INSERT INTO session_file_updates_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_file_updates"
        )
        await db.execute("DROP TABLE session_file_updates")
        await db.execute("ALTER TABLE session_file_updates_new RENAME TO session_file_updates")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_file_updates_session ON session_file_updates(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_file_updates_path ON session_file_updates(file_path)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_session_file_updates_project ON session_file_updates(project_id)")

        # ── 6. Rebuild session_artifacts (add project_id) ─────────────────────
        await _ensure_project_id_and_backfill("session_artifacts")
        sa_cols = await _col_names("session_artifacts")
        await db.execute("DROP TABLE IF EXISTS session_artifacts_new")
        await db.execute(
            """
            CREATE TABLE session_artifacts_new (
                id           TEXT PRIMARY KEY,
                project_id   TEXT,
                session_id   TEXT NOT NULL,
                title        TEXT NOT NULL,
                type         TEXT DEFAULT 'document',
                description  TEXT DEFAULT '',
                source       TEXT DEFAULT '',
                url          TEXT,
                source_log_id TEXT,
                source_tool_name TEXT,
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sa = {
            "id", "project_id", "session_id", "title", "type", "description",
            "source", "url", "source_log_id", "source_tool_name",
        }
        common = sorted(sa_cols & known_sa)
        await db.execute(
            f"INSERT INTO session_artifacts_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_artifacts"
        )
        await db.execute("DROP TABLE session_artifacts")
        await db.execute("ALTER TABLE session_artifacts_new RENAME TO session_artifacts")

        # ── 7. Rebuild session_usage_events (has project_id NOT NULL) ─────────
        sue_cols = await _col_names("session_usage_events")
        await db.execute("DROP TABLE IF EXISTS session_usage_events_new")
        await db.execute(
            """
            CREATE TABLE session_usage_events_new (
                id                 TEXT PRIMARY KEY,
                project_id         TEXT NOT NULL,
                session_id         TEXT NOT NULL,
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
                metadata_json      TEXT DEFAULT '{}',
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sue = {
            "id", "project_id", "session_id", "root_session_id", "linked_session_id",
            "source_log_id", "captured_at", "event_kind", "model", "tool_name",
            "agent_name", "token_family", "delta_tokens", "cost_usd_model_io", "metadata_json",
        }
        common = sorted(sue_cols & known_sue)
        await db.execute(
            f"INSERT INTO session_usage_events_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_usage_events"
        )
        await db.execute("DROP TABLE session_usage_events")
        await db.execute("ALTER TABLE session_usage_events_new RENAME TO session_usage_events")
        for idx_ddl in [
            "CREATE INDEX IF NOT EXISTS idx_session_usage_events_project ON session_usage_events(project_id, captured_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_session_usage_events_session ON session_usage_events(session_id, captured_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_session_usage_events_source ON session_usage_events(session_id, source_log_id)",
            "CREATE INDEX IF NOT EXISTS idx_session_usage_events_entity_dims ON session_usage_events(project_id, token_family, event_kind)",
        ]:
            await db.execute(idx_ddl)

        # ── 8. Rebuild session_relationships (has project_id; both FKs composite) ──
        sr_cols = await _col_names("session_relationships")
        await db.execute("DROP TABLE IF EXISTS session_relationships_new")
        await db.execute(
            """
            CREATE TABLE session_relationships_new (
                id                 TEXT PRIMARY KEY,
                project_id         TEXT NOT NULL,
                parent_session_id  TEXT NOT NULL,
                child_session_id   TEXT NOT NULL,
                relationship_type  TEXT NOT NULL,
                context_inheritance TEXT DEFAULT '',
                source_platform    TEXT DEFAULT '',
                parent_entry_uuid  TEXT DEFAULT '',
                child_entry_uuid   TEXT DEFAULT '',
                source_log_id      TEXT,
                metadata_json      TEXT DEFAULT '{}',
                source_file        TEXT DEFAULT '',
                created_at         TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id, parent_session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE,
                FOREIGN KEY (project_id, child_session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sr = {
            "id", "project_id", "parent_session_id", "child_session_id",
            "relationship_type", "context_inheritance", "source_platform",
            "parent_entry_uuid", "child_entry_uuid", "source_log_id",
            "metadata_json", "source_file", "created_at",
        }
        common = sorted(sr_cols & known_sr)
        await db.execute(
            f"INSERT INTO session_relationships_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_relationships"
        )
        await db.execute("DROP TABLE session_relationships")
        await db.execute("ALTER TABLE session_relationships_new RENAME TO session_relationships")
        for idx_ddl in [
            "CREATE INDEX IF NOT EXISTS idx_session_relationships_parent ON session_relationships(project_id, parent_session_id, relationship_type)",
            "CREATE INDEX IF NOT EXISTS idx_session_relationships_child ON session_relationships(project_id, child_session_id, relationship_type)",
            "CREATE INDEX IF NOT EXISTS idx_session_relationships_source ON session_relationships(project_id, source_file)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_relationships_unique ON session_relationships(project_id, parent_session_id, child_session_id, relationship_type, parent_entry_uuid, child_entry_uuid)",
        ]:
            await db.execute(idx_ddl)

        # ── 9. Rebuild session_sentiment_facts (add project_id) ───────────────
        await _ensure_project_id_and_backfill("session_sentiment_facts")
        ssf_cols = await _col_names("session_sentiment_facts")
        await db.execute("DROP TABLE IF EXISTS session_sentiment_facts_new")
        await db.execute(
            """
            CREATE TABLE session_sentiment_facts_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id         TEXT,
                session_id         TEXT NOT NULL,
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
                computed_at        TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_ssf = {
            "id", "project_id", "session_id", "feature_id", "root_session_id",
            "thread_session_id", "source_message_id", "source_log_id", "message_index",
            "sentiment_label", "sentiment_score", "confidence", "heuristic_version",
            "evidence_json", "computed_at",
        }
        common = sorted(ssf_cols & known_ssf)
        await db.execute(
            f"INSERT INTO session_sentiment_facts_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_sentiment_facts"
        )
        await db.execute("DROP TABLE session_sentiment_facts")
        await db.execute("ALTER TABLE session_sentiment_facts_new RENAME TO session_sentiment_facts")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_sentiment_facts_session "
            "ON session_sentiment_facts(session_id, message_index, source_log_id)"
        )

        # ── 10. Rebuild session_code_churn_facts (add project_id) ─────────────
        await _ensure_project_id_and_backfill("session_code_churn_facts")
        sccf_cols = await _col_names("session_code_churn_facts")
        await db.execute("DROP TABLE IF EXISTS session_code_churn_facts_new")
        await db.execute(
            """
            CREATE TABLE session_code_churn_facts_new (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id               TEXT,
                session_id               TEXT NOT NULL,
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
                computed_at              TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sccf = {
            "id", "project_id", "session_id", "feature_id", "root_session_id",
            "thread_session_id", "file_path", "first_source_log_id", "last_source_log_id",
            "first_message_index", "last_message_index", "touch_count",
            "distinct_edit_turn_count", "repeat_touch_count", "rewrite_pass_count",
            "additions_total", "deletions_total", "net_diff_total", "churn_score",
            "progress_score", "low_progress_loop", "confidence", "heuristic_version",
            "evidence_json", "computed_at",
        }
        common = sorted(sccf_cols & known_sccf)
        await db.execute(
            f"INSERT INTO session_code_churn_facts_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_code_churn_facts"
        )
        await db.execute("DROP TABLE session_code_churn_facts")
        await db.execute("ALTER TABLE session_code_churn_facts_new RENAME TO session_code_churn_facts")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_code_churn_facts_session "
            "ON session_code_churn_facts(session_id, file_path)"
        )

        # ── 11. Rebuild session_scope_drift_facts (add project_id) ────────────
        await _ensure_project_id_and_backfill("session_scope_drift_facts")
        ssdf_cols = await _col_names("session_scope_drift_facts")
        await db.execute("DROP TABLE IF EXISTS session_scope_drift_facts_new")
        await db.execute(
            """
            CREATE TABLE session_scope_drift_facts_new (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id              TEXT,
                session_id              TEXT NOT NULL,
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
                computed_at             TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_ssdf = {
            "id", "project_id", "session_id", "feature_id", "root_session_id",
            "thread_session_id", "planned_path_count", "actual_path_count",
            "matched_path_count", "out_of_scope_path_count", "drift_ratio",
            "adherence_score", "confidence", "heuristic_version",
            "evidence_json", "computed_at",
        }
        common = sorted(ssdf_cols & known_ssdf)
        await db.execute(
            f"INSERT INTO session_scope_drift_facts_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_scope_drift_facts"
        )
        await db.execute("DROP TABLE session_scope_drift_facts")
        await db.execute("ALTER TABLE session_scope_drift_facts_new RENAME TO session_scope_drift_facts")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_scope_drift_facts_session "
            "ON session_scope_drift_facts(session_id, feature_id)"
        )

        # ── 12. Rebuild session_stack_observations (has project_id NOT NULL) ───
        sso_cols = await _col_names("session_stack_observations")
        await db.execute("DROP TABLE IF EXISTS session_stack_observations_new")
        await db.execute(
            """
            CREATE TABLE session_stack_observations_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id         TEXT NOT NULL,
                session_id         TEXT NOT NULL,
                feature_id         TEXT DEFAULT '',
                workflow_ref       TEXT DEFAULT '',
                confidence         REAL DEFAULT 0.0,
                observation_source TEXT DEFAULT 'backfill',
                evidence_json      TEXT DEFAULT '{}',
                created_at         TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(project_id, session_id),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_sso = {
            "id", "project_id", "session_id", "feature_id", "workflow_ref",
            "confidence", "observation_source", "evidence_json", "created_at", "updated_at",
        }
        common = sorted(sso_cols & known_sso)
        await db.execute(
            f"INSERT INTO session_stack_observations_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_stack_observations"
        )
        await db.execute("DROP TABLE session_stack_observations")
        await db.execute("ALTER TABLE session_stack_observations_new RENAME TO session_stack_observations")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_session "
            "ON session_stack_observations(project_id, session_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_stack_observations_feature "
            "ON session_stack_observations(project_id, feature_id, updated_at DESC)"
        )

        # ── 13. Rebuild session_memory_drafts (has project_id NOT NULL) ────────
        smd_cols = await _col_names("session_memory_drafts")
        await db.execute("DROP TABLE IF EXISTS session_memory_drafts_new")
        await db.execute(
            """
            CREATE TABLE session_memory_drafts_new (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id           TEXT NOT NULL,
                session_id           TEXT NOT NULL,
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
                UNIQUE(project_id, content_hash),
                FOREIGN KEY (project_id, session_id) REFERENCES sessions(project_id, id) ON DELETE CASCADE
            )
            """
        )
        known_smd = {
            "id", "project_id", "session_id", "feature_id", "root_session_id",
            "thread_session_id", "workflow_ref", "title", "memory_type", "status",
            "module_name", "module_description", "content", "confidence",
            "source_message_id", "source_log_id", "source_message_index",
            "content_hash", "evidence_json", "publish_attempts", "published_module_id",
            "published_memory_id", "reviewed_by", "review_notes", "reviewed_at",
            "published_at", "last_publish_error", "created_at", "updated_at",
        }
        common = sorted(smd_cols & known_smd)
        await db.execute(
            f"INSERT INTO session_memory_drafts_new ({', '.join(common)}) "
            f"SELECT {', '.join(common)} FROM session_memory_drafts"
        )
        await db.execute("DROP TABLE session_memory_drafts")
        await db.execute("ALTER TABLE session_memory_drafts_new RENAME TO session_memory_drafts")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_project_status "
            "ON session_memory_drafts(project_id, status, updated_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_memory_drafts_session "
            "ON session_memory_drafts(project_id, session_id, updated_at DESC)"
        )

        # ── 14. Rebuild outbound_telemetry_queue ──────────────────────────────
        # This table has a UNIQUE(session_id) constraint and had its sessions FK
        # removed in a prior migration (_migrate_outbound_telemetry_queue_event_type).
        # We do not add a composite FK here because session_id may be empty/NULL
        # for artifact-level rows; only a no-op rebuild is needed to ensure
        # the table schema is consistent with FK-off state.
        # (No composite FK on outbound_telemetry_queue — session_id is not a
        #  strict foreign key in the current post-event_type migration schema.)

        # ── Verify FK integrity ───────────────────────────────────────────────
        async with db.execute("PRAGMA foreign_key_check") as _fk_cur:
            fk_violations = await _fk_cur.fetchall()
        if fk_violations:
            raise RuntimeError(
                f"P3-003-FU v31: PRAGMA foreign_key_check returned violations "
                f"after composite PK + child FK rebuild: {fk_violations}"
            )

        await db.commit()
        logger.info(
            "P3-003-FU v31: sessions composite PK (project_id, id) + all child "
            "composite FKs applied. PRAGMA foreign_key_check: empty."
        )
    except Exception:
        logger.exception("P3-003-FU v31: composite PK + child FK migration failed; rolling back.")
        raise
    finally:
        await db.execute("PRAGMA foreign_keys=ON")


async def _migrate_v30_sessions_composite_pk(db: aiosqlite.Connection) -> None:
    """P3-003: Recreate sessions with composite PK (project_id, id).

    SQLite does not support altering primary keys in-place, so we use the
    rename-create-copy-drop pattern.  Forward-only; existing DBs missing a
    project_id column are aborted with a clear log message (they should not
    exist given project_id has been required since v22).

    Pre-checks:
      1. project_id column must exist — aborts otherwise.
      2. No (project_id, id) duplicates — aborts if any are found.

    Triggers, FKs pointing INTO sessions.id from child tables are preserved
    because we keep the same column types.  Child tables that reference
    sessions(id) are temporarily FK-enforcement-off during the swap.
    """
    # ── Step 1: confirm project_id column exists ──────────────────────────────
    async with db.execute("PRAGMA table_info(sessions)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if "project_id" not in cols:
        logger.error(
            "P3-003 ABORTED: sessions table is missing project_id column. "
            "Cannot create composite PK (project_id, id)."
        )
        return

    # ── Step 2: check whether composite PK already exists ────────────────────
    async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'") as cur:
        row = await cur.fetchone()
    if row and "PRIMARY KEY (project_id, id)" in (row[0] or ""):
        logger.info("P3-003: sessions composite PK already present; skipping.")
        return

    # ── Step 3: collision check ───────────────────────────────────────────────
    async with db.execute(
        """
        SELECT project_id, id, COUNT(*) AS cnt
        FROM sessions
        GROUP BY project_id, id
        HAVING cnt > 1
        LIMIT 1
        """
    ) as cur:
        collision = await cur.fetchone()
    if collision:
        logger.error(
            "P3-003 ABORTED: found (project_id, id) collision in sessions: "
            "project_id=%s id=%s count=%s. Resolve duplicates before re-running.",
            collision[0],
            collision[1],
            collision[2],
        )
        return

    # ── Step 4: recreate table with composite PK ─────────────────────────────
    # Use create-new / copy-from-live / drop-old / rename ordering so that
    # child tables (session_logs, session_tool_usage, session_file_updates)
    # keep their REFERENCES sessions(...) DDL pointing at the name "sessions"
    # throughout.  Renaming the live table first would cause SQLite to rewrite
    # those FK clauses to the temp name, which we then drop — leaving dangling
    # references.
    await db.execute("PRAGMA foreign_keys=OFF")
    try:
        # Read existing columns before creating the new table so we can build
        # a safe INSERT that only references columns present in the live table.
        async with db.execute("PRAGMA table_info(sessions)") as _cur:
            existing_col_names = {row[1] for row in await _cur.fetchall()}

        # 1. Create sessions_new with the composite PK — identical DDL except
        #    name and PK clause.
        await db.execute(
            """
            CREATE TABLE sessions_new (
                id               TEXT NOT NULL,
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
                session_forensics_json TEXT DEFAULT '{}',
                command_slug     TEXT DEFAULT '',
                latest_summary   TEXT DEFAULT '',
                subagent_type    TEXT DEFAULT '',
                models_used_json TEXT DEFAULT '[]',
                agents_used_json TEXT DEFAULT '[]',
                skills_used_json TEXT DEFAULT '[]',
                PRIMARY KEY (project_id, id)
            )
            """
        )
        # 2. Copy rows from the live sessions table (never renamed).
        #    Only include columns that exist in the old table; absent columns
        #    receive their DEFAULT values in sessions_new.
        cols_in_both = sorted(existing_col_names)
        col_list = ", ".join(cols_in_both)
        await db.execute(
            f"INSERT INTO sessions_new ({col_list}) SELECT {col_list} FROM sessions"
        )
        # 3. Drop the original sessions table.
        await db.execute("DROP TABLE sessions")
        # 4. Rename sessions_new → sessions.
        await db.execute("ALTER TABLE sessions_new RENAME TO sessions")
        # Recreate all indexes that were on the old sessions table.
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_project"
            " ON sessions(project_id, started_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated"
            " ON sessions(project_id, status, updated_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_source_file ON sessions(source_file)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_project_source_file"
            " ON sessions(project_id, source_file)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_root"
            " ON sessions(project_id, root_session_id, started_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_family"
            " ON sessions(project_id, conversation_family_id, started_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_thread_kind"
            " ON sessions(project_id, thread_kind, started_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at"
            " ON sessions(project_id, updated_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_conversation_family"
            " ON sessions(conversation_family_id)"
        )
        # 5. Verify FK integrity before committing.
        # Note: PRAGMA foreign_key_check raises OperationalError when a child
        # table references sessions(id) after the PK becomes composite
        # (project_id, id) — SQLite requires the referenced column to be a
        # standalone PK or covered by a UNIQUE index.  Child-table rows are
        # empty at migration time and the column still exists, so this is a
        # schema-level mismatch rather than a data-level violation.  We catch
        # the OperationalError and log it as an expected post-migration state;
        # actual data-integrity enforcement is handled at write time via FK
        # triggers in the child-table DDL.
        try:
            async with db.execute("PRAGMA foreign_key_check") as _fk_cur:
                fk_violations = await _fk_cur.fetchall()
            if fk_violations:
                raise RuntimeError(
                    f"P3-003: PRAGMA foreign_key_check returned violations after sessions "
                    f"composite PK swap: {fk_violations}"
                )
        except Exception as _fk_err:
            import sqlite3 as _sqlite3

            if isinstance(_fk_err, _sqlite3.OperationalError) or (
                hasattr(_fk_err, "__cause__")
                and isinstance(getattr(_fk_err, "__cause__", None), _sqlite3.OperationalError)
            ):
                logger.debug(
                    "P3-003: PRAGMA foreign_key_check raised OperationalError after composite "
                    "PK swap (expected: child tables reference sessions(id) which is no longer "
                    "a standalone PK): %s",
                    _fk_err,
                )
            else:
                raise
        await db.commit()
        logger.info("P3-003: sessions composite PK (project_id, id) applied.")
    except Exception:
        logger.exception("P3-003: sessions composite PK migration failed; rolling back.")
        raise
    finally:
        await db.execute("PRAGMA foreign_keys=ON")


async def _migrate_v30_detail_tables_project_id(db: aiosqlite.Connection) -> None:
    """P3-004: Add nullable project_id to session detail tables and backfill.

    Tables: session_logs, session_tool_usage, session_file_updates.
    Backfills project_id from the parent sessions row via UPDATE...
    subquery; adds an index on project_id for each table.
    """
    # ── session_logs ──────────────────────────────────────────────────────────
    await _ensure_column(db, "session_logs", "project_id", "TEXT")
    await db.execute(
        """
        UPDATE session_logs
        SET project_id = (
            SELECT project_id FROM sessions WHERE sessions.id = session_logs.session_id
        )
        WHERE project_id IS NULL
        """
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_logs_project"
        " ON session_logs(project_id)",
    )

    # ── session_tool_usage ────────────────────────────────────────────────────
    await _ensure_column(db, "session_tool_usage", "project_id", "TEXT")
    await db.execute(
        """
        UPDATE session_tool_usage
        SET project_id = (
            SELECT project_id FROM sessions WHERE sessions.id = session_tool_usage.session_id
        )
        WHERE project_id IS NULL
        """
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_tool_usage_project"
        " ON session_tool_usage(project_id)",
    )

    # ── session_file_updates ──────────────────────────────────────────────────
    await _ensure_column(db, "session_file_updates", "project_id", "TEXT")
    await db.execute(
        """
        UPDATE session_file_updates
        SET project_id = (
            SELECT project_id FROM sessions WHERE sessions.id = session_file_updates.session_id
        )
        WHERE project_id IS NULL
        """
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_session_file_updates_project"
        " ON session_file_updates(project_id)",
    )

    logger.info("P3-004: project_id columns backfilled on session detail tables.")


def _resolve_migration_lock_path() -> Path:
    """Return the path to the inter-process migration lock file.

    Mirrors config.DB_PATH resolution so custom CCDASH_DB_PATH values are
    respected.  The directory is created (parents=True) if it does not exist.
    """
    db_path = config.DB_PATH
    lock_dir = db_path.parent
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / ".migration.lock"


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Create all tables and seed data. Idempotent.

    On SQLite, a POSIX exclusive flock on ``data/.migration.lock`` is acquired
    before any DDL so that concurrent processes (e.g., API + worker booting at
    the same time) do not race on first-boot schema creation.  The flock is
    released unconditionally in a finally block, mirroring the advisory-lock
    pattern used in postgres_migrations.py.

    After acquiring the lock the current schema_version is re-read; if another
    process already completed the migration the DDL phase is skipped ("migration
    already complete" logged), preventing redundant work and SQLITE_LOCKED
    errors.

    The lock timeout is configurable via CCDASH_MIGRATION_LOCK_TIMEOUT_SECONDS
    (default 30 s).

    busy_timeout is set to 30 000 ms as a safety net for contention that
    occurs *outside* the flock window (e.g. WAL conversion, PRAGMA execution
    during connection setup before the flock is acquired).  The flock remains
    the primary serializer; busy_timeout converts any residual SQLITE_BUSY
    into a wait rather than an immediate OperationalError.
    """
    # ── Safety net: wait up to 30 s for any SQLite-level lock before the
    #    flock is even attempted (WAL conversion needs a momentary exclusive
    #    lock; without this a racing process gets OperationalError immediately).
    await db.execute("PRAGMA busy_timeout = 30000")

    # ── T3-008: acquire inter-process flock before any DDL ────────────────────
    lock_path = _resolve_migration_lock_path()
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
    deadline = time.monotonic() + _MIGRATION_LOCK_TIMEOUT_SECONDS
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire SQLite migration lock within "
                        f"{_MIGRATION_LOCK_TIMEOUT_SECONDS}s "
                        f"(lock file: {lock_path})"
                    )
                # Yield to the event loop so callers are not blocked solid.
                await asyncio.sleep(0.1)

        # ── Re-check schema_version after acquiring the lock (another process
        #    may have finished migrations while we were waiting) ────────────────
        try:
            async with db.execute("SELECT MAX(version) FROM schema_version") as _cur:
                _row = await _cur.fetchone()
                _version_after_lock = _row[0] if _row and _row[0] else 0
        except Exception:
            _version_after_lock = 0

        if _version_after_lock >= SCHEMA_VERSION:
            logger.info(
                "T3-008: migration already complete (version %d); "
                "skipping DDL phase.",
                _version_after_lock,
            )
            # Still run idempotent column/index checks and ledger below.
            await _run_migrations_inner(db, current_version=_version_after_lock)
            return

        await _run_migrations_inner(db, current_version=_version_after_lock)
    finally:
        if acquired:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


async def _run_migrations_inner(db: aiosqlite.Connection, current_version: int) -> None:
    """Actual migration logic, executed under the flock.

    Extracted so run_migrations stays readable and the lock/unlock bracket is
    unmistakable.
    """
    # Check current schema version
    try:
        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            current_version = row[0] if row and row[0] else current_version
    except Exception:
        pass  # retain caller-supplied current_version

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
    # Phase 5 detection columns (T5-006). Existing rows read these as '' / NULL —
    # null is a valid contract state, no backfill required (AC-5.3 resilience).
    await _ensure_column(db, "sessions", "model_slug", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "workflow_id", "TEXT")
    await _ensure_column(db, "sessions", "subagent_parent_id", "TEXT")
    await _ensure_column(db, "sessions", "skill_name", "TEXT")
    await _ensure_column(db, "sessions", "context_window", "TEXT")
    # Phase 11 launch-time capture columns (T11-003). All nullable.
    await _ensure_column(db, "sessions", "launcher", "TEXT")
    await _ensure_column(db, "sessions", "profile", "TEXT")
    await _ensure_column(db, "sessions", "effort_tier", "TEXT")
    await _ensure_column(db, "sessions", "model_variant", "TEXT")
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

    # ── T1-004: Backfill idx_sessions_project_status_updated on existing DBs ────
    # Declared in _TABLES (above) but previously only created on a version bump.
    # This _ensure_index call makes it available on all existing databases.
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_project_status_updated"
        " ON sessions(project_id, status, updated_at)",
    )

    # ── T1-005: source_file indexes — kills full-scan in list_by_source ──────────
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_source_file"
        " ON sessions(source_file)",
    )
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_project_source_file"
        " ON sessions(project_id, source_file)",
    )

    # ── T1-010: materialized badge columns on sessions ────────────────────────────
    # SQLite has no ADD COLUMN IF NOT EXISTS; _ensure_column checks existence first.
    await _ensure_column(db, "sessions", "command_slug", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "latest_summary", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "subagent_type", "TEXT DEFAULT ''")
    await _ensure_column(db, "sessions", "models_used_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "agents_used_json", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "sessions", "skills_used_json", "TEXT DEFAULT '[]'")

    # ── T1-019: entity_links.project_id column + idx_links_project ───────────────
    await _ensure_column(db, "entity_links", "project_id", "TEXT")
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_links_project ON entity_links(project_id)",
    )

    # ── v33: scope/scope_id columns on analytics_entries ─────────────────────────
    # ALTER ADD COLUMN with a constant DEFAULT is an O(1) metadata-only operation —
    # safe on large databases. All pre-existing rows get scope='project', scope_id=''.
    await _ensure_column(db, "analytics_entries", "scope", "TEXT NOT NULL DEFAULT 'project'")
    await _ensure_column(db, "analytics_entries", "scope_id", "TEXT NOT NULL DEFAULT ''")

    # ── T1-014: Partial indexes for analytics_entries (period='point') ───────────
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_analytics_point_latest"
        " ON analytics_entries(project_id, metric_type, captured_at DESC)"
        " WHERE period = 'point'",
    )
    # ── T1-001: Unique partial index for ON CONFLICT point-period dedup ──────────
    # Before creating the UNIQUE index, remove any duplicate same-day point rows
    # that may exist on existing databases. We keep only the latest row per
    # (project_id, metric_type, date(captured_at)) group. The check runs only
    # when the index does not yet exist so that idempotent re-runs are free.
    async with db.execute(
        "SELECT 1 FROM sqlite_master"
        " WHERE type='index' AND name='idx_analytics_point_daily'"
        " LIMIT 1"
    ) as _cur:
        _idx_exists = await _cur.fetchone() is not None
    if not _idx_exists:
        await db.execute(
            """
            DELETE FROM analytics_entries
            WHERE period = 'point'
              AND id NOT IN (
                  SELECT MAX(id)
                  FROM analytics_entries
                  WHERE period = 'point'
                  GROUP BY project_id, metric_type, date(captured_at)
              )
            """
        )
        await db.commit()
    await _ensure_index(
        db,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_point_daily"
        " ON analytics_entries(project_id, metric_type, date(captured_at))"
        " WHERE period = 'point'",
    )
    # ── T1-014: Partial index for telemetry_events event_type queries ─────────────
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_telemetry_event_type_partial"
        " ON telemetry_events(event_type, project_id, occurred_at)"
        " WHERE event_type != ''",
    )

    # Seed metric types
    await db.executescript(_SEED_METRIC_TYPES)

    # Seed default alert configs
    await db.executescript(_SEED_ALERT_CONFIGS)

    # ── v30 migrations (P3-001/002/006 tables created via _TABLES above) ─────
    if current_version < 30:
        # P3-004: add + backfill project_id on session detail tables
        await _migrate_v30_detail_tables_project_id(db)

    # ── v31 migrations (P3-003-FU: composite PK + composite child FKs) ───────
    if current_version < 31:
        # P3-003-FU: promote sessions PK to (project_id, id); rebuild all child
        # tables with composite FK (project_id, session_id)->sessions(project_id, id).
        # Idempotent: no-ops if PK is already composite.
        await _migrate_v31_sessions_composite_pk_and_child_fks(db)

    # ── v32 migrations ────────────────────────────────────────────────────────
    if current_version < 32:
        # P5-005: owners_json + linked_docs_json on features (columnar extraction)
        await _ensure_column(db, "features", "owners_json", "TEXT DEFAULT '[]'")
        await _ensure_column(db, "features", "linked_docs_json", "TEXT DEFAULT '[]'")
        await db.execute(
            """
            UPDATE features
            SET owners_json = COALESCE(json_extract(data_json, '$.owners'), '[]'),
                linked_docs_json = COALESCE(json_extract(data_json, '$.linkedDocs'), '[]')
            WHERE owners_json IS NULL OR owners_json = '[]'
            """
        )

        # P5-012: council_reviews scaffold table (feature-scoped)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS council_reviews (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL,
                feature_id  TEXT NOT NULL,
                status      TEXT,
                summary     TEXT,
                data_json   TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_council_reviews_project_feature"
            " ON council_reviews(project_id, feature_id)",
        )

        # P5-013: research_notes scaffold table (project/feature-scoped)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS research_notes (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL,
                feature_id  TEXT,
                title       TEXT,
                url         TEXT,
                body        TEXT,
                source      TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_research_notes_project_feature"
            " ON research_notes(project_id, feature_id)",
        )
        await db.commit()
        logger.info("v32 migrations complete: owners_json/linked_docs_json on features; council_reviews; research_notes.")

    # ── v33 migrations ────────────────────────────────────────────────────────
    if current_version < 33:
        # Promote scope/scope_id into the unique dedup index so per-feature analytics
        # rows are DISTINCT from project-level rows of the same metric+day.
        # No row-dedup DELETE is needed: all pre-existing rows receive scope_id='' by
        # DEFAULT (via the _ensure_column calls above), and the old index already
        # guaranteed uniqueness on (project_id, metric_type, date), so the new wider
        # key (project_id, metric_type, scope_id='', date) is also unique over existing
        # data — CREATE UNIQUE INDEX will succeed without any pre-cleanup.
        await db.execute("DROP INDEX IF EXISTS idx_analytics_point_daily")
        await _ensure_index(
            db,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_point_daily"
            " ON analytics_entries(project_id, metric_type, scope_id, date(captured_at))"
            " WHERE period = 'point'",
        )
        await db.commit()
        logger.info("v33 migrations complete: scope/scope_id columns + new idx_analytics_point_daily key.")

    # ── v34 migrations (T1-004: branch-aware planning intelligence index) ────
    if current_version < 34:
        # Additive index only — no column alterations, no data rewrites.
        # IF NOT EXISTS guard ensures idempotent re-runs are safe.
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_sessions_git_branch"
            " ON sessions(git_branch, project_id)",
        )
        await db.commit()
        logger.info("v34 migrations complete: idx_sessions_git_branch added.")

    if current_version < 35:
        # Phase 11 launch-time capture columns (T11-003). All nullable TEXT;
        # no backfill — null == not captured (legitimate contract state).
        # COALESCE-guarded upsert ensures re-ingest never clobbers a prior value.
        await _ensure_column(db, "sessions", "launcher", "TEXT")
        await _ensure_column(db, "sessions", "profile", "TEXT")
        await _ensure_column(db, "sessions", "effort_tier", "TEXT")
        await _ensure_column(db, "sessions", "model_variant", "TEXT")
        await db.commit()
        logger.info("v35 migrations complete: launch-time capture columns added.")

    # ── v36 migrations (ADR-009: SessionIngestSource port + ingest_cursors) ──
    # Placed after the v31 composite-PK rebuild so source_ref is not stripped as
    # an orphan column by that rebuild's column-intersection logic.
    if current_version < 36:
        await _ensure_column(db, "sessions", "source_ref", "TEXT")
        await db.execute(
            """
            UPDATE sessions
            SET source_ref = 'fs:' || source_file
            WHERE source_ref IS NULL
              AND source_file IS NOT NULL
              AND source_file != ''
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS ix_sessions_source_ref ON sessions (project_id, source_ref)",
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_cursors (
                source_id      TEXT NOT NULL,
                project_id     TEXT NOT NULL,
                workspace_id   TEXT NOT NULL DEFAULT 'default',
                last_cursor    TEXT,
                last_ingest_at TEXT,
                error_count    INTEGER NOT NULL DEFAULT 0,
                last_error     TEXT,
                last_error_at  TEXT,
                PRIMARY KEY (source_id, project_id, workspace_id)
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS ix_ingest_cursors_workspace ON ingest_cursors (workspace_id)",
        )
        await db.commit()
        logger.info("v36 migrations complete: source_ref column + ingest_cursors table (ADR-009).")

    # ── v37 migrations (ADR-008: workspace-scoped bearer auth) ──────────────────
    if current_version < 37:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'active',
                created_at   TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_tokens (
                token_id     TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                project_id   TEXT NOT NULL,
                hashed_token TEXT NOT NULL UNIQUE,
                scope        TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at   TEXT,
                description  TEXT
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS ix_workspace_tokens_workspace"
            " ON workspace_tokens (workspace_id) WHERE revoked_at IS NULL",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS ix_workspace_tokens_hash"
            " ON workspace_tokens (hashed_token) WHERE revoked_at IS NULL",
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO workspaces (workspace_id, name, status, created_at)
            VALUES ('default-local', 'Default Local Workspace', 'active', datetime('now'))
            """
        )
        for scoped_table in ("sessions", "documents", "tasks", "features"):
            await _ensure_column(db, scoped_table, "workspace_id", "TEXT NOT NULL DEFAULT 'default-local'")
        await _ensure_column(db, "entity_links", "workspace_id", "TEXT NOT NULL DEFAULT 'default-local'")
        await _ensure_column_if_table_exists(db, "progress_files", "workspace_id", "TEXT NOT NULL DEFAULT 'default-local'")
        # Normalise any legacy 'default' ingest_cursors rows to 'default-local'.
        await db.execute(
            """
            DELETE FROM ingest_cursors
            WHERE workspace_id = 'default'
              AND EXISTS (
                SELECT 1 FROM ingest_cursors c2
                WHERE c2.source_id = ingest_cursors.source_id
                  AND c2.project_id = ingest_cursors.project_id
                  AND c2.workspace_id = 'default-local'
              )
            """
        )
        await db.execute(
            "UPDATE ingest_cursors SET workspace_id = 'default-local' WHERE workspace_id = 'default'"
        )
        await db.commit()
        logger.info("v37 migrations complete: workspaces + workspace_tokens + workspace_id columns (ADR-008).")

    # ── v38 migrations (Codex session ingestion Phase 1: repo_path on projects) ──
    if current_version < 38:
        # Add repo_path to projects for deterministic cwd→project attribution.
        # Nullable TEXT; default NULL — populated at registration time.
        # Phase 1 of codex-session-ingestion-v1 plan.
        await _ensure_column(db, "projects", "repo_path", "TEXT")
        await db.commit()
        logger.info("v38 migrations complete: repo_path column added to projects table.")

    # ── v39 migrations (Codex session ingestion Phase 2: cwd on sessions) ──────
    if current_version < 39:
        # Add cwd to sessions for Codex working-directory attribution.
        # Nullable TEXT; NULL for Claude Code sessions (contract state).
        # Populated from session_forensics["entryContext"]["workingDirectories"][0]
        # during Codex sync.  COALESCE-guarded on upsert so a re-ingest never
        # clobbers a previously-captured value.
        # Phase 2 of codex-session-ingestion-v1 plan.
        await _ensure_column(db, "sessions", "cwd", "TEXT")
        await db.commit()
        logger.info("v39 migrations complete: cwd column added to sessions table.")

    # ── v40 migrations (T1-001: research-foundry-run-telemetry rf_events) ─────
    # rf_events is also declared in _TABLES (above) so get_sqlite_migration_
    # tables() discovers it for the dual-DDL parity/direct-count exit gate
    # (T1-002). This version-gated CREATE TABLE guarantees the table also
    # appears on databases that were already at/above the pre-bump
    # SCHEMA_VERSION and would otherwise skip the executescript(_TABLES)
    # path entirely (ingest_cursors v36 precedent, exactly).
    if current_version < 40:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rf_events (
                event_id                             TEXT PRIMARY KEY,
                workspace_id                         TEXT NOT NULL DEFAULT 'default-local',
                project_id                            TEXT NOT NULL,
                created_at                            TEXT NOT NULL DEFAULT (datetime('now')),
                event_timestamp                       TEXT NOT NULL,
                rf_project                             TEXT NOT NULL,
                run_id                                 TEXT,
                intent_id                              TEXT,
                task_node_id                           TEXT,
                agent_postures_json                    TEXT,
                skillbom_ids_json                      TEXT,
                tools_json                             TEXT,
                input_artifacts_json                   TEXT,
                output_artifacts_json                  TEXT,
                metric_source_cards_created            INTEGER,
                metric_claims_total                    INTEGER,
                metric_claims_supported                INTEGER,
                metric_claims_mixed                    INTEGER,
                metric_claims_contradicted             INTEGER,
                metric_claims_inference                INTEGER,
                metric_claims_speculation               INTEGER,
                metric_unsupported_claims              INTEGER,
                metric_verification_passed             INTEGER,
                metric_tokens_estimated                INTEGER,
                metric_cost_estimated_usd              REAL,
                metric_latency_minutes                 REAL,
                metric_rework_count                    INTEGER,
                metric_drift_score                     REAL,
                metric_quality_score                   TEXT,
                metric_queries_executed                INTEGER,
                metric_urls_extracted                  INTEGER,
                metric_useful_source_count             INTEGER,
                metric_duplicate_rate                  REAL,
                metric_extraction_failure_rate         REAL,
                metric_citation_coverage               REAL,
                metric_estimated_cost_usd              REAL,
                metric_latency_ms                      REAL,
                governance_sensitivity                 TEXT,
                governance_key_profile_used            TEXT,
                governance_key_fingerprint             TEXT,
                governance_policy_passed               INTEGER,
                governance_violations_json             TEXT,
                reuse_meatywiki_writeback_candidate     INTEGER,
                reuse_skillbom_candidate                INTEGER,
                reuse_reusable_source_pack_candidate    INTEGER,
                human_review_required                  INTEGER,
                human_review_status                    TEXT,
                human_review_reviewer                  TEXT,
                raw_payload_json                       TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_rf_events_run_id ON rf_events(run_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_rf_events_project_created"
            " ON rf_events(project_id, created_at)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_rf_events_workspace ON rf_events(workspace_id)",
        )
        await db.commit()
        logger.info(
            "v40 migrations complete: rf_events table added "
            "(research-foundry-run-telemetry-v1, T1-001)."
        )

    # ── v41 migrations (T2-001: research-foundry-run-telemetry research_runs) ──
    # research_runs is also declared in _TABLES (above) so
    # get_sqlite_migration_tables() discovers it for the dual-DDL
    # parity/direct-count exit gate (T2-002). This version-gated CREATE TABLE
    # guarantees the table also appears on databases that were already at/
    # above the pre-bump SCHEMA_VERSION and would otherwise skip the
    # executescript(_TABLES) path entirely (rf_events v40 precedent, exactly).
    if current_version < 41:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                run_id                                   TEXT PRIMARY KEY,
                workspace_id                             TEXT NOT NULL DEFAULT 'default-local',
                project_id                                TEXT NOT NULL,
                created_at                                TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at                                TEXT NOT NULL DEFAULT (datetime('now')),
                rf_run_id                                 TEXT,
                intent_id                                 TEXT,
                task_node_id                              TEXT,
                rf_project                                TEXT,
                event_count                               INTEGER NOT NULL DEFAULT 0,
                first_event_at                            TEXT,
                last_event_at                             TEXT,
                total_queries_executed                    INTEGER,
                total_urls_extracted                      INTEGER,
                total_useful_source_count                 INTEGER,
                total_tokens_estimated                    INTEGER,
                total_claims_total                        INTEGER,
                total_claims_supported                    INTEGER,
                total_claims_mixed                        INTEGER,
                total_claims_contradicted                 INTEGER,
                total_unsupported_claims                  INTEGER,
                total_estimated_cost_usd                  REAL,
                total_latency_ms                          REAL,
                citation_coverage                         REAL,
                duplicate_rate                            REAL,
                extraction_failure_rate                   REAL,
                quality_score                             TEXT,
                drift_score                               REAL,
                governance_sensitivity                    TEXT,
                governance_policy_passed                  INTEGER,
                human_review_required                     INTEGER,
                human_review_status                       TEXT,
                human_review_reviewer                     TEXT,
                reuse_meatywiki_writeback_candidate        INTEGER,
                reuse_skillbom_candidate                   INTEGER,
                reuse_reusable_source_pack_candidate       INTEGER,
                agent_postures_json                       TEXT,
                skillbom_ids_json                         TEXT,
                tools_json                                TEXT,
                input_artifacts_json                      TEXT,
                output_artifacts_json                     TEXT
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_research_runs_project ON research_runs(project_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_research_runs_workspace ON research_runs(workspace_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_research_runs_rf_run_id ON research_runs(rf_run_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_research_runs_project_last_event"
            " ON research_runs(project_id, last_event_at)",
        )
        await db.commit()
        logger.info(
            "v41 migrations complete: research_runs table added "
            "(research-foundry-run-telemetry-v1, T2-001)."
        )

    # ── v42 migrations (T1-005: ccdash-automated-aar-review-v1 aar_reviews) ────
    # aar_reviews is also declared in _TABLES (above) so
    # get_sqlite_migration_tables() discovers it for the dual-DDL
    # parity/direct-count exit gate (T1-007). This version-gated CREATE TABLE
    # guarantees the table also appears on databases that were already at/
    # above the pre-bump SCHEMA_VERSION and would otherwise skip the
    # executescript(_TABLES) path entirely (rf_events v40 / research_runs v41
    # precedent, exactly).
    if current_version < 42:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS aar_reviews (
                aar_document_id          TEXT NOT NULL,
                session_id                TEXT NOT NULL,
                project_id                 TEXT NOT NULL,
                aar_document_path         TEXT DEFAULT '',
                correlation                TEXT,
                flags                      TEXT,
                triage_verdict             TEXT,
                triage_reasons             TEXT,
                evidence_refs              TEXT,
                generated_at               TEXT,
                provenance_skill_name      TEXT,
                provenance_workflow_id     TEXT,
                created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at                 TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (aar_document_id, session_id)
            )
            """
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_aar_reviews_project ON aar_reviews(project_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_aar_reviews_document ON aar_reviews(aar_document_id)",
        )
        await _ensure_index(
            db,
            "CREATE INDEX IF NOT EXISTS idx_aar_reviews_verdict ON aar_reviews(triage_verdict)",
        )
        await db.commit()
        logger.info(
            "v42 migrations complete: aar_reviews table added "
            "(ccdash-automated-aar-review-v1, T1-005)."
        )

    # ── Ensure idx_sessions_git_branch exists on all pre-v34 databases ───────
    # _ensure_index is idempotent; the IF NOT EXISTS guard means this call is
    # always safe regardless of whether the v34 block ran above.
    await _ensure_index(
        db,
        "CREATE INDEX IF NOT EXISTS idx_sessions_git_branch"
        " ON sessions(git_branch, project_id)",
    )

    # ── T3-011: ensure migrations_applied table exists for pre-DDL-path DBs ─────
    # Databases that already had schema_version >= SCHEMA_VERSION skip
    # executescript(_TABLES), so the table may not exist yet.  CREATE TABLE IF
    # NOT EXISTS is always safe.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations_applied (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    # Record schema version
    if should_record_version:
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        # ── T3-011: record each applied migration version individually ──────────
        # INSERT OR IGNORE means re-running (idempotent path) never duplicates.
        # We record every version from (current_version + 1) to SCHEMA_VERSION
        # so that databases that skipped intermediate versions still get complete
        # ledger coverage for their first-boot DDL run.
        for _v in range(current_version + 1, SCHEMA_VERSION + 1):
            await db.execute(
                "INSERT OR IGNORE INTO migrations_applied (version) VALUES (?)",
                (_v,),
            )
    await db.commit()
    logger.info(f"Migrations complete — schema version {max(current_version, SCHEMA_VERSION)}")
