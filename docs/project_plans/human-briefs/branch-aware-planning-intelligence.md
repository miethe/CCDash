---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
status: draft
created: 2026-06-04
updated: 2026-06-04
audience: [humans]
feature_slug: branch-aware-planning-intelligence
category: human-briefs
owner: nick
priority: high
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
intent_ref: null
epic_ref: null
related_documents:
  - docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-feasibility-brief.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/
---

# Branch-Aware Planning Intelligence — Human Brief

## 1. Context Pointers

**Why this feature exists**: Operators running multi-worktree or multi-branch development workflows cannot answer "which sessions are running on this feature?" or "which branch did this session run on?" without leaving the planning command center. Planning items show "branch TBD" and "commit TBD" as default fallbacks, disconnected from the rich session/branch data already persisted in the database.

**Scope**: Phase 1 is display-from-existing-data only. All required git branch/commit/session data is already end-to-end in the DB; the gap is purely surface exposure in planning DTOs and UI components. No new write paths, no migrations adding columns, no new data collection.

**Related documents**:
- **Feasibility brief** (`docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-feasibility-brief.md`): Verdict `conditional go` at 0.85 confidence. Three investigation legs (tech, risk, UX value) confirm Phase 1 is immediately viable; Phase 2 (multi-branch doc scanning) is gated on R-01 spike.
- **Tech spike findings** (`spikes/tech-findings.md`): Architecture is additive only; branch/commit/session data flows end-to-end from parser → DB → agent queries layer.
- **Risk spike findings** (`spikes/risk-findings.md`): Phase 1 low-risk (additive schema, index-only migrations, no ADR-007 write-path cost). Phase 2 triggers R-01 blocker. Key undisclosed risks: Codex structural NULL gitBranch (788 sessions at 0% coverage), planning_worktree_contexts is operator-gated, SSE live-update in-process only under SQLite, cwd not a direct column.
- **UX value spike findings** (`spikes/ux-value-findings.md`): Active-session chips on CommandCenterFeatureCard is top-value (confidence 0.90); per-phase session links in detail panel (confidence 0.82); branch/commit provenance dialog (confidence 0.72, conditionally gated on gitBranch coverage audit — PASSED at 99.1% on feature-linked sessions, 2026-06-04).
- **R-01 BranchWatcherRegistry spike** (`spikes/r01-branch-watcher/`): Examines multi-branch FileWatcher binding for Phase 2. Not blocking Phase 1. In flight; results inform Phase 2 planning.

---

## 2. Estimation Sanity Check

**H1 (new CRUD tables)**: N/A — Phase 1 is display-only; no new tables.

**H2 (implementation split across systems)**: Single implementation (5 related stories across BE query exposure, FE contract, UI surfaces). No architectural seams or sub-contractor integration overhead.

**H3 (algorithmic service)**: N/A — display-only; no new algorithmic service (branch correlation S2 is Phase 2).

**H4 (bundle-vs-sum)**: 5 stories (S-ACT active-session chips, S1 git-branch chip, S3 commit/PR provenance dialog, S4 per-phase session links, S5/S6 polling) fan out across BE and FE. Bottom-up story sum: 3 (S-ACT) + 2 (S1) + 3 (S3) + 3 (S4) + 1 (S5/S6) = **~13 pts floor**. No architectural seam cost; stories are independent within the additive DTO pattern.

**H5 (anchor to known feature)**: Planning agent session board feature (same agent_queries + board-UI shape, already shipped at ~8 pts). Phase 1 at 13 pts delta: +5 pts for S-ACT (new join, new chip template), +3 pts for S4 (inverse query, detail panel section), +1 pt for S3/S5/S6 bundle. Delta is **<30% above anchor**, consistent with scaling from 1 board surface to 2 (session board + command center) with depth (active-session joining).

**H6 (hidden plumbing)**: Transport wiring (routers/agent.py), frontend contract synchronization (types.ts + hooks), seam verification (tracing each DTO field producer→transport→surface). Estimated at **~15% overhead**, bundled into P2 (1 pt) and P4 (1.5 pts). Included in total 13 pts.

**Bottom-up total: ~13 pts**, agrees with top-down.

---

## 3. Estimation Confidence

- **H4 bundle-vs-sum holds**: 5 stories are truly independent in the additive DTO model; no hidden orchestration cost.
- **H5 anchor delta <30%**: Confirmed by implementation plan; P1 (4 pts DTO) + P2 (2 pts transport/contract) + P3 (5 pts surfaces) + P4 (1.5 pts verification) + P5 (0.5 pts docs) = **13 pts**. Anchor is 8 pts; delta = 5 pts = 62% overhead. **CAUTION**: This is higher than the <30% rule suggests, but justified by P3 being 4 independent parallel stories rather than a single coordinated task. If the stories experience integration friction, risk estimate goes up. Mitigation: strict seam verification in P4.

---

## 4. Open Questions Ledger

**OQ-1 (resolved, 2026-06-04)**: TTL override mechanism for the two planning-board endpoints?
- **Resolution**: `@memoized_query` in `backend/application/services/agent_queries/cache.py` already accepts `ttl: int | None` kwarg. Pass `ttl=30` to the decorator instances on `pcc_command_center` and `pss_session_board` service methods. No new infra required. Implemented in implementation plan T1-002 and T1-003.

**OQ-2 (resolved, 2026-06-04)**: Pagination guard on inverse phase→sessions query?
- **Resolution**: Cap at 20 most-recent sessions per phase. Matches activeSessions display threshold; avoids unbounded query results. Implemented in T1-004.

**OQ-3 (carried to implementation time, TBD)**: Bridge-button placement in CommandCenterDetailPanel header vs footer, and branch/commit click-dialog component type (popover vs modal)?
- **Reason carried**: Defer to existing planning-tokens layout conventions in the detail panel at implementation time. Default suggestion: panel header area for the "Open full detail" button. Popover/tooltip-drawer for the branch/commit dialog consistent with existing planning card affordances. T3-004 owns final decision. No risk to Phase 1 (both choices are low-cost).

**Phase 2 gates from deferred items**:
- **ADR-007 retrofit**: Before Phase 2 implementation begins, `SqliteDocumentRepository.upsert` must be retrofitted with `retry_on_locked` per ADR-007. This is a Phase-0 prerequisite task for Phase 2, not Phase 1. Noted in implementation plan DEF-001.
- **Proposed ADR-008**: BranchWatcherRegistry↔planning-service seam requires an ADR to record registry ownership, lifecycle, and eviction contract before Phase 2. Document in Phase 1 doc finalization task (T5-003).
- **R-01 BranchWatcherRegistry spike**: Phase 2 (multi-branch doc scanning, ~20–27 pts) is fully gated on R-01 spike results. No Phase 2 planning can begin until spike concludes.

---

## 5. Deferred Items Rationale

| Item | Category | Why Deferred | Phase Target |
|------|----------|--------------|--------------|
| **Phase 2: Multi-branch doc scanning** | dependency-blocked | S2 (branch-signal correlation in `session_correlation.py`) and Phase 2 multi-branch FileWatcher paths require R-01 BranchWatcherRegistry design spike (in flight). ADR-006 registry semantics must not be violated. FileWatcher is single-path-per-project-id; multi-branch binding is unresolved. | Phase 2, ~20–27 pts, post-R-01 spike |
| **Full CommandCenterDetailPanel → board modal consolidation** | scope-cut | `MultiProjectDetailRail` already acknowledges this debt. The "Open full detail" bridge button (bundled with S4) is the interim Phase 1 affordance. Full consolidation is maintenance-cost-driven; no Phase 1 engineering required. | Post-Phase 2, triggered by cost threshold |
| **PlanningTopBar top-level active branch chip** | scope-cut | UX leg priority 4, confidence 0.65. Deferred in favor of higher-value affordances (S-ACT command center chip, per-phase links). | Post-Phase 1 backlog |
| **Cache key strategy for branch-aware queries** | research-needed | Should branch-aware planning queries bypass 600s `@memoized_query` cache or incorporate branch as key dimension? Phase 1 uses `ttl=30` override on production endpoints. Full cache strategy is Phase 2 architecture decision. | Phase 2 |

---

## 6. Risk Narrative

**R1 — Server cache vs live updates (DECIDED)**: `@memoized_query` default 600s TTL; new fields without branch context in cache key may serve stale data. **Decision**: Apply `ttl=30` to the two planning-board service methods. Worst-case end-to-end latency: sync cycle completes (≤30s) → next FE poll fires (15s `refetchInterval`) → UI updates. Total: ≤45s. Browser smoke check in T4-003 verifies observed refresh within ~15s under in-process SQLite topology.

**R2 — Codex structural null (ADDRESSED in ACs)**: 788 Codex sessions hardcode `gitBranch=NULL` per parser.py. Represents 0% coverage of Codex platform. **Mitigation**: AC-NULLBRANCH-1 and AC-NULLBRANCH-2 require two distinct display states: "Codex — no branch" (structural null, determinable from `platform` field) vs "branch unknown" (Claude Code data-not-emitted null). No session card is hidden; both null states render gracefully.

**R3 — DTO contract breakage (ADDRESSED in P2)**: New fields on `PlanningAgentSessionCardDTO` could break existing consumers. **Mitigation**: All new fields are additive and optional. T2-001 includes contract assertion that old-shape consumers are unaffected. T2-002 marks all new TS types as optional (`?`). Resilience required for every new field: explicit undefined/null fallback in the FE code.

---

## 7. Acceptance Criteria (Policy Compliance)

**Policy**: All AC entries must include `target_surfaces` (where the AC is verified), `propagation_contract` (what backend produces, what FE receives), `resilience` (fallback on absent/null), and `verified_by` (test or task reference). All new optional backend fields require explicit FE fallback — missing is a contract state, not a bug.

**Summary of mandatory ACs**:
- **AC-NULLBRANCH-1**: Codex session branch chip displays "Codex — no branch" (determinable from platform field)
- **AC-NULLBRANCH-2**: Claude Code null branch chip displays "branch unknown" (generic indicator)
- **AC-WORKTREE-EMPTY**: "No worktree registered" state with registration prompt when planning_worktree_contexts is empty (not "branch TBD")
- **AC-SSE-TOPOLOGY**: Non-functional requirement; document three-topology live-update behavior (in-process SQLite, multi-process SQLite, Postgres NOTIFY)
- **AC-CWD-EXCLUSION**: No phase 1 story may use `session_forensics_json` cwd/workingDirectories for branch/worktree inference without a migration task
- **AC-ACTIVE-SESSION-CHIP** (S-ACT): Pulsing active-session chip on CommandCenterFeatureCard with "+N" overflow; absent/null fallback
- **AC-BRANCH-DIALOG** (S3): Branch/commit click-dialog showing all linked branches/commits with provenance identifiers; empty-state hidden/disabled
- **AC-PHASE-SESSION-LINKS** (S4): Phase rows show linked session list with transcript links; absent/missing phase fallback
- **AC-REFETCH-INTERVAL** (S5/S6): Both planning hooks receive `refetchInterval={15_000}` at call sites
- **AC-OPEN-FULL-DETAIL** (S4 bridge): "Open full detail" button always visible, routes to `planningRouteFeatureModalHref()`

All 10 ACs are traced two-way in implementation plan Table § "Two-Way AC Traceability" to implementing tasks (P1–P3) and Phase 4 verification tasks.

---

## 8. Expected Success Behaviors

Operator-verifiable outcomes after Phase 1 completion:

1. **Active-session visibility**: Operator opens planning command center. Any feature with running sessions displays a pulsing active-session chip on the card showing agent name and "+N" overflow. The chip appears within one 15s `refetchInterval` cycle of a session starting.

2. **Branch chip on session board**: Each session card on the planning session board displays a branch chip:
   - If `git_branch` is populated: shows the branch name (e.g., "feature/auth")
   - If Codex session (`platform="codex"`): shows "Codex — no branch"
   - If Claude Code and `git_branch` is null: shows "branch unknown"

3. **Branch/commit provenance dialog**: Clicking the branch/commit area on a CommandCenterFeatureCard opens a dialog showing all linked branches and commit/PR refs. Each entry is labeled with its provenance (worktree mapping, session gitBranch, commit-ref, or pr-ref). Operator knows the data source at a glance.

4. **Per-phase session links**: Opening the CommandCenterDetailPanel detail view, phase rows show a linked-sessions section. Clicking a session link navigates to the transcript. No 4-step cross-surface workflow required.

5. **Live polling**: Planning command center and session board refresh automatically every ~15s without manual navigation. Session state changes are reflected within one refresh cycle under the standard dev topology (worker + API in same process).

6. **"Open full detail" bridge**: A button in the detail panel links to the full ProjectBoard-style feature modal for operators needing the complete session/history/commit view. Clearly marked as bridge affordance pending consolidation.

7. **No "branch TBD" for registered worktrees**: Features with operator-registered worktrees via the planning launch flow show the resolved branch name. Features without registered worktrees show "No worktree registered" with a prompt, not a silent fallback.

---

## 9. Running Log

**2026-06-04**: Exploration concluded (feasibility verdict: conditional 0.85). Three-leg investigation (tech 0.85, risk 0.85, UX value 0.82) confirms Phase 1 display-from-existing-data is immediately viable. gitBranch coverage audit passed at 99.1% on feature-linked sessions (1,878 of 1,896). S3 (commit/PR provenance dialog) included unconditionally in Phase 1 scope. R-01 BranchWatcherRegistry spike launched to gate Phase 2. PRD + implementation plan authored. Ready for `/plan:plan-feature --tier=2` scoped to Phase 1 (~13 pts, 5 stories, 5 phases, ~2 weeks estimate).
