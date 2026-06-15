# Context — Offline-Capable CCDash CLI (Direct-from-Source)

Plan: `docs/project_plans/implementation_plans/enhancements/ccdash-offline-cli-direct-source-v1.md`
Status: **draft — awaiting decision confirmation before execution** (paused per request 2026-06-14)

## Origin
`/quick-feature` request: make the CLI capable offline — a wrapper over session-log
access direct from source for a configured harness, parsing directly, providing insight
when the backend isn't running, reusing a consolidated core imported by both CLI and
backend. Scoped up to a full (4-phase) feature.

## Verified architecture (2026-06-14, 5-reader map + direct code check)
- `backend/cli/runtime.py:29-44` `bootstrap_cli()` = open DB + build ports. **No
  `run_migrations`, no `SyncEngine`.** CLI assumes a worker-populated DB. This is the
  whole offline gap.
- `SyncEngine(db)` + public `async sync_project(project, sessions_dir, docs_dir,
  progress_dir, *, allow_writeback=True, capture_analytics=True,
  backfill_session_intelligence=True, force=False, trigger=...)` —
  `db/sync_engine.py:1372,3069`. Container does `run_migrations(db)` then `SyncEngine(db)`
  (`runtime/container.py:113,272`). → reusable synchronous core for the CLI.
- agent_queries = function-level DI on `CorePorts`; `ports.storage.sessions()` resolves
  via `RepositoryBackedStorageUnitOfWork(db, *, repo_builders)` (`adapters/storage/base.py:133,218`).
  Repos are `@runtime_checkable` Protocols. → enables Approach-1 (future) and is irrelevant
  to Approach-2 (recommended).
- Cache `@memoized_query` → `get_data_version_fingerprint()` queries raw DB every call
  (`agent_queries/cache.py`). Fine for Approach-2 (real DB); blocks a pure no-DB path.
- `reporting.py:159` passes `ports.storage.db` raw to `list_workflow_registry()` — only
  non-repo DB access; Approach-2 unaffected.
- Parsers return fully-typed `AgentSession`; sync-time-only enrichments (pricing, context
  observability, usage attribution, intelligence facts, commit correlations, badges)
  cannot come from a bare parse → must degrade offline.
- Config: `pathConfig.sessions` (`sourceKind` filesystem/project_root/github_repo) +
  `agentPlatforms`; `ProjectPathResolver` resolves them. ADR-006: registry DB-authoritative,
  `projects.json` import/export-only but readable as offline seed.
- Standalone `packages/ccdash_cli/` deps = httpx/typer/ccdash-contracts only; **cannot**
  host direct-parse without vendoring backend.

## Chosen direction
**Approach 2b** — local cache DB (`~/.ccdash/offline-cache.db`, `:memory:` via
`--ephemeral`) + synchronous scoped `sync_project(allow_writeback=False)` from a new
`bootstrap_offline()`, then the existing command/agent_queries stack runs unchanged.
Highest reuse, lowest new code, closes the two verified gaps. Approach 1 (filesystem
repos) documented as a future option.

## Open decisions (recommendations baked into plan; confirm before execution)
- A: offline target = **repo-local `backend/cli/` only** (standalone stays HTTP-only).
- B: **2b default**, 2a via `--ephemeral`.
- C: **reuse `projects.json` export shape** for the offline config (+ `--config` override).
- D: **explicit `--offline` flag / `CCDASH_OFFLINE=1`** (no auto-fallback in v1).

## Execution intent
After plan + decisions confirmed: run a phased workflow (Phase 0→3). Backend tests via
**named files only** (pytest collection hang). Add CLI smoke against a JSONL fixture.

## Artifacts
- Understanding workflow run: `wf_69ca690b-230` (5 readers; results captured into plan §3).

---

## Refined implementation design (verified 2026-06-15) — authoritative for delegates

Execution decisions locked (user: "proceed with the plan", recommendations A–D accepted).
Implementation is delegated to ICA Claude (`~/ica-claude.sh`, opus[1m]) per user request;
orchestrator (Opus) verifies + commits.

### Verified integration points
- **Global options**: `backend/cli/main.py:24` `@app.callback() def main(output, project)` — add
  `--offline` (bool), `--ephemeral` (bool), `--refresh` (bool), `--config` (path) here; set them as
  `runtime.OFFLINE` / `runtime.EPHEMERAL` / `runtime.REFRESH` / `runtime.OFFLINE_CONFIG` module globals
  (mirrors how `OUTPUT_MODE`/`PROJECT_OVERRIDE` are set).
- **DB path override**: `backend/db/connection.py:23` `DB_PATH = config.DB_PATH` is a module global;
  `get_connection()` (line 32-62) uses it directly. Offline bootstrap sets `connection.DB_PATH = <offline db>`
  BEFORE the first `get_connection()`. `_connection` is a process singleton (fine — one CLI process).
- **Migrations**: `await backend.db.migrations.run_migrations(db)` — the call `bootstrap_cli` omits.
- **Sync (worker pattern to mirror)**: `backend/adapters/jobs/runtime.py:428-435`:
  `sessions_dir, docs_dir, progress_dir = bundle.as_tuple()` →
  `await sync_engine.sync_project(project, sessions_dir, docs_dir, progress_dir, …)`.
  Offline call: `SyncEngine(db).sync_project(project, sessions_dir, docs_dir, progress_dir,
  force=REFRESH, allow_writeback=False, capture_analytics=False,
  backfill_session_intelligence=False, trigger="cli-offline")`.
- **Project + path resolution (NO DB needed for the JSON read)**: `DbProjectManager._load_snapshot()`
  (`backend/project_manager.py:417-425`) **auto-seeds projects.json → DB when the DB has no rows**
  (lazy, automatic, no flag). This IS the ADR-006 bootstrap-seed path → offline is compliant.
  `mgr.get_project(id)` / `mgr.get_active_project()` / `mgr.resolve_project_paths(project, refresh=).as_tuple()`.

### Two gotchas that MUST be honored
1. **Do NOT reuse the module singleton `db_project_manager`** (`project_manager.py:366-367` freezes
   `_db_path` from `connection.DB_PATH` at import time → split-brain vs the offline DB). Construct a
   **fresh** `DbProjectManager(storage_path=<projects.json>, db_path=<offline db>, db_backend="sqlite")`
   and inject via `build_core_ports(db, …, workspace_registry=ProjectManagerWorkspaceRegistry(fresh_mgr))`
   (`runtime_ports.py:43,61,133-147` accept the override).
2. **`--ephemeral` must use a temp FILE, not `:memory:`.** The registry uses a *separate synchronous*
   `SqliteProjectRepository(db_path)` connection; `:memory:` would be a different DB from the async
   `aiosqlite` connection → split-brain. Use `tempfile` db file, delete on exit.

### Offline config (Decision C)
Reuse `projects.json` shape. Resolve path: `--config` → `CCDASH_PROJECTS_FILE` (config.py) →
`~/.ccdash/projects.json` → `./projects.json`. If none found / project unresolved, exit with a clear
"offline registry not found; export via `ccdash project list --output json`" message.

### Degradation (Decision D + G4)
Worker-only enrichments (pricing/cost, analytics KPIs, context observability, intelligence facts)
are null offline. Formatters must render "unavailable offline" (not 0/blank) and human output shows an
offline banner. `capture_analytics=False`/`backfill_session_intelligence=False` keep offline sync fast.

### File plan
- `backend/cli/offline.py` (NEW): config-path resolution + `bootstrap_offline()` + `ensure_synced()`.
- `backend/cli/runtime.py`: module globals + route `execute_query` through offline bootstrap when `OFFLINE`.
- `backend/cli/main.py`: global options.
- formatters/output: degradation markers + banner.
- `backend/tests/test_cli_offline_sync.py` (NEW, named — never unscoped pytest): real DB + migrations +
  small JSONL fixture under `backend/tests/fixtures/offline/`; assert non-zero sessions, idempotent
  re-run, `allow_writeback=False` (no repo mutation), null-enrichment renders as "unavailable offline".

### Delegation log
- ICA opus[1m] — Phase 0+1. **DONE.** Deliverable A (`backend/cli/offline.py`) landed on first run; the
  delegate then died on "Prompt is too long" (I had injected the FULL CLAUDE.md via
  `--append-system-prompt-file` — too big for the ICA gateway's effective cap under `--bare`).
  **Lesson: inject a compact curated context note, NOT the full CLAUDE.md; let `--add-dir` carry the rest.**
  Re-ran B/C/D with a lean context pack (`tmp/ccdash-delegate-context.md`) → runtime.py wiring + main.py
  options + `backend/tests/test_cli_offline_sync.py` (3 real e2e tests).
- Verified in-session (not just the delegate report): `import backend.cli.main` OK; 3/3 tests pass;
  all 4 options register in `--help`; **full CLI smoke** `python -m backend.cli --offline --ephemeral
  --config <tmp registry> --project <id> status project` → exit 0, real JSON, both raw jsonl sessions
  parsed with no server/worker. `total_cost:0.0` confirms pricing degrades to a contract state (→ Phase 2).
- ICA sonnet[1m] — Phase 2+3. **DONE.** Lean context pack again (no full CLAUDE.md). Delivered:
  stderr offline banner in `runtime.execute_query` (Phase 2 T2-003 — formatters/DTOs untouched, per-field
  markers ruled out as YAGNI); standalone-CLI unreachable-server hint (`target.py`); `docs/guides/offline-cli.md`;
  CLAUDE.md "Key Conventions" bullet.
- Orchestrator verified in-session: banner on **stderr only**, stdout stays VALID JSON (✓ critical — no
  corruption); offline test 3/3; standalone target tests 33/33; session get/transcript/search + status all
  work offline. Closed a doc/reality gap myself (1-line): wired `CCDASH_OFFLINE=1` env var
  (`envvar="CCDASH_OFFLINE"` on the `--offline` Typer option) — Decision D contract; verified engages offline
  with no flag. (import_boundary 4-failure baseline is pre-existing/environmental, unrelated.)

## STATUS: FEATURE COMPLETE (all 4 phases). Commits on `plan/ccdash-offline-cli-direct-source`:
- 1bde430 plan (draft) · 0479db1 Phase 0+1 (offline.py + wiring + e2e test) · (this) Phase 2+3 (banner+docs+hint+env).
Future (Non-Goals, documented): Approach-1 zero-DB filesystem repos; auto-fallback on connection failure;
standalone client-side HTTP cache; offline pricing via bundled catalog.
