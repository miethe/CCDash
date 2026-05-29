---
schema_version: 2
doc_type: phase_plan
title: "CCDash FE Data Layer Refactor — P3–P4: Cache Consolidation & Context Teardown"
status: draft
created: 2026-05-28
updated: 2026-05-28
phase: "3-4"
phase_title: "Cache and Context Teardown"
feature_slug: ccdash-frontend-data-layer-refactor
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
entry_criteria:
  - "P2 complete: all 6 entity domains on TQ; useData() facade intact"
  - "vitest run green"
exit_criteria:
  - "P3: planning.ts LRU Maps deleted; featureSurfaceCache.ts + featureCacheBus.ts deleted; useFeatureSurface public API preserved via TQ-backed adapter; FeatureSurfaceRegressionMatrix.test green"
  - "P4: AppEntityDataContext deleted; AppRuntimeContext client-state-only; Dashboard cold load ≤2 requests; all 15 screens individually migrated and runtime-smoked; contexts client-state-only; mutations optimistic via TQ; karen milestone"
integration_owner: ui-engineer-enhanced
---

# Phase 3–4: Cache Consolidation & Context Teardown

**Parent Plan**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
**Phases**: P3 (5 pts), P4 (4 pts) — total 9 pts
**Primary Agent**: ui-engineer-enhanced
**Model / Effort**: sonnet / extended (high-risk adapter + context surgery)

> **R-P3 (integration_owner declared)**: Both phases have multiple file-ownership overlaps (planning hooks, feature surface adapter, context providers, screen consumers). `ui-engineer-enhanced` is declared `integration_owner` and owns the seam tasks that verify cross-owner propagation contracts.

---

## Phase 3: Hand-Rolled Cache Consolidation (HIGH RISK)

**Duration**: 2–3 days
**Dependencies**: P2 complete
**Assigned Subagent(s)**: ui-engineer-enhanced
**Model / Effort**: sonnet / extended (delicate adapter + freshness-keying design; silent-breakage risk)
**Risk**: HIGH — `featureSurfaceCache.ts` / `featureCacheBus.ts` feed `useFeatureSurface` across the feature surface; `planning.ts` has a complex freshness-bucket keying scheme with no direct TQ analogue

### Context

Retire two hand-rolled cache systems:

1. **`services/planning.ts`** (1483 lines): Three module-scope LRU Maps (`PLANNING_BROWSER_CACHE`, `PLANNING_FEATURE_CONTEXT_CACHE`, `PLANNING_SESSION_BOARD_CACHE`, inventory-frontend.md §5). SWR via `inFlight?: Promise<T>` refs. Freshness-bucket keying: `PLANNING_BROWSER_CACHE` keys on `(projectId, freshnessToken, payloadType)` — `freshnessToken` comes from backend `dataFreshness` field.

2. **`services/featureSurfaceCache.ts`** (455 lines) + **`services/featureCacheBus.ts`** (88 lines): Two-tier LRU+SWR adapter; pub/sub invalidation bus (inventory-frontend.md §5). Consumer API: `useFeatureSurface` hook in `services/useFeatureSurface.ts` (512 lines) — this public API must be preserved.

**OQ-2 Resolution**: Fold the backend `dataFreshness` token into the TQ `queryKey` array: `planningKeys.summary(projectId, freshnessToken)`. When `dataFreshness` changes on the next poll, TQ treats it as a new key and fetches fresh data. This is cleaner than a custom `staleTime` predicate and avoids a non-standard TQ extension.

**Inventory refs**:
- `services/planning.ts:76-78` — three LRU Maps (inventory-frontend.md §5)
- `services/planning.ts:315-318` — featureCacheBus subscription at module scope (inventory-frontend.md §5)
- `services/featureSurfaceCache.ts` — two-tier LRU (inventory-frontend.md §5)
- `services/featureCacheBus.ts:88` — pub/sub bus (inventory-frontend.md §5)
- `components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx:537-590` — regression matrix to extend (inventory-priorart.md §3)

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T3-001 | Author planning TQ queries | Create `services/queries/planning.ts`. Migrate `planning.ts` fetch logic (summary, featureContext, sessionBoard) to `useQuery` hooks: `usePlanningSummaryQuery(projectId, freshnessToken)`, `usePlanningFeatureContextQuery(projectId, featureId)`, `usePlanningSessionBoardQuery(projectId)`. Keys: `planningKeys.summary(projectId, freshnessToken)`, etc. `staleTime: 0` (freshness token drives invalidation, not stale timer). | Three hook functions in `services/queries/planning.ts`; `freshnessToken` folded into queryKey; unit test: when `freshnessToken` changes, a new fetch is triggered (TQ treats it as a distinct key). | 1.5 pts | ui-engineer-enhanced | sonnet | extended | T2-011 |
| T3-002 | Migrate planning consumers to TQ hooks | Update all planning consumers (PlanningHomePage.tsx, PlanningGraphPanel.tsx, TrackerIntakePanel.tsx, ArtifactDrillDownPage.tsx, PlanningNodeDetail.tsx) to call `usePlanningSummaryQuery` etc. directly. Remove `cacheProjectPlanningSummary` calls and `onRevalidated` callbacks. Remove `clearPlanningBrowserCache` and `featureCacheBus` subscription at `planning.ts:315-318`. | Planning consumers migrated; `onRevalidated` pattern eliminated; `featureCacheBus` subscription at planning.ts:315-318 removed; consumers use TQ `isFetching` instead of SWR callback. | 1 pt | ui-engineer-enhanced | sonnet | extended | T3-001 |
| T3-003 | Delete planning.ts LRU Maps | After T3-002: remove the three module-scope LRU Maps (`PLANNING_BROWSER_CACHE`, `PLANNING_FEATURE_CONTEXT_CACHE`, `PLANNING_SESSION_BOARD_CACHE`) and supporting utilities (`touchMapKey`, `trimMapToLimit`, `cacheProjectPlanningSummary`, `clearPlanningBrowserCache`). The fetch functions themselves may remain as plain async API helpers called by TQ query functions. | `planning.ts` no longer contains `new Map()` declarations or LRU eviction logic; `noHandRolledCache.test.ts` guardrail passes; file may still exist for non-cache API utilities. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T3-002 |
| T3-004 | Author useFeatureSurface TQ adapter | Create a TQ-backed adapter that preserves the `useFeatureSurface` public API (inventory-frontend.md §5: `query`, `invalidate(scope)`, `cacheKey`). Internally: list-tier → `useQuery` keyed `featureSurfaceKeys.list(projectId, query, page)`, `staleTime: 0`, invalidation via `queryClient.invalidateQueries`. Rollup-tier → `useQuery` keyed `featureSurfaceKeys.rollup(projectId, ids, freshnessToken)`, `staleTime: 30_000`. featureCacheBus `publishFeatureWriteEvent` call-sites → `queryClient.invalidateQueries({ queryKey: featureSurfaceKeys.all(projectId) })`. No consumer edits in P3. | `useFeatureSurface.ts` exported API unchanged; `featureSurfaceKeys` entries in `queryKeys.ts`; `ProjectBoard.tsx` v2 path continues to work without any edits (seam verified by T3-007). | 1 pt | ui-engineer-enhanced | sonnet | extended | T3-001 |
| T3-005 | Delete featureSurfaceCache.ts + featureCacheBus.ts | After T3-004: delete `services/featureSurfaceCache.ts` (455 lines) and `services/featureCacheBus.ts` (88 lines). All mutation call-sites that called `publishFeatureWriteEvent` now call `queryClient.invalidateQueries({ queryKey: featureSurfaceKeys.all(projectId) })`. | Both files deleted; `publishFeatureWriteEvent` import absent from all files (source-read assertion); `queryClient.invalidateQueries` handles invalidation at mutation sites. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T3-004 |
| T3-006 | Extend FeatureSurfaceRegressionMatrix test | Add TQ-path assertions to `components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx:537-590` (inventory-priorart.md §3): mock TQ provider; assert list-tier hook returns paginated cards; assert rollup-tier hook returns rollups; assert `invalidate('all')` triggers `queryClient.invalidateQueries`. | Extended regression matrix passes; `vitest run` green. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T3-005 |
| T3-007 | Seam task: cache retirement integration (P3) | Navigate to Planning and ProjectBoard v2 in dev server. Assert planning summary loads, graph loads, session board loads. Assert ProjectBoard v2 list loads paginated and rollups load. Assert feature write mutation (status change on a feature) triggers correct TQ invalidation and re-fetch. **R-P3 seam task**: cross-owner seam verification between planning queries (T3-001), feature surface adapter (T3-004), and their respective UI consumers. | Planning and ProjectBoard v2 functional; feature write mutation invalidates both planning and feature surface queries; no `publishFeatureWriteEvent` calls in console or network. | 0 pts | ui-engineer-enhanced | sonnet | extended | T3-006 |
| T3-008 | Runtime smoke: Planning + FeatureModal (P3) | Boot dev server. Navigate to Planning — verify summary, graph, session board all load. Open a FeatureModal — verify v2 modal section loads. Change a feature status — verify optimistic update and cache invalidation. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | Smoke passes: Planning fully functional; FeatureModal functional; feature write invalidates correctly. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T3-007 |
| T3-009 | task-completion-validator gate (P3) | Validate P3 exit criteria: planning.ts LRU Maps deleted; featureSurfaceCache.ts + featureCacheBus.ts deleted; useFeatureSurface API preserved; FeatureSurfaceRegressionMatrix green; smoke passed. | Validator passes; P3 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T3-008 |

**Phase 3 Quality Gates:**
- [ ] `planning.ts` LRU Maps deleted (`PLANNING_BROWSER_CACHE`, `PLANNING_FEATURE_CONTEXT_CACHE`, `PLANNING_SESSION_BOARD_CACHE`)
- [ ] `featureSurfaceCache.ts` and `featureCacheBus.ts` files deleted
- [ ] `useFeatureSurface` public API preserved; `ProjectBoard` v2 path functional without consumer edits
- [ ] `publishFeatureWriteEvent` import absent from all files (source-reading assertion)
- [ ] `FeatureSurfaceRegressionMatrix.test.tsx` extended and green
- [ ] `noHandRolledCache.test.ts` guardrail green for all migrated files
- [ ] Runtime smoke: Planning + FeatureModal
- [ ] `task-completion-validator` sign-off (P3)

---

## Phase 4: Eager-Load Removal + Context Shrinkage + Optimistic Mutations (HIGH RISK)

**Duration**: 2–3 days
**Dependencies**: P1, P2, P3 all complete (all consumers migrated before root teardown)
**Assigned Subagent(s)**: ui-engineer-enhanced
**Model / Effort**: sonnet / extended (high-risk context teardown across 15 screens; polling/SSE interplay)
**Risk**: HIGH — 24 component files call `useData()`; `AppEntityDataContext` deletion requires all 15 screens individually verified first

### Context

Remove `AppRuntimeContext`'s 7–8 request fan-out (`refreshAll` at line 221). Port polling intervals to per-query `refetchInterval`. Shrink then **delete** `AppEntityDataContext` (476 lines) — only after all 15 screens are individually migrated and runtime-smoked. Port optimistic mutations (feature/phase/task status changes) to TQ `onMutate`/`onError`/`onSettled`. Resolve OQ-3 (keep or delete `useData()` facade).

**OQ-3 Resolution**: Keep a minimal `useData()` shim that re-exports TQ hook values + client-state from `AppSessionContext`. This avoids touching 24 import sites in one risky sweep. The shim is thin enough to be a permanent resident (< 50 lines).

**OQ-4 Resolution**: No per-deploy rollback flag needed for the migration (it is incremental + facade-preserved). Keep `VITE_CCDASH_QUERY_DEVTOOLS` only for devtools visibility.

**OQ-6 Resolution**: Map polling to per-query `refetchInterval`: health query = 30s, alerts/notifications = 30s, features (live-mode fallback) = 5s when `VITE_CCDASH_LIVE_FEATURES_ENABLED=false`. SSE-enabled paths set `refetchInterval: false` (SSE supersedes poll).

**Inventory refs**:
- `contexts/AppRuntimeContext.tsx:221` — `refreshAll()` eager fan-out (inventory-frontend.md §1)
- `contexts/AppRuntimeContext.tsx:225,249` — 30s and 5s poll intervals (inventory-frontend.md §1)
- `contexts/AppEntityDataContext.tsx` — 476 lines; `pendingFeatureStatusById` optimistic map to remove (inventory-frontend.md §1)
- `contexts/DataContext.tsx` — 155 lines facade + `dataContextShared.ts:106` lines (inventory-frontend.md §1)
- Consumer graph: 15 screens (inventory-frontend.md §3)

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T4-001 | Remove eager fan-out from AppRuntimeContext | Remove `refreshAll()` call at `AppRuntimeContext.tsx:221` and the loop that fires `refreshSessions/Documents/Tasks/Alerts/Notifications` on mount. Replace with a single `GET /api/health` query hook (`useHealthQuery`) with `refetchInterval: 30_000`. Dashboard mount now issues only queries enabled for the Dashboard route. | `AppRuntimeContext.tsx:221` eager `refreshAll` call removed; health query polls at 30s; no domain data fetched at root mount; `AppRuntimeContext` exposes only `runtimeStatus`, `loading`, `error`, `runtimeUnreachable`. | 1 pt | ui-engineer-enhanced | sonnet | extended | T3-009 |
| T4-002 | Port polling intervals to refetchInterval | Replace `setInterval(refreshAll, 30_000)` at `AppRuntimeContext.tsx:225` and `setInterval(refreshFeatures, 5_000)` at line 249 with TQ `refetchInterval` per query. Health: `refetchInterval: 30_000`. Alerts/notifications: `refetchInterval: 30_000` (already on hooks in T2-005). Features live-mode fallback: `useFeatureCardQuery.refetchInterval = VITE_CCDASH_LIVE_FEATURES_ENABLED ? false : 5_000`. SSE-connected paths: `refetchInterval: false`. | No `setInterval` for polling in `AppRuntimeContext`; feature hook has correct `refetchInterval` logic; unit test with mock timer asserts health called at 30s; feature called at 5s when SSE disabled. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T4-001 |
| T4-003 | Route-colocate queries with enabled flags | Add `enabled` flags to each domain query hook: `useDocumentsQuery` enabled only when on a documents-consuming route; `useFeaturesQuery` enabled only when on a features-consuming route. Dashboard route: `useSessionsQuery` + `useTasksQuery` only (or later `useDashboardBundleQuery` after P5). Use a `useCurrentRoute()` helper or route-param detection. | Dashboard cold load issues ≤ 2 requests (sessions + tasks); navigate-to-PlanCatalog triggers document fetch on demand; unit test mounts Dashboard and asserts no documents/features/alerts network calls. | 1 pt | ui-engineer-enhanced | sonnet | extended | T4-002 |

**AC-B2: Dashboard does not fetch non-Dashboard domains on cold load**
- target_surfaces:
    - `components/Dashboard.tsx`
- propagation_contract: `useDocumentsQuery`, `useAlertsQuery`, `useFeaturesQuery` have `enabled: false` when current route is `/` (Dashboard)
- resilience: If route detection fails, queries fall back to `enabled: true` — existing behavior, no regression
- visual_evidence_required: Network screenshot showing Dashboard cold load with ≤ 2 requests
- verified_by: T4-003, T4-008 (smoke)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T4-004 | Port optimistic mutations to TQ | Replace manual `pendingFeatureStatusById` optimistic map in `AppEntityDataContext` with TQ `useMutation` for `updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus`. Pattern: `onMutate` snapshot + optimistic update → `onError` rollback → `onSettled` invalidation. Create `services/mutations/features.ts`. | `pendingFeatureStatusById` map removed from `AppEntityDataContext`; three mutation hooks in `services/mutations/features.ts`; unit test: simulate network failure → assert UI rolls back to pre-mutation state within one render cycle. | 1 pt | ui-engineer-enhanced | sonnet | extended | T4-003 |

**AC-B4: Optimistic mutations ported to TQ**
- target_surfaces:
    - `components/ProjectBoard.tsx` (status mutation consumer)
    - `contexts/AppEntityDataContext.tsx` (optimistic map removed after migration)
- resilience: On `onError`, cache is restored to snapshot; UI reflects rollback within one render cycle
- visual_evidence_required: false
- verified_by: T4-004 unit test, T4-008 smoke

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T4-005 | Delete AppEntityDataContext | After all 15 screens individually migrated to domain query hooks and individually runtime-smoked in T4-003: remove `contexts/AppEntityDataContext.tsx` (476 lines). The `AppEntityDataProvider` wrapper in `DataContext.tsx` is removed; `useAppEntityData()` no longer exported. `useData()` shim reads directly from domain query hooks. | `AppEntityDataContext.tsx` file deleted; `AppEntityDataProvider` removed from `DataContext.tsx` provider tree; `useAppEntityData()` no longer exported; `vitest run` green; source-reading guardrail asserts file absent. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T4-004 |
| T4-006 | Shrink AppRuntimeContext to client-state-only | After T4-001, T4-002, T4-005: `AppRuntimeContext` retains only `runtimeStatus` (from health query), `runtimeUnreachable` (derived), `retryRuntime`. `loading` and `error` come from individual domain query hooks, not a global root state. Remove `refreshAllInFlightRef`, `pollingActiveRef`, `consecutiveFailuresRef`, and all domain refresh callbacks. | `AppRuntimeContext.tsx` < 100 lines (target); no `useEffect(fetch)` for domain data; no `setInterval` for polling; remaining: health query, derived `runtimeUnreachable`, `featureSurfaceV2Active` flag read. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T4-005 |
| T4-007 | Thin useData() facade + contexts/__tests__ | Finalize `DataContext.tsx` as a thin ≤50-line facade re-exporting TQ hook values + `AppSessionContext` client-state. Extend `contexts/__tests__/dataArchitecture.test.ts` to assert: `DataContext` has no `createContext()` with server arrays, no `useEffect(fetch)`, no `useState` for session/document/task/feature arrays. Assert `AppDataProviderGate` still gates inner providers. | `DataContext.tsx` ≤ 50 lines; all assertions in `dataArchitecture.test.ts` pass; `useData()` still exports all fields needed by 15 screens; `AppDataProviderGate` preserved. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T4-006 |
| T4-008 | Runtime smoke: ALL 15 screens (P4 karen gate) | Boot dev server. Navigate to all 15 screens: Dashboard, ProjectBoard, SessionInspector, PlanCatalog, Analytics, Workflows, CodebaseExplorer, Planning (Home, AgentSessionBoard, AgentRosterPanel, FeatureAgentLane, TrackerIntakePanel, ArtifactDrillDownPage, GraphPanel, NodeDetail), OpsPanel, Settings, FeatureExecutionWorkbench, TestingPage, Layout. Verify each renders without error, no spinner on back-nav to previously-visited routes. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | All 15 screens load without error; back-nav no spinner; DevTools: Dashboard cold load ≤ 2 requests; no domain fetch on routes that don't need them. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T4-007 |
| T4-009 | karen milestone gate (P4) | Run `karen` milestone review: verify P4 deliverables against PRD ACs (AC-B2, AC-B3, AC-B4), architecture compliance (no eager fan-out at root, TQ-backed facade, client-state-only contexts), and risk status (all HIGH risks resolved or mitigated). | karen review passes; P4 milestone signed off. | 0 pts | karen | sonnet | adaptive | T4-008 |
| T4-010 | task-completion-validator gate (P4) | Validate P4 exit criteria: AppEntityDataContext deleted; contexts client-state-only; Dashboard ≤2 cold requests; all 15 screens smoked; mutations optimistic; karen milestone passed. | Validator passes; P4 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T4-009 |

**AC-B3: useData() facade compatibility preserved during migration**
- target_surfaces:
    - `contexts/DataContext.tsx`
    - `components/Dashboard.tsx`
    - `components/ProjectBoard.tsx`
    - `components/SessionInspector.tsx`
    - `components/PlanCatalog.tsx`
    - `components/Analytics/AnalyticsDashboard.tsx`
    - `components/Workflows/WorkflowRegistryPage.tsx`
    - `components/CodebaseExplorer.tsx`
    - `components/Planning/PlanningHomePage.tsx`
    - `components/Planning/PlanningAgentSessionBoard.tsx`
    - `components/Planning/PlanningAgentRosterPanel.tsx`
    - `components/Planning/PlanningFeatureAgentLane.tsx`
    - `components/OpsPanel.tsx`
    - `components/Settings.tsx`
    - `components/FeatureExecutionWorkbench.tsx`
- propagation_contract: `useData()` is a thin shim reading from TQ hooks + `AppSessionContext`; field shapes unchanged throughout migration window
- resilience: Any TQ hook returning `undefined` data propagates existing falsy defaults already used by consumers
- visual_evidence_required: false
- verified_by: T4-007 (`dataArchitecture.test.ts`), T4-008 (all-screen smoke)

**Phase 4 Quality Gates:**
- [ ] `AppRuntimeContext.tsx` eager fan-out removed; health query polls at 30s; feature fallback at 5s (SSE-gated)
- [ ] `AppEntityDataContext.tsx` deleted; file absent from repo
- [ ] `AppRuntimeContext` < 100 lines; client-state-only
- [ ] `DataContext.tsx` ≤ 50 lines thin facade; `AppDataProviderGate` preserved
- [ ] `services/mutations/features.ts` — three TQ mutations with optimistic pattern
- [ ] `dataArchitecture.test.ts` extended; all assertions green
- [ ] Runtime smoke: all 15 screens — AC-B2, AC-B3, AC-B4 verified
- [ ] `karen` milestone review passed
- [ ] `task-completion-validator` sign-off (P4)
