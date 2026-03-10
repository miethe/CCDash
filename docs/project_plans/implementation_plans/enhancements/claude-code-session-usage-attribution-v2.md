---
doc_type: implementation_plan
status: in-progress
category: enhancements
title: 'Implementation Plan: Claude Code Session Usage Attribution V2'
description: Add immutable usage events, attribution links, and rollups so CCDash
  can analyze token usage by skill, agent, subthread, command, artifact, workflow,
  and feature.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
created: 2026-03-09
updated: '2026-03-10'
tags:
- implementation
- claude-code
- tokens
- attribution
- analytics
- skills
- agents
- workflows
feature_slug: claude-code-session-usage-attribution-v2
feature_family: claude-code-session-usage-analytics-alignment
lineage_family: claude-code-session-usage-analytics-alignment
lineage_parent: claude-code-session-usage-analytics-alignment-v1
lineage_children: []
lineage_type: iteration
linked_features:
- claude-code-session-usage-attribution-v2
related:
- docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
- docs/project_plans/PRDs/enhancements/claude-code-session-usage-analytics-alignment-v1.md
- docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-analytics-alignment-v1.md
- docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
- backend/routers/analytics.py
- backend/services/workflow_effectiveness.py
- backend/db/sync_engine.py
- backend/parsers/platforms/claude_code/parser.py
- components/Analytics/AnalyticsDashboard.tsx
- components/execution/WorkflowEffectivenessSurface.tsx
- components/SessionInspector.tsx
- types.ts
plan_ref: claude-code-session-usage-attribution-v2
linked_sessions: []
request_log_id: ''
commits: []
prs: []
owner: platform-engineering
owners:
- platform-engineering
- fullstack-engineering
- ai-integrations
contributors:
- ai-agents
complexity: High
track: Attribution
timeline_estimate: 3-5 weeks across 7 phases
---

# Implementation Plan: Claude Code Session Usage Attribution V2

## Objective

Build a derived attribution layer on top of V1 usage alignment so CCDash can answer:

1. which skills, agents, commands, artifacts, and subthreads consumed tokens
2. how confidently those tokens can be attributed
3. which execution patterns correlate with strong or weak outcomes

## Scope and Fixed Decisions

1. V2 depends on V1 session usage alignment as its data foundation.
2. Immutable usage events are stored once; attribution is modeled as links from events to entities.
3. Exclusive totals and supporting totals are distinct concepts and must not be merged.
4. Session totals remain authoritative for session workload; attribution is a derived analytical layer.
5. Attributed cost remains model-IO-derived cost unless a new pricing model is added later.

## Non-Goals

1. Replacing V1 session totals with heuristic attribution totals.
2. Building a generic causal inference engine for every session behavior.
3. Solving all workflow recommendation logic in the same release.
4. Supporting every platform before the Claude Code path is validated.

## Recommended Data Model

### 1) Immutable Usage Events

Create a normalized `session_usage_events` table keyed by event/log identity with fields such as:

1. `id`
2. `project_id`
3. `session_id`
4. `root_session_id`
5. `linked_session_id`
6. `source_log_id`
7. `captured_at`
8. `event_kind`
9. `model`
10. `tool_name`
11. `agent_name`
12. `token_family`
13. `delta_tokens`
14. `cost_usd_model_io`
15. `metadata_json`

### 2) Attribution Links

Create a normalized `session_usage_attributions` table:

1. `event_id`
2. `entity_type`
3. `entity_id`
4. `attribution_role`
5. `weight`
6. `method`
7. `confidence`
8. `metadata_json`

### 3) Derived Rollups

Materialize rollups for common query paths via `analytics_entries` and related link tables, or a dedicated attribution-rollup table, for:

1. skill
2. agent
3. subthread
4. command
5. artifact
6. feature
7. workflow or stack

## Attribution Semantics

1. One usage event can have one primary attribution link.
2. The same event can also have multiple supporting links.
3. Exclusive totals sum primary links only.
4. Supporting totals may exceed session totals and must be labeled as participation, not reconciliation-grade totals.
5. Weight and confidence are required for every non-trivial inferred link.

## Reconciliation Rules

1. `model_input` + `model_output` usage-event totals must reconcile to `sessions.model_io_tokens`.
2. `cache_creation_input` + `cache_read_input` usage-event totals must reconcile to the persisted session cache-input families.
3. `tool_result_*` usage-event totals reconcile only to the `tool_result_*` session columns; they never mutate session-authoritative model-IO totals.
4. Relay-mirror events remain stored for traceability, but they stay excluded from V1 observed workload totals until a tested attribution rule promotes them.
5. Exclusive attribution totals reconcile against session-authoritative totals; supporting totals are participation metrics and may exceed those totals.

## Phase 1: Schema and Contract Definition

Tasks:

1. Define backend/frontend types for usage events, attribution links, and aggregate responses.
2. Add SQLite and PostgreSQL migrations for immutable usage-event and attribution-link storage.
3. Define canonical enums for:
   - token family
   - entity type
   - attribution role
   - attribution method
4. Document reconciliation rules between session totals and exclusive attribution totals.

Acceptance criteria:

1. The attribution schema is stable and cross-database compatible.
2. Types and API contracts distinguish exclusive versus supporting views.
3. The contract is clear enough to implement multiple attribution methods without schema churn.

## Phase 2: Usage Event Population and Backfill

Tasks:

1. Populate `session_usage_events` from the preserved V1 log-level usage metadata and session context.
2. Backfill historical Claude sessions into usage-event rows.
3. Preserve source traceability from event rows back to session/log identifiers.
4. Validate that event totals reconcile with V1 session totals for the same token families.

Acceptance criteria:

1. Historical Claude sessions produce stable usage-event rows.
2. Event totals reconcile with session totals within defined tolerance.
3. Reprocessing is deterministic and idempotent.

## Phase 3: Attribution Resolver and Confidence Rules

Tasks:

1. Implement primary attribution resolvers for:
   - explicit skill invocation
   - explicit agent/subthread ownership
   - command execution context
   - artifact-linked events
2. Implement supporting attribution resolvers for:
   - nearby skill/artifact windows
   - workflow or stack membership
   - feature context inheritance
3. Assign `method`, `confidence`, and `weight` for every created link.
4. Add safeguards so one event cannot silently create multiple primary owners.

Acceptance criteria:

1. Attribution methods are deterministic and testable.
2. High-confidence explicit signals outrank heuristic window-based signals.
3. No event receives conflicting primary attributions.

## Phase 4: Rollups, Queries, and Correlation APIs

Tasks:

1. Extend analytics APIs to query attribution by skill, agent, subthread, command, artifact, and feature.
2. Add drill-down APIs from aggregate rows to contributing sessions and usage events.
3. Add correlation metrics such as:
   - attributed tokens per completed task
   - cache share by skill or agent
   - attributed model cost by workflow component
   - subagent yield versus attributed tokens
4. Materialize rollups needed for performant UI filtering and sorting.

Acceptance criteria:

1. APIs can serve attribution views without scanning raw logs per request.
2. Aggregate results include confidence and method summaries.
3. Drill-down rows can be traced back to source sessions and logs.

## Phase 5: UI Surfaces and Workflow Integration

Tasks:

1. Add attribution tabs or panels to `components/Analytics/AnalyticsDashboard.tsx`.
2. Extend `components/execution/WorkflowEffectivenessSurface.tsx` to consume attributed token and cost metrics.
3. Add session-level attribution drill-down or overlays in `components/SessionInspector.tsx`.
4. Add feature-facing attribution summaries where confidence and scope are strong enough.

Acceptance criteria:

1. Users can inspect top costly or high-yield skills and agents in-product.
2. Workflow effectiveness views can compare patterns using attributed token metrics.
3. Session and feature drill-downs retain traceability to source evidence.

## Phase 6: Calibration, Validation, and Heuristic Tuning

Tasks:

1. Build validation fixtures covering explicit skill, explicit subagent, artifact-linked, and ambiguous overlap scenarios.
2. Compare exclusive totals against session model-IO totals on sampled real sessions.
3. Measure attribution coverage, confidence distribution, and false-positive patterns.
4. Tune weights and precedence rules based on calibration findings.

Acceptance criteria:

1. Attribution coverage and reconciliation metrics are reported.
2. Known ambiguity cases are visible and bounded rather than silently misattributed.
3. The heuristic stack is stable enough for user-facing release.

## Phase 7: Documentation, Rollout, and V3 Hooks

Tasks:

1. Document attribution semantics, caveats, and confidence interpretation for maintainers and users.
2. Add rollout guardrails or feature flags if attribution views should launch gradually.
3. Capture follow-on hooks for:
   - smarter recommendation systems
   - stack optimization loops
   - broader cross-platform attribution
4. Ensure V2 outputs can feed future workflow or stack recommendation layers without redefining the core contract.

Acceptance criteria:

1. Attribution caveats are documented clearly.
2. Rollout can be controlled without schema rework.
3. Future optimization work can consume V2 outputs as stable inputs.

## Risks

1. Over-attribution risk: too many supporting links create noisy analytics.
2. Under-attribution risk: conservative rules leave valuable events unattributed.
3. Performance risk: event-level drill-downs and broad rollups become expensive without materialization.
4. Product risk: users misread supporting totals as exclusive reconciled totals.

## Recommended Rollout Order

1. Schema and contracts
2. Usage-event population
3. Attribution resolver
4. Rollups and APIs
5. UI integration
6. Calibration
7. Documentation and rollout
