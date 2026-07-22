---
schema_version: 2
doc_type: phase_plan
title: "Phase 5: Cross-Repo Consumer Contract + Transport Decision"
status: draft
created: 2026-07-22
phase: 5
phase_title: "Cross-Repo Consumer Contract + Event Transport Decision"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- Phase 4 sealed and its karen end-of-P2 milestone review passed.
exit_criteria:
- Contract doc cites the PRD §7.3 event schema verbatim.
- D5 transport decision (pull vs push) recorded as an ADR addendum.
- Best-effort cross-repo smoke shows op consuming a real verdict and producing a routed decision with
  NO CCDash code change.
- human_triage_required verdicts never auto-route to op council (asserted in the smoke harness).
---

# Phase 5: Cross-Repo Consumer Contract + Event Transport Decision

**Duration**: ~1 sprint (mostly specification; heavy implementation is out-of-repo)
**Dependencies**: Phase 4 sealed + karen milestone passed
**Assigned Subagent(s)**: `backend-architect` (primary — transport decision + seam contract), `documentation-writer` (secondary — contract doc authoring)
**Points**: 5-8 (decisions block §4 anchor: no RF analogue; heavy op-side implementation is OUT of
this repo — this repo's obligation is the contract + transport decision + smoke harness only)

## Overview

Specify the `op`-side consumer contract end-to-end, even though the consumer *code* lives in the
`agentic_meta_dev`/`op` repo. Resolve decision D5 (does `op` consumption stay PULL via
REST/MCP/CLI as the v1 transport, or does the log-only `aar_review_candidate` event get promoted to a
durable/queued PUSH) from real cross-repo smoke evidence, and record the outcome as an ADR addendum.
This repo's deliverable is the **contract + decision + smoke harness**, not a working `op`
implementation.

**Boundary rationale** (decisions block §1): `op`-side routing must be proven before autonomous
writeback runs unattended in Phase 6 (highest blast radius last).

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T5-001 | Resolve D5 (transport decision) | Evaluate whether the existing PULL path (REST/MCP/CLI, already polled at `op`'s classify→plan→dispatch gate) is sufficient, or whether the log-only `aar_review_candidate` event must be promoted to a durable/queued PUSH. Base the decision on the smoke evidence from T5-004 — do not decide before that evidence exists. | Decision recorded with explicit rationale tied to smoke evidence; defaults to PULL-as-v1 unless smoke proves it insufficient (decisions block §pending default). | 1.5 pt | backend-architect | sonnet | extended | Phase 4 sealed |
| T5-002 | ADR addendum recording D5 | Author an ADR addendum recording the transport decision (T5-001) and its rationale; append to the accepted ADR or a dated addendum file. | Addendum merged; referenced from this plan's `adr_refs`; OQ-6 marked resolved (or explicitly deferred to the Phase 7 DOC-006 design spec if T5-004's smoke was inconclusive). | 0.5 pt | backend-architect | sonnet | adaptive | T5-001 |
| T5-003 | Author cross-repo consumer contract specification | Author a contract specification document (this repo's obligation is contract-fidelity, not implementation) that cites the PRD §7.3 `aar_review_candidate` event schema verbatim, names the routing decision inputs (`correlation.confidence`, `triage_verdict`), and states explicitly that `human_triage_required` verdicts must never auto-route to `op council`. This is the hand-off artifact for the `op`/`agentic_meta_dev` repo team. | Contract doc cites §7.3 field-for-field (no paraphrase drift); routing-decision inputs named exactly as they appear in the reconciled DTO; the `human_triage_required` non-auto-route rule stated as a MUST. | 2 pts | documentation-writer | haiku | adaptive | T5-001 |
| T5-004 | Best-effort cross-repo smoke harness | Build a best-effort smoke harness (in this repo, or a thin script invoking a real `op` instance if available) demonstrating `op` consuming a real `aar_review_candidate`/verdict and producing a routed decision with zero CCDash-side code change required. | Smoke evidence captured (log/transcript) showing consumption + routing; explicitly marked best-effort — a partial/simulated smoke (e.g., mocking `op`'s dispatch gate) is acceptable if a live cross-repo run is unavailable, and must be documented as such. | 2 pts | backend-architect | sonnet | extended | T5-001 |
| T5-005 | Assert `human_triage_required` never auto-routes | Add an assertion (in the smoke harness or a targeted contract test) proving that a `human_triage_required` verdict is never passed to `op council`/ARC by the documented routing contract. | Assertion is testable and green; documented as part of T5-003's contract doc. | 1 pt | backend-architect | sonnet | adaptive | T5-003, T5-004 |

## Structured Acceptance Criteria

#### AC P5.1: Contract doc is a faithful, field-for-field mirror of PRD §7.3
- target_surfaces:
    - docs/project_plans/adrs/
- propagation_contract: The contract spec (T5-003) is the canonical hand-off artifact; the
  `agentic_meta_dev`/`op` repo implementation must reference it rather than re-deriving the schema
  independently (PRD §14 Documentation Acceptance: "do not fork or restate it in the op repo without
  a pointer back here").
- resilience: N/A (documentation-fidelity AC).
- visual_evidence_required: false
- verified_by: [T5-003]

#### AC P5.2: `human_triage_required` never auto-escalates (Hard Invariant #2 extension)
- target_surfaces:
    - docs/project_plans/adrs/
- propagation_contract: The routing-decision table documented in T5-003 explicitly excludes
  `human_triage_required` from any automated `op council`/ARC dispatch path.
- resilience: N/A (invariant AC).
- visual_evidence_required: false
- verified_by: [T5-005]

## Phase 5 Quality Gates

- [ ] D5 transport decision recorded with rationale tied to real smoke evidence (T5-001, T5-002).
- [ ] Contract spec cites §7.3 verbatim; routing inputs named exactly.
- [ ] Cross-repo smoke evidence captured (best-effort acceptable, documented as such).
- [ ] `human_triage_required` non-auto-route assertion green.
- [ ] `task-completion-validator` review passes.

## Phase 5 Success Criteria

All exit criteria in this file's frontmatter are met. Note: this phase's exit criteria intentionally
do NOT require a working `op`-side implementation — only contract-fidelity and best-effort smoke
evidence, per the PRD's explicit "this repo's obligation is the contract, not the implementation"
framing (PRD §6 P3).
