---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 2
phase_title: Ingest Path Canonicalization
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 2: Ingest Path Canonicalization'
status: completed
started: '2026-05-04'
completed: '2026-05-04'
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs:
- 9196922
- 7e57c7f
- 0577e4c
- f0c106a
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
- python-backend-engineer
- data-layer-expert
contributors: []
tasks:
- id: ING-001
  description: Update sync state lookup, upsert, and delete usage sites so startup sync checks canonical source identity before deciding a file is new.
  status: completed
  assigned_to:
  - python-backend-engineer
  - data-layer-expert
  dependencies:
  - SRC-002
  estimated_effort: 2 pts
  priority: high
- id: ING-002
  description: Normalize sessions.source_file at write boundaries or add an explicit canonical source column while preserving display/debug compatibility.
  status: completed
  assigned_to:
  - python-backend-engineer
  - data-layer-expert
  dependencies:
  - SRC-002
  estimated_effort: 2 pts
  priority: high
- id: ING-003
  description: Ensure delete/replace boundaries do not duplicate rows when the same physical file appears through an alias path.
  status: completed
  assigned_to:
  - python-backend-engineer
  - data-layer-expert
  dependencies:
  - ING-001
  - ING-002
  estimated_effort: 2 pts
  priority: high
- id: ING-004
  description: Confirm publish counts reflect real changed sessions, not alias re-ingestion.
  status: completed
  assigned_to:
  - python-backend-engineer
  - data-layer-expert
  dependencies:
  - ING-003
  estimated_effort: 1 pt
  priority: high
parallelization:
  batch_1:
  - ING-001
  - ING-002
  batch_2:
  - ING-003
  batch_3:
  - ING-004
  critical_path:
  - SRC-002
  - ING-001
  - ING-003
  - ING-004
blockers: []
success_criteria:
- A second startup under container paths skips files already synced under host paths when content/mtime is unchanged.
- Existing local SQLite tests still pass.
- Existing Postgres repository tests still pass.
files_modified:
- backend/db/sync_engine.py
- backend/tests/test_file_watcher.py
- backend/tests/test_sync_engine_linking.py
- .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-2-progress.md
progress: 100
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 2

## Objective

Apply canonical source keys at ingest lookup/write/delete boundaries after the Phase 1 helper contract is implemented.

## Current Status

Phase 2 is complete. Alias-path unchanged sessions skip parsing and live fanout when canonical sync state and lineage are already current.
