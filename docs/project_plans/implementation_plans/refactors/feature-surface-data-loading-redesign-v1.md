---
title: Feature Surface Data Loading Redesign - Implementation Plan
description: Phased implementation plan for bounded feature board loading, aggregate
  rollups, lazy modal data, repository-backed filtering, and cache discipline.
audience:
- ai-agents
- developers
tags:
- implementation
- refactor
- performance
- features
- sessions
- api-contracts
created: 2026-04-22
updated: '2026-04-23'
category: product-planning
status: in-progress
related:
- /docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
---

# Implementation Plan: Feature Surface Data Loading Redesign

**Plan ID:** `IMPL-2026-04-22-FEATURE-SURFACE-DATA-LOADING-REDESIGN`
**Date:** 2026-04-22
**Author:** Codex
**Complexity:** XL
**Total Estimated Effort:** 69 points
**Target Timeline:** 3-5 engineering weeks, depending on test fixture readiness and rollout strictness

## Executive Summary

This plan replaces the feature board's eager per-feature linked-session calls with a layered feature surface architecture: repository-backed list queries, batched aggregate rollups, explicit lazy modal section endpoints, and bounded frontend caches. It preserves the full current feature set while moving expensive session/log detail work behind user intent and data-source pagination.

## Current Hotspots

1. `ProjectBoard` calls `/api/features/{id}/linked-sessions` for every filtered feature during page render.
2. `ProjectBoardFeatureModal` calls full feature detail and full linked sessions on mount regardless of active tab.
3. Modal detail requests use raw feature IDs in some paths instead of `encodeURIComponent`.
4. The linked-sessions endpoint performs N+1 session row/log work and root-family expansion.
5. Feature list paths mix backend pagination with frontend or in-memory filtering.
6. There is no batch/card rollup contract; cards compute summary metrics from full session arrays.

## Architecture Direction

### Target Data Contracts

| Contract | Purpose | Payload Bound |
|----------|---------|---------------|
| `GET /api/v1/features` | Feature card/list rows with filters, search, sort, pagination, counts | Page/window only |
| `POST /api/v1/features/rollups` | Aggregate metrics for returned feature IDs | Bounded ID list, no logs |
| `GET /api/v1/features/{feature_id}` | Modal overview shell and optional light includes | Single feature |
| `GET /api/v1/features/{feature_id}/sessions` | Linked sessions, paginated and optionally enriched | Page only |
| `GET /api/v1/features/{feature_id}/activity` | Timeline/history/commit aggregates | Single feature, paginated where needed |

### Layering Rules

1. Repositories own filtering, sorting, counts, pagination, and aggregate SQL.
2. Services assemble DTOs and decide freshness/precision metadata.
3. Routers validate query parameters and return stable contracts.
4. Frontend hooks own query identity, cache policy, loading state, error state, and invalidation.
5. Components render state; components must not fan out API calls by item unless explicitly virtualized/prefetched.

## Phase Overview

| Phase | Title | Effort | Details |
|------|-------|--------|---------|
| 0 | Inventory, Contracts, Guardrails | 8 pts | [Phase 0](./feature-surface-data-loading-redesign-v1/phase-0-inventory-contracts.md) |
| 1 | Repository and Query Foundation | 14 pts | [Phase 1](./feature-surface-data-loading-redesign-v1/phase-1-repository-query-foundation.md) |
| 2 | Service and API Contracts | 15 pts | [Phase 2](./feature-surface-data-loading-redesign-v1/phase-2-service-api-contracts.md) |
| 3 | Frontend Data Layer and Board Migration | 13 pts | [Phase 3](./feature-surface-data-loading-redesign-v1/phase-3-frontend-board.md) |
| 4 | Modal Lazy Loading and Reliability | 10 pts | [Phase 4](./feature-surface-data-loading-redesign-v1/phase-4-modal-lazy-loading.md) |
| 5 | Validation, Observability, Rollout | 9 pts | [Phase 5](./feature-surface-data-loading-redesign-v1/phase-5-validation-rollout.md) |

## Critical Path

1. Phase 0 metric inventory must complete before DTO design is finalized.
2. Phase 1 repository methods unblock all API and frontend work.
3. Phase 2 service/API contracts unblock Phase 3 and Phase 4 implementation.
4. Phase 5 parity and performance gates determine when legacy eager paths can be removed.

## Parallel Work Opportunities

1. Frontend hook design can begin during Phase 2 once DTO drafts stabilize.
2. Modal error/loading state components can be built before final linked-session pagination is ready.
3. Observability and benchmark fixtures can start in Phase 1 and be expanded through Phase 5.
4. SQLite and Postgres repository implementations can be split between workers if method contracts are locked first.

## Contract Principles

1. Never load session logs for card-level metrics.
2. Never fetch full linked-session arrays for all features on board load.
3. Never paginate after fully materializing a large session list.
4. Every list endpoint must return accurate total/page metadata for the applied query.
5. Every aggregate endpoint must state freshness, precision, and whether values are exact or sampled.
6. Every frontend fetch path must encode path parameters.
7. Every user-visible empty state must distinguish "loaded and empty" from "failed to load."

## Rollout Strategy

1. Add new v1 contracts and hooks behind `FEATURE_SURFACE_V2`.
2. Keep legacy `/api/features` and `/api/features/{id}/linked-sessions` paths available.
3. Run parity tests comparing old full-detail-derived metrics with new rollups on fixtures.
4. Switch ProjectBoard to v2 list/rollup path.
5. Switch modal tabs to lazy section loaders.
6. Remove eager summary loader and legacy dependency only after parity and performance gates pass.

## Quality Gates

1. Unit tests pass for SQLite and Postgres repository query behavior.
2. API tests cover filters, sorts, totals, rollups, detail sections, errors, and pagination.
3. Component tests prove no per-feature linked-session fetches occur on initial board render.
4. Modal tests cover encoded feature IDs and tab-level loading/error/retry states.
5. Performance tests show bounded request count and payload size under large fixtures.
6. Existing tests for ProjectBoard, PlanningHomePage, FeatureExecutionWorkbench, SessionInspector, and linked-session routes remain green or are intentionally migrated.

## Key Files

### Backend

- `backend/routers/_client_v1_features.py`
- `backend/routers/client_v1.py`
- `backend/application/services/agent_queries/feature_forensics.py`
- `backend/application/services/agent_queries/models.py`
- `backend/db/repositories/features.py`
- `backend/db/repositories/postgres/features.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`
- `backend/db/repositories/entity_graph.py`
- `backend/db/repositories/postgres/entity_graph.py`
- `backend/services/feature_execution.py`

### Frontend

- `components/ProjectBoard.tsx`
- `services/apiClient.ts`
- `contexts/AppEntityDataContext.tsx`
- `services/live/useLiveInvalidation.ts`
- `services/planningRoutes.ts`
- `components/SessionCard.tsx`
- `components/FeatureExecutionWorkbench.tsx`
- `components/SessionInspector.tsx`

### Tests

- `backend/tests/test_features_router_linked_sessions.py`
- `backend/tests/test_client_v1_contract.py`
- `backend/tests/test_features_repository.py`
- `backend/tests/test_features_list_filter.py`
- `components/__tests__/ProjectBoard.featureModal.test.tsx`
- `services/__tests__/planningRoutes.test.ts`

## Implementation Notes

1. Prefer extending v1 contracts rather than adding new legacy `/api/features` hot paths.
2. Keep legacy route compatibility while frontend migration is incomplete.
3. Avoid introducing an external cache dependency; use bounded in-memory backend cache only where existing cache infrastructure supports invalidation.
4. Use query parameter objects and DTO types in `services/apiClient.ts`; do not scatter `fetch` calls in UI components.
5. Treat card and modal data as separate products: cards need aggregates; tabs need details.

