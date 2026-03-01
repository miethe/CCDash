---
title: "Test Visualizer Component Specifications"
doc_type: design
feature_slug: test-visualizer
created: 2026-02-28
updated: 2026-02-28
---

# Test Visualizer Component Specifications

This document provides implementation-ready specifications for all 8 core Test Visualizer UI components. Each specification includes the TypeScript props interface, visual states, interaction behavior, accessibility requirements, responsive behavior, animation specs, and dependencies. A frontend engineer should be able to implement any component directly from this document without additional design input.

**Design system reference**: `docs/project_plans/designs/test-visualizer/design-system.md`
**Backend DTOs**: `backend/models.py` (TestRunDTO, TestResultDTO, TestIntegritySignalDTO, DomainHealthRollupDTO, FeatureTimelinePointDTO, etc.)

---

## Table of Contents

1. [TestStatusBadge](#1-teststatusbadge)
2. [TestRunCard](#2-testruncard)
3. [IntegrityAlertCard](#3-integrityalertcard)
4. [HealthSummaryBar](#4-healthsummarybar)
5. [DomainTreeView](#5-domaintreeview)
6. [TestResultTable](#6-testresulttable)
7. [TestTimeline](#7-testtimeline)
8. [HealthGauge](#8-healthgauge)

---

## Shared Types

These types are referenced across multiple components. They should be defined in a shared module (e.g., `components/test-visualizer/types.ts`).

```typescript
/** Canonical test statuses. Matches backend `status` fields. */
export type TestStatus =
  | 'passed'
  | 'failed'
  | 'skipped'
  | 'error'
  | 'xfailed'
  | 'xpassed'
  | 'unknown'
  | 'running';

/** Status priority order for sorting (lower index = higher severity). */
export const STATUS_PRIORITY: TestStatus[] = [
  'error',
  'failed',
  'xpassed',
  'xfailed',
  'skipped',
  'running',
  'unknown',
  'passed',
];

/** Health level derived from pass rate percentage. */
export type HealthLevel = 'healthy' | 'degraded' | 'at-risk' | 'critical';

/** Integrity signal severity. */
export type SignalSeverity = 'high' | 'medium' | 'low';
```

---

## 1. TestStatusBadge

A small inline indicator that renders an icon and optional label for a test status. This is the most frequently reused component in the Test Visualizer -- it appears inside tables, cards, trees, and tooltips.

### 1.1 Props Interface

```typescript
import { type LucideIcon } from 'lucide-react';

interface TestStatusBadgeProps {
  /** The test status to display. */
  status: TestStatus;
  /** Badge size variant. Defaults to 'md'. */
  size?: 'sm' | 'md' | 'lg';
  /** Whether to show the text label. Ignored for 'sm' (always hidden). Defaults to true for 'md' and 'lg'. */
  showLabel?: boolean;
  /** Additional CSS classes appended to the outer element. */
  className?: string;
}
```

### 1.2 Status Configuration Map

This lookup drives all rendering decisions. Define it as a constant outside the component.

```typescript
import {
  CheckCircle2, XCircle, MinusCircle, AlertCircle,
  AlertTriangle, HelpCircle, Loader2,
} from 'lucide-react';

interface StatusConfig {
  icon: LucideIcon;
  label: string;
  badgeClasses: string; // border + bg + text color classes
}

const STATUS_CONFIG: Record<TestStatus, StatusConfig> = {
  passed:  { icon: CheckCircle2,  label: 'Passing', badgeClasses: 'border-emerald-500/45 bg-emerald-500/12 text-emerald-200' },
  failed:  { icon: XCircle,       label: 'Failing', badgeClasses: 'border-rose-500/45 bg-rose-500/12 text-rose-200' },
  skipped: { icon: MinusCircle,   label: 'Skipped', badgeClasses: 'border-amber-500/45 bg-amber-500/12 text-amber-200' },
  error:   { icon: AlertCircle,   label: 'Error',   badgeClasses: 'border-rose-600/45 bg-rose-600/12 text-rose-300' },
  xfailed: { icon: AlertTriangle, label: 'XFail',   badgeClasses: 'border-amber-400/45 bg-amber-400/12 text-amber-200' },
  xpassed: { icon: AlertTriangle, label: 'XPass',   badgeClasses: 'border-rose-400/45 bg-rose-400/12 text-rose-200' },
  unknown: { icon: HelpCircle,    label: 'Unknown', badgeClasses: 'border-slate-500/45 bg-slate-500/12 text-slate-300' },
  running: { icon: Loader2,       label: 'Running', badgeClasses: 'border-indigo-400/45 bg-indigo-400/12 text-indigo-200' },
};
```

### 1.3 Size Variant Classes

| Size | Base Classes | Icon Size | Shows Label | Gap |
|------|-------------|-----------|-------------|-----|
| `sm` | `px-1 py-0.5` | 12 | Never | none |
| `md` | `px-1.5 py-0.5 text-[10px] gap-1.5` | 16 | Default yes | `gap-1.5` |
| `lg` | `px-2 py-1 text-xs gap-1.5` | 20 | Default yes | `gap-1.5` |

All sizes share these base classes: `inline-flex items-center rounded border font-semibold`.

### 1.4 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Renders icon + optional label with status colors |
| **Running** | `Loader2` icon receives `animate-spin motion-reduce:animate-none` class |
| **Hover** | No hover state -- badge is informational, not interactive |
| **Focus** | Not focusable by default (purely presentational) |
| **Disabled** | N/A -- badges are not interactive |
| **Loading** | N/A -- the badge itself does not load |
| **Error** | N/A -- status is always provided by parent |

### 1.5 Interaction Spec

- **Not interactive.** The badge is a presentational element. It does not respond to clicks, hovers, or keyboard events.
- Parent components may wrap the badge in a button or link for interactivity, but the badge itself remains inert.

### 1.6 Accessibility

```html
<span
  role="status"
  aria-label="Test status: {label}"
  aria-live="{running ? 'polite' : undefined}"
  class="..."
>
  <Icon aria-hidden="true" />
  {showLabel && <span>{label}</span>}
</span>
```

- `aria-label` is always present. Critical for `sm` size where no visible text exists.
- `aria-live="polite"` only on `running` status to announce transitions.
- Icon is always `aria-hidden="true"` since the `aria-label` conveys meaning.

### 1.7 Responsive Behavior

- No breakpoint-specific changes. The badge is inline and self-sizing.
- Parent components may choose different `size` variants at different breakpoints via prop.

### 1.8 Animation/Transition Specs

- **Running spin**: `animation: spin 1s linear infinite` (Tailwind `animate-spin`).
- **Reduced motion**: `motion-reduce:animate-none` stops the spin, leaving a static `Loader2` icon.
- No other transitions.

### 1.9 Dependencies

- `lucide-react`: CheckCircle2, XCircle, MinusCircle, AlertCircle, AlertTriangle, HelpCircle, Loader2

### 1.10 Visual Examples

```
sm + passed:   [*]                          (emerald circle icon only, ~20px tall)
md + passed:   [* Passing]                  (emerald icon + label, ~22px tall)
lg + passed:   [* Passing]                  (larger emerald icon + label, ~28px tall)

sm + failed:   [x]                          (rose circle icon only)
md + failed:   [x Failing]                  (rose icon + label)

sm + running:  [(spinning)]                 (indigo spinning loader)
md + running:  [(spinning) Running]         (indigo spinning loader + label)
```

---

## 2. TestRunCard

A card component that summarizes a single test run. Used in run history lists, session detail views, and the main test dashboard.

### 2.1 Props Interface

```typescript
interface TestRunCardProps {
  /** The test run data. */
  run: TestRunDTO;
  /** Whether to show the linked agent session. Defaults to false. */
  showSession?: boolean;
  /** Compact mode hides the git SHA chip and session link. Defaults to false. */
  compact?: boolean;
  /** Additional CSS classes on the outer card. */
  className?: string;
}
```

Where `TestRunDTO` is:

```typescript
interface TestRunDTO {
  run_id: string;
  project_id: string;
  timestamp: string;         // ISO 8601
  git_sha: string;
  branch: string;
  agent_session_id: string;
  env_fingerprint: string;
  trigger: string;           // 'local' | 'ci' | 'agent'
  status: string;            // 'complete' | 'running' | 'failed'
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  duration_ms: number;
  metadata: Record<string, unknown>;
  created_at: string;
}
```

### 2.2 Layout Structure

```
+---------------------------------------------------------------+
| [run_id:7]  [trigger badge]              [relative timestamp]  |  Header row
|                                                                |
| [HealthSummaryBar: passed/failed/skipped]                      |  Summary bar
|                                                                |
| [git_sha:7 chip]  [branch chip]  [duration]  [session link]   |  Metadata row
+---------------------------------------------------------------+
```

### 2.3 Card Styling

**Outer container:**
```
bg-slate-900 border border-slate-800 rounded-xl p-4
  hover:border-slate-700 transition-colors duration-150
  cursor-pointer
```

**Header row:** `flex items-center justify-between mb-3`
- Run ID: `text-sm font-mono font-semibold text-slate-200` -- truncated to first 7 characters of `run_id`
- Trigger badge: `TestStatusBadge`-style inline badge with trigger type. Colors: `local` = slate, `ci` = cyan, `agent` = indigo.
- Timestamp: `text-xs text-slate-500` -- relative format ("2 hours ago", "yesterday"). Use a utility like `date-fns/formatDistanceToNow`.

**Stats row:** Renders an embedded `HealthSummaryBar` component with `passed_tests`, `failed_tests`, `skipped_tests`, `total_tests`.

**Metadata row:** `flex items-center gap-2 mt-3 flex-wrap`
- Git SHA chip (if `git_sha` non-empty and not compact): `text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700` -- truncated to 7 chars.
- Branch chip (if `branch` non-empty and not compact): same styling as git SHA chip.
- Duration: `text-xs text-slate-500` with Clock icon (size 12). Format: `{ms}ms` if <1s, `{s}s` if <60s, `{m}m {s}s` otherwise.
- Session link (if `showSession` and `agent_session_id` non-empty): `text-xs text-indigo-400 hover:text-indigo-300 underline` linking to `/#/sessions/{agent_session_id}`.

### 2.4 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Card with summary content as described above |
| **Hover** | Border lightens to `border-slate-700`. Subtle transition. |
| **Active/Pressed** | `bg-slate-800/50` momentary flash (150ms) |
| **Expanded** | Not applicable -- the card itself does not expand. Click navigates. |
| **Loading** | Skeleton: rounded-xl with `animate-pulse bg-slate-800` placeholder. Height ~120px. |
| **Empty** | N/A -- component requires a `run` prop |
| **Error** | N/A -- error states handled by parent container |
| **Run status=running** | Pulsing indigo left border: `border-l-[3px] border-l-indigo-400 animate-pulse` |

### 2.5 Interaction Spec

- **Click on card body**: Navigate to `/tests?run_id={run_id}` (via HashRouter).
- **Click on session link**: Navigate to `/#/sessions/{agent_session_id}`. Stops propagation so it does not trigger card navigation.
- **Keyboard**: Card is focusable (`tabIndex={0}`). `Enter` or `Space` triggers navigation. Focus ring: `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900`.

### 2.6 Accessibility

```html
<article
  role="article"
  aria-label="Test run {run_id:7}, {relative_time}: {passed} passed, {failed} failed, {skipped} skipped"
  tabIndex={0}
  class="..."
>
  ...
</article>
```

- The card uses `<article>` semantics since it is a self-contained content block.
- The `aria-label` provides a full summary for screen readers.
- Interactive child links use standard `<a>` tags with descriptive text.

### 2.7 Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 640px (sm) | Metadata row wraps. Git SHA and branch chips stack below duration. |
| >= 640px | Single row for all metadata items. |
| Minimum width | 280px (set as `min-w-[280px]` on card) |

### 2.8 Animation/Transition Specs

- Border color transition: `transition-colors duration-150`
- Press feedback: `active:bg-slate-800/50` with `transition-colors duration-150`
- Running pulse: Tailwind `animate-pulse` on left border (only when `run.status === 'running'`)
- Reduced motion: `motion-reduce:animate-none` on the pulse

### 2.9 Dependencies

- `HealthSummaryBar` (internal)
- `TestStatusBadge` (for trigger badge, optional)
- `lucide-react`: Clock
- `date-fns`: formatDistanceToNow (or equivalent relative time utility)
- React Router: `useNavigate` for navigation

---

## 3. IntegrityAlertCard

Displays a single test integrity signal (e.g., flaky test detection, orphaned test, coverage gap). The card uses a colored left border to indicate severity.

### 3.1 Props Interface

```typescript
interface IntegrityAlertCardProps {
  /** The integrity signal data. */
  signal: TestIntegritySignalDTO;
  /** Whether to show the linked session. Defaults to false. */
  showSession?: boolean;
  /** Whether the card starts expanded. Defaults to false. */
  defaultExpanded?: boolean;
  /** Callback when dismiss is clicked. If omitted, dismiss button is hidden. */
  onDismiss?: (signalId: string) => void;
  /** Additional CSS classes. */
  className?: string;
}
```

Where `TestIntegritySignalDTO` is:

```typescript
interface TestIntegritySignalDTO {
  signal_id: string;
  project_id: string;
  git_sha: string;
  file_path: string;
  test_id: string | null;
  signal_type: string;       // e.g., 'flaky_test', 'orphaned_test', 'coverage_gap'
  severity: 'high' | 'medium' | 'low';
  details: Record<string, unknown>;
  linked_run_ids: string[];
  agent_session_id: string;
  created_at: string;
}
```

### 3.2 Layout Structure

```
+-- 3px colored left border -----------------------------------------+
| [severity icon]  [signal_type label]           [timestamp] [dismiss]|
|                  [file_path (mono)]                                  |
|                  [git_sha chip] [session link]                       |
|                                                                      |
|  (expanded) [details_json formatted block]                           |
+----------------------------------------------------------------------+
```

### 3.3 Severity Styling

| Severity | Left Border | Icon | Icon Class |
|----------|------------|------|------------|
| `high` | `border-l-[3px] border-l-rose-500` | `ShieldAlert` | `text-rose-500` |
| `medium` | `border-l-[3px] border-l-amber-500` | `ShieldX` | `text-amber-500` |
| `low` | `border-l-[3px] border-l-slate-600` | `Shield` | `text-slate-400` |

**Base card classes:**
```
bg-slate-900 border border-slate-800 rounded-xl p-4 border-l-[3px]
```

The `border-l-*` color class is appended based on severity.

### 3.4 Content Styling

- **Signal type label**: `text-sm font-semibold text-slate-100`. The `signal_type` string is formatted: replace underscores with spaces, title-case each word. Example: `flaky_test` becomes "Flaky Test".
- **File path**: `text-xs font-mono text-slate-400 mt-1`. Full path, no truncation.
- **Git SHA chip**: `text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700`. Truncated to 7 characters.
- **Timestamp**: `text-xs text-slate-500`. Relative format.
- **Session link** (if `showSession` and `agent_session_id` non-empty): `text-xs text-indigo-400 hover:text-indigo-300 underline`.
- **Dismiss button** (if `onDismiss` provided): `text-slate-600 hover:text-slate-400` X icon (size 14), positioned top-right of the card header.

### 3.5 Expanded Details Section

When expanded, a details block renders below the metadata:

```
mt-3 pt-3 border-t border-slate-800
```

Content: `details` object rendered as formatted key-value pairs.
- Keys: `text-xs font-medium text-slate-500`
- Values: `text-xs font-mono text-slate-300`
- If `details` contains a `message` or `reason` key, render it first as a paragraph (`text-xs text-slate-300`).
- Remaining keys render in a definition-list style (`<dl>` with `<dt>` / `<dd>` pairs).

### 3.6 Visual States

| State | Behavior |
|-------|----------|
| **Default (collapsed)** | Shows header + file path + metadata chips |
| **Expanded** | Adds details section below with border-top separator |
| **Hover** | Card border lightens: `hover:border-slate-700` |
| **Loading** | Skeleton: card-shaped placeholder with `animate-pulse`, height ~80px |
| **Empty** | N/A -- component requires a `signal` prop |

### 3.7 Interaction Spec

- **Click on card body**: Toggles expanded/collapsed state. Exclude clicks on links and dismiss button.
- **Click on session link**: Navigates to `/#/sessions/{agent_session_id}`. Stops propagation.
- **Click dismiss**: Calls `onDismiss(signal_id)`. Stops propagation.
- **Keyboard**: Card body is focusable (`tabIndex={0}`). `Enter` or `Space` toggles expansion. `Escape` collapses if expanded. Focus ring: `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900`.

### 3.8 Accessibility

```html
<div
  role="region"
  aria-label="{severity} severity: {signal_type_formatted} in {file_path}"
  tabIndex={0}
  aria-expanded="{isExpanded}"
>
  <Icon aria-hidden="true" />
  ...
</div>
```

- Severity icon is decorative (`aria-hidden="true"`).
- The `aria-label` conveys severity, type, and file path.
- `aria-expanded` reflects the expansion state.

### 3.9 Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 640px | Timestamp moves below signal type label (stacks vertically). Dismiss button remains top-right. |
| >= 640px | Header is a single row: icon + label on left, timestamp + dismiss on right. |
| Minimum width | 260px |

### 3.10 Animation/Transition Specs

- Expand/collapse: Content height animates from 0 to auto. Use `grid-rows` trick: `grid grid-rows-[0fr]` collapsed, `grid-rows-[1fr]` expanded, with `transition-[grid-template-rows] duration-200 ease-out`. Inner container: `overflow-hidden`.
- Border hover: `transition-colors duration-150`
- Reduced motion: `motion-reduce:transition-none`

### 3.11 Dependencies

- `lucide-react`: ShieldAlert, ShieldX, Shield, X (for dismiss)
- `date-fns`: formatDistanceToNow

---

## 4. HealthSummaryBar

A horizontal stacked bar chart showing the proportional breakdown of test results. Used standalone and embedded inside `TestRunCard`.

### 4.1 Props Interface

```typescript
interface HealthSummaryBarProps {
  /** Number of passing tests. */
  passed: number;
  /** Number of failing tests. */
  failed: number;
  /** Number of skipped tests. */
  skipped: number;
  /** Total test count. If omitted, calculated as passed + failed + skipped. */
  total?: number;
  /** Number of errored tests. Defaults to 0. */
  errored?: number;
  /** Whether to show the text summary below the bar. Defaults to true. */
  showSummary?: boolean;
  /** Bar height class. Defaults to 'h-2'. */
  height?: 'h-1.5' | 'h-2' | 'h-3';
  /** Additional CSS classes. */
  className?: string;
}
```

### 4.2 Layout Structure

```
[==passed==|==failed==|==errored==|==skipped==|==unknown==]   bar
 42 passing | 3 failing | 1 skipped                           text summary
```

### 4.3 Bar Implementation

**Container:**
```
{height} rounded-full overflow-hidden flex bg-slate-800
  hover:h-3 transition-all duration-200
```

Note: the hover height expansion only applies when `height` is `h-2` (default). When explicitly set to `h-1.5` or `h-3`, hover does not change height.

**Segments** (rendered left to right in this order):

| Segment | Tailwind Background | Order |
|---------|---------------------|-------|
| Passed | `bg-emerald-500` | 1 |
| Failed | `bg-rose-500` | 2 |
| Errored | `bg-rose-600` | 3 |
| Skipped | `bg-amber-500` | 4 |
| Unknown | `bg-slate-600` | 5 |

Each segment is a `<div>` with:
- `style={{ width: '{percentage}%' }}` where `percentage = (count / total) * 100`
- `min-w-[2px]` class applied when the segment count is non-zero
- `transition-all duration-200` for smooth resizing
- No border-radius on individual segments (container handles rounding via `overflow-hidden`)

**Unknown count** is derived: `total - passed - failed - errored - skipped` (only if positive).

### 4.4 Segment Tooltips

Each segment displays a tooltip on hover:

```typescript
// Tooltip content
`${count} ${label} (${percentage.toFixed(1)}%)`
```

Tooltip styling matches CCDash chart tooltips:
```
bg-slate-950 border border-slate-700 rounded-lg px-2 py-1
text-xs text-slate-200
```

Position: above the segment, centered horizontally. Use CSS `position: absolute` with a parent `position: relative` wrapper per segment, or a shared tooltip component.

### 4.5 Text Summary

Rendered below the bar when `showSummary` is true.

```html
<div class="text-sm text-slate-400 mt-2 flex items-center gap-2 flex-wrap">
  <span><span class="text-emerald-400">{passed}</span> passing</span>
  <span class="text-slate-600">|</span>
  <span><span class="text-rose-400">{failed}</span> failing</span>
  <span class="text-slate-600">|</span>
  <span><span class="text-amber-400">{skipped}</span> skipped</span>
</div>
```

If `errored > 0`, insert after failing: `<span class="text-slate-600">|</span> <span><span class="text-rose-500">{errored}</span> errored</span>`.

### 4.6 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Proportional segments with text summary |
| **Hover (bar)** | Bar height expands to `h-3` (from `h-2`). Segment tooltips appear on individual hover. |
| **Empty (total=0)** | Full-width `bg-slate-700 rounded-full h-2`. Centered text below: `text-xs text-slate-500 italic` "No test data available" |
| **All passing** | Single emerald segment fills 100% |
| **Loading** | `animate-pulse bg-slate-800 rounded-full h-2` placeholder bar. No text summary. |

### 4.7 Interaction Spec

- **Hover on segment**: Shows tooltip with count and percentage.
- **Not clickable.** The bar is informational only.
- **Keyboard**: Not focusable (purely visual element with `role="img"`).

### 4.8 Accessibility

```html
<div
  role="img"
  aria-label="Test results: {passed} passing, {failed} failing, {skipped} skipped out of {total} total"
>
  <!-- segments are aria-hidden since the aria-label conveys all info -->
  <div aria-hidden="true" class="...">
    ...segments...
  </div>
</div>
```

### 4.9 Responsive Behavior

- The bar is always 100% width of its container. No breakpoint-specific behavior.
- Text summary wraps naturally via `flex-wrap`.
- Minimum container width: 120px.

### 4.10 Animation/Transition Specs

- Bar height expansion: `transition-all duration-200 ease-out`
- Segment width changes (when data updates): `transition-all duration-200 ease-out`
- Reduced motion: `motion-reduce:transition-none`

### 4.11 Dependencies

- No external dependencies. Pure HTML/CSS/Tailwind implementation.
- Optional: a shared `Tooltip` component if one exists in the codebase.

---

## 5. DomainTreeView

A recursive tree component that displays test domains and their child features/subdomains. Each node shows a name, health percentage, and a mini health bar. Follows the WAI-ARIA Tree View pattern.

### 5.1 Props Interface

```typescript
interface DomainTreeViewProps {
  /** Array of top-level domain rollups. Each may contain nested children. */
  domains: DomainHealthRollupDTO[];
  /** Called when a domain node is selected. Receives the domain_id. */
  onSelect: (domainId: string) => void;
  /** The currently selected domain_id. Controls highlight state. */
  selectedPath?: string;
  /** Array of domain_ids that should be expanded. If omitted, all collapsed. */
  expandedPaths?: string[];
  /** Called when a node is expanded or collapsed. */
  onToggle?: (domainId: string, expanded: boolean) => void;
  /** Whether the tree is loading. Shows skeleton state. */
  isLoading?: boolean;
  /** Additional CSS classes. */
  className?: string;
}
```

Where `DomainHealthRollupDTO` is:

```typescript
interface DomainHealthRollupDTO {
  domain_id: string;
  domain_name: string;
  tier: string;             // 'core' | 'extended' | 'exploratory'
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  pass_rate: number;        // 0.0 - 1.0
  integrity_score: number;  // 0.0 - 1.0
  confidence_score: number;
  last_run_at: string | null;
  children: DomainHealthRollupDTO[];
}
```

### 5.2 Layout Structure

Each tree node renders as:

```
[chevron] [color bar 3px] [name]                 [health% badge] [mini bar]
                          [N tests, last run X ago]               (60px wide)
```

Indentation: Each nesting level adds `pl-4` (16px) to the left.

### 5.3 Node Styling

**Node container (default):**
```
flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer
  transition-colors duration-100
```

**Node container (hover):**
```
bg-slate-800 rounded-lg
```

**Node container (selected):**
```
bg-indigo-500/10 border border-indigo-500/20 rounded-lg
```

**Chevron icon**: `ChevronRight` (size 14, `text-slate-500`). Rotates 90 degrees when expanded. Transition: `transition-transform duration-150`.

**Color-coded left bar** (3px tall vertical bar on the left side of each node):
- `pass_rate >= 0.9`: `bg-emerald-500`
- `pass_rate >= 0.7`: `bg-amber-400`
- `pass_rate >= 0.5`: `bg-amber-600`
- `pass_rate < 0.5`: `bg-rose-500`

Rendered as: `w-[3px] h-8 rounded-full {color_class}`.

**Name text**: `text-sm font-medium text-slate-200`. Truncate with `truncate` class (ellipsis) if needed.

**Subtitle text**: `text-[10px] text-slate-500`. Format: `{total_tests} tests` with optional `, last run {relative_time}`.

**Health percentage badge**: `text-xs font-semibold` in health color (emerald/amber/rose following the same pass_rate thresholds as the left bar). Format: `{Math.round(pass_rate * 100)}%`.

**Mini health bar**: A 60px-wide, 4px-tall `HealthSummaryBar` with `showSummary={false}` and `height="h-1.5"`.

### 5.4 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Tree with all nodes at specified expansion levels |
| **Hover (node)** | `bg-slate-800 rounded-lg` background |
| **Selected (node)** | `bg-indigo-500/10 border border-indigo-500/20 rounded-lg` |
| **Focused (node)** | Focus ring: `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 outline-none` |
| **Expanded** | Chevron rotated 90 degrees, children visible |
| **Collapsed** | Chevron points right, children hidden |
| **Loading** | 5 skeleton rows: `animate-pulse bg-slate-800 rounded-lg h-10 mb-1` with varying widths (100%, 90%, 85%, 95%, 80%) |
| **Empty** | Centered message: `text-sm text-slate-500 italic py-8` "No test domains configured". Below: a subtle "Configure domains" link in `text-indigo-400 text-xs hover:text-indigo-300`. |

### 5.5 Interaction Spec

**Mouse:**
- Click on chevron area: toggles expand/collapse (calls `onToggle`).
- Click on node body (non-chevron): selects the node (calls `onSelect`) AND toggles expand if it has children.
- Hover: background change as described.

**Keyboard (WAI-ARIA Tree pattern):**

| Key | Action |
|-----|--------|
| `ArrowDown` | Move focus to next visible node |
| `ArrowUp` | Move focus to previous visible node |
| `ArrowRight` | If collapsed and has children: expand. If expanded: move focus to first child. If leaf: no action. |
| `ArrowLeft` | If expanded: collapse. If collapsed or leaf: move focus to parent node. |
| `Enter` | Select the focused node (calls `onSelect`) |
| `Space` | Toggle expand/collapse of focused node |
| `Home` | Move focus to first node in tree |
| `End` | Move focus to last visible node in tree |
| `Escape` | Deselect (calls `onSelect('')`) |

Focus management: The tree container manages a single roving `tabIndex`. The focused node gets `tabIndex={0}`, all others get `tabIndex={-1}`.

### 5.6 Accessibility

```html
<div role="tree" aria-label="Test domain hierarchy" class="...">
  <!-- Recursive rendering -->
  <div
    role="treeitem"
    aria-expanded="{hasChildren ? isExpanded : undefined}"
    aria-selected="{isSelected}"
    aria-level="{depth + 1}"
    aria-setsize="{siblingsCount}"
    aria-posinset="{indexInSiblings + 1}"
    tabIndex="{isFocused ? 0 : -1}"
  >
    <div><!-- node content --></div>
    {isExpanded && hasChildren && (
      <div role="group">
        <!-- child treeitem elements -->
      </div>
    )}
  </div>
</div>
```

- `role="tree"` on the outermost container.
- `role="treeitem"` on each node.
- `role="group"` wrapping child nodes of an expanded parent.
- `aria-expanded` only present on nodes that have children.
- `aria-level`, `aria-setsize`, `aria-posinset` for screen reader context.

### 5.7 Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 640px | Mini health bar hidden. Health percentage badge only. |
| >= 640px | Full layout with mini health bar visible. |
| Minimum width | 240px |

### 5.8 Animation/Transition Specs

- Chevron rotation: `transition-transform duration-150 ease-out`. Collapsed: `rotate-0`. Expanded: `rotate-90`.
- Children reveal: `transition-[grid-template-rows] duration-200 ease-out`. Uses `grid grid-rows-[0fr]` / `grid-rows-[1fr]` pattern with `overflow-hidden` on the inner wrapper.
- Node background: `transition-colors duration-100`
- Reduced motion: All transitions respect `motion-reduce:transition-none`.

### 5.9 Dependencies

- `HealthSummaryBar` (for mini health bars)
- `lucide-react`: ChevronRight, ChevronDown
- `date-fns`: formatDistanceToNow
- React: `useRef`, `useState`, `useCallback` for keyboard focus management

---

## 6. TestResultTable

A sortable, filterable table that displays individual test results. Supports inline expansion for error details and status filtering.

### 6.1 Props Interface

```typescript
interface TestResultTableProps {
  /** Array of test results to display. */
  results: TestResultDTO[];
  /** Optional map of test_id -> TestDefinitionDTO for enriched display. */
  definitions?: Record<string, TestDefinitionDTO>;
  /** Callback when a test row is clicked. Receives test_id. */
  onTestClick?: (testId: string) => void;
  /** Filter to specific statuses. If omitted, shows all. */
  filterStatus?: TestStatus[];
  /** Search query to filter by test name. Case-insensitive. */
  searchQuery?: string;
  /** Whether the data is loading. */
  isLoading?: boolean;
  /** Maximum results before "Show more" button. Defaults to 50. */
  pageSize?: number;
  /** Additional CSS classes. */
  className?: string;
}
```

Where `TestResultDTO` is:

```typescript
interface TestResultDTO {
  run_id: string;
  test_id: string;
  status: string;           // TestStatus
  duration_ms: number;
  error_fingerprint: string;
  error_message: string;
  artifact_refs: string[];
  stdout_ref: string;
  stderr_ref: string;
  created_at: string;
}
```

And `TestDefinitionDTO`:

```typescript
interface TestDefinitionDTO {
  test_id: string;
  project_id: string;
  path: string;
  name: string;
  framework: string;
  tags: string[];
  owner: string;
  created_at: string;
  updated_at: string;
}
```

### 6.2 Layout Structure

```
[Status filter pills]                              [Search input]

| Test Name          | Status   | Duration | Error Preview       |
|--------------------|----------|----------|---------------------|
| test_login_flow    | Passing  | 120ms    | --                  |
| test_checkout      | Failing  | 45ms     | AssertionError: ... |
|   (expanded) Full error message + stack trace                  |
| test_search        | Skipped  | --       | --                  |
| ...                                                            |

                    [Show more (showing 50 of 128)]
```

### 6.3 Filter Controls

**Status filter pills**: Rendered above the table, left-aligned.

```html
<div class="flex items-center gap-2 mb-4 flex-wrap">
  {STATUS_OPTIONS.map(status => (
    <button
      class="px-2.5 py-1 rounded-full text-xs font-medium border transition-colors duration-100
        {isActive
          ? `${statusBgClass} ${statusBorderClass} ${statusTextClass}`
          : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-600'
        }"
      aria-pressed="{isActive}"
    >
      <Icon size={12} /> {label}
    </button>
  ))}
</div>
```

Each pill uses the status badge colors from `STATUS_CONFIG` when active. When inactive, uses neutral slate styling.

**Search input**: Right-aligned, same row as filter pills on desktop. Stacks below on mobile.

```html
<div class="relative">
  <Search size={14} class="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
  <input
    type="text"
    placeholder="Search tests..."
    class="pl-8 pr-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg
      text-slate-200 placeholder:text-slate-500
      focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
      w-full sm:w-64"
  />
</div>
```

### 6.4 Table Styling

**Table container**: `w-full overflow-x-auto`

```html
<table class="w-full text-left">
  <thead>
    <tr class="border-b border-slate-800">
      <th>...</th>
    </tr>
  </thead>
  <tbody>
    ...
  </tbody>
</table>
```

**Header cells** (`<th>`):
```
text-xs font-medium text-slate-500 uppercase tracking-wider
  py-3 px-4 cursor-pointer select-none
  hover:text-slate-300 transition-colors duration-100
```

**Sort indicator**: Active sort column includes a `ChevronUp` or `ChevronDown` icon (size 12) inline after the header text. Inactive sortable columns show a subtle `ChevronsUpDown` icon (size 12, `text-slate-600`) on hover only.

**Column definitions**:

| Column | Width | Content | Sortable | Sort Logic |
|--------|-------|---------|----------|------------|
| Test Name | `flex-1`, min `200px` | `name` from definition, or `test_id` fallback. Monospace if showing path: `font-mono text-sm text-slate-300` | Yes | Alphabetical (a-z, z-a) |
| Status | `80px` | `TestStatusBadge` with `size="sm"` | Yes | By `STATUS_PRIORITY` index |
| Duration | `90px` | Formatted duration: `text-sm text-slate-400 tabular-nums`. Format: `<1ms`, `Nms`, `N.Ns`, `Nm Ns` | Yes | Numeric (ascending, descending) |
| Error Preview | `flex-1`, min `150px` | First 80 characters of `error_message`. `text-sm text-slate-500 truncate`. Full text appears on hover tooltip. If empty, render `--` in `text-slate-600`. | Yes | Alphabetical |

**Data rows** (`<tr>`):
```
border-b border-slate-800/50
  hover:bg-slate-800/50 transition-colors duration-100
  cursor-pointer
```

**Data cells** (`<td>`): `py-3 px-4`

### 6.5 Expanded Error Detail

When a row is clicked, an inline detail section expands below the row:

```html
<tr class="bg-slate-800/30">
  <td colspan="4" class="px-4 py-3">
    <div class="rounded-lg bg-slate-950 border border-slate-800 p-4 max-h-64 overflow-y-auto">
      <p class="text-xs font-medium text-slate-400 mb-2">Error Detail</p>
      <pre class="text-xs font-mono text-rose-300 whitespace-pre-wrap break-words">
        {error_message}
      </pre>
    </div>
  </td>
</tr>
```

If `stdout_ref` or `stderr_ref` are present, render tabs within the detail section: "Error" | "Stdout" | "Stderr". Tab styling follows the standard CCDash tab pattern.

### 6.6 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Table with sortable headers, status badges, duration, error previews |
| **Hover (row)** | `bg-slate-800/50` background |
| **Expanded (row)** | Inline error detail section visible below the row. The row itself gets `bg-slate-800/30` permanently while expanded. |
| **Sorted** | Active column header shows directional chevron. Data reorders. |
| **Filtered** | Only matching rows visible. Filter pills show active state. |
| **Searched** | Only rows matching search query visible. Matched text highlighted with `bg-amber-500/20 text-amber-200 rounded px-0.5`. |
| **Loading** | 5 skeleton rows. Each row: 4 cells with `animate-pulse bg-slate-800 rounded h-4` at varying widths. Header row visible (not skeleton). |
| **Empty (no data)** | Full table container with centered message: `text-sm text-slate-500 italic py-12` "No test results". Icon: `FlaskConical` (size 24, `text-slate-600`) above text. |
| **Empty (filtered)** | Same layout but message: "No matching tests" with a "Clear filters" link in `text-indigo-400 text-xs`. |

### 6.7 Interaction Spec

**Mouse:**
- Click header: Toggles sort direction for that column. First click = ascending, second = descending, third = removes sort.
- Click row: Toggles expanded error detail. If `onTestClick` is provided, also calls it with the `test_id`.
- Click filter pill: Toggles that status in/out of the active filter set.
- Type in search: Debounced (300ms) case-insensitive filter on test name.

**Keyboard:**

| Key | Context | Action |
|-----|---------|--------|
| `Tab` | Table | Moves focus between interactive elements: search input, filter pills, header cells, rows |
| `Enter` | Row focused | Expand/collapse error detail |
| `Escape` | Row expanded | Collapse the expanded detail |
| `Enter` | Header focused | Toggle sort |
| `ArrowUp`/`ArrowDown` | Table body focused | Move focus between rows |

### 6.8 Accessibility

```html
<table aria-label="Test results">
  <thead>
    <tr>
      <th scope="col" aria-sort="{ascending|descending|none}">
        Test Name <SortIcon />
      </th>
      ...
    </tr>
  </thead>
  <tbody>
    <tr
      tabIndex={0}
      aria-expanded="{isExpanded}"
      aria-label="{testName}: {statusLabel}, {duration}"
    >
      ...
    </tr>
    {isExpanded && (
      <tr aria-label="Error details for {testName}">
        ...
      </tr>
    )}
  </tbody>
</table>
```

- Semantic `<table>`, `<thead>`, `<tbody>`, `<th scope="col">` structure.
- `aria-sort` on the currently sorted column header.
- `aria-expanded` on expandable rows.
- `aria-label` on rows for screen reader summary.
- Filter pills use `aria-pressed` to indicate active state.
- Search input has `aria-label="Search tests by name"`.

### 6.9 Pagination

When `results.length > pageSize` (default 50):
- Only the first `pageSize` results render.
- A "Show more" button appears below the table.

```html
<button class="w-full py-3 text-sm text-indigo-400 hover:text-indigo-300
  bg-slate-900 border border-slate-800 rounded-lg mt-2
  focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900">
  Show more (showing {visibleCount} of {totalCount})
</button>
```

Clicking "Show more" increases the visible count by another `pageSize`. This is additive, not full page navigation. Once all results are visible, the button disappears.

### 6.10 Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 640px | Error Preview column hidden. Duration column uses abbreviated format ("120ms" instead of "0.12s"). Filter pills scroll horizontally in a `overflow-x-auto` container. Search input moves below filter pills (full width). |
| 640px-1024px | All columns visible. Table scrolls horizontally if needed (`overflow-x-auto`). |
| >= 1024px | Full layout, no scrolling needed. |
| Minimum container width | 320px |

### 6.11 Animation/Transition Specs

- Row expansion: Animate height from 0 to content height. Use `transition-all duration-200 ease-out` on the detail `<tr>`. The detail content fades in: `transition-opacity duration-200 ease-out` from `opacity-0` to `opacity-100`.
- Sort change: No animation on data reorder (instant re-render).
- Filter change: No animation (instant filter).
- Row hover: `transition-colors duration-100`
- Reduced motion: `motion-reduce:transition-none`

### 6.12 Dependencies

- `TestStatusBadge` (for status column)
- `lucide-react`: Search, ChevronUp, ChevronDown, ChevronsUpDown, FlaskConical
- React: `useState`, `useMemo`, `useCallback`

---

## 7. TestTimeline

A line/area chart showing test pass rate over time, with optional integrity signal markers. Built on Recharts.

### 7.1 Props Interface

```typescript
interface TestTimelineProps {
  /** Timeline data points, one per date. */
  timeline: TimelineDataPoint[];
  /** Whether to render integrity signal markers. Defaults to false. */
  showSignals?: boolean;
  /** Chart height in pixels. Defaults to 200. */
  height?: number;
  /** The date string of the "first green" milestone (all tests passing). */
  firstGreen?: string | null;
  /** The date string of the "last red" milestone (most recent failure). */
  lastRed?: string | null;
  /** Whether the data is loading. */
  isLoading?: boolean;
  /** Additional CSS classes. */
  className?: string;
}
```

Where `TimelineDataPoint` maps from the backend `FeatureTimelinePointDTO`:

```typescript
interface TimelineDataPoint {
  date: string;             // ISO date or "YYYY-MM-DD"
  pass_rate: number;        // 0.0 - 1.0
  passed: number;
  failed: number;
  skipped: number;
  run_ids: string[];
  signals: TestIntegritySignalDTO[];
}
```

### 7.2 Chart Configuration

**Recharts components used:**
- `ResponsiveContainer`
- `AreaChart`
- `Area`
- `XAxis`
- `YAxis`
- `Tooltip`
- `ReferenceLine`
- `ReferenceDot`
- `CartesianGrid`

**Chart layout:**
```typescript
<ResponsiveContainer width="100%" height={height}>
  <AreaChart data={timeline} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
    <defs>
      <linearGradient id="passRateGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#10b981" stopOpacity={0.2} />
        <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
      </linearGradient>
    </defs>

    <CartesianGrid
      strokeDasharray="3 3"
      stroke="#1e293b"
      vertical={false}
    />

    <XAxis
      dataKey="date"
      tickFormatter={formatDateShort}   // "Jan 15", "Feb 1"
      tick={{ fontSize: 11, fill: '#64748b' }}
      axisLine={{ stroke: '#334155' }}
      tickLine={false}
    />

    <YAxis
      domain={[0, 100]}
      tickFormatter={(v) => `${v}%`}
      tick={{ fontSize: 11, fill: '#64748b' }}
      axisLine={false}
      tickLine={false}
      width={40}
    />

    <Tooltip content={<CustomTooltip />} />

    <Area
      type="monotone"
      dataKey="passRatePercent"        // pass_rate * 100
      stroke="#10b981"
      strokeWidth={2}
      fill="url(#passRateGradient)"
      dot={false}
      activeDot={{
        r: 4,
        fill: '#10b981',
        stroke: '#0f172a',
        strokeWidth: 2,
      }}
    />

    {/* Reference lines for milestones */}
    {firstGreen && (
      <ReferenceLine
        x={firstGreen}
        stroke="#10b981"
        strokeDasharray="4 4"
        strokeOpacity={0.5}
        label={{
          value: 'First Green',
          position: 'top',
          fill: '#10b981',
          fontSize: 10,
        }}
      />
    )}

    {lastRed && (
      <ReferenceLine
        x={lastRed}
        stroke="#f43f5e"
        strokeDasharray="4 4"
        strokeOpacity={0.5}
        label={{
          value: 'Last Red',
          position: 'top',
          fill: '#f43f5e',
          fontSize: 10,
        }}
      />
    )}

    {/* Integrity signal markers */}
    {showSignals && signalDates.map(point => (
      <ReferenceDot
        key={point.date}
        x={point.date}
        y={point.passRatePercent}
        r={5}
        fill="#f43f5e"
        stroke="#0f172a"
        strokeWidth={2}
        shape="diamond"
      />
    ))}
  </AreaChart>
</ResponsiveContainer>
```

### 7.3 Custom Tooltip

```typescript
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload as TimelineDataPoint;

  return (
    <div className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs font-medium text-slate-200 mb-1">
        {formatDateFull(label)}
      </p>
      <p className="text-sm font-semibold text-emerald-400">
        {(data.pass_rate * 100).toFixed(1)}% pass rate
      </p>
      <p className="text-xs text-slate-400 mt-1">
        {data.passed + data.failed + data.skipped} tests across {data.run_ids.length} run(s)
      </p>
      {data.signals.length > 0 && (
        <p className="text-xs text-rose-400 mt-1">
          {data.signals.length} integrity signal(s)
        </p>
      )}
    </div>
  );
};
```

### 7.4 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Area chart with emerald gradient, axis labels, optional milestones |
| **Hover** | Active dot appears on the line. Tooltip shows at cursor position. |
| **With signals** | Red diamond markers at dates containing integrity signals |
| **Loading** | `animate-pulse bg-slate-800 rounded-lg` rectangle at the configured height. No axes or labels. |
| **Empty** | Centered within the chart area: `text-sm text-slate-500 italic` "No timeline data". Background: `bg-slate-900 rounded-lg border border-slate-800`. Height matches `height` prop. |
| **Single point** | Renders as a single dot instead of a line. No area fill. |

### 7.5 Interaction Spec

- **Hover on chart**: Recharts handles tooltip display and active dot.
- **Click on signal marker**: Optional. If a click handler is needed, wrap `ReferenceDot` in a custom shape component that handles `onClick`. For V1, signals are informational only (no click interaction).
- **Not keyboard-navigable** in V1. The chart is wrapped in `role="img"` with a descriptive `aria-label`.

### 7.6 Accessibility

```html
<div
  role="img"
  aria-label="Test pass rate timeline from {startDate} to {endDate}.
    Current pass rate: {latestPassRate}%.
    {firstGreen ? `First all-green run: ${firstGreen}.` : ''}
    {lastRed ? `Last failing run: ${lastRed}.` : ''}
    {signalCount > 0 ? `${signalCount} integrity signals detected.` : ''}"
>
  <ResponsiveContainer>
    ...
  </ResponsiveContainer>
</div>
```

- The chart is treated as an image with a comprehensive `aria-label`.
- Individual data points are not individually accessible in V1. Screen reader users rely on the summary label and the adjacent `TestResultTable` for detailed data.

### 7.7 Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 640px | X-axis shows fewer date ticks (every other tick). Y-axis hidden (removed, relying on tooltip for exact values). Height reduced to 160px if not explicitly set. |
| >= 640px | Full axis labels. Default height 200px. |
| Chart width | Always 100% of parent via `ResponsiveContainer`. |

### 7.8 Animation/Transition Specs

- Recharts built-in animations: `isAnimationActive={true}`, `animationDuration={600}`, `animationEasing="ease-in-out"`.
- Reduced motion: Pass `isAnimationActive={false}` when `prefers-reduced-motion: reduce` is detected. Use a `useReducedMotion()` hook or `window.matchMedia('(prefers-reduced-motion: reduce)')`.

### 7.9 Date Formatting

```typescript
/** Short format for X-axis ticks. */
function formatDateShort(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  // Output: "Jan 15", "Feb 1"
}

/** Full format for tooltip header. */
function formatDateFull(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  });
  // Output: "Wed, Jan 15, 2026"
}
```

### 7.10 Dependencies

- `recharts`: ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, ReferenceDot
- `date-fns` (optional, for date formatting -- or use native `toLocaleDateString`)
- React: `useMemo` for data transformation

---

## 8. HealthGauge

A circular SVG progress ring that displays a test health percentage (0-100). Fully specified in the design system document (Section 3). This section provides implementation-level detail and integration guidance.

### 8.1 Props Interface

```typescript
interface HealthGaugeProps {
  /** Health score as a percentage (0-100). */
  score: number;
  /** Size variant. Defaults to 'md'. */
  size?: 'sm' | 'md' | 'lg';
  /** Optional label override. If omitted, derived from score. */
  label?: string;
  /** Whether to show the label text below the percentage. Hidden for 'sm'. Defaults to true. */
  showLabel?: boolean;
  /** Whether to animate the ring on mount/update. Defaults to true. */
  animated?: boolean;
  /** Additional CSS classes on the outer wrapper. */
  className?: string;
}
```

### 8.2 Health Level Derivation

```typescript
function getHealthLevel(score: number): { level: HealthLevel; color: string; label: string } {
  if (score >= 90) return { level: 'healthy',  color: '#10b981', label: 'Healthy' };
  if (score >= 70) return { level: 'degraded', color: '#fbbf24', label: 'Degraded' };
  if (score >= 50) return { level: 'at-risk',  color: '#d97706', label: 'At Risk' };
  return                   { level: 'critical', color: '#f43f5e', label: 'Critical' };
}
```

### 8.3 Size Configuration

| Variant | SVG Size | Stroke Width | Radius | Circumference | Percentage Text | Label Text |
|---------|----------|-------------|--------|---------------|-----------------|------------|
| `sm` | 56x56 | 4px | 24px | `2 * pi * 24 = 150.796` | `text-base font-bold text-slate-100` | Hidden |
| `md` | 80x80 | 6px | 34px | `2 * pi * 34 = 213.628` | `text-xl font-bold text-slate-100` | `text-[10px] font-medium` in health color |
| `lg` | 120x120 | 8px | 52px | `2 * pi * 52 = 326.726` | `text-3xl font-bold text-slate-100` | `text-xs font-medium` in health color |

### 8.4 SVG Implementation

```tsx
const SIZE_CONFIG = {
  sm: { size: 56, stroke: 4, radius: 24, textClass: 'text-base' },
  md: { size: 80, stroke: 6, radius: 34, textClass: 'text-xl' },
  lg: { size: 120, stroke: 8, radius: 52, textClass: 'text-3xl' },
};

function HealthGauge({ score, size = 'md', label, showLabel = true, animated = true, className }: HealthGaugeProps) {
  const config = SIZE_CONFIG[size];
  const { color, label: derivedLabel } = getHealthLevel(score);
  const displayLabel = label ?? derivedLabel;

  const circumference = 2 * Math.PI * config.radius;
  const offset = circumference - (score / 100) * circumference;
  const center = config.size / 2;

  const prefersReducedMotion = useReducedMotion();
  const shouldAnimate = animated && !prefersReducedMotion;

  return (
    <div
      role="meter"
      aria-valuenow={score}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Test health: ${score}% - ${displayLabel}`}
      className={`relative inline-flex items-center justify-center ${className ?? ''}`}
    >
      <svg
        width={config.size}
        height={config.size}
        viewBox={`0 0 ${config.size} ${config.size}`}
      >
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={config.radius}
          fill="none"
          stroke="rgb(30 41 59 / 0.5)"
          strokeWidth={config.stroke}
        />
        {/* Progress arc */}
        <circle
          cx={center}
          cy={center}
          r={config.radius}
          fill="none"
          stroke={color}
          strokeWidth={config.stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={shouldAnimate ? {
            transition: 'stroke-dashoffset 0.6s ease-in-out',
          } : undefined}
        />
      </svg>

      {/* Centered text overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`${config.textClass} font-bold text-slate-100`}>
          {score}%
        </span>
        {showLabel && size !== 'sm' && (
          <span
            className={`${size === 'lg' ? 'text-xs' : 'text-[10px]'} font-medium`}
            style={{ color }}
          >
            {displayLabel}
          </span>
        )}
      </div>
    </div>
  );
}
```

### 8.5 Visual States

| State | Behavior |
|-------|----------|
| **Default** | Ring filled proportionally to score. Percentage text centered. Label below (md/lg). |
| **Score 0** | Empty ring (only track visible). Text shows "0%". Label shows "Critical". |
| **Score 100** | Full ring. Text shows "100%". Label shows "Healthy". |
| **Animating** | Ring fills from 0 to target on mount. Duration: 600ms, ease-in-out. |
| **Score update** | Ring transitions from previous offset to new offset. Same 600ms timing. |
| **Loading** | `animate-pulse` circle placeholder: `bg-slate-800 rounded-full` at the configured size. No text. |

### 8.6 Interaction Spec

- **Not interactive.** The gauge is purely informational.
- **Not focusable** (no tabIndex).
- Parent components may wrap it in a clickable container.

### 8.7 Accessibility

```html
<div
  role="meter"
  aria-valuenow="{score}"
  aria-valuemin="0"
  aria-valuemax="100"
  aria-label="Test health: {score}% - {label}"
>
```

- `role="meter"` is the correct ARIA role for a gauge/meter display.
- The full description is in `aria-label`, making the visual SVG purely decorative to screen readers.

### 8.8 Responsive Behavior

- No breakpoint-specific changes. The parent component selects the appropriate `size` prop.
- The SVG is inline and does not stretch beyond its configured size.

### 8.9 Animation/Transition Specs

- Ring fill: `transition: stroke-dashoffset 0.6s ease-in-out` on the progress `<circle>`.
- Reduced motion: `@media (prefers-reduced-motion: reduce)` disables the transition entirely (instant render).
- Implementation: Use a `useReducedMotion()` hook that checks `window.matchMedia('(prefers-reduced-motion: reduce)')`.

### 8.10 Integration Contexts

The HealthGauge is used in several locations with different size preferences:

| Context | Size | Notes |
|---------|------|-------|
| Main test dashboard header | `lg` | Centered in a stat card |
| Domain tree node inline | `sm` | Positioned right of the node name as an alternative to the health % text |
| Feature test health card | `md` | Within a card alongside summary text |
| Session detail test tab | `md` | Paired with HealthSummaryBar below it |

### 8.11 Dependencies

- No external dependencies. Pure SVG + React implementation.
- Utility hook: `useReducedMotion()` (shared utility).

### 8.12 useReducedMotion Hook

```typescript
import { useState, useEffect } from 'react';

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return reduced;
}
```

---

## Appendix A: Component Dependency Graph

```
TestTimeline
  └── (recharts)

DomainTreeView
  └── HealthSummaryBar
  └── (lucide-react)

TestResultTable
  └── TestStatusBadge
  └── (lucide-react)

TestRunCard
  └── HealthSummaryBar
  └── TestStatusBadge (optional, for trigger)
  └── (date-fns)

IntegrityAlertCard
  └── (lucide-react)
  └── (date-fns)

HealthSummaryBar
  └── (no component deps)

TestStatusBadge
  └── (lucide-react)

HealthGauge
  └── (no deps)
```

## Appendix B: File Organization

All test visualizer components should live under:

```
components/test-visualizer/
  types.ts                  # Shared types (TestStatus, HealthLevel, etc.)
  constants.ts              # STATUS_CONFIG, STATUS_PRIORITY, SIZE_CONFIG
  hooks/
    useReducedMotion.ts     # Shared reduced-motion hook
  TestStatusBadge.tsx
  TestRunCard.tsx
  IntegrityAlertCard.tsx
  HealthSummaryBar.tsx
  DomainTreeView.tsx
  TestResultTable.tsx
  TestTimeline.tsx
  HealthGauge.tsx
```

## Appendix C: Focus Ring Standard

All focusable interactive elements across these components use the same focus ring:

```
focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500
  focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900
```

This matches the existing CCDash focus style and provides visible keyboard focus indicators against the dark background.
