# Agentic SDLC Intelligence Developer Reference

Last updated: 2026-03-08

This reference covers the rollout script, feature-flag model, API surfaces, and primary implementation files for the Agentic SDLC Intelligence foundation.

## Primary backend files

- `backend/services/integrations/skillmeat_client.py`
- `backend/services/integrations/skillmeat_sync.py`
- `backend/services/integrations/skillmeat_resolver.py`
- `backend/services/stack_observations.py`
- `backend/services/workflow_effectiveness.py`
- `backend/services/stack_recommendations.py`
- `backend/services/agentic_intelligence_flags.py`
- `backend/routers/integrations.py`
- `backend/routers/features.py`
- `backend/routers/analytics.py`
- `backend/scripts/agentic_intelligence_rollout.py`

## Primary frontend files

- `components/execution/RecommendedStackCard.tsx`
- `components/execution/WorkflowEffectivenessSurface.tsx`
- `components/FeatureExecutionWorkbench.tsx`
- `components/Analytics/AnalyticsDashboard.tsx`
- `components/Settings.tsx`
- `services/analytics.ts`
- `services/agenticIntelligence.ts`
- `types.ts`

## Feature flags

### Global env gates

- `CCDASH_SKILLMEAT_INTEGRATION_ENABLED`
  - hard-disables SkillMeat sync/cache/observation endpoints
- `CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED`
  - hard-disables stack recommendation generation
- `CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED`
  - hard-disables workflow effectiveness and failure-pattern endpoints

### Project-scoped settings

Stored under `Project.skillMeat.featureFlags`:

- `stackRecommendationsEnabled`
- `workflowAnalyticsEnabled`

The frontend uses these flags to hide or replace surfaces with disabled-state notices. The backend uses them to skip expensive work and return consistent `503 feature_disabled` responses where appropriate.

## Rollout script

Command:

```bash
python backend/scripts/agentic_intelligence_rollout.py --project <project-id>
```

Supported flags:

- `--all-projects`
- `--skip-sync`
- `--skip-backfill`
- `--skip-recompute`
- `--limit`
- `--force-recompute`

Execution order:

1. sync SkillMeat definitions into the external definition cache
2. backfill session stack observations
3. recompute workflow-effectiveness rollups and failure-pattern summaries

## API surface

### Integrations

- `POST /api/integrations/skillmeat/sync`
- `GET /api/integrations/skillmeat/definitions`
- `POST /api/integrations/skillmeat/observations/backfill`
- `GET /api/integrations/skillmeat/observations`

### Feature execution

- `GET /api/features/{feature_id}/execution-context`
  - adds:
    - `recommendedStack`
    - `stackAlternatives`
    - `stackEvidence`
    - `definitionResolutionWarnings`

### Analytics

- `GET /api/analytics/workflow-effectiveness`
- `GET /api/analytics/failure-patterns`

## Verification

Targeted checks used for this rollout:

```bash
python3 -m pytest backend/tests/test_agentic_intelligence_flags.py backend/tests/test_integrations_router.py backend/tests/test_features_execution_context_router.py backend/tests/test_analytics_router.py -q
npm test -- --run services/__tests__/agenticIntelligence.test.ts
npm run build
```

`npm run typecheck` currently fails in unrelated pre-existing files outside this feature area (`components/ProjectBoard.tsx`, `contexts/DataContext.tsx`, `constants.ts`, `components/TranscriptMappedMessageCard.tsx`).
