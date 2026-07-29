---
title: "Phase 2: Data Layer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-29
updated: 2026-07-29
feature_slug: "proof-to-routing-loop"
feature_version: "v1"
phase: 2
phase_title: "Data Layer"
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria: ["Phase 1 complete — envelope constants + flag exist"]
exit_criteria: ["Dual-DDL parity + repo tests green (ADR-006/007)"]
related_documents:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - docs/guides/aar-review-loop.md
spike_ref: null
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: null
owner: null
contributors: []
priority: medium
risk_level: medium
category: "infrastructure"
tags: [phase-plan, implementation, infrastructure, routing-feedback, data-layer]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/migration_governance.py
  - backend/db/repositories/routing_rollup.py
  - backend/tests/test_routing_rollup_repo.py
---

# Phase 2: Data Layer

**Parent Plan**: [Implementation Plan: Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~0.5–1 day (3 pts)
**Effort**: 3 story points
**Dependencies**: Phase 1 complete (envelope constants + `CCDASH_ROUTING_FEEDBACK_ENABLED` flag exist)
**Team Members**: data-layer-expert (sole subagent, all 4 tasks)

---

## Phase Overview

This phase creates one brand-new table, `routing_rollup`, and its repository. **This is an
additive-only schema change, not a Mode-D migration of existing production data.** `routing_rollup`
has zero existing rows on every database — SQLite and PostgreSQL alike — because the feature it
backs does not exist yet anywhere in the codebase before this phase runs. There is no legacy table
to reshape, no existing row to backfill or reinterpret, and no isolation/worktree concern that a
data-migrating change would carry. `isolation: shared` (per the parent plan's `wave_plan`) is
correct and deliberate: this phase is a pure `CREATE TABLE IF NOT EXISTS` + a new repository module,
exactly like the `aar_reviews` (v42) and `research_runs` (v41) tables that preceded it.

This phase is a structural clone of the shipped Automated AAR Review Loop's data layer
(`aar_reviews` table + `backend/db/repositories/aar_reviews.py`, merged `7d96c3e`). Every design
decision below mirrors that precedent's shape rather than inventing a new pattern.

### Goals

- Freeze the `routing_rollup` table's column list and natural grain key so Phase 3 (Rollup Compute
  Service) has a stable persistence contract to write against.
- Ship dual DDL (SQLite + PostgreSQL) that is structurally identical after canonical type
  normalization — zero new `COLUMN_PARITY_DRIFT_ALLOWLIST` entries, by construction, mirroring the
  `aar_reviews`/`research_runs`/`rf_events` "parity-clean by construction" precedent.
- Ship a repository (`backend/db/repositories/routing_rollup.py`) that clones `aar_reviews.py`'s
  shared-ordered-columns-contract shape, upserts on the natural grain key, and wraps every write in
  `retry_on_locked` (ADR-007).
- Prove the write path with a direct-count assertion test (ADR-007 exit-gate discipline) before
  Phase 3 is allowed to depend on this table.

### Architecture Focus

This phase implements the **Database + Repository** layers following CCDash's layered architecture:

- **Layer**: Database (dual-DDL migration) → Repository (data access).
- **Patterns**: Dual-DDL migration parity (SQLite `_TABLES` bootstrap string + version-gated upgrade
  block, mirroring the `aar_reviews` v42 precedent exactly); shared ordered-columns contract driving
  both the DDL column list and the repository's INSERT/upsert column list so the two representations
  cannot silently drift apart (ADR-007 dual-DDL parity discipline, same pattern as
  `AAR_REVIEWS_COLUMNS` / `research_runs.py` / `rf_events.py`); natural-key upsert (`ON CONFLICT`)
  rather than a surrogate autoincrement key.
- **Standards**: ADR-006 (DB-authoritative registry — `project_id` is always the caller-supplied
  scoping key, never re-derived from `projects.json`); ADR-007 (every write path wraps
  `backend.db.repositories.base.retry_on_locked`; every new write path ships a direct-count
  assertion test); independent SQLite connections issue `PRAGMA busy_timeout = 30000`.

---

## Task Breakdown

### Epic: `routing_rollup` Table + Repository

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|---------------------|-------|--------|--------------|
| T2-001 | Design `routing_rollup` schema | Design columns: natural grain key `(project_id, source_skill_name, model)` (never `(task_class, model)` — task_class is derived, per PRD §6.3); derived `task_class` column; D5 metric columns (`sample_count` int, `success_rate` real, `cost_index` real, `regression_rate` real, `confidence` real, `eligible_for_adjustment` bool/int, `window_start`/`window_end` timestamp — ordinary UPDATE-in-place columns, not part of the key, `freshness_ts` timestamp); envelope version columns (`contract_version`, `taxonomy_version`, `mapping_version`) for AC-8; derived `provider` column (never independently keyed). | Grain documented as `(project_id, source_skill_name, model)`, never `(task_class, model)` | 0.5 pts | data-layer-expert | sonnet | adaptive | Phase 1 complete |
| T2-002 | Dual DDL | `CREATE TABLE routing_rollup` in both `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py` — same column list/order in both dialects, new migration version bump. Additive-only: no ALTER of `sessions`/`aar_reviews`, no backfill. | Table created on fresh + upgrade paths; version bumped consistently in both files | 1 pt | data-layer-expert | sonnet | adaptive | T2-001 |
| T2-003 | Repository | New `backend/db/repositories/routing_rollup.py` cloning `aar_reviews.py`'s shape: shared ordered columns contract, upsert on the natural grain key, every write `retry_on_locked`-wrapped (ADR-007). Read methods: project-scoped + full-table fetch for Phase 3's query service. | Upsert idempotent (re-run on same key updates, never duplicates); all writes retry_on_locked-wrapped | 1 pt | data-layer-expert | sonnet | adaptive | T2-002 |
| T2-004 | Parity allowlist + direct-count test | Add a `COLUMN_PARITY_DRIFT_ALLOWLIST` entry ONLY if a column intentionally differs by dialect (expect none — call this out explicitly if any dialect-specific type coercion is needed). Write a direct-count assertion test (ADR-007) verifying a repository write lands exactly one row per grain key on both backends. | Zero unexplained allowlist entries; direct-count test green on both backends | 0.5 pts | data-layer-expert | sonnet | adaptive | T2-003 |
| **Total** | — | — | — | **3 pts** | — | — | — | — |

**Model Selection Guidance**: Refer to `.claude/config/multi-model.toml` for valid model values and effort policies:
- **Sonnet** (default implementation): all four tasks — schema design, dual-DDL authoring, and
  repository construction all require the moderate-reasoning tier; this phase has no
  documentation-only or mechanical-search task that would route to haiku.

**Effort Policy** (see `.claude/config/multi-model.toml`):
- **adaptive**: default reasoning for all tasks in this phase; none of the four tasks requires the
  extended/algorithmic reasoning reserved for Phase 3.

---

## Detailed Task Specifications

### Task T2-001: Design `routing_rollup` schema

**Estimate**: 0.5 points
**Assigned Subagent(s)**: data-layer-expert
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: None (Phase 1 complete is the phase-level entry criterion)
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Design the full `routing_rollup` column list and natural grain key before any DDL is written. This
is a design task: its output is the column contract (name, type, nullability, default, and — for
each — which dialect uses which literal type token) that T2-002 implements verbatim as the DDL
header comment/docstring, mirroring `aar_reviews`'s module-docstring style
(`backend/db/repositories/aar_reviews.py:1-32`) and the inline DDL comment block above the
`aar_reviews` `CREATE TABLE` in both migration files
(`backend/db/sqlite_migrations.py:1428-1444`, `backend/db/postgres_migrations.py:1442-1458`).

**Design decisions to lock**:
- **Natural grain key**: `(project_id, source_skill_name, model)` — this is the `PRIMARY KEY` and
  the upsert conflict target. It is **not** `(task_class, model)`, and it deliberately excludes
  `window_start` — `window_start`/`window_end` remain ordinary columns (still present, still
  populated) that are UPDATE-in-place on every worker sweep to reflect the current rolling window.
  Including `window_start` in the key would cause unbounded row growth (a new row every sweep
  instead of one row per key); the three-column key avoids that by construction and preserves the
  same one-row-per-key invariant the shipped `aar_reviews` table already guarantees. Per PRD §6.3,
  `task_class` is a derived, denormalized column computed at write time via the pinned
  `skill_name → task_class` mapping; the contract's `validateFeedbackJoin()` requires a singular
  `source_skill_name` per row so the router can independently re-verify each row's mapping. Any
  `task_class`-level merge across skill names happens router-side (D8, out of scope).
- **Column list** (17 persisted columns, excluding `created_at`/`updated_at`):
  `project_id`, `source_skill_name`, `model`, `window_start`, `window_end`, `task_class`,
  `provider`, `sample_count`, `success_rate`, `cost_index`, `regression_rate`, `confidence`,
  `eligible_for_adjustment`, `freshness_ts`, `contract_version`, `taxonomy_version`,
  `mapping_version`.
- **`task_class`**: `TEXT NOT NULL`, derived only — never the raw `source_skill_name` string (D3).
- **`provider`**: `TEXT NOT NULL`, derived via `derive_model_identity()` — never an independently
  keyed dimension (D2); it rides alongside `model` for read-side convenience only.
- **D5 metric payload columns**: `sample_count INTEGER NOT NULL DEFAULT 0`; `success_rate REAL`,
  `cost_index REAL`, `regression_rate REAL`, `confidence REAL` (nullable — a coverage-only or
  `_unclassified` row may not carry a meaningful value for all four); `eligible_for_adjustment
  INTEGER NOT NULL DEFAULT 0` (0/1, deliberately **not** a Postgres `BOOLEAN` — see T2-004's
  no-drift rationale); `window_start TEXT NOT NULL`, `window_end TEXT NOT NULL`, `freshness_ts TEXT
  NOT NULL` (all three ISO-8601 strings, matching the `generated_at TEXT` convention already used by
  `aar_reviews` rather than a native timestamp type, to avoid the nullability drift class documented
  as DRIFT-002/DRIFT-003 in `migration_governance.py`; `window_start`/`window_end` are ordinary,
  non-key columns updated in place on every upsert to reflect the current rolling window).
- **AC-8 version columns**: `contract_version TEXT NOT NULL`, `taxonomy_version TEXT NOT NULL`,
  `mapping_version TEXT NOT NULL` — every row is self-describing per-version so a consumer pinned to
  a different version can detect a mismatch (digests themselves are Phase 1 constants surfaced by
  the query service at read time, not persisted per-row — only the three version strings live in the
  table).
- **Audit columns**: `created_at`/`updated_at` follow the `aar_reviews` convention exactly — SQLite
  `TEXT NOT NULL DEFAULT (datetime('now'))`, Postgres `TIMESTAMP WITH TIME ZONE DEFAULT
  CURRENT_TIMESTAMP` — an already-approved `timestamp_default_expression` category, auto-suppressed
  by `column_parity_diff()`'s nullability special-case (`migration_governance.py:736-748`); this
  needs no new allowlist entry.

**Acceptance Criteria**:
- [ ] Grain documented as `(project_id, source_skill_name, model)`, never `(task_class, model)`, and
  `window_start`/`window_end` documented as ordinary (non-key) columns
- [ ] `task_class` documented as derived/denormalized, never the raw `source_skill_name` value
- [ ] `provider` documented as derived via `derive_model_identity()`, never an independently keyed
  dimension
- [ ] All 17 columns above are named, typed, and marked nullable/NOT NULL with rationale, ready for
  T2-002 to transcribe into both DDL files without further design decisions

**Implementation Notes**:
- This task produces no new file — its output is the design rationale that becomes the DDL header
  comment block T2-002 writes directly into `sqlite_migrations.py` / `postgres_migrations.py`.
- Do not invent additional columns beyond the 17 above (e.g., no `producer`, no `mapping_digest` —
  those are static constants the query service assembles into the full envelope at read time in
  Phase 3, not per-row persisted state).

**Files Involved**:
- None directly — this task's output flows into T2-002's DDL comment block.

---

### Task T2-002: Dual DDL

**Estimate**: 1 point
**Assigned Subagent(s)**: data-layer-expert
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T2-001
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Add `CREATE TABLE IF NOT EXISTS routing_rollup` (plus supporting indexes) to both
`backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`, following the exact
two-part pattern established for `aar_reviews` (v42):

1. **Bootstrap path** — append the new table's DDL to the end of the existing `_TABLES` multi-line
   string in each file (immediately after the `aar_reviews` block:
   `sqlite_migrations.py:1428-1465`, `postgres_migrations.py:1442-1479`), so a fresh database gets
   the table via `executescript(_TABLES)`.
2. **Upgrade path** — add a version-gated block inside `run_migrations()` in each file
   (`if current_version < 43:`), mirroring the `aar_reviews` v42 block verbatim
   (`sqlite_migrations.py:4249-4295`, `postgres_migrations.py:3791-3829`), so a database that is
   already at schema version ≥ 43 on first boot after this phase still gets the table (the same
   reason the `aar_reviews`/`research_runs`/`rf_events` version-gated blocks exist — a database that
   skips the `_TABLES` execute path entirely on upgrade must not skip this table).
3. **Version bump** — bump `SCHEMA_VERSION` from `42` to `43` in **both** files
   (`sqlite_migrations.py:68`, `postgres_migrations.py:46`).

**DDL (SQLite)** — column order matches T2-001's design exactly:

```sql
CREATE TABLE IF NOT EXISTS routing_rollup (
    project_id                TEXT NOT NULL,
    source_skill_name         TEXT NOT NULL,
    model                     TEXT NOT NULL,
    window_start              TEXT NOT NULL,
    window_end                TEXT NOT NULL,
    task_class                TEXT NOT NULL,
    provider                  TEXT NOT NULL,
    sample_count              INTEGER NOT NULL DEFAULT 0,
    success_rate              REAL,
    cost_index                REAL,
    regression_rate           REAL,
    confidence                REAL,
    eligible_for_adjustment   INTEGER NOT NULL DEFAULT 0,
    freshness_ts              TEXT NOT NULL,
    contract_version          TEXT NOT NULL,
    taxonomy_version          TEXT NOT NULL,
    mapping_version           TEXT NOT NULL,
    created_at                TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, source_skill_name, model)
);

CREATE INDEX IF NOT EXISTS idx_routing_rollup_project ON routing_rollup(project_id);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_task_class ON routing_rollup(task_class);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_skill_model ON routing_rollup(source_skill_name, model);
```

**DDL (PostgreSQL)** — identical column list/order/types except `created_at`/`updated_at` use
`TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP` (the same dialect substitution `aar_reviews`
already uses):

```sql
CREATE TABLE IF NOT EXISTS routing_rollup (
    project_id                 TEXT NOT NULL,
    source_skill_name          TEXT NOT NULL,
    model                      TEXT NOT NULL,
    window_start               TEXT NOT NULL,
    window_end                 TEXT NOT NULL,
    task_class                 TEXT NOT NULL,
    provider                   TEXT NOT NULL,
    sample_count               INTEGER NOT NULL DEFAULT 0,
    success_rate               REAL,
    cost_index                 REAL,
    regression_rate            REAL,
    confidence                 REAL,
    eligible_for_adjustment    INTEGER NOT NULL DEFAULT 0,
    freshness_ts               TEXT NOT NULL,
    contract_version           TEXT NOT NULL,
    taxonomy_version           TEXT NOT NULL,
    mapping_version            TEXT NOT NULL,
    created_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, source_skill_name, model)
);

CREATE INDEX IF NOT EXISTS idx_routing_rollup_project ON routing_rollup(project_id);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_task_class ON routing_rollup(task_class);
CREATE INDEX IF NOT EXISTS idx_routing_rollup_skill_model ON routing_rollup(source_skill_name, model);
```

**Acceptance Criteria**:
- [ ] `routing_rollup` is created via the `_TABLES` bootstrap path in both files (fresh-DB coverage)
- [ ] `routing_rollup` is created via a `current_version < 43` gated block in `run_migrations()` in
  both files (upgrade-path coverage), logging a completion message mirroring the v42 precedent's
  wording
- [ ] `SCHEMA_VERSION` reads `43` in both `sqlite_migrations.py` and `postgres_migrations.py`
- [ ] Column list, order, and types are byte-identical (module type aliasing aside) between the two
  DDL blocks within a single file (bootstrap vs. upgrade path) and between the two files
- [ ] No `ALTER TABLE` touches `sessions` or `aar_reviews`; no backfill statement of any kind is
  added — this phase writes only new, empty-table DDL

**Implementation Notes**:
- Follow the exact comment-block convention used at `sqlite_migrations.py:4249-4256` explaining
  *why* the version-gated block exists even though the table is also in `_TABLES` — this is a known
  gotcha class (a database already at/above the pre-bump version skips `_TABLES` entirely on
  upgrade) and the comment prevents a future editor from "simplifying" it away.
- `get_sqlite_migration_tables()` / `get_postgres_migration_tables()` discover tables via a regex
  over the `_TABLES` string (`_CREATE_TABLE_RE` in `migration_governance.py`) — the new
  `CREATE TABLE IF NOT EXISTS routing_rollup (...);` block must be well-formed enough for that regex
  to match (trailing `;` terminator, balanced parens) or the parity test in T2-004 will report the
  table as absent rather than parity-clean.

**Files Involved**:
- `backend/db/sqlite_migrations.py` - append `routing_rollup` DDL to `_TABLES`; add `current_version
  < 43` block in `run_migrations()`; bump `SCHEMA_VERSION` to `43`
- `backend/db/postgres_migrations.py` - same three edits, Postgres dialect

---

### Task T2-003: Repository

**Estimate**: 1 point
**Assigned Subagent(s)**: data-layer-expert
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T2-002
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Create `backend/db/repositories/routing_rollup.py`, cloning `backend/db/repositories/aar_reviews.py`'s
shape exactly:

- An ordered `ROUTING_ROLLUP_COLUMNS: tuple[str, ...]` module-level constant (the 17 columns from
  T2-001/T2-002, in DDL order) that drives both repositories' INSERT/upsert column lists — the same
  role `AAR_REVIEWS_COLUMNS` plays for `aar_reviews.py`.
- `_NATURAL_KEY_COLUMNS = ("project_id", "source_skill_name", "model")` and a derived
  `_UPDATE_COLUMNS` tuple (every column except the natural key — including `window_start`/
  `window_end`, which are ordinary UPDATE-in-place columns, not key columns) for the
  `ON CONFLICT ... DO UPDATE SET` clause.
- `SqliteRoutingRollupRepository` (aiosqlite-backed) and `PostgresRoutingRollupRepository`
  (asyncpg-backed) classes, each exposing:
  - `upsert(row: Mapping[str, Any]) -> None` — builds the INSERT/upsert statement from
    `ROUTING_ROLLUP_COLUMNS`, conflict target `(project_id, source_skill_name, model)`,
    wrapped in `retry_on_locked` (ADR-007), exactly like `aar_reviews.py`'s `upsert()`.
  - `upsert_many(rows: list[Mapping[str, Any]]) -> int` — loops `upsert()`, returns rows written.
  - `get_by_project(project_id: str, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]` —
    project-scoped read, for the REST/CLI transports (Phase 5) and operator debugging.
  - `get_all(*, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]` — full-table,
    cross-project read for Phase 3's `RoutingRollupQueryService` to assemble the response envelope
    (the query service, not this repository, applies any project scoping the caller's `AuthContext`
    requires).
  - `count_by_project(project_id: str) -> int`.

**One deliberate deviation from the `aar_reviews.py` clone anchor** — document this explicitly in
the module docstring: `aar_reviews.py` includes a `build_aar_review_row(dto: AARReviewDTO, ...)`
mapping helper because the AAR-document triage compute service (`aar_review.py`) already existed
before its persistence layer shipped. Here, the compute service (`RoutingRollupQueryService`) and
its DTOs (`RoutingRollupKeyDTO` / `RoutingRollupResponseDTO` in
`backend/application/services/agent_queries/models.py`) do not exist yet — they are Phase 3's
deliverable, which depends on this phase, not the other way around. `routing_rollup.py` therefore
accepts already-shaped `Mapping[str, Any]` rows keyed by `ROUTING_ROLLUP_COLUMNS` rather than a DTO
object; `ROUTING_ROLLUP_COLUMNS` (exported in `__all__`) is the explicit row-shape contract Phase 3
must satisfy when it calls `upsert()`/`upsert_many()`. Note this in the docstring so a Phase 3
implementer does not go looking for a `build_routing_rollup_row()` helper that does not exist.

**Acceptance Criteria**:
- [ ] Upsert idempotent — re-upserting the same `(project_id, source_skill_name, model)` key twice
  updates the existing row in place (including a new `window_start`/`window_end` reflecting the
  latest sweep's rolling window); direct `COUNT(*)` never increases on the second call
- [ ] All writes (`upsert`, and therefore `upsert_many`) on both `SqliteRoutingRollupRepository` and
  `PostgresRoutingRollupRepository` are wrapped in `backend.db.repositories.base.retry_on_locked`
- [ ] `ROUTING_ROLLUP_COLUMNS` is the single source of truth for both the SQLite and Postgres
  upsert's column list — no independently-typed literal column list duplicated in either class
- [ ] `get_by_project` and `get_all` both exist and are read-only (no derivation, no mutation)

**Implementation Notes**:
- Mirror `aar_reviews.py`'s `_row_values(row: Mapping[str, Any]) -> tuple[Any, ...]` helper verbatim
  (returns *row*'s values in `ROUTING_ROLLUP_COLUMNS` order) — both repository classes reuse it.
- SQLite `upsert()` uses `?` placeholders + `ON CONFLICT(...) DO UPDATE SET ...,
  updated_at = datetime('now')`; Postgres `upsert()` uses `$1..$N` placeholders + `ON CONFLICT(...)
  DO UPDATE SET ..., updated_at = CURRENT_TIMESTAMP` — same two-dialect split as `aar_reviews.py`'s
  `SqliteAarReviewsRepository.upsert()` / `PostgresAarReviewsRepository.upsert()`.
- `logger = logging.getLogger("ccdash.db.routing_rollup")`, `_REPO_NAME = "routing_rollup"` (passed
  to `retry_on_locked(..., repo=_REPO_NAME)` for consistent log correlation, matching `aar_reviews.py`).

**Files Involved**:
- `backend/db/repositories/routing_rollup.py` - new file, full repository module

---

### Task T2-004: Parity allowlist + direct-count test

**Estimate**: 0.5 points
**Assigned Subagent(s)**: data-layer-expert
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T2-003
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Verify `routing_rollup` is column-parity-clean across backends by construction, and prove the write
path with an ADR-007 direct-count assertion test.

**Parity verification (expect zero new allowlist entries)**: `column_parity_diff("routing_rollup")`
must return `{}`. This is achievable by construction because every column in T2-001/T2-002's design
uses identical literal types (after `_TYPE_NORM_MAP` normalization) in both dialects:
- All `TEXT` columns are `TEXT` in both dialects — no normalization needed.
- `sample_count` and `eligible_for_adjustment` are `INTEGER` in **both** dialects (deliberately not
  Postgres `BOOLEAN` for `eligible_for_adjustment` — using `INTEGER` on both sides sidesteps the
  `BOOLEAN → integer` collapsing rule entirely rather than relying on it, which is the most
  parity-clean choice available and needs no allowlist entry either way).
- `success_rate`, `cost_index`, `regression_rate`, `confidence` are `REAL` in **both** dialects
  (deliberately not Postgres `DOUBLE PRECISION`, which would only need the already-supported
  `floating_point_type` category but is unnecessary precision for a rollup metric — using `REAL`
  identically avoids invoking that category at all).
- `created_at`/`updated_at` use the `aar_reviews` timestamp-default pattern (SQLite `TEXT NOT NULL
  DEFAULT (datetime('now'))` vs. Postgres `TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`) —
  this is the one accepted structural difference in the table, and it is **already** suppressed by
  `column_parity_diff()`'s built-in nullability special-case
  (`migration_governance.py:736-748`), so it requires **no** new `COLUMN_PARITY_DRIFT_ALLOWLIST`
  entry, exactly as it does not for `aar_reviews`/`research_runs`/`rf_events`.

If a real, unavoidable dialect-specific type coercion is discovered during implementation, add
exactly one `(table, column)` pair to `COLUMN_PARITY_DRIFT_ALLOWLIST` with a `DRIFT-NNN`-numbered
comment (continuing the existing sequence in `migration_governance.py`) explaining the coercion and
why it is harmless — do not add a blanket or speculative entry.

**Direct-count test**: write `backend/tests/test_routing_rollup_repo.py`, cloning
`backend/tests/test_aar_reviews_repo.py`'s structure (sections 1 and 3 specifically; there is no DTO
or backfill-hook analog here, so sections 2/4/5 of that file do not apply):

1. **Migration governance section** (`unittest.TestCase`): `routing_rollup` is registered in both
   `get_sqlite_migration_tables()` and `get_postgres_migration_tables()`; is **not**
   enterprise-only; `column_parity_diff("routing_rollup") == {}`; `routing_rollup` appears in
   `get_column_parity_diff_all()` with an empty diff; zero `COLUMN_PARITY_DRIFT_ALLOWLIST` entries
   where `pair[0] == "routing_rollup"`; every name in `ROUTING_ROLLUP_COLUMNS` exists in both DDL
   column sets.
2. **ADR-007 direct-count section** (`unittest.IsolatedAsyncioTestCase`, SQLite via `aiosqlite.connect(":memory:")`
   + `PRAGMA busy_timeout = 30000` + `run_migrations(db)` + `SqliteRoutingRollupRepository(db)`):
   - Write N distinct `(project_id, source_skill_name, model)` rows (each with its own
     `window_start`/`window_end`); assert `SELECT COUNT(*) FROM routing_rollup` equals N.
   - Upsert the same natural key twice — with different metric values and a later
     `window_start`/`window_end` window — across a simulated sliding-window sequence (e.g. three
     sweeps advancing `window_start` each time); assert `COUNT(*)` stays at 1 throughout (never
     grows with the number of sweeps) and the stored row reflects the most recent write's values,
     including the updated window bounds (idempotency; this is the unbounded-row-growth regression
     this test exists to catch).
   - `upsert_many` writes every row in a batch; returned count matches `len(rows)` and matches
     `COUNT(*)`.
   - `get_by_project` scopes correctly across two distinct `project_id` values.

**Postgres write-path note**: consistent with the `aar_reviews`/`research_runs` precedent, this
phase's direct-count assertion runs against SQLite only (no `asyncpg` fixture exists in this
repo's unit-test suite for any rollup table). `PostgresRoutingRollupRepository`'s structural
correctness is covered by the parity test above (identical SQL shape, same `ROUTING_ROLLUP_COLUMNS`
contract as the SQLite class); live Postgres write-path correctness is covered by the existing
`npm run docker:hosted:smoke:seeded-pg` integration suite once all phases have landed, not by a new
per-phase unit test.

**Acceptance Criteria**:
- [ ] Zero unexplained `COLUMN_PARITY_DRIFT_ALLOWLIST` entries for `routing_rollup` (ideally zero
  entries at all; any entry added must carry a `DRIFT-NNN` comment with rationale)
- [ ] `column_parity_diff("routing_rollup") == {}`
- [ ] Direct-count test green on SQLite: N upserted rows → `COUNT(*) == N`; re-upsert of an existing
  key never increases `COUNT(*)`
- [ ] New test file runs clean as a named module: `backend/.venv/bin/python -m pytest
  backend/tests/test_routing_rollup_repo.py -v`

**Implementation Notes**:
- Run the new test file as a **named module**, not via full-suite collection — per this repo's
  known pytest-collection-hang hazard (`test_runtime_bootstrap` / `test_sse_wire_boundary` hang at
  import under some collection orders); this is a documented operational quirk of this repo, not a
  new risk introduced by this phase.
- Reuse `test_aar_reviews_repo.py`'s import list as a starting point
  (`backend.db.migration_governance`, `backend.db.sqlite_migrations.run_migrations`, `aiosqlite`) —
  drop the `AARReviewDTO`/backfill-specific imports that have no analog here.

**Files Involved**:
- `backend/db/migration_governance.py` - only if a genuine allowlist entry is needed (expected: no
  functional change, optionally a documentation comment noting `routing_rollup` is parity-clean by
  construction, mirroring the `aar_reviews` comment block at lines 507-518)
- `backend/tests/test_routing_rollup_repo.py` - new file, migration-governance + direct-count tests

---

## Quality Gates

This phase is complete when:

- [ ] **Functional**: `routing_rollup` table exists on a fresh database (via `_TABLES`) and on an
  upgraded database (via the `current_version < 43` block) in both SQLite and PostgreSQL
- [ ] **Testing**: `backend/tests/test_routing_rollup_repo.py` passes as a named module; direct-count
  assertion (ADR-007) is green; upsert idempotency is proven
- [ ] **Performance**: N/A — no live aggregation on this phase's path; indexes on `project_id`,
  `task_class`, and `(source_skill_name, model)` are present for Phase 3's read patterns
- [ ] **Security**: N/A — no new PII surface; `project_id`/`source_skill_name`/`model` are already
  exposed via existing session surfaces
- [ ] **Documentation**: DDL comment block documents the natural-key rationale and the
  derived-column (`task_class`/`provider`) invariant, mirroring `aar_reviews`'s docstring style
- [ ] **Code Quality**: `ROUTING_ROLLUP_COLUMNS` is the single source of truth for both dialects'
  column lists; no duplicated literal column list drifts from it
- [ ] **Architecture**: Additive-only DDL confirmed — zero `ALTER TABLE` on `sessions`/`aar_reviews`,
  zero backfill statements; `retry_on_locked` wraps every write (ADR-007); `SCHEMA_VERSION` bumped
  consistently (42 → 43) in both migration files
- [ ] **Column parity**: `column_parity_diff("routing_rollup") == {}`; zero unexplained
  `COLUMN_PARITY_DRIFT_ALLOWLIST` entries
- [ ] **Seam verification**: N/A — `integration_owner: null`, `seam_tasks: null`; this phase has a
  single owner specialty (data-layer-expert) and no cross-owner file overlap
- [ ] **Runtime smoke**: N/A — `ui_touched: false`; this phase has no `*.tsx` file anywhere in
  `files_affected`

---

## Integration Points

### External Systems

- None. This phase has no external system dependency — the entire deliverable is new,
  self-contained schema + repository code inside CCDash's own database layer.

### Internal Systems

- **Phase 3 (Rollup Compute Service)**: `RoutingRollupQueryService` (Phase 3) will construct rows
  shaped exactly per `ROUTING_ROLLUP_COLUMNS` and call this phase's repository `upsert`/`upsert_many`
  to persist them — Phase 3 cannot start meaningfully until this phase freezes that contract.
- **Phase 4 (Worker Sweep Job)**: `RoutingRollupSweepJob` (Phase 4) will hold a repository instance
  (via the same DI pattern `AARReviewSweepJob` uses for `SqliteAarReviewsRepository`/
  `PostgresAarReviewsRepository`) and call `upsert_many` once per sweep pass per project.
- **Phase 5 (Transport Surfaces)**: REST/MCP/CLI (Phase 5) will call `get_by_project`/`get_all` (via
  Phase 3's query service, not directly) to assemble the response envelope.
- **ADR-006 (`workspace_registry.list_projects()`)**: not called by this phase directly, but
  `project_id` is always the caller-supplied scoping key on every repository method — this phase
  never re-derives a project list from `projects.json`.
- **ADR-007 (`repositories/base.py::retry_on_locked`)**: every write path in this phase's repository
  wraps this helper — the concrete write-path discipline this phase is graded against.

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/db/sqlite_migrations.py` | ~1465 (append to `_TABLES`), ~68 (`SCHEMA_VERSION`), ~4296 (new `current_version < 43` block) | Add `routing_rollup` DDL to bootstrap + upgrade paths; bump schema version | data-layer-expert |
| `backend/db/postgres_migrations.py` | ~1479 (append to `_TABLES`), ~46 (`SCHEMA_VERSION`), ~3830 (new `current_version < 43` block) | Same three edits, Postgres dialect | data-layer-expert |
| `backend/db/migration_governance.py` | ~462-519 (docstring/allowlist comment area only, if needed) | Optional documentation note that `routing_rollup` is parity-clean by construction | data-layer-expert |
| `backend/db/repositories/routing_rollup.py` | new file, ~280-320 lines (sized like `aar_reviews.py`) | New repository: `ROUTING_ROLLUP_COLUMNS`, Sqlite/Postgres repo classes | data-layer-expert |
| `backend/tests/test_routing_rollup_repo.py` | new file, ~150-200 lines | Migration-governance + ADR-007 direct-count tests | data-layer-expert |

---

## Testing Strategy

### Unit Tests

- `backend/tests/test_routing_rollup_repo.py`:
  - Migration governance: table registration in both backend getters, not enterprise-only, zero
    column-parity diff, zero new allowlist entries, `ROUTING_ROLLUP_COLUMNS` ⊆ both DDL column sets.
  - ADR-007 direct-count + upsert idempotency against an in-memory SQLite database seeded via
    `run_migrations()`.
- Run as a named module (this repo's full-suite pytest collection is known to hang on unrelated
  files — see repo memory `ccdash-pytest-collection-hangs`):
  ```bash
  backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_repo.py -v
  ```

### Integration Tests

- Dual-DDL structural parity **is** this phase's integration test — `column_parity_diff()` and
  `get_column_parity_diff_all()` statically parse and compare both dialects' DDL text without
  requiring a live Postgres connection.
- Live Postgres write-path correctness (asyncpg round-trip) is intentionally deferred to the
  existing repo-wide `npm run docker:hosted:smoke:seeded-pg` suite once every phase of this feature
  has landed — consistent with the `aar_reviews`/`research_runs` precedent, which also has no
  per-table live-Postgres unit test.

### E2E Tests (if applicable)

- N/A for this phase. No frontend surface; no cross-transport contract yet (that is Phase 5/6's
  concern). This phase's only externally-observable behavior is "the table exists and can be
  written to and read back," which the unit tests above fully cover.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Column-parity drift silently introduced (a float/int/bool type mismatch between dialects) | Medium | Use identical literal types (`REAL`, `INTEGER`) in both dialects rather than relying on `_TYPE_NORM_MAP` collapsing; verified by `column_parity_diff("routing_rollup") == {}` in T2-004's test, which fails the build on any real drift. |
| Repository built ahead of its DTO leaves a loose row-shape contract for Phase 3 | Medium | `ROUTING_ROLLUP_COLUMNS` is exported and documented as the explicit contract; the module docstring calls out the deliberate deviation from the `aar_reviews.py` DTO-mapper pattern so Phase 3's author does not go looking for a helper that does not exist here. |
| `_TABLES` bootstrap DDL and the version-gated upgrade-path DDL drift apart within the same file | Low | Both blocks are authored from the same T2-001 design in the same task (T2-002); the existing `aar_reviews` precedent's inline comment explaining *why* both paths must exist is copied forward verbatim to keep future editors from "simplifying" one path away. |
| `SCHEMA_VERSION` bumped in one migration file but not the other | Low | T2-002's acceptance criteria explicitly require both files to read `43`; `validate_migration_governance_contract()` (existing CI check) would also surface a table-set mismatch if one dialect's bump were skipped entirely. |
| Live Postgres write-path regression not caught by this phase's own tests | Low | Structural parity (this phase's actual gate) plus the pre-existing `npm run docker:hosted:smoke:seeded-pg` suite (run later, once the full feature lands) is the established two-tier validation strategy already used for every prior rollup table in this codebase. |

---

## Success Metrics

- **Completion**: T2-001 through T2-004 all checked off; `routing_rollup` table exists in both
  `sqlite_migrations.py` and `postgres_migrations.py` at `SCHEMA_VERSION = 43`.
- **Quality**: `column_parity_diff("routing_rollup") == {}`; zero new
  `COLUMN_PARITY_DRIFT_ALLOWLIST` entries.
- **Testing**: `backend/tests/test_routing_rollup_repo.py` green; direct-count assertion proves
  N-rows-in → N-rows-persisted with idempotent upsert-on-conflict.
- **Contract clarity**: `ROUTING_ROLLUP_COLUMNS` is the single source of truth consumed identically
  by both repository classes' upsert statements — no duplicated, independently-drifting column list
  anywhere in the module.

---

## Notes

### Implementation Approach

Clone-first: every design decision in this phase traces to a specific line range in the shipped
`aar_reviews` precedent (`backend/db/repositories/aar_reviews.py`,
`backend/db/sqlite_migrations.py:1428-1465` + `:4249-4295`,
`backend/db/postgres_migrations.py:1442-1479` + `:3791-3829`). Where this phase's design
deliberately diverges (no DTO-mapper in the repository, since the DTO doesn't exist until Phase 3),
the divergence is called out explicitly in T2-003 rather than silently improvised.

### Gotchas

- **Version-gate ordering**: the `if current_version < 43:` block must be added in both files at a
  position consistent with the existing sequential version-gate blocks (after the `v42` block, before
  any always-run `_ensure_index` calls that follow it) — copy the existing structural position of the
  `aar_reviews` v42 block exactly.
- **`_TABLES` regex sensitivity**: `_CREATE_TABLE_RE` in `migration_governance.py` requires a
  trailing `;` and `CREATE TABLE IF NOT EXISTS <table> (...)` shape to match — an extra blank line or
  a missing semicolon silently drops the table from `get_sqlite_migration_tables()` /
  `get_postgres_migration_tables()`, which would make T2-004's registration assertions fail with a
  confusing "table not found" rather than a parity diff.
- **Independent SQLite connections**: the new test file's `aiosqlite.connect(":memory:")` fixture
  must issue `PRAGMA busy_timeout = 30000` immediately after connecting, per the project-wide
  invariant — omitting it will not fail this phase's fast in-memory tests but would violate the
  documented convention other write-path tests already follow.

### Learnings

_Capture as this phase progresses._

### Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
