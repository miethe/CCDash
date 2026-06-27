---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Enterprise Edition — Executive Summary & Findings"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Enterprise Edition — Executive Summary & Findings

> The entry-point document for the CCDash Enterprise Edition planning bundle. Read this first, then the
> [bundle index](README.md). Every claim here is anchored to `file:line` evidence carried up from the seven
> detail deliverables (01–07) and the orchestrator
> [synthesis brief](../../../../.claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md).
> This is a **planning/analysis** output — no application code was modified.

---

## 1. What was investigated

A **12-domain forensic sweep** (2026-05-30) of the CCDash codebase, run against a real, in-use **9.5 GB
SQLite cache** (`data/ccdash_cache.db`: 9,246 sessions, 367 features, ~533 sync cycles over ~103–151 days for
the `skillmeat` project). The sweep covered: container/deploy, ingestion-filesystem, database, caching,
backend-API, frontend-core, planning-frontend, workers-runtime, multi-project, perf-evidence, data-contracts,
and completed-work/gaps. It produced **130 catalogued issues** (`issue-ledger.md`), a **completed-vs-gaps
ledger** (`completed-and-gaps.md`), and per-domain findings with measured row counts and byte sizes.

The mission: make the **enterprise/containerized edition** production-usable, performant, and
multi-project-scalable. **Container + Postgres is the PRIMARY target; local mode is a dev mode.**

**One-paragraph thesis.** CCDash already contains most of the enterprise scaffolding it needs — **19+ completed
efforts** including containerization, explicit runtime profiles (`local`/`api`/`worker`/`worker-watch`/`test`),
data-platform modularization, an SSE live-update platform, Postgres `NOTIFY` live ingest, a query-cache layer, a
completed TanStack Query migration, a planning control plane, and a (flagged-off) multi-project command center.
The enterprise edition is **not failing because the architecture is wrong** — it is failing because the **last
mile is mis-wired and disabled-by-default**, and because a cluster of **data-volume, N+1, and cache-correctness
defects** make it slow at `skillmeat` scale. The work ahead is **finishing, wiring, and hardening — not
rewriting**.

---

## 2. Top 5 findings

### Finding 1 (THE headline) — A default container deploy ingests ZERO live data, and fails silently

`docker compose --profile enterprise --profile postgres up` reaches a **healthy API with an empty database**.
This is the definitive answer to "why does the containerized build pull no live data": **three independent,
compounding defects, each alone sufficient** to leave the DB empty (synthesis §1; doc 03 §2; doc 01 §9.4):

| # | Defect | Evidence | Effect |
|---|--------|----------|--------|
| 1 | Ingestion disabled by default | `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: false` (`compose.yaml:27`) → `_sync_engine_enabled()` returns `False` (`container.py:237–242`); `CCDASH_WORKER_STARTUP_SYNC_ENABLED: false` (`compose.yaml:133`); `live-watch` profile (the only one flipping both on) **not** in the default startup command | No `SyncEngine`, no initial scan, no watcher |
| 2 | Host paths don't resolve in-container | `projects.json` stores host-absolute `~/...` paths; `FilesystemProjectPathProvider.resolve()` opens them verbatim (`project_paths/providers/filesystem.py:25–28`); source-identity aliasing (`source_identity.py:271–308`) is **not** auto-derived from `ResolvedProjectPaths` — it needs ~6 hand-set env vars | Watcher resolves **zero paths** but still **passes `readyz`** (silent) |
| 3 | Watcher can't observe changes | `watchfiles` inotify does not fire on Docker Desktop bind mounts; `WATCHFILES_FORCE_POLLING` defaults `false`; `projects.json` is mounted `read_only:true` yet `ProjectManager._save()` writes on startup migration → `PermissionError` (`compose.yaml:48`; `project_manager.py:100`) | No live events even when paths resolve; crash-on-migration |

**Root-cause class:** defaults + wiring + a missing fail-loud readiness contract — **not** a missing subsystem.
This is the highest-ROI, lowest-risk fix (Phase 0).

### Finding 2 — The 10 GB DB slowness anatomy: unbounded growth + dual-transcript duplication

The production SQLite DB is **9.86 GB raw** with **157 free pages** (effectively zero slack) and **no retention
policy on any table** (doc 02 §2; doc 01 §4.4):

| Table | Rows | Storage | Why it bleeds |
|-------|-----:|--------:|---------------|
| `session_logs` | 546,043 | **2,084 MB** | verbatim `content`+`tool_args`+`tool_output` TEXT; **~1.75 GB is dead duplicate** of `session_messages` after re-ingest (`services/sessions.py:107–116`) |
| `telemetry_events` | 918,374 | **1,648 MB** | `payload_json` avg 1.6 KB / max 2.3 MB, **no TTL** (`sqlite_migrations.py:500–542`) |
| `session_messages` | 385,508 | **1,232 MB** | canonical transcript — second full copy of the same content |
| `analytics_entries` | 1,798,056 | **466 MB** | full snapshot appended every sync (~3,313 rows/sync, ~250 rows/min active), **zero pruning** (`sync_engine.py:5802`; no `DELETE` anywhere) |
| `sessions` | 9,246 | 199 MB | `session_forensics_json` avg 19 KB/row = 175 MB of recomputable aggregate stored in-row |
| `analytics_entity_links` | 3,580,439 | 166 MB | ~2 links per analytics entry, unpruned alongside parent |

Compounding it: **`PRAGMA cache_size=2000` = an 8 MB page cache for a 9.5 GB DB** (`connection.py:52–54`) — every
analytical query pages in from disk. A 90-day retention window + `ON CONFLICT` upsert cuts `analytics_entries`
~50× (1.8M → ~30–90K rows); dropping dead `session_logs` reclaims ~1.75 GB; `telemetry_events` TTL reclaims ~1.4 GB.

### Finding 3 — The cache is per-replica cold, inconsistent, and pays 6 DB queries on every request

The cache is a single in-process `cachetools.TTLCache(maxsize=512, ttl=600)` allocated at module import
(`cache.py:50`). In enterprise mode `api` and `worker` are **separate containers**, and each `api` replica holds
an **independent cache** — perpetually cold and inconsistent (doc 02 §4.4). Worse, the **`api` profile is
`jobs=False`** (`profiles.py:41–52`), so the container that serves traffic receives **zero background warming**
(`runtime.py:192`). And `get_data_version_fingerprint()` fires **6 sequential SQL queries on every cached
request — even on a hit** — including a full **global `entity_links` GROUP_CONCAT scan across all 26,681 rows of
all projects** (`cache.py:84–142, 258–289`), because `entity_links` has **no `project_id` column**
(`sqlite_migrations.py:37–56`). The fingerprint result is **not itself cached**.

### Finding 4 — Server N+1 storms: ~12–15K queries per sync; 50×5,000-row fetch per session-list page

- **`_capture_analytics`** runs a per-feature × per-session N+1 — **~11,744–15,000 DB queries per analytics
  snapshot** for 367 features (`sync_engine.py:5876–5972`), synchronously inside the sync loop.
- **`GET /api/sessions`** calls `list_session_logs` (internal limit 5,000 rows) for **every** session in a page of
  50 — **up to 250,000 log-row fetches per list page** — purely to derive badges and a summary that never change
  after a session ends (`api.py:628`; `services/sessions.py:92`).
- **`GET /api/agent/planning/view`** runs **6× `SELECT *` `list_all` full scans, sequentially** (no
  `asyncio.gather`) per cache miss (`planning.py:2158, 2199, 2220, 2242`).
- **`entity_graph.upsert()`** commits **per link → ~25,000 individual commits** during a link rebuild
  (`entity_graph.py:40`).

### Finding 5 — The multi-project / worker model is single-project at its core

`projects.json` is a **local file, not DB-backed** (breaks multi-replica containers); `FileWatcher` is a
**process-level singleton — one project watched at a time** (`file_watcher.py:307`); `InProcessJobScheduler` is a
bare `asyncio.create_task()` with **no queue, retry, priority, backpressure, or supervision** — a crashed job
reports `idle`, not `dead` (`adapters/jobs/local.py:8–10`; `runtime.py:385–420`); analytics + cache warming cover
**only the active/bound project** (`runtime.py:793–838`). Multi-project today = **N worker containers, one per
project, with no shared scheduler or cross-project analytics** (synthesis §3; doc 01 §8).

---

## 3. Highest-confidence root causes of slowness (HIGH confidence — measured, multi-domain)

1. **Data volume / unbounded growth (HIGH).** No retention anywhere; `analytics_entries` +3,313 rows/sync;
   `telemetry_events` 1.6 GB of untrimmed JSON; `session_logs`/`session_messages` 3.3 GB dual storage with ~1.75 GB
   dead. 8 MB page cache for a 9.5 GB DB. (doc 02 §2; database + perf-evidence measured.)
2. **N+1 query patterns (HIGH).** `_capture_analytics` ~12–15K queries/snapshot; session-list 50×5,000-row fetch;
   planning bundle 6× `list_all` sequential; `entity_graph` 25K commits; row-by-row INSERTs (no `executemany`);
   `SELECT *` across all planning services drags the `data_json` BLOB. (doc 02 §3.)
3. **Cache cost & correctness (HIGH).** Per-replica in-process cache; unwarmed `api`; unscoped + uncached
   fingerprint (6 queries/request); no post-sync invalidation (only call site is `planning.py:1567`); phantom
   per-metric TTLs. (doc 02 §4.)
4. **Frontend fetch storms (HIGH).** V1 `PlanningCommandCenter` bypasses TanStack Query (raw `useEffect`); session
   board has no server pagination (hard-coded `limit=500`) and no V1 virtualization; `/planning` always-mounts 5
   concurrent cold-load requests; `useData()` is a non-reactive `getQueryData` snapshot (13+ stale consumers);
   `useFeaturesQuery` polls 5 s when SSE is off (the enterprise default), `useFeatureSurface` list `staleTime:0`.
   (doc 02 §5.)
5. **Ingestion cost (HIGH).** No manifest-based skip for the JSONL session scan (full `rglob` + N DB lookups every
   startup); `sessions.source_file` has no index (full scan per watch event); blocking startup sync serializes on
   one SQLite connection. (doc 02 §6.)

---

## 4. Highest-priority enterprise gaps

From the 20 CRITICAL ledger issues, which decompose into the root causes above (doc 03 §6; doc 01 Appendix B):

| Gap | Phase | Why it blocks enterprise |
|-----|-------|--------------------------|
| Container ingests zero data by default; silent failure | **0** | Enterprise is unusable out of the box |
| Host paths in `projects.json` don't resolve in-container; alias not auto-derived | **0** | Even with ingestion on, the watcher finds nothing |
| `analytics_entries` unbounded; `session_logs`/`session_messages` dual storage; no pragmas | **1** | The 10 GB bleed; everything analytical is slow |
| `_capture_analytics` N+1; session-list N+1; planning bundle 6× scans | **1/2** | Every sync and every list/board view is slow |
| In-process cache not shared across `api`+`worker` replicas; unscoped+uncached fingerprint | **2** | The single most important enterprise correctness fix |
| `projects.json` not DB-backed; single-project watcher; no durable queue/supervision | **3** | Blocks true multi-replica multi-project at scale |
| V1 command center off TQ; session board no pagination/virtualization | **4** | UX cold-loads the 10 GB backend on every nav |
| `tokenUsageByModel` missing from `Feature` → `PlanningTokenTelemetry.source` always `unavailable` | **5** | A KPI is silently broken; ARC/MeatyWiki integrations are zero-implementation |

---

## 5. Recommended target architecture (one paragraph)

Make **Postgres the authoritative enterprise data plane**, replace the `projects.json` local file with a
DB-backed **`projects` table** and move in-memory open-question overlays (`_OQ_OVERLAY`) to DB; front it with a
**shared cache (Valkey/Redis in enterprise, a Postgres-backed cache table as the single-node fallback)** to kill
per-replica cold/inconsistent caches, and **project-scope + cache the fingerprint** (add `project_id` to
`entity_links`, parallelize bundle sub-calls with `asyncio.gather`, precompute the planning graph in DB);
restructure the worker as a **multi-project worker with a per-project `FileWatcher` registry plus a durable task
queue with retry/priority/backpressure/supervision** (keeping one-container-per-project as a valid isolation
deployment); enforce **storage hygiene** (retention/TTL on `analytics_entries`+`telemetry_events`, transcript
dedupe, SQLite pragmas, backfilled indexes, `executemany` batching, materialized session badges); finish the
**frontend** (complete TQ, server pagination + virtualization, kill polling, viewport-deferred mounting); and ship
the **command center as a multi-project control plane by default behind a runtime capability flag**. The
container last-mile becomes **defaults-on + auto-derived path aliases + a fail-loud `readyz` (FAILS when
watch-paths == 0) + a CI `docker compose up` e2e smoke test**. (doc 05; synthesis §6.)

---

## 6. Recommended FIRST implementation phase — Phase 0: Enterprise Liveness Hotfix

**Goal:** a standard `docker compose --profile enterprise --profile postgres up` ingests live session data with
**zero extra flags**, and any misconfiguration **fails loud** (fails `readyz`) instead of silently serving an
empty dashboard. **No new subsystems.** Effort rollup: **S:8 · M:4 · L:0 · XL:0** (phase complexity **M**) —
the highest-ROI, lowest-risk phase (doc 06 Phase 0; doc 07 Phase 0).

Exactly what it does:

| Change | Evidence | Ledger / Task |
|--------|----------|---------------|
| Flip enterprise filesystem-ingestion + worker startup-sync defaults **ON**; fold `live-watch` into the default enterprise topology | `config.py:244–246`; `compose.yaml:27,133`; `container.py:237–242` | P0-001 (merges 4 critical findings) |
| Auto-derive container path aliases from `ResolvedProjectPaths` (no 6 hand-set env vars); validate host paths resolve in-container | `providers/filesystem.py:25–28`; `source_identity.py:271–308` | P0-002 |
| `readyz` **FAILS** when worker-watch resolves zero watch-paths (`configured_no_paths`) | `file_watcher.py:108–112,252–266`; `runtime.py:422–463` | P0-003 |
| Default `WATCHFILES_FORCE_POLLING=true` for `worker-watch` on bind mounts | `compose.yaml:175`; `file_watcher.py:16,183` | P0-004 |
| Make `projects.json` writable (RW mount) + atomic `_save()` (temp-file + rename) | `compose.yaml:48`; `project_manager.py:140–146` | P0-005 |
| Add `worker-watch` dispatch to `entrypoint.sh`; add `frontend depends_on: api`; `pg_advisory_lock` around `run_migrations()` | `entrypoint.sh:10–24`; `compose.yaml:195–217`; `container.py:106–108` | P0-008, P0-007, P0-011 |
| Watcher-triggered delete uses the canonical source key, not a raw path string | `sync_engine.py:3944` vs `:4171` | P0-012 |
| **CI `docker compose up` e2e smoke gate** — drop a fixture `.jsonl`, assert `GET /api/sessions` returns ≥1 row and worker `readyz` is 200 **iff** watch-paths > 0 | synthesis §6.2 | P0-013 (exit gate) |

**Acceptance:** default enterprise compose ingests sessions with no extra flags; worker `readyz` is 200 iff
watch-paths > 0 with an actionable zero-path log; live updates fire on Docker Desktop bind mounts; the e2e smoke
test is green on every PR touching `deploy/runtime/**` or `backend/runtime/**`. **Risk to manage:** default-on
ingestion triggers the Phase 1 blocking startup sync — ship Phase 0 with `STARTUP_SYNC_LIGHT_MODE` defaulted true
in-container and reconcile the three-way default mismatch (`config.py:966` False / `runtime.py:731` getattr True /
`sync_engine.py:4261` getattr False) so heavy passes defer to the worker loop. **Rollback** = revert env-var
defaults + compose edits; no schema migration, no data change.

---

## 7. Open decisions requiring human input (synthesis §8)

These gate specific tasks and need a human call before/at execution (doc 07 "Open Decisions"):

| Decision | Gates | Recommendation |
|----------|-------|----------------|
| **Shared cache technology** — Valkey/Redis (new operational dependency) vs Postgres-backed cache table (no new infra, lower throughput) | P2-001 | **Valkey** for enterprise; Postgres-cache fallback for single-node |
| **Worker topology default** — one-worker-watch-all vs one-container-per-project | P3-005, P3-006 | **watch-all default** + per-project opt-in isolation (blast-radius) |
| **Transcript storage** — canonical `session_messages` only (drop `session_logs`) vs offload raw JSONL to object storage | P1-002, P1-016 | **canonical-only** + filesystem as source-of-truth |
| **ARC council + MeatyWiki integration depth/timing** — scaffold now vs defer (net-new, zero implementation today) | P5-012, P5-013 | **scaffold now** behind capability flags; full depth deferred |
| **SQLite future in enterprise** — confirm Postgres is mandatory for all enterprise tiers; SQLite stays dev-only | (cross-cutting) | SQLite **dev-only**; Postgres mandatory |

---

## 8. Bundle docs

Full manifest and reading order in the [bundle index](README.md). Detail deliverables:

| Doc | What it answers |
|-----|-----------------|
| [01 — Current-State Architecture](01-current-state-architecture.md) | What exists now (FE/BE/DB/workers/ingestion/cache/multi-project/container), file:line baseline |
| [02 — Performance Forensics](02-performance-forensics.md) | Why it is slow — the 10 GB anatomy, N+1 catalog, cache cost, quick wins vs deep refactors |
| [03 — Enterprise Edition Gap Analysis](03-enterprise-edition-gap-analysis.md) | What works, what is broken, what is missing; the compounding container-failure chain |
| [04 — Planning Command Center UX & Data Spec](04-planning-command-center-ux-data-spec.md) | Multi-project control-plane IA, drill-down model, new/changed endpoints, data availability matrix |
| [05 — Target Architecture Proposal](05-target-architecture-proposal.md) | Enterprise-primary topology, backend/DB/worker/cache/FE/container target design, tradeoffs |
| [06 — Implementation Roadmap](06-implementation-roadmap.md) | Phase 0–6 with goal/scope/changes/risks/validation/acceptance/rollback/effort per phase |
| [07 — Issue & Task Backlog](07-issue-task-backlog.md) | 130 issues → 118 executable tasks; Top 12 P0 quick-start; critical-coverage check |

**Evidence base (worknotes):**
`.claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md` (steering),
`issue-ledger.md` (130 issues), `completed-and-gaps.md` (shipped vs missing), and
`investigation/*.md` (12 per-domain findings with file:line anchors).
