---
type: progress
schema_version: 2
doc_type: progress
prd: planning-forensics-boundary-extraction-v1
feature_slug: planning-forensics-boundary-extraction-v1
phase: 2
phase_name: Planning Query Migration
status: in_progress
created: '2026-05-06'
updated: '2026-05-06'
prd_ref: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
owners:
  - platform-engineering
contributors:
  - python-backend-engineer
  - backend-architect
tasks:
  - id: P2-001
    title: Replace direct forensics dependency in planning query service
    status: pending
    assigned_to:
      - python-backend-engineer
    assigned_model: sonnet
    dependencies: []
  - id: P2-002
    title: Migrate _client_v1_features.py consumer
    status: pending
    assigned_to:
      - python-backend-engineer
    assigned_model: sonnet
    dependencies:
      - P2-001
  - id: P2-003
    title: Preserve response compatibility
    status: pending
    assigned_to:
      - python-backend-engineer
    assigned_model: sonnet
    dependencies:
      - P2-001
  - id: P2-004
    title: Add compatibility tests
    status: pending
    assigned_to:
      - python-backend-engineer
    assigned_model: sonnet
    dependencies:
      - P2-001
      - P2-002
      - P2-003
  - id: P2-005
    title: Review next-run preview context selection
    status: pending
    assigned_to:
      - backend-architect
    assigned_model: sonnet
    dependencies:
      - P2-001
parallelization:
  batch_1:
    - P2-001
  batch_2:
    - P2-002
    - P2-003
    - P2-005
  batch_3:
    - P2-004
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
progress: 0
---

# Phase 2: Planning Query Migration

Planning consumes bounded evidence rather than full feature forensics.

## Quality Gate

Existing planning APIs and `/api/v1/features/*` pass compatibility tests, planning no longer depends on transcript-heavy forensic detail for summary evidence, and import-time singleton coupling in `planning.py` is removed without breaking test isolation.
