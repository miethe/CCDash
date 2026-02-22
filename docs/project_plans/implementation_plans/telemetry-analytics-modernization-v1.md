---
title: "Implementation Plan: Telemetry + Analytics Modernization"
description: "Comprehensive audit and improvement roadmap for CCDash telemetry collection, storage, analytics, correlation, and export"
audience: [ai-agents, developers, engineering-leads]
tags: [implementation, planning, analytics, telemetry, observability, otel, grafana, dashboards]
created: 2026-02-22
updated: 2026-02-22
category: "implementation-plan"
complexity: "High"
track: "Two-track (Quick Wins + Platform)"
status: "draft"
---

# Implementation Plan: Telemetry + Analytics Modernization

## Objective

Build a complete, reliable analytics pipeline that:

1. Captures full-fidelity telemetry across sessions, agents/skills, threads, tool calls, commits/PRs, features, and tasks.
2. Persists telemetry in a queryable model with clear lineage and correlation keys.
3. Produces trustworthy built-in analytics/dashboards (no simulated values).
4. Exports telemetry and derived metrics to standard observability platforms (OTel-first, Prom fallback, Grafana-ready).

## Scope and decision defaults

Selected defaults for this plan:

1. Delivery: two-track roadmap (quick wins first, platform hardening second).
2. Export strategy: OTel-native with Prometheus fallback.
3. Data governance: full-fidelity capture by default.
4. Storage: SQLite-first with Postgres parity.
5. Platform target: self-hosted local observability stack first.

---

## Current pipeline audit

### End-to-end flow today

1. Ingestion/parsing:
   - Session metadata/logs/tool calls/artifacts: `backend/parsers/sessions.py`
   - Document entities/links: `backend/parsers/documents.py`
   - Task/progress extraction: `backend/parsers/progress.py`
2. Persistence + derived snapshot metrics:
   - Sync and analytics snapshot creation: `backend/db/sync_engine.py`
3. Query/export layer:
   - Analytics APIs and Prom export: `backend/routers/analytics.py`
4. UI consumption:
   - Analytics dashboard: `components/Analytics/AnalyticsDashboard.tsx`
   - Main dashboard: `components/Dashboard.tsx`
   - Session analytics view: `components/SessionInspector.tsx`
   - Settings alerts: `components/Settings.tsx`

### Data coverage matrix (captured vs saved vs analyzed vs exported)

1. Sessions/log lines/tool usage/artifacts
   - Captured: yes
   - Persisted: yes (`sessions`, `session_logs`, `session_tool_usage`, `session_artifacts`)
   - Analyzed: partial
   - Exported externally: minimal
2. Thread/subthread relationships
   - Captured: partial (`subagent_start`, artifact links)
   - Persisted: partial
   - Analyzed: low
   - Exported externally: no
3. Tokens/cost/model usage
   - Captured: partial (mix of real and inferred)
   - Persisted: partial
   - Analyzed: partial
   - Exported externally: minimal (latest-value Prom only)
4. Features/tasks/projects/PR/commits correlations
   - Captured: partial
   - Persisted: partial (`entity_links`, artifacts)
   - Analyzed: limited
   - Exported externally: no
5. Alerts
   - Captured/configured: seed + UI state
   - Persisted: partially (seed), runtime editing not wired
   - Analyzed/evaluated: partial
   - Exported: no

### Confirmed strengths

1. Session parser already extracts many high-value signals (tool calls, subagents, command phases, commit hash, summaries, PR links, queue operations).
2. Existing entity-linking logic is robust and confidence-aware.
3. Core normalized data is available at useful scale in the local cache DB.

### Confirmed gaps and defects

1. Analytics scope is narrow:
   - Snapshot captures only a small set of project-level point metrics.
   - No rich dimensions for model/tool/agent/skill/feature in series APIs.
2. Entity-linked analytics missing:
   - `analytics_entity_links` table exists but is not populated.
3. Metadata missing in analytics rows:
   - `analytics_entries.metadata_json` currently unused.
4. No rollups:
   - All analytics rows use `period='point'`; no hourly/daily/weekly materialization.
5. Correctness defect in task completion metrics:
   - Progress parser uses `done`/`deferred`, while stats query expects `completed`.
   - Observed outcome: velocity/completion analytics can be zero despite completed tasks.
6. Underutilized fields:
   - Tool duration (`session_tool_usage.total_ms`) not populated.
   - File diff stats (additions/deletions) are often zeroed.
   - Session impact history/timeline not fully persisted and rehydrated.
7. Frontend analytics disconnects:
   - Main dashboard contains hardcoded KPI/model values.
   - Session inspector token timeline includes simulated data.
   - Alerts settings UI not wired to backend CRUD.
8. Export path is shallow:
   - Prom endpoint exposes latest-value gauges only.
   - No OTel SDK wiring, no OTLP exporter pipeline.
9. Postgres parity risk:
   - Analytics link upsert/uniqueness semantics are stronger in SQLite than in Postgres implementation.

---

## Target-state architecture

### Principles

1. Keep parsers as source for telemetry facts.
2. Keep DB as analytics store and correlation graph.
3. Separate event facts from derived metric series.
4. Make frontend consume backend analytics as source of truth.
5. Keep compatibility while adding richer APIs.

### Data model layers

1. Fact layer (high fidelity): `telemetry_events` (new)
2. Operational normalized layer: existing session/task/feature/link tables
3. Derived metrics layer: `analytics_entries` (expanded semantics)
4. Correlation layer: `analytics_entity_links` + `entity_links`

### Canonical correlation keys

1. `project_id`
2. `session_id`
3. `root_session_id`
4. `feature_id`
5. `task_id`
6. `commit_hash`
7. `pr_number`
8. `phase`
9. `tool_name`
10. `model`
11. `agent`
12. `skill`

---

## High-value new telemetry to add

1. Tool execution fidelity:
   - `duration_ms`, `exit_code`, `retry_count`, `failure_class`, `timeout_flag`
2. Token economics:
   - Prompt/completion token deltas per step, cumulative checkpoints, cost attribution per feature/task
3. Thread topology:
   - Fan-out, depth, unresolved branch count, orphaned subthread count
4. Delivery lifecycle:
   - Commit/PR open/review/merge timestamps, cycle time, re-open counts
5. Quality pipeline outcomes:
   - Test/lint/build/deploy counters and pass/fail classes
6. Efficiency/rework:
   - Tokens per completed task, retries per successful tool action, loop/stall detection
7. Confidence and lineage:
   - Link confidence, inferred-vs-explicit relationship flags, ambiguity score

---

## API and schema modernization plan

### Analytics API surface (new/expanded)

1. `GET /api/analytics/overview`
   - KPI card payload for selectable scope and date window
2. `GET /api/analytics/series`
   - Period rollups and optional dimension grouping
3. `GET /api/analytics/breakdown`
   - Distributions by tool/model/agent/skill/feature/session type
4. `GET /api/analytics/correlation`
   - Feature/task/session/commit/PR joined view with confidence metadata
5. Alerts CRUD:
   - `POST /api/analytics/alerts`
   - `PATCH /api/analytics/alerts/{id}`
   - `DELETE /api/analytics/alerts/{id}`

Compatibility:

1. Keep `/api/analytics/metrics`, `/api/analytics/trends`, `/api/analytics/export/prometheus`.
2. Re-implement legacy endpoints on top of the new query engine.

### Schema changes

1. Expand `analytics_entries` usage:
   - Proper `period` values (`point`, `hourly`, `daily`, `weekly`)
   - Non-empty `metadata_json` for dimensions/context
2. Start writing `analytics_entity_links` during metric generation.
3. Add `telemetry_events` table (SQLite + Postgres parity):
   - Keys: project/session/time/sequence
   - Dimensions: event_type, tool/model/agent/skill, feature/task, commit/PR
   - Payload: `payload_json` full fidelity
4. Add missing indexes and uniqueness guarantees for link upserts in Postgres.

### Frontend type updates

1. Expand analytics types in `types.ts` for overview/series/breakdown/correlation.
2. Align alert metric enums with backend metric IDs.
3. Add session analytics types for real token timeline points and timing summaries.

---

## Two-track implementation roadmap

## Track A (2-4 weeks): correctness + complete in-product analytics

### A1. Correctness and persistence parity

1. Fix task completion semantics (`done`/`deferred` counted appropriately).
2. Populate `session_tool_usage.total_ms` from available runtime/progress data.
3. Persist session impact/timeline/date fields so UI can rehydrate accurately.
4. Write dimensional context into `analytics_entries.metadata_json`.
5. Populate `analytics_entity_links` for all derived metrics where entity scope exists.

### A2. Query layer expansion

1. Implement overview/series/breakdown/correlation endpoints.
2. Add rollup aggregation windows: point, hourly, daily, weekly.
3. Add filters: project, feature, session type, model family, tool, agent, skill, date range.
4. Add limit/pagination for heavy grouped queries.

### A3. UI wiring (remove placeholder/simulated analytics)

1. Replace hardcoded main dashboard KPIs and model chart with `/overview` + `/breakdown`.
2. Replace simulated Session Inspector token series with `/series`.
3. Wire Settings alerts tab to backend CRUD and persisted evaluation results.
4. Ensure dashboard refresh and cache invalidation are explicit and observable.

Deliverable criteria for Track A:

1. All displayed analytics derived from persisted backend data.
2. No key metrics return incorrect zero values due to status mismatch.
3. Alert configurations persist and survive reload.

## Track B (platform): telemetry infrastructure + external observability

### B1. Event fact model and backfill

1. Implement `telemetry_events` migrations (SQLite + Postgres).
2. Build backfill job from existing session tables and artifacts.
3. Add incremental ingestion path from sync pipeline.

### B2. OTel instrumentation

1. Add SDK/exporter dependencies and initialization.
2. Instrument FastAPI request traces and critical backend spans (parse/sync/rebuild/repo calls).
3. Emit counters/histograms for ingestion latency, parser failures, tool success/failure, and token/cost metrics.
4. Configure via env vars:
   - `CCDASH_OTEL_ENABLED`
   - `CCDASH_OTEL_ENDPOINT`
   - `CCDASH_OTEL_SERVICE_NAME`
   - `CCDASH_PROM_PORT`

### B3. Self-hosted observability stack

1. Add `deploy/observability/docker-compose.yml`:
   - OTel Collector, Prometheus, Grafana, optional Tempo/Loki
2. Add Grafana provisioning:
   - Datasources and dashboard JSON
3. Ship default dashboards:
   - Ingestion health and lag
   - Token/cost efficiency by feature and model
   - Tool reliability and retry burden
   - Session/thread complexity vs delivery latency
   - Link confidence and unresolved-entity ambiguity

Deliverable criteria for Track B:

1. OTLP export working end-to-end.
2. Grafana dashboards available out-of-box via compose stack.
3. Derived metric parity across in-app views and external observability platform.

---

## Export strategy detail (OTel + Prom + Grafana)

1. OTel first:
   - Emit traces for workflows and DB-heavy operations.
   - Emit metrics for counts, rates, durations, and cost/token usage.
2. Prometheus fallback:
   - Keep `/api/analytics/export/prometheus` for compatibility.
   - Expand beyond latest-value gauges to support richer time-series labels where feasible.
3. Grafana mapping:
   - Use Prometheus/OTel Collector as primary datasource.
   - Add dashboard templates aligned with in-product KPIs.

Suggested metric mapping examples:

1. `ccdash_tool_calls_total{tool,status}` (counter)
2. `ccdash_tool_duration_ms{tool}` (histogram)
3. `ccdash_tokens_total{model,feature}` (counter)
4. `ccdash_cost_usd_total{model,feature}` (counter)
5. `ccdash_session_depth{project}` (gauge/distribution)
6. `ccdash_sync_duration_ms{result}` (histogram)

---

## Built-in dashboard and analysis tooling plan

### Dashboarding libraries and implementation approach

1. Continue existing charting stack where possible to avoid churn.
2. Introduce query abstraction in `services/analytics.ts` for new endpoint family.
3. Add reusable hooks for scoped analytics queries and caching.
4. Build configurable panels with shared filter state (project/date/feature/tool/model).
5. Add drill-down navigation paths:
   - KPI -> series -> correlation -> raw session/context detail

### In-product analysis features to add

1. Cohort analysis by feature/session type.
2. Efficiency leaderboard (cost-per-done-task, tokens-per-phase).
3. Reliability heatmaps (tool x model x failure class).
4. Regression/anomaly cards (sudden cost spike, drop in completion velocity).
5. Correlated timeline view (events + commits + PR milestones + task transitions).

---

## Validation and test plan

### Unit and integration tests

1. Parser-to-repository parity for extracted metadata and timings.
2. Task metric correctness across status variants (`done`, `deferred`, `completed` compatibility).
3. Rollup correctness for hourly/daily/weekly windows.
4. Entity-linked analytics write/read correctness.
5. Alert CRUD and evaluation lifecycle tests.
6. OTel smoke tests for traces and metrics emission.

### UI verification

1. Dashboard values match backend API responses exactly.
2. Session Inspector charts use persisted series, not synthetic estimations.
3. Alert settings persist and reflect backend truth after reload.

### Performance and scale checks

1. Full sync runtime regression budget.
2. Query latency SLOs for overview/series/breakdown/correlation.
3. DB growth and retention checks under full-fidelity ingestion.

---

## Rollout, backfill, and risk management

1. Release A1/A2/A3 behind feature flags where needed.
2. Run one-time analytics recompute/backfill after correctness fixes.
3. Validate KPI parity before replacing current UI data paths.
4. Release telemetry event table and OTel export incrementally.
5. Document retention, sampling (if later needed), and privacy controls.

Key risks and mitigations:

1. Risk: DB growth from full-fidelity events.
   - Mitigation: retention windows, cold archive, optional sampling policy in later phase.
2. Risk: query latency for high-cardinality dimensions.
   - Mitigation: targeted indexes, pre-aggregations/materialized rollups.
3. Risk: schema drift between SQLite/Postgres.
   - Mitigation: parity test suite and migration contract checks.

---

## Initial implementation backlog

1. `AN-001` Fix task completion metric semantics in SQLite/Postgres repositories.
2. `AN-002` Extend analytics capture to include metadata and entity links.
3. `AN-003` Add analytics overview endpoint.
4. `AN-004` Add analytics series endpoint with rollups and grouping.
5. `AN-005` Add analytics breakdown endpoint.
6. `AN-006` Add analytics correlation endpoint.
7. `AN-007` Add alert CRUD APIs and persistence.
8. `AN-008` Rewire `components/Dashboard.tsx` to backend analytics.
9. `AN-009` Rewire `components/SessionInspector.tsx` token timeline to backend series.
10. `AN-010` Rewire `components/Settings.tsx` alerts UI to backend CRUD.
11. `AN-011` Add `telemetry_events` schema and backfill pipeline.
12. `AN-012` Add OTel SDK wiring and OTLP/Prom exporters.
13. `AN-013` Add self-hosted Grafana/Prom/Collector stack in `deploy/observability`.

## Definition of done

1. All major analytics shown in-product are backend-derived and persisted.
2. Entity-linked correlations are queryable for feature/task/session/commit/PR workflows.
3. OTel export is operational and Grafana dashboards are usable with provided deploy assets.
4. Correctness defects (especially task completion) are resolved and covered by tests.
