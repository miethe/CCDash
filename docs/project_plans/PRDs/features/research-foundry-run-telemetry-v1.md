---
title: 'PRD: Research Foundry Run Telemetry in CCDash'
schema_version: 2
doc_type: prd
it_schema: 1
description: Ingest, persist, correlate, and visualize Research Foundry (RF) search-run
  telemetry as a first-class CCDash run entity, linked to sessions, so the operator
  can close RF's evidence-driven provider-selection loop.
status: draft
created: '2026-07-21'
updated: '2026-07-21'
feature_slug: research-foundry-run-telemetry
feature_version: v1
tier: 3
effort_estimate: '26 points (P1: 8, P2: 9, P3: 6, P4: 3)'
changelog_required: true
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
related_documents:
- ../../../../docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-feasibility-brief.md
- ../../../../docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
- ../../../../../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
references:
  user_docs:
  - docs/guides/remote-ingest-operator-guide.md
  context:
  - CLAUDE.md
  specs:
  - docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md
  related_prds: []
spike_ref: null
adr_refs:
- docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-proposed-adr.md
charter_ref: docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
changelog_ref: null
test_plan_ref: null
owner: null
contributors: []
priority: medium
risk_level: medium
category: product-planning
tags:
- prd
- planning
- feature
- research-foundry
- telemetry
- ingest
- analytics
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- backend/routers/ingest.py
- backend/application/models/ingest.py
- backend/application/services/ingest/rf_events_ingest.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/repositories/entity_graph.py
- backend/application/services/agent_queries/run_intelligence.py
- backend/application/services/agent_queries/ingest_sources.py
- backend/routers/agent.py
- backend/routers/client_v1.py
- components/Analytics/AnalyticsDashboard.tsx
- services/queryKeys.ts
- types.ts
open_questions:
- 'OQ-5: Should run_id resolve intent_id against the IntentTree API, or stay opaque
  display-only for v1? Resolved for this PRD: opaque display-only; IntentTree resolution
  is a named deferred item.'
decisions:
- decision: 'D1: Transport = new POST /api/v1/ingest/rf-events + rf_events table,
    reusing NDJSON/ingest_cursors/dead-letter (ADR-008/009/014/015)'
  rationale: RF's emit_ccdash_event writes YAML only inside RF's own workspace; reusing
    /ingest/sessions would pollute the sessions table.
  status: locked
- decision: 'D2: Correlate run<->session via links.py entity-link rows (kind=research_run)
    keyed by a genuine UUID run_id; RF ids are display-only attributes; no aos_correlation.py
    extension'
  rationale: RF ids are non-UUID semantic slugs that fail UUID_RE/AOS_URN_RE.
  status: locked
- decision: 'D3: Dual SQLite+Postgres DDL, retry_on_locked, direct-count test, parity-allowlist
    entry (ADR-007)'
  rationale: Non-negotiable DB write-path rule; ingest_cursors v36 precedent.
  status: locked
- decision: 'D4: 4-panel tab inside AnalyticsDashboard.tsx, not a new top-level route'
  rationale: Existing visual language is a 1:1 fit; reversible; YAGNI for solo-LAN
    volume.
  status: locked
- decision: 'D5: D-001 dedup discipline on any run<->session rollup from day one +
    regression test'
  rationale: run<->session is the same one-to-many shape as the deferred D-001 over-count.
  status: locked
- decision: 'D6: Split persistence into rf_events (raw append-only log) + research_runs
    (derived rollup)'
  rationale: Ingest stays append-only/idempotent; rollup is recomputable from the
    raw log.
  status: locked
- decision: 'D7: Defer per-provider cost/quality splits (no source_cards join in v1)'
  rationale: "The \xA716 execution_event carries only a provider LIST, not per-provider\
    \ splits; joining source_cards is out of scope for v1."
  status: locked
success_metrics:
- 100% of POSTed RF events persist idempotently (no duplicate rf_events rows on re-POST
  of the same event_id).
- research_runs rollup is queryable via REST/MCP/CLI with zero cross-run cost double-counting
  (D-001 regression test green).
- Provider Economics tab renders KPI strip + 3 panels from live or seeded data and
  degrades to explicit empty state with zero events (no 0/NaN).
agent_title: RF run telemetry ingest + entity + analytics tab
agent_summary: Add a new ingest endpoint + rf_events/research_runs tables + run_intelligence
  query service + a 4-panel analytics tab so RF search-run telemetry becomes a queryable,
  session-correlated CCDash entity.
---

# Feature Brief & Metadata

**Feature Name:** Research Foundry Run Telemetry in CCDash

**Filepath Name:** `research-foundry-run-telemetry-v1`

**Date:** 2026-07-21

**Author:** prd-writer (Sonnet 5), from Opus-authored decisions block

**Related Epic(s)/PRD ID(s):** None (new capability area)

**Related Documents:**

- Feasibility brief (verdict: conditional → effective go, 0.82 confidence): `docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-feasibility-brief.md`
- Exploration charter: `docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md`
- Four spikes (tech/priorart/risk/value): `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/`
- Opus decisions block: `.claude/worknotes/research-foundry-run-telemetry/decisions-block.md`
- RF Search Router spec (§11.2 `search_run`, §16 `execution_event` / §16.2 panels): `research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md`
- Deferred correlation dedup design spec: `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`

---

## 1. Executive Summary

Research Foundry (RF) — a sibling repo/service run by the same operator — now emits a
schema-validated per-run telemetry event (`ccdash_event`, RF spec §16) carrying provider spend,
useful-source rate, duplicate/extraction-failure rates, and latency. Today that event is written
only to a directory inside **RF's own workspace** with zero egress to CCDash — the evidence RF
needs to close its "which provider/mode gives the best useful-sources-per-dollar?" loop (RF spec
§5.2) is produced but never consumed. This feature adds a new ingest transport, a first-class
`research_runs` entity correlated to CCDash sessions, and a 4-panel analytics tab so the operator
can see RF's cost/quality economics inside CCDash, the existing home for cross-project analytics.

**Priority:** MEDIUM

**Key Outcomes:**
- Outcome 1: RF-shaped events POST to CCDash and persist idempotently, with dead-letter recovery on failure.
- Outcome 2: Ingested events roll up into a queryable `research_runs` entity, correlated to sessions where applicable, with zero cross-run cost double-counting.
- Outcome 3: A "Provider Economics" tab inside `AnalyticsDashboard.tsx` makes cost-per-useful-source and mode-level quality legible, degrading gracefully to an explicit empty state when RF has not yet sent any events.

---

## 2. Context & Background

### Current State

CCDash has no concept of an RF "search run." Sessions (`AgentSession`, `types.ts`) model AI
coding-agent transcripts; AOS correlation (`backend/services/aos_correlation.py`) is a read-time
URN-graph derivation over session transcript text and an external sidecar JSONL, keyed on
canonical `urn:aos:<kind>:<UUID>` strings — it is session metadata enrichment, not a run model,
and does not have stored `aos_*_uuid` columns (that claim in early prior-art research was
incorrect; corrected by the risk spike). `POST /api/v1/ingest/sessions` (ADR-006/008) is the only
external-push ingest surface today, and it hard-codes session-table semantics downstream
(`backend/application/services/ingest/session_ingest.py` → `sessions` table).

### Problem Space

RF shipped `emit_ccdash_event()` (commit `c3a2545`, 2026-07-20) — real, tested (135+ tests),
schema-validated (`schemas/ccdash_event.schema.yaml`) — but it writes YAML **only inside RF's own
workspace** (`FoundryPaths.ccdash` → `<rf-root>/ccdash/events/<event_id>.yaml`). There is no HTTP
client, OTEL exporter, or shared DB anywhere in RF's emission path. CCDash has zero code that
reads RF's workspace tree. The telemetry is real and durable; the receiving side does not exist.

### Current Alternatives / Workarounds

The operator would otherwise inspect RF's local YAML mirror (`ccdash/events/*.yaml`,
`ccdash/daily/*.yaml`) by hand, or run `rf ccdash summarize --period daily` from RF's own CLI —
no cross-session correlation, no dashboard visualization, no historical trend.

### Architectural Context

CCDash follows router → transport-neutral `agent_queries` service → repository → dual-DDL table.
This feature adds a new ingest router path, a new `agent_queries/run_intelligence.py` service, two
new dual-DDL tables, and one new frontend analytics tab — all additive, matching the existing
layered architecture with **zero modification** to `sessions`, `aos_correlation.py`,
`backend/routers/analytics.py`, or `planning_sessions.py`.

---

## 3. Problem Statement

> As the operator running Research Foundry search runs on the LAN, when I want to know which
> search mode or provider combination gives the best useful-sources-per-dollar, I have no visible
> evidence today — RF computes the metrics but they are inert YAML inside RF's own workspace —
> instead of a queryable, correlated, visualized run history inside CCDash.

**Technical Root Cause:**
- RF's telemetry transport is `defined_stubbed` (tech spike, confidence 0.92): schema-validated emission exists, egress to CCDash does not.
- No CCDash entity maps onto an RF search run (priorart spike, confidence 0.92): sessions, AOS correlation, and planning-board are all session/feature-scoped, not run-scoped.
- RF's correlation ids (`intent_id`, `task_node_id`, `event_id`) are non-UUID semantic slugs that cannot join CCDash's AOS sidecar-URN graph (risk spike, confidence 0.75).

---

## 4. Goals & Success Metrics

### Primary Goals

**Goal 1: Contract-first ingest that works with zero RF-side changes required**
- CCDash builds and tests the receiving contract independently of RF's transport landing.
- Success: `POST /api/v1/ingest/rf-events` accepts RF's `ccdash_event` shape and persists to `rf_events`, verifiable with seeded fixtures alone.

**Goal 2: A first-class, session-correlated run entity with no cost double-counting**
- Success: `research_runs` rollup is queryable via REST/MCP/CLI; any run↔session join applies D-001 dedup discipline from day one, with a shipped regression test.

**Goal 3: Legible cost/quality evidence inside the existing analytics home**
- Success: A 4-panel "Provider Economics" tab renders live/seeded run data and an explicit empty state with zero events — never `0`/`NaN` masquerading as "no cost incurred."

### Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|-------------------|
| Duplicate `rf_events` rows on re-POST of same `event_id` | N/A (no ingest exists) | 0 | Idempotency regression test (P1 exit gate) |
| Cross-run/cross-session cost double-count on any rollup | N/A | 0 | D-001-shape regression test (two runs sharing one session; session tokens counted once) |
| Provider Economics tab render with zero RF events | N/A | Explicit empty state, no `0`/`NaN` | Runtime smoke test (P3 exit gate) |
| Dual-DDL column-parity drift on `rf_events`/`research_runs` | N/A | 0 (CI-blocking) | `test_migration_governance.py` |

---

## 5. User Personas & Journeys

### Personas

**Primary Persona: Solo Operator (Nick)**
- Role: Runs both CCDash and Research Foundry on the same LAN, single-user.
- Needs: A single place to see whether a search mode/provider mix is worth its cost before running more RF searches.
- Pain Points: RF's evidence is buried in per-run YAML with no aggregation or trend view.

### High-level Flow

```mermaid
sequenceDiagram
    participant RF as Research Foundry
    participant CCDashAPI as POST /api/v1/ingest/rf-events
    participant RawTable as rf_events (raw)
    participant Rollup as research_runs (derived)
    participant Links as links.py (entity_graph)
    participant Tab as AnalyticsDashboard "Provider Economics" tab

    RF->>CCDashAPI: ccdash_event (best-effort, fail-open)
    CCDashAPI->>RawTable: idempotent insert (dedup on event_id)
    RawTable->>Rollup: derive/upsert research_runs row (CCDash-minted UUID run_id if RF's run_id is non-UUID)
    Rollup->>Links: entity-link row (kind=research_run) if a correlated session is known
    Tab->>Rollup: GET /api/agent/research-runs (via run_intelligence.py)
    Note over Tab: Zero events -> explicit empty state, never 0/NaN
```

---

## 6. Requirements

### 6.1 Functional Requirements

| ID | Requirement | Priority | Notes |
| :-: | ----------- | :------: | ----- |
| FR-1 | New `POST /api/v1/ingest/rf-events` endpoint accepts RF's `ccdash_event` shape (NDJSON or single JSON), reusing `WorkspaceTokenAuthBackend` (ADR-008) | Must | Router: `backend/routers/ingest.py` (new route in the existing `ingest_router`) |
| FR-2 | New `rf_events` table (dual SQLite+Postgres DDL) persists the raw event append-only, deduped on `event_id` | Must | Precedent: `ingest_cursors` v36 (`backend/db/sqlite_migrations.py:3782`) |
| FR-3 | Ingest reuses the idempotent NDJSON batch pattern + a per-source `ingest_cursors` row (`source_id='rf'`) + existing dead-letter queue on permanent failure | Must | No new coalescing mechanism; `CCDASH_SYNC_COALESCING_ENABLED` does not apply (RF is not a filesystem source) |
| FR-4 | `GET /api/v1/capabilities` advertises a `research-runs:*` capability string | Must | `backend/routers/client_v1.py` — same pattern as `sessions:detail` |
| FR-5 | `/api/health/detail` → `ingest_sources[]` registers an `rf` source entry with freshness thresholds | Must | `backend/application/services/agent_queries/ingest_sources.py` |
| FR-6 | New `research_runs` table (dual DDL) derives/upserts one row per run from `rf_events`, keyed on a genuine UUID `run_id` (CCDash-minted if RF's `run_id` is not a UUID4) | Must | RF spec §11.2 types `run_id` as generic `string`, not guaranteed UUID |
| FR-7 | New `run_intelligence.py` transport-neutral query service exposes run list + run detail | Must | `backend/application/services/agent_queries/run_intelligence.py`, pattern-matched to `system_metrics.py` |
| FR-8 | `GET /api/agent/research-runs` (+ `/{run_id}` detail) REST route wraps the query service | Must | `backend/routers/agent.py` |
| FR-9 | Run↔session correlation via `backend/db/repositories/entity_graph.py` (`SqliteEntityLinkRepository`) entity-link rows, `kind='research_run'`, keyed by the UUID `run_id`; RF's `intent_id`/`task_node_id` stored as display-only string attributes, never as join keys | Must | D2 — do not extend `aos_correlation.py` |
| FR-10 | Any rollup that sums cost/workload across run↔session joins applies `DISTINCT`/`GROUP BY`-before-sum (D-001 Option A) and ships a regression test (two runs sharing one session; session tokens counted once) | Must | D5; see `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` |
| FR-11 | Run intelligence query service auto-wires to MCP (`backend/mcp/server.py`) and CLI (`backend/cli/`) per the transport-neutral pattern | Should | OQ-3 resolved: include the query service now; MCP/CLI thin wrappers are low marginal cost given the existing pattern |
| FR-12 | New "Provider Economics" tab (`id: 'research'`) added to `AnalyticsDashboard.tsx` `TAB_LABELS`, with 4 panels: KPI strip, cost & quality by mode, spend/run-volume trend, run-level drill table | Must | D4; reuses `MetricCard`, `TrendChart`, `EntityLinkButton`, dense-table patterns already in the file |
| FR-13 | Feature flag `CCDASH_RF_TELEMETRY_ENABLED` (default `true`, fail-open) gates the ingest route + the analytics tab | Must | OQ-2 resolved; disabling hides the tab and 404s the ingest route without affecting any other surface |
| FR-14 | Every RF-sourced field in ingest payload and rollup passes through the existing Layer 1 known-secret pattern scan before persistence | Should | Reuse `backend/application/services/agent_queries/redaction.py` gate defensively; RF events carry query text and cost data, not transcripts, but the scan is cheap insurance |

### 6.2 Non-Functional Requirements

**Performance:**
- RF's telemetry cadence is per-search-run (low-frequency, not per-message); no batching design is required for v1.
- All writes wrapped in `retry_on_locked` (ADR-007); independent connections set `PRAGMA busy_timeout=30000`.

**Security:**
- No new auth scheme — reuse `WorkspaceTokenAuthBackend` (ADR-008) exactly as the sessions ingest route does.
- RF POST is best-effort/fail-open on RF's side (out of this PRD's scope; see RF companion deliverable in §8 Dependencies); CCDash's endpoint never blocks or retries synchronously against RF.

**Reliability:**
- Idempotent ingest: re-POSTing the same `event_id` is a no-op (zero duplicate rows).
- Dead-letter queue captures permanently-failed events for later replay, reusing the existing NDJSON dead-letter mechanism.
- Absence is a contract state: no RF events ever arriving must not degrade any existing surface (sessions, planning, analytics overview) — the new surface is additive by construction.

**Observability:**
- OpenTelemetry spans on the new ingest route and `run_intelligence.py` service calls, structured logs with `trace_id`/`span_id`.
- `ingest_sources[]` entry surfaces staleness exactly like other remote sources (`CCDASH_INGEST_SOURCE_FRESH_SECONDS`/`_STALE_SECONDS`).

---

## 7. Scope

### In Scope

- New `POST /api/v1/ingest/rf-events` endpoint + `rf_events` raw table (P1).
- `research_runs` derived rollup + `run_intelligence.py` query service + REST/MCP/CLI surfaces (P2).
- Run↔session correlation via `links.py`/`entity_graph.py`, keyed by a genuine UUID `run_id` (P2).
- D-001-shape dedup discipline + regression test on any run-aware rollup (P2).
- 4-panel "Provider Economics" analytics tab inside `AnalyticsDashboard.tsx` (P3): KPI strip, cost & quality **by mode** (not by provider — see Contract Reality below), spend/volume trend, run-level drill table.
- Feature flag, capability advertisement, ingest health entry, operator docs, CHANGELOG entry (P4).
- Deferred-panel design specs authored as DOC-006 tasks in the implementation plan (P4) — see §12 Deferred Items.

### Out of Scope

**Contract reality — the honest visualization grain is per-mode/per-run, not per-provider.** RF's
§16 `execution_event` carries run-level aggregate metrics plus a provider **list**
(`selected_providers: [exa, brave, jina]`) — it does **not** carry per-provider cost/quality splits,
source domains, extractor identity, report timestamps, or the claim ledger. The following are
explicitly out of scope for v1 and are named deferred items (§12), not silent gaps:

- Per-provider cost/quality attribution (§16.2 panels #2, #8 "by provider") — not computable from the event alone.
- Useful-source-rate by domain (§16.2 panel #3) — needs source domain, which lives in `source_cards` (RF spec §11.3), not the event.
- Extraction-failure-rate by extractor (§16.2 panel #7) — needs `source_card.extractor`.
- Search→report latency (§16.2 panel #6) — needs a report/synthesis timestamp not present in the event.
- Claims unsupported/conflicted/stale (§16.2 panel #10) — needs RF's claim ledger (§11.4), a separate entity not ingested by this feature.
- Reusable patterns promoted to SkillMeat (§16.2 panel #11) — cross-system, explicitly out of the exploration charter's scope.
- **RF-side emission changes**: adding the HTTP POST call inside `emit_ccdash_event()` is a research-foundry-repo deliverable, handed off separately (see the RF transport handoff addendum referenced in the feasibility brief). This PRD's endpoint must work correctly against seeded fixtures with zero live RF traffic.
- **Provider-scoring algorithm**: this feature surfaces raw cost/quality metrics; it does not implement any provider-ranking or recommendation algorithm.
- **MeatyWiki/SkillMeat writebacks**: RF's own writeback targets (`meatywiki_page_ids`, `skillmeat_candidate_ids` on `search_run.writebacks`) are not ingested or surfaced by this feature.
- **IntentTree `intent_id` resolution**: `intent_id`/`task_node_id` are stored as opaque display strings; resolving them against the IntentTree API is a named deferred item (§12).

---

## 8. Dependencies & Assumptions

### External Dependencies

- **Research Foundry** (sibling repo/service, node `:7432`): source of the `ccdash_event` telemetry. Schema: `research-foundry/schemas/ccdash_event.schema.yaml` (`additionalProperties: true` — tolerant of CCDash-side additions).

### Internal Dependencies

- **NDJSON/ingest_cursors/dead-letter transport** (ADR-008/009/014/015): reused as-is for the new ingest route.
- **`backend/db/repositories/entity_graph.py`** (`SqliteEntityLinkRepository`): extended with a new linkable entity kind (`research_run`), additive.
- **`components/Analytics/AnalyticsDashboard.tsx`** (1,244 lines pre-feature): extended with one new tab; existing tabs, primitives (`MetricCard`, `TrendChart`, `EntityLinkButton`), and `TAB_LABELS` array are additive-only touches.

### Assumptions

- RF's transport is `defined_stubbed` as of this writing (2026-07-21); this PRD builds the receiving contract independent of when/whether the RF-side POST call lands. Zero live events is a valid, tested, first-class state (see resilience ACs below).
- RF's `search_run.run_id` (spec §11.2) is typed as a generic `string`, not guaranteed to be a UUID4; CCDash mints its own UUID `run_id` for `research_runs` when RF's value does not parse as one.
- `intent_id`/`task_node_id` remain opaque display strings for v1 (OQ-5 resolved: no IntentTree resolution in this feature).

### Feature Flags

- `CCDASH_RF_TELEMETRY_ENABLED` (default `true`, fail-open): gates the ingest route and the analytics tab. Disabling returns 404 from the ingest endpoint and hides the tab; no effect on any other CCDash surface.

---

## 9. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
| ----- | :----: | :--------: | ---------- |
| Run↔session cost rollup reproduces D-001's multi-parent over-count | High | Medium-High if shipped without dedup | Apply D-001 Option A (`DISTINCT`/`GROUP BY` before sum) as a hard rule from day one (P2); ship the regression test as an exit gate, not deferred |
| Correlation-key mismatch (RF slugs vs. CCDash UUIDs) corrupts the AOS URN graph if force-fit | Medium | Certain if attempted | D2 — entity-link rows keyed by a genuine UUID `run_id`; RF's semantic ids stored as display-only attributes; zero changes to `aos_correlation.py` |
| Per-provider data gap: §16.2 "by provider/domain/extractor" panels are not computable from the event alone | Medium | Certain (confirmed by spec inspection) | Build the honest per-mode/per-run grain for v1 MVP (P3); named deferred items with unblock conditions (§12), not silently dropped |
| RF telemetry may not flow yet (transport is `defined_stubbed`, cross-repo dependency) | Medium | Medium (separate deploy lifecycle) | Contract-first P1 buildable and testable now via seeded fixtures; resilience-by-default on every surface; feature flag; fail-open at both ends |
| Dual-DDL parity drift across two new tables (SQLite vs. Postgres) | Low-Medium | Low (governance test auto-fails CI) | Follow the `ingest_cursors` v36 precedent exactly; `test_migration_governance.py` gate before merge |

---

## 10. Target State (Post-Implementation)

**User Experience:**
- The operator opens `/analytics`, selects the "Provider Economics" tab, and sees total RF spend, cost-per-useful-source, and a mode-level breakdown table — with an explicit "no research runs recorded yet" empty state if RF has never POSTed an event.
- Clicking a run row's `EntityLinkButton` (when a correlated session exists) opens that session in `SessionInspector`.

**Technical Architecture:**
- RF (once its companion transport change lands) POSTs each `ccdash_event` to `POST /api/v1/ingest/rf-events`; CCDash persists it idempotently to `rf_events`, derives/upserts a `research_runs` row, and (when a session correlation is discoverable) writes an `entity_graph` link row.
- `run_intelligence.py` serves REST (`/api/agent/research-runs*`), MCP, and CLI consumers from the same query path.
- The analytics tab reads via a TanStack Query hook keyed in `services/queryKeys.ts` (`researchRunsKeys`).

**Observable Outcomes:**
- `ingest_sources[]` shows an `rf` entry with live/stale/disconnected state.
- `GET /api/v1/capabilities` includes `research-runs:*`.
- Zero duplicate `rf_events` rows on repeated POSTs of the same `event_id`; zero cross-run cost double-counting on any rollup.

---

## 11. Overall Acceptance Criteria (Definition of Done)

### AC-1: Ingest endpoint persists idempotently with zero live RF traffic required

- target_surfaces:
    - backend/routers/ingest.py
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
- propagation_contract: A seeded `ccdash_event`-shaped JSON POST to `/api/v1/ingest/rf-events` (workspace-token auth) inserts one `rf_events` row; re-POSTing the identical `event_id` inserts zero additional rows.
- resilience: If the request body is missing optional RF fields (e.g. `human_review`, `output.claim_ledger_created`), the row still persists with those columns null — never a 422 for an optional field's absence.
- visual_evidence_required: false
- verified_by: [T1-ingest-idempotency-test, T1-direct-count-assertion-test]

### AC-2: Dual-DDL parity holds for both new tables

- target_surfaces:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
- propagation_contract: `rf_events` and `research_runs` each carry an identical column set (modulo allowed type drift: `JSONB` vs `TEXT`, `SERIAL` vs `AUTOINCREMENT`) across both DDL files, registered in `get_sqlite_migration_tables()`/`get_postgres_migration_tables()`.
- resilience: N/A (structural AC).
- visual_evidence_required: false
- verified_by: [T1-migration-governance-test]

### AC-3: Run↔session correlation never double-counts

- target_surfaces:
    - backend/db/repositories/entity_graph.py
    - backend/application/services/agent_queries/run_intelligence.py
- propagation_contract: Two `research_runs` rows linked to the same session, when rolled up for a combined cost/workload figure, produce a session-token count equal to the session's own stored total — counted once, not once per linked run.
- resilience: A run with zero linked sessions renders with an explicit "no linked session" state in any rollup that lists linkage, never a null-coalesced `0`.
- visual_evidence_required: false
- verified_by: [T2-d001-shape-dedup-regression-test]

### AC-4: Provider Economics tab renders correctly with zero events

- target_surfaces:
    - components/Analytics/AnalyticsDashboard.tsx
- propagation_contract: With `research_runs` empty, the "Provider Economics" tab renders an explicit empty state ("No research runs recorded yet") in all 4 panels — KPI strip, cost & quality by mode, spend/volume trend, run-level drill table.
- resilience: Missing (never null-vs-zero-conflated) `estimated_cost_usd`, `citation_coverage`, `latency_ms`, or any other optional metric on an individual run renders as an explicit "—" per-cell, never `$0.00`/`NaN`/`0%`.
- visual_evidence_required: desktop ≥1440px, before/after screenshots (empty state + seeded-fixture state)
- verified_by: [T3-runtime-smoke-provider-economics-tab, T3-resilience-fixture-test]

### AC-5: Capability + health surfaces advertise the new source correctly

- target_surfaces:
    - backend/routers/client_v1.py
    - backend/application/services/agent_queries/ingest_sources.py
- propagation_contract: `GET /api/v1/capabilities` includes `research-runs:*`; `/api/health/detail` → `ingest_sources[]` includes an `rf` entry whose state transitions `idle` → `connected` → `backed_up` → `disconnected` per the existing freshness-threshold logic, unmodified.
- resilience: Consumers that predate this feature and query `/api/v1/capabilities` MUST NOT hard-fail on the new capability string (existing contract, re-verified).
- visual_evidence_required: false
- verified_by: [T1-capability-advert-test, T1-ingest-source-health-test]

### Functional Acceptance

- [ ] FR-1 through FR-14 implemented per §6.1
- [ ] Seeded fixtures exercise the full P1→P3 path with zero live RF traffic
- [ ] All edge cases from Contract Reality (§7 Out of Scope) render as named deferrals, not silent gaps

### Technical Acceptance

- [ ] Follows router → agent_queries service → repository → dual-DDL table pattern
- [ ] All new API responses use DTOs, not ORM/row objects
- [ ] Cursor pagination on `research_runs`/`rf_events` list endpoints
- [ ] ErrorResponse envelope for all new endpoint failures
- [ ] OpenTelemetry spans on the ingest route and `run_intelligence.py`
- [ ] Structured logging with trace_id, span_id

### Quality Acceptance

- [ ] Unit tests for ingest idempotency, D-001-shape dedup regression, migration governance
- [ ] Integration test covering POST → rf_events → research_runs rollup → correlation link
- [ ] Runtime smoke check on the Provider Economics tab at ≥1440px (empty + seeded states)
- [ ] `karen` end-of-feature review passed

### Documentation Acceptance

- [ ] Operator guide for the new ingest source + feature flag
- [ ] CHANGELOG `[Unreleased]` entry (this PRD sets `changelog_required: true`)
- [ ] Deferred-panel design specs authored per §12

---

## 12. Deferred Items

Each deferred item below is a named, out-of-scope-for-v1 gap with an explicit unblock condition,
so the implementation plan can create design-spec authoring tasks (DOC-006) for them in P4.

| Item | Why deferred | Unblock condition |
|------|--------------|-------------------|
| **Per-provider cost/quality splits** (§16.2 panels #2, #8) | RF's §16 event carries only a provider list, not per-provider metric splits | RF emits per-provider metric splits in a future event schema version, **or** CCDash joins RF's §11.2 `source_cards` (requires ingesting `source_card` as a second entity) |
| **Useful-source rate by domain** (§16.2 panel #3) | Domain is not on the event; it lives on `source_card.url`/`canonical_url` | Same `source_cards` join as above |
| **Extraction failure rate by extractor** (§16.2 panel #7) | Extractor identity is on `source_card.extractor`, not the event | Same `source_cards` join as above |
| **Search→report latency** (§16.2 panel #6) | No report/synthesis timestamp exists on the event | RF adds a report-completion timestamp to a future event schema version |
| **Claims unsupported/conflicted/stale — claim-ledger panel** (§16.2 panel #10) | Requires ingesting RF's claim ledger (§11.4 `claim`), a distinct entity not covered by this PRD | A follow-up feature ingests `claim` records as a new entity, correlated to `research_runs` |
| **Reusable patterns promoted to SkillMeat panel** (§16.2 panel #11) | Cross-system (SkillMeat writeback tracking), explicitly out of the exploration charter's scope | A follow-up feature reads RF's `search_run.writebacks.skillmeat_candidate_ids` and joins SkillMeat's own artifact-intelligence surfaces |
| **IntentTree `intent_id`/`task_node_id` resolution** | Would require a live IntentTree API call at ingest or query time; opaque-string storage is sufficient for v1 operator legibility | IntentTree API access is wired for CCDash's backend (today `intent_id` is stored and displayed as an opaque string only) |

---

## 13. Assumptions & Open Questions

### Assumptions

- The exploration bundle (charter + 4 spikes + feasibility brief) satisfies the Tier-3 SPIKE gate; no separate SPIKE document is required before implementation planning.
- RF's transport landing (the companion HTTP POST inside `emit_ccdash_event()`) is a research-foundry-repo deliverable tracked separately; this PRD's endpoint is fully testable via seeded fixtures without it.
- `research_runs.run_id` is CCDash's canonical UUID primary key; RF's raw `run_id` string (per spec §11.2, typed as generic `string`) is stored as a separate `rf_run_id` display column when it does not parse as a UUID4.

### Open Questions

- [x] **OQ-1**: One table or two for persistence? — **A**: Two (`rf_events` raw + `research_runs` derived rollup); D6, locked.
- [x] **OQ-2**: Feature-flag name + default? — **A**: `CCDASH_RF_TELEMETRY_ENABLED`, default `true`, fail-open.
- [x] **OQ-3**: Expose run intelligence via MCP + CLI now or defer? — **A**: Include the query service and thin MCP/CLI wrappers now (FR-11); low marginal cost given the transport-neutral pattern.
- [x] **OQ-4**: Per-provider split via `source_cards` join now or defer? — **A**: Defer (D7); named deferred item with unblock condition (§12).
- [x] **OQ-5**: Resolve `intent_id` via IntentTree API or store opaque? — **A**: Opaque display-only for v1; named deferred item (§12).

---

## 14. Appendices & References

### Related Documentation

- **Proposed ADR**: `docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-proposed-adr.md` — (1) transport is `POST /api/v1/ingest/rf-events` backed by `rf_events`; (2) correlation uses entity-link rows keyed by a UUID `run_id`.
- **Design Spec (dedup precedent)**: `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` (D-001 Option A).
- **Remote ingest operator guide**: `docs/guides/remote-ingest-operator-guide.md` — transport precedent this feature reuses.

### Symbol References

- RF telemetry service: `research-foundry/src/research_foundry/services/telemetry.py:132-258` (`emit_ccdash_event`)
- RF search router: `research-foundry/src/research_foundry/services/search_router/router.py:363-378`
- RF paths: `research-foundry/src/research_foundry/paths.py:114-115` (`FoundryPaths.ccdash`)
- CCDash ingest router: `backend/routers/ingest.py`
- CCDash ingest models: `backend/application/models/ingest.py`
- CCDash entity link repository: `backend/db/repositories/entity_graph.py`
- CCDash ingest_cursors precedent: `backend/db/sqlite_migrations.py:3762-3800` (v36, ADR-009)
- CCDash AOS correlation (not touched): `backend/services/aos_correlation.py`
- CCDash analytics dashboard: `components/Analytics/AnalyticsDashboard.tsx` (`TAB_LABELS` at line 56)

### Prior Art

- Four exploration spikes: `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/{tech,priorart,risk,value}-spike.md`
- Note: the priorart spike's initial recommendation of a new top-level `/research` route was **superseded** by the risk and value spikes' analysis (D4) — the 4-panel MVP fits inside the existing `AnalyticsDashboard.tsx` visual language without a new route.

---

## Implementation

### Phased Approach

**Phase 1: Ingest transport + `rf_events` persistence** (8 pts)
- New `POST /api/v1/ingest/rf-events` endpoint (workspace-token auth, NDJSON/JSON)
- New `rf_events` raw table (dual DDL, `retry_on_locked`, ADR-007 direct-count test, column-parity allowlist entry)
- Idempotent enqueue via a `source_id='rf'` `ingest_cursors` row; reuse dead-letter queue
- `/api/v1/capabilities` advertises `research-runs:*`; `/api/health/detail` → `ingest_sources[]` registers `rf`
- Exit gate: a seeded/fixture event POSTs, persists idempotently, dead-letters on malformed payload; parity + direct-count tests green

**Phase 2: Run entity + intelligence + correlation** (9 pts)
- `research_runs` derived rollup table (dual DDL); CCDash-minted UUID `run_id` when RF's is non-UUID
- `run_intelligence.py` transport-neutral query service; `GET /api/agent/research-runs` (+ detail); MCP/CLI parity
- Run↔session correlation via `entity_graph.py` entity-link rows (kind=`research_run`)
- D-001 dedup discipline applied to any rollup, with regression test shipped as an exit gate
- Exit gate: runs queryable with metrics + linked sessions; dedup regression test passes

**Phase 3: Analytics visualization tab** (6 pts)
- 4-panel "Provider Economics" tab added to `AnalyticsDashboard.tsx` `TAB_LABELS`
- TanStack Query hook + `services/queryKeys.ts` entry (`researchRunsKeys`); `types.ts` entities (`ResearchRun`, `ResearchRunMetrics`)
- Resilience for every optional/absent field (AC-4)
- Exit gate: runtime smoke on the tab at ≥1440px (empty state + seeded-fixture state); resilience ACs verified

**Phase 4: Hardening + docs + deferred specs** (3 pts)
- Operator guide, CHANGELOG `[Unreleased]` entry, feature-flag doc
- Deferred-panel design specs authored per §12 (DOC-006 tasks)
- `karen` end-of-feature review; AC coverage matrix green

### Epics & User Stories Backlog

| Story ID | Short Name | Description | Acceptance Criteria | Estimate |
|----------|-----------|-------------|-------------------|----------|
| RFT-P1-1 | RF ingest endpoint | New `POST /api/v1/ingest/rf-events` route + auth reuse | AC-1 | 3 |
| RFT-P1-2 | `rf_events` table | Dual-DDL raw event table + parity test | AC-2 | 3 |
| RFT-P1-3 | Health + capability advert | `ingest_sources[]` + `/capabilities` entries | AC-5 | 2 |
| RFT-P2-1 | `research_runs` rollup | Dual-DDL derived table + UUID minting logic | AC-2 | 3 |
| RFT-P2-2 | `run_intelligence.py` + REST/MCP/CLI | Query service + wrappers | — | 3 |
| RFT-P2-3 | Run↔session correlation + D-001 dedup | Entity-link adapter + regression test | AC-3 | 3 |
| RFT-P3-1 | Provider Economics tab (4 panels) | KPI strip + mode table + trend + drill table | AC-4 | 6 |
| RFT-P4-1 | Docs + deferred specs + karen gate | Operator guide, CHANGELOG, DOC-006 specs | — | 3 |

---

**Progress Tracking:**

See progress tracking: `.claude/progress/research-foundry-run-telemetry/phase-N-progress.md` (created at implementation-plan time).
