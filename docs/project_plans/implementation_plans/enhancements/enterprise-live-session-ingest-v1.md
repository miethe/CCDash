---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: phased_plan
status: in-progress
category: enhancements
title: Enterprise Live Session Ingest V1 - Implementation Plan
description: Phased implementation for watcher-capable enterprise workers and cross-process
  live session fanout.
summary: Adds an explicit watcher worker mode, compose/operator support, shared Postgres-backed
  live fanout, and validation for near-live session ingestion in the enterprise stack.
author: codex
created: 2026-05-01
updated: '2026-05-02'
audience:
- ai-agents
- developers
- backend-platform
- devops
tags:
- implementation
- enterprise
- live-updates
- sessions
- worker
- watcher
- postgres
related:
- docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
- docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
- docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
---

# Implementation Plan: Enterprise Live Session Ingest V1

Plan ID: `IMPL-2026-05-01-ENTERPRISE-LIVE-SESSION-INGEST`

Related documents:

1. PRD: `docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md`
2. SSE platform PRD: `docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md`
3. Transcript append PRD: `docs/project_plans/PRDs/enhancements/session-transcript-append-deltas-v1.md`
4. Deployment runtime modularization PRD: `docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md`

Complexity: Medium

Total estimated effort: 39 points

Target timeline: 1-2 weeks

## Executive Summary

Implement enterprise live sessions in two steps: first, make filesystem live ingest an explicit worker capability; second, bridge worker-published live events into the API process that owns browser SSE streams. The design preserves the hosted API's no-watch contract while giving operators a clear `worker-watch` role for local/shared-host deployments with mounted session directories.

## Implementation Strategy

Architecture sequence:

1. Runtime capability and storage contract updates.
2. Watcher worker compose/env/operator support.
3. Cross-process live fanout adapter.
4. Probe, docs, and frontend recovery validation.
5. Integration testing and rollout hardening.

Critical path:

1. `worker-watch` profile exists and starts file watcher.
2. `sync_changed_files` persists active session changes.
3. Worker live events traverse shared fanout to API SSE broker.

Parallel work:

1. Compose/docs can start after runtime profile naming is decided.
2. Live fanout adapter tests can run in parallel with watcher runtime tests.
3. Frontend validation is mostly configuration and smoke testing because the SSE client already exists.

## Phase Overview

| Phase | Title | Estimate | Primary Subagents | Outcome |
|-------|-------|----------|-------------------|---------|
| 1 | Runtime Capability Model | 7 pts | backend-architect, python-backend-engineer | Add explicit watcher-capable enterprise worker role. |
| 2 | Compose and Operator Contract | 6 pts | DevOps, python-backend-engineer | Make watcher worker runnable and documented. |
| 3 | Shared Live Event Fanout | 12 pts | backend-architect, data-layer-expert, python-backend-engineer | Deliver worker events to API SSE subscribers. |
| 4 | Health, Observability, and Recovery | 6 pts | backend-architect, DevOps | Expose watcher/fanout health and safe fallback behavior. |
| 5 | Validation and Documentation | 8 pts | python-backend-engineer, frontend-developer, documentation-writer | Prove live ingest and update docs/tests. |

## Phase 1: Runtime Capability Model

Assigned Subagents: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
|---------|-----------|-------------|---------------------|----------|--------------|
| RUN-001 | Add Watcher Worker Profile | Add an explicit `worker-watch` runtime profile or equivalent role with `watch=True`, `sync=True`, `jobs=True`, `auth=False`, recommended storage `enterprise`. | Profile exists; default `worker` remains no-watch; `api` remains no-watch/no-sync. | 2 pts | None |
| RUN-002 | Storage Contract Update | Extend runtime storage contract/readiness semantics for watcher worker. | Enterprise storage allowed; readiness checks include DB, migrations, worker binding, watcher runtime. | 2 pts | RUN-001 |
| RUN-003 | Bootstrap Compatibility | Ensure worker bootstrap accepts the new runtime profile and starts the existing file watcher only for watcher-capable profiles. | `file_watcher.start` is called for `worker-watch`, not `worker` or `api`. | 2 pts | RUN-001 |
| RUN-004 | Runtime Tests | Add tests covering profile capabilities and watcher startup gating. | Tests fail if API gains watcher ownership or default worker changes unexpectedly. | 1 pt | RUN-003 |

Quality gates:

1. Runtime profile matrix is explicit.
2. API remains stateless/background-free.
3. Existing local runtime behavior is unchanged.

## Phase 2: Compose and Operator Contract

Assigned Subagents: DevOps, python-backend-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
|---------|-----------|-------------|---------------------|----------|--------------|
| OPS-001 | Compose Service | Add a `worker-watch` compose service/profile using the backend image, existing Postgres env, project binding, and read-only ingest mounts. | Operator can start it with a documented profile; service has probe port separate from default worker if both run. | 2 pts | RUN-001 |
| OPS-002 | Env Examples | Add env vars for watcher worker project id, probe port, and optional `WATCHFILES_FORCE_POLLING`. | `.env.example` explains macOS Docker Desktop polling mode and one-project-per-worker limitation. | 1 pt | OPS-001 |
| OPS-003 | Mount Validation Guidance | Document required mounts for `projects.json`, workspace root, `.claude`, and `.codex`. | Troubleshooting table explains missing paths and watcher "nothing to monitor". | 1 pt | OPS-001 |
| OPS-004 | Worker Coexistence | Decide whether `worker-watch` replaces `worker` locally or co-runs with a unique probe port. | Compose supports a clear local enterprise recipe without port conflicts. | 2 pts | OPS-001 |

Quality gates:

1. `docker compose config` validates.
2. Operator can run API + frontend + Postgres + watcher worker.
3. Health endpoints are reachable for each worker role.

## Phase 3: Shared Live Event Fanout

Assigned Subagents: backend-architect, data-layer-expert, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
|---------|-----------|-------------|---------------------|----------|--------------|
| LIVE-001 | Fanout Adapter Design | Define a live event bus abstraction separate from the current in-memory broker. | API can subscribe; worker can publish; local mode can keep in-memory-only behavior. | 2 pts | RUN-001 |
| LIVE-002 | Postgres Notify Publisher | Implement a Postgres-backed publisher using compact event envelopes and channel naming scoped to CCDash. | Worker publishes invalidation/append events without depending on API process memory. | 3 pts | LIVE-001 |
| LIVE-003 | API Notify Subscriber | Add API-side listener that receives Postgres notifications and republishes into the API in-memory SSE broker. | Browser `/api/live/stream` receives worker-originated events. | 3 pts | LIVE-002 |
| LIVE-004 | Payload Size Guard | Handle Postgres `NOTIFY` payload limits by emitting compact invalidation events or storing large payloads elsewhere. | Large transcript append payloads do not break listener loop; fallback is deterministic. | 2 pts | LIVE-002 |
| LIVE-005 | Fanout Tests | Add integration tests for worker publish -> API subscriber -> SSE broker delivery. | Tests cover duplicate event handling, malformed notifications, and reconnect. | 2 pts | LIVE-003 |

Quality gates:

1. Worker-originated session invalidations reach API SSE subscribers.
2. Event authorization remains enforced at API subscription time.
3. Fanout failures do not block Postgres ingestion.

## Phase 4: Health, Observability, and Recovery

Assigned Subagents: backend-architect, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
|---------|-----------|-------------|---------------------|----------|--------------|
| OBS-001 | Watcher Probe Fields | Add watcher enabled/running state, watch path count, and last change-sync marker to detail probes where practical. | `detailz` distinguishes "not expected", "running", and "configured but no paths". | 2 pts | RUN-003 |
| OBS-002 | Fanout Probe Fields | Expose live fanout connected/error counters in API detail or cache status. | Operators can see listener health and recent fanout errors. | 2 pts | LIVE-003 |
| OBS-003 | Structured Logs | Add logs for watcher start paths, classified changes, sync result, and fanout publish/listen failures. | Troubleshooting can rely on logs without code instrumentation. | 1 pt | OBS-001 |
| OBS-004 | Recovery Semantics | Confirm browser REST refresh still recovers when fanout is down and sync persists rows. | Documented fallback path; tests or manual smoke prove no hard dependency on live fanout. | 1 pt | LIVE-003 |

Quality gates:

1. Readiness/degraded states are actionable.
2. Fanout degradation is visible but does not make ingestion fail.
3. Existing cache/status behavior remains compatible.

## Phase 5: Validation and Documentation

Assigned Subagents: python-backend-engineer, frontend-developer, documentation-writer, DevOps

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
|---------|-----------|-------------|---------------------|----------|--------------|
| TEST-001 | Runtime Unit Tests | Cover runtime profile/storage contract matrix and watcher gating. | Existing runtime bootstrap tests pass with new profile. | 1 pt | RUN-004 |
| TEST-002 | Watcher Integration Test | Simulate a JSONL append in a watched sessions directory and assert incremental sync updates Postgres. | Test proves no worker restart is required. | 2 pts | OPS-001 |
| TEST-003 | Browser Live Smoke | Validate active Session Inspector updates through SSE when worker-watch ingests a session change. | Manual or automated smoke records event arrival and UI refresh. | 2 pts | LIVE-005 |
| TEST-004 | Compose Smoke | Add or document a compose smoke procedure for enterprise live session ingest. | Procedure includes command, expected probes, append test, and DB count check. | 1 pt | OPS-004 |
| DOC-001 | Runtime Docs | Update `deploy/runtime/README.md` and env examples with live-watch setup. | Docs explain profiles, project binding, mounts, polling mode, and one-project limitation. | 1 pt | TEST-004 |
| DOC-002 | Developer Reference | Update live-update developer docs with cross-process fanout architecture. | Docs identify in-memory vs Postgres fanout responsibilities. | 1 pt | LIVE-005 |

Quality gates:

1. Targeted backend tests pass.
2. Compose stack can demonstrate live ingest.
3. Docs are sufficient for an operator to reproduce setup.

## Rollout Plan

1. Ship `worker-watch` as opt-in.
2. Keep current `worker` behavior unchanged for scheduled jobs/startup sync.
3. Recommend local enterprise users start `worker-watch` instead of, or alongside, default worker depending on whether they need scheduled jobs separated.
4. Enable Postgres fanout only in enterprise storage mode.
5. Revisit multi-project watching after v1 proves one-project watcher stability.

## Validation Commands

Representative commands for final verification:

```bash
docker compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch \
  up --build

curl -sS http://localhost:9465/detailz | python3 -m json.tool

docker compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch \
  exec -T postgres psql -U ccdash -d ccdash \
  -c "select count(*) from sessions;"
```

## Open Questions

1. Should `worker-watch` replace default `worker` in local enterprise examples, or run as a separate service with a separate probe port?
2. Should Postgres fanout be always-on for enterprise, or guarded by an env flag for staged rollout?
3. Are transcript append payloads small enough for Postgres `NOTIFY`, or should v1 use invalidation-only cross-process events?
4. Should watcher workers support Codex and Claude homes as separate enabled source groups in probes?

## Completion Criteria

1. Watcher worker mode exists and is documented.
2. New active session writes are ingested into Postgres without restart.
3. Worker-originated live session events reach browser SSE subscribers.
4. API remains watcher-free.
5. Tests and docs cover the new operator path.
