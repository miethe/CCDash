---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 4
title: Worker Sweep Job
status: completed
created: '2026-07-29'
updated: '2026-07-31'
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
contributors: []
commit_refs:
- 5b9db6c
- 8573bcc
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T4-001
  description: RoutingRollupSweepJob — multi-project, incremental, idempotent worker
    sweep (clones AARReviewSweepJob)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  priority: high
  estimated_effort: 2h
  assigned_model: sonnet
  model_effort: adaptive
  note: T4-002 (runtime.py/container.py wiring) and T4-003 (test_routing_rollup_sweep_job.py
    + cache-invalidation hook) intentionally out of scope for this task
  evidence:
  - backend/adapters/jobs/routing_rollup_sweep_job.py (new); manual smoke run: flag-off
      no-op, multi-project fan-out, idempotent re-sweep, flag-flip reversibility all
      verified against an in-memory SQLite fixture
  started: 2026-07-30T22:00Z
  completed: 2026-07-31T00:00Z
  verified_by:
  - T4-003
- id: T4-002
  description: Wire job registration — register in runtime.py and container.py, add
    config tunable
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T4-001
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T00:00Z
  completed: 2026-07-31T00:30Z
  evidence:
  - commit: 5b9db6c
  verified_by:
  - T4-003
- id: T4-003
  description: Cache invalidation + reversibility tests — flag-flip test (AC-7), multi-project
    test, flag-off no-op test
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T4-002
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-07-31T00:30Z
  completed: 2026-07-31T01:15Z
  evidence:
  - test: backend/tests/test_routing_rollup_sweep_job.py
  - commit: 8573bcc
  verified_by:
  - T6-006
parallelization:
  batch_1:
  - T4-001
  batch_2:
  - T4-002
  batch_3:
  - T4-003
  critical_path:
  - T4-001
  - T4-002
  - T4-003
  estimated_total_time: 4h
blockers: []
success_criteria: []
files_modified:
- backend/adapters/jobs/routing_rollup_sweep_job.py
- backend/adapters/jobs/runtime.py
- backend/runtime/container.py
- backend/tests/test_routing_rollup_sweep_job.py
progress: 100
---

# Phase 4: Worker Sweep Job

**Total Tasks**: 3  
**Estimated Effort**: 2 points  
**Key Files**: `routing_rollup_sweep_job.py`, `runtime.py`, `container.py`, tests

## Objective

Ship the worker-side persistence half — a background sweep job that periodically populates `routing_rollup` by calling Phase 3's service for every registered project. This phase performs zero computation of its own; aggregation, mapping, and metrics are Phase 3's concern. This phase is purely orchestration + persistence.

## Implementation Notes

### Architectural Decisions

- **Wave placement**: Runs in same wave as Phase 5 (parallel execution) — Phase 4 touches jobs/runtime, Phase 5 touches routers/cli/mcp (disjoint files)
- **Multi-project fan-out**: Via `workspace_registry.list_projects()` (ADR-006), not projects.json
- **Idempotent upsert**: All computation delegated to Phase 3; zero re-derivation in job body
- **Flag gate checked twice**: Constructor-time (container.py) AND execute()-time (defense in depth)
- **Double-gate deliberate**: Single-point regression in flag cannot silently no-op a flip in either direction

### Patterns and Best Practices

- Clones `AARReviewSweepJob` structural shape exactly
- Multi-project enumeration, incremental watermark tracking, idempotent upsert pattern
- `(project_id, trigger)` coalescing guard prevents double-sweeping
- Cache invalidation on write (aclear_project_cache) — only when rows actually written

### Known Gotchas

- **ICA-offload eligible**: This is a mechanical clone; cost-shift candidate per delegation-router, but Phase 6 guards must re-run on return
- **Import cycles**: Local imports deferred in key methods to avoid `backend.adapters.jobs` ↔ `backend.application.services` cycle
- **Do not import from backend.scripts**: Duplicate lookup logic locally if needed (mirrors AAR pattern)
- **Workspace resolution**: Defensive pattern (resolve_session_workspace_id style) when needed for Phase 3 calls

### Development Setup

- Familiarity with `AARReviewSweepJob` module structure
- Knowledge of `workspace_registry.list_projects()` (ADR-006) pattern
- Understanding of job registration in `runtime.py` + `container.py`
- Ability to write multi-project fixture tests with workspace mocking

## Completion Notes

- Job appears in runtime's registered job list (T4-002, commit 5b9db6c).
- Multi-project sweep test green (`MultiProjectRoutingRollupSweepTests`, commit 8573bcc).
- Flag-flip reversibility test green (AC-7, worker/repository layer — see
  `RoutingRollupSweepJobTests::test_flag_flip_reversibility_produces_zero_new_writes_on_next_tick`,
  commit 8573bcc). Phase 6's T6-006 owns the feature-level, cross-transport
  final AC-7 validation; Phase 5's read surfaces (`T5-001..T5-004`) are still
  `pending` as of this phase's close, so the read-side "reports disabled"
  half of AC-7 is not asserted here — see this task's own Implementation
  Notes in the phase plan for why that's deliberate, not a gap.
- Cache invalidation fires exactly once per project that wrote rows, never
  for a project whose tick wrote nothing (verified in the same multi-project
  test, three-project fixture: two with in-window sessions, one without).
