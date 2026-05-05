---
type: progress
schema_version: 2
doc_type: progress
feature_slug: live-ingest-source-path-canonicalization-hardening
phase: 4
phase_title: Runtime Guardrails And Operator Docs
title: 'live-ingest-source-path-canonicalization-hardening-v1 - Phase 4: Runtime Guardrails And Operator Docs'
status: completed
started: '2026-05-04'
completed: null
created: '2026-05-04'
updated: '2026-05-04'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
commit_refs: []
pr_refs: []
execution_model: task-scoped
overall_progress: 100
completion_estimate: complete
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- DevOps
- documentation-writer
contributors: []
tasks:
- id: OPS-001
  description: Document startup sync load versus idle polling load and explain WATCHFILES_FORCE_POLLING as a worker-watch compatibility fallback.
  status: completed
  assigned_to:
  - DevOps
  - documentation-writer
  dependencies: []
  estimated_effort: 1 pt
  priority: medium
- id: OPS-002
  description: Document host port 8000 conflict checks and safer stack validation through frontend proxy or container probes.
  status: completed
  assigned_to:
  - documentation-writer
  dependencies: []
  estimated_effort: 1 pt
  priority: medium
- id: OPS-003
  description: Document how sessionsPath, .claude, .codex, workspace roots, and optional mounts affect watch size and startup cost.
  status: completed
  assigned_to:
  - documentation-writer
  dependencies:
  - SRC-001
  estimated_effort: 1 pt
  priority: medium
parallelization:
  batch_1:
  - OPS-001
  - OPS-002
  batch_2:
  - OPS-003
  critical_path:
  - OPS-001
  - OPS-003
blockers: []
success_criteria:
- Runtime docs use docker-compose for this environment and do not assume standalone docker.
- Docs include expected CPU/RAM interpretation rather than only commands.
- Docs do not present polling mode as a default performance setting.
files_modified:
- deploy/runtime/README.md
- .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-4-progress.md
progress: 100
---

# live-ingest-source-path-canonicalization-hardening-v1 - Phase 4

## Objective

Add runtime operator guardrails for live-watch startup, polling fallback, port validation, and watch scope sizing.

## Current Status

Phase 4 is complete. Runtime docs now cover polling load, port conflict checks, and watch scope startup cost.
