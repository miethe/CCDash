---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-data-loading-redesign-v1
feature_slug: feature-surface-data-loading-redesign-v1
prd_ref: docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
phase: 1
title: Repository and Query Foundation
status: in_progress
created: '2026-04-23'
updated: '2026-04-23'
started: '2026-04-23'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- data-layer-expert
- python-backend-engineer
contributors: []
model_usage:
  primary: sonnet
  external: []
ui_touched: false
runtime_smoke: not_applicable
tasks:
- id: P1-001
  description: Query Models - Define typed repository query option models (filters,
    sort keys, pagination, rollup field selection, linked-session includes) shared
    by SQLite/Postgres implementations and service layer.
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  started: 2026-04-23T01:00Z
  completed: 2026-04-23T01:30Z
  evidence:
  - test: backend/tests/test_feature_queries_models.py
  verified_by:
  - phase-1-orchestrator
- id: P1-002
  description: Feature List Query - Implement storage-backed list_feature_cards /
    count_feature_cards with filtering, search, sort, totals for SQLite and Postgres.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-001
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
  started: 2026-04-23T01:35Z
  completed: 2026-04-23T02:10Z
  evidence:
  - test: backend/tests/test_feature_list_query.py
  verified_by:
  - phase-1-orchestrator
- id: P1-003
  description: Feature Phase Summary Bulk Query - list_phase_summaries_for_features
    bulk query eliminating per-feature get_phases N+1.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P1-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  started: 2026-04-23T02:15Z
  completed: 2026-04-23T02:50Z
  evidence:
  - test: backend/tests/test_phase_summary_bulk.py
  verified_by:
  - phase-1-orchestrator
- id: P1-004
  description: Feature Rollup Aggregate Query - get_feature_session_rollups returns
    exact/partial metrics and freshness metadata for bounded feature IDs (100 cap)
    without reading session logs.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-002
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
  started: 2026-04-23T02:15Z
  completed: 2026-04-23T03:25Z
  evidence:
  - test: backend/tests/test_feature_rollup_query.py
  verified_by:
  - phase-1-orchestrator
- id: P1-005
  description: Linked-Session Page Query - True source-level pagination (list_feature_session_refs,
    count_feature_session_refs, list_session_family_refs) with optional inherited
    thread expansion.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P1-004
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P1-006
  description: Index Review - Add/validate indexes for feature filters, entity link
    lookups, session project/root ordering, document/task feature filters, test health
    joins. Capture query plans for SQLite and Postgres.
  status: pending
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-005
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
- id: P1-007
  description: Repository Tests - SQLite and Postgres-parity tests for filters, sorts,
    totals, rollups, linked-session pagination. Regression-proof against in-memory
    post-pagination and N+1.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P1-006
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - P1-001
  batch_2:
  - P1-002
  batch_3:
  - P1-003
  - P1-004
  batch_4:
  - P1-005
  batch_5:
  - P1-006
  batch_6:
  - P1-007
progress: 57
---

# Phase 1 Progress — Repository and Query Foundation

## Context

Phase 0 deliverables in `.claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/`:
- `field-inventory.md`, `query-matrix.md`, `rollup-dto-draft.md`, `modal-section-contracts.md`, `performance-budgets.md`, `parity-fixture-plan.md`

Key constraints fed from Phase 0:
- 18 metric groups currently require full session-log arrays per card (primary hotspot: `loadFeatureSessionSummary`).
- 3 frontend-only filters must move server-side: status, category, date ranges (indexed columns exist).
- Rollup DTO: 24 fields, 8 exact / 12 eventually_consistent / 4 partial; **100-ID batch cap**.
- v1 known bug: in-memory status/category filtering applied **after** pagination — Phase 1 must eliminate this path.

## Execution Strategy

Commit at the end of each batch. Tasks marked completed via CLI with `--started`, `--completed`, and `--evidence commit:<sha>`.
