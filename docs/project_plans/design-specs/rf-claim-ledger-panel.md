---
schema_version: 2
doc_type: design_spec
title: "RF Claim-Ledger Panel — Design Spec"
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
  - claim-ledger
  - claims
  - new-entity
  - deferred
problem_statement: "PRD §16.2 panel #10 (\"Claims unsupported/conflicted/stale\") needs per-claim drill-down data, but RF's §16 execution_event only carries run-level aggregate claim counts — the claim ledger (§11.4) is a distinct entity this feature does not ingest."
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md
  - docs/project_plans/human-briefs/research-foundry-run-telemetry.md
  - backend/db/sqlite_migrations.py
---

# RF Claim-Ledger Panel

## Context

DF-005 covers PRD §16.2 panel #10, "Claims unsupported/conflicted/stale." This feature (Research
Foundry Run Telemetry v1) ingests RF's §16.1 `execution_event` into `rf_events` (raw log) and rolls
it up into `research_runs` (derived, one row per run). Both tables already carry **aggregate claim
counts** sourced from `execution_event.metrics.*`:

- `rf_events`: `metric_claims_total`, `metric_claims_supported`, `metric_claims_mixed`,
  `metric_claims_contradicted`, `metric_claims_inference`, `metric_claims_speculation`,
  `metric_unsupported_claims`, `metric_verification_passed`
- `research_runs`: `total_claims_total`, `total_claims_supported`, `total_claims_mixed`,
  `total_claims_contradicted`, `total_unsupported_claims` (summed across every folded-in event)

These columns are sufficient for a coarse trend widget ("N unsupported claims this run/week") but
**not** for the panel PRD §16.2 actually names — a browsable ledger of *which* claims are
unsupported, conflicted, or stale, with their evidence and conflict summaries. That requires the
individual `claim` entity from RF spec §11.4, which this feature does not ingest:

```yaml
claim:
  id: string
  text: string
  claim_type: factual|pricing|opinion|inference|recommendation|implementation_detail
  confidence: low|medium|high
  evidence:
    - source_id: string
      span_ref: string
      support_level: direct|indirect|contextual|conflicting
  conflicts:
    - source_id: string
      conflict_summary: string
  status: unsupported|partially_supported|supported|conflicted|stale
  last_verified_at: datetime
```

(Source: `research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md`
§11.4.)

Note the overlap with DF-001–DF-003: those defer on RF's `source_card` entity (§11.3), which itself
has a `key_claims` array (`claim_id`, `claim`, `evidence_span_ref`) — a *shallow reference*, not the
full claim record. A future `source_cards` ingestion (DF-001's unblock) would not, by itself,
satisfy this panel; the full `claim` entity (status, evidence list, conflicts list,
`last_verified_at`) lives only in the claim ledger.

## Why This Is Out of Scope for v1

- The claim ledger is a **distinct RF entity**, not a field on `execution_event`. The event only
  signals `output.claim_ledger_created: true|false` — a boolean, not the ledger contents.
- Ingesting it means a new table, a new (likely pull-based) sync path, and a new correlation key —
  none of which are in this PRD's P1–P3 scope (§7 Out of Scope; PRD §12 DF-005).
- This PRD's exploration charter is scoped to the telemetry event stream; RF's `/v1/claims/verify`
  and `/claim-ledgers` read surfaces (§11.4/§17 of the RF spec) are a separate integration surface.

## Follow-Up Feature Sketch

### New entity: `claims`

A new table, analogous in spirit to `rf_events`/`research_runs` but modeling RF's claim ledger
directly rather than a telemetry event:

| Column | Source | Notes |
|---|---|---|
| `claim_id` | `claim.id` | RF-issued; primary key candidate, but see Correlation below |
| `run_id` | correlation | CCDash's canonical UUID `research_runs.run_id` — **never** RF's raw run id, per D2 |
| `text` | `claim.text` | |
| `claim_type` | `claim.claim_type` | enum: factual\|pricing\|opinion\|inference\|recommendation\|implementation_detail |
| `confidence` | `claim.confidence` | enum: low\|medium\|high |
| `status` | `claim.status` | enum: unsupported\|partially_supported\|supported\|conflicted\|stale — the panel's primary filter dimension |
| `evidence_json` | `claim.evidence[]` | JSON-encoded list of `{source_id, span_ref, support_level}` |
| `conflicts_json` | `claim.conflicts[]` | JSON-encoded list of `{source_id, conflict_summary}` |
| `last_verified_at` | `claim.last_verified_at` | drives the "stale" bucket (age since last verification) |
| `rf_claim_id` | `claim.id` (display) | opaque display string, mirroring the `rf_run_id`/`intent_id` pattern already established on `rf_events`/`research_runs` |

### Correlation approach (D2-consistent)

Per this PRD's D2 (locked decision), `research_runs.run_id` is a genuine, CCDash-minted UUID and RF's
own semantic identifiers are stored as display-only attributes, never join keys against
`aos_correlation.py`. The claim ledger should follow the identical pattern:

- `claims.run_id` joins to `research_runs.run_id` (the same UUID join key already established for
  session correlation) — not RF's raw `run_id` string.
- RF's own `claim.id` is stored as `rf_claim_id`, a display-only string, exactly as `rf_run_id` is
  today.
- Zero new coupling to `aos_correlation.py` or the `UUID_RE`/`AOS_URN_RE` boundary.

### Ingest path

Two candidate directions, both viable and not mutually exclusive:

1. **Pull-based**: CCdash's worker calls RF's `/claim-ledgers` (or `/v1/claims/verify`-adjacent read
   endpoint) per completed run, keyed by RF's raw `run_id`, and upserts into `claims` — similar
   shape to a sync-engine pull rather than an event push.
2. **Push-based**: RF emits a claim-ledger-shaped event (or an event carrying the full ledger array)
   through the same `/api/v1/ingest/rf-events`-style transport this feature already builds, gated by
   its own idempotency key (`claim_id` + `run_id`, mirroring this PRD's `event_id` idempotency
   contract).

The pull-based direction is likely simpler to land first, since it does not require an RF-side
schema/transport change beyond what RF's spec already documents (§17 API surface); the push-based
direction is architecturally consistent with this feature's existing ingest pattern and would keep
claim data flowing through the same `ingest_sources[]` health/staleness surface.

### Panel shape (PRD §16.2 panel #10)

- Filterable/browsable list of claims by `status` (unsupported / partially_supported / supported /
  conflicted / stale), scoped to a `research_runs.run_id` (or aggregated across a project/time
  window).
- Per-claim drill-down: text, claim_type, confidence, evidence sources, conflict summaries,
  `last_verified_at` (age-based staleness indicator).
- The existing `total_unsupported_claims`/`total_claims_contradicted` rollup columns on
  `research_runs` remain useful as the KPI-strip summary tile that this panel expands from — no need
  to duplicate that aggregation once per-claim rows exist; the rollup can stay computed from
  `claims.status` counts instead of (or alongside) `execution_event.metrics.*`.

## Open Questions

1. Pull-based (CCDash calls RF's claim-ledger read API) vs. push-based (RF emits claim events) —
   which does RF's team prefer to build first?
2. Does a claim ever change `status` after `last_verified_at` (e.g., re-verification), and if so, is
   `claims` an append-only history table or a mutable upsert-by-`claim_id` table?
3. Should `claims` be scoped strictly to `run_id`, or can a claim be shared/reused across multiple
   runs (e.g., a claim first raised in one run and re-cited in a later run)?
4. Does the `source_cards` ingestion from DF-001 (if it lands first) change the shape of this
   entity's evidence linkage, given `claim.evidence[].source_id` and `source_card.key_claims[]`
   reference each other?

## Promotion Criteria

Promote this idea to a shaped design spec when a follow-up feature is scoped to ingest RF's `claim`
records (§11.4) as a new entity correlated to `research_runs`, per PRD §12's named unblock condition.
At minimum, promotion needs: (a) a decision on pull vs. push ingest direction (Open Question 1), and
(b) confirmation of whether DF-001's `source_cards` ingestion is a co-requisite or independent of
this entity.
