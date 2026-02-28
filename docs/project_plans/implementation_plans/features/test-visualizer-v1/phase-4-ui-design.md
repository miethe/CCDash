---
title: "Phase 4: UI/UX Design - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 4
phase_title: "UI/UX Design"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "20 story points"
duration: "1.5 weeks"
assigned_subagents: [ui-designer, gemini-orchestrator, ux-researcher, ui-engineer]
entry_criteria:
  - PRD approved
  - Design spec reviewed
  - CCDash design system understood (slate-dark theme, indigo accents, existing component patterns)
exit_criteria:
  - Test status visual language defined (colors, icons, badges)
  - Testing Page wireframes complete (full page, domain tree, drilldown panels)
  - Feature Modal / Execution Page / Session Page tab designs complete
  - Component library design spec for all 8 core components
  - Interaction design spec for live updates, drilldown transitions, filter animations
  - Design artifacts committed to docs/project_plans/designs/test-visualizer/
tags: [implementation, ui-design, test-visualizer, ux, wireframes, components]
---

# Phase 4: UI/UX Design

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 20 story points | **Duration**: 1.5 weeks
**Assigned Subagents**: ui-designer, gemini-orchestrator, ux-researcher, ui-engineer
**Parallel With**: Phases 1, 2, 3 (backend critical path runs concurrently)

---

## Overview

Phase 4 runs in parallel with the backend critical path (Phases 1-3). Design artifacts produced here directly feed Phase 5 (Core UI Components) and Phase 6 (Page & Tab Integration). The goal is to produce detailed specifications, not pixel-perfect mockups — the implementation team needs clear visual language, layout structure, and component specs.

All design decisions must respect CCDash's established visual system:
- **Dark theme**: `bg-slate-950` / `bg-slate-900` / `bg-slate-800`
- **Accent**: `indigo-500` / `indigo-400` for primary actions and active states
- **Status colors**: `emerald-*` (success/passing), `rose-*` (error/failing), `amber-*` (warning/skipped), `slate-*` (neutral)
- **Card pattern**: `bg-slate-900 border border-slate-800 rounded-xl p-4`
- **Typography**: `text-slate-100` (primary), `text-slate-400` (secondary/muted)
- **Icons**: Lucide React (existing library)

---

## Sub-Phase 4A: Design System Extension

**Subagents**: ui-designer, gemini-orchestrator
**Skills**: aesthetic, frontend-design, ui-ux-pro-max
**Output**: Visual language spec document at `docs/project_plans/designs/test-visualizer/design-system.md`

### Test Status Visual Language

Define the canonical visual representation for each test status, used consistently across all 4 entry points:

| Status | Color Token | Icon (Lucide) | Badge Text | Usage |
|--------|-------------|---------------|------------|-------|
| `passed` | `emerald-500` | `CheckCircle2` | "Passing" | Test result is green |
| `failed` | `rose-500` | `XCircle` | "Failing" | Test result is red |
| `skipped` | `amber-500` | `MinusCircle` | "Skipped" | Explicitly skipped |
| `error` | `rose-600` | `AlertCircle` | "Error" | Infrastructure error |
| `xfailed` | `amber-400` | `AlertTriangle` | "XFail" | Expected failure |
| `xpassed` | `rose-400` | `AlertTriangle` | "XPass" | Unexpected pass (warning) |
| `unknown` | `slate-500` | `HelpCircle` | "Unknown" | No data yet |
| `running` | `indigo-400` | `Loader2` (spin) | "Running" | Live active test |

### Health Gauge Visual Language

Computed health score displayed as a visual gauge:

| Score Range | Color | Label |
|-------------|-------|-------|
| 90-100% | `emerald-500` | "Healthy" |
| 70-89% | `amber-400` | "Degraded" |
| 50-69% | `amber-600` | "At Risk" |
| < 50% | `rose-500` | "Critical" |

### Integrity Signal Severity

| Severity | Color | Icon | Display |
|----------|-------|------|---------|
| `high` | `rose-500` | `ShieldAlert` | Prominent alert banner |
| `medium` | `amber-500` | `ShieldX` | Inline warning card |
| `low` | `slate-400` | `Shield` | Subtle indicator |

### Deliverables

- [ ] Status color/icon/badge spec table (as above, formalized)
- [ ] Health gauge color scale spec
- [ ] Integrity signal severity display spec
- [ ] Figma-style color reference (tailwind token names)
- [ ] Icon set selection confirmed (all from Lucide React)

---

## Sub-Phase 4B: Testing Page Wireframes

**Subagents**: gemini-orchestrator (scaffolding), ui-designer (refinement)
**Output**: Wireframe descriptions + ASCII layout in `docs/project_plans/designs/test-visualizer/testing-page-wireframes.md`

### Testing Page Layout (`/tests`)

The Testing Page has three primary zones:

```
┌─────────────────────────────────────────────────────────────────┐
│ HEADER: "Test Visualizer"  [Last updated: 2m ago]  [Refresh]   │
│ GLOBAL HEALTH GAUGE: 87% Healthy  •  1,234 tests  •  23 failing │
├─────────────────┬───────────────────────────────────────────────┤
│ DOMAIN TREE     │  DETAIL PANEL                                 │
│ (left sidebar)  │  (right, takes remaining width)               │
│                 │                                               │
│ > Domain A 95%  │  [Selected: Domain A > Auth > Login Feature]  │
│   > Auth 92%    │                                               │
│     > Login 89% │  ┌─ Health Summary ──────────────────────┐   │
│     > Signup 95%│  │  89% Healthy  •  9 passing  •  1 fail  │   │
│   > Billing 95% │  └──────────────────────────────────────────┘ │
│ > Domain B 72%  │                                               │
│   ...           │  ┌─ Test Results Table ──────────────────┐   │
│                 │  │  [Search] [Filter: Status] [Run: All]  │   │
│ [Filter panel]  │  │  test_login_valid    PASS  120ms       │   │
│                 │  │  test_login_invalid  PASS   45ms       │   │
│                 │  │  test_mfa_bypass     FAIL  250ms       │   │
│                 │  │  ...                                   │   │
│                 │  └──────────────────────────────────────────┘ │
│                 │                                               │
│                 │  ┌─ Integrity Alerts ────────────────────┐   │
│                 │  │  [HIGH] Assert removed in abc1234      │   │
│                 │  └──────────────────────────────────────────┘ │
└─────────────────┴───────────────────────────────────────────────┘
```

### Domain Tree Design

- Tree nodes: collapsible with `ChevronRight`/`ChevronDown`
- Status badge on each node (pass%, failing count)
- Color-coded left border matching health level
- "Loading..." skeleton state during fetch
- "No tests mapped" empty state with action to set up mapping

### Drilldown Panels

Panel levels activated by tree click:
1. **Domain selected**: Summary stats + feature list
2. **Feature selected**: Health gauge + test suite list + integrity alerts
3. **Test selected**: Full result history + run timeline

### Filter Controls (Sidebar Portal)

Rendered into `#sidebar-portal` div in Layout.tsx:
- Status filter: checkbox group (passed, failed, skipped, error)
- Run filter: dropdown (All, Latest, Last 7 days, by run_id)
- Branch filter: text input or dropdown of known branches
- Session filter: link to filter by agent_session_id

### Deliverables

- [ ] ASCII wireframe for full Testing Page layout (above)
- [ ] Domain tree node design spec
- [ ] Detail panel state machine (what shows at each drilldown level)
- [ ] Filter sidebar spec (controls and behavior)
- [ ] Empty states: no tests, no mappings, feature flag disabled

---

## Sub-Phase 4C: Tab Designs

**Subagents**: ui-designer
**Output**: Tab layout specs in `docs/project_plans/designs/test-visualizer/tab-designs.md`

### Feature Modal "Test Status" Tab

The Feature Modal (in `ProjectBoard.tsx`) uses `FeatureModalTab` union type. The new "Test Status" tab shows a compact summary:

```
┌─── Test Status ──────────────────────────────────────────────┐
│  Health: 89%  •  9 passing  •  1 failing  •  0 skipped      │
│  Last run: 2h ago  •  Branch: feat/my-feature                │
│                                                               │
│  Recent Failures:                                             │
│  • test_mfa_bypass [FAIL] — assertion_removed signal         │
│                                                               │
│  Integrity: 1 alert (medium severity)                        │
│                                                               │
│  [View Full Test Status →]  (links to Execution Page tab)   │
└───────────────────────────────────────────────────────────────┘
```

**Visibility rule**: Tab is only shown when `feature.test_health !== null` (i.e., tests are mapped to this feature). Hidden for features with no test data.

### Execution Page "Test Status" Tab

Added to `WorkbenchTab` union type in `FeatureExecutionWorkbench.tsx`. Full view, filtered to selected feature:

```
┌─── Test Status ──────────────────────────────────────────────┐
│  [LIVE indicator if session active] Last run: 30s ago        │
│                                                               │
│  Health: 89%  ████████░░  •  [Refresh] [Link to /tests]     │
│                                                               │
│  ┌─ Test Run History ───────────────────────────────┐        │
│  │  Run #abc123  2h ago  94% pass  •  Session S-1   │        │
│  │  Run #def456  1d ago  87% pass  •  Session S-2   │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─ Test Results (Latest Run) ──────────────────────┐        │
│  │  [Status filter] [Search]                        │        │
│  │  test_login_valid     PASS  120ms                │        │
│  │  test_mfa_bypass      FAIL  250ms  [Details v]   │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─ Integrity Alerts (Feature) ─────────────────────┐        │
│  │  [HIGH] Assert removed in abc1234  Session S-2   │        │
│  └──────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────┘
```

**Live behavior**: If `session.status === 'running'`, poll every 30s for new test results. Show "LIVE" badge on panel header. Auto-scroll to new failures.

### Session Page "Test Status" Tab

Added to `SessionInspector.tsx` tab union. Filtered by `agent_session_id`:

```
┌─── Test Status (This Session) ───────────────────────────────┐
│  Session: session-xyz  •  Branch: feat/my-feature            │
│                                                               │
│  [Test runs triggered by this session]                       │
│  Run #abc123  94% pass  •  Modified: 3 tests                 │
│                                                               │
│  Tests Modified During Session:                              │
│  • test_mfa_bypass  CHANGED  [diff indicator]                │
│  • test_login_new   ADDED                                    │
│                                                               │
│  [LIVE] if session active / [Historical] if completed       │
└───────────────────────────────────────────────────────────────┘
```

**Key difference from Execution tab**: Shows "tests modified during this session" — tests where the `session_file_updates` records changes to test files.

### Deliverables

- [ ] Feature Modal tab layout spec with visibility rules
- [ ] Execution Page tab layout spec with live vs historical states
- [ ] Session Page tab layout spec with "modified tests" section
- [ ] Tab icon selection (suggest: `TestTube2` from Lucide)
- [ ] Tab label: "Test Status" (consistent across all 3 tab locations)

---

## Sub-Phase 4D: Component Library Design

**Subagents**: ui-designer, ui-engineer
**Output**: Component spec in `docs/project_plans/designs/test-visualizer/component-specs.md`

### Component Specifications

#### `TestStatusBadge`

```
Props: status: TestStatus, size?: 'sm' | 'md' | 'lg', showLabel?: boolean
Visual: Icon + color + optional text label
Sizes: sm (12px icon, no label), md (16px icon + label), lg (20px icon + label)
States: all 8 status types from design system
Accessibility: aria-label="Test status: Passing"
```

#### `TestRunCard`

```
Props: run: TestRunDTO, showSession?: boolean, compact?: boolean
Visual: Header (run_id short + timestamp) + stats row (pass/fail/skip counts)
         + optional session link + optional git_sha chip
States: expanded (shows all results) vs collapsed (summary only)
Interaction: click to expand, link to /tests?run_id=...
```

#### `TestResultTable`

```
Props: results: TestResultDTO[], definitions: Record<string, TestDefinitionDTO>,
       onTestClick?: (testId) => void, filterStatus?: TestStatus[]
Visual: Sortable table: Test Name | Status | Duration | Error Preview
        Status column: TestStatusBadge
        Error preview: truncated first line of error_message, tooltip on hover
Interaction: click row to expand error details inline
Empty state: "No test results" with helpful message
Loading state: Skeleton rows (5 rows minimum)
```

#### `DomainTreeView`

```
Props: domains: DomainHealthRollupDTO[], onSelect: (domainId) => void,
       selectedId?: string, expandedIds?: string[]
Visual: Collapsible tree, each node shows: name + health bar + pass% badge
        Selected node: indigo highlight border
        Collapsed by default, expand on click
Interaction: click node to select (fires onSelect), chevron to expand/collapse
             keyboard: arrow keys navigate, Enter to select
```

#### `TestTimeline`

```
Props: timeline: TimelineDataPoint[], showSignals?: boolean, height?: number
Visual: Line chart (pass_rate over time), x-axis = dates, y-axis = 0-100%
        Signal markers: red diamond markers at dates with integrity signals
        "first_green" and "last_red" annotations
        Color: emerald line for passing trend, rose markers for failures
Library: Existing chart library (check AnalyticsDashboard for precedent)
Interaction: hover tooltip shows date + pass_rate + run_ids + signal count
```

#### `IntegrityAlertCard`

```
Props: signal: TestIntegritySignalDTO, showSession?: boolean
Visual: Card with severity icon + signal_type label + git_sha chip
        + file_path + timestamp
        High severity: rose-500 left border
        Medium: amber-500 left border
        Low: slate-500 left border
Interaction: click to expand details_json, link to session if agent_session_id set
```

#### `HealthGauge`

```
Props: passRate: number, integrityScore: number, size?: 'sm' | 'md' | 'lg'
Visual: Circular progress ring (pass_rate) + color based on health scale
        Center text: "87%" in large font
        Subtitle: health label ("Healthy" / "Degraded" / "At Risk" / "Critical")
        Size sm: 64px ring, size md: 96px ring, size lg: 128px ring
Accessibility: aria-valuenow, aria-valuemin, aria-valuemax
```

#### `HealthSummaryBar`

```
Props: passed: number, failed: number, skipped: number, total: number
Visual: Horizontal stacked bar: emerald (passed) + rose (failed) + amber (skipped)
        Below bar: "N passing • M failing • K skipped" text
        Proportional widths, minimum 2px width per non-zero category
Accessibility: role="img", aria-label describes the full breakdown
```

### Deliverables

- [ ] Detailed prop interfaces for all 8 components
- [ ] Visual description for each state (default, loading, empty, error)
- [ ] Accessibility requirements per component
- [ ] Responsive behavior (minimum width: 320px for badges, 480px for tables)
- [ ] Animation/transition specs for state changes

---

## Sub-Phase 4E: Interaction Design

**Subagents**: ui-designer, ux-researcher
**Output**: Interaction spec in `docs/project_plans/designs/test-visualizer/interaction-design.md`

### Live Update Animations

When new test results arrive during polling:
- New failing tests: slide-in from top of result table, rose-500 pulse animation (500ms)
- Status change (fail -> pass): badge color transition with 300ms ease
- Health gauge: smooth animation on value change (300ms ease-out)
- "New results available" banner: non-blocking toast at top of panel, click to refresh

### Drilldown Transitions

- Tree node click -> detail panel fade-in (150ms)
- Domain -> Feature -> Test drilldown: breadcrumb updates, panel slides right (200ms)
- Back navigation: panel slides left

### Filter Interactions

- Filter changes trigger debounced refetch (300ms debounce)
- Loading state: table rows replaced with skeleton (not spinner overlay)
- Filter tags shown as chips below search bar; click chip to remove

### Keyboard Navigation

- Domain tree: arrow keys navigate, Enter selects, Escape deselects
- Test result table: Tab/Shift-Tab moves between rows; Enter expands details; Space toggles checkbox
- Modal tabs: arrow keys switch tabs

### Deliverables

- [ ] Animation timing spec for all state transitions
- [ ] Live update user flow spec (polling, notification, refresh)
- [ ] Keyboard navigation map for all interactive elements
- [ ] Drilldown navigation breadcrumb behavior spec
- [ ] Empty state copy (text + icon per empty state type)

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| DES-1 | Design system extension | Define test status visual language: color tokens, icons, badge styles, health gauge scale, integrity severity display. | Design system spec document complete. All 8 status types documented with Tailwind token names and Lucide icons. | 2 | ui-designer | None |
| DES-2 | Testing Page wireframes | Create ASCII wireframe + written layout spec for full Testing Page. Cover: global health header, domain tree sidebar, detail panel (3 drilldown states), filter sidebar. | Wireframe covers all 3 drilldown states. Filter sidebar spec complete. Empty states documented. | 4 | ui-designer, gemini-orchestrator | DES-1 |
| DES-3 | Feature Modal tab design | Design "Test Status" tab for Feature Modal. Compact summary view. Visibility rules. Link to Execution Page. | Tab layout spec with all data elements. Visibility rule documented. Tab icon chosen. | 2 | ui-designer | DES-1 |
| DES-4 | Execution Page tab design | Design "Test Status" tab for Execution Page. Full view with live indicator, run history, result table, integrity alerts. Cover live vs historical states. | Both live and historical states designed. Auto-scroll behavior specified. "LIVE" badge spec defined. | 3 | ui-designer | DES-3 |
| DES-5 | Session Page tab design | Design "Test Status" tab for Session Page. "Modified tests" section unique to this tab. Session-scoped filtering. | Tab layout spec. "Modified tests" section clearly designed. Links to Testing Page specified. | 2 | ui-designer | DES-3 |
| DES-6 | Component specs: badges and cards | Write detailed component specs for: TestStatusBadge, TestRunCard, IntegrityAlertCard, HealthSummaryBar. Cover props, states, accessibility, sizing. | All 4 component specs written. Prop interfaces defined. All states (default, loading, empty, error) described. | 3 | ui-designer, ui-engineer | DES-1 |
| DES-7 | Component specs: tree and table | Write detailed component specs for: DomainTreeView, TestResultTable. Cover: keyboard nav, loading skeleton, empty states, interaction flows. | Both specs complete. Keyboard nav documented. Loading skeleton described. Row expansion behavior specified. | 2 | ui-designer, ui-engineer | DES-1 |
| DES-8 | Component specs: charts and gauges | Write specs for: TestTimeline (line chart), HealthGauge (circular progress). Define chart library to use (consistent with AnalyticsDashboard), axis labels, tooltip behavior, signal markers. | Both specs complete. Chart library confirmed. Axis and tooltip behavior documented. Responsive behavior specified. | 2 | ui-designer, ui-engineer | DES-1 |

---

## Quality Gates

- [ ] All design artifacts committed to `docs/project_plans/designs/test-visualizer/`
- [ ] Design system extension doc reviewed by ui-engineer for implementability
- [ ] All Tailwind tokens used in specs exist in current CCDash theme
- [ ] All icons selected from Lucide React (no external icon library additions)
- [ ] Accessibility requirements documented per component
- [ ] Wireframes reviewed against PRD requirements (FR-8 through FR-11)
- [ ] Interaction design covers live update, drilldown, and keyboard nav
- [ ] Phase 5 engineer can start implementation from specs without further design clarification

---

## Key Design Artifacts

| Artifact | Path | Owner |
|----------|------|-------|
| Design system extension | `docs/project_plans/designs/test-visualizer/design-system.md` | ui-designer |
| Testing Page wireframes | `docs/project_plans/designs/test-visualizer/testing-page-wireframes.md` | ui-designer |
| Tab designs | `docs/project_plans/designs/test-visualizer/tab-designs.md` | ui-designer |
| Component specs | `docs/project_plans/designs/test-visualizer/component-specs.md` | ui-designer, ui-engineer |
| Interaction design | `docs/project_plans/designs/test-visualizer/interaction-design.md` | ui-designer, ux-researcher |
