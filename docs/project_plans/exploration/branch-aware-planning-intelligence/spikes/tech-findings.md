---
schema_version: 2
doc_type: spike_findings
title: "Branch-Aware Planning Intelligence — Tech Leg Findings"
status: complete
created: 2026-06-04
updated: 2026-06-04
feature_slug: branch-aware-planning-intelligence
leg: tech
confidence: 0.85
partial: false
---

# Tech Findings: Branch-Aware Planning Intelligence

## Verdict Summary

**NOT a deal-killer.** Branch and commit identifiers are already present in parsed session data (`gitBranch`, `gitCommitHash`) and are persisted to the DB `sessions` table. Feature `commitRefs`/`prRefs` are parsed from frontmatter and stored in the `features.data_json` blob. A `planning_worktree_contexts` table and `WorktreeGitStateProbe` service already exist and are live in the Planning Command Center. The data substrate for branch-aware display is real.

The gap is **surface exposure** on planning board items and the session board cards: the existing data is not wired into the planning session board or the per-phase pane. Deriving session→branch linkage does not require per-branch git checkout scanning.

---

## Claim-by-Claim Verification

### Claim 1: "CCDash only tracks the currently checked-out branch per project."

**Verdict: Partially true, with nuance.**

- The `FileWatcher` and `FileWatcherRegistry` bind to a single set of filesystem paths per `project_id` (sessions_dir, docs_dir, progress_dir, worknotes_dir). These paths are configured at runtime startup per registered project. There is no multi-branch directory scanning — the watcher watches the configured paths only.
- However, the Claude Code session parser (`backend/parsers/platforms/claude_code/parser.py:2419`) reads `gitBranch` from every JSONL entry and stores it per session. Sessions from any worktree whose `.jsonl` files land under the watched `sessions_dir` will have their `gitBranch` field captured.
- The `planning_worktree_contexts` DB table (`backend/db/repositories/worktree_contexts.py`) stores `branch`, `worktree_path`, and `base_branch` per planning launch, and `WorktreeGitStateProbe` actively probes those paths at query time (TTL 5 s). The Planning Command Center (`CommandCenterFeatureCard.tsx`) already shows `item.worktree?.branch` and `item.gitState?.head`.
- **Confidence: 0.85.** The watcher is single-path; worktree branches are tracked via a separate launch-context table, not by scanning git refs.

### Claim 2: "Planning command-center board items do not update live."

**Verdict: True for the Planning Command Center page; planning session board has no live refetch either.**

- `usePlanningCommandCenterQuery` has `staleTime: 30_000` and accepts an optional `refetchInterval` parameter, but no component passes a `refetchInterval` to it. There is no background polling on the command center board.
- `usePlanningSessionBoardQuery` / `usePlanningFeatureSessionBoardQuery` also use `staleTime: 30_000`, no `refetchInterval` is passed in practice.
- The Planning Summary hook (`usePlanningSummaryQuery`) uses TanStack Query with `staleTime: 30_000`. The `dataFreshness` token in query keys means a fresh fetch fires only when the backend freshness signal changes — but that requires the frontend to first receive a stale response with the new token.
- Comparison: `FeatureExecutionWorkbench` polls at 900 ms; `ProjectBoard` feature modal polls at 15 s. The planning surfaces have 0 live refetch interval.
- **Confidence: 0.9.** The API supports `refetchInterval` opt-in but no consumer passes it to planning surfaces.

### Claim 3: "branch/commit fields on planning items are never populated."

**Verdict: Mixed — data exists in the pipeline but is not surfaced on planning board cards or the session board.**

What IS populated:
- `sessions.git_branch` and `sessions.git_commit_hash` are DB columns populated from parsed session JSONL (`claude_code/parser.py:4338`).
- `Feature.commitRefs` and `Feature.prRefs` are model fields populated from frontmatter `commit_refs`/`pr_refs` keys (`parsers/features.py:1642-1644`) and stored in `features.data_json`, then reconstituted in `feature_from_row` in `feature_execution.py:383-384`.
- `planning_worktree_contexts.branch` is a DB column populated on launch and surfaced via `PlanningCommandCenterItemDTO.worktree.branch` (already displayed in `CommandCenterFeatureCard.tsx:168`).

What is NOT surfaced:
- `sessions.git_branch` is selected in `feature_sessions.py` (`_SESSION_COLS` list: line 72-73) but is not passed through to `PlanningAgentSessionCardDTO` — the card DTO has no `git_branch` or `git_commit_hash` field.
- `Feature.commitRefs` / `Feature.prRefs` are in the `Feature` model but are not included in the planning query service summary items (`FeatureSummaryItem` model in `agent_queries/models.py` has no `commitRefs`).
- The planning session board correlation pipeline (`session_correlation.py`) uses `task_id`, `phase_hints`, `command_tokens`, and lineage — no branch/commit correlation signal.
- **Confidence: 0.9.** The data exists at the DB and model layer; it is absent from the transport DTOs and card components for planning surfaces.

### Claim 4: "There is no way to link sessions to planning items (per-phase links, chips, transcript links)."

**Verdict: False — session→feature linkage exists but is incomplete.**

- `entity_links` table stores `session→feature` links with `link_type='related'`. The `PlanningSessionQueryService` (`planning_sessions.py`) loads these links and uses them for "explicit_link" correlation (highest confidence). The session board card `PlanningAgentSessionCardDTO` already has `transcript_href` (`#/sessions/{session_id}`), `planning_href` (`#/planning/{feature_id}`), and `phase_href` (`#/planning/{feature_id}/phases/{phase_number}`).
- `SqliteFeatureSessionRepository` (`feature_sessions.py`) provides paginated session queries scoped to a feature via entity_links.
- What is missing:
  - Per-phase session links are not rendered in the Planning feature detail pane (the FeatureDetailShell / phase rows do not have a "sessions" section).
  - Active-session chips on command-center board cards are not implemented (the card shows `worktree.branch` but not running session indicators).
  - The correlation pipeline has no branch-signal: a session on `feat/my-feature` branch with no entity_link or phase_hint will be "unlinked" even though the branch name directly implies the feature.
- **Confidence: 0.85.**

### Claim 5: "The board page already shows many details, raising a consolidation question."

**Verdict: True — `ProjectBoard` and the Planning `CommandCenter` are separate and have overlapping data.**

- `ProjectBoard.tsx` is the legacy project-level session/feature board. It has commit-hash display (`gitCommitHash`, `gitCommitHashes`, `commitCorrelations`), branch display in commit sections, and a feature modal with `refetchInterval: 15_000`.
- `PlanningCommandCenter` + `CommandCenterBoardView` is the newer surface with worktree, git state, and command-center items. It has no live polling but has more planning-specific context.
- `PlanningAgentSessionBoard.tsx` is a separate Kanban surface inside the Planning page, showing session cards grouped by state/feature/phase/agent/model.
- There is no shared modal component between `ProjectBoard` and the planning command center; they each have their own card/row components.
- **Confidence: 0.95.** Consolidation is real but the planning session board card is already the richer component for session-to-feature linkage.

---

## Integration Points

### A. Add `git_branch` to `PlanningAgentSessionCardDTO`

- **File**: `backend/application/services/agent_queries/models.py` — add `git_branch: str | None = None` and `git_commit_hash: str | None = None` to `PlanningAgentSessionCardDTO`.
- **File**: `backend/application/services/agent_queries/planning_sessions.py:build_active_session_card` — read `session.get("git_branch")` and populate the new field.
- **File**: `types.ts` — extend `PlanningAgentSessionCardDTO` interface.
- **File**: Planning session board card component — render branch chip below agent/model.

### B. Add branch-signal to session correlation

- **File**: `backend/application/services/agent_queries/session_correlation.py` — add `_correlate_branch` step that matches `session.git_branch` against feature slug tokens (e.g., `feat/my-feature-slug` → slug extraction → feature lookup). Confidence: medium.
- No schema changes required. This is purely a correlation pipeline extension.

### C. Surface `commitRefs`/`prRefs` on planning board card

- **File**: `backend/application/services/agent_queries/models.py` — add `commit_refs: list[str]` and `pr_refs: list[str]` to `FeatureSummaryItem`.
- **File**: `backend/application/services/agent_queries/planning.py:_build_summary_from_data` — read from `feature.commitRefs` / `feature.prRefs`.
- **File**: `types.ts` — extend `FeatureSummaryItem`.
- **File**: planning card component — add click-to-expand provenance dialog (commit hash + PR ref chips).

### D. Per-phase session links in the details pane

- The `FeaturePhase` model has a phase number. `SqliteFeatureSessionRepository` can already query sessions by feature. Extending with a `phase_number` filter (match against `session.phase_hints`) would allow per-phase session list queries.
- **File**: `backend/db/repositories/feature_sessions.py` — add optional `phase_number` filter.
- **File**: `backend/application/services/agent_queries/planning.py:get_feature_planning_context` — include `linked_sessions_by_phase` in the `PhaseContextItem`.
- **File**: Planning feature detail shell — add session links list to phase rows.

### E. Live board updates (refetchInterval)

- **File**: `services/queries/planning.ts:usePlanningCommandCenterQuery` — already accepts `refetchInterval`. Callers just need to pass a value (e.g., 15_000 ms to match ProjectBoard).
- **File**: `components/Planning/CommandCenter/PlanningCommandCenter.tsx` — pass `refetchInterval={15_000}` to the hook.
- The backend `@memoized_query` TTL is ~600 s server-side; the client 30 s staleTime already means the backend cache will generally be hit. Live updates require adding a `refetchInterval` at the component layer — this is a 1-line change per surface.

---

## Rough Story-Point Ranges

Using H5 = Planning Session Board implementation as anchor (estimated 8 points based on board + correlation engine complexity):

| Story | Description | Est. Points |
|---|---|---|
| S1 | Add `git_branch`/`git_commit_hash` to session card DTO + UI chip | 2 |
| S2 | Branch-signal in session correlation pipeline | 3 |
| S3 | `commitRefs`/`prRefs` on planning summary item + click-dialog | 3 |
| S4 | Per-phase session links in feature detail pane | 5 |
| S5 | Live refetchInterval for command center board (15 s) | 1 |
| S6 | Live refetchInterval for planning session board | 1 |
| Total (display-first path) | S1 + S3 + S5 + S6 | **7** |
| Total (full scope) | All six stories | **15** |

H5 anchor: Planning session board (already shipped) = ~8 points. The display-first path (S1+S3+S5+S6) is roughly 1 sprint. The full scope including per-phase session links and branch correlation is ~2 sprints.

---

## Key Files and Locations

| Concern | File | Notes |
|---|---|---|
| Session branch parsing | `backend/parsers/platforms/claude_code/parser.py:2419`, `:4338` | `gitBranch` extracted from each JSONL entry |
| Session DB schema | `backend/db/repositories/sessions.py:38,71,127` | `git_branch` column persisted |
| Feature commitRefs parsing | `backend/parsers/features.py:1642-1696` | From frontmatter `commit_refs`/`prRefs` |
| Feature model | `backend/models.py:2089-2090` | `commitRefs`, `prRefs` fields |
| Session card DTO | `backend/application/services/agent_queries/models.py` | No `git_branch` field currently |
| Session→feature linkage | `backend/db/repositories/entity_graph.py` | `entity_links` table, `source_type='session'` |
| Correlation pipeline | `backend/application/services/agent_queries/session_correlation.py` | No branch-signal step |
| feature_sessions repo | `backend/db/repositories/feature_sessions.py:72-73` | `git_branch` selected but not returned to planning service |
| Worktree contexts | `backend/db/repositories/worktree_contexts.py:68-83` | `branch`, `worktree_path`, `base_branch` columns |
| Git state probe | `backend/application/services/worktree_git_state.py` | Already live; probes HEAD, dirty, upstream, ahead/behind |
| Planning command center (board) | `components/Planning/CommandCenter/CommandCenterFeatureCard.tsx:164-188` | Already displays `worktree.branch` and `gitState.head` |
| Planning session board | `components/Planning/PlanningAgentSessionBoard.tsx` | No git_branch field on cards |
| Planning session query | `services/queries/planning.ts:150-177` | `staleTime: 30_000`, no `refetchInterval` |
| Command center query | `services/queries/planning.ts:361-403` | Accepts `refetchInterval` but no caller passes it |
| File watcher | `backend/db/file_watcher.py:79-139` | Single-path per project, no multi-branch |

---

## Open Questions for Risk Leg

1. **Branch-signal correlation FP rate**: Matching `git_branch` against feature slug tokens may produce false positives on short slugs or generic branch names (e.g., `main`, `dev`). The risk leg should define a minimum branch-name length and exclusion list.
2. **Multi-branch session scanning**: If operators run sessions from multiple worktrees of the same project, do all worktree `sessions_dir` paths need to be registered? Currently only one `sessions_dir` is watched per project. The risk leg should assess whether the watcher registry needs to support multiple sessions directories for the same `project_id`.
3. **Query cache invalidation for live git state**: `WorktreeGitStateProbe` has a 5 s TTL. The planning command center query has a 30 s staleTime. If the frontend polls at 15 s, the git state will update twice per `staleTime` cycle. Risk leg should evaluate CPU/subprocess cost of probing N worktrees per page load.

---

## Deal-Killer Assessment

The deal-killer condition ("no reliable branch/commit identifiers derivable without per-branch checkout scanning") is **NOT triggered**.

- `gitBranch` is captured in session JSONL and persisted to the `sessions.git_branch` DB column for every Claude Code session.
- `commitRefs`/`prRefs` from frontmatter are parsed into `features.data_json`.
- `planning_worktree_contexts.branch` is an explicit DB column populated at launch time.

None of these require invasive per-branch git checkout scanning. The branch-signal correlation step (`_correlate_branch`) would read from an already-indexed DB column. Phase 1 (display-from-existing-data) is fully feasible without new file scanning.
