# Planning Command Center

The Planning Command Center is the project-level cockpit on `/planning`. It sits below the planning metrics and artifact chips and shows the live feature work queue with the context needed to choose the next command.

## What It Shows

Each row, card, or board item includes:

1. Feature name, status, planning signal, blockers, and story points remaining/total.
2. Current or next phase, target plan file, related artifacts, and related files that can be added to command context.
3. The deterministic next command, its resolver rule id, and required capabilities such as `planning` or `dev-execution`.
4. Worktree path, branch, git head, dirty count, upstream, ahead/behind, and probe warnings.
5. Launch batch readiness, PR/review state, and action availability.

## Views

Use the view switcher in the toolbar:

1. List: dense triage with expandable rows and editable command text.
2. Cards: scan-friendly feature cards with launch, plan, PR, and detail actions.
3. Board: status buckets for Needs Plan, Ready, Active Phase, Blocked, and Review/Done.

## Actions

Command edits are local until copied or launched. The launch action opens `PlanningLaunchSheet` and passes the edited command as the launch command override. Provider, model, approval, and worktree mutation remain owned by the execution launch flow.

PR buttons open the recorded pull request URL when available. Review and merge controls are capability-gated; disabled controls mean the command center has surfaced the state but will not bypass execution policy.

## Before And After Context

Before execution, read:

1. PRD: `docs/project_plans/PRDs/enhancements/planning-command-center-v1.md`
2. Implementation plan: `docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md`
3. Human brief: `docs/project_plans/human-briefs/planning-command-center-v1.md`
4. Wireframes: `docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/list-view.png` and `board-view.png`

After execution, read:

1. AAR: `docs/project_plans/reports/planning-command-center-v1-aar-2026-05-29.md`
2. Phase commits on branch `codex/planning-command-center-v1`
3. Focused test commands recorded in the implementation plan closeout
