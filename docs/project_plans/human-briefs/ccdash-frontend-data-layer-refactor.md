---
schema_name: ccdash_document
schema_version: 2

doc_type: human_brief
doc_subtype: feature_brief
root_kind: project_plans

id: BRIEF-ccdash-frontend-data-layer-refactor
title: "CCDash Frontend Data Layer Refactor — Human Brief"
status: draft
category: human-briefs

feature_slug: ccdash-frontend-data-layer-refactor
feature_family: ccdash-frontend-data-layer-refactor
feature_version: v1

prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
intent_ref: null
epic_ref: null

related_documents:
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/decisions-block.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-frontend.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-backend.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md

owner: null
contributors: []

audience: [humans]

priority: high
confidence: 0.82

created: 2026-05-28
updated: 2026-05-28
target_release: ""

tags: [human-brief, tanstack-query, data-layer, refactor, performance]
---

# CCDash Frontend Data Layer Refactor — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-05-28

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- **Plan (root)**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- **Phase 0–2**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/phase-0-2-foundation-and-domains.md`
- **Phase 3–4**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/phase-3-4-cache-and-context-teardown.md`
- **Phase 5–7**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/phase-5-7-backend-virtualization-validation.md`
- **Decisions Block**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/decisions-block.md`
- **Frontend Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-frontend.md`
- **Backend Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-backend.md`
- **Prior Art Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md`
- **Design Specs (deferred)**: `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md` (authored in P7)
- **SPIKEs**: None — SPIKE waived (Tier 3); three inventory worknotes serve as research basis
- **Related Briefs**: None
- **Prior refactor**: `docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md` (partial prior art — the two-tier cache being retired was built in this prior plan)

---

## 2. Estimation Sanity Check

_Migrated from decisions block §4. Human-authored; not agent-relevant._

**Bottom-up total**: 31 pts (Epics A–C committed) + 1 pt (Epic D gate artifact) = **32 pts** / ~4–6 engineer-weeks
**Top-down anchor**: `feature-surface-data-loading-redesign-v1` (prior FE data-loading refactor) and `ccdash-planning-reskin-v2` (planning SWR cache) both confirm a 30+ pt multi-phase FE refactor is in-family for this codebase
**Reconciliation**: Bottom-up and top-down agree within ~10%. Trust bottom-up.

H1–H6 heuristic application:

- **H1 (noun-counting)**: No new CRUD-with-RBAC domain nouns (this is a refactor, not a greenfield feature). 0 new tables. H1 floor = 0 — does not inflate the estimate. The complexity is in retiring existing infrastructure, not adding new.

- **H2 (dual-implementation multiplier)**: Not applicable — this is a pure frontend refactor with backend bundle endpoints added as composition (no new repository interfaces). Backend bundle endpoints are DTO composition over existing repositories, not new dual-impl repos. H2 not applied.

- **H3 (algorithmic flag)**: Three algorithmic surfaces identified:
    - P1 (3 pts): `useInfiniteQuery` with cursor pagination — dedup semantics, back-nav cache restore, page-flattening (SWR/dedup algorithmic). Budgeted at 3 pts with `extended` effort.
    - P3 (5 pts): Planning freshness-bucket keying TQ mapping — `dataFreshness` token folded into queryKey; `staleTime` design for the rollup tier; cache bus replacement. Budgeted at 5 pts with `extended` effort.
    - P4 (4 pts): 15-screen facade migration with live-SSE/polling interplay — refetchInterval mapping, SSE suppression logic, context teardown ordering. Budgeted at 4 pts with `extended` effort.

- **H4 (bundle-vs-sum)**: Four capability areas independently estimated:
    | Area | Independent Est. | Notes |
    |------|-----------------|-------|
    | Epic A: TQ foundation + sessions | 2 + 3 = 5 pts | P0 + P1 |
    | Epic B: Remaining domains + cache consolidation + context teardown | 5 + 5 + 4 = 14 pts | P2 + P3 + P4 |
    | Epic C: Backend bundles + virtualization | 6 + 3 = 9 pts | P5 + P6 |
    | Epic D gate artifact: Docs + entry-criteria spec | 2 + 1 = 3 pts | P7 |
    | **Σ** | **31 committed + 1 gate = 32 pts** | Bottom-up floor confirmed |
    
    Plan total (31 committed + 1 gate) ≥ Σ (32). Consistent.

- **H5 (anchor reference)**: 
    - **Anchor 1**: `feature-surface-data-loading-redesign-v1` — prior FE data-loading refactor (two-tier LRU + SWR cache). Estimated ~8–10 pts at the time; landed on schedule. This plan retires that cache and adds TQ system-wide — broader scope, consistent with a ~3x multiplier on the anchor.
    - **Anchor 2**: `ccdash-planning-reskin-v2` — planning SWR cache build (~10 pts). Confirms that a single complex cache system is ~5 pts. P3 (cache consolidation of TWO systems) at 5 pts is right-sized.
    - Delta justification: This plan's 31 pts vs anchor 8–10 pts = ~3–4x. Delta justified by: (a) six more domains to migrate beyond the feature-surface anchor, (b) root context teardown across 15 screens, (c) three new backend bundle endpoints, (d) three virtualizer integrations. All capability areas decomposed and independently estimated. Trust H4 bundle-vs-sum over anchor ratio.

- **H6 (hidden plumbing budget)**: Absorbed into P0 and P7. Explicit items: `queryKey` registry hygiene (~0.5 pts in P0), devtools wiring (P0), CLAUDE.md pointer (P7 T7-005), `deferred_items_spec_refs` maintenance (P7 T7-008). Net plumbing = ~1–1.5 pts ≈ 5% of subtotal. Below the 15–20% H6 guideline because this is a refactor (no new OpenAPI schemas, no RLS, no new DI wiring beyond TQ provider). H6 accepted at 5%.

**Locked estimate**: 31 pts (Epics A–C) + 1 pt (Epic D gate) = **32 pts**.

---

## 3. Wave & Orchestration Notes

**Critical path**: P0 → P1 → P2 → P3 → P4 → P7. The FE migration spine gates everything. P4 is the highest-risk phase — `AppEntityDataContext` deletion requires ALL consumers individually migrated and smoked.

**Parallel opportunities**:
- **P5 backend** can start immediately after P0 (disjoint files: `backend/routers/`, `agent_queries/`). Run in parallel with P2/P3/P4. Assign python-backend-engineer to P5a while ui-engineer-enhanced owns the FE migration spine.
- **P6 virtualization** can start after P2 completes (domain hooks exist). Run in parallel with P3/P4. Virtualization touches list-render code, independent of context teardown.
- **P5 FE wiring** (P5b) joins after P4 + P5a backend endpoint ships — this is the latest of the three parallel tracks to converge.

**Merge order**: P0 first (prerequisite). Then P1 → P2 → P3 → P4 in sequence (FE spine). P5a and P6 can merge as they complete independently. P5b merges after P4 + P5a. P7 is the final merge.

**Wave plan summary**:
- Wave 1: P0 (foundation, serial prerequisite)
- Wave 2: P1 (sessions slice) + P5a backend start
- Wave 3: P2 (remaining domains) + P6 start
- Wave 4: P3 (cache consolidation, serial)
- Wave 5: P4 (context teardown, serial) + P5b FE wiring
- Wave 6: P7 (validation + docs, serial)

**Cross-feature coupling**: `CCDASH_FEATURE_SURFACE_V2_ENABLED` flag must remain functional during P3 — the feature surface v2 path is the primary consumer of `featureSurfaceCache.ts` being retired. The TQ-backed `useFeatureSurface` adapter (P3 T3-004) must preserve the flag gate behavior.

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | Decisions block §7, PRD §12 | `useInfiniteQuery` vs offset pagination for session list | Resolved | Plan P1: `useInfiniteQuery` — matches existing "Load more" UX; `loadMoreSessions` replaced by `fetchNextPage()` |
| OQ-2 | Decisions block §7 | How to represent planning.ts freshness-bucket keying in TQ | Resolved | Plan P3: fold `dataFreshness` token into queryKey array; new `dataFreshness` = new key = new fetch |
| OQ-3 | Decisions block §7 | Delete `useData()` facade at end of P4 or keep as permanent thin shim | Resolved | Plan P4: keep minimal shim (≤50 lines); avoids touching 24 import sites in one sweep |
| OQ-4 | Decisions block §7 | Migration flag mechanism (runtime vs build-time) | Resolved | Plan P0: `VITE_CCDASH_QUERY_DEVTOOLS` flag only (devtools visibility); no per-deploy rollback flag needed (incremental + facade-preserved migration) |
| OQ-5 | Decisions block §7 | Do bundle endpoints need new `agent_queries` methods? | Resolved | Plan P5: compose existing cached reads (same as `planning.summary` helpers at `planning.py:787-857`); no new `agent_queries` methods needed |
| OQ-6 | Decisions block §7 | `refetchInterval` mapping for 30s health + 5s feature polls | Resolved | Plan P4: health query = 30s; alerts/notifications = 30s; features live-mode fallback = 5s when `VITE_CCDASH_LIVE_FEATURES_ENABLED=false`; SSE-connected paths set `refetchInterval: false` |
| OQ-PRD-1 | PRD §12 | Should `useInfiniteQuery` replace offset pagination for session list? | Resolved | Consistent with OQ-1 above |
| OQ-PRD-2 | PRD §12 | Does `ModelColorsContext` warrant migration in this PRD? | Resolved (deferred) | Deferred — single low-frequency fetch; risk/reward unfavorable. See Deferred Items §5. |
| OQ-PRD-3 | PRD §12 | `CCDASH_TQ_MIGRATION_ENABLED` — runtime vs build-time flag? | Resolved | Runtime-resolved not needed (no per-deploy rollback target). Build-time devtools flag only. |

---

## 5. Deferred Items Rationale

- **Epic D (Next.js/SSR migration execution)**: Deferred because `HashRouter` is spread across ~30 files (`App.tsx:2,65,105`), and `AppRuntimeContext.tsx:43` reads `window.location.hash` at module scope — two hard SSR blockers. Full execution would balloon scope beyond this plan. Promote when: Epics A–C are smoke-clean for 14 calendar days; `ccdash-nextjs-migration-v1.md` sub-plan is authored and approved; `CCDASH_NEXTJS_ENABLED` flag is defined. Entry-criteria spec authored in P7 DOC-006.

- **ModelColorsContext TQ migration**: Deferred because it is a single low-frequency `GET /api/analytics/model-facets` fetch on mount — the risk/reward for migrating it in this refactor window is unfavorable. Promote in a future data-layer clean-up pass.

---

## 6. Risk Narrative

- **P3 cache retirement silent breakage (HIGH)**: The `featureSurfaceCache.ts` / `featureCacheBus.ts` feeds `useFeatureSurface` across the ProjectBoard v2 surface. The planning.ts freshness-bucket keying (`PLANNING_BROWSER_CACHE` project × freshnessToken × payloadType) has no direct TQ analogue. Naive replacement loses freshness semantics with no type error. Watch for: planning summary going stale without revalidating; feature write mutations not triggering visible re-render on ProjectBoard. The `FeatureSurfaceRegressionMatrix.test.tsx` extended in P3 is the primary safety net. If it can't be made deterministic, escalate to an Opus consult before P4.

- **P4 AppEntityDataContext deletion (HIGH)**: 24 component files call `useData()`; 12 of 15 screens consume `activeProject`. Deleting `AppEntityDataContext` while any screen is unmigrated breaks that screen instantly. The mitigation is strict ordering: delete only after all 15 screens are individually runtime-smoked. The `karen` gate at P4 exit is mandatory — do not let an agent mark P4 complete without the karen review. If any screen smoke fails, the deletion must be rolled back.

- **Polling/SSE double-fetch (MEDIUM)**: `AppRuntimeContext` currently suppresses the 5s feature poll when `featureSurfaceV2Active` is true (SSE connected). Porting to per-query `refetchInterval` risks inadvertently re-enabling the poll when SSE is active, causing double-fetch. Watch for: elevated network activity when `VITE_CCDASH_LIVE_FEATURES_ENABLED=true`; verify `refetchInterval: false` is set on the features query when SSE connection is established.

- **Pagination semantics break at limit=5000 removal (MEDIUM)**: `OpsPanel.tsx:268` currently reduces the full task list to counts and filters. This breaks when paginated. P2 T2-003 audits this consumer specifically — verify `OpsPanel` renders correct task totals from `total` field in paginated response, not from `items.length`.

---

## 7. What to Watch For

- **P3 seam (T3-007)**: After retiring `featureCacheBus.ts`, any mutation that previously called `publishFeatureWriteEvent` must now call `queryClient.invalidateQueries`. Grep for `publishFeatureWriteEvent` imports after P3 — any remaining import is a bug.

- **P4 ordering discipline**: Do not delete `AppEntityDataContext` until all 15 screens pass individual runtime smoke. A partial deletion is worse than no deletion. The task-completion-validator gate (T4-010) must see the karen sign-off (T4-009) before P4 can close.

- **P5 parallel track convergence**: P5a (backend endpoints) and P5b (FE wiring) are separate agents. Confirm P5a endpoints are fully deployed (or locally available) before P5b starts wiring. The seam task T5-008 is the verification point.

- **P6 virtualizer container height**: `useVirtualizer` requires an explicit container height in CSS. If the container collapses to height=0 (e.g., in a CSS flexbox context), the virtualizer renders nothing. The 200-item fallback (T6-001) catches this but will produce visible degradation. Smoke with a container that has an explicit height applied.

- **guardrail tests are early-warning systems**: The `noHandRolledCache.test.ts` test will fail if any phase inadvertently re-introduces a `new Map()` + TTL pattern. Run `vitest run services/__tests__/noHandRolledCache.test.ts` after every phase to catch regressions before P7.

---

## 8. Expected Success Behaviors

Observable, human-verifiable outcomes after ship:

- [ ] Navigate to Dashboard, then to SessionInspector, then press browser back. Session list appears instantly — no spinner, no network call.
- [ ] Open browser DevTools network tab. Navigate to Dashboard (cold load). Confirm exactly one network call to `/api/v1/dashboard` and no calls to `/api/documents`, `/api/features`, or `/api/analytics/alerts`.
- [ ] Open DevTools. Navigate to Planning page. Confirm one call to `/api/agent/planning/view` — no separate calls to `planning/summary`, `planning/graph`, and `planning/session-board`.
- [ ] Open DevTools. Confirm `GET /api/tasks?limit=5000` and `GET /api/features?limit=5000` never appear after migration.
- [ ] In SessionInspector with a project containing >50 sessions, scroll the session list rapidly. Confirm smooth scroll without DOM thrash (virtualizer renders only visible rows).
- [ ] In PlanCatalog with >100 documents, confirm list renders quickly and count badge shows the correct total from the API response.
- [ ] Run `npm run test` in a terminal. Confirm `vitest run` exits 0 with no failures in `noHandRolledCache.test.ts`, `dataArchitecture.test.ts`, or `FeatureSurfaceRegressionMatrix.test.tsx`.
- [ ] Verify the `services/planning.ts` file no longer contains `new Map()` declarations (source grep: `grep -n "new Map()" services/planning.ts` returns empty).
- [ ] Verify `services/featureSurfaceCache.ts` and `services/featureCacheBus.ts` no longer exist (`ls services/featureSurfaceCache.ts` → file not found).
- [ ] Change a feature status in ProjectBoard. Confirm the UI updates optimistically (no flash to old state) and rolls back if you simulate a network error via DevTools "Offline" mode.

---

## 9. Running Log

- [2026-05-28] Brief created. All OQs resolved from decisions-block.md §7 and PRD §12 at planning time. Confidence: 0.82.
