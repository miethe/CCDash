---
type: progress
schema_version: 2
doc_type: progress
prd: branch-aware-planning-intelligence
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
execution_model: sequential
phase: 1
title: Backend Query / DTO Exposure
status: completed
started: null
completed: null
created: '2026-06-04'
updated: '2026-06-04'
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
contributors:
- data-layer-expert
tasks:
- id: T1-001
  title: Add git_branch to PlanningAgentSessionCardDTO
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  batch: batch_1
  depends_on: []
  estimated_effort: 1 pt
  started: '2026-06-04T14:07:20-04:00'
  completed: '2026-06-04T14:07:20-04:00'
  evidence:
  - commit: 92c98d3
  verified_by:
  - T4-002
- id: T1-002
  title: Add activeSessions to PlanningCommandCenterItemDTO
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  batch: batch_2
  depends_on:
  - T1-001
  estimated_effort: 1.5 pts
  started: '2026-06-04T14:12:12-04:00'
  completed: '2026-06-04T14:12:12-04:00'
  evidence:
  - commit: 55a232a
  verified_by:
  - T4-002
- id: T1-003
  title: Add commit_refs / pr_refs to FeatureSummaryItem
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  model_effort: adaptive
  batch: batch_3
  depends_on:
  - T1-002
  estimated_effort: 1 pt
  started: '2026-06-04T14:14:47-04:00'
  completed: '2026-06-04T14:14:47-04:00'
  evidence:
  - commit: 6a5097f
  verified_by:
  - T4-002
- id: T1-004
  title: Add linked_sessions_by_phase to PhaseContextItem + DB index
  status: completed
  assigned_to:
  - python-backend-engineer
  - data-layer-expert
  assigned_model: sonnet
  model_effort: adaptive
  batch: batch_4
  depends_on:
  - T1-003
  estimated_effort: 1.5 pts
  started: '2026-06-04T14:21:43-04:00'
  completed: '2026-06-04T14:21:43-04:00'
  evidence:
  - commit: 22bd18b
  verified_by:
  - T4-002
parallelization:
  batch_1:
  - T1-001
  batch_2:
  - T1-002
  batch_3:
  - T1-003
  batch_4:
  - T1-004
  critical_path:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  estimated_total_time: ~2 days
blockers: []
success_criteria:
- All four DTO types updated with new fields; new fields optional/nullable
- Unit tests pass for all new service-layer methods against seeded fixtures
- ttl=30 applied to both planning-board endpoint service methods (pcc_command_center,
  pss_session_board)
- DB index migration adds sessions(git_branch, project_id) with IF NOT EXISTS guard;
  no column modifications
- Transport-neutral pattern respected (agent_queries layer only; no router code in
  this phase)
- task-completion-validator signs off
files_modified:
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/planning_sessions.py
- backend/application/services/agent_queries/planning_command_center.py
- backend/application/services/agent_queries/planning.py
- backend/db/repositories/feature_sessions.py
- backend/db/sqlite_migrations.py
progress: 100
---

# branch-aware-planning-intelligence — Phase 1: Backend Query / DTO Exposure

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

## Summary

Extends four DTOs in the transport-neutral agent_queries layer with branch, session,
commit, and phase-link data. Also adds a DB index on `sessions(git_branch, project_id)`
and applies `ttl=30` TTL overrides to the two planning-board service methods.
All tasks share `models.py` as a serialization barrier — serialized into four batches.

## Task Checklist

| ID | Name | Status |
|----|------|--------|
| T1-001 | Add `git_branch` to `PlanningAgentSessionCardDTO` | pending |
| T1-002 | Add `activeSessions` to `PlanningCommandCenterItemDTO` | pending |
| T1-003 | Add `commit_refs` / `pr_refs` to `FeatureSummaryItem` | pending |
| T1-004 | Add `linked_sessions_by_phase` to `PhaseContextItem` + DB index | pending |

## Batch Execution Order

| Batch | Tasks | Rationale |
|-------|-------|-----------|
| batch_1 | T1-001 | models.py baseline — must land first |
| batch_2 | T1-002 | depends on T1-001 (shared models.py) |
| batch_3 | T1-003 | depends on T1-002 (shared models.py) |
| batch_4 | T1-004 | depends on T1-003 (shared models.py + DB migration) |

## Phase 1 Quality Gates

- [ ] All four DTO types updated with new fields; new fields optional/nullable
- [ ] Unit tests pass for all new service-layer methods against seeded fixtures
- [ ] `ttl=30` applied to both planning-board endpoint service methods (`pcc_command_center`, `pss_session_board`)
- [ ] DB index migration adds `sessions(git_branch, project_id)` with `IF NOT EXISTS` guard; no column modifications
- [ ] Transport-neutral pattern respected (agent_queries layer only; no router code in this phase)
- [ ] task-completion-validator signs off
