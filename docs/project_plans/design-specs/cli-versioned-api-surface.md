---
schema_version: "1.0"
doc_type: design-spec
title: "CCDash CLI Versioned Client API Surface"
status: draft
created: "2026-04-12"
feature_slug: "ccdash-standalone-global-cli"
prd_ref: "docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md"
---

# CCDash CLI Versioned Client API Surface

## Purpose

This document defines the read-only HTTP surface that the standalone `ccdash` CLI will consume.
It is separate from the existing `/api/agent/` surface, which is reserved for MCP and AI agent
consumers. The versioned client API is the stable contract that makes the CLI distributable,
remotely pointed, and script-friendly.

The canonical server implementation lives in `backend/routers/client_v1.py` (to be created in
Phase 2). All handlers must remain thin adapters over existing application services and
repositories. No business logic belongs in the router layer.

---

## Design Decisions

### D1: `/api/v1/` prefix, not `/api/agent/`

The existing `/api/agent/` prefix carries a specific semantic: it is the transport for agent and
MCP consumers whose primary user is another AI process. Mixing a human-operator CLI into that
surface would blur the audience boundary and make future versioning or access-control decisions
harder. A separate `/api/v1/` prefix keeps the two consumer populations independently evolvable.

### D2: URL-based versioning (`/v1/`, `/v2/`)

Header-based versioning (e.g. `Accept: application/vnd.ccdash.v1+json`) is invisible in browser
URLs, harder to mock in tests, and not supported by all HTTP clients without extra configuration.
URL-based versioning is explicit, easy to route, and unambiguous in logs. A future `/api/v2/`
prefix can coexist with `/api/v1/` without touching existing clients.

### D3: Response envelope

All v1 responses are wrapped in a standard JSON object:

```json
{
  "status": "ok" | "partial" | "error",
  "data": { ... },
  "meta": {
    "generated_at": "<iso8601>",
    "instance_id": "<instance-name>",
    "request_id": "<uuid>"
  }
}
```

`status` semantics align with the existing `AgentQueryEnvelope` convention:
- `ok`: primary entity resolved and all supporting data loaded
- `partial`: primary entity resolved but one or more supporting sources were unavailable
- `error`: primary entity or request scope could not be resolved

### D4: Pagination envelope (list endpoints)

```json
{
  "status": "ok",
  "data": [ ... ],
  "meta": {
    "cursor": "<opaque-string or null>",
    "has_more": true,
    "total": 120,
    "limit": 50,
    "generated_at": "...",
    "instance_id": "..."
  }
}
```

Cursor-based pagination is preferred for live data whose underlying order can shift between
requests. For stable ordered data (e.g. sorted feature lists), offset/limit is acceptable as a
pragmatic fallback when a cursor implementation would not add real value. Endpoints that support
both document both. CLI commands that use `--offset` / `--limit` flags map directly.

### D5: Error envelope

```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND" | "INVALID_PARAM" | "SERVER_ERROR" | "UNAUTHORIZED" | "UNAVAILABLE",
    "message": "Human-readable description",
    "detail": { }
  },
  "meta": { "generated_at": "...", "instance_id": "...", "request_id": "..." }
}
```

Error codes are uppercase snake-case strings so CLI error handling can switch on them without
parsing free-text messages. `detail` is optional and may carry structured context (e.g. which
field failed validation).

---

## Endpoint Catalog

### Instance / Connectivity

#### `GET /api/v1/instance`

Allows the CLI to confirm which CCDash instance answered a request and what capabilities it
advertises. Used by `ccdash doctor` and embedded in every response `meta.instance_id` field.

| Field | Detail |
|-------|--------|
| Parameters | none |
| Response DTO | `InstanceMetaDTO` (new) |
| Service | New — thin handler reading `config.py` values |
| Pagination | N/A |

`InstanceMetaDTO` fields: `instance_id` (str), `version` (str), `environment` (str), `db_backend`
(str), `capabilities` (list[str]), `server_time` (datetime).

`capabilities` is a string list that names which endpoint groups are active on this instance (e.g.
`["project", "features", "sessions", "workflows", "reports"]`). The CLI uses this list to degrade
gracefully when talking to an older server that does not yet expose every group.

---

### Project

#### `GET /api/v1/project/status`

Returns the project overview snapshot. Directly reuses `ProjectStatusQueryService`.

| Field | Detail |
|-------|--------|
| Parameters | `project_id` (query, optional) |
| Response DTO | `ProjectStatusDTO` (existing, wrapped in envelope) |
| Service | `ProjectStatusQueryService.get_status()` |
| Pagination | N/A |

CLI command: `ccdash status project`

---

### Features

#### `GET /api/v1/features`

Paginated list of features with lightweight filter support. Delegates to the existing features
repository (`repo.list_paginated`). Does not include full task trees — the list payload carries
summary-level fields only.

| Field | Detail |
|-------|--------|
| Parameters | `status` (query, optional, repeatable), `category` (query, optional), `limit` (query, default 50, max 200), `offset` (query, default 0) |
| Response DTO | `FeatureListDTO` (new) containing `list[FeatureSummaryDTO]` |
| Service | features repository `list_paginated` + `count` |
| Pagination | offset/limit; cursor deferred to Phase 2 if needed |

`FeatureSummaryDTO` fields: `id`, `name`, `status`, `category`, `priority`, `total_tasks`,
`completed_tasks`, `updated_at`.

CLI command: `ccdash feature list`

---

#### `GET /api/v1/features/{feature_id}`

Full feature forensics detail. Reuses `FeatureForensicsQueryService`. The response is richer than
the list payload and includes linked sessions, documents, tasks, workflow mix, and narrative.

| Field | Detail |
|-------|--------|
| Parameters | `feature_id` (path, required) |
| Response DTO | `FeatureForensicsDTO` (existing, wrapped in envelope) |
| Service | `FeatureForensicsQueryService.get_forensics()` |
| Pagination | N/A |

Returns HTTP 404 / error envelope with code `NOT_FOUND` for unknown feature IDs.

CLI command: `ccdash feature show <feature-id>`

---

#### `GET /api/v1/features/{feature_id}/sessions`

Sessions linked to a specific feature, without the full forensics payload. Useful for fast
investigation without the cost of assembling the complete forensics bundle.

| Field | Detail |
|-------|--------|
| Parameters | `feature_id` (path, required), `limit` (query, default 50), `offset` (query, default 0) |
| Response DTO | `FeatureSessionsDTO` (new) containing `list[SessionRef]` |
| Service | features repository `get_linked_sessions` (existing) or `FeatureForensicsQueryService` partial assembly |
| Pagination | offset/limit |

`FeatureSessionsDTO` fields: `feature_id`, `feature_slug`, `sessions` (list[`SessionRef`]),
`total`.

CLI command: `ccdash feature sessions <feature-id>`

---

#### `GET /api/v1/features/{feature_id}/documents`

Documents linked to a specific feature. Surfaces `DocumentRef` entries without the full forensics
bundle.

| Field | Detail |
|-------|--------|
| Parameters | `feature_id` (path, required) |
| Response DTO | `FeatureDocumentsDTO` (new) containing `list[DocumentRef]` |
| Service | `FeatureForensicsQueryService` partial assembly, or direct links repository |
| Pagination | N/A (document counts per feature are typically small) |

CLI command: `ccdash feature documents <feature-id>`

---

### Sessions

Session endpoints wrap the existing analytics `session-intelligence` services under a stable,
versioned path. The underlying `SessionIntelligenceReadService` and `TranscriptSearchService`
objects are reused; only the routing path and response envelope change.

#### `GET /api/v1/sessions`

Paginated session list with common filters. Delegates to `session_intelligence_read_service.list_sessions`.

| Field | Detail |
|-------|--------|
| Parameters | `feature_id` (query, optional), `root_session_id` (query, optional), `limit` (query, default 50, max 100), `offset` (query, default 0) |
| Response DTO | `SessionListDTO` (new) wrapping `list[SessionIntelligenceSummary]` from existing `SessionIntelligenceListResponse` |
| Service | `SessionIntelligenceReadService.list_sessions()` (existing, at `/api/analytics/session-intelligence`) |
| Pagination | offset/limit |

CLI command: `ccdash session list`

---

#### `GET /api/v1/sessions/{session_id}`

Full intelligence detail for a single session.

| Field | Detail |
|-------|--------|
| Parameters | `session_id` (path, required) |
| Response DTO | `SessionDetailDTO` (new) wrapping `SessionIntelligenceDetailResponse` (existing) |
| Service | `SessionIntelligenceReadService.get_session_detail()` (existing, at `/api/analytics/session-intelligence/detail`) |
| Pagination | N/A |

Returns HTTP 404 / error envelope with code `NOT_FOUND` for unknown session IDs.

CLI command: `ccdash session show <session-id>`

---

#### `GET /api/v1/sessions/search`

Intelligence search across session transcripts. Delegates to `TranscriptSearchService.search`.

| Field | Detail |
|-------|--------|
| Parameters | `q` (query, required, min 2 chars), `feature_id` (query, optional), `root_session_id` (query, optional), `session_id` (query, optional), `limit` (query, default 25, max 100), `offset` (query, default 0) |
| Response DTO | `SessionSearchDTO` (new) wrapping `SessionSemanticSearchResponse` (existing) |
| Service | `TranscriptSearchService.search()` (existing, at `/api/analytics/session-intelligence/search`) |
| Pagination | offset/limit |

Note: the path `/api/v1/sessions/search` must be registered before `/api/v1/sessions/{session_id}`
in the router so FastAPI does not interpret the literal string `search` as a session ID.

CLI command: `ccdash session search "<query>"`

---

#### `GET /api/v1/sessions/{session_id}/drilldown`

Concern-focused drilldown for a single session. Surfaces the specific concern dimension (e.g.
`cost`, `errors`, `tool_use`) rather than the full detail payload.

| Field | Detail |
|-------|--------|
| Parameters | `session_id` (path, required), `concern` (query, required, enum: `SessionIntelligenceConcern`) |
| Response DTO | `SessionDrilldownDTO` (new) wrapping `SessionIntelligenceDrilldownResponse` (existing) |
| Service | `SessionIntelligenceReadService.drilldown()` (existing, at `/api/analytics/session-intelligence/drilldown`) |
| Pagination | N/A |

CLI command: `ccdash session drilldown <session-id> --concern <concern>`

---

#### `GET /api/v1/sessions/{session_id}/family`

Returns all sessions that share a root session with the given session ID, enabling thread
navigation across sub-sessions spawned from a root.

| Field | Detail |
|-------|--------|
| Parameters | `session_id` (path, required) |
| Response DTO | `SessionFamilyDTO` (new) |
| Service | New service needed — `SessionFamilyQueryService` or equivalent read from sessions repository filtering on `root_session_id` |
| Pagination | N/A (family size bounded by root-session fan-out, typically small) |

`SessionFamilyDTO` fields: `root_session_id`, `session_count`, `members` (list[`SessionRef`]).

This is the only session endpoint with no existing direct backend analogue. The sessions repository
already stores `root_session_id`; the new service only needs to group by that field.

CLI command: `ccdash session family <session-id>`

---

### Workflows

#### `GET /api/v1/workflows/failures`

Workflow failure patterns and diagnostics. Reuses `WorkflowDiagnosticsQueryService`.

| Field | Detail |
|-------|--------|
| Parameters | `feature_id` (query, optional) |
| Response DTO | `WorkflowDiagnosticsDTO` (existing, wrapped in envelope) |
| Service | `WorkflowDiagnosticsQueryService.get_diagnostics()` |
| Pagination | N/A |

CLI command: `ccdash workflow failures`

---

### Reports

#### `POST /api/v1/reports/aar`

Deterministic after-action report generation for a feature. Reuses `ReportingQueryService`.

| Field | Detail |
|-------|--------|
| Request body | `{"feature_id": "<id>"}` |
| Response DTO | `AARReportDTO` (existing, wrapped in envelope) |
| Service | `ReportingQueryService.generate_aar()` |
| Pagination | N/A |

CLI command: `ccdash report aar --feature <feature-id>`

---

## Endpoint Summary Table

| Method | Path | CLI Command | Service | DTO | New? |
|--------|------|-------------|---------|-----|------|
| GET | `/api/v1/instance` | `doctor` / implicit | config.py | `InstanceMetaDTO` | Yes |
| GET | `/api/v1/project/status` | `status project` | `ProjectStatusQueryService` | `ProjectStatusDTO` | Wrapper only |
| GET | `/api/v1/features` | `feature list` | features repo | `FeatureListDTO` | Yes |
| GET | `/api/v1/features/{id}` | `feature show` | `FeatureForensicsQueryService` | `FeatureForensicsDTO` | Wrapper only |
| GET | `/api/v1/features/{id}/sessions` | `feature sessions` | features repo / forensics partial | `FeatureSessionsDTO` | Yes |
| GET | `/api/v1/features/{id}/documents` | `feature documents` | forensics partial / links repo | `FeatureDocumentsDTO` | Yes |
| GET | `/api/v1/sessions` | `session list` | `SessionIntelligenceReadService` | `SessionListDTO` | Wrapper only |
| GET | `/api/v1/sessions/search` | `session search` | `TranscriptSearchService` | `SessionSearchDTO` | Wrapper only |
| GET | `/api/v1/sessions/{id}` | `session show` | `SessionIntelligenceReadService` | `SessionDetailDTO` | Wrapper only |
| GET | `/api/v1/sessions/{id}/drilldown` | `session drilldown` | `SessionIntelligenceReadService` | `SessionDrilldownDTO` | Wrapper only |
| GET | `/api/v1/sessions/{id}/family` | `session family` | `SessionFamilyQueryService` | `SessionFamilyDTO` | Yes (service too) |
| GET | `/api/v1/workflows/failures` | `workflow failures` | `WorkflowDiagnosticsQueryService` | `WorkflowDiagnosticsDTO` | Wrapper only |
| POST | `/api/v1/reports/aar` | `report aar` | `ReportingQueryService` | `AARReportDTO` | Wrapper only |

"Wrapper only" means the endpoint is a thin re-export of an existing service under the versioned
path with the standard envelope applied. No new business logic is needed.

---

## New DTOs Required

All new DTOs belong in `backend/application/services/agent_queries/models.py` or a new
`backend/routers/client_v1_models.py` if they are envelope-only. Core contract types (those that
the CLI package will import) belong in the shared contracts package
(`packages/ccdash_contracts/`).

| DTO | Location | Fields |
|-----|----------|--------|
| `InstanceMetaDTO` | `client_v1_models.py` | `instance_id`, `version`, `environment`, `db_backend`, `capabilities`, `server_time` |
| `FeatureListDTO` | `client_v1_models.py` | `features: list[FeatureSummaryDTO]`, `total`, `offset`, `limit` |
| `FeatureSummaryDTO` | shared contracts | `id`, `name`, `status`, `category`, `priority`, `total_tasks`, `completed_tasks`, `updated_at` |
| `FeatureSessionsDTO` | shared contracts | `feature_id`, `feature_slug`, `sessions: list[SessionRef]`, `total` |
| `FeatureDocumentsDTO` | shared contracts | `feature_id`, `feature_slug`, `documents: list[DocumentRef]` |
| `SessionListDTO` | `client_v1_models.py` | `sessions: list[SessionIntelligenceSummary]`, `total`, `offset`, `limit` |
| `SessionDetailDTO` | `client_v1_models.py` | thin wrapper preserving `SessionIntelligenceDetailResponse` fields |
| `SessionSearchDTO` | `client_v1_models.py` | thin wrapper preserving `SessionSemanticSearchResponse` fields |
| `SessionDrilldownDTO` | `client_v1_models.py` | thin wrapper preserving `SessionIntelligenceDrilldownResponse` fields |
| `SessionFamilyDTO` | shared contracts | `root_session_id`, `session_count`, `members: list[SessionRef]` |

---

## New Services Required

Only one net-new service is needed. All other endpoints route through existing services.

| Service | Location | Purpose |
|---------|----------|---------|
| `SessionFamilyQueryService` | `backend/application/services/agent_queries/session_family.py` | Group sessions by `root_session_id` using the sessions repository |

---

## Deferred Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Cursor-based pagination for features | Deferred to Phase 2 | Offset/limit is sufficient for v1 feature list sizes |
| Authentication middleware on `/api/v1/` | Phase 5 | Bearer-token auth is a Phase 5 concern; v1 endpoints initially behave like the rest of the local API |
| Write endpoints | Out of scope | v1 is read-only by PRD requirement |
| Multi-project targeting in session endpoints | Deferred | `project_id` query param will be added uniformly once the project-switching model is stable |
| Federation / cross-instance aggregation | Out of scope for v1 | Instance identity metadata is included in every response to enable this later |

---

## Router Registration

The v1 router must be registered in `backend/runtime/bootstrap_local.py` (and the equivalent API
runtime bootstrap) alongside the existing routers:

```python
from backend.routers.client_v1 import client_v1_router
app.include_router(client_v1_router)
```

The router prefix is `/api/v1`, tags `["client-v1"]`.

---

## Acceptance Criteria for This Document

- [x] Every planned CLI command maps to a named endpoint or an explicit defer decision
- [x] All existing agent-query services are reused where coverage exists
- [x] New DTOs are named and assigned to a file location
- [x] The single new service (`SessionFamilyQueryService`) is identified and scoped
- [x] Pagination approach is documented per endpoint
- [x] The `/api/agent/` surface is unchanged and undisturbed
- [x] Error envelope and versioning strategy are documented
