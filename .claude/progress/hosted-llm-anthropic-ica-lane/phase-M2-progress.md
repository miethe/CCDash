---
type: progress
schema_version: 2
doc_type: progress
prd: hosted-llm-anthropic-ica-lane
feature_slug: hosted-llm-anthropic-ica-lane
phase: M2
status: completed
created: 2026-08-10
updated: '2026-08-10'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md
itt_node_id: node_01KZP8ZDME85N9Q0EGFVX0TKRV
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
commit_refs:
- '6100904'
- 6e79947
- acbc357
pr_refs: []
owners:
- data-layer-expert
- python-backend-engineer
contributors: []
parallelization:
  batch_1:
  - TM2-001
  - TM2-002
  - TM2-003
  batch_2:
  - TM2-004
  - TM2-005
  - TM2-006
  - TM2-007
  - TM2-008
  - TM2-009
tasks:
- id: TM2-001
  title: 'Dual DDL: projects.llm_egress_consent in sqlite + postgres CREATE TABLE
    and _ensure_column, default FALSE'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  started: 2026-08-10T17:00Z
  completed: 2026-08-10T17:35Z
  evidence:
  - commit: '6100904'
  verified_by:
  - orchestrator-verified
- id: TM2-002
  title: Bump SCHEMA_VERSION 51 -> 52 in both migration modules, zero COLUMN_PARITY_DRIFT_ALLOWLIST
    entries
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  started: 2026-08-10T17:00Z
  completed: 2026-08-10T17:35Z
  evidence:
  - commit: '6100904'
  verified_by:
  - orchestrator-verified
- id: TM2-003
  title: 'Read path: Project.llm_egress_consent on the model, both repositories, and
    project_manager._row_to_project'
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  started: 2026-08-10T17:00Z
  completed: 2026-08-10T17:35Z
  evidence:
  - commit: '6100904'
  verified_by:
  - orchestrator-verified
- id: TM2-004
  title: CCDASH_LLM_EGRESS_CONSENT global config var, default FALSE (fail-closed)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T18:15Z
  evidence:
  - commit: 6e79947
  verified_by:
  - gate-security
  - gate-validator
- id: TM2-005
  title: Lane resolver returns None under false consent (structural no-op, no call-site
    conditional)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T18:15Z
  evidence:
  - commit: 6e79947
  verified_by:
  - gate-security
  - gate-validator
- id: TM2-006
  title: Sweep skips non-consenting projects, evaluated per tick not at construction
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T19:00Z
  evidence:
  - commit: 6e79947
  - commit: acbc357
  - orchestrator: disk-verified freshness flag per-tick
  verified_by:
  - gate-security-repass-1
- id: TM2-007
  title: 'Provenance enforced on egress: only AGGREGATE / TRANSCRIPT_REDACTED may
    leave the box'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T18:15Z
  evidence:
  - commit: 6e79947
  verified_by:
  - gate-security
  - gate-validator
- id: TM2-008
  title: Per-tick egress observability line (lane, model id served, project id)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T18:15Z
  evidence:
  - commit: 6e79947
  verified_by:
  - gate-validator
- id: TM2-009
  title: 'Tests: negative-construction under false consent, two-project narrowing,
    per-tick revocation, wrong-provenance rejection'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM2-001
  - TM2-003
  started: 2026-08-10T17:40Z
  completed: 2026-08-10T19:00Z
  evidence:
  - commit: acbc357
  - test: 211 passed 8 skipped 22 subtests
  - orchestrator: ran 211 passed 8 skipped
  verified_by:
  - gate-security-repass-1
total_tasks: 9
completed_tasks: 9
in_progress_tasks: 0
blocked_tasks: 0
pending_tasks: 0
progress: 100
overall_progress: 100
---

# Milestone M2 — Consent gates egress, with no new provider added

## Exit Criteria

- `projects.llm_egress_consent` column exists in both SQLite and PostgreSQL DDL; migration version bumped to 52
- `CCDASH_LLM_EGRESS_CONSENT` (default FALSE) gates lane resolution; False consent returns None
- Sweep and egress observability respect per-project consent; only AGGREGATE and TRANSCRIPT_REDACTED leave the box
- Tests verify false-consent construction, per-project narrowing, per-tick revocation, and provenance enforcement

## Gate

- `gate_lens: [security, validator]`
- `gate_lens_reason: irreversible-outward`

## Mode-D

M2 contains a schema migration affecting both SQLite and PostgreSQL DDL (projects.llm_egress_consent column + SCHEMA_VERSION bump). The operator granted Mode-D approval in the invoking prompt. Only migration modules were edited (backend/db/migrations.py and backend/db/migrations_postgres.py); no live database was applied locally.
