---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: product_prd
status: completed
category: enhancements
title: 'PRD: Session Transcript Append Deltas V1'
description: Add transcript-specific live append delivery so active Session Inspector
  views can merge new log entries incrementally instead of re-fetching full session
  detail on every update.
summary: Extend the shared live-update platform with a dedicated session transcript
  topic, append-safe payloads, and bounded recovery so hot session views stay fresh
  with lower request volume.
author: codex
created: 2026-03-22
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/fdd3443
- https://github.com/miethe/CCDash/commit/751559c
- https://github.com/miethe/CCDash/commit/1bd54f6
pr_refs:
- https://github.com/miethe/CCDash/pull/15
priority: medium
risk_level: medium
complexity: medium
track: Platform
timeline_estimate: 4-6 days across 5 phases
feature_slug: session-transcript-append-deltas-v1
feature_family: live-update-platform
feature_version: v1
lineage_family: live-update-platform
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
  kind: follow_up
lineage_children: []
lineage_type: enhancement
problem_statement: Session live updates already use SSE invalidations, but active
  transcript views still pay the cost of targeted full session-detail refreshes for
  append-only growth.
owner: platform-engineering
owners:
- platform-engineering
- frontend-engineering
- backend-platform
contributors:
- ai-agents
audience:
- ai-agents
- developers
- frontend-engineering
- backend-platform
tags:
- prd
- sse
- live-updates
- sessions
- transcript
- append
- performance
related_documents:
- docs/project_plans/designs/session-transcript-append-deltas-v1.md
- docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
- docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md
- docs/project_plans/implementation_plans/enhancements/session-transcript-append-deltas-v1.md
- docs/live-update-platform-developer-reference.md
context_files:
- backend/application/live_updates/domain_events.py
- backend/application/live_updates/topics.py
- backend/db/sync_engine.py
- backend/routers/live.py
- components/SessionInspector.tsx
- services/live/topics.ts
- services/live/connectionManager.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/session-transcript-append-deltas-v1.md
---
# PRD: Session Transcript Append Deltas V1

## Delivery Status

Status: completed on 2026-03-23.

Validated against the current tree:

1. `backend/application/live_updates/topics.py` and `backend/db/sync_engine.py` publish the dedicated transcript append topic and delta events.
2. `components/SessionInspector.tsx` consumes append-safe transcript updates instead of relying on full-detail refreshes as the primary path.
3. `backend/tests/test_live_domain_publishers.py` and `backend/tests/test_live_router.py` cover the transport contract and fallback behavior.

Relevant commits:

- [fdd3443](https://github.com/miethe/CCDash/commit/fdd3443) feat(live): add session transcript topic contract
- [751559c](https://github.com/miethe/CCDash/commit/751559c) feat(live): publish session transcript append deltas
- [36a3279](https://github.com/miethe/CCDash/commit/36a3279) feat(live): append session transcripts in inspector
- [1bd54f6](https://github.com/miethe/CCDash/commit/1bd54f6) docs(live): document transcript append rollout

Pull request:

- [#15](https://github.com/miethe/CCDash/pull/15)

## Executive Summary

CCDash already moved active session viewing off the old 5 second detail polling loop, but the current session live path still responds to transcript growth by invalidating `session.{session_id}` and re-fetching full session detail. That behavior is correct and safe, yet it scales poorly as transcripts get longer because append-only growth still triggers heavyweight read-model recomputation.

This follow-up adds a transcript-specific append channel on top of the existing SSE platform. Active Session Inspector views should subscribe to a dedicated transcript topic, merge newly persisted log entries into local state when append semantics are safe, and fall back to the existing invalidation plus REST recovery path when cursors gap, payloads are incomplete, or transcript history is rewritten.

## Current State

The current stack already provides the key foundations:

1. a shared live event envelope with `append`, `invalidate`, `heartbeat`, and `snapshot_required`
2. topic multiplexing, cursor tracking, and reconnect handling in the frontend live connection manager
3. bounded replay and snapshot fallback in the backend live broker and router
4. session invalidation publishing from sync/ingestion paths

What is still missing:

1. there is no dedicated `session.{session_id}.transcript` topic helper
2. session live publishing does not distinguish append-safe transcript growth from coarse invalidation
3. Session Inspector subscribes only to the coarse session topic and refreshes full detail whenever the session changes
4. the frontend has no transcript delta merge contract or duplicate-suppression path for appended logs

## Problem Statement

Active transcript viewing in Session Inspector remains refresh-oriented instead of append-oriented.

User-visible and technical consequences:

1. hot sessions can trigger repeated full `GET /api/sessions/{id}` requests even when the only change is one newly appended log row
2. transcript growth feels like a detail refresh rather than a continuous append stream
3. reconnect and replay semantics are correct today, but they force recovery through the heavyweight read model more often than necessary
4. the shared live-update platform already supports append delivery, yet session transcripts still use only the coarse invalidation path

## Goals

1. add a dedicated append topic for active session transcript growth
2. keep the existing session invalidation topic as the authoritative fallback for status or non-append-safe changes
3. let Session Inspector append new transcript rows directly into selected-session state when ordering and identity checks pass
4. preserve cursor replay, hidden-tab recovery, and `snapshot_required` semantics from the shared live platform
5. reduce request volume and full session-detail recomputation for hot active-session views

## Non-Goals

1. redesigning the full session detail API
2. introducing a durable cross-process transcript event store
3. streaming every session-derived subview independently in this iteration
4. changing historical or inactive session behavior outside the live path
5. replacing the coarse session invalidation topic for non-append-safe mutations

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Active-session refresh behavior | Append-only transcript growth still triggers targeted full detail fetches | Append-only growth normally updates the visible transcript without a full session-detail refetch |
| Hot-session request volume | One or more full session-detail requests during normal active transcript growth | At least 60% fewer full session-detail requests for hot append-only sessions |
| Recovery correctness | Session invalidation plus REST refresh already recovers reliably | Append stream preserves the same correctness, with REST fallback on any replay or ordering gap |
| UI continuity | Transcript updates feel refresh-oriented | New transcript entries appear incrementally without visible detail flashes in normal cases |

## User and System Outcomes

1. Users watching an active session see transcript growth as small append steps rather than repeated full refreshes.
2. Frontend state stays aligned with the shared live-update model instead of creating a bespoke session streaming path.
3. Backend publish logic can emit lighter session-specific deltas without weakening the fallback model that already works.
4. Future live session optimizations can build on the transcript topic rather than overloading the coarse invalidation topic.

## Functional Requirements

### FR-1: Transcript Topic Contract

The platform must add a transcript-specific topic family:

1. `session.{session_id}.transcript`

Rules:

1. the topic is used only for append-safe transcript growth
2. `session.{session_id}` remains available for session invalidation and status refresh
3. topic helpers must exist in both backend and frontend live-update modules

### FR-2: Append Payload Shape

Transcript append payloads must be lightweight and orderable.

Required fields:

1. `sessionId`
2. `entryId`
3. `sequenceNo`
4. `kind`
5. `createdAt`
6. `payload`

Rules:

1. `entryId` must be stable enough for duplicate suppression
2. `sequenceNo` must be monotonic within a session transcript stream
3. payloads must expose only data already available through session detail reads
4. append identity must be derived from durable log metadata rather than transient array position alone
5. if append-safe construction is not possible, the system must emit invalidation instead of a guessed append event

### FR-3: Backend Publish Semantics

The backend must publish transcript append events close to the ingestion path where new logs are already detected.

Requirements:

1. detect newly observed session log rows during sync/ingestion
2. map only the newly observed rows into transcript append payloads
3. use durable transcript identity when deciding whether rows are newly appended versus rewritten or re-numbered
4. publish coarse invalidation only when status or non-append-safe fields change, or when append confidence is insufficient
5. preserve bounded replay behavior through the existing live broker

### FR-4: Session Inspector Merge and Recovery

Session Inspector must adopt a stream-first transcript merge path for active sessions.

Requirements:

1. subscribe to both `session.{session_id}.transcript` and `session.{session_id}` while an active session is visible
2. append transcript events into `selectedSession.logs` only when sequence and identity checks pass
3. update coarse session metadata from invalidation payloads when safe
4. trigger targeted REST refresh on `snapshot_required`, cursor gaps, sequence mismatches, missing identifiers, or non-append-safe invalidations
5. preserve existing fallback polling only when live transport is disabled or unhealthy

### FR-5: Rollout and Observability

The feature must remain staged and measurable.

Requirements:

1. gate transcript append behavior behind a dedicated frontend flag
2. keep existing session live updates as the baseline fallback
3. validate append correctness across reconnect, tab-hide/tab-resume, and backend restart scenarios
4. expose enough logging or counters to compare append delivery and fallback frequency during rollout

## Non-Functional Requirements

1. The feature must reuse the existing SSE transport, replay buffer, and connection manager instead of adding a second live client.
2. Append delivery must not require database schema changes for V1.
3. The frontend merge path must suppress duplicates and preserve transcript ordering deterministically.
4. Failure handling must prefer explicit fallback over partial or speculative transcript merges.
5. The implementation must remain reversible by disabling the transcript-append flag.

## Dependencies and Assumptions

1. the shared SSE platform and session invalidation path remain the canonical transport baseline
2. session logs already have sufficient identity and ordering data to construct append-safe payloads for the common case
3. active-session detail fetch remains available as the recovery path
4. no distributed event broker is required for this iteration

## Risks and Mitigations

1. Risk: session sync can rewrite or renumber logs, so raw position may not reliably identify true append-only growth.
   Mitigation: fall back to coarse invalidation when append confidence is low.
2. Risk: reconnect or hidden-tab resume can create cursor gaps beyond the replay buffer.
   Mitigation: keep `snapshot_required` and targeted REST recovery as first-class paths.
3. Risk: transcript rewrites or compaction could make append-only merging unsafe.
   Mitigation: treat rewrite-like mutations as invalidation-only events.
4. Risk: frontend merge bugs could silently duplicate or reorder transcript rows.
   Mitigation: require deterministic duplicate suppression and automated merge tests before rollout.

## Acceptance Criteria

1. Active append-only session growth normally updates Session Inspector through transcript append events without a full detail refetch.
2. Replay gaps, missing IDs, sequence mismatches, and non-append-safe session changes recover through the existing targeted REST refresh path.
3. A dedicated transcript topic and topic helper exist in backend and frontend live-update modules.
4. The feature is protected by a dedicated rollout flag and can be disabled independently of coarse session live updates.
5. Automated and manual validation cover append merge correctness, reconnect recovery, and reduced request volume for hot active sessions.
