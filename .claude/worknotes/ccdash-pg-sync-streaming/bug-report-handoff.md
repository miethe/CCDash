# Bug Report & Hand-off — CCDash Postgres-path sync defects (block remote/Mac→nuc streaming)

- **Date:** 2026-06-26
- **Status:** Open — needs backend owner (data-layer-expert / python-backend-engineer)
- **Discovered by:** `/fix:debug` investigation of "CCDash on the nuc seems to be failing / on a different port"
- **Severity:** Bug #1 = **P1 blocker** (data loss: sessions silently skipped; blocks any real-session Postgres ingest, incl. remote streaming). Bug #2 = **P2** (log spam + misleading `unhealthy` status; degrades gracefully).
- **Related memory:** `ccdash-nuc-remote-streaming`, `ccdash-core-remediation-plan` (CCDash PG path "dead-on-arrival"), `ccdash-runtime-deploy-remediation` (real seeded-pg smoke catches FK bugs unit mocks miss).

---

## TL;DR

The nuc CCDash instance is healthy (API `http://10.42.10.76:8090`, UI `:3010`). A separate worker-watch crash loop was already fixed this session (see §4). While validating a **Mac→remote session-streaming** setup (a local worker writing to the node's shared Postgres at `10.42.10.76:5440`), the transport was **proven working (50 real sessions streamed)** but a clean full backfill **stalled** on two pre-existing Postgres-path bugs. Both must be fixed (and the node redeployed) before streaming is production-usable.

These are NOT remote-specific bugs — they fire on **any** Postgres deployment syncing real sessions with usage/tool data. The node's own worker never tripped #1 because its only project (`default-skillmeat`) has no real sessions.

---

## Environment / how to reproduce

- **Composition:** `CCDASH_DB_BACKEND=postgres` (enterprise-postgres / pgvector). Repo + node DB both at migration `schema_version = 35`.
- **Repro A (what was done):** run a local worker against a shared Postgres and sync a directory of real Claude Code session JSONL:
  ```bash
  cd <repo>
  CCDASH_DB_BACKEND=postgres \
  CCDASH_DATABASE_URL='postgresql://ccdash:<pw>@10.42.10.76:5440/ccdash' \
  CCDASH_RUNTIME_PROFILE=worker-watch \
  CCDASH_WORKER_PROJECT_ID=<pid> \
  CCDASH_WORKER_WATCH_PROJECT_ID=<pid> \
  backend/.venv/bin/python -m backend.worker
  # where <pid> is a project registered in the DB with sessions_path=/abs/path/to/.claude/projects
  ```
- **Repro B (minimal):** point any Postgres-backed CCDash worker/api at a project whose `sessions_path` contains real sessions that carry usage events + tool usage, and trigger a sync. Watch for `ForeignKeyViolationError` / `UniqueViolationError` in the worker log and "Skipping session file that failed to sync".

---

## Bug #1 — Non-atomic per-session multi-table write (P1, data loss)

### Symptom
During backfill, a large fraction of sessions fail and are skipped. Worker log (observed):
```
asyncpg.exceptions.ForeignKeyViolationError: insert or update on table "session_messages"
  violates foreign key constraint "fk_session_messages_session"
DETAIL: Key (project_id, session_id)=(<proj>, S-agent-…) is not present in table "sessions".
...
asyncpg.exceptions.ForeignKeyViolationError: ... "session_tool_usage" ... "fk_session_tool_usage_session"
...
asyncpg.exceptions.ForeignKeyViolationError: ... "session_usage_attributions" ... "session_usage_attributions_event_id_fkey"
DETAIL: Key (event_id)=(usage-…) is not present in table "session_usage_events".
"Skipping session file that failed to sync"
# on retry of the same file, partial rows already exist:
asyncpg.exceptions.UniqueViolationError: Key (project_id, source_key)=(<proj>, commit:…) already exists.
asyncpg.exceptions.UniqueViolationError: Key (id)=(usage-…) already exists.
```
Net effect in repro: ingestion stalled at ~50 sessions out of 3,780; mix of FK + Unique violations; sessions with usage/tool data dropped.

### Root cause
The per-session persist is **split across multiple pooled connections with no single enclosing transaction**, so child rows can be FK-checked against a parent that isn't committed/visible yet on the asyncpg pool (`self.db` is a connection pool — each `execute`/`executemany`/`postgres_transaction` acquires a *different* connection):

- Entry point: `backend/db/sync_engine.py:4559 _sync_single_session` → clears prior rows (`session_repo.delete_by_source`, `:~4599`) → `backend/ingestion/session_ingest_service.py:111 persist_envelope` writes the parent `sessions` row + children.
- The child repo writes each open their **own** transaction/connection: `backend/db/repositories/postgres/sessions.py:737, 789, 810 (session_tool_usage INSERT), 854` all use `async with postgres_transaction(self.db) as conn:` — i.e. one transaction per child method, not one spanning parent+children.
- The usage path is worse — **no transaction wrapper at all**: `backend/db/sync_engine.py:1738 _replace_session_usage_attribution` → `:1751 self.session_usage_repo.replace_session_usage(...)` → `backend/db/repositories/postgres/usage_attribution.py:20–80 replace_session_usage` issues `self.db.execute(DELETE…)`, then `self.db.executemany(INSERT session_usage_events…)`, then `self.db.executemany(INSERT session_usage_attributions…)` — three separate pool acquisitions. `session_usage_attributions.event_id` → `session_usage_events`, so the attributions insert can run on a connection where the just-inserted events aren't committed → FK violation.
- Because the failed file is retried but the earlier partial inserts already committed, the retry collides → `UniqueViolation` (`source_key`, usage `id`). Non-idempotent inserts.

### Proposed fix
1. Wrap the **entire** per-session persist (parent `sessions` + ALL children: `session_messages`, `session_tool_usage`, `session_usage_events`, `session_usage_attributions`, relationships, facts) in **one** `postgres_transaction(self.db)` on a **single acquired connection**, inserting parents strictly before children. Thread that `conn` through `persist_envelope` and `replace_session_usage` instead of each opening its own. The helper already exists (`postgres_transaction` in `backend/db/repositories/postgres/…`).
2. Make all inserts **idempotent** (`INSERT … ON CONFLICT … DO UPDATE/NOTHING`) keyed on the natural keys (`(project_id, source_key)`, usage `id`, etc.) so a re-sync of the same source file converges instead of colliding.
3. Per repo ADR-007: new/changed write paths must use `repositories/base.py:retry_on_locked` and ship a **direct-count assertion test**.

### Acceptance criteria
- Backfill of a real `~/.claude/projects` tree (thousands of sessions, with usage + tool data) against Postgres completes with **0 FK violations, 0 Unique violations, 0 "Skipping session file"**.
- Re-running the same backfill (idempotency) produces no errors and no duplicate rows (`SELECT count(*)` stable).
- New direct-count test exercising parent+children atomicity on the Postgres backend (use `npm run docker:hosted:smoke:seeded-pg` for the seeded-pg path — unit mocks miss this class of FK bug).

---

## Bug #2 — `get_data_version_fingerprint` Postgres SQL alias error (P2)

### Symptom
Every watcher fan-out / freshness check logs (for `default-skillmeat` and any project):
```
get_data_version_fingerprint: could not read freshness markers (project_id='…'):
  column fp.updated_at does not exist
HINT: Perhaps you meant to reference the column "f.updated_at".
```
The function catches the error and degrades gracefully (returns a null/fallback fingerprint), so it is **not fatal** — but it spams logs and is the reason `ccdash_worker-watch_1` reports `Health=unhealthy` (it is **not** crashing; `Restarts=0`).

### Root cause
`backend/application/services/agent_queries/cache.py`:
- `:597 get_data_version_fingerprint` → `:647` logs the "could not read freshness markers" error.
- `:707 _query_max_updated_at` Postgres branch builds SQL `SELECT COUNT(*) AS c, MAX(fp.updated_at) AS m …` at `:752` and `:765` referencing table alias **`fp`**, but the `FROM` clause / actual alias is **`f`** (per the Postgres `HINT`). Alias mismatch → `column fp.updated_at does not exist`. The SQLite branch (`:772`) uses unqualified `updated_at` and is unaffected, which is why this only shows on Postgres.

### Proposed fix
Align the alias in the Postgres SQL at `cache.py:752` / `:765` (either alias the table `fp` in `FROM` to match the `MAX(fp.updated_at)` reference, or change the reference to `f.updated_at` to match the `FROM` alias). Add a Postgres-path test for `_query_max_updated_at` / `get_data_version_fingerprint` so the alias can't regress.

### Acceptance criteria
- No `get_data_version_fingerprint: could not read freshness markers` errors in worker/api logs on the Postgres backend.
- `ccdash_worker-watch_1` health resolves (no longer flips `unhealthy` due to this query) when it has a project to fingerprint.

---

## 4. Context: worker-watch crash loop (already FIXED this session — informational)

The node's `worker-watch` was in a 40,698-restart loop because `deploy/runtime/.env` line 97 `CCDASH_WORKER_WATCH_PROJECT_ID` was left as the literal placeholder `REPLACE_WITH_RESOLVABLE_PROJECT_ID` (line 86 `CCDASH_WORKER_PROJECT_ID` was correctly `default-skillmeat`). Fix applied on the node: emptied the value → resolves `default-skillmeat`; recreated the container; `Restarts=0` verified. Backup: `deploy/runtime/.env.bak.worker-watch-fix-20260626`. Note `compose.yaml`'s `${VAR:-}` default only fires when unset/empty, so a non-empty placeholder passes straight through — a deploy-template footgun worth hardening (validate env at startup / reject the literal placeholder).

---

## 5. Streaming setup recipe (to re-validate after the fixes land)

Chosen architecture = **shared-enterprise-postgres**: a worker on the Mac watches `~/.claude/projects`, parses JSONL natively, writes to the node Postgres; node API/UI serve it from the shared DB (transcripts are DB-backed via `SessionTranscriptService` — no node file access needed).

1. Register a project in the shared DB (registry is DB-authoritative, ADR-006). `sessions_path` must be an **absolute** Mac path (watched as-is). Minimum columns: `id, name, path, sessions_path, is_active` (rest default).
2. Run the Mac worker with the Repro A command (set BOTH `CCDASH_WORKER_PROJECT_ID` and `CCDASH_WORKER_WATCH_PROJECT_ID` — the worker-watch contract requires `WORKER_PROJECT_ID` non-empty, `backend/config.py:950`).
3. **Migration parity is mandatory:** the worker runs `run_migrations` on startup (`backend/runtime/container.py:113`, no skip flag). Keep the Mac repo at the node's deployed `schema_version` (currently 35) or redeploy the node first, else the local worker migrates the shared DB ahead of the node API.
4. Done = clean backfill (0 FK/Unique errors), sessions visible in the UI under the project, then set up launchd persistence.

### Gotchas (verified this session)
- Node ports are **8090 (API) / 3010 (UI)** — NOT 8000/3000 (those are SkillMeat on the node).
- Watcher fan-out covers **all registered** projects and **ignores `is_active`** — a registered remote project will be fan-out-targeted by the node worker-watch (harmless if its path is absent on the node — `sync_engine.py:4435` early-returns — but it will trigger Bug #2's freshness query for that project).
- `sessions.project_id` has **no FK to `projects`** — deleting a project orphans its sessions; delete sessions explicitly (`session_*` children DO cascade off `sessions`).

---

## 6. Suggested validation gate

After fixes + `/redeploy ccdash`: re-run the Mac worker backfill against a real `~/.claude/projects` and assert `0` FK/Unique violations and `count(sessions where project_id=<pid>)` ≈ count of JSONL files, idempotent on re-run, with `worker-watch` healthy.
