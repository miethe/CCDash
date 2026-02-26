
# CCDash — Agentic Project Dashboard & Analytics Platform

**CCDash** is a local-first dashboard designed to orchestrate, monitor, and analyze the work of AI Agents within a software project. It bridges the gap between traditional project management (Kanban/Docs) and AI-driven development (Session logs, Tool usage, Token metrics).

## 🚀 Core Philosophy

1.  **Agent-First**: Every task, commit, and document changes is traceable back to specific Agent Sessions.
2.  **Forensics & Debugging**: Detailed introspection into Agent "thought processes," tool usage, and costs.
3.  **Local Context**: Tightly coupled with the local filesystem, Git history, and Markdown frontmatter.

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
    *   **Markdown Preview**: Renders document content.
    *   **Metadata**: Parses frontmatter (Authors, Version, Status).
    *   **Version Control**: Lists linked Commits and PRs.
    *   **Bi-directional Linking**: Tabs showing "Linked Files" and "Linked Entities" (Tasks/Sessions).

### 6. Session Inspector (Agent Forensics)
The core debugging loop for AI interactions.
*   **Session Index**: Grid view of Active (Live) vs. Historical sessions with cost and health indicators.
*   **Deep Dive View (Tabbed Interface)**:
    1.  **Transcript**: 
        *   3-pane fluid layout (Log list, Detail view, Metadata sidebar).
        *   **Message/Tool/Skill Support**: distinct visual styling for different log types.
        *   **Inline Expansion**: Inspect tool arguments and large outputs without losing context.
    2.  **Activity**:
        *   Chronological timeline of log entries, file actions, and linked artifacts.
        *   Includes `sourceLogId`-driven deep-link highlighting from Transcript.
    3.  **Files**:
        *   Aggregated table with one row per file touched by the root thread.
        *   Multi-action chips (`Read`, `Create`, `Update`, `Delete`) per file.
        *   Touch/session counts, net diff, and open actions.
    4.  **Artifacts**:
        *   Visual cards for generated Memories, Request Logs, and Knowledge Base entries.
    5.  **App Impact**:
        *   **Codebase Impact Chart**: Line chart tracking LOC added/removed and file touch-counts over the session duration.
        *   **Test Stability Chart**: Area chart visualizing Test Pass vs. Fail counts over time.
    6.  **Analytics (Advanced)**:
        *   **Interactive Charts**: Click on any chart (Active Agents, Tool Usage, Model Allocation) to view detailed stats (Cost, Tokens, Count) and deep-link to filtered transcript views.
        *   **Token Timeline**: Detailed cumulative timeline from persisted backend data via `GET /api/analytics/series?metric=session_tokens&session_id=...`.
        *   **Master Timeline**: Full-width correlation view of session lifecycle events against token consumption.
    7.  **Agents**:
        *   Card view of all participating agents (e.g., Architect, Coder, Planner).
        *   Click-to-filter transcript by specific agent.

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

---

## 📊 Data Models

### Feature
The primary unit of delivery. Aggregates:
*   `linkedDocs`: References to PRDs, Implementation Plans, and Reports.
*   `phases`: Implementation phases containing granular `ProjectTask` items.
*   `relatedFeatures`: Bi-directional links to other version variants of the same feature.
*   `deferredTasks`: Count of terminal-complete tasks deferred for later follow-up.

### AgentSession
The atomic unit of work. Contains:
*   `logs`: The conversation and tool execution stream.
*   `impactHistory`: Persisted time-series impact data (rehydrated from cache DB).
*   `updatedFiles`: List of file modifications.
*   `linkedArtifacts`: References to external systems (SkillMeat, MeatyCapture).
*   `dates` / `timeline`: Persisted date metadata and event timeline.

### ProjectTask
Represents a specific unit of implementation.
*   `status`: Mapped from frontmatter (pending/backlog, in-progress, review, completed/done, deferred).
*   `cost`: Derived from estimated effort.

### PlanDocument
Represents Markdown documentation. Contains:
*   `frontmatter`: Metadata for linking back to Tasks and Sessions.

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
    *   `npm run build` - build frontend assets
    *   `npm run start:backend` - production-style backend startup
    *   `npm run start:frontend` - serve built frontend (`vite preview`)

5.  **Environment Variables**:
    *   `GEMINI_API_KEY`: Enables AI insight features.
    *   `CCDASH_BACKEND_HOST` / `CCDASH_BACKEND_PORT`: Backend bind host/port for startup scripts.
    *   `CCDASH_API_PROXY_TARGET`: Vite proxy target for `/api` requests.
    *   `CCDASH_LINKING_LOGIC_VERSION`: Link-rebuild version gate (default `1`). Bump when link inference logic changes to force one full relink.
    *   `CCDASH_STARTUP_SYNC_LIGHT_MODE`: run startup sync in lightweight mode first (default `true`).
    *   `CCDASH_STARTUP_SYNC_DELAY_SECONDS`: delay before startup sync starts (default `2`).
    *   `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS`: run deferred link rebuild after light startup sync (default `true`).
    *   `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS`: delay before deferred rebuild (default `45`).
    *   `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS`: capture analytics during deferred rebuild (default `false`).

For detailed setup, troubleshooting, and deployment startup guidance, see [`docs/setup-user-guide.md`](docs/setup-user-guide.md).  
For sync/rebuild operation behavior, see [`docs/sync-observability-and-audit.md`](docs/sync-observability-and-audit.md).  
For codebase explorer backend and scoring details, see [`docs/codebase-explorer-developer-reference.md`](docs/codebase-explorer-developer-reference.md).
