---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-standalone-global-cli-v1
feature_slug: ccdash-standalone-global-cli-v1
phase: 2
status: in_progress
created: '2026-04-13'
updated: '2026-04-13'
prd_ref: docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md
commit_refs: []
pr_refs: []

owners:
- python-backend-engineer
- backend-architect
contributors: []

tasks:
  - id: P2-T1
    title: Add instance metadata endpoint
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies: []
  - id: P2-T2
    title: Promote project/workflow endpoints into versioned client surface
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies: []
  - id: P2-T3
    title: Add feature list/detail endpoints
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies: []
  - id: P2-T4
    title: Add feature-linked session/documents endpoints
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies:
    - P2-T3
  - id: P2-T5
    title: Add session intelligence list/detail/search/drilldown/family endpoints
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies: []
  - id: P2-T6
    title: Add contract tests
    status: pending
    assigned_to:
    - python-backend-engineer
    dependencies:
    - P2-T1
    - P2-T2
    - P2-T3
    - P2-T4
    - P2-T5

parallelization:
  batch_1:
  - P2-T1
  - P2-T2
  - P2-T3
  - P2-T5
  batch_2:
  - P2-T4
  batch_3:
  - P2-T6
  critical_path:
  - P2-T3
  - P2-T4
  - P2-T6

total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
progress: 0
---

# Phase 2: Server-Side Client API Foundation

## Goal

Expose a stable, versioned HTTP surface (`/api/v1/`) for the standalone CLI, wrapping existing application services under a new client-facing contract with standard response envelopes.

## Reference Documents

- Design spec: `docs/project_plans/design-specs/cli-versioned-api-surface.md`
- Design spec: `docs/project_plans/design-specs/cli-package-split-and-schemas.md`
- Design spec: `docs/project_plans/design-specs/cli-target-model-and-auth.md`

## Batch Execution Plan

### Batch 1 (Parallel): Core Endpoints
- P2-T1: Instance metadata endpoint
- P2-T2: Project/workflow versioned endpoints
- P2-T3: Feature list/detail endpoints
- P2-T5: Session intelligence endpoints

### Batch 2: Feature-linked Endpoints
- P2-T4: Feature sessions/documents endpoints (depends on P2-T3 for feature routing)

### Batch 3: Contract Tests
- P2-T6: Contract tests for all endpoints
