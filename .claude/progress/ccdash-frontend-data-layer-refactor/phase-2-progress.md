---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 2
title: Remaining Entity Domains
status: not_started
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs: []
pr_refs: []
owners:
- ui-engineer-enhanced
contributors:
- frontend-developer
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 11
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T2-001
  description: useDocumentsQuery hook (useInfiniteQuery, page size 500, MAX_DOCUMENTS_IN_MEMORY cap via select transform)
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-006
- id: T2-002
  description: Migrate document consumers (PlanCatalog, TrackerIntakePanel, ArtifactDrillDownPage, PlanningGraphPanel, PlanningNodeDetail, FeatureExecutionWorkbench, DocumentModal)
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-001
- id: T2-003
  description: useTasksQuery hook (paginated, page 100); remove limit=5000 from apiClient.getTasks; port OpsPanel to paginated shape
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-006
- id: T2-004
  description: useFeaturesQuery hook (paginated, GET /api/v1/features?view=cards&page=N); remove limit=5000 from apiClient.getFeatures; ProjectBoard legacy path paginated
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-006
- id: T2-005
  description: useAlertsQuery + useNotificationsQuery hooks; port 30s polling from AppRuntimeContext to refetchInterval on each query
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-006
- id: T2-006
  description: useProjectsQuery hook (staleTime 300_000); AppSessionContext retains activeProject client-state
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-006
- id: T2-007
  description: Migrate alerts, notifications, projects consumers (Settings.tsx, Layout.tsx, ProjectSelector.tsx); update useData() shims
  status: pending
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-005
  - T2-006
- id: T2-008
  description: Extend noHandRolledCache guardrail to assert absence of new Map()+TTL and limit=5000 in all 6 domain hook files
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-007
- id: T2-009
  description: Seam task — verify useData() facade shape for all 6 migrated domains; run dataArchitecture.test.ts; cross-owner seam (ui-engineer-enhanced + frontend-developer)
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-007
- id: T2-010
  description: Runtime smoke PlanCatalog + ProjectBoard; verify no limit=5000 in network; paginated features; alerts visible
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-008
  - T2-009
- id: T2-011
  description: task-completion-validator gate (P2)
  status: pending
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-010
parallelization:
  batch_1:
  - T2-001
  - T2-003
  - T2-004
  - T2-005
  - T2-006
  batch_2:
  - T2-002
  - T2-007
  batch_3:
  - T2-008
  - T2-009
  batch_4:
  - T2-010
  batch_5:
  - T2-011
  critical_path:
  - T2-004
  - T2-002
  - T2-009
  - T2-010
  - T2-011
blockers: []
success_criteria:
- id: SC-2.1
  description: 6 domain query hook files created in services/queries/
  status: pending
- id: SC-2.2
  description: limit=5000 removed from apiClient.ts methods (lines 401, 413); tasks + features paginated
  status: pending
- id: SC-2.3
  description: OpsPanel and Settings updated for paginated task/feature shape
  status: pending
- id: SC-2.4
  description: useData() facade shim returns all 6 domain arrays from TQ cache (seam T2-009 verified)
  status: pending
- id: SC-2.5
  description: noHandRolledCache.test.ts guardrail green for all 6 domain hook files; limit=5000 absent
  status: pending
- id: SC-2.6
  description: Runtime smoke PlanCatalog + ProjectBoard render without regression
  status: pending
- id: SC-2.7
  description: task-completion-validator sign-off
  status: pending
files_modified:
- services/queries/documents.ts
- services/queries/tasks.ts
- services/queries/features.ts
- services/queries/alerts.ts
- services/queries/notifications.ts
- services/queries/projects.ts
- services/apiClient.ts
- contexts/AppEntityDataContext.tsx
- components/PlanCatalog.tsx
- components/ProjectBoard.tsx
- components/OpsPanel.tsx
- components/Settings.tsx
- components/Layout.tsx
- components/Planning/TrackerIntakePanel.tsx
- components/Planning/ArtifactDrillDownPage.tsx
- components/Planning/PlanningGraphPanel.tsx
- components/Planning/PlanningNodeDetail.tsx
- components/FeatureExecutionWorkbench.tsx
- services/__tests__/noHandRolledCache.test.ts
---

# CCDash Frontend Data Layer Refactor - Phase 2: Remaining Entity Domains

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-2-progress.md \
  -t T2-001 -s completed
```

---

## Objective

Migrate documents, tasks, features, alerts, notifications, and projects to TQ hooks. Two parallel batches: Batch A (ui-engineer-enhanced: docs/tasks/features) and Batch B (frontend-developer: alerts/notifications/projects). Tasks and features must move off `limit=5000`. Seam task T2-009 verifies cross-owner facade contract.
