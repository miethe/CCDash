---
title: 'Implementation Plan: CCDash Planning Reskin v2 Interaction and Performance
  Addendum'
schema_version: 2
doc_type: implementation_plan
status: in-progress
created: '2026-04-21'
updated: '2026-04-21'
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_version: v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
scope: Planning-page follow-up for in-page modal navigation, active-first cached loading,
  missing metric wiring, tracker/intake side-panel behavior, and agent roster detail
  interactions.
effort_estimate: 30-38 story points
architecture_summary: 'Six focused phases: route-local modal orchestration, planning
  query/cache tightening, metric and density wiring, tracker/intake side panel, agent
  roster details, and verification/performance gates.'
related_documents:
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
- docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
- docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
- docs/guides/planning-control-plane-guide.md
references:
  user_docs: []
  context:
  - components/Planning/PlanningHomePage.tsx
  - components/Planning/TrackerIntakePanel.tsx
  - components/Planning/PlanningAgentRosterPanel.tsx
  - components/Planning/PlanningRouteLayout.tsx
  - components/ProjectBoard.tsx
  - components/DocumentModal.tsx
  - services/planning.ts
  - services/planningRoutes.ts
  - backend/application/services/agent_queries/planning.py
  - backend/application/services/agent_queries/cache.py
  specs: []
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
parent_feature_slug: ccdash-planning-reskin-v2
test_plan_ref: null
plan_structure: unified
progress_init: manual
owner: platform-engineering
contributors: []
priority: high
risk_level: medium
category: enhancements
tags:
- implementation
- planning
- ui
- caching
- interactions
- agents
files_affected:
- components/Planning/PlanningHomePage.tsx
- components/Planning/PlanningMetricsStrip.tsx
- components/Planning/TrackerIntakePanel.tsx
- components/Planning/PlanningAgentRosterPanel.tsx
- components/Planning/PlanningRouteLayout.tsx
- components/Planning/PlanningGraphPanel.tsx
- components/Planning/PlanningSummaryPanel.tsx
- components/ProjectBoard.tsx
- components/DocumentModal.tsx
- services/planning.ts
- services/planningRoutes.ts
- types.ts
- backend/application/services/agent_queries/planning.py
- backend/application/services/agent_queries/cache.py
- backend/routers/api.py
- backend/routers/features.py
- backend/tests/test_planning_query_service.py
- services/__tests__/planning.test.ts
- components/Planning/__tests__/planningHomePage.test.tsx
- components/Planning/__tests__/planningHomePageNavigation.test.tsx
---

# Implementation Plan: CCDash Planning Reskin v2 Interaction and Performance Addendum

**Plan ID**: `IMPL-2026-04-21-ccdash-planning-reskin-v2-interaction-performance-addendum`
**Parent Effort**: `ccdash-planning-reskin-v2`
**Complexity**: Medium
**Target Timeline**: 1.5-2.5 weeks with frontend/backend parallelization

## Executive Summary

The v2 planning reskin has the right visual direction, but several interaction and data-loading details still behave like a cross-page prototype. This addendum tightens the planning page into a true control-plane surface:

1. Feature, tracker, roster, and artifact clicks should first resolve inside `/planning` through a modal, side panel, or nested route. Navigation to `/board`, `/sessions`, `/artifacts`, or `/planning/feature/:id` should be an explicit secondary action.
2. Initial page load should be active-first and cache-aware. Summary state should be warm from a bounded browser cache, graph/detail payloads should load lazily, and backend cache fingerprints must include every data source used by planning queries.
3. Placeholder metrics must become real data or explicit unavailable states. Token tracker, ctx/phase, density, feature status filters, and status count math must be wired to canonical payload fields.
4. Tracker/Intake and Agent Roster rows must open contextual detail surfaces in place, not bounce the operator to another page.

## Current Code Findings

1. `PlanningHomePage` sends feature clicks to `planningFeatureModalHref(featureId)`, which currently resolves to `/board?feature=...`. This directly violates the modal-first planning interaction.
2. `TrackerIntakePanel` row clicks currently resolve a document and open `DocumentModal`; feature-context rows still use the same board navigation callback.
3. `PlanningAgentRosterPanel` displays `session.agentId` before `session.title`, even though backend session hydration already derives subagent type from `subagent_start` or task-tool metadata.
4. `PlanningRouteLayout` stores density preference and sets CSS variables, but many planning rows still hard-code padding/gaps/heights, so the selector has limited visible effect.
5. `PlanningMetricsStrip` mixes overlapping feature status counts. `total`, `active`, `blocked`, `stale`, `mismatches`, and `completed` are not mutually exclusive, so users read them as a broken sum.
6. Backend planning summary is memoized, but it still loads all feature and document rows and builds graph evidence for each feature. The existing cache fingerprint covers sessions/features only; planning reads documents too, so document-only changes can be stale while full loads are still expensive.

## Product Requirements

### R1: Modal-First Planning Navigation

Nearly all planning-page clicks must keep the operator on `/planning` initially.

1. Clicking a feature opens the shared feature modal in the planning route.
2. The feature modal includes explicit links/buttons for:
   - expand to `/planning/feature/:featureId`
   - open on `/board?feature=...`
   - open execution workbench if applicable
3. Clicking a planning artifact opens `DocumentModal` in place.
4. Clicking an artifact composition group may navigate to `/planning/artifacts/:type` because that is a nested planning page; rows inside it still open `DocumentModal`.
5. No primary click in the planning home, tracker/intake panel, summary panel, graph, or roster should navigate away from `/planning`.

### R2: Active-First Cached Loading

The planning home should not need full graph/detail payloads before it can render.

1. Render a lightweight summary first, then hydrate graph, tracker, and detail panels lazily.
2. Prioritize `in-progress`, `review`, `blocked`, `draft`, and `approved` features before terminal `done`, `completed`, `closed`, `deferred`, or `superseded` items.
3. Add bounded browser cache with stale-while-revalidate semantics:
   - scope by project id and planning data freshness
   - keep only summary/facet/list payloads in memory
   - cap cached projects and payload count to avoid long-lived memory growth
4. Backend cache fingerprints must include every planning input source used by each query: features, feature phases, documents, sessions, entity links, and any planning status/writeback tables touched by that query.
5. Large detail payloads (`feature context`, `full graph`, `phase operations`) load only on open, hover prefetch, or explicit expansion.

### R3: Metric Wiring and Filters

The planning metrics strip must distinguish health signals from mutually exclusive status buckets.

1. Replace heuristic token-saved and ctx/phase values with backend fields, or render an explicit unavailable state with no fake percentage.
2. Add `statusCounts` to the summary payload with mutually exclusive canonical buckets:
   - shaping
   - planned
   - active
   - blocked
   - review
   - completed
   - deferred
   - stale_or_mismatched
3. Keep health signals (`blocked`, `stale`, `mismatch`) visually distinct from status totals so the numbers are not expected to add to total unless labeled as buckets.
4. Every feature status count is clickable and applies a planning-page filter.
5. The current filter is reflected in the URL or route state so browser back/forward restores it.
6. Density mode changes visible row height, gaps, table padding, and compact metadata density across all planning list/table surfaces.

### R4: Tracker and Intake Side Panel

Tracker/Intake rows should open a side-panel quick view rather than the board feature modal.

1. Feature-like rows open a planning side panel with feature title, status evidence, linked artifacts, current phase, blockers, and next action.
2. Document-only rows open the document modal or a document side panel, depending on available metadata.
3. The side panel can promote to the full feature modal or full document modal without losing tab/filter state.
4. The side panel should reuse existing feature/document components where possible; do not create a second feature detail renderer unless the shared modal is too heavy for quick view.

### R5: Agent Roster Interactions and Identity

The roster should show agent type first, agent id second.

1. Roster height is pinned to match the Triage Inbox height at desktop breakpoints and becomes vertically scrollable inside the panel.
2. All planning sections that can overflow expose a consistent expand action that opens a larger modal.
3. Agent display name precedence:
   - `session.subagentType` or equivalent canonical metadata
   - `session.title` when it is a derived human label
   - `Orchestrator` for root/main sessions
   - `session.agentId` only as fallback
4. Agent id remains visible in tooltip/title and in the details modal.
5. Every roster row opens an agent detail modal with state, model, token/context utilization, linked session, parent/root session, linked feature, phase/task hints, files/artifacts when available, and navigation links.
6. Roster list rows include quick-view feature/phase/task hints when available from session metadata, linked feature APIs, or session-feature links.

## Phase Summary

Canonical orchestration table. Keep synced with detailed phase breakdowns below.

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 11 | Route-Local Modal Orchestration | 6-8 pts | ui-engineer-enhanced, frontend-developer | sonnet | Feature/artifact modal extraction, route state, deep-link support |
| 12 | Planning Query and Browser Cache Strategy | 7-9 pts | python-backend-engineer, react-performance-optimizer | sonnet | Summary/facet split, active-first loading, browser cache, prefetch |
| 13 | Metrics, Filters, and Density Wiring | 5-6 pts | ui-engineer-enhanced, python-backend-engineer | sonnet | Status counts, metric tiles, clickable filters, density modes |
| 14 | Tracker and Intake Side Panel | 5-6 pts | ui-engineer-enhanced, frontend-developer | sonnet | Quick-view panel, row resolution, promotion paths, state preservation |
| 15 | Agent Roster Details | 5-6 pts | frontend-developer, python-backend-engineer | sonnet | Canonical agent type, display precedence, detail modal, scrolling |
| 16 | Verification and Performance Gates | 6-7 pts | testing specialist, react-performance-optimizer, web-accessibility-checker | sonnet | Tests, cache behavior, load budgets, a11y regression, OTEL instrumentation |
| 17 | Documentation Finalization | 3-4 pts | changelog-generator, documentation-writer | haiku | CHANGELOG, parent plan updates, feature guide, context pointers |
| **Total** | — | **37-47 pts** | — | — | — |

---

## Implementation Phases

### Phase 11: Route-Local Modal Orchestration

**Estimate**: 6-8 pts
**Assigned Subagents**: `ui-engineer-enhanced`, `frontend-developer`
**Entry Criteria**: Parent plan phases 8-10 merged. Modal extraction infrastructure available.
**Exit Criteria**: All tasks in phase complete. Planning modal and side-panel surfaces open/close correctly. URL state preserved. Tests green.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P11-001 | Extract or wrap the `ProjectBoard` feature modal so `/planning` can host it without rendering the board page. | Planning can open a feature modal from summary, graph, and feature columns while URL remains under `/planning`. | sonnet | 2 pts |
| P11-002 | Replace `planningFeatureModalHref` primary usage with route-local modal state. | Primary feature clicks no longer navigate to `/board`. Existing explicit "Open board" links still work. | sonnet | 2 pts |
| P11-003 | Add planning modal route state, deep-link support, and back-button handling. | `/planning?feature=<id>&modal=feature` or equivalent opens the modal; browser back closes it before leaving planning. | sonnet | 2 pts |
| P11-004 | Normalize artifact click behavior around `DocumentModal`. | Artifact rows/chips open documents in place; nested `/planning/artifacts/:type` remains available for group drill-down. | sonnet | 2 pts |

### Phase 12: Planning Query and Browser Cache Strategy

**Estimate**: 7-9 pts
**Assigned Subagents**: `python-backend-engineer`, `react-performance-optimizer`
**Entry Criteria**: Phase 11 complete. Backend summary fields agreed upon.
**Exit Criteria**: All tasks in phase complete. Browser cache working with warm return <250ms. Cache invalidation covers all planning input tables. Tests green.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P12-001 | Split summary/facets from graph/detail payloads if current summary cannot meet budget. | Planning shell can render from a lightweight summary without building every graph synchronously. | sonnet | 2 pts |
| P12-002 | Add query params for active-first loading, terminal inclusion, and result limits. | Default home fetch prioritizes active/planned/blocked/review items; terminal features load on demand or after idle. | sonnet | 2 pts |
| P12-003 | Fix backend cache fingerprint coverage for planning queries. | Cache invalidates when documents, feature phases, sessions, or entity links change, not only feature/session timestamps. | sonnet | 2 pts |
| P12-004 | Add frontend bounded stale-while-revalidate cache for planning summary/facets. | Returning to `/planning` renders warm state immediately and refreshes in background. Cache has bounded keys and payload types. | sonnet | 2 pts |
| P12-005 | Add hover/open prefetch for feature context and roster/session details. | Opening a recently hovered feature/agent is near-instant without preloading every detail payload. | sonnet | 1 pt |

### Phase 13: Metrics, Filters, and Density Wiring

**Estimate**: 5-6 pts
**Assigned Subagents**: `ui-engineer-enhanced`, `python-backend-engineer`
**Entry Criteria**: Phase 12 complete. Summary payload includes `statusCounts`, `ctxPerPhase`, token telemetry fields.
**Exit Criteria**: All tasks in phase complete. Metric tiles show real data. Filters clickable and reflected in route state. Density changes visible across surfaces. Tests green.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P13-001 | Add summary fields for `statusCounts`, `ctxPerPhase`, and token telemetry availability. | UI consumes real fields; no fabricated token-saved or ctx/phase values remain. | sonnet | 2 pts |
| P13-002 | Rework metric tiles into status buckets plus health signals. | Status buckets add to total; health signals are labeled as overlays/signals. | sonnet | 1.5 pts |
| P13-003 | Make each metric tile clickable. | Clicking a count filters planning lists/graph; filter is reflected in route state and can be cleared. | sonnet | 1 pt |
| P13-004 | Apply density variables across lists, rows, tracker tabs, graph rows, and roster. | Comfortable vs compact changes visible density consistently and is covered by component tests. | sonnet | 1.5 pts |

### Phase 14: Tracker and Intake Side Panel

**Estimate**: 5-6 pts
**Assigned Subagents**: `ui-engineer-enhanced`, `frontend-developer`
**Entry Criteria**: Phase 11 modal orchestration complete. Route-local state infrastructure in place.
**Exit Criteria**: All tasks in phase complete. Quick-view panel opens/closes correctly. State preserved across open/close. Tests green.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P14-001 | Add `PlanningQuickViewPanel` for tracker/intake rows. | Row click opens a right-side panel in `/planning`; focus is trapped and restorable. | sonnet | 2 pts |
| P14-002 | Resolve node row click target as feature-first when `featureSlug` exists, doc-first otherwise. | Feature rows show feature quick view; standalone docs show document quick view/modal. | sonnet | 1.5 pts |
| P14-003 | Add promotion paths from quick view. | Quick view can open full feature modal, full document modal, or expanded nested planning page. | sonnet | 1 pt |
| P14-004 | Preserve tab/filter state across quick-view open/close. | Closing a panel returns to the same tracker tab and scroll position. | sonnet | 1 pt |

### Phase 15: Agent Roster Details

**Estimate**: 5-6 pts
**Assigned Subagents**: `frontend-developer`, `python-backend-engineer`
**Entry Criteria**: Phase 11 complete. Agent session hydration with type metadata available from backend.
**Exit Criteria**: All tasks in phase complete. Roster displays agent types correctly. Detail modal functional. Quick-view hints displayed where available. Tests green.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P15-001 | Add canonical `subagentType` or `displayAgentType` to `AgentSession`. | Frontend does not parse human title strings to infer agent type. | sonnet | 2 pts |
| P15-002 | Change roster name precedence and root-session label. | Subagents show type labels; main/root sessions show `Orchestrator`; ids appear only as tooltip/detail fallback. | sonnet | 1 pt |
| P15-003 | Pin roster height to triage height and add internal scrolling. | Roster and triage align at desktop; long roster scrolls inside its panel. | sonnet | 1 pt |
| P15-004 | Add roster row detail modal. | Clicking any row opens agent details with links to session, feature, phase/task context, parent/root session, model, token/context data. | sonnet | 1.5 pts |
| P15-005 | Link roster rows to feature/phase quick-view data. | Roster rows show compact feature/phase/task hints when available; missing metadata has a neutral empty state. | sonnet | 1 pt |

### Phase 16: Verification and Performance Gates

**Estimate**: 6-7 pts
**Assigned Subagents**: `testing specialist`, `react-performance-optimizer`, `web-accessibility-checker`
**Entry Criteria**: Phases 11-15 feature-complete. All code integrated.
**Exit Criteria**: All tasks in phase complete. Test suite green. Load budgets met. A11y regression coverage in place. OTEL instrumentation complete. QA pass.

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P16-001 | Add frontend tests for modal-first navigation. | Tests assert planning clicks do not navigate to `/board` unless the explicit board link is clicked. | sonnet | 1.5 pts |
| P16-002 | Add cache and lazy-load tests. | Tests cover warm render, stale revalidation, bounded cache eviction, and detail-only-on-open behavior. | sonnet | 1.5 pts |
| P16-003 | Add backend tests for planning summary fields and cache invalidation. | Tests cover `statusCounts`, ctx/phase fields, token availability, active-first filtering, and document-driven invalidation. | sonnet | 1.5 pts |
| P16-004 | Add roster and tracker interaction tests. | Tests cover side panel, row modal, agent naming precedence, and scroll-height behavior. | sonnet | 1 pt |
| P16-005 | Measure load budgets. | Warm planning return renders summary in under 250ms in component-level timing; cold local p95 target remains under 2s for summary shell before graph hydration. | sonnet | 1.5 pts |
| P16-006 | A11y regression for new modal/panel surfaces. | Focus trap on `PlanningQuickViewPanel`, agent detail modal, route-local feature modal; ARIA roles; keyboard-close on all three. | sonnet | 1 pt |
| P16-007 | Add OTEL spans on new planning query params and cache fingerprint paths. | Instrument service methods added in P12-001, P12-002, P12-003, P15-001 with observability context. | sonnet | 1 pt |

## Data Contracts

### Project Planning Summary Additions

Add or verify these fields on `ProjectPlanningSummaryDTO` and `ProjectPlanningSummary`:

```ts
statusCounts: {
  shaping: number;
  planned: number;
  active: number;
  blocked: number;
  review: number;
  completed: number;
  deferred: number;
  staleOrMismatched: number;
};
ctxPerPhase?: {
  contextCount: number;
  phaseCount: number;
  ratio: number | null;
  source: "backend" | "unavailable";
};
tokenTelemetry?: {
  totalTokens: number | null;
  byModelFamily: Array<{ modelFamily: string; totalTokens: number }>;
  source: "session_attribution" | "unavailable";
};
```

### Agent Session Additions

Add or verify these fields on `AgentSession`:

```ts
subagentType?: string;
displayAgentType?: string;
linkedFeatureIds?: string[];
phaseHints?: string[];
taskHints?: string[];
```

Backend derivation should reuse the existing `_subagent_type_from_logs` logic and expose the value directly instead of forcing roster display to infer from `title` or `agentId`.

## Acceptance Criteria

1. Clicking any feature on `/planning` opens an in-page feature modal or side panel first; it does not immediately navigate to `/board`.
2. Clicking tracker/intake rows opens the side-panel quick view for feature-like rows and document modal/quick view for document-only rows.
3. Agent roster rows are clickable and open an agent detail modal.
4. Roster names show subagent type or `Orchestrator` before falling back to agent id.
5. Roster panel height aligns with Triage Inbox and scrolls internally when rows overflow.
6. Planning summary renders from cached browser state when revisiting the page, then revalidates in background.
7. Backend planning cache invalidates on changes to all planning input tables, including documents and feature phases.
8. Graph/detail payloads are lazy-loaded rather than required for first meaningful planning render.
9. Token tracker and ctx/phase either show real backend data or an explicit unavailable state; no heuristic/fake telemetry remains.
10. Feature status buckets are mutually exclusive and clickable; health signals are visually separated from status totals.
11. Density selector visibly changes all major planning list/table surfaces.
12. New tests cover navigation, caching, data contract fields, tracker side panel, roster modal, and density behavior.

## Deferred Items & In-Flight Findings Policy

### Deferred Items Triage Table

N/A — no deferred items identified at planning time. All scope and technical prerequisites are in-flight across parent plan phases 8-10 (currently open). When findings emerge during execution, follow the lazy-findings-creation rule: first finding triggers `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum-findings.md` (path follows `.claude/findings/[feature-slug]-findings.md` convention).

### In-Flight Findings

Lazy-creation rule: Findings doc created on **first real finding only**. Path: `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum-findings.md`.

---

## Out of Scope

1. Redesigning `/board`, `/plans`, `/sessions`, or `/artifacts` globally.
2. Building a new feature-detail system unrelated to the existing board modal.
3. Implementing SSE streaming beyond existing live invalidation.
4. Loading all completed/closed feature details into browser memory for offline browsing.
5. Replacing the existing agent query cache foundation.

### Phase 17: Documentation Finalization

**Estimate**: 3-4 pts
**Assigned Subagents**: `changelog-generator`, `documentation-writer`
**Entry Criteria**: Phase 16 verification complete. All code merged.
**Exit Criteria**: CHANGELOG `[Unreleased]` entry finalized. Parent plan updated if needed. Feature guide authored. Context pointers added. Documentation merged.

#### Objectives

1. Capture user-facing changes in CHANGELOG `[Unreleased]` section.
2. Update parent plan's Phase Summary / related_documents if needed.
3. Author feature guide summarizing new surfaces and interaction patterns.
4. Add context pointers to CLAUDE.md or key-context if new agent-facing patterns introduced.

#### Tasks

| Task | Description | Acceptance Criteria | Model | Effort |
| --- | --- | --- | --- | --- |
| P17-001 | CHANGELOG `[Unreleased]` entry | Add entries for modal-first navigation, active-first loading, metric/filter wiring, quick-view panels, roster detail interactions. Group under `Changed` (if behavior changes) or `Added` (if new surfaces). | haiku | 1 pt |
| P17-002 | Update parent plan references | Review parent plan's Phase Summary table and related_documents; add addendum reference if not already present. | haiku | 0.5 pts |
| P17-003 | Author feature guide | Create `.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md` summarizing new modal orchestration, quick-view panel, agent detail modal, metric tiles, and density modes. | haiku | 1.5 pts |
| P17-004 | Context and CLAUDE.md pointers | If new interaction patterns or caching strategies introduced agent-facing behavior, add brief pointers to CLAUDE.md or key-context files (Progressive Disclosure: one-liner + path reference only). | haiku | 0.5 pts |

**Phase 17 Quality Gates:**
- [ ] CHANGELOG `[Unreleased]` entry complete and linked to PR
- [ ] Parent plan updated with addendum reference
- [ ] Feature guide complete with all new surfaces documented
- [ ] Context files updated if new agent-facing patterns introduced
- [ ] Documentation merged to main

---

## Suggested Execution Order

1. Phase 12 backend summary/cache contract work can run in parallel with Phase 11 modal extraction.
2. Phase 13 should start after the summary fields are agreed, but density wiring can proceed independently.
3. Phase 14 depends on route-local modal/panel orchestration from Phase 11.
4. Phase 15 can proceed in parallel once agent session display fields are exposed.
5. Phase 16 runs throughout, with final performance measurement after all lazy-loading changes land.
6. Phase 17 (documentation) begins after Phase 16 verification is complete.

### Sequencing Risk

Addendum Phase 11 (modal orchestration) touches `PlanningHomePage.tsx` and `PlanningRouteLayout.tsx`, files also targeted by parent plan phases 8-10 (currently open). Confirm parent phases 8-10 are merged before Phase 11 begins to avoid divergent edits on the same files.
