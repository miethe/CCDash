---
schema_version: 2
doc_type: exploration_synthesis
title: "Routing Feedback Success Signal — Synthesis & Verdict"
status: completed
created: 2026-08-03
feature_slug: routing-feedback-success-signal
verdict: conditional
parent_charter: docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md
---

# Routing Feedback Success Signal — Synthesis & Verdict

Four investigation legs ran in parallel on 2026-08-03 against the operative node Postgres
(`10.42.10.76:5440`, 19,178 sessions). Every quantitative claim below traces to a query run by a
leg or by the orchestrator; the orchestrator independently re-verified the two load-bearing claims.

**Verdict: CONDITIONAL.**

---

## 1. The shared denominator

Rollup key is `(project_id, skill_name, model)` — `project_id` is part of the real key, which the
charter's `(source_skill_name × model)` shorthand omits. `min_sample` = 5,
`window_days` = 30 (`backend/config.py`).

| Quantity | Value |
|---|---|
| Sessions, all time | 19,178 |
| Sessions in 30-day window | 7,354 |
| All keys in window | 396 |
| **Keys clearing `min_sample`=5 — THE DENOMINATOR** | **188** |
| Sessions inside those 188 keys | 6,952 |

Coverage is reported as `N/188` throughout — percent of keys clearing min_sample, never percent of
sessions, per the charter's explicit instruction. Each leg reported *derivable* keys and
*informative* keys (non-constant) separately, because a column that is present but constant
everywhere is coverage without information.

## 2. Leg results

| Leg | Coverage (informative / 188) | Confound | Verdict | Confidence |
|---|---|---|---|---|
| `tool-failures` | **140 / 188 = 74.5%** | Categorical parser gap — **mitigable** | **conditional** | 0.85 |
| `harness-errors` | 70 / 188 = 37.2% | Unmitigable | no-go | 0.85 |
| `abandonment` | 60 / 188 = 31.9% (7-day threshold) | Unmitigable | no-go | 0.85 |
| `existing-rollups` | 49 / 188 = 26.1% (if fixed) | Scores themselves circular | no-go | 0.75 |

**`tool-failures` is the only candidate that clears the ≥50% threshold.** The three others fail on
coverage alone, before their confounds are even weighed — each independently, and each for a
different structural reason.

## 3. Why the verdict is conditional and not go

`session_tool_usage.success_count/call_count` genuinely derives from `tool_result.is_error`
(Claude Code parser) and Codex's `status` field. Naive coverage is a comfortable pass at 74.5%.

Split by model family and it collapses in a specific, non-random way:

| Family | Keys | Informative | Tool calls (in window) | Errors |
|---|---|---|---|---|
| Claude | 138 | **137 (99.3%)** | 183,813 | 5,836 |
| GPT / Codex | 37 | **0 (0.0%)** | 60,128 | **0** |
| other | 13 | 3 | 387 | 9 |

All-time the gap is starker still: GPT/Codex sessions logged **190,450 tool calls with exactly zero
errors**, against Claude's 398,043 calls / 13,708 errors (3.4%). Codex-native tool names
(`exec_command`, `apply_patch`) sit at 0.0000% while Claude-native tools show plausible real rates
(`Bash` 3.7%, `Write` 6.2%, `WebSearch` 7.5%). Zero errors across 190k calls is not reliability —
it is an unpopulated field. The Codex error-detection heuristic never matches real payloads.

This is **not noise, and that is precisely why it disqualifies a go**. Shipping this derivation as
`success_rate` today would hand the router a signal in which every GPT/Codex key looks flawless by
construction. `weight_failure` is 0.5 — the single largest term in the merge (§2.3) — so the router
would systematically prefer GPT/Codex models over Claude models on the strength of a parser gap,
with real routing consequences. That is worse than the current honest null: an inert loop misroutes
nothing, whereas a categorically biased one misroutes confidently.

It is nonetheless **conditional rather than no-go** because the defect is a bounded, named,
independently-verifiable fix in one parser path — not a missing capture surface. The charter's own
conditional criterion ("a candidate shows promise but its coverage or confound risk can only be
resolved by a specific named follow-up") describes this exactly.

**The deal-killer did not trigger**: a candidate does reach usable coverage across keys clearing
min_sample. The honest outcome is therefore not abandonment — it is a gated one-step follow-up.

## 4. Named precondition (what "conditional" is conditional on)

1. **Fix Codex tool-error detection**, then re-measure the family split. Acceptance: GPT/Codex
   informative-key fraction becomes comparable to Claude's, or the residual gap is quantified and
   explicitly accepted. Until then `success_rate` MUST stay null — do not ship a Claude-only signal
   into a cross-family router key.
2. **Re-run this leg's coverage measurement** post-fix against the same 188-key denominator, so the
   before/after is directly comparable.
3. **Only then** scope the `success_rate` producer increment (DI-4b implementation).

A narrower fallback exists and is explicitly *not* recommended: scope the signal to Claude-family
keys only. It is narrower than DI-4b asks, and a partially-populated cross-family key space
reintroduces the same bias in a subtler form.

## 5. `regression_rate` remains unsourced

Every leg addressed the success/failure axis. **None found a regression signal**, and one reason is
now firm: `test_results` and `test_runs` are both **0 rows system-wide**, so no test-outcome
signal exists to regress against. No retry/rework linkage exists in the schema either — 95.2% of
sessions with a recorded tool failure still completed, and "failed once then recovered" is
indistinguishable from "failed and stayed broken."

`regression_rate` should stay null indefinitely, and no follow-up in §4 will populate it. If the
router needs a regression term, that is a new-capture question, not a derivation question.

## 6. Corrections to committed prior art

Two claims in committed documents are refuted by measurement. Recorded rather than silently
edited, matching the precedent §0 itself set.

### 6.1 The `<synthetic>` lead was mis-specified

Handoff spec §0 names the lead candidate as `<synthetic>` harness entries, "325 occurrences across
249 transcripts." Measured:

| Query | Result |
|---|---|
| `session_messages.content LIKE '%<synthetic>%'` | **11 rows / 5 sessions** |
| `sessions.model = '<synthetic>'` | **244 sessions** |
| `content LIKE '%API Error%'` | 545 rows / 436 sessions |
| `content LIKE '%Request interrupted%'` | 427 rows / 399 sessions |

The audit conflated *sessions whose model never resolved* (`model = '<synthetic>'`, 244 — the
origin of "249 transcripts") with *harness error entries*. The literal string is near-absent from
transcript content and is mostly meta-discussion where it does appear. Real harness errors live as
free text (`API Error:`, `Agent "..." failed:`, `[Request interrupted...]`) in
`session_messages.content`.

This matters beyond bookkeeping: `model = '<synthetic>'` is **self-referential as an outcome
signal** — the model is unresolved *because the request failed first*. 5 of the 188 keys carry it,
one driving an 82% "error rate" that is pure circularity. The exploration's designated lead
candidate was, in part, an artifact of the failure it was meant to measure.

### 6.2 The `effectiveness_rollups` attribution gap has a different cause — and a second blocker

The prior explanation (component extraction emitting hashes/prompt-text so `resolve_stack_components`
matches nothing) is refuted. Clean skill slugs *do* exist (`toolLabel: "dev-execution"`, `"planning"`)
in `session_messages` (814 rows / 815 distinct sessions). The actual cause: `stack_observations.py`
reads exclusively from **`session_logs`, which has 0 rows** on the operative Postgres, because the
enterprise sync profile deliberately stopped writing it (`sync_engine.py:_should_write_legacy_session_logs`)
in favour of `session_messages`. That is a bounded wiring bug (~3–5 pts, no migration).

But a **second, independent, open-ended blocker** sits behind it: `effectiveness_rollups`' scope-key
grain **has no `model` dimension at all**. Fixing attribution cannot serve a `(skill × model)` key
without a separate unscoped redesign (likely 8–13 pts on its own). And the scores themselves are
confounded: 86.4% of stack-scope rows sit at an identical formulaic `successScore ≈ 0.45`, driven by
`sessions.status` — the already-rejected signal — weighted 0.45, plus a `test_pass_ratio` term that
is always 0 because `test_results`/`test_runs` are empty. **`effectiveness_rollups` is not a
latent outcome signal awaiting a join; it is largely a re-encoding of the signal §0 already
rejected.** This closes it as an alternative path.

## 7. Cross-cutting findings the charter did not ask for

- **`session_logs` is empty (0 rows) system-wide.** Found independently by two legs. It breaks
  stack-observation attribution *and* removes all per-call tool-error detail, so error *text* cannot
  be inspected without re-parsing raw JSONL. Any future work assuming `session_logs` is populated is
  building on sand.
- **61% of min_sample-clearing keys have a NULL `skill_name`** (114 of 188), which the producer
  coalesces to `""`. Even given a perfect success signal, most keys the router acts on carry no
  skill identity and degenerate to `(project × model)`. This bounds the value of *any*
  skill-keyed routing feedback and is worth its own decision before further DI-4b investment.
- **`cost_index` is live and load-bearing.** On the node, `routing_rollup` has 261/346 rows with
  non-null `cost_index` across 249 distinct values (sweeping as of 2026-08-03 16:35), while
  `success_rate`/`regression_rate` are 0/346. DI-4a shipped. So the loop is **cost-only**, not
  inert — a no-go here would have degraded it, not killed it. §0's table stating `cost_index = 1.0
  fixed` is now stale.

## 8. What to do next

1. Fix Codex tool-error detection; re-measure the family split (§4).
2. Decide on the NULL-`skill_name` question (§7) — it conditions the value of all DI-4b work.
3. Leave `success_rate` and `regression_rate` null, and `live_consumption_disabled`, until (1) clears.
4. Do not schedule DI-1. Do not pursue `effectiveness_rollups` as an alternative (§6.2).
5. Update handoff spec §0 for the two corrections in §6 and the stale `cost_index` row in §7.

## 9. Confidence

**0.84** — mean of the four leg confidences (0.85 / 0.85 / 0.85 / 0.75), sustained rather than
discounted because the orchestrator independently reproduced the two claims the verdict rests on:
the tool-failures family split (140/188 informative; 0/37 GPT/Codex; 190,450 calls / 0 errors
all-time) and the `<synthetic>` refutation. One leg's coverage figure differed from the
orchestrator's first attempt by 139 vs 140 keys; the discrepancy was traced to NULL-unsafe join
semantics in the orchestrator's query (`skill_name` is NULL on 114 keys), not to the leg — the
leg's number stands.
