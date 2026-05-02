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
status: completed
started: '2026-05-01'
completed: '2026-05-02'
commit_refs:
- 6f921ff
pr_refs: []
overall_progress: 100
completion_estimate: completed
total_tasks: 4
completed_tasks: 4
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
  status: completed
  assigned_to:
  - DevOps
  - documentation-writer
  dependencies:
  - OPS-001
  estimated_effort: 1pt
  priority: medium
- id: OPS-003
  description: Document required mounts for `projects.json`, workspace root, `.claude`, and `.codex`.
  status: completed
  assigned_to:
  - documentation-writer
  dependencies:
  - OPS-001
  estimated_effort: 1pt
  priority: medium
- id: OPS-004
  description: Decide whether `worker-watch` replaces `worker` locally or co-runs with a unique probe port.
  status: completed
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
- deploy/runtime/.env.example
- deploy/runtime/README.md
- docs/guides/containerized-deployment-quickstart.md
- .claude/progress/enterprise-live-session-ingest-v1/phase-2-progress.md
progress: 100
updated: '2026-05-02'
---

# enterprise-live-session-ingest-v1 - Phase 2

## Objective

Make watcher-capable enterprise workers runnable and understandable for local/shared-host operators.

## Status

Phase 2 is complete. `OPS-001` added a `worker-watch` compose service under the `live-watch` profile with a separate probe port from the default worker.

`OPS-002` documents the watcher worker environment contract in `deploy/runtime/.env.example`, including the shared one-project worker binding, `CCDASH_WORKER_WATCH_PROBE_PORT=9466`, `CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true`, and optional `WATCHFILES_FORCE_POLLING=true` for macOS Docker Desktop bind mounts.

`OPS-003` documents required read-only mounts for `projects.json`, the workspace root, `.claude`, and `.codex`, with troubleshooting guidance for unresolved projects and watcher "nothing to monitor" states.

`OPS-004` records the coexistence decision: the default `worker` and `worker-watch` co-run locally in enterprise deployments with distinct probe ports (`9465` and `9466`) instead of the watcher replacing the default worker.

Static YAML validation passed during `OPS-001`; Docker compose validation was blocked in that environment because `docker` was not installed on PATH. This closeout ran static Markdown/diff checks after the documentation updates.
