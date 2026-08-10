---
it_schema: 1
feature_slug: provider-channel-credential-entities
title: "Provider, Channel & Credential Entities — implementation plan"
doc_type: implementation_plan
schema_version: 2
status: completed
planning_maturity: draft
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
spike_ref: null
itt_node_id: node_01KZKZC504A3G77J6Y5VGNEDNA
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
source_artifact_id: srcart_01KZPASRJD8QQPQF6N97JD29PQ
deferred_items_spec_refs: []
findings_doc_ref: null
required_artifacts: []
related_documents:
  - docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
  - docs/project_plans/human-briefs/provider-channel-credential-entities.md
  - docs/project_plans/adrs/adr-019-provider-correlation-home-ccdash.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
acceptance_criteria:
  - "AC1: Provider, channel and credential exist as addressable dimensions with their own identity, so a question can be asked of a key or a channel without aggregating a session query."
  - "AC2: The existing providerVendor/providerSurface/providerChannel axes are promoted, not duplicated — no parallel vocabulary."
  - "AC3: Cumulative and periodic spend/token/session counts are readable per credential across projects, surviving key rotation as a continuous series."
  - "AC4: The decision on whether correlation lives in CCDash or elsewhere is recorded with its reason, not left implicit."
open_questions: []
decisions:
  - decision: "ADR-019 records CCDash as the correlation home; accepted, sign-off confirmed by Nick 2026-08-10. AC4 is satisfied."
    rationale: "CCDash already owns the session fact table, the only per-session spend readings that exist anywhere, and the DB-authoritative cross-project registry (ADR-006) that AC3's join requires. Briefly downgraded to `proposed` when a second planning session could not evidence the sign-off; Nick confirmed it directly and the status was restored."
    status: accepted
  - decision: "Rotation lineage is DECLARED, never inferred — an explicit action names the predecessor; the rollup trusts only the stored pointer."
    rationale: "A wrong inferred merge asserts a continuity that never happened and is invisible in the output. Operator cost is one action per rotation; rotations are rare (PRD §8). Resolves PRD OQ1."
    status: accepted
  - decision: "Dimension backfill is eager but runs as an idempotent worker/CLI job SEPARATE from the v51->v52 DDL migration — never inside it."
    rationale: "api and worker run migrations concurrently on the node; a long scan inside the migration widens that known DuplicateColumn race. DDL stays fast; the backfill is re-runnable and observable. Resolves PRD OQ3."
    status: accepted
  - decision: "The rollup excludes non-`attributed` spend by default, always reports the excluded count, and accepts `?include_unattributed=true` for debugging."
    rationale: "Keeps the default honest (NFR-1) while leaving a first-class debugging path instead of forcing a drop to raw SQL. Resolves PRD OQ2."
    status: accepted
  - decision: "Tier 3 SPIKE waived; PRD §Architectural Context plus in-repo precedent stand in."
    rationale: "No feasibility unknown survives recon: v51 is a concrete dual-DDL template and system_metrics.py a working cross-project rollup analog. The three open questions were design choices (now decided), not unknowns."
    status: accepted
routing_constraints:
  - "Dual SQLite+Postgres DDL authoring (M1) MUST stay claude-primary — single-backend DDL is this repo's recurring parity defect and half-applies on the node."
  - "Rotation-lineage continuity logic (M2) MUST stay claude-primary — a wrong lineage join silently fabricates a continuous series."
  - "Spend-attribution exclusion arithmetic (M3) MUST stay claude-primary — the never-silently-divided invariant is the feature's correctness core."
  - "Backfill job mechanics, DTO/types.ts mirroring, transport wiring, and test scaffolding are offload-eligible."
  - "Capability bar: M1/M2 require a model that holds both migration modules plus the parity allowlist at once; M3 requires reasoning over a closed-vocabulary precedence chain."
wave_plan:
  waves: [["M1"], ["M2"], ["M3"]]
  phases:
    - id: M1
      title: "Dimensions exist and are parity-clean"
      depends_on: []
      exit_criteria:
        - "SCHEMA_VERSION is 52 in both modules; the three new tables are structurally identical across backends and appear in NO COLUMN_PARITY_DRIFT_ALLOWLIST pair."
        - "Every new write path uses retry_on_locked and ships a direct-count assertion test."
      gate_lens: [security, validator]
      gate_lens_reason: irreversible-outward
    - id: M2
      title: "Credentials are entities with declared rotation continuity, and history is backfilled"
      depends_on: ["M1"]
      exit_criteria:
        - "Declared rotation A->B reads back as one continuous series; two undeclared credentials stay two series."
        - "Backfill run twice yields identical row counts; no secret-shaped value can be persisted."
      gate_lens: [security, validator]
      gate_lens_reason: authz-boundary
    - id: M3
      title: "Per-credential rollup readable cross-project"
      depends_on: ["M2"]
      exit_criteria:
        - "Seeded multi-verdict fixture returns an attributed-only spend total plus the correct excluded count across >=2 projects; unknown attribution token does not raise."
      gate_lens: [validator]
---

# Implementation Plan — Provider, Channel & Credential Entities

Provider/channel/credential are today derived attributes on a session row, so every question about
a key or a lane must be phrased as an aggregation over `sessions`. When this is done they are
persisted, addressable entities: a caller asks a credential a question directly, a rotation reads
as one series, and the correlation-home question is answered on the record.

## Scope boundary

**In:** provider/channel/credential dimension tables (dual DDL, v51 -> v52); the existing
`providerId` slug promoted as the dimension key; credential rows keyed `(channel, credential_name)`
with a declared rotation-lineage pointer; an idempotent backfill job; a cross-project
per-credential rollup service + REST + capability advertisement; ADR-019.

**Out (stated, not dropped):** FE/UI surfacing (sibling node `node_01KZP4DXZ2V7M6Q4KWWTF86J4Y`);
budgets/headroom (a follow-on feature); provider reliability records (no capture path exists);
changing `derive_provider_identity`'s logic (its output is promoted as-is, per AC2).

## Rubric — what "good" looks like

Judge this on whether a wrong answer is *possible*, not on whether the happy path works.
**One vocabulary, not two**: the dimension key IS the existing `providerId` slug, never re-minted;
a second naming scheme for the same concepts is worse than no dimension at all. **Declared, not
guessed continuity**: two credentials merge only when a stored pointer says so — absent a pointer
they stay two series, and that is the correct answer. **One choke point for attribution**: the
exclusion of non-`attributed` spend lives in exactly one place, so no future path can sum over
unattributed rows; prefer making that state unrepresentable over guarding each new call site.
Dual-backend parity is verified in the same change set that adds the table, not a follow-up PR —
and by construction, not by allowlisting.

## Named risks

- **Silent spend-sum-over-NULL.** Sharpest failure: it yields a plausible number, not an error.
  `decide_attribution` (`backend/parsers/ica_spend.py:121`) already stores NULL rather than
  dividing — a structural guarantee shipped in v51. M3's exclusion+count AC must not undo it.
  Note the scope: **only spend is excluded; token and session counts are not.**
- **Parallel-vocabulary drift (the AC2 failure mode).** `lib/providerIdentity.ts:26-38` is the FE
  mirror — any axis change stays a two-file change.
- **Single-backend DDL.** Recurring defect class here; a divergent table half-applies and
  crash-loops the node. New tables must NOT enter `COLUMN_PARITY_DRIFT_ALLOWLIST` — that allowlist
  is for known column drift on tables that already exist in both backends. The precedent is a test
  asserting no allowlist pair names the new table (`test_routing_rollup_repo.py:99-109`).
- **Migration-time concurrency.** api and worker migrate concurrently on the node — this is why
  the backfill is a separate job. Do not fold the scan back into M1.
- **First-of-shape.** No dimension table is referenced *from* `sessions` today; every existing FK
  runs the other way. `pricing_catalog_entries` (`sqlite_migrations.py:1050-1069`) is the nearest
  table shape; `tags` and `metric_types` are lookup tables but neither is consumed from `sessions`.
- **AC3 is not demonstrable on live data yet.** Launcher activation
  (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`) is unshipped, so `sessions.ica_key` is NULL on every real
  row. Evidence M3 against a seeded fixture; do not close it on an empty live series.

## References

- PRD (narrative AC, ground truth): `docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md`
- `backend/model_identity.py:115-125,160-200,209-260` — the vocabularies, `_provider_channel`, and
  `derive_provider_identity` (`providerId` composed at `:247`)
- `lib/providerIdentity.ts:26-38` — FE mirror of the provider axes
- `backend/parsers/ica_spend.py:58-68,121` — attribution vocab + `decide_attribution`
- `backend/db/sqlite_migrations.py:85` / `postgres_migrations.py:61` — `SCHEMA_VERSION`; v51 blocks
  at `sqlite:4615-4628` / `postgres:4159-4167` are the concrete template for a v52 block
- `backend/db/migration_governance.py:462,745` — `COLUMN_PARITY_DRIFT_ALLOWLIST` and its check
- `backend/application/services/agent_queries/system_metrics.py:316-345,413+` — cross-project
  rollup pattern (`@memoized_query` + `workspace_registry.list_projects()`, ADR-006)
- `backend/db/repositories/base.py:114` — `retry_on_locked`; compliant example `sessions.py:463-472`
- Adjacent open defect `node_01KZEXSPEKDRCSY3FGEVZPEWMV` (credentials logged in URLs/error bodies)
  — M2 must not regress it

## Milestones

### M1 — Dimensions exist and are parity-clean

**Mode-D precondition (blocking):** this milestone contains a schema migration — execution halts
for explicit human approval before the DDL runs. That is a precondition of starting M1, not a
footnote. Three dimension tables land in both `sqlite_migrations.py` and `postgres_migrations.py`
in the same change set, `SCHEMA_VERSION` 51 -> 52, following the `pricing_catalog_entries` shape,
keyed on the already-derived `providerId` slug — registering the existing vocabulary, never
minting a new one. Credential rows are keyed `(channel, credential_name)`, deliberately not
ICA-specific so subscription seats and API keys are representable. No rows are populated here.

**AC:** `SCHEMA_VERSION == 52` in both modules; a test asserts no `COLUMN_PARITY_DRIFT_ALLOWLIST`
pair names any of the three new tables; structural parity holds across backends; each new write
path has a direct-count assertion test (ADR-007); no column can hold secret material.

### M2 — Credentials are entities with declared rotation continuity, and history is backfilled

A declared lineage pointer between credential rows is the feature's one genuinely algorithmic
piece — what makes a rotation read as one series instead of two. It is set by an explicit action
naming the predecessor; nothing infers it. Separately, an idempotent backfill job (worker plus CLI
entry, **not** inside the migration) populates dimension rows from existing `sessions`.
`credential_name` is the key NAME only; no secret material enters any table, log, or response —
the v51 invariant, inherited, and the adjacent defect above must not regress.

**AC:** a declared rotation A->B reads back as one continuous series; two undeclared credentials do
NOT merge; backfill run twice yields identical row counts; sessions with NULL `ica_key` produce no
credential row and no error; a credential row for a non-ICA channel is creatable; a test asserts no
secret-shaped value can be persisted; an unknown channel value does not raise.

### M3 — Per-credential rollup readable cross-project

Context class here is **C2**, not the plan's dominant C3 — a bounded, single-service read surface,
not a migration or a lineage algorithm. A new module in
`backend/application/services/agent_queries/` follows the cross-project pattern
(`workspace_registry.list_projects()`, ADR-006, `@memoized_query`), transport-neutral first, then
REST plus a capability string. Spend sums MUST exclude sessions whose `ica_spend_attribution !=
'attributed'` and MUST report the excluded count alongside the total; `?include_unattributed=true`
returns them for debugging. **Token and session counts are NOT subject to this exclusion — only
spend is.**

**AC:** a seeded fixture mixing all four attribution verdicts returns a spend total over only
`attributed` rows plus the correct excluded count, across >=2 projects; `include_unattributed=true`
returns the excluded rows; an unknown attribution token does not raise; the rollup follows declared
rotation lineage; capability string advertised and consumers tolerate its absence.

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| AC1 + parity | `backend/.venv/bin/python -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_migration_governance.py backend/tests/test_postgres_migrations_upgrade.py -v` | `SCHEMA_VERSION==52` both modules; allowlist names none of the three new tables |
| AC1 writes | `backend/.venv/bin/python -m pytest backend/tests/test_migration_concurrency.py -v` plus the new dimension repo test | direct-count assertion passes after each write |
| AC2 | `git grep -n "_PROVIDER_VENDOR_TOKENS\|_PROVIDER_SURFACE_LABELS\|_provider_channel" -- backend/ \| grep -v model_identity.py` | no hits outside `model_identity.py` — no parallel vocabulary |
| AC3 rotation | new rotation test module, run by name | declared pair -> one series; undeclared pair -> two series |
| AC3 backfill | run the backfill CLI twice, compare counts | second run reports 0 inserts, identical totals |
| AC3 rollup | `backend/.venv/bin/python -m pytest backend/tests/test_agent_queries_integration.py backend/tests/test_system_metrics.py -v` plus the new rollup test | attributed-only spend, exact excluded count, >=2 projects |
| PG upgrade | `npm run docker:hosted:smoke:seeded-pg` | v51->v52 applies cleanly on a seeded PG |
| AC4 | `grep -q 'status: "accepted"' docs/project_plans/adrs/adr-019-provider-correlation-home-ccdash.md` | **MET 2026-08-10** — ADR-019 exists with decision + rationale, `status: accepted`, sign-off confirmed directly by Nick. |

> Named test modules only — unscoped `pytest` (including `pytest backend/tests/ -k ...`, which
> still collects the whole directory) hangs in this repo, and `test_runtime_bootstrap` hangs while
> a dev server is running.

## Sequencing (load-bearing)

M1 -> M2 -> M3 is a real dependency chain: M2's credential rows reference M1's channel dimension
and its backfill writes into tables M1 creates; M3 aggregates over M2's credential identity. The
one ordering constraint *inside* M1 is that both migration modules' v52 blocks land in the same
change set — a single-backend commit is exactly the drift this plan guards against.

## Deferred items (design-spec stubs authored in M3)

| Item | Source | Disposition |
|---|---|---|
| Budgets / remaining-headroom per credential | PRD §7 | Follow-on feature; stub spec |
| Provider reliability records (429 rates) | PRD §7 | Needs new capture first; separate PRD |
| Subscription-seat and API-key capture paths | PRD §8 | Schema accommodates; capture out of scope |
| Inference-assisted rotation suggestion | Decision 1 | Rejected for v1; record rationale only |
| Staged-rollout feature flag for the rollup | PRD §8 | Not needed; revisit if the read proves costly |
| Live-traffic demonstration of AC3 | PRD §8/§9 | Blocked on launcher activation node |

## Execution ledger

Deviations are logged with rationale to
`.claude/worknotes/provider-channel-credential-entities/implementation-notes.md` and reviewed at
each milestone boundary rather than halting on them. `context_class: C3` — a `karen` pass runs at
every milestone boundary in addition to the per-milestone gate lens. **Blockers still stop**, and
Mode-D is non-negotiable: M1's schema migration halts for explicit human approval.
