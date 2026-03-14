---
type: progress
schema_version: 2
doc_type: progress
prd: workflow-registry-and-correlation-v1
feature_slug: workflow-registry-and-correlation-v1
prd_ref: /docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
phase: 6
title: Cross-surface integration and actions
status: planning
started: '2026-03-14'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- codex
tasks:
- id: INT-6.1
  description: Reuse existing action and artifact-reference patterns inside workflow detail interactions where helpful.
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  dependencies: []
  estimated_effort: 2h
  priority: high
- id: INT-6.2
  description: Wire workflow detail actions for SkillMeat definitions, executions, bundles, context memory, and representative sessions.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - INT-6.1
  estimated_effort: 2h
  priority: high
- id: INT-6.3
  description: Add workflow hub backlinks from analytics and execution surfaces.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies: []
  estimated_effort: 1h
  priority: medium
- id: INT-6.4
  description: Validate navigation flows, refine empty/error states, and record completion in tracking artifacts.
  status: pending
  assigned_to:
  - frontend-developer
  dependencies:
  - INT-6.2
  - INT-6.3
  estimated_effort: 1h
  priority: high
parallelization:
  batch_1:
  - INT-6.1
  - INT-6.3
  batch_2:
  - INT-6.2
  batch_3:
  - INT-6.4
  critical_path:
  - INT-6.1
  - INT-6.2
  - INT-6.4
  estimated_total_time: 4h
blockers: []
success_criteria:
- Workflow detail actions open the correct SkillMeat or CCDash destinations without dead-end buttons.
- Analytics and execution surfaces provide a clear path into the new workflow hub.
- Existing execution-page workflow intelligence behavior continues to work after integration changes.
files_modified:
- .claude/progress/workflow-registry-and-correlation-v1/phase-6-progress.md
- components/Analytics/AnalyticsDashboard.tsx
- components/FeatureExecutionWorkbench.tsx
- components/Workflows/detail/ActionsRow.tsx
- components/Workflows/detail/WorkflowDetailPanel.tsx
progress: 0
updated: '2026-03-14'
---

# Workflow Registry - Phase 6: Cross-surface integration and actions

YAML frontmatter is the source of truth for status, task state, and validation notes.
