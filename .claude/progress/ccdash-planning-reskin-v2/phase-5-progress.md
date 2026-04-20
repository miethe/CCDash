---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2"
feature_slug: "ccdash-planning-reskin-v2"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 5
title: "Feature Detail Drawer — Header & Lineage"
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
  - id: "T5-001"
    description: "Render fixed right drawer panel (min 920px / 64vw, bg-1, border-left line-2, box-shadow); scroll independent; close button top-right; responsive width at <1280px"
    status: "pending"
    assigned_to: ["ui-engineer-enhanced", "frontend-developer"]
    dependencies: ["T4-006"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T5-002"
    description: "Render drawer header: category/slug breadcrumb, mismatch pill, serif italic h1 title, raw→effective status pills with arrow, complexity chip, tags, Execute CTA, Close button"
    status: "pending"
    assigned_to: ["ui-engineer-enhanced", "frontend-developer"]
    dependencies: ["T5-001"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T5-003"
    description: "Render lineage strip: 7 clickable artifact-type tiles (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/REPORT) with type label, count, status pill, PhaseDot stack for PHASE; clicking scrolls to section"
    status: "pending"
    assigned_to: ["frontend-developer", "ui-engineer-enhanced"]
    dependencies: ["T5-001"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T5-001"]
  batch_2: ["T5-002", "T5-003"]
  critical_path: ["T5-001", "T5-002"]
  estimated_total_time: "2-3 days"

blockers: []

success_criteria:
  - { id: "SC-5.1", description: "Drawer shell renders with correct dimensions (920px min, 64vw max)", status: "pending" }
  - { id: "SC-5.2", description: "Header complete with all fields and correct colors", status: "pending" }
  - { id: "SC-5.3", description: "Lineage strip renders 7 tiles with correct data", status: "pending" }
  - { id: "SC-5.4", description: "Lineage tile clicks scroll and toggle sections", status: "pending" }
  - { id: "SC-5.5", description: "Close button functional", status: "pending" }
  - { id: "SC-5.6", description: "Responsive width verified (640px at <1280px)", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2 - Phase 5: Feature Detail Drawer — Header & Lineage

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-5-progress.md \
  -t T5-001 -s completed
```

---

## Phase Overview

**Title**: Feature Detail Drawer — Header & Lineage
**Dependencies**: Phase 4 complete (T4-006 — graph row selection must be functional)
**Entry Criteria**: Graph row selection functional
**Exit Criteria**: Feature detail drawer shell complete with header and lineage strip

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-5`

Phase 5 establishes the drawer shell that Phase 6 builds on. T5-001 (drawer shell) is the critical entry point.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T5-001 | Feature detail drawer shell | ui-engineer-enhanced, frontend-developer | 1.5 pts | T4-006 | pending |
| T5-002 | Drawer header with metadata | ui-engineer-enhanced, frontend-developer | 2 pts | T5-001 | pending |
| T5-003 | Lineage strip with artifact tiles | frontend-developer, ui-engineer-enhanced | 1.5 pts | T5-001 | pending |

---

## Quick Reference

### Batch 1 — After T4-006 (Phase 4) completes
```
Task("ui-engineer-enhanced", "T5-001: Render fixed right panel drawer: min(920px, 64vw) wide, bg-1 background, border-left line-2, box-shadow. Drawer opens on graph row click. Content scrolls independently from graph. Close button top-right. Responsive: narrow to min(640px, 95vw) at <1280px.")
```

### Batch 2 — After T5-001 completes; run in parallel
```
Task("ui-engineer-enhanced", "T5-002: Render drawer header: category/slug breadcrumb, mismatch pill (if mismatched, mag color), serif italic Fraunces h1 title, raw status pill → effective status pill (arrow if different), complexity chip, tags (up to 3), Execute CTA button, Close button. All fields visible. Ref: docs/project_plans/designs/ccdash-planning/project/app/feature_detail.jsx")
Task("frontend-developer", "T5-003: Render lineage strip: 7 clickable tiles for SPEC/SPIKE/PRD/PLAN/PHASE/CTX/REPORT. Each tile: type label, count xN, representative status pill, PhaseDot stack for PHASE type. Clicking tile scrolls to relevant section and opens/toggles it. Mute tiles for empty types.")
```

---

## Quality Gates

- [ ] Drawer shell renders with correct dimensions (min 920px, max 64vw)
- [ ] Header complete with all fields and colors
- [ ] Lineage strip renders 7 tiles with correct data
- [ ] Lineage tile clicks scroll and toggle sections
- [ ] Close button functional
- [ ] Responsive width verified (640px at <1280px)

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
