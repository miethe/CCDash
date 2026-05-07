# Phase 5: Workflow Diagnostics Inventory

## Workflow-Related Components

### Already correctly located in `components/Workflows/`
| File | Notes |
|------|-------|
| `components/Workflows/WorkflowRegistryPage.tsx` | Page shell for `/workflows` and `/workflows/:workflowId` routes |
| `components/Workflows/workflowRegistryUtils.ts` | Utility functions for the registry |
| `components/Workflows/catalog/WorkflowCatalog.tsx` | Catalog list view |
| `components/Workflows/catalog/WorkflowListItem.tsx` | Individual workflow list item |
| `components/Workflows/detail/WorkflowDetailPanel.tsx` | Detail panel for a selected workflow |
| `components/Workflows/__tests__/workflowRegistryRendering.test.tsx` | Rendering tests for the registry |

### Misplaced — needs to move
| File | Current location | Target location |
|------|-----------------|-----------------|
| `components/execution/WorkflowEffectivenessSurface.tsx` | `execution/` | `components/Workflows/WorkflowEffectivenessSurface.tsx` |

### Execution-owned — correct, do NOT move
| File | Reason |
|------|--------|
| `components/execution/RecommendedStackCard.tsx` | Stack recommendation UI — belongs to execution, not workflow diagnostics |
| `components/execution/RecommendedStackPreviewCard.tsx` | Preview wrapper around RecommendedStackCard — same rationale |

## Workflow Routes (App.tsx lines 90–91)

```
/workflows            → WorkflowRegistryPage
/workflows/:workflowId → WorkflowRegistryPage
```

No route changes required.

## Workflow Services

| File | Status |
|------|--------|
| `services/workflows.ts` | Correctly placed — stays at `services/workflows.ts` |
| `services/__tests__/workflows.test.ts` | Test coverage for the service layer |

## Analytics Embedding

`components/Analytics/AnalyticsDashboard.tsx`
- Line 41: imports `WorkflowEffectivenessSurface` from `../execution/WorkflowEffectivenessSurface`
- Line 50: declares `AnalyticsTab` union including `'workflow_intelligence'`
- Line 55: registers the `workflow_intelligence` tab with label "Workflow Intel"
- Lines 683–705: renders `<WorkflowEffectivenessSurface>` when that tab is active

`components/FeatureExecutionWorkbench.tsx`
- Line 80: imports `WorkflowEffectivenessSurface` from `./execution/WorkflowEffectivenessSurface`
- Line 3158–3182: embeds the surface in the workbench view with a link to `/analytics?tab=workflow_intelligence`

## Summary: What Moves vs What Stays

| File | Action |
|------|--------|
| `components/execution/WorkflowEffectivenessSurface.tsx` | **MOVE** to `components/Workflows/WorkflowEffectivenessSurface.tsx` |
| `components/Analytics/AnalyticsDashboard.tsx` | Update import path only |
| `components/FeatureExecutionWorkbench.tsx` | Update import path only |
| `services/workflows.ts` | Stay — already workflow-owned |
| `components/Workflows/*` (all others) | Stay — already correctly located |
| `components/execution/RecommendedStackCard.tsx` | Stay — execution concept |
| `components/execution/RecommendedStackPreviewCard.tsx` | Stay — execution concept |
