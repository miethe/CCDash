---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 3
phase_title: Duplicate Migration And Backfill
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 3: Duplicate Migration And Backfill'
status: in-progress
started: '2026-05-04'
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
- data-layer-expert
- python-backend-engineer
contributors: []
tasks:
- id: MIG-001
  description: Add repeatable SQL or a CLI/admin script that reports host/container alias duplicates in sync_state, sessions, and derived tables.
  status: pending
  assigned_to:
  - data-layer-expert
  dependencies:
  - SRC-002
  estimated_effort: 1 pt
  priority: high
- id: MIG-002
  description: Define how to choose survivor rows and update or delete duplicate rows without losing newer mtime/hash data or canonical transcript rows.
  status: pending
  assigned_to:
  - data-layer-expert
  - python-backend-engineer
  dependencies:
  - MIG-001
  estimated_effort: 1 pt
  priority: high
- id: MIG-003
  description: Implement a project-scoped dry-run/apply command for duplicate source identity collapse.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - MIG-002
  estimated_effort: 2 pts
  priority: high
- id: MIG-004
  description: Verify table counts, live feature/session views, and source lookup behavior after cleanup.
  status: pending
  assigned_to:
  - task-completion-validator
  dependencies:
  - MIG-003
  estimated_effort: 1 pt
  priority: high
parallelization:
  batch_1:
  - MIG-001
  batch_2:
  - MIG-002
  batch_3:
  - MIG-003
  batch_4:
  - MIG-004
  critical_path:
  - MIG-001
  - MIG-002
  - MIG-003
  - MIG-004
blockers: []
success_criteria:
- The audit script reports duplicate alias counts and exits non-zero only on query failure.
- Migration requires an explicit project id and supports dry-run review before apply.
- Duplicate cleanup is restart-safe, idempotent, and preserves newer sync/session evidence.
files_modified: []
progress: 0
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 3

## Objective

Add project-scoped duplicate source identity audit and collapse tooling for host/container alias drift.

## Current Status

Phase 3 is in progress. Phases 1 and 2 completed the canonical identity helper and ingest write-boundary usage.
