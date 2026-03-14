---
doc_type: prd
status: draft
category: enhancements

title: "PRD: Claude Code Session Thread Scope Rollups V1"
description: "Add explicit direct-thread versus thread-family token and cost semantics across Session Inspector, linked-session lists, transcript drilldowns, and analytics so CCDash can show main-thread metrics without hiding cumulative subthread spend."
author: codex
audience: [ai-agents, developers, engineering-leads, platform-engineering]
created: 2026-03-12
updated: 2026-03-12

tags: [prd, claude-code, sessions, subthreads, tokens, cost, analytics, transcript]
feature_slug: claude-code-session-thread-scope-rollups-v1
feature_family: claude-code-session-thread-scope-rollups
lineage_family: claude-code-session-thread-scope-rollups
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [claude-code-session-thread-scope-rollups-v1]
related:
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/implementation_plans/enhancements/session-fork-lineage-tracking-v1.md
  - backend/models.py
  - backend/routers/api.py
  - backend/routers/analytics.py
  - backend/services/session_usage_attribution.py
  - components/SessionInspector.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/ProjectBoard.tsx
  - components/Analytics/AnalyticsDashboard.tsx
  - lib/tokenMetrics.ts
  - types.ts
implementation_plan_ref: ""

request_log_id: ""
commits: []
prs: []
owner: platform-engineering
owners: [platform-engineering, data-platform, fullstack-engineering]
contributors: [ai-agents]

complexity: High
track: Standard
timeline_estimate: "2-3 weeks across 5 phases"
---

# PRD: Claude Code Session Thread Scope Rollups V1

## Executive Summary

CCDash already distinguishes current context from cumulative workload and now preserves enough session and event-level usage data to reason about linked subthreads. The remaining gap is presentation and aggregation scope: the product does not yet define when token and cost metrics should represent only the selected session versus the selected session plus its linked subthreads.

V1 introduces an explicit two-scope contract:

1. `directThread` = only the currently viewed session
2. `threadFamily` = the current session plus all linked descendant threads materialized beneath it

The Session Transcript and core session context remain direct-thread views by default. Session detail, linked-session lists, and analytics surfaces must additionally expose thread-family rollups for tokens and cost, while keeping context utilization strictly single-session. The same scope semantics must remain queryable for agent- and analytics-level correlation so future analysis does not have to guess whether a number is thread-local or cumulative.

## Context and Current State

Recent CCDash work established three important foundations:

1. `observedTokens` is now distinct from legacy `tokensIn + tokensOut`
2. `currentContextTokens` and `contextUtilizationPct` are persisted as session-local observability signals
3. attribution data can correlate usage to agents, subthreads, skills, artifacts, and commands

Current product behavior is still inconsistent across surfaces:

1. Session detail views mainly present the selected session row, even when linked subthreads exist.
2. Session list cards and feature-linked session views do not consistently distinguish direct-thread totals from subtree totals.
3. Context percentage is a session-local metric but sits near aggregate token and cost metrics, which invites scope confusion.
4. Transcript and analytics token views are partially disconnected: analytics can already derive cumulative per-log token deltas, but transcript presentation does not surface that information at the message origin point.
5. Analytics and correlation views can aggregate token or cost values, but they do not yet expose a first-class scope dimension for `direct thread` versus `thread family`.

The result is that the same session tree can be interpreted differently depending on where a user looks:

1. Session Inspector transcript implies "this session only"
2. linked session cards often imply "this row only"
3. high-level analysis often wants "this root session plus all descendant work"

That ambiguity becomes more costly now that CCDash tracks subthread sessions, session lineage, context occupancy, and attribution metrics in the same product.

## Problem Statement

CCDash has the underlying session and token data needed to explain subthread spend, but it lacks a consistent scope contract for showing it.

Current user-visible problems:

1. A main session with multiple subagent threads can look cheap or small if only the direct thread is shown.
2. A list of sessions can understate total spend if descendant thread totals are hidden, or overstate context if aggregate metrics are mixed with single-session context.
3. Users cannot easily answer "how much did this exact transcript consume so far" while reading a session chronologically.
4. Agent and analytics rollups cannot cleanly compare direct session ownership with descendant thread contribution because the API/UI contract does not label scope explicitly.

User stories:

> As an engineer reviewing a main session, I need the transcript and context to stay focused on that session while also seeing the cumulative token and cost impact of all descendant subthreads.

> As an engineering lead scanning session lists or linked feature sessions, I need the displayed tokens and cost to reflect the full session subtree, with a quick breakdown by thread.

> As a power user debugging a long transcript, I need optional line-by-line token counts and cumulative usage so I can see where context pressure ramped up.

> As an analyst, I need session, agent, and analytics views to expose the same scope semantics so I can correlate cost and token usage without double counting or mixing direct and family totals.

Technical root causes:

1. Session APIs do not expose a first-class `metricScope` contract for direct versus descendant-inclusive rollups.
2. UI surfaces independently choose whether they read direct session totals, linked session summaries, or attribution-derived aggregates.
3. Per-log usage data exists in log metadata and analytics derivations, but transcript rendering does not present it as a user-facing toggle.
4. Existing aggregation helpers optimize for session totals, not for "session row plus descendant thread tree" summaries with per-thread breakdowns.

## Goals

1. Define and expose a canonical two-scope metric model for session tokens and cost: `directThread` and `threadFamily`.
2. Keep transcript content and context metrics session-local unless a user explicitly asks for rollup detail.
3. Make session lists and feature-linked session lists show thread-family token and cost totals by default, with a per-thread breakdown affordance.
4. Add transcript token drilldowns that let users inspect per-message token delta and cumulative usage progression.
5. Make thread-scope metrics reusable across analytics, agent summaries, and future correlation workflows without ambiguous semantics.

## Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Scope clarity in session detail | Session detail mixes direct-thread semantics with hidden descendant cost | Session detail clearly labels direct-thread and thread-family token/cost values while keeping context session-local | UI review plus integration checks |
| Session list completeness | Session cards can understate subtree spend | Session list and linked-session cards display thread-family total tokens and cost for rows with descendants | Session/feature UI regression tests |
| Context-scope correctness | Context can be misread as aggregate | Context percentage remains single-session on all surfaces and is never rolled up as family context | Contract tests plus UI review |
| Transcript token visibility | Token progression requires inference from analytics only | Transcript page offers optional per-message token delta/cumulative badges and expandable breakdowns for supported logs | Frontend interaction tests |
| Analytics scope parity | Analytics aggregates do not label scope consistently | Relevant analytics payloads expose direct-thread and thread-family rollups or a scope filter where appropriate | API contract tests |
| Correlation readiness | Per-agent or per-feature analysis must infer thread scope indirectly | Thread-scope metrics are queryable by session, agent, feature, artifact, and lineage relationships | Backend integration tests |

## Users and Jobs-to-be-Done

1. Engineers: "Show me the session I opened, but do not hide what its subagents cost."
2. Engineering leads: "Let me compare full session trees in lists and analytics without losing per-thread breakdowns."
3. Power users: "Let me trace token growth through the transcript and inspect the exact token families for a given message."
4. Platform engineers: "Give me a reusable scope contract so downstream analytics stop making their own assumptions."

## Functional Requirements

### 1) Canonical Thread Scope Contract

CCDash must introduce a stable scope contract for session usage metrics.

Required scopes:

1. `directThread`
   - the selected session row only
2. `threadFamily`
   - the selected session plus all descendant linked sessions reachable through session-thread lineage

Required metric families under both scopes where meaningful:

1. `tokenInput`
2. `tokenOutput`
3. `modelIOTokens`
4. `cacheCreationInputTokens`
5. `cacheReadInputTokens`
6. `cacheInputTokens`
7. `observedTokens`
8. `toolReportedTokens` or fallback totals where allowed
9. `displayCostUsd`
10. provenance summaries where available

Scope rules:

1. `currentContextTokens`, `contextWindowSize`, and `contextUtilizationPct` remain direct-thread only.
2. Thread-family scope must never synthesize a fake aggregate context percentage.
3. Scope labels must be explicit in API payloads and UI copy.
4. Thread-family totals must follow existing lineage rules and avoid double counting shared or inherited history.

### 2) Session Detail Semantics

When viewing a main session or any selected session in Session Inspector:

1. The transcript body must continue to show only the selected session's transcript entries.
2. The session context panel must show only the selected session's current context and context percentage.
3. Token and cost summaries must show:
   - direct-thread totals for the selected session
   - thread-family totals for the selected session plus descendants
4. If no descendants exist, thread-family totals may collapse to the same value but should still follow the same contract internally.
5. Family totals must include a per-thread breakdown view listing at minimum:
   - session or thread label
   - relationship type
   - observed tokens
   - display cost
   - share of family total

### 3) Session List and Linked-Session Card Semantics

For Session Forensics list rows, feature-linked session rows, and other comparable session list surfaces:

1. Displayed tokens and cost must default to thread-family totals.
2. A hover, popover, or equivalent compact affordance must show per-thread breakdown for that row's subtree.
3. Context percentage and current context tokens shown on cards must remain specific to the single row session only.
4. Surfaces must visually distinguish:
   - session-local context
   - subtree token/cost totals
5. Sorting and filtering that use token or cost values must specify whether they operate on direct-thread or thread-family totals. Default list sorting should favor the displayed thread-family totals on list surfaces that show them.

### 4) Transcript Token Drilldown

The Session Transcript page should offer an optional token drilldown mode.

Requirements:

1. A user-controlled toggle enables line-by-line token visibility.
2. In drilldown mode, user-originating transcript bubbles should display a small token badge that shows cumulative token usage so far for the direct thread when data exists.
3. The badge may display raw context tokens when that is the strongest available signal, but the label must make clear whether the number is:
   - cumulative observed tokens
   - current context tokens
   - another bounded fallback
4. Expanding a message or tool call should expose a dedicated token section when usage data exists, including:
   - input tokens
   - output tokens
   - cache creation input tokens
   - cache read input tokens
   - observed token delta
   - cumulative direct-thread observed tokens after that event
   - event-level cost or provenance metadata when available
   - attribution or linked-thread note when relevant
5. Missing token data must degrade gracefully rather than showing invented values.

### 5) Analytics and Correlation Surfaces

Relevant analytics surfaces must expose the same scope semantics.

At minimum:

1. Session analytics payloads must return direct-thread and thread-family usage/cost summaries.
2. Analytics Dashboard views that summarize sessions must support either:
   - separate direct-thread and thread-family fields, or
   - an explicit scope filter that defaults consistently per card
3. Agent-facing analytics should be able to show:
   - direct-thread averages for sessions owned by that agent
   - thread-family averages when descendant work is intentionally included
4. Feature and artifact correlations must be able to join on thread-family totals without reparsing raw transcripts.
5. Existing attribution views remain valid, but they must not silently substitute attributed totals where thread-family totals are intended.

### 6) Data and API Contract

Backend contracts must expose enough structure for all relevant surfaces.

Required additions or guarantees:

1. Session detail DTOs expose both direct-thread and thread-family usage summaries.
2. Session list DTOs expose the displayed thread-family totals plus compact thread breakdown metadata.
3. Thread breakdown rows preserve stable identifiers so tooltips, drilldowns, and analytics links can open a contributing thread directly.
4. Rollup payloads preserve relationship metadata such as:
   - child session id
   - relationship type
   - thread kind
   - agent or subagent name when available
5. Correlation payloads must retain join keys for:
   - session id
   - root session id or conversation family id
   - feature links
   - attribution entity ids
   - source log ids when drilldown evidence is needed

### 7) Historical Compatibility and Backfill

1. Existing sessions without descendant threads must continue to render correctly with minimal payload overhead.
2. Historical sessions with linked subthreads should populate thread-family rollups from persisted session rows and lineage data, not from per-request transcript reparsing.
3. Transcript token drilldown should rely on existing log metadata, usage summaries, or event rows where present; unsupported historical sessions may show limited detail with clear fallback behavior.

## Non-Functional Requirements

1. Performance: session list surfaces must not require loading full descendant transcripts just to render family totals or tooltip breakdowns.
2. Correctness: thread-family totals must not double count shared ancestor history, relay mirrors, or fallback tool totals already superseded by linked subthread sessions.
3. Explainability: every surfaced total must make its scope obvious in copy or affordance.
4. Compatibility: direct session APIs and legacy consumers should continue to function while new scoped fields are added.
5. Extensibility: the scope contract should remain compatible with fork lineage, attribution rollups, and future platform-specific thread types.

## Out of Scope

1. Merging descendant transcript content into the parent transcript view.
2. Replacing attribution logic with thread-family ownership logic.
3. Creating a single aggregate context percentage across multiple threads.
4. Redesigning all analytics cards in one pass beyond the surfaces that expose session, feature, or agent usage metrics.
5. Retroactively fabricating per-message token detail for logs that do not preserve usable usage data.

## Dependencies and Assumptions

1. The V1 usage-alignment contract remains the source of truth for direct-thread token families.
2. Context observability fields remain session-local and should not be repurposed as lineage-wide metrics.
3. Session lineage or relationship data is available for descendant thread traversal.
4. Existing attribution and usage-event work remains additive and can be joined to scoped session rollups where deeper analysis is needed.
5. Frontend surfaces already consuming session/thread data can be extended without introducing a new transcript storage model.

## Risks and Mitigations

1. Risk: Users confuse direct-thread and thread-family totals if both are shown without strong labels.
   - Mitigation: standardize labels, tooltips, and layout positions across surfaces.
2. Risk: Family rollups double count fallback tool totals when a linked session exists.
   - Mitigation: reuse the existing fallback-only rules from session usage alignment and cover subtree aggregation with tests.
3. Risk: Transcript drilldown implies precision that historical logs do not support.
   - Mitigation: gate badges and expanded sections on actual usage availability and expose provenance/fallback labels.
4. Risk: Analytics surfaces drift from Session Inspector semantics.
   - Mitigation: define scoped DTOs centrally and reuse the same helpers across session, feature, and analytics endpoints.
5. Risk: Forks and subagents require slightly different rollup semantics.
   - Mitigation: build the scope contract on lineage relationships and relationship types rather than hardcoding subagent-only assumptions.

## Proposed Implementation Phases

### Phase 1: Scoped Session Contract

1. Add direct-thread and thread-family usage summary structures to backend and frontend session types.
2. Centralize lineage traversal and descendant rollup helpers.
3. Define shared labels and scope semantics for session, feature, and analytics surfaces.

### Phase 2: Session and Linked-List UI Updates

1. Update Session Inspector summary panels to show both scopes while keeping context direct-thread only.
2. Update Session Forensics cards and linked-session cards to display thread-family tokens/cost with per-thread breakdown affordances.
3. Ensure sorting/filtering uses the correct displayed totals.

### Phase 3: Transcript Token Drilldown

1. Reuse existing per-log token delta derivations where available.
2. Add transcript-level toggle, badge presentation, and expandable token breakdown sections.
3. Preserve graceful fallback behavior for unsupported logs.

### Phase 4: Analytics and Agent Correlation

1. Extend relevant analytics/session endpoints with scoped usage summaries.
2. Expose scope-aware agent, feature, and artifact rollups where session usage is presented.
3. Keep attribution and family-rollup semantics separate but joinable.

### Phase 5: Validation and Backfill Hardening

1. Validate sampled session trees with known subthreads.
2. Add regression coverage for direct-thread versus family totals, tooltip breakdowns, and transcript badge behavior.
3. Confirm that historical sessions degrade safely when transcript-level detail is incomplete.

## Acceptance Criteria

1. Opening a session with linked descendant threads shows only the selected transcript and selected-session context, while token and cost panels expose both direct-thread and thread-family values.
2. Session Forensics cards and feature-linked session rows display thread-family totals with a per-thread breakdown affordance.
3. Context utilization is never rendered as a cumulative family metric.
4. Transcript token drilldown can show cumulative direct-thread usage next to supported originating messages and reveal event token breakdowns on expansion.
5. Relevant analytics and agent rollups can use the same scoped session metrics without ad hoc recalculation.
