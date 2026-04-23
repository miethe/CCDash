---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-005
created: 2026-04-23
---

# Performance Budgets — Feature Surface Data Loading Redesign

---

## 1. Summary

This document establishes hard numeric performance budgets for the two primary
feature surfaces — **BOARD** (`ProjectBoard` initial render plus filter/sort
interactions) and **MODAL** (`ProjectBoardFeatureModal` open plus per-tab
interactions). Every number here is a measurable threshold; Phase 5 tests must
assert each one.

The key design change driving these budgets:

- **Board cold-open**: today fires N linked-session fetches (one per visible
  card). Target: **2 requests total** — 1 list request + 1 rollup batch request,
  regardless of page size.
- **Modal cold-open**: today fires 2 requests unconditionally (full feature
  detail + full linked-sessions). Target: **1 request** (overview shell only).

All numbers are calibrated against the local fixture set defined in P0-006
(small = 10 features / ≤5 sessions each, medium = 50 features / ≤20 sessions
each, large = 200 features / ≤100 sessions each). Latency figures assume
SQLite, single-node, localhost; they are not production SLA figures.

---

## 2. Board Budgets

### 2.1 Request Count

| Scenario | Budget | Rationale | Assertion method |
|---|---|---|---|
| Cold board open (any page size ≤ 50) | **2 requests**: 1 × `GET /api/v1/features` + 1 × `POST /api/v1/features/rollups` | Replaces today's 1 list + N per-card linked-session calls | Vitest mock-fetch counter: assert `fetchSpy.callCount === 2` after board initial render |
| Warm-cache board open (SWR hit on both list + rollup) | **0 requests** | Both keys within `staleTime` | Vitest: assert `fetchSpy.callCount === 0` on second mount within stale window |
| Filter/sort change (single param change) | **1 request**: 1 × `GET /api/v1/features` (re-query with new params) | Rollup is unchanged if feature set changes negligibly; re-request rollup only when returned `featureIds` differ | Vitest: assert at most 1 list re-request + at most 1 rollup re-request per filter interaction |
| Filter change producing a different feature set | **2 requests**: 1 × list + 1 × rollup | Expected when filter narrows/expands the visible ID set | Vitest: assert `fetchSpy.callCount <= 2` per filter interaction |
| Board page navigation (offset change) | **2 requests**: 1 × list (new page) + 1 × rollup (new IDs) | Pagination loads a fresh window | Vitest: same 2-request assertion per page turn |
| Viewport scroll triggering rollup prefetch | **1 request**: 1 × rollup for the pre-fetch batch | Must not fire a list re-request | MSW: verify no `GET /api/v1/features` fires during scroll prefetch |
| Rapid filter typing (debounce window: 300 ms) | **≤ 2 requests** per settled query (debounce must coalesce intermediate keystrokes) | Current implementation triggers on every keystroke with no debounce | Vitest: mock `Date.now`, advance timer past debounce, assert at most 2 calls per settled input |

**Hard rule**: Board initial render must never fire `GET /api/features/{id}/linked-sessions`. Any occurrence is a test failure.

### 2.2 Payload Size

| Endpoint | Per-page budget | Ceiling | Assertion method |
|---|---|---|---|
| `GET /api/v1/features` response (50-feature page) | **≤ 80 KB** (gzip) | 120 KB | MSW response size interceptor; Vitest byte counter on serialized JSON |
| `GET /api/v1/features` response (per-row average) | **≤ 1.6 KB** per feature row | 2.5 KB | Same; derive per-row from total / page size |
| `POST /api/v1/features/rollups` request body (100 IDs) | **≤ 4 KB** | 6 KB | Vitest: measure serialized request body |
| `POST /api/v1/features/rollups` response (100 IDs) | **≤ 60 KB** (gzip) | 90 KB | MSW response size interceptor |
| `POST /api/v1/features/rollups` per-rollup average | **≤ 600 bytes** per `FeatureRollupDTO` | 900 bytes | Derive from total / item count |

**Rationale for list row cap**: The list DTO carries layout fields only (P0-003
§5 allocation); no `linkedDocs[]` array, no session arrays. 1.6 KB is generous
for the scalar + short-array fields in the list row contract.

**Rollup fan-out rules (hard constraints)**:

| Rule | Value | Enforcement |
|---|---|---|
| Max IDs per rollup request | **100** | Backend returns `422` if `featureIds.length > 100`; frontend batches in chunks of ≤ 100 |
| Batch strategy for viewport > 100 cards | Two sequential rollup requests; not parallel (to avoid thundering-herd) | Frontend slices `visibleIds` into `[0..99]`, `[100..199]`; fires second request after first resolves |
| Debounce on rapid card scroll / viewport resize | **150 ms** (half of filter debounce; rollup re-requests are cheaper to cancel) | `useRollupQuery` debounces the ID list before triggering; asserted via Vitest timer mocks |
| Rollup request suppressed when IDs are unchanged | Yes — stable ID set must not re-request | Vitest: verify referential equality of ID array triggers no new request |

### 2.3 Latency (p50 / p95, local fixture set)

All latency figures are for the **backend query time only** (excluding network
serialization), measured by the OTEL `duration_ms` histogram.

| Endpoint | p50 target | p95 target | Fixture size | Assertion method |
|---|---|---|---|---|
| `GET /api/v1/features` (50 rows, any filter) | **≤ 25 ms** | **≤ 60 ms** | Medium (50 features) | Backend pytest timer; OTEL `feature_list_duration_ms` histogram |
| `GET /api/v1/features` (200 rows, no filter) | **≤ 50 ms** | **≤ 120 ms** | Large (200 features) | Same histogram |
| `POST /api/v1/features/rollups` (50 IDs) | **≤ 30 ms** | **≤ 80 ms** | Medium | OTEL `feature_rollup_duration_ms` histogram |
| `POST /api/v1/features/rollups` (100 IDs) | **≤ 50 ms** | **≤ 140 ms** | Large | Same histogram |
| Total board cold-open (2 sequential requests) | **≤ 120 ms** | **≤ 280 ms** | Medium | Playwright `performance.measure` from navigation start to `data-board-ready` attribute |

### 2.4 Client-Side Compute

| Operation | Budget (ms, main thread) | Memo stability requirement | Assertion method |
|---|---|---|---|
| `filteredFeatures` useMemo (filter + sort over 50 rows) | **≤ 5 ms** | Stable reference when filter params and row data are unchanged | Vitest `performance.now()` wrapper; React DevTools Profiler in dev |
| `filteredFeatures` useMemo (200 rows) | **≤ 15 ms** | Same stability requirement | Same |
| Board initial render (commit phase, 50 cards) | **≤ 50 ms** | N/A | React Profiler `actualDuration` ≤ 50 in Vitest; Playwright LCP timing |
| Card re-render on single rollup field update | **≤ 8 ms** (per-card; only the affected card re-renders) | `FeatureCard` / `FeatureListCard` must be wrapped in `React.memo` with stable prop identity | React Profiler: assert sibling cards do not re-render when one rollup updates |
| Kanban column re-group (status change for 1 card) | **≤ 10 ms** | Column arrays must be memoized; only the changed column array must change identity | Vitest: assert column memo for unchanged columns returns same reference |
| Rollup merge into board state (100 items) | **≤ 3 ms** | Merge must not trigger a full board re-render | Vitest: assert board root does not re-render on rollup-only state update |

---

## 3. Modal Budgets

### 3.1 Request Count

| Scenario | Budget | Rationale | Assertion method |
|---|---|---|---|
| Cold modal open (any tab) | **1 request**: 1 × `GET /api/v1/features/{id}?include=overview_shell` | Replaces today's 2 unconditional requests (full detail + full linked-sessions) | Vitest mock-fetch counter: assert `fetchSpy.callCount === 1` on modal mount before any tab click |
| Overview tab render (cold) | **1 request** (included in cold open above) | Overview is the default tab; no supplemental fetch | Assertion covered by cold-open test |
| Overview tab render (warm cache, re-open within staleTime=30s) | **0 requests** | Shell is cached | Vitest: re-mount modal, assert no fetch |
| Phases tab — first activation | **1–2 requests**: 1 × `GET /features/{id}/phases` + optionally 1 × `GET /features/{id}/phases/session-annotations` | Phases data is lazy | MSW: assert these 2 endpoints fire on first Phases tab click, no others |
| Phases tab — subsequent activations (within staleTime=60s) | **0 requests** | Cached | Vitest: second tab click, assert no fetch |
| Documents tab — first activation | **0 requests** (renders from Overview shell `linkedDocs` metadata) | Docs metadata is in the shell | Vitest: assert no fetch on Documents tab click after shell has loaded |
| Relations tab — first activation | **0 requests** (renders from Overview shell) | Relations data is in the shell | Same assertion pattern as Docs |
| Sessions tab — first activation | **1 request**: 1 × `GET /features/{id}/sessions?limit=20` | Tile summary from rollup cache; list is paged | MSW: assert exactly 1 sessions endpoint call on first Sessions tab click; assert no `linked-sessions` call |
| Sessions tab — paginate (next page) | **1 request** per page | Cursor-based pagination | MSW: assert one new sessions request per "Load more" |
| Test Status tab — first activation | **1 request**: 1 × `GET /health/features?...&feature_id={id}&limit=1` | Independent health endpoint | MSW: assert exactly 1 health call on Test Status tab click |
| History/Activity tab — first activation | **1 request**: 1 × `GET /features/{id}/activity?limit=50` | New activity aggregate endpoint | MSW: assert 1 activity call; assert no `linked-sessions` call |
| Modal re-open after live invalidation | **1 request** (re-fetches shell) | `featureTopic` invalidation marks shell stale | Vitest: fire mock live event, re-open modal, assert 1 fetch |

**Hard rule**: `GET /api/features/{id}/linked-sessions` must never fire on
modal open or on any tab activation. Any occurrence is a test failure. This
includes the eagerly-fired calls currently in `refreshLinkedSessions` inside
the modal `useEffect`.

### 3.2 Sessions Tab Pagination Budget

| Parameter | Value | Rationale | Enforcement |
|---|---|---|---|
| Default page size | **20 rows** | Visible viewport fits ~6–8 session cards; 20 is 2–3 viewport heights | `limit` default in hook; backend hard-cap at 50 |
| Hard max page size | **50 rows** | Backend returns `422` if `limit > 50` | Backend validation; Vitest asserts default is 20 |
| Per-page response payload | **≤ 40 KB** (gzip, 20 rows, no enrichment includes) | 20 × ~2 KB per session item | MSW response size interceptor |
| Per-session item payload (no includes) | **≤ 2 KB** | Scalar fields only; no log arrays, no inline task annotations | Vitest: measure per-item serialized size |
| Per-session item payload (with `include=tokens`) | **≤ 3.5 KB** | Adds per-model token breakdown | Same |
| Per-session item payload (with `include=logs`) | **Uncapped (not budgeted)** | Log data is unbounded by design; this include is a user-explicit action | No budget assertion; test must verify `include=logs` is never auto-requested |
| Cursor-based pages (not offset) | Cursor must be opaque string | Prevents page-drift during concurrent sync updates | Contract test: response carries `next_cursor` string or `null` |

### 3.3 Overview Shell Payload

| Metric | Budget | Ceiling | Assertion method |
|---|---|---|---|
| Overview shell response size | **≤ 15 KB** (gzip) | 22 KB | MSW response size interceptor; Vitest byte check |
| `linkedDocs` metadata items in shell | **≤ 100 items** | Hard cap in API | Backend: return 422 or truncate + `truncated: true` flag if feature has > 100 docs |
| `blockingFeatures` items in shell | **≤ 10 items** | Hard cap in API | Same |

### 3.4 Latency (p50 / p95, local fixture set)

| Endpoint | p50 target | p95 target | Fixture | Assertion method |
|---|---|---|---|---|
| `GET /api/v1/features/{id}` (overview shell) | **≤ 20 ms** | **≤ 50 ms** | Medium feature (5 phases, 10 docs) | OTEL `feature_shell_duration_ms` |
| `GET /api/v1/features/{id}/sessions` (page 1, 20 items) | **≤ 25 ms** | **≤ 70 ms** | Feature with 50 linked sessions | OTEL `feature_sessions_page_duration_ms` |
| `GET /api/v1/features/{id}/sessions` (page 1, 20 items, large session set) | **≤ 40 ms** | **≤ 100 ms** | Feature with 200 linked sessions | Same histogram |
| `GET /api/v1/features/{id}/activity` (50 commits) | **≤ 35 ms** | **≤ 90 ms** | Feature with 50 linked sessions + commits | OTEL `feature_activity_duration_ms` |
| `GET /api/v1/features/{id}/phases` | **≤ 15 ms** | **≤ 40 ms** | Feature with 10 phases / 50 tasks | OTEL `feature_phases_duration_ms` |
| Cold modal open (user-perceived: shell request + first render) | **≤ 100 ms** | **≤ 250 ms** | Medium feature | Playwright `performance.measure` from modal open event to `data-modal-ready` attribute |

### 3.5 Client-Side Compute

| Operation | Budget (ms, main thread) | Memo stability | Assertion method |
|---|---|---|---|
| Modal initial render (Overview tab, shell loaded) | **≤ 30 ms** (commit phase) | N/A | React Profiler `actualDuration` in Vitest |
| Tab switch (Overview → Phases, phases cached) | **≤ 15 ms** | Tab content must be memoized by tab ID | React Profiler |
| Sessions tab — render 20 session cards | **≤ 25 ms** | Cards must be `React.memo`-wrapped | React Profiler |
| Sessions tab — append next 20 session cards (pagination) | **≤ 20 ms** (incremental) | Existing cards must not re-render on append | React Profiler: assert prior cards `actualDuration === 0` on append |
| `resolveTokenMetrics` on session card | **Not called on client at all** | Server pre-computes `workloadTokens` and `cacheShare` on each session item | Vitest: assert `resolveTokenMetrics` is never imported or called in the new Sessions tab hook path |

---

## 4. Cache Budgets

The frontend cache follows the **planning-style bounded LRU** pattern established
in `services/planning.ts`. A per-resource entry is the unit of eviction.

### 4.1 Board-Level Caches

| Cache | Key shape | Max entries | TTL (staleTime) | Eviction policy | Invalidation triggers | OTEL metric |
|---|---|---|---|---|---|---|
| Feature list pages | `[projectId, filters, sort, offset, limit]` | **20 pages** (covers 10 pages forward + 10 back with generous buffer) | **30 s** | LRU — oldest page evicted when limit is exceeded | Project change; filter param change; `featureTopic('*')` live event | `feature_list_cache_hit_ratio` |
| Feature rollup batches | `[projectId, sortedFeatureIds, includeFlags]` | **10 batches** (~1,000 individual rollup entries given 100 IDs/batch) | **60 s** | LRU — oldest batch evicted | `featureTopic(featureId)` live event for any ID in the batch; sync-engine `cacheVersion` change | `feature_rollup_cache_hit_ratio` |
| Individual rollup entries (within a batch) | N/A — entries are always fetched in batch, not individually | Derived from batch entries (max 100 per batch × 10 batches = **1,000 rollup entries**) | Inherits batch TTL | N/A | Inherits batch invalidation | Same `feature_rollup_cache_hit_ratio` |
| Rollup `cacheVersion` token | `[projectId]` | 1 per project | Matches rollup TTL | N/A; always overwritten | Backend `cacheVersion` change in response envelope | `rollup_cache_version_mismatches` |

**Board total memory target**: Feature list pages (20 × 80 KB each = 1.6 MB)
+ rollup batches (10 × 60 KB each = 600 KB) = **≤ 2.2 MB** per project in the
board cache. This is the acceptance ceiling; exceeding it is a regression.

### 4.2 Modal-Level Caches

| Cache | Key shape | Max entries | TTL (staleTime) | Eviction policy | Invalidation triggers | OTEL metric |
|---|---|---|---|---|---|---|
| Feature overview shell | `['feature', 'modal-overview', projectId, featureId]` | **50 features** (LRU; covers recently-viewed features during a session) | **30 s** | LRU — oldest feature shell evicted at 51st entry | `featureTopic(featureId)` live event; mutation of status/phase/task | `feature_shell_cache_hit_ratio` |
| Feature phases + tasks | `['feature', 'phases', projectId, featureId]` | **50 features** | **60 s** | LRU | `featureTopic(featureId)`, `featurePhaseTopic(featureId, *)` | `feature_phases_cache_hit_ratio` |
| Feature phase annotations | `['feature', 'phase-annotations', projectId, featureId]` | **50 features** | **60 s** | LRU | `featureTopic(featureId)` | (shared with phases metric) |
| Sessions first page | `['feature', 'sessions', projectId, featureId, null, '']` | **20 features** (fewer entries; session pages are larger) | **15 s** | LRU | `featureTopic(featureId)` — all session pages for the feature are evicted together | `feature_sessions_cache_hit_ratio` |
| Sessions subsequent pages | `['feature', 'sessions', projectId, featureId, cursor, include]` | **60 pages total** across all features (20 features × 3 pages average) | **15 s** | LRU (page-level) | Same as first page | Same metric |
| Feature test health | `['feature', 'test-health', projectId, featureId]` | **50 features** | **60 s** | LRU | `projectTestsTopic(projectId)` | `feature_test_health_cache_hit_ratio` |
| Feature activity | `['feature', 'activity', projectId, featureId, cursor]` | **30 entries** (20 features × first page + 10 subsequent pages) | **60 s** | LRU | `featureTopic(featureId)` | `feature_activity_cache_hit_ratio` |

**Modal total memory target**: 50 shells × 15 KB + 50 phases × 5 KB + 20 session first-pages × 40 KB + ancillary = **≤ 2.5 MB** per project in the modal cache.

**Combined board + modal memory ceiling**: **≤ 5 MB** per project. This is the
single most consequential cache regression guard (see §5).

### 4.3 Cache Eviction and Cross-Cache Invalidation

| Rule | Specification |
|---|---|
| Project switch | All board and modal caches for the previous project are purged immediately. Caches for the new project start empty (no cross-project data retained in memory). |
| `featureTopic(featureId)` live event | Invalidates: overview shell, phases, phase-annotations, all session pages, activity for that `featureId`. Does NOT invalidate: test health (separate topic), feature list pages (those re-fetch on next interaction), rollup batches containing that ID (re-fetch on next board render). |
| Sync-engine `cacheVersion` change | Invalidates: all rollup batches for the project. Does NOT invalidate: modal shell or session caches (they have their own freshness semantics). |
| `projectTestsTopic(projectId)` | Invalidates: all test-health entries for the project. |

---

## 5. Regression Guard vs Today

The following table maps today's observed/approximate worst-case behavior to
the target value and the measurement method for CI regression detection.

| Metric | Today (observed / approximate) | Target | Delta | CI measurement |
|---|---|---|---|---|
| **Board cold-open request count** (50-card page) | **51 requests** (1 list + 50 per-card `/linked-sessions` calls) | **2 requests** | −96% | Vitest mock-fetch counter in `ProjectBoard` render test; fail if count > 2 |
| **Board initial network payload** (50-card page, uncompressed) | **~2–10 MB** (50 full linked-session arrays, each potentially hundreds of `FeatureSessionLink` objects) | **≤ 140 KB** gzip (80 KB list + 60 KB rollup) | −97 to −99% | MSW response size interceptor; fail if gzip total > 200 KB |
| **Modal cold-open request count** | **2 requests** (full feature detail + full linked-sessions) | **1 request** (overview shell) | −50% | Vitest mock-fetch counter; fail if count > 1 on modal mount |
| **Modal linked-sessions payload per open** | **Unbounded** (full `FeatureSessionLink[]` array; could be 100+ objects × ~3 KB = 300+ KB) | **0 bytes** (no linked-sessions call on open) | −100% | MSW: assert `linked-sessions` endpoint receives 0 requests on modal mount |
| **Sessions tab first-page payload** | **Same as above** (all linked sessions downloaded for any tab) | **≤ 40 KB** (20 session items × ~2 KB, gzip) | −87 to −99% | MSW response size interceptor on Sessions tab activation |
| **Client-side token metric computation** (`resolveTokenMetrics` calls per board render) | **N × M** (N cards × M sessions per card; O(n²) for subthread detection) | **0 calls** (server pre-computes `workloadTokens` and `cacheShare`) | −100% | Vitest: assert `resolveTokenMetrics` is never called in board render path |
| **`buildFeatureSessionSummary` calls per board render** | **50 calls** (one per visible card) | **0 calls** (replaced by rollup DTO fields) | −100% | Vitest: assert `buildFeatureSessionSummary` is never called in board render path |
| **Board `filteredFeatures` useMemo input size** | **≤ 5,000 features** (current `limit=5000` call) | **≤ 50 features** (paginated list window) | −99% | Vitest: assert `getFeatures` is never called with `limit > 200` in the new path |
| **Modal mount-time linked-sessions fetch** | **Always fires** (`refreshLinkedSessions` `useEffect` on every mount) | **Never fires on mount** | −100% | Vitest: assert no `linked-sessions` request fires in the first 500 ms after modal mount |
| **Frontend cache memory** (board + modal, 1 project) | **Unbounded** (no LRU; all 5,000 features plus all linked-session arrays retained for the session lifetime) | **≤ 5 MB** | Bounded | Vitest: measure `JSON.stringify(cacheSnapshot).length`; fail if > 6 MB |
| **Main-thread time per board render** (50 cards, including session summary computation) | **~150–500 ms** (estimated; `buildFeatureSessionSummary` × 50 + `resolveTokenMetrics` O(n²) across sessions) | **≤ 50 ms** | −67 to −90% | React Profiler `actualDuration` in Vitest; Playwright `Long Tasks` audit |

**The single most consequential regression guard**: Board cold-open request
count must be **≤ 2** (1 list + 1 rollup). Any `GET /api/features/{id}/linked-sessions`
call on board render is a hard failure. This is the primary hotspot removed by
the redesign, and its re-emergence would fully negate the performance gain.

---

## 6. Measurement and Instrumentation Plan

### 6.1 OTEL Metric Names (Phase 5 must add these)

| OTEL metric name | Type | Labels | What it measures |
|---|---|---|---|
| `feature_list_request_count` | Counter | `project_id`, `surface` (board/planning), `cache_hit` (bool) | Total feature list requests; cache_hit tracks SWR hits |
| `feature_list_duration_ms` | Histogram (p50, p95) | `project_id`, `filter_params` (sanitized key) | Backend query time for `GET /api/v1/features` |
| `feature_list_payload_bytes` | Histogram | `project_id`, `page_size` | Serialized response size |
| `feature_rollup_request_count` | Counter | `project_id`, `batch_size`, `cache_hit` (bool) | Rollup requests; `batch_size` = number of IDs |
| `feature_rollup_duration_ms` | Histogram (p50, p95) | `project_id` | Backend aggregation time for `POST /api/v1/features/rollups` |
| `feature_rollup_payload_bytes` | Histogram | `project_id`, `batch_size` | Rollup response size |
| `feature_shell_request_count` | Counter | `project_id`, `cache_hit` (bool) | Modal shell fetch requests |
| `feature_shell_duration_ms` | Histogram (p50, p95) | `project_id` | Backend time for overview shell |
| `feature_shell_payload_bytes` | Histogram | `project_id` | Shell response size |
| `feature_sessions_page_duration_ms` | Histogram (p50, p95) | `project_id`, `page_number`, `include_flags` | Backend time for paginated sessions endpoint |
| `feature_sessions_payload_bytes` | Histogram | `project_id`, `page_size`, `include_flags` | Sessions page response size |
| `feature_activity_duration_ms` | Histogram (p50, p95) | `project_id` | Backend time for activity endpoint |
| `feature_phases_duration_ms` | Histogram (p50, p95) | `project_id` | Backend time for phases endpoint |
| `feature_list_cache_hit_ratio` | Gauge | `project_id` | Frontend SWR cache hit rate for list pages |
| `feature_rollup_cache_hit_ratio` | Gauge | `project_id` | Frontend cache hit rate for rollup batches |
| `feature_shell_cache_hit_ratio` | Gauge | `project_id` | Frontend cache hit rate for modal shells |
| `feature_sessions_cache_hit_ratio` | Gauge | `project_id` | Frontend cache hit rate for session pages |
| `feature_test_health_cache_hit_ratio` | Gauge | `project_id` | Frontend cache hit rate for test health |
| `feature_activity_cache_hit_ratio` | Gauge | `project_id` | Frontend cache hit rate for activity pages |
| `rollup_cache_version_mismatches` | Counter | `project_id` | How often the `cacheVersion` token changes, triggering full rollup re-fetch |
| `legacy_linked_sessions_call_count` | Counter | `project_id`, `surface` | Calls to the old `/linked-sessions` endpoint — must trend to 0 after rollout |

### 6.2 Testing Methods by Budget Category

| Budget category | Primary method | Secondary method |
|---|---|---|
| Request count | **Vitest mock-fetch counter**: wrap `fetch` with a spy, assert call count per scenario | MSW request interception: assert specific endpoint URLs are or are not called |
| Payload size | **MSW response size interceptor**: measure `response.json()` stringified byte length | Backend pytest: assert `len(json.dumps(response))` against ceiling |
| Backend latency | **Backend pytest timer**: `time.perf_counter()` around handler; parameterized by fixture size | OTEL histogram in integration test environment |
| Frontend latency (main thread) | **React Profiler `actualDuration`** in Vitest via `@testing-library/react` `Profiler` wrapper | Playwright `Long Tasks` observer in E2E smoke test |
| Cache hit ratio | **Vitest**: spy on `fetch`; assert 0 calls on warm-cache render | Manual: React Query devtools in dev |
| Cache memory | **Vitest**: serialize query client cache snapshot, measure byte length | `performance.memory.usedJSHeapSize` in Playwright (Chromium only) |
| Memo stability | **Vitest + `renderHook`**: assert `result.current.filteredFeatures === prevResult.current.filteredFeatures` when inputs unchanged | React DevTools Profiler (manual) |

---

## 7. Acceptance Gate for Legacy Removal

The legacy eager path (`GET /api/features/{id}/linked-sessions` fired per card,
and `refreshLinkedSessions` fired on modal mount) may be removed from production
code only when **all of the following gates pass in CI**:

| Gate | Pass condition | Measured by |
|---|---|---|
| **G1 — Board request count** | `fetchSpy.callCount === 2` on cold board render (50 cards, medium fixture) | Vitest mock-fetch counter |
| **G2 — No linked-sessions on board** | `fetchSpy` records zero calls matching `/linked-sessions` on board render | Vitest URL assertion |
| **G3 — No linked-sessions on modal mount** | `fetchSpy` records zero calls matching `/linked-sessions` within 500 ms of modal mount | Vitest URL + timer assertion |
| **G4 — Modal cold-open request count** | `fetchSpy.callCount === 1` on cold modal mount (before any tab click) | Vitest mock-fetch counter |
| **G5 — Sessions tab payload** | First-page response ≤ 40 KB gzip for 20 items | MSW response size interceptor |
| **G6 — Board payload ceiling** | Total gzip payload (list + rollup) ≤ 200 KB on cold render | MSW: sum of all response sizes on board mount |
| **G7 — Parity: session counts** | `rollup.sessionCount` matches `buildFeatureSessionSummary(legacyLinkedSessions).total` for every fixture feature (tolerance: 0 — exact match required) | Vitest: run both paths against medium fixture, compare outputs |
| **G8 — Parity: token totals** | `rollup.observedTokens` matches `sum(resolveTokenMetrics(s).workloadTokens for s in legacySessions)` for every fixture feature (tolerance: ±1 integer rounding) | Same |
| **G9 — Parity: display cost** | `rollup.displayCost` matches `sum(resolveDisplayCost(s) for s in legacySessions)` (tolerance: ±0.01 USD) | Same |
| **G10 — Legacy endpoint remains available** | `GET /api/features/{id}/linked-sessions` continues to return 200 at time of legacy removal (it is not deleted — only the client call paths are removed) | Backend API test |
| **G11 — Feature flag controlled** | `FEATURE_SURFACE_V2` flag enables new path; disabling it restores legacy path and passes existing legacy tests | Vitest: parameterized test run with flag on and off |
| **G12 — Cache memory ceiling** | Serialized query client cache ≤ 6 MB after rendering 50-card board + opening 5 modals | Vitest cache snapshot size assertion |
| **G13 — Main-thread board render** | React Profiler `actualDuration` ≤ 50 ms for 50-card board | Vitest Profiler assertion |

**Gates G1, G2, G3, G4 are blockers** — failure on any one of these prevents
legacy removal regardless of all others passing. G5–G13 are quality gates that
must also pass but individually allow a hold-and-investigate workflow rather
than an immediate rollback.

---

## 8. Open Questions

1. **Rollup latency under large session counts.** The p95 rollup target of
   140 ms for 100 IDs assumes SQLite with the session aggregation query using
   indexed `feature_id` + `project_id` columns. If session row counts per feature
   exceed ~500 and indexes are absent, this p95 will be exceeded. Phase 1 must
   confirm index coverage before locking these numbers.

2. **Board payload ceiling under large `linkedDocs` arrays.** The list DTO
   decision (P0-003 §5) removes `linkedDocs[]` from the list row, but the
   `documentCoverage` scalar counts remain. If a feature has unusual numbers of
   quality-signal `integritySignalRefs[]` (an array field staying in the list
   row), the per-row average could exceed 2.5 KB. Phase 1 must measure typical
   `integritySignalRefs` array sizes and either cap them or move them to the
   rollup.

3. **Phase annotation payload vs. session annotation budget.** P0-004 §2.2
   caps `sessionIds` and `commitHashes` at 5 per phase/task in the annotation
   endpoint. If a phase has 30 linked sessions (common for long-running
   multi-agent phases), the cap silently truncates. The annotation response
   should carry a `truncated: true` field; the budget must be revised once
   typical phase-to-session cardinality is measured in P0-006 fixtures.

4. **`unresolvedSubthreadCount` computation overhead.** P0-003 classifies this
   field as `partial` and gated by `include.subthreadResolution=false` (default).
   If the backend opts to compute it eagerly, the self-join may add 10–30 ms to
   rollup p95 for large session sets. Budget impact must be validated in Phase 1
   query profiling before enabling by default.

5. **Frontend cache memory measurement accuracy.** The `JSON.stringify(cacheSnapshot)`
   method underestimates actual V8 heap usage (object headers, closures, React
   Query internal structures). Phase 5 should use `performance.memory.usedJSHeapSize`
   in a Playwright Chromium test as the authoritative memory gate, with the
   stringify method as a fast Vitest approximation.

6. **Debounce alignment between filter and rollup.** Filter debounce is
   specified at 300 ms; rollup ID-list debounce at 150 ms. If a filter change
   produces a new feature set, the rollup must wait for the list response before
   sending new IDs. The effective rollup debounce from a user filter keystroke
   is therefore 300 ms (list debounce) + network round-trip + 150 ms (rollup
   debounce). Verify this does not cause a perceptible badge-flash (tiles showing
   stale rollup values for > 500 ms after a filter change) in Playwright
   interaction tests.

7. **Activity endpoint existence.** `GET /api/v1/features/{id}/activity` does
   not exist yet (P0-004 OQ-1). The History tab latency budget (p50 ≤ 35 ms,
   p95 ≤ 90 ms) is forward-specified and cannot be asserted until Phase 2
   implements the endpoint. Phase 5 must add the gate once the endpoint is
   available; it should not block the acceptance gate for legacy removal of the
   board/modal session eager-loading paths.
