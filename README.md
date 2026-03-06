
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
*   **KPI Cards**: Backend-derived KPIs from `GET /api/analytics/overview` (cost, tokens, session count, completion, tool reliability, velocity).
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
*   **Filtering**: Search features by name/slug/tag, filter by category/status (including deferred caveat), and sort by update date or total task count.
    *   In the feature modal, the **Phases** tab supports phase-status and task-status filtering, including deferred.

### 4. Project Management
*   **Dynamic Project Switching**: Easily switch between multiple local projects from the sidebar.
*   **Project Context**: Each project maintains its own configuration for session logs, plan documentation, and progress tracking.
*   **Project Creation**: Add new projects by specifying local paths and metadata, which are persisted for future sessions.

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
*   **Project Testing Configuration**: Per-project Testing settings to configure platforms (`pytest`, `jest`, `playwright`, coverage/perf/load/triage), result directories, glob patterns, runtime flags, path validation, on-demand sync, and setup-script export.

### 9. Execution Workbench (In-App Local Terminal)
*   **Route**: `/execution` with feature-scoped execution context and command recommendations.
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
*   **Backend API**: `/api/execution/*` endpoints persist runs, events, and approvals for auditable run lifecycles.

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
    *   `npm run discover:sessions` - run session signal discovery (default profile: `claude_code`)
    *   `npm run build` - build frontend assets
    *   `npm run start:backend` - production-style backend startup
    *   `npm run start:frontend` - serve built frontend (`vite preview`)

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
For sync/rebuild operation behavior, see [`docs/sync-observability-and-audit.md`](docs/sync-observability-and-audit.md).  
For codebase explorer backend and scoring details, see [`docs/codebase-explorer-developer-reference.md`](docs/codebase-explorer-developer-reference.md).
For execution run architecture and API integration details, see [`docs/execution-workbench-developer-reference.md`](docs/execution-workbench-developer-reference.md).
