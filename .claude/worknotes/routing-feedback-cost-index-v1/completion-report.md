# Completion Report — Routing Feedback Cost Index (DI-4a)

Contract: `docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md`

## Summary

Replaced the fixed `_COST_INDEX_BASELINE = 1.0` placeholder in `routing_rollup.py`'s
`compute_metrics` with a real per-`(source_skill_name x model)` `cost_index`, derived from
`sessions.display_cost_usd`/`total_cost` aggregated in the same single `GROUP BY` query
`fetch_raw_rows` already issues. The index is normalized against a per-`task_class` mean
cost-per-covered-session baseline (D-a1, ratified). Zero-coverage keys/classes emit
`cost_index: null` (D-a2, hard constraint), never a fabricated placeholder. A new
`cost_coverage_fraction` field (D-a3) surfaces the covered/total session ratio so a consuming
router can discount a low-coverage `cost_index`. D-a4 (outlier handling) was implemented per the
contract's own recommendation: no separate suppression logic — reliance on the existing
`min_sample_size`/`eligible_for_adjustment` gate.

A second, closely related fix was made in `_client_v1_routing_rollup.py`'s `_row_to_key_dto`: it
previously defaulted a persisted `NULL` `cost_index` back to `1.0` on the
`/api/v1/routing/rollup` read path — exactly the fabricated-placeholder failure mode this
contract exists to remove, on the same endpoint the contract names in its API/Integration
Requirements section. This is documented as a deviation below since it touches a file outside
`routing_rollup.py`'s literal scope.

## Files Changed

- `backend/application/services/agent_queries/routing_rollup.py` — added `cost_sum`/
  `cost_covered_count` aggregates to `RawRollupRow`/`MappedRollupRow`/`ProviderRollupRow`; extended
  `_fetch_raw_aggregate_rows`'s single SQL statement (both SQLite and PostgreSQL branches) to
  aggregate `SUM(CASE WHEN COALESCE(display_cost_usd, total_cost, 0) > 0 THEN ... ELSE 0 END)` and
  a matching covered-session count; added `_task_class_cost_baselines` and
  `_cost_index_and_coverage` helpers; wired both into `compute_metrics`; removed the now-unused
  `_COST_INDEX_BASELINE` constant; updated module/class docstrings.
- `backend/application/services/agent_queries/models.py` — `RoutingRollupKeyDTO.cost_index` is now
  `float | None` (was a required `float`); added `cost_coverage_fraction: float = 0.0`.
- `backend/routers/_client_v1_routing_rollup.py` — `_row_to_key_dto` no longer defaults a
  persisted `NULL` `cost_index` to `1.0`; passes it through as `None`. Added
  `cost_coverage_fraction` passthrough (always `0.0` on this path since it is not persisted).
- `backend/tests/test_routing_rollup_metrics.py` — updated the two tests that hard-asserted
  `cost_index == 1.0`; added `cost_sum`/`cost_covered_count` kwargs to the `_provider_row` fixture
  helper; added five new test classes covering D-a1 (per-task_class baseline, incl. a test proving
  a global mean would have skewed the result but the implementation does not), D-a2 (zero-coverage
  null, both at the row level and at the whole-task_class level), D-a3 (partial coverage computed
  over the covered subset only + differing coverage fraction vs. a fully-covered key), and D-a4
  (a low-sample dominant-outlier key demonstrably NOT suppressed, but excluded from
  `eligible_for_adjustment` by the existing gate).
- `backend/tests/test_client_v1_routing_rollup.py` — replaced
  `test_cost_index_defaults_to_one_when_none` with `test_cost_index_null_passes_through_unchanged`;
  added `test_cost_coverage_fraction_defaults_to_zero_since_not_persisted`.
- `docs/guides/routing-feedback-loop.md` — updated the `cost_index` field definition (previously
  inaccurately described as "relative to the lowest-cost model", i.e. option (c) from D-a1, which
  was never the ratified choice) to describe the real per-task_class-mean behavior; added
  `cost_coverage_fraction` to the field table and the JSON example; marked `success_rate`/
  `regression_rate` explicitly nullable in the field table (they were already `null` in v1 but the
  table didn't say so).

## Acceptance Criteria Status

- [x] **Determinism**: `compute_metrics` performs pure arithmetic over its input row list — no
  wall-clock/randomness/ordering dependency introduced. Covered indirectly by the existing
  `test_routing_rollup_determinism.py` suite (unchanged, still green) plus the new deterministic
  unit tests.
- [x] **No LLM on the compute path**: `test_routing_rollup_no_llm_imports.py` still passes
  unmodified against the changed module.
- [x] **Zero-coverage key emits `null`**: `TestCostIndexZeroCoverage` — both a single zero-coverage
  row and an entire zero-coverage `task_class`.
- [x] **Partial-coverage key emits a computed index over the covered subset, differing coverage
  fraction asserted**: `TestCostIndexPartialCoverage`.
- [x] **Full-coverage key emits a real, non-constant `cost_index`**: `TestCostIndexFullCoverage`
  (includes a 4-distinct-input test proving the value is not a disguised constant).
- [x] **Baseline choice (D-a1) implemented and testable**: `TestCostIndexBaselineIsPerTaskClass` —
  two task classes with wildly different absolute costs but identical relative standing within
  their own bucket produce identical relative `cost_index` values.
- [x] **Outlier handling (D-a4) documented and tested**: `TestCostIndexOutlierHandling` — a
  low-sample key with one dominant expensive session produces the "overstated" raw-mean index
  (no suppression applied), but is excluded from `eligible_for_adjustment` by the existing gate.
- [x] **Existing digest-parity test stays green**: `test_routing_feedback_contract_parity.py`
  unmodified, still passes.
- [x] **Existing envelope-completeness test stays green**: `test_routing_rollup_envelope_completeness.py`
  unmodified (its seed fixture's literal `cost_index: 1.0` round-trips through
  `_row_to_key_dto`/the REST/MCP/CLI transports unchanged — the test only asserts envelope *shape*,
  never a specific `cost_index` value, so no update was needed there).
- [x] **Envelope stays additive/forward-compatible**: `cost_index` changed type from `float` to
  `float | None` (a widening, not a narrowing) and `cost_coverage_fraction` is a new, defaulted
  field — no existing field's shape or semantics changed. `test_routing_rollup_disabled_state.py`
  (byte-identical disabled-envelope test) unmodified, still passes.

## Validation Run

| Command | Result | Notes |
|---|---|---|
| `python -m py_compile backend/application/services/agent_queries/routing_rollup.py backend/application/services/agent_queries/models.py backend/routers/_client_v1_routing_rollup.py` | Pass | Build/import sanity. |
| `ruff check <6 touched .py files>` | Pass | "All checks passed!" — repo lint tool is `ruff`, not `flake8`. |
| `pytest backend/tests/test_routing_rollup_metrics.py -v` | Pass | 26/26 (was 17; +2 updated, +9 new). |
| `pytest backend/tests/test_client_v1_routing_rollup.py -v` | Pass | 22/22 (1 test replaced, 1 new). |
| `pytest backend/tests/test_routing_rollup_envelope_completeness.py backend/tests/test_routing_rollup_disabled_state.py backend/tests/test_routing_feedback_contract_parity.py backend/tests/test_routing_rollup_determinism.py backend/tests/test_routing_rollup_no_llm_imports.py backend/tests/test_routing_rollup_aggregation.py backend/tests/test_routing_rollup_repo.py backend/tests/test_routing_rollup_mapping.py backend/tests/test_routing_rollup_provider_coverage.py backend/tests/test_routing_rollup_sparse_protected.py backend/tests/test_routing_rollup_sweep_job.py backend/tests/test_routing_rollup_transports.py -q` (all unmodified) | Pass | 150 passed, 179 subtests passed total across the full listed set — no regressions in any adjacent routing-rollup test file. |
| `pytest backend/tests/test_cli_commands.py -k routing backend/tests/test_mcp_server.py -k routing -q` | Pass | CLI/MCP transports unaffected. |
| mypy/pyright | Not run | No mypy/pyright config found wired into this repo's `npm run` scripts; contract marks this N/A unless the project runs one. |
| `pnpm test`/`type-check`/`lint` | N/A | Backend-only change, no frontend files touched. |

## Deviations From Contract

1. **Touched `backend/routers/_client_v1_routing_rollup.py` and
   `backend/tests/test_client_v1_routing_rollup.py`**, outside the contract's literal "this
   contract touches `routing_rollup.py`, its cost helper(s), and its tests only" scope statement.
   Justification: the contract's own §7 explicitly names `GET /api/v1/routing/rollup` as the
   endpoint whose `cost_index` behavior changes, and that endpoint is served entirely by
   `_client_v1_routing_rollup.py`'s persisted-table read path (`routing_rollup.py`'s
   `compute_metrics`/`build_response` are only invoked by the Phase 4 sweep worker, never
   in-request). Leaving `_row_to_key_dto`'s `None -> 1.0` fallback in place would have meant every
   value that AC-2 (zero-coverage emits `null`) is centrally about gets silently converted back
   into the exact fabricated placeholder the contract exists to remove, the moment it round-trips
   through the one endpoint the contract names by path. This was judged a required fix to satisfy
   the contract's own AC, not scope creep.
2. **D-a1/D-a2/D-a3/D-a4 all implemented per the contract's own recommendations, no re-litigation.**
   No deviation on the design-decision content itself.
3. **No new DDL/column** — `cost_coverage_fraction` is computed-not-persisted, exactly as the
   contract's Data Requirements section anticipated as the preferred outcome if a coverage signal
   needed a home. It is `0.0` (not the live fraction) when read back through the persisted
   `routing_rollup` table, since that table has no column for it; this is documented in the DTO's
   own docstring and covered by a dedicated test.

## Risks / Limitations

- The `cost_coverage_fraction` signal is only "live" on the in-process `compute_metrics`/
  `build_response` call path (used by the Phase 4 sweep worker when it computes what to persist).
  Once persisted and read back through `/api/v1/routing/rollup`, it is always `0.0` — a router
  consuming that live endpoint today cannot yet use it to discount partial coverage. Closing this
  gap would require either a new `routing_rollup` DDL column (explicitly out of scope for this
  contract) or persisting it in an existing column's semantics — neither was attempted here per the
  contract's explicit "no new DDL" instruction.
- `sessions.total_cost` has a `DEFAULT 0.0` (not `NULL`) at the DDL level; the "no cost
  attribution" criterion (`COALESCE(display_cost_usd, total_cost, 0) > 0`) treats a genuine
  zero-cost session identically to an uninstrumented one. This mirrors the feature contract's own
  cited signal-source audit criterion (`> 0`) verbatim, so it is not a new gap introduced by this
  work, but it means a legitimately free session (if one ever exists) would count as "uncovered."

## Follow-up Recommendations

- DI-4b (`success_rate`/`regression_rate`) remains a separate, unscoped feasibility question per
  its own exploration charter — this contract's `_task_class_cost_baselines` pattern (grouping by
  the same already-resolved `task_class` field) is directly reusable if DI-4b ever needs a
  per-class outcome baseline of its own.
- If the router ever needs a live `cost_coverage_fraction` through the persisted read path, a
  follow-up contract should either add the column (new DDL, its own schema-version bump) or fold
  it into the `routing_rollup` table's existing JSON-shaped columns if one exists — neither was
  explored here since it was explicitly out of scope.

## Memory Candidates Captured

- None captured as durable memory items — findings here are fully contained in this Completion
  Report and the contract's own decision records (D-a1..D-a4); no new gotcha/pattern discovery
  outside what the contract already anticipated.
