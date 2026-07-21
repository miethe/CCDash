---
schema_version: 2
doc_type: design_spec
title: "RF Useful-Source Rate by Domain"
status: draft
maturity: idea
feature_slug: research-foundry-run-telemetry
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
created: 2026-07-21
updated: 2026-07-21
category: features
tags:
  - design-spec
  - features
  - research-foundry
  - analytics
  - deferred
  - source-cards
problem_statement: "CCDash cannot compute useful-source rate by domain for Research Foundry (RF) search runs, because domain identity lives on RF's per-source `source_card.url`/`canonical_url`, not on the run-level `execution_event` this feature ingests."
---

# RF Useful-Source Rate by Domain

## Context

This is deferred item **DF-002** from the Research Foundry Run Telemetry PRD (§12) and
implementation plan (Deferred Items table). It corresponds to Provider Economics panel #3
(RF spec §16.2), which asks: "which source domains yield useful sources most often?"

RF's `execution_event` (spec §16) carries run-level aggregate metrics and a provider **list**
(e.g. `selected_providers: [exa, brave, jina]`), but no per-source detail. Domain identity —
and whether a given fetched source was ultimately judged useful — lives on RF's
`source_card.url` / `source_card.canonical_url` (RF spec §11.3), which is a distinct entity
this feature does not ingest. Without `source_cards`, CCDash has no domain dimension to group
by, so the panel cannot be built honestly against v1's `rf_events`/`research_runs` grain.

This is the same root gap and the same unblock path as **DF-001** (per-provider cost/quality
splits): both require ingesting RF's `source_card` records and joining them into the
run-scoped telemetry model. DF-001 and DF-002 should be promoted together, not independently,
since they share the ingestion dependency and the join shape.

## Shaping Direction

If/when RF's `source_cards` are ingested as a second entity (per the DF-001 unblock condition),
the useful-source-rate-by-domain panel should:

1. Join `source_cards` to the owning `research_runs` row via the run's genuine UUID `run_id`
   (the same correlation key already used for run↔session links), not RF's raw string `run_id`.
2. Derive `domain` from `source_card.canonical_url` when present, falling back to
   `source_card.url` — normalizing scheme/www but not doing full public-suffix parsing in v1.
3. Compute useful-source rate as `useful_source_count / total_source_count` grouped by domain,
   over a selectable time window (matching the existing Provider Economics KPI-strip window
   selector), with a minimum-sample-size floor to avoid noisy single-source domains dominating
   the ranking.
4. Render as a ranked table or bar panel (top N domains by useful-source rate, with raw counts
   shown alongside the rate so a 100% rate on n=1 reads differently from n=50).
5. Degrade to an explicit empty state ("no source-card data ingested yet") rather than 0%/NaN
   when `source_cards` is absent or empty for the selected window — consistent with this
   feature's resilience-by-default convention.

This spec intentionally does not commit to a `source_card` table shape or ingestion mechanism;
that is DF-001's scope to define when promoted, and this panel is additive on top of it.

## Open Questions

1. Does RF's `source_card.canonical_url` reliably resolve redirect chains, or will CCDash need
   its own normalization pass before grouping by domain?
2. Should "useful" be RF's own judgment field on `source_card` (if one exists), or does CCDash
   need to define its own usefulness heuristic from downstream signals (e.g. citation in the
   final report)?
3. What is the minimum sample size per domain before it is included in the ranked panel, and
   should that threshold be configurable?
4. Does this panel share a single `source_cards` ingest/table with DF-001 and DF-003
   (extraction-failure-rate-by-extractor), or does each deferred panel warrant its own scoped
   projection? (Likely one shared table, three read-time projections — but unconfirmed until
   promotion planning.)

## Promotion Criteria

Promote this spec — together with DF-001 and DF-003, which share the same unblock — when either:

- RF emits per-source domain and usefulness data directly on a future `execution_event` schema
  version (removing the need for a separate join), **or**
- CCDash ingests RF's `source_cards` as a second entity and can join it to `research_runs` via
  the genuine UUID `run_id` correlation key established in this feature's P2.

At that point, this spec should be re-shaped into a full implementation plan alongside DF-001
and DF-003, since all three read from the same joined `source_cards` data.
