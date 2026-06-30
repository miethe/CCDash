---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: draft
category: enhancements
title: "PRD: Session Transcript Orchestration Intelligence V1"
description: "Promote CCDash session transcripts into a navigable orchestration view with inferred titles, minimap navigation, workflow/team/task registers, effort transitions, plan metadata, and token usage rails."
summary: "Add derived transcript intelligence so operators can understand what a session did, where major orchestration events happened, how tasks and workflows evolved, and where token burn accrued."
created: 2026-06-30
updated: 2026-06-30
priority: high
risk_level: medium
complexity: high
track: Sessions / Transcript Intelligence / Orchestration
feature_slug: session-transcript-orchestration-intelligence-v1
feature_family: session-transcript-intelligence
feature_version: v1
owner: platform-engineering
owners:
  - platform-engineering
  - fullstack-engineering
  - ai-integrations
contributors:
  - codex
audience:
  - ai-agents
  - developers
  - platform-engineering
  - engineering-leads
tags:
  - prd
  - sessions
  - transcript
  - workflows
  - task-register
  - effort
  - tokens
  - claude-code
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md
related_documents:
  - docs/project_plans/reports/plan-2-ccdash-observability-integration-analysis-2026-03-21.md
  - docs/project_plans/design-specs/session-transcript-orchestration-intelligence-v1.md
  - docs/project_plans/feature_contracts/enhancements/per-message-token-usage.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
  - docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-transcript-append-deltas-v1.md
context_files:
  - App.tsx
  - components/SessionInspector.tsx
  - components/SessionInspector/TranscriptView.tsx
  - components/SessionInspector/SessionInspectorPanels.tsx
  - components/SessionCard.tsx
  - types.ts
  - services/queries/sessions.ts
  - services/apiClient.ts
  - backend/routers/api.py
  - backend/application/services/sessions.py
  - backend/application/services/agent_queries/session_detail.py
  - backend/parsers/sessions.py
  - backend/models.py
  - services/live/topics.ts
changelog_required: true
commit_refs: []
pr_refs: []
files_affected: []
---

# PRD: Session Transcript Orchestration Intelligence V1

## Executive Summary

CCDash already parses Claude Code and Codex sessions into rich session summaries, transcript rows, tool summaries, per-message token usage, session usage totals, workflow evidence, and planning-session board data. `plan-2-ccdash-observability-integration-analysis-2026-03-21.md` is the root architecture context: this plan extends the closed-loop observability model into the transcript reader rather than starting a new session-intelligence system. The transcript experience still behaves mostly like a chronological reader. Operators can see raw TaskCreate/TaskUpdate rows, workflow calls, effort commands, subagents, token totals, and plan hints, but they must read linearly and infer the operating story themselves.

This enhancement adds a derived transcript intelligence layer and matching UI:

1. inferred session names for `/sessions` cards,
2. a scrollable transcript minimap with alternate projections,
3. task and workflow registers in the transcript sidepane,
4. workflow and Agent Teams representation for Claude Code sessions,
5. effort-level detection and transition markers,
6. plan tier/mode/task linkage,
7. chat-level token rails and details that reflect source-data limits honestly.

V1 should not replace raw transcript fidelity. It should add an index and interaction layer on top of the current transcript so long sessions become navigable and actionable.

## Current Baseline

The codebase is not starting from zero:

1. `/sessions` is a query-param driven inspector. The selected session link shape is `/sessions?session=<id>&tab=transcript`; there is no active `/sessions/:id` route.
2. Frontend session data flows through `services/queries/sessions.ts` and `services/apiClient.ts`.
3. Backend session routes include `GET /api/sessions`, `GET /api/sessions/{id}`, and `GET /api/sessions/{id}/logs`; transcript reading is centralized in `backend/application/services/sessions.py`.
4. `AgentSession` already carries `workflowId`, `subagentParentId`, `skillName`, `effortTier`, `modelVariant`, token totals, model identity, agents, skills, and `toolSummary`.
5. `SessionLog` already carries `tokenUsage`, `toolCall`, `linkedSessionId`, `relatedToolCallId`, metadata, and subagent-thread structure.
6. `components/SessionInspector/TranscriptView.tsx` already extracts Task/Agent tool details, TaskCreate/TaskUpdate details, subagent links, tool groups, commit events, and per-message token captions.
7. The transcript detail already has a three-pane layout; V1 should add focused components/contracts, not rebuild the inspector shell.
8. `session-transcript-append-deltas-v1` is the transcript-specific live update baseline. V1 must not introduce a second live transport.
9. `planning-agent-session-board-v1` introduced planning/session correlation, transcript links, lineage, token summaries, and session card concepts.
10. `workflow-registry-and-correlation-v1` introduced workflow identity/correlation foundations outside the transcript.
11. `claude-code-session-usage-analytics-alignment-v1`, `claude-code-session-usage-attribution-v2`, and `claude-code-session-context-and-cost-observability-v1` define the canonical token, cost, context, and attribution semantics.
12. Launch-time capture sidecars can populate `effort_tier` and `model_variant`, but transcript-derived `/effort` changes are not yet promoted as session-level state.

Current implementation gaps to account for:

1. `effortTier` is visible in the full Forensics tab with `modelVariant`, but not consistently promoted to the session card, header, or transcript markers.
2. `workflowId` is typed and backend-filled in places, but workflow identity is not directly rendered in the `/sessions` transcript experience.
3. Agent/team data is currently closer to sidecar counts and unread counts than a first-class team/workflow call viewer.
4. Some older planning/document surfaces still emit path-style session links such as `/sessions/{id}` or `#/sessions/{id}` even though the active route is query-param based.

Live sample evidence from `S-18d3c99f-0c34-4f5d-8a40-82ab21977e89`:

1. current title is `Feature Planning`, which is less useful than the first meaningful command `/plan:plan-feature` plus the feature/deferred-item focus,
2. the transcript contains `/effort ultracode`, a dynamic Workflow run, `TaskCreate x5`, `TaskUpdate x5`, and a later `/effort high`,
3. the session summary still reports `effortTier: null`,
4. the session has high-value token totals and per-message token data, but no transcript-level token rail or workflow/team aggregation.

## Problem Statement

CCDash sessions contain enough structure to reconstruct an orchestration story, but the UI leaves that structure scattered:

1. session cards often use generic titles or raw ids,
2. transcript readers cannot jump by role, command, workflow, task, branch, commit, or token hotspot,
3. task mutations appear as repeated noisy tool rows instead of a stateful task register,
4. workflow and Agent Teams usage does not have a first-class transcript representation,
5. effort-level changes are visible only as raw `/effort` commands,
6. plan tiers, dev-execution modes, and task-level plan metadata are not linked to the session rows that used them,
7. token usage is present at multiple granularities, but the UI does not explain source coverage or avoid false per-tool precision.

## Goals

1. Infer useful session display names without overwriting raw ids or explicit labels.
2. Add a scrollable, interactive minimap that can switch between outline, role, task, workflow, branch, and token projections.
3. Build a transcript sidepane Task view that maintains a derived task register from TaskCreate/TaskUpdate and related task signals.
4. Build a transcript sidepane Workflow view that captures Workflow tool calls, dynamic workflow notifications, output-file links, and Agent Teams where detectable.
5. Surface effort level as a first-class session fact beside model identity, including transcript markers for effort transitions.
6. Link plan tier, execution mode, dev-execution Mode C/D/E, phase, task, and external task ids to transcript rows.
7. Present chat-level token usage with clear coverage semantics: per-message when available, attribution-event detail when available, aggregate fallback when not.

## Non-Goals

1. Replacing the Workflow Registry page or Planning Agent Session Board.
2. Building a Claude Code workflow authoring surface.
3. Assigning token usage to individual tool calls when the source provides only assistant-turn usage.
4. Solving every non-Claude platform event shape in V1.
5. Persisting a new marker table before the derived index contract is validated.
6. Rewriting the whole Session Inspector layout.
7. Solving exclusive feature cost ownership or multi-feature commit cost attribution.
8. Delivering Codex parity for transcript orchestration semantics.
9. Building durable replay/time-scrub for planning boards or transcript timelines.
10. Modeling workflow package creation, workflow editing, or workflow launch UX.
11. Adding drag-to-launch, workload balancing, or planning automation to the Planning Agent Session Board.
12. Expanding runtime ingestion beyond current JSONL/session-sidecar sources.

## External Source Notes

Claude Code docs as of 2026-06-30 shape the V1 assumptions:

1. Workflows are script-defined orchestrations that can run multiple subagents and save results to output files, so CCDash should treat workflow file names and output paths as linkable evidence rather than ordinary prose.
2. Agent Teams are concurrent peer agents over a shared task list with separate execution contexts, so CCDash must not collapse them into a single normal Agent tool call without fixture proof.
3. `/effort` has distinct Claude Code levels; `ultracode` maps to advanced automatic workflow orchestration behavior, so V1 should represent `max` and `ultracode` with distinct badges and transcript transitions.
4. Token/cost docs distinguish session usage and Agent Team costs; CCDash should surface agent/team token usage only when the source data identifies the scope.

Reference pages consulted:

1. `https://docs.anthropic.com/en/docs/claude-code/workflows`
2. `https://docs.anthropic.com/en/docs/claude-code/agent-teams`
3. `https://docs.anthropic.com/en/docs/claude-code/interactive-mode`
4. `https://docs.anthropic.com/en/docs/claude-code/costs`

## Users and Jobs

1. **Operator coordinating agentic work**: "Give me the name and shape of this session immediately, then let me jump to the important parts."
2. **Planner reviewing Claude Code workflows**: "Show me which workflow ran, which agents or teams participated, which track failed, and which artifacts it produced."
3. **Reviewer auditing execution quality**: "Show effort changes, Mode D boundaries, task-state changes, and commits in one navigable transcript index."
4. **Cost/performance investigator**: "Show me where token burn happened, what model or agent produced it, and whether the detail is directly observed or inferred."

## Functional Requirements

### FR-1: Inferred Session Names

The session list and session detail header must expose an inferred title when confidence is sufficient.

Derivation order:

1. first meaningful command plus feature slug or key argument,
2. first skill invocation plus feature slug,
3. first workflow title plus feature slug,
4. first plan/artifact target,
5. existing explicit title,
6. raw session id.

Ignored sources include `/clear`, continuation summaries, local-command caveats, empty shell output, and pure metadata rows.

The API should expose:

1. `displayTitle`,
2. `displayTitleSource`,
3. `displayTitleConfidence`,
4. `displayTitleParts`.

The UI keeps the raw session id in smaller secondary text.

### FR-2: Transcript Intelligence Index

Add a derived index contract for a transcript:

1. marker id and source log id,
2. sequence/timestamp,
3. marker kind,
4. actor/role,
5. label and detail,
6. severity/accent category,
7. linked session/task/workflow/plan/artifact ids,
8. token delta and cumulative known token total when available,
9. confidence and source method.

V1 may derive the index on demand from session detail/log rows. The contract must be stable enough to persist later.

### FR-3: Scrollable Minimap

The transcript view must show a right-side minimap for the selected session with:

1. click-to-jump,
2. keyboard navigation,
3. current viewport indicator,
4. selected marker state,
5. mode switcher for outline, roles, tasks, workflows, branches, and tokens,
6. marker counts and empty states.

The minimap must support long transcripts without forcing full raw row rendering in the sidepane.

### FR-4: Task Register and Transcript Grouping

The right sidepane must include a Task view that:

1. creates task entries from TaskCreate,
2. updates state from TaskUpdate and related task text,
3. links task rows to transcript markers,
4. links task ids to plan tasks or IntentTree nodes when known,
5. shows state, owner/agent, timestamps, and latest evidence,
6. groups adjacent TaskCreate/TaskUpdate rows in the transcript into one expandable summary row.

Raw rows must remain accessible through expansion and deep links.

### FR-5: Workflow and Agent Teams Representation

The right sidepane must include a Workflow view that detects:

1. explicit Workflow tool calls,
2. dynamic workflow start/completion system messages,
3. workflow task notifications and output-file links,
4. workflow `.js` file names when present,
5. workflow stage/track names when recoverable,
6. normal subagent threads,
7. Agent Teams event shapes once confirmed by source fixtures.

The UI should distinguish:

1. normal Agent/Task delegation,
2. workflow-orchestrated delegation,
3. Agent Teams delegation,
4. forked/branched continuation threads.

### FR-6: Effort Level Detection and Transitions

Effort level must be displayed beside model identity on:

1. session list cards,
2. session detail header,
3. transcript markers,
4. task/workflow sidepane details where relevant.

Source precedence:

1. launch sidecar `effort_tier`,
2. session metadata payload `effort`,
3. `/effort` command rows and command stdout,
4. dynamic workflow messages that map to effort tiers,
5. null with explicit "unknown" state.

The transcript must show transition markers when effort changes mid-session, including `ultracode -> high` style summaries.

### FR-7: Plan Tier, Mode, and Task Metadata

When a session references a plan, feature slug, or task id, the transcript sidepane must show:

1. PRD and plan links,
2. tier,
3. execution model,
4. wave/phase/task ids,
5. Mode C/D/E boundaries from dev-execution plans or prompts,
6. IntentTree links when available,
7. confidence/source metadata.

This data should be derived from existing planning docs and task/linking services, not hand-coded in the transcript component.

### FR-8: Chat-Level Token Usage

The transcript must add a token rail and richer detail affordances:

1. per-message segments from `SessionLog.tokenUsage`,
2. cumulative known total through each marker,
3. cache vs new/model IO distinction,
4. per-agent/subagent totals when linked session or usage-attribution data exists,
5. per-tool-call detail only when event-level source data exists,
6. coverage labels when token data is aggregate-only or turn-level-only.

The UI must not split a single assistant-turn token total across tool calls unless the source provides event-level attribution.

## Acceptance Criteria

#### AC-1: Inferred session title appears on session list and detail header
- target_surfaces:
    - components/SessionInspector.tsx
    - components/SessionInspector/TranscriptView.tsx
    - types.ts
- propagation_contract: Backend inferred-title fields flow into `AgentSession` and are rendered as primary title, with raw id rendered as secondary text.
- resilience: Missing inferred-title fields fall back to existing title or id with no blank primary label.
- visual_evidence_required: desktop 1440px screenshot of `/sessions` list and selected detail header.
- verified_by: PLAN-T1, API-T1, UI-T1, QA-T1

#### AC-2: Minimap supports role, outline, task, workflow, branch, and token projections
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - components/SessionInspector/SessionInspectorPanels.tsx
    - backend/application/services/agent_queries/session_detail.py
- propagation_contract: Transcript intelligence index returns typed markers that the minimap renders and uses for scroll/selection.
- resilience: Missing marker categories render empty-state rows and keep transcript rendering unchanged.
- visual_evidence_required: desktop screenshot of minimap with the live sample session.
- verified_by: API-T2, UI-T2, QA-T2

#### AC-3: TaskCreate and TaskUpdate clusters collapse in transcript and populate Task sidepane
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - components/SessionInspector/SessionInspectorPanels.tsx
    - types.ts
- propagation_contract: Derived task register links transcript marker ids to task sidepane rows and grouped transcript summary rows.
- resilience: Unparseable task payloads remain visible as raw tool rows and produce low-confidence sidepane entries only when an id is recoverable.
- visual_evidence_required: screenshot with collapsed task group plus expanded state.
- verified_by: API-T3, UI-T3, QA-T2

#### AC-4: Workflow and Agent Teams events have a distinct transcript sidepane representation
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - components/SessionInspector/SessionInspectorPanels.tsx
    - backend/application/services/agent_queries/session_detail.py
- propagation_contract: Workflow register entries link tool calls, system notifications, output files, agent/thread ids, and known workflow file names.
- resilience: Unknown Agent Teams event shapes show as unclassified orchestration markers until fixture support is added.
- visual_evidence_required: screenshot of `S-18d3c99f-0c34-4f5d-8a40-82ab21977e89` showing dynamic workflow start/completion.
- verified_by: API-T4, UI-T4, QA-T2

#### AC-5: Effort level is displayed and transition markers are searchable
- target_surfaces:
    - components/SessionInspector.tsx
    - components/SessionInspector/TranscriptView.tsx
    - backend/parsers/sessions.py
    - backend/application/services/sessions.py
- propagation_contract: Launch sidecar and transcript-derived effort transitions populate session summary fields and transcript markers.
- resilience: Unknown effort remains null/unknown, never guessed from model name alone.
- visual_evidence_required: screenshot showing `Ultracode -> High` on the live sample session.
- verified_by: PARSE-T1, API-T5, UI-T5, QA-T2

#### AC-6: Plan tier, dev-execution mode, and task links appear in transcript sidepane
- target_surfaces:
    - components/SessionInspector/SessionInspectorPanels.tsx
    - backend/application/services/agent_queries/session_detail.py
    - backend/application/services/planning_command_resolver.py
- propagation_contract: Plan/task references resolve through existing planning document and task link services and return typed sidepane references.
- resilience: Missing plan files or external task links show source/confidence labels instead of broken anchors.
- visual_evidence_required: screenshot of sidepane plan metadata for a plan-linked session.
- verified_by: API-T6, UI-T6, QA-T2

#### AC-7: Token rail reflects source granularity and avoids false precision
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - lib/tokenMetrics.ts
    - types.ts
- propagation_contract: `SessionLog.tokenUsage` and usage-attribution summaries feed a row-aligned rail and details popover with coverage labels.
- resilience: Rows without token data render no segment; aggregate-only sessions show a coverage notice and no fake row-level distribution.
- visual_evidence_required: screenshot with token rail and hover detail.
- verified_by: UI-T7, QA-T2

## Open Questions

| ID | Question | Owner | Default for V1 |
|----|----------|-------|----------------|
| OQ-1 | What exact JSONL shape does Claude Code Agent Teams emit? | Phase 0 researcher | Add fixture-driven support after discovery; classify unknown team rows generically before then. |
| OQ-2 | Should workflow output files be parsed during sync? | backend-architect | Link output files in V1; parse only safe metadata fields if the file exists and is readable. |
| OQ-3 | Should transcript index be persisted? | data-layer-expert | No new marker table in V1; derive through query service and cache. |
| OQ-4 | How should `/effort max` and `/effort ultracode` map to badge flair? | UX owner | Distinct badge styles, not warning states unless paired with risk signals. |
| OQ-5 | Which stale path-style session links should be normalized while adding inferred-title links? | frontend-developer | Keep query-param route canonical and update known planning/document links touched by the feature. |

## Success Metrics

| Metric | Target |
|--------|--------|
| Live sample navigation | User can jump to `/plan:plan-feature`, `/effort ultracode`, Workflow start/completion, TaskCreate cluster, and `/effort high` from minimap. |
| Session-card clarity | High-confidence inferred title appears for sessions with meaningful command/slug signals. |
| Transcript noise reduction | Adjacent task mutation rows collapse to one expandable transcript group. |
| Token clarity | Token rail shows coverage and cumulative known total without assigning unsupported per-tool tokens. |
| Effort accuracy | `/effort` transitions appear even when launch-time `effortTier` is null. |

## Rollout

1. Ship behind a frontend flag such as `VITE_CCDASH_TRANSCRIPT_ORCHESTRATION_INTEL_ENABLED`.
2. Add backend query fields as nullable/additive.
3. Validate against synthetic fixtures plus the live IntentTree session.
4. Enable minimap and inferred titles first; workflow/task/token sidepane tabs can remain hidden until their data contract is stable.
5. Add a CHANGELOG entry because the transcript surface changes visibly.
