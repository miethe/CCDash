---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 2
title: "Planning Home \u2014 Metrics & Artifact Chips"
status: completed
created: '2026-04-20'
updated: '2026-04-20'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 3
completed_tasks: 3
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- frontend-developer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T2-001
  description: Render hero header with serif italic h1, subtitle, and right-side corpus
    stats (date, ctx/phase count, spark chart, tokens-saved %)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T1-003
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T2-002
  description: 'Render 6-tile metrics strip: Features/Active/Blocked/Stale/Mismatches/Completed
    with correct accent colors from planning summary API'
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T2-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T2-003
  description: Render 8 artifact composition chips (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/TRK/REP)
    with counts; clicking navigates to /planning/artifacts/:type
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - T2-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - T2-001
  batch_2:
  - T2-002
  - T2-003
  critical_path:
  - T2-001
  - T2-002
  estimated_total_time: 2 days
blockers: []
success_criteria:
- id: SC-2.1
  description: Hero header visible with corpus stats and animated spark chart
  status: pending
- id: SC-2.2
  description: 6 metrics tiles render with correct counts and accent colors
  status: pending
- id: SC-2.3
  description: 8 artifact chips render and navigate correctly
  status: pending
- id: SC-2.4
  description: All counts verified against backend payload
  status: pending
- id: SC-2.5
  description: Desktop and narrow-desktop responsive verified
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 2: Planning Home — Metrics & Artifact Chips

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-2-progress.md \
  -t T2-001 -s completed
```

---

## Phase Overview

**Title**: Planning Home — Metrics & Artifact Chips
**Dependencies**: Phase 1 complete (T1-003 — canvas layout must exist)
**Entry Criteria**: Top bar and shell layout complete
**Exit Criteria**: Hero header, metrics strip, artifact chips all rendering with correct data

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-2`

Note: Phase 3 (triage/roster) and Phase 4 (graph) both depend on Phase 2 completing, but can run in parallel with each other after T2-001 finishes.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T2-001 | Hero header with corpus stats | ui-engineer-enhanced, frontend-developer | 2 pts | T1-003 | pending |
| T2-002 | Metrics strip (6 tiles) | ui-engineer-enhanced, frontend-developer | 2 pts | T2-001 | pending |
| T2-003 | Artifact chip row (8 types) | frontend-developer, ui-engineer-enhanced | 2 pts | T2-001 | pending |

---

## Quick Reference

### Batch 1 — After T1-003 (Phase 1) completes
```
Task("ui-engineer-enhanced", "T2-001: Render hero header with serif italic h1 'The Planning Deck.', subtitle, and right-side corpus stats (date, ctx/phase count, animated spark chart, tokens-saved %). Pull from GET /api/planning/summary or compute client-side. h1 in Fraunces italic, CLS-safe.")
```

### Batch 2 — After T2-001 completes; run in parallel
```
Task("ui-engineer-enhanced", "T2-002: Render 6-tile metrics strip in responsive grid: Features (total), Active (plan color), Blocked (error color), Stale (warn color), Mismatches (mag color), Completed (ok color). Pull counts from planning summary API. Colors from planning-tokens.css.")
Task("frontend-developer", "T2-003: Render 8 artifact composition chips (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/TRK/REP). Each chip: type glyph, label, count. Colored with artifact-identity tokens. Clicking navigates to /planning/artifacts/:type. Empty counts show 0. Row ends with corpus summary text.")
```

---

## Quality Gates

- [ ] Hero header visible with corpus stats and animated spark chart
- [ ] 6 metrics tiles render with correct counts and accent colors
- [ ] 8 artifact chips render and navigate correctly
- [ ] All counts verified against backend payload
- [ ] Desktop and narrow-desktop responsive verified

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
