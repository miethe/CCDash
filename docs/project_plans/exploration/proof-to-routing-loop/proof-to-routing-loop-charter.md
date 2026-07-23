---
schema_version: 2
doc_type: exploration_charter
title: "Proof → Routing Feedback Loop — Exploration Charter"
status: concluded
created: 2026-07-23
feature_slug: proof-to-routing-loop
timebox_days: 3
hypothesis: "We believe CCDash can emit a deterministic, opt-in (task_class × model
  × provider × profile) rollup that the delegation-router ingests as an empirical
  routing prior — closing the backward pass — because the mechanics clone the already-shipped
  AAR-review PULL/no-LLM consumer contract and the tuple's model/provider/profile
  fields are already captured per-session."
deal_killer: "If CCDash cannot derive a router-joinable task_class from already-captured
  fields, OR real telemetry lacks the per-tuple sample density to ever clear a minimum-sample
  threshold, the rollup emits no actionable signal — abandon."
investigation_legs:
- id: tech
  question: 'Can CCDash compute the (task_class × model × provider × profile) rollup
    deterministically from already-ingested rows, reusing the aar_reviews table +
    system_metrics.py + worker + agent_queries pattern? Specifically: (a) can task_class
    be derived from existing captured fields (skillName/command/feature-tier) with
    no new capture path; (b) are model/provider/profile/effort actually captured per-session
    as the spec claims; (c) enumerate exact integration points and give a story-point
    estimate using aar_reviews as the H5 anchor.'
  assigned_to: spike-writer
- id: value
  question: Does real CCDash telemetry have enough per-tuple sample density that
    a minimum-sample-threshold rollup (candidate N=5–10) would ever emit a 
    non-trivial adjustment — or is every (task_class × model × provider × 
    profile) key too sparse for a single-operator workload, making the signal 
    inert? Inspect the live cache DB schema and, if populated, run 
    count/distinct queries over sessions grouped by the tuple; if unpopulated, 
    assess plausible density structurally.
  assigned_to: data-layer-expert
- id: risk
  question: 'What are the top risks of building the routing rollup + PULL seam? Assess:
    cross-repo coupling risk (consumer is delegation-router in the MeatySkills repo,
    branch ibm-main — NOT visible from this repo; is a spec-only seam contract sufficient?);
    overfitting/oscillation defense adequacy (§5 min-sample / decay / bounded adjustment);
    attribution granularity for multi-session outcomes (OQ6); Constraint-4 preservation;
    blast radius on CCDash. Confirm or refute the charter deal-killer and surface
    any additional deal-killers.'
  assigned_to: backend-architect
verdict_criteria:
  go:
  - 'tech leg: task_class is derivable from captured fields AND model/provider/profile
    confirmed captured; confidence >= 0.7'
  - 'value leg: a plausible path to per-tuple sample density above threshold exists;
    confidence >= 0.7'
  - 'risk leg: risks have concrete mitigations and the deal-killer is refuted; confidence
    >= 0.7'
  no_go:
  - 'Deal-killer triggered: no router-joinable task_class derivable, OR telemetry
    provably too sparse to ever clear threshold'
  - tech leg reports infeasibility with confidence >= 0.8
  conditional:
  - task_class is derivable CCDash-side but the exact join to the router's 
    task_class taxonomy requires a cross-repo contract negotiation (unreachable 
    from this repo) before build — name that as the concrete precondition
verdict: conditional
verdict_rationale: "All three legs converged independently at/above the 0.7 bar (tech
  0.75, value 0.75, risk 0.72). Mechanics are a low-risk, near-zero-blast-radius clone
  of the shipped AAR-review rollup (Constraint-4 held structurally; ~10-16 pts). The
  spec's literal 4-field tuple is not viable — provider is derived-not-captured; profile/effort_tier/model_variant
  are write-path-dead (0/14,399 sessions) — but the achievable coarsened tuple (skill_name-as-task_class
  x model) refutes the density deal-killer (~52% of keys clear N>=5 in a 30-day window).
  Crux is unresolvable from this repo: task_class is a join key against the delegation-router's
  externally-owned taxonomy (MeatySkills/ibm-main). Precondition: negotiate the shared
  task_class vocabulary before the router consumes the join key; CCDash-side emission
  machinery may be built speculatively in parallel."
output_artifacts: []
updated: '2026-07-23'
---

# Proof → Routing Feedback Loop — Exploration Charter

## Hypothesis Context

CCDash already ingests per-session `modelVariant`, `modelProvider`, `profile`, `effortTier`,
`launcher`, `skillName`, plus token/cost and error signals, and layers feature/AAR outcome
verdicts on top. The design spec (`docs/project_plans/design-specs/proof-to-routing-loop.md`,
maturity `shaping`) proposes turning that observability into an *actuating* signal: a
deterministic rollup the delegation-router reads as a routing prior, closing the AOS "backward
pass" (workstream #6). The mechanics are a near-exact clone of the shipped AAR-review consumer
contract (PULL surface, no LLM on the compute path, capability-gated, default-off flag). What is
**unproven** is the crux the spec itself flags as unresolved (Open Question 1): whether a
`task_class` that *joins to the router's taxonomy* can be derived from CCDash's captured data,
and whether real single-operator telemetry is dense enough per tuple for the signal to be
anything but inert.

---

## Investigation Legs

### Leg: tech — Technical Feasibility (with folded prior-art)

**Question**: (see frontmatter `tech`)
**Assigned to**: `spike-writer`
**Expected output**: `docs/project_plans/exploration/proof-to-routing-loop/spikes/tech-findings.md`

- Confirm the tuple fields (`model`, `provider`, `profile`, `effort`) are genuinely captured per-session (verify against `sessions` DDL / capture columns, not the spec's claim).
- Assess `task_class` derivation options: `skillName`, command, feature tier — and whether any yields a stable, router-joinable class.
- Enumerate integration points: worker priming, `agent_queries/` service, rollup storage (new table vs read-time aggregation, OQ2), REST/MCP/CLI PULL surface, `/api/v1/capabilities` gate, config flag `CCDASH_ROUTING_ROLLUP_ENABLED`.
- H5 anchor: `aar_reviews` rollup + AAR-review consumer contract (shipped 7d96c3e). Give a story-point estimate and justify any delta.

### Leg: value — Data-Signal Viability

**Question**: (see frontmatter `value`)
**Assigned to**: `data-layer-expert`
**Expected output**: `docs/project_plans/exploration/proof-to-routing-loop/spikes/value-findings.md`

- Inspect the cache DB (`data/ccdash_cache.db`) schema and row counts if populated.
- Group sessions by `(task_class-proxy × model × provider × profile)` and report the distribution of per-key sample counts against candidate threshold N=5–10.
- If the DB is empty/absent, assess structurally: given single-operator usage, is the tuple space too wide (cardinality explosion) for keys to accumulate samples?

### Leg: risk — Risk / Blast Radius / Cross-Repo Seam

**Question**: (see frontmatter `risk`)
**Assigned to**: `backend-architect`
**Expected output**: `docs/project_plans/exploration/proof-to-routing-loop/spikes/risk-findings.md`

- Cross-repo coupling: the consumer (delegation-router) lives in MeatySkills/`ibm-main`, invisible here. Is a spec-only seam contract (mirroring the AAR-review consumer contract) sufficient, or is a live join needed pre-build?
- Overfitting/oscillation (§5), attribution granularity (OQ6), Constraint-4 preservation, CCDash-side blast radius.
- Explicitly confirm or refute the charter `deal_killer`.

---

## Verdict Criteria Narrative

**Go** if: `task_class` is derivable and router-joinable, the tuple fields are confirmed captured,
a plausible path to per-key sample density above threshold exists, and risks carry concrete
mitigations with the deal-killer refuted (all legs ≥ 0.7).

**No-go** if: the deal-killer fires — no router-joinable `task_class`, or telemetry provably too
sparse to ever clear the minimum-sample threshold — or the tech leg reports infeasibility ≥ 0.8.

**Conditional** if: CCDash *can* derive `task_class` and build the rollup, but the exact join to
the router's own `task_class` taxonomy needs a cross-repo contract negotiation (unreachable from
this repo) before implementation. The precondition names that negotiation as the next step.

---

## Out of Scope

- The delegation-router's prior-merge math / adjustment algorithm (explicitly the router's, per spec §3c).
- Any push/dispatch behavior — CCDash produces evidence only, never routes.
- Editing `~/.claude/config/model-registry.yaml` or the router repo.

---

## Citations / Prior Art

- Design spec: `docs/project_plans/design-specs/proof-to-routing-loop.md` (maturity: shaping)
- Sibling PULL/no-LLM pattern: `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`
- Rollup-table + config-flag precedent: `docs/project_plans/design-specs/system-metrics-background-rollup.md`
- Shipped H5 anchor: AAR review loop (`aar_reviews` table, merge 7d96c3e); `docs/guides/aar-review-loop.md`

---

## Notes

- 2026-07-23: Charter scaffolded via `/plan:explore`. 3 legs (tech + value + risk); prior-art folded into tech (strong internal H5 anchor). Timebox 3 days.
