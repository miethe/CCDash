---
title: "Test Status Tab Designs"
doc_type: design
feature_slug: test-visualizer
created: 2026-02-28
updated: 2026-02-28
---

# Test Status Tab Designs

## 1. Overview

The "Test Status" tab surfaces test health data in three distinct locations within CCDash. Each location serves a different user intent and operates at a different information density. This document specifies the layout, content, states, and behavior for all three tab instances.

All visual tokens (colors, icons, badge classes, typography) reference the Test Visualizer Design System (`design-system.md`). This document does not redefine those tokens -- it specifies how they compose into tab layouts.

### Tab Identity (Shared Across All Locations)

| Property | Value |
|----------|-------|
| Icon | `TestTube2` from `lucide-react`, `size={16}` in the tab bar |
| Label | "Test Status" |
| Position | After existing tabs, before Settings tab if one exists |
| Color scheme | Follows `design-system.md` status colors throughout |

---

## 2. Feature Modal "Test Status" Tab

### Context

This tab appears inside the Feature Modal rendered by `ProjectBoard.tsx`. The modal uses the `FeatureModalTab` union type for its tab system. The "Test Status" tab is appended to that union.

### Visibility Rule

The tab is rendered in the tab bar **only** when `feature.test_health !== null`. When `test_health` is null (no tests mapped to this feature), the tab is hidden entirely -- no disabled state, no placeholder, simply absent from the tab list.

### Layout Specification

The modal content area is approximately 600px wide. The tab content must remain compact and scannable.

```
+----------------------------------------------------------------------+
|  [Overview]  [Sessions]  [Test Status]  [Links]                      |
+----------------------------------------------------------------------+
|                                                                      |
|  +--[HealthGauge sm]--+  9 passing  |  1 failing  |  0 skipped      |
|  |       89%          |                                              |
|  +--------------------+  Last run: 2h ago  *  Branch: feat/my-feat   |
|                                                                      |
|  ---- divider (border-t border-slate-800 my-4) ----                  |
|                                                                      |
|  Recent Failures                                          (heading)  |
|                                                                      |
|  [XCircle] test_mfa_bypass ........... [FAIL badge]                  |
|            assertion_removed signal                                  |
|                                                                      |
|  [XCircle] test_checkout_edge ........ [FAIL badge]                  |
|            timeout after 30s                                         |
|                                                                      |
|  ---- divider ----                                                   |
|                                                                      |
|  [ShieldX amber] 1 alert (medium severity)                           |
|                                                                      |
|  ---- divider ----                                                   |
|                                                                      |
|  View Full Test Status ->                          (indigo-400 link) |
|                                                                      |
+----------------------------------------------------------------------+
```

### Section Breakdown

#### Header Row

Layout: `flex items-center gap-4`

| Element | Specification |
|---------|---------------|
| HealthGauge | `sm` variant (56x56px), score from `feature.test_health` |
| Stats text | `text-sm text-slate-400`, counts colored per status: `<span class="text-emerald-400">9</span> passing <span class="text-slate-600">\|</span> <span class="text-rose-400">1</span> failing <span class="text-slate-600">\|</span> <span class="text-amber-400">0</span> skipped` |

#### Metadata Row

Layout: `text-xs text-slate-500 mt-1`

Content: `Last run: {relative_time} * Branch: {branch_name}`

Separator: `<span class="text-slate-700 mx-1">*</span>`

#### Recent Failures Section

Condition: Rendered only when `failed_count > 0`.

Heading: `text-sm font-semibold text-slate-200 mb-2` -- "Recent Failures"

List: Up to 3 most recent failing tests. Each entry is a row:

```
Layout: flex items-start gap-2 py-1.5
  [XCircle size={14} class="text-rose-500 mt-0.5 shrink-0"]
  <div class="flex-1 min-w-0">
    <div class="flex items-center justify-between gap-2">
      <span class="text-sm text-slate-300 truncate font-mono">{test_name}</span>
      [TestStatusBadge status="failed" size="sm"]
    </div>
    <span class="text-xs text-slate-500 truncate block">{failure_reason or signal_type}</span>
  </div>
```

If more than 3 failures exist, show a muted link below the list: `text-xs text-slate-500` -- "+{n} more failures"

#### Integrity Summary

Layout: `flex items-center gap-2`

Content: `[ShieldX size={16} class="text-amber-500"] <span class="text-sm text-slate-300">{count} alert(s) ({highest_severity} severity)</span>`

Condition: Rendered only when integrity alerts exist for this feature.

Icon selection follows severity of the highest-priority alert:
- `high`: `ShieldAlert` in `text-rose-500`
- `medium`: `ShieldX` in `text-amber-500`
- `low`: `Shield` in `text-slate-400`

#### Action Link

Layout: `mt-4 flex justify-end`

Link: `text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer flex items-center gap-1`

Content: `View Full Test Status` + `ChevronRight size={14}`

Behavior: Navigates to the Execution Page with the Test Status tab pre-selected for this feature.

### States

#### Loading State

Skeleton layout matching the header row and section structure:

```
+----------------------------------------------------------------------+
|  [circle skeleton 56x56 pulse]  [bar skeleton w-48 h-4 pulse]       |
|                                  [bar skeleton w-32 h-3 pulse]       |
|                                                                      |
|  [bar skeleton w-full h-3 pulse]                                     |
|  [bar skeleton w-3/4 h-3 pulse]                                      |
+----------------------------------------------------------------------+
```

Skeleton classes: `bg-slate-800 rounded animate-pulse`

#### All Tests Passing (No Failures)

The "Recent Failures" section is replaced with a success message:

```
Layout: flex items-center gap-2 py-3
  [CheckCircle2 size={18} class="text-emerald-500"]
  <span class="text-sm text-emerald-400 font-medium">All tests passing</span>
```

#### No Test Data (Tab Hidden)

When `feature.test_health === null`, the tab does not appear in the tab bar. No empty state needed within the tab content since the tab itself is never rendered.

---

## 3. Execution Page "Test Status" Tab

### Context

This tab appears in the `FeatureExecutionWorkbench.tsx` workbench panel. It is added to the `WorkbenchTab` union type. The workbench panel is full-width within its container, giving this tab significantly more room than the modal variant.

The tab content is scoped to the currently selected feature in the execution workbench.

### Live vs Historical Modes

The tab operates in two modes based on session state:

| Mode | Condition | Polling | Visual Indicators |
|------|-----------|---------|-------------------|
| **Live** | `session.status === 'running'` | Every 30 seconds | Pulsing indigo dot, "LIVE" badge, indigo border glow on panel |
| **Historical** | `session.status !== 'running'` | None | Static timestamp, no glow |

### Layout Specification (Full Width)

```
+----------------------------------------------------------------------+
|  [Overview]  [Code]  [Logs]  [Test Status]                          |
+======================================================================+
|                                                                      |
|  +--- Live Indicator Bar (live mode only) -----------------------+  |
|  |  [pulsing indigo dot]  LIVE   Last run: 30s ago               |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
|  +--- Health Section ----+  +--- Summary Bar (full width) ------+  |
|  |  [HealthGauge md 80px]|  |  ████████████░░░░                  |  |
|  |        89%            |  |  9 passing | 1 failing | 0 skipped |  |
|  |      Degraded         |  +------------------------------------+  |
|  +-----------------------+                                          |
|                             [RefreshCcw] Refresh   [->] View /tests |
|                                                                      |
|  ================================================================== |
|                                                                      |
|  Test Run History                                    [ChevronDown]  |
|  +---------------------------------------------------------------+  |
|  |  [v] Run abc123   2h ago   94% pass   Session S-1   [->]     |  |
|  |  [ ] Run def456   1d ago   87% pass   Session S-2   [->]     |  |
|  |  [ ] Run ghi789   3d ago   91% pass   Session S-3   [->]     |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
|  ================================================================== |
|                                                                      |
|  Test Results (Latest Run)                                          |
|  +---------------------------------------------------------------+  |
|  |  [All] [Passing] [Failing] [Skipped] [Error]    [Search....]  |  |
|  +---------------------------------------------------------------+  |
|  |  STATUS     TEST NAME             DURATION   FILE             |  |
|  |  --------   --------------------  --------   ---------------  |  |
|  |  [PASS]     test_login_valid      120ms      tests/auth/..   |  |
|  |  [FAIL]     test_mfa_bypass       250ms      tests/auth/..   |  |
|  |             > AssertionError: expected True...                |  |
|  |  [PASS]     test_logout           85ms       tests/auth/..   |  |
|  |  [SKIP]     test_sso_flow         --         tests/auth/..   |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
|  ================================================================== |
|                                                                      |
|  Integrity Alerts                                                    |
|  +---------------------------------------------------------------+  |
|  |  [HIGH rose left-border] Assert removed in abc1234            |  |
|  |  test_mfa_bypass * Session S-2 * Detected 2h ago             |  |
|  +---------------------------------------------------------------+  |
|  +---------------------------------------------------------------+  |
|  |  [MED amber left-border] Flaky test detected                  |  |
|  |  test_checkout * Failed 3 of last 5 runs                      |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
+----------------------------------------------------------------------+
```

### Section Breakdown

#### Live Indicator Bar

Condition: Rendered only when `session.status === 'running'`.

Layout: `flex items-center gap-3 mb-4 px-3 py-2 bg-indigo-500/8 border border-indigo-500/20 rounded-lg`

Elements:
- Pulsing dot: `<span class="relative flex h-2.5 w-2.5"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span></span>`
- LIVE badge: `text-[10px] font-bold uppercase tracking-wider text-indigo-300 bg-indigo-500/20 px-1.5 py-0.5 rounded`
- Timestamp: `text-xs text-slate-400 ml-auto` -- "Last run: {relative_time}"

When live, the entire tab panel gets a subtle border glow: `border border-indigo-500/15` replacing the default `border-slate-800`.

#### Health Section

Layout: `flex items-start gap-6 mb-6`

Left column:
- HealthGauge `md` variant (80x80px)
- Score from the feature's test health

Right column (flex-1):
- HealthSummaryBar component (full width of remaining space)
- Action row below the bar: `flex items-center gap-4 mt-3`
  - Refresh button: `flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors cursor-pointer` -- `[RefreshCcw size={14}] Refresh`
  - View link: `flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer` -- `View in /tests [ChevronRight size={14}]`

#### Test Run History

Container: `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`

Header: `flex items-center justify-between px-4 py-3 border-b border-slate-800 cursor-pointer hover:bg-slate-800/50 transition-colors`
- Title: `text-sm font-semibold text-slate-200` -- "Test Run History"
- Toggle: `ChevronDown size={16}` (rotates to `ChevronRight` when collapsed)

Section is collapsible. Default state: expanded.

Each run entry (TestRunCard compact):

```
Layout: flex items-center gap-3 px-4 py-3 border-b border-slate-800/50 last:border-b-0
  hover:bg-slate-800/30 transition-colors cursor-pointer

  [expand chevron]
  <div class="flex-1 min-w-0">
    <div class="flex items-center gap-2">
      <span class="text-sm font-mono text-slate-300">Run {short_id}</span>
      <span class="text-xs text-slate-500">{relative_time}</span>
    </div>
  </div>
  <div class="flex items-center gap-3">
    [mini HealthSummaryBar, 120px wide, h-1.5]
    <span class="text-sm text-slate-400">{pass_rate}% pass</span>
    <span class="text-xs text-slate-500">Session {session_id}</span>
    [ChevronRight size={14} class="text-slate-600"]
  </div>
```

The latest run is auto-expanded to show its test results inline. Clicking a run selects it and updates the "Test Results" section below.

#### Test Results (Latest Run)

Container: `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`

##### Filter Bar

Layout: `flex items-center gap-2 px-4 py-3 border-b border-slate-800 flex-wrap`

Filter chips (status filters):

```
Base (inactive): text-xs px-2.5 py-1 rounded-full border cursor-pointer transition-colors
                 border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300

Active variant:  border-{status-color}/45 bg-{status-color}/12 text-{status-light-color}
```

Chips: `All`, `Passing`, `Failing`, `Skipped`, `Error`

"All" chip when active: `border-indigo-500/45 bg-indigo-500/12 text-indigo-200`

Search input (right-aligned, pushed by `ml-auto`):

```
flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5
  [Search size={14} class="text-slate-500"]
  <input class="bg-transparent text-sm text-slate-300 placeholder:text-slate-600 outline-none w-40"
         placeholder="Search tests..." />
```

##### Results Table

Semantic HTML table structure.

Table header:

```
<thead>
  <tr class="border-b border-slate-800">
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left w-16">Status</th>
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left">Test Name</th>
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-right w-24">Duration</th>
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left w-48">File</th>
  </tr>
</thead>
```

Table rows:

```
<tr class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
  <td class="px-4 py-2.5">[TestStatusBadge status={status} size="sm"]</td>
  <td class="px-4 py-2.5 text-sm text-slate-300">{test_name}</td>
  <td class="px-4 py-2.5 text-sm text-slate-400 text-right font-mono">{duration_ms}ms</td>
  <td class="px-4 py-2.5 text-sm font-mono text-slate-500 truncate max-w-[12rem]">{file_path}</td>
</tr>
```

Failed test rows are expandable. When expanded, an additional row appears below:

```
<tr class="bg-slate-950/50">
  <td colspan="4" class="px-4 py-3 pl-12">
    <pre class="text-xs font-mono text-rose-300/80 whitespace-pre-wrap max-h-32 overflow-y-auto">
      {error_message / stack_trace}
    </pre>
  </td>
</tr>
```

Columns are sortable. Active sort column header gets: `text-slate-300` instead of `text-slate-500`, with a sort direction indicator arrow.

#### Integrity Alerts

Container: vertical stack of IntegrityAlertCards with `space-y-3`.

Section header: `text-sm font-semibold text-slate-200 mb-3` -- "Integrity Alerts"

Each card follows the design-system.md IntegrityAlertCard spec (severity left border, icon, title, description).

Additional metadata line below the description: `text-xs text-slate-500` -- `{test_name} * Session {session_id} * Detected {relative_time}`

When no alerts exist, this section is hidden entirely.

### States

#### Live State

- Polling interval: 30 seconds
- On new data: smooth prepend of new results, auto-scroll to first new failure
- LIVE badge pulses gently: no animation on the text itself, the dot handles the visual pulse
- Panel border shifts to `border-indigo-500/15`
- Refresh button shows a brief spin animation on `RefreshCcw` when a poll completes

#### Historical State

- No polling
- Timestamp shows absolute or relative: `text-xs text-slate-500` -- "Last updated: 2h ago"
- No LIVE badge or indicator bar
- Panel border remains default `border-slate-800`
- Refresh button still available for manual refresh

#### Loading State

Full skeleton layout:

```
[HealthGauge skeleton: circle 80x80 bg-slate-800 animate-pulse]
[Summary bar skeleton: h-2 w-full bg-slate-800 rounded-full animate-pulse]
[Three row skeletons: h-10 w-full bg-slate-800 rounded animate-pulse with space-y-2]
```

#### Empty State (No Test Runs)

Centered within the tab content area:

```
Layout: flex flex-col items-center justify-center py-16 text-center
  [TestTube2 size={32} class="text-slate-600 mb-3"]
  <p class="text-sm text-slate-500">No test runs found for this feature</p>
  <p class="text-xs text-slate-600 mt-1">Test data will appear here after tests are mapped and executed</p>
```

---

## 4. Session Page "Test Status" Tab

### Context

This tab appears in `SessionInspector.tsx` and is added to the session inspector's tab union type. The content is scoped to a single `agent_session_id` -- it shows only test runs and test modifications that occurred during this specific session.

### Key Difference from Execution Page Tab

The Execution Page tab shows all runs for a feature across sessions. The Session Page tab shows:

1. Test runs triggered during **this session only**
2. A unique "Modified Tests" section showing test files that were changed by the agent during the session (sourced from `session_file_updates`)

This makes it a forensic view: "What did this agent session do to the tests?"

### Layout Specification

```
+----------------------------------------------------------------------+
|  [Overview]  [Logs]  [Files]  [Test Status]                         |
+======================================================================+
|                                                                      |
|  +--- Session Context Bar ------------------------------------------+|
|  |  Session: session-xyz   *   Branch: feat/my-feature              ||
|  +------------------------------------------------------------------+|
|                                                                      |
|  +--- Live Indicator (if session active) ----------------------------+
|  |  [pulsing indigo dot]  LIVE   Last run: 30s ago                  |
|  +------------------------------------------------------------------+
|                                                                      |
|  Test Runs (This Session)                                            |
|  +---------------------------------------------------------------+  |
|  |  [v] Run abc123   10m ago   94% pass   8 passed / 1 failed    |  |
|  |      +--- Expanded Results Table (same as Execution tab) --+  |  |
|  |      |  [PASS] test_login_valid      120ms                  |  |  |
|  |      |  [FAIL] test_mfa_bypass       250ms                  |  |  |
|  |      |  ...                                                 |  |  |
|  |      +------------------------------------------------------+  |  |
|  |                                                               |  |
|  |  [ ] Run def456   45m ago   100% pass  5 passed / 0 failed   |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
|  ================================================================== |
|                                                                      |
|  Modified Tests                                                      |
|  +---------------------------------------------------------------+  |
|  |  FILE                      TEST              CHANGE            |  |
|  |  -----------------------   ----------------  ---------------   |  |
|  |  tests/auth/test_mfa.py    test_mfa_bypass   [CHANGED badge]  |  |
|  |                                               [diff icon]      |  |
|  |  tests/auth/test_login.py  test_login_new    [ADDED badge]    |  |
|  |  tests/old/test_legacy.py  test_legacy_flow  [DELETED badge]  |  |
|  +---------------------------------------------------------------+  |
|                                                                      |
+----------------------------------------------------------------------+
```

### Section Breakdown

#### Session Context Bar

Layout: `flex items-center gap-2 px-3 py-2 bg-slate-800/50 rounded-lg mb-4`

Elements:
- Session ID: `text-sm font-mono text-slate-300` -- "Session: {session_id}"
- Separator: `<span class="text-slate-700">*</span>`
- Branch: `text-sm text-slate-400` -- "Branch: {branch_name}"

#### Live Indicator

Same specification as the Execution Page tab live indicator. Rendered only when `session.status === 'running'`.

#### Test Runs (This Session)

Section header: `text-sm font-semibold text-slate-200 mb-3` -- "Test Runs (This Session)"

Container: `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`

Each run entry is a TestRunCard (same compact format as Execution tab) with the following differences:
- No "Session S-x" reference (redundant since we are already in a session view)
- Shows absolute counts instead of percentage: "8 passed / 1 failed / 0 skipped"
- The latest run is auto-expanded to show its full results table inline

The inline results table follows the same specification as the Execution Page "Test Results" table, including filter chips and search input.

#### Modified Tests Section

This section is unique to the Session Page tab.

Section header: `text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2` -- `[FileText size={16}] Modified Tests`

Condition: Rendered only when the session has file updates that touch test files. Detection is based on `session_file_updates` records where the file path matches test file patterns.

Container: `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`

Table structure:

```
<thead>
  <tr class="border-b border-slate-800">
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left">File</th>
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left">Test</th>
    <th class="text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-2.5 text-left w-32">Change</th>
  </tr>
</thead>
```

Table rows:

```
<tr class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
  <td class="px-4 py-2.5 text-sm font-mono text-slate-400 truncate max-w-[16rem]">{file_path}</td>
  <td class="px-4 py-2.5 text-sm font-mono text-slate-300">{test_name}</td>
  <td class="px-4 py-2.5">
    [Change type badge] [optional diff icon]
  </td>
</tr>
```

Change type badges:

| Change Type | Badge Classes |
|-------------|---------------|
| `CHANGED` | `inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-amber-500/45 bg-amber-500/12 text-amber-200` |
| `ADDED` | `inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-emerald-500/45 bg-emerald-500/12 text-emerald-200` |
| `DELETED` | `inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-rose-500/45 bg-rose-500/12 text-rose-200` |

Diff icon (shown only for `CHANGED` entries): `FileText size={14} class="text-slate-500 hover:text-indigo-400 cursor-pointer transition-colors ml-2"` -- clicking this could navigate to a diff view in a future iteration.

### States

#### Live State

Same behavior as Execution Page tab:
- Polling every 30 seconds
- LIVE indicator bar shown
- Panel border glow `border-indigo-500/15`
- New test results auto-prepend

#### Historical State

- No polling
- No LIVE indicator
- Static timestamp display
- Modified Tests section shows final state of all test file changes from the session

#### Loading State

Skeleton layout:

```
[Context bar skeleton: h-8 w-full bg-slate-800 rounded-lg animate-pulse]
[Two run card skeletons: h-14 w-full bg-slate-800 rounded animate-pulse with space-y-2]
[Three row skeletons for modified tests: h-10 w-full bg-slate-800 rounded animate-pulse]
```

#### Empty State (No Test Runs in This Session)

Centered layout:

```
Layout: flex flex-col items-center justify-center py-12 text-center
  [TestTube2 size={32} class="text-slate-600 mb-3"]
  <p class="text-sm text-slate-500">No test runs during this session</p>
  <p class="text-xs text-slate-600 mt-1">Tests will appear here when runs are triggered during an active session</p>
```

#### Empty State (No Modified Tests)

The "Modified Tests" section is hidden entirely when no test files were modified. No empty state placeholder is shown for this subsection.

---

## 5. Cross-Tab Consistency Rules

### Shared Component Usage

| Component | Feature Modal | Execution Page | Session Page |
|-----------|--------------|----------------|--------------|
| HealthGauge | `sm` (56px) | `md` (80px) | Not shown (runs have counts, not scores) |
| HealthSummaryBar | Not shown (text stats only) | Full width | Not shown (inline in run cards) |
| TestStatusBadge | `sm` (icon-only in failure list) | `sm` (in table rows) | `sm` (in table rows) |
| TestRunCard | Not shown | Compact list | Compact list (no session ref) |
| IntegrityAlertCard | Summary line only | Full cards | Not shown |
| TestResultTable | Not shown | Full table with filters | Full table with filters (inline in runs) |

### Tab Bar Integration

For each location, the "Test Status" tab follows the existing tab bar pattern:

```
Tab (inactive): text-sm text-slate-400 hover:text-slate-200 px-3 py-2 cursor-pointer transition-colors
                flex items-center gap-1.5 border-b-2 border-transparent

Tab (active):   text-sm text-slate-100 px-3 py-2 cursor-pointer
                flex items-center gap-1.5 border-b-2 border-indigo-500

Icon:           TestTube2 size={16}
Label:          "Test Status"
```

### Color System Alignment

All three tabs use the same color tokens from `design-system.md`:

- Pass: `emerald-500` / `emerald-400` (text) / `emerald-200` (badge text)
- Fail: `rose-500` / `rose-400` (text) / `rose-200` (badge text)
- Skip: `amber-500` / `amber-400` (text) / `amber-200` (badge text)
- Error: `rose-600` / `rose-300` (badge text)
- Running/Live: `indigo-400` / `indigo-200` (badge text)
- Backgrounds: `slate-950` > `slate-900` (cards) > `slate-800` (borders/dividers)

### Empty States Summary

| Location | Condition | Behavior |
|----------|-----------|----------|
| Feature Modal | `test_health === null` | Tab hidden from tab bar entirely |
| Feature Modal | `test_health !== null` but 0 failures | "All tests passing" success message |
| Execution Page | No test runs for feature | Centered empty illustration |
| Session Page | No test runs in session | Centered empty illustration |
| Session Page | No modified test files | "Modified Tests" section hidden |

---

## 6. ASCII Wireframes

### 6.1 Feature Modal with Test Status Tab Active

```
+============================================================+
|  Feature: Add MFA Support                           [X]    |
+============================================================+
|  [Overview]  [Sessions]  [*Test Status*]  [Links]          |
+------------------------------------------------------------+
|                                                            |
|   +------+                                                 |
|   |      |                                                 |
|   | 89%  |   9 passing | 1 failing | 0 skipped            |
|   |      |   Last run: 2h ago * Branch: feat/add-mfa       |
|   +------+                                                 |
|    56x56                                                   |
|                                                            |
|   ---------------------------------------------------      |
|                                                            |
|   Recent Failures                                          |
|                                                            |
|   [X] test_mfa_bypass .................... [FAIL]          |
|       assertion_removed signal                             |
|                                                            |
|   ---------------------------------------------------      |
|                                                            |
|   [ShieldX] 1 alert (medium severity)                      |
|                                                            |
|   ---------------------------------------------------      |
|                                                            |
|                        View Full Test Status ->            |
|                                                            |
+------------------------------------------------------------+
```

### 6.2 Execution Page Workbench with Test Status Tab Active (Live State)

```
+============================================================+
|  Feature Execution Workbench                               |
|  Feature: Add MFA Support                                  |
+============================================================+
|  [Overview]  [Code]  [Logs]  [*Test Status*]               |
+------------------------------------------------------------+
|  .-- indigo border glow (border-indigo-500/15) ----------. |
|  |                                                        | |
|  |  (o) LIVE                           Last run: 30s ago  | |
|  |  ~~~~                                                  | |
|  |                                                        | |
|  |  +--------+   ████████████░░░░░░░                      | |
|  |  |        |   9 passing | 1 failing | 0 skipped        | |
|  |  |  89%   |                                            | |
|  |  |Degraded|   [Refresh]              [View in /tests]  | |
|  |  +--------+                                            | |
|  |   80x80                                                | |
|  |                                                        | |
|  |  ====================================================  | |
|  |                                                        | |
|  |  Test Run History                              [v]     | |
|  |  +--------------------------------------------------+  | |
|  |  | [v] Run abc123  2h ago  ████░ 94%  Sess S-1  [>] |  | |
|  |  | [ ] Run def456  1d ago  ███░░ 87%  Sess S-2  [>] |  | |
|  |  | [ ] Run ghi789  3d ago  ████░ 91%  Sess S-3  [>] |  | |
|  |  +--------------------------------------------------+  | |
|  |                                                        | |
|  |  ====================================================  | |
|  |                                                        | |
|  |  Test Results (Latest Run)                             | |
|  |  +--------------------------------------------------+  | |
|  |  | [*All*] [Pass] [Fail] [Skip] [Err]  [Search...]  |  | |
|  |  |--------------------------------------------------|  | |
|  |  | STATUS  TEST NAME           DURATION  FILE        |  | |
|  |  | [PASS]  test_login_valid    120ms     tests/au..  |  | |
|  |  | [FAIL]  test_mfa_bypass     250ms     tests/au..  |  | |
|  |  |   > AssertionError: expected True, got False      |  | |
|  |  | [PASS]  test_logout         85ms      tests/au..  |  | |
|  |  | [SKIP]  test_sso_flow       --        tests/au..  |  | |
|  |  +--------------------------------------------------+  | |
|  |                                                        | |
|  |  ====================================================  | |
|  |                                                        | |
|  |  Integrity Alerts                                      | |
|  |  +--------------------------------------------------+  | |
|  |  | [HIGH] Assert removed in abc1234                  |  | |
|  |  | test_mfa_bypass * Session S-2 * 2h ago            |  | |
|  |  +--------------------------------------------------+  | |
|  |                                                        | |
|  '--------------------------------------------------------' |
+------------------------------------------------------------+
```

### 6.3 Execution Page Workbench with Test Status Tab Active (Historical State)

```
+============================================================+
|  Feature Execution Workbench                               |
|  Feature: Add MFA Support                                  |
+============================================================+
|  [Overview]  [Code]  [Logs]  [*Test Status*]               |
+------------------------------------------------------------+
|                                                            |
|  +--------+   ████████████░░░░░░░                          |
|  |        |   9 passing | 1 failing | 0 skipped            |
|  |  89%   |                                                |
|  |Degraded|   [Refresh]              [View in /tests]      |
|  +--------+   Last updated: 2h ago                         |
|   80x80                                                    |
|                                                            |
|  ==========================================================|
|                                                            |
|  Test Run History                                    [v]   |
|  +------------------------------------------------------+  |
|  | [v] Run abc123  2h ago  ████░ 94%  Sess S-1  [>]     |  |
|  | [ ] Run def456  1d ago  ███░░ 87%  Sess S-2  [>]     |  |
|  +------------------------------------------------------+  |
|                                                            |
|  ==========================================================|
|                                                            |
|  Test Results (Latest Run)                                 |
|  +------------------------------------------------------+  |
|  | [*All*] [Pass] [Fail] [Skip] [Err]    [Search...]    |  |
|  |------------------------------------------------------|  |
|  | STATUS  TEST NAME           DURATION  FILE            |  |
|  | [PASS]  test_login_valid    120ms     tests/auth/..   |  |
|  | [FAIL]  test_mfa_bypass     250ms     tests/auth/..   |  |
|  | [PASS]  test_logout         85ms      tests/auth/..   |  |
|  +------------------------------------------------------+  |
|                                                            |
|  ==========================================================|
|                                                            |
|  Integrity Alerts                                          |
|  +------------------------------------------------------+  |
|  | [HIGH] Assert removed in abc1234                      |  |
|  | test_mfa_bypass * Session S-2 * 2h ago                |  |
|  +------------------------------------------------------+  |
|                                                            |
+------------------------------------------------------------+
```

### 6.4 Session Inspector with Test Status Tab Active

```
+============================================================+
|  Session Inspector: session-xyz                            |
+============================================================+
|  [Overview]  [Logs]  [Files]  [*Test Status*]              |
+------------------------------------------------------------+
|                                                            |
|  +------------------------------------------------------+  |
|  | Session: session-xyz  *  Branch: feat/add-mfa        |  |
|  +------------------------------------------------------+  |
|                                                            |
|  (o) LIVE                           Last run: 30s ago      |
|  ~~~~                                                      |
|                                                            |
|  Test Runs (This Session)                                  |
|  +------------------------------------------------------+  |
|  | [v] Run abc123  10m ago  8 passed / 1 failed / 0 sk  |  |
|  |   +------------------------------------------------+ |  |
|  |   | [*All*] [Pass] [Fail] [Skip]     [Search...]   | |  |
|  |   |------------------------------------------------| |  |
|  |   | [PASS]  test_login_valid   120ms  tests/auth/.. | |  |
|  |   | [FAIL]  test_mfa_bypass    250ms  tests/auth/.. | |  |
|  |   |   > AssertionError: expected True, got False    | |  |
|  |   | [PASS]  test_logout        85ms   tests/auth/.. | |  |
|  |   +------------------------------------------------+ |  |
|  |                                                       |  |
|  | [ ] Run def456  45m ago  5 passed / 0 failed / 0 sk  |  |
|  +------------------------------------------------------+  |
|                                                            |
|  ==========================================================|
|                                                            |
|  [FileText] Modified Tests                                 |
|  +------------------------------------------------------+  |
|  | FILE                    TEST              CHANGE      |  |
|  | tests/auth/test_mfa.py  test_mfa_bypass   [CHANGED]  |  |
|  |                                           [diff]      |  |
|  | tests/auth/test_new.py  test_login_new    [ADDED]     |  |
|  | tests/old/test_old.py   test_legacy_flow  [DELETED]   |  |
|  +------------------------------------------------------+  |
|                                                            |
+------------------------------------------------------------+
```

---

## 7. Interaction Specifications

### Tab Switching

All three locations use the same tab interaction model:
- Click tab label to switch
- No transition animation between tab content (instant swap)
- Active tab state persists during the session but does not persist across page navigation
- URL hash is not updated for tab state (follows existing CCDash convention)

### Expandable Rows (Test Run Cards)

- Click anywhere on the row to expand/collapse
- Chevron rotates 90 degrees: `transition-transform duration-200`
- Content area uses `max-height` transition for smooth expand: `transition-all duration-200 ease-in-out`
- Only one run can be expanded at a time (accordion behavior)

### Filter Chips (Test Results)

- Click to toggle filter
- "All" deselects all specific filters (shows everything)
- Selecting any specific filter deselects "All"
- Multiple specific filters can be active simultaneously (OR logic)
- Active chip count animates with a brief scale pulse: `transition-transform duration-150`

### Search Input (Test Results)

- Debounced at 300ms
- Filters by test name (substring match, case-insensitive)
- Combines with status filter chips (AND logic)
- Shows result count when active: `text-xs text-slate-500` -- "Showing {n} of {total}"
- Clear button (X) appears when input has value

### Action Link Navigation

"View Full Test Status" in the Feature Modal navigates to:
1. The Execution Page for the current feature
2. Pre-selects the "Test Status" tab

Implementation: uses the existing routing mechanism (HashRouter navigation).

### Refresh Button

- Click triggers an immediate data refetch
- Button icon (`RefreshCcw`) spins for 500ms during fetch: `animate-spin`
- Button is disabled during fetch to prevent double-clicks: `opacity-50 cursor-not-allowed`

---

## 8. Responsive Considerations

### Feature Modal

The modal is a fixed-width overlay. No responsive breakpoints needed. Content reflows naturally within the ~600px width constraint via flex-wrap.

### Execution Page Tab

| Breakpoint | Behavior |
|-----------|----------|
| >= 1024px | Full layout as specified (health gauge beside summary bar, table with all columns) |
| 768-1023px | Health gauge stacks above summary bar. Table hides "File" column. |
| < 768px | Not applicable (Execution Workbench is not shown on mobile) |

### Session Page Tab

| Breakpoint | Behavior |
|-----------|----------|
| >= 1024px | Full layout as specified |
| 768-1023px | Modified Tests table hides "File" column, shows only test name + change badge |
| < 768px | Not applicable (Session Inspector is not shown on mobile) |

---

## 9. Data Dependencies

### Feature Modal Tab

Requires from API:
- `feature.test_health` (number or null) -- visibility gate
- `feature.test_counts` (`{ passed, failed, skipped, error, total }`)
- `feature.latest_test_run` (`{ timestamp, branch }`)
- `feature.recent_failures` (array, max 3, with test name and failure reason)
- `feature.integrity_alert_count` and `highest_severity`

### Execution Page Tab

Requires from API:
- `/api/tests/health/{feature_slug}` -- health score and counts
- `/api/tests/runs?feature_slug={slug}` -- run history
- `/api/tests/results?run_id={id}` -- individual run results
- `/api/tests/integrity?feature_slug={slug}` -- integrity alerts
- `session.status` -- for live/historical mode detection

### Session Page Tab

Requires from API:
- `/api/tests/runs?session_id={id}` -- runs for this session
- `/api/tests/results?run_id={id}` -- individual run results
- `/api/sessions/{id}/file_updates` -- file modifications (existing endpoint, filtered client-side for test files)
- `session.status` -- for live/historical mode detection
