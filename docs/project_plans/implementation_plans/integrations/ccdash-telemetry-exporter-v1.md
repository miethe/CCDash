---
schema_version: 3
doc_type: implementation_plan
status: in-progress
category: integrations
title: 'Implementation Plan: CCDash Telemetry Exporter V1'
description: Phased implementation plan for the CCDash Closed-Loop Telemetry Exporter,
  a background worker system for pushing anonymized workflow metrics to SAM
author: implementation-planner
created: 2026-03-24
updated: '2026-03-26'
feature_slug: ccdash-telemetry-exporter
prd_ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
tags:
- implementation-plan
- ccdash
- telemetry
- exporter
- sam
- integration
- background-jobs
- observability
---

# Implementation Plan: CCDash Telemetry Exporter V1

**Complexity**: Large (L) | **Track**: Standard
**Estimated Effort**: 28 story points | **Timeline**: 3-4 weeks across 4 phases

## Executive Summary

The CCDash Closed-Loop Telemetry Exporter closes the feedback loop between local project AI execution and the enterprise SkillMeat Artifact Manager (SAM) by implementing a persistent outbound queue, background export job, and operator controls.

The implementation follows a phased approach:

1. **Phase 1 (Foundation)**: Database schema, queue repository, transformation pipeline, and anonymization verifier
2. **Phase 2 (Export Worker)**: SAM HTTP client and scheduled job with retry logic
3. **Phase 3 (UI & Ops)**: Settings toggle, ops panel telemetry section, and "push now" action
4. **Phase 4 (Hardening)**: Backpressure, queue purging, OTel instrumentation, load testing, and docs

All work integrates with existing CCDash patterns: Router→Service→Repository layered architecture, async SQLite/PostgreSQL backend, job scheduling via `RuntimeJobAdapter`, and OTel metrics.

## Implementation Strategy

### Architecture Approach

- **Queueing**: Persistent `outbound_telemetry_queue` table in the same DB backend as sessions
- **Transformation**: Stateless `TelemetryTransformer` service + `AnonymizationVerifier` guard
- **Export**: `SAMTelemetryClient` wrapping aiohttp; `TelemetryExporterJob` runs under worker profile only
- **Observability**: New OTel spans, counters, and histograms; structured logging per run
- **Control Plane**: REST API endpoints + React UI in settings and ops panel

### Layer Sequencing (MeatyPrompts Architecture)

| Phase | Layer | Components | Dependencies |
|-------|-------|------------|--------------|
| 1 | Database | migration + schema | None |
| 1 | Model | `ExecutionOutcomePayload` Pydantic | None |
| 1 | Repository | `TelemetryQueueRepository` | Database layer |
| 1 | Service | `TelemetryTransformer`, `AnonymizationVerifier` | Model layer, existing model_identity |
| 2 | Adapter | `SAMTelemetryClient` (HTTP wrapper) | Config, aiohttp |
| 2 | Job | `TelemetryExporterJob` | Service, Repository |
| 2 | Runtime | `RuntimeContainer` registration | Job adapter |
| 3 | API | Status endpoint, "push now" endpoint | Repository, Service |
| 3 | UI | Settings toggle, ops panel components | API endpoints |
| 4 | Observability | OTel metrics, spans, structured logs | All previous layers |

### Parallel Work Opportunities

- P1-T1 through P1-T4 (config, migration, repository) can proceed independently of P1-T5 through P1-T7 (transformer, anonymization)
- P2-T1 (SAMTelemetryClient) can be developed in parallel with P1 completion
- P3 UI work depends on P2 completion for API stability but can start design work early

## Phase Overview

| Phase | Title | Duration | Story Points | Files Created | Key Deliverables |
|-------|-------|----------|--------------|----------------|------------------|
| 1 | Foundation | 1 week | 8 | 6 new, 2 modified | Queue table, repo, models, transformer, anonymization |
| 2 | Export Worker | 1 week | 8 | 4 new, 2 modified | SAM client, job, worker registration, retry logic |
| 3 | UI & Ops | 1 week | 7 | 5 new, 3 modified | Settings toggle, ops panel section, API endpoints |
| 4 | Hardening | 1 week | 5 | 2 new, 4 modified | OTel instrumentation, queue purging, load test, docs |
| **Total** | | **3-4 weeks** | **28** | **17 new, 11 modified** | Production-ready telemetry export pipeline |

---

## Phase 1: Foundation — Queue, Models, and Transformation

**Goal**: Implement the data persistence layer, transformation pipeline, and anonymization verification so that sessions can be enqueued without any network operations.

**Entry Criteria**:
- PRD approved and signed off
- Deployment Runtime Modularization and Hexagonal Foundation PRDs already shipped
- Team understands anonymization requirements

**Exit Criteria**:
- A session row can be transformed and enqueued in unit tests without network calls
- `AnonymizationVerifier` rejects payloads containing absolute paths, email addresses, and other sensitive patterns
- Config variables are documented in `.env.example`
- All unit tests pass; >85% code coverage for repository and transformer

### P1 Task Breakdown

#### P1-T1: Add Configuration Variables

**ID**: P1-T1
**Title**: Add telemetry exporter configuration to `backend/config.py` and `.env.example`
**Description**: Register all 8 telemetry exporter environment variables in the config module using existing `_env_bool()`, `_env_int()`, and `os.getenv()` patterns. Create a `TelemetryExporterConfig` Pydantic model for validation. Update `.env.example` with all variables and default values. Add docstrings for each variable.

**Files to Create/Modify**:
- `backend/config.py` — Add 8 new variables + `TelemetryExporterConfig` class
- `.env.example` — Add telemetry section with variable explanations

**Dependencies**: None
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- All 8 variables (`CCDASH_TELEMETRY_EXPORT_ENABLED`, `CCDASH_SAM_ENDPOINT`, etc.) are registered
- `TelemetryExporterConfig` validates min/max bounds (e.g., interval >= 60, batch_size 1-500)
- `.env.example` documents each variable with type and default
- Config module exports the config instance for injection
- Existing config tests pass

#### P1-T2: Create Database Migration for `outbound_telemetry_queue` Table

**ID**: P1-T2
**Title**: Add `outbound_telemetry_queue` table schema via migration
**Description**: Create a new migration in `backend/db/migrations.py` that defines the `outbound_telemetry_queue` table. Schema includes: `id` (UUID primary key), `session_id` (UUID foreign key), `project_slug` (text), `payload_json` (text), `status` (enum: pending/synced/failed/abandoned), `created_at`, `last_attempt_at`, `attempt_count` (int), `last_error` (text nullable). Add indexes on `status` and `created_at` for query efficiency.

**Files to Create/Modify**:
- `backend/db/migrations.py` — Add new migration function

**Dependencies**: None
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Migration creates table with correct schema (all fields present, types correct)
- Indexes exist on `status` and `created_at`
- Migration is idempotent (can be run multiple times safely)
- Migration works on both SQLite and PostgreSQL
- Rollback migration is defined (if applicable)
- Migration is registered in the migration runner

#### P1-T3: Implement `TelemetryQueueRepository`

**ID**: P1-T3
**Title**: Create `TelemetryQueueRepository` following base repository pattern
**Description**: Create `backend/db/repositories/telemetry_queue.py` extending `BaseRepository` from `base.py`. Implement methods: `enqueue()` (idempotent by session_id), `fetch_pending_batch(batch_size)`, `mark_synced(id)`, `mark_failed(id, error, attempt_count)`, `mark_abandoned(id, error)`, `get_queue_stats()`, and `purge_old_synced(retention_days)`. All methods are async coroutines using the shared async DB connection from `backend/db/connection.py`. Enqueue operation must handle duplicates (existing pending or synced rows) gracefully.

**Files to Create/Modify**:
- `backend/db/repositories/telemetry_queue.py` — New file
- `backend/db/repositories/__init__.py` — Import new repository (if applicable)

**Dependencies**: P1-T2 (migration completed)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- All 7 methods implemented and return correct types
- `enqueue()` is idempotent: calling it twice with same session_id results in single queue row
- `fetch_pending_batch()` returns rows ordered by `created_at` ASC
- `mark_failed()` increments `attempt_count` and updates `last_attempt_at`
- `mark_abandoned()` sets status to `abandoned` and logs session_id
- `purge_old_synced()` deletes rows older than retention window
- Unit tests cover all paths; 100% code coverage
- Works with async SQLite and PostgreSQL connections

#### P1-T4: Register Repository in `backend/db/factory.py`

**ID**: P1-T4
**Title**: Register `TelemetryQueueRepository` in the factory pattern
**Description**: Add a provider or factory method in `backend/db/factory.py` (or equivalent composition root) to instantiate `TelemetryQueueRepository` with the shared async DB connection. Ensure the repository is injected into any service or job that needs it.

**Files to Create/Modify**:
- `backend/db/factory.py` — Add repository provider

**Dependencies**: P1-T3 (repository implemented)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Factory creates repository instance with correct connection
- Repository is injectable into services/jobs
- Existing factory tests still pass

#### P1-T5: Define `ExecutionOutcomePayload` Pydantic Model

**ID**: P1-T5
**Title**: Create `ExecutionOutcomePayload` model in `backend/models.py`
**Description**: Add a Pydantic model class to `backend/models.py` (or a new `backend/models/telemetry.py` file) representing the SAM execution outcome payload. Include all fields from the PRD data contract: `event_id`, `project_slug`, `session_id`, `workflow_type` (optional), `model_family`, `token_input`, `token_output`, `token_cache_read` (optional), `token_cache_write` (optional), `cost_usd`, `tool_call_count`, `tool_call_success_count` (optional), `duration_seconds`, `message_count`, `outcome_status`, `test_pass_rate` (optional), `context_utilization_peak` (optional), `feature_slug` (optional), `timestamp`, `ccdash_version`. Use Pydantic field validators to enforce types and constraints (e.g., 0.0–1.0 for rates). Implement `.to_json()` method that excludes optional fields when None.

**Files to Create/Modify**:
- `backend/models.py` OR `backend/models/telemetry.py` — Add model class
- `backend/models/__init__.py` — Export new model (if new file)

**Dependencies**: None
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Model includes all 22 fields from PRD
- Field types are correct (UUID strings, floats, ints, enums, timestamps)
- Optional fields are correctly marked (exclude from JSON when None)
- `to_json()` method produces valid JSON matching schema_version: "1"
- Pydantic validators enforce constraints
- Unit tests verify serialization and optional field handling

#### P1-T6: Implement `TelemetryTransformer` Service

**ID**: P1-T6
**Title**: Create `TelemetryTransformer` service in `backend/services/`
**Description**: Create `backend/services/telemetry_transformer.py` (or reuse existing transformer file) implementing a stateless `TelemetryTransformer` class with method `transform_session(session_row, analytics_metadata) -> ExecutionOutcomePayload`. The transformer maps fields from the CCDash `sessions` table to the SAM payload contract. Uses `model_family_name()` from `backend/model_identity.py` for canonical model representation. Derives `outcome_status` from session state. Includes `test_pass_rate` only when test signals are present. Calls `AnonymizationVerifier.verify()` before returning the payload.

**Files to Create/Modify**:
- `backend/services/telemetry_transformer.py` — New file
- `backend/services/__init__.py` — Import transformer (if applicable)

**Dependencies**: P1-T5 (ExecutionOutcomePayload model)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- `transform_session()` accepts session row dict and optional analytics metadata
- Maps all required fields from session to payload
- Uses `model_family_name()` for model normalization
- Derives `outcome_status` correctly from session state
- Includes optional fields only when data is present
- Calls `AnonymizationVerifier` before returning
- Unit tests cover various session states (completed, interrupted, errored)
- Unit tests verify optional field inclusion/exclusion

#### P1-T7: Implement `AnonymizationVerifier` Guard

**ID**: P1-T7
**Title**: Create `AnonymizationVerifier` in `backend/services/telemetry_transformer.py`
**Description**: Implement a stateless `AnonymizationVerifier` class with static method `verify(payload: dict) -> None` that raises `AnonymizationError` if any field contains sensitive content. The verifier checks: absolute file paths (regex `/^\/` or `^[A-Z]:\\`), email addresses (regex `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`), sensitive field names (blocklist: `password`, `token`, `secret`, `key`, `credential`, `auth`), raw error stack traces, usernames, hostnames. Allow only UUID strings, integer counts, float metrics (0-1 for rates), ISO 8601 timestamps, enum values, and project slugs.

**Files to Create/Modify**:
- `backend/services/telemetry_transformer.py` — Add `AnonymizationVerifier` class

**Dependencies**: P1-T5 (ExecutionOutcomePayload model)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- `verify()` raises `AnonymizationError` on absolute paths (Unix and Windows)
- `verify()` raises on email-shaped strings
- `verify()` raises on sensitive field names from blocklist
- `verify()` accepts valid UUID strings, counts, rates, timestamps, slugs
- `verify()` can be unit tested in isolation (no network/DB dependencies)
- Unit tests include adversarial payloads (various path formats, email obfuscations)
- Coverage includes both whitelist (allowed patterns) and blacklist (forbidden patterns)

#### P1-T8: Unit Tests for Transformer and Anonymization Verifier

**ID**: P1-T8
**Title**: Write comprehensive unit tests for `TelemetryTransformer` and `AnonymizationVerifier`
**Description**: Create test file `backend/tests/test_telemetry_transformer.py` covering: transformer field mapping for all session states (completed, interrupted, errored), optional field inclusion/exclusion, model normalization via `model_family_name()`, and verifier rejection of sensitive content (paths, emails, field names, stack traces). Include fixtures for mock session rows and analytics metadata. Use pytest with mock session data.

**Files to Create/Modify**:
- `backend/tests/test_telemetry_transformer.py` — New test file

**Dependencies**: P1-T6, P1-T7 (transformer and verifier implemented)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- 10+ test cases for transformer (various session states, optional fields)
- 15+ test cases for verifier (paths, emails, field names, valid payloads)
- All tests pass
- Coverage >= 90% for transformer.py and verifier code
- Tests use pytest and mock session data; no DB or network calls
- Adversarial test cases included (email variations, path obfuscation)

#### P1-T9: Unit Tests for `TelemetryQueueRepository`

**ID**: P1-T9
**Title**: Write unit tests for `TelemetryQueueRepository` with mock async DB
**Description**: Create test file `backend/tests/test_telemetry_queue_repository.py` covering: enqueue idempotency, batch fetch ordering, mark-synced/failed/abandoned transitions, attempt count increment, purge-old-synced behavior, and get-queue-stats aggregation. Use pytest-asyncio and mock async SQLite connection.

**Files to Create/Modify**:
- `backend/tests/test_telemetry_queue_repository.py` — New test file

**Dependencies**: P1-T3 (repository implemented), P1-T2 (migration defines schema)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- 12+ test cases covering all repository methods
- Enqueue idempotency verified: duplicate session_id does not create second row
- Batch fetch returns rows in created_at ASC order
- Failed/abandoned transitions update status, error, and attempt_count correctly
- Purge-old-synced removes rows beyond retention window
- All tests pass with async mock DB
- Coverage >= 90% for repository.py
- No DB fixtures required (mocked)

### Phase 1 Deliverables

- New `backend/db/repositories/telemetry_queue.py` (TelemetryQueueRepository)
- New `backend/services/telemetry_transformer.py` (TelemetryTransformer + AnonymizationVerifier)
- New `backend/models.py` section or `backend/models/telemetry.py` (ExecutionOutcomePayload)
- Updated `backend/config.py` with 8 telemetry variables
- Updated `.env.example` with telemetry section
- Updated `backend/db/migrations.py` with queue table migration
- Updated `backend/db/factory.py` with repository provider
- Test files: `backend/tests/test_telemetry_transformer.py`, `backend/tests/test_telemetry_queue_repository.py`

### Phase 1 Testing Requirements

- Unit tests: transformer, verifier, repository (>85% coverage)
- Integration: Transform a real session row → enqueue → fetch-pending-batch → mark-synced
- Anonymization verification: Reject 10+ adversarial payloads (paths, emails, etc.)
- Config validation: Enforce interval >= 60, batch size 1-500

---

## Phase 2: Export Worker and HTTP Client

**Goal**: Implement the background job and SAM HTTP client so that the worker runtime can fetch batches from the queue and push them to SAM with retry logic.

**Entry Criteria**:
- Phase 1 complete and all tests passing
- SAM endpoint contract confirmed (POST /api/v1/analytics/execution-outcomes)
- Deployment Runtime Modularization PRD shipped (worker profile exists)

**Exit Criteria**:
- Worker runtime can push a 50-event batch to a mock SAM server
- Retries work correctly (5xx → retry after exponential backoff, 4xx → abandon)
- Job is re-entrant (no parallel execution of same job)
- Integration tests pass with mock HTTP server

### P2 Task Breakdown

#### P2-T1: Implement `SAMTelemetryClient`

**ID**: P2-T1
**Title**: Create `SAMTelemetryClient` in `backend/services/integrations/`
**Description**: Create `backend/services/integrations/sam_telemetry_client.py` wrapping aiohttp for HTTP POST to SAM. Constructor accepts `endpoint_url`, `api_key`, `timeout_seconds`, and `allow_insecure`. Implements async method `push_batch(events: List[ExecutionOutcomePayload]) -> Tuple[bool, Optional[str]]` returning success flag and optional error message. Validates config at construction: raises if endpoint or key is empty when enabled. Enforces TLS (rejects plaintext unless `allow_insecure=true`). Handles HTTP responses per FR-4.4: 200/202 → success, 429 → retry, 4xx → abandon, 5xx → retry, network errors → retry. Logs response body on error.

**Files to Create/Modify**:
- `backend/services/integrations/sam_telemetry_client.py` — New file
- `backend/services/integrations/__init__.py` — Import client (if applicable)

**Dependencies**: P1-T5 (ExecutionOutcomePayload model), P1-T1 (config with SAM variables)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Constructor validates endpoint/key presence and TLS requirement
- `push_batch()` returns (True, None) on 200/202
- `push_batch()` returns (False, error_msg) on 5xx or network error
- `push_batch()` returns (False, "abandoned") on 4xx (except 429)
- `push_batch()` returns (False, "rate_limited") on 429
- Timeout enforced (configurable, default 30 seconds)
- Logs response body and status code on error
- TLS enforcement: rejects http:// unless allow_insecure=true
- Unit tests with mock aiohttp responses

#### P2-T2: Implement `TelemetryExporterJob`

**ID**: P2-T2
**Title**: Create `TelemetryExporterJob` in `backend/adapters/jobs/`
**Description**: Create `backend/adapters/jobs/telemetry_exporter.py` implementing the job interface compatible with `InProcessJobScheduler` and `RuntimeJobAdapter`. Implements `async def execute() -> JobResult` that: checks if exporter is enabled; fetches pending batch from `TelemetryQueueRepository`; calls `SAMTelemetryClient.push_batch()`; updates row statuses (mark-synced or mark-failed); emits OTel span with batch metadata; logs structured info (run_id, batch_size, duration_ms, outcome). Enforces re-entrancy guard: skips execution if previous run still in progress. Implements exponential backoff: base 60s, max 4 hours, max 10 attempts.

**Files to Create/Modify**:
- `backend/adapters/jobs/telemetry_exporter.py` — New file
- `backend/adapters/jobs/__init__.py` — Import job (if applicable)

**Dependencies**: P2-T1 (SAMTelemetryClient), P1-T3 (TelemetryQueueRepository), P1-T1 (config)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Implements job interface (execute() returns JobResult)
- Fetches batch of configurable size (default 50) from queue
- Calls SAMTelemetryClient with fetched events
- Updates row statuses: mark-synced on success, mark-failed on retry, mark-abandoned on 4xx
- Re-entrancy guard prevents parallel execution
- Exponential backoff logic: attempt N → delay = min(60 * 2^(N-1), 14400) seconds
- Emits OTel span named `telemetry.export.batch` with attributes
- Structured log at INFO level: run_id, batch_size, duration_ms, outcome, queue_depth
- Skips gracefully if exporter is disabled via config

#### P2-T3: Register `TelemetryExporterJob` in Worker Profile

**ID**: P2-T3
**Title**: Register job in `RuntimeContainer` for worker runtime profile
**Description**: Modify `backend/runtime/container.py` to register `TelemetryExporterJob` in the worker profile only. The job must not be instantiated in the API-only or local-only profiles. Inject dependencies: `TelemetryQueueRepository`, `SAMTelemetryClient`, `TelemetryExporterConfig`. Set job interval to `CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS` from config.

**Files to Create/Modify**:
- `backend/runtime/container.py` — Add job registration

**Dependencies**: P2-T2 (TelemetryExporterJob), P1-T1 (config)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Job is registered with InProcessJobScheduler in worker profile
- Job interval is configurable via config variable
- Job is NOT registered in API-only profile
- Job receives correct dependencies injected
- Existing container tests still pass

#### P2-T4: Add Enqueue Trigger in Sync Engine Session Finalization

**ID**: P2-T4
**Title**: Integrate telemetry enqueuing into sync engine session finalization
**Description**: Modify `backend/db/sync_engine.py` (or `backend/parsers/sessions.py`) to enqueue a telemetry event when a session is finalized. Hook into the existing session-finalization event or add a call to `TelemetryTransformer.transform_session()` followed by `TelemetryQueueRepository.enqueue()`. This is a "should" requirement per FR-1.3 (optional but recommended). Pass the transformed and verified payload to the repository.

**Files to Create/Modify**:
- `backend/db/sync_engine.py` OR `backend/parsers/sessions.py` — Add enqueue call

**Dependencies**: P1-T6 (TelemetryTransformer), P1-T3 (TelemetryQueueRepository)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Session finalization triggers enqueue
- Transform and anonymization verify before enqueue
- Enqueue is idempotent (no duplicate rows)
- Existing sync engine tests still pass
- No exceptions bubble up (catch and log if enqueue fails)

#### P2-T5: Integration Tests with Mock SAM Server

**ID**: P2-T5
**Title**: Write integration tests for export job with mock HTTP server
**Description**: Create test file `backend/tests/test_telemetry_exporter_job.py` with integration tests using a mock HTTP server (e.g., pytest fixtures with aioresponses or httpretty). Tests cover: successful batch push (200/202), 5xx retry with backoff, 4xx abandon with logging, network error retry, re-entrancy guard prevents parallel runs, exponential backoff timing, queue state transitions. Simulate realistic scenarios: queue with 50 pending rows, partial success (some rows fail, retry later), SAM outage recovery.

**Files to Create/Modify**:
- `backend/tests/test_telemetry_exporter_job.py` — New test file
- `backend/tests/fixtures/mock_sam_server.py` — Mock HTTP server fixture (if needed)

**Dependencies**: P2-T1, P2-T2 (client and job)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- 8+ integration test cases (success, retries, abandonment, network errors, re-entrancy)
- Mock HTTP server returns configurable responses (200, 5xx, 4xx, timeout)
- Queue state transitions verified after each scenario
- Exponential backoff timing verified (delays double on each retry)
- Re-entrancy test confirms parallel execution is prevented
- All tests pass and use pytest-asyncio
- No real network calls made

#### P2-T6: Update Module `__init__.py` Files

**ID**: P2-T6
**Title**: Update imports in `__init__.py` files for new modules
**Description**: Update `backend/services/__init__.py`, `backend/adapters/jobs/__init__.py`, `backend/services/integrations/__init__.py` to import and expose the new classes (TelemetryTransformer, AnonymizationVerifier, SAMTelemetryClient, TelemetryExporterJob) for use throughout the codebase.

**Files to Create/Modify**:
- `backend/services/__init__.py` — Add imports
- `backend/adapters/jobs/__init__.py` — Add imports
- `backend/services/integrations/__init__.py` — Add imports (if applicable)

**Dependencies**: All Phase 2 modules created
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- All new classes can be imported from their package `__init__.py`
- No circular import errors
- Imports are re-exported cleanly

### Phase 2 Deliverables

- New `backend/services/integrations/sam_telemetry_client.py` (SAMTelemetryClient)
- New `backend/adapters/jobs/telemetry_exporter.py` (TelemetryExporterJob)
- Updated `backend/runtime/container.py` with job registration
- Updated `backend/db/sync_engine.py` with enqueue trigger
- Test file: `backend/tests/test_telemetry_exporter_job.py`
- Updated `__init__.py` files in services and jobs

### Phase 2 Testing Requirements

- Unit tests: SAMTelemetryClient response handling (200, 429, 4xx, 5xx, network errors)
- Integration tests: Job fetches batch → transforms → pushes → updates queue state
- Retry logic: Exponential backoff timing verified
- Re-entrancy: Parallel job execution prevented
- Mock SAM server: Simulate various failure scenarios

---

## Phase 3: UI Controls and Operations Panel

**Goal**: Deliver operator-friendly controls for enabling/disabling the exporter, viewing queue health, and triggering manual exports.

**Entry Criteria**:
- Phase 2 complete; exporter job is stable
- Backend API runtime profile includes new endpoints
- Frontend build and test infrastructure ready

**Exit Criteria**:
- Settings toggle works: enable/disable exporter, reflects env-var lock
- Ops panel shows: queue depth by status, last push timestamp, 24-hour event count, recent errors
- "Push Now" button triggers immediate export
- All API endpoints tested and documented

### P3 Task Breakdown

#### P3-T1: Backend API Endpoint for Telemetry Export Status

**ID**: P3-T1
**Title**: Create `/api/telemetry/export/status` endpoint in backend router
**Description**: Create or extend `backend/routers/telemetry.py` (new router) with GET endpoint `/api/telemetry/export/status` that returns telemetry exporter configuration and queue stats. Response shape: `{ "enabled": bool, "configured": bool, "sam_endpoint_masked": str, "queue_stats": { "pending": int, "failed": int, "abandoned": int }, "last_push_timestamp": ISO8601 | null, "events_pushed_24h": int, "last_error": str | null, "error_severity": "info" | "warning" | "error" | null }`. Uses `TelemetryQueueRepository.get_queue_stats()` and `TelemetryExporterConfig`.

**Files to Create/Modify**:
- `backend/routers/telemetry.py` — New router file
- `backend/runtime/container.py` — Register router (if needed)

**Dependencies**: P1-T3 (TelemetryQueueRepository), P1-T1 (config)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Endpoint returns correct shape with all fields
- Endpoint uses TelemetryQueueRepository for stats
- SAM endpoint is masked (show only hostname, not full URL)
- API key is never exposed in response
- Endpoint handles missing config gracefully (returns configured=false)
- Unit/integration tests verify response shape and data accuracy

#### P3-T2: Backend API Endpoint for "Push Now" Action

**ID**: P3-T2
**Title**: Create POST `/api/telemetry/export/push-now` endpoint
**Description**: Create endpoint that triggers an immediate export batch outside the scheduled interval. Endpoint fetches a batch, calls SAMTelemetryClient, updates queue state, and returns result. Response includes: `{ "success": bool, "batch_size": int, "duration_ms": int, "error": str | null }`. Only enabled when exporter is configured and enabled. Prevents concurrent pushes (uses same re-entrancy guard as scheduled job).

**Files to Create/Modify**:
- `backend/routers/telemetry.py` — Add POST endpoint

**Dependencies**: P2-T2 (TelemetryExporterJob logic reusable), P1-T3 (repo)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- POST endpoint triggers immediate export
- Returns batch_size, duration_ms, success flag
- Returns 400 if exporter not configured
- Returns 429 if previous export still in progress (re-entrancy)
- Updates queue state (mark-synced or mark-failed per outcome)
- Unit tests verify success and error cases

#### P3-T3: Frontend Types for Telemetry Export State

**ID**: P3-T3
**Title**: Add TypeScript types for telemetry export in `types.ts`
**Description**: Add TypeScript interfaces to `types.ts` for telemetry API responses: `TelemetryExportStatus`, `TelemetryQueueStats`, `PushNowResponse`. Types should match backend response shapes from P3-T1 and P3-T2.

**Files to Create/Modify**:
- `types.ts` — Add telemetry export types

**Dependencies**: P3-T1, P3-T2 (backend API shapes finalized)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: frontend-developer

**Acceptance Criteria**:
- Types match backend API responses
- Types are exported from types.ts
- Frontend components can import and use types
- No TypeScript compilation errors

#### P3-T4: Settings Toggle Component for Telemetry Export

**ID**: P3-T4
**Title**: Create "Enable Enterprise Telemetry Export" toggle in Settings > Integrations
**Description**: Create or extend React component in `components/SettingsIntegrations.tsx` (or similar) with a toggle for "Enable Enterprise Telemetry Export" in the SkillMeat integration section. Toggle should: be disabled and grayed out if SAM endpoint or API key are not configured; reflect current enabled state from backend; persist toggle changes via API; show masked SAM endpoint URL and last verified connection status; show hint if toggle is env-var locked (CCDASH_TELEMETRY_EXPORT_ENABLED=false via config).

**Files to Create/Modify**:
- `components/SettingsIntegrations.tsx` OR new `components/TelemetryExportToggle.tsx` — Add/update toggle
- `services/apiClient.ts` — Add API call for toggle update (if needed)

**Dependencies**: P3-T1 (status endpoint), P3-T3 (types)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: frontend-developer

**Acceptance Criteria**:
- Toggle renders in Settings > Integrations > SkillMeat
- Toggle is disabled if SAM endpoint/key not configured
- Clicking toggle calls backend API to persist state
- Toggle reflects current state on load
- Shows masked endpoint URL (hostname only)
- Shows "Environment Lock" hint if env-var controlled
- Toggle state persists across page reload
- Accessibility: proper label, ARIA attributes, keyboard navigation

#### P3-T5: Ops Panel Telemetry Export Section

**ID**: P3-T5
**Title**: Create "Telemetry Export" section in `/ops` operations panel
**Description**: Create React component in `components/OpsPanelTelemetrySection.tsx` (or extend `components/OpsPanel.tsx`) displaying telemetry exporter health. Display: current queue depth by status (pending/failed/abandoned), last successful push timestamp (or "Never" if none), total events pushed in last 24 hours, most recent HTTP error message with timestamp. Include a "Push Now" action button (disabled if exporter not configured). Refresh queue stats every 10 seconds via polling from `/api/telemetry/export/status`.

**Files to Create/Modify**:
- `components/OpsPanelTelemetrySection.tsx` — New component
- `components/OpsPanel.tsx` — Import and include section (if needed)
- `services/apiClient.ts` — Add polling function (if needed)

**Dependencies**: P3-T1, P3-T2 (backend endpoints), P3-T3 (types)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: frontend-developer

**Acceptance Criteria**:
- Section renders in /ops page
- Displays all 5 fields: queue depth (pending/failed/abandoned), last push, 24-hour count, error message
- Polls status endpoint every 10 seconds
- "Push Now" button enabled when exporter configured
- Clicking "Push Now" calls endpoint and shows result toast
- Error message includes timestamp if available
- Handles API errors gracefully (shows "Unable to load" with retry)
- Responsive design (mobile-friendly)

#### P3-T6: Wire API Client for New Endpoints

**ID**: P3-T6
**Title**: Add telemetry export API methods to `services/apiClient.ts`
**Description**: Add typed API client functions to `services/apiClient.ts`: `getTelemetryExportStatus()` (GET /api/telemetry/export/status), `triggerPushNow()` (POST /api/telemetry/export/push-now). Both use `fetch()` with proper error handling and return typed responses.

**Files to Create/Modify**:
- `services/apiClient.ts` — Add API methods

**Dependencies**: P3-T1, P3-T2 (backend endpoints), P3-T3 (types)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: frontend-developer

**Acceptance Criteria**:
- `getTelemetryExportStatus()` returns TelemetryExportStatus
- `triggerPushNow()` returns PushNowResponse
- Both methods handle errors and return typed responses
- Methods are exported from apiClient module
- Frontend components can import and use methods

### Phase 3 Deliverables

- New `backend/routers/telemetry.py` with status and push-now endpoints
- New `components/OpsPanelTelemetrySection.tsx` React component
- Updated `types.ts` with telemetry export types
- Updated `services/apiClient.ts` with API client methods
- Updated `components/SettingsIntegrations.tsx` with toggle component
- Test files for API endpoints

### Phase 3 Testing Requirements

- API endpoint tests: Status returns correct shape, push-now triggers export
- Frontend component tests: Toggle state, settings persistence, ops panel refresh
- Integration test: Toggle enable → Queue status visible → Push Now works
- E2E test (manual): Settings toggle → Ops panel shows status → Push Now → Queue updates

---

## Phase 4: Hardening — Backpressure, Monitoring, and Documentation

**Goal**: Implement queue size capping, row purging, comprehensive OTel instrumentation, load testing, and production documentation.

**Entry Criteria**:
- Phase 3 complete; UI and ops panel are stable
- Backend exporter and frontend controls working end-to-end
- Ready for production rollout

**Exit Criteria**:
- Queue cannot exceed size cap (CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE)
- Synced rows are purged on schedule (configurable retention)
- All OTel metrics emitted and visible in Prometheus
- Load test confirms <2% CPU overhead at 50-event batches
- Complete end-user and operator documentation published
- All success metrics measurable and tracked

### P4 Task Breakdown

#### P4-T1: Queue-Size Cap Enforcement

**ID**: P4-T1
**Title**: Implement max queue size check in `TelemetryQueueRepository.enqueue()`
**Description**: Modify `backend/db/repositories/telemetry_queue.py` method `enqueue()` to check current pending queue size before inserting. If queue size >= `CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE`, emit warning log and return without inserting (drop-and-warn behavior). Log includes session_id and queue size at time of drop.

**Files to Create/Modify**:
- `backend/db/repositories/telemetry_queue.py` — Add size check to enqueue()

**Dependencies**: P1-T3 (repository), P1-T1 (config with max queue size)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- `enqueue()` checks queue size before insert
- Drop-and-warn logged with session_id, current size, max size
- Size check does not significantly impact enqueue performance (<5ms overhead)
- Unit tests verify size cap enforcement

#### P4-T2: Synced-Row Purge with Retention Window

**ID**: P4-T2
**Title**: Implement synced-row purge in `TelemetryExporterJob`
**Description**: Modify `backend/adapters/jobs/telemetry_exporter.py` to call `TelemetryQueueRepository.purge_old_synced()` at the end of each job execution. Method uses `CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS` (default 30 days) to determine cutoff. Logs number of rows purged.

**Files to Create/Modify**:
- `backend/adapters/jobs/telemetry_exporter.py` — Add purge call

**Dependencies**: P1-T3 (repository purge method), P2-T2 (job), P1-T1 (config)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Job calls purge_old_synced() after each batch push
- Purge uses retention window from config
- Log includes number of rows purged
- Purge is optional (can be disabled via config if needed)
- Unit tests verify purge behavior

#### P4-T3: OTel Counters and Histograms in `backend/observability/otel.py`

**ID**: P4-T3
**Title**: Extend OTel instrumentation with telemetry exporter metrics
**Description**: Modify `backend/observability/otel.py` to add new metrics: `ccdash_telemetry_export_events_total` (counter, labels: status={success/retry/abandon}, project), `ccdash_telemetry_export_latency_ms` (histogram, labels: project), `ccdash_telemetry_export_queue_depth` (gauge, labels: status={pending/failed/abandoned}, project), `ccdash_telemetry_export_errors_total` (counter, labels: error_type={network/timeout/4xx/5xx}, project), `ccdash_telemetry_export_disabled` (gauge, 1 if disabled, 0 if enabled).

**Files to Create/Modify**:
- `backend/observability/otel.py` — Add metric definitions

**Dependencies**: P1-T1 (config), P2-T2 (job)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- All 5 metrics defined with correct types (counter, histogram, gauge)
- Metrics have appropriate labels for filtering
- Metrics can be exported to Prometheus
- Unit tests verify metric registration and emission
- No performance impact on existing metrics

#### P4-T4: OTel Span Wrapping for Export Batches

**ID**: P4-T4
**Title**: Add OTel span instrumentation to `TelemetryExporterJob`
**Description**: Modify `backend/adapters/jobs/telemetry_exporter.py` to wrap batch export in an OTel span named `telemetry.export.batch` with attributes: `batch_size` (int), `project_slug` (string), `sam_endpoint_host` (string, masked), `outcome` (string: success/retry/abandon). Span should time the entire batch push operation.

**Files to Create/Modify**:
- `backend/adapters/jobs/telemetry_exporter.py` — Add span wrapping

**Dependencies**: P2-T2 (job), P4-T3 (OTel metrics)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Span named `telemetry.export.batch` wraps batch push
- Span includes all 4 attributes
- Span duration reflects push latency
- Span is properly closed on success and error
- Unit tests verify span creation and attributes

#### P4-T5: Prometheus Gauge for Disabled State

**ID**: P4-T5
**Title**: Emit Prometheus gauge for exporter-disabled state
**Description**: Ensure `backend/observability/otel.py` emits `ccdash_telemetry_export_disabled` gauge (value 1 if disabled, 0 if enabled) even when exporter is not configured. This allows alerting dashboards to detect deployments where telemetry export is unconfigured. Gauge is set on worker profile startup and updated on each job run.

**Files to Create/Modify**:
- `backend/observability/otel.py` — Add disabled gauge
- `backend/runtime/container.py` — Set gauge on worker profile startup

**Dependencies**: P1-T1 (config), P2-T3 (job registration)
**Estimated Effort**: S (1-2 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Gauge is set to 1 when exporter disabled, 0 when enabled
- Gauge is visible in Prometheus output
- Gauge is updated on job runs
- No performance impact

#### P4-T6: Load Test Script

**ID**: P4-T6
**Title**: Create load test demonstrating <2% CPU overhead
**Description**: Create `backend/tests/load_test_telemetry_exporter.py` or similar that: generates a synthetic queue of 1000 pending rows; runs exporter job 10 times processing 50-event batches; measures total CPU time, duration, and memory overhead. Verifies that total CPU time for 10 job runs is <2% of worker process CPU time. Uses Python's `cProfile` or similar. Generates report with timing statistics.

**Files to Create/Modify**:
- `backend/tests/load_test_telemetry_exporter.py` — New test script

**Dependencies**: P2-T2 (job), P1-T3 (repository)
**Estimated Effort**: M (2-4 hours)
**Assigned to**: python-backend-engineer

**Acceptance Criteria**:
- Load test generates 1000 synthetic queue rows
- Job processes 50-event batches 10 times
- Measures CPU time and memory usage
- Verifies <2% CPU overhead
- Generates readable report with timing stats
- Test runs in <5 minutes

#### P4-T7: End-to-End Documentation

**ID**: P4-T7
**Title**: Write production operator documentation
**Description**: Create comprehensive documentation covering: configuration guide (all 8 environment variables, defaults, constraints), operator procedures (enable/disable, monitor via ops panel, interpret error codes), troubleshooting (queue growth, network issues, abandoned rows), monitoring (which Prometheus metrics to watch, alerting recommendations), and security notes (API key rotation, TLS enforcement, anonymization verification). Document in `docs/` directory.

**Files to Create/Modify**:
- `docs/guides/telemetry-exporter-guide.md` — New guide document
- `docs/guides/telemetry-exporter-troubleshooting.md` — Troubleshooting guide
- `docs/api/telemetry-export-api.md` — API documentation (optional)
- Updated `CLAUDE.md` context file (if applicable)

**Dependencies**: All phases 1-3 complete
**Estimated Effort**: M (2-4 hours)
**Assigned to**: documentation-writer

**Acceptance Criteria**:
- Configuration guide covers all 8 variables with examples
- Operator procedures are step-by-step and testable
- Troubleshooting covers common failure modes
- Monitoring guide lists key metrics and alert conditions
- Security section covers API key, TLS, anonymization
- Documentation is rendered and readable
- Code examples are tested

### Phase 4 Deliverables

- Updated `backend/db/repositories/telemetry_queue.py` with size cap check
- Updated `backend/adapters/jobs/telemetry_exporter.py` with purge call
- Updated `backend/observability/otel.py` with telemetry metrics
- Load test script: `backend/tests/load_test_telemetry_exporter.py`
- Documentation files: configuration, troubleshooting, API guides
- Updated `CLAUDE.md` or context files (if applicable)

### Phase 4 Testing Requirements

- Load test: <2% CPU overhead at 50-event batches
- OTel metrics: Counters increment correctly, gauges update, histograms record latency
- Span tests: Batch export wrapped in OTel span with correct attributes
- Queue cap tests: Enqueue rejects when size >= max, logs warning
- Purge tests: Old rows deleted on schedule, correct retention window respected
- Documentation verification: All examples are current and tested

---

## Dependency Graph

```
Phase 1: Foundation
├─ P1-T1: Config vars
│  └─ Used by: P2-T2, P2-T3, P3-T1, P4-T1, P4-T2, P4-T5
├─ P1-T2: DB migration
│  └─ Required by: P1-T3
├─ P1-T3: TelemetryQueueRepository
│  ├─ Required by: P1-T4, P2-T2, P3-T1, P4-T1
│  └─ Depends on: P1-T2
├─ P1-T4: Repository registration
│  └─ Depends on: P1-T3
├─ P1-T5: ExecutionOutcomePayload model
│  ├─ Required by: P1-T6, P2-T1, P3-T3
│  └─ No dependencies
├─ P1-T6: TelemetryTransformer
│  ├─ Required by: P1-T8, P2-T4
│  └─ Depends on: P1-T5, existing model_identity
├─ P1-T7: AnonymizationVerifier
│  ├─ Required by: P1-T8, P1-T6 (called before return)
│  └─ Depends on: P1-T5
├─ P1-T8: Transformer/Verifier tests
│  └─ Depends on: P1-T6, P1-T7
└─ P1-T9: Repository tests
   └─ Depends on: P1-T3, P1-T2

Phase 2: Export Worker
├─ P2-T1: SAMTelemetryClient
│  ├─ Required by: P2-T2, P3-T2
│  └─ Depends on: P1-T5, P1-T1
├─ P2-T2: TelemetryExporterJob
│  ├─ Required by: P2-T3, P2-T5, P4-T2
│  └─ Depends on: P2-T1, P1-T3, P1-T1
├─ P2-T3: Register job in RuntimeContainer
│  └─ Depends on: P2-T2, P1-T1
├─ P2-T4: Sync engine enqueue trigger
│  └─ Depends on: P1-T6, P1-T3
├─ P2-T5: Integration tests
│  └─ Depends on: P2-T1, P2-T2
└─ P2-T6: Module __init__.py updates
   └─ Depends on: All Phase 2 modules

Phase 3: UI & Ops
├─ P3-T1: Status endpoint
│  └─ Depends on: P1-T3, P1-T1
├─ P3-T2: Push-now endpoint
│  └─ Depends on: P2-T2, P1-T3
├─ P3-T3: Frontend types
│  └─ Depends on: P3-T1, P3-T2
├─ P3-T4: Settings toggle
│  └─ Depends on: P3-T1, P3-T3
├─ P3-T5: Ops panel section
│  └─ Depends on: P3-T1, P3-T2, P3-T3
└─ P3-T6: API client methods
   └─ Depends on: P3-T1, P3-T2, P3-T3

Phase 4: Hardening
├─ P4-T1: Queue-size cap
│  └─ Depends on: P1-T3, P1-T1
├─ P4-T2: Synced-row purge
│  └─ Depends on: P1-T3, P2-T2, P1-T1
├─ P4-T3: OTel metrics
│  └─ Depends on: P1-T1, P2-T2
├─ P4-T4: OTel spans
│  └─ Depends on: P2-T2, P4-T3
├─ P4-T5: Disabled-state gauge
│  └─ Depends on: P1-T1, P2-T3
├─ P4-T6: Load test
│  └─ Depends on: P2-T2, P1-T3
└─ P4-T7: Documentation
   └─ Depends on: All phases 1-3

Critical Path (minimum duration):
P1-T1,T2,T5 → P1-T3,T6,T7 → P2-T1,T2 → P3-T1,T2 → P3-T5,T4 → P4-T3,T6,T7
Estimated: 3-4 weeks
```

## Integration Points with Existing Codebase

### Backend Dependencies

| Component | File | Usage | Integration Point |
|-----------|------|-------|------------------|
| Config | `backend/config.py` | Read telemetry env vars | Add `TelemetryExporterConfig` class |
| DB Connection | `backend/db/connection.py` | Async SQLite/PostgreSQL | Repository uses singleton connection |
| Migrations | `backend/db/migrations.py` | Create queue table | Add migration function for queue schema |
| Base Repository | `backend/db/repositories/base.py` | Repository pattern | `TelemetryQueueRepository` extends base |
| Factory | `backend/db/factory.py` | Dependency injection | Register repository provider |
| Job Interface | `backend/adapters/jobs/__init__.py` | Job scheduling | `TelemetryExporterJob` implements interface |
| Runtime Container | `backend/runtime/container.py` | Profile-based registration | Register job in worker profile only |
| Model Identity | `backend/model_identity.py` | Normalize model names | Transformer calls `model_family_name()` |
| OTel | `backend/observability/otel.py` | Instrumentation | Add 5 new metrics and span names |
| Domain Events | `backend/application/live_updates/domain_events.py` | Event triggering | Optional: hook session finalization (P2-T4) |
| Session Parser | `backend/parsers/sessions.py` | Session finalization | Optional: trigger enqueue (P2-T4) |
| Sync Engine | `backend/db/sync_engine.py` | Sync completion | Optional: trigger enqueue (P2-T4) |

### Frontend Dependencies

| Component | File | Usage | Integration Point |
|-----------|------|-------|------------------|
| Types | `types.ts` | Type definitions | Add `TelemetryExportStatus`, `TelemetryQueueStats` |
| API Client | `services/apiClient.ts` | HTTP calls | Add `getTelemetryExportStatus()`, `triggerPushNow()` |
| Settings | `components/SettingsIntegrations.tsx` | Settings UI | Add telemetry toggle in SkillMeat section |
| Ops Panel | `components/OpsPanel.tsx` | Operations dashboard | Add telemetry section component |
| Router | `App.tsx` (if applicable) | Route registration | Status endpoint already routable via proxy |

### External Dependencies

| Dependency | Type | Availability | Notes |
|------------|------|--------------|-------|
| `aiohttp` | Python library | Already present | Used for SkillMeat integration; no new dependency |
| SAM API | External service | Must be deployed | Endpoint: `POST /api/v1/analytics/execution-outcomes` |
| OTel Exporter | Infrastructure | Must be configured | Prometheus/Jaeger backend for metrics/traces |

## Quality Gates and Acceptance Criteria

### Phase 1 Quality Gates

- [ ] All 8 config variables registered and validated
- [ ] DB migration creates queue table with correct schema and indexes
- [ ] Repository implements all 7 methods with >90% test coverage
- [ ] Transformer maps all session fields correctly
- [ ] Anonymization verifier rejects 10+ adversarial payloads (paths, emails, etc.)
- [ ] Model can serialize to JSON matching schema_version: "1"
- [ ] All unit tests pass (transformer, verifier, repository)

### Phase 2 Quality Gates

- [ ] SAMTelemetryClient handles all HTTP response codes correctly (200/202, 429, 4xx, 5xx)
- [ ] TelemetryExporterJob is re-entrant (no parallel execution)
- [ ] Exponential backoff timing verified (base 60s, max 4 hours)
- [ ] Job is registered in worker profile only
- [ ] Integration tests pass with mock SAM server
- [ ] Enqueue trigger in sync engine works end-to-end
- [ ] All OTel spans and logs emitted correctly

### Phase 3 Quality Gates

- [ ] Status endpoint returns correct shape with all fields
- [ ] Push-now endpoint triggers immediate export
- [ ] Settings toggle enables/disables exporter
- [ ] Toggle reflects env-var lock (cannot override if env-controlled)
- [ ] Ops panel refreshes queue stats every 10 seconds
- [ ] API key never exposed in frontend or logs
- [ ] Accessibility tests pass (toggle, button labels, keyboard nav)

### Phase 4 Quality Gates

- [ ] Queue cannot exceed size cap (tested with >10,000 pending rows)
- [ ] Synced rows purged on schedule (tested with retention window)
- [ ] All OTel metrics emitted and visible in Prometheus
- [ ] Load test confirms <2% CPU overhead at 50-event batches
- [ ] Documentation covers all 8 config variables and troubleshooting
- [ ] No regressions in existing tests (>95% pass rate on full suite)

## Success Metrics (from PRD)

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Delivery rate (1-hour SLO) | 0% | >= 99.5% | Count successful deliveries ÷ total enqueued |
| Queue-to-delivery latency (p95) | N/A | <= 20 min | Measure time from enqueue to SAM receipt |
| Exporter CPU overhead | N/A | < 2% | Load test with cProfile |
| Anonymization violations | N/A | 0 | Field audit + regex scanning |
| Operator diagnosis time | Manual search | < 2 min | Time to find error via ops panel |
| Data freshness staleness | N/A | Warning if > 2 intervals | Ops panel timestamp check |
| Abandoned events | N/A | < 0.1% weekly | Count abandoned ÷ total enqueued |

---

## Risk Mitigation Summary

| Risk | Impact | Mitigation | Owner |
|------|--------|-----------|-------|
| Anonymization pipeline blind spot | High | Blocklist + regex verifier + field audit | P1-T7 lead |
| SAM contract changes silently | Medium | Schema version pinned, error logging, canary test | P2-T1 lead |
| Queue unbounded growth | High | Size cap enforcement + retention purge | P4-T1, P4-T2 |
| Excessive DB I/O on SQLite | Medium | Indexed status/created_at, batching, off-peak purge | P1-T2, P4-T2 |
| Worker restarts mid-batch | Low | Two-phase update (claim → push → mark) | P2-T2 |
| Operator doesn't notice exporter disabled | Medium | Ops panel banner + Prometheus gauge | P3-T5, P4-T5 |

---

## Timeline Estimate

**Week 1**: Phase 1 (Foundation)
- Days 1-2: P1-T1, P1-T2, P1-T5 (config, migration, model)
- Days 3-4: P1-T3, P1-T4, P1-T6, P1-T7 (repository, transformer, verifier)
- Day 5: P1-T8, P1-T9 (testing), plus sign-off

**Week 2**: Phase 2 (Export Worker) + Phase 3 start
- Days 1-2: P2-T1, P2-T2, P2-T3 (SAMTelemetryClient, job, registration)
- Day 3: P2-T4, P2-T5, P2-T6 (enqueue trigger, integration tests, imports)
- Days 4-5: P3-T1, P3-T2 (API endpoints) + sign-off on Phase 2

**Week 3**: Phase 3 (UI & Ops)
- Days 1-2: P3-T3, P3-T4, P3-T5, P3-T6 (types, toggle, ops panel, API client)
- Days 3-5: Testing, bug fixes, sign-off on Phase 3

**Week 4**: Phase 4 (Hardening)
- Days 1-2: P4-T1, P4-T2, P4-T3, P4-T4, P4-T5 (backpressure, OTel)
- Days 3-4: P4-T6 (load test), P4-T7 (documentation)
- Day 5: Final testing, sign-off, production readiness

Total: 3-4 weeks across 4 phases, 28 story points

---

## Subagent Assignments

### Phase 1 Tasks

| Task | Assigned to | Model | Effort |
|------|-------------|-------|--------|
| P1-T1 (Config) | python-backend-engineer | sonnet | S |
| P1-T2 (Migration) | python-backend-engineer | sonnet | M |
| P1-T3 (Repository) | python-backend-engineer | sonnet | M |
| P1-T4 (Factory) | python-backend-engineer | sonnet | S |
| P1-T5 (Model) | python-backend-engineer | sonnet | S |
| P1-T6 (Transformer) | python-backend-engineer | sonnet | M |
| P1-T7 (Verifier) | python-backend-engineer | sonnet | M |
| P1-T8 (Tests) | python-backend-engineer | sonnet | M |
| P1-T9 (Tests) | python-backend-engineer | sonnet | M |

### Phase 2 Tasks

| Task | Assigned to | Model | Effort |
|------|-------------|-------|--------|
| P2-T1 (SAMClient) | python-backend-engineer | sonnet | M |
| P2-T2 (Job) | python-backend-engineer | sonnet | M |
| P2-T3 (Registration) | python-backend-engineer | sonnet | S |
| P2-T4 (Trigger) | python-backend-engineer | sonnet | S |
| P2-T5 (Tests) | python-backend-engineer | sonnet | M |
| P2-T6 (Imports) | python-backend-engineer | haiku | S |

### Phase 3 Tasks

| Task | Assigned to | Model | Effort |
|------|-------------|-------|--------|
| P3-T1 (Status Endpoint) | python-backend-engineer | sonnet | M |
| P3-T2 (Push-Now Endpoint) | python-backend-engineer | sonnet | M |
| P3-T3 (Types) | frontend-developer | sonnet | S |
| P3-T4 (Settings Toggle) | frontend-developer | sonnet | M |
| P3-T5 (Ops Panel) | frontend-developer | sonnet | M |
| P3-T6 (API Client) | frontend-developer | sonnet | S |

### Phase 4 Tasks

| Task | Assigned to | Model | Effort |
|------|-------------|-------|--------|
| P4-T1 (Queue Cap) | python-backend-engineer | sonnet | S |
| P4-T2 (Purge) | python-backend-engineer | sonnet | S |
| P4-T3 (OTel Metrics) | python-backend-engineer | sonnet | M |
| P4-T4 (OTel Spans) | python-backend-engineer | sonnet | S |
| P4-T5 (Disabled Gauge) | python-backend-engineer | sonnet | S |
| P4-T6 (Load Test) | python-backend-engineer | sonnet | M |
| P4-T7 (Docs) | documentation-writer | haiku | M |

**Total Estimated Effort**: 28 story points

---

## Related Documents

- **PRD**: `/docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md`
- **Prerequisite PRDs**: Deployment Runtime Modularization, Hexagonal Foundation
- **Related Implementation Plans**: telemetry-analytics-modernization-v1.md
- **Architecture References**: CLAUDE.md (backend structure, job patterns, observability)

---

**Plan Status**: Draft
**Last Updated**: 2026-03-24
**Author**: Implementation Planner (Haiku 4.5)
