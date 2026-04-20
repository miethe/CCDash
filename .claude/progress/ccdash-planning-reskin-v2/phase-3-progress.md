---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 3
title: Triage Inbox & Live Agent Roster
status: completed
created: '2026-04-20'
updated: '2026-04-20'
started: null
completed: null
commit_refs:
- f3435ac
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
- id: T3-001
  description: Render triage inbox with 5 filterable tabs (All/Blocked/Mismatches/Stale/Ready-to-promote)
    with count badges; triage rows with severity bar, kind badge, action button; clicking
    title opens feature detail drawer
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T2-003
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: T3-002
  description: Implement triage action buttons (Remediate/Dismiss/Promote/Assign PM/Archive/Resume
    per kind) showing toast feedback and triggering graph refresh
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - T3-001
  estimated_effort: 2 pts
  priority: medium
  assigned_model: sonnet
- id: T3-003
  description: Render live agent roster alongside triage in two-up layout (1.3fr/1fr);
    state dots glow for active states; rows color-coded; stacks below 1280px
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T3-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - T3-001
  batch_2:
  - T3-002
  - T3-003
  critical_path:
  - T3-001
  - T3-002
  estimated_total_time: 3 days
blockers: []
success_criteria:
- id: SC-3.1
  description: Triage inbox renders with all 5 filter tabs and badge counts
  status: pending
- id: SC-3.2
  description: Triage action buttons functional and show toast feedback
  status: pending
- id: SC-3.3
  description: Live agent roster side-by-side with triage in two-up layout
  status: pending
- id: SC-3.4
  description: State dots and row colors match design tokens
  status: pending
- id: SC-3.5
  description: Two-up layout responsive; stacks below 1280px
  status: pending
- id: SC-3.6
  description: Triage and roster data accurate against backend
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 3: Triage Inbox & Live Agent Roster

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-3-progress.md \
  -t T3-001 -s completed
```

---

## Phase Overview

**Title**: Triage Inbox & Live Agent Roster
**Dependencies**: Phase 2 complete (T2-003 — home layout established)
**Entry Criteria**: Home layout established
**Exit Criteria**: Triage and roster panels side-by-side, fully functional with filters and polling

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-3`

Note: Phase 3 (triage/roster) and Phase 4 (graph) are both unblocked once Phase 2 completes and can run in parallel. Phase 3 is NOT on the critical path to Phases 5-6 (graph row selection from Phase 4 is what unblocks the drawer).

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T3-001 | Triage inbox with filterable tabs | ui-engineer-enhanced, frontend-developer | 3 pts | T2-003 | pending |
| T3-002 | Triage action buttons | frontend-developer | 2 pts | T3-001 | pending |
| T3-003 | Live agent roster panel | ui-engineer-enhanced, frontend-developer | 2 pts | T3-001 | pending |

---

## Quick Reference

### Batch 1 — After T2-003 (Phase 2) completes
```
Task("ui-engineer-enhanced", "T3-001: Render triage inbox with 5 filterable tabs (All/Blocked/Mismatches/Stale/Ready-to-promote) with count badges. Triage rows: 3px severity bar, kind badge, feature slug, title, action button + chevron. Clicking title opens feature detail drawer. Empty state: green check + 'Nothing to triage'. Pull from TriageService or GET /api/planning/triage. Ref: docs/project_plans/designs/ccdash-planning/project/app/triage.jsx")
```

### Batch 2 — After T3-001 completes; run in parallel
```
Task("frontend-developer", "T3-002: Implement triage action buttons with correct labels per kind (Remediate/Dismiss/Promote to PRD/Assign PM/Archive/Resume shaping). Clicking shows toast feedback and triggers planning graph refresh. Action state persists briefly.")
Task("ui-engineer-enhanced", "T3-003: Render live agent roster alongside triage in two-up layout (triage 1.3fr, roster 1fr). Columns: state dot (glows for running/thinking), agent name + model/tier, current task, since. Row colors: running=ok, thinking=info, queued=warn, idle=dim. Responsive: stack below 1280px. Poll existing live-agent context.")
```

---

## Quality Gates

- [ ] Triage inbox renders with all 5 filter tabs
- [ ] Triage action buttons functional and show toast feedback
- [ ] Live agent roster side-by-side with triage
- [ ] State dots and row colors match design tokens
- [ ] Two-up layout responsive; stacks below 1280px
- [ ] Triage and roster data accurate against backend

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
