---
type: progress
schema_version: 2
doc_type: progress
prd: provider-channel-credential-entities
feature_slug: provider-channel-credential-entities
phase: 1
status: completed
created: 2026-08-10
updated: '2026-08-10'
prd_ref: docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/provider-channel-credential-entities-v1.md
commit_refs: []
pr_refs: []
milestone: M1
milestone_title: Dimensions exist and are parity-clean
mode_d: true
mode_d_reason: schema migration v51 -> v52; authored + tested in worktree only, never
  applied to the node
owners:
- opus-orchestrator
contributors:
- data-layer-expert
- python-backend-engineer
- ica-executor
tasks:
- id: M1-001
  title: 'Dual-backend DDL: three provider dimension tables, SCHEMA_VERSION 51 ->
    52'
  status: completed
  assigned_to: data-layer-expert
  routing: 'claude-primary (MUST-stay: dual-backend DDL parity)'
  files_affected:
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  dependencies: []
- id: M1-002
  title: Provider dimension repository — retry_on_locked write paths + direct-count
    assertion tests (ADR-007)
  status: completed
  assigned_to: python-backend-engineer
  routing: 'claude-primary (MUST-stay: DB write-path correctness)'
  files_affected:
  - backend/db/repositories/provider_dimensions.py
  dependencies:
  - M1-001
- id: M1-003
  title: Parity + no-allowlist + no-secret-column test module
  status: completed
  assigned_to: ica-executor
  routing: 'ica sonnet-5 (offload-eligible: test scaffolding)'
  files_affected:
  - backend/tests/test_provider_dimension_schema.py
  dependencies:
  - M1-001
- id: M1-004
  title: M1 gate — security + validator lenses, plus karen milestone pass (context_class
    C3)
  status: completed
  assigned_to: codex-executor
  routing: codex gpt-5.6-terra (AC validation), karen claude-primary
  dependencies:
  - M1-001
  - M1-002
  - M1-003
parallelization:
  batch_1:
  - M1-001
  batch_2:
  - M1-002
  - M1-003
  batch_3:
  - M1-004
  note: 'Serialized single-committer: the orchestrator makes all commits; agents never
    touch git.'
acceptance_criteria:
- SCHEMA_VERSION == 52 in both migration modules
- No COLUMN_PARITY_DRIFT_ALLOWLIST pair names any of the three new tables
- Structural parity holds across SQLite and Postgres for all three tables
- Each new write path uses retry_on_locked and ships a direct-count assertion test
- No column can hold secret material
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
---

# M1 — Dimensions exist and are parity-clean

Three provider dimension tables land in both migration modules in one change set. No rows are
populated here; M2 backfills.

## Schema decided by the orchestrator (Mode-D)

See `.claude/worknotes/provider-channel-credential-entities/implementation-notes.md` for the
rationale behind `rotated_from_id` landing in M1, the absence of an FK on it, the open channel
vocabulary, and the `provider_*` table-name namespace.

## Status log

- 2026-08-10 — worktree `exec/provider-channel-credential-entities` created off `main` @ 42dc2ac.
- 2026-08-10 — M1-001 dispatched (data-layer-expert, claude-primary).
