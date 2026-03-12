---
type: progress
schema_version: 2
doc_type: progress
prd: project-path-sources-and-github-integration-v1
feature_slug: project-path-sources-and-github-integration-v1
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 4
title: Project API and active path consumption
status: completed
started: ''
completed: ''
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: pending
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- backend-architect
contributors:
- codex
tasks:
- id: PPG-16
  description: Update the project API to accept and return the new project-path config.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PPG-5
  estimated_effort: 1pt
  priority: high
- id: PPG-17
  description: Refactor ProjectManager.get_active_paths() behind a resolved-path bundle
    API.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PPG-6
  - PPG-10
  estimated_effort: 2pt
  priority: high
- id: PPG-18
  description: Update sync, parsers, document loading, and safe-path checks to consume
    resolved paths.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PPG-17
  estimated_effort: 3pt
  priority: high
- id: PPG-19
  description: Preserve defaults for local-only projects and the default example project.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - PPG-17
  estimated_effort: 1pt
  priority: medium
- id: PPG-20
  description: Add effective-path metadata for diagnostics where useful.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PPG-17
  - PPG-18
  estimated_effort: 1pt
  priority: medium
parallelization:
  batch_1:
  - PPG-16
  - PPG-17
  batch_2:
  - PPG-18
  - PPG-19
  batch_3:
  - PPG-20
  critical_path:
  - PPG-17
  - PPG-18
  - PPG-20
  estimated_total_time: 8pt / ~3 days
blockers: []
success_criteria:
- Legacy local projects behave the same after the refactor.
- GitHub-backed plan docs and progress paths are discoverable by existing workflows.
- No downstream consumer treats raw GitHub URLs as filesystem paths.
files_modified: []
progress: 100
updated: '2026-03-12'
---

# project-path-sources-and-github-integration-v1 - Phase 4
