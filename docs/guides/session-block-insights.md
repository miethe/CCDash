# Session Block Insights Guide

End-user behavior and developer implementation details for session block insights.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-03-12

Session Block Insights adds optional burn-rate and billing-block views to `Session Inspector > Analytics` for longer Claude Code sessions.

### What it shows

- rolling blocks based on the main session start time
- per-block observed workload totals
- per-block display-cost totals
- token burn rate and cost burn rate
- projected end-of-block totals for the latest active or partial block

These views are additive only. They do not change the canonical `Observed Workload`, `Current Context`, or `Display Cost` values shown elsewhere in CCDash.

### Where to enable it

Use `Settings > Projects > SkillMeat Integration > Session Block Insights`.

If the global rollout gate is disabled, the toggle remains ineffective until the backend is restarted with:

```bash
CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED=true
```

### How to use it

1. Open a Claude Code session in `Session Inspector`.
2. Switch to the `Analytics` tab.
3. Use the `1h`, `3h`, `5h`, or `8h` buttons to change the block window.
4. Read the latest block summary for:
   - block workload
   - token burn rate
   - cost burn rate
   - projected end-of-block totals
5. Use the chart and recent-block cards to compare earlier blocks against the latest one.

### Interpretation notes

- `Observed workload` follows the same semantics used elsewhere in CCDash:
  - model input
  - model output
  - cache creation input
  - cache read input
- block analytics use the main session only, not linked subthreads
- short sessions show a notice instead of forcing a misleading block breakdown

### Data availability

CCDash prefers persisted `usageEvents` when they are available. If those are missing, it falls back to transcript message usage metadata.

If neither source is present, Session Inspector shows a data-availability notice instead of synthetic values.

## Developer Reference

Last updated: 2026-03-12

This reference covers the rollout controls, calculation path, and primary files for session block insights.

### Rollout model

#### Global env gate

- `CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED`
  - defaults to `true`
  - hard-disables the project-scoped flag when set to `false`

#### Project-scoped flag

Stored under `Project.skillMeat.featureFlags.sessionBlockInsightsEnabled`.

The frontend uses this flag to show or hide the Session Inspector block-analytics surface. The backend helper mirrors the same flag for future API-side gating.

### Calculation path

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

### Primary files

- `components/SessionInspector.tsx`
- `components/Settings.tsx`
- `lib/sessionBlockInsights.ts`
- `services/agenticIntelligence.ts`
- `backend/services/agentic_intelligence_flags.py`
- `backend/config.py`
- `types.ts`
- `backend/models.py`

### Validation

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
