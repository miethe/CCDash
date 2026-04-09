---
doc_type: implementation_plan
status: completed
category: enhancements
title: 'Implementation Plan: Claude Code Session Usage Analytics Alignment V1'
description: Persist stable Claude usage totals, backfill historical sessions, align
  analytics semantics around observed tokens, and expose cache-aware token breakdowns
  in the UI.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
created: 2026-03-09
updated: '2026-04-07'
commit_refs:
- https://github.com/miethe/CCDash/commit/2d6fe0f
- https://github.com/miethe/CCDash/commit/3aedf0d
- https://github.com/miethe/CCDash/commit/09c9e30
- https://github.com/miethe/CCDash/commit/c4b166c
- https://github.com/miethe/CCDash/commit/df595f7
- https://github.com/miethe/CCDash/commit/0415d52
pr_refs: []
tags:
- implementation
- claude-code
- sessions
- tokens
- analytics
- cache
- frontend
- backend
feature_slug: claude-code-session-usage-analytics-alignment-v1
feature_family: claude-code-session-usage-analytics-alignment
lineage_family: claude-code-session-usage-analytics-alignment
lineage_parent: ''
lineage_children: []
lineage_type: iteration
linked_features:
- claude-code-session-usage-analytics-alignment-v1
related:
- docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
- docs/project_plans/reports/claude-code-session-schema-and-token-audit-2026-03-08.md
- docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
- backend/parsers/platforms/claude_code/parser.py
- backend/models.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/repositories/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/db/sync_engine.py
- backend/routers/analytics.py
- backend/routers/api.py
- backend/services/workflow_effectiveness.py
- components/Dashboard.tsx
- components/ProjectBoard.tsx
- components/SessionInspector.tsx
- components/FeatureExecutionWorkbench.tsx
- components/Analytics/AnalyticsDashboard.tsx
- types.ts
plan_ref: claude-code-session-usage-analytics-alignment-v1
linked_sessions: []
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

# Implementation Plan: Claude Code Session Usage Analytics Alignment V1

## Objective

Turn the March 8, 2026 Claude Code schema/token audit into production behavior by:

1. persisting stable usage totals for Claude sessions
2. backfilling historical session rows
3. redefining analytics defaults around `observedTokens`
4. updating UI surfaces to show cache-aware token composition
5. codifying a safe relay-attribution and tool-token fallback policy

## Scope and Fixed Decisions

1. `tokensIn` and `tokensOut` remain the backward-compatible model-IO fields.
2. The default "total tokens" semantic becomes `observedTokens`, not `tokensIn + tokensOut`.
3. Stable hot-path usage totals are persisted as first-class session fields in both SQLite and PostgreSQL; detailed usage families remain available in `session_forensics_json`.
4. Tool-reported totals are operational fallback signals, not additive totals when linked subagent sessions exist.
5. Relay-wrapped `data.message.message.*` records remain excluded from observed totals until the attribution rule is explicitly implemented and tested.
6. V1 is limited to Claude Code session semantics even if the contract later expands to other platforms.
7. Cost remains model-IO-derived in V1; observed workload tokens do not automatically imply higher estimated dollar cost.

## Non-Goals

1. Recomputing cost models from cache-read or cache-creation token families.
2. Building a new generic telemetry store for all session platforms.
3. Full UI redesign of session or analytics pages beyond token-semantics updates.
4. Counting relay-wrapped message mirrors in V1 without a safe deduplication model.

## Recommended Data Contract

Persist the following stable fields on `sessions`:

1. `model_io_tokens`
2. `cache_creation_input_tokens`
3. `cache_read_input_tokens`
4. `cache_input_tokens`
5. `observed_tokens`
6. `tool_reported_tokens`
7. `tool_result_input_tokens`
8. `tool_result_output_tokens`
9. `tool_result_cache_creation_input_tokens`
10. `tool_result_cache_read_input_tokens`

Derived API-facing ratios:

1. `cacheShare = cacheInputTokens / observedTokens`
2. `outputShare = tokensOut / modelIOTokens`

Rationale:

1. These metrics are stable enough to query directly.
2. They match the report's recommended token model.
3. They prevent request-time reparsing of nested `sessionForensics`.

## V2-Ready Attribution Guardrails

V1 should preserve enough event-level detail to support later token attribution by skill, agent, command, or subthread without changing parser semantics again.

Required guardrails:

1. Preserve per-log usage deltas in normalized log metadata for every Claude message/tool record that exposes them, including cache families where available.
2. Keep stable join keys across the stack:
   - `session_id`
   - `source_log_id`
   - timestamp
   - agent/subthread identity
   - command/tool context
   - skill/artifact refs when resolvable
3. Treat later attribution as a separate derived layer, not as destructive mutation of session totals.
4. When V2 arrives, write attribution rows with:
   - `artifact_type`
   - `artifact_id`
   - `token_family`
   - `delta_tokens`
   - `attribution_method`
   - `confidence`

This keeps V1 focused on correctness while leaving room for:

1. session totals for sessions that used a given skill
2. subthread totals for a specific agent
3. delta-based token attribution around skill or artifact usage windows
4. correlation views across model, skill, agent, command, feature, and cost

## Phase 1: Persistence Contract and Schema Parity

Tasks:

1. Add the new Claude usage columns to `sessions` migrations in both `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`.
2. Extend `backend/models.py`, `types.ts`, and API serialization contracts to expose the persisted usage fields and derived ratios.
3. Update `backend/db/repositories/sessions.py` and `backend/db/repositories/postgres/sessions.py` to write/read the new fields.
4. Keep `session_forensics_json` as the source for detailed usage families while making the stable totals queryable.
5. Confirm normalized log metadata retains per-event token deltas and contextual join keys needed for later attribution work.

Acceptance criteria:

1. SQLite and PostgreSQL schemas stay aligned.
2. Session rows can round-trip the new usage fields without breaking current readers.
3. Existing `tokensIn` and `tokensOut` fields remain intact.
4. Per-log usage metadata remains available for future attribution derivation.

## Phase 2: Sync Engine Mapping and Historical Backfill

Tasks:

1. Update sync/session upsert logic in `backend/db/sync_engine.py` to map parser-emitted `sessionForensics.usageSummary` into the new session columns.
2. Define one canonical source for each persisted field:
   - `model_io_tokens` from message input/output totals
   - `cache_*` from message usage totals
   - `tool_reported_tokens` from `toolResultReportedTotals.totalTokens`
   - tool-result usage totals from `toolResultUsageTotals`
3. Add a deterministic resync/backfill path for historical Claude sessions.
4. Preserve or enrich log-level metadata so message/tool rows still expose the event deltas later attribution will need.
5. Emit enough logging or summary output to verify how many sessions were updated during backfill.

Acceptance criteria:

1. Historical Claude session rows populate the new usage fields after resync.
2. Stored `observedTokens` matches parser-derived message totals on validation fixtures and sampled real sessions.
3. Backfill is safe to rerun without duplicate side effects.
4. Event-level metadata still supports reconstructing token deltas over time.

## Phase 3: Analytics, Feature Rollups, and Workflow Semantics

Tasks:

1. Update `backend/routers/analytics.py` so overview, series, breakdown, and correlation outputs expose:
   - `modelIOTokens`
   - `cacheInputTokens`
   - `observedTokens`
   - `toolReportedTokens`
2. Update `/overview` and any landing-dashboard KPI payloads so app-level summaries remain aligned with the new token semantics.
3. Replace legacy default `totalTokens` rollups with `observedTokens`, while preserving compatibility behavior for callers that still expect `totalTokens`.
4. Update feature/session aggregation logic in `backend/db/sync_engine.py` and `backend/services/workflow_effectiveness.py` to use the report's root/full-thread/fallback rules.
5. Ensure tool-reported totals are used only when linked subagent sessions are absent.
6. Keep cost metrics explicitly model-IO-derived and labeled that way in contracts where both tokens and cost appear.

Acceptance criteria:

1. Analytics APIs no longer undercount Claude session workload by ignoring cache totals.
2. Feature-level totals avoid double counting linked subagent sessions.
3. Workflow effectiveness and related rollups use the new semantics consistently.
4. Overview/dashboard payloads do not mix observed-token semantics with unlabeled model-IO cost semantics.

## Phase 4: Session, Feature, and Analytics UI Adoption

Tasks:

1. Update `components/SessionInspector.tsx` to show a token-family breakdown and label legacy `tokensIn`/`tokensOut` as model IO.
2. Update `components/FeatureExecutionWorkbench.tsx` to aggregate feature workload with `observedTokens` and expose cache contribution.
3. Update `components/ProjectBoard.tsx` token/cost surfaces so feature and commit views do not imply `tokenInput + tokenOutput` is the only meaningful total.
4. Update `components/Dashboard.tsx` so any token KPI added or reused from overview follows the same semantics and cost labels.
5. Update `components/Analytics/AnalyticsDashboard.tsx` to:
   - default "total tokens" cards/charts to `observedTokens`
   - add a cache-efficiency panel
   - surface ratios like cache share where useful
6. Update shared frontend types and formatting helpers so new metrics render consistently.

Acceptance criteria:

1. Users can distinguish model IO from cache-driven workload in the UI.
2. Existing charts and cards keep working with the expanded payload shape.
3. No major token surface still silently equates total tokens with `tokensIn + tokensOut`.
4. Token/cost pairings on dashboard and feature views clearly distinguish observed workload from estimated model cost.

## Phase 5: Relay Attribution Policy and Guardrails

Tasks:

1. Document the counting policy for `data.message.message.*` relay mirrors in the implementation and tests.
2. Add explicit guardrails in parser-to-persistence or aggregation logic so excluded relay mirrors cannot leak into `observedTokens`.
3. Define how relay data should be surfaced for diagnostics if it remains excluded from totals.
4. Add targeted tests that demonstrate:
   - excluded relay mirrors do not inflate totals
   - tool-reported totals do not double count linked subagent sessions

Acceptance criteria:

1. Relay counting behavior is explicit rather than accidental.
2. Double counting is prevented by code and regression tests.
3. Maintainers can see the policy in code/docs without re-reading the audit report.

## Phase 6: Validation, Rollout, and Documentation

Tasks:

1. Extend parser, repository, sync, and analytics tests to cover the new token model end to end.
2. Add API contract coverage for the expanded analytics/session payloads.
3. Add frontend validation for token cards, tables, and cache-efficiency rendering.
4. Document the metric semantics in developer-facing docs or inline implementation references so later work does not regress to legacy totals.
5. Run a real-corpus verification pass against the inventory sample and at least one known high-cache session from the report.
6. Capture follow-up notes for a V2 attribution plan once the event-level data contract is confirmed in real sessions.

Acceptance criteria:

1. Backend and frontend test coverage exists for the new token semantics.
2. Real-corpus spot checks reproduce the expected observed-token behavior.
3. The rollout path is documented enough for future backfills and maintenance work.

## Risks

1. The largest product risk is semantic confusion if legacy and new totals coexist without clear labels.
2. The largest technical risk is double counting across linked sessions, tool-reported totals, and relay mirrors.
3. The largest rollout risk is partially backfilled data causing mixed analytics semantics across projects.

## Recommended Rollout Order

1. Persistence contract and schema parity
2. Sync/backfill mapping
3. Analytics and feature rollups
4. UI adoption
5. Relay guardrails
6. Validation and documentation

## Completion Notes

Completed on 2026-03-09.

Phase 4 delivered:

1. Session, feature, dashboard, and analytics UI surfaces now default to observed workload semantics.
2. Feature-facing session summaries and cards expose cache contribution and keep model IO labeled separately from cost.
3. Session and analytics views now show token-family breakdowns instead of silently equating total tokens with `tokensIn + tokensOut`.

Phase 5 delivered:

1. Claude parser forensics now publish `usageSummary.relayMirrorTotals` for excluded `data.message.message.*` relay records.
2. Sync/persistence continues to derive `observedTokens` only from parser `messageTotals`, making the exclusion explicit in code.
3. Tool-reported totals remain fallback-only in shared aggregation logic when linked subthreads are present.

Phase 6 delivered:

1. Added regression coverage for relay exclusion, feature-linked token payloads, and tool-fallback aggregation rules.
2. Real-corpus spot check completed against local Claude session `785bd0e5-bf81-4150-8407-ff7a2e6c45c3`, where `_derive_claude_usage_fields` resolved `model_io_tokens=5,834`, `cache_input_tokens=1,128,322`, and `observed_tokens=1,134,089`.
3. Updated README, execution workbench user docs, and changelog to document observed workload, cache input, and model-IO semantics.
4. Validation completed with targeted backend pytest coverage and frontend Vitest coverage for the new token helper.
