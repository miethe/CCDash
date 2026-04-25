---
title: "Feature Surface Data Loading Redesign - Review Report"
description: "Review of plan coverage, implementation coverage, and plan conformance for the feature surface performance pass."
audience: [ai-agents, developers]
tags: [review, performance, feature-surface, implementation-plan, refactor]
created: 2026-04-24
updated: 2026-04-24
category: "product-planning"
status: published
related:
  - /docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-0-inventory-contracts.md
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-4-modal-lazy-loading.md
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-5-validation-rollout.md
---

# Feature Surface Data Loading Redesign - Review Report

## Executive Summary

The plan covered the fundamental feature-surface performance intent well for visible feature consumers: ProjectBoard, the embedded feature modal, feature list mode, PlanningHomePage, FeatureExecutionWorkbench, SessionInspector, Dashboard, BlockingFeatureList, and planning cache coordination. The Phase 0 inventory was the strongest part of the plan because it mapped current visible fields, filters, modal sections, and expensive session-derived metrics before implementation.

The implementation substantially met the plan for the core hotspot: ProjectBoard no longer renders from per-feature linked-session calls, the feature modal uses lazy section loading, v1 list/rollup/session-page contracts exist, and targeted backend/frontend tests pass.

The main gap is that the app-level feature data surface was not fully closed. `AppEntityDataContext` still refreshes the legacy full feature list through `client.getFeatures()`, and `AppRuntimeContext` still calls that refresh on initial load, 30-second refreshes, live invalidation, and 5-second fallback polling. This preserves a global `/features?offset=0&limit=5000` path even when ProjectBoard itself renders from `useFeatureSurface`.

## Plan Coverage Assessment

Verdict: mostly complete, with one important app-shell omission.

The plan covered the central intent:

- Bounded board loading: one list page plus one rollup batch.
- Repository-backed filters, sort, totals, and pagination.
- No card-level session log/detail reads.
- Lazy modal sections with tab-level loading, empty, error, retry, and stale states.
- Paginated linked-session detail.
- SQLite and Postgres repository parity.
- Cross-surface migration beyond the board: SessionInspector, FeatureExecutionWorkbench, Dashboard/BlockingFeatureList, and planning cache coordination.
- Validation via parity, performance, observability, feature flag, rollback docs, and legacy caller inventory.

The plan did not sufficiently make the global data provider a first-class performance surface. The PRD identifies `apiClient.getFeatures()` loading `/api/features?offset=0&limit=5000` as part of the current problem, and the parent plan lists `contexts/AppEntityDataContext.tsx` as a key file, but the phase tasks do not explicitly retire or gate the provider-level legacy feature refresh. That matters because the global provider still runs independently of ProjectBoard.

## Implementation Coverage Assessment

Verdict: strong core implementation coverage, partial app-shell coverage.

Implemented coverage is broad:

- Backend v1 endpoints exist for feature card list, rollups, modal overview/sections, and paginated session pages.
- SQLite and Postgres repository methods were added for feature list queries, phase summaries, rollups, and session pagination.
- Frontend feature clients, cache, flag handling, `useFeatureSurface`, and `useFeatureModalData` were added.
- ProjectBoard renders from `surfaceCards` and `surfaceRollups` rather than the old session-summary loop.
- Modal and cross-surface tests assert no eager `/api/features/{id}/linked-sessions` calls in key UI paths.
- Documentation and rollback notes were added.

Implementation gaps:

1. Global feature refresh still uses the legacy 5000-row list.
   `services/apiClient.ts` still defines `getFeatures()` as `/features?offset=0&limit=5000`, `AppEntityDataContext.refreshFeatures()` still calls it, and `AppRuntimeContext.refreshAll()` plus feature polling still trigger that path. This weakens the app-level request/payload budget even though the board render path is bounded.

2. Feature write paths still interpolate raw IDs.
   `updateFeatureStatus`, `updatePhaseStatus`, and `updateTaskStatus` in `services/apiClient.ts` still build `/features/${featureId}/...` and phase/task paths without `encodeURIComponent`. The plan and PRD expected feature IDs with reserved URL characters to work across fetch paths, not only read/detail paths.

3. FeatureExecutionWorkbench migration is incomplete against the strict wording of P4-008.
   The component uses `useFeatureSurface` for picker/list data, but selected feature detail still loads through `getFeatureExecutionContext(selectedFeatureId)` and uses `context.sessions`. That is no longer a per-feature board fan-out, but it is not fully moved onto the shared feature-surface client plus paginated session model described by the phase task.

4. Runtime smoke was skipped for Phases 4 and 5.
   The targeted test coverage is good, but the progress files explicitly mark UI runtime smoke as skipped. The remaining risks are network-trace and visual behavior risks, especially around modal tab transitions, live invalidation, and global provider fetches.

## Plan Conformance

Met expectations:

- The old ProjectBoard per-card linked-session fan-out was removed.
- Card metrics are sourced from DTO + rollup mapping.
- Server-backed filters and totals are implemented on the new feature-card path.
- Modal sessions are loaded on demand through a paginated client.
- Legacy linked-session callers were inventoried and production eager callers were removed or replaced.
- Feature-surface tests, parity tests, benchmarks, flag tests, and docs were added.

Partially met expectations:

- "Every frontend fetch path must encode path parameters" is only partially met.
- "Initial feature board calls <= 3" is met for the new board hook path, but not for the full app shell if the global provider is included in the measurement.
- "FeatureExecutionWorkbench migration" is met for avoiding eager linked-session calls, but not fully for moving selected feature/session detail onto paginated surface contracts.

## Verification Run During Review

Frontend targeted suite:

`pnpm test --run components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx components/__tests__/ProjectBoardEagerLoop.test.tsx services/__tests__/featureSurface.test.ts services/__tests__/useFeatureSurface.test.ts services/__tests__/useFeatureModalData.test.ts services/__tests__/featureSurfaceFlag.test.ts`

Result: 6 files passed, 148 tests passed.

Backend targeted suite:

`python -m pytest backend/tests/test_client_v1_feature_surface.py backend/tests/test_feature_surface_parity.py backend/tests/test_feature_surface_benchmarks.py backend/tests/test_feature_surface_v2_flag.py -q`

Result: 32 passed, 5 skipped. Warnings: three unknown `pytest.mark.slow` warnings.

## Recommended Follow-Ups

1. Replace or gate `AppEntityDataContext.refreshFeatures()` so route-level feature surfaces can opt into the v2 bounded list instead of always loading `/features?offset=0&limit=5000`.
2. Encode all feature, phase, and task path parameters in `services/apiClient.ts`.
3. Decide whether `FeatureExecutionWorkbench` selected-detail loading is intentionally exempt because it is user-selected, or migrate its sessions tab to the paginated feature-surface session client.
4. Add one browser/network smoke pass for ProjectBoard and modal flows to verify app-shell request counts, not only component-level request invariants.
