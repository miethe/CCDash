---
schema_version: 2
doc_type: implementation_plan
title: "CCDash DB Design Remediation \u2014 Implementation Plan"
status: completed
created: '2026-06-03'
updated: '2026-06-03'
feature_slug: ccdash-db-design-remediation
feature_version: v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: null
scope: Fix silent project-registry persistence failure, standardize DB-write reliability
  and observability, close migration concurrency/parity gaps, activate dormant storage-retention
  subsystem, and ratify ADR-006/007.
effort_estimate: ~40 pts
architecture_summary: Five-phase remediation of CCDash DB design gaps confirmed by
  SPIKE audit. Phases sequence from smallest/most-reversible (P1 registry correctness)
  through generalization (P2 reliability), migration integrity (P3), storage hygiene
  activation (P4), and documentation ratification (P5). P3 and P4 run in parallel
  after P1 verifies. Destructive multi-GB session reclaim is owned by ccdash-enterprise-liveness-storage-v1
  and is referenced, not re-scoped here.
priority: high
risk_level: high
owner: Nick Miethe
contributors: []
category: product-planning
tags:
- implementation
- infrastructure
- database
- remediation
- registry
- migration
- reliability
milestone: null
changelog_required: false
deferred_items_spec_refs:
- docs/project_plans/design-specs/sqlite-evidence-json-not-null-backfill.md
- docs/project_plans/design-specs/retry-on-locked-repo-retrofit.md
findings_doc_ref: .claude/findings/ccdash-db-design-remediation-findings.md
spike_ref: docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md
adr_refs:
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
charter_ref: docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md
changelog_ref: null
test_plan_ref: null
plan_structure: independent
progress_init: auto
commit_refs:
- 4ef37ac
- 7d04401
- '3254722'
- '9633900'
- 587ce60
- baeb768
- 3a8bef9
- 0d69591
pr_refs: []
files_affected:
- backend/project_manager.py
- backend/tests/test_retention_prune.py
- docs/guides/db-vacuum-runbook.md
- docs/project_plans/design-specs/sqlite-evidence-json-not-null-backfill.md
- backend/db/repositories/projects.py
- backend/db/repositories/base.py
- backend/db/repositories/execution.py
- backend/db/repositories/sessions.py
- backend/db/sqlite_migrations.py
- backend/db/migration_governance.py
- backend/db/migrations.py
- backend/runtime/bootstrap.py
- backend/runtime/container.py
- backend/runtime_ports.py
- backend/config.py
- backend/observability/otel.py
- backend/adapters/jobs/runtime.py
- backend/tests/test_db_project_registry.py
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
- CLAUDE.md
related_documents:
- docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
- docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md
- docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md
- .claude/worknotes/ccdash-db-design-remediation/decisions-block.md
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
- docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
wave_plan:
  serialization_barriers:
  - backend/db/repositories/base.py
  - backend/project_manager.py
  - CLAUDE.md
  phases:
  - id: P1
    depends_on: []
    isolation: shared
    parallelizable: false
    owner_skills: []
    files_affected:
    - backend/project_manager.py
    - backend/db/repositories/projects.py
    - backend/runtime/container.py
    - backend/runtime_ports.py
    - backend/config.py
    - backend/tests/test_db_project_registry.py
  - id: P2
    depends_on:
    - P1
    isolation: shared
    parallelizable: false
    files_affected:
    - backend/db/repositories/base.py
    - backend/db/repositories/execution.py
    - backend/db/repositories/sessions.py
    - backend/runtime/bootstrap.py
    - backend/observability/otel.py
  - id: P3
    depends_on:
    - P1
    isolation: shared
    parallelizable: true
    files_affected:
    - backend/db/sqlite_migrations.py
    - backend/db/migrations.py
    - backend/db/migration_governance.py
    - backend/db/repositories/projects.py
  - id: P4
    depends_on:
    - P1
    isolation: shared
    parallelizable: true
    files_affected:
    - backend/adapters/jobs/runtime.py
    - backend/config.py
  - id: P5
    depends_on:
    - P2
    - P3
    - P4
    isolation: shared
    parallelizable: false
    files_affected:
    - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
    - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
    - CLAUDE.md
  waves:
  - - P1
  - - P2
  - - P3
    - P4
  - - P5
---

# Implementation Plan: CCDash DB Design Remediation

**Plan ID**: `IMPL-2026-06-03-CCDASH-DB-DESIGN-REMEDIATION`
**Date**: 2026-06-03
**Author**: Implementation Planner
**Human Brief**: `docs/project_plans/human-briefs/ccdash-db-design-remediation.md`
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md`
- **SPIKE Findings**: `docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md`
- **Decisions Block**: `.claude/worknotes/ccdash-db-design-remediation/decisions-block.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Liveness PRD** (owns destructive storage reclaim): `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`

**Complexity**: XL (Tier 3) | **Total Estimated Effort**: ~40 pts | **Timeline**: 4–6 weeks

---

## Executive Summary

This plan remediates five SPIKE-confirmed DB design gaps in CCDash across five phased deliverables. Phase 1 ships the minimal, reversible registry correctness fix first and independently (11 pts): the silent `_flush_snapshot_to_db` no-op is replaced with fail-loud + retry behavior, the dual project managers are collapsed per ADR-006, and the bootstrap is re-sequenced outside the heavy sync window. Phase 2 generalizes the locked-retry helper into `repositories/base.py` and wires DB-write observability into `/api/health/detail` and Prometheus (8 pts). Phase 3 (13 pts, parallel with P4) closes migration concurrency and column-parity gaps; Phase 4 (5 pts) activates the dormant retention subsystem behind its flag with a snapshot-protected VACUUM runbook. Phase 5 ratifies ADR-006/007 and documents conventions (3 pts). The destructive multi-GB `session_logs`/`telemetry_events` reclaim is owned by the enterprise-liveness-storage PRD and is referenced only in P4.

**Key success outcomes:**
- Registry rows survive every cold restart (proven by direct `repo.count()` + lock-injection test)
- Every DB write path retries via a shared helper and surfaces failures in health + Prometheus
- SQLite and Postgres migration paths reach column-level parity with a concurrency guard
- 2.23 GB freelist reclaimed; retention subsystem active behind its flag

---

## Implementation Strategy

### Architecture Sequence

This remediation follows a repair-then-generalize pattern rather than the standard new-feature layering sequence:

1. **P1 — Registry Correctness** (ADR-006): Fix the root cause at `project_manager.py:447–460`; collapse dual managers; sequence bootstrap correctly
2. **P2 — Reliability Generalization** (ADR-007): Extract the P1 retry pattern into `repositories/base.py`; wire health and metrics
3. **P3 — Migration Integrity** (parallel post-P1): Concurrency guard, column-parity diff, `ensure_table` elimination, idempotency tests
4. **P4 — Storage Hygiene** (parallel post-P1, snapshot-gated): Activate retention flag, VACUUM runbook
5. **P5 — Docs & Ratification** (converge): ADR status → accepted, CLAUDE.md conventions, deferred specs, AAR

### Critical Path

```
ADR-006 ratified (done 2026-06-03) ──> P1 (Registry Correctness)
                                          │
                                          ├──> P2 (Reliability + Observability)   [P1 must verify first]
                                          │
                                          ├──> P3 (Migration Integrity)           [parallel with P4]
                                          │
                                          └──> P4 (Storage Hygiene)               [snapshot-gated; parallel with P3]
P2 + P3 + P4 ──────────────────────────────────────────────────────> P5 (Docs/ADRs)
```

**Hard gate**: P1 cold-start smoke must pass before P4 may begin. P4 also requires operator DB snapshot confirmation.

### Parallel Opportunities

- P3 and P4 may run concurrently after P1 verifies (independent code surfaces)
- P4 start requires operator snapshot confirmation; if that is delayed, P3 can proceed solo
- P5 documentation tasks within Phase 5 are parallelizable after P2/P3/P4 complete

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| P1 | Registry Correctness & Authority | 11 pts | data-layer-expert (primary), python-backend-engineer (secondary) | sonnet | Opus review of ADR-006 conformance at P1 exit; karen gate after P1 |
| P2 | DB-Write Reliability & Observability | 8 pts | python-backend-engineer (primary), data-layer-expert (secondary) | sonnet | Generalizes P1 retry; runtime smoke on `/api/health/detail` |
| P3 | Migration Integrity & Parity | 13 pts | data-layer-expert (sole owner) | sonnet | Parallel with P4 after P1; karen gate after P3 |
| P4 | Storage Hygiene Activation | 5 pts | platform-engineer (primary), data-layer-expert (secondary) | sonnet + opus (go/no-go on live-DB step) | Blocked on operator snapshot; snapshot-first gate mandatory |
| P5 | Docs, ADRs & Deferred Items | 3 pts | documentation-writer | haiku | Converges last; karen end-of-feature review |
| **Total** | — | **~40 pts** | — | — | Tier 3 |

> Estimation rationale lives in the Human Brief §2. See `docs/project_plans/human-briefs/ccdash-db-design-remediation.md`.

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| OQ-01 | research-needed | `migrations_applied` ledger: shared vs backend-specific schema not yet decided | Decided at P3 authoring; if backend-specific, a parity spec is needed | `docs/project_plans/design-specs/migrations-applied-ledger-schema.md` (conditionally) |
| OQ-02 | research-needed | WAL-checkpoint strategy: config PRAGMA vs retention job; timing implications unclear | Decided at P4 authoring; encode in VACUUM runbook | N/A — absorbed into runbook doc if in-scope |
| P2-3-telemetry | backlog | `telemetry_events` bounded growth and index-bloat review is referenced only; owned by liveness PRD | When liveness PRD P1 ships and retention is running, verify via metrics | N/A — liveness PRD owns |

All deferred items will receive design-spec authoring tasks in P5 (T5-005) if the decisions above remain open at execution time.

### In-Flight Findings

Lazy-creation rule: the findings doc is not pre-created. Create `.claude/findings/ccdash-db-design-remediation-findings.md` only on the first real execution finding. If P3 column-parity diff surfaces genuine drift beyond the in-phase threshold (>2 pts), this is the primary trigger.

---

## Risk Mitigation

### Technical Risks

| Risk | Impact | Likelihood | Mitigation | Phase |
|------|:------:|:----------:|-----------|:-----:|
| VACUUM/retention-prune on 11 GB live DB locks for minutes | High | Medium | Snapshot-before-touch mandatory; validate VACUUM on snapshot copy only; Opus go/no-go before any live-DB step | P4 |
| Registry bootstrap re-sequencing regresses worker binding | Medium | Medium | Mandatory cold-start smoke: assert `/api/projects` full set + worker binding before P1 exits | P1 |
| SQLite migration concurrency guard deadlocks dual-process boot | Medium | Low | Mirror Postgres advisory-lock intent: acquire-migrate-release with timeout; test concurrent api+worker boot | P3 |
| Column-parity diff surfaces real existing drift expanding P3 scope | Medium | Medium | On first drift >2 pts: record to lazy findings doc, triage; do not balloon P3 | P3 |
| Dual-manager collapse breaks `manager=` explicit-JSON override callers | Low | Low | Grep all callers before retiring; preserve `import_from_json()` / `export_to_json()` | P1 |

---

## Reviewer Gates

| After Phase | Reviewer | Type |
|-------------|----------|------|
| P1 | task-completion-validator | Per-phase completion check |
| P1 | karen | Tier 3 milestone review (ADR-006 conformance) |
| P2 | task-completion-validator | Per-phase completion check |
| P3 | task-completion-validator | Per-phase completion check |
| P3 | karen | Tier 3 milestone review (migration integrity) |
| P4 | task-completion-validator | Per-phase completion check |
| P5 / Feature end | karen | End-of-feature Tier 3 review |

---

## Phase Detail Files

The full task tables, acceptance criteria, and quality gates for each phase are in the phase files below. Load only the phase currently being executed.

| Phase | File |
|-------|------|
| P1 — Registry Correctness & Authority (11 pts) | [phase-1-registry-correctness.md](./ccdash-db-design-remediation-v1/phase-1-registry-correctness.md) |
| P2 — DB-Write Reliability & Observability (8 pts) | [phase-2-reliability-observability.md](./ccdash-db-design-remediation-v1/phase-2-reliability-observability.md) |
| P3 — Migration Integrity & Parity (13 pts) | [phase-3-migration-integrity.md](./ccdash-db-design-remediation-v1/phase-3-migration-integrity.md) |
| P4 — Storage Hygiene Activation (5 pts) | [phase-4-storage-hygiene.md](./ccdash-db-design-remediation-v1/phase-4-storage-hygiene.md) |
| P5 — Docs, ADRs & Deferred Items (3 pts) | [phase-5-docs-adrs.md](./ccdash-db-design-remediation-v1/phase-5-docs-adrs.md) |

---

## Success Metrics

| Metric | Baseline | Target | Verified By |
|--------|----------|--------|-------------|
| Registry rows survive cold restart | 0 (flush fails silently) | 5/5 rows present after restart, asserted by `repo.count()` | T1-006 + P1 cold-start smoke |
| Lock-injection test: flush fails loud | None | Asserts `Exception` raised, never silent True | T1-005 |
| `/api/health/detail` registry + DB fields present | Not present | All 5 fields non-null after warm start | T2-003 + T2-004 CLI smoke |
| `ccdash_db_write_failures_total` counter | Not present | Increments under injected failure | T2-006 |
| Column-parity test | Not present | Zero drift for all shared tables | T3-002 |
| Migration idempotency | Single-run only | `run_migrations` twice: no error, stable schema | T3-003 |
| SQLite migration concurrency | No guard | Two concurrent `run_migrations`: safe | T3-001 |
| Freelist pages post-VACUUM | 543,926 (2.23 GB) | <1,000 on snapshot copy | T4-002 |

---

**Progress Tracking**: `.claude/progress/ccdash-db-design-remediation/`
