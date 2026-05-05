---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 5
phase_title: Performance Validation Gate
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 5: Performance Validation Gate'
status: pending
started: null
completed: null
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: task-scoped
overall_progress: 0
completion_estimate: pending
total_tasks: 4
completed_tasks: 0
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
  status: pending
  assigned_to:
  - performance-engineer
  dependencies:
  - ING-004
  - MIG-004
  estimated_effort: 2 pts
  priority: high
- id: VAL-002
  description: Sample worker-watch CPU and memory every 30 seconds for 10 minutes after startup completes with no file changes.
  status: pending
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
files_modified: []
progress: 0
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 5

## Objective

Validate startup idempotence, idle resource behavior, Postgres churn, and regression coverage after phases 3 and 4 complete.

## Current Status

Phase 5 is pending until the migration/backfill tooling and operator guardrails are complete.
