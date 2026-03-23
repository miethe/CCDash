---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements
title: "Implementation Plan: Session Transcript Append Deltas V1"
description: "Implement a transcript-specific live append path for active sessions so Session Inspector can merge newly persisted log entries incrementally while preserving coarse invalidation and REST recovery."
summary: "Add shared transcript topic helpers, publish append-safe session log deltas from ingestion, migrate Session Inspector to append-first behavior, and harden fallback coverage before rollout."
author: codex
owner: platform-engineering
owners: [platform-engineering, frontend-engineering, backend-platform]
contributors: [ai-agents]
audience: [ai-agents, developers, platform-engineering, frontend-engineering]
created: 2026-03-22
updated: 2026-03-22
tags: [implementation, sse, live-updates, sessions, transcript, append, frontend, backend]
priority: medium
risk_level: medium
complexity: medium
track: Platform
timeline_estimate: "4-6 days across 5 phases"
feature_slug: session-transcript-append-deltas-v1
feature_family: live-update-platform
feature_version: v1
lineage_family: live-update-platform
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/session-transcript-append-deltas-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
linked_features:
  - sse-live-update-platform-v1
related_documents:
  - docs/project_plans/PRDs/enhancements/session-transcript-append-deltas-v1.md
  - docs/project_plans/designs/session-transcript-append-deltas-v1.md
  - docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
  - docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md
  - docs/live-update-platform-developer-reference.md
context_files:
  - backend/application/live_updates/domain_events.py
  - backend/application/live_updates/topics.py
  - backend/db/sync_engine.py
  - backend/routers/live.py
  - backend/tests/test_live_domain_publishers.py
  - backend/tests/test_live_router.py
  - components/SessionInspector.tsx
  - services/live/topics.ts
  - services/live/connectionManager.ts
  - services/live/config.ts
  - services/__tests__/liveConnectionManager.test.ts

request_log_id: ""
commits: []
prs: []
---

# Implementation Plan: Session Transcript Append Deltas V1

## Objective

Extend the shared live-update platform so active session transcripts can receive append-safe log deltas over SSE, merge them directly into Session Inspector state, and preserve the current invalidation plus targeted REST refresh path whenever append delivery is unsafe or incomplete.

## Current Baseline

The core transport is already in place:

1. the backend supports append, invalidate, heartbeat, and `snapshot_required` events
2. topic replay and cursor tracking already work through the shared live broker and router
3. the frontend live connection manager already multiplexes subscriptions and routes per-topic recovery callbacks
4. Session Inspector already uses stream-first invalidation for active sessions and falls back to polling only when live transport is unavailable

The remaining gap is session-specific:

1. session live publishing is coarse-grained invalidation only
2. Session Inspector refreshes full detail instead of merging transcript deltas
3. there is no shared transcript-topic helper or append payload contract for sessions

## Scope and Fixed Decisions

1. V1 reuses the existing SSE platform and does not introduce a second transport.
2. Coarse `session.{session_id}` invalidation remains the safety net.
3. No database migration is planned for V1.
4. Transcript append events are emitted only for append-safe new log rows.
5. Any uncertainty in delta construction or merge ordering falls back to targeted REST refresh.
6. A dedicated frontend flag gates transcript append adoption independently from coarse session live updates.

## Architecture

## 1) Shared Topic and Payload Contract

Add a new transcript topic helper to the shared live-update modules.

Primary targets:

1. `backend/application/live_updates/topics.py`
2. `services/live/topics.ts`

Add or document a transcript append payload contract with:

1. session identifier
2. stable log or entry identifier
3. monotonic sequence number
4. normalized transcript kind
5. created-at timestamp
6. append payload matching Session Inspector needs

Guidelines:

1. keep the payload smaller than full session detail
2. prefer normalized Session Inspector-facing fields over raw storage internals
3. keep coarse invalidation as the fallback path for non-append-safe mutations

## 2) Backend Publish Path

Extend the session live publisher helpers and sync path to emit transcript appends when safe.

Primary targets:

1. `backend/application/live_updates/domain_events.py`
2. `backend/db/sync_engine.py`

Responsibilities:

1. compare the new sync view of a session against the previously known durable log identity boundary
2. identify newly persisted transcript rows in stable order
3. map those rows into transcript append payloads
4. publish append events to `session.{session_id}.transcript`
5. continue publishing coarse invalidation to `session.{session_id}` when status changes or append confidence is low

Implementation notes:

1. avoid recomputing the entire session detail model just to produce append payloads
2. do not rely on raw array position alone because session sync can rewrite or renumber stored logs
3. keep replay bounded; old cursors should still resolve through `snapshot_required`
4. update tests around domain publisher behavior and router replay expectations

## 3) Frontend Session Inspector Adoption

Migrate the active-session live path from invalidation-only to append-first plus fallback.

Primary targets:

1. `components/SessionInspector.tsx`
2. `services/live/config.ts`
3. `services/live/connectionManager.ts` if helper hooks need small extensions

Responsibilities:

1. add a dedicated transcript-append feature flag such as `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED`
2. subscribe active session views to both coarse session invalidation and transcript append topics
3. append safe transcript deltas directly into `selectedSession.logs`
4. suppress duplicates using stable log identity
5. trigger `getSessionById(sessionId, { force: true })` on `snapshot_required`, sequence mismatch, missing IDs, or non-append-safe invalidations
6. keep existing unhealthy-live polling fallback intact

Implementation notes:

1. isolate merge logic in a small helper rather than burying all rules in the effect callback
2. make header/status updates tolerant of append-only flows
3. preserve hidden-tab pause/backoff semantics already supported by the live client

## 4) Validation and Failure Handling

Cover correctness before rollout.

Primary targets:

1. `backend/tests/test_live_domain_publishers.py`
2. `backend/tests/test_live_router.py`
3. `services/__tests__/liveConnectionManager.test.ts`
4. frontend tests near Session Inspector if local coverage exists

Required scenarios:

1. append-safe session growth emits transcript append events in order
2. stale cursor gaps emit `snapshot_required` for the transcript topic
3. duplicate or mismatched append events trigger fallback rather than silent corruption
4. active-session viewing recovers after hidden-tab resume or reconnect
5. coarse invalidation remains correct for status changes and transcript rewrites

## 5) Rollout and Documentation

Ship behind a staged flag and measure fallback frequency.

Primary targets:

1. `docs/live-update-platform-developer-reference.md`
2. `.env.example` or equivalent env documentation if live flags are listed there

Responsibilities:

1. document the new topic and payload contract
2. document when publishers must choose append versus invalidation
3. validate request-volume improvement in local or dev testing
4. keep rollback simple by disabling only the transcript-append flag

## Phase Plan

## Phase 1: Topic and Contract Foundations

**Assigned Subagent(s)**: backend-architect, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| TXAPP-101 | Transcript Topic Helpers | Add `sessionTranscriptTopic` helpers to backend and frontend live topic modules. | Both stacks can construct the transcript topic consistently for a given session id. | 1 pt | backend-architect, frontend-developer | None |
| TXAPP-102 | Append Payload Contract | Define and document the normalized session transcript append payload shape. | Backend publishers and frontend merge logic share one documented append contract. | 1 pt | backend-architect | TXAPP-101 |

**Phase 1 Quality Gates**

1. Topic naming is consistent with current live-update normalization rules.
2. Payload shape is small, append-oriented, and sufficient for Session Inspector merging.

## Phase 2: Backend Transcript Publishers

**Assigned Subagent(s)**: python-backend-engineer, backend-architect

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| TXAPP-201 | Delta Detection in Sync Path | Detect newly persisted transcript rows without treating every sync as a full snapshot update, using durable transcript identity rather than raw row position. | Sync path can identify append-safe new rows in stable order for active sessions even when parsed logs are rewritten or re-numbered. | 2 pts | python-backend-engineer | TXAPP-102 |
| TXAPP-202 | Transcript Append Publisher | Publish append-safe transcript deltas to `session.{session_id}.transcript` and keep coarse invalidation for unsafe changes. | Backend emits transcript append events for normal growth and invalidation for unsafe mutations. | 2 pts | python-backend-engineer, backend-architect | TXAPP-201 |
| TXAPP-203 | Backend Publisher Tests | Extend publisher/router coverage for transcript append, replay, and snapshot fallback. | Automated tests cover append order, cursor gaps, and fallback semantics. | 1 pt | python-backend-engineer | TXAPP-202 |

**Phase 2 Quality Gates**

1. Append events are ordered and bounded by the existing replay model.
2. Unsafe or ambiguous session updates still recover through invalidation.

## Phase 3: Frontend Session Inspector Migration

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| TXAPP-301 | Transcript Append Flag | Add a dedicated frontend rollout flag for transcript append behavior. | Transcript append can be enabled or disabled independently of coarse session live updates. | 1 pt | frontend-developer | TXAPP-102 |
| TXAPP-302 | Dual-Topic Subscription | Subscribe active Session Inspector views to transcript append and coarse session invalidation topics. | Active sessions listen to both topics without duplicating fallback behavior. | 2 pts | frontend-developer | TXAPP-202, TXAPP-301 |
| TXAPP-303 | Merge Helper and Fallback Rules | Append transcript rows into local state with duplicate suppression and sequence checks, falling back to REST refresh on mismatch. | Normal appends merge in place; unsafe events trigger targeted refetch instead of corrupting UI state. | 2 pts | frontend-developer, ui-engineer-enhanced | TXAPP-302 |

**Phase 3 Quality Gates**

1. Active append-only sessions update without full-detail flashes in the common path.
2. The existing live-health polling fallback remains intact when streaming is disabled or degraded.

## Phase 4: Recovery and Regression Coverage

**Assigned Subagent(s)**: frontend-developer, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| TXAPP-401 | Reconnect and Hidden-Tab Recovery | Validate transcript append behavior across reconnect, hidden-tab pause/resume, and backend restart scenarios. | Recovery paths behave like current session live updates, with append-first optimization where possible. | 1 pt | frontend-developer, python-backend-engineer | TXAPP-303 |
| TXAPP-402 | Duplicate and Rewrite Guardrails | Add tests or assertions for duplicate events, missing identifiers, sequence mismatches, and transcript rewrite fallback. | Unsafe transcript mutations do not silently corrupt Session Inspector state. | 1 pt | frontend-developer, python-backend-engineer | TXAPP-401 |

**Phase 4 Quality Gates**

1. Replay gaps and bad payloads deterministically trigger recovery.
2. No regression appears in inactive or historical session viewing.

## Phase 5: Rollout, Metrics, and Documentation

**Assigned Subagent(s)**: documentation-writer, backend-architect, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| TXAPP-501 | Topic and Rollout Documentation | Document the transcript topic, append payload, and fallback rules. | Developers can adopt or debug transcript append delivery without rediscovering the contract. | 1 pt | documentation-writer | TXAPP-402 |
| TXAPP-502 | Rollout Validation | Compare request behavior for hot active sessions with the flag on versus off. | Rollout notes include evidence that append-first delivery reduces full-detail refresh traffic. | 1 pt | backend-architect, frontend-developer | TXAPP-501 |

**Phase 5 Quality Gates**

1. Rollout is reversible through one dedicated flag.
2. Developer docs and validation notes are sufficient for future follow-on work.

## Risks and Mitigations

1. Risk: sync-layer delta detection may not reliably identify only new transcript rows because session ingestion can rewrite or renumber stored logs.
   Mitigation: fall back to coarse invalidation when append-safe boundaries cannot be proven.
2. Risk: frontend merge logic may couple too tightly to current log shapes.
   Mitigation: normalize an explicit append payload contract and keep merge code isolated.
3. Risk: replay buffers may be too short for some hidden-tab resume windows.
   Mitigation: rely on existing `snapshot_required` semantics instead of enlarging scope in V1.

## Exit Criteria

1. Active append-only session growth normally updates Session Inspector through transcript append events.
2. The system still recovers cleanly through coarse invalidation and targeted REST refresh when append delivery is unsafe.
3. A dedicated transcript append flag, automated coverage, and developer documentation are in place.
