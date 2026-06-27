---
schema_version: 2
doc_type: implementation_plan
title: "CCDash Enterprise Liveness Hotfix & Storage Hygiene \u2014 Implementation\
  \ Plan"
status: completed
created: 2026-05-30
updated: '2026-05-30'
feature_slug: ccdash-enterprise-edition-v1
feature_version: v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
plan_ref: null
scope: 'Two-phase enterprise fix: default-on ingestion + fail-loud readyz (Phase 0);
  DB retention, index backfills, N+1 rewrites, and session-badge materialization (Phase
  1).'
effort_estimate: "Phase 0 ~M (12 tasks S/M + 1 L + 1 seam); Phase 1 ~L (19 tasks S\u2013\
  L + 1 seam + 1 smoke)"
architecture_summary: No new subsystems. Phase 0 = default flips, compose wiring,
  additive guards. Phase 1 = schema-additive DDL, retention jobs (flag-gated), index
  backfills, batched writes, and one staged destructive drop (flag-gated default-OFF).
priority: critical
risk_level: high
owner: nick
contributors:
- Claude Opus 4.8
- Claude Sonnet 4.6
changelog_required: true
related_documents:
- docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
- docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
- docs/project_plans/planning/ccdash-enterprise-edition-v1/03-enterprise-edition-gap-analysis.md
- .claude/worknotes/ccdash-enterprise-edition-v1/decisions-block.md
- .claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md
references:
  context:
  - .claude/worknotes/ccdash-enterprise-edition-v1/decisions-block.md
  specs: []
  related_prds: []
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
spike_ref: null
charter_ref: null
changelog_ref: null
plan_structure: unified
progress_init: auto
tags:
- infrastructure
- enterprise
- liveness
- storage
- performance
- database
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- compose.yaml
- compose.hosted.yml
- entrypoint.sh
- backend/config.py
- backend/runtime/container.py
- backend/runtime/bootstrap.py
- backend/runtime/bootstrap_worker.py
- backend/db/connection.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/sync_engine.py
- backend/db/entity_graph.py
- backend/db/file_watcher.py
- backend/db/repositories/analytics.py
- backend/db/repositories/sessions.py
- backend/project_manager.py
- backend/project_paths/providers/filesystem.py
- backend/application/services/source_identity.py
- backend/adapters/jobs/runtime.py
- backend/services/usage_attribution.py
- backend/routers/api.py
- backend/services/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/db/repositories/postgres/_transactions.py
- .github/workflows/
wave_plan:
  serialization_barriers:
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - compose.yaml
  phases:
  - id: P0
    depends_on: []
    isolation: shared
    parallelizable: true
    files_affected:
    - compose.yaml
    - entrypoint.sh
    - backend/config.py
    - backend/runtime/container.py
    - backend/runtime/bootstrap.py
    - backend/db/file_watcher.py
    - backend/project_manager.py
    - backend/project_paths/providers/filesystem.py
    - backend/application/services/source_identity.py
    - backend/db/postgres_migrations.py
    - .github/workflows/
  - id: P1
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    files_affected:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
    - backend/db/connection.py
    - backend/db/sync_engine.py
    - backend/db/entity_graph.py
    - backend/db/repositories/analytics.py
    - backend/db/repositories/sessions.py
    - backend/db/repositories/postgres/sessions.py
    - backend/db/repositories/postgres/_transactions.py
    - backend/services/usage_attribution.py
    - backend/routers/api.py
    - backend/services/sessions.py
  waves:
  - - P0
  - - P1
success_metrics:
- docker compose --profile enterprise --profile postgres up ingests >=1 session from a dropped fixture .jsonl with no extra flags
- Worker readyz returns 200 iff resolved watch-paths > 0; zero paths return 503 with configured_no_paths reason
- CI workflow is green on every PR touching deploy/runtime/** or backend/runtime/**
- DB shrinks >= 3 GB measured via dbstat byte totals
- SELECT COUNT(*) FROM analytics_entries drops ~50x (1.8M -> ~30-90K rows)
- _capture_analytics issues single-digit batched queries per snapshot (measured via query counter at sync_engine.py:5787)
- entity_graph rebuild executes as 1 commit (counter at entity_graph.py:40)
- GET /api/sessions session-list serves materialized badge columns (no per-session log fetch)
- SQLite and Postgres report identical SCHEMA_VERSION
acceptance_criteria:
- 'Phase 0 exit gate: P0-013 CI e2e smoke passing'
- 'Phase 1 exit gate: >=3 GB reclaimed'
- 'Phase 1 exit gate: analytics_entries ~50x reduction'
- 'Phase 1 exit gate: _capture_analytics single-digit queries/snapshot'
- 'Phase 1 exit gate: entity_graph 1 commit/rebuild'
definition_of_done: 'Both phase quality gates pass: Feature exit gate is P0-013 CI e2e smoke passing; Phase 1 exit requires measurable DB-size/row-count/query-count assertions (>=3 GB reclaimed; analytics_entries ~50x reduction; _capture_analytics single-digit queries/snapshot; entity_graph 1 commit/rebuild). task-completion-validator per phase; karen at feature end.'
planning_maturity: shipped
---

# Implementation Plan: CCDash Enterprise Liveness Hotfix & Storage Hygiene

**Plan ID**: `IMPL-2026-05-30-CCDASH-ENTERPRISE-LIVENESS-STORAGE`
**Date**: 2026-05-30
**Author**: Claude Sonnet 4.6 (implementation-planner)
**Human Brief**: N/A — infrastructure fix with enumerable test scenarios; decisions block carries the estimation rationale
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`
- **Decisions block**: `.claude/worknotes/ccdash-enterprise-edition-v1/decisions-block.md`
- **Bundle roadmap**: `docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md`

**Complexity**: Phase 0 = M | Phase 1 = L | Tier 3
**Total Estimated Effort**: Phase 0 ≈ 14 pts | Phase 1 ≈ 21 pts
**Reviewer gates**: `task-completion-validator` per phase; `karen` at feature end

## Executive Summary

A default `docker compose --profile enterprise --profile postgres up` currently ingests zero live session data and fails silently. This plan fixes that in two phases with no new subsystems.

**Phase 0 — Enterprise Liveness Hotfix** (M complexity): Flip three compounding defaults (ingestion enabled, worker-watch in default topology, force-polling on bind mounts), auto-derive container path aliases from `ResolvedProjectPaths`, make `readyz` fail loud on zero watch paths, make `projects.json` writable/atomic, add `frontend depends_on: api`, add `pg_advisory_lock` around migrations, and gate the whole fix behind a CI `docker compose up` e2e smoke test.

**Phase 1 — Storage Hygiene & DB Performance** (L complexity): Shrink the 9.5 GB DB ≥ 3 GB via retention/TTL and staged transcript dedupe (flag-gated default-OFF), add four missing indexes, apply SQLite pragmas (dev-only), kill the worst N+1 storms (`_capture_analytics` 12–15K → single-digit queries, `entity_graph` 25K commits → 1, session-list badge derivation), and reconcile the schema version gap. Destructive tasks carry `CCDASH_DROP_SESSION_LOGS_ENABLED` / `CCDASH_ANALYTICS_RETENTION_*` / `CCDASH_TELEMETRY_RETENTION_*` flag gates (all default OFF).

**Feature exit gate**: P0-013 CI e2e smoke passing. Phase 1 exit requires measurable DB-size/row-count/query-count assertions (≥3 GB reclaimed; `analytics_entries` ~50× reduction; `_capture_analytics` single-digit queries/snapshot; `entity_graph` 1 commit/rebuild).

## Implementation Strategy

### Architecture Sequence

This feature departs from the standard 8-layer sequence because both phases are infrastructure-only (no new UI layer, no new user-facing API surface beyond side-effects). The sequence within each phase follows:

1. **Compose / entrypoint wiring** — default flips, env vars, service ordering
2. **Config + container bootstrap** — Python-side readers, readyz contract, advisory lock
3. **DB schema (additive DDL)** — indexes, new columns, pragma gates, UNIQUE-in-DDL
4. **Repository / sync-engine rewrites** — N+1 kills, `executemany`, retention, canonical delete
5. **Seam verification** — integration_owner sign-off on cross-owner contract
6. **CI smoke gate** — e2e test as the definitive acceptance instrument

### Parallel Work Opportunities

**Phase 0 batch_0**: Seven tasks with no cross-dependencies run in parallel (P0-004, P0-005, P0-006, P0-007, P0-009, P0-014, P0-SEC-CORS).

**Phase 1 batch_0**: Nine additive/non-destructive tasks run in parallel (P1-004, P1-005, P1-006, P1-008, P1-009, P1-011, P1-012, P1-017, P1-018). See phase file for full batch dependency graph.

### Critical Path

P0-001 → P0-015 → P0-008 → P0-003 → P0-013 (the Phase 0 critical path through the e2e gate)

P1-010 (badge materialization) → P1-002 (staged drop, batch_4) → P1-016 (FTS5, optional)

P1-001 → P1-013 → P1-014 (retention chain)

P1-015 (schema-version reconcile) is the absolute last task — depends on all additive DDL landing.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 0 | Enterprise Liveness Hotfix | 14 pts | `devops-architect`, `python-backend-engineer` | sonnet | 4 batches; exit gate = P0-013 e2e smoke |
| 1 | Storage Hygiene & DB Performance | 21 pts | `data-layer-expert`, `python-backend-engineer` | sonnet | 6 batches; 3 destructive tasks flag-gated default-OFF |
| **Total** | — | **35 pts** | — | — | Tier 3; `karen` at feature end |

## Integration Owners

**Phase 0 seam** (compose↔config↔runtime): `devops-architect` is the integration owner for the cross-owner seam covering P0-001, P0-006, P0-015, and P0-008. The seam task is P0-SEAM-0 (see phase file).

**Phase 1 seam** (DDL↔repo↔service): `data-layer-expert` is the integration owner for the cross-owner seam covering P1-010 DDL / P1-002 consumer migration / P1-019 entity_links column. The seam task is P1-SEAM-1 (see phase file).

## Phase Files

| Phase | File |
|-------|------|
| Phase 0 — Enterprise Liveness Hotfix | [phase-0-liveness.md](./ccdash-enterprise-liveness-storage-v1/phase-0-liveness.md) |
| Phase 1 — Storage Hygiene & DB Performance | [phase-1-storage.md](./ccdash-enterprise-liveness-storage-v1/phase-1-storage.md) |

## Deferred Items & In-Flight Findings Policy

### Deferred Items

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| P1-016 FTS5/tsvector | dependency-blocked | Depends on P1-002 staging being complete; may slip to Phase 6 if staging window extends | P1-002 fully staged and consumers migrated | docs/project_plans/design-specs/fts5-session-search-v1.md |
| Phases 2–6 | scope-cut | Out of scope for this PRD; covered by the enterprise edition bundle roadmap | Enterprise edition Phase 1 complete and validated | — |

### In-Flight Findings

Lazy-creation rule applies. Path if needed: `.claude/findings/ccdash-enterprise-liveness-storage-v1-findings.md`.

## Risk Mitigation Summary

| Risk | Severity | Mitigation |
|------|----------|------------|
| Default-on ingestion triggers heavy blocking startup sync | HIGH | P0-015 light-mode reconcile lands with P0-001 (paired in batch_1); in-container `CCDASH_STARTUP_SYNC_LIGHT_MODE=true` defers heavy passes to the worker loop |
| `session_logs` drop irreversible | HIGH | Flag-gated `CCDASH_DROP_SESSION_LOGS_ENABLED` default OFF; staged after P1-010; DB snapshot before first run; filesystem JSONL is re-derivable SoT |
| Retention DELETE locks SQLite under load | MED | Batched `batch_size=1000` by `captured_at`; `busy_timeout`; worker-scheduled off request path |
| SCHEMA_VERSION no-op on existing DBs | MED | P1-015 lands LAST; `_ensure_index` idempotent backfills |
| Cross-owner seams (compose↔config↔runtime) | MED | Explicit integration_owner per phase; seam tasks in both phase files |
| Path-alias mis-map | MED | Log derived alias map at startup; fail-loud readyz (P0-003) catches zero-path result |

## Success Metrics

### Phase 0 Exit Gate (P0-013)

- `docker compose --profile enterprise --profile postgres up` ingests ≥1 session from a dropped fixture `.jsonl` with no extra flags.
- Worker `readyz` returns 200 iff resolved watch-paths > 0; zero paths return 503 with `configured_no_paths` reason.
- CI workflow is green on every PR touching `deploy/runtime/**` or `backend/runtime/**`.

### Phase 1 Exit Gate

- DB shrinks ≥ 3 GB measured via `dbstat` byte totals.
- `SELECT COUNT(*) FROM analytics_entries` drops ~50× (1.8M → ~30–90K rows).
- `_capture_analytics` issues single-digit batched queries per snapshot (measured via query counter at `sync_engine.py:5787`).
- `entity_graph` rebuild executes as 1 commit (counter at `entity_graph.py:40`).
- `GET /api/sessions` session-list serves materialized badge columns (no per-session log fetch).
- SQLite and Postgres report identical `SCHEMA_VERSION`.

## Wrap-Up: Feature Guide & PR

After both phase quality gates pass:

1. Delegate `documentation-writer` (haiku) to create `.claude/worknotes/ccdash-enterprise-edition-v1/feature-guide.md` covering Phase 0 + Phase 1.
2. Open PR with title ≤ 70 chars referencing the feature guide and CHANGELOG `[Unreleased]` entry.

---

**Progress Tracking**:
- `.claude/progress/ccdash-enterprise-edition-v1/phase-0-progress.md`
- `.claude/progress/ccdash-enterprise-edition-v1/phase-1-progress.md`
