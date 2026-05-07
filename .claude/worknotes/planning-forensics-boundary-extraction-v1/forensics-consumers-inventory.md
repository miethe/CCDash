---
created: 2026-05-06
purpose: Phase 0 inventory — all consumers of FeatureForensicsQueryService and the feature_forensics module
---

# Forensics Consumers Inventory

Complete inventory of every import and call site of `FeatureForensicsQueryService` (and the `feature_forensics` module) across the repo, generated as part of the planning-forensics boundary extraction refactor.

Search commands used:
```
grep -rn "FeatureForensicsQueryService\|feature_forensics" backend/
grep -rn "FeatureForensicsQueryService\|feature_forensics" packages/
```

---

## Production Consumers

| File | Line Range | Import / Call | Needs Full Forensics? | Notes |
|------|-----------|--------------|----------------------|-------|
| `backend/application/services/agent_queries/planning.py` | L44 (import), L69 (singleton), L1405–1417 (call) | `from .feature_forensics import FeatureForensicsQueryService`; `_feature_forensics_query_service = FeatureForensicsQueryService()` at module level; `await _feature_forensics_query_service.get_forensics(context, ports, feature_id)` | **Bounded summary only** | Consumes only `forensics.token_usage_by_model`, `forensics.total_tokens`, and `forensics.status`. Full transcript/session detail is never accessed. The module-level singleton is constructed at import time — tight coupling risk for refactor. |
| `backend/routers/_client_v1_features.py` | L17–20 (import), L63 (singleton), L708–727 (private `_get_forensics` wrapper), L987, L1037, L1082 (call sites) | `from backend.application.services.agent_queries import FeatureForensicsQueryService`; `_feature_forensics_query_service = FeatureForensicsQueryService()` at module level | **Mixed — varies by call site** | Three call sites with different depth needs: (1) `get_feature_detail_v1` (L987) — returns the full `FeatureForensicsDTO` to the client, needs **full forensics**. (2) `get_feature_sessions_v1` (L1037) — calls forensics only to resolve `feature_slug`; needs **bounded summary only** (slug field). (3) `get_feature_documents_v1` (L1082) — reads `forensics.linked_documents`; needs **bounded summary** (document refs, no transcripts). |
| `backend/routers/agent.py` | L12–14 (import), L62 (singleton), L111–125 (endpoint + call) | `from backend.application.services.agent_queries import FeatureForensicsQueryService`; `feature_forensics_query_service = FeatureForensicsQueryService()` at module level; `GET /api/agent/feature-forensics/{feature_id}` passes through entire `FeatureForensicsDTO` | **Full forensics** | This is the primary agent-facing REST endpoint. Returns the complete DTO — transcripts, session evidence, rework signals, token telemetry. No filtering applied. |
| `backend/mcp/tools/features.py` | L4 (import), L9 (singleton), L13–25 (tool registration + call) | `from backend.application.services.agent_queries import FeatureForensicsQueryService`; `_service = FeatureForensicsQueryService()` at module level; `ccdash_feature_forensics` MCP tool calls `_service.get_forensics(...)` and returns `build_envelope(result)` | **Full forensics** | MCP tool `ccdash_feature_forensics` exposes the complete forensics payload to MCP clients. Wraps via `build_envelope`; no field pruning occurs. |
| `backend/cli/commands/feature.py` | L6 (import), L12 (singleton), L26 (call) | `from backend.application.services.agent_queries import FeatureForensicsQueryService`; `_feature_service = FeatureForensicsQueryService()` at module level; `await _feature_service.get_forensics(context, ports, feature_id)` | **Full forensics** | CLI `feature report` command. Renders the entire `FeatureForensicsDTO` via configurable output formatter (JSON / Markdown / default). No field restriction. |

---

## Indirect / Internal Consumers

These files import private helpers from the `feature_forensics` module but do **not** instantiate or call `FeatureForensicsQueryService` directly.

| File | Line Range | Import / Call | Needs Full Forensics? | Notes |
|------|-----------|--------------|----------------------|-------|
| `backend/application/services/agent_queries/reporting.py` | L8–14 (import), L112–118 (call to helpers) | `from backend.application.services.agent_queries.feature_forensics import _document_ref_from_row, _feature_slug, _load_feature_session_rows, _session_ref_from_row, _task_ref_from_row` | **Full session rows** | `ReportingQueryService.generate_aar` calls `_load_feature_session_rows` (a private helper from `feature_forensics`) to fetch raw session data for AAR metrics. It does NOT go through `FeatureForensicsQueryService.get_forensics()` — it reuses internal helpers directly. This creates a hidden dependency on the module's private API; must be accounted for in any refactor of those helpers. |

---

## feature_surface Package

The `backend/application/services/feature_surface/` package (`__init__.py`, `dtos.py`, `list_rollup_service.py`, `modal_service.py`) contains **no direct references** to `FeatureForensicsQueryService` or the `feature_forensics` module. Confirmed by grep with zero results across all four files.

`_client_v1_features.py` uses `FeatureSurfaceListRollupService` and `FeatureModalDetailService` from this package independently alongside `FeatureForensicsQueryService`, but the feature_surface services do not themselves call into forensics.

---

## Test Consumers (not production — listed for completeness)

| File | Summary |
|------|---------|
| `backend/tests/test_agent_queries_feature_forensics.py` | Core unit tests for `FeatureForensicsQueryService.get_forensics`. Imports and instantiates the service directly. |
| `backend/tests/test_feature_forensics_aliases.py` | Alias/parity coverage for feature slug variants. Instantiates `FeatureForensicsQueryService()` per test. |
| `backend/tests/test_feature_forensics_endpoint_agreement.py` | Contract tests asserting router → service agreement. Patches `SessionTranscriptService`. |
| `backend/tests/test_agent_router.py` | Tests `agent_router.get_feature_forensics` endpoint; mocks `feature_forensics_query_service` on the router module. |
| `backend/tests/test_agent_queries_integration.py` | Integration tests; imports and calls `FeatureForensicsQueryService().get_forensics(...)` directly. |
| `backend/tests/test_agent_query_cache_invalidation.py` | Cache invalidation tests; instantiates `FeatureForensicsQueryService()` in setUp. |
| `backend/tests/test_agent_query_memoized_query.py` | Memoization tests; imports and calls service per test case. |
| `backend/tests/test_agent_query_bypass_cache.py` | Bypass-cache tests; imports `get_feature_forensics` from `backend.routers.agent`. |
| `backend/tests/test_mcp_server.py` | MCP regression tests; patches `FeatureForensicsQueryService.get_forensics`. |
| `backend/tests/test_agent_queries_shared.py` | Shared import smoke test; asserts `FeatureForensicsQueryService` is importable. |
| `backend/tests/test_repositories_bulk_fetch.py` | Imports `FeatureForensicsQueryService` for bulk-fetch fixture construction. |
| `backend/tests/test_planning_query_service.py` | Patches `backend.application.services.agent_queries.planning._feature_forensics_query_service.get_forensics` — directly targets the module-level singleton in `planning.py`. |
| `backend/tests/test_agent_queries_reporting.py` | Patches `SessionIntelligenceReadService.list_sessions` inside the `feature_forensics` module path — indirect. |
| `backend/tests/test_otel_agent_query_cache_counters.py` | OTel counter tests using the string `"feature_forensics"` as a cache key label. |
| `backend/tests/test_agent_query_cache.py` | Cache key tests using `endpoint="feature_forensics"`. |

---

## Key Findings for Refactor Planning

1. **Three module-level singletons constructed at import time**: `planning.py` (`_feature_forensics_query_service`), `_client_v1_features.py` (`_feature_forensics_query_service`), `agent.py` (`feature_forensics_query_service`), `mcp/tools/features.py` (`_service`), and `cli/commands/feature.py` (`_feature_service`). Any interface change must account for these eager-init singletons.

2. **planning.py needs only bounded summary**: The planning service reads `token_usage_by_model`, `total_tokens`, and `status`. A `ForensicsSummaryDTO` (counts + totals + confidence) would satisfy this consumer without pulling full transcript/session data.

3. **`_client_v1_features.py` has mixed depth requirements**: `get_feature_detail_v1` needs the full DTO; `get_feature_sessions_v1` needs only the slug; `get_feature_documents_v1` needs linked document refs. A bounded summary endpoint could serve two of the three call sites, with only `get_feature_detail_v1` retaining a full-forensics dependency.

4. **`reporting.py` couples to private module internals**: It imports `_load_feature_session_rows`, `_session_ref_from_row`, `_document_ref_from_row`, `_task_ref_from_row`, and `_feature_slug` directly. These private helpers must not be deleted or renamed without updating `reporting.py`.

5. **No forensics usage in `feature_surface/`**: The entire `feature_surface` package is clean — no hidden forensics dependency there.

6. **packages/ccdash_cli/**: No direct references found. The standalone CLI package communicates over HTTP and does not import the service library.
