---
schema_version: 2
doc_type: exploration_charter
title: "Routing Feedback Success Signal — Exploration Charter"
status: draft
created: 2026-08-01
feature_slug: routing-feedback-success-signal
timebox_days: 3
hypothesis: "A per-session success/failure signal can be derived from existing CCDash session telemetry with high enough coverage to make routing-feedback's failure term load-bearing."
deal_killer: "If no candidate derivation reaches usable coverage across the (source_skill_name x model) keys that clear min_sample, abandon -- leave success_rate/regression_rate null, leave live_consumption disabled, and record that the loop cannot be closed without new capture rather than shipping a fabricated signal."
investigation_legs:
  - id: harness-errors
    question: "Can harness error entries be counted per session as a failure signal, and is an API/infrastructure error confounded with model-quality failure for routing purposes?"
    assigned_to: spike-writer
  - id: tool-failures
    question: "Do tool_use/tool_result pairs expose a per-session tool error rate usable as a failure signal?"
    assigned_to: spike-writer
  - id: abandonment
    question: "Are active sessions that never reach completed (533 rows) a usable negative signal, or just watcher lag?"
    assigned_to: spike-writer
  - id: existing-rollups
    question: "What would it cost to populate skill attribution in effectiveness_rollups so its successScore/riskScore/qualityScore become usable, as an alternative to deriving a new signal?"
    assigned_to: spike-writer
verdict_criteria:
  go:
    - "At least one investigation leg identifies a derivation whose coverage, measured as a percentage of (source_skill_name x model) keys that clear min_sample, exceeds a usable threshold (recommend >=50% of clearing keys; the SPIKE must state and justify its own threshold)"
    - "The chosen derivation's confound risk (e.g. harness-errors' infrastructure-vs-model-quality conflation) is assessed and judged acceptable or mitigable"
    - "Deal-killer condition not triggered"
  no_go:
    - "Deal-killer condition triggered: no candidate reaches usable coverage across keys clearing min_sample"
    - "The only coverage-adequate candidate has an unmitigable confound (e.g. harness-errors signal is dominated by infrastructure noise, not model-quality variance)"
  conditional:
    - "A candidate shows promise but its coverage or confound risk can only be resolved by a specific named follow-up (e.g. populating effectiveness_rollups skill attribution first, per the existing-rollups leg)"
verdict: null
verdict_rationale: null
output_artifacts: []
related_documents:
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
---

# Routing Feedback Success Signal — Exploration Charter

## Hypothesis Context

DI-1 (the router merge) is permanently inert against the shipped v1 producer because
`success_rate`/`regression_rate` are `None` for every row, by design — no genuine outcome signal
exists yet in `sessions` (handoff spec §0). The audit ruled out every existing table as a direct
source: `sessions.status` carries only two non-outcome values, `test_results` has zero rows, and
`effectiveness_rollups` (14,561 rows, real `successScore`/`riskScore`/`qualityScore`) has no
populated skill dimension to join against (`skills:none` on all 7,290 stack-scope rows). One lead
survived untested: `<synthetic>` harness error/interrupt entries (325 occurrences / 249
transcripts) are per-session failure events, whose complement is a candidate `success_rate`. This
exploration decides whether that lead, or an adjacent one, is usable — before implementation.

---

## Investigation Legs

### Leg: harness-errors — Harness Error Entries as Failure Signal

**Question**: Can harness error entries be counted per session as a failure signal? Lead
candidate: the `<synthetic>` entries (325 occurrences / 249 transcripts) are literally `API Error:
Connection closed mid-response` and interrupt notices.
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/harness-errors-spike.md`

- Coverage: fraction of `(source_skill_name × model)` keys clearing `min_sample` with enough
  variance in harness-error presence to derive a rate (not a mostly-zero column).
- **Confounding — this leg's central question, not a footnote**: a connection-closed error is an
  infrastructure/transport failure, not evidence of a bad model response. Assess whether harness
  errors correlate with anything model-attributable (rate-limiting/overload clustering the router
  *should* react to) or are uniform noise it *shouldn't*.
- If confounded and unmitigable: is a complement-based `success_rate` meaningfully different from
  re-deriving `sessions.status`'s `completed`/`active` split — already rejected as a non-signal?

### Leg: tool-failures — Tool Use/Result Error Rate

**Question**: Do `tool_use`/`tool_result` pairs expose a per-session tool error rate usable as a
failure signal?
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/tool-failures-spike.md`

- Coverage, as a percentage of keys clearing `min_sample`.
- Whether a tool-call error is attributable to the model's choices vs. the tool/environment — the
  same confound shape as the harness-errors leg.

### Leg: abandonment — Active-Never-Completed Sessions

**Question**: Are `active` sessions that never reach `completed` (533 rows, per §0) a usable
negative signal, or just watcher lag?
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/abandonment-spike.md`

- Age distribution of `active` sessions: overwhelmingly recent (watcher lag, not abandonment) vs. a
  meaningful stale tail.
- Coverage, as a percentage of keys clearing `min_sample`, under a stale-active threshold.

### Leg: existing-rollups — Cost of Populating `effectiveness_rollups` Skill Attribution

**Question**: Could `effectiveness_rollups` become usable if skill attribution were populated?
§0 proves it is unusable TODAY — this leg scopes what populating it would cost, as an alternative
to deriving a new signal.
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/existing-rollups-spike.md`

- Where skill attribution fails to get set upstream, and whether closing that gap is bounded or
  open-ended.
- If bounded: would it unlock coverage comparable to or better than the other candidates, given
  the table already carries real success/risk/quality scores?

---

## Verdict Criteria Narrative

**Go** if: at least one leg's derivation reaches usable coverage — as a percentage of
`(source_skill_name × model)` keys clearing `min_sample`, **not** a percentage of all sessions,
which would overstate usability for exactly the keys the router acts on — and its confound risk is
judged acceptable or mitigable.

**No-go** if: the deal-killer triggers, or the only coverage-adequate candidate has an unmitigable
confound (e.g. harness-errors encoding "rate-limited" as "performs badly"). Either way: leave
`success_rate`/`regression_rate` null, leave `live_consumption_disabled`, and record that the loop
cannot be closed without new capture — not a fabricated signal.

**Conditional** if: a candidate shows promise but is blocked on a named, scopeable follow-up (most
plausibly existing-rollups' attribution gap) — the next step is that follow-up, not a fresh search.

---

## Out of Scope

- Implementing any derivation — feasibility question, not an implementation task (§5.4).
- `cost_index` (DI-4a) — tracked separately, already buildable
  (`docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md`).
- Any router-side merge-algorithm change (DI-1) — deferred, owned by MeatySkills/`ibm-main`.
- New data capture instrumentation — a no-go verdict is the answer, not a mandate to scope it here.

---

## Citations / Prior Art

- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` §0 (signal-source
  audit) and §5.4 (DI-4 scoping; this charter covers DI-4b).
- `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` — parent PRD.

---

## Notes

2026-08-01: Charter authored per the ground-truth audit in the handoff spec §0/§5.4. No legs run yet.
