---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 2
title: Worker Ownership and Job Routing
status: completed
started: '2026-04-14'
completed: '2026-04-14'
commit_refs:
- "11c9926"
- "866da71"
- "3612eab"
pr_refs: []
overall_progress: 100
completion_estimate: "completed; worker binding, filesystem isolation, and CLI/MCP bootstrap invariants are fully landed"
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- data-layer-expert
- DevOps
contributors:
- codex
tasks:
- id: JOB-101
  description: Classify all current background work including startup sync, file watch,
    analytics snapshots, telemetry export, integration refresh/backfill, and reconciliation
    by runtime owner and trigger model, including the API-local manual exception paths
    for telemetry push-now, integration refresh/backfill, and cache sync endpoints.
  status: completed
  assigned_to:
  - backend-architect
  - DevOps
  dependencies:
  - RUN-003
  estimated_effort: 3pt
  priority: high
- id: JOB-102
  description: Replace implicit active-project assumptions with an explicit worker
    binding contract based on operator configuration or workspace-registry resolution
    rules.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - JOB-101
  estimated_effort: 4pt
  priority: high
- id: JOB-103
  description: Move watcher and filesystem-ingest assumptions behind local/worker-only
    adapter boundaries and prevent accidental start in `api` or `test` profiles.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - JOB-101
  estimated_effort: 2pt
  priority: high
- id: JOB-104
  description: Preserve the current local convenience posture where API plus jobs
    may co-run, while keeping hosted API stateless and background-free.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - JOB-102
  estimated_effort: 3pt
  priority: high
- id: JOB-105
  description: Codify that CLI and MCP query surfaces remain non-serving, non-job-owning
    adapters that use lightweight runtime bootstrap and never trigger watcher, startup
    sync, or worker ownership paths.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - JOB-101
  estimated_effort: 2pt
  priority: high
parallelization:
  batch_1:
  - JOB-101
  batch_2:
  - JOB-102
  - JOB-103
  - JOB-105
  batch_3:
  - JOB-104
  critical_path:
  - JOB-101
  - JOB-102
  - JOB-104
  estimated_total_time: 16pt / 5-6 days
blockers: []
success_criteria:
- Hosted API no longer owns watcher, startup sync, or scheduled background work.
- Worker can be started independently with explicit responsibility boundaries.
- Local runtime still supports current contributor workflows without hidden hosted assumptions.
- CLI and MCP remain lightweight query adapters with no accidental job or watcher ownership.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-2-progress.md
- docs/setup-user-guide.md
progress: 100
updated: '2026-04-14'
---

# deployment-runtime-modularization-v1 - Phase 2

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-2-progress.md --task JOB-101 --status in_progress
```

## Objective

Document the Phase 2 worker ownership model so runtime routing, worker binding, and API-local operator exceptions stay aligned with the plan.

## Background Job Ownership Matrix

| Concern | local | api | worker | test |
| --- | --- | --- | --- | --- |
| Startup sync | owns | none | owns | none |
| File watch | owns | none | none | none |
| Analytics snapshots | owns | none | owns | none |
| Telemetry export | manual push-now only | manual push-now only | owns scheduled export | none |
| Integration refresh/backfill | startup refresh/backfill when configured | manual sync/refresh/backfill only | startup refresh/backfill when configured | none |
| Reconciliation / cache sync | owns | manual exception only when `sync_engine` exists | owns | none |

## API-Local Exception Paths

- `telemetry push-now` is a manual HTTP control path, not a scheduled ownership path.
- `integration refresh/backfill` is a startup-time concern in local/worker runtimes when SkillMeat is configured; the API exposes manual HTTP control paths.
- `cache` sync/rebuild endpoints are only usable when the API has `app.state.sync_engine`; otherwise they fail closed.
- CLI and MCP are lightweight query adapters; they bootstrap with `test`-profile wiring and do not own background work.

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute JOB-101: classify background work ownership and API-local exception paths")

# Batch 2 (after JOB-101)
Task("backend-architect", "Execute JOB-102: define the explicit worker binding contract")
Task("python-backend-engineer", "Execute JOB-103: isolate watcher and filesystem-ingest assumptions behind local/worker adapters")
Task("backend-architect", "Execute JOB-105: codify CLI and MCP lightweight bootstrap invariants")

# Batch 3 (after JOB-102)
Task("backend-architect", "Execute JOB-104: preserve local co-run compatibility without reintroducing hosted background work")
```
