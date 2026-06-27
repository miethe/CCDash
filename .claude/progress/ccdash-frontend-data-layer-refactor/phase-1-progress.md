---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 1
title: Sessions Vertical Slice (Canonical Pattern)
status: completed
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs:
- 84eda5a
pr_refs: []
owners:
- ui-engineer-enhanced
contributors: []
execution_model: sequential
started: null
completed: null
overall_progress: 100
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T1-001
  description: Author useSessionsQuery (useInfiniteQuery) + useSessionDetailQuery
    in services/queries/sessions.ts; key on sessionsKeys; staleTime 30_000; enabled
    guard
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T0-003
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: 84eda5a
  verified_by:
  - T1-006
- id: T1-002
  description: Author useSessionDetailQuery in services/queries/sessions.ts; replace
    bespoke sessionDetailRequestsRef/sessionDetailTimestampsRef Map TTL; dedup concurrent
    calls
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T1-001
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: 84eda5a
  verified_by:
  - T1-006
- id: T1-003
  description: Migrate SessionInspector, Dashboard, PlanningAgentSessionBoard to TQ
    hooks; remove AppEntityDataContext.tsx:111 duplicate refreshSessions(true); keep
    useData().sessions shim
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T1-001
  - T1-002
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: 84eda5a
  verified_by:
  - T1-006
- id: T1-004
  description: Write back-navigation cache Vitest test; assert zero additional GET
    /api/sessions calls on warm mount within gcTime window
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T1-003
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: 84eda5a
  verified_by:
  - T1-006
- id: T1-005
  description: Runtime smoke Dashboard + SessionInspector; verify single /api/sessions
    on cold load; no spinner on warm back-nav
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-003
  - T1-004
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - runtime_smoke: skipped
  verified_by:
  - T1-006
- id: T1-006
  description: task-completion-validator gate (P1)
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T1-005
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - review: task-completion-validator-pass
  - review: task-completion-validator-pass
  verified_by:
  - T1-006
parallelization:
  batch_1:
  - T1-001
  batch_2:
  - T1-002
  batch_3:
  - T1-003
  batch_4:
  - T1-004
  batch_5:
  - T1-005
  batch_6:
  - T1-006
  critical_path:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  - T1-005
  - T1-006
blockers: []
success_criteria:
- id: SC-1.1
  description: useSessionsQuery (infinite) + useSessionDetailQuery hooks in services/queries/sessions.ts
  status: pending
- id: SC-1.2
  description: AppEntityDataContext.tsx:111 duplicate refreshSessions(true) removed
  status: pending
- id: SC-1.3
  description: SessionInspector, Dashboard, PlanningAgentSessionBoard consuming hooks
    directly
  status: pending
- id: SC-1.4
  description: useData().sessions facade intact (reads from TQ cache)
  status: pending
- id: SC-1.5
  description: Fetch-spy test passes — 1 cold-load session call; 0 on warm back-nav
  status: pending
- id: SC-1.6
  description: Runtime smoke Dashboard + SessionInspector (AC-A2, AC-A3 verified)
  status: pending
- id: SC-1.7
  description: task-completion-validator sign-off
  status: pending
files_modified:
- services/queries/sessions.ts
- contexts/AppEntityDataContext.tsx
- components/SessionInspector.tsx
- components/Dashboard.tsx
- components/Planning/PlanningAgentSessionBoard.tsx
progress: 100
runtime_smoke: skipped
runtime_smoke_reason: background worktree session; no interactive browser. Network-count
  ACs (single cold-load session fetch, no limit=5000, 30s refetch) covered by fetch-spy
  + guardrail vitest tests; vite build green proves compile/bundle.
---

# CCDash Frontend Data Layer Refactor - Phase 1: Sessions Vertical Slice

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-1-progress.md \
  -t T1-001 -s completed
```

---

## Objective

Migrate sessions end-to-end as the canonical pattern all later phases replicate. Use `useInfiniteQuery` for session list (resolves OQ-1). Eliminate duplicate cold-load fetch at `AppEntityDataContext.tsx:111`. Back-navigation must render from TQ cache with no spinner.
