---
schema_version: 2
doc_type: design_spec
title: "SQLite evidence_json NOT NULL Backfill (DRIFT-004/005/006)"
description: >
  Design spec for closing the NOT NULL constraint gap on evidence_json in three
  SQLite session-intelligence fact tables, surfaced during P3 column-parity diff.
maturity: shaping
status: draft
created: '2026-06-03'
updated: '2026-06-03'
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
findings_ref: .claude/findings/ccdash-db-design-remediation-findings.md
related_documents:
  - backend/db/sqlite_migrations.py
  - backend/db/migration_governance.py
tags:
  - database
  - migration
  - sqlite
  - schema-drift
  - column-parity
audience: developers
---

# Design Spec: SQLite `evidence_json` NOT NULL Backfill (DRIFT-004/005/006)

## Problem

Three SQLite session-intelligence fact tables have a structural NOT NULL gap on
their `evidence_json` column relative to the Postgres DDL:

| Drift ID | Table | SQLite definition | Postgres definition |
|----------|-------|-------------------|---------------------|
| DRIFT-004 | `session_sentiment_facts` | `evidence_json TEXT DEFAULT '{}'` (nullable) | `evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb` |
| DRIFT-005 | `session_code_churn_facts` | `evidence_json TEXT DEFAULT '{}'` (nullable) | `evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb` |
| DRIFT-006 | `session_scope_drift_facts` | `evidence_json TEXT DEFAULT '{}'` (nullable) | `evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb` |

SQLite formally permits NULL in these columns; Postgres rejects it. The
repository layer always writes a non-NULL JSON object, so no NULL rows exist in
practice. However, the gap means a future repository bug would be silently
accepted by SQLite but hard-rejected by Postgres — creating a subtle
cross-backend divergence that could mask regressions during SQLite-only
development.

The P3 column-parity diff (`migration_governance.py:column_parity_diff`) raised
these items. They were allowlisted (DRIFT-004/005/006 in
`COLUMN_PARITY_DRIFT_ALLOWLIST`) under the scope-protection rule because
applying the fix requires a backfill migration that P3 did not own.

**Allowlist anchor:** `backend/db/migration_governance.py` —
`COLUMN_PARITY_DRIFT_ALLOWLIST`.

## Current State

- Allowlist entries: DRIFT-004, DRIFT-005, DRIFT-006 (see findings doc, section
  "DRIFT-004/005/006").
- No NULL rows are expected in production, but this has not been formally
  verified.
- No migration step currently applies `NOT NULL` to the three SQLite columns.
- The Postgres DDL is already correct; this spec is SQLite-only.

### Relevant File/Line Anchors

| Item | Location |
|------|----------|
| SQLite `session_sentiment_facts` DDL | `backend/db/sqlite_migrations.py` — search `session_sentiment_facts` |
| SQLite `session_code_churn_facts` DDL | `backend/db/sqlite_migrations.py` — search `session_code_churn_facts` |
| SQLite `session_scope_drift_facts` DDL | `backend/db/sqlite_migrations.py` — search `session_scope_drift_facts` |
| Allowlist definition | `backend/db/migration_governance.py` — `COLUMN_PARITY_DRIFT_ALLOWLIST` |
| Parity diff function | `backend/db/migration_governance.py` — `column_parity_diff` / `get_column_parity_diff_all` |
| Postgres DDL | `backend/db/postgres_migrations.py` — same table names |

## Proposed Direction

Add a versioned SQLite migration step that:

1. **Verifies the absence of NULL rows** for all three tables before altering
   them. If any NULL rows exist, the migration aborts with a clear error and
   populates them with `'{}'` as a backfill default before retrying.

   ```sql
   -- Pre-check (run per table)
   SELECT COUNT(*) FROM session_sentiment_facts WHERE evidence_json IS NULL;
   -- Expected: 0. If non-zero, UPDATE before proceeding.
   UPDATE session_sentiment_facts SET evidence_json = '{}' WHERE evidence_json IS NULL;
   ```

2. **Applies `NOT NULL` via recreate-and-copy** (SQLite does not support
   `ALTER COLUMN`). The standard SQLite pattern:

   ```sql
   -- Example for session_sentiment_facts (repeat for the other two tables)
   CREATE TABLE session_sentiment_facts_new (
       -- ... all columns, evidence_json TEXT NOT NULL DEFAULT '{}'
   );
   INSERT INTO session_sentiment_facts_new SELECT * FROM session_sentiment_facts;
   DROP TABLE session_sentiment_facts;
   ALTER TABLE session_sentiment_facts_new RENAME TO session_sentiment_facts;
   -- Re-create any indexes that existed on the original table.
   ```

3. **Records the migration version** in `migrations_applied` (T3-011 ledger).

4. **Removes DRIFT-004, DRIFT-005, DRIFT-006 from `COLUMN_PARITY_DRIFT_ALLOWLIST`**
   once the migration is applied and the parity test passes.

### Migration Trigger

This migration should be added as the next available integer version in the
`sqlite_migrations.py` step sequence, after P3's final step (T3-008/T3-011
work). It is safe to include in a standalone maintenance release.

## Open Questions

1. **Index recreation**: What indexes currently exist on the three fact tables?
   The migration author must introspect live schemas and re-create all indexes
   inside the recreate-copy migration to avoid silent index loss.

2. **Postgres migration step needed?** Postgres is already correct. Confirm
   via `column_parity_diff` after the SQLite migration ships that no new drift
   is introduced.

3. **Migration version assignment**: Coordinate with the next-pending migration
   step number in `sqlite_migrations.py` to avoid version gaps.

4. **Test coverage**: A new test asserting zero NULL `evidence_json` rows on a
   freshly migrated SQLite DB should be added alongside the migration step.

## Acceptance Criteria (for the implementing phase)

- [ ] `SELECT COUNT(*) FROM session_sentiment_facts WHERE evidence_json IS NULL`
  returns 0 post-migration on any test DB.
- [ ] Same for `session_code_churn_facts` and `session_scope_drift_facts`.
- [ ] SQLite schema for all three tables shows `evidence_json TEXT NOT NULL`.
- [ ] `column_parity_diff` returns no entries for DRIFT-004/005/006.
- [ ] DRIFT-004/005/006 removed from `COLUMN_PARITY_DRIFT_ALLOWLIST`.
- [ ] Migration is idempotent: running `run_migrations` twice does not error.
- [ ] All three tables retain their full row counts after migration.
