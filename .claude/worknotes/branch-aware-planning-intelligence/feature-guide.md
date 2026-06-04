# Branch-Aware Planning Intelligence v1 — Feature Guide

## 1. What Was Built

Phase 1 surfaces existing git branch/commit data directly on CCDash planning board items. Five stories deployed:

- **S-ACT: Active-session chips** — Pulsing green dot + agent name + "+N" overflow on `CommandCenterFeatureCard` when running sessions exist
- **S1: Branch chips** — `git_branch` field on session board cards with distinct Codex "no branch" vs Claude Code "branch unknown" null states
- **S3: Provenance dialog** — Click branch/commit area to open dialog listing all linked branches and commit/PR refs with source identifiers
- **S4: Per-phase session links** — `CommandCenterDetailPanel` phase rows show linked sessions with transcript links; "Open full detail" bridge button
- **S5/S6: Live polling** — Both planning hooks poll at 15s intervals via `refetchInterval: 15_000`

All features are display-only; no new write paths introduced.

## 2. Architecture Overview

Data flows through CCDash's transport-neutral pattern:

**Backend (P1 DTO Exposure):**
- `PlanningAgentSessionCardDTO`: added `git_branch`, `git_commit_hash` (populated in `planning_sessions.py:build_active_session_card`)
- `PlanningCommandCenterItemDTO`: added `active_sessions` (join in `planning_command_center.py`), `commit_refs`, `pr_refs`
- `FeatureSummaryItem`: added `commit_refs`, `pr_refs` (from `features.data_json` via `planning.py:_build_summary_from_data`)
- `PhaseContextItem`: added `linked_sessions_by_phase: dict[int, list[SessionLink]]` (inverse phase→sessions via `entity_links` + `phase_hints`)
- DB index: `sessions(git_branch, project_id)` with `IF NOT EXISTS` guard

**TTL Override (R1 risk mitigation):**
- `@memoized_query(ttl=30)` on both planning-board service methods (`pcc_command_center`, `pss_session_board`)
- Reduces server cache from 600s default to 30s; frontend polls at 15s → effective staleness ≤45s

**Transport (P2):**
- Router updates: `backend/routers/agent.py` exposes new fields in API responses
- Frontend types: `types.ts` includes optional `git_branch?`, `activeSessions?`, `commit_refs?`, `pr_refs?`, `linkedSessionsByPhase?`
- Hook integration: `services/queries/planning.ts` accepts `refetchInterval` parameter; component call sites pass `refetchInterval={15_000}`

**Surfaces (P3):**
- `CommandCenterFeatureCard`: renders active-session chip row, provenance dialog trigger, empty-state "No worktree registered"
- `PlanningAgentSessionBoard`: renders branch chip below agent/model row with three null states
- `CommandCenterDetailPanel`: phase rows render session list; "Open full detail" button navigates to feature modal

## 3. SSE Topology Disclosure

Live session updates behave differently by deployment topology — a pre-existing constraint, not a Phase 1 limitation:

| Topology | Behavior |
|----------|----------|
| **Standard dev** (`npm run dev`, worker + API in same process) | Updates delivered within one 15s `refetchInterval` cycle. Session state changes written by worker reach API in-memory cache directly via SSE invalidation. |
| **SQLite, separate processes** | Live-update delivery **not guaranteed**. Worker state changes may not reach API's in-memory cache until the API's own sync cycle runs. 15s `refetchInterval` still fires but hits stale cache. |
| **Postgres** | Live updates delivered across processes via `NOTIFY` fanout. |

Code comments at hook call sites (`PlanningCommandCenter.tsx`, `PlanningAgentSessionBoard.tsx`) and in `services/queries/planning.ts` document this constraint.

## 4. How to Test

**API verification:**
```bash
curl -s http://localhost:8000/api/agent/planning/command-center \
  ?project_id=<id>&page=1 | jq '.data.items[0] | {active_sessions, commit_refs, pr_refs}'

curl -s http://localhost:8000/api/agent/planning/session-board \
  ?project_id=<id>&grouping=feature | jq '.data.groups[0].cards[0] | {git_branch, git_commit_hash}'
```

**Unit tests:**
- `backend/tests/test_t1_002_active_sessions_on_command_center_dto.py` — verifies `active_sessions` join
- `backend/tests/test_planning_commit_pr_refs_t1_003.py` — verifies `commit_refs`/`pr_refs` population
- `backend/tests/test_branch_index_and_phase_session_links.py` — verifies `linked_sessions_by_phase` and DB index
- `backend/tests/test_planning_session_board.py` — verifies `git_branch`/`git_commit_hash` on card DTO
- Frontend: `commandCenterBranchProvenanceDialog.test.tsx`, `commandCenterFeatureCardActiveSessions.test.tsx`, `planningAdapterFields.test.ts`

**Smoke test:**
```bash
CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true npm run dev
# Browser: planning command center + session board visible
# Verify: active-session chips render; branch chips show; refetch fires every ~15s
```

## 5. Known Limitations

- **Phase 2 deferred (DEF-001 through DEF-004):** Multi-branch FileWatcher, BranchWatcherRegistry, S2 branch-signal correlation, Phase 2 architecture decisions blocked on R-01 spike
- **cwd exclusion (AC-CWD-EXCLUSION):** No Phase 1 story uses `session_forensics_json` workingDirectories for branch/worktree inference
- **No new write paths:** All changes are read-only DTO exposure + additive index; ADR-007 compliance cost is zero
- **SQLite separate-process limitation:** Documented in SSE topology table above; multi-process deployments see stale cache until sync cycle runs
