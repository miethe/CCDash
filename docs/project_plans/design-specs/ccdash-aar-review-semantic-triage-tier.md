---
schema_version: 2
doc_type: design_spec
maturity: idea
title: "CCDash AAR Review — Autonomous Semantic-Triage Tier (v2)"
status: draft
created: 2026-07-22
updated: 2026-07-22
feature_slug: ccdash-aar-review-semantic-triage-tier
problem_statement: "v1's AAR↔session triage service is deliberately deterministic-only (Hard Invariant #1: no LLM on CCDash's read/recall/compute path), so signals that require semantic judgment — a claimed outcome not matching what the transcript actually did, a subtly-wrong-but-'successful' agent/skill choice, a recommendation only visible from reading the full evidence — are lost at the CCDash layer unless op happens to look."
open_questions:
- "OQ-A: CCDash vs op ownership of the semantic-triage tier (the deal-killer)."
- "OQ-B: How to keep the model lane provably OFF the read path (process/deployment separation)?"
- "OQ-C: Cost/quota governance + interaction with v1's 3 self-recursion guards."
- "OQ-D: Which semantic signals are worth a model pass (value vs. token cost)?"
- "OQ-E: Does this reuse ARC (op council) rather than a bespoke capable-model call — i.e., is the 'capable model' rung just the existing ARC pipeline?"
explored_alternatives:
- "A) Keep v1 as-is; op owns 100% of model work (status quo — the seam-purity option)."
- "B) CCDash-hosted semantic-triage job lane (this spec)."
- "C) CCDash-adjacent but separate service/worker that reads CCDash over the API (middle ground; preserves recall-path purity without embedding models in CCDash's process)."
related_documents:
- docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
- docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
- docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
prd_ref: null
---

# CCDash AAR Review — Autonomous Semantic-Triage Tier (v2)

## Context

The shipped + planned CCDash Automated AAR Review Loop (v1, P1 shipped; P2–P4 planned)
deliberately keeps ALL model work OUT of CCDash. Hard Invariant #1 = no LLM on CCDash's
read/recall/compute path; per the accepted seam ADR, CCDash is the deterministic evidence +
detection layer and op/ARC own all model-driven synthesis, dispatch, and recommendation. This
embodies the AOS constraints "no LLM on the recall path" and "cheap extract → expensive
synthesize."

## Problem statement

Because every semantic judgment is pushed upstream, signals that CANNOT be computed
deterministically are effectively lost at the CCDash layer unless op happens to look. The PRD
itself concedes this: "any flag needing semantic judgment ('was this agent choice wrong') is not
a triage flag." Example signals a deterministic rule cannot catch: the AAR's claimed outcome not
matching what the session transcript actually did; a subtly-wrong agent/skill choice that still
"succeeded"; a recommendation that only a model reading the full evidence could surface. v1 gives
op the raw evidence but no cheap semantic pre-filter close to the data.

## Proposed shape (v2) — the escalation ladder, seam-preserving

A SEPARATE, opt-in, flag-gated autonomous SYNTHESIS JOB LANE — architecturally distinct from the
deterministic read path (must never sit on any query op/ARC/the FE call):

1. Deterministic layer (v1's flags/worker) is the cheap pre-filter — free, deterministic, better
   than a model for the mechanical part.
2. On cadence OR on deterministic-flag-tripped candidates, a cheap model (e.g. Haiku) does a
   bounded SEMANTIC pass over the already-ingested, redaction-passed evidence.
3. Only survivors escalate to a capable model for full-data review + draft recommendations.
4. Output is enriched candidate events / draft recommendations emitted ONLY through the existing
   gates (op approve; never CCDash-initiated writeback; cost/quota-governed; same self-recursion
   guards as v1 P6).

## Why v2, not folded into v1

It crosses an AOS hard constraint (no-LLM-on-recall-path), so it needs its own exploration +
verdict rather than being bolted onto the shipping deterministic seam. v1 (P2–P4) should land
first and stay lean.

## Deal-killer candidate (for the explore charter)

The load-bearing question: SHOULD this semantic tier live in CCDash at all, or in op? CCDash's
case = data locality (it already holds the full session/plan/artifact graph; shipping all of it
to op per candidate is wasteful). op's case = single synthesis owner + keeps CCDash a pure
deterministic recall surface. If the answer is "op should own it," this v2 collapses into an
op-side feature and CCDash builds nothing new — that is the deal-killer to test.

## Explored alternatives

- A) Keep v1 as-is; op owns 100% of model work (status quo — the seam-purity option).
- B) CCDash-hosted semantic-triage job lane (this spec).
- C) CCDash-adjacent but separate service/worker that reads CCDash over the API (middle ground;
  preserves recall-path purity without embedding models in CCDash's process).

## Open questions (seed the explore legs)

- OQ-A: CCDash vs op ownership (the deal-killer).
- OQ-B: How to keep the model lane provably OFF the read path (process/deployment separation)?
- OQ-C: Cost/quota governance + interaction with v1's 3 self-recursion guards.
- OQ-D: Which semantic signals are worth a model pass (value vs. token cost)?
- OQ-E: Does this reuse ARC (op council) rather than a bespoke capable-model call — i.e., is the
  "capable model" rung just the existing ARC pipeline?
