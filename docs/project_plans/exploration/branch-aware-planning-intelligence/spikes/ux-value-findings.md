---
schema_version: 2
doc_type: spike_findings
title: "Branch-Aware Planning Intelligence — UX Value & Shape Findings"
status: complete
confidence: 0.82
partial: false
feature_slug: branch-aware-planning-intelligence
leg: ux-value
created: 2026-06-04
updated: 2026-06-04
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
---

# Branch-Aware Planning Intelligence — UX Value & Shape Findings

## Deal-Killer Assessment

**Not triggered** for UX-value scope. The surface already carries structural affordances
for branch/commit/session data (branch chip in `CommandCenterDetailPanel`, `WorktreeGitStatePanel`,
`gitBranch` and `commitHashes` on `FeatureSessionLink`, `PlanningCommandCenterWorktree.branch`).
The UX scaffolding is ready. Whether the *data* populates reliably is a question for the
tech and risk legs, not this leg.

---

## 1. Counterfactual: How Does an Operator Answer "What Is Happening on Branch X?" Today

### 1a. Planning Command Center Board

The primary planning surface is `PlanningCommandCenter` → `CommandCenterFeatureCard` /
`CommandCenterDetailPanel`.

**What it already shows:**
- Feature cards show a branch row (`item.worktree?.branch` or "branch TBD") with a copy-to-clipboard
  button, and a commit SHA chip (`item.gitState?.head` or "commit TBD").
  Source: `components/Planning/CommandCenter/CommandCenterFeatureCard.tsx` lines 164–206.
- The "details" side-panel (`CommandCenterDetailPanel`) shows a dedicated "worktree and git state"
  section that renders `WorktreeGitStatePanel` — displaying branch name, worktree path, dirty count,
  HEAD SHA, ahead/behind counts, and warnings.
  Source: `components/Planning/CommandCenter/CommandCenterDetailPanel.tsx` lines 85–88.
- `WorktreeGitStatePanel` also shows `gitState.upstream` as a fallback when no worktree is linked.
  Source: `components/Planning/CommandCenter/WorktreeGitStatePanel.tsx`.

**What is missing / degraded:**
- If `item.worktree` is null (feature has no associated worktree context), every branch and commit
  field falls back to "branch TBD" / "commit TBD". There is no affordance to answer "which
  sessions ran on this feature's branch?" when no worktree is explicitly linked — the card shows
  the worktree's branch, not the branches of participating sessions.
- There is no "branch → sessions" reverse index: the operator cannot click a branch name to see
  all sessions that touched that branch. They get the branch per worktree context, not per session.
- No active-session chip on the card body — `CommandCenterFeatureCard` has no live-session
  indicator. The only session signal is `lastActivity.timestamp` (last-activity label, Issue 4).
  There is no per-feature "N agents running" chip.
- The phase plan table in the detail panel (`PhasePlanTable`) shows phases/status/agents/model but
  has no session links per phase.

**Finding (high confidence 0.85):** The planning command-center board already has the *structural*
UX containers for branch and commit display. The operator pain is that these show "TBD" when the
worktree mapping is missing — not that the affordance is absent. This is a data-population problem,
not a UX-shape problem for the card and detail panel.

---

### 1b. PlanningAgentSessionBoard

The session board (`PlanningAgentSessionBoard.tsx`) is the existing surface for live-session
visibility. It is Kanban-style with columns grouped by state/feature/phase/agent/model.

**What it already shows per session card:**
- Session ID, agent name, model chip
- Feature badge (correlation featureId/featureName) — branch-to-feature association by proxy
- Phase hint and task hint
- Token summary and context-window bar
- Correlation confidence tier (high/medium/low/unknown) with evidence tooltip
- State dot with animation for active sessions
- Relationship badge (parent/root/sibling/child)
- Transcript link, feature plan link, phase-ops link in `CardActionRow`

**What is missing:**
- No branch field on session cards. A session running on `fix/auth-worktree` is not labeled with
  that branch — the operator cannot filter or scan by branch name.
- The `PlanningAgentSessionDetailPanel` (inline side panel) shows lineage, feature correlation,
  evidence, token context, and activity timeline — but no branch or commit information. The session
  card data type (`PlanningAgentSessionCard` in `types.ts`) does not appear to carry a `gitBranch`
  or `commitHash` field.
- Feature-grouped columns have a header link to `planningRouteFeatureModalHref`, but no branch
  label on the column header.

**Finding (medium confidence 0.70):** The session board is the nearest analog for "what's happening
on branch X" but does not surface branch/commit provenance. An operator must infer branch from the
feature slug visible on the card, then mentally map feature→branch. This is a genuine gap.

---

### 1c. ProjectBoard Feature Modal — Sessions and History Tabs

The `ProjectBoard.tsx` feature modal is the richest existing branch+session+commit surface:

- `FeatureSessionLink` (the session data contract) carries `gitBranch?: string` and
  `commitHashes: string[]` fields.
- The board-level commit aggregation logic (`addCommitRow`) cross-links sessions to commits and
  extracts `gitBranch` from each session into a `branches: Set<string>` per commit accumulator.
  Source: `ProjectBoard.tsx` lines 1849–1854.
- A `GitCommitAggregate` entity carries `branches: string[]` and `sessionIds: string[]`, enabling
  "which sessions touched this commit" and "which branch was this commit on."
- The modal has a history tab and a sessions tab. Sessions tab (`SessionsTab.tsx`) shows per-session
  cards with `gitBranch`, `commitHashes`, PR links, etc.

**Finding (high confidence 0.88):** The ProjectBoard feature modal is the prior art for branch-aware
session display. It already links sessions → commits → branches within a feature detail view. The
planning page does NOT reuse this modal for its feature cards — it has its own side pane
(`CommandCenterDetailPanel`) which is far less rich. This is the core of the consolidation question.

---

## 2. Evaluation of Proposed Affordances

### 2a. Branch/Commit Fields on Cards with a Click-Dialog

**Evaluation:** Moderate UX value; infrastructure partially exists.

- The `CommandCenterFeatureCard` already shows a branch row. The gap is the click-dialog showing
  all linked branches/commits and how each was linked (worktree mapping vs. session gitBranch
  vs. commit correlation). This is a net-new sub-surface.
- Risk: if `item.worktree.branch` is the only data source (i.e., one branch per feature context),
  a "linked branches" dialog may rarely show more than one entry, limiting value.
- If session `gitBranch` fields are populated, the dialog could show multiple branches per feature
  with session/commit provenance. This depends on tech-leg findings.
- The copy-branch-name affordance already exists (line 64–74 in `CommandCenterFeatureCard`). A
  click-to-expand-dialog would replace or augment the current static display.

**Verdict:** Incrementally valuable. Build after tech leg confirms session gitBranch data exists.

---

### 2b. Active-Session Chips on Planning Command Center Cards

**Evaluation:** High UX value; this is the most conspicuous missing signal.

The multi-project card (`MultiProjectWorkItemCard.tsx`) already has an active-session chip in the
project identity strip — a pulsing green dot with agent name and "+N" overflow.
Source: `MultiProjectWorkItemCard.tsx` lines 97–123.

The single-project `CommandCenterFeatureCard` has NO equivalent. An operator looking at the
planning board cannot immediately see "2 agents are running right now on this feature." The
`lastActivity.timestamp` label is a poor substitute — it shows elapsed time, not live status.

**Pattern to follow:** `MultiProjectWorkItemCard`'s active-session indicator is the direct template.
The same chip pattern can be added to `CommandCenterFeatureCard` using `activeSessions` data.
The session board already knows which sessions are running; the command center data could be
enriched to carry `activeSessions` inline (as `AggregateWorkItem` does in the multi-project path).

**Verdict:** High value, low implementation risk (pattern already exists in `MultiProjectWorkItemCard`).
This is the top-priority affordance.

---

### 2c. Per-Phase Session Links in the Details Pane with Transcript Links

**Evaluation:** High value for investigation workflows; moderate implementation effort.

Currently `PhasePlanTable` (shown in `CommandCenterDetailPanel`) shows phase/status/agent/model/files
but NO session links per phase. The `PlanningAgentSessionDetailPanel` (session board's inline panel)
already shows per-session transcript links and feature plan links.

A per-phase session list in the detail pane would enable: "which sessions worked on Phase 3?" →
click → transcript, eliminating a multi-step search through the session board.

The `PlanningAgentSessionCard` correlation model already records `phaseNumber` and `phaseTitle`.
The inverse query (feature phase → sessions) is not exposed in `CommandCenterDetailPanel`.

**Verdict:** High value for operators debugging multi-phase features. Add as a section to
`CommandCenterDetailPanel` ("phase sessions" section, below phase plan table). The transcript link
pattern is already established in `CardActionRow` and `PlanningAgentSessionDetailPanel`.

---

### 2d. Top-Level Branch Shown as Active Non-Worktree Branch

**Evaluation:** Moderate value; depends on data reliability.

The charter proposes showing the "active non-worktree branch" (i.e., the main checked-out branch
of the project, not individual worktree branches) as a top-level indicator. This would tell an
operator "this project is currently on `fix/auth-v2`."

The `WorktreeGitStatePanel` already surfaces `gitState.upstream` as a fallback, which approximates
this. The gap is a prominent top-level display (e.g., in `PlanningTopBar` or `PlanningMetricsStrip`)
rather than buried in the per-feature detail panel.

**Verdict:** Lower priority than session chips. The information is accessible; it's a prominence
question. Add to `PlanningTopBar` as a secondary metadata chip, not a primary feature.

---

## 3. Consolidation Trade-offs: Board Modal vs Planning Side Pane

### 3a. Current State

**ProjectBoard feature modal** (`ProjectBoard.tsx` → `FeatureDetailShell`, `OverviewTab`,
`SessionsTab`, `HistoryTab`, `PhasesTab`, `RelationsTab`):
- Full-tab detail surface with 7 tabs (overview, phases, docs, relations, sessions, history, test-status)
- Carries commit aggregation, branch-aware session grouping, PR links
- Uses `planningFeatureModalHref()` → navigates to `/board?feature=<id>&tab=<tab>`
- OR `planningRouteFeatureModalHref()` → opens at `/planning?feature=<id>&modal=feature&tab=<tab>`

**Planning-page side pane** (`CommandCenterDetailPanel`):
- Single-surface slide-over (right drawer, 760px max)
- Sections: next command, target plan, worktree/git state, phase plan, launch/review context, blockers
- Much less rich than the board modal — no sessions tab, no history tab, no commit aggregation
- Used within the planning command center; does NOT trigger full modal overhead

### 3b. Modal-First Navigation Convention

`services/planningRoutes.ts` already provides `planningRouteFeatureModalHref()` which opens the
full feature modal *within* `/planning` (URL: `/planning?feature=<id>&modal=feature&tab=overview`).
This is the established modal-first pattern from the planning reskin feature guide (§1 of
`.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md`).

The `PlanningAgentSessionBoard` already uses `planningRouteFeatureModalHref` for feature-column
header links and `CardActionRow`'s feature plan link — so the full modal is already accessible
from the session board via link. The feature modal is NOT reused as the primary detail surface
in the command center; `CommandCenterDetailPanel` is used instead.

### 3c. Cross-Project Portfolio Board Mode

`MultiProjectDetailRail` (MPCC-505) shows a lightweight drawer for session and feature detail in
the multi-project view. Its `featureId + kind:'workItem'` path renders `PhasePlanTable` directly,
not the full modal. The comment in that file notes "Future: full modal replacement once existing
modal hooks are project-scoped."

This confirms the multi-project board is already acknowledging the same consolidation debt.

### 3d. Maintenance Cost of Two Surfaces

Two distinct detail surfaces now diverge in completeness:
- Board modal: sessions tab (with branch/commit data), history tab, PR integration, 7 tabs
- Planning side pane: ~5 sections, no sessions tab, no history, no commit data

Every new branch-aware or session-aware feature must be added to BOTH if both are kept. The
commission cost of the planning-side-pane's `CommandCenterDetailPanel` is ongoing. The board
modal already carries the session/commit/branch UX that this feature aims to add.

**Verdict:** Consolidation is the correct long-term direction. However, an immediate rip-and-replace
of `CommandCenterDetailPanel` with the full modal is risky (different layouts, the side pane is
lighter-weight for quick-glance detail, and the board modal requires feature data to already be
loaded). Recommendation: augment the side pane for now (sessions section + phase-session links),
and make the side pane's "open in full detail" button navigate to `planningRouteFeatureModalHref`.

---

## 4. Recommendations

### Priority Order

1. **Active-session chips on `CommandCenterFeatureCard`** (HIGH priority)
   - Pattern: `MultiProjectWorkItemCard`'s session indicator strip (lines 97–123)
   - Data source: `PlanningCommandCenterItem.activeSessions` (field to be added; tech leg scope)
   - Implementation: add `activeSessions?: AggregateWorkItemSession[]` to `PlanningCommandCenterItem`
     and a chip row below the branch row in `CommandCenterFeatureCard`
   - UX: pulsing green dot + agent name + "+N" overflow (mirrors multi-project pattern exactly)
   - Confidence this is worth building: **0.90**

2. **Per-phase session links in `CommandCenterDetailPanel`** (HIGH priority)
   - Add a "phase sessions" section below the existing "phase plan" section
   - Render session cards with transcript links, agent name, start time, correlation confidence
   - Source pattern: `PlanningAgentSessionDetailPanel`'s quick-actions section
   - Requires: backend to return per-phase session list on the command-center item query
   - Confidence: **0.82**

3. **Branch/commit click-dialog on feature cards** (MEDIUM priority)
   - Replace static branch row with a clickable trigger opening a popover/dialog
   - Dialog content: linked branches (worktree + session gitBranch), commit SHAs, per-branch sessions
   - Blocked by tech leg: need confirmation that session `gitBranch` is populated reliably
   - Do not build until tech leg confirms provenance data quality
   - Confidence (conditional on tech leg): **0.72**

4. **Top-level active branch in `PlanningTopBar`** (LOW priority)
   - Add a branch chip to `PlanningTopBar` showing the project's active (non-worktree) branch
   - Data source: project-level git state (already surfaced in worktree context)
   - Low effort, low urgency — the information is accessible via WorktreeGitStatePanel per feature
   - Confidence: **0.65**

5. **Consolidation: board modal as primary planning detail surface** (MEDIUM priority, deferred)
   - Augment `CommandCenterDetailPanel` to add a "full detail" button → `planningRouteFeatureModalHref`
   - Over time, migrate detail sections from the side pane to the modal
   - Do NOT do a full replace in the immediate feature scope — too disruptive
   - MultiProjectDetailRail already plans this ("Future: full modal replacement")
   - Confidence full consolidation is worth it: **0.80**; timing is deferred

---

## 5. Confidence Signals and Evidence Quality

| Claim | Evidence | Confidence |
|---|---|---|
| Branch row already exists on command-center cards | Read `CommandCenterFeatureCard.tsx` lines 164–206 | 0.95 |
| Active-session chip missing from single-project cards | Read full `CommandCenterFeatureCard` — no pulsing chip | 0.95 |
| Multi-project card has session chip (template exists) | Read `MultiProjectWorkItemCard.tsx` lines 97–123 | 0.95 |
| Board modal (ProjectBoard) carries branch/session/commit data | Read `ProjectBoard.tsx` types, `FeatureSessionLink.gitBranch` | 0.90 |
| Planning side pane lacks sessions/history tabs | Read `CommandCenterDetailPanel.tsx` full structure | 0.95 |
| planningRouteFeatureModalHref used from session board | Read `PlanningAgentSessionBoard.tsx` import + `CardActionRow` | 0.95 |
| Session board has no branch field per card | Read `PlanningAgentSessionCard` usage in board — no branch field | 0.85 |
| PhasePlanTable has no session links | Read `PhasePlanTable.tsx` — only phase/status/agents/model/files | 0.95 |
| MultiProjectDetailRail acknowledges consolidation debt | Read comment "Future: full modal replacement" | 0.90 |

---

## 6. UX Shape Summary

```
CommandCenterFeatureCard (TODAY → PROPOSED)
  ├── status pill (unchanged)
  ├── title + slug (unchanged)
  ├── summary (unchanged)
  ├── phase/points/readiness chips (unchanged)
  ├── next-command box (unchanged)
  ├── branch row: click-to-copy (unchanged)     → EXTEND: click opens branch+session dialog
  ├── commit SHA chip (unchanged)               → EXTEND: part of branch dialog
  ├── last-activity label (unchanged)
  ├── artifact chips (unchanged)
  ├── [NEW] active-session chip row             ← highest priority addition
  └── action buttons (unchanged)

CommandCenterDetailPanel (TODAY → PROPOSED)
  ├── header: status + branch chip + title (unchanged)
  ├── next command section (unchanged)
  ├── target plan section (unchanged)
  ├── worktree and git state section (unchanged)
  ├── phase plan section (unchanged)
  ├── [NEW] phase sessions section              ← per-phase session cards with transcript links
  ├── launch and review section (unchanged)
  └── blockers (unchanged)
  └── [NEW] "Open full detail" button           ← navigates to planningRouteFeatureModalHref
```

The existing Board modal (reachable via `planningRouteFeatureModalHref`) already contains the
sessions and history tabs with full branch/commit/session linkage. The planning side pane needs
only the highest-value additions (session chips, phase-session links) to close the immediate gap;
full consolidation is a deferred second phase.
