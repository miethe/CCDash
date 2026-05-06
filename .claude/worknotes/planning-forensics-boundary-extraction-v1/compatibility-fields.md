---
created: 2026-05-06
purpose: Compatibility field catalogue for the planning-forensics boundary extraction refactor
status: authoritative
---

# Compatibility Fields — Planning-Forensics Boundary Extraction

This document catalogues every field on `FeatureForensicsDTO` (and its nested types), classifies each by consumer scope, identifies the CLI v1 contract surface, and maps which fields move to the new bounded `FeatureEvidenceSummary`.

Source files examined:
- `backend/application/services/agent_queries/models.py` — canonical DTO definitions
- `backend/application/services/agent_queries/feature_forensics.py` — assembly service
- `backend/application/services/feature_surface/dtos.py` — feature surface DTOs
- `backend/routers/_client_v1_features.py` — v1 client API surface
- `backend/routers/client_v1_models.py` — v1 envelope and compat models
- `.claude/worknotes/planning-forensics-boundary-extraction-v1/forensics-consumers-inventory.md` — consumer inventory

---

## 1. FeatureForensicsDTO Field Table

`FeatureForensicsDTO` extends `AgentQueryEnvelope`. Envelope base fields are listed first, then DTO-own fields. Nested types (`SessionRef`, `DocumentRef`, `TaskRef`, `TokenUsageByModel`, `TelemetryAvailability`) are expanded in Section 2.

| Field | Type | Consumers | Classification | Notes |
|-------|------|-----------|----------------|-------|
| **Envelope base — AgentQueryEnvelope** | | | | |
| `status` | `"ok" \| "partial" \| "error"` | `planning.py` (L1415), `_client_v1_features.py` `_get_forensics` (L726), `agent.py` passthrough, MCP passthrough, CLI passthrough | **Stable** | `planning.py` reads this to gate planning logic. `_get_forensics` raises 404 when `status == "error"`. Must remain present and honour the ok/partial/error enum. |
| `data_freshness` | `datetime` | `agent.py` passthrough, MCP passthrough, CLI passthrough | Internal | Not read by any named consumer logic; included in full-passthrough outputs. Can be moved or renamed freely as long as full-forensics paths are updated together. |
| `generated_at` | `datetime` | Same full-passthrough consumers | Internal | Same as `data_freshness`. |
| `source_refs` | `list[str]` | Same full-passthrough consumers | Internal | Diagnostic provenance field. No consumer reads individual entries. |
| **DTO-own fields** | | | | |
| `feature_id` | `str` | All consumers (key identifier) | **Stable** | Primary lookup key. Present in every response envelope. Must not be removed or renamed. |
| `feature_slug` | `str` | `_client_v1_features.py` `_get_forensics` return (L727), `get_feature_sessions_v1` (L1037), `get_feature_documents_v1` (L1082) | **Stable** | Used to build `FeatureSessionsDTO.feature_slug` and `FeatureDocumentsDTO.feature_slug`. These are CLI v1 contract fields. Must remain on any bounded summary. |
| `feature_status` | `str` | `agent.py` passthrough, MCP passthrough, CLI passthrough | Internal | Lifecycle status of the feature row itself. Not directly read by planning or v1 session/document paths. Can be sourced from the bounded summary. |
| `name` | `str` | All full-passthrough consumers | Internal | Display name. Error-path returns use it as fallback. Refactorable so long as full-forensics paths carry it. |
| `telemetry_available` | `TelemetryAvailability` | All full-passthrough consumers | Internal | Data-presence indicator. Not read by planning or v1 compat paths. |
| `linked_sessions` | `list[SessionRef]` | `agent.py` passthrough, MCP passthrough, CLI passthrough | **Stable** | Primary evidence list. Referenced in docstring as "single authoritative session list for a feature". Must remain intact for full-forensics consumers. The v1 sessions path no longer reads from this field directly (it now calls `FeatureModalDetailService`), but CLI `feature report` renders the complete DTO including this field. |
| `linked_documents` | `list[DocumentRef]` | `get_feature_documents_v1` (L1088) reads `forensics.linked_documents` directly | **Stable** | The v1 documents endpoint reads this field explicitly. Must remain on any response object returned by `_get_forensics`. Migration candidate for bounded summary only once `get_feature_documents_v1` is updated to call a bounded-summary path instead. |
| `linked_tasks` | `list[TaskRef]` | `agent.py` passthrough, MCP passthrough, CLI passthrough | Internal | Not read by any v1 compat path. Can be sourced from bounded summary. |
| `iteration_count` | `int` | Same full-passthrough consumers | Internal | Derived count (`len(session_refs)`). Not read individually by compat paths. |
| `total_cost` | `float` | Same full-passthrough consumers | Internal | Aggregate cost. Not read by planning or compat paths. |
| `total_tokens` | `int` | `planning.py` (L1416) | **Stable** | Read by `planning.py` for planning telemetry. Must be present on the new `FeatureEvidenceSummary`. |
| `token_usage_by_model` | `TokenUsageByModel` | `planning.py` (L1415) | **Stable** | Read by `planning.py` for per-model token attribution. Must be present on the new `FeatureEvidenceSummary`. |
| `workflow_mix` | `dict[str, float]` | Same full-passthrough consumers | Internal | Not read by planning or compat paths individually. |
| `rework_signals` | `list[str]` | Same full-passthrough consumers | Internal | Signal labels only used in full-forensics outputs. |
| `failure_patterns` | `list[str]` | Same full-passthrough consumers | Internal | Same as `rework_signals`. |
| `representative_sessions` | `list[SessionRef]` | Same full-passthrough consumers | Internal | Top-3 ranked session refs; full-forensics output only. |
| `summary_narrative` | `str` | Same full-passthrough consumers | Internal | Human-readable string; full-forensics output only. |
| `sessions_note` | `str` | Same full-passthrough consumers | Internal | Static advisory string; no consumer reads or routes on this value. |

---

## 2. Nested Type Field Tables

### SessionRef (extends SessionSummary)

| Field | Type | Classification | Notes |
|-------|------|----------------|-------|
| `session_id` | `str` | **Stable** | Required key on `SessionSummary`. Present in `FeatureSessionsDTO.sessions` items. |
| `feature_id` | `str` | **Stable** | Populated by `_session_row_to_session_ref` in the v1 sessions path. |
| `root_session_id` | `str` | Internal | Used in session thread grouping; not read by planning. |
| `title` | `str` | Internal | Display field. |
| `status` | `str` | Internal | Per-session status; not routed on by planning. |
| `started_at` | `str` | Internal | Timestamp. |
| `ended_at` | `str` | Internal | Timestamp. |
| `model` | `str` | Internal | Used in `_aggregate_token_usage_by_model` derivation but not directly exposed to planning. |
| `total_cost` | `float` | Internal | Contributes to `FeatureForensicsDTO.total_cost` aggregation. |
| `total_tokens` | `int` | Internal | Contributes to `FeatureForensicsDTO.total_tokens` aggregation; planning reads the aggregate, not the per-session value. |
| `workflow_refs` | `list[str]` | Internal | Used for `workflow_mix` derivation. |
| `duration_seconds` | `float` | Internal | Used for rework-signal detection (`long_running_session`). |
| `tool_names` | `list[str]` | Internal | Extracted from transcript logs; full-forensics only. |
| `source_ref` | `str` | Internal | Provenance tag. |

### DocumentRef

| Field | Type | Classification | Notes |
|-------|------|----------------|-------|
| `document_id` | `str` | **Stable** | Key field in `FeatureDocumentsDTO.documents`. |
| `title` | `str` | **Stable** | Consumed by `get_feature_documents_v1` passthrough. |
| `file_path` | `str` | **Stable** | Included in v1 documents response. |
| `canonical_path` | `str` | Internal | Normalised path; used internally. |
| `doc_type` | `str` | **Stable** | Included in v1 documents response. |
| `status` | `str` | **Stable** | Included in v1 documents response. |
| `updated_at` | `str` | Internal | Timestamp; not contractually required downstream. |
| `feature_slug` | `str` | Internal | Denormalised slug; not read by v1 documents consumers. |

### TaskRef

| Field | Type | Classification | Notes |
|-------|------|----------------|-------|
| `task_id` | `str` | Internal | No v1 compat path reads task refs. |
| `title` | `str` | Internal | Full-forensics display field. |
| `status` | `str` | Internal | Full-forensics display field. |
| `priority` | `str` | Internal | Full-forensics display field. |
| `owner` | `str` | Internal | Full-forensics display field. |
| `phase_id` | `str` | Internal | Full-forensics display field. |
| `updated_at` | `str` | Internal | Timestamp. |

### TokenUsageByModel

| Field | Type | Classification | Notes |
|-------|------|----------------|-------|
| `opus` | `int` | **Stable** | Read by `planning.py` via `forensics.token_usage_by_model`. |
| `sonnet` | `int` | **Stable** | Same. |
| `haiku` | `int` | **Stable** | Same. |
| `other` | `int` | **Stable** | Same. |
| `total` | `int` | **Stable** | Same; also mirrors `FeatureForensicsDTO.total_tokens`. |

### TelemetryAvailability

| Field | Type | Classification | Notes |
|-------|------|----------------|-------|
| `tasks` | `bool` | Internal | Data-presence flag; not read by planning or v1 compat. |
| `documents` | `bool` | Internal | Same. |
| `sessions` | `bool` | Internal | Same. |

---

## 3. CLI v1 Contract

The following response shapes are exposed by `_client_v1_features.py` and re-exported via `packages/ccdash_contracts/`. These constitute the external CLI compatibility contract. Field shapes **must not change** without a versioned migration.

### GET /api/v1/features/{feature_id} → `ClientV1Envelope[FeatureForensicsDTO]`

The entire `FeatureForensicsDTO` is the data payload. Every field in Section 1 is part of this response. Effectively all fields are externally visible, but the ones listed as **Stable** above are the ones that existing consumers actively read or route on.

Key fields explicitly read by `get_feature_detail_v1` call chain:
- `status` — gates the 404 error path in `_get_forensics`
- `feature_slug` — returned as the second element of the `_get_forensics` tuple; used in downstream compat DTOs

### GET /api/v1/features/{feature_id}/sessions → `ClientV1Envelope[FeatureSessionsDTO]`

```
FeatureSessionsDTO:
  feature_id:   str
  feature_slug: str          ← sourced from _get_forensics() when bypass_cache=False
  sessions:     list[SessionRef]
  total:        int
```

The `feature_slug` on this DTO is the only field sourced from `FeatureForensicsDTO` today. All session rows come from `FeatureModalDetailService`. This path can move to a bounded summary (needing only `feature_slug`) without touching the `sessions` data assembly.

### GET /api/v1/features/{feature_id}/documents → `ClientV1Envelope[FeatureDocumentsDTO]`

```
FeatureDocumentsDTO:
  feature_id:   str
  feature_slug: str          ← sourced from _get_forensics() return tuple
  documents:    list[DocumentRef]
```

`documents` is read directly from `forensics.linked_documents`. This is the only v1 compat path that still reads a list-typed evidence field from the full forensics DTO. This path is a **migration candidate** once `linked_documents` is available on the bounded summary.

### GET /api/v1/features (summary view) → `ClientV1PaginatedEnvelope[FeatureSummaryDTO]`

No forensics dependency. Served entirely from the feature repository.

### GET /api/v1/features (cards view) → `ClientV1Envelope[FeatureCardPageResponseDTO]`

No forensics dependency. Served by `FeatureSurfaceListRollupService`.

### POST /api/v1/features/rollups → `ClientV1Envelope[FeatureRollupResponseDTO]`

No forensics dependency. Served by `FeatureSurfaceListRollupService`.

### GET /api/v1/features/{feature_id}/modal → `ClientV1Envelope[FeatureModalOverviewDTO]`

No forensics dependency. Served by `FeatureModalDetailService` + `FeatureSurfaceListRollupService`.

### GET /api/v1/features/{feature_id}/modal/{section} → `ClientV1Envelope[FeatureModalSectionDTO]`

No forensics dependency. Served by `FeatureModalDetailService`.

### GET /api/v1/features/{feature_id}/sessions/page → `ClientV1Envelope[LinkedFeatureSessionPageDTO]`

No forensics dependency. Served entirely by `FeatureModalDetailService`.

---

## 4. Fields That planning.py Reads

The `planning.py` consumer (L1405–1417) reads exactly three fields after calling `get_forensics`:

| Field | Type | Present on Full DTO | Must Be on FeatureEvidenceSummary |
|-------|------|--------------------|------------------------------------|
| `token_usage_by_model` | `TokenUsageByModel` | Yes (`feature_forensics.py` L366) | **Yes** |
| `total_tokens` | `int` | Yes (`feature_forensics.py` L308) | **Yes** |
| `status` | `"ok" \| "partial" \| "error"` | Yes (envelope base) | **Yes** — gates downstream planning logic |

`planning.py` never reads `linked_sessions`, `linked_documents`, `linked_tasks`, transcript data, `rework_signals`, `failure_patterns`, `workflow_mix`, `representative_sessions`, or `summary_narrative`. A `FeatureEvidenceSummary` that carries only these three fields (plus `feature_id` and `feature_slug` for routing) is sufficient to satisfy this consumer.

---

## 5. Migration Plan

### Phase A — Introduce FeatureEvidenceSummary (no breaking changes)

Create a new bounded DTO alongside the existing `FeatureForensicsDTO`:

```python
class FeatureEvidenceSummary(AgentQueryEnvelope):
    """Lightweight summary for consumers that do not need full transcript evidence."""
    feature_id: str
    feature_slug: str = ""
    feature_status: str = ""
    total_tokens: int = 0
    total_cost: float = 0.0
    token_usage_by_model: TokenUsageByModel = Field(default_factory=TokenUsageByModel)
    linked_doc_count: int = 0
    linked_session_count: int = 0
    linked_task_count: int = 0
    linked_documents: list[DocumentRef] = Field(default_factory=list)
    # status and data_freshness inherited from AgentQueryEnvelope
```

This covers all three fields `planning.py` needs, plus `feature_slug` for v1 compat paths, plus `linked_documents` to unblock `get_feature_documents_v1` migration.

### Phase B — Migrate planning.py

Replace `FeatureForensicsQueryService` with a new `FeatureEvidenceSummaryService` (or an overloaded method returning `FeatureEvidenceSummary`). The module-level singleton in `planning.py` is constructed at import time — update the singleton type and call site together.

Test coverage: `backend/tests/test_planning_query_service.py` patches the singleton directly; update the patch target when the singleton type changes.

### Phase C — Migrate two v1 compat paths

| Endpoint | Current forensics field read | New source |
|----------|------------------------------|------------|
| `get_feature_sessions_v1` | `feature_slug` (for slug resolution) | `FeatureEvidenceSummary.feature_slug` |
| `get_feature_documents_v1` | `feature_slug` + `linked_documents` | `FeatureEvidenceSummary.feature_slug` + `FeatureEvidenceSummary.linked_documents` |

After Phase C, `_get_forensics` is called only by `get_feature_detail_v1`. All other call sites in `_client_v1_features.py` use the bounded summary.

### Phase D — Full forensics isolation

`FeatureForensicsQueryService.get_forensics` (full transcript enrichment via `_enrich_session_refs`) remains in place to serve:
- `GET /api/agent/feature-forensics/{feature_id}` (`agent.py`)
- MCP tool `ccdash_feature_forensics` (`mcp/tools/features.py`)
- CLI `feature report` (`cli/commands/feature.py`)
- `GET /api/v1/features/{feature_id}` (`get_feature_detail_v1`)

These four consumers require the complete evidence payload and must not be migrated to the bounded summary.

### Phase E — reporting.py private helper dependency

`reporting.py` imports five private helpers from `feature_forensics.py`:
- `_document_ref_from_row`
- `_feature_slug`
- `_load_feature_session_rows`
- `_session_ref_from_row`
- `_task_ref_from_row`

These must be promoted to a shared internal utility module (e.g., `agent_queries/_row_helpers.py`) before the `feature_forensics` module is refactored. Do not delete or rename these helpers until `reporting.py` is updated. This is a hidden seam that must be treated as a named deliverable.

### Fields that remain on FeatureForensicsDTO indefinitely (not migrated)

The following fields have no migration candidate because they are structural to the full forensics contract:

- `linked_sessions` (list with enriched `SessionRef` including `tool_names`, `workflow_refs`)
- `representative_sessions`
- `rework_signals`
- `failure_patterns`
- `workflow_mix`
- `summary_narrative`
- `sessions_note`
- `iteration_count`
- `telemetry_available`
