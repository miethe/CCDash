---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 0
title: TQ Foundation & Guardrails
status: completed
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs:
- c8d583c
- 4e1db9b
pr_refs: []
owners:
- ui-engineer-enhanced
contributors: []
execution_model: sequential
started: null
completed: null
overall_progress: 100
completion_estimate: on-track
total_tasks: 8
completed_tasks: 8
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T0-001
  description: Install @tanstack/react-query v5; verify no peer-dep conflicts with
    react-virtual
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies: []
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-002
  description: Author lib/queryClient.ts with project defaults (staleTime, gcTime,
    retry, refetchOnWindowFocus); export createProjectQueryClient
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-001
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-003
  description: Author services/queryKeys.ts with all key factories (sessions, documents,
    tasks, features, alerts, notifications, planning, dashboard); all keyed on projectId
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-001
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-004
  description: Mount QueryClientProvider above DataProvider in App.tsx; clear on project
    switch; preserve AppDataProviderGate
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-002
  - T0-003
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-005
  description: Add ReactQueryDevtools gated by VITE_CCDASH_QUERY_DEVTOOLS env var
    (devDependency, not in prod bundle)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-004
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-006
  description: Extend guardrail tests in dataArchitecture.test.ts and create services/__tests__/noHandRolledCache.test.ts;
    ban new Map()+TTL patterns; allow TQ imports
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-004
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - commit: c8d583c
  verified_by:
  - T0-008
- id: T0-007
  description: Runtime smoke all routes (Dashboard, SessionInspector, PlanCatalog,
    ProjectBoard, Planning, Analytics, Settings); verify no regressions
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-005
  - T0-006
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - runtime_smoke: skipped
  verified_by:
  - T0-008
- id: T0-008
  description: task-completion-validator gate (P0)
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T0-007
  started: '2026-05-28T23:30:00Z'
  completed: '2026-05-28T23:30:00Z'
  evidence:
  - review: task-completion-validator-pass
  - review: task-completion-validator-pass
  verified_by:
  - T0-008
parallelization:
  batch_1:
  - T0-001
  batch_2:
  - T0-002
  - T0-003
  batch_3:
  - T0-004
  batch_4:
  - T0-005
  - T0-006
  batch_5:
  - T0-007
  batch_6:
  - T0-008
  critical_path:
  - T0-001
  - T0-002
  - T0-004
  - T0-005
  - T0-007
  - T0-008
blockers: []
success_criteria:
- id: SC-0.1
  description: '@tanstack/react-query ^5.x in package.json; no peer-dep conflicts'
  status: pending
- id: SC-0.2
  description: lib/queryClient.ts and services/queryKeys.ts authored
  status: pending
- id: SC-0.3
  description: QueryClientProvider mounted above DataProvider in App.tsx
  status: pending
- id: SC-0.4
  description: dataArchitecture.test.ts extended; noHandRolledCache.test.ts created;
    vitest run green
  status: pending
- id: SC-0.5
  description: Runtime smoke all routes render without error or regression
  status: pending
- id: SC-0.6
  description: task-completion-validator sign-off
  status: pending
files_modified:
- package.json
- package-lock.json
- lib/queryClient.ts
- services/queryKeys.ts
- App.tsx
- contexts/__tests__/dataArchitecture.test.ts
- services/__tests__/noHandRolledCache.test.ts
progress: 100
runtime_smoke: skipped
runtime_smoke_reason: background worktree session; no interactive browser. Network-count
  ACs (single cold-load session fetch, no limit=5000, 30s refetch) covered by fetch-spy
  + guardrail vitest tests; vite build green proves compile/bundle.
---

# CCDash Frontend Data Layer Refactor - Phase 0: TQ Foundation & Guardrails

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-0-progress.md \
  -t T0-001 -s completed
```

---

## Objective

Install TanStack Query v5, mount `QueryClientProvider` above existing `DataProvider`, author `lib/queryClient.ts` and `services/queryKeys.ts`, add devtools flag, and extend guardrail tests. Zero domains migrated yet — app must render identically to pre-TQ baseline.

---

## Implementation Notes

T0-002 and T0-003 can run in parallel after T0-001. T0-005 and T0-006 can run in parallel after T0-004. T0-008 is the validator gate (0 pts).
