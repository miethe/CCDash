---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
status: completed
category: enhancements
title: "Implementation Plan: Session Transcript Orchestration Intelligence V1"
description: "Build derived transcript intelligence, inferred titles, minimap navigation, task/workflow registers, effort transitions, plan metadata links, and source-aware token rails for CCDash session transcripts."
summary: "Implement a feature-flagged transcript orchestration layer on top of existing session logs and session intelligence contracts."
created: 2026-06-30
updated: 2026-06-30
priority: high
risk_level: medium
complexity: high
track: Sessions / Transcript Intelligence / Orchestration
feature_slug: session-transcript-orchestration-intelligence-v1
feature_family: session-transcript-intelligence
feature_version: v1
tier: 3
effort_estimate: "20 pts across 6 phases"
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
  - fullstack-engineering
tags:
  - implementation
  - sessions
  - transcript
  - workflows
  - task-register
  - effort
  - tokens
  - claude-code
prd: docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md
plan_ref: null
related_documents:
  - docs/project_plans/reports/plan-2-ccdash-observability-integration-analysis-2026-03-21.md
  - docs/project_plans/design-specs/session-transcript-orchestration-intelligence-v1.md
  - docs/project_plans/human-briefs/session-transcript-orchestration-intelligence-v1.md
  - .claude/worknotes/session-transcript-orchestration-intelligence-v1/decisions-block.md
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
  - components/SessionInspector/sessionInspectorShared.ts
  - components/SessionCard.tsx
  - types.ts
  - lib/tokenMetrics.ts
  - services/queries/sessions.ts
  - services/apiClient.ts
  - backend/routers/api.py
  - backend/application/services/sessions.py
  - backend/application/services/agent_queries/session_detail.py
  - backend/application/services/planning_command_resolver.py
  - backend/parsers/sessions.py
  - backend/models.py
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/transcript_intelligence.py
  - backend/application/services/agent_queries/session_detail.py
  - backend/models.py
  - backend/routers/api.py
  - components/SessionCard.tsx
  - components/SessionInspector/SessionInspectorPanels.tsx
  - components/SessionInspector/TranscriptView.tsx
  - lib/featureFlags.ts
  - types.ts
  - components/__tests__/transcriptIntelligence.test.tsx
  - backend/tests/test_transcript_intelligence.py
wave_plan:
  execution_model: workflow
  phases:
    - id: P0
      name: Code Truth Fixture and Source Audit
      phase_strategy: static
      model: sonnet
      effort: adaptive
    - id: P1
      name: Derived Index Contract
      phase_strategy: static
      model: sonnet
      effort: extended
    - id: P2
      name: Session List and Header
      phase_strategy: static
      model: sonnet
      effort: adaptive
    - id: P3
      name: Minimap and Registers
      phase_strategy: static
      model: sonnet
      effort: extended
    - id: P4
      name: Token Rail and Agent Detail
      phase_strategy: static
      model: sonnet
      effort: adaptive
    - id: P5
      name: Validation Docs and Rollout
      phase_strategy: static
      model: sonnet
      effort: adaptive
  waves:
    - id: wave-0
      phases: [P0]
    - id: wave-1
      phases: [P1]
    - id: wave-2
      phases: [P2, P3]
    - id: wave-3
      phases: [P4]
    - id: wave-4
      phases: [P5]
tasks:
  - id: PLAN-T1
    title: "Define inferred-title algorithm and contract"
    status: completed
    phase: P1
    assigned_to: backend-architect
    estimate: 1
  - id: API-T2
    title: "Build transcript intelligence index DTOs and query service"
    status: completed
    phase: P1
    assigned_to: python-backend-engineer
    estimate: 2
  - id: UI-T2
    title: "Implement minimap shell and marker modes"
    status: completed
    phase: P3
    assigned_to: ui-engineer-enhanced
    estimate: 2
---

# Implementation Plan: Session Transcript Orchestration Intelligence V1

**PRD**: `docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md`
**Design Spec**: `docs/project_plans/design-specs/session-transcript-orchestration-intelligence-v1.md`
**Human Brief**: `docs/project_plans/human-briefs/session-transcript-orchestration-intelligence-v1.md`
**Decisions Block**: `.claude/worknotes/session-transcript-orchestration-intelligence-v1/decisions-block.md`

## Objective

Deliver a feature-flagged transcript orchestration layer that makes long CCDash sessions understandable at a glance and navigable by major operational signals. This is a successor integration plan over the Plan 2 CCDash observability architecture, not a greenfield transcript rebuild:

1. inferred title,
2. effort and model identity,
3. minimap markers,
4. task register,
5. workflow/team register,
6. plan tier/mode/task links,
7. token usage coverage and cumulative burn.

## Scope and Fixed Decisions

1. V1 derives a transcript intelligence index through backend query services. It does not add a persisted marker table.
2. Raw transcript rows remain the source of truth and remain reachable.
3. TaskCreate/TaskUpdate rows may be grouped visually, but expansion must reveal raw rows.
4. Effort state uses explicit source precedence; no effort value is guessed from model identity alone.
5. Token rail semantics must distinguish observed row-level usage, attribution-event usage, and aggregate-only fallback.
6. Agent Teams support is fixture-gated. Unknown team events render as unclassified orchestration markers until the source shape is verified.
7. Implementation is additive and behind a feature flag.
8. The canonical selected-session route is `/sessions?session=<id>&tab=transcript`; path-style links are compatibility cleanup, not a new route.
9. Transcript live updates build on `session-transcript-append-deltas-v1`; V1 must not add a second event topic or polling loop.
10. Token, cost, context, and attribution semantics reuse `claude-code-session-usage-analytics-alignment-v1`, `claude-code-session-usage-attribution-v2`, and `claude-code-session-context-and-cost-observability-v1`.

## Phase Summary

| Phase | Title | Points | Target Subagents | Model | Effort | Exit Gate |
|-------|-------|--------|------------------|-------|--------|-----------|
| P0 | Code Truth Fixture and Source Audit | 2.5 | codebase-explorer, backend-architect | sonnet | adaptive | Code ownership and fixture matrix reviewed. |
| P1 | Derived Index Contract | 5 | backend-architect, python-backend-engineer | sonnet | extended | API/DTO tests pass. |
| P2 | Session List and Header | 2.5 | ui-engineer-enhanced | sonnet | adaptive | Title/effort/link UI tests pass. |
| P3 | Minimap and Registers | 5 | ui-engineer-enhanced, frontend-developer, web-accessibility-checker | sonnet | extended | Runtime smoke on live sample. |
| P4 | Token Rail and Agent Detail | 3 | frontend-developer, react-performance-optimizer | sonnet | adaptive | Token coverage tests pass. |
| P5 | Validation Docs and Rollout | 2 | task-completion-validator, documentation-writer | sonnet | adaptive | Selected gates and changelog complete. |

### Estimation Sanity Check

**Noun count (H1)**: 0 new CRUD nouns. V1 uses derived DTOs and existing session/message storage.
**Dual-impl multiplier (H2)**: Not applied because V1 avoids new persistence. If a marker table is added, re-estimate with SQLite/Postgres parity.
**Algorithmic flag (H3)**: Applies to inferred-title, effort-transition, task-register, workflow-register, and token-coverage resolvers. Budgeted in P1/P3/P4 with explicit fixtures.
**Bundle decomposition (H4)**:

| Area | Independent Est. | Notes |
|------|------------------|-------|
| Inferred titles + effort | 3 pts | Backend derivation plus UI badges. |
| Transcript index + minimap | 5 pts | Marker contract, scroll/selection, modes. |
| Task/workflow registers | 5 pts | Stateful grouping and sidepane views. |
| Plan tier/mode links | 2 pts | Existing planning docs/query reuse. |
| Token rail | 3 pts | Coverage-aware rail and details. |
| Route/link compatibility | 1 pt | Query-param route remains canonical; stale path-style links are normalized. |
| Validation/docs | 1 pt | A11y, runtime smoke, changelog. |
| **Sum** | **20 pts** | Locked total. |

**Anchor (H5)**: Planning Agent Session Board V1 and per-message-token-usage are the closest anchors. This plan is larger than per-message-token-usage because it adds minimap, task/workflow registers, and effort/plan linking, but smaller than full Planning Agent Session Board because it does not build new launch orchestration.
**Plumbing budget (H6)**: Included in P1 and P5 for DTOs, API tests, feature flag, docs, and changelog.
**Huge-file touch (H7)**: `components/SessionInspector.tsx` and `components/SessionInspector/TranscriptView.tsx` are high-friction surfaces. Apply grep/sed-scoped editing discipline and avoid full-file rewrites.

**Bottom-up total**: 20 pts.
**Top-down intuition**: 18-22 pts.
**Locked estimate**: 20 pts.

## Data Contracts

### Transcript Intelligence Index

Add a derived response shape, either embedded in session detail or returned through a focused endpoint:

```ts
export interface TranscriptIntelligenceIndex {
  sessionId: string;
  title: SessionInferredTitle;
  effortTimeline: SessionEffortTransition[];
  markers: TranscriptMarker[];
  taskRegister: TranscriptTaskRegisterItem[];
  workflowRegister: TranscriptWorkflowRegisterItem[];
  planLinks: TranscriptPlanLink[];
  tokenCoverage: TranscriptTokenCoverage;
}
```

Recommended marker fields:

1. `id`,
2. `logId`,
3. `sequence`,
4. `timestamp`,
5. `kind`,
6. `label`,
7. `detail`,
8. `actor`,
9. `accent`,
10. `confidence`,
11. `sourceMethod`,
12. `links`,
13. `tokenDelta`,
14. `cumulativeKnownTokens`.

### Inferred Title

```ts
export interface SessionInferredTitle {
  displayTitle: string;
  rawSessionId: string;
  source: 'command' | 'skill' | 'workflow' | 'artifact' | 'existing_title' | 'session_id';
  confidence: number;
  commandName?: string;
  featureSlug?: string;
  reason?: string;
}
```

### Effort Timeline

Effort state should preserve source and transitions:

```ts
export interface SessionEffortTransition {
  id: string;
  logId?: string;
  timestamp?: string;
  fromEffort?: string | null;
  toEffort: string;
  providerEffort?: string | null;
  source: 'launch_sidecar' | 'session_metadata' | 'command' | 'stdout' | 'workflow_message';
  confidence: number;
}
```

### Token Coverage

```ts
export interface TranscriptTokenCoverage {
  rowLevelKnownTokens: number;
  aggregateObservedTokens: number;
  coveragePct: number;
  sourceGranularity: 'message' | 'usage_event' | 'aggregate' | 'none';
  caveats: string[];
}
```

## Implementation Phases

### Phase P0: Code Truth Fixture and Source Audit

**Goal**: Lock supported source shapes before the shared index contract ships.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P0-T1 | Code truth and route audit | Verify current `/sessions` route shape, `App.tsx` routing, session query/API ownership, backend route ownership, and transcript component ownership before editing. | Implementation notes identify canonical route `/sessions?session=<id>&tab=transcript`, stale link emitters, and exact backend/frontend files to touch. | 0.5 | codebase-explorer | sonnet | adaptive |
| P0-T2 | Live sample audit | Capture marker expectations for `S-18d3c99f-0c34-4f5d-8a40-82ab21977e89`: `/plan:plan-feature`, `/effort ultracode`, Workflow start/completion, TaskCreate/TaskUpdate, `/effort high`, token totals. | Fixture note lists exact row kinds, timestamps, expected markers, and current null `effortTier`. | 0.5 | codebase-explorer | sonnet | adaptive |
| P0-T3 | Agent Teams source audit | Search local/live Claude Code sessions and SkillMeat/IntentTree workflow examples for Agent Teams event shape. | Supported shapes are enumerated; unknown shape is documented as a V1 unclassified marker state. | 0.5 | codebase-explorer | sonnet | adaptive |
| P0-T4 | Workflow output safety | Determine which workflow output-file metadata can be linked or parsed without leaking raw content. | Output-file policy is written in the implementation PR notes. | 0.5 | backend-architect | sonnet | adaptive |
| P0-T5 | Token granularity matrix | Document available token granularity from `SessionLog.tokenUsage`, session totals, and usage-attribution events. | Matrix states where per-tool-call token display is supported versus prohibited. | 0.5 | backend-architect | sonnet | adaptive |

### Phase P1: Derived Index Contract

**Goal**: Add backend and shared frontend types so UI components consume one contract.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P1-T1 | DTO definitions | Add `TranscriptIntelligenceIndex` types in backend models and `types.ts`. | Types include title, effort timeline, markers, task register, workflow register, plan links, and token coverage. | 1 | python-backend-engineer | sonnet | adaptive |
| P1-T2 | Inferred-title resolver | Implement derivation from command/skill/workflow/artifact/existing title/id sources. | Fixture tests cover `/clear` ignored, `/plan:plan-feature` selected, feature slug extraction, and fallback states. | 1 | backend-architect | sonnet | extended |
| P1-T3 | Effort resolver | Derive effort timeline from sidecar fields, metadata, `/effort` command rows, and stdout. | Live sample derives `ultracode -> high`; null remains unknown when no source exists. | 1 | python-backend-engineer | sonnet | adaptive |
| P1-T4 | Marker/register service | Add session-detail query helper that returns markers, task register, workflow register, and plan links. | API tests verify task/workflow markers and confidence/source labels. | 1.5 | python-backend-engineer | sonnet | adaptive |
| P1-T5 | Token coverage resolver | Compute known row-level tokens, aggregate observed tokens, coverage percent, and caveats. | Tests prove aggregate-only sessions do not get fake row-level tokens. | 0.5 | python-backend-engineer | sonnet | adaptive |

#### AC P1.1: Backend handles missing index fields
- target_surfaces:
    - backend/application/services/agent_queries/session_detail.py
    - backend/application/services/sessions.py
    - types.ts
- propagation_contract: Null/additive fields are normalized into explicit empty arrays or unknown states for the frontend.
- resilience: Older session payloads without the new index keep rendering through current SessionInspector paths.
- visual_evidence_required: false
- verified_by: P1-T1, P1-T4

### Phase P2: Session List and Header

**Goal**: Make sessions recognizable before the user opens the transcript.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P2-T1 | Session-card title rendering | Render `displayTitle` as primary and raw id as secondary on `/sessions` cards. | Screenshot shows useful inferred title and smaller id for a fixture session. | 0.75 | ui-engineer-enhanced | sonnet | adaptive |
| P2-T2 | Model/effort badges | Show effort beside model in list and detail header, including advanced effort styling. | `Ultracode -> High` displays when transitions exist; unknown state is quiet. | 0.75 | ui-engineer-enhanced | sonnet | adaptive |
| P2-T3 | Header fallback states | Add null-safe fallback tests for sessions without title/effort fields. | Missing fields do not create blank labels or crashes. | 0.5 | frontend-developer | sonnet | adaptive |
| P2-T4 | Session link compatibility | Normalize touched planning/document links to query-param session URLs and keep legacy normalization tests passing. | Known links opened from planning surfaces land on `/sessions?session=<id>&tab=transcript`; no new `/sessions/:id` route is introduced. | 0.5 | frontend-developer | sonnet | adaptive |

### Phase P3: Minimap and Registers

**Goal**: Add the core interactive transcript navigation and sidepane state views.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P3-T1 | Minimap component | Add right-side minimap with marker list, mode switcher, selected state, and current viewport indicator. | Click and keyboard navigation scroll/select transcript rows. | 1.5 | ui-engineer-enhanced | sonnet | extended |
| P3-T2 | Task register sidepane | Add Task sidepane view derived from TaskCreate/TaskUpdate entries. | Task rows show state, timestamps, transcript links, and plan/IntentTree links where known. | 1 | frontend-developer | sonnet | adaptive |
| P3-T3 | Task group transcript row | Collapse adjacent TaskCreate/TaskUpdate rows into one expandable grouped row. | Expansion shows raw rows and links to sidepane entries. | 0.75 | ui-engineer-enhanced | sonnet | adaptive |
| P3-T4 | Workflow register sidepane | Add Workflow sidepane view with workflow tool calls, dynamic completion markers, output-file links, agents/tracks, and unknown team markers. | Live sample displays workflow start/completion and stalled/passed track hints when recoverable. | 1 | frontend-developer | sonnet | adaptive |
| P3-T5 | Plan metadata sidepane | Show tier, execution model, Mode C/D/E, phase/task ids, PRD/plan links, and confidence. | Plan-linked sessions show plan metadata without broken anchors. | 0.5 | frontend-developer | sonnet | adaptive |
| P3-T6 | A11y and layout review | Verify keyboard, focus, reduced motion, and no overlapping sidepane/minimap text. | A11y review has no required fixes. | 0.25 | web-accessibility-checker | sonnet | adaptive |

#### AC P3.1: Minimap interactions are keyboard accessible
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - components/SessionInspector/SessionInspectorPanels.tsx
- propagation_contract: Marker focus updates transcript selection and transcript selection updates minimap selection.
- resilience: If a marker points to a missing row, the minimap shows disabled state and does not throw.
- visual_evidence_required: desktop screenshot of minimap plus selected transcript row.
- verified_by: P3-T1, P3-T6

### Phase P4: Token Rail and Agent Detail

**Goal**: Show token usage in context without making unsupported claims.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P4-T1 | Token rail component | Add left transcript rail with row segments, cache/model colors, cumulative tooltip, and footer total. | Rows with `tokenUsage` render segments; rows without usage render no segment. | 1 | frontend-developer | sonnet | adaptive |
| P4-T2 | Agent/workflow token summaries | Add small token/model summaries to agent and workflow sidepane items where linked session or attribution data exists. | Agent item displays token totals and opens detail without implying per-tool precision. | 0.75 | frontend-developer | sonnet | adaptive |
| P4-T3 | Coverage caveats | Add UI labels for message-level, usage-event, aggregate-only, and no-token states. | Aggregate-only fixture shows coverage notice and no row-level rail. | 0.5 | ui-engineer-enhanced | sonnet | adaptive |
| P4-T4 | Performance pass | Verify rail/minimap remain stable on long transcripts and do not break virtualization. | Large transcript smoke has no obvious scroll jank or row overlap. | 0.75 | react-performance-optimizer | sonnet | adaptive |

#### AC P4.1: Token rail is source-aware
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
    - lib/tokenMetrics.ts
    - types.ts
- propagation_contract: Token coverage resolver feeds frontend rail and detail labels.
- resilience: Missing token data leaves row layout stable and shows coverage notice only at session/rail summary level.
- visual_evidence_required: screenshot of token rail tooltip and coverage footer.
- verified_by: P4-T1, P4-T3, P4-T4

### Phase P5: Validation, Docs, and Rollout

**Goal**: Harden and document the feature before enabling by default.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| P5-T1 | Backend tests | Add parser/query/service tests for title, effort, markers, registers, and token coverage. | Targeted backend tests pass. | 0.5 | python-backend-engineer | sonnet | adaptive |
| P5-T2 | Frontend tests | Add Vitest coverage for title fallback, minimap marker rendering, task grouping, effort badge, and token rail caveats. | `npm run test` passes for related tests. | 0.5 | frontend-developer | sonnet | adaptive |
| P5-T3 | Runtime smoke | Run dev stack and browser smoke on the live sample route or a local fixture equivalent. | Smoke evidence includes screenshots for list, minimap, task/workflow pane, token rail. | 0.5 | ui-engineer-enhanced | sonnet | adaptive |
| P5-T4 | Docs and changelog | Add CHANGELOG entry and concise operator note for source coverage/feature flag. | Changelog and docs mention feature flag and token source caveats. | 0.25 | documentation-writer | haiku | adaptive |
| P5-T5 | Completion review | Run reviewer against PRD ACs and implementation plan. | `task-completion-validator` passes or required fixes are resolved. | 0.25 | task-completion-validator | sonnet | adaptive |

## Deferred Items and In-Flight Findings Policy

| Item | Reason | Promotion Trigger | Planned Handling |
|------|--------|-------------------|------------------|
| Persisted transcript marker table | Adds dual SQLite/Postgres migration and backfill before event shapes stabilize. | Query-time derivation is too slow on real long sessions after caching/perf pass. | Create follow-up infrastructure plan. |
| Full workflow output-file parsing | Output files may contain raw agent content and arbitrary structure. | A safe metadata schema is confirmed. | Link files in V1; parse metadata only if explicitly safe. |
| Full Agent Teams topology | Source shape not yet confirmed in local fixtures. | One or more real fixtures with team metadata are available. | Add fixture-backed resolver task. |
| Cross-platform parity | Codex and Claude Code event models differ. | Claude Code V1 succeeds and Codex parity data is inventoried. | Add separate parity contract. |

## Validation Plan

1. `npm run test` for frontend unit coverage.
2. `npm run typecheck` for shared `types.ts` changes.
3. Targeted backend tests for session parser/detail services, likely `backend/.venv/bin/python -m pytest backend/tests/ -k "session" -v`.
4. Runtime smoke per `CLAUDE.md`: start dev stack, open `/sessions?session=S-18d3c99f-0c34-4f5d-8a40-82ab21977e89&tab=transcript` when live data is available or a local fixture equivalent when not.
5. Browser screenshots for list title, header effort, minimap, task pane, workflow pane, and token rail.

## Execution Notes

1. Keep `components/SessionInspector.tsx` and `TranscriptView.tsx` edits scoped. Prefer extracting focused components instead of growing the main files.
2. New optional backend fields require explicit frontend fallback states.
3. Do not display advanced effort as an error state by default.
4. Do not assign per-tool token totals unless usage attribution provides event-level support.
5. Raw transcript rows remain accessible after grouping.
6. Feature flag should default off until runtime smoke passes.
