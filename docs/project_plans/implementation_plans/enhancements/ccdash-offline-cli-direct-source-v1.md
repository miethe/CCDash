---
title: "Offline-Capable CCDash CLI \u2014 Direct-from-Source Session Access"
slug: ccdash-offline-cli-direct-source
version: v1
status: completed
type: implementation-plan
created: 2026-06-14
owner: Nick Miethe
related:
- backend/cli/
- packages/ccdash_cli/
- backend/application/services/agent_queries/
- backend/db/sync_engine.py
- backend/parsers/
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
updated: '2026-06-15'
---

# Offline-Capable CCDash CLI — Direct-from-Source Session Access

## 1. Problem & Motivation

Today CCDash insight surfaces (CLI, MCP, REST) all read from a **pre-populated cache
DB** that a separate worker/backend keeps in sync from the filesystem. When the
backend isn't running — a fresh checkout, a laptop without the stack up, a teammate
who only installed the standalone CLI — there is **no way to get session-log insight at
all**:

- **Standalone CLI** (`packages/ccdash_cli/`, pipx-installable) is HTTP-only. Server
  unreachable ⇒ `ConnectionError` ⇒ exit 4, no fallback. *(verified: `runtime/client.py`,
  `commands/target.py`)*
- **Repo-local CLI** (`backend/cli/`) imports backend code directly but is **100%
  DB-driven**. `bootstrap_cli()` opens a connection and builds ports but **never runs
  migrations and never triggers a sync** — it assumes a worker already populated the DB.
  Empty/stale DB ⇒ empty results or a graceful "error" status. *(verified:
  `backend/cli/runtime.py:29-44` — no `run_migrations`, no `SyncEngine`)*

The user goal: **make the CLI capable offline** — a wrapper that reads session logs
**direct from source for a configured harness**, parses them **directly**, and produces
insight **without the backend running** — ideally by **reusing a consolidated core**
imported by both CLI and backend rather than a parallel implementation.

## 2. Goals / Non-Goals

### Goals
- G1. Run high-value read commands (`session search/get/transcript`, `status`, and
  `feature` to the extent links exist) **with no server and no worker**, against a
  project's raw session logs.
- G2. Locate session sources via an **offline config file** (project → harness →
  session-log paths) without requiring the registry DB.
- G3. **Maximize reuse** of existing backend code (parsers, ingest, agent_queries) — no
  fork of the query/DTO logic.
- G4. **Degrade gracefully**: fields that genuinely require the full backend (live
  pricing, derived analytics snapshots, cross-run intelligence) surface as explicit
  "unavailable offline" states, never crashes. (Aligns with the resilience-by-default
  invariant: missing optional field = contract state, not a bug.)

### Non-Goals
- N1. Offline **writes** / mutation of project repos (offline is read-only;
  `sync_project(allow_writeback=False)`).
- N2. Full agent_queries parity offline (pricing recalculation, analytics rollups,
  sentiment/churn/scope-drift intelligence facts) — these are sync/worker-derived and
  out of scope for v1.
- N3. Turning the **standalone pipx CLI** into a direct-parse engine (see §6 Decision A).
- N4. New harness/platform parsers (we reuse the existing `claude_code` / `codex`
  platform adapters).

## 3. Architecture Findings (verified)

Source: 5-reader parallel architecture map + direct code verification (2026-06-14).

| Area | Finding | Implication |
|------|---------|-------------|
| Repo-local CLI | `bootstrap_cli()` opens DB + builds `CorePorts`; **no migrations, no sync** (`backend/cli/runtime.py:29-44`). Uses `test` profile (sync disabled). | The *only* gap to offline is "DB is empty because nobody synced." Closing it = run migrations + a synchronous scoped sync. |
| agent_queries | Services take `CorePorts` via **function-level DI**; `ports.storage.sessions()` resolves through `RepositoryBackedStorageUnitOfWork._repo_builders` (`backend/adapters/storage/base.py:133,218`). Repos are `@runtime_checkable` Protocols (`db/repositories/base.py`). | Two clean injection seams exist: swap **repo builders** (Approach 1) *or* seed a **real DB** the existing builders read (Approach 2). |
| Cache layer | `@memoized_query` calls `get_data_version_fingerprint()` which queries raw DB tables on every call (`agent_queries/cache.py`). | A pure no-DB path (Approach 1) must supply a filesystem fingerprinter or disable cache (TTL=0). A real-DB path (Approach 2) works unchanged. |
| Reporting | `reporting.py:159` passes `ports.storage.db` raw to `list_workflow_registry()` — only non-repository DB access in the query services. | Approach 1 must wrap this; Approach 2 is unaffected. |
| Sync engine | `SyncEngine(db)` + public `async sync_project(project, sessions_dir, docs_dir, progress_dir, *, allow_writeback=True, capture_analytics=True, …)` (`db/sync_engine.py:1372,3069`). Container pattern = `run_migrations(db)` then `SyncEngine(db)` (`runtime/container.py:113,272`). Recent-first + light-mode incremental already built in. | The **entire ingest→enrich→query pipeline is already a reusable core** callable synchronously from the CLI. `allow_writeback=False` gives read-only safety for free. |
| Parsers | `claude_code/parser.py` returns a fully-typed `AgentSession` with all transcript-derivable fields incl. launch-time capture sidecars. Sync-time-only enrichments (pricing, context observability, usage attribution, intelligence facts, commit correlations, badges) **cannot** be computed from a bare transcript parse. | Offline can serve ~40-50% of fields directly; the rest must degrade. |
| Config / paths | Project record carries `pathConfig.sessions` (`sourceKind` ∈ filesystem/project_root/github_repo) + `agentPlatforms`. `ProjectPathResolver` already resolves these (`services/project_paths/resolver.py`). Registry is **DB-authoritative (ADR-006)**; `projects.json` is import-seed/export-only but still readable on bootstrap when DB is empty. | An offline config = a minimal slice of the `projects.json` export shape; resolution reuses `ProjectPathResolver`. |
| Standalone CLI | `packages/ccdash_cli/` depends on `httpx, typer, ccdash-contracts` **only** — zero backend imports by design (`pyproject.toml`). No cache, no storage, no parsers. | Offline-direct-parse **cannot** live here without vendoring `backend/` and breaking the publication boundary. |

## 4. Scope Verdict

**This is more than a quick-feature.** It introduces a config contract, an offline
bootstrap path, a synchronous sync driver, graceful-degradation wiring across multiple
commands, plus tests and docs — a focused **4-phase feature**, not a 1-3 file change.
Recommended execution: phased workflow run after plan approval.

## 5. Approach Options

| # | Approach | Reuse | New code | "Direct parse, no backend" fidelity | Effort | Verdict |
|---|----------|-------|----------|--------------------------------------|--------|---------|
| 1 | **Filesystem-backed repositories** — `FilesystemSessionRepository` etc. satisfying the Protocols, registered as `repo_builders`, `db=None`. agent_queries runs against parsed files with no DB. | High (query layer) | High — implement every Protocol method against parsed data **+** filesystem fingerprinter **+** wrap `reporting.py` raw-DB call. | Highest (literally no DB) | L | Elegant long-term; large, several couplings to solve, several unvalidated assumptions (`db=None` through builders). |
| 2a | **Ephemeral seed DB** — parse source into a `:memory:`/temp SQLite per invocation via `sync_project`, query the normal stack, throw away. | Maximal (whole pipeline) | Low | High (CLI parses; backend server/worker not running) | S | Always fresh; pays parse cost each call (mitigated by light-mode manifest). |
| 2b | **Local cache DB + synchronous scoped sync** — maintain `~/.ccdash/offline-cache.db`; on each offline command run `migrations` + incremental `sync_project` for the target project, then query the normal stack. | Maximal (whole pipeline) | Low–Med | High (same as 2a; CLI owns the parse, no server) | S–M | **Recommended.** Closes the two verified gaps (no-migrations, no-sync) with existing machinery; repeat calls are cheap via recent-first/light-mode incremental. |
| 3 | **Thin parse-only command group** — call parsers directly, format output, bypass agent_queries. | Low | Med | High | M | Fastest to a demo but **duplicates DTO/projection logic** and diverges from the "consolidated core" goal. Rejected. |

### Recommendation: **Approach 2b** (with 2a as a `--no-cache`/`--ephemeral` toggle)

Rationale:
- It realizes the user's "**core service imported from both**" goal literally — the shared
  core is the **existing** `SyncEngine` + `session_ingest_service` + `agent_queries`
  stack, now invoked **synchronously from the CLI** instead of only from the worker. No
  parallel implementation, no DTO fork.
- It closes exactly the two verified gaps (`bootstrap_cli` runs no migrations / no sync)
  using code paths the container already exercises.
- `allow_writeback=False` gives read-only safety with no new guard.
- Graceful degradation is mostly free: the sync-time enrichments that need external
  catalogs already write **nullable contract states**, which the formatters already
  tolerate.
- Approach 1 remains a viable **future** evolution if a truly zero-DB path is ever
  required; nothing here blocks it.

## 6. Open Decisions (confirm before execution)

> These are the load-bearing forks. Recommendations in **bold**; the plan in §7–§8
> assumes them. Flag any change and the phase breakdown adjusts.

- **Decision A — Which CLI is the offline target?**
  **➤ Repo-local `backend/cli/` only (recommended).** It already imports the backend
  core; offline-direct-parse is impossible in the decoupled standalone pipx package
  without vendoring `backend/`. The standalone CLI's offline story = "use
  `backend/.venv/bin/ccdash --offline`" (documented), with an *optional, separate* future
  enhancement of client-side HTTP-response caching for degraded reads. *Alternative:
  invest in a shared `ccdash-offline-core` package the standalone CLI could depend on —
  larger, deferred.*

- **Decision B — Sync model: 2b local-cache (recommended) vs 2a ephemeral?**
  **➤ 2b as default, 2a via `--ephemeral`.** 2b is faster on repeat use; 2a guarantees
  zero persisted state for the privacy-sensitive.

- **Decision C — Offline config file: reuse `projects.json` vs new `~/.ccdash/offline.toml`?**
  **➤ Reuse the `projects.json` export shape**, discovered at `CCDASH_PROJECTS_FILE` →
  `~/.ccdash/projects.json` → repo `./projects.json`. Avoids a second registry format;
  ADR-006 already treats `projects.json` as the import/export artifact. A thin
  `--config <path>` override is added. *Alternative: a purpose-built minimal TOML — fewer
  fields but a new contract to maintain.*

- **Decision D — Offline trigger: explicit `--offline` vs auto-fallback on connection failure?**
  **➤ Explicit `--offline` flag (+ `CCDASH_OFFLINE=1`) for v1**; auto-fallback is a
  follow-up once UX of "silently served stale local data" is validated. Explicit is
  predictable and scriptable.

## 7. Recommended Design (Approach 2b)

```
ccdash --offline <command> [--project P] [--config path] [--ephemeral] [--refresh]
        │
        ▼
backend/cli/runtime.py :: bootstrap_offline()            # NEW, parallel to bootstrap_cli()
        │  1. resolve offline cache DB path (~/.ccdash/offline-cache.db | :memory: if --ephemeral)
        │  2. connection.get_connection() against that DB
        │  3. await migrations.run_migrations(db)         # the gap bootstrap_cli skips
        │  4. build_core_ports(db, profile=test)
        ▼
backend/cli/offline_sync.py :: ensure_synced(project_id) # NEW thin driver
        │  1. load offline registry (projects.json shape) — NO DB dependency
        │  2. resolve Project + ProjectPathResolver → (sessions_dir, docs_dir, progress_dir)
        │  3. engine = SyncEngine(db)
        │  4. await engine.sync_project(project, sessions_dir, docs_dir, progress_dir,
        │         force=opts.refresh, allow_writeback=False,
        │         capture_analytics=False, backfill_session_intelligence=False, trigger="cli-offline")
        ▼
<existing command> → agent_queries service → ports.storage.* → local cache DB   # UNCHANGED
        ▼
formatter marks pricing/analytics/intelligence as "unavailable offline" where null
```

Key properties:
- **No new query/DTO code.** Commands and agent_queries services run verbatim.
- **Incremental.** After first sync, recent-first + light-mode manifest make repeat
  offline calls cheap; `--refresh` forces a full re-parse.
- **Read-only & non-mutating.** `allow_writeback=False`; offline cache lives under
  `~/.ccdash/`, never touches the project repo or the main `data/ccdash_cache.db` (unless
  the operator points `--config`/env there deliberately).
- **Degradation flags.** `capture_analytics=False` / `backfill_session_intelligence=False`
  skip worker-grade enrichment for speed; formatters annotate the resulting nulls.

## 8. Phased Implementation Plan

> Task IDs `T{phase}-{nnn}`. Each phase ends with named-file backend tests (per the
> pytest-collection-hang convention — never unscoped `pytest backend/tests`) and, for any
> command-output change, a CLI smoke against a real session-log fixture.

### Phase 0 — Offline config contract + DB-free path resolution *(foundation)*
- **T0-001** Define the offline registry contract (subset of `projects.json` export:
  `projects[].{id,name,path,pathConfig.sessions,agentPlatforms}`, `activeProjectId`).
  Document required vs dropped fields.
- **T0-002** `backend/cli/offline_config.py`: loader resolving `--config` → `CCDASH_PROJECTS_FILE`
  → `~/.ccdash/projects.json` → `./projects.json`; build `Project` models **without** the
  DB-backed `DbProjectManager`.
- **T0-003** DB-free session/doc/progress path resolution reusing `ProjectPathResolver`
  (filesystem + project_root `sourceKind`; `github_repo` → explicit "unsupported offline").
- **AC0**: `ccdash --offline status --project X` resolves the correct session dir from a
  config file with no DB and no server (assert resolution, not yet query).
- **Tests**: `backend/tests/test_cli_offline_config.py` (new, named).

### Phase 1 — Offline bootstrap + synchronous scoped sync *(the core wiring)*
- **T1-001** `bootstrap_offline()` in `backend/cli/runtime.py`: cache-DB path resolution
  (default `~/.ccdash/offline-cache.db`, `:memory:` when `--ephemeral`), `run_migrations`,
  `build_core_ports`.
- **T1-002** `backend/cli/offline_sync.py :: ensure_synced(project_id, *, refresh)`:
  constructs `SyncEngine(db)`, calls `sync_project(..., allow_writeback=False,
  capture_analytics=False, backfill_session_intelligence=False, trigger="cli-offline")`.
- **T1-003** Global `--offline` / `--ephemeral` / `--refresh` options + `CCDASH_OFFLINE`
  env on the root Typer app; route `execute_query` through `bootstrap_offline` +
  `ensure_synced` when offline.
- **AC1**: On a project with **no server/worker and an empty/absent main DB**,
  `ccdash --offline status` returns real, freshly-parsed session/feature status.
- **Tests**: `backend/tests/test_cli_offline_sync.py` (new) — end-to-end against a small
  JSONL fixture; assert non-zero session counts and idempotent re-run (incremental skip).

### Phase 2 — Command surface + graceful enrichment degradation
- **T2-001** Verify/extend `session search`, `session get`, `session transcript` offline
  (transcript depends on `session_messages` — confirm `sync_project` populates it offline).
- **T2-002** `status` + `feature` offline: forensics to the extent entity-links are built
  during the offline sync (`rebuild_links=True`).
- **T2-003** Degradation markers: formatters render "unavailable offline" (not 0/blank)
  for `totalCost`/pricing, analytics KPIs, intelligence facts when null in offline mode;
  add an offline banner to human output.
- **AC2**: Each targeted command runs offline; output **clearly distinguishes** "no data"
  from "unavailable without full backend." No crashes on null enrichment fields.
- **Tests**: extend `test_cli_offline_sync.py` per command; a degradation-rendering unit test.

### Phase 3 — Standalone-CLI integration decision, tests, docs
- **T3-001** Implement Decision A: document standalone-CLI offline = repo-local
  `--offline`; add a clear "server unreachable" hint pointing operators to it
  (`packages/ccdash_cli/.../commands/target.py`).
- **T3-002** Full test pass (named files only): config, path resolution, bootstrap, sync,
  degradation, idempotency. Standalone CLI tests: `python -m pytest packages/ccdash_cli/tests/ -v`.
- **T3-003** Docs: `docs/guides/offline-cli.md` (config format, commands, what degrades and
  why) + a CLAUDE.md "Key Conventions" bullet + CHANGELOG entry via `/release:bump`.
- **AC3**: Green tests; a new operator can, from docs alone, configure and run offline
  insight on a fresh checkout with the stack down.

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Offline sync mutates project repos (frontmatter write-back) | `allow_writeback=False` (verified param); assert no writes in tests. |
| Parse cost on large session dirs each call | Recent-first window + light-mode manifest (already in `sync_engine`); `--ephemeral` opt-in; default persistent cache. |
| Operators confuse "empty offline result" with "stale" | Explicit `--offline` (Decision D) + offline banner + freshness from `sync_state`. |
| `github_repo` source kind needs network/credentials | Explicitly unsupported offline with a clear message (Phase 0). |
| Transcript needs `session_messages` populated | T2-001 verifies `sync_project` writes canonical `session_messages` in offline path. |
| `projects.json` may not exist when DB-only projects were added via UI | Doc the `export_to_json()` / `ccdash project list --output json` path to seed an offline config; `--config` override. |
| Cache DB schema drift vs new migrations | Offline bootstrap always runs `run_migrations` first (same as container). |
| Scope creep toward full Approach-1 parity | Non-Goals N2 fences this; Approach 1 stays a documented future option. |

## 10. Test Strategy

- Backend: **named** test files only (`test_cli_offline_config.py`, `test_cli_offline_sync.py`)
  — never unscoped `pytest backend/tests` (collection hang).
- Use a committed minimal JSONL session fixture (+ optional `.capture.json` sidecar) under
  `backend/tests/fixtures/offline/`.
- Assert: DB-free path resolution; migrations-on-empty-DB; non-zero parsed counts;
  incremental idempotent re-run; `allow_writeback=False` (no repo mutation); null
  enrichment fields render as "unavailable offline."
- CLI smoke: `backend/.venv/bin/ccdash --offline status --project <fixture>` with the
  stack down.

## 11. Out of Scope / Future

- Approach 1 zero-DB filesystem repositories (+ filesystem fingerprinter, `reporting.py`
  wrap) — revisit only if a truly DB-less path is required.
- Auto-fallback to offline on connection failure (Decision D follow-up).
- Standalone-CLI client-side HTTP response cache for degraded reads.
- Offline pricing via a bundled/cached pricing catalog snapshot.
- A shared `ccdash-offline-core` package consumable by the standalone CLI.
