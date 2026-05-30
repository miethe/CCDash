---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: implementation_plan
status: draft
category: enhancements
title: "Implementation Plan: Multi-Project Planning Command Center V1"
description: "Phased implementation plan for all-project Planning Command Center scope, consolidated active-session board, project display metadata, route-local detail access, and performance validation."
summary: "Build backend aggregate planning endpoints, active-only cross-project session board services, project display metadata, frontend multi-project command-center mode, and validation gates."
created: 2026-05-29
updated: 2026-05-29
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Multi-Project Operations
timeline_estimate: "4-6 weeks across 7 phases"
feature_slug: multi-project-planning-command-center-v1
feature_family: planning-command-center
feature_version: v1
lineage_family: planning-command-center
lineage_parent:
  ref: docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md
  kind: extension_of
lineage_children: []
lineage_type: enhancement
owner: platform-engineering
owners:
  - platform-engineering
  - fullstack-engineering
  - ai-integrations
contributors:
  - ai-agents
audience:
  - ai-agents
  - developers
  - platform-engineering
  - engineering-leads
tags:
  - implementation
  - planning
  - command-center
  - multi-project
  - active-sessions
  - performance
prd_ref: docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
spike_ref: docs/project_plans/spikes/multi-project-planning-command-center-v1.md
related:
  - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
  - docs/project_plans/spikes/multi-project-planning-command-center-v1.md
  - docs/project_plans/PRDs/enhancements/planning-command-center-v1.md
  - docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md
  - docs/project_plans/PRDs/features/system-wide-metrics-v1.md
  - docs/project_plans/feature_contracts/features/live-agents-count-v1.md
  - docs/project_plans/feature_contracts/features/watcher-rebind-on-active-project-switch-v1.md
plan_ref: multi-project-planning-command-center-v1
effort_estimate: "28 pts"
plan_structure: unified
files_affected:
  - backend/models.py
  - backend/config.py
  - backend/application/services/agent_queries/multi_project_planning_command_center.py
  - backend/application/services/agent_queries/multi_project_planning_sessions.py
  - backend/application/services/agent_queries/planning_command_center.py
  - backend/application/services/agent_queries/planning_sessions.py
  - backend/db/repositories/sessions.py
  - backend/routers/agent.py
  - backend/routers/projects.py
  - services/multiProjectPlanningCommandCenter.ts
  - services/apiClient.ts
  - services/queries/planning.ts
  - services/queryKeys.ts
  - contexts/DataContext.tsx
  - types.ts
  - components/Planning/CommandCenter/
  - components/Planning/PlanningHomePage.tsx
  - components/Planning/PlanningAgentSessionBoard.tsx
  - components/ProjectSelector.tsx
---

# Implementation Plan: Multi-Project Planning Command Center V1

**Plan ID:** `IMPL-2026-05-29-MULTI-PROJECT-PLANNING-COMMAND-CENTER`
**Date:** 2026-05-29
**Author:** Codex Planning Agent
**Related Documents:**
- **PRD:** `docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md`
- **SPIKE:** `docs/project_plans/spikes/multi-project-planning-command-center-v1.md`
- **Parent V1:** `docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md`

**Complexity:** High
**Total Estimated Effort:** 28 pts
**Target Timeline:** 4-6 weeks

## Executive Summary

This plan extends Planning Command Center from a single-project cockpit into a high-performance all-project operations screen. The implementation adds backend aggregate endpoints, active-only cross-project session board services, project display metadata, frontend multi-project views, project-scoped detail modals, performance gates, and documentation.

The critical design rule is backend aggregation. The browser must not issue N project-board requests on page load, and the active-session board must avoid loading full project session boards for cold projects.

## Implementation Strategy

### Architecture Sequence

1. **DTO and project metadata layer** - aggregate DTOs, project display config, feature flag, query keys.
2. **Backend command-center aggregate** - cross-project work-item service and endpoint.
3. **Backend active-session aggregate** - active-only session repository/service and endpoint.
4. **Frontend data layer** - service adapters and TanStack Query hooks.
5. **Frontend UI layer** - consolidated board, project filters, project cards, modals.
6. **Performance and resilience** - cache, pagination, virtualization, perf tests.
7. **Docs and rollout** - guide, human brief, smoke, changelog, feature-flag rollout.

### Parallel Work Opportunities

- Phase 2 and Phase 3 can run after Phase 1 freezes DTOs because command work items and active-session cards have separate service modules.
- Phase 4 can start against mocked DTO fixtures while Phase 2/3 finish.
- Phase 5 UI components can split into project filters, active-session board, and work-item board with mostly disjoint file ownership.
- Phase 6 backend and frontend tests can run in parallel after API contracts are stable.

### Critical Path

Phase 1 -> Phase 2/3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7.

Phase 5 is blocked by Phase 4 service adapters. Phase 6 is the release gate because performance and project-scope tests are load-bearing.

## Phase Summary

| Phase | Title | Estimate | Assigned Subagent(s) | Notes |
|-------|-------|----------|----------------------|-------|
| 1 | Contract, Feature Flag, Project Display Metadata | 3 pts | backend-architect, python-backend-engineer, ui-designer | Freeze DTO shape and project identity model. |
| 2 | Cross-Project Command-Center Aggregate | 6 pts | backend-architect, python-backend-engineer | Reuse V1 resolver/item builders; no browser fan-out; page/lazy-enrich aggregate payloads. |
| 3 | Cross-Project Active-Session Board | 5 pts | python-backend-engineer, data-layer-expert | Add active-only session query and card aggregation. |
| 4 | Frontend Data Layer And Query State | 4 pts | frontend-developer | Move command center onto shared query hooks, then add aggregate adapters and URL state. |
| 5 | Multi-Project Planning UI | 5 pts | ui-engineer-enhanced, frontend-developer, ui-designer | Consolidated board, project rail, modals, card states. |
| 6 | Performance, Tests, Accessibility | 4 pts | react-performance-optimizer, web-accessibility-checker, testing specialist | Perf budgets and FE/BE seam gates. |
| 7 | Rollout, Docs, Runtime Smoke | 1 pt | documentation-writer, DevOps | Feature flag rollout and operator docs. |
| **Total** | - | **28 pts** | - | - |

## Phase 1: Contract, Feature Flag, Project Display Metadata

**Dependencies:** Completed SPIKE.
**Assigned Subagent(s):** backend-architect, python-backend-engineer, ui-designer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-101 | Aggregate DTO Contract | Add Pydantic and TypeScript types for project summary, project display metadata, aggregate work item, aggregate session card, pagination, warnings, and freshness. | DTOs cover project id/name/color/group/stale/error/counts and embed V1 work item/session card shapes without field ambiguity. | 1 pt | backend-architect, frontend-developer | None |
| MPCC-102 | Feature Flag | Add backend/frontend capability flag for multi-project command center. | Flag can disable all new UI and endpoints return clear disabled response or are hidden by capability. | 0.5 pts | python-backend-engineer | MPCC-101 |
| MPCC-103 | Project Display Config | Add optional `ProjectDisplayConfig` to `Project` for color, group, sort order, and label override. | Existing `projects.json` loads without modification; unset projects get deterministic fallback color/group. | 1 pt | python-backend-engineer, ui-designer | MPCC-101 |
| MPCC-104 | Contract Fixtures | Create shared backend/frontend fixtures for 3 projects, stale project, failed project, active sessions, root/worker lineage, and work items. | Fixtures support backend unit tests and frontend component tests. | 0.5 pts | testing specialist | MPCC-101 |

**Quality Gates:**
- [ ] Existing project registry tests pass.
- [ ] DTO serialization round trip covers unset and customized display metadata.
- [ ] Feature flag defaults to off.

## Phase 2: Cross-Project Command-Center Aggregate

**Dependencies:** Phase 1.
**Assigned Subagent(s):** backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-201 | Refactor V1 Item Builder | Extract reusable helper from `PlanningCommandCenterQueryService` so a cross-project service can build items without routing through HTTP. | Single-project endpoint remains behavior-compatible; helper accepts explicit project scope. | 1 pt | python-backend-engineer | MPCC-101 |
| MPCC-202 | Aggregate Service | Add `MultiProjectPlanningCommandCenterQueryService` with bounded project fan-out, per-project warnings, cache, server-side sort/filter, and aggregate pagination. | Endpoint can return all-project work items with project metadata and partial status. | 2 pts | backend-architect, python-backend-engineer | MPCC-201 |
| MPCC-203 | Project Summary Rollup | Add per-project counts for work items, blocked, review, stale, active sessions, and errors using system metrics/freshness helpers. | Project rail can render counts without extra requests. | 1 pt | python-backend-engineer | MPCC-202 |
| MPCC-204 | API Endpoint | Add `GET /api/agent/planning/multi-project/command-center`. | OpenAPI includes filters, pagination, and response model; flag off behavior covered. | 0.5 pts | python-backend-engineer | MPCC-202 |
| MPCC-205 | Backend Tests | Add unit/router tests for aggregation, filters, pagination, partial failures, stale warnings, and project metadata. | Focused pytest suite passes. | 0.5 pts | testing specialist | MPCC-204 |
| MPCC-206 | Page-First And Lazy Enrichment | Prevent aggregate list reads from probing git or materializing detail-only fields for off-page items; fix detail lookup paths that scan only the first page. | Aggregate list enriches only page-visible rows; detail endpoint can find an item beyond the first page. | 1 pt | backend-architect, python-backend-engineer | MPCC-202 |

**Quality Gates:**
- [ ] No frontend project-loop dependency is required to load aggregate work items.
- [ ] A failing project produces partial response and visible project error.
- [ ] Aggregate list payloads do not run git probes for off-page items.
- [ ] Existing V1 command-center tests still pass.

## Phase 3: Cross-Project Active-Session Board

**Dependencies:** Phase 1.
**Assigned Subagent(s):** python-backend-engineer, data-layer-expert

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-301 | Active Session Repository Query | Add indexed repository method to list active/recent sessions by project with window, limit, and `include_subagents` controls. | Query uses project/status/updated index and excludes stale active rows by default. | 1 pt | data-layer-expert, python-backend-engineer | MPCC-101 |
| MPCC-302 | Correlation Helper Refactor | Extract reusable active-card builder/correlation helpers from `PlanningSessionQueryService` without changing existing board behavior. | Single-project session board tests remain green. | 1 pt | python-backend-engineer | MPCC-301 |
| MPCC-303 | Aggregate Session Service | Add `MultiProjectActiveSessionBoardQueryService` that fetches active candidates, loads feature/link data only where needed, nests workers, and groups cards. | Response includes active cards across projects with project metadata and worker summaries. | 2 pts | backend-architect, python-backend-engineer | MPCC-302 |
| MPCC-304 | Session Board Endpoint | Add `GET /api/agent/planning/multi-project/session-board` with grouping, project/group filters, active window, workers toggle, pagination, and stale-state filters. | Endpoint returns grouped cards and project summaries. | 0.5 pts | python-backend-engineer | MPCC-303 |
| MPCC-305 | Backend Tests | Cover active-only filtering, worker nesting, project failures, stale suppression, grouping, and no-active-project fast path. | Focused pytest suite passes. | 0.5 pts | testing specialist | MPCC-304 |

**Quality Gates:**
- [ ] Service does not call `get_session_board` once per project.
- [ ] Projects with zero active candidates do not load full feature/link correlation data.
- [ ] Worker/subagent cards are visible without duplicating every worker as a top-level card by default.

## Phase 4: Frontend Data Layer And Query State

**Dependencies:** Phase 1 DTOs; can use mocks while Phases 2/3 finish.
**Assigned Subagent(s):** frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-401 | Service Adapter | Add `services/multiProjectPlanningCommandCenter.ts` adapters for both aggregate endpoints. | Snake-case wire data adapts to camelCase models; API errors are typed. | 1 pt | frontend-developer | MPCC-101 |
| MPCC-402 | Current Command-Center Query Migration | Move the existing current-project command-center fetch path onto TanStack Query and shared query keys before adding portfolio reads. | V1 behavior is unchanged; fetches dedupe and preserve stale/error states through query hooks. | 1 pt | frontend-developer | MPCC-401 |
| MPCC-403 | Aggregate Query Hooks | Add TanStack Query hooks and query keys for aggregate command center and active-session board. | Query keys include filters, grouping, project/group selection, page, and feature flag. | 0.75 pts | frontend-developer | MPCC-402 |
| MPCC-404 | URL State | Add URL-addressable view mode, project/group filter, session grouping, selected card, and modal state. | Reload preserves selected filters and route-local detail target. | 0.75 pts | frontend-developer | MPCC-403 |
| MPCC-405 | Mock Fixtures And Tests | Add frontend fixture payloads and adapter tests. | Adapter tests cover partial, stale, failed project, empty, and worker-nested payloads. | 0.5 pts | frontend-developer | MPCC-401 |

**Quality Gates:**
- [ ] No data fetch starts without feature flag/project list readiness.
- [ ] Query state does not mutate active project.
- [ ] Current-project command center uses the same query layer as portfolio mode.
- [ ] Adapter tests cover every field consumed by Phase 5 components.

## Phase 5: Multi-Project Planning UI

**Dependencies:** Phase 4.
**Assigned Subagent(s):** ui-engineer-enhanced, frontend-developer, ui-designer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-501 | Multi-Project Shell | Add a feature-flagged multi-project mode inside Planning Command Center without removing V1. | Users can switch between consolidated and current-project modes. | 0.75 pts | ui-engineer-enhanced | MPCC-403 |
| MPCC-502 | Project Filter Rail | Build all/group/project filter rail or segmented controls with project colors, counts, stale/error indicators, and keyboard support. | Project colors are labels plus accents, not color-only meaning. | 1 pt | ui-engineer-enhanced, ui-designer | MPCC-501 |
| MPCC-503 | Consolidated Active-Session Board | Build active-session board with state/project/feature/phase/agent/model grouping, worker summaries, card expansion, and transcript/detail actions. | Board renders 100 cards without overlap and supports grouping changes. | 1.5 pts | ui-engineer-enhanced, frontend-developer | MPCC-403 |
| MPCC-504 | Cross-Project Work-Item Board/List | Extend command-center list/card/board components to render project identity and aggregate pagination. | Work item cards retain V1 actions and show project metadata. | 1 pt | frontend-developer | MPCC-501 |
| MPCC-505 | Route-Local Detail Modals | Wire session, feature, plan, launch, execution, PR/review, and stale-project detail drawers with explicit `project_id`. Start with portfolio detail rail where existing modal hooks are not yet project-scoped. | Opening detail does not switch active project; focus returns to originating card. | 0.75 pts | frontend-developer | MPCC-404 |

**Quality Gates:**
- [ ] The first viewport clearly shows live active sessions and project identity.
- [ ] Detail drawers work for a non-active project.
- [ ] Existing single-project command-center route remains intact.

## Phase 6: Performance, Tests, Accessibility

**Dependencies:** Phases 2-5.
**Assigned Subagent(s):** react-performance-optimizer, web-accessibility-checker, testing specialist

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-601 | Backend Performance Tests | Add 36-project and threshold-scale aggregate fixtures for command-center and active-session endpoints. | p95 budgets enforced; cache repeat budgets enforced. | 1 pt | python-backend-engineer, data-layer-expert | MPCC-205, MPCC-305 |
| MPCC-602 | Frontend Performance | Add virtualization/windowing or equivalent for large card sets and verify render budgets. | 100 cards usable; >250 visible cards use windowing. | 1 pt | react-performance-optimizer, frontend-developer | MPCC-503 |
| MPCC-603 | FE/BE Contract Tests | Assert frontend-consumed fields exist in live aggregate responses. | Contract tests fail on DTO drift. | 0.75 pts | testing specialist | MPCC-401, MPCC-204, MPCC-304 |
| MPCC-604 | Accessibility Pass | Test keyboard navigation, project filter labels, board group headings, modal focus, contrast, and reduced motion. | WCAG AA issues in touched surfaces resolved or documented. | 0.75 pts | web-accessibility-checker, ui-engineer-enhanced | MPCC-505 |
| MPCC-605 | Regression Suite | Run existing planning command center, planning home, session board, and launch sheet suites. | Existing V1 behavior not regressed. | 0.5 pts | testing specialist | MPCC-604 |

**Quality Gates:**
- [ ] `python3 -m pytest backend/tests/test_multi_project_planning_command_center.py backend/tests/test_multi_project_planning_sessions.py backend/tests/test_multi_project_planning_performance.py -q`
- [ ] `npm test -- services/__tests__/multiProjectPlanningCommandCenter.test.ts components/Planning/__tests__/multiProjectPlanningCommandCenter.test.tsx`
- [ ] Existing V1 command-center tests pass.
- [ ] Browser smoke shows no text overlap on desktop and mobile-width responsive states.

## Phase 7: Rollout, Docs, Runtime Smoke

**Dependencies:** Phase 6.
**Assigned Subagent(s):** documentation-writer, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MPCC-701 | Operator Guide | Document multi-project command center usage, project colors/groups, stale state, active sessions, and detail actions. | Guide includes try-it steps and troubleshooting. | 0.25 pts | documentation-writer | MPCC-605 |
| MPCC-702 | Human Brief And AAR Stub | Add human brief or closeout stub for release traceability. | Docs link PRD, plan, spike, validation, and flag. | 0.25 pts | documentation-writer | MPCC-701 |
| MPCC-703 | Runtime Smoke | Run backend/frontend locally with multi-project fixture and capture browser smoke notes. | Smoke verifies all-project board, active sessions, project filters, and detail modal. | 0.25 pts | testing specialist | MPCC-605 |
| MPCC-704 | Rollout Toggle | Document feature flag rollout and fallback path. | Flag can be disabled without code revert. | 0.25 pts | DevOps, documentation-writer | MPCC-703 |

**Quality Gates:**
- [ ] Feature flag defaults remain safe for release branch.
- [ ] Runtime smoke includes at least one non-active project detail modal.
- [ ] Docs include performance caveats and stale-data semantics.

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|---------------------|
| N-project browser fan-out sneaks in | High | Medium | Enforce aggregate endpoint usage in architecture and tests. |
| Active-session aggregate becomes full-board aggregate | High | Medium | Repository active-only query and perf tests are Phase 3/6 gates. |
| Stale project data looks live | High | Medium | Freshness indicators on project filters and cards; live window clamps active rows. |
| Route-local modals fetch wrong project | Medium | Medium | Explicit project id in URL state and every detail request; test with non-active project. |
| Aggregate DTO grows too large | Medium | Medium | Server pagination, collapsed-detail payloads, lazy detail fetch. |
| Accessibility regression from color-heavy project identity | Medium | Low | Color plus text labels, contrast tests, keyboard focus gates. |

## Validation Plan

Focused backend:

```bash
python3 -m pytest backend/tests/test_multi_project_planning_command_center.py \
  backend/tests/test_multi_project_planning_sessions.py \
  backend/tests/test_multi_project_planning_performance.py -q
```

Focused frontend:

```bash
npm test -- services/__tests__/multiProjectPlanningCommandCenter.test.ts \
  components/Planning/__tests__/multiProjectPlanningCommandCenter.test.tsx
```

Regression:

```bash
python3 -m pytest backend/tests/test_planning_command_center_service.py \
  backend/tests/test_planning_router.py \
  backend/tests/test_live_metrics.py \
  backend/tests/test_system_metrics.py -q

npm test -- services/__tests__/planningCommandCenter.test.ts \
  components/Planning/__tests__/planningCommandCenter.test.tsx \
  components/Planning/__tests__/planningLaunchSheet.test.tsx
```

Runtime smoke:

1. Start backend with local runtime.
2. Start frontend on an available Vite port.
3. Enable the multi-project flag.
4. Open `/#/planning`.
5. Verify consolidated active sessions, project filters, stale indicators, work-item board, and non-active project detail modal.

## Deferred Follow-Ups

| Item | Rationale | Promotion Trigger |
|------|-----------|-------------------|
| Simultaneous watch-all-projects runtime | Larger runtime topology decision. | Operators need sub-minute freshness for many non-active projects. |
| Background planning rollup table | Adds write complexity. | Project count > 100 or p95 aggregate reads exceed target. |
| Manual stale-project resync action | Useful but not required for v1. | Stale indicators show frequent non-active stale projects in real use. |
| Persisted saved views | Valuable after base UI stabilizes. | Users repeatedly create the same cross-project filters. |
| External widget API hardening | Separate auth/rate-limit contract. | Concrete widget consumer enters planning. |

## Definition Of Done

- Aggregate command-center and active-session endpoints are implemented and tested.
- Project display metadata has deterministic fallback and optional persistence.
- Multi-project Planning UI is feature flagged and fallback-safe.
- Active sessions across projects can be operated from one screen.
- Detail modals use explicit project scope and do not switch active project.
- Performance budgets pass.
- Existing V1 command center remains intact.
- Operator docs and runtime smoke evidence are added.
