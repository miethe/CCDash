# Feature Surface v2 Rollback Guide

Last updated: 2026-04-24

This guide describes how to disable the v2 feature-surface data path and revert to the legacy v0 path, including expected behavior differences and cache invalidation steps.

---

## Toggle Location

The rollout flag is the `CCDASH_FEATURE_SURFACE_V2_ENABLED` environment variable.

| Value | Behavior |
|-------|----------|
| `true` (default) | v2 path active — board data loaded from `/api/v1/features?view=cards`, rollups from `/api/v1/features/rollups`, modal sections from `/api/v1/features/{id}/modal` and section endpoints. |
| `false` | v2 path disabled — frontend falls back to legacy `/api/features/{id}` and `/api/features/{id}/linked-sessions` for modal data. Board card grid renders empty (no card-level filter or rollup metrics). |

Set the variable in `.env` (local dev) or your operator environment:

```env
# Disable v2 feature-surface data path (emergency rollback)
CCDASH_FEATURE_SURFACE_V2_ENABLED=false
```

The backend exposes the current value via `/api/health` (field `featureSurfaceV2Enabled`) and `/api/health/detail`. The frontend reads it once at mount and picks the data path for that page load. A browser refresh is required after changing the flag.

---

## Expected Behavior Per Value

### `CCDASH_FEATURE_SURFACE_V2_ENABLED=true` (default)

- **ProjectBoard**: Fetches paginated, server-filtered feature cards and batched rollup metrics. Board columns, card metrics (session badge, cost badge, last-active), and server-side search/filter all work.
- **Feature modal**: Each tab (overview, phases, docs, relations, sessions, test-status, history) loads independently and lazily from the corresponding `/api/v1/features/{id}/modal` section endpoints.
- **Cache**: The bounded SWR + LRU list cache (`featureSurfaceCache.ts`) and modal section LRU (`useFeatureModalData.ts`) are populated.

### `CCDASH_FEATURE_SURFACE_V2_ENABLED=false`

- **ProjectBoard**: `useFeatureSurface` returns an empty card list immediately (no network calls to v1 list/rollup endpoints). Board columns are empty.
- **Feature modal overview and sessions tabs**: Data loaded from legacy `/api/features/{id}` and `/api/features/{id}/linked-sessions`. Other modal tabs (phases, docs, relations, test-status, history) receive empty item lists.
- **Board-level filter/search/sort**: Not functional (those controls target the v1 server-side filter path).
- **v1 backend endpoints**: All `/api/v1/features/…` endpoints remain online and respond normally. They are NOT gated by this flag. The flag only controls which path the frontend activates.

---

## Cache Invalidation Steps

After changing the flag value:

1. **Restart the backend** to reload the config value from the environment:
   ```bash
   npm run dev:backend
   # or in production:
   systemctl restart ccdash-api
   ```

2. **Hard-refresh the browser** (Ctrl+Shift+R / Cmd+Shift+R). The frontend reads `featureSurfaceV2Enabled` from `/api/health` on the initial load. Cached health responses in the runtime polling loop may persist up to 30 seconds; a hard refresh forces an immediate re-poll.

3. **Optionally clear the browser-side SWR + LRU cache** if stale card data appears after toggling back to `true`:
   - Open the browser console and run:
     ```js
     // clears the module-level featureSurfaceCache singleton
     window.__ccdash_invalidate_feature_cache?.();
     ```
   - If that is not available, navigate away from ProjectBoard and back; the LRU is automatically primed on the next mount.

4. **Query cache (backend)**: The agent query service in-process TTL cache has a default TTL of 60 seconds (`CCDASH_QUERY_CACHE_TTL_SECONDS`). After a restart it is cleared. If you need to clear it without a restart, use the `/api/cache/invalidate` endpoint (requires operator access).

---

## Known Regressions When Disabled

| Capability | Status when flag=false |
|-----------|----------------------|
| Board card grid | Empty — no cards rendered |
| Server-side feature search | Non-functional |
| Server-side status/stage/tag filters | Non-functional |
| Card-level rollup metrics (sessions, cost, activity) | Not shown |
| Pagination on large feature lists | Non-functional |
| Modal overview tab | Data loaded from legacy endpoint (reduced fidelity — no quality signals, document coverage, or family position) |
| Modal sessions tab | Data loaded from legacy flat-array endpoint (no pagination, no enrichment fields, no subthread counts) |
| Modal phases, docs, relations, test-status, history tabs | Empty item lists |
| Live invalidation of board data on session sync | Not triggered (v2 cache bus disabled) |
| Feature card freshness indicators | Not shown |

These regressions are expected and acceptable for a short-term rollback window. The legacy endpoints remain fully supported for the lifetime of this release.

---

## Re-enabling v2

Remove the `CCDASH_FEATURE_SURFACE_V2_ENABLED=false` override (or set it to `true`) and restart the backend. No database migrations are required. The v2 endpoints were fully provisioned as part of the Phase 2/3 rollout and remain available at all times regardless of the flag value.
