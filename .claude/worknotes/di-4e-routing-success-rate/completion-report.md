## Completion Report

### Summary

Replaced `routing_rollup.py`'s permanent `success_rate=None` placeholder with a
real per-`(project_id, source_skill_name, model)` tool-error-rate complement,
call-volume-weighted (D-b1) and null-on-zero-attribution (D-b2). Added a new
per-key `success_rate_coverage_fraction` companion (compute-layer/response-DTO
only, no persisted column) and two response-level skill-dimension coverage
counters (`skill_attributed_key_count`/`skill_unattributed_key_count`, D-b3).
`regression_rate` stays permanently `None` with a citation comment (DI-4b
closure, AC4); `CCDASH_ROUTING_FEEDBACK_ENABLED`/`live_consumption_disabled`
untouched (AC5). No new column/migration — matches the contract's explicit
"no schema change" constraint.

### D-b4 Live Verification Result — **EXECUTED (fix cycle 1); result = HALT**

AC2 requires running the D-b4 live family-split verification query against the
current 30-day window and recording pass/HALT. **Fix cycle 1 executed this live
query against the actual operative database** (node Postgres,
`10.42.10.76:5440`, per project convention — connection string sourced from the
repo root's gitignored `.env`, never hardcoded), adapting
`di-4d-remeasurement.md` §1's SQL to the current window. (The prior cycle's
"could not execute — no reachable DB" finding was itself incorrect: the main
repo checkout's `.env` — gitignored, not committed, not previously consulted —
pins this worktree's `CCDASH_DATABASE_URL` at that node Postgres. `asyncpg` in
`backend/.venv` was used to run the query directly, with the DSN passed only
via an environment variable at invocation time, never written to any
committed file.)

**Query executed** (adapted to "now" instead of the document's 2026-08-03
capture date; identical `min_sample=5` aggregation and `stddev>0`
"informative" definition as `di-4d-remeasurement.md` §1–2):

```sql
WITH per_session AS (
  SELECT session_id, SUM(call_count) AS calls, SUM(success_count) AS successes
  FROM session_tool_usage GROUP BY session_id),
win AS (
  SELECT s.id, s.project_id, s.skill_name, s.model FROM sessions s
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS'))
SELECT w.project_id, w.skill_name, w.model, w.id, ps.calls, ps.successes
FROM win w LEFT JOIN per_session ps ON ps.session_id = w.id;
```

**Live output (2026-08-10, run against the node Postgres 30-day rolling window)**,
aggregated to `(project_id, skill_name, model)` with `HAVING count(*) >= 5`:

| family | keys | informative | zero-mean | no-data | calls | errors | err_rate |
|---|---|---|---|---|---|---|---|
| claude-family | 157 | 154 (98.1%) | 3 | 0 | 189,664 | 7,196 | 3.79% |
| gpt/codex-family | 28 | **6 (21.4%)** | 21 | 1 | 46,394 | **19** | **0.04%** |
| synthetic | 4 | 2 (50.0%) | 1 | 1 | 342 | 8 | 2.34% |
| empty model | 8 | 0 | 0 | 8 | 0 | 0 | n/a |
| **TOTAL** | **197** | **162 (82.2%)** | 25 | 10 | 236,400 | 7,223 | 3.06% |

(Denominator: 6,993 sessions in the 30-day window, 395 all keys, 197 clearing
`min_sample=5`, 6,604 sessions inside those keys — a live-data snapshot, not
directly the same 188-key set `di-4d-remeasurement.md` measured on 2026-08-03,
since the rolling window has advanced ~1 week and the fleet has grown.)

**Determination: HALT.** The gpt/codex-family informative-key fraction is
**21.4%** and its error rate is **0.04%** — this sits far closer to
`di-4d-remeasurement.md`'s documented **BEFORE** state (0.0% informative,
0.00% error rate — the old-parser artifact) than to its **AFTER** state (89.2%
informative, 1.48% error rate — the fixed-parser re-parse). This is the exact
failure mode D-b4 exists to catch: **the current live 30-day window is still
measurably dominated by stale pre-`b51de27` `session_tool_usage` rows for the
Codex/GPT family.** The parser fix landed at commit `b51de27`, but — exactly as
`di-4d-remeasurement.md` §0/§7 warned — a code fix does not retroactively
correct rows already written by the old parser, and no backfill/resync of
historical Codex `session_tool_usage` rows has run. Shipping `success_rate` for
this family today would silently reintroduce the categorical-zero skew DI-4d
exists to close, for exactly the family this contract most needs to be correct
about.

**Per the contract's own D-b4 ratification ("HALT this contract and report —
do not ship") and the explicit `escalation_recommendation` in the contract's
frontmatter, this contract does not ship as-is.** See "HALT — Escalation and
Follow-Up Scope" below for the recommended precondition and re-run path. This
report leaves the already-implemented code as-is — the compute logic is
correct-by-construction and was independently re-verified by the reviewer
(what is blocked is *shipping*, not the *implementation's correctness*) — but
withdraws this contract from `completed`/ship-ready status pending the
backfill precondition below.

### HALT — Escalation and Follow-Up Scope

Per the contract's ratified `escalation_recommendation`:

> "If the D-b4 live-verification gate HALTs (window still skewed by stale
> pre-`b51de27` Codex `session_tool_usage` rows), do not force the sprint --
> promote to a short Tier 1 follow-up scoped around a Codex
> `session_tool_usage` backfill/resync precondition, then re-run this same
> contract once the window is clean."

**Recommended follow-up scope** (for a new, short Tier 1 feature contract,
NOT expanded into this one):

1. **Backfill/resync `session_tool_usage` for Codex sessions** whose rows
   predate commit `b51de27` — re-parse the raw `~/.codex/sessions/**/*.jsonl`
   through the fixed `parse_session_file`/`tool_outcome.py` and overwrite the
   stale `call_count`/`success_count` rows for those sessions, mirroring the
   re-parse method `di-4d-remeasurement.md` §0 already validated (99.9% file
   coverage on that pass).
2. **Re-run this exact D-b4 verification query** against the live window once
   the backfill has run, to confirm the gpt/codex-family informative fraction
   has moved back toward the ~89% `di-4d-remeasurement.md` demonstrated is
   achievable, not still stuck near the ~0-20% stale-row artifact measured
   above.
3. **Then re-run this DI-4e contract** (or simply flip its status back to
   ready-to-ship) — no code change is anticipated to be needed at that point;
   this contract's implementation already computes `success_rate` correctly
   for whatever the live rows say, so a clean backfill is expected to be
   sufficient without touching `routing_rollup.py` again.
4. Since `live_consumption_disabled` (AC5, DI-1) stays true throughout, no
   router acts on the interim (skewed) values in production — the backfill is
   a trust precondition for the *signal*, not an emergency mitigation for an
   active incident.

**Not resolved by this fix cycle**: whether to leave the already-merged
`routing_rollup.py`/`models.py`/docs changes on this branch pending the
backfill, or to hold the branch unmerged until the backfill lands. That is an
Opus/operator decision (per the fix-cycle instructions, which scope this cycle
to running the verification and recording the result, not to further code or
merge decisions) — flagged explicitly here rather than decided unilaterally.

### Files Changed

- `backend/application/services/agent_queries/routing_rollup.py` — extended
  `_fetch_raw_aggregate_rows`'s single aggregate query with a `LEFT JOIN`
  against a `(project_id, session_id)` pre-aggregate CTE of
  `session_tool_usage` (scoped by both columns together, never `session_id`
  alone — `sessions`' own PK is the composite `(project_id, id)`). Threaded
  `tool_call_sum`/`tool_success_sum`/`tool_usage_covered_count` through
  `RawRollupRow` → `MappedRollupRow` → `ProviderRollupRow`. Added
  `_success_rate_and_coverage` (mirrors `_cost_index_and_coverage`'s
  shape/docstring rigor) and `_skill_dimension_coverage`. Wired both into
  `compute_metrics`/`build_response`. Added the `regression_rate` DI-4b
  citation comment at the assignment site.
- `backend/application/services/agent_queries/models.py` — added
  `RoutingRollupKeyDTO.success_rate_coverage_fraction` and
  `RoutingRollupResponseDTO.skill_attributed_key_count`/
  `skill_unattributed_key_count`. Updated both classes' docstrings.
- `backend/routers/_client_v1_routing_rollup.py` — **deviation, see below**:
  extended `_build_response_from_rows` to reassemble the two new
  skill-dimension counters from persisted rows (same population definition as
  the compute layer), and set `success_rate_coverage_fraction=None` explicitly
  (documented as always-null on this read path, since the field is
  compute-layer-only). This file is NOT in the contract's declared
  `files_affected` list.
- `backend/tests/test_routing_rollup_metrics.py` — added
  `TestSuccessRateZeroCoverage`, `TestSuccessRateFullCoverage`,
  `TestSuccessRatePartialCoverage`, `TestSuccessRateCallVolumeWeighted` (the
  D-b1 synthetic 200-call-vs-2-call case), `TestSuccessRateDeterminism`,
  `TestSkillDimensionCoverageCounters`; renamed/refocused the old
  `TestUnavailableSignals` to `TestRegressionRatePermanentlyNone` (success_rate
  is no longer permanently unavailable, so the combined class name was
  inaccurate — the assertion itself was not weakened, only regression_rate's
  half of it was kept and success_rate's half moved to its own dedicated
  classes above).
- `backend/tests/test_routing_rollup_envelope_completeness.py` — added the
  `SKILL_DIMENSION_COUNTER_FIELDS` presence check and a dedicated
  `test_skill_dimension_counters_reflect_min_sample_size_population` test
  across all three transports. Also fixed a **pre-existing, unrelated** bug
  discovered while touching this file: `_make_seed_row`'s base fixture dict
  was missing `cost_coverage_fraction` (the v47 column), which failed its own
  `assert set(row) == set(ROUTING_ROLLUP_COLUMNS)` shape check — this bug
  predates this task (confirmed via `git diff`/`aos-git refresh` showing the
  file was untouched before this sprint) and is unrelated to DI-4e; fixed as
  part of the contract's instruction to update this file, not left broken.
- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` —
  updated §0's field table (`success_rate` now SUPERSEDED/real,
  `regression_rate` reconfirmed permanently null), added new §0a documenting
  DI-4e as shipped with the D-b1..D-b5 decisions and the D-b4 caveat above,
  and updated the "Consequent routing" DI-4b status line.
- `docs/guides/routing-feedback-loop.md` — updated the field-definition tables
  (per-key `success_rate`/`success_rate_coverage_fraction`/`regression_rate`;
  top-level `skill_attributed_key_count`/`skill_unattributed_key_count`) and
  both the enabled and disabled envelope JSON examples.

### Acceptance Criteria Status

- [x] **AC1**: `success_rate` populated only for keys with genuine tool-usage
  attribution; `null` (never fabricated) otherwise, with a coverage companion
  emitted. Tested (zero/partial/full coverage classes).
- [ ] **AC2**: D-b4 live verification query **was executed** against the node
  Postgres (fix cycle 1) and returned **HALT** — the current 30-day window's
  gpt/codex-family is measurably skewed by stale pre-`b51de27`
  `session_tool_usage` rows (21.4% informative / 0.04% err_rate, vs. the
  fixed-parser 89.2% informative / 1.48% err_rate `di-4d-remeasurement.md`
  demonstrated is achievable). Per the contract's own D-b4 ratification, this
  contract does **not** ship as-is. See "HALT — Escalation and Follow-Up
  Scope" above; AC2 is explicitly **not met** and this is not a code defect.
- [x] **AC3**: Skill-dimension coverage counters added to the response
  envelope (both compute layer and persisted-read path) and documented in
  `routing-feedback-loop.md` and `routing-feedback-router-merge-handoff.md`,
  citing the feasibility brief's ~40-45% figure.
- [x] **AC4**: `regression_rate` remains `None` with a citation comment at the
  `compute_metrics` assignment site and in both DTOs' docstrings.
- [x] **AC5**: No change to `CCDASH_ROUTING_FEEDBACK_ENABLED`/
  `live_consumption_disabled`. Verified by diff review — neither symbol
  appears in any of this sprint's edits except in comments/docstrings.

**Additional engineering ACs:**
- [x] Determinism test (`TestSuccessRateDeterminism`).
- [x] Zero-tool-usage key asserts `success_rate is None` directly
  (`TestSuccessRateZeroCoverage`).
- [x] Partial-coverage key's `success_rate` computed over the covered subset,
  coverage signal differs from a fully-covered key's
  (`TestSuccessRatePartialCoverage`, two tests).
- [x] Full-coverage key's `success_rate` changes when underlying inputs change
  (`TestSuccessRateFullCoverage::test_success_rate_changes_when_underlying_call_error_inputs_change`).
- [x] D-b1 call-volume-weighted synthetic case (200-call/1-error vs 2-call/
  1-error) asserts the call-volume-weighted answer, not the per-session mean
  (`TestSuccessRateCallVolumeWeighted`).
- [x] Existing digest-parity/envelope-completeness tests updated only where
  they asserted the old fixed `None` (`TestUnavailableSignals` →
  `TestRegressionRatePermanentlyNone`, regression_rate assertion unchanged,
  success_rate assertion moved to its own dedicated classes) — never weakened.

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `pytest backend/tests/test_routing_rollup_metrics.py -v` | Pass (34/34) | |
| `pytest backend/tests/test_routing_rollup_envelope_completeness.py -v` | Pass (3/3, 17 subtests) | Includes the pre-existing fixture fix |
| `pytest backend/tests/test_client_v1_routing_rollup.py` | Pass (24/24) | |
| `pytest backend/tests/test_routing_rollup_aggregation.py` | Pass (11/11, 3 subtests) | Exercises the new SQL join against a real sqlite DB |
| `pytest backend/tests/test_routing_rollup_determinism.py` | Pass (8/8) | |
| `pytest backend/tests/test_routing_rollup_disabled_state.py` | **8 failed** (pre-existing, unrelated) | Same `cost_coverage_fraction`-missing fixture bug as the one fixed in `test_routing_rollup_envelope_completeness.py`, but in a **different file not in this contract's `files_affected`**. Confirmed pre-existing via `git diff`/`aos-git refresh` (file untouched by this sprint). Not fixed here — out of declared scope; flagged as a Follow-Up below. |
| `pytest backend/tests/test_routing_rollup_effort_dimension.py` | Pass (19/19) | |
| `pytest backend/tests/test_routing_rollup_mapping.py` | Pass (14/14, 2 subtests) | |
| `pytest backend/tests/test_routing_rollup_no_llm_imports.py` | Pass (2/2, 1 subtest) | CI no-LLM-import grep guard still green |
| `pytest backend/tests/test_routing_rollup_provider_coverage.py` | Pass (10/10) | |
| `pytest backend/tests/test_routing_rollup_repo.py` | Pass (18/18) | |
| `pytest backend/tests/test_routing_rollup_sparse_protected.py` | Pass (15/15, 132 subtests) | |
| `pytest backend/tests/test_routing_rollup_sweep_job.py` | Pass (3/3) | |
| `pytest backend/tests/test_routing_rollup_transports.py` | Pass (4/4) | |
| `pytest backend/tests/ -k routing_rollup` (full collection) | Not run — segfaults | Known repo-wide pytest-collection hazard (see project memory: "CCDash pytest collection hangs" — `test_runtime_bootstrap`/`test_sse_wire_boundary` crash at import in full collection). Ran every `*routing_rollup*` file individually instead (all above) — equivalent coverage, no gap. |
| `ruff check` (5 touched Python files) | Pass | "All checks passed!" |
| `python -m py_compile` (5 touched Python files) | Pass | |
| Module import smoke (`routing_rollup`, `models`, `_client_v1_routing_rollup`) | Pass | |

### Deviations From Contract

1. **Touched `backend/routers/_client_v1_routing_rollup.py`, not in the
   contract's declared `files_affected`.** Discovered during implementation:
   ALL THREE transports (REST, MCP, CLI) read `RoutingRollupResponseDTO`
   exclusively through this module's `_fetch_routing_rollup`/
   `_build_response_from_rows` — never through
   `RoutingRollupQueryService.build_response` directly (that live-compute path
   is only invoked by the worker sweep job, to *persist* rows, not to *serve*
   reads). AC3 requires the skill-dimension counters to actually appear "in
   the envelope" a consumer receives — if I had not touched this file, the
   two new counters would always read back `0`/`0` on every real consumer
   transport, silently failing AC3's intent while technically satisfying it at
   the compute-layer-only level. I judged this a necessary consequence of
   implementing AC3 correctly, not a scope expansion, and made the change
   as a small, pattern-consistent addition mirroring the exact same
   `mapped_count`/`unclassified_count` reassembly logic already in that file.
2. **AC2's D-b4 live query could not be executed** — see the dedicated section
   above. This is the most significant deviation; flagged prominently, not
   buried.
3. **`success_rate_coverage_fraction` is compute-layer/response-DTO only, not
   persisted** — this was the implementer's choice the contract left open
   ("exact field name is this contract's implementation decision"), but the
   consequence (it is invisible on every persisted-read transport) is worth
   restating: it is testable and correct at the compute layer
   (`RoutingRollupQueryService.compute_metrics`), satisfying the letter of the
   "Additional engineering ACs" partial/full-coverage tests, but a live
   consumer reading `/api/v1/routing/rollup` today will always see `null` for
   it. Documented in three places (module docstring, DTO docstring, guide doc)
   so this is not a silent gap.
4. **`test_routing_rollup_disabled_state.py`'s pre-existing failure was left
   unfixed** — same root-cause bug as the one I fixed in
   `test_routing_rollup_envelope_completeness.py` (a static fixture dict
   missing the v47 `cost_coverage_fraction` column), but that file is not in
   this contract's declared scope and fixing it there was not necessary for
   any AC in this contract. Flagged as a Follow-Up, not silently left broken
   without mention.

### Risks and Limitations

- **AC2 is confirmed HALTED, not merely unverified** — see D-b4 section. The
  code is correct and tested, but the *current live production data* is
  confirmed **not** trustworthy for the Codex/GPT family specifically (21.4%
  informative vs. the ~89% a clean window should show). This contract should
  not be treated as ship-ready until the backfill/resync precondition in "HALT
  — Escalation and Follow-Up Scope" runs and a re-check of this same query
  passes. The risk is moot for production *today* only because
  `live_consumption_disabled` stays true — but that is not a substitute for
  clearing AC2 before this contract is marked complete.
- **D-b5 (retry/recovery blindness)** is documented, not modeled, per the
  contract's explicit instruction — restated in the module docstring, the DTO
  docstring, and both updated docs.
- **`success_rate_coverage_fraction` invisibility on read transports** (see
  Deviation 3) is a real, if minor, usability gap for a future consumer
  expecting parity with `cost_coverage_fraction`'s persisted behavior.

### Follow-Up Recommendations

1. **Scope and run the Tier 1 backfill/resync follow-up** named in "HALT —
   Escalation and Follow-Up Scope" above: re-parse pre-`b51de27` Codex
   `session_tool_usage` rows, then re-run this exact D-b4 query to confirm the
   window is clean before treating this contract as ship-ready.
2. **Fix `test_routing_rollup_disabled_state.py`'s pre-existing fixture bug**
   (missing `cost_coverage_fraction` in its seed-row dict) — a small, separate,
   unrelated cleanup; not blocking, not part of this contract.
3. Consider a future Tier 0/1 follow-up to actually persist
   `success_rate_coverage_fraction` (would require a schema migration,
   explicitly out of scope here) if a live consumer ever needs it to survive
   the read path the way `cost_coverage_fraction` does since v47.

### Memory Candidates Captured

None captured via the memory CLI/API in this sprint (sandboxed environment,
no live DB — the memory item creation flow was not exercised to avoid the
same class of environment risk already documented above). The durable lessons
below are recorded here for the reviewer/Opus to promote manually if desired:

- **Gotcha**: `sessions`' primary key is the composite `(project_id, id)`, not
  a globally-unique `id` — any future join against a child table keyed only
  by `session_id` (e.g. `session_tool_usage`, whose own PK is
  `(session_id, tool_name)`) must scope the join by BOTH `project_id` AND
  `session_id`/`id` together, or risk silently fusing two different projects'
  sessions that happen to share an id string. (Anchor:
  `backend/db/sqlite_migrations.py:308`, `backend/application/services/agent_queries/routing_rollup.py::_fetch_raw_aggregate_rows`.)
- **Pattern**: all three routing-rollup transports (REST/MCP/CLI) share one
  read path — `backend/routers/_client_v1_routing_rollup.py::_fetch_routing_rollup`
  — never the live `RoutingRollupQueryService.build_response` directly. Any
  future field added to `RoutingRollupResponseDTO`/`RoutingRollupKeyDTO` that
  must be visible to a real consumer needs a corresponding update in that
  router file's reassembly logic, not just the compute-service file — the two
  are easy to conflate as "the same code path" but are not.
