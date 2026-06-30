---
schema_version: 2
doc_type: design_spec
title: "Session Transcript Orchestration Intelligence V1"
description: "Interaction design for inferred session names, transcript minimap navigation, task/workflow sidepanes, effort transitions, plan metadata, and token-usage rails."
status: draft
maturity: ready
created: 2026-06-30
updated: 2026-06-30
feature_slug: session-transcript-orchestration-intelligence-v1
problem_statement: "CCDash session transcripts expose rich raw events, but the session list and transcript view do not yet turn commands, tasks, workflows, effort changes, plan modes, and token burn into a navigable operating surface."
open_questions:
  - "OQ-DS-1: What exact event shape does Claude Code Agent Teams emit in JSONL when enabled, and how does it differ from normal Agent/Task tool calls?"
  - "OQ-DS-2: Should workflow output-file payloads be parsed during sync, or linked lazily from the transcript sidepane when available?"
  - "OQ-DS-3: What is the default minimap density for very long transcripts: every marker, sampled marker buckets, or role-only buckets with drill-in?"
  - "OQ-DS-4: Which legacy path-style session links should be normalized as part of the title/header work?"
explored_alternatives:
  - "Client-only minimap from loaded logs: faster to ship, but weak for paginated or very large transcripts."
  - "Separate persisted marker table: fastest reads, but adds migration/backfill cost before the source event contract is fully stable."
  - "Derived query service index: preferred V1 path; no new table, stable API contract, server-side caching allowed."
related_documents:
  - docs/project_plans/reports/plan-2-ccdash-observability-integration-analysis-2026-03-21.md
  - docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md
  - docs/project_plans/feature_contracts/enhancements/per-message-token-usage.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
  - docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-transcript-append-deltas-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md
---

# Session Transcript Orchestration Intelligence V1

## Design Intent

Turn the transcript view from a chronological log reader into an operating surface for agentic work. The transcript remains readable first, but the surrounding UI should answer:

1. what this session was mainly about,
2. where the major commands, agents, tasks, workflows, commits, and effort changes happened,
3. what state the task/workflow register is in,
4. how much token burn each turn or subagent contributed,
5. how the session relates to implementation plans, tiers, modes, and external task systems.

The experience should feel dense and operational, not decorative.

## Route and First-Viewport Layout

The `/sessions` page keeps the current list/detail split. Selected transcript links remain query-param based: `/sessions?session=<id>&tab=transcript`. V1 should normalize touched stale path-style links, but it should not add a new `/sessions/:id` route.

Session cards promote a derived title:

```text
+ Session card ---------------------------------------------------+
| /plan:plan-feature cc-focus-pane-tabs-followups                 |
| S-18d3c99f-0c34-4f5d-8a40-82ab21977e89                         |
| Claude Opus 4.8  |  Ultracode -> High  |  Planning  |  $203.81 |
| Workflow x1  Agent x5  Tasks 5/5  60.6M observed tokens         |
+----------------------------------------------------------------+
```

Rules:

1. Title source order: first meaningful user command with args and feature slug, first Skill invocation plus slug, first Workflow title plus slug, first artifact/plan target, fallback existing title, fallback session id.
2. Ignore `/clear`, local command caveats, pure continuation summaries, and empty commands.
3. Keep the raw session id as small secondary text.
4. Do not overwrite stored user labels. Add an inferred-title field plus source/confidence metadata.

## Transcript Detail Layout

```text
+ Header ---------------------------------------------------------+
| /plan:plan-feature cc-focus-pane-tabs-followups                 |
| Claude Opus 4.8 | Ultracode -> High | Planning | 60.6M tok      |
+-----------+---------------------------------------+-------------+
| token rail | transcript message stream            | sidepane    |
|            |                                       | tabs        |
| cumulative | [effort changed: ultracode]           | Minimap     |
| burn bars  | user command                          | Tasks       |
|            | agent / tool / workflow rows          | Workflows   |
|            | [workflow completed]                  | Plan        |
|            | assistant response                    | Tokens      |
+-----------+---------------------------------------+-------------+
```

`components/SessionInspector/TranscriptView.tsx` already owns a dense three-pane transcript experience with task/agent parsing and per-message token captions. V1 should add focused minimap/register/token components and shared derived-index types rather than replacing the existing detail shell.

### Left Token Rail

The rail is a narrow visual scale aligned to transcript rows:

1. each assistant row with `tokenUsage` contributes a segment,
2. cache read, cache creation, model input, and model output use distinct but quiet colors,
3. hover reveals row tokens plus cumulative tokens through that point,
4. rows without usage data reserve no misleading value,
5. the footer shows cumulative known tokens and the known-data coverage percentage.

If event-level attribution exists, agent and tool rows can show attributed token totals. If only per-message usage exists, tool-call rows display "turn-level only" instead of assigning false precision.

### Right Minimap View

Default minimap mode:

```text
Minimap
[role] [time] [label]
| blue  19:35 /plan:plan-feature
| red   19:39 /effort ultracode
| amber 19:45 Workflow started
| green 20:51 Workflow completed
| gray  20:53 TaskUpdate x1
| teal  22:24 Commit b1561d0
| red   14:39 /effort high
```

Interactions:

1. click marker to scroll to row and select it,
2. keyboard arrows move marker focus and transcript focus together,
3. current viewport is shown as a line or pill,
4. mode switcher changes marker projection without changing transcript state.

Minimap modes:

1. **Outline**: user commands, effort changes, workflow starts/completions, commits, major agent completions.
2. **Roles**: user, agent, system, tool, command, workflow, task.
3. **Tasks**: TaskCreate/TaskUpdate state changes grouped by task id.
4. **Workflow**: workflow run, stages, agent team members, task notifications, output file links.
5. **Branches**: root, subagent, fork, continuation, and related child threads.
6. **Tokens**: largest token deltas and cumulative threshold crossings.

### Task Sidepane

Task view is a state register, not another log list:

```text
Tasks
5 tasks detected
[done] DI-199   Plan CC Focus pane summaries
       Created 19:39, updated 23:11, linked plan, IntentTree node
[blocked] DI-200 Review contradiction in plan
```

TaskCreate/TaskUpdate rows remain in the transcript, but adjacent clusters collapse into one expandable line:

```text
Task register updated: created 3, updated 2
```

Expanded state reveals each raw command and links back to the sidepane task row.

### Workflow Sidepane

Workflow view captures both explicit Workflow tool calls and dynamic/autonomous workflows triggered by effort mode:

```text
Workflow
Author + adversarially verify 4 tiered planning artifacts
Status: completed with one stalled track
Effort: ultracode / xhigh
Agents: 10
Tracks:
  DI-198 stalled at implementation-planner
  DI-199 passed review
  DI-200 flagged contradiction
  DI-201 passed review
Artifacts:
  output file, decisions blocks, PRDs, plans
```

V1 should link workflow threads by the best available evidence:

1. workflow tool-call id,
2. system completion notification,
3. task notification output-file,
4. linked agent/session ids,
5. root session id and timestamp window,
6. workflow file name when a `.claude/workflows/*.js` orchestrator is invoked.

### Plan Metadata View

When a session command or task references a plan or feature slug, the transcript sidepane should show:

1. tier,
2. execution model,
3. modes such as Mode C, Mode D, Mode E,
4. phase/wave/task ids,
5. linked plan/PRD/human brief,
6. IntentTree node links when present.

This is a sidepane summary with transcript callouts at the rows where the plan/task metadata became relevant.

## Color Semantics

Use restrained semantic colors:

1. user command: blue,
2. agent/subagent: violet,
3. workflow: amber,
4. task: cyan,
5. commit: green,
6. effort change: red or magenta when advanced effort is active,
7. token hotspot: orange,
8. system/continuation: gray.

Avoid making advanced effort look like an alert unless it is also a risk or context-pressure event.

## Live Sample Fixture

Use `S-18d3c99f-0c34-4f5d-8a40-82ab21977e89` as a fixture during implementation:

1. summary title today is `Feature Planning`;
2. first major command is `/plan:plan-feature`;
3. `/effort ultracode` appears at 2026-06-27T19:39:20.807Z;
4. dynamic Workflow starts around 2026-06-27T19:45:12.631Z;
5. system completion appears at 2026-06-27T20:51:29.006Z;
6. `/effort high` appears at 2026-06-28T14:39:56.919Z;
7. `toolSummary` includes `Agent x5`, `TaskCreate x5`, and `TaskUpdate x5`;
8. session summary currently reports `effortTier: null`, despite the transcript containing effort changes.
9. current transcript code already extracts Task/Agent tool details and per-message token captions, so fixture validation should compare the new derived index to existing rendered details rather than duplicate parsing in the UI.

## Acceptance Shape

The design is ready when a user can open that fixture and, without reading linearly, jump to:

1. the first meaningful planning command,
2. the ultracode effort transition,
3. the workflow run and completion,
4. the task-register updates,
5. the high-effort transition,
6. the largest token-burn messages,
7. the plan/task metadata associated with DI-199.
