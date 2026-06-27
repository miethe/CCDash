# CCDash Frontend Data Layer Inventory
<!-- For: TanStack Query migration PRD -->
<!-- Date: 2026-05-28 -->

---

## 1. Context Layer

### AppEntityDataContext.tsx — 476 lines
**Server-state held**: sessions (AgentSession[], paginated 50/page), sessionTotal, sessionFilters, documents (PlanDocument[], paginated 500/page), tasks (ProjectTask[]), alerts (AlertConfig[]), notifications (Notification[]), features (Feature[]).
**Client-state held**: pendingFeatureStatusById (optimistic map), sessionFilters, documentOffset/Total.
**Eager fetches on mount**: `useEffect(() => { void refreshSessions(true); }, [refreshSessions])` at line 111 — fires immediately when provider mounts (gated by `AppDataProviderGate`).
**Hooks exposed**: `useAppEntityData()` — returns all entity arrays + refresh/mutation callbacks.
**Bespoke caching**:
- `sessionDetailRequestsRef` (Map<string, Promise>) — in-flight dedup ref for `getSessionById`, TTL 30 s (`SESSION_DETAIL_TTL_MS = 30_000`). Entries GC'd by `gcSessionDetailRequests()` only when `isMemoryGuardEnabled()`.
- `sessionDetailTimestampsRef` (Map<string, number>) — parallel timestamp map for TTL sweep.
- `refreshFeaturesInFlightRef` (Ref<Promise|null>) — single-flight dedup for `refreshFeatures`.
- `SESSIONS_PER_PAGE = 50` constant at line 48; documents page size hard-coded 500 at line 173.
- `MAX_DOCUMENTS_IN_MEMORY` cap (2000, from `constants.ts:391`) applied in `refreshDocuments` when memory guard enabled.
- Tasks fetched unbounded: `/tasks?offset=0&limit=5000` (apiClient.ts:401).
- Features fetched unbounded: `/features?offset=0&limit=5000` (apiClient.ts:413).

### AppSessionContext.tsx — 88 lines
**Server-state**: projects (Project[]), activeProject (Project | null). No eager mount fetch — `refreshProjects` is called by `AppRuntimeContext.refreshAll()` not on its own mount.
**Client-state**: project scope (via `client.setProjectScope`).
**Hooks exposed**: `useAppSession()` — projects, activeProject, refreshProjects, addProject, updateProject, switchProject.
**Bespoke caching**: none; delegates to apiClient scope header.

### AppRuntimeContext.tsx — 293 lines
**Server-state**: runtimeStatus (RuntimeStatus | null), loading, error, runtimeUnreachable.
**Client-state**: pollingActiveRef, consecutiveFailuresRef, isTestsRoute.
**Eager fetches on mount**:
- `useEffect(() => { void refreshAllRef.current(); }, [])` at line 221 — fires `refreshAll()` immediately, which fans out to `session.refreshProjects()` + parallel `entity.refreshSessions/Documents/Tasks/Alerts/Notifications` + `client.getHealth()` + conditionally `entity.refreshFeatures()`.
- Health poll: `setInterval(refreshAll, 30_000)` at line 225.
- Feature poll: `setInterval(refreshFeatures, 5_000)` at line 249 — fallback when live updates unavailable and `featureSurfaceV2Active` is false.
**Hooks exposed**: `useAppRuntime()` — loading, error, runtimeStatus, refreshAll, featureSurfaceV2Active, runtimeUnreachable, retryRuntime.
**Bespoke caching**: `refreshAllInFlightRef` (single-flight dedup). `featureSurfaceV2Active` flag (from `runtimeStatus.featureSurfaceV2Enabled`) suppresses the global 5 s feature poll and live subscription when ProjectBoard v2 surface is active.

### DataContext.tsx — 155 lines (facade) + dataContextShared.ts — 106 lines (shared types/utils)
**Role**: Pure composition facade; no state of its own. `useData()` assembles a flat `DataContextValue` from `useAppSession()`, `useAppEntityData()`, and `useAppRuntime()`.
**Provider tree** (`DataProvider`):
```
DataClientProvider
  AuthSessionProvider
    AppDataProviderGate (mounts inner providers only after auth resolves)
      AppSessionProvider
        AppEntityDataProvider
          AppRuntimeProvider
```
`dataContextShared.ts` holds `SessionFilters`, `SessionFetchOptions`, `PaginatedResponse`, `mergeSessionDetail` (applies `MAX_SESSION_LOG_ROWS=5000` ring-buffer cap), `aggregateFeatureFromPhases`, `matchesPhase`.

### DataClientContext.tsx — 21 lines
**Role**: Wraps `createApiClient()` in a context singleton (created once via `useMemo`). No state; no fetches. Exposes `useDataClient()`.

### ThemeContext.tsx — 85 lines
**Pure client-state**: theme preference and resolved theme (localStorage + system media query). No server fetches. Exposes `useTheme()`.

### ModelColorsContext.tsx — 230 lines
**Mixed**: Loads `modelFacets` from `/api/analytics/model-facets` on mount (one eager fetch). Color overrides stored in localStorage per project. Subscribes to `useData().sessions` for derived color registry. Exposes `useModelColors()`.

---

## 2. Provider Tree (App.tsx)

```
ThemeProvider                         <- pure client, no fetches
  HashRouter
    Route "/*" ->
      DataProvider                    <- starts eager fetch waterfall on mount
        Layout
          ModelColorsProvider         <- one eager fetch: /api/analytics/model-facets
            <screen routes>
```

**Eager-fetch sequence on `DataProvider` mount** (AppRuntimeProvider.useEffect line 221):
1. `session.refreshProjects()` -> GET /api/projects + GET /api/projects/active (sequential)
2. In parallel: `entity.refreshSessions()` (GET /api/sessions?offset=0&limit=50), `entity.refreshDocuments()` (GET /api/documents?offset=0&limit=500), `entity.refreshTasks()` (GET /api/tasks?offset=0&limit=5000), `entity.refreshAlerts()` (GET /api/analytics/alerts), `entity.refreshNotifications()` (GET /api/analytics/notifications), `client.getHealth()` (GET /api/health), and conditionally `entity.refreshFeatures()` (GET /api/features?offset=0&limit=5000).

**7-8 parallel requests** immediately on any authenticated page load.

**Duplicate session fetch**: AppEntityDataContext fires `refreshSessions(true)` on its own mount (line 111), before AppRuntimeContext's `refreshAll` does the same. Sessions are fetched **twice** on cold load.

---

## 3. Consumer Graph

| Screen | File | Domains consumed |
|--------|------|-----------------|
| Dashboard | components/Dashboard.tsx:150 | sessions, tasks, loading |
| ProjectBoard | components/ProjectBoard.tsx:1072, 3134 | features (v2 surface), activeProject, documents, mutations |
| SessionInspector | components/SessionInspector.tsx:3952, 4578, 5376 | sessions, sessionFilters, setSessionFilters, loadMoreSessions, hasMoreSessions, getSessionById, features, activeProject, runtimeStatus, loading |
| PlanCatalog | components/PlanCatalog.tsx:278 | documents, features |
| Analytics | components/Analytics/AnalyticsDashboard.tsx:109 | activeProject only (fetches own analytics data) |
| Workflows | components/Workflows/WorkflowRegistryPage.tsx:45 | activeProject only |
| CodebaseExplorer | components/CodebaseExplorer.tsx:76 | activeProject only |
| Planning (multiple) | PlanningHomePage.tsx:931, PlanningAgentSessionBoard:1164, PlanningAgentRosterPanel:445, PlanningFeatureAgentLane:623 | activeProject, sessions, features, getSessionById |
| Planning (documents) | TrackerIntakePanel:684, ArtifactDrillDownPage:171, PlanningGraphPanel:1476, PlanningNodeDetail:1561 | documents, activeProject |
| OpsPanel | components/OpsPanel.tsx:268 | ALL domains: projects, activeProject, sessions, sessionTotal, documents, tasks, features, refreshAll |
| Settings | components/Settings.tsx:955, 1206, 1946, 2876 | projects, activeProject, updateProject, alerts, refreshAll |
| FeatureExecutionWorkbench | components/FeatureExecutionWorkbench.tsx:601 | activeProject, documents, getSessionById, runtimeStatus |
| TestingPage | components/TestVisualizer/TestingPage.tsx:69 | activeProject only |
| Layout | components/Layout.tsx:288 | notifications, error |
| ProjectSelector | components/ProjectSelector.tsx:10 | projects, activeProject, switchProject |
| DocumentModal | components/DocumentModal.tsx:282 | sessions, features, refreshDocuments |

**Domain usage summary**:
- `sessions`: Dashboard, SessionInspector, Planning (board/roster/lane/topbar), OpsPanel, DocumentModal
- `documents`: PlanCatalog, Planning (4 components), OpsPanel, FeatureExecutionWorkbench, DocumentModal
- `tasks`: Dashboard, OpsPanel
- `features`: PlanCatalog, ProjectBoard, SessionInspector, Planning (home/roster), OpsPanel, DocumentModal
- `alerts/notifications`: Settings, Layout
- `activeProject`: nearly every screen (12 of 15 screens)

---

## 4. Fetch Surface (services/apiClient.ts — 525 lines)

All calls prefixed `/api/` via Vite proxy. `ApiClient` interface lines 94-121:

| Method | Endpoint | Notes |
|--------|----------|-------|
| `getHealth()` | GET /health | polled every 30 s |
| `getSessions(filters, opts)` | GET /sessions?offset&limit&sort_by=started_at&sort_order=desc | page size 50 |
| `getSession(id)` | GET /sessions/:id | detail with transcript |
| `getDocuments(offset, limit)` | GET /documents?offset&limit&include_progress=true | page size 500 |
| `getTasks()` | GET /tasks?offset=0&limit=5000 | UNBOUNDED |
| `getAlerts()` | GET /analytics/alerts | polled every 30 s |
| `getNotifications()` | GET /analytics/notifications | polled every 30 s |
| `getFeatures()` | GET /features?offset=0&limit=5000 | UNBOUNDED; polled 5 s fallback |
| `getProjects()` | GET /projects | |
| `getActiveProject()` | GET /projects/active | |
| `fetchSnapshotDiagnostics(projectId?)` | GET /agent/artifact-intelligence/snapshot-diagnostics | |
| `updateFeatureStatus` | PATCH /features/:id/status | |
| `updatePhaseStatus` | PATCH /features/:id/phases/:phaseId/status | |
| `updateTaskStatus` | PATCH /features/:id/phases/:phaseId/tasks/:taskId/status | |
| `addProject` | POST /projects | |
| `updateProject` | PUT /projects/:id | |
| `switchProject` | POST /projects/active/:id | |
| `getTelemetryExportStatus` | GET /telemetry/export/status | |
| `updateTelemetryExportSettings` | PATCH /telemetry/export/settings | |
| `triggerTelemetryPushNow` | POST /telemetry/export/push-now | |

**N-request waterfalls**:
- Cold load: 7-8 parallel (see §2). Plus a duplicate session fetch.
- SessionInspector open: `getSessions` (list) + `getSession(id)` (detail) — 2 hops.
- Documents (PlanCatalog): sequential `getDocuments` loop until MAX_DOCUMENTS_IN_MEMORY.
- ProjectBoard v2: `listFeatureCards` -> `getFeatureRollups` — 2-hop waterfall per page.

---

## 5. Existing Bespoke Caches

### services/planning.ts — 1483 lines
Module-level singleton Map-of-Maps LRU: `PLANNING_BROWSER_CACHE` (8 projects x 3 freshness keys x 3 payload types), `PLANNING_FEATURE_CONTEXT_CACHE` (24 entries), `PLANNING_SESSION_BOARD_CACHE` (16 entries). All implement stale-while-revalidate via an `inFlight?: Promise<T>` stored on the cache entry — concurrent reads hit the same in-flight promise. LRU via insertion-order Map + delete/re-insert promotion. Invalidation subscribes to `featureCacheBus` at module init; evicts on project-scoped feature write events. No TTL — freshness-token-based.

### services/featureSurfaceCache.ts — 455 lines
Two-tier bounded LRU+SWR adapter implementing `FeatureSurfaceCacheAdapter`:
- Tier 1 (list pages): `LRUMap<CacheEntry>` max 50, keyed `projectId|query|page`. No TTL.
- Tier 2 (rollups): `LRUMap<RollupCacheEntry>` max 100, TTL 30 s (`FEATURE_SURFACE_CACHE_LIMITS.rollupTtlMs`). `isStale()` triggers background SWR.
Invalidation: subscribes to `featureCacheBus`; exports `invalidateFeatureSurface({ projectId, featureIds?, scope? })` for external call sites.

### services/featureCacheBus.ts — 88 lines
Synchronous pub/sub bus (`Set<FeatureWriteSubscriber>`). `publishFeatureWriteEvent(event)` fans out synchronously; subscriber errors are caught and logged. Both `planning.ts` and `featureSurfaceCache.ts` register at module init. Mutation call-sites call `publishFeatureWriteEvent` after successful writes to drive coordinated invalidation of both caches simultaneously.

### services/useFeatureSurface.ts — 512 lines
React hook owning the list->rollup two-step fetch for ProjectBoard v2. `query` state -> `listFeatureCards` -> card IDs -> `getFeatureRollups`. Injected `FeatureSurfaceCacheAdapter` (defaults to `defaultFeatureSurfaceCache`). Exposes `invalidate(scope: 'list'|'rollups'|'all')` and `cacheKey` for live-topic wiring. `useLiveInvalidation` in ProjectBoard calls `invalidate('all')` on feature write events.

**TQ replacement scope**: All four are hand-rolled TQ equivalents — in-flight dedup (inFlight Promise refs), LRU eviction (TQ's built-in cache), SWR (staleTime/refetchOnMount), scoped invalidation (queryClient.invalidateQueries). featureCacheBus maps to TQ's `queryClient.invalidateQueries` fan-out.

---

## 6. Virtualization & Memory Guards

### Virtualized views
- `components/SessionInspector/TranscriptView.tsx:2448` — `useVirtualizer` on transcript log rows. The only log/transcript list that virtualizes.
- `components/ui/icon-picker.tsx:203` — `useVirtualizer` on icon grid in picker modal.
- `components/SessionInspector.tsx:2` — imports `useVirtualizer` but the session list itself (lines 5856-5901) renders via plain `.map()`. **Session list is NOT virtualized.**

### Non-virtualized large lists (migration risk)
- Session list in SessionInspector (past sessions): `pastSessionThreadRoots.map(renderThreadNode)` and `pastSessions.map(...)`. All loaded sessions (up to N*50 pages) render.
- Document list in PlanCatalog: `documents.map()` on up to 2000 entries.
- Feature list in ProjectBoard (legacy path): `features.map()` on up to 5000 entries. v2 surface is paginated 50/page but not virtualized.

### Memory guard constants
| Constant | Value | File:Line |
|----------|-------|-----------|
| `SESSIONS_PER_PAGE` | 50 | AppEntityDataContext.tsx:48 |
| `MAX_DOCUMENTS_IN_MEMORY` | 2000 | constants.ts:391 |
| `MAX_SESSION_LOG_ROWS` | 5000 | constants.ts:4 |
| `VITE_CCDASH_MEMORY_GUARD_ENABLED` | default `true` | lib/featureFlags.ts:23 |

**Memory guard flag** (`isMemoryGuardEnabled()`): gates document pagination cap (`refreshDocuments`/`loadMoreDocuments` in AppEntityDataContext), session detail TTL GC (`gcSessionDetailRequests`), transcript ring-buffer (`mergeSessionDetail` in dataContextShared.ts:55), and polling teardown on 3 consecutive failures (AppRuntimeContext.tsx:171).

**Transcript ring-buffer**: `mergeSessionDetail` (dataContextShared.ts:46-70) slices fetched logs to `MAX_SESSION_LOG_ROWS=5000` keeping the latest, sets `transcriptTruncated.droppedCount`. Only applied when memory guard enabled.

---

## 7. Key Migration Notes for TanStack Query PRD

1. **Duplicate session fetch on cold load**: AppEntityDataContext.tsx:111 fires `refreshSessions(true)` independently of AppRuntimeContext's `refreshAll` (line 221). TQ with a shared query key naturally dedups.

2. **Unbounded task/feature loads**: `getTasks(limit=5000)` and `getFeatures(limit=5000)` are never paginated at the context layer. TQ migration should introduce server-side pagination for both — significant backend contract change.

3. **Three polling intervals to consolidate**: 30 s health+all-data poll, 5 s feature fallback poll, live EventSource invalidation — all hand-wired in AppRuntimeContext. TQ's `refetchInterval` per query key replaces all three.

4. **Four bespoke cache systems to retire**: planning.ts LRU, featureSurfaceCache.ts two-tier LRU, session-detail in-flight Map (AppEntityDataContext), feature in-flight ref. All map to TQ's built-in cache with appropriate staleTime/gcTime settings.

5. **Optimistic updates**: `updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus` implement manual optimistic rollback with snapshot/restore pattern. TQ's `onMutate`/`onError` standardizes this.

6. **featureCacheBus cross-cache coordination**: `publishFeatureWriteEvent` -> both cache subscribers. With TQ, `queryClient.invalidateQueries({ queryKey: ['features', projectId] })` replaces the bus entirely.

7. **AppDataProviderGate auth guard**: Provider tree mounts only after `AuthSessionProvider` resolves — TQ migration must preserve this gate, likely via `enabled: shouldMountAppDataProviders(auth)` on each query.
