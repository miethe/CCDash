---
type: progress
schema_version: 2
doc_type: progress
prd: deployment-runtime-modularization-v1
feature_slug: deployment-runtime-modularization-v1
prd_ref: /docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
phase: 5
title: Observability and Hosted Safety Guardrails
status: completed
started: '2026-04-18'
completed: '2026-04-18'
commit_refs:
- "e0ccd5f"
- "c4dce45"
- "5f40fb9"
pr_refs: []
overall_progress: 100
completion_estimate: "completed; hosted auth and worker probe guardrails, worker freshness signals, and runtime-tagged telemetry export metrics are fully landed"
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- DevOps
contributors:
- codex
tasks:
- id: OBS-401
  description: Tag logs, traces, and metrics with runtime profile, storage profile,
    deployment mode, project binding, and worker role metadata.
  status: completed
  assigned_to:
  - DevOps
  - python-backend-engineer
  dependencies:
  - PKG-302
  estimated_effort: 2pt
  priority: high
- id: OBS-402
  description: Add structured warnings and fail-fast checks for permissive auth fallback,
    invalid storage pairing, missing secrets, unsupported integration settings, and
    unsafe worker bindings.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PKG-301
  estimated_effort: 3pt
  priority: high
- id: OBS-403
  description: Expose job backlog, last successful execution times, sync lag, and
    watcher-disabled state in metrics and detailed health payloads.
  status: completed
  assigned_to:
  - DevOps
  - python-backend-engineer
  dependencies:
  - OPS-203
  estimated_effort: 3pt
  priority: high
parallelization:
  batch_1:
  - OBS-402
  batch_2:
  - OBS-401
  - OBS-403
  critical_path:
  - OBS-402
  - OBS-401
  - OBS-403
  estimated_total_time: 8pt / 3-4 days
blockers: []
success_criteria:
- Runtime metadata is present across primary logs, traces, and metrics for API and
  worker runtimes.
- Hosted safety failures are surfaced through structured warnings and fail fast where
  the runtime contract requires it.
- Worker backlog, freshness, sync lag, and watcher-disabled signals are available
  in metrics and detailed health payloads for alerting and operator diagnosis.
files_modified:
- .claude/progress/deployment-runtime-modularization-v1/phase-5-progress.md
- backend/adapters/auth/bearer.py
- backend/adapters/jobs/runtime.py
- backend/runtime/container.py
- backend/tests/test_cache_warming_job.py
- backend/tests/test_runtime_bootstrap.py
- backend/observability/otel.py
- backend/services/integrations/telemetry_exporter.py
- backend/tests/test_telemetry_exporter.py
progress: 100
updated: '2026-04-18'
---

# deployment-runtime-modularization-v1 - Phase 5

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-5-progress.md --task OBS-402 --status completed
```

## Objective

Close Phase 5 by landing runtime-aware observability metadata, hosted misconfiguration guardrails, and worker freshness signals so operators can distinguish safe hosted posture from degraded or mixed-mode behavior.

## Observability Guardrail Snapshot

| Concern | Current state | Notes |
| --- | --- | --- |
| Runtime metadata telemetry | landed | Telemetry exporter metrics now carry runtime profile, deployment mode, and storage profile dimensions for OTEL and Prometheus paths. |
| Misconfiguration guardrails | landed | Hosted auth fallback and worker/runtime misconfiguration now surface structured probe warnings and fail fast where the runtime contract requires it. |
| Backpressure and freshness signals | landed | Worker probes and metrics now expose backlog counts, last-success freshness, sync lag, and watcher-disabled state for operator diagnosis. |

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("backend-architect", "Execute OBS-402: add hosted misconfiguration guardrails and fail-fast checks for unsafe runtime combinations")

# Batch 2 (after OBS-402)
Task("DevOps", "Execute OBS-401: add runtime metadata tags across logs, traces, and metrics for API and worker runtimes")
Task("DevOps", "Execute OBS-403: expose backlog and freshness signals in metrics and detailed health payloads")
```

## Completion Notes

- Landed hosted auth and runtime probe guardrails in `backend/adapters/auth/bearer.py`, `backend/runtime/container.py`, and `backend/adapters/jobs/runtime.py`, including structured warnings for unsafe worker bindings and degraded watcher state.
- Added worker probe freshness and backpressure reporting so detailed runtime health now includes backlog counts, sync lag, watcher-disabled state, and last-success markers for managed jobs.
- Tagged telemetry exporter metrics with runtime dimensions in `backend/observability/otel.py` and `backend/services/integrations/telemetry_exporter.py`, with regression coverage in the Phase 5 test files.
