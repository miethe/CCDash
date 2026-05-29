# Human Brief: Planning Command Center V1

## Purpose

Planning Command Center turns `/planning` into a project command console. The main operator question is: "What feature is live, what should run next, where is the plan, and what branch/worktree/commit is it on?"

## Operator Workflow

1. Open `/planning` for the active project.
2. Scan the command center list for active, ready, blocked, and done items.
3. Expand a row or open details to review the plan path, phase table, worktree, branch, git state, PR state, and related files.
4. Edit the suggested command only when local context needs to be added.
5. Copy the command or launch it through the Launch Sheet. Launch preserves execution guardrails for provider/model/worktree/approval.
6. Use card or board view when the operator needs portfolio triage instead of a dense list.

## Command Rules

The backend command resolver returns rule ids `PCC-CMD-001` through `PCC-CMD-009`. These map planning state to commands such as spike, explore, plan-feature, execute-phase, complete-user-story, or quick-feature fallback. Unsupported command capabilities are surfaced as warnings rather than hidden.

## Status Meaning

Done items show the branch or git head when available. Blocked items show the top blocker. Ready items have enough phase and launch batch context to open the Launch Sheet. Active items show the current phase/worktree context.

## Guardrails

The command center is a composition layer. It does not replace `/execution`, does not mutate git state directly, and does not bypass execution policy. Mutating launches still go through `PlanningLaunchSheet` and execution APIs.
