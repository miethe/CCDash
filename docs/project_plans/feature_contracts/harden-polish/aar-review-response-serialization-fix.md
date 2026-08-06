---
title: "Feature Contract: Fix GET /api/v1/project/aar-review 500 (response-serialization boundary)"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "Fix a FastAPI ResponseValidationError that 500s GET /api/v1/project/aar-review on valid, fully-populated payloads, add a route-level regression test, and audit sibling ClientV1Envelope[...] routes for the same latent defect."
status: completed
created: 2026-08-06
updated: 2026-08-06
feature_slug: aar-review-response-serialization-fix
category: harden-polish
estimated_points: 5
tier: 1
owner: null
priority: high
risk_level: low
changelog_required: false
node_type: work_package
acceptance_criteria:
  - "GET /api/v1/project/aar-review returns 200 with a valid token and a well-formed body containing the reviews array"
  - "Response body preserves project_id, total, and per-review schema_version/status/correlation/flags fields seen in the reported error input"
  - "A route-level regression test (FastAPI TestClient, full request->response cycle) fails on a serialization-only regression; a handler-return-value-only test is explicitly insufficient"
  - "No other route on client_v1_router regresses; sibling routes sharing the same generic ClientV1Envelope[...] response pattern are checked and any latent defect found is fixed and reported"
execution_mode: autonomous
agent_title: "Fix aar-review response-serialization 500"
agent_summary: "Diagnose and fix the ResponseValidationError at the ClientV1Envelope[AARReviewListDTO] serialization boundary for GET /api/v1/project/aar-review; harden the regression test; audit sibling client_v1 routes."
agent_context: "Seed context: backend/routers/client_v1.py, backend/routers/_client_v1_aar_review.py, backend/routers/client_v1_models.py, backend/application/services/agent_queries/models.py, backend/tests/test_client_v1_aar_review.py, docs/guides/aar-review-loop.md. Note: the existing 8-test suite in test_client_v1_aar_review.py already passes locally against SQLite with small (1-2 flag) payloads -- the reported 500 was observed on the node (Postgres backend, 6 real AARReviewDTOs). Root cause is not yet confirmed against a realistic multi-row payload; do not assume the diagnosis in the linked traceback is complete without reproducing it."
open_questions:
  - "Is the defect reproducible against SQLite with a payload shaped like the real one (6 reviews, populated correlation + flags), or is it Postgres-specific (jsonb codec / driver-decoded types feeding _loads_dict/_loads_list differently than SQLite's TEXT columns)?"
  - "Is there a second/duplicate registration of a generic-envelope response type that FastAPI's return-type-annotation resolution (from __future__ import annotations + parametrized Generic pydantic models) is colliding with, causing `data` to validate against the wrong concrete type?"
decisions: []
scores: {}
related_documents:
  - docs/guides/aar-review-loop.md
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs:
  - ac8b108
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/cache.py
  - backend/tests/test_client_v1_aar_review.py
  - backend/tests/test_query_cache.py
---

# Feature Contract: Fix GET /api/v1/project/aar-review 500 (response-serialization boundary)

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 5,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 4,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [
    "Root cause is not yet confirmed against a realistic multi-row payload (existing 8-test suite already passes locally against SQLite with small payloads) -- but this is a bounded reproduce-then-fix investigation inside one sprint, not a standalone SPIKE."
  ],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/harden-polish/aar-review-response-serialization-fix.md",
  "execution_target": "execute-contract",
  "slug": "aar-review-response-serialization-fix",
  "category": "harden-polish",
  "review_intensity": "standard",
  "files_affected": [
    "backend/routers/client_v1.py",
    "backend/routers/_client_v1_aar_review.py",
    "backend/routers/client_v1_models.py",
    "backend/tests/test_client_v1_aar_review.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Reproduce, fix, harden regression test, audit siblings",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint.\n\nImplement the Feature Contract at docs/project_plans/feature_contracts/harden-polish/aar-review-response-serialization-fix.md in full -- read it directly, it is your specification.\n\nSummary: GET /api/v1/project/aar-review 500s on the node with a FastAPI ResponseValidationError at the ClientV1Envelope[AARReviewListDTO] serialization boundary, even though the handler computes a correct, fully-populated payload (6 AARReviewDTOs). Auth is confirmed not the problem. The existing route-level test suite at backend/tests/test_client_v1_aar_review.py (8 tests) already passes locally against SQLite with small (1-2 flag) payloads -- so you must REPRODUCE the defect first (try a realistic >=6-row, fully-populated payload; consider SQLite-vs-Postgres jsonb-decoding differences in backend/routers/_client_v1_aar_review.py's _loads_dict/_loads_list; consider the memoized_query cache-hit path) before applying any fix. Do not ship a speculative fix with no reproduction evidence -- if you cannot reproduce it after a good-faith attempt, say so explicitly in the Completion Report.\n\nKey files: backend/routers/client_v1.py (route registration, 21 sibling ClientV1Envelope[...]/ClientV1PaginatedEnvelope[...] routes), backend/routers/_client_v1_aar_review.py (handler), backend/routers/client_v1_models.py (AARReviewListDTO), backend/application/services/agent_queries/models.py (AARReviewDTO/AARReviewCorrelation/AARReviewFlag), backend/tests/test_client_v1_aar_review.py (existing coverage baseline).\n\nEnvironment: use /Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python (no local .venv in this worktree). Run ONLY named test files, e.g. backend/.venv/bin/python -m pytest backend/tests/test_client_v1_aar_review.py -v -- never a bare `pytest backend/tests/` (full-directory collection hangs at import).\n\nDeliver: (1) confirmed root cause, (2) minimal correct fix at the serialization boundary, (3) a hardened route-level regression test (TestClient, full request/response cycle, realistic multi-row payload) that would have caught this defect, (4) an audit of all 21 sibling client_v1_router routes sharing the same generic-envelope pattern, fixing any that share the defect, (5) a Completion Report per contract §13.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 5,
                "files_affected": [
                  "backend/routers/client_v1.py",
                  "backend/routers/_client_v1_aar_review.py",
                  "backend/routers/client_v1_models.py",
                  "backend/tests/test_client_v1_aar_review.py"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If the sibling audit (AC4) reveals the same defect on multiple routes with distinct root causes per route, or if reproduction proves Postgres-specific and requires a live Postgres fixture not available in this environment, stop and promote to Tier 2 (author a PRD covering the full generic-envelope hardening, since fixing N routes individually would exceed this contract's single-sprint scope)."
}
```

## 1. Goal

`GET /api/v1/project/aar-review` returns 200 with the full, correctly-shaped AAR-review rollup for any valid, fully-populated payload — the response-serialization boundary no longer raises `ResponseValidationError`.

---

## 2. User / Actor

- **Primary user**: `op story` (the Signal-to-System AAR pipeline), which PULLs this endpoint to intake AAR lessons. CCDash never pushes; while this endpoint 500s the intake leg is dead and lessons stay stranded.
- **Secondary users**: any LAN agent or operator hitting the endpoint directly (e.g. `ccdash-cli`, MCP consumers) to inspect AAR triage state.

---

## 3. Job To Be Done

When a project has persisted `aar_reviews` rows (any count, any shape of `correlation`/`flags`), the caller wants to `GET /api/v1/project/aar-review` and reliably receive a 200 with the full rollup, so that downstream consumers (`op story`) never treat a serialization defect as "no lessons to pull."

---

## 4. Scope

### In Scope

- Root-cause the `ResponseValidationError` at the `ClientV1Envelope[AARReviewListDTO]` boundary for `GET /api/v1/project/aar-review`, reproducing it first (do not fix blind).
- Apply the minimal correct fix at the serialization boundary (prefer option #1 from the request: type the envelope's `data` field as the concrete DTO type; `.model_dump()` in the handler or loosening the response model are fallback options if #1 does not resolve the actual root cause).
- Strengthen `backend/tests/test_client_v1_aar_review.py` (or add a new test in the same file) with a route-level (TestClient, full request/response cycle) regression case using a realistic multi-row payload (>=6 rows, populated `correlation` with a non-null `strategy`/`confidence`/`session_ids`/`feature_id`, and populated `flags[]`) that would have caught this exact class of defect.
- Audit every other route on `client_v1_router` that returns `ClientV1Envelope[...]` or `ClientV1PaginatedEnvelope[...]` (21 call sites in `backend/routers/client_v1.py` as of this contract) for the same latent defect — a route-level smoke request per untested sibling is sufficient; do not write a full new test suite per sibling.
- Report (in the Completion Report) which sibling routes were checked and which, if any, shared the defect and were fixed.

### Out of Scope

- Any change to `agent_router`'s `/aar-review/{document_id}` route (different router, different response_model, not implicated by this report).
- Any change to AAR-review business logic, correlation strategy, or flag computation (`backend/application/services/agent_queries/aar_review.py`, the sweep worker).
- Auth changes of any kind (confirmed not the problem — no token -> 401 already behaves correctly).
- Widening the audit beyond `client_v1_router` (e.g. `agent_router`, other routers) unless the root cause is proven to be a project-wide FastAPI/pydantic configuration issue rather than something scoped to this router's registration.

---

## 5. UX / Behavior Requirements

- A request to `GET /api/v1/project/aar-review` with a valid token and a project that has 0 persisted rows continues to return 200 with the existing normalized-empty contract (`reviews: []`, `total: 0`) — do not regress `test_a_empty_project_returns_200_with_normalized_empty_payload`.
- A request against a project with N>=1 persisted rows (including realistic N=6, multi-flag rows) returns 200 with `total == N` (post-dedup) and every `AARReviewDTO` field intact: `document_id`, `correlation.{strategy,confidence,session_ids,feature_id}`, `flags[].{flag_id,triggered,severity,evidence_refs,rationale}`, `triage_verdict`, `reasons`, `generated_at`, `source_refs`, plus the deprecated flat aliases.
- Envelope shape is unchanged: `{status, data: {project_id, total, reviews[]}, meta}`.

---

## 6. Data Requirements

- No schema change. No new tables, columns, or migrations. This is a pure serialization-boundary fix in `backend/routers/`.
- If the fix is "type `data` as the concrete DTO," confirm no other consumer (frontend `types.ts`, `ccdash-cli`) depended on a looser/`dict`-typed `data` shape in the OpenAPI schema — a tightened response_model should be a strict superset of the previous behavior, not a breaking narrowing.

---

## 7. API / Integration Requirements

**Modified endpoint:**
- `GET /api/v1/project/aar-review` — no path/param change; response-serialization fix only.

**Routes to audit (no functional change expected, verify only) — every `ClientV1Envelope[...]`/`ClientV1PaginatedEnvelope[...]` return-annotated route in `backend/routers/client_v1.py`**, e.g. `/instance/meta`, `/capabilities`, `/project/status`, `/routing/rollup`, dashboard/workflow/feature/session-intelligence/session-detail/session-transcript/session-family/AAR-report routes.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/routers/_client_v1_aar_review.py` — zero-derivation deserialization pattern; do not add business logic here.
- `backend/routers/client_v1_models.py` / `ccdash_contracts/envelopes.py` — the `ClientV1Envelope[T]` generic envelope pattern used by every v1 route; a fix here must not require every route to add an explicit `response_model=` unless that is the actual root cause and fix.

**Must not change** (protected areas):
- `AARReviewDTO` / `AARReviewCorrelation` / `AARReviewFlag` shapes in `backend/application/services/agent_queries/models.py` (frozen per the `ccdash-automated-aar-review-v1` PRD §7.2).
- Auth (`require_v1_auth`, `get_auth_context`) — not implicated, do not touch.
- `memoized_query` caching behavior, unless the investigation proves the cache is returning a non-DTO shape on a hit (in which case fix the cache/decorator boundary, not the DTO shapes).

**New dependencies:**
- No new dependencies expected.

---

## 9. Acceptance Criteria

- [ ] GET `/api/v1/project/aar-review` returns 200 with a valid token and a well-formed body containing the `reviews` array (matches request AC1).
- [ ] Response body preserves `project_id`, `total`, and per-review `schema_version`/`status`/`correlation`/`flags` fields as seen in the reported error input (matches request AC2 — note: `AARReviewDTO` itself has no top-level `schema_version`/`status` field; verify against the actual DTO shape and reconcile with the report's language in the Completion Report if these terms map to envelope-level `status` and PRD `schema_version: 2` rather than per-DTO fields).
- [ ] A route-level regression test (FastAPI TestClient exercising the full request->response cycle, not the handler's raw return value) exists and demonstrably fails if the serialization boundary regresses — verified by confirming the new/updated test would have caught the original defect (e.g. temporarily reintroduce the bug locally during development and confirm the test fails, then revert) (matches request AC3).
- [ ] Every sibling route on `client_v1_router` sharing the generic-envelope response pattern is checked; any found to share the defect is fixed; the Completion Report names exactly which routes were checked and which (if any) were fixed (matches request AC4).
- [ ] Full existing `test_client_v1_aar_review.py` suite (8 tests) still passes.
- [ ] No other `backend/tests/test_client_v1_*.py` test regresses.

---

## 10. Validation Requirements

- [ ] `backend/.venv/bin/python -m pytest backend/tests/test_client_v1_aar_review.py -v` passes (existing + new/hardened tests).
- [ ] `backend/.venv/bin/python -m pytest backend/tests/test_agent_router.py -v` passes (adjacent router, sanity check for no collateral regression).
- [ ] Named-file sweep of other `test_client_v1_*.py` files touched by the sibling audit, run individually (never a bare directory `pytest backend/tests/` — collection hangs in this repo).
- [ ] No lint/typecheck regressions in touched files (project has no dedicated backend typecheck gate beyond pytest; rely on tests).
- [ ] No unrelated changes introduced — scope stays inside `backend/routers/` + the one test file unless the sibling audit proves a fix is needed elsewhere.

---

## 11. Risk Areas

- **Reproduction gap**: the existing test suite already passes locally against SQLite with small payloads. The fix must not be applied "blind" against the reported traceback alone — reproduce first (try SQLite with a 6-row, fully-populated payload; if that still passes, the defect may be Postgres-specific or an artifact of a stale node deployment (`podman-compose build` not run — see project memory `ccdash-node-runs-baked-image-not-mounted-source`). If local reproduction genuinely fails after a good-faith attempt, document the gap explicitly in the Completion Report rather than shipping an unverified fix.
- **Generic-envelope blast radius**: `ClientV1Envelope[T]` backs 21+ routes. A fix that changes how the router declares/resolves `response_model` (rather than a narrow handler-side change) could regress other routes silently — hence the mandatory sibling audit (AC4) rather than a single-route patch-and-ship.
- **Stale node deployment confound**: per project memory, the node runs a baked container image and `git reset` + restart does not pick up new code without an explicit rebuild. If reproduction against current `main`/this branch fails, note that the node's currently-deployed code may simply predate an already-landed fix — do not assume the bug is unfixed in the codebase without checking.

---

## 12. Implementation Notes

**Suggested approach:**
1. Reproduce first: extend or add a test in `backend/tests/test_client_v1_aar_review.py` that seeds >=6 `aar_reviews` rows with populated `correlation` (non-null `strategy`/`confidence`/`session_ids`/`feature_id`) and a non-empty `flags[]` per row, then hits `GET /api/v1/project/aar-review` via TestClient. Confirm whether it passes or fails against the current worktree state.
2. If it fails: inspect the actual pydantic `ValidationError` structure (`error.errors()`) to pinpoint whether the issue is the envelope's `data` field, a nested `AARReviewDTO` field, or the `memoized_query` cache boundary returning a non-DTO shape on a cache hit (bypass_cache=True vs False matters here — test both).
3. If it passes locally: broaden the repro — check `PostgresAarReviewsRepository.get_by_project`'s row shape assumptions in `_loads_dict`/`_loads_list` (`backend/routers/_client_v1_aar_review.py`) against how the Postgres jsonb driver actually decodes columns (dict already vs JSON text), since SQLite always returns TEXT.
4. Apply the fix per request's preference order (#1 first: type `data` explicitly as the concrete DTO if that's genuinely the gap; otherwise `.model_dump()` at the handler boundary; loosening the response model is the least-preferred fallback).
5. Run the sibling audit: for each of the 21 `ClientV1Envelope[...]`/`ClientV1PaginatedEnvelope[...]` routes in `client_v1.py`, confirm an existing test already exercises it at the route level (many already have `test_client_v1_*.py` files); for any route with no existing route-level test, add a minimal smoke request.

**Similar existing code**:
- `backend/tests/test_client_v1_routing_rollup.py` — sibling route-level test pattern for the structurally similar `RoutingRollupResponseDTO` envelope; useful cross-check for whether the same defect exists there.

**Known gotchas**:
- Never run a bare `pytest backend/tests/` — full-directory collection hangs at import (`test_runtime_bootstrap.py`, `test_sse_wire_boundary.py`). Always target named test files.
- Use `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python` (no local `.venv` in this worktree).
- `from __future__ import annotations` is present in `client_v1.py`, `_client_v1_aar_review.py`, and `client_v1_models.py` — if the root cause involves generic/parametrized-type resolution, this is the first thing to check (string annotations + `typing.get_type_hints` + parametrized Pydantic `Generic` models is a known footgun combination).

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason.
- **Root cause**: What was actually reproduced and confirmed as the defect (not just the reported hypothesis) — including whether the reported diagnosis in the request matched reality.
- **Tests run**: What tests were added/updated and results, including confirmation the new regression test would have caught the original defect.
- **Sibling audit results**: Table of every `client_v1_router` route checked, whether it already had route-level coverage, and whether it shared the defect.
- **Validation results**: Table of all validation commands and their results (pass/fail/not applicable).
- **Deviations from contract**: Any material changes to the contract during implementation and why.
- **Risks / Limitations**: Any remaining risks (e.g. inability to fully reproduce against real Postgres) or known limitations.
- **Follow-up recommendations**: Suggested next steps (e.g. node redeploy/rebuild verification once merged).

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (3–8 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `docs/guides/aar-review-loop.md`
- `backend/tests/test_client_v1_aar_review.py` (existing coverage baseline)
- IntentTree node: `node_01KZC1WS1GEKTTVB733YA8JEXZ`

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the Completion Report.
- **Impossible constraints** (e.g. cannot reproduce locally at all): Flag in the Completion Report before attempting workarounds — do not ship a speculative fix with no reproduction evidence without saying so explicitly.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. Avoid cleanup, refactors, or feature expansion beyond this contract. The reviewer will check for scope drift.
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

