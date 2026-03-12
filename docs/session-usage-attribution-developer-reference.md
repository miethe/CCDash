# Session Usage Attribution Developer Reference

Last updated: 2026-03-10

This reference covers the V2 attribution contract, rollout controls, API surfaces, and forward hooks for recommendation systems.

## Primary files

- `backend/services/session_usage_attribution.py`
- `backend/services/session_usage_analytics.py`
- `backend/services/workflow_effectiveness.py`
- `backend/services/agentic_intelligence_flags.py`
- `backend/routers/analytics.py`
- `backend/routers/api.py`
- `backend/db/repositories/usage_attribution.py`
- `backend/db/repositories/postgres/usage_attribution.py`
- `components/Analytics/AnalyticsDashboard.tsx`
- `components/execution/WorkflowEffectivenessSurface.tsx`
- `components/SessionInspector.tsx`
- `services/analytics.ts`
- `services/agenticIntelligence.ts`
- `types.ts`

## Contract summary

- `session_usage_events`
  - immutable event rows keyed by event identity
  - preserve token family, delta tokens, model-IO-derived cost, log linkage, and session linkage
- `session_usage_attributions`
  - derived links from events to entities
  - every non-trivial link carries `method`, `confidence`, and `weight`
- exclusive totals
  - sum only `attribution_role=primary`
- supporting totals
  - sum `attribution_role=supporting`
  - may exceed exclusive or session totals

## Supported entity scopes

- `skill`
- `agent`
- `subthread`
- `command`
- `artifact`
- `workflow`
- `feature`

## API surface

- `GET /api/analytics/usage-attribution`
  - aggregate rows by entity
  - returns exclusive/supporting totals, method mix, session count, and confidence summary
- `GET /api/analytics/usage-attribution/drilldown`
  - returns contributing attributed events for one entity row
- `GET /api/analytics/usage-attribution/calibration`
  - returns coverage, reconciliation gaps, ambiguity counts, confidence bands, and method mix
- `GET /api/sessions/{session_id}`
  - now includes:
    - `usageEvents`
    - `usageAttributions`
    - `usageAttributionSummary`
    - `usageAttributionCalibration`
- `GET /api/analytics/workflow-effectiveness`
  - now includes:
    - `attributedTokens`
    - `supportingAttributionTokens`
    - `attributedCostUsdModelIO`
    - `averageAttributionConfidence`
    - `attributionCoverage`
    - `attributionCacheShare`

## Rollout controls

### Global env gate

- `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED`
  - hard-disables attribution analytics endpoints
  - session detail payloads fall back to empty attribution fields instead of breaking the rest of the session view

### Project-scoped flag

Stored under `Project.skillMeat.featureFlags`:

- `usageAttributionEnabled`

Frontend behavior:

- `/analytics?tab=attribution` shows a disabled-state notice instead of firing attribution-only requests
- Session Inspector analytics shows a disabled-state notice for attribution
- workflow-effectiveness surfaces remain available

Backend behavior:

- attribution analytics endpoints return `503 feature_disabled`
- session detail keeps the base session payload intact and omits attribution payloads when disabled

## Interpretation rules to preserve

- Never merge exclusive and supporting totals into one “total”.
- Never present cache workload as direct cost.
- Calibration gaps are expected to be visible when attribution is conservative or disabled.
- Session totals remain the source of truth for workload correctness.

## V3 hooks preserved by V2

These outputs are stable inputs for later layers:

- recommendation ranking by attributed token efficiency
- stack optimization loops using cache share and attributed cost by workflow component
- broader cross-platform attribution once non-Claude parsers produce equivalent event/link contracts
- artifact-aware and feature-aware recommendation systems using method mix and confidence summaries

## Suggested verification

```bash
python3 -m pytest backend/tests/test_session_usage_analytics.py backend/tests/test_analytics_router.py backend/tests/test_sessions_api_router.py backend/tests/test_workflow_effectiveness.py backend/tests/test_agentic_intelligence_flags.py -q
npm test -- --run services/__tests__/agenticIntelligence.test.ts
```

`npm run typecheck` still has unrelated pre-existing failures outside the attribution work area as of 2026-03-10.
