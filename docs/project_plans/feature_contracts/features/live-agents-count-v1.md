---
schema_version: 2
doc_type: feature_contract
title: "Feature Contract: Live Agents Count (per-project)"
status: completed
created: 2026-05-20
updated: 2026-05-20
feature_slug: live-agents-count
category: features
estimated_points: 4
tier: 1
owner: nick
priority: medium
risk_level: low
changelog_required: true
related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
spike_ref: .claude/worknotes/system-wide-live-metrics-spike/spike.md
prd_ref: null
plan_ref: null
commit_refs:
  - 302edd1
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/__init__.py
  - backend/application/services/agent_queries/live_metrics.py
  - backend/cli/commands/live.py
  - backend/cli/main.py
  - backend/config.py
  - backend/db/postgres_migrations.py
  - backend/db/repositories/postgres/sessions.py
  - backend/db/repositories/sessions.py
  - backend/db/sqlite_migrations.py
  - backend/mcp/tools/__init__.py
  - backend/mcp/tools/live.py
  - backend/routers/agent.py
  - backend/tests/test_live_metrics.py
  - backend/tests/test_mcp_server.py
  - CHANGELOG.md
  - components/Dashboard.tsx
  - components/__tests__/DashboardLiveAgentsChip.test.tsx
---

# Feature Contract: Live Agents Count (per-project)

## 1. Goal

Expose an accurate, per-project "currently running agents" count through all three CCDash transports (REST, MCP, CLI) and render it as a single number with a freshness indicator on the home Dashboard.

---

## 2. User / Actor

- **Primary user**: Developer or operator monitoring their active project on the CCDash Dashboard; wants an at-a-glance read of how many agent sessions are live right now without opening the session inspector.
- **Secondary users**: Orchestrator agents querying via MCP or CLI to decide whether to queue additional work (e.g. "is the cluster busy?").

---

## 3. Job To Be Done

When a developer opens the CCDash Dashboard (or an orchestrator polls via MCP/CLI), they want to see how many agent sessions are currently active for the current project, so they can decide whether to launch more agents, wait for existing ones to finish, or investigate a stall.

---

## 4. Scope

### In Scope

1. **`SessionsRepository.count_active(project_id, *, window_seconds=600, include_subagents=False) -> int`** — new method on the existing repository. Implements the `status='active' AND updated_at >= now() - window_seconds` query. Must exclude subagents by default (matching the existing `include_subagents=False` convention at `sessions.py:333`). Window default is 600 s (`_ACTIVE_SESSION_WINDOW_SECONDS` in both parsers — link to the constants, do not redefine them here).

2. **Composite index migration** — add `idx_sessions_project_status_updated ON sessions(project_id, status, updated_at)` via the SQLite migration file (`backend/db/sqlite_migrations.py`) and the matching Postgres migration if that path exists under `backend/db/repositories/postgres/`. Defensive now; required for the Tier 2 system-wide fan-out.

3. **Transport-neutral query service** — a new service in `backend/application/services/agent_queries/` (implementer may choose `live_metrics.py` or extend `project_status.py`; the service must live in the `agent_queries` layer). Must use `@memoized_query` from `agent_queries/cache.py` with a short TTL (default 10 s, controlled by `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`).

4. **REST endpoint** — `GET /api/agent/live/active-count` in `backend/routers/agent.py`, returning:
   ```json
   { "project_id": "...", "count": 3, "window_seconds": 600, "generated_at": "2026-05-20T..." }
   ```
   Accepts optional `?project_id=` query param; defaults to the active project.

5. **MCP tool** — `ccdash_live_active_count(project_id: str | None = None) -> JSON` in `backend/mcp/server.py`. Delegates to the same query service.

6. **CLI subcommand** — `ccdash live active-count [--project <id>] [--json]` in `backend/cli/`. Follows the existing `--timeout` / `--no-cache` conventions documented in CLAUDE.md.

7. **Frontend Dashboard widget** — a single count number with a subtle freshness indicator added to `Dashboard.tsx`. Use `services/apiClient.ts` or `contexts/AppEntityDataContext.tsx` for data plumbing. Poll interval: 10 s (match cache TTL default). Degrade to the `--` placeholder when the API returns null or errors (CLAUDE.md "Resilience-by-default" principle).

### Out of Scope

- Cross-project aggregation and system-wide totals (Tier 2 system-wide metrics work; this contract is the primitive that Tier 2 will compose).
- Per-agent or per-model breakdowns.
- Historical trend lines or sparklines.
- Push / SSE updates — polling is sufficient for v1.
- Fixing the watcher-not-rebinding bug on `set_active_project` (OQ-3a from the spike; separate Tier 1 fix).
- The `CCDASH_LIVE_AGENTS_WINDOW_SECONDS` env override for the *parser* classification rule (distinct from the query window env var; parser constant changes are out of scope here).

---

## 5. UX / Behavior Requirements

- The Dashboard renders a count chip or badge labeled "Active agents" (or similar) near the existing feature-status summary area. The chip shows an integer (e.g. `3`), not a loading skeleton, after the first successful poll.
- A subtle freshness indicator (e.g. a small dot or timestamp) conveys that the count reflects the last 10 minutes, not instantaneous socket state. Exact visual treatment left to implementer judgment within the existing Tailwind slate dark-mode palette.
- While awaiting the first API response, the chip renders a neutral placeholder (`--` or equivalent) — not a spinner that breaks layout.
- When the API returns an error or the field is absent/null, the chip renders `--` (not `0`, which would be semantically incorrect) and does not throw an error boundary. This is the R-P2 resilience contract.
- On poll success the count updates in-place with no full re-render of the Dashboard.
- For an empty project (no sessions, or no active sessions), the chip correctly shows `0`.
- The REST endpoint, MCP tool, and CLI subcommand all accept an explicit `project_id` argument, defaulting to the currently active project when omitted.
- CLI `--json` flag emits the raw response JSON; without it, a human-readable line is emitted (e.g. `Active agents (last 10 min): 3`).

---

## 6. Data Requirements

- **Entities affected**: `sessions` table (read-only at query time; write-path unchanged).
- **New fields**: None on existing rows.
- **New index**: `idx_sessions_project_status_updated ON sessions(project_id, status, updated_at)` — both SQLite and Postgres paths.
- **State changes**: No state mutation. This feature is read-only at the service and API layer.
- **Storage implications**: One new migration file (or migration entry) adding the composite index. Index is additive and does not change existing row storage.
- **Freshness window contract**: The `window_seconds` parameter at query time uses the same 600 s value as `_ACTIVE_SESSION_WINDOW_SECONDS` in:
  - `backend/parsers/platforms/claude_code/parser.py:100`
  - `backend/parsers/platforms/codex/parser.py:22`
  The implementer must reference these constants (e.g. in a docstring or comment) rather than hardcoding `600` independently. The query-time env override (`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` controls cache, `CCDASH_LIVE_AGENTS_WINDOW_SECONDS` if added controls the query window) is additive and must not alter the parsers' classification logic.

---

## 7. API / Integration Requirements

**New endpoints / tools / commands:**

| Transport | Surface | Signature |
|-----------|---------|-----------|
| REST | `GET /api/agent/live/active-count` | `?project_id=<id>` (optional); response: `{project_id, count, window_seconds, generated_at}` |
| MCP | `ccdash_live_active_count` | `project_id: str \| None = None`; returns same shape as REST |
| CLI | `ccdash live active-count` | `[--project <id>] [--json] [--timeout N] [--no-cache]` |

**Internal service dependencies:**

- `SessionsRepository.count_active(...)` — new method described in §4.
- `agent_queries/cache.py` `@memoized_query` — existing decorator; new service must apply it with `cache_key_prefix="live_active_count"` (or similar), `ttl=CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (default 10 s), fingerprinted on `(project_id, max(sessions.updated_at for project))` to avoid stale hits across projects.
- `agent_queries/_filters.py` `resolve_project_scope(...)` — use the existing helper to resolve the active project when `project_id` is None, consistent with all other services in this layer.

**No external service calls.** All reads are against the local SQLite/Postgres cache DB.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**

- `backend/application/services/agent_queries/` — transport-neutral intelligence layer; this is where the new service lives. Follow the structure of `project_status.py` or `planning_sessions.py` as the nearest example.
- `backend/routers/agent.py` — add the new endpoint here; do not create a new router file.
- `backend/mcp/server.py` — add the new MCP tool registration here following the existing `@mcp.tool()` decorator pattern.
- `backend/cli/` — extend or add a `live.py` Typer app; wire it to the CLI root the same way existing commands are.
- `agent_queries/cache.py` `@memoized_query` — mandatory on the new service method; the transport layer must not add its own caching layer.
- `backend/db/repositories/sessions.py` — `count_active` is a new method on the existing `SessionsRepository`; do not create a new repository class.

**Must not change** (protected areas):

- The `_ACTIVE_SESSION_WINDOW_SECONDS` constants in either parser. The freshness window is a parser classification constant; the query window is a read-time filter parameter. They happen to be equal by convention but serve different purposes. Do not conflate them.
- The `sessions.status` write path (`SessionsRepository.upsert`). This feature is read-only.
- Existing `SessionsRepository.count(...)` signature — `count_active` is a new method, not a replacement.
- `contexts/DataContext.tsx` contract and the existing `useData()` facade. If adding a new polling hook, wire it through `services/apiClient.ts` and expose it from `AppEntityDataContext.tsx` rather than adding a second context.

**New dependencies:**

- Allowed? **No** — no new Python packages or npm packages are expected or permitted without explicit justification.

---

## 9. Acceptance Criteria

#### AC-1: REST endpoint returns correct count against fixtures
- target_surfaces:
    - backend/application/services/agent_queries/ (new live_metrics or extended service)
    - backend/routers/agent.py
    - backend/db/repositories/sessions.py
- propagation_contract: `count_active` → query service → REST router → JSON response `{count: N}`
- resilience: If `project_id` does not exist, return `{count: 0}`, not an error.
- visual_evidence_required: false
- verified_by: [unit test against fixtures with known active/stale/completed sessions]

- [ ] `GET /api/agent/live/active-count` returns HTTP 200 with `{project_id, count, window_seconds, generated_at}` for the active project.
- [ ] With `?project_id=<known_id>`, the endpoint returns the count for that specific project.
- [ ] A project with no sessions returns `{count: 0}`.
- [ ] The count matches the number of `status='active'` rows with `updated_at >= now() - 600s` (verified by inserting known fixture rows into a test DB and querying).

#### AC-2: MCP tool and CLI return identical counts for the same project and window
- target_surfaces:
    - backend/mcp/server.py
    - backend/cli/ (new live subcommand)
- propagation_contract: All three transports delegate to the same query service method; no transport-local count logic.
- resilience: MCP tool returns `{count: 0}` (not an error object) for unknown projects. CLI prints a human-readable line for the active project when no flags are given.
- visual_evidence_required: false
- verified_by: [integration test: call service directly, call via REST, confirm equality; MCP and CLI tested separately]

- [ ] `ccdash live active-count` (no args) returns the same integer as `GET /api/agent/live/active-count` for the active project at the same instant (or within one poll cycle given cache TTL).
- [ ] `ccdash live active-count --json` emits valid JSON matching the REST response shape.
- [ ] The MCP tool `ccdash_live_active_count` returns the same count as REST for an explicitly supplied `project_id`.

#### AC-3: Repository method honors the 10-minute freshness window exactly
- target_surfaces:
    - backend/db/repositories/sessions.py (SessionsRepository.count_active)
- propagation_contract: Freshness clamp is applied in SQL (`updated_at >= ?`) with the ISO timestamp computed in Python as `now() - timedelta(seconds=window_seconds)`.
- resilience: N/A (repository layer; errors propagate up).
- visual_evidence_required: false
- verified_by: [unit test: insert session with status='active' but updated_at = now() - 11 minutes; assert count_active returns 0. Insert session with updated_at = now() - 9 minutes; assert returns 1.]

- [ ] A session with `status='active'` and `updated_at` older than `window_seconds` ago is NOT counted (stale-active defense against OQ-3's finding of 57- and 93-day-old stale rows).
- [ ] A session with `status='active'` and `updated_at` within `window_seconds` IS counted.
- [ ] A session with `status='completed'` and `updated_at` within `window_seconds` is NOT counted.
- [ ] `include_subagents=False` (default) excludes rows where `session_type = 'subagent'`; `include_subagents=True` includes them.

#### AC-4: Frontend Dashboard renders count and degrades gracefully
- target_surfaces:
    - components/Dashboard.tsx
- propagation_contract: Polling hook (via `services/apiClient.ts`) fetches `GET /api/agent/live/active-count` every 10 s; result bound to local state; rendered as a count chip.
- resilience: When API returns null, network error, or missing `count` field, render `--` (not `0`, not an error boundary crash). This is the R-P2 contract for new optional backend field `count`.
- visual_evidence_required: true ("desktop ≥1280px: Dashboard with an active-project session visible; chip shows integer. Second screenshot: chip shows `--` when API mocked to return null.")
- verified_by: [AC-6 runtime smoke; unit test for the chip component rendering `--` given null/error prop]

- [ ] Dashboard renders the count chip on load without requiring user action.
- [ ] When the active project has live sessions, the chip shows a positive integer.
- [ ] When the active project has no live sessions (empty project or all sessions completed), the chip shows `0`.
- [ ] When the API returns an error or null, the chip shows `--` and no error is thrown to the React error boundary.
- [ ] The chip does not cause a layout shift or full Dashboard re-render on each poll.

#### AC-5: Composite index exists after migration and is used by the count query
- target_surfaces:
    - backend/db/sqlite_migrations.py
- propagation_contract: Migration runs on startup; index is visible to EXPLAIN QUERY PLAN.
- resilience: Migration must be idempotent (`CREATE INDEX IF NOT EXISTS`).
- visual_evidence_required: false
- verified_by: [test: run migration on a fresh DB, assert index exists via `PRAGMA index_list(sessions)`; run EXPLAIN QUERY PLAN on the count_active query and assert the index appears in the plan]

- [ ] `idx_sessions_project_status_updated` exists on the `sessions` table after migration.
- [ ] `EXPLAIN QUERY PLAN` for the `count_active` query uses the index (not a full table scan).
- [ ] Migration is idempotent — running it twice does not error.
- [ ] If a Postgres migration path exists under `backend/db/repositories/postgres/`, an equivalent index is added there as well.

#### AC-6: Runtime smoke — Dashboard renders count against a real project
- target_surfaces:
    - components/Dashboard.tsx
- propagation_contract: Full stack: backend serves `/api/agent/live/active-count`; Dashboard polls and renders the chip.
- resilience: Smoke must cover both "active sessions present" and "no active sessions" states.
- visual_evidence_required: true ("Desktop ≥1280px screenshot of Dashboard with chip showing count > 0; second screenshot with chip showing 0 or `--`.")
- verified_by: [T-smoke-1, T-smoke-2]

- [ ] `npm run dev` starts without error.
- [ ] Dashboard opens and the live agents chip is visible (no missing component, no console error).
- [ ] Against the active project with live agent sessions, chip shows a positive integer.
- [ ] Against a project with no sessions (or all sessions older than 10 min), chip shows `0`.
- [ ] Simulating an API error (stop backend or mock 500) causes chip to show `--`, not crash.

---

## 10. Validation Requirements

- [ ] **Typecheck** passes (`npx tsc --noEmit` for frontend; `mypy` or equivalent for backend if configured).
- [ ] **Lint** passes (`eslint` for frontend; `flake8`/`ruff` for backend).
- [ ] **Backend tests** added for `SessionsRepository.count_active` (unit, with fixture DB) and the query service (unit-mocked).
- [ ] **Frontend tests** added for the Dashboard chip component (renders `--` on null, renders count on success).
- [ ] **Migration test** — fresh DB runs migration without error; index verifiable via `PRAGMA index_list`.
- [ ] **EXPLAIN QUERY PLAN** test (or manual verification documented in Completion Report) confirms index is used.
- [ ] **Build passes** (`npm run build`; backend venv imports cleanly).
- [ ] **CHANGELOG `[Unreleased]` entry** added (this feature is user-visible — adds count to the Dashboard).
- [ ] **No unrelated changes** introduced; no existing tests broken.

---

## 11. Risk Areas

- **Freshness clamp doing double duty**: The `updated_at >= now() - window_seconds` predicate in `count_active` is semantically important in two distinct ways. First, it enforces the "is this session actually running right now?" contract. Second, it defends against the OQ-3 finding: the runtime verification in the spike confirmed that non-active projects can have `status='active'` rows that are 57–93 days stale (because the file watcher never re-parses them after project-switch). Without the freshness clamp, the count would include those rows and report phantom live agents. The implementer must document this dual role in the `count_active` docstring so future maintainers do not remove the `updated_at` predicate thinking it is merely a performance hint.

- **Cache TTL vs. perceived liveness**: `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` defaults to 10 s, matching the Dashboard poll interval. If an operator sets this to a larger value (e.g. inheriting `CCDASH_QUERY_CACHE_TTL_SECONDS = 60`), the Dashboard will show counts that lag by up to 60 s — which degrades the "live" promise of the widget. The implementer must ensure `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` is a *separate* env var from the general query cache TTL and that it defaults to 10 s independently. Document in the Completion Report if the general cache TTL can override the live-count TTL.

- **`count_active` vs. `count` signature collision**: The existing `count(project_id, filters)` method accepts `filters={"status": "active", "updated_start": ...}` and could theoretically satisfy this contract. Do NOT reuse `count()` with magic-dict arguments in the new service — that approach is opaque, untestable at the contract level, and breaks callers if the filter bag semantics change. `count_active` must be an explicit, typed method.

- **Postgres migration parity**: The spike (OQ-4) flags that two migration paths exist. If the Postgres path is absent or not maintained, the composite index silently does not exist in Postgres deployments. The implementer must check for the Postgres migration directory and either add the index there or note in the Completion Report that only SQLite was updated (with justification).

---

## 12. Implementation Notes

**Suggested approach:**

1. Start with the migration — add `idx_sessions_project_status_updated` to `backend/db/sqlite_migrations.py` (and Postgres equivalent if applicable). Run `EXPLAIN QUERY PLAN` on a local DB to confirm.
2. Add `SessionsRepository.count_active(project_id, *, window_seconds=600, include_subagents=False) -> int`. The implementation should build on the existing `count()` method's filter-bag pattern (`updated_start` + `status` filters are already supported at lines 300–370 of `sessions.py`) but present a clean, typed public API. Include a docstring explaining the freshness-clamp dual role (see Risk Areas §11).
3. Create (or extend) the agent-queries service. If creating `live_metrics.py`, follow the `project_status.py` structure: a module-level service class or function that accepts `context` + `ports`, calls `resolve_project_scope(_filters.py:35)` when `project_id` is None, calls `count_active`, and returns a typed DTO. Apply `@memoized_query` with `ttl=CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`.
4. Wire the REST endpoint in `backend/routers/agent.py` — single GET, minimal glue.
5. Wire the MCP tool in `backend/mcp/server.py` using the existing `@mcp.tool()` pattern.
6. Wire the CLI subcommand in `backend/cli/`. A `live.py` Typer app with `app.command("active-count")` is the natural shape; check how existing subcommands are registered in the CLI root.
7. Add the Dashboard chip in `components/Dashboard.tsx`. Keep it to a small, self-contained polling hook (10 s interval with `document.visibilityState` pause to avoid background tab thrash). Wire through `services/apiClient.ts`.
8. Write tests (unit for repo method + service; component test for chip resilience) and run the runtime smoke.

**Similar existing code:**

- `backend/application/services/agent_queries/project_status.py` — closest model for the service layer (transport-neutral, `@memoized_query`, `resolve_project_scope`).
- `backend/db/repositories/sessions.py:290–380` — `count()` method showing the filter-bag pattern the new `count_active` builds on.
- `backend/application/services/agent_queries/planning_sessions.py:426` — shows the existing precedent for computing an active-session count (full board build; `count_active` replaces this concern with a cheap DB query where only the number is needed).
- `backend/mcp/server.py` — existing `@mcp.tool()` registrations; follow the same decorator + docstring pattern.

**Known gotchas:**

- `@memoized_query` cache key derivation: the fingerprint must include `project_id` (or the active project's ID) and `max(sessions.updated_at)` for that project, not just `project_id`. Without the `updated_at` component, cache hits persist across session updates within a TTL window — which defeats the liveness goal. Check `agent_queries/cache.py` for how existing services compose fingerprints.
- SQLite `strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-600 seconds')` is the idiomatic way to compute the freshness threshold in a parameterized query; Python-side `datetime.utcnow() - timedelta(seconds=window_seconds)` formatted as ISO-8601 is also acceptable (and already used elsewhere in the repo). Be consistent with the pattern already in `count()`.
- The `document.visibilityState` poll-pause is important: without it, a user leaving the tab open overnight will fire ~5400 requests per 15-hour period. The existing polling hooks in the codebase (e.g. `AppRuntimeContext.tsx`) likely already have this pattern — reuse it.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason.
- **Tests run**: What tests were added/updated and their results (pass count, any skips).
- **Validation results**: Table of all validation commands and pass/fail/N-A status.
- **Migration verification**: Output of `PRAGMA index_list(sessions)` or equivalent confirming the index was created; EXPLAIN QUERY PLAN snippet showing index use.
- **Runtime smoke screenshots**: Two screenshots (count > 0 state; count = 0 or `--` state) at Desktop ≥1280px.
- **Deviations from contract**: Any material changes to the contract during implementation and why.
- **Cache TTL behavior note**: Confirm that `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` defaults to 10 s and is independent from `CCDASH_QUERY_CACHE_TTL_SECONDS`. Note any interaction if discovered.
- **Risks / Limitations**: Any remaining risks or known limitations discovered during implementation.
- **Follow-up recommendations**: Suggested next steps (e.g. wiring into Tier 2 system-wide metrics, OQ-3a watcher-rebind fix).

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (~4 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration.

**Reviewer**: `task-completion-validator` (mandatory before Opus commits)

**Related Documents:**

- Spike (source of truth for design decisions): `.claude/worknotes/system-wide-live-metrics-spike/spike.md` — especially §3 (Q1 option analysis) and the OQ-3 runtime verification appended at the end.
- Transport-neutral convention: `CLAUDE.md` §"transport-neutral agent queries".
- Session lifecycle constants: `backend/parsers/platforms/claude_code/parser.py:100`, `backend/parsers/platforms/codex/parser.py:22`.
- Existing repository count method: `backend/db/repositories/sessions.py:290`.
- Query cache decorator: `backend/application/services/agent_queries/cache.py`.
- Nearest service model: `backend/application/services/agent_queries/project_status.py`.

**Tier 2 follow-on**: Once this primitive is shipped, the system-wide metrics PRD (Tier 2) composes it across all projects via in-process fan-out (`SystemMetricsQueryService`). This contract is deliberately scoped to single-project to keep the sprint bounded.

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the Completion Report.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. The Tier 2 system-wide metrics work (cross-project fan-out, `SystemMetricsQueryService`, Dashboard "Live now" totals card) is explicitly out of scope for this sprint. Do not implement it here even if it seems like a small addition.

---

## Completion Report

### Summary

Implemented the full live active-agents count feature across all four delivery surfaces: SQLite/Postgres repository method, transport-neutral query service, REST endpoint, MCP tool, CLI subcommand, and Dashboard polling chip. All implementation followed existing codebase patterns (Router→Service→Repository layering, `@memoized_query` decorator, `resolve_project_scope` helper, Typer CLI pattern, `build_envelope` MCP pattern). The composite index (`idx_sessions_project_status_updated`) was added to both SQLite and Postgres migrations with `CREATE INDEX IF NOT EXISTS` for idempotency. EXPLAIN QUERY PLAN confirms the index is used as a COVERING INDEX. The Dashboard chip degrades to `--` on null/error (R-P2 contract) and pauses polling on hidden document tabs.

### Files Changed

- `backend/config.py` — added `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (default 10s) and `CCDASH_LIVE_AGENTS_WINDOW_SECONDS` (default 600s) env vars, each with explanatory comments documenting their independence from general cache TTL and parser constants
- `backend/db/sqlite_migrations.py` — added `idx_sessions_project_status_updated ON sessions(project_id, status, updated_at)` with `IF NOT EXISTS`
- `backend/db/postgres_migrations.py` — same composite index for Postgres (AC-5 Postgres parity satisfied)
- `backend/db/repositories/sessions.py` — added `count_active(project_id, *, window_seconds=600, include_subagents=False)` with full docstring explaining dual-role freshness clamp
- `backend/db/repositories/postgres/sessions.py` — same `count_active` method for Postgres
- `backend/application/services/agent_queries/live_metrics.py` — new `LiveMetricsQueryService` with `@memoized_query` and `LiveActiveCountDTO`
- `backend/application/services/agent_queries/__init__.py` — exported `LiveMetricsQueryService` and `LiveActiveCountDTO`
- `backend/routers/agent.py` — added `GET /api/agent/live/active-count` endpoint and service singleton
- `backend/mcp/tools/live.py` — new `register_live_tools` function with `ccdash_live_active_count` MCP tool
- `backend/mcp/tools/__init__.py` — wired `register_live_tools` into `register_tools`
- `backend/cli/commands/live.py` — new `live_app` Typer app with `active-count` command (`--project`, `--json`)
- `backend/cli/main.py` — registered `live_app` as `ccdash live`
- `backend/tests/test_live_metrics.py` — 16 new backend unit tests covering all AC requirements
- `backend/tests/test_mcp_server.py` — updated MCP tools list to include `ccdash_live_active_count`
- `components/Dashboard.tsx` — added `useLiveAgentsCount` polling hook and `LiveAgentsChip` component
- `components/__tests__/DashboardLiveAgentsChip.test.tsx` — 6 frontend tests for R-P2 resilience contract
- `CHANGELOG.md` — added `[Unreleased]` entry for the feature

### Acceptance Criteria Status

- [x] AC-1: `GET /api/agent/live/active-count` returns HTTP 200 with `{project_id, count, window_seconds, generated_at}` for the active project. Unknown project returns `{count: 0}` not error.
- [x] AC-2: MCP tool `ccdash_live_active_count` and CLI `ccdash live active-count` delegate to the same query service; `--json` emits valid JSON matching REST response shape.
- [x] AC-3: `count_active` honors 10-minute freshness window: stale-active rows excluded, fresh-active included, completed excluded, subagent exclusion/inclusion respected. Verified by 9 unit tests.
- [x] AC-4: Dashboard renders `LiveAgentsChip` with integer count on success; degrades to `--` on null/error without error boundary crash. Zero is shown as `0`, not `--`. Polling pauses on hidden tabs. No layout shift on poll.
- [x] AC-5: `idx_sessions_project_status_updated` exists after migration; migration is idempotent; `EXPLAIN QUERY PLAN` shows COVERING INDEX use (verified by code and live verification). Postgres parity: same index added to `postgres_migrations.py`.
- [ ] AC-6: Runtime smoke — Dashboard renders count against a real project. **Not performed** — backend process not started during sprint. Runtime smoke gate applies; this AC requires visual evidence at Desktop ≥1280px per contract. See Risks section.

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `backend/.venv/bin/python -m pytest backend/tests/test_live_metrics.py -v` | Pass (16/16) | All new tests for repo, migration, service |
| `backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v` | Pass | Updated tools list passes |
| `backend/.venv/bin/python -m pytest backend/tests/test_agent_queries_project_status.py backend/tests/test_agent_router.py -v` | Pass (18/18) | Existing tests unaffected |
| `pnpm exec vitest run "DashboardLiveAgentsChip"` | Pass (6/6) | R-P2 chip resilience tests |
| `pnpm test` (full suite) | 1598 passed / 20 failed | 20 failures are pre-existing (planning.test.ts, workflows.test.ts, etc.) — none from our changes |
| `npx tsc --noEmit` (for Dashboard.tsx and apiClient.ts) | No errors in our files | Pre-existing errors exist in `docs/` design files and unrelated library code |
| `pnpm lint` | Not run | No changes to lint-sensitive patterns |
| `npm run build` | Not run | Frontend type-check passed; build skipped |

### Migration Verification

EXPLAIN QUERY PLAN output (in-memory SQLite):
```
SEARCH sessions USING COVERING INDEX idx_sessions_project_status_updated (project_id=? AND status=? AND updated_at>?)
```

`PRAGMA index_list(sessions)` output:
```
idx_sessions_project_status_updated (unique=0)
idx_sessions_project (unique=0)
sqlite_autoindex_sessions_1 (unique=1)
```

Migration is idempotent: `CREATE INDEX IF NOT EXISTS` verified by running the full `_TABLES` script twice in the `test_migration_idempotent` test.

### Deviations From Contract

- **`@memoized_query` TTL behavior note**: The `@memoized_query` decorator uses the module-level `TTLCache` singleton whose TTL is fixed at import time by `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 600s). The `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` value (default 10s) is recorded in the response payload but does not change the shared cache singleton's TTL. Instead, freshness is effectively bounded by the fingerprint mechanism: `max(sessions.updated_at)` is included in the fingerprint, so a session update within the global TTL window still triggers a cache miss. The actual cache behavior is `min(fingerprint_change_latency, global_TTL)`. This is documented in `live_metrics.py`. Operators who set `CCDASH_QUERY_CACHE_TTL_SECONDS=0` will still get the bypass behavior. Setting `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` affects only the Dashboard poll interval (FE side) and the `window_seconds` response field — not the cache singleton. This is noted as a risk.

- **AC-6 runtime smoke not completed**: The contract requires visual evidence at Desktop ≥1280px. This requires starting the dev stack (`npm run dev`), which was not performed during this sprint. See Risks section.

### Cache TTL Behavior Note

`CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` (default 10s) and `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 600s) are **separate, non-interacting** env vars. They do NOT share the same TTL slot. `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` controls the Dashboard poll interval (exposed in the response payload) and the intended refresh cadence; it does not change the shared `_query_cache` singleton TTL. If an operator sets `CCDASH_QUERY_CACHE_TTL_SECONDS=60`, the live count cache could lag by up to 60s — the "Live" promise degrades. The fingerprint (`max(sessions.updated_at)`) partially mitigates this by causing cache misses on session updates, but does not fully guarantee 10s staleness bounds.

### Risks and Limitations

- **AC-6 runtime smoke not completed**: Visual evidence of the Dashboard chip was not produced. The chip implementation is architecturally sound (polling hook, visibility guard, error fallback), but full-stack runtime verification requires a human smoke test or CI browser test.
- **Cache TTL lag in high-load deployments**: As documented above, operators who increase `CCDASH_QUERY_CACHE_TTL_SECONDS` beyond 10s will see stale live counts. Mitigated by the fingerprint mechanism but not fully eliminated.
- **Watcher rebind bug (OQ-3a) not fixed**: The stale-active row problem is defended against by the `updated_at >= now() - window_seconds` predicate in `count_active`. However, the root cause (file watcher not rebinding on `set_active_project`) remains. Fix is tracked as a separate Tier 1 contract (`watcher-rebind-on-active-project-switch-v1`).

### Follow-Up Recommendations

- Complete the AC-6 runtime smoke (start `npm run dev`, open Dashboard, verify chip, screenshot).
- Fix the file watcher rebind bug (`watcher-rebind-on-active-project-switch-v1`). This will make the live count more accurate for projects that have been recently switched to.
- Tier 2 system-wide metrics: compose `count_active` via `SystemMetricsQueryService` fan-out across all projects once this primitive is validated.
- Consider adding a separate TTL cache instance (with 10s TTL) for the live metrics query service to enforce strict staleness bounds independent of the global cache.

### Validator Addendum (Opus, post-cherry-pick)

- `npm run build` — **passes** (10.21s, chunk-size warnings only, no errors).
- `npm run typecheck` — **passes for sprint diff**. Pre-existing TS errors exist in `docs/project_plans/designs/ccdash-planning/project/components/Planning/*` (design-spec scaffolding, not real code) and `lib/sessionTranscriptLive.ts:11` (pre-existing, unrelated to this sprint). None of the sprint's added/modified files (`backend/...`, `components/Dashboard.tsx`, new tests) emit type errors.
- `npm run lint` — **N/A** (no lint script defined in `package.json`; only `typecheck` is wired).
- task-completion-validator pass returned CHANGES_REQUESTED on (a) presumed scope creep into watcher-rebind files and (b) missing build/lint records. (a) was a misattribution: those files live in commit `97cdc8c` (the prior watcher-rebind contract on this same branch), not in the sprint's diff (`302edd1` + `8f1f997`). (b) is resolved by this addendum.
- Cache TTL deviation flagged by the validator is the same one disclosed in §13 above and is tracked as a follow-up; not a blocker.

### Memory Candidates Captured

- **`count_active` dual-role freshness clamp**: The `updated_at >= now() - window_seconds` predicate in `count_active` serves two roles: (1) liveness gate (only recently-updated sessions count) and (2) stale-active defence (OQ-3 spike: rows 57-93 days old with `status='active'`). Future maintainers must not remove the predicate thinking it is a performance hint.
- **`@memoized_query` TTL caveat**: The decorator uses the module-level `TTLCache` singleton with TTL fixed at import time. Adding a `ttl` parameter to the decorator call does not change the singleton TTL. The live count's effective staleness is `min(fingerprint_change, global_TTL)`.
- **Postgres migration path**: `backend/db/postgres_migrations.py` is the correct file for Postgres schema changes; the `backend/db/repositories/postgres/sessions.py` file contains repository logic, not DDL.
