---
schema_version: 2
doc_type: report
report_category: adr
title: "ADR: Research Foundry Run Telemetry — Transport & Correlation"
status: proposed
created: 2026-07-20
updated: 2026-07-20
feature_slug: research-foundry-run-telemetry
exploration_charter_ref: docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
related_documents:
- docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-feasibility-brief.md
- docs/project_plans/exploration/research-foundry-run-telemetry/rf-transport-handoff-addendum.md
---

# ADR (Proposed): Research Foundry Run Telemetry — Transport & Correlation

**Status**: proposed (drafted during pre-commitment exploration; acceptance at the go/no-go verdict, not at implementation).

## Context

Research Foundry (RF) emits a schema-validated per-run `ccdash_event` today (`emit_ccdash_event`,
commit `c3a2545`), but writes it only to YAML inside RF's own workspace (`FoundryPaths.root/ccdash/events/*.yaml`)
with zero network/DB/OTEL egress toward CCDash ([tech-spike.md:60-100](spikes/tech-spike.md)).
CCDash has no code that reads RF's tree and no "run" entity to attach the data to
([priorart-spike.md](spikes/priorart-spike.md)). Two decisions must be fixed before planning:
**how the telemetry reaches CCDash**, and **how a run is correlated to existing sessions** — given
that RF's `intent_id`/`task_node_id`/`event_id` are non-UUID semantic slugs that cannot join
CCDash's AOS sidecar-URN graph ([risk-spike.md:40-70](spikes/risk-spike.md)).

## Decision

**1. Transport = a new `POST /api/v1/ingest/rf-events` endpoint backed by a new `rf_events` table.**
RF's `ccdash_event` is already flat and schema-validated (`additionalProperties: true`), matching a
dedicated events table almost 1:1 with no `sessions`-table pollution. The endpoint reuses the
existing NDJSON + `ingest_cursors` + dead-letter transport and workspace-token auth (ADR-008/009/014/015);
it does **not** reuse the filesystem-watcher sync-coalescing path, which is filesystem-source-scoped
and does not protect external HTTP writes ([risk-spike.md:128-147](spikes/risk-spike.md)). RF adds a
best-effort HTTP POST at the end of `emit_ccdash_event()` (companion deliverable; see handoff
addendum) and retains its local YAML mirror as durable source-of-truth for replay.

**2. Correlation = entity-link rows keyed by a UUID `run_id`; RF semantic ids are display-only.**
CCDash mints (or accepts, if RF supplies a UUID4) a genuine UUID `run_id` and links run↔session via
`backend/db/repositories/links.py` entity-link rows (`kind=research_run`), not via the AOS URN graph.
`intent_id`/`task_node_id`/`event_id` are stored as opaque string attributes for operator legibility
and downstream IntentTree cross-reference, never as SQL join keys. Any run↔session cost/workload
rollup applies D-001 dedup (`DISTINCT`/`GROUP BY` before sum) with a regression test from day one.

## Alternatives Considered

- **Filesystem-watch adapter over RF's `ccdash/events/` tree** — *fallback.* Requires no RF-side
  change, but couples CCDash to RF's on-disk workspace path on the same host, has no natural
  workspace/auth boundary, and reinvents cursor/dedup that NDJSON already solves
  ([tech-spike.md:181](spikes/tech-spike.md)). Kept as the no-RF-rework fallback only.
- **Reuse `POST /api/v1/ingest/sessions`** — *rejected.* Cheapest, but semantically wrong: pollutes
  the `sessions` table (modeled for transcripts), trips redaction/correlation logic built for
  sessions, and has no home for `metrics.providers`/`governance.*`/`reuse.*`
  ([tech-spike.md:124-159,182](spikes/tech-spike.md)).
- **OTEL export / shared DB** — *rejected.* No RF-side OTEL exists; disproportionate for coarse
  per-run cadence. Shared DB violates cross-repo DDL-ownership and layering
  ([tech-spike.md:183-184](spikes/tech-spike.md)).
- **Retrofit RF ids into `aos_correlation.py`'s UUID parser** — *rejected.* RF slugs fail
  `UUID_PATTERN`/`AOS_URN_RE` and would land as silently inert `unresolved_sidecar_row` diagnostics
  ([risk-spike.md:49-55](spikes/risk-spike.md)).

## Consequences

- **Positive**: Additive-only blast radius — new tables/service/route/link-kind/health-entry/capability,
  zero modification to `sessions`/`aos_correlation.py`/`analytics.py`/`planning_sessions.py`. Clean
  seam extensible to future non-session external telemetry producers. Fail-open coupling: if RF is
  down/absent the surface degrades to an observable stale/empty state, non-cascading.
- **Negative / cost**: Requires a (small, additive) RF-side change for the primary transport;
  introduces the precedent-free run↔session link adapter (highest-uncertainty slice, ~5 pts) and a
  standing obligation to apply D-001 dedup on every run-aware rollup. Dual-DDL parity discipline
  applies to both new tables.
- **Deferred**: Per-provider cost/quality attribution — the event carries a provider *list*, not
  per-provider splits; unblocked later by RF per-provider metric splits or a `source_cards` join
  ([value-spike.md:16-17,57-64](spikes/value-spike.md)).

## Status

proposed — accept at the exploration go/no-go verdict.
