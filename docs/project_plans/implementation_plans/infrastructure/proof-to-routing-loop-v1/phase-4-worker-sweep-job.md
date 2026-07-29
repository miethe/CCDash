---
title: "Phase 4: Worker Sweep Job"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-29
updated: 2026-07-29
feature_slug: "proof-to-routing-loop"
feature_version: "v1"
phase: 4
phase_title: "Worker Sweep Job"
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria: ["Phase 3 complete — RoutingRollupQueryService exists"]
exit_criteria: ["Multi-project sweep test + flag-off no-op test green"]
related_documents:
  - docs/guides/aar-review-loop.md
  - docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-5-transport-surfaces.md
spike_ref: null
adr_refs: []
charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: null
owner: null
contributors: []
priority: medium
risk_level: low
category: "infrastructure"
tags: [implementation, planning, infrastructure, routing-feedback, worker, no-llm]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/adapters/jobs/routing_rollup_sweep_job.py
  - backend/adapters/jobs/runtime.py
  - backend/runtime/container.py
  - backend/tests/test_routing_rollup_sweep_job.py
---

# Phase 4: Worker Sweep Job

**Parent Plan**: [Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~0.5–1 day (near-exact mechanical clone; H5 clone-discount applies)
**Effort**: 2 story points
**Dependencies**: Phase 3 complete (`RoutingRollupQueryService` exists and its output shape is frozen)
**Team Members**: python-backend-engineer

---

## Phase Overview

This phase ships the worker-side persistence half of the routing-feedback loop: a background sweep
job that periodically populates the `routing_rollup` table by calling Phase 3's
`RoutingRollupQueryService` for every registered project. The job performs **zero computation of its
own** — aggregation, mapping application, coverage, and metric-payload design all happened in Phase
3. This phase is purely: enumerate projects → call the query service → upsert the result → invalidate
the read cache → repeat on the next tick, gated end-to-end by `CCDASH_ROUTING_FEEDBACK_ENABLED`.

**Wave placement**: This phase runs in the **same wave as Phase 5** (parallel execution). Phase 4
touches only `backend/adapters/jobs/*` + `backend/runtime/container.py` (the writer side); Phase 5
touches only `backend/routers/*` + `backend/mcp/*` + `backend/cli/*` (the reader side). The two phases
operate on disjoint files once Phase 3 freezes the `routing_rollup` table shape and the
`RoutingRollupQueryService` read contract — there is no file-ownership conflict and no need for
`isolation: worktree`.

### Goals

- Clone `AARReviewSweepJob`'s exact shape into a new `RoutingRollupSweepJob` — same multi-project
  fan-out, same incremental/idempotent/upsert discipline, same cache-invalidation hook.
- Wire the new job into the runtime's existing job-registration pattern with zero new orchestration
  concepts introduced.
- Prove reversibility (AC-7) at the worker layer: flipping the flag off mid-run produces zero new
  writes on the very next tick.

### Architecture Focus

This phase implements the **Worker/Background Job** layer, cloning the shipped Automated AAR Review
Loop:
- **Layer**: Worker (background job), sibling of `AARReviewSweepJob`.
- **Patterns**: multi-project fan-out via `ports.workspace_registry.list_projects()` (ADR-006 — the
  same registry-driven enumeration the watcher fan-out and cache-warming jobs use); incremental
  watermark scoping (only new/changed windows since the last tick); idempotent upsert (never
  re-derive — delegate all computation to Phase 3's `RoutingRollupQueryService`); cache-invalidate on
  write (mirror `aclear_project_cache`); default-off flag gate re-checked at both construction time
  (`container.py`) and execute() time (defense in depth).
- **Standards**: ADR-006 (DB-authoritative project registry — never `projects.json` directly);
  ADR-007 (every DB write path uses `repositories/base.py:retry_on_locked` — enforced inside Phase 2's
  `routing_rollup` repository, not re-implemented here).

---

## Task Breakdown

### Epic: Worker Sweep Job — `RoutingRollupSweepJob`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|---------------------|-------|--------|--------------|
| T4-001 | `RoutingRollupSweepJob` | New `backend/adapters/jobs/routing_rollup_sweep_job.py` cloning `aar_review_sweep_job.py`'s shape: multi-project (`workspace_registry.list_projects()`, ADR-006), incremental, idempotent upsert via Phase 2's repository, calls Phase 3's `RoutingRollupQueryService` for all computation (zero re-derivation in the job). No-op entirely (skip the sweep body) when `CCDASH_ROUTING_FEEDBACK_ENABLED` is `False`. | Identical output on repeat runs over unchanged data (idempotent); flag-off run performs zero writes | 1 pt | python-backend-engineer | sonnet | adaptive | Phase 3 complete |
| T4-002 | Wire job registration | Register `RoutingRollupSweepJob` in `backend/adapters/jobs/runtime.py` and `backend/runtime/container.py`, mirroring `AARReviewSweepJob`'s exact registration call shape. Interval config: follow the `CCDASH_AAR_REVIEW_SWEEP_INTERVAL_SECONDS` naming convention (implementer's choice of exact name — not a locked canonical name in this plan) or reuse an existing shared interval if appropriate. | Job appears in the runtime's registered job list; flag-gated at registration time, not just inside the job body | 0.5 pts | python-backend-engineer | sonnet | adaptive | T4-001 |
| T4-003 | Cache invalidation + reversibility tests | On any row written, invalidate the routing-rollup read cache for the project (mirror `aclear_project_cache`). New `backend/tests/test_routing_rollup_sweep_job.py`: multi-project sweep test (every registered project swept), flag-off no-op test (zero writes when disabled), flag-flip reversibility test (flip the flag mid-run; assert zero new writes on the next tick and read surfaces revert to disabled — AC-7). | All three tests green; no residual writes survive a flag flip | 0.5 pts | python-backend-engineer | sonnet | adaptive | T4-002 |

**Phase total**: 2 pts.

**Model Selection Guidance**: All three tasks are Claude Sonnet by default. Refer to
`.claude/config/multi-model.toml` for valid model values and effort policies.

**Effort Policy**: `adaptive` — default reasoning for a near-exact mechanical clone; no task in this
phase needs `extended` reasoning (that budget belongs to Phase 3, the one algorithmic phase in this
feature).

---

## Detailed Task Specifications

### Task T4-001: `RoutingRollupSweepJob`

**Estimate**: 1 point
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: Phase 3 complete (`RoutingRollupQueryService` exists and its output DTO shape is
frozen)
**started**: null
**completed**: null
**verified_by**: [T4-003]
**evidence**: []

**Description**:
Create `backend/adapters/jobs/routing_rollup_sweep_job.py` defining `RoutingRollupSweepJob`, a
near-exact structural clone of `backend/adapters/jobs/aar_review_sweep_job.py`'s `AARReviewSweepJob`.
Mirror every documented invariant from that module:

1. **Multi-project fan-out** — `_resolve_projects_to_sweep()` mirrors `AARReviewSweepJob`'s method of
   the same name: when constructed with an explicit `project`, sweep just that project (preserves
   single-project test ergonomics); otherwise enumerate every registered project via
   `self.ports.workspace_registry.list_projects()` (ADR-006 — the same DB-authoritative,
   registry-driven enumeration the watcher fan-out and cache-warming jobs already use). Container
   wiring (T4-002) always constructs this job with `project=None` — this is a cross-project rollup,
   not scoped to whichever single project the worker's sync engine is bound to.
2. **Incremental** — track a per-project watermark (in-process, `dict[str, str]`) of the newest
   observed window/session timestamp from the previous tick, mirroring `AARReviewSweepJob._watermarks`.
   Losing the watermark across a worker restart is safe (next tick re-scans a superset, never misses
   data) because idempotent upsert (below) is what actually prevents duplicate/incorrect state, not
   the watermark.
3. **Idempotent upsert, zero re-derivation** — for each project, call Phase 3's
   `RoutingRollupQueryService` (`backend/application/services/agent_queries/routing_rollup.py`) to
   compute the full `(project_id, source_skill_name, model)`-grain rollup for that project's current window.
   This job performs **no aggregation, no mapping application, no metric-payload arithmetic of its
   own** — it is a pure orchestration + persistence shim around the service Phase 3 already built and
   tested. Upsert every returned row via Phase 2's `routing_rollup` repository (ADR-007
   `retry_on_locked`-wrapped writes, unchanged — do not re-implement retry logic here).
4. **`(project_id, trigger)` coalescing guard** — mirror `AARReviewSweepJob.execute()`'s in-flight set
   exactly (same key shape, same check-then-add-is-atomic-in-asyncio reasoning) so a second concurrent
   dispatch for the same project/trigger coalesces rather than double-sweeping.
5. **Flag gate, checked twice** — `execute()` re-checks `config.CCDASH_ROUTING_FEEDBACK_ENABLED` at the
   top (defense in depth, mirrors `AARReviewSweepJob.execute()`'s own
   `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` check) and returns an `outcome="disabled"` result with
   **zero writes and zero calls into the query service** — the sweep body is skipped entirely, not
   just gated at the write step. Reference `backend/config.py`'s
   `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` docstring block for the exact commenting convention to
   mirror when the corresponding `CCDASH_ROUTING_FEEDBACK_ENABLED` flag is declared/consumed (the flag
   itself is Phase 1 scope — this task only *reads* it).
6. **Result dataclass** — define a `RoutingRollupSweepRunResult` dataclass (mirrors
   `AARReviewSweepRunResult`'s shape: `success`, `outcome`, per-project counters, `error`, `details`)
   and an aggregation helper (mirrors `_aggregate_sweep_results`) that folds N per-project results into
   one tick-level result using the same outcome-precedence rules (`"disabled"` / `"no_project"` /
   `"coalesced"` / `"success"` / `"error"` / `"partial_error"`).

**Acceptance Criteria**:
- [ ] Two sweeps over an unchanged window produce field-identical `routing_rollup` rows (idempotent —
  no drift on repeat runs).
- [ ] A flag-off (`CCDASH_ROUTING_FEEDBACK_ENABLED=False`) run performs zero writes and makes zero
  calls into `RoutingRollupQueryService` (the sweep body is skipped, not silently no-op-written).
- [ ] Multi-project construction (`project=None`) enumerates and sweeps every project returned by
  `workspace_registry.list_projects()` in a single tick.
- [ ] Zero LLM/model-client imports anywhere in this module's transitive import graph (Hard Invariant
  #1, unchanged from the AAR-review precedent — every computed value came from Phase 3's service).

**Implementation Notes**:
- **ICA-offload eligible (`claude-sonnet-5[1m]`)**: this task is a near-exact mechanical clone of a
  shipped module (H5 clone-discount) — a strong cost-shift candidate per the delegation-router. If ICA
  is unavailable, fall back to the primary sonnet model per the standard `fallback_chain`.
  **Regardless of which provider executes this task, Phase 6's guard/test battery (no-LLM import
  guard, determinism test, parity test) must be re-run on return** — offload changes the execution
  provider, never the acceptance bar.
- Do not import from `backend.scripts.*` — if any discovery/lookup logic needs duplicating from a
  script module, duplicate it locally (mirrors `aar_review_sweep_job.py`'s own
  `looks_like_aar_document` duplication-not-import convention and its documented rationale).
- Use local (call-time, not module-top-level) imports for anything importing
  `backend.application.services.agent_queries` or `backend.application.services.common` — these
  transitively import `backend.runtime_ports`, which imports `backend.adapters.jobs`, creating an
  import cycle through this module's own eager top-level import if not deferred. Mirror
  `aar_review_sweep_job.py::_execute_inner`'s exact local-import pattern and its docstring rationale.
- Resolve the per-project `workspace_id` the same defensive way as
  `resolve_session_workspace_id()` if this job's Phase 3 call needs one — do not hardcode a bare
  string literal at any call site.

**Files Involved**:
- `backend/adapters/jobs/routing_rollup_sweep_job.py` - new file; `RoutingRollupSweepJob`,
  `RoutingRollupSweepRunResult`, aggregation helper — structural clone of `aar_review_sweep_job.py`.

---

### Task T4-002: Wire job registration

**Estimate**: 0.5 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T4-001
**started**: null
**completed**: null
**verified_by**: [T4-003]
**evidence**: []

**Description**:
Register `RoutingRollupSweepJob` into the runtime's existing background-job wiring, mirroring
`AARReviewSweepJob`'s registration call shape exactly across both files it touches:

1. **`backend/runtime/container.py`** — construct `RoutingRollupSweepJob` only when
   `CCDASH_ROUTING_FEEDBACK_ENABLED` is true AND the profile is in the same profile set
   `AARReviewSweepJob` uses (`_export_profiles`) — mirror the existing `aar_review_sweep_job=(...)`
   conditional construction block verbatim in structure (construct with `project=None` unconditionally,
   for the same multi-project reasoning documented on the AAR-review precedent). Thread the resulting
   task handle through the lifecycle object the same way
   `self.lifecycle.aar_review_sweep_task` is threaded onto `app.state`.
2. **`backend/adapters/jobs/runtime.py`** — add a `routing_rollup_sweep_job` constructor parameter to
   the runtime state/adapter (mirrors `aar_review_sweep_job` at line ~140), a
   `_start_routing_rollup_sweep_task()` method (mirrors `_start_aar_review_sweep_task()`, including its
   `profile.name != "worker"` guard and the 60-second interval floor), a periodic loop coroutine
   (mirrors `_run_periodic_aar_review_sweeps()`, including `_mark_job_started` /
   `_mark_job_success` / `_mark_job_failure` / `_mark_job_cancelled` bookkeeping calls under a new
   observation key), and wiring into the adapter's `start()`/`shutdown()`/status-reporting methods
   everywhere `aar_review_sweep_task` currently appears (the job-observations dict key, the
   status-summary dict, the task-map used by shutdown cancellation, and the health/status snapshot
   surfaces) — grep `aar_review_sweep` across `runtime.py` and add a sibling entry at every call site
   found, not just the constructor and the loop.
3. **Interval config** — the implementer chooses the exact env var name (not a locked canonical name
   in this plan); follow the `CCDASH_AAR_REVIEW_SWEEP_INTERVAL_SECONDS` naming convention (a sibling
   `CCDASH_ROUTING_FEEDBACK_SWEEP_INTERVAL_SECONDS` is the obvious choice) or reuse an existing shared
   interval knob if one is already appropriate for this cadence. This flag is declared in
   `backend/config.py` — if Phase 1 has not already declared it, declare it here with the same
   `_env_int(..., 1800)` shape and 60-second floor clamp as the AAR-review precedent.

**Acceptance Criteria**:
- [ ] `RoutingRollupSweepJob` appears in the runtime's registered job list (observable via the same
  status/health snapshot surface `aarReviewSweep` appears on today).
- [ ] The job is flag-gated at **registration time** (never constructed at all when
  `CCDASH_ROUTING_FEEDBACK_ENABLED` is false) — not merely gated inside the job body after
  construction.
- [ ] `local`/`test` runtime profiles never construct or schedule this job regardless of the flag
  value (mirrors the AAR-review precedent's profile gate).

**Implementation Notes**:
- **ICA-offload eligible (`claude-sonnet-5[1m]`)**: this task is a mechanical registration clone with a
  well-precedented call shape — a strong cost-shift candidate per the delegation-router. If ICA is
  unavailable, fall back to the primary sonnet model per the standard `fallback_chain`.
  **Regardless of which provider executes this task, Phase 6's guard/test battery must be re-run on
  return** — offload changes the execution provider, never the acceptance bar.
- Any `dev:backend` execution used to manually verify this wiring locally must use `--runtime local`
  per the project convention (note this explicitly does NOT start the worker profile that actually runs
  this job — use `dev:worker` or the worker profile directly to exercise the sweep loop end-to-end).
- Double-gate deliberately, matching the AAR-review precedent's own documented reasoning: constructing
  the job only under the flag in `container.py` AND re-checking the flag inside `execute()` (T4-001)
  means an accidental single-point config regression can never silently no-op a flag flip in either
  direction.

**Files Involved**:
- `backend/adapters/jobs/runtime.py` - add constructor param, `_start_routing_rollup_sweep_task()`,
  periodic loop, and every sibling call site the `aar_review_sweep` grep surfaces.
- `backend/runtime/container.py` - conditional construction block mirroring `aar_review_sweep_job=(...)`.

---

### Task T4-003: Cache invalidation + reversibility tests

**Estimate**: 0.5 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T4-002
**started**: null
**completed**: null
**verified_by**: [T6-006]
**evidence**: []

**Description**:
Close the loop on both write-path hygiene and reversibility (AC-7):

1. **Cache invalidation** — inside `RoutingRollupSweepJob`'s per-project sweep, on any row actually
   written for that project, invalidate the routing-rollup read cache the same way
   `aar_review_sweep_job.py::_execute_inner` invalidates `aar_review_list`'s cache via
   `aclear_project_cache(project_id)` (a local, call-time import to avoid the same import-cycle this
   module's own docstring documents). Only fire the invalidation when `pairs_written` (or this
   feature's equivalent row-count field) is greater than zero for that project — a no-op tick must
   never invalidate a cache that has nothing stale to clear.
2. **New test module** `backend/tests/test_routing_rollup_sweep_job.py` (run as a named module —
   `backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_sweep_job.py -v` — never a
   full-suite collection; see the project's pytest-collection-hang guidance), covering:
   - **Multi-project sweep test**: construct the job with `project=None` against a
     `workspace_registry.list_projects()` fixture backing two-or-more projects; assert every
     registered project is swept in one tick (mirror
     `MultiProjectAARReviewSweepTests.test_sweeps_multiple_registered_projects_in_one_tick`'s fixture
     shape from `backend/tests/test_aar_review_worker_guards.py`).
   - **Flag-off no-op test**: with `CCDASH_ROUTING_FEEDBACK_ENABLED=False`, assert `execute()` returns
     `outcome="disabled"` and the `routing_rollup` table's row count is unchanged (zero writes) —
     mirror `AARReviewSweepJobTests.test_disabled_by_default_flag_is_a_no_op`.
   - **Flag-flip reversibility test (AC-7)**: run one sweep with the flag enabled (rows written);
     flip `CCDASH_ROUTING_FEEDBACK_ENABLED` to `False`; run a second sweep tick and assert **zero new
     writes** occur and the row count is unchanged from the first tick; assert whatever read-side
     disabled-envelope helper Phase 3/5 exposes reports "disabled" for that project immediately after
     the flip (no partial state, no stale enabled rows served) — this is the phase's direct evidence
     for PRD AC-7's `propagation_contract` ("Flipping `CCDASH_ROUTING_FEEDBACK_ENABLED` to `false` ...
     stops all new `routing_rollup` writes ... no partial state, no stale enabled rows served").

**Acceptance Criteria**:
- [ ] All three tests (multi-project sweep, flag-off no-op, flag-flip reversibility) pass.
- [ ] No residual writes survive a flag flip — the reversibility test asserts the row count is
  byte-for-byte unchanged across the flip boundary.
- [ ] Cache invalidation fires exactly once per project that wrote at least one row, and never fires
  for a project whose tick wrote nothing (mirror
  `AARReviewSweepJobTests.test_cache_invalidation_hook_fires_only_on_write`'s assertion shape).

**Implementation Notes**:
- Not marked ICA-offload eligible — this task is the phase's actual acceptance-bar evidence (AC-7) and
  stays on the primary model, even though the surrounding job (T4-001) is offload-eligible.
- This task's flag-flip reversibility test is Phase 4's own partial closure of AC-7; Phase 6's
  T6-006 performs the feature-level, cross-transport final reversibility validation — do not treat
  this task's green test as the final AC-7 sign-off, only as this phase's contribution to it.
- Fixture DB setup mirrors `test_aar_review_worker_guards.py`'s `asyncSetUp`/`asyncTearDown` pattern:
  in-memory `aiosqlite` connection, `PRAGMA busy_timeout = 30000`, run migrations, patch the flag via
  `unittest.mock.patch.object(config, ...)` rather than mutating the module attribute directly.

**Files Involved**:
- `backend/adapters/jobs/routing_rollup_sweep_job.py` - cache-invalidation call site (row-count-gated).
- `backend/tests/test_routing_rollup_sweep_job.py` - new file; three required tests plus any
  supporting pure-function/fixture coverage the implementer judges useful.

---

## Quality Gates

This phase is complete when:

- [ ] **Functional**: `RoutingRollupSweepJob` sweeps every registered project on each tick, calling
  Phase 3's `RoutingRollupQueryService` for all computation and upserting via Phase 2's repository.
- [ ] **Testing**: All three required tests in `test_routing_rollup_sweep_job.py` are green
  (multi-project sweep, flag-off no-op, flag-flip reversibility).
- [ ] **Performance**: N/A — no new performance-sensitive read path in this phase (sweep runs on a
  background interval, not on any request path).
- [ ] **Security**: N/A — no new auth surface; the job operates entirely server-side using existing
  `ports` plumbing.
- [ ] **Documentation**: Module docstring on `routing_rollup_sweep_job.py` documents the clone
  relationship and hard invariants, mirroring `aar_review_sweep_job.py`'s own docstring conventions.
- [ ] **Code Quality**: Linting/type-checks pass; no `backend.scripts.*` imports from this module.
- [ ] **Architecture**: Follows the multi-project/ADR-006/ADR-007 patterns cloned from
  `AARReviewSweepJob` exactly — no new orchestration concept introduced.
- [ ] **Seam verification**: N/A — `integration_owner` is `null` for this phase; Phase 6 owns the
  cross-phase seam verification (the Phase 4 writer ↔ Phase 5 reader ↔ Phase 3 service contract) via
  its guard/parity/determinism/disabled-state test battery.
- [ ] **Runtime smoke**: N/A — `ui_touched: false`; this phase has no frontend surface and introduces
  no `*.tsx` files.

---

## Integration Points

### External Systems

- None. This phase has no external-system dependency — it is a pure background worker operating
  entirely against CCDash's own database.

### Internal Systems

- **Phase 3 (`RoutingRollupQueryService`)**: T4-001 is a pure consumer of Phase 3's output DTO shape.
  This job performs zero re-derivation — any aggregation/mapping/metric-payload change belongs in
  Phase 3, never patched around in this phase's job body.
- **Phase 2 (`routing_rollup` repository)**: T4-001 upserts exclusively through Phase 2's repository
  (ADR-007 `retry_on_locked` discipline lives there, not duplicated here).
- **Phase 5 (Transport Surfaces)**: disjoint files, same wave. Phase 5's REST/MCP/CLI read surfaces
  read the same `routing_rollup` rows this phase's job writes; no direct code dependency between the
  two phases, only a shared table-shape contract frozen by Phase 3.
- **Existing worker runtime (`backend/adapters/jobs/runtime.py`, `backend/runtime/container.py`)**:
  T4-002 is a pure sibling-registration addition alongside `AARReviewSweepJob`, `ArtifactRollupExportJob`,
  and `TelemetryExporterJob` — no existing job's wiring is modified, only extended.
- **Cache layer (`aclear_project_cache`)**: T4-003 invalidates the routing-rollup project cache on
  write, mirroring the AAR-review P4/karen cache-invalidation carry-forward.

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/adapters/jobs/routing_rollup_sweep_job.py` | new (~250-350) | `RoutingRollupSweepJob` — multi-project, incremental, idempotent worker sweep | python-backend-engineer |
| `backend/adapters/jobs/runtime.py` | +~90 (new method + loop + wiring) | Job registration, periodic loop, status/observation wiring | python-backend-engineer |
| `backend/runtime/container.py` | +~15 (conditional construction block) | Flag-gated, profile-gated job construction | python-backend-engineer |
| `backend/tests/test_routing_rollup_sweep_job.py` | new (~300-400) | Multi-project sweep, flag-off no-op, flag-flip reversibility tests | python-backend-engineer |

---

## Testing Strategy

### Unit Tests

- Pure-function coverage for any helper this phase introduces (e.g. an incremental-window-selection
  helper, if one is added rather than reused from Phase 3's service).
- `RoutingRollupSweepRunResult` aggregation-helper coverage: outcome precedence across
  disabled/no-project/coalesced/success/error/partial_error, mirroring
  `_aggregate_sweep_results`'s documented precedence rules.

### Integration Tests

- **Multi-project sweep**: two-or-more registered projects, one tick, assert every project is swept
  and its rows persisted.
- **Flag-off no-op**: `CCDASH_ROUTING_FEEDBACK_ENABLED=False` produces zero writes and zero calls into
  `RoutingRollupQueryService`.
- **Flag-flip reversibility (AC-7)**: enabled tick writes rows → flag flipped off → next tick writes
  nothing and row count is unchanged.
- **Cache invalidation**: fires exactly once per project with at least one write; never fires for a
  no-write tick.
- **Idempotency**: two sweeps over an unchanged window produce field-identical rows (no drift, no
  duplicate rows, no re-derivation artifacts).

### E2E Tests (if applicable)

- Not applicable — this phase has no HTTP/CLI/MCP surface (Phase 5 owns those); end-to-end coverage of
  the full worker→transport path is Phase 6's responsibility.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Job body silently re-derives instead of delegating to Phase 3's service (drift risk between the two "sources of truth") | Medium | AC explicitly requires zero computation in the job; code review checks for any aggregation/mapping logic inside `routing_rollup_sweep_job.py` and rejects it — the job must be a thin orchestration+persistence shim only. |
| Import cycle through `backend.adapters.jobs` (the same cycle `aar_review_sweep_job.py` already documents and works around) | Low | Reuse the exact local-import-at-call-time pattern from `AARReviewSweepJob._execute_inner`; this is a known, already-solved problem — copy the solution, don't re-derive it. |
| Double-gate drift: `container.py` and `execute()` disagree on the flag's current value at process-restart boundaries | Low | Both gates read the same `config.CCDASH_ROUTING_FEEDBACK_ENABLED` module attribute at their respective check times; no caching of the flag value across the two checks. |
| ICA-offloaded execution (T4-001/T4-002) subtly diverges from the AAR-review clone anchor in ways that pass locally but fail Phase 6's guards | Medium | Phase 6's guard/test battery is re-run on return regardless of execution provider — this is a hard requirement in this phase's task notes, not a suggestion. |

---

## Success Metrics

- **Completion**: All three tasks (T4-001, T4-002, T4-003) checked off.
- **Quality**: All quality gates passed; no seam or runtime-smoke gate applies to this phase.
- **Determinism**: Two sweeps over an unchanged window produce field-identical `routing_rollup` rows
  (feeds the parent plan's feature-level "Determinism: 100%" success metric).
- **Reversibility**: Flag-off run performs zero writes; flag-flip mid-run produces zero new writes on
  the next tick (this phase's contribution to PRD AC-7, finalized in Phase 6).
- **Testing**: `test_routing_rollup_sweep_job.py`'s three required tests green.

---

## Notes

### Implementation Approach

This phase is a near-exact mechanical clone (H5 clone-discount) of the shipped
`AARReviewSweepJob` (`backend/adapters/jobs/aar_review_sweep_job.py`) and its runtime wiring
(`backend/adapters/jobs/runtime.py`, `backend/runtime/container.py`). The implementer's primary job is
fidelity to the anchor, not novel design — every structural decision (multi-project fan-out,
incremental watermarking, idempotent upsert, coalescing guard, cache invalidation, double-gated flag
check) already has a working, tested precedent in this codebase. Where this phase's job differs from
the anchor is narrow and explicit: it calls Phase 3's `RoutingRollupQueryService` instead of Phase
3-equivalent `AARReviewQueryService.get_review`, and it upserts via Phase 2's `routing_rollup`
repository instead of the `aar_reviews` repository. Everything else is the same shape.

Both T4-001 and T4-002 are explicitly marked **ICA-offload eligible (`claude-sonnet-5[1m]`)** in their
Implementation Notes above — this is exactly the kind of mechanical-clone wave the delegation-router
treats as a cost-shift candidate. If ICA is unavailable, fall back to the primary sonnet model per the
standard `fallback_chain`. **Regardless of which provider executes T4-001/T4-002, Phase 6's
guard/test battery must be re-run on return** — offload changes the execution provider, never the
acceptance bar. T4-003 is not offload-marked; it is this phase's direct acceptance-bar evidence and
stays on the primary model.

Any `dev:backend` execution referenced anywhere in this phase file must use `--runtime local` (the
project's standing convention) — note that the worker sweep loop itself only runs under the `worker`
profile, not `local`; use `dev:worker` (or the worker runtime profile directly) to exercise the
periodic tick end-to-end.

### Gotchas

- **Import cycle**: importing `backend.application.services.agent_queries` or
  `backend.application.services.common` at this module's top level will create an import cycle
  through `backend.runtime_ports` → `backend.adapters.jobs`. Defer these imports to call time inside
  the per-project sweep method, exactly as `aar_review_sweep_job.py::_execute_inner` already does and
  documents.
- **Flag-gate double-check**: do not remove the `execute()`-time flag re-check just because
  `container.py` already gates construction — the AAR-review precedent's defense-in-depth reasoning
  applies unchanged here (a config flip mid-run must be honored without a worker restart).
- **Watermark is an optimization, not a correctness guarantee**: the in-process watermark dict is lost
  on worker restart by design; idempotent upsert (via Phase 2's repository) is what actually prevents
  duplicate/incorrect writes across that boundary, not the watermark. Do not add any correctness logic
  that depends on the watermark surviving a restart.
- **pytest collection hangs**: run `test_routing_rollup_sweep_job.py` as a named module, never as part
  of a full `backend/tests/` collection sweep (per this repo's documented pytest-collection-hang
  behavior on unrelated test files).

### Learnings

_Capture learnings as phase progresses._

### Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
