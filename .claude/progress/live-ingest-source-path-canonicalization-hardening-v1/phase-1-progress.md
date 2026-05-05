---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 1
phase_title: Source Identity Contract
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 1: Source Identity Contract'
status: in_progress
started: '2026-05-04'
completed: null
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: task-scoped
overall_progress: 67
completion_estimate: on-track
total_tasks: 3
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- data-layer-expert
contributors:
- codex
tasks:
- id: SRC-001
  description: Define a single source identity contract for filesystem-derived session, document, progress, and test files.
  status: completed
  assigned_to:
  - backend-architect
  - data-layer-expert
  dependencies: []
  estimated_effort: 1 pt
  priority: high
- id: SRC-002
  description: Add a helper that maps host and container aliases to a stable source key before repository lookup/write.
  status: completed
  assigned_to:
  - backend-architect
  - data-layer-expert
  dependencies:
  - SRC-001
  estimated_effort: 2 pts
  priority: high
- id: SRC-003
  description: Cover symlinks, non-mounted paths, optional mount slots, unrelated projects, and paths outside known roots.
  status: pending
  assigned_to:
  - backend-architect
  - data-layer-expert
  dependencies:
  - SRC-002
  estimated_effort: 1 pt
  priority: high
parallelization:
  batch_1:
  - SRC-001
  batch_2:
  - SRC-002
  batch_3:
  - SRC-003
  critical_path:
  - SRC-001
  - SRC-002
  - SRC-003
blockers: []
success_criteria:
- Contract document or code comments identify canonical inputs, outputs, collision behavior, and rollout constraints.
- Canonicalization is deterministic and side-effect free.
- The helper does not require a live container runtime.
files_modified:
- backend/services/source_identity.py
- backend/tests/test_source_identity.py
- .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-1-progress.md
- .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-2-progress.md
- docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
progress: 67
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 1

## Objective

Define the canonical filesystem source identity contract before implementing alias resolution or ingest write-boundary changes.

## Current Status

`SRC-001` and `SRC-002` are complete. `SRC-003` remains pending and no sync engine wiring has been added.
