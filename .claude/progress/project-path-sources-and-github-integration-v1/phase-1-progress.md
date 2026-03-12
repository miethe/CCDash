---
type: progress
schema_version: 2
doc_type: progress
prd: project-path-sources-and-github-integration-v1
feature_slug: project-path-sources-and-github-integration-v1
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 1
title: Domain model and migration scaffolding
status: completed
started: '2026-03-12'
completed: ''
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: in_progress
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
contributors:
- codex
tasks:
- id: PPG-1
  description: Extend backend models with typed project path references, GitHub repo
    refs, and GitHub integration settings models.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies: []
  estimated_effort: 2pt
  priority: high
- id: PPG-2
  description: Extend frontend shared types with the matching project path and GitHub
    integration contracts.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - PPG-1
  estimated_effort: 1pt
  priority: high
- id: PPG-3
  description: Add compatibility migration helpers in ProjectManager for legacy project
    records.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PPG-1
  estimated_effort: 2pt
  priority: high
- id: PPG-4
  description: Choose and scaffold GitHub integration settings persistence outside
    project records.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - PPG-1
  estimated_effort: 1pt
  priority: high
- id: PPG-5
  description: Preserve derivable legacy path fields until downstream consumers migrate.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PPG-1
  - PPG-3
  estimated_effort: 1pt
  priority: high
parallelization:
  batch_1:
  - PPG-1
  batch_2:
  - PPG-2
  - PPG-3
  - PPG-4
  batch_3:
  - PPG-5
  critical_path:
  - PPG-1
  - PPG-3
  - PPG-5
  estimated_total_time: 7pt / ~3 days
blockers: []
success_criteria:
- Existing projects still load without modification.
- New project config can represent project_root, filesystem, and github_repo sources.
- Invalid path-source combinations are rejected during validation.
files_modified: []
progress: 100
updated: '2026-03-12'
---

# project-path-sources-and-github-integration-v1 - Phase 1
