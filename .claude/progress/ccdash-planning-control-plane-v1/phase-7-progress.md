---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 7
title: Planning UI Consolidation — Foundation & Extraction
status: in_progress
created: '2026-04-17'
updated: '2026-04-17'
started: null
completed: null
commit_refs:
- 6d7a4e9
pr_refs: []
overall_progress: 0
completion_estimate: 4-5 days
total_tasks: 4
completed_tasks: 3
in_progress_tasks: 1
blocked_tasks: 0
at_risk_tasks: 0
owners:
- frontend-developer
- ui-engineer-enhanced
contributors:
- codebase-explorer
- task-completion-validator
tasks:
- id: PCP-701
  description: Codebase explorer audit of planning-only metadata components in components/Planning/
    that duplicate /board or /plans logic. For each component record location, purpose,
    and replacement strategy (import from @miethe/ui, extract to @miethe/ui, or keep-local).
    Produce audit report and extraction manifest. Reference .claude/skills/planning/references/ui-extraction-guidance.md.
  status: completed
  assigned_to:
  - codebase-explorer
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PCP-604
  estimated_effort: 2 pts
  priority: high
- id: PCP-702
  description: Implement active plans (status in-progress) and planned features (implementation
    plans with status draft/approved) columns/tabs on planning home, reusing board
    column/list primitives from ProjectBoard. Clicking a feature must open ProjectBoard
    feature modal, not planning-only detail.
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PCP-701
  - PCP-302
  estimated_effort: 3 pts
  priority: high
- id: PCP-706
  description: Create or promote components/shared/PlanningMetadata.tsx with shared
    status/mismatch/batch-readiness badge and chip components. Migrate or deprecate
    planning-only variants following PCP-701 extraction manifest. Update all imports
    across planning, board, and catalog surfaces.
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - PCP-701
  estimated_effort: 2 pts
  priority: high
- id: PCP-709
  description: Extract and publish components to @miethe/ui. For each "extract" decision
    in PCP-701 manifest fork component to @miethe/ui; refactor dependencies; add package
    entry; port tests (>80% coverage); add Storybook story; document; publish with
    semver. Update CCDash imports to use extracted components. Mark task with [pkg]
    for model tracking. Reference .claude/skills/planning/references/ui-extraction-guidance.md
    § "9-Step Extraction Process".
  status: in_progress
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - PCP-701
  estimated_effort: 3-5 pts
  priority: high
parallelization:
  batch_1:
  - PCP-701
  batch_2:
  - PCP-702
  - PCP-706
  batch_3:
  - PCP-709
  critical_path:
  - PCP-701
  - PCP-709
  - PCP-702
  estimated_total_time: 10-12 pts / 4-5 days
blockers: []
notes:
- Phase 7 is a post-gate foundation and extraction phase. Phase 6 validation gates
  must remain satisfied throughout; all behavior is preserved and only component internals
  are swapped and extracted.
- PCP-701 audit is a blocking prerequisite — the extraction manifest it produces governs
  all downstream refactor and extraction decisions in PCP-702, PCP-706, and PCP-709.
- PCP-702 and PCP-706 can proceed in parallel once PCP-701 audit report is available.
- PCP-709 extraction work depends on PCP-701 decisions but can proceed in parallel
  with PCP-702 and PCP-706 extraction/consolidation work.
- Active plans columns (PCP-702) use extracted/shared components from PCP-709 and
  consolidated metadata from PCP-706.
progress: 75
---

# Phase 7 Progress: Planning UI Consolidation — Foundation & Extraction

## Overview

Phase 7 is the post-gate foundation and extraction phase for the Planning Control Plane V1. It audits planning-specific UI primitives, produces an extraction manifest, extracts reusable components to `@miethe/ui`, consolidates metadata primitives into `components/shared/PlanningMetadata.tsx`, and implements active-plans and planned-features columns on planning home using shared board list components. Phase 6 validation gates must remain satisfied throughout.

## Objective

Establish @miethe/ui component extraction discipline for planning UI, eliminate planning-only duplicates eligible for sharing, and begin consolidation by adding active/planned features columns. All extracted components must have published npm packages, >80% test coverage, and Storybook stories. Planning home surfaces active and planned work using shared board list primitives. No planning-specific UI duplications of library-eligible primitives remain in CCDash after this phase.

## Task Breakdown

| Task ID | Description | Assigned To | Est. | Dependencies | Status |
|---------|-------------|-------------|------|--------------|--------|
| PCP-701 | Audit planning primitives; produce extraction manifest with import/extract/keep-local decisions | codebase-explorer, frontend-developer, ui-engineer-enhanced | 2 pts | PCP-604 | pending |
| PCP-702 | Active plans + planned features columns on planning home using board list primitives | frontend-developer, ui-engineer-enhanced | 3 pts | PCP-701, PCP-302 | pending |
| PCP-706 | Consolidate planning metadata components into shared/PlanningMetadata.tsx following extraction manifest | ui-engineer-enhanced, frontend-developer | 2 pts | PCP-701 | pending |
| PCP-709 | Extract and publish eligible components to @miethe/ui with full tests/docs/Storybook [pkg] | ui-engineer-enhanced, frontend-developer | 3-5 pts | PCP-701 | pending |

## Batch Dependency Structure

```
Batch 1 (unblock):     PCP-701
Batch 2 (parallel):    PCP-702, PCP-706
Batch 3 (parallel):    PCP-709 (extraction proceeds in parallel with PCP-702/706)
```

## Quality Gates

1. All Phase 6 validation tests pass without modification after each batch.
2. Extraction manifest from PCP-701 is complete and actionable; every planning-only primitive has a clear decision (import/extract/keep-local).
3. No planning-only badge or status chip component remains in `components/Planning/` after PCP-706.
4. All extracted components in @miethe/ui have >80% unit test coverage, Storybook stories, and published npm packages with semver versioning.
5. Active plans and planned features are visible on planning home using the same list components as `/board`.
6. `components/shared/PlanningMetadata.tsx` is the single source of truth for status/mismatch/batch-readiness rendering.
7. CCDash imports all applicable shared UI from @miethe/ui; no inline duplicates remain.

## Success Criteria

1. Planning component audit is complete with extraction manifest documenting import/extract/keep-local decisions.
2. All extraction candidates have moved to @miethe/ui with published npm packages, >80% test coverage, Storybook stories, and README docs.
3. CCDash imports reuse shared UI from @miethe/ui instead of maintaining inline copies.
4. `components/shared/PlanningMetadata.tsx` consolidates all planning status/badge rendering — no planning-only variants in `components/Planning/`.
5. Active plans and planned features columns surface on planning home using shared board list components.
6. Phase 6 validation gates remain satisfied; no behavior regressions.
7. No planning-specific UI duplications of library-eligible primitives remain in codebase.

## Quick Reference

### PCP-701 — Audit Planning Primitives and @miethe/ui Extraction Manifest
```
Task("Audit all planning-only metadata components in components/Planning/ that
duplicate /board or /plans logic. For each component record: location, purpose,
and extraction decision (import from @miethe/ui if exists, extract to @miethe/ui
if reusable, or keep-local if planning-specific). Produce extraction manifest as
the deliverable. Reference .claude/skills/planning/references/ui-extraction-guidance.md.
Assigned: codebase-explorer, frontend-developer, ui-engineer-enhanced.
Dependency: PCP-604 (Phase 6 complete).")
```

### PCP-702 — Active Plans + Planned Features Columns
```
Task("Implement active plans (status: in-progress) and planned features
(implementation plans status: draft/approved) columns/tabs on PlanningHomePage.tsx
using ProjectBoard column/list primitives. Clicking a feature must open the
ProjectBoard feature modal — not a planning-only detail panel.
Assigned: frontend-developer, ui-engineer-enhanced.
Dependencies: PCP-701, PCP-302.")
```

### PCP-706 — Consolidate Planning Metadata Components
```
Task("Create or promote components/shared/PlanningMetadata.tsx with shared
status/mismatch/batch-readiness badge and chip components. Migrate or deprecate
all planning-only badge/chip variants in components/Planning/ following PCP-701
extraction manifest. Update all imports across planning, board, and catalog surfaces.
Assigned: ui-engineer-enhanced, frontend-developer.
Dependency: PCP-701.")
```

### PCP-709 — Extract and Publish Components to @miethe/ui [pkg]
```
Task("For each 'extract' decision in PCP-701 manifest: fork component to temp
branch in @miethe/ui; refactor dependencies; add package entry; port tests (>80%
coverage); add Storybook story; document; publish with semver. Update CCDash imports
to use extracted components from @miethe/ui instead of inline originals. Reference
.claude/skills/planning/references/ui-extraction-guidance.md § '9-Step Extraction Process'.
Mark task with [pkg] for model tracking.
Assigned: ui-engineer-enhanced, frontend-developer.
Dependency: PCP-701.")
```

## PCP-709 Execution Log

**Skillmeat-side prep complete (awaiting human publish):**

- 5 primitives ported to `@miethe/ui/src/primitives/`: `StatusChip`, `EffectiveStatusChips`, `MismatchBadge`, `BatchReadinessPill`, `PlanningNodeTypeIcon` (+ supporting `variants.ts`).
- 55/55 tests passing in `@miethe/ui`; new unit test added for `PlanningNodeTypeIcon` (CCDash had no coverage — audit blocker resolved).
- `package.json` bumped `0.2.0 → 0.3.0`. `CHANGELOG.md` and `README.md` updated. `tsc -p tsconfig.build.json` exit 0.
- Storybook stories skipped: `@miethe/ui` has no Storybook setup. Deferred as follow-up.
- No commit made in skillmeat repo; no `npm publish` run — human operator reviews & publishes.

**CCDash post-publish follow-ups (blocks phase 7 completion):**

1. Bump `@miethe/ui` in CCDash `package.json` to `^0.3.0` and install.
2. In `components/shared/PlanningMetadata.tsx`, flip 5 re-exports from `@/components/Planning/primitives/...` → `@miethe/ui/primitives` (StatusChip, EffectiveStatusChips, MismatchBadge, BatchReadinessPill, PlanningNodeTypeIcon). Leave `LineageRow` and `castPlanningStatus` re-exports on local primitives (keep-local per manifest).
3. Refactor `components/Planning/PlanningGraphPanel.tsx` lines 66–78 (duplicate `NodeTypeIcon` logic) to use the extracted `PlanningNodeTypeIcon`.
4. After parity verified, delete `components/Planning/primitives/StatusChip.tsx`, `EffectiveStatusChips.tsx`, `MismatchBadge.tsx`, `BatchReadinessPill.tsx`, `PlanningNodeTypeIcon.tsx`, and `variants.ts`. Update `components/Planning/primitives/index.ts` accordingly.
5. Run `npm run build` + vitest suite; confirm no regressions. Mark PCP-709 `completed` and phase-7 `completed`.
