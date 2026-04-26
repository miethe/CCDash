---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: draft
category: enhancements
title: "PRD: Planning Agent Session Board V1"
description: "Add a rich planning-native board that shows active agent sessions as interactive cards tied to features, phases, tasks, transcripts, and next-run prompt previews."
summary: "Extend the planning control plane with an animated Kanban-style agent/session board, feature drill-down, lineage highlighting, activity detail, and prepared CLI prompt chains without requiring in-app execution."
author: codex
created: 2026-04-25
updated: 2026-04-25
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
  ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
  kind: follow_up
lineage_children: []
lineage_type: enhancement
problem_statement: CCDash shows planning state and a live agent roster, but it does not yet provide a planning-native board where operators can see which active agent sessions are working on which feature, phase, task, and prompt chain.
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
  - platform-engineering
  - engineering-leads
tags:
  - prd
  - planning
  - sessions
  - agents
  - orchestration
  - cli
  - frontend
  - interactive-board
  - animation
linked_features:
  - ccdash-planning-control-plane-v1
  - feature-execution-workbench-v1
related_documents:
  - docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  - docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
  - docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
  - docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/agent-session-board.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/feature-agent-lane.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/session-detail-panel.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/prompt-context-composer.png
context_files:
  - components/Planning/PlanningAgentRosterPanel.tsx
  - components/Planning/AgentDetailModal.tsx
  - components/Planning/PlanningLaunchSheet.tsx
  - components/Planning/primitives/PhaseOperationsPanel.tsx
  - components/Planning/PlanningNodeDetail.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/SessionInspector.tsx
  - backend/application/services/agent_queries/planning.py
  - backend/services/feature_execution.py
  - backend/routers/planning.py
  - backend/routers/execution.py
  - services/planning.ts
  - services/execution.ts
  - types.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
---

# PRD: Planning Agent Session Board V1

## Executive Summary

CCDash already has a planning control plane, phase operations, launch preparation, session links, and a live agent roster. V1 adds the missing operator view between those pieces: a planning-native agent/session board that shows active and recent agent work as interactive cards grouped by feature, phase, status, and ownership, with direct links into transcripts and a preview of the next CLI prompt that would be run.

The feature is intentionally read/prepare-first. It should make orchestration state feel live and inspectable through motion, lineage highlighting, selection, and composition interactions, while preserving a clear boundary: V1 can prepare and copy commands and prompts, but it does not need to execute them in-app.

## Visual Guidance

These generated wireframes are implementation guidance, not pixel-perfect design requirements. They should guide layout density, interaction model, and continuity with the current CCDash dark planning surfaces.

| Screen | Wireframe | Guidance |
|--------|-----------|----------|
| Planning Agent Board | [agent-session-board.png](../../implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/agent-session-board.png) | Board-level Kanban/swimlane structure, grouping controls, dense agent cards, live-state indicators, and relationship lines. |
| Feature Agent Lane | [feature-agent-lane.png](../../implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/feature-agent-lane.png) | Feature drill-down layout with phase lanes, confidence labels, active/recent cards, and phase operations context. |
| Session Detail Panel | [session-detail-panel.png](../../implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/session-detail-panel.png) | Selected-card detail panel, activity markers, transcript linkage, evidence, lineage, and add-to-context action. |
| Prompt Context Composer | [prompt-context-composer.png](../../implementation_plans/enhancements/wireframes/planning-agent-session-board-v1/prompt-context-composer.png) | Copy-only prompt context tray with selected sessions, artifacts, transcript refs, command preview, prompt preview, and drag/click-to-compose affordances. |

## Current State

The current app already provides the main ingredients:

1. `PlanningAgentRosterPanel` shows active, thinking, queued, and idle agent sessions from `DataContext`.
2. `AgentDetailModal` links an agent session to session detail, parent/root lineage, linked features, phase hints, task hints, model, and token usage.
3. `PhaseOperationsPanel` shows phase tasks, readiness, batches, ownership, blockers, and launch entry points.
4. `PlanningLaunchSheet` can prepare launch context with provider, model, worktree, approval, and command override controls.
5. Planning query APIs expose project summary, graph, feature context, and phase operations.
6. Session views and transcript append behavior provide the transcript inspection path.

What is missing is a board-level composition of those ingredients. The user can inspect agents, phases, and sessions, but cannot easily answer:

1. Which sessions are currently working on this feature?
2. Which phase and task is each agent tied to?
3. Which active sessions are orchestrators versus subagents?
4. Which transcript should I inspect for the latest evidence?
5. What would the next CLI prompt or command be if I continued this plan?
6. Which artifacts and context links would be attached to that next run?

## Problem Statement

As a developer or orchestration operator, when I look at a planning feature, I need to see the active agent sessions, their phase/task ownership, transcript evidence, and next-run prompt context together. Today those facts are spread across the planning board, agent roster, launch sheet, and session transcript pages, so continuing a multi-agent planning workflow requires manual reconstruction.

## Goals

1. Add a visual agent/session board for planning work that supports Kanban-style grouping.
2. Tie agent/session cards back to feature, phase, batch, task, transcript, and artifact context.
3. Add feature-level drill-down so a feature can show its active sessions and next-run prompt preview in one place.
4. Let the user compose or inspect the next CLI command/prompt chain without executing it in-app.
5. Reuse existing planning, execution, live-update, and session-linking contracts where possible.
6. Make the board operationally expressive with restrained animation, stable card dimensions, lineage highlighting, and activity detail.

## Non-Goals

1. Full autonomous orchestration with no user confirmation.
2. Replacing the existing planning graph, phase operations panel, or launch sheet.
3. Replacing session transcript views with a second transcript implementation.
4. Editing raw planning artifacts from the board in V1.
5. Introducing a new source of truth for planning state independent of markdown/frontmatter.
6. Time-scrubbed replay over historical session events in V1.
7. Drag-to-execute or any interaction that bypasses existing launch and approval controls.

## Users and Jobs-to-be-Done

1. Developer: "Show me what agents are running for this feature and what they are doing right now."
2. Feature owner: "Show me which phase/task each active session maps to and whether it is blocked, ready, or stale."
3. Orchestration operator: "Let me prepare the next CLI run with the correct plan, phase, task, transcript, and context artifacts."
4. Reviewer: "Show me the transcript and evidence behind an agent card before I continue or relaunch work."

## Functional Requirements

### FR-1: Agent/Session Board

The planning area must expose a board that renders agent sessions as cards.

The board must support grouping by:

1. agent state: running, thinking, queued, idle, completed, blocked, unknown
2. feature
3. phase
4. batch or task where available
5. agent or model where useful
6. worktree where known

Each card must show:

1. display agent type or orchestrator label
2. session id and session lineage hints
3. model/provider when known
4. linked feature
5. phase/task hints
6. current status and last activity time
7. token/context usage when available
8. transcript link

### FR-1A: Rich Board Interaction and Motion

The board must support an interactive, animated operating mode that improves situational awareness without creating layout instability.

V1 interactions must include:

1. subtle live-state animation for running and thinking cards
2. animated state transitions when a card moves between board groups
3. fixed card dimensions or reserved regions so live updates do not cause layout jumps
4. hover and focus states that expose primary actions without covering important card content
5. reduced-motion behavior for users who prefer reduced animation
6. clear visual distinction between live animation and actionable execution controls

V1 board modes should include:

1. Kanban by session state
2. feature swimlanes with phase grouping
3. phase swimlanes with task or batch grouping where data exists

### FR-1B: Lineage and Relationship Highlighting

The board must help users understand orchestration fan-out and session relationships.

V1 relationship interactions must include:

1. highlighting parent, root, and sibling sessions when a card is hovered, focused, or selected
2. highlighting the linked feature, phase, batch, and task when the card has reliable correlation
3. exposing weak or inferred relationships with lower-confidence styling
4. optional lightweight connector lines or edge highlights where they remain readable
5. a selected-card state that keeps related cards highlighted while the detail panel is open

### FR-2: Feature Drill-Down Agent Lane

Feature detail views must include an agent/session lane that filters the board to the selected feature.

The lane must show:

1. active sessions tied to the feature
2. recent completed sessions tied to the feature
3. sessions with weak or inferred feature linkage, marked as such
4. phase and task association for each session
5. direct links to phase operations and transcript detail

### FR-3: Transcript and Planning Linkage

The board must bridge from a session card to transcript and planning context.

Required navigation:

1. open session transcript by session id
2. open feature planning context
3. open phase operations for a phase number
4. open the source plan or progress artifact when available
5. open parent or root session for subagent sessions

### FR-3A: Session Activity Detail

Selecting a session card must open a detail surface that provides fast operational context without loading the full transcript into the board.

The detail surface must show:

1. latest activity summary or event markers when available
2. transcript link and transcript freshness metadata
3. command/tool markers when available from session data
4. feature, phase, batch, and task evidence
5. parent/root session lineage
6. model, token, and context utilization summary
7. actions to add the card/session as context for the next-run preview

### FR-4: Next-Run Prompt Preview

The feature must provide a prompt/command preview panel for continuing work.

The preview must include:

1. recommended CLI command or workflow token
2. feature id or slug
3. phase number and task/batch id when selected
4. selected context artifacts
5. linked transcript ids
6. generated prompt text or prompt skeleton
7. copy action for command and prompt

V1 may keep this as a preview-only flow. Execution can remain delegated to CLI or later launch orchestration.

### FR-5: Prompt Chain Setup

The user must be able to chain the next run from the current card or feature context.

V1 chain setup must support:

1. selecting one or more prior sessions as context
2. selecting the target feature, phase, batch, or task
3. selecting plan, PRD, progress, and context artifact refs
4. previewing the command/prompt that would be used
5. copying the prepared CLI invocation
6. adding cards to the prompt context through explicit click actions
7. optionally supporting drag-to-compose when accessible keyboard and non-drag alternatives are also present

Drag-to-compose must only add context to the preview. It must not execute or launch work.

### FR-6: Derived Correlation and Confidence

The backend must expose how a session is tied to planning context.

Correlation sources may include:

1. explicit `linkedFeatureIds`
2. phase hints
3. task hints
4. parent/root session lineage
5. command tokens
6. transcript/path evidence
7. planning artifact references

Cards must show weak or inferred mappings instead of presenting them as certain.

## Non-Functional Requirements

### Performance

1. The board must remain responsive with hundreds of session cards.
2. Feature-scoped drill-down should avoid full-project recomputation where existing planning/query caches can be reused.
3. Transcript previews must be links or summaries, not full transcript hydration in the board list.
4. Animation must stay lightweight and avoid triggering expensive layout work on every live update.

### Accessibility

1. Board grouping must be navigable by keyboard.
2. Cards must expose meaningful labels for state, feature, phase, and session links.
3. Prompt preview copy actions must have accessible labels and visible confirmation.
4. Motion must respect reduced-motion preferences.
5. Any drag-to-compose interaction must have a keyboard and button equivalent.

### Reliability

1. Missing session metadata must degrade to clear unknown/empty states.
2. Inferred mappings must include confidence and evidence.
3. Active session state should update through existing live/cache mechanisms where available.

### Security and Safety

1. V1 must not execute generated prompts unless routed through existing launch/approval controls.
2. Prompt previews must make command overrides explicit.
3. Worktree/provider/model selection must reuse existing launch preparation semantics when offered.

## Scope

### In Scope

1. Planning board view for agent/session cards.
2. Feature-scoped agent/session lane.
3. Card-to-transcript and card-to-planning navigation.
4. Derived session-to-planning correlation contract.
5. Next-run command and prompt preview.
6. Copy-only CLI continuation workflow for V1.
7. Animated live-state card treatment and state transitions.
8. Grouping modes for state, feature, phase, agent/model, and known worktree.
9. Relationship highlighting for parent/root/sibling sessions and linked planning entities.
10. Selected-card detail surface with activity markers and prompt-context actions.
11. Click-to-compose prompt context, with drag-to-compose allowed only when accessible fallback controls exist.

### Out of Scope

1. Full prompt execution inside the UI.
2. Autonomous fan-out orchestration without approval.
3. Editing PRDs, implementation plans, or progress files from the board.
4. Persisting a second planning model that competes with markdown/frontmatter.
5. Durable board replay and time scrub.
6. Drag-to-execute, auto-launch, or execution bypass from board cards.
7. Advanced capacity scheduling or workload balancing across providers.

## Deferred to V2

The following ideas are valuable but should not block V1:

1. Board replay and time scrub for reconstructing recent multi-agent activity.
2. Durable event timeline storage dedicated to board playback.
3. Drag-to-execute or drag-to-launch after explicit approval model design.
4. Advanced capacity/load view with scheduling suggestions across provider/model pools.
5. Rich graph-layout lineage mode for large orchestrator/subagent trees.
6. Persisted custom board layouts, saved filters, and operator-specific views.

## Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|--------------------|
| Feature-to-session visibility | Users inspect roster and sessions separately | Feature detail shows active and recent sessions in one lane | Manual QA plus UI tests |
| Next-run preparation | Users manually reconstruct command and context | Prompt preview lists command, artifacts, transcripts, and target task | Component tests and copy telemetry |
| Session correlation clarity | Weak mappings can look like normal links | Cards expose confidence/evidence for inferred mappings | Contract tests and UI snapshots |
| Transcript navigation | Transcript access requires separate session search | Card has direct transcript and lineage actions | E2E or route-level tests |
| Board interaction clarity | Roster rows and planning state are visually separate | Live cards animate state, highlight relationships, and open activity detail | Component tests, reduced-motion checks, manual QA |

## Dependencies and Assumptions

1. Existing `AgentSession` fields continue to include status, feature links, phase hints, task hints, lineage, model, token, and context usage where available.
2. Planning query service remains the source for feature and phase operations context.
3. Session transcript views remain the canonical transcript inspection surface.
4. Existing launch preparation APIs can be reused for provider/model/worktree metadata where prompt preview needs them.
5. V1 can ship without starting commands from the board.

## Target State

When a user opens Planning or a feature detail view, they can see active agent work as cards connected to the plan. Selecting a card shows the session transcript link, feature/phase/task context, correlation evidence, and an option to prepare the next run. The prepared run shows the exact CLI command and prompt skeleton with selected artifacts and context links, ready to copy or later route through launch orchestration.

## Acceptance Criteria

1. A planning agent/session board renders active and recent sessions as cards.
2. Board grouping can switch between state, feature, and phase.
3. Feature detail includes a filtered agent/session lane.
4. Each card links to transcript, feature planning context, phase operations, and parent/root session where available.
5. Cards expose correlation confidence/evidence for inferred feature/phase/task mappings.
6. A prompt preview panel generates a copyable command and prompt skeleton for a selected feature/phase/task/session context.
7. V1 does not execute commands directly from the new board unless routed through existing launch/approval controls.
8. Running/thinking cards animate subtly, while reduced-motion users receive non-animated state indicators.
9. Selecting a card highlights related lineage and planning context and opens an activity/detail surface.
10. Users can add session cards to the next-run prompt context through click controls, with drag-to-compose allowed only as an enhancement.
