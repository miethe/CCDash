---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-theme-system-foundation-v1
feature_slug: ccdash-theme-system-foundation-v1
prd_ref: /docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md
plan_ref: /docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
phase: 5
title: Feature surface migration waves
status: in_progress
started: '2026-03-20'
completed: ''
commit_refs:
- 43bdf87
pr_refs: []
overall_progress: 67
completion_estimate: in_progress
total_tasks: 3
completed_tasks: 2
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
- codebase-janitor
contributors:
- codex
tasks:
- id: THEME-401
  description: Migrate Dashboard, analytics shells, and shared metric cards to semantic surfaces and chart adapter usage.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - THEME-202
  estimated_effort: 4pt
  priority: high
- id: THEME-402
  description: Migrate test-visualizer and workflow registry surfaces to semantic primitives and status variants.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - THEME-201
  estimated_effort: 4pt
  priority: high
- id: THEME-403
  description: Migrate the most styling-dense monolithic pages in staged slices using semantic shells and shared surface patterns.
  status: in_progress
  assigned_to:
  - codebase-janitor
  - frontend-developer
  dependencies:
  - THEME-401
  estimated_effort: 6pt
  priority: high
parallelization:
  batch_1:
  - THEME-401
  - THEME-402
  batch_2:
  - THEME-403
notes:
- Phase 5 is being executed as three migration waves with commits after each completed wave.
- THEME-403 will focus on the highest-leverage semantic shell and repeated surface substitutions first to reduce regression risk in monolithic pages.
---
