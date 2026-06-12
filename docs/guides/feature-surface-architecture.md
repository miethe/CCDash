# Feature Surface Architecture Guide

Last updated: 2026-06-12

This guide documents the redesigned feature-surface data contracts, caching strategy, and performance budgets for CCDash developers. It describes which API endpoint to use for card-level metrics vs modal sections, how the frontend caches work, and what invalidation events clear which caches.

---

## Overview

The feature surface uses a **two-layer caching architecture** separating server-side and client-side concerns:

**Backend (server-side):**
1. **Repository layer** (`backend/db/repositories/features.py`, `postgres/features.py`): Filtering, sorting, pagination, and aggregation queries.
2. **Service layer** (`backend/application/services/feature_surface/*.py`): DTO assembly, freshness metadata, cross-domain enrichment.
3. **Query cache** (`backend/application/services/agent_queries/cache.py:50`): `@memoized_query` decorator with ~600s TTL caching expensive reads.
4. **Router layer** (`backend/routers/features.py`): HTTP contracts, parameter validation, observability instrumentation.

**Frontend (client-side):**
5. **Query client** (`lib/queryClient.ts`): TanStack Query `QueryClient` managing all server-state caching; staleTime: 30s–5min per query.
6. **Domain query hooks** (`services/queries/*.ts`): TQ-backed hooks wrapping feature endpoints; query keys registered at `services/queryKeys.ts`.
7. **Component layer**: Features, cards, modals consume domain hooks; TQ caching layer enables instant back-navigation renders from previously-visited routes.

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

**Owns:** Feature board data loading (list + rollup in one call sequence), TQ-backed.

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

**Cache policy:** TanStack Query QueryClient backed:
- **List query**: Keyed via registry at `services/queryKeys.ts`. staleTime: 30s. Enabled only when `projectId` is set.
- **Rollup query**: Separate TQ query, keyed on sorted feature IDs. staleTime: 30s. Stale-while-revalidate pattern via TQ's background refetch.
- Back-navigation renders instantly from TQ cache for previously-visited routes.

**When to use:**
- Rendering ProjectBoard columns and feature cards.
- Any UI that displays a paginated, filterable feature list with summary metrics.
- **Never** call this once per card to fetch detail; use the rollup endpoint instead.

**Invalidation:**
- `queryClient.invalidateQueries({ queryKey: featureSurfaceKeys.list(...) })` — clears list pages.
- `queryClient.invalidateQueries({ queryKey: featureSurfaceKeys.rollups(...) })` — clears rollup cache.
- Automatically invoked in mutation handlers (e.g., after feature status/phase/task writes).

### `useFeatureModalData(featureId, options)`

**Owns:** Per-section modal tab loading (overview, phases, docs, relations, sessions, test-status, history), TQ-backed.

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

**Cache policy:** TanStack Query backed per modal section:
- Keyed via `services/queryKeys.ts` registry (e.g., `featureModalKeys.overview(featureId)`).
- staleTime: 30s–1min per section (varies by section weight).
- Separate queries per section avoid eviction conflicts.
- Each section loads independently; no eager fetch of all tabs.

**When to use:**
- Each modal tab loads independently on click (no eager fetch of all tabs).
- Supports pagination within Sessions tab without refetching all previous pages.
- Prefetch sections before the user clicks to reduce perceived latency.
- **Never** open a modal and immediately fetch all tab data; use the lazy-load pattern.

**Invalidation:**
- `queryClient.invalidateQueries({ queryKey: featureModalKeys.section(featureId, sectionName) })` — clears one section.
- `queryClient.invalidateQueries({ queryKey: featureModalKeys.allForFeature(featureId) })` — clears all sections for a feature.
- Automatically invoked in mutation handlers after feature writes.

---

## Cache Invalidation

All server-state is managed by TanStack Query. Invalidation happens through the QueryClient:

```typescript
// From ProjectBoard.tsx or any mutation handler
await updateFeatureStatus(featureId, newStatus);

// Invalidate affected feature queries
queryClient.invalidateQueries({
  queryKey: featureSurfaceKeys.list(projectId)
});
queryClient.invalidateQueries({
  queryKey: featureSurfaceKeys.rollups(projectId)
});
queryClient.invalidateQueries({
  queryKey: featureModalKeys.allForFeature(featureId)
});
```

**Mutation patterns:** Most mutations are handled by calling `queryClient.invalidateQueries()` in the mutation handler's `onSuccess` callback. TQ automatically refetches stale queries on next access.

**Project switch:**

```typescript
// From context provider or route handler
handleProjectChange(newProjectId);
queryClient.clear(); // or selectively invalidate previous project's queries
```

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

1. ✅ **Use `useFeatureSurface` for list + card metrics** — TQ-backed, never fetch detail per card.
2. ✅ **Use `useFeatureModalData` for modal tabs** — TQ-backed, sections load independently on tab click.
3. ✅ **Invalidate via QueryClient** — call `queryClient.invalidateQueries()` in mutation handlers, not via deleted cache bus.
4. ✅ **Use queryKey registry** — hook into keys from `services/queryKeys.ts`; never hard-code query keys.
5. ✅ **Encode feature IDs in URLs** — `encodeURIComponent(featureId)` in all API paths.
6. ✅ **Handle missing rollup gracefully** — if a feature has no rollups in the response, show a fallback badge.
7. ✅ **Never prefetch all modal tabs** — wait for user intent (tab click).
8. ✅ **Page before enriching** — the API does this for you; don't add extra joins client-side.

---

---

## Session-Detail Surface

The session-detail surface is a separate read domain from the feature surface. It is used to retrieve full session data (transcript, tokens, subagents, artifacts, entity links) for any project's session. The entry point is transport-neutral; all three transports (REST, MCP, CLI) delegate to the same service function.

### Transport-Neutral Service (`agent_queries/session_detail.py`)

`backend/application/services/agent_queries/session_detail.py` is the **single source of truth** for all session detail reads. No transport implements its own transcript reader or redaction logic.

The public entry point:

```python
# backend/application/services/agent_queries/session_detail.py
async def get_session_detail(
    project_id: str,
    session_id: str,
    ports: CorePorts,
    *,
    include: FrozenSet[str] | set[str] | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    context: RequestContext | None = None,
) -> SessionDetailBundle | None
```

**Include flags** (any subset, or `None` for all):

| Flag | Segment returned |
|------|----------------|
| `transcript` | Cursor-paginated log entries (already redacted) |
| `subagents` | Child session rows resolved via `list_relationships` |
| `tokens` | Token telemetry dict extracted from the session row |
| `artifacts` | Entity links whose `source_type` or `target_type` is an artifact variant (`artifact`, `document`, `file`, `attachment`) |
| `links` | All remaining (non-artifact) entity links for the session |

Unknown flags are logged and ignored — they do not raise.

**Service constants:**
- `DEFAULT_TRANSCRIPT_LIMIT = 200` items per page
- `MAX_TRANSCRIPT_LIMIT = 1000` items per page (over-limit values are clamped, not rejected)

**Returns:** `SessionDetailBundle` when found, `None` when the session does not exist or the `project_id` does not match the row's own project.

---

### Cursor-Pagination Envelope

All transcript responses use the cursor-pagination envelope:

```json
{
  "items":      [...],
  "cursor":     "<opaque base64 string — the cursor used for this page>",
  "limit":      200,
  "nextCursor": "<opaque base64 string>  | null"
}
```

`cursor` and `nextCursor` are opaque URL-safe base64-encoded JSON strings (`{"o": <offset>}`). `nextCursor` is `null` when this is the last page. Pass the previous `nextCursor` value as the `cursor` parameter on the next call to advance the page. Invalid or empty cursors reset silently to offset 0.

The `SessionTranscriptPageV1` contract (standalone `/transcript` endpoint) adds `sessionId`, `projectId`, and `redactedFieldCount` identity fields to the same envelope:

```json
{
  "sessionId":          "<id>",
  "projectId":          "<id>",
  "items":              [...],
  "cursor":             "<opaque>",
  "limit":              200,
  "nextCursor":         "<opaque> | null",
  "redactedFieldCount": 0
}
```

---

### Redaction Layer

Redaction is applied by `agent_queries/session_detail.py` via `agent_queries/redaction.redact_entries` **before** the bundle is returned to any transport. Secrets are scrubbed at a single egress boundary; no transport adds its own redaction logic. `redactedFieldCount` in the bundle (and in every transcript envelope) is the aggregate count of fields redacted across the page.

Redaction failures are logged and the entry passes through unredacted — delivery safety is preferred over a 500 in edge cases.

---

### REST Transport

Two Phase 2 endpoints in `backend/routers/client_v1.py` (handler logic in `backend/routers/_client_v1_sessions.py`):

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `GET /api/v1/sessions/{id}/detail` | Full bundle — all include segments | `?project_id=` required (HTTP 400 if absent); `?include=` repeatable; `?cursor=`, `?limit=` (1–1000, default 200) |
| `GET /api/v1/sessions/{id}/transcript` | Transcript page only | `?project_id=` required (HTTP 400 if absent); same cursor/limit params |

Both endpoints:
- Require an explicit `project_id` — there is **no active-project fallback** (HTTP 400 if absent).
- Return HTTP 404 when the session is not found in the given project.
- Delegate entirely to `get_session_detail`; the handler adds no business logic.

---

### MCP Transport

Three tools registered in `backend/mcp/tools/sessions.py` (all require explicit `project_id`; no active-project fallback):

| Tool | Purpose |
|------|---------|
| `ccdash_session_detail` | Full bundle — all or selected include segments |
| `ccdash_session_transcript` | Transcript page only |
| `ccdash_session_search` | Full-text / keyword search across transcripts |

**MCP payload budget constants** (transport-specific, more conservative than REST):

| Constant | Value | Purpose |
|----------|-------|---------|
| `MCP_TRANSCRIPT_DEFAULT_LIMIT` | 50 | Default items per MCP call |
| `MCP_TRANSCRIPT_MAX_LIMIT` | 200 | Per-call ceiling (below the service max of 1 000) |
| `MCP_ENVELOPE_MAX_BYTES` | 1 048 576 (1 MiB) | Hard byte ceiling after serialisation |

When the serialised response exceeds `MCP_ENVELOPE_MAX_BYTES`, transcript items are trimmed from the tail and `meta.truncated: true` is set with a `meta.truncated_reason` containing cursor guidance. Over-budget responses never silently drop items.

---

### CLI Transport (repo-local)

Three commands in `backend/cli/commands/session.py`:

| Command | Purpose |
|---------|---------|
| `ccdash session get <id> --project <pid>` | Full detail bundle |
| `ccdash session transcript <id> --project <pid>` | Transcript page only |
| `ccdash session search <query> [--project]` | Search transcripts |

`--project` is **required** for `get` and `transcript` (mirrors the REST invariant). The standalone `ccdash` CLI (`packages/ccdash_cli/`) exposes the same commands over HTTP via `GET /api/v1/sessions/{id}/detail` and `GET /api/v1/sessions/{id}/transcript`.

---

### Cache Tiers

| Layer | Cache | Notes |
|-------|-------|-------|
| Backend service (`session_detail.py`) | None — **no `@memoized_query`** | Transcript content is cursor-paginated per-request; caching at the service layer would break cursor semantics. Each call fetches fresh data from the repository. |
| Frontend — detail (`useSessionDetailQuery`) | TanStack Query `staleTime: 30 000 ms`, `gcTime: 300 000 ms` | Keyed via `sessionsKeys.detail(projectId, sessionId)`. Concurrent calls within the stale window deduplicate automatically. |
| Frontend — list (`useSessionsQuery`) | TanStack Query `staleTime: 30 000 ms` | Infinite-scroll list keyed via `sessionsKeys.list(projectId, filters)`. |

**Key principle:** The session-detail bundle is not `@memoized_query` cached on the server. Client-side TQ caching provides the dedup and back-navigation performance guarantee.

---

## Related Documentation

- **Rollback Guide:** [`docs/guides/feature-surface-v2-rollback.md`](./feature-surface-v2-rollback.md) — How to disable v2 and revert to legacy paths in an emergency.
- **QueryClient Configuration:** `lib/queryClient.ts` — TanStack Query client setup with staleTime defaults and global configuration.
- **QueryKey Registry:** `services/queryKeys.ts` — Centralized query key definitions for all feature surface, feature modal, and session queries.
- **Implementation Plan:** [`docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md`](../project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md) § Architecture Direction — Authoritative contract table and layering rules.
- **CLAUDE.md § Frontend Data Layer:** [./CLAUDE.md](../../CLAUDE.md) — Project-wide architecture context for TQ QueryClient and service queries.
- **Contracts package:** `packages/ccdash_contracts/src/ccdash_contracts/models.py` — `SessionDetailV1`, `SessionTranscriptPageV1`, `TranscriptPageV1` Pydantic models; authoritative camelCase field names.
- **MCP session tools:** `backend/mcp/tools/sessions.py` — `register_session_tools`; MCP payload budget constants.
