---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-data-loading-redesign-v1
feature_slug: feature-surface-data-loading-redesign-v1
prd_ref: docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
phase_plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-4-modal-lazy-loading.md
phase: 4
title: Modal Lazy Loading and Reliability
status: in_progress
created: '2026-04-23'
updated: '2026-04-24'
started: '2026-04-23'
commit_refs:
- 42dfe77
- 34e4738
- 4fff4e5
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 11
completed_tasks: 9
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
- react-performance-optimizer
- frontend-architect
contributors: []
model_usage:
  primary: sonnet
  external: []
ui_touched: true
runtime_smoke: pending
tasks:
- id: P4-001
  description: Encoded Modal Paths - Replace raw feature ID path interpolation in
    modal fetches with encoded API client methods.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-001
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P4-002
  description: Modal Data Hook - useFeatureModalData with per-section query state,
    cache keys, abort/request IDs, retries.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - P2-007
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: P4-003
  description: Lazy Tab Loading - Remove full linked-session fetch from modal mount;
    trigger session fetch on Sessions tab activation or explicit prefetch.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - P4-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P4-004
  description: Session Pagination UI - load-more/page handling for linked sessions
    while preserving tree/grouping, summaries, and card detail.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - P4-003
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P4-005
  description: Tab State Rendering - visible loading, error, retry, empty, and stale
    states for each tab.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - P4-002
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P4-006
  description: Modal Live Refresh Policy - polling/live invalidation refreshes only
    loaded/active sections; no redundant detail fetches.
  status: completed
  assigned_to:
  - react-performance-optimizer
  dependencies:
  - P4-003
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P4-007
  description: SessionInspector Migration - Replace per-feature linked-session fan-out
    with useFeatureSurface + paginated modal session client.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-001
  - P3-006
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P4-008
  description: FeatureExecutionWorkbench Migration - Move feature/session reads onto
    shared surface client + bounded cache; render from FeatureCardDTO rollup.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-001
  - P3-005
  - P3-006
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P4-009
  description: Dashboard / BlockingFeatureList Migration - Consume shared FeatureCardDTO
    path; retire bespoke fetches.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - P3-005
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P4-010
  description: Modal Consumer Wiring - Wire FeatureModal* consumers onto P3-001 overview/section
    clients; remove raw /api/features interpolation in components.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - P4-001
  - P4-002
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P4-011
  description: Planning Cache Coordination - Layered invalidation between services/planning.ts
    SWR+LRU and useFeatureSurface bounded cache; ADR-style note.
  status: completed
  assigned_to:
  - frontend-architect
  - react-performance-optimizer
  dependencies:
  - P3-006
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - P4-001
  - P4-002
  - P4-009
  - P4-011
  batch_2:
  - P4-003
  - P4-005
  - P4-010
  batch_3:
  - P4-004
  - P4-006
  batch_4:
  - P4-007
  - P4-008
progress: 81
---

# Phase 4 Progress — Modal Lazy Loading and Reliability

## Context

Phase 3 moved the ProjectBoard onto `useFeatureSurface` with a bounded cache, server-backed filters, FeatureCardDTO/rollup rendering, and removal of the eager `loadFeatureSessionSummary` fan-out. Phase 4 applies the same discipline to the feature modal and the remaining legacy consumers (SessionInspector, FeatureExecutionWorkbench, Dashboard/BlockingFeatureList), plus coordinates the planning-page cache with the new feature-surface cache.

## Execution Strategy

Commit at the end of each batch. Tasks independent of the modal hook run in Batch 1 alongside the hook itself.

- Batch 1: P4-001 (encoded paths) + P4-002 (modal data hook) + P4-009 (Dashboard migration) + P4-011 (planning cache ADR) — all parallelizable; hook unblocks Batch 2.
- Batch 2: P4-003 (lazy tabs) + P4-005 (tab states) + P4-010 (modal consumer wiring) — parallel on top of P4-002.
- Batch 3: P4-004 (session pagination) + P4-006 (live refresh policy) — parallel on top of P4-003.
- Batch 4: P4-007 (SessionInspector) + P4-008 (FeatureExecutionWorkbench) — parallel migrations consuming the hook.

## Runtime Smoke

`ui_touched: true`. Dev-server smoke required before phase exit:
- Open modal overview on several features (including IDs with `/`, `#`, `&`, spaces) and confirm no eager linked-session call.
- Activate each tab (phases, docs, relations, sessions, test-status, history) and confirm on-demand load + loading/error/empty/retry states.
- Sessions tab: verify pagination and preservation of tree/summary/card detail.
- Live refresh: leave modal open and verify only the active tab refetches.
- SessionInspector, FeatureExecutionWorkbench, Dashboard: spot-check rendering from unified payloads, no duplicate fan-out.
