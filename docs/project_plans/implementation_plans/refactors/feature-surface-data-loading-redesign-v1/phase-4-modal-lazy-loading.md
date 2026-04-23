---
title: "Phase 4: Modal Lazy Loading and Reliability"
description: "Refactor feature modal tabs to load detail data by active tab with encoded IDs, visible state, retries, and paginated sessions."
audience: [ai-agents, developers]
tags: [implementation, phase, modal, lazy-loading, reliability]
created: 2026-04-22
updated: 2026-04-22
category: "product-planning"
status: draft
related:
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
---

# Phase 4: Modal Lazy Loading and Reliability

**Effort:** 10 pts
**Dependencies:** Phase 2 API contracts, Phase 3 API client methods
**Assigned Subagent(s):** frontend-developer, ui-engineer-enhanced, react-performance-optimizer

## Objective

Make feature modal data loading intentional and reliable: open a cheap overview shell, load each tab's data only when needed, show real loading/error states, and page linked sessions without full upfront materialization.

## Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| P4-001 | Encoded Modal Paths | Replace raw feature ID path interpolation in modal fetches with encoded API client methods. | Feature IDs containing `/`, spaces, `#`, `?`, and `&` load correctly. | 1 pt | frontend-developer | P3-001 |
| P4-002 | Modal Data Hook | Add `useFeatureModalData` or equivalent with per-section query state, cache keys, abort/request IDs, and retries. | Modal can independently load overview, phases, docs, relations, sessions, test status, and history. | 3 pts | frontend-developer | P2-007 |
| P4-003 | Lazy Tab Loading | Remove full linked-session fetch from modal mount; trigger session fetch on Sessions tab activation or explicit prefetch. | Opening modal overview does not call linked-session detail endpoint. | 2 pts | frontend-developer | P4-002 |
| P4-004 | Session Pagination UI | Add load-more/page handling for linked sessions while preserving current tree/grouping, summaries, and card detail sections. | Sessions tab supports large linked-session sets without loading all rows. | 2 pts | ui-engineer-enhanced | P4-003 |
| P4-005 | Tab State Rendering | Add visible loading, error, retry, empty, and stale states for each tab. | Transient failures are not rendered as valid empty data. | 1 pt | ui-engineer-enhanced | P4-002 |
| P4-006 | Modal Live Refresh Policy | Update polling/live invalidation to refresh only loaded or active sections and avoid redundant detail fetches. | Background refresh does not fetch unloaded heavy sections. | 1 pt | react-performance-optimizer | P4-003 |

## Modal Loading Policy

1. On open:
   - Load overview shell only.
   - Optionally load lightweight test health if required to decide tab visibility.
   - Do not load full linked sessions.

2. On tab activation:
   - `overview`: use shell and cheap derived state.
   - `phases`: load phases/tasks if not already included.
   - `docs`: load document metadata and coverage.
   - `relations`: load feature dependency/relation data.
   - `sessions`: load first linked-session page.
   - `test-status`: load test health/detail.
   - `history`: load activity/timeline/commit aggregates.

3. On live invalidation:
   - Refresh active tab immediately.
   - Mark inactive loaded tabs stale.
   - Do not fetch inactive unloaded tabs.

## Sessions Tab Requirements

1. Preserve current visible session information: title, status, model identity, cost/tokens, commands, commit hashes, PR links, workflow type, related phases/tasks, primary/subthread markers, and thread tree when requested.
2. Default first page should be cheap; expensive badge/log enrichment must be opt-in or page-scoped.
3. Tree building should work with partial pages and communicate when more children/pages are available.
4. Counts displayed in tab labels can come from rollup totals before full detail loads.

## Error State Requirements

1. Error states include retry controls.
2. Empty states only render after a successful response with zero items.
3. Partial responses show a non-blocking warning and available data.
4. Request cancellation or stale request IDs must not overwrite newer tab data.

## Quality Gates

- [ ] Modal overview open makes no full linked-session call.
- [ ] Sessions tab fetches on first activation and supports pagination.
- [ ] Feature IDs with special characters pass component tests.
- [ ] Errors are visible and retryable.
- [ ] Live refresh does not trigger heavy inactive tab loads.

## Notes for Implementers

1. Keep tab labels accurate by using rollup counts where detail has not loaded.
2. Avoid duplicate state sources between `selectedFeature`, `fullFeature`, and per-section detail.
3. Once section hooks are stable, consider splitting the oversized modal component into smaller tab components.

