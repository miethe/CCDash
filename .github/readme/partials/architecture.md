---

## Architecture

CCDash is a full-stack local-first application with a split frontend/backend design.

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite (port 3000) |
| Styling | Tailwind CSS (Slate dark mode) |
| Charts | Recharts (Area, Bar, Pie, Line, Composed) |
| Routing | React Router DOM v7 (HashRouter) |
| Backend | Python FastAPI (port 8000) |
| Database | Async SQLite (default) or PostgreSQL |
| AI | Google Gemini SDK (`@google/genai`) |

### Data Flow

```
Session JSONL files + Markdown docs
          ↓
    backend/parsers/        ← Parse filesystem artifacts
          ↓
  db/sync_engine.py         ← Sync parsed data into cache DB
          ↓
  db/repositories/          ← Data access layer
          ↓
    routers/ (REST API)     ← Expose via /api/* endpoints
          ↓
  services/apiClient.ts     ← Frontend typed API client
          ↓
    React contexts + UI     ← Shell providers feed components
```

### Key Directories

```
.                           ← Frontend root (App.tsx, types.ts, constants.ts)
├── components/             ← Page-level UI components
├── contexts/               ← Shell state providers (session, entity, runtime)
├── services/               ← Domain API helpers and typed client
└── backend/
    ├── parsers/            ← Session JSONL + document + progress parsers
    ├── routers/            ← REST API route handlers
    ├── services/           ← Business logic (codebase explorer, execution)
    ├── db/                 ← Connection, migrations, sync engine, repositories
    ├── runtime/            ← Runtime profiles + FastAPI app bootstrap
    └── observability/      ← OpenTelemetry + Prometheus instrumentation
```

### Multi-Project Support

Projects are defined in `projects.json`. Each project has typed path-source configuration for session logs, plan documentation, and progress tracking — supporting local filesystem roots, project-relative roots, and GitHub-backed repo paths.

See [`CLAUDE.md`](CLAUDE.md) for full architecture conventions and development guidelines.
