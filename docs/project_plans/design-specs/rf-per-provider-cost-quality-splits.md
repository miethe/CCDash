---
schema_version: 2
doc_type: design_spec
title: "DF-001: Per-Provider Cost/Quality Splits for Research Foundry Run Telemetry"
description: >
  Deferred design spec for the Research Foundry (RF) run telemetry feature's per-provider
  cost/quality attribution gap (PRD §12, DF-001). RF's §16 execution_event carries only a
  provider LIST, not per-provider metric splits, so the "Provider Economics" tab's v1 MVP
  visualizes at the per-mode/per-run grain, not per-provider. Documents both candidate
  unblock paths and the investigation scope for whichever path is chosen at promotion time.
status: draft
maturity: idea
created: '2026-07-21'
updated: '2026-07-21'
feature_slug: research-foundry-run-telemetry
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
problem_statement: >
  The operator cannot see cost or quality broken down per-provider (e.g. exa vs. brave vs.
  jina) for a Research Foundry search run, because RF's emitted telemetry event aggregates
  cost/quality at the run level and only lists which providers were selected — it does not
  carry a per-provider split of spend, useful-source count, or citation coverage.
open_questions:
  - "Will RF add a per-provider metrics array to a future ccdash_event schema version, or will CCDash instead ingest RF's source_cards as a second entity and derive the split by joining source_card.provider against research_runs?"
  - "If the source_cards join path is chosen, does CCDash need a new ingest route/table (source_cards raw + rollup), or can per-provider aggregation be computed read-time from an existing RF export?"
  - "Does RF's source_card entity (RF spec §11.3) even carry a per-source cost attribution, or only provider identity — i.e. is cost inherently non-attributable below the run level regardless of which entity is ingested?"
explored_alternatives: []
related_documents:
  - docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md
  - research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
tags:
  - research-foundry
  - telemetry
  - analytics
  - deferred
  - provider-economics
audience: developers
category: design-spec
---

# DF-001: Per-Provider Cost/Quality Splits for Research Foundry Run Telemetry

## 1. Deferred Item Summary

**Item ID**: DF-001 (PRD §12, row 1 — "Per-provider cost/quality splits")
**Parent feature**: `research-foundry-run-telemetry-v1` (Tier 3, 26 pts)
**Corresponds to**: Research Foundry (RF) spec §16.2 dashboard panels #2 and #8 (both
"by provider" breakdowns)
**Current status**: Deferred (PRD decision D7, locked; scoped out at PRD authoring time,
2026-07-21)

Research Foundry's `emit_ccdash_event()` (RF spec §16, `execution_event`) is a
schema-validated, run-level telemetry event. It carries aggregate cost, useful-source
count, duplicate/extraction-failure rates, and latency for the run **as a whole**, plus a
`selected_providers` field that is a **list** of provider identifiers (e.g.
`[exa, brave, jina]`). It does **not** carry a per-provider breakdown of any of those
metrics — there is no `cost_by_provider`, `useful_sources_by_provider`, or
`citation_coverage_by_provider` structure anywhere in the event schema.

Because of this, the "Provider Economics" tab shipped in this feature's Phase 3 renders
its 4 panels at the **per-mode** and **per-run** grain (KPI strip, cost & quality by
*mode*, spend/volume trend, run-level drill table) — never per-provider. A user who wants
to know "is exa worth more than brave per useful source?" cannot answer that question from
the v1 tab; they can only compare search *modes* (e.g. `broad` vs. `deep`), which conflate
whichever providers happened to be selected for a given run.

## 2. Why It Is Deferred

### 2.1 Not Computable From the Ingested Event Alone

`rf_events`/`research_runs` (this feature's two new tables) are derived entirely from RF's
`ccdash_event` payload. The event's `selected_providers` list has no accompanying per-item
metrics — it is provider *identity*, not provider *attribution*. There is no way to
compute a per-provider split from data this feature ingests; the gap is a payload-shape
limitation, not a query or aggregation limitation on the CCDash side.

### 2.2 Confirmed at PRD Authoring Time, Not a Post-Hoc Discovery

This gap was identified during PRD authoring (decision D7, locked) by direct inspection of
RF's event schema and search-router source (RF spec §16, `router.py:363-378`), not
discovered mid-implementation. It is a Contract Reality named deferral (PRD §7 "Out of
Scope"), not a silent gap.

### 2.3 Two Independent Unblock Paths Exist, Neither Chosen Yet

Unlike a single missing field, this gap has **two structurally different unblock paths**
(§3 below) with meaningfully different implementation cost and ownership. Committing to
one now, before either RF's schema roadmap or CCDash's appetite for ingesting a second RF
entity (`source_cards`) is known, would be premature design work. This is exactly the
`maturity: idea` case per the DOC-006 checklist — direction is not yet known.

### 2.4 Phase Scope

Phase 4 of this feature is hardening + docs + deferred-item specs, not new ingest/entity
work. Per PRD decision D7, per-provider attribution is explicitly out of scope for v1;
implementing either unblock path is a follow-up feature.

## 3. Unblock Condition

**Promote this item (author an implementation plan; change `status: draft` →
`status: active` or equivalent) when either of the following becomes true:**

### Path A — RF emits per-provider splits in a future event schema version

Research Foundry adds a per-provider metrics structure to `ccdash_event` (e.g.
`provider_metrics: [{provider, cost_usd, useful_sources, citation_coverage, ...}]`) in a
future schema version. Because RF's schema is `additionalProperties: true` (tolerant of
CCDash-side additions) and this feature's ingest route persists the raw event payload in
`rf_events` before deriving `research_runs`, CCDash can add the new field to its rollup
derivation without a breaking schema change on the ingest side — only `research_runs`
(or a new child table) needs a corresponding dual-DDL column/table addition.

**Trigger signal**: RF's `schemas/ccdash_event.schema.yaml` gains a per-provider field, and
RF's `telemetry.py:emit_ccdash_event()` (currently `c3a2545`) populates it.

**Relative cost if chosen**: Low. No new ingest transport or entity; extends the existing
`rf_events` → `research_runs` derivation with new columns and re-derives the "by provider"
panel from data already flowing through the pipe.

### Path B — CCDash ingests RF's `source_cards` as a second entity and joins

RF spec §11.3 defines a `source_card` entity per discovered/scored source within a search
run, which is expected to carry provider identity (and, per RF's own §16.2 panel
definitions, presumably per-source cost/quality signal — see Open Question 3 below,
unconfirmed as of this writing). CCDash would need a **new ingest path** (or an extension
of the existing `rf-events` route) plus a new dual-DDL `source_cards` table, correlated to
`research_runs` by `run_id`, then a `GROUP BY provider` aggregation to derive the
per-provider split at query time in `run_intelligence.py`.

**Trigger signal**: A follow-up PRD/exploration confirms `source_card` carries the
necessary cost/quality attribution (not just identity), and a decision is made to ingest
it as a second entity (this is the same "requires ingesting source_card as a second
entity" language used for DF-002 and DF-003, PRD §12 rows 2–3 — all three items share this
same unblock condition and would likely be promoted together).

**Relative cost if chosen**: Medium-High. New ingest route or route extension, new
dual-DDL table + parity test, new correlation join, new query-service aggregation, likely
bundled with DF-002 (useful-source-rate-by-domain) and DF-003
(extraction-failure-rate-by-extractor) since all three depend on the same `source_cards`
ingestion decision.

## 4. Investigation Scope If Promoted

Regardless of which path triggers promotion, before implementation begins:

### 4.1 Confirm the Data Shape

- If Path A: obtain RF's updated `ccdash_event.schema.yaml` and confirm the per-provider
  field's exact shape (array vs. map keyed by provider; which metrics are attributed).
- If Path B: obtain RF's `source_card` schema (RF spec §11.3) and confirm which fields
  exist today — provider identity is expected, but per-source cost attribution is
  unconfirmed (Open Question 3).

### 4.2 Dual-DDL and Correlation Design (Path B only)

- Design the `source_cards` table (raw, append-only, dual SQLite+Postgres DDL) following
  the same `rf_events` v1 precedent (this feature's Phase 1).
- Design the `source_cards` → `research_runs` correlation key (expected: `run_id` foreign
  key, matching the same UUID-minting rule this feature applies to `research_runs`).
- Apply the same D-001 dedup discipline (PRD decision D5) to any per-provider rollup that
  sums across runs or sessions — this is the same one-to-many shape risk.

### 4.3 Panel Redesign

- Extend or add a panel to the "Provider Economics" tab (`components/Analytics/AnalyticsDashboard.tsx`)
  for the per-provider breakdown, reusing the existing `MetricCard`/dense-table patterns.
- Confirm resilience for providers with partial data (a provider selected but with no
  attributable cost renders as an explicit "—", never `$0.00`).

### 4.4 Relevant File Anchors

| Surface | Location |
|---------|----------|
| RF event schema | `research-foundry/schemas/ccdash_event.schema.yaml` |
| RF search router (provider selection) | `research-foundry/src/research_foundry/services/search_router/router.py:363-378` |
| RF telemetry emission | `research-foundry/src/research_foundry/services/telemetry.py:132-258` |
| RF `source_card` entity spec | `research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md` §11.3 |
| CCDash ingest route (this feature) | `backend/routers/ingest.py` (`/api/v1/ingest/rf-events`) |
| CCDash raw event table (this feature) | `backend/db/sqlite_migrations.py` / `backend/db/postgres_migrations.py` (`rf_events`) |
| CCDash rollup query service (this feature) | `backend/application/services/agent_queries/run_intelligence.py` |
| Provider Economics tab (this feature) | `components/Analytics/AnalyticsDashboard.tsx` |
| D-001 dedup precedent | `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` |

## 5. Acceptance Criteria (Placeholder — for use when promoted)

```yaml
AC-DF001-1:
  description: >
    A "cost & quality by provider" breakdown is queryable via run_intelligence.py and
    renders in the Provider Economics tab, sourced from whichever unblock path (A or B)
    was implemented.
  verified_by:
    - backend/tests/test_run_intelligence.py  # new: per-provider aggregation test
    - Runtime smoke: Provider Economics tab renders the new panel with seeded fixtures

AC-DF001-2:
  description: >
    If Path B (source_cards join) was chosen, no run-or-session cost double-counts across
    a per-provider rollup (D-001 Option A dedup discipline applied).
  verified_by:
    - backend/tests/test_run_intelligence.py  # D-001-shape regression test, per-provider variant

AC-DF001-3:
  description: >
    A provider with zero attributable cost/quality data renders as an explicit "—" per
    metric, never $0.00/NaN/0% masquerading as "no cost incurred."
  verified_by:
    - Runtime smoke: seeded fixture with a partial-data provider
```

## 6. Notes on Bundling

DF-002 (useful-source-rate-by-domain) and DF-003 (extraction-failure-rate-by-extractor) —
the two other PRD §12 deferred items whose unblock condition is "the same `source_cards`
join as above" — should be evaluated together with this item if Path B is ever pursued.
A single follow-up exploration/PRD covering all three `source_cards`-dependent panels is
likely more efficient than three separate follow-up features, since they share the same
new ingest transport, table, and correlation design. Path A (RF schema addition) is
specific to this item alone and does not bundle with DF-002/DF-003.

---

*Deferred under `research-foundry-run-telemetry-v1`, Phase 4, Task T4-001. See PRD §12
"Deferred Items" table, row 1, for the original deferral record.*
