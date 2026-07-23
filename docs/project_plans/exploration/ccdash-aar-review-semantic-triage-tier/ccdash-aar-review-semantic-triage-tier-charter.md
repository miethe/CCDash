---
schema_version: 2
doc_type: exploration_charter
title: "CCDash AAR Review — Autonomous Semantic-Triage Tier (v2) — Exploration Charter"
status: concluded
created: 2026-07-23
feature_slug: ccdash-aar-review-semantic-triage-tier
timebox_days: 3
hypothesis: "We believe a seam-preserving, opt-in semantic-triage job lane close to
  CCDash's data is worth building because data locality (CCDash already holds the
  full session/plan/artifact graph) makes a cheap local semantic pre-filter cheaper
  than shipping all evidence to op per candidate — provided the model lane stays provably
  off the deterministic read/recall path."
deal_killer: "If the semantic-triage tier should be owned by op (single synthesis
  owner) rather than CCDash — i.e., data-locality does not justify a CCDash-hosted
  or CCDash-adjacent model lane — then v2 collapses into an op-side feature and CCDash
  builds nothing new. Abandon the CCDash-side build."
investigation_legs:
- id: tech
  question: Is a seam-preserving semantic-triage job lane (alt B CCDash-hosted 
    vs alt C CCDash-adjacent worker over the API) technically feasible with the 
    model lane PROVABLY off the read/recall/compute path? Identify integration 
    points, the process/deployment separation mechanism (OQ-B), and a rough 
    story-point estimate anchored on v1's worker lane.
  assigned_to: ica-executor
- id: risk
  question: "What are the top risks — chiefly blast radius on Hard Invariant #1 (no-LLM-on-recall-path),
    cost/quota governance, and interaction with v1's 3 self-recursion guards (OQ-C)?
    Assess and rule on the deal_killer: does data locality justify a CCDash-side lane,
    or should op own it (OQ-A)?"
  assigned_to: ica-executor
- id: value
  question: Which semantic signals are actually worth a model pass (value vs 
    token cost, OQ-D)? Do the signals currently lost at the CCDash layer 
    (claimed-outcome-vs-transcript mismatch, subtly-wrong-but-successful 
    agent/skill choice, evidence-only recommendations) cause measurable pain 
    today, and how often would each fire?
  assigned_to: ica-executor
- id: priorart
  question: Does the existing ARC (op council) pipeline already provide the 
    'capable model' rung (OQ-E)? Survey internal precedent (v1 AAR loop, ARC, op
    ownership boundary) and any external prior art for LLM-assisted post-hoc 
    triage. Is CCDash building something new, or does op already own this 
    capability?
  assigned_to: ica-executor
verdict_criteria:
  go:
  - All investigation legs report confidence >= 0.7
  - 'Deal-killer NOT triggered: data locality demonstrably justifies a CCDash-side
    (B or C) lane over op ownership'
  - A provably-off-read-path separation mechanism exists (OQ-B answered)
  no_go:
  - 'Deal-killer triggered: op should own the semantic tier; CCDash builds nothing
    new'
  - Risk leg reports no viable way to keep the model lane off the recall path 
    with confidence >= 0.8
  conditional:
  - Ownership resolves toward CCDash-adjacent (alt C) but a specific 
    precondition (e.g. v1 P2–P4 landed, or a cost-governance mechanism) must 
    hold first
verdict: no-go
verdict_rationale: "All four legs converge on no-go for a CCDash-side build. Risk
  (0.82) CONFIRMS the deal-killer: op should own the semantic tier — the data-locality
  premise is quantitatively false (tiny deterministic-flag-survivor set; a live /api/v1/project/aar-review
  endpoint already handles transport), while a CCDash-hosted model lane converts Hard
  Invariant #1 from a structural property into a permanent fragile reachability check.
  Priorart (0.82): the capable-model rung already exists as ARC/council-review (the
  v1-P3 destination) — REUSE not build; only a narrow cheap-model pre-filter is unowned,
  and op has no locality disadvantage for it. Value (0.55): that residual pre-filter
  is thin (only 2 of 5 signals clear value>cost, narrowly scoped). Tech (0.82): Alt
  C is feasible-with-constraints, but feasibility is not desirability. CCDash builds
  nothing new; the residual is an op-side feature consuming CCDash's existing aar_review_candidate
  API."
output_artifacts: []
updated: '2026-07-23'
---

# CCDash AAR Review — Autonomous Semantic-Triage Tier (v2) — Exploration Charter

## Hypothesis Context

v1's AAR↔session triage is deterministic-only by design (Hard Invariant #1: no LLM on CCDash's
read/recall/compute path). Signals needing semantic judgment — a claimed outcome not matching the
transcript, a subtly-wrong "successful" agent/skill choice, an evidence-only recommendation — are
lost at the CCDash layer unless op happens to look. v2 proposes a separate, opt-in, flag-gated
SYNTHESIS job lane (deterministic pre-filter → cheap-model semantic pass → capable-model escalation,
output only through existing op gates). The load-bearing question is *ownership*: CCDash (data
locality) vs op (single synthesis owner). This exploration exists to answer that before any tier
classification or PRD.

---

## Investigation Legs

### Leg: tech — Technical Feasibility (OQ-B)
**Question**: See frontmatter. **Assigned to**: `ica-executor` (routed via delegation-router)
**Expected output**: `spikes/tech-findings.md`
- Alt B (CCDash-hosted job lane) vs alt C (CCDash-adjacent worker over the v1 API) separation mechanisms
- How to prove the model lane never sits on any op/ARC/FE query path (process/deployment separation)

### Leg: risk — Risk / Blast Radius + Deal-Killer (OQ-A, OQ-C)
**Question**: See frontmatter. **Assigned to**: `ica-executor`
**Expected output**: `spikes/risk-findings.md`
- Blast radius on Hard Invariant #1; cost/quota governance; v1's 3 self-recursion guards
- Explicit ownership ruling: confirm or refute the deal_killer

### Leg: value — Value / Desirability (OQ-D)
**Question**: See frontmatter. **Assigned to**: `ica-executor`
**Expected output**: `spikes/value-findings.md`
- Enumerate candidate semantic signals; estimate fire-frequency and value vs token cost

### Leg: priorart — Comparable Prior Art (OQ-E)
**Question**: See frontmatter. **Assigned to**: `ica-executor`
**Expected output**: `spikes/priorart-findings.md`
- Does ARC / op council already provide the capable-model rung? Internal + external precedent

---

## Verdict Criteria Narrative

**Go** if legs converge (confidence ≥ 0.7), the deal-killer is refuted (data locality justifies a
CCDash-side B/C lane), and a provably-off-read-path mechanism exists.
**No-go** if op should own the tier, or no separation mechanism keeps the model lane off the recall
path with high confidence.
**Conditional** if ownership tilts CCDash-adjacent (alt C) but a named precondition (v1 P2–P4 landed;
cost-governance in place) must resolve first.

---

## Out of Scope

- Implementing any semantic-triage code (this is pre-commitment exploration only)
- Re-litigating v1's deterministic seam ADR (accepted; v2 must not fold into v1)
- Model selection tuning beyond the cheap→capable ladder shape

---

## Citations / Prior Art

- `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md`
- `docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md`
- `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md`
- Design spec: `docs/project_plans/design-specs/ccdash-aar-review-semantic-triage-tier.md`

---

## Notes

- 2026-07-23: Charter scaffolded via `/plan:explore`. Legs routed through `/delegation-router`; all four leaves dispatched to ICA (`ica-executor` / `~/ica-claude.sh --bare`) per operator instruction.
