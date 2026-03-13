# CCDash — Agentic Project Dashboard & Analytics Platform

**CCDash** is a local-first dashboard designed to orchestrate, monitor, and analyze the work of AI Agents within a software project. It bridges the gap between traditional project management (Kanban/Docs) and AI-driven development (Session logs, Tool usage, Token metrics).

### Core Philosophy

1. **Agent-First**: Every task, commit, and document change is traceable back to specific Agent Sessions.
2. **Forensics & Debugging**: Detailed introspection into Agent "thought processes," tool usage, and costs.
3. **Local Context**: Tightly coupled with the local filesystem, Git history, and Markdown frontmatter.

### Session Ingestion Platforms

- **Claude Code**: Native JSONL parsing plus sidecar enrichment (todos, tasks, teams, session-env, tool-results).
- **Codex**: JSONL payload parsing (response_item, event_msg, turn_context) with tool/result correlation and payload signal extraction.
- **Platform registry**: Centralized parser routing so additional platforms can be added without changing API/UI contracts.

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite |
| Styling | Tailwind CSS (Slate dark mode) |
| Icons | Lucide React |
| Charts | Recharts |
| Routing | React Router DOM v7 |
| Backend | Python FastAPI, async SQLite / PostgreSQL |
| AI | Google Gemini SDK |
