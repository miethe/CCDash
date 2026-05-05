---
type: progress
schema_version: 2
doc_type: progress
prd: otel-session-metrics-ingestion-v1
feature_slug: otel-session-metrics-ingestion-v1
phase: 2
phase_title: Shared Persistence Refactor
status: in-progress
started: '2026-05-05'
updated: '2026-05-05'
prd_ref: docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/otel-session-metrics-ingestion-v1.md
commit_refs: []
pr_refs: []
owners:
- backend-platform
- data-platform
- observability
contributors:
- codex
tasks:
- id: P2-T1
  title: Extract JSONL session persistence into SessionIngestService
  status: completed
  assigned_to:
  - backend-platform
  dependencies:
  - P1-T1
  - P1-T2
  - P1-T3
  - P1-T4
  files:
  - backend/db/sync_engine.py
  - backend/ingestion/session_ingest_service.py
- id: P2-T2
  title: Keep sync-state and delete-by-source responsibilities in SyncEngine
  status: completed
  assigned_to:
  - backend-platform
  dependencies:
  - P2-T1
  files:
  - backend/db/sync_engine.py
  - backend/tests
- id: P2-T3
  title: Preserve repository construction and database profile selection
  status: completed
  assigned_to:
  - data-platform
  dependencies:
  - P2-T1
  files:
  - backend/db/sync_engine.py
  - backend/ingestion/session_ingest_service.py
- id: P2-T4
  title: Add and run JSONL sync regression coverage
  status: pending
  assigned_to:
  - testing
  dependencies:
  - P2-T1
  - P2-T2
  - P2-T3
  files:
  - backend/tests
- id: P2-T5
  title: Add source dimension to ingestion metrics
  status: pending
  assigned_to:
  - observability
  dependencies:
  - P2-T1
  files:
  - backend/observability/otel.py
  - backend/db/sync_engine.py
parallelization:
  batch_1:
  - P2-T1
  batch_2:
  - P2-T2
  - P2-T3
  batch_3:
  - P2-T4
  - P2-T5
total_tasks: 5
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
progress: 60
validation:
  required:
  - backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py backend/tests/test_sessions_codex_parser.py -v
  - backend/.venv/bin/python -m pytest backend/tests/test_sync_engine_transcript_live_updates.py backend/tests/test_sync_engine_session_intelligence.py -v
  - backend/.venv/bin/python -m pytest backend/tests/test_session_ingest_contract.py -v
---

# Phase 2 Progress: Shared Persistence Refactor

## Objective

Make JSONL session ingestion use the source-neutral persistence service without changing sync-state behavior, repository selection, frontend DTOs, or downstream session projections.

## Status

P2-T1 is complete. The complete JSONL persistence path now flows through `SessionIngestService.persist_envelope()`, with `jsonl_session_to_envelope()` bridging the existing parsed session payload into the normalized ingest contract.

`SyncEngine._sync_single_session()` still owns the file mtime/hash checks, parser invocation, source cleanup, relationship cleanup, sync-state update, and outer ingestion timing.

## Validation Notes

- `PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/test_session_ingest_service.py backend/tests/test_session_ingest_contract.py backend/tests/test_sync_engine_linking.py::SyncEngineSessionBackfillTests backend/tests/test_sync_engine_transcript_canonicalization.py backend/tests/test_sync_engine_session_intelligence.py backend/tests/test_file_watcher.py::JsonlAppendIncrementalSyncTests backend/tests/test_sync_engine_transcript_live_updates.py -q` passed: 20 passed in 2.83s.
- `PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/test_sync_engine_session_ingest_boundaries.py -q` passed: 2 passed in 1.17s.
- `PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/test_sync_engine_session_ingest_repository_wiring.py -q` passed: 2 passed in 0.66s.
