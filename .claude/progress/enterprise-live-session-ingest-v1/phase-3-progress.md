---
type: progress
schema_version: 2
doc_type: progress
prd: enterprise-live-session-ingest-v1
feature_slug: enterprise-live-session-ingest-v1
prd_ref: /docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
plan_ref: /docs/project_plans/implementation_plans/enhancements/enterprise-live-session-ingest-v1.md
phase: 3
title: Shared Live Event Fanout
status: completed
started: '2026-05-02'
completed: '2026-05-02'
commit_refs:
- 0a27b0f
- 2b46b82
- c30ae07
pr_refs: []
overall_progress: 100
completion_estimate: completed
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- data-layer-expert
- python-backend-engineer
contributors:
- codex
tasks:
- id: LIVE-001
  description: Define a live event bus abstraction separate from the current in-memory broker.
  status: completed
  assigned_to:
  - backend-architect
  dependencies:
  - RUN-001
  estimated_effort: 2pt
  priority: high
- id: LIVE-002
  description: Implement a Postgres-backed publisher using compact event envelopes and channel naming scoped to CCDash.
  status: completed
  assigned_to:
  - data-layer-expert
  - python-backend-engineer
  dependencies:
  - LIVE-001
  estimated_effort: 3pt
  priority: high
- id: LIVE-003
  description: Add API-side listener that receives Postgres notifications and republishes into the API in-memory SSE broker.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - LIVE-002
  estimated_effort: 3pt
  priority: high
- id: LIVE-004
  description: Handle Postgres `NOTIFY` payload limits with compact invalidation events and deterministic fallback.
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - LIVE-002
  estimated_effort: 2pt
  priority: high
- id: LIVE-005
  description: Add integration tests for worker publish -> API subscriber -> SSE broker delivery.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - LIVE-003
  estimated_effort: 2pt
  priority: high
parallelization:
  batch_1:
  - LIVE-001
  batch_2:
  - LIVE-002
  - LIVE-004
  batch_3:
  - LIVE-003
  batch_4:
  - LIVE-005
  critical_path:
  - LIVE-001
  - LIVE-002
  - LIVE-003
  - LIVE-005
  estimated_total_time: 12pt / 3-4 days
blockers: []
success_criteria:
- Worker-originated session invalidations reach API SSE subscribers.
- Event authorization remains enforced at API subscription time.
- Fanout failures do not block Postgres ingestion.
files_modified:
- backend/application/live_updates/bus.py
- backend/application/live_updates/__init__.py
- backend/adapters/live_updates/postgres_notify.py
- backend/adapters/live_updates/postgres_listener.py
- backend/adapters/live_updates/__init__.py
- backend/runtime/container.py
- backend/tests/test_postgres_live_fanout.py
progress: 100
updated: '2026-05-02'
---

# enterprise-live-session-ingest-v1 - Phase 3

## Objective

Bridge worker-originated live events into the API process that owns browser SSE streams.

## Status

Phase 3 is complete. Worker and watcher-worker enterprise Postgres runtimes publish compact CCDash-scoped live notifications through Postgres `NOTIFY`. The API runtime listens on the same channel and republishes notifications into its in-memory SSE broker.

V1 fanout intentionally downgrades cross-process append payloads to invalidations with `rest_snapshot` recovery hints. Large or nested payloads are stripped from the NOTIFY envelope so Postgres payload limits cannot break the listener loop. The browser remains authorized at API subscription time; the fanout transport only moves already-scoped event topics into the API broker.

Validation covered compact envelope encode/decode, append-to-invalidation behavior, payload-size guardrails, malformed notification handling, and worker publish -> API listener -> in-memory broker delivery.
