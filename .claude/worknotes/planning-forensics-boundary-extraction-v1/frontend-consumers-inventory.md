---
created: 2026-05-06
purpose: Phase 0 inventory — all frontend consumers of feature/session forensics data
scope: services/, components/, contexts/ at repo root
---

# Frontend Feature/Session Consumers Inventory

Complete inventory of every frontend file that consumes feature forensics data, feature surface layer APIs, session evidence, or token telemetry. Generated as part of the planning-forensics boundary extraction refactor (Phase 0).

Search commands used:
```
grep -rn "forensic|FeatureForensic|featureForensic|session.*evidence|token.*telemetry|tokenTelemetry" services/ components/ contexts/
grep -rn "featureSurface|useFeatureSurface|featureCacheBus|publishFeatureWrite|useFeatureModalData|featureSurfaceCache|FeatureRollupDTO|FeatureCardDTO|getFeatureRollups|listFeatureCards|getFeatureLinked|getLegacyFeature" components/ services/
```

---

## Legend

- **Summary data**: counts, totals, status labels, freshness timestamps — no session message content
- **Full forensics**: session transcripts, per-message tool usage, `sessionForensics` blob fields, rework signals, detailed session evidence
- **Direct API consumer**: file calls `featureSurface.ts` or `useFeatureSurface` / `useFeatureModalData` hooks directly
- **Props/context**: file receives feature/session data through props, context, or parent-passed callbacks

---

## Required Consumers (Spec-Identified)

### 1. `services/useFeatureModalData.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/useFeatureModalData.ts` |
| Line range (imports) | L34–46 |
| Line range (hook body) | L363–721 |
| Data dependency | `FeatureModalOverviewDTO` (card + rollup), `FeatureModalSectionDTO` (phases / docs / relations / test_status / activity), `LinkedFeatureSessionPageDTO` (sessions with pagination) |
| Summary vs Full Forensics | **Summary only.** Sections carry structured items (`label`, `kind`, `status`, `badges`, `metadata`). No transcript or raw `sessionForensics` blob is fetched. Session section returns `LinkedFeatureSessionDTO` with session-level counts (tokens, cost, status) — not message-level detail. |
| Consumer type | **Direct API consumer** — calls `getFeatureModalOverview`, `getFeatureModalSection`, `getFeatureLinkedSessionPage`, `getLegacyFeatureDetail`, `getLegacyFeatureLinkedSessions` from `featureSurface.ts` |
| Notes | 7-section hook with internal `ModalSectionLRU` (120-entry LRU, module-level singleton). Each section has independent `idle/loading/error/stale/success` lifecycle. The `sessions` section exposes pagination via `sessionPagination` + `loadMoreSessions`. v2 path (`featureSurfaceV2Enabled=true`) routes through typed v1 endpoints; v2-disabled path falls back to legacy flat-array endpoints. Cache key: `{featureId}|{section}|{paramsHash}`. |

---

### 2. `components/FeatureModal/TabStateView.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/FeatureModal/TabStateView.tsx` |
| Line range (types) | L30–60 |
| Line range (component) | L147–186 |
| Data dependency | `TabStatus` (`idle | loading | success | error | stale`), `error?: string`, `isEmpty?: boolean`, `children: ReactNode` |
| Summary vs Full Forensics | **Not a data consumer.** Pure rendering primitive — no feature or session data is accessed directly. |
| Consumer type | **Props only** — receives `status`, `error`, `onRetry`, `isEmpty`, `emptyLabel`, `staleLabel`, `children` from parent |
| Notes | Mirrors `ModalSectionStore` status values (P4-002). Renders `LoadingSkeleton`, `ErrorBanner`, `StaleIndicator`, or `EmptyState` depending on status. Wraps all modal tab content in `ProjectBoardFeatureModal`. No data fetching or transformation occurs here. |

---

### 3. `services/featureSurface.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/featureSurface.ts` |
| Line range (wire types) | L85–334 |
| Line range (public DTOs) | L336–631 |
| Line range (adapters) | L632–844 |
| Line range (API methods) | L846–1111 |
| Data dependency | `FeatureCardDTO` (summary fields: status, task counts, coverage, quality signals), `FeatureRollupDTO` (session counts, token totals, model families, doc/test metrics), `FeatureModalOverviewDTO`, `FeatureModalSectionDTO`, `LinkedFeatureSessionPageDTO` |
| Summary vs Full Forensics | **Summary by design.** `FeatureRollupDTO` exposes aggregate token totals (`observedTokens`, `modelIoTokens`, `cacheInputTokens`), session counts, and model/workflow type breakdowns — not per-session transcripts or tool-call details. `LinkedFeatureSessionDTO` carries session-level metadata (status, model, cost, `reasons[]`, `commands[]`) but not message-level content. |
| Consumer type | **Direct API consumer** — the leaf client layer. Calls `/api/v1/features`, `/api/v1/features/rollups`, `/api/v1/features/{id}/modal`, `/api/v1/features/{id}/modal/{section}`, `/api/v1/features/{id}/sessions/page`. Also wraps legacy `/api/features/{id}` and `/api/features/{id}/linked-sessions`. |
| Notes | All wire shapes are internally typed (`Wire*`); public exports are camelCase DTOs. Snake_case fallback handled by `wireField()`. `getLegacyFeatureLinkedSessions` is deprecated (P5-006) — kept for test harnesses only. `getFeatureTaskSource` resolves task source file content for a task-source dialog. |

---

### 4. `services/featureSurfaceCache.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/featureSurfaceCache.ts` |
| Line range (LRU impl) | L52–101 |
| Line range (FeatureSurfaceCache class) | L129–254 |
| Line range (invalidateFeatureSurface) | L291–319 |
| Line range (bus subscription) | L328–335 |
| Line range (useFeatureSurfaceLiveInvalidation hook) | L390–455 |
| Data dependency | `CacheEntry` (from `useFeatureSurface`), `RollupCacheEntry` (rollup payloads + timestamp) |
| Summary vs Full Forensics | **Infrastructure only** — stores and evicts cached list + rollup data. Does not consume feature or session content itself. |
| Consumer type | **Indirect** — caches payloads produced by `featureSurface.ts`. Receives `FeatureWriteEvent` from `featureCacheBus.ts` as a subscriber. |
| Notes | Two-tier LRU: Tier 1 list pages (max 50 entries), Tier 2 rollups (max 100 entries, 30s TTL). `invalidateFeatureSurface()` is exported for use by `ProjectBoard.tsx` and the bus subscriber. `useFeatureSurfaceLiveInvalidation` React hook wires live topics (`project.{id}.features`, `feature.{id}`, `session.{id}`, `project.{id}.tests`) to the hook's `invalidate` action. |

---

### 5. `services/featureCacheBus.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/featureCacheBus.ts` |
| Line range (types) | L20–37 |
| Line range (API) | L42–88 |
| Data dependency | `FeatureWriteEvent` (`projectId`, `featureIds[]`, `kind: status | phase | rename | task | generic`) |
| Summary vs Full Forensics | **Infrastructure only** — pub/sub bus. Carries only IDs and mutation kind; no feature content. |
| Consumer type | **Infrastructure** — synchronous pub/sub. Subscribers: `featureSurfaceCache.ts` (L328) and `planning.ts` (L315). Publishers: `ProjectBoard.tsx` (L1814, L1861, L1896, L4897). |
| Notes | Module-level `_subscribers: Set` registry. `publishFeatureWriteEvent()` is synchronous and catches subscriber errors individually. `subscribeToFeatureWrites()` is called at module init time by both cache modules, so the registry is always populated before any write fires. |

---

### 6. `components/ProjectBoard.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/ProjectBoard.tsx` |
| Line range (imports) | L6–68 |
| Line range (feature surface hook call) | L4839–4851 |
| Line range (FeatureCard/FeatureListCard render) | L4438–4590, L4682–4700 |
| Line range (feature modal open logic) | L4950–4965 |
| Line range (publishFeatureWriteEvent calls) | L1814, L1861, L1896, L4897 |
| Line range (invalidateFeatureSurface call) | L4899 |
| Line range (useFeatureModalData hook) | L1427 |
| Line range (TabStateView usage) | L3146–4106 |
| Data dependency | `FeatureCardDTO` (board column rendering), `FeatureRollupDTO` (session badge, cost badge, last-active indicator via `rollupToSessionSummary`), `FeatureModalOverviewDTO` + section DTOs (modal tabs via `useFeatureModalData`), `LinkedFeatureSessionDTO` (sessions tab list), `FeatureQualitySignalsDTO` (blocker/at-risk signals), `FeatureDependencySummaryDTO` (blocking-feature state) |
| Summary vs Full Forensics | **Board cards: summary only** (card metrics, rollup totals). **Modal overview tab: summary** (card + rollup). **Modal sessions tab: summary session list** (per-session metadata, no transcripts). **Modal phases/docs/relations/test-status/history tabs: structured summary items** (label, kind, status, metadata). No raw `sessionForensics` blob is rendered in this component. |
| Consumer type | **Direct API consumer** — calls `useFeatureSurface` for board data, `useFeatureModalData` for modal sections, and directly calls `getLegacyFeatureDetail`, `getFeatureLinkedSessionPage`, `getFeatureTaskSource` from `featureSurface.ts`. Also calls `publishFeatureWriteEvent` (write-through) and `invalidateFeatureSurface` (explicit React state reset). |
| Notes | Modal entry point and cache-bus publisher. `ProjectBoardFeatureModal` (L1379) is where `useFeatureModalData` is instantiated. Status/phase/task mutations at L1814, L1861, L1896 each call `publishFeatureWriteEvent` to propagate invalidation to both the feature surface cache and the planning browser cache. The modal uses `TabStateView` as a rendering wrapper for all section tabs. `featureSurfaceV2Enabled` flag gates v1/legacy path. |

---

## Additional Consumers Found

### 7. `services/useFeatureSurface.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/useFeatureSurface.ts` |
| Line range (types) | L35–148 |
| Line range (hook) | L265–end |
| Data dependency | `FeatureCardDTO[]`, `Map<string, FeatureRollupDTO>`, pagination state, load state, query parameters |
| Summary vs Full Forensics | **Summary only** — fetches board card list and batch rollup metrics. No session transcripts, tool calls, or `sessionForensics` fields. |
| Consumer type | **Direct API consumer** — orchestrates `listFeatureCards` + `getFeatureRollups` from `featureSurface.ts`. Injects `defaultFeatureSurfaceCache` adapter from `featureSurfaceCache.ts`. |
| Notes | Two-phase fetch: (1) `listFeatureCards` to get paginated `FeatureCardDTO[]`, (2) `getFeatureRollups` for the current page's IDs. Returns `{ cards, rollups, total, hasMore, query, listState, rollupState, setQuery, invalidate, prefetch }`. Consumed by `ProjectBoard.tsx`, `Dashboard.tsx`, `FeatureExecutionWorkbench.tsx`. |

---

### 8. `components/featureCardAdapters.ts`

| Aspect | Detail |
|--------|--------|
| File | `components/featureCardAdapters.ts` |
| Line range | L1–249 |
| Data dependency | `FeatureCardDTO`, `FeatureRollupDTO`, `FeatureRollupBucketDTO` |
| Summary vs Full Forensics | **Summary only** — adapts card/rollup DTOs to the legacy `Feature` interface used by `FeatureCard`/`FeatureListCard` components. Projects `FeatureRollupDTO` into `RollupSessionSummary` (aggregate session counts, token totals, workflow type buckets). |
| Consumer type | **Props** — pure transformation functions, not a React component or hook. Receives `FeatureCardDTO`/`FeatureRollupDTO` from callers. |
| Notes | Three exported adapters: `rollupToSessionSummary` (rollup → session badge metrics), `cardDTOToFeature` (card → legacy `Feature` shape), `cardDTOBoardStage` (card → board column key), `rollupLinkedDocCount` (rollup → linked-doc count). Consumed exclusively by `ProjectBoard.tsx`. |

---

### 9. `components/Dashboard.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/Dashboard.tsx` |
| Line range (import) | L13 |
| Line range (hook call) | L70 |
| Line range (render) | L207+ |
| Data dependency | `FeatureCardDTO[]`, `Map<string, FeatureRollupDTO>` (via `useFeatureSurface`), aggregate counts for summary tiles |
| Summary vs Full Forensics | **Summary only** — renders aggregate feature counts and high-level status breakdown. No session detail. |
| Consumer type | **Direct API consumer** (via `useFeatureSurface`) |
| Notes | Uses `useFeatureSurface` for the "Feature Surface Summary" section. Receives `cards` and `rollups` but renders only aggregate counts — total features, status distribution. No per-feature deep dive on this page. |

---

### 10. `components/SessionInspector.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/SessionInspector.tsx` |
| Line range (imports) | L39 |
| Line range (forensics tab) | L2730–3768 |
| Line range (features tab — getLegacyFeatureDetail) | L4705–4735 |
| Line range (SessionForensicsView component) | L3176–3768 |
| Data dependency | `session.sessionForensics` (`Record<string, any>`) including sub-fields: `thinking`, `entryContext`, `sidecars`, `queuePressure`, `resourceFootprint`, `subagentTopology`, `toolResultIntensity`, `platformTelemetry`, `codexPayloadSignals`, `testExecution`. Also calls `getLegacyFeatureDetail` (features tab) and `getFeatureLinkedSessionPage` (per-feature sessions). |
| Summary vs Full Forensics | **Full forensics** — the Forensics tab (`session.sessionForensics`) is the primary consumer of the full forensic blob. Renders all sub-fields including thinking level, entry context, sidecar telemetry, queue pressure, subagent topology, and tool result intensity. Session transcript full content is rendered in the Transcript tab. |
| Consumer type | **Direct API consumer** — calls `getLegacyFeatureDetail<Feature>` per feature (features tab, gated behind `activeTab === 'features'`), `getFeatureLinkedSessionPage` (session cross-navigation). Receives `session: AgentSession` (with `sessionForensics` blob) via props/context from the session detail route. |
| Notes | `SessionForensicsView` (defined inline, L3176–3768) is the full forensics renderer. The `forensics` tab type is a named `SessionInspectorTab` value. Raw JSON dump of the entire `sessionForensics` blob rendered at L3768 as a debug fallback. Features tab (L4705) uses per-feature `getLegacyFeatureDetail` fan-out (P5-001 TODO: replace with `useFeatureSurface` extension). |

---

### 11. `components/SessionInspector/TranscriptView.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/SessionInspector/TranscriptView.tsx` |
| Line range (imports) | L22 |
| Line range (SessionForensicsView equivalent) | L2722–2770+ |
| Data dependency | `session.sessionForensics` sub-fields: `thinking`, `entryContext`, `sidecars`, `resourceFootprint`, `queuePressure`, `subagentTopology`, `toolResultIntensity`, `platformTelemetry`. Also imports `getFeatureLinkedSessionPage` and `LinkedFeatureSessionDTO`. |
| Summary vs Full Forensics | **Full forensics** — mirrors the forensics rendering logic in `SessionInspector.tsx` for the transcript-adjacent context. |
| Consumer type | **Props** for `sessionForensics` (passed in as part of the `session` prop). **Direct API consumer** for `getFeatureLinkedSessionPage` (cross-navigation from session to feature session list). |
| Notes | Shares the `SessionInspectorTab` type definition with `SessionInspector.tsx` (L29, L34). This component duplicates the forensics sub-field destructuring pattern found in `SessionInspector.tsx`. Candidate for consolidation when separating forensics from planning contexts. |

---

### 12. `components/FeatureExecutionWorkbench.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/FeatureExecutionWorkbench.tsx` |
| Line range (imports) | L62–65 |
| Line range (useFeatureSurface call) | L611 |
| Line range (getLegacyFeatureDetail call) | L1205 |
| Data dependency | `FeatureCardDTO[]` (feature picker auto-select via `surfaceCards`), `FeatureRollupDTO` (optional metrics). Direct `getLegacyFeatureDetail<Feature>` call for the selected feature's full shape. |
| Summary vs Full Forensics | **Mixed** — board summary via `useFeatureSurface` (card list + rollups). Full feature detail via `getLegacyFeatureDetail` for the execution workbench form. No `sessionForensics` blob accessed. |
| Consumer type | **Direct API consumer** — calls both `useFeatureSurface` and `getLegacyFeatureDetail`. |
| Notes | Uses `useFeatureSurface` for the feature picker to auto-select the active feature. Fetches full feature detail on selection via `getLegacyFeatureDetail`. Session data not consumed directly here — sessions are accessed through the linked sessions panel inside the workbench. |

---

### 13. `services/planning.ts`

| Aspect | Detail |
|--------|--------|
| File | `services/planning.ts` |
| Line range (import) | L40 |
| Line range (bus subscription) | L315–319 |
| Line range (tokenTelemetry adapter) | L491, L1055 |
| Data dependency | `FeatureWriteEvent` (via `subscribeToFeatureWrites`). Wire `token_telemetry` field adapted to `PlanningTokenTelemetry` for `ProjectPlanningSummary`. |
| Summary vs Full Forensics | **Summary only** — `tokenTelemetry` is an aggregate metric (`totalTokens`, `byModelFamily[]`, `source`). No session-level detail. |
| Consumer type | **Indirect** — subscribes to the feature-write bus (not feature surface API). Receives `FeatureWriteEvent` and clears the planning browser cache for the affected project. |
| Notes | Planning cache (`PLANNING_BROWSER_CACHE`) is evicted on feature writes via `clearPlanningBrowserCache(event.projectId)`. The `token_telemetry` wire field is adapted at L1055 as part of the planning summary response adapter (not a forensics-specific path). This coupling is the source of the planning/forensics boundary conflict identified in the PRD. |

---

### 14. `components/Planning/PlanningMetricsStrip.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/Planning/PlanningMetricsStrip.tsx` |
| Line range (tokenTelemetry usage) | L116, L327, L335 |
| Data dependency | `summary.tokenTelemetry: PlanningTokenTelemetry | null` from `ProjectPlanningSummary` |
| Summary vs Full Forensics | **Summary only** — renders formatted total token count and "unavailable" fallback tile from `tokenTelemetry`. |
| Consumer type | **Props** — receives `summary: ProjectPlanningSummary` from parent (PlanningHomePage or similar). |
| Notes | Two render paths gated by `tokenTelemetry` presence and `source !== 'unavailable'`. `data-testid="token-telemetry"` and `data-testid="token-telemetry-unavailable"` are tested in `planningMetricsStrip.test.tsx`. This component is the main planning surface consumer of the forensics-derived token aggregate field. |

---

### 15. `contexts/AppRuntimeContext.tsx`

| Aspect | Detail |
|--------|--------|
| File | `contexts/AppRuntimeContext.tsx` |
| Line range (import) | L8 |
| Line range (flag derivation) | L72 |
| Line range (polling gate) | L162, L208, L243 |
| Data dependency | `featureSurfaceV2Enabled` boolean from runtime health payload (via `isFeatureSurfaceV2Enabled`) |
| Summary vs Full Forensics | **Infrastructure only** — flag gates which polling path is active. No feature content. |
| Consumer type | **Indirect** — reads runtime health status to expose `featureSurfaceV2Active` boolean. Downstream consumers (`ProjectBoard`, `Dashboard`, `FeatureExecutionWorkbench`) read this flag to choose the v1 vs legacy data path. |
| Notes | `featureSurfaceV2Active` is provided in context and consumed by components that call `isFeatureSurfaceV2Enabled(runtimeStatus)`. When `featureSurfaceV2Active` is true, polling for legacy `features` is skipped — `useFeatureSurface` owns all refresh. |

---

### 16. `components/BlockingFeatureList.tsx`

| Aspect | Detail |
|--------|--------|
| File | `components/BlockingFeatureList.tsx` |
| Line range (type import) | L5 |
| Line range (prop type) | L15–20 |
| Line range (usage commentary) | L55 |
| Data dependency | `FeatureCardDTO` (optional `featureCard?: FeatureCardDTO | null` prop) — reads `qualitySignals`, `dependencyState` |
| Summary vs Full Forensics | **Summary only** — reads quality signal counts and dependency state from the card DTO. |
| Consumer type | **Props** — receives `featureCard` optionally. Falls back to the legacy `Feature` shape when not provided. |
| Notes | Added in P4-009 to support the unified feature surface path. The `featureCard` prop provides quality signals and dependency state without a separate per-feature fetch. |

---

## Data Boundary Summary

| Data Category | Summary Consumers | Full Forensics Consumers |
|---------------|-------------------|--------------------------|
| Feature card metrics (status, task counts, coverage) | `featureSurface.ts`, `useFeatureSurface.ts`, `featureCardAdapters.ts`, `ProjectBoard.tsx`, `Dashboard.tsx`, `BlockingFeatureList.tsx` | — |
| Rollup aggregates (session counts, token totals, model families) | `featureSurface.ts`, `useFeatureSurface.ts`, `featureCardAdapters.ts`, `ProjectBoard.tsx`, `Dashboard.tsx` | — |
| Linked session list (metadata: status, model, cost, reasons) | `useFeatureModalData.ts`, `ProjectBoard.tsx`, `SessionInspector.tsx`, `TranscriptView.tsx`, `FeatureExecutionWorkbench.tsx` | — |
| Modal section items (phases, docs, relations, test-status, history) | `useFeatureModalData.ts`, `ProjectBoard.tsx` | — |
| Token telemetry (aggregate totals, by-model breakdown) | `planning.ts`, `PlanningMetricsStrip.tsx` | — |
| `sessionForensics` blob (thinking, entryContext, sidecars, queuePressure, subagentTopology, toolResultIntensity, platformTelemetry) | — | `SessionInspector.tsx`, `TranscriptView.tsx` |
| Full session transcripts / message-level detail | — | `SessionInspector.tsx`, `TranscriptView.tsx` |
| Per-feature full detail (`getLegacyFeatureDetail`) | — | `SessionInspector.tsx` (features tab, fan-out), `FeatureExecutionWorkbench.tsx` (workbench form) |

### Key Observations for Boundary Extraction

1. **Clean boundary exists** between the feature surface summary layer (`featureSurface.ts`, `useFeatureSurface.ts`, `useFeatureModalData.ts`) and the session forensics layer (`SessionInspector.tsx`, `TranscriptView.tsx`). No planning component directly touches `sessionForensics`.

2. **tokenTelemetry coupling** in `planning.ts` (L491, L1055) is the primary cross-boundary field — it is a forensics-derived aggregate surfaced on `ProjectPlanningSummary`. Extraction candidate: move this to a dedicated forensics-summary adapter or separate query.

3. **featureCacheBus is already a clean seam** — `planning.ts` subscribes to the bus without importing any `featureSurface` DTOs. This pattern is safe to keep post-refactor.

4. **`getLegacyFeatureDetail` fan-out in `SessionInspector.tsx`** (L4732, features tab) is marked as a TODO (P5-001) — should be replaced with a `useFeatureSurface` extension to remove the direct legacy endpoint coupling from the forensics view.

5. **`TranscriptView.tsx` duplicates forensics rendering** from `SessionInspector.tsx` — consolidation is a prerequisite or co-deliverable for any forensics boundary refactor.
