---
schema_version: 2
doc_type: spike
title: "System-Wide Live Metrics — Live Agents Signal + Cross-Project Aggregation"
status: draft
created: 2026-05-19
feature_slug: system-wide-live-metrics
research_questions:
  - "What is the cheapest, accurate way to determine 'currently running agents' for a project?"
  - "How should CCDash structure a system-wide (cross-project) metrics surface for the home dashboard and future desktop widgets?"
complexity: medium
estimated_research_time: "0.5d"
prd_ref: null
plan_ref: null
related_documents:
  - backend/parsers/platforms/claude_code/parser.py
  - backend/parsers/platforms/codex/parser.py
  - backend/db/repositories/sessions.py
  - backend/application/services/agent_queries/planning_sessions.py
  - backend/application/services/agent_queries/project_status.py
  - backend/adapters/jobs/runtime.py
  - backend/project_manager.py
---

# Spike: System-Wide Live Metrics

## 1. Summary & Recommendation

**Q1 — Cheap "currently running agents" count.** CCDash already derives a per-session `status` of `"active"` vs `"completed"` inside both parsers (Claude Code and Codex) using a JSONL `mtime`-within-10-minutes heuristic plus terminal-event detection, and persists the result on `sessions.status` (cached SQLite/Postgres). The frontend duplicates this in TypeScript (`isSessionLiveInFlight`). The cheapest accurate signal for a project's running-agent count is therefore **a single indexed `COUNT(*)` against the cached `sessions` table**, filtered by `project_id`, `status = 'active'`, and a freshness clamp `updated_at >= now() - 10 min` to eliminate stale "active" rows from sessions that ended without writing a terminal event and have not yet been re-scanned by the file watcher. This is O(1) repo work, reuses existing rows and the `idx_sessions_project` index, and inherits the watcher's write-through freshness for the active project. **Recommended: extend `SessionsRepository.count` with the freshness filter and expose a tiny `GET /api/agent/project/{id}/live-counts` endpoint.**

**Q2 — System-wide metrics.** Today the entire `agent_queries/` surface is single-project: every service starts with `resolve_project_scope(...)` (`_filters.py:35`) and the runtime only starts startup-sync + `file_watcher` for the **active** project (`adapters/jobs/runtime.py:135–171`). The cached `sessions` table, however, is already partitioned by `project_id` for every known project that has *ever* been the active one, so the cheapest first step is **in-process fan-out across the `WorkspaceRegistry` list with per-project `COUNT(*)` queries** behind a new `SystemMetricsQueryService`. This avoids new tables, new background jobs, and new schema, and gives the home dashboard a sub-100ms answer for ~36 projects (the count currently in `projects.json`). The known caveat — staleness for non-active projects — is acceptable for the home-dashboard use case and is mitigated by a planned follow-on (light-mode per-project rescan on home-dashboard load, plus optional opt-in multi-project watching). **Recommended: Tier 2 — a `SystemMetricsQueryService` with REST + CLI + MCP surfaces, layered on top of the Q1 live-count primitive.**

The two pieces ladder cleanly: Q1 is a Tier 1 Feature Contract producing the per-project primitive; Q2 is a Tier 2 PRD that composes that primitive across projects and adds rollup DTOs.

---

## 2. Current State Findings (with citations)

### 2.1 Session lifecycle is already computed at parse time

Two parsers, both same shape:

- **Claude Code** — `backend/parsers/platforms/claude_code/parser.py:1519–1543` (`_derive_session_status`) inspects the last entry; if it is a `system` event with `durationMs` or one of `_TERMINAL_SYSTEM_SUBTYPES = {"turn_duration", "compact_boundary", "microcompact_boundary", "informational"}` (`parser.py:101–106`) the session is `"completed"`. Otherwise it falls back to file `mtime`: if the JSONL was touched within `_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60` (`parser.py:100`) it returns `"active"`, else `"completed"`.
- **Codex** — `backend/parsers/platforms/codex/parser.py:418–429` (`_derive_status`) does the same: scan the last 20 entries for `payload.type in {"task_complete", "turn_aborted"}` → `"completed"`; otherwise `mtime` within `_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60` (`parser.py:22`) → `"active"`.

Both parsers feed `AgentSession.status` via `parse_session_file()` (`backend/parsers/sessions.py:11–13`, a thin shim to `parsers/platforms/registry.py`).

### 2.2 The status is persisted and indexed

- The `sessions` table stores `status TEXT DEFAULT 'completed'` (`backend/db/sqlite_migrations.py:92`) alongside `project_id` (line 90), `started_at`, `ended_at`, `updated_at` (lines 143–146), with index `idx_sessions_project ON sessions(project_id, started_at DESC)` (line 155). There is no dedicated `(project_id, status)` index today.
- `SessionsRepository.count(project_id, filters)` already supports `filters["status"]` and emits `WHERE status = ?` (`backend/db/repositories/sessions.py:300–302`). It also already accepts `updated_start`/`updated_end` (lines 365–370) — the freshness clamp is one parameter away.
- `SessionsRepository.upsert(...)` writes `session_data.get("status", "completed")` on every sync (`backend/db/repositories/sessions.py:89`), so DB rows track the latest parser verdict whenever the watcher re-syncs the file.

### 2.3 The file watcher already keeps the active project current

- `FileWatcher.start(..., sessions_dir, docs_dir, progress_dir, ...)` (`backend/db/file_watcher.py:72–135`) opens a `watchfiles.awatch` over the project's directories and calls `sync_engine.sync_changed_files(...)` on every `.jsonl`/`.md`/artifact change (`file_watcher.py:182–238`, `_classify_changes` at 268–303).
- The watcher is **per-active-project**: `adapters/jobs/runtime.py:162–172` shows `file_watcher.start(self.sync, active_project.id, sessions_dir, docs_dir, progress_dir, ...)` — there is exactly one watcher and it tracks only `active_project`. Switching projects (via `set_active_project`, `adapters/workspaces/local.py:27–28`) does not currently tear down and restart the watcher inside the same process; that's a known limitation worth noting.
- Practically: for the active project, `sessions.status` is refreshed within seconds of any JSONL append. For non-active projects, the row's `status` reflects the last time that project *was* active (or the last startup-sync — see 2.5).

### 2.4 The frontend already computes "live in-flight" the same way

`components/SessionInspector.tsx:46` defines `LIVE_IN_FLIGHT_WINDOW_MS = 10 * 60 * 1000` and `isSessionLiveInFlight` (lines 176–182) requires `session.status === 'active'` **and** last-activity epoch within 10 minutes. This is the exact mirror of the backend rule and confirms the chosen contract is already implicit in the product. `TranscriptView.tsx:157` duplicates the same helper. There is **no aggregate counter** in `Dashboard.tsx` or `OpsPanel.tsx` today — `Dashboard.tsx:226` shows a feature-status chip (`featureCounts.active`), not a session-level "running agents" count.

### 2.5 Planning session board already computes a running count — but for the active project only

`PlanningSessionQueryService.get_board(...)` (`backend/application/services/agent_queries/planning_sessions.py:298–442`) loads up to 500 sessions for the resolved project (line 338–345), maps each via `_map_session_state` (line 89) using `_STATUS_STATE_MAP` (lines 44–58) where `running|in_progress|active → "running"`, then computes `active_count = sum(1 for c in all_cards if c.state in {"running", "thinking"})` (line 426). This proves the contract; it is just expensive (full board build, correlation, grouping) for the question "how many are running right now?"

### 2.6 Every agent query is single-project

`agent_queries/_filters.py:35–52` (`resolve_project_scope`) is the entry point used by every service in the package (project_status, feature_forensics, planning, planning_sessions, workflow_intelligence, artifact_intelligence, reporting). A grep for `all.*project|cross.*project|all_projects` across `backend/routers/` and `backend/application/services/agent_queries/` returns no cross-project query path. `routers/projects.py:15–18` exposes `GET /api/projects` (listing), and `ProjectManager.list_projects()` (`backend/project_manager.py:96–97`) returns the in-memory project list loaded from `projects.json`. The current `projects.json` declares **36 projects** (verified by grep on `"id":`).

### 2.7 Startup-sync, cache warming, and other background jobs are single-project

`backend/adapters/jobs/runtime.py:135–186` shows the runtime starts `startup_sync` (line 137), `file_watcher` (line 163), `analytics_snapshot_task` (line 175), `telemetry_export_task` (line 178), `artifact_rollup_export_task` (line 181), and `cache_warming_task` (line 184) — all bound to `active_project` (line 116, `active_project = self.ports.workspace_registry.get_active_project()`). The runtime does **not** sweep all projects on a schedule.

### 2.8 Query cache exists but is project-scoped

`agent_queries/cache.py` provides `@memoized_query` used by e.g. `project_status.get_status` (line 96 in `project_status.py`). Cache TTL controlled by `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 60) per CLAUDE.md — but cache keys are derived per-`project_id`. No fingerprint exists for "all projects".

---

## 3. Question 1 — Live-Agents Signal Options

### Option A — DB count on `(project_id, status='active', updated_at recent)` (RECOMMENDED)

**Definition.** A session is "running" iff:
1. `sessions.status = 'active'` (the parser's terminal-event aware verdict), AND
2. `sessions.updated_at >= now() - 10 minutes` (the same `_ACTIVE_SESSION_WINDOW_SECONDS`, applied as a freshness clamp at query time).

**Query (sketch).**

```sql
SELECT COUNT(*)
FROM sessions
WHERE project_id = ?
  AND status = 'active'
  AND updated_at >= ?    -- now() - 10m, ISO string
  AND (session_type IS NULL OR session_type != 'subagent');  -- existing convention
```

**Cost.** O(rows-matching-project) without a new index; one `(project_id, status, updated_at)` composite index reduces it to O(active-rows). Even without the index, on a project with 10K cached sessions the scan is ~milliseconds.

**Accuracy.**
- *True positives:* live JSONL appends in the last 10 minutes — parser already marks `active`, watcher resync within seconds.
- *Eliminates false positives:* the freshness clamp catches the failure mode where a session ended without a terminal event AND the watcher didn't get a final mtime tick (e.g. process killed). The DB still says `status='active'` until the next file scan, but the `updated_at` predicate excludes it.
- *Caveat — non-active projects:* for projects not currently active, no watcher is running, so newly-started sessions in those projects won't be reflected until a sync runs. For Q1 (per-project count, called against a project the user is viewing) this is fine because viewing a project will typically be the active project. For Q2's home dashboard, this is a known staleness vector — covered below.

**Worked example.** A user has 3 Claude Code sessions and 1 Codex session open on the active project right now. Each writes JSONL lines every few seconds. `file_watcher` re-parses each on every change; each parse re-derives `status='active'` (no terminal event yet, mtime fresh) and `upsert` rewrites the row including `updated_at` (`sessions.py:89`). The COUNT(*) returns 4. If one of those terminals and writes a `turn_duration` system entry, the next watcher tick parses, derives `status='completed'`, upserts, and the next COUNT returns 3 within a few seconds at most.

**Pros.**
- Zero new schema, zero new background jobs.
- Reuses the contract already implicit in parser + sync_engine + frontend.
- Cheap enough to poll at 5–10s for live counters.
- Freshness clamp gives a hard upper bound on "stale active" rows.

**Cons.**
- Inherits the active-project-only freshness limitation for cross-project (Q2).
- A new composite index `(project_id, status, updated_at)` is desirable; adding it requires an Alembic-equivalent migration on the SQLite migrations file (`backend/db/sqlite_migrations.py`).

### Option B — Direct filesystem scan of session dirs (rejected)

Glob each project's `sessionsPath` for `*.jsonl` files with `mtime > now() - 10m`. Avoids DB entirely.

**Pros.** Always live, even for non-active projects (doesn't depend on the watcher).
**Cons.**
- Re-runs filesystem stat on potentially thousands of files per call.
- Bypasses the terminal-event detection — counts files that have written a final `turn_duration` but whose mtime is still fresh as "running".
- Diverges from the existing contract (`sessions.status`) and would create a second source of truth.

### Option C — Watcher event piggyback (rejected for now)

Maintain an in-memory `active_session_ids: set[str]` populated by `file_watcher._watch_loop`'s classified changes and decremented by terminal-event detection in `sync_engine`.

**Pros.** O(1) reads.
**Cons.**
- Only works for the active project (one watcher).
- Stateful, lost on process restart; requires reconstruction from DB on boot — at which point Option A's query *is* the reconstruction.
- Adds a new invalidation surface (subagents, forks, multi-platform sessions).

### Option D — `LiveEventBroker` subscription / SSE-derived count (rejected for the count)

`backend/routers/live.py` already exposes `GET /api/live/stream` over SSE with topic-filtered events. A client could subscribe to `session.*` and count distinct running sessions over a window.

**Pros.** Pushes updates.
**Cons.** Too heavy for "give me a number"; SSE is appropriate for the *delta* feed once the initial count exists. Better paired with Option A (poll the count, subscribe for changes).

### Recommendation — Q1

Adopt **Option A** with these specifics:

- Add `SessionsRepository.count_active(project_id, *, window_seconds=600, include_subagents=False) -> int`, internally building a `count(...)` call with `filters={"status": "active", "updated_start": iso_now_minus(window_seconds)}`.
- Add a migration to create `idx_sessions_project_status_updated ON sessions(project_id, status, updated_at)` — defensive for the future Q2 fan-out where the scan multiplies by 36 projects.
- Expose via a `SessionLiveCountsQueryService` (single-domain enough that it could also just live on `SessionIntelligenceReadService`; prefer the agent-queries home for transport-neutrality and so MCP/CLI can consume it without a router-only path).
- Window is configurable via env (`CCDASH_LIVE_AGENTS_WINDOW_SECONDS`, default 600) so the parser constant and the query stay in sync if the parser window is ever retuned.

---

## 4. Question 2 — System-Wide Metrics Architecture

The home dashboard needs an aggregate across all known projects. Three architectures.

### Option 1 — In-process fan-out across `WorkspaceRegistry.list_projects()` (RECOMMENDED for v1)

A new `SystemMetricsQueryService` lives in `backend/application/services/agent_queries/system_metrics.py`. Its primary method:

```text
get_overview(context, ports, *, include=[...]) -> SystemMetricsDTO
```

iterates `ports.workspace_registry.list_projects()` and for each project runs the Q1 `count_active` plus a small fixed bundle of cheap aggregates (e.g. `sessions.count` last 24h, `features.count_by_status` already used in `project_status.feature_counts`). Per-project work is gathered with `asyncio.gather` so the fan-out runs concurrently against the shared DB connection.

**DTO shape (sketch).**

```text
SystemMetricsDTO:
  generated_at: datetime
  projects: list[ProjectMetricSummary]
    project_id, project_name
    live_agents_count: int
    sessions_last_24h: int
    feature_counts: { "active": int, "blocked": int, ... }
    data_freshness: datetime          # max(sync_state.last_synced)
    is_active_project: bool
  totals:
    live_agents_count: int             # sum across projects
    projects_with_live_agents: int
    sessions_last_24h: int
  status: "ok" | "partial" | "error"
  source_refs: [...]
```

**Cost.** For 36 projects, with the recommended composite index from Q1, expect ~5–10 ms per project for the counts → ~50–100 ms wall clock when issued concurrently against SQLite (WAL mode), well below the 30s CLI timeout and acceptable for a home-dashboard load. Cached via `@memoized_query` with TTL = `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 60s); fingerprint composed from `(max(sessions.updated_at) per project, max(features.updated_at) per project, projects.json mtime)`. The cache turns repeat calls into ~5 ms.

**Pros.**
- Zero new schema beyond the Q1 index.
- Zero new background jobs.
- Reuses existing per-project repository methods; no SQL gymnastics.
- Trivially extensible: add a new per-project number → it shows up in totals.

**Cons.**
- **Staleness for non-active projects** — as documented in §2.7, only the active project has a live file watcher. A non-active project's `sessions.status='active'` rows reflect the moment it was last active (or last startup-synced). For "currently running agents across the system", this means the count is correct for the active project and an over-/under-count for others. Mitigations (any subset):
  - (a) Lazy on-demand rescan: when `system_metrics.get_overview` runs, for each non-active project trigger a light `sync_engine.sync_planning_artifacts(...)` + a sessions-dir glob-and-parse-recent pass. Bounded by the same `STARTUP_SYNC_LIGHT_MODE` plumbing (see `runtime.py:581–589`).
  - (b) Opt-in multi-project watching: extend `FileWatcher` to support N projects (the underlying `watchfiles.awatch` already accepts multiple paths — see `file_watcher.py:183`). Gated by an env flag like `CCDASH_WATCH_ALL_PROJECTS=false` for performance reasons.
  - (c) Annotate stale data in the DTO: `data_freshness` already exists; expose `is_stale: bool` per project so the UI can render an indicator.
- Cross-project DB scans require either a single DB (current default) or a more invasive change for multi-DB-per-project deployments — *current state has one shared `data/ccdash_cache.db`*, so this is fine.

### Option 2 — Cross-project repository method (one SQL per metric)

Add `SessionsRepository.count_active_by_project(project_ids=None) -> dict[str, int]` issuing a single `SELECT project_id, COUNT(*) ... GROUP BY project_id`. Service composes these dicts instead of fan-out.

**Pros.**
- One SQL per metric, regardless of project count — best raw performance at scale (hundreds+ of projects).
- Cleaner SQL; better index utilization for a `GROUP BY project_id`.

**Cons.**
- Each new metric requires a new aggregated repo method; harder to compose than Option 1.
- Less transport-neutral by accident: the repo starts to encode service-shaped aggregates.
- Marginal performance benefit at 36 projects; revisit if scaling to 1000+.

### Option 3 — Background-rollup table `project_metrics_snapshot`

A new table `project_metrics_snapshot(project_id, snapshot_at, live_agents_count, sessions_last_24h, feature_counts_json, ...)` written by a new background job (`_start_metrics_snapshot_task`) every N seconds. Reads always hit the snapshot.

**Pros.**
- Constant-time reads (1 row per project).
- Naturally supports historical timelines / sparklines for the dashboard.
- Friendly to future desktop widgets that want sub-50ms responses.

**Cons.**
- New schema + migration.
- New background job (must extend `adapters/jobs/runtime.py` to schedule cross-project work — non-trivial because all current jobs are active-project-scoped).
- Doesn't solve the active-vs-non-active project freshness problem (the rollup is only as fresh as the data it computes from, which still depends on watchers/syncs).
- Premature for v1 (~36 projects, no widgets shipped yet).

### Recommendation — Q2

Adopt **Option 1** (in-process fan-out) for v1 with the cache TTL knob to soften repeat-call cost. Reserve **Option 3** as a planned follow-on once the home dashboard is in user hands and we can measure call patterns + widget appetite. Pair v1 with mitigation (c) (stale-flag in DTO) plus a feature-flagged path for mitigation (a) (lazy rescan) — both are small additions and avoid touching the watcher topology in v1.

The widget story (mentioned in the prompt) maps to Option 3 cleanly: the snapshot table becomes the contract for a future Tauri/Electron widget that polls `/api/agent/system-metrics/snapshot` at 1Hz. Building Option 1 first keeps the API shape and consumer code identical; the snapshot is a backing-store swap, not a contract change.

---

## 5. Proposed Minimal API Surface

Naming follows existing conventions in `backend/routers/agent.py` and `agent_queries/` (transport-neutral, then exposed across REST + CLI + MCP).

### REST (additions to `agent_router` in `backend/routers/agent.py`)

```text
GET  /api/agent/project/{project_id}/live-counts
     -> { liveAgentsCount: int, windowSeconds: int, generatedAt: str, status: "ok"|"partial"|"error" }

GET  /api/agent/system-metrics/overview?include=live_agents,sessions_24h,feature_counts
     -> SystemMetricsDTO (see §4 Option 1)
```

Both are GETs, cacheable via `@memoized_query` with the existing TTL machinery.

### CLI (additions to `backend/cli/` — same Typer surface that already exposes `ccdash`)

```text
ccdash live counts                       # active project, formatted
ccdash live counts --project <id>        # explicit project
ccdash live counts --all --json          # system-wide JSON
ccdash system overview                   # human-readable rollup
ccdash system overview --json            # for piping
```

Reuses the existing `--timeout` / `--no-cache` / `--q` flags (CLAUDE.md "Standalone CLI").

### MCP (additions to `backend/mcp/server.py`)

```text
get_live_agent_counts(project_id: str | None = None) -> JSON
get_system_metrics_overview(include: list[str] | None = None) -> JSON
```

Both delegate to the same `SystemMetricsQueryService` / `SessionLiveCountsQueryService` per the "transport-neutral agent queries" rule in CLAUDE.md.

### Frontend touchpoints

- `Dashboard.tsx` gains a "Live now" chip near the existing `FeatureSummaryChip` (line 226), backed by a polling hook against `/api/agent/system-metrics/overview` (5–10s interval; degrade to manual refresh on tab hidden via the standard `document.visibilityState` pattern).
- `ProjectBoard.tsx` / `OpsPanel.tsx` use the per-project endpoint for the project header.

No new SSE topics needed for v1; if widget appetite materializes, a `system.live_counts.changed` topic on `LiveEventBroker` is the natural next step.

---

## 6. Open Questions & Risks

| # | Question / Risk | Notes |
|---|-----------------|-------|
| OQ-1 | Should "live agents" exclude `session_type='subagent'` by default? | Existing repo convention defaults to excluding subagents (`sessions.py:227–228`, `333–334`). Q1 should mirror, with an `include_subagents=False` flag. The planning board uses `include_subagents: True` (`planning_sessions.py:344`) — different audience, different default. |
| OQ-2 | Does the per-project session-id distinction handle multi-fork conversations correctly? | Same session forked → 2 rows, both could be `status='active'`. For "running agents" headcount this is probably fine (each fork is an agent process). Validate with a session that actually has `fork_count > 0`. |
| OQ-3 | What happens to the watcher when the user switches the active project? | `set_active_project` is called via `routers/projects.py:124–150` but I did **not** find a `file_watcher.stop()/start()` cycle wired to it. If the runtime keeps watching the previously-active project's directories, the cross-project freshness story is slightly better than §2.7 implies; if not, it's slightly worse. Needs runtime verification before committing the Q2 PRD scope. |
| OQ-4 | Postgres parity for the new index | `backend/db/sqlite_migrations.py` shows the SQLite schema; Postgres migration path lives under `backend/db/repositories/postgres/` + Alembic. The new composite index must be authored for both backends. |
| OQ-5 | Cache invalidation on session writes | `@memoized_query` fingerprinting on `agent_queries/cache.py` derives from data-version functions. The new service's fingerprint must include `max(sessions.updated_at)` per project, not just per the resolved scope. Needs a dedicated fingerprint helper. |
| Risk-1 | Staleness for non-active projects misleads users | Mitigate via `is_stale` flag + tooltip in UI; document the contract clearly. |
| Risk-2 | 10-minute window is too generous for "right now" | The parser constant is shared between FE and BE today; changing it has cross-cutting impact. Add the env override (`CCDASH_LIVE_AGENTS_WINDOW_SECONDS`) so operators can tighten the query window without changing the parser's classification rule. |
| Risk-3 | Cross-project fan-out blows up at 100+ projects | Acceptable at 36 (current). At ≥100, fall back to Option 2 (single GROUP BY) — same DTO, different repo method; one-line swap inside the service. |

---

## 7. Suggested Next Step

This work splits cleanly along tier boundaries:

1. **Tier 1 — Feature Contract: per-project live-agents count.**
   Path: `docs/project_plans/feature_contracts/features/live-agents-count-v1.md`
   Scope:
   - `SessionsRepository.count_active(project_id, *, window_seconds, include_subagents)`
   - New composite index `idx_sessions_project_status_updated` (SQLite + Postgres)
   - `SessionLiveCountsQueryService` in `agent_queries/`
   - `GET /api/agent/project/{project_id}/live-counts`
   - CLI `ccdash live counts` + MCP `get_live_agent_counts`
   - Optional: tiny `<LiveAgentsChip>` on `ProjectBoard`
   - Tests per `agent_queries/README.md` (happy / partial / error)
   - Estimated 4–6 pts.

2. **Tier 2 — PRD + Implementation Plan: system-wide metrics.**
   Path: `docs/project_plans/PRDs/features/system-wide-metrics-v1.md` (+ plan)
   Depends on (1). Scope:
   - `SystemMetricsQueryService` (in-process fan-out, cached)
   - `SystemMetricsDTO` + per-project summary DTO
   - `GET /api/agent/system-metrics/overview`
   - CLI `ccdash system overview` + MCP `get_system_metrics_overview`
   - `Dashboard.tsx` "Live now" chip + system-wide totals card
   - Stale-data indicator (`is_stale` per project)
   - Decide on opt-in multi-project watching (env flag only in v1)
   - Defer Option 3 (snapshot table) to a follow-on once widget plans firm up.
   - Estimated 8–10 pts.

Both work items reference this spike via `spike_ref` in their frontmatter once authored.

## Runtime Verification (OQ-3 Resolution) — 2026-05-20

Verified against the running local stack (backend :8000, SQLite `data/ccdash_cache.db`).

**Sub-question 1 — Does `set_active_project` rebind the watcher? Verdict: NO.**

- `POST /api/projects/active/3da60e0c-...` (CCDash) succeeded and `GET /api/projects/active` returned `CCDash`, but `GET /api/health/detail` → `detail.watcher.watchPaths` was unchanged and still pointed at the previous project's SkillMeat paths:
  `['/Users/miethe/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat', '.../skillmeat/docs/project_plans', '.../skillmeat/.claude/progress', '.../skillmeat/test-results']`.
- Code path confirms it: `backend/routers/projects.py:142` calls `core_ports.workspace_registry.set_active_project(project_id)`, which in `backend/adapters/workspaces/local.py:27-28` only delegates to `self._manager.set_active_project(...)`. There is no `file_watcher.stop()/start()`, no event/notifier, and no subscription from `RuntimeJobAdapter` to active-project changes. The watcher is started exactly once in `backend/adapters/jobs/runtime.py:162-172` against whatever `active_project` was at runtime startup, and stays bound for the life of the process. Active was restored to SkillMeat at the end of the test.

**Sub-question 2 — Staleness of `sessions.status` / `sessions.updated_at` for non-active projects. Verdict: ARBITRARILY STALE — only refreshed when that project happens to be active and the watcher (or a startup-sync) re-parses its files.**

- DB evidence (today is 2026-05-20):
  - Active project `3df0ff70-...` (SkillMeat): max `updated_at = 2026-05-20T03:24:47Z` — fresh, matches watcher behavior.
  - `3da60e0c-...` (CCDash itself): 1 row `status='active'`, `updated_at=2026-03-24T15:31:02Z` — ~57 days stale.
  - `verification-project`: 1 row `status='active'`, `updated_at=2026-02-16T16:45:58Z` — ~93 days stale.
- `SessionsRepository.upsert` (`backend/db/repositories/sessions.py:89`) writes `status` and `updated_at` only when sync runs for that project. Sync only runs from the watcher (active-project-bound), startup-sync (active-project-bound, `runtime.py:135-148`), or an explicit on-demand sync call. There is no per-project background touch.

**Sub-question 3 — Any startup-sync or periodic sweep that touches non-active projects? Verdict: NO.**

- `backend/adapters/jobs/runtime.py:110-188` resolves `active_project` once at `start()` (line 120) and scopes startup-sync (137), file_watcher (163), analytics_snapshot (175), telemetry_export (178), artifact_rollup_export (181), and cache_warming (184) to that single project. The cache-warming loop and analytics-snapshot loop both call `workspace_registry.get_active_project()` on each tick (lines 649, 745), so they continue to pin to whatever is *currently* active — still single-project, never a fan-out.
- `backend/db/sync_engine.py` and `backend/db/file_watcher.py` provide no sweep-all-projects entry point; sync is always invoked with a single `project_id`.

**Implication for Q2 system-wide metrics design.** §4 Option 1 (in-process fan-out across `workspace_registry.list_projects()`) as written returns **frozen snapshots, not live data** for non-active projects. The mitigation list in §4 was directionally right but understates the gap:

- Mitigation (c) (`is_stale` flag) is **mandatory, not optional** — without it, "live agents" totals will be wildly wrong (e.g. the current DB would report `verification-project` as having a live agent from 93 days ago). Even Option A's 10-minute `updated_at` freshness clamp from §3 handles this correctly *for query semantics* — stale active rows are excluded — but the resulting count will under-report any non-active project that does have live agents the watcher never saw. Either failure mode is silent without the flag.
- Mitigation (a) (lazy on-demand rescan during fan-out) becomes a **near-requirement** for the home-dashboard "currently running" promise. Without it, the cross-project live count is the active-project live count plus zero. A bounded `sessions-dir mtime-glob → parse-recent` pass per non-active project would close the gap; cost scales with active-session-file count, not total sessions.
- Mitigation (b) (multi-project watching via `watchfiles.awatch` over N paths) remains the correct **long-term** answer once widgets ship; v1 can ship without it if (a) is implemented.

**New risks / follow-up questions.**

- OQ-3a: `set_active_project` not rebinding the watcher is arguably a pre-existing bug (not just a Q2 design constraint). Cross-project freshness today depends on which project happened to be active at server start, not which the user is currently viewing. Worth a dedicated Tier 1 fix that wires the workspace registry to publish active-change events and the runtime job adapter to restart the watcher — independent of, and a precondition for, Q2.
- OQ-3b: The composite index proposed in §3 should include `updated_at` first or `(project_id, updated_at) WHERE status='active'` (partial) to keep the cross-project fan-out scan cheap once 36+ projects multiply the row count.
- OQ-3c: Light-mode rescan during `system_metrics.get_overview` must avoid stampeding the DB on home-dashboard load. Bound concurrency (`asyncio.Semaphore`) and respect `CCDASH_STARTUP_SYNC_LIGHT_MODE` semantics.

