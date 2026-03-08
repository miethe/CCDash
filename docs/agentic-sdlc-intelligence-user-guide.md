# Agentic SDLC Intelligence User Guide

Last updated: 2026-03-08

Use the agentic SDLC intelligence surfaces to understand which workflow stacks are working, why they work, and where failure patterns are repeating.

## Where it appears

- `/execution`
  - Recommended Stack card in the feature workbench
  - embedded Workflow Intelligence panel in the `Analytics` tab
- `/analytics?tab=workflow_intelligence`
  - cross-project workflow, agent, skill, context, and stack leaderboard
  - ranked failure-pattern list with representative session evidence
- `Settings > Projects > SkillMeat Integration`
  - per-project toggles for `Recommended Stack UI` and `Workflow Effectiveness`

## Recommended Stack card

The workbench card combines current feature state with historical evidence:

- primary recommended stack with confidence, quality, efficiency, and risk scores
- resolved SkillMeat workflow/skill/context chips when cached definitions are available
- alternative stacks ranked behind the primary recommendation
- similar-work examples that link back to past sessions and related features
- warnings when the system falls back to local CCDash evidence instead of resolved SkillMeat definitions

## Workflow Intelligence view

The workflow intelligence surface helps compare what has historically performed well:

- scope filters:
  - workflow
  - agent
  - skill
  - context module
  - stack
- scoring columns:
  - success
  - efficiency
  - quality
  - risk
- failure patterns:
  - queue waste
  - repeated debug loops
  - weak validation paths

Use the feature-level embedded view in `/execution` when deciding what to do next for one feature. Use the full `/analytics` tab when you want to compare patterns across the active project.

## Disabled states

If a project disables one of the intelligence surfaces:

- `/execution` keeps command recommendations and run controls available.
- `/analytics` keeps the rest of the analytics dashboard available.
- the disabled surface shows an inline notice instead of a blank or broken panel.

## Recommended pilot workflow

1. Enable SkillMeat integration and enter the base URL, project ID, and workspace ID.
2. Leave `Recommended Stack UI` and `Workflow Effectiveness` enabled for the pilot project.
3. Ask an operator to run:
   - `python backend/scripts/agentic_intelligence_rollout.py --project <project-id>`
4. Open `/execution` for a feature with linked docs or linked sessions.
5. Compare the recommended stack against recent similar work before launching a run.
6. Review `/analytics?tab=workflow_intelligence` after a few sessions to spot patterns that should be standardized or retired.
