---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 5
phase_title: Performance Validation Gate
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 5: Performance Validation Gate'
status: completed
started: '2026-05-05'
completed: '2026-05-05'
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: task-scoped
overall_progress: 100
completion_estimate: complete
total_tasks: 4
completed_tasks: 4
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
  status: completed
  assigned_to:
  - performance-engineer
  dependencies:
  - VAL-001
  estimated_effort: 1 pt
  priority: high
- id: VAL-004
  description: Run focused backend tests for watcher, runtime bootstrap, fanout, sync writes, canonicalization, and migration coverage.
  status: completed
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
progress: 100
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

## VAL-003 Evidence

- Before second restart table stats:
  - `session_messages n_tup_ins=926289 n_tup_del=495089`
  - `session_usage_attributions n_tup_ins=3058160 n_tup_del=1484582`
  - `sessions n_tup_ins=9003 n_tup_del=2072`
  - `sync_state n_tup_ins=14382 n_tup_del=37`
  - `telemetry_events n_tup_ins=1488890 n_tup_del=794202`
- Immediately after second startup, the same table counters were unchanged.
- After the 10-minute idle window, the same table counters were still unchanged.
- `worker-watch /detailz` remained `ready=pass`, `startupSync=succeeded`, backlog `0`, publisher `published=11`, `publishErrors=0`.

## VAL-004 Evidence

- Combined command attempted: `python -m pytest backend/tests/test_file_watcher.py backend/tests/test_runtime_bootstrap.py backend/tests/test_postgres_live_fanout.py backend/tests/test_sync_engine_linking.py backend/tests/test_sync_engine_transcript_live_updates.py backend/tests/test_source_identity.py backend/tests/test_source_alias_duplicate_audit.py -q`.
- Combined command failed before test execution with a Python 3.12 segmentation fault during import/collection.
- Split focused passes:
  - `python -m pytest backend/tests/test_file_watcher.py backend/tests/test_source_identity.py backend/tests/test_source_alias_duplicate_audit.py backend/tests/test_sync_engine_linking.py -q` -> 42 passed.
  - `python -m pytest backend/tests/test_postgres_live_fanout.py -q` -> 11 passed.
  - `python -m pytest backend/tests/test_sync_engine_transcript_live_updates.py -q` -> 2 passed.
- Runtime bootstrap caveat:
  - `python -m pytest backend/tests/test_runtime_bootstrap.py -q` segfaulted during pytest collection.
  - `PYTEST_ADDOPTS=--assert=plain python -m pytest backend/tests/test_runtime_bootstrap.py -q` also segfaulted during collection/import.
  - `python -m py_compile backend/tests/test_runtime_bootstrap.py` exited with code `-1`, while `python -m py_compile backend/runtime/container.py backend/runtime_ports.py` passed.
- Result: 55 focused tests passed; the runtime bootstrap test file remains an environment/import caveat rather than evidence of a runtime regression.
