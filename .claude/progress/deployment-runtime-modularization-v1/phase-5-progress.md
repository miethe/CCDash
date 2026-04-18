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
status: in_progress
started: '2026-04-18'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 5
completion_estimate: "started 2026-04-18; 3-4 days remaining to land runtime telemetry metadata, hosted misconfiguration guardrails, and worker freshness signals"
total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
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
  status: pending
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
  status: in_progress
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
  status: pending
  assigned_to:
  - DevOps
  - python-backend-engineer
  dependencies:
  - OPS-203
  estimated_effort: 3pt
  priority: high
parallelization:
  batch_1:
  - OBS-401
  - OBS-402
  - OBS-403
  critical_path:
  - OBS-402
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
progress: 5
updated: '2026-04-18'
---

# deployment-runtime-modularization-v1 - Phase 5

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/deployment-runtime-modularization-v1/phase-5-progress.md --task OBS-402 --status completed
```

## Objective

Start Phase 5 by landing runtime-aware observability metadata, hosted misconfiguration guardrails, and worker freshness signals so operators can distinguish safe hosted posture from degraded or mixed-mode behavior.

## Observability Guardrail Snapshot

| Concern | Current state | Notes |
| --- | --- | --- |
| Runtime metadata telemetry | queued | Need runtime profile, storage profile, deployment mode, project binding, and worker role tags across logs, traces, and metrics. |
| Misconfiguration guardrails | in progress | Phase kickoff is focused on making permissive auth, invalid storage, missing secrets, unsupported integrations, and unsafe worker bindings visible and fail-fast where required. |
| Backpressure and freshness signals | queued | Need backlog, last-success, sync lag, and watcher-disabled visibility in metrics plus detailed health payloads. |

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("DevOps", "Execute OBS-401: add runtime metadata tags across logs, traces, and metrics for API and worker runtimes")
Task("backend-architect", "Execute OBS-402: add hosted misconfiguration guardrails and fail-fast checks for unsafe runtime combinations")
Task("DevOps", "Execute OBS-403: expose backlog and freshness signals in metrics and detailed health payloads")
```
