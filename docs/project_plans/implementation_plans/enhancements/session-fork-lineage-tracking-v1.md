---
doc_type: implementation_plan
status: draft
category: enhancements

title: "Implementation Plan: Session Fork Lineage Tracking V1"
description: "Detect session forks, materialize forked main-thread sessions, and surface fork lineage in Session UI without breaking mapping or analytics."
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-03-06
updated: 2026-03-06

tags: [implementation, backend, frontend, sessions, lineage, forks, analytics, mappings]
feature_slug: session-fork-lineage-tracking-v1
feature_family: session-fork-lineage-tracking
lineage_family: session-fork-lineage-tracking
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [session-fork-lineage-tracking-v1]
related:
  - backend/parsers/platforms/claude_code/parser.py
  - backend/models.py
  - backend/db/repositories/sessions.py
  - backend/db/repositories/postgres/sessions.py
  - backend/db/sync_engine.py
  - backend/routers/api.py
  - components/SessionInspector.tsx
  - types.ts
  - docs/session-data-discovery.md
  - docs/project_plans/reports/session-data-discovery-findings-2026-03-02.md
plan_ref: session-fork-lineage-tracking-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: fullstack-engineering
owners: [fullstack-engineering]
contributors: [ai-agents]

complexity: High
track: Standard
timeline_estimate: "4-6 days across 6 phases"
---

# Implementation Plan: Session Fork Lineage Tracking V1

## Objective

Detect forked conversation branches during session ingestion, create first-class fork sessions from the fork point forward, and expose them across Session UX as a distinct lineage type from subagents.

## Scope and Fixed Decisions

1. Forks are modeled as first-class lineage, not as subagents.
2. A fork inherits full parent context, while a subagent starts with fresh context.
3. Parent/root session remains the canonical owner of all pre-fork history.
4. A fork session displays only the branch segment from the fork point forward.
5. The parent session transcript receives an injected synthetic fork note at the branch point, similar in visibility to subthread markers but visually distinct.
6. Fork sessions receive unique synthetic session IDs and are stored separately from the parent session.
7. Existing `parentSessionId` / `rootSessionId` semantics remain reserved for current session/subagent lineage so mapping logic does not silently change.
8. Fork lineage is introduced through a normalized relationship model that can support future platforms with different fork markers.
9. V1 targets Claude Code fork detection first, but the storage and UI contract must be platform-agnostic.

## Non-Goals

1. Reconstructing shared pre-fork history inside the fork transcript body.
2. Supporting branch merges or rejoin semantics.
3. Retrofitting all session analytics to family-wide rollups in the same phase as core fork support.
4. Replacing existing subagent lineage behavior.

## Problem Summary

Today the app flattens forked Claude conversations into one session because ingestion preserves `entryUuids` and `parentUuids` only as aggregate sets, not parent-child edges. The raw transcript is tree-shaped, but the normalized session output is linear. This causes three failures:

1. Fork creation is invisible in the parent timeline.
2. Post-fork activity from separate branches is combined into one session transcript.
3. Feature/session mapping and analytics cannot distinguish direct branch work from shared ancestor context.

## Recommended Architecture

## 1) Normalized Thread Lineage Contract

Introduce a cross-platform lineage contract orthogonal to current session/subagent lineage.

Proposed concepts:

1. `threadKind`
   - `root`
   - `fork`
   - `subagent`
2. `contextInheritance`
   - `fresh`
   - `full`
3. `conversationFamilyId`
   - stable family key shared by root session and all forks created from the same underlying conversation
4. `session_relationships`
   - normalized edges between sessions with typed metadata

Proposed relationship types:

1. `fork`
2. `subagent`
3. reserved for future: `resume`, `handoff`, `branch`

## 2) Fork Session Materialization Strategy

Materialize each fork as a synthetic derived session instead of trying to render one DAG in a single transcript view.

Why this approach:

1. It keeps existing Session detail patterns intact.
2. It avoids duplicating pre-fork logs and metrics into child sessions.
3. It lets mappings and analytics remain direct-session scoped by default.
4. It scales to multiple forks and nested forks without redesigning the entire Session page around a graph UI.

Fork session rules:

1. `id` is synthetic and stable from `(platform, rawSessionId, forkRootEntryUuid)`.
2. `threadKind = fork`
3. `contextInheritance = full`
4. `conversationFamilyId` matches the parent/root family
5. transcript/logs include only entries reachable from the fork root child
6. session metadata stores:
   - `forkParentSessionId`
   - `forkPointEntryUuid`
   - `forkPointParentEntryUuid`
   - `forkDepth`
   - `branchEntryCount`
   - `platformForkDetector`

## 3) Parent Session Representation

Inject a synthetic timeline/log artifact into the parent session for each fork:

1. log type: `fork_start`
2. speaker: `system`
3. timestamp: fork root timestamp
4. content:
   - human label
   - fork session deep link target
   - context inheritance note (`inherits full parent context`)
5. metadata:
   - `forkSessionId`
   - `forkPointEntryUuid`
   - `forkChildEntryUuid`
   - `threadKind = fork`

This mirrors subthread visibility while making the semantic distinction explicit.

## 4) Mapping-Safe Correlation Model

To avoid breaking current mapping behavior:

1. shared ancestor history remains owned by the parent/root session only
2. fork sessions contribute only post-fork direct activity to mapping and analytics
3. UI may optionally show inherited parent context as lineage metadata, not as duplicated mapped evidence
4. family-level rollups are opt-in and must dedupe by raw entry UUID if added later

Default behavior after V1:

1. existing mapping logic stays direct-session scoped
2. root session mapping remains unchanged for pre-fork content
3. fork session mapping is newly available for post-fork content
4. no shared pre-fork logs/files/artifacts are counted twice

## Data Model Changes

## Session model additions

Add fields to backend/frontend session types:

1. `threadKind`
2. `conversationFamilyId`
3. `contextInheritance`
4. `forkParentSessionId`
5. `forkPointLogId`
6. `forkPointEntryUuid`
7. `forkPointParentEntryUuid`
8. `forkDepth`
9. `forkCount`

## Session log metadata additions

Add raw lineage metadata to each ingested log:

1. `entryUuid`
2. `parentUuid`
3. `rawMessageId`
4. `branchRootEntryUuid`
5. `threadKind`
6. `isSynthetic`
7. `syntheticEventType`

This is sufficient to reconstruct branch topology without storing the full raw transcript again.

## New relationship storage

Add a new normalized `session_relationships` table with:

1. `id`
2. `project_id`
3. `parent_session_id`
4. `child_session_id`
5. `relationship_type`
6. `context_inheritance`
7. `source_platform`
8. `parent_entry_uuid`
9. `child_entry_uuid`
10. `source_log_id`
11. `metadata_json`
12. `created_at`

Rationale:

1. avoids overloading existing session lineage columns
2. provides future-platform flexibility
3. supports UI sections and analytics joins cleanly

## Platform Detection Contract

Create a normalized branch detection interface inside platform parsers.

Proposed detector output:

1. `relationshipType`
2. `parentEntryUuid`
3. `childEntryUuid`
4. `childTimestamp`
5. `contextInheritance`
6. `confidence`
7. `platformMetadata`

Claude Code V1 detection rule:

1. build `children_by_parent_uuid`
2. ignore ordinary tool/progress fan-out
3. identify a fork when a parent entry has more than one conversational child branch
4. choose conversational children from user/assistant/system turn roots, excluding tool-result wrappers and resume noise

## ID and Session Family Strategy

Recommended IDs:

1. keep current session IDs unchanged for existing root/subagent sessions
2. generate fork IDs as a stable synthetic ID from:
   - `platform`
   - `rawSessionId`
   - `forkRootEntryUuid`
3. store `rawSessionId` and `forkRootEntryUuid` in forensics metadata for traceability

Recommended family key:

1. `conversationFamilyId = original normalized session id` for root and all derived forks
2. subagents may continue to use current session lineage while still optionally participating in a future family view

## API and Query Surface Changes

## Backend session payload changes

Update session detail/list payloads to return fork lineage fields and relationship summaries.

Proposed additions:

1. `forks[]` on session detail:
   - `sessionId`
   - `label`
   - `forkPointTimestamp`
   - `forkPointPreview`
   - `entryCount`
2. `sessionRelationships[]` for generic lineage rendering
3. `forkSummary` in `sessionForensics`

## Query semantics

1. Existing root-thread views keep current default scope.
2. Fork sessions are listed as standalone sessions with `threadKind = fork`.
3. Session detail can show:
   - parent fork origin
   - sibling forks
   - child forks
4. Later analytics can add `include_family=true` without schema redesign.

## UI Plan

## Session list and badges

1. Add distinct fork badge/icon separate from subagent badge.
2. Fork rows show parent/root lineage affordance.
3. Filtering can distinguish:
   - root sessions
   - fork sessions
   - subagents

## Session detail page

Add a new `Forks` section distinct from `Agents`/subthreads.

Parent session:

1. show fork note blocks inline in transcript/activity
2. show `Forks` section with cards for child forks
3. each card includes:
   - fork label
   - created time
   - entry count
   - inheritance note
   - open session action

Fork session:

1. header banner shows:
   - forked from parent session
   - fork point preview
   - inherited full context
2. transcript starts at fork point
3. show sibling and parent navigation in the `Forks` section

## Recommended Delivery Phases

## Phase 1: Lineage contract and storage foundation

1. Extend backend/frontend models with thread lineage fields.
2. Add `session_relationships` migrations for SQLite and Postgres.
3. Add repository support for relationship upsert/query.
4. Define normalized relationship payload shape for parser output.

Success criteria:

1. data model supports fork lineage without changing existing subagent semantics
2. relationship table can represent fork and subagent types
3. no existing session repository tests regress

## Phase 2: Claude parser fork detection and synthetic session generation

1. Add parent-child adjacency construction in Claude parser.
2. Detect fork events from raw transcript tree.
3. Emit synthetic fork note logs into parent session.
4. Materialize derived fork sessions from fork root onward.
5. Populate session forensics:
   - `forkSummary`
   - `branchTopology`
   - detector confidence

Success criteria:

1. example Claude session produces one parent session plus one or more fork sessions
2. parent session includes fork marker log entries
3. fork session transcript starts at fork child, not session start

## Phase 3: Sync, persistence, and backfill behavior

1. Update sync engine to ingest synthetic fork sessions and relationship rows.
2. Ensure list/detail queries return fork sessions cleanly.
3. Add incremental backfill path for existing cached sessions.
4. Protect idempotency so repeated sync does not duplicate forks.

Success criteria:

1. sync runs are stable on repeated ingestion
2. cached sessions can be backfilled without data corruption
3. parent and fork sessions remain queryable independently

## Phase 4: Mapping and analytics safety layer

1. Audit mapping resolvers and linked-session logic for assumptions on `sessionType`.
2. Keep direct-session mapping logic unchanged by default.
3. Add fork-specific lineage metadata without duplicating ancestor evidence.
4. Add tests proving shared pre-fork data is not double-counted.
5. Add family-aware hooks only behind explicit opt-in flags where needed.

Success criteria:

1. existing feature/session mappings remain stable for non-fork sessions
2. fork sessions generate distinct direct mappings from post-fork activity
3. shared ancestor logs/files are not counted twice

## Phase 5: Session UI integration

1. Add fork badge/type treatment in session list and detail header.
2. Add `Forks` section to Session detail.
3. Render synthetic fork note blocks in transcript/activity.
4. Add fork origin banner for fork sessions.
5. Add navigation between parent session and fork sessions.

Success criteria:

1. parent session clearly shows where the fork happened
2. fork sessions are visually distinct from subagents
3. users can navigate parent <-> fork without ambiguity

## Phase 6: Validation, fixtures, and future-platform hooks

1. Add parser fixtures covering:
   - single fork
   - multiple forks
   - nested forks
   - false-positive tool/progress fan-out
2. Add backend API tests for fork fields and relationship payloads.
3. Add frontend render tests for fork badges, banners, and section cards.
4. Document platform detector extension points for future systems.

Success criteria:

1. Claude fork fixtures parse deterministically
2. false positives from tool/progress fan-out are blocked
3. extension contract exists for non-Claude fork detectors

## Testing Plan

## Parser tests

1. exact example session with one assistant parent and two user children
2. root with multiple user siblings at different depths
3. parent with progress/user or tool-result/user siblings that must not create forks
4. nested fork under an existing fork session

## Repository and sync tests

1. relationship row upsert and dedupe
2. fork session id stability across repeated sync
3. family query behavior
4. backfill over existing session cache

## Mapping regression tests

1. feature linking unchanged for baseline sessions
2. fork session direct mappings only include post-fork evidence
3. family-inclusive queries dedupe shared ancestor activity when enabled

## Frontend tests

1. parent session renders fork note block
2. fork session renders origin banner
3. `Forks` section lists child/sibling relationships
4. fork badge does not reuse subagent styling or labels

## Acceptance Criteria

1. Forks are detected and stored as separate sessions with stable synthetic IDs.
2. Parent sessions display injected fork notes at the correct transcript point.
3. Fork sessions are listed and rendered as a unique lineage type, not as subthreads/subagents.
4. Fork transcripts start at the fork point and do not duplicate ancestor logs.
5. Existing mapping behavior for non-fork sessions is unchanged.
6. Fork sessions can be correlated independently while still preserving parent-family lineage.
7. The storage and UI contract can support future non-Claude fork detectors.

## Risks and Mitigations

1. Risk: false fork detection from ordinary transcript fan-out.
   - Mitigation: conversation-child filtering plus fixture corpus from real sessions.
2. Risk: mapping regressions from new session type semantics.
   - Mitigation: keep existing `parentSessionId` / `rootSessionId` behavior intact and add orthogonal lineage fields.
3. Risk: duplicate analytics from shared pre-fork ancestry.
   - Mitigation: fork sessions store only post-fork subtree; parent remains canonical owner of shared history.
4. Risk: UI confusion between forks and subagents.
   - Mitigation: distinct badges, dedicated `Forks` section, explicit context inheritance copy.

## Rollout Notes

1. Ship parser + storage support behind a feature flag if needed.
2. Backfill cached Claude sessions after parser release.
3. Enable UI fork rendering after a small fixture corpus validates lineage integrity.
4. Defer family-wide analytics rollups until direct-session correctness is proven.
