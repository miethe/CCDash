---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-db-design-remediation
feature_slug: ccdash-db-design-remediation
phase: 3
title: Migration Integrity & Parity
status: completed
created: '2026-06-03'
updated: '2026-06-03'
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
commit_refs:
- baeb768
pr_refs: []
owners:
- data-layer-expert
contributors: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 8
completed_tasks: 8
in_progress_tasks: 0
blocked_tasks: 0
model_usage:
  primary: sonnet
tasks:
- id: T3-008
  description: SQLite migration concurrency guard using fcntl.flock on data/.migration.lock
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-verified
  estimated_effort: 3pts
  assigned_model: sonnet
  model_effort: extended
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:30Z
  evidence:
  - test: backend/tests/test_migration_concurrency.py
  verified_by:
  - T3-001
  - T3-003
- id: T3-009
  description: "Column/constraint-level parity diff \u2014 extend migration_governance.py"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-verified
  estimated_effort: 4pts
  assigned_model: sonnet
  model_effort: extended
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:35Z
  evidence:
  - test: backend/tests/test_migration_governance.py
  - findings: .claude/findings/ccdash-db-design-remediation-findings.md
  verified_by:
  - T3-002
- id: T3-011
  description: "Per-version migration ledger \u2014 migrations_applied table with\
    \ applied_at timestamp"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-008
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:30Z
  evidence:
  - test: backend/tests/test_migration_concurrency.py
  verified_by:
  - T3-001
  - T3-003
- id: T3-010
  description: ensure_table DDL elimination in SqliteProjectRepository and PostgresProjectRepository
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-008
  estimated_effort: 3pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:35Z
  evidence:
  - test: backend/tests/test_inline_ddl_audit.py
  - test: backend/tests/test_db_project_registry.py
  verified_by:
  - T3-004
- id: T3-001
  description: "Concurrent migration test \u2014 two processes, no lock error, no\
    \ duplicate ledger rows"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-008
  - T3-011
  estimated_effort: 3pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:30Z
  evidence:
  - test: backend/tests/test_migration_concurrency.py
  verified_by:
  - T3-001
  - T3-003
- id: T3-002
  description: "Column-parity CI test \u2014 test_column_parity_all_shared_tables\
    \ passes on both backends"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-009
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:35Z
  evidence:
  - test: backend/tests/test_migration_governance.py
  - findings: .claude/findings/ccdash-db-design-remediation-findings.md
  verified_by:
  - T3-002
- id: T3-003
  description: "Migration idempotency test \u2014 run_migrations twice, no error,\
    \ stable schema"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-008
  - T3-011
  estimated_effort: 3pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:30Z
  evidence:
  - test: backend/tests/test_migration_concurrency.py
  verified_by:
  - T3-001
  - T3-003
- id: T3-004
  description: "Grep-for-inline-DDL CI audit \u2014 zero hits for projects DDL in\
    \ production repos"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T3-010
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T23:55Z
  completed: 2026-06-04T00:35Z
  evidence:
  - test: backend/tests/test_inline_ddl_audit.py
  - test: backend/tests/test_db_project_registry.py
  verified_by:
  - T3-004
parallelization:
  batch_1:
  - T3-008
  - T3-009
  batch_2:
  - T3-011
  - T3-010
  - T3-002
  batch_3:
  - T3-001
  - T3-003
  - T3-004
  critical_path:
  - T3-008
  - T3-011
  - T3-001
blockers:
- id: BLOCKER-P3-001
  title: P1 must be verified before P3 can begin
  severity: critical
  blocking:
  - T3-008
  - T3-009
  resolution: 'RESOLVED 2026-06-04: P1 exited at commit 9633900 (T1-010 gate passed).'
  created: '2026-06-03'
  resolved: '2026-06-04'
success_criteria:
- id: SC-1
  description: T3-008 SQLite migration concurrency guard; lock file at data/.migration.lock
  status: met
- id: SC-2
  description: T3-001 concurrent migration test passes (two processes, no lock error,
    no duplicate rows)
  status: met
- id: SC-3
  description: T3-009 migration_governance.py exports column_parity_diff; returns
    empty dict on current codebase
  status: met
- id: SC-4
  description: T3-002 test_column_parity_all_shared_tables passes in CI on both backends
  status: met
- id: SC-5
  description: T3-010 ensure_table contains no inline CREATE TABLE DDL for projects
  status: met
- id: SC-6
  description: T3-004 CI grep confirms zero hits for projects inline DDL in production
    repos
  status: met
- id: SC-7
  description: T3-011 migrations_applied ledger records per-version rows with applied_at;
    no duplicates on rerun
  status: met
- id: SC-8
  description: T3-003 migration idempotency test passes on both SQLite and Postgres
  status: met
- id: SC-9
  description: task-completion-validator sign-off
  status: met
- id: SC-10
  description: 'karen milestone review: migration integrity (concurrency guard, column-parity,
    idempotency)'
  status: met
notes:
- 'Scope-protection rule: if T3-009 column_parity_diff reveals drift >2 pts, record
  to .claude/findings/ccdash-db-design-remediation-findings.md (create lazily), triage,
  do NOT expand P3 beyond 13 pts.'
- Runs in parallel with P4 after P1 exits.
- 'T3-009 drift outcome: 6 genuine drift items (DRIFT-001..006) recorded in .claude/findings/ccdash-db-design-remediation-findings.md
  and allowlisted in COLUMN_PARITY_DRIFT_ALLOWLIST; no migration DDL rewritten (scope-protection
  rule applied). findings_doc_ref set on parent plan.'
- 'Reviewer gates: task-completion-validator APPROVED after one fix cycle (busy_timeout
  startup-race + governance tautology); karen milestone review PASS. Validation evidence:
  106 passed / 1 skipped (Postgres env-gated) across 11 named test files.'
- "Environment note: backend/tests/test_runtime_bootstrap.py hangs in this dev environment\
  \ (pre-existing \u2014 orphaned hung processes predate Phase 3 work); excluded from\
  \ sweeps. Backend-only phase: runtime_smoke not applicable (no UI changes)."
runtime_smoke: not-applicable-backend-only
progress: 100
---

# ccdash-db-design-remediation — Phase 3: Migration Integrity & Parity

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

**Blocked on**: P1 verified (T1-010 cold-start smoke passed). May run in parallel with P4 after P1 exits.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-db-design-remediation/phase-3-progress.md \
  -t T3-008 -s completed --started <ISO> --completed <ISO>
```

---

## Objective

Close migration concurrency and column-parity gaps: add SQLite concurrency guard, extend `migration_governance.py` to column-level diff, eliminate `ensure_table` inline DDL, and add per-version migration ledger.

---

## Quick Reference

| Task | Description | Assigned | Deps |
|------|-------------|----------|------|
| T3-008 | SQLite migration concurrency guard (impl) | data-layer-expert | P1 verified |
| T3-009 | Column/constraint-level parity diff (impl) | data-layer-expert | P1 verified |
| T3-011 | Per-version migration ledger | data-layer-expert | T3-008 |
| T3-010 | ensure_table DDL elimination (impl) | data-layer-expert | T3-008 |
| T3-001 | Concurrent migration test | data-layer-expert | T3-008, T3-011 |
| T3-002 | Column-parity CI test | data-layer-expert | T3-009 |
| T3-003 | Migration idempotency test | data-layer-expert | T3-008, T3-011 |
| T3-004 | Grep-for-inline-DDL CI audit | data-layer-expert | T3-010 |

## Reviewer Gates

- **task-completion-validator** — per-phase completion check at phase exit
- **karen** — Tier 3 milestone review: migration integrity (concurrency guard, column-parity, idempotency)
