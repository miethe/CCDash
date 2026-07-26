---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Proof → Routing Feedback Loop — Feasibility Brief"
status: finalized
created: 2026-07-23
updated: '2026-07-26'
feature_slug: proof-to-routing-loop
verdict: conditional
verdict_confidence: 0.75
exploration_charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
proposed_adr_ref: null
recommended_next_action: "/plan:plan-feature --tier=2; T1 vocabulary contract is pinned, while rollup and router merge remain unimplemented"
precondition_status: cleared-2026-07-26
related_documents:
- docs/project_plans/exploration/proof-to-routing-loop/spikes/tech-findings.md
- docs/project_plans/exploration/proof-to-routing-loop/spikes/value-findings.md
- docs/project_plans/exploration/proof-to-routing-loop/spikes/risk-findings.md
- docs/project_plans/design-specs/proof-to-routing-loop.md
---

# Proof → Routing Feedback Loop — Feasibility Brief

**Verdict: `conditional` (confidence 0.75).** Mechanics clone the shipped AAR-review PULL
contract cleanly (~10–16 pts, Tier 2). The blocker is not CCDash-side: it is an unresolved
cross-repo vocabulary join with the delegation-router that this repo cannot close alone.

> **T1 resolution addendum (2026-07-26):** The historical exploration verdict remains
> `conditional`, but its named precondition is now cleared. agentic_meta_dev owns
> `docs/agentic-operator/contracts/routing-feedback.md` and the exact v1 source mapping;
> MeatySkills `ibm-main` owns `aos.routing.task_class` v1.0.0 plus a fail-closed external join
> validator. The decision explicitly rejects raw `skill_name == task_class` (17 observed names,
> 12 policy keys, zero direct overlaps). The feature may now proceed to
> `/plan:plan-feature --tier=2`. CCDash rollup emission, router adjustment math, and live
> consumption are still absent/disabled.

---

## 1. Synopsis

The design spec (`docs/project_plans/design-specs/proof-to-routing-loop.md`, maturity `shaping`)
proposes closing the AOS "backward pass" (workstream #6) by having CCDash emit a deterministic,
opt-in `(task_class × model × provider × profile)` rollup that the delegation-router (MeatySkills
repo, branch `ibm-main`) ingests as an empirical routing prior — turning CCDash's existing
observability into an actuating signal without ever putting a model on the decision path
(Constraint 4). Three legs investigated independently — tech, value, risk — and converged on the
same shape: the emission machinery is a near-exact, low-risk clone of the shipped AAR-review
consumer contract, but the spec's literal 4-field tuple is not what the data or codebase actually
support. Two of its four fields are write-path-dead, `provider` is a derived value rather than a
raw column, and the one load-bearing field the tuple survives on — `task_class` — has exactly one
deterministic CCDash-side candidate (`skill_name`), whose vocabulary is this repo's own skill
catalog with no confirmed join to the router's own taxonomy, which lives in a repo none of the
three legs could see. The verdict is therefore `conditional`: the build is real and cheap, but it
depends on a precondition CCDash cannot satisfy unilaterally.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| tech | spike-writer | 0.75 | [tech-findings.md](spikes/tech-findings.md) | Mechanics clone the AAR-review contract exactly (worker, `agent_queries/` service, REST/MCP/CLI, capability gate, default-off flag); tuple fields confirmed captured but `provider` is derived (not raw) and `profile`/`effort_tier`/`model_variant` are fed by an opt-in, fail-open sidecar; `skill_name` is the only viable `task_class` candidate and its router-joinability is structurally unconfirmable from this repo. Estimate: 10–16 pts. |
| value | data-layer-expert | 0.75 | [value-findings.md](spikes/value-findings.md) | Real telemetry (14,399 sessions, `data/ccdash_cache.db`) shows `profile`/`effort_tier`/`model_variant` at 0/14,399 populated (write-path-dead); the coarsened `(skill_name, model)` tuple yields 40 keys with 52% clearing N≥5 and 35% clearing N≥10 (30-day window: 50%/33%) — density deal-killer refuted for the achievable tuple, not the literal one. |
| risk | backend-architect | 0.72 | [risk-findings.md](spikes/risk-findings.md) | Charter deal-killer "partially triggered": CCDash blast radius is confirmed near-zero and Constraint-4 holds structurally, but a spec-only seam contract (which worked for AAR's CCDash-owned enums) does not transfer to `task_class` because it is an external join key — silent non-join or coincidental mis-join is the dominant unmitigated risk. |

---

## 3. Cost Estimate

**Rough estimate**: 10–16 story points (Tier 2 equivalent) for the CCDash-side emission
machinery, read-time-aggregation path. Add +6–9 pts if a persisted `routing_rollup` table is
chosen instead of read-time aggregation ([tech-findings.md §5](spikes/tech-findings.md)).

**Comparable past feature**: `aar_reviews` / Automated AAR Review Loop v1 (~30–45 pts across
7 phases, merged `7d96c3e`) — used as the H5 anchor per the charter. This rollup needs neither
AAR's multi-hop evidence-correlation phase (P2) nor its SkillMeat semantic 5th-flag phase (P3),
since the aggregation here is a flat GROUP BY over already-typed session rows, not a doc→feature→
plan→task traversal — hence the smaller slice of AAR's total budget.

**Major cost drivers**:
- `task_class` derivation module + sparse/null-bucket handling (novel logic): 2–3 pts
- Rollup query service (GROUP BY + threshold/window arithmetic, `system_metrics.py`-shaped): 3–4 pts
- REST endpoint, capability-gate string, config flag(s): 1–2 pts
- MCP + CLI surfaces (thin, precedent-heavy wrappers): 1–2 pts
- Consumer-contract doc + operator guide, No-LLM CI guard port: 3–4 pts

**Not captured in the estimate**: the cross-repo taxonomy-join risk (§5/§6 below) is a *blocking
precondition*, not a story-point cost CCDash-side work can absorb ([tech-findings.md §5](spikes/tech-findings.md)).

---

## 4. Value Statement

**Primary beneficiaries**: The delegation-router (and, transitively, the operator whose tasks it
routes), which today has only a hand-maintained `model-registry.yaml` scorecard that drifts and
depends on a human noticing a bad route before it's corrected.

**Evidence of demand**:
- The design spec names an explicit, currently-open gap: the AOS "forward pass" (idea → route →
  execute → record) is strong but the "backward pass" (outcome → learning → changed future
  behavior) is weak — proof is observability, never actuation
  (`docs/project_plans/design-specs/proof-to-routing-loop.md` §1).
- The value leg confirms the underlying signal is real, not speculative: even in a young (~7-week),
  sparsely-populated (5–23%) capture window, roughly half of `(skill_name, model)` keys already
  clear a usable sample threshold and the trend is rising, not flat
  ([value-findings.md §3](spikes/value-findings.md)).

**Counterfactual**: If not built, the router's only empirical input remains the hand-authored
scorecard; a route that repeatedly fails, costs 5x, or regresses keeps getting selected until a
human notices and edits `model-registry.yaml` by hand — the exact backward-pass gap the spec names.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| `task_class` vocabulary mismatch → silent non-join: rollup ships real, well-formed `sample_count`s that never intersect the router's own taxonomy keys (or, worse, coincidentally partially overlap and drive real mis-routing) | organizational | H | Negotiate the shared `task_class` vocabulary with the delegation-router owner *before* the router consumes the field as a live join key; ship `task_class` as an explicit, versioned, documented field so a mismatch is human-detectable, mirroring the AAR contract's enum-field discipline ([risk-findings.md §2-3](spikes/risk-findings.md)) |
| Literal 4-field tuple triggers the density deal-killer as written (`profile`/`effort_tier`/`model_variant` are 0/14,399 populated) | technical | M | Ship the coarsened `(mapped task_class × model)` tuple, not the spec's literal tuple — this is forced by data reality, not a design choice ([value-findings.md §2-4](spikes/value-findings.md)) |
| Guardrail split across repos: bounded-adjustment floor and human-override-always-wins are the router's implementation, unverifiable from CCDash | technical | M | Document in the seam contract exactly which §5 guardrails are CCDash's (verifiable) vs. the router's (asserted only) ([risk-findings.md §4](spikes/risk-findings.md)) |
| CCDash-side blast radius (schema, endpoints, worker) | technical | L | Additive-only, default-off flag (`CCDASH_ROUTING_ROLLUP_ENABLED`), no existing row/endpoint modified — same pattern as `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`; reversible instantly ([risk-findings.md §6](spikes/risk-findings.md)) |

**Blast radius**: Confirmed near-zero. The risk this exploration surfaced is not "CCDash breaks
something" — it is "CCDash builds a correct, safe, zero-blast-radius feature that is functionally
inert or silently miscalibrated on the consumer side because the join key was never negotiated"
— an effectiveness risk wearing a blast-radius costume ([risk-findings.md §6](spikes/risk-findings.md)).

---

## 6. Architectural Implications

No new architectural pattern is required — this fits the existing worker-primed, transport-neutral
`agent_queries/` → REST/MCP/CLI → `/api/v1/capabilities`-gated, default-off-flag shape already
proven by the AAR-review consumer contract and `system_metrics.py` rollups
([tech-findings.md §4](spikes/tech-findings.md)). The one real architectural correction this
exploration produced is to the spec's tuple itself:

- **`provider` is not a raw column** — no `model_provider`/`modelProvider` column exists in the
  `sessions` DDL. It is computed at read/serialization time by `derive_model_identity()` from the
  first token of `model`. It should be treated as a derived GROUP BY key, not a captured field, and
  it never independently splits a key already grouped by `model` — it can only ever coarsen `model`,
  never refine it ([tech-findings.md §3](spikes/tech-findings.md); [value-findings.md §4](spikes/value-findings.md)).
- **`profile`, `effort_tier`, `model_variant` must be dropped** from the tuple. The columns and
  parser wiring exist (fed by an opt-in, fail-open launch-time capture sidecar) but are
  write-path-dead in the operator's real corpus — 0/14,399 sessions populated. This is forced by
  data reality, not a design preference ([tech-findings.md §3](spikes/tech-findings.md);
  [value-findings.md §2](spikes/value-findings.md)).
- **`task_class` is an explicit mapped value derived from `skill_name`, not the raw string.**
  `skill_name` remains the only captured source field suitable for a deterministic mapping, but the
  2026-07-26 T1 review proved its vocabulary is a different namespace (17 observed names, 12 router
  policy keys, zero exact overlaps). CCDash preserves `source_skill_name`, applies only a pinned
  exact mapping, and surfaces `_unclassified` plus coverage for null/unlisted/executor-identity
  values. `_unclassified` is telemetry-only and never routes. This supersedes the exploration's
  original raw-equality candidate while retaining its "never synthesize a default" visibility
  requirement ([tech-findings.md §2, §6 OQ-3](spikes/tech-findings.md)).
- The net corrected tuple is `(mapped task_class × model)`, effectively 2-dimensional, not
  the spec's literal 4-dimensional tuple. `provider` may still ride along in the response payload
  for free (derived from `model`) but contributes no independent cardinality.
- The cross-project crux is now resolved by `aos.routing.feedback` v1.0.0:
  agentic_meta_dev owns the seam decision and source mapping; MeatySkills owns
  `aos.routing.task_class` v1.0.0 and a fail-closed validator that binds
  `source_skill_name → task_class`. Contract/taxonomy/mapping mismatch, aliases, unknowns,
  `_unclassified`, and protected classes have no empirical effect. The router's live-consumption
  gate is executable and remains disabled.

---

## 7. Verdict

**Historical exploration verdict**: conditional
**Confidence**: 0.75
**Current disposition (2026-07-26)**: named precondition cleared; ready for feature planning

**Rationale**: All three legs converged independently on the same shape at or above the charter's
≥0.7 confidence bar (tech 0.75, value 0.75, risk 0.72), refuting the charter's density deal-killer
for the *achievable* coarsened tuple while confirming the literal 4-field tuple would trigger it
([value-findings.md §5](spikes/value-findings.md)), and confirming the mechanics are a low-risk,
near-zero-blast-radius clone of shipped prior art ([tech-findings.md §1](spikes/tech-findings.md);
[risk-findings.md §6](spikes/risk-findings.md)). At exploration time this satisfied the charter's
`conditional` branch exactly: the cross-repo join was a precondition CCDash could not settle
unilaterally. The 2026-07-26 T1 contract now settles that precondition with version/digest pins,
exact source binding, fail-closed behavior, and explicit guardrail ownership. It does not implement
the CCDash rollup or router merge.

**Recommended next action**: `/plan:plan-feature --tier=2` for the default-off CCDash emission
machinery and separately gated router merge. Live empirical consumption remains disabled until the
router's numeric cap/floor, minimum-sample defense, human-override precedence, protected immunity,
disable path, and provenance tests land.

---

## 8. Citations

- Exploration charter: [proof-to-routing-loop-charter.md](proof-to-routing-loop-charter.md)
- Tech leg SPIKE: [spikes/tech-findings.md](spikes/tech-findings.md) — tuple field capture audit
  (§3); `task_class` derivation candidates and crux (§2); integration points (§4); 10–16 pt estimate
  vs. `aar_reviews` anchor (§5).
- Value leg SPIKE: [spikes/value-findings.md](spikes/value-findings.md) — live DB density query
  (`data/ccdash_cache.db`, 14,399 sessions); coarsened-tuple key counts and threshold-clearing rates
  (§3); deal-killer bottom line (§5).
- Risk leg SPIKE: [spikes/risk-findings.md](spikes/risk-findings.md) — deal-killer partial-trigger
  assessment (§1); risk register (§2); cross-repo seam analysis (§3); Constraint-4 structural
  guarantee (§5); blast-radius confirmation (§6).
- Design spec: [proof-to-routing-loop.md](../../design-specs/proof-to-routing-loop.md) — problem
  statement, tuple sketch, ownership seams, guardrails, and Open Question 1 (`task_class`
  definition) that this exploration was scoped to resolve.
