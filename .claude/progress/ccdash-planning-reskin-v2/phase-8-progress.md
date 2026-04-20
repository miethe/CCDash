---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2"
feature_slug: "ccdash-planning-reskin-v2"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 8
title: "A11y Hardening & Performance Tuning"
status: "pending"
created: 2026-04-20
updated: 2026-04-20
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 6
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["web-accessibility-checker", "react-performance-optimizer"]
contributors: ["frontend-developer", "ui-engineer-enhanced"]

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T8-001"
    description: "Keyboard navigation audit: test all interactive elements for Tab navigation and Enter/Space activation; fix tab order; use tabindex strategically; no keyboard traps"
    status: "pending"
    assigned_to: ["web-accessibility-checker"]
    dependencies: ["T6-006"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T8-002"
    description: "Add ARIA roles to planning graph (role=table/grid, rowheader, columnheader); ensure all color-only elements have text labels; test with screen reader"
    status: "pending"
    assigned_to: ["web-accessibility-checker"]
    dependencies: ["T8-001"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T8-003"
    description: "Implement 2px solid brand-color focus ring at 60% alpha, 2px offset on all focusable elements; verify contrast >=4.5:1 against bg-1 and bg-2"
    status: "pending"
    assigned_to: ["web-accessibility-checker", "ui-engineer-enhanced"]
    dependencies: ["T8-002"]
    estimated_effort: "0.5 pts"
    priority: "medium"
    assigned_model: "sonnet"

  - id: "T8-004"
    description: "Audit StatusPills, ArtifactChips, model-identity bars for color-only reliance; add text labels next to dots; verify WCAG 2.1 section 1.4.1 compliance"
    status: "pending"
    assigned_to: ["web-accessibility-checker", "ui-engineer-enhanced"]
    dependencies: ["T8-003"]
    estimated_effort: "1 pt"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T8-005"
    description: "Confirm Google Fonts loaded with display:swap and preconnect; measure CLS <0.1; paint timing <50ms; no invisible text during load"
    status: "pending"
    assigned_to: ["react-performance-optimizer", "frontend-developer"]
    dependencies: ["T1-003"]
    estimated_effort: "0.5 pts"
    priority: "medium"
    assigned_model: "sonnet"

  - id: "T8-006"
    description: "Benchmark planning home TTI <=2s, graph render 50 features <=500ms, graph render 200 features <=1.5s, drawer open <=150ms; use React DevTools Profiler and Lighthouse; document if budgets exceeded"
    status: "pending"
    assigned_to: ["react-performance-optimizer", "frontend-developer"]
    dependencies: ["T4-005", "T4-006"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T8-001", "T8-005"]
  batch_2: ["T8-002", "T8-006"]
  batch_3: ["T8-003"]
  batch_4: ["T8-004"]
  critical_path: ["T8-001", "T8-002", "T8-003", "T8-004"]
  estimated_total_time: "2-3 days"

blockers: []

success_criteria:
  - { id: "SC-8.1", description: "All interactive elements keyboard-navigable (Tab order, Enter/Space activation)", status: "pending" }
  - { id: "SC-8.2", description: "ARIA roles and screen-reader support validated", status: "pending" }
  - { id: "SC-8.3", description: "Focus ring visible (2px, brand color, 60% alpha, 2px offset) and contrasting", status: "pending" }
  - { id: "SC-8.4", description: "Color-only elements have text fallback labels", status: "pending" }
  - { id: "SC-8.5", description: "Fonts load non-blocking with <50ms impact; CLS <0.1", status: "pending" }
  - { id: "SC-8.6", description: "Performance budgets met (TTI <=2s, graph 50 features <=500ms, drawer <=150ms)", status: "pending" }
  - { id: "SC-8.7", description: "WCAG 2.1 AA compliance verified", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2 - Phase 8: A11y Hardening & Performance Tuning

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-8-progress.md \
  -t T8-001 -s completed
```

---

## Phase Overview

**Title**: A11y Hardening & Performance Tuning
**Dependencies**: Phases 4-7 complete (T6-006 for a11y; T4-005/T4-006 for perf; T1-003 for font perf)
**Entry Criteria**: All feature surfaces complete
**Exit Criteria**: WCAG 2.1 AA compliance, font perf optimized, graph render budgets met

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-8`

T8-001 through T8-004 are sequential (each requires the prior). T8-005 and T8-006 can run in parallel starting from batch_1 as their dependencies (T1-003 and T4-005/T4-006 respectively) are from earlier phases.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T8-001 | Keyboard navigation audit | web-accessibility-checker | 1.5 pts | T6-006 | pending |
| T8-002 | ARIA roles and screen-reader support | web-accessibility-checker | 1.5 pts | T8-001 | pending |
| T8-003 | Focus ring styling and visual hierarchy | web-accessibility-checker, ui-engineer-enhanced | 0.5 pts | T8-002 | pending |
| T8-004 | Color + text label fallback | web-accessibility-checker, ui-engineer-enhanced | 1 pt | T8-003 | pending |
| T8-005 | Font performance (non-blocking, CLS, paint impact) | react-performance-optimizer, frontend-developer | 0.5 pts | T1-003 | pending |
| T8-006 | Planning graph render budgets | react-performance-optimizer, frontend-developer | 1.5 pts | T4-005, T4-006 | pending |

---

## Quick Reference

### Batch 1 — After T6-006 (Phase 6) and T1-003 (Phase 1) complete; run in parallel
```
Task("web-accessibility-checker", "T8-001: Keyboard navigation audit for all interactive elements: feature detail drawer, triage rows, graph rows, PhaseCards, BatchCols, TaskRows, ExecBtns, OQ editor. Test Tab order and Enter/Space activation. Fix any keyboard traps. Document any tabindex additions.")
Task("react-performance-optimizer", "T8-005: Confirm Google Fonts (Geist/JetBrains Mono/Fraunces) loaded with display:swap. Add preconnect links in <head>. Measure CLS before/after font load (target <0.1). Confirm paint timing <50ms impact. No invisible text during font load.")
```

### Batch 2 — After T8-001 completes and T4-005/T4-006 complete; run in parallel
```
Task("web-accessibility-checker", "T8-002: Add role=table or role=grid to planning graph. Add role=rowheader to feature column. Add role=columnheader to lane headers. Ensure all color-only elements have text labels. Test with screen reader (NVDA on Windows or VoiceOver on Mac).")
Task("react-performance-optimizer", "T8-006: Benchmark with React DevTools Profiler and Lighthouse: planning home TTI (target <=2s), graph 50 features (target <=500ms), graph 200 features (target <=1.5s), drawer open (target <=150ms). Document if budgets exceeded with mitigation plan.")
```

### Batch 3 — After T8-002 completes
```
Task("web-accessibility-checker", "T8-003: Implement 2px solid brand-color focus ring at 60% alpha, 2px offset per handoff CSS. Apply to all focusable elements in planning surfaces. Verify contrast >=4.5:1 against bg-1 and bg-2 backgrounds.")
```

### Batch 4 — After T8-003 completes
```
Task("web-accessibility-checker", "T8-004: Audit StatusPills (add label text next to dot), ArtifactChips (ensure type label always readable), model-identity bars (add Opus/Sonnet/Haiku text next to dots or in legend). Verify WCAG 2.1 section 1.4.1 compliance — no color as sole means of conveying information.")
```

---

## Quality Gates

- [ ] All interactive elements keyboard-navigable (Tab order, Enter/Space activation)
- [ ] ARIA roles and screen-reader support validated
- [ ] Focus ring visible (2px solid brand color, 60% alpha, 2px offset)
- [ ] Color-only elements have text fallback labels
- [ ] Fonts load non-blocking; CLS <0.1; paint timing <50ms
- [ ] Performance budgets met (TTI <=2s, graph 50 features <=500ms, drawer <=150ms)
- [ ] WCAG 2.1 AA compliance verified

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
