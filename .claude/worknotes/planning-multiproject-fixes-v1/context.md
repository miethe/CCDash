# Planning Multi-Project Fixes v1 — Context & Plan

Status: completed
Owner: orchestrated (Opus) → specialist subagents
Source: user bug report (2026-06-03) on the multi-project planning page.

## Verification (runtime + tests)

- Backend: 137 passed / 1 pre-existing failure (`test_job_adapter_..._api_profile`, unrelated `_maybe_start_drain_loop` SimpleNamespace) / 1 skipped.
- Frontend: `tsc --noEmit` clean on changed files; 100 vitest pass incl. 31-test a11y suite (no nested-button regression); production build OK.
- Runtime API smoke (isolated backend, existing cache):
  - Issue 1: multi-project session board `active_count=7` (was 0); `active_window_minutes=1 → 0`, `=43200 → 7` (param honored).
  - Issue 2: command-center `hide_done=false → 689` vs `true → 324` (365 Done excluded).
  - Issue 3: default sort = last_activity desc, nulls last (verified on real items).
  - Issue 4: `item.last_activity.timestamp` present in payload (nested under `item`).
  - Issue 5: portfolio `next_work_items` (20) all carry non-empty `project_id`.
- Post-review fixes: (a) closed cross-repo write-back leak on the steady-state watcher path (allow_writeback threaded through sync_changed_files → FileWatcher/registry); (b) reconciled active-window FE/BE param drift (FE omits default, BE honors active_window_minutes×60); (c) made all-projects sync a NON-BLOCKING background task (was inline-await in start(), which hung app startup).
- Operator note: a backend restart is required to backfill non-active projects in the existing DB (e.g. skillmeat `core-cache-boundary-refactor-v1` → completed). `CCDASH_SYNC_ALL_PROJECTS=false` restores active-only sync if the full sweep is too heavy.

## Scope — 6 confirmed issues

Diagnostics (parallel investigation workflow `planning-multiproject-diagnose`) confirmed each root cause against code + the live cache DB.

| # | Issue | Root cause (confirmed) | Layer |
|---|-------|------------------------|-------|
| 1 | Portfolio view never shows active sessions | Portfolio board uses `list_active(window_seconds=600)` (10-min liveness clamp); single-project board has no recency clamp. Newest active row ~8h old → portfolio always 0. NOT a project_id/FC-1 bug. | backend |
| 2 | Done items shown by default | Filter inits to "no filter"; backend filter is positive exact-match only (no exclusion). 84% of features are `done`. | BE+FE |
| 3 | Not sorted by activity | FE hardcodes `sortBy:'priority'`; backend has no `priority` branch (falls through to last_activity); toolbar `activity` value ≠ backend key. | BE+FE |
| 4 | No last-activity indicator | Timestamps already on wire (`item.lastActivity.timestamp`, `card.lastActivityAt`) but never rendered; session card shows `startedAt`; 6 local `relativeTime` copies lack a >24h absolute branch. | FE |
| 5 | Portfolio Overview not clickable | Lenses + project strip render as plain div/li (no onClick); filter setters already exist; `nextWork` lacks `projectId`. | BE+FE |
| 6 | Planning docs mis-detected (`core-cache-boundary-refactor-v1`) | PRIMARY: sync+watcher bind only to active project → non-active SkillMeat docs (Jun 1–2) never ingested → standalone-PRD `draft→backlog`. TERTIARY: `.claude/worknotes/` not a scan root. SECONDARY: standalone-PRD status not rolled up. | backend |

## Decisions

- **1**: New config `CCDASH_PLANNING_PORTFOLIO_ACTIVE_WINDOW_SECONDS` (default 30d). Surfaces recent indexed active sessions, excludes 57–93d phantom rows. Single-project board unchanged.
- **2**: Backend `hide_done` exclusion over full terminal set `{done,completed,closed,deferred,superseded}`. FE default ON + "Show done" toggle; URL-addressable in portfolio. Backend param default False (API back-compat); FE opts in.
- **3**: Default `sortBy:'last_activity'` desc; align toolbar; drop no-op `priority` option; missing timestamps sort last (both comparators).
- **4**: Shared `formatLastActivity` util in `lib/planningHelpers.ts` (relative <24h, `toLocaleString` >24h + full-datetime tooltip); render on work-item + session cards; null-safe.
- **5**: Single `<button>` per overview item (no nested-button regression; mirror `MultiProjectFilterRail.ProjectChip`). Project → `setProjectIds` toggle; Next Work → `openFeatureDetail` (extend `nextWork` with `projectId`).
- **6**: `CCDASH_SYNC_ALL_PROJECTS` flag (default ON, staggered) syncs all registered projects. **Frontmatter write-back stays disabled for non-active projects** (no mutation of other repos). Add `.claude/worknotes/` scan/watch root. Restart/re-sync backfills SkillMeat.

## Execution order (sequential — shared files agent.py/planning.ts/config.py)

1. BE: portfolio active-session window (issue 1)
2. BE: command-center filters + nextWork projectId + comparator missing-ts fix (issues 2 BE, 3 BE, 5 BE)
3. BE: all-projects sync + worknotes scan root (issue 6)
4. FE: filter/sort defaults, last-activity display, overview clickability (issues 2/3/4/5 FE)
5. Review (code-reviewer)
6. Verify: build + typecheck + targeted tests + runtime browser smoke (orchestrator)

## Notes / residual

- Single-project board still shows phantom 57–93d active rows (separate latent bug; out of scope — resolving issue 1's complaint, not perfect parity).
- After issue 6 ships, a restart / full sync is required to backfill non-active projects in the existing DB.
- Runtime smoke gate (CLAUDE.md) applies to FE changes before phase completion.
