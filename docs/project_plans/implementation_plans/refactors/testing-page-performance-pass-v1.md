---
title: "Implementation Plan: Testing Page Performance Pass"
schema_version: 2
doc_type: implementation_plan
status: completed
created: 2026-03-03
updated: 2026-03-03
feature_slug: "testing-page-performance-pass"
feature_version: "v1"
prd_ref: null
plan_ref: null
scope: "Refactor test exploration data flow and rendering for large suites (7k+ tests per run)"
effort_estimate: "~3-5 engineering days"
related_documents:
  - docs/project_plans/implementation_plans/features/test-visualizer-v1.md
owner: fullstack-engineering
contributors: [ai-agents]
priority: high
risk_level: medium
category: "refactor"
tags: [implementation, refactor, performance, testing, test-visualizer]
---

# Implementation Plan: Testing Page Performance Pass

## Executive Summary

The Testing page currently slows down under large payloads because full run results are loaded into client memory, filtered/sorted in the browser, and rendered as large DOM tables. This pass introduces progressive loading and server-driven result queries first, then project-scoped caching and backend precomputation in follow-up phases.

This plan captures the original phased approach agreed for the performance pass.

## Goals

1. Make `/tests` responsive with large runs (including pytest runs with 7000+ test cases).
2. Prevent Testing page interactions from degrading overall app navigation performance.
3. Cache high-value test data by `project_id` to avoid duplicate work.
4. Keep API and UI behavior compatible with existing workflows.

## Non-Goals

1. Replacing the full Test Visualizer architecture.
2. Introducing websocket streaming in this pass.
3. Changing ingestion semantics for test artifacts.

## Phase Overview

| Phase | Title | Status | Objective |
|------|-------|--------|-----------|
| 1 | Progressive Result Loading | Completed | Stop loading/rendering entire run result sets at once |
| 2 | Project-Scoped Cache Layer | Completed | Reuse runs/features/domain rollups per project with invalidation |
| 3 | Backend Query Scalability | Completed | Remove in-memory filtering and N+1 query patterns |
| 4 | Performance Guardrails | Completed | Add budgets, observability, and regression tests at realistic data volume |

## Phase 1: Progressive Result Loading (Completed)

### Completed Work

1. Added a paginated endpoint for run results with server-side status/query/sort/cursor controls.
2. Added lightweight mode for run detail (`include_results=false`) to avoid large payload transfer.
3. Refactored Testing UI to consume paginated results and incremental "Load more" behavior.
4. Removed duplicate domain health polling in full Testing page composition path.
5. Updated live run polling to use lightweight run detail mode.

### Outcome

1. Browser no longer receives full result payloads by default for selected runs.
2. Result table no longer sorts/filters the full run dataset client-side.
3. Initial run detail interaction cost is materially reduced for large suites.

## Phase 2: Project-Scoped Cache Layer (Completed)

### Scope

1. Add in-memory cache keyed by `projectId` for:
   - test runs list queries
   - feature health queries
   - domain health rollups
   - run result pages (`runId + filters + sort + cursor`)
2. Apply TTL + stale-while-revalidate behavior.
3. Add bounded LRU policy for run result pages to cap memory growth.
4. Invalidate project caches when sync/ingest operations complete.

### Deliverables

1. Shared cache utility/hooks for Test Visualizer data.
2. Cache invalidation wiring tied to manual refresh and sync operations.
3. Instrumentation logs/metrics for cache hit/miss rates.

### Acceptance Criteria

1. Reopening `/tests` for same project avoids redundant initial network calls where data is fresh.
2. Navigating run selection with previously loaded pages resolves from cache first.
3. Memory remains bounded under repeated run switches.

## Phase 3: Backend Query Scalability (Completed)

### Scope

1. Move list/filter operations to DB-native queries for runs/features/history/alerts paths.
2. Remove `limit=5000` + Python-filter patterns on hot endpoints.
3. Reduce N+1 behavior in health calculations (`latest per test`, mappings by run).
4. Add targeted indexes only where query plans show benefit.

### Deliverables

1. Repository-level query methods for filtered run and health access paths.
2. Router/service refactors to consume those methods.
3. Endpoint latency benchmarks before/after.

### Acceptance Criteria

1. `/api/tests/runs` and health endpoints avoid full-project in-memory filtering on request path.
2. P95 endpoint latency is stable under larger historical datasets.
3. Functional behavior remains equivalent for existing UI filters.

## Phase 4: Performance Guardrails (Completed)

### Scope

1. Define performance budgets for load time, interaction latency, and memory.
2. Add test fixtures approximating large-suite conditions (7000+ tests/run).
3. Add regression checks for heavy query paths and frontend rendering paths.
4. Add lightweight observability markers around key endpoints and UI transitions.

### Deliverables

1. Performance test cases for backend and documented benchmark commands.
2. Documented budgets and pass/fail thresholds.
3. Follow-up remediation checklist for any missed budget.

### Acceptance Criteria

1. Performance regressions are detectable in CI/local checks.
2. Team has a repeatable benchmark path for future test visualizer changes.

## Rollout and Risk Mitigation

1. Roll out behind existing Test Visualizer feature gating; keep behavior additive.
2. Keep pagination defaults conservative (`limit` bounded) to protect API and UI.
3. Preserve compatibility with current filters and route query parameters.
4. Validate with both small fixtures and large real project datasets before phase completion.

## Tracking Notes

1. Phase 1 completed on 2026-03-03.
2. Next execution target is Phase 2 (project-scoped caching).
3. Update this plan `status`, `updated`, and phase statuses as each phase lands.
