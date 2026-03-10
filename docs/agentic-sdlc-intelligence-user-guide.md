# Agentic SDLC Intelligence User Guide

Last updated: 2026-03-10

Use the agentic SDLC intelligence surfaces to understand which workflow stacks are working, why they work, and where failure patterns are repeating.

## Where it appears

- `/execution`
  - Recommended Stack card in the feature workbench
  - embedded Workflow Intelligence panel in the `Analytics` tab
- `/analytics?tab=workflow_intelligence`
  - cross-project workflow, agent, skill, context, and stack leaderboard
  - ranked failure-pattern list with representative session evidence
  - attributed token, cost, coverage, and cache-share summaries when usage attribution is enabled
- `/analytics?tab=attribution`
  - direct entity-level attribution leaderboard and calibration view
- `Settings > Projects > SkillMeat Integration`
  - per-project toggles for `Recommended Stack UI`, `Usage Attribution`, and `Workflow Effectiveness`

## Recommended Stack card

The workbench card combines current feature state with historical evidence:

- primary recommended stack with confidence, quality, efficiency, and risk scores
- resolved SkillMeat workflow/skill/context chips when cached definitions are available
- insight badges for effective workflow precedence, curated bundle matches, context previews, and recent SkillMeat executions
- dedicated insight panels for:
  - context coverage and preview token footprint
  - curated bundle fit and matched artifact refs
  - execution awareness, including recent/completed/active run counts
- alternative stacks ranked behind the primary recommendation
- similar-work examples that link back to past sessions and related features
- warnings when the system falls back to local CCDash evidence instead of resolved SkillMeat definitions
- direct open actions that route to the audited SkillMeat workflow, memory, bundle, or execution destination when CCDash has enough identifiers

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
- attribution overlays:
  - attributed tokens
  - attributed cost
  - attribution coverage
  - attribution cache share

Use the feature-level embedded view in `/execution` when deciding what to do next for one feature. Use the full `/analytics` tab when you want to compare patterns across the active project.

Use `/analytics?tab=attribution` when you want entity-first token ownership rather than outcome-first workflow ranking.

## Disabled states

If a project disables one of the intelligence surfaces:

- `/execution` keeps command recommendations and run controls available.
- `/analytics` keeps the rest of the analytics dashboard available.
- the disabled surface shows an inline notice instead of a blank or broken panel.
- Session Inspector keeps the rest of the analytics surface available when usage attribution is disabled.

## SkillMeat settings modes

Use `Settings > Projects > SkillMeat Integration`.

- Local mode:
  - leave `AAA enabled` off
  - leave the API key empty
  - set `Project Path` to the SkillMeat filesystem `project_id`
  - use `Collection ID` only when artifact/bundle scope needs it
- AAA-enabled mode:
  - enable `AAA enabled`
  - enter the API credential in `API Key`
  - wait for the connection, project mapping, and auth indicators to confirm the config
- Compatibility note:
  - legacy `workspaceId` values are deprecated and are not the primary mapping key in V2
  - CCDash now treats the SkillMeat project filesystem path as canonical

## Recommended pilot workflow

1. Enable SkillMeat integration and enter the base URL plus the SkillMeat project filesystem path.
2. Leave `AAA enabled` off for local SkillMeat or enable it and provide an API key for protected instances.
3. Confirm the connection, project mapping, and auth indicators in Settings.
4. Leave `Recommended Stack UI`, `Usage Attribution`, and `Workflow Effectiveness` enabled for the pilot project.
5. Ask an operator to run:
   - `python backend/scripts/agentic_intelligence_rollout.py --project <project-id> --fail-on-warning`
6. Open `/execution` for a feature with linked docs or linked sessions.
7. Review:
   - the recommended stack
   - the context coverage / curated bundle / execution awareness insight panels
   - the similar-work evidence
8. If SkillMeat is temporarily unavailable, continue using cached recommendations and previously computed rollups until the source comes back.
9. Review `/analytics?tab=attribution` to validate entity ownership and confidence before making workflow changes.
10. Review `/analytics?tab=workflow_intelligence` after a few sessions to spot patterns that should be standardized or retired.
