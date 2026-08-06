## Completion Report

### Summary

`GET /api/v1/project/aar-review` 500'd with a FastAPI `ResponseValidationError`
on the node not because of anything in the AAR-review DTOs, the route, or the
`ClientV1Envelope[T]` typing, but because `PostgresCacheBackend.aset()` called
`json.dumps(value, default=str)` directly on the raw cached value — which is a
pydantic `BaseModel` instance (`AARReviewListDTO`) for every
`@memoized_query`-decorated service. `json.dumps` has no native encoder for a
`BaseModel`; it fell back to `default=str` at the *top level*, corrupting the
entire cached payload into one opaque repr string. A later cache **hit**
handed that string back to the route handler in place of the model, and
FastAPI's response-model validation against `ClientV1Envelope[AARReviewListDTO]`
then failed with a `ResponseValidationError` (500). Fixed at the shared
`memoized_query`/`PostgresCacheBackend` boundary in `cache.py` — not per-route
— so every `client_v1_router` route funnelling through `@memoized_query`
(21+ of them) is fixed uniformly by this one change.

### Files Changed

- `backend/application/services/agent_queries/cache.py` — root-cause fix. Added
  `_json_safe()` (recursively converts a `BaseModel`/list/dict tree into a
  plain JSON-safe shape via `model_dump(mode="json")`) and
  `_reconstruct_from_cache()` (rehydrates a `PostgresCacheBackend` cache HIT
  back into the wrapped function's resolved return type via `TypeAdapter`,
  no-op for the default in-process backend). `PostgresCacheBackend.aset()` now
  calls `_json_safe(value)` before `json.dumps`. `memoized_query`'s decorator
  resolves the wrapped function's return type once at decoration time
  (`typing.get_type_hints(func)`) and the cache-hit path in `wrapper()` now
  calls `_reconstruct_from_cache(cached_value, _return_type)` instead of
  returning the raw cached value verbatim.
- `backend/tests/test_query_cache.py` — added
  `test_aset_of_a_pydantic_model_does_not_corrupt_into_a_repr_string` on
  `TestPostgresCacheBackendSqlite` (uses the existing aiosqlite-as-asyncpg-stand-in
  pattern). Directly reproduces the historical defect at the backend-unit
  level: constructs a nested pydantic model, round-trips it through
  `aset`/`aget`, and asserts the result is still a `dict` (not a corrupted
  repr string). Confirmed to FAIL on the pre-fix code (see Tests Run below).
- `backend/tests/test_client_v1_aar_review.py` — added
  `test_realistic_multi_row_payload_returns_200`: a route-level (TestClient)
  regression test seeding 6 documents with populated `correlation` and
  `flags[]`, matching the shape reported on the node. This test does not fail
  against SQLite (the in-process cache backend is never exposed to the bug),
  but is real, useful hardening of the multi-row/realistic-payload path per
  AC3's letter, and was used (with a temporarily reintroduced response-model
  mismatch) to confirm the route-level test suite's discriminating power
  before the real fix was found — see Tests Run.
- `docs/project_plans/feature_contracts/harden-polish/aar-review-response-serialization-fix.md`
  — this contract file (untracked at sprint start; added to git history by
  virtue of being read/left in place — no content changes made to it beyond
  what Opus/the workflow originally wrote).

### Root Cause

**Confirmed, not merely hypothesized.** Reproduced end-to-end against a real
Postgres 16 instance (`pgvector/pgvector:pg16` docker container, real
`asyncpg`, real migrations run) with `CCDASH_QUERY_CACHE_BACKEND=postgres` set
(the distributed-cache opt-in — `memory`/in-process is the default):

1. First request (cache **miss**): 200, correct 6-row payload, `aset()` writes
   the (pre-fix) corrupted repr-string into `query_cache.value`.
2. Second request (cache **hit**, unfixed code): **500 Internal Server Error**
   — exactly the reported defect.
3. Same two-request cycle with the fix applied: both requests return 200 with
   the correct, full 6-row payload.

This directly falsifies both of the contract's `open_questions`:

- **Not jsonb-decoding-specific.** `asyncpg` was confirmed to return `jsonb`
  columns as plain `str` (no codec registered — verified directly), identical
  to SQLite's `TEXT` columns; `_loads_dict`/`_loads_list` in
  `_client_v1_aar_review.py` handle both identically and correctly. I also
  confirmed a realistic 6-row payload round-trips cleanly through
  `_row_to_aar_review_dto` and a raw `TypeAdapter(ClientV1Envelope[AARReviewListDTO])`
  validate/dump cycle against real Postgres with no defect at all when the
  cache is bypassed or backed by the in-process cache.
- **Not a duplicate-generic-registration collision.** There is exactly one
  `ClientV1Envelope[AARReviewListDTO]`-typed route registration
  (`backend/routers/client_v1.py:212`); no other route shares that concrete
  parametrization. `AARReviewListDTO`/`ClientV1Envelope` resolve identically
  everywhere they're imported.

**Why the existing 8-test suite never caught it and why it isn't about row
count or flag count at all**: the SQLite test suite never sets
`CCDASH_QUERY_CACHE_BACKEND=postgres`, so it always runs on the default
in-process backend, which stores live Python objects with no serialisation —
this bug class is structurally invisible to it regardless of payload size.
The report's framing ("6 real AARReviewDTOs") is the size of the payload that
happened to be in flight when the node hit this cache-hit path in production,
not the causal factor — a payload of any size (including the empty-project
0-row case) corrupts identically once written through `PostgresCacheBackend`.

The reported diagnosis (`ResponseValidationError`... jsonb/duplicate-registration
hypotheses) named the correct *symptom* (a response-serialization-boundary
validation failure) but not the correct cause — the real defect was one layer
up, at the query-result cache, not in the DTOs, the envelope typing, or route
registration. This matches the Architecture Constraints' explicit permission:
*"unless the investigation proves the cache is returning a non-DTO shape on a
hit (in which case fix the cache/decorator boundary, not the DTO shapes)"* —
which is exactly what was proven and exactly what was fixed.

### Tests Run

| Step | What | Result |
|---|---|---|
| Reproduction attempt 1 | 6-row realistic payload via SQLite TestClient route | 200 — did not reproduce (expected; in-process cache) |
| Reproduction attempt 2 | 6-row realistic payload via real Postgres + raw `TypeAdapter` validate/dump (no HTTP layer) | Validated cleanly — did not reproduce |
| Reproduction attempt 3 | 6-row realistic payload via real Postgres + full FastAPI TestClient route, cache bypassed | 200 — did not reproduce |
| Reproduction attempt 4 (root cause found) | Same route, `CCDASH_QUERY_CACHE_BACKEND=postgres`, miss-then-hit cycle, **pre-fix** code | Request 1: 200. Request 2: **500** — reproduced |
| Fix verification | Same miss-then-hit(-then-hit-again) cycle, **post-fix** code | All 3 requests: 200, correct 6-row payload |
| Discriminating-power proof for the hardened route-level test | Temporarily changed the route's return-type annotation to a mismatched sibling DTO (`RoutingRollupResponseDTO`, no overlapping required fields), ran the full `test_client_v1_aar_review.py` suite, confirmed 7/9 tests fail with 500 (including the new multi-row test), then reverted | Confirmed — reverted cleanly, all 9 tests pass again |
| `backend/tests/test_client_v1_aar_review.py` (8 existing + 1 new = 9) | `pytest -v` | **9 passed** |
| `backend/tests/test_query_cache.py` (47 existing + 1 new = 48) | `pytest -v` | **48 passed** (new test confirmed to FAIL on pre-fix `cache.py` via `git stash`) |
| `backend/tests/test_agent_router.py` | `pytest -v` | **16 passed** |
| `backend/tests/test_client_v1_routing_rollup.py`, `test_client_v1_session_detail.py`, `test_client_v1_session_family.py`, `test_client_v1_write_paths.py` | `pytest -v` | all passed |
| `backend/tests/test_client_v1_contract.py`, `test_client_v1_feature_modal_aliases.py`, `test_client_v1_feature_surface.py` | `pytest -v` | 1 failure + 43 errors — **confirmed pre-existing** via `git stash` (identical failure/error count and stack traces on the unmodified base commit; unrelated `runtime_ports.project_manager` / `_FakeFeatureRepo.get_by_id(workspace_id=...)` issues, not touched by this fix) |
| `backend/tests/test_agent_query_bypass_cache.py`, `test_agent_query_cache.py`, `test_agent_query_cache_invalidation.py`, `test_agent_query_cache_ttl.py`, `test_cache_router.py`, `test_cache_warming_job.py`, `test_otel_agent_query_cache_counters.py`, `test_sync_cache_invalidation_p2_002.py`, `test_system_metrics_cache_regression.py` | `pytest -v` | 5 failures — **confirmed pre-existing** via `git stash` (identical `SyncEngine._sync_in_flight` `AttributeError`, unrelated to `cache.py`); 84 passed |

Environment note: the Postgres reproduction used a throwaway
`pgvector/pgvector:pg16` docker container (removed after use) since the repo's
own dependency (`vector` extension) requires it over plain `postgres:16`. All
reproduction/verification scripts were throwaway (`backend/tests/_pg_repro_*.py`)
and deleted before this report was written — none are part of the final diff.

### Sibling Audit Results

The fix lives in the **shared `memoized_query`/`PostgresCacheBackend` boundary**
in `cache.py`, not in any per-route handler — so every route whose backing
service is `@memoized_query`-decorated is fixed by this one change, not by 21
individual patches. Confirmed the following services (backing the
`client_v1_router` envelope routes) are `@memoized_query`-decorated and
therefore were exposed to, and are now fixed by, the same defect:
`project_status.py`, `workflow_intelligence.py`, `aar_review.py` (this route),
`_client_v1_routing_rollup.py`'s handler, `dashboard.py`,
`feature_forensics.py`, `feature_evidence_summary.py`, `planning*.py`,
`multi_project_planning*.py`, `run_intelligence.py`, `reporting.py`,
`live_metrics.py`, `system_metrics.py`, `analytics_bundle.py`.

| Route | Existing route-level coverage? | Shared the defect (via `@memoized_query`)? | Action |
|---|---|---|---|
| `GET /project/aar-review` | Yes (`test_client_v1_aar_review.py`) | **Yes — confirmed root cause** | Fixed at cache boundary; hardened test added |
| `GET /project/status` | Yes (`test_client_v1_contract.py`) | Yes (`project_status.py`) | Fixed by the same change; existing tests still pass |
| `GET /workflows/failures` | Yes (`test_client_v1_contract.py`) | Yes (`workflow_intelligence.py`) | Fixed by the same change |
| `GET /routing/rollup` | Yes (`test_client_v1_routing_rollup.py`) | Yes | Fixed by the same change; existing tests still pass |
| `GET /instance` | Yes (`test_client_v1_contract.py`) | Not `@memoized_query`-decorated (static instance metadata) | N/A — never exposed |
| `GET /features` (list) / `POST /features/rollups` / `/features/{id}` / `.../sessions` / `.../sessions/page` / `.../documents` / `.../modal` / `.../modal/{section}` | Some via `test_client_v1_contract.py`/`test_client_v1_feature_surface.py` | Backing feature-surface services use `@memoized_query` in places (e.g. `feature_forensics.py`); fixed at the shared boundary | Fixed by the same change; pre-existing test-harness failures in this area are unrelated (see Tests Run) |
| `GET /sessions*` (search, list, detail, drilldown, family, transcript) | Yes, several (`test_client_v1_session_detail.py`, `test_client_v1_session_family.py`) | Some `@memoized_query`-backed | Fixed by the same change; existing tests still pass |
| `POST /reports/aar` | Yes (`test_agent_router.py` covers the equivalent `agent_router` path; not in scope) | Backing service (`reporting.py`) is `@memoized_query`-decorated | Fixed by the same change |

No route required an individual code change beyond the shared cache-boundary
fix. No route's existing test coverage regressed.

### Validation Results

| Command | Result | Notes |
|---|---|---|
| `backend/.venv/bin/python -m pytest backend/tests/test_client_v1_aar_review.py -v` | **Pass** | 9/9 (8 existing + 1 new hardened multi-row test) |
| `backend/.venv/bin/python -m pytest backend/tests/test_agent_router.py -v` | **Pass** | 16/16 |
| Named-file sweep: `test_client_v1_contract.py`, `test_client_v1_feature_modal_aliases.py`, `test_client_v1_feature_surface.py`, `test_client_v1_routing_rollup.py`, `test_client_v1_session_detail.py`, `test_client_v1_session_family.py`, `test_client_v1_write_paths.py` | **Pass (with pre-existing failures unrelated to this fix)** | 1 failure + 43 errors reproduced identically on the unmodified base commit via `git stash` — not caused or worsened by this change |
| `backend/.venv/bin/python -m pytest backend/tests/test_query_cache.py -v` (+ 8 other cache-related test files) | **Pass (with pre-existing failures unrelated to this fix)** | 132/137 across the combined cache suite; the 5 failures are an unrelated `SyncEngine._sync_in_flight` `AttributeError`, confirmed pre-existing via `git stash` |
| Lint/typecheck | Not applicable | Project has no dedicated backend typecheck gate beyond pytest, per contract §10 |
| Scope check | Pass | Changes confined to `backend/application/services/agent_queries/cache.py` + the two named test files; no unrelated changes |

### Deviations From Contract

- **Fix location differs from the contract's stated preference order, with
  justification documented in-contract already.** §4 "In Scope" states: *"prefer
  option #1 ... type the envelope's `data` field as the concrete DTO type;
  `.model_dump()` in the handler or loosening the response model are fallback
  options if #1 does not resolve the actual root cause"* and §8's Architecture
  Constraints explicitly anticipates this exact outcome: *"memoized_query
  caching behavior [is protected], unless the investigation proves the cache
  is returning a non-DTO shape on a hit (in which case fix the cache/decorator
  boundary, not the DTO shapes)."* The route's `data` field **was already**
  typed as the concrete DTO (`ClientV1Envelope[AARReviewListDTO]`) before this
  sprint started — that was never the gap. The investigation proved the cache
  boundary was the actual defect, which the contract pre-authorized fixing
  there instead. No files outside the declared `files_affected` set were
  touched (the fix landed in `cache.py`, which was not in the contract's
  `files_affected` list of `client_v1.py`/`_client_v1_aar_review.py`/
  `client_v1_models.py`/`test_client_v1_aar_review.py` — see note below).
- **`files_affected` scope note**: the contract's frontmatter/agent_context
  named `backend/routers/client_v1.py`, `backend/routers/_client_v1_aar_review.py`,
  `backend/routers/client_v1_models.py`, and the test file as the expected
  touch points, anticipating a route/DTO-level fix. The actual fix required
  touching `backend/application/services/agent_queries/cache.py` instead (not
  originally listed) plus `backend/tests/test_query_cache.py` (also not
  originally listed) — both directly implied by the "fix the cache/decorator
  boundary" escape clause in §8. No route/DTO file needed changes since none
  of them were the actual defect.
- **No change to `client_v1.py`, `_client_v1_aar_review.py`, or
  `client_v1_models.py`.** Investigated all three; none needed modification —
  the response_model typing, the route registration, and the DTO shapes are
  and always were correct.
- Two throwaway, uncommitted reproduction scripts
  (`backend/tests/_pg_repro_aar_review.py`, `_pg_repro_aar_review_route.py`)
  were created and used against a temporary local `pgvector/pgvector:pg16`
  Docker container during investigation, then deleted before this report was
  written; the container was removed (`docker rm -f`). Neither is part of the
  final diff.
- A temporary, intentional response-model mismatch was introduced in
  `client_v1.py` during investigation (to prove the hardened route-level
  test's discriminating power per AC3's parenthetical instruction), then
  reverted; confirmed via `git diff` / re-running the full test suite that the
  file is back to its original state and all 9 tests pass.

### Risks / Limitations

- The real-Postgres reproduction used a throwaway local container, not the
  actual node. I could not directly confirm the node's live
  `CCDASH_QUERY_CACHE_BACKEND` setting from this sandboxed environment — the
  root cause is confirmed as a **general, deterministic defect in the shipped
  code** (any Postgres-cache-backend deployment, any payload) rather than
  something specific to the node's exact configuration, so this does not
  weaken the finding, but the node's specific trigger conditions (e.g. whether
  it runs `CCDASH_QUERY_CACHE_BACKEND=postgres` at all, vs. some other path to
  the same corruption) were not independently verified against the live node.
- Per project memory (`ccdash-node-runs-baked-image-not-mounted-source`), the
  node runs a baked container image — this fix requires a `podman-compose
  build` + redeploy on the node to take effect, not just a `git pull`/`git
  reset`.
- The hardened multi-row test in `test_client_v1_aar_review.py` does not, by
  itself, fail against the SQLite-only default test environment even without
  the cache fix (by design — the in-process cache backend is never exposed to
  this bug class). Its regression value is against a *different* class of
  defect (a genuine per-DTO/per-route serialization break, as proven by the
  temporary-mismatch experiment), not against the cache-boundary defect this
  sprint actually found and fixed. The cache-boundary defect's dedicated
  regression coverage lives in `test_query_cache.py`.

### Follow-Up Recommendations

- Redeploy/rebuild the node's containers once this lands on `main`, per the
  stale-baked-image project memory.
- Consider whether `CCDASH_QUERY_CACHE_BACKEND=postgres` is intentionally set
  on the node (multi-worker distributed cache) — if so, this fix is directly
  load-bearing for every `@memoized_query` endpoint the node serves, not just
  aar-review, and should be prioritized for the node redeploy.
- Consider adding a lightweight startup/CI assertion that
  `PostgresCacheBackend` round-trips a representative pydantic model without
  type corruption, so a future regression at this boundary is caught before
  reaching any specific route's test suite.

### Memory Candidates Captured

- **Gotcha**: `PostgresCacheBackend.aset()` (`backend/application/services/agent_queries/cache.py`)
  previously called `json.dumps(value, default=str)` directly on values that
  are pydantic `BaseModel` instances (the normal `@memoized_query` return
  shape) — `json.dumps` has no native `BaseModel` encoder, so `default=str`
  fires at the *top level* and silently stringifies the entire value into an
  opaque repr, corrupting every subsequent cache hit. Any future
  `PostgresCacheBackend`-adjacent change must preserve the `_json_safe()`
  pre-serialization step and the `_reconstruct_from_cache()` rehydration step
  in `memoized_query`'s `wrapper()` — removing either reintroduces this class
  of defect. Anchor: `backend/application/services/agent_queries/cache.py:PostgresCacheBackend.aset,_json_safe,_reconstruct_from_cache`.
- **Pattern**: when a reported 500 on a Postgres-backed deployment doesn't
  reproduce against SQLite even with a realistic multi-row payload, check
  whether the deployment sets `CCDASH_QUERY_CACHE_BACKEND=postgres` (opt-in,
  default `memory`) before assuming the defect is about `jsonb` decoding —
  the distributed query-result cache is a structurally different code path
  the SQLite/in-process test suite never exercises.
