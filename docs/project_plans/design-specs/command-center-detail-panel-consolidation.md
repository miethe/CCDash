---
schema_version: 2
doc_type: design_spec
title: "CommandCenterDetailPanel → Board Modal Consolidation"
status: draft
maturity: idea
created: 2026-06-04
updated: 2026-06-04
feature_slug: branch-aware-planning-intelligence
feature_version: v2
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
spike_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
adr_refs:
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
related_documents:
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
priority: low
risk_level: medium
category: frontend-ux
tags:
- command-center
- detail-panel
- board-modal
- consolidation
- multi-project
- planning
- deferred
- tech-debt
problem_statement: >
  CommandCenterDetailPanel is a lightweight side pane that surfaces phase/status/agent/model
  information for a selected feature in the Planning Command Center. The ProjectBoard feature
  modal (reached via planningRouteFeatureModalHref) is the richer, more complete surface:
  it shows sessions tab, history tab, branch/commit data, and transcript links. These two
  surfaces duplicate responsibility and diverge over time. The full consolidation — replacing
  CommandCenterDetailPanel with the board modal as the primary detail surface — is deferred
  because the modal hooks are not yet project-scoped for multi-project use. A bridge button
  ("Open full detail") was added in Phase 1 as an interim measure.
open_questions:
- "OQ-1: What is the threshold condition for triggering promotion? The plan states
  'maintenance cost threshold crossed or explicit team decision post-Phase 2.' A concrete
  metric should be defined: e.g., three or more features are added to CommandCenterDetailPanel
  that duplicate functionality already in the board modal, OR the panel requires its own
  session-display logic beyond what was built in Phase 1 T3-004."
- "OQ-2: Are the ProjectBoard feature modal hooks (usePlanningFeatureModalQuery or equivalent)
  project-scoped today? The UX leg finding notes that MultiProjectDetailRail records this
  debt explicitly: 'Future: full modal replacement once existing modal hooks are
  project-scoped.' This must be resolved before consolidation can begin."
- "OQ-3: Does consolidation require a new modal route, or does planningRouteFeatureModalHref
  (already shipping in Phase 1 T3-004) provide the correct navigation target? If the board
  modal is already reachable from the planning command center via the bridge button, is the
  consolidation about eliminating the side-pane entirely, or about enriching the modal
  with command-center-specific context (worktree state, active-session chips)?"
- "OQ-4: What happens to the CommandCenterDetailPanel keyboard and focus management
  (currently: Esc closes panel, Tab cycles through phase rows) when the panel is replaced
  by a modal? The modal must match or improve on existing accessibility affordances."
explored_alternatives:
- "Option A (Deferred — CURRENT): Keep CommandCenterDetailPanel as side pane; add bridge
  button (Phase 1 T3-004) to navigate to board modal for richer detail. Low short-term
  cost; allows independent evolution of both surfaces."
- "Option B (Full consolidation — TARGET): Replace CommandCenterDetailPanel with a
  dedicated CommandCenter modal that reuses the ProjectBoard feature modal's tab structure
  (sessions, history, branch/commit data) but adds planning-specific context (worktree
  state, active-session chips from PlanningCommandCenterItemDTO). Requires
  project-scoped modal hooks."
- "Option C (Partial merge): Add a sessions tab and branch/commit tab to
  CommandCenterDetailPanel, making it match the board modal's information density.
  Avoids the routing change but creates a second implementation of the same feature
  tabs. Not recommended — increases maintenance cost."
related_prds:
- docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
- docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
---

# CommandCenterDetailPanel → Board Modal Consolidation

**Deferred item**: DEF-002 from `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`

**Maturity**: idea — the problem is identified and the long-term direction is clear, but the trigger condition and implementation approach are not yet specified. Do not promote to PRD until OQ-1 and OQ-2 are resolved.

---

## 1. Context

The CCDash Planning Command Center has two overlapping detail surfaces for a selected feature:

1. **`CommandCenterDetailPanel`** (`components/Planning/CommandCenter/CommandCenterDetailPanel.tsx`) — a side pane that renders phase/status/agent/model rows (via `PhasePlanTable`) and, after Phase 1, per-phase session links. It is opened by clicking a feature card in the command center board.

2. **`ProjectBoard` feature modal** — reached via `planningRouteFeatureModalHref(featureId)` (added as the "Open full detail" bridge button in Phase 1 T3-004). This modal shows session history, branch/commit data, and transcript links in a richer tab-based layout.

The UX leg of the R-01 spike identified this as an active consolidation debt:
> "`MultiProjectDetailRail` already records this debt: 'Future: full modal replacement once existing modal hooks are project-scoped.'"

The Phase 1 bridge button is an interim measure. Full consolidation is the stated long-term direction.

---

## 2. Problem

**Divergence over time**: Each new planning feature risks being added to both surfaces (e.g., active-session chips added to the feature card but not the detail panel, or branch correlation shown in the panel but not the modal). This creates inconsistency for operators.

**Double maintenance**: Any UI change to session card layout, phase row rendering, or branch display must be applied in both the side pane and the modal. Phase 1 T3-004 already demonstrates this: the session list section added to `CommandCenterDetailPanel` partially duplicates the session display logic in the board modal.

**Navigation friction**: Operators discover the richer modal only by clicking the bridge button. The panel itself gives an incomplete view. Operators who do not notice the "Open full detail" button get less information than those who do.

---

## 3. Proposed Long-Term Direction (Option B)

Full consolidation: **replace `CommandCenterDetailPanel` with a `CommandCenter`-specific modal** that:
- Reuses the `ProjectBoard` feature modal's tab structure (sessions tab, history tab, branch/commit data tab).
- Adds planning-specific context panels not present in the board modal: worktree state (from `PlanningCommandCenterItemDTO.worktree`), active-session chips (from `PlanningCommandCenterItemDTO.activeSessions`), and the `PhasePlanTable` as a dedicated "Plan" tab.
- Is reachable via the same `planningRouteFeatureModalHref` routing helper (already in use).

This consolidation eliminates the side pane, removes the bridge button (no longer needed), and makes the command center detail experience consistent with the rest of the planning surface.

---

## 4. Current State (Post-Phase 1)

After Phase 1 ships, the state is:

| Surface | What it shows | Gaps |
|---------|--------------|------|
| `CommandCenterDetailPanel` (side pane) | Phase plan rows (PhasePlanTable), per-phase session links (T3-004), "Open full detail" bridge button (T3-004) | No sessions tab, no history tab, no branch/commit dialog, no active-session chips in panel context |
| `ProjectBoard` feature modal (via bridge button) | Session history, branch/commit data, transcript links | No worktree state, no PhasePlanTable, no active-session chips in planning context |

The bridge button (T3-004) makes the modal reachable. Consolidation would make it the primary surface.

---

## 5. Trigger Conditions for Promotion

This spec is promoted from `idea` to `shaping` when at least one of the following triggers is met:

1. **Maintenance cost threshold**: three or more feature additions require parallel changes to both `CommandCenterDetailPanel` and the board modal.
2. **Explicit team decision**: post-Phase 2 architecture review concludes that side-pane-plus-bridge is causing operator confusion.
3. **Modal hooks are project-scoped**: OQ-2 resolves — `MultiProjectDetailRail` debt is cleared and modal hooks support multi-project scenarios cleanly.

---

## 6. Prerequisites Before Implementation

1. **Project-scoped modal hooks** (OQ-2): `usePlanningFeatureModalQuery` or the equivalent hook must be project-scoped. The UX leg explicitly names this as the blocking condition.
2. **Phase 2 complete**: the per-phase session links and active-session chips (Phase 1 T3-004 and T3-001) should be stable before the consolidation changes their render location.
3. **Accessibility audit**: the panel's keyboard navigation (Esc to close, Tab through rows) must be preserved or improved in the modal (OQ-4).

---

## 7. Related Specs

- **DEF-001 spec** (multi-branch watcher, BranchWatcherRegistry): `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`
- **UX leg findings** (active-session chip, per-phase session links, consolidation debt): `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md`
- **Phase 1 implementation plan**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`
- **Multi-project planning command center PRD**: `docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md`
