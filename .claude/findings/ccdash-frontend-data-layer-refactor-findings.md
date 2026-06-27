---
schema_version: 2
doc_type: report
title: "CCDash Frontend Data Layer Refactor — P5–P7 Findings"
status: accepted
created: 2026-05-29
feature_slug: ccdash-frontend-data-layer-refactor
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
report_category: in-flight-findings
tags: [data-layer, tanstack-query, findings, runtime-smoke, guardrails]
---

# CCDash Frontend Data Layer Refactor — P5–P7 Findings

In-flight findings captured during execution of Phases 5–7 (backend fat-read
bundles, list virtualization, validation/docs/Epic D gate).

## F-1: Stale guardrail in FeatureSurfaceRegressionMatrix (SURFACE 6) — FIXED

**Severity**: Medium (process gap) · **Status**: Resolved in P7 (T7-001)

The `P5-004 Matrix — useFeatureModalData` describe block in
`components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx` read
`services/useFeatureModalData.ts` to prove the linked-sessions demand-gate
(call gated behind `tab === 'sessions'`, ≤3 bounded call sites, no mount-time
eager fetch). Commit `00c8f15` (#47, "Extract the planning forensics boundary")
moved that dispatcher + load-more logic into
`services/useFeatureModalForensics.ts`, leaving zero call sites in the old file.
Two tests therefore failed on the **P4-sealed branch tip** — i.e. the guardrail
suite was already red before P5–P7 began, yet P4 was sealed.

- **Fix**: Repointed the SURFACE 6 proofs to
  `services/useFeatureModalForensics.ts` (2 call sites at lines 235/296; the
  dispatcher call at 235 is gated by `} else if (tab === 'sessions') {`). The
  architectural invariant is unchanged — only the file location moved.
- **Process note**: A source-reading guardrail that hard-codes a file path
  silently rots when code is extracted. P4's exit gate did not re-run the full
  named guardrail suite, or it would have caught this. Recommend phase-exit
  gates run the complete `vitest run` (not a per-phase subset).

## F-2: Runtime smoke deferred (no booted runtime in this execution)

**Severity**: Low · **Status**: Deferred with automated-evidence substitute

T5-009, T6-004, and T7-002 call for booting the dev server + browser and
inspecting the DevTools network waterfall across seeded projects (>50 sessions,
>100 docs, >50 features). This P5–P7 sprint ran as a headless background job
without a booted CCDash stack or seeded fixtures, so live DevTools smoke was
**not performed** (the plan permits `runtime_smoke: skipped` + reason).

Substitute automated evidence that exercises the same invariants:
- **Single-request-per-view**: `components/__tests__/bundleQuerySeam.test.ts`
  (fetch-spy) and `components/__tests__/dashboardColdLoad.test.tsx` assert
  Dashboard cold load issues one `GET /api/v1/dashboard` and no separate
  `/api/sessions` or `/api/tasks` calls; planning view bundle asserted similarly.
- **Virtualization row bounds**: `SessionInspectorVirtualization`,
  `PlanCatalogVirtualization`, `ProjectBoardVirtualization` test suites assert
  DOM rendered-row count ≤ `overscan*2 + visibleCount`.
- **Missing-field resilience**: bundle hook tests assert `taskCounts ?? {}` and
  `sessions ?? []` behavior.

**Follow-up**: Run the documented live DevTools smoke against a seeded project
before release; record the network-waterfall screenshots the ACs request.

## F-3: Analytics overview-bundle FE component wiring deferred

**Severity**: Low · **Status**: Hook shipped; component wiring deferred

The `GET /api/analytics/overview-bundle` endpoint (T5-004) and its consumer hook
`useAnalyticsOverviewQuery` (`services/queries/analytics.ts`,
`analyticsKeys.overviewBundle`) shipped. Wiring it into `AnalyticsDashboard.tsx`
was deferred: that component's tab state machine drives ~4 `Promise.all`
analytics calls and replacing `analyticsService.getOverview()` materially
expands scope beyond the P5b "if low-risk" qualifier. Graded P5 success criteria
(Dashboard + Planning ≤1 above-fold request) are unaffected — analytics is not a
graded cold-load surface. **Follow-up**: wire `useAnalyticsOverviewQuery` into
`AnalyticsDashboard.tsx` in a future pass.

## F-4: Epic D SSR-blocker citation drift (documented in gate spec)

**Severity**: Informational · **Status**: Captured in entry-criteria spec

While authoring `ccdash-nextjs-migration-entry-criteria.md` (T7-006), the
inventory-priorart citations were verified and had drifted:
- `AppRuntimeContext.tsx:43` module-scope `window.location.hash` read — **no
  longer present** (resolved during P4 context teardown). AC-D1 criterion 2 is
  retained verbatim because a full module-scope-browser-global audit is still
  required at Epic D entry; the resolved instance does not waive that audit.
- HashRouter "across ~30 files" — collapsed to a single active import in
  `App.tsx` (`WorkflowRegistryPage.tsx` has only a comment reference).
- `AuthSessionContext.tsx:192-193` `window.location.assign` confirmed SSR-safe
  (guarded by `typeof window !== 'undefined'`).

## F-5: Second stale guardrail introduced by P6 (ProjectBoard) — FIXED

**Severity**: Medium · **Status**: Resolved before merge (karen end-of-feature catch)

P6 virtualization of `ProjectBoard.tsx` (T6-003, commit `87ca83e`) replaced the
eager `surfaceCards.map(c => (` list render with a `@tanstack/react-virtual`
loop (`surfaceCards[vRow.index]`). The `P3-005` source-reading guardrail in
`components/__tests__/ProjectBoardCardMetrics.test.tsx:459` asserted the old
literal string and broke — same failure class as F-1, but newly introduced. The
initial T7-001 guardrail run only covered the 5 named guardrail files and missed
this suite; the `karen` end-of-feature review ran the FULL `vitest` suite and
caught it.

- **Fix**: Updated the assertion to accept the virtualized render
  (`surfaceCards[vRow.index]`) while preserving the invariant (list renders from
  `surfaceCards`, never the eager `filteredFeatures`). ProjectBoardCardMetrics
  back to 17/17.
- **Verification**: Full-suite failing-file set on tip is a strict subset of the
  clean-baseline failing set (diff empty) — zero new regressions from P5–P7; the
  P7 fix additionally removed `FeatureSurfaceRegressionMatrix` from the failing
  set. Remaining 12 files / 45 failing tests are pre-existing P0–P4 debt
  (Planning suites rendered without a QueryClient provider, etc.), out of scope
  for P5–P7 and tracked here for a future cleanup pass.
- **Reinforces F-1's process note**: phase-exit gates must run the COMPLETE
  `vitest run`, not a named subset — source-reading guardrails rot on any
  render-shape change.
