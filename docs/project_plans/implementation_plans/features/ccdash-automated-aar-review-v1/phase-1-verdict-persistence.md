---
schema_version: 2
doc_type: phase_plan
title: "Phase 1: Verdict Reconciliation + Persistence Foundation"
status: draft
created: 2026-07-22
phase: 1
phase_title: "Verdict Reconciliation + Persistence Foundation"
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
feature_slug: ccdash-automated-aar-review
entry_criteria:
- P1 (MVP feature contract) shipped and its 4 flags validated as useful / low-false-positive against
  a sample of real AARs (scope-findings.md Inc-2 gate — a hard precondition, not a formality; see
  PRD §6 P2 Entry). Do not begin schema reconciliation before this signal exists.
exit_criteria:
- Reconciled DTO (nested correlation{}, 3-value triage_verdict) passes a contract test pinning the
  field shape.
- aar_reviews table backfills all existing AAR<->session pairs discoverable from current entity_links.
- COLUMN_PARITY_DRIFT_ALLOWLIST updated; parity test green on both SQLite and PostgreSQL.
- Guard-input columns (skill_name/workflow_id provenance passthrough, (aar_document_id, session_id)
  dedup key) are present on aar_reviews even though guards are not enforced until Phase 6.
---

# Phase 1: Verdict Reconciliation + Persistence Foundation

**Duration**: ~1 sprint
**Dependencies**: P1 MVP shipped + validated (see Entry Criteria above)
**Assigned Subagent(s)**: `data-layer-expert` (primary — dual-DDL migration + repository), `python-backend-engineer` (secondary — DTO reconciliation + service serialization)
**Points**: 5-7 (decisions block §4 anchor: RF-telemetry P2 correlation-persistence wave, ~8 pts,
minus the read-side already built in P1)

## Overview

Reconcile the shipped flat/2-value `AARReviewDTO` to the PRD's canonical §7.2 contract (nested
`correlation{}` object + 3-value `triage_verdict` including `human_triage_required`), bump
`schema_version`, and persist every triage computation into a new `aar_reviews` rollup table
(ADR-007-compliant: dual SQLite+PostgreSQL DDL, `retry_on_locked`, direct-count assertion test). This
is the schema-freeze gate the entire remaining roadmap depends on — no evidence enrichment (Phase 2),
SkillMeat linkage (Phase 3), or cross-repo contract (Phase 5) may proceed until this shape is locked.

**Boundary rationale** (decisions block §1): schema/verdict contract must be frozen and persisted
before evidence-enrichment layers richer refs onto it.

## Deterministic Rule Annotations (OQ-7 compliance)

- OQ-2 resolution (two-hop confidence gating) is a **threshold comparison** against the existing
  0.64-1.0 band — no semantic judgment.
- The DTO reconciliation is a pure schema-mapping operation (field rename/restructure) — no new
  derivation logic is introduced in this phase.

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|--------------|----------------------|----------|--------------|-------|--------|--------------|
| T1-001 | Sample real AARs for OQ-1 prevalence | Sample >=5 real `op story`-produced AAR docs (or the fixture corpus if fewer than 5 real docs exist) and record whether each carries a direct session/feature frontmatter ref vs relying on the two-hop fallback. Record findings in this phase's progress notes. | Prevalence recorded for >=5 docs (or documented shortfall); result documented as an input to OQ-1, defaulting to "two-hop-lean" per decisions block if data is sparse. | 1 pt | python-backend-engineer | sonnet | adaptive | None |
| T1-002 | Resolve OQ-2 (two-hop confidence gating) | Decide whether every two-hop pairing routes to `human_triage_required` regardless of score, or whether the existing 0.64-1.0 band remains eligible for autonomous triage. Record the decision + rationale in this phase's progress notes and update the verdict decision table accordingly. | Decision recorded; verdict decision table (T1-003) reflects it exactly. | 1 pt | backend-architect | sonnet | extended | None |
| T1-003 | Reconcile AARReviewDTO to PRD §7.2 | Restructure the shipped flat DTO into nested `correlation{strategy, confidence, session_ids, feature_id}` + 3-value `triage_verdict` (`surface_only\|deep_review_recommended\|human_triage_required`) per T1-002's resolution; bump `schema_version`; keep flat fields as deprecated aliases for one release window (D1 default) unless T1-002/OQ-5 says otherwise. | DTO matches PRD §7.2 exactly; flat fields present but marked deprecated in docstring; schema_version incremented. | 2 pts | python-backend-engineer | sonnet | adaptive | T1-002 |
| T1-004 | Reconciled-DTO contract test | Add a contract test pinning the exact field shape (nested correlation, 3-value verdict, deprecated-alias presence) so a future change cannot silently drift the shape again. | Test fails if any §7.2 field is renamed/removed without an explicit schema_version bump. | 0.5 pt | python-backend-engineer | sonnet | adaptive | T1-003 |
| T1-005 | Design `aar_reviews` table (dual DDL) | Design the `aar_reviews` rollup table schema: `aar_document_id`, `aar_document_path`, `correlation` (JSON), `flags` (JSON), `triage_verdict`, `triage_reasons`, `evidence_refs`, `generated_at`, plus guard-input columns `provenance_skill_name`, `provenance_workflow_id`, and a `(aar_document_id, session_id)` dedup key column/index (guard inputs, D4 — not yet enforced). Write dual SQLite + PostgreSQL DDL. | Schema covers every §7.2 field; guard-input columns present; dual DDL reviewed for parity. | 2 pts | data-layer-expert | sonnet | adaptive | T1-004 |
| T1-006 | Implement `aar_reviews` repository | Implement `backend/db/repositories/aar_reviews.py` using `repositories/base.py:retry_on_locked` for every write; project-scoped per ADR-006 registry conventions. | All writes wrapped in `retry_on_locked`; repository exposes upsert-by-`(aar_document_id, session_id)` semantics. | 1.5 pt | data-layer-expert | sonnet | adaptive | T1-005 |
| T1-007 | Direct-count assertion test + parity allowlist | Ship a direct-count assertion test proving every intended write actually lands a row (ADR-007 requirement); add the new table's columns to `COLUMN_PARITY_DRIFT_ALLOWLIST`. | Direct-count test passes on both SQLite and PostgreSQL; parity allowlist entry present and accurate. | 1 pt | data-layer-expert | sonnet | adaptive | T1-006 |
| T1-008 | Backfill migration | One-time backfill: compute+persist `aar_reviews` rows for every AAR<->session pair already discoverable via `entity_links` at migration time. | Backfill runs idempotently (re-run is a no-op); row count matches the discoverable pair count. | 1 pt | python-backend-engineer | sonnet | adaptive | T1-007 |
| T1-009 | ADR addendum recording D1 | Author an ADR addendum (append to the accepted ADR or a dated addendum file) recording the DTO reconciliation decision (D1), the flat-field deprecation window, and the OQ-2 resolution (T1-002). | Addendum merged; referenced from this plan's `adr_refs`. | 0.5 pt | backend-architect | sonnet | adaptive | T1-003, T1-002 |

## Structured Acceptance Criteria

#### AC P1.1: Every new write path follows ADR-007 (Hard Invariant #4a)
- target_surfaces:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
    - backend/db/repositories/aar_reviews.py
- propagation_contract: `aar_reviews` DDL is defined identically (field-for-field) in both
  `sqlite_migrations.py` and `postgres_migrations.py`; the repository is the only write path and
  wraps every write in `retry_on_locked`.
- resilience: N/A (write-path compliance AC, not a resilience AC).
- visual_evidence_required: false
- verified_by: [T1-006, T1-007]

#### AC P1.2: Reconciled DTO shape is contract-pinned before persistence
- target_surfaces:
    - backend/application/services/agent_queries/models.py
- propagation_contract: The reconciled `AARReviewDTO` (nested `correlation{}`, 3-value
  `triage_verdict`) is the single shape `aar_reviews` persists and Phase 4's v1 endpoint later
  serializes — no transport re-derives or diverges from it.
- resilience: If `correlation.confidence` is missing/null, the verdict defaults to
  `human_triage_required`, never `surface_only` or `deep_review_recommended` (missing confidence is a
  contract state, not a bug — carried forward unchanged from the shipped P1 decision table).
- visual_evidence_required: false
- verified_by: [T1-004]

## Phase 1 Quality Gates

- [ ] Reconciled DTO passes the contract test (T1-004).
- [ ] `aar_reviews` DDL identical in shape across SQLite and PostgreSQL; parity allowlist updated.
- [ ] Direct-count assertion test green on both backends.
- [ ] Backfill is idempotent and covers all discoverable pairs.
- [ ] Guard-input columns (`provenance_skill_name`, `provenance_workflow_id`, dedup key) present, even
  though unenforced until Phase 6.
- [ ] ADR addendum merged recording D1 + OQ-2 resolution.
- [ ] `task-completion-validator` review passes.

## Phase 1 Success Criteria

All exit criteria in this file's frontmatter are met; Phase 2 may begin only after this file's
quality gates are checked off.
