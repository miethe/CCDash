---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
status: completed
category: enhancements
title: 'Implementation Plan: Workflow Registry and Correlation Surface V1'
description: Implement a dedicated Workflow page in CCDash that unifies workflow identity,
  composition, correlation quality, and effectiveness evidence across CCDash and SkillMeat.
summary: Add a read-only workflow registry surface with a backend aggregation endpoint,
  workflow catalog/detail UI, correlation-state modeling, and drill-down actions into
  SkillMeat and CCDash evidence.
created: 2026-03-13
updated: '2026-03-14'
priority: high
risk_level: medium
complexity: High
track: Workflow Intelligence / Integrations
timeline_estimate: 3-5 weeks across 7 phases
feature_slug: workflow-registry-and-correlation-v1
feature_family: workflow-intelligence-and-integration
feature_version: v1
lineage_family: workflow-intelligence-and-integration
lineage_parent: null
lineage_children: []
lineage_type: enhancement
owner: platform-engineering
owners:
- platform-engineering
- ai-integrations
- fullstack-engineering
contributors:
- ai-agents
audience:
- developers
- platform-engineering
- engineering-leads
tags:
- implementation
- workflows
- skillmeat
- analytics
- integrations
- execution
prd: docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
related:
- docs/workflow-skillmeat-integration-developer-reference.md
- docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
- backend/services/integrations/skillmeat_sync.py
- backend/services/integrations/skillmeat_resolver.py
- backend/services/stack_observations.py
- backend/services/workflow_effectiveness.py
- backend/services/stack_recommendations.py
- backend/routers/analytics.py
- backend/models.py
- types.ts
- components/Analytics/AnalyticsDashboard.tsx
- components/execution/WorkflowEffectivenessSurface.tsx
- components/execution/RecommendedStackCard.tsx
- components/Layout.tsx
plan_ref: workflow-registry-and-correlation-v1
linked_sessions: []
---

# Implementation Plan: Workflow Registry and Correlation Surface V1

## Objective

Build a dedicated read-only Workflow page in CCDash that lets developers inspect:

1. workflow identity across CCDash and SkillMeat
2. workflow composition and related references
3. workflow correlation quality and resolution state
4. workflow effectiveness and evidence
5. the concrete gaps preventing stronger workflow modeling

The implementation should reuse current CCDash caches and scoring systems while introducing a clearer workflow response contract and a purpose-built UI.

## Current Baseline

Current backend capabilities already provide most of the raw material:

1. SkillMeat definition sync and enrichment
2. per-session stack observation backfill
3. workflow and stack effectiveness rollups
4. recommended-stack generation and artifact references
5. stable SkillMeat deep links

Current frontend capabilities already provide some reusable pieces:

1. workflow-effectiveness tables
2. artifact reference modal patterns
3. execution-page workflow and stack evidence cards
4. integrations settings and refresh actions

The missing piece is a dedicated aggregation and presentation layer that treats workflows as first-class cross-system objects.

## Fixed Decisions

1. V1 is read-only.
2. SkillMeat remains the source of truth for workflow definitions.
3. CCDash remains the source of truth for observations, scoring, and recommendations.
4. The new page should be a dedicated route, not only an analytics-tab expansion.
5. The page should make workflow ambiguity explicit rather than collapsing it into one label.
6. V1 should prefer derived aggregation from existing tables and services over introducing new long-term storage unless implementation pressure proves otherwise.

## Architecture Overview

### Backend

Add a workflow-registry aggregation layer that composes:

1. cached SkillMeat workflow definitions
2. cached artifact definitions that represent command-like workflows
3. observed workflow families from `session_stack_observations`
4. effectiveness rollups from `workflow_effectiveness`
5. stack and recommendation evidence where useful

Expected output shape per workflow entity:

1. identity block
2. correlation block
3. composition block
4. effectiveness block
5. issues block
6. actions block

### Frontend

Add a new route and page shell with:

1. workflow catalog sidebar or list pane
2. workflow detail panel
3. search and filters
4. drill-down actions
5. disabled/empty/error states

## Proposed New Backend Modules

1. `backend/services/workflow_registry.py`
   - aggregate list and detail payloads
   - normalize workflow entity identity
   - compute correlation state and issues
2. `backend/tests/test_workflow_registry.py`
   - contract and edge-case coverage

Potential model additions:

1. `WorkflowRegistryItem`
2. `WorkflowRegistryDetail`
3. `WorkflowCorrelationState`
4. `WorkflowCompositionSummary`
5. `WorkflowRegistryIssue`

## Proposed New Frontend Modules

1. `components/workflows/WorkflowRegistryPage.tsx`
2. `components/workflows/WorkflowCatalog.tsx`
3. `components/workflows/WorkflowDetailPanel.tsx`
4. `components/workflows/WorkflowCompositionSection.tsx`
5. `components/workflows/WorkflowIssuesPanel.tsx`
6. `services/workflows.ts`

The exact split can be adjusted during implementation, but the catalog/detail separation should remain.

## Phase 1: Response contract and aggregation service foundation

1. Add shared backend/frontend models for workflow registry list/detail payloads.
2. Define explicit fields for:
   - observed workflow family ref
   - resolved SkillMeat workflow id
   - resolved command artifact id
   - display label
   - correlation state
   - issues
3. Create `backend/services/workflow_registry.py`.
4. Implement normalization helpers that merge current workflow-like objects into one registry entity shape.

Assigned subagent(s): `backend-architect`, `python-backend-engineer`

Success criteria:

1. a registry item can represent strong, hybrid, weak, and unresolved workflow states
2. the contract separates identity concerns instead of reusing overloaded `workflowRef`
3. shared types remain consistent across backend and frontend

## Phase 2: Backend data composition and correlation logic

1. Load workflow definitions, artifact definitions, observations, and rollups into the registry service.
2. Merge SkillMeat workflows with CCDash-observed workflow families.
3. Detect and expose:
   - resolved-to-workflow
   - resolved-to-command-artifact
   - dual-backed
   - unresolved
4. Aggregate observed aliases and representative commands.
5. Add issue detection for stale cache, weak resolution, missing composition, and missing context coverage.

Assigned subagent(s): `python-backend-engineer`, `backend-architect`

Success criteria:

1. workflow entities can be built from current caches without manual data patching
2. hybrid command/workflow states are rendered explicitly
3. issue detection highlights the main known tuning gaps

## Phase 3: Composition and evidence enrichment

1. Reuse current workflow-enrichment metadata to expose:
   - artifact refs
   - resolved context modules
   - bundle alignment
   - plan summary
   - stage order
   - gate and fan-out counts
2. Reuse effectiveness rollups to attach:
   - success
   - efficiency
   - quality
   - risk
   - sample size
3. Attach representative sessions and recent SkillMeat execution summaries where available.
4. Expose stable SkillMeat actions for workflow/artifact/context/bundle navigation.

Assigned subagent(s): `python-backend-engineer`, `backend-architect`

Success criteria:

1. each workflow detail can surface composition and effectiveness together
2. the service clearly distinguishes CCDash evidence from SkillMeat metadata
3. missing composition data is surfaced as an issue rather than silently omitted

## Phase 4: Router and API surface

1. Add workflow registry endpoints, likely under `backend/routers/analytics.py` or a dedicated router.
2. Support:
   - list view
   - detail view
   - search and filter params
3. Keep payloads page-ready so the frontend does not recreate backend correlation rules.
4. Add disabled-state behavior when workflow analytics are turned off.

Assigned subagent(s): `python-backend-engineer`

Success criteria:

1. the API supports catalog and detail loading separately
2. filters are stable and documented
3. feature flags and disabled-state behavior remain consistent with existing analytics conventions

## Phase 5: New Workflow page and navigation

### Wireframes

Reference wireframes generated via Gemini Flash Image (nano-banana):

| Wireframe | Path | Description |
|-----------|------|-------------|
| Catalog list | `docs/wireframes/workflow-registry/workflow-catalog-wireframe.png` | Sidebar nav + search + filter chips + workflow card list |
| Detail panel | `docs/wireframes/workflow-registry/workflow-detail-wireframe.png` | Identity, composition stats, effectiveness bars, issues, actions |
| Full page (master-detail) | `docs/wireframes/workflow-registry/workflow-full-page-wireframe.png` | Combined catalog sidebar + detail panel layout |

### Implementation tasks

1. Add HashRouter route `/workflows` and optional `/:workflowId` param for deep-linking.
2. Add navigation entry in Layout.tsx sidebar (Lucide `Workflow` icon, positioned after Analytics).
3. Implement `WorkflowRegistryPage.tsx` as master-detail split layout.
4. Implement `WorkflowCatalog` (left pane) with search, filter chips, and card list.
5. Implement `WorkflowDetailPanel` (right pane) with identity, composition, effectiveness, issues, and actions sections.

### Component hierarchy

```
components/Workflows/
├── WorkflowRegistryPage.tsx          → Route shell, layout split, data fetching
├── catalog/
│   ├── WorkflowCatalog.tsx           → Search + filters + scrollable list
│   ├── CatalogFilterBar.tsx          → Filter chip row (All, Resolved, Hybrid, Unresolved)
│   └── WorkflowListItem.tsx          → Individual card with badge + mini score bars
└── detail/
    ├── WorkflowDetailPanel.tsx       → Container for all detail sections
    ├── DetailIdentityHeader.tsx      → Name, correlation badge, source labels
    ├── CompositionSection.tsx        → Artifact refs, context modules, bundle, stages
    ├── EffectivenessSection.tsx      → Score bars (success/efficiency/quality/risk) + sample size
    ├── IssuesSection.tsx             → Warning cards with AlertTriangle icons
    └── ActionsRow.tsx                → Pill buttons: Open in SkillMeat, View Sessions, View Artifact
```

### Responsive layout strategy

- **Desktop (≥1280px)**: Side-by-side master-detail. Catalog fixed at 380–420px, detail panel fluid.
- **Medium (1024–1279px)**: Catalog collapses to compact rail or drawer overlay; detail takes full width.
- **Mobile (<1024px)**: Stacked single-column. Selecting a workflow navigates to full-screen detail with back button.
- Breakpoint switch: use Tailwind `xl:` for side-by-side, `lg:` for collapsible, default stacked.

### State management approach

- **URL params**: Selected workflow via `/:workflowId` in HashRouter for deep-linking and browser back.
- **Global data**: Fetch registry list and detail via `services/workflows.ts` using the same patterns as `apiClient.ts`.
- **Local UI state**: `useState` for search query, active filter chip, catalog scroll position.
- **No new context needed**: Page-scoped data fetching; avoid adding to `DataContext`.

### Design language mapping (from existing patterns)

**Catalog list items** — reuse `WorkflowEffectivenessSurface` card pattern:
- Container: `rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4 transition-colors hover:border-slate-700`
- Workflow name: `text-sm font-semibold text-slate-100`
- Score bars: `h-2 overflow-hidden rounded-full bg-slate-900` with gradient fill

**Correlation badges** — reuse `RecommendedStackCard` resolution badge pattern:
- Resolved: `border-emerald-500/35 bg-emerald-500/10 text-emerald-100`
- Hybrid/Dual-backed: `border-cyan-500/20 bg-cyan-500/10 text-cyan-100`
- Unresolved: `border-amber-500/35 bg-amber-500/10 text-amber-100`
- Badge structure: `inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold`

**Filter chips** — pill-style toggles:
- Active: `rounded-full border border-indigo-500/30 bg-indigo-500/15 px-3 py-1 text-xs font-semibold text-indigo-200`
- Inactive: `rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-400 hover:border-slate-600`

**Detail sections** — reuse section header pattern:
- Section label: `text-[11px] uppercase tracking-[0.18em] text-slate-500`
- Section container: `rounded-2xl border border-slate-800/80 bg-slate-950/55 px-4 py-4`

**Effectiveness bars** — reuse score bar pattern from `WorkflowEffectivenessSurface`:
- Success: `from-emerald-400 to-emerald-500`
- Efficiency: `from-sky-400 to-blue-500`
- Quality: `from-cyan-400 to-indigo-500`
- Risk: `from-amber-300 via-orange-400 to-rose-500`

**Issue cards** — amber-tinted warning pattern:
- `rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-amber-100 text-sm`
- Icon: `<AlertTriangle size={14} className="text-amber-400" />`

**Action buttons** — pill button pattern from `RecommendedStackCard`:
- `inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-100 hover:bg-sky-500/20`

### UX enhancements

- Keyboard navigation: Arrow Up/Down to browse catalog, Enter to select, Escape to deselect.
- Search: Debounced input (300ms) with `Cmd+K` / `/` hotkey focus.
- Loading: Skeleton loaders matching `rounded-[24px]` card shapes with `animate-pulse`.
- Empty states: "No workflows found" with "Clear Filters" action; "Select a workflow" prompt in detail panel.
- Disabled state: When workflow analytics feature flag is off, show info banner matching existing `bg-indigo-900/20 border border-indigo-500/30` pattern.

Assigned subagent(s): `frontend-developer`, `ui-engineer-enhanced`

Success criteria:

1. users can browse workflows without visiting execution or analytics first
2. catalog and detail rendering remains usable on desktop and mobile widths
3. correlation state is visually clear, not buried in metadata
4. wireframe fidelity is maintained in implementation
5. design tokens match existing CCDash patterns with no new color or spacing primitives

## Phase 6: Cross-surface integration and actions

1. Reuse or adapt existing artifact modal patterns where helpful.
2. Add open actions to:
   - SkillMeat workflow
   - related artifact
   - related context memory
   - related bundle
   - representative session
3. Add refresh/recompute affordances or links into existing ops flows.
4. Link from execution and analytics surfaces back to the new workflow page when appropriate.

Assigned subagent(s): `frontend-developer`, `ui-engineer-enhanced`

Success criteria:

1. the page acts as a workflow hub rather than a dead-end viewer
2. users can move between workflow identity, evidence, and SkillMeat objects efficiently
3. no existing execution-page behavior regresses

## Phase 7: Validation, QA, and documentation

1. Add backend tests for:
   - strong workflow resolution
   - hybrid command-artifact workflow resolution
   - unresolved workflows
   - issue detection
2. Add frontend tests for:
   - list rendering
   - search/filter behavior
   - detail panel rendering
   - action links
3. Update developer docs where needed to reference the new page.
4. Run validation:
   - targeted backend tests
   - frontend build

Assigned subagent(s): `python-backend-engineer`, `frontend-developer`, `documentation-writer`

Success criteria:

1. new workflow payloads are test-covered
2. page interactions are test-covered at least at the smoke level
3. developer docs reflect the new surface and routing

## Testing Plan

## Backend tests

1. registry list groups SkillMeat workflows and CCDash workflow families correctly
2. command-only workflow families are marked as hybrid or weak as designed
3. unresolved workflow families produce issues instead of empty labels
4. detail payload includes composition and effectiveness when present
5. disabled-state behavior matches current feature-flag conventions

## Frontend tests

1. workflow catalog renders items and correlation badges
2. search narrows the catalog deterministically
3. filter state updates the visible set
4. detail panel renders identity, composition, effectiveness, and issues
5. action buttons emit the correct link/open behavior

## Manual QA

1. page loads with SkillMeat integration enabled and populated cache
2. page loads when SkillMeat is disabled and shows a clear state
3. command-family workflows like `/dev:execute-phase` are distinguishable from true SkillMeat workflow definitions
4. unresolved workflow entries visibly explain why they are unresolved
5. drill-down into representative sessions and SkillMeat links works end to end

## Acceptance Criteria

1. CCDash exposes a dedicated Workflow page.
2. The page lists workflow entities from both SkillMeat and CCDash observations.
3. Each workflow exposes an explicit correlation state.
4. Workflow detail combines identity, composition, effectiveness, and issues.
5. Users can navigate from the page to related SkillMeat definitions and CCDash sessions.
6. The page remains informative when workflow resolution is hybrid or incomplete.

## Risks and Mitigations

1. Risk: backend aggregation grows too coupled to current service internals.
   - Mitigation: create a dedicated registry service instead of embedding logic in routers or components.
2. Risk: the page duplicates execution or analytics views instead of complementing them.
   - Mitigation: keep the focus on identity, composition, and correlation quality.
3. Risk: workflow detail lacks enough composition depth for true tuning.
   - Mitigation: surface current limits as issues and plan V2 around explicit workflow-graph modeling.
4. Risk: performance degrades if every workflow detail is loaded eagerly.
   - Mitigation: separate list and detail fetches.

## Rollout Notes

1. Ship behind the existing workflow analytics gate if needed for a gradual rollout.
2. Validate first with internal projects that already have SkillMeat-backed workflow data.
3. Use early feedback to decide whether V2 should add:
   - a dedicated workflow graph model
   - bundle-as-workflow-package support
   - manual correlation annotations
