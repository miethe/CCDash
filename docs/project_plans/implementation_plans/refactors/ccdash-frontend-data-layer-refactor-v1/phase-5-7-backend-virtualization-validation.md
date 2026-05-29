---
schema_version: 2
doc_type: phase_plan
title: "CCDash FE Data Layer Refactor — P5–P7: Backend Bundles, Virtualization & Validation"
status: draft
created: 2026-05-28
updated: 2026-05-28
phase: "5-7"
phase_title: "Backend Virtualization and Validation"
feature_slug: ccdash-frontend-data-layer-refactor
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
entry_criteria:
  - "P0 complete (P5 backend can start from P0)"
  - "P2 complete (P6 virtualization can start from P2)"
  - "P4 complete (P5 FE wiring starts after P4)"
exit_criteria:
  - "P5: Three bundle endpoints ship; FE consumes; ≤1 above-fold request per view"
  - "P6: Three lists virtualized; smooth scroll at scale; memory-guard interplay verified"
  - "P7: All guardrail tests green; docs updated; Epic D entry-criteria spec authored; CHANGELOG updated; karen end-of-feature passed"
integration_owner: ui-engineer-enhanced
---

# Phase 5–7: Backend Bundles, Virtualization & Validation

**Parent Plan**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
**Phases**: P5 (6 pts), P6 (3 pts), P7 (3 pts) — total 12 pts
**Parallelization**: P5 backend starts after P0; P6 starts after P2; both parallelize against P3/P4

> **R-P3 (P5 integration_owner declared)**: P5 involves both `python-backend-engineer` (BE endpoints) and `ui-engineer-enhanced` (FE wiring) with shared files in `services/queries/dashboard.ts` and `components/Dashboard.tsx`. `ui-engineer-enhanced` is declared `integration_owner` for the FE wiring seam.

---

## Phase 5: Backend Fat-Read Bundles + Waterfall Collapse

**Duration**: 3–4 days (spread across P2–P4 in parallel for backend portion)
**Dependencies**: P0 (backend); P4 + P5a backend (FE wiring)
**Assigned Subagent(s)**: python-backend-engineer (P5a backend), ui-engineer-enhanced (P5b FE wiring)
**Model / Effort**: sonnet / adaptive
**Risk**: Medium — bundle endpoints compose already-cached reads at near-zero extra DB cost; risk is FE waterfall regression if wiring incomplete

### Context

Three bundle endpoints reduce above-fold request count to ≤1 per view. All backend logic lands in `backend/application/services/agent_queries/` first (transport-neutral pattern per CLAUDE.md), then wired into `backend/routers/`. Follow the precedent of `GET /api/agent/planning/summary` (inventory-backend.md §2) and `GET /api/v1/features/{id}/modal` (inventory-backend.md §2).

**P5a (backend, starts after P0, parallel to P2/P3/P4)**:
- `GET /api/v1/dashboard` — sessions page (limit 20, desc) + task counts by status
- `GET /api/agent/planning/view?include=graph,session_board` — composing planning summary, graph, session board
- `GET /api/analytics/overview-bundle` — above-fold analytics data

**P5b (FE wiring, starts after P4 + P5a endpoint ships)**:
- Wire `useDashboardBundleQuery`, `usePlanningViewQuery`, `useAnalyticsOverviewQuery` onto bundle endpoints
- Update `Dashboard.tsx`, `PlanningHomePage.tsx`, `AnalyticsDashboard.tsx` to consume bundle queries
- Implement `include=` opt-in for heavy planning sub-payloads

**OQ-5 Resolution**: Confirmed — bundle endpoints compose existing cached `agent_queries` reads (same pattern as `planning.summary` helpers at `planning.py:787-857`); no new `agent_queries` methods needed. DTOs are composition of existing DTOs.

**Inventory refs**:
- `backend/application/services/agent_queries/planning.py:787-857` — `_build_status_counts/_ctx_per_phase/_token_telemetry` helpers (inventory-backend.md §2)
- `backend/routers/client_v1.py:265` — `FeatureModalOverviewDTO` bundle pattern (inventory-backend.md §2)
- `backend/application/services/agent_queries/cache.py:50` — `@memoized_query` TTLCache (inventory-backend.md §4)
- `backend/observability/otel.py` — OTEL spans for new routes

### P5a Backend Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T5-001 | Dashboard agent_queries service | Create `backend/application/services/agent_queries/dashboard.py`. Add `get_dashboard_bundle(project_id) -> DashboardBundleDTO` composing: `sessions_page` (limit 20, sorted `started_at` desc) from `SessionsRepository`, `task_counts` (by status) from `TasksRepository`. Wrap with `@memoized_query` (10s TTL — live counts). DTO: `DashboardBundleDTO(sessions: list[SessionCardDTO], task_counts: dict[str, int])`. | `dashboard.py` created; `DashboardBundleDTO` in `models.py`; pytest: route returns both sessions and task_counts; `@memoized_query` applied; OTEL span added via `backend/observability/otel.py`. | 1 pt | python-backend-engineer | sonnet | adaptive | T0-008 |
| T5-002 | Dashboard router endpoint | Wire `GET /api/v1/dashboard` in `backend/routers/client_v1.py`. Returns `ClientV1Envelope[DashboardBundleDTO]`. Auth: same guard as other `/api/v1/` routes. OTEL: span name `ccdash.dashboard.bundle`. | Route registered; pytest integration test asserts response contains `sessions` list and `task_counts` dict; `meta` envelope present; existing `/api/v1/` auth pattern followed. | 0.5 pts | python-backend-engineer | sonnet | adaptive | T5-001 |
| T5-003 | Planning view bundle endpoint | Add `get_planning_view_bundle(project_id, include: list[str]) -> PlanningViewBundleDTO` in `backend/application/services/agent_queries/planning.py`. Compose existing `planning.summary`, optionally `planning.graph`, optionally `planning_sessions.session_board` based on `include=` param. Wire `GET /api/agent/planning/view?include=graph,session_board` in `backend/routers/agent.py`. | `GET /api/agent/planning/view` returns summary always; adds graph + session_board when `include=` param specifies them; pytest asserts with and without `include`; `@memoized_query` on each sub-method (already present). | 1.5 pts | python-backend-engineer | sonnet | adaptive | T0-008 |
| T5-004 | Analytics overview bundle endpoint | Add `get_analytics_overview_bundle(project_id) -> AnalyticsOverviewBundleDTO` in `backend/application/services/agent_queries/` (new or extend analytics). Wire `GET /api/analytics/overview-bundle` in `backend/routers/analytics.py`. Above-fold data only — tabs remain lazy. | Route returns analytics above-fold data; pytest integration test; OTEL span; tabs (detailed breakdowns) remain separate lazy endpoints. | 1 pt | python-backend-engineer | sonnet | adaptive | T0-008 |

**AC-R-P2 (resilience ACs for new backend fields)**:
- `DashboardBundleDTO.task_counts` missing → FE `useDashboardBundleQuery` returns `taskCounts ?? {}`; Dashboard count badges show 0
- `DashboardBundleDTO.sessions` missing → FE returns `sessions ?? []`; Dashboard session list shows empty state
- `PlanningViewBundleDTO` graph sub-payload missing (when not in `include=`) → FE planning graph panel shows "loading" until explicitly requested
- verified_by: T5-006 (FE resilience assertions)

### P5b FE Wiring Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T5-005 | Author useDashboardBundleQuery | Create `services/queries/dashboard.ts` with `useDashboardBundleQuery(projectId)` using `useQuery`. Key: `dashboardKeys.bundle(projectId)`. `staleTime: 10_000` (matches backend live-count TTL). `enabled: !!projectId && isOnDashboardRoute`. Returns `{ sessions, taskCounts, isLoading, error }`. | Hook file at `services/queries/dashboard.ts`; unit test: mocks `GET /api/v1/dashboard` response; asserts `sessions` and `taskCounts` fields populated; asserts missing `taskCounts` returns `{}`. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T5-002, T4-010 |
| T5-006 | Wire Dashboard to bundle query | Update `components/Dashboard.tsx` to consume `useDashboardBundleQuery` instead of separate `useSessionsQuery` + `useTasksQuery`. Cold Dashboard load now issues exactly one `GET /api/v1/dashboard` request. Add resilience: `taskCounts ?? {}`, `sessions ?? []`. | Dashboard cold load: 1 network call (`GET /api/v1/dashboard`); fetch-spy test asserts no separate `GET /api/sessions` or `GET /api/tasks` calls from Dashboard; `taskCounts` missing handled. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T5-005 |
| T5-007 | Wire Planning to view bundle | Add `usePlanningViewQuery(projectId, { includeGraph, includeSessionBoard })` in `services/queries/planning.ts` using `useQuery` keyed on `planningKeys.view(projectId, include)`. Wire to `GET /api/agent/planning/view?include=`. Planning page issues one above-fold call; graph/session-board loaded on demand via `enabled` + `include=` refinement. | Planning page cold load: 1 network call; `include=graph` adds graph; `include=session_board` adds board; unit test asserts correct `include=` query param construction. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T5-003, T4-010 |
| T5-008 | Seam task: P5 integration (BE endpoint + FE wiring) | Verify bundle endpoint integration: boot dev server, navigate to Dashboard — assert DevTools shows single `/api/v1/dashboard` call; navigate to Planning — assert single `/api/agent/planning/view` call. Verify resilience: temporarily mock missing `taskCounts` field — assert Dashboard renders without error, count badges show 0. **R-P3 cross-owner seam**: python-backend-engineer (endpoint) × ui-engineer-enhanced (TQ wiring) seam verified here. | Seam test passes: 1 request per view; resilience to missing fields confirmed. | 0 pts | ui-engineer-enhanced | sonnet | adaptive | T5-007 |

**AC-C1: Dashboard bundle endpoint ships**
- target_surfaces:
    - `backend/application/services/agent_queries/dashboard.py` (new)
    - `backend/routers/client_v1.py` (new route)
    - `services/queries/dashboard.ts` (new TQ query)
    - `components/Dashboard.tsx`
- propagation_contract: `useDashboardBundleQuery` returns `{ sessions, taskCounts }`; `Dashboard.tsx` reads both fields
- resilience: FE handles missing `taskCounts` with `taskCounts ?? {}`; handles missing `sessions` with `sessions ?? []`
- visual_evidence_required: Network waterfall screenshot showing single `/api/v1/dashboard` call on Dashboard cold load
- verified_by: T5-006 (fetch-spy), T5-008 (seam), T5-009 (smoke)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T5-009 | Runtime smoke: Dashboard + Planning + Analytics (P5) | Boot dev server. Navigate to Dashboard — verify single `/api/v1/dashboard` call in DevTools. Navigate to Planning — verify single `planning/view` call. Navigate to Analytics — verify overview-bundle call. Check bundle payloads complete. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | Smoke passes: 1 above-fold call per view; all bundle payloads render correctly. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T5-008 |
| T5-010 | task-completion-validator gate (P5) | Validate P5 exit criteria: 3 bundle endpoints ship; FE consumes; Dashboard + Planning ≤1 above-fold request. | Validator passes; P5 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T5-009 |

**Phase 5 Quality Gates:**
- [ ] `backend/application/services/agent_queries/dashboard.py` created with `DashboardBundleDTO`
- [ ] `GET /api/v1/dashboard` route in `client_v1.py` registered; pytest integration test passing
- [ ] `GET /api/agent/planning/view?include=` endpoint; pytest passing
- [ ] `GET /api/analytics/overview-bundle` endpoint; pytest passing
- [ ] `services/queries/dashboard.ts` — `useDashboardBundleQuery` with resilience for missing fields
- [ ] Dashboard cold load: 1 network request; fetch-spy confirmed
- [ ] Planning cold load: 1 network request
- [ ] Resilience ACs: missing `taskCounts`/`sessions` handled
- [ ] `task-completion-validator` sign-off (P5)

---

## Phase 6: List Virtualization

**Duration**: 1–2 days (parallelized with P4/P5 after P2 complete)
**Dependencies**: P2 complete (domain hooks exist for list data); P1 for session list hook
**Assigned Subagent(s)**: ui-engineer-enhanced
**Model / Effort**: sonnet / adaptive (`@tanstack/react-virtual` already installed as a dependency)
**Risk**: Medium — scroll-position loss on back-nav; virtualizer container height = 0 edge case

### Context

Virtualize three large list surfaces using `useVirtualizer` from `@tanstack/react-virtual` (already installed via `TranscriptView.tsx:2448` and `icon-picker.tsx:203` — inventory-frontend.md §6). Session list is NOT currently virtualized despite the import being present (`SessionInspector.tsx:2` imports it but `SessionInspector.tsx:5856-5901` uses plain `.map()` — inventory-frontend.md §6).

**Inventory refs**:
- `components/SessionInspector.tsx:5856-5901` — `pastSessionThreadRoots.map` + `pastSessions.map` (inventory-frontend.md §6)
- `components/PlanCatalog.tsx` — `documents.map()` on up to 2000 entries (inventory-frontend.md §6)
- `components/ProjectBoard.tsx` legacy path — `features.map()` on up to 5000 entries (inventory-frontend.md §6)
- `components/SessionInspector/TranscriptView.tsx:2448` — `useVirtualizer` pattern to copy (inventory-frontend.md §6)
- `contexts/dataContextShared.ts:55` — `mergeSessionDetail` ring-buffer (memory guard interplay)

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T6-001 | Virtualize session list in SessionInspector | Apply `useVirtualizer` to `pastSessionThreadRoots.map(renderThreadNode)` and `pastSessions.map(...)` at `components/SessionInspector.tsx:5856-5901`. Copy pattern from `TranscriptView.tsx:2448`. Container requires explicit height (CSS). Preserve scroll position on back-nav: store `virtualizer.scrollOffset` in TQ query meta on unmount; restore via `initialOffset` on mount. Fallback: if container height = 0, cap `.map()` at 200 items + log warning. | `pastSessionThreadRoots` and `pastSessions` lists use `useVirtualizer`; DOM has only visible-row `div`s (Vitest: `role="listitem"` count ≤ `overscan*2 + visibleCount`); scroll position restored on back-nav; 200-item fallback when height=0; `VITE_CCDASH_MEMORY_GUARD_ENABLED` interplay preserved (ring-buffer cap still applied at `mergeSessionDetail`). | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T2-011 |
| T6-002 | Virtualize document list in PlanCatalog | Apply `useVirtualizer` to `PlanCatalog.tsx` document list. Document count badge reads from TQ `useDocumentsQuery` `total` field (not `documents.length` from a full in-memory array — avoids needing all docs loaded for count display). Same fallback pattern as T6-001. | Document list uses `useVirtualizer`; count badge reads `total` from TQ query; DOM has only visible rows; Vitest render test asserts row count ≤ visible threshold; `MAX_DOCUMENTS_IN_MEMORY=2000` cap from TQ `select` transform preserved. | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T2-011 |
| T6-003 | Virtualize legacy feature list in ProjectBoard | Apply `useVirtualizer` to `components/ProjectBoard.tsx` legacy path (`features.map()` on up to 5000 entries). v2 surface already paginated 50/page — no change to v2 surface. Legacy path: virtualizer with `useFeaturesQuery` paginated data. | Legacy feature list uses `useVirtualizer`; v2 surface unchanged; DOM renders only visible rows; Vitest test asserts row count bounded. | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T2-011 |

**AC-C3: Session list virtualized in SessionInspector**
- target_surfaces:
    - `components/SessionInspector.tsx` (lines 5856-5901)
- propagation_contract: Virtualizer renders only visible rows; `useVirtualizer` consumes `useInfiniteQuery` flattened pages; scroll position stored in TQ query meta
- resilience: Container height = 0 → capped `.map()` render (200 items) with console warning
- visual_evidence_required: Runtime smoke screenshot showing session list in SessionInspector with >50 items rendering without layout thrash
- verified_by: T6-001 (Vitest row-count assertion), T6-004 (smoke)

**AC-C4: Document list virtualized in PlanCatalog**
- target_surfaces:
    - `components/PlanCatalog.tsx`
- propagation_contract: Same virtualizer pattern; `total` from TQ query drives count badge
- resilience: Same fallback as AC-C3
- visual_evidence_required: Runtime smoke screenshot showing PlanCatalog with ≥500 documents without scrollbar jank
- verified_by: T6-002 (Vitest), T6-004 (smoke)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T6-004 | Runtime smoke: SessionInspector + PlanCatalog + ProjectBoard (P6) | Boot dev server. Navigate to SessionInspector with a project containing >50 sessions — verify list renders without DOM thrash, scroll works. Navigate to PlanCatalog with >100 documents — verify smooth scroll. Navigate to ProjectBoard legacy path with >50 features — verify list renders. Check memory guard interplay: document pagination cap still enforced. **If runtime unavailable, record `runtime_smoke: skipped` + reason.** | Smoke passes: lists virtualized; scroll smooth; count badges correct; memory guard interplay confirmed. | 0 pts (included in smoke coverage) | ui-engineer-enhanced | sonnet | adaptive | T6-003 |
| T6-005 | task-completion-validator gate (P6) | Validate P6 exit criteria: 3 lists virtualized; smooth scroll at scale; memory-guard interplay verified; AC-C3, AC-C4 met. | Validator passes; P6 marked complete. | 0 pts | task-completion-validator | sonnet | adaptive | T6-004 |

**Phase 6 Quality Gates:**
- [ ] Session list in `SessionInspector.tsx:5856-5901` uses `useVirtualizer`
- [ ] Document list in `PlanCatalog.tsx` uses `useVirtualizer`; count badge reads `total` from TQ
- [ ] Legacy feature list in `ProjectBoard.tsx` uses `useVirtualizer`
- [ ] Vitest row-count assertions: DOM row count ≤ `overscan*2 + visibleCount`
- [ ] Scroll position restored on back-nav for session list
- [ ] Memory guard interplay: `MAX_DOCUMENTS_IN_MEMORY` and `mergeSessionDetail` ring-buffer still enforced
- [ ] Runtime smoke: all 3 virtualized lists
- [ ] `task-completion-validator` sign-off (P6)

---

## Phase 7: Validation, Docs & Epic D Scoping

**Duration**: 1–2 days
**Dependencies**: P4, P5, P6 all complete
**Assigned Subagent(s)**: documentation-writer (docs+CHANGELOG), documentation-complex (Epic D spec), ui-engineer-enhanced (guardrails+smoke)
**Model / Effort**: haiku / adaptive (docs+CHANGELOG); sonnet / adaptive (Epic D spec, guardrails, smoke)
**Risk**: Low — validation phase; Epic D is gating only, not execution

### Context

Run the full guardrail suite, comprehensive runtime smoke across all target surfaces, update `docs/guides/feature-surface-architecture.md` to reflect the two-layer cache model (server `@memoized_query` + client TQ), update CHANGELOG, and author the Epic D entry-criteria design spec + sub-plan stub. `karen` runs end-of-feature review.

**Inventory refs**:
- `docs/guides/feature-surface-architecture.md` — two-tier cache docs to update (inventory-priorart.md §1)
- `components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx` — full regression suite (inventory-priorart.md §3)
- `contexts/__tests__/dataArchitecture.test.ts` — guardrail (inventory-priorart.md §3)
- `services/__tests__/noHandRolledCache.test.ts` — guardrail (new file, T0-006)

### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T7-001 | Full guardrail suite | Run `vitest run` against the full suite: `noHandRolledCache.test.ts`, `dataArchitecture.test.ts`, `FeatureSurfaceRegressionMatrix.test.tsx`, `featureSurfaceDecoupling.test.ts`, `ProjectBoardEagerLoop.test.tsx`. All must be green. Fix any regressions before proceeding. | All guardrail and regression tests pass; `vitest run` exits 0; no skipped tests in the listed files. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T6-005 |
| T7-002 | Comprehensive runtime smoke (all surfaces) | Boot dev server. Navigate to all surfaces in the Phase Summary table `target_surfaces`: Dashboard, SessionInspector, PlanCatalog, ProjectBoard, Planning (Home, AgentSessionBoard, GraphPanel), FeatureModal, Analytics. Verify each renders without error or regression. Verify above-fold request count per view: Dashboard ≤1, Planning ≤1, Analytics ≤1. **If runtime unavailable, record `runtime_smoke: skipped` + reason; P7 cannot be marked `completed` without this.** | Comprehensive smoke passes: all surfaces functional; request counts meet targets; no JS errors; memory guard behaviors confirmed. | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T7-001 |
| T7-003 | Update feature-surface-architecture.md | Update `docs/guides/feature-surface-architecture.md` to reflect the new two-layer cache model: server-side `@memoized_query` (600s TTL, `backend/application/services/agent_queries/cache.py:50`) + client-side TQ `QueryClient` (30s–5min staleTime, configured in `lib/queryClient.ts`). Update hook API section: `useFeatureSurface` now TQ-backed. Remove references to LRU Map + featureCacheBus. Add queryKey registry reference (`services/queryKeys.ts`). | `feature-surface-architecture.md` updated; no references to removed files (`featureSurfaceCache.ts`, `featureCacheBus.ts`, `planning.ts` LRU Maps); two-layer model documented; hook API section current. | 0.5 pts | documentation-writer | haiku | adaptive | T7-002 |
| T7-004 | Update CHANGELOG [Unreleased] | Add CHANGELOG entry under `[Unreleased]` for: **Performance**: "Replaced three hand-rolled server-state caches with TanStack Query; back-navigation renders instantly from cache for all previously-visited routes." **Changed**: "Dashboard cold load reduced to 1 network request (was 8–9 parallel); tasks and features requests now paginated (no longer limit=5000)." **Improved**: "Session list, document list, and feature list virtualized via @tanstack/react-virtual." Follow `.claude/specs/changelog-spec.md` categorization rules. | CHANGELOG `[Unreleased]` section contains entries under `Performance`, `Changed`, and `Improved` categories; `.claude/specs/changelog-spec.md` rules followed; `changelog_ref` frontmatter in plan set to `CHANGELOG.md`. | 0.5 pts | documentation-writer | haiku | adaptive | T7-002 |
| T7-005 | Update CLAUDE.md context pointer | Add a one-liner pointer to CLAUDE.md under the frontend data layer section: `- **Frontend data layer**: All server state in TQ QueryClient; hooks in \`services/queries/\`; queryKey registry at \`services/queryKeys.ts\`; bundle endpoints in \`backend/application/services/agent_queries/\`. See \`docs/guides/feature-surface-architecture.md\`.` | CLAUDE.md updated with ≤3-line pointer; no full-content duplication; progressive disclosure pattern followed. | 0.5 pts | documentation-writer | haiku | adaptive | T7-003 |

**DOC-006: Epic D Entry-Criteria Design Spec (mandatory)**
- This task is the deferred-item spec authoring required by the Deferred Items section of the parent plan.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| T7-006 | DOC-006: Author Epic D entry-criteria design spec | Create `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md` with `maturity: shaping`, `doc_type: design_spec`, `prd_ref` pointing to the parent PRD. Content: enumerate AC-D1 entry criteria verbatim (from PRD §11 Epic D), document the three SSR blockers (`HashRouter` across ~30 files per inventory-priorart.md §4; `AppRuntimeContext.tsx:43` module-scope `window.location.hash` read; `window.location.assign` in `AuthSessionContext.tsx:192-193` safe). List preconditions: Epics A–C smoke-clean 14 days; sub-plan approved; `CCDASH_NEXTJS_ENABLED` flag defined. | Design spec file created at canonical path; `maturity: shaping`; `prd_ref` set; AC-D1 criteria enumerated; SSR blockers documented with file:line citations; `deferred_items_spec_refs` in parent plan frontmatter updated to include this path. | 0.5 pts | documentation-complex | sonnet | adaptive | T7-002 |
| T7-007 | DOC-006: Author ccdash-nextjs-migration-v1 sub-plan stub | Create `docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md` as a stub implementation plan. Frontmatter: `status: draft`, `prd_ref: null` (Epic D has no standalone PRD yet), note in body that execution is blocked until entry criteria in `ccdash-nextjs-migration-entry-criteria.md` are met. Body: one-paragraph scope description, SSR blocker list, entry-criteria gate reference. | Stub file created; clearly marked as requiring entry-criteria gate; `ccdash-nextjs-migration-entry-criteria.md` referenced; no implementation tasks added (those require a future PRD). | 0.5 pts | documentation-complex | sonnet | adaptive | T7-006 |
| T7-008 | Update plan frontmatter lifecycle fields | Set `status: completed`, populate `files_affected` list (final), `changelog_ref: CHANGELOG.md`, `deferred_items_spec_refs: [docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md]`, `updated: 2026-05-28` in the parent plan frontmatter. | Plan frontmatter complete; `deferred_items_spec_refs` populated; `findings_doc_ref` set or confirmed null; lifecycle fields updated. | 0.5 pts | documentation-writer | haiku | adaptive | T7-007 |
| T7-009 | Update planning skill SPEC | Check `.claude/specs/skills-index.md` — planning skill domain includes TQ migration patterns and bundle endpoint guidance. Update planning skill `SPEC.md` if the new two-layer cache model or queryKey registry pattern should appear in the Capability Coverage matrix. | `skills-index.md` checked; planning SPEC.md updated if applicable; otherwise documented as N/A. | 0.5 pts | ai-artifacts-engineer | sonnet | adaptive | T7-008 |
| T7-010 | karen end-of-feature review | Run `karen` end-of-feature review: verify all PRD ACs met (AC-A1–A3, AC-B1–B4, AC-C1–C4, AC-D1 gate only); verify all guardrail tests green; verify CHANGELOG entry present; verify Epic D gate doc authored; verify no deferred items missing spec. | karen review passes; all ACs confirmed; feature marked complete. | 0 pts | karen | sonnet | adaptive | T7-009 |
| T7-011 | task-completion-validator gate (P7) | Validate P7 exit criteria: all guardrails green; docs updated; Epic D entry-criteria spec authored; CHANGELOG updated; karen end-of-feature passed. | Validator passes; P7 marked complete; plan `status: completed`. | 0 pts | task-completion-validator | sonnet | adaptive | T7-010 |

**Phase 7 Quality Gates:**
- [ ] `vitest run` exits 0; all guardrail and regression test suites green
- [ ] Comprehensive runtime smoke: all 7 target surfaces pass
- [ ] `docs/guides/feature-surface-architecture.md` updated: two-layer cache model, no references to deleted files
- [ ] CHANGELOG `[Unreleased]` updated with Performance, Changed, and Improved entries
- [ ] CLAUDE.md updated with ≤3-line pointer to data layer
- [ ] `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md` authored (DOC-006)
- [ ] `docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md` stub created (DOC-006)
- [ ] `deferred_items_spec_refs` in parent plan frontmatter populated
- [ ] Plan frontmatter lifecycle fields complete (`status: completed`, `changelog_ref`, `files_affected`)
- [ ] Planning skill SPEC.md updated (or N/A documented)
- [ ] `karen` end-of-feature review passed
- [ ] `task-completion-validator` sign-off (P7)
