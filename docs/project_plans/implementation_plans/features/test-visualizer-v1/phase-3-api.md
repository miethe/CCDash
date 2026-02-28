---
title: "Phase 3: API Layer - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 3
phase_title: "API Layer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "14 story points"
duration: "1 week"
assigned_subagents: [python-backend-engineer, backend-architect]
entry_criteria:
  - Phase 1 complete: repositories and DTOs exist
  - Phase 2 complete: ingest endpoint and stub router exist
exit_criteria:
  - All 7+ REST endpoints implemented and returning valid DTOs
  - Cursor pagination on all list endpoints
  - ErrorResponse envelope on all error paths
  - OpenTelemetry spans added to all endpoint handlers
  - Correlation endpoint joins test data with session/commit/feature data
  - TestHealthService computes domain and feature rollups
  - All endpoints return 503 when feature flag disabled
tags: [implementation, api, test-visualizer, rest, fastapi]
---

# Phase 3: API Layer

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 14 story points | **Duration**: 1 week
**Assigned Subagents**: python-backend-engineer, backend-architect

---

## Overview

This phase completes `backend/routers/test_visualizer.py` (started in Phase 2 as a stub) and introduces `backend/services/test_health.py` for rollup computation. All endpoints follow the existing CCDash patterns: `Request` injection for DB access, `get_*_repository()` factory calls, DTO responses (no ORM exposure), cursor-based pagination, and `ErrorResponse` envelopes.

The router is registered in `main.py` with prefix `/api/tests`. All endpoints are gated by `CCDASH_TEST_VISUALIZER_ENABLED`.

---

## API Endpoints

### Complete Endpoint Surface

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tests/ingest` | Ingest test run (Phase 2) |
| GET | `/api/tests/health/domains` | Domain health rollup tree |
| GET | `/api/tests/health/features` | Feature health list (filterable by domain) |
| GET | `/api/tests/runs/{run_id}` | Single run detail + results |
| GET | `/api/tests/runs` | Paginated list of runs |
| GET | `/api/tests/{test_id}/history` | Historical results for one test |
| GET | `/api/tests/features/{feature_id}/timeline` | Feature health timeline |
| GET | `/api/tests/integrity/alerts` | Integrity signals list |
| GET | `/api/tests/correlate` | Cross-entity correlation query |

---

## Endpoint Specifications

### `GET /api/tests/health/domains`

Returns domain health rollup tree. Computed by `TestHealthService.get_domain_rollups()`.

**Query params:**
- `project_id: str` (required)
- `since: str | None` - filter runs to after this ISO timestamp
- `include_children: bool = True` - include child domains/subdomains

**Response:** `list[DomainHealthRollupDTO]` (nested, children inlined)

**Rollup computation:**
1. For each domain, fetch all `test_ids` mapped to it (primary mappings only)
2. Join with latest `test_results` per test_id
3. Compute: `pass_rate = passed / (passed + failed)` (skipped excluded from denominator)
4. Apply integrity penalty: `integrity_score -= 0.1 * open_signal_count`
5. `confidence_score = pass_rate * integrity_score`

---

### `GET /api/tests/health/features`

Returns feature health list, optionally filtered by domain.

**Query params:**
- `project_id: str` (required)
- `domain_id: str | None`
- `since: str | None`
- `cursor: str | None` - base64-encoded pagination cursor
- `limit: int = 50`

**Response:**
```json
{
  "items": [FeatureTestHealthDTO],
  "next_cursor": "base64string | null",
  "total": 42
}
```

---

### `GET /api/tests/runs/{run_id}`

Returns full run detail including all test results.

**Response:**
```json
{
  "run": TestRunDTO,
  "results": [TestResultDTO],
  "definitions": {test_id: TestDefinitionDTO},
  "integrity_signals": [TestIntegritySignalDTO]
}
```

---

### `GET /api/tests/runs`

Paginated list of recent runs.

**Query params:**
- `project_id: str` (required)
- `agent_session_id: str | None`
- `feature_id: str | None`
- `git_sha: str | None`
- `since: str | None`
- `cursor: str | None`
- `limit: int = 20`

---

### `GET /api/tests/{test_id}/history`

Historical test results for one test, newest first.

**Query params:**
- `project_id: str` (required)
- `limit: int = 50`
- `since: str | None`
- `cursor: str | None`

**Response:** paginated list of `TestResultDTO` with joined `TestRunDTO.git_sha` and `TestRunDTO.agent_session_id`.

---

### `GET /api/tests/features/{feature_id}/timeline`

Feature health over time. Groups runs by day, computes pass_rate per day.

**Query params:**
- `project_id: str` (required)
- `since: str | None` (default: 90 days ago)
- `until: str | None`
- `include_signals: bool = True`

**Response:**
```json
{
  "feature_id": "my-feature",
  "feature_name": "My Feature",
  "timeline": [
    {
      "date": "2026-02-01",
      "pass_rate": 0.95,
      "passed": 19,
      "failed": 1,
      "skipped": 0,
      "run_ids": ["run-abc"],
      "signals": [TestIntegritySignalDTO]
    }
  ],
  "first_green": "2026-01-15T10:00:00Z",
  "last_red": "2026-02-10T14:00:00Z",
  "last_known_good": "2026-02-12T09:00:00Z"
}
```

---

### `GET /api/tests/integrity/alerts`

Lists integrity signals, newest first.

**Query params:**
- `project_id: str` (required)
- `since: str | None`
- `signal_type: str | None`
- `severity: str | None`
- `agent_session_id: str | None`
- `limit: int = 50`
- `cursor: str | None`

**Response:** paginated `TestIntegritySignalDTO` list.

---

### `GET /api/tests/correlate`

Cross-entity join. Given a `run_id`, returns all correlated CCDash entities.

**Query params:**
- `run_id: str` (required)
- `project_id: str` (required)

**Response:**
```json
{
  "run": TestRunDTO,
  "agent_session": AgentSession | null,
  "commit_correlation": CommitCorrelation | null,
  "features": [FeatureTestHealthDTO],
  "integrity_signals": [TestIntegritySignalDTO],
  "links": {
    "session_url": "/#/sessions?session_id=...",
    "feature_url": "/#/execution?feature_id=...",
    "testing_page_url": "/#/tests?run_id=..."
  }
}
```

This query joins `test_runs.agent_session_id -> sessions`, `test_runs.git_sha -> commit_correlations`, and `test_feature_mappings -> features`.

---

## TestHealthService

`backend/services/test_health.py` encapsulates all rollup computation logic. The router never does rollup math directly.

```python
class TestHealthService:
    def __init__(self, db):
        self.db = db
        self.run_repo = get_test_run_repository(db)
        self.result_repo = get_test_result_repository(db)
        self.mapping_repo = get_test_mapping_repository(db)
        self.domain_repo = get_test_domain_repository(db)
        self.integrity_repo = get_test_integrity_repository(db)

    async def get_domain_rollups(
        self, project_id: str, since: str | None = None
    ) -> list[DomainHealthRollupDTO]:
        """Compute nested domain health rollups."""
        ...

    async def get_feature_health(
        self, project_id: str, feature_id: str
    ) -> FeatureTestHealthDTO:
        """Compute health for a single feature."""
        ...

    async def get_feature_timeline(
        self, project_id: str, feature_id: str,
        since: str | None, until: str | None,
        include_signals: bool
    ) -> dict:
        """Compute day-by-day health timeline for a feature."""
        ...

    async def get_correlation(
        self, run_id: str, project_id: str
    ) -> dict:
        """Cross-entity join: run -> session, commit, features, signals."""
        ...
```

---

## Pagination Pattern

All list endpoints use cursor-based pagination following this pattern (consistent with existing CCDash PaginatedResponse):

```python
# Cursor encodes: base64(json({"offset": N, "since": "ISO", "sort": "created_at"}))
def encode_cursor(offset: int, **kwargs) -> str:
    import base64, json
    return base64.b64encode(json.dumps({"offset": offset, **kwargs}).encode()).decode()

def decode_cursor(cursor: str) -> dict:
    import base64, json
    return json.loads(base64.b64decode(cursor.encode()).decode())
```

Response envelope for paginated endpoints:
```json
{
  "items": [...],
  "next_cursor": "base64string | null",
  "total": 42,
  "limit": 20
}
```

---

## Error Response Pattern

All error cases use the existing `ErrorResponse` envelope pattern:

```python
class TestVisualizerError(HTTPException):
    pass

# In router:
if not run:
    raise HTTPException(status_code=404, detail={
        "error": "run_not_found",
        "message": f"No run found with id={run_id}",
        "hint": "Check run_id is correct and was ingested successfully"
    })
```

Feature flag check (DRY helper):
```python
def _require_feature_enabled():
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        raise HTTPException(status_code=503, detail={
            "error": "feature_disabled",
            "message": "Test Visualizer is not enabled",
            "hint": "Set CCDASH_TEST_VISUALIZER_ENABLED=true in environment"
        })
```

---

## OpenTelemetry Instrumentation

Add spans to all endpoint handlers following `backend/observability/` patterns:

```python
from backend.observability import get_tracer

tracer = get_tracer("ccdash.test_visualizer")

@router.get("/health/domains")
async def get_domain_health(request: Request, ...):
    with tracer.start_as_current_span("test_visualizer.get_domain_health") as span:
        span.set_attribute("project_id", project_id)
        span.set_attribute("since", since or "")
        ...
```

Span attributes to capture:
- `project_id` on all spans
- `run_id` on run-specific spans
- `feature_id` on feature-specific spans
- `domain_id` on domain-specific spans
- `result_count` on list spans
- `db_query_ms` on heavy queries

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| API-1 | TestHealthService skeleton | Create `backend/services/test_health.py` with all method signatures and docstrings. Wire to repositories via factory. Return stub data initially. | File exists, imports cleanly, no runtime errors on construction. All method signatures match spec. | 1 | python-backend-engineer | Phase 1 |
| API-2 | Domain health rollup | Implement `get_domain_rollups()` in TestHealthService. Query all domains, join with primary mappings, join with latest test_results, compute pass_rate and integrity_score. Return nested DomainHealthRollupDTO. | Returns correct nested structure. pass_rate = passed / (passed + failed). Children correctly nested. Performance < 500ms for 100 domains. | 3 | python-backend-engineer | API-1 |
| API-3 | Feature health rollup | Implement `get_feature_health()` and `list_feature_health()`. Filter by domain_id. Compute open_signals count from integrity table. | Feature health DTO includes all fields. Correctly filters by domain when provided. | 2 | python-backend-engineer | API-2 |
| API-4 | Feature timeline | Implement `get_feature_timeline()`. Group test results by day. Compute first_green, last_red, last_known_good from run timestamps. Include integrity signals on timeline. | Timeline has one entry per day with runs. first_green/last_red correctly computed. Historical query < 2s for 12 months. | 2 | backend-architect | API-3 |
| API-5 | Correlation query | Implement `get_correlation()`. Join run -> sessions, run -> commit_correlations, run -> features via mappings, run -> integrity_signals. Build `links` dict with deep-link URLs. | Returns all correlated entities. Gracefully handles missing session or commit correlation. Links are valid HashRouter paths. | 2 | backend-architect | API-4 |
| API-6 | Complete REST endpoints | Implement all GET endpoints in `test_visualizer.py` router: `GET /health/domains`, `GET /health/features`, `GET /runs/{run_id}`, `GET /runs`, `GET /{test_id}/history`, `GET /features/{feature_id}/timeline`, `GET /integrity/alerts`, `GET /correlate`. All call TestHealthService or repositories. | All 7+ endpoints return 200 with valid DTOs. Pagination works. 404 for missing resources. 503 when feature disabled. | 2 | python-backend-engineer | API-5 |
| API-7 | OTel instrumentation | Add OpenTelemetry spans to all endpoint handlers and TestHealthService methods. Include: span names, project_id, entity IDs, result counts. | Spans appear in OTel trace output. No performance regression. Span attributes set correctly. | 1 | python-backend-engineer | API-6 |
| API-8 | Pagination implementation | Implement cursor encoding/decoding helpers. Apply to all list endpoints: `GET /runs`, `GET /{test_id}/history`, `GET /health/features`, `GET /integrity/alerts`. Return `next_cursor: null` when no more pages. | Cursor pagination works end-to-end. Same items not returned on page 2. next_cursor is null on last page. | 1 | python-backend-engineer | API-6 |

---

## Quality Gates

- [ ] All 9 endpoints exist and return non-500 on valid requests
- [ ] All endpoints return 503 when `CCDASH_TEST_VISUALIZER_ENABLED=false`
- [ ] Domain health rollup returns nested tree structure
- [ ] Feature timeline includes `first_green`, `last_red`, `last_known_good` fields
- [ ] Correlation endpoint returns linked entity URLs
- [ ] Cursor pagination works: second request with `next_cursor` returns different items
- [ ] OpenTelemetry spans emitted (visible in OTel logs at DEBUG level)
- [ ] No raw SQL in router handlers (all via service/repository layer)
- [ ] No ORM model leakage in responses (all DTOs)
- [ ] Integration tests cover happy path for all 9 endpoints
- [ ] Integration tests cover: missing run_id (404), disabled flag (503), invalid cursor (400)
- [ ] Performance: `GET /health/domains` with 100 domains < 500ms on SQLite

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/routers/test_visualizer.py` | Modified | Complete all GET endpoints (stub started in Phase 2) |
| `backend/services/test_health.py` | Created | TestHealthService with all rollup methods |
| `backend/models.py` | Modified | Add timeline response DTOs, correlate response DTO |
| `backend/tests/test_test_visualizer_router.py` | Created | Integration tests for all endpoints |
| `backend/tests/test_test_health_service.py` | Created | Unit tests for TestHealthService |
