---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md
phase: 1
title: Storage Hygiene & DB Performance
status: completed
started: null
completed: null
created: '2026-05-30'
updated: '2026-05-30'
commit_refs:
- 62fbf56
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 20
completed_tasks: 19
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- data-layer-expert
- python-backend-engineer
contributors: []
tasks:
- id: T1-001
  ledger_id: P1-001
  title: analytics_entries retention DELETE + ON CONFLICT upsert
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: L
  destructive: true
  flag_gate: CCDASH_ANALYTICS_RETENTION_ENABLED
  anchors:
  - analytics.py:20
  - analytics.py:47
  - sync_engine.py:5802-5812
  - base.py
- id: T1-002
  ledger_id: P1-002
  title: Drop session_logs (staged, flag-gated default-OFF)
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_4
  depends_on:
  - T1-010
  estimated_effort: XL
  destructive: true
  flag_gate: CCDASH_DROP_SESSION_LOGS_ENABLED
  anchors:
  - sqlite_migrations.py:165-220
  - services/sessions.py:87-118
  - api.py:626
  - api.py:660
  - api.py:812
  - api.py:844
  - api.py:956
  - _client_v1_features.py:814
  - _client_v1_features.py:849
  - feature_forensics.py:167
  - skillmeat_memory_drafts.py:269
- id: T1-003
  ledger_id: P1-003
  title: telemetry_events TTL retention
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: M
  destructive: true
  flag_gate: CCDASH_TELEMETRY_RETENTION_ENABLED
  anchors:
  - sqlite_migrations.py:501-542
  - sync_engine.py:1428-1456
  - sync_engine.py:1495-1527
- id: T1-004
  ledger_id: P1-004
  title: Backfill idx_sessions_project_status_updated via _ensure_index
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - sqlite_migrations.py:161-162
  - sqlite_migrations.py:1362-1367
- id: T1-005
  ledger_id: P1-005
  title: idx_sessions_source_file (+composite)
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - repositories/sessions.py:161-167
  - sync_engine.py:4121-4130
- id: T1-006
  ledger_id: P1-006
  title: SQLite pragmas (dev-only)
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - connection.py:50-54
- id: T1-007
  ledger_id: P1-007
  title: _capture_analytics N+1 -> batched CTE/JOIN
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_3
  depends_on:
  - T1-004
  estimated_effort: L
  anchors:
  - sync_engine.py:5787
  - sync_engine.py:5876-5972
  - analytics.py
- id: T1-008
  ledger_id: P1-008
  title: entity_graph.upsert single-tx executemany
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - entity_graph.py:27
  - entity_graph.py:41
- id: T1-009
  ledger_id: P1-009
  title: executemany inserts (telemetry/attribution/session-log)
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - sync_engine.py:1428-1456
  - usage_attribution.py:26
  - usage_attribution.py:53
  - repositories/sessions.py:730-753
- id: T1-010
  ledger_id: P1-010
  title: Materialize session badge columns
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: L
  anchors:
  - api.py:624-660
  - services/sessions.py:87-118
  - repositories/sessions.py
- id: T1-011
  ledger_id: P1-011
  title: Postgres atomic upsert_logs/file_updates
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - repositories/postgres/sessions.py:88
  - _transactions.py
- id: T1-012
  ledger_id: P1-012
  title: Postgres entity_links UNIQUE into initial DDL
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - postgres_migrations.py:1491-1498
- id: T1-013
  ledger_id: P1-013
  title: get_latest_entries HAVING fix
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T1-001
  estimated_effort: S
  anchors:
  - analytics.py:57-83
- id: T1-014
  ledger_id: P1-014
  title: partial indexes (analytics period=point, telemetry event_type)
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T1-001
  estimated_effort: S
  anchors:
  - analytics.py:57-83
- id: T1-015
  ledger_id: P1-015
  title: Reconcile SQLite(27)/Postgres(28) SCHEMA_VERSION
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_5
  depends_on:
  - T1-004
  - T1-005
  - T1-010
  - T1-012
  - T1-014
  - T1-019
  estimated_effort: M
  anchors:
  - sqlite_migrations.py:16
  - postgres_migrations.py:11
- id: T1-016
  ledger_id: P1-016
  title: FTS5/tsvector on session_messages.content
  status: deferred
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_4
  depends_on:
  - T1-002
  estimated_effort: L
  anchors:
  - sqlite_migrations.py
- id: T1-017
  ledger_id: P1-017
  title: manifest JSONL session-scan skip
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - sync_engine.py:4107-4119
  - sync_engine.py:4239-4278
- id: T1-018
  ledger_id: P1-018
  title: batch startup backfill loops
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: M
  anchors:
  - sync_engine.py:2058-2095
- id: T1-019
  ledger_id: P1-019
  title: entity_links.project_id + idx_links_project (Phase 2 prereq)
  status: completed
  assigned_to:
  - data-layer-expert
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T1-008
  estimated_effort: M
  anchors:
  - sqlite_migrations.py:37-56
  - entity_graph.py
- id: T1-P0012
  ledger_id: P0-012
  title: Canonical-source-key delete path (folded from Phase 0)
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  anchors:
  - sync_engine.py:3939
  - sync_engine.py:4135
  - sync_engine.py:1292
parallelization:
  batch_0:
  - T1-004
  - T1-005
  - T1-006
  - T1-008
  - T1-009
  - T1-011
  - T1-012
  - T1-017
  - T1-018
  batch_1:
  - T1-019
  - T1-010
  - T1-P0012
  batch_2:
  - T1-001
  - T1-003
  - T1-013
  - T1-014
  batch_3:
  - T1-007
  batch_4:
  - T1-002
  - T1-016
  batch_5:
  - T1-015
  critical_path:
  - T1-001
  - T1-013
  - T1-007
  - T1-010
  - T1-002
  - T1-015
  estimated_total_time: 5-7 days
execution_model: batch-parallel
blockers: []
success_criteria:
- analytics_entries retention runs on worker schedule without locking SQLite
- session_logs drop is flag-gated (CCDASH_DROP_SESSION_LOGS_ENABLED=false by default)
- All 6 session_logs consumers migrated to session_messages before T1-002 runs
- idx_sessions_project_status_updated and idx_sessions_source_file exist on both backends
- SCHEMA_VERSION reconciled (SQLite=28, Postgres=28) after all additive DDL
- N+1 in _capture_analytics eliminated; executemany in bulk-insert paths
notes: "Destructive tasks (T1-001, T1-002, T1-003) are flag-gated and worker-scheduled.\
  \ T1-002 (session_logs drop) is the highest-risk task: it is irreversible. It must\
  \ not run until T1-010 (badge materialization) is complete AND all 6 consumers have\
  \ been migrated. DB snapshot required before enabling CCDASH_DROP_SESSION_LOGS_ENABLED.\
  \ T1-016 (FTS5) should be deferred if T1-002 staging is incomplete. T1-015 (SCHEMA_VERSION\
  \ bump) MUST land last \u2014 after all additive DDL tasks. T1-P0012 folds P0-012\
  \ (canonical delete) from Phase 0 decisions block into this phase's batch_1 per\
  \ the decisions-block instruction.\n"
progress: 95
---

# Phase 1 — Storage Hygiene & DB Performance

Progress file for CCDash Enterprise Edition v1, Phase 1.

## Summary

Cleans up the storage layer: retention/TTL policies for analytics and telemetry,
session badge column materialization, N+1 elimination in analytics capture,
executemany batch inserts, Postgres atomicity fixes, index backfills, and
the staged (flag-gated) drop of the legacy `session_logs` table in favor of
the canonical `session_messages` store. SCHEMA_VERSION bump lands last.

## Batch Execution Order

| Batch | Tasks | Gate |
|-------|-------|------|
| batch_0 | T1-004,005,006,008,009,011,012,017,018 | Parallel; additive/non-destructive |
| batch_1 | T1-019, T1-010, T1-P0012 | Schema/materialization + canonical delete |
| batch_2 | T1-001, T1-003, T1-013, T1-014 | Destructive retention; flag-gated |
| batch_3 | T1-007 | N+1 rewrite; needs T1-004 indexes |
| batch_4 | T1-002, T1-016 | Staged drop + FTS; T1-016 optional |
| batch_5 | T1-015 | Version bump — MUST be last |

## Destructive Task Summary

| Task | Flag Gate | Default | Reversible |
|------|-----------|---------|------------|
| T1-001 | CCDASH_ANALYTICS_RETENTION_ENABLED | OFF | Partially (re-derivable) |
| T1-002 | CCDASH_DROP_SESSION_LOGS_ENABLED | OFF | No (take DB snapshot first) |
| T1-003 | CCDASH_TELEMETRY_RETENTION_ENABLED | OFF | Partially |

## Risk Hotspots

- **T1-002**: session_logs DROP is irreversible; filesystem JSONL is the re-derivable SoT;
  snapshot DB before enabling flag.
- **T1-001/T1-003 retention DELETEs**: batched (batch_size=1000) + busy_timeout;
  run on worker schedule, not request path.
- **T1-015**: SCHEMA_VERSION no-op on existing DBs if not last; `_ensure_index` is idempotent.
