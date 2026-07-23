---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Proof → Routing Feedback Loop — Feasibility Brief"
status: finalized
created: 2026-07-23
updated: '2026-07-23'
feature_slug: proof-to-routing-loop
verdict: conditional
verdict_confidence: 0.75
exploration_charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
proposed_adr_ref: null
recommended_next_action: "defer-until: shared task_class vocabulary negotiated with delegation-router (MeatySkills/ibm-main); then /plan:plan-feature --tier=2. CCDash-side emission machinery (coarsened tuple) may be built speculatively in parallel."
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
| Literal 4-field tuple triggers the density deal-killer as written (`profile`/`effort_tier`/`model_variant` are 0/14,399 populated) | technical | M | Ship the coarsened `(skill_name-as-task_class × model)` tuple, not the spec's literal tuple — this is forced by data reality, not a design choice ([value-findings.md §2-4](spikes/value-findings.md)) |
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
- **`task_class` = `skill_name`, with an explicit fallback bucket** for non-skill sessions. It is
  the only field that is (a) already captured with no new capture path, (b) a genuine task-type
  label rather than a priority tier or run-instance id, and (c) stable once present. Because
  `skill_name` is null for any session that didn't invoke a named skill, the rollup should surface
  an explicit `_unclassified`/null bucket rather than suppress it — visibility about coverage gaps
  mirrors the AAR contract's "never synthesize a default" precedent
  ([tech-findings.md §2, §6 OQ-3](spikes/tech-findings.md)).
- The net corrected tuple is `(skill_name-as-task_class × model)`, effectively 2-dimensional, not
  the spec's literal 4-dimensional tuple. `provider` may still ride along in the response payload
  for free (derived from `model`) but contributes no independent cardinality.
- The crux this correction does **not** resolve — and cannot resolve from this repo — is whether
  the `skill_name` vocabulary intersects the delegation-router's own `task_class` taxonomy. Unlike
  the AAR contract's routing fields (CCDash-owned enums with nothing to join), `task_class` is
  structurally a join key against an externally-owned, independently-evolving vocabulary
  ([risk-findings.md §3](spikes/risk-findings.md)). No ADR is warranted here: the open decision is
  the shared vocabulary itself, which CCDash cannot settle unilaterally, not an internal
  architectural choice this repo can lock in now.

---

## 7. Verdict

**Verdict**: conditional
**Confidence**: 0.75

**Rationale**: All three legs converged independently on the same shape at or above the charter's
≥0.7 confidence bar (tech 0.75, value 0.75, risk 0.72), refuting the charter's density deal-killer
for the *achievable* coarsened tuple while confirming the literal 4-field tuple would trigger it
([value-findings.md §5](spikes/value-findings.md)), and confirming the mechanics are a low-risk,
near-zero-blast-radius clone of shipped prior art ([tech-findings.md §1](spikes/tech-findings.md);
[risk-findings.md §6](spikes/risk-findings.md)). This satisfies the charter's `conditional` branch
exactly as scoped: `task_class` is derivable CCDash-side (`skill_name`, with a fallback bucket), but
the exact join to the delegation-router's own taxonomy requires a cross-repo vocabulary negotiation
that is unreachable from this repo — a **precondition**, not a settled fact, and not something a
CCDash-side ADR can decide unilaterally ([risk-findings.md §3](spikes/risk-findings.md)). CCDash may
build the emission machinery (schema, worker, endpoint, flag, capability string, coarsened tuple)
speculatively and in parallel — that half is additive and low-risk — but the router must not be
wired to consume `task_class` as a real routing join key until the vocabulary is negotiated,
mirroring how the AAR contract itself was only "locked" once its enum semantics were pinned, not at
first draft.

**Recommended next action**: `defer-until: shared task_class vocabulary negotiated with
delegation-router (MeatySkills/ibm-main); then /plan:plan-feature --tier=2`. CCDash-side emission
machinery (coarsened tuple) may be built speculatively in parallel.

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
