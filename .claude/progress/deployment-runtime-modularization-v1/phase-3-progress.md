---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 3
title: Health, Readiness, and Degradation Semantics
status: completed
started: '2026-04-15'
completed: '2026-04-15'
commit_refs:
- "0c050f8"
- "0f36c24"
- "1ac72b2"
- "d7af803"
- "a6cd153"
pr_refs: []
overall_progress: 100
completion_estimate: "completed; probe contracts, API/worker diagnostics, and degradation tests are fully landed"
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- DevOps
- documentation-writer
contributors:
- codex
tasks:
- id: OPS-201
  description: Define a common liveness, readiness, and detailed-state schema for
    API and worker runtimes, including degraded-state semantics and recommended probe
    intervals.
  status: completed
  assigned_to:
  - backend-architect
  - DevOps
  dependencies:
  - JOB-104
  estimated_effort: 3pt
  priority: high
- id: OPS-202
  description: Refactor the current `/api/health` surface into additive live/ready/detail
    endpoints or equivalent payloads that distinguish DB, migration, auth, storage,
    and runtime-capability state.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OPS-201
  estimated_effort: 3pt
  priority: high
- id: OPS-203
  description: Add a lightweight probe server or equivalent admin-port surface for
    worker runtime that reports job state, checkpoint freshness, backlog, and last-success
    markers.
  status: completed
  assigned_to:
  - python-backend-engineer
  - DevOps
  dependencies:
  - OPS-201
  estimated_effort: 3pt
  priority: high
- id: OPS-204
  description: Add tests for degraded and unready conditions such as auth provider
    misconfiguration, pending migrations, missing worker binding, queue backlog, and
    disabled integrations.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - OPS-202
  estimated_effort: 2pt
  priority: high
- id: OPS-205
  description: Ensure readiness/detail payloads expose stable machine-consumable fields
    that CLI, MCP, and downstream skill guidance can rely on for troubleshooting and
    operator flows.
  status: completed
  assigned_to:
  - python-backend-engineer
  - documentation-writer
  dependencies:
  - OPS-201
  estimated_effort: 2pt
  priority: high
parallelization:
  batch_1:
  - OPS-201
  batch_2:
  - OPS-202
  - OPS-203
  - OPS-205
  batch_3:
  - OPS-204
  critical_path:
  - OPS-201
  - OPS-202
  - OPS-204
  estimated_total_time: 13pt / 5-6 days
blockers: []
success_criteria:
- API and worker each expose operator-grade probe surfaces.
- Degraded and unready states are consistent across runtimes.
- Hosted validation no longer depends on interpreting ad hoc log output alone.
- Probe and detail payloads are stable enough for CLI/MCP and skill-driven troubleshooting
  flows.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-3-progress.md
- backend/adapters/jobs/runtime.py
- backend/db/migration_governance.py
- backend/runtime/bootstrap.py
- backend/runtime/bootstrap_worker.py
- backend/runtime/container.py
- backend/runtime/storage_contract.py
- backend/runtime_ports.py
- backend/tests/test_cache_warming_job.py
- backend/tests/test_request_context.py
- backend/tests/test_runtime_bootstrap.py
- backend/tests/test_storage_profiles.py
- backend/worker.py
- components/OpsPanel.tsx
- components/session-intelligence/SessionIntelligencePanel.tsx
- services/apiClient.ts
- services/runtimeProfile.ts
progress: 100
updated: '2026-04-15'
---

# deployment-runtime-modularization-v1 - Phase 3

Use CLI to update progress:

```bash
# Mark the probe contract task complete
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-3-progress.md --task OPS-201 --status completed

# Mark worker probe surface complete
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-3-progress.md --task OPS-203 --status completed
```

## Objective

Define probe and degradation semantics for API and worker runtimes so operators can distinguish liveness, readiness, and actionable degraded states.

## Phase 3 Work Queue

| Task ID | Task Name | Dependency | Status |
| --- | --- | --- | --- |
| OPS-201 | Probe Contract | Root contract for runtime probe shape and degraded-state semantics | completed |
| OPS-202 | API Probe Split | Depends on `OPS-201` | completed |
| OPS-203 | Worker Probe Surface | Depends on `OPS-201` | completed |
| OPS-204 | Degradation Tests | Depends on `OPS-202` | completed |
| OPS-205 | Tooling-Facing Diagnostic Contract | Depends on `OPS-201` | completed |

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute OPS-201: define the common probe contract for API and worker runtimes")
Task("DevOps", "Execute OPS-201: validate probe contract assumptions for deployment and orchestration")

# Batch 2 (after OPS-201)
Task("python-backend-engineer", "Execute OPS-202: split the API health surface into live, ready, and detailed endpoints")
Task("python-backend-engineer", "Execute OPS-203: add the worker probe surface on a lightweight admin port")
Task("python-backend-engineer", "Execute OPS-205: codify stable diagnostic fields for CLI, MCP, and skill guidance")

# Batch 3 (after OPS-202)
Task("python-backend-engineer", "Execute OPS-204: add degraded and unready condition tests")
```
