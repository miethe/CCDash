---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2"
feature_slug: "ccdash-planning-reskin-v2"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 1
title: "Shell Reskin & Top Bar"
status: "pending"
created: 2026-04-20
updated: 2026-04-20
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 3
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["ui-engineer-enhanced", "frontend-developer"]
contributors: []

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T1-001"
    description: "Reskin app rail with Planning icon/label active state using brand color ring highlight; confirm nav routing unchanged"
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["T0-002"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T1-002"
    description: "Build top bar with breadcrumb, live-agent status pill, global search button (cmd+K), and New spec primary CTA stub (toast)"
    status: "pending"
    assigned_to: ["ui-engineer-enhanced", "frontend-developer"]
    dependencies: ["T0-002"]
    estimated_effort: "2.5 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T1-003"
    description: "Update planning route canvas to max-width 1680px, padding 22px top/bottom 28px left/right, scroll-independent from rail"
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["T1-001", "T1-002"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T1-001", "T1-002"]
  batch_2: ["T1-003"]
  critical_path: ["T1-001", "T1-003"]
  estimated_total_time: "2-3 days"

blockers: []

success_criteria:
  - { id: "SC-1.1", description: "App rail active state matches handoff design", status: "pending" }
  - { id: "SC-1.2", description: "Top bar complete with all elements (breadcrumb, live counts, search, CTA)", status: "pending" }
  - { id: "SC-1.3", description: "Main canvas layout correct (max-width, padding, scroll)", status: "pending" }
  - { id: "SC-1.4", description: "Responsive behavior verified at >=1280px breakpoint", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2 - Phase 1: Shell Reskin & Top Bar

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-1-progress.md \
  -t T1-001 -s completed
```

---

## Phase Overview

**Title**: Shell Reskin & Top Bar
**Dependencies**: Phase 0 complete (T0-002 specifically — primitives must be available)
**Entry Criteria**: Tokens and primitives available from Phase 0
**Exit Criteria**: App rail, top bar, shell layout all reskinned per handoff

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-1`

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T1-001 | App rail reskin | ui-engineer-enhanced | 2 pts | T0-002 | pending |
| T1-002 | Top bar implementation | ui-engineer-enhanced, frontend-developer | 2.5 pts | T0-002 | pending |
| T1-003 | Main canvas layout | frontend-developer | 1.5 pts | T1-001, T1-002 | pending |

---

## Quick Reference

### Batch 1 — After T0-002 (Phase 0) completes; run in parallel
```
Task("ui-engineer-enhanced", "T1-001: Reskin app rail with Planning item active state using brand color ring highlight per handoff design. Icon and label both highlighted. Nav routing must remain unchanged. Responsive behavior at <1280px.")
Task("ui-engineer-enhanced", "T1-002: Build top bar: breadcrumb (CCDash / CCDash · Planning / Planning Deck), live-agent status pill (running + thinking count from live-agent context), global search button (cmd+K), New spec primary CTA (stub—shows toast for v2). Responsive layout.")
```

### Batch 2 — After T1-001 and T1-002 complete
```
Task("frontend-developer", "T1-003: Update planning route canvas to max-width 1680px, padding 22px top/bottom 28px left/right. Content scrolls independently from rail. Apply Tailwind classes. Verify responsive behavior.")
```

---

## Quality Gates

- [ ] App rail active state matches handoff design
- [ ] Top bar complete with all elements (breadcrumb, live counts, search, CTA)
- [ ] Main canvas layout correct (max-width 1680px, padding 22/28px, independent scroll)
- [ ] Responsive behavior verified (>=1280px breakpoint)

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
