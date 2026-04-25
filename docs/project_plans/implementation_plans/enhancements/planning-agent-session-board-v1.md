---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: in-progress
category: enhancements
title: 'Implementation Plan: Planning Agent Session Board V1'
description: Implement a rich Kanban-style planning board for active agent sessions,
  feature-scoped agent lanes, transcript links, relationship highlighting, and next-run
  CLI prompt previews.
summary: Extend the planning control plane with normalized session-to-planning correlation,
  animated board-ready APIs, interactive agent/session card UI, feature drill-down
  lanes, and copy-only next-run prompt preparation.
author: codex
created: 2026-04-25
updated: '2026-04-25'
priority: high
risk_level: medium
complexity: high
track: Planning / Execution / Orchestration
timeline_estimate: 2-4 weeks across 5 phases
feature_slug: planning-agent-session-board-v1
feature_family: planning-control-plane
feature_version: v1
lineage_family: planning-control-plane
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
owner: fullstack-engineering
owners:
- fullstack-engineering
- platform-engineering
- ai-integrations
contributors:
- ai-agents
audience:
- ai-agents
- developers
- fullstack-engineering
- platform-engineering
tags:
- implementation
- planning
- sessions
- agents
- orchestration
- cli
- frontend
- interactive-board
- animation
prd: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
related:
  - docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
  - docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/agent-session-board.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/feature-agent-lane.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/session-detail-panel.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/prompt-context-composer.png
  - components/Planning/PlanningAgentRosterPanel.tsx
- components/Planning/AgentDetailModal.tsx
- components/Planning/PlanningLaunchSheet.tsx
- components/Planning/primitives/PhaseOperationsPanel.tsx
- components/FeatureExecutionWorkbench.tsx
- components/SessionInspector.tsx
- backend/application/services/agent_queries/planning.py
- backend/services/feature_execution.py
- services/planning.ts
- services/execution.ts
- types.ts
plan_ref: planning-agent-session-board-v1
linked_sessions: []
---

# Implementation Plan: Planning Agent Session Board V1

## Objective

Deliver a planning-native agent/session board that shows active and recent sessions as rich interactive cards tied to features, phases, batches, tasks, transcripts, lineage, and next-run prompt previews. V1 is read/prepare-first: it generates copyable CLI command and prompt context, supports live board interactions, and does not need to execute commands in-app.

## Visual Guidance

Use these generated wireframes as implementation references. They are directional; preserve CCDash's existing component system, spacing primitives, and accessibility behavior where the generated image conflicts with the codebase.

| Screen | Wireframe | Implementation Focus |
|--------|-----------|----------------------|
| Planning Agent Board | [agent-session-board.png](./wireframes/planning-agent-session-board-v1/agent-session-board.png) | Phase 2 board shell, grouped columns, card density, live-state indicators, relationship layer, and state/feature/phase grouping controls. |
| Feature Agent Lane | [feature-agent-lane.png](./wireframes/planning-agent-session-board-v1/feature-agent-lane.png) | Phase 3 feature-scoped lane, phase/task mapping, confidence labels, and phase operations adjacency. |
| Session Detail Panel | [session-detail-panel.png](./wireframes/planning-agent-session-board-v1/session-detail-panel.png) | Phase 3 selected-card panel with activity markers, evidence, transcript freshness, lineage, context usage, and add-to-context action. |
| Prompt Context Composer | [prompt-context-composer.png](./wireframes/planning-agent-session-board-v1/prompt-context-composer.png) | Phase 4 prompt context tray, session/artifact chips, command preview, prompt preview, copy actions, and preview-only boundary. |

## Current Baseline

The codebase already contains useful pieces:

1. `PlanningAgentRosterPanel` derives live agent rows from `DataContext` and opens `AgentDetailModal`.
2. `AgentDetailModal` already displays feature links, phase/task hints, session lineage, token/context usage, and transcript navigation.
3. `PhaseOperationsPanel` exposes phase tasks, readiness, blockers, and launch entry points.
4. `PlanningLaunchSheet` prepares provider, model, worktree, approval, and command override state.
5. `services/planning.ts` adapts planning APIs for summary, graph, feature context, and phase operations.
6. `types.ts` already includes `AgentSession`, `FeaturePlanningContext`, `PhaseOperations`, and launch preparation contracts.

The main implementation need is to normalize session-to-planning correlation into a reusable board contract, then build UI that composes existing surfaces without duplicating transcript or launch logic.

## Scope and Fixed Decisions

1. V1 ships a visual board plus feature-scoped lane.
2. V1 supports prompt/command preview and copy actions.
3. V1 does not directly execute generated commands from the new board.
4. Transcript content remains owned by the session transcript surface.
5. Markdown/frontmatter remains the planning source of truth.
6. Existing launch preparation APIs may be reused for provider/model/worktree metadata, but the new board can remain copy-only.
7. V1 includes rich board interaction: animated live-state cards, grouping modes, selected-card detail, relationship highlighting, and prompt context composition.
8. V1 animation must respect reduced-motion preferences and preserve stable layout dimensions.
9. Drag-to-compose is optional and must have explicit click or keyboard alternatives; drag-to-execute is deferred.

## Architecture

### Backend

Add a board-oriented aggregation layer that composes:

1. session records and lineage
2. explicit feature links
3. phase/task hints
4. planning graph and phase operation data
5. transcript route references
6. command/prompt preview inputs
7. relationship metadata for parent/root/sibling sessions and linked planning entities
8. board activity markers suitable for list/detail display without transcript hydration

Preferred target:

1. extend `backend/application/services/agent_queries/planning.py` if the logic fits the current planning query service
2. otherwise add a focused service under `backend/application/services/agent_queries/planning_sessions.py`

The backend should return page-ready DTOs so the frontend does not reimplement correlation confidence rules.

### Frontend

Add board and prompt preview components under `components/Planning/`:

1. `PlanningAgentSessionBoard.tsx`
2. `PlanningAgentSessionCard.tsx`
3. `PlanningAgentSessionDetailPanel.tsx`
4. `PlanningNextRunPreview.tsx`
5. optional `PlanningFeatureAgentLane.tsx`
6. `PlanningBoardToolbar.tsx`
7. `PlanningBoardRelationshipLayer.tsx`
8. `PlanningPromptContextTray.tsx`

Reuse existing primitives and routes:

1. `AgentDetailModal` for rich session detail where practical
2. `PhaseOperationsPanel` links for phase detail
3. session routes for transcript inspection
4. `PlanningLaunchSheet` concepts for provider/model/worktree labels
5. existing planning primitives for status, readiness, and lineage display

### Data Contracts

Add shared types to `types.ts`:

1. `PlanningSessionCorrelation`
2. `PlanningAgentSessionCard`
3. `PlanningAgentSessionBoardGroup`
4. `PlanningNextRunPreview`
5. `PlanningNextRunContextRef`
6. `PlanningBoardGroupingMode`
7. `PlanningSessionRelationship`
8. `PlanningSessionActivityMarker`

Recommended fields for `PlanningAgentSessionCard`:

1. `sessionId`
2. `agentName`
3. `agentType`
4. `state`
5. `model`
6. `featureId`
7. `featureName`
8. `phaseNumber`
9. `phaseTitle`
10. `batchId`
11. `taskId`
12. `taskTitle`
13. `correlation`
14. `transcriptHref`
15. `planningHref`
16. `phaseHref`
17. `parentSessionId`
18. `rootSessionId`
19. `lastActivityAt`
20. `tokenSummary`
21. `relationships`
22. `activityMarkers`
23. `motionState`
24. `contextActions`

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Correlation Contract and Query Foundation | 8 pts | 3-4 days | Yes | Normalize session-to-feature/phase/task correlation and expose board DTOs |
| 2 | Rich Board UI and Card Components | 12 pts | 4-5 days | Yes | Render animated grouped cards with transcript, planning, and relationship interactions |
| 3 | Feature Drill-Down and Detail Integration | 8 pts | 3-4 days | Partial | Add feature-scoped agent lane, selected-card detail, and lineage highlighting |
| 4 | Next-Run Prompt Preview and Context Composer | 10 pts | 4-5 days | Yes | Generate copyable CLI command and prompt skeleton from selected sessions, cards, and artifacts |
| 5 | Tests, Telemetry, Performance, and Rollout | 8 pts | 3-4 days | Final gate | Add tests, telemetry, reduced-motion checks, performance checks, and docs notes |

Total estimate: 46 story points over 3-5 weeks.

## Phase 1: Correlation Contract and Query Foundation

### Objectives

1. Define board-ready session and correlation DTOs.
2. Reuse existing session, planning, and phase operation data.
3. Make weak/inferred mappings explicit with confidence and evidence.

### Primary Targets

1. `backend/application/services/agent_queries/planning.py`
2. `backend/application/services/agent_queries/models.py`
3. `backend/routers/planning.py` or `backend/routers/agent.py`
4. `types.ts`
5. `services/planning.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PASB-101 | DTO Contract | Define backend and frontend types for board cards, groups, correlation evidence, relationships, activity markers, and next-run context refs. | Types capture explicit and inferred mapping, evidence refs, route refs, relationship refs, activity markers, and card state without frontend-only inference. | 2 pts | backend-architect, frontend-developer | None |
| PASB-102 | Session Correlation Service | Build correlation logic using linked feature ids, phase hints, task hints, lineage, command tokens, and planning refs. | Each card includes confidence, source labels, and evidence refs; weak mappings are distinguishable. | 3 pts | python-backend-engineer | PASB-101 |
| PASB-103 | Board Query Endpoint | Expose project and feature-scoped board responses with grouping metadata, relationship metadata, and lightweight activity markers. | API supports project-wide board and `featureId` filtered board with stable response shape. | 2 pts | python-backend-engineer | PASB-102 |
| PASB-104 | Frontend Service Adapter | Add `services/planning.ts` helpers that adapt backend snake_case to frontend camelCase. | Frontend can fetch board groups and card detail without direct fetch duplication. | 1 pt | frontend-developer | PASB-103 |

### Quality Gates

1. Backend unit tests cover explicit, inferred, weak, and unknown correlation states.
2. Frontend type checks pass.
3. Existing planning summary, graph, feature context, and phase operations APIs remain unchanged.

## Phase 2: Rich Board UI and Card Components

### Objectives

1. Add a Kanban-style board surface to the planning area.
2. Support grouping by state, feature, phase, agent/model, and known worktree.
3. Keep cards dense, stable, animated, and navigable.
4. Add relationship-aware hover/focus/selection behavior.

### Primary Targets

1. `components/Planning/PlanningAgentSessionBoard.tsx`
2. `components/Planning/PlanningAgentSessionCard.tsx`
3. `components/Planning/PlanningBoardToolbar.tsx`
4. `components/Planning/PlanningBoardRelationshipLayer.tsx`
5. `components/Planning/PlanningHomePage.tsx`
6. `components/Planning/PlanningRouteLayout.tsx`
7. `components/Planning/__tests__/`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PASB-201 | Board Shell | Add grouped board layout with toolbar controls for grouping and filters. | Board can switch grouping without layout jumps and handles loading, empty, and error states. | 2 pts | ui-engineer-enhanced | PASB-104 |
| PASB-202 | Session Card | Implement card with agent, session, model, feature, phase/task, state, time, token/context summaries, activity marker, and fixed-size live regions. | Card is readable at compact density, avoids layout jumps, and has accessible labels for primary links. | 2 pts | ui-engineer-enhanced | PASB-201 |
| PASB-203 | Planning Links | Add card actions for transcript, feature planning context, phase operations, and parent/root session. | All links route to existing surfaces and are hidden or disabled when unavailable. | 2 pts | frontend-developer | PASB-202 |
| PASB-204 | Live Refresh Integration | Reuse existing data/live/cache mechanisms so active session state refreshes predictably. | Board updates after session/planning changes without manual reload in normal active flows. | 2 pts | frontend-developer | PASB-201 |
| PASB-205 | Motion and Reduced Motion | Add subtle live-state animation, animated state transitions, and reduced-motion fallbacks. | Running/thinking cards communicate live state without expensive layout work; reduced-motion users receive static indicators. | 2 pts | ui-engineer-enhanced | PASB-202 |
| PASB-206 | Relationship Highlighting | Highlight parent/root/sibling sessions and linked planning entities on hover, focus, and selection. | Related cards and planning refs are visually connected, while weak relationships use lower-confidence styling. | 2 pts | frontend-developer, ui-engineer-enhanced | PASB-103, PASB-202 |

### Quality Gates

1. Component tests cover grouping modes and empty/error states.
2. Keyboard navigation reaches board controls and card actions.
3. Board does not hydrate full transcripts in list rendering.
4. Reduced-motion behavior is covered by a focused test or implementation check.
5. Relationship highlighting works without blocking basic card navigation.

## Phase 3: Feature Drill-Down and Detail Integration

### Objectives

1. Add a feature-scoped agent/session lane to planning feature detail.
2. Connect existing agent detail modal and phase operations flows.
3. Make active/recent sessions visible without leaving feature context.
4. Add a selected-card detail surface with latest activity, evidence, and context actions.

### Primary Targets

1. `components/Planning/PlanningNodeDetail.tsx`
2. `components/FeatureExecutionWorkbench.tsx`
3. `components/Planning/AgentDetailModal.tsx`
4. `components/Planning/PlanningAgentRosterPanel.tsx`
5. `components/Planning/PlanningAgentSessionDetailPanel.tsx`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PASB-301 | Feature Agent Lane | Render filtered cards for selected feature in node/detail or workbench context. | Feature detail shows active and recent linked sessions with state and phase/task context. | 2 pts | frontend-developer | PASB-203 |
| PASB-302 | Card Detail Reuse | Reuse or extend `AgentDetailModal` so card selection shows lineage, features, phase/task hints, and token context. | Detail view avoids duplicating modal semantics and preserves accessibility behavior. | 2 pts | ui-engineer-enhanced | PASB-301 |
| PASB-303 | Weak Link Presentation | Add visible confidence/evidence presentation for inferred mappings. | Inferred cards show why they are linked and do not look equivalent to explicit links. | 1 pt | frontend-developer | PASB-102 |
| PASB-304 | Cross-Surface Navigation | Add deep links from board to feature planning context, phase operations, and session transcript. | Navigation preserves selected feature/session where route supports it. | 1 pt | frontend-developer | PASB-301 |
| PASB-305 | Activity Detail Panel | Add a selected-card panel with latest activity markers, transcript freshness, command/tool markers, evidence, lineage, and token/context summary. | Users can understand what the session is doing and add it to prompt context without opening the full transcript. | 2 pts | frontend-developer, ui-engineer-enhanced | PASB-103, PASB-302 |

### Quality Gates

1. Existing agent roster tests still pass.
2. Feature detail handles zero, one, and many session cards.
3. Weak mapping labels are present in snapshots or component tests.
4. Selected-card detail has accessible focus management and does not obscure board navigation.

## Phase 4: Next-Run Prompt Preview and Context Composer

### Objectives

1. Generate a copyable CLI command and prompt skeleton for continuing work.
2. Let the user choose feature, phase, batch/task, prior sessions, and artifact refs.
3. Keep the flow copy/preview-only unless routed through existing launch controls.
4. Let users add session cards and artifacts into the prompt context through explicit controls, with optional drag-to-compose.

### Primary Targets

1. `components/Planning/PlanningNextRunPreview.tsx`
2. `components/Planning/PlanningAgentSessionDetailPanel.tsx`
3. `components/Planning/PlanningPromptContextTray.tsx`
4. `services/planning.ts`
5. `services/execution.ts`
6. `backend/application/services/agent_queries/planning.py`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PASB-401 | Preview Contract | Define next-run preview DTO with command, prompt, context refs, transcript refs, and warnings. | Contract can represent `/dev:execute-phase`, `/dev:quick-feature`, or plan-specific continuation prompts. | 2 pts | backend-architect, python-backend-engineer | PASB-101 |
| PASB-402 | Prompt Composer | Implement deterministic prompt composer from feature, phase, batch/task, selected sessions, and artifact refs. | Preview output is stable, copyable, and explains missing context warnings. | 3 pts | python-backend-engineer | PASB-401 |
| PASB-403 | Preview Panel UI | Add UI for selecting prior sessions/context refs and rendering command plus prompt skeleton. | User can inspect and copy command and prompt separately. | 2 pts | frontend-developer, ui-engineer-enhanced | PASB-402 |
| PASB-404 | Launch Sheet Alignment | Where provider/model/worktree choices are shown, reuse existing launch preparation labels and constraints. | UI does not introduce a competing execution path or bypass approval semantics. | 1 pt | frontend-developer | PASB-403 |
| PASB-405 | Context Tray Interactions | Add explicit controls to add/remove session cards, phase refs, artifact refs, and transcript refs from the prompt context tray. | Context selection is inspectable, reversible, and updates preview output immediately. | 1 pt | frontend-developer | PASB-403 |
| PASB-406 | Optional Drag-to-Compose | Add drag-to-compose only if click and keyboard alternatives are implemented first. | Dragging a card adds context to preview only; it never executes or launches work. | 1 pt | ui-engineer-enhanced | PASB-405 |

### Quality Gates

1. Prompt composer tests cover feature-only, phase-specific, task-specific, and prior-session continuation cases.
2. Copy actions are covered by frontend tests.
3. The preview clearly states when it is not executing anything.
4. Drag-to-compose, if shipped, has equivalent click and keyboard paths.

## Phase 5: Tests, Telemetry, Performance, and Rollout

### Objectives

1. Add regression coverage for backend correlation and frontend board behavior.
2. Instrument usage without logging full prompt text or transcript content.
3. Validate animation and board density performance.
4. Stage rollout safely behind existing planning UI controls if needed.

### Primary Targets

1. `backend/tests/`
2. `components/Planning/__tests__/`
3. `services/telemetry.ts` or existing telemetry helpers
4. README or developer reference notes if current docs require it

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| PASB-501 | Backend Tests | Cover board query, correlation confidence, and prompt preview composition. | Tests prove deterministic mappings and safe unknown-state behavior. | 2 pts | python-backend-engineer | PASB-402 |
| PASB-502 | Frontend Tests | Cover board grouping, card links, relationship highlighting, feature lane, reduced-motion behavior, and copy preview actions. | Tests run with existing planning component suite and avoid brittle layout assertions. | 3 pts | frontend-developer | PASB-403, PASB-206 |
| PASB-503 | Telemetry | Add events for board opened, grouping changed, card opened, transcript link clicked, context added, prompt copied, and reduced-motion fallback used where available. | Telemetry excludes full transcript and prompt content. | 1 pt | frontend-developer | PASB-403 |
| PASB-504 | Performance Validation | Check board rendering with large card sets and live-state updates. | Board remains responsive with hundreds of cards and animation does not cause obvious layout thrash. | 1 pt | react-performance-optimizer, ui-engineer-enhanced | PASB-205 |
| PASB-505 | Rollout Validation | Run build, focused planning tests, backend planning tests, and manual route QA. | Validation commands pass or failures are documented with actionable follow-up. | 1 pt | task-completion-validator | PASB-501, PASB-502 |

### Quality Gates

1. `npm run build` passes.
2. Focused planning component tests pass.
3. Backend planning/correlation tests pass.
4. Manual QA validates grouping, feature filtering, transcript navigation, relationship highlighting, reduced-motion behavior, and prompt copy flow.

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Session correlation is noisy | Users may trust weak links too much | Medium | Expose confidence, evidence, and unknown states explicitly |
| Board becomes visually dense | Planning surface gets harder to scan | Medium | Keep cards compact, groupable, and filterable; avoid full transcript previews |
| Prompt preview feels like execution | Users may expect commands to run | Medium | Label V1 as preview/copy-only and route execution through existing launch controls |
| Duplicate planning logic appears in frontend | Drift across planning surfaces | Medium | Keep correlation and prompt composition in backend DTOs |
| Active session updates lag | Board may look stale | Medium | Reuse existing live/cache refresh paths and show freshness metadata |
| Animation hurts usability or performance | Board feels distracting or slow | Medium | Use subtle CSS-driven motion, fixed card dimensions, and reduced-motion fallbacks |
| Drag interactions reduce accessibility | Keyboard users lose feature parity | Medium | Treat drag-to-compose as optional and require explicit non-drag alternatives |

## Deferred to V2

These recommendations should remain outside the V1 critical path:

1. Board replay and time scrub over recent activity.
2. Durable event timeline storage dedicated to replay and forensic reconstruction.
3. Drag-to-execute or drag-to-launch flows.
4. Advanced provider/model capacity view with scheduling suggestions.
5. Rich graph-layout lineage mode for large orchestrator/subagent fan-out trees.
6. Persisted custom board layouts, saved filters, and operator-specific views.
7. Automated workload balancing or assignment recommendations.

## Success Criteria

1. Project planning can render a board of active and recent agent sessions.
2. Cards are tied to feature, phase, batch, task, transcript, and session lineage where evidence exists.
3. Feature detail can show a filtered agent/session lane for that feature.
4. The user can create a copyable next-run command and prompt preview from a card or feature context.
5. Weak mappings, missing context, and preview-only behavior are explicit in the UI.
6. Live cards provide restrained motion and state transitions without layout instability.
7. Selecting a card highlights related sessions and planning entities and opens a useful activity/detail surface.
8. Users can add cards and artifacts to a prompt context tray without triggering execution.
