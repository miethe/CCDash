# Execution Workbench User Guide

Last updated: 2026-03-09

Use the Execution Workbench to launch, monitor, and control local terminal commands from inside CCDash.

Route:

- `/execution`

## What was added

- In-app local run launch from recommendation commands.
- Recommended Stack card with confidence, alternatives, and similar-work evidence.
- Resolved SkillMeat definition chips plus fallback warnings when only local CCDash evidence is available.
- Inline V2 insight panels for context coverage, curated bundle fit, and recent SkillMeat execution activity.
- Embedded Workflow Intelligence panel in the `Analytics` tab for feature-scoped effectiveness and failure-pattern review.
- Pre-run policy review (command, working directory, env profile).
- Approval workflow for high-risk commands.
- Live run history and output streaming in a dedicated `Runs` tab.
- Run controls for `cancel` and `retry`.

## Recommended stack workflow

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

## How to run a command

1. Open `/execution` and select a feature.
2. In the recommendation panel, click `Run in Workbench` (or `Run` on an alternative).
3. In the review dialog:
   - verify or edit `Command`
   - set `Working Directory`
   - choose `Env Profile` (`default`, `minimal`, `project`, `ci`)
   - click `Re-check` to refresh policy verdict
4. Click `Launch Run`.

If the policy verdict is `deny`, launch is blocked until you change command/cwd/profile.

## Approval-required runs

Some commands are classified as `requires_approval` and enter `blocked` status.

To continue:

1. Open the `Runs` tab.
2. Select the blocked run.
3. Click `Review Approval`.
4. Choose `Approve and Run` or `Deny` (optional reason recorded).

## Runs tab

The `Runs` tab provides:

- `Run History` list for the selected feature
- selected run metadata (status, cwd, policy/risk, timestamps)
- live terminal output (stdout/stderr stream)
- actions:
  - `Cancel` for `queued`/`running`
- `Retry` for `failed`/`canceled`/`blocked`

## Analytics tab

The workbench `Analytics` tab now includes:

- summary cards for sessions, observed workload, cost, telemetry, and last event
- cache contribution surfaced alongside feature workload so high-cache Claude sessions are visible without opening the session detail page
- model IO and cost kept separate so token totals do not imply a direct dollar mapping
- embedded workflow intelligence scoped to the selected feature
- a shortcut into `/analytics?tab=workflow_intelligence`

If workflow intelligence is disabled for the current project, the summary cards remain and the intelligence panel is replaced with a notice.

## Run status meanings

- `queued`: accepted and waiting for execution start.
- `running`: subprocess is active.
- `succeeded`: process exited with code `0`.
- `failed`: process exited non-zero or failed to launch.
- `canceled`: user cancellation completed.
- `blocked`: policy or approval gate prevented execution.

## Troubleshooting

- If `Runs` is empty:
  - ensure a feature is selected.
  - launch at least one run from recommendation actions.
- If a run fails immediately:
  - check working directory exists and is inside workspace root.
  - verify command syntax and selected env profile.
- If approval keeps returning to blocked:
  - policy may now evaluate to `deny`; re-check in review flow and inspect reason codes.

For full workflow-intelligence behavior, see `docs/agentic-sdlc-intelligence-user-guide.md`.
