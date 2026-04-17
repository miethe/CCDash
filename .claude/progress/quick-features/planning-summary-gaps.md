---
slug: planning-summary-gaps
status: completed
created: 2026-04-17
scope: small
related_plan: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
---

# Planning Summary Gaps (post-PCP v1 follow-up)

Three post-landing fixes reported against the Planning Control Plane V1:

## Fix 1 — "Planned" column is empty (backend)

**Root cause.** `PlanningQueryService.get_project_planning_summary` in
`backend/application/services/agent_queries/planning.py` builds `feature_summaries`
exclusively from rows in the `features` table. Those rows are populated by
`backend/parsers/features.py`, whose feature extraction is anchored to
`implementation_plan` documents. Design-spec-only and PRD-only work items
therefore never appear, so `PlannedFeaturesColumn` (filters `effectiveStatus ∈
{draft, approved}`) is always empty.

**Fix.** In `planning.py`, after the existing `projected` loop that emits one
`FeatureSummaryItem` per real feature, scan `doc_rows` for documents whose
`doc_type` is `design_spec` / `spec` (with `doc_subtype` `design_spec` or
`design_doc`) or `prd`, and whose `feature_slug_canonical` (or hint) does not
match any already-emitted feature summary. For each such orphan spec/PRD,
synthesize a `FeatureSummaryItem` with:

- `feature_id` = `feature_slug_canonical` (fallback: slug derived from path)
- `feature_name` = document title
- `raw_status` = document frontmatter `status` (fallback: `draft`)
- `effective_status` = same (no projection — there's no phase data yet)
- `is_mismatch` = `False`, `mismatch_state` = `"unknown"`
- `phase_count` = 0, `blocked_phase_count` = 0, `node_count` = 1
- A new optional field `source_artifact_kind: Literal["feature","design_spec","prd"]`
  on `FeatureSummaryItem` so the UI can render these rows differently if needed.

If an orphan `prd` and an orphan `design_spec` share a canonical slug, prefer
the `design_spec` (it is closer to "planned"). Dedupe by canonical slug.

**Also update counts:** increment `total_feature_count` for synthesized rows
and count any `draft`/`approved` synthesized row in a new
`planned_feature_count` on the DTO (additive, non-breaking).

**Do not** write these synthesized features back into the `features` table.
This is a read-layer synthesis only.

**Tests.** Extend `backend/tests/test_planning_query_service.py` (or the nearest
existing test for `get_project_planning_summary`) with fixtures covering:
- a design_spec with no matching implementation_plan → appears in summary with
  `source_artifact_kind="design_spec"`, `effective_status="draft"`.
- a PRD without impl plan → appears with `source_artifact_kind="prd"`.
- a design_spec whose slug matches an existing feature → NOT duplicated.

## Fix 2 — Phased plans & progress files shown as standalone artifacts (frontend)

**Root cause.** `ArtifactDrillDownPage.tsx` exposes `'implementation-plans'`
(which includes `phase_plan`) and `'progress'` as top-level drill-down
categories. `PlanningSummaryPanel` and friends render counts pulled from
`summary.nodeCountsByType` including `implementation_plan` (which mixes in
`phase_plan`) and `progress` as discoverable rows.

Per the design intent (same treatment as SPIKE/ADR), phase plans and progress
files are **evidence**, not independent planning artifacts. They should remain
reachable via the owning feature/phase drill-down (graph detail, phase ops)
but not appear as standalone top-level artifact categories.

**Fix.**

1. In `components/Planning/ArtifactDrillDownPage.tsx`:
   - Remove `'progress'` from `ArtifactDrillDownType` and `ARTIFACT_TYPE_CONFIGS`.
   - Remove `'phase_plan'` from the `implementation-plans` config's
     `docTypeTokens` (keep only `implementation_plan`).
2. In `components/Planning/PlanningSummaryPanel.tsx` (and any other
   `nodeCountsByType` consumer): stop surfacing `progress` as a clickable
   count. Keep the `implementation_plan` count, but compute it from a value
   that excludes `phase_plan` — either derive it frontend-side from the DTO if
   the backend already separates them, or leave the existing field and filter
   in the UI.
3. Update `services/planningRoutes.ts` (`planningArtifactsHref`) if needed so
   stale `progress` routes 404-redirect or route back to planning home.
4. Update any tests that currently assert progress/phase_plan appears as a
   standalone category.

**Keep:** the nested rendering of phase batches inside `PlanningNodeDetail`
and `PhaseOperationsPanel` — these already treat phase/progress as evidence.

## Fix 3 — Phase accordion missing "Phase N" prefix (frontend)

**Root cause.** `PhaseAccordion` in `components/Planning/PlanningNodeDetail.tsx`
(line 231) renders `{phase.phaseTitle || phase.phaseToken}`. The
`PhaseContextItem` type already carries `phaseNumber` (used in
`components/Planning/primitives/PhaseOperationsPanel.tsx:244` as
`Phase ${data.phaseNumber}`).

**Fix.** Update the accordion header to render
`Phase {phase.phaseNumber}: {phase.phaseTitle || phase.phaseToken}` (or fall
back to just `Phase {phase.phaseNumber}` if no title/token). Match the
visual pattern already used in `PhaseOperationsPanel`.

Add/extend a test in `components/Planning/__tests__/` that asserts the
rendered phase header contains the phase number.

## Out of scope

- Migrating features table to include design_specs/PRDs.
- Redesigning the planning graph node schema.
- Changing how `phase_plan` documents are parsed or linked.

## Quality gates

- `backend/.venv/bin/python -m pytest backend/tests/ -k "planning" -v`
- `npm run test` (vitest)
- `npm run typecheck`
- `npm run build`
