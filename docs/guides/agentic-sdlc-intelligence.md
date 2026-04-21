# Agentic SDLC Intelligence Guide

User workflow, Workflow Registry behavior, and developer implementation reference for CCDash workflow intelligence.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-03-14

Use the agentic SDLC intelligence surfaces to understand which workflow stacks are working, why they work, and where failure patterns are repeating.

### Where it appears

- `/execution`
  - Recommended Stack card in the feature workbench
  - embedded Workflow Intelligence panel in the `Analytics` tab
- `/analytics?tab=workflow_intelligence`
  - cross-project workflow, agent, skill, context, and stack leaderboard
  - ranked failure-pattern list with representative session evidence
  - attributed token, cost, coverage, and cache-share summaries when usage attribution is enabled
- `/workflows`
  - dedicated workflow identity and correlation hub
  - searchable catalog with correlation-state filters
  - composition, effectiveness, issue, and action drill-down for one workflow at a time
- `/analytics?tab=attribution`
  - direct entity-level attribution leaderboard and calibration view
- `Settings > Integrations > SkillMeat`
  - per-project toggles for `Recommended Stack UI`, `Usage Attribution`, and `Workflow Effectiveness`

### Recommended Stack card

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

### Workflow Intelligence view

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

Use `/workflows` when you need to inspect one workflow deeply instead of comparing many rows:

- confirm whether the workflow is truly SkillMeat-backed or only command-backed
- inspect composition metadata such as stages, context modules, and bundle alignment
- review issue cards that explain unresolved or weak correlation states
- open the exact SkillMeat or CCDash object that explains the workflow’s current state

Use `/analytics?tab=attribution` when you want entity-first token ownership rather than outcome-first workflow ranking.

### Disabled states

If a project disables one of the intelligence surfaces:

- `/execution` keeps command recommendations and run controls available.
- `/analytics` keeps the rest of the analytics dashboard available.
- the disabled surface shows an inline notice instead of a blank or broken panel.
- Session Inspector keeps the rest of the analytics surface available when usage attribution is disabled.

### SkillMeat settings modes

Use `Settings > Integrations > SkillMeat`.

- Local mode:
  - leave `AAA enabled` off
  - leave the API key empty
  - set `Project ID` to the SkillMeat project identifier
  - use `Collection ID` only when artifact/bundle scope needs it
- AAA-enabled mode:
  - enable `AAA enabled`
  - enter the API credential in `API Key`
  - wait for the connection, project mapping, and auth indicators to confirm the config
- Compatibility note:
  - legacy `workspaceId` values are deprecated and are not the primary mapping key in V2
  - CCDash now treats the SkillMeat `projectId` as the canonical mapping value

### Recommended pilot workflow

1. Enable SkillMeat integration and enter the base URL plus the SkillMeat project ID.
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
11. Open `/workflows` to inspect the identity, evidence, and next-hop actions for any workflow that looks ambiguous or unusually effective.

## Workflow Registry User Guide

Last updated: 2026-03-14

Use the Workflow Registry to inspect how CCDash and SkillMeat currently understand a workflow, where that understanding is weak, and which evidence or definitions you should open next.

Route:

- `/workflows`

### What the Workflow Registry is for

The Workflow Registry is the workflow-identity hub for CCDash.

Use it when you need to answer questions like:

- which workflows CCDash is currently observing
- whether a workflow is strongly resolved to a SkillMeat definition or only weakly matched to a command artifact
- which artifact refs, context modules, bundles, or stages are attached to the workflow
- whether the workflow has enough historical evidence to trust its effectiveness scores
- which session or SkillMeat object to open next

### Catalog view

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

### Detail view

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

### How it relates to other surfaces

- `/execution`
  - use this when you are deciding what to run next for one feature
  - use the Workflow Registry when you need stronger identity and resolution context for the recommended workflow
- `/analytics?tab=workflow_intelligence`
  - use this when you want ranked comparisons across workflows, agents, skills, or stacks
  - use the Workflow Registry when you want one workflow’s identity, correlation quality, and drill-down actions in one place
- `Settings > Integrations > SkillMeat`
  - use this to enable or disable workflow analytics for the active project

### Disabled and empty states

- If no active project is selected, the page will ask you to choose one first.
- If workflow analytics are disabled for the project, the page will show a disabled-state notice instead of loading the registry.
- If the catalog has no matching workflows, use `Clear filters` or refresh the workflow cache from the existing SkillMeat/Ops flows.

### Recommended operator flow

1. Open `/workflows`.
2. Filter to `Hybrid`, `Weak`, or `Unresolved`.
3. Pick a workflow with recent observations and review its `Issues` section first.
4. Open the linked SkillMeat workflow, command artifact, or context memory if the issue points to missing or stale metadata.
5. Open a representative CCDash session when you need to inspect the raw command or transcript evidence.
6. Return to `/execution` or `/analytics` after you understand whether the workflow should be trusted, tuned, or ignored.

## Developer Reference

Last updated: 2026-03-14

This reference covers the rollout script, feature-flag model, API surfaces, and primary implementation files for the Agentic SDLC Intelligence foundation.

For the full current-state Workflow + SkillMeat dataflow, resolution behavior, storage model, and tuning gaps, see [workflow-skillmeat-integration.md](../developer/workflow-skillmeat-integration.md).

### Primary backend files

- `backend/services/integrations/skillmeat_client.py`
- `backend/services/integrations/skillmeat_sync.py`
- `backend/services/integrations/skillmeat_resolver.py`
- `backend/services/integrations/skillmeat_routes.py`
- `backend/services/stack_observations.py`
- `backend/services/workflow_effectiveness.py`
- `backend/services/stack_recommendations.py`
- `backend/services/agentic_intelligence_flags.py`
- `backend/routers/integrations.py`
- `backend/routers/features.py`
- `backend/routers/analytics.py`
- `backend/scripts/agentic_intelligence_rollout.py`

### Primary frontend files

- `components/execution/RecommendedStackCard.tsx`
- `components/execution/WorkflowEffectivenessSurface.tsx`
- `components/Workflows/WorkflowRegistryPage.tsx`
- `components/Workflows/detail/WorkflowDetailPanel.tsx`
- `components/FeatureExecutionWorkbench.tsx`
- `components/Analytics/AnalyticsDashboard.tsx`
- `components/Settings.tsx`
- `services/analytics.ts`
- `services/agenticIntelligence.ts`
- `services/workflows.ts`
- `types.ts`

### Feature flags

#### Global env gates

- `CCDASH_SKILLMEAT_INTEGRATION_ENABLED`
  - hard-disables SkillMeat sync/cache/observation endpoints
- `CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED`
  - hard-disables stack recommendation generation
- `CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED`
  - hard-disables workflow effectiveness and failure-pattern endpoints

#### Project-scoped settings

Stored under `Project.skillMeat.featureFlags`:

- `stackRecommendationsEnabled`
- `workflowAnalyticsEnabled`
- `usageAttributionEnabled`

The frontend uses these flags to hide or replace surfaces with disabled-state notices. The backend uses them to skip expensive work and return consistent `503 feature_disabled` responses where appropriate.

### SkillMeat settings contract

- `Project.skillMeat.projectId`
  - stores the canonical SkillMeat `project_id`
  - this is the canonical project mapping in V2
- `Project.skillMeat.collectionId`
  - optional collection scoping for artifact and bundle lookups
- `Project.skillMeat.aaaEnabled`
  - enables credentialed requests and auth-status validation
- `Project.skillMeat.apiKey`
  - sent only for AAA-enabled / protected SkillMeat instances
- Legacy compatibility:
  - `workspaceId` is deprecated and should not be used for active mapping logic
  - existing saved configs are interpreted safely so older projects still load

The frontend now edits these values from `Settings > Integrations > SkillMeat`. The `Projects` tab remains responsible for typed project path sources and testing configuration, while app-scoped GitHub integration settings live under `Settings > Integrations > GitHub`.

### Rollout script

Command:

```bash
python backend/scripts/agentic_intelligence_rollout.py --project <project-id> --fail-on-warning
```

Supported flags:

- `--all-projects`
- `--skip-sync`
- `--skip-backfill`
- `--skip-recompute`
- `--limit`
- `--force-recompute`
- `--fail-on-warning`

Execution order:

1. sync SkillMeat definitions into the external definition cache
2. backfill session stack observations
3. recompute workflow-effectiveness rollups and failure-pattern summaries

Sync output now prints:

- contract-aligned per-type definition counts (`artifact`, `workflow`, `context_module`, `bundle`)
- V2 enrichment totals:
  - effective workflows
  - workflows with cached plan summaries
  - workflows with execution enrichment
  - context modules with preview summaries
- recoverable warning lines by section

Use `--fail-on-warning` when you want rollout to act like a stricter operator gate for CI or pre-pilot checks.

### Fallback behavior

- Definition sync is read-only against SkillMeat.
- Recommendation and analytics layers continue to use cached definitions and previously computed rollups when SkillMeat is down.
- UI surfaces should keep evidence provenance clear:
  - SkillMeat-native execution data remains separate from CCDash session telemetry
  - unresolved definitions degrade to cached metadata or local-only evidence instead of breaking the workbench

### API surface

#### Integrations

- `POST /api/integrations/skillmeat/sync`
- `GET /api/integrations/skillmeat/definitions`
- `POST /api/integrations/skillmeat/observations/backfill`
- `GET /api/integrations/skillmeat/observations`
- `GET /api/integrations/github/settings`
- `PUT /api/integrations/github/settings`
- `POST /api/integrations/github/validate`
- `POST /api/integrations/github/refresh-workspace`
- `POST /api/integrations/github/check-write`

#### Feature execution

- `GET /api/features/{feature_id}/execution-context`
  - adds:
    - `recommendedStack`
    - `stackAlternatives`
    - `stackEvidence`
    - `definitionResolutionWarnings`

#### Analytics

- `GET /api/analytics/workflow-effectiveness`
- `GET /api/analytics/workflow-registry`
- `GET /api/analytics/workflow-registry/detail`
- `GET /api/analytics/failure-patterns`
- `GET /api/analytics/usage-attribution`
- `GET /api/analytics/usage-attribution/drilldown`
- `GET /api/analytics/usage-attribution/calibration`

Workflow effectiveness rows may now carry attribution-derived metrics when usage attribution is enabled:

- `attributedTokens`
- `supportingAttributionTokens`
- `attributedCostUsdModelIO`
- `averageAttributionConfidence`
- `attributionCoverage`
- `attributionCacheShare`

#### Workflow Registry surface

`/workflows` is the identity-and-correlation companion to `/analytics?tab=workflow_intelligence`.

Use it when the implementation task is about:

- workflow-resolution quality
- observed family aliasing
- command-artifact fallback matches
- bundle/context/stage composition exposure
- SkillMeat deep-link actions

Primary files:

- `backend/services/workflow_registry.py`
- `backend/routers/analytics.py`
- `components/Workflows/WorkflowRegistryPage.tsx`
- `components/Workflows/detail/WorkflowDetailPanel.tsx`
- `services/workflows.ts`

### Verification

Targeted checks used for this rollout:

```bash
python3 -m pytest backend/tests/test_agentic_intelligence_flags.py backend/tests/test_integrations_router.py backend/tests/test_features_execution_context_router.py backend/tests/test_analytics_router.py -q
python3 -m pytest backend/tests/test_stack_recommendations.py -q
python3 -m pytest backend/tests/test_session_usage_analytics.py backend/tests/test_sessions_api_router.py backend/tests/test_workflow_effectiveness.py -q
python3 -m pytest backend/tests/test_workflow_registry.py backend/tests/test_analytics_router.py -q
npm test -- --run services/__tests__/agenticIntelligence.test.ts
npm test -- --run services/__tests__/workflows.test.ts components/Workflows/__tests__/workflowRegistryRendering.test.tsx
npm run build
```

`pnpm typecheck` is currently expected to pass for the repo baseline after the frontend shell/context split removed the prior `contexts/DataContext.tsx` typecheck drift from this area.
