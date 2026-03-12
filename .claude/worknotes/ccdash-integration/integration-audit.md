# SkillMeat Integration Audit for CCDash

**Date**: 2026-03-08
**Author**: Opus (SkillMeat-side audit)
**Audience**: CCDash implementing agents and engineers
**Grounded in**: Current SkillMeat codebase on branch `feat/aaa-rbac-foundation`

## Summary

This document answers all 10 deliverables from the CCDash integration design spec. Every claim is grounded in current source code. Items marked **Not Yet Stable** should not be depended on in V1.

---

## 1. Integration Contract Summary

### API Base Path

| Item | Value | Status |
|------|-------|--------|
| Base URL (local dev) | `http://127.0.0.1:8080` | **Confirmed** |
| API prefix | `/api/v1/` | **Confirmed** — all versioned endpoints use this prefix |
| Health endpoint | `/health` (no prefix) | **Confirmed** |
| OpenAPI spec | `/docs` (Swagger), `/redoc`, `/openapi.json` | **Confirmed** |
| API version | `0.1.0-alpha` (in `openapi.json` `info.version`) | **Confirmed** |

**Source**: `skillmeat/api/server.py`, `skillmeat/api/openapi.json`

### Feature Flags Relevant to CCDash

| Flag | Default | Purpose |
|------|---------|---------|
| `workflow_engine_enabled` | `true` | Gates all `/api/v1/workflows` and `/api/v1/workflow-executions` endpoints |
| `memory_context_enabled` | `true` | Gates context module and memory item endpoints |
| `modular_content_architecture` | `false` | Experimental — context entity restructuring, do not depend on |

**Source**: `skillmeat/api/config.py` (`APISettings`)

### Auth Model

**Default (local dev)**: `auth_enabled=false` — `LocalAuthProvider` is used. All requests pass through as `local_admin` with no credentials. This is the expected mode for CCDash local integration.

**Enterprise / hosted**: `auth_enabled=true` with `auth_provider=clerk` — CCDash would send `Authorization: Bearer <JWT>` validated against Clerk JWKS.

**Service-to-service (enterprise)**: `SKILLMEAT_ENTERPRISE_PAT_SECRET` — shared secret for enterprise bootstrap auth. Not relevant for standard integration.

**Recommendation for CCDash V1**: Assume `LocalAuthProvider` (no auth headers needed). If auth is enabled, send `Authorization: Bearer <token>` — the middleware handles both API key and Bearer token. Add a config field for optional bearer token.

**Source**: `skillmeat/api/config.py`, `skillmeat/api/middleware/auth.py`, `skillmeat/api/auth/`

### Versioning / Stability

The API is versioned at `v1` via URL prefix. However, the OpenAPI version is `0.1.0-alpha`, which means:

- **Endpoint paths** are stable within `/api/v1/`.
- **Response schemas** may gain new optional fields (additive changes OK).
- **Breaking changes** (field removals, type changes) are not expected but not formally guaranteed until `1.0.0`.
- **Workflow and execution endpoints** are newer and less battle-tested than artifact/collection endpoints.

**Recommendation**: CCDash should tolerate unknown fields in responses and treat missing optional fields gracefully.

### Pagination Conventions

Two modes coexist:

| Mode | Used By | Parameters | Response |
|------|---------|------------|----------|
| **Cursor-based** | Artifacts (`/artifacts`), Collections, Context modules | `limit` (int), `after`/`cursor` (string) | `page_info: { has_next_page, end_cursor, total_count }` |
| **Offset-based** | Workflows, Executions | `skip` (int, 0-based), `limit` (int) | Flat list, no page metadata |
| **Page-based** | Artifact list endpoint | `page` (int, 1-based), `page_size` (int, 1-100) | Flat list |

**Cursor format**: Base64-encoded opaque string. Do not parse — treat as opaque.

**Source**: `skillmeat/api/schemas/common.py` (`PageInfo`, `PaginatedResponse`)

### Error Response Shape

All errors follow a consistent envelope:

```json
{
  "error": "NotFound",
  "message": "Artifact 'skill:nonexistent' not found",
  "details": [
    {
      "code": "NOT_FOUND",
      "message": "No artifact matches the given identifier",
      "field": null
    }
  ],
  "request_id": "abc123"
}
```

**Programmatic error codes** (use `details[].code` for retry/fallback logic):
- `NOT_FOUND`, `DUPLICATE`, `CONFLICT` — resource errors
- `RATE_LIMITED` — back off and retry
- `VALIDATION_FAILED`, `INVALID_SOURCE`, `INVALID_TYPE` — client errors
- `GITHUB_API_ERROR`, `NETWORK_ERROR` — transient external errors
- `INTERNAL_ERROR` — server bug

**Source**: `skillmeat/api/schemas/errors.py`, `skillmeat/api/utils/error_handlers.py`

### Retry Guidance

| Status | Strategy |
|--------|----------|
| 429 | Retry after `Retry-After` header (if present), else exponential backoff |
| 500 | Retry once after 1s; if repeated, surface error to user |
| 502/503 | SkillMeat server down — use cached snapshots |
| 404 | Do not retry — resource does not exist |

### Rate Limiting

- Disabled by default (`rate_limit_enabled=false`).
- When enabled: IP-based, configurable `rate_limit_requests` per minute (default 100).
- Returns 429 with standard error envelope.

**Source**: `skillmeat/api/middleware/rate_limit.py`

---

## 2. Canonical Contracts

### 2a. Artifacts

**Status**: **Confirmed** — most mature API surface.

**OpenAPI spec**: `skillmeat/api/openapi.json` — authoritative.
**Router**: `skillmeat/api/routers/artifacts.py`
**Schemas**: `skillmeat/api/schemas/artifacts.py`

#### Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/artifacts` | List artifacts (paginated) |
| `GET` | `/api/v1/artifacts/{artifact_id}` | Get artifact detail |
| `GET` | `/api/v1/artifacts/{artifact_id}/files` | List artifact files |
| `GET` | `/api/v1/artifacts/{artifact_id}/files/{file_path:path}` | Get file content |
| `GET` | `/api/v1/artifacts/{artifact_id}/upstream` | Check upstream status |

#### Query Parameters (List)

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `artifact_type` | string (optional) | — | Filter: `skill`, `command`, `agent`, `mcp`, `hook`, `composite` |
| `page` | int | 1 | 1-based page number |
| `page_size` | int | 50 | Items per page (1-100) |

#### ArtifactResponse Fields

| Field | Type | Stable | Notes |
|-------|------|--------|-------|
| `id` | string | **Yes** | Composite key `type:name` (e.g., `skill:pdf`) |
| `uuid` | string | **Yes** | 32-char hex, globally unique |
| `name` | string | **Yes** | Artifact name |
| `type` | string | **Yes** | `skill`, `command`, `agent`, `mcp`, `hook`, `composite` |
| `source` | string | **Yes** | e.g., `anthropics/skills/pdf` |
| `origin` | string | **Yes** | `local`, `github`, `marketplace` |
| `origin_source` | string? | **Yes** | Original source when marketplace-sourced |
| `version` | string | **Yes** | e.g., `latest`, `1.2.3` |
| `aliases` | string[] | **Yes** | Alternative names |
| `tags` | string[] | **Yes** | Searchable tags |
| `metadata` | object? | **Yes** | Nested: `title`, `description`, `author`, `license`, `version`, `dependencies`, `tools`, `linked_artifacts`, `unlinked_references` |
| `upstream` | object? | **Yes** | `tracking_enabled`, `current_sha`, `upstream_sha`, `update_available`, `has_local_modifications`, `drift_status` |
| `deployment_stats` | object? | Partially | Deployment counters |
| `deployments` | array? | Partially | Deployment summaries |
| `collections` | array | **Yes** | Collection memberships |
| `added` | datetime | **Yes** | When added |
| `updated` | datetime | **Yes** | Last update |
| `owner_id` | UUID? | **Yes** | Owner (enterprise) |
| `visibility` | string? | **Yes** | `private`, `team`, `public` |

#### Identity Rules

- **Primary ID**: `type:name` — human-readable, stable across migrations. Use this for display and matching.
- **UUID**: 32-char hex — use for cross-system foreign keys when `type:name` might change (rare).
- **Immutability**: Both `id` and `uuid` are immutable once created.

### 2b. Workflows

**Status**: **Confirmed** — functional but newer than artifacts.

**Router**: `skillmeat/api/routers/workflows.py`
**Schemas**: `skillmeat/api/schemas/workflow.py`
**Gate**: `workflow_engine_enabled` feature flag

#### Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/workflows` | List workflows |
| `POST` | `/api/v1/workflows` | Create from YAML |
| `GET` | `/api/v1/workflows/{workflow_id}` | Get workflow detail |
| `PUT` | `/api/v1/workflows/{workflow_id}` | Update YAML |
| `DELETE` | `/api/v1/workflows/{workflow_id}` | Delete |
| `POST` | `/api/v1/workflows/{workflow_id}/validate` | Validate YAML |
| `POST` | `/api/v1/workflows/{workflow_id}/plan` | Generate execution plan |

#### Query Parameters (List)

| Param | Type | Default |
|-------|------|---------|
| `project_id` | string? | — |
| `skip` | int | 0 |
| `limit` | int | 50 (max 200) |

#### WorkflowResponse Fields

| Field | Type | Stable | Notes |
|-------|------|--------|-------|
| `id` | string | **Yes** | DB PK (UUID hex) |
| `name` | string | **Yes** | Display name |
| `description` | string? | **Yes** | — |
| `version` | string | **Yes** | SemVer |
| `status` | string | **Yes** | `draft`, `active`, `archived` |
| `definition` | string | **Yes** | Raw YAML (SWDL format) |
| `tags` | string[] | **Yes** | Searchable |
| `stages` | StageResponse[] | **Yes** | Ordered list |
| `project_id` | string? | **Yes** | Owner project |
| `created_at` | datetime | **Yes** | — |
| `updated_at` | datetime | **Yes** | — |

#### StageResponse Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | DB PK |
| `stage_id_ref` | string | SWDL reference (kebab-case) |
| `name` | string | Display name |
| `stage_type` | string | `agent`, `gate`, `fan_out` |
| `order_index` | int | 0-based position |
| `condition` | string? | SWDL guard expression |
| `depends_on` | string[] | Stage ID references |

#### Provenance / Version

- `version` field tracks SemVer on the workflow definition.
- `definition` field contains the raw YAML — CCDash can parse this for artifact references.
- No separate "provenance" or "source" field — workflows are local definitions, not sourced from external registries.

### 2c. Context Modules

**Status**: **Confirmed** — part of Memory & Context Intelligence System.

**Router**: `skillmeat/api/routers/context_modules.py`
**Schemas**: `skillmeat/api/schemas/context_module.py`
**Gate**: `memory_context_enabled` feature flag

#### Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/context-modules` | List modules (project-scoped) |
| `POST` | `/api/v1/context-modules` | Create module |
| `GET` | `/api/v1/context-modules/{module_id}` | Get module detail |
| `PUT` | `/api/v1/context-modules/{module_id}` | Update module |
| `DELETE` | `/api/v1/context-modules/{module_id}` | Delete module |
| `POST` | `/api/v1/context-modules/{module_id}/memories` | Add memory to module |
| `DELETE` | `/api/v1/context-modules/{module_id}/memories/{memory_id}` | Remove memory |
| `GET` | `/api/v1/context-modules/{module_id}/memories` | List module's memories |

#### Context Packing Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/context-packs/preview` | Preview pack (read-only, token estimate) |
| `POST` | `/api/v1/context-packs/generate` | Generate full pack markdown |

#### ContextModuleResponse Fields

| Field | Type | Stable | Notes |
|-------|------|--------|-------|
| `id` | string | **Yes** | Unique module ID |
| `project_id` | string | **Yes** | Project scope |
| `name` | string | **Yes** | Human-readable |
| `description` | string? | **Yes** | — |
| `selectors` | object? | **Yes** | `memory_types`, `min_confidence`, `file_patterns`, `workflow_stages` |
| `priority` | int | **Yes** | 0-100, default 5 |
| `content_hash` | string? | **Yes** | SHA-256 for change detection |
| `created_at` | string? | **Yes** | ISO 8601 |
| `updated_at` | string? | **Yes** | ISO 8601 |
| `memory_items` | array? | Partially | Only when `include_items=true` |

#### Identity Rules

- **ID**: Opaque string (database PK). Use as foreign key.
- **Name**: Human-readable, unique within project scope. Safe for display.
- **`ctx:name` format**: Not currently implemented as an API-level identifier. CCDash should use `id` for lookups and `name` for display. The `ctx:name` convention exists in CLI/SWDL authoring but is not a direct API query parameter.

### 2d. Workflow Executions

**Status**: **Confirmed** — functional, newer surface.

**Router**: `skillmeat/api/routers/workflow_executions.py`
**Schemas**: `skillmeat/api/schemas/workflow_executions.py`

#### Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/workflow-executions` | Start execution |
| `GET` | `/api/v1/workflow-executions` | List executions |
| `GET` | `/api/v1/workflow-executions/by-workflow/{workflow_id}` | List by workflow |
| `GET` | `/api/v1/workflow-executions/{execution_id}` | Get execution (with steps) |
| `GET` | `/api/v1/workflow-executions/{execution_id}/stream` | SSE event stream |
| `POST` | `/api/v1/workflow-executions/{execution_id}/pause` | Pause |
| `POST` | `/api/v1/workflow-executions/{execution_id}/resume` | Resume |
| `POST` | `/api/v1/workflow-executions/{execution_id}/cancel` | Cancel |

#### ExecutionResponse Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | DB PK (UUID hex) |
| `workflow_id` | string | Parent workflow ID |
| `status` | string | `pending`, `running`, `paused`, `completed`, `failed`, `cancelled` |
| `parameters` | object? | Resolved execution params |
| `started_at` | datetime? | — |
| `completed_at` | datetime? | — |
| `error_message` | string? | — |
| `steps` | ExecutionStepResponse[] | Per-stage records |

#### ExecutionStepResponse Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | DB PK |
| `stage_id` | string | Kebab-case SWDL reference |
| `stage_name` | string | Display name |
| `stage_type` | string | `agent`, `gate`, `fan_out` |
| `batch_index` | int | Parallel batch (0-based) |
| `status` | string | `pending`, `running`, `completed`, `failed` |
| `started_at` | datetime? | — |
| `completed_at` | datetime? | — |
| `error_message` | string? | — |

---

## 3. Project/Workspace Mapping

### Recommended Mapping Strategy

| CCDash Concept | SkillMeat Equivalent | How to Map |
|----------------|---------------------|------------|
| CCDash project | SkillMeat project | Store the SkillMeat project path (e.g., `/Users/me/my-project`) as the CCDash integration setting. Use this as `project_id` in API calls. |
| CCDash project scope | SkillMeat collection + project | A SkillMeat "project" points to a filesystem directory. Artifacts live in "collections" and get "deployed" to projects. CCDash should track the project path and optionally the default collection ID. |
| Workspace | Not exposed | No workspace concept in the API. Projects are self-contained scopes. |

### Project ID Format

- **Type**: Filesystem path string (e.g., `/Users/miethe/dev/homelab/development/skillmeat`)
- **URL encoding**: Path-based IDs use `:path` FastAPI parameter — URL-encode slashes when calling the API.
- **Uniqueness**: Tied to filesystem location. Unique within a SkillMeat instance.

### Collection vs Project vs Filesystem

| Layer | Purpose | Source of Truth |
|-------|---------|-----------------|
| **Filesystem collection** (`~/.skillmeat/collection/`) | User's artifact library | Filesystem |
| **DB collection** (user-collections) | Organizational groupings in the web UI | Database |
| **Project** | A target directory where artifacts are deployed | Filesystem path |
| **Context modules / Memory items** | Project-scoped knowledge groupings | Database |
| **Workflows** | Can be project-scoped or global | Database |

### CCDash Integration Config Recommendation

Store per-CCDash-project:
```json
{
  "skillmeat_base_url": "http://127.0.0.1:8080",
  "skillmeat_project_id": "/Users/me/my-project",
  "skillmeat_collection_id": "default",
  "skillmeat_auth_token": null,
  "skillmeat_enabled": true
}
```

**Source**: `skillmeat/api/routers/projects.py`, `skillmeat/api/routers/user_collections.py`

---

## 4. Artifact Definition Guidance

### Artifact ID Format

- **Primary**: `type:name` (e.g., `skill:pdf`, `agent:claude-code`, `command:deploy`)
- **Uniqueness**: Unique within a SkillMeat instance. The `type:` prefix prevents name collisions across artifact types.
- **Immutable**: Once created, the `type:name` ID does not change.

### Artifact Types CCDash Should Prioritize

| Type | Priority | Rationale |
|------|----------|-----------|
| `skill` | **High** | Most common artifact type, directly maps to capabilities |
| `agent` | **High** | Maps to orchestration patterns and subagent topology |
| `command` | **Medium** | Maps to execution entry points (slash commands) |
| `mcp` | **Medium** | MCP server definitions, relevant for tool-use analysis |
| `hook` | **Low** | Event-driven, less directly tied to workflow stacks |
| `composite` | **Low** | Multi-artifact packages — resolve to constituent parts |

### Linked Artifacts

The `metadata.linked_artifacts` field contains references to other artifacts declared as dependencies:

```json
{
  "metadata": {
    "linked_artifacts": [
      {"name": "aesthetic", "type": "skill"},
      {"name": "artifact-tracking", "type": "skill"}
    ]
  }
}
```

**Interpretation**: These are declared dependencies, not runtime observations. CCDash should use them for:
- Pre-populating candidate stack components
- Understanding artifact relationships
- Informing recommendation groupings

**`unlinked_references`**: String references found in artifact content that couldn't be resolved to known artifacts. Useful for discovering implicit dependencies.

### Alias Safety

- Aliases are mutable and user-defined.
- **Do not use aliases for matching** — use `type:name` or `uuid` only.
- Aliases are safe for display/search but not for stable foreign keys.

### Metadata Stability

| Field | Stable for Scoring? |
|-------|---------------------|
| `metadata.title` | Yes — display only |
| `metadata.description` | Yes — display only |
| `metadata.author` | Yes — attribution |
| `metadata.tools` | **Partially** — tool lists may change between versions |
| `metadata.linked_artifacts` | **Yes** — good for stack composition |
| `metadata.dependencies` | **Yes** — good for dependency graphs |
| `tags` | **Yes** — good for category matching |

---

## 5. Workflow Definition Guidance

### Base vs Override

- **Base workflow**: Created via `POST /api/v1/workflows` with `project_id=null` — global definition.
- **Project override**: Created with `project_id=<path>` — scoped to a specific project.
- **No explicit override layer**: There is no "inherit + patch" mechanism. A project workflow is a standalone definition that happens to be scoped.

**Recommendation for CCDash**: Fetch all workflows, filter by `project_id` to find project-specific ones. If a project has its own workflow with the same `name` as a global one, treat the project version as the effective definition.

### Workflow ID vs Name

| Field | Use For |
|-------|---------|
| `id` (UUID hex) | Stable foreign key, API lookups |
| `name` | Display, fuzzy matching against session evidence |

### Stage-Level Artifact References

Stages in SWDL YAML can reference artifacts. The `stages[].stage_type` field indicates:
- `agent` — references an agent artifact
- `gate` — a manual approval checkpoint
- `fan_out` — parallel stage execution

The raw `definition` (YAML) field contains the full SWDL including any artifact references in stage configurations. CCDash should parse the YAML to extract artifact IDs when needed.

### Context Module References

Workflows can reference context modules in their SWDL definition using `ctx:module_name` syntax. These are authoring-time references; at execution time they resolve to context module IDs.

### Execution / Planning Endpoints

| Endpoint | Safe to Depend On | Notes |
|----------|--------------------|-------|
| `POST .../validate` | **Yes** | Static YAML validation, no side effects |
| `POST .../plan` | **Yes** | Generates execution plan without running it |
| `POST /workflow-executions` | **Yes** | Starts real execution |
| `GET /workflow-executions/{id}` | **Yes** | Execution state + step details |

### Plan Output

The `/plan` endpoint returns an execution plan showing:
- Stage ordering and parallelization batches
- Dependency resolution
- Estimated execution structure

**This is a good candidate for CCDash to consume** — it represents the "effective workflow" after validation and dependency resolution.

### Known Caveats

1. **No inheritance model**: No base+override merge. Project workflows are independent definitions.
2. **SWDL format is SkillMeat-specific**: CCDash needs a SWDL parser to extract stage-level artifact references from the `definition` YAML field.
3. **Workflow `id` is a UUID**, not a human-readable composite like artifacts.

---

## 6. Context Module Guidance

### Stable Identifiers

| Identifier | Format | Use For |
|------------|--------|---------|
| `id` | Opaque string (DB PK) | API lookups, foreign keys |
| `name` | String (unique per project) | Display, fuzzy matching |

### Resolution Strategy

- **By ID**: `GET /api/v1/context-modules/{module_id}` — always works.
- **By name**: Not a direct API query parameter. List modules for a project and filter client-side by `name`.
- **`ctx:name`**: This is a SWDL authoring convention, not an API query format. CCDash should resolve `ctx:name` references by listing modules and matching `name`.

### Selector Semantics

The `selectors` object controls which memory items are included in a context pack:

```json
{
  "memory_types": ["decision", "gotcha", "learning"],
  "min_confidence": 0.7,
  "file_patterns": ["skillmeat/api/**/*.py"],
  "workflow_stages": ["implementation", "review"]
}
```

| Selector Key | Type | Semantics |
|-------------|------|-----------|
| `memory_types` | string[] | Filter by memory type (`decision`, `constraint`, `gotcha`, `style_rule`, `learning`) |
| `min_confidence` | float | Minimum confidence threshold (0.0-1.0) |
| `file_patterns` | string[] | Glob patterns for file-anchored memories |
| `workflow_stages` | string[] | Stage names for workflow-relevant memories |

### Content Hash / Packed Content

- `content_hash` (SHA-256) is available and stable — use for change detection / cache invalidation.
- Packed content is available via `POST /api/v1/context-packs/generate` — returns structured markdown with token count.
- Pack preview (`POST /api/v1/context-packs/preview`) returns item selection and token estimate without generating markdown.

### Deep-Link for Context Modules

- **No dedicated detail page** in the web UI. Context entities are listed at `/context-entities`.
- Context modules (Memory & Context system) are managed via the project memory page: `/projects/{project_id}/memory`.
- **Safest display fallback**: Show module `name` with a link to `/projects/{project_id}/memory`.

---

## 7. Deep-Link / UI Routing Contract

### Confirmed Routes

| Entity | URL Pattern | Status |
|--------|-------------|--------|
| Artifact detail | `/artifacts/{type:name}` | **Confirmed** — e.g., `/artifacts/skill:pdf` |
| Workflow detail | `/workflows/{workflow_id}` | **Confirmed** — UUID-based |
| Workflow execution list | `/workflows/executions` | **Confirmed** |
| Context entities | `/context-entities` | **Confirmed** — list view, no detail route |
| Project detail | `/projects/{project_id}` | **Confirmed** — path-encoded |
| Project memory | `/projects/{project_id}/memory` | **Confirmed** |
| Collection browser | `/collection` | **Confirmed** |

### Caveats

1. **Artifact deep links work directly** with `type:name` IDs — no encoding needed for the colon.
2. **Workflow deep links** use UUID hex — CCDash must store the workflow `id` (not just `name`).
3. **Execution deep links**: No direct `execution_id` route exists. Link to `/workflows/executions?workflow_id={wf_id}` as closest match.
4. **Context module deep links**: No dedicated page. Link to `/projects/{project_id}/memory` as fallback.
5. **Project IDs in URLs**: Filesystem paths need URL encoding (slashes → `%2F`).

### URL Construction

```
Base: http://localhost:3000  (Next.js dev default)

Artifact:  {base}/artifacts/{artifact_id}
Workflow:  {base}/workflows/{workflow_id}
Project:   {base}/projects/{encodeURIComponent(project_id)}
Memory:    {base}/projects/{encodeURIComponent(project_id)}/memory
```

**Source**: `skillmeat/web/app/` directory structure (Next.js App Router)

---

## 8. Enhancement Opportunities

### Priority 1: High Value, Low Effort

#### 8a. Effective Workflow Endpoint

**Why**: CCDash needs to resolve what workflow actually applies to a project, considering scoping. Currently there's no single "give me the effective workflow for project X" endpoint.

**Current support**: `GET /api/v1/workflows?project_id=X` returns project-scoped workflows. Global workflows are separate.

**Smallest useful change**: Add a `GET /api/v1/workflows/effective?project_id=X` endpoint that returns project workflows with global fallbacks, ordered by relevance.

#### 8b. Stable Deep-Link IDs for Context Modules

**Why**: CCDash needs to link to specific context modules. Currently there's no dedicated detail page.

**Current support**: Modules have stable `id` fields. The web UI has a project memory page.

**Smallest useful change**: Add `/context-modules/{module_id}` detail page in the web UI, or add query param support (`/projects/{id}/memory?module={module_id}`) for scroll-to behavior.

#### 8c. Bundle / Stack Definitions

**Why**: CCDash wants to recommend "stacks" (artifact combinations). SkillMeat has a bundles system.

**Current support**: `GET /api/v1/bundles` exists with list, detail, import, export, validate, and analytics endpoints. Bundles represent curated artifact groupings.

**Smallest useful change**: Expose bundle composition (constituent artifact IDs) in the bundle detail response. CCDash can map observed stacks to known bundles.

### Priority 2: Medium Value, Medium Effort

#### 8d. Webhook / Event Integration

**Why**: Polling for definition changes is wasteful. CCDash would benefit from push notifications.

**Current support**: No webhook system exists. SSE exists for workflow execution streaming only.

**Smallest useful change**: Add a webhook registration endpoint (`POST /api/v1/webhooks`) that fires on artifact mutations, workflow changes, and execution completions.

#### 8e. Context Pack Preview for External Consumers

**Why**: CCDash could use context pack previews to understand what knowledge is available for a workflow.

**Current support**: `POST /api/v1/context-packs/preview` exists and returns token estimates + item selection.

**Smallest useful change**: Already available. CCDash just needs to call it.

#### 8f. Workflow Outcome Metadata

**Why**: CCDash wants to correlate SkillMeat workflow executions with delivery outcomes.

**Current support**: Execution responses include `status`, `started_at`, `completed_at`, `error_message`, and per-step status. No outcome quality metrics.

**Smallest useful change**: Add optional `outcome_metadata` field (JSON) to execution records that CCDash (or other consumers) could write back with outcome signals.

### Priority 3: High Value, High Effort

#### 8g. Recommendation Metadata on Workflows

**Why**: SkillMeat could expose workflow recommendations natively (e.g., "for feature type X, start with workflow Y").

**Current support**: Not implemented.

**Smallest useful change**: Add a `recommendations` field to workflow definitions — author-provided guidance that CCDash can combine with observed effectiveness.

#### 8h. Push Event System

**Why**: Full event-driven integration instead of polling + webhooks.

**Current support**: SSE for executions only.

**Smallest useful change**: Extend SSE to a general event bus (artifact changes, workflow updates, execution events). More complex than webhooks but better for real-time UIs.

---

## 9. Example Payloads / Fixtures

See companion file: `example-payloads.json`

---

## 10. Final Recommendation

### V1: What CCDash Should Rely On Now

| Surface | Endpoints | Status |
|---------|-----------|--------|
| **Artifact definitions** | `GET /api/v1/artifacts`, `GET /api/v1/artifacts/{id}` | **Stable** — most mature surface |
| **Workflow definitions** | `GET /api/v1/workflows`, `GET /api/v1/workflows/{id}` | **Stable** — functional, well-tested |
| **Workflow plans** | `POST /api/v1/workflows/{id}/plan` | **Stable** — no side effects |
| **Context modules** | `GET /api/v1/context-modules`, `GET /api/v1/context-modules/{id}` | **Stable** — functional |
| **Context packs** | `POST /api/v1/context-packs/preview` | **Stable** — read-only |
| **Deep links** | `/artifacts/{id}`, `/workflows/{id}` | **Stable** |
| **Auth** | `LocalAuthProvider` (no headers) | **Stable** — default mode |
| **Error responses** | Standard envelope with `code` field | **Stable** |

**V1 integration pattern**:
1. Store SkillMeat base URL + project path in CCDash project settings.
2. Sync artifacts via `GET /artifacts` (paginated).
3. Sync workflows via `GET /workflows?project_id=X` + `GET /workflows` (global).
4. Sync context modules via `GET /context-modules?project_id=X`.
5. For each artifact/workflow/module, store a snapshot with `id`, `version`/`updated_at`, and raw response.
6. Deep-link using `/artifacts/{id}` and `/workflows/{id}`.
7. Tolerate SkillMeat unavailability by falling back to cached snapshots.

### V2: What Would Unlock Better Fidelity

| Enhancement | Impact |
|-------------|--------|
| Effective workflow endpoint | Eliminates client-side project+global merge logic |
| Context module deep-link page | Direct navigation from CCDash recommendations |
| Bundle composition exposure | Maps observed stacks to curated bundles |
| Webhook notifications | Eliminates polling for definition changes |
| Execution outcome metadata | Enables round-trip effectiveness measurement |
| Workflow recommendation metadata | Author-provided hints improve recommendation quality |

### Do Not Depend On (Unstable)

| Item | Reason |
|------|--------|
| `modular_content_architecture` flag | Experimental, not finalized |
| Context entity types (spec/rule/context files) | Overlaps with context modules, may be restructured |
| Marketplace publishing endpoints | Internal workflow, not stable for external integration |
| Artifact deployment strategies (merge mode) | Complex, internal-facing |

---

## Source Files Referenced

| File | Purpose |
|------|---------|
| `skillmeat/api/openapi.json` | Canonical API contract |
| `skillmeat/api/server.py` | Router registration, lifespan |
| `skillmeat/api/config.py` | APISettings, feature flags |
| `skillmeat/api/middleware/auth.py` | Auth middleware, LocalAuthProvider |
| `skillmeat/api/auth/` | Auth provider implementations |
| `skillmeat/api/dependencies.py` | DI aliases, AuthContextDep |
| `skillmeat/api/routers/artifacts.py` | Artifact endpoints |
| `skillmeat/api/routers/workflows.py` | Workflow endpoints |
| `skillmeat/api/routers/workflow_executions.py` | Execution endpoints |
| `skillmeat/api/routers/context_modules.py` | Context module endpoints |
| `skillmeat/api/routers/context_packing.py` | Context pack endpoints |
| `skillmeat/api/routers/projects.py` | Project endpoints |
| `skillmeat/api/routers/user_collections.py` | Collection endpoints |
| `skillmeat/api/routers/bundles.py` | Bundle endpoints |
| `skillmeat/api/routers/memory_items.py` | Memory item endpoints |
| `skillmeat/api/schemas/artifacts.py` | Artifact schemas |
| `skillmeat/api/schemas/workflow.py` | Workflow schemas |
| `skillmeat/api/schemas/workflow_executions.py` | Execution schemas |
| `skillmeat/api/schemas/context_module.py` | Context module schemas |
| `skillmeat/api/schemas/context_entity.py` | Context entity schemas |
| `skillmeat/api/schemas/errors.py` | Error response schemas |
| `skillmeat/api/schemas/common.py` | Pagination schemas |
| `skillmeat/api/utils/error_handlers.py` | Error handling utilities |
| `skillmeat/web/app/` | Next.js UI routes |
