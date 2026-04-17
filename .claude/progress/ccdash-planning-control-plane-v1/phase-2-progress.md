---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 2
title: Planning APIs and Live Update Contracts
status: in_progress
created: '2026-04-16'
updated: '2026-04-16'
started: '2026-04-16'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: 3-4 days
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
  - backend-architect
  - python-backend-engineer
  - frontend-developer
contributors:
  - ai-agents
tasks:
  - id: PCP-201
    description: Add a transport-neutral planning query layer for planning home, graph detail, feature planning context, and phase operations under the existing agent-query/service pattern.
    status: pending
    assigned_to:
      - backend-architect
      - python-backend-engineer
    dependencies:
      - PCP-105
    estimated_effort: 3 pts
    priority: high
  - id: PCP-202
    description: Add or extend API endpoints for planning summary, graph/detail, feature planning context, and phase operations.
    status: pending
    assigned_to:
      - python-backend-engineer
    dependencies:
      - PCP-201
    estimated_effort: 2 pts
    priority: high
  - id: PCP-203
    description: Add project and feature planning invalidation topics, plus any phase/worktree topics needed for V1.
    status: pending
    assigned_to:
      - python-backend-engineer
    dependencies:
      - PCP-201
    estimated_effort: 2 pts
    priority: high
  - id: PCP-204
    description: Add frontend types and API helpers for planning payloads and live subscriptions.
    status: pending
    assigned_to:
      - frontend-developer
    dependencies:
      - PCP-202
      - PCP-203
    estimated_effort: 1 pt
    priority: high
parallelization:
  batch_1:
    - PCP-201
  batch_2:
    - PCP-202
    - PCP-203
  batch_3:
    - PCP-204
  critical_path:
    - PCP-201
    - PCP-202
    - PCP-204
  estimated_total_time: 8 pts / 3-4 days
blockers: []
notes:
  - Phase 1 landed the derived planning graph, effective status, and phase batch model in `backend/services/feature_execution.py` / `backend/models.py` / `types.ts`; Phase 2 exposes that via stable APIs and live topics.
  - Commits land per batch as requested ("commit in batches").
success_criteria:
  - id: SC-2.1
    description: Planning surfaces can bootstrap from stable APIs and remain fresh via live invalidation.
    status: pending
  - id: SC-2.2
    description: Routers stay thin and the aggregation logic remains service-owned.
    status: pending
  - id: SC-2.3
    description: No view needs to re-derive planning graph or mismatch logic from raw frontmatter.
    status: pending
files_modified: []
---

# ccdash-planning-control-plane-v1 - Phase 2

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Objective

Expose stable planning-focused APIs for summary, graph, feature drill-down, and phase operations, and add planning live-update topics that align with existing SSE infrastructure. Keep the contract transport-neutral for REST/CLI/MCP reuse.

## Orchestration Quick Reference

```bash
# Batch 1
Task("backend-architect", "Execute PCP-201: planning query service in backend/application/services/agent_queries/")

# Batch 2 (parallel after PCP-201)
Task("python-backend-engineer", "Execute PCP-202: REST planning endpoints in backend/routers/")
Task("python-backend-engineer", "Execute PCP-203: planning live topics + invalidation wiring")

# Batch 3 (after PCP-202 + PCP-203)
Task("frontend-developer", "Execute PCP-204: shared types + API/live helpers on the frontend")
```
