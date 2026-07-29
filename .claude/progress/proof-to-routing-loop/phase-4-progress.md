---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 4
title: "Worker Sweep Job"
status: pending
created: "2026-07-29"
updated: "2026-07-29"
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["python-backend-engineer"]
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T4-001"
    description: "RoutingRollupSweepJob — multi-project, incremental, idempotent worker sweep (clones AARReviewSweepJob)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    priority: "high"
    estimated_effort: "2h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T4-002"
    description: "Wire job registration — register in runtime.py and container.py, add config tunable"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T4-001"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T4-003"
    description: "Cache invalidation + reversibility tests — flag-flip test (AC-7), multi-project test, flag-off no-op test"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T4-002"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

parallelization:
  batch_1: ["T4-001"]
  batch_2: ["T4-002"]
  batch_3: ["T4-003"]
  critical_path: ["T4-001", "T4-002", "T4-003"]
  estimated_total_time: "4h"

blockers: []

success_criteria: []

files_modified:
  - "backend/adapters/jobs/routing_rollup_sweep_job.py"
  - "backend/adapters/jobs/runtime.py"
  - "backend/runtime/container.py"
  - "backend/tests/test_routing_rollup_sweep_job.py"

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

*Fill in when phase is complete*

- Job appears in runtime's registered job list
- Multi-project sweep test green
- Flag-flip reversibility test green (AC-7)
- Cache invalidation fires exactly once per project that wrote rows
