# Frontend Core: Architecture, State Management & Performance Investigation

**Date:** 2026-05-30
**Domain:** frontend-core
**Analyst:** Subagent — Sonnet 4.6
**Context:** Enterprise/container edition readiness; local DB is 10 GB; `types.ts` is ~4000 lines; app is reported slow on large projects.

---

## 1. Executive Summary

The TanStack Query (TQ) migration is substantively complete but partially incomplete in critical places. The `useData()` shim in `DataContext.tsx` is architecturally broken: it reads TQ cache via `queryClient.getQueryData()` (a snapshot read) rather than reactive `useQuery()` subscriptions, meaning components that rely on the facade will silently see stale or empty arrays when TQ background-refetches data. Multiple heavy components (SessionInspector at 6101 lines, ProjectBoard at 3895 lines) remain as monolithic files with no `React.memo` boundary protection. The features query fires every 5 seconds (`refetchInterval: 5_000`) when SSE is disabled, which is the production default for hosted/enterprise deploys — creating a high-frequency polling storm on large projects. Dashboard.tsx retains a manual `setInterval`-based live-agents poll alongside at least two direct `analyticsService.*` fetch calls that bypass TQ entirely. The documents page size of 500 items per page with a cap of 2000 items in memory is very large for enterprise projects. Virtualization exists in SessionInspector and ProjectBoard, but is missing from several list surfaces.

---

## 2. Provider Architecture

### 2.1 Provider Tree

```
QueryClientProvider (App.tsx:90, queryClientRef.useRef(createProjectQueryClient('default')))
  ThemeProvider
    HashRouter
      DataProvider (contexts/DataContext.tsx:82 — composition facade)
        DataClientProvider
          AuthSessionProvider
            AppDataProviderGate
              AppSessionProvider     ← project list + activeProject, refreshes from /projects/active
              AppRuntimeProvider     ← health polling (30 s refetchInterval via useHealthQuery)
```

`DataProvider` is mounted on every authenticated route via `App.tsx:100`. `AppRuntimeProvider` contains `useHealthQuery` which politely polls every 30 s. No broad re-render source was found in the provider tree itself.

**GOOD:** `AppEntityDataContext.tsx` has been fully deleted (T4-005 complete). No domain-data Context holding server arrays remains mounted at the top of the tree.

### 2.2 Critical flaw in `useData()` shim — cache read without subscription

`DataContext.tsx:120-267` (`useData()`) calls `queryClient.getQueryData(...)` for every domain (sessions, documents, tasks, features, alerts, notifications, projects). **`getQueryData` is a one-time snapshot read, not a reactive subscription.** This means:

- When a background TQ refetch completes (e.g. after 30 s staleTime), components consuming `useData().sessions` will NOT re-render with fresh data.
- The only way consumers get fresh data is if the enclosing function component re-renders for an unrelated reason (e.g., the `session` or `runtime` context values change).
- Effectively, `useData()` operates as a cache snapshot, not as a live data binding.

Evidence:
- `DataContext.tsx:132` — `const tqSessionsData = queryClient.getQueryData<InfiniteData<...>>(sessionsKeys.list(projectId))`
- `DataContext.tsx:143` — same pattern for documents
- `DataContext.tsx:151,155,161,164,167` — same for tasks, features, alerts, notifications, projects
- No `useQuery()` or `queryClient.getQueryCache().subscribe()` is present in `useData()`.

This means `OpsPanel.tsx:272` destructuring `sessions, sessionTotal, documents` from `useData()` will see empty arrays until a render cycle coincidental with a cache population event.

### 2.3 `useData()` still consumed by 13+ components

Despite the TQ migration, the `useData()` facade is still consumed as follows:

- `Layout.tsx:294` — `activeProject, error`
- `Dashboard.tsx:152` — `activeProject, tasks, loading`
- `ProjectBoard.tsx:1072, 3145` — `activeProject, updateFeatureStatus, documents`
- `SessionInspector.tsx:3957, 4585, 5393` — `sessionFilters, activeProject, features, loading`
- `OpsPanel.tsx:272` — `projects, activeProject, sessions, sessionTotal, documents, refreshAll`
- `PlanCatalog.tsx:294` — `features, activeProject, documents`
- `DocumentModal.tsx:283` — `sessions, features, refreshDocuments, activeProject`
- `Settings.tsx:1213, 1957, 2890` — `activeProject, updateProject, refreshAll`
- `FeatureExecutionWorkbench.tsx:605` — `activeProject, getSessionById, runtimeStatus`
- `CodebaseExplorer.tsx:76` — `activeProject`
- `ProjectSelector.tsx:11` — `activeProject, switchProject`
- `AddProjectModal.tsx:15` — `addProject`
- `PlanningHomePage.tsx:928` — `activeProject, features`

Most of these are benign (client-state like `activeProject` is sourced from `AppSessionContext` which is reactive), but `sessions`, `documents`, `features`, `tasks`, `alerts`, `notifications` in the shim are cache snapshots.

---

## 3. Polling and Fetch Frequency Analysis

### 3.1 TanStack Query polling intervals

| Query | staleTime | refetchInterval | Notes |
|---|---|---|---|
| `useHealthQuery` | 25 s | 30 s | Controlled, visibility-aware |
| `useSessionsQuery` | 30 s | none | Correct |
| `useSessionDetailQuery` | 30 s | none | Correct |
| `useDocumentsQuery` | 60 s | none | Correct |
| `useTasksQuery` | 30 s | none | Correct |
| `useFeaturesQuery` | 30 s | **5_000 ms** when SSE off | See below |
| `useAlertsQuery` | 30 s | 30 s | Correct |
| `useNotificationsQuery` | 30 s | 30 s | Correct |
| `usePlanningSummaryQuery` | **0** | none | Key-driven; see below |
| `useFeatureSurface (list tier)` | **0** | none | Always stale |
| `useFeatureSurface (rollup tier)` | 30 s | none | Correct |
| `useDashboardBundleQuery` | 10 s | none | Correct |
| `useAnalyticsOverviewQuery` | 30 s | none | Correct |
| `usePlanningViewQuery` | 30 s | none | Correct |

**Critical: `refetchInterval: 5_000` on features (`services/queries/features.ts:85`)**

When `VITE_CCDASH_LIVE_FEATURES_ENABLED=false` (the documented `.env.example` default), features are polled every **5 seconds**. On a project with a large features list, this means parsing the full 100-item features page response every 5 seconds. The local `.env` sets `VITE_CCDASH_LIVE_FEATURES_ENABLED=true`, so this is hidden locally but will fire in enterprise/hosted deploys where SSE is not configured.

**`staleTime: 0` on `useFeatureSurface` list tier (`services/useFeatureSurface.ts:348`)**

The feature surface list tier is always considered stale. This means every mount of `ProjectBoard` or `Dashboard` triggers an immediate background refetch of the feature cards list, regardless of how recently it was fetched. With `DEFAULT_ROLLUP_FIELDS` set, this also cascades to a rollup batch request.

### 3.2 Manual `setInterval` polls (outside TQ)

These bypass TQ's visibility-awareness, retry, and dedup:

| Location | Interval | Endpoint |
|---|---|---|
| `Dashboard.tsx:117` (`useLiveAgentsCount`) | 10 s | `/api/agent/live/active-count` |
| `SystemMetricsChip.tsx:73` | 30 s | system metrics endpoint |
| `ProjectBoard.tsx:1422` | 15 s (`FEATURE_MODAL_POLL_INTERVAL_MS`) | feature health + session refresh |
| `OpsPanel.tsx:885` | 2.5 s or 15 s (adaptive) | `/cache/operations?limit=30` |
| `OpsPanel.tsx:900` | 10 s | telemetry status |
| `SessionInspector.tsx:4646` | (unknown — file:4646) | session live refresh |
| `SessionInspector.tsx:5652` | (unknown — file:5652) | session live refresh |
| `FeatureExecutionWorkbench.tsx:854` | (unknown) | execution state |
| `TestVisualizer/hooks.ts:167,272,359` | (configurable) | test polling |
| `PlanningAgentSessionBoard.tsx:880` | 15 s | `StaleIndicator` tick — benign |

`ProjectBoard.tsx:1422` with a 15 s feature-modal poll fires while the feature modal is open, refreshing session data even when SSE is available. `OpsPanel.tsx:885` at 2.5 s when operations are active is aggressive.

### 3.3 `analyticsService.*` raw fetch calls outside TQ

`Dashboard.tsx:250-253` makes three parallel `analyticsService.*` calls in a `useEffect` that fires on every change to `[sessions.length, tasks.length]`:
- `analyticsService.getSessionCostCalibration()`
- `analyticsService.getSeries({ metric: 'session_cost', period: 'daily', limit: 120 })`
- `analyticsService.getSeries({ metric: 'task_velocity', period: 'daily', limit: 120 })`

These have no TQ caching, dedup, or stale protection. `sessions.length` or `tasks.length` changing (e.g. on background TQ refetch) re-fires all three fetches.

`AnalyticsDashboard.tsx:151-158` fires seven parallel fetches on mount including `analyticsService.getArtifacts({ limit: 200 })` — no TQ, no caching.

---

## 4. Memory Guard and Transcript Ring-Buffer

**Status: Partially implemented.**

- `isMemoryGuardEnabled()` defaults to `true` via `VITE_CCDASH_MEMORY_GUARD_ENABLED` (`lib/featureFlags.ts:22-23`).
- The transcript ring-buffer cap is applied in `dataContextShared.ts:55-65` (`mergeSessionDetail`): if `logs.length > MAX_SESSION_LOG_ROWS (5000)`, the oldest logs are dropped, keeping the last 5000, and `transcriptTruncated.droppedCount` is set.
- `TranscriptView.tsx:2466` shows a truncation notice when `isMemoryGuardEnabled() && transcriptTruncated.droppedCount > 0`.
- `documents` are capped to `MAX_DOCUMENTS_IN_MEMORY = 2000` (constants.ts:391) via `useDocumentsQuery`'s `select` transform (`services/queries/documents.ts:76-77`).

**Gaps:**
- `MAX_SESSION_LOG_ROWS = 5000` is very large; a session with 5000 JSONL log rows held in React state is a significant memory allocation, especially when multiple sessions are loaded simultaneously.
- The document page size is `DOCUMENTS_PAGE_SIZE = 500` items per page (`services/queries/documents.ts:22`), allowing up to 4 pages × 500 = 2000 documents in memory. For enterprise projects with many docs, all 2000 may be loaded eagerly.
- No per-session memory eviction policy: once fetched, session detail objects remain in TQ cache for `gcTime: 300_000` (5 min). With many concurrent session detail fetches this can accumulate significantly.

---

## 5. Virtualization Coverage

**Status: Good on primary lists, absent on several secondary lists.**

| Surface | Virtualized | Evidence |
|---|---|---|
| `SessionInspector` session list | YES (partial — `pastThreadsVirtualizer`, `pastCardsVirtualizer` in detail panel at lines 5749/5758) | `SessionInspector.tsx:2, 5749, 5758` |
| `TranscriptView` message list | YES — `rowVirtualizer` | `TranscriptView.tsx:2448` |
| `ProjectBoard` feature list | YES — `featureListVirtualizer` | `ProjectBoard.tsx:3483` |
| `PlanCatalog` doc list | YES — `docCardVirtualizer`, `docListVirtualizer` | `PlanCatalog.tsx:590, 596` |
| `MultiProjectCommandCenter` | YES — `virtualizer` | `MultiProjectCommandCenter.tsx:97` |
| `MultiProjectSessionBoard` card columns | YES — `CardList` uses `useVirtualizer` (threshold-gated) | `MultiProjectSessionBoard.tsx:337, 41` |
| `Analytics/AnalyticsDashboard` artifact/correlation lists | NO | No import of `@tanstack/react-virtual` found |
| `OpsPanel` operations list | NO | No virtualizer found; capped at limit=30 |
| `PlanCatalog` feature cross-links | NO | Client-side filter/sort with no virtualization |
| `SessionInspector` main session list (before detail) | Partial — only in detail sub-panels, not the initial list render | `SessionInspector.tsx:5749` only in `PastThreadsPanel` |

The primary session list scroll pane in `SessionInspector` before a session is selected uses `useSessionsQuery` with infinite scroll, but the initial list of sessions in the left panel does not appear to use a virtualizer — it relies on TQ pagination (page size 50) + load-more. This is acceptable but may still be slow to paint with many items due to DOM node count.

---

## 6. TanStack Query Migration State

### Completed
- `AppEntityDataContext.tsx` deleted (T4-005, confirmed by architecture test at `contexts/__tests__/dataArchitecture.test.ts:54`).
- All domain hooks migrated: sessions, documents, tasks, features, alerts, notifications, projects, health, planning, dashboard bundle, analytics overview, feature surface.
- `useData()` shim is a facade (T4-007) — no more `createContext()` holding server state arrays.
- `refetchOnWindowFocus: false` set globally (`lib/queryClient.ts:35`).
- Fat-read bundles implemented: `useDashboardBundleQuery` (T5-005), `usePlanningViewQuery` (T5-007), `useAnalyticsOverviewQuery` (T5-007 best-effort).
- QueryClient is `useRef`-stabilized at App level (`App.tsx:87`) — no re-creation on re-render.
- `queryClient.clear()` on project switch (`DataContext.tsx:197`) — correct.

### Partial / Broken
- `useData()` shim uses `getQueryData()` not `useQuery()` — no reactive subscription for 7 domain arrays (`DataContext.tsx:132-167`). Components relying on `useData().sessions`, `useData().tasks`, etc. only update when the enclosing component re-renders for other reasons.
- `Dashboard.tsx` analytics series calls remain outside TQ (3 raw `analyticsService.*` fetches, `Dashboard.tsx:251-253`).
- `AnalyticsDashboard.tsx` still uses 7 parallel raw fetches on mount with no TQ wrapper.
- Several `setInterval` polls remain across 6+ components; these should be migrated to TQ `refetchInterval` or SSE-triggered invalidation.
- `useFeaturesQuery` `refetchInterval: 5_000` when SSE off is unguarded for enterprise — will hammer the backend every 5 s on large projects.

---

## 7. Large Component Files

These monolithic components carry high maintenance and performance risk:

| File | Lines | Notes |
|---|---|---|
| `SessionInspector.tsx` | 6101 | Single export; no `React.memo` on inner panels |
| `TranscriptView.tsx` | 3784 | Good: has virtualizer for message rows |
| `ProjectBoard.tsx` | 3895 | Good: has feature list virtualizer |
| `Planning/PlanningNodeDetail.tsx` | 1936 | No memo observed |
| `Planning/PlanningGraphPanel.tsx` | 1728 | No memo observed |
| `Planning/PlanningAgentSessionBoard.tsx` | 1591 | `SessionCard`, `BoardColumn` are `memo`-wrapped |
| `OpsPanel.tsx` | 2186 | Multiple `setInterval` loops |

`SessionInspector.tsx` at 6101 lines is the largest single component file. It has virtualizers in the detail subpanels but the component's render function is enormous with no `React.memo` boundaries on inner panel components. Any state change anywhere in the component triggers a full re-render of all sub-panels.

---

## 8. Component-Level Memoization

`React.memo` is used sparingly:
- `PlanningAgentSessionBoard.tsx:362, 723` — `SessionCard`, `BoardColumn` — **good**
- `MultiProjectSessionBoard.tsx:92, 128, 328, 419` — `WorkerRow`, `AggregateSessionCardView`, `CardList`, `BoardGroupColumn` — **good**
- `components/ui/icon-picker.tsx:35` — `IconRenderer` — fine

**Missing memo:**
- `Dashboard.tsx` — `StatCard`, `LiveAgentsChip`, `FeatureSummaryChip` are plain functional components with no `React.memo`. Re-renders on every `useData()` hook result change.
- `SessionInspector.tsx` — All inner panel components are declared inside the same module, none wrapped in `React.memo`. `ActivityView`, `FilesView`, `SessionSummaryCard` etc. in `SessionInspectorPanels.tsx` (675 lines, not checked for memo).
- `ProjectBoard.tsx` — Feature cards and phase panels inside the modal are un-memoized. Every 15 s modal poll re-renders the entire modal tree.

---

## 9. Page Load / Cold Start Performance

On cold load of a large project:

1. `AppSessionProvider` mounts → fires `refreshProjects()` → two sequential fetches (`/projects`, `/projects/active`) (`AppSessionContext.tsx:22-44`).
2. `AppRuntimeProvider` mounts → `useHealthQuery` fires immediately.
3. Route component mounts; each page independently mounts its own TQ hooks.
4. `Dashboard` cold load:
   - `useDashboardBundleQuery` (1 req) ✓
   - `useAnalyticsOverviewQuery` (1 req) ✓
   - `useFeatureSurface` list (1 req, `staleTime: 0`) + rollup (1 req) → 2 more reqs
   - `useLiveAgentsCount` manual poll (1 req immediately) ✗
   - `analyticsService.*` (3 reqs via `useEffect`) ✗
   - Total: ~8 requests on Dashboard mount
5. `SessionInspector` cold load: `useSessionsQuery` (1 req) + `useFeaturesQuery` (mounted for cold-load population) + `useDocumentsQuery` (mounted for cold-load population) → 3 requests minimum; `useFeaturesQuery` then polls again every 5 s.
6. `PlanCatalog` cold load: `useDocumentsQuery` + `useFeaturesQuery` + `useData().features` (fallback) + `useData().documents`.

---

## 10. Enterprise / Container-Specific Issues

### 10.1 SSE defaults for enterprise
The `.env.example` has `VITE_CCDASH_LIVE_FEATURES_ENABLED=false` (line 135). For enterprise, without explicit SSE enablement:
- Features poll every 5 s (`refetchInterval: 5_000`)
- Sessions and execution SSE topics are enabled in `.env.example` (lines 132-133), but `isFeatureLiveUpdatesEnabled` defaults false → feature polling fallback
- `isOpsLiveUpdatesEnabled` defaults false → OpsPanel falls back to its own adaptive `setInterval` at 2.5–15 s

### 10.2 Query cache on project switch
`queryClient.clear()` is called on `switchProject` (`DataContext.tsx:197`). This is correct behavior but means every project switch causes all active queries to refetch simultaneously, creating a burst of requests.

### 10.3 No SSR or prefetching
Vite SPA with HashRouter — no SSR, no query prefetching. All data is loaded after first render. Container deploys where the backend may be remote/slow will show loading states on every navigation.

### 10.4 Vite build configuration
`vite.config.ts:84` exposes `GEMINI_API_KEY` via `process.env` define — this bakes the key into the JS bundle at build time. In a containerized enterprise build, this would expose the Gemini key in the static bundle.

---

## 11. Issues Summary Table

| # | Title | Severity | Area | File:Line | Complexity |
|---|---|---|---|---|---|
| 1 | `useData()` shim uses `getQueryData()` not `useQuery()` — no reactive subscription | high | frontend | `DataContext.tsx:132-167` | M |
| 2 | `useFeaturesQuery` polls every 5 s when SSE disabled (enterprise default) | high | perf | `services/queries/features.ts:85` | S |
| 3 | `useFeatureSurface` list tier `staleTime: 0` — refetches on every mount | high | perf | `services/useFeatureSurface.ts:348` | S |
| 4 | Dashboard `analyticsService.*` fetches outside TQ, re-fire on session/task length changes | medium | frontend | `Dashboard.tsx:251-253` | M |
| 5 | `AnalyticsDashboard` fires 7 parallel raw fetches on every mount with no TQ caching | medium | frontend | `AnalyticsDashboard.tsx:151-158` | M |
| 6 | Manual `setInterval` polls in Dashboard (10 s), SystemMetricsChip (30 s), ProjectBoard feature modal (15 s), OpsPanel (2.5–15 s), SessionInspector | medium | perf | Multiple — `Dashboard.tsx:117`, `ProjectBoard.tsx:1422`, `OpsPanel.tsx:885,900` | L |
| 7 | `SessionInspector.tsx` 6101-line monolith with no `React.memo` on inner panels | medium | perf | `SessionInspector.tsx:1` | L |
| 8 | `ProjectBoard.tsx` 3895-line monolith — feature modal re-renders fully every 15 s poll | medium | perf | `ProjectBoard.tsx:1422` | L |
| 9 | Documents fetched in pages of 500 items, up to 2000 in memory — large for enterprise | medium | perf | `services/queries/documents.ts:22`, `constants.ts:391` | S |
| 10 | Session transcript cap `MAX_SESSION_LOG_ROWS = 5000` allows 5000 log rows per session in React state | medium | perf | `constants.ts:4`, `dataContextShared.ts:55` | S |
| 11 | `GEMINI_API_KEY` baked into bundle via Vite `define` | medium | container | `vite.config.ts:84-87` | S |
| 12 | `usePlanningSummaryQuery` `staleTime: 0` means refetch on every Planning mount | low | perf | `services/queries/planning.ts:72` | S |
| 13 | `OpsPanel.tsx` destructures `sessions, documents` from `useData()` — gets stale snapshots, not live subscriptions | medium | frontend | `OpsPanel.tsx:272` | S |
| 14 | `PlanningHomePage` and 12 other components still use `useData()` facade for `features` — stale snapshot risk | medium | frontend | `PlanningHomePage.tsx:928`, others | L |
| 15 | No server-side search for sessions in SessionInspector — all filtering is client-side via URL params passed to TQ keys | low | perf | `SessionInspector.tsx:3957-3958` | M |

---

## 12. What is Complete and Healthy

- TQ v5 (`^5.100.14`) is fully wired: `QueryClientProvider` is at the correct level, `queryClientRef.useRef` prevents re-creation.
- `AppEntityDataContext.tsx` is deleted — no broad re-render source from context holding server arrays.
- `refetchOnWindowFocus: false` globally — no noisy refetches on alt-tab.
- Fat-read bundles are implemented for Dashboard (`T5-005`), Planning view (`T5-007`), Analytics overview (`T5-007 best-effort`).
- Virtualization is present on the heaviest lists: session transcript (TranscriptView), feature board (ProjectBoard), docs (PlanCatalog), multi-project boards (Planning/CommandCenter).
- `mergeSessionDetail` ring-buffer cap is implemented and guarded by `isMemoryGuardEnabled()`.
- `queryClient.clear()` on project switch is correctly placed.
- SSE live invalidation infrastructure (LiveConnectionManager, topics, `useLiveInvalidation`) is fully built with exponential backoff, visibility-aware pause, cursor tracking — production grade.
- Lazy route code-splitting is implemented in `App.tsx` for all pages.
- `SessionsQuery` uses infinite scroll with page size 50 — correct.

---

## 13. Key Recommendations (Priority Order)

1. **Fix `useData()` reactive subscription gap** — Replace `queryClient.getQueryData()` calls in `DataContext.tsx:132-167` with `useQuery()` hooks so that consumers of `useData().sessions`, `.features`, etc. re-render when TQ background-refetches. Alternatively, eliminate `useData()` entirely from the remaining 13 consumers and have them use domain hooks directly.

2. **Fix `useFeaturesQuery` refetchInterval** — Change from `refetchInterval: 5_000` to `refetchInterval: 30_000` when SSE is disabled, or require SSE to be enabled in enterprise deploys. At 5 s on a project with 100+ features, this generates 12 requests/minute.

3. **Set `staleTime` on `useFeatureSurface` list tier** — Change from 0 to at least 10 s to avoid a refetch on every mount. `staleTime: 0` combined with mount-on-each-navigation creates rapid re-requests.

4. **Migrate Dashboard chart fetches to TQ** — Move `analyticsService.getSessionCostCalibration()`, `getSeries(session_cost)`, `getSeries(task_velocity)` into `useQuery` hooks so they benefit from dedup, caching, and are not re-fired on `sessions.length` changes.

5. **Migrate `AnalyticsDashboard` fetches to TQ** — 7 parallel raw fetches with no caching; replace with TQ hooks.

6. **Convert manual `setInterval` polls to TQ `refetchInterval`** — Especially `Dashboard.tsx:useLiveAgentsCount` (10 s), `SystemMetricsChip` (30 s), `OpsPanel` (2.5–15 s adaptive). These bypass TQ's visibility-awareness.

7. **Add `React.memo` to SessionInspector and ProjectBoard inner panels** — Both are monolithic files; wrapping major sub-panels (ActivityView, FilesView, SessionSummaryCard, phase panels) in `memo()` would prevent unnecessary re-renders from ancestor state changes.

8. **Reduce document page size for enterprise** — `DOCUMENTS_PAGE_SIZE = 500` with cap 2000 is excessive for large enterprise projects. Consider 100/page with a lower max (500), or switch to on-demand pagination.

9. **Fix Gemini API key exposure** — `vite.config.ts:84-87` bakes `GEMINI_API_KEY` into the bundle. This key should not be in a browser-served bundle in an enterprise context; it should be proxied server-side.

10. **Add `staleTime` guidance to `usePlanningSummaryQuery`** — The comment says staleTime: 0 is intentional (freshness-token key pattern), but this means every Planning page mount causes a fresh fetch even if freshness token hasn't changed. Consider at least 5 s to debounce rapid navigation.
