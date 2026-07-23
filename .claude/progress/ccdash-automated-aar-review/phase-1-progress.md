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
title: Verdict Reconciliation + Persistence Foundation
status: completed
created: '2026-07-22'
updated: '2026-07-22'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: complete
total_tasks: 9
completed_tasks: 9
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
  description: Sample >=5 real op story-produced AAR docs (or fixture corpus if fewer
    than 5 exist) and record whether each carries a direct session/feature frontmatter
    ref vs relying on the two-hop fallback (OQ-1 prevalence).
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: adaptive
  note: 'Blocked: Task() tool not enabled in this phase-owner''s tool context — cannot
    dispatch to assigned specialist (python-backend-engineer) per Delegation Mandate.
    Escalated to Opus.'
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - worknote: .claude/worknotes/ccdash-automated-aar-review/oq1-aar-prevalence.md
  - worknote: .claude/worknotes/ccdash-automated-aar-review/oq1-aar-prevalence.md
  verified_by:
  - task-completion-validator
- id: T1-002
  description: 'Resolve OQ-2 (two-hop confidence gating): decide whether every two-hop
    pairing routes to human_triage_required regardless of score, or whether the existing
    0.64-1.0 band remains eligible for autonomous triage.'
  status: completed
  assigned_to:
  - backend-architect
  dependencies: []
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: extended
  note: 'Blocked: Task() tool not enabled in this phase-owner''s tool context — cannot
    dispatch to assigned specialist (backend-architect) per Delegation Mandate. Escalated
    to Opus.'
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - adr: ccdash-automated-aar-review-proposed-adr.md#addendum
  - adr: ccdash-automated-aar-review-proposed-adr.md#addendum
  verified_by:
  - task-completion-validator
- id: T1-003
  description: 'Reconcile AARReviewDTO to PRD §7.2: nested correlation{strategy, confidence,
    session_ids, feature_id} + 3-value triage_verdict (surface_only|deep_review_recommended|human_triage_required);
    bump schema_version; keep flat fields as deprecated aliases for one release window.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-002
  estimated_effort: 2 pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - test: backend/tests/test_aar_review_dto_contract.py
  - test: backend/tests/test_aar_review_dto_contract.py
  verified_by:
  - task-completion-validator
- id: T1-004
  description: Reconciled-DTO contract test pinning the exact §7.2 field shape (nested
    correlation, 3-value verdict, deprecated-alias presence).
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-003
  estimated_effort: 0.5 pt
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs:
  - AC-P1.2
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - test: backend/tests/test_aar_review_dto_contract.py
  - test: backend/tests/test_aar_review_dto_contract.py
  verified_by:
  - task-completion-validator
- id: T1-005
  description: 'Design aar_reviews rollup table (dual SQLite+PostgreSQL DDL): aar_document_id,
    aar_document_path, correlation (JSON), flags (JSON), triage_verdict, triage_reasons,
    evidence_refs, generated_at, plus guard-input columns provenance_skill_name, provenance_workflow_id,
    and an (aar_document_id, session_id) dedup key column/index.'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-004
  estimated_effort: 2 pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - code: backend/db/sqlite_migrations.py+postgres_migrations.py
  - code: backend/db/sqlite_migrations.py
  verified_by:
  - task-completion-validator
- id: T1-006
  description: Implement backend/db/repositories/aar_reviews.py using repositories/base.py:retry_on_locked
    for every write; project-scoped per ADR-006 registry conventions; upsert-by-(aar_document_id,
    session_id) semantics.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-005
  estimated_effort: 1.5 pt
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs:
  - AC-P1.1
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - code: backend/db/repositories/aar_reviews.py
  - code: backend/db/repositories/aar_reviews.py
  verified_by:
  - task-completion-validator
- id: T1-007
  description: Direct-count assertion test proving every intended write actually lands
    a row (ADR-007); add the new table's columns to COLUMN_PARITY_DRIFT_ALLOWLIST.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-006
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs:
  - AC-P1.1
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - test: backend/tests/test_aar_reviews_repo.py
  - test: backend/tests/test_aar_reviews_repo.py
  verified_by:
  - task-completion-validator
- id: T1-008
  description: 'One-time backfill migration: compute+persist aar_reviews rows for
    every AAR<->session pair already discoverable via entity_links at migration time;
    must be idempotent.'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-007
  estimated_effort: 1 pt
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - test: backend/tests/test_aar_reviews_repo.py
  - test: backend/tests/test_aar_reviews_repo.py
  verified_by:
  - task-completion-validator
- id: T1-009
  description: ADR addendum recording D1 (DTO reconciliation decision), the flat-field
    deprecation window, and the OQ-2 resolution (T1-002).
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - T1-003
  - T1-002
  estimated_effort: 0.5 pt
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-07-22T12:00:00Z'
  completed: '2026-07-22T19:00:00Z'
  evidence:
  - adr: ccdash-automated-aar-review-proposed-adr.md#addendum
  - adr: ccdash-automated-aar-review-proposed-adr.md#addendum
  verified_by:
  - task-completion-validator
parallelization:
  batch_1:
  - T1-001
  - T1-002
  batch_2:
  - T1-003
  batch_3:
  - T1-004
  - T1-009
  batch_4:
  - T1-005
  batch_5:
  - T1-006
  batch_6:
  - T1-007
  batch_7:
  - T1-008
  critical_path:
  - T1-002
  - T1-003
  - T1-004
  - T1-005
  - T1-006
  - T1-007
  - T1-008
  estimated_total_time: 5-7 pts (7 sequential batches)
blockers:
- Task() tool not available in phase-owner tool context (P1-owner spawn) — every T1-*
  task requires Task() dispatch to its assigned_to specialist per the Delegation Mandate;
  direct implementation by the phase-owner is forbidden. No task in this phase can
  proceed until either (a) the phase-owner is respawned with Task enabled, or (b)
  Opus dispatches these tasks directly. Blocked before any batch started; zero implementation/exploration
  side effects beyond read-only context gathering.
success_criteria:
- id: SC-1
  description: Reconciled DTO passes the contract test (T1-004).
  status: met
- id: SC-2
  description: aar_reviews DDL identical in shape across SQLite and PostgreSQL; parity
    allowlist updated.
  status: met
- id: SC-3
  description: Direct-count assertion test green on both backends.
  status: met
- id: SC-4
  description: Backfill is idempotent and covers all discoverable pairs.
  status: met
- id: SC-5
  description: Guard-input columns (provenance_skill_name, provenance_workflow_id,
    dedup key) present, even though unenforced until Phase 6.
  status: met
- id: SC-6
  description: ADR addendum merged recording D1 + OQ-2 resolution.
  status: met
- id: SC-7
  description: task-completion-validator review passes.
  status: met
files_modified:
- backend/application/services/agent_queries/aar_review.py
- backend/application/services/agent_queries/models.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/repositories/aar_reviews.py
notes: 'Entry criteria: P1 (MVP feature contract, commit e4c38cd) shipped and its
  4 flags validated as useful/low-false-positive against a sample of real AARs (scope-findings.md
  Inc-2 gate). This is the schema-freeze gate the entire remaining roadmap depends
  on — no evidence enrichment (Phase 2), SkillMeat linkage (Phase 3), or cross-repo
  contract (Phase 5) may proceed until this shape is locked.

  '
progress: 100
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
