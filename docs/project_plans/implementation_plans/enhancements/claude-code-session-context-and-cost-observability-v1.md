---
doc_type: implementation_plan
status: draft
category: enhancements
title: "Implementation Plan: Claude Code Session Context And Cost Observability V1"
description: "Persist live context metrics, add cost provenance and calibration, and expose clearer token and cost semantics across CCDash session forensics and analytics."
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-03-11
updated: 2026-03-11
tags: [implementation, claude-code, sessions, context, cost, pricing, analytics, frontend, backend]
feature_slug: claude-code-session-context-and-cost-observability-v1
feature_family: claude-code-session-context-and-cost-observability
lineage_family: claude-code-session-context-and-cost-observability
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [claude-code-session-context-and-cost-observability-v1]
related:
  - docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md
  - docs/project_plans/reports/session-token-context-gap-and-ccusage-review-2026-03-11.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
  - backend/parsers/platforms/claude_code/parser.py
  - backend/models.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/repositories/sessions.py
  - backend/db/repositories/postgres/sessions.py
  - backend/db/sync_engine.py
  - backend/routers/api.py
  - backend/routers/analytics.py
  - components/SessionInspector.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/ProjectBoard.tsx
  - components/Dashboard.tsx
  - components/Analytics/AnalyticsDashboard.tsx
  - lib/tokenMetrics.ts
plan_ref: claude-code-session-context-and-cost-observability-v1
linked_sessions: []
request_log_id: ""
commits: []
prs: []
owner: platform-engineering
owners: [platform-engineering, data-platform, fullstack-engineering]
contributors: [ai-agents]
complexity: High
track: Standard
timeline_estimate: "2-4 weeks across 6 phases"
---

# Implementation Plan: Claude Code Session Context And Cost Observability V1

## Objective

Close the remaining Claude Code token and cost clarity gaps by:

1. persisting live context-window metrics separately from workload totals
2. adding a Settings-backed pricing catalog with per-platform defaults and per-model overrides
3. adding explicit cost provenance and recalculation support
4. adding pricing calibration and mismatch visibility
5. updating UI surfaces to distinguish context, workload, and cost semantics
6. optionally adding billing-block and burn-rate insights without changing canonical totals

## Scope and Fixed Decisions

1. `observedTokens` remains the canonical cumulative workload total.
2. `Current Context` is a separate metric and must never be merged into session workload totals.
3. Existing `totalCost` remains available for compatibility, but new fields define how that value was obtained.
4. Pricing configuration must be user-editable from Settings at both platform and model granularity.
5. Automatic provider-price sync is best-effort and must not override manual prices without clear precedence rules.
6. Dynamic pricing lookup is preferred over the current rough parser-only estimate.
7. Billing-block and burn-rate insights are additive and may ship behind a feature flag.
8. All major product surfaces must consume the same normalized semantics for context, workload, and cost provenance.
9. The new fields must be persisted in query-friendly structures so feature-, dashboard-, and analytics-level correlation does not depend on reparsing raw session artifacts.

## Non-Goals

1. Replacing the existing session-usage attribution model.
2. Reworking non-Claude session context semantics in the same iteration.
3. Building a full pricing-management subsystem for arbitrary providers beyond configured platforms and core token families.
4. Treating recalculated cost as authoritative when the source pricing contract is incomplete.

## Recommended Data Contract

### Session-level context fields

Persist the following fields on `sessions` for Claude Code rows:

1. `current_context_tokens`
2. `context_window_size`
3. `context_utilization_pct`
4. `context_measurement_source`
5. `context_measured_at`

Recommended semantics:

1. `current_context_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from the latest valid assistant usage signal
2. source precedence:
   - hook `context_window`
   - transcript-derived latest assistant usage

### Session-level cost provenance fields

Persist or derive:

1. `reported_cost_usd`
2. `recalculated_cost_usd`
3. `display_cost_usd`
4. `cost_provenance`
5. `cost_confidence`
6. `cost_mismatch_pct`
7. `pricing_model_source`

### Pricing catalog fields

Persist a pricing catalog or equivalent settings-backed store with:

1. `platform_type`
2. `model_id`
3. `input_cost_per_million`
4. `output_cost_per_million`
5. `cache_creation_cost_per_million`
6. `cache_read_cost_per_million`
7. `speed_multiplier_fast`
8. `source_type`
9. `source_updated_at`
10. `override_locked`
11. `sync_status`
12. `sync_error`

Recommended semantics:

1. `reported_cost_usd` comes from provider/session data when available
2. `recalculated_cost_usd` comes from model/version-aware pricing lookup
3. `display_cost_usd` is chosen from reported, recalculated, or estimated sources per explicit rules
4. `cost_provenance` must be one of `reported`, `recalculated`, `estimated`, or `unknown`
5. model-level pricing overrides take precedence over platform defaults
6. user overrides take precedence over synced provider values unless explicitly cleared
7. provider-sync data must retain freshness and error metadata

### Correlation-readiness requirements

The persisted contract should support efficient joins and rollups across:

1. session
2. feature
3. artifact
4. model
5. platform
6. date or timeline windows
7. execution or dashboard summary scopes

## Phase 1: Persistence Contract and Type Updates

Tasks:

1. Add new session columns in `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`.
2. Extend `backend/models.py`, API serializers, and frontend types to expose context and cost-provenance fields.
3. Add persistence for pricing catalog entries and sync metadata, either through dedicated tables or a clearly modeled settings store.
4. Ensure the new fields are persisted in query-friendly locations rather than only opaque JSON blobs.
5. Update session repositories and settings-related repositories to round-trip the new fields cleanly in SQLite and PostgreSQL.

Assigned subagents:

1. `data-layer-expert`
2. `python-backend-engineer`

Acceptance criteria:

1. Both databases expose the same new fields.
2. Existing session APIs remain backward compatible.
3. New fields default safely when data is unavailable.
4. Pricing catalog entries can persist platform defaults, model overrides, and sync metadata.
5. The storage layout supports low-friction retrieval for Session, Feature, Dashboard, Workbench, and Analytics use cases.

## Phase 2: Context Signal Capture and Historical Enrichment

Tasks:

1. Add parser or sync-engine logic to capture hook-provided `context_window` data when present.
2. Add transcript fallback logic that scans backward to the latest assistant usage record and computes context occupancy without output tokens.
3. Persist measurement source and timestamp so context freshness is visible.
4. Add deterministic backfill or resync support for historical Claude sessions.

Assigned subagents:

1. `python-backend-engineer`
2. `backend-architect`

Acceptance criteria:

1. Context fields populate for sampled sessions with hook data.
2. Context fallback populates for sampled sessions without hook data when transcript usage is present.
3. Measurement source and timestamp are visible in session payloads.
4. Reprocessing is idempotent.

## Phase 3: Pricing Service, Settings, and Cost Provenance

Tasks:

1. Introduce a pricing service abstraction that can provide:
   - model context limits
   - model pricing
   - cache pricing where supported
   - speed-tier multipliers where supported
   - provider-sync adapters where available for configured platforms
2. Add Settings-backed pricing configuration flows for:
   - platform defaults
   - model overrides
   - manual edit and reset
   - sync trigger and sync status
3. Replace or supplement the parser’s rough `_estimate_cost` path with a recalculated cost flow based on the pricing service.
4. Compute `reported_cost_usd`, `recalculated_cost_usd`, `display_cost_usd`, `cost_provenance`, and `cost_confidence`.
5. Define explicit display rules:
   - use reported when present and trusted
   - otherwise use recalculated when pricing coverage is sufficient
   - otherwise use estimated or unknown fallback

Assigned subagents:

1. `backend-architect`
2. `python-backend-engineer`
3. `data-layer-expert`
4. `frontend-developer`

Acceptance criteria:

1. Claude session cost payloads expose provenance and confidence.
2. Recalculated cost can use dynamic pricing data for supported models.
3. Unsupported or partially supported pricing cases degrade safely and explicitly.
4. Settings can persist and edit pricing by platform and model.
5. Automatic sync can refresh configured platform pricing when a provider source is available.

## Phase 4: Calibration and Validation Tooling

Tasks:

1. Add a calibration path that compares reported versus recalculated cost.
2. Aggregate mismatch and confidence summaries by model, model version, and platform version.
3. Expose calibration summaries through analytics/debug APIs or internal reports.
4. Add regression fixtures for:
   - supported pricing
   - unsupported models
   - cache-aware pricing
   - speed-tier pricing
   - manual override precedence
   - synced-price fallback

Assigned subagents:

1. `python-backend-engineer`
2. `code-reviewer`

Acceptance criteria:

1. Mismatch percent and confidence are queryable.
2. Sample sessions can be audited without manual SQL inspection.
3. Test coverage exists for representative pricing cases.
4. Override and sync-precedence rules are covered by automated tests.

## Phase 5: Retrieval Contracts, API Expansion, and Cross-Surface Adoption

Tasks:

1. Expand backend contracts in `backend/routers/api.py` and `backend/routers/analytics.py` so the new fields are available to all relevant consumers without ad hoc recomputation.
2. Ensure feature- and execution-oriented payloads can retrieve the new fields through normalized joins rather than reparsing raw session blobs.
3. Update `components/Settings.tsx` to add a pricing configuration surface in Settings with:
   - platform selectors
   - model override rows
   - editable pricing inputs
   - sync action and status
   - freshness and error indicators
4. Update `components/SessionInspector.tsx` to show:
   - `Current Context`
   - `Observed Workload`
   - split cache input
   - cost provenance and confidence
5. Update `components/FeatureExecutionWorkbench.tsx` to use the normalized context/cost fields where feature-linked sessions are summarized.
6. Update `components/ProjectBoard.tsx` feature/session summary surfaces to adopt the same semantics.
7. Update `components/Dashboard.tsx` to keep top-level KPIs aligned with the same token/context/cost meanings.
8. Update `components/Analytics/AnalyticsDashboard.tsx` to support context and calibration-oriented views where practical.
9. Ensure shared helpers and types, including `lib/tokenMetrics.ts`, do not conflate context, workload, and spend.
10. Add concise explanatory labels so context occupancy is not mistaken for cumulative tokens.

Assigned subagents:

1. `ui-engineer-enhanced`
2. `frontend-developer`
3. `ui-designer`
4. `python-backend-engineer`

Acceptance criteria:

1. Settings supports editing and syncing pricing by platform and model.
2. Session Inspector presents context and workload as clearly distinct concepts.
3. Feature, Workbench, Dashboard, and Analytics surfaces consume the same canonical fields and labels.
4. Cost provenance is visible wherever Claude session cost is shown in detail.
5. Existing token and cost views continue to render safely with the new payload shape.

## Phase 6: Optional Billing-Block and Burn-Rate Insights

Tasks:

1. Add a session-block abstraction for longer Claude sessions with configurable block duration, defaulting to `5` hours.
2. Compute per-block token totals, cost totals, token burn rate, cost burn rate, and projected end-of-block totals.
3. Decide whether to ship this phase behind a feature flag if phases 1-5 consume the full iteration budget.
4. Expose block insights in Session Inspector or a dedicated analytics subview if the output is clear and non-confusing.

Assigned subagents:

1. `backend-architect`
2. `ui-engineer-enhanced`
3. `frontend-developer`

Acceptance criteria:

1. Block analytics do not alter canonical session totals.
2. Users can inspect burn-rate data for long sessions when the feature is enabled.
3. The block model is optional and does not gate core context/cost clarity improvements.

## Validation and Rollout

Validation tasks:

1. Add unit tests for context computation, pricing lookup, and provenance selection.
2. Add repository and API contract tests for the new fields and pricing settings endpoints.
3. Add sampled-session validation against known real sessions, including `S-883b7028-5748-49b3-a6f5-0bd478f643a7`.
4. Verify that sessions without context or pricing signals still render safely.
5. Verify that manual overrides persist across provider sync and app restarts.
6. Verify that Feature, Workbench, Dashboard, and Analytics views all resolve the same persisted fields without local reinterpretation.

Rollout guidance:

1. Ship core context and cost provenance first.
2. Keep calibration views available to maintainers early, even if broader UI exposure lands later.
3. Gate billing-block views if they threaten delivery of core semantics.

## Risks and Mitigations

1. Risk: dynamic pricing dependencies become network-coupled or brittle.
   - Mitigation: prefer cached or bundled pricing data with offline-safe fallback.
2. Risk: automatic provider refresh overwrites intentionally curated prices.
   - Mitigation: model explicit override precedence, lock behavior, and audit metadata for synced values.
3. Risk: transcript-derived context can be stale or absent.
   - Mitigation: always expose source and measurement timestamp.
4. Risk: users overtrust recalculated cost in unsupported-pricing cases.
   - Mitigation: show confidence and provenance explicitly.
5. Risk: optional burn-rate views distract from core correctness work.
   - Mitigation: treat phase 6 as strictly lower priority.

## Delivery Summary

Recommended implementation order:

1. schema and type contract
2. context capture and persistence
3. pricing catalog, sync, and cost provenance
4. calibration and validation
5. Settings and UI adoption
6. optional burn-rate insights

This keeps the iteration focused on semantic clarity first, with higher-order analytics added only after the new context and cost contracts are stable.
