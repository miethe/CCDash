---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 4
title: Planning Graph Reskin & Enhancements
status: completed
created: '2026-04-20'
updated: '2026-04-20'
started: null
completed: null
commit_refs:
- 361b3fc
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- react-performance-optimizer
contributors:
- frontend-developer
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T4-001
  description: Reskin lane headers with colored square glyphs and sticky positioning;
    reskin feature cells with category badge, complexity chip, mismatch/stale indicators,
    2-line title clamp, status pill
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - T2-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T4-002
  description: Implement DocChip component with type label, truncated title, status
    dot; support multiple stacked chips per lane cell; mute completed/superseded artifacts
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - T4-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T4-003
  description: Implement PhaseDot (filled=completed, pulsing ring=in-progress, !=blocked)
    and PhaseStackInline showing completed/total count in progress lane
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - react-performance-optimizer
  dependencies:
  - T4-001
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
- id: T4-004
  description: "Implement TotalsCell showing story-points, total tokens, stacked model-identity\
    \ bar (opus/sonnet/haiku proportional widths), per-model token counts with colored\
    \ dots. Data source: server-provided feature.tokenUsage from PlanningQueryService\
    \ / FeatureForensicsQueryService (total_tokens + per-model tokenUsageByModel delivered\
    \ by T7-004) \u2014 actual session-forensics tokens, not client-side estimates"
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - react-performance-optimizer
  dependencies:
  - T4-002
  - T4-003
  - T7-004
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T4-005
  description: Add SVG edge layer with animated dashed flow edges for active features
    (brand color); static edges for inactive; no performance regression
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - react-performance-optimizer
  dependencies:
  - T4-004
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T4-006
  description: Add graph filter controls dropdown (All categories/features/enhancements/refactors/spikes)
    and artifact legend below graph with color swatches and animated edge example
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - T4-005
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
parallelization:
  batch_1:
  - T4-001
  batch_2:
  - T4-002
  - T4-003
  batch_3:
  - T4-004
  batch_4:
  - T4-005
  batch_5:
  - T4-006
  critical_path:
  - T4-001
  - T4-002
  - T4-004
  - T4-005
  - T4-006
  estimated_total_time: 4-5 days
blockers: []
success_criteria:
- id: SC-4.1
  description: Lane headers sticky and match design
  status: pending
- id: SC-4.2
  description: DocChips render for multi-artifact lanes
  status: pending
- id: SC-4.3
  description: PhaseStackInline with PhaseDots in all 3 states
  status: pending
- id: SC-4.4
  description: TotalsCell shows points and server-provided actual tokens from session
    forensics (total + per-model bar via feature.tokenUsageByModel); no client-side
    estimation
  status: pending
- id: SC-4.5
  description: SVG edges animated and performant
  status: pending
- id: SC-4.6
  description: Filter controls and legend functional
  status: pending
- id: SC-4.7
  description: Graph render time <=1.5s for 50 features
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 4: Planning Graph Reskin & Enhancements

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-4-progress.md \
  -t T4-001 -s completed
```

---

## Phase Overview

**Title**: Planning Graph Reskin & Enhancements
**Dependencies**: Phase 2 complete (T2-001 — metrics/chips; Phase 3 not on critical path)
**Entry Criteria**: Metrics and chips complete
**Exit Criteria**: Full graph reskin with all new lanes, DocChips, TotalsCell, edges, filters, and legend

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-4`

Phase 4 is on the critical path: Phases 5-6 (feature detail drawer) require graph row selection from T4-006. Phase 3 (triage/roster) can proceed in parallel with Phase 4 after Phase 2 completes.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T4-001 | Lane headers and feature cell reskin | ui-engineer-enhanced | 2 pts | T2-001 | pending |
| T4-002 | DocChips and multi-artifact lanes | ui-engineer-enhanced | 2 pts | T4-001 | pending |
| T4-003 | PhaseStackInline and PhaseDots | ui-engineer-enhanced, react-performance-optimizer | 1.5 pts | T4-001 | pending |
| T4-004 | TotalsCell with model-identity bar (server-provided actuals) | ui-engineer-enhanced, react-performance-optimizer | 2 pts | T4-002, T4-003, T7-004 | pending |
| T4-005 | SVG edge layer with animation | ui-engineer-enhanced, react-performance-optimizer | 2 pts | T4-004 | pending |
| T4-006 | Graph filter controls and legend | frontend-developer, ui-engineer-enhanced | 1.5 pts | T4-005 | pending |

---

## Quick Reference

### Batch 1 — After T2-001 (Phase 2) completes
```
Task("ui-engineer-enhanced", "T4-001: Reskin lane header row with colored square glyphs (each artifact type, glyph color = artifact color), sticky positioning. Reskin feature cell: category badge, complexity chip, mismatch indicator (mag ⚑) and stale indicator (warn ◷), 2-line title clamp, status pill + slug. Ref: docs/project_plans/designs/ccdash-planning/project/app/graph.jsx")
```

### Batch 2 — After T4-001 completes; run in parallel
```
Task("ui-engineer-enhanced", "T4-002: Implement DocChip (type label + truncated title + status dot). Support multiple stacked chips per lane cell for features with 2+ artifacts of same type. Gray out completed/superseded artifacts.")
Task("ui-engineer-enhanced", "T4-003: Implement PhaseDot (14x14px): filled=completed, pulsing ring=in-progress, !=blocked. Implement PhaseStackInline in progress lane showing row of dots with completed/total count. Animation smooth for in-progress state.")
```

### Batch 3 — After T4-002 and T4-003 complete
```
Task("ui-engineer-enhanced", "T4-004: Implement TotalsCell in rightmost lane: large story-points number, total tokens right-aligned, stacked model-identity bar (opus/sonnet/haiku proportional widths), per-model token counts with colored dots. Data source: server-provided feature.tokenUsage from PlanningQueryService / FeatureForensicsQueryService — specifically total_tokens plus the per-feature tokenUsageByModel breakdown delivered by T7-004 (actual session-forensics tokens, not estimates). Graceful fallback when backend returns 0.")
```

### Batch 4 — After T4-004 completes
```
Task("ui-engineer-enhanced", "T4-005: Add SVG layer rendering animated dashed flow edges for active features (brand color), static edges for inactive. Edges connect per-row lane cells in sequence. No performance regression on graph render.")
```

### Batch 5 — After T4-005 completes
```
Task("frontend-developer", "T4-006: Add 'All categories' dropdown filter (features/enhancements/refactors/spikes). Implement legend below graph: color swatch + label per artifact type + animated edge example labeled 'active edge'. 'New feature' button stub shows toast.")
```

---

## Quality Gates

- [ ] Lane headers sticky and match design
- [ ] DocChips render for multi-artifact lanes; multiple chips stack correctly
- [ ] PhaseStackInline with PhaseDots in all 3 states (completed/in-progress/blocked)
- [ ] TotalsCell shows points and server-provided actual tokens (total + per-model bar) from session forensics; no client-side estimator present
- [ ] SVG edges animated and performant
- [ ] Filter controls and legend functional
- [ ] Graph render time <=1.5s for 50 features

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
