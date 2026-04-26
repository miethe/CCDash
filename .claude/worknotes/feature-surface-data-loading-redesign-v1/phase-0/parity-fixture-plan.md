---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-006
created: 2026-04-23
---

# Parity Fixture Plan

---

## 1. Summary

This document defines the fixture tiers and test scaffolding that Phase 5 will use to prove:

(a) **Old-vs-new parity** — every card metric and modal metric derived from the legacy eager full-session-array path matches the value returned by the new rollup and section endpoints, within stated tolerance.

(b) **Performance budgets hold** — request count, payload size, backend query count, and latency stay within the targets established in P0-005 under MEDIUM and LARGE fixture loads.

Three fixture tiers are defined: SMALL (smoke + correctness), MEDIUM (integration + performance baseline), LARGE (stress + query plan validation). All tiers use a shared deterministic seed mechanism and frozen timestamps to ensure reproducibility. Fixtures are implemented as pytest factory functions over in-memory SQLite (the same pattern used by `test_features_list_filter.py` and `test_features_repository.py`), with JSON snapshots exported for frontend MSW handlers.

---

## 2. Fixture Tier Specifications

| Dimension | SMALL | MEDIUM | LARGE |
|---|---|---|---|
| **Feature count** | 5 | 40 | 200 |
| **Status distribution** | 1 backlog, 1 in-progress, 1 review, 1 done, 1 deferred | 8 backlog, 10 in-progress, 6 review, 8 done, 4 deferred, 4 draft | 40 backlog, 50 in-progress, 30 review, 40 done, 20 deferred, 20 draft |
| **Session count** | 20 total | ~400 total | ~4 000 total |
| **Primary vs subthread split** | 16 primary / 4 subthreads | ~320 primary / ~80 subthreads (20%) | ~3 000 primary / ~1 000 subthreads (25%) |
| **Linked docs** | 6 (1–2 per feature; all docTypes) | ~100 (2–3 per feature, mixed docTypes) | ~500 (2–3 per feature, mixed docTypes) |
| **Tasks** | 10 total (2 per feature) | ~160 total (4 per feature) | ~800 total (4 per feature) |
| **Failing tests** | 1 feature with 2 failing tests | 4 features with failing tests (1–3 failures each) | 20 features with failing tests (1–5 failures each) |
| **Date spread** | All dates within a single 30-day window (2026-01-01 to 2026-01-31) | 6-month spread (2025-10-01 to 2026-04-01); `completedAt` only on done/deferred features; `startedAt` absent on backlog features | 18-month spread (2024-10-01 to 2026-04-01); same rules; ~10% of features have `updatedAt` in the last 7 days to exercise "recently updated" sort |
| **Category diversity** | 3 categories: `ui`, `api`, `infra` | 6 categories: `ui`, `api`, `infra`, `ml`, `data`, `devex` | 8 categories including `security`, `platform` |
| **Tag diversity** | 0–2 tags per feature; 4 distinct tag values | 0–5 tags per feature; 12 distinct tag values | 0–8 tags per feature; 25 distinct tag values |
| **Token/cost range per session** | 500–5 000 `observedTokens`; $0.01–$0.10 `displayCostUsd` | 500–50 000 tokens; $0.001–$0.50 cost; 2 zero-cost sessions (tool-only) | 200–200 000 tokens; $0.00–$2.00 cost; ~5% zero-cost sessions; 1 session with null `displayCostUsd` (tests fallback chain) |
| **Relation graph density** | 1 `blocked_by` relation pair; no families | 4 `blocked_by` pairs; 2 feature families (3 members each); 2 `related` links | 10 `blocked_by` pairs; 5 feature families (3–8 members each); 15 `related` links; 2 circular `related` entries |
| **Special edge cases** | 1 feature with 0 sessions; 1 feature with 0 linked docs | All SMALL edges plus: 1 feature with 20 subthreads only (no primary sessions); 1 feature with 0 tasks; 2 features sharing the same session via multiple link records | All MEDIUM edges plus: 2 orphan features (no project cross-reference); 1 feature with 50 sessions (tests rollup batch boundary); 1 feature with empty `data_json` (tests null-safe paths); 1 feature with `deferredTasks > 0` but `status = in-progress` (tests `hasDeferredCaveat` edge); 1 feature with null `plannedAt` and null `startedAt`; 1 session with `parentSessionId` pointing to a session that is NOT in the feature's session set (tests `unresolvedSubthreadCount`) |

---

## 3. Existing Fixtures Catalog and Gap Analysis

### 3.1 Reusable Existing Fixtures

The following patterns are reusable as-is or with minor extension:

| File | Pattern/Factory | What It Provides | Reusable for Parity? |
|---|---|---|---|
| `test_features_list_filter.py` | `_insert_features()` (sync SQLite helper) + `_start_app()` / `_stop_app()` lifecycle | Per-test temp SQLite DB with migrated schema; seeds feature rows by dict; builds a real FastAPI `TestClient`. Proven pattern for filter/pagination tests. | Yes — extend to seed sessions, links, phases, tasks. This is the base factory pattern. |
| `test_features_list_filter.py` | `_run_migrations_sync()` | Runs full migration stack on a temp DB file synchronously. Reusable in any new fixture builder. | Yes — import directly. |
| `test_features_repository.py` | `FeatureRepositoryTests.asyncSetUp()` | `aiosqlite` in-memory DB + `run_migrations` + `SqliteFeatureRepository`. Single-feature upsert pattern with phases. | Yes — extend to multi-feature upsert for SMALL tier. |
| `test_features_router_linked_sessions.py` | `_FakeFeatureRepo`, `_FakeSessionRepo`, `_FakeLinkRepo`, `_FakeTaskRepo` | Complete fake repository layer covering: feature + phase shape, session row shape (all token fields, cost fields, subthread fields, commit correlations, PR links), link metadata JSON shape. The `_FakeSessionRepo.list_paginated` signature matches the real repo contract. | Yes — the column shapes and JSON structures are the authoritative fixture schema. Use them as the reference for column completeness when building SMALL/MEDIUM/LARGE generators. |
| `test_client_v1_contract.py` | `TestClientV1Contract.setUpClass()` | Full `build_runtime_app("test")` + patched observability + `TestClient` lifecycle. Reusable as the bootstrap harness for integration-level parity tests that need a running API. | Yes — copy the `setUpClass` / `tearDownClass` pattern; extend to seed data before entering the TestClient context. |
| `test_agent_queries_feature_forensics.py` | `_IdentityProvider`, `_AuthorizationPolicy`, `_WorkspaceRegistry`, `_Storage` | Complete `CorePorts`-shaped fake dependency tree for unit-testing query services. Reusable for rollup service unit tests once the rollup service exists. | Yes — reuse as the service-layer fake harness. |

**Count of reusable existing fixtures: 5 distinct patterns (across 4 files)**

No dedicated `conftest.py` exists; no shared fixture factories or `pytest.fixture` declarations were found. All existing patterns are unittest-style class setup methods.

### 3.2 Gap Analysis

| Gap | Description | Tier(s) Affected | Blocking for Phase 5? |
|---|---|---|---|
| **G-01** No session seed helper | No helper inserts rows into `sessions` + `session_feature_links` tables. The fake repos mock the layer; no real DB session seeding exists. | SMALL, MEDIUM, LARGE | Yes — rollup queries run against real DB; fake repos cannot test the SQL aggregate path. |
| **G-02** No links table seed helper | No helper seeds the `links` table (feature→doc, feature→session, feature→task relations). `_FakeLinkRepo` mocks the interface; no SQL seeder exists. | SMALL, MEDIUM, LARGE | Yes — `linkedDocCount`, `linkedDocCountsByType`, `linkedTaskCount` all read the `links` table. |
| **G-03** No multi-feature fixture set | All existing seeding is single-feature or 5 small features. No fixture covers the MEDIUM/LARGE cardinality needed for batch rollup testing (`POST /api/v1/features/rollups` with 40–100 IDs). | MEDIUM, LARGE | Yes — rollup batch endpoint cannot be load-tested without it. |
| **G-04** No subthread session fixtures | No existing test seeds sessions with non-null `parent_session_id`. `_FakeSessionRepo` has `parent_session_id: None` hardcoded. `unresolvedSubthreadCount` and `subthreadCount` cannot be tested against real SQL without this. | SMALL, MEDIUM, LARGE | Yes — two rollup fields are untestable without subthread rows. |
| **G-05** No doc-type seed helper | No helper seeds `documents` + links between features and documents. `LinkedDocument` is used in router tests but only via fake repos, not real DB rows. | SMALL, MEDIUM, LARGE | Yes — `linkedDocCountsByType` aggregate requires real `documents` rows with `doc_type`. |
| **G-06** No test-health seed helper | No helper seeds `feature_test_health` rows. `testCount` / `failingTestCount` rollup fields cannot be integration-tested. | SMALL, MEDIUM, LARGE | Partial — these fields are `include.testCount=false` by default; non-blocking for first Phase 5 milestone but blocks full rollup field coverage. |
| **G-07** No frontend MSW fixtures | `ProjectBoard.featureModal.test.tsx` mocks `useData()` with an empty `features: []` array and asserts on tab resolution logic only. There are no MSW response fixtures for rollup or section endpoints. No shared JSON source-of-truth exists between backend and frontend test data. | Frontend | Yes — frontend parity tests cannot assert card metric values without MSW fixtures that match the backend fixture output. |
| **G-08** No LARGE-tier performance fixture | No mechanism to generate and seed 200 features × 4 000 sessions. Needed for query-plan validation and latency budgets. | LARGE | Not blocking Phase 5 milestone 1; blocking the full performance gate. |
| **G-09** No "old path" rollup reference values | No test computes `buildFeatureSessionSummary` + the old per-feature derived values from a fixture, so there is nothing to assert parity against. The old-path reference values must be generated from the fixture and stored as snapshots before the new path is tested. | SMALL (all tiers for parity) | Yes — without the old-path snapshot, parity cannot be proven by definition. |

**Count of gaps: 9**

---

## 4. Generator Strategy and File Layout

### 4.1 Strategy: Pytest Factory Functions Over In-Memory SQLite

**Recommendation: pytest fixture factories (not SQL seed files, not JSON blobs).**

Rationale:

- The existing codebase uses `unittest.IsolatedAsyncioTestCase` + `aiosqlite` in-memory or temp-file SQLite for all repository-level tests. A pytest factory layer can be used from both `unittest` and `pytest`-style tests.
- SQL seed files (`.sql`) would need to be maintained in lock-step with migration changes. The migration runner is already the authority on schema; seeding should go through the same `upsert` methods the sync engine uses, which catches schema drift automatically.
- JSON blobs exported from the generator serve as the MSW source of truth for frontend tests, but the generator that produces them must be Python-side (the backend owns the canonical shape). The JSON blobs are derived artifacts of the factory, not the primary definition.
- The fake repo pattern (`_FakeSessionRepo`, `_FakeLinkRepo`) is retained for unit tests of query services and router handlers, where the SQL aggregate behavior is not under test. Real-DB fixtures are used only for integration and parity tests that must exercise the SQL layer.

**Factory design:**

Each tier is a parameterized factory function that accepts a `seed: int` and returns a `FixturePack` (a dataclass holding the temp DB path, the list of inserted feature IDs, and metadata for assertions). The factory uses the existing `_run_migrations_sync` + direct `sqlite3` insertions pattern, extended to cover all needed tables.

### 4.2 Proposed File Layout

```
backend/tests/fixtures/feature_surface/
  __init__.py
  builders.py          # Core factory: build_feature_surface_fixture(tier, seed)
                       # Returns FixturePack(db_path, feature_ids, session_ids, doc_ids, meta)
  tiers.py             # SMALL_SPEC, MEDIUM_SPEC, LARGE_SPEC dataclasses (counts, distributions)
  old_path_reference.py  # Computes buildFeatureSessionSummary-equivalent in Python for parity baseline
  snapshots/
    small_rollup_expected.json    # Generated; checked into repo; updated by make-snapshots script
    medium_rollup_expected.json
    small_session_summary_legacy.json  # Old-path baseline values for parity assertion
    medium_session_summary_legacy.json

backend/tests/
  test_feature_surface_rollup_parity.py   # Phase 5 parity tests (SMALL, MEDIUM)
  test_feature_surface_performance.py    # Phase 5 performance tests (MEDIUM, LARGE)

# Frontend (JSON snapshots shared from backend build)
src/__tests__/fixtures/feature_surface/
  small_rollup_response.json    # Copied from backend snapshot by `npm run sync-fixtures`
  medium_rollup_response.json
  small_modal_overview_response.json
  small_sessions_page_response.json
```

The `npm run sync-fixtures` script (shell one-liner) copies the JSON snapshots from `backend/tests/fixtures/feature_surface/snapshots/` into the frontend fixtures directory. This is the single source of truth for both backend integration tests and frontend MSW handlers: the backend generates the data, the frontend consumes the same JSON.

---

## 5. Parity Test Shape

Each parity test follows the same three-step pattern:

1. **Generate fixture** via `build_feature_surface_fixture("small", seed=42)`.
2. **Compute old-path reference** by calling `old_path_reference.compute_legacy_summary(fixture.db_path, feature_id)` — a Python reimplementation of the frontend's `buildFeatureSessionSummary` that reads raw session rows from the DB and applies the same aggregation logic. This produces the pre-redesign baseline.
3. **Call new endpoint** via `TestClient.post("/api/v1/features/rollups", json={...})` and assert new-path value matches baseline within tolerance.

```python
# Illustrative shape (not final code)
class TestRollupParity_Small(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture = build_feature_surface_fixture("small", seed=42)
        cls.legacy = compute_legacy_summaries(cls.fixture)  # old-path baseline
        # ... bootstrap app pointing at fixture.db_path ...

    def test_session_count_exact(self):
        feat_id = self.fixture.feature_ids[0]
        rollup = self._get_rollup(feat_id)
        expected = self.legacy[feat_id]["total"]          # old path: len(sessions)
        actual   = rollup["sessionCount"]                  # new path: SQL COUNT(*)
        self.assertEqual(expected, actual)                 # tolerance: exact

    def test_primary_session_count_exact(self):
        feat_id = self.fixture.feature_ids[0]
        rollup = self._get_rollup(feat_id)
        expected = self.legacy[feat_id]["mainThreads"]
        actual   = rollup["primarySessionCount"]
        self.assertEqual(expected, actual)                 # tolerance: exact

    def test_observed_tokens_exact(self):
        feat_id = self.fixture.feature_ids[0]
        rollup = self._get_rollup(feat_id)
        expected = self.legacy[feat_id]["workloadTokens"]
        actual   = rollup["observedTokens"]
        self.assertEqual(expected, actual)                 # tolerance: exact (deterministic seed)

    def test_display_cost_within_tolerance(self):
        feat_id = self.fixture.feature_ids[0]
        rollup = self._get_rollup(feat_id)
        expected = self.legacy[feat_id]["totalDisplayCost"]
        actual   = rollup["displayCost"]
        self.assertAlmostEqual(expected, actual, places=6)  # tolerance: float rounding only

    def test_linked_doc_count_exact(self):
        feat_id = self.fixture.feature_ids[0]
        rollup = self._get_rollup(feat_id)
        expected = len(self.fixture.doc_ids_by_feature[feat_id])
        actual   = rollup["linkedDocCount"]
        self.assertEqual(expected, actual)                  # tolerance: exact (links table)

    def test_workflow_types_coverage(self):
        feat_id = self.fixture.feature_ids[2]
        rollup = self._get_rollup(feat_id)
        expected_workflows = self.legacy[feat_id]["byType_keys"]
        actual_workflows   = {w["workflow"] for w in rollup["workflowTypes"]}
        self.assertEqual(expected_workflows, actual_workflows)  # tolerance: exact set equality

    def test_orphan_feature_zero_sessions(self):
        feat_id = self.fixture.zero_session_feature_id
        rollup = self._get_rollup(feat_id)
        self.assertEqual(rollup["sessionCount"], 0)
        self.assertIsNone(rollup["latestSessionAt"])
        # precision must be exact (no sync data means no eventually_consistent fields in play)
        self.assertEqual(rollup["precision"], "exact")

    def test_unresolved_subthread_count(self):
        feat_id = self.fixture.orphan_subthread_feature_id  # LARGE only
        rollup  = self._get_rollup(feat_id)
        # The subthread's parent is outside the feature's session set
        self.assertGreaterEqual(rollup["unresolvedSubthreadCount"], 1)
        self.assertEqual(rollup["precision"], "partial")
```

### Metric-level tolerance table

| Metric | Old-path source | New-path field | Tolerance |
|---|---|---|---|
| `sessionCount` | `buildFeatureSessionSummary(sessions).total` | `rollup.sessionCount` | `exact` |
| `primarySessionCount` | `summary.mainThreads` | `rollup.primarySessionCount` | `exact` |
| `subthreadCount` | `summary.subThreads` | `rollup.subthreadCount` | `exact` |
| `unresolvedSubthreadCount` | `summary.unresolvedSubThreads` | `rollup.unresolvedSubthreadCount` | `exact` (deterministic fixture; `partial` precision flag must be set) |
| `observedTokens` | `summary.workloadTokens` (sum of `resolveTokenMetrics`) | `rollup.observedTokens` | `exact` |
| `modelIOTokens` | Sum of `session.modelIOTokens` | `rollup.modelIOTokens` | `exact` |
| `cacheInputTokens` | Sum of `session.cacheInputTokens` | `rollup.cacheInputTokens` | `exact` |
| `displayCost` | Sum of `resolveDisplayCost(session)` | `rollup.displayCost` | `abs diff < 1e-6` (float arithmetic) |
| `totalCost` | Sum of `session.totalCost` | `rollup.totalCost` | `abs diff < 1e-6` |
| `workflowTypes[].workflow` set | Set of `getCoreSessionGroupId(s)` buckets used in `byType[]` | `{w["workflow"] for w in rollup.workflowTypes}` | `exact set equality` |
| `workflowTypes[].sessionCount` | Count of sessions per bucket | `rollup.workflowTypes[i].sessionCount` | `exact` |
| `linkedDocCount` | `feature.linkedDocs.length` (from list DTO) | `rollup.linkedDocCount` | `exact` |
| `linkedDocCountsByType` | `buildLinkedDocTypeCounts(feature.linkedDocs)` | `rollup.linkedDocCountsByType` | `exact` per-type |
| `latestSessionAt` | `MAX(session.startedAt)` over linked sessions | `rollup.latestSessionAt` | `exact` (ISO8601 string match) |
| `testCount` | `featureTestHealth.totalTests` | `rollup.testCount` | `exact` (when `include.testCount=true`) |
| `failingTestCount` | `featureTestHealth.failingTests` | `rollup.failingTestCount` | `exact` |
| `linkedCommitCount` | `gitHistoryData.commits.length` | `rollup.linkedCommitCount` | `exact` |

**"Eventually consistent" note:** All session-derived fields are `eventually_consistent` in the rollup DTO's precision taxonomy, but with a deterministic fixture using a frozen sync state, the values are reproducibly exact in tests. The `eventually_consistent` label governs production staleness behavior; in tests, fixtures are considered "fully synced" at fixture creation time.

---

## 6. Performance Test Shape

Performance tests run against MEDIUM and LARGE tiers only. They do not assert correctness of values — that is parity-test scope — they assert request lifecycle measurements.

### 6.1 What Is Measured

| Metric | Measurement Method | MEDIUM Target | LARGE Target |
|---|---|---|---|
| **Backend query count per rollup batch** | Patch `aiosqlite.Connection.execute` to count calls; assert total calls for a batch of 40 IDs stays below N | ≤ 5 DB round-trips for a batch of 40 IDs (1 aggregation CTE, 1 doc counts, 1 task counts, 1 test health, 1 meta) | ≤ 5 DB round-trips for a batch of 100 IDs (same queries, larger IN-list) |
| **Rollup endpoint response time (P50)** | `timeit` loop over 10 cold calls (cache bypassed via `CCDash-Cache-Control: no-store`); assert median | < 150 ms | < 500 ms |
| **Rollup payload size** | `len(json.dumps(response.json()))` | < 20 KB for 40-feature batch | < 50 KB for 100-feature batch |
| **Feature list endpoint response time (P50)** | Same timeit loop | < 100 ms for `limit=50` with status + category filters | < 200 ms for `limit=50` with all Phase 1 filters applied |
| **Feature list payload size** | Same as rollup | < 30 KB for 50 features | < 30 KB for 50 features (same page size) |
| **Modal overview shell response time (P50)** | Single feature fetch with overview shell fields | < 80 ms | < 100 ms |
| **Sessions paginated endpoint response time (P50)** | First page, `limit=20`, no includes | < 100 ms | < 200 ms (feature with 50 sessions) |
| **Per-board-load API call count** | Count distinct HTTP calls from `TestClient` during a simulated board render (fetch 40 features + rollup batch + no linked-session calls) | = 2 calls (1 list + 1 rollup batch) | = 2 calls |

### 6.2 Test File Structure

```python
# backend/tests/test_feature_surface_performance.py

class TestRollupPerformance_Medium(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture = build_feature_surface_fixture("medium", seed=42)
        # ... bootstrap app ...

    def test_rollup_batch_query_count_bounded(self):
        # Patch DB execute, call rollup, assert call count <= 5
        ...

    def test_rollup_batch_latency_p50(self):
        # 10 iterations, assert median < 150ms
        ...

    def test_rollup_payload_size(self):
        # Assert len(json.dumps(body)) < 20_000
        ...

    def test_board_load_call_count(self):
        # Simulate board: GET /api/v1/features + POST /api/v1/features/rollups
        # Assert no calls to /api/features/{id}/linked-sessions
        call_log = []
        # ... instrument client ...
        self.assertEqual(
            sum(1 for c in call_log if "linked-sessions" in c["path"]), 0
        )
        self.assertEqual(len(call_log), 2)

class TestRollupPerformance_Large(unittest.TestCase):
    # Same tests, LARGE fixture, relaxed latency budgets
    ...
```

---

## 7. Frontend Mock Strategy

### 7.1 MSW Handler Shape

Frontend parity tests need MSW handlers for four new endpoints:

| Endpoint | MSW handler | JSON source |
|---|---|---|
| `POST /api/v1/features/rollups` | `http.post('/api/v1/features/rollups', resolver)` | `small_rollup_response.json` (keyed by featureId) |
| `GET /api/v1/features` | `http.get('/api/v1/features', resolver)` | `small_feature_list_response.json` |
| `GET /api/v1/features/:featureId` | `http.get('/api/v1/features/:featureId', resolver)` | `small_modal_overview_response.json` per ID |
| `GET /api/v1/features/:featureId/sessions` | `http.get('/api/v1/features/:featureId/sessions', resolver)` | `small_sessions_page_response.json` |

The `ProjectBoard.featureModal.test.tsx` already demonstrates the mock pattern (`vi.mock('../../contexts/DataContext')`). For parity tests, the pattern upgrades from mocking `useData()` to intercepting the HTTP layer via MSW so the actual hooks (`useFeatureRollup`, `useFeatureModalOverview`, etc.) run and parse the JSON shapes.

### 7.2 Single Source of Truth Sync

The JSON fixture files are **generated by the Python backend factory**, not written by hand:

```
# In CI / developer workflow:
python -m backend.tests.fixtures.feature_surface.builders export-snapshots \
    --tier small --seed 42 --out backend/tests/fixtures/feature_surface/snapshots/
npm run sync-fixtures  # copies snapshots/ → src/__tests__/fixtures/feature_surface/
```

This ensures:
- Column shape changes in the backend repository layer automatically propagate to frontend test fixtures on next snapshot regeneration.
- Frontend tests fail if they diverge from the backend contract (because the JSON snapshot is stale), not silently pass with invented values.
- The `npm run sync-fixtures` diff is reviewable in PRs alongside the backend change.

### 7.3 Rollup MSW Handler Pattern

```typescript
// src/__tests__/fixtures/feature_surface/handlers.ts
import { http, HttpResponse } from 'msw';
import smallRollupResponse from './small_rollup_response.json';

export const featureSurfaceHandlers = [
  http.post('/api/v1/features/rollups', async ({ request }) => {
    const body = await request.json() as { featureIds: string[] };
    const rollups: Record<string, unknown> = {};
    for (const id of body.featureIds) {
      if (id in smallRollupResponse.rollups) {
        rollups[id] = smallRollupResponse.rollups[id];
      }
    }
    return HttpResponse.json({
      rollups,
      missing: body.featureIds.filter(id => !(id in smallRollupResponse.rollups)),
      errors: {},
      generatedAt: '2026-04-23T00:00:00Z',
      cacheVersion: 'test-v1',
    });
  }),
];
```

### 7.4 Frontend Parity Assertion Pattern

```typescript
// Asserts that the rendered card token badge matches the rollup value
it('card displays observedTokens from rollup without fetching linked-sessions', async () => {
  const server = setupServer(...featureSurfaceHandlers);
  server.listen();
  // render <ProjectBoard /> with FEATURE_SURFACE_V2 flag enabled
  // assert no requests to /api/features/*/linked-sessions fired
  // assert token badge text matches smallRollupResponse.rollups[featId].observedTokens
  server.close();
});
```

---

## 8. Reproducibility and CI Plan

### 8.1 Deterministic Seeds

All fixture builders accept a `seed: int` parameter. Randomized values (token counts, cost amounts, dates, status assignments) are generated with `random.Random(seed)` seeded before first use, and `datetime` values are offset from a frozen epoch (`FIXTURE_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)`). The seed is stored in the `FixturePack.meta` dict so assertion failures can reference it in the error message.

Frozen timestamps use `FIXTURE_EPOCH + timedelta(days=i * delta_days)` for date spreads. No `datetime.now()` calls appear in fixture generation code.

The Python `random.Random` instance is not the global `random` module — all other code using global `random` state is unaffected.

### 8.2 CI Strategy

| Tier | When to Run | Rationale |
|---|---|---|
| **SMALL** | Every PR, every commit (fast: < 5 s) | Correctness smoke gate; fixture is tiny, SQLite in-memory, no I/O. Must stay green before any merge. |
| **MEDIUM** | Every PR on backend-touching changes, plus scheduled nightly | Integration gate; covers all rollup fields, batch sizing, filter parity. ~30–60 s. Skip on purely frontend-only PRs via path filters. |
| **LARGE** | Nightly only (not on every PR) | Stress gate; fixture generation alone takes ~10–30 s. Nightly failures create issues; not a merge blocker. |
| **Performance tests (MEDIUM)** | Nightly + manually triggered on perf-critical PRs | `test_feature_surface_performance.py` with MEDIUM tier. Latency assertions assume CI hardware baseline; assertions use relative multipliers (e.g., P50 < 5× the P50 of the SMALL tier on same hardware) to avoid flakiness. |
| **Performance tests (LARGE)** | Nightly only | Same as LARGE correctness. |

**Snapshot regeneration policy:** Snapshots in `backend/tests/fixtures/feature_surface/snapshots/` are committed artifacts. A CI step (`make check-snapshots`) regenerates them and diffs the output; a non-empty diff fails the check with a message: "Fixture snapshots are stale — run `make regen-snapshots` and commit the result." This prevents silent drift between the fixture generator and the committed JSON.

---

## 9. Open Questions

1. **`buildFeatureSessionSummary` Python reimplementation scope.** The `old_path_reference.py` module must reimplement the frontend's `buildFeatureSessionSummary` and `resolveTokenMetrics` helpers in Python so the old-path baseline can be generated from fixture data. The key risk is subtle behavioral differences (e.g., the `hasLinkedSubthreads` cross-check, the `resolveDisplayCost` fallback chain). These helpers should be ported from `components/ProjectBoard.tsx` and validated against `_FakeSessionRepo` test data before Phase 5 parity assertions go green. Recommend assigning this as a standalone P5 task.

2. **`workflowTypes` bucketing vs `getCoreSessionGroupId`.** The rollup DTO's `workflowTypes` field groups by raw `workflow_type` column value, while the frontend's `byType[]` in `FeatureSessionSummary` uses `getCoreSessionGroupId` (a heuristic that maps `workflowType` + `sessionType` + `commands[]` + `title` patterns to broader buckets like `plan`, `execution`, `other`). The parity assertion for this field must decide: (a) assert the raw `workflow_type` distribution matches, or (b) add a server-side `getCoreSessionGroupId` equivalent to the rollup. If (a), the `byType[]` card tooltip changes appearance (more granular), which is a product decision. Needs resolution before Phase 5 parity tests are written for this field.

3. **LARGE fixture generation time.** Inserting ~4 000 sessions × all linked tables synchronously may take tens of seconds. If this is prohibitively slow for nightly CI, the LARGE tier may need to use a pre-built SQLite file committed to the repo (a `.db` file artifact in `backend/tests/fixtures/feature_surface/`) rather than being generated per-run. This conflicts with the "no binary blobs in git" preference; the alternative is a `make build-large-fixture` step that is cached by CI.

4. **Postgres parity.** The fixture builders described here target SQLite only. Phase 1 and Phase 2 will add a Postgres repository implementation. Phase 5 parity tests should run against both backends. A `CCDASH_DB_BACKEND=postgres` CI job variant is needed, which requires a Postgres service container in CI. This is out of scope for the fixture plan itself but must be noted as a Phase 5 dependency.

5. **`npm run sync-fixtures` reliability.** If the frontend build toolchain or CI does not have Python available at the step that generates snapshots, the sync will fail silently. The `make check-snapshots` step must run after `pytest` completes and before the frontend test job starts. CI job ordering must encode this dependency explicitly.

6. **Rollup endpoint does not exist yet.** `POST /api/v1/features/rollups` has no backend implementation at the start of Phase 5. The parity test file will fail to compile useful assertions until Phase 2/3 delivers the endpoint. Recommendation: write `test_feature_surface_rollup_parity.py` as a set of `@unittest.skip("Pending Phase 2 rollup endpoint")` tests from day one, removing the skip decorator as each endpoint ships. This keeps the test file in the repo and visible without blocking other CI runs.
