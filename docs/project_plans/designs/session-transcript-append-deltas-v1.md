---
doc_type: design_doc
doc_subtype: design_spec
status: draft
category: enhancements

title: "Design Spec: Session Transcript Append Deltas V1"
description: "Design a transcript-specific live-update optimization so active sessions can stream appended log entries instead of forcing full session-detail refreshes on every invalidation."
summary: "Extend the shared SSE live-update platform with append-oriented session transcript payloads, cursor-aware recovery, and bounded fallback rules so Session Inspector can append new transcript lines incrementally while preserving the current invalidation path as safety net."
author: codex
audience: [ai-agents, developers, platform-engineering, frontend-engineering]
created: 2026-03-15
updated: 2026-03-22

tags: [design, sse, live-updates, sessions, transcript, optimization]
feature_slug: session-transcript-append-deltas-v1
feature_family: live-update-platform
feature_version: v1
blocked_by: []
sequence_order: null
lineage_family: live-update-platform
lineage_parent: "docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md"
lineage_children: []
lineage_type: follow_up
primary_doc_role: supporting_design

linked_features:
  - sse-live-update-platform-v1
related_documents:
  - docs/project_plans/implementation_plans/enhancements/sse-live-update-platform-v1.md
  - docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md
  - docs/project_plans/PRDs/enhancements/session-transcript-append-deltas-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-transcript-append-deltas-v1.md
  - docs/live-update-platform-developer-reference.md
  - components/SessionInspector.tsx
  - backend/application/live_updates/domain_events.py
  - backend/db/sync_engine.py

surfaces:
  - session_inspector
  - shared_live_update_platform
user_flows:
  - watch_active_session_transcript
  - recover_after_tab_hide_or_reconnect
  - recover_after_replay_gap
ux_goals:
  - Keep active transcript views fresh without reloading the full session payload on every change.
  - Preserve the existing reconnect and fallback semantics from the shared live client.
  - Make transcript growth feel incremental rather than “snap refreshed.”
components:
  - session_transcript_append_publisher
  - session_transcript_delta_adapter
  - session_transcript_recovery_path
accessibility_notes:
  - Incremental transcript rendering must preserve reading order and avoid unexpected focus jumps.
  - Live updates should remain understandable when screen readers encounter appended content.
motion_notes:
  - Prefer subtle append affordances only if they do not disrupt continuous reading or auto-scroll behavior.
asset_refs: []

owner: platform-engineering
owners: [platform-engineering, frontend-engineering]
contributors: [codex]
---

# Design Spec: Session Transcript Append Deltas V1

## 1. Intent

The shared SSE rollout completed with session live updates driven by invalidation plus targeted `GET /api/sessions/{id}` refreshes. That removed the old 5s polling loop from the primary path, but it still means every live transcript change can trigger a full session-detail refresh.

This design logs the next optimization step: stream appended transcript entries directly so Session Inspector can merge new lines incrementally, while keeping the current invalidation path as a bounded fallback.

## 2. Current State

Today:

1. backend emits session invalidation events with summary metadata such as `status`, `updatedAt`, and `logCount`
2. Session Inspector subscribes to `session.{session_id}` and responds by re-fetching full session detail
3. replay gaps and disconnects already fall back cleanly to REST recovery

Strengths of the current behavior:

1. simple and correct
2. leverages existing session REST read model
3. does not depend on a persistent event store

Limitations:

1. refresh cost grows with transcript size
2. frequent session writes can cause repeated full payload fetches
3. transcript rendering is refresh-oriented instead of append-oriented

## 3. Goals

1. Add append-oriented transcript payloads for active sessions.
2. Preserve the current shared SSE broker, cursor, heartbeat, and reconnect model.
3. Keep invalidation plus REST refresh available as the fallback and replay-gap recovery path.
4. Avoid reintroducing a timer-driven live loop for active sessions.

## 4. Non-Goals

1. redesign the full session-detail API
2. build a durable cross-process transcript event log
3. replace execution/event append flows already in place
4. stream every derived session subview independently in the first pass

## 5. Proposed Topic and Payload Model

Add session transcript append delivery as a distinct topic family:

1. `session.{session_id}.transcript`
2. keep `session.{session_id}` for invalidation/status fallback

Append payload shape should be small and transcript-specific:

```json
{
  "sessionId": "session-123",
  "entryId": "log-456",
  "sequenceNo": 42,
  "kind": "assistant_message",
  "createdAt": "2026-03-15T19:10:00Z",
  "payload": {
    "type": "assistant",
    "content": "..."
  }
}
```

Design rules:

1. one append event per newly persisted transcript/log entry
2. stable ordering via `sequenceNo`
3. invalidation event remains available for status changes, compaction, edits, or append-model mismatch

## 6. Backend Design

Publish append deltas close to the point where session logs are ingested or persisted.

Preferred sequence:

1. detect new session log rows during sync/ingest
2. map newly observed rows into transcript append DTOs
3. publish append events to `session.{session_id}.transcript`
4. publish invalidation to `session.{session_id}` only when status or non-append-safe fields change

Guardrails:

1. if the system cannot confidently compute only the new entries, fall back to invalidation
2. replay buffer size should remain bounded and use `snapshot_required` on gaps
3. append payloads must not include more data than the existing REST session detail already exposes

## 7. Frontend Design

Session Inspector should subscribe to both topics while an active session is visible:

1. `session.{session_id}.transcript` for append events
2. `session.{session_id}` for status invalidation and coarse fallback

Client behavior:

1. append incoming transcript items directly into `selectedSession.logs`
2. update status/header metadata from invalidation payloads when safe
3. trigger targeted REST refresh on `snapshot_required`, reconnect gap, or invalidation that signals non-append-safe changes

Fallback triggers should include:

1. replay gap
2. missing `entryId` or sequence mismatch
3. tab resume when client cursor is no longer satisfiable
4. session mutation types that rewrite or compact transcript history

## 8. Recovery and Rollout

Rollout order:

1. keep current invalidation-only session path as default safety baseline
2. gate transcript append deltas behind a separate frontend rollout flag
3. enable in development first and compare request volume against current invalidation behavior
4. promote only if append merging stays correct across reconnect, tab hide/show, and backend restart

Suggested rollout flag:

1. `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED`

## 9. Validation Plan

Automated:

1. backend tests for append publisher sequencing and replay gap behavior
2. frontend tests for transcript merge correctness and duplicate suppression
3. reconnect tests where transcript append stream falls back to REST recovery

Manual:

1. watch a long active session and confirm transcript lines append without full-detail flashes
2. hide/restore the tab and verify cursor recovery
3. restart backend during active viewing and verify recovery path
4. compare network volume against the current invalidation-only behavior

## 10. Exit Criteria

This optimization is done when:

1. active session transcript updates normally arrive as append deltas
2. replay gaps recover without user-visible corruption
3. Session Inspector still has a reliable invalidation plus REST fallback path
4. request volume for hot session transcript views is measurably lower than the current invalidation-only approach

## 11. Open Questions

1. Should transcript append DTOs mirror raw parser log rows or a Session Inspector-specific normalized shape?
2. Which session mutations are safe to represent as append-only versus always forcing invalidation?
3. Do we need a lightweight cursor persisted per transcript topic beyond the shared connection manager map already in place?
