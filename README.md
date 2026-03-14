
# CCDash — Agentic Project Dashboard & Analytics Platform

**CCDash** is a local-first dashboard designed to orchestrate, monitor, and analyze the work of AI Agents within a software project. It bridges the gap between traditional project management (Kanban/Docs) and AI-driven development (Session logs, Tool usage, Token metrics).

## 🚀 Core Philosophy

1.  **Agent-First**: Every task, commit, and document changes is traceable back to specific Agent Sessions.
2.  **Forensics & Debugging**: Detailed introspection into Agent "thought processes," tool usage, and costs.
3.  **Local Context**: Tightly coupled with the local filesystem, Git history, and Markdown frontmatter.

## 🔌 Session Ingestion Platforms

- **Claude Code**: native JSONL parsing plus sidecar enrichment (`todos`, `tasks`, `teams`, `session-env`, `tool-results`).
- **Codex**: JSONL payload parsing (`response_item`, `event_msg`, `turn_context`) with tool/result correlation and payload signal extraction.
- **Platform registry**: parser routing is centralized so additional platforms can be added without changing API/UI contracts.

---

## 🛠️ Technology Stack

*   **Frontend**: React 19, TypeScript, Vite
*   **Styling**: Tailwind CSS (Slate dark mode theme)
*   **Icons**: Lucide React
*   **Visualization**: Recharts (Area, Bar, Pie, Line, Composed charts)
*   **Routing**: React Router DOM (v7)
*   **AI Integration**: Google Gemini SDK (`@google/genai`)

---

## 📦 Feature Specification

### 1. Global Navigation & Layout
*   **Collapsible Sidebar**: Fluid transition sidebar with icon-only mode.
*   **Notifications**: Badge system for system alerts (e.g., cost overruns, quality drops).
*   **Theme**: Deep "Slate" dark mode optimized for long engineering sessions.

### 2. Dashboard (Overview)
*   **KPI Cards**: Backend-derived KPIs from `GET /api/analytics/overview` now distinguish observed workload, model IO, cache contribution, cost, session count, completion, tool reliability, and velocity.
*   **Usage Attribution Tab**: `/analytics?tab=attribution` ranks attributed workload by skill, agent, command, artifact, workflow, and feature with calibration and event drill-down.
*   **AI Insights**: Integrated **Google Gemini** analysis that reads current metrics/tasks and generates executive summaries on project health.
*   **Visualizations**:
    *   **Cost vs. Velocity Area Chart**: Tracks spending against task velocity over time (`GET /api/analytics/series`).
    *   **Model Usage Bar Chart**: Model usage breakdown from overview payload.

### 3. Feature Board (Aggregate Delivery View)
*   **Feature-Centric View**: Redesigned board that groups work into **Features** discovered from project documentation (PRDs and Implementation Plans).
*   **Document-First Discovery**: Automatically cross-references PRDs, Implementation Plans, and Progress files to build a cohesive view of each feature.
*   **Views**: Toggle between **Kanban Board** (grouped by feature stage: Backlog, In Progress, Review, Done) and **List View**.
    *   Features with deferred steps still land in **Done** when all tasks are terminal (`done` or `deferred`), and show a deferred caveat indicator.
*   **Drill-Down Modal**: 
    *   **Overview**: Visualize linked documents (PRDs, Plans, Reports), category badges, and related feature variants (v1, v2).
    *   **Phases tab**: Accordion view of implementation phases. Each phase expands to show a checklist of individual tasks with their real-time status.
    *   **Documents tab**: Quick access to all documentation files associated with the feature.
    *   **Session summaries**: Feature-linked session chips and modal cards now surface observed workload and cache share instead of implying `tokensIn + tokensOut` is the only total.
*   **Filtering**: Search features by name/slug/tag, filter by category/status (including deferred caveat), and sort by update date or total task count.
    *   In the feature modal, the **Phases** tab supports phase-status and task-status filtering, including deferred.

### 4. Project Management
*   **Dynamic Project Switching**: Easily switch between multiple local projects from the sidebar.
*   **Project Context**: Each project maintains typed path-source configuration for session logs, plan documentation, and progress tracking, with support for local filesystem roots, project-relative roots, and GitHub-backed repo paths where applicable.
*   **Project Creation**: Add new projects by specifying metadata and canonical path roots, which are persisted for future sessions.

### 5. Plan Catalog (Documentation)
*   **Views**:
    *   **Card Grid**: Visual overview of PRDs, RFCs, and Architecture docs.
    *   **List**: Sortable table view.
    *   **Folder/Explorer**: 3-pane IDE-style file explorer for navigating documentation hierarchies.
*   **Document Modal**:
    *   Canonical tabs: **Summary**, **Delivery**, **Relationships**, **Content**, **Timeline**, **Raw**.
    *   Typed metadata from canonical schema fields (priority/risk/complexity/track, timeline/release/milestone, readiness/test impact, ownership/audience).
    *   Relationship surfaces include typed `linked_features[]` (type/source/confidence), related docs, request IDs, commit refs, and PR refs.
    *   **Raw** tab includes normalized and raw frontmatter payloads for migration/debugging parity.
    *   Plan documents can now be edited directly in the modal; local files save in place, while eligible GitHub-backed plan docs can commit and push through the managed repo workspace flow.

### 6. Session Inspector (Agent Forensics)
The core debugging loop for AI interactions.
*   **Session Index**: Grid view of Active (Live) vs. Historical sessions with cost and health indicators.
*   **Session Header Context**:
    *   Full-width tab bar below the title row.
    *   Dedicated middle context section between Title and Session Cost showing:
        *   primary **Linked Feature** (status + confidence + quick-open)
        *   **Platform** value promoted from Forensics Session Capture.
*   **Deep Dive View (Tabbed Interface)**:
    1.  **Transcript**: 
        *   3-pane fluid layout (Log list, Detail view, Metadata sidebar).
        *   **Message/Tool/Skill Support**: distinct visual styling for different log types.
        *   **Mapped Event Cards**: command/artifact/action mapping for transcript entries (for example Agent invocation, Skill mention, Hook invocation, and test-related command events).
        *   **Inline Expansion**: Inspect tool arguments and large outputs without losing context.
    2.  **Forensics**:
        *   Full forensic payload exploration from parser-derived telemetry.
        *   **Queue Pressure**: queue operation/status/task-type distributions and `waiting_for_task` signals.
        *   **Resource Footprint**: command-derived external/internal targets (`api`, `database`, `docker`, `ssh`, `service`).
        *   **Subagent Topology**: task fan-out, linked subagent sessions, and orphan linkage tracking.
        *   **Tool Result Intensity**: `tool-results` sidecar file volume and largest file inspection.
        *   **Hook Invocation Signals**: parsed hook invocation context (`hookName`, `hookPath`, `hookEvent`, `hookCommand`) and invocation timeline in `entryContext.hookInvocations`.
        *   **Test Execution Summary**: aggregated session test-run signals (`testExecution`) including framework counts, status counts, and parsed run metrics.
        *   **Platform Telemetry**: project-level platform config telemetry (for example MCP server inventory for Claude).
        *   **Codex Payload Signals**: payload/tool distributions for Codex sessions.
    3.  **Features**:
        *   Linked feature set with confidence metadata, status/category chips, and task hierarchy correlation.
        *   Loads related main-thread sessions for each feature and supports direct navigation.
    4.  **Test Status**:
        *   Scrollable `Modified Tests During This Session` list derived from all test file actions (including reads/edits).
        *   `Tests Run During This Session` list with one row per detected run from transcript tool calls.
        *   Per-run telemetry includes framework/status, grouped targets/domains/flags, and parsed pass/fail/skipped/xfailed counts and duration when available.
    5.  **Analytics (Advanced)**:
        *   **Interactive Charts**: Click on any chart (Active Agents, Tool Usage, Model Allocation) to view detailed stats (Cost, Tokens, Count) and deep-link to filtered transcript views.
        *   **Token Timeline**: Detailed cumulative timeline from persisted backend data via `GET /api/analytics/series?metric=session_tokens&session_id=...`.
        *   **Token Semantics**: Session analytics now separate model IO, cache input, observed workload, and tool-reported fallback diagnostics.
        *   **Usage Attribution**: Session analytics now include per-session attribution summaries with exclusive vs supporting totals, confidence, and model-IO-derived cost context.
        *   **Session Block Insights**: Long sessions can be broken into configurable `1h`, `3h`, `5h`, or `8h` workload/cost blocks with burn-rate and projected end-of-block summaries.
        *   **Master Timeline**: Full-width correlation view of session lifecycle events against token consumption.
    6.  **Artifacts**:
        *   Visual cards for generated and captured artifact events, including Skills, Commands, Agents/Subagents, Hooks, Tasks, and test-run artifacts.
        *   Source-log and linked-thread correlation so artifact cards can be traced back to the originating transcript event and sub-thread.
        *   Test artifacts include parsed test-run details (command, scope, counts, timing, status) via card detail modals for cross-session traceability.
    7.  **App Impact**:
        *   Outcome-and-correlation layer derived from currently captured data:
            *   file/code footprint (`updatedFiles`, action mix, net line delta)
            *   validation/test movement (`sessionForensics.testExecution` + parsed run fallback)
            *   delivery traceability (artifact and linked-feature correlation)
            *   workflow risk signals (queue pressure, API/tool errors).
        *   Includes:
            *   summary KPI cards
            *   correlation insights
            *   pipeline coverage health panel
            *   filterable impact event stream.
        *   **Boundary vs Analytics**:
            *   `Analytics` explains *resource/behavior telemetry* (tokens, costs, allocations).
            *   `App Impact` explains *delivery outcomes and inferred conclusions*.
    8.  **Agents**:
        *   Card view of all participating agents (e.g., Architect, Coder, Planner).
        *   Click-to-filter transcript by specific agent.
        *   Sub-thread labels resolve to captured `subagent_type` when available for more stable cross-session naming.
    9.  **Files**:
        *   Aggregated table with one row per file touched by the root thread.
        *   Multi-action chips (`Read`, `Create`, `Update`, `Delete`) per file.
        *   Touch/session counts, net diff, and open actions.
    10.  **Activity**:
        *   Chronological timeline of log entries, file actions, and linked artifacts.
        *   Includes `sourceLogId`-driven deep-link highlighting from Transcript.

### 7. Codebase Explorer
*   **Route**: `/codebase` with a 3-pane explorer (tree, file list, detail).
*   **Coverage**: Full project tree under active project root with `.gitignore` + safety excludes.
*   **Correlations**: Per-file sessions, feature involvement levels, linked documents, and recent activity.
*   **Cross Navigation**:
    *   session links open `/sessions?session=...`
    *   feature links open `/board?feature=...`
    *   document links open `/plans?doc=...`

### 8. Settings
*   **Alert Rules Engine**: Persisted alert CRUD (`POST/PATCH/DELETE /api/analytics/alerts`) for threshold-based monitoring.
*   **Toggle System**: Activate/Deactivate alerts with backend persistence.
*   **Projects tab**:
    *   per-project path-source editors for project root, plan docs, sessions, and progress roots
    *   typed source selection (`project_root`, `filesystem`, `github_repo`) with effective-path previews and GitHub validation/status messaging
    *   project-scoped Testing configuration for platforms (`pytest`, `jest`, `playwright`, coverage/perf/load/triage), result directories, glob patterns, runtime flags, path validation, on-demand sync, and setup-script export
*   **Integrations tab**:
    *   dedicated `SkillMeat` and `GitHub` sub-tabs instead of mixing integration settings into `Projects`
    *   GitHub integration controls for token/repository validation, managed workspace refresh, and write-capability checks used by plan-document write-back
*   **AI Platforms Pricing Catalog**:
    *   dedicated `AI Platforms` tab for global pricing management instead of project-scoped editing
    *   platform defaults plus family defaults for `Claude Code` and `Codex`
    *   detected exact-model rows synthesized from synced sessions across configured projects
    *   best-effort live provider sync for Anthropic and OpenAI pricing pages with bundled fallback
    *   provider refresh can be triggered from the UI or automated through `POST /api/pricing/catalog/sync?platformType=...`
    *   manual exact-model overrides can be added, saved, reset, and deleted without removing required platform/family defaults
*   **SkillMeat Intelligence Controls**: Per-project SkillMeat settings are managed from `Settings > Integrations > SkillMeat` and include rollout controls for:
    *   read-only definition sync
    *   recommended stack UI visibility in `/execution`
    *   session block insights visibility in Session Inspector analytics
    *   usage attribution visibility in `/analytics` and Session Inspector
    *   workflow intelligence analytics visibility in `/analytics` and `/execution`

### 9. Execution Workbench (In-App Local Terminal)
*   **Route**: `/execution` with feature-scoped execution context and command recommendations.
*   **Recommended Stack Card**:
    *   confidence-scored workflow/stack suggestion based on historical outcomes
    *   resolved SkillMeat definition chips and cached metadata fallbacks
    *   inline insight panels for context coverage, curated bundle fit, and SkillMeat execution awareness
    *   similar-work evidence links into prior sessions/features
*   **Run Launch UX**: `Run in Workbench` actions open a pre-run review modal with:
    *   editable command text
    *   working-directory selection
    *   env profile selection (`default`, `minimal`, `project`, `ci`)
    *   policy re-check before launch
*   **Safety Pipeline**:
    *   `allow` commands run immediately.
    *   `requires_approval` commands enter `blocked` until explicit approve/deny.
    *   `deny` commands are blocked until changed and re-evaluated.
*   **Runs Tab**:
    *   run history list for the selected feature
    *   active run metadata/status
    *   streamed terminal output (`stdout`/`stderr`)
    *   actions for cancel and retry
*   **Embedded Workflow Intelligence**:
    *   feature-scoped workflow effectiveness leaderboard
    *   failure-pattern summaries
    *   jump-off to the full analytics workflow intelligence view
    *   direct handoff into the dedicated Workflow Registry at `/workflows`
*   **Backend API**: `/api/execution/*` endpoints persist runs, events, and approvals for auditable run lifecycles.

### 10. Workflow Registry
*   **Route**: `/workflows` with deep-linkable workflow detail routes at `/workflows/:workflowId`.
*   **Catalog + Detail Layout**:
    *   searchable workflow catalog with correlation-state filters
    *   responsive master-detail layout for desktop, tablet, and stacked mobile flows
    *   keyboard support for search focus and catalog navigation
*   **Workflow Identity**:
    *   observed workflow family refs and aliases
    *   explicit correlation state (`strong`, `hybrid`, `weak`, `unresolved`)
    *   separate SkillMeat workflow-definition and command-artifact resolution metadata
*   **Workflow Detail**:
    *   composition summary for artifact refs, context refs, resolved modules, bundle alignment, stages, gates, and fan-out
    *   effectiveness summary for success, efficiency, quality, risk, attribution coverage, and confidence
    *   issue cards that explain stale cache, weak resolution, missing composition, missing context coverage, and missing effectiveness evidence
    *   representative CCDash sessions plus recent SkillMeat workflow execution summaries
*   **Cross-Surface Navigation**:
    *   analytics and execution surfaces now link into the registry
    *   registry actions can open SkillMeat workflows, command artifacts, bundles, context memory, executions, and representative CCDash sessions

### 11. Agentic SDLC Intelligence
*   **Read-only SkillMeat integration**:
    *   caches artifact, workflow, context-module, and bundle definitions per project
    *   stores normalized provenance and snapshot metadata for deterministic recommendations
    *   enriches effective workflows with plan summaries, context previews, and recent workflow execution metadata
*   **Observed Stack Extraction**:
    *   backfills historical sessions into stack observations using agents, skills, commands, linked artifacts, and session forensics
    *   resolves matching components against cached SkillMeat definitions when available
*   **Workflow Intelligence Analytics**:
    *   `/analytics?tab=workflow_intelligence` ranks workflow, agent, skill, context, and stack scopes by success, efficiency, quality, and risk
    *   workflow rollups now include attributed token, cost, coverage, and cache-share signals when attribution is enabled
    *   failure-pattern clustering highlights queue waste, repeated debug loops, and weak validation paths
    *   `/workflows` now acts as the identity-and-correlation hub that complements the leaderboard-style analytics view
*   **Operator Tooling**:
    *   `python backend/scripts/agentic_intelligence_rollout.py` can sync definitions, backfill observations, and recompute workflow rollups for the active or selected project
    *   support flags: `--project`, `--all-projects`, `--skip-sync`, `--skip-backfill`, `--skip-recompute`, `--force-recompute`, `--fail-on-warning`

---

## 📊 Data Models

### Feature
The primary unit of delivery. Aggregates:
*   `linkedDocs`: References to PRDs, Implementation Plans, and Reports.
*   `phases`: Implementation phases containing granular `ProjectTask` items.
*   `relatedFeatures`: Bi-directional links to other version variants of the same feature.
*   `deferredTasks`: Count of terminal-complete tasks deferred for later follow-up.
*   Rollup metadata from linked docs: `description`, `summary`, `priority`, `riskLevel`, `complexity`, `track`, `timelineEstimate`, `targetRelease`, `milestone`, `executionReadiness`, `testImpact`.
*   Structured context blocks: `primaryDocuments`, `documentCoverage`, `qualitySignals`, and typed `linkedFeatures`.

### AgentSession
The atomic unit of work. Contains:
*   `logs`: The conversation and tool execution stream.
*   `impactHistory`: Persisted impact-event stream (rehydrated from cache DB), including parser-derived progress and execution outcome signals; also supports legacy numeric snapshots.
*   `updatedFiles`: List of file modifications.
*   `linkedArtifacts`: References to external systems (SkillMeat, MeatyCapture).
    *   Includes parser-captured runtime artifacts such as `skill`, `command`, `agent`, `task`, `hook`, and `test_run` with source-log correlation.
*   `dates` / `timeline`: Persisted date metadata and event timeline.
*   `sessionForensics`: Structured platform-aware forensic payload including:
    *   `entryContext`, `sidecars`, `analysisSignals`
    *   `queuePressure`, `resourceFootprint`, `subagentTopology`, `toolResultIntensity`
    *   `platformTelemetry` (Claude) and `codexPayloadSignals` (Codex)

### ProjectTask
Represents a specific unit of implementation.
*   `status`: Mapped from frontmatter (pending/backlog, in-progress, review, completed/done, deferred).
*   `cost`: Derived from estimated effort.

### PlanDocument
Represents Markdown documentation. Contains:
*   Typed identity/classification metadata (`docType`, `docSubtype`, `rootKind`, canonical status).
*   Canonical delivery/classification fields (`description`, `summary`, `priority`, `riskLevel`, `complexity`, `track`, `timelineEstimate`, `targetRelease`, `milestone`, `executionReadiness`, `testImpact`).
*   `frontmatter` + `metadata` blocks for normalized linking (`linkedFeatureRefs`, related docs, request/commit/PR refs, source/context files, doc-type-specific fields).

---

## 🚀 Running the Project

1.  **Install frontend dependencies**:
    ```bash
    npm install
    ```

2.  **Install backend dependencies and create `backend/.venv`**:
    ```bash
    npm run setup
    ```

3.  **Start full local development stack (backend + frontend)**:
    ```bash
    npm run dev
    ```

4.  **Useful scripts**:
    *   `npm run dev:backend` - backend only (reload mode)
    *   `npm run dev:frontend` - frontend only
    *   `npm run dev:worker` - background worker only (startup sync + scheduled jobs, no HTTP server)
    *   `npm run discover:sessions` - run session signal discovery (default profile: `claude_code`)
    *   `npm run build` - build frontend assets
    *   `npm run start:backend` - production-style backend startup
    *   `npm run start:worker` - production-style background worker startup
    *   `npm run start:frontend` - serve built frontend (`vite preview`)
    *   `python backend/scripts/agentic_intelligence_rollout.py --project <project-id>` - sync SkillMeat definitions, backfill stack observations, and recompute workflow intelligence rollups

5.  **Environment Variables**:
    *   `GEMINI_API_KEY`: Enables AI insight features.
    *   `CCDASH_BACKEND_HOST` / `CCDASH_BACKEND_PORT`: Backend bind host/port for startup scripts.
    *   `CCDASH_API_PROXY_TARGET`: Vite proxy target for `/api` requests.
    *   `CCDASH_TEST_VISUALIZER_ENABLED`: Global hard gate for `/api/tests/*` and `/tests` data.
    *   `CCDASH_INTEGRITY_SIGNALS_ENABLED`: Global hard gate for integrity signal features.
    *   `CCDASH_LIVE_TEST_UPDATES_ENABLED`: Global hard gate for live test updates.
    *   `CCDASH_SEMANTIC_MAPPING_ENABLED`: Global hard gate for semantic mapping.
    *   `CCDASH_LINKING_LOGIC_VERSION`: Link-rebuild version gate (default `1`). Bump when link inference logic changes to force one full relink.
    *   `CCDASH_STARTUP_SYNC_LIGHT_MODE`: run startup sync in lightweight mode first (default `true`).
    *   `CCDASH_STARTUP_SYNC_DELAY_SECONDS`: delay before startup sync starts (default `2`).
    *   `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS`: run deferred link rebuild after light startup sync (default `true`).
    *   `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS`: delay before deferred rebuild (default `45`).
    *   `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS`: capture analytics during deferred rebuild (default `false`).
    *   `CCDASH_SKILLMEAT_INTEGRATION_ENABLED`: global hard gate for SkillMeat sync/cache endpoints (default `true`).
    *   `CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED`: global hard gate for historical stack recommendations (default `true`).
    *   `CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED`: global hard gate for workflow intelligence endpoints (default `true`).
    *   `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED`: global hard gate for attribution analytics and session attribution payloads (default `true`).

7.  **Runtime profile notes**:
    *   `npm run dev` / `npm run start:backend` use the `local` runtime profile: HTTP + in-process sync/watch/job behavior for desktop-style convenience.
    *   `backend.main:app` is the hosted-style API entrypoint with incidental background work disabled.
    *   `npm run dev:worker` / `npm run start:worker` run `backend.worker`, which performs sync/refresh/scheduled work without serving HTTP.
    *   Frontend shell state is split across session, entity-data, runtime, and API-client layers; `contexts/DataContext.tsx` remains a compatibility facade for existing components.

6.  **Test Mapping Workflow (recommended)**:
    *   Run one initial backfill for each project (`POST /api/tests/mappings/backfill`) to bootstrap mappings across existing runs.
    *   Resolver uses cached primary mappings for unchanged tests and remaps only new/changed tests on future runs.
    *   Pass `force_recompute=true` only when mapping logic changes and you want a full remap.
    *   Domain mapping now supports hierarchical sub-domains and adaptive depth for large test groups.
    *   Mapping providers are pluggable; current built-ins are `test_metadata`, `repo_heuristics`, and low-priority `path_fallback`, with semantic import support via `POST /api/tests/mappings/import`.
    *   Backfill prunes stale unmapped leaf domains to keep domain drilldown cleaner after resolver changes.

For detailed setup, troubleshooting, and deployment startup guidance, see [`docs/setup-user-guide.md`](docs/setup-user-guide.md).  
For project-scoped Testing configuration and `/tests` ingestion flow, see [`docs/testing-user-guide.md`](docs/testing-user-guide.md).  
For end-user execution flow in `/execution`, see [`docs/execution-workbench-user-guide.md`](docs/execution-workbench-user-guide.md).  
For end-user workflow intelligence and recommended-stack usage, see [`docs/agentic-sdlc-intelligence-user-guide.md`](docs/agentic-sdlc-intelligence-user-guide.md).
For end-user attribution semantics and interpretation, see [`docs/session-usage-attribution-user-guide.md`](docs/session-usage-attribution-user-guide.md).
For implementation details and rollout commands, see [`docs/agentic-sdlc-intelligence-developer-reference.md`](docs/agentic-sdlc-intelligence-developer-reference.md).
For attribution contracts, rollout controls, and API details, see [`docs/session-usage-attribution-developer-reference.md`](docs/session-usage-attribution-developer-reference.md).
For sync/rebuild operation behavior, see [`docs/sync-observability-and-audit.md`](docs/sync-observability-and-audit.md).  
For codebase explorer backend and scoring details, see [`docs/codebase-explorer-developer-reference.md`](docs/codebase-explorer-developer-reference.md).
For execution run architecture and API integration details, see [`docs/execution-workbench-developer-reference.md`](docs/execution-workbench-developer-reference.md).
