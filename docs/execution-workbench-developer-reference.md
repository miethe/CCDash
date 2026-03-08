# Execution Workbench Developer Reference

Last updated: 2026-03-08

This reference documents the local-terminal execution integration for the Execution Workbench.

## Frontend implementation

Workbench page:

- `/Users/miethe/dev/homelab/development/CCDash/components/FeatureExecutionWorkbench.tsx`

Execution UI components:

- `/Users/miethe/dev/homelab/development/CCDash/components/execution/ExecutionRunHistory.tsx`
- `/Users/miethe/dev/homelab/development/CCDash/components/execution/ExecutionRunPanel.tsx`
- `/Users/miethe/dev/homelab/development/CCDash/components/execution/ExecutionApprovalDialog.tsx`
- `/Users/miethe/dev/homelab/development/CCDash/components/execution/RecommendedStackCard.tsx`
- `/Users/miethe/dev/homelab/development/CCDash/components/execution/WorkflowEffectivenessSurface.tsx`

Client service + shared types:

- `/Users/miethe/dev/homelab/development/CCDash/services/execution.ts`
- `/Users/miethe/dev/homelab/development/CCDash/services/analytics.ts`
- `/Users/miethe/dev/homelab/development/CCDash/services/agenticIntelligence.ts`
- `/Users/miethe/dev/homelab/development/CCDash/types.ts`

Route wiring:

- `/Users/miethe/dev/homelab/development/CCDash/App.tsx` (`/execution`)

## Backend API and runtime

Router:

- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/execution.py`

Policy engine:

- `/Users/miethe/dev/homelab/development/CCDash/backend/services/execution_policy.py`

Runtime manager:

- `/Users/miethe/dev/homelab/development/CCDash/backend/services/execution_runtime.py`

Repositories:

- `/Users/miethe/dev/homelab/development/CCDash/backend/db/repositories/execution.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/db/repositories/postgres/execution.py`

## REST endpoints

- `POST /api/execution/policy-check`
- `POST /api/execution/runs`
- `GET /api/execution/runs`
- `GET /api/execution/runs/{run_id}`
- `GET /api/execution/runs/{run_id}/events`
- `POST /api/execution/runs/{run_id}/approve`
- `POST /api/execution/runs/{run_id}/cancel`
- `POST /api/execution/runs/{run_id}/retry`
- `GET /api/features/{feature_id}/execution-context`
- `GET /api/analytics/workflow-effectiveness`
- `GET /api/analytics/failure-patterns`

## Run lifecycle

1. UI runs `policy-check` from review modal.
2. `create run` writes `execution_runs` + initial event.
3. Policy verdict paths:
   - `allow` -> run moves to `queued`, runtime starts immediately.
   - `requires_approval` -> run stays `blocked` until approval.
   - `deny` -> run remains `blocked` with policy reason events.
4. Runtime streams stdout/stderr into `execution_run_events`.
5. UI polls `GET run` + incremental events (`after_sequence`) while run is active.
6. Terminal status is persisted as `succeeded`/`failed`/`canceled`.

## Execution storage model

Tables:

- `execution_runs`
- `execution_run_events`
- `execution_approvals`

Key columns:

- run identity + project/feature scoping
- source + normalized command
- policy/risk/approval metadata
- lifecycle timestamps/status/exit code
- append-only event stream with sequence numbers

## Polling and UI behavior

- `Runs` tab keeps a feature-scoped run list.
- Selected run event feed is loaded once, then incrementally polled.
- Polling runs only while selected run is `queued` or `running`.
- Approval dialog and review modal both mutate run state through API, then refresh list.
- Stack recommendations are only rendered when project SkillMeat feature flags keep them enabled.
- Workflow intelligence can be disabled independently; the workbench and analytics dashboard render explicit fallback notices instead of firing disabled requests.

## Validation

Backend tests:

```bash
PYTHONPATH=. uv run pytest backend/tests/test_execution_router.py backend/tests/test_execution_policy_service.py -q
```

Frontend build:

```bash
npm run build
```

Additional intelligence checks:

```bash
python3 -m pytest backend/tests/test_agentic_intelligence_flags.py backend/tests/test_integrations_router.py backend/tests/test_features_execution_context_router.py backend/tests/test_analytics_router.py -q
npm test -- --run services/__tests__/agenticIntelligence.test.ts
```

See `/Users/miethe/dev/homelab/development/CCDash/docs/agentic-sdlc-intelligence-developer-reference.md` for rollout and flag details.
