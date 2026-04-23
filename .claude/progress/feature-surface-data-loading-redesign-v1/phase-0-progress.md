---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-data-loading-redesign-v1
feature_slug: feature-surface-data-loading-redesign-v1
prd_ref: docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
phase: 0
title: Inventory, Contracts, Guardrails
status: pending
created: 2026-04-23
updated: '2026-04-23'
started: '2026-04-23'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 6
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- lead-architect
- backend-architect
- frontend-developer
- react-performance-optimizer
contributors: []
model_usage:
  primary: sonnet
  external: []
ui_touched: false
runtime_smoke: not_applicable
tasks:
- id: P0-001
  description: 'Feature Surface Inventory - field map covering board cards, list view,
    modal (overview, phases, docs, relations, sessions, test status, history), PlanningHomePage,
    FeatureExecutionWorkbench, and SessionInspector links. Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/field-inventory.md'
  status: completed
  assigned_to:
  - frontend-developer
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  started: 2026-04-23T00:00Z
  completed: 2026-04-23T00:10Z
  evidence:
  - file: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/field-inventory.md
- id: P0-002
  description: 'Filter/Sort/Search Inventory - query matrix for text search, status/stage,
    category, date ranges, progress, tasks, dependency state, quality signals, completed
    grouping. Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/query-matrix.md'
  status: pending
  assigned_to:
  - backend-architect
  dependencies:
  - P0-001
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P0-003
  description: 'Rollup Contract Draft - FeatureRollupDTO fields (session counts, primary
    roots, subthreads, token/cost totals, latest activity, model/provider summary,
    task/doc/test metrics, freshness, precision). Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/rollup-dto-draft.md'
  status: pending
  assigned_to:
  - lead-architect
  dependencies:
  - P0-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: P0-004
  description: 'Modal Section Contract Draft - per-tab source endpoint, cache key,
    loading state, failure mode for overview/phases/docs/relations/sessions/test status/history.
    Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/modal-section-contracts.md'
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - P0-001
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
- id: P0-005
  description: 'Performance Budgets - request count, payload size, latency, cache
    budgets for board and modal with measurable assertions. Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/performance-budgets.md'
  status: pending
  assigned_to:
  - react-performance-optimizer
  dependencies:
  - P0-003
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
- id: P0-006
  description: 'Parity Fixture Plan - small/medium/large project fixtures with linked
    sessions, subthreads, docs, tests, mixed statuses. Output: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/parity-fixture-plan.md'
  status: pending
  assigned_to:
  - backend-architect
  dependencies:
  - P0-002
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
parallelization:
  batch_1:
  - P0-001
  batch_2:
  - P0-002
  - P0-003
  - P0-004
  batch_3:
  - P0-005
  - P0-006
  critical_path:
  - P0-001
  - P0-003
  - P0-005
  estimated_total_time: 2-3 days
blockers: []
success_criteria:
- id: SC-0.1
  description: Field inventory covers every current visible feature/card/modal metric
  status: pending
- id: SC-0.2
  description: Query matrix covers all current filters/sorts/search behavior
  status: pending
- id: SC-0.3
  description: DTO contracts identify exact vs eventually consistent values
  status: pending
- id: SC-0.4
  description: Performance budgets are measurable
  status: pending
- id: SC-0.5
  description: Parity fixture plan supports old-vs-new and performance tests
  status: pending
progress: 16
---

# Phase 0 Progress: Inventory, Contracts, Guardrails

Deliverables are markdown artifacts under
`.claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/`.
Phase 0 is pure discovery/contract work — no application code changes.
Runtime smoke gate is not applicable (`ui_touched: false`).

## Batch Strategy

- **Batch 1** (serial): P0-001 — establishes field map used by all subsequent tasks.
- **Batch 2** (parallel): P0-002, P0-003, P0-004 — each consumes the field map to produce a different contract surface.
- **Batch 3** (parallel): P0-005 (needs rollup DTO), P0-006 (needs query matrix).

Commits are taken after each batch per operator instruction.
