---
schema_version: 2
doc_type: implementation_plan
title: Feature Surface Remediation - Implementation Plan
description: 'Address four gaps from the feature-surface-data-loading-redesign review:
  G1 app-shell feature refresh decoupling, G2 URL encoding on write paths, G3 FeatureExecutionWorkbench
  migration decision, and G4 runtime smoke validation.'
status: in-progress
created: '2026-04-24'
updated: '2026-04-24'
feature_slug: feature-surface-remediation-v1
feature_version: v1
prd_ref: null
plan_ref: null
scope: 'Close four specific gaps identified in the feature-surface-data-loading-redesign
  review: global feature refresh performance (G1), write-path URL encoding (G2), FeatureExecutionWorkbench
  migration scope (G3), and runtime smoke validation (G4).'
effort_estimate: 5-6 story points
architecture_summary: Three independent phases addressing backend resilience (G2 encoding),
  frontend performance (G1 decoupling), and validation (G3 decision doc + G4 smoke
  test). No architectural changes required.
related_documents:
- /docs/project_plans/reports/feature-surface-data-loading-redesign-review-2026-04-24.md
- /docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
- /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
references:
  related_prds:
  - /docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: .claude/findings/feature-surface-remediation-findings.md
changelog_required: false
owner: null
contributors: []
priority: high
risk_level: medium
category: harden-polish
tags:
- remediation
- feature-surface
- performance
- encoding
- validation
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- services/apiClient.ts
- contexts/AppEntityDataContext.tsx
- services/__tests__/apiClient.test.ts
- backend/tests/test_client_v1_write_paths.py
- components/FeatureExecutionWorkbench.tsx
- .claude/progress/feature-surface-remediation-v1/phase-1-progress.md
---

# Implementation Plan: Feature Surface Remediation

**Plan ID**: `IMPL-2026-04-24-FEATURE-SURFACE-REMEDIATION`
**Date**: 2026-04-24
**Author**: Implementation Planner
**Related Documents**:
- **Review Report**: `/docs/project_plans/reports/feature-surface-data-loading-redesign-review-2026-04-24.md`
- **Parent PRD**: `/docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md`
- **Parent Plan**: `/docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md`

**Complexity**: Small (S)
**Total Estimated Effort**: 5–6 story points
**Target Timeline**: 1–2 weeks (three independent phases)

## Executive Summary

The feature-surface-data-loading-redesign (parent plan) achieved its core objectives — ProjectBoard now loads from bounded v2 contracts and the modal uses lazy section loading. Four gaps remain:

1. **G1 (high, perf)**: `AppEntityDataContext.refreshFeatures()` still loads the legacy 5000-row `/api/features` endpoint globally, even when ProjectBoard renders from v2 surfaces. Gate the refresh on opt-in v2 bounded list OR fully decouple ProjectBoard's surface from the app-shell global provider.

2. **G2 (high, bug)**: `services/apiClient.ts` write paths (`updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus`) do not encode feature/phase/task IDs in URL paths. Add `encodeURIComponent()` and test with IDs containing `#`, `?`, `&`, and spaces.

3. **G3 (medium, tech-debt)**: `FeatureExecutionWorkbench` selected-feature detail — decide whether it is exempt from v2 migration (user-initiated) or should move sessions tab to the paginated surface. Document decision in a brief spec.

4. **G4 (medium, test)**: Runtime smoke was skipped for phases 4–5 of the parent plan. Run browser smoke: ProjectBoard card load network trace (verify request count), modal tab lazy-load waterfall, cache invalidation on feature update. Record findings in progress.

This plan splits remediation into three parallelizable phases: G2 encoding (backend + frontend tests), G1 decoupling (frontend refactor), and G3–G4 validation (docs + smoke test).

---

## Implementation Strategy

### Architecture Sequence

No new database, repository, or service layers. All work is within existing contracts:
- **API Layer**: G2 requires no backend changes; encoding happens in client paths.
- **UI Layer**: G1 requires `AppEntityDataContext` refactor and ProjectBoard re-wiring.
- **Testing & Validation**: G2 needs new unit tests; G4 needs browser trace capture.
- **Documentation**: G3 requires a brief decision doc.

### Parallel Work Opportunities

1. **Phase 1 (G2 encoding)** and **Phase 2 (G1 decoupling)** are independent and can proceed in parallel.
2. **Phase 3 (G3 decision + G4 smoke)** depends only on phases 1–2 being complete (for validation context).

### Critical Path

1. Phase 1: URL encoding (1–2 pts) — unblocks G2 QA and risk closure.
2. Phase 2: App-shell decoupling (2–3 pts) — addresses the dominant app-level performance gap.
3. Phase 3: Decision doc + smoke validation (1 pt) — confirms phases 1–2 did not regress performance.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|-------------------|----------|-------|
| 1 | G2: URL Encoding on Write Paths | 1–2 pts | frontend-developer, python-backend-engineer | sonnet | Client-side encoding + unit tests + optional backend validation |
| 2 | G1: App-Shell Feature Refresh Decoupling | 2–3 pts | ui-engineer-enhanced, frontend-developer | sonnet | RefreshContext → ProjectBoard surface; network trace AC with evidence |
| 3 | G3–G4: FeatureExecutionWorkbench Decision + Runtime Smoke | 1 pt | task-completion-validator, documentation-writer | haiku/sonnet | Brief spec for G3 + browser smoke pass for G4; record in progress |
| **Total** | — | **5–6 pts** | — | — | Three independent phases; G1 qualifies as UI-touching (Rule R-P4 smoke required) |

---

## Estimation Sanity Check (Mandatory)

**H1: Noun counting** – New CRUD with RBAC: none. This is remediation, not new entities.

**H2: Dual-implementation multiplier** – No new backend surfaces; encoding is client-side only. Skip.

**H3: Algorithmic service flag** – No algorithmic work; decoupling is refactoring. Skip.

**H4: Bundle-vs-sum** – Single capability area (feature-surface refinement). Bottom-up:
- G2 (encoding): ~1 pt (change 3 methods, add 6 test cases)
- G1 (decoupling): ~2.5 pts (refactor `AppEntityDataContext` + ProjectBoard re-wiring + network AC verification)
- G3–G4 (validation): ~1 pt (spec + smoke + findings recording)
- **Total**: 4.5 pts → round to 5–6 pts for fuzzy scope (network trace AC, potential G1 edge cases).

**H5: Anchor reference** – Parent plan feature-surface was 85 pts over 5 phases; this is a 6–8% follow-up for gap closure and validation. Reasonable.

**H6: Hidden plumbing budget** – Minimal (no DTOs, migrations, or DI changes). 15–20% of bottom-up = ~0.7–1.2 pts, absorbed in phase estimates.

**Conclusion**: Bottom-up 5–6 pts is sound. All four gaps have clear scope boundaries.

---

## Deferred Items & In-Flight Findings Policy

**No deferred items.** All gaps have concrete scope and clear acceptance criteria. G3 is fully scoped as a decision-doc task within Phase 3.

**Findings**: If runtime smoke (G4) uncovers unexpected regressions, create `.claude/findings/feature-surface-remediation-findings.md` and update `findings_doc_ref` in this plan's frontmatter.

---

## Phase Breakdown

### Phase 1: G2 — URL Encoding on Write Paths

**Duration**: 1–2 days
**Dependencies**: None (independent from other phases)
**Assigned Subagent(s)**: frontend-developer (primary), python-backend-engineer (secondary for optional backend validation)
**Model**: sonnet

#### Context

The parent plan assumed feature/phase/task IDs with reserved URL characters (e.g., `FEAT-123#draft`, `PHASE-A?status=active`) would fail silently or bypass validation. `services/apiClient.ts` write paths use raw string interpolation: `updateFeatureStatus(featureId, status)` → `/features/${featureId}/status`. This breaks for IDs containing `#`, `?`, `&`, or spaces.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| G2-001 | Encode feature/phase/task IDs in `apiClient.ts` write paths | Update `updateFeatureStatus()`, `updatePhaseStatus()`, `updateTaskStatus()` to call `encodeURIComponent(featureId)` and equivalent for phase/task IDs before building URL strings. Include inline comment citing URL RFC 3986 reserved character rules. | Three methods use `encodeURIComponent()` on all ID params; no raw string interpolation in URL paths; inline docs reference RFC 3986 § 2.2 | 0.5 pts | frontend-developer | none |
| G2-002 | Unit test encoding with reserved-char IDs | Add test cases in `services/__tests__/apiClient.test.ts` covering: `#`, `?`, `&`, space, `%`, `+`. Verify that fetch calls encode the params and the backend receives decoded IDs correctly. | ≥6 test cases for mixed ID strings; all pass; no encoding/decoding round-trip bugs | 0.5 pts | frontend-developer | G2-001 |
| G2-003 | Optional: Backend validation of decoded IDs | Add a short note or optional test in `backend/tests/test_client_v1_write_paths.py` to confirm that `updateFeatureStatus(..., featureId="FEAT-123#draft")` resolves to the correct feature after client encoding and server decoding. | Test passes if a feature with special-char ID is correctly updated via the encoded path; skip if backend tests already cover this or if backend accepts raw IDs without decoding. | 0 pts (optional) | python-backend-engineer | G2-002 |

#### Quality Gate

- All three methods in `services/apiClient.ts` encode IDs with `encodeURIComponent()`.
- Unit tests exercise at least 6 reserved-character combinations.
- Existing tests for `updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus` remain green after changes.

---

### Phase 2: G1 — App-Shell Feature Refresh Decoupling

**Duration**: 2–3 days
**Dependencies**: None (independent from Phase 1; both can run in parallel)
**Assigned Subagent(s)**: ui-engineer-enhanced (primary), frontend-developer (secondary)
**Model**: sonnet

#### Context

`AppEntityDataContext.refreshFeatures()` calls `client.getFeatures()` → `/api/features?offset=0&limit=5000`, which loads all features globally. Even though ProjectBoard itself renders from bounded v2 surfaces (via `useFeatureSurface`), the app-shell refresh runs on init, every 30 seconds, on live invalidation, and on 5-second fallback polling. This preserves a costly global request even when no component needs the full-list data.

The gap is architectural: the app-shell global provider and the ProjectBoard surface provider are decoupled in *consumption* but not in *refresh triggers*. Either gate the global refresh on a v2 bounded-list endpoint, or fully separate ProjectBoard's surface from the global provider.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| G1-001 | Decouple ProjectBoard from `AppEntityDataContext.refreshFeatures()` | Refactor `contexts/AppEntityDataContext.tsx` so that ProjectBoard (and any other surface) can opt-in to using v2 bounded surfaces via `useFeatureSurface` hook without triggering the global legacy `/features?limit=5000` refresh. Options: (a) add an opt-in flag to the refresh trigger, or (b) move ProjectBoard's `useFeatureSurface` data fetch outside the global provider context. Choose option in coordination with the implementation. | ProjectBoard no longer depends on `AppEntityDataContext.refreshFeatures()`; refresh logic is still available for legacy consumers; no circular dependencies between contexts. | 1.5 pts | ui-engineer-enhanced | none |
| G1-002 | Update ProjectBoard to independently manage surface cache invalidation | Ensure ProjectBoard's surface cache invalidates on live feature/session/task updates and syncs independently of the global provider refresh cycle. Wire `useLiveInvalidation` into `useFeatureSurface` or equivalent. | Feature modal updates trigger immediate surface cache invalidation; network trace shows no stale card metrics after update; no race conditions between invalidation and UI render. | 1 pt | frontend-developer | G1-001 |
| G1-003 | Acceptance: Network trace for ProjectBoard initial load | Capture Chrome DevTools network trace for ProjectBoard initial load (first page load, default filters). Measure: total request count (must be ≤ 3: list, rollups, plus optional modal data), total payload size (should be <500 KB for 50 features). Record baseline + post-refactor trace in progress file. | Network trace artifact saved; request count documented; initial-load payload size ≤ 500 KB; `target_surfaces` lists AppEntityDataContext → ProjectBoard, SessionInspector, Dashboard consumers. | 0.5 pts | ui-engineer-enhanced | G1-002 |

#### Structured Acceptance Criteria (Multi-Surface)

**AC: Network Request Count Bounded on Initial ProjectBoard Load**

- **target_surfaces**:
  - `contexts/AppEntityDataContext.tsx` (global refresh trigger)
  - `components/ProjectBoard.tsx` (card list + rollup rendering)
  - `services/apiClient.ts` (fetch orchestration)

- **propagation_contract**: ProjectBoard uses `useFeatureSurface` hook (decoupled from `AppEntityDataContext` global refresh); live invalidation re-fetches surface cache independently of app-shell refresh cycle.

- **resilience**: If `AppEntityDataContext.refreshFeatures()` is still called by legacy consumers (SessionInspector, Dashboard), those consumers see bounded v2 data if the opt-in flag is set; fallback to legacy `/features?limit=5000` if flag is unset (graceful degradation).

- **visual_evidence_required**: Chrome DevTools network trace (desktop ≥1440px) showing ProjectBoard load with ≤3 requests before first paint (list, rollups, and optional prefetch).

- **verified_by**: G1-003 (network trace capture + payload measurement).

#### Quality Gate

- Network trace confirms initial ProjectBoard load = ≤ 3 API requests (list, rollup, optional modal prefetch).
- Payload size ≤ 500 KB for first page (50 features, default filters).
- Live invalidation on feature status update does not cause "flash" or stale card render.
- Existing tests for SessionInspector, Dashboard, and AppRuntimeContext remain green.

---

### Phase 3: G3–G4 — FeatureExecutionWorkbench Decision + Runtime Smoke Validation

**Duration**: 1–2 days
**Dependencies**: Phases 1–2 should be complete for context; can start in parallel after Phase 1 completes
**Assigned Subagent(s)**: task-completion-validator (primary), documentation-writer (secondary)
**Model**: haiku (spec), sonnet (smoke trace capture if needed)

#### Context

**G3 (scope decision)**: `FeatureExecutionWorkbench` selected-feature detail currently loads via `getFeatureExecutionContext(selectedFeatureId)` and uses `context.sessions` for the sessions tab, not the paginated `useFeatureSurface` surface. The parent plan (P4-008) is ambiguous: "migrate to paginated surface" could mean optional (user-initiated loading is acceptable) or mandatory (move all detail onto v2 contracts). This gap requires a decision doc to clarify scope and future maintenance burden.

**G4 (validation)**: Phases 4–5 of the parent plan skipped runtime smoke tests (browser interactions, network waterfall, visual behavior). This phase runs a targeted smoke pass: ProjectBoard card load + modal tab transitions + cache invalidation on feature status update. Findings are recorded in progress.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| G3-001 | Author FeatureExecutionWorkbench migration decision spec | Create a brief design spec (`.claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md`) deciding: (a) FeatureExecutionWorkbench is exempt from v2 migration because user-selected detail loads are not eagerly prefetched, OR (b) the selected-feature sessions tab should migrate to `useFeatureSurface` + paginated API. Include rationale (maintenance burden, adoption risk, performance delta). No code changes — spec only. | Spec file exists at `.claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md`; decision is stated in executive summary (option a or b); rationale includes maintenance and performance considerations; status set to `draft` pending review. | 0.5 pts | documentation-writer | none |
| G4-001 | Browser smoke: ProjectBoard card load network waterfall | Start fresh browser session, navigate to feature board with default filters (first 50 features). Capture Chrome DevTools network trace. Verify: (1) list request + rollups request + optional session prefetch = ≤ 3 total, (2) no per-feature `/features/{id}/linked-sessions` calls, (3) all cards render correctly with badge metrics (status, token count, document coverage). Save trace artifact. | Network trace file saved to progress; request count ≤ 3; no eager per-feature calls detected; cards render complete with all badges. | 0.25 pts | task-completion-validator | G1-003 (after Phase 2) |
| G4-002 | Browser smoke: Modal lazy-load tab waterfall | Open feature modal. Verify: (1) modal loads overview immediately (≤1 request), (2) click Phases tab → lazy fetch (1 request, quick), (3) click Sessions tab → lazy fetch with paging (1 request, expected latency for session detail), (4) switch tabs repeatedly → cache hit, no re-fetch. Record findings. | Modal overview tab loads in <500ms; each tab fetch is lazy (only on tab click); tab re-opens use cache (no network call on second open); findings recorded in progress. | 0.25 pts | task-completion-validator | G1-003, G2-002 (after Phases 1–2) |
| G4-003 | Browser smoke: Feature status update → invalidation → re-render | Open ProjectBoard. Update a feature status via the detail panel. Verify: (1) network trace shows status update request, (2) card immediately updates (cache invalidated), (3) no stale card state or duplicate re-fetches. Record trace and findings. | Status update request and card re-render occur within 2 seconds; no stale card state; cache invalidation is explicit (no polling fallback visible in network trace). | 0.25 pts | task-completion-validator | G1-002, G2-001 (after Phases 1–2) |
| G4-004 | Record findings and closure | Consolidate smoke test findings into progress file (`.claude/progress/feature-surface-remediation-v1/phase-3-progress.md`). If any regressions or unexpected findings surface, create `.claude/findings/feature-surface-remediation-findings.md` and update plan's `findings_doc_ref`. Mark phase 3 as complete. | Progress file populated with smoke test results (pass/fail per test case); any findings documented with context and impact; plan frontmatter `findings_doc_ref` updated if needed. | 0 pts (recording only) | task-completion-validator | G4-001, G4-002, G4-003 |

#### Quality Gate

- G3 spec file exists and is readable.
- G4 browser smoke passes all three test cases (network trace, modal lazy-load, invalidation).
- No new regressions detected in smoke pass; if findings emerge, they are documented.
- Progress file records test artifacts (trace filenames, key measurements, known gaps if any).

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| **G2 encoding breaks existing feature IDs in tests** | Low | Encoding is additive; existing IDs without special chars are unaffected. Add tests to verify round-trip encoding/decoding. |
| **G1 decoupling introduces race condition between global and surface refresh** | Medium | Use explicit cache invalidation triggers (live events) rather than polling fallback; test with concurrent updates. |
| **G3 decision remains ambiguous** | Low | Spec requirement forces explicit statement; future PRD can clarify if needed. |
| **G4 smoke reveals unexpected regressions** | Medium | Treat as findings; create issue and prioritize fixes before merging Phases 1–2. |

---

## Quality Gates & Verification

### Phase 1 Quality Gate (G2 Encoding)

- [ ] Three write methods in `apiClient.ts` use `encodeURIComponent()` on all ID params.
- [ ] Unit tests pass: 6+ test cases with reserved characters.
- [ ] Existing tests for `updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus` remain green.
- [ ] No encoding/decoding round-trip bugs in browser console or backend logs.

### Phase 2 Quality Gate (G1 Decoupling)

- [ ] ProjectBoard no longer depends on `AppEntityDataContext.refreshFeatures()`.
- [ ] Network trace confirms ≤ 3 initial requests for ProjectBoard load.
- [ ] Live invalidation on feature update triggers surface cache refresh (not global polling).
- [ ] SessionInspector and Dashboard tests remain green (or are intentionally migrated to v2).
- [ ] Payload size ≤ 500 KB for first page (50 features).

### Phase 3 Quality Gate (G3–G4 Validation)

- [ ] G3 spec file exists and decision is stated.
- [ ] G4 browser smoke: All three test cases pass (network, modal, invalidation).
- [ ] Progress file documents test artifacts and findings.
- [ ] If findings are load-bearing, `.claude/findings/feature-surface-remediation-findings.md` exists.

---

## Implementation Notes

1. **G2 encoding is client-side only** — no backend changes required. The backend will receive decoded IDs through the standard FastAPI/Starlette routing layer.

2. **G1 decoupling requires coordination** — decision to gate the global refresh OR decouple ProjectBoard should be made early in Phase 2 to avoid mid-phase refactoring.

3. **G3 decision doc is low-effort** — 30-minute spec authoring; main value is explicit scope statement for future maintenance.

4. **G4 smoke is manual** — use browser DevTools network trace capture; consider automating with Playwright if the project adopts E2E test infrastructure later.

5. **Phases 1 and 2 can run in parallel** — no shared dependencies. Phase 3 should start after Phase 1 (for G3 context) but can validate Phases 1–2 together.

---

## Files Affected

**Frontend**:
- `services/apiClient.ts` (G2: encode IDs)
- `services/__tests__/apiClient.test.ts` (G2: test encoding)
- `contexts/AppEntityDataContext.tsx` (G1: decouple refresh)
- `components/ProjectBoard.tsx` (G1: use surface hook)
- `services/live/useLiveInvalidation.ts` (G1: wire invalidation)

**Backend** (optional):
- `backend/tests/test_client_v1_write_paths.py` (G2: optional validation)

**Documentation / Specs**:
- `.claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md` (G3)
- `.claude/progress/feature-surface-remediation-v1/phase-1-progress.md` (execution tracking)
- `.claude/progress/feature-surface-remediation-v1/phase-2-progress.md` (execution tracking)
- `.claude/progress/feature-surface-remediation-v1/phase-3-progress.md` (execution tracking)
- `.claude/findings/feature-surface-remediation-findings.md` (if needed for G4 findings)

---

## Success Criteria

1. **G2**: Feature/phase/task IDs with reserved URL characters work correctly in all write paths. No silent failures or encoding bugs.

2. **G1**: ProjectBoard initial load = ≤ 3 API requests. Global `AppEntityDataContext.refreshFeatures()` no longer blocks ProjectBoard rendering.

3. **G3**: Explicit scope decision documented for FeatureExecutionWorkbench's v2 migration status (exempt or target).

4. **G4**: No unexpected regressions in browser smoke pass. All three test cases (network, modal, invalidation) demonstrate expected behavior.

All gaps from the review report are closed, and the parent feature-surface-data-loading-redesign implementation is validated as complete.
