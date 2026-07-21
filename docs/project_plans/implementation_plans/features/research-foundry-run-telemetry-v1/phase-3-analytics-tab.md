---
title: "Phase 3: Analytics visualization tab"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-21
updated: 2026-07-21
feature_slug: "research-foundry-run-telemetry"
feature_version: "v1"
phase: 3
phase_title: "Analytics visualization tab"
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
entry_criteria:
  - "Phase 2 exit gate passed: research_runs queryable, dedup regression test green, karen milestone review passed"
exit_criteria:
  - "Provider Economics tab renders from live/seeded data"
  - "Runtime smoke passed at desktop >=1440px (empty state + seeded-fixture state)"
  - "All resilience ACs verified for optional/absent fields"
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: backend-architect
ui_touched: true
target_surfaces:
  - components/Analytics/AnalyticsDashboard.tsx
seam_tasks:
  - T3-000
owner: null
contributors: []
priority: medium
risk_level: medium
category: "product-planning"
tags: [phase-plan, implementation, ui, analytics, seam]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - components/Analytics/AnalyticsDashboard.tsx
  - services/queryKeys.ts
  - types.ts
---

# Phase 3: Analytics visualization tab

**Parent Plan**: [Research Foundry Run Telemetry — Implementation Plan](../research-foundry-run-telemetry-v1.md)
**Duration**: ~1 week
**Effort**: 6.5 story points
**Dependencies**: Phase 2 complete (stable `run_intelligence.py` contract)
**Team Members**: `backend-architect` (seam owner), `frontend-developer`, `ui-engineer-enhanced`, `task-completion-validator`

---

## Phase Overview

This phase adds a 4-panel "Provider Economics" tab inside the existing
`components/Analytics/AnalyticsDashboard.tsx` (D4 — no new top-level route). Because Phase 2 is
backend-owned and this phase is frontend-owned, and both share a single typed contract
(`run_intelligence.py`'s REST response ↔ `types.ts` entities), this phase declares
**`integration_owner: backend-architect`** per Plan Generator Rule R-P3 and opens with an explicit
seam task (T3-000) that verifies the contract before any panel is built.

### Goals

- Ship `types.ts` entities + a `services/queryKeys.ts` registry entry for `research_runs` (FR-12 groundwork).
- Add the 4-panel tab: KPI strip, cost & quality by mode, spend/volume trend, run-level drill table (FR-12).
- Guarantee resilience for every optional/absent field — never `0`/`NaN` masquerading as real data (AC-4).
- Pass a runtime smoke check at desktop ≥1440px before this phase is considered done (R-P4).

### Architecture Focus

- **Layer**: UI (React 19 + TanStack Query)
- **Patterns**: Existing `AnalyticsDashboard.tsx` primitives — `MetricCard`, `TrendChart`,
  `EntityLinkButton`, dense-table patterns — reused, not reinvented
- **Standards**: TanStack Query hook + `services/queryKeys.ts` registry pattern (per
  `docs/guides/feature-surface-architecture.md`)

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|----------------------|----------|-------------|-------|--------|---------------|
| T3-000 | **Seam task** — contract verification (R-P3) | Verify the `GET /api/agent/research-runs` (+ detail) response DTO field names/types (Phase 2, T2-003/T2-004) exactly match the planned `types.ts` `ResearchRun`/`ResearchRunMetrics` interfaces before any panel work begins; write a short field-by-field mapping note; block T3-002 until this checklist passes | Zero field-name/type mismatches between backend DTO and FE type at panel-build time | 0.5 pts | backend-architect, frontend-developer | sonnet | adaptive | Phase 2 complete |
| T3-001 | `types.ts` entities + `queryKeys.ts` registry entry | Add `ResearchRun`, `ResearchRunMetrics` to root `types.ts`; add `researchRunsKeys` to `services/queryKeys.ts` per the existing registry pattern | Types match the seam-verified contract (T3-000); query key registry entry follows existing conventions | 0.5 pts | frontend-developer | sonnet | adaptive | T3-000 |
| T3-002 | TanStack Query hooks | `useResearchRuns` / `useResearchRunDetail` hooks wired to the new REST route, following the cache-tier conventions in `docs/guides/feature-surface-architecture.md` | Hooks handle loading/error/success/empty states | 1 pt | frontend-developer | sonnet | adaptive | T3-001 |
| T3-003 | Tab shell + KPI strip | New `id: 'research'` entry in `AnalyticsDashboard.tsx` `TAB_LABELS`; KPI strip using existing `MetricCard` | Tab appears in the dashboard nav; KPI strip renders from live/seeded data | 1.5 pts | ui-engineer-enhanced | sonnet | adaptive | T3-002 |
| T3-004 | Cost & quality by mode + spend/volume trend + run-level drill table | 3 remaining panels reusing `TrendChart` and dense-table patterns already in the file; grain is per-mode/per-run (honest v1 MVP, not per-provider — see Out of Scope in PRD §7) | All 3 panels render from the same hook data; `EntityLinkButton` opens the correlated session in `SessionInspector` when a link exists | 1.5 pts | ui-engineer-enhanced | sonnet | adaptive | T3-003 |
| T3-005 | Resilience fallbacks for optional/absent fields (R-P2, FE half) | Every optional field from the AC-2-Field backend contract (Phase 2) renders an explicit "—" per-cell when absent, never `$0.00`/`NaN`/`0%`; zero-events state renders "No research runs recorded yet" across all 4 panels | AC-4 resilience clause fully covered — see structured AC below | 0.5 pts | frontend-developer | sonnet | adaptive | T3-004 |
| T3-006 | Runtime smoke test (R-P4 gate) | Start the dev server; capture before/after screenshots at desktop ≥1440px for both the empty state (zero events) and the seeded-fixture state, covering every panel in `target_surfaces` | Screenshot evidence archived; AC-4 `visual_evidence_required` satisfied | 0.5 pts | frontend-developer | sonnet | adaptive | T3-005 |
| T3-007 | Phase 3 completion review | `task-completion-validator` verifies all Phase 3 ACs, including the seam checklist (T3-000) and runtime smoke evidence (T3-006) | Reviewer sign-off recorded before Phase 4 kickoff | 0.5 pts | task-completion-validator | sonnet | adaptive | T3-000 through T3-006 |

**Phase 3 total: 6.5 pts**

---

## Acceptance Criteria (structured)

### AC-4: Provider Economics tab renders correctly with zero events

- target_surfaces:
    - components/Analytics/AnalyticsDashboard.tsx
- propagation_contract: With `research_runs` empty, the "Provider Economics" tab renders an explicit empty state ("No research runs recorded yet") in all 4 panels — KPI strip, cost & quality by mode, spend/volume trend, run-level drill table.
- resilience: Missing (never null-vs-zero-conflated) `estimated_cost_usd`, `citation_coverage`, `latency_ms`, or any other optional metric on an individual run renders as an explicit "—" per-cell, never `$0.00`/`NaN`/`0%`.
- visual_evidence_required: desktop ≥1440px, before/after screenshots (empty state + seeded-fixture state)
- verified_by: [T3-006, T3-007]

### AC-4-Fields: Explicit enumeration of optional per-run fields (R-P2)

- target_surfaces:
    - components/Analytics/AnalyticsDashboard.tsx
- propagation_contract: The following fields, each optional on the `run_intelligence.py` DTO (per Phase 2's AC-2-Field), are rendered per-cell in the run-level drill table and/or KPI strip: `estimated_cost_usd`, `citation_coverage`, `latency_ms`, `mode`, `selected_providers`, `linked_session_id`, `rf_run_id`, `intent_id`, `task_node_id`.
- resilience: Each field renders "—" when `null`; `linked_session_id` absence renders "no linked session" (not a broken `EntityLinkButton`); `intent_id`/`task_node_id` render as opaque display strings only, never as clickable links (DF-007 — IntentTree resolution is deferred).
- visual_evidence_required: desktop ≥1440px, seeded-fixture state showing at least one run with each field null and one with all fields populated
- verified_by: [T3-005, T3-006, T3-007]

---

## Quality Gates

- [ ] Seam checklist (T3-000) passed — zero backend/FE type mismatches
- [ ] Tab renders all 4 panels from live/seeded data (T3-003, T3-004)
- [ ] Empty-state and per-field resilience verified (T3-005)
- [ ] **Runtime smoke** (`ui_touched: true`): screenshot evidence archived at `.claude/evidence/phase-3/` referencing every `target_surfaces` entry OR `runtime_smoke: skipped` with an explicit reason recorded — a clean unit-test pass is not a substitute (R-P4)
- [ ] `task-completion-validator` sign-off recorded (T3-007)

---

## Key Files Modified

| File Path | Purpose | Subagent |
|-----------|---------|----------|
| `components/Analytics/AnalyticsDashboard.tsx` | New "Provider Economics" tab, 4 panels | ui-engineer-enhanced, frontend-developer |
| `services/queryKeys.ts` | `researchRunsKeys` registry entry | frontend-developer |
| `types.ts` | `ResearchRun`, `ResearchRunMetrics` entities | frontend-developer |

---

## Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-21

[Return to Parent Plan](../research-foundry-run-telemetry-v1.md)
