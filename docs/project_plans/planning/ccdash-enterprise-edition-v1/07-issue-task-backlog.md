---
schema_version: 2
doc_type: report
report_category: investigations
title: CCDash Enterprise Edition Issue & Task Backlog
status: completed
created: 2026-05-30
updated: '2026-06-02'
feature_slug: ccdash-enterprise-edition-v1
audience:
- ai-agents
- developers
related_documents:
- docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Enterprise Edition — Issue & Task Backlog

This is the **executable backlog** derived from the 130-issue ledger (`issue-ledger.md`), the
completed-work & gaps ledger (`completed-and-gaps.md`), and the steering brief (`synthesis-brief.md`).
Issues that recurred across domains are **deduped and merged** into single tasks (e.g. the four
"ingestion disabled by default" findings → one P0 task). Tasks are grouped into the **Phase 0-6**
boundaries defined in the synthesis brief §7. Every **critical** and **high** ledger issue maps to a
task here; medium/low issues are folded into the nearest task or carried as discrete lower-priority rows.

**Task schema:** `ID | Title | Area | Complexity (S<0.5d / M 1-2d / L 3-5d / XL >1wk) | Priority (P0/P1/P2) | Evidence (file:line) | Acceptance criteria | Depends on`.

**Phase intent (per synthesis brief §7):**

- **Phase 0** — Enterprise Liveness Hotfix (container wiring; live data flows; fail-loud readyz; e2e smoke).
- **Phase 1** — Storage Hygiene & DB Performance (retention/TTL, dedupe, pragmas, indexes, batch upserts, materialized badges).
- **Phase 2** — Cache & Query Correctness (shared cache, scoped+cached fingerprint, sync-invalidation, summary/detail split).
- **Phase 3** — DB-backed Project Registry & Multi-Project Worker (projects table, OQ→DB, watcher registry, durable queue, supervision).
- **Phase 4** — Frontend Performance Finish (TQ completion, pagination/virtualization, polling cleanup, deferred mount, fonts, Gemini key).
- **Phase 5** — Command Center as Multi-Project Control Plane (runtime flag, cross-project rollups, ranked next-work, deep-link detail, artifacts, ARC/MeatyWiki scaffolds).
- **Phase 6** — Observability, Retention Ops & Validation (OTEL gaps, scheduled retention/VACUUM, load test, container e2e CI gate).

---

## Top 12 P0 Tasks (Quick-Start for the Next Workflow)

These are the highest-ROI, lowest-risk tasks that unblock everything else. Execute these first.

| # | Task ID | Title | Phase | Why first |
|---|---------|-------|-------|-----------|
| 1 | **P0-001** | Flip ingestion + worker startup-sync defaults ON; fold `live-watch` into default enterprise topology | 0 | Without this a standard `docker compose up` ingests nothing — empty DB (merges 4 critical findings). |
| 2 | **P0-002** | Auto-derive container path aliases from `ResolvedProjectPaths`; validate host paths resolve in-container | 0 | Host `~/...` paths in `projects.json` open verbatim in-container → zero files found. |
| 3 | **P0-003** | Fail-loud `readyz`: FAIL when watcher watch-paths == 0 | 0 | Silent failure today — watcher watches nothing but `readyz` passes. |
| 4 | **P0-004** | Force polling on bind mounts (`WATCHFILES_FORCE_POLLING=true` default for worker-watch) | 0 | `watchfiles` inotify does not fire on Docker Desktop bind mounts. |
| 5 | **P0-005** | Make project registry writable in container (drop `read_only` / mount rw) so `_save()` migration succeeds | 0 | `read_only:true` mount + `_save()` on startup migration = `PermissionError` crash. |
| 6 | **P0-013** | CI `docker compose up` e2e smoke: assert sessions appear in API after ingest | 0 | The acceptance gate that proves Phase 0 actually works end-to-end. |
| 7 | **P1-001** | `analytics_entries` retention/TTL job + dedupe (1.8M rows / 466 MB, zero retention) | 1 | Unbounded growth; the single largest live-table bleed. |
| 8 | **P1-002** | Drop duplicate `session_logs` after canonical `session_messages` written (~1.75 GB dead) | 1 | 3.3 GB dual-transcript storage; ~1.75 GB never purged. |
| 9 | **P1-007** | Fix `_capture_analytics` N+1 (~11.7K–15K queries/snapshot → batched) | 1 | Largest per-sync query storm; throttles every worker cycle. |
| 10 | **P2-001** | Shared distributed cache (Valkey/Redis or Postgres-backed) replacing per-replica `TTLCache` | 2 | "Single most important enterprise correctness fix" — kills cold/inconsistent per-replica cache. |
| 11 | **P2-003** | Project-scope + cache the fingerprint (`entity_links.project_id`; cache fingerprint result) | 2 | Every cached request runs a full global `entity_links` GROUP_CONCAT scan first. |
| 12 | **P3-001** | Replace `projects.json` with a DB-backed `projects` table | 3 | Local-file registry breaks multi-replica containers; blocks true multi-project. |

---

## Phase 0 — Enterprise Liveness Hotfix

**Goal:** a standard enterprise `docker compose up` ingests live data, fails loud when misconfigured, and is
proven by an e2e smoke test. Mostly default flips, path-alias derivation, and a readiness contract — no new
subsystems. Unblocks all enterprise use.

**Merged findings:** The four separate "ingestion disabled by default" issues (ledger lines 15, 16, 21, 24)
and the two "live-watch not in default startup" issues (lines 22, 260) collapse into **P0-001**. The two
host-path-resolution findings (lines 20, 257) and the alias-derivation findings (lines 56, 180) collapse into
**P0-002**.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P0-001** | Flip enterprise ingestion + worker startup-sync defaults ON; fold `live-watch` into default enterprise topology | containerization | M | P0 | `container.py:237-242`; `compose.yaml:133`; ledger 15,16,21,22,24,260 | `docker compose up` (no extra `--profile`) instantiates `SyncEngine`; `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` and `CCDASH_WORKER_STARTUP_SYNC_ENABLED` default true in enterprise anchor; worker-watch is part of the default enterprise stack | — |
| **P0-002** | Auto-derive container path aliases from `ResolvedProjectPaths`; validate `projects.json` host paths resolve in-container | containerization | M | P0 | `source_identity.py` (alias not auto-populated); `FilesystemProjectPathProvider.resolve()`; ledger 20,56,180,257; gaps `container-deploy`:257 | `SourceIdentityPolicy` populated from `ResolvedProjectPaths` without operator setting 6 env vars; registration-time validation that resolved `sessions_dir`/`docs_dir` exist inside a mount alias; opaque-hash keys no longer produced when mount vars absent | P0-001 |
| **P0-003** | Fail-loud `readyz`: FAIL when worker-watch watch-paths == 0 (`configured_no_paths`) | containerization | S | P0 | `runtime.py:422-463`; gaps `ingestion-fs`:178; ledger 54 | `readyz` returns non-ready when watcher resolves zero valid paths; probe surfaces `configured_no_paths` as a failure, not a silent pass | P0-002 |
| **P0-004** | Force polling on bind mounts — `WATCHFILES_FORCE_POLLING=true` default for worker-watch | containerization | S | P0 | `compose.yaml:175`; ledger 55; gaps `ingestion-fs`:179 | worker-watch service defaults `WATCHFILES_FORCE_POLLING=true`; watcher fires events on Docker Desktop bind mounts in the smoke test | P0-001 |
| **P0-005** | Make project registry writable in container so `ProjectManager._save()` migration succeeds | containerization | S | P0 | `ProjectManager._save()`; `compose.yaml` `read_only:true`; ledger 66; gaps `container-deploy`:261 | `projects.json` mount is writable (or migration writes to a writable path); no `PermissionError` on startup schema migration | P0-001 |
| **P0-006** | Implement `CCDASH_WORKER_WATCH_PROJECT_ID` (and `*_STARTUP_SYNC_ENABLED`) in Python `config.py` | containerization | S | P0 | `config.py` (vars read only at compose layer); ledger 58,111; gaps `workers-runtime`:208,216 | `CCDASH_WORKER_WATCH_PROJECT_ID`, `CCDASH_WORKER_STARTUP_SYNC_ENABLED`, `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED` are read by `config.py`; k8s/bare-container deploys bind correctly without compose | P0-001 |
| **P0-007** | Add `frontend` `depends_on: api` so it does not serve 502s at startup | containerization | S | P1 | `compose.yaml`; ledger 68; gaps `container-deploy`:263 | frontend service waits for api health before accepting traffic; no startup 502s in smoke test | — |
| **P0-008** | Handle `worker-watch` in `entrypoint.sh` case statement | containerization | S | P1 | `deploy/runtime/entrypoint.sh`; ledger 69,117; gaps `container-deploy`:264, `completed-work`:300 | `CCDASH_RUNTIME_PROFILE=worker-watch` launches without a `command:` override; no fall-through error case | — |
| **P0-009** | Remove dead `CCDASH_PROJECTS_FILE` env var or wire it into `config.py`/`ProjectManager` | containerization | S | P2 | `config.py` (never reads it); ledger 67; gaps `container-deploy`:262 | `CCDASH_PROJECTS_FILE` either drives the registry path or is removed from docs/onboarding script | — |
| **P0-010** | Fix/retire diverged `compose.hosted.yml` for current worker requirements | containerization | M | P1 | `compose.hosted.yml`; ledger 70; gaps `container-deploy`:265 | hosted compose mounts filesystem volumes, sets `CCDASH_WORKER_PROJECT_ID`, runs worker non-root, uses hardened Dockerfiles — or is explicitly deprecated | P0-001 |
| **P0-011** | Add `pg_advisory_lock` around `run_migrations()` to prevent api/worker DDL race | containerization | M | P1 | `postgres_migrations.py:1497-2176`; ledger 115; gaps `container-deploy`:266 | api and worker both call `run_migrations()` on fresh Postgres without DDL race; second caller waits on advisory lock | — |
| **P0-012** | Watcher-triggered delete must use canonical source key, not raw path string | ingestion | S | P1 | `sync_engine.py:3944`; ledger 53; gaps `ingestion-fs`:177 | file-deletion event matches the canonical `ccdash-source:v1/...` key stored at ingest (`source_identity.py:120-138`); no orphaned DB rows after delete | P0-002 |
| **P0-013** | CI `docker compose up` e2e smoke test asserting sessions appear in API | testing | M | P0 | gaps `ingestion-fs`:185 ("no e2e container smoke test"); brief §7 Phase 0 | CI brings up the enterprise stack, drops a session JSONL into a mounted path, and asserts the API returns the session within a bounded timeout; gate is required for Phase 0 exit | P0-001,P0-002,P0-003,P0-004 |
| **P0-014** | Startup warning when enterprise profile + ingestion enabled + DB empty + zero watch paths | containerization | S | P2 | gaps `multi-project`:236; ledger 132 | operator sees an explicit log/probe warning explaining why data is missing (no paths / not registered), instead of a silent empty DB | P0-003 |
| **P0-015** | Reconcile `CCDASH_STARTUP_SYNC_LIGHT_MODE` default across `config.py`/`runtime.py`/`sync_engine.py` | ingestion | S | P2 | ledger 106; gaps `ingestion-fs`:182 | single authoritative default for light-mode (config.py=False vs runtime.py fallback=True mismatch resolved); documented in `.env.example` | — |

---

## Phase 1 — Storage Hygiene & DB Performance

**Goal:** shrink the 10 GB SQLite DB, stop unbounded growth, and remove the worst N+1 query storms. Highly
measurable: row counts, byte sizes, query counts per sync.

**Merged findings:** the analytics-retention findings (ledger 11, 23, 120, 124, 324) collapse into **P1-001**.
The `_capture_analytics` N+1 findings (ledger 12, 77, 126) collapse into **P1-007**. The SQLite-pragma
findings (ledger 48, 76, 335) collapse into **P1-009**. The session-logs duplication findings (ledger 44, 121,
330) collapse into **P1-002**.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P1-001** | `analytics_entries` retention/TTL + dedupe job (1.8M rows / 466 MB, +3,313/sync, zero retention) | database | M | P0 | ledger 11,23,120,124,324; brief §2a | scheduled retention/pruning job caps `analytics_entries` (and `analytics_entity_links`) by age/window; row growth bounded; documented `CCDASH_ANALYTICS_RETENTION_*` env var; backfill prune of existing rows | — |
| **P1-002** | Drop duplicate `session_logs` rows after canonical `session_messages` are written (~1.75 GB) | database | L | P0 | ledger 44,121,330; brief §2a | post-write prune removes `session_logs` rows once canonical `session_messages` exist; ~1.75 GB reclaimed; transcript reads still served from canonical table; decision recorded (canonical-only + filesystem source-of-truth per brief §8) | — |
| **P1-003** | `telemetry_events.payload_json` TTL/retention (1.6 GB unbounded JSON blobs) | database | M | P0 | ledger 49,128; brief §2a | TTL/retention job caps `telemetry_events` by age; 1.6 GB blob growth bounded; `CCDASH_TELEMETRY_RETENTION_*` documented | — |
| **P1-004** | Backfill `idx_sessions_project_status_updated` via `_ensure_index` for existing DBs | database | S | P0 | ledger 42; gaps `database`:121; defined-but-unapplied at `database` COMPLETED:112 | index exists in live DB (not just DDL); `count_active`/status-filtered queries use it; `_ensure_index` migration backfills existing databases | — |
| **P1-005** | Add `sessions.source_file` index (full-table scan on every file-watch event) | database | S | P0 | ledger 43; gaps `database`:122 | `sessions.source_file` indexed; file-watch sync lookup is index-seek not full scan | — |
| **P1-006** | Tune SQLite PRAGMAs: `cache_size`, `synchronous=NORMAL`, `mmap_size`, `wal_autocheckpoint`, `temp_store` | performance | S | P0 | `connection.py:52-54`; ledger 48,76,131,335; brief §2a (8 MB cache for 9.5 GB DB) | page cache sized for the DB (not 8 MB); `synchronous=NORMAL`, `mmap_size`, `wal_autocheckpoint`, `temp_store` set at connection init; measured read-latency improvement | — |
| **P1-007** | Fix `_capture_analytics` feature-level N+1 (~11.7K–15K queries/snapshot for 367 features) | backend | L | P0 | ledger 12,77,126; gaps `database`:126; brief §2b | per-snapshot query count drops from ~12-15K to a bounded set via batched/joined reads; OTEL histogram confirms; 367-feature snapshot no longer issues per-feature round-trips | P1-004 |
| **P1-008** | Batch `entity_graph.upsert()` (25K individual commits during link rebuild → single transaction) | database | M | P0 | ledger 45; gaps `database`:127; brief §2b | link rebuild uses a batch upsert path with one (or few) transactions instead of commit-per-link; rebuild time measurably reduced | — |
| **P1-009** | Replace row-by-row INSERTs with `executemany` across telemetry/attribution/log writes | ingestion | S | P0 | ledger 75; gaps `perf-evidence`:327; brief §2b | telemetry/attribution/session_log writes use `executemany` (single batch) per write group; sync INSERT batch sizes instrumented | — |
| **P1-010** | Materialize session badge metadata (models/agents/skills) on `sessions` table | backend | M | P0 | ledger 9,74; gaps `backend-api`:91, `perf-evidence`:326; brief §2b/§2d | `command_slug`, `latest_summary`, `subagent_type`, `models_used`, `agents_used`, `skills_used` materialized on `sessions`; session list view no longer N+1 full-log-fetches per row; backfill for existing rows | — |
| **P1-011** | Wrap Postgres `upsert_logs`/`upsert_file_updates`/`upsert_tool_usage` in transactions (DELETE-then-N-INSERT non-atomic) | backend | M | P1 | ledger 47; gaps `database`:125 | each upsert wraps DELETE + INSERTs in one transaction; no partial-write window on crash | — |
| **P1-012** | Add Postgres `entity_links` UNIQUE constraint to initial DDL (ON CONFLICT silently inserts dupes on fresh install) | database | M | P1 | ledger 46; gaps `database`:129; `database` COMPLETED:118 | UNIQUE index present in initial Postgres DDL (not only post-DDL step); `ON CONFLICT` upsert works on a fresh install with no duplicate rows | — |
| **P1-013** | Fix `get_latest_entries` HAVING anti-pattern (prevents index-only early exit on 1.8M-row table) | database | S | P1 | ledger 100; gaps `database`:132 | query rewritten to permit index-only early exit; latency on `analytics_entries` reads measurably lower | P1-001 |
| **P1-014** | Add candidate partial indexes: `analytics_entries(period='point')`, `telemetry_events(event_type)` | database | S | P1 | ledger 133; gaps `database`:133 | partial indexes created; targeted analytics/telemetry filters use them | P1-001,P1-003 |
| **P1-015** | Reconcile SQLite (27) vs Postgres (28) `SCHEMA_VERSION` migration divergence | database | M | P1 | ledger 101; gaps `database`:130 | SQLite and Postgres migration chains agree on schema version semantics; divergence documented or resolved | — |
| **P1-016** | Add FTS5 index on `session_messages.content` (LIKE full-table-scan today) | database | L | P2 | ledger 122; gaps `perf-evidence`:329; brief §3 | message content search uses FTS5 (or Postgres GIN/tsvector parity) instead of `LIKE` full scan; search latency bounded on large transcripts | P1-002 |
| **P1-017** | Manifest-based scan skip for session JSONL (full rglob + N DB lookups every startup) | ingestion | M | P2 | ledger 57; gaps `ingestion-fs`:181; brief §2b | session scanner skips unchanged paths via manifest (parity with document scan `sync_engine.py:4239-4278`); startup scan no longer full-rglobs unchanged session dirs | — |
| **P1-018** | Batch backfill loops during startup sync (sequential single-row round-trips → batched/concurrent) | performance | M | P2 | ledger 108; gaps `ingestion-fs`:184 | telemetry/commit-correlation/usage-attribution backfills batched or concurrent; startup sync time reduced | P1-009 |

---

## Phase 2 — Cache & Query Correctness

**Goal:** make the cache correct and fast across replicas. Shared cache, scoped+cached fingerprint,
sync-triggered invalidation, and the summary/detail endpoint split. Depends on Phase 1's index/scoping work.

**Merged findings:** the per-replica/distributed-cache findings (ledger 13, 150) and the multi-replica
consistency findings (gaps `caching`:158) collapse into **P2-001**. The fingerprint-scan findings (ledger 14,
36, 105; gaps `caching`:154-155) collapse into **P2-003**. The bundle parallelism findings (ledger 4, 96;
gaps `backend-api`:92) collapse into **P2-007**.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P2-001** | Shared distributed cache (Valkey/Redis or Postgres-backed) replacing per-replica in-process `TTLCache` | caching | XL | P0 | `cache.py:50,294-317`; ledger 13,97,104; gaps `caching`:150,158; brief §6.1 | api + worker replicas share one cache backend; cache hits survive replica restarts and are consistent across replicas; in-process `TTLCache` is a fallback for single-node only; tech choice recorded (Valkey default, Postgres-cache fallback per brief §8) | — |
| **P2-002** | Sync-triggered cache invalidation — `sync_project()` clears affected project's cache entries | caching | M | P0 | gaps `caching`:152; ledger 51 | completion of `sync_project()` invalidates that project's cached entries; stale reads do not persist past a sync; cross-replica invalidation propagates (LISTEN/NOTIFY or pub/sub) | P2-001 |
| **P2-003** | Project-scope + cache the cache fingerprint (`entity_links.project_id`; cache fingerprint result) | database | M | P0 | `cache.py` fingerprint; ledger 14,36,105; gaps `backend-api`:95,103, `caching`:154-155; brief §2c | add `project_id` to `entity_links`; fingerprint scans only the project's rows; fingerprint result itself is cached (no ~6 DB queries before every cache lookup) | P1-008 |
| **P2-004** | Replace `feature_phases` O(N) GROUP_CONCAT fingerprint with `MAX(updated_at)+COUNT(*)` | database | S | P0 | ledger 37; gaps `backend-api`:96 | fingerprint computed via `MAX(updated_at)+COUNT(*)` instead of O(N) string concat; constant-time per call | — |
| **P2-005** | Enforce documented per-metric TTLs (`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`, `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`) | caching | S | P1 | ledger 50; gaps `caching`:151 | the two documented TTL env vars actually drive cache behavior for those metrics; verified by test that changing the value changes eviction | P2-001 |
| **P2-006** | Project-scoped cache eviction API (`clear_cache()` evicts all projects today) | caching | S | P1 | ledger 131; gaps `caching`:153 | a project-targeted eviction path exists; `open_question` resolution evicts only the affected project, not all | P2-001 |
| **P2-007** | Parallelize planning view-bundle sub-calls (6× `list_all` sequential → `asyncio.gather` + shared data pass) | backend | M | P0 | ledger 4,96; gaps `backend-api`:92; brief §2b | the 6 `list_all` scans share a single data-load pass and run via `asyncio.gather`; bundle latency measurably reduced; no redundant full scans | P2-008 |
| **P2-008** | Replace `SELECT *` `list_all` with column-projected `list_summary` variants on planning summary paths | database | M | P0 | ledger 38; gaps `backend-api`:97; brief §2b | planning summary paths use column-projected summary queries; full-row payloads reserved for detail endpoints | P1-004 |
| **P2-009** | Add `@memoized_query` to V1 single-project `PlanningCommandCenterQueryService.get_command_center` | caching | S | P0 | ledger 34; gaps `backend-api`:93 | V1 command-center build is cached via `@memoized_query` (parity with multi-project path) | P2-001 |
| **P2-010** | Add `@memoized_query` to single-project `PlanningSessionQueryService.get_session_board` | caching | S | P1 | ledger 39; gaps `backend-api`:98 | single-project session board is cached; no longer fetches 500 sessions unconditionally on every call | P2-001 |
| **P2-011** | Fast-path `get_command_center_item` by `feature_id` (no 500-item full-page scan for one feature) | backend | S | P0 | ledger 35; gaps `backend-api`:94 | single-feature retrieval queries by `feature_id` directly; no 500-item page load per item | — |
| **P2-012** | `get_feature_planning_context` must not load all features+docs for a single feature request | backend | M | P1 | ledger 40; gaps `backend-api` (context loads everything) | feature context loads only the target feature's graph/phases/docs; bounded query count per request | P2-008 |
| **P2-013** | NullGitProbe in V1 single-project command-center build (git subprocess per item today) | performance | S | P1 | ledger 41; gaps `backend-api`:99; `backend-api` COMPLETED:83 | V1 build uses NullGitProbe for off-page items (parity with MPCC-206); no git subprocess per command-center item | — |
| **P2-014** | Background cache warm-up job wired to `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` covering all 14 memoized endpoints | caching | M | P1 | ledger 99,102; gaps `caching`:156-157, `backend-api`:100; brief §2c (covers 2 of 14) | warmer covers all memoized endpoints (not 2 of 14); api-profile replicas receive warming via shared cache; warm-up honors the refresh-interval config | P2-001 |
| **P2-015** | Raise `TTLCache maxsize` from 512 for multi-project × multi-endpoint load (single-node fallback) | caching | S | P2 | ledger 97,104; gaps `backend-api`:101 | single-node fallback cache sized for project×endpoint cardinality; documented sizing guidance | P2-001 |
| **P2-016** | Add `@memoized_query` to legacy `list_features` (`/api/features`) polled every 5s with N+1 | caching | M | P1 | ledger 52; gaps `caching`:159 | legacy `/api/features` is cached server-side; N+1 removed; see also P4-005 (FE polling interval) | P1-010 |
| **P2-017** | Batch session-detail multi-query fan-out (8+ sequential round-trips today) | backend | M | P2 | ledger 98; gaps `backend-api`:102 | session detail endpoint issues a bounded, batched set of queries instead of 8+ sequential round-trips | — |
| **P2-018** | Precompute the planning graph in DB via worker (recomputed in-memory per cache TTL today) | performance | M | P2 | ledger 82; gaps `data-contracts`:368; brief §5 | planning graph precomputed and stored in DB by the worker; reads serve the precomputed graph; large project-sets no longer recompute per TTL | P3-007 |

---

## Phase 3 — DB-backed Project Registry & Multi-Project Worker

**Goal:** make CCDash genuinely multi-project: a DB-backed project registry, durable open-question state, a
per-project watcher registry, a durable job queue with supervision, and multi-project warming/analytics.

**Merged findings:** the `projects.json`-not-DB findings (ledger 17, 26, 264 across multi-project/data-contracts/
container) collapse into **P3-001**. The single-worker-per-project findings (ledger 19, 62; gaps
`workers-runtime`:211, `multi-project`:234) collapse into **P3-005**. The durable-queue/supervision findings
(ledger 59, 60, 61; gaps `workers-runtime`:209-210,214) collapse into **P3-006**.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P3-001** | Replace `projects.json` with a DB-backed `projects` table | database | L | P0 | ledger 17,26; gaps `multi-project`:233, `data-contracts`:361, `container-deploy`:257; brief §6.1 | a `projects` table is the authoritative registry; multi-replica containers read/write it; `projects.json` becomes import/bootstrap only; registration validates container-resolvable paths (ties to P0-002) | — |
| **P3-002** | Move open-question resolutions from process memory (`_OQ_OVERLAY`) to DB | database | M | P0 | ledger 78; gaps `data-contracts`:362; brief §4 | OQ resolutions persisted in DB; survive restart; consistent across replicas; `clear_cache()` on resolution evicts only the affected project (ties to P2-006) | P3-001 |
| **P3-003** | Make session primary key project-scoped (globally-unique PK risks cross-project collision) | database | L | P0 | ledger 63; gaps `multi-project`:237; brief §3 | `sessions` PK incorporates `project_id` (or composite uniqueness) so cross-project IDs cannot collide/corrupt; migration + backfill | P3-001 |
| **P3-004** | Add `project_id` to `session_logs`, `session_tool_usage`, `session_file_updates` | database | M | P0 | ledger 65; gaps `multi-project`:238; brief §3 | detail tables carry `project_id` (not relying on session_id FK uniqueness); project-scoped queries on detail tables become possible | P3-003 |
| **P3-005** | Multi-project worker: per-project `FileWatcher` registry ("watch all registered projects") | workers | XL | P0 | `file_watcher.py:307` (singleton); ledger 19,62; gaps `workers-runtime`:211, `multi-project`:234-235; brief §6.4 | singleton `FileWatcher` becomes a dict-keyed registry; one worker can watch N registered projects; one-container-per-project remains a valid isolation deployment; CLI/probe reports per-project watch state | P3-001 |
| **P3-006** | Durable task queue + supervision replacing `InProcessJobScheduler` bare `asyncio.create_task()` | workers | XL | P0 | ledger 59,60,61; gaps `workers-runtime`:209-210,214; brief §3/§6.4 | durable (Redis/Postgres-backed) queue with retry/priority/backpressure; container crash mid-sync resumes from the queue (no full re-sync); dead jobs report `dead`/`crashed` not `idle`; project-scoped scheduling | P3-001 |
| **P3-007** | Multi-project warming + analytics loop (warm/analyze all registered projects, not just bound/active) | workers | M | P0 | ledger 110,113; gaps `workers-runtime`:212, `multi-project`:240, `caching`:158; brief §3 | warming and analytics snapshot iterate all registered projects; cross-project analytics produced; no longer single-active-project only | P3-005,P2-014 |
| **P3-008** | Remove global active-project fallback in enterprise mode (headerless requests must fail-fast) | backend | M | P1 | ledger 64; gaps `multi-project`:239; brief §3 | in enterprise mode a request with no `X-CCDash-Project-Id` fails fast instead of silently routing to the global active project; local/dev mode retains fallback | P3-001 |
| **P3-009** | Wire `TelemetryExporterJob` + `ArtifactRollupExportJob` for `worker-watch` profile | workers | S | P1 | ledger 133; gaps `workers-runtime`:213 | both jobs run under `worker-watch` (not only `worker`); telemetry flushes in the live-watch topology | P0-001 |
| **P3-010** | Add `asyncio.Lock` mutex around `rebind_watcher` (race in multi-operator scenarios) | workers | S | P1 | ledger 112; gaps `multi-project`:242 | concurrent `rebind_watcher` calls are serialized; no torn watcher state under multi-operator activity | P3-005 |
| **P3-011** | Guard `projects.json` `_save()` against torn writes (synchronous unguarded write today) | multi-project | S | P1 | ledger 114; gaps `multi-project`:243 | registry persistence is atomic (temp-file + rename or DB transaction); no torn file on concurrent writes — subsumed once P3-001 lands (DB-backed) | P3-001 |
| **P3-012** | Remove module-level `container = build_worker_runtime()` orphaned at import time | workers | S | P1 | `bootstrap_worker.py:86`; ledger 109; gaps `workers-runtime`:215 | no `RuntimeContainer` built at import time; container constructed inside the bootstrap entrypoint | — |
| **P3-013** | Add task supervision states + `stale_since` threshold alarm to probe contract | workers | M | P1 | ledger 59; gaps `workers-runtime`:210,217 | probe distinguishes `idle`/`running`/`dead`/`crashed`; `stale_since` threshold alarm computed server-side, not left to operators | P3-006 |
| **P3-014** | Postgres NOTIFY listener reconnect/backoff (dropped connection permanently kills live fan-out) | integration | M | P1 | ledger 73,107; gaps `ingestion-fs`:183, `completed-work`:293 | listener auto-reconnects with exponential backoff; transient DB disconnect does not permanently kill live ingest/fan-out; covered by a reconnect test | — |
| **P3-015** | Job-queue depth metrics for analytics snapshots + cache warming (only telemetry has depth today) | workers | S | P2 | gaps `workers-runtime`:218 | analytics and warming jobs expose queue/backpressure depth metrics; parity with telemetry export | P3-006 |
| **P3-016** | Multi-project `projects.json` without explicit binding — detect/warn | multi-project | S | P2 | ledger 132; gaps `ingestion-fs`:186 | when registry has multiple projects but no worker binding, operator gets a clear warning (ties to P0-014) | P3-001 |

---

## Phase 4 — Frontend Performance Finish

**Goal:** finish the TanStack Query migration, add pagination/virtualization where missing, eliminate
`setInterval` polling, defer off-screen mounting, self-host fonts, and move the Gemini key server-side. Can
overlap Phase 1 (different owners).

**Merged findings:** the `setInterval`-sprawl findings (ledger 85; gaps `frontend-core`:29) collapse into
**P4-006**. The always-mount + concurrent-cold-load findings (ledger 30; gaps `planning-frontend`:63) collapse
into **P4-007**.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P4-001** | Server-side pagination for the planning session board (full project payload every load) | performance | L | P0 | ledger 7; gaps `planning-frontend`:61; brief §2d | session-board endpoint accepts cursor/page params; FE requests pages; full project payload no longer fetched per load | P2-010 |
| **P4-002** | Migrate V1 `PlanningCommandCenter` to TanStack Query (raw `useEffect`/local state today) | caching | M | P0 | ledger 8; gaps `planning-frontend`:62; brief §2d | V1 command center uses TQ hooks (cache + dedup); no raw `useEffect` data fetch; parity with multi-project center | P2-009 |
| **P4-003** | Make `useData()` reactive — `useQuery()` subscription, not `getQueryData()` snapshot (7 domain arrays, 13+ components) | frontend | M | P0 | ledger 27; gaps `frontend-core`:24; brief §2d | the 7 domain arrays are read via reactive `useQuery`; the 13+ consuming components update on background refetch; stale-snapshot defect gone | — |
| **P4-004** | V1 `PlanningAgentSessionBoard` virtualization (rich cards render for all sessions; CSS-scroll only) | performance | M | P0 | ledger 32; gaps `planning-frontend`:65; brief §2d | V1 board `BoardColumn` is virtualized (parity with multi-project board threshold 250); only visible cards render | P4-001 |
| **P4-005** | Raise `useFeaturesQuery` `refetchInterval` from 5s and `useFeatureSurface` list `staleTime` from 0 | performance | S | P0 | ledger 28,29,120,332; gaps `frontend-core`:25-26; brief §2d | features poll ≥30s when SSE off (was 5s → 12 req/min); list-tier `staleTime` ≥10-30s; no refetch-on-every-mount | P2-016 |
| **P4-006** | Replace `setInterval` sprawl with TQ `refetchInterval`/SSE invalidation (8+ components) | performance | L | P0 | ledger 85; gaps `frontend-core`:29 (Dashboard 10s, SystemMetricsChip 30s, ProjectBoard modal 15s, OpsPanel adaptive, SessionInspector ×2, FeatureExecutionWorkbench, TestVisualizer); brief §2d | all manual `setInterval` polls replaced with TQ `refetchInterval` or SSE-driven invalidation; visibility-aware + dedup honored | P4-003 |
| **P4-007** | Viewport-deferred mounting for session board + command center (planning home = 5 concurrent cold loads) | performance | M | P0 | ledger 30; gaps `planning-frontend`:63; brief §2d | planning home defers mounting off-screen board/center; entry no longer fires 5 concurrent cold-load requests | P4-001,P4-002 |
| **P4-008** | Correct hover-prefetch via `queryClient.prefetchQuery` (currently fetched and discarded; modal still cold) | caching | S | P1 | ledger 31; gaps `planning-frontend`:64 | hover prefetch populates the TQ cache so the modal opens warm; no fetch-and-discard | P4-002 |
| **P4-009** | Self-host planning fonts (Google Fonts CDN fails silently in restricted-egress containers) | containerization | S | P1 | ledger 94; gaps `planning-frontend`:68; brief §6 | planning fonts served from the app/container, not Google Fonts CDN; renders correctly with egress blocked | — |
| **P4-010** | Move `GEMINI_API_KEY` server-side (baked into JS bundle via Vite `define`) | integration | M | P1 | ledger 89; gaps `frontend-core`:31; brief §2d | Gemini calls proxied through the backend; key never shipped in the client bundle; container builds carry no embedded key | — |
| **P4-011** | Migrate Dashboard KPI cards + analytics series to TanStack Query (legacy imperative path shows 0 on slow load) | frontend | M | P0 | ledger 71,83; gaps `frontend-core`:27, `completed-work`:292 | Dashboard KPI + analytics series use TQ; loading skeleton/error state instead of literal `0`; 20.5s cold / 9.7s warm legacy path retired | P4-003 |
| **P4-012** | Migrate `AnalyticsDashboard` to TanStack Query (7 parallel raw fetches every mount) | frontend | M | P1 | ledger 84; gaps `frontend-core`:28 | `AnalyticsDashboard` (incl. `getArtifacts({limit:200})`) goes through TQ; cached/deduped; no 7 raw fetches per mount | P4-003 |
| **P4-013** | Add `React.memo` to inner panels of `SessionInspector` (6101 lines) and `ProjectBoard` (3895 lines) | performance | M | P1 | ledger 86,87; gaps `frontend-core`:30 | inner panels memoized; full re-render on unrelated state change eliminated; ProjectBoard feature modal no longer re-renders entire tree on poll | P4-006 |
| **P4-014** | Add UI pagination to V1 command center (`pageSize=50` hardcoded; features >50 silently missing) | ux | M | P1 | ledger 92; gaps `planning-frontend`:74 | command-center list paginates beyond page 1; features beyond 50 are reachable; no silent truncation | P4-002 |
| **P4-015** | TanStack Query cache invalidation on project switch (`invalidateQueries()` after `setApiProjectScope()`) | frontend | S | P1 | ledger 134; gaps `multi-project`:241 | `queryClient.invalidateQueries()` fires on project switch; no stale cross-project UI window | P4-003 |
| **P4-016** | Fix `usePlanningSummaryQuery` `staleTime:0` refetch on every Planning mount | performance | S | P2 | ledger 128 | planning summary has a non-zero `staleTime`; no refetch on every Planning page mount | — |
| **P4-017** | Gate multi-project queries on `useProjectListReady` (hardcoded `projectListReady:true` today) | multi-project | S | P1 | ledger 33; gaps `planning-frontend`:67 | multi-project queries wait for the project list to resolve; no firing with `projectListReady:true` before list is ready | P5-001 |
| **P4-018** | Avoid O(N) Set re-construction on session-board hover (re-evaluates all `SessionCard` memos) | performance | M | P2 | ledger 91 | hover does not rebuild an O(N) Set; `SessionCard` memos no longer all re-evaluate on hover | P4-004 |
| **P4-019** | `StaleIndicator` should not start `setInterval` from mount regardless of staleness | performance | S | P2 | ledger 95 | timer starts only when an item can become stale; no always-on interval from mount | P4-006 |
| **P4-020** | Reduce document page size / memory cap (`pageSize=500`, max 2000) for enterprise; lazy PlanCatalog load | performance | S | P2 | ledger 88; gaps `frontend-core`:32 | enterprise-appropriate document page size + on-demand PlanCatalog loading; memory cap tuned for constrained containers | — |
| **P4-021** | `OpsPanel` should read sessions/documents reactively (stale `useData()` snapshots today) | frontend | S | P2 | ledger 90; gaps `frontend-core` | `OpsPanel` subscribes reactively (depends on P4-003); no stale snapshot reads | P4-003 |
| **P4-022** | Document/enable SSE for features/tests/ops in `.env.example` + deploy guides (defaulted off) | containerization | S | P1 | gaps `frontend-core`:36 | enterprise deploy docs explain enabling SSE; defaults/guidance documented so operators don't silently run 5s polling | P4-005 |

---

## Phase 5 — Command Center as Multi-Project Control Plane

**Goal:** deliver the command-center vision: a multi-project control plane by default behind a **runtime**
capability flag, with cross-project rollups, a ranked next-work queue, modal + deep-link detail, SkillMeat
artifact integration, and capability-gated ARC/MeatyWiki scaffolds. Depends on Phase 2-3 data contracts.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P5-001** | Runtime capability flag for multi-project command center (Vite **build-time** constant today) | container/frontend | M | P0 | ledger 93,119; gaps `planning-frontend`:66, `completed-work`:299; brief §5/§6.7 | `MULTI_PROJECT_COMMAND_CENTER_ENABLED` becomes a runtime capability served by an endpoint (no rebuild to enable in container); multi-project view is the default control plane when capability is present | P3-001 |
| **P5-002** | Add `tokenUsageByModel` to `Feature` model → fix `PlanningTokenTelemetry.source` always `unavailable` | backend | M | P0 | ledger 25; gaps `data-contracts`:360; brief §4 | `tokenUsageByModel` populated on `Feature`; `PlanningTokenTelemetry.source` resolves to real data; planning token KPI no longer broken | P1-010 |
| **P5-003** | Cross-project token/cost aggregate endpoint (`ProjectWorkItemCounts` incomplete) | backend | M | P0 | ledger 125; gaps `data-contracts`:365; brief §4 | a cross-project token/cost rollup endpoint exists; control-plane KPIs show aggregate cost across registered projects | P3-007,P5-002 |
| **P5-004** | Ranked "available next work" backlog endpoint (no priority-ordered execution queue today) | backend | M | P0 | ledger 127; gaps `data-contracts`:366; brief §4/§5 | an endpoint returns shaping/planned items ranked into a priority-ordered next-work queue; surfaced in the command center | P3-001 |
| **P5-005** | Column-index `Feature.data_json` BLOB fields (tags/owners/phases/linkedDocs) for SQL filtering | database | L | P1 | ledger 79; gaps `data-contracts`:367; brief §4 | tags/owners/phases/linkedDocs are queryable via SQL (columns or generated indexes) instead of opaque BLOB; filtering performant at skillmeat scale | P2-008 |
| **P5-006** | Deep-linkable feature detail route (`/planning/feature/:id`) alongside modal-first nav | ux | M | P1 | brief §5 UX decision; `planningRouteFeatureModalHref` (`services/planningRoutes.ts:41`) | a shareable/focusable `/planning/feature/:id` route exists; both modal and deep-link are backed by lazy, tab-scoped, endpoint-level loading (summary on open, detail per tab) | P4-002 |
| **P5-007** | Surface SkillMeat artifacts in feature detail (data already exists; not surfaced) | integration | M | P1 | `data-contracts` COMPLETED (artifact snapshot/ranking/recommendation wired); brief §5/§7 | feature detail renders SkillMeat artifact snapshot/ranking/recommendations from existing tables; no new ingestion needed | P5-006 |
| **P5-008** | Live PR status (stored ref strings only today; no GitHub API live query) | integration | M | P1 | ledger 126; gaps `data-contracts`:369 | PR status queried live (GitHub API) and surfaced in command center; stale ref strings replaced with live state | — |
| **P5-009** | Implement Cmd-K cross-feature/cross-project command palette (stub/toast today) | ux | XL | P2 | ledger 129; gaps `planning-frontend`:69, COMPLETED:58 (stub) | Cmd-K performs real cross-feature/cross-project navigation/search; no longer toast-only | P5-001 |
| **P5-010** | Implement "New Spec" / artifact creation workflow (stub today) | ux | L | P2 | ledger 129; gaps `planning-frontend`:70 | New-Spec creates a real spec/artifact via backend; no longer a stub toast | — |
| **P5-011** | Replace synthesized sparklines + "tokens saved %" with real per-day aggregate data | ux | M | P1 | ledger 130; gaps `planning-frontend`:71-72; brief §5 (synthesized fictions) | sparklines/`tokensSavedPct`/`ctxPerPhase` sourced from real historical aggregates (T2-001 backend); no heuristic fictions shown to enterprise users | P3-007 |
| **P5-012** | ARC / agentic-research-council integration scaffold (zero implementation today) | integration | XL | P2 | ledger 80; gaps `data-contracts`:363; brief §4/§7 (capability-gated, later phase) | ARC scaffolded behind a capability flag: model + client + DB table + endpoint stubs; surfaced only when capability present; full depth deferred per brief §8 | P5-001 |
| **P5-013** | MeatyWiki research integration scaffold (registered as project only, no API) | integration | XL | P2 | ledger 81; gaps `data-contracts`:364; brief §4/§7 | MeatyWiki scaffolded behind a capability flag: API surface + DB table + endpoint stubs; full depth deferred per brief §8 | P5-001 |
| **P5-014** | `PlanningSummaryPanel` attention column click-through beyond `ROW_LIMIT=8` | ux | S | P2 | gaps `planning-frontend`:73 | stale/blocked/mismatched attention columns are fully navigable beyond the 8-row cap | P4-002 |
| **P5-015** | Emit `ArtifactVersionOutcomePayload` (SAM version-level telemetry incomplete) | integration | S | P2 | ledger 137; gaps `data-contracts`:370 | `ArtifactVersionOutcomePayload` emitted by the exporter; SAM version-level telemetry path complete | P3-009 |
| **P5-016** | Live invalidation (SSE) wired to session board + command center (only planning summary today) | frontend | S | P1 | gaps `planning-frontend`:75 | SSE invalidation drives session board and command center (parity with planning summary at `PlanningHomePage.tsx:969-978`) | P4-002,P4-006 |

---

## Phase 6 — Observability, Retention Ops & Validation

**Goal:** harden and validate. OTEL coverage gaps, scheduled retention/VACUUM ops, a skillmeat-scale load
test, and a container e2e CI gate. Closes out the residual completed-work follow-ups.

| ID | Title | Area | Cplx | Pri | Evidence | Acceptance criteria | Depends on |
|----|-------|------|------|-----|----------|---------------------|-----------|
| **P6-001** | Add OTEL instrumentation for analytics snapshot, session-list badge derivation, sync INSERT batch sizes | performance | M | P1 | ledger 123; gaps `perf-evidence`:331, `completed-work`:297; brief §2b | OTEL histograms exist for `_capture_analytics` duration, badge-derivation latency, and INSERT batch sizes; live-fanout instruments (FU-5) confirmed present | P1-007,P1-010 |
| **P6-002** | Scheduled DB retention + VACUUM/ANALYZE job (no scheduled stats refresh; retention policy absent at scale) | database | M | P0 | ledger 124,334; gaps `perf-evidence`:333-334; brief §6 | a scheduled worker job runs retention (analytics/telemetry) + VACUUM/ANALYZE; statistics refreshed; ties P1-001/P1-003 retention into a recurring op | P1-001,P1-003 |
| **P6-003** | Postgres time-series partitioning for `analytics_entries` / `telemetry_events` at enterprise scale | database | L | P1 | ledger 124,333; gaps `perf-evidence`:333 | Postgres `analytics_entries`/`telemetry_events` partitioned by time; enterprise-scale retention drops partitions instead of row-deletes | P1-001,P1-003 |
| **P6-004** | Skillmeat-scale load test (large-project ingest + planning bundle + multi-project fan-out) | testing | L | P0 | brief §7 Phase 6; perf-evidence measured 10 GB DB / 367 features | a reproducible load test exercises skillmeat-scale data; asserts bounded latency on planning bundle, session list, and multi-project fan-out; results recorded | P1-007,P2-007,P3-007 |
| **P6-005** | Container e2e CI gate (promote P0-013 smoke into a required pipeline gate) | testing | M | P0 | brief §6.2/§7 Phase 6; gaps `ingestion-fs`:185 | the `docker compose up` e2e smoke (P0-013) is a required CI gate blocking merge on regression of live-data flow | P0-013 |
| **P6-006** | Resolve `CORS` always-allow `localhost:3000` regardless of production config | containerization | S | P1 | ledger 116; gaps `container-deploy`:267 | CORS honors `CCDASH_FRONTEND_ORIGIN`; production does not unconditionally allow `localhost:3000/127.0.0.1:3000` | — |
| **P6-007** | Re-evaluate / un-skip bootstrap test `FU-004` skip decorators (5 classes/methods) | testing | M | P2 | ledger 72; gaps `completed-work`:295 (`test_runtime_bootstrap.py:616,680,716,1057,1333`) | skips re-evaluated against current `bootstrap.py:176,224` (authGuardrail/probeDetailWarningCodes present); coverage restored or skips justified in code | — |
| **P6-008** | Wire-boundary SSE smoke test (Postgres NOTIFY→SSE path to SessionInspector) — FU-4 | testing | M | P1 | gaps `completed-work`:294 | an integration/real-browser test verifies SessionInspector receives live events end-to-end through NOTIFY→SSE | P3-014 |
| **P6-009** | Publish-exception isolation around `LiveEventBus.publish()` call sites — FU-3 | backend | S | P1 | gaps `completed-work`:296 (`backend/db/sync_engine.py`) | `LiveEventBus.publish()` wrapped in try/except at call sites; a publish failure cannot abort a sync write | — |
| **P6-010** | Confirm/add live-fanout OTEL instruments — FU-5 | performance | S | P2 | gaps `completed-work`:297 | `ccdash_live_fanout_publish_latency_ms`, `ccdash_live_fanout_delivered_total`, `ccdash_live_watcher_sync_latency_ms` present and emitting | P6-001 |
| **P6-011** | Document `_COMPACT_PAYLOAD_KEYS` extension contract — FU-7 | testing | S | P2 | gaps `completed-work`:298 | the cross-process compact-payload key contract is documented so downstream consumers add fields safely | — |
| **P6-012** | Fix PRD status metadata drift (planning-command-center-v1, enterprise-live-session-ingest-v1 stuck `draft`) | testing | S | P2 | ledger 135; gaps `completed-work`:302, `multi-project`:135 | both PRDs reflect `completed` status; effort-triage confusion resolved (CLI `manage-plan-status.py`) | — |
| **P6-013** | Document `container_project_onboarding.py` as a required pre-deploy step | containerization | S | P1 | gaps `container-deploy`:268 | enterprise deploy docs include running `container_project_onboarding.py` before first startup; no undocumented manual step | P0-002 |

---

## Summary Rollup — Phase × Area Task Counts

| Phase | frontend | backend | database | workers | container | ux | perf | integration | testing | caching | ingestion | multi-proj | **Total** |
|-------|---------:|--------:|---------:|--------:|----------:|---:|-----:|------------:|--------:|--------:|----------:|-----------:|----------:|
| **P0** | — | — | — | — | 10 | — | — | — | 1 | — | 3 | — | **15** ¹ |
| **P1** | — | 2 | 11 | — | — | — | 2 | — | — | — | 3 | — | **18** |
| **P2** | — | 4 | 4 | — | — | — | 2 | — | — | 8 | — | — | **18** |
| **P3** | — | 1 | 4 | 8 | — | — | — | 1 | — | — | — | 2 | **16** |
| **P4** | 5 | — | — | — | 2 | 1 | 11 | 1 | — | 2 | — | 1 | **22** ² |
| **P5** | 2 | 4 | 1 | — | — | 5 | — | 5 | — | — | — | — | **16** ² |
| **P6** | — | 1 | 2 | — | 2 | — | 2 | — | 6 | — | — | — | **13** |
| **Total** | **7** | **12** | **22** | **16** | **16** | **6** | **17** | **8** | **7** | **10** | **6** | **5** | **118** |

¹ P0-001/P0-002/P0-013 each merge multiple ledger issues (see Phase 0 merge notes), so 15 tasks subsume ~22 ledger rows.
² A few tasks carry a hybrid area (e.g. P5-001 container/frontend) and are counted under their primary area.

## Priority Totals

| Priority | Count | Notes |
|----------|------:|-------|
| **P0** | 49 | Blocking enterprise usability/correctness/scale; includes all critical ledger issues + the highest-leverage highs. |
| **P1** | 49 | Required for production hardening; the bulk of high-severity issues. |
| **P2** | 20 | Polish, deferrable integrations (ARC/MeatyWiki), and residual follow-ups. |
| **Total** | **118** | 130 ledger issues deduped/merged into 118 executable tasks. |

## Critical-Issue Coverage Check

All 20 **critical** ledger issues map to a task (merged where duplicated):

| Critical ledger issue (line) | Task |
|------------------------------|------|
| Session board no server pagination (7) | P4-001 |
| V1 command center bypasses TQ (8) | P4-002 |
| N+1 session-list log-fetch (9, 74) | P1-010 |
| Planning bundle 6× list_all (4) | P2-007 |
| analytics_entries unbounded (11, 23) | P1-001 |
| _capture_analytics N+1 12-15K (12, 77) | P1-007 |
| In-process cache not shared (13) | P2-001 |
| entity_links fingerprint full scan (14, 36) | P2-003 |
| FILESYSTEM_INGESTION_ENABLED false (15, 21) | P0-001 |
| Worker startup sync disabled (16, 24) | P0-001 |
| projects.json not DB-backed (17, 26) | P3-001 |
| Enterprise profile silently disables ingestion (18) | P0-001 |
| Single worker per project (19) | P3-005 |
| Host-path projects.json no resolve (20) | P0-002 |
| live-watch not default (22) | P0-001 |
| tokenUsageByModel missing (25) | P5-002 |

(Each critical from lines 7-26 is covered; the four ingestion-disabled criticals collapse into P0-001 as designed.)

## Open Decisions Carried Into Execution (from synthesis brief §8)

These gate specific tasks and need human input before/at execution:

| Decision | Gates | Recommendation (brief §8) |
|----------|-------|---------------------------|
| Shared cache tech: Valkey/Redis vs Postgres-backed | P2-001 | Valkey for enterprise; Postgres-cache fallback for single-node |
| Worker topology default: watch-all vs one-per-project | P3-005, P3-006 | watch-all default + per-project opt-in isolation |
| Transcript storage: canonical-only vs offload raw JSONL | P1-002, P1-016 | canonical `session_messages` + filesystem source-of-truth |
| ARC & MeatyWiki depth/timing | P5-012, P5-013 | scaffold-now behind capability flags; full depth deferred |
| SQLite future in enterprise | P1-006, P6-003 | SQLite stays dev-only; Postgres mandatory for enterprise |
