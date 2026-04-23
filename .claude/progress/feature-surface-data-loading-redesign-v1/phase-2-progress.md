---
type: progress
schema_version: 2
doc_type: progress
prd: feature-surface-data-loading-redesign-v1
feature_slug: feature-surface-data-loading-redesign-v1
prd_ref: docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md
phase: 2
title: Service and API Contracts
status: in_progress
created: '2026-04-23'
updated: '2026-04-23'
started: '2026-04-23'
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 8
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- api-documenter
contributors: []
model_usage:
  primary: sonnet
  external: []
ui_touched: false
runtime_smoke: not_applicable
tasks:
- id: P2-001
  description: DTO Definitions - Add DTOs for FeatureCardDTO, FeatureCardPageDTO, FeatureRollupDTO, FeatureModalOverviewDTO, FeatureModalSectionDTO, and LinkedFeatureSessionPageDTO.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P1-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:24Z
  evidence:
  - test: backend/tests/test_feature_surface_dtos.py
- id: P2-002
  description: Feature Surface Query Service - Add service that composes feature list rows and phase/doc/dependency summaries from repositories.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - P1-004
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:24Z
  evidence:
  - test: backend/tests/test_feature_surface_list_rollup_service.py
- id: P2-003
  description: Rollup Service - Add service that resolves aggregate metrics for bounded feature IDs and validates field selection.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P1-004
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:24Z
  evidence:
  - test: backend/tests/test_feature_surface_list_rollup_service.py
- id: P2-004
  description: Modal Detail Service - Split modal detail into overview, phases/tasks, docs, relations, sessions, test status, and activity helpers.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - P1-005
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:24Z
  evidence:
  - test: backend/tests/test_feature_surface_modal_service.py
- id: P2-005
  description: v1 Feature List Endpoint - Extend GET /api/v1/features or add compatible query mode for card DTOs with backend filters, sort, and totals.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P2-002
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:38Z
  evidence:
  - test: backend/tests/test_client_v1_contract.py
  - test: backend/tests/test_client_v1_feature_surface.py
- id: P2-006
  description: v1 Rollup Endpoint - Add POST /api/v1/features/rollups with bounded IDs and field selection.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P2-003
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:38Z
  evidence:
  - test: backend/tests/test_client_v1_feature_surface.py
- id: P2-007
  description: v1 Modal Endpoints - Add or extend endpoints for overview, section includes, paginated sessions, and activity.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - P2-004
  estimated_effort: 1 pt
  priority: high
  assigned_model: sonnet
  completed: 2026-04-23T16:38Z
  evidence:
  - test: backend/tests/test_client_v1_feature_surface.py
- id: P2-008
  description: API Observability - Instrument latency, result count, payload size estimate, cache status, and error categorization.
  status: pending
  assigned_to:
  - backend-architect
  dependencies:
  - P2-005
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
parallelization:
  batch_1:
  - P2-001
  - P2-002
  - P2-003
  - P2-004
  batch_2:
  - P2-005
  - P2-006
  - P2-007
  batch_3:
  - P2-008
progress: 88
---

# Phase 2 Progress — Service and API Contracts

## Context

Phase 1 established repository-backed list, phase summary, rollup, and linked-session pagination primitives. Phase 2 builds stable service and API contracts on those bounded reads without reintroducing eager per-feature session hydration.

## Explicit Deferrals

- Real indexed `latest_activity_at` and `session_count` sort columns remain deferred beyond this phase; Phase 2 must not present these as exact sort semantics unless backed by real repository support.
- Cursor-based pagination for `LinkedSessionQuery` remains deferred; Phase 2 should continue to use offset pagination and preserve the placeholder cursor field only as metadata.
- Postgres migration runner for the six planned indexes, tag GIN/junction-table work, and `linkedPrCount` persistence remain out of scope for this phase.

## Execution Strategy

Commit at the end of each batch. Keep work split across DTO/service files first, then router/contract files, then observability. Leave unrelated workspace changes untouched.

## Batch 1 Complete

- Added backend-owned feature-surface DTOs with camelCase serialization.
- Added bounded list/rollup service over Phase 1 repository methods.
- Added section-oriented modal detail service with source-paged session loading.
- Validation: `backend/.venv/bin/python -m pytest backend/tests/test_feature_surface_dtos.py backend/tests/test_feature_surface_list_rollup_service.py backend/tests/test_feature_surface_modal_service.py -q`

## Batch 2 Complete

- Added Phase 2 shared/public v1 feature-surface contracts to `ccdash_contracts`.
- Added `view=cards` plus `include=card/cards` compatibility mode on `GET /api/v1/features`.
- Added `POST /api/v1/features/rollups`, modal overview/section endpoints, and a richer linked-session page route while preserving legacy default responses.
- Validation: `backend/.venv/bin/python -m pytest backend/tests/test_client_v1_contract.py backend/tests/test_client_v1_feature_surface.py -q`
