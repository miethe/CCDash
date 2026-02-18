---
title: "Implementation Plan: DB Caching Layer"
description: "SQLite-backed cache with incremental sync, file watching, universal entity linking, pagination, and analytics time-series"
audience: [ai-agents, developers, engineering-leads]
tags: [implementation, planning, database, caching, performance, architecture]
created: 2025-02-15
updated: 2025-02-15
category: "implementation-plan"
complexity: "High"
track: "Standard"
status: "draft"
---

# Implementation Plan: DB Caching Layer

**Project:** CCDash — Agentic Analytics Dashboard
**Complexity:** High (H) | **Track:** Standard
**Timeline:** ~3–4 weeks across 5 incremental phases

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Architectural Design](#architectural-design)
4. [Schema Design](#schema-design)
5. [Sync Engine](#sync-engine)
6. [API Changes](#api-changes)
7. [Frontend Changes](#frontend-changes)
8. [Phase Breakdown](#phase-breakdown)
9. [File Structure](#file-structure)
10. [Verification Plan](#verification-plan)

---

## Executive Summary

Every API request in CCDash currently re-parses files from disk. A real project with **459 JSONL session files (2.8 GB)** causes 60+ second hangs that cascade into frontend failures. This plan introduces a **SQLite-backed caching layer** where:

- **Filesystem remains the source of truth** — DB is a read cache
- **Incremental sync** only re-parses changed files (mtime-based)
- **File watcher** detects real-time changes to source directories
- **Write-through** for app-initiated changes (status updates → filesystem → cache)
- **Universal entity linking** enables any entity to reference any other entity
- **Pagination** for large datasets (sessions)
- **Analytics time-series** with multi-entity associations and export support
- **Repository abstraction** enables optional DB backend swaps (PostgreSQL, BYO-DB)

**Key Deliverables:**
- `backend/db/` package with connection, repositories, sync engine, file watcher
- All router endpoints reading from DB instead of re-parsing disk
- Paginated API responses
- Persistent alert configs, app-specific metadata, and entity links
- Analytics snapshots with trend queries and Prometheus/Grafana export
- Zero-config default (SQLite, single file, fully portable)

---

## Problem Statement

| Issue | Current Behavior | With Cache |
|---|---|---|
| Load time (459 sessions) | 60+ seconds → timeout | < 50ms (DB query) |
| Polling (30s interval) | Re-parses all files every cycle | Lightweight DB reads |
| Session cap | Limited to 50 most recent | All sessions ingested incrementally |
| Cross-entity links | Rebuilt from scratch each load | Persisted, queryable, manually editable |
| Analytics | Point-in-time only, re-computed | Historical snapshots, trend queries |
| App metadata | Lost on restart (ratings, notes) | Persisted in DB |
| Alert configs | Hardcoded in API | Stored in DB, user-editable |

---

## Architectural Design

### Data Flow

```mermaid
graph LR
  FS["Filesystem<br/>(Source of Truth)"] -->|"FileWatcher<br/>detects changes"| Sync["SyncEngine"]
  Sync -->|"parse → upsert"| DB["Cache DB<br/>(SQLite default)"]
  DB -->|"fast queries"| API["FastAPI<br/>Endpoints"]
  API -->|"write-through"| FS
  API -->|"invalidate"| Sync
  FE["Frontend"] -->|"REST + pagination"| API
```

**Core principle**: Filesystem remains source of truth. DB is a **read cache** that additionally stores app-specific metadata, entity links, and analytics snapshots that don't belong in files.

### Database Selection

| Criterion | SQLite (default) | PostgreSQL (optional) |
|---|---|---|
| Zero config | ✅ Single file | ❌ Server required |
| Portable | ✅ Copy one file | ❌ |
| Full SQL + JSON | ✅ `json_extract` | ✅ `jsonb` |
| Full-text search | ✅ FTS5 | ✅ tsvector |
| Concurrent writes | ⚠️ WAL mode sufficient | ✅ MVCC |
| Python async | `aiosqlite` | `asyncpg` |

**Default: SQLite in WAL mode** — zero-config, portable, sufficient for single-user dev dashboards.

### Repository Pattern (DB Abstraction)

All DB access goes through abstract `Protocol` interfaces so backends can be swapped without touching business logic:

```python
# backend/db/repositories/base.py
class SessionRepository(Protocol):
    async def upsert(self, session: AgentSession, project_id: str) -> None: ...
    async def get_by_id(self, session_id: str) -> AgentSession | None: ...
    async def list_paginated(self, offset: int, limit: int, **filters) -> list[AgentSession]: ...
    async def count(self, **filters) -> int: ...
    async def get_linked(self, entity_type: str, entity_id: str) -> list[AgentSession]: ...

# Same pattern for: DocumentRepository, TaskRepository, FeatureRepository,
#                    EntityLinkRepository, AnalyticsRepository, TagRepository
```

Concrete implementations: `SqliteSessionRepository`, optionally `PostgresSessionRepository`.
Backend selected via `CCDASH_DB_BACKEND` env var (default: `sqlite`).

---

## Schema Design

### 1. Sync State (Incremental Change Detection)

```sql
CREATE TABLE sync_state (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    file_mtime   REAL NOT NULL,
    entity_type  TEXT NOT NULL,        -- 'session' | 'document' | 'task' | 'feature'
    project_id   TEXT NOT NULL,
    last_synced  TEXT NOT NULL,
    parse_ms     INTEGER DEFAULT 0
);
```

### 2. Universal Entity Cross-Linking

A single junction table enables **any entity to link to any other**. Designed for efficient 1-to-many queries and **tree-view traversal** (parent/child/sibling chains):

```sql
CREATE TABLE entity_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type   TEXT NOT NULL,           -- 'session' | 'feature' | 'document' | 'task' | 'project'
    source_id     TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    link_type     TEXT DEFAULT 'related',  -- 'related' | 'parent' | 'child' | 'blocks' | 'implements' | 'references'
    origin        TEXT DEFAULT 'auto',     -- 'auto' (parser-discovered) | 'manual' (user-created)
    confidence    REAL DEFAULT 1.0,        -- for auto-discovered: parser confidence
    depth         INTEGER DEFAULT 0,       -- tree depth from root (0 = root, 1 = direct child, etc.)
    sort_order    INTEGER DEFAULT 0,       -- ordering among siblings
    metadata_json TEXT,                    -- optional extra context
    created_at    TEXT NOT NULL,
    UNIQUE(source_type, source_id, target_type, target_id, link_type)
);

-- Efficient lookups in BOTH directions (source→targets, target→sources)
CREATE INDEX idx_links_source ON entity_links(source_type, source_id);
CREATE INDEX idx_links_target ON entity_links(target_type, target_id);
-- Fast tree traversal: "get all children of entity X"
CREATE INDEX idx_links_tree   ON entity_links(source_type, source_id, link_type, depth);
-- Find all manual links (for UI editing)
CREATE INDEX idx_links_origin ON entity_links(origin) WHERE origin = 'manual';
```

**Tree-view queries:**

```sql
-- Get full tree for feature F-123 (parent, children, siblings)
-- 1. Children (direct + nested via depth)
SELECT * FROM entity_links
  WHERE source_type = 'feature' AND source_id = 'F-123'
    AND link_type = 'child'
  ORDER BY depth, sort_order;

-- 2. Parent chain
SELECT * FROM entity_links
  WHERE target_type = 'feature' AND target_id = 'F-123'
    AND link_type = 'child';  -- reverse: "who has F-123 as child?"

-- 3. Siblings (same parent)
SELECT sibling.* FROM entity_links AS parent
  JOIN entity_links AS sibling
    ON sibling.source_type = parent.source_type
    AND sibling.source_id = parent.source_id
    AND sibling.link_type = 'child'
  WHERE parent.target_type = 'feature' AND parent.target_id = 'F-123'
    AND parent.link_type = 'child'
    AND sibling.target_id != 'F-123';

-- 4. All linked entities OF ANY TYPE for entity X (1-to-many fan-out)
SELECT * FROM entity_links
  WHERE (source_type = 'feature' AND source_id = 'F-123')
     OR (target_type = 'feature' AND target_id = 'F-123');
```

**External links** (URLs, PRs, issues) use a separate table to avoid polluting entity IDs:

```sql
CREATE TABLE external_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    url           TEXT NOT NULL,
    link_label    TEXT DEFAULT '',         -- 'GitHub PR #42', 'Jira PROJ-123'
    link_category TEXT DEFAULT 'other',    -- 'vcs' | 'issue_tracker' | 'docs' | 'other'
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_ext_links ON external_links(entity_type, entity_id);
```

### 3. Tags System

Shared tagging across all entity types with optional UI colors:

```sql
CREATE TABLE tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT ''
);

CREATE TABLE entity_tags (
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    PRIMARY KEY (entity_type, entity_id, tag_id)
);
CREATE INDEX idx_entity_tags_tag ON entity_tags(tag_id);
```

### 4. Sessions (Core + Normalized Detail Tables)

```sql
CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    task_id          TEXT DEFAULT '',
    status           TEXT DEFAULT 'completed',
    model            TEXT DEFAULT '',
    duration_seconds INTEGER DEFAULT 0,
    tokens_in        INTEGER DEFAULT 0,
    tokens_out       INTEGER DEFAULT 0,
    total_cost       REAL DEFAULT 0.0,
    quality_rating   INTEGER DEFAULT 0,
    friction_rating  INTEGER DEFAULT 0,
    git_commit_hash  TEXT,
    git_author       TEXT,
    git_branch       TEXT,
    -- Classification
    session_type     TEXT DEFAULT '',       -- 'coding' | 'review' | 'planning' | 'debugging'
    -- Hierarchy
    parent_session_id TEXT,
    -- Timestamps
    started_at       TEXT DEFAULT '',
    ended_at         TEXT DEFAULT '',
    created_at       TEXT NOT NULL,         -- ingested into DB
    updated_at       TEXT NOT NULL,
    -- Source
    source_file      TEXT NOT NULL
);
CREATE INDEX idx_sessions_project ON sessions(project_id, started_at DESC);

-- Normalized log entries (queryable: "find all tool calls across sessions")
CREATE TABLE session_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    log_index      INTEGER NOT NULL,
    timestamp      TEXT NOT NULL,
    speaker        TEXT NOT NULL,           -- 'user' | 'agent'
    type           TEXT NOT NULL,           -- 'message' | 'tool' | 'subagent' | 'skill'
    content        TEXT DEFAULT '',
    agent_name     TEXT,
    tool_name      TEXT,
    tool_args      TEXT,
    tool_output    TEXT,
    tool_status    TEXT DEFAULT 'success'
);
CREATE INDEX idx_logs_session ON session_logs(session_id, log_index);
CREATE INDEX idx_logs_tool    ON session_logs(tool_name) WHERE tool_name IS NOT NULL;

-- Tool usage summary per session
CREATE TABLE session_tool_usage (
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name     TEXT NOT NULL,
    call_count    INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    total_ms      INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, tool_name)
);

-- File changes per session
CREATE TABLE session_file_updates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    file_path    TEXT NOT NULL,
    additions    INTEGER DEFAULT 0,
    deletions    INTEGER DEFAULT 0,
    agent_name   TEXT DEFAULT ''
);
CREATE INDEX idx_file_updates_session ON session_file_updates(session_id);
CREATE INDEX idx_file_updates_path   ON session_file_updates(file_path);

-- Session artifacts (generated docs/code)
CREATE TABLE session_artifacts (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    type         TEXT DEFAULT 'document',
    description  TEXT DEFAULT '',
    source       TEXT DEFAULT ''
);
```

### 5. Documents

```sql
CREATE TABLE documents (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    title          TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    status         TEXT DEFAULT 'active',
    author         TEXT DEFAULT '',
    content        TEXT,
    -- Classification
    doc_type       TEXT DEFAULT '',         -- 'prd' | 'implementation_plan' | 'report' | 'spec' | 'phase_plan'
    category       TEXT DEFAULT '',
    -- Hierarchy
    parent_doc_id  TEXT,
    -- Timestamps
    created_at     TEXT DEFAULT '',
    updated_at     TEXT DEFAULT '',
    last_modified  TEXT DEFAULT '',
    -- Raw
    frontmatter_json TEXT NOT NULL,
    source_file    TEXT NOT NULL
);
CREATE INDEX idx_docs_project ON documents(project_id);
CREATE INDEX idx_docs_type    ON documents(doc_type);
```

### 6. Tasks

```sql
CREATE TABLE tasks (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT DEFAULT '',
    status         TEXT DEFAULT 'backlog',
    priority       TEXT DEFAULT 'medium',
    owner          TEXT DEFAULT '',
    last_agent     TEXT DEFAULT '',
    cost           REAL DEFAULT 0.0,
    -- Classification
    task_type      TEXT DEFAULT '',         -- 'implementation' | 'review' | 'testing' | 'docs'
    project_type   TEXT DEFAULT '',
    project_level  TEXT DEFAULT '',
    -- Hierarchy
    parent_task_id TEXT,
    feature_id     TEXT,                    -- direct FK to features
    phase_id       TEXT,                    -- which phase within feature
    -- Direct linking (from frontmatter)
    session_id     TEXT DEFAULT '',
    commit_hash    TEXT DEFAULT '',
    -- Timestamps
    created_at     TEXT DEFAULT '',
    updated_at     TEXT DEFAULT '',
    completed_at   TEXT DEFAULT '',
    -- Source
    source_file    TEXT NOT NULL,
    data_json      TEXT NOT NULL
);
CREATE INDEX idx_tasks_feature ON tasks(feature_id, phase_id);
CREATE INDEX idx_tasks_status  ON tasks(project_id, status);
```

### 7. Features

```sql
CREATE TABLE features (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT DEFAULT 'backlog',
    category        TEXT DEFAULT '',
    total_tasks     INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    -- Hierarchy (sub-features)
    parent_feature_id TEXT,
    -- Timestamps
    created_at      TEXT DEFAULT '',
    updated_at      TEXT DEFAULT '',
    completed_at    TEXT DEFAULT '',
    -- Full data
    data_json       TEXT NOT NULL
);
CREATE INDEX idx_features_project ON features(project_id);

CREATE TABLE feature_phases (
    id              TEXT PRIMARY KEY,      -- "{feature_id}:phase-{n}"
    feature_id      TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    phase           TEXT NOT NULL,
    title           TEXT DEFAULT '',
    status          TEXT DEFAULT 'backlog',
    progress        INTEGER DEFAULT 0,
    total_tasks     INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0
);
CREATE INDEX idx_phases_feature ON feature_phases(feature_id);
```

### 8. Analytics (Multi-Entity Time-Series)

```sql
-- Metric type registry (extensible)
CREATE TABLE metric_types (
    id            TEXT PRIMARY KEY,        -- 'session_cost' | 'tokens_used' | 'task_velocity'
    display_name  TEXT NOT NULL,
    unit          TEXT DEFAULT '',          -- '$' | 'tokens' | 'count' | '%' | 'seconds'
    value_type    TEXT DEFAULT 'gauge',     -- 'gauge' | 'counter' | 'histogram'
    aggregation   TEXT DEFAULT 'sum',       -- how to roll up: 'sum' | 'avg' | 'max' | 'min' | 'count'
    description   TEXT DEFAULT ''
);

-- Analytics data points
CREATE TABLE analytics_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    metric_type   TEXT NOT NULL REFERENCES metric_types(id),
    value         REAL NOT NULL,
    captured_at   TEXT NOT NULL,
    period        TEXT DEFAULT 'point',     -- 'point' | 'hourly' | 'daily' | 'weekly'
    metadata_json TEXT                      -- extra context (model breakdown, etc.)
);
CREATE INDEX idx_analytics_lookup
    ON analytics_entries(project_id, metric_type, captured_at);
CREATE INDEX idx_analytics_period
    ON analytics_entries(project_id, period, captured_at);

-- Link analytics entries to entities (many-to-many across types)
CREATE TABLE analytics_entity_links (
    analytics_id  INTEGER NOT NULL REFERENCES analytics_entries(id) ON DELETE CASCADE,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    PRIMARY KEY (analytics_id, entity_type, entity_id)
);
CREATE INDEX idx_analytics_entity
    ON analytics_entity_links(entity_type, entity_id);
```

**Example queries:**

```sql
-- Project-wide daily cost trend (no entity joins needed)
SELECT captured_at, value FROM analytics_entries
  WHERE project_id = ? AND metric_type = 'session_cost' AND period = 'daily'
  ORDER BY captured_at;

-- All cost metrics linked to feature F-123
SELECT ae.* FROM analytics_entries ae
  JOIN analytics_entity_links ael ON ae.id = ael.analytics_id
  WHERE ael.entity_type = 'feature' AND ael.entity_id = 'F-123'
    AND ae.metric_type = 'session_cost';

-- Total tokens across all sessions linked to a feature
SELECT SUM(s.tokens_in + s.tokens_out) FROM sessions s
  JOIN entity_links el ON el.target_type = 'session' AND el.target_id = s.id
  WHERE el.source_type = 'feature' AND el.source_id = 'F-123';
```

**Seed metric types:**

| id | display_name | unit | aggregation |
|---|---|---|---|
| `session_cost` | Session Cost | `$` | sum |
| `session_tokens` | Tokens Used | `tokens` | sum |
| `session_duration` | Session Duration | `seconds` | avg |
| `session_count` | Sessions | `count` | count |
| `task_velocity` | Tasks Completed | `count` | count |
| `task_completion_pct` | Completion % | `%` | avg |
| `feature_progress` | Feature Progress | `%` | avg |
| `tool_call_count` | Tool Calls | `count` | sum |
| `tool_success_rate` | Tool Success Rate | `%` | avg |
| `file_churn` | Files Modified | `count` | sum |

### 9. App-Specific Metadata + Alert Configs

```sql
CREATE TABLE app_metadata (
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id, key)
);

CREATE TABLE alert_configs (
    id         TEXT PRIMARY KEY,
    project_id TEXT,
    name       TEXT NOT NULL,
    metric     TEXT NOT NULL,
    operator   TEXT NOT NULL,
    threshold  REAL NOT NULL,
    is_active  INTEGER DEFAULT 1,
    scope      TEXT DEFAULT 'session'
);
```

---

## Sync Engine

### Incremental File Scanning

```python
class SyncEngine:
    async def sync_project(self, project: Project):
        await self._sync_sessions(project)
        await self._sync_documents(project)
        await self._sync_progress(project)
        await self._sync_features(project)       # re-derive after docs+progress
        await self._rebuild_entity_links(project) # auto-discover cross-references
        await self._capture_analytics(project)    # snapshot metrics

    async def _sync_sessions(self, project: Project):
        for jsonl_file in sessions_dir.glob("*.jsonl"):
            mtime = jsonl_file.stat().st_mtime
            cached = await self.sync_repo.get_sync_state(str(jsonl_file))
            if cached and cached.file_mtime == mtime:
                continue  # unchanged
            session = parse_session_file(jsonl_file)
            if session:
                await self.session_repo.upsert(session, project.id)
                await self.session_repo.upsert_logs(session.id, session.logs)
                await self.session_repo.upsert_tool_usage(session.id, session.toolsUsed)
                await self.session_repo.upsert_file_updates(session.id, session.updatedFiles)
```

### File Watcher

```python
async def watch_project_dirs(project: Project, sync_engine: SyncEngine):
    paths = [sessions_path, docs_path, progress_path]
    async for changes in awatch(*[p for p in paths if p.exists()]):
        affected = classify_changes(changes)
        await sync_engine.sync_changed_files(affected)
```

### Write-Through Flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant FS as Filesystem
    participant SE as SyncEngine
    participant DB as SQLite
    FE->>API: PATCH /features/{id}/status
    API->>FS: update_frontmatter_field()
    API->>SE: invalidate(file_path)
    SE->>FS: re-parse changed file
    SE->>DB: upsert updated entity
    API->>FE: return updated entity from DB
```

---

## API Changes

### Pagination

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int

@sessions_router.get("", response_model=PaginatedResponse[AgentSession])
async def list_sessions(offset: int = 0, limit: int = 50, project_id: str | None = None,
                        sort_by: str = "started_at", sort_order: str = "desc"):
    items = await session_repo.list_paginated(offset, limit, project_id)
    total = await session_repo.count(project_id)
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)
```

### Entity Links API

```python
@links_router.get("/{entity_type}/{entity_id}")
async def get_entity_links(entity_type: str, entity_id: str, link_type: str | None = None):
    """Get all links for an entity (bidirectional). Used for tree-view rendering."""

@links_router.post("")
async def create_link(link: EntityLinkCreate):
    """Create a manual entity link."""

@links_router.get("/{entity_type}/{entity_id}/tree")
async def get_entity_tree(entity_type: str, entity_id: str):
    """Get full tree (parent chain + children + siblings) for tree-view display."""
```

### Analytics Export

```python
@analytics_router.get("/trends")
async def get_trends(metric_type: str, project_id: str, period: str = "daily",
                     start: str | None = None, end: str | None = None): ...

@analytics_router.get("/export/prometheus")
async def export_prometheus(project_id: str | None = None):
    """Prometheus exposition format for Grafana import."""
```

### Cache Management

```python
@app.get("/api/cache/status")
async def cache_status(): ...

@app.post("/api/cache/rescan")
async def trigger_rescan(): ...
```

---

## Frontend Changes

### Pagination in DataContext

```typescript
const [sessionPage, setSessionPage] = useState(0);
const PAGE_SIZE = 50;

const loadMoreSessions = useCallback(async () => {
    const next = sessionPage + 1;
    const data = await fetchJson<PaginatedResponse<AgentSession>>(
        `/sessions?offset=${next * PAGE_SIZE}&limit=${PAGE_SIZE}`
    );
    setSessions(prev => [...prev, ...data.items]);
    setSessionPage(next);
    setHasMore(data.total > (next + 1) * PAGE_SIZE);
}, [sessionPage]);
```

### Entity Link Tree View

Render parent/child/sibling structures on entity detail pages using the `/tree` endpoint.

---

## Phase Breakdown

### Phase 1: Core Cache Layer *(highest priority — fixes performance)*

| Task ID | Title | Description |
|---|---|---|
| DB-P1-01 | Add `aiosqlite` dependency | Add to `requirements.txt` |
| DB-P1-02 | Create `backend/db/` package | `connection.py`, `migrations.py` with all CREATE TABLE statements |
| DB-P1-03 | Implement repository protocols | `repositories/base.py` with all Protocol definitions |
| DB-P1-04 | SQLite session repository | CRUD + pagination + normalized detail tables |
| DB-P1-05 | SQLite document repository | CRUD + type filtering |
| DB-P1-06 | SQLite task repository | CRUD + feature/phase grouping |
| DB-P1-07 | SQLite feature repository | CRUD + phases sub-table |
| DB-P1-08 | Entity links repository | CRUD + tree queries + bidirectional lookups |
| DB-P1-09 | Tags repository | CRUD + cross-entity tagging |
| DB-P1-10 | Sync engine | Incremental mtime-based scanning for all entity types |
| DB-P1-11 | Migrate routers | All endpoints read from DB; full scan on startup |
| DB-P1-12 | Persist alert configs | Move from hardcoded → DB table |

### Phase 2: File Watcher + Write-Through

| Task ID | Title | Description |
|---|---|---|
| DB-P2-01 | File watcher service | `watchfiles`-based background task monitoring project dirs |
| DB-P2-02 | Write-through | Status updates → filesystem → invalidate → re-sync |
| DB-P2-03 | Cache management API | `/api/cache/status` and `/api/cache/rescan` endpoints |

### Phase 3: Pagination + Frontend

| Task ID | Title | Description |
|---|---|---|
| DB-P3-01 | PaginatedResponse model | Generic paginated wrapper + query params on all list endpoints |
| DB-P3-02 | Frontend loadMore | Scroll-triggered loading in DataContext |
| DB-P3-03 | Cache-aware polling | Lightweight DB reads replace full re-parse |

### Phase 4: Analytics + Export

| Task ID | Title | Description |
|---|---|---|
| DB-P4-01 | Metric types registry | Seed table with 10+ metric definitions |
| DB-P4-02 | Snapshot background task | Periodic capture into `analytics_entries` |
| DB-P4-03 | Multi-entity linking | `analytics_entity_links` population during sync |
| DB-P4-04 | Trends API | `/api/analytics/trends` with date-range queries |
| DB-P4-05 | Prometheus export | `/api/analytics/export/prometheus` for Grafana |
| DB-P4-06 | Frontend trend charts | Charts on Overview / Analytics pages |

### Phase 5: Optional Advanced Backends

| Task ID | Title | Description |
|---|---|---|
| DB-P5-01 | PostgreSQL repositories | Optional `asyncpg`-based implementations |
| DB-P5-02 | Config-driven selection | `CCDASH_DB_BACKEND=sqlite\|postgres` |
| DB-P5-03 | Redis hot-path cache | Optional layer for frequently-accessed queries |
| DB-P5-04 | Documentation | Setup guides for advanced users |

---

## File Structure

```
backend/db/
├── __init__.py
├── connection.py            # DB connection factory (SQLite/Postgres)
├── migrations.py            # Schema creation + versioning
├── repositories/
│   ├── __init__.py
│   ├── base.py              # Protocol definitions
│   ├── sessions.py          # SqliteSessionRepository
│   ├── documents.py         # SqliteDocumentRepository
│   ├── tasks.py             # SqliteTaskRepository
│   ├── features.py          # SqliteFeatureRepository
│   ├── links.py             # Entity links + external links + tags
│   └── analytics.py         # Analytics entries + metric types
├── sync_engine.py           # Incremental file → DB sync
└── file_watcher.py          # watchfiles-based change detection
```

---

## Verification Plan

### Automated Tests

- **SyncEngine**: Verify incremental sync only re-parses changed files
- **Repository CRUD**: All entity types against SQLite
- **Load test**: Ingest 459 session files, verify query time < 50ms
- **Write-through**: Update status → verify filesystem → verify DB
- **Entity links**: "All sessions for feature X", tree traversal queries
- **Analytics**: Snapshot capture, trend queries, Prometheus format

### Manual Verification

- Start with empty DB → verify full scan completes and populates all tables
- Modify a session JSONL file → verify watcher triggers re-parse
- Change project paths in Settings → verify rescan populates new data
- Scroll through sessions list → verify pagination loads more
- View entity detail → verify tree-view shows linked entities
- Import Prometheus endpoint into Grafana
