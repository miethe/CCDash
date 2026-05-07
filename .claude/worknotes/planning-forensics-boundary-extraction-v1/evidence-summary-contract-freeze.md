---
created: 2026-05-06
feature: planning-forensics-boundary-extraction-v1
purpose: Frozen contract reference for FeatureEvidenceSummary — Phases 2 and 3 depend on this
status: frozen
phase: 1
---

# FeatureEvidenceSummary Contract (Frozen)

## DTO Fields

| Field Name | Type | Default | Notes |
|-----------|------|---------|-------|
| `status` (inherited) | `"ok" \| "partial" \| "error"` | `"ok"` | Query envelope status — not feature status |
| `data_freshness` (inherited) | `datetime` | UTC now | Timestamp of envelope creation |
| `generated_at` (inherited) | `datetime` | UTC now | Timestamp of envelope creation |
| `source_refs` (inherited) | `list[str]` | `[]` | List of [feature_id, session_id...] sources |
| `feature_id` | `str` | — | Canonical feature identifier (required) |
| `feature_slug` | `str` | `""` | URL-safe feature slug |
| `feature_status` | `str` | `""` | Feature lifecycle status (e.g., "active", "completed") |
| `name` | `str` | `""` | Human-readable feature name |
| `session_count` | `int` | `0` | Count of linked sessions |
| `total_tokens` | `int` | `0` | Aggregated tokens across all linked sessions |
| `total_cost` | `float` | `0.0` | Aggregated cost across all linked sessions |
| `token_usage_by_model` | `TokenUsageByModel` | `{}` | Token rollup by model family (opus/sonnet/haiku/other/total) |
| `workflow_mix` | `dict[str, float]` | `{}` | Normalized workflow frequency (sums to ~1.0) |
| `latest_activity` | `datetime \| None` | `None` | Most recent session end/start time |
| `telemetry_available` | `TelemetryAvailability` | `{}` | Flags: sessions/documents/tasks populated |

### Nested Models

**TokenUsageByModel:**
- `opus: int = 0`
- `sonnet: int = 0`
- `haiku: int = 0`
- `other: int = 0`
- `total: int = 0`

**TelemetryAvailability:**
- `tasks: bool = False` (always False for this service)
- `documents: bool = False` (always False for this service)
- `sessions: bool = False` (True if session_count > 0)

## REST Endpoint

**Method:** `GET`

**Path:** `/api/agent/feature-evidence-summary/{feature_id}`

**Path Parameters:**
- `feature_id` (required): Canonical feature identifier

**Query Parameters:** None

**Response Model:** `FeatureEvidenceSummary`

**Status Codes:**
- `200 OK`: Feature found and summary generated (status may be "ok" or "partial")
- `404 Not Found`: Feature not found (raised by router when service returns status="error")

**Error Behavior:** Service returns `FeatureEvidenceSummary(status="error", feature_id=..., telemetry_available=TelemetryAvailability())` when:
- Project scope cannot be resolved
- Feature row lookup fails
- The router raises `HTTPException(404)` if status == "error"

## Cache Policy

**Cache Key Prefix:** `"feature-evidence-summary"`

**Cache Key Format:** Keyed by `feature_id` parameter (project-scoped internally)

**TTL Source:** `CCDASH_QUERY_CACHE_TTL_SECONDS` (default: 600 seconds)

**Fingerprint Sources:**
- `sessions` repository version
- `entity_links` repository version
- Planning tables tracked by `get_data_version_fingerprint()`

**Invalidation:** Any session ingest or link rebuild produces a new fingerprint and causes cache miss on next call.

**Error Caching:** Error responses (status="error") are NOT cached — decorator bypasses store when fingerprint is unavailable.

## Downstream Usage Rules

- **Phase 2/3 consumers MUST** import `FeatureEvidenceSummary` from `backend.application.services.agent_queries.models`
- **Phase 2/3 consumers MUST** call `FeatureEvidenceSummaryService.get_summary()`, NOT `FeatureForensicsQueryService.get_forensics()`
- **No new fields may be added** to this DTO until Phase 4 (stabilization review)
- **Fields NOT on this DTO** remain on `FeatureForensicsDTO` only:
  - `linked_sessions` (full SessionRef enrichment)
  - `linked_documents` (DocumentRef list)
  - `linked_tasks` (TaskRef list)
  - `iteration_count`
  - `rework_signals`
  - `failure_patterns`
  - `representative_sessions`
  - `summary_narrative`
- **Telemetry availability contract:** `documents` and `tasks` are always `False` for evidence summary (by design; this service is intentionally bounded and does not fetch those)
- **Session rows:** Populated by either entity-link resolution or fallback to `SessionIntelligenceReadService.list_sessions()` for feature-scoped queries

## Design Notes

This service is intentionally **lighter than FeatureForensicsQueryService** for planning surface perf:
- No session log file opens
- No transcript-level analysis
- No document/task enrichment
- Suitable for high-frequency calls (project summary, Kanban boards)

The bounded contract is what enables Phases 2/3 to parallelize planning queries without log I/O overhead.
