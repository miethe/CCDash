---
type: progress
schema_version: 2
doc_type: progress
prd: enterprise-live-session-ingest-v1
feature_slug: enterprise-live-session-ingest-v1
prd_ref: /docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/enterprise-live-session-ingest-v1.md
phase: 2
title: Compose and Operator Contract
status: in_progress
started: '2026-05-01'
completed:
commit_refs:
- 6f921ff
pr_refs: []
overall_progress: 33
completion_estimate: pending
total_tasks: 4
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- DevOps
- python-backend-engineer
- documentation-writer
contributors:
- codex
tasks:
- id: OPS-001
  description: Add a `worker-watch` compose service/profile using the backend image, existing Postgres env, project binding, and read-only ingest mounts.
  status: completed
  assigned_to:
  - DevOps
  - python-backend-engineer
  dependencies:
  - RUN-001
  estimated_effort: 2pt
  priority: high
- id: OPS-002
  description: Add env vars for watcher worker project id, probe port, and optional `WATCHFILES_FORCE_POLLING`.
  status: pending
  assigned_to:
  - DevOps
  - documentation-writer
  dependencies:
  - OPS-001
  estimated_effort: 1pt
  priority: medium
- id: OPS-003
  description: Document required mounts for `projects.json`, workspace root, `.claude`, and `.codex`.
  status: pending
  assigned_to:
  - documentation-writer
  dependencies:
  - OPS-001
  estimated_effort: 1pt
  priority: medium
- id: OPS-004
  description: Decide whether `worker-watch` replaces `worker` locally or co-runs with a unique probe port.
  status: pending
  assigned_to:
  - DevOps
  dependencies:
  - OPS-001
  estimated_effort: 2pt
  priority: high
parallelization:
  batch_1:
  - OPS-001
  batch_2:
  - OPS-002
  - OPS-003
  - OPS-004
  critical_path:
  - OPS-001
  - OPS-004
  estimated_total_time: 6pt / 1-2 days
blockers: []
success_criteria:
- `docker compose config` validates.
- Operator can run API + frontend + Postgres + watcher worker.
- Health endpoints are reachable for each worker role.
files_modified:
- deploy/runtime/compose.yaml
progress: 33
updated: '2026-05-01'
---

# enterprise-live-session-ingest-v1 - Phase 2

## Objective

Make watcher-capable enterprise workers runnable and understandable for local/shared-host operators.

## Status

`OPS-001` added a `worker-watch` compose service under the `live-watch` profile with a separate probe port from the default worker. Static YAML validation passed; Docker compose validation is blocked in this environment because `docker` is not installed on PATH.
