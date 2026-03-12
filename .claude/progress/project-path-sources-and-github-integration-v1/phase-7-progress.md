---
type: progress
schema_version: 2
doc_type: progress
prd: project-path-sources-and-github-integration-v1
feature_slug: project-path-sources-and-github-integration-v1
prd_ref: /docs/project_plans/PRDs/enhancements/project-path-sources-and-github-integration-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
phase: 7
title: Validation, tests, and rollout hardening
status: completed
started: '2026-03-12'
completed: '2026-03-12'
commit_refs:
- '06e217c'
- 1447dd0
pr_refs: []
overall_progress: 0
completion_estimate: completed
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- code-reviewer
- task-completion-validator
- frontend-developer
- python-backend-engineer
contributors:
- codex
tasks:
- id: PPG-33
  description: Add backend unit and router tests for document updates, GitHub gating, and managed repo write behavior.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PPG-28
  - PPG-29
  estimated_effort: 3pt
  priority: high
- id: PPG-34
  description: Add frontend tests for typed path helper behavior and document-editing support where practical.
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - PPG-24
  - PPG-32
  estimated_effort: 2pt
  priority: medium
- id: PPG-35
  description: Execute manual QA for local-only projects, repo-backed paths, and write-enabled plan-document flows.
  status: completed
  assigned_to:
  - task-completion-validator
  dependencies:
  - PPG-27
  - PPG-32
  estimated_effort: 2pt
  priority: high
- id: PPG-36
  description: Document rollout caveats and remaining unrelated repo-wide quality-gate debt.
  status: completed
  assigned_to:
  - code-reviewer
  dependencies:
  - PPG-33
  - PPG-34
  - PPG-35
  estimated_effort: 1pt
  priority: medium
parallelization:
  batch_1:
  - PPG-33
  - PPG-34
  batch_2:
  - PPG-35
  batch_3:
  - PPG-36
  critical_path:
  - PPG-33
  - PPG-35
  - PPG-36
  estimated_total_time: 8pt / ~3 days
blockers:
- Full `pnpm typecheck` still fails on pre-existing files outside this feature scope (`components/TranscriptMappedMessageCard.tsx`, `constants.ts`, and `contexts/DataContext.tsx`).
success_criteria:
- Local-only project configuration remains stable.
- Repo-backed paths resolve and sync successfully in supported scenarios.
- GitHub write support stays disabled unless fully configured.
files_modified:
- /backend/tests/test_documents_router.py
- /services/__tests__/projectPaths.test.ts
- /docs/project_plans/implementation_plans/enhancements/project-path-sources-and-github-integration-v1.md
progress: 100
updated: '2026-03-12'
---

# project-path-sources-and-github-integration-v1 - Phase 7
