# Session Block Insights Developer Reference

Last updated: 2026-03-12

This reference covers the rollout controls, calculation path, and primary files for session block insights.

## Rollout model

### Global env gate

- `CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED`
  - defaults to `true`
  - hard-disables the project-scoped flag when set to `false`

### Project-scoped flag

Stored under `Project.skillMeat.featureFlags.sessionBlockInsightsEnabled`.

The frontend uses this flag to show or hide the Session Inspector block-analytics surface. The backend helper mirrors the same flag for future API-side gating.

## Calculation path

Primary calculator:

- `lib/sessionBlockInsights.ts`

Source precedence:

1. `session.usageEvents`
2. `session.logs[*].metadata`

Included workload families:

- `model_input`
- `model_output`
- `cache_creation_input`
- `cache_read_input`

Cost allocation:

- block cost uses the session display-cost total from `resolveDisplayCost(session)`
- the calculator distributes that cost proportionally across the included workload-token total so block costs remain additive

Block semantics:

- blocks roll forward from `session.startedAt`
- default duration is `5` hours
- UI overrides support `1h`, `3h`, `5h`, and `8h`
- completed sessions can end with a `partial` final block
- active sessions expose `projectedWorkloadTokens` and `projectedCostUsd` for the latest block

## Primary files

- `components/SessionInspector.tsx`
- `components/Settings.tsx`
- `lib/sessionBlockInsights.ts`
- `services/agenticIntelligence.ts`
- `backend/services/agentic_intelligence_flags.py`
- `backend/config.py`
- `types.ts`
- `backend/models.py`

## Validation

Frontend tests:

```bash
pnpm test -- lib/__tests__/sessionBlockInsights.test.ts services/__tests__/agenticIntelligence.test.ts
pnpm build
```

Backend tests:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_agentic_intelligence_flags.py -q
```

If `pytest` is unavailable in `backend/.venv`, install backend dev dependencies before rerunning the backend check.
