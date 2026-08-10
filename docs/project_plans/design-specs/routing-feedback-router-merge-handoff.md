---
title: "Design Spec: Routing Feedback Router Merge Handoff (DI-1)"
doc_type: design-spec
maturity: shaping
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
status: draft
created: 2026-07-31
updated: 2026-08-03
audience: developers
category: cross-repo-integration
tags:
  - routing-feedback
  - delegation-router
  - cross-repo-handoff
  - empirical-routing
  - deferred-item
related_documents:
  - docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
description: |
  Deferred item DI-1: Router-side empirical merge algorithm and live consumption gate.
  Specifies the cross-repo handoff seam between CCDash's routing-feedback producer
  surface and MeatySkills/delegation-router's live consumer-side merge and adjustment
  math. This item is deferred because the router-side work is owned by MeatySkills and
  currently blocked by `live_consumption_disabled`. Documents the contract bridge,
  numeric merge algorithm candidates, and promotion readiness criteria.
schema_version: 2
---

# Design Spec: Routing Feedback Router Merge Handoff (DI-1)

## 0. Blocking Precondition — the v1 Envelope Carries No Outcome Signal

> **Added 2026-08-01.** Read this before scheduling any router-side work. It changes what DI-1's
> next actionable step *is*.

The merge algorithm in §2 consumes `success_rate`, `cost_index`, and `regression_rate`. In the
shipped v1 producer, **all three are null-or-constant for every row, by deliberate design**
(`backend/application/services/agent_queries/routing_rollup.py`):

| Field | v1 emitted value | Why (producer's own rationale) |
|-------|------------------|--------------------------------|
| `success_rate` | ~~`None`, always~~ — **DI-4e real for Claude-family keys; HALTED (forced `null`) for gpt/codex-family keys via a mechanical gate, 2026-08-10 (see §0a below).** Compute logic (per-key tool-error-rate complement, `null` on zero attribution) is correct for every provider; a separate, config-driven stale-provider gate (`CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS`) unconditionally withholds `success_rate` for the gpt/codex family until a backfill precondition clears and D-b4 re-verifies clean — enforced at both compute time and read time, so REST/MCP/CLI never serve a stale-family value. | Was: `sessions.status` carries only `active`/`completed` — not a success/failure signal. Fabricating one "would be actively misleading to a consuming router." |
| `regression_rate` | `None`, always — **still true, permanently.** CLOSED per DI-4b (2026-08-03): no `test_results`/`test_runs` signal exists anywhere in this schema. Not revisited by DI-4e. | No genuine regression signal available to that module, and none is being built. |
| `cost_index` | ~~`1.0`, fixed (`_COST_INDEX_BASELINE`)~~ — **SUPERSEDED 2026-08-03: now real.** DI-4a shipped; the node serves 261/346 rows non-null across 249 distinct values. | Was: per-key cost normalization is "a real design surface of its own," deliberately not gold-plated into a provisional payload. |
| `sample_count` | real | — |
| `confidence` | real — `n/(n+5)` | — |
| `eligible_for_adjustment` | real | — |

Running the ratified algorithm (§2.2) against those actual values, for every row:

```
penalty_for_failure    = 0.0        # success_rate None → neutral
penalty_for_cost       = max(1.0 - 1.0, 0.0) = 0.0
penalty_for_regression = 0.0        # regression_rate None → neutral
combined_signal        = 0.0
score_delta            = max(-0.0, -0.15) = 0.0   → NEUTRAL
```

**Every row, every model, every window resolves to NEUTRAL.** A router merge built against v1
would be a correct, well-tested, permanently inert no-op machine. Enabling
`live_consumption` would not make the feedback loop live; it would make it *silently* dead —
strictly worse than the current honest `live_consumption_disabled`.

**Consequence for sequencing.** DI-1 (router merge) is **not** the next actionable item. The
blocking work is a CCDash producer increment that emits a real outcome signal — tracked as **DI-4**
(see §5.4).

### 0a. Update 2026-08-10 — DI-4e implemented but HALTED at ship gate: `success_rate` code is real, live window still stale

DI-4d (Codex tool-error detection fix, main `b51de27`) and DI-4f (skill-attribution NO-GO, closed
2026-08-03 — see `docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-feasibility-brief.md`)
together cleared the two preconditions §0's "named precondition" paragraph and the tool-failures
audit below both named. DI-4e (feature contract
`docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md`) then shipped a
real per-`(project_id, source_skill_name, model)` `success_rate`:

- **`success_rate = 1 - (sum(tool_errors) / sum(tool_calls))`**, call-volume-weighted across every
  tool-usage-attributed session in the key (D-b1) — never a mean of per-session rates.
- `null` (never a fabricated constant) for a key with zero tool-usage-attributed sessions (D-b2).
- A per-key coverage companion (`success_rate_coverage_fraction`, mirrors `cost_coverage_fraction`'s
  shape) — **compute-layer/response-DTO only, not persisted** (no new column/migration), so it reads
  back `null` on every persisted-table transport (REST/MCP/CLI) today.
- **AC3 — skill-dimension coverage is now an explicit contract state.** The response envelope
  carries two additive counters, `skill_attributed_key_count`/`skill_unattributed_key_count`, scoped
  to the same `min_sample_size`-clearing population the skill-attribution feasibility brief's
  **~40-45% coverage figure** describes (non-empty `source_skill_name` vs. the `(project × model)`
  cohort wearing a three-part key's clothes). A router-side (or any) consumer can now tell which
  bucket a key falls into without inspecting `source_skill_name` per row — count/fraction only, no
  per-consumer discounting logic (D-b3).
- **Retry/recovery blindness is a documented, un-fixed limitation (D-b5):** raw error-rate cannot
  distinguish "failed then recovered" from "failed and stayed broken" — 95.2% of tool-failure
  sessions still reach `completed` (per the DI-4d re-measurement). Not modeled here; the schema has
  no retry linkage.
- `regression_rate` stays permanently `null` — DI-4b closure, unaffected, not revisited.
- **`live_consumption_disabled` is untouched** (DI-1, router owner's call). Re-running §0's
  "Running the ratified algorithm" arithmetic with a real `success_rate` now yields a genuinely
  non-neutral `penalty_for_failure` for keys with tool-usage attribution — but that arithmetic still
  never executes against live traffic while the flag stays disabled.

**D-b4 live-verification result: HALT (confirmed 2026-08-10 against the live node Postgres).** The
DI-4d re-measurement (`docs/project_plans/exploration/routing-feedback-success-signal/spikes/tool-failures/di-4d-remeasurement.md`
§7) found that *historical* `session_tool_usage` rows for Codex sessions written before `b51de27`
still record 100% success (the old parser's artifact) — a fix does not retroactively correct stored
counts. Fix cycle 1 of DI-4e's implementation sprint re-ran the D-b4 family-split verification query
against the operative Postgres (`10.42.10.76:5440`) over the current 30-day window and found the
gpt/codex-family still measurably skewed: **21.4% of keys informative, 0.04% error rate** — far
closer to the pre-fix baseline (0.0% informative, 0.00% error rate) than to the fixed-parser
re-parse's demonstrated 89.2% informative / 1.48% error rate. **No backfill/resync of historical
Codex `session_tool_usage` rows has run**, so the code-fix-vs-stored-data gap `di-4d-remeasurement.md`
§0/§7 warned about is still live today. Per the contract's own D-b4 ratification and
`escalation_recommendation`, **DI-4e does not ship as-is**: a short Tier 1 backfill/resync follow-up
(re-parse pre-`b51de27` Codex JSONL through the fixed parser and overwrite the stale
`session_tool_usage` rows) is the precondition, after which this same D-b4 query should be re-run to
confirm the window has cleared before treating any Codex-family `success_rate` value as trustworthy.

**Update 2026-08-10 (fix cycle 2) — the HALT is now a mechanical gate, and the finding was
independently re-confirmed.** Fix cycle 1 recorded the HALT determination but left
`success_rate` computation unconditional in code — nothing actually withheld a gpt/codex-family
value from being served. This is now closed:
`config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS` (default `("openai",)`) forces
`success_rate`/`success_rate_coverage_fraction` to `null`/`0.0` for any matching provider, enforced
BOTH at compute time (`routing_rollup.py::_success_rate_and_coverage`, so no future worker sweep
persists a stale-family value) AND at read time
(`_client_v1_routing_rollup.py::_row_to_key_dto`, so an already-persisted row is never served with
one either) — independent of `CCDASH_ROUTING_FEEDBACK_ENABLED`/`live_consumption_disabled`. This
flag is the only sanctioned way to lift the gate, and only once the backfill/resync precondition
below has run and this same D-b4 query has been re-run and shown clean. Additionally, fix cycle 2
independently re-ran the D-b4 query (not merely re-reading fix cycle 1's self-reported figures)
against the same live node Postgres and reproduced the finding: **21.4% of gpt/codex-family keys
informative, 0.04% error rate** — unchanged from fix cycle 1's measurement, confirming the window
is still stale.

DI-4 does **not** decompose evenly. A signal-source audit against the node Postgres
(2026-08-01, 18,762 sessions) found the three fields have completely different feasibility:

| Field | Feasibility | Evidence |
|-------|-------------|----------|
| `cost_index` | **SHIPPED (DI-4a, 2026-08-02)** | `sessions.total_cost` / `display_cost_usd` > 0 on **13,460 of 18,762** rows (72%). Aggregates directly at the `(source_skill_name × model)` grain — no external join, no new table. |
| `success_rate` | **Conditional — one candidate, gated on a parser fix** (DI-4b exploration closed 2026-08-03) | see audit below, then the DI-4b outcome box |
| `regression_rate` | **No signal exists — confirmed by all four DI-4b legs** | see audit below, then the DI-4b outcome box |

**Signal-source audit — every candidate ruled out:**

- `sessions.status` — 2 distinct values only (`completed` 18,229 / `active` 533). Confirms the v1
  code comment; not an outcome signal.
- `test_results` — **0 rows**. No test-outcome signal exists at all.
- `effectiveness_rollups` — 14,561 rows, and it does carry `successScore` / `riskScore` /
  `qualityScore`. **But it has no skill dimension whatsoever**: all 7,290 `stack`-scope rows have
  `scopeLabel` matching `skills:none`, and the other 7,271 rows are `agent`-scope (opaque agent
  hashes). There is nothing to join `source_skill_name` against. This is not a hard grain
  reconciliation — it is an impossible one, until skill attribution is actually populated.
  (`attributionCoverage: 0.0` in sampled rows is consistent with attribution never being wired.)
  **Correction 2026-08-03 (DI-4b `existing-rollups` leg):** the *cause* stated here and elsewhere —
  component extraction emitting hashes/prompt-text — is **wrong**. Clean skill slugs do exist
  (`toolLabel: "dev-execution"`, `"planning"`) in `session_messages`; `stack_observations.py` reads
  exclusively from `session_logs`, which is **0 rows** on the operative Postgres because the
  enterprise sync profile deliberately stopped writing it
  (`sync_engine.py:_should_write_legacy_session_logs`). That part is a bounded wiring bug (~3-5 pts).
  **But this table is now closed as a signal source on two further grounds:** (a) its scope key has
  **no `model` dimension at all**, so fixing attribution cannot serve a `(skill x model)` key without
  a separate open-ended redesign; (b) 86.4% of stack-scope rows sit at an identical formulaic
  `successScore ~= 0.45` driven by `sessions.status` -- the signal this very audit rejected -- plus a
  `test_pass_ratio` term that is always 0 because `test_results`/`test_runs` are empty. It is largely
  a re-encoding of the rejected signal, not a latent outcome signal awaiting a join.
- `session_stack_observations` — 16,559 rows, all `observation_source: backfill`, with
  `skillsUsed: []` and `agentsUsed: []` empty in samples; payload is queue-pressure and
  artifact-count telemetry, carrying no outcome semantics.

> An earlier revision of this section named `effectiveness_rollups` as DI-4's signal source and
> called the work "grain reconciliation." That was **wrong** and is corrected above — the table has
> no populated skill dimension, so no join is possible. Recorded rather than silently edited,
> because the mistaken version was committed and may have been read.

~~**A promising lead for the success signal**~~ — **REFUTED 2026-08-03. This lead was
mis-specified, and the exploration built on it found it to be a false trail.** Recorded rather than
silently edited, per the same precedent this section set above.

The claim was: `<synthetic>` harness entries are per-session failure events, "325 occurrences across
249 transcripts," making harness-error counts a candidate `regression_rate` and its complement a
candidate `success_rate`. Measured against the node Postgres:

| Query | Result |
|-------|--------|
| `session_messages.content LIKE '%<synthetic>%'` | **11 rows / 5 sessions** |
| `sessions.model = '<synthetic>'` | **244 sessions** |
| `content LIKE '%API Error%'` | 545 rows / 436 sessions |
| `content LIKE '%Request interrupted%'` | 427 rows / 399 sessions |

The audit conflated *sessions whose model never resolved* (`model = '<synthetic>'`, 244 — the origin
of the "249 transcripts" figure) with *harness error entries*. The literal string is near-absent
from transcript content, and mostly meta-discussion where it appears. Real harness errors live as
free text (`API Error:`, `Agent "..." failed:`, `[Request interrupted...]`) in
`session_messages.content`.

Worse, `model = '<synthetic>'` is **self-referential as an outcome signal**: the model is unresolved
*because the request failed first*. 5 of the 188 min-sample-clearing keys carry it, one driving an
82% "error rate" that is pure circularity. The designated lead was, in part, an artifact of the
failure it was meant to measure.

### DI-4b outcome — exploration closed 2026-08-03, verdict CONDITIONAL

Full record: `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md`

Denominator: **188** keys clear `min_sample`=5 (of 396 in-window keys). Note the real producer key
is `(project_id, skill_name, model)` — `project_id` is part of it, which the
`(source_skill_name × model)` shorthand used throughout this spec omits.

| Leg | Informative keys / 188 | Confound | Verdict |
|-----|------------------------|----------|---------|
| `tool-failures` | **140 (74.5%)** | Categorical parser gap — *mitigable* | **conditional** |
| `harness-errors` | 70 (37.2%) | Unmitigable | no-go |
| `abandonment` | 60 (31.9%) | Unmitigable (parse-time freeze artifact) | no-go |
| `existing-rollups` | 49 (26.1%) if fixed | Scores circular on `sessions.status` | no-go |

Only `tool-failures` clears the >=50% threshold, so the deal-killer did **not** trigger. It cannot
ship as-is: **0 of 37 GPT/Codex keys are informative** (190,450 all-time tool calls, exactly 0
errors) against **137 of 138** Claude keys, because the Codex error-detection heuristic never
matches real payloads. With `weight_failure` at 0.5 — the largest term in §2.3 — shipping this would
systematically bias routing *toward* GPT/Codex models on a parser artifact. An inert loop misroutes
nothing; a categorically biased one misroutes confidently.

**Named precondition before any `success_rate` producer work:** fix Codex tool-error detection,
re-measure the family split against the same 188-key denominator, then scope the increment. Do not
ship a Claude-family-only signal into a cross-family router key.

**`regression_rate` is closed, not deferred.** No leg found a regression signal;
`test_results`/`test_runs` are 0 rows and the schema has no retry linkage (95.2% of sessions with a
recorded tool failure still completed, so "failed then recovered" is indistinguishable from "failed
and stayed broken"). Populating it is a new-capture question, not a derivation question.

**Blocking discovery, out of the charter's scope but conditioning all of it:** **61% of
min-sample-clearing keys (114/188) have a NULL `skill_name`**, which the producer coalesces to `""`.
Even given a perfect success signal, most keys the router acts on carry no skill identity and
degenerate to `(project × model)`. Tracked as its own exploration:
`docs/project_plans/exploration/routing-key-skill-attribution/`.

**Consequent routing** — DI-4 is two artifacts, not one plan. Both authored 2026-08-01:

1. **DI-4a `cost_index` → Tier 1 Feature Contract** (5 pts, buildable today):
   `docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md`
2. **DI-4b `success_rate` / `regression_rate` → exploration charter first** (3-day timebox):
   `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md`
   Whether *any* derivable success signal exists is an open feasibility question, not an
   implementation task. Planning an implementation before that question is answered would repeat
   the mistake this section documents.
   **Status 2026-08-10: implemented but HALTED at the ship gate for `success_rate` (DI-4e, see
   §0a — live D-b4 verification found the current window still stale-skewed for Codex/GPT;
   backfill precondition required before ship); `regression_rate` stays closed permanently.**

Do not schedule DI-1 before DI-4 lands. A partial DI-4 that ships only `cost_index` **does** make
the loop non-inert (a genuinely expensive model can then be downweighted on cost alone), but leaves
the failure half of the merge weightless — `weight_failure` is 0.5, the single largest term.

---

## Deferral Rationale

**Status**: `live_consumption_disabled` — The delegation-router's routing-adjustment logic
(**live merge**, bounded-adjustment cap, effective-score floor, minimum-sample re-gating, decay
blending) is owned by MeatySkills/`ibm-main`. As of Phase 6, this work is unscheduled and gated on
explicit promotion decision from the router owner.

**CCDash's Scope (Shipped)**: Evidence-only producer surface. All metrics, sample counts, window
boundaries, eligibility signals, and deterministic rollup are delivered and tested in Phases 1–6.

**Router's Scope (Deferred)**: Consumption, numeric merge, routing-decision actuation, and
RoutingRecord provenance. No changes to CCDash are required for this work to proceed.

**Trigger for Promotion**: Router owner flips `live_consumption_disabled` → enabled and signals
readiness to negotiate merge algorithm against the CCDash envelope shape (§2).

---

## 1. Consumer Contract Mirror (Reference)

The canonical hand-off contract is published at:

- **PULL Surface**: `GET /api/v1/routing/rollup?project_id={project_id}`
- **DTO Schema**: `RoutingRollupDTO` + `RoutingFeedbackKeyDTO` (in CCDash `backend/models.py`)
- **Capability**: `"routing:feedback"` advertised via `GET /api/v1/capabilities`
- **Transport**: REST, MCP tool `ccdash_routing_rollup`, CLI `ccdash routing rollup`
- **Vendor Sync**: Pinned mapping file (`routing_task_map_v1.json`), digest-locked by CI (AC-2)

See `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md` (§1–2) for
full access patterns and envelope structure.

---

## 2. Merge Algorithm Candidate: Bounded-Adjustment Model

This section documents the **proposed** merge algorithm for router-side consumption. It is NOT
implemented in CCDash Phase 1–6 and is provided for planning purposes only.

> **Corrected 2026-08-01 (two defects in the original candidate).** The pseudocode below is the
> ratified form; both fixes are load-bearing.
>
> 1. **Sign inversion.** The original computed `recommended_score_delta = max(combined_signal, cap)`.
>    Because every `penalty_*` term is *positive* for a bad model, `combined_signal` is positive for
>    a bad model, so the downweight trigger (`delta < -0.01`) could never fire. As written, a failing
>    model was **never** downweighted — the only rows that ever adjusted were cheap *successful*
>    ones, via the then-unclamped negative cost term. Fixed by negating: `max(-combined_signal, cap)`.
> 2. **Cost bonus removed.** `penalty_for_cost` is now clamped at `0.0`, so a cheaper-than-baseline
>    model can no longer offset its own failure rate. The surface is strictly a downweight signal,
>    which is what "bounded-adjustment" is meant to mean.
>
> The original §2.3 numeric defaults (`confidence_threshold 0.7`, `max_adjustment_cap −0.15`,
> weights `0.5 / 0.3 / 0.2`) are **ratified unchanged** — the defects were in the sign convention
> and the cost clamp, not the parameter values. Verified against the extreme case
> (`success_rate 0.20`, `cost_index 2.0`, `regression_rate 0.50`): `combined_signal = 0.750`,
> `score_delta = −0.150` — the cap binds correctly.
>
> The Appendix example's `score_delta: -0.10` was hand-written and does not reproduce under either
> the original or the corrected algorithm; it has been regenerated (see Appendix).

### 2.1 Metric Inputs (from CCDash)

**Per `(source_skill_name × model)` key:**

```typescript
// From RoutingFeedbackKeyDTO (CCDash envelope)
input {
  source_skill_name: string;          // raw skill_name from session telemetry
  task_class: string;                 // derived via pinned mapping
  model: string;                      // e.g., "claude-sonnet-5"
  provider: string;                   // derived via derive_model_identity()
  sample_count: number;               // sessions in window
  success_rate: number;               // [0.0, 1.0]
  cost_index: number;                 // relative cost vs baseline
  regression_rate: number;            // [0.0, 1.0]
  confidence: number;                 // [0.0, 1.0]
  eligible_for_adjustment: boolean;   // true iff sample >= min_sample AND not protected
  window_start: string;               // ISO 8601
  window_end: string;                 // ISO 8601
}
```

### 2.2 Router's Merge Math (Candidate)

**Candidate Algorithm** (pseudocode, subject to negotiation):

```
for each RoutingFeedbackKeyDTO row from CCDash:

  1. Check eligibility:
     - if !eligible_for_adjustment: SKIP (protected class or sub-threshold sample)
     - if confidence < 0.7: SKIP (low confidence; CCDash recommendation)
     - continue

  2. Derive adjustment signals:
     - penalty_for_failure = 1.0 - success_rate              // range [0.0, 1.0]
     - penalty_for_cost = max(cost_index - 1.0, 0.0)        // clamped: cheapness earns no bonus
     - penalty_for_regression = regression_rate * 0.5       // regression carries half weight
     - combined_signal = (penalty_for_failure * 0.5) +
                        (penalty_for_cost * 0.3) +
                        (penalty_for_regression * 0.2)      // weights: sum = 1.0
                                                            // combined_signal >= 0 always;
                                                            // larger = worse

  3. Apply bounded adjustment:
     - max_adjustment_cap = -0.15                           // never downweight >15%
     - recommended_score_delta = max(-combined_signal, max_adjustment_cap)   // NOTE the negation
     - if recommended_score_delta < -0.01: RECOMMEND DOWNWEIGHT by delta
     - else: NEUTRAL (no adjustment signal from this row)

  4. Construct RoutingRecord:
     - routing_record = {
         source_feedback_id: row.id,              // trace back to CCDash
         source_feedback_window: row.window_start,
         task_class: row.task_class,
         model: row.model,
         provider: row.provider,
         score_delta: recommended_score_delta,
         evidence: {
           success_rate: row.success_rate,
           cost_index: row.cost_index,
           regression_rate: row.regression_rate,
           sample_count: row.sample_count,
           confidence: row.confidence
         },
         timestamp: now(),
         source: "ccdash-routing-feedback-v1.0.0"
       }
     - emit RoutingRecord to MeatySkills dispatch queue
```

### 2.3 Numeric Defaults (Candidate)

These values are **illustrative** and subject to empirical validation (see Promotion Readiness, §3):

| Parameter | Candidate Default | Rationale | Tuning Signal |
|-----------|-------------------|-----------|---------------|
| `confidence_threshold` | 0.7 | CCDash confidence < 0.7 suggests sample/window too sparse | Increase to 0.8 if false positives; decrease to 0.6 if missing real adjustments |
| `max_adjustment_cap` | -0.15 (−15%) | Conservative; never downweight more than 15% on a single signal | Increase cap (e.g., −0.25) if router wants more aggressive adjustments; decrease cap if too many changes churn routes |
| `weight_failure` | 0.5 | Success rate is the primary signal | Reduce if cost/regression overwhelm the data |
| `weight_cost` | 0.3 | Cost matters but secondary to correctness | Tune based on operational cost constraints |
| `weight_regression` | 0.2 | Regression is early-warning signal, half-weight | Increase to 0.3 if model drift is critical |
| `regression_half_weight` | 0.5 | Regression penalizes less than explicit failures | Experiment with 0.7–1.0 if regression predictive power improves |

---

### 2.4 ADR — Landing Surface for the Empirical Adjustment (RATIFIED 2026-08-03)

> **Read this together with §2.2 and §2.3.** This addendum amends both. §2.2's *aggregation* math
> survives intact; §2.3's `max_adjustment_cap` does **not** survive as a magnitude. Anyone
> implementing DI-1 from §2.2/§2.3 alone will build an adjustment with nowhere to apply.

**Status**: Ratified (self-ratified — router owner == producer owner, same operator).
**Decision date**: 2026-08-03.
**Supersedes**: §2.3 `max_adjustment_cap` semantics; §2.2 step 3–4 actuation shape.
**Prerequisite closed**: DI-1 PREREQ (`node_01KZ484RDK3Y1AXQ59EAVY16QV`).

#### 2.4.1 Problem

§2.2 emits a **bounded continuous** `score_delta` (cap −0.15) and SPEC.md invariant 10 assigns the
router a *"bounded-adjustment cap and **effective-score floor**"*. Neither exists. The resolver does
not rank by any score — it selects by **chain position** and **integer within-model priority**.
Implementing §2.2 verbatim would compute a correct number with nowhere to put it.

#### 2.4.2 Verification (independent, source-read 2026-08-03 — not taken on report)

Against `~/.claude/skills/delegation-router/{resolver.js,SPEC.md,SKILL.md}` and
`~/.claude/config/model-registry.yaml`:

1. **The production path has no score.** `resolve()` (`resolver.js:651`) dispatches to
   `resolveFromToml` **only when `input._configPath` is set**, which the JSDoc marks
   `INTERNAL: legacy provider-plugins.toml path (tests)`. Production always takes
   `resolveFromRegistry` (`:684`). Its selection order is: MUST-stay → determinism filter →
   explicit-provider (`byModelThenPriority`) → `routing_policy` chain walk (first resolvable entry
   wins, **position-based**) → cost/priority ranking → claude fallback. Every comparator is
   discrete/lexicographic: `free` bool, `COST_TIER_RANK` int (`:480`), `priority` int (`:799`).
2. **The one continuous score is test-only and unusable anyway.** `candidateScore` (`:1022`) sits
   under the header *"Legacy TOML resolution (preserves existing 33-test fixture behavior)"* and is
   reached only via `resolveFromToml`. It is also quantized — `COST_TIER_RANK` (0–3) plus a 0/0.5
   determinism bonus, with −10 / +0.1 offsets — so a −0.15 delta could not flip anything except a
   0.1-spaced fallback tie. **A continuous landing surface does not exist in either path.**
3. **`scores:` is not wired.** Zero reads of `.scores` in `resolver.js`. SKILL.md:140–144 states the
   resolver does not order by it: *"advisory metadata … **not** a resolver input in v3 (reserved for
   a future upgrade)."*
4. **The spec's own invariant is unsatisfiable as written.** SPEC.md:222 requires an
   "effective-score floor" over a score the resolver does not compute. Confirmed contradiction, not
   a misreading.
5. **`priority_overrides` is provably inert for every feedback-eligible class.** `resolveChainEntry`
   (`:601–618`) never reads `priority`; the chain walk (stage 2) short-circuits before the priority
   ranking (stage 3, guarded `if (!chosen)`). The registry declares **12 `routing_policy` chains, 10
   of them non-MUST-stay** (`orchestration`, `mode_d` are MUST-stay and immune) — i.e. *all* eligible
   classes are chain-routed, so all of them bypass `priority` entirely. `priority` is additionally
   documented as a **within-model** rank that "must never be compared across different models"
   (`:740–749`).

**Verdict: the finding is CONFIRMED and strengthened** — option (B) as originally stated
("emit `priority_overrides`") would have been a **no-op** for 10 of 10 eligible classes.

#### 2.4.3 BL-1 determination — distinct, not a prerequisite

SPEC.md BL-1 ("Registry-aware scoring fully wired", *status: planned (design W2)*) scopes
`enabled` · `priority` · availability · capability-match from the registry — **registry-field
honoring, not a continuous score.** Two reasons it is not this work:

- **It is already delivered.** SKILL.md:127–129 instructs readers *not* to say the resolver scores on
  `cost_tier + sampling`, because *"v3 **is** registry-aware (`enabled`, priority, availability,
  capability match)"* — BL-1's exact scope. `resolveFromRegistry` confirms it. **BL-1's `planned`
  status is stale**; a follow-up should mark it complete.
- **Even fully re-opened it would not produce an effective score.** SKILL.md:140–141 keeps the two
  strictly separate: v3 ranking is *"chain / priority / availability / capability-match"* **and** the
  `scores:` block is *"not a resolver input."*

→ **DI-1 is NOT sequenced behind BL-1.** This node is not duplicate scope, and closing it by
reference to BL-1 would have left the gap open.

#### 2.4.4 Options considered

| | Option | Rejected because |
|---|---|---|
| **A** | **Resolver v4 — score-aware ranking.** Wire `scores:` into ranking, apply the delta to the effective score. | Blast radius covers **every** route, not just feedback-touched ones, so it needs its own regression posture before any feedback value is realized. Worse, it is the wrong *shape*: `scores:` is **per-model**, while selection is over **(model, provider) lanes** — it cannot express "this model on ICA vs subscription", which is most of what routing decides. And a `routing_policy` chain is an operator's **statement of intent** ("free first, then this"); collapsing it into a scalar is a real semantic loss. Scale mismatch is fatal on its own: −0.15 against 1–10 registry scores is 1.5% and would never flip anything. |
| **B** | **Emit `priority_overrides` / `routing_policy_overrides`.** | `priority_overrides` is a **no-op for all 10 eligible classes** (§2.4.2 finding 5). And both levers live in `routing.local.toml` — the **human-authored** project-local override file. Writing machine feedback into the human channel makes SPEC.md invariant 10's *"absolute human-override precedence"* unenforceable: two writers, one field, no discriminator. |
| **C** | ✅ **Separate demotion-only feedback channel, actuated on the chain.** | **CHOSEN.** |

#### 2.4.5 Decision — Option (C)

Keep §2.2's scalar as an **evidence aggregate that triggers a bounded discrete demotion**. Do not
invent a resolver-wide score; do not write into the human override channel.

1. **Channel.** A dedicated machine-written state file (e.g.
   `~/.claude/state/routing-feedback-overrides.json`), **never** `routing.local.toml`. Precedence
   becomes structural, not conventional:
   `MUST-stay (absolute) > routing.local.toml (human) > routing-feedback state (machine) > registry defaults`.
2. **Actuation point.** One new stage between the current stage 2 and stage 3: reorder the
   `routing_policy` chain array for that `task_class` **before** the position-based walk. This is a
   pure `(chain, feedbackForClass) → chain'` function — the three-stage structure is unchanged. For
   any class with no chain, the same record nudges stage-3 `priority` instead (secondary path).
3. **Demotion-only, one step.** An adjustment may move a chain entry **at most one position later**
   and may **never promote**. Feedback can only say "prefer this less", never "prefer this more".
4. **Provenance.** RoutingRecord carries `rank_displacement` (the applied action) *and*
   `combined_signal` + the §2.2 evidence block (why), so `skillmeat routing audit --violations`
   remains meaningful.

#### 2.4.6 Re-ratified guardrail semantics (discrete world)

SPEC.md invariant 10's vocabulary is re-expressed. **A magnitude cap is meaningless when there is
exactly one available action; boundedness must come from displacement limits and hysteresis.**

| Continuous invariant (retired) | Discrete re-ratification | Value |
|---|---|---|
| bounded-adjustment **cap** (−0.15 magnitude) | **max rank displacement**, demotion-only | `1` position; promotion forbidden |
| **effective-score floor** | **never-empty / last-candidate floor** — a demotion may never empty a chain, displace the sole remaining candidate, or touch a MUST-stay class | structural |
| **decay** toward zero | **hysteresis + TTL** — demote at `θ`, restore below `θ_restore`; an override expires if not re-confirmed by the next window | `θ = 0.15`, `θ_restore = 0.08`, TTL = 1 window |
| min-sample defense | unchanged — carried by `eligible_for_adjustment` | producer-side |

**Why `θ = 0.15`:** in §2.2 the trigger was `delta < −0.01` (fires at `combined_signal > 0.01`) and
the cap **bound** at `combined_signal ≥ 0.15`. A single rank displacement is a *full-strength*
action, so it must fire at the old **saturation** point, not the old sensitivity point. Firing a
whole rank flip on `combined_signal = 0.02` would be far more aggressive than the ratified
continuous design ever intended. `|−0.15|` therefore survives as a **trigger threshold**, not as a
magnitude. `θ_restore = 0.08` (≈ θ/2) is the anti-flap band.

#### 2.4.7 Retirement / survival ledger — do not let stale params carry over

| Parameter (§2.2 / §2.3) | Fate |
|---|---|
| `weight_failure` 0.5 · `weight_cost` 0.3 · `weight_regression` 0.2 | ✅ **SURVIVE** — they aggregate evidence into `combined_signal`, which is still computed verbatim |
| `regression_half_weight` 0.5 | ✅ **SURVIVES** |
| `confidence_threshold` 0.7 | ✅ **SURVIVES** |
| D9b sign inversion `max(-combined_signal, cap)` | ⚠️ **PARTLY RETIRED** — the sign defect is real and its *lesson* holds (`combined_signal` is positive for a bad model), but the `max(…, cap)` clamp goes away with the magnitude. Compare `combined_signal ≥ θ` directly |
| D9c cost clamp `max(cost_index − 1.0, 0.0)` | ✅ **SURVIVES** — still inside `combined_signal` |
| `max_adjustment_cap` **−0.15** | ❌ **RETIRED as a magnitude.** `|0.15|` is re-purposed as `θ` |
| `score_delta` (RoutingRecord field) | ❌ **RETIRED** — replaced by `rank_displacement`; `combined_signal` is kept as *evidence*, never as an applied value |
| §2.2 step 3 worked example **−0.150 (cap-bound)** | ❌ **RETIRED as an assertion.** Its replacement: `combined_signal = 0.750 ≥ θ = 0.15` → demote 1 position |

#### 2.4.8 Consequences

- **DI-1 is unblocked on shape** and its acceptance criteria are updated to (C). It remains gated on
  DI-4b's verdict (cost-only merge acceptable or not) — an orthogonal blocker.
- **Resolver v4 / `scores:` wiring is out of scope for DI-1** and stays a standalone future upgrade.
- **Router-repo follow-ups** (MeatySkills, not CCDash): amend SPEC.md:222 to the §2.4.6 vocabulary
  (drop "effective-score floor"), and correct BL-1's stale `planned` status.

---

## 3. Promotion Readiness Criteria

### 3.1 Router Owner Readiness Checklist

Before flipping `live_consumption_disabled` → enabled, router owner MUST:

- [ ] **Read CCDash envelope contract** (§2 above + `ccdash-routing-feedback-consumer-contract-v1.md`)
  - Understand the 11 pinned fields, window semantics, confidence scale, and eligible_for_adjustment logic
  - Confirm all fields map to router's merge model

- [ ] **Validate envelope shape in staging**
  - Deploy CCDash producer with `CCDASH_ROUTING_FEEDBACK_ENABLED=true` to staging
  - Fetch a live `/api/v1/routing/rollup` response
  - Confirm all fields present, sample counts realistic, window boundaries sensible
  - Spot-check 5–10 rows for correctness (skill_name mapping, success_rate bounds, cost_index sign)

- [ ] **Negotiate numeric merge defaults**
  - Accept or modify the candidate defaults in §2.3
  - Document the chosen values in a router-side config file or hardcoded constant
  - Share the config with CCDash owner for reference in operator guidance

- [ ] **Agree on versioning & compatibility**
  - Confirm router's merge logic gracefully handles unknown/missing fields (forward compatibility)
  - Define the rollback procedure if a new CCDash version breaks the merge (e.g., schema v2 additions)
  - Establish a max-age policy for feedback windows (e.g., "ignore rows older than 7 days")

- [ ] **Plan RoutingRecord provenance tracking**
  - Router MUST emit RoutingRecord with `source_feedback_id` (references CCDash `routing_rollup.id`)
  - This enables operator audits ("why was this route downweighted?") and post-mortems

- [ ] **Dry-run in controlled environment**
  - Before production, stage a controlled scenario (e.g., 10 sessions with artificially high failure rate)
  - Confirm router picks up the signal and adjusts the route
  - Verify no infinite loops or race conditions (e.g., downweighted model never re-tried, starving feedback)

### 3.2 CCDash Handoff Validation (Phase 7+)

If router owner decides to promote DI-1, CCDash owner MUST:

- [ ] **Read router merge spec**
  - Ensure numeric defaults and merge math are compatible with CCDash's confidence semantics
  - Flag if router's logic contradicts the "eligible_for_adjustment = sample >= 5 AND not protected" invariant

- [ ] **Add operator guidance to `/docs/guides/routing-feedback-loop.md`**
  - Document the merge algorithm, tuning knobs, and expected latency (window → merge → next routing decision)
  - Provide runbooks for debugging: "routing not changing despite evidence," "route churning too fast," etc.
  - Link to router's documentation for merge algorithm details (out-of-tree)

- [ ] **Add integration test to seeded-PG smoke**
  - End-to-end: ingest sessions, compute routing_rollup, call `/api/v1/routing/rollup`, parse response
  - Confirm response shape is stable across runs (determinism, AC-3)
  - No new test code in CCDash; router owner's tests drive their side

- [ ] **Publish capability + version info**
  - Update `_V1_CAPABILITIES` to include routing version info if merge logic changes
  - Example: `"routing:feedback-v1.0.0"` or `"routing:feedback-v1.0.0:merge-bounded-adjustment"`
  - Router can check capability string to decide whether to consume

---

## 4. Risk Mitigation

### 4.1 Silent Non-Join (R-P3)

**Risk**: Router's merge runs but CCDash's envelope schema has drifted (e.g., new field added, old
field removed). Router misses the field, produces incorrect routing decisions, and no signal alerts.

**Mitigation**:
- **CCDash (Phase 1–6)**: Digest-parity test (AC-2) ensures mapping version + digest are frozen until explicitly re-versioned
- **Router (Phase 7+)**: Implement a contract-version check before consuming
  - Fetch `/api/v1/capabilities` on startup
  - Confirm `"routing:feedback"` is present and compatible (e.g., version >= 1.0.0 AND version < 2.0.0)
  - Fail startup with a loud error if version mismatch

### 4.2 Vocabulary Drift

**Risk**: Skill-name to task_class mapping is re-vendored in CCDash (e.g., new skill added), but router still consumes old mapping. Task classes diverge between producer and consumer.

**Mitigation**:
- **CCDash (Phase 1–6)**: Vendor digest locked. Router's CI guard (AC-2) catches changes
- **Router (Phase 7+)**: Before consuming, verify mapping digest via CCDash `/api/v1/routing/rollup` response
  - Extract `mapping_digest` from response
  - Compare against router's cached/pinned digest
  - If mismatch: log warning, skip this project's routing feedback, retry in next cycle (don't crash)

### 4.3 Feedback Loop Instability

**Risk**: Router adjusts routes based on feedback, which changes which models run, which generates new feedback, which adjusts routes again. Loop oscillates without converging.

**Mitigation**:
- **Router (Phase 7+)**: Implement cooldown/hysteresis
  - Do not adjust the same (task_class, model) twice within N hours (e.g., 24h)
  - Once adjusted, require 2+ independent feedback signals before re-adjusting
  - Log all routing-record transitions for audit trail

---

## 5. Deferred Tasks & Next Steps

### 5.1 No CCDash Changes Required

All work for DI-1 is owned by MeatySkills/delegation-router. CCDash Phase 1–6 is complete and
shipping with `live_consumption_disabled` (default-off).

### 5.2 Router Owner's Next Steps (If Promoted)

1. **Schedule design review** with router team to negotiate §2.3 defaults
2. **Implement merge algorithm** in MeatySkills/ibm-main against the CCDash contract (§2)
3. **Add integration test** to router's CI: fetch `/api/v1/routing/rollup` from local CCDash instance, parse, apply merge math
4. **Stage in pre-production** with real sessions; validate signal correctness
5. **Update router's consumer contract doc** to reference this spec and DI-2 (model namespacing) and DI-3 (window/decay defaults)

### 5.4 DI-4 — Producer Outcome Metrics v1.1 (BLOCKS DI-1)

**Added 2026-08-01. Owner: CCDash. This is the actual next actionable item.**

Per §0, DI-1 cannot produce a non-neutral adjustment until the envelope carries a real outcome
signal. DI-4 is that increment:

- **Populate `success_rate`** from a genuine outcome signal rather than `sessions.status`.
- **Populate `regression_rate`** likewise.
- **Derive a real `cost_index`** — a per-key cost normalization against a cross-key baseline,
  replacing the fixed `_COST_INDEX_BASELINE = 1.0`.

**Signal sources**: see the audit in §0. `cost_index` has a verified source
(`sessions.total_cost`, 72% populated, already at the right grain). `success_rate` and
`regression_rate` have **none** — every candidate table was checked and ruled out.

**Split accordingly:**

- **DI-4a — `cost_index` (Tier 1 Feature Contract).** Aggregate mean per-session cost per
  `(source_skill_name × model)` key, normalize against a cross-key baseline, replace the fixed
  `_COST_INDEX_BASELINE = 1.0`. The design decisions worth naming: which baseline (global mean vs
  per-task-class mean vs cheapest-key), and what to emit for a key whose sessions have no cost
  attribution (28% of rows) — `null`, never a fabricated `1.0`, per the same principle that made
  v1 emit `null` in the first place.
- **DI-4b — `success_rate` / `regression_rate` (SPIKE).** ~~Answer "does a derivable per-session
  success signal exist?"~~ **CLOSED 2026-08-03 — verdict CONDITIONAL.** All four legs ran; see the
  DI-4b outcome box in §0 and the full synthesis at
  `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md`.
  The lead candidate named here (harness error-entry counts) was **refuted** — and was
  mis-specified in §0 to begin with. Outcome:
  - `success_rate`: one viable candidate (per-key tool-error rate, 140/188 = 74.5% informative
    keys), gated on a **named bounded precondition** — fix Codex tool-error detection (0/37
    GPT/Codex keys informative today) and re-measure. Successor task: **DI-4d** below.
  - `regression_rate`: **no signal exists**, confirmed by all four legs. Closed, not deferred.
    Leave null indefinitely; revisit only as a new-capture question.
  - Leave `live_consumption_disabled` until DI-4d clears.

- **DI-4d — Fix Codex tool-error detection (NEW, blocks `success_rate`).** The Codex parser's
  error-detection heuristic never matches real payloads: GPT/Codex sessions record 190,450 tool
  calls with exactly 0 errors, while Claude-family tools show plausible rates (`Bash` 3.7%,
  `Write` 6.2%, `WebSearch` 7.5%). Acceptance: GPT/Codex informative-key fraction becomes
  comparable to Claude's, or the residual gap is quantified and explicitly accepted; then re-run
  the DI-4b `tool-failures` coverage measurement against the same 188-key denominator so
  before/after is directly comparable. Only after that is a `success_rate` producer increment
  (DI-4e) scopeable.

- **DI-4f — Routing-key skill attribution (NEW, conditions all DI-4b value).** 114 of the 188
  min-sample-clearing keys (61%) have a NULL `skill_name`. Exploration charter:
  `docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-charter.md`.
  Decide this before further `success_rate` investment — a perfect signal on a key with no skill
  dimension is a `(project × model)` signal, not the skill-aware feedback DI-1 was designed for.

**Coverage is a first-class contract state** in both halves: emit `null` when a key lacks
attribution, never a fabricated zero or baseline.

**Versioning**: additive per D5. A v1.1 envelope that populates previously-`null` fields is
forward-compatible with any consumer that already tolerates `null`.

### 5.3 CCDash Owner's Next Steps (If Promoted)

1. **Track router's merge spec** as it stabilizes in MeatySkills/ibm-main
2. **Update operator guidance** (`/docs/guides/routing-feedback-loop.md`) with merge algorithm, tuning knobs, and troubleshooting
3. **Implement capability version check** if router requests version-specific behavior
4. **Plan for Phase 7 / post-v1** cross-repo seam validation

---

## Appendix: Example RoutingRecord (Router Output)

**Example**: Router consumes a CCDash row with high failure rate and emits a RoutingRecord:

```json
{
  "source_feedback_id": "rf:123456",
  "source_feedback_window": "2026-07-24T00:00:00Z",
  "task_class": "ai:model-selection:multi-choice",
  "model": "claude-haiku-4-5",
  "provider": "anthropic",
  "score_delta": -0.15,
  "evidence": {
    "success_rate": 0.62,
    "cost_index": 0.50,
    "regression_rate": 0.15,
    "sample_count": 37,
    "confidence": 0.82
  },
  "timestamp": "2026-07-31T10:30:00Z",
  "source": "ccdash-routing-feedback-v1.0.0"
}
```

**Interpretation**: Haiku's success rate on this task is 62% (vs ~80% for other models). Cost is
very low (0.50× baseline), but under the ratified algorithm cheapness earns no offset —
`penalty_for_cost` clamps to `0.0`. The merge computes:

```
penalty_for_failure    = 1.0 - 0.62          = 0.380
penalty_for_cost       = max(0.50 - 1.0, 0)  = 0.000
penalty_for_regression = 0.15 * 0.5          = 0.075
combined_signal        = 0.380*0.5 + 0.000*0.3 + 0.075*0.2 = 0.205
score_delta            = max(-0.205, -0.15)  = -0.150      ← cap binds
```

Router applies the −15% cap to Haiku's score for this task and emits the RoutingRecord for
auditing. (Under the *original* uncorrected pseudocode these same inputs produced `+0.055 →
NEUTRAL` — no adjustment at all. That discrepancy is what surfaced the sign defect.)

> **Reminder**: this example uses illustrative non-null metrics. The shipped v1 producer emits
> `success_rate: null`, `regression_rate: null`, `cost_index: 1.0` for every row — see §0.

---

## References

- **CCDash Routing Feedback Consumer Contract**: `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md`
- **Proof→Routing Loop PRD**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` (§3, Problem Statement; §8, Decisions D1/D8; §13, OQ-6)
- **AOS Routing Feedback Contract**: `/Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md`
- **AOS Model Registry**: `~/.claude/config/model-registry.yaml` (current hand-maintained scorecard)
