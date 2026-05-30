# CCDash Caching Investigation — Enterprise Edition

**Domain:** Caching / query-cache layer and invalidation correctness  
**Date:** 2026-05-30  
**DB context:** `data/ccdash_cache.db` = 10 GB, WAL = 1.7 MB. Many large projects (e.g. skillmeat).

---

## Summary

The backend query cache is a **single in-process `TTLCache` singleton** (`cachetools`, `maxsize=512`) allocated at module-import time. It lives inside whichever OS process called `import backend.application.services.agent_queries.cache`. In an enterprise deployment with separate `api` and `worker` containers, each container has its own independent copy. The worker may warm its copy, but the api container serves traffic from its own cold cache until it happens to fill through user-driven requests. Background cache-warming only runs in `jobs`-capable profiles (worker/local), not in the `api` profile, so the api container is never proactively warmed.

Fourteen distinct service methods are decorated with `@memoized_query`. On every incoming request to a cached endpoint, the decorator first runs 6 sequential DB queries to compute a **data-version fingerprint** before the cache key can even be looked up. On a 10 GB SQLite database with large `entity_links` and `feature_phases` tables, this pre-check overhead is significant. The entity_links fingerprint performs a full-table `GROUP_CONCAT` / `STRING_AGG` across all links with no project-scoped filter, making it a global scan proportional to total link count, not the active project's.

Cache keys are project-scoped via the `{endpoint}:{project_id}:{param_hash}:{fingerprint}` format, preventing cross-project result leakage. However, two env vars advertised as separate per-metric TTLs (`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`, `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`) have no effect on the actual cache eviction behavior, because the underlying `TTLCache` singleton uses a single TTL baked at import time. The frontend feature-list endpoint (`GET /api/features`) has no server-side caching at all and is polled by the client every 5 seconds when SSE is disabled (the default for live-features).

---

## Architecture Overview

### Backend Cache Singleton

**File:** `backend/application/services/agent_queries/cache.py:50`

```python
_effective_ttl: int = max(1, config.CCDASH_QUERY_CACHE_TTL_SECONDS)
_query_cache: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=_effective_ttl)
```

- **Type:** `cachetools.TTLCache` — in-process, no external dependency (no Redis, no Memcached)
- **Maxsize:** 512 entries (hard cap; oldest entries evicted when full)
- **TTL:** Fixed at import time from `CCDASH_QUERY_CACHE_TTL_SECONDS` (default: **600 seconds** per `config.py:983`)
- **Thread-safety:** Intentionally not thread-safe; safe under asyncio single-threaded event loop per documentation at `cache.py:385–390`
- **Scope:** Module-level singleton — one cache per OS process

**Config defaults** (`backend/config.py`):
| Variable | Default | Purpose |
|----------|---------|---------|
| `CCDASH_QUERY_CACHE_TTL_SECONDS` | `600` | Global TTL for all memoized_query entries |
| `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` | `300` | Background warmer interval |
| `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` | `10` | *Advertised* but NOT enforced at cache layer |
| `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` | `30` | *Advertised* but NOT enforced at cache layer |

---

## What Is Cached (Endpoint Inventory)

All 14 `@memoized_query` decorated methods live in `backend/application/services/agent_queries/`:

| Service Method | Endpoint Key | File | Line |
|---------------|-------------|------|------|
| `ProjectStatusQueryService.get_status` | `project_status` | `project_status.py` | 96 |
| `WorkflowDiagnosticsQueryService.get_diagnostics` | `workflow_diagnostics` | `workflow_intelligence.py` | 67 |
| `FeatureForensicsQueryService.get_forensics` | `feature_forensics` | `feature_forensics.py` | 221 |
| `ReportingQueryService.get_aar_report` | `aar_report` | `reporting.py` | 63 |
| `PlanningQueryService.get_project_summary` | `planning_project_summary` | `planning.py` | 883 |
| `PlanningQueryService.get_project_graph` | `planning_project_graph` | `planning.py` | 1180 |
| `PlanningQueryService.get_feature_context` | `planning_feature_context` | `planning.py` | 1306 |
| `PlanningQueryService.get_phase_operations` | `planning_phase_ops` | `planning.py` | 1574 |
| `LiveMetricsQueryService.get_active_count` | `live_active_count` | `live_metrics.py` | 76 |
| `SystemMetricsQueryService.get_system_active_count` | `system_active_count` | `system_metrics.py` | 172 |
| `DashboardQueryService.get_bundle` | `dashboard_bundle` | `dashboard.py` | 112 |
| `AnalyticsBundleQueryService.get_analytics_bundle` | `analytics_overview_bundle` | `analytics_bundle.py` | 67 |
| `FeatureEvidenceSummaryService.get_summary` | `feature-evidence-summary` | `feature_evidence_summary.py` | 187 |
| `MultiProjectPlanningCommandCenterQueryService.get_command_center` | `mpcc_command_center` | `multi_project_planning_command_center.py` | 355 |
| `MultiProjectActiveSessionBoardQueryService.get_session_board` | `mpss_session_board` | `multi_project_planning_sessions.py` | 502 |

**Not cached (high-traffic):**
- `GET /api/features` (legacy `list_features`) — `backend/routers/features.py:837` — no memoized_query, polled at 5s by default from frontend
- `GET /api/v1/features` (v1 surface list) — `backend/routers/client_v1.py:189` — delegates to `_client_v1_features.py`, no server-side cache
- `GET /api/sessions` and `GET /api/documents` — `backend/routers/api.py` — no cache layer

---

## Cache Key Format and Project Scoping

**File:** `backend/application/services/agent_queries/cache.py:294–317`

```
{endpoint_name}:{project_id or 'global'}:{param_hash}:{fingerprint}
```

- `project_id` is extracted from `RequestContext.project.project_id` (or explicit param) and lives in the key scope slot, not the param hash
- Different projects produce different cache keys — **no cross-project leakage risk**
- `system_active_count` uses `project_id=None` → scope resolves to literal `"global"` — this is intentional since it fans out across all projects
- Multi-project keys (`mpcc_command_center`, `mpss_session_board`) include sorted `project_ids` in the param hash

---

## Data-Version Fingerprint: Cost and Correctness

### What the fingerprint does

**File:** `backend/application/services/agent_queries/cache.py:84–142`

Before every cache lookup, `get_data_version_fingerprint()` issues **6 sequential DB queries**:

| # | Table | Query | Scope |
|---|-------|-------|-------|
| 1 | `sessions` | `MAX(updated_at)` | project-scoped |
| 2 | `features` | `MAX(updated_at)` | project-scoped |
| 3 | `feature_phases` | `COUNT + GROUP_CONCAT(all phase markers)` | project-scoped (via JOIN) |
| 4 | `documents` | `MAX(updated_at)` | project-scoped |
| 5 | `entity_links` | `COUNT + GROUP_CONCAT(all link markers)` | **GLOBAL — no project_id filter** |
| 6 | `planning_worktree_contexts` | `MAX(updated_at)` | project-scoped |

### Critical issue: entity_links is a global table scan

**File:** `backend/application/services/agent_queries/cache.py:258–289`

The `_query_entity_links_marker()` function runs:

```sql
SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
FROM (
    SELECT COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ...
    FROM entity_links
    ORDER BY source_type, source_id, ...
)
```

No `WHERE project_id = ?` clause. On a 10 GB database with millions of entity_links spanning 36+ projects, every fingerprint computation performs a full-table aggregation. The result is then SHA-256 hashed. This query executes on **every request to every cached endpoint** (before the cache key is checked), regardless of whether the cache will hit.

The `entity_links` table schema (`backend/db/sqlite_migrations.py:37–56`) confirms there is **no `project_id` column** on this table, making project-scoped filtering impossible without a join to sessions/features. The existing indexes (`idx_links_source`, `idx_links_target`, `idx_links_tree`) do not help a COUNT+GROUP_CONCAT across all rows.

### feature_phases also scans heavily

**File:** `backend/application/services/agent_queries/cache.py:195–255`

`_query_feature_phases_marker()` with a `project_id` argument runs a JOIN between `feature_phases` and `features` and then a `GROUP_CONCAT` of all phase markers for that project. With large numbers of features and phases this produces a large intermediate string before hashing. No index covers `feature_phases.feature_id` + `features.project_id` joint traversal in SQLite.

### Fingerprint is NOT itself cached

The fingerprint result is computed fresh on every request. There is no secondary TTL cache for the fingerprint itself. On a busy API with 10 concurrent users, each cached endpoint request triggers 6 DB queries regardless of the overall TTL.

---

## Background Cache Warming: Architecture Gap

### What warming does

**File:** `backend/adapters/jobs/runtime.py:840–982`

The `_start_cache_warming_task()` method runs a periodic asyncio loop (interval = `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`, default 300 s) that warms exactly **2 of the 14+ cached endpoints**: `project_status` and `workflow_diagnostics`.

```python
await _project_status_svc.get_status(context, self.ports)
await _workflow_svc.get_diagnostics(context, self.ports)
```

The other 12 endpoints (`planning_project_summary`, `planning_project_graph`, `feature_forensics`, `aar_report`, `live_active_count`, `system_active_count`, `dashboard_bundle`, `analytics_overview_bundle`, `feature-evidence-summary`, `planning_feature_context`, `planning_phase_ops`, `mpcc_command_center`, `mpss_session_board`) are only warmed by demand.

### Fatal architecture gap: warming only runs in jobs-capable profiles

**File:** `backend/runtime/profiles.py:28–88`

| Profile | `jobs=` | Used in |
|---------|---------|---------|
| `local` | `True` | Dev workstation |
| `api` | **`False`** | **Enterprise API container** |
| `worker` | `True` | Enterprise worker container |
| `worker-watch` | `True` | Enterprise worker with filesystem watch |
| `test` | `False` | Test suite |

The cache warming task (`_start_cache_warming_task`) is only scheduled when `self.profile.capabilities.jobs == True` (`runtime.py:182,192`). In the enterprise deployment the `api` profile has `jobs=False`. Therefore:

**The API container that serves traffic has NO cache warming job running.** The worker container warms its own in-process cache, which is invisible to the API container.

This means in a containerized deployment:
1. API container starts cold
2. First user request to `project_status` triggers 6 fingerprint queries + full service query
3. Subsequent requests within 600 s hit cache
4. After 600 s the entry expires; next user request is cold again
5. No background process refills the API cache before expiry

---

## Documented-but-Broken Per-Metric TTLs

### `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (documented, unenforced)

**Config:** `backend/config.py:987–994` — documented default 10 s  
**Doc comment in service:** `backend/application/services/agent_queries/live_metrics.py:19–32`  

The design note says staleness is bounded by `min(fingerprint_change, global_ttl)`. In practice this only helps when a new session appears (changing `sessions.MAX(updated_at)`). If the API is idle and no new sessions are created, the live count could remain cached for the full global TTL (600 s default), not 10 s. The env var `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` is read by `config.py` and stored in the response payload, but never fed into any TTL slot in `_query_cache`.

**File:** `backend/application/services/agent_queries/cache.py:50` — single TTLCache, single TTL.

### `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` (documented, unenforced)

**Config:** `backend/config.py:1015–1023` — documented default 30 s  
**Router comment:** `backend/routers/agent.py:212` — "response is cached server-side for CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS"

Same problem: the env var has no code path that creates a separate TTLCache slot or sub-TTL. `system_active_count` uses `@memoized_query` which reads from the global singleton at the global TTL. An operator setting `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS=30` will see no effect.

---

## Frontend Stale Times and Polling

### Frontend TanStack Query cache settings

**File:** `lib/queryClient.ts:29–41`

Default `QueryClient` config:
- `staleTime: 30_000` (30 s)
- `gcTime: 300_000` (5 min)
- `refetchOnWindowFocus: false`
- `retry: 3, skip 4xx`

**Per-hook overrides** (from `services/queries/*.ts`):

| Query | staleTime | refetchInterval | Notes |
|-------|-----------|-----------------|-------|
| `dashboard.bundle` | 10 s | — | `dashboard.ts:87` |
| `planning.summary` | **0** | — | Token-driven invalidation `planning.ts:72` |
| `planning.*` (others) | 30 s | — | `planning.ts:104,137,171,262,338,386` |
| `sessions.*` | 30 s | — | `sessions.ts:55,89` |
| `features.*` (old path) | 30 s | **5 s** (default) | `features.ts:81,85` |
| `featureSurface.list` | **0** | — | `useFeatureSurface.ts:348` |
| `featureSurface.rollup` | 30 s | — | `useFeatureSurface.ts:397` |
| `documents.*` | 60 s | — | `documents.ts:72` |
| `projects.list` | 300 s | — | `projects.ts:62` |
| `health.*` | 25 s | 30 s | `health.ts:52,53` |
| `alerts.*` | 30 s | 30 s | `alerts.ts:45,46` |
| `notifications.*` | 30 s | 30 s | `notifications.ts:45,46` |
| `analytics.overviewBundle` | 30 s | — | `analytics.ts:55` |

### Feature list 5-second polling gap (HIGH severity)

**File:** `services/queries/features.ts:85`

```typescript
refetchInterval: isFeatureLiveUpdatesEnabled() ? false : 5_000,
```

`isFeatureLiveUpdatesEnabled()` reads `VITE_CCDASH_LIVE_FEATURES_ENABLED` which **defaults to `false`** (`services/live/config.ts:21–23`). In the default configuration the old feature list query polls the server every 5 seconds. `GET /api/features` (legacy `features_router`) has no `@memoized_query` wrapper. Each poll triggers a raw DB read: `repo.list_paginated()` + `repo.count()` + per-feature `get_phases()` loop (N+1 risk) + `load_feature_execution_derived_states()`.

### featureSurface list staleTime=0 pressure

**File:** `services/useFeatureSurface.ts:348`

The feature surface list hook uses `staleTime: 0`, meaning TQ considers the data immediately stale after any fetch. This ensures TQ refetches in the background on every component mount. Combined with the board being a primary route, this generates constant background traffic to `GET /api/v1/features` even when the user is not changing anything.

---

## Project-Switch Cache Invalidation

**File:** `lib/queryClient.ts:29` — comment: "Call `queryClient.clear()` when the active project changes"  
**File:** `services/queryKeys.ts:1–9` — all keys prefixed with `projectId` for selective invalidation

Frontend TQ cache correctly handles project switching via `queryClient.clear()` or selective `invalidateQueries`. However there is no backend cache invalidation triggered on project switch. The backend `@memoized_query` cache will serve stale results for up to 600 s after a project switch if the new project happens to produce the same fingerprint (unlikely but theoretically possible given global `entity_links` fingerprint).

More practically: the backend cache does NOT know about project switches initiated by the CLI (`ccdash project use <id>`). A CLI user switching projects and then hitting the API within the TTL window will see old cached results.

---

## Invalidation on Write: Single Call Site

**File:** `backend/application/services/agent_queries/planning.py:1567`

```python
clear_cache()
```

The only backend code path that calls `clear_cache()` is `PlanningQueryService.resolve_open_question()`. No other write path (status changes, task updates, sync completion, session writes) explicitly clears the cache. The cache is only invalidated by:

1. TTL expiry (600 s)
2. `clear_cache()` in `resolve_open_question` (planning write)
3. `bypass_cache=True` query param (forces a miss, stores fresh result)

Sync operations (`POST /api/cache/sync`, `POST /api/cache/sync-paths`) do not call `clear_cache()` after completing. After a full sync on a large project, cached `project_status`, `workflow_diagnostics`, and all planning surfaces remain stale until TTL expiry.

---

## Enterprise Container Deployment Gaps

### [CRITICAL] In-process cache cannot be shared across containers

The `TTLCache` singleton lives in Python process memory. Multiple `api` replicas behind a load balancer each have independent caches:

- User A's request goes to replica 1 — warms entry in replica 1's cache
- User B's request goes to replica 2 — cold miss, triggers 6 fingerprint queries + full service query
- Replica 1's worker warming (if any) does not propagate to replica 2

**No Redis, no Memcached, no shared cache.** This is explicitly documented in `docs/guides/query-cache-tuning-guide.md:17`: "Cache is in-process only: restarts clear it, and multi-process deployments (multiple API servers) do not share cache state."

### [CRITICAL] API profile has `jobs=False`, so no cache warming in api containers

**File:** `backend/runtime/profiles.py:41–52`

The `api` profile explicitly sets `jobs=False`. The `_start_cache_warming_task()` call at `runtime.py:192` is inside `if self.profile.capabilities.jobs:`. Therefore zero background warming runs in the API container. The worker container warms its private cache, which is discarded on container restart and not shared with API containers.

### [HIGH] Fingerprint overhead on 10GB SQLite

Every request to a cached endpoint runs 6 DB queries. The entity_links query (`COUNT + GROUP_CONCAT` with ORDER BY across all rows) on a large table is an O(N) scan with sort. SQLite does not parallelize queries. With 36+ projects, millions of entity_links, the fingerprint computation may take tens to hundreds of milliseconds per call. On a single-file SQLite database, concurrent fingerprint reads and write operations from the sync engine create lock contention (WAL mode helps but doesn't eliminate it).

### [HIGH] Cache maxsize=512 for multi-project enterprise

With 36+ projects × 14 cached endpoints × multiple filter variants (feature forensics per feature, planning per feature, phases per phase), the 512-entry maximum can be exceeded. When maxsize is hit, `cachetools.TTLCache` evicts the oldest entry (LRU within TTL). On a large installation the effective hit rate may degrade significantly.

**File:** `backend/application/services/agent_queries/cache.py:50`

---

## Recommended Enterprise Caching Architecture

The current design is well-suited for single-process local mode. For enterprise/container readiness, the following changes are needed:

### Tier 1: Shared distributed cache (Redis/Valkey)

Replace the `TTLCache` singleton with a shared cache backend:
- Single instance behind load balancer: multiple api replicas hit the same cache
- Serialize cache values as JSON/msgpack
- Use project-scoped key prefixes (current format already supports this)
- Set Redis key TTL to match `CCDASH_QUERY_CACHE_TTL_SECONDS`
- Worker container performs precompute writes; API containers read

### Tier 2: Per-metric TTL enforcement

Separate cache buckets or key-prefix namespaces for different TTL tiers:
- `live:*` keys → 10 s TTL (current `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`)
- `system:*` keys → 30 s TTL (current `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`)
- `heavy:*` keys (planning, forensics, AAR) → 600 s TTL

### Tier 3: Fingerprint caching

Cache the fingerprint result itself with a short TTL (5–10 s):
- Eliminates 6 DB queries per request when cache is hot
- Fingerprint mismatches still trigger cache bypass, but fingerprint query is amortized

### Tier 4: Scope entity_links fingerprint to project

Add a `project_id` lookup to entity_links (via join or denormalized column) or replace the global entity_links fingerprint with a project-scoped alternative (e.g., `MAX(created_at) WHERE source_type = 'feature' AND source_id IN (project's feature IDs)`).

### Tier 5: Sync-triggered invalidation

After `sync_project()` completes, post a targeted `NOTIFY` (Postgres) or Redis pub/sub message to invalidate project-scoped cache keys. API containers subscribe and evict their local caches (or pull from Redis). This eliminates the 600 s stale window after sync.

### Tier 6: Extend background warming coverage

The warmer currently covers 2/14+ memoized endpoints. Add warming for: `planning_project_summary`, `analytics_overview_bundle`, `dashboard_bundle`, `system_active_count`. Warming targets should match the frontend's poll frequency.

---

## Issue Index

### [CRITICAL] In-process cache broken across enterprise api+worker containers

- **Severity:** Critical — makes the cache effectively worthless in enterprise multi-container mode
- **Evidence:** `cache.py:50` singleton + `profiles.py:46` `jobs=False` for api profile + `runtime.py:192` warming only in jobs-capable profiles
- **Impact:** Every API request in container mode hits the DB with 6 fingerprint queries + full service query; no shared warming
- **Fix:** Introduce shared Redis/Valkey cache layer. Short-term: enable a jobs-capable sidecar in api containers that warms the in-process cache on schedule.

### [CRITICAL] entity_links fingerprint is a full global table scan

- **Severity:** Critical on large DBs — runs on every request to every cached endpoint
- **Evidence:** `cache.py:258–289` — no WHERE clause, GROUP_CONCAT over all rows across all projects
- **Impact:** On 10 GB DB with millions of links, each fingerprint invocation serializes millions of rows, hashes them, and blocks all other SQLite reads during GROUP_CONCAT
- **Fix:** Scope entity_links fingerprint to project (join on source_id/target_id matching project's features), or drop entity_links from fingerprint and use a dedicated `entity_links_version` counter updated by the sync engine

### [HIGH] CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS and CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS are phantom config (documented but not enforced)

- **Severity:** High — operators following docs will believe they've set a 10 s / 30 s TTL for live metrics but the actual TTL is the global 600 s
- **Evidence:** `cache.py:50` — single TTLCache with single TTL; neither env var is read by `cache.py`; `live_metrics.py:19` documents the intent as a fingerprint-based workaround which only works when sessions actually change
- **Fix:** Create a secondary `TTLCache` with the live-count TTL, or use key-prefix namespaces with per-prefix expiry in Redis

### [HIGH] No cache invalidation after sync

- **Severity:** High — after full sync of new sessions/features, all cached queries remain stale for up to 600 s
- **Evidence:** `planning.py:1567` is the only `clear_cache()` call; `routers/cache.py:363–424` sync endpoints do not call `clear_cache()`; no pub/sub invalidation on sync complete
- **Fix:** Call `clear_cache()` (or project-scoped invalidation) after `sync_project()` completes

### [HIGH] Feature list default 5-second polling to an uncached endpoint

- **Severity:** High — sustained load on `GET /api/features` with N+1 phase queries per request
- **Evidence:** `services/queries/features.ts:85` `refetchInterval: 5_000`; `live/config.ts:21` `isFeatureLiveUpdatesEnabled` defaults to `false`; `features_router:836–950` has no `@memoized_query`; `features.py:868` calls `get_phases(f["id"])` inside a per-feature loop
- **Fix:** Add `@memoized_query` to the legacy feature list path, or migrate all FE consumers to v1 surface and increase staleTime. At minimum, change the default to use staleTime=30s with no refetchInterval and rely on explicit invalidation.

### [MEDIUM] featureSurface list staleTime=0 generates constant background refetches

- **Severity:** Medium — unnecessary DB pressure on every component mount
- **Evidence:** `services/useFeatureSurface.ts:334,348` — `staleTime: 0`
- **Impact:** TQ marks list data stale immediately; background refetch triggers on every route render
- **Fix:** Increase staleTime to 10–30 s for the list tier and use explicit invalidation after mutations

### [MEDIUM] Cache maxsize=512 insufficient for multi-project enterprise

- **Severity:** Medium — LRU eviction degrades hit rate when projects × endpoints × filter variants exceed 512
- **Evidence:** `cache.py:50` `maxsize=512`; 36+ projects × 14 endpoints × parameter variants (per-feature forensics, per-feature planning) can easily exceed 512
- **Fix:** Increase `maxsize` to 2048–4096 as an immediate mitigation. Long-term: use Redis with no maxsize constraint.

### [MEDIUM] Background warming covers only 2 of 14+ memoized endpoints

- **Severity:** Medium — planning graph, feature forensics, analytics bundle remain cold until first request
- **Evidence:** `runtime.py:919–941` warms only `project_status` and `workflow_diagnostics`
- **Fix:** Add `planning_project_summary`, `dashboard_bundle`, `analytics_overview_bundle` to warming targets

### [LOW] Cache clearing on open_question resolution is full-cache eviction

- **Severity:** Low — `planning.py:1567` calls `clear_cache()` which evicts ALL 512 entries, not just the project's entries
- **Evidence:** `cache.py:73–79` `_query_cache.clear()` — total eviction
- **Fix:** Implement selective project-scoped eviction by filtering keys matching `*:{project_id}:*`

---

## Files Cited

| File | Relevant Lines | Topic |
|------|---------------|-------|
| `backend/application/services/agent_queries/cache.py` | 50, 84–142, 258–289, 294–317, 328–492 | Core cache singleton, fingerprint, decorator |
| `backend/config.py` | 983–1023 | Cache-related env var defaults |
| `backend/adapters/jobs/runtime.py` | 840–982 | Background warming loop |
| `backend/runtime/profiles.py` | 41–52 | api profile `jobs=False` |
| `backend/application/services/agent_queries/planning.py` | 1567 | Only `clear_cache()` call |
| `backend/routers/cache.py` | 363–424 | Sync endpoints (no cache invalidation) |
| `backend/routers/agent.py` | 212–224 | system_metrics TTL comment (misleading) |
| `backend/db/sqlite_migrations.py` | 37–56 | entity_links schema (no project_id col) |
| `services/queries/features.ts` | 81–85 | 5-second polling interval |
| `services/live/config.ts` | 21–23 | `isFeatureLiveUpdatesEnabled` defaults false |
| `services/useFeatureSurface.ts` | 334–348 | staleTime=0 on list tier |
| `lib/queryClient.ts` | 29–41 | Global TQ defaults |
| `services/queryKeys.ts` | 1–9 | projectId-prefixed key format |
| `docs/guides/query-cache-tuning-guide.md` | all | Operator docs (reflects current behavior with caveats) |
| `docs/guides/feature-surface-architecture.md` | 16 | In-process cache limitation acknowledged |
