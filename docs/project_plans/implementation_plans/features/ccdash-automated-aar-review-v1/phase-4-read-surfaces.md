---
schema_version: 2
doc_type: phase_plan
title: "Phase 4: Read Surfaces — FE Panel + v1 LAN Endpoint"
status: draft
created: 2026-07-22
phase: 4
phase_title: "Read Surfaces: FE Panel + v1 LAN Endpoint + Capability"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
integration_owner: python-backend-engineer
ui_touched: true
target_surfaces:
- components/Planning/FeatureAARReviewPanel.tsx
entry_criteria:
- Phase 3 sealed (full 5-flag + reconciled verdict exists).
exit_criteria:
- FE panel renders all 3 triage_verdict states and is null-resilient on every optional §7.2 field.
- v1 LAN endpoint returns the persisted verdict (redaction-applied), reusing @memoized_query.
- aar-review capability string advertised at /api/v1/capabilities.
- Runtime smoke recorded (browser + endpoint) per CLAUDE.md's Runtime smoke gate convention.
---

# Phase 4: Read Surfaces — FE Panel + v1 LAN Endpoint + Capability

**Duration**: ~1 sprint
**Dependencies**: Phase 3 sealed
**Assigned Subagent(s)**: `ui-engineer-enhanced` (FE, primary), `python-backend-engineer` (v1 endpoint, primary)
**Points**: 4-6 (decisions block §4 anchor: prior planning-surface read panels ~4 pts + v1 endpoint
plumbing, H6 hidden-plumbing budget)
**Integration Owner**: `python-backend-engineer` (owns the DTO-field → panel + v1-payload seam per R-P3 — this phase has FE + BE overlap with file-ownership split: `.tsx` ∥ `client_v1.py`)

## Overview

Ship the first human-visible surface for this feature: a read-only `FeatureAARReviewPanel.tsx` and a
v1 REST endpoint (`GET /api/v1/.../aar-review`) so `op`/ARC/Hermes can pull the persisted verdict over
LAN from the agentic-nuc node. Register the `aar-review` capability string per the standing
`/api/v1/capabilities` convention. **This is the end-of-P2 (PRD roadmap tier) milestone — requires a
`karen` review in addition to `task-completion-validator`.**

**Boundary rationale** (decisions block §1): the v1 pull surface + capability must exist before the
Phase 5 external consumer contract can reference a real endpoint.

**File ownership split**: FE (`components/Planning/FeatureAARReviewPanel.tsx`) and BE
(`backend/routers/client_v1.py`) parallelize under this split, joined by the mandatory seam task
T4-004 (R-P3).

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T4-001 | `FeatureAARReviewPanel.tsx` (read-only) | Build a read-only panel listing triage verdicts and flag evidence for a project's AARs, consuming the persisted `aar_reviews` rollup via a query hook. Must render all 3 `triage_verdict` states and remain resilient to every optional §7.2 field (see AC P4.1/P4.2). | Panel renders correctly for `surface_only`, `deep_review_recommended`, and `human_triage_required` rows in the same list; no crash on any missing optional field. | 2 pts | ui-engineer-enhanced | sonnet | adaptive | Phase 3 sealed |
| T4-002 | v1 LAN endpoint | Implement `GET /api/v1/.../aar-review` in `backend/routers/client_v1.py`, following the existing v1 client-endpoint pattern; consumes the persisted `aar_reviews` rollup via redaction-applied `session_detail` output; reuses `@memoized_query`. | Endpoint returns the reconciled §7.2 DTO shape; redaction applied before serialization; response cached per `@memoized_query` conventions. | 1.5 pt | python-backend-engineer | sonnet | adaptive | Phase 3 sealed |
| T4-003 | `aar-review` capability registration | Register the `aar-review` capability string in the `/api/v1/capabilities` response per the standing capability-advertisement convention. | Capability string present in `/api/v1/capabilities` output; consumer contract (Phase 5) can reference it. | 0.5 pt | python-backend-engineer | sonnet | adaptive | T4-002 |
| T4-004 | Seam task — DTO field → panel + v1 payload | Verify the propagation contract end-to-end: every §7.2 DTO field the panel renders is the same field the v1 endpoint serializes, with identical null-handling on both surfaces. This is the mandatory seam task per R-P3 (FE + BE overlap on the same DTO). | A single test/checklist confirms field-for-field parity between what T4-001 renders and what T4-002 returns for the same fixture row, including all resilience behaviors from AC P4.1-P4.4. | 1 pt | python-backend-engineer | sonnet | adaptive | T4-001, T4-002 |
| T4-005 | Runtime smoke (browser + endpoint) | Start the local dev stack; navigate to the panel; confirm all 3 verdict states render as specified; call the v1 endpoint directly and confirm the payload matches. Record screenshot evidence per AC P4.1's `visual_evidence_required`. | Runtime smoke recorded in the phase progress notes; if unavailable, `runtime_smoke: skipped` with an explicit reason is recorded (a clean unit-test pass alone is not a substitute, per CLAUDE.md). | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T4-001, T4-004 |

## Structured Acceptance Criteria

#### AC P4.1: FE panel renders across every triage_verdict state, resilient to every optional §7.2 field
- target_surfaces:
    - components/Planning/FeatureAARReviewPanel.tsx
- propagation_contract: The panel consumes the reconciled `AARReviewDTO` (Phase 1 §7.2 shape) from the
  `aar_reviews` rollup via its query hook; each row renders `triage_verdict`, `flags[]`
  (with sharpened Phase 2/3 evidence), and `correlation`.
- resilience: When `flags[].evidence` is empty or `severity` is null for a given flag, the panel
  renders that flag as "not triggered / not evaluated" rather than omitting the row or throwing. When
  `correlation.feature_id` is null (explicit_session_ref strategy carries no feature), the panel
  renders session-only context without a feature link, never a broken link or crash.
- visual_evidence_required: desktop >=1440px, panel populated with at least one row of each
  triage_verdict value (surface_only, deep_review_recommended, human_triage_required)
- verified_by: [T4-005]

#### AC P4.2: FE handles missing `guards.*` fields (R-P2 — new backend field from PRD §7.3)
- target_surfaces:
    - components/Planning/FeatureAARReviewPanel.tsx
- propagation_contract: `guards.provenance_excluded`/`guards.dedup_key` are null in every Phase 1-5
  emission (guards do not exist as enforced behavior until Phase 6).
- resilience: The panel treats a null `guards` block as "guard state not applicable at this producer
  version" and never renders it as an error or a missing-data warning; it MUST NOT infer guard
  enforcement from the field's presence alone.
- visual_evidence_required: false
- verified_by: [T4-005]

#### AC P4.3: FE handles missing enrichment evidence (R-P2 — new fields from Phase 2/3)
- target_surfaces:
    - components/Planning/FeatureAARReviewPanel.tsx
- propagation_contract: Phase 2's sharpened plan/task evidence refs and Phase 3's SkillMeat-ranking
  evidence are additive fields on `flags[].evidence`; they are absent for pre-enrichment or unlinked
  rows.
- resilience: When sharpened evidence is absent, the panel falls back to rendering the base P1
  evidence for that flag — never a blank/error row.
- visual_evidence_required: false
- verified_by: [T4-005]

#### AC P4.4: v1 endpoint serializes only redaction-passed data (Hard Invariant #4)
- target_surfaces:
    - backend/routers/client_v1.py
- propagation_contract: `client_v1.py`'s `aar-review` handler calls the `AARReviewQueryService`,
  which internally consumes `session_detail.py`'s redaction-applied output exclusively.
- resilience: N/A (invariant AC).
- visual_evidence_required: false
- verified_by: [T4-002, T4-004]

## Reviewer Gates

- `task-completion-validator` — mandatory, standard per-phase gate.
- **`karen` milestone review — end of P2 (PRD roadmap tier).** This phase closes the PRD's P2 tier
  (5th flag + persisted rollup + FE surface); `karen` must review the full slice (Phases 1-4 combined)
  before Phase 5 begins.

## Phase 4 Quality Gates

- [ ] Panel renders all 3 verdict states, resilient to every optional field (AC P4.1-P4.3).
- [ ] v1 endpoint returns the persisted, redaction-applied verdict (AC P4.4).
- [ ] `aar-review` capability advertised.
- [ ] Seam task (T4-004) confirms field-for-field parity between panel and v1 payload.
- [ ] Runtime smoke recorded (or explicitly `skipped` with reason).
- [ ] `task-completion-validator` review passes.
- [ ] **`karen` end-of-P2 milestone review passes.**

## Phase 4 Success Criteria

All exit criteria in this file's frontmatter are met, AND the `karen` end-of-P2 milestone review has
passed, before Phase 5 begins.
