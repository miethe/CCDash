---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
plan_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
phase: 3
title: DB-backed Project Registry & Multi-Project Worker
status: completed
started: 2026-06-01T14:06Z
completed: null
created: '2026-05-31'
updated: '2026-06-01'
commit_refs:
- dde811a
- a7032dc
pr_refs: []
overall_progress: 100
completion_estimate: complete (P3-003-FU + P3-006-FU landed)
total_tasks: 20
completed_tasks: 19
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- migration-owner
- notify-owner
- registry-owner
- sessions-repo-owner
- oq-owner
- watcher-queue-owner
- worker-bootstrap-owner
contributors: []
tasks:
- id: T3-001
  ledger_id: P3-001
  title: Replace projects.json with a DB-backed projects table
  status: completed
  assigned_to:
  - migration-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: L
  enterprise_gated: true
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-002
  ledger_id: P3-002
  title: Move open-question resolutions from process memory (_OQ_OVERLAY) to DB
  status: completed
  assigned_to:
  - migration-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T3-001
  estimated_effort: M
  enterprise_gated: true
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-003
  ledger_id: P3-003
  title: Make session primary key project-scoped (globally-unique PK risks cross-project
    collision)
  status: completed
  assigned_to:
  - migration-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T3-001
  estimated_effort: L
  destructive: true
  enterprise_gated: true
  started: 2026-06-01T21:00Z
  completed: 2026-06-01T22:30Z
  evidence:
  - test: backend/tests/test_sessions_composite_pk_upsert.py
  verified_by:
  - T3-FU-GATE
- id: T3-004
  ledger_id: P3-004
  title: Add project_id to session_logs, session_tool_usage, session_file_updates
  status: completed
  assigned_to:
  - migration-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T3-003
  estimated_effort: M
  enterprise_gated: true
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-014
  ledger_id: P3-014
  title: Postgres NOTIFY listener reconnect/backoff (dropped connection permanently
    kills live fan-out)
  status: completed
  assigned_to:
  - notify-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  enterprise_gated: true
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-001-facade
  ledger_id: P3-001
  title: "DB-backed projects table \u2014 repository facade layer"
  status: completed
  assigned_to:
  - registry-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-001
  estimated_effort: M
  notes: Repository/service facade over the projects table; ProjectManager reads/writes
    DB registry
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-003-repo
  ledger_id: P3-003
  title: "Session PK migration \u2014 repository + query updates"
  status: completed
  assigned_to:
  - sessions-repo-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-003
  estimated_effort: L
  destructive: true
  started: 2026-06-01T21:00Z
  completed: 2026-06-01T22:30Z
  evidence:
  - test: backend/tests/test_phase3_repository_migration.py
  verified_by:
  - T3-FU-GATE
- id: T3-004-repo
  ledger_id: P3-004
  title: "Detail tables project_id \u2014 repository + query updates"
  status: completed
  assigned_to:
  - sessions-repo-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-004
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-002-oq
  ledger_id: P3-002
  title: "OQ resolutions DB persistence \u2014 service + cache integration"
  status: completed
  assigned_to:
  - oq-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-002
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-005
  ledger_id: P3-005
  title: "Multi-project worker \u2014 per-project FileWatcher registry"
  status: completed
  assigned_to:
  - watcher-queue-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-001
  estimated_effort: XL
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-006
  ledger_id: P3-006
  title: Durable task queue + supervision replacing InProcessJobScheduler bare asyncio.create_task()
  status: completed
  assigned_to:
  - watcher-queue-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-001
  estimated_effort: XL
  started: 2026-06-01T21:00Z
  completed: 2026-06-01T22:30Z
  evidence:
  - test: backend/tests/test_p3_watcher_registry.py
  verified_by:
  - T3-FU-GATE
- id: T3-010
  ledger_id: P3-010
  title: Add asyncio.Lock mutex around rebind_watcher (race in multi-operator scenarios)
  status: completed
  assigned_to:
  - watcher-queue-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-005
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-013
  ledger_id: P3-013
  title: Add task supervision states + stale_since threshold alarm to probe contract
  status: completed
  assigned_to:
  - watcher-queue-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-006
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-015
  ledger_id: P3-015
  title: Job-queue depth metrics for analytics snapshots + cache warming
  status: completed
  assigned_to:
  - watcher-queue-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-006
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-007
  ledger_id: P3-007
  title: Multi-project warming + analytics loop (warm/analyze all registered projects)
  status: completed
  assigned_to:
  - worker-bootstrap-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-005
  - T2-014
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-008
  ledger_id: P3-008
  title: Remove global active-project fallback in enterprise mode (headerless requests
    must fail-fast)
  status: completed
  assigned_to:
  - worker-bootstrap-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-001
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-009
  ledger_id: P3-009
  title: Wire TelemetryExporterJob + ArtifactRollupExportJob for worker-watch profile
  status: completed
  assigned_to:
  - worker-bootstrap-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-012
  ledger_id: P3-012
  title: Remove module-level container = build_worker_runtime() orphaned at import
    time
  status: completed
  assigned_to:
  - worker-bootstrap-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-016
  ledger_id: P3-016
  title: "Multi-project projects.json without explicit binding \u2014 detect/warn"
  status: completed
  assigned_to:
  - worker-bootstrap-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-001
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T11:55Z
  evidence:
  - commit: dde811a
  verified_by:
  - T3-VALIDATOR
- id: T3-011
  ledger_id: P3-011
  title: Guard projects.json _save() against torn writes
  status: merged
  assigned_to:
  - migration-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T3-001
  estimated_effort: S
  notes: "Subsumed by T3-001 \u2014 DB-backed registry replaces the projects.json\
    \ write path; no separate implementation needed"
parallelization:
  batch_1:
  - T3-001
  - T3-002
  - T3-003
  - T3-004
  - T3-014
  batch_2:
  - T3-001-facade
  - T3-003-repo
  - T3-004-repo
  - T3-002-oq
  - T3-005
  - T3-006
  - T3-010
  - T3-013
  - T3-015
  - T3-007
  - T3-008
  - T3-009
  - T3-012
  - T3-016
  critical_path:
  - T3-001
  - T3-003
  - T3-005
  - T3-006
  - T3-007
  estimated_total_time: 7-10 days
execution_model: batch-parallel
blockers: []
success_criteria:
- A projects table is the authoritative registry; multi-replica containers read/write
  it; projects.json becomes import/bootstrap only
- OQ resolutions persisted in DB; survive restart; consistent across replicas
- sessions PK incorporates project_id (or composite uniqueness); no cross-project
  ID collision possible
- Detail tables (session_logs, session_tool_usage, session_file_updates) carry project_id
- Singleton FileWatcher becomes a per-project dict-keyed registry; one worker can
  watch N registered projects
- Durable queue with retry/priority/backpressure; container crash mid-sync resumes
  from queue
- Warming and analytics snapshot iterate all registered projects; cross-project analytics
  produced
- In enterprise mode a headerless request fails fast; local/dev mode retains fallback
- T3-011 confirmed subsumed by T3-001 (DB-backed registry eliminates torn-write risk)
- Migration ordering: "projects \u2192 oq_resolutions \u2192 job_queue \u2192 session\
    \ PK \u2192 detail project_id \u2192 SCHEMA_VERSION bump LAST"
notes: "Migration ordering is critical: T3-001 (projects table) must land first as\
  \ it unblocks T3-002, T3-003, T3-005, T3-006, T3-008, T3-016. T3-003 (session PK)\
  \ is destructive \u2014 DDL-only in batch_1 with repository/query updates deferred\
  \ to batch_2 (T3-003-repo). T3-011 is marked merged/subsumed: the DB-backed registry\
  \ in T3-001 makes the torn-write guard redundant. T3-014 (Postgres NOTIFY reconnect)\
  \ is enterprise_gated and runs in batch_1 independently since it has no registry\
  \ dependency. SCHEMA_VERSION bump must land last \u2014 after all additive DDL tasks\
  \ complete in both batches.\n"
progress: 95
runtime_smoke: not-applicable (backend-only phase)
---

# Phase 3 — DB-backed Project Registry & Multi-Project Worker

Progress file for CCDash Enterprise Edition v1, Phase 3.

## Summary

Makes CCDash genuinely multi-project: a DB-backed `projects` table replaces `projects.json`,
open-question resolutions are persisted in DB, session PKs become project-scoped, detail tables
gain `project_id`, the singleton `FileWatcher` becomes a per-project registry, and `InProcessJobScheduler`
is replaced by a durable queue with supervision and multi-project warming. T3-011 is pre-marked
`merged` — it is fully subsumed by T3-001 (DB-backed registry eliminates the torn-write surface).

## Batch Execution Order

| Batch | Tasks | Gate |
|-------|-------|------|
| batch_1 | T3-001,002,003,004,014 | DDL-only; T3-001 is the hard prerequisite; T3-003 is destructive (DDL only in this batch); T3-014 independent |
| batch_2 | T3-001-facade,003-repo,004-repo,002-oq,005,006,010,013,015,007,008,009,012,016 | After batch_1; repository/service/worker layers; parallel within the batch |

## Migration Ordering

| Step | Task | Notes |
|------|------|-------|
| 1 | T3-001 | projects table (DDL) |
| 2 | T3-002 | oq_resolutions table (DDL) |
| 3 | T3-006 | job_queue table (DDL) |
| 4 | T3-003 | session PK project-scoped (DDL; destructive) |
| 5 | T3-004 | detail tables project_id (DDL) |
| LAST | — | SCHEMA_VERSION bump after all additive DDL |

## Destructive / Enterprise-Gated Task Summary

| Task | Type | Notes |
|------|------|-------|
| T3-003 | destructive | Session PK migration; backfill required; DDL-only in batch_1, repo updates in batch_2 |
| T3-001 | enterprise_gated | DB registry; multi-replica prerequisite |
| T3-002 | enterprise_gated | OQ persistence; survive-restart requirement |
| T3-003 | enterprise_gated | Session PK scoping; cross-project safety |
| T3-004 | enterprise_gated | Detail table project_id |
| T3-014 | enterprise_gated | Postgres NOTIFY reconnect/backoff |
| T3-011 | merged | Subsumed by T3-001 DB-backed registry |
