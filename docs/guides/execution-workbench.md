# Execution Workbench Guide

End-user workflows and developer reference for execution recommendations, runs, approvals, and storage.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-04-06

Use the Execution Workbench to launch, monitor, and control local terminal commands from inside CCDash.

Recommendation evidence now follows the completed session-intelligence storage contract: `local` deployments rely on cache-oriented local evidence, while `enterprise` deployments can use canonical Postgres-backed transcript intelligence and checkpoint-backfilled history.

Route:

- `/execution`

### What was added

- In-app local run launch from recommendation commands.
- Recommended Stack card with confidence, alternatives, and similar-work evidence.
- Resolved SkillMeat definition chips plus fallback warnings when only local CCDash evidence is available.
- Inline V2 insight panels for context coverage, curated bundle fit, and recent SkillMeat execution activity.
- Embedded Workflow Intelligence panel in the `Analytics` tab for feature-scoped effectiveness and failure-pattern review.
- Dependency-aware execution context in the overview view:
  - blocked-by dependency chips and execution-gate status
  - family position, next item, and family-sequence summaries
  - linked document chips that open the document modal for the selected plan or progress file
- Pre-run policy review (command, working directory, env profile).
- Approval workflow for high-risk commands.
- Live run history and output streaming in a dedicated `Runs` tab.
- Run controls for `cancel` and `retry`.

### Recommended stack workflow

1. Open `/execution` and select a feature.
2. Review the Recommended Stack card before launching a run.
3. Check:
   - confidence score
   - sample size, success, quality, and risk metrics
   - primary components and resolved SkillMeat references
   - effective workflow / bundle / execution badges
   - context coverage, curated bundle, and execution-awareness panels
   - alternatives if the primary suggestion looks too risky
   - similar-work examples for prior sessions/features that produced the recommendation
4. If the project disables stack recommendations, the workbench keeps command guidance available and shows a disabled-state notice instead.

### Recommendation evidence posture

- `local` storage profile: recommendations stay grounded in local CCDash evidence and optional SkillMeat cache data; embeddings and enterprise historical backfill are not part of the local contract.
- `enterprise` storage profile: recommendations can draw on canonical transcript-intelligence rows, full analytics, and the checkpointed enterprise backfill path documented in [`docs/guides/session-intelligence-rollout-guide.md`](session-intelligence-rollout-guide.md).
- SkillMeat memory drafting is separate from launching runs. CCDash may surface reviewable draft candidates from successful sessions, but publication remains approval-gated and is not triggered automatically by the workbench.

### Dependency-aware overview

When a feature carries dependency and family metadata, the workbench overview now shows:

- the current execution gate and why the feature is blocked or ready
- family position and the next recommended family item
- blocked-by feature chips that navigate back to the feature board
- sequenced document chips that open the selected document in the modal

The top navigation row also keeps direct routes to `Board`, `Plans`, `Sessions`, and `Analytics` so you can jump between the family view, the plan catalog, and the broader analytics surfaces without leaving the workbench context.

### How to run a command

1. Open `/execution` and select a feature.
2. In the recommendation panel, click `Run in Workbench` (or `Run` on an alternative).
3. In the review dialog:
   - verify or edit `Command`
   - set `Working Directory`
   - choose `Env Profile` (`default`, `minimal`, `project`, `ci`)
   - click `Re-check` to refresh policy verdict
4. Click `Launch Run`.

If the policy verdict is `deny`, launch is blocked until you change command/cwd/profile.

### Approval-required runs

Some commands are classified as `requires_approval` and enter `blocked` status.

To continue:

1. Open the `Runs` tab.
2. Select the blocked run.
3. Click `Review Approval`.
4. Choose `Approve and Run` or `Deny` (optional reason recorded).

### Runs tab

The `Runs` tab provides:

- `Run History` list for the selected feature
- selected run metadata (status, cwd, policy/risk, timestamps)
- live terminal output (stdout/stderr stream)
- actions:
  - `Cancel` for `queued`/`running`
- `Retry` for `failed`/`canceled`/`blocked`

### Analytics tab

The workbench `Analytics` tab now includes:

- summary cards for sessions, observed workload, cost, telemetry, and last event
- cache contribution surfaced alongside feature workload so high-cache Claude sessions are visible without opening the session detail page
- model IO and cost kept separate so token totals do not imply a direct dollar mapping
- embedded workflow intelligence scoped to the selected feature
- a shortcut into `/analytics?tab=workflow_intelligence`
- a shortcut into `/workflows` when you need workflow identity, correlation, and drill-down actions rather than leaderboard comparisons

If workflow intelligence is disabled for the current project, the summary cards remain and the intelligence panel is replaced with a notice.

For storage posture and runtime validation expectations behind those analytics, see [`docs/guides/storage-profiles-guide.md`](storage-profiles-guide.md) and [`docs/guides/session-intelligence-rollout-guide.md`](session-intelligence-rollout-guide.md).

### Run status meanings

- `queued`: accepted and waiting for execution start.
- `running`: subprocess is active.
- `succeeded`: process exited with code `0`.
- `failed`: process exited non-zero or failed to launch.
- `canceled`: user cancellation completed.
- `blocked`: policy or approval gate prevented execution.

### Troubleshooting

- If `Runs` is empty:
  - ensure a feature is selected.
  - launch at least one run from recommendation actions.
- If a run fails immediately:
  - check working directory exists and is inside workspace root.
  - verify command syntax and selected env profile.
- If approval keeps returning to blocked:
  - policy may now evaluate to `deny`; re-check in review flow and inspect reason codes.

For full workflow-intelligence behavior, see `docs/guides/agentic-sdlc-intelligence.md` and `docs/guides/agentic-sdlc-intelligence.md`.

## Developer Reference

Last updated: 2026-03-23

This reference documents the local-terminal execution integration for the Execution Workbench.

### Frontend implementation

Workbench page:

- `components/FeatureExecutionWorkbench.tsx`

Execution UI components:

- `components/execution/ExecutionRunHistory.tsx`
- `components/execution/ExecutionRunPanel.tsx`
- `components/execution/ExecutionApprovalDialog.tsx`
- `components/execution/RecommendedStackCard.tsx`
- `components/execution/WorkflowEffectivenessSurface.tsx`

Client service + shared types:

- `services/execution.ts`
- `services/analytics.ts`
- `services/agenticIntelligence.ts`
- `types.ts`

Dependency-aware execution contract:

- `FeatureExecutionContext` now carries `dependencyState`, `familySummary`, `familyPosition`, `executionGate`, and `recommendedFamilyItem` alongside the existing recommendation and analytics payloads.
- The workbench overview reads those fields directly to render the execution-gate card, family position, blocked-by evidence, and linked document actions.
- Route buttons on the overview header intentionally point back to the board, plans, sessions, and analytics so the family view stays connected to the rest of CCDash.

Route wiring:

- `App.tsx` (`/execution`)

### Backend API and runtime

Router:

- `backend/routers/execution.py`

Policy engine:

- `backend/services/execution_policy.py`

Runtime manager:

- `backend/services/execution_runtime.py`

Repositories:

- `backend/db/repositories/execution.py`
- `backend/db/repositories/postgres/execution.py`

### REST endpoints

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

### Run lifecycle

1. UI runs `policy-check` from review modal.
2. `create run` writes `execution_runs` + initial event.
3. Policy verdict paths:
   - `allow` -> run moves to `queued`, runtime starts immediately.
   - `requires_approval` -> run stays `blocked` until approval.
   - `deny` -> run remains `blocked` with policy reason events.
4. Runtime streams stdout/stderr into `execution_run_events`.
5. UI polls `GET run` + incremental events (`after_sequence`) while run is active.
6. Terminal status is persisted as `succeeded`/`failed`/`canceled`.

### Execution storage model

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

### Polling and UI behavior

- `Runs` tab keeps a feature-scoped run list.
- Selected run event feed is loaded once, then incrementally polled.
- Polling runs only while selected run is `queued` or `running`.
- Approval dialog and review modal both mutate run state through API, then refresh list.
- Stack recommendations are only rendered when project SkillMeat feature flags keep them enabled.
- Workflow intelligence can be disabled independently; the workbench and analytics dashboard render explicit fallback notices instead of firing disabled requests.

### Dependency-aware execution rendering

- The feature board and document modal now expose the same family/dependency surfaces as the workbench, so `blocked_by` relations and `sequenceOrder` values should stay normalized across the API payloads.
- `FeatureExecutionContext.documents` should include the linked documents used for sequence chips, and the `feature` payload should already contain the derived dependency/family summary fields when the workbench renders.
- The workbench should treat the blocked-state banner as a review-only affordance. It is present when `reviewPolicy.verdict === 'deny'` and `reviewOpen` is true, with the button state disabled until the policy is reconsidered.

### Validation

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
npm test -- --run components/__tests__/dependencyAwareExecutionUi.test.tsx
```

See `docs/guides/agentic-sdlc-intelligence.md` for rollout and flag details.
