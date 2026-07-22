---
schema_version: 2
doc_type: phase_plan
title: "Phase 2: Full-Metadata Evidence Enrichment"
status: draft
created: 2026-07-22
phase: 2
phase_title: "Full-Metadata Evidence Enrichment"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- Phase 1 sealed (reconciled DTO + `aar_reviews` persistence live; contract test + parity + direct-count green).
exit_criteria:
- Each of the 4 shipped flags' evidence carries concrete plan/task/session-metadata references (not
  just session ids).
- Unit-tested over fixtures covering the enrichment traversal's deterministic paths.
- A test asserts NO model client is importable/invoked on the compute path (Hard Invariant #1).
---

# Phase 2: Full-Metadata Evidence Enrichment

**Duration**: ~1 sprint
**Dependencies**: Phase 1 sealed
**Assigned Subagent(s)**: `python-backend-engineer` (primary — implementation), `backend-architect` (secondary — deterministic traversal design)
**Points**: 5-7 (decisions block §4 anchor: H3 algorithmic-service flag — doc→feature→plan→task
traversal + deterministic flag sharpening qualifies at >=3 pts; new enrichment service + fixtures)

## Overview

Build a deterministic enrichment layer over `session_detail` (tokens, `context_window`,
detection/capture columns, subagents, artifacts, links) plus a doc→feature→plan/progress→task
frontmatter traversal (`acceptance_criteria`, `assigned_to`, `assigned_model`, `effort`, `phase`).
This layer **sharpens** the 4 shipped flags with richer, plan/task-anchored `evidence_refs` and
`triage_reasons` — it does not introduce new semantic verdicts (D2).

**Boundary rationale** (decisions block §1): session/plan-metadata evidence is a prerequisite for the
Phase 3 SkillMeat correlation (the 5th flag reads both used-artifacts *and* the task-domain context
this phase's enrichment surfaces build).

## Deterministic Rule Annotations (OQ-7 compliance — mandatory per task)

Every enrichment comparison below MUST be one of: set-membership, threshold, or static-ruleset
lookup. Any comparison an implementer finds requires semantic judgment ("was this the *right*
choice") is **out of scope** for this phase — descope it and record the finding, per Hard Invariant
#1; it belongs to the synthesis tier upstream (op/ARC).

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T2-001 | Design evidence-contract + traversal | Design the deterministic doc→feature→plan/progress→task frontmatter traversal and the shape of the enrichment evidence contract (what fields each flag's `evidence_refs`/`triage_reasons` may cite). Document the ruleset explicitly (no free-text judgment fields). | Design doc/comment captures the exact traversal path + evidence-field contract; reviewed against Hard Invariant #1 before implementation begins. | 1.5 pt | backend-architect | sonnet | extended | Phase 1 sealed |
| T2-002 | Implement `session_detail` enrichment reads | Implement the enrichment service's reads over `session_detail` (tokens, `context_window`, detection/capture columns, subagents, artifacts, links) — consuming the redaction-passed output exclusively, never raw JSONL (Hard Invariant #4). | Enrichment reads use `session_detail.py`'s public surface only; no raw JSONL file read introduced. | 1.5 pt | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-003 | Implement plan/task frontmatter traversal | Implement the doc→feature→plan/progress→task traversal, extracting `acceptance_criteria`, `assigned_to`, `assigned_model`, `effort`, `phase` from linked plan/progress frontmatter via existing `document_linking.py`/`entity_links` reads (D6 — no new port). | Traversal resolves for fixture docs with a linked plan/task; returns empty (not an error) when no link exists. | 1.5 pt | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-004 | Sharpen `context_ballooning` with plan/task evidence | Attach plan-declared `effort`/`phase` context to the flag's evidence when the linked task frontmatter is available; deterministic threshold logic is unchanged from P1. | Evidence includes the linked task id/phase when resolvable; flag logic itself is unchanged (sharpening evidence only, per D2). | 1 pt | python-backend-engineer | sonnet | adaptive | T2-002, T2-003 |
| T2-005 | Sharpen `missing_artifacts` with plan/task `acceptance_criteria` | Compare the AAR-claimed artifacts against the linked task's `acceptance_criteria`/`files_affected` frontmatter (set-difference), in addition to the existing `session_artifacts` diff. | Evidence names both the session-artifact gap and any unmet task-frontmatter AC reference, when resolvable; falls back to P1 behavior when no plan/task link exists. | 1 pt | python-backend-engineer | sonnet | adaptive | T2-002, T2-003 |
| T2-006 | Sharpen `generic_agent_vs_specialist` with `assigned_to`/`assigned_model` | Compare the session's actual `agentsUsed`/`skill_name` against the linked task's `assigned_to`/`assigned_model` frontmatter (set-membership comparison: did the session use what the plan assigned?). Static keyword→specialist lookup from P1 remains the fallback when no plan link exists. | Evidence states both P1's generic-agent trigger and any assigned-vs-actual mismatch, when resolvable. | 1 pt | python-backend-engineer | sonnet | adaptive | T2-002, T2-003 |
| T2-007 | Sharpen `stack_ineffectiveness` with `phase`/`effort` correlation | Correlate the linked task's declared `phase`/`effort` against observed failure/retry density (threshold comparison, unchanged derivation) to add context to the evidence, not new logic. | Evidence names the linked phase/effort context when resolvable; flag trigger logic unchanged from P1. | 1 pt | python-backend-engineer | sonnet | adaptive | T2-002, T2-003 |
| T2-008 | No-LLM compute-path assertion test (Hard Invariant #1) | Ship a test that statically asserts no LLM/model-client import (Anthropic SDK, OpenAI SDK, any `Task`/`Agent` dispatch helper) exists anywhere in `aar_review.py` or its enrichment-module dependency graph. | Test fails if any such import is introduced; runs as part of the standard test suite, not a manual grep. | 1 pt | python-backend-engineer | sonnet | adaptive | T2-004, T2-005, T2-006, T2-007 |
| T2-009 | Enrichment fixture suite | Build/extend fixtures covering: doc with a linked plan/task vs doc with no link; each flag's sharpened-evidence path vs its P1 fallback path. | Fixture suite is unit-tested and green; covers both linked and unlinked cases for all 4 flags. | 1 pt | python-backend-engineer | sonnet | adaptive | T2-004, T2-005, T2-006, T2-007 |

## Structured Acceptance Criteria

#### AC P2.1: No LLM/semantic judgment anywhere on the compute path (Hard Invariant #1)
- target_surfaces:
    - backend/application/services/agent_queries/aar_review.py
- propagation_contract: The static-import assertion test (T2-008) runs as part of the standard test
  suite; a code-review gate explicitly checks this invariant on every subsequent phase's diff to
  `aar_review.py` and its dependency graph.
- resilience: N/A (invariant AC, not a resilience AC).
- visual_evidence_required: false
- verified_by: [T2-008]

#### AC P2.2: Enrichment consumes only redaction-passed `session_detail` (Hard Invariant #4b)
- target_surfaces:
    - backend/application/services/agent_queries/aar_review.py
    - backend/application/services/agent_queries/session_detail.py
- propagation_contract: All enrichment reads route through `session_detail.py`'s public,
  redaction-applied output; no new raw-JSONL file read is introduced anywhere in the enrichment
  module.
- resilience: If a session's `session_detail` output has redacted/absent fields, the enrichment layer
  treats the absence as "insufficient data for this evidence point" — never an error, never a fallback
  to raw-file access.
- visual_evidence_required: false
- verified_by: [T2-002, task-completion-validator manual check]

## Phase 2 Quality Gates

- [ ] All 4 flags carry sharpened, plan/task-anchored evidence when a link is resolvable.
- [ ] All 4 flags fall back cleanly to P1 behavior when no plan/task link exists (never an error).
- [ ] No-LLM compute-path test (T2-008) green.
- [ ] Fixture suite (T2-009) green, covering linked and unlinked cases.
- [ ] `task-completion-validator` review passes.

## Phase 2 Success Criteria

All exit criteria in this file's frontmatter are met. Phase 3's SkillMeat linkage may begin once the
enrichment evidence contract (T2-001) is frozen — task-level scaffolding of Phase 3 may start in
parallel per the plan's Parallel Work Opportunities note, but Phase 3 does not formally close until
this phase is sealed.
