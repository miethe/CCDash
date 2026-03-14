# Workflow Registry User Guide

Last updated: 2026-03-14

Use the Workflow Registry to inspect how CCDash and SkillMeat currently understand a workflow, where that understanding is weak, and which evidence or definitions you should open next.

Route:

- `/workflows`

## What the Workflow Registry is for

The Workflow Registry is the workflow-identity hub for CCDash.

Use it when you need to answer questions like:

- which workflows CCDash is currently observing
- whether a workflow is strongly resolved to a SkillMeat definition or only weakly matched to a command artifact
- which artifact refs, context modules, bundles, or stages are attached to the workflow
- whether the workflow has enough historical evidence to trust its effectiveness scores
- which session or SkillMeat object to open next

## Catalog view

The left catalog pane supports:

- free-text search by workflow label, alias, or representative command
- correlation-state filters:
  - `All`
  - `Resolved`
  - `Hybrid`
  - `Weak`
  - `Unresolved`
- keyboard controls:
  - `/` or `Cmd/Ctrl+K` focuses search
  - `Arrow Up` / `Arrow Down` moves through visible rows
  - `Enter` opens the highlighted row

Each workflow card shows:

- the display label and primary observed workflow family ref
- correlation-state badge
- resolved SkillMeat workflow and/or command-artifact chips when available
- representative command evidence
- sample size and last-observed timestamp
- effectiveness mini-bars when rollups exist
- current issue count

## Detail view

Selecting a workflow opens a detail panel with:

- `Identity`
  - observed family ref and aliases
  - separate SkillMeat workflow-definition and command-artifact resolution
- `Actions`
  - open the SkillMeat workflow, command artifact, executions, bundle, or context memory
  - open a representative CCDash session
- `Composition`
  - artifact refs
  - context refs and resolved context modules
  - plan summary
  - stage order
  - gate and fan-out counts
  - bundle alignment
- `Effectiveness`
  - success, efficiency, quality, and risk
  - attribution coverage and confidence
  - evidence summary
- `Issues`
  - stale cache
  - weak or unresolved resolution
  - missing composition
  - missing context coverage
  - missing effectiveness evidence
- `Evidence`
  - representative CCDash sessions
  - recent SkillMeat workflow execution summaries

## How it relates to other surfaces

- `/execution`
  - use this when you are deciding what to run next for one feature
  - use the Workflow Registry when you need stronger identity and resolution context for the recommended workflow
- `/analytics?tab=workflow_intelligence`
  - use this when you want ranked comparisons across workflows, agents, skills, or stacks
  - use the Workflow Registry when you want one workflow’s identity, correlation quality, and drill-down actions in one place
- `Settings > Integrations > SkillMeat`
  - use this to enable or disable workflow analytics for the active project

## Disabled and empty states

- If no active project is selected, the page will ask you to choose one first.
- If workflow analytics are disabled for the project, the page will show a disabled-state notice instead of loading the registry.
- If the catalog has no matching workflows, use `Clear filters` or refresh the workflow cache from the existing SkillMeat/Ops flows.

## Recommended operator flow

1. Open `/workflows`.
2. Filter to `Hybrid`, `Weak`, or `Unresolved`.
3. Pick a workflow with recent observations and review its `Issues` section first.
4. Open the linked SkillMeat workflow, command artifact, or context memory if the issue points to missing or stale metadata.
5. Open a representative CCDash session when you need to inspect the raw command or transcript evidence.
6. Return to `/execution` or `/analytics` after you understand whether the workflow should be trusted, tuned, or ignored.
