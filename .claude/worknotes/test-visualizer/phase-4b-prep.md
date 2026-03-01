---
type: context
schema_version: 2
doc_type: context
prd: "test-visualizer"
feature_slug: "test-visualizer"
created: 2026-02-28
updated: 2026-02-28
---

# Phase 4B Execution Prep

**Batch 2 Tasks**: TASK-4.2, TASK-4.3, TASK-4.6, TASK-4.7, TASK-4.8
**Tools Required**: gemini-cli, nano-banana, ui-designer agent

## Tool Availability

- `gemini` CLI: v0.30.0 at `/opt/homebrew/bin/gemini`
- `nano-banana` CLI: at `/Users/miethe/.bun/bin/nano-banana`
- Both tools confirmed operational

## Task-Tool Mapping

| Task | Description | Tools | Agent |
|------|-------------|-------|-------|
| TASK-4.2 | Testing Page wireframes | gemini (UI mockup), nano-banana (visual), ui-designer | ui-designer + gemini-orchestrator |
| TASK-4.3 | Feature Modal tab design | ui-designer (text spec) | ui-designer |
| TASK-4.6 | Component specs: badges and cards | ui-designer (text spec) | ui-designer + ui-engineer |
| TASK-4.7 | Component specs: tree and table | ui-designer (text spec) | ui-designer + ui-engineer |
| TASK-4.8 | Component specs: charts and gauges | ui-designer (text spec) | ui-designer + ui-engineer |

## Gemini Wireframe Generation Prompts

### TASK-4.2: Testing Page Mockup

```bash
gemini "Generate a UI mockup image for a Testing Page in a dark-themed developer dashboard.

Context: Full-page test visualizer with domain tree navigation on the left and detail panels on the right. The page is part of CCDash, a dark-mode developer dashboard using bg-slate-950 backgrounds, slate-900 cards, indigo-500 accents.

Layout requirements:
- Top header bar: 'Test Visualizer' title, global health gauge (87% Healthy in emerald), test count (1,234 tests), failing count (23 failing in rose), Refresh button
- Left sidebar (250px): Collapsible domain tree with health percentages per node. Nodes have color-coded left borders (emerald for healthy, amber for degraded, rose for critical). Filter panel at bottom with status checkboxes and run dropdown.
- Right detail panel (remaining width): Shows selected domain/feature with health summary bar (emerald/rose/amber stacked bar), test results table (sortable columns: Test Name, Status badge, Duration, Error Preview), and integrity alerts section at bottom (cards with severity left borders).

Design requirements:
- Dark theme: bg-slate-950 page, bg-slate-900 cards, border-slate-800 dividers
- Status badges: emerald for pass, rose for fail, amber for skip
- Health gauge: circular progress ring, emerald colored, 87% text center
- Table rows: hover state bg-slate-800, alternating subtle backgrounds
- Tree nodes: indigo highlight on selected, chevron icons for expand/collapse

Dimensions: 1440x900px, aspect ratio 16:10
Style: clean production UI, not wireframe - realistic dark mode dashboard" --yolo -o text
```

### TASK-4.2: Domain Tree Close-Up

```bash
nano-banana "Dark mode developer dashboard sidebar showing a collapsible test domain tree navigation. Slate-900 background. Tree nodes show: chevron icon, domain name, health percentage badge. Selected node highlighted with indigo-500 border. Nodes have color-coded left borders: green for healthy, amber for degraded, red for critical. Expanded and collapsed states visible. Clean minimal design." -s 1K -a 9:16 -o testing-page-domain-tree -d docs/project_plans/designs/test-visualizer/
```

### TASK-4.2: Detail Panel Close-Up

```bash
nano-banana "Dark mode dashboard detail panel showing test results. Slate-950 background. Contains: health summary bar (stacked horizontal bar in green/red/amber), sortable test results table with status badges (green checkmark, red X, amber dash), duration column, and error preview column. Below the table: integrity alert card with red left border and shield icon. Clean minimal dark UI." -s 1K -a 4:3 -o testing-page-detail-panel -d docs/project_plans/designs/test-visualizer/
```

## Existing CCDash Patterns (Context for Agents)

### Layout Structure
- Layout.tsx has sidebar with `#sidebar-portal` div for page-specific filters
- Sidebar width: 256px (w-64) or 80px (w-20) collapsed
- Main content: `flex-1` takes remaining width
- Nav items use `NavItem` component with Lucide icons

### Existing Nav Items (for reference)
- Overview, Project Board, Execution, Documents, Session Forensics
- Codebase Explorer, Session Mappings, Operations, Analytics, SkillMeat Context
- New "Test Visualizer" item will use `TestTube2` icon at route `/tests`

### Card Pattern
```
bg-slate-900 border border-slate-800 rounded-xl p-5
```

### Badge Pattern
```
inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold
border-{color}-500/45 bg-{color}-500/12 text-{color}-200
```

### Chart Library
Recharts v3.7.0 — use AreaChart, BarChart for timeline/trends

## Design System Reference

All visual language defined in:
`docs/project_plans/designs/test-visualizer/design-system.md`

Key sections:
- Section 2: Test Status Visual Language (8 status types with full Tailwind classes)
- Section 3: Health Gauge Design (SVG spec, 3 sizes)
- Section 4: Integrity Signal Severity (3 levels with card styling)
- Section 5: Health Summary Bar (stacked bar spec)
- Section 9: Color Reference Table (complete semantic color map)

## Output Files for 4B

| Task | Output Path |
|------|-------------|
| TASK-4.2 | `docs/project_plans/designs/test-visualizer/testing-page-wireframes.md` |
| TASK-4.3 | `docs/project_plans/designs/test-visualizer/tab-designs.md` (Feature Modal section) |
| TASK-4.6 | `docs/project_plans/designs/test-visualizer/component-specs.md` (badges & cards) |
| TASK-4.7 | `docs/project_plans/designs/test-visualizer/component-specs.md` (tree & table) |
| TASK-4.8 | `docs/project_plans/designs/test-visualizer/component-specs.md` (charts & gauges) |

## Execution Strategy

1. Run gemini mockup for Testing Page (TASK-4.2) — generates visual reference
2. Run nano-banana close-ups for tree and detail panel (TASK-4.2)
3. In parallel, delegate TASK-4.3, 4.6, 4.7, 4.8 to ui-designer agents
4. All agents reference design-system.md for visual language consistency
5. Generated images go to `docs/project_plans/designs/test-visualizer/` alongside specs
