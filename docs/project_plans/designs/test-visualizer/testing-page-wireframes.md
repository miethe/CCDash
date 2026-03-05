---
title: "Testing Page Wireframes"
doc_type: design
feature_slug: test-visualizer
created: 2026-02-28
updated: 2026-02-28
---

# Testing Page Wireframes

## 1. Overview

This document is the complete wireframe specification for the Testing Page (`/tests` route) in CCDash. It describes every zone, panel state, filter behavior, empty state, loading state, and responsive breakpoint in written form. Visual mockup images are produced separately -- this document is the authoritative written layout spec that a frontend engineer uses alongside those mockups during implementation.

All colors, icons, badges, and typography referenced here come from the [Test Visualizer Design System](/docs/project_plans/designs/test-visualizer/design-system.md). This document does not redefine those tokens; it references them by name.

### Route Configuration

- **Path**: `/tests`
- **Component**: `TestVisualizerPage`
- **Router**: HashRouter (consistent with all other CCDash routes)
- **URL query params consumed**: `domain`, `feature`, `test`, `status`, `run_id`, `branch`, `session`

---

## 2. Page Layout: Three-Zone Architecture

The Testing Page is divided into three fixed zones that together fill the full viewport area to the right of the global CCDash sidebar (Layout.tsx).

### Zone Map

```
Full viewport (minus Layout.tsx global sidebar)
+-----------------------------------------------------------------+
| ZONE 1: Header Bar (full width, 64px fixed height)              |
+-----------------------------------------------------------------+
| ZONE 2: Domain Tree  | ZONE 3: Detail Panel                    |
| Sidebar              | (remaining width, scrollable)            |
| (280px fixed width,  |                                          |
|  full remaining       |                                          |
|  height, scrollable)  |                                          |
|                       |                                          |
|                       |                                          |
|                       |                                          |
+-----------------------+------------------------------------------+
```

### Structural HTML Outline

```html
<div class="flex flex-col h-full">
  <!-- Zone 1: Header Bar -->
  <header class="h-16 shrink-0 ...">...</header>

  <!-- Zones 2 & 3: Body -->
  <div class="flex flex-1 overflow-hidden">
    <!-- Zone 2: Domain Tree Sidebar -->
    <aside class="w-[280px] shrink-0 overflow-y-auto ...">...</aside>

    <!-- Zone 3: Detail Panel -->
    <main class="flex-1 overflow-y-auto ...">...</main>
  </div>
</div>
```

---

## 3. Zone 1: Header Bar

**Dimensions**: Full width of the testing page area, 64px height, fixed (does not scroll).

**Background**: `bg-slate-900 border-b border-slate-800`

### Layout

```
+-------------------------------------------------------------------+
| [TestTube2]  Test Visualizer    [HealthGauge sm]  1,234 tests     |
|                                  87% Healthy      23 failing      |
|                                                   Last: 2m ago [R]|
+-------------------------------------------------------------------+
```

### Left Section

- **Icon**: `TestTube2` from Lucide, `size={22}`, `className="text-indigo-400"`
- **Title**: "Test Visualizer", `text-xl font-semibold text-slate-100`
- **Container**: `flex items-center gap-3`

### Center Section

- **HealthGauge**: `sm` variant (56x56 SVG), displaying the global pass rate across all domains
- **Stats row** (to the right of gauge): `flex items-center gap-4 text-sm text-slate-400`
  - Total test count: `"{total} tests"`
  - Failing count: `<span class="text-rose-400">{failing} failing</span>`
  - These are plain text, not badges

### Right Section

- **Timestamp**: "Last updated: 2m ago" in `text-xs text-slate-500`
  - Computed as relative time from most recent `TestRunDTO.started_at`
  - Updates every 60 seconds via interval
- **Refresh button**: `<button>` with `RefreshCcw` icon (`size={16}`), `text-slate-400 hover:text-slate-200`
  - `className="p-2 rounded-lg hover:bg-slate-800 transition-colors"`
  - On click: re-fetches all data (domains, health, current detail panel)
  - Shows `animate-spin` on the icon during fetch (300ms minimum to prevent flash)
  - `aria-label="Refresh test data"`

### Header Responsive Notes

- Below 768px: hide the center stats section; show only title and refresh button
- Below 640px: abbreviate title to just the TestTube2 icon

---

## 4. Zone 2: Domain Tree Sidebar

**Dimensions**: 280px width, full height below header, vertically scrollable.

**Background**: `bg-slate-950 border-r border-slate-800`

### 4.1 Tree Structure

The tree is a two-level hierarchy: **Domain** (top level) and **Feature** (child level). Data comes from `GET /api/tests/health/domains`.

```
DOMAIN TREE
+------------------------------------------+
| > core-api                        94%    |
|   > auth                          92%    |
|   > billing                       96%    |
|   > users                         88%    |
| v payments                        71%    |
|   > checkout                      65%    |
|   > refunds                       78%    |
| > notifications                   100%   |
|                                          |
|                                          |
| -------- FILTER PANEL --------           |
| (rendered via sidebar portal)            |
+------------------------------------------+
```

### 4.2 Tree Node Design

Each tree node is rendered as a single row with the following structure:

```
[chevron] [name]                    [health%]
```

#### Domain Node (Top Level)

- **Chevron**: `ChevronRight` (collapsed) or `ChevronDown` (expanded), `size={14}`, `text-slate-500`
- **Name**: `text-sm font-medium text-slate-200 truncate`
- **Health badge**: Pass rate percentage, `text-xs font-semibold` with color based on health scale:
  - 90-100%: `text-emerald-400`
  - 70-89%: `text-amber-400`
  - 50-69%: `text-amber-600`
  - 0-49%: `text-rose-400`
- **Left border**: 3px solid border on the left edge, color matching the health scale
- **Container**: `flex items-center gap-2 px-3 py-2.5 cursor-pointer rounded-lg mx-2 transition-colors`

#### Feature Node (Child Level)

- Same structure as domain but indented with `pl-8`
- Chevron omitted (leaf nodes, no further nesting)
- Instead of chevron, a small dot: `w-1.5 h-1.5 rounded-full` in the health color

#### Node States

| State | Classes |
|-------|---------|
| Default | `text-slate-200 hover:bg-slate-800/50` |
| Hover | `bg-slate-800/50` |
| Selected | `bg-indigo-500/10 border border-indigo-500/20` (replaces default border) |
| Focused (keyboard) | `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950` |

#### Interaction

- **Click on chevron area or name**: Expands/collapses children AND selects the node (fires `onSelect`)
- **Click on already-expanded domain**: Selects the domain without collapsing (double-click to collapse)
- **Keyboard**: `ArrowDown`/`ArrowUp` to navigate between visible nodes. `ArrowRight` to expand a collapsed domain. `ArrowLeft` to collapse an expanded domain or move to parent. `Enter` to select. `Home`/`End` to jump to first/last node.
- **WAI-ARIA**: `role="tree"` on container, `role="treeitem"` on each node, `aria-expanded` on domain nodes.

### 4.3 Filter Panel (Sidebar Portal)

The filter panel renders into the `#sidebar-portal` div defined in Layout.tsx (line 67 of Layout.tsx). It appears below the main navigation items, separated by the existing `border-t border-slate-800` divider.

When the Layout sidebar is collapsed (`isCollapsed === true`), the portal div is hidden (`class="hidden"`), so the filter panel is not visible in collapsed mode. This is acceptable because filters are secondary controls.

#### Filter Controls

**Section header**: `text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3` -- "Test Filters"

##### Status Filter

- **Type**: Checkbox group
- **Options**: Passed, Failed, Skipped, Error (each with status icon + label)
- **Default**: Passed and Failed checked; Skipped and Error unchecked
- **Rendering**: Vertical stack, each item is:
  ```
  [checkbox] [StatusIcon size={12}] [label text-xs text-slate-300]
  ```
- **Checkbox style**: `w-3.5 h-3.5 rounded border-slate-600 bg-slate-800 checked:bg-indigo-500 checked:border-indigo-500`

##### Run Filter

- **Type**: Dropdown select
- **Options**: "All Runs" (default), "Latest Run", "Last 7 Days", then a separator, then individual `run_id` values (most recent 10)
- **Style**: `bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-300 px-2 py-1.5 w-full`
- **Dropdown menu**: `bg-slate-800 border border-slate-700 rounded-lg shadow-lg` with `hover:bg-slate-700` items

##### Branch Filter

- **Type**: Text input with autocomplete dropdown
- **Placeholder**: "Filter by branch..."
- **Style**: `bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-300 px-2 py-1.5 w-full`
- **Autocomplete**: Populated from `GET /api/tests/branches` (returns known branch names). Dropdown appears on focus and filters as user types.
- **Icon**: `GitBranch` (`size={12}`) inline at left inside input

##### Session Filter

- **Type**: Text input
- **Placeholder**: "Session ID..."
- **Style**: Same as branch filter
- **Behavior**: Accepts an `agent_session_id` value. On valid input, filters all results to tests associated with that session.
- **Icon**: `Terminal` (`size={12}`) inline at left inside input

#### Filter Behavior

1. **Debounced refetch**: Any filter change triggers a 300ms debounce, then re-fetches the detail panel data with updated query parameters.
2. **URL persistence**: All active filters are serialized to URL query params (`?status=passed,failed&run_id=latest&branch=feat/auth`). This enables sharing filtered views via URL.
3. **Active filter chips**: When any non-default filter is active, a chip bar appears at the top of the Detail Panel (Zone 3), showing each active filter as a removable chip.
4. **Clear all**: A "Clear filters" text button appears in the chip bar when any filter is active. Resets all filters to defaults.

---

## 5. Zone 3: Detail Panel

**Dimensions**: Remaining width after sidebar (viewport width minus Layout sidebar minus 280px domain tree), full height below header, vertically scrollable.

**Background**: `bg-slate-950`

**Padding**: `p-6` (24px all sides)

The Detail Panel content changes based on the user's selection in the Domain Tree. This is governed by a state machine with four states.

---

## 6. Detail Panel State Machine

```
                    +------------------+
                    |   NO SELECTION   |  (initial state)
                    |   (State 1)      |
                    +--------+---------+
                             |
                    click domain node
                             |
                             v
                    +------------------+
                    | DOMAIN SELECTED  |
                    |   (State 2)      |
                    +--------+---------+
                             |
                    click feature node
                             |
                             v
                    +------------------+
                    | FEATURE SELECTED |
                    |   (State 3)      |
                    +--------+---------+
                             |
                    click table row
                             |
                             v
                    +------------------+
                    |  TEST SELECTED   |
                    |   (State 4)      |
                    +------------------+

    Navigation back: breadcrumb click returns to any ancestor state.
    Tree click: always jumps directly to State 2 or State 3.
    Escape key: moves up one level (State 4 -> 3 -> 2 -> 1).
```

### 6.1 State 1: No Selection (Default)

Displayed when the page first loads and no domain or feature is selected.

```
+------------------------------------------------------+
|                                                      |
|                                                      |
|          [TestTube2 icon, size={48},                 |
|           text-slate-700]                            |
|                                                      |
|       Select a domain or feature                     |
|       from the tree to view test results             |
|                                                      |
|                                                      |
|  +------------+  +------------+  +---------------+   |
|  | Total Tests|  | Pass Rate  |  | Recent Fails  |   |
|  |   1,234    |  |   87.2%    |  |     23        |   |
|  +------------+  +------------+  +---------------+   |
|                                                      |
+------------------------------------------------------+
```

#### Elements

- **Illustration area**: Centered vertically and horizontally in upper two-thirds of panel
  - Icon: `TestTube2`, `size={48}`, `className="text-slate-700 mx-auto"`
  - Heading: "Select a domain or feature", `text-base font-medium text-slate-400 text-center mt-4`
  - Subtext: "from the tree to view test results", `text-sm text-slate-500 text-center mt-1`

- **Quick stats cards**: Row of 3 stat cards at bottom of centered area, `flex gap-4 mt-8 justify-center`
  - Each card: `bg-slate-900 border border-slate-800 rounded-xl px-6 py-4 text-center min-w-[140px]`
  - Card title: `text-xs text-slate-500 uppercase tracking-wider` ("Total Tests", "Pass Rate", "Recent Failures")
  - Card value: `text-2xl font-bold text-slate-100 mt-1`
  - Pass Rate card value color: matches health gauge color scale
  - Recent Failures card value: `text-rose-400` if > 0, `text-emerald-400` if 0

### 6.2 State 2: Domain Selected

Displayed when a domain node is clicked in the tree.

```
+------------------------------------------------------+
| core-api                                             |
+------------------------------------------------------+
|                                                      |
|  +-- Health Summary --+  +-- Summary Bar ----------+|
|  |  [HealthGauge md]  |  |  [HealthSummaryBar]     ||
|  |  94% Healthy       |  |  ██████████████░░░       ||
|  |                    |  |  47 passing | 2 failing  ||
|  |  49 tests total    |  |  | 0 skipped             ||
|  +--------------------+  +--------------------------+|
|                                                      |
|  Features in this domain                             |
|  +-------------------------------------------------+ |
|  | [dot] auth           92%  12 tests  1 failing   | |
|  | [dot] billing        96%  15 tests  0 failing   | |
|  | [dot] users          88%   8 tests  1 failing   | |
|  | [dot] notifications 100%  14 tests  0 failing   | |
|  +-------------------------------------------------+ |
|                                                      |
|  Integrity Alerts (2)                                |
|  +-------------------------------------------------+ |
|  | [ShieldAlert] Assert removed in abc1234         | |
|  | [ShieldX] Flaky test detected: test_timeout     | |
|  +-------------------------------------------------+ |
|                                                      |
+------------------------------------------------------+
```

#### Breadcrumb

- Position: Top of detail panel, `mb-6`
- Content: Just the domain name (single segment, no separator needed)
- Style: `text-lg font-semibold text-slate-100`
- Behavior: Clicking the breadcrumb when deeper (State 3/4) returns to this state

#### Health Summary Row

- **Layout**: `flex gap-6 items-start`
- **Left: HealthGauge**
  - Variant: `md` (80x80 SVG)
  - Data: aggregated pass rate for the domain
  - Below gauge: `text-sm text-slate-400 mt-2` showing "{total} tests total"
- **Right: HealthSummaryBar**
  - Full-width within its flex container (`flex-1`)
  - Shows pass/fail/skip/error breakdown for the entire domain
  - Text summary below bar per design system spec

#### Feature List

- **Section header**: "Features in this domain", `text-base font-semibold text-slate-200 mt-8 mb-4`
- **Feature cards**: Vertical stack with `space-y-2`
- **Each card**: `bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-800/50 transition-colors`
  - Left side: `flex items-center gap-3`
    - Health dot: `w-2 h-2 rounded-full` in health color
    - Feature name: `text-sm font-medium text-slate-200`
  - Right side: `flex items-center gap-4 text-xs text-slate-400`
    - Pass rate: `font-semibold` in health color
    - Test count: "{n} tests"
    - Failing count (if > 0): `text-rose-400` "{n} failing"
  - Click: transitions to State 3 with that feature selected

#### Integrity Alerts

- **Section header**: "Integrity Alerts ({count})", `text-base font-semibold text-slate-200 mt-8 mb-4`
  - Count badge: `text-xs bg-rose-500/12 text-rose-300 px-1.5 py-0.5 rounded ml-2` (only if count > 0)
- **Cards**: `IntegrityAlertCard` components from design system, `space-y-3`
- **Empty case**: If no alerts for domain, show positive empty state (see Section 9.5)

### 6.3 State 3: Feature Selected

Displayed when a feature node is clicked in the tree (or a feature card is clicked from State 2).

```
+------------------------------------------------------+
| core-api  >  auth  >  Login Feature                 |
+------------------------------------------------------+
| [Active filter chips: Passed, Failed]    [Clear all] |
+------------------------------------------------------+
|                                                      |
|  +-- Health -----+  +-- Summary Bar ---------------+|
|  | [Gauge lg]    |  |  [HealthSummaryBar]           ||
|  | 89% Healthy   |  |  ████████████░░               ||
|  |               |  |  9 passing | 1 failing        ||
|  | 10 tests      |  |  | 0 skipped                  ||
|  | Last: 2h ago  |  |                               ||
|  +---------------+  +-------------------------------+|
|                                                      |
|  Test Results                          [Search____]  |
|  +--------------------------------------------------+|
|  | NAME            STATUS    DURATION  ERROR         ||
|  |--------------------------------------------------|  |
|  | test_login_ok   [PASS]    120ms                   ||
|  | test_login_bad  [PASS]     45ms                   ||
|  | test_mfa_bypass [FAIL]    250ms     Assert...     ||
|  | test_sso_flow   [PASS]     89ms                   ||
|  | ...                                               ||
|  +--------------------------------------------------+|
|                                                      |
|  Integrity Alerts (1)                                |
|  +--------------------------------------------------+|
|  | [HIGH] Assert removed in abc1234 -- Session S-2   ||
|  +--------------------------------------------------+|
|                                                      |
+------------------------------------------------------+
```

#### Breadcrumb

- **Format**: `domain > feature_parent > feature_name` using `ChevronRight` (`size={14}`, `text-slate-600`) as separator
- **Each segment**: `text-sm text-slate-400 hover:text-indigo-400 cursor-pointer transition-colors`
- **Active segment** (last): `text-lg font-semibold text-slate-100` (not clickable)
- **Click behavior**: Clicking a breadcrumb segment navigates to that state (domain click goes to State 2)

#### Active Filter Chips

- **Position**: Below breadcrumb, `mt-2 mb-4`
- **Visibility**: Only shown when non-default filters are active
- **Each chip**: `inline-flex items-center gap-1 text-xs bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 rounded-full px-2.5 py-1 mr-2`
  - Close button: `XCircle` (`size={12}`), `text-indigo-400 hover:text-indigo-200 cursor-pointer`
  - Click close: removes that filter
- **Clear all**: `text-xs text-slate-500 hover:text-slate-300 cursor-pointer ml-2` -- "Clear all"

#### Health Summary Row

- **Layout**: `flex gap-6 items-start`
- **Left: HealthGauge**
  - Variant: `lg` (120x120 SVG)
  - Data: pass rate for this feature
  - Below gauge: two lines of `text-sm text-slate-400`
    - "{total} tests"
    - "Last run: {relative_time}" (e.g., "Last run: 2h ago")
- **Right: HealthSummaryBar**
  - `flex-1` width
  - Shows pass/fail/skip/error breakdown for this feature only
  - Includes error and xfail/xpass counts if present

#### Test Results Table (TestResultTable)

- **Section header row**: `flex items-center justify-between mt-8 mb-4`
  - Left: "Test Results", `text-base font-semibold text-slate-200`
  - Right: Search input
    - `bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 px-3 py-1.5 w-64`
    - `Search` icon (`size={14}`) inside input at left
    - Placeholder: "Search tests..."
    - Filters test names client-side (instant, no debounce needed)

- **Table structure**: Semantic HTML `<table>` element

  | Column | Header Text | Width | Alignment | Sort |
  |--------|-------------|-------|-----------|------|
  | Test Name | NAME | flex / remaining | left | alphabetical |
  | Status | STATUS | 100px | center | by priority order |
  | Duration | DURATION | 100px | right | numeric |
  | Error Preview | ERROR | 200px min | left | none |

- **Table header row**: `text-xs font-medium text-slate-500 uppercase tracking-wider border-b border-slate-800 pb-2`

- **Table body rows**: Each row is:
  - Container: `border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors`
  - Test Name cell: `text-sm font-mono text-slate-300 py-3`
  - Status cell: `TestStatusBadge` component, `md` size
  - Duration cell: `text-sm text-slate-400 tabular-nums` (right-aligned). Format: ms for < 1s, `{n.n}s` for >= 1s
  - Error Preview cell: `text-sm text-slate-500 truncate max-w-[200px]` -- first line of `error_message`, or empty if passed

- **Row expansion** (click a row):
  - The row expands downward to show full error details
  - Expansion area: `bg-slate-900/50 px-4 py-3 border-l-2 border-rose-500/30`
  - Full error message: `text-sm font-mono text-rose-300 whitespace-pre-wrap`
  - Stack trace (if present): `text-xs font-mono text-slate-500 mt-2 max-h-48 overflow-y-auto`
  - Close: click the row again, or press `Escape`
  - Only one row can be expanded at a time

- **Sorting**: Click column header to sort. Active sort column header gets `text-slate-300` and a sort direction indicator (`ChevronUp`/`ChevronDown`, `size={12}`). Default sort: failed first (status priority), then alphabetical.

- **Empty table state**: "No test results match your filters" with `text-sm text-slate-500 italic text-center py-8`

#### Integrity Alerts

Same structure as State 2 but filtered to the selected feature.

### 6.4 State 4: Individual Test Selected

Displayed when a user clicks a test row in State 3 and wants the full detail view (accessible via a "View details" link in the expanded row, or by double-clicking the row).

```
+------------------------------------------------------+
| core-api  >  auth  >  Login  >  test_mfa_bypass     |
+------------------------------------------------------+
|                                                      |
|  +-- Test Result Detail ----+                        |
|  | Status: [FAIL badge lg]  |  Duration: 250ms      |
|  | Run: run-abc123          |  Branch: feat/auth     |
|  | Session: session-xyz     |  Timestamp: 2h ago     |
|  +--------------------------+                        |
|                                                      |
|  Error Message                                       |
|  +--------------------------------------------------+|
|  | AssertionError: expected 403, got 200             ||
|  |                                                   ||
|  | File: tests/auth/test_login.py:47                 ||
|  | in test_mfa_bypass                                ||
|  |   assert response.status_code == 403              ||
|  +--------------------------------------------------+|
|                                                      |
|  Run History                                         |
|  +--------------------------------------------------+|
|  | [PASS]  run-789  3h ago   120ms  feat/auth        ||
|  | [FAIL]  run-abc  2h ago   250ms  feat/auth        ||
|  | [PASS]  run-def  1d ago    98ms  main             ||
|  | [PASS]  run-ghi  2d ago   105ms  main             ||
|  | [PASS]  run-jkl  3d ago   112ms  main             ||
|  +--------------------------------------------------+|
|                                                      |
|  Related Sessions                                    |
|  +--------------------------------------------------+|
|  | [Terminal] session-xyz  feat/auth  2h ago  [Link] ||
|  | [Terminal] session-abc  main       1d ago  [Link] ||
|  +--------------------------------------------------+|
|                                                      |
+------------------------------------------------------+
```

#### Breadcrumb

- Four segments: domain > feature_parent > feature > test_name
- Test name (last segment): `text-lg font-semibold text-slate-100 font-mono`

#### Test Result Detail Card

- **Container**: `bg-slate-900 border border-slate-800 rounded-xl p-5`
- **Layout**: CSS grid, 2 columns, 3 rows
- **Fields**:
  - Status: `TestStatusBadge` `lg` variant
  - Duration: `text-sm text-slate-300` with `Clock` icon (`size={14}`, `text-slate-500`)
  - Run ID: `text-sm font-mono text-slate-400` (truncated to first 8 chars)
  - Branch: `text-sm text-slate-300` with git branch icon
  - Session: `text-sm font-mono text-indigo-400 hover:underline cursor-pointer` -- links to `/sessions?id={session_id}`
  - Timestamp: `text-sm text-slate-400` -- relative time

#### Error Message Section

- **Section header**: "Error Message", `text-base font-semibold text-slate-200 mt-6 mb-3`
- **Container**: `bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-sm`
- **Error text**: `text-rose-300 whitespace-pre-wrap`
- **Stack trace**: `text-slate-500 mt-3 border-t border-slate-800 pt-3`
- **File path**: `text-slate-400` with the file:line reference, clickable if codebase explorer supports it
- **Copy button**: Top-right corner of container, `text-slate-500 hover:text-slate-300`, copies full error + stack trace to clipboard

#### Run History Section

- **Section header**: "Run History", `text-base font-semibold text-slate-200 mt-6 mb-3`
- **List**: Vertical stack of recent runs for this specific test definition
- **Each row**: `flex items-center gap-4 py-2.5 border-b border-slate-800/50 text-sm`
  - `TestStatusBadge` `sm` variant
  - Run ID: `font-mono text-slate-400` (first 8 chars)
  - Relative time: `text-slate-500`
  - Duration: `text-slate-400 tabular-nums`
  - Branch: `text-slate-500`
- **Maximum**: Show last 10 runs. If more exist, show "View all runs" link at bottom.
- **Visual indicator**: The current run (the one being viewed) has `bg-indigo-500/5 rounded` highlight

#### Related Sessions

- **Section header**: "Related Sessions", `text-base font-semibold text-slate-200 mt-6 mb-3`
- **Each row**: `flex items-center gap-3 py-2.5 border-b border-slate-800/50`
  - `Terminal` icon (`size={14}`, `text-slate-500`)
  - Session ID: `text-sm font-mono text-indigo-400 hover:underline cursor-pointer`
  - Branch: `text-xs text-slate-500`
  - Relative time: `text-xs text-slate-500`
  - Link arrow: `ChevronRight` (`size={14}`, `text-slate-600`)
- **Click**: Navigates to `/sessions?id={session_id}` (opens Session Forensics page)

---

## 7. Transitions Between States

All state transitions use coordinated animations to maintain spatial context.

### Forward Drill-Down (State N to State N+1)

1. Current detail panel content fades out: `opacity 1 -> 0` over 150ms, `ease-out`
2. Brief 50ms pause (allows DOM to update)
3. New content slides in from the right: `translateX(24px) -> translateX(0)` + `opacity 0 -> 1` over 200ms, `ease-out`

### Backward Navigation (State N to State N-1)

1. Current content fades out: `opacity 1 -> 0` over 150ms
2. New content slides in from the left: `translateX(-24px) -> translateX(0)` + `opacity 0 -> 1` over 200ms

### Breadcrumb Updates

- New breadcrumb segments slide in from the right on drill-down
- Removed segments fade out on backward navigation
- Timing: 150ms, synchronized with panel content transition

### Tree Selection Highlight

- Old selection: `bg-indigo-500/10` fades out over 150ms
- New selection: `bg-indigo-500/10` fades in over 150ms
- The tree auto-expands parent nodes if a child is selected via URL param

### Reduced Motion

When `prefers-reduced-motion: reduce` is active:
- All transitions become instant (0ms duration)
- No slide transforms, only opacity changes (or no opacity changes)

---

## 8. Loading States

### 8.1 Initial Page Load

Full skeleton layout displayed while the first data fetch completes.

```
+-------------------------------------------------------------------+
| [pulse bar 120px]                    [pulse circle 56px]          |
+-------------------------------------------------------------------+
| [pulse bar 180px h-6]    | [pulse block full-width h-32]         |
| [pulse bar 140px h-6]    |                                        |
| [pulse bar 160px h-6]    | [pulse block full-width h-16]         |
| [pulse bar 120px h-6]    | [pulse block full-width h-16]         |
| [pulse bar 150px h-6]    | [pulse block full-width h-16]         |
|                           |                                        |
+---------------------------+----------------------------------------+
```

- **Header skeleton**: Pulse animation bar for title (120px width) + circle for gauge (56px diameter)
- **Sidebar skeleton**: 5 rows of pulse bars with varying widths (120-180px), `h-6`, `rounded`, `bg-slate-800 animate-pulse`
- **Detail panel skeleton**: One large block (h-32) for health summary + three medium blocks (h-16) for content cards
- **Skeleton base class**: `bg-slate-800 animate-pulse rounded`

### 8.2 Domain Tree Loading

When tree data is being fetched (initial load or refresh):

- 5 placeholder rows: `h-7 rounded bg-slate-800 animate-pulse mx-2 mb-2`
- Widths alternate: 180px, 140px, 160px, 120px, 150px (to suggest varying node name lengths)

### 8.3 Detail Panel Transition Loading

When switching between states (e.g., selecting a different feature):

1. Old content fades out (150ms)
2. Skeleton appears for the new content type:
   - State 2 skeleton: gauge placeholder + 3 feature card placeholders
   - State 3 skeleton: gauge placeholder + 5 table row placeholders
   - State 4 skeleton: detail card placeholder + error block placeholder + 5 history row placeholders
3. Skeleton replaced by real content with fade-in (150ms)

### 8.4 Table Loading

When the test results table is loading (filter change, page change):

- Table header remains visible (not replaced by skeleton)
- 5 skeleton rows matching column widths:
  ```
  | [bar 160px] | [bar 60px] | [bar 50px] | [bar 120px] |
  ```
- Each bar: `h-4 rounded bg-slate-800 animate-pulse`
- Rows spaced with `py-3` to match real row height

### 8.5 Refresh Loading

When the refresh button is clicked:

- `RefreshCcw` icon gets `animate-spin` class
- No skeleton replacement -- existing data stays visible
- Data updates in-place when fetch completes
- If fetch takes > 5 seconds, show subtle toast: "Still loading..." in `text-xs text-slate-500`

---

## 9. Empty States

All empty states follow a consistent layout pattern: centered content with icon, title, description, and optional action button.

### 9.1 No Tests Ingested

**Trigger**: API returns zero test runs and zero test definitions.

```
+------------------------------------------+
|                                          |
|        [FlaskConical size={48}           |
|         text-slate-700]                  |
|                                          |
|     No test data available               |
|                                          |
|     Test results have not been           |
|     ingested yet. Configure your         |
|     JUnit XML path to get started.       |
|                                          |
|     [Configure Test Ingestion]           |
|                                          |
+------------------------------------------+
```

- **Icon**: `FlaskConical`, `size={48}`, `text-slate-700`
- **Title**: "No test data available", `text-base font-medium text-slate-400 mt-4`
- **Description**: `text-sm text-slate-500 mt-2 max-w-sm text-center`
- **Action**: Primary button linking to settings/setup documentation
  - `bg-indigo-500 hover:bg-indigo-400 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors`

### 9.2 No Domain Mappings

**Trigger**: Test data exists but no domain/feature mappings are configured.

- **Icon**: `FolderTree`, `size={48}`, `text-slate-700`
- **Title**: "No test mappings configured"
- **Description**: "Tests have been ingested but no domain or feature mappings exist. Create a mapping configuration to organize tests into domains and features."
- **Action**: "Configure Mappings" button

### 9.3 Feature Flag Disabled

**Trigger**: The test visualizer feature flag is not enabled in project settings.

- **Icon**: `TestTube2`, `size={48}`, `text-slate-700`
- **Title**: "Test Visualizer is not enabled"
- **Description**: "This feature is currently disabled for this project. Enable it in project settings to start visualizing test results."
- **Action**: "Go to Settings" button linking to `/settings`

### 9.4 Filter Yields No Results

**Trigger**: Active filters produce zero matching test results.

- **Icon**: `Search`, `size={48}`, `text-slate-700`
- **Title**: "No matching tests"
- **Description**: "No test results match your current filters. Try adjusting your filter criteria."
- **Action**: "Clear all filters" text button (not primary styled)
  - `text-indigo-400 hover:text-indigo-300 text-sm font-medium cursor-pointer`

### 9.5 No Integrity Signals (Positive)

**Trigger**: Feature or domain has test data but zero integrity signals.

- **Icon**: `ShieldCheck` (Lucide), `size={32}`, `text-emerald-500/50`
- **Title**: "No integrity issues detected"
- **Description**: "All tests in this scope appear structurally sound. No removed assertions, flaky patterns, or coverage drops detected."
- **Styling**: This is a positive confirmation, so it uses muted emerald tones rather than the neutral slate of error empty states.
  - Container: `bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 text-center`
  - Title: `text-sm font-medium text-emerald-400`
  - Description: `text-xs text-emerald-500/70`

---

## 10. Responsive Behavior

### Breakpoint: 1440px and Above (Full Desktop)

- Layout as specified in all sections above
- Sidebar: 280px
- Detail panel: remaining width
- All features visible

### Breakpoint: 1024px - 1439px (Narrow Desktop)

- Sidebar narrows to 240px
- Detail panel adapts (it uses flex-1, so this is automatic)
- Test result table: Error Preview column hidden (columns: Name, Status, Duration only)
- Health summary row stacks vertically if panel width < 500px

### Breakpoint: 768px - 1023px (Tablet)

- Domain tree sidebar collapses to icon-only mode:
  - Width: 48px
  - Shows only health-colored dots for each domain (no text)
  - On hover, shows tooltip with domain name + health %
  - Click expands sidebar as an overlay (positioned absolute, `z-30`, with backdrop)
- Detail panel takes full remaining width
- Test result table: Error Preview column hidden
- Health gauge downsized from `lg` to `md`

### Breakpoint: Below 768px (Mobile)

- Domain tree sidebar fully hidden
- Hamburger toggle button in header bar (left side, replacing the title text)
  - `Menu` icon (`size={20}`), opens sidebar as full-screen overlay
  - Overlay: `fixed inset-0 z-40 bg-slate-950/95 backdrop-blur-sm`
  - Close button: `X` icon in top-right of overlay
- Detail panel takes full width with reduced padding: `p-4` instead of `p-6`
- Health summary: gauge and bar stack vertically (`flex-col`)
- Breadcrumb: truncates middle segments with ellipsis if more than 2 segments

### Breakpoint: Below 640px (Small Mobile)

- Test result table switches to card layout:
  ```
  +--------------------------------------+
  | test_login_valid              [PASS]  |
  | Duration: 120ms                      |
  +--------------------------------------+
  | test_mfa_bypass               [FAIL]  |
  | Duration: 250ms                      |
  | Error: AssertionError: expected...   |
  +--------------------------------------+
  ```
  - Each card: `bg-slate-900 border border-slate-800 rounded-xl p-3 mb-2`
  - Test name: `text-sm font-mono text-slate-200`
  - Status badge: `TestStatusBadge sm`, positioned top-right
  - Duration: `text-xs text-slate-500`
  - Error preview (if failed): `text-xs text-rose-400 mt-1 line-clamp-2`

- Quick stats cards (State 1): stack vertically (`flex-col`)
- Feature cards (State 2): full width, no min-width constraints

---

## 11. ASCII Wireframes

### 11.1 Full Page Layout (1440px viewport)

This wireframe shows the complete Testing Page as it appears within the CCDash shell at a 1440px viewport width. The CCDash global sidebar (Layout.tsx) is shown on the far left for context.

```
+----+------------------------------------------------------------+
|    |                                                            |
| C  | [TestTube2] Test Visualizer    [Gauge 87%]  1,234 tests   |
| C  |                                23 failing   Last: 2m [R]  |
| D  +------------------+-------------------------------------------+
| a  | DOMAIN TREE      | DETAIL PANEL                              |
| s  |                  |                                            |
| h  | v core-api  94%  | core-api > auth > Login Feature            |
|    |   > auth    92%  |                                            |
| S  |   > billing 96%  | +-- Health ----+  +-- Bar ---------------+ |
| i  |   > users   88%  | | [Gauge lg]   |  | ████████████░░       | |
| d  | > payments  71%  | | 89% Healthy  |  | 9 pass | 1 fail     | |
| e  | > notif    100%  | | 10 tests     |  | | 0 skipped          | |
| b  |                  | | Last: 2h ago |  |                      | |
| a  |                  | +--------------+  +----------------------+ |
| r  |                  |                                            |
|    | -- FILTERS --    | Test Results                    [Search_] |
|    | [x] Passed       | +----------------------------------------+ |
|    | [x] Failed       | | NAME             STATUS  DUR   ERROR    | |
|    | [ ] Skipped      | |----------------------------------------| |
|    | [ ] Error        | | test_login_ok    [PASS]  120ms          | |
|    |                  | | test_login_bad   [PASS]   45ms          | |
|    | Run: [All Runs]  | | test_mfa_bypass  [FAIL]  250ms Assert..| |
|    | Branch: [______] | | test_sso_flow    [PASS]   89ms          | |
|    | Session: [______] | +----------------------------------------+ |
|    |                  |                                            |
|    |                  | Integrity Alerts (1)                       |
|    |                  | +----------------------------------------+ |
|    |                  | | [!] Assert removed in abc1234  Sess S-2 | |
|    |                  | +----------------------------------------+ |
+----+------------------+--------------------------------------------+
```

### 11.2 Domain Tree Expanded State

Shows the tree with one domain expanded and one feature selected.

```
+-------------------------------+
| DOMAIN TREE                   |
|-------------------------------|
| v core-api              94%  |
| |  [*] auth             92%  |  <-- selected (indigo highlight)
| |  [ ] billing           96%  |
| |  [ ] users             88%  |
| > payments              71%  |  <-- collapsed
| > notifications        100%  |
|-------------------------------|
| TEST FILTERS                  |
|                               |
| Status                        |
| [x] Passed                    |
| [x] Failed                    |
| [ ] Skipped                   |
| [ ] Error                     |
|                               |
| Run                           |
| +---------------------------+ |
| | All Runs              [v] | |
| +---------------------------+ |
|                               |
| Branch                        |
| +---------------------------+ |
| | Filter by branch...      | |
| +---------------------------+ |
|                               |
| Session                       |
| +---------------------------+ |
| | Session ID...             | |
| +---------------------------+ |
+-------------------------------+

Legend:
  v = expanded (ChevronDown)
  > = collapsed (ChevronRight)
  [*] = selected node (indigo bg)
  [ ] = unselected leaf node
  [x] = checked checkbox
  [ ] = unchecked checkbox
  [v] = dropdown arrow
```

### 11.3 Detail Panel at Feature Level (State 3)

Isolated view of the detail panel content when a feature is selected.

```
+--------------------------------------------------------------+
| core-api  >  auth  >  Login Feature                          |
+--------------------------------------------------------------+
| [Passed x] [Failed x]                         [Clear all]   |
+--------------------------------------------------------------+
|                                                              |
| +--- Health ------+   +--- Summary Bar ---------------------+|
| |                 |   |                                      ||
| |   /-------\     |   |  ██████████████████░░                ||
| |  |  89%    |    |   |                                      ||
| |   \-------/     |   |  9 passing  |  1 failing  |  0 skip ||
| |   Healthy       |   |                                      ||
| |                 |   +--------------------------------------+|
| |  10 tests       |                                          |
| |  Last: 2h ago   |                                          |
| +-----------------+                                          |
|                                                              |
| Test Results                                    [Search____] |
| +------------------------------------------------------------+
| | NAME                  | STATUS   | DURATION | ERROR        |
| |------------------------------------------------------------|
| | test_login_valid      | [PASS]   | 120ms    |              |
| | test_login_invalid    | [PASS]   |  45ms    |              |
| | test_mfa_bypass       | [FAIL]   | 250ms    | Assert...    |
| |   +-- Expanded Error Detail ----------------------------+  |
| |   | AssertionError: expected 403, got 200               |  |
| |   |                                                     |  |
| |   | File: tests/auth/test_login.py:47                   |  |
| |   |   assert response.status_code == 403                |  |
| |   +-----------------------------------------------------+  |
| | test_sso_flow         | [PASS]   |  89ms    |              |
| | test_password_reset   | [PASS]   |  67ms    |              |
| | test_session_expire   | [PASS]   | 134ms    |              |
| | test_rate_limiting    | [PASS]   | 210ms    |              |
| | test_token_refresh    | [PASS]   |  56ms    |              |
| | test_logout           | [PASS]   |  38ms    |              |
| +------------------------------------------------------------+
|                                                              |
| Integrity Alerts (1)                                         |
| +------------------------------------------------------------+
| | [ShieldAlert] Assert removed in commit abc1234             |
| | File: tests/auth/test_login.py                             |
| | Session: session-xyz  |  2 hours ago         [View Sess >]|
| +------------------------------------------------------------+
|                                                              |
| +-- No further integrity issues ----------------------------+|
| |  [ShieldCheck] No integrity issues detected                ||
| |  All tests appear structurally sound.                      ||
| +------------------------------------------------------------+|
+--------------------------------------------------------------+
```

### 11.4 Mobile Layout (375px viewport)

Shows the Testing Page on a small mobile device. The global sidebar and domain tree are hidden behind a hamburger menu.

```
+-----------------------------------+
| [=] Test Visualizer     [R]      |
+-----------------------------------+
| core-api > auth > Login           |
| [Passed x] [Failed x] [Clear]   |
+-----------------------------------+
|                                   |
|  +-- Health --+                   |
|  | /------\   |                   |
|  || 89%   |   |                   |
|  | \------/   |                   |
|  | Healthy    |                   |
|  +------------+                   |
|                                   |
|  ██████████████████░░             |
|  9 pass | 1 fail | 0 skip        |
|                                   |
|  [Search_____________________]   |
|                                   |
|  +-------------------------------+|
|  | test_login_valid       [PASS] ||
|  | Duration: 120ms               ||
|  +-------------------------------+|
|  | test_login_invalid     [PASS] ||
|  | Duration: 45ms                ||
|  +-------------------------------+|
|  | test_mfa_bypass        [FAIL] ||
|  | Duration: 250ms               ||
|  | AssertionError: expected...   ||
|  +-------------------------------+|
|  | test_sso_flow          [PASS] ||
|  | Duration: 89ms                ||
|  +-------------------------------+|
|                                   |
|  Integrity Alerts (1)            |
|  +-------------------------------+|
|  | [!] Assert removed abc1234   ||
|  | tests/auth/test_login.py     ||
|  +-------------------------------+|
|                                   |
+-----------------------------------+

Legend:
  [=] = hamburger menu (opens sidebar overlay)
  [R] = refresh button
```

---

## 12. Data Flow Summary

This section maps each UI element to its API endpoint for developer reference.

| UI Element | API Endpoint | Response DTO | Poll Interval |
|-----------|-------------|-------------|---------------|
| Header health gauge | `GET /api/tests/health/global` | `HealthRollupDTO` | Manual refresh only |
| Header test count | `GET /api/tests/health/global` | `HealthRollupDTO` | Manual refresh only |
| Domain tree | `GET /api/tests/health/domains` | `DomainHealthRollupDTO[]` | Manual refresh only |
| Domain detail (State 2) | `GET /api/tests/health/domains/{id}` | `DomainHealthRollupDTO` | On selection |
| Feature detail (State 3) | `GET /api/tests/health/features/{slug}` | `FeatureHealthRollupDTO` | On selection |
| Test results table | `GET /api/tests/results?feature={slug}&status={}&run_id={}` | `TestResultDTO[]` | On filter change |
| Integrity alerts | `GET /api/tests/integrity?scope={domain\|feature}&id={id}` | `TestIntegritySignalDTO[]` | On selection |
| Test run history (State 4) | `GET /api/tests/results?test_def_id={id}&limit=10` | `TestResultDTO[]` | On selection |
| Branch autocomplete | `GET /api/tests/branches` | `string[]` | On filter panel mount |
| Last updated timestamp | Derived from most recent `TestRunDTO.started_at` in cached data | -- | 60s interval |

---

## 13. URL Query Parameter Schema

All filter and navigation state is serialized to URL query parameters for shareability and browser back/forward support.

| Parameter | Type | Example | Maps To |
|-----------|------|---------|---------|
| `domain` | string | `?domain=core-api` | Selected domain in tree (State 2+) |
| `feature` | string | `?feature=auth-login` | Selected feature (State 3+) |
| `test` | string | `?test=test_mfa_bypass` | Selected test (State 4) |
| `status` | comma-separated | `?status=passed,failed` | Status filter checkboxes |
| `run_id` | string | `?run_id=latest` | Run filter dropdown |
| `branch` | string | `?branch=feat/auth` | Branch filter input |
| `session` | string | `?session=session-xyz` | Session filter input |
| `sort` | string | `?sort=status` | Active sort column |
| `sort_dir` | `asc` or `desc` | `?sort_dir=desc` | Sort direction |

**Behavior**:
- On page load, URL params are read and used to restore state (expand tree, select nodes, apply filters).
- On any state change (selection, filter, sort), URL is updated via `window.history.replaceState` (no full navigation).
- The `domain` param auto-expands that domain in the tree. The `feature` param auto-selects that feature. Both together jump directly to State 3.

---

## 14. Keyboard Navigation Map

| Context | Key | Action |
|---------|-----|--------|
| Domain Tree | `ArrowDown` | Move focus to next visible node |
| Domain Tree | `ArrowUp` | Move focus to previous visible node |
| Domain Tree | `ArrowRight` | Expand collapsed domain / move to first child |
| Domain Tree | `ArrowLeft` | Collapse expanded domain / move to parent |
| Domain Tree | `Enter` | Select focused node (update detail panel) |
| Domain Tree | `Home` | Move focus to first node |
| Domain Tree | `End` | Move focus to last visible node |
| Test Results Table | `ArrowDown` | Move focus to next row |
| Test Results Table | `ArrowUp` | Move focus to previous row |
| Test Results Table | `Enter` | Expand/collapse error details for focused row |
| Test Results Table | `Escape` | Collapse expanded row / deselect test |
| Detail Panel | `Escape` | Navigate up one level in state machine |
| Filter inputs | `Escape` | Close autocomplete dropdown |
| Global | `Tab` | Standard focus traversal |
| Refresh button | `Enter` / `Space` | Trigger data refresh |

**Focus management**: When the detail panel transitions between states, focus moves to the first heading element in the new content. This ensures screen reader users are oriented after a state change.

---

## 15. Implementation Notes for Developers

### Component Hierarchy

```
TestVisualizerPage
  +-- TestVisualizerHeader
  |     +-- HealthGauge (sm)
  +-- TestVisualizerBody (flex row)
        +-- DomainTreeSidebar
        |     +-- DomainTreeView
        |     +-- TestFilterPanel (rendered via portal to #sidebar-portal)
        +-- DetailPanel
              +-- DetailPanelEmpty (State 1)
              +-- DomainDetailView (State 2)
              |     +-- HealthGauge (md)
              |     +-- HealthSummaryBar
              |     +-- FeatureCardList
              |     +-- IntegrityAlertList
              +-- FeatureDetailView (State 3)
              |     +-- Breadcrumb
              |     +-- FilterChipBar
              |     +-- HealthGauge (lg)
              |     +-- HealthSummaryBar
              |     +-- TestResultTable
              |     +-- IntegrityAlertList
              +-- TestDetailView (State 4)
                    +-- Breadcrumb
                    +-- TestResultDetailCard
                    +-- ErrorMessageBlock
                    +-- RunHistoryList
                    +-- RelatedSessionsList
```

### State Management

- **Selection state** (which domain/feature/test is selected): Managed via URL query params + local component state derived from URL.
- **Filter state**: Managed via URL query params. A `useTestFilters()` hook reads and writes filter state.
- **Tree expand/collapse state**: Local component state (not persisted to URL since it is a UI concern, not a data concern).
- **Data fetching**: Use the existing pattern from DataContext -- `useEffect` hooks that trigger fetches when selection or filter state changes.

### Performance Considerations

- Domain tree data should be fetched once on mount and cached. Refresh button re-fetches.
- Detail panel data is fetched on demand when selection changes. Previous data can be cached for back-navigation.
- Test results table supports up to 500 rows without virtualization. For features with more tests, implement cursor-based pagination (fetch 50 at a time, "Load more" button).
- Filter debounce (300ms) prevents rapid-fire API calls during typing.

### Accessibility Checklist

- [ ] `role="tree"` on domain tree, `role="treeitem"` on nodes
- [ ] `aria-expanded` on expandable domain nodes
- [ ] `aria-selected` on selected tree node
- [ ] Semantic `<table>` with `<thead>`, `<tbody>`, `<th scope="col">`
- [ ] `role="meter"` on HealthGauge with proper aria attributes
- [ ] `role="img"` on HealthSummaryBar with descriptive aria-label
- [ ] Focus management on state transitions
- [ ] `prefers-reduced-motion` respected for all animations
- [ ] All interactive elements keyboard-operable
- [ ] Focus ring style: `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900`
