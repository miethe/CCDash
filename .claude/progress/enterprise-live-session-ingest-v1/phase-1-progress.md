---
type: progress
schema_version: 2
doc_type: progress
prd: enterprise-live-session-ingest-v1
feature_slug: enterprise-live-session-ingest-v1
prd_ref: /docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/enterprise-live-session-ingest-v1.md
phase: 1
title: Runtime Capability Model
status: in_progress
started: '2026-05-01'
completed:
commit_refs: []
pr_refs: []
overall_progress: 25
completion_estimate: pending
total_tasks: 4
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
contributors:
- codex
tasks:
- id: RUN-001
  description: Add an explicit `worker-watch` runtime profile or equivalent role.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies: []
  estimated_effort: 2pt
  priority: high
- id: RUN-002
  description: Extend runtime storage contract/readiness semantics for watcher worker.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - RUN-001
  estimated_effort: 2pt
  priority: high
- id: RUN-003
  description: Ensure bootstrap starts the file watcher only for watcher-capable profiles.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - RUN-001
  estimated_effort: 2pt
  priority: high
- id: RUN-004
  description: Add tests covering profile capabilities and watcher startup gating.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - RUN-003
  estimated_effort: 1pt
  priority: high
parallelization:
  batch_1:
  - RUN-001
  batch_2:
  - RUN-002
  - RUN-003
  batch_3:
  - RUN-004
  critical_path:
  - RUN-001
  - RUN-003
  - RUN-004
  estimated_total_time: 7pt / 2-3 days
blockers: []
success_criteria:
- Runtime profile matrix is explicit.
- API remains stateless/background-free.
- Existing local runtime behavior is unchanged.
files_modified:
- .claude/progress/enterprise-live-session-ingest-v1/phase-1-progress.md
progress: 25
updated: '2026-05-01'
---

# enterprise-live-session-ingest-v1 - Phase 1

## Objective

Add an explicit watcher-capable enterprise worker role while preserving no-watch behavior for `api` and the default `worker`.
