---
title: "ADR-019: Provider/Channel/Credential Correlation Home — CCDash"
type: "adr"
status: "accepted"
created: "2026-08-10"
parent_prd: "docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md"
tags: ["adr", "provider-identity", "credentials", "cost-attribution", "entity-model"]
---

# ADR-019: Provider/Channel/Credential Correlation Home — CCDash

## Status

Accepted (2026-08-10, approved by Nick)

## Context

CCDash holds provider, channel, model and credential as session **attributes** — `providerVendor` /
`providerSurface` / `providerChannel` (derived at read time), plus the persisted `launcher`,
`model_variant`, and `ica_key` columns. Because they are attributes of a row, every question about a
provider or a key must be phrased as an aggregation over sessions. That answers "how many tokens did
ICA sessions use last week". It does not answer "what has key `CC3` cost across every session and
every project", or "which channel is carrying which classes of work".

Promoting those axes into entities with their own identity, history and rollups raises a prior
question the requester deliberately left open: **is CCDash the right home for the correlation and
analysis, or only for the ingest?** The requester's framing:

> "If CCDash is the wrong place, I think it would still at least be the right place to
> capture/ingest, regardless of if perform the correlations."

So ingest was already settled as CCDash; only the analytical home was open.

This ADR exists because the parent PRD's AC4 requires that the decision be **recorded with its
reason, not left implicit** — specifically, not settled by whichever surface happened to get built
first.

## Decision

**CCDash is the correlation home, not only the ingest home.** The provider, channel and credential
dimensions, and the cross-project rollups over them, live in CCDash.

## Decision Drivers

In order of weight:

1. **CCDash already owns the fact table.** `sessions` carries the only per-session spend readings
   that exist anywhere — `ica_spend_start` / `ica_spend_end` / `ica_spend_delta`, shipped in v51.
   No other system holds them.
2. **CCDash already owns the cross-project registry.** The DB-authoritative project registry
   (ADR-006) is precisely the join AC3's "readable per credential **across projects**" requires.
3. **Ingest is already settled here.** Siting analysis elsewhere means exporting the fact table to a
   second system and keeping two schemas in step, for no capability gain.
4. **The provider axes already have a single derivation path here.** `derive_provider_identity` at
   `backend/model_identity.py:209` is documented (L217-222) as "the single derivation path for
   provider identity in the backend". An external home would either duplicate that function or
   depend on CCDash to pre-derive — and a duplicated derivation is the parallel-vocabulary failure
   the PRD's AC2 exists to prevent.

## Alternatives Considered

### A. External warehouse / BI layer

Would be the right call if provider rollups needed to join against data CCDash does not hold —
provider billing invoices, provider-side rate-limit records. Lost because that is not the current
need, and it would require exporting the fact table plus dual schema maintenance.

**This is the alternative to revisit**, not a strawman; see Revisit Criteria below.

### B. IntentTree as the analytical home

Lost because IntentTree models the work graph, not provider telemetry — it would have to import the
session fact table wholesale to answer any of the motivating questions. Note CCDash already exposes
node↔session cost attribution *to* IntentTree via `GET /api/v1/intent-nodes/{node_id}/cost`, which is
the correct direction of that dependency: CCDash derives, IntentTree consumes.

## Consequences

**Enables**

- Provider / channel / credential dimension tables in CCDash's own schema.
- Per-credential rollups spanning projects, following the existing cross-project pattern in
  `backend/application/services/agent_queries/system_metrics.py`.
- The already-derived `providerId` slug promoted as the dimension key, rather than a second
  vocabulary for the same concepts (AC2).

**Accepts**

- CCDash's schema grows a dimension-table concern it did not previously have. Its nearest existing
  precedent is `pricing_catalog_entries` (`backend/db/sqlite_migrations.py:1050-1069`).
- Provider analytics is coupled to CCDash's availability.
- If provider-side billing data ever needs joining, **this decision is the first thing that must be
  revisited** — not worked around downstream.

## Revisit Criteria

Reopen this decision when any of the following becomes true:

1. Provider rollups need to join provider-side billing invoices or rate-limit records that CCDash
   does not capture.
2. A second consumer outside CCDash needs the same rollups, and pre-deriving inside CCDash becomes
   the bottleneck.
3. Session volume makes cross-project rollups untenable inside the cache DB.
