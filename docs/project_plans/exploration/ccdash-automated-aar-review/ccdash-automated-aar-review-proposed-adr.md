---
schema_version: 2
doc_type: adr
title: "CCDash is the producer of AAR-review evidence; op/ARC/SkillMeat own synthesis, swarm dispatch, and writeback"
status: accepted
created: 2026-07-21
updated: 2026-07-21
feature_slug: ccdash-automated-aar-review
exploration_charter_ref: docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-charter.md
related_documents:
  - docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-feasibility-brief.md
---

# ADR (Proposed): CCDash is the Producer of AAR-Review Evidence

**Status**: accepted (upgraded from proposed on the `go` exploration verdict + human sign-off, 2026-07-21)

## Context

The AOS produces AARs everywhere, but the loop from *post-hoc AAR* to *acted-upon system
improvement* (new/swapped skill or agent, config change) exists nowhere. `op story` already sources
AARs from CCDash (`ccdash report aar --feature`) but terminates in a **blog draft PR** — a
categorically different sink from a system-improvement recommendation (reuse-findings §3). The user
framed the desired loop as "ARC-driven": sessions auto-triaged into either a cheap surface-review or
a full ARC swarm deep-dive, with recommendations routed back through `op`/SkillMeat.

The seam question this ADR settles: **where does CCDash's responsibility end and op/ARC/SkillMeat's
begin?** The load-bearing risk is that "ARC-driven" is misread as "CCDash orchestrates ARC," which
would put an LLM on CCDash's recall path, hand CCDash a cost-explosion surface it does not own, and
create an autonomous-writeback path that bypasses existing HITL gates (risk-findings §1–§2).

## Decision

1. **Producer/consumer boundary.** CCDash produces *evidence + AAR↔session correlation + deterministic
   triage flags + a triage verdict DTO*. `op`/ARC/SkillMeat consume it and own *all* model-driven
   synthesis, swarm/ARC dispatch, artifact creation, and gated writeback.
2. **Model-free on the CCDash side.** All triage computation is deterministic (threshold/lookup/regex
   over already-ingested DB rows) — the same class as `persona_extract_rules.py` R1–R8. **No LLM on
   the recall/read path.** If establishing a flag requires semantic judgment, that flag is not a
   triage flag; it belongs to the synthesis tier upstream.
3. **CCDash emits a model-free producer event**, mirroring the RF→CCDash `ccdash_event.yaml`
   writeback pattern in reverse. `op` reads the `aar_review_candidate` event and decides the route
   (surface note vs `op council`/ARC) **at its own existing plan gate**.
4. **All gates stay upstream.** CCDash never calls the swarm, never runs ARC, never mutates the
   SkillMeat catalog, never writes to skills/agents. Every irreversible action goes through op's
   HITL gate, story's approve gate, ARC's validate gate, or IntentTree's AgentRun gate.

## Consequences

**Positive**: Clean seam matching three in-repo precedents; cost control and blast radius stay with
the subsystems that own them; CCDash's contribution is additive and reversible; the MVP ships with no
new ingest, no writeback, no scheduling. **Negative / accepted**: CCDash cannot "close the loop" by
itself — a consumer (op) must act on the event for value to land; low-confidence correlations route
to human triage rather than auto-escalating (accepted, per risk-findings §4). **Follow-on
obligations**: any persisted triage state is a new write path subject to ADR-007 (`retry_on_locked`,
direct-count assertion test, dual SQLite+PG DDL); triage input must consume redaction-passed
`session_detail` output, never raw JSONL.

## Alternatives Considered

- **CCDash as orchestrator (rejected).** Have CCDash auto-dispatch ARC swarm deep-dives and write
  recommendations back into SkillMeat/skills/agents directly. Rejected because it (a) puts LLM calls
  on CCDash's recall path (violates the hardest AOS constraint), (b) hands CCDash a cost-explosion and
  unbounded-recursion surface it does not own — an AAR-review session is itself a session and would
  re-enter triage (risk-findings §1), and (c) creates autonomous writeback bypassing every existing
  HITL gate (charter Out-of-Scope). The producer/consumer split delivers the same user outcome while
  keeping each risk with its current owner.

## Precedent

- **`ccdash persona extract`** — producer-only; reconcile/dedup/gate/writeback stay upstream in the
  persona bank. CCDash emits a model-free candidate; agentic_meta_dev owns the model calls (CLAUDE.md;
  contracts/persona.md:35). This ADR applies the identical shape to review triage.
- **`council_review_queries.py`** — CCDash *reads* ARC council-review state (capability-gated on
  `ARC_ENABLED`, empty-state when off); it never invokes or writes ARC outcomes.
- **RF→CCDash event writeback** — `rf writeback` emits a structured `ccdash_event.yaml` consumed by
  CCDash (commit 9594fcc). This ADR inverts that established contract: CCDash emits the event, `op`
  consumes it.
