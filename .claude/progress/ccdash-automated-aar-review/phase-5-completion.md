# Phase 5 Completion Note — Cross-Repo Consumer Contract + Event Transport Decision

**Status:** COMPLETED · branch `feat/ccdash-automated-aar-review` · 2026-07-22
**Validator:** task-completion-validator — CHANGES_REQUESTED (contract-spec surface accuracy) → **fixed + re-verified by Opus**.

## What was decided / built
- **D5 = PULL (T5-001/T5-002):** op-consumption transport is the existing REST/MCP/CLI PULL path as the
  v1 contract. Rationale: op already polls at its dispatch gate; the v1 PULL endpoint is built +
  live-verified (P4); no consumer has proven PULL insufficient; PUSH would add delivery-state
  complexity inside CCDash's blast radius (contra the producer/consumer boundary). Recorded as an
  addendum in `…/ccdash-automated-aar-review-proposed-adr.md`, with the explicit trigger condition that
  would later justify PUSH. Invariant #2 (emit-only) unaffected.
- **Cross-repo consumer contract (T5-003 · AC-P5.1):**
  `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md` — cites PRD §7.3
  `aar_review_candidate` schema verbatim; names routing inputs exactly (`correlation.confidence`,
  `triage_verdict`); states prominently that `human_triage_required` MUST NEVER auto-route to op
  council/ARC (§4.2 "THE CRITICAL GUARDRAIL"). **Correction applied:** the initial draft fabricated
  MCP/REST/CLI surface details; corrected to the real shipped shapes — REST list
  `GET /api/v1/project/aar-review` → `ClientV1Envelope[AARReviewListDTO]{project_id,total,reviews}`
  (no pagination), MCP single-doc `ccdash_aar_review(document_id, project_id?)`, CLI single-doc
  `report aar-review --document <id>`; a filtered/paginated list is documented as §1.4 PROPOSED
  (explicitly not shipped). Verified directly by Opus (fabricated identifiers gone / present only in
  negative or PROPOSED context).
- **Smoke harness (T5-004) + non-auto-route assertion (T5-005 · AC-P5.2):**
  `backend/scripts/aar_review_consumer_smoke.py` — simulated-routing mode (op has no AAR-review
  subcommand yet; that's op-side PRD §6 P3 future work). Round-trips real production DTOs through
  `model_dump(mode="json")` (identical to the live endpoint) and routes purely from the payload with
  zero CCDash import of compute/service modules. Asserts `human_triage_required → human_handoff`
  (never op_council/ARC) across 10 confidence values incl. `None`; exit 0. Zero CCDash write/dispatch.

## Verification
- Harness exit 0; AC-P5.2 assertion green across the confidence fuzz set.
- §7.3 citation byte-for-byte verbatim (validator diff = zero).
- Scope: only the ADR addendum + consumer spec + harness changed — no `aar_review.py`/endpoint/models/migration edits.

## Note
The PULL contract works with **zero CCDash-side code change** — a consumer routes safely from what
CCDash already exposes today. op-side consumer implementation is owned by agentic_meta_dev/op (PRD §6 P3).
