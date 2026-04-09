---
doc_type: prd
status: completed
category: enhancements
title: 'PRD: Claude Code Session Usage Analytics Alignment V1'
description: Align CCDash session storage, analytics, and UI with the richer Claude
  Code usage schema so token reporting reflects real observed workload instead of
  model IO only.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
- platform-engineering
created: 2026-03-09
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/2d6fe0f
- https://github.com/miethe/CCDash/commit/3aedf0d
- https://github.com/miethe/CCDash/commit/09c9e30
- https://github.com/miethe/CCDash/commit/c4b166c
- https://github.com/miethe/CCDash/commit/df595f7
- https://github.com/miethe/CCDash/commit/0415d52
pr_refs: []
tags:
- prd
- claude-code
- sessions
- tokens
- analytics
- cache
- forensics
feature_slug: claude-code-session-usage-analytics-alignment-v1
feature_family: claude-code-session-usage-analytics-alignment
lineage_family: claude-code-session-usage-analytics-alignment
lineage_parent: ''
lineage_children: []
lineage_type: iteration
linked_features:
- claude-code-session-usage-analytics-alignment-v1
related:
- docs/project_plans/reports/claude-code-session-schema-and-token-audit-2026-03-08.md
- docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
- backend/parsers/platforms/claude_code/parser.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/repositories/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/db/sync_engine.py
- backend/routers/analytics.py
- backend/services/workflow_effectiveness.py
- backend/routers/api.py
- components/Dashboard.tsx
- components/ProjectBoard.tsx
- components/SessionInspector.tsx
- components/FeatureExecutionWorkbench.tsx
- components/Analytics/AnalyticsDashboard.tsx
- types.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
request_log_id: ''
commits:
- 2d6fe0f
- 3aedf0d
- 09c9e30
- c4b166c
- df595f7
- 0415d52
prs: []
owner: platform-engineering
owners:
- platform-engineering
- fullstack-engineering
contributors:
- ai-agents
complexity: High
track: Standard
timeline_estimate: 2-3 weeks across 6 phases
---
# PRD: Claude Code Session Usage Analytics Alignment V1

## Delivery Status

Status: completed on 2026-03-09.

Validated against the current tree:

1. `backend/db/repositories/sessions.py` and `backend/db/repositories/postgres/sessions.py` persist the richer Claude usage totals.
2. `backend/routers/analytics.py` and `backend/services/workflow_effectiveness.py` use observed-token semantics for rollups.
3. `components/Analytics/AnalyticsDashboard.tsx` and `components/SessionInspector.tsx` render the cache-aware workload breakdowns introduced by the rollout.

Relevant commits:

- [2d6fe0f](https://github.com/miethe/CCDash/commit/2d6fe0f) feat(sessions): persist claude usage contract fields
- [3aedf0d](https://github.com/miethe/CCDash/commit/3aedf0d) feat(sync): backfill persisted claude usage fields
- [09c9e30](https://github.com/miethe/CCDash/commit/09c9e30) feat(analytics): align observed token semantics
- [c4b166c](https://github.com/miethe/CCDash/commit/c4b166c) feat(ui): adopt observed workload token semantics
- [df595f7](https://github.com/miethe/CCDash/commit/df595f7) feat(parser): document relay token guardrails
- [0415d52](https://github.com/miethe/CCDash/commit/0415d52) docs(plan): record corpus token spot check

## Executive Summary

CCDash currently parses richer Claude Code usage data than it actually persists or visualizes. The March 8, 2026 audit showed that session totals and downstream analytics still default to `tokensIn + tokensOut`, even though Claude transcripts now include large cache-read, cache-creation, server-tool, and tool-result usage families that materially change the interpretation of session workload.

V1 aligns session storage, analytics contracts, and frontend surfaces around a multi-metric token model. The system should preserve backward-compatible model IO fields while introducing first-class `observedTokens`, cache totals, tool-reported fallback totals, and a clear attribution policy for relay-wrapped message records.

The result should be that CCDash answers two different questions correctly:

1. "How many model IO tokens did this session directly consume?"
2. "How much total token workload did this session actually observe, including cache replay?"

## Context and Current State

The March 8, 2026 report scanned 25 Claude Code session files, 2,494 entries, and 316 distinct nested paths with zero parse errors. That audit confirmed five important facts:

1. Claude Code usage payloads now include cache creation, cache read, server tool request counts, speed, service tier, and iteration metadata.
2. Tool results also carry their own usage payloads and reported totals.
3. Wrapped relay records under `data.message.message.*` appear frequently in the local corpus.
4. CCDash already parses much of this data into `sessionForensics.usageSummary`.
5. CCDash storage, analytics, and UI still mostly operate on `tokens_in + tokens_out`.

Today the parser already emits normalized usage summaries, but those metrics do not drive the main session records, feature rollups, or analytics dashboards. Current implementation paths named in the audit include:

1. `backend/db/repositories/sessions.py`
2. `backend/db/repositories/postgres/sessions.py`
3. `backend/db/sync_engine.py`
4. `backend/routers/analytics.py`
5. `backend/services/workflow_effectiveness.py`
6. `components/SessionInspector.tsx`
7. `components/FeatureExecutionWorkbench.tsx`
8. `components/Analytics/AnalyticsDashboard.tsx`

The most visible consequence is that CCDash can materially understate workload. In the audit's concrete example session, the app-reported total was about 20k tokens while the observed message total was about 7.5M tokens because cache-read volume was invisible to dashboards and rollups.

## Problem Statement

Users currently see a misleading "total tokens" story for Claude Code sessions.

1. Session detail views show only model IO totals, which understates real workload when cache replay dominates.
2. Feature and analytics views roll up legacy token fields, so cross-session comparisons do not reflect observed context pressure.
3. Tool-reported token totals exist but have no safe fallback policy when linked subagent sessions are absent.
4. Relay-wrapped `data.message.message.*` records appear in large volume, but CCDash has no explicit attribution rule for whether or how to count them.

User stories:

> As an engineer inspecting a Claude Code session, I need to distinguish model IO from cache-driven workload so I can understand whether a session was cheap prompting, heavy replay, or both.

> As an engineering lead reviewing feature rollups, I need a trustworthy default "total tokens" metric so comparisons across sessions and features are not systematically understated.

> As a platform maintainer, I need a stable token contract and relay-attribution policy so parser upgrades do not silently change analytics semantics.

Technical root causes:

1. The parser computes richer usage totals in `sessionForensics.usageSummary`, but `sessions` persistence still centers on `tokens_in` and `tokens_out`.
2. Analytics and workflow-effectiveness rollups sum `tokenInput + tokenOutput` or `tokens_in + tokens_out` rather than derived observed totals.
3. Frontend token displays assume a single overloaded total instead of separate token families.
4. Relay-wrapped message mirrors are detected but not governed by an explicit counting policy.

## Goals

1. Make Claude Code session totals trustworthy by introducing a first-class multi-metric usage model.
2. Preserve backward compatibility for existing `tokensIn` and `tokensOut` consumers while redefining the default "total tokens" experience around `observedTokens`.
3. Normalize cache, tool-reported, and server-tool usage into queryable backend contracts.
4. Expose token-family breakdowns in session, feature, and analytics UI so users can interpret workload composition.
5. Establish an explicit attribution policy for relay-wrapped `data.message.message.*` records before they influence totals.
6. Preserve enough event-level usage detail in normalized storage to support later skill-, agent-, and subthread-level token attribution without another parser redesign.

## Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Session observed token correctness | Legacy totals differ materially from parsed usage summary on sampled Claude sessions | `observedTokens` matches persisted parser-derived message totals for validated Claude sessions | Compare stored totals to `sessionForensics.usageSummary.messageTotals.allTokens` after resync |
| Analytics token-model coverage | Analytics endpoints mostly expose one `totalTokens` number | Overview, series, breakdown, and correlation payloads expose `modelIOTokens`, `cacheInputTokens`, `observedTokens`, and `toolReportedTokens` where relevant | API contract tests |
| Historical session coverage | Historical Claude sessions depend on `tokens_in + tokens_out` only | Existing local Claude session corpus is backfilled/resynced with the new usage fields | Resync/backfill validation |
| UI token transparency | Session and analytics UI emphasize one overloaded total | Session, feature, and analytics surfaces show distinct model IO, cache, and observed totals | Frontend integration checks |
| Relay attribution clarity | No explicit policy | Policy documented and encoded in backend logic/tests | Policy doc + regression tests |

## Users and Jobs-to-be-Done

1. Engineers: "Show me whether this session spent effort on fresh prompting, cache replay, or subtask work."
2. Engineering leads: "Give me feature and session rollups that reflect real workload, not understated legacy totals."
3. Platform engineers: "Keep token semantics stable as Claude Code schema variants evolve."

## Functional Requirements

### 1) Canonical Token Model

CCDash must distinguish, at minimum:

1. `modelIOTokens = input_tokens + output_tokens`
2. `cacheInputTokens = cache_creation_input_tokens + cache_read_input_tokens`
3. `observedTokens = modelIOTokens + cacheInputTokens`
4. `toolReportedTokens = toolUseResult.totalTokens` or normalized tool-result usage totals used only as fallback
5. `serverToolRequests` tracked separately from token totals

### 2) Session Persistence

1. Stable usage metrics must be persisted in queryable form for Claude Code sessions rather than remaining accessible only inside `sessionForensics`.
2. `tokensIn` and `tokensOut` must remain available for backward compatibility.
3. The persisted contract must support both SQLite and PostgreSQL.
4. Detailed raw or semi-structured usage payloads may remain in `sessionForensics`, but hot-path totals must be queryable without reparsing nested JSON blobs.

### 3) Session and Feature Aggregation

1. Session detail APIs must return model IO totals, cache totals, observed totals, tool-reported totals, and ratio fields where applicable.
2. Feature rollups must default to root/full-thread `observedTokens` semantics rather than legacy totals.
3. Tool-reported totals may be used only as fallback when a linked subagent session is missing.
4. The aggregation rules must avoid double counting when linked subagent sessions are present.

### 4) Analytics Contracts

1. Analytics endpoints must expose separate token families instead of only one overloaded total.
2. Default dashboard "total tokens" views must use `observedTokens`.
3. Ratios such as `cacheShare` and `outputShare` must be available for derived analysis.
4. Existing API consumers must not break; any legacy `totalTokens` field must either map to `observedTokens` or remain clearly documented during transition.

### 5) UI Surfaces

1. Session Inspector must show a token-family breakdown for Claude Code sessions.
2. Feature Execution Workbench must use `observedTokens` for high-level workload summaries and allow users to inspect cache contribution.
3. Feature-facing surfaces in `ProjectBoard` that summarize session-, commit-, or correlation-level token usage must stop assuming `tokenInput + tokenOutput` is the only meaningful total.
4. The landing dashboard overview contract must remain consistent with the analytics token model so any token KPIs added there do not regress to legacy semantics.
5. Analytics Dashboard must expose a cache-efficiency panel with:
   - model IO tokens
   - cache read tokens
   - cache creation tokens
   - cache share
6. Surfaces that previously rendered only `tokensIn + tokensOut` must be updated or explicitly labeled as model IO.

### 6) Cost Semantics

1. Cost must remain explicitly modeled as model-IO-derived cost unless and until CCDash introduces a validated pricing model for cache or tool-reported token families.
2. UI surfaces that pair tokens and cost must not imply that `observedTokens` directly maps to current `totalCost`.
3. Analytics and dashboard copy must distinguish "observed workload tokens" from "estimated model cost."

### 7) Relay Attribution Policy

1. `data.message.message.*` relay-wrapped records must not silently influence totals without a documented attribution rule.
2. V1 must codify whether these records are excluded, counted conditionally, or exposed as a separate family.
3. The policy must be testable and visible to maintainers.

### 8) Backfill and Resync

1. Historical Claude sessions must be resynced or backfilled so analytics stop depending on legacy totals only.
2. The backfill path must be deterministic and safe to rerun.
3. Backfill completion should be observable through logs or summary reporting.

### 9) V2 Attribution Readiness

1. V1 must preserve per-log or per-event usage deltas and the contextual keys needed for later attribution work, including session ID, source log ID, timestamp, model, agent/subthread context, and skill/artifact references when available.
2. The storage contract must support future attribution rows that can assign token deltas to skills, agents, commands, or artifact usage with a method/confidence value.
3. V1 must avoid baking in assumptions that only session-level totals matter.

## Non-Functional Requirements

1. Backward compatibility: existing consumers of `tokensIn` and `tokensOut` must continue to work.
2. Cross-database parity: SQLite and PostgreSQL storage contracts must remain aligned.
3. Performance: the new hot-path metrics must be queryable without reparsing large nested JSON at request time.
4. Correctness: token totals must not double count linked sessions or relay mirrors.
5. Explainability: UI labels must distinguish model IO, cache input, and observed totals clearly.
6. Extensibility: the normalized model must remain compatible with future token attribution by skill, agent, command, or subthread.

## Out of Scope

1. Repricing or recomputing dollar-cost estimates from cache totals.
2. Counting relay-wrapped records beyond the policy required to avoid silent ambiguity.
3. General telemetry platform redesign outside Claude Code session usage semantics.
4. Reworking non-Claude session token semantics in the same phase.
5. Shipping v2 artifact attribution views in the same phase as core session/analytics correction.

## Dependencies and Assumptions

1. `backend/parsers/platforms/claude_code/parser.py` remains the source of truth for normalized Claude usage extraction.
2. `sessionForensics.usageSummary` is sufficiently stable to seed the first persistence pass for core metrics.
3. Existing analytics tables and session sync flows remain the primary integration path.
4. There is no immediate need to reparse raw session files outside the existing sync/backfill flow.

## Risks and Mitigations

1. Risk: Double counting tool-reported totals and linked subagent sessions.
   - Mitigation: enforce explicit fallback-only rules and cover them with aggregation tests.
2. Risk: UI confusion if old and new totals are shown without explanation.
   - Mitigation: label model IO separately and reserve "total tokens" for observed totals.
3. Risk: Relay records introduce unstable semantics.
   - Mitigation: freeze counting behavior behind a documented policy before enabling them.
4. Risk: Schema drift in future Claude Code payloads.
   - Mitigation: keep the inventory script in the maintenance loop and add regression coverage for new usage families.
5. Risk: V1 session-only persistence leaves later skill/agent attribution too coarse.
   - Mitigation: preserve event-level usage deltas and contextual keys now, even if V2 is the first release to query them.

## Acceptance Criteria

1. CCDash persists first-class Claude usage totals beyond `tokensIn` and `tokensOut`.
2. Session APIs and frontend types expose model IO, cache, observed, and tool-reported totals.
3. Analytics dashboard defaults to `observedTokens` for total workload views.
4. Feature-level token summaries use the new aggregation policy and avoid double counting linked sessions.
5. Historical Claude sessions can be resynced/backfilled to populate the new fields.
6. Relay-wrapped `data.message.message.*` counting behavior is explicitly documented and covered by tests.
7. Session, workbench, and analytics UI surfaces show cache contribution instead of hiding it behind one overloaded total.
8. Dashboard and feature-facing token/cost surfaces either adopt the new semantics or explicitly label model-IO-only values.
9. V1 storage preserves enough event-level usage context to support later skill-, agent-, and subthread-level attribution work.
