---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 0
title: Design Tokenization & Primitive Inventory
status: completed
created: 2026-04-20
updated: '2026-04-20'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-designer
- ui-engineer-enhanced
contributors:
- python-backend-engineer
- frontend-developer
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T0-001
  description: Extract OKLCH tokens from Planning Deck handoff into planning-tokens.css
    and tailwind.config.js with CSS fallbacks
  status: completed
  assigned_to:
  - ui-designer
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T0-002
  description: Implement all base primitive React components in components/Planning/primitives/
    (Panel, Tile, Chip, Btn variants, Dot, StatusPill, ArtifactChip, MetricTile, SectionHeader,
    Spark, ExecBtn)
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - T0-001
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: T0-003
  description: Load Geist, JetBrains Mono, and Fraunces fonts via Google Fonts CDN
    with display:swap and CSS custom properties
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - T0-001
  estimated_effort: 1 pt
  priority: medium
  assigned_model: sonnet
- id: T0-004
  description: Audit backend PlanningQueryService to confirm spikes[] and openQuestions[]
    present in feature payloads; add if missing (resolves OQ-01)
  status: completed
  assigned_to:
  - python-backend-engineer
  - ui-engineer-enhanced
  dependencies: []
  estimated_effort: 1.5 pts
  priority: high
  assigned_model: sonnet
- id: T0-005
  description: Implement comfortable/compact density mode toggle stored in localStorage
    planning_density_preference
  status: completed
  assigned_to:
  - frontend-developer
  dependencies:
  - T0-002
  estimated_effort: 0.5 pts
  priority: low
  assigned_model: sonnet
- id: T0-006
  description: 'Audit session-forensics token aggregation (resolves OQ-02): confirm
    per-feature total_tokens on FeatureForensicsDTO and per-session {model, total_tokens}
    on linked_sessions; confirm whether per-model (opus/sonnet/haiku/other) breakdown
    is exposed or scope to T7-004. Document feature-session correlation path (feature_forensics.py:266)
    and model-identity derivation (backend/model_identity.py:29).'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  estimated_effort: 0.5 pts
  priority: high
  assigned_model: sonnet
parallelization:
  batch_1:
  - T0-001
  - T0-004
  - T0-006
  batch_2:
  - T0-002
  - T0-003
  batch_3:
  - T0-005
  critical_path:
  - T0-001
  - T0-002
  - T0-005
  estimated_total_time: 3-4 days
blockers: []
success_criteria:
- id: SC-0.1
  description: All OKLCH tokens defined in planning-tokens.css with browser-compatible
    fallbacks
  status: pending
- id: SC-0.2
  description: All primitives implemented and render correctly in all states
  status: pending
- id: SC-0.3
  description: Storybook stories or documented usage for each primitive
  status: pending
- id: SC-0.4
  description: Typography loads non-blocking with correct fallbacks
  status: pending
- id: SC-0.5
  description: Backend payload includes spikes[] and openQuestions[] (OQ-01 resolved)
  status: pending
- id: SC-0.6
  description: Density toggle works and persists across reloads
  status: pending
- id: SC-0.7
  description: 'Session-forensics token aggregation audited: per-feature total_tokens
    confirmed; per-model breakdown confirmed on payload OR scoped to T7-004 (OQ-02
    resolved)'
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 0: Design Tokenization & Primitive Inventory

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-0-progress.md \
  -t T0-001 -s completed
```

---

## Phase Overview

**Title**: Design Tokenization & Primitive Inventory
**Dependencies**: None (can run in parallel with Phase 7)
**Entry Criteria**: PRD approved, design handoff available at `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html`
**Exit Criteria**: All tokens mapped, all primitives implemented and tested, backend payload audited

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-0`

This phase establishes the design-system foundation that all subsequent phases depend on. No phase 1–6 work should begin until T0-001 and T0-002 are complete.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T0-001 | Token extraction and Tailwind config | ui-designer | 2 pts | — | pending |
| T0-002 | Base primitive components | ui-engineer-enhanced | 3 pts | T0-001 | pending |
| T0-003 | Typography setup (Geist/Mono/Fraunces) | ui-engineer-enhanced | 1 pt | T0-001 | pending |
| T0-004 | Backend payload audit (OQ-01) | python-backend-engineer, ui-engineer-enhanced | 1.5 pts | — | pending |
| T0-005 | Density modes (localStorage) | frontend-developer | 0.5 pts | T0-002 | pending |
| T0-006 | Session-forensics token aggregation audit (OQ-02) | python-backend-engineer | 0.5 pts | — | pending |

---

## Quick Reference

### Batch 1 — Run in parallel (no deps)
```
Task("ui-designer", "T0-001: Extract OKLCH tokens from Planning Deck handoff into planning-tokens.css and tailwind.config.js. Cover surface tokens (bg-0..bg-4, line-1/2, ink-0..4), artifact-identity colors (spec/spk/prd/plan/prog/ctx/trk/rep), semantic colors (ok/warn/err/info/mag), model-identity colors (opus/sonnet/haiku), brand accent. Add CSS sRGB fallbacks. Ref: docs/project_plans/designs/ccdash-planning/project/Planning Deck.html")
Task("python-backend-engineer", "T0-004: Audit backend/application/services/agent_queries/ PlanningQueryService. Confirm feature payloads include spikes[], openQuestions[], artifact arrays per type, and mismatch/stale/readyToPromote flags. Add missing fields. Document payload structure.")
Task("python-backend-engineer", "T0-006: Audit session-forensics token aggregation (OQ-02). Confirm (a) FeatureForensicsDTO.total_tokens (backend/application/services/agent_queries/feature_forensics.py:336) is exposed on the planning feature payload and (b) per-model (opus/sonnet/haiku/other) breakdown is present OR scope as extension T7-004. Document feature-session correlation path (feature_forensics.py:266 via links repo) and model-identity derivation (backend/model_identity.py:29).")
```

### Batch 2 — After T0-001 completes
```
Task("ui-engineer-enhanced", "T0-002: Implement React primitives in components/Planning/primitives/: Panel, Tile, Chip, Btn, BtnGhost, BtnPrimary, Dot, StatusPill (11 status values: idea/shaping/ready/draft/approved/in-progress/blocked/completed/superseded/future/deprecated), ArtifactChip (8 types), MetricTile, SectionHeader, Spark, ExecBtn. Reference docs/project_plans/designs/ccdash-planning/project/app/primitives.jsx")
Task("ui-engineer-enhanced", "T0-003: Load Geist (sans), JetBrains Mono (mono), Fraunces (serif) via Google Fonts CDN. Apply via --sans/--mono/--serif CSS custom properties. Use display:swap. Add preconnect links. Measure paint impact <50ms.")
```

### Batch 3 — After T0-002 completes
```
Task("frontend-developer", "T0-005: Implement comfortable (44px row, 16px gap) and compact (34px row, 10px gap) density mode toggle. Store in localStorage key planning_density_preference. All planning surfaces must respect setting.")
```

---

## Quality Gates

- [ ] All OKLCH tokens defined in `planning-tokens.css` with browser-compatible fallbacks
- [ ] All primitives implemented and render correctly in all states
- [ ] StatusPill covers all 11 status values
- [ ] Storybook stories or documented usage for each primitive
- [ ] Typography loads non-blocking with correct fallbacks (display: swap, preconnect)
- [ ] Backend payload includes `spikes[]` and `openQuestions[]` (OQ-01 resolved)
- [ ] Session-forensics token aggregation audited (OQ-02 resolved): per-feature total_tokens confirmed and per-model breakdown confirmed on payload OR scoped to T7-004
- [ ] Density toggle works and persists

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
