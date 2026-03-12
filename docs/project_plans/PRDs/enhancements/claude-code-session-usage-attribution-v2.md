---
doc_type: prd
status: completed
category: enhancements

title: "PRD: Claude Code Session Usage Attribution V2"
description: "Add event-level token attribution and correlation so CCDash can explain workload by skill, agent, subthread, command, artifact, and feature rather than only by session."
author: codex
audience: [ai-agents, developers, engineering-leads, platform-engineering]
created: 2026-03-09
updated: 2026-03-10

tags: [prd, claude-code, tokens, attribution, analytics, skills, agents, subthreads, artifacts]
feature_slug: claude-code-session-usage-attribution-v2
feature_family: claude-code-session-usage-analytics-alignment
lineage_family: claude-code-session-usage-analytics-alignment
lineage_parent: claude-code-session-usage-analytics-alignment-v1
lineage_children: []
lineage_type: iteration
linked_features: [claude-code-session-usage-attribution-v2]
related:
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/reports/claude-code-session-schema-and-token-audit-2026-03-08.md
  - docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
  - docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
  - backend/routers/analytics.py
  - backend/services/workflow_effectiveness.py
  - components/Analytics/AnalyticsDashboard.tsx
  - components/execution/WorkflowEffectivenessSurface.tsx
  - backend/parsers/platforms/claude_code/parser.py
  - backend/db/sync_engine.py
  - types.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md

request_log_id: ""
commits:
  - 0e40a00
  - 6045ab3
  - 3c41590
  - 5e32c03
  - 0e778e1
prs: []
owner: platform-engineering
owners: [platform-engineering, fullstack-engineering, ai-integrations]
contributors: [ai-agents]

complexity: High
track: Attribution
timeline_estimate: "3-5 weeks across 7 phases"
---

# PRD: Claude Code Session Usage Attribution V2

## Executive Summary

V1 corrects Claude Code session totals and preserves enough event-level usage data to stop undercounting workload. V2 builds on that foundation by answering the next layer of questions: which skills, agents, subthreads, commands, and artifacts actually consumed tokens, how much of that consumption was direct versus inferred, and which patterns correlate with efficient or wasteful execution.

The core architectural decision is to separate:

1. immutable token events
2. derived attribution edges
3. aggregate analytics views

This avoids corrupting session totals with heuristic attribution logic while still enabling detailed correlation views such as:

1. tokens attributed to a specific skill across all sessions
2. model IO and observed workload by subagent or subthread
3. token efficiency for workflow stacks, commands, or artifact bundles
4. feature-level comparisons by agent/skill mix

## Context and Current State

After V1, CCDash will have:

1. correct session-level `observedTokens`
2. cache-aware token breakdowns
3. safer tool-token fallback rules
4. preserved event-level token deltas and join keys for future attribution

Even with that work complete, current analytics still stop at relatively coarse scopes:

1. session totals
2. model and tool breakdowns
3. artifact counts and some token/cost aggregates by artifact type/model
4. workflow effectiveness views driven primarily by session-level outcomes

What the app still cannot answer well is:

1. how many tokens were directly associated with a specific skill
2. whether a subagent consumed high token volume but produced weak delivery outcomes
3. which commands or artifact combinations create high cache share or low yield
4. how token burn distributes across the lifecycle of a multi-agent session

## Problem Statement

Today CCDash can say that a session used many tokens, or that a session involved certain skills or agents, but it cannot defensibly say which portion of that token usage should be attributed to those entities.

That blocks several high-value questions:

1. "Which skills are expensive but worthwhile?"
2. "Which subagents consume large token budgets without enough delivery impact?"
3. "Which workflow stacks minimize token burn per completed task?"
4. "Which features are consistently implemented with low-yield agent or skill mixes?"

User stories:

> As an engineer tuning my workflow, I need to see which skills and agents actually drove token usage so I can keep the useful ones and drop the wasteful ones.

> As an engineering lead, I need token and cost views by skill, agent, subthread, and feature so I can compare execution strategies on real project outcomes.

> As a workflow author, I need attribution confidence and method transparency so I can trust the analysis instead of treating it as black-box guesswork.

Technical root causes:

1. Session totals are available, but attribution is not modeled as a first-class layer.
2. Current analytics payloads aggregate by session, model, tool, and artifact type more readily than by event-linked skill or agent usage.
3. Skills and agents are often inferable from logs, artifacts, or linked sessions, but there is no canonical weighting/confidence contract for attaching token deltas to them.
4. Using naive before/after windows without immutable event storage and attribution edges would make double counting and overlap errors likely.

## Goals

1. Introduce a canonical event-level usage attribution model that supports skills, agents, subthreads, commands, artifacts, workflows, and features.
2. Keep session-level workload correctness separate from attribution heuristics.
3. Support both exclusive and assistive views of token attribution without double counting session totals.
4. Make attribution methods and confidence visible in APIs and UI.
5. Feed richer token efficiency signals into workflow effectiveness and future recommendation systems.

## Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Primary attribution coverage | No formal attribution model | High-confidence primary attribution exists for most attributable Claude token events in validation corpus | Attribution calibration report |
| Session-to-attribution reconciliation | Not possible today | Exclusive attributed model-IO totals reconcile closely with session model-IO totals on validated sessions | Event/rollup consistency checks |
| Entity query coverage | Session/model/tool-focused analytics only | APIs can query token usage by skill, agent, subthread, command, artifact, and feature | API contract tests |
| Attribution transparency | No method/confidence exposure | Every attributed token aggregate exposes attribution method mix and confidence summary | API/UI checks |
| Product adoption | No dedicated attribution surfaces | Dashboard or analytics users can inspect top costly/high-yield skills and agents in-product | UX validation |

## Users and Jobs-to-be-Done

1. Engineers: "Show me which skills, commands, and agents actually drove this session's token burn."
2. Engineering leads: "Compare token efficiency across subagents, skills, and feature execution patterns."
3. Workflow authors: "Calibrate stacks using evidence-backed token attribution and outcomes."
4. Platform engineers: "Add new attribution rules without rewriting core session semantics."

## Functional Requirements

### 1) Canonical Attribution Model

CCDash must separate:

1. immutable usage events
2. attribution links from events to entities
3. aggregate rollups for analytics/UI

Attribution-capable entity scopes must include, at minimum:

1. skill
2. agent
3. subthread or linked subagent session
4. command
5. artifact
6. feature
7. workflow or stack when resolvable

### 2) Attribution Semantics

1. Each usage event may have one primary attribution and zero or more supporting attributions.
2. Attribution links must include `method`, `confidence`, and `weight`.
3. The system must support both:
   - exclusive views that reconcile to session totals
   - supporting views that show participation without pretending exclusivity
4. Overlapping attributions must not silently inflate exclusive totals.

### 3) Token Families

Attribution must work across the same token families introduced in V1, while preserving their semantic differences:

1. model IO tokens
2. cache creation tokens
3. cache read tokens
4. observed workload tokens
5. tool-reported tokens when used in a bounded fallback context

### 4) Query and Analytics Surface

The system must support:

1. per-entity totals by skill, agent, subthread, command, artifact, and feature
2. filters by model, model family, date range, feature, session type, and platform version
3. correlation views such as:
   - tokens per completed task
   - cache share by skill or agent
   - attributed model cost by workflow component
   - subagent yield versus attributed tokens
4. drill-down from aggregate rows to contributing sessions and source log events

### 5) UI Surfaces

1. Analytics Dashboard must expose token attribution views by skill, agent, artifact, command, and feature.
2. Workflow Effectiveness surfaces must be able to incorporate attributed token and cost metrics.
3. Session Inspector must be able to show event-level attribution overlays or drill-downs for a selected session.
4. Feature views should support attributed workload summaries for linked sessions/subthreads when correlation confidence is sufficient.

### 6) Cost Semantics

1. Attributed cost must remain clearly labeled as model-IO-derived cost unless a broader pricing model is introduced.
2. Cache-attributed workload must not be mislabeled as directly billable cost.
3. UI and API contracts must preserve the distinction between workload attribution and price attribution.

### 7) Attribution Transparency and Validation

1. Every attributed aggregate must expose attribution confidence or quality summaries.
2. The product must provide a way to inspect which rules contributed to an attribution.
3. Calibration workflows must support comparing attributed totals against known-good sample sessions.

## Non-Functional Requirements

1. Attribution logic must be explainable and auditable.
2. Event storage and queries must remain performant on large session corpora.
3. The attribution layer must be additive; it must not destabilize V1 session totals.
4. The model must remain cross-database compatible.
5. The contract must remain extensible to future platforms beyond Claude Code.

## Out of Scope

1. Exact causal inference for every token event.
2. Fully automated stack recommendations in the same release.
3. Retroactively changing raw parser semantics for pre-V1 sessions beyond required backfill/enrichment.
4. Solving every workflow-effectiveness or recommendation problem in the same phase.

## Dependencies and Assumptions

1. V1 usage alignment work has already shipped or is available as the data foundation.
2. Event-level token deltas and join keys are preserved well enough for derived attribution.
3. Existing skill, agent, artifact, and workflow definitions remain queryable through current CCDash and SkillMeat-linked structures.
4. Attribution can begin with confidence-based heuristics before more explicit instrumentation exists.

## Risks and Mitigations

1. Risk: Overlapping heuristics double count events.
   - Mitigation: separate primary versus supporting attributions and enforce exclusive reconciliation checks.
2. Risk: Low-confidence inference creates misleading product claims.
   - Mitigation: expose method/confidence and allow filtering to high-confidence views.
3. Risk: Query cost grows too quickly.
   - Mitigation: materialize derived attribution rollups instead of recomputing everything from raw logs on every request.
4. Risk: Users conflate attributed workload with attributed cost.
   - Mitigation: keep cost semantics explicit and model-IO-bound.

## Acceptance Criteria

1. CCDash persists or derives immutable usage events and separate attribution edges.
2. APIs can return attributed token metrics by skill, agent, subthread, command, artifact, and feature.
3. Exclusive attribution views reconcile to session model-IO totals within defined tolerance on validation corpora.
4. Analytics UI exposes attribution views with confidence/method transparency.
5. Workflow effectiveness and related strategy surfaces can consume attributed token metrics.
6. Cost remains clearly labeled as model-IO-derived even when workload attribution includes cache or supporting views.
