---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 5
phase_title: Performance Validation Gate
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 5: Performance Validation Gate'
status: in-progress
started: '2026-05-05'
completed: null
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: task-scoped
overall_progress: 50
completion_estimate: 2 tasks remaining
total_tasks: 4
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- performance-engineer
- task-completion-validator
contributors: []
tasks:
- id: VAL-001
  description: Start the stack twice and compare sync, fanout, and write counts for unchanged alias-path files.
  status: completed
  assigned_to:
  - performance-engineer
  dependencies:
  - ING-004
  - MIG-004
  estimated_effort: 2 pts
  priority: high
- id: VAL-002
  description: Sample worker-watch CPU and memory every 30 seconds for 10 minutes after startup completes with no file changes.
  status: completed
  assigned_to:
  - performance-engineer
  dependencies:
  - VAL-001
  estimated_effort: 1 pt
  priority: medium
- id: VAL-003
  description: Capture table stats before and after second startup to ensure unchanged rows and dead tuples do not grow materially.
  status: pending
  assigned_to:
  - performance-engineer
  dependencies:
  - VAL-001
  estimated_effort: 1 pt
  priority: high
- id: VAL-004
  description: Run focused backend tests for watcher, runtime bootstrap, fanout, sync writes, canonicalization, and migration coverage.
  status: pending
  assigned_to:
  - task-completion-validator
  dependencies:
  - ING-004
  - MIG-004
  estimated_effort: 1 pt
  priority: high
parallelization:
  batch_1:
  - VAL-001
  batch_2:
  - VAL-002
  - VAL-003
  - VAL-004
  critical_path:
  - VAL-001
  - VAL-003
blockers: []
success_criteria:
- Second startup does not bulk re-ingest unchanged alias-path session files.
- Idle CPU/RAM evidence distinguishes startup load from sustained idle behavior.
- Focused regression tests pass or caveats are recorded with exact command output.
files_modified:
- .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-5-progress.md
progress: 50
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 5

## Objective

Validate startup idempotence, idle resource behavior, Postgres churn, and regression coverage after phases 3 and 4 complete.

## Current Status

Phase 5 is in progress. VAL-001 completed live startup idempotence smoke against the compose enterprise/postgres/live-watch stack.

## VAL-001 Evidence

- `docker-compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch up -d` started the stack.
- First `worker-watch` startup sync completed at `2026-05-05T03:05:14Z`: `startupSync=succeeded`, backlog `0`, readiness `pass`, `lastDurationMs=576388`.
- Before restart, live fanout publisher reported `published=1424`, `publishErrors=0`.
- `docker-compose ... restart worker-watch` triggered a second startup sync.
- Second startup sync completed at `2026-05-05T03:07:32Z`: `startupSync=succeeded`, backlog `0`, readiness `pass`, `lastDurationMs=112252`, `published=11`, `publishErrors=0`.
- The second startup did not bulk re-publish the corpus and completed materially faster than the first startup.

## VAL-002 Evidence

- `for i in $(seq 1 20); do date -u +sample=%Y-%m-%dT%H:%M:%SZ; docker-compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch stats --no-stream | awk 'NR==1 || /ccdash-worker-watch-1|ccdash-postgres-1/'; sleep 30; done`
- Window: `2026-05-05T03:08:09Z` through `2026-05-05T03:18:30Z`, 20 samples.
- `WATCHFILES_FORCE_POLLING=true` in `deploy/runtime/.env`.
- `worker-watch` CPU stayed sustained but bounded in the polling range, roughly `12.01%` to `22.30%`.
- `worker-watch` RSS rose from about `164 MiB` to about `267 MiB` early in the idle window, then remained flat near `266-269 MiB`; no monotonic growth across the full window.
- Postgres CPU was mostly `0.00-0.10%` after startup, with brief samples at `2.64-2.78%`; Postgres RSS dropped from about `353 MiB` to about `300 MiB`.
