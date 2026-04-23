---
title: "Phase 2: Service and API Contracts"
description: "Introduce stable service DTOs and v1 API endpoints for feature cards, rollups, modal sections, and paginated linked sessions."
audience: [ai-agents, developers]
tags: [implementation, phase, services, api, dto]
created: 2026-04-22
updated: 2026-04-22
category: "product-planning"
status: draft
related:
  - /docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
---

# Phase 2: Service and API Contracts

**Effort:** 15 pts
**Dependencies:** Phase 1 repository methods
**Assigned Subagent(s):** backend-architect, python-backend-engineer, api-documenter

## Objective

Create stable API and service contracts that expose bounded feature list rows, aggregate rollups, modal section detail, and paginated linked sessions without leaking legacy heavy behavior into card rendering.

## Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| P2-001 | DTO Definitions | Add DTOs for `FeatureCardDTO`, `FeatureCardPageDTO`, `FeatureRollupDTO`, `FeatureModalOverviewDTO`, `FeatureModalSectionDTO`, and `LinkedFeatureSessionPageDTO`. | DTOs serialize with frontend-friendly camelCase and include freshness/precision metadata. | 2 pts | python-backend-engineer | P1-001 |
| P2-002 | Feature Surface Query Service | Add service that composes feature list rows and phase/doc/dependency summaries from repositories. | Service returns complete card rows without session logs. | 3 pts | backend-architect | P1-004 |
| P2-003 | Rollup Service | Add service that resolves aggregate metrics for bounded feature IDs and validates field selection. | Rollup response supports all card metrics and rejects unbounded requests. | 2 pts | python-backend-engineer | P1-004 |
| P2-004 | Modal Detail Service | Split modal detail into overview, phases/tasks, docs, relations, sessions, test status, and activity helpers. | Each section has clear cost profile and can be loaded independently. | 3 pts | backend-architect | P1-005 |
| P2-005 | v1 Feature List Endpoint | Extend `GET /api/v1/features` or add compatible query mode for card DTOs with backend filters, sort, and totals. | API tests verify query semantics and accurate pagination metadata. | 2 pts | python-backend-engineer | P2-002 |
| P2-006 | v1 Rollup Endpoint | Add `POST /api/v1/features/rollups` with bounded IDs and field selection. | API returns rollups for current page features in one request. | 1 pt | python-backend-engineer | P2-003 |
| P2-007 | v1 Modal Endpoints | Add/extend endpoints for overview, section includes, paginated sessions, and activity. | Modal can load any tab without calling legacy linked-session route. | 1 pt | python-backend-engineer | P2-004 |
| P2-008 | API Observability | Instrument latency, result count, payload size estimate, cache status, and error categorization. | Metrics/logs exist for list, rollup, session page, and modal section calls. | 1 pt | backend-architect | P2-005 |

## Endpoint Details

### `GET /api/v1/features`

Parameters:
- `q`
- `status`
- `stage`
- `category`
- `planned_from`, `planned_to`
- `started_from`, `started_to`
- `completed_from`, `completed_to`
- `updated_from`, `updated_to`
- `sort`
- `order`
- `limit`
- `offset` or cursor-compatible future field
- `include=card,phase_summary,document_summary,dependency_summary`

Response:
- `data.items`
- `data.facets` or `meta.facets` when requested
- `meta.total`, `offset`, `limit`, `has_more`, `query_hash`, `freshness`

### `POST /api/v1/features/rollups`

Request:
- `feature_ids`: bounded list
- `fields`: optional field selectors
- `include_inherited_threads`: bool, default true for counts only

Response:
- Map keyed by feature ID.
- Missing IDs return explicit empty rollup entries or diagnostics.

### `GET /api/v1/features/{feature_id}/sessions`

Parameters:
- `limit`, `offset`
- `sort`, `order`
- `include=badges,tasks,commands,thread_children`
- `primary_only`
- `workflow_type`
- `phase`

Response:
- Page of linked sessions.
- Total count for the applied query.
- `enrichment` metadata describing whether logs were read.

## Compatibility Rules

1. Existing legacy endpoints remain until the frontend no longer depends on them.
2. The existing `/api/features/{id}/linked-sessions` can be reimplemented via the new service internally, but must preserve response shape while it exists.
3. The v1 forensics endpoint must not become the default card source if it still materializes all linked sessions.

## Quality Gates

- [ ] API contract tests cover every query parameter and response metadata field.
- [ ] Rollup endpoint returns all fields needed by current cards.
- [ ] Sessions endpoint paginates at the repository/service level.
- [ ] Error responses distinguish not found, partial data, unsupported include, and transient failure.
- [ ] Existing CLI/MCP consumers of v1 feature forensics remain compatible.

## Notes for Implementers

1. Keep DTO names explicit; avoid reusing `Feature` for card rows if the payload is not full feature detail.
2. Add OpenAPI examples for default board load, filtered board load, modal sessions page, and rollup request.
3. Ensure feature ID aliases/canonical slugs remain supported where existing routes support them.

