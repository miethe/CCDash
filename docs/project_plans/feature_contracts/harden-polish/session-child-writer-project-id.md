---
title: 'Feature Contract: Session Child-Writer project_id Threading'
schema_version: 2
doc_type: feature_contract
status: completed
created: 2026-06-02
updated: '2026-06-02'
feature_slug: session-child-writer-project-id
category: harden-polish
estimated_points: 5
tier: 1
owner: nick
priority: high
risk_level: medium
changelog_required: false
related_documents:
- docs/project_plans/feature_contracts/harden-polish/v33-composite-key-schema-hardening.md
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Feature Contract: Session Child-Writer project_id Threading

## 1. Goal

Thread `project_id` through every v31 session child-table writer that currently omits it, scope all replace-DELETEs to `(project_id, session_id)`, and add `project_id` to parent-table `UPDATE` statements, so composite FKs are always satisfied, NULL/empty child rows are never written, and a writer for project A can never delete project B's rows that share a `session_id`.

---

## 2. User / Actor

- **Primary actor**: The CCDash backend sync pipeline and ingest service — both issue writes to session child tables as part of normal session ingestion and backfill.
- **Secondary actors**: Any direct callers of session-repo methods (routers, services, batch backfill jobs) that need to rely on project isolation guarantees.

---

## 3. Job To Be Done

When the sync engine or ingest service writes session intelligence facts, artifacts, logs, or file updates, it needs to store the owning `project_id` alongside every row so that a future read, delete, or rebuild for project A never corrupts project B's data that happens to share the same `session_id` string.

---

## 4. Scope

### In Scope

Writers, their protocol definitions, and their call-sites — across both SQLite and Postgres implementations:

**session_artifacts — `upsert_artifacts`**
- Files: `backend/db/repositories/sessions.py` (~line 853), `backend/db/repositories/postgres/sessions.py` (~line 727), protocol `backend/db/repositories/base.py` (~line 36)
- Currently: no `project_id` param at all
- Required: add `project_id: str = ""` param; include `project_id` as the first INSERT column; scope DELETE to `WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')` (NULL/'' tolerance per reference pattern)
- Caller: `backend/ingestion/session_ingest_service.py` (~line 203) must pass `project_id`

**session_sentiment_facts — `replace_session_sentiment_facts`**
- Files: `backend/db/repositories/session_intelligence.py` (~line 30), `backend/db/repositories/postgres/session_intelligence.py` (~line 14), protocol `backend/db/repositories/base.py` (~line 66)
- Currently: no `project_id` param; DELETE is `WHERE session_id = ?`
- Required: add `project_id: str = ""` param; include `project_id` in INSERT; scope DELETE with NULL/'' tolerance
- Callers: `backend/db/sync_engine.py` (~line 1699) and `backend/application/services/session_intelligence.py` (~line 1005)

**session_code_churn_facts — `replace_session_code_churn_facts`**
- Files: `backend/db/repositories/session_intelligence.py` (~line 74), `backend/db/repositories/postgres/session_intelligence.py` (~line 58), protocol (~line 68)
- Same pattern as sentiment_facts above
- Callers: same as sentiment_facts (`sync_engine.py` ~line 1700, `session_intelligence.py` ~line 1006)

**session_scope_drift_facts — `replace_session_scope_drift_facts`**
- Files: `backend/db/repositories/session_intelligence.py` (~line 132), `backend/db/repositories/postgres/session_intelligence.py` (~line 115), protocol (~line 70)
- Same pattern as sentiment_facts above
- Callers: same as sentiment_facts (`sync_engine.py` ~line 1701, `session_intelligence.py` ~line 1007)

**session_logs — `upsert_logs` (DELETE scoping only)**
- Files: `backend/db/repositories/sessions.py` (~line 742), `backend/db/repositories/postgres/sessions.py` (~line 608)
- Currently: `project_id` is already threaded through INSERT, but DELETE is `WHERE session_id = ?` (un-scoped)
- Required: scope DELETE to `WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')` — no param signature change needed since `project_id` already exists

**session_file_updates — `upsert_file_updates` (DELETE scoping only)**
- Files: `backend/db/repositories/sessions.py` (~line 826), `backend/db/repositories/postgres/sessions.py` (~line 694)
- Currently: `project_id` is already threaded through INSERT, but DELETE is `WHERE session_id = ?` (un-scoped)
- Required: same DELETE scoping fix as `upsert_logs`

**sessions parent table — `update_session_badges`, `update_usage_fields`, `update_observability_fields`**
- Files: `backend/db/repositories/sessions.py` (~lines 158, 670, 702), `backend/db/repositories/postgres/sessions.py` (~lines 542, 571)
- Currently: `WHERE id = ?` (un-scoped by project)
- Required: add `project_id: str = ""` param; change WHERE clause to `WHERE project_id = ? AND id = ?` with NULL/'' fallback (i.e., `WHERE (project_id = ? OR project_id IS NULL OR project_id = '') AND id = ?` so sessions written before this fix still update); thread `project_id` from all callers
- Callers of `update_session_badges`: `backend/routers/api.py` (~line 720), `backend/application/services/sessions.py` (~line 296)
- Callers of `update_usage_fields`: `backend/db/sync_engine.py` (~line 2252) — `session_id` and `project_id` are both in scope; pass `project_id`
- Callers of `update_observability_fields`: `backend/db/sync_engine.py` (~line 2297) — same

**Test harness**
- File: `backend/tests/test_session_intelligence_service.py` (~line 109 `asyncSetUp`)
- Currently: `replace_session_sentiment_facts`, `replace_session_code_churn_facts`, and `replace_session_scope_drift_facts` called without `project_id`, causing FK violations under `PRAGMA foreign_keys=ON`
- Required: pass `project_id="project-1"` (matching the parent session's `project_id`) to all three calls; the 5 currently-failing tests must pass

### Out of Scope

- v33 schema migration or any DDL changes — the schema already has `project_id` columns on all listed tables (added in v31); this contract is writer plumbing only
- Orphan data backfill for rows written before this fix — covered by FC-2 (`v33-composite-key-schema-hardening`)
- `workspace_id` scoping — a separate Tier-2 ticket covering the 25+ methods failing `test_workspace_scoping.py`
- Any new tables or indexes
- Postgres `asyncpg` parameter placeholder differences are in scope only insofar as the existing pattern already uses `$1`/`$2` vs `?`; the fix must follow the respective backend's existing placeholder style

**Note on the `""` default**: Every new `project_id: str = ""` default is a latent landmine. The correct long-term posture is for callers to always pass a real non-empty `project_id`. Acceptance criteria require that all callers in scope pass a real value. The `""` default exists only for backward-compatibility with any call paths not yet identified; it must not be used as a silent fallback. Add a `# TODO(FC-1): remove default once all callers are confirmed` comment to each new default parameter.

---

## 5. UX / Behavior Requirements

This contract has no direct user-facing UI changes. Observable behavior changes:

- After this fix, a call to `upsert_artifacts("session-123", [...], project_id="proj-A")` will not delete `session_artifacts` rows owned by `proj-B` that share `session_id = "session-123"`.
- The CCDash sync pipeline will write `project_id` into `session_artifacts`, `session_sentiment_facts`, `session_code_churn_facts`, `session_scope_drift_facts` rows on every fresh ingest or backfill pass. Rows previously written with NULL/'' `project_id` will continue to be queryable (FK check tolerates NULL).
- `update_session_badges`, `update_usage_fields`, and `update_observability_fields` will only update the session row that belongs to the specified project; a stale session_id shared across projects will no longer silently cross-update.
- No changes to API response shapes, frontend components, or observable user-facing behavior.

---

## 6. Data Requirements

- **Schema**: No DDL changes. All `project_id` columns already exist on the affected tables (added in v31). This contract writes real values into columns that were previously written as NULL or not written at all.
- **New fields**: None.
- **State changes**: On next ingest/backfill, child rows for new sessions will have non-NULL, non-empty `project_id`. Pre-existing NULL/'' rows remain until FC-2 backfill runs.
- **Storage implications**: None (columns already exist).
- **Invariant**: `PRAGMA foreign_keys=ON` is always set via `backend/db/connection.py:53`. Composite FK `(project_id, session_id) REFERENCES sessions(project_id, id)` requires both columns to be non-NULL and matching a parent row, **or** both being NULL (SQLite FK NULL-exemption). Writing `project_id = ""` (empty string) alongside a real `session_id` that has a non-empty `project_id` in sessions will violate the FK. Callers **must** pass the real `project_id`, not `""`.

---

## 7. API / Integration Requirements

No new HTTP endpoints. No external service calls. Internal dependencies:

- `backend/ingestion/session_ingest_service.py`: must pass `project_id` to `upsert_artifacts`; the value is already in scope at the call site (~line 203)
- `backend/db/sync_engine.py`: must pass `project_id` to `replace_session_sentiment_facts`, `replace_session_code_churn_facts`, `replace_session_scope_drift_facts`, `update_usage_fields`, `update_observability_fields`; `project_id` is already in scope at all call sites
- `backend/application/services/session_intelligence.py` (`_replace_session_intelligence_facts`): must pass `project_id` to the three `replace_*` fact methods; `session_row.get("project_id")` is available
- `backend/routers/api.py`: must pass `project_id` to `update_session_badges`; the project is derivable from the request context (already available as part of session context)
- `backend/application/services/sessions.py`: must pass `project_id` to `update_session_badges`; the session row contains `project_id`

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/db/repositories/session_messages.py` — the `replace_session_messages` reference implementation. Specifically: DELETE scoped with `(project_id = ? OR project_id IS NULL OR project_id = '')`, `project_id` as the first INSERT column, message-index deduplication before INSERT.
- `backend/db/repositories/sessions.py` — existing `upsert_logs` and `upsert_file_updates` already include `project_id` in INSERT; use the same pattern for the DELETE scoping fix.
- SQLite uses `?` placeholders; Postgres uses `$N` positional placeholders. Both implementations must be updated in parallel and kept in sync. The executor must update both files for each affected method.

**Must not change (protected areas):**
- `PRAGMA foreign_keys=ON` setting in `backend/db/connection.py:53` — never disable this outside a schema migration
- The external call signature of any public router endpoint
- The `replace_session_messages` method in `session_messages.py` — it already follows the correct pattern and must not be modified

**New dependencies:** No new dependencies expected.

---

## 9. Acceptance Criteria

### AC-1: upsert_artifacts accepts and writes project_id

- [ ] `upsert_artifacts(session_id, artifacts, project_id)` signature exists in SQLite repo, Postgres repo, and base protocol
- [ ] INSERT includes `project_id` as a column; the value passed by the caller is stored in the row (not NULL, not '')
- [ ] DELETE is scoped: `WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')`
- [ ] `session_ingest_service.py` passes `project_id` (non-empty) at the call site

### AC-2: replace_session_*_facts accept and write project_id

- [ ] `replace_session_sentiment_facts(session_id, facts, project_id)` signature exists in SQLite repo, Postgres repo, and base protocol
- [ ] Same for `replace_session_code_churn_facts` and `replace_session_scope_drift_facts`
- [ ] INSERT includes `project_id`; DELETE is scoped with NULL/'' tolerance
- [ ] All callers in `sync_engine.py` and `session_intelligence.py` pass `project_id`

### AC-3: upsert_logs and upsert_file_updates DELETEs are project-scoped

- [ ] `upsert_logs` DELETE: `WHERE session_id = ? AND (project_id = ? OR project_id IS NULL OR project_id = '')` in both SQLite and Postgres
- [ ] `upsert_file_updates` DELETE: same scoping in both SQLite and Postgres
- [ ] No change to caller signatures (project_id already threaded)

### AC-4: Parent-table UPDATEs are project-scoped

- [ ] `update_session_badges(session_id, ..., project_id)` signature exists in SQLite repo and base protocol; Postgres repo updated if it has the method (currently absent — add it or skip if Postgres delegates elsewhere; document the decision)
- [ ] `update_usage_fields(session_id, ..., project_id)` and `update_observability_fields(session_id, ..., project_id)` updated in both SQLite and Postgres repos
- [ ] WHERE clause: `WHERE (project_id = ? OR project_id IS NULL OR project_id = '') AND id = ?` to preserve backward compatibility with legacy rows
- [ ] All callers pass `project_id`

### AC-5: Cross-project isolation test

- [ ] A test exists (new or extended) that:
  1. Inserts session `S-1` under `project-A` and session `S-1` under `project-B` (same session_id, different projects)
  2. Calls `upsert_artifacts("S-1", [...], project_id="project-A")`
  3. Asserts that `project-B`'s `session_artifacts` rows for `session_id = "S-1"` are **not** deleted
  4. Asserts that `project-A`'s rows are replaced correctly
- [ ] The same cross-project isolation test pattern is applied to at least one of the three `replace_*_facts` writers

### AC-6: FK compliance under foreign_keys=ON

- [ ] A test or test fixture exists that:
  1. Sets up an in-memory SQLite DB via `run_migrations`
  2. Upserts a parent session with a real `project_id` (e.g., `"project-1"`)
  3. Calls `upsert_artifacts`, `replace_session_sentiment_facts`, `replace_session_code_churn_facts`, `replace_session_scope_drift_facts` with matching `project_id`
  4. Verifies no FK violation is raised
  5. Verifies no child row has NULL or '' `project_id`

### AC-7: Existing test_session_intelligence_service tests pass

- [ ] The 5 tests in `backend/tests/test_session_intelligence_service.py` that currently fail due to FK violations pass after this change:
  - `test_transcript_search_returns_ranked_matches`
  - `test_list_sessions_builds_rollups`
  - `test_detail_and_drilldown_return_fact_payloads`
  - `test_historical_backfill_is_incremental_and_restart_safe`
  - `test_embedding_block_builder_creates_message_and_window_blocks`
- [ ] Run command: `backend/.venv/bin/python -m pytest backend/tests/test_session_intelligence_service.py -v` (named file, not unscoped)

### AC-8: No regression in session-ingest and session-message tests

- [ ] Existing session ingest and session message tests continue to pass
- [ ] Run commands:
  - `backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v`
  - Any test file covering `SessionIngestService` (run by named file path)

### AC-9: Silent "" writes are avoided

- [ ] No caller in scope passes `project_id=""` (empty string) as a final value — the `""` default exists only as a parameter default, not as an intentional value
- [ ] Each new `project_id: str = ""` parameter has a `# TODO(FC-1): remove default once all callers are confirmed` comment

---

## 10. Validation Requirements

- [ ] **Backend lint** passes: `backend/.venv/bin/python -m flake8 backend/db/repositories/ backend/ingestion/ backend/application/services/session_intelligence.py backend/db/sync_engine.py`
- [ ] **Type check** passes: `backend/.venv/bin/python -m mypy backend/db/repositories/ --ignore-missing-imports` (or equivalent)
- [ ] **test_session_intelligence_service.py** passes: `backend/.venv/bin/python -m pytest backend/tests/test_session_intelligence_service.py -v`
- [ ] **New cross-project isolation test** passes (written as part of this contract)
- [ ] **Named test files only** — never run unscoped `pytest backend/tests` (known hang risk per project memory)
- [ ] **Build** passes: `npm run build` (frontend unaffected; verify no backend import errors surface)
- [ ] **No unrelated changes** introduced — no schema DDL, no frontend files, no non-session repositories

---

## 11. Risk Areas

- **SQLite/Postgres drift**: Both backends must be updated in parallel. The SQLite path uses `?` and `aiosqlite`; the Postgres path uses `$N` and `asyncpg`. A fix applied to only one backend will silently break the other. The executor must check both files side-by-side for each method.
- **The `""` default is a landmine**: Passing `project_id=""` stores an empty string, which satisfies `project_id IS NULL OR project_id = ''` in the DELETE scope but will violate the composite FK when `foreign_keys=ON` because the parent session has a real non-empty `project_id`. Every caller must be audited; the `""` default is a safety net for unmapped call paths only.
- **update_session_badges is called in lazy-backfill paths**: `backend/routers/api.py` calls `update_session_badges` in a `try/except` block that silently swallows failures. After threading `project_id`, if `project_id` is not available in that call context, the method will silently no-op. The executor must confirm `project_id` is derivable from the available context and document if it is not.
- **Postgres repo may not have update_session_badges**: Searching the Postgres sessions file reveals `update_usage_fields` and `update_observability_fields` but not `update_session_badges`. If the Postgres repo is missing this method entirely, adding it is in scope; if it delegates to the SQLite implementation, document clearly.
- **_replace_session_intelligence_facts in session_intelligence.py (service layer)**: This function calls the three `replace_*_facts` methods and already receives `project_id` as a parameter — but the inner calls do not pass it through to the repo. Threading the parameter through this private function is straightforward but easy to miss one of the three calls.
- **Test asyncSetUp project_id**: The test `asyncSetUp` already passes `"project-1"` to `sessions().upsert(...)` and `session_messages().replace_session_messages(...)`. The three intelligence fact calls at lines 140, 158, and 186 do not. The fix is to add `project_id="project-1"` to those three calls only.

---

## 12. Implementation Notes

**Suggested approach:**

1. Start with the base protocol (`backend/db/repositories/base.py`): add `project_id: str = ""` to `upsert_artifacts` and the three `replace_*_facts` protocol stubs. Add `project_id: str = ""` to `update_session_badges`, `update_usage_fields`, `update_observability_fields` protocol stubs.
2. Update SQLite implementations in `backend/db/repositories/sessions.py` and `backend/db/repositories/session_intelligence.py` — change DELETE scoping first, then add `project_id` to INSERT column lists.
3. Mirror the same changes in Postgres implementations (`backend/db/repositories/postgres/sessions.py`, `backend/db/repositories/postgres/session_intelligence.py`). Note `$N` placeholder style.
4. Update callers: `session_ingest_service.py`, `sync_engine.py`, `session_intelligence.py` service layer, `sessions.py` service layer, `routers/api.py`. Check each call site for `project_id` availability.
5. Fix the three calls in `test_session_intelligence_service.py:asyncSetUp` to pass `project_id="project-1"`.
6. Write the cross-project isolation test (AC-5).
7. Run named test files to validate.

**Reference implementation (already shipped):**
- `backend/db/repositories/session_messages.py` — `replace_session_messages` threaded `project_id` as first INSERT column and scoped DELETE with `(project_id = ? OR project_id IS NULL OR project_id = '')`. Follow this pattern exactly.

**Known gotchas:**
- `upsert_logs` in the Postgres implementation uses `ON CONFLICT ON CONSTRAINT idx_logs_source_log_unique DO NOTHING` — this conflict constraint does not reference `project_id`, so adding `project_id` to the DELETE scope does not affect the conflict resolution. Leave the ON CONFLICT clause unchanged.
- `upsert_file_updates` in Postgres uses `postgres_transaction(self.db)` context manager — scope the DELETE inside the same transaction.
- `session_artifacts` INSERT uses `id` as PRIMARY KEY (TEXT); `project_id` is a separate non-PK column. The DELETE-then-INSERT pattern is correct; do not attempt an upsert-by-id without also scoping by project.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified files with the specific method names changed and a one-line reason per file
- **Tests run**: Named test file paths, not module paths; results for all tests in AC-7 and AC-8
- **Validation results**: Table of each validation command (lint, type check, named test runs) with pass/fail
- **Cross-project isolation test**: Whether it was added as a new test or extended an existing one; what it asserts
- **Deviations from contract**: Any method found to be already correct (no change needed), any caller where `project_id` was not available and a workaround was applied, and any Postgres-specific divergence
- **Risks / Limitations**: Any callers not yet audited; any `""` defaults left in place with rationale
- **Follow-up recommendations**: Whether FC-2 (orphan backfill migration) should proceed immediately, and any additional callers discovered during implementation

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (5 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration. Requires explicit user greenlight before execution.

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents:**
- `docs/project_plans/feature_contracts/harden-polish/v33-composite-key-schema-hardening.md` — FC-2 depends on FC-1 landing first (no new orphans must be created during/after the v33 backfill)
- Reference commit 299f7bc: `backend/db/repositories/session_messages.py` `replace_session_messages` — the canonical reference implementation this contract follows
- `backend/db/connection.py:53` — `PRAGMA foreign_keys=ON` invariant
- `backend/db/sqlite_migrations.py` — v31 migration added `project_id` columns to all affected tables

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **A method already correct** (project-scoped DELETE, project_id in INSERT, caller passing project_id): Document in Completion Report as "already compliant" and skip.
- **A caller where project_id is not available**: Flag in Completion Report before attempting workarounds. Do not fabricate a project_id; document the gap.
- **Postgres method missing entirely**: Add the method following the SQLite pattern adapted for asyncpg `$N` syntax. Document in Completion Report.

Stay within scope. Do not modify schema, add migrations, change API response shapes, or touch frontend files. The reviewer will check for scope drift.
