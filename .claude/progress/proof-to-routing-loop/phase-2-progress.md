---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 2
title: Data Layer
status: completed
created: '2026-07-29'
updated: '2026-07-31'
started: 2026-07-31T00:00Z
completed: 2026-07-31T02:15Z
overall_progress: 50
completion_estimate: on-track
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- data-layer-expert
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T2-001
  description: "Design routing_rollup schema \u2014 grain key (project_id, source_skill_name,\
    \ model)"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies: []
  priority: high
  estimated_effort: 0.5h
  assigned_model: sonnet
  started: 2026-07-31T00:00Z
  completed: 2026-07-31T00:30Z
  evidence:
  - commit: fb356ce
  - note: "Design-only task (no production file per phase plan) \u2014 output recorded\
      \ as the DDL header-comment block in this file's 'Design Output \u2014 T2-001'\
      \ section below, ready for T2-002 to transcribe verbatim."
- id: T2-002
  description: "Dual DDL \u2014 CREATE TABLE in sqlite_migrations.py and postgres_migrations.py\
    \ (v43)"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T2-001
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  note: 'Dual DDL landed: routing_rollup in _TABLES bootstrap + v43 gated upgrade
    block, SCHEMA_VERSION 42->43, both files; migration_governance.py parity-clean-by-construction
    note added. Verified: fresh-DB + simulated upgrade path create the table; column_parity_diff==={};
    test_aar_reviews_repo.py 26/26 green; test_migration_governance.py green modulo
    one pre-existing unrelated failure (workspace_id drift, confirmed on HEAD via
    git stash).'
  started: 2026-07-31T00:30Z
  completed: 2026-07-31T01:15Z
  evidence:
  - commit: '5963300'
- id: T2-003
  description: "Repository \u2014 backend/db/repositories/routing_rollup.py with upsert\
    \ + reads"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T2-002
  priority: high
  estimated_effort: 1h
  assigned_model: sonnet
  note: 'routing_rollup.py repository landed: ROUTING_ROLLUP_COLUMNS (17 cols, matches
    v43 DDL exactly), natural-key upsert (project_id, source_skill_name, model) via
    retry_on_locked (ADR-007), window_start/window_end as ordinary UPDATE-in-place
    columns, Sqlite/Postgres classes with upsert/upsert_many/get_by_project/get_all/count_by_project.
    Manually smoke-verified idempotency (in-memory sqlite + run_migrations) ahead
    of T2-004''s formal direct-count test; test_aar_reviews_repo.py 26/26 still green
    (no regression).'
  started: 2026-07-31T01:15Z
  completed: 2026-07-31T01:45Z
  evidence:
  - commit: c17a1dd
- id: T2-004
  description: "Parity allowlist + direct-count test \u2014 ADR-007 write-path validation"
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - T2-003
  priority: high
  estimated_effort: 0.5h
  assigned_model: sonnet
  note: 'Landed backend/tests/test_routing_rollup_repo.py, the Phase 2 exit-gate coverage:
    migration-governance assertions (registered in both backend migration-table getters,
    not enterprise-only, column_parity_diff("routing_rollup") == {}, zero COLUMN_PARITY_DRIFT_ALLOWLIST
    entries, PRIMARY KEY pinned to (project_id, source_skill_name, model)) plus ADR-007
    direct-count assertions (SQLite + fake-asyncpg Postgres): N distinct keys -> COUNT(*)
    == N, re-upsert never duplicates and reflects the latest write, distinct grain
    keys never collapse, get_by_project/get_all/count_by_project scope correctly,
    nullable metric columns accept None.'
  started: 2026-07-31T01:45Z
  completed: 2026-07-31T02:15Z
  evidence:
  - commit: 19d5b72
parallelization:
  batch_1:
  - T2-001
  batch_2:
  - T2-002
  batch_3:
  - T2-003
  batch_4:
  - T2-004
  critical_path:
  - T2-001
  - T2-002
  - T2-003
  - T2-004
  estimated_total_time: 3h
blockers: []
success_criteria: []
files_modified:
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/migration_governance.py
- backend/db/repositories/routing_rollup.py
- backend/tests/test_routing_rollup_repo.py
progress: 100
---

# Phase 2: Data Layer

**Total Tasks**: 4  
**Estimated Effort**: 3 points  
**Key Files**: Migration files (v43), `routing_rollup.py` repository, tests

## Objective

Create the `routing_rollup` table and repository. This is an additive-only schema change with a natural grain key of `(project_id, source_skill_name, model)`. Every column is persisted except derived fields (task_class, provider).

## Implementation Notes

### Architectural Decisions

- **Additive-only DDL**: No ALTER on existing tables, no backfill — this feature creates a brand new table from scratch
- **Natural key discipline**: `(project_id, source_skill_name, model)` is the PRIMARY KEY; `window_start`/`window_end` are ordinary columns updated in place on upsert
- **Dual-DDL parity by construction**: Uses identical literal types (TEXT, INTEGER, REAL) in both SQLite and PostgreSQL to avoid drift allowlist entries
- **ADR-006/007 discipline**: Every write path wrapped in `retry_on_locked`; direct-count assertion test validates idempotency

### Patterns and Best Practices

- Clones `aar_reviews` table structure exactly, including the shared ordered-columns contract pattern
- Uses same `_ensure_column` migration pattern for schema version bumping
- Bootstrap path (in `_TABLES`) + upgrade path (version-gated block) both present for fresh and upgraded databases

### Known Gotchas

- **Version-gate ordering**: New block must follow the v42 block, before any `_ensure_index` calls
- **`_TABLES` regex sensitivity**: `_CREATE_TABLE_RE` requires trailing `;` and specific shape — off-by-one breaks silently
- **Independent SQLite connections**: New test must issue `PRAGMA busy_timeout = 30000` immediately after connecting

### Development Setup

- Knowledge of SQLite/PostgreSQL DDL syntax and type normalization
- Familiarity with `column_parity_diff()` and `migration_governance.py` patterns
- Understanding of `retry_on_locked` pattern from ADR-007

## Design Output — T2-001 (`routing_rollup` column contract)

**Status**: locked. This is a design-only task (per the phase plan: "produces no new file — its
output is the design rationale that becomes the DDL header comment block T2-002 writes directly
into `sqlite_migrations.py` / `postgres_migrations.py`"). The block below is validated against:
`backend/db/repositories/aar_reviews.py:1-32` (module-docstring style), the `aar_reviews` v42 DDL in
both migration files, `backend/application/services/agent_queries/routing_feedback_contract.py`
(T1-002 envelope constants), PRD §6.3 (row-grain resolution + literal payload example), and
`backend/db/migration_governance.py` (drift-category matrix) — ready for T2-002 to transcribe
verbatim without further design decisions.

### Grain key (locked)

`PRIMARY KEY (project_id, source_skill_name, model)` — **never** `(task_class, model)` and
**never** including `window_start`/`window_end` in the key. `task_class` is a derived/denormalized
column computed at write time via the pinned `skill_name → task_class` mapping (D3) — the router's
`validateFeedbackJoin()` needs the raw `source_skill_name` per row to independently re-verify the
mapping, so it can never be collapsed pre-emission (PRD §6.3, resolves the D2 tuple ambiguity).
`window_start`/`window_end` are ordinary UPDATE-in-place columns reflecting the *current* rolling
window — putting them in the key would turn this into an unbounded time-series log instead of a
one-row-per-key rollup (the same invariant `aar_reviews` already guarantees for
`(aar_document_id, session_id)`).

### 11-field join envelope — persisted vs. static-at-read-time

The `aos.routing.feedback` v1.0.0 envelope has 11 fields (PRD §6.3 literal example, top block).
Only 5 are persisted per-row; the other 6 are frozen constants in `routing_feedback_contract.py`
that the Phase 3 query service assembles into the full envelope at **read** time — never persisted
redundantly per-row:

| Envelope field | Persisted? | Where |
|---|---|---|
| `producer` | No | `routing_feedback_contract.PRODUCER` constant |
| `contract_id` | No | `routing_feedback_contract.CONTRACT_ID` constant |
| `contract_version` | **Yes** | `routing_rollup.contract_version` (AC-8 per-row version stamp) |
| `taxonomy_id` | No | `routing_feedback_contract.TAXONOMY_ID` constant |
| `taxonomy_version` | **Yes** | `routing_rollup.taxonomy_version` (AC-8) |
| `taxonomy_digest` | No | `routing_feedback_contract.TAXONOMY_DIGEST` constant |
| `mapping_id` | No | `routing_feedback_contract.MAPPING_ID` constant |
| `mapping_version` | **Yes** | `routing_rollup.mapping_version` (AC-8) |
| `mapping_digest` | No | `routing_feedback_contract.MAPPING_DIGEST` constant |
| `source_skill_name` | **Yes** | `routing_rollup.source_skill_name` (grain key) |
| `task_class` | **Yes** | `routing_rollup.task_class` (derived, D3) |

Rationale: digests/ids/producer never change per row and are cheap to assemble at read time; only
the three *version* strings are stamped per row (AC-8 version-mismatch resilience — a consumer
pinned to an older mapping/taxonomy/contract version can detect drift per key without re-fetching
constants). Do not add `producer`, `mapping_digest`, `taxonomy_digest`, `contract_id`,
`taxonomy_id`, or `mapping_id` as columns — this was an explicit non-goal called out in the phase
plan's T2-001 Implementation Notes.

### Full column contract (17 persisted columns + 2 audit columns = 19 total)

| # | Column | SQLite type | Postgres type | Null / Default | Category | Rationale |
|---|---|---|---|---|---|---|
| 1 | `project_id` | TEXT NOT NULL | TEXT NOT NULL | — | grain key | ADR-006: caller-supplied scoping key, never re-derived from `projects.json` |
| 2 | `source_skill_name` | TEXT NOT NULL | TEXT NOT NULL | — | grain key | raw skill name; router re-verifies mapping against this, never `task_class` |
| 3 | `model` | TEXT NOT NULL | TEXT NOT NULL | — | grain key | verbatim model string as captured (no cross-repo namespacing — DI-2 deferred) |
| 4 | `window_start` | TEXT NOT NULL | TEXT NOT NULL | ISO-8601 | metric payload (non-key) | ordinary UPDATE-in-place column; rolling-window lower bound |
| 5 | `window_end` | TEXT NOT NULL | TEXT NOT NULL | ISO-8601 | metric payload (non-key) | ordinary UPDATE-in-place column; rolling-window upper bound |
| 6 | `task_class` | TEXT NOT NULL | TEXT NOT NULL | — | derived | computed via pinned mapping at write time; never the raw `source_skill_name` string (D3) |
| 7 | `provider` | TEXT NOT NULL | TEXT NOT NULL | — | derived | via `derive_model_identity()`; read-side convenience only, never an independent key (D2) |
| 8 | `sample_count` | INTEGER NOT NULL | INTEGER NOT NULL | DEFAULT 0 | metric payload (D5) | denominator for all other metrics; drives `eligible_for_adjustment` |
| 9 | `success_rate` | REAL | REAL | nullable | metric payload (D5) | nullable — a coverage-only/`_unclassified` row may have no meaningful value |
| 10 | `cost_index` | REAL | REAL | nullable | metric payload (D5) | nullable, same rationale as `success_rate` |
| 11 | `regression_rate` | REAL | REAL | nullable | metric payload (D5) | nullable, same rationale |
| 12 | `confidence` | REAL | REAL | nullable | metric payload (D5) | nullable, same rationale |
| 13 | `eligible_for_adjustment` | INTEGER NOT NULL | INTEGER NOT NULL | DEFAULT 0 | metric payload (OQ-3) | 0/1, deliberately **not** Postgres `BOOLEAN` — identical literal type token in both dialects keeps this parity-clean by construction (BOOLEAN→"integer" is already an approved `migration_governance.py` category, but matching literal tokens needs no category check at all); `= sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`, hardcoded `false` for protected-class/`_unclassified` rows (FR-6, never overridable) |
| 14 | `freshness_ts` | TEXT NOT NULL | TEXT NOT NULL | ISO-8601 | metric payload (D5) | worker-sweep completion timestamp for this row |
| 15 | `contract_version` | TEXT NOT NULL | TEXT NOT NULL | — | AC-8 envelope | per-row stamp of `routing_feedback_contract.CONTRACT_VERSION` at write time |
| 16 | `taxonomy_version` | TEXT NOT NULL | TEXT NOT NULL | — | AC-8 envelope | per-row stamp of `TAXONOMY_VERSION` |
| 17 | `mapping_version` | TEXT NOT NULL | TEXT NOT NULL | — | AC-8 envelope | per-row stamp of `MAPPING_VERSION` |
| 18 | `created_at` | TEXT NOT NULL DEFAULT (datetime('now')) | TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP | — | audit | `aar_reviews` convention verbatim; `timestamp_default_expression` — already an approved drift category, no new allowlist entry |
| 19 | `updated_at` | TEXT NOT NULL DEFAULT (datetime('now')) | TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP | — | audit | same as `created_at` |

All timestamp-shaped columns (`window_start`, `window_end`, `freshness_ts`) use `TEXT` ISO-8601 —
matching `aar_reviews.generated_at TEXT` — rather than a native timestamp type, to avoid the
nullability-drift class documented as DRIFT-002/DRIFT-003 in `migration_governance.py`.

### Indexes (mirrors `aar_reviews`' 3-index shape)

```sql
CREATE INDEX IF NOT EXISTS idx_routing_rollup_project ON routing_rollup(project_id);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_task_class ON routing_rollup(task_class);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_skill_model ON routing_rollup(source_skill_name, model);
```

### DDL header comment block (ready for T2-002 to paste verbatim above `CREATE TABLE routing_rollup`)

```
-- ── Routing Feedback Persistence: routing_rollup (T2-00x, proof-to-routing- --
-- loop-v1 Phase 2) ─────────────────────────────────────────────────────────
-- One row per (project_id, source_skill_name, model) key, computed by the
-- deterministic RoutingRollupQueryService
-- (backend/application/services/agent_queries/routing_rollup.py, Phase 3).
-- PRIMARY KEY (project_id, source_skill_name, model) is both the natural
-- dedup key and the upsert conflict target -- window_start/window_end are
-- ORDINARY, UPDATE-in-place columns reflecting the CURRENT rolling window,
-- deliberately excluded from the key (including them would turn this into
-- an unbounded time-series log instead of a one-row-per-key rollup).
-- `task_class` is derived/denormalized at write time via the pinned
-- skill_name -> task_class mapping (D3) -- never the raw `source_skill_name`
-- string; the router's validateFeedbackJoin() needs source_skill_name intact
-- per row to independently re-verify the mapping, so rows are never
-- pre-merged by task_class before emission (PRD Sec.6.3). `provider` is
-- derived via derive_model_identity() -- read-side convenience only, never
-- an independently keyed dimension (D2). `contract_version`/
-- `taxonomy_version`/`mapping_version` are per-row AC-8 stamps of the
-- routing_feedback_contract.py constants at write time; `producer`/
-- `contract_id`/`taxonomy_id`/`taxonomy_digest`/`mapping_id`/`mapping_digest`
-- are NOT persisted -- they are static and assembled at read time from the
-- same module. `eligible_for_adjustment` is INTEGER 0/1 (not BOOLEAN) to
-- keep the literal type token identical across dialects by construction.
```

### AC checklist (T2-001, all satisfied)

- [x] Grain documented as `(project_id, source_skill_name, model)`, never `(task_class, model)`,
  and `window_start`/`window_end` documented as ordinary (non-key) columns
- [x] `task_class` documented as derived/denormalized, never the raw `source_skill_name` value
- [x] `provider` documented as derived via `derive_model_identity()`, never an independently keyed
  dimension
- [x] All 17 persisted columns above are named, typed, and marked nullable/NOT NULL with
  rationale, ready for T2-002 to transcribe into both DDL files without further design decisions

## Completion Notes

*Fill in when phase is complete*

- Table creation verified on both backends
- Parity test green (zero unexpected allowlist entries)
- Direct-count assertion validates write-path idempotency
