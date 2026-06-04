---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-db-design-remediation
feature_slug: ccdash-db-design-remediation
phase: 1
title: Registry Correctness & Authority
status: completed
created: '2026-06-03'
updated: '2026-06-03'
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
commit_refs:
- 4ef37ac
- 7d04401
- 325472250d0a
pr_refs: []
owners:
- data-layer-expert
contributors:
- python-backend-engineer
overall_progress: 100
completion_estimate: on-track
total_tasks: 10
completed_tasks: 10
in_progress_tasks: 0
blocked_tasks: 0
model_usage:
  primary: sonnet
tasks:
- id: T1-001
  description: Fail-loud bootstrap — fix _flush_snapshot_to_db swallow site
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T17:37Z
  completed: 2026-06-03T17:37Z
  evidence:
  - test: backend/tests/test_db_project_registry.py:14-passed
  verified_by:
  - T1-005
  - T1-006
- id: T1-009
  description: Dead config.DB_PATH cleanup at config.py:57
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T17:37Z
  completed: 2026-06-03T17:37Z
  evidence:
  - test: backend/tests/test_request_context.py:40-passed
  verified_by:
  - task-completion-validator
- id: T1-002
  description: Locked-retry on registry sync write — apply _commit_with_retry pattern
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-001
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T17:37Z
  completed: 2026-06-03T17:37Z
  evidence:
  - test: backend/tests/test_db_project_registry.py:14-passed
  verified_by:
  - T1-005
- id: T1-005
  description: Lock-injection test — F-01 reproducer in test_db_project_registry.py
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-001
  - T1-002
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T19:43Z
  completed: 2026-06-03T19:43Z
  evidence:
  - test: test_registry_flush_fail_loud
  verified_by:
  - task-completion-validator
- id: T1-006
  description: Direct-count post-flush test asserting repo.count() == len(snapshot)
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T1-001
  - T1-002
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T19:43Z
  completed: 2026-06-03T19:43Z
  evidence:
  - test: test_registry_persistence_direct_count
  verified_by:
  - task-completion-validator
- id: T1-003
  description: Bootstrap sequencing — move registry bootstrap before SyncEngine burst
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-001
  - T1-002
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: extended
  started: 2026-06-03T19:43Z
  completed: 2026-06-03T19:43Z
  evidence:
  - test: 56-passed-named-suites
  - smoke: log-ordering-verified-by-T1-010
  verified_by:
  - T1-010
- id: T1-004
  description: Dual-manager collapse — per ADR-006 Option B; add import/export helpers
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-003
  estimated_effort: 3pts
  assigned_model: sonnet
  model_effort: extended
  started: 2026-06-03T19:48Z
  completed: 2026-06-03T19:48Z
  evidence:
  - test: test_db_project_registry.py:19-passed
  verified_by:
  - T1-008
  - T1-010
- id: T1-007
  description: Caller-grep audit — document/remove all manager= JSON-backed call sites
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-004
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T19:48Z
  completed: 2026-06-03T19:48Z
  evidence:
  - audit: caller-grep-table-in-commit
  verified_by:
  - task-completion-validator
- id: T1-008
  description: Import/export round-trip test — 5 projects in, 5 out, existing rows
    preserved
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-004
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T19:48Z
  completed: 2026-06-03T19:48Z
  evidence:
  - test: TestImportExportRoundTrip:3-tests
  verified_by:
  - task-completion-validator
- id: T1-010
  description: P1 cold-start smoke — /api/projects = 5 projects; worker binds; no
    ERROR logs
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  - T1-005
  - T1-006
  - T1-007
  - T1-008
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: 2026-06-03T19:54Z
  completed: 2026-06-03T19:54Z
  evidence:
  - smoke: api-5-projects,db-count-5,log-ordering-verified,no-registry-errors
  - deviation: worker-profile-enterprise-only-by-design
  verified_by:
  - task-completion-validator
parallelization:
  batch_1:
  - T1-001
  - T1-009
  batch_2:
  - T1-002
  - T1-003
  batch_3:
  - T1-005
  - T1-006
  - T1-004
  batch_4:
  - T1-007
  - T1-008
  batch_5:
  - T1-010
  critical_path:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  - T1-007
  - T1-010
blockers: []
success_criteria:
- id: SC-1
  description: T1-005 test_registry_flush_fail_loud passes (lock-injection, fail-loud)
  status: met
- id: SC-2
  description: T1-006 test_registry_persistence_direct_count passes (no two-instance
    workaround)
  status: met
- id: SC-3
  description: T1-008 import/export round-trip test passes
  status: met
- id: SC-4
  description: 'T1-010 cold-start smoke: /api/projects = 5; projects table non-empty;
    worker binds'
  status: met
- id: SC-5
  description: T1-009 dead config.DB_PATH removed or consolidated; grep confirms
  status: met
- id: SC-6
  description: task-completion-validator sign-off
  status: met
- id: SC-7
  description: 'karen milestone review: ADR-006 conformance'
  status: met
progress: 100
---

# ccdash-db-design-remediation — Phase 1: Registry Correctness & Authority

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-db-design-remediation/phase-1-progress.md \
  -t T1-001 -s completed --started <ISO> --completed <ISO>
```

---

## Objective

Fix the root cause of F-01: replace the silent `_flush_snapshot_to_db` no-op with fail-loud + retry behavior, collapse the dual project managers per ADR-006, and re-sequence the bootstrap outside the heavy sync window.

---

## Quick Reference

| Task | Description | Assigned | Deps |
|------|-------------|----------|------|
| T1-001 | Fail-loud bootstrap | data-layer-expert | — |
| T1-009 | Dead config.DB_PATH cleanup | python-backend-engineer | — |
| T1-002 | Locked-retry on registry sync write | data-layer-expert | T1-001 |
| T1-003 | Bootstrap sequencing | python-backend-engineer | T1-001, T1-002 |
| T1-004 | Dual-manager collapse | python-backend-engineer | T1-003 |
| T1-005 | Lock-injection test | data-layer-expert | T1-001, T1-002 |
| T1-006 | Direct-count post-flush test | data-layer-expert | T1-001, T1-002 |
| T1-007 | Caller-grep audit | python-backend-engineer | T1-004 |
| T1-008 | Import/export round-trip test | python-backend-engineer | T1-004 |
| T1-010 | P1 cold-start smoke (runtime-smoke) | python-backend-engineer | T1-001–T1-008 |

## Reviewer Gates

- **task-completion-validator** — per-phase completion check at phase exit
- **karen** — Tier 3 milestone review: ADR-006 conformance (single DB-backed manager, import/export helpers, no silent flush)
