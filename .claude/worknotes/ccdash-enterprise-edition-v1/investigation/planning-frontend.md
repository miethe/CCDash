# Planning Frontend Investigation
## CCDash Enterprise Edition v1 — Domain: planning-frontend

**Date**: 2026-05-30  
**Analyst**: Senior architect forensic review  
**Source files read**: PlanningHomePage.tsx, PlanningRouteLayout.tsx, PlanningTopBar.tsx, PlanningSummaryPanel.tsx, PlanningAgentSessionBoard.tsx, PlanningAgentSessionDetailPanel.tsx, CommandCenter/* (all 20 files), FeatureModal/FeatureDetailShell.tsx, services/queries/planning.ts, services/planningRoutes.ts, services/planningCommandCenter.ts

---

## 1. View Inventory — What Each Command-Center View Exists Today

### 1.1 PlanningHomePage (single-project, `/planning`)

**file**: `components/Planning/PlanningHomePage.tsx`

The page mounts a single TQ query at line 954:
```
usePlanningViewQuery({ projectId, enabled, includeGraph: false, includeSessionBoard: false })
```
This fires GET `/api/agent/planning/view?project_id=<id>` — one above-fold request.

The page renders, in vertical stack order, all of the following as a single layout:

| Section | Component | Data source |
|---|---|---|
| Hero header | inline `HeroHeader` | summary (derived) |
| Metrics strip | `PlanningMetricsStrip` | summary |
| Artifact chip row | `PlanningArtifactChipRow` | summary.nodeCountsByType |
| **Command Center Shell** | `PlanningCommandCenterShell` | separate fetch: GET `/api/agent/planning/command-center` |
| Triage + Roster grid | `PlanningTriagePanel` + `PlanningAgentRosterPanel` | summary |
| Summary panel | `PlanningSummaryPanel` | summary |
| Active / Planned columns | `ActivePlansColumn` + `PlannedFeaturesColumn` | summary.featureSummaries (client-filtered) |
| Graph panel | `PlanningGraphPanel` | separate TQ query |
| Tracker intake | `TrackerIntakePanel` | summary |
| **Agent Session Board** | `PlanningAgentSessionBoard` | separate fetch: GET `/api/agent/planning/session-board` |

**Cold-load network requests**: minimum 3 separate requests (view-bundle, command-center, session-board) each with their own round-trip latency. With the 10 GB SQLite cache, these can be extremely slow.

### 1.2 PlanningCommandCenterShell / PlanningCommandCenter (V1, single-project)

**file**: `components/Planning/CommandCenter/PlanningCommandCenter.tsx:94`

The V1 component uses a **raw `useEffect` + manual fetch** pattern (NOT TanStack Query), lines 133–161. This is architecturally divergent from the rest of the planning surface which uses TQ hooks.

- Fires GET `/api/agent/planning/command-center?project_id=...&page_size=50` on mount.
- Has both a `load` callback (line 108) and a duplicate `useEffect` (line 133) that both call `getPlanningCommandCenter`. The `load` callback is only called via `onRefresh` toolbar button. The effect fires the same request on mount. There is no deduplication — on mount, both paths can race if the component re-renders during the effect cleanup window.
- Three view modes: `list` (default), `cards`, `board` (5-column kanban).
- **No pagination in UI**: `pageSize: 50` is hardcoded (line 119, 143). No UI for page > 1.
- **No TQ cache**: data lives in local React state (`loadState`), discarded on unmount. No background refresh, no stale-while-revalidate, no cross-tab dedup.

### 1.3 MultiProjectCommandCenter (MPCC, flagged off by default)

**file**: `components/Planning/CommandCenter/MultiProjectCommandCenter.tsx`

Feature flag: `MULTI_PROJECT_COMMAND_CENTER_ENABLED` (default `false`, env `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED`).

When mode = `'multi'` this replaces the V1 component. Uses TQ hooks:
- `useMultiProjectCommandCenterQuery` — GET `/api/agent/planning/multi/command-center` (or similar)
- `useMultiProjectSessionBoardQuery` — GET `/api/agent/planning/multi/session-board`

Both hooks guard on `MULTI_PROJECT_COMMAND_CENTER_ENABLED` in the query's `enabled` field (`services/queries/planning.ts:340,388`).

However, `MultiProjectCommandCenter` passes `projectListReady: true` and `enabled: true` unconditionally (lines 237–238, 251–252 in MultiProjectCommandCenter.tsx), meaning once the mode toggle is on, both queries fire immediately without waiting for any project-list readiness signal. For enterprise environments with many projects, this can produce N×M fanout at the backend before the user has filtered.

**Work-item virtualization**: threshold is 250 items (`WORK_ITEM_VIRTUALIZE_THRESHOLD = 250`). Below that, all items render eagerly. On a large portfolio with 50+ active features, this renders fully without virtualization. For a 10 GB database that could mean 50+ fully-expanded command center items on initial load.

### 1.4 MultiProjectSessionBoard (MPCC, flagged)

**file**: `components/Planning/CommandCenter/MultiProjectSessionBoard.tsx`

Renders a Kanban-style board of cross-project agent sessions grouped by state/project/feature/phase/agent/model.

- Per-column card virtualization threshold: 250 cards/column (`VIRTUALIZE_THRESHOLD = 250`, line 41).
- Below threshold, plain rendering (no windowing).
- The `useVirtualizer` hook is called unconditionally but `enabled: shouldVirtualize` gates whether it actively measures (line 102). This is correct per tanstack-virtual API.

### 1.5 PlanningAgentSessionBoard (V1, always-mounted on planning home)

**file**: `components/Planning/PlanningAgentSessionBoard.tsx`

- Mounted **always** as part of `PlanningShell`, even on the planning home page (line 919 PlanningHomePage.tsx).
- Uses TQ: `usePlanningSessionBoardQuery` — GET `/api/agent/planning/session-board`.
- Each `BoardColumn` renders all cards inside a fixed-height `div` with `maxHeight: 520` (line 819) and `overflow-y: auto`. No virtualization applied at this layer.
- `StaleIndicator` runs a 15-second `setInterval` (line 880) to update the "stale" badge. This is a perpetual timer on every planning home page load.
- The board builds a `cardBySessionId` Map (line 1271) and recalculates `highlightedSessionIds`, `weakHighlightedSessionIds`, `relationBadgeMap` as `useMemo` derived from `activeSessionId` (line 1283). These are O(N) traversals on every hover/select. With hundreds of sessions (e.g., Skillmeat project), hover latency will be noticeable.

### 1.6 PlanningSummaryPanel (attention columns)

**file**: `components/Planning/PlanningSummaryPanel.tsx`

- `ROW_LIMIT = 8` hardcoded (line 40). Items beyond 8 show "+N more" with no click-through.
- No virtualization.
- Attention column data (stale, blocked, mismatched) is derived from IDs in `summary.staleFeatureIds`, `summary.blockedFeatureIds`, `summary.reversalFeatureIds`, resolved via a `Map<featureId, FeatureSummaryItem>`. O(N) per render.

### 1.7 FeatureDetailShell / FeatureModal

**file**: `components/FeatureModal/FeatureDetailShell.tsx`

- Full modal (`h-[88vh]`, `max-w-6xl`): opens via planning-route URL param `?modal=feature&feature=<id>`.
- Modal-first navigation is enforced: all feature drill-downs on `/planning` stay on the planning route and open the modal via `setPlanningRouteFeatureModalSearch` (`services/planningRoutes.ts:63`).
- On-hover prefetch: `PlanningFeatureRow` calls `prefetchFeaturePlanningContext` on `mouseEnter`/`onFocus` (PlanningHomePage.tsx line 396, PlanningSummaryPanel.tsx line 67). `prefetchFeaturePlanningContext` (`services/planning.ts:848`) calls `getFeaturePlanningContext` and discards errors — this is a fire-and-forget that bypasses TQ's cache. It does NOT populate the TQ cache, so the TQ hook inside `FeatureQuickViewContent` will still issue a network request on panel open.

---

## 2. Default Page Payload Heaviness

On cold load of `/planning`:

| Request | Endpoint | Expected payload size concern |
|---|---|---|
| 1 | GET `/api/agent/planning/view?project_id=<id>` | ProjectPlanningSummary includes ALL featureSummaries + nodeCountsByType. With 100+ features and a 10 GB DB, this is the primary latency bottleneck. |
| 2 | GET `/api/agent/planning/command-center?page_size=50` | Each PlanningCommandCenterItem includes artifacts, phaseRows, worktree, gitState, relatedFiles, launchBatch — dense per-item payload. 50 items × ~5KB each = ~250KB response. |
| 3 | GET `/api/agent/planning/session-board?grouping=state` | All sessions for the project, grouped. With thousands of sessions in a 10 GB DB, this could be extremely large. |

**Key problem**: Requests 2 and 3 fire immediately on mount without user interaction. The planning home page has no "load on demand" gate for the command center or session board — they are always-mounted children of `PlanningShell` (PlanningHomePage.tsx lines 842–919).

The `PlanningRouteLayout` also fires two additional background queries on layout mount (`useSessionsQuery` + `useFeaturesQuery`, lines 146–147) — these warm the cache but add to initial load concurrency.

Total above-fold concurrent requests: **5** (view, command-center, session-board, sessions, features).

---

## 3. Modal-First vs Page Drill-Down Model

**Status: DONE (routing layer is correct, with a gap in quick-view prefetch)**

The routing model is modal-first for planning:
- `planningRouteFeatureModalHref` (`services/planningRoutes.ts:41`) generates `/planning?feature=<id>&modal=feature&tab=<tab>`.
- `PlanningHomePage` resolves modal state from `useSearchParams` (line 933) and renders `ProjectBoardFeatureModal` as an overlay (line 1089).
- All feature rows in `ActivePlansColumn`, `PlannedFeaturesColumn`, `PlanningSummaryPanel` open the modal rather than navigating away.
- Prefetch on hover is wired (PlanningHomePage.tsx line 984) but bypasses TQ cache (see §1.7 gap).

**Gap**: `prefetchFeaturePlanningContext` (`services/planning.ts:848`) is a bare async call that does NOT use `queryClient.prefetchQuery`. This means:
1. The data fetched on hover is discarded.
2. When the modal opens, `usePlanningFeatureContextQuery` (inside `FeatureQuickViewContent`) fires a fresh request.
3. The prefetch provides zero cache benefit.

---

## 4. Virtualization and Lazy-Loading Presence

| Surface | Virtualization | Lazy load |
|---|---|---|
| PlanningAgentSessionBoard columns | None — `maxHeight: 520` + CSS scroll only | No — board always mounts |
| MultiProjectSessionBoard columns | TanStack Virtual > 250 cards/col | No — board always mounts |
| MultiProjectCommandCenter work items | TanStack Virtual > 250 items | No |
| CommandCenterListView | None | No |
| CommandCenterBoardView | None (5 kanban columns, no window) | No |
| PlanningSummaryPanel attention columns | None (ROW_LIMIT=8 truncation only) | No |
| ActivePlansColumn / PlannedFeaturesColumn | None | No |
| FeatureDetailShell tabs | None | Tab content hidden via `hidden` attr |

**Critical**: The V1 session board (`PlanningAgentSessionBoard`) has no virtualization at all. A project with 200 sessions grouped by `state` would render every card into the DOM — each card has 7–8 DOM rows with inline styles, `useEffect`, `useCallback`, `useState`, and a `memo` wrapper. At 200+ sessions, first-render jank is guaranteed.

---

## 5. Per-Card Data Fan-Out

### PlanningAgentSessionCard (V1 board)

Each card contains: `sessionId`, `agentName`, `model`, `state`, `startedAt`, `lastActivityAt`, `durationSeconds`, `tokenSummary` (4 fields + contextWindowPct), `activityMarkers[]`, `relationships[]`, `correlation` (featureId, featureName, phaseNumber, phaseTitle, taskId, taskTitle, batchId, confidence, evidence[]), `transcriptHref`.

This is a **rich per-card object**. For a project with 500 sessions, the session-board payload includes 500 × (all fields above). No pagination. No cursor.

### CommandCenter Item (V1 command center)

Each `PlanningCommandCenterItem` contains: `feature` (id, name, slug, summary), `status` (raw, effective, mismatch, signal), `phase` (current, next, total, name), `storyPoints`, `command` (command string, phase, targetArtifactPath, alternatives[]), `worktree` (branch, batchId, contextId, state), `gitState` (head, status), `artifacts[]`, `relatedFiles[]`, `phaseRows[]`, `blockers[]`, `launchBatch`, `capabilities`, `pullRequest`, `targetArtifact`.

Hardcoded `pageSize: 50`. No server-driven pagination beyond page/hasMore.

---

## 6. Current State vs Desired Command Center

### What Already Exists (DONE)

| Desired capability | Status | Evidence |
|---|---|---|
| Active plans per project, phase/status view | DONE | `ActivePlansColumn`, `CommandCenterListView` with phase column |
| Completed features view | DONE | `bucketCommandCenterItem` returns 'done' for complete/merged; `PlannedFeaturesColumn` shows draft/approved |
| Blocked features view | DONE | `PlanningSummaryPanel` AttentionColumn "Blocked Features"; command center `blockers[]` field |
| Next available work | DONE | `commandCenterLaunchReadiness` derives 'ready'/'blocked'/'needs context'; QuickCommandBar shows launch button |
| Live session status | DONE | `PlanningAgentSessionBoard` + `PlanningTopBar` live-agent pill |
| Linked sessions per feature | DONE | Session board groups by feature; card `correlation.featureId` links back |
| Linked artifacts per feature | DONE | `CommandCenterFeatureRow` shows `artifacts[]`; `PhasePlanTable` shows phaseFiles |
| Feature drill-down (modal-first) | DONE | `planningRouteFeatureModalHref`; `FeatureDetailShell` with 7 tabs |
| Phase operations panel | DONE | `CardActionRow` deep-link to `?panel=phase-ops`; `PlanningAgentSessionDetailPanel` Phase Ops link |
| Prepare Next Run | DONE | `PlanningNextRunPreview` mounted in session board |
| Status bucket + signal filters | DONE | `usePlanningFilter`, `featureMatchesBucket`, `featureMatchesSignal` |
| Multi-project portfolio view | PARTIAL | `MultiProjectCommandCenter` exists but gated behind `MULTI_PROJECT_COMMAND_CENTER_ENABLED=false`; no production backend endpoints verified |
| Token telemetry per session | DONE | `tokenSummary` on cards, context window bar |

### What Is Missing or Broken

| Desired capability | Status | Gap |
|---|---|---|
| Hover-prefetch populating TQ cache | BROKEN | `prefetchFeaturePlanningContext` bypasses TQ; no cache benefit |
| Session board virtualization (V1) | MISSING | No `useVirtualizer` in `PlanningAgentSessionBoard`; renders all cards |
| Pagination in V1 command center | MISSING | `pageSize: 50` hardcoded; no UI for page > 1; can miss features |
| TQ cache for V1 command center | MISSING | `PlanningCommandCenter` uses raw `useEffect` + local state, not TQ |
| Lazy-mount of board/command-center | MISSING | Both always mount on planning home regardless of viewport position |
| Global Cmd-K search | STUB | `handleSearch` in PlanningTopBar (line 116) pushes toast "coming in v2" |
| New Spec creation | STUB | `handleNewSpec` (line 131) pushes toast "coming in v2" |
| Multi-project: real project-list readiness gate | MISSING | `projectListReady: true` hardcoded; fires before project list resolves |
| Multi-project: cross-project session linking | PARTIAL | Detail rail opens but cross-project feature modal is not wired (MPCC-505 comment) |
| Completed features column with history | PARTIAL | Only 'done' bucket in CC; no time-ordered history/recently-completed view |
| Historical sparkline data | STUB | `deriveCorpusStats` synthesizes fake 12-point series (line 138–142); TODO comment at line 135 |
| Token-saved % | STUB | `tokensSavedPct` heuristic computation only (line 127); TODO at line 130 |
| ctxPerPhase telemetry | STUB | TODO(T2-001) at line 107 |

---

## 7. Performance Risks (Perf-at-Scale)

### CRITICAL: No session-board pagination — O(N) payload

**file**: `services/planning.ts:922`, `services/queries/planning.ts:126`

GET `/api/agent/planning/session-board` fetches all sessions for a project with no cursor or page param. For "skillmeat" with a 10 GB DB, this endpoint could return thousands of session cards. The frontend receives the entire payload and builds a flat card Map (line 1271). At enterprise scale (10+ projects × 1000+ sessions), this is unusable.

### HIGH: V1 PlanningCommandCenter not using TanStack Query

**file**: `components/Planning/CommandCenter/PlanningCommandCenter.tsx:100–161`

Uses `useState` + `useEffect` for data fetching. No deduplification, no background refresh, no cache sharing, no stale-while-revalidate. Every re-mount of the planning home page re-fires the request. On a slow 10 GB backend, this adds ~1–5s to perceived render time on every navigation.

### HIGH: Always-on parallel fetching from PlanningHomePage

**file**: `components/Planning/PlanningHomePage.tsx:918–921`

`PlanningAgentSessionBoard` is mounted unconditionally inside `PlanningShell`. This means even when the user only wants to check the active plans list, the session board query fires. Similarly `PlanningCommandCenterShell` is always mounted (line 842). These should be lazy-mounted (e.g., via Intersection Observer or accordion expansion).

### HIGH: PlanningRouteLayout fires sessions+features pre-queries on every planning route

**file**: `components/Planning/PlanningRouteLayout.tsx:146–147`

`useSessionsQuery` and `useFeaturesQuery` fire on every `/planning/*` route (including nested artifact drill-down pages) regardless of whether the child route needs them. With a 10 GB DB, the sessions query payload can be multi-megabyte. TQ's `staleTime` default for these hooks was not checked here but would need to be long (300+ seconds) to avoid re-fetching on tab re-focus.

### MEDIUM: Session-board highlight recalculation on every hover

**file**: `components/Planning/PlanningAgentSessionBoard.tsx:1283–1323`

`useMemo` recalculates `highlightedSessionIds`, `weakHighlightedSessionIds`, `highlightedFeatureIds`, `highlightedPhaseKeys` on every change to `activeSessionId` (which changes on every card hover). For 200 sessions, the `cardBySessionId` Map lookup is O(1) but the iteration over `activeCard.relationships` still triggers a new Set construction, which causes all 200 `SessionCard` memo wrappers to re-evaluate their `isHighlighted` prop. Since `Set.has()` result is a boolean primitive, React's `memo` should short-circuit at the `===` check — but only if the Set reference is stable. Here it is newly constructed on every hover, so all 200 cards re-render on hover.

**Fix**: Use stable identity for the Sets (e.g., compare by serializing the active session ID, and only rebuild when the active session changes between different sessions — which is already guarded, but the Set creation still happens).

### MEDIUM: V1 CommandCenterBoardView — no virtualization, 5 columns × N items each

**file**: `components/Planning/CommandCenter/CommandCenterBoardView.tsx:30–44`

All items are partitioned into 5 buckets and rendered without windowing. 50-item page with 30 items in 'active' = 30 `CommandCenterFeatureCard` components, each with Tooltip wrappers, 4 `ArtifactChip`s, and several `useState`/`useCallback` hooks. The card is `min-h-[270px]`. No lazy-mount, no virtualization.

### MEDIUM: 15-second `setInterval` in StaleIndicator — memory leak risk

**file**: `components/Planning/PlanningAgentSessionBoard.tsx:879–884`

```js
const id = setInterval(() => setTick((t) => t + 1), 15_000);
```
This triggers a `setTick` state update every 15 seconds on every mounted `StaleIndicator`. While `StaleIndicator` returns `null` before the stale TTL (60s), the interval is running from mount. In enterprise mode with multiple planning views open (e.g., via browser tabs or a dashboard mode), each tab has its own interval. The cleanup is correct (line 881), but the component should check stale-ness before starting the interval.

### LOW: Planning fonts loaded via Google Fonts CDN

**file**: `components/Planning/PlanningRouteLayout.tsx:31–48`

Three Google Fonts preconnect/stylesheet links are injected on every planning route mount. In enterprise/container deployments with restricted network egress, these will hang or fail silently, delaying first contentful paint. No offline fallback font stack is specified.

---

## 8. Enterprise/Container Readiness Gaps

### 8.1 Multi-project feature gated and not battle-tested

`MULTI_PROJECT_COMMAND_CENTER_ENABLED=false` by default. The backend endpoints it relies on (`/api/agent/planning/multi/command-center`, `/api/agent/planning/multi/session-board`) — not verified as stable in the backend investigation, but the frontend query hooks exist and the API contracts are typed in `types.ts`. The feature exists architecturally but has never run in production.

### 8.2 No cross-project project-list readiness signal

`MultiProjectCommandCenter` passes `projectListReady: true` unconditionally (lines 237, 251). In enterprise, the project list is loaded asynchronously from `projects.json` (814 lines). There is no hook that signals "project list has fully resolved"; the component assumes it always has. This can cause multi-project queries to fire with an empty or partial project scope, returning wrong data.

### 8.3 `MULTI_PROJECT_COMMAND_CENTER_ENABLED` is a build-time constant

**file**: `constants.ts:418–421`

```ts
export const MULTI_PROJECT_COMMAND_CENTER_ENABLED: boolean = readBoolEnv(
  MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT,
  (import.meta as any).env?.VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED,
  ...
);
```
This is resolved at Vite build time via `import.meta.env`. Changing it in a container requires a rebuild, not a restart. For enterprise deployments this is a high-friction configuration surface. It should either be runtime-configurable via the capabilities endpoint (already partially exists: `getLaunchCapabilities()` at PlanningHomePage.tsx line 946) or always-on with the mode toggle providing the user-facing gate.

### 8.4 Global Cmd-K search is stubbed

**file**: `components/Planning/PlanningTopBar.tsx:116`

```ts
pushToast('Search coming in v2 — press ⌘K to trigger when integrated.');
```
For enterprise users navigating 100+ features across 10+ projects, the lack of cross-project search is a major UX gap. The keyboard shortcut is registered (line 120–128) but opens a toast. This is a placeholder.

### 8.5 No "New Spec" action

**file**: `components/Planning/PlanningTopBar.tsx:131`

```ts
pushToast('New spec — coming in v2.');
```
The primary creation action in the planning toolbar is stubbed. For a command center this is a critical missing piece.

---

## 9. Data Architecture Summary

```
Cold load /planning:
  1. GET /api/agent/planning/view          → ProjectPlanningSummary (all features, N can be large)
  2. GET /api/agent/planning/command-center → PlanningCommandCenterPage (pageSize=50, not TQ-cached)
  3. GET /api/agent/planning/session-board  → PlanningAgentSessionBoard (all sessions, NO pagination)
  4. GET /api/sessions (from PlanningRouteLayout)
  5. GET /api/features (from PlanningRouteLayout)

On feature row hover:
  6. GET /api/agent/planning/features/<id>  → bypasses TQ (fire-and-forget, data discarded)

On feature modal open:
  7. GET /api/agent/planning/features/<id>  → TQ fetch (cache miss due to step 6 bypass)

On session card select (detail panel):
  No new network request — data already in board payload.

On "Prepare Next Run":
  8. GET /api/agent/planning/next-run-preview/<featureId>
```

**TQ staleTime summary for planning hooks**:
- `usePlanningViewQuery`: 30s staleTime, 300s gcTime
- `usePlanningFeatureContextQuery`: 30s, 300s
- `usePlanningSessionBoardQuery`: 30s, 300s
- `usePlanningSummaryQuery` (legacy): staleTime: 0 (freshnessToken-driven)
- V1 `PlanningCommandCenter`: no TQ, no cache

---

## 10. Issue Register

### CRIT-01: Session board has no server-side pagination — full project payload on every load

**Severity**: critical  
**Area**: perf  
**Evidence**: `services/planning.ts:922`; `usePlanningSessionBoardQuery` (no page param). With a 10 GB SQLite DB, this query could return megabytes of session data on every mount.

### CRIT-02: V1 PlanningCommandCenter bypasses TanStack Query

**Severity**: critical  
**Area**: caching  
**Evidence**: `PlanningCommandCenter.tsx:100–161`. Raw `useEffect` + local `useState`. No dedup, no cache, no background refresh. Every navigation to `/planning` re-fetches the command center cold.

### HIGH-01: Always-on parallel mount of session board + command center

**Severity**: high  
**Area**: perf  
**Evidence**: `PlanningHomePage.tsx:842,919`. Both components mount regardless of viewport position and fire network requests on every planning home load.

### HIGH-02: Hover-prefetch bypasses TQ cache — zero benefit

**Severity**: high  
**Area**: caching  
**Evidence**: `services/planning.ts:848`; `PlanningHomePage.tsx:984`. `prefetchFeaturePlanningContext` calls `getFeaturePlanningContext` directly without `queryClient.prefetchQuery`. Data fetched on hover is discarded; TQ issues a second request on modal open.

### HIGH-03: V1 session board has no virtualization — all cards rendered eagerly

**Severity**: high  
**Area**: perf  
**Evidence**: `PlanningAgentSessionBoard.tsx:1549`; `BoardColumn` renders all visible cards in a fixed-height CSS scroll container with `maxHeight: 520`. No TanStack Virtual integration. Rich cards with 8+ DOM nodes each.

### HIGH-04: Multi-project mode fires before project-list is ready

**Severity**: high  
**Area**: multi-project  
**Evidence**: `MultiProjectCommandCenter.tsx:237–238,251–252`. `projectListReady: true` hardcoded; queries fire before `projects.json` has resolved.

### MED-01: Session board hover causes O(N) re-render cascade

**Severity**: medium  
**Area**: perf  
**Evidence**: `PlanningAgentSessionBoard.tsx:1283–1323`. New `Set` objects constructed on every `activeSessionId` change (hover), causing all `SessionCard` memo wrappers to re-evaluate `isHighlighted` prop.

### MED-02: Board command center pageSize=50 with no UI pagination

**Severity**: medium  
**Area**: ux  
**Evidence**: `PlanningCommandCenter.tsx:119,143`. Projects with >50 features silently truncate. Users cannot access features 51+.

### MED-03: MULTI_PROJECT_COMMAND_CENTER_ENABLED is build-time only

**Severity**: medium  
**Area**: container  
**Evidence**: `constants.ts:418–421`. Requires Vite rebuild to enable multi-project mode in container.

### MED-04: Google Fonts CDN dependency in planning route layout

**Severity**: medium  
**Area**: container  
**Evidence**: `PlanningRouteLayout.tsx:31–48`. Three CDN links injected on every planning route. Fails silently in restricted-egress containers; no offline fallback.

### MED-05: StaleIndicator setInterval runs from mount regardless of stale state

**Severity**: medium  
**Area**: perf  
**Evidence**: `PlanningAgentSessionBoard.tsx:879–884`. 15s interval starts immediately even when board data is fresh.

### LOW-01: Cmd-K search and "New Spec" are stubs

**Severity**: low  
**Area**: ux  
**Evidence**: `PlanningTopBar.tsx:116,131`. Toast-only responses; functionality not implemented.

### LOW-02: Sparkline data and token-saved % are heuristic fictions

**Severity**: low  
**Area**: ux  
**Evidence**: `PlanningHomePage.tsx:135–142` (fake sparkline), line 127 (heuristic token-saved %). TODO comments present. Misleads enterprise users.

---

## 11. Desired Command-Center Gap Analysis

| Capability | Current state | Gap to close |
|---|---|---|
| Active plans per project | Done: `ActivePlansColumn` | — |
| Phase/status per feature | Done: `CommandCenterListView` phase column | — |
| Blocked / stale attention | Done: `PlanningSummaryPanel` attention columns | Add click-through beyond 8 items (ROW_LIMIT) |
| Next available work command | Done: `QuickCommandBar`, `commandCenterLaunchReadiness` | Add search/filter across all work items (Cmd-K stub) |
| Live agent session status | Done: `PlanningAgentSessionBoard` + live-agent pill | Add server-side pagination to session board endpoint |
| Linked sessions → features | Done: card `correlation`, `BoardColumn` feature links | — |
| Linked artifacts per feature | Done: `artifacts[]` in command center items | — |
| Cross-project portfolio view | Partial: `MultiProjectCommandCenter` exists | Enable flag; fix projectListReady; verify backend endpoints |
| Historical completed view | Partial: 'done' bucket in command center | No time-ordered recently-completed column; no sparkline from real data |
| Token telemetry | Partial: per-card `tokenSummary`, aggregate context envelope | `ctxPerPhase` / `tokensSavedPct` are stubs; need backend data |
| Global search | Missing: Cmd-K stub | Full implementation required |
| Spec / artifact creation | Missing: "New Spec" stub | Full creation workflow required |
| Real-time push (SSE/WS) | Partial: `useLiveInvalidation` wired for planning summary | Not wired to session board or command center |
