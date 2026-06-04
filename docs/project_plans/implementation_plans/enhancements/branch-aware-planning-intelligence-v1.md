---
title: 'Implementation Plan: Branch-Aware Planning Intelligence v1'
schema_version: 2
doc_type: implementation_plan
status: approved
created: 2026-06-04
updated: '2026-06-04'
feature_slug: branch-aware-planning-intelligence
feature_version: v1
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
plan_ref: null
scope: "Surface git branch/commit provenance, live active-session chips, and per-phase\
  \ session links on planning board items using data already in the DB \u2014 display-only,\
  \ no new write paths."
effort_estimate: ~13 pts
architecture_summary: "Additive DTO field exposure across agent_queries layer \u2192\
  \ REST transport \u2192 frontend types/hooks \u2192 planning UI surfaces. Strict\
  \ layer order: backend query/DTO (P1) \u2192 transport + FE contract (P2) \u2192\
  \ frontend surfaces (P3) \u2192 verification (P4) \u2192 docs (P5)."
related_documents:
- docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-feasibility-brief.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
references:
  user_docs: []
  context:
  - docs/guides/feature-surface-architecture.md
  - .claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md
  specs: []
  related_prds:
  - docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
  - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
spike_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
adr_refs:
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
deferred_items_spec_refs: []
findings_doc_ref: null
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
changelog_ref: null
changelog_required: true
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: null
contributors: []
priority: high
risk_level: medium
category: product-planning
tags:
- implementation
- planning
- branch
- git
- sessions
- live-updates
- display-only
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/planning_sessions.py
- backend/application/services/agent_queries/planning_command_center.py
- backend/application/services/agent_queries/planning.py
- backend/db/repositories/feature_sessions.py
- backend/db/sqlite_migrations.py
- backend/routers/agent.py
- types.ts
- services/queries/planning.ts
- components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- components/Planning/CommandCenter/CommandCenterDetailPanel.tsx
- components/Planning/PlanningAgentSessionBoard.tsx
wave_plan:
  serialization_barriers:
  - types.ts
  - services/queries/planning.ts
  phases:
  - id: P1
    depends_on: []
    isolation: shared
    parallelizable: true
    owner_skills: []
    files_affected:
    - backend/application/services/agent_queries/models.py
    - backend/application/services/agent_queries/planning_sessions.py
    - backend/application/services/agent_queries/planning_command_center.py
    - backend/application/services/agent_queries/planning.py
    - backend/db/repositories/feature_sessions.py
    - backend/db/sqlite_migrations.py
  - id: P2
    depends_on:
    - P1
    isolation: shared
    parallelizable: false
    owner_skills: []
    files_affected:
    - backend/routers/agent.py
    - types.ts
    - services/queries/planning.ts
  - id: P3
    depends_on:
    - P2
    isolation: shared
    parallelizable: true
    owner_skills: []
    files_affected:
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
    - components/Planning/CommandCenter/CommandCenterDetailPanel.tsx
    - components/Planning/PlanningAgentSessionBoard.tsx
  - id: P4
    depends_on:
    - P3
    isolation: shared
    parallelizable: false
    owner_skills: []
    files_affected: []
  - id: P5
    depends_on:
    - P4
    isolation: shared
    parallelizable: false
    owner_skills: []
    files_affected:
    - CHANGELOG.md
    - .claude/worknotes/branch-aware-planning-intelligence/feature-guide.md
  waves:
  - - P1
  - - P2
  - - P3
  - - P4
  - - P5
---

# Implementation Plan: Branch-Aware Planning Intelligence v1

**Plan ID**: `IMPL-2026-06-04-BRANCH-AWARE-PLANNING-INTELLIGENCE`
**Date**: 2026-06-04
**Author**: Claude Sonnet 4.6 (Implementation Planner)
**Human Brief**: N/A — not created (feature fits within ~13 pts with clear anchor)
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Feasibility brief**: `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-feasibility-brief.md`

**Complexity**: Medium
**Total Estimated Effort**: ~13 pts
**Target Timeline**: ~2 weeks

---

## Executive Summary

Phase 1 of Branch-Aware Planning Intelligence closes the display gap between the DB data substrate and the planning board UI. All five stories (S-ACT active-session chips, S1 git-branch chip on session cards, S3 commit/PR provenance click-dialog, S4 per-phase session links, and S5/S6 polling) are implemented by progressively exposing existing DB fields up through the agent-queries layer, REST transport, TypeScript types, React Query hooks, and planning UI surfaces. No migrations add new columns; no write paths are introduced; ADR-007 compliance cost is zero.

The plan follows a strict five-phase sequence: backend DTO exposure (P1) → transport + frontend contract (P2) → frontend surface implementation (P3, stories fanned out in parallel) → verification with AC coverage matrix and seam assertions (P4) → documentation finalization (P5). Total estimate: ~13 pts.

---

## Implementation Strategy

### Architecture Sequence

This feature follows the CCDash transport-neutral pattern:

1. **Agent Queries Layer** — Additive DTO fields on `PlanningAgentSessionCardDTO`, `PlanningCommandCenterItemDTO`, `FeatureSummaryItem`, `PhaseContextItem`; inverse phase→sessions query; DB index migration.
2. **REST Transport** — Wire new fields through `backend/routers/agent.py`; update OpenAPI response shapes.
3. **Frontend Contract** — Update `types.ts`; extend `services/queries/planning.ts` hooks with `refetchInterval`.
4. **UI Surfaces** — React component changes across three planning components; bridge button; null-state chips.
5. **Verification** — AC coverage matrix, seam task, runtime browser smoke.
6. **Documentation** — CHANGELOG entry; feature-guide worknote with SSE topology disclosure.

### Parallel Work Opportunities

- **Phase 1**: Tasks within the phase are parallelizable per DTO — `git_branch` field on session card DTO, `activeSessions` on command center DTO, and `commit_refs`/`pr_refs` on feature summary item are independent subtasks.
- **Phase 3**: All four UI story tasks (S-ACT chip, S1 branch chip, S3 click-dialog, S4 phase session links + bridge button) are independent components; they can be assigned in a single parallel batch after P2 completes.

### Critical Path

P1 DTO exposure → P2 hooks/types → S4 per-phase links in `CommandCenterDetailPanel` (deepest UI story) → P4 seam verification task.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 1 | Backend Query / DTO Exposure | 4 pts | python-backend-engineer, data-layer-expert | sonnet | Parallel within phase per DTO; data-layer-expert for query review only |
| 2 | Transport + Frontend Contract | 2 pts | python-backend-engineer, ui-engineer-enhanced | sonnet | BE router + FE contract in one batch; barriers on types.ts / planning.ts |
| 3 | Frontend Surfaces | 5 pts | ui-engineer-enhanced, frontend-developer | sonnet | S-ACT/S1/S3/S4 fanned out in parallel; bridge button bundled with S4 |
| 4 | Verification | 1.5 pts | task-completion-validator, karen | sonnet | Sequential; karen at feature end |
| 5 | Documentation Finalization | 0.5 pts | documentation-writer | haiku | CHANGELOG + feature-guide SSE topology disclosure |
| **Total** | — | **~13 pts** | — | — | Bottom-up sum; anchored to planning-session-board feature (same shape, comparable scale) |

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| DEF-001 | dependency-blocked | Phase 2 multi-branch doc scanning (multi-branch FileWatcher paths, `BranchWatcherRegistry`, S2 branch-signal correlation `session_correlation.py`, ~20–27 pts) | R-01 BranchWatcherRegistry spike concludes at `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/`; ADR-007 retrofit of `SqliteDocumentRepository.upsert` as Phase-0 prerequisite task; proposed ADR-008 (BranchWatcherRegistry↔planning-service seam) drafted | `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md` (authored in DOC-006) |
| DEF-002 | scope-cut | Full `CommandCenterDetailPanel` → board modal consolidation (side-pane replacement; `MultiProjectDetailRail` debt) | Maintenance cost threshold crossed or explicit team decision post-Phase 2 | `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md` (authored in DOC-006) |
| DEF-003 | scope-cut | `PlanningTopBar` top-level active branch chip (UX leg priority 4, confidence 0.65) | Post-Phase 1 backlog review | Tracked inline in DEF-001 spec; no separate spec required |
| DEF-004 | research-needed | Cache-key strategy for branch-aware queries in multi-project/cross-branch scenarios | Phase 2 architecture decision after R-01 spike | Covered in DEF-001 Phase-2 spec |

**ADR-007 retrofit note (DEF-001 prerequisite)**: Before any Phase 2 implementation begins, `SqliteDocumentRepository.upsert` must be retrofitted with `retry_on_locked` per ADR-007. This is a Phase-0 task scoped to the Phase 2 plan, not this plan.

**Proposed ADR-008**: The BranchWatcherRegistry↔planning-service seam requires a proposed ADR to record the registry ownership, lifecycle, and eviction contract before Phase 2 implementation can begin. The DOC-006 task for DEF-001 must include a note on this dependency.

### In-Flight Findings

Findings doc is NOT pre-created. Path if needed: `.claude/findings/branch-aware-planning-intelligence-findings.md`. On first finding: set `findings_doc_ref` in this plan's frontmatter, append to `related_documents`, and add a DOC-006 row if the finding is load-bearing.

### Quality Gate

Documentation Finalization (Phase 5) cannot be sealed until:
- DEF-001 and DEF-002 each have a design-spec path in `deferred_items_spec_refs`, OR are explicitly marked N/A.
- DEF-003 and DEF-004 are documented as covered by the DEF-001 spec.
- `findings_doc_ref` is null (no in-flight findings) or the findings doc is finalized.

---

## Phase Breakdown

**Column conventions**:
- `Estimate` — story points
- `Model` — `sonnet` | `haiku` | `gpt-5.3-codex` | `gemini-3.1-pro` | `nano-banana-pro`
- `Effort` — reasoning budget. Claude: `adaptive` | `extended`. Codex: `none`–`xhigh`. Gemini: `none`–`high`.

---

### Phase 1: Backend Query / DTO Exposure

**Duration**: ~2 days
**Dependencies**: None
**Assigned Subagent(s)**: python-backend-engineer (primary), data-layer-expert (query review)
**Parallelizable**: Yes — tasks are independent per DTO target

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T1-001 | Add `git_branch` to `PlanningAgentSessionCardDTO` | In `backend/application/services/agent_queries/models.py`, add `git_branch: str \| None` and `git_commit_hash: str \| None` to `PlanningAgentSessionCardDTO`. In `planning_sessions.py:build_active_session_card`, populate both fields from `session.get("git_branch")` and `session.get("git_commit_hash")`. | DTO fields present and nullable; `build_active_session_card` populates from session dict; unit test asserts field is `None` for sessions lacking the key and populated correctly for sessions with the key; Codex-session fixture has `git_branch=None` with `platform="codex"` | 1 pt | python-backend-engineer | sonnet | adaptive | None |
| T1-002 | Add `activeSessions` to `PlanningCommandCenterItemDTO` | In `models.py`, define `AggregateWorkItemSession` (or reuse existing shape) and add `activeSessions: list[AggregateWorkItemSession]` to `PlanningCommandCenterItemDTO`. In `planning_command_center.py:PlanningCommandCenterQueryService`, add join that fetches sessions in `running` state for each feature using same pattern as `AggregateWorkItem.activeSessions` in multi-project path. Apply `@memoized_query("pcc_command_center", ..., ttl=30)` TTL override on the service method (OQ-1: resolved — decorator accepts `ttl: int \| None` param, pass `ttl=30`). | `activeSessions` populated in service-layer unit test with seeded running-state session fixture; field is an empty list (not null) when no sessions are running; TTL override verified in test by checking effective cache key TTL; `@memoized_query` `ttl=30` kwarg passed to the two planning-board service methods | 1.5 pts | python-backend-engineer | sonnet | adaptive | None |
| T1-003 | Add `commit_refs` / `pr_refs` to `FeatureSummaryItem` | In `models.py`, add `commit_refs: list[str]` and `pr_refs: list[str]` to `FeatureSummaryItem`. In `planning.py:_build_summary_from_data`, read `feature.commitRefs` / `feature.prRefs` (from `features.data_json` / `document_refs`) and populate the new fields. Apply `ttl=30` to the planning summary service method's `@memoized_query` invocation. | Fields populated in unit test against seeded `document_refs` fixture with `ref_kind='commit'` and `ref_kind='pr'`; both fields default to empty list when absent; no new DB queries introduced (reads from already-fetched feature data) | 1 pt | python-backend-engineer | sonnet | adaptive | None |
| T1-004 | Add `linked_sessions_by_phase` to `PhaseContextItem` + DB index | In `models.py`, define `SessionLink` (session_id, agent_name, start_time, transcript_href) and add `linked_sessions_by_phase: dict[int, list[SessionLink]] \| None` to `PhaseContextItem`. In `backend/db/repositories/feature_sessions.py`, add optional `phase_number` filter on `SqliteFeatureSessionRepository` using `entity_links` table and `phase_hints` column. Implement inverse phase→sessions query in `planning_sessions.py` (or `planning.py`). Add additive DB index `sessions(git_branch, project_id)` in `backend/db/sqlite_migrations.py` with `IF NOT EXISTS` guard. Pagination: cap results at 20 most-recent sessions per phase (OQ-2: resolved — cap=20 recommended). | Inverse phase→sessions query returns correct sessions for a seeded fixture with `phase_hints`; cap at 20 enforced and tested; index migration runs cleanly on existing DB with no column alterations; `IF NOT EXISTS` guard verified; `PhaseContextItem.linked_sessions_by_phase` is `None` when query returns no results | 1.5 pts | python-backend-engineer, data-layer-expert | sonnet | adaptive | None |

**Phase 1 Quality Gates:**
- [ ] All four DTO types updated with new fields; new fields optional/nullable
- [ ] Unit tests pass for all new service-layer methods against seeded fixtures
- [ ] `ttl=30` applied to both planning-board endpoint service methods (`pcc_command_center`, `pss_session_board`)
- [ ] DB index migration adds `sessions(git_branch, project_id)` with `IF NOT EXISTS` guard; no column modifications
- [ ] Transport-neutral pattern respected (agent_queries layer only; no router code in this phase)
- [ ] task-completion-validator signs off

---

### Phase 2: Transport + Frontend Contract

**Duration**: ~1 day
**Dependencies**: Phase 1 complete
**Assigned Subagent(s)**: python-backend-engineer (BE router), ui-engineer-enhanced (types.ts + hooks)
**Parallelizable**: No — `types.ts` and `services/queries/planning.ts` are serialization barriers; run as single batch after P1

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T2-001 | Wire new fields through `backend/routers/agent.py` | In `backend/routers/agent.py`, update the planning session board and planning command center endpoint response serialization to include the new DTO fields (`git_branch`, `git_commit_hash`, `activeSessions`, `commit_refs`, `pr_refs`, `linked_sessions_by_phase`). Ensure OpenAPI schema reflects new optional fields. | API returns new fields in response JSON; manual curl or contract test confirms field presence; old consumers (existing consumers of the planning endpoints) are unaffected — all new fields are additive and optional; OpenAPI schema updated | 0.5 pts | python-backend-engineer | sonnet | adaptive | T1-001, T1-002, T1-003, T1-004 |
| T2-002 | Update `types.ts` with new planning TS types | In root `types.ts`, add `git_branch?: string \| null` and `git_commit_hash?: string \| null` to the planning session card type; add `activeSessions?: AggregateWorkItemSession[]` to the planning command center item type; add `commit_refs?: string[]` and `pr_refs?: string[]` to the feature summary item type; add `linked_sessions_by_phase?: Record<number, SessionLink[]>` to the phase context item type. Define `SessionLink` interface. All new fields are optional (`?`) with explicit fallbacks. | TypeScript compiles with zero type errors; all new fields are optional; `SessionLink` interface matches backend `SessionLink` DTO shape; resilience: every new field has an explicit undefined/null fallback in the type (no non-null assertions) | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-001 |
| T2-003 | Add `refetchInterval` to both planning hooks | In `services/queries/planning.ts` (or the hook call sites in `PlanningCommandCenter.tsx` and `PlanningAgentSessionBoard.tsx`), pass `refetchInterval: 15_000` to `usePlanningCommandCenterQuery` and `usePlanningSessionBoardQuery` (including `usePlanningFeatureSessionBoardQuery`). Add code comment at each call site documenting the SSE topology constraint (AC-SSE-TOPOLOGY). | Call sites pass `refetchInterval={15_000}`; code comment present at each site explaining multi-process SQLite topology limitation; TypeScript compiles; existing hook API not changed (no new hook parameters needed) | 0.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-002 |

**Phase 2 Quality Gates:**
- [ ] API returns all new fields; contract test confirms old-shape consumers unaffected
- [ ] `types.ts` compiles; all new fields marked optional
- [ ] `refetchInterval: 15_000` present at both hook call sites with topology comment
- [ ] task-completion-validator signs off

---

### Phase 3: Frontend Surfaces

**Duration**: ~2 days
**Dependencies**: Phase 2 complete
**Assigned Subagent(s)**: ui-engineer-enhanced (primary), frontend-developer (secondary)
**Parallelizable**: Yes — S-ACT, S1, S3, and S4+bridge are independent components; fan out as a single parallel batch

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T3-001 | S-ACT: Active-session chip on `CommandCenterFeatureCard` | In `CommandCenterFeatureCard.tsx`, implement active-session chip row using `MultiProjectWorkItemCard.tsx` lines 97–123 as the direct template. Chip shows pulsing green dot + agent name + "+N" overflow when `activeSessions` is non-empty. Each chip includes a transcript link to `#/sessions/{session_id}`. Resilience: when `activeSessions` is absent or null, chip row is not rendered and no error is thrown. | Chip row renders with non-empty `activeSessions`; absent/null `activeSessions` renders nothing (unit test covers both states); "+N" overflow fires at same threshold as template; transcript link navigates to `#/sessions/{session_id}`; chip matches template visual at desktop ≥1280px | 1.5 pts | ui-engineer-enhanced | sonnet | adaptive | T2-002 |
| T3-002 | S1: `git_branch` chip on planning session board cards | In `PlanningAgentSessionBoard.tsx` (session card area), add a branch chip below the agent/model row. Three distinct states required: (1) `git_branch` populated → show branch name chip; (2) `git_branch` null and `platform === "codex"` → show "Codex — no branch" chip (AC-NULLBRANCH-1); (3) `git_branch` null and platform not codex → show "branch unknown" chip (AC-NULLBRANCH-2). Resilience: if `platform` field is absent but `git_branch` is null, fall back to AC-NULLBRANCH-2. Session card remains fully usable in all null states. | All three chip states render correctly in unit tests with appropriate fixtures; AC-NULLBRANCH-1 chip is visually distinct from AC-NULLBRANCH-2 chip at desktop ≥1280px; session card does not crash or hide when `git_branch` or `platform` is absent; verified_by: verify-nullbranch-codex, verify-nullbranch-claudecode | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T2-002 |
| T3-003 | S3: Branch/commit provenance click-dialog on `CommandCenterFeatureCard` | In `CommandCenterFeatureCard.tsx`, make the branch/commit area clickable to open a dialog/popover (OQ-3: resolved — use a popover/tooltip-drawer consistent with existing planning card affordances; implementation-time decision). Dialog shows all linked branches and commit/PR refs from `commit_refs` and `pr_refs`, each labeled with a provenance identifier (worktree, session-git-branch, commit-ref, or pr-ref). Resilience: when both `commit_refs` and `pr_refs` are absent or empty, the click trigger is hidden or disabled with tooltip "No branch or commit data linked." | Dialog opens on click and shows at least one entry with a visible provenance label in fixture test; empty-state trigger hidden/disabled with tooltip; dialog renders at desktop ≥1280px; verified_by: verify-branch-dialog, smoke-planning-command-center | 1 pt | ui-engineer-enhanced | sonnet | adaptive | T2-002 |
| T3-004 | S4: Per-phase session links in `CommandCenterDetailPanel` + bridge button | In `CommandCenterDetailPanel.tsx`, add a session list section below each phase row when `linked_sessions_by_phase[phase_number]` is non-empty. Each session entry shows agent name + start time + clickable transcript link (`#/sessions/{session_id}`). Resilience: when `linked_sessions_by_phase` is absent or phase key is missing, phase row renders without session section and no error is thrown. Also add "Open full detail" button (AC-OPEN-FULL-DETAIL) always visible when detail panel is open: calls `planningRouteFeatureModalHref(featureId)` from `services/planningRoutes.ts`; button is hidden or disabled with tooltip "Feature ID not available" when `featureId` is null/undefined. Bridge button placement: follow existing planning-tokens layout conventions in the detail panel header (OQ-3 bridge: implementation-time decision within panel header area). | Phase rows with sessions show the session list; phase rows without sessions render normally; transcript link navigates correctly; "Open full detail" button always visible with valid featureId; button hidden/disabled with null featureId; visual evidence at desktop ≥1280px; verified_by: verify-phase-session-links, smoke-planning-detail-panel | 1.5 pts | ui-engineer-enhanced, frontend-developer | sonnet | adaptive | T2-002 |

**Phase 3 Quality Gates:**
- [ ] All four story components pass their unit tests; resilience (null/missing field) states covered
- [ ] AC-NULLBRANCH-1 and AC-NULLBRANCH-2 chips are visually distinct
- [ ] AC-CWD-EXCLUSION: no `session_forensics_json` workingDirectories access in any Phase 3 change (code review gate)
- [ ] "Open full detail" button routes to `planningRouteFeatureModalHref` correctly
- [ ] Runtime smoke check: planning command center and session board render correctly with `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true` (R-P4 requirement; must be recorded before marking phase complete)
- [ ] task-completion-validator signs off

---

### Phase 4: Verification

**Duration**: ~0.5 days
**Dependencies**: Phase 3 complete
**Assigned Subagent(s)**: task-completion-validator (phase), karen (feature end)
**Parallelizable**: No — sequential

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T4-001 | AC coverage matrix verification | Run `ac-coverage-report.py` against the implementation. Verify every PRD AC ID (AC-NULLBRANCH-1, AC-NULLBRANCH-2, AC-WORKTREE-EMPTY, AC-SSE-TOPOLOGY, AC-CWD-EXCLUSION, AC-ACTIVE-SESSION-CHIP, AC-BRANCH-DIALOG, AC-PHASE-SESSION-LINKS, AC-REFETCH-INTERVAL, AC-OPEN-FULL-DETAIL) is covered by at least one task or test. Every PRD AC's `verified_by` list must reference an implemented test or task. | `ac-coverage-report.py` exits clean with no uncovered AC IDs; all `verified_by` references resolve to real tests/tasks | 0.5 pts | task-completion-validator | sonnet | adaptive | T3-001, T3-002, T3-003, T3-004 |
| T4-002 | Seam verification task (R-P3 mandatory) | `integration_owner: ui-engineer-enhanced`. Verify each new backend field propagates correctly through the full stack: producer (`planning_sessions.py` / `planning_command_center.py` / `planning.py`) → `routers/agent.py` → `types.ts` → planning query hook → each target_surface component (see all `target_surfaces` entries across PRD ACs). Verify absent-field fallback path for each field (unit test or fixture test). Target surfaces covered: `components/Planning/PlanningAgentSessionBoard.tsx`, `components/Planning/CommandCenter/CommandCenterFeatureCard.tsx`, `components/Planning/CommandCenter/CommandCenterDetailPanel.tsx`. | End-to-end propagation verified for all five new DTO fields; absent-field fallback confirmed for each surface; no target_surface is missing coverage; seam assertion documented in task output | 0.5 pts | task-completion-validator | sonnet | adaptive | T4-001 |
| T4-003 | Runtime browser smoke — all UI surfaces (R-P4) | With backend running (`npm run dev`, `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true`), perform manual browser smoke check covering: (1) Planning command center: active-session chip visible on feature card with running session; worktree-empty state shows correct label; branch/commit dialog opens; "Open full detail" button routes correctly. (2) Planning session board: git_branch chip renders in all three states (populated, Codex null, Claude Code null). (3) `CommandCenterDetailPanel`: phase row session list visible; transcript link navigates. (4) Board refreshes within ~15s of session state change. Record smoke evidence (screenshot spec: desktop ≥1280px). | Smoke evidence recorded for all four surface groups; no runtime errors in browser console; board refreshes observed at ~15s interval; evidence attached to task output or progress file | 0.5 pts | task-completion-validator | sonnet | adaptive | T4-002 |
| T4-004 | ADR-007 non-applicability confirmation | Confirm no new write paths exist in Phase 1–3 changes. Review all modified files in `backend/db/repositories/` for any `INSERT`, `UPDATE`, or `DELETE` operations introduced by this feature. Confirm the DB index migration (T1-004) is index-only (no column alterations). | Written confirmation: zero new write paths; DB migration is additive index only; ADR-007 `retry_on_locked` requirement does not apply to Phase 1 | 0 pts | task-completion-validator | sonnet | adaptive | T4-001 |

**Phase 4 Quality Gates:**
- [ ] `ac-coverage-report.py` clean — all PRD AC IDs covered
- [ ] Seam verification complete: all five new DTO fields traced producer→surface with fallback confirmed
- [ ] Runtime browser smoke recorded for all three planning UI components
- [ ] ADR-007 non-applicability confirmed in writing
- [ ] karen review complete (feature-end gate)

---

### Phase 5: Documentation Finalization

**Duration**: ~0.5 days
**Dependencies**: Phase 4 complete
**Assigned Subagent(s)**: documentation-writer (haiku)
**Parallelizable**: No — single batch

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T5-001 | CHANGELOG `[Unreleased]` entry | Using `changelog-generator` skill, add an `[Unreleased]` entry for the feature under the `Added` category. Entry covers: active-session chips on planning command center cards, git-branch chip on session board cards, commit/PR provenance click-dialog, per-phase session links in detail panel, "Open full detail" bridge button, and automatic 15s polling on both planning surfaces. Follow categorization rules in `.claude/specs/changelog-spec.md`. Set `changelog_ref: CHANGELOG.md` in plan frontmatter. | `[Unreleased]` section in `CHANGELOG.md` contains an entry matching this feature; `changelog_ref` frontmatter updated | 0.5 pts | documentation-writer | haiku | adaptive | All P1–P4 |
| T5-002 | Feature-guide worknote update with SSE topology disclosure | Create or update `.claude/worknotes/branch-aware-planning-intelligence/feature-guide.md`. Required sections: (1) What Was Built — active-session chips, branch chip, provenance dialog, phase session links, polling; (2) Architecture Overview — key files/layers, DTO chain, TTL override mechanism; (3) SSE Topology Disclosure — document the three-topology live-update behavior from AC-SSE-TOPOLOGY (in-process SQLite, separate-process SQLite, Postgres NOTIFY); (4) How to Test — CLI or API calls to verify new fields, smoke check instructions; (5) Known Limitations — Phase 2 deferred items, cwd exclusion, no new write paths. Keep under 200 lines. | Feature guide exists; SSE topology section present and accurate (matches AC-SSE-TOPOLOGY table); all five required sections present; under 200 lines | 0 pts | documentation-writer | haiku | adaptive | T5-001 |
| T5-003 | Author design specs for deferred items (DOC-006) | Author `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md` (maturity: shaping) for DEF-001 (Phase 2 multi-branch watcher/BranchWatcherRegistry/S2 correlation, ~20–27 pts). Include: open questions from R-01 spike, ADR-007 retrofit prerequisite for `SqliteDocumentRepository.upsert`, note on proposed ADR-008 (BranchWatcherRegistry↔planning-service seam). Author `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md` (maturity: idea) for DEF-002 (full CommandCenterDetailPanel → board modal consolidation). Set `prd_ref` to parent PRD in both specs. Append both paths to `deferred_items_spec_refs` in this plan's frontmatter. | Both design specs exist at canonical paths; `prd_ref` set correctly; DEF-001 spec includes ADR-007 retrofit and proposed ADR-008 notes; `deferred_items_spec_refs` in plan frontmatter populated | 0.5 pts | documentation-writer | sonnet | adaptive | T5-001 |
| T5-004 | Update plan frontmatter and CLAUDE.md pointer | Set `status: completed`, populate `commit_refs`, `pr_refs`, `files_affected`, `updated`, and `changelog_ref` in this plan's frontmatter. If CLAUDE.md needs a pointer to the SSE topology disclosure (agent-relevant behavior change), add a one-liner pointer under the Planning session board section. | Plan frontmatter reflects completed state; CLAUDE.md updated if applicable (≤3 lines added, pointer-only) | 0 pts | documentation-writer | haiku | adaptive | T5-003 |

**Phase 5 Quality Gates:**
- [ ] CHANGELOG `[Unreleased]` entry present and correctly categorized
- [ ] Feature guide exists at `.claude/worknotes/branch-aware-planning-intelligence/feature-guide.md` with SSE topology section
- [ ] Both deferred-item design specs authored; `deferred_items_spec_refs` populated
- [ ] Plan frontmatter complete (status, commit_refs, pr_refs, files_affected, updated, changelog_ref)
- [ ] task-completion-validator signs off

---

## Risk Mitigation

### Risk Table

| ID | Risk | Severity | Mitigation | Status |
|----|------|----------|------------|--------|
| R1 | **Server cache vs live updates**: `@memoized_query` 600s default TTL; `refetchInterval` polling re-reads stale server cache, defeating the "live" promise | HIGH | **Decided**: Apply `ttl=30` to `@memoized_query(...)` on the two planning-board service methods (`pcc_command_center`, `pss_session_board`). The decorator already supports `ttl: int \| None` — no new infra required (OQ-1 resolved). Freshness seam assertion: T4-002 must confirm end-to-end latency ≤45s (sync→API→UI) under in-process SQLite topology. | Decided — implement in T1-002/T1-003 |
| R2 | Codex structural null branch (788 sessions, parser hardcodes NULL) | HIGH | AC-NULLBRANCH-1 and AC-NULLBRANCH-2 are mandatory distinct display states. FE must branch on `platform_type`, never infer. T3-002 implements; T4-001 verifies AC coverage. | Addressed in T3-002 |
| R3 | DTO contract breakage for existing consumers of `PlanningAgentSessionCardDTO` | MED | All new fields additive + optional. T2-001 includes contract assertion that old-shape consumers are unaffected. R-P2 resilience ACs required for every new field. | Addressed in T2-001, T2-002 |
| R4 | "Active session" definition ambiguity for S-ACT chips | MED | Reuse session-board state classification from `planning_sessions.py` (state grouping already shipped). Do NOT invent a new liveness heuristic. T1-002 documents this constraint. | Addressed in T1-002 |
| R5 | Transcript link targets | LOW | Use existing HashRouter `#/sessions/{session_id}` route. No new route work. `planningRouteFeatureModalHref` already implemented. | No action needed |
| R6 | cwd/workingDirectories inference temptation | LOW | AC-CWD-EXCLUSION enforced at phase level; Phase 3 quality gate includes code-review check for any `session_forensics_json` access. | Enforced in P3 gate |

### Freshness Seam Assertion (R1)

Under in-process SQLite topology (`npm run dev`, worker + API in same process): `ttl=30` on the two planning-board endpoints means server cache expires in ≤30s. With `refetchInterval: 15_000`, the FE polls at 15s intervals. Worst-case end-to-end latency: sync cycle completes → server cache expires (≤30s) → next FE poll fires (≤15s) → UI updates. Total: ≤45s. T4-003 smoke check observes the board refreshing within ~15s.

---

## Two-Way AC Traceability

All PRD AC IDs must appear as `verified_by` references in at least one Phase 4 verification task. The table below cross-references each PRD AC to its implementing phase task(s) and Phase 4 verification.

| PRD AC ID | Implementing Task(s) | Phase 4 Verified By |
|-----------|---------------------|---------------------|
| AC-NULLBRANCH-1 | T3-002 | T4-001 (ac-coverage-report), T4-002 (seam), T4-003 (smoke) |
| AC-NULLBRANCH-2 | T3-002 | T4-001 (ac-coverage-report), T4-002 (seam), T4-003 (smoke) |
| AC-WORKTREE-EMPTY | T1-002, T3-001 | T4-001 (ac-coverage-report), T4-003 (smoke) |
| AC-SSE-TOPOLOGY | T2-003 (code comment), T5-002 (feature guide) | T4-001 (ac-coverage-report) |
| AC-CWD-EXCLUSION | P3 code-review gate | T4-001 (ac-coverage-report), T4-004 (ADR-007 confirmation) |
| AC-ACTIVE-SESSION-CHIP | T1-002 (backend), T3-001 (frontend) | T4-001, T4-002, T4-003 (smoke-planning-command-center) |
| AC-BRANCH-DIALOG | T1-003 (backend), T3-003 (frontend) | T4-001, T4-002, T4-003 (smoke-planning-command-center) |
| AC-PHASE-SESSION-LINKS | T1-004 (backend), T3-004 (frontend) | T4-001, T4-002, T4-003 (smoke-planning-detail-panel) |
| AC-REFETCH-INTERVAL | T2-003 | T4-001, T4-003 (observed 15s refresh) |
| AC-OPEN-FULL-DETAIL | T3-004 | T4-001, T4-003 (smoke-planning-command-center) |

#### AC-NULLBRANCH-1: Codex session branch chip
- target_surfaces:
    - components/Planning/PlanningAgentSessionBoard.tsx
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- propagation_contract: `PlanningAgentSessionCardDTO.git_branch` is `null` and `PlanningAgentSessionCardDTO.platform` is `"codex"`. Each target surface reads both fields to determine the chip label.
- resilience: If `platform` field is absent but `git_branch` is null, fall back to AC-NULLBRANCH-2 (generic "branch unknown"). Do not crash or hide the session card.
- visual_evidence_required: branch chip renders with "Codex — no branch" label at desktop width ≥1280px
- verified_by: [T4-001, T4-002, T4-003]

#### AC-NULLBRANCH-2: Claude Code null branch chip
- target_surfaces:
    - components/Planning/PlanningAgentSessionBoard.tsx
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- propagation_contract: `PlanningAgentSessionCardDTO.git_branch` is `null` and `platform` is not `"codex"`. Target surfaces render the generic null-branch indicator.
- resilience: Render "branch unknown" indicator. Session card remains fully visible and usable.
- visual_evidence_required: chip renders with "branch unknown" label at desktop width ≥1280px, distinct from AC-NULLBRANCH-1 chip
- verified_by: [T4-001, T4-002, T4-003]

#### AC-WORKTREE-EMPTY: Feature card branch empty state
- target_surfaces:
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- propagation_contract: `PlanningCommandCenterItemDTO.worktree` is `null` or absent. Card branch row reads this field and renders the empty state when null.
- resilience: Render "No worktree registered" text with visible registration affordance. Do NOT render "branch TBD". Do NOT render an error state.
- visual_evidence_required: empty-state renders at desktop ≥1280px with both label and affordance visible
- verified_by: [T4-001, T4-003]

#### AC-ACTIVE-SESSION-CHIP: Active session chip rendering
- target_surfaces:
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- propagation_contract: `PlanningCommandCenterItemDTO.activeSessions` (new field) is populated by the backend query and received by the card component. Component renders chip row when `activeSessions` is non-empty.
- resilience: When `activeSessions` is absent or null, chip row is not rendered. No error is thrown. Fallback must be covered by a unit test.
- visual_evidence_required: pulsing green dot + agent name + "+N" overflow chip visible at desktop ≥1280px with at least one active session
- verified_by: [T4-001, T4-002, T4-003]

#### AC-BRANCH-DIALOG: Branch and commit provenance dialog
- target_surfaces:
    - components/Planning/CommandCenter/CommandCenterFeatureCard.tsx
- propagation_contract: `FeatureSummaryItem.commit_refs` and `pr_refs` (new fields) are populated from `features.data_json` by `planning.py:_build_summary_from_data` and delivered to the card component. Each entry shows a link-provenance identifier.
- resilience: When `commit_refs` and `pr_refs` are both absent or empty, the click-dialog trigger is hidden or disabled with tooltip "No branch or commit data linked."
- visual_evidence_required: dialog opens on click and shows at least one entry with a visible provenance label at desktop ≥1280px
- verified_by: [T4-001, T4-002, T4-003]

#### AC-PHASE-SESSION-LINKS: Phase rows show linked sessions
- target_surfaces:
    - components/Planning/CommandCenter/CommandCenterDetailPanel.tsx
- propagation_contract: `PhaseContextItem.linked_sessions_by_phase` (new field) is populated via inverse phase→sessions query using `entity_links` and `phase_hints`. Detail panel renders session list below each phase row when phase has linked sessions.
- resilience: When `linked_sessions_by_phase` is absent or the phase key is missing, the phase row renders without a session section. No error state.
- visual_evidence_required: at least one phase row with a session list visible at desktop ≥1280px; each session entry has a clickable transcript link
- verified_by: [T4-001, T4-002, T4-003]

---

## Open Questions Resolution

| OQ | Question | Resolution |
|----|----------|------------|
| OQ-1 | Exact TTL override mechanism for the two planning-board endpoints | **Resolved inline**: `@memoized_query` in `backend/application/services/agent_queries/cache.py` (line 921) already accepts `ttl: int \| None` as a keyword argument. Pass `ttl=30` to the decorator instances for `pcc_command_center` and `pss_session_board`. No new infra needed. Implemented in T1-002 and T1-003. |
| OQ-2 | Whether the inverse phase→sessions query needs a pagination guard | **Resolved**: Cap at 20 most-recent sessions per phase. This matches the `activeSessions` display threshold and avoids unbounded query results. Implemented in T1-004. |
| OQ-3 | Bridge-button placement in `CommandCenterDetailPanel` header vs footer | **Carried as implementation-time decision**: Defer to existing planning-tokens layout conventions in the detail panel at implementation time. The panel header area is the default suggestion per decisions block §8. Task T3-004 owns this decision. |

---

## Wrap-Up: Feature Guide & PR

After all phase quality gates pass:

1. Verify `.claude/worknotes/branch-aware-planning-intelligence/feature-guide.md` committed (T5-002).
2. Open PR:

```bash
gh pr create \
  --title "feat(planning): branch-aware planning intelligence v1 — live session chips, branch provenance, phase links" \
  --body "$(cat <<'EOF'
## Summary
- Active-session chips on CommandCenterFeatureCard show running sessions within 15s without leaving the planning surface
- git_branch chip on session board cards with distinct Codex/Claude Code null states; commit/PR provenance click-dialog on feature cards
- Per-phase session links in CommandCenterDetailPanel enable one-click transcript access from phase rows; "Open full detail" bridge button
- Both planning hooks poll at refetchInterval=15s; planning-board endpoint cache TTL reduced to 30s

## Feature Guide
.claude/worknotes/branch-aware-planning-intelligence/feature-guide.md

## Test plan
- [ ] Unit tests pass for all new DTO fields (backend service layer)
- [ ] TypeScript compiles with zero errors
- [ ] AC coverage report clean (all 10 PRD AC IDs covered)
- [ ] Smoke-tested locally with CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true
- [ ] Board refresh observed within ~15s of session state change

Generated with Claude Code
EOF
)"
```

---

**Progress Tracking:**

See `.claude/progress/branch-aware-planning-intelligence/`
