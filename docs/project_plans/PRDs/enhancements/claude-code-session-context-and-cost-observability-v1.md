---
doc_type: prd
status: completed
category: enhancements
title: 'PRD: Claude Code Session Context And Cost Observability V1'
description: Add first-class live context metrics, cost provenance, pricing calibration,
  and higher-order workload insights so CCDash can distinguish prompt-window pressure
  from accumulated workload and explain cost confidence.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
- platform-engineering
created: 2026-03-11
updated: '2026-03-12'
tags:
- prd
- claude-code
- sessions
- context
- tokens
- cost
- analytics
- forensics
- pricing
feature_slug: claude-code-session-context-and-cost-observability-v1
feature_family: claude-code-session-context-and-cost-observability
lineage_family: claude-code-session-context-and-cost-observability
lineage_parent: ''
lineage_children: []
lineage_type: iteration
linked_features:
- claude-code-session-context-and-cost-observability-v1
related:
- docs/project_plans/reports/session-token-context-gap-and-ccusage-review-2026-03-11.md
- docs/project_plans/reports/claude-code-session-schema-and-token-audit-2026-03-08.md
- docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
- docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
- docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
- docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md
- backend/parsers/platforms/claude_code/parser.py
- backend/routers/api.py
- backend/routers/analytics.py
- backend/services/session_usage_analytics.py
- components/SessionInspector.tsx
- components/FeatureExecutionWorkbench.tsx
- components/ProjectBoard.tsx
- components/Dashboard.tsx
- components/Analytics/AnalyticsDashboard.tsx
- lib/tokenMetrics.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/claude-code-session-context-and-cost-observability-v1.md
request_log_id: ''
commits:
- 6e63f3a
- 09bce8b
prs: []
owner: platform-engineering
owners:
- platform-engineering
- data-platform
- fullstack-engineering
contributors:
- ai-agents
complexity: High
track: Standard
timeline_estimate: 2-4 weeks across 6 phases
---

# PRD: Claude Code Session Context And Cost Observability V1

## Executive Summary

CCDash now captures cache-aware session workload and event-level attribution, but it still cannot answer several user-facing questions cleanly:

1. how full was the live Claude context window at a given point in the session
2. whether displayed cost is reported, recalculated, or only estimated
3. whether a cost estimate is trustworthy for a given model/version/session
4. how token and cost burn evolved inside a long-running session block

This enhancement adds a separate context-observability layer on top of the existing workload model. It introduces first-class live context occupancy metrics, cost provenance and calibration fields, and optional billing-block or burn-rate views for longer Claude Code sessions.

The core decision is to keep three concepts distinct:

1. `Current Context` = prompt-window occupancy at the latest known point in the session
2. `Observed Workload` = cumulative model IO plus cache input families already persisted by CCDash
3. `Cost` = explicitly labeled as reported, recalculated, or estimated, with confidence/calibration metadata

The pricing model for recalculated cost must also become user-configurable from Settings, with per-platform defaults, per-model overrides, and automatic sync from real provider pricing sources when those sources are available and configured.

## Context and Current State

The March 11, 2026 report confirmed that CCDash already persists:

1. `modelIOTokens`
2. `cacheCreationInputTokens`
3. `cacheReadInputTokens`
4. `cacheInputTokens`
5. `observedTokens`
6. tool-result usage families
7. event-level attribution overlays

The same report also confirmed that CCDash does not currently persist or surface:

1. live `/context`-equivalent token counts
2. model context-window size
3. context-window utilization percentage
4. cost provenance semantics
5. pricing mismatch or calibration confidence
6. billing-block or burn-rate insights

This creates an avoidable user-facing mismatch. A live `/context` note such as `91k` tokens and a Forensics `Workload` value of `4,044,790` are both valid, but they represent different metrics. Today CCDash does not make that distinction explicit enough.

The report also reviewed `ccusage` and identified several reusable logic families:

1. hook- and transcript-based context occupancy capture
2. model context-limit lookup
3. reported-vs-calculated cost modes
4. pricing mismatch audits
5. session block and burn-rate modeling

## Problem Statement

CCDash can explain cumulative workload, but it cannot yet explain live prompt pressure or cost confidence with the same precision.

Current user-visible problems:

1. users can mistake `Workload` for current context occupancy
2. cost is shown as a single number without provenance
3. high-cache sessions can appear cheap or expensive without enough explanation of why
4. maintainers lack a built-in way to validate estimated costs against reported values
5. long sessions lack burn-rate or billing-block views that help interpret spend over time

User stories:

> As an engineer reviewing a session, I need to see current context occupancy separately from cumulative workload so I can tell whether the model was approaching prompt-window limits.

> As an engineering lead, I need to know whether a displayed cost is reported, recalculated, or estimated so I can trust comparisons across sessions and models.

> As a platform maintainer, I need calibration and mismatch tooling so I can detect model-pricing drift and avoid silently inaccurate cost analytics.

Technical root causes:

1. existing session payloads do not persist a context-window contract
2. current parser cost estimation relies on rough hardcoded model-IO rates
3. cost provenance is not represented in the session/API model
4. no pricing-validation workflow exists inside CCDash
5. there is no Settings-backed pricing catalog or override model for platforms and models
6. no higher-order session-block abstraction exists for burn-rate or projected-usage views

## Goals

1. Add a first-class context metric to Claude Code session forensics that is separate from `observedTokens`.
2. Add cost provenance fields so CCDash can distinguish reported, recalculated, and estimated cost.
3. Add pricing-calibration signals so maintainers can measure mismatch rates and confidence.
4. Add user-configurable pricing settings with per-platform and per-model values plus auto-sync where supported.
5. Expose clearer token/cost semantics across all major product surfaces, including Session Inspector, feature-facing views, Execution Workbench, Dashboard, Analytics, and Settings.
6. Add optional billing-block and burn-rate insights for long sessions without corrupting core session totals.
7. Store the new data in normalized, easily retrievable forms that support correlation by session, feature, artifact, model, platform, and timeline without reparsing raw transcript files at request time.

## Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Context observability coverage | No persisted `/context`-equivalent metric | Latest Claude context occupancy is available for validated sessions when hook payloads or transcript usage data exist | Session API contract tests + sampled session verification |
| Context/workload semantic clarity | Users can confuse workload with context | Session Inspector exposes separate context and workload cards with distinct labels and explanations | UI review and integration checks |
| Cost provenance coverage | One undifferentiated `totalCost` value | Session/API surfaces expose provenance for most Claude sessions as reported, recalculated, or estimated | API contract tests |
| Pricing settings coverage | No configurable pricing catalog in Settings | Users can view synced prices and override pricing per platform and model from Settings | Settings UX checks + persistence tests |
| Pricing validation visibility | No built-in mismatch analysis | Calibration summaries expose mismatch rates by model/version and confidence bands | Calibration tests and debug report |
| Cost-model correctness | Rough parser-only estimate | Recalculated cost path uses dynamic pricing data, cache-aware families where supported, and model/version-aware fallbacks | Pricing unit tests and sampled corpus comparisons |

## Users and Jobs-to-be-Done

1. Engineers: "Show me whether the model was under context pressure or just accumulated a lot of workload."
2. Engineering leads: "Show me cost with provenance so I can compare sessions without overtrusting estimates."
3. Platform engineers: "Give me a mismatch audit so I can detect pricing regressions or unsupported models."
4. Power users: "Let me override provider prices when needed without patching code or waiting for a deploy."
5. Power users: "Show me how fast tokens and cost were burning during a long active session."

## Functional Requirements

### 1) Context Observability Contract

CCDash must add a distinct session-level context contract for Claude Code sessions:

1. `currentContextTokens`
2. `contextWindowSize`
3. `contextUtilizationPct`
4. `contextMeasurementSource`
5. `contextMeasuredAt`

Allowed sources:

1. Claude hook `context_window` payload when available
2. transcript fallback using the latest assistant message with usage

Context semantics:

1. context occupancy must include `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`
2. output tokens must not count toward current context occupancy
3. context utilization percent must be clamped to `0-100`

### 2) Cost Provenance Contract

CCDash must add explicit cost provenance fields:

1. `reportedCostUsd`
2. `recalculatedCostUsd`
3. `displayCostUsd`
4. `costProvenance`
5. `costConfidence`
6. `costMismatchPct`
7. `pricingModelSource`

Supported provenance values:

1. `reported`
2. `recalculated`
3. `estimated`
4. `unknown`

### 3) Recalculated Cost Semantics

For Claude Code sessions, recalculated cost must:

1. prefer model/version-aware pricing tables over hardcoded parser estimates
2. support model input and output pricing at minimum
3. incorporate cache creation and cache read pricing when supported by the selected pricing source
4. apply speed-tier multipliers when the underlying pricing contract supports them
5. degrade safely to `estimated` when full pricing data is unavailable

### 4) Calibration and Validation

CCDash must provide a maintainable way to validate pricing behavior:

1. compare `reportedCostUsd` and `recalculatedCostUsd`
2. compute mismatch percent
3. aggregate mismatch rates by model, version, and platform version
4. expose calibration summaries in backend APIs or internal debug/reporting surfaces
5. surface low-confidence or unsupported-pricing cases explicitly

### 5) Pricing Settings and Override Management

CCDash must provide a Settings experience for pricing configuration.

Required capabilities:

1. view pricing by platform and model
2. persist platform-level default pricing
3. persist model-level overrides that take precedence over platform defaults
4. support pricing fields for:
   - input tokens
   - output tokens
   - cache creation tokens where supported
   - cache read tokens where supported
   - optional speed-tier multipliers where supported
5. show the source of each value:
   - provider-synced
   - user override
   - built-in fallback
6. show freshness metadata such as last sync time
7. allow users to trigger refresh from real provider pricing sources when available
8. allow users to lock or preserve manual overrides so automatic refresh does not overwrite them unintentionally

Pricing-synchronization behavior:

1. CCDash should attempt to pull real pricing data for configured platforms when the platform supports an accessible pricing source or API contract.
2. Automatic sync must be best-effort and must not block cost rendering when provider sync is unavailable.
3. When no provider sync is available, the app must fall back to stored overrides or bundled defaults.

### 6) Session and Analytics UI

Session Inspector must:

1. show `Current Context` separately from `Observed Workload`
2. show context tokens, context-window size, and utilization percent
3. show cost provenance and confidence
4. split cache input into creation and read where useful
5. avoid implying that cumulative workload equals current prompt occupancy

Analytics surfaces should support:

1. context utilization summaries where meaningful
2. cost provenance or calibration filters
3. model-level cost mismatch reporting
4. optional token/cost burn-rate views for long sessions

Feature-facing and workload surfaces must also adopt the new semantics:

1. feature-linked session summaries must expose context and cost-provenance data where relevant
2. `FeatureExecutionWorkbench` must be able to aggregate and display:
   - observed workload
   - current/latest context where meaningful
   - display cost with provenance
   - cache contribution
3. `ProjectBoard` and related feature/session summary cards must stop implying that one total-token value explains both workload and context pressure
4. `Dashboard` overview cards and any top-level KPIs must use the same canonical semantics as Analytics and Session views
5. all shared helpers and frontend types must remain consistent so the same fields can be rendered across Session, Feature, Workbench, Dashboard, and Analytics surfaces without local reinterpretation

Settings UI must:

1. expose a dedicated pricing configuration surface or clear subsection
2. let users filter and edit pricing by platform and model
3. clearly distinguish synced versus overridden values
4. expose sync status, errors, and last successful refresh time

### 7) Billing-Block and Burn-Rate Insights

CCDash should support a higher-order session-block abstraction for long Claude Code sessions:

1. configurable default block duration, initially `5` hours
2. active block cost
3. active block token totals
4. token burn rate
5. cost burn rate
6. projected end-of-block totals

This feature may ship behind a feature flag if core context and cost provenance work lands first.

### 8) Backfill and Resync

Historical Claude sessions should be enrichable through deterministic resync/backfill logic so the new context and cost fields are populated where source data exists.

### 9) Retrieval and Correlation Contract

The new data must be stored and exposed in ways that are easy to retrieve and correlate.

Requirements:

1. hot-path session totals and latest context/cost-provenance fields must be queryable directly from stable session storage
2. pricing catalog data must be queryable by platform and model without scanning opaque blobs
3. analytics and feature rollups must be able to join session context/cost fields with:
   - feature links
   - artifact links
   - model facets
   - platform facets
   - timeline or date windows
4. request-time logic must not require reparsing transcript files or deeply nested raw JSON for common UI views
5. correlation APIs must preserve enough structure to compare:
   - context utilization by model/platform
   - cost mismatch by model/platform/version
   - workload versus cost by feature or execution surface
   - burn-rate patterns across long-running sessions

## Non-Functional Requirements

1. Backward compatibility: existing `totalCost` consumers must not break during the transition.
2. Explainability: UI labels must distinguish context, workload, and cost provenance clearly.
3. Cross-database parity: SQLite and PostgreSQL session contracts must remain aligned.
4. Performance: context and cost metadata should be queryable without reparsing raw transcript files at request time.
5. Extensibility: the model should remain compatible with future multi-platform cost and context semantics.
6. Offline safety: provider-price sync failures must not break settings or cost display.
7. Correlation-readiness: the storage contract must support low-friction joins across sessions, features, artifacts, models, platforms, and analytics time windows.

## Out of Scope

1. redefining `observedTokens`
2. merging context occupancy into cumulative workload totals
3. replacing the existing attribution model
4. building a full standalone pricing administration product beyond configured platforms and core token families

## Dependencies and Assumptions

1. V1 session usage alignment remains the foundation for workload totals.
2. V2 attribution remains additive and does not need to be redesigned for this feature.
3. Claude hook `context_window` payloads are not guaranteed for every session, so transcript fallback is required.
4. A reusable pricing source can be integrated or embedded without forcing online-only behavior.
5. Some providers may not expose a machine-readable pricing endpoint, so bundled defaults and user overrides must remain first-class.

## Risks and Mitigations

1. Risk: users may still conflate context and workload if labels are weak.
   - Mitigation: use separate UI cards with short explanatory copy and stable field names.
2. Risk: pricing data may be incomplete for some models or versions.
   - Mitigation: keep provenance and confidence explicit, and fall back safely.
3. Risk: automatic provider refresh could overwrite intentionally customized prices.
   - Mitigation: add explicit override precedence and sync-protection behavior in Settings.
4. Risk: transcript-derived context may be stale relative to latest session activity.
   - Mitigation: persist measurement timestamp and source so staleness is visible.
5. Risk: burn-rate features add complexity before core semantics are stable.
   - Mitigation: gate billing-block views behind a later phase or feature flag.

## Target State

After this enhancement:

1. Session Inspector shows both live context occupancy and cumulative workload.
2. Cost is labeled as reported, recalculated, or estimated.
3. Calibration views can identify pricing mismatches and unsupported models.
4. High-cache sessions can be interpreted without guessing whether the problem was prompt pressure, replay volume, or pricing ambiguity.
5. Long sessions can expose higher-order usage patterns such as burn rate and projected block totals.

## Acceptance Criteria

1. Session APIs expose context and cost-provenance fields for Claude sessions without breaking existing consumers.
2. Session Inspector displays `Current Context` separately from `Observed Workload`.
3. Settings exposes per-platform pricing defaults and per-model overrides with sync metadata.
4. Recalculated cost uses dynamic pricing lookup when possible and falls back safely when not.
5. Calibration outputs can quantify mismatch between reported and recalculated cost.
6. Feature, Workbench, Dashboard, and Analytics surfaces adopt the same token/context/cost semantics instead of inventing local variants.
7. Historical sessions can be enriched through deterministic resync or backfill.
8. Optional burn-rate or billing-block views do not alter canonical session totals.

## Implementation Phases

1. context signal ingestion and persistence
2. pricing catalog, sync, and cost provenance model
3. calibration and mismatch reporting
4. normalized retrieval/correlation contracts, API expansion, and all-surface UI adoption
5. historical enrichment and validation
6. optional billing-block and burn-rate insights
