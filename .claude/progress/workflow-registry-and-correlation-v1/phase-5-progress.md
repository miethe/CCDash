---
type: progress
schema_version: 2
doc_type: progress
prd: workflow-registry-and-correlation-v1
feature_slug: workflow-registry-and-correlation-v1
prd_ref: /docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
phase: 5
title: New Workflow page and navigation
status: completed
started: '2026-03-14'
completed: '2026-03-14'
commit_refs:
- 8964e3c
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- codex
tasks:
- id: UI-5.1
  description: Add the Workflow route variants and sidebar navigation entry with active-state handling.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies: []
  estimated_effort: 1h
  priority: high
- id: UI-5.2
  description: Add a workflow registry frontend service for list/detail loading and API error normalization.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies: []
  estimated_effort: 1h
  priority: high
- id: UI-5.3
  description: Build the workflow catalog pane with search, correlation filters, keyboard navigation, and responsive states.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - UI-5.1
  - UI-5.2
  estimated_effort: 3h
  priority: high
- id: UI-5.4
  description: Build the workflow detail panel with identity, composition, effectiveness, issues, and actions sections.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - UI-5.2
  estimated_effort: 3h
  priority: high
- id: UI-5.5
  description: Finish the master-detail responsive shell, empty/loading/disabled states, and deep-link selection handling.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - UI-5.3
  - UI-5.4
  estimated_effort: 2h
  priority: high
parallelization:
  batch_1:
  - UI-5.1
  - UI-5.2
  batch_2:
  - UI-5.3
  - UI-5.4
  batch_3:
  - UI-5.5
  critical_path:
  - UI-5.2
  - UI-5.4
  - UI-5.5
  estimated_total_time: 7h
blockers: []
success_criteria:
- The app exposes a dedicated `/workflows` route with deep-linkable workflow detail selection.
- Users can browse workflow entities from a dedicated page without visiting analytics or execution first.
- The catalog and detail layout remains usable across stacked, drawer, and side-by-side breakpoints.
- Correlation state, composition, effectiveness, issues, and actions are visually clear using existing CCDash design patterns.
files_modified:
- .claude/progress/workflow-registry-and-correlation-v1/phase-5-progress.md
- App.tsx
- components/Layout.tsx
- components/Workflows/WorkflowRegistryPage.tsx
- components/Workflows/catalog/WorkflowCatalog.tsx
- components/Workflows/catalog/CatalogFilterBar.tsx
- components/Workflows/catalog/WorkflowListItem.tsx
- components/Workflows/detail/ActionsRow.tsx
- components/Workflows/detail/CompositionSection.tsx
- components/Workflows/detail/DetailIdentityHeader.tsx
- components/Workflows/detail/EffectivenessSection.tsx
- components/Workflows/detail/IssuesSection.tsx
- components/Workflows/detail/WorkflowDetailPanel.tsx
- components/Workflows/workflowRegistryUtils.ts
- services/workflows.ts
progress: 100
updated: '2026-03-14'
---

# Workflow Registry - Phase 5: New Workflow page and navigation

YAML frontmatter is the source of truth for status, task state, and validation notes.
