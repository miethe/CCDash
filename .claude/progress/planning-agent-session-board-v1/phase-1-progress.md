---
type: progress
schema_version: 2
doc_type: progress
prd: planning-agent-session-board-v1
feature_slug: planning-agent-session-board-v1
phase: 1
phase_title: Correlation Contract and Query Foundation
status: completed
created: '2026-04-25'
updated: '2026-04-25'
prd_ref: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: '2026-04-29'
ui_touched: false
owners:
- fullstack-engineering
contributors:
- ai-agents
tasks:
- id: PASB-101
  title: DTO Contract
  description: Define backend and frontend types for board cards, groups, correlation
    evidence, relationships, activity markers, and next-run context refs.
  status: completed
  assigned_to:
  - backend-architect
  - frontend-developer
  assigned_model: sonnet
  dependencies: []
  acceptance_criteria:
  - Types capture explicit and inferred mapping, evidence refs, route refs, relationship
    refs, activity markers, and card state without frontend-only inference.
  estimate: 2 pts
- id: PASB-102
  title: Session Correlation Service
  description: Build correlation logic using linked feature ids, phase hints, task
    hints, lineage, command tokens, and planning refs.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - PASB-101
  acceptance_criteria:
  - Each card includes confidence, source labels, and evidence refs; weak mappings
    are distinguishable.
  estimate: 3 pts
- id: PASB-103
  title: Board Query Endpoint
  description: Expose project and feature-scoped board responses with grouping metadata,
    relationship metadata, and lightweight activity markers.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - PASB-102
  acceptance_criteria:
  - API supports project-wide board and featureId filtered board with stable response
    shape.
  estimate: 2 pts
- id: PASB-104
  title: Frontend Service Adapter
  description: Add services/planning.ts helpers that adapt backend snake_case to frontend
    camelCase.
  status: completed
  assigned_to:
  - frontend-developer
  assigned_model: sonnet
  dependencies:
  - PASB-103
  acceptance_criteria:
  - Frontend can fetch board groups and card detail without direct fetch duplication.
  estimate: 1 pt
parallelization:
  batch_1:
  - PASB-101
  batch_2:
  - PASB-102
  batch_3:
  - PASB-103
  batch_4:
  - PASB-104
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
---

# Phase 1: Correlation Contract and Query Foundation

## Objective

Normalize session-to-feature/phase/task correlation and expose board DTOs. All tasks are sequential (101 → 102 → 103 → 104). Commits after each batch.
