---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
plan_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
phase: 2
title: Cache & Query Correctness
status: completed
started: null
completed: null
created: '2026-05-31'
updated: '2026-06-01'
commit_refs:
- 46abba0
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 18
completed_tasks: 17
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- cache-owner
- warming-owner
- repo-owner
- pcc-owner
- ps-owner
- session-detail-owner
- invalidation-owner
- planning-bundle-owner
- legacy-features-owner
contributors: []
tasks:
- id: T2-001
  ledger_id: P2-001
  title: Shared distributed cache (Valkey/Redis or Postgres-backed) replacing per-replica
    in-process TTLCache
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: XL
  flag_gate: CCDASH_QUERY_CACHE_BACKEND
- id: T2-003
  ledger_id: P2-003
  title: Project-scope + cache the fingerprint (entity_links.project_id; cache fingerprint
    result)
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T1-008
  estimated_effort: M
- id: T2-004
  ledger_id: P2-004
  title: Replace feature_phases O(N) GROUP_CONCAT fingerprint with MAX(updated_at)+COUNT(*)
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: S
- id: T2-005
  ledger_id: P2-005
  title: Enforce documented per-metric TTLs (CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS,
    CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS)
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: S
- id: T2-006
  ledger_id: P2-006
  title: Project-scoped cache eviction API (clear_cache() evicts all projects today)
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: S
- id: T2-015
  ledger_id: P2-015
  title: "Raise TTLCache maxsize from 512 for multi-project \xD7 multi-endpoint load\
    \ (single-node fallback)"
  status: completed
  assigned_to:
  - cache-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: S
- id: T2-014
  ledger_id: P2-014
  title: Background cache warm-up job wired to CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS
    covering all 14 memoized endpoints
  status: completed
  assigned_to:
  - warming-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: M
- id: T2-008
  ledger_id: P2-008
  title: Replace SELECT * list_all with column-projected list_summary variants on
    planning summary paths
  status: completed
  assigned_to:
  - repo-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T1-004
  estimated_effort: M
- id: T2-009
  ledger_id: P2-009
  title: Add @memoized_query to V1 single-project PlanningCommandCenterQueryService.get_command_center
  status: completed
  assigned_to:
  - pcc-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: S
- id: T2-011
  ledger_id: P2-011
  title: Fast-path get_command_center_item by feature_id (no 500-item full-page scan
    for one feature)
  status: completed
  assigned_to:
  - pcc-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: S
- id: T2-013
  ledger_id: P2-013
  title: NullGitProbe in V1 single-project command-center build (git subprocess per
    item today)
  status: completed
  assigned_to:
  - pcc-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: S
- id: T2-010
  ledger_id: P2-010
  title: Add @memoized_query to single-project PlanningSessionQueryService.get_session_board
  status: completed
  assigned_to:
  - ps-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-001
  estimated_effort: S
- id: T2-017
  ledger_id: P2-017
  title: Batch session-detail multi-query fan-out (8+ sequential round-trips today)
  status: completed
  assigned_to:
  - session-detail-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
- id: T2-002
  ledger_id: P2-002
  title: "Sync-triggered cache invalidation \u2014 sync_project() clears affected\
    \ project's cache entries"
  status: completed
  assigned_to:
  - invalidation-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T2-001
  estimated_effort: M
- id: T2-007
  ledger_id: P2-007
  title: "Parallelize planning view-bundle sub-calls (6\xD7 list_all sequential \u2192\
    \ asyncio.gather + shared data pass)"
  status: completed
  assigned_to:
  - planning-bundle-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T2-008
  estimated_effort: M
- id: T2-012
  ledger_id: P2-012
  title: get_feature_planning_context must not load all features+docs for a single
    feature request
  status: completed
  assigned_to:
  - planning-bundle-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T2-008
  estimated_effort: M
- id: T2-016
  ledger_id: P2-016
  title: Add @memoized_query to legacy list_features (/api/features) polled every
    5s with N+1
  status: completed
  assigned_to:
  - legacy-features-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T1-010
  estimated_effort: M
- id: T2-018
  ledger_id: P2-018
  title: Precompute the planning graph in DB via worker (recomputed in-memory per
    cache TTL today)
  status: deferred
  assigned_to:
  - planning-bundle-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T3-007
  estimated_effort: M
  notes: "Deferred \u2014 depends on P3-007 (multi-project warming) + consumed by\
    \ Phase 5"
parallelization:
  batch_1:
  - T2-001
  - T2-003
  - T2-004
  - T2-005
  - T2-006
  - T2-015
  - T2-014
  - T2-008
  - T2-009
  - T2-011
  - T2-013
  - T2-010
  - T2-017
  batch_2:
  - T2-002
  - T2-007
  - T2-012
  - T2-016
  critical_path:
  - T2-001
  - T2-002
  - T2-008
  - T2-007
  estimated_total_time: 5-8 days
execution_model: batch-parallel
blockers: []
success_criteria:
- api + worker replicas share one distributed cache backend (Valkey default, Postgres-cache
  fallback)
- Cache hits survive replica restarts and are consistent across replicas
- sync_project() completion invalidates only the affected project's cache entries
- entity_links fingerprint scans only the project's rows; fingerprint result itself
  is cached
- feature_phases fingerprint computed via MAX(updated_at)+COUNT(*) instead of O(N)
  GROUP_CONCAT
- All 14 memoized endpoints covered by the background warm-up job
- Planning summary paths use column-projected list_summary queries; no SELECT * full-row
  payloads
- V1 command center and session board are memoized via @memoized_query
- legacy /api/features cached server-side; N+1 removed
- T2-018 deferred pending P3-007 completion
notes: "T2-001 (distributed cache) is the foundational blocker for T2-002, T2-005,\
  \ T2-006, T2-009, T2-010, T2-014, T2-015 \u2014 those tasks must not start until\
  \ T2-001 is complete. Tech-choice decision required before T2-001: Valkey for enterprise\
  \ / Postgres-cache fallback for single-node (per synthesis brief \xA78). T2-018\
  \ (planning graph precompute) is deferred because it depends on P3-007 (multi-project\
  \ warming) and is consumed by Phase 5 logic; it carries status=deferred and should\
  \ not block phase completion.\n"
progress: 94
---

# Phase 2 — Cache & Query Correctness

Progress file for CCDash Enterprise Edition v1, Phase 2.

## Summary

Makes the cache correct and fast across replicas. Delivers a shared distributed cache
(Valkey/Redis or Postgres-backed) to replace per-replica in-process `TTLCache`,
project-scoped fingerprinting, sync-triggered invalidation, `@memoized_query` coverage
for the remaining unmemoized service methods, background warm-up for all 14 endpoints,
column-projected summary queries, and the planning bundle `asyncio.gather` parallelisation.
Depends on Phase 1 index/scoping work (T1-004, T1-008, T1-010).

## Batch Execution Order

| Batch | Tasks | Gate |
|-------|-------|------|
| batch_1 | T2-001,003,004,005,006,015,014,008,009,011,013,010,017 | Parallel; T2-001 is the distributed-cache foundation — others that depend on it may start as soon as T2-001 merges |
| batch_2 | T2-002,007,012,016 | After batch_1; invalidation + bundle parallelisation + legacy memoization |

## Deferred Task

| Task | Reason | Unblocked By |
|------|--------|-------------|
| T2-018 | Depends on P3-007 (multi-project warming) + consumed by Phase 5 | P3-007 complete |

## Key Decisions Required Before Execution

| Decision | Gates | Recommendation |
|----------|-------|---------------|
| Shared cache tech: Valkey/Redis vs Postgres-backed | T2-001 | Valkey for enterprise; Postgres-cache fallback for single-node |
| Project-scoped eviction vs global clear | T2-002, T2-006 | Project-targeted eviction only; no global clear in enterprise |
