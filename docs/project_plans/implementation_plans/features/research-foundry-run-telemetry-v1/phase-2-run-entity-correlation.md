---
title: "Phase 2: Run entity + intelligence + correlation"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-21
updated: 2026-07-21
feature_slug: "research-foundry-run-telemetry"
feature_version: "v1"
phase: 2
phase_title: "Run entity + intelligence + correlation"
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
entry_criteria:
  - "Phase 1 exit gate passed: rf_events ingest idempotent + dual-DDL parity green"
exit_criteria:
  - "research_runs rollup queryable via REST (+ MCP/CLI) with linked sessions"
  - "D-001-shape dedup regression test green"
  - "karen milestone review passed before Phase 3 starts"
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
  - docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md
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
risk_level: high
category: "product-planning"
tags: [phase-plan, implementation, correlation, dedup, algorithmic-risk]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/repositories/entity_graph.py
  - backend/application/services/agent_queries/run_intelligence.py
  - backend/routers/agent.py
  - backend/mcp/server.py
  - backend/cli/
---

# Phase 2: Run entity + intelligence + correlation

**Parent Plan**: [Research Foundry Run Telemetry — Implementation Plan](../research-foundry-run-telemetry-v1.md)
**Duration**: ~1.5–2 weeks
**Effort**: 10 story points
**Dependencies**: Phase 1 complete (stable `rf_events` ingest contract)
**Team Members**: `data-layer-expert`, `python-backend-engineer`, `backend-architect`, `karen`, `task-completion-validator`

---

## Phase Overview

This is the **algorithmic risk hotspot** of the feature (decisions block §3, Risk 1 and Risk 2 —
both `high`/`medium` severity). It derives a `research_runs` rollup from `rf_events`, exposes it
through a new transport-neutral `run_intelligence.py` query service, and correlates runs to
sessions via `entity_graph.py` link rows keyed by a **genuine UUID** `run_id` — never RF's semantic
slugs. Any rollup that sums cost/workload across a run↔session join **must** apply D-001 dedup
discipline (`DISTINCT`/`GROUP BY`-before-sum) from day one, with a regression test shipped as an
exit gate rather than deferred.

### Goals

- Derive/upsert `research_runs` from `rf_events`, minting a CCDash UUID `run_id` when RF's own
  value doesn't parse as one (FR-6).
- Ship `run_intelligence.py` + REST (+ MCP/CLI) surfaces (FR-7, FR-8, FR-11).
- Correlate runs to sessions via `entity_graph.py` entity-link rows, `kind='research_run'` (FR-9, D2).
- Prove zero cross-run/cross-session cost double-counting with a shipped regression test (FR-10, D5).

### Architecture Focus

- **Layer**: Database (dual DDL) + Service (`agent_queries`) + API
- **Patterns**: `system_metrics.py`/`artifact_intelligence.py` as the transport-neutral service
  pattern; `SqliteEntityLinkRepository` for correlation, **not** `aos_correlation.py` (D2 is a hard
  boundary — zero changes to that file)
- **Standards**: ADR-007 (dual-DDL parity, direct-count test); D-001 Option A dedup discipline
  (`docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`)

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|----------------------|----------|-------------|-------|--------|---------------|
| T2-001 | `research_runs` dual-DDL rollup table + UUID minting | New table (dual DDL); derive/upsert one row per run from `rf_events`; if RF's `run_id` string does not parse as UUID4, mint a CCDash UUID and store RF's raw value in a separate `rf_run_id` display column | Rollup derivable from seeded `rf_events` fixtures with zero live RF traffic; RF's non-UUID ids never become a primary/join key | 2 pts | data-layer-expert | sonnet | adaptive | Phase 1 complete |
| T2-002 | Migration governance + parity/direct-count test (ADR-007 exit gate) | `research_runs` added to `COLUMN_PARITY_DRIFT_ALLOWLIST`; direct-count assertion test on both backends | `test_migration_governance.py` passes for `research_runs`; AC-2 fully closed (both tables now covered) | 0.5 pts | data-layer-expert | sonnet | adaptive | T2-001 |
| T2-003 | `run_intelligence.py` query service | New `backend/application/services/agent_queries/run_intelligence.py`, pattern-matched to `system_metrics.py`: run list (cursor-paginated) + run detail | Service is transport-neutral (no REST/MCP-specific logic inside it); returns DTOs, not ORM rows | 2 pts | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-004 | `GET /api/agent/research-runs` (+ `/{run_id}` detail) REST route | Wraps `run_intelligence.py` in `backend/routers/agent.py`; cursor pagination; `ErrorResponse` envelope | Endpoint returns run rollups with metrics + linked-session summary | 1 pt | python-backend-engineer | sonnet | adaptive | T2-003 |
| T2-005 | MCP/CLI thin wrappers | Wire `run_intelligence.py` into `backend/mcp/server.py` and `backend/cli/` per the transport-neutral pattern (FR-11) | MCP tool + CLI command both return the same shape as the REST route | 0.5 pts | python-backend-engineer | sonnet | adaptive | T2-003 |
| T2-006 | Run↔session correlation via `entity_graph.py` | `SqliteEntityLinkRepository` entity-link rows, `kind='research_run'`, keyed by the UUID `run_id`; RF's `intent_id`/`task_node_id` stored as display-only string attributes — **never** as join keys; zero changes to `aos_correlation.py` (D2 hard boundary) | A run with a discoverable correlated session gets a link row; `aos_correlation.py` diff is empty | 2 pts | backend-architect | sonnet | extended | T2-001 |
| T2-007 | D-001-shape dedup regression test (R1 verification task) | Regression test: two `research_runs` rows linked to the same session; roll up a combined cost/workload figure; assert the session's token count is counted **once**, not once per linked run — exact shape of the deferred D-001 bug, at the run↔session layer | AC-3 fully covered; test explicitly modeled on `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` Option A | 1 pt | backend-architect | sonnet | extended | T2-006 |
| T2-008 | `karen` milestone review | Strict QA pass on the correlation + dedup implementation (T2-006, T2-007) before Phase 3 begins consuming this contract — this is the decisions-block-mandated mid-feature gate, not a courtesy review | `karen` sign-off recorded; any gaps block Phase 3 kickoff | 0.5 pts | karen | sonnet | adaptive | T2-006, T2-007 |
| T2-009 | Phase 2 completion review | `task-completion-validator` verifies all Phase 2 ACs are genuinely met | Reviewer sign-off recorded before Phase 3 kickoff | 0.5 pts | task-completion-validator | sonnet | adaptive | T2-001 through T2-008 |

**Phase 2 total: 10 pts**

---

## Acceptance Criteria (structured)

### AC-2 (completes here): Dual-DDL parity holds for both new tables

- target_surfaces:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
- propagation_contract: `rf_events` and `research_runs` each carry an identical column set (modulo allowed type drift: `JSONB` vs `TEXT`, `SERIAL` vs `AUTOINCREMENT`) across both DDL files, registered in `get_sqlite_migration_tables()`/`get_postgres_migration_tables()`.
- resilience: N/A (structural AC).
- visual_evidence_required: false
- verified_by: [T2-002, T2-009]

### AC-3: Run↔session correlation never double-counts

- target_surfaces:
    - backend/db/repositories/entity_graph.py
    - backend/application/services/agent_queries/run_intelligence.py
- propagation_contract: Two `research_runs` rows linked to the same session, when rolled up for a combined cost/workload figure, produce a session-token count equal to the session's own stored total — counted once, not once per linked run.
- resilience: A run with zero linked sessions renders with an explicit "no linked session" state in any rollup that lists linkage, never a null-coalesced `0`.
- visual_evidence_required: false
- verified_by: [T2-007, T2-008, T2-009]

### AC-2-Field: FE-facing optional-field resilience contract for `research_runs` (R-P2)

Every field on the `run_intelligence.py` response DTO that is optional at the source (not every
RF event carries every metric) must be explicitly nullable on the DTO, never coerced to `0` or
`""`. This is the backend half of the R-P2 contract that Phase 3 (T3-005) consumes on the FE side.

- target_surfaces:
    - backend/application/services/agent_queries/run_intelligence.py
- propagation_contract: `estimated_cost_usd`, `citation_coverage`, `latency_ms`, `mode`, `selected_providers`, `linked_session_id`, `rf_run_id`, `intent_id`, `task_node_id` are all `Optional[...]` on the response DTO; absence serializes as JSON `null`, never `0`/`""`/`[]`.
- resilience: Consumers (including the Phase 3 FE hook) receive `null` for any metric RF's event didn't carry, and must not synthesize a default value on the backend side.
- visual_evidence_required: false
- verified_by: [T2-003, T2-009]

---

## Quality Gates

- [ ] `research_runs` derivable from seeded `rf_events` with zero live RF traffic (T2-001)
- [ ] Dual-DDL parity + direct-count test green for `research_runs` (T2-002)
- [ ] `run_intelligence.py` is transport-neutral; REST/MCP/CLI all return the same DTO shape (T2-003, T2-004, T2-005)
- [ ] `aos_correlation.py` has zero diff (D2 hard boundary verified) (T2-006)
- [ ] D-001-shape dedup regression test green (T2-007)
- [ ] `karen` milestone sign-off recorded (T2-008)
- [ ] `task-completion-validator` sign-off recorded (T2-009)
- [ ] Every optional DTO field is nullable, never defaulted server-side (AC-2-Field)

---

## Key Files Modified

| File Path | Purpose | Subagent |
|-----------|---------|----------|
| `backend/db/sqlite_migrations.py` | `research_runs` table DDL (SQLite) | data-layer-expert |
| `backend/db/postgres_migrations.py` | `research_runs` table DDL (Postgres) | data-layer-expert |
| `backend/db/repositories/entity_graph.py` | New `research_run` link kind | backend-architect |
| `backend/application/services/agent_queries/run_intelligence.py` | New query service | python-backend-engineer |
| `backend/routers/agent.py` | New REST route | python-backend-engineer |
| `backend/mcp/server.py` | MCP tool wrapper | python-backend-engineer |
| `backend/cli/` | CLI command wrapper | python-backend-engineer |

---

## Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-21

[Return to Parent Plan](../research-foundry-run-telemetry-v1.md)
