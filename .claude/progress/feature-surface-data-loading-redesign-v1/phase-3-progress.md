---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-data-loading-redesign-v1
feature_slug: feature-surface-data-loading-redesign-v1
prd_ref: docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
phase_plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-3-frontend-board.md
phase: 3
title: Frontend Data Layer and Board Migration
status: in_progress
created: '2026-04-23'
updated: '2026-04-23'
started: '2026-04-23'
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
- react-performance-optimizer
contributors: []
model_usage:
  primary: sonnet
  external: []
ui_touched: true
runtime_smoke: pending
tasks:
- id: P3-001
  description: API Client Methods - Add typed client methods for feature card list, rollups, modal sections, and linked-session pages.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P2-005
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P3-002
  description: Feature Surface Hook - Implement useFeatureSurface for query state, list/rollup loading, cache keys, errors, invalidation.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-001
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: P3-003
  description: Server-Backed Filters - Move board search/filter/sort query state into API parameters while preserving draft/apply UX.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - P3-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P3-004
  description: Remove Eager Linked-Session Summary Loop - Delete filteredFeatures.forEach(loadFeatureSessionSummary) pattern.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P3-005
  description: Card Metric Mapping - Render card metrics from FeatureCardDTO plus FeatureRollupDTO.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - P3-004
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P3-006
  description: Cache and Invalidation - Bounded cache keyed by project/query/page/featureIds/freshness token.
  status: pending
  assigned_to:
  - react-performance-optimizer
  dependencies:
  - P3-002
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P3-007
  description: Board Tests - Tests proving bounded calls, query params, filter behavior, rollup rendering, no legacy summary fan-out.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P3-006
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - P3-001
  batch_2:
  - P3-002
  batch_3:
  - P3-003
  - P3-004
  - P3-006
  batch_4:
  - P3-005
  batch_5:
  - P3-007
progress: 0
---

# Phase 3 Progress — Frontend Data Layer and Board Migration

## Context

Phase 2 established bounded v1 feature-surface endpoints (cards view, rollups POST, modal section endpoints, paginated linked-sessions, observability). Phase 3 moves the ProjectBoard frontend off ad-hoc effects onto a dedicated data layer that issues one card page + one bounded rollup batch per query, with server-backed filters, bounded cache, and no per-feature linked-session fan-out.

## Execution Strategy

Commit at the end of each batch. Dependencies are strictly linear through P3-002, then fan out:

- Batch 1: P3-001 — typed client methods (foundation)
- Batch 2: P3-002 — `useFeatureSurface` hook (sequencing hub)
- Batch 3: P3-003 + P3-004 + P3-006 — filters, eager-loop removal, cache policy (parallel)
- Batch 4: P3-005 — card metric mapping onto card+rollup DTOs
- Batch 5: P3-007 — regression tests proving bounded calls

## Runtime Smoke

`ui_touched: true`; a dev-server smoke pass on the board (load, filter, sort, status change, modal open) is required before phase exit.
