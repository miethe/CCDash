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

| Phase | Title | Goal | Primary Files |
|---|---|---|---|
| 1 | Ingest Contract | Define normalized envelopes, merge policy, source provenance, and tests | `backend/ingestion/models.py`, tests |
| 2 | Shared Persistence Refactor | Extract JSONL persistence into `SessionIngestService` with no behavior change | `backend/db/sync_engine.py`, `backend/ingestion/session_ingest_service.py` |
| 3 | Claude OTel Adapter | Normalize Claude metrics/logs into partial `AgentSession` envelopes | `backend/ingestion/otel/claude_code_adapter.py` |
| 4 | OTLP Receiver and Config | Add inbound endpoints, auth/privacy config, and receiver tests | `backend/ingestion/otel/receiver.py`, router/config |
| 5 | Merge Semantics and UI/API Provenance | Merge JSONL + OTel safely and expose fidelity/provenance | repositories, service DTOs, `types.ts` |
| 6 | Validation, Docs, and Rollout | E2E local Claude setup, collector examples, regression suite | docs/guides, tests |

## Phase 1: Ingest Contract

Goal: create the source-neutral contracts before moving persistence code.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P1-T1 | Add `NormalizedSessionEnvelope`, `IngestSource`, `MergePolicy`, `SourceProvenance`, and `SessionIngestResult` models. | Models support JSONL, OTel, platform type, source identity, confidence, and source timestamps. | backend-platform |
| P1-T2 | Define an `IngestSourceAdapter` protocol with `can_accept()` and `to_envelopes()` semantics. | JSONL and OTel adapters can implement the same protocol without import cycles. | backend-platform |
| P1-T3 | Add source key/idempotency helpers. | Same OTel metric/log event maps to the same source key on replay. | data-platform |
| P1-T4 | Add unit tests for envelope validation and source key generation. | Tests cover missing session IDs, unresolved aggregate source, and valid Claude Code source metadata. | testing |

Quality gate:

1. No production sync behavior changes yet.
2. Contracts are independent of FastAPI request objects and repository implementations.

## Phase 2: Shared Persistence Refactor

Goal: make JSONL ingestion use the new persistence service with equivalent behavior.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P2-T1 | Create `SessionIngestService` and move the session persistence block out of `_sync_single_session()`. | Service can persist one complete JSONL-derived envelope and returns synced session IDs, append counts, and relationship counts. | backend-platform |
| P2-T2 | Keep sync-state and delete-by-source responsibilities in `SyncEngine`. | Existing file mtime/hash behavior is unchanged. | backend-platform |
| P2-T3 | Inject or construct repositories consistently with current `SyncEngine` patterns. | SQLite and Postgres repository selection remains unchanged. | data-platform |
| P2-T4 | Add regression tests around JSONL sync. | Existing `test_sessions_parser`, `test_sessions_codex_parser`, session message, usage attribution, and live append tests pass. | testing |
| P2-T5 | Add source dimension to internal ingestion metrics. | `record_ingestion()` or equivalent can distinguish `source=jsonl` and later `source=otel`. | observability |

Quality gate:

1. No OTel receiver code is needed for this phase.
2. Diff should show behavior-preserving extraction first.
3. Existing frontend DTOs remain untouched.

## Phase 3: Claude OTel Adapter

Goal: normalize Claude Code OTel data into partial session envelopes.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P3-T1 | Implement Claude metric mapping for `session.count`, `token.usage`, `cost.usage`, `active_time.total`, `lines_of_code.count`, `commit.count`, `pull_request.count`, and `code_edit_tool.decision`. | Adapter produces deterministic partial `AgentSession` updates and forensics summaries by `session.id`. | backend-platform |
| P3-T2 | Implement Claude log event mapping for user prompt, tool result, API request/error, tool decision, skill activation, at-mention, hooks, and compaction. | Structural events become `SessionLog` rows or `sessionForensics.otel.events` entries based on privacy policy. | backend-platform |
| P3-T3 | Add beta trace mapping for `interaction`, `llm_request`, and tool spans behind a feature flag. | Trace spans can enrich timeline/latency facts without being required for metrics/log ingestion. | backend-platform |
| P3-T4 | Add privacy/redaction policy. | Prompt text, tool content, raw API bodies, email, and account fields are redacted or rejected according to config. | security |
| P3-T5 | Add metric temporality normalization. | Delta and cumulative metrics are idempotent for replayed export batches. | data-platform |

Quality gate:

1. OTel-only fixtures produce valid `NormalizedSessionEnvelope` objects.
2. Mapping tests include Claude Code 2.1.126 `skill_activated.invocation_trigger`.
3. Missing `session.id` does not crash ingestion; unresolved facts are stored or dropped according to policy.

## Phase 4: OTLP Receiver and Config

Goal: expose an inbound endpoint that Claude Code or an OTel Collector can target.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P4-T1 | Add inbound OTel config in `backend/config.py`. | Config includes enable flag, receiver token, allowed platforms, raw retention, privacy mode, trace enablement, and max payload size. | backend-platform |
| P4-T2 | Add FastAPI receiver routes. | Routes accept OTLP HTTP/protobuf metrics/logs and optional traces, return OTLP-compatible success/error responses, and do not log raw bodies. | backend-platform |
| P4-T3 | Wire receiver to Claude OTel adapter and `SessionIngestService`. | Posting a fixture payload creates or updates a session through the shared service. | backend-platform |
| P4-T4 | Add auth/rate limits/payload limits. | Non-local receiver requires bearer token; oversized payloads are rejected before decoding. | security |
| P4-T5 | Add internal observability. | CCDash records inbound payload count, decode failures, normalized envelope count, persisted sessions, and latency by source/platform. | observability |

Quality gate:

1. Receiver can be disabled cleanly.
2. API runtime remains safe for local use; worker/topology implications are documented if receiver is API-owned.
3. Tests cover unauthorized, malformed, too-large, unsupported signal, and valid payload cases.

## Phase 5: Merge Semantics and Provenance

Goal: make OTel additive to JSONL forensics without corrupting richer transcript data.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P5-T1 | Implement merge policy in `SessionIngestService`. | `patch_metrics` updates metrics/forensics without deleting JSONL source rows; `upsert_complete` preserves current JSONL behavior. | data-platform |
| P5-T2 | Add provenance fields to `sessionForensics.otel`. | Session detail shows OTel source, app version, resource attributes policy, last received signal, confidence, and unresolved counts. | backend-platform |
| P5-T3 | Preserve canonical transcript priority. | JSONL/canonical `session_messages` are not replaced by metrics-only OTel data. | data-platform |
| P5-T4 | Add frontend type support for source/fidelity labels only where needed. | Missing provenance fields are safe fallbacks; no UI regression for older sessions. | frontend |
| P5-T5 | Add API filters/facets for source/platform when useful. | Existing platform facets can distinguish Claude Code JSONL vs Claude Code OTel provenance without breaking labels. | backend-platform |

Quality gate:

1. Same session ingested from JSONL then OTel remains one session.
2. Same session ingested from OTel then JSONL upgrades transcript fidelity.
3. Replayed OTel batches do not double count tokens/cost.

## Phase 6: Validation, Documentation, and Rollout

Goal: make the feature operable and safe to enable.

Tasks:

| ID | Task | Acceptance Criteria | Owner |
|---|---|---|---|
| P6-T1 | Add Claude Code setup guide. | Docs include direct endpoint and OTel Collector examples with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, metrics/log exporters, endpoint variables, and privacy warnings. | docs |
| P6-T2 | Add fixture corpus. | Fixtures cover metrics-only, logs-only, metrics+logs, beta traces, missing session ID, sensitive content, and replay. | testing |
| P6-T3 | Add E2E local smoke script or test. | A sample OTLP payload creates a visible session and can be queried through `/api/sessions`. | testing |
| P6-T4 | Update developer docs for adapter authors. | New platform adapter guidance explains how future Codex/other OTel sources implement the registry. | docs |
| P6-T5 | Rollout behind feature flag. | Default remains disabled until config is present; release notes explain how to enable. | platform-engineering |

Quality gate:

1. Full backend regression suite for sessions, session messages, usage attribution, analytics, and cache sync passes.
2. Frontend typecheck/build passes if frontend fields changed.
3. Manual direct or collector-forwarded Claude Code telemetry run is documented with exact observed result.

## Test Plan

Required tests:

1. `backend/tests/test_session_ingest_service.py`
2. `backend/tests/test_otel_claude_adapter.py`
3. `backend/tests/test_otel_receiver.py`
4. JSONL regression tests for Claude Code and Codex parser paths.
5. Merge tests for JSONL then OTel, OTel then JSONL, and replayed OTel.
6. Privacy tests for prompts, tool inputs, raw API bodies, email/account attributes, and unknown attributes.
7. API tests proving `/api/sessions` and `/api/v1/sessions` still return compatible DTOs.

Suggested fixture layout:

```text
backend/tests/fixtures/otel/claude_code/
  metrics_session_usage_v2_1_126.json
  logs_skill_at_mention_compaction_v2_1_126.json
  traces_interaction_beta_v2_1_126.json
  sensitive_payload_redaction.json
  missing_session_id_unresolved.json
```

## Implementation Notes

1. Do not reuse outbound `backend/services/telemetry_transformer.py` for inbound OTel. Its job is anonymized export, not source ingestion.
2. Keep OTel raw attribute names in bounded provenance so future schema changes are diagnosable.
3. Treat Claude Code traces as beta because the official docs mark tracing as beta and span attributes may change.
4. Prefer resource/service attributes for platform identification, but trust metric/event names for Claude mapping.
5. Make `session.id` inclusion explicit in docs; without it, session-level forensics quality drops sharply.

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
