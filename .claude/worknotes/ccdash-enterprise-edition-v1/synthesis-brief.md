# CCDash Enterprise Edition — Orchestrator Synthesis Brief

> Authored by the lead planning/architecture agent (Opus) from the 12-domain forensic investigation
> (2026-05-30). This is the **steering document** for all deliverable authoring. Every authoring agent
> MUST stay consistent with the decisions, priorities, and phasing here. Evidence lives in
> `investigation/*.md`, `issue-ledger.md` (130 issues), and `completed-and-gaps.md`.

## 0. One-paragraph thesis

CCDash already contains **most of the enterprise scaffolding it needs** — 19+ completed efforts including
containerization, explicit runtime profiles (local/api/worker/worker-watch/test), data-platform
modularization, an SSE live-update platform, Postgres NOTIFY live ingest, a query-cache layer, a completed
TanStack Query migration, a planning control plane, a planning command center (V1), and a multi-project
command center (flagged off). The enterprise edition is not failing because the architecture is wrong; it
is failing because **the last mile is mis-wired and disabled-by-default**, and because a cluster of
**data-volume, N+1, and cache-correctness defects** make it slow at `skillmeat` scale. The work ahead is
mostly **finishing, wiring, and hardening** — not rewriting. Treat container+Postgres as the primary target.

## 1. Root cause #1 — Why the containerized enterprise build pulls no live data (HIGH confidence, 4 agents corroborate)

Three independent, compounding defects — each alone is sufficient to leave the container DB empty:

1. **Ingestion is disabled by default.** `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults **false**
   in the compose anchor → `SyncEngine` is never instantiated (`container.py:237-242`).
   `CCDASH_WORKER_STARTUP_SYNC_ENABLED` defaults **false** for the worker (`compose.yaml:133`) → no initial
   scan. The `live-watch` profile that flips these on is **not** part of the default enterprise startup
   command (requires `--profile live-watch`). Net: a standard `docker compose up` enterprise deploy ingests nothing.
2. **Host paths don't resolve inside the container.** `projects.json` stores host-absolute `~/...` paths;
   `FilesystemProjectPathProvider.resolve()` opens them verbatim in-container. Source-identity aliasing
   exists (`source_identity.py`) but is **not auto-populated from `ResolvedProjectPaths`** — it depends on
   the operator setting ~6 env vars correctly. When paths don't resolve, the watcher watches **zero paths**
   and still **passes `readyz`** (silent failure).
3. **The watcher can't observe changes even when paths resolve.** `watchfiles` inotify does not fire on
   Docker Desktop bind mounts and `WATCHFILES_FORCE_POLLING` defaults **false**. Compounding: `projects.json`
   is mounted `read_only:true` but `ProjectManager._save()` writes on startup migration → `PermissionError`.

**Design implication:** the fix is primarily **defaults + wiring + a fail-loud readiness contract + an e2e
smoke test**, not new subsystems. This is the highest-ROI, lowest-risk first phase.

## 2. Root cause #2 — Why it is slow (local + large projects) (HIGH confidence)

### 2a. Data volume — the 10GB SQLite DB decomposed
- `analytics_entries`: **1.8M rows / 466MB**, +3,313 rows/sync, **zero retention** — unbounded growth.
- `telemetry_events.payload_json`: **1.6GB** unbounded JSON blobs, no TTL.
- `session_logs` + `session_messages`: **3.3GB dual/duplicate transcript storage**; ~**1.75GB** of
  `session_logs` never purged after canonical `session_messages` are written.
- SQLite page cache is **8MB for a 9.5GB DB**; `PRAGMA synchronous/mmap_size/cache_size` untuned.

### 2b. N+1 / query patterns
- `_capture_analytics`: **~11,744–15K DB queries per sync snapshot** (feature-level N+1, 367 features).
- Session list view: N+1 full log-fetch per row — badge metadata (models/agents/skills) not materialized.
- Planning view bundle: **6× `list_all` full scans** with no data sharing; sub-services run **sequentially**.
- `entity_graph.upsert()`: **commit per link → 25K individual commits** during link rebuild.
- Row-by-row INSERTs (no `executemany`) across telemetry/attribution/logs.
- All planning services use `SELECT *` `list_all` (no column projection).

### 2c. Cache correctness & cost
- The cache **fingerprint** = a **full global `entity_links` GROUP_CONCAT scan on every cached request**,
  unscoped across all projects (`entity_links` has no `project_id`). The fingerprint itself is **not cached**
  → ~6 DB queries before every cache lookup. `feature_phases` fingerprint is O(N) GROUP_CONCAT.
- In-process `TTLCache(maxsize=512)` is **not shared across api+worker containers** → in enterprise the cache
  is per-replica, perpetually cold, and inconsistent; **no invalidation after sync**; documented per-metric
  TTLs (`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`, `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`) are never enforced;
  warming covers only 2 of 14 endpoints and only the active project.

### 2d. Frontend
- V1 `PlanningCommandCenter` **bypasses TanStack Query** (raw `useEffect`, no cache/dedup).
- Session board: **no server-side pagination** → full project payload every load; **no virtualization** on V1 board.
- Planning home **always-mounts** session board + command center → **5 concurrent cold-load requests** on entry.
- `useData()` shim is **non-reactive** (`getQueryData` snapshot, not `useQuery`) → 13+ components see stale data.
- `useFeaturesQuery` polls **5s** when SSE off (the enterprise default); `useFeatureSurface` list `staleTime:0`
  refetches every mount; `setInterval` sprawl across 8+ components bypasses TQ dedup/visibility.

## 3. Root cause #3 — Multi-project & worker model is single-project at the core (HIGH confidence)

Already present: `project_id` columns on most top-level tables, request-scoped `resolve_project()` with
`X-CCDash-Project-Id`, `POST /api/projects/active/{id}` with watcher rebind, CLI `project` group, MPCC fan-out
with bounded concurrency. **But:**
- `projects.json` is a **local file, not DB-backed** → breaks multi-replica containers.
- `FileWatcher` is a **process-level singleton — one project watched at a time**. Multi-project today = **N
  worker containers, one per project, with no orchestration / shared scheduler / cross-project analytics**.
- `InProcessJobScheduler` = bare `asyncio.create_task()` — **no queue, retry, priority, backpressure, or
  supervision**; **no durable task queue** → full re-sync on every restart; a dead job reports `idle`.
- Session PK is **globally unique** (cross-project collision risk); `session_logs/tool_usage/file_updates`
  lack `project_id`. Cache warming + analytics only cover the bound project.

## 4. Root cause #4 — Command-center data contract gaps (MEDIUM-HIGH confidence)

Strong existing surface: SkillMeat artifact intelligence is **fully wired** (snapshot/ranking/recommendation/
rollups), planning DTOs are rich (command-center item, session board, feature context, phase ops), plus
execution runs + approval pipeline, test-run integration, worktree contexts. **Gaps:**
- `tokenUsageByModel` missing from `Feature` → `PlanningTokenTelemetry.source` is always `unavailable` (KPI broken).
- `Feature.data_json` BLOB → no SQL filtering on tags/owners/phases/linkedDocs (bottleneck at scale).
- Open-question resolutions live in process memory (`_OQ_OVERLAY`) → lost on restart, multi-instance-incompatible.
- **ARC council + MeatyWiki research integrations: zero implementation** (registered as projects only).
- No cross-project token/cost aggregate; no ranked "available next work" backlog endpoint; PR status not live.

## 5. Command center: vision vs reality

Built today: modal-first nav (`planningRouteFeatureModalHref`), 7-tab feature detail shell, command-center
list/card/board views, phase-plan table, agent session board + forensics detail panel, multi-project command
center (flagged **off**), attention columns (stale/blocked/mismatched). Gaps: V1 not on TQ; no server
pagination/virtualization on V1 board; multi-project gated by a **build-time** flag; Cmd-K + New-Spec are
stubs; sparklines and "tokens saved %" are **synthesized fictions**; ARC/MeatyWiki surfaces absent.

**UX decision:** keep **modal-first drill-down for in-context** feature inspection (already the pattern) AND
add a **deep-linkable detail route** (`/planning/feature/:id`) for focus/share — both backed by lazy,
tab-scoped, endpoint-level data loading (summary on open, detail per tab). Default command-center view =
**multi-project, high-signal, progressive disclosure** (active-now / changed-recently / needs-attention /
next-work), gated by a **runtime capability flag**, not a build-time constant.

## 6. Target architecture decisions (orchestrator judgment — authoring agents adopt these)

1. **Enterprise data plane = Postgres authoritative + shared cache (Redis/Valkey) + durable job queue.**
   Replace `projects.json` with a `projects` table; move `_OQ_OVERLAY` and open-question resolutions to DB.
   Shared cache is the single most important enterprise correctness fix (kills per-replica cold/inconsistent cache).
2. **Container last-mile = defaults + auto-derived path aliases + fail-loud readiness + e2e smoke.** Flip
   worker ingestion/startup-sync defaults on; fold `live-watch` into the default enterprise topology; auto-derive
   container path aliases from `ResolvedProjectPaths`; force polling on bind mounts; make project registry
   writable/DB-backed; `readyz` FAILS when watch-paths == 0; CI `docker compose up` smoke asserts sessions appear.
3. **Storage hygiene = retention + dedupe + pragmas + indexes + batching.** TTL/retention jobs for
   `analytics_entries` & `telemetry_events`; drop duplicate `session_logs` after canonical messages; tune SQLite
   pragmas; add `idx_sessions_project_status_updated` (backfill) + `sessions.source_file` index + analytics
   partial indexes; `executemany` + single-transaction upserts; materialize session badge metadata; FTS5 for
   message search.
4. **Worker model = multi-project worker with a per-project FileWatcher registry + durable queue + supervision.**
   Support "watch all registered projects" in one worker (small fleets) AND keep one-container-per-project as a
   valid isolation deployment (blast-radius). Project-scoped scheduling; multi-project warming/analytics loop.
5. **Query/payload split = summary (cached, column-projected, denormalized) vs detail (lazy).** Project-scope the
   cache fingerprint (add `project_id` to `entity_links`) and cache the fingerprint; parallelize bundle sub-calls
   (`asyncio.gather`); precompute the planning graph in DB via the worker.
6. **Frontend finish = complete TQ + pagination/virtualization + kill polling + defer mounting.** Migrate V1
   command center, `AnalyticsDashboard`, Dashboard charts; make `useData` reactive; server pagination +
   virtualization on the session board; replace `setInterval` with TQ `refetchInterval`/SSE invalidation; raise
   `staleTime`s; viewport-deferred mounting; self-host fonts; move the Gemini key server-side.
7. **Command center = multi-project control plane by default.** Runtime capability flag; cross-project rollups;
   ranked next-work queue; modal + deep-link detail; SkillMeat artifacts surfaced in feature detail (data already
   exists); ARC/MeatyWiki integrations scaffolded behind capability flags for a later phase.

## 7. Roadmap shape (authoring agents must use these phase boundaries)

- **Phase 0 — Enterprise Liveness Hotfix** (quick wins, days): container wiring so live data flows; fail-loud
  readyz; e2e `docker compose up` smoke. Unblocks all enterprise use. Mostly default flips + path-alias derivation.
- **Phase 1 — Storage Hygiene & DB Performance**: retention/TTL, transcript dedupe, pragmas, missing indexes,
  batch upserts, materialize badges. Shrinks the 10GB DB and removes the worst N+1s. Highly measurable.
- **Phase 2 — Cache & Query Correctness**: shared cache (Redis/Valkey) or Postgres-backed; project-scope +
  cache the fingerprint; sync-triggered invalidation; summary/detail endpoint split + column projection;
  parallelize bundle sub-calls.
- **Phase 3 — DB-backed Project Registry & Multi-Project Worker**: `projects` table; OQ overlay → DB; per-project
  watcher registry; durable queue; supervision; multi-project warming/analytics.
- **Phase 4 — Frontend Performance Finish**: TQ completion, pagination/virtualization, polling cleanup, deferred
  mounting, font self-host, Gemini key relocation.
- **Phase 5 — Command Center as Multi-Project Control Plane**: runtime flag, cross-project rollups, ranked
  next-work, drill-down detail, SkillMeat artifact integration; ARC/MeatyWiki integration scaffolds (capability-gated).
- **Phase 6 — Observability, Retention Ops & Validation**: OTEL gaps, scheduled retention/VACUUM, skillmeat-scale
  load test, container e2e CI gate.

**Sequencing rationale:** Phase 0 makes enterprise usable at all; Phase 1 makes it fast and stops the DB
bleeding; Phase 2 makes it correct/fast across replicas; Phase 3 makes it genuinely multi-project; Phase 4
finishes UX performance; Phase 5 delivers the command-center vision; Phase 6 hardens and validates. Phases 1
and 4 can overlap (DB vs FE owners). Phase 2 depends on Phase 1's index/scoping work. Phase 5 depends on
Phases 2-3 data contracts.

## 8. Open decisions requiring human input (carry into deliverables)

- **Shared cache technology**: Redis/Valkey (operational dependency) vs Postgres-backed cache table
  (no new infra, lower throughput). Recommend Valkey for enterprise, Postgres-cache fallback for single-node.
- **Worker topology default**: one-worker-watch-all vs one-container-per-project. Recommend watch-all default
  with per-project opt-in isolation; confirm against deployment scale expectations.
- **Transcript storage**: keep canonical `session_messages` only and drop `session_logs`, or offload raw JSONL
  to object storage / keep on filesystem and store only derived rows. Recommend canonical-only + filesystem source-of-truth.
- **ARC & MeatyWiki integration depth/timing**: scaffold-now-vs-defer; these are net-new (Phase 5+).
- **SQLite future in enterprise**: SQLite stays dev-only; confirm Postgres is mandatory for all enterprise tiers.

## 9. Confidence & evidence

- Container live-data failure: **HIGH** (corroborated by ingestion-fs, multi-project, container-deploy, perf-evidence).
- 10GB DB / N+1 / unbounded analytics: **HIGH** (database + perf-evidence measured row counts & byte sizes).
- Cache non-shared / fingerprint scan: **HIGH** (caching + backend-api).
- Single-project worker/watcher: **HIGH** (workers-runtime + multi-project).
- Data-contract gaps (ARC/MeatyWiki/tokenUsageByModel): **HIGH** for absence; **MEDIUM** for exact target shape.
