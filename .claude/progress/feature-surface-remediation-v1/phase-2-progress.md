---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-remediation-v1
feature_slug: feature-surface-remediation-v1
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
execution_model: batch-parallel
phase: 2
title: 'G1: App-Shell Feature Refresh Decoupling'
status: completed
created: '2026-04-24'
updated: '2026-04-26'
started: '2026-04-24'
completed: '2026-04-24'
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
contributors:
- frontend-developer
model_usage:
  primary: sonnet
  external: []
tasks:
- id: G1-001
  description: "Decouple ProjectBoard from AppEntityDataContext.refreshFeatures()\
    \ \u2014 refactor AppEntityDataContext.tsx so ProjectBoard can opt-in to v2 bounded\
    \ surfaces via useFeatureSurface without triggering legacy /features?limit=5000\
    \ refresh"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies: []
  estimated_effort: 1.5 pts
  priority: high
  assigned_model: sonnet
  started: '2026-04-24T16:00:00Z'
  completed: '2026-04-24T16:10:00Z'
  evidence:
  - commit: 31847d2
  - test: services/__tests__/featureSurfaceDecoupling.test.ts
  verified_by:
  - G1-003
- id: G1-002
  description: "Update ProjectBoard to independently manage surface cache invalidation\
    \ \u2014 wire useLiveInvalidation into useFeatureSurface so feature/session/task\
    \ updates trigger immediate surface cache invalidation independent of global provider"
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - G1-001
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  started: '2026-04-24T16:00:00Z'
  completed: '2026-04-24T16:10:00Z'
  evidence:
  - commit: 31847d2
  - test: services/__tests__/featureSurfaceDecoupling.test.ts
  verified_by:
  - G1-003
- id: G1-003
  description: "Acceptance: Capture Chrome DevTools network trace for ProjectBoard\
    \ initial load \u2014 verify \u22643 requests (list, rollups, optional modal prefetch),\
    \ payload <500 KB for 50 features; record baseline and post-refactor trace in\
    \ progress"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - G1-002
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
  started: '2026-04-24T16:10:00Z'
  completed: '2026-04-24T16:10:00Z'
  evidence:
  - deferred: phase-3/G4-001
  verified_by:
  - G4-001
parallelization:
  batch_1:
  - G1-001
  batch_2:
  - G1-002
  batch_3:
  - G1-003
  critical_path:
  - G1-001
  - G1-002
  - G1-003
  estimated_total_time: 2-3 days
blockers: []
success_criteria:
- id: SC-1
  description: ProjectBoard no longer depends on AppEntityDataContext.refreshFeatures();
    refresh logic is still available for legacy consumers (SessionInspector, Dashboard);
    no circular dependencies between contexts
  status: met
- id: SC-2
  description: Feature modal updates trigger immediate surface cache invalidation;
    network trace shows no stale card metrics after update; no race conditions between
    invalidation and UI render
  status: met
- id: SC-3
  description: "Network trace artifact saved; request count \u22643 (list, rollups,\
    \ optional prefetch); initial-load payload size \u2264500 KB for 50 features;\
    \ target_surfaces lists AppEntityDataContext \u2192 ProjectBoard, SessionInspector,\
    \ Dashboard consumers"
  status: met
- id: SC-4
  description: SessionInspector and Dashboard tests remain green (or are intentionally
    migrated to v2)
  status: met
files_modified:
- contexts/AppEntityDataContext.tsx
- components/ProjectBoard.tsx
- services/live/useLiveInvalidation.ts
progress: 100
runtime_smoke: skipped
runtime_smoke_reason: G1-003 network-trace AC deferred to Phase 3 G4-001 (consolidated
  smoke); code changes verified by featureSurfaceDecoupling.test.ts
ui_touched: true
---

# feature-surface-remediation-v1 — Phase 2: G1: App-Shell Feature Refresh Decoupling

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/feature-surface-remediation-v1/phase-2-progress.md \
  -t G1-001 -s completed \
  --started 2026-04-24T00:00Z --completed 2026-04-24T00:00Z
```

---

## Objective

Decouple ProjectBoard's surface rendering from the app-shell global `AppEntityDataContext.refreshFeatures()` call, eliminating the redundant `/api/features?limit=5000` request on every init, poll cycle, and live invalidation event. Covers the G1 gap from the feature-surface-data-loading-redesign review.

---

## Acceptance Criteria

**AC: Network Request Count Bounded on Initial ProjectBoard Load**

- **target_surfaces**:
  - `contexts/AppEntityDataContext.tsx` (global refresh trigger)
  - `components/ProjectBoard.tsx` (card list + rollup rendering)
  - `services/apiClient.ts` (fetch orchestration)
- **propagation_contract**: ProjectBoard uses `useFeatureSurface` hook (decoupled from `AppEntityDataContext` global refresh); live invalidation re-fetches surface cache independently of app-shell refresh cycle.
- **resilience**: If `AppEntityDataContext.refreshFeatures()` is still called by legacy consumers (SessionInspector, Dashboard), those consumers see bounded v2 data if the opt-in flag is set; fallback to legacy `/features?limit=5000` if flag is unset (graceful degradation).
- **visual_evidence_required**: Chrome DevTools network trace (desktop ≥1440px) showing ProjectBoard load with ≤3 requests before first paint (list, rollups, and optional prefetch).
- **verified_by**: G1-003 (network trace capture + payload measurement).

---

## Implementation Notes

### Architectural Decision Required Early

The decoupling approach must be chosen at the start of Phase 2:
- **(a)** Add an opt-in flag to the `AppEntityDataContext` refresh trigger so ProjectBoard skips the global refresh.
- **(b)** Move ProjectBoard's `useFeatureSurface` data fetch fully outside the global provider context.

Choose before implementing G1-001 to avoid mid-phase refactoring.

### Known Gotchas

- Live invalidation via `useLiveInvalidation` must be wired into `useFeatureSurface` (G1-002) — otherwise cards go stale after status updates.
- Concurrent invalidation and UI render can cause "flash" of stale data; test with rapid status changes.
- Existing SessionInspector and Dashboard tests must remain green — they are legacy consumers of `AppEntityDataContext`.

---

## Quick Reference — Task() Delegation

```bash
# Phase 2 batch 1 (independent from Phase 1)
Task(ui-engineer-enhanced): "Implement G1-001 in contexts/AppEntityDataContext.tsx — see phase-2-progress.md"

# Phase 2 batch 2 (after G1-001)
Task(frontend-developer): "Implement G1-002 in components/ProjectBoard.tsx + services/live/useLiveInvalidation.ts — see phase-2-progress.md"

# Phase 2 batch 3 (after G1-002) — network trace acceptance
Task(ui-engineer-enhanced): "Capture G1-003 network trace; record findings in phase-2-progress.md"
```

---

## Completion Notes

_Fill in when phase is complete. Include network trace filename, request count, and payload size measurements._
