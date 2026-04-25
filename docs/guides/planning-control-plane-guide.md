# Planning Control Plane Guide

Last updated: 2026-04-21

CCDash now provides a unified planning control plane that turns frontmatter-driven planning artifacts into a live, explainable operational GUI. This guide covers enabling planning surfaces, understanding effective status semantics, and launching plan-driven agent work. The v2 reskin adds a dedicated triage inbox, live agent roster, richer planning graph lanes, and a feature drawer with SPIKE and OQ workflows.

## Overview

The Planning Control Plane (Phases 1–6 of PCP-v1, plus the v2 reskin surfaces) unifies:

1. **Planning Graph**: Linked design specs, PRDs, implementation plans, and progress files as a navigable graph.
2. **Effective Status & Mismatch Detection**: Raw artifact status combined with progress and execution evidence to derive effective state and surfaced mismatches.
3. **Phase Operations**: Batch-ready tasks, dependencies, and execution state for each phase within a feature.
4. **Launch Preparation**: Plan-driven multi-agent launch with worktree and provider/model awareness.

For background, see the full PRD at `docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md` and the architecture design spec at `docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md`.

## Frontend Surfaces

The planning control plane provides seven primary UI surfaces:

### PlanningHomePage
The planning entry point, showing:
- Hero stats and corpus summary
- Metrics strip for active planning health
- Artifact composition chips for the planning corpus
- Status mismatch warnings
- Recent planning-related execution activity

### PlanningGraphPanel
Graph visualization of linked planning artifacts:
- Nodes represent design specs, PRDs, implementation plans, and progress files
- Edges show parent-child and dependency relationships
- Lane-based totals cells surface effort, token, and model-identity context
- Click to drill into individual nodes
- Supports feature-scoped graph views for focused planning

### PlanningTriageInbox
Fast-action queue for planning cleanup:
- Blocked features and phases
- Status mismatches and stale artifacts
- Ready-to-promote items
- Filter tabs for quick prioritization

### LiveAgentRoster
Live execution roster for planning work:
- Running and idle agents
- State dots and model-aware context
- Current task summary for each agent
- Lightweight live/idle visibility for launch prep

### PlanningNodeDetail
Detailed view of a single planning artifact:
- Full text or frontmatter content
- Raw status and effective status side-by-side
- Linked child and parent nodes
- Related sessions, features, and execution runs
- Mismatch provenance with evidence
- Lineage strip, SPIKE tiles, inline OQ resolution, dependency DAG, and exec buttons for the feature drawer

### ExecutionTasksPanel
Operational detail for phase work:
- Task batch readiness and dependency state
- Estimated scope and effort
- Blocked or critical-path markers
- Model-aware execution context for launch preparation

### PlanningLaunchSheet
Plan-driven launch dialog for multi-agent work:
- Phase and batch selection
- Provider and model picker (from `default_provider_catalog`)
- Worktree context setup and branch configuration
- Execution policy validation
- Launch confirmation and tracking

### PlanningAgentSessionBoard
Kanban-style board for active and recent agent sessions:
- Card-based layout with sessions grouped by state, feature, phase, agent, or model
- Session cards display agent name, model, session state, correlation confidence, token usage, and activity markers
- Drill-down to session details via card click

### PlanningAgentSessionDetailPanel
Selected-card sidebar with comprehensive session context:
- Lineage tree showing feature and phase relationships
- Feature correlation with evidence scores
- Evidence list of linked documents, tasks, and sessions
- Token context bar with input/output/cache breakdown
- Activity timeline with key milestones
- Quick actions for drill-down and launch prep

### PlanningNextRunPreview
Copy/preview-only panel for generating CLI commands and prompt skeletons:
- Integrates `PlanningPromptContextTray` for managing session/artifact/phase context references
- Generates template CLI commands with feature/phase context
- Supports copying prompt skeletons to clipboard
- Non-interactive preview mode; execution goes through `PlanningLaunchSheet`

## Backend APIs

All planning and launch endpoints follow the app-request pattern: resolve the request context, check feature flags, delegate to the transport-neutral service, and return structured DTOs.

### Planning Endpoints

**`GET /api/agent/planning/summary`** — Project-level planning health counts and per-feature summaries. Returns feature status, phase counts, mismatch indicators, and stale detection signals.

**`GET /api/agent/planning/graph`** — Aggregated planning graph nodes and edges for the project or scoped to a single feature. Supports optional depth-limited traversal in future versions.

**`GET /api/agent/planning/features/{feature_id}`** — One feature's planning subgraph, status provenance, per-phase context, and evidence for raw vs. effective status divergence.

**`GET /api/agent/planning/features/{feature_id}/phases/{phase_number}`** — Operational detail for a single phase: batch readiness, task state, dependency evidence, and launch readiness.

**`GET /api/agent/planning/session-board`** — Aggregated agent session board across the project. Supports grouping by state, feature, phase, agent, or model. Returns session cards with correlation confidence, token metrics, and activity markers. Gated by `CCDASH_PLANNING_CONTROL_PLANE_ENABLED`.

**`GET /api/agent/planning/next-run-preview/{feature_id}`** — Preview panel for the next run of a feature. Generates CLI command templates and prompt skeletons with session/artifact/phase context. Copy-only; execution through launch sheet. Gated by `CCDASH_NEXT_RUN_PREVIEW_ENABLED` (default true).

### Launch Endpoints

**`GET /api/execution/launch/capabilities`** — Exposes enabled status, provider catalog, and planning awareness. Gated by `CCDASH_LAUNCH_PREP_ENABLED` when describing capability details.

**`POST /api/execution/launch/prepare`** — Prepare a multi-agent launch for a phase or batch. Validates worktree setup, provider/model selection, and execution policy. Returns preparation metadata.

**`POST /api/execution/launch/start`** — Confirm and start the prepared launch. Creates execution runs for each task in the batch and returns run IDs.

## Feature Flags

### `CCDASH_PLANNING_CONTROL_PLANE_ENABLED`

**Default**: `true`

Controls whether planning endpoints, home surface, and graph visualization are available. When `false`:

- `/api/agent/planning/*` endpoints return HTTP 503 with error code `planning_disabled`
- Frontend renders a disabled planning shell (planning home shows a notice)
- Graph, drill-down, and phase operations views are unavailable

Set to `false` to disable the feature entirely without data loss.

### `CCDASH_LAUNCH_PREP_ENABLED`

**Default**: `false`

Controls whether launch preparation and multi-agent launch surfaces are available. When `false`:

- `/api/execution/launch/prepare` and `/api/execution/launch/start` endpoints return HTTP 503 with error code `launch_disabled`
- Launch sheet is unavailable in the UI
- Worktree and provider selection flows are hidden

Enable this only after observing stable planning surface behavior in production.

### Recommended Staged Rollout

1. **Day 1**: Enable `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true` (it defaults to true). Observe planning home, graph navigation, and status accuracy for 24–48 hours.
2. **Day 2**: Validate effective status derivation and mismatch detection across your project's plan. Watch for stale detection false positives.
3. **Week 1**: Once confident, enable `CCDASH_LAUNCH_PREP_ENABLED=true`. Test launch preparation on non-critical phases first.
4. **Ongoing**: Monitor telemetry spans and error logs for planning-specific failures.

## Telemetry & Observability

The planning control plane emits OpenTelemetry spans whenever a planning or launch operation completes (when `CCDASH_OTEL_ENABLED=true`). Spans are no-op if OTEL is disabled.

### Planning Spans

- `planning.summary` — attributes: `project_id`
- `planning.graph` — attributes: `project_id`, `feature_id`, `depth`
- `planning.feature_context` — attributes: `feature_id`
- `planning.phase_operations` — attributes: `feature_id`, `phase_number`

### Launch Spans

- `launch.capabilities` — attributes: none
- `launch.prepare` — attributes: `project_id`, `feature_id`, `phase_number`, `batch_id`
- `launch.start` — attributes: `project_id`, `feature_id`, `phase_number`, `batch_id`, `provider`

Enable a trace exporter in `backend/config.py` (e.g., Jaeger, Datadog) to stream these spans for performance and error diagnostics.

## Effective Status & Mismatch Semantics

The planning control plane derives effective status by combining multiple signals:

### Raw Status
The status declared in a planning artifact's frontmatter (`status: draft`, `status: active`, etc.). Always preserved as-is.

### Effective Status
Computed from:
1. Raw artifact status
2. Progress file frontmatter for that feature/phase
3. Execution runs and linked sessions for the feature
4. Task completion markers and feature-family state

Effective status may advance (e.g., from `draft` to `complete` if all tasks are done) or regress (e.g., from `complete` to `in-progress` if a new blocker appears).

### Mismatch
Occurs when raw status diverges from effective status due to:
- Stale frontmatter (progress file updated but artifact status not)
- Completion inference (feature marked complete but dependencies still active)
- Blocker evidence (phase declared active but task evidence shows blocked)
- Rework signals (feature marked complete but new sessions indicate iteration)

Every mismatch is surfaced with provenance: the exact evidence (session ID, task ID, timestamp) that triggered the divergence.

### Stale Detection
A phase or feature is marked stale if:
- Raw status has not been updated in `N` days (configurable; default 14 days)
- AND no new sessions or execution runs have been created for that feature in the last `M` days (configurable; default 7 days)

Reference `backend/application/services/agent_queries/planning.py` for the full effective status derivation logic.

## Limitations & Caveats

1. **Frontmatter Fidelity**: Effective status depends on well-formed YAML frontmatter in all planning artifacts. Malformed or missing fields may cause status computation errors; the service logs these as warnings and falls back to raw status.

2. **Stale Detection Precision**: Stale timestamps are relative to the local filesystem mtime for planning artifacts. Clock skew in CI/CD or batch imports can affect stale detection accuracy.

3. **Worktree Context Model**: Launch preparation assumes a valid worktree context (branch name, base commit, working directory). Incomplete or missing context will block launch confirmation.

4. **Provider & Model Catalog**: Available providers and models are gated by `backend/services/launch_providers.py:default_provider_catalog()`. Adding new providers requires updating the catalog.

5. **No Autonomous Execution**: The planning control plane surfaces launch readiness but does not auto-execute; all launches require explicit user confirmation via the launch sheet or API.

## Rollback

To safely disable the planning control plane:

1. Set `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=false`
2. Optionally set `CCDASH_LAUNCH_PREP_ENABLED=false`
3. Restart the API runtime

No data is deleted. The frontend degrades gracefully: planning home shows a disabled notice, graph views are hidden, and all other CCDash surfaces remain functional. Re-enable the flags to restore access.

## Further Reading

- **PRD** (full requirements and non-goals): `docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md`
- **Implementation Plan** (phase structure, backend design): `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md`
- **Architecture Spec** (graph semantics, effective status model): `docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md`
- **Telemetry Exporter Guide** (how to stream planning spans to OTEL): `docs/guides/telemetry-exporter-guide.md`
- **Planning Reskin v2 specs** (deferred-item follow-on design work): `docs/project_plans/design-specs/`
