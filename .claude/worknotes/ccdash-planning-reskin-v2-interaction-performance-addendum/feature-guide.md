---
schema_version: 2
doc_type: context
type: context
prd: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
status: active
created: 2026-04-21
updated: 2026-04-21
title: "Interaction & Performance Addendum — Feature Guide"
---

# Interaction & Performance Addendum — Feature Guide

Reference documents:
- **PRD**: `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md`
- **Load Budget Findings**: `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum/p16-005-load-budget-measurement.md`
- **A11y Regression Findings**: `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum/p16-006-a11y-regression.md`

---

## 1. Modal-First Navigation

Planning surfaces (PlanCatalog, PlanningTriagePanel) operate in modal-first mode: clicking a plan/feature/tracker row opens a modal or side panel instead of navigating directly to `/board`. This preserves context and reduces full-page re-renders.

**Route helpers** (`lib/planning-routes.ts`):
- `planningRouteFeatureModalHref(featureId)` — feature modal
- `planningFeatureModalHref(featureId)` — alias for above
- `planningFeatureDetailHref(featureId)` — explicit board navigation

**Key components**:
- `PlanCatalog` — list view with modal row triggers
- `PlanningTriagePanel` — triage drill-down in modal
- `PlanningQuickViewPanel` — side panel details (see §4)

**Keyboard interaction**:
- `Escape` closes modal/panel
- Focus trap active while modal open
- Focus restored to trigger on close

---

## 2. Active-First Cached Loading

Planning summary employs stale-while-revalidate (SWR) with bounded LRU cache to achieve warm render under 250 ms and cold local p95 under 2 s. Cache is browser-resident and regenerated on project/session state changes.

**Cache implementation** (`services/planning.ts`):
- `PLANNING_BROWSER_CACHE` — configurable cache size (default 10 entries)
- `PLANNING_BROWSER_CACHE_LIMITS` — per-entry TTL and size constraints
- `cacheProjectPlanningSummary(projectId, fetcher, onRevalidated)` — SWR wrapper
  - Returns cached value immediately if valid
  - Spawns background revalidation if stale
  - Invokes `onRevalidated` callback when fresh data arrives

**Detail payloads** are fetched on-demand (panel/modal open only), not pre-fetched.

---

## 3. Metric Tiles & Filters

Planning dashboard tiles map to backend `status_counts` (eight buckets: shaping, planned, active, blocked, review, completed, deferred, stale_or_mismatched). Tiles are clickable filters that update the visible feature list.

**Filter behavior**:
- Default filter excludes terminal features (completed, deferred)
- Active-first ordering: incomplete features appear first
- Tab + filter state persists across page reloads via URL query or localStorage

**Backend contract**: `GET /api/v1/planning/project/{projectId}/summary` returns aggregate counts and individual feature records with status enum.

---

## 4. PlanningQuickViewPanel

Side panel for triage/tracker interactions. Houses feature metadata, promotion rows, and linked resources. Implements accessibility best practices:

- **Focus management**: Focus trap during open; escape closes and restores focus to trigger via `priorFocusRef`
- **ARIA**: `role="dialog"` + `aria-modal="true"` + descriptive `aria-labelledby`
- **Keyboard**: `Escape` to close
- **Content slots**: Feature detail rows, document promotion, agent drill-down

---

## 5. AgentDetailModal

Row-click modal for roster agent drill-down. Displays agent metadata, session activity, and linked features.

**Agent naming precedence**:
1. `displayAgentType` (if present)
2. `agentId`
3. First word of `title`
4. ID prefix (e.g., "agent-" from `agent-1234`)

**Accessibility**:
- Focus trap
- `Escape` to close
- `aria-label` with full agent name
- Scroll-bounded: `max-h-[85vh]` with `overflow-y-auto`

**Data resolution**:
- Linked features resolved via `linkedFeatureIds` → feature lookup in planning state
- Session count/metadata from agent query layer

---

## Implementation Notes

- All route helpers are co-located in `lib/planning-routes.ts` for consistency
- Modal stacking: only one modal active at a time; side panels do not stack modals
- Cache invalidation: triggered by session sync, feature mutations, or explicit refresh
- Performance budget: SWR revalidation must not exceed 500 ms on cold path
