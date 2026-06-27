---
schema_version: 2
doc_type: phase_plan
title: "CCDash FE Data Layer Refactor — P0–P2: Foundation, Sessions Slice & Remaining Domains"
status: draft
created: 2026-05-28
updated: 2026-05-28
phase: "0-2"
phase_title: "Foundation and Domains"
feature_slug: ccdash-frontend-data-layer-refactor
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
entry_criteria:
  - "@tanstack/react-query ^5.x available in package registry (same vendor as react-virtual already installed)"
  - "Vitest test suite passes on main branch"
exit_criteria:
  - "P0: TQ mounted; app renders identically; guardrail scaffold present; vitest run green; runtime smoke all routes"
  - "P1: Sessions on TQ; one cold-load session fetch (was 2); back-nav no spinner; useData() sessions facade intact"
  - "P2: All 6 entity domains on TQ; tasks/features paginated; limit=5000 gone from entity contexts; runtime smoke PlanCatalog + ProjectBoard"
integration_owner: null
---

# Phase 0–2: Foundation, Sessions Slice & Remaining Domains

**Parent Plan**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
**Phases**: P0 (2 pts), P1 (3 pts), P2 (5 pts) — total 10 pts
**Primary Agent**: ui-engineer-enhanced
**Secondary Agent** (P2): frontend-developer (parallel domain batches)

---

## Phase 0: TQ Foundation & Guardrails

**Duration**: ~1 day
**Dependencies**: None
**Assigned Subagent(s)**: ui-engineer-enhanced
**Model / Effort**: sonnet / adaptive
**Risk**: Low — library install with clear scope

### Context

Install `@tanstack/react-query` v5 and wire the `QueryClientProvider` above the existing `DataProvider` in `App.tsx`. Author `lib/queryClient.ts` (staleTime/gcTime/retry defaults) and `services/queryKeys.ts` (centralized key registry). Add devtools flag. Extend existing source-reading guardrail tests to permit TQ imports and ban new hand-rolled LRU/TTL patterns. Zero domains migrated yet — app must render identically.

**Inventory refs**:
- `App.tsx` — provider mount point (inventory-frontend.md §2, provider tree)
- `contexts/__tests__/dataArchitecture.test.ts:10-30` — guardrail pattern to extend (inventory-priorart.md §3)
- `components/__tests__/ProjectBoardEagerLoop.test.tsx:266-297` — banned-symbol source-read pattern to copy (inventory-priorart.md §3)

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T0-001 | Install @tanstack/react-query | Run `npm install @tanstack/react-query@^5`. Verify no peer-dep conflicts with existing `@tanstack/react-virtual@^3`. Update `package.json` and lock file. | `package.json` shows `@tanstack/react-query ^5.x`; `npm install` succeeds; no peer-dep warnings. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | None |
| T0-002 | Author lib/queryClient.ts | Create `lib/queryClient.ts` exporting a `QueryClient` factory with project defaults: `staleTime: 30_000`, `gcTime: 300_000`, `retry: (count, err) => count < 3 && err.status !== 4xx`, `refetchOnWindowFocus: false`. Export `createProjectQueryClient(projectId: string)` that calls `queryClient.clear()` on project switch. | File exists at `lib/queryClient.ts`; factory returns correctly configured `QueryClient`; unit test asserts default `staleTime` and retry behavior. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-001 |
| T0-003 | Author services/queryKeys.ts | Create `services/queryKeys.ts` centralizing all query key factories: `sessionsKeys`, `documentsKeys`, `tasksKeys`, `featuresKeys`, `alertsKeys`, `notificationsKeys`, `planningKeys`, `dashboardKeys`. Each factory accepts `projectId` as first param. No inline string keys anywhere. | File exists; all key factories exported; existing `vitest` guardrail extended to assert no `useQuery(["..."])` inline string key in migrated hook files. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-001 |
| T0-004 | Mount QueryClientProvider in App.tsx | Wrap `DataProvider` in `App.tsx` with `QueryClientProvider client={queryClient}`. QueryClient is created once via `createProjectQueryClient(activeProject?.id ?? 'default')` and cleared on project switch. Auth gate preserved: `AppDataProviderGate` remains innermost gate. | `QueryClientProvider` appears above `DataProvider` in `App.tsx`; `contexts/__tests__/dataArchitecture.test.ts` extended to assert `QueryClientProvider` present above `DataProvider`; no `useQuery` fires before auth resolves. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-002, T0-003 |
| T0-005 | Add ReactQueryDevtools flag | Add `@tanstack/react-query-devtools` (devDependency). Mount `<ReactQueryDevtools>` gated by `VITE_CCDASH_QUERY_DEVTOOLS=true` env var (build-time flag, default false). Gate reads `import.meta.env.VITE_CCDASH_QUERY_DEVTOOLS` at call time, not module scope. | Devtools panel visible in browser when flag is true; not bundled in production build (devDependency); flag follows VITE env convention from inventory-priorart.md §5. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-004 |
| T0-006 | Extend guardrail tests | In `contexts/__tests__/dataArchitecture.test.ts` and a new `services/__tests__/noHandRolledCache.test.ts`: add source-reading assertions that ban `new Map()` + TTL patterns in `services/` and `contexts/` (post-migration), assert no `useEffect(fetch)` in context providers, and permit `@tanstack/react-query` imports. Copy banned-symbol pattern from `components/__tests__/ProjectBoardEagerLoop.test.tsx:266-297` (inventory-priorart.md §3). | Two guardrail test files updated/created; `vitest run` green. Initially all assertions pass because no migration has occurred yet — the tests will catch regressions in later phases. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-004 |
| T0-007 | Runtime smoke: all routes | Boot dev server (`npm run dev`). Navigate to Dashboard, SessionInspector, PlanCatalog, ProjectBoard, Planning, Analytics, Settings. Verify app renders identically to pre-TQ baseline with no console errors from the new provider. | All routes load without error; no visible UI regressions; browser console clean of TQ errors. **If runtime unavailable, record `runtime_smoke: skipped` + reason; phase cannot be marked `completed` without this or an explicit skip record.** | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T0-005, T0-006 |
| T0-008 | task-completion-validator gate (P0) | Run `task-completion-validator` to verify P0 exit criteria: TQ mounted, guardrails present, app renders identically, vitest green. | Validator passes; P0 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T0-007 |

**Phase 0 Quality Gates:**
- [ ] `@tanstack/react-query ^5.x` in `package.json`; no peer-dep conflicts
- [ ] `lib/queryClient.ts` and `services/queryKeys.ts` authored
- [ ] `QueryClientProvider` mounted above `DataProvider` in `App.tsx`
- [ ] `dataArchitecture.test.ts` extended; `noHandRolledCache.test.ts` created; `vitest run` green
- [ ] Runtime smoke: all routes render without error or regression
- [ ] `task-completion-validator` sign-off

---

## Phase 1: Sessions Vertical Slice (Canonical Pattern)

**Duration**: 1–2 days
**Dependencies**: P0 complete
**Assigned Subagent(s)**: ui-engineer-enhanced
**Model / Effort**: sonnet / extended (canonical pattern — worth deeper reasoning so replication is clean)
**Risk**: Low-medium — sets the pattern all later phases copy

### Context

Migrate sessions end-to-end: `useSessionsQuery` + `useSessionDetailQuery` hooks, remove the **duplicate** cold-load session fetch (`AppEntityDataContext.tsx:111` fires before `AppRuntimeContext.refreshAll` at line 221 — two `GET /api/sessions` calls on cold load). Back-navigation must render from TQ cache with no spinner. Resolve OQ-1 (useInfiniteQuery vs offset pagination for session list). Keep `useData().sessions` facade returning the same shape throughout.

**Inventory refs**:
- `contexts/AppEntityDataContext.tsx:111` — duplicate `refreshSessions(true)` call (inventory-frontend.md §1, §7 note 1)
- `contexts/AppRuntimeContext.tsx:221` — `refreshAll()` fires second session fetch (inventory-frontend.md §1)
- `components/SessionInspector.tsx:3952,4578,5376` — session list consumer (inventory-frontend.md §3)
- `components/Dashboard.tsx:150` — sessions consumer (inventory-frontend.md §3)
- `components/Planning/PlanningAgentSessionBoard.tsx:1164` — sessions consumer (inventory-frontend.md §3)
- `services/apiClient.ts:getSessions` — `GET /api/sessions?offset&limit&sort_by=started_at&sort_order=desc` (inventory-frontend.md §4)

### OQ-1 Resolution

**Decision**: Use `useInfiniteQuery` for the session list (matches existing "Load more" UX pattern; avoids page-number state). `loadMoreSessions` consumers replace `loadMoreSessions()` call with `fetchNextPage()`. Session detail stays `useQuery`.

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T1-001 | Author useSessionsQuery hook | Create `services/queries/sessions.ts` with `useSessionsQuery(projectId, filters)` using `useInfiniteQuery`. Key: `sessionsKeys.list(projectId, filters)`. `staleTime: 30_000`. `getNextPageParam` from response `total` + current offset. `enabled: !!projectId && !!authResolved`. Returns `{ data, isLoading, isFetching, fetchNextPage, hasNextPage, error }`. | Hook file at `services/queries/sessions.ts`; unit test (Vitest + fetch-spy) asserts one `GET /api/sessions` on mount; asserts `fetchNextPage` increments offset. | 1 pt | ui-engineer-enhanced | sonnet | extended | T0-003 |
| T1-002 | Author useSessionDetailQuery hook | Add `useSessionDetailQuery(sessionId)` in `services/queries/sessions.ts` using `useQuery`. Key: `sessionsKeys.detail(sessionId)`. `staleTime: 30_000`, `gcTime: 300_000`. Replaces bespoke `sessionDetailRequestsRef` / `sessionDetailTimestampsRef` Map TTL in `AppEntityDataContext.tsx` (inventory-frontend.md §1). | Hook exported; unit test asserts deduplicated concurrent calls produce one fetch; `sessionDetailRequestsRef` pattern removed from context file. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T1-001 |
| T1-003 | Migrate session consumers to hooks | Update `components/SessionInspector.tsx`, `components/Dashboard.tsx`, `components/Planning/PlanningAgentSessionBoard.tsx` to call `useSessionsQuery` / `useSessionDetailQuery` directly instead of `useData().sessions`. `useData().sessions` facade reads from TQ cache (thin shim). Remove `AppEntityDataContext.tsx:111` duplicate `refreshSessions(true)`. | Cold load issues exactly one `GET /api/sessions` call (verified by fetch spy); `useData().sessions` still returns session data (shim); `AppEntityDataContext.tsx:111` line removed. | 1 pt | ui-engineer-enhanced | sonnet | extended | T1-001, T1-002 |
| T1-004 | Back-navigation cache verification | Write Vitest test: mount SessionInspector → navigate away (via router simulation) → navigate back → assert `fetch` was NOT called on second mount (data came from TQ cache). Warm-cache threshold: within `gcTime` window (5 min default). | Test passes: zero additional `GET /api/sessions` calls on warm back-nav. | 0.5 pts | ui-engineer-enhanced | sonnet | extended | T1-003 |

**AC-A2 (from PRD): Sessions domain migrated, duplicate fetch eliminated**
- target_surfaces:
    - `contexts/AppEntityDataContext.tsx` (duplicate fetch removed at line 111)
    - `components/SessionInspector.tsx` (consumer migrated to hook)
    - `components/Dashboard.tsx` (consumer migrated)
    - `components/Planning/PlanningAgentSessionBoard.tsx` (consumer migrated)
- propagation_contract: `useSessionsQuery` returns `{ data, isLoading, isFetching, error }`; consumers replace `sessions` array with `data?.pages.flatMap(p => p.items) ?? []`
- resilience: `data` undefined on first load renders existing empty-state UI; no change to error boundary
- visual_evidence_required: DevTools network screenshot showing single `/api/sessions` call on cold load
- verified_by: T1-003 (fetch-spy), T1-004 (back-nav test), T1-005 (smoke)

**AC-A3 (from PRD): Back-navigation renders from cache**
- target_surfaces:
    - `components/SessionInspector.tsx`
    - `components/Dashboard.tsx`
- resilience: If TQ cache empty (first visit or post-clear), loading state shown — same as baseline
- visual_evidence_required: false (covered by fetch-spy count assertion in T1-004)
- verified_by: T1-004

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T1-005 | Runtime smoke: Dashboard + SessionInspector | Boot dev server. Navigate to Dashboard — verify session list loads. Navigate to SessionInspector — verify session list and detail load. Navigate away and back — verify no spinner on back-nav. Check browser DevTools: single `/api/sessions` call on cold load. | Smoke passes: ≤1 session network call on cold load; no spinner on back-nav within warm window. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T1-003, T1-004 |
| T1-006 | task-completion-validator gate (P1) | Validate P1 exit criteria: one cold-load session fetch, back-nav from cache, facade preserved, AC-A2 + AC-A3 met. | Validator passes; P1 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T1-005 |

**Phase 1 Quality Gates:**
- [ ] `useSessionsQuery` (infinite) + `useSessionDetailQuery` (query) hooks authored in `services/queries/sessions.ts`
- [ ] `AppEntityDataContext.tsx:111` duplicate `refreshSessions(true)` removed
- [ ] `SessionInspector`, `Dashboard`, `PlanningAgentSessionBoard` consuming hook directly
- [ ] `useData().sessions` facade still returns session data (shim from TQ cache)
- [ ] Fetch-spy test: 1 cold-load session call; 0 on warm back-nav
- [ ] Runtime smoke: Dashboard + SessionInspector — AC-A2, AC-A3 verified
- [ ] `task-completion-validator` sign-off

---

## Phase 2: Remaining Entity Domains

**Duration**: 2–3 days
**Dependencies**: P1 complete
**Assigned Subagent(s)**: ui-engineer-enhanced (primary), frontend-developer (parallel domain batches)
**Model / Effort**: sonnet / adaptive (mechanical replication of the P1 pattern)
**Risk**: Low — follows the established P1 hook pattern; main risk is pagination semantics for tasks/features

### Context

Migrate documents, tasks, features, alerts, notifications, and projects to TQ hooks, replicating the P1 pattern. **Critical**: tasks and features must move off `limit=5000` (inventory-frontend.md §4, `apiClient.ts:401,413`). Tasks use offset pagination (page size 100); features use the existing `GET /api/v1/features?view=cards&page=N` paginated endpoint. Audit consumers that reduce the full client list to counts or filters before paginating — those consumers must source aggregate counts from summary/card DTOs instead.

**Parallel batching**: Six domains split by file ownership — run as two parallel batches:
- **Batch A** (ui-engineer-enhanced): documents, tasks, features
- **Batch B** (frontend-developer): alerts, notifications, projects

**Inventory refs**:
- `services/apiClient.ts:401,413` — `limit=5000` calls (inventory-frontend.md §4)
- `components/PlanCatalog.tsx:278` — documents consumer (inventory-frontend.md §3)
- `components/ProjectBoard.tsx:1072,3134` — features consumer (inventory-frontend.md §3)
- `components/OpsPanel.tsx:268` — ALL domains consumer (inventory-frontend.md §3)
- `components/Settings.tsx:955,1206,1946,2876` — alerts, projects consumer (inventory-frontend.md §3)
- `components/Layout.tsx:288` — notifications consumer (inventory-frontend.md §3)

### Batch A: Documents, Tasks, Features

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T2-001 | useDocumentsQuery hook | Create `services/queries/documents.ts`. Use `useInfiniteQuery`; key `documentsKeys.list(projectId, offset)`; `staleTime: 60_000`; page size 500 (matching existing `MAX_DOCUMENTS_IN_MEMORY` cap via `select` transform). `enabled: !!projectId && !!authResolved`. | Hook file; unit test asserts paginated fetch; documents page size 500; `MAX_DOCUMENTS_IN_MEMORY=2000` cap applied via TQ `select`. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T1-006 |
| T2-002 | Migrate document consumers | Update `PlanCatalog.tsx`, `Planning/TrackerIntakePanel.tsx`, `Planning/ArtifactDrillDownPage.tsx`, `Planning/PlanningGraphPanel.tsx`, `Planning/PlanningNodeDetail.tsx`, `FeatureExecutionWorkbench.tsx`, `DocumentModal.tsx` to consume `useDocumentsQuery`. `useData().documents` facade reads from TQ cache. | Consumers updated; `useData().documents` shim works; `vitest run` green. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-001 |
| T2-003 | useTasksQuery hook (paginated) | Create `services/queries/tasks.ts`. Use `useQuery` with offset pagination (page 100). Key `tasksKeys.list(projectId, page)`. Remove `limit=5000` from `apiClient.getTasks()` (or add a new `getTasksPaginated` method). Audit `OpsPanel.tsx:268` which consumes ALL tasks — port to paginated with total count from response meta. | Hook file; `apiClient.ts:401` `limit=5000` gone; `OpsPanel` uses paginated response; source-reading guardrail asserts `limit=5000` absent from `services/`. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T1-006 |
| T2-004 | useFeaturesQuery hook (paginated) | Create `services/queries/features.ts`. Use `useQuery` keyed on `featuresKeys.list(projectId, query, page)`. Wire onto existing `GET /api/v1/features?view=cards&page=N` paginated endpoint. Remove `limit=5000` from `apiClient.getFeatures()`. `ProjectBoard.tsx` legacy path switches to paginated. | Hook file; `apiClient.ts:413` `limit=5000` gone; `ProjectBoard` legacy path paginated; source-reading guardrail asserts no `limit=5000` in `services/` and `contexts/`. | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T1-006 |

**AC-C2 partial (limit=5000 elimination for tasks + features)**
- target_surfaces:
    - `services/apiClient.ts` (getTasks, getFeatures methods updated — lines 401, 413)
    - `services/queries/tasks.ts` (new paginated query)
    - `services/queries/features.ts` (updated to v1 paginated endpoint)
    - `components/OpsPanel.tsx` (all-task consumer updated to paginated shape)
- propagation_contract: Paginated shape `{ items: T[], total: number, page: number, pageSize: number }`; consumers read `items` not the full array
- resilience: `OpsPanel` and `Settings` handle paginated `items + total` shape; `total` displayed as count; `items` used for list render
- visual_evidence_required: false
- verified_by: T2-003, T2-004, T2-011 (smoke)

### Batch B: Alerts, Notifications, Projects

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T2-005 | useAlertsQuery + useNotificationsQuery hooks | Create `services/queries/alerts.ts` and `services/queries/notifications.ts`. Use `useQuery`; `staleTime: 30_000`; port the 30s polling interval from `AppRuntimeContext.tsx:225` to `refetchInterval: 30_000` on each query. `enabled: !!projectId`. | Two hook files; `refetchInterval: 30_000` set; unit test asserts `getAlerts` called on mount + re-called after 30s mock timer. | 0.5 pts | frontend-developer | sonnet | adaptive | T1-006 |
| T2-006 | useProjectsQuery hook | Create `services/queries/projects.ts`. Use `useQuery`; `staleTime: 300_000` (projects rarely change). `AppSessionContext` continues to own `activeProject` and `switchProject` client-state. | Hook file; `AppSessionContext` still exposes `activeProject` (client-state only); `refreshProjects` backed by TQ `invalidateQueries`. | 0.5 pts | frontend-developer | sonnet | adaptive | T1-006 |
| T2-007 | Migrate alerts, notifications, projects consumers | Update `Settings.tsx`, `Layout.tsx` for alerts/notifications; `ProjectSelector.tsx` for projects. All read from TQ hooks. `useData()` facade shim updated for each. | Consumers updated; `useData()` facade intact; `vitest run` green. | 0.5 pts | frontend-developer | sonnet | adaptive | T2-005, T2-006 |

### Integration & Validation

**AC-B1 partial (all entity domains migrated to TQ — entity domain subset)**
- target_surfaces:
    - `contexts/AppEntityDataContext.tsx` (entity state section — server arrays progressively emptied as hooks take over)
    - `services/queries/documents.ts`
    - `services/queries/tasks.ts`
    - `services/queries/features.ts`
    - `services/queries/alerts.ts`
    - `services/queries/notifications.ts`
    - `services/queries/projects.ts` (via AppSessionContext refactor)
- propagation_contract: Each domain hook returns `{ data: T | undefined, isLoading, error }`; `useData()` facade reads from hooks
- resilience: Each domain hook returns `data: undefined` on first load; consumers render existing empty-state patterns unchanged
- visual_evidence_required: false
- verified_by: T2-008, T2-009, T2-010, T2-011

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T2-008 | Update noHandRolledCache guardrail | Extend `services/__tests__/noHandRolledCache.test.ts` to assert absence of `new Map()` + TTL patterns in all newly migrated query hook files. Assert `limit=5000` string absent from `services/` and `contexts/`. | Guardrail assertions cover all 6 domain hook files; `vitest run` green. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-007 |
| T2-009 | Seam task: P2 entity domain integration | Verify `useData()` facade exports the correct shape for all 6 migrated domains. Run `contexts/__tests__/dataArchitecture.test.ts` — confirm all required `useData()` fields still present. | `dataArchitecture.test.ts` green; no `useData()` field regressions after 6-domain migration. This is the cross-owner seam task (ui-engineer-enhanced + frontend-developer) verifying the facade contract. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-007 |
| T2-010 | Runtime smoke: PlanCatalog + ProjectBoard | Boot dev server. Navigate to PlanCatalog — verify document list loads, no `limit=5000` call in DevTools. Navigate to ProjectBoard — verify features load paginated (v2 surface shows cards; legacy path shows paginated list). Check alerts visible in Layout header. | Smoke passes: no `limit=5000` in network; PlanCatalog and ProjectBoard render without regression. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-008, T2-009 |
| T2-011 | task-completion-validator gate (P2) | Validate P2 exit criteria: all 6 domains on TQ; `limit=5000` gone from entity contexts; `useData()` facade intact; guardrail tests green; smoke passed. | Validator passes; P2 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T2-010 |

**Phase 2 Quality Gates:**
- [ ] 6 domain query hook files created in `services/queries/`
- [ ] `limit=5000` removed from `services/apiClient.ts` methods (lines 401, 413); tasks + features paginated
- [ ] `OpsPanel` and `Settings` updated for paginated task/feature shape
- [ ] `useData()` facade shim returns all 6 domain arrays from TQ cache (seam task T2-009 verified)
- [ ] `noHandRolledCache.test.ts` guardrail green for all 6 domain hook files
- [ ] Source-reading guardrail asserts `limit=5000` absent
- [ ] Runtime smoke: PlanCatalog + ProjectBoard render without regression
- [ ] `task-completion-validator` sign-off (P2)
