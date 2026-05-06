---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: in-progress
category: integrations
title: "Implementation Plan: OTel Session Metrics Ingestion V1"
description: "Phased implementation plan for inbound OpenTelemetry session metrics ingestion with a reusable normalized session-ingest module."
summary: "Refactor CCDash session ingestion so local JSONL transcripts, Claude Code OTLP telemetry, and future agent platforms feed the same AgentSession, session_messages, usage attribution, analytics, and live update pipeline."
author: codex
created: 2026-05-02
updated: 2026-05-05
changelog_required: true
deferred_items_spec_refs: []
findings_doc_ref: docs/project_plans/implementation_plans/integrations/otel-session-metrics-ingestion-v1-data-coverage-matrix.md
priority: high
risk_level: high
complexity: high
track: Integrations
timeline_estimate: "4-6 weeks across 6 phases"
feature_slug: otel-session-metrics-ingestion-v1
feature_family: otel-session-metrics-ingestion
feature_version: v1
lineage_family: otel-session-metrics-ingestion
lineage_parent:
  ref: docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: integration
prd: docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
prd_ref: docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
plan_ref: otel-session-metrics-ingestion-v1
owner: platform-engineering
owners:
  - platform-engineering
  - backend-platform
  - data-platform
contributors:
  - ai-agents
audience:
  - ai-agents
  - developers
  - backend-platform
  - data-platform
tags:
  - implementation
  - opentelemetry
  - otlp
  - ingestion
  - sessions
  - claude-code
  - platform-adapters
related_documents:
  - docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
  - docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  - docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md
  - docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
  - docs/developer/session-data-discovery.md
  - docs/developer/telemetry-analytics.md
context_files:
  - backend/db/sync_engine.py
  - backend/parsers/platforms/registry.py
  - backend/models.py
  - backend/services/session_transcript_projection.py
  - backend/services/session_usage_attribution.py
  - backend/db/repositories/sessions.py
  - backend/db/repositories/session_messages.py
  - backend/application/services/sessions.py
  - backend/routers/cache.py
  - backend/observability/otel.py
  - types.ts
---

# Implementation Plan: OTel Session Metrics Ingestion V1

## Objective

Add inbound OpenTelemetry session ingestion without creating a second analytics stack. The implementation should first extract a reusable session-ingest module from the current JSONL sync path, then add a Claude Code OTel adapter that normalizes OTLP metrics/logs/traces into the same downstream contracts.

The end state is:

1. JSONL and OTel ingestion share one persistence service.
2. Existing `AgentSession`, `SessionLog`, `session_messages`, usage attribution, intelligence facts, telemetry events, and live-update behavior remain canonical.
3. OTel-derived fields carry source provenance and confidence.
4. Future platform adapters can be added without editing session UI or repository internals.

## Architecture Strategy

### New Module Boundary

Introduce a source-neutral ingestion module:

```text
backend/ingestion/
  __init__.py
  models.py                  # NormalizedSessionEnvelope, IngestResult, MergePolicy
  registry.py                # adapter registration and source lookup
  session_ingest_service.py  # shared persistence and derived pipelines
  jsonl_adapter.py           # bridge from existing parser registry
  otel/
    __init__.py
    receiver.py              # OTLP HTTP receiver/router helpers
    claude_code_adapter.py   # Claude OTel signal normalization
    privacy.py               # redaction and content policy
    temporality.py           # delta/cumulative normalization
```

If the repo prefers a service-only shape during implementation, `backend/services/ingestion/` is acceptable, but the package should still keep source adapters separate from persistence orchestration.

### Critical Refactor

Extract the persistence block currently inside `SyncEngine._sync_single_session()` into `SessionIngestService.persist_envelope()`.

That extracted service owns:

1. session upsert,
2. canonical transcript projection,
3. legacy log fallback,
4. tool/file/artifact persistence,
5. observability field derivation,
6. usage attribution replacement,
7. derived telemetry events,
8. commit correlations,
9. session intelligence facts,
10. outbound telemetry enqueue,
11. live transcript/snapshot publishing,
12. internal CCDash OTel metrics.

`SyncEngine._sync_single_session()` should retain file sync-state checks, file hash/mtime handling, parser invocation, and source cleanup, then delegate persistence to the new service.

### OTel Receiver Approach

V1 should support OTLP HTTP/protobuf endpoints first:

1. `/api/ingest/otel/v1/metrics`
2. `/api/ingest/otel/v1/logs`
3. `/api/ingest/otel/v1/traces` behind `CCDASH_OTEL_INGEST_TRACES_ENABLED`

Claude Code can target these directly with per-signal endpoint variables, or operators can run a local OTel Collector that forwards to CCDash. If direct protobuf decoding is too large for V1, land collector-compatible JSON intake as a temporary adapter only if the plan explicitly keeps the normalized service contract unchanged.

## Phase Overview

| Phase | Title | Goal | Primary Files | Status |
|---|---|---|---|---|
| 1 | Ingest Contract | Define normalized envelopes, merge policy, source provenance, and tests | `backend/ingestion/models.py`, tests | **SHIPPED** (b00d409, 044105e) |
| 2 | Shared Persistence Refactor | Extract JSONL persistence into `SessionIngestService` with no behavior change | `backend/db/sync_engine.py`, `backend/ingestion/session_ingest_service.py` | **SHIPPED** (b00d409, 4e8aea2, fce904f, 044105e, f192678) |
| 3 | Claude OTel Adapter | Normalize Claude metrics/logs/traces into partial `AgentSession` envelopes | `backend/ingestion/otel/claude_code_adapter.py` | in-progress |
| 4 | OTLP Receiver and Config | Add inbound endpoints, auth/privacy config, and receiver tests | `backend/ingestion/otel/receiver.py`, router/config | not started |
| 5 | Merge Semantics and UI/API Provenance | Merge JSONL + OTel safely and expose fidelity/provenance | repositories, service DTOs, `types.ts` | not started |
| 6 | Validation, Docs, and Rollout | E2E local Claude setup, collector examples, regression suite | docs/guides, tests | not started |

## Phase 1: Ingest Contract

**Status: SHIPPED** — contracts landed in commits b00d409 and 044105e. All tasks below are complete.

Goal: create the source-neutral contracts before moving persistence code.

Tasks:

| ID | Task | Acceptance Criteria | Owner | Status |
|---|---|---|---|---|
| P1-T1 | Add `NormalizedSessionEnvelope`, `IngestSource`, `MergePolicy`, `SourceProvenance`, and `SessionIngestResult` models. | Models support JSONL, OTel, platform type, source identity, confidence, and source timestamps. | backend-platform | done |
| P1-T2 | Define an `IngestSourceAdapter` protocol with `can_accept()` and `to_envelopes()` semantics. | JSONL and OTel adapters can implement the same protocol without import cycles. | backend-platform | done |
| P1-T3 | Add source key/idempotency helpers. | Same OTel metric/log event maps to the same source key on replay. | data-platform | done |
| P1-T4 | Add unit tests for envelope validation and source key generation. | Tests cover missing session IDs, unresolved aggregate source, and valid Claude Code source metadata. | testing | done |

Quality gate:

1. No production sync behavior changes yet.
2. Contracts are independent of FastAPI request objects and repository implementations.

## Phase 2: Shared Persistence Refactor

**Status: SHIPPED** — persistence extraction landed in b00d409; sync boundaries in 044105e; repo wiring in fce904f; JSONL sync persistence regression in 4e8aea2; ingestion source labeling in f192678. All tasks below are complete.

Goal: make JSONL ingestion use the new persistence service with equivalent behavior.

Tasks:

| ID | Task | Acceptance Criteria | Owner | Status |
|---|---|---|---|---|
| P2-T1 | Create `SessionIngestService` and move the session persistence block out of `_sync_single_session()`. | Service can persist one complete JSONL-derived envelope and returns synced session IDs, append counts, and relationship counts. | backend-platform | done |
| P2-T2 | Keep sync-state and delete-by-source responsibilities in `SyncEngine`. | Existing file mtime/hash behavior is unchanged. | backend-platform | done |
| P2-T3 | Inject or construct repositories consistently with current `SyncEngine` patterns. | SQLite and Postgres repository selection remains unchanged. | data-platform | done |
| P2-T4 | Add regression tests around JSONL sync. | Existing `test_sessions_parser`, `test_sessions_codex_parser`, session message, usage attribution, and live append tests pass. | testing | done |
| P2-T5 | Add source dimension to internal ingestion metrics. | `record_ingestion()` or equivalent can distinguish `source=jsonl` and later `source=otel`. | observability | done |

Quality gate:

1. No OTel receiver code is needed for this phase.
2. Diff should show behavior-preserving extraction first.
3. Existing frontend DTOs remain untouched.

## Phase 3: Claude OTel Adapter

Goal: normalize Claude Code OTel data into partial session envelopes.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P3-T1 | Implement Claude metric mapping for `session.count`, `token.usage`, `cost.usage`, `active_time.total`, `lines_of_code.count`, `commit.count`, `pull_request.count`, and `code_edit_tool.decision`. | (1) Adapter produces deterministic partial `AgentSession` updates and forensics summaries by `session.id`. (2) **Matrix addition — attribution AC**: Token events with `query_source='subagent'` OR `cost.usage.effort` attribute map to `sessionUsageAttribution` with `entityType='subagent'` and `method='explicit_subthread_ownership'`; analogous for `main` and `auxiliary`. (3) `start_type ∈ {fresh,resume,continue}` from `session.count` is stored in `sessionMetadata.startType` (net-new field per Matrix F). (4) `active_time.total` `type` attribute (`user`/`cli`) is preserved as `userActiveDurationSeconds` / `cliOnlyDurationSeconds` (net-new per Matrix F). (5) `code_edit_tool.decision` `source` and `language` attributes are stored in `toolSummary[]` extension (OTel-only enhancements per Matrix A). (6) `lines_of_code.count` type split (`added`/`removed`) is preserved in aggregation; JSONL file-level details take priority when available. | backend-platform |
| P3-T2 | Implement Claude log event mapping for the full set of OTel log events. | **Revised scope (matrix addition — 8 events added)**: Covers all events in the Claude Code monitoring spec: `user_prompt`, `api_request`, `api_response`, `api_error`, `api_request_body`, `api_response_body`, `tool_result`, `tool_decision`, `permission_mode_changed`, `auth`, `mcp_server_connection`, `internal_error`, `plugin_installed`, `skill_activated`, `at_mention`, `api_retries_exhausted`, `hook_execution_start`, `hook_execution_complete`, `compaction`. Net-new structures created: `sessionForensics.otel.permissionModeTransitions[]`, `sessionForensics.otel.authEvents[]`, `sessionForensics.otel.mcpConnections[]`, `sessionForensics.otel.pluginEvents[]`, `sessionForensics.otel.skillEvents[]`, `sessionForensics.otel.atMentions[]`, `sessionForensics.otel.hookEvents[]`, `sessionForensics.otel.compactionEvents[]`, `sessionForensics.otel.apiRetryHistory[]`. Events map to `SessionLog` rows or forensic entries per privacy policy. `api_response.ttft_ms` and `api_response.duration_ms` are stored in `sessionForensics.otel.apiMetrics[]` (net-new per Matrix F). `tool_decision.source` enum is stored in `sessionForensics.otel.toolDecisions[]` (net-new). | backend-platform |
| P3-T3 | Add beta trace mapping for `interaction`, `llm_request`, `tool`, `tool.blocked_on_user`, and `tool.execution` spans behind a feature flag. | **Revised scope (matrix addition — 2 spans added)**: (1) `interaction`, `llm_request`, and `tool` spans as in original plan. (2) **New**: `claude_code.tool.blocked_on_user` span maps to `sessionForensics.otel.toolWaitEvents[]` with `duration_ms`, `decision`, `source`. (3) **New**: `claude_code.tool.execution` span maps to `sessionForensics.otel.toolExecutionMetrics[]`. (4) `claude_code.hook` span requires `ENABLE_BETA_TRACING_DETAILED=1` flag for hook definition content (second beta flag — add to receiver config). (5) All trace spans remain gated behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`. Missing session.id on traces does not crash ingestion. | backend-platform |
| P3-T4 | Add privacy/redaction policy. | **Revised ACs (matrix additions)**: (1) Prompt text, tool content, raw API bodies, email, and account fields are redacted or rejected according to config. (2) **Extended-thinking content is permanently unavailable from OTel** — even with `OTEL_LOG_RAW_API_BODIES=1`; adapter must not attempt to read it, and user guide must state this explicitly. (3) `workspace.host_paths` requires PII review: paths must be normalized and optionally hashed before storage; cardinality cap per session must be documented. (4) `user.email` is hashed at ingestion time when present (one-way hash; hash strategy documented in code). (5) `user.id` (installation identifier) is always-on and is safe for anonymized sessions; must not be used as endpoint authentication identity. (6) `terminal.type` is stored as-is (medium cardinality, not PII); cardinality guidance documented. (7) Sentiment/churn/scope-drift intelligence derivation requires both `OTEL_LOG_USER_PROMPTS=1` and `OTEL_LOG_TOOL_CONTENT=1` opt-ins; without them these facts are unavailable from OTel. (8) **mTLS client cert lifecycle**: if mTLS is used (`CLAUDE_CODE_CLIENT_CERT`, `CLAUDE_CODE_CLIENT_KEY`, `CLAUDE_CODE_CLIENT_PASSPHRASE`, `NODE_EXTRA_CA_CERTS`), cert rotation, expiry handling, and fallback strategy must be documented in operational guide. | security |
| P3-T5 | Add metric temporality normalization. | Delta and cumulative metrics are idempotent for replayed export batches. `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` config var is respected by the ingester when normalizing delta vs cumulative metric streams. | data-platform |

Quality gate:

1. OTel-only fixtures produce valid `NormalizedSessionEnvelope` objects.
2. Mapping tests include Claude Code 2.1.126 `skill_activated.invocation_trigger`.
3. Missing `session.id` does not crash ingestion; unresolved facts are stored or dropped according to policy.
4. **Matrix addition**: Fixtures cover all 19 log event types; P0 events (`permission_mode_changed`, `auth`, `mcp_server_connection`, `compaction`) each have at least one happy-path test.
5. **Matrix addition**: Extended-thinking redaction is verified by test: a fixture containing extended-thinking content produces zero extended-thinking fields in stored forensics.

## Phase 4: OTLP Receiver and Config

Goal: expose an inbound endpoint that Claude Code or an OTel Collector can target.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P4-T1 | Add inbound OTel config in `backend/config.py`. | **Revised ACs (matrix additions)**: Config includes enable flag, receiver token, allowed platforms, raw retention, privacy mode, trace enablement, and max payload size. **Additionally**: (a) mTLS vars `CLAUDE_CODE_CLIENT_CERT`, `CLAUDE_CODE_CLIENT_KEY`, `CLAUDE_CODE_CLIENT_PASSPHRASE`, `NODE_EXTRA_CA_CERTS` documented for production hardening. (b) `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` (delta/cumulative preference) recognized and passed to temporality normalizer. (c) `ENABLE_BETA_TRACING_DETAILED` flag (second beta flag gating hook span definition content) added alongside existing `CCDASH_OTEL_INGEST_TRACES_ENABLED`. (d) W3C TRACEPARENT propagation semantics documented: ingester preserves TRACEPARENT header for future upstream correlation but does not require it; CLI mode ignores ambient TRACEPARENT; Agent SDK mode reads and auto-propagates. (e) Arbitrary `OTEL_RESOURCE_ATTRIBUTES` are accepted as a key-value bag and merged into envelope provenance metadata; ingester does not reject unknown resource attributes. (f) Config example must include `OTEL_SERVICE_NAME` override pattern for Agent SDK users who rename the service. (g) Per-call env override semantics (Python merges with parent env; TypeScript replaces) documented for Agent SDK operators. | backend-platform |
| P4-T2 | Add FastAPI receiver routes. | Routes accept OTLP HTTP/protobuf metrics/logs and optional traces, return OTLP-compatible success/error responses, and do not log raw bodies. | backend-platform |
| P4-T3 | Wire receiver to Claude OTel adapter and `SessionIngestService`. | Posting a fixture payload creates or updates a session through the shared service. | backend-platform |
| P4-T4 | Add auth/rate limits/payload limits. | Non-local receiver requires bearer token; oversized payloads are rejected before decoding. | security |
| P4-T5 | Add internal observability. | CCDash records inbound payload count, decode failures, normalized envelope count, persisted sessions, and latency by source/platform. | observability |

Quality gate:

1. Receiver can be disabled cleanly.
2. API runtime remains safe for local use; worker/topology implications are documented if receiver is API-owned.
3. Tests cover unauthorized, malformed, too-large, unsupported signal, and valid payload cases.
4. **Matrix addition**: Test confirms that a payload with `OTEL_SERVICE_NAME=support-triage-agent` (Agent SDK rename) is accepted and stored with the custom service name rather than "claude-code".
5. **Matrix addition**: Test confirms arbitrary `OTEL_RESOURCE_ATTRIBUTES` key-value pairs (e.g., `tenant.id=acme-corp`, `enduser.id=user-123`) are preserved in envelope provenance metadata without causing ingestion errors.

## Phase 5: Merge Semantics and Provenance

Goal: make OTel additive to JSONL forensics without corrupting richer transcript data.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P5-T1 | Implement merge policy in `SessionIngestService`. | `patch_metrics` updates metrics/forensics without deleting JSONL source rows; `upsert_complete` preserves current JSONL behavior. TRACEPARENT is preserved in envelope metadata for future upstream correlation but not required for merge. | data-platform |
| P5-T2 | Add provenance fields to `sessionForensics.otel`. | Session detail shows OTel source, app version, resource attributes policy, last received signal, confidence, and unresolved counts. **Matrix addition — prompt.id correlation**: New optional field `session_messages.otel_prompt_id` (UUID per user turn) is added to the `session_messages` schema to enable OTel-native message deduplication and ordering when both JSONL and OTel report the same turn. Field is nullable; FE handles missing `otel_prompt_id` as safe fallback (no UI regression). Deduplication strategy: strict UUID match when available; time-window heuristic documented as deferred (see Deferred Items). | backend-platform |
| P5-T3 | Preserve canonical transcript priority. | JSONL/canonical `session_messages` are not replaced by metrics-only OTel data. JSONL-only fields explicitly enumerated in Matrix E are enforced as JSONL-canonical: `parentUuid`/`uuid` entry tree, fork fields (`forkParentSessionId`, `forkPointEntryUuid`, `forkDepth`, `forkCount`), `threadKind`, `subagentThread`, `displayAgentType`, extended-thinking content, `platformVersionTransitions[]`, sidecars (`todos`, `tasks`, `teams`), `phaseHints[]`, `taskHints[]`, sentiment/churn/scope-drift facts, Codex platform sessions, `gitAuthor`, `gitBranch`, `recalculatedCostUsd`, `relayMirrorUsage`. Fork ancestry must be verified JSONL-first; OTel must not override. | data-platform |
| P5-T4 | Add frontend type support for source/fidelity labels only where needed. | Missing provenance fields are safe fallbacks; no UI regression for older sessions. New optional fields from Matrix F (`userActiveDurationSeconds`, `cliOnlyDurationSeconds`, `sessionMetadata.startType`, `sessionForensics.otel.ttftMs`) each have an explicit FE fallback AC per R-P2: "FE handles missing X gracefully when field is absent." | frontend |
| P5-T5 | Add API filters/facets for source/platform when useful. | **Revised AC (matrix critical fix)**: Facet logic MUST NOT hardcode `service.name == "claude-code"`. Use `service.name` as-is from resource attributes. When Agent SDK overrides `OTEL_SERVICE_NAME` (e.g., "support-triage-agent"), faceting must still group correctly. Regression test: Agent SDK override of `OTEL_SERVICE_NAME` does not break platform facets or session grouping. Facet logic should also group/filter by `enduser.id` and `tenant.id` resource attributes when present. | backend-platform |

Quality gate:

1. Same session ingested from JSONL then OTel remains one session.
2. Same session ingested from OTel then JSONL upgrades transcript fidelity.
3. Replayed OTel batches do not double count tokens/cost.
4. **Matrix addition — R-P2 gate**: Every new optional backend field introduced in this phase has a corresponding FE fallback AC. Verify before marking phase complete.
5. **Matrix addition — service.name gate**: Regression test with custom `OTEL_SERVICE_NAME` passes before phase complete.

## Phase 6: Validation, Documentation, and Rollout

Goal: make the feature operable and safe to enable.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P6-T1 | Add Claude Code setup guide. | **Revised ACs (matrix additions)**: (1) Docs include direct endpoint and OTel Collector examples with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, metrics/log exporters, endpoint variables, and privacy warnings. (2) **Extended-thinking caveat**: Guide explicitly states that extended-thinking content is permanently unavailable from OTel — even with `OTEL_LOG_RAW_API_BODIES=1` — and is only available via JSONL transcripts. (3) **Optional Intelligence Signals section**: Guide documents that sentiment/churn/scope-drift intelligence facts require both `OTEL_LOG_USER_PROMPTS=1` and `OTEL_LOG_TOOL_CONTENT=1` opt-ins; without both, these facts remain unavailable from OTel and are not populated in analytics. Marked as optional enrichments, not required for session ingestion. (4) **mTLS production hardening**: Guide covers cert/key variables (`CLAUDE_CODE_CLIENT_CERT`, `CLAUDE_CODE_CLIENT_KEY`), rotation, and fallback for production deployments. (5) **Agent SDK section**: Guide shows `OTEL_SERVICE_NAME` override pattern and per-call env semantics (Python merge vs TypeScript replace). (6) **`session.id` prominence**: Guide emphasizes that without `OTEL_METRICS_INCLUDE_SESSION_ID=true`, session-level forensics quality drops sharply; include as a required configuration step. | docs |
| P6-T2 | Add fixture corpus. | **Revised ACs (matrix additions)**: Fixtures cover metrics-only, logs-only, metrics+logs, beta traces, missing session ID, sensitive content, and replay. **Additionally**: fixture for each of the 8 net-new log event types added in P3-T2 (`permission_mode_changed`, `auth`, `mcp_server_connection`, `compaction`, `plugin_installed`, `skill_activated`, `at_mention`, `hook_execution_start`/`complete`). Fixture for Agent SDK `OTEL_SERVICE_NAME` override. Fixture with `OTEL_RESOURCE_ATTRIBUTES` injection (`tenant.id`, `enduser.id`). Fixture with extended-thinking content in raw body (to verify redaction). | testing |
| P6-T3 | Add E2E local smoke script or test. | A sample OTLP payload creates a visible session and can be queried through `/api/sessions`. | testing |
| P6-T4 | Update developer docs for adapter authors. | New platform adapter guidance explains how future Codex/other OTel sources implement the registry. Codex platform sessions are documented as out of scope for this V1 (Codex emits separate logs; OTel is Claude Code telemetry only). | docs |
| P6-T5 | Rollout behind feature flag. | Default remains disabled until config is present; release notes explain how to enable. | platform-engineering |

Quality gate:

1. Full backend regression suite for sessions, session messages, usage attribution, analytics, and cache sync passes.
2. Frontend typecheck/build passes if frontend fields changed.
3. Manual direct or collector-forwarded Claude Code telemetry run is documented with exact observed result.
4. **Matrix addition**: Fixture corpus covers all 19 log event types with at least one test per event type.
5. **Matrix addition**: User guide reviewed for extended-thinking caveat and Optional Intelligence Signals section before merge.

## Test Plan

Required tests:

1. `backend/tests/test_session_ingest_service.py`
2. `backend/tests/test_otel_claude_adapter.py`
3. `backend/tests/test_otel_receiver.py`
4. JSONL regression tests for Claude Code and Codex parser paths.
5. Merge tests for JSONL then OTel, OTel then JSONL, and replayed OTel.
6. Privacy tests for prompts, tool inputs, raw API bodies, email/account attributes, and unknown attributes.
7. API tests proving `/api/sessions` and `/api/v1/sessions` still return compatible DTOs.

Matrix-driven additions to test coverage:

8. **service.name facet regression**: Agent SDK `OTEL_SERVICE_NAME` override (e.g., "support-triage-agent") does not break platform facet grouping or session queries.
9. **OTEL_RESOURCE_ATTRIBUTES injection**: Arbitrary resource attrs (`tenant.id`, `enduser.id`) preserved in envelope provenance without ingestion errors.
10. **All 19 log event types**: At least one happy-path test per event, with P0 events (`permission_mode_changed`, `auth`, `mcp_server_connection`, `compaction`) having both happy-path and missing-field tests.
11. **Extended-thinking redaction**: Fixture with extended-thinking content in raw body produces zero extended-thinking fields in stored forensics.
12. **prompt.id correlation**: When `otel_prompt_id` is present on a `session_messages` row, deduplication logic produces one row per user turn (not two) when both JSONL and OTel report the same turn.
13. **Token attribution AC**: `claude_code.token.usage` with `query_source=subagent` correctly creates `sessionUsageAttribution` with `entityType=subagent` and `method=explicit_subthread_ownership`.
14. **Trace sub-span coverage**: `tool.blocked_on_user` and `tool.execution` spans (behind beta flag) map to `toolWaitEvents[]` and `toolExecutionMetrics[]` respectively.
15. **Temporality normalization**: Replayed cumulative metric export (same data sent twice) does not double-count tokens or cost.

Suggested fixture layout:

```text
backend/tests/fixtures/otel/claude_code/
  metrics_session_usage_v2_1_126.json
  metrics_token_attribution_subagent_query_source.json
  logs_skill_at_mention_compaction_v2_1_126.json
  logs_permission_mode_changed.json
  logs_auth_event.json
  logs_mcp_server_connection.json
  logs_hook_execution_start_complete.json
  logs_plugin_installed.json
  traces_interaction_beta_v2_1_126.json
  traces_tool_blocked_on_user_beta.json
  traces_tool_execution_beta.json
  sensitive_payload_redaction.json
  sensitive_extended_thinking_redaction.json
  missing_session_id_unresolved.json
  agent_sdk_service_name_override.json
  resource_attributes_tenant_enduser_injection.json
  replay_cumulative_temporality.json
```

## Implementation Notes

1. Do not reuse outbound `backend/services/telemetry_transformer.py` for inbound OTel. Its job is anonymized export, not source ingestion.
2. Keep OTel raw attribute names in bounded provenance so future schema changes are diagnosable.
3. Treat Claude Code traces as beta because the official docs mark tracing as beta and span attributes may change. Detailed hook span definitions require a second beta flag `ENABLE_BETA_TRACING_DETAILED=1`.
4. Prefer resource/service attributes for platform identification, but trust metric/event names for Claude mapping.
5. Make `session.id` inclusion explicit in docs; without it, session-level forensics quality drops sharply.
6. **Matrix addition**: Never hardcode `service.name == "claude-code"` in facet queries or aggregation. Agent SDK users regularly rename this attribute.
7. **Matrix addition**: No separate SDK telemetry adapter is required. The Agent SDK emits identical OTel signals through the Claude Code CLI subprocess; P3 adapter logic applies to both.
8. **Matrix addition**: JSONL-only fields (fork graph, extended-thinking, sentiment/churn facts, Codex sessions, git context, relay mirror usage) are documented in Matrix E of the coverage matrix. These fields will never be supplied by OTel and must remain JSONL-canonical indefinitely.

## Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| **service.name facet breakage for Agent SDK users** | High | P5-T5 AC explicitly prohibits hardcoded `service.name == "claude-code"`. Regression test with override required before phase complete. |
| **8 missing log event types in P3-T2 scope** | High | P3-T2 revised to cover all 19 log events. Fixture corpus expanded accordingly. Missing any P0 event (`permission_mode_changed`, `auth`, `mcp_server_connection`, `compaction`) blocks P3 quality gate. |
| **Extended-thinking content false expectation** | Medium | P3-T4 and P6-T1 both document the permanent redaction. Test verifies no extended-thinking fields appear in stored forensics. |
| **prompt.id deduplication strategy undefined** | Medium | P5-T2 implements strict UUID match for now. Time-window heuristic deferred (see Deferred Items). Undefined behavior documented: if JSONL and OTel both arrive for the same turn without matching UUID, they are treated as distinct rows. |
| **mTLS cert expiry in production** | Low | P3-T4 and P6-T1 document cert rotation guidance. Operational risk only; ingester falls back to no-mTLS on cert load failure (behavior must be verified). |
| **Beta trace span stability** | Low | Trace spans are gated behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`; upstream docs explicitly mark as unstable. Adapter tests use version-pinned fixtures and must be updated when upstream schema changes. |
| **Tenant/org scoping not designed** | Low | `tenant.id` and `organization.id` from resource attrs are preserved as forensic metadata bags in V1. Top-level scoping construct deferred (see Deferred Items). |

## Operational Setup Example

Direct Claude Code to CCDash once receiver routes exist:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:8000/api/ingest/otel/v1/metrics
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:8000/api/ingest/otel/v1/logs
export OTEL_METRICS_INCLUDE_SESSION_ID=true
claude
```

Optional trace setup:

```bash
export CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:8000/api/ingest/otel/v1/traces
```

Content-bearing variables such as `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, and `OTEL_LOG_RAW_API_BODIES` must stay off unless the operator explicitly approves storage of that data.

## Deferred Items & In-Flight Findings Policy

The following items are surfaced by the data coverage matrix (OQ markers from Matrix §12) and are explicitly deferred from V1 scope. Each requires a design-spec authoring task before V2 implementation.

| ID | Item | Matrix Source | Rationale for Deferral | Design Spec Required |
|---|---|---|---|---|
| DEFER-001 | `prompt.id` time-window deduplication heuristic | Matrix §12 OQ-1; P5-T2 | V1 implements strict UUID match. Time-window heuristic requires empirical analysis of JSONL/OTel arrival timing distributions. Premature optimization. | Yes — design spec for cross-source message deduplication strategy |
| DEFER-002 | `user.email` hash strategy and salt | Matrix §12 OQ-2 | One-way hash at ingestion is implemented in V1. Global lookup table (cross-session email tracking) requires privacy review and policy decision beyond ingestion scope. | Yes — design spec for PII hash lifecycle and cross-session identity linking |
| DEFER-003 | Tenant/organization top-level scoping construct | Matrix §12 OQ-3 | `tenant.id` and `organization.id` are preserved as forensic metadata bags in V1. Top-level `organizationId` on AgentSession requires multi-tenant query isolation design. | Yes — design spec for multi-tenant session scoping and query isolation |
| DEFER-004 | Workspace path retention policy | Matrix §12 OQ-4 | `workspace.host_paths` is hashed in V1 per P3-T4. Normalization strategy, cardinality cap, and retention window require policy decision. | Yes — design spec for workspace path PII lifecycle |
| DEFER-005 | TRACEPARENT upstream correlation | Matrix §12 OQ-5 | TRACEPARENT is preserved in V1 but not forwarded. Integration with Honeycomb/Datadog requires operator demand validation before building. | No — evaluate demand; create design spec only if prioritized |
| DEFER-006 | Extended-thinking conditional availability | Matrix §12 OQ-6 | Permanent OTel redaction is hard constraint from Claude Code. Any future conditional availability requires upstream API change, not CCDash changes. | No — upstream constraint; document in architecture notes |
| DEFER-007 | Raw API body external object store (`api_request_body`/`api_response_body`) | Matrix B, §9 Matrix F | V1 rejects raw body opt-in storage. S3/GCS/local object store adapter required for full untruncated body support. High effort; privacy-gated. | Yes — design spec for external body store integration and privacy contract |

**DOC-006 design-spec tasks**: Items DEFER-001 through DEFER-005 and DEFER-007 each require a `design_spec` authored at `docs/project_plans/design-specs/otel-ingestion-[topic].md` before V2 planning begins. DEFER-006 is upstream-blocked and requires no local design spec.
