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

## Addendum — Phase 1 Locked Decisions (2026-07-22)

Phase 1 implementation surfaced two open items from the exploration set (DTO shape drift from PRD
§7.2, and OQ-2 verdict-gating semantics). Both are now resolved and implemented; this addendum
records the accepted decisions for the historical record. Neither changes the Decision or
Consequences sections above — both are refinements within the existing producer/consumer boundary
and model-free invariant.

1. **D1 — DTO reconciliation (implemented).** The shipped flat/2-value `AARReviewDTO` was
   reconciled to the PRD §7.2 canonical shape: a nested `correlation{strategy, confidence,
   session_ids, feature_id}` object plus a 3-value `triage_verdict` enum
   (`surface_only | deep_review_recommended | human_triage_required`). `schema_version` bumped to 2.
   The OLD flat fields (`session_refs`, `correlation_confidence`, `correlation_strategy`, `verdict`)
   remain present as **deprecated aliases**, auto-synced from the nested values via a pydantic
   `model_validator`, for a one-release deprecation window, then removal. Rationale: the PRD is
   authoritative on shape, and blast radius today is near-zero — this is a log-only event with no
   external consumer yet.

2. **OQ-2 resolution — two-hop confidence gating (implemented as `compute_verdict`).** The
   correlation *strategy* (direct vs two-hop) does **not** by itself force
   `human_triage_required`. Only the confidence *value* / ambiguity gates the verdict, in this
   decision order:
   - (a) `correlation.confidence` missing/null → `human_triage_required` (hard rule).
   - (b) confidence below the 0.64 floor → `human_triage_required`.
   - (c) two-hop correlation resolving multiple candidate sessions with no dominant one (ambiguous
     tie) → `human_triage_required`.
   - (d) otherwise (confidence ≥ 0.64, unambiguous) → deterministic flag mapping: any triggered flag
     → `deep_review_recommended`; no triggered flags → `surface_only`.

   Rationale: OQ-1 prevalence sampling (see
   `.claude/worknotes/ccdash-automated-aar-review/oq1-aar-prevalence.md`) found two-hop is the
   dominant real-world correlation path — 0 of 9 sampled AARs carried a direct session ref.
   Strategy-gating on "two-hop ⇒ always human" would therefore route nearly every real AAR to a
   human and defeat autonomous triage before it starts. The 0.64–1.0 confidence band stays eligible
   for autonomous triage regardless of strategy.

3. **Invariant preserved.** Invariant #1 (zero LLM/model calls on the compute path) holds for both
   decisions above — all verdict logic is deterministic threshold/set/ruleset comparison, the same
   class as `persona_extract_rules.py` R1–R8 (cf. Decision §2, Precedent).

## Addendum — Phase 5: D5 Transport Decision (2026-07-22)

Phase 4 shipped the read-only v1 PULL surface for the persisted `aar_reviews` rollup
(`GET /api/v1/project/aar-review`, `backend/routers/_client_v1_aar_review.py`) and live-verified it
returns 200 with the §7.2 envelope shape (nested `AARReviewListDTO` of `AARReviewDTO`). Phase 5's
scope was to settle the one remaining open transport question from the PRD §6 P3 cross-repo
consumer contract: **how does `op` actually consume `aar_review_candidate` evidence — PULL
(poll the existing REST/MCP/CLI surface) or PUSH (a new queued/durable event CCDash actively
delivers)?** This addendum records that decision for the historical record; it does not change
the Decision or Consequences sections above — it resolves a transport detail strictly within the
existing producer/consumer boundary (Decision §3: *"`op` reads the `aar_review_candidate` event
and decides the route... at its own existing plan gate"*).

1. **D5 — Transport decision (resolved): PULL.** The op-consumption transport for AAR-review
   evidence is the existing REST/MCP/CLI **PULL** path, using the already-shipped v1 endpoint
   (`GET /api/v1/project/aar-review`) as the v1 contract — not a new PUSH/queue/webhook delivery
   mechanism. The log-only `aar_review_candidate` event (`log_aar_review_candidate`,
   `backend/observability/otel.py`) remains exactly what it already is: an observability
   emission, not a delivery transport.

2. **Rationale.**
   - `op` already polls at its own existing plan gate (classify→plan→dispatch per Decision §3) —
     it does not need CCDash to push anything to fit its own control flow; a poll-based read at
     that gate is a strictly smaller, more reversible surface than a new push channel.
   - The v1 PULL endpoint is *built and live-verified* (Phase 4): it returns HTTP 200 with the
     §7.2-shaped envelope (`ClientV1Envelope[AARReviewListDTO]`) today, with zero additional
     CCDash-side work required for a consumer to start reading it.
   - No real external consumer exists yet that has demonstrated PULL is insufficient — `op`'s
     AAR-review-specific consumer subcommand is itself still PRD §6 P3 future work in the
     `agentic_meta_dev`/`op` repo (verified during the Phase 5 smoke: `op --help` exposes no
     AAR-review route today). Building a PUSH/queue transport ahead of a proven need would be
     speculative infrastructure with no consumer to validate it against.
   - PUSH would add a new persisted delivery-state surface (a queue, at-least-once/exactly-once
     semantics, retry/backoff, dead-letter handling) squarely inside CCDash's own blast radius —
     exactly the kind of complexity the Decision (§1–§4) already keeps out of CCDash's
     responsibility by design. PULL keeps CCDash's contribution purely additive: a consumer reads
     when it is ready; CCDash owns no delivery-failure state.
   - This mirrors the existing precedent shape: `council_review_queries.py` is a CCDash-side PULL
     read of ARC state (Precedent, above); this ADR's inverse direction (`op` PULLing CCDash state)
     is the symmetric case, not a new pattern.

3. **Confirming evidence (Phase 5 smoke, T5-004/T5-005).** A best-effort, zero-CCDash-write
   harness (`backend/scripts/aar_review_consumer_smoke.py`) constructed sample `AARReviewDTO`
   payloads — one per `triage_verdict` value — using the real production DTO classes serialized
   exactly as the live endpoint would return them, then applied the PRD §6 P3-documented
   op-side routing rule (route on `correlation.confidence` + `triage_verdict`;
   `human_triage_required` never auto-routes to `op council`/ARC) purely against the pulled JSON
   payload, with zero import of any CCDash compute/service module and zero DB/write access. The
   routing function correctly reproduced the documented contract for all three verdicts, and a
   fuzz assertion (10 confidence values, including `null` and adversarial edge values) confirmed
   `human_triage_required` never resolves to a council/dispatch route regardless of confidence —
   proving the PULL contract carries enough information for a consumer to route safely with zero
   CCDash-side code change.

4. **Trigger condition for revisiting (PUSH promotion).** This decision is deliberately not
   permanent. Promote the log-only `aar_review_candidate` event to a durable/queued PUSH transport
   only if a real consumer later demonstrates, in production, that PULL is insufficient — e.g. an
   observed staleness/latency gap between candidate generation and `op`'s next poll that materially
   delays action on a `deep_review_recommended` item, or a consumer that cannot afford to poll at
   all (an always-on trigger requirement). Until such a concrete, evidenced gap exists, PULL is the
   simpler, already-shipped, already-verified contract and remains the standing decision.

5. **Invariant preserved.** Invariant #2 (CCDash emits only — no dispatch, no writeback, no
   swarm/ARC invocation) holds unchanged: PULL does not grant CCDash any new capability to act on
   its own evidence; it only changes how a consumer *reads* evidence CCDash already computed and
   already exposes today.
