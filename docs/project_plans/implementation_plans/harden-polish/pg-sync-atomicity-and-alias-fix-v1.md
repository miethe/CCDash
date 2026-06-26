---
schema_version: 2
doc_type: implementation_plan
title: "Postgres Sync Atomicity & Fingerprint Alias Fix"
description: "Fix two pre-existing Postgres-path defects: (1) non-atomic per-session multi-table write causes FK/Unique violations on real-session ingest (P1, data loss), (2) fp.updated_at alias mismatch in fingerprint query causes log spam and false unhealthy status (P2)."
status: completed
created: 2026-06-26T16:05:00Z
updated: 2026-06-26T18:00:00Z
feature_slug: pg-sync-atomicity-and-alias-fix
category: harden-polish
priority: p1
risk_level: high
prd_ref: null
plan_ref: null
scope: backend Python only — Postgres write path and fingerprint query. No schema migration, no new columns, no frontend changes.
effort_estimate: "7 story points"
changelog_required: false
related_documents:
  - .claude/worknotes/ccdash-pg-sync-streaming/bug-report-handoff.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
files_affected:
  - backend/db/sync_engine.py
  - backend/ingestion/session_ingest_service.py
  - backend/db/repositories/postgres/sessions.py
  - backend/db/repositories/postgres/usage_attribution.py
  - backend/db/repositories/postgres/session_intelligence.py
  - backend/db/repositories/postgres/session_messages.py
  - backend/db/repositories/usage_attribution.py
  - backend/db/repositories/base.py
  - backend/application/services/agent_queries/cache.py
  - backend/tests/test_pg_session_atomicity.py
  - backend/tests/test_agent_query_cache.py
deferred_items_spec_refs: []
findings_doc_ref: .claude/worknotes/ccdash-pg-sync-streaming/bug-report-handoff.md
commit_refs:
  - c4efac6  # P2 alias fix (fp.updated_at -> f.updated_at)
  - ff2e1be  # P1 atomic txn wrap
  - 48396a6  # P3 integration test (superseded by pool harness)
  - aad95c4  # P2b complete conn threading across all children + pool test
pr_refs: []
merge_commit: null  # squash-merged to main (no merge commit); see commit_refs
merge_branch: worktree-autopilot+pg-sync-streaming-fixes
---

```json
{
  "tier": 1,
  "effort_points": 7,
  "wave_count": 2,
  "phase_count": 3,
  "file_count": 7,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/implementation_plans/harden-polish/pg-sync-atomicity-and-alias-fix-v1.md",
  "execution_target": "execute-plan",
  "slug": "pg-sync-atomicity-and-alias-fix",
  "category": "harden-polish",
  "review_intensity": "tier3",
  "files_affected": [
    "backend/db/sync_engine.py",
    "backend/ingestion/session_ingest_service.py",
    "backend/db/repositories/postgres/sessions.py",
    "backend/db/repositories/postgres/usage_attribution.py",
    "backend/application/services/agent_queries/cache.py",
    "backend/tests/test_pg_session_atomic_persist.py",
    "backend/tests/test_agent_query_cache.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Bug #2 — fingerprint alias fix + regression test",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous implementation.\n\nFix the Postgres SQL alias mismatch in `backend/application/services/agent_queries/cache.py` function `_query_feature_phases_marker` (around line 765 in the `if project_id:` branch). The Postgres SQL currently references `MAX(fp.updated_at)` where `fp` is the alias for `feature_phases`, but `feature_phases` does not have an `updated_at` column in the schema. The `features` table (aliased `f`) does have `updated_at`. Change `MAX(fp.updated_at)` to `MAX(f.updated_at)` in the Postgres SQL string in the `if project_id:` branch. Also check and fix the `else` branch (`pg_sql = sqlite_sql`) which references the unqualified `updated_at` — if Postgres also fails on that path, add a Postgres-specific fallback SQL.\n\nThen extend `backend/tests/test_agent_query_cache.py` with a Postgres-path test for `_query_feature_phases_marker` and/or `get_data_version_fingerprint` that mocks an asyncpg-style connection and asserts the function returns a valid string (not None) — preventing the alias from silently regressing. The mock must NOT be an aiosqlite.Connection instance so the Postgres branch executes.\n\nAcceptance criteria:\n- `_query_feature_phases_marker` with a Postgres-style mock db and a project_id executes the Postgres SQL branch without raising `UndefinedColumnError` or similar.\n- `get_data_version_fingerprint` returns a non-None string (not degraded) when the Postgres branch is exercised.\n- Existing tests in `test_agent_query_cache.py` continue to pass.\n- No 'could not read freshness markers' log lines emitted when the fixed code path executes.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 1.5,
                "files_affected": [
                  "backend/application/services/agent_queries/cache.py",
                  "backend/tests/test_agent_query_cache.py"
                ]
              }
            ]
          },
          {
            "id": "phase-2",
            "title": "Bug #1 core — atomic per-session transaction + idempotent inserts",
            "mode": "C",
            "review_intensity": "tier3",
            "tasks": [
              {
                "id": "TASK-2.1",
                "prompt": "Mode C: Autonomous implementation.\n\nThis is a P1 data-loss fix on the Postgres write path. Read the full root-cause in `.claude/worknotes/ccdash-pg-sync-streaming/bug-report-handoff.md` §Bug #1 before starting.\n\nProblem: per-session persist in `backend/db/sync_engine.py:_sync_single_session` calls `backend/ingestion/session_ingest_service.py:persist_envelope`, which calls child repo write methods (`upsert_logs`, `upsert_tool_usage`, `upsert_file_updates`, `upsert_artifacts`) each opening their own `async with postgres_transaction(self.db)` — each acquiring a separate asyncpg pool connection. The parent `sessions.upsert` is also on a different pool connection. FK-constrained child rows fail because the parent row is not yet committed/visible on another pooled connection.\n\nAlso, `_replace_session_usage_attribution` -> `PostgresSessionUsageRepository.replace_session_usage` does DELETE + executemany(events) + executemany(attributions) on THREE separate pool acquisitions with no transaction wrapper. `session_usage_attributions.event_id` FK -> `session_usage_events` fails.\n\nFix strategy (all changes are Postgres-path only; SQLite behavior is unchanged):\n\n1. `backend/db/sync_engine.py:_sync_single_session`:\n   - Import `aiosqlite` for isinstance check. Detect if `self.db` is NOT `aiosqlite.Connection` (i.e., Postgres pool).\n   - For the Postgres path: wrap the entire per-session persist block (from `delete_by_source` through `persist_envelope`) in a single `async with postgres_transaction(self.db) as pg_conn:` context. Pass `pg_conn` down to `persist_envelope` as a new optional keyword arg `_pg_conn=pg_conn`.\n   - For the SQLite path: no change.\n   - Import `postgres_transaction` from `backend.db.repositories.postgres._transactions` (conditional, only used when needed).\n\n2. `backend/ingestion/session_ingest_service.py:SessionIngestService.persist_envelope`:\n   - Add optional keyword arg `_pg_conn: Any = None` to the signature.\n   - Thread `_pg_conn` to all child write calls: `session_repo.upsert_logs(..., _pg_conn=_pg_conn)`, `upsert_tool_usage`, `upsert_file_updates`, `upsert_artifacts`, and `replace_session_usage_attribution` (which is a callable — add `_pg_conn=_pg_conn` to its call signature or handle in `_replace_session_usage_attribution`).\n   - Also thread to `session_repo.upsert(session_dict, project_id, _pg_conn=_pg_conn)` so the parent INSERT is on the same connection.\n   - SQLite callers pass `_pg_conn=None` (unchanged behavior).\n\n3. `backend/db/repositories/postgres/sessions.py` — child write methods:\n   - `upsert_logs`, `upsert_tool_usage`, `upsert_file_updates`, `upsert_artifacts`: add optional `_pg_conn=None` parameter.\n   - When `_pg_conn is not None`: use `_pg_conn` directly (no new `postgres_transaction`). Execute DELETE and INSERT directly on `_pg_conn`.\n   - When `_pg_conn is None`: use the existing `async with postgres_transaction(self.db) as conn:` pattern (backward compat for callers that don't thread a connection).\n   - Also update `upsert(session_data, project_id, _pg_conn=None)`: when `_pg_conn` is provided, execute the INSERT directly on `_pg_conn`; otherwise use `self.db.execute` as today.\n   - Add `ON CONFLICT DO NOTHING` or `ON CONFLICT ... DO UPDATE` to INSERT statements in `upsert_tool_usage` (no conflict clause today) and `upsert_file_updates` (no conflict clause today), using natural keys `(session_id, tool_name)` and `(session_id, file_path, action_timestamp)` respectively. The `upsert_artifacts` INSERT also lacks ON CONFLICT — add ON CONFLICT on `(project_id, id)` DO NOTHING.\n   - The `upsert_logs` INSERT already has `ON CONFLICT ON CONSTRAINT idx_logs_source_log_unique DO NOTHING` — leave it.\n\n4. `backend/db/repositories/postgres/usage_attribution.py:PostgresSessionUsageRepository.replace_session_usage`:\n   - Add optional `conn=None` parameter.\n   - When `conn is not None`: use `conn` directly for all three operations (DELETE events, executemany events, executemany attributions) — no separate pool acquisitions.\n   - When `conn is None`: wrap the three operations in a single `async with postgres_transaction(self.db) as conn:` (fixing the existing no-transaction bug for standalone callers).\n   - Add `ON CONFLICT (id) DO NOTHING` to the `session_usage_events` INSERT (natural key = `id`).\n   - Add `ON CONFLICT (event_id, entity_type, entity_id, attribution_role) DO NOTHING` to `session_usage_attributions` INSERT (or DO UPDATE if a constraint with that name exists; verify from schema).\n\n5. `backend/db/sync_engine.py:_replace_session_usage_attribution`:\n   - Add `_pg_conn=None` parameter and pass it through to `self.session_usage_repo.replace_session_usage(..., conn=_pg_conn)`.\n\n6. Protocol (`backend/db/repositories/base.py:SessionUsageRepository`):\n   - Update `replace_session_usage` signature to include optional `conn: Any = None` so the protocol matches.\n\nConstraints:\n- SQLite backend behavior must be 100% unchanged — all `_pg_conn=None` / `conn=None` defaults preserve existing paths.\n- NO new DB columns or schema migrations.\n- Per ADR-007: new write paths should use `retry_on_locked` — but this is Postgres-path only and asyncpg uses asyncpg exceptions, not aiosqlite. `retry_on_locked` only retries on aiosqlite locked errors. Do NOT wrap the new Postgres transaction in `retry_on_locked` (it would swallow asyncpg exceptions). The transaction itself provides atomicity; the existing sync-engine-level exception handler (skips + logs) provides the retry-at-file-level behavior already.\n- Do NOT touch the SQLite implementations of these repo methods.\n- Do NOT alter DB migration files.\n\nAcceptance criteria (unit-level, no real DB required):\n- `persist_envelope` can be called with `_pg_conn=<mock>` and all child writes use that mock connection.\n- `replace_session_usage` with `conn=None` still wraps DELETE+events+attributions in a single transaction.\n- `replace_session_usage` with a `conn` arg uses it directly.\n- Existing unit tests pass.\n\nDo NOT write the seeded-pg integration test — that is Phase 3.\nDo NOT git add/commit/push/stash.",
                "assigned_to": "data-layer-expert",
                "effort": 4,
                "files_affected": [
                  "backend/db/sync_engine.py",
                  "backend/ingestion/session_ingest_service.py",
                  "backend/db/repositories/postgres/sessions.py",
                  "backend/db/repositories/postgres/usage_attribution.py",
                  "backend/db/repositories/base.py"
                ]
              }
            ]
          }
        ]
      },
      {
        "id": "wave-2",
        "phases": [
          {
            "id": "phase-3",
            "title": "Bug #1 seeded-pg integration test (direct-count assertion)",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-3.1",
                "prompt": "Mode C: Autonomous implementation.\n\nWrite the integration test for the Bug #1 atomic persist fix. This test MUST run against the real seeded-pg backend — unit mocks cannot detect FK violations across pooled connections.\n\nCreate `backend/tests/test_pg_session_atomic_persist.py`.\n\nThe test should be structured as a `unittest.TestCase` that:\n1. Skips automatically if `CCDASH_DB_BACKEND != 'postgres'` or if `CCDASH_DATABASE_URL` is unset (so it only runs in the seeded-pg environment).\n2. Sets up a real asyncpg pool connection to the configured Postgres DB.\n3. Constructs a minimal `NormalizedSessionEnvelope` with a session payload that includes `session_messages`, `session_tool_usage`, `session_usage_events`, and `session_usage_attributions` (use realistic-looking IDs).\n4. Calls the full `_sync_single_session` path (or instantiates `SessionIngestService` + calls `persist_envelope` with a live Postgres-backed repo set) to persist the session.\n5. Directly asserts row counts in each table using raw SQL against the test DB:\n   - `SELECT count(*) FROM sessions WHERE project_id=$1 AND id=$2` == 1\n   - `SELECT count(*) FROM session_messages WHERE project_id=$1 AND session_id=$2` == expected_count\n   - `SELECT count(*) FROM session_tool_usage WHERE session_id=$1` == expected_count\n   - `SELECT count(*) FROM session_usage_events WHERE project_id=$1 AND session_id=$2` == expected_count\n   - `SELECT count(*) FROM session_usage_attributions WHERE event_id IN (SELECT id FROM session_usage_events WHERE session_id=$1)` == expected_count\n6. Calls `persist_envelope` again with the SAME session (idempotency pass) and asserts the same row counts — no increase, no error.\n7. Cleans up test rows in tearDown (DELETE by test project_id).\n\nKey test invariants:\n- Zero FK violations during the persist call (asyncpg ForeignKeyViolationError would propagate as test failure).\n- Zero UniqueViolationError on the idempotency pass.\n- All expected child rows are present after persist (proving atomicity and correct ordering).\n\nReference pattern from `backend/tests/test_postgres_migrations_upgrade.py` for how to skip and set up asyncpg.\n\nAlso note: `npm run docker:hosted:smoke:seeded-pg` is the authoritative gate command that Opus will run post-merge-prep. The test must be runnable via:\n```\nCCDASH_DB_BACKEND=postgres CCDASH_DATABASE_URL=<url> backend/.venv/bin/python -m pytest backend/tests/test_pg_session_atomic_persist.py -v\n```\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "data-layer-expert",
                "effort": 1.5,
                "files_affected": [
                  "backend/tests/test_pg_session_atomic_persist.py"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "Not expected to exceed single-pass capacity; if TASK-2.1 scope expands to touch session_messages or session_intelligence repos, promote to Tier 2 and add a Phase 2b for those repos."
}
```

## Executive Summary

Two pre-existing Postgres-path bugs block real-session ingest and Mac→nuc streaming. Both are pure backend Python fixes with no schema migration required. The root causes are fully identified in the bug-report handoff.

**Bug #1 (P1, data loss):** Per-session persist is split across multiple asyncpg pool connections with no single enclosing transaction. Child table INSERTs (`session_messages`, `session_tool_usage`, `session_usage_events`, `session_usage_attributions`) FK-check against a `sessions` parent row that isn't yet committed/visible on a different pooled connection → `ForeignKeyViolationError`. On retry, already-committed partial rows → `UniqueViolationError`. Net effect: sessions with usage/tool data silently skipped.

**Bug #2 (P2, log spam):** `_query_feature_phases_marker` in `cache.py` references `fp.updated_at` (alias for `feature_phases`) but `feature_phases` has no `updated_at` column. Postgres raises `column fp.updated_at does not exist`; the function catches and degrades to `None` → spams "could not read freshness markers" logs and causes `worker-watch` to report `unhealthy`.

---

## Implementation Strategy

### Architecture Sequence

1. **Phase 1 (Wave 1, parallel)** — Bug #2: one-line SQL alias fix + Postgres-path regression test.
2. **Phase 2 (Wave 1, parallel)** — Bug #1 core: thread a single acquired connection through the per-session persist path; add `ON CONFLICT` idempotency to all child INSERT statements; update protocol signature for `replace_session_usage`.
3. **Phase 3 (Wave 2, sequential after Phase 2)** — Bug #1 seeded-pg integration test: direct-count assertions against a live Postgres DB to prove FK atomicity and idempotency.

### Critical Path

Phase 1 is independent of Bug #1 work. Phase 3 depends on Phase 2 completing. Wave 1 phases run in parallel.

### Phase Summary

| Phase | Title | Pts | Agent | Model | Wave |
|-------|-------|-----|-------|-------|------|
| Phase 1 | Bug #2 alias fix + test | 1.5 | python-backend-engineer | sonnet | 1 |
| Phase 2 | Bug #1 core atomic txn + idempotency | 4.0 | data-layer-expert | sonnet | 1 |
| Phase 3 | Bug #1 seeded-pg direct-count test | 1.5 | data-layer-expert | sonnet | 2 |

---

## Wave Plan

### Wave 1 — Core fixes (parallel)

**Phase 1: Bug #2 — fingerprint alias fix**

Entry criteria: none.

| Task | File | Description |
|------|------|-------------|
| TASK-1.1 | `cache.py`, `test_agent_query_cache.py` | Fix `fp.updated_at` → `f.updated_at` in `_query_feature_phases_marker` Postgres SQL; add Postgres-path mock test. |

Exit criteria: `get_data_version_fingerprint` returns non-None on Postgres path with project_id; existing cache tests pass.

Review: `task-completion-validator` (standard pass).

---

**Phase 2: Bug #1 core — single-connection transaction + idempotency**

Entry criteria: none (parallel with Phase 1).

Key design decision: use `_pg_conn=None` optional parameter threading rather than a connection-scoped repo factory, to minimize surface area of the change and preserve the protocol interface.

| Task | Files | Description |
|------|-------|-------------|
| TASK-2.1 | `sync_engine.py`, `session_ingest_service.py`, `sessions.py`, `usage_attribution.py`, `base.py` | Wrap per-session persist in one `postgres_transaction`; thread `_pg_conn` through `persist_envelope` and all child repo write methods; add `ON CONFLICT` to `session_tool_usage`, `session_file_updates`, `session_artifacts`, `session_usage_events`, `session_usage_attributions` INSERTs; wrap standalone `replace_session_usage` in a single transaction when no `conn` is passed. |

Connection threading design:

```
sync_engine._sync_single_session
  ├── Postgres path:
  │   async with postgres_transaction(self.db) as pg_conn:
  │       session_repo.delete_by_source(..., _pg_conn=pg_conn)
  │       session_repo.delete_relationships_for_source(..., _pg_conn=pg_conn)  [optional - low risk]
  │       ingest_service.persist_envelope(..., _pg_conn=pg_conn)
  │           └── session_repo.upsert(session_dict, project_id, _pg_conn=pg_conn)       ← parent
  │               session_repo.upsert_logs(..., _pg_conn=pg_conn)                        ← child
  │               session_repo.upsert_tool_usage(..., _pg_conn=pg_conn)                  ← child
  │               session_repo.upsert_file_updates(..., _pg_conn=pg_conn)                ← child
  │               session_repo.upsert_artifacts(..., _pg_conn=pg_conn)                   ← child
  │               session_message_repo.replace_session_messages(..., _pg_conn=pg_conn)   ← child
  │               replace_session_usage_attribution(... _pg_conn=pg_conn)
  │                   └── session_usage_repo.replace_session_usage(..., conn=pg_conn)    ← child
  └── SQLite path: unchanged (all _pg_conn=None, existing behavior)
```

Idempotency keys for new ON CONFLICT clauses:

| Table | Conflict key | Action |
|-------|-------------|--------|
| `session_tool_usage` | `(session_id, tool_name)` | DO NOTHING |
| `session_file_updates` | natural key or `(session_id, file_path, action_timestamp)` | DO NOTHING |
| `session_artifacts` | `(project_id, id)` | DO NOTHING |
| `session_usage_events` | `(id)` | DO NOTHING |
| `session_usage_attributions` | `(event_id, entity_type, entity_id, attribution_role)` | DO NOTHING |

Note: Executor must verify actual constraint names from the schema (migrations.py) before writing ON CONFLICT clauses. If a named constraint exists, reference it by name; otherwise use ON CONFLICT ON `(columns)`.

Exit criteria: unit tests pass with SQLite; `_pg_conn` threading exercised via mock in test. FK and Unique violations are eliminated by construction (same-connection transaction).

Review: `task-completion-validator` (tier3 pass — core write path, data loss risk).

---

### Wave 2 — Integration validation

**Phase 3: Bug #1 seeded-pg direct-count test**

Entry criteria: Phase 2 merged (code available on branch).

| Task | File | Description |
|------|------|-------------|
| TASK-3.1 | `tests/test_pg_session_atomic_persist.py` | Create direct-count assertion test exercising parent+children atomicity on real Postgres backend. Skips if not in Postgres env. Runs as: `CCDASH_DB_BACKEND=postgres CCDASH_DATABASE_URL=<url> python -m pytest backend/tests/test_pg_session_atomic_persist.py -v`. |

Exit criteria: Test passes on real seeded-pg. Zero FK/Unique violations. Idempotency pass produces stable counts.

**Authoritative gate:** `npm run docker:hosted:smoke:seeded-pg` — Opus runs this post-merge-prep.

Review: `task-completion-validator` (standard pass).

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `_pg_conn` threading misses a child write method (incomplete fix) | High | Phase 3 seeded-pg test catches any remaining pooled-connection child writes — FK violations would still surface |
| `ON CONFLICT` key mismatch (wrong columns, no constraint exists) | Medium | Executor must verify constraint names from `migrations.py` before writing; test catches UniqueViolationError |
| SQLite regression from the `_pg_conn` param change | Medium | All new params have `None` defaults; SQLite path is via `isinstance(db, aiosqlite.Connection)` guard in sync_engine.py |
| `replace_session_messages` missing from connection threading | Low | The `session_message_repo.replace_session_messages` is also a child write — executor should include it; the seeded-pg test asserts row counts for messages |
| `postgres_transaction` nested savepoint behavior | Low | asyncpg SAVEPOINT is correct for nested `async with conn.transaction()` — the Postgres txn helper handles this correctly when passed a Connection (not Pool) |

---

## Validation Notes for Executor

1. **FK bugs are invisible to unit mocks.** The seeded-pg test (Phase 3) is the ONLY reliable way to prove Bug #1 is fixed. Do not skip Phase 3 or substitute with mock-only tests.
2. **`npm run docker:hosted:smoke:seeded-pg`** is the authoritative gate. Opus will run it post-merge-prep.
3. **SQLite path must be unchanged.** Run `backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py backend/tests/test_runtime_bootstrap.py -v` to confirm no SQLite regressions.
4. **Constraint name lookup.** Before writing any ON CONFLICT clause, search `backend/db/migrations.py` for the constraint or index name for that table to ensure the clause is valid.
5. **`session_messages` table.** The `session_message_repo.replace_session_messages` call in `persist_envelope` is also a child write. It must be included in the `_pg_conn` threading. Verify the Postgres `session_messages` repo accepts a `_pg_conn` param or trace through its implementation.

---

## Success Criteria

- Backfill of a real `~/.claude/projects` tree (thousands of sessions with usage + tool data) against Postgres completes with **0 FK violations, 0 Unique violations, 0 "Skipping session file"** log lines.
- Re-running the same backfill produces no errors and stable row counts (idempotent).
- No `get_data_version_fingerprint: could not read freshness markers` errors in worker/api logs on Postgres.
- `ccdash_worker-watch_1` health resolves (no longer flips unhealthy due to the fingerprint query).
- `npm run docker:hosted:smoke:seeded-pg` passes.
- All existing backend unit tests pass unchanged.
