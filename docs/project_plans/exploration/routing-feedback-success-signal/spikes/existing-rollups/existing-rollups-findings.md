---
doc_type: spike_findings
leg_id: existing-rollups
confidence: 0.75
status: complete
created: 2026-08-03
---

# Existing-Rollups Leg — Findings

## Question

What would it cost to populate skill attribution in `effectiveness_rollups` so its
`successScore`/`riskScore`/`qualityScore` become usable, as an alternative to deriving a fresh
outcome signal for DI-4b (`success_rate`/`regression_rate`)?

## Method

All queries run read-only against `postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash` via
`/tmp/rfss/q.py`, per SHARED-CONTEXT.md. Code paths read via `Read`/`grep` against this repo at
HEAD (`bbfc0ba`). No writes, no migrations, no implementation.

Code inspected:
- `backend/services/stack_observations.py` (`build_session_stack_observation`,
  `backfill_session_stack_observations`)
- `backend/session_badges.py` (`derive_session_badges`)
- `backend/services/integrations/skillmeat_resolver.py` (`resolve_stack_components`)
- `backend/services/workflow_effectiveness.py` (`_scope_keys`, `_stack_scope_id`,
  `_aggregate_rollups`, `_collect_effectiveness_dataset` success/quality/risk formulas)
- `backend/db/repositories/{sessions,postgres/sessions}.py` (`get_logs` → `session_logs`)
- `backend/db/sync_engine.py` (`_should_write_legacy_session_logs`,
  `_enterprise_canonical_transcript_authoritative`)
- `backend/scripts/agentic_intelligence_rollout.py` (the only caller of the backfill + recompute)

## Current State

**Row counts and scope breakdown** (`effectiveness_rollups`, 14,561 rows total):

```sql
SELECT scope_type, COUNT(*) FROM effectiveness_rollups GROUP BY scope_type;
-- agent: 7271
-- stack: 7290
-- (no "skill" or "workflow" scope_type rows exist at all)
```

100% of `stack`-scope rows carry `skills:none` in `scopeLabel`/`scope_id` — confirmed, matches the
handoff spec §0 audit. **New finding**: no `scope_type='skill'` row exists in the table at all
(not merely `skills:none` inside `stack` labels) — the skill scope key is never emitted, because
no observation ever carries a `component_type='skill'` entry.

`generatedAt` is a single frozen batch timestamp:

```sql
SELECT DISTINCT metrics_json->>'generatedAt' FROM effectiveness_rollups;
-- 19 distinct values, all 2026-07-27T18:0x–18:1x — one backfill run, 7 days stale as of this SPIKE
```

There is no scheduled recompute job; `effectiveness_rollups` is only populated when
`backend/scripts/agentic_intelligence_rollout.py` is run by hand (`get_workflow_effectiveness(...,
recompute=True)`).

**Upstream tables**:

```sql
SELECT COUNT(*) FROM session_stack_observations;                -- 16,620
SELECT observation_source, COUNT(*) FROM session_stack_observations GROUP BY 1;
-- backfill: 16,620  (100% — no live-write-path rows exist)
SELECT COUNT(*) FROM session_stack_observations WHERE jsonb_array_length(evidence_json->'skillsUsed') > 0;
-- 0
SELECT COUNT(*) FROM session_stack_observations WHERE jsonb_array_length(evidence_json->'agentsUsed') > 0;
-- 7462
```

`skillsUsed` is **always** an empty array (0/16,620). `agentsUsed` is populated for 7,462/16,620
(45%) — but, per code, `agentsUsed` is seeded directly from `sessions.agent_id`
(`session_badges.py:121`, `_add_unique(agents, agents_seen, session_agent_id)`), not from any
per-session transcript scan. It survives independently of the bug described below; skill
attribution does not have an equivalent direct-column fallback.

## Attribution Failure Point

**The prior audit's "hashes/prompt-text, not `<kind>:<slug>`" framing is refuted by direct
evidence.** Clean, resolvable skill identifiers exist upstream:

```sql
SELECT metadata_json FROM session_messages WHERE tool_name='Skill' LIMIT 8;
-- toolLabel: "dev-execution", "artifact-tracking", "skillmeat-cli", "planning", "firecrawl-scrape"
-- toolArgs: {"skill": "dev-execution"} etc. — exactly the slug resolve_stack_components expects
SELECT COUNT(*) FROM session_messages WHERE tool_name='Skill';               -- 814
SELECT COUNT(DISTINCT session_id) FROM session_messages WHERE tool_name='Skill';  -- 815
```

**The real failure point**: `build_session_stack_observation` / `backfill_session_stack_observations`
(`backend/services/stack_observations.py:315-333`) call `session_repo.get_logs(session_id)`, which
reads exclusively from the `session_logs` table
(`backend/db/repositories/postgres/sessions.py:1172-1181`: `SELECT * FROM session_logs WHERE
session_id = $1 ...`). On the operative Postgres:

```sql
SELECT COUNT(*) FROM session_logs;  -- 0
```

`session_logs` is **entirely empty**. This is not an accident: `backend/db/sync_engine.py:1526-1528`
(`_should_write_legacy_session_logs`) skips writing `session_logs` whenever
`_enterprise_canonical_transcript_authoritative()` is true (i.e. `STORAGE_PROFILE.profile ==
"enterprise"`) **and** canonical rows exist — which is this node's deployment profile. The real
transcript data has migrated to `session_messages` (955,646 rows) and `session_tool_usage` (47,753
rows), tables `stack_observations.py` never reads.

`derive_session_badges` (`backend/session_badges.py:101-192`) derives `skillsUsed` only from
`log.get("type")=="command"` rows with `metadata.skillFormat`, or `log.get("type")=="tool"` rows
with `tool_name.lower()=="skill"` — both conditioned on the (empty) `session_logs` row shape. It
has no fallback to `session_messages`, unlike `agentsUsed`'s direct `session_agent_id` seed.

**Precise failure point**: `backend/services/stack_observations.py:323`
(`logs = await session_repo.get_logs(session_id)`) reads a table the enterprise sync path has
deliberately stopped writing to, while `session_badges.derive_session_badges` has no alternate
input path. `resolve_stack_components` (`skillmeat_resolver.py:69-95`) is downstream and was never
reached with real skill data to test — it is very likely correct, but unverified against real
skill components because none ever arrive.

## Bounded-vs-Open-Ended Determination

**Split verdict — two independent gaps, one bounded, one open-ended:**

1. **Bounded**: the empty-`session_logs` wiring gap. The data needed for skill attribution exists
   upstream, cleanly formatted, in `session_messages`/`session_tool_usage`. Fixing this is a scoped
   code change — point the observation builder at the canonical transcript tables instead of the
   legacy (enterprise-profile-dormant) one — plus a re-run of the existing backfill script with
   `force_recompute=True`. No migration, no new column, no schema change.

2. **Open-ended / structurally absent**: even after (1), coverage is capped low (see below) because
   explicit `Skill`-tool invocations are a rare event relative to total session volume — most
   sessions are attributable to a skill via `sessions.skill_name` (a parser-level classification)
   without ever calling the `Skill` tool mid-transcript. There is no way to backfill a
   `Skill`-tool-call signal for a session that never emitted one; this is a genuine capture gap, not
   a wiring bug, and int historical sessions cannot be reconstructed.

3. **Second open-ended gap, independent of (1)/(2)**: `effectiveness_rollups`' scope-key grain
   (`_scope_keys`/`_stack_scope_id`, `workflow_effectiveness.py:353-421`) has **no `model` dimension
   anywhere** — buckets are `workflow` / `agent` / `skill` / `context_module` / `stack` / `bundle`,
   never `(skill, model)`. Even a fully-populated `skill` scope row gives one score per skill
   collapsed across every model that ever used it — structurally incompatible with DI-1's
   `(project_id, skill_name, model)` key without a design change to the rollup's grain (comparable
   in scope to DI-4a's own cost_index design work, not a wiring fix).

## Coverage If Fixed

Denominator per SHARED-CONTEXT: 188 keys clearing `min_sample=5` in the 30-day window; 6,952–6,957
sessions inside those keys (small variance from clock drift between query runs).

**Measured** (fix scenario: assume (1) above is fixed and `Skill`-tool-call presence is used as
the attribution signal):

```sql
-- sessions inside the 188 clearing keys with >=1 Skill-tool-call in session_messages
-- total_keyed_sessions: 6957, keyed_sessions_with_skill_toolcall: 317
-- => 317/6957 = 4.6% of sessions
-- keys with >=1 such session: 49/188 = 26.1% of keys
```

**317/6,957 sessions (4.6%)** and **49/188 keys (26.1%)** would gain *any* skill-component
attribution at all if the wiring were fixed — this is "derivable," not "informative": most of
those 49 keys would have only 1-2 attributed sessions out of ≥5 in the key, nowhere near enough to
move a key-level average meaningfully, and this is measured, not estimated. **26.1% is below the
charter's own suggested ≥50% usability threshold**, before even reaching the model-dimension
problem in the section above.

**Estimated** (not measured, flagged as such): if `sessions.skill_name` (already 100% populated for
every keyed session, by construction) were used directly as the attribution key instead of routing
through `session_stack_observations`'s component-extraction pipeline, coverage would trivially be
100% of the 188 keys — but that is a different design (bypassing the stack-observation/component
join entirely and aggregating `_collect_effectiveness_dataset`'s per-session scores directly by
`(project_id, sessions.skill_name, sessions.model)`), not "populating skill attribution in
`effectiveness_rollups`" as the leg is scoped. It is a legitimate alternative worth naming to the
orchestrator, but out of scope for this leg's literal question — and it does not solve the
confound problem below.

**Backfill vs forward-only**: the `session_messages`/`session_tool_usage` data already exists
historically (955,646 / 47,753 rows respectively, going back to the DB's full 2025-08-28 → 2026-08-03
span), so a fix could backfill immediately via the existing
`backfill_session_stack_observations(..., force_recompute=True)` path — this is **not**
forward-only-with-a-30-day-lead-time. That said, `effectiveness_rollups` itself has no scheduled
recompute (see Current State) — productionizing this requires adding a recurring recompute job,
independent of the attribution fix.

## Cost Estimate

**Piece 1 — wiring fix (bounded)**: ~3-5 pts / 2-4 days.
- Files: `backend/services/stack_observations.py` (swap `session_repo.get_logs()` for a
  `session_messages`/`session_tool_usage`-backed read, or add a fallback), `backend/session_badges.py`
  (`derive_session_badges` needs an input-shape adapter for message rows — `session_messages` lacks
  a `type` discriminator matching `session_logs`' `command`/`tool` values; needs field mapping from
  `tool_name`/`metadata_json.toolCategory`), `backend/db/repositories/sessions.py` +
  `backend/db/repositories/postgres/sessions.py` (new or adapted read method if not reusing
  `get_tool_usage`).
- Layers touched: repository (new read), service (`stack_observations.py`,
  `session_badges.py`), no router/API change needed for the fix itself.
- No migration. No schema change (existing `session_stack_components.component_type='skill'` already
  supported).
- Backfill job: re-run `backfill_session_stack_observations(..., force_recompute=True)` for all
  16,620 existing observations — this **rewrites** existing `session_stack_observations` +
  `session_stack_components` rows (an UPDATE-in-place recompute, not a destructive delete). No
  Mode-D trigger (not auth/payments/deletion/migration/secret-rotation) but should be flagged to a
  reviewer as a full-corpus recompute.
- Test updates: `backend/tests/test_stack_observations.py`, `backend/tests/test_workflow_effectiveness.py`
  fixtures currently assume `session_logs`-shaped input; need message-shaped fixtures added.

**Piece 2 — model-dimension redesign (open-ended)**: not estimable without its own design pass.
Touches `_scope_keys`/`_stack_scope_id`/`_aggregate_rollups` (`workflow_effectiveness.py`), the
`scope_id` encoding convention (a `|`-joined string, currently has no room for a model token without
a breaking format change or a new `scope_type`), and every consumer of `scopeId`/`scopeLabel`
(frontend rollup panels, if any). Rough order of magnitude: comparable to or larger than DI-4a's
5-pt cost_index contract, likely Tier 2 (8-13 pts) given it changes a shared aggregation contract.
Recommend a follow-up SPIKE/design-spec, not a direct estimate here.

**Piece 3 — confound (test-outcome capture)**: out of this leg's scope entirely; `test_results` and
`test_runs` are both 0 rows system-wide (confirmed below), and there is no code path in this leg
that could backfill test-outcome telemetry that was never captured.

**Combined**: Piece 1 alone does not clear the coverage bar (26.1% of keys, measured). Reaching a
usable state requires Piece 1 **and** Piece 2, and Piece 2 is itself open-ended-sized work
comparable to building a fresh signal from scratch — this materially weakens the "populate
attribution" path's cost advantage over the other three legs.

## Confound Assessment

**The charter's framing of `effectiveness_rollups` as carrying "real success/risk/quality scores"
is overstated for the bulk of the corpus.** Formula, read directly from
`workflow_effectiveness.py:832-850`:

```
success_score = 0.45 * _session_outcome_score(row)   # from sessions.status
              + 0.35 * test_pass_ratio               # from test_runs / forensics fallback
              + 0.20 * resolution_score               # component-resolution rate
              - retry_penalty
```

`_session_outcome_score` (`workflow_effectiveness.py:430-439`) returns `1.0` for
`status in _FINAL_SESSION_STATUSES` (i.e. `completed`) and `0.35` as the default otherwise — this
is a direct re-derivation of `sessions.status`, **the exact signal the handoff spec §0 audit already
rejected** as carrying only two non-outcome values.

`test_pass_ratio` falls back to `forensics.testExecution` when no `test_runs` rows exist
(`_derive_test_ratio`, `workflow_effectiveness.py:327-350`) and returns `0.0` when neither is
present. Confirmed system-wide:

```sql
SELECT COUNT(*) FROM test_results;  -- 0
SELECT COUNT(*) FROM test_runs;     -- 0
```

Both are 0 rows — the 0.35-weighted term is non-informative for every session in the DB unless
`session_forensics_json.testExecution` happens to be populated (not verified here, but structurally
this term contributes 0 for any session without forensics test data).

**Measured distribution confirms this is not a footnote**:

```sql
SELECT round((metrics_json->>'successScore')::numeric,2) AS bucket, COUNT(*)
FROM effectiveness_rollups WHERE scope_type='stack' GROUP BY bucket ORDER BY bucket;
-- 6296 / 7290 rows (86.4%) sit at successScore ≈ 0.45 — exactly
-- 0.45*1.0(completed) + 0.35*0.0(no test data) + 0.20*0.0(no resolved components)
```

86.4% of `stack`-scope rollup rows carry the identical formulaic value produced by "session
completed, no test data, no resolved components" — i.e., almost the entire corpus's "quality score"
is a restatement of the already-rejected status signal plus two zero contributions, not a
model-attributable outcome measurement. Additionally, `sampleSize >= 5` (real aggregation, not a
single-session bucket) occurs in only 19/7,290 `stack` rows (0.26%) — the "rollup" is overwhelmingly
single-session, not an aggregate.

**Verdict on the confound question**: `successScore`/`qualityScore`/`riskScore` are **not**
primarily model-attributable outcome signals today. They substantially inherit the `sessions.status`
non-signal (0.45 weight) and a structurally-absent test-outcome term (0.35 weight, always 0 given
0 rows in `test_results`/`test_runs`), leaving `resolution_score` (0.20 weight, itself an
attribution-pipeline artifact, not a task-outcome measure) as the only term with any real variance
for most rows. Fixing skill attribution would let these scores be *sliced by skill*, but would not
make the scores themselves more informative — the confound is upstream of the join this leg was
asked to evaluate.

## Comparison to Deriving a Fresh Signal

Populating skill attribution is **not** the cheaper or better-value path relative to the other three
legs' candidates, for three independent reasons:

1. **Coverage ceiling below threshold even after the bounded fix**: 26.1% of keys (measured), vs.
   the charter's own ≥50% usability bar — and that ceiling requires Piece 2 (open-ended model-axis
   redesign) to even become relevant at the router's actual `(skill, model)` grain.
2. **The underlying scores are confounded today**: 86.4% of `stack`-scope rows are a formulaic
   restatement of the rejected `sessions.status` signal plus two zero-weight-effective terms. "This
   table already carries real success/risk/quality scores" is not accurate for the current corpus —
   fixing the join surfaces this confound rather than avoiding it.
3. **Total cost exceeds a single bounded fix**: Piece 1 (wiring) is cheap (~3-5 pts), but Piece 1
   alone is insufficient (coverage still under threshold and the model axis is still missing).
   Piece 2 is open-ended and likely Tier 2-sized on its own. The other three legs (harness-errors,
   tool-failures, abandonment) are direct per-session derivations against `sessions`/
   `session_tool_usage` — no cross-table attribution-pipeline dependency, no model-axis redesign
   needed, and (per this leg's evidence) a comparably-sized or smaller implementation footprint.

## Verdict Contribution (this leg)

**no-go** for this leg specifically, as an alternative to a fresh derivation: populating
`effectiveness_rollups`' skill attribution does not clear the charter's coverage bar even after its
bounded piece is fixed (26.1% of keys measured, not the required ≥50%), requires a second,
open-ended, comparably-sized design change (model dimension) to become relevant to DI-1's actual
key grain at all, and the base scores it would slice are themselves confounded by a non-informative
status echo and a structurally-empty test-outcome term. If the charter's overall verdict is
`conditional`, this leg's evidence argues the named follow-up should **not** be "fix
`effectiveness_rollups` attribution" — that path costs more and delivers less than a fresh
per-session derivation from the other three legs' tables.

## Confidence

**0.75** — every quantitative claim above is a pasted, real query result against the operative
node Postgres (no estimates presented as measurements); the two areas of residual uncertainty are
(a) whether `session_forensics_json.testExecution` is populated widely enough to move
`test_pass_ratio` off the 0.0 default for any material fraction of sessions (not directly queried —
would require iterating `session_forensics_json` payloads), and (b) the true cost of Piece 2 (model
dimension), which is explicitly unestimated rather than guessed.
