---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 3
title: Hand-Rolled Cache Consolidation (HIGH RISK)
status: completed
created: '2026-05-28'
updated: '2026-05-29'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs:
- d2bc95c
pr_refs: []
owners:
- ui-engineer-enhanced
contributors: []
execution_model: sequential
started: null
completed: null
overall_progress: 100
completion_estimate: on-track
total_tasks: 9
completed_tasks: 9
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T3-001
  description: Author services/queries/planning.ts with usePlanningSummaryQuery, usePlanningFeatureContextQuery,
    usePlanningSessionBoardQuery; fold freshnessToken into queryKey (OQ-2 resolution)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T2-011
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-002
  description: Migrate planning consumers (PlanningHomePage, PlanningGraphPanel, TrackerIntakePanel,
    ArtifactDrillDownPage, PlanningNodeDetail) to TQ hooks; remove onRevalidated +
    featureCacheBus subscription at planning.ts:315-318
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-001
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-003
  description: Delete planning.ts LRU Maps (PLANNING_BROWSER_CACHE, PLANNING_FEATURE_CONTEXT_CACHE,
    PLANNING_SESSION_BOARD_CACHE) and LRU utilities; fetch functions may remain as
    plain async helpers
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-002
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-004
  description: Author TQ-backed useFeatureSurface adapter preserving public API (query,
    invalidate(scope), cacheKey); list-tier useQuery + rollup-tier useQuery; featureCacheBus
    publishFeatureWriteEvent → queryClient.invalidateQueries
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-001
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-005
  description: Delete services/featureSurfaceCache.ts (455 lines) + services/featureCacheBus.ts
    (88 lines); replace publishFeatureWriteEvent call-sites with queryClient.invalidateQueries
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-004
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-006
  description: Extend FeatureSurfaceRegressionMatrix.test.tsx:537-590 with TQ-path
    assertions (mock TQ provider, list/rollup hooks, invalidate triggers)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-005
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
- id: T3-007
  description: Seam task — navigate to Planning + ProjectBoard v2 in dev server; verify
    planning loads; verify feature write mutation triggers correct TQ invalidation;
    R-P3 cross-owner seam
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: extended
  dependencies:
  - T3-006
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  - runtime_smoke: skipped-bg-job-validated-via-build+vitest
  verified_by:
  - T3-009
- id: T3-008
  description: Runtime smoke Planning + FeatureModal; verify summary/graph/session
    board load; verify feature status change triggers optimistic update + cache invalidation
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T3-007
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  - runtime_smoke: skipped-bg-job-validated-via-build+vitest
  verified_by:
  - T3-009
- id: T3-009
  description: task-completion-validator gate (P3)
  status: completed
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T3-008
  started: '2026-05-28'
  completed: '2026-05-29'
  evidence:
  - commit: d2bc95c
  verified_by:
  - T3-009
parallelization:
  batch_1:
  - T3-001
  batch_2:
  - T3-002
  - T3-004
  batch_3:
  - T3-003
  - T3-005
  batch_4:
  - T3-006
  batch_5:
  - T3-007
  batch_6:
  - T3-008
  batch_7:
  - T3-009
  critical_path:
  - T3-001
  - T3-002
  - T3-003
  - T3-006
  - T3-007
  - T3-008
  - T3-009
blockers: []
success_criteria:
- id: SC-3.1
  description: planning.ts LRU Maps deleted (3 module-scope Maps + LRU utilities)
  status: pending
- id: SC-3.2
  description: featureSurfaceCache.ts and featureCacheBus.ts files deleted
  status: pending
- id: SC-3.3
  description: useFeatureSurface public API preserved; ProjectBoard v2 path functional
    without consumer edits
  status: pending
- id: SC-3.4
  description: publishFeatureWriteEvent import absent from all files (source-reading
    assertion)
  status: pending
- id: SC-3.5
  description: FeatureSurfaceRegressionMatrix.test.tsx extended and green
  status: pending
- id: SC-3.6
  description: noHandRolledCache.test.ts guardrail green for all migrated files
  status: pending
- id: SC-3.7
  description: Runtime smoke Planning + FeatureModal
  status: pending
- id: SC-3.8
  description: task-completion-validator sign-off
  status: pending
files_modified:
- services/queries/planning.ts
- services/planning.ts
- services/featureSurfaceCache.ts
- services/featureCacheBus.ts
- services/useFeatureSurface.ts
- services/queryKeys.ts
- components/Planning/PlanningHomePage.tsx
- components/Planning/PlanningGraphPanel.tsx
- components/Planning/TrackerIntakePanel.tsx
- components/Planning/ArtifactDrillDownPage.tsx
- components/Planning/PlanningNodeDetail.tsx
- components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx
progress: 100
---

# CCDash Frontend Data Layer Refactor - Phase 3: Hand-Rolled Cache Consolidation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-3-progress.md \
  -t T3-001 -s completed
```

---

## Objective

Retire two hand-rolled cache systems: `services/planning.ts` (three LRU Maps) and `services/featureSurfaceCache.ts`/`featureCacheBus.ts`. Fold `freshnessToken` into TQ queryKey (OQ-2 resolution). Preserve `useFeatureSurface` public API via TQ-backed adapter. HIGH RISK — silent consumer breakage possible.
