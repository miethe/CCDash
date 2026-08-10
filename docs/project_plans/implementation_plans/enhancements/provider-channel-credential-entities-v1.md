---
it_schema: 1
feature_slug: provider-channel-credential-entities
title: "Provider, Channel & Credential Entities — implementation plan"
doc_type: implementation_plan
schema_version: 2
status: draft
tier: 3
priority: medium
effort_estimate: "17 pts"
risk_level: medium
context_class: C3
owner: nick
changelog_required: true
created: 2026-08-10
updated: 2026-08-10
prd_ref: docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
plan_ref: null
itt_node_id: node_01KZKZC504A3G77J6Y5VGNEDNA
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
deferred_items_spec_refs: []
findings_doc_ref: null
required_artifacts: []
related_documents:
  - docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
acceptance_criteria:
  - "AC1: Provider, channel and credential exist as addressable dimensions with their own identity, so a question can be asked of a key or a channel without aggregating a session query."
  - "AC2: The existing providerVendor/providerSurface/providerChannel axes are promoted, not duplicated — no parallel vocabulary."
  - "AC3: Cumulative and periodic spend/token/session counts are readable per credential across projects, surviving key rotation as a continuous series."
  - "AC4: The decision on whether correlation lives in CCDash or elsewhere is recorded with its reason, not left implicit."
open_questions:
  - "Manual-declare vs inferred rotation lineage (PRD OQ1) — this plan assumes manual declare; revisit if that assumption proves wrong."
  - "Rollup debug escape hatch for unattributed spend (PRD OQ2) — left to M3 implementation judgment."
  - "Lazy vs eager dimension backfill (PRD OQ3) — M1 assumes eager, one-time migration-time backfill."
decisions:
  - decision: "ADR-019 records CCDash as the correlation home for these rollups; accepted by Nick 2026-08-10."
    rationale: "CCDash already owns the session fact table, the only per-session spend readings that exist anywhere, and the DB-authoritative cross-project registry (ADR-006) AC3's join requires — see PRD §AC4 Decision."
    status: accepted
routing_constraints:
  - "Rotation-lineage continuity logic (M2) MUST stay claude-primary — a wrong lineage join silently fabricates a continuous series"
  - "Spend-attribution exclusion arithmetic (M3) MUST stay claude-primary — the never-silently-divided invariant is the feature's correctness core"
  - "Dual SQLite+Postgres DDL authoring (M1) MUST stay claude-primary — single-backend DDL is the project's recurring parity defect"
  - "Backfill script mechanics, DTO/types.ts mirroring, and test scaffolding are offload-eligible"
  - "Capability bar: M1/M2 require a model that holds both migration files plus the parity allowlist simultaneously; M3 requires reasoning over a closed-vocabulary precedence chain"
wave_plan:
  waves: [["M1"], ["M2"], ["M3"]]
  phases:
    - id: M1
      title: "Dimensions exist and are populated"
      depends_on: []
      exit_criteria: ["Named query returns a dimension row for a known providerId; both backends carry identical columns; parity check passes; backfill row count == distinct providerId count over sessions"]
      gate_lens: [security, validator]
      gate_lens_reason: irreversible-outward
    - id: M2
      title: "Credential is an entity with rotation continuity"
      depends_on: ["M1"]
      exit_criteria: ["Declared rotation A→B reads back as one continuous series; a non-ICA-channel credential row is creatable; no secret-shaped value can be persisted"]
      gate_lens: [security, validator]
      gate_lens_reason: authz-boundary
    - id: M3
      title: "Per-credential rollup readable cross-project"
      depends_on: ["M2"]
      exit_criteria: ["Seeded multi-verdict fixture returns the correct excluded count and an attributed-only spend total across >=2 projects; unknown attribution token does not raise"]
      gate_lens: [validator]
---

# Implementation Plan — Provider, Channel & Credential Entities

Provider/channel/credential are today derived attributes on a session row. When done, they are persisted, addressable entities — a caller asks a credential or channel a question directly, a rotation reads as one series, and the correlation-home question (ADR-019) is answered on the record rather than settled implicitly by whatever gets built first.

## Scope boundary

**In:** provider/channel/credential dimension tables (dual DDL); the `providerId` slug promoted as the dimension key; credential rows keyed `(channel, credential_name)` with a rotation-lineage pointer; a cross-project per-credential rollup service + REST + capability advertisement; ADR-019; backfill from existing `sessions`.

**Out (stated, not dropped):** FE/UI surfacing (sibling node `node_01KZP4DXZ2V7M6Q4KWWTF86J4Y`); budgets/headroom (a follow-on feature); provider reliability records (no capture path exists); changing `derive_provider_identity`'s derivation logic (its output is promoted as-is, per AC2).

## Rubric — what "good" looks like

One vocabulary, not two: the dimension key IS the existing `providerId` slug, never re-minted. Rotation lineage is explicit and declared, never inferred from an activity gap — inference risks false continuity, worse than no lineage at all. A spend rollup that sums over a `NULL` delta or hides its excluded-session count is a regression, not a simplification. Dual-backend parity is verified in the same change set that adds the column, not a follow-up PR.

## Named risks

- **AC3 isn't demonstrable on live data yet.** Launcher activation (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`) is unshipped — `sessions.ica_key` is NULL on every row until it lands, so every per-credential series is empty today. M3's AC is evidenced against a seeded fixture; do not close M3 on an empty live series. Shipping the launcher hooks first is cheap and makes the AC real.
- **Parallel-vocabulary drift (the AC2 failure mode).** A second naming scheme for provider/channel/credential is worse than no dimension at all. The dimension key IS `providerId`; `lib/providerIdentity.ts:26-38` is the FE mirror — any axis change stays a two-file change.
- **Single-backend DDL.** Recurring defect class in this repo; mitigated by the parity check being an M1 exit criterion, not a review courtesy.
- **Silent spend division.** `decide_attribution` (`backend/parsers/ica_spend.py:121`) already stores `NULL` rather than dividing — a *structural* guarantee shipped in v51. M3's exclusion+count AC must not undo it.

## References

- PRD (narrative AC, ground truth): `docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md`
- `backend/model_identity.py:209,217-222` — `derive_provider_identity`, the single derivation path
- `lib/providerIdentity.ts:26-38` — FE mirror of the provider axes
- `backend/parsers/ica_spend.py:121` — `decide_attribution`, the never-silently-divided invariant
- `backend/db/sqlite_migrations.py:1050-1069` — `pricing_catalog_entries`, nearest dimension-table pattern
- `system_metrics.py:339,435` — cross-project rollup pattern (ADR-006); adjacent open defect `node_01KZEXSPEKDRCSY3FGEVZPEWMV` (credentials logged in URLs/error bodies) — M2 must not regress it

## Milestones

### M1 — The dimensions exist and are populated

**Mode-D precondition (blocking):** this milestone contains a schema migration — execution halts for explicit human approval before the DDL runs; this is a precondition of starting M1, not a footnote. Provider + channel rows are keyed on the already-derived `providerId` slug — registering the existing vocabulary, never minting a new one. Dual DDL lands in `sqlite_migrations.py` and `postgres_migrations.py` in the same change, `SCHEMA_VERSION` 51→52, plus a `COLUMN_PARITY_DRIFT_ALLOWLIST` entry, following the `pricing_catalog_entries` shape. Dimension rows are backfilled from existing sessions.

**AC:** a named query returns a dimension row for a known `providerId`; both backends carry identical columns; the parity check passes; backfill row count equals the distinct `providerId` count over `sessions`.

### M2 — A credential is an entity with continuity across rotation

Credential rows are keyed `(channel, credential_name)` — deliberately not ICA-specific, so subscription seats and API keys are representable. `credential_name` is the key NAME only; no secret material enters any table, log, or response (the v51 invariant, inherited). A lineage/supersedes pointer between credential rows is the feature's one genuinely algorithmic piece — what makes a rotation read as one continuous series instead of two disjoint ones. Must not regress the adjacent open defect `node_01KZEXSPEKDRCSY3FGEVZPEWMV`.

**AC:** a rotation scenario (key A superseded by key B) reads back as one continuous series; a credential row for a non-ICA channel is creatable; a test asserts no secret-shaped value can be persisted.

### M3 — The per-credential rollup is readable across projects

Context class here is C2, not the plan's dominant C3 — a bounded, single-service read surface, not a migration or a lineage algorithm. A new service module in `backend/application/services/agent_queries/` follows the cross-project pattern (`ports.workspace_registry.list_projects()`, ADR-006, `@memoized_query`), wired to a REST endpoint and a capability string, transport-neutral first. Spend sums MUST exclude sessions whose `ica_spend_attribution != 'attributed'` and MUST report the excluded count alongside the total; token and session counts are NOT subject to this exclusion — only spend is.

**AC:** a seeded fixture with a mix of attribution verdicts returns the correct excluded count and a spend total over only `attributed` rows; the rollup spans >=2 projects; an unknown attribution token does not raise.

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| AC1 | `backend/.venv/bin/python -m pytest backend/tests/ -k "provider_dimension or channel_dimension or credential_dimension" -v` | Dimension row exists for a known `providerId`/channel/credential, addressable without a session aggregation. |
| AC2 | `git grep -n "_PROVIDER_VENDOR_TOKENS\|_PROVIDER_SURFACE_LABELS\|_provider_channel" -- backend/ \| grep -v model_identity.py` | No hits outside `model_identity.py` — no parallel vocabulary introduced. |
| AC3 | `backend/.venv/bin/python -m pytest backend/tests/ -k "credential_rotation" -v` | Positive: declared CC3→CC4 rotation yields one series. Negative: two undeclared credentials do not merge. |
| AC4 | `test -f docs/project_plans/adrs/adr-019-provider-correlation-home-ccdash.md && grep -q 'status: "accepted"' docs/project_plans/adrs/adr-019-provider-correlation-home-ccdash.md` | **MET 2026-08-10** — ADR-019 exists with decision + rationale, `status: accepted`. |

## Sequencing

M1 → M2 → M3, and the ADR precedes all three. M2's credential rows carry a foreign reference to M1's channel dimension. M3 aggregates over M2's credential identity. The ADR precedes the DDL because the correlation-home decision determines whether these tables belong in CCDash at all — building the schema first would settle AC4 implicitly, which AC4 forbids. **The ADR has now landed (accepted 2026-08-10), so that precondition is satisfied — only M1's Mode-D migration approval remains.**

## Execution ledger

Deviations are logged with rationale to `.claude/worknotes/provider-channel-credential-entities/implementation-notes.md`, reviewed at each milestone boundary rather than halting on them. Blockers still stop; beyond those, mid-milestone halts are only for destructive action, real scope change, or input only the operator has. Mode-D boundaries are non-negotiable — M1's schema migration halts for explicit human approval, per its precondition above.
