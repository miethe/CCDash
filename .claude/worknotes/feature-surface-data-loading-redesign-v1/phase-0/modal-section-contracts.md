---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-004
created: 2026-04-23
---

# Modal Section Contracts — ProjectBoardFeatureModal

---

## 1. Summary

**Cold-modal-open request budget: 1 request.**

When a user opens the modal on the Overview tab, exactly one request fires:
`GET /api/v1/features/{encoded_feature_id}?include=overview_shell`

This request returns the overview shell fields only. Every other tab lazy-loads its own bounded fetch on first activation. The Sessions tab is the only tab that pages at the source. History/Activity derives from a dedicated activity aggregate endpoint, not from the full session array. Test Status fires independently only when the tab is explicitly activated.

The current implementation violates this budget in two ways:
1. `refreshFeatureDetail` and `refreshLinkedSessions` both fire unconditionally on every modal mount.
2. The feature detail endpoint (`GET /api/features/{feature.id}`) is fetched without `encodeURIComponent` on the raw `feature.id` string inside the detail load effect.

### Top 3 open questions

1. **Activity aggregate endpoint does not exist yet.** `GET /api/v1/features/{feature_id}/activity` is specified in the target data contracts table but has no backend implementation. History/Activity tab contracts in this document are forward-specifying that endpoint. Phase 2 must confirm its response shape before Phase 4 can implement the tab hook.

2. **Phase/task session and commit annotation without the full session array.** Phases tab currently builds `phaseSessionLinks` and `taskSessionLinksByTaskId` maps by iterating the full session list. The replacement contract proposes a dedicated `GET /api/v1/features/{feature_id}/phases/session-annotations` endpoint. This endpoint does not exist; Phase 2 must decide whether to add it to the features router or embed the data in the full feature detail response under a `phaseAnnotations` include flag.

3. **`include=` parameter shape for the overview shell vs. full detail.** The current `GET /api/features/{feature_id}` endpoint returns the entire `Feature` object unconditionally. Splitting this into a cheap shell vs. optional includes requires either a new v1 endpoint or an `include=` query parameter on the existing endpoint. The chosen approach dictates how `useFeatureModalOverview` constructs its URL and cache key, and must be resolved in Phase 2 before Phase 4 implementation begins.

---

## 2. Tab Contracts

### 2.1 Overview Tab

The Overview tab must load cheaply on every modal open. It owns the cold-open request.

**Shell fields (always in this response, payload bounded):**
`id`, `name`, `status`, `category`, `priority`, `riskLevel`, `complexity`, `track`, `featureFamily`, `targetRelease`, `milestone`, `executionReadiness`, `tags`, `totalTasks`, `completedTasks`, `deferredTasks`, `phaseCount`, `documentCoverage`, `qualitySignals` (scalars only: `blockerCount`, `atRiskTaskCount`, `testImpact`, `integritySignalRefs`), `planningStatus` (`rawStatus`, `effectiveStatus`, `mismatchState`), `executionGate` (`state`, `isReady`, `reason`, `waitingOnFamilyPredecessor`, `familyPosition`), `familySummary` (`featureFamily`, `sequencedItems`, `unsequencedItems`, `nextRecommendedFeatureId`, `nextRecommendedFamilyItem`), `dates` (all scalar date values), `linkedDocs` (metadata only: `id`, `title`, `docType`, `filePath`, `status`, `sequenceOrder`, `prdRef`, `lineageFamily`, `lineageParent`, `lineageChildren` — no content body), `linkedFeatures` (typed refs: `feature`, `type`, `source`, `confidence`, `notes`), `relatedFeatures`, `blockingFeatures` (up to 5 items for blocking evidence display), `dependencyState`.

**Deferred fields (not in shell, require explicit include):**
Full `phases[]` with nested `tasks[]` — those are owned by the Phases tab. Full session arrays — owned by Sessions tab. Git history aggregates — owned by History tab.

| Attribute | Value |
|---|---|
| Source endpoint | `GET /api/v1/features/{encoded_feature_id}` (new v1 path) or `GET /api/features/{encoded_feature_id}?include=overview_shell` (existing path with include gate) |
| Request shape | Path: `feature_id` must be `encodeURIComponent`-encoded. No pagination. Optional: `?include=phases` to add full phase+task tree for Phases tab co-loading (not default). |
| Response shape | Overview shell field list above. No `phases[].tasks[]` unless `include=phases` is passed. `linkedDocs` carries metadata only — no `content` field. |
| Trigger | `open-on-modal-open` — fires immediately when modal mounts, regardless of active tab. |
| Cache key | `['feature', 'modal-overview', projectId, featureId]` |
| Cache policy | `staleTime: 30_000` (30 s). Invalidate on: `featureTopic(featureId)` live event, mutation of feature status/phase/task status. Do not invalidate on session events for unrelated features. |
| Loading state | Full modal skeleton: status badge placeholder, three metric tile placeholders, field-row placeholders. No tab content shown while shell loads. |
| Error state | Inline error banner inside modal with "Retry" button. Copy: "Could not load feature details. Try again." Empty fields must not render null — show `—` placeholder per field. Distinguish network failure (retry affordance) from 404 (permanent error copy: "Feature not found"). |
| Failure mode | 404: render "Feature not found" in the modal body, disable all tabs, show close button. 5xx / network: retain last cached data if available (stale-while-error); show non-blocking error toast. No tab content loads while shell is in error state. |
| Request bound | Single feature object. Payload target < 15 KB. `linkedDocs` capped at 100 items in metadata-only form. `blockingFeatures` capped at 10. |

---

### 2.2 Phases / Tasks Tab

Phase and task data are already embedded in the full `Feature.phases[]` tree that the Overview shell may return via `include=phases`. If the shell omitted phases (the default), the Phases tab fires a bounded supplemental fetch on first activation.

**Fields needed:**
`phases[].phase`, `phases[].title`, `phases[].status`, `phases[].completedTasks`, `phases[].totalTasks`, `phases[].tasks[].id`, `.title`, `.status`, `.owner`. Phase-to-session annotation (session IDs + commit hashes per phase/task) is a separate lightweight fetch — see below.

| Attribute | Value |
|---|---|
| Source endpoint | Primary: overview shell with `include=phases` param (preferred — zero extra requests if co-loaded). Fallback: `GET /api/v1/features/{encoded_feature_id}/phases` (new, returns phases+tasks only, no session data). Phase session annotations: `GET /api/v1/features/{encoded_feature_id}/phases/session-annotations` (planned new endpoint — see Open Question 2). |
| Request shape | `feature_id` encoded. No pagination (phase count is bounded per feature). Session annotations endpoint: no required params; returns map of `{ phaseNumber: { sessionIds: string[], commitHashes: string[] }, taskId: { sessionIds: string[], commitHashes: string[] } }`. |
| Response shape | `{ phases: FeaturePhase[] }` where each phase includes `tasks[]`. Annotation response: `{ byPhase: Record<string, {sessionIds, commitHashes}>, byTask: Record<string, {sessionIds, commitHashes}> }`. |
| Trigger | `open-on-tab-activate` — fires when user clicks Phases tab if phases data is not yet in cache. Annotation fetch fires in parallel with phases fetch on tab activation. |
| Cache key | `['feature', 'phases', projectId, featureId]`, `['feature', 'phase-annotations', projectId, featureId]` |
| Cache policy | `staleTime: 60_000` (60 s). Invalidate on: `featureTopic(featureId)` or `featurePhaseTopic(featureId, phaseNumber)` live event. Session annotation cache invalidates on `featureTopic(featureId)` events only. |
| Loading state | Phase accordion skeletons (one per expected phase count from Overview shell's `phaseCount` field). Task rows show placeholder lines inside expanded accordions. Annotation badges show `—` until annotation fetch resolves. |
| Error state | Per-section: if phases fetch fails, show "Could not load phases" with Retry inside the tab body. If annotation fetch fails, show phase/task session badges as `—` with a non-blocking inline note "Session links unavailable". |
| Failure mode | 404 on phases endpoint: show "No phase data found" empty state, not an error. 5xx: show retry affordance. Annotation 404/5xx: degrade gracefully — hide session/commit annotation columns rather than blocking the entire tab. |
| Request bound | Phases payload: bounded by feature (typically < 10 phases, < 50 tasks). Annotation payload: `sessionIds` capped at 5 per phase/task, `commitHashes` capped at 5 per phase/task. |

---

### 2.3 Documents Tab

Documents are already present in the Overview shell as lightweight `linkedDocs` metadata (no content body). The Documents tab needs no additional fetch in the nominal case — it renders from the shell's `linkedDocs` array.

**Fields needed from shell:** `linkedDocs[].id`, `.title`, `.docType`, `.filePath`, `.status`, `.featureFamily`, `.sequenceOrder`, `.prdRef`, `.blockedBy`, `.lineageFamily`, `.lineageParent`, `.lineageChildren`. Primary/supporting badge derived from `Feature.primaryDocuments` (also in shell).

**Fields that require a supplemental fetch:** If the user clicks a document card to expand its full content body (`content`, `sections`), a separate `GET /api/documents/{doc_id}` fetch fires lazily. This is out of scope for the tab-level contract; the tab itself does not need it.

| Attribute | Value |
|---|---|
| Source endpoint | Overview shell data only (no additional endpoint on tab activate). Document content expansion (optional, user-triggered): `GET /api/documents/{encoded_doc_id}` (existing endpoint, confirmed suitable — `documents_router.get("/{doc_id}")` in `backend/routers/api.py`). |
| Request shape | None on tab activate. Document expand: `GET /api/documents/{encodeURIComponent(doc_id)}`. |
| Response shape | Derives from `linkedDocs[]` already in cache. Document expand: `PlanDocument` including `content` field. |
| Trigger | `open-on-tab-activate` — no fetch fires. Tab renders immediately from Overview shell cache. |
| Cache key | No separate key needed for the tab itself. Document expand: `['document', 'detail', doc_id]`. |
| Cache policy | Derives from Overview shell cache (`staleTime: 30_000`). Document expand: `staleTime: 120_000`, no live invalidation unless a document-specific topic is subscribed. |
| Loading state | If Overview shell is still loading, tab shows generic skeleton. Once shell resolves, Documents tab renders immediately — no additional loading state. |
| Error state | If `linkedDocs` is empty array: "No linked documents found" empty state (not an error). If shell errored: tab shows locked state with Overview error UI. |
| Failure mode | Document expand failure: inline card-level error, does not affect the tab. |
| Request bound | `linkedDocs` metadata already bounded (< 100 items) in shell. |

---

### 2.4 Relations Tab

All relations data is present in the Overview shell. The Relations tab renders entirely from cache — no additional fetch on tab activate.

**Fields needed from shell:**
`linkedFeatures[]` (typed refs), `relatedFeatures[]`, `blockingFeatures[]` / `dependencyState.dependencies[]`, `familySummary.*`, `familyPosition.*`, `executionGate.familyPosition.*`. Lineage fields from `linkedDocs[].lineageFamily/lineageParent/lineageChildren` (already in shell's `linkedDocs` metadata).

| Attribute | Value |
|---|---|
| Source endpoint | None on tab activate — all data from Overview shell cache. |
| Request shape | None. |
| Response shape | Derives from shell cache. |
| Trigger | `open-on-tab-activate` — no fetch. Renders from Overview shell. |
| Cache key | No separate key. Shares Overview shell key `['feature', 'modal-overview', projectId, featureId]`. |
| Cache policy | Inherits Overview shell policy. |
| Loading state | If shell is loading, tab shows skeleton. If shell has resolved, tab renders immediately. |
| Error state | If `linkedFeatures` is absent or empty: "No relations found" empty state per relation group. If `dependencyState` is absent: degrade — hide blocking evidence section with "Dependency data unavailable" note. |
| Failure mode | No independent failure mode. Fails only if Overview shell fails. |
| Request bound | Bounded by shell. `blockingFeatures` capped at 10 in shell. |

---

### 2.5 Sessions Tab

Sessions tab is the highest-cost tab and must never eagerly load on modal open. It must page at the source and support explicit enrichment via `include=` parameters.

**Fields needed — summary tiles (from rollup, not paginated list):**
`sessionCount`, `primarySessionCount`, `subthreadCount`, `observedTokens`, `modelIOTokens`, `cacheInputTokens` — these come from `FeatureRollupDTO` (defined in P0-003). Rollup is loaded as part of the card-level board data; the modal reuses it from shared cache.

**Fields needed — per-session list (paginated):**
`sessionId`, `title`, `status`, `model*`, `modelsUsed[]`, `startedAt`, `endedAt`, `updatedAt`, `durationSeconds`, `workloadTokens` (server-pre-computed), `displayCostUsd`, `gitCommitHash`, `gitCommitHashes`, `confidence`, `contextUtilizationPct`, `isPrimaryLink`, `isSubthread`, `parentSessionId`, `sessionType`, `workflowType`, `cacheShare` (server-pre-computed), `linkStrategy`, `reasons[]`, `commands[]`, `toolSummary[]`, `agentsUsed[]`, `skillsUsed[]`.

**Enrichment includes (opt-in, explicit `include=` param):**
- `include=logs` — full JSONL transcript events. Heavy; only when user expands session detail into transcript view.
- `include=tokens` — full per-model token breakdown. Medium; adds `modelIOTokens` per session item.
- `include=subthreads` — inline sub-thread session items nested under their parent. Medium.

The `hasLinkedSubthreads` flag MUST be a server-computed boolean on each session item — the frontend must not perform O(n²) cross-checks.

**Cross-reference with phase tasks:** Phase task annotations (which task a session relates to) come from the Phases annotation endpoint, not from the sessions page. The sessions list does not carry task linkage inline unless `include=task_annotations` is explicitly requested.

| Attribute | Value |
|---|---|
| Source endpoint | Tile summary: `FeatureRollupDTO` from shared board rollup cache (no new fetch). Paginated list: `GET /api/v1/features/{encoded_feature_id}/sessions?cursor={cursor}&limit=20&include={comma-separated}` (new paginated v1 endpoint replacing unbounded `GET /api/features/{feature_id}/linked-sessions`). |
| Request shape | `feature_id`: `encodeURIComponent`-encoded. `cursor`: opaque cursor string (or absent for first page). `limit`: default 20, max 50. `include`: optional comma-separated values from `{logs, tokens, subthreads, task_annotations}`. Sort: `started_at desc` (fixed). |
| Response shape | `{ items: FeatureSessionLink[], next_cursor: string \| null, total: number, has_more: boolean }`. Each item carries `hasLinkedSubthreads: boolean` (server-computed). Token metrics (`workloadTokens`, `cacheShare`) are server-pre-computed scalars — no client-side `resolveTokenMetrics` calls. |
| Trigger | `open-on-tab-activate` — fires when user first clicks Sessions tab. Pagination fires on scroll-to-end or explicit "Load more" interaction. |
| Cache key | `['feature', 'sessions', projectId, featureId, cursor, include]` — cursor and include are part of the key. First page: `['feature', 'sessions', projectId, featureId, null, '']`. |
| Cache policy | `staleTime: 15_000` (15 s, shorter than shell — sessions change frequently). Invalidate on: `featureTopic(featureId)` live event. Subsequent pages inherit the same invalidation; all pages for a feature are invalidated together on a live event. |
| Loading state | On first tab activation: metric tile skeletons (4 tiles), then a list of 5 session card skeletons. Pagination: spinner at bottom of list + disabled "Load more" button. |
| Error state | Tile summary uses rollup cache — if rollup is absent, tiles show `—` (not an error). Paginated list failure: "Could not load sessions" inline error with Retry button. Subsequent page failure: toast error, existing loaded pages remain visible. Distinguish: empty first page ("No sessions linked to this feature") from network error ("Failed to load sessions — Retry"). |
| Failure mode | 404: treat as "no sessions" empty state, not an error. 5xx: show retry affordance on first page. If rollup tile data is stale, show staleness indicator rather than hiding tiles. |
| Request bound | Page size: default 20, hard max 50 items per request. Each session item payload: target < 2 KB without enrichment includes. No full log arrays unless `include=logs` is explicitly passed. |

---

### 2.6 Test Status Tab

Test Status is fully independent of feature detail and session data. It calls the health/features endpoint only when the tab is explicitly activated.

**Fields needed:**
`FeatureTestHealth` — `featureId`, `featureName`, `totalTests`, `passingTests`, `failingTests`, `skippedTests`, `coverage`, `lastRunAt`, domain health items.

| Attribute | Value |
|---|---|
| Source endpoint | `GET /health/features?project_id={projectId}&feature_id={encoded_feature_id}&limit=1` (existing `test_visualizer_router.get("/health/features")` in `backend/routers/test_visualizer.py`). |
| Request shape | `project_id`: active project ID. `feature_id`: `encodeURIComponent`-encoded feature ID. `limit=1`. No cursor needed (single feature lookup). |
| Response shape | `CursorPage<FeatureTestHealth>` — take `items[0]` where `item.featureId === featureId`. If no item matches, treat as no test data. |
| Trigger | `open-on-tab-activate` — fires only when user clicks Test Status tab. The current implementation fires this unconditionally on modal mount (in the `refreshFeatureTestHealth` `useEffect` with no tab gate) — this is a bug to fix in Phase 4. |
| Cache key | `['feature', 'test-health', projectId, featureId]` |
| Cache policy | `staleTime: 60_000` (60 s). Invalidate on: `projectTestsTopic(projectId)` live event. Does NOT invalidate on `featureTopic` or session events. |
| Loading state | Full-tab loading skeleton matching the FeatureModalTestStatus component structure (metric tiles + domain list rows). |
| Error state | If `totalTests === 0` or no item returned: "No test data for this feature" empty state — not an error. Network/5xx failure: "Could not load test status" with Retry. |
| Failure mode | 404: empty state. 5xx: show retry, keep previous data if cached. If tab is navigated to when `totalTests === 0`, the current code auto-redirects to overview — this behavior should be preserved (check after fetch resolves, before rendering). |
| Request bound | Single response item (limit=1 filtered by featureId). |

---

### 2.7 History / Activity Tab

History tab currently requires the full session array to build git commit aggregates, PR lists, branch lists, and the session-start/end event timeline. Under the new contract, all of this is served by a dedicated activity aggregate endpoint. The frontend must never load full session arrays for this tab.

**Fields needed — commit aggregates:**
`commits[]` each with: `hash`, `sessionIds[]`, `branches[]`, `phases[]`, `taskIds[]`, `filePaths[]`, `pullRequests[]`, `tokenInput`, `tokenOutput`, `fileCount`, `additions`, `deletions`, `costUsd`, `eventCount`, `toolCallCount`, `commandCount`, `artifactCount`.

**Fields needed — PR and branch summaries:**
`pullRequests[]`, `branches[]`, `commitsCount`, `pullRequestsCount`, `branchesCount`.

**Fields needed — timeline events:**
`events[]` each with: `type` (`feature_event` | `doc_event` | `session_start` | `session_end`), `timestamp`, `label`, `sessionId?`, `docId?`, `phase?`. Session start/end boundaries are pre-computed server-side from session `startedAt`/`endedAt` — the frontend does not receive the session list.

| Attribute | Value |
|---|---|
| Source endpoint | `GET /api/v1/features/{encoded_feature_id}/activity?cursor={cursor}&limit=50` (new endpoint — does not exist yet; see Open Question 1). Commit filter (client-side text filter on `gitHistoryCommitFilter` state) operates on already-fetched items. |
| Request shape | `feature_id`: `encodeURIComponent`-encoded. `cursor`: opaque cursor (absent for first page). `limit`: default 50 commits. Optional: `?since={iso_timestamp}` to bound the window. |
| Response shape | `{ commits: GitCommitAggregate[], pullRequests: PrSummary[], branches: string[], events: ActivityEvent[], commitsCount: number, pullRequestsCount: number, branchesCount: number, next_cursor: string \| null }`. Session session start/end events are pre-merged into `events[]` by the backend — no raw session array in the response. |
| Trigger | `open-on-tab-activate` — fires when user first clicks History tab. |
| Cache key | `['feature', 'activity', projectId, featureId, cursor]` |
| Cache policy | `staleTime: 60_000` (60 s). Invalidate on: `featureTopic(featureId)` live event. Does NOT require invalidation on `sessionTopic` for individual sessions — the activity aggregate is batch-refreshed when the feature topic fires. |
| Loading state | Three count tiles (commits, PRs, branches) as skeletons, then commit list row placeholders. Timeline section shows event skeleton rows. |
| Error state | If `commitsCount === 0` and `events` is empty: "No git history found for this feature" empty state. Network/5xx: "Could not load history" with Retry. Distinguish empty from error. |
| Failure mode | 404: empty state. 5xx: retry affordance. Activity endpoint not yet available (Phase 2 gap): tab shows "History data unavailable" with note, does not block other tabs. |
| Request bound | Commits capped at 50 per page. Per-commit `filePaths[]` capped at 20. Events capped at 200 per page. No session log content in this response. |

---

## 3. Hook / Cache-Key Conventions

### Recommended hook names

| Hook | Owns | Key shape |
|---|---|---|
| `useFeatureModalOverview(projectId, featureId)` | Overview shell fetch + cache | `['feature', 'modal-overview', projectId, featureId]` |
| `useFeaturePhases(projectId, featureId, enabled)` | Phase+task list | `['feature', 'phases', projectId, featureId]` |
| `useFeaturePhaseAnnotations(projectId, featureId, enabled)` | Phase/task session annotation map | `['feature', 'phase-annotations', projectId, featureId]` |
| `useFeatureSessionsPage(projectId, featureId, cursor, include)` | Sessions paginated page | `['feature', 'sessions', projectId, featureId, cursor, include]` |
| `useFeatureTestHealth(projectId, featureId, enabled)` | Test health | `['feature', 'test-health', projectId, featureId]` |
| `useFeatureActivity(projectId, featureId, cursor, enabled)` | Activity/history aggregates | `['feature', 'activity', projectId, featureId, cursor]` |

**Key invariants:**
- `projectId` is always the first variable segment after the resource noun — switching projects must produce a distinct key and a full cache miss.
- `featureId` is always passed as the raw (decoded) string to hooks; hooks are responsible for calling `encodeURIComponent(featureId)` when building the URL.
- `enabled` boolean gates all lazy-tab hooks — set `enabled: false` until the tab is activated.
- `cursor` is part of the Sessions and Activity keys — the first page uses `cursor: null`.

### Path encoding rule

Every hook that constructs a URL with `featureId` in the path must call `encodeURIComponent(featureId)` at the point of URL construction, not before. Do not pre-encode the `featureId` passed as a prop — the raw ID is needed for cache key identity. Current hotspot: line 1511 and line 1524 in `ProjectBoard.tsx` use `feature.id` directly without encoding; both must be fixed.

---

## 4. Invalidation and Prefetch Rules

### Query-key invalidation matrix

| Hook | Invalidates on | Ignores |
|---|---|---|
| `useFeatureModalOverview` | `featureTopic(featureId)`, feature status/phase/task mutations | Unrelated session events, test events |
| `useFeaturePhases` | `featureTopic(featureId)`, `featurePhaseTopic(featureId, *)` | Session events, test events |
| `useFeaturePhaseAnnotations` | `featureTopic(featureId)` | Individual session events, test events |
| `useFeatureSessionsPage` | `featureTopic(featureId)` — invalidates all session pages for the feature | Session events for other features |
| `useFeatureTestHealth` | `projectTestsTopic(projectId)` | Feature events, session events |
| `useFeatureActivity` | `featureTopic(featureId)` | Individual session events |

**Live event behavior:**
- When `featureTopic(featureId)` fires, Overview, Phases, PhaseAnnotations, Sessions, and Activity caches for that feature are all marked stale. They re-fetch on next access (stale-while-revalidate pattern).
- Sessions pages: on invalidation, only the first page is automatically refetched. Subsequent cursor pages are dropped from cache and must be re-paginated by user scroll.
- Test Health only subscribes to `projectTestsTopic` — test run completions do not carry a per-feature topic currently.

### Prefetch rules

**Hover prefetch (optional, low-priority):**
- When a user hovers a feature card for > 300 ms, the board may prefetch `useFeatureModalOverview` for that feature ID. This is a best-effort prefetch with low priority — it must not block card rendering or trigger linked-session fetches.
- Phases and Sessions tabs: no hover prefetch. They are lazy by definition.
- Test Health: no hover prefetch. Test data is project-scoped and not worth per-card prefetching.

**Tab-switch prefetch:**
- When the user is on the Overview tab and moves the pointer toward another tab (intent signal), no automatic prefetch fires. Prefetch fires only on `pointerdown` / `click` of the tab button — this is the `open-on-tab-activate` trigger.

**No background refresh:**
- Modal hooks do not use polling intervals. Live invalidation via `useLiveInvalidation` is the sole refresh mechanism while the modal is open.

---

## 5. Open Questions

1. **Activity aggregate endpoint does not exist.** `GET /api/v1/features/{feature_id}/activity` is forward-specified here. History tab cannot be implemented in Phase 4 until Phase 2 defines and builds this endpoint. Interim option: Phase 4 can show a degraded "History unavailable" state for History tab while the endpoint is pending, with full History tab implementation gated on Phase 2 completion.

2. **Phase/task session annotation endpoint does not exist.** `GET /api/v1/features/{feature_id}/phases/session-annotations` is specified here. An alternative approach — embedding phase annotations in the overview shell under `include=phase_annotations` — avoids a new endpoint at the cost of a larger shell payload. Phase 2 must choose one.

3. **`include=` parameter on the overview shell endpoint.** The current `GET /api/features/{feature_id}` endpoint returns the full `Feature` object with no include gating. To make the shell cheap, Phase 2 must either (a) add include-gating to the existing endpoint, (b) create a new v1 shell endpoint, or (c) define a separate minimal DTO endpoint. The cache key shape in this document assumes approach (a) or (b). If (c) is chosen, the key must include the DTO variant as a segment.

4. **Rollup tile data source for Sessions tab.** The Sessions tab metric tiles (total, primary, subthread, token totals) are assumed to come from `FeatureRollupDTO` which is defined in P0-003 and does not exist yet. If the rollup DTO is not available by Phase 4, these tiles must either be computed from the first page of sessions (imprecise) or omitted until the rollup is ready. Phase 3/4 coordination is required.

5. **Session-to-task annotation strategy.** The Phases tab currently shows which sessions are linked to each task (`taskSessionLinksByTaskId`). This requires either a server-side annotation join or a client-side cross-reference between the sessions page and the phase task list. Under the new contracts, the sessions page does not carry task IDs unless `include=task_annotations` is requested. Phase 2 must decide whether `task_annotations` becomes a supported include param on the sessions endpoint or whether a dedicated annotation endpoint is the right seam.

6. **`encodeURIComponent` audit scope.** This document requires all modal hooks to encode `featureId` in URL paths. The current codebase has at least two unencoded paths in `ProjectBoard.tsx` (lines 1511, 1524) and one correctly encoded path at line 4593. Phase 4 implementation must audit all paths in `ProjectBoardFeatureModal` render scope, including any feature ID embedded in navigation URLs (e.g., the execution workbench link at line 1687).
