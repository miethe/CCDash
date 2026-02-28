---
title: "Implementation Plan: Test Visualizer"
schema_version: 2
doc_type: implementation_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: null
scope: "Full test observability subsystem with 4 UI entry points, ingestion pipeline, API, and integrity signals"
effort_estimate: "~120 story points"
related_documents:
  - docs/project_plans/PRDs/features/test-visualizer-v1.md
  - docs/project_plans/designs/test-visualizer.md
owner: fullstack-engineering
contributors: [ai-agents]
priority: high
risk_level: high
category: "product-planning"
tags: [implementation, planning, test-visualizer, testing, observability]
---

# Implementation Plan: Test Visualizer

**Complexity**: XL | **Track**: Full
**Estimated Effort**: ~120 story points | **Timeline**: 8-10 weeks
**PRD**: [test-visualizer-v1.md](/docs/project_plans/PRDs/features/test-visualizer-v1.md)
**Design Spec**: [test-visualizer.md](/docs/project_plans/designs/test-visualizer.md)

---

## Executive Summary

The Test Visualizer introduces a complete test and feature observability subsystem to CCDash. It answers the fundamental question: "Is this feature actually working, or did an agent just make the tests pass?" The subsystem spans the full stack from JUnit XML ingestion through domain mapping, integrity signal detection, REST API, and four distinct UI entry points.

The implementation follows CCDash's established layered architecture (Filesystem Parsers -> SyncEngine -> Repositories -> Services -> Routers -> Frontend). New tables are added to the existing SQLite/PostgreSQL schema via the versioned migration system. All endpoints follow the existing Router -> Service -> Repository pattern. UI components share a common design language with the existing slate-dark theme and indigo accent palette.

**Key architectural decisions:**
- Append-only test result storage keyed by `(run_id, test_id)` for audit trail integrity
- Pluggable Domain Mapping Provider system with precedence and conflict resolution
- Async integrity signal detection to avoid blocking ingestion
- Polling-first live updates (60s interval); WebSocket deferred to v2
- Feature-flagged subsystem (`CCDASH_TEST_VISUALIZER_ENABLED`) for safe rollout

---

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | File |
|-------|-------|--------|----------|---------------|------|
| 1 | Data Layer | 18 pts | 1.5 weeks | Yes | [phase-1-data-layer.md](./test-visualizer-v1/phase-1-data-layer.md) |
| 2 | Ingestion Pipeline | 16 pts | 1 week | Yes | [phase-2-ingestion.md](./test-visualizer-v1/phase-2-ingestion.md) |
| 3 | API Layer | 14 pts | 1 week | Yes | [phase-3-api.md](./test-visualizer-v1/phase-3-api.md) |
| 4 | UI/UX Design | 20 pts | 1.5 weeks | No (parallel) | [phase-4-ui-design.md](./test-visualizer-v1/phase-4-ui-design.md) |
| 5 | Core UI Components | 18 pts | 1.5 weeks | Depends on 3+4 | [phase-5-core-ui.md](./test-visualizer-v1/phase-5-core-ui.md) |
| 6 | Page & Tab Integration | 16 pts | 1 week | Depends on 5 | [phase-6-integration.md](./test-visualizer-v1/phase-6-integration.md) |
| 7 | Domain Mapping & Integrity | 10 pts | 1 week | Depends on 1+2 | [phase-7-mapping-integrity.md](./test-visualizer-v1/phase-7-mapping-integrity.md) |
| 8 | Testing & Polish | 8 pts | 1 week | Final gate | [phase-8-testing-polish.md](./test-visualizer-v1/phase-8-testing-polish.md) |

**Total**: ~120 story points over 8-10 weeks

---

## Implementation Strategy

### Architecture Sequence (Critical Path)

```
Phase 1: DB Schema (migrations + repositories)
    |
Phase 2: Ingestion Pipeline (JUnit parser + SyncEngine extension + ingest API)
    |
Phase 3: API Layer (all 7+ REST endpoints + services + DTOs)
    |
Phase 5: Core UI Components (types + service + shared components)
    |
Phase 6: Page & Tab Integration (TestingPage + 3 new tabs)
```

### Parallel Work Opportunities

- **Phase 4 (UI/UX Design)** runs in parallel with Phases 1-3. Design work begins immediately so components are spec'd before frontend engineers start Phase 5.
- **Phase 7 (Domain Mapping & Integrity)** can begin once Phase 1 (DB) and Phase 2 (Ingestion) are complete. It does not block Phase 3 (API) since the API gracefully handles empty mappings.
- **Phase 8 (Testing & Polish)** begins alongside Phase 6 as backend tests can be written once Phase 2-3 are stable.

### MeatyPrompts Layer Sequence

Following CCDash's established layered architecture:

```
DB Schema (migrations)
    -> Repository Protocols (base.py)
    -> Repository Implementations (SQLite + Postgres)
    -> Factory Functions (factory.py)
    -> Pydantic Models (models.py)
    -> Parser / Ingestion (parsers/test_results.py)
    -> Services (services/test_health.py, services/mapping_resolver.py, services/integrity_detector.py)
    -> Router (routers/test_visualizer.py)
    -> Frontend Types (types.ts additions)
    -> Frontend Service (services/testVisualizer.ts)
    -> Frontend Components (components/TestVisualizer/)
    -> Page Integration (TestingPage, FeatureExecutionWorkbench tabs, SessionInspector tabs, ProjectBoard modal tabs)
```

### Feature Flag Gating

All new functionality is gated by `CCDASH_TEST_VISUALIZER_ENABLED=true` (default: false). Sub-flags for incremental rollout:
- `CCDASH_INTEGRITY_SIGNALS_ENABLED` - gates the async integrity pipeline
- `CCDASH_LIVE_TEST_UPDATES_ENABLED` - gates polling refresh on test pages
- `CCDASH_SEMANTIC_MAPPING_ENABLED` - gates SemanticLLMProvider

---

## Risk Mitigation Summary

| Risk | Mitigation Strategy |
|------|---------------------|
| SQLite volume (millions of test result rows) | Append-only with blob refs; Phase 8 adds archival. Index on (run_id, test_id). Monitor DB size. |
| Domain mapping inaccuracy | Confidence scoring per mapping. Only show "primary" if confidence > 70%. Log provider disagreements. Manual override in v2. |
| Integrity signal false positives | Strict detection rules (removed lines only, not modified). Require 2+ signals per test. Tune thresholds post-rollout. |
| Agent session correlation gaps | Require explicit `agent_session_id` in ingest payload. Validate before storing. Log mismatches. |
| Git CLI unavailability | Graceful degradation: skip integrity signal detection if `git` not found. Log with remediation steps. |
| WebSocket complexity | Defer WebSocket to v2. Use polling (60s) for v1. Existing DataContext polling pattern reused. |
| Breaking existing APIs | All new tables and routes are additive. Existing DB schema unchanged. Feature flag allows instant rollback. |

---

## Success Metrics Summary

| Metric | Target |
|--------|--------|
| Test ingestion latency | < 500ms (single run), < 5s (100-run bulk) |
| Domain health query latency | < 500ms (100 domains, 1000+ tests) |
| Live update delay | < 60s (polling v1) |
| Integrity alert precision | > 90% (< 10% false positive) |
| Test mapping coverage | > 80% of tests mapped to domain/feature |
| API endpoints functional | All 7+ endpoints return valid DTOs |
| UI entry points | All 4 surfaces (Testing Page, Feature Modal, Execution Page, Session Page) |
| Backend test coverage | > 80% for services (test_health, mapping_resolver, integrity_detector) |

---

## Key Files Created / Modified

### Backend (New)
- `backend/routers/test_visualizer.py` - All test API endpoints
- `backend/services/test_health.py` - Domain/feature rollup computation
- `backend/services/mapping_resolver.py` - Provider orchestration
- `backend/services/integrity_detector.py` - Async integrity signal detection
- `backend/parsers/test_results.py` - JUnit XML + JSON parser
- `backend/db/repositories/test_runs.py` - SQLite implementation
- `backend/db/repositories/test_results.py` - SQLite implementation
- `backend/db/repositories/test_definitions.py` - SQLite implementation
- `backend/db/repositories/test_domains.py` - SQLite implementation
- `backend/db/repositories/test_mappings.py` - SQLite implementation
- `backend/db/repositories/test_integrity.py` - SQLite implementation
- `backend/db/repositories/postgres/test_*.py` - Postgres implementations

### Backend (Modified)
- `backend/db/sqlite_migrations.py` - SCHEMA_VERSION 12->13, new tables
- `backend/db/postgres_migrations.py` - New tables for Postgres
- `backend/db/repositories/base.py` - New Repository Protocol interfaces
- `backend/db/factory.py` - New `get_test_*_repository()` factory functions
- `backend/models.py` - New Pydantic DTOs for all test entities
- `backend/main.py` - Include test_visualizer_router
- `backend/config.py` - New `CCDASH_TEST_VISUALIZER_ENABLED` flags

### Frontend (New)
- `components/TestVisualizer/TestingPage.tsx` - Dedicated `/tests` page
- `components/TestVisualizer/TestStatusView.tsx` - Shared filterable view
- `components/TestVisualizer/TestStatusBadge.tsx` - Status badge component
- `components/TestVisualizer/TestRunCard.tsx` - Run summary card
- `components/TestVisualizer/TestResultTable.tsx` - Results table
- `components/TestVisualizer/DomainTreeView.tsx` - Domain hierarchy tree
- `components/TestVisualizer/TestTimeline.tsx` - Feature health timeline chart
- `components/TestVisualizer/IntegrityAlertCard.tsx` - Integrity signal display
- `components/TestVisualizer/HealthGauge.tsx` - Pass % health gauge
- `services/testVisualizer.ts` - Frontend API client

### Frontend (Modified)
- `types.ts` - New test-related TypeScript interfaces
- `App.tsx` - Add `/tests` route
- `components/Layout.tsx` - Add "Testing" nav item
- `components/FeatureExecutionWorkbench.tsx` - Add "Test Status" tab
- `components/SessionInspector.tsx` - Add "Test Status" tab
- `components/ProjectBoard.tsx` - Add "Test Status" tab to feature modal

---

## Phase Files

- [Phase 1: Data Layer](./test-visualizer-v1/phase-1-data-layer.md)
- [Phase 2: Ingestion Pipeline](./test-visualizer-v1/phase-2-ingestion.md)
- [Phase 3: API Layer](./test-visualizer-v1/phase-3-api.md)
- [Phase 4: UI/UX Design](./test-visualizer-v1/phase-4-ui-design.md)
- [Phase 5: Core UI Components](./test-visualizer-v1/phase-5-core-ui.md)
- [Phase 6: Page & Tab Integration](./test-visualizer-v1/phase-6-integration.md)
- [Phase 7: Domain Mapping & Integrity](./test-visualizer-v1/phase-7-mapping-integrity.md)
- [Phase 8: Testing & Polish](./test-visualizer-v1/phase-8-testing-polish.md)
