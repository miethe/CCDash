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
*   **Visualization**: Recharts (Area, Bar, Pie, Line charts)
*   **Routing**: React Router DOM (v7)
*   **AI Integration**: Google Gemini SDK (`@google/genai`)

---

## 📦 Feature Specification

### 1. Global Navigation & Layout
*   **Collapsible Sidebar**: Fluid transition sidebar with icon-only mode.
*   **Notifications**: Badge system for system alerts (e.g., cost overruns, quality drops).
*   **Theme**: Deep "Slate" dark mode optimized for long engineering sessions.

### 2. Dashboard (Overview)
*   **KPI Cards**: High-level metrics for Total Spend, Average Session Quality, Hallucination Rate, and Shipping Velocity.
*   **AI Insights**: Integrated **Google Gemini** analysis that reads current metrics/tasks and generates executive summaries on project health.
*   **Visualizations**:
    *   **Cost vs. Quality Area Chart**: Tracks spending against code quality over time.
    *   **Model Usage Bar Chart**: Breakdown of underlying LLM usage (Claude vs. Gemini).

### 3. Project Board (Feature Management)
*   **Views**: Toggle between **Kanban Board** (Drag & Drop) and **List View** (Detailed metadata).
*   **Filtering**: Search by keyword, filter by status, sort by date/cost.
*   **Task Cards**: Display owner, cost, priority, and derived metadata (agents used, tools used).
*   **Task Detail Modal**:
    *   **Overview**: Description, quick stats, tags, and ownership.
    *   **Context Tab**: Built-in file viewer for related code/docs.
    *   **Sessions Tab**: Linked list of all Agent Sessions that worked on this specific task.
    *   **Git Tab**: Timeline of commits associated with the task/agents.

### 4. Plan Catalog (Documentation)
*   **Views**:
    *   **Card Grid**: Visual overview of PRDs, RFCs, and Architecture docs.
    *   **List**: Sortable table view.
    *   **Folder/Explorer**: 3-pane IDE-style file explorer for navigating documentation hierarchies.
*   **Document Modal**:
    *   **Markdown Preview**: Renders document content.
    *   **Metadata**: Parses frontmatter (Authors, Version, Status).
    *   **Version Control**: Lists linked Commits and PRs.
    *   **Bi-directional Linking**: Tabs showing "Linked Files" and "Linked Entities" (Tasks/Sessions).

### 5. Session Inspector (Agent Forensics)
The core debugging loop for AI interactions.
*   **Session Index**: Grid view of Active (Live) vs. Historical sessions with cost and health indicators.
*   **Deep Dive View (Tabbed Interface)**:
    1.  **Transcript**: 
        *   3-pane fluid layout (Log list, Detail view, Metadata sidebar).
        *   **Message/Tool/Skill Support**: distinct visual styling for different log types.
        *   **Inline Expansion**: Inspect tool arguments and large outputs without losing context.
    2.  **Files**: 
        *   Table of all files touched in the session.
        *   Diff stats (Additions/Deletions).
        *   "Open in IDE" simulation or "View Doc" if the file exists in the Plan Catalog.
    3.  **Artifacts**: 
        *   Visual cards for generated Memories, Request Logs, and Knowledge Base entries.
    4.  **App Impact**: 
        *   **Codebase Impact Chart**: Line chart tracking LOC added/removed and file touch-counts over the session duration.
        *   **Test Stability Chart**: Area chart visualizing Test Pass vs. Fail counts over time.
    5.  **Analytics**: 
        *   Tool Usage Pie Chart.
        *   Token Consumption Bar Chart (Input vs. Output).
        *   Cost breakdown per step.
    6.  **Agents**: 
        *   Card view of all participating agents (e.g., Architect, Coder, Planner).
        *   Click-to-filter transcript by specific agent.

### 6. Settings
*   **Alert Rules Engine**: Configure thresholds for active monitoring (e.g., "Alert if Session Cost > $5.00").
*   **Toggle System**: Activate/Deactivate specific rules.

---

## 📊 Data Models

### AgentSession
The atomic unit of work. Contains:
*   `logs`: The conversation and tool execution stream.
*   `impactHistory`: Time-series data of code/test changes.
*   `updatedFiles`: List of file modifications.
*   `linkedArtifacts`: References to external systems (SkillMeat, MeatyCapture).

### ProjectTask
Represents a feature or bug. Links to:
*   `relatedFiles`: Context files.
*   `lastAgent`: The last model to touch the task.

### PlanDocument
Represents Markdown documentation. Contains:
*   `frontmatter`: Metadata for linking back to Tasks and Sessions.

---

## 🚀 Running the Project

1.  **Install Dependencies**:
    ```bash
    npm install
    ```

2.  **Start Development Server**:
    ```bash
    npm run dev
    ```

3.  **Environment Variables**:
    *   `API_KEY`: Required for Google Gemini "AI Insight" features.
