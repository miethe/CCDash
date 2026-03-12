---
type: progress
schema_version: 2
doc_type: progress
prd: project-path-sources-and-github-integration-v1
feature_slug: project-path-sources-and-github-integration-v1
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 5
title: Settings UI restructure and per-field editors
status: completed
started: '2026-03-12'
completed: '2026-03-12'
commit_refs:
- 5aa509b
pr_refs: []
overall_progress: 0
completion_estimate: completed
total_tasks: 7
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- codex
tasks:
- id: PPG-21
  description: Add a top-level integrations tab in Settings.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - PPG-20
  estimated_effort: 1pt
  priority: high
- id: PPG-22
  description: Add nested SkillMeat and GitHub sub-tabs under Integrations.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - PPG-21
  estimated_effort: 1pt
  priority: high
- id: PPG-23
  description: Remove the embedded SkillMeat editor from the Project Settings pane.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - PPG-21
  estimated_effort: 1pt
  priority: high
- id: PPG-24
  description: Add per-field path-source selectors and source-aware inputs for root, plan docs, sessions, and progress.
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PPG-20
  estimated_effort: 3pt
  priority: high
- id: PPG-25
  description: Add GitHub URL helper text and effective-path preview states.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - PPG-24
  estimated_effort: 1pt
  priority: medium
- id: PPG-26
  description: Add validation and status badges for path resolution and GitHub auth.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - PPG-22
  - PPG-24
  estimated_effort: 2pt
  priority: high
- id: PPG-27
  description: Keep the default path editing flow simple for local-only users.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - PPG-24
  estimated_effort: 1pt
  priority: medium
parallelization:
  batch_1:
  - PPG-21
  - PPG-24
  batch_2:
  - PPG-22
  - PPG-23
  - PPG-25
  batch_3:
  - PPG-26
  - PPG-27
  critical_path:
  - PPG-24
  - PPG-26
  estimated_total_time: 10pt / ~4 days
blockers: []
success_criteria:
- Users can configure local-only projects without extra friction.
- Users can paste a GitHub repo/tree URL and see validation feedback.
- SkillMeat and GitHub settings are available from the new Integrations tab.
files_modified:
- /components/Settings.tsx
- /components/AddProjectModal.tsx
- /services/projectPaths.ts
- /services/githubIntegrations.ts
progress: 100
updated: '2026-03-12'
---

# project-path-sources-and-github-integration-v1 - Phase 5
