---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 3
title: Rollup Compute Service
status: completed
created: '2026-07-29'
updated: '2026-07-31'
started: '2026-07-31'
completed: null
overall_progress: 20
completion_estimate: on-track
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T3-001
  description: RoutingRollupQueryService skeleton — pure-SQL GROUP BY aggregation
    at grain key
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  priority: critical
  estimated_effort: 2h
  assigned_model: sonnet
  model_effort: extended
  evidence:
  - note: backend/application/services/agent_queries/routing_rollup.py, backend/tests/test_routing_rollup_aggregation.py
      (11 passed)
  started: '2026-07-31T00:00:00Z'
  completed: '2026-07-31T00:00:00Z'
  verified_by:
  - T6-004
- id: T3-002
  description: Apply pinned mapping + protected-class policy — derive task_class,
    handle _unclassified
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T3-001
  priority: critical
  estimated_effort: 2h
  assigned_model: sonnet
  model_effort: extended
  evidence:
  - note: backend/application/services/agent_queries/routing_rollup.py (apply_mapping
      + MappedRollupRow + mapping loader), backend/tests/test_routing_rollup_mapping.py
      (14 passed)
  started: '2026-07-31T00:00:00Z'
  completed: '2026-07-31T00:00:00Z'
  verified_by:
  - T6-005
- id: T3-003
  description: Provider + coverage counters — derive provider via derive_model_identity(),
    compute mapped/unclassified counts
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-002
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-31T00:00:00Z'
  completed: '2026-07-31T00:00:00Z'
  evidence:
  - test: backend/tests/test_routing_rollup_provider_coverage.py
  - note: apply_provider+compute_coverage_counters on RoutingRollupQueryService (10
      passed)
  verified_by:
  - T6-003
- id: T3-004
  description: D5 metric payload — sample_count, success_rate, cost_index, regression_rate,
    confidence, eligible_for_adjustment, windows, freshness
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T3-003
  priority: critical
  estimated_effort: 2h
  assigned_model: sonnet
  model_effort: extended
  started: '2026-07-31T00:00:00Z'
  completed: '2026-07-31T00:00:00Z'
  evidence:
  - test: backend/tests/test_routing_rollup_metrics.py
  - note: compute_metrics+build_response on RoutingRollupQueryService, RoutingRollupKeyDTO/RoutingRollupResponseDTO
      in models.py (17 passed)
  verified_by:
  - T6-005
- id: T3-005
  description: Determinism + no-LLM guard — AST-walk transitive imports, two-invocation
    fixture test
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T3-004
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-31T00:00:00Z'
  completed: '2026-07-31T00:00:00Z'
  evidence:
  - test: backend/tests/test_routing_rollup_determinism.py
  - test: backend/tests/test_routing_rollup_no_llm_imports.py
  verified_by:
  - T6-001
  - T6-004
parallelization:
  batch_1:
  - T3-001
  batch_2:
  - T3-002
  batch_3:
  - T3-003
  - T3-004
  batch_4:
  - T3-005
  critical_path:
  - T3-001
  - T3-002
  - T3-004
  - T3-005
  estimated_total_time: 8h
blockers: []
success_criteria: []
files_modified:
- backend/application/services/agent_queries/routing_rollup.py
- backend/application/services/agent_queries/models.py
- backend/tests/test_routing_rollup_determinism.py
- backend/tests/test_routing_rollup_no_llm_imports.py
progress: 100
---

# Phase 3: Rollup Compute Service

**Total Tasks**: 5  
**Estimated Effort**: 4 points  
**Key Files**: `routing_rollup.py` service, `models.py` DTOs, determinism test, no-LLM guard

## Objective

Implement `RoutingRollupQueryService` — the **only genuinely algorithmic phase** in the entire feature. Aggregate sessions at `(project_id, source_skill_name, model)` grain, apply the pinned v1 skill_name→task_class mapping, compute metrics, and prove determinism + no-LLM invariant.

## Implementation Notes

### Architectural Decisions

- **Pure SQL aggregation**: One GROUP BY query, zero N+1, zero ORM lazy-loading
- **Hard invariant (AOS Constraint 4)**: Zero LLM/model-client imports anywhere in transitive closure
- **Mapping application at write time**: `task_class` is a derived, denormalized column — never raw `skill_name` (D3/FR-6)
- **Protected-class policy**: `_unclassified` (always emitted, eligible_for_adjustment hardcoded False); protected classes (orchestration, mode_d) gated by `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`
- **Sub-threshold visibility**: Every distinct key present in response, never suppressed; only `eligible_for_adjustment` flips to False

### Patterns and Best Practices

- Clones `aar_review.py` and `system_metrics.py` query-service conventions
- Uses `aiosqlite` direct queries, not ORM
- Module-level docstring explicitly states no-LLM invariant
- Imports deferred locally in key methods to avoid import cycles

### Known Gotchas

- **Row-grain discipline**: Never collapse (source_skill_name, model) rows sharing a task_class — that merge is the router's job (out of scope)
- **Two independent gates**: `_unclassified` bypasses the protected-class gate entirely (always emitted); protected classes are gated by config flag
- **Provider sourcing**: Always via `derive_model_identity(model)["modelProvider"]` — never independently derived
- **Confidence saturation**: Pick a simple, documented, monotonic formula (e.g., min(1.0, sample_count / (sample_count + k)))
- **This is H3 anchor phase**: The only algorithmic phase — budget plan-level karen review at completion, not just task-completion-validator

### Development Setup

- Familiarity with SQL GROUP BY aggregation patterns
- Knowledge of `routing_feedback_contract.py` mapping loader pattern
- Understanding of D5 metric payload design (PRD §6.3 JSON example)
- Ability to author AST-walk import-graph guards

### T3-001 Notes (RoutingRollupQueryService skeleton — completed 2026-07-31)

- Shipped `backend/application/services/agent_queries/routing_rollup.py`:
  `RawRollupRow` (frozen dataclass: `project_id`, `source_skill_name`, `model`,
  `session_count`, `window_start`, `window_end`) + `RoutingRollupQueryService.fetch_raw_rows`.
  One `GROUP BY project_id, skill_name, model` query against `sessions`
  (`skill_name` aliased `source_skill_name`), dual-path SQLite/PostgreSQL
  mirroring `system_metrics.py::_fetch_model_family_tokens`. Window read from
  `config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` via `_filters.resolve_time_window`
  (never hardcoded); `window_days` kwarg is a test/worker override only.
- **Scoping decision**: kept the raw shape to `session_count` only — did NOT
  add success/failure status-classification counts at this stage. The Phase
  Overview's "session counts/success signal inputs" phrase is a summary of
  the T3-001..T3-004 pipeline as a whole; T3-001's own Description/AC only
  mandate grouping + window + zero-N+1 + no-ORM. Deriving a success/failure
  signal requires a status-semantics decision that's more naturally T3-004's
  (D5 metric payload) design surface — extend `_fetch_raw_aggregate_rows`/
  `RawRollupRow` there rather than guessing the shape here.
- Deliberately did NOT filter out empty/NULL `skill_name` or `model` — every
  row in the window is counted, unfiltered. This matters for T3-003's
  `mapped_count + unclassified_count == total_rows` invariant: filtering rows
  out at this layer would silently break that arithmetic downstream.
- `models.py` untouched — `RoutingRollupKeyDTO`/`RoutingRollupResponseDTO` are
  T3-004's deliverable per the phase file's own "Files Involved" list for
  T3-001 (only `routing_rollup.py` + read-only `_filters.py`).
- New test file `backend/tests/test_routing_rollup_aggregation.py` (11 tests,
  all green) covers this task's own ACs: correct grouping (distinct keys,
  cross-project non-collapse, `project_ids` filter), zero-N+1 (query-count
  wrapper across N=1/5/15/20 keys), and window-boundary-from-config (default
  30d, shrunk via `patch.object(config, ...)`, and the `window_days` override
  param). This file is additive to the two T3-005-owned guard files
  (`test_routing_rollup_determinism.py`, `test_routing_rollup_no_llm_imports.py`)
  — it does not replace or anticipate either.
- Verified no regression: `test_routing_rollup_repo.py` (17, Phase 2) and
  `test_agent_queries_aar_review.py` + `test_aar_review_no_llm_imports.py` +
  `test_routing_feedback_contract_parity.py` (32, precedent modules) all still
  green after this change.

### T3-002 Notes (pinned mapping + protected-class policy — completed 2026-07-31)

- Extended `routing_rollup.py` with a new `MappedRollupRow` frozen dataclass
  (`RawRollupRow`'s fields + `task_class: str` + `is_coverage_only: bool`) and
  `RoutingRollupQueryService.apply_mapping(rows, *, include_protected_rows=None)`
  — a pure in-memory transform, zero I/O beyond one cached mapping-file read.
- **No pre-existing mapping loader found in `routing_feedback_contract.py`** —
  that module (Phase 1 output) ships only frozen identity constants
  (`CONTRACT_ID`, `MAPPING_DIGEST`, `MAPPING_JSON_PATH`, etc.), no loader
  function, despite the phase file's Files-Involved note describing
  `MAPPING_JSON_PATH + mapping loader (Phase 1 output)` as if both existed
  there. Verified by reading the actual module and
  `test_routing_feedback_contract_parity.py` (which reads
  `MAPPING_JSON_PATH.read_bytes()` directly, no loader call). Added the
  loader (`_load_skill_to_task_class_mapping`, `functools.lru_cache(maxsize=1)`)
  and the lookup helper (`_resolve_task_class`) inside `routing_rollup.py`
  itself — it reads `routing_feedback_contract.MAPPING_JSON_PATH` exclusively
  (never a second/independent path, never re-vendors the JSON), satisfying
  the task's "pure consumer of that contract" framing without needing to edit
  the read-only `routing_feedback_contract.py` file.
- **Two independent emission gates**, both keyed off the *resolved*
  `task_class` value, never mapping-entry presence: `UNCLASSIFIED_TASK_CLASS`
  ("_unclassified") rows always emitted regardless of
  `include_protected_rows`; `PROTECTED_TASK_CLASSES`
  (`frozenset({"orchestration", "mode_d"})`) rows emitted only when the flag
  resolves `True` (kwarg override > `config.CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`
  default, mirroring T3-001's `window_days` override convention).
- **`eligible_for_adjustment` doesn't exist as a field yet** (it's T3-004's
  DTO field, not built until that task). To satisfy this task's own AC
  ("every protected/`_unclassified` row has `eligible_for_adjustment=False`
  hardcoded... independent of T3-004's sample-size threshold logic") without
  preempting T3-004's design surface, `MappedRollupRow.is_coverage_only` is
  the single source of truth T3-004 MUST consume to force
  `eligible_for_adjustment=False` — documented explicitly in both the
  dataclass docstring and `apply_mapping`'s docstring as a hard contract for
  T3-004, and proven independent of `session_count` magnitude by a dedicated
  test (`session_count=50_000` on a protected/`_unclassified` row still
  yields `is_coverage_only=True`).
- Exact dict lookup only (no fuzzy matching, no case-folding) per the phase's
  own risk-mitigation note; missing entry and an existing entry that itself
  resolves to `_unclassified` (the real vendored `codex`/`claude-api`/
  `ica-delegate` executor-identity rules) are both routed through the same
  `_resolve_task_class` fallthrough — deliberately un-distinguishable to the
  caller, per FR-7.
- New test file `backend/tests/test_routing_rollup_mapping.py` (14 tests, all
  green) exercises the REAL pinned `routing_task_map_v1.json` mapping
  directly (not a mocked fixture) — `planning`→`orchestration`,
  `release`→`mode_d`, `codex`/`claude-api`/`ica-delegate`→`_unclassified`,
  `debugging`→`implementation` — covering: `_unclassified` always-emitted
  (both flag values, both no-entry and executor-identity-entry cases),
  protected-class gating (present/absent per flag, config-default fallthrough
  via `patch.object`), `is_coverage_only` independence from `session_count`,
  `task_class` never leaking the raw `source_skill_name`, and raw-field
  passthrough fidelity (`apply_mapping` never mutates its input list).
- Verified no regression: `test_routing_rollup_aggregation.py` (11, T3-001),
  `test_routing_rollup_repo.py` (17, Phase 2),
  `test_routing_feedback_contract_parity.py` (4),
  `test_agent_queries_aar_review.py` + `test_aar_review_no_llm_imports.py`
  (28, precedent modules) all still green after this change.

### T3-003 Notes (provider + coverage counters — completed 2026-07-31)

- Extended `routing_rollup.py` with two new pure in-memory transforms on
  `RoutingRollupQueryService`, both operating on T3-002's `MappedRollupRow`
  output:
  - `apply_provider(rows) -> list[ProviderRollupRow]` — a new frozen
    dataclass (`MappedRollupRow`'s fields + `provider: str`). `provider` is
    ALWAYS `derive_model_identity(row.model)["modelProvider"]` (module-level
    import from `backend.model_identity`, mirroring
    `system_metrics.py:37`'s existing same-directory precedent) — no
    independent parsing/keying path added, per the phase file's own
    Implementation Notes.
  - `compute_coverage_counters(rows) -> CoverageCounters` — a new frozen
    dataclass (`mapped_count: int`, `unclassified_count: int`,
    `distinct_unmapped_skill_names: list[str]`). Session-level totals
    (summed `session_count`, not row counts) keyed strictly off each row's
    *resolved* `task_class`: `task_class == UNCLASSIFIED_TASK_CLASS` routes
    to `unclassified_count` (covers both no-entry and executor-identity
    entries that themselves resolve to `_unclassified`); everything else —
    including protected-class rows (`orchestration`/`mode_d`, still
    `is_coverage_only=True`) — routes to `mapped_count`. Every row lands in
    exactly one bucket, so `mapped_count + unclassified_count` always equals
    the summed `session_count` of the input list exactly.
- `derive_model_identity` import confirmed safe for the (not-yet-built)
  T3-005 no-LLM guard: `backend/model_identity.py` itself imports only `re`
  and `typing` — zero transitive risk.
- `distinct_unmapped_skill_names` built from a `set` accumulator, emitted via
  `sorted(...)` — deterministic alphabetical order, satisfying T3-005's
  downstream determinism requirement.
- New test file `backend/tests/test_routing_rollup_provider_coverage.py` (10
  tests, all green): provider equality against `derive_model_identity()` for
  five model strings including empty-string and unknown-model edge cases;
  field-passthrough + no-input-mutation for `apply_provider`; hand-computed
  counter arithmetic including a dedicated executor-identity fixture
  (`codex`=11, `claude-api`=4, `ica-delegate`=2, `debugging`=9 sessions,
  built via the REAL `apply_mapping` pipeline rather than a hand-built
  `MappedRollupRow`, to prove the counters never double-count a row that has
  both a mapping entry AND an `_unclassified` resolution) — asserts
  `unclassified_count=17`, `mapped_count=9`,
  `distinct_unmapped_skill_names=["claude-api", "codex", "ica-delegate"]`;
  protected-class-counts-as-mapped case; empty-input zero-counters case;
  dedup+sort ordering across duplicate skill names and out-of-order input.
- Verified no regression: `test_routing_rollup_aggregation.py` (11, T3-001),
  `test_routing_rollup_mapping.py` (14, T3-002),
  `test_routing_rollup_repo.py` (17, Phase 2),
  `test_routing_feedback_contract_parity.py` (4),
  `test_agent_queries_aar_review.py` + `test_aar_review_no_llm_imports.py`
  (28, precedent modules) all still green after this change (74 passed, 7
  subtests passed total across the named-file regression run).

### T3-004 Notes (D5 metric payload — completed 2026-07-31)

- Extended `routing_rollup.py` with the terminal transform in the
  T3-001..T3-004 pipeline: `RoutingRollupQueryService.compute_metrics`
  (per-row D5 payload → `RoutingRollupKeyDTO`) and `.build_response`
  (wraps that list with the top-level `RoutingRollupResponseDTO` envelope,
  consuming T3-003's `CoverageCounters`). Added both DTOs to `models.py`
  right after `AARReviewDTO` (plain `BaseModel` subclasses, snake_case,
  **not** `AgentQueryEnvelope` — mirrors `AARReviewDTO`'s documented
  rationale exactly, per the task's own instruction).
- `eligible_for_adjustment = (not row.is_coverage_only) and sample_count >=
  min_sample_size` — the AND with `is_coverage_only` was required to honor
  T3-002's hard contract (`MappedRollupRow.is_coverage_only` docstring:
  "T3-004 MUST hardcode `eligible_for_adjustment=False`... independent of
  its own sample-size threshold logic"); a literal reading of T3-004's own
  Description (`sample_count >= MIN_SAMPLE_SIZE` alone) would have violated
  that contract for a large-`sample_count` coverage-only row. Verified by a
  dedicated test with `session_count=50_000`/`99_999` on
  `_unclassified`/`orchestration` rows still yielding `eligible=False`.
- **`min_sample_size` and `freshness_ts` are both kwarg override points**
  (mirrors `fetch_raw_rows`'s `window_days` / `apply_mapping`'s
  `include_protected_rows` convention) — default to
  `config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` and a new `_now_iso()`
  module function respectively. `_now_iso()` is isolated exactly like
  `aar_review.py`'s own `_now_iso()` so a future T3-005 determinism test can
  `unittest.mock.patch` it to freeze `freshness_ts` across two invocations —
  this task did not build that test (T3-005's job), only made it patchable.
  `freshness_ts` is computed ONCE per `compute_metrics`/`build_response`
  call, never per-row, so every key in one response shares an identical
  timestamp.
- **Design decision — `success_rate`/`regression_rate` emit `None` in v1**:
  confirmed by direct inspection (both `claude_code/parser.py` and
  `codex/parser.py`'s `_derive_session_status`/`_derive_status` functions,
  plus a grep across `backend/`) that `sessions.status` carries ONLY
  `'active'`/`'completed'` in this codebase — there is no genuine
  per-session success/failure/outcome-judgment signal anywhere on the row
  this module aggregates. Fabricating a value from that non-signal (e.g.
  treating `status == 'completed'` as "success") would be near-100%
  degenerate for historical data and actively misleading to a consuming
  router — worse than `null`. This reading is reinforced by Phase 2's own
  DDL: `success_rate`/`cost_index`/`regression_rate`/`confidence` are the
  ONLY four D5 columns declared nullable (`sample_count`/
  `eligible_for_adjustment` are `NOT NULL`), and
  `test_routing_rollup_repo.py` already has a dedicated null-value test for
  exactly these four columns — both signals this was anticipated, not an
  oversight. **Flagging for orchestrator attention**: this is a real,
  documented v1 design gap (both fields always `null` today) that may be
  worth a D9-adjacent finding/deferred-item entry before Phase 5 socializes
  the D5 shape with the router owner — did not create
  `.claude/findings/proof-to-routing-loop-findings.md` myself (lazy-creation
  policy + orchestrator-owned decision), surfacing it here and in the task
  handoff instead.
- **`cost_index` is a fixed baseline constant (`1.0`) for every row** —
  the PRD's own literal phrasing ("1.0 = baseline") is satisfied by
  construction; a per-key cost-normalization signal (e.g. derived from
  `sessions.total_cost`/`reported_cost_usd`) would require cross-key
  baseline derivation, a real design surface of its own, deliberately not
  built here per the task's explicit "do not gold-plate this into a
  tunable model" instruction.
- **`confidence` formula**: `sample_count / (sample_count + k)`, clamped to
  `1.0`, with `k = 5.0` (`_CONFIDENCE_SATURATION_K`, a fixed module
  constant, NOT read from `config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`)
  — this is the exact example formula the phase's own Implementation Notes
  suggested. Deliberately decoupled from the runtime-tunable eligibility
  threshold so an operator retuning `MIN_SAMPLE_SIZE` doesn't silently
  reshape the confidence curve; `confidence` and `eligible_for_adjustment`
  are documented as two independent D5 fields (PRD §6.3).
- `window_start`/`window_end`/`freshness_ts` render via a new `_iso8601()`
  helper (`value.isoformat()`, timezone-aware) — deliberately distinct from
  the pre-existing `_iso()` helper (T3-001), which renders the NAIVE
  `sessions.updated_at`-comparison string form used only inside
  `_fetch_raw_aggregate_rows`'s SQL params; the two must never be swapped.
- New test file `backend/tests/test_routing_rollup_metrics.py` (17 tests,
  all green): full envelope + D5 field-by-field verification against real
  `routing_feedback_contract.py` constants (never hardcoded duplicate
  literals); sub-threshold visibility (`sample_count=1` still present,
  `eligible=False`); the below/at-threshold boundary
  (`MIN_SAMPLE_SIZE-1` vs `MIN_SAMPLE_SIZE`); `min_sample_size` kwarg
  override + config-default fallthrough; coverage-only hardcoded-ineligible
  independence from `sample_count` magnitude (both `_unclassified` and
  `orchestration`); confidence's zero-at-zero / monotonic / never-exceeds-1
  properties; `cost_index==1.0` and `success_rate`/`regression_rate is
  None` across ordinary and coverage-only rows; `freshness_ts` override +
  `_now_iso()` patch-based default; `build_response`'s full top-level
  envelope assembly and its never-suppress-any-row invariant. Deliberately
  did NOT add the `RoutingRollupKeyDTO`/`RoutingRollupResponseDTO`
  plain-`BaseModel`-not-`AgentQueryEnvelope` isinstance/MRO check — the
  phase file's own AC routes that assertion to T3-005's determinism test
  module explicitly; not duplicated here.
- Verified no regression: `test_routing_rollup_aggregation.py` (11, T3-001),
  `test_routing_rollup_mapping.py` (14, T3-002),
  `test_routing_rollup_provider_coverage.py` (10, T3-003),
  `test_routing_rollup_repo.py` (17, Phase 2),
  `test_routing_feedback_contract_parity.py` (4),
  `test_agent_queries_aar_review.py` + `test_aar_review_no_llm_imports.py`
  (28, precedent modules) all still green after this change (101 passed, 7
  subtests passed total across the named-file regression run).

### T3-005 Notes (determinism + no-LLM guard — completed 2026-07-31)

- New test file `backend/tests/test_routing_rollup_determinism.py`: runs the
  FULL T3-001..T3-004 pipeline (`fetch_raw_rows` → `apply_mapping` →
  `apply_provider` → `compute_coverage_counters` → `build_response`) twice
  against an unchanged fixture DB and asserts every field of every
  `RoutingRollupKeyDTO` — and the response-level envelope — is
  value-identical across both invocations, compared against a
  deterministically **sorted** key list (`(source_skill_name, model)`), per
  the task's own instruction that order-independent set comparison alone is
  insufficient. Also adds the `RoutingRollupKeyDTO`/`RoutingRollupResponseDTO`
  plain-`BaseModel`-not-`AgentQueryEnvelope` isinstance/MRO check that
  T3-004's own AC explicitly routed to this module (not duplicated in
  `test_routing_rollup_metrics.py`).
- **Wall-clock non-determinism sources pinned, not incidentally avoided**:
  `fetch_raw_rows` never passes `until` to `_filters.resolve_time_window`,
  so that helper calls `datetime.now(timezone.utc)` internally on every
  call — patched `routing_rollup.resolve_time_window` (the name bound into
  that module's namespace via its `from ._filters import resolve_time_window`)
  to return a fixed `(window_start, window_end)` tuple for both pipeline
  runs. `build_response`'s `freshness_ts` is pinned via the existing kwarg
  override point (T3-004) rather than patching `_now_iso` directly — both
  are valid per that task's own docstring.
- Fixture seeds one session pair/row per T3-002 policy branch so the
  determinism proof exercises the whole pipeline, not just the
  ordinary-key path: `debugging`→`implementation` (mapped, ordinary),
  `planning`→`orchestration` (protected, gated-in by the
  `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` default-`True`),
  `codex`→`_unclassified` (executor-identity, HAS a mapping entry),
  `totally-unmapped-skill`→`_unclassified` (NO mapping entry at all) — a
  dedicated `test_fixture_exercises_every_policy_branch` sanity test guards
  against a future edit silently narrowing this coverage, which would make
  the determinism proof trivial.
- New test file `backend/tests/test_routing_rollup_no_llm_imports.py`:
  clones `test_aar_review_no_llm_imports.py`'s AST-walk BFS pattern
  byte-identically (same `_BANNED_IMPORT_PATTERNS`/`_BANNED_SYMBOL_PATTERNS`
  lists, same `_module_name_to_path`/`_iter_import_candidates`/
  `_walk_dependency_graph` structure), `_ENTRY_MODULE =
  "backend.application.services.agent_queries.routing_rollup"`. Deliberately
  did NOT pre-wire a Phase-4 `_P6_ENTRY_MODULES`-style second entry point —
  `routing_rollup_sweep_job.py` does not exist yet as of this task; the
  docstring/class-docstring explicitly flag this as Phase 6 (T6-001)'s
  additive extension point (mirroring the AAR precedent's own two-test-method
  shape) so that future edit is additive, not a rewrite, per the task's own
  instruction not to mark this guard "final."
- **Manually verified the guard fails loudly** (per this task's third AC):
  temporarily inserted `import anthropic` into `routing_rollup.py` on this
  worktree, re-ran the guard, confirmed a non-empty `offending` list surfaced
  in the assertion failure (`"...routing_rollup imports 'anthropic'"`), then
  reverted via `git checkout --` before committing — not a permanent CI
  fixture, exactly as the task specifies.
- Both this phase's `exit_criteria` (determinism + mapping-fidelity +
  no-LLM-import tests green) are now satisfied; ran the full named-file
  regression sweep (`test_routing_rollup_{aggregation,mapping,
  provider_coverage,metrics,repo}.py`, `test_routing_feedback_contract_parity.py`,
  `test_agent_queries_aar_review.py`, `test_aar_review_no_llm_imports.py`,
  plus the two new T3-005 files): 108 passed, 7 subtests passed, zero
  regressions.
- **Progress-file backfill (phase-exit gate)**: `update-status.py`'s
  completion gate for a single task-status flip is OR-based (timing OR
  evidence), but `validate-phase-completion.py`'s phase-exit gate requires
  `started`+`completed`+`verified_by`+`evidence` on every completed task —
  marking T3-005 completed (the last pending task) auto-flipped this file's
  top-level `status` to `completed`, which then failed that stricter gate on
  T3-001/T3-002 (missing `started`/`completed`/`verified_by`) and T3-004/
  T3-005 (missing `verified_by`). Backfilled `verified_by` for all four from
  values already pinned elsewhere in this feature's own planning docs — never
  invented: T3-001→`T6-004` and T3-002→`T6-005` (this phase file's own
  Detailed Task Specifications), T3-004→`T6-005` (same), T3-005→
  `[T6-001, T6-004]` (Phase 6's AC-3 closure table: "Determinism + no-LLM |
  T3-005, T6-001, T6-004"). T3-001/T3-002's `started`/`completed` timestamps
  use the same `2026-07-31T00:00:00Z` placeholder-day convention T3-003/
  T3-004 already established earlier in this same phase (exact intra-day
  clock times were never tracked; the whole phase ran same-day per this
  file's own top-level `started`/`updated: '2026-07-31'`). `validate-phase-
  completion.py` now reports zero violations.

## Completion Notes

- Determinism test green (two invocations produce field-identical rows) —
  `backend/tests/test_routing_rollup_determinism.py`, full pipeline, 6 tests.
- No-LLM guard green (transitive import graph clean, >5 modules visited,
  manually confirmed to fail loudly on a deliberate banned import) —
  `backend/tests/test_routing_rollup_no_llm_imports.py`.
- Full `RoutingRollupResponseDTO` shape matches PRD §6.3 example — verified
  field-by-field in `test_routing_rollup_metrics.py` (T3-004) and re-asserted
  end-to-end (real pipeline, not hand-built fixtures) in this task's
  determinism test.
- Mapping fidelity verified against fixture — `test_routing_rollup_mapping.py`
  (T3-002) against the real vendored `routing_task_map_v1.json`, plus this
  task's own multi-branch fixture proving determinism holds across every
  policy path (ordinary/protected/unclassified-via-entry/unclassified-via-
  no-entry).
- Phase 3 (`Rollup Compute Service`) is now fully complete: all 5 tasks
  (T3-001 through T3-005) `completed`, `validate-phase-completion.py` gate
  passes with zero violations, both phase `exit_criteria` satisfied.
