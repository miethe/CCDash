---
title: "Phase 3: Frontend Data Layer and Board Migration"
description: "Refactor feature board data access around hooks, bounded caches, server-backed filters, and batched rollups."
audience: [ai-agents, developers]
tags: [implementation, phase, frontend, react, caching, project-board]
created: 2026-04-22
updated: 2026-04-22
category: "product-planning"
status: draft
related:
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
---

# Phase 3: Frontend Data Layer and Board Migration

**Effort:** 13 pts
**Dependencies:** Phase 2 API contracts
**Assigned Subagent(s):** frontend-developer, ui-engineer-enhanced, react-performance-optimizer

## Objective

Move feature board loading from ad hoc component effects to a dedicated data layer that requests one feature page plus one bounded rollup batch, preserves all current filters and card metrics, and avoids unnecessary client-side full-data caching.

## Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| P3-001 | API Client Methods | Add typed client methods for feature card list, rollups, modal sections, and linked-session pages. | No new raw feature-surface `fetch` calls are added in components. | 2 pts | frontend-developer | P2-005 |
| P3-002 | Feature Surface Hook | Implement `useFeatureSurface` or equivalent for query state, list loading, rollup loading, cache keys, errors, and invalidation. | Hook returns cards, rollups, facets/totals, loading states, and retry handlers. | 3 pts | frontend-developer | P3-001 |
| P3-003 | Server-Backed Filters | Move board search/filter/sort query state into API parameters while preserving draft/apply filter UX. | UI behavior matches current filters; totals reflect backend query. | 2 pts | ui-engineer-enhanced | P3-002 |
| P3-004 | Remove Eager Linked-Session Summary Loop | Delete or bypass the `filteredFeatures.forEach(loadFeatureSessionSummary)` pattern on ProjectBoard only. | No per-feature linked-session fan-out on ProjectBoard initial render. Other surfaces (SessionInspector, Workbench, Dashboard) remain on legacy pattern until Phase 4 P4-007..P4-009. | 2 pts | frontend-developer | P3-002 |
| P3-005 | Card Metric Mapping | Render all current card metrics from `FeatureCardDTO` plus `FeatureRollupDTO`. | Existing visual cards, list view, counts, badges, and progress displays remain populated. | 2 pts | ui-engineer-enhanced | P3-004 |
| P3-006 | Cache and Invalidation | Add bounded cache policy keyed by project, query, page/window, feature IDs, and freshness token. | Reopening same board query avoids duplicate requests while sync/live invalidation refreshes stale data. | 1 pt | react-performance-optimizer | P3-002 |
| P3-007 | Board Tests | Add tests proving bounded calls, correct query params, filter behavior, rollup rendering, and no legacy summary fan-out. | Tests fail if `/linked-sessions` is called for each feature on initial render. | 1 pt | frontend-developer | P3-006 |

## Frontend Cache Policy

1. Cache feature list pages by `projectId + normalizedQuery + page`.
2. Cache rollups by `projectId + sortedFeatureIds + requestedFields + freshnessToken`.
3. Use short TTL or stale-while-revalidate for rollups.
4. Invalidate on:
   - project switch
   - feature status/phase/task write-through
   - sync completion
   - live topics for project features, individual feature, sessions, documents, tests
5. Do not cache full linked-session arrays as board state.

## Board Behavior Requirements

1. Draft filters remain local until applied.
2. Search should debounce or apply explicitly, matching current UX decision from Phase 0.
3. Board columns derive from returned status/stage fields and accurate backend totals.
4. List view and board view must share the same query source.
5. "Done" feature limiting should be supported by backend query options if introduced; do not slice done features only in the UI when totals matter.
6. Loading state should support partial rendering: list loaded, rollups pending.

## Component Boundaries

- `ProjectBoard` should orchestrate layout and interactions.
- Feature data loading should move to hooks/services.
- Feature cards should accept card DTO + rollup DTO, not trigger network requests.
- Status update handlers should optimistically update local cache and then reconcile with server response.

## Scope & Deferrals

**Phase 3 scope is limited to ProjectBoard.** Other surfaces consuming feature/linked-session data (SessionInspector, FeatureExecutionWorkbench, Dashboard/BlockingFeatureList, and planning modals) remain on legacy patterns until Phase 4. The legacy `/api/features/{id}/linked-sessions` route is retained for non-board callers; Phase 5 will inventory and migrate or document each. This phase does not guarantee that other surfaces remain silent on legacy routes; verification is a Phase 5 task.

## Quality Gates

- [ ] Initial board load request count is bounded and asserted in tests.
- [ ] Card metrics match legacy-derived metrics on parity fixtures.
- [ ] Filters and sorts remain feature-complete.
- [ ] Existing ProjectBoard tests pass or are migrated to v2 fixtures.
- [ ] Frontend cache does not grow without bounds under repeated filter changes.

## Notes for Implementers

1. Use `encodeURIComponent` for every path parameter added in this phase.
2. Keep current board rendering density and controls stable unless a small loading/error state is required.
3. Consider virtualizing only if DOM render cost remains high after data loading is fixed; this phase focuses on network/data flow.

