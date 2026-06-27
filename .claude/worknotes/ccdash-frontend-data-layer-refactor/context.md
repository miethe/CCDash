---
schema_version: 2
doc_type: context
type: context
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
title: CCDash Frontend Data Layer Refactor — Development Context
status: active
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
critical_notes_count: 0
implementation_decisions_count: 6
active_gotchas_count: 0
agent_contributors: []
agents: []
---

# CCDash Frontend Data Layer Refactor — Development Context

**Status**: Planning — Not Started
**Created**: 2026-05-28
**Last Updated**: 2026-05-28

## Feature Summary

This refactor migrates CCDash's three independent hand-rolled SWR+LRU server-state caches — `AppEntityDataContext` (476 lines), `services/planning.ts` (three module-scope LRU Maps, 1483 lines), and `services/featureSurfaceCache.ts`/`featureCacheBus.ts` (543 lines combined) — to a single TanStack Query `QueryClient`, while adding three backend fat-read bundle endpoints, virtualizing three large list surfaces, and gating Next.js/SSR migration behind entry criteria. The migration is incremental and facade-preserving: `useData()` shim remains functional through all phases and is thinned (not deleted) at P4 exit.

## Key Document Pointers

| Document | Path |
|----------|------|
| PRD | `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md` |
| Implementation Plan | `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md` |
| Phase files | `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/` (3 files) |
| Decisions Block | `.claude/worknotes/ccdash-frontend-data-layer-refactor/decisions-block.md` |
| Frontend Inventory | `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-frontend.md` |
| Backend Inventory | `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-backend.md` |
| Prior Art Inventory | `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md` |

## 8-Phase Map

| Phase | Title | Pts | Primary Agent(s) | Model | Depends On |
|-------|-------|-----|-----------------|-------|-----------|
| P0 | TQ Foundation & Guardrails | 2 | ui-engineer-enhanced | sonnet | — |
| P1 | Sessions Vertical Slice | 3 | ui-engineer-enhanced | sonnet/extended | P0 |
| P2 | Remaining Entity Domains | 5 | ui-engineer-enhanced, frontend-developer | sonnet | P1 |
| P3 | Cache Consolidation (HIGH RISK) | 5 | ui-engineer-enhanced | sonnet/extended | P2 |
| P4 | Eager-Load Removal + Context Teardown (HIGH RISK) | 4 | ui-engineer-enhanced | sonnet/extended | P1+P2+P3 |
| P5 | Backend Fat-Read Bundles | 6 | python-backend-engineer (BE), ui-engineer-enhanced (FE) | sonnet | P0 (BE); P4+P5a (FE) |
| P6 | List Virtualization | 3 | ui-engineer-enhanced | sonnet | P2 |
| P7 | Validation, Docs & Epic D Gate | 3 | docs-writer, docs-complex, ui-engineer-enhanced | haiku+sonnet | P4+P5+P6 |

**Parallel opportunities**: P5 backend runs against P2/P3/P4; P6 runs against P4/P5; P5 FE wiring joins after P4 + P5a ship.

**karen gates**: P4 exit (milestone) and P7 exit (end-of-feature).

## 6 Key Risks (decisions-block.md §3)

1. **Hand-rolled cache retirement breaks consumers silently** (HIGH, P3) — Preserve `useFeatureSurface` API via TQ-backed adapter; extend `FeatureSurfaceRegressionMatrix.test.tsx`
2. **Root context teardown while 24 components consume `useData()`** (HIGH, P4) — Keep facade through P1–P4; delete `AppEntityDataContext` only after all 15 screens individually migrated and smoked
3. **Polling/live-SSE behavior regression** (MEDIUM, P4) — Per-query `refetchInterval`; SSE-enabled paths set `refetchInterval: false`
4. **Pagination semantics break when `limit=5000` removed** (MEDIUM, P2/P5) — Audit consumers for full-list reductions; source counts from summary/bundle endpoints
5. **Next.js/SSR migration scoped too early** (HIGH, deferred) — Epic D entry criteria gates execution; `deferred_items_spec_refs` must be populated before P7 sealed
6. **Runtime smoke discipline** (MEDIUM, P0–P6) — Every UI phase carries a runtime-smoke task; phase cannot be marked `completed` without smoke or explicit `runtime_smoke: skipped` record

## 6 Resolved Open Questions

| OQ | Resolution |
|----|-----------|
| OQ-1: useInfiniteQuery vs offset for session list | `useInfiniteQuery` — matches existing "Load more" UX; `loadMoreSessions()` → `fetchNextPage()` |
| OQ-2: freshnessToken for planning cache | Fold into TQ queryKey array: `planningKeys.summary(projectId, freshnessToken)` — TQ treats new token as new key |
| OQ-3: Keep or delete `useData()` facade | Keep as thin ≤50-line shim re-exporting TQ values + `AppSessionContext` client-state — avoids touching 24 import sites |
| OQ-4: Per-deploy rollback flag | Not needed — migration is incremental + facade-preserved; keep `VITE_CCDASH_QUERY_DEVTOOLS` only |
| OQ-5: Bundle endpoint composition cost | Compose existing cached `agent_queries` reads at near-zero extra DB cost; no new `agent_queries` methods needed |
| OQ-6: Polling mapping | Health 30s; alerts/notifications 30s; features live-mode fallback 5s when `VITE_CCDASH_LIVE_FEATURES_ENABLED=false`; SSE paths → `refetchInterval: false` |

---

## Implementation Decisions

_(Agents: append notes below as work proceeds)_

---

## Gotchas & Observations

_(Agents: append gotchas below as implementation reveals surprises)_

---

## References

- Progress files: `.claude/progress/ccdash-frontend-data-layer-refactor/phase-{0..7}-progress.md`
- Implementation plan: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- Feature-surface architecture doc: `docs/guides/feature-surface-architecture.md`
