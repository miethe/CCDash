---
schema_version: 2
doc_type: report
title: "CCDash DB Design Remediation — Column/Constraint Parity Findings"
created: 2026-06-03
updated: 2026-06-03
status: accepted
source: T3-009
phase: P3-P4
promoted_to: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Column/Constraint Parity Findings (T3-009)

Static DDL-parsing analysis of all shared tables (SQLite + shared-Postgres,
excluding enterprise-only) produced by `get_column_parity_diff_all()` in
`backend/db/migration_governance.py`.

Type normalization, default-value normalization, and the
`timestamp_default_expression` category suppression account for all
expected cross-backend differences.  The items below are the residual
genuine drift items that cannot be collapsed by normalization.

---

## DRIFT-001 — `outbound_telemetry_queue.event_type` (column missing in SQLite baseline DDL)

**Tables affected:** `outbound_telemetry_queue`
**Columns affected:** `event_type`
**Classification:** Bootstrapping artifact (not semantic schema gap)

| Backend  | Situation |
|----------|-----------|
| SQLite   | `event_type` column is **absent** from `_TABLES` baseline DDL |
| Postgres | `event_type TEXT NOT NULL DEFAULT 'execution_outcome'` present in `_TABLES` |

**Root cause:** The SQLite `event_type` column was added later via
`_migrate_outbound_telemetry_queue_add_event_type()` — a rename-create-copy-drop
migration that also removes an FK constraint.  Postgres received it in the
initial DDL.  Both backends converge at runtime once the migration runs.

**Risk:** Low.  No functional difference at runtime; both backends have the column
after migration.

**Resolution:** Allowlisted in `COLUMN_PARITY_DRIFT_ALLOWLIST` as DRIFT-001.
No DDL change warranted — fixing the SQLite `_TABLES` baseline would conflict
with the migration guard (`if await _column_exists(...)` check).

---

## DRIFT-002 — `session_relationships.created_at` nullability

**Tables affected:** `session_relationships`
**Columns affected:** `created_at`
**Classification:** Minor nullability gap (harmless in practice)

| Backend  | Definition |
|----------|------------|
| SQLite   | `created_at TEXT NOT NULL DEFAULT (datetime('now'))` |
| Postgres | `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP` (nullable) |

**Root cause:** The Postgres DDL author omitted `NOT NULL` when writing the
`TIMESTAMP WITH TIME ZONE` column; the SQLite DDL carried `NOT NULL`.  After
type normalization both become `text` with `<timestamp_now>` default, but
nullability differs.

**Risk:** Low.  The repository layer always writes a value for `created_at`;
no NULL rows exist in practice.

**Resolution:** Allowlisted as DRIFT-002.  No DDL change: adding `NOT NULL` to
the Postgres column would require an ALTER TABLE that could fail if any NULL
rows exist from older deployments.

---

## DRIFT-003 — `oq_resolutions.created_at` and `oq_resolutions.updated_at` nullability

**Tables affected:** `oq_resolutions`
**Columns affected:** `created_at`, `updated_at`
**Classification:** Minor nullability gap (harmless in practice)

| Backend  | Definition |
|----------|------------|
| SQLite   | `created_at TEXT NOT NULL DEFAULT (datetime('now'))` |
| Postgres | `created_at TEXT DEFAULT CURRENT_TIMESTAMP::text` (nullable) |

**Root cause:** Postgres `oq_resolutions` timestamps use `TEXT DEFAULT CURRENT_TIMESTAMP::text`
without `NOT NULL`; the SQLite DDL has `NOT NULL`.  Same pattern as DRIFT-002.

**Risk:** Low.  The repository always provides values; no NULL rows expected.

**Resolution:** Allowlisted as DRIFT-003 (`created_at` and `updated_at`).

---

## DRIFT-004/005/006 — `evidence_json` NOT NULL constraint on session intelligence fact tables

**Tables affected:** `session_sentiment_facts`, `session_code_churn_facts`, `session_scope_drift_facts`
**Columns affected:** `evidence_json` on each table
**Classification:** Real structural drift (NOT NULL constraint missing in SQLite)

| Backend  | Definition |
|----------|------------|
| SQLite   | `evidence_json TEXT DEFAULT '{}'` (nullable) |
| Postgres | `evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb` (NOT NULL) |

**Root cause:** When these tables were authored, the Postgres DDL received `JSONB NOT NULL`
but the corresponding SQLite DDL was written as `TEXT DEFAULT '{}'` without `NOT NULL`.
The `json_storage` difference category already accounts for the TEXT vs JSONB type
difference, but the NOT NULL constraint mismatch is a genuine structural gap.

**Risk:** Low in practice.  The repository layer always writes a non-NULL JSON object
to `evidence_json`; no NULL values exist in production data.  However, the SQLite
schema formally permits NULL, meaning a bug in the repo layer would be accepted by
SQLite but rejected by Postgres — creating a subtle cross-backend behaviour gap.

**Fix considered:** Adding `NOT NULL` to the three SQLite `evidence_json` columns in
the `_TABLES` baseline DDL.  **Not applied** because:
1. Adding `NOT NULL` changes applied-migration semantics — existing databases with
   any NULL `evidence_json` rows (however unlikely) would need a backfill migration.
2. No migration step currently provides that backfill.

**Recommended follow-up:** Add an `ALTER TABLE ... ALTER COLUMN evidence_json SET NOT NULL`
step in the next SQLite migration version (after verifying no NULL rows exist via
`SELECT COUNT(*) FROM <table> WHERE evidence_json IS NULL`), then remove DRIFT-004/005/006
from the allowlist.

**Resolution:** Allowlisted as DRIFT-004 (`session_sentiment_facts.evidence_json`),
DRIFT-005 (`session_code_churn_facts.evidence_json`), DRIFT-006
(`session_scope_drift_facts.evidence_json`).

---

## Suppressed (not in allowlist — handled by parser normalization)

The following categories of differences are suppressed automatically by the
type-normalization and default-normalization logic in `_normalize_type()` and
`_normalize_default()`:

- **REAL / DOUBLE PRECISION → `real`**: floating_point_type category
- **INTEGER / BIGINT / SERIAL / BIGSERIAL → `integer`**: identity_column_strategy category
- **BOOLEAN → `integer`**: SQLite stores booleans as 0/1 INTEGER; both normalize to `integer`
- **JSONB / JSON → `text`**: json_storage category
- **TIMESTAMP WITH TIME ZONE / TIMESTAMPTZ → `text`**: timestamp_default_expression category
- **VARCHAR / CHARACTER VARYING / CLOB → `text`**: text alias normalization
- **datetime('now') / CURRENT_TIMESTAMP / CURRENT_TIMESTAMP::text → `<timestamp_now>`**:
  default-expression normalization; combined with the timestamp_default_expression
  suppression rule, which drops columns whose ONLY difference is nullable when both
  sides have a `<timestamp_now>` default (the canonical pattern for these columns).
- **DEFAULT FALSE / DEFAULT 0**: boolean-default normalization (`false` → `0`)

---

## P4 Addendum — Runtime Wiring & Connection Management Defects

### FINDING-P4-A — Retention Job Analytics Port Access Bug

**Component:** `backend/adapters/jobs/runtime.py`  
**Issue:** The retention job's analytics snapshot invocation attempted to access `ports.storage.analytics` as a bound method rather than a callable object. This caused runtime NameError when the job executed.

**Resolution:** Fixed in commit `3a8bef9` with regression test coverage. Port injection now properly instantiates analytics service as a dependency.

**Follow-up:** DRIFT-004/005/006 (`evidence_json` NOT NULL constraint alignment) now has a detailed design spec at `docs/project_plans/design-specs/sqlite-evidence-json-not-null-backfill.md` covering the backfill migration strategy.

---

### FINDING-P4-B — VACUUM in Transaction on Shared aiosqlite Connection

**Component:** `backend/db/connection.py` (shared async SQLite connection pool)  
**Issue:** Attempting to run `VACUUM` while a transaction was active on the shared aiosqlite connection caused SQLite to reject the operation with "database is locked" errors during background sync operations.

**Resolution:** Fixed in commit `3a8bef9` by deferring VACUUM calls to occur outside of active transactions. Regression test added to prevent re-introduction.

---

*P3 findings generated by T3-009 static DDL analysis on 2026-06-03.*  
*P4 findings appended from Phase 4 runtime remediation (T4-013, T4-014).*  
*Authoritative code: `backend/db/migration_governance.py` — `COLUMN_PARITY_DRIFT_ALLOWLIST`.*
