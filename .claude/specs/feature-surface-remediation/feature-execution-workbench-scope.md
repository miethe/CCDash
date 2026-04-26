---
schema_version: 2
doc_type: design-spec
title: "FeatureExecutionWorkbench Migration Scope Decision"
status: draft
created: 2026-04-24
feature_slug: feature-surface-remediation-v1
plan_ref: docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
tags: [feature-surface, scope-decision, workbench]
---

# FeatureExecutionWorkbench Migration Scope Decision

## Executive Summary

**Decision: Option (b) — Migrate sessions tab to `useFeatureSurface` + paginated `/api/v2/...` API.**

The FeatureExecutionWorkbench currently uses `useFeatureSurface` (v2 bounded surface) for the sidebar picker but loads selected-feature detail via the legacy `getFeatureExecutionContext` endpoint. While user-initiated selection means request volume is low, consolidating on the v2 surface layer reduces maintenance burden, clarifies the API contract for future detail screens, and eliminates divergent implementations. The effort is minimal (~0.5 pts) because the picker already uses the surface; only the session-detail rendering path changes.

---

## Background

### Parent Plan (P4-008) Coverage

The feature-surface-data-loading-redesign parent plan (5 phases, 85 pts, completed 2026-04-24) reshaped feature board loading:
- **Phase 3**: ProjectBoard now fetches from bounded `useFeatureSurface` (list + rollup), not per-card eager calls.
- **Phase 4**: Extended migration to "cross-surface": SessionInspector, FeatureExecutionWorkbench, Dashboard, and planning cache coordination.

The Phase 4 task for FeatureExecutionWorkbench (P4-008) was worded: "Migrate FeatureExecutionWorkbench's picker and selected-feature loading to surface contracts." This is ambiguous—does it mean "picker only" (user-selected, low volume) or "picker + detail" (both lazy-load)?

### Current Workbench Data Flows

1. **Picker/List** (line 607-609): Already migrated. Uses `useFeatureSurface({ rollupFields: [...] })` to load bounded, cached feature cards. No per-feature eager calls. ✅
2. **Selected-Feature Detail** (line 1067): Still legacy. Calls `getFeatureExecutionContext(selectedFeatureId)`, which returns a rich `FeatureExecutionContext` object including `context.sessions`. This is the ambiguous scope item.

The sessions tab rendering (visible when tab='sessions') reads `context.sessions`, which is an array loaded eagerly by `getFeatureExecutionContext`.

### Request Profile

- **Picker**: ~50 features, 1 list + 1 rollup = 2 requests total (already bounded and cached via v2 surface).
- **Selected detail**: User clicks a feature → 1 call to fetch detail. No eager prefetch for unselected features.
- **Total impact if left as-is**: Low (1 selected feature = 1 call). NOT a hot-path performance bottleneck.

However, the **architecture signal** is that two parallel implementations exist: surface-based (picker) and legacy-based (detail).

---

## Options Considered

### Option (a): Exempt from v2 Migration

**Rationale:**
- User-initiated selection means `getFeatureExecutionContext` calls are not eagerly prefetched. Request volume is ~1 per user interaction, not N per board render.
- Sessions tab is an implementation detail; the feature surface contracts (`/api/v1/features/{id}/sessions`) are for feature card metrics, not workbench execution detail.
- Execution context includes rich metadata (recommendations, policy state, execution runs, etc.) that is specific to the workbench; wrapping this in generic feature-surface DTOs adds friction.
- Maintenance cost is low: `getFeatureExecutionContext` is already implemented and tested.

**Con:**
- Divergence: The workbench uses both v2 (picker) and legacy (detail). Future developers may copy the legacy pattern for new detail screens, perpetuating two API styles.
- Future drift: If the legacy endpoint is eventually deprecated, workbench will need refactoring. Deferring migration shifts cost to later.
- Test duplication: Two parallel test patterns (surface cache tests vs. context tests).

### Option (b): Migrate to useFeatureSurface + Paginated Sessions

**Rationale:**
- **Consistency**: All feature-detail loading in the app uses the same v2 surface API. Clearer contract for future screens.
- **Reduced complexity**: One caching strategy (surface LRU), one invalidation path (feature cache bus). The workbench no longer maintains a separate context load + manual state refresh.
- **Future-proof**: If legacy endpoints are retired, workbench is already on the new contract.
- **Effort is minimal**: The picker already uses `useFeatureSurface`. The detail tab only needs to route session data through the existing `useFeatureModalData` hook (line 77, already imported but not used in workbench).
- **Contract alignment**: The feature-surface architecture guide explicitly documents `useFeatureModalData` for modal sections, including sessions pagination. Workbench detail is semantically a modal-like detail view.

**Con:**
- Workbench execution context includes non-feature fields (execution runs, policy checks, etc.). Separating these from feature detail requires composition or a separate workbench-specific API layer.
- Slightly larger payload for the common case (feature overview always loads; execution data is added on demand).

---

## Decision

**Option (b) — Migrate to v2 surfaces.**

**Numbered rationale:**

1. **Architectural consistency wins**: Single API pattern (v2 surfaces) for all feature-detail loading eliminates decision paralysis for future screens. Workbench is the last major cross-surface consumer; consolidation now prevents drift.

2. **Maintenance clarity**: One caching strategy (`useFeatureSurface` + `useFeatureModalData` + feature cache bus) is easier to reason about than parallel legacy + modern flows. Developers no longer ask "which API do I use for detail screens?"

3. **Minimal effort**: The workbench picker already uses `useFeatureSurface`. The selected-feature detail tab only needs to integrate `useFeatureModalData(selectedFeatureId)` for sessions pagination and route execution-specific state through a separate workbench context. Estimated ~0.5 story points of refactoring.

4. **Future deprecation readiness**: When legacy endpoints are retired, workbench is already compliant. No late-stage migration surprise.

5. **Scalability for execution metadata**: Execution context data (policy state, run history, recommendations) can be sourced independently of feature surface, composed alongside modal sections at the component level. This is cleaner than bloating the feature-surface contract.

---

## Consequences

### If Chosen: Migration Tasks

Estimated effort: **0.5 story points** (Phase 3 of the remediation plan, task G3–G4-005 or similar).

**Refactoring scope:**
1. Replace `getFeatureExecutionContext(selectedFeatureId)` calls with `useFeatureModalData(selectedFeatureId)` for session-list and session-pagination data.
2. Keep execution-specific state (runs, policy checks, recommendations) in a separate workbench-only context or directly in component state.
3. Update the sessions tab render path to use `sections['sessions'].load(params)` instead of `context.sessions`.
4. Verify invalidation wiring: Feature cache bus events should clear the modal section cache (already implemented for feature updates in phase-4).

**Files touched:**
- `components/FeatureExecutionWorkbench.tsx` (primary)
- `services/execution.ts` (optional: create `getExecutionRecommendations()` if not already separate from context)
- `services/__tests__/FeatureExecutionWorkbench.test.ts` (update mock data sources)

**Performance delta:** Negligible. Sessions are loaded on-demand (user clicks tab); paginated surface will load the same data via the same endpoint. No slowdown; slight memory reduction due to unified cache (surface LRU vs. context state).

### If Deferred: Maintenance Burden

- Two API patterns remain in active use (surface + legacy context).
- FeatureExecutionWorkbench stands alone as the exception to "all detail screens use v2."
- Risk: New feature screens (e.g., future execution-detail panel) copy the workbench pattern (context-based) instead of surface-based, creating more fragmentation.

---

## Follow-Ups & Open Questions

1. **Execution context shape**: Are `recommendations`, `executionRuns`, and `policy` state mutually exclusive with feature-surface fields, or do they overlap? (Answer: They are mutually exclusive; workbench-specific, not shared with planning or board views.)

2. **Backwards compatibility**: Does `getFeatureExecutionContext` need to remain in the API for external consumers, or can it be removed after workbench migration? (Deferred to Phase 5 / deprecation planning.)

3. **Sessions tab pagination state**: How should page navigation be wired in the workbench UI? (Reuse `useFeatureModalData` section state, which handles pagination and caching.)

---

## Acceptance Criteria

- [ ] Spec approved (status: `approved`)
- [ ] Refactoring completes with all tests passing
- [ ] No per-feature eager calls introduced (verify with network trace)
- [ ] Sessions tab pagination works correctly (load page 1, 2, … on user interaction)
- [ ] Feature cache bus invalidation clears modal section cache on feature write
- [ ] Existing workbench UI behavior and performance remain unchanged
