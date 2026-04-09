---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: completed
category: enhancements
title: "Implementation Plan: SSE Live Update Platform V1"
description: "Implement a reusable server-sent events transport, broker, and frontend subscription layer that can replace hot polling loops across CCDash."
summary: "Sequence live-update work through broker/contract foundations, stream endpoint delivery, frontend connection management, surface migrations, and hardening with staged fallbacks."
author: codex
audience: [ai-agents, developers, platform-engineering, frontend-engineering]
created: 2026-03-11
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/e091a60
- https://github.com/miethe/CCDash/commit/7a51d30
pr_refs: []
tags: [implementation, sse, live-updates, transport, polling, realtime]
priority: high
risk_level: medium
complexity: high
track: Platform
timeline_estimate: "2-3 weeks across 6 phases"
feature_slug: sse-live-update-platform-v1
feature_family: live-update-platform
feature_version: v1
lineage_family: live-update-platform
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
linked_features: []
related_documents:
  - docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
  - docs/project_plans/implementation_plans/live-update-animations-v1.md
  - docs/execution-workbench-developer-reference.md
  - docs/live-update-platform-developer-reference.md
  - docs/project_plans/designs/session-transcript-append-deltas-v1.md
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
context_files:
  - backend/main.py
  - backend/routers/api.py
  - backend/routers/execution.py
  - backend/db/sync_engine.py
  - backend/services/execution_runtime.py
  - contexts/DataContext.tsx
  - components/SessionInspector.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/ProjectBoard.tsx
  - components/TestVisualizer/hooks.ts
  - components/OpsPanel.tsx
  - services/execution.ts
---

# Implementation Plan: SSE Live Update Platform V1

## Objective

Implement a reusable live-update substrate for CCDash that delivers scoped server-sent events to the frontend, supports reconnect and targeted recovery, and can be adopted incrementally by execution, sessions, features, tests, and ops surfaces. The implementation must reduce polling pressure without forcing a risky all-at-once state-management rewrite.

## Delivery Status

Status: completed on 2026-03-15

Delivered in phases 1-6:

1. shared contracts, broker, replay, heartbeat, and frontend connection management
2. execution stream append delivery and stream-first workbench recovery
3. session live invalidation and targeted REST recovery without the old 5s polling loop as the primary path
4. feature board/modal invalidation topics and global feature refresh cues
5. test visualizer and ops panel stream-first invalidation with polling fallback
6. broker observability, rollout flags, and developer documentation

Residual risk carried from phases 3-4:

1. session live updates currently use invalidation plus targeted REST refresh rather than transcript append deltas
2. that still satisfies the V1 migration goal because the old 5s session polling loop is no longer the primary live path
3. transcript append streaming remains the clearest follow-up if session traffic or payload size grows materially

## Fixed Decisions

1. Use SSE (`text/event-stream`) as the server-to-client protocol for V1.
2. Keep existing REST endpoints as bootstrap and recovery paths.
3. Introduce a generic `LiveEventBroker`/publisher boundary instead of binding domain code directly to transport concerns.
4. Support both append deltas and invalidation events.
5. Use one shared frontend live client with multiplexed topic subscriptions per browser tab where feasible.
6. Keep per-surface fallback polling until each adopter is proven stable.

## Scope and Guardrails

In scope:

1. Shared live event contract and broker abstraction.
2. SSE endpoint, heartbeat, reconnect, and replay-gap handling.
3. Frontend connection manager and subscription hooks/utilities.
4. Migration of selected live surfaces to the shared platform.
5. Metrics, flags, and operational controls.

Out of scope:

1. WebSocket transport.
2. Full persistent event-store architecture.
3. Distributed broker deployment in this phase.
4. Migration of every polling loop in the application.

Non-negotiables:

1. Surface rollouts must be reversible behind flags.
2. The stream payload must avoid heavyweight recomputation where invalidation is sufficient.
3. Auth/project scoping must be preserved by design even if local mode is permissive today.
4. The implementation should leave clean seams for the hexagonal/runtime refactor rather than adding another permanent singleton.

## Proposed Module Targets

Backend:

1. `backend/application/live_updates/`
   - `contracts.py`
   - `topics.py`
   - `broker.py`
   - `publisher.py`
2. `backend/adapters/live_updates/`
   - `in_memory_broker.py`
   - `sse_stream.py`
3. `backend/routers/live.py`
4. runtime wiring in `backend/main.py` or a runtime bootstrap seam

Frontend:

1. `services/live/`
   - `types.ts`
   - `client.ts`
   - `connectionManager.ts`
   - `topics.ts`
2. `components/animations/` or `services/live/` integration with existing `LiveUpdateTransport` intent
3. focused adoption helpers:
   - `useLiveExecutionRun`
   - `useLiveSessionTranscript`
   - `useLiveInvalidation`

Exact paths may shift, but the end state must separate event contracts, transport internals, and surface adapters.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Event Contract and Broker Foundation | 8 pts | 3-4 days | Yes | Define the shared live-update model and publish/subscribe abstraction |
| 2 | SSE Delivery Endpoint and Runtime Wiring | 9 pts | 4 days | Yes | Ship the stream endpoint, heartbeat, topic subscription, and local runtime adapter |
| 3 | Frontend Shared Live Client | 10 pts | 4-5 days | Yes | Build connection management, subscription APIs, replay handling, and fallback hooks |
| 4 | Execution and Session Adoption | 12 pts | 4-5 days | Yes | Migrate the highest-value hot polling surfaces first |
| 5 | Feature, Test, and Ops Adoption | 10 pts | 4-5 days | Partial | Extend the platform to invalidation-oriented surfaces |
| 6 | Hardening, Metrics, and Rollout | 7 pts | 3 days | Final gate | Add observability, QA, rollout flags, and docs |

**Total**: ~56 story points over 2-3 weeks

## Implementation Strategy

### Adoption Order

1. Define the shared event contract before any surface-specific work.
2. Use execution run events as the first streaming adopter because they already model ordered incremental updates.
3. Migrate session transcript live updates next, replacing repeated full-detail polling with append/invalidation.
4. Extend to feature/test/ops surfaces using invalidation events where append semantics are not worth the complexity.
5. Preserve polling as a fallback at every phase until the stream path is stable.

### Why This Order

1. Execution already has a sequence-based event model and the hottest poll cadence in the app.
2. Session inspector is the most visible costly live read path.
3. Feature/test/ops surfaces benefit from the shared client and broker once the core substrate exists, but they do not need to define the event model.

## Phase 1: Event Contract and Broker Foundation

**Assigned Subagent(s)**: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-001 | Event Envelope Contract | Define typed live event envelope, delivery hints, topic naming, replay cursor semantics, and topic authorization inputs. | Contract is documented in code and test fixtures; append/invalidate/heartbeat/snapshot-required are supported. | 3 pts | backend-architect | None |
| LIVE-002 | Broker Port and Publisher API | Introduce `LiveEventBroker` and publish helper interfaces that domain code can use without transport coupling. | Domain publishers can emit events without importing router/stream implementation details. | 3 pts | backend-architect, python-backend-engineer | LIVE-001 |
| LIVE-003 | In-Memory Broker Adapter | Implement local-runtime broker with topic fan-out, bounded buffers for replay, and backpressure/drop accounting. | Local runtime can publish and subscribe in-process with bounded memory behavior. | 2 pts | python-backend-engineer | LIVE-002 |

**Phase 1 Quality Gates**

1. Broker/publisher boundaries are explicit and testable.
2. Topic and cursor contracts are stable enough for frontend integration.
3. Replay buffer limits and failure semantics are documented.

## Phase 2: SSE Delivery Endpoint and Runtime Wiring

**Assigned Subagent(s)**: backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-101 | Stream Router | Add `GET /api/live/stream` with topic subscription input, heartbeat frames, disconnect cleanup, and SSE framing. | Stream endpoint serves valid `text/event-stream` responses and cleans up subscribers on disconnect. | 4 pts | python-backend-engineer | LIVE-003 |
| LIVE-102 | Runtime Composition | Wire broker/publisher into backend startup without hard-coding transport logic into every router. | Local runtime boots with broker attached; the path is ready to move under future runtime composition work. | 2 pts | backend-architect | LIVE-003 |
| LIVE-103 | Replay and Snapshot-Required Semantics | Support replay from recent buffered events where possible, emit `snapshot_required` when the requested cursor cannot be satisfied. | Clients can reconnect using last cursor; gap behavior is deterministic and tested. | 3 pts | python-backend-engineer | LIVE-101 |

**Phase 2 Quality Gates**

1. Stream endpoint survives connect/disconnect churn.
2. Heartbeats prevent idle timeout drift in local dev/proxy conditions.
3. Replay miss behavior is explicit instead of silently dropping events.

## Phase 3: Frontend Shared Live Client

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-201 | Shared Connection Manager | Build a shared live client that multiplexes topics over one stream, ref-counts subscriptions, and exposes connect/disconnect status. | Multiple consumers reuse the same underlying stream connection where topic scope allows. | 4 pts | frontend-developer | LIVE-103 |
| LIVE-202 | Cursor Persistence and Recovery | Track the latest cursor per topic/subscription and handle `snapshot_required` by invoking caller-provided recovery callbacks. | Disconnect/reconnect preserves state or triggers targeted REST catch-up instead of blind full refresh. | 3 pts | frontend-developer | LIVE-201 |
| LIVE-203 | Fallback and Visibility Policy | Add visibility-aware pause/backoff rules and seamless fallback to existing polling when streaming is disabled or unavailable. | Surface adapters can choose stream-first with polling fallback using one shared pattern. | 3 pts | ui-engineer-enhanced, frontend-developer | LIVE-201 |

**Phase 3 Quality Gates**

1. Shared client works with at least two independent subscribers in the same view.
2. Fallback behavior does not duplicate both stream and poll updates simultaneously.
3. Client APIs are generic enough for execution, sessions, and invalidation-only surfaces.

## Phase 4: Execution and Session Adoption

**Assigned Subagent(s)**: python-backend-engineer, frontend-developer, backend-architect

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-301 | Execution Run Publishers | Publish execution run state changes and run event appends from the runtime/service path to `execution.run.{run_id}` and related topics. | Active run panel can receive output and state updates over the shared live client. | 4 pts | python-backend-engineer | LIVE-203 |
| LIVE-302 | Execution Workbench Migration | Replace the 900ms active-run polling loop with stream-first behavior plus targeted REST recovery. | `FeatureExecutionWorkbench` no longer depends on tight interval polling when the flag is enabled. | 3 pts | frontend-developer | LIVE-301 |
| LIVE-303 | Session Transcript Publishers | Publish transcript append and session-status updates for active sessions, using append or invalidate semantics as appropriate. | Session detail no longer needs repeated full `GET /api/sessions/{id}` polling for live transcript freshness. | 3 pts | python-backend-engineer, backend-architect | LIVE-203 |
| LIVE-304 | Session Inspector Migration | Replace live session-detail polling with stream-driven transcript/status updates and bounded recovery paths. | Active session inspector behaves correctly across reconnect, tab switches, and replay gaps. | 2 pts | frontend-developer | LIVE-303 |

**Phase 4 Quality Gates**

1. Execution and session surfaces remain accurate through disconnect/reconnect.
2. Stream payloads avoid full-detail recomputation for every message.
3. Existing non-live/historical flows remain unchanged.

## Phase 5: Feature, Test, and Ops Adoption

**Assigned Subagent(s)**: frontend-developer, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-401 | Feature Invalidation Topics | Publish feature/project invalidation events for modal history/session surfaces and global feature refresh cues. | `ProjectBoard` and related feature views can refetch on invalidation instead of timer loops. | 3 pts | python-backend-engineer | LIVE-304 |
| LIVE-402 | Test Visualizer Live Hook Integration | Add stream-first invalidation or lightweight delta updates for active test views, preserving feature-flag gating already present in test hooks. | `useLiveTestUpdates` can consume live updates with polling fallback. | 3 pts | frontend-developer, python-backend-engineer | LIVE-401 |
| LIVE-403 | Ops/Sync Live Status | Publish operation/status invalidation events and migrate `OpsPanel` refresh behavior where feasible. | Running ops status can refresh without its own independent tight polling loop. | 2 pts | python-backend-engineer, frontend-developer | LIVE-401 |
| LIVE-404 | Shared Invalidation Helpers | Generalize frontend invalidation adapters so future surfaces can subscribe without bespoke stream parsing. | New surfaces can plug into invalidation topics with minimal custom code. | 2 pts | frontend-developer | LIVE-402 |

**Phase 5 Quality Gates**

1. At least one non-append domain successfully uses invalidation events.
2. Feature/test/ops migrations use the same shared client and recovery rules.
3. No surface regression requires global page refresh to recover.

## Phase 6: Hardening, Metrics, and Rollout

**Assigned Subagent(s)**: backend-architect, frontend-developer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| LIVE-501 | Observability and Metrics | Add counters/logging for active connections, topics, reconnects, replay misses, dropped publishes, and client lag. | Operators can see stream health and detect runaway reconnect or fan-out issues. | 2 pts | backend-architect | LIVE-404 |
| LIVE-502 | Feature Flags and Safe Rollout | Add per-surface flags so execution/session/feature/test/ops adoption can be enabled independently. | Rollout is staged and reversible without code removal. | 2 pts | frontend-developer | LIVE-404 |
| LIVE-503 | QA and Failure Injection | Validate disconnects, stale cursors, hidden-tab resume, backend restart recovery, and fallback behavior. | Manual QA matrix and automated coverage exist for the core failure paths. | 2 pts | frontend-developer, python-backend-engineer | LIVE-501 |
| LIVE-504 | Developer Documentation | Document event topics, payload classes, subscription conventions, and rollout guidance. | Future feature work can adopt the live platform without rediscovering transport rules. | 1 pt | documentation-writer | LIVE-501 |

**Phase 6 Quality Gates**

1. Stream health is measurable.
2. Rollout can be controlled per surface.
3. Core failure modes have both documented and tested recovery behavior.

## Cross-Cutting Technical Notes

### Event Publishing Strategy

Publish from the point where mutation or ingestion already occurs:

1. execution runtime writes
2. sync engine session/file discovery
3. service-layer mutations for features/ops

Avoid publishing from read paths unless emitting invalidation that is already known to be necessary.

### Replay Strategy

Use a pragmatic replay model:

1. If the domain has a natural ordered sequence and recent buffer, replay from cursor.
2. If it does not, emit `snapshot_required`.
3. Let the consumer invoke domain-specific REST catch-up.

This keeps V1 robust without forcing a generalized persistent event log.

### Auth and Runtime Compatibility

Even if local mode remains permissive:

1. topic filtering must accept request/project context
2. the frontend client must not assume native `EventSource` is the only viable client path
3. payloads should avoid leaking data beyond what the corresponding REST endpoint would expose

## Testing Strategy

### Backend Tests

1. Broker publish/subscribe fan-out and bounded replay behavior.
2. SSE framing and disconnect cleanup.
3. Replay success and `snapshot_required` on cursor gaps.
4. Topic authorization/scoping behavior.
5. Publisher integration tests for execution and session flows.

### Frontend Tests

1. Shared connection manager multiplexing and ref-count behavior.
2. Cursor persistence and recovery callbacks.
3. Stream-first plus polling fallback coordination.
4. Execution and session surface adoption flows.
5. Invalidations driving refetch without duplicate loops.

### Manual QA

1. View one active session for multiple minutes; verify request volume stays bounded.
2. Run one active execution; verify live output arrives without 900ms polling.
3. Hide and restore the tab; verify reconnect and recovery.
4. Restart backend during active stream; verify automatic reconnect and catch-up.
5. Toggle surface flags off; verify fallback polling still works.

## Rollout Order

1. Ship broker and stream endpoint dark.
2. Enable for execution in development.
3. Enable for live session inspector in development.
4. Enable invalidation surfaces one at a time.
5. Promote to default after metrics show reduced polling and stable reconnect behavior.

## Acceptance Criteria

1. Shared SSE transport is available behind a stable frontend and backend abstraction.
2. Execution run updates no longer need tight polling when the feature flag is enabled.
3. Active session transcript updates no longer depend on repeated full-detail polling.
4. At least one additional surface adopts invalidation-driven live updates through the same client.
5. Disconnect/reconnect/replay-gap behavior is explicitly handled and observable.
