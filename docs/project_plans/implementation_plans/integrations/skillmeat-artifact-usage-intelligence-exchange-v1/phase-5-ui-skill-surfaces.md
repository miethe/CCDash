---
schema_version: 3
doc_type: phase_plan
title: "Phase 5: UI & Skill Surfaces"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 5
phase_title: "UI & Skill Surfaces"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - Phase 4 complete: rollup export operational, ranking/recommendation API endpoints stable
  - API responses returning correct data against seeded test fixtures
exit_criteria:
  - All 5 surfaces render with seeded data (Analytics, Workflow Effectiveness, Execution Workbench, Settings, MCP/CLI)
  - All surfaces handle missing or null fields gracefully (R-P2 fallback ACs satisfied)
  - Runtime smoke test confirms all 5 surfaces at known routes
  - MCP tool `artifact_recommendations` returns concise summary
  - CLI `ccdash artifact rankings` and `ccdash artifact recommendations` commands work
integration_owner: ui-engineer-enhanced
ui_touched: true
target_surfaces:
  - components/Analytics/AnalyticsDashboard.tsx
  - components/Analytics/ArtifactRankingsView.tsx
  - components/execution/WorkflowEffectivenessSurface.tsx
  - components/execution/ArtifactContributionPanel.tsx
  - components/execution/ExecutionWorkbenchRecommendations.tsx
  - components/Settings.tsx
seam_tasks:
  - T5-007
---

# Phase 5: UI & Skill Surfaces

## Phase Overview

**Estimate**: 6 pts
**Duration**: ~4–5 days
**Dependencies**: Phase 4 complete (backend APIs stable)
**Assigned Subagent(s)**: ui-engineer-enhanced (primary), frontend-developer (Settings + MCP/CLI)

This is the only UI-touching phase. R-P4 applies: a runtime smoke task (T5-008) is mandatory and must reference all 5 target surfaces. R-P3 applies: ui-engineer-enhanced and frontend-developer share `types.ts` as an overlapping file — integration_owner is ui-engineer-enhanced.

### Scope

Five new or extended surfaces:

1. **Analytics: Artifact Rankings View** — new tab or section in `AnalyticsDashboard.tsx` with rankings table, filters, and inline recommendation badges
2. **Workflow Effectiveness: Artifact Contribution** — add artifact contribution panel to `WorkflowEffectivenessSurface.tsx`
3. **Execution Workbench: Recommendation Surface** — add recommendations section to the workbench, advisory-only with no mutation controls
4. **Settings: Snapshot Health** — extend `Settings.tsx` with SkillMeat snapshot diagnostics (age, unresolved count, export status, enable/disable flag)
5. **`ccdash` MCP/CLI query** — add `artifact_recommendations` MCP tool and `ccdash artifact` CLI subcommands

### Parallelization

```yaml
parallelization:
  batch_1:
    # Analytics surface, Settings panel, and MCP/CLI query can parallelize
    # (distinct component owners, no shared state mutations)
    - task: T5-001
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: medium
    - task: T5-004
      assigned_to: frontend-developer
      model: sonnet
      effort: low
    - task: T5-005
      assigned_to: frontend-developer
      model: sonnet
      effort: low
  batch_2:
    # Workflow Effectiveness and Execution Workbench surfaces
    - task: T5-002
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: medium
      depends_on: [T5-001]
    - task: T5-003
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: medium
      depends_on: [T5-001]
  batch_3:
    # Seam validation and runtime smoke after all surfaces built
    - task: T5-006
      assigned_to: frontend-developer
      model: sonnet
      effort: low
      depends_on: [T5-001, T5-002, T5-003, T5-004, T5-005]
    - task: T5-007
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: low
      depends_on: [T5-001, T5-002, T5-003, T5-004]
    - task: T5-008
      assigned_to: ui-engineer-enhanced
      model: sonnet
      effort: low
      depends_on: [T5-001, T5-002, T5-003, T5-004, T5-005, T5-006, T5-007]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T5-001 | Analytics: Artifact Rankings View | Add `ArtifactRankingsView.tsx` under `components/Analytics/`. Renders a filterable table of ranking rows: artifact name, type, usage tokens, cost, success score, efficiency score, context pressure, recommendation badges. Filters: project, collection, user, period, artifact type, workflow, recommendation type. API call: `GET /api/analytics/artifact-rankings`. Ranking rows fetched via `services/analytics.ts`. | View renders with seeded data. Filters correctly narrow results. Recommendation badges display type and confidence. Empty state: no data message. Error state: API failure shows error with retry. Loading state: skeleton shown during fetch. AC-T5-001-FE-Fallback: all optional fields on `ArtifactRankingRow` handled (see structured AC). | 1.5 pts | ui-engineer-enhanced | sonnet | medium | Phase 4 complete |
| T5-002 | Workflow Effectiveness: Artifact Contribution | Extend `components/execution/WorkflowEffectivenessSurface.tsx` with `ArtifactContributionPanel.tsx`. Shows top-N artifacts by contribution for the selected workflow, with usage tokens, effectiveness score, and top recommendation. API call: `GET /api/analytics/artifact-rankings?workflow_id=X`. | Panel renders artifact contributions for a seeded workflow. Top-3 artifacts shown by default (expandable). Recommendation badge shown if present. AC-T5-002-FE-Fallback: missing artifact contribution data renders "No artifact data" placeholder without throwing. | 1 pt | ui-engineer-enhanced | sonnet | medium | T5-001 |
| T5-003 | Execution Workbench: Recommendations Surface | Add recommendations section to Execution Workbench (component path TBD — likely `components/execution/` or a modal panel). Shows artifact optimization recommendations for the selected feature/workflow. Advisory-only: no accept/reject/apply controls in V1. Shows: recommendation type, confidence, affected artifact, rationale, next_action. API call: `GET /api/analytics/artifact-recommendations`. | Recommendations section renders with seeded data. Advisory-only: no mutation controls present. Confidence displayed prominently (percentage or bar). Stale-snapshot warning shown if snapshot age > threshold. AC-T5-003-FE-Fallback: missing recommendations renders "No recommendations" placeholder. AC-T5-003-Advisory: no apply/accept/reject button rendered regardless of recommendation type. | 1 pt | ui-engineer-enhanced | sonnet | medium | T5-001 |
| T5-004 | Settings: Snapshot Health Panel | Extend `components/Settings.tsx` with SkillMeat Artifact Intelligence section. Shows: snapshot age (last fetched), artifact count, unresolved identity count, export freshness (last rollup export), artifact intelligence enabled/disabled toggle (writes to `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` config). API call: agent query for snapshot diagnostics. | Snapshot health data renders correctly. Snapshot age shown in human-readable format (e.g., "2 hours ago"). Unresolved count links to a tooltip explaining identity reconciliation. Enable/disable toggle persists setting. AC-T5-004-FE-Fallback: missing snapshot_health data renders "No snapshot data" with a "Fetch Now" action button, not an error. | 0.5 pts | frontend-developer | sonnet | low | Phase 4 complete |
| T5-005 | MCP tool and CLI commands | Add `artifact_recommendations` MCP tool to `backend/mcp/server.py` (FastMCP). Tool signature: `artifact_recommendations(project_id, min_confidence=0.7, limit=5) -> str`. Returns concise markdown summary of top recommendations. Add CLI subcommands to `backend/cli/`: `ccdash artifact rankings --project X --period 7d` and `ccdash artifact recommendations --project X --min-confidence 0.7`. | MCP tool returns concise markdown summary with artifact names, recommendation types, and confidence. CLI commands return JSON or markdown output. MCP tool registered and listed in `backend/tests/test_mcp_server.py`. CLI commands appear in `ccdash --help`. Both handle missing data gracefully (return "No recommendations available" not an error). | 0.5 pts | frontend-developer | sonnet | low | Phase 4 complete |
| T5-006 | apiClient.ts fetch helpers | Add typed API fetch helpers to `services/apiClient.ts` (or `services/analytics.ts`): `fetchArtifactRankings(params)`, `fetchArtifactRecommendations(params)`, `fetchSnapshotDiagnostics(project_id)`. Use existing fetch patterns. | All 3 helpers return typed responses. Error handling follows existing apiClient patterns. TypeScript compilation clean. | 0.5 pts | frontend-developer | sonnet | low | T5-001, T5-002, T5-003, T5-004 |
| T5-007 | Seam task: FE↔BE contract validation | Verify that all 5 UI surfaces call the correct API endpoints and correctly handle the full range of response shapes (success, empty, error, partial data). Run against seeded test fixtures. This is the cross-owner seam validation task. | All 5 surfaces confirmed to call correct endpoints. All surfaces handle empty state, error state, and partial data (missing optional fields). Type compatibility between TypeScript interfaces and API response shapes confirmed. | 0.5 pts | ui-engineer-enhanced | sonnet | low | T5-001, T5-002, T5-003, T5-004 |
| T5-008 | Runtime smoke test | Start dev server. Confirm all 5 surfaces render at their routes: (1) Analytics > Artifact Rankings, (2) Workflow Effectiveness > Artifact Contribution, (3) Execution Workbench > Recommendations, (4) Settings > Artifact Intelligence, (5) `ccdash artifact recommendations` CLI command. Confirm no JS console errors. Confirm loading, empty, and error states render without crashes. | Smoke test sign-off: all 5 surfaces render. No unhandled JS exceptions. Loading states visible during API fetch. Empty states render "No data" placeholders. Error states show error UI, not blank page. | 0.5 pts | ui-engineer-enhanced | sonnet | low | All T5-001 through T5-007 |

---

## Structured ACs

#### AC T5-001-FE-Fallback: ArtifactRankingsView handles missing optional fields
- target_surfaces:
    - components/Analytics/ArtifactRankingsView.tsx
- propagation_contract: >
    ArtifactRankingsView receives ArtifactRankingRow[] from fetchArtifactRankings().
    All optional fields on ArtifactRankingRow (success_score, efficiency_score, context_pressure,
    identity_confidence, recommendation) accessed via optional chaining.
- resilience: >
    If success_score is null/undefined: render "—" placeholder, not 0 or NaN.
    If recommendation is null/undefined: badge not rendered, not an error.
    If context_pressure is null/undefined: progress bar not rendered.
    If entire array is empty: "No artifact rankings available" empty state rendered.
- visual_evidence_required: desktop ≥1440px screenshot of empty state and loaded state
- verified_by:
    - T5-007
    - T5-008

#### AC T5-003-Advisory-Only: No mutation controls in Recommendations Surface
- target_surfaces:
    - components/execution/ExecutionWorkbenchRecommendations.tsx
- propagation_contract: >
    Recommendations rendered as read-only cards. next_action displayed as instructional text.
    No action buttons (apply, accept, reject, dismiss) rendered in V1.
- resilience: >
    Even if backend recommendation object contains a hypothetical apply_url field in a future
    API version, V1 frontend must not render action controls. The V1 component should not
    consume or render any field named apply_*, action_url, or mutation_*.
- visual_evidence_required: desktop ≥1440px screenshot of recommendations panel
- verified_by:
    - T5-008

#### AC T5-004-FE-Fallback: Settings snapshot health handles missing data
- target_surfaces:
    - components/Settings.tsx
- propagation_contract: >
    Snapshot diagnostics fetched via fetchSnapshotDiagnostics(). SnapshotHealth interface
    uses all-optional fields. Settings panel checks for null/undefined before rendering each field.
- resilience: >
    If SnapshotHealth is null (no snapshot yet): render "No snapshot data" message with
    "Fetch Now" action button. Not an error state — this is expected for new projects.
    If snapshot_age_seconds is null: render "Last fetched: Unknown".
    If unresolved_count is null: render "Identity mapping: Unavailable" with tooltip.
- visual_evidence_required: desktop ≥1440px screenshot showing no-data state
- verified_by:
    - T5-007
    - T5-008

---

## Key Files Affected

- `components/Analytics/ArtifactRankingsView.tsx` (new)
- `components/Analytics/AnalyticsDashboard.tsx` — add Artifact Rankings tab/section
- `components/execution/ArtifactContributionPanel.tsx` (new)
- `components/execution/WorkflowEffectivenessSurface.tsx` — add artifact contribution panel
- `components/execution/ExecutionWorkbenchRecommendations.tsx` (new)
- `components/Settings.tsx` — add Artifact Intelligence section
- `services/analytics.ts` — add `fetchArtifactRankings`, `fetchArtifactRecommendations`
- `services/apiClient.ts` — add `fetchSnapshotDiagnostics`
- `types.ts` — new interfaces: `ArtifactRankingRow`, `ArtifactRecommendation`, `SnapshotHealth`
- `backend/mcp/server.py` — add `artifact_recommendations` MCP tool
- `backend/cli/` — add `artifact` subcommand group with `rankings` and `recommendations`

---

## Quality Gates

- [ ] All 5 surfaces render with seeded data without console errors
- [ ] All optional fields on `ArtifactRankingRow` handled with graceful fallbacks (R-P2)
- [ ] Advisory-only constraint: no mutation controls in Recommendations Surface (R-P4)
- [ ] Settings snapshot health panel renders no-data state correctly
- [ ] MCP tool `artifact_recommendations` returns concise markdown summary
- [ ] CLI `ccdash artifact rankings` and `ccdash artifact recommendations` work and appear in `--help`
- [ ] Seam task T5-007: all surfaces confirmed to call correct endpoints with correct response handling
- [ ] **Runtime smoke task T5-008 signed off (R-P4 mandatory) — all 5 target surfaces**
- [ ] TypeScript compilation clean across all new files
