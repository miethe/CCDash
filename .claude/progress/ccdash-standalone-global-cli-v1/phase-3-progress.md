---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-standalone-global-cli-v1
feature_slug: ccdash-standalone-global-cli-v1
phase: 3
status: completed
created: '2026-04-13'
updated: '2026-04-13'
prd_ref: docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md
commit_refs:
- 4208c63
- e2c0b4c
- 6e40902
- c94da71
pr_refs: []
owners:
- python-backend-engineer
contributors: []
tasks:
- id: P3-T1
  title: Scaffold standalone package
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
- id: P3-T2
  title: Build HTTP client runtime
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P3-T1
- id: P3-T3
  title: Build config and target store
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P3-T1
- id: P3-T4
  title: Implement operator commands
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P3-T2
  - P3-T3
- id: P3-T5
  title: Add install and smoke tests
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P3-T4
parallelization:
  batch_1:
  - P3-T1
  batch_2:
  - P3-T2
  - P3-T3
  batch_3:
  - P3-T4
  batch_4:
  - P3-T5
  critical_path:
  - P3-T1
  - P3-T2
  - P3-T4
  - P3-T5
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
---

# Phase 3: Standalone CLI Runtime and Distribution

## Goal

Deliver the new globally installable CLI runtime and core operator commands that talk to a running CCDash instance over HTTP.

## Reference Documents

- Design spec: `docs/project_plans/design-specs/cli-package-split-and-schemas.md`
- Design spec: `docs/project_plans/design-specs/cli-target-model-and-auth.md`
- Design spec: `docs/project_plans/design-specs/cli-versioned-api-surface.md`
- Server API: `backend/routers/client_v1.py` (Phase 2 deliverable)

## Batch Execution Plan

### Batch 1: Package Scaffold
- P3-T1: Create `packages/ccdash_contracts/` and `packages/ccdash_cli/` with pyproject.toml and source layout

### Batch 2 (Parallel): Runtime Foundations
- P3-T2: HTTP client runtime (httpx, base URL resolution, retries, error mapping, version negotiation)
- P3-T3: Config and target store (TOML config at ~/.config/ccdash/, keyring integration, env overrides)

### Batch 3: Commands
- P3-T4: Operator commands (target add/list/use/set-token/remove, doctor, version, status project, workflow failures)

### Batch 4: Validation
- P3-T5: Install smoke tests, import boundary guard, clean-install validation
