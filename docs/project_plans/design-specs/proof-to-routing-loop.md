---
schema_version: 2
doc_type: design_spec
title: "Proof → Routing Feedback Loop"
status: draft
maturity: shaping
feature_slug: proof-to-routing-loop
prd_ref: null
created: 2026-07-22
updated: 2026-07-22
category: cross-repo-integration
audience: developers
tags:
  - design-spec
  - telemetry
  - rollup
  - routing-feedback
  - backward-pass
  - cross-repo-integration
  - delegation-router
problem_statement: >
  CCDash proves what works, but that proof is observability — a surface a human or agent
  LOOKS AT — not a signal that changes future routing. A route that repeatedly fails, costs
  5x, or regresses keeps getting selected until an agent notices and re-learns the lesson by
  hand. This spec shapes an offline, deterministic rollup CCDash emits per
  (task_class × model × provider × profile) that the delegation-router (MeatySkills repo) can
  ingest as a routing prior — closing the backward pass without ever putting a model on the
  decision path (AOS Constraint 4).
related_documents:
  - agentic_meta_dev/docs/project_plans/meta-plans/aos-backward-pass-initiative.md   # launchpad meta-plan (workstream #6 of "closing the backward pass"); note-form path — lives in the agentic_meta_dev repo, not here
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md         # sibling PULL/no-LLM consumer-contract pattern this reuses
  - docs/project_plans/design-specs/system-metrics-background-rollup.md               # prior rollup-table + config-flag precedent
  # CROSS-REPO CONSUMERS (not specified here — named only):
  #   - delegation-router (MeatySkills repo, branch `ibm-main`) — produces immutable RoutingRecords; would ingest this rollup as a prior
  #   - ~/.claude/config/model-registry.yaml (`scores:` per model) — the §1.5 manual scorecard this feeds as an empirical layer
---

# Proof → Routing Feedback Loop

> Workstream #6 of the AOS "closing the backward pass" initiative. The forward pass
> (idea → route → execute → record) is strong; the backward pass (outcome → learning →
> changed future behavior) is weak. In the layer model, "CCDash proves what works" — this
> spec makes that proof *actuating* instead of merely *legible*.

## 1. Problem Statement

CCDash already ingests rich per-session telemetry: each `AgentSession` carries `modelVariant`
(launch-time model id, e.g. `claude-opus-4-8[1m]`), `modelProvider`, `profile` (launch
profile, e.g. `ica-delegate`), `effortTier`, `launcher`, `skillName`, plus token/cost metrics,
tool usage, and error signals. Feature and AAR-review rollups layer outcome judgments on top.

But all of this is **observability**: a dashboard, a report, an AAR a human or agent reads. The
proof does not feed back into *how the next task is dispatched*. When a given task-class,
dispatched a given way, fails three times, costs 5x, or regresses, nothing mechanically
downweights that route. Instead each freshly-instantiated agent re-discovers the lesson — or
doesn't — and the delegation-router keeps selecting the same losing route because its only
empirical input is the hand-maintained §1.5 scorecard (`model-registry.yaml`), which drifts.

The lesson exists in CCDash's data. It just never changes a decision.

## 2. The Insight: Close the Loop

Make the outcome signal flow **back** into routing, automatically and deterministically:

> A `(task_class × model × provider × profile)` combination that empirically fails / costs more /
> regresses should mechanically DOWNWEIGHT that route as a **prior** the delegation-router reads —
> with no agent re-learning the lesson and no model call at routing time.

CCDash owns the telemetry and the aggregation. The delegation-router owns the decision. The seam
between them is a single, static, deterministically-computed rollup artifact — read, never
model-interpreted. This mirrors the existing **AAR-review consumer contract** exactly: CCDash
produces evidence via a PULL surface; the consumer owns all routing logic; zero LLM on CCDash's
compute path; CCDash never pushes or dispatches.

## 3. Approach Sketch

### 3a. The outcome signal CCDash aggregates

A new rollup keyed on the tuple `(task_class, model, provider, profile)`. Per key, over a
rolling window, derive **only from already-ingested session/feature/AAR rows** (deterministic
aggregation — SQL, thresholds, counts; no inference):

| Field | Source | Meaning |
|---|---|---|
| `sample_count` | count of sessions in window | how much evidence backs this key |
| `success_rate` | feature/AAR verdicts + error signals | fraction of runs that met their bar |
| `cost_index` | token/cost metrics ÷ task-class median cost | relative spend (the "5x" signal) |
| `regression_rate` | AAR regression flags / re-open / rework signals | fraction that regressed |
| `window` / `last_computed_at` | rollup job clock | freshness + decay basis |

The tuple reuses fields CCDash *already captures* on `AgentSession`; only `task_class` is new
(see Open Questions). Computation lives in the transport-neutral
`backend/application/services/agent_queries/` layer, primed by the existing worker
(`backend/worker.py`) — the same shape as `system_metrics.py` rollups and the persisted
`aar_reviews` table, behind a config flag (`CCDASH_ROUTING_ROLLUP_ENABLED`, default `false`)
so the path is opt-in during rollout.

### 3b. The feedback channel CCDash emits (PULL, not push)

A read-only rollup surface, exposed identically across the transport-neutral surfaces CCDash
already uses (REST / MCP / CLI):

```
GET /api/v1/routing/rollup?project_id={id}&task_class={optional}
→ { generated_at, window, keys: [ { task_class, model, provider, profile,
      sample_count, success_rate, cost_index, regression_rate, confidence } ] }
```

Semantics match the AAR-review contract: PULL only (the router polls; CCDash never dispatches),
gated behind `/api/v1/capabilities` (`routing-rollup`) so consumers negotiate rather than
hard-fail, deterministic and stable. The router (or a nightly sync in MeatySkills) fetches and
caches this as a static file — the routing path itself never makes a network or model call.

### 3c. How delegation-router + model-registry `scores:` ingest it

The delegation-router (MeatySkills repo, branch `ibm-main`) treats the rollup as an **empirical
prior layered over the manual §1.5 scorecard** in `~/.claude/config/model-registry.yaml`:

- The hand-authored `scores:` (Cost · Intelligence · Taste · Speed) remain the **defaults**.
- The rollup applies a bounded **adjustment** — e.g. a per-key multiplier or additive nudge —
  when `sample_count` clears the minimum threshold. A route with low `success_rate` /
  high `cost_index` / high `regression_rate` for a task_class is downweighted for *that*
  task_class only; the base scorecard is untouched.
- The router still emits its immutable `RoutingRecord`; the rollup's contribution is recorded in
  the record's provenance so the decision remains auditable ("downweighted: 3 failures / 12
  samples for task_class=code-refactor on ica-sonnet-5").

The exact merge math is the router's to own and is **out of scope here** — this spec defines the
signal and the seam, not the consumer's algorithm.

### 3d. Why this respects Constraint 4

Constraint 4 (no LLM on the render/navigation/decision path) holds by construction:

- **Aggregation is offline + deterministic**: computed by the CCDash worker via SQL/thresholds
  over ingested rows — the same no-LLM guarantee already verified for `aar_review.py`.
- **The router reads a static rollup**: routing consults a cached artifact, a pure lookup — no
  model, no network, at decision time.
- The only model calls in the whole loop are the *original task executions* whose outcomes CCDash
  observed. The learning is arithmetic, not inference.

## 4. Ownership / Seams

| Concern | Owner |
|---|---|
| Session/feature/AAR telemetry ingest | **CCDash** (existing) |
| `(task_class × model × provider × profile)` rollup computation | **CCDash** worker + `agent_queries/` |
| Rollup PULL surface (REST/MCP/CLI + capability gate) | **CCDash** |
| Routing decision, RoutingRecord, prior-merge math | **delegation-router** (MeatySkills, `ibm-main`) |
| Manual scorecard baseline (`scores:`) | `~/.claude/config/model-registry.yaml` |

CCDash produces **evidence only**. It never routes, dispatches, mutates the registry, or writes
RoutingRecords. Same division of labor as the AAR-review consumer contract.

## 5. Guardrails (overfitting / oscillation defense)

An automatic downweight that flips a route on a single bad run, or thrashes back and forth, would
be worse than the status quo. Minimum defenses:

- **Minimum-sample threshold** — a key contributes zero adjustment until `sample_count ≥ N`
  (candidate default: `N` in the 5–10 range, tunable). Below threshold the manual scorecard
  stands alone.
- **Decay / recency weighting** — old outcomes decay so a route that has recovered is not
  penalized forever, and a rolling window bounds memory.
- **Bounded adjustment** — the rollup can nudge, not veto; it cannot drive a route's effective
  score below a floor (prevents starvation, §6).
- **Human-visible + reversible** — every downweight is legible on a CCDash surface *and* stamped
  into the RoutingRecord provenance, never silent. A human override in the registry always wins,
  and disabling the flag reverts instantly to pure-scorecard behavior.

## 6. Open Questions

1. **`task_class` definition** — CCDash does not yet have a first-class `task_class`. Derive it
   from `skillName` / command / feature tier? Adopt the router's own task_class taxonomy so the
   join is exact? A shared vocabulary is the crux of the seam and is unresolved.
2. **Rollup storage** — a new `routing_rollup` table (separation of concern, like `aar_reviews`),
   or a read-time aggregation over existing session rows? Freshness vs. compute cost, same
   trade-off `system-metrics-background-rollup` weighs.
3. **Push vs. pull** — PULL matches the AAR-review contract and keeps CCDash non-actuating. Is a
   nightly export file (router-side cron fetch) enough, or does the router want an on-demand poll?
4. **Cold-start starvation** — a never-yet-tried route has no samples and must not be permanently
   frozen out. The minimum-sample threshold means new routes fall back to the scorecard, but an
   explicit exploration allowance (occasionally route to under-sampled keys) may be needed —
   likely the *router's* responsibility, not CCDash's.
5. **Interaction with the manual scorecard** — is the rollup a strict overlay on `scores:`, or a
   parallel input the router blends? Where does the human-authored default end and the empirical
   prior begin? Must be pinned before the router builds the merge.
6. **Attribution granularity** — cost/regression are cleanly per-session; some outcomes (a
   multi-session feature) are not. How is a shared outcome attributed across the tuples that
   contributed? (Echoes the RF per-provider-split attribution problem, DF-001.)

## 7. Explored Alternatives

- **Manual scorecard tuning (status quo)** — a human periodically edits `model-registry.yaml`
  `scores:` after noticing a bad route. This is exactly the backward-pass gap: it depends on a
  human re-learning the lesson, drifts between edits, and does not scale across task-classes.
  Retained as the *baseline layer* the loop augments, not replaces.
- **Model-on-the-decision-path** — have a model read CCDash telemetry and adjust routing at
  dispatch time. **Rejected** by Constraint 4 (no LLM on the decision path) and by cost/latency:
  a routing decision must be a deterministic lookup. The offline-aggregation design gives the
  same adaptivity without a model in the hot path.

## 8. Success Signal

A `(task_class × model × provider × profile)` route that repeatedly fails / overspends / regresses
is **automatically downweighted** in the next routing decision — no human edit and no agent
re-learning the lesson — and that downweight is **visible** (on a CCDash surface and in the
RoutingRecord provenance) and **reversible** (human override in the registry wins; the config flag
reverts to pure-scorecard behavior). The backward pass is closed for routing: proof changes the
next decision, mechanically.
