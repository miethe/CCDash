# Feature Surface Architecture Guide

Last updated: 2026-04-24

This guide documents the redesigned feature-surface data contracts, caching strategy, and performance budgets for CCDash developers. It describes which API endpoint to use for card-level metrics vs modal sections, how the frontend caches work, and what invalidation events clear which caches.

---

## Overview

The feature surface is a **layered architecture** that separates concerns across backend repositories, service aggregators, REST routers, and frontend hooks with explicit cache boundaries:

1. **Repository layer** (`backend/db/repositories/features.py`, `postgres/features.py`): Filtering, sorting, pagination, and aggregation queries.
2. **Service layer** (`backend/application/services/feature_surface/*.py`): DTO assembly, freshness metadata, cross-domain enrichment.
3. **Router layer** (`backend/routers/features.py`): HTTP contracts, parameter validation, observability instrumentation.
4. **Frontend hooks** (`services/useFeatureSurface.ts`, `services/useFeatureModalData.ts`): Query identity, cache policy, loading/error state, invalidation.
5. **Cache layer** (`services/featureSurfaceCache.ts`, `services/planning.ts`): Two-tier SWR + LRU for list pages and rollups; separate LRU for modal sections.

**Key principle:** Never fan out per-feature API calls during list rendering. Cards fetch metrics via a single bounded rollup call; modal sections load lazily and independently.

---

## Data Contracts

Five v1 API endpoints form the public surface contract. Each has a specific purpose and payload bound:

| Endpoint | Purpose | Payload Bound | Use When |
|----------|---------|---------------|----------|
| `GET /api/v1/features?view=cards&page=...` | Feature card/list rows with filters, search, sort, pagination, counts | Page only (default 20 items) | Rendering board columns, list views. Returns facet counts if present. |
| `POST /api/v1/features/rollups` | Batched aggregate metrics for a returned feature ID list | Bounded ID list (max 100 IDs), no session logs | Computing card summary badges (session count, cost, activity date) immediately after a list fetch. |
| `GET /api/v1/features/{feature_id}` | Modal overview shell with quality signals, family position, and optional light includes | Single feature, no session logs | Opening modal overview tab; includes counts, status, phases, docs coverage metadata. |
| `GET /api/v1/features/{feature_id}/sessions?page=...` | Linked sessions for a feature, paginated and optionally enriched with subthread counts | Page only (default 20 items), pagination before enrichment | Populating Sessions tab; supports filtering, pagination, and per-session badges. |
| `GET /api/v1/features/{feature_id}/activity` | Timeline/history/commit aggregates for a feature | Single feature, paginated where needed | Activity/History tab; includes phase transitions, task events, document updates. |

**Payload bounds are enforced:** rollup requests larger than 100 IDs return `400 Bad Request`. List endpoints paginate before building full detail, preventing N+1 session reads.

---

## Frontend Hooks & When to Use Them

### `useFeatureSurface(projectId, query, options)`

**Owns:** Feature board data loading (list + rollup in one call sequence).

```typescript
// Typical usage
const {
  cards,        // FeatureCardDTO[] — the feature list rows
  rollups,      // Record<featureId, rollup> — cached aggregate metrics
  total,        // number — count of all features matching filters
  filteredTotal, // number — count after search applied
  loading,      // 'idle' | 'loading' | 'success' | 'error'
  error,        // Error | null
  page,         // current page number
  pageSize,     // items per page
  setQuery,     // update filters, search, sort
  retry,        // refetch on error
  prefetch,     // warm cache for adjacent page
} = useFeatureSurface(projectId, query, {
  rollupFields: ['session_counts', 'token_cost_totals', 'latest_activity'],
});
```

**Cache policy:** Two-tier bounded LRU:
- **List tier:** 50 entries, keyed by `projectId|normalizedQuery|page`. No TTL; invalidates on project switch or write events.
- **Rollup tier:** 100 entries, keyed by `projectId|sortedIds|fields|freshnessToken`. 30s TTL; stale-while-revalidate exposed via `isStale()`.

**When to use:**
- Rendering ProjectBoard columns and feature cards.
- Any UI that displays a paginated, filterable feature list with summary metrics.
- **Never** call this once per card to fetch detail; use the rollup endpoint instead.

**Invalidation:**
- `invalidateFeatureSurface({ projectId, featureIds: [...] })` — fine-grained, clears list pages and rollup entries for affected IDs.
- Automatically invoked when status/phase/task writes publish events to the feature cache bus.

### `useFeatureModalData(featureId, options)`

**Owns:** Per-section modal tab loading (overview, phases, docs, relations, sessions, test-status, history).

```typescript
// Typical usage
const sections = useFeatureModalData(featureId, {
  includeFields: ['document_coverage', 'quality_signals'],
  sessionPageSize: 20,
});

// Load a specific section
sections['overview'].load();
sections['sessions'].load({ page: 1 });

// Each section exposes
{
  status: 'idle' | 'loading' | 'success' | 'error' | 'stale',
  data: FeatureModalOverviewDTO | FeatureModalSectionDTO | LinkedFeatureSessionPageDTO,
  error: Error | null,
  requestId: string, // prevents stale overwrites
  load(params?): Promise<void>,
  retry(): Promise<void>,
  invalidate(): void,
  prefetch(): Promise<void>, // warm cache without switching state
}

// Top-level helpers
sections.markStale('sessions'); // transition one section to stale
sections.invalidateAll();        // clear all sections for this feature
sections.prefetch('activity');   // warm cache before user clicks
```

**Cache policy:** Dedicated modal section LRU:
- **Max 120 entries**, keyed by `featureId|section|paramsHash`.
- Separate from list/rollup cache to avoid eviction conflicts (board ~50 items, modal 1 feature × 7 sections).
- No TTL; invalidates on feature writes or explicit user refresh.

**When to use:**
- Each modal tab loads independently on click (no eager fetch of all tabs).
- Supports pagination within Sessions tab without refetching all previous pages.
- Prefetch sections before the user clicks to reduce perceived latency.
- **Never** open a modal and immediately fetch all tab data; use the lazy-load pattern.

**Invalidation:**
- `sections.invalidate()` — clears cache for that specific feature's all sections.
- Automatically cleared on feature status/phase/task writes (coarse-grained via planning cache bus).

---

## Cache Invalidation Matrix

Two independent browser-side caches coexist. A unified **feature cache bus** (`services/featureCacheBus.ts`) ensures both are invalidated deterministically:

| Event | Feature Surface Cache | Planning Browser Cache | Feature Cache Bus |
|-------|----------------------|----------------------|------------------|
| **Feature status write** (ProjectBoard.handleFeatureStatusChange) | Fine-grained: `invalidateFeatureSurface({ projectId, featureIds: [id] })` | Coarse: `clearPlanningBrowserCache(projectId)` | `publishFeatureWriteEvent({ projectId, featureIds: [id], kind: 'status' })` |
| **Phase progression** (modal edit) | Fine-grained: same as above | Coarse: same as above | `publishFeatureWriteEvent({ ..., kind: 'phase' })` |
| **Task update** (modal edit) | Fine-grained: same as above | Coarse: same as above | `publishFeatureWriteEvent({ ..., kind: 'task' })` |
| **Project switch** | Direct call: `invalidateFeatureSurface({ projectId })` | Direct call: `clearPlanningBrowserCache(projectId)` | Not used; not a feature write |
| **Sync completion** | Existing live-topic handler + periodic revalidation | Existing freshness-key revalidation | Not involved |
| **Rollout flag toggle** (`CCDASH_FEATURE_SURFACE_V2_ENABLED`) | Browser hard-refresh (Cmd+Shift+R) clears `/api/health` cache; optional `window.__ccdash_invalidate_feature_cache?.()` | Same hard-refresh | Not involved |

**Planning cache detail:** The planning browser cache uses freshness buckets (not feature IDs) as its internal key structure. Eviction is coarse (all entries for a project) because feature-granular eviction would require a schema change out of scope for Phase 4.

---

## Performance Budgets

The feature-surface architecture enforces request count, payload size, and latency budgets verified by `backend/tests/test_feature_surface_benchmarks.py`. These budgets are **CI-safe** (generous, pure mock I/O) and intended to prove call shape, not DB throughput:

### Board Load (`GET /api/v1/features`)

| Metric | Small (10 features / 50 sessions) | Medium (100 features / 1000 sessions) | Budget |
|--------|-----------------------------------|--------------------------------------|--------|
| Latency | < 500 ms | < 1500 ms | 2× hard fail limit |
| Request count | 1 (list) + 1 (rollup) = 2 | 1 (list) + 1 (rollup) = 2 | Always 2, regardless of page size |
| Payload estimate | ~10 KB (20 cards) | ~50 KB (20 cards) | Scales with window size, not feature count |
| Session logs read | 0 | 0 | Never fetch logs for card metrics |

**Key assertion:** Board render triggers exactly 2 network requests (one list, one rollup) regardless of feature count. No per-feature eager calls.

### Rollup Endpoint (`POST /api/v1/features/rollups`)

| Metric | Small (10 IDs) | Medium (100 IDs) | Oversized (200 IDs) | Budget |
|--------|----------------|------------------|---------------------|--------|
| Latency | < 500 ms | < 1500 ms | 400 Bad Request | 2× hard fail limit |
| Request count | 1 | 1 | Rejected | Single batch |
| Payload estimate | ~1 KB (overhead) + ~100 B per ID | ~1 KB + ~100 B × 100 | Rejected | No logs, pure aggregates |
| Session logs read | 0 | 0 | N/A | Never fetch logs |

**Key assertion:** Rollup rejects batches > 100 IDs at the router layer. No N+1 session queries.

### Linked-Session Page (`GET /api/v1/features/{id}/sessions?page=...`)

| Metric | Small (50 sessions, page=1) | Large (10k sessions, page=500) | Budget |
|--------|-----------------------------|---------------------------------|--------|
| Latency | < 500 ms | < 500 ms | 2× hard fail limit |
| Request count | 1 (pagination before enrichment) | 1 per page | One per page |
| Payload estimate | ~5 KB (20 items per page) | ~5 KB (20 items per page) | Constant per page |
| Session logs read | 0 for pagination; enrichment happens after | 0 for pagination; enrichment after | Never paginate full arrays |

**Key assertion:** Pagination happens at the repository layer before expensive enrichment (subthread counts, badges). Large session lists do not materialize in memory.

### Modal Tab Activation (`GET /api/v1/features/{id}/modal/{section}?page=...`)

| Metric | Activity + Rollup (combined) | Sessions (paginated) | Other tabs | Budget |
|--------|-------------------------------|----------------------|------------|--------|
| Latency | < 500 ms | < 500 ms | < 200 ms | 2× hard fail limit |
| Request count | 1 (roundtrip) | 1 per page | 1 per tab | Single request per section |
| Payload estimate | ~2 KB | ~5 KB | ~1-3 KB | Lean DTOs, no full detail |
| Session logs read | 0 | 0 (pagination first) | 0 | Never fetch logs for sections |

**Key assertion:** Opening any modal tab triggers exactly 1 network request. No combined list + detail fetches; no session log reads for summary metrics.

---

## Cache Invalidation Events

The feature cache bus publishes three event kinds. Write-site handlers call `publishFeatureWriteEvent()` once; both caches subscribe automatically:

```typescript
// From ProjectBoard.tsx or any mutation handler
await updateFeatureStatus(featureId, newStatus);

// One call triggers both cache evictions
publishFeatureWriteEvent({
  projectId,
  featureIds: [featureId],
  kind: 'status', // or 'phase' or 'task'
});

// Subscriber 1 (Feature Surface Cache)
// → invalidateFeatureSurface({ projectId, featureIds: [featureId] })
// → Evicts only list pages and rollup entries for this feature

// Subscriber 2 (Planning Cache)
// → clearPlanningBrowserCache(projectId)
// → Evicts all entries for the project (coarse-grained)
```

**Project switch** does NOT use the bus (not a feature write):

```typescript
// From context provider or route handler
handleProjectChange(newProjectId);
invalidateFeatureSurface({ projectId: oldProjectId });  // Direct call
clearPlanningBrowserCache(oldProjectId);                // Direct call
```

---

## Migration Guide: Building New Components

### Anti-Pattern: Per-Feature Data Fanout

❌ **Don't do this:**

```typescript
// WRONG: fetches /api/v1/features/{id} for every card
function FeatureCard({ featureId, projectId }) {
  const [detail, setDetail] = useState(null);
  
  useEffect(() => {
    fetch(`/api/v1/features/${encodeURIComponent(featureId)}`)
      .then(r => r.json())
      .then(setDetail);
  }, [featureId]);
  
  return <div>{detail?.session_count}</div>; // N+1 calls
}
```

### Correct Pattern: List → Rollup → Cards

✅ **Do this instead:**

```typescript
// 1. Parent component fetches the list once
function FeatureGrid({ projectId }) {
  const { cards, rollups, loading } = useFeatureSurface(projectId, query);
  
  // 2. Render cards with pre-fetched rollup data
  return (
    <div>
      {loading && <Spinner />}
      {cards.map(card => (
        <FeatureCard
          key={card.id}
          feature={card}
          metrics={rollups[card.id]} // Already fetched, no new call
          onOpen={() => openModal(card.id)}
        />
      ))}
    </div>
  );
}

// 3. Modal opens lazily; sections load independently
function FeatureModal({ featureId }) {
  const sections = useFeatureModalData(featureId);
  const [activeTab, setActiveTab] = useState('overview');
  
  // 4. Load only the active tab
  useEffect(() => {
    sections[activeTab].load();
  }, [activeTab]);
  
  return (
    <Tabs onChange={tab => setActiveTab(tab)}>
      <TabPanel name="overview" data={sections.overview} />
      <TabPanel name="sessions" data={sections.sessions} />
      {/* Other tabs load on demand */}
    </Tabs>
  );
}
```

### Migration Checklist

When adding a new feature surface consumer:

1. ✅ **Use `useFeatureSurface` for list + card metrics** — never fetch detail per card.
2. ✅ **Use `useFeatureModalData` for modal tabs** — sections load independently on tab click.
3. ✅ **Call `publishFeatureWriteEvent()` after mutations** — use the cache bus, not direct `invalidateFeatureSurface()` calls.
4. ✅ **Encode feature IDs in URLs** — `encodeURIComponent(featureId)` in all API paths.
5. ✅ **Handle missing rollup gracefully** — if a feature has no rollups in the response, show a fallback badge.
6. ✅ **Never prefetch all modal tabs** — wait for user intent (tab click).
7. ✅ **Page before enriching** — the API does this for you; don't add extra joins client-side.

---

## Related Documentation

- **Rollback Guide:** [`docs/guides/feature-surface-v2-rollback.md`](./feature-surface-v2-rollback.md) — How to disable v2 and revert to legacy paths in an emergency.
- **Planning Cache ADR:** [`docs/project_plans/design-specs/feature-surface-planning-cache-coordination.md`](../project_plans/design-specs/feature-surface-planning-cache-coordination.md) — Detailed cache bus design and invalidation semantics.
- **Implementation Plan:** [`docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md`](../project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md) § Architecture Direction — Authoritative contract table and layering rules.
- **Phase 5 Plan:** [`docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-5-validation-rollout.md`](../project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-5-validation-rollout.md) — Testing strategy and rollout gates.
- **CLAUDE.md § Planning Entries:** [./CLAUDE.md](../../CLAUDE.md) — Project-wide architecture context.
