---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md
phase: 0
title: Enterprise Liveness Hotfix
status: completed
started: null
completed: null
created: '2026-05-30'
updated: '2026-05-30'
commit_refs:
- 62fbf56
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 15
completed_tasks: 15
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- devops-architect
- python-backend-engineer
contributors: []
tasks:
- id: T0-001
  ledger_id: P0-001
  title: Default-on ingestion + startup-sync + fold worker-watch into enterprise profile
  status: completed
  assigned_to:
  - devops-architect
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  anchors:
  - compose.yaml:27
  - compose.yaml:133
  - compose.yaml:157-193
  - compose.yaml:169
  - config.py:246
  - container.py:237-243
- id: T0-002
  ledger_id: P0-002
  title: Auto-derive container path aliases from ResolvedProjectPaths
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: L
  anchors:
  - project_paths/providers/filesystem.py:11-37
  - source_identity.py:247-308
- id: T0-003
  ledger_id: P0-003
  title: Fail-loud readyz when watch-paths==0
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_2
  depends_on:
  - T0-001
  estimated_effort: M
  anchors:
  - bootstrap_worker.py:50-61
  - container.py:650-671
  - container.py:875-921
  - file_watcher.py:43-45
  - file_watcher.py:105-112
  - file_watcher.py:252-266
- id: T0-004
  ledger_id: P0-004
  title: WATCHFILES_FORCE_POLLING=true default for worker-watch
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - compose.yaml:175
  - file_watcher.py:16
  - file_watcher.py:183
  started: 2026-05-30T10:00Z
- id: T0-005
  ledger_id: P0-005
  title: Writable projects.json + atomic _save()
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - compose.yaml:44-48
  - project_manager.py:99-100
  - project_manager.py:140-146
- id: T0-006
  ledger_id: P0-006
  title: Read worker env vars in config.py
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - config.py
- id: T0-007
  ledger_id: P0-007
  title: frontend depends_on api (service_healthy)
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - compose.yaml:195-217
  - compose.hosted.yml:67-80
- id: T0-008
  ledger_id: P0-008
  title: entrypoint.sh worker-watch dispatch case
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: S
  anchors:
  - entrypoint.sh:8
  - entrypoint.sh:10-25
  - compose.yaml:162
  - compose.yaml:165
- id: T0-009
  ledger_id: P0-009
  title: Reconcile CCDASH_PROJECTS_FILE dead var
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - project_manager.py:287
  - compose.yaml:45
- id: T0-010
  ledger_id: P0-010
  title: Repair/deprecate compose.hosted.yml
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_2
  depends_on: []
  estimated_effort: M
  anchors:
  - compose.hosted.yml:1-84
- id: T0-011
  ledger_id: P0-011
  title: pg_advisory_lock around run_migrations()
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_1
  depends_on: []
  estimated_effort: M
  anchors:
  - container.py:106-108
  - postgres_migrations.py:1497-1519
- id: T0-013
  ledger_id: P0-013
  title: CI docker compose up e2e smoke gate
  status: completed
  assigned_to:
  - devops-architect
  assigned_model: sonnet
  batch: batch_3
  depends_on:
  - T0-001
  - T0-003
  - T0-004
  - T0-008
  estimated_effort: L
  anchors:
  - compose.yaml
  - bootstrap_worker.py:50-61
  - file_watcher.py:252-266
- id: T0-014
  ledger_id: P0-014
  title: Startup fail-loud log (enterprise + ingestion-off + empty DB)
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - container.py:237-243
  - container.py:106-108
  - config.py:246
- id: T0-015
  ledger_id: P0-015
  title: Reconcile STARTUP_SYNC_LIGHT_MODE
  status: completed
  assigned_to:
  - devops-architect
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_1
  depends_on:
  - T0-001
  estimated_effort: M
  anchors:
  - config.py:966
  - adapters/jobs/runtime.py:730
  - sync_engine.py:4261
- id: T0-SEC-CORS
  ledger_id: P0-SEC-CORS
  title: Gate dev CORS origins behind dev flag
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  batch: batch_0
  depends_on: []
  estimated_effort: S
  anchors:
  - bootstrap.py:57-67
parallelization:
  batch_0:
  - T0-004
  - T0-005
  - T0-006
  - T0-007
  - T0-009
  - T0-014
  - T0-SEC-CORS
  batch_1:
  - T0-001
  - T0-008
  - T0-011
  - T0-015
  batch_2:
  - T0-002
  - T0-003
  - T0-010
  batch_3:
  - T0-013
  critical_path:
  - T0-001
  - T0-015
  - T0-003
  - T0-013
  estimated_total_time: 3-4 days
execution_model: batch-parallel
blockers: []
success_criteria:
- GET /healthz and GET /readyz return 200 in enterprise docker compose topology
- worker-watch profile registered; entrypoint dispatches without fall-through
- readyz returns 503 when enterprise profile active and watch-path count is 0
- CI e2e smoke passes (sessions >= 1 AND worker readyz 200 with watch-paths > 0)
- CORS origins restricted to FRONTEND_ORIGIN in enterprise/api runtime
notes: "P0-012 (canonical-source-key delete path) is intentionally excluded from Phase\
  \ 0 \u2014 it is schema-adjacent / data-integrity work that belongs in Phase 1 batch_1.\
  \ See T1-P0012 in phase-1-progress.md. T0-015 must sequence WITH T0-001 (not after)\
  \ to avoid a heavy-sync window in enterprise containers on first boot.\n"
progress: 100
---

# Phase 0 — Enterprise Liveness Hotfix

Progress file for CCDash Enterprise Edition v1, Phase 0.

## Summary

Fixes the enterprise container topology so that the liveness/readiness probes
work, ingestion is on by default, worker-watch is folded into the `enterprise`
profile, and CORS is properly gated. Unlocks Phase 1 schema/storage work.

## Batch Execution Order

| Batch | Tasks | Gate |
|-------|-------|------|
| batch_0 | T0-004, T0-005, T0-006, T0-007, T0-009, T0-014, T0-SEC-CORS | No cross-deps; run all in parallel |
| batch_1 | T0-001, T0-008, T0-011, T0-015 | Core wiring; T0-015 pairs with T0-001 |
| batch_2 | T0-002, T0-003, T0-010 | Depends on batch_1 seams |
| batch_3 | T0-013 | e2e gate; requires 001/003/004/008 landed |

## Risk Hotspots

- **T0-001 + T0-015 sequencing**: default-on ingestion triggers heavy startup sync;
  STARTUP_SYNC_LIGHT_MODE reconcile must land simultaneously to avoid blocking boot.
- **T0-013**: CI gate will fail until all batch_0–batch_2 compose/entrypoint changes are merged.
