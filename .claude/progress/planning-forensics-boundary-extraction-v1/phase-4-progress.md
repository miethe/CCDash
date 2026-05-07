---
type: progress
schema_version: 2
doc_type: progress
prd: planning-forensics-boundary-extraction-v1
feature_slug: planning-forensics-boundary-extraction-v1
phase: 4
phase_name: Frontend Feature Detail Boundary
status: in_progress
created: '2026-05-07'
updated: '2026-05-07'
prd_ref: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
owners:
  - platform-engineering
contributors:
  - frontend-developer
  - ui-engineer-enhanced
  - frontend-architect
  - documentation-writer

execution_model: batch-parallel

tasks:
  - id: P4-000
    title: File Phase 4 tab/domain ownership manifest
    status: pending
    assigned_to:
      - frontend-architect
      - documentation-writer
    assigned_model: sonnet
    dependencies: []
  - id: P4-001
    title: Extract reusable feature-detail shell
    status: pending
    assigned_to:
      - ui-engineer-enhanced
    assigned_model: sonnet
    dependencies:
      - P4-000
  - id: P4-002
    title: Split useFeatureModalData into composable domain data handles
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-000
  - id: P4-003
    title: Move planning-native tabs/actions into planning module
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-001
      - P4-002
  - id: P4-004
    title: Move session evidence tabs into forensics/session module
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-001
      - P4-002
  - id: P4-005
    title: Move execution/test handoff into execution-owned components
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-001
      - P4-002
  - id: P4-006
    title: Preserve board and planning route adapters
    status: pending
    assigned_to:
      - ui-engineer-enhanced
    assigned_model: sonnet
    dependencies:
      - P4-003
      - P4-004
      - P4-005
  - id: P4-007
    title: Preserve cache invalidation across the split
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-003
      - P4-004
      - P4-005
  - id: P4-008
    title: Retire legacy detail/session fetches only after parity
    status: pending
    assigned_to:
      - frontend-developer
    assigned_model: sonnet
    dependencies:
      - P4-006
      - P4-007
  - id: P4-009
    title: Preserve lazy loading, encoded IDs, and tests through relocation
    status: pending
    assigned_to:
      - ui-engineer-enhanced
    assigned_model: sonnet
    dependencies:
      - P4-008

parallelization:
  batch_1:
    - P4-000
  batch_2:
    - P4-001
    - P4-002
  batch_3:
    - P4-003
    - P4-004
    - P4-005
  batch_4:
    - P4-006
    - P4-007
  batch_5:
    - P4-008
  batch_6:
    - P4-009
---

# Phase 4: Frontend Feature Detail Boundary

Separate planning, forensics, and execution UI ownership inside feature detail surfaces while preserving cache invalidation correctness.

## Entry Criteria
- [x] Phase 0 frontend inventory (P0-002) filed
- [x] Phase 1 FeatureEvidenceSummary DTO frozen
- [ ] Existing feature-surface lazy-loading tests baseline verified

## Execution Notes

Commit per task as requested. Pay special attention to delegation discipline — no more than one agent writes to `ProjectBoard.tsx` at a time. Shared type changes are sequential before parallel UI work.
