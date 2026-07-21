---
title: "Phase 1: Ingest transport + rf_events persistence"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-21
updated: 2026-07-21
feature_slug: "research-foundry-run-telemetry"
feature_version: "v1"
phase: 1
phase_title: "Ingest transport + rf_events persistence"
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
entry_criteria:
  - "PRD approved; decisions block D1/D3/D6 locked"
  - "No dependency on RF's transport landing — seeded fixtures alone must exercise the full path"
exit_criteria:
  - "A seeded/fixture ccdash_event-shaped payload POSTs to /api/v1/ingest/rf-events, persists idempotently, and dead-letters on malformed payload"
  - "Dual-DDL parity + direct-count assertion tests green for rf_events"
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
spike_ref: null
adr_refs:
  - docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-proposed-adr.md
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: []
owner: null
contributors: []
priority: medium
risk_level: medium
category: "product-planning"
tags: [phase-plan, implementation, ingest, dual-ddl]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/routers/ingest.py
  - backend/application/models/ingest.py
  - backend/application/services/ingest/rf_events_ingest.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/application/services/agent_queries/ingest_sources.py
  - backend/routers/client_v1.py
---

# Phase 1: Ingest transport + `rf_events` persistence

**Parent Plan**: [Research Foundry Run Telemetry — Implementation Plan](../research-foundry-run-telemetry-v1.md)
**Duration**: ~1–1.5 weeks
**Effort**: 8.5 story points
**Dependencies**: None — buildable and testable with zero live RF traffic (seeded fixtures only)
**Team Members**: `data-layer-expert`, `python-backend-engineer`, `task-completion-validator`

---

## Phase Overview

This phase builds the receiving side of RF's telemetry independent of whether RF's own companion
HTTP-POST change has landed. It adds a new `POST /api/v1/ingest/rf-events` endpoint reusing the
existing NDJSON/`ingest_cursors`/dead-letter transport stack (ADR-008/009/014/015) and a new
`rf_events` raw append-only table (dual SQLite+Postgres DDL). Nothing in this phase touches
`sessions`, `aos_correlation.py`, or any existing ingest source.

### Goals

- Ship an idempotent ingest contract that can be fully exercised with seeded fixtures (FR-1–FR-3).
- Register the new source in the capability + health-detail surfaces (FR-4, FR-5).
- Gate the entire feature behind `CCDASH_RF_TELEMETRY_ENABLED` (FR-13).
- Pass the ADR-007 dual-DDL parity + direct-count exit gate before Phase 2 begins.

### Architecture Focus

- **Layer**: Database (dual DDL) + API (router/service)
- **Patterns**: `ingest_cursors` v36 precedent exactly (`backend/db/sqlite_migrations.py:3762-3800`); `retry_on_locked` on all writes; `WorkspaceTokenAuthBackend` reuse (no new auth scheme)
- **Standards**: ADR-007 (DB write-failure surfacing), ADR-008/009/014/015 (remote ingest transport)

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|----------------------|----------|-------------|-------|--------|---------------|
| T1-001 | `rf_events` dual-DDL raw table | New table in both `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`, registered in `get_sqlite_migration_tables()`/`get_postgres_migration_tables()`, columns cover the full `ccdash_event` shape (event_id PK, run_id, rf raw ids, cost/quality metrics, optional fields nullable) | Migrations run cleanly on both backends; `event_id` uniquely constrained | 2 pts | data-layer-expert | sonnet | adaptive | None |
| T1-002 | Migration governance + parity/direct-count test (ADR-007 exit gate) | Add `rf_events` to `COLUMN_PARITY_DRIFT_ALLOWLIST` entry set correctly; write the direct-count assertion test (insert N rows, assert `SELECT COUNT(*)` == N) per ADR-007 | `test_migration_governance.py` passes for `rf_events`; direct-count test green on both backends | 1 pt | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-003 | `POST /api/v1/ingest/rf-events` endpoint | New route in `backend/routers/ingest.py` (existing `ingest_router`), Pydantic models in `backend/application/models/ingest.py`, service in `backend/application/services/ingest/rf_events_ingest.py`; reuses `WorkspaceTokenAuthBackend`; accepts NDJSON or single JSON; runs the Layer 1 redaction scan (FR-14) before persistence | Endpoint accepts RF's `ccdash_event` shape; auth reuses existing backend with zero new auth code; redaction scan invoked on payload fields | 2 pts | python-backend-engineer | sonnet | adaptive | T1-001 |
| T1-004 | Idempotent cursor enqueue + dead-letter reuse | New `source_id='rf'` row in `ingest_cursors`; wire the existing dead-letter queue for permanently-failed events; all writes wrapped in `retry_on_locked` | Malformed/permanently-failing payloads land in the existing dead-letter NDJSON, not silently dropped | 1 pt | python-backend-engineer | sonnet | adaptive | T1-003 |
| T1-005 | Ingest idempotency regression test | Test: POST the same `event_id` twice → exactly one `rf_events` row; POST with missing optional fields (`human_review`, `output.claim_ledger_created`, etc.) → row persists with those columns null, never a 422 | AC-1 fully covered: idempotency + optional-field resilience | 1 pt | python-backend-engineer | sonnet | adaptive | T1-002, T1-004 |
| T1-006 | Feature flag `CCDASH_RF_TELEMETRY_ENABLED` | Gate the ingest route behind the flag (default `true`, fail-open); disabling 404s the route with zero effect on any other surface | Flag toggles route availability; documented default | 0.5 pts | python-backend-engineer | sonnet | adaptive | T1-003 |
| T1-007 | Capability advert + `ingest_sources[]` health entry | `GET /api/v1/capabilities` advertises `research-runs:*` (`backend/routers/client_v1.py`); `/api/health/detail` → `ingest_sources[]` registers an `rf` entry with the existing freshness-threshold logic (`backend/application/services/agent_queries/ingest_sources.py`) | AC-5 fully covered; existing consumers of `/api/v1/capabilities` do not hard-fail on the new string | 0.5 pts | python-backend-engineer | sonnet | adaptive | T1-004 |
| T1-008 | Phase 1 completion review | `task-completion-validator` verifies all Phase 1 ACs (AC-1, AC-2 partial, AC-5) are genuinely met, not superficially — re-run T1-005 and T1-002's tests independently | Reviewer sign-off recorded before Phase 2 kickoff | 0.5 pts | task-completion-validator | sonnet | adaptive | T1-001 through T1-007 |

**Phase 1 total: 8.5 pts**

---

## Acceptance Criteria (structured)

### AC-1: Ingest endpoint persists idempotently with zero live RF traffic required

- target_surfaces:
    - backend/routers/ingest.py
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
- propagation_contract: A seeded `ccdash_event`-shaped JSON POST to `/api/v1/ingest/rf-events` (workspace-token auth) inserts one `rf_events` row; re-POSTing the identical `event_id` inserts zero additional rows.
- resilience: If the request body is missing optional RF fields (e.g. `human_review`, `output.claim_ledger_created`), the row still persists with those columns null — never a 422 for an optional field's absence.
- visual_evidence_required: false
- verified_by: [T1-005, T1-008]

### AC-5: Capability + health surfaces advertise the new source correctly

- target_surfaces:
    - backend/routers/client_v1.py
    - backend/application/services/agent_queries/ingest_sources.py
- propagation_contract: `GET /api/v1/capabilities` includes `research-runs:*`; `/api/health/detail` → `ingest_sources[]` includes an `rf` entry whose state transitions `idle` → `connected` → `backed_up` → `disconnected` per the existing freshness-threshold logic, unmodified.
- resilience: Consumers that predate this feature and query `/api/v1/capabilities` MUST NOT hard-fail on the new capability string (existing contract, re-verified).
- visual_evidence_required: false
- verified_by: [T1-007, T1-008]

### AC-2 (partial — completes in Phase 2): Dual-DDL parity holds for `rf_events`

- target_surfaces:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
- propagation_contract: `rf_events` carries an identical column set (modulo allowed type drift) across both DDL files, registered in both migration-table getters.
- resilience: N/A (structural AC).
- visual_evidence_required: false
- verified_by: [T1-002, T1-008]

---

## Quality Gates

- [ ] Migrations run successfully on both SQLite and Postgres (T1-001)
- [ ] `COLUMN_PARITY_DRIFT_ALLOWLIST` entry + direct-count test green (T1-002)
- [ ] Idempotency regression test green — zero duplicate rows on re-POST (T1-005)
- [ ] Dead-letter queue captures permanently-failed events (T1-004)
- [ ] Feature flag gates the route correctly, default `true` (T1-006)
- [ ] `/api/v1/capabilities` and `/api/health/detail` advertise the new source (T1-007)
- [ ] `task-completion-validator` sign-off recorded (T1-008)
- [ ] OpenTelemetry spans + structured logging (trace_id/span_id) present on the new route

---

## Key Files Modified

| File Path | Purpose | Subagent |
|-----------|---------|----------|
| `backend/routers/ingest.py` | New route added to existing `ingest_router` | python-backend-engineer |
| `backend/application/models/ingest.py` | Pydantic request/response models for the RF event shape | python-backend-engineer |
| `backend/application/services/ingest/rf_events_ingest.py` | New service: idempotent persistence + dead-letter wiring | python-backend-engineer |
| `backend/db/sqlite_migrations.py` | `rf_events` table DDL (SQLite) | data-layer-expert |
| `backend/db/postgres_migrations.py` | `rf_events` table DDL (Postgres) | data-layer-expert |
| `backend/application/services/agent_queries/ingest_sources.py` | New `rf` source entry | python-backend-engineer |
| `backend/routers/client_v1.py` | Capability advert string | python-backend-engineer |

---

## Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-21

[Return to Parent Plan](../research-foundry-run-telemetry-v1.md)
