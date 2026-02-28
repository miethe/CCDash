---
title: "Phase 8: Testing & Polish - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 8
phase_title: "Testing & Polish"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "8 story points"
duration: "1 week"
assigned_subagents: [python-backend-engineer, frontend-developer]
entry_criteria:
  - Phases 1-7 complete
  - All API endpoints functional
  - All 4 UI entry points functional
  - Domain mapping and integrity signals producing data
exit_criteria:
  - Backend unit tests > 80% coverage for all new services
  - Integration tests cover all 9 API endpoints (happy path + error cases)
  - Performance benchmarks met (ingestion < 500ms, domain health < 500ms)
  - Live update polling tested end-to-end
  - Feature flag rollback tested (disable flag, verify no UI shown)
  - All edge cases handled (empty mappings, Git unavailable, feature flag off)
  - Accessibility checks pass for all new components
  - Error states and loading states implemented for all components
tags: [implementation, testing, polish, test-visualizer, performance, accessibility]
---

# Phase 8: Testing & Polish

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 8 story points | **Duration**: 1 week
**Assigned Subagents**: python-backend-engineer, frontend-developer

---

## Overview

This phase hardens the Test Visualizer subsystem for production use. It covers backend unit and integration tests, performance validation, live update end-to-end testing, feature flag rollback verification, edge case handling, accessibility compliance, and UI polish. Some test files were created in earlier phases as stubs — this phase completes them.

---

## Backend Testing

### Unit Test Coverage Targets

| Module | Target Coverage | Test File |
|--------|----------------|-----------|
| `parsers/test_results.py` | > 90% | `tests/test_test_results_parser.py` |
| `services/test_health.py` | > 80% | `tests/test_test_health_service.py` |
| `services/test_ingest.py` | > 80% | `tests/test_test_ingest_service.py` |
| `services/mapping_resolver.py` | > 85% | `tests/test_mapping_resolver.py` |
| `services/integrity_detector.py` | > 80% | `tests/test_integrity_detector.py` |
| `db/repositories/test_runs.py` | > 75% | `tests/test_test_repositories.py` |
| `routers/test_visualizer.py` | > 70% | `tests/test_test_visualizer_router.py` |

### Test Pattern (following existing CCDash style)

```python
# backend/tests/test_test_health_service.py

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

class TestTestHealthService(unittest.TestCase):
    """Tests for TestHealthService rollup computation."""

    class _FakeTestRunRepo:
        async def list_by_project(self, *a, **kw): return []
        async def get_by_id(self, *a, **kw): return None

    class _FakeMappingRepo:
        async def list_by_feature(self, *a, **kw): return []
        async def list_by_domain(self, *a, **kw): return []

    def setUp(self):
        self.db = MagicMock()
        # Patch factory functions to return fake repos

    def test_empty_domain_returns_zero_pass_rate(self):
        """Domain with no mapped tests returns passRate=0."""
        ...

    def test_pass_rate_excludes_skipped_from_denominator(self):
        """pass_rate = passed / (passed + failed), skipped excluded."""
        ...

    def test_integrity_score_penalized_by_open_signals(self):
        """Each open signal subtracts 0.1 from integrity_score (min 0)."""
        ...
```

### Integration Test Cases

All integration tests use in-memory SQLite (`:memory:`) with fresh migrations:

```python
# backend/tests/test_test_visualizer_router.py (integration)

class TestTestVisualizerRouter(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create in-memory SQLite, run migrations, create FastAPI test client
        ...

    async def test_ingest_creates_run_and_results(self):
        """POST /api/tests/ingest stores run and results correctly."""
        ...

    async def test_ingest_idempotent_same_run_id(self):
        """Same run_id posted twice returns 'skipped' on second call."""
        ...

    async def test_domain_health_returns_nested_tree(self):
        """GET /api/tests/health/domains returns nested domain structure."""
        ...

    async def test_feature_timeline_first_green_computed(self):
        """Feature timeline includes first_green date when test went from fail to pass."""
        ...

    async def test_correlate_links_to_session(self):
        """GET /api/tests/correlate returns linked agent session when present."""
        ...

    async def test_feature_flag_disabled_returns_503(self):
        """All endpoints return 503 when CCDASH_TEST_VISUALIZER_ENABLED=false."""
        ...

    async def test_missing_run_id_returns_404(self):
        """GET /api/tests/runs/{run_id} returns 404 for unknown run_id."""
        ...
```

---

## Performance Validation

### Benchmark Targets

| Test | Target | Method |
|------|--------|--------|
| Ingest single run (100 tests) | < 500ms | `timeit` on ingest service |
| Ingest bulk (100 runs × 100 tests) | < 5s | `timeit` on bulk ingest |
| GET /health/domains (100 domains, 1000 tests) | < 500ms | Timed API call |
| GET /features/{id}/timeline (12 months data) | < 2s | Timed API call |
| DomainTreeView render (100 domains) | < 1s | Browser console timing |

### Performance Test Script

```python
# backend/tests/test_test_visualizer_performance.py

import asyncio
import time
import unittest

class TestTestVisualizerPerformance(unittest.IsolatedAsyncioTestCase):

    async def test_ingest_100_tests_under_500ms(self):
        """Single run with 100 tests completes ingestion in < 500ms."""
        payload = generate_test_payload(test_count=100)
        start = time.perf_counter()
        result = await ingest_service.ingest_run(payload, db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed_ms, 500, f"Ingestion took {elapsed_ms:.0f}ms, expected < 500ms")

    async def test_domain_health_100_domains_under_500ms(self):
        """Domain health rollup for 100 domains completes in < 500ms."""
        # Seed 100 domains, 1000 test mappings
        ...
```

### SQLite Index Review

After seeding with realistic data volumes, verify query plans use indexes:

```sql
-- Verify indexes used for domain health query
EXPLAIN QUERY PLAN
SELECT tm.domain_id, tr.status, COUNT(*) as cnt
FROM test_feature_mappings tm
JOIN test_results tr ON tm.test_id = tr.test_id
WHERE tm.project_id = 'test-project' AND tm.is_primary = 1
GROUP BY tm.domain_id, tr.status;
```

Expected: Uses `idx_mappings_domain` and `idx_test_results_test` indexes. If not, add covering indexes in `_ensure_index()` calls.

---

## Live Update End-to-End Test

Manual test procedure (to be documented in testing guide):

1. Start CCDash backend (`npm run dev:backend`)
2. Navigate to Testing Page (`/#/tests`)
3. Open DevTools Network tab
4. Note polling interval: every 60s, `GET /api/tests/health/domains` is called
5. POST a new test run via API:
   ```bash
   curl -X POST http://localhost:8000/api/tests/ingest \
     -H "Content-Type: application/json" \
     -d '{"run_id": "test-live-001", "project_id": "...", "timestamp": "...", ...}'
   ```
6. Within 60s, verify Testing Page updates without page reload
7. Navigate to Execution Page with active session; verify 30s polling interval when `isLive=true`

---

## Feature Flag Rollback Test

```bash
# 1. With flag enabled: verify all endpoints work
CCDASH_TEST_VISUALIZER_ENABLED=true npm run dev:backend

# 2. With flag disabled: verify graceful degradation
CCDASH_TEST_VISUALIZER_ENABLED=false npm run dev:backend

# Expected behavior when disabled:
# - POST /api/tests/ingest returns 503
# - GET /api/tests/* returns 503
# - UI: Testing Page shows "Feature disabled" message (not crash)
# - UI: Test Status tabs not rendered (hidden, not error)
```

---

## Edge Case Handling

### Backend Edge Cases

| Case | Current Handling | Required Fix |
|------|-----------------|--------------|
| Empty JUnit XML (no testcases) | Returns empty payload | Verify: no DB writes, success response |
| Malformed XML | Raises exception | Catch, log, return 400 with error detail |
| Unknown `agent_session_id` | Stored but logged | Verified in ING-6, add explicit test |
| `git` command not found | Skip integrity | Verified in MAP-6, add explicit test |
| Mapping provider all fail | No mappings stored | Verify: graceful, health endpoints return 0 tests |
| Feature ID not in CCDash | Mapping stored with unknown feature | Log warning; API returns feature with name=feature_id |
| Bulk ingest > 1000 tests | Slow | Chunked upserts; test with 5000 test batch |
| DB disk full | SQLite exception | Catch, return 507 Insufficient Storage |

### Frontend Edge Cases

| Case | Expected Behavior |
|------|------------------|
| Feature has no test runs | "Test Status" tab hidden in Feature Modal |
| Domain with 0 tests | Shows "No test data yet" with setup instructions |
| API returns 503 (flag disabled) | Show "Test Visualizer not enabled" banner, not crash |
| Network error on poll | Show "Last updated N minutes ago" with retry button |
| TestTimeline with 1 data point | Render single point on chart (no line), show date |
| Test name exceeds 100 chars | Truncate with tooltip showing full name |
| 1000+ domains in tree | Virtual scroll (if DomainTreeView uses virtual list) or pagination |

---

## Accessibility Compliance

WCAG 2.1 AA requirements for all new components:

| Component | Requirements | Check Method |
|-----------|-------------|--------------|
| TestStatusBadge | Color + text label (not color-only). aria-label. | Manual + axe-core |
| HealthGauge | aria-valuenow, aria-valuemin, aria-valuemax. Screen reader text. | axe-core |
| DomainTreeView | role="tree", aria-expanded, keyboard nav. | axe-core + keyboard test |
| TestResultTable | role="table", th scope, sortable column announces sort direction. | axe-core |
| IntegrityAlertCard | role="alert" for high severity. Severity text not color-only. | Manual |
| Test Status tabs | role="tab", aria-selected, keyboard activation. | axe-core |

---

## UI Polish Tasks

| Task | Priority | Description |
|------|----------|-------------|
| Loading skeletons | High | All data tables/cards show skeleton during fetch (not spinner overlay) |
| Error boundaries | High | Wrap TestingPage and each tab in React ErrorBoundary; show "Something went wrong" with retry |
| Empty state illustrations | Medium | "No tests yet" state with setup instructions and link to API docs |
| Responsive layout | Medium | Testing Page works at 1024px min width (matches Layout min-width) |
| Live indicator pulse | Low | CSS pulse animation on "LIVE" badge (not jarring, 2s cycle) |
| Tooltip on truncated names | Low | Test names > 50 chars show tooltip on hover |

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| TST-1 | Complete backend unit tests | Fill in stub test files from earlier phases. Achieve > 80% coverage targets for all 5 service modules. Use `_FakeRepo` pattern consistent with existing tests. | Coverage targets met. All tests pass with `backend/.venv/bin/python -m pytest backend/tests/ -v`. No test depends on network or filesystem. | 2 | python-backend-engineer | Phases 1-7 |
| TST-2 | Integration tests | Implement full integration test suite in `test_test_visualizer_router.py`. In-memory SQLite. Cover all 9 endpoints + error cases. | All 9 endpoints tested. Idempotency verified. Feature flag disable tested. 404 cases tested. | 2 | python-backend-engineer | TST-1 |
| TST-3 | Performance benchmarks | Implement performance test file. Seed realistic data volumes. Verify all benchmarks met. Document any SQLite index additions needed. | All 4 benchmark targets met. Performance tests runnable in CI without external dependencies. | 1 | python-backend-engineer | TST-2 |
| TST-4 | Edge case handling | Audit and fix all edge cases from the table above. Backend: malformed XML, bulk ingest, Git not found. Frontend: 503 graceful, empty domain, TestTimeline with 1 point. | All edge cases produce expected output (not crash). Error messages are user-friendly. | 2 | python-backend-engineer, frontend-developer | Phases 1-7 |
| TST-5 | Accessibility checks | Run axe-core against all new components. Fix any violations. Verify keyboard navigation for DomainTreeView and TestResultTable. Add missing aria attributes. | Zero axe-core violations on Testing Page. Keyboard nav works for tree and table. Screen reader text present on HealthGauge. | 1 | frontend-developer | Phases 5-6 |

---

## Quality Gates (Final)

### Functional
- [ ] All 17 functional requirements (FR-1 through FR-17) verified against implementation
- [ ] JUnit XML parser handles: standard, parameterized, nested, error-only suites
- [ ] All 9 API endpoints return valid DTOs with correct data
- [ ] All 4 UI entry points functional and share TestStatusView components
- [ ] Domain mapping with RepoHeuristicsProvider produces > 70% coverage on sample project

### Technical
- [ ] `backend/.venv/bin/python -m pytest backend/tests/ -v` — all tests pass
- [ ] Coverage > 80% for new services (run with `--cov=backend/services`)
- [ ] TypeScript compilation passes: `npx tsc --noEmit`
- [ ] No new ESLint errors (all existing rules pass)
- [ ] Feature flag `CCDASH_TEST_VISUALIZER_ENABLED=false` disables subsystem completely

### Performance
- [ ] Single-run ingest (100 tests) < 500ms
- [ ] Domain health query (100 domains) < 500ms
- [ ] Feature timeline (12 months) < 2s
- [ ] TestingPage initial render < 1s (with mock data)

### Accessibility
- [ ] Zero axe-core violations on Testing Page
- [ ] DomainTreeView keyboard navigable (arrows + Enter)
- [ ] All status badges include text label (not color-only)
- [ ] HealthGauge has aria-valuenow/min/max

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/tests/test_test_results_parser.py` | Completed | Fill in stub from Phase 2 |
| `backend/tests/test_test_ingest_service.py` | Completed | Fill in stub from Phase 2 |
| `backend/tests/test_test_health_service.py` | Completed | Fill in stub from Phase 3 |
| `backend/tests/test_test_visualizer_router.py` | Completed | Fill in stub from Phase 3 |
| `backend/tests/test_mapping_resolver.py` | Completed | Fill in stub from Phase 7 |
| `backend/tests/test_integrity_detector.py` | Completed | Fill in stub from Phase 7 |
| `backend/tests/test_test_repositories.py` | Completed | Fill in stub from Phase 1 |
| `backend/tests/test_test_visualizer_performance.py` | Created | Performance benchmark tests |
| Various component files | Modified | Add error boundaries, loading skeletons, aria attributes |
