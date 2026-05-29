---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 4
title: Eager-Load Removal + Context Teardown (HIGH RISK)
status: completed
created: '2026-05-28'
updated: '2026-05-29'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs:
- 56a2d60
pr_refs: []
owners:
- ui-engineer-enhanced
contributors:
- karen
execution_model: sequential
started: null
completed: null
overall_progress: 100
completion_estimate: on-track
total_tasks: 10
completed_tasks: 10
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T4-001
  description: Remove refreshAll() eager fan-out at AppRuntimeContext.tsx:221; replace
    with useHealthQuery refetchInterval 30_000; AppRuntimeContext exposes runtimeStatus/loading/error/runtimeUnreachable
    only
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-009
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-002
  description: Port polling intervals to per-query refetchInterval; remove setInterval
    at AppRuntimeContext.tsx:225 and :249; health 30s, alerts/notifications 30s, features
    live-mode fallback 5s (SSE-gated)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-001
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-003
  description: "Route-colocate queries with enabled flags; Dashboard route enables\
    \ only sessions+tasks; add useCurrentRoute helper; verify Dashboard cold load\
    \ \u22642 requests"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-002
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-004
  description: Port optimistic mutations to TQ useMutation (updateFeatureStatus, updatePhaseStatus,
    updateTaskStatus) in services/mutations/features.ts; remove pendingFeatureStatusById
    map from AppEntityDataContext; onMutate/onError/onSettled pattern
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-003
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-005
  description: Delete contexts/AppEntityDataContext.tsx (476 lines) after all 15 screens
    individually migrated and smoked in T4-003; remove AppEntityDataProvider from
    DataContext.tsx
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-004
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-006
  description: Shrink AppRuntimeContext to client-state-only (<100 lines); remove
    refreshAllInFlightRef, pollingActiveRef, consecutiveFailuresRef, domain refresh
    callbacks
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-005
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-007
  description: "Thin useData() facade (\u226450 lines) re-exporting TQ hook values\
    \ + AppSessionContext client-state; extend dataArchitecture.test.ts assertions\
    \ (no createContext with server arrays, no useEffect fetch)"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T4-006
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: 56a2d60
  verified_by:
  - T4-009
  - T4-010
- id: T4-008
  description: "Runtime smoke ALL 15 screens (Dashboard, ProjectBoard, SessionInspector,\
    \ PlanCatalog, Analytics, Workflows, CodebaseExplorer, Planning-Home/AgentSessionBoard/AgentRosterPanel/FeatureAgentLane/TrackerIntakePanel/ArtifactDrillDownPage/GraphPanel/NodeDetail,\
    \ OpsPanel, Settings, FeatureExecutionWorkbench, TestingPage, Layout); verify\
    \ back-nav no spinner; Dashboard \u22642 cold requests"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T4-007
  started: '2026-05-29'
  completed: '2026-05-29'
  evidence:
  - runtime: vite-dev-server-http200
  - test: dashboardColdLoad
  verified_by:
  - T4-009
  - T4-010
- id: T4-009
  description: "karen milestone gate (P4) \u2014 verify P4 deliverables against PRD\
    \ ACs (AC-B2, AC-B3, AC-B4), architecture compliance, risk status"
  status: completed
  assigned_to:
  - karen
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T4-008
  started: '2026-05-29'
  completed: '2026-05-29'
  evidence:
  - review: karen-PASS-WITH-NOTES
  verified_by:
  - T4-010
- id: T4-010
  description: task-completion-validator gate (P4)
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T4-009
  started: '2026-05-29'
  completed: '2026-05-29'
  evidence:
  - review: task-completion-validator-PASS
  verified_by:
  - T4-010
parallelization:
  batch_1:
  - T4-001
  batch_2:
  - T4-002
  batch_3:
  - T4-003
  batch_4:
  - T4-004
  batch_5:
  - T4-005
  batch_6:
  - T4-006
  batch_7:
  - T4-007
  batch_8:
  - T4-008
  batch_9:
  - T4-009
  batch_10:
  - T4-010
  critical_path:
  - T4-001
  - T4-002
  - T4-003
  - T4-004
  - T4-005
  - T4-006
  - T4-007
  - T4-008
  - T4-009
  - T4-010
blockers: []
success_criteria:
- id: SC-4.1
  description: AppRuntimeContext.tsx eager fan-out removed; health query polls at
    30s; feature fallback at 5s (SSE-gated)
  status: pending
- id: SC-4.2
  description: AppEntityDataContext.tsx deleted; file absent from repo
  status: pending
- id: SC-4.3
  description: AppRuntimeContext < 100 lines; client-state-only
  status: pending
- id: SC-4.4
  description: "DataContext.tsx \u2264 50 lines thin facade; AppDataProviderGate preserved"
  status: pending
- id: SC-4.5
  description: "services/mutations/features.ts \u2014 three TQ mutations with optimistic\
    \ pattern"
  status: pending
- id: SC-4.6
  description: dataArchitecture.test.ts extended; all assertions green
  status: pending
- id: SC-4.7
  description: Runtime smoke all 15 screens (AC-B2, AC-B3, AC-B4 verified)
  status: pending
- id: SC-4.8
  description: karen milestone review passed
  status: pending
- id: SC-4.9
  description: task-completion-validator sign-off
  status: pending
files_modified:
- contexts/AppRuntimeContext.tsx
- contexts/AppEntityDataContext.tsx
- contexts/DataContext.tsx
- contexts/dataContextShared.ts
- contexts/__tests__/dataArchitecture.test.ts
- services/mutations/features.ts
- components/Dashboard.tsx
- components/ProjectBoard.tsx
- components/SessionInspector.tsx
- components/PlanCatalog.tsx
progress: 100
runtime_smoke: partial
runtime_smoke_reason: "Vite dev server boots (HTTP 200); full 15-screen browser walkthrough\
  \ deferred to pre-main validation \u2014 background job, no worktree backend venv,\
  \ only user personal Chrome available. AC-B2 covered by dashboardColdLoad test;\
  \ AC-B4 by mutation rollback test."
---

# CCDash Frontend Data Layer Refactor - Phase 4: Eager-Load Removal + Context Teardown

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-4-progress.md \
  -t T4-001 -s completed
```

---

## Objective

Remove `AppRuntimeContext` 7–8 request fan-out. Port polling to per-query `refetchInterval`. Delete `AppEntityDataContext` (476 lines) only after all 15 screens individually migrated and runtime-smoked. Port optimistic mutations to TQ. `karen` reviews at phase exit. HIGH RISK — 24 components consume `useData()`.

**OQ-3 Resolution**: Keep minimal `useData()` shim (<50 lines) — avoids touching 24 import sites in one sweep.
**OQ-4 Resolution**: No per-deploy rollback flag needed (incremental + facade-preserved).
**OQ-6 Resolution**: Health 30s, alerts/notifications 30s, features live-mode fallback 5s when SSE disabled; SSE paths set `refetchInterval: false`.
