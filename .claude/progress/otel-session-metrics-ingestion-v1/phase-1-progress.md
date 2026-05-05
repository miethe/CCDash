---
type: progress
schema_version: 2
prd: otel-session-metrics-ingestion-v1
phase: 1
phase_title: Ingest Contract
status: in_progress
progress: 25
plan: docs/project_plans/implementation_plans/integrations/otel-session-metrics-ingestion-v1.md
updated: '2026-05-05'
tasks:
- id: P1-T1
  title: Add source-neutral ingest models
  status: completed
  assigned_to:
  - backend-platform
  dependencies: []
- id: P1-T2
  title: Define IngestSourceAdapter protocol
  status: pending
  assigned_to:
  - backend-platform
  dependencies:
  - P1-T1
- id: P1-T3
  title: Add source key and idempotency helpers
  status: pending
  assigned_to:
  - data-platform
  dependencies:
  - P1-T1
- id: P1-T4
  title: Add envelope validation and source key tests
  status: pending
  assigned_to:
  - testing
  dependencies:
  - P1-T1
  - P1-T2
  - P1-T3
parallelization:
  batch_1:
  - P1-T1
  batch_2:
  - P1-T2
  - P1-T3
  batch_3:
  - P1-T4
validation:
  required:
  - "backend/.venv/bin/python -m pytest backend/tests/test_session_ingest_contract.py -v"
  - "backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py backend/tests/test_sessions_codex_parser.py -v"
total_tasks: 4
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
---

# Phase 1 Progress: Ingest Contract

## Objective

Create source-neutral ingestion contracts before moving persistence code.

## Validation Notes

- Pending.
