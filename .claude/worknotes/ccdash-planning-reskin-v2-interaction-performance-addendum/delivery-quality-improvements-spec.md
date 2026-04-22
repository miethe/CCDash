---
title: Delivery Quality Improvements — Planning & Execution Skills Spec
schema_version: 1
doc_type: spec
status: draft
created: '2026-04-22'
author: orchestrator
scope: Cross-cutting changes to planning/, dev-execution/, artifact-tracking/, debugging/ skills plus command bindings and phase templates to prevent the class of integration/verification gaps observed in ccdash-planning-reskin-v2-interaction-performance-addendum-v1.
motivating_incident: .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-{13,15,16}-progress.md
---

# Delivery Quality Improvements — Planning & Execution Skills Spec

## 1. Problem Statement

The v2 interaction/performance addendum shipped with six regressions that Codex had to patch after the fact (roster height, serif-font leak on compact headings, missing density font vars, missing Orchestrator label, Status-Distribution filter not propagating, no FE fallback for missing `statusCounts`). Every one was in the plan's scope; none were caught by the seven Phase-16 verification tasks. The plan's text was correct — the **planning grammar, the execution protocol, and the verification matrix were all too coarse to catch cross-panel seam bugs and visual regressions.**

This spec defines concrete, testable upgrades to the `planning`, `dev-execution`, `artifact-tracking`, and `debugging` skills, plus new command bindings and progress-file schema fields, so the next multi-panel UI plan cannot pass verification without the seams and visuals proven.

## 2. Failure Taxonomy (from the incident)

| Class | Symptom | Root lever it exposes |
|---|---|---|
| **Ambiguous AC scope** | "filters lists/graph" — which panels? | Planning grammar lacks a `target_surfaces` field |
| **Seam ownership gap** | FE + BE owners but nobody owned propagation | Phase schema lacks `integration_owner` / `seam_tasks` |
| **Contract-only tests** | Payload shape asserted, rendered output not | Verification phase lacks AC↔test matrix |
| **No visual/runtime gate** | Serif font leak, missing density vars undetected | No mandatory browser smoke gate on UI phases |
| **Batch-flip completion** | Phase marked done with `started: null, completed: null` | artifact-tracking allows completion without timing |
| **Implicit resilience** | FE assumed `statusCounts` always present | Planning grammar has no `resilience` AC bucket |

## 3. Design Goals

1. **No AC without enumerable target surfaces.** "Visible/propagates/applied across" is not an AC unless it lists the specific panels/components/rows.
2. **Every UI-touching phase has a mandatory runtime smoke gate.** Not a suggestion, a blocking task.
3. **Every AC maps to ≥1 verification task; every verification task cites ≥1 AC.** The Phase 16 table becomes a matrix, not a list.
4. **Seam tasks are first-class.** When a phase has parallel FE+BE owners, a named seam/integration task is added automatically.
5. **Completion requires timing signals.** `started` and `completed` timestamps must be non-null for `status: completed`.
6. **Resilience is a planning category, not a reviewer's courtesy.** Every new payload field implies a "handles missing/null" AC.

## 4. Concrete Changes

### 4.1 `planning` skill — grammar upgrades

Add required structured fields to every implementation plan's `## Product Requirements` and phase tables.

**New AC schema (markdown):**

```markdown
#### AC R3.4: Status Distribution filter narrows planning surfaces
- target_surfaces:
  - components/Planning/PlanningSummaryPanel.tsx (attention columns)
  - components/Planning/PlanningGraphPanel.tsx (phase rows)
  - components/Planning/TrackerIntakePanel.tsx (row list)
  - components/Planning/PlanningAgentRosterPanel.tsx (row list if linked)
- propagation_contract: selected bucket/signal is passed via route state and consumed by every target_surface's query/memo
- resilience: if payload lacks statusCounts, filter controls render disabled with tooltip "Backend did not supply status counts"
- visual_evidence_required: before/after screenshots at desktop ≥1440px
- verified_by: [P16-003, P16-012-smoke]
```

**Plan generator rules** (`planning` skill SKILL.md additions):

- R-P1: *No AC may contain "across", "everywhere", "throughout", "all X", or "visible" without an explicit `target_surfaces:` list.*
- R-P2: *Every new backend field X introduces an implicit AC "FE handles missing X"; generator writes it automatically if not present.*
- R-P3: *Every phase with ≥2 owner specialties and overlapping file edits (`files_affected` intersection ≥1) must declare an `integration_owner` and at least one seam task.*
- R-P4: *UI-touching phases (any `*.tsx` in files_affected) must include a "runtime smoke" task in the verification phase.*

### 4.2 Phase & progress YAML — new fields

```yaml
# implementation plan phase frontmatter
phase:
  id: 13
  title: Metrics, Filters, and Density Wiring
  integration_owner: ui-engineer-enhanced   # NEW — required when ≥2 specialties
  ui_touched: true                          # NEW — auto-derived from files_affected
  target_surfaces:                          # NEW — union of all task target_surfaces
    - components/Planning/PlanningSummaryPanel.tsx
    - components/Planning/PlanningGraphPanel.tsx
    - components/Planning/TrackerIntakePanel.tsx
  seam_tasks: [P13-005]                     # NEW — tasks that span owner boundaries

# progress file frontmatter — completion gate
tasks:
  - id: P13-003
    status: completed
    started: 2026-04-21T14:02Z   # NEW — required non-null when status != pending
    completed: 2026-04-21T17:40Z # NEW — required non-null when status == completed
    verified_by:                  # NEW — which P16 task signed this off
      - P16-003
      - P16-012-smoke
    evidence:                     # NEW — file refs, commit SHAs, screenshot paths
      - commit: abc123
      - screenshot: .claude/evidence/phase-13/status-filter-before.png
      - test: components/Planning/__tests__/statusFilterPropagation.test.tsx
```

`artifact-tracking/scripts/update-status.py` rejects `-s completed` without `--started` and `--completed` (or `--evidence`), with `--force` escape valve that logs a warning.

### 4.3 `dev-execution` skill — execution protocol upgrades

**New step between "implement" and "mark complete"**: `verify target_surfaces`. For each task with `target_surfaces`, a delegated subagent must (a) grep/read each target file, (b) confirm the propagation contract is wired, (c) emit a checklist that gets appended to the progress task's `evidence:` list.

**Parallel-execution rule:** when a phase's batch contains tasks with overlapping `target_surfaces`, the execution engine:
1. Runs implementation tasks in parallel as today.
2. Then runs the phase's `seam_tasks` serially, with the `integration_owner` as the assigned agent.
3. Seam tasks are gated on all their upstream task ids being `completed`.

**Runtime smoke gate:** the last sub-step of any `ui_touched: true` phase:
- Launch `npm run dev` (if not already running) via a non-blocking task.
- Delegate a browser automation agent (Claude-in-Chrome or chrome-devtools) to open each `target_surface` entry point and capture screenshots.
- Attach screenshots to `.claude/evidence/phase-N/`.
- Explicit decision point: orchestrator reviews screenshots OR records "skipped — no runtime available" with reason. Skipping is allowed but logged; silent skipping is not.

### 4.4 `artifact-tracking` skill — schema + scripts

Add to `.claude/skills/artifact-tracking/scripts/`:

1. **`validate-phase-completion.py`** — blocks `status: completed` if any task lacks `started`, `completed`, `verified_by`, or `evidence`. Run automatically by the `dev-execution` "phase exit" step.
2. **`ac-coverage-report.py`** — walks the plan's ACs, the phase's tasks, and produces a two-way coverage matrix. Fails if any AC has zero `verified_by` references or any verification task cites zero ACs.
3. **Extend `update-status.py`** with `--started`, `--completed`, `--evidence`, `--verified-by` flags and the rejection rule above.

### 4.5 `debugging` skill — post-incident hook

Add a "post-incident retrospective" workflow triggered by the phrase patterns "Codex had to patch", "gaps after merge", "we missed", "regression after phase X complete":

1. Read the plan + progress files.
2. Classify each gap against the failure taxonomy in §2.
3. Emit a patch-plan that adds the missing ACs/surfaces/seams/smoke tasks to the plan as an addendum, not a new plan.
4. Optionally save a feedback memory via the auto-memory system so the pattern informs future plans.

### 4.6 Command bindings (CLAUDE.md table)

Additions to the Command–Skill Bindings table:

| Command | Required Skills | New hook |
|---|---|---|
| `/plan:plan-feature` | planning | After plan generation, run `ac-coverage-report.py --dry` and block merge to `status: approved` if any AC lacks `target_surfaces` |
| `/dev:execute-phase` | dev-execution, artifact-tracking | Before phase-exit, run `validate-phase-completion.py` and `ac-coverage-report.py`; block `status: completed` on any error |
| `/fix:debug` | debugging | If prompt contains post-incident phrases, auto-invoke §4.5 retrospective workflow |

### 4.7 CLAUDE.md amendments

1. Under **Prime Directives**, add a 5th directive: **Seam integrity** — "Cross-owner seams are a named deliverable, not an emergent property."
2. Under the UI testing rule ("For UI or frontend changes, start the dev server…"), add: *"If runtime is unavailable, Phase N cannot be marked `completed` without an explicit `runtime_smoke: skipped` field and reason; a clean unit-test pass is not a substitute."*
3. Add a "Resilience-by-default" clause: *"Every new optional backend field requires an explicit FE fallback AC. Missing is a contract state, not a bug."*

## 5. Acceptance Criteria for This Spec

1. A generated plan fails `/plan:plan-feature` exit if any AC contains vague propagation language without `target_surfaces`.
2. A phase with overlapping FE+BE owners auto-gets an `integration_owner` and ≥1 seam task.
3. `update-status.py -s completed` rejects missing `started`/`completed` timestamps.
4. AC↔verification coverage matrix is emitted as part of phase exit and blocks on uncovered ACs.
5. UI-touching phases cannot reach `status: completed` without either runtime smoke evidence or explicit `runtime_smoke: skipped` with reason.
6. Every new backend field generates a paired FE-fallback AC.
7. `/fix:debug` on post-incident phrasing produces a patch-plan that maps each gap to the §2 taxonomy.

## 6. Rollout Plan

| Step | Artifact | Owner | Gate |
|---|---|---|---|
| 1 | Land schema additions to planning skill templates | planning maintainer | Unit test: generator rejects vague AC |
| 2 | Extend `update-status.py` + add 2 new scripts | artifact-tracking maintainer | Scripts have test coverage |
| 3 | Update `dev-execution` with seam step + smoke gate | dev-execution maintainer | Dry-run on an in-flight phase |
| 4 | Amend CLAUDE.md directives | project lead | Review + merge |
| 5 | Backfill: run `ac-coverage-report.py` on the last three plans to validate retroactively | orchestrator | Report filed, no false-positive regression |
| 6 | Dogfood on next UI addendum | feature owner | Zero post-merge regressions of §2 failure classes |

## 7. Non-Goals

1. Replacing the existing `planning` skill output format — only additive fields.
2. Requiring a human code-review gate (CI + CLI validators do the work).
3. Mandating visual regression tooling (Chromatic/Percy) — screenshots to `.claude/evidence/` are enough for now.
4. Retroactively re-verifying already-merged features.

## 8. Open Questions

1. Should `target_surfaces` be path strings or symbol refs (`ai/symbols.graph.json` ids)? Symbol refs are more stable but require the graph to exist at plan time.
2. Runtime smoke: Claude-in-Chrome vs chrome-devtools vs a minimal Playwright script — pick one canonical for the skill.
3. Evidence retention: do screenshots live in-repo under `.claude/evidence/` or in an artifact store? In-repo is simplest but bloats git history.
4. Should seam tasks always go to the `integration_owner`, or can they be split between owners with an explicit handoff protocol?

## 9. Reference Incident

See `.claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-{13,15,16}-progress.md` and commit `ed0d86b` vs. the Codex remediation patch. Every gap in that remediation maps cleanly to a class in §2 and would have been blocked by one of the changes in §4.
