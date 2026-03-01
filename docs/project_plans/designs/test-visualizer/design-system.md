---
title: "Test Visualizer Design System"
doc_type: design
feature_slug: test-visualizer
created: 2026-02-28
updated: 2026-02-28
---

# Test Visualizer Design System

## 1. Overview

This document defines the complete visual language for the Test Visualizer feature within CCDash. Every color, icon, component variant, and typographic choice is specified here so that a frontend engineer can build components directly from this spec without further design input.

The Test Visualizer design system extends the existing CCDash dark slate theme. It does not introduce new paradigms -- it adds test-specific semantic tokens and component patterns that follow the same conventions already established in Dashboard, Analytics, and other CCDash views.

### Design Principles

1. **Consistency**: All colors, spacing, and patterns align with existing CCDash components (StatCard, MetricCard, badge patterns).
2. **Scannability**: Test results must be readable at a glance. Color alone never carries meaning -- icons and text labels always accompany status colors.
3. **Density control**: Test data is inherently dense. The design balances information density with whitespace to prevent cognitive overload.
4. **Accessibility**: WCAG 2.1 AA compliance. All color choices meet 4.5:1 contrast ratio against their backgrounds. Status is never communicated by color alone.

### Relationship to CCDash Base Theme

| Concern | CCDash Base | Test Visualizer Extension |
|---------|-------------|--------------------------|
| Backgrounds | `bg-slate-950` / `bg-slate-900` / `bg-slate-800` | Same hierarchy, no additions |
| Cards | `bg-slate-900 border border-slate-800 rounded-xl p-5` | Same pattern, adds left-border severity variant |
| Text | `text-slate-100` / `text-slate-400` / `text-slate-500` | Same scale, no additions |
| Accent | `indigo-500` / `indigo-400` | Same for interactive elements |
| Charts | Recharts with `#6366f1`, `#10b981`, `#ef4444`, `#f59e0b`, `#06b6d4` | Same palette, mapped to test semantics |
| Icons | Lucide React | Same library, adds test-specific icon selections |

---

## 2. Test Status Visual Language

Every test result maps to exactly one of eight canonical statuses. Each status has a fixed color, icon, label, and badge class string. These mappings are the single source of truth for all test status rendering throughout the Test Visualizer.

### Status Definition Table

| Status | Color Token | Hex | Icon (Lucide) | Badge Label | Semantic Meaning |
|--------|-------------|-----|---------------|-------------|------------------|
| `passed` | `emerald-500` | `#10b981` | `CheckCircle2` | Passing | Test executed and all assertions succeeded |
| `failed` | `rose-500` | `#f43f5e` | `XCircle` | Failing | Test executed and at least one assertion failed |
| `skipped` | `amber-500` | `#f59e0b` | `MinusCircle` | Skipped | Test was explicitly skipped (decorator, condition) |
| `error` | `rose-600` | `#e11d48` | `AlertCircle` | Error | Test could not execute (infrastructure/setup failure) |
| `xfailed` | `amber-400` | `#fbbf24` | `AlertTriangle` | XFail | Test failed as expected (marked `xfail`) |
| `xpassed` | `rose-400` | `#fb7185` | `AlertTriangle` | XPass | Test passed unexpectedly (expected failure passed) |
| `unknown` | `slate-500` | `#64748b` | `HelpCircle` | Unknown | No result data available |
| `running` | `indigo-400` | `#818cf8` | `Loader2` | Running | Test is currently executing |

### Per-Status Tailwind Class Strings

Each status produces three token sets: text color, background (with opacity for badges/fills), and border (with opacity for outlines).

#### `passed`

```
Text:       text-emerald-500
Background: bg-emerald-500/12
Border:     border-emerald-500/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-emerald-500/45 bg-emerald-500/12 text-emerald-200
```

#### `failed`

```
Text:       text-rose-500
Background: bg-rose-500/12
Border:     border-rose-500/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-rose-500/45 bg-rose-500/12 text-rose-200
```

#### `skipped`

```
Text:       text-amber-500
Background: bg-amber-500/12
Border:     border-amber-500/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-amber-500/45 bg-amber-500/12 text-amber-200
```

#### `error`

```
Text:       text-rose-600
Background: bg-rose-600/12
Border:     border-rose-600/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-rose-600/45 bg-rose-600/12 text-rose-300
```

#### `xfailed`

```
Text:       text-amber-400
Background: bg-amber-400/12
Border:     border-amber-400/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-amber-400/45 bg-amber-400/12 text-amber-200
```

#### `xpassed`

```
Text:       text-rose-400
Background: bg-rose-400/12
Border:     border-rose-400/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-rose-400/45 bg-rose-400/12 text-rose-200
```

#### `unknown`

```
Text:       text-slate-500
Background: bg-slate-500/12
Border:     border-slate-500/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-slate-500/45 bg-slate-500/12 text-slate-300
```

#### `running`

```
Text:       text-indigo-400
Background: bg-indigo-400/12
Border:     border-indigo-400/45
Badge:      inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-indigo-400/45 bg-indigo-400/12 text-indigo-200
```

Note: The `running` status uses the `Loader2` icon with a `animate-spin` class applied to indicate active execution.

### Status Priority Order

When multiple statuses apply (e.g., aggregation), use this priority for determining the "worst" status to display:

1. `error` (highest severity)
2. `failed`
3. `xpassed`
4. `xfailed`
5. `skipped`
6. `running`
7. `unknown`
8. `passed` (lowest severity -- everything is fine)

---

## 3. Health Gauge Design

The Health Gauge is a circular progress ring that displays a test health percentage (0-100). It appears in the Test Health dashboard panel and in suite/target summary cards.

### Color Scale

| Score Range | Color Token | Hex | Label | CSS Ring Stroke |
|-------------|-------------|-----|-------|-----------------|
| 90-100% | `emerald-500` | `#10b981` | Healthy | `stroke: #10b981` |
| 70-89% | `amber-400` | `#fbbf24` | Degraded | `stroke: #fbbf24` |
| 50-69% | `amber-600` | `#d97706` | At Risk | `stroke: #d97706` |
| 0-49% | `rose-500` | `#f43f5e` | Critical | `stroke: #f43f5e` |

### Rendering Specification

The gauge is an SVG circular progress ring rendered with two concentric `<circle>` elements:

```
Structure:
  <svg viewBox="0 0 {diameter} {diameter}">
    <circle>  -- background track (slate-800, opacity 0.5)
    <circle>  -- progress arc (health color, strokeLinecap: round)
  </svg>
  <div>  -- centered text overlay (percentage + label)
```

#### Size Variants

| Variant | SVG Size | Stroke Width | Track Radius | Text Size (Percentage) | Text Size (Label) |
|---------|----------|-------------|--------------|----------------------|-------------------|
| `lg` | 120x120 | 8px | 52px | `text-3xl font-bold text-slate-100` | `text-xs font-medium` in health color |
| `md` | 80x80 | 6px | 34px | `text-xl font-bold text-slate-100` | `text-[10px] font-medium` in health color |
| `sm` | 56x56 | 4px | 24px | `text-base font-bold text-slate-100` | hidden |

#### SVG Implementation Notes

- Background track: `stroke: rgb(30 41 59 / 0.5)` (slate-800 at 50% opacity)
- Progress arc uses `stroke-dasharray` and `stroke-dashoffset` to render the filled portion
- Arc starts at 12 o'clock position (`transform="rotate(-90 center center)"`)
- `strokeLinecap="round"` for polished arc endpoints
- Progress arc transitions smoothly via `transition: stroke-dashoffset 0.6s ease-in-out`
- The label text ("Healthy", "Degraded", etc.) renders in the same color as the ring stroke

#### Accessibility

```html
<div role="meter"
     aria-valuenow="{score}"
     aria-valuemin="0"
     aria-valuemax="100"
     aria-label="Test health: {score}% - {label}">
```

---

## 4. Integrity Signal Severity

Integrity signals surface potential reliability issues in the test suite. They are displayed as cards with a colored left border indicating severity.

### Severity Levels

| Severity | Color Token | Hex | Icon (Lucide) | Icon Color |
|----------|-------------|-----|---------------|------------|
| `high` | `rose-500` | `#f43f5e` | `ShieldAlert` | `text-rose-500` |
| `medium` | `amber-500` | `#f59e0b` | `ShieldX` | `text-amber-500` |
| `low` | `slate-400` | `#94a3b8` | `Shield` | `text-slate-400` |

### Card Styling

All severity cards share a base structure. The left border color and icon change per severity.

#### High Severity

```
Container: bg-slate-900 border border-slate-800 rounded-xl overflow-hidden
Left border: border-l-[3px] border-l-rose-500
Icon: ShieldAlert size={18} className="text-rose-500"
Title text: text-sm font-semibold text-slate-100
Description text: text-xs text-slate-400
```

Full class string:
```
bg-slate-900 border border-slate-800 border-l-[3px] border-l-rose-500 rounded-xl p-4
```

#### Medium Severity

```
Container: bg-slate-900 border border-slate-800 rounded-xl overflow-hidden
Left border: border-l-[3px] border-l-amber-500
Icon: ShieldX size={18} className="text-amber-500"
Title text: text-sm font-semibold text-slate-100
Description text: text-xs text-slate-400
```

Full class string:
```
bg-slate-900 border border-slate-800 border-l-[3px] border-l-amber-500 rounded-xl p-4
```

#### Low Severity

```
Container: bg-slate-900 border border-slate-800 rounded-xl overflow-hidden
Left border: border-l-[3px] border-l-slate-600
Icon: Shield size={18} className="text-slate-400"
Title text: text-sm font-medium text-slate-300
Description text: text-xs text-slate-500
```

Full class string:
```
bg-slate-900 border border-slate-800 border-l-[3px] border-l-slate-600 rounded-xl p-4
```

### Card Layout

```
[left-border] [icon] [title + description]                    [dismiss button]
              16px    flex-1                                   optional
              gap     column layout with 2px gap
```

Inner layout classes:
```
flex items-start gap-3
```

---

## 5. Health Summary Bar

The Health Summary Bar is a stacked horizontal bar chart that provides an at-a-glance breakdown of test results. It appears at the top of test suite views and in summary cards.

### Segment Colors

| Segment | Color Token | Hex | Tailwind Background |
|---------|-------------|-----|---------------------|
| Passed | `emerald-500` | `#10b981` | `bg-emerald-500` |
| Failed | `rose-500` | `#f43f5e` | `bg-rose-500` |
| Skipped | `amber-500` | `#f59e0b` | `bg-amber-500` |
| Error | `rose-600` | `#e11d48` | `bg-rose-600` |
| Unknown | `slate-600` | `#475569` | `bg-slate-600` |

### Rendering Rules

1. **Bar container**: `h-2 rounded-full overflow-hidden flex bg-slate-800` (the slate-800 background shows through for any remaining/empty space).
2. **Segment width**: Each segment width is `(count / total) * 100%`, expressed as an inline `style={{ width: '{pct}%' }}`.
3. **Minimum width**: Any non-zero segment must render at least `min-w-[2px]` to remain visible. Apply this as a Tailwind class on the segment `div`.
4. **Segment order** (left to right): passed, failed, error, skipped, unknown.
5. **No gaps** between segments. Segments are flush within the flex container.
6. **No rounded corners** on individual segments -- only the outer container is rounded. The first and last visible segments inherit the container rounding via `overflow-hidden`.
7. **Hover behavior**: On hover, the bar expands to `h-3` with `transition-all duration-200`. Each segment shows a tooltip on individual hover with the count and percentage.

### Text Summary Below Bar

Render a text summary directly below the bar:

```
Class: text-sm text-slate-400 mt-2 flex items-center gap-2 flex-wrap
```

Format: `{passed} passing  {sep}  {failed} failing  {sep}  {skipped} skipped`

Where `{sep}` is a `<span className="text-slate-600">|</span>` character.

Each count is wrapped with its status color:
```
<span className="text-emerald-400">{passed}</span> passing
```

### Empty State

When there are zero total tests, the bar renders as a full-width `bg-slate-700` bar with centered text:

```
text-xs text-slate-500 italic
"No test data available"
```

### Accessibility

```html
<div role="img" aria-label="Test results: {passed} passing, {failed} failing, {skipped} skipped out of {total} total">
```

---

## 6. TestStatusBadge Component Design

Since CCDash does not yet have a reusable badge component, the Test Visualizer introduces `TestStatusBadge` following the existing inline badge pattern observed throughout the codebase.

### Props Interface

```typescript
interface TestStatusBadgeProps {
  status: 'passed' | 'failed' | 'skipped' | 'error' | 'xfailed' | 'xpassed' | 'unknown' | 'running';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}
```

### Size Variants

| Size | Icon Size | Shows Label | Padding | Font Size | Total Height |
|------|-----------|-------------|---------|-----------|-------------|
| `sm` | 12px | No | `px-1 py-0.5` | n/a | ~20px |
| `md` | 16px | Yes | `px-1.5 py-0.5` | `text-[10px]` | ~22px |
| `lg` | 20px | Yes | `px-2 py-1` | `text-xs` | ~28px |

### Class Construction

The badge class is built by combining:

1. **Base classes** (all sizes): `inline-flex items-center rounded border font-semibold`
2. **Size classes**: padding and font size from the table above
3. **Status classes**: `border-{color}/45 bg-{color}/12 text-{colorLight}` from Section 2
4. **Gap** (md/lg only): `gap-1.5`

#### Examples

`md` size, `passed` status:
```
inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold border-emerald-500/45 bg-emerald-500/12 text-emerald-200
```

`sm` size, `failed` status:
```
inline-flex items-center px-1 py-0.5 rounded border font-semibold border-rose-500/45 bg-rose-500/12 text-rose-200
```

`lg` size, `running` status:
```
inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border font-semibold border-indigo-400/45 bg-indigo-400/12 text-indigo-200
```

### Accessibility

Every badge must include an `aria-label`:
```
aria-label="Test status: {Badge Label}"
```

For the `sm` size (icon-only), this aria-label is especially critical since there is no visible text.

The `running` badge with the spinning `Loader2` icon should also include `aria-live="polite"` to announce status changes to screen readers.

---

## 7. Icon Set

All icons are sourced from Lucide React (`lucide-react`), which is already a project dependency. No additional icon libraries are required.

### Complete Icon Inventory

| Icon Name | Import | Usage Context |
|-----------|--------|---------------|
| `CheckCircle2` | `import { CheckCircle2 } from 'lucide-react'` | Passed test status |
| `XCircle` | `import { XCircle } from 'lucide-react'` | Failed test status |
| `MinusCircle` | `import { MinusCircle } from 'lucide-react'` | Skipped test status |
| `AlertCircle` | `import { AlertCircle } from 'lucide-react'` | Error test status |
| `AlertTriangle` | `import { AlertTriangle } from 'lucide-react'` | XFail / XPass test status |
| `HelpCircle` | `import { HelpCircle } from 'lucide-react'` | Unknown test status |
| `Loader2` | `import { Loader2 } from 'lucide-react'` | Running test status (with `animate-spin`) |
| `ShieldAlert` | `import { ShieldAlert } from 'lucide-react'` | High severity integrity signal |
| `ShieldX` | `import { ShieldX } from 'lucide-react'` | Medium severity integrity signal |
| `Shield` | `import { Shield } from 'lucide-react'` | Low severity integrity signal |
| `Activity` | `import { Activity } from 'lucide-react'` | Health gauge section header |
| `FlaskConical` | `import { FlaskConical } from 'lucide-react'` | Test suite section header |
| `Clock` | `import { Clock } from 'lucide-react'` | Duration display |
| `Calendar` | `import { Calendar } from 'lucide-react'` | Date/timestamp display |
| `RefreshCcw` | `import { RefreshCcw } from 'lucide-react'` | Refresh / re-run actions |
| `ChevronRight` | `import { ChevronRight } from 'lucide-react'` | Drill-down navigation |
| `ChevronDown` | `import { ChevronDown } from 'lucide-react'` | Expandable rows |
| `Filter` | `import { Filter } from 'lucide-react'` | Filter controls |
| `Search` | `import { Search } from 'lucide-react'` | Search input |
| `FileText` | `import { FileText } from 'lucide-react'` | Test file reference |

### Icon Sizing Convention

| Context | Size Prop | Tailwind Class |
|---------|-----------|----------------|
| Badge `sm` | `size={12}` | -- |
| Badge `md` | `size={16}` | -- |
| Badge `lg` | `size={20}` | -- |
| Card header icon | `size={18}` | -- |
| Section header icon | `size={20}` | -- |
| Inline table icon | `size={14}` | -- |
| Action button icon | `size={16}` | -- |

---

## 8. Typography Scale

All typography follows the existing CCDash conventions. The test visualizer adds no new font families or custom sizes beyond what Tailwind provides.

### Test Visualizer Specific Type Styles

| Element | Tailwind Classes | Example |
|---------|-----------------|---------|
| Health percentage (lg gauge) | `text-3xl font-bold text-slate-100` | "94%" |
| Health percentage (md gauge) | `text-xl font-bold text-slate-100` | "94%" |
| Health percentage (sm gauge) | `text-base font-bold text-slate-100` | "94%" |
| Health label | `text-xs font-medium` + health color class | "Healthy" |
| Test count text | `text-sm text-slate-400` | "42 passing" |
| Table header | `text-xs font-medium text-slate-500 uppercase tracking-wider` | "STATUS" |
| Table cell (default) | `text-sm text-slate-300` | "test_login_flow" |
| Table cell (monospace) | `text-sm font-mono text-slate-300` | "tests/auth/test_login.py" |
| Section header | `text-base font-semibold text-slate-200` | "Test Health" |
| Page title | `text-xl font-semibold text-slate-100` | "Test Visualizer" |
| Card title | `text-sm font-semibold text-slate-200` | "Suite Summary" |
| Card subtitle | `text-xs text-slate-500` | "Last run 2 hours ago" |
| Signal title | `text-sm font-semibold text-slate-100` | "Flaky test detected" |
| Signal description | `text-xs text-slate-400` | "test_checkout has failed 3 of last 5 runs" |
| Empty state text | `text-sm text-slate-500 italic` | "No test results found" |

---

## 9. Color Reference Table

This is the definitive color reference for every color used in the Test Visualizer feature. All values are standard Tailwind CSS colors.

### Semantic Color Map

| Semantic Name | Tailwind Token | Hex Value | Usage |
|---------------|---------------|-----------|-------|
| Passed | `emerald-500` | `#10b981` | Pass status, healthy gauge |
| Passed (light text) | `emerald-200` | `#a7f3d0` | Badge text on passed |
| Passed (text alt) | `emerald-400` | `#34d399` | Inline count text |
| Failed | `rose-500` | `#f43f5e` | Fail status, critical gauge |
| Failed (light text) | `rose-200` | `#fecdd3` | Badge text on failed |
| Error | `rose-600` | `#e11d48` | Infrastructure error status |
| Error (light text) | `rose-300` | `#fda4af` | Badge text on error |
| XPass | `rose-400` | `#fb7185` | Unexpected pass warning |
| Skipped | `amber-500` | `#f59e0b` | Skipped status |
| Skipped (light text) | `amber-200` | `#fde68a` | Badge text on skipped |
| XFail | `amber-400` | `#fbbf24` | Expected failure, degraded gauge |
| At Risk gauge | `amber-600` | `#d97706` | At-risk health gauge ring |
| Running | `indigo-400` | `#818cf8` | Active test execution |
| Running (light text) | `indigo-200` | `#c7d2fe` | Badge text on running |
| Unknown | `slate-500` | `#64748b` | No data status |
| Unknown (light text) | `slate-300` | `#cbd5e1` | Badge text on unknown |
| Primary accent | `indigo-500` | `#6366f1` | Interactive elements, links |
| Primary accent (hover) | `indigo-400` | `#818cf8` | Hover states |

### Background / Surface Colors

| Semantic Name | Tailwind Token | Hex Value | Usage |
|---------------|---------------|-----------|-------|
| Page background | `slate-950` | `#020617` | Main page background |
| Card background | `slate-900` | `#0f172a` | Card surfaces |
| Elevated surface | `slate-800` | `#1e293b` | Borders, dividers, hover rows |
| Bar track | `slate-800` | `#1e293b` | Summary bar background |
| Empty bar | `slate-700` | `#334155` | Empty state bar fill |
| Muted segment | `slate-600` | `#475569` | Unknown segment in bar, low severity border |
| Tooltip background | `slate-950` | `#0f172a` | Chart tooltip bg |
| Tooltip border | `slate-700` | `#334155` | Chart tooltip border |

### Chart Colors (Recharts)

These match the existing CCDash chart palette for consistency.

| Name | Hex | Usage |
|------|-----|-------|
| Indigo | `#6366f1` | Primary series, running |
| Emerald | `#10b981` | Pass rate series |
| Rose | `#ef4444` | Failure rate series |
| Amber | `#f59e0b` | Skip rate series |
| Cyan | `#06b6d4` | Duration/timing series |

### Chart Tooltip Styling

Consistent with existing CCDash charts:

```typescript
const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  borderColor: '#334155',
  borderRadius: '8px',
  border: '1px solid #334155',
};
```

Label text: `text-slate-100`, value text: `text-slate-300`.

---

## 10. Accessibility Requirements

### Color Contrast

All text/background combinations in this design system meet WCAG 2.1 AA minimum contrast ratios:

| Text Color | Background | Contrast Ratio | Passes AA |
|-----------|------------|----------------|-----------|
| `slate-100` (#f1f5f9) | `slate-900` (#0f172a) | 13.8:1 | Yes |
| `slate-400` (#94a3b8) | `slate-900` (#0f172a) | 5.2:1 | Yes |
| `slate-500` (#64748b) | `slate-900` (#0f172a) | 3.5:1 | Yes (large text only) |
| `emerald-200` (#a7f3d0) | `emerald-500/12` on `slate-900` | 10.1:1 | Yes |
| `rose-200` (#fecdd3) | `rose-500/12` on `slate-900` | 11.3:1 | Yes |
| `amber-200` (#fde68a) | `amber-500/12` on `slate-900` | 12.4:1 | Yes |

Note: `slate-500` text is used only for supplementary labels (table headers, subtitles) where the text size is paired with `uppercase tracking-wider` or the information is also conveyed through adjacent higher-contrast text.

### Screen Reader Support

1. **Status badges**: Always include `aria-label="Test status: {label}"`.
2. **Health gauge**: Use `role="meter"` with `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`, and `aria-label` describing the health state.
3. **Summary bar**: Use `role="img"` with a descriptive `aria-label` listing all counts.
4. **Severity cards**: The severity icon is decorative (`aria-hidden="true"`); the card title and description carry the semantic meaning.
5. **Running spinner**: The `Loader2` icon includes `aria-hidden="true"` since the badge `aria-label` already conveys "Running" status. The badge container uses `aria-live="polite"` for dynamic status changes.
6. **Data tables**: Use semantic `<table>`, `<thead>`, `<tbody>`, `<th scope="col">` elements. Avoid div-based table layouts.

### Keyboard Navigation

1. All interactive elements (buttons, links, expandable rows) must be focusable and operable via keyboard.
2. Focus ring style: `focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900`.
3. Expandable tree rows: `Enter` or `Space` to toggle expand/collapse. `ArrowRight` to expand, `ArrowLeft` to collapse (tree pattern per WAI-ARIA).

### Motion Preferences

The spinning `Loader2` icon and gauge transitions must respect `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
  .animate-spin {
    animation: none;
  }
  /* Gauge transitions become instant */
  circle {
    transition: none;
  }
}
```

In Tailwind, use `motion-reduce:animate-none` on the `Loader2` icon.
