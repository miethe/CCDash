---
title: "Implementation Plan: CCDash Frontend Data Layer Refactor v1"
schema_version: 2
doc_type: implementation_plan
status: draft
created: 2026-05-28
updated: 2026-05-28
feature_slug: "ccdash-frontend-data-layer-refactor"
feature_version: "v1"
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: null
scope: "Replace three hand-rolled server-state caches with TanStack Query, remove eager-load waterfall, add backend fat-read bundles, virtualize large lists, and gate Next.js/SSR migration entry criteria."
effort_estimate: "31 pts (Epics A–C) + 1 pt Epic D gate = 32 pts total"
architecture_summary: "TQ QueryClientProvider above DataProvider; domain query hooks in services/queries/; contexts shrunk to client-state; bundle endpoints in agent_queries/ then routers/; virtualizers via @tanstack/react-virtual."
risk_level: medium
changelog_required: true
category: refactors
tags: [implementation, refactor, tanstack-query, data-layer, performance, frontend]
priority: high
owner: null
contributors: []
milestone: null
commit_refs: []
pr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
related_documents:
  - docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/decisions-block.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-frontend.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-backend.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md
  - docs/guides/feature-surface-architecture.md
references:
  user_docs:
    - docs/guides/feature-surface-architecture.md
    - docs/guides/query-cache-tuning-guide.md
  context:
    - .claude/context/distilled/project-fundamentals-and-design-context.md
  specs:
    - .claude/specs/changelog-spec.md
  related_prds:
    - docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
plan_structure: unified
progress_init: auto
files_affected:
  - App.tsx
  - lib/queryClient.ts
  - services/queryKeys.ts
  - services/queries/sessions.ts
  - services/queries/documents.ts
  - services/queries/tasks.ts
  - services/queries/features.ts
  - services/queries/alerts.ts
  - services/queries/notifications.ts
  - services/queries/planning.ts
  - services/queries/dashboard.ts
  - services/planning.ts
  - services/featureSurfaceCache.ts
  - services/featureCacheBus.ts
  - services/useFeatureSurface.ts
  - services/apiClient.ts
  - contexts/AppEntityDataContext.tsx
  - contexts/AppRuntimeContext.tsx
  - contexts/DataContext.tsx
  - contexts/AppSessionContext.tsx
  - components/Dashboard.tsx
  - components/SessionInspector.tsx
  - components/PlanCatalog.tsx
  - components/ProjectBoard.tsx
  - backend/application/services/agent_queries/dashboard.py
  - backend/routers/client_v1.py
  - backend/routers/api.py
wave_plan:
  serialization_barriers:
    - contexts/DataContext.tsx
    - services/queryKeys.ts
    - App.tsx
  phases:
    - id: P0
      depends_on: []
      isolation: shared
      parallelizable: false
      files_affected:
        - App.tsx
        - lib/queryClient.ts
        - services/queryKeys.ts
    - id: P1
      depends_on: [P0]
      isolation: shared
      parallelizable: false
      files_affected:
        - services/queries/sessions.ts
        - contexts/AppEntityDataContext.tsx
        - components/SessionInspector.tsx
        - components/Dashboard.tsx
    - id: P2
      depends_on: [P1]
      isolation: shared
      parallelizable: true
      files_affected:
        - services/queries/documents.ts
        - services/queries/tasks.ts
        - services/queries/features.ts
        - services/queries/alerts.ts
        - services/queries/notifications.ts
        - contexts/AppEntityDataContext.tsx
    - id: P3
      depends_on: [P2]
      isolation: shared
      parallelizable: false
      files_affected:
        - services/planning.ts
        - services/featureSurfaceCache.ts
        - services/featureCacheBus.ts
        - services/useFeatureSurface.ts
    - id: P4
      depends_on: [P3]
      isolation: shared
      parallelizable: false
      files_affected:
        - contexts/AppEntityDataContext.tsx
        - contexts/AppRuntimeContext.tsx
        - contexts/DataContext.tsx
        - App.tsx
    - id: P5
      depends_on: [P0]
      isolation: shared
      parallelizable: true
      files_affected:
        - backend/application/services/agent_queries/dashboard.py
        - backend/routers/client_v1.py
        - backend/routers/api.py
        - services/queries/dashboard.ts
        - components/Dashboard.tsx
    - id: P6
      depends_on: [P2]
      isolation: shared
      parallelizable: false
      files_affected:
        - components/SessionInspector.tsx
        - components/PlanCatalog.tsx
        - components/ProjectBoard.tsx
    - id: P7
      depends_on: [P4, P5, P6]
      isolation: shared
      parallelizable: false
      files_affected:
        - CHANGELOG.md
        - docs/guides/feature-surface-architecture.md
        - docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md
  waves:
    - [P0]
    - [P1, P5]
    - [P2, P6]
    - [P3]
    - [P4]
    - [P7]
---

# Implementation Plan: CCDash Frontend Data Layer Refactor v1

**Plan ID**: `IMPL-2026-05-28-CCDASH-FE-DATA-LAYER-REFACTOR`
**Date**: 2026-05-28
**Author**: Implementation Planner (sonnet)
**Human Brief**: `docs/project_plans/human-briefs/ccdash-frontend-data-layer-refactor.md`
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- **Decisions Block**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/decisions-block.md`
- **Frontend Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-frontend.md`
- **Backend Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-backend.md`
- **Prior Art Inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md`

**Complexity**: XL (Tier 3)
**Total Estimated Effort**: 31 pts (Epics A–C committed) + 1 pt (Epic D gate artifact) = 32 pts
**Target Timeline**: 4–6 weeks

---

## Executive Summary

This plan migrates CCDash's three independent hand-rolled SWR+LRU server-state caches — `AppEntityDataContext` (476 lines), `services/planning.ts` (three module-scope LRU Maps, 1483 lines), and `services/featureSurfaceCache.ts`/`featureCacheBus.ts` (543 lines combined) — to a single TanStack Query `QueryClient`. The migration proceeds **incrementally and facade-preserving**: the `useData()` compatibility shim remains functional throughout Epics A–B and is deleted only after all 15 screen consumers are individually verified.

P5 backend bundle endpoints (`GET /api/v1/dashboard`, `GET /api/agent/planning/view?include=`, `GET /api/analytics/overview-bundle`) are parallelized against the FE migration spine and composed from already-cached `agent_queries` reads at near-zero extra DB cost. P6 virtualizes three large list surfaces via `@tanstack/react-virtual` (already installed). P7 authors the Epic D entry-criteria design spec and sub-plan stub, gating any Next.js/SSR execution until Epics A–C are smoke-clean for 14 days.

**Key Milestones**:
1. P0 complete — TQ mounted, app renders identically, guardrail scaffold present
2. P4 complete — all domains migrated, eager-load removed, `AppEntityDataContext` deleted (**karen milestone**)
3. P7 complete — all guardrails green, docs updated, Epic D gate doc authored (**karen end-of-feature**)

---

## Implementation Strategy

### Architecture Sequence

This refactor follows a **migration spine** rather than the standard layered DB→Repo→Service→API→UI flow, because the primary work is retiring existing bespoke infrastructure rather than adding new capability:

1. **Foundation** (P0) — TQ provider + queryKey registry + guardrail tests
2. **Canonical Domain Slice** (P1) — Sessions vertical (proves the hook+consumer pattern)
3. **Domain Replication** (P2) — Remaining 6 domains, parallelizable by file ownership
4. **Cache Consolidation** (P3) — Retire hand-rolled planning + feature surface caches
5. **Root Teardown** (P4) — Eager-load removal, context shrinkage, polling port
6. **Backend Bundles** (P5) — Fat-read endpoints (parallelized from P0, FE wiring after P4)
7. **Virtualization** (P6) — Three list surfaces (parallelized from P2)
8. **Validation + Epic D Gate** (P7) — Guardrails, docs, entry-criteria spec

### Parallel Work Opportunities

- **P5 backend endpoints run in parallel with P2/P3/P4** — backend-only files (`backend/routers/`, `agent_queries/`) are disjoint from the FE migration. Begin P5a backend after P0 completes.
- **P2 domains parallelize internally** — each domain is a distinct hook file + consumer set. Assign batches by file ownership.
- **P6 virtualizer work runs in parallel with P4/P5** — list-render code is independent of context teardown once the relevant domain hooks (P1/P2) exist.
- **P5 FE wiring** joins after its bundle endpoint ships AND the relevant domain is migrated (P4 dependency).

### Critical Path

```
P0 → P1 → P2 → P3 → P4 → P7
             ↑
        P5a backend (starts after P0)
        P6 virtualization (starts after P2)
```

P4 is the high-water-mark gate: no root teardown until P1–P3 are fully migrated. `karen` reviews at P4 exit and again at P7.

### Phase Summary

Canonical orchestration index. Keep in sync with detailed phase breakdowns in phase files.

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| P0 | TQ Foundation & Guardrails | 2 pts | ui-engineer-enhanced | sonnet / adaptive | Installs TQ, mounts provider, registry, devtools flag, guardrail scaffold |
| P1 | Sessions Vertical Slice | 3 pts | ui-engineer-enhanced | sonnet / extended | Canonical pattern; dedup cold-fetch; back-nav from cache |
| P2 | Remaining Entity Domains | 5 pts | ui-engineer-enhanced, frontend-developer | sonnet / adaptive | 6 domains parallel by file ownership; tasks+features paginated |
| P3 | Cache Consolidation (HIGH RISK) | 5 pts | ui-engineer-enhanced | sonnet / extended | Retire planning.ts LRU + featureSurfaceCache; preserve useFeatureSurface API |
| P4 | Eager-load Removal + Context Teardown (HIGH RISK) | 4 pts | ui-engineer-enhanced | sonnet / extended | Fan-out removal; 15-screen migration; AppEntityDataContext deleted; karen |
| P5 | Backend Fat-Read Bundles | 6 pts | python-backend-engineer (BE), ui-engineer-enhanced (FE) | sonnet / adaptive | 3 bundle endpoints + FE TQ wiring; parallelized from P0 |
| P6 | List Virtualization | 3 pts | ui-engineer-enhanced | sonnet / adaptive | SessionInspector, PlanCatalog, ProjectBoard; react-virtual already installed |
| P7 | Validation, Docs & Epic D Gate | 3 pts | documentation-writer, documentation-complex, ui-engineer-enhanced | haiku+sonnet / adaptive | Docs+CHANGELOG (haiku); guardrails+smoke (sonnet); Epic D spec (sonnet); karen |
| **Total** | — | **31 pts + 1 pt Epic D = 32 pts** | — | — | Epic D gate artifact is 1 pt in P7 |

**Reviewer gates**: `task-completion-validator` exits every phase; `karen` at P4 and P7.

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| EPIC-D | scope-cut | Next.js/SSR migration execution blocked by HashRouter→BrowserRouter across ~30 files + `window.location.hash` module-scope reads (`AppRuntimeContext.tsx:43`); full execution would balloon scope beyond this plan | Epics A–C smoke-clean for 14 days; HashRouter removed; `ccdash-nextjs-migration-v1.md` sub-plan authored and approved | `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md` (authored in P7 DOC-006) |
| MODEL-COLORS | scope-cut | `ModelColorsContext` single low-frequency fetch on mount (`/api/analytics/model-facets`) — risk/reward unfavorable in this refactor window | Future data-layer clean-up pass | N/A — single eager fetch, low ROI |

**Quality Gate**: `deferred_items_spec_refs` must be populated with the Epic D design-spec path before P7 is sealed.

### In-Flight Findings

Lazy-creation rule applies. Path if needed: `.claude/findings/ccdash-frontend-data-layer-refactor-findings.md`.

---

## Phase File Links

This plan exceeds 800 lines. Detailed task tables live in phase-specific files:

| Phase File | Phases Covered | Content |
|-----------|----------------|---------|
| [`phase-0-2-foundation-and-domains.md`](./ccdash-frontend-data-layer-refactor-v1/phase-0-2-foundation-and-domains.md) | P0, P1, P2 | TQ foundation + sessions slice + 6 domain migrations |
| [`phase-3-4-cache-and-context-teardown.md`](./ccdash-frontend-data-layer-refactor-v1/phase-3-4-cache-and-context-teardown.md) | P3, P4 | Cache consolidation + eager-load removal + context teardown |
| [`phase-5-7-backend-virtualization-validation.md`](./ccdash-frontend-data-layer-refactor-v1/phase-5-7-backend-virtualization-validation.md) | P5, P6, P7 | Backend bundles + list virtualization + validation/docs |

---

## Risk Summary

| Risk | Severity | Phase | Mitigation (brief) |
|------|----------|-------|-------------------|
| Hand-rolled cache retirement breaks consumers silently | High | P3 | Preserve `useFeatureSurface` API via TQ-backed adapter; extend `FeatureSurfaceRegressionMatrix.test.tsx` |
| Root context teardown while 24 components consume `useData()` | High | P4 | Keep facade through P1–P4; delete `AppEntityDataContext` only after all 15 screens individually migrated and smoked |
| Polling/live-SSE behavior regression | Medium | P4 | Per-query `refetchInterval`; SSE-enabled paths set `refetchInterval: false` |
| Pagination semantics break when `limit=5000` removed | Medium | P2/P5 | Audit consumers for full-list reductions; source counts from summary/bundle endpoints |
| Next.js/SSR migration scoped too early | High (deferred) | P7 | Epic D entry criteria gates execution; see `deferred_items_spec_refs` |
| Runtime smoke discipline | Medium | P0–P6 | Every UI phase carries a runtime-smoke task referencing `target_surfaces` |

**Full risk detail**: decisions-block.md §3.

---

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Cold load request count | 8–9 (parallel + duplicate) | ≤ 1 above-fold per view |
| Back-navigation spinner (warm) | Always shows | 0 ms for cached routes |
| Duplicate session fetch | 2 calls on cold | 1 call |
| Hand-rolled cache modules | 3 | 0 (source-reading guardrail) |
| Non-virtualized large lists | 3 | 0 |
| Bundle size delta | — | +13 KB (TQ) − 40 KB (deleted caches) = net −27 KB |

---

## Progress Tracking

See `.claude/progress/ccdash-frontend-data-layer-refactor/` (created when implementation begins).

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-05-28
