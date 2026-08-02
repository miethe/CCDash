---
title: "Design Spec: Routing Feedback Router Merge Handoff (DI-1)"
doc_type: design-spec
maturity: shaping
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
status: draft
created: 2026-07-31
updated: 2026-07-31
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
| `success_rate` | `None`, always | `sessions.status` carries only `active`/`completed` — not a success/failure signal. Fabricating one "would be actively misleading to a consuming router." |
| `regression_rate` | `None`, always | Same — no genuine regression signal available to that module. |
| `cost_index` | `1.0`, fixed (`_COST_INDEX_BASELINE`) | Per-key cost normalization is "a real design surface of its own," deliberately not gold-plated into a provisional payload. |
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

DI-4 does **not** decompose evenly. A signal-source audit against the node Postgres
(2026-08-01, 18,762 sessions) found the three fields have completely different feasibility:

| Field | Feasibility | Evidence |
|-------|-------------|----------|
| `cost_index` | **Buildable now** | `sessions.total_cost` / `display_cost_usd` > 0 on **13,460 of 18,762** rows (72%). Aggregates directly at the `(source_skill_name × model)` grain — no external join, no new table. |
| `success_rate` | **No signal exists** | see audit below |
| `regression_rate` | **No signal exists** | see audit below |

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
- `session_stack_observations` — 16,559 rows, all `observation_source: backfill`, with
  `skillsUsed: []` and `agentsUsed: []` empty in samples; payload is queue-pressure and
  artifact-count telemetry, carrying no outcome semantics.

> An earlier revision of this section named `effectiveness_rollups` as DI-4's signal source and
> called the work "grain reconciliation." That was **wrong** and is corrected above — the table has
> no populated skill dimension, so no join is possible. Recorded rather than silently edited,
> because the mistaken version was committed and may have been read.

**A promising lead for the success signal** (untested, for the SPIKE to evaluate): the
`<synthetic>` harness entries this feature just taught the parser to ignore as a *model* are
themselves **per-session failure events** — `API Error: Connection closed mid-response` and
interrupt notices, present in 325 occurrences across 249 transcripts. Counting harness error
entries per session is a candidate derivation for `regression_rate`, and its complement for
`success_rate`. Adjacent candidates: tool-failure rates, session abandonment (`active` sessions
that never complete), and rework/retry patterns already surfaced by the AAR review loop.

**Consequent routing** — DI-4 is two artifacts, not one plan. Both authored 2026-08-01:

1. **DI-4a `cost_index` → Tier 1 Feature Contract** (5 pts, buildable today):
   `docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md`
2. **DI-4b `success_rate` / `regression_rate` → exploration charter first** (3-day timebox):
   `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md`
   Whether *any* derivable success signal exists is an open feasibility question, not an
   implementation task. Planning an implementation before that question is answered would repeat
   the mistake this section documents.

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
- **DI-4b — `success_rate` / `regression_rate` (SPIKE).** Answer "does a derivable per-session
  success signal exist?" before planning an implementation. Lead candidate: harness error-entry
  counts (see §0). Deal-killer: if no candidate reaches usable coverage, DI-1 stays deferred
  indefinitely and the honest outcome is to leave `live_consumption_disabled` and say so.

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
