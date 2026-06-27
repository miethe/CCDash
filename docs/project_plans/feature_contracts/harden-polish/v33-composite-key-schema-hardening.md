---
title: "Feature Contract: v33 Composite-Key Schema Hardening"
schema_version: 2
doc_type: feature_contract
status: draft
created: 2026-06-02
updated: 2026-06-02
feature_slug: v33-composite-key-schema-hardening
category: harden-polish
estimated_points: 3
tier: 1
owner: nick
priority: high
risk_level: high
changelog_required: false
related_documents:
  - docs/project_plans/feature_contracts/harden-polish/session-child-writer-project-id.md
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Feature Contract: v33 Composite-Key Schema Hardening

> **CAPTURE ONLY — DO NOT EXECUTE without explicit user greenlight.**
>
> This contract documents a forward-only, destructive schema migration against a production SQLite cache that may reach 10 GB. Execution requires the user to explicitly authorize the sprint. The executor must not begin implementation until the user provides a clear go-ahead ("proceed with FC-2" or equivalent). No code changes, no migration files, no test runs until greenlit.

---

## 1. Goal

Author and validate a forward-only v33 SQLite migration that makes cross-project `session_id` collisions structurally impossible for `session_tool_usage` and `session_messages`, plus a one-time `project_id` backfill for orphan rows in `session_sentiment_facts`, `session_code_churn_facts`, `session_scope_drift_facts`, `session_artifacts`, and `session_logs` that were written with NULL/'' `project_id` before FC-1 landed.

---

## 2. User / Actor

- **Primary actor**: The CCDash operator running the migration against their local or hosted instance. The migration fires automatically on server startup (via `run_migrations`).
- **Secondary actor**: The CCDash development team validating migration correctness against a schema-faithful copy of the real database before promoting to production.

---

## 3. Job To Be Done

When the v31 migration extended `session_tool_usage` with a nullable `project_id` column, its PRIMARY KEY remained `(session_id, tool_name)` — a collision is possible if two projects share a `session_id` and the same tool name. Similarly, `session_messages` uses a `(session_id, message_index)` unique index. This contract promotes both to include `project_id` as the leading key component, and backfills orphan child rows so the FK invariant holds before any new writes under FC-1 create more.

---

## 4. Scope

### In Scope

**v33 SQLite migration** (`backend/db/sqlite_migrations.py`):

The migration must follow the v31 rename-create-copy-drop pattern with the exact lessons encoded in v31 (commit ec27957):

- `DROP TABLE IF EXISTS *_new` idempotency guard before each `CREATE TABLE *_new`
- Copy rows via column INTERSECTION (not a hard-coded column list) — compute the intersection of source columns and target columns using `PRAGMA table_info`, then construct `INSERT INTO new_table (col_list) SELECT col_list FROM old_table`
- Composite-PK/idempotency short-circuit at the top of the function: if the target PK is already composite, log and return immediately
- `PRAGMA foreign_keys = OFF` outside any transaction; restore to ON at the end (match the v31 pattern exactly — see `_migrate_v31_sessions_composite_pk_and_child_fks`)

**Specific schema changes:**

1. `session_tool_usage` PRIMARY KEY: `(session_id, tool_name)` → `(project_id, session_id, tool_name)`
   - Current schema: `PRIMARY KEY (session_id, tool_name)` (from `backend/db/sqlite_migrations.py` ~line 283)
   - New PK requires `project_id` to be NOT NULL for uniqueness purposes; migration must either backfill `project_id` from the parent `sessions` row before the rebuild OR accept that pre-FC-1 rows with `project_id = ''` will coalesce under the new PK (document which approach is used)

2. `session_messages` unique index: `idx_session_messages_session_message` on `(session_id, message_index)` → `(project_id, session_id, message_index)`
   - The unique index (not a PK) must be dropped and recreated with `project_id` as the leading column
   - Note: `session_messages` already has a composite FK `(project_id, session_id) REFERENCES sessions(project_id, id)` from v31; this change hardens the uniqueness constraint only

**One-time `project_id` backfill** (part of the same migration function):

For rows with `project_id IN (NULL, '')` in these tables:
- `session_sentiment_facts`
- `session_code_churn_facts`
- `session_scope_drift_facts`
- `session_artifacts`
- `session_logs`

Backfill strategy:
1. UPDATE rows by joining to `sessions` on `session_id` where the join resolves to **exactly one** `project_id` (i.e., the `session_id` appears in `sessions` for only one distinct non-empty `project_id`):
   ```sql
   UPDATE <table>
   SET project_id = (
       SELECT s.project_id
       FROM sessions s
       WHERE s.id = <table>.session_id
         AND s.project_id IS NOT NULL
         AND s.project_id != ''
       GROUP BY s.project_id
       HAVING COUNT(*) = 1
   )
   WHERE (project_id IS NULL OR project_id = '')
     AND EXISTS (
       SELECT 1 FROM sessions s
       WHERE s.id = <table>.session_id
     )
   ```
2. DELETE rows that remain with `project_id IN (NULL, '')` after the UPDATE (truly unresolvable orphans — their parent session either does not exist or appears under multiple projects):
   ```sql
   DELETE FROM <table>
   WHERE (project_id IS NULL OR project_id = '')
   ```
3. Log counts of backfilled rows and deleted orphans per table.

**Validation (pre-production):**

- The migration must be tested against a schema-faithful slim copy of the real DB (e.g., `data/ccdash_cache_test_copy.db`) that mirrors the live schema but contains a small representative data sample — never run against the live `data/ccdash_cache.db` during development
- After migration, run `PRAGMA foreign_key_check` and assert zero violations
- After migration, assert no rows with `project_id IN (NULL, '')` exist in the five backfill tables
- After migration, assert that `session_tool_usage` has no two rows sharing `(project_id, session_id, tool_name)`

**Backup recommendation (must appear in migration log output):**

The migration function must emit a `logger.warning` before beginning any destructive operation:
```
"v33 migration: recommend backing up data/ccdash_cache.db before proceeding on a production instance. Proceeding in 0s..."
```

### Out of Scope

- FC-1 writer changes (`session-child-writer-project-id`) — this contract explicitly depends on FC-1 landing first (so no new orphan rows are written during or after backfill). FC-1 must be committed and the server restarted before v33 runs in production.
- Postgres migration — no Postgres schema changes are in scope for this contract; Postgres DDL is handled separately.
- `workspace_id` scoping — the 25+ methods failing `test_workspace_scoping.py` are a separate Tier-2 ticket. That work is not covered here, not blocked by this contract, and must not be conflated with this migration.
- Any application-layer code changes (repository methods, service layer, callers) — schema and backfill only.
- Rollback mechanism — this is a forward-only migration. No down-migration path is defined.

---

## 5. UX / Behavior Requirements

This contract has no user-facing UI changes. Observable operational behavior:

- On first server startup after v33 is applied, the migration log will emit per-table counts of backfilled rows and deleted orphans.
- The backup warning will appear in the log before any destructive step.
- After v33, inserting two `session_tool_usage` rows with the same `(project_id, session_id, tool_name)` will raise a UNIQUE constraint violation (previously only `(session_id, tool_name)` was unique — project isolation is now structural).
- After v33, the `session_messages` unique index includes `project_id`, so two messages with the same `(project_id, session_id, message_index)` will be rejected.
- Session queries and reads are not affected (no column is removed; project_id was already present).

---

## 6. Data Requirements

- **Schema changes**: Two DDL changes (see Scope). Both use the rename-create-copy-drop pattern.
- **New fields**: None.
- **State changes**: Orphan child rows in five tables gain a real `project_id` (backfilled from parent) or are deleted.
- **Storage implications**: The `session_tool_usage` rebuild changes the PK; this may alter rowid ordering but not data volume. The `session_messages` index rebuild is in-place.
- **Production database size hazard**: The live `data/ccdash_cache.db` may approach 10 GB. Rebuilding `session_tool_usage` and rebuilding the `session_messages` unique index involves a full table scan and temporary table creation. On a 10 GB file, this can take minutes and requires sufficient free disk space (at least 2× the table size as temporary space). The migration log must emit timing information per step.
- **FK invariant**: `PRAGMA foreign_keys=ON` (connection.py:53). After v33, `session_tool_usage` rows require `(project_id, session_id)` to match a parent row in `sessions(project_id, id)`. The backfill step above ensures this for resolvable rows; orphans are deleted.

---

## 7. API / Integration Requirements

No HTTP endpoint changes. No external service calls.

Internal dependencies:
- **FC-1 must land first**: FC-1 (`session-child-writer-project-id`) must be committed and the server must have completed at least one sync cycle so that newly-written child rows carry real `project_id` values. Without FC-1, v33's backfill will clean up old orphans but new writes will immediately create new ones.
- `backend/db/sqlite_migrations.py`: the v33 migration function will be added here and registered in the migration runner's version table (matching the existing version-keyed dispatcher pattern).
- `backend/db/migration_governance.py`: the governance contract validator must be satisfied (existing pattern — follow whatever the validator requires for registering a new migration version).

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/db/sqlite_migrations.py` — `_migrate_v31_sessions_composite_pk_and_child_fks` is the canonical template. Copy its structure: idempotency check, PRAGMA off, DROP TABLE IF EXISTS _new, CREATE TABLE _new, PRAGMA table_info intersection copy, DROP original, RENAME _new, PRAGMA on, foreign_key_check.
- Commit ec27957 lessons (v31 rebuild):
  1. `DROP TABLE IF EXISTS *_new` before CREATE (idempotency)
  2. Column intersection copy (never hard-code the full column list)
  3. Composite-PK short-circuit at migration entry
  4. `PRAGMA foreign_keys=OFF` outside transaction, restored unconditionally in a `try/finally`

**Must not change (protected areas):**
- Live production `data/ccdash_cache.db` during development — use a test copy only
- `PRAGMA foreign_keys=ON` setting in `connection.py:53`
- The v31 migration function itself — do not modify it; v33 is additive
- Any application-layer code (repositories, services, routers) — this is a migration-and-backfill-only contract

**New dependencies:** No new dependencies expected.

---

## 9. Acceptance Criteria

### AC-1: Idempotency

- [ ] Running the v33 migration twice on the same database produces no error and no data change on the second run
- [ ] The idempotency short-circuit uses `PRAGMA table_info` (or `sqlite_master`) to detect the new PK/index, not a version number alone (version number is necessary but not sufficient for detecting partial runs)

### AC-2: session_tool_usage PK promotion

- [ ] After v33, `session_tool_usage` has `PRIMARY KEY (project_id, session_id, tool_name)` (verified via `sqlite_master` in a test)
- [ ] All rows from the original table are present in the rebuilt table (row count is preserved or reduced only by explicit orphan deletion)
- [ ] Attempting to INSERT a row with `(project_id, session_id, tool_name)` matching an existing row raises `UNIQUE constraint failed`

### AC-3: session_messages unique index broaden

- [ ] After v33, the unique index on `session_messages` covers `(project_id, session_id, message_index)` (verified via `sqlite_master` in a test)
- [ ] The index is named consistently (e.g., `idx_session_messages_session_message` or a new v33-specific name — document the chosen name)
- [ ] Existing session_messages data is preserved; `message_index` deduplication behavior is unchanged

### AC-4: Orphan backfill correctness

- [ ] After v33, no rows in `session_sentiment_facts`, `session_code_churn_facts`, `session_scope_drift_facts`, `session_artifacts`, or `session_logs` have `project_id IN (NULL, '')` (verified by a SELECT COUNT query in a test)
- [ ] Rows whose `session_id` resolves to exactly one non-empty `project_id` in the `sessions` table have been updated with that value
- [ ] Rows whose `session_id` does not appear in `sessions`, or appears under multiple distinct `project_id` values, have been deleted
- [ ] The migration function logs the count of backfilled rows and deleted orphans per table

### AC-5: FK compliance after migration

- [ ] `PRAGMA foreign_key_check` returns zero violations after v33 completes (asserted in a test)
- [ ] `PRAGMA foreign_keys=ON` is re-enabled unconditionally at the end of the migration (verified in the migration code — must use `try/finally`)

### AC-6: Validation against slim DB copy

- [ ] The migration is tested against a schema-faithful slim copy of the real database (not `:memory:` alone, and not the live production DB)
- [ ] The slim copy is created using the project's standard migration runner (`run_migrations`) so its schema is current
- [ ] Test documents the copy creation method so it is reproducible by the operator

### AC-7: Backup warning in migration log

- [ ] The migration function emits a `logger.warning` recommending a backup before any destructive operation
- [ ] The warning text includes the path `data/ccdash_cache.db` and the recommendation to backup

### AC-8: FC-1 dependency enforcement (documentation)

- [ ] The migration function docstring states: "Depends on FC-1 (session-child-writer-project-id) being deployed first. Running v33 before FC-1 will clean up existing orphans but new ingest runs will recreate them."
- [ ] The contract's related_documents field references FC-1 (already set in frontmatter)

### AC-9: No regression on existing migration tests

- [ ] Run: `backend/.venv/bin/python -m pytest backend/tests/test_runtime_bootstrap.py -v`
- [ ] Run: `backend/.venv/bin/python -m pytest backend/tests/test_request_context.py -v`
- [ ] Any named test file that exercises `run_migrations` continues to pass
- [ ] Named test files only — never unscoped `pytest backend/tests`

---

## 10. Validation Requirements

- [ ] **Migration idempotency test** passes (run migration twice, assert no error, assert row counts stable)
- [ ] **FK check test** passes (`PRAGMA foreign_key_check` = 0 violations after migration)
- [ ] **Orphan count test** passes (zero NULL/'' project_id rows in five tables)
- [ ] **Slim DB copy validation** documented and reproducible
- [ ] **Backup warning** present in migration log output
- [ ] **Existing migration tests** pass (named test files, not unscoped)
- [ ] **No unrelated changes** — no application layer code, no frontend files, no non-migration files modified

---

## 11. Risk Areas

- **Destructive rebuild on 10 GB production cache** — same hazard class as v31. A `DROP TABLE` inside the rebuild permanently destroys the original if the subsequent `ALTER TABLE RENAME` fails. The migration must use `try/finally` to restore `PRAGMA foreign_keys=ON` and must log every step. The executor must validate on a slim copy before documenting "ready for production."
- **Column intersection copy correctness** — if `PRAGMA table_info` returns unexpected results (e.g., due to schema drift from a partial prior migration), the intersection computation may produce an incorrect column list. The migration must log the computed intersection before executing the INSERT.
- **session_tool_usage PK with pre-FC-1 `project_id = ''` rows** — if FC-1 has not yet landed and there are empty-string `project_id` rows in `session_tool_usage`, the new PK `(project_id, session_id, tool_name)` with `project_id = ''` is structurally valid but logically wrong. The backfill step must attempt to resolve these too. Rows that cannot be resolved (no parent session match or ambiguous) must be deleted, not silently retained.
- **session_messages index rename may break existing queries** — if any query hard-codes the index name `idx_session_messages_session_message`, renaming it will not break correctness (SQLite uses indexes transparently) but it may break `EXPLAIN QUERY PLAN` assertions in tests. Check for hard-coded index name references before renaming.
- **PRAGMA foreign_keys=OFF window** — between `PRAGMA foreign_keys=OFF` and the final `PRAGMA foreign_keys=ON`, any concurrent write (from a background worker) can write FK-violating rows. In practice, this migration runs at server startup before the background worker starts, but the executor must verify the startup sequence and document if there is any concurrent-write risk.
- **FC-1 must precede production run** — if this migration is deployed without FC-1, the backfill will clean up existing orphans but the `upsert_artifacts` and `replace_*_facts` writers will immediately create new NULL-`project_id` rows on the next sync. Document this dependency prominently in the migration docstring and in the Completion Report.

---

## 12. Implementation Notes

**Suggested approach:**

1. Read `_migrate_v31_sessions_composite_pk_and_child_fks` in `backend/db/sqlite_migrations.py` in full — the v33 migration function must follow the same structure.
2. Write `_migrate_v33_composite_key_hardening(db)` in `sqlite_migrations.py`:
   - Idempotency check: `SELECT sql FROM sqlite_master WHERE name='session_tool_usage'` and verify `PRIMARY KEY (project_id, session_id, tool_name)` is not already present
   - PRAGMA foreign_keys=OFF (outside transaction, in try/finally)
   - Rebuild `session_tool_usage`: DROP IF EXISTS _new, CREATE _new with new PK, compute column intersection, INSERT via intersection, DROP original, RENAME
   - Rebuild `session_messages` index: DROP old unique index, CREATE new unique index on `(project_id, session_id, message_index)`
   - Backfill orphan `project_id` in five tables (one UPDATE + one DELETE per table)
   - PRAGMA foreign_key_check
   - PRAGMA foreign_keys=ON
   - Log counts throughout
3. Register v33 in the migration version dispatcher (follow the existing pattern for version registration)
4. Write tests: idempotency, PK assertion, orphan count, FK check
5. Validate against slim DB copy

**Reference pattern:**
- `backend/db/sqlite_migrations.py` — `_migrate_v31_sessions_composite_pk_and_child_fks` (~line 1562)
- Commit ec27957 message and diff for the specific guards added in v31

**Known gotchas:**
- `session_tool_usage` currently has a simple `CREATE INDEX IF NOT EXISTS idx_session_tool_usage_project ON session_tool_usage(project_id)` added by v31. This index is on a nullable column; after v33 it becomes part of the composite PK. Drop the standalone `project_id` index if it becomes redundant post-rebuild.
- The `session_messages` unique index is currently `(session_id, message_index)`. The new index must be `(project_id, session_id, message_index)` — note the ordering: `project_id` first so scans by `(project_id, session_id)` can use the index.
- `PRAGMA foreign_key_check` in SQLite returns one row per violation. An empty result set means zero violations. The test must assert `len(results) == 0`, not `results is None`.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of modified files with the specific functions added/modified and a one-line reason per file
- **Tests run**: Named test file paths and results for all ACs in section 9
- **Validation results**: Table of each validation command (lint, named test runs, PRAGMA checks) with pass/fail
- **Slim DB copy validation**: How the copy was created, what schema it contained, and what the migration produced (row counts before/after per table)
- **Orphan counts**: Per-table counts of rows backfilled and rows deleted
- **Deviations from contract**: Any AC found to be impossible or requiring a different approach; any v31 pattern that did not apply cleanly to v33
- **Risks / Limitations**: Any production risk not mitigated by the slim-copy test; any open dependency on FC-1 not yet resolved; known constraints on production DB size
- **Follow-up recommendations**: Whether v33 is safe to run on the live instance, and what operator steps are required (backup, restart sequence, log monitoring)

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (3 points — schema + backfill only, no application layer)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion. **REQUIRES EXPLICIT USER GREENLIGHT BEFORE ANY CODE CHANGES.**

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents:**
- `docs/project_plans/feature_contracts/harden-polish/session-child-writer-project-id.md` — FC-1; **must land and deploy before FC-2 executes in production**
- `backend/db/sqlite_migrations.py` — `_migrate_v31_sessions_composite_pk_and_child_fks` is the canonical template for v33
- Commit ec27957 — v31 migration guards and lessons (DROP TABLE IF EXISTS, intersection copy, composite-PK idempotency short-circuit)
- `backend/db/connection.py:53` — `PRAGMA foreign_keys=ON` invariant
- **Workspace_id scoping (SEPARATE ticket)**: The 25+ methods failing `test_workspace_scoping.py` are NOT covered by this contract. That work is independent of v33 and must not be included in this sprint.

---

## Notes for Agents

This contract is your specification. **Do not begin implementation until the user explicitly greenlights execution.** If you receive this contract without a greenlight message, respond with: "FC-2 is capture-only and requires explicit user authorization before I can begin. Please confirm you want me to proceed."

If greenlit:
- **Never run any migration against `data/ccdash_cache.db` during development.** Use a slim copy.
- The `PRAGMA foreign_keys=OFF` window must be as short as possible. Log every step inside it.
- If `PRAGMA foreign_key_check` returns violations after migration, do not swallow the error — raise `RuntimeError` with the full violation list.
- Document any deviation from the FC-1 dependency assumption (e.g., if FC-1 is not yet committed when you run tests, note the orphan re-creation risk explicitly).

Stay within scope. No application-layer changes. No frontend files. No repository method changes. The reviewer will check for scope drift.
