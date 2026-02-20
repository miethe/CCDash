---
doc_type: implementation_plan
status: draft
category: enhancements

title: "Implementation Plan: Live Update Animation System"
description: "Extensible motion architecture for real-time history, sessions, and transcript updates without flicker"
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-02-20
updated: 2026-02-20

tags: [implementation, frontend, animation, realtime, ux]
feature_slug: live-update-animations-v1
feature_family: live-update-animations
lineage_family: live-update-animations
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [live-update-animations-v1]
prd: ""
prd_ref: ""
related:
  - docs/document-frontmatter-current-implementation-spec-2026-02-19.md
  - docs/document-frontmatter-improvement-spec-2026-02-19.md
related_documents:
  - docs/document-frontmatter-current-implementation-spec-2026-02-19.md
  - docs/document-frontmatter-improvement-spec-2026-02-19.md
plan_ref: live-update-animations-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: frontend-engineering
owners: [frontend-engineering]
contributors: [ai-agents]

complexity: Medium
track: Standard
timeline_estimate: "1-2 weeks across 4 phases"
---

# Implementation Plan: Live Update Animation System

**Project:** CCDash  
**Complexity:** Medium (M) | **Track:** Standard  
**Timeline:** ~1-2 weeks across 4 phases

## Executive Summary

Live updates currently land as hard list refreshes in key surfaces:

1. Feature Modal `History` tab
2. Feature Modal `Sessions` tab
3. Session `Transcript` tab

This plan introduces a reusable motion and live-diff layer so new items animate into place instead of causing visual flicker, with a messaging-style transcript behavior and active-agent live indicator.

## Goals

1. Animate top insertions in Feature Modal history and sessions so existing rows are pushed smoothly.
2. Add transcript live rail for active sessions, including agent-level activity hints.
3. Animate new transcript messages as fly-ins while preserving readable scroll behavior.
4. Build extensible primitives so future live surfaces can reuse the same system.
5. Respect reduced-motion accessibility preferences.

## Non-Goals

1. Backend transport migration to WebSockets/SSE in this iteration.
2. Redesigning visual theme, typography, or page-level layout.
3. Reworking session parsing/linking logic outside what is needed for live indicators.

## Current-State Findings

1. Feature Modal refreshes feature detail and linked sessions every 5 seconds in `components/ProjectBoard.tsx`.
2. Global session data refreshes on polling in `contexts/DataContext.tsx`.
3. `getSessionById` currently returns cached detail when logs are already present, which prevents forced freshness in session detail.
4. There is no reduced-motion handling currently in frontend components.
5. Existing `animate-in` classes cover mount transitions, but not data-delta list transitions.

## Framework Decision

Use **Framer Motion** as the animation runtime.

Rationale:

1. Strong React-native list/layout animation support with `AnimatePresence` and `layout`.
2. Better control than AutoAnimate for conditional entry/exit and sequencing.
3. Easier long-term extensibility than a custom FLIP-heavy CSS implementation.

## Architecture

### 1. Shared Motion Layer

Create `components/animations/` with:

1. `motionTokens.ts`
2. `motionPresets.ts`
3. `useReducedMotionPreference.ts`
4. `useAnimatedListDiff.ts`
5. `useSmartScrollAnchor.ts`
6. `TypingIndicator.tsx`

Design rules:

1. Centralize durations, easings, and spring tuning.
2. Export named presets (`listInsertTop`, `messageFlyIn`, `typingPulse`).
3. Gate initial-hydration animations.
4. Offer reduced-motion variants for every preset.

### 2. Live Data Reconciliation Layer

Add stable merge and diff helpers so UI animates true deltas only:

1. Keep object identity for unchanged rows by ID.
2. Compute `insertedIds`, `removedIds`, and `movedIds`.
3. Mark only inserted items as entering animation targets.
4. Avoid reorder jitter when sort keys are unchanged.

### 3. Transport Abstraction Hook

Define a frontend `LiveUpdateTransport` interface with polling implementation in this iteration, so SSE/WebSocket can be introduced later without changing animation consumers.

## Public API and Type Changes

### DataContext API

In `contexts/DataContext.tsx`, update:

```ts
getSessionById(sessionId: string, options?: { force?: boolean }): Promise<AgentSession | null>
```

Behavior:

1. `force: true` bypasses cached full-detail object.
2. Default behavior remains backward-compatible.

### Frontend Types

In `types.ts`, add:

1. `LiveAgentActivity`
2. `LiveTranscriptState`
3. `LiveInsertMeta`
4. `MotionPresetKey`

## Detailed UX Behavior

### Feature Modal: History Tab

1. New event inserts at top.
2. New row fades and slightly translates into final position.
3. Existing rows shift down via layout animation.
4. Initial load is static; only subsequent live deltas animate.

### Feature Modal: Sessions Tab

1. New linked session enters at top of the relevant group.
2. Thread/group expansion state is preserved during live refresh.
3. Subthread tree uses position layout animation for pushdown.
4. Existing cards keep focus/hover state when unaffected.

### Session Transcript: Active Live Mode

1. Show bottom live rail only when session status is active.
2. Live rail displays `Live` status, typing indicator, and active agent chips derived from active subthreads.
3. New messages fly in from bottom and push the thread upward.
4. Smart scroll policy:
   - If user is near bottom (<=120px), auto-stick to latest.
   - If user is away from bottom, do not jump; show `N new messages` chip.
5. Clicking the chip jumps to latest and clears the counter.

## Phase Breakdown

## Phase 1: Motion Foundation

1. Add `framer-motion` dependency.
2. Create shared motion tokens and preset registry.
3. Add reduced-motion hook and fallback styles.
4. Add unit tests for token/preset wiring.

## Phase 2: Data Freshness and Diff

1. Extend `getSessionById` with force refresh path.
2. Add local active-session polling cadence in session detail.
3. Implement list merge/diff utilities and hydration guards.
4. Add tests for insert/remove/move diff logic.

## Phase 3: Feature Modal Animations

1. Replace unstable fallback keys in history rows with deterministic keys.
2. Add top-insert and pushdown layout animations in History tab.
3. Add equivalent animation behavior for Sessions tree/cards.
4. Verify expanded state persistence across live refreshes.

## Phase 4: Transcript Live UX

1. Add live rail and active-agent indicator.
2. Add message fly-in animation and layout shifts.
3. Implement smart sticky scroll with `N new messages` chip.
4. Add reduced-motion parity and interaction QA.

## Test Cases and Scenarios

### Unit Tests

1. `useAnimatedListDiff` detects inserts/removals/moves correctly.
2. `useSmartScrollAnchor` toggles between sticky/manual states correctly.
3. Reduced-motion path swaps to low-motion presets.

### Integration Tests

1. Feature history update inserts top row with delta animation state.
2. Feature sessions update preserves expanded groups/subthreads.
3. Transcript update near bottom auto-scrolls and animates entry.
4. Transcript update away from bottom does not jump and shows new-message chip.

### Manual QA

1. Active session running for 2+ minutes shows no full-list flicker.
2. Rapid inserts do not degrade interaction noticeably.
3. Reduced-motion OS preference produces minimal movement with intact usability.

## Acceptance Criteria

1. Live updates in Feature Modal History and Sessions animate smoothly with pushdown behavior.
2. Transcript in active sessions behaves like a messaging feed with smart sticky scrolling.
3. Active-agent indicator reflects active subthreads consistently.
4. No regressions in list selection, expansion state, or tab switching.
5. Motion logic is reusable from shared animation modules.

## Risks and Mitigations

1. Risk: Polling bursts cause over-animation.  
Mitigation: coalesce updates per tick and cap concurrent animated inserts.

2. Risk: Scroll jitter in transcript.  
Mitigation: strict anchor threshold and deterministic bottom detection.

3. Risk: Performance regression on long lists.  
Mitigation: animate position only where possible and avoid expensive per-row visual effects.

## Rollout Strategy

1. Introduce behind a local UI feature flag for controlled testing.
2. Validate against real active sessions in development.
3. Remove flag after acceptance criteria are met and stabilize as default behavior.

## Assumptions and Defaults

1. Motion density default is balanced.
2. Transcript scroll policy is smart sticky.
3. Polling remains the live transport in this iteration.
4. Backend API changes are not required for this scope.
