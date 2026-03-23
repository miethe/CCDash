---
type: progress
schema_version: 2
doc_type: progress
prd: dependency-aware-execution-and-family-views-v1
feature_slug: dependency-aware-execution-and-family-views-v1
prd_ref: /docs/project_plans/PRDs/enhancements/dependency-aware-execution-and-family-views-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md
phase: 3
title: Shared UI Components
status: in-progress
started: '2026-03-23'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 3
completed_tasks: 0
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- frontend-developer
- ui-designer
contributors:
- codex
tasks:
- id: DEP-201
  description: Build a reusable badge that pairs text, iconography, and status for blocked, blocked_unknown, and unblocked states.
  status: in_progress
  assigned_to:
  - ui-engineer-enhanced
  - ui-designer
  dependencies:
  - DEP-101
  estimated_effort: 2pt
  priority: high
- id: DEP-202
  description: Build a compact list component that shows the first blocking feature, status, and view/open actions.
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - DEP-101
  - DEP-102
  estimated_effort: 2pt
  priority: high
- id: DEP-203
  description: Build ordered family lane and summary card components with current, next, done, blocked, and unsequenced states.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  - ui-designer
  dependencies:
  - DEP-102
  estimated_effort: 4pt
  priority: high
parallelization:
  batch_1:
  - DEP-201
  batch_2:
  - DEP-202
  - DEP-203
  critical_path:
  - DEP-201
  - DEP-203
  estimated_total_time: 8pt / 3-4 days
blockers: []
success_criteria:
- Shared components accept normalized backend payloads only.
- Blocked state is clear in text and structure, not icon-only.
- Family lanes remain readable on both desktop and narrow layouts.
files_modified:
- .claude/progress/dependency-aware-execution-and-family-views-v1/phase-3-progress.md
- components/DependencyStateBadge.tsx
- components/BlockingFeatureList.tsx
- components/FamilySequenceLane.tsx
- components/FamilySummaryCard.tsx
- components/ExecutionGateCard.tsx
- components/__tests__/
progress: 0
updated: '2026-03-23'
---

# dependency-aware-execution-and-family-views-v1 - Phase 3

Use CLI to update progress:

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py --file .claude/progress/dependency-aware-execution-and-family-views-v1/phase-3-progress.md --task DEP-201 --status completed
```

## Objective

Introduce the reusable dependency and family UI primitives that all execution-aware surfaces will share.

## Completion Notes

- Pending.
