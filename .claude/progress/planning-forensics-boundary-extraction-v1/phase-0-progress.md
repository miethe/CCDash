---
type: progress
schema_version: 2
doc_type: progress
prd: planning-forensics-boundary-extraction-v1
feature_slug: planning-forensics-boundary-extraction-v1
phase: 0
phase_name: Contract Inventory And Guardrails
status: pending
created: 2026-05-06
updated: '2026-05-06'
prd_ref: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
owners:
- platform-engineering
contributors:
- backend-architect
- frontend-developer
- documentation-writer
- ui-engineer-enhanced
tasks:
- id: P0-001
  title: Inventory planning consumers of forensics/token/session evidence
  status: pending
  assigned_to:
  - backend-architect
  - documentation-writer
  assigned_model: sonnet
  dependencies: []
  evidence: []
- id: P0-002
  title: Inventory feature/session frontend consumers
  status: pending
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  assigned_model: sonnet
  dependencies: []
  evidence: []
- id: P0-003
  title: Define compatibility fields
  status: pending
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  dependencies:
  - P0-001
  evidence: []
- id: P0-004
  title: Decide MCP/CLI transport scope
  status: completed
  assigned_to:
  - backend-architect
  assigned_model: sonnet
  dependencies: []
  evidence: []
- id: P0-005
  title: Add guardrail notes
  status: completed
  assigned_to:
  - documentation-writer
  assigned_model: haiku
  dependencies: []
  evidence: []
parallelization:
  batch_1:
  - P0-001
  - P0-002
  - P0-004
  - P0-005
  batch_2:
  - P0-003
total_tasks: 5
completed_tasks: 2
in_progress_tasks: 0
blocked_tasks: 0
progress: 40
---

# Phase 0: Contract Inventory And Guardrails

## Goal
Lock the exact consumers and fields before code moves.

## Quality Gate
Implementation cannot start until (a) the two inventory artifacts are filed, (b) compatibility fields are fixed, and (c) the MCP/CLI scope decision is recorded. A verbal call-site list is not sufficient — the artifact must exist on disk.
