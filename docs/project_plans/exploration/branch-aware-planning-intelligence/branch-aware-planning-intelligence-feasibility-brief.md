---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Branch-Aware Planning Intelligence \u2014 Feasibility Brief"
status: finalized
created: 2026-06-04
updated: '2026-06-04'
feature_slug: branch-aware-planning-intelligence
verdict: conditional
verdict_confidence: 0.85
exploration_charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
proposed_adr_ref: null
recommended_next_action: "Proceed to /plan:plan-feature --tier=2 scoped to Phase 1\
  \ (~9-12 pts) covering S-ACT active-session chips, S1 git_branch chip, S3 commitRefs/prRefs\
  \ click-dialog (UNGATED \u2014 coverage audit 2026-06-04 passed with 99.1% of feature-linked\
  \ sessions carrying non-null git_branch), S4 per-phase session links, and S5/S6\
  \ refetchInterval live updates. Phase 2 (multi-branch doc scanning + S2 correlation,\
  \ ~6 pts) remains gated on the R-01 BranchWatcherRegistry spike (launched 2026-06-04,\
  \ results under spikes/r01-branch-watcher/). Phase 1 PRD must still include ACs\
  \ for Codex structural null-branch display (788 sessions at 0% coverage) vs data-not-emitted\
  \ null, planning_worktree_contexts empty state, SSE in-process-only topology disclosure\
  \ under SQLite, and must exclude cwd/workingDirectories-based inference unless a\
  \ migration task is added."
related_documents:
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
---

# Branch-Aware Planning Intelligence — Feasibility Brief

---

## 1. Synopsis

Branch-aware planning intelligence surfaces git branch/commit provenance, live session state, and per-phase session links on CCDash planning board items. The idea emerged from an operator report that planning items cannot be traced to the sessions or commits that produced them, and that work on non-checked-out branches is invisible on the planning board. Three investigation legs (technical current-state, risk/blast-radius, and UX value) were run in parallel. The verdict is **conditional go**: a meaningful display-first phase is immediately feasible using data already in the pipeline, while a second phase involving multi-branch document scanning is gated on a named prerequisite spike.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| tech | research-technical-spike | 0.85 | [tech-findings.md](spikes/tech-findings.md) | Branch/commit/session data is already end-to-end in the DB; the gap is surface exposure in planning DTOs and card components. Deal-killer not triggered. A 7-pt display-first path (S1+S3+S5+S6) and a 15-pt full-scope path are both viable without new filesystem scanning. Note: active-session chips and per-phase session links are not included in the tech leg's story table but are confirmed feasible via existing DTO and query patterns. |
| risk | backend-architect | 0.85 | [risk-findings.md](spikes/risk-findings.md) | Phase 1 (display-from-existing-data) is low-risk: all required schema additions are additive, ADR-007 compliance is straightforward, and live updates need only a refetchInterval argument per planning hook. Phase 2 (multi-branch doc scanning) partially triggers the charter deal-killer and is blocked on a dedicated watcher multi-branch binding spike (R-01). Key undisclosed risks addressed below: cwd/workingDirectories is NOT a direct DB column; planning_worktree_contexts is operator-gated; SSE live-update is in-process only under SQLite; gitBranch coverage confidence is 0.50. |
| ux-value | ux-researcher | 0.82 | [ux-value-findings.md](spikes/ux-value-findings.md) | No deal-killers. Structural UX scaffolding already exists across three surfaces. Active-session chips on CommandCenterFeatureCard are the highest-value, lowest-risk affordance (confidence 0.90, direct template in MultiProjectWorkItemCard lines 97–123). Per-phase session links in CommandCenterDetailPanel are high-value (confidence 0.82) and have no multi-branch dependency. Branch/commit click-dialog (S3) is CONDITIONALLY medium-value (confidence 0.72) — explicitly gated on tech-leg confirmation of gitBranch data quality. Full side-pane-to-board-modal consolidation is deferred. |

**Weighted aggregate confidence**: (0.85 + 0.85 + 0.82) / 3 = **0.84** (rounded to 0.85 for final verdict given the display-first path is unambiguously feasible).

---

## 3. Cost Estimate (Revised)

**Rough estimate**: 9–15 story points (Tier 2)

**Display-first path (Phase 1 core — unconditional)**: ~6 story points
- S-ACT: Add `activeSessions` to PlanningCommandCenterItem + active-session chip row on CommandCenterFeatureCard (pattern: MultiProjectWorkItemCard lines 97–123) — **3 pts**
- S1: Add `git_branch`/`git_commit_hash` to PlanningAgentSessionCardDTO + chip on session card — **2 pts**
- S5: Add `refetchInterval: 15_000` to usePlanningCommandCenterQuery callers — **1 pt**
- S6: Add `refetchInterval: 15_000` to usePlanningSessionBoardQuery callers — **0 pts** (1-line change, bundled with S5)

**Display-first path (Phase 1 conditional — gated on gitBranch coverage audit)**: +3 pts
- S3: Surface commitRefs/prRefs with click-dialog on CommandCenterFeatureCard — **3 pts**
  - Proceeds to Phase 1 only if coverage audit shows sufficient non-NULL gitBranch sessions.
  - If audit fails threshold, S3 moves to Phase 2 scope.

**Display-first path (Phase 1 unconditional high-value addition)**: +3 pts
- S4: Per-phase session links in CommandCenterDetailPanel — **3 pts**
  - Requires: optional `phase_number` filter in SqliteFeatureSessionRepository + `linked_sessions_by_phase` in get_feature_planning_context + phase-session section in CommandCenterDetailPanel.
  - Has NO multi-branch scanning dependency. Inverse query (phase → sessions) uses existing entity_links table and phase_hints on sessions.
  - Misclassified as Phase 2 in original synthesis: corrected to Phase 1.

**Phase 1 total (with S3 and S4)**: ~9 story points
**Phase 1 total (without S3, if coverage audit fails)**: ~6 story points

**Full scope (Phase 1 + Phase 2 — gated on R-01 spike and coverage audit)**: ~15 story points
- Adds S2: Branch-signal correlation step in session correlation pipeline — **3 pts**
- Adds S3 (if deferred from Phase 1): commitRefs/prRefs click-dialog — **3 pts**

**Comparable past feature (H5 anchor)**: PlanningAgentSessionBoard (planning session board) — estimated at ~8 pts, already shipped. The Phase 1 core at 6–9 pts is in the same range; full scope at 15 pts is approximately 2x, consistent with the added correlation engine and detail-pane work.

**Major cost drivers**:
- Active-session chips (3 pts): requires new `activeSessions` field on PlanningCommandCenterItem DTO, backend query to join live sessions to command-center items, and frontend chip component
- Per-phase session links (3 pts): requires new inverse query method (feature phase → sessions by phase_hints), PhaseContextItem field addition, and CommandCenterDetailPanel section
- Branch-signal correlation pipeline step (3 pts, Phase 2 or deferred S3): extracting feature slug tokens from git_branch strings, managing false-positive rate on generic branch names
- ADR-007 compliance cost: every new write path in repositories requires retry_on_locked usage and a direct-count assertion test (applies to branch linkage join table if added)

---

## 4. Value Statement

**Primary beneficiaries**: Operators running multi-worktree or multi-branch development workflows who use the CCDash planning command center to track feature progress.

**Evidence of demand**:
- Operator report (charter hypothesis): planning items cannot be traced to the sessions or commits that produced them. This is the founding signal for the exploration.
- Structural gap confirmed by tech leg: CommandCenterFeatureCard shows `branch TBD` and `commit TBD` as default fallback strings — the UI already acknowledges the gap; the problem is data flow, not absent affordance.
- ProjectBoard already implements full branch+session+commit linkage with 7 tabs (sessions, history, commit aggregation); the gap is that this richness does not propagate to the planning surfaces operators use day-to-day.
- PlanningAgentSessionBoard session cards carry no gitBranch field; operators must infer branch from feature slug — confirmed by ux-value leg.
- PhasePlanTable has no per-phase session link column — confirmed by ux-value leg.
- Active-session chip (the highest-priority UX affordance, confidence 0.90) is entirely absent from CommandCenterFeatureCard; the `lastActivity.timestamp` label is the only session signal — confirmed by ux-value leg.

**Counterfactual**: If this is not built, operators investigating "which session produced this planning item on branch X?" must manually cross-reference the ProjectBoard modal (already rich) against the planning command center (data-sparse). Active-session visibility requires leaving the planning surface. Per-phase session investigation requires manually searching the session board filtered by feature — a four-surface workflow for what could be a one-click action.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Phase 1 Impact | Mitigation |
|------|----------|---------|----------------|------------|
| R-01: Multi-branch doc scanning — FileWatcher has no multi-branch path binding; watching non-active-checkout markdown docs requires new BranchWatcherRegistry abstraction or breaks ADR-006 registry semantics | technical | H | None — Phase 1 does not touch doc watcher | Gate Phase 2 on a dedicated spike for watcher multi-branch binding design. Phase 1 is unaffected — session JSONL files are not branch-partitioned on disk. |
| R-02: gitBranch coverage gap — Codex sessions always have gitBranch=NULL (hardcoded in parser.py line 1244); older Claude Code versions may not emit the field; actual null fraction in operator data is unknown; coverage confidence is 0.50 | technical | M | S1 chip may be empty for majority of sessions; S3 click-dialog may be vacuous | All branch-display UI must be null-safe. A gitBranch coverage audit against live data is required as a Phase 1 prerequisite for S3 commitment. S1 proceeds with null-safe UI unconditionally. |
| R-03: Branch-signal correlation false positives — matching git_branch string against feature slug tokens may yield false positives on short/generic branch names (main, dev, fix) | technical | M | None — S2 (correlation) is Phase 2 | Implement minimum branch-name length threshold and an exclusion list of common non-feature branch patterns. Specification of threshold/exclusion list is a named open item (see §9). |
| R-04: uvicorn --reload drops all in-process watcher registrations on every file save — multi-branch watchers would compound this in the standard dev environment | operational | M (dev only) | None | Document as dev-env hazard. Phase 1 is unaffected. Phase 2 watcher spike must design for reload resilience. |
| R-05: Query-cache staleness — @memoized_query 600s backend TTL; cache keys that don't incorporate branch context will serve stale responses up to 600s after a branch switch | technical | L | Low — 30s frontend staleTime resolves most cases | New branch-keyed fields should be included in cache key fingerprint or planning queries should set lower TTL. |
| R-06: ADR-007 compliance cost on new write paths — every new repository write must use retry_on_locked and ship a direct-count assertion test | technical | M | Low — Phase 1 write paths are additive index only | Enforce at code-review gate. New join tables (Phase 2) trigger ADR-007; index-only additions (Phase 1) do not. |
| R-07: SSE live update delivery is in-process only — cross-process coordination (worker + API in separate processes) requires Postgres NOTIFY fanout; SQLite deployments where worker and API are separate processes will miss session-sync events | operational | L | Affects live-session chip freshness in non-standard deployments | Pre-existing constraint, not new to this feature. The Phase 1 PRD must document the supported deployment topology (standard dev setup: worker and API share process; SQLite multi-process deployments are not guaranteed live). Phase 2 (Postgres deployment guidance) is deferred. |
| R-08: WorktreeGitStateProbe subprocess cost at scale — 5s TTL cache, 0.8s per-call timeout; N active worktrees per page load at 15s refetch may accumulate CPU/subprocess cost | operational | M | Present if operators have multiple worktrees | Probe is already implemented and capped. Monitor subprocess count against registered worktrees. Enforce worktree registration limit if needed. |
| R-09: workingDirectories/cwd is NOT a direct DB column — cwd data is stored in session_forensics_json JSON blob (parser.py lines 2227–2229, 4065); it is not filterable/indexable without a migration | technical | M | Phase 1 stories must not use cwd-based inference | If any Phase 1 story is later revised to use cwd for worktree or branch inference, a schema migration is required. This is a migration gate: Phase 1 PRD must explicitly exclude cwd-based inference from acceptance criteria, or include a migration task if cwd filtering is needed. |
| R-10: planning_worktree_contexts is operator-gated — table is populated only via explicit planning control plane launch-flow registration; operators who do not use the control plane will have no worktree branch context, and the branch row on CommandCenterFeatureCard will always show "branch TBD" | operational | M | Present for all operators not using the launch flow | The Phase 1 PRD must include an acceptance criterion for the empty-state UX when planning_worktree_contexts is empty: render "No worktree registered" (not "branch TBD") with a prompt to register via the launch flow. The null-safe UI requirement must distinguish this state from sessions with present-but-null branch data. |

---

## 6. Architectural Implications

This feature fits cleanly into the existing layered architecture with additive changes only. No structural rewrites are required for Phase 1.

**Agent queries layer** (`backend/application/services/agent_queries/`): PlanningCommandCenterQueryService and PlanningSessionQueryService need new DTO fields:
- `activeSessions: list[AggregateWorkItemSession]` on `PlanningCommandCenterItemDTO` (new field, mirrors multi-project AggregateWorkItem pattern)
- `git_branch: str | None` and `git_commit_hash: str | None` on `PlanningAgentSessionCardDTO`
- `commit_refs: list[str]` and `pr_refs: list[str]` on `FeatureSummaryItem` (conditional on S3 proceeding)
- `linked_sessions_by_phase: dict[int, list[SessionLink]]` on `PhaseContextItem` (for S4 per-phase links)

This is the canonical extension point per the transport-neutral pattern in CLAUDE.md.

**Repository layer** (`backend/db/repositories/`): An index on `sessions(git_branch, project_id)` is additive and does not introduce a new write path (no ADR-007 cost). A new optional `phase_number` filter on `SqliteFeatureSessionRepository` is a read-only query extension (no ADR-007 cost). A new `session_branch_links` join table is an option for Phase 2 only and does require ADR-007 compliance.

**cwd/workingDirectories constraint**: The `workingDirectories` (cwd) field is NOT a direct DB column — it is serialized into `session_forensics_json` and stored as a JSON blob in the `sessions` table. Any Phase 1 story that requires filtering or indexing by working directory would require a schema migration (new direct column or extracted index). The Phase 1 scope must not assume cwd is filterable without migration.

**Frontend hooks** (`services/queries/`): `usePlanningCommandCenterQuery` and `usePlanningSessionBoardQuery` each need a single `refetchInterval` argument added at their call sites. Hook infrastructure is already in place.

**Schema migrations** (`backend/db/sqlite_migrations.py`): All Phase 1 migrations are additive (index additions). Migration runner already acquires 30s busy_timeout and uses IF NOT EXISTS guards — no new migration patterns required.

**SSE live-update topology constraint**: The existing SSE broker/bus is in-memory per process. Under the standard dev setup (`npm run dev`), worker and API share a single process and live updates reach the frontend. Under SQLite deployments where the worker and API run as separate processes, session-sync events from the worker do not reach the API's in-memory bus unless Postgres NOTIFY fanout is enabled. This is a pre-existing constraint (R-07 above). The Phase 1 PRD must document the supported deployment topology and must not promise live-update delivery for multi-process SQLite deployments.

**Multi-branch doc watching** (Phase 2 only): The FileWatcher architecture is fundamentally single-project, single-path-bundle per project_id. Supporting non-active-checkout document paths requires either a new `BranchWatcherRegistry` abstraction or explicit worktree path registration from operators. This is a named spike prerequisite — no Phase 2 implementation should begin without the spike completing first. A `TODO(PCP-Phase5)` comment in `backend/application/live_updates/topics.py` line 137 already marks this future worktree_planning_topic work.

**Consolidation debt**: CommandCenterDetailPanel (~5 sections, no sessions/history tabs) is substantially less rich than the ProjectBoard modal (7 tabs, commit aggregation, branch-aware session grouping). The correct long-term direction is consolidation, but it is deferred. Immediate recommendation: augment the side pane with the new phase-session links and add an "Open full detail" button routing to `planningRouteFeatureModalHref()`, which already exists in `services/planningRoutes.ts`. MultiProjectDetailRail already acknowledges this debt with a `Future: full modal replacement` comment.

---

## 7. Verdict

**Verdict**: conditional
**Confidence**: 0.85

**Rationale**: All three charter verdict criteria for a `go` verdict are met for Phase 1 (display-from-existing-data): both tech and risk legs report confidence at or above 0.85, the deal-killer condition is not triggered (gitBranch is a fully persisted DB column, commitRefs/prRefs are in document_refs, and no per-branch git checkout scanning is required for Phase 1), and a bounded phased path exists. The `conditional` verdict rather than `go` is warranted for three reasons:

1. **Phase 2 prerequisite spike**: Phase 2 (multi-branch document scanning and watcher multi-branch binding) partially triggers the charter's deal-killer condition — markdown docs are working-tree-bound, and watching non-active-branch docs requires architectural work not yet spiked. Phase 2 must not be committed until a dedicated watcher multi-branch binding spike (R-01) completes.

2. **gitBranch coverage unknown**: Actual gitBranch coverage in operator session data is unknown (confidence 0.50 per risk leg). Codex sessions hardcode gitBranch=NULL. If most sessions have NULL gitBranch, S3 (branch/commit click-dialog) delivers no visible operator value despite 3 points of implementation cost. A minimum-threshold coverage audit against live data must gate S3's Phase 1 commitment. S1 (branch chip) proceeds unconditionally with null-safe UI.

3. **Undisclosed constraints for PRD author**: Several constraints discovered during the investigation are not visible to the PRD author without explicit documentation: (a) cwd/workingDirectories is in a JSON blob, not a direct column (R-09); (b) planning_worktree_contexts is operator-gated, not auto-discovered (R-10); (c) SSE live-update is in-process only under SQLite (R-07); (d) Codex sessions structurally cannot carry gitBranch, requiring a distinct null display state.

**S4 phase reclassification**: Per-phase session links in CommandCenterDetailPanel (S4) are reclassified from Phase 2 to Phase 1. S4 requires only an inverse repository query (phase → sessions by phase_hints on existing entity_links) and a UI section in CommandCenterDetailPanel — it has no multi-branch scanning dependency. Grouping S4 with S2 (branch-signal correlation, which does depend on Phase 2 infrastructure) would unnecessarily delay high-value, low-risk work.

**Recommended next action**: Proceed to `/plan:plan-feature --tier=2` scoped to Phase 1 as described in §3. Phase 2 (multi-branch doc scanning, ~6 additional points) is deferred pending R-01 spike and gitBranch coverage audit. The Phase 1 PRD must reference this feasibility brief in `related_documents` and explicitly list Phase 2 as a deferred item requiring its own spike before scheduling.

---

## 8. Phase 1 Story Scope (Corrected)

The following table is the authoritative Phase 1 story list, reconciling all three legs. Stories are ordered by priority.

| Story | Description | Points | Conditional? | Notes |
|-------|-------------|--------|-------------|-------|
| S-ACT | Active-session chips on CommandCenterFeatureCard | 3 | No | Top-priority UX affordance (confidence 0.90). Template: MultiProjectWorkItemCard lines 97–123. Backend: new `activeSessions` field on PlanningCommandCenterItemDTO. |
| S1 | git_branch chip on PlanningAgentSessionCardDTO + session card UI | 2 | No | Null-safe required; see Codex null state below. |
| S4 | Per-phase session links in CommandCenterDetailPanel | 3 | No | No multi-branch dependency. Inverse phase→sessions query on existing entity_links. Reclassified from Phase 2. |
| S5/S6 | refetchInterval on both planning board hooks | 1 | No | 1-line change per hook call site. |
| S3 | commitRefs/prRefs click-dialog on CommandCenterFeatureCard | 3 | Yes — gated on gitBranch coverage audit | Proceeds to Phase 1 only if audit confirms sufficient non-NULL coverage. If not, deferred to Phase 2. |

**Phase 1 total**: 6 pts (without S3) to 9 pts (with S3).

---

## 9. Open Questions (Revised)

1. **gitBranch coverage audit (gates S3)**: What percentage of sessions in the operator's live dataset have a non-NULL gitBranch? The risk leg places coverage confidence at 0.50; Codex sessions hardcode NULL. A minimum-threshold check against live data must gate S3 commitment. Proposed gate: if fewer than 30% of sessions linked to active features have non-NULL gitBranch, S3 is deferred to Phase 2. The PRD author must run or commission this audit before locking Phase 1 scope. **Owner: PRD author. Required before Phase 1 PRD approval.**

2. **Branch-name exclusion list and minimum-length threshold**: What branch names should be excluded from the correlation signal (e.g., main, dev, fix, release)? What minimum length prevents false positives? This affects S2 (correlation pipeline) and any display of raw git_branch values in S1 and S3. **Owner: unassigned. Must be assigned and specified before S2 implementation. Does not block Phase 1 unconditional stories (S-ACT, S1, S4, S5/S6) but does block S2 in Phase 2.**

3. **Codex-session null-branch display state**: Codex sessions hardcode gitBranch=NULL (parser.py line 1244). The UI must distinguish two null-branch states: (a) "no branch data available" (Claude Code session where gitBranch was not emitted by that Claude Code version), and (b) "Codex session — branch structurally absent" (where branch is categorically unavailable). Ambiguous null rendering produces misleading acceptance criteria. **Owner: PRD author. Must be specified as distinct AC states in Phase 1 PRD.**

4. **planning_worktree_contexts empty-state UX**: Operators who do not use the planning control plane launch flow will have no entries in planning_worktree_contexts, causing every branch row to show "branch TBD." The empty-state must distinguish "no worktree registered" (operator action required) from "worktree registered but branch not resolved." **Owner: PRD author. Must be specified as an AC in Phase 1 PRD.**

5. **SSE live-update supported topology**: The Phase 1 PRD must specify which deployment configurations support live-update delivery (standard dev: worker + API in single process = live updates work; SQLite multi-process: live updates may be missed). This is not a new engineering requirement — it is a documentation requirement. **Owner: PRD author. Must appear in Phase 1 PRD non-functional requirements or constraints section.**

6. **Phase 2 prerequisite: BranchWatcherRegistry design**: What is the correct design for multi-branch doc watching — explicit operator-registered worktree paths vs. auto-discovery — and does either approach satisfy ADR-006 registry semantics without composite project IDs? **Owner: dedicated spike (R-01). Blocks Phase 2 only.**

7. **Cache key strategy for branch-aware queries**: Should branch-aware planning queries bypass the 600s @memoized_query cache or incorporate branch as a key dimension? **Owner: Phase 2 architecture decision. Does not block Phase 1.**

8. **Branch-to-feature linkage model**: Should branch-to-feature linkage be modeled as (a) an index on sessions(git_branch, project_id) [no new write path], (b) a new session_branch_links join table [requires ADR-007 compliance], or (c) a branch column on features? Phase 1 uses option (a); Phase 2 must make an explicit choice. **Owner: Phase 2 architecture decision.**

9. **Consolidation trigger threshold**: At what feature size or maintenance cost does the two-surface maintenance burden (CommandCenterDetailPanel + ProjectBoard modal) justify a full migration? **Owner: future planning cycle. Deferred.**

---

## 10. Phase 1 Acceptance Criteria Constraints (For PRD Author)

The following constraints must appear as explicit ACs in the Phase 1 PRD. They are undisclosed to the PRD author without this synthesis.

**AC-NULLBRANCH-1 (Codex null state)**: When a session has gitBranch=NULL because the session was produced by the Codex platform, the branch chip must display "Codex — no branch" (or equivalent) rather than the generic null indicator. The rendering must be determinable from the session's platform/source field, not solely from the null gitBranch value. This distinguishes the "structurally absent" Codex case from the "data not yet available" Claude Code case.

**AC-NULLBRANCH-2 (Claude Code null state)**: When a session has gitBranch=NULL because the Claude Code version did not emit the field, the branch chip must display a generic "branch unknown" indicator. Do not block session display; render the null state gracefully.

**AC-WORKTREE-EMPTY**: When planning_worktree_contexts contains no entries for the current feature (operator has not used the launch control plane), the CommandCenterFeatureCard branch row must display "No worktree registered" (not "branch TBD") with a visible affordance prompting the operator to register a worktree via the planning launch flow. This state must be explicitly tested.

**AC-SSE-TOPOLOGY**: Non-functional requirement. The Phase 1 PRD must document: "Live session chip updates are delivered within one 15s refetchInterval cycle under the standard CCDash development topology (worker and API in the same process). Under SQLite deployments where worker and API run as separate processes, live-update delivery from the worker is not guaranteed. Postgres deployments receive live updates across processes via NOTIFY fanout."

**AC-CWD-EXCLUSION**: No Phase 1 story may use `session_forensics_json` workingDirectories/cwd data for branch inference, worktree matching, or any filterable query without a corresponding schema migration task in the same phase. If cwd-based inference is needed, a migration must be added to extract cwd as a direct column.

---

## 11. Citations

- Exploration charter: `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md`
- Tech leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md`
- Risk leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md`
- UX value leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md`
- ADR-006 (DB-authoritative project registry): `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- ADR-007 (DB write failure surfacing standard): `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- Planning reskin feature guide (modal-first navigation): `.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md`
- Feature surface architecture (cache tiers, polling): `docs/guides/feature-surface-architecture.md`

---

## Addendum: gitBranch Coverage Audit (2026-06-04, post-verdict)

Run against the live operator DB (`data/ccdash_cache.db`) per the conditional verdict's S3 gate:

| Population | Sessions | Non-null `git_branch` | Coverage |
|---|---|---|---|
| All sessions | 9,967 | 9,167 | 92.0% |
| Last 60 days | 4,369 | 3,930 | 90.0% |
| Feature-linked sessions (S3 gate population) | 1,896 | 1,878 | **99.1%** |
| Codex sessions | 788 | 0 | 0.0% |

**Gate outcome**: PASS (99.1% >> 30% threshold). **S3 is included in Phase 1 unconditionally.**
Branch diversity confirmed (main: 1,278; development: 475; plus 6+ feature/refactor branches with 140-210 sessions each), so the click-dialog displays meaningful provenance.
Codex 0% coverage confirms the structural-null display state is a real requirement (788 affected sessions), not a theoretical edge case.
