---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
plan_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
phase: 4
title: Frontend Performance Finish
status: completed
started: 2026-06-01T09:00Z
completed: 2026-06-01T20:00Z
created: '2026-05-31'
updated: '2026-06-01'
commit_refs:
- 6a32eda
- 9700bae
pr_refs: []
overall_progress: 100
completion_estimate: complete
total_tasks: 22
completed_tasks: 21
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- backend-typescript-architect
contributors: []
tasks:
- id: T4-001
  ledger_id: P4-001
  title: Server-side pagination for the planning session board (full project payload
    every load)
  status: completed
  assigned_to:
  - backend-pagination-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T2-010
  estimated_effort: L
  started: 2026-06-01T09:00Z
  completed: 2026-06-01T17:00Z
  evidence:
  - test: backend/tests/test_planning_sessions_pagination.py
  verified_by:
  - T4-GATE-W1
- id: T4-010
  ledger_id: P4-010
  title: Move GEMINI_API_KEY server-side (baked into JS bundle via Vite define)
  status: completed
  assigned_to:
  - gemini-proxy-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T09:00Z
  completed: 2026-06-01T17:00Z
  evidence:
  - test: backend/tests/test_ai_insight_router.py
  verified_by:
  - T4-GATE-W1
- id: T4-003
  ledger_id: P4-003
  title: "Make useData() reactive \u2014 useQuery() subscription, not getQueryData()\
    \ snapshot (7 domain arrays, 13+ components)"
  status: completed
  assigned_to:
  - datacontext-owner
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T09:00Z
  completed: 2026-06-01T17:00Z
  evidence:
  - test: contexts/__tests__
  verified_by:
  - T4-GATE-W1
- id: T4-002
  ledger_id: P4-002
  title: Migrate V1 PlanningCommandCenter to TanStack Query (raw useEffect/local state
    today)
  status: completed
  assigned_to:
  - command-center-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T2-009
  estimated_effort: M
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-014
  ledger_id: P4-014
  title: Add UI pagination to V1 command center (pageSize=50 hardcoded; features >50
    silently missing)
  status: completed
  assigned_to:
  - command-center-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-002
  estimated_effort: M
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-004
  ledger_id: P4-004
  title: V1 PlanningAgentSessionBoard virtualization (rich cards render for all sessions;
    CSS-scroll only)
  status: completed
  assigned_to:
  - session-board-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-001
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-018
  ledger_id: P4-018
  title: Avoid O(N) Set re-construction on session-board hover (re-evaluates all SessionCard
    memos)
  status: completed
  assigned_to:
  - session-board-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-004
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-019
  ledger_id: P4-019
  title: StaleIndicator should not start setInterval from mount regardless of staleness
  status: completed
  assigned_to:
  - session-board-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-006
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-006
  ledger_id: P4-006
  title: Replace setInterval sprawl with TQ refetchInterval/SSE invalidation (8+ components)
  status: completed
  assigned_to:
  - setinterval-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-003
  estimated_effort: L
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-011
  ledger_id: P4-011
  title: Migrate Dashboard KPI cards + analytics series to TanStack Query (legacy
    imperative path shows 0 on slow load)
  status: completed
  assigned_to:
  - dashboard-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-003
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-012
  ledger_id: P4-012
  title: Migrate AnalyticsDashboard to TanStack Query (7 parallel raw fetches every
    mount)
  status: completed
  assigned_to:
  - dashboard-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-003
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-005
  ledger_id: P4-005
  title: Raise useFeaturesQuery refetchInterval from 5s and useFeatureSurface list
    staleTime from 0
  status: completed
  assigned_to:
  - polls-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T2-016
  estimated_effort: S
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-008
  ledger_id: P4-008
  title: Correct hover-prefetch via queryClient.prefetchQuery (currently fetched and
    discarded; modal still cold)
  status: completed
  assigned_to:
  - polls-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-002
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - commit: pending
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-016
  ledger_id: P4-016
  title: Fix usePlanningSummaryQuery staleTime:0 refetch on every Planning mount
  status: completed
  assigned_to:
  - polls-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-009
  ledger_id: P4-009
  title: Self-host planning fonts (Google Fonts CDN fails silently in restricted-egress
    containers)
  status: completed
  assigned_to:
  - fonts-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-015
  ledger_id: P4-015
  title: TanStack Query cache invalidation on project switch (invalidateQueries()
    after setApiProjectScope())
  status: completed
  assigned_to:
  - project-switch-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-003
  estimated_effort: S
  started: 2026-06-01T09:00Z
  completed: 2026-06-01T17:00Z
  evidence:
  - test: contexts/__tests__
  verified_by:
  - T4-GATE-W1
- id: T4-013
  ledger_id: P4-013
  title: Add React.memo to inner panels of SessionInspector (6101 lines) and ProjectBoard
    (3895 lines)
  status: completed
  assigned_to:
  - memo-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-006
  estimated_effort: M
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-021
  ledger_id: P4-021
  title: OpsPanel should read sessions/documents reactively (stale useData() snapshots
    today)
  status: completed
  assigned_to:
  - opspanel-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-003
  estimated_effort: S
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-022
  ledger_id: P4-022
  title: Document/enable SSE for features/tests/ops in .env.example + deploy guides
    (defaulted off)
  status: completed
  assigned_to:
  - docs-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-005
  estimated_effort: S
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-020
  ledger_id: P4-020
  title: Reduce document page size / memory cap (pageSize=500, max 2000) for enterprise;
    lazy PlanCatalog load
  status: completed
  assigned_to:
  - docs-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T10:00Z
  completed: 2026-06-01T18:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W2
- id: T4-007
  ledger_id: P4-007
  title: Viewport-deferred mounting for session board + command center (planning home
    = 5 concurrent cold loads)
  status: completed
  assigned_to:
  - session-board-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T4-001
  - T4-002
  estimated_effort: M
  started: 2026-06-01T11:00Z
  completed: 2026-06-01T19:00Z
  evidence:
  - test: vitest
  verified_by:
  - T4-GATE-W3
- id: T4-017
  ledger_id: P4-017
  title: Gate multi-project queries on useProjectListReady (hardcoded projectListReady:true
    today)
  status: deferred
  assigned_to:
  - project-switch-owner
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T5-001
  estimated_effort: S
  notes: "Deferred \u2014 depends on P5-001 (runtime capability flag for multi-project\
    \ command center); out of scope for Phase 4"
parallelization:
  batch_1:
  - T4-001
  - T4-010
  - T4-003
  batch_2:
  - T4-002
  - T4-014
  - T4-004
  - T4-018
  - T4-019
  - T4-006
  - T4-011
  - T4-012
  - T4-005
  - T4-008
  - T4-016
  - T4-009
  - T4-015
  - T4-013
  - T4-021
  - T4-022
  - T4-020
  - T4-007
  critical_path:
  - T4-003
  - T4-006
  - T4-001
  - T4-004
  - T4-002
  estimated_total_time: 6-9 days
execution_model: batch-parallel
blockers: []
success_criteria:
- Session-board endpoint accepts cursor/page params; full project payload no longer
  fetched per load
- V1 command center uses TQ hooks (cache + dedup); no raw useEffect data fetch
- The 7 domain arrays are read via reactive useQuery; 13+ consuming components update
  on background refetch
- All manual setInterval polls replaced with TQ refetchInterval or SSE-driven invalidation
- V1 board BoardColumn virtualized (parity with multi-project board threshold 250)
- Gemini calls proxied through the backend; key never shipped in client bundle
- Dashboard KPI + analytics series use TQ; loading skeleton/error state instead of
  literal 0
- Planning fonts served from app/container; renders correctly with egress blocked
- features poll >= 30s when SSE off (was 5s); list-tier staleTime >= 10-30s
- queryClient.invalidateQueries() fires on project switch; no stale cross-project
  UI window
- T4-017 deferred pending P5-001 completion
notes: "T4-003 (useData reactive) is the foundational batch_1 prerequisite for T4-006,\
  \ T4-011, T4-012, T4-015, T4-021 \u2014 those tasks require reactive data before\
  \ they can correctly remove setInterval or migrate to TQ. T4-001 (server pagination)\
  \ and T4-002 (V1 CC TQ migration) are also batch_1 blockers for their respective\
  \ downstream batch_2 tasks. T4-017 is deferred because it depends on P5-001 (runtime\
  \ capability flag); it carries status=deferred and must not block phase 4 completion.\
  \ Runtime smoke gate required before marking phase completed per CLAUDE.md operating\
  \ procedures.\n"
progress: 95
runtime_smoke: partial-build+http+vitest-render+backend
merge_commit: 9700bae
merge_branch: feat/ccdash-enterprise-edition-v1
---

# Phase 4 — Frontend Performance Finish

Progress file for CCDash Enterprise Edition v1, Phase 4.

## Summary

Finishes the TanStack Query migration, adds pagination and virtualization where missing, eliminates
`setInterval` polling across 8+ components, defers off-screen mounting, self-hosts planning fonts,
and moves the Gemini key server-side. Core enabler is T4-003 (`useData()` reactive subscription),
which unblocks the polling cleanup and dashboard migrations. Can overlap Phase 1 (different owners).

## Batch Execution Order

| Batch | Tasks | Gate |
|-------|-------|------|
| batch_1 | T4-001, T4-010, T4-003 | Parallel; foundational — server pagination, Gemini proxy, reactive useData |
| batch_2 | T4-002,014,004,018,019,006,011,012,005,008,016,009,015,013,021,022,020,007 | After batch_1; parallel within batch |

## Deferred Task

| Task | Reason | Unblocked By |
|------|--------|-------------|
| T4-017 | Depends on P5-001 (multi-project runtime capability flag) | P5-001 complete |

## Key Dependency Chains

| Foundation | Downstream (batch_2) |
|-----------|----------------------|
| T4-003 (reactive useData) | T4-006, T4-011, T4-012, T4-015, T4-021 |
| T4-001 (server pagination) | T4-004, T4-007 |
| T4-002 (V1 CC TQ) | T4-014, T4-008, T4-007 |
| T4-006 (setInterval cleanup) | T4-013, T4-019 |
