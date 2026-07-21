---
schema_version: 2
doc_type: design_spec
title: "Research Foundry Search→Report Latency Panel - Design Spec"
status: draft
maturity: idea
feature_slug: research-foundry-run-telemetry
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
created: 2026-07-21
updated: 2026-07-21
category: features
tags: [research-foundry, telemetry, latency, analytics, deferred]
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md
  - docs/project_plans/design-specs/rf-per-provider-cost-quality-splits.md
  - docs/project_plans/design-specs/rf-useful-source-rate-by-domain.md
  - docs/project_plans/design-specs/rf-extraction-failure-rate-by-extractor.md
---

# Research Foundry Search→Report Latency Panel

## Problem Statement

RF spec §16.2 names "Search-to-report latency" as dashboard panel #6, distinct from panel #5
("Search-to-source-card latency"). The `execution_event` (RF spec §16.1, the `ccdash_event` shape
this PRD ingests) carries a single `timestamp` field and a `metrics.latency_ms` figure, but
`latency_ms` measures search-execution time — queries issued through source extraction — which
satisfies panel #5, not panel #6. There is no field on the event marking when the *report/synthesis*
stage (the human- or agent-consumable output produced from the sourced material) completed, so
CCDash cannot compute "time from search start to finished report" for any run ingested today.

Promotion trigger (from PRD §12 Deferred Items / implementation-plan row DF-004, and the phase-4
plan row DF-004 that spawned this spec): **RF adds a report-completion timestamp to a future
version of the `ccdash_event` schema** (§16.1) — the precise unblock is a new field on the event,
not a client-side computation trick, since neither endpoint of the interval (search start, report
completion) is present in the payload CCDash currently receives.

## Known Constraints

- The current `execution_event` shape (RF spec §16.1) exposes only `timestamp` (a single point in
  time, whose exact semantics — emission time vs. execution-end time — are not pinned down by the
  spec) and `metrics.latency_ms` (search-execution duration, i.e. panel #5's metric, not panel #6's).
- RF's `search_run` entity (RF spec §11.2) does carry a `created_at`/`completed_at` pair that could
  answer "how long did the whole run take," but `search_run` is RF-internal state — this PRD only
  ingests the flattened `execution_event` POST (`POST /api/v1/ingest/rf-events`), and ingesting
  `search_run` directly is out of scope (see PRD §7 Out of Scope; DF-001/DF-002/DF-003 share this
  same "would need a second RF entity" shape, though `search_run` differs from `source_cards`).
- No `search_started_at` (or equivalent) field exists on the event either — both ends of the
  interval this panel needs are absent, not just one.
- RF's example events (§16.1, §27 Appendix C) show exactly one `execution_event` per run today, not
  a start/end event pair — there is no reliable "diff two events for the same run" fallback.
- Any client-side estimate (e.g. treating the event's `timestamp` minus `metrics.latency_ms` as
  "search start," then assuming "report complete" equals the same `timestamp`) would silently
  conflate search latency with report latency, which the PRD's own resilience clause forbids:
  "Missing (never null-vs-zero-conflated) `estimated_cost_usd`, `citation_coverage`, `latency_ms`,
  or any other optional metric on an individual run renders as an explicit `—` per-cell, never
  `$0.00`/`NaN`/`0%`." A fabricated latency value would violate that same principle even more
  severely than a missing one.
- `research_runs` (this feature's derived rollup table, D6) has no column for this metric today;
  adding one now, unpopulated, would be premature schema surface for a metric CCDash cannot compute.

## Open Questions

- What exact field(s) will RF add: a single `report_completed_at`, a paired
  `search_started_at`/`report_completed_at`, or a schema-version bump that exposes
  `search_run.created_at`/`completed_at` (§11.2) directly on `ccdash_event`?
- Does "search-to-report" mean wall-clock time from search initiation to the final report being
  produced, or should it net out idle/human-review time (the event already carries
  `human_review.status: pending`, §16.1)?
- Will the new timestamp land on every `execution_event`, or only on a terminal "run complete"
  event distinct from today's per-execution shape — which would change how `research_runs` derives
  the metric (single-event upsert vs. a second event kind to correlate)?
- Once unblocked, should CCDash backfill this metric for historical `rf_events` rows retroactively
  (impossible if the field simply didn't exist at ingest time), or only compute it forward from the
  RF schema-version cutover — i.e., is a `null`/"—" floor for all pre-cutover rows acceptable
  permanently?
- Does this new field belong on `research_runs` as a plain column, or does it need its own
  intelligence-layer helper in `run_intelligence.py` (this PRD's query service) analogous to how
  cost/quality-by-mode is computed today?

## Notes

Panel #5 ("Search-to-source-card latency") is **not** the subject of this deferred item and is
already computable from the ingested event's `metrics.latency_ms` — this spec covers panel #6
only, and the distinction should stay explicit in any future implementation plan or UI copy to
avoid conflating the two.

Once RF's report-completion timestamp lands, the natural implementation shape mirrors the other
DOC-006 deferred items from this feature (DF-001–DF-003): a new nullable column on `research_runs`
(fallback to an explicit `—`, never `0`/`NaN`, for any run ingested before the RF schema-version
cutover), surfaced as a new KPI or trend panel in the existing "Provider Economics" analytics tab
(`AnalyticsDashboard.tsx`) rather than a new tab, consistent with the honest per-mode/per-run grain
this feature already established in P3.
