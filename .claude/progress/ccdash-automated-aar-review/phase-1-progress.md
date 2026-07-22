---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-automated-aar-review
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
execution_model: batch-parallel
phase: 1
title: "Verdict Reconciliation + Persistence Foundation"
status: pending
created: 2026-07-22
updated: 2026-07-22
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: on-track

total_tasks: 9
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners:
- data-layer-expert
- python-backend-engineer
contributors:
- backend-architect

model_usage:
  primary: sonnet
  external: []

tasks:
- id: T1-001
  description: "Sample >=5 real op story-produced AAR docs (or fixture corpus if fewer
    than 5 exist) and record whether each carries a direct session/feature frontmatter
    ref vs relying on the two-hop fallback (OQ-1 prevalence)."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: []
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T1-002
  description: "Resolve OQ-2 (two-hop confidence gating): decide whether every two-hop
    pairing routes to human_triage_required regardless of score, or whether the
    existing 0.64-1.0 band remains eligible for autonomous triage."
  status: pending
  assigned_to: [backend-architect]
  dependencies: []
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: extended
- id: T1-003
  description: "Reconcile AARReviewDTO to PRD §7.2: nested correlation{strategy,
    confidence, session_ids, feature_id} + 3-value triage_verdict
    (surface_only|deep_review_recommended|human_triage_required); bump schema_version;
    keep flat fields as deprecated aliases for one release window."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T1-002]
  estimated_effort: "2 pts"
  assigned_model: sonnet
  model_effort: adaptive
- id: T1-004
  description: "Reconciled-DTO contract test pinning the exact §7.2 field shape
    (nested correlation, 3-value verdict, deprecated-alias presence)."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T1-003]
  estimated_effort: "0.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P1.2]
- id: T1-005
  description: "Design aar_reviews rollup table (dual SQLite+PostgreSQL DDL):
    aar_document_id, aar_document_path, correlation (JSON), flags (JSON),
    triage_verdict, triage_reasons, evidence_refs, generated_at, plus guard-input
    columns provenance_skill_name, provenance_workflow_id, and an
    (aar_document_id, session_id) dedup key column/index."
  status: pending
  assigned_to: [data-layer-expert]
  dependencies: [T1-004]
  estimated_effort: "2 pts"
  assigned_model: sonnet
  model_effort: adaptive
- id: T1-006
  description: "Implement backend/db/repositories/aar_reviews.py using
    repositories/base.py:retry_on_locked for every write; project-scoped per ADR-006
    registry conventions; upsert-by-(aar_document_id, session_id) semantics."
  status: pending
  assigned_to: [data-layer-expert]
  dependencies: [T1-005]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P1.1]
- id: T1-007
  description: "Direct-count assertion test proving every intended write actually
    lands a row (ADR-007); add the new table's columns to
    COLUMN_PARITY_DRIFT_ALLOWLIST."
  status: pending
  assigned_to: [data-layer-expert]
  dependencies: [T1-006]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P1.1]
- id: T1-008
  description: "One-time backfill migration: compute+persist aar_reviews rows for
    every AAR<->session pair already discoverable via entity_links at migration
    time; must be idempotent."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T1-007]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T1-009
  description: "ADR addendum recording D1 (DTO reconciliation decision), the flat-field
    deprecation window, and the OQ-2 resolution (T1-002)."
  status: pending
  assigned_to: [backend-architect]
  dependencies: [T1-003, T1-002]
  estimated_effort: "0.5 pt"
  assigned_model: sonnet
  model_effort: adaptive

parallelization:
  batch_1: [T1-001, T1-002]
  batch_2: [T1-003]
  batch_3: [T1-004, T1-009]
  batch_4: [T1-005]
  batch_5: [T1-006]
  batch_6: [T1-007]
  batch_7: [T1-008]
  critical_path: [T1-002, T1-003, T1-004, T1-005, T1-006, T1-007, T1-008]
  estimated_total_time: "5-7 pts (7 sequential batches)"

blockers: []

success_criteria:
- id: SC-1
  description: "Reconciled DTO passes the contract test (T1-004)."
  status: pending
- id: SC-2
  description: "aar_reviews DDL identical in shape across SQLite and PostgreSQL;
    parity allowlist updated."
  status: pending
- id: SC-3
  description: "Direct-count assertion test green on both backends."
  status: pending
- id: SC-4
  description: "Backfill is idempotent and covers all discoverable pairs."
  status: pending
- id: SC-5
  description: "Guard-input columns (provenance_skill_name, provenance_workflow_id,
    dedup key) present, even though unenforced until Phase 6."
  status: pending
- id: SC-6
  description: "ADR addendum merged recording D1 + OQ-2 resolution."
  status: pending
- id: SC-7
  description: "task-completion-validator review passes."
  status: pending

files_modified:
- backend/application/services/agent_queries/aar_review.py
- backend/application/services/agent_queries/models.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/repositories/aar_reviews.py

notes: >
  Entry criteria: P1 (MVP feature contract, commit e4c38cd) shipped and its 4 flags
  validated as useful/low-false-positive against a sample of real AARs (scope-findings.md
  Inc-2 gate). This is the schema-freeze gate the entire remaining roadmap depends on — no
  evidence enrichment (Phase 2), SkillMeat linkage (Phase 3), or cross-repo contract
  (Phase 5) may proceed until this shape is locked.
---

# ccdash-automated-aar-review - Phase 1: Verdict Reconciliation + Persistence Foundation

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-1-progress.md \
  -t T1-001 -s completed

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-1-progress.md \
  --updates "T1-001:completed,T1-002:completed"

# Arbitrary field update
python .claude/skills/artifact-tracking/scripts/update-field.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-1-progress.md \
  --field overall_progress --value 25
```

---

## Objective

Reconcile the shipped flat/2-value `AARReviewDTO` to the PRD's canonical §7.2 contract (nested
`correlation{}` + 3-value `triage_verdict`), and persist every triage computation into a new
`aar_reviews` rollup table (ADR-007-compliant dual DDL + `retry_on_locked` + direct-count test).

---

## Implementation Notes

### Architectural Decisions

- D1 (locked): reconcile flat DTO to nested PRD §7.2 shape; bump `schema_version`; flat fields
  remain deprecated aliases for one release window.
- D6 (locked): reuse existing CorePorts/storage; no new correlation key, no new `CorePort`.
- Guard-input columns (provenance_skill_name, provenance_workflow_id, dedup key) are designed here
  as data model but not enforced until Phase 6 (D4).

### Patterns and Best Practices

- ADR-007 write-path standard: every `aar_reviews` write goes through
  `repositories/base.py:retry_on_locked`; dual DDL in `sqlite_migrations.py` +
  `postgres_migrations.py`; direct-count assertion test on both backends per ADR-006/007
  conventions already used elsewhere in `backend/db/repositories/`.

### Known Gotchas

- Missing `correlation.confidence` must default the verdict to `human_triage_required`, never
  `surface_only`/`deep_review_recommended` (contract state, not a bug — carried forward from the
  shipped P1 decision table).
- Do not begin schema reconciliation before the P1 validation-signal entry criterion exists.

### Development Setup

No special setup beyond the standard backend venv (`backend/.venv`); this phase touches only
backend migration/model/repository files.

---

## Completion Notes

_To be filled in when this phase is complete: what was built, key learnings, unexpected
challenges, recommendations for Phase 2._
