---
schema_version: 2
doc_type: phase_plan
title: "Phase 1 — Storage Hygiene & DB Performance"
status: approved
created: 2026-05-30
updated: 2026-05-30
phase: 1
phase_title: "Storage Hygiene & DB Performance"
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md
integration_owner: data-layer-expert
entry_criteria:
  - Phase 0 complete (all quality gates passed; P0-013 e2e smoke green)
  - Live data exists in the enterprise container DB (prerequisite for before/after measurement)
  - Phase 0 pg_advisory_lock in place (P0-011)
exit_criteria:
  - DB shrinks ≥ 3 GB (dbstat before/after)
  - analytics_entries bounded; COUNT drops ~50x
  - _capture_analytics issues single-digit queries per snapshot
  - entity_graph rebuild = 1 commit
  - GET /api/sessions serves materialized badge columns (no per-session log fetch)
  - SQLite and Postgres report identical SCHEMA_VERSION
  - task-completion-validator sign-off
---

# Phase 1 — Storage Hygiene & DB Performance

**Parent plan**: [ccdash-enterprise-liveness-storage-v1.md](../ccdash-enterprise-liveness-storage-v1.md)
**Integration owner**: `data-layer-expert` (DDL↔repo↔service seam for P1-010, P1-002, P1-019)
**Complexity**: L (7×S + 8×M + 3×L + 1 seam task + 1 runtime-smoke task)
**Estimate**: ~21 pts
**Destructive tasks**: P1-001, P1-002, P1-003 — all flag-gated default-OFF; see flag-gate column

## Phase Overview

Shrink the 9.5 GB DB and kill the worst N+1 query storms. All destructive tasks are gated behind feature flags defaulting OFF and require a DB snapshot before first run. The filesystem JSONL remains the re-derivable source of truth throughout.

**P0-012** (canonical-source-key delete path) folds into this phase's batch_1 because it is schema-adjacent and data-integrity-critical; it was originally scoped in Phase 0 but the decisions block explicitly defers it here.

## Batch Dependency Graph

```
batch_0 (parallel, additive/non-destructive, no cross-deps):
  P1-004, P1-005, P1-006, P1-008, P1-009, P1-011, P1-012, P1-017, P1-018

batch_1 (schema/materialization; after batch_0 seams land):
  P1-019 (after P1-008), P1-010 (badge materialization), P0-012 (canonical delete)

batch_2 (destructive retention — flag-gated, batched, worker-scheduled):
  P1-001 (then P1-013, P1-014 in order), P1-003 (parallel with P1-001)

batch_3 (N+1 perf, needs indexes from batch_0):
  P1-007 (after P1-004)

batch_4 (staged drop — flag-gated default-OFF; after P1-010 + all 6 consumers migrated):
  P1-002, then P1-016 (optional/defer if staging incomplete)

batch_5 (version bump — LAST; after every additive DDL):
  P1-015
```

## Task Table

**Destructive task flag gates**:
- P1-001: `CCDASH_ANALYTICS_RETENTION_ENABLED` (default OFF); `CCDASH_ANALYTICS_RETENTION_DAYS` (default 90)
- P1-003: `CCDASH_TELEMETRY_RETENTION_ENABLED` (default OFF); `CCDASH_TELEMETRY_RETENTION_DAYS` (default 30)
- P1-002: `CCDASH_DROP_SESSION_LOGS_ENABLED` (default OFF); staged after P1-010 and all 6 consumers migrated

**All tasks**: `assigned_model: sonnet`, `Effort: adaptive`

| Task ID | Title | Anchors | Change | Acceptance Criteria | Cplx | Assigned To | Flag Gate | Depends On | Batch |
|---------|-------|---------|--------|---------------------|------|-------------|-----------|------------|-------|
| P1-004 | Backfill idx_sessions_project_status_updated via _ensure_index | `sqlite_migrations.py:161-162,1362-1367` | Add `_ensure_index` call to backfill the declared-but-absent composite index on live DBs | Index present in live (non-fresh) DB after migration run; `_ensure_index` call is idempotent (`IF NOT EXISTS`); EXPLAIN on status-filtered session query shows index use | S | data-layer-expert | — | — | 0 |
| P1-005 | idx_sessions_source_file + composite index | `repositories/sessions.py:161-167`; `sync_engine.py:4121-4130` | Add `idx_sessions_source_file` and `idx_sessions_project_source_file` via `_ensure_index` | Both indexes present after backfill; EXPLAIN on `list_by_source()` shows index use (no SCAN sessions); watch-event delete/lookup no longer full table scans | S | data-layer-expert | — | — | 0 |
| P1-006 | SQLite pragmas (dev-only profile gate) | `connection.py:50-54` | Add `cache_size=-131072` (128 MB), `synchronous=NORMAL`, `mmap_size`, `wal_autocheckpoint=1000`, `temp_store=MEMORY`; gate on SQLite path only (Postgres early-returns) | Pragmas applied when DB backend is SQLite; Postgres path does not execute pragma block; `PRAGMA cache_size` reads -131072 after connection; no pragma applied on enterprise/Postgres deployments | S | python-backend-engineer | — | — | 0 |
| P1-008 | entity_graph.upsert single-tx executemany | `entity_graph.py:27,41` | Replace per-link commit loop with a single-transaction `executemany` call | A full `entity_graph` rebuild issues 1 commit (not 25K); functional output (link rows inserted) is identical; counter at `entity_graph.py:40` confirms single commit | M | python-backend-engineer | — | — | 0 |
| P1-009 | executemany inserts (telemetry/attribution/session-log) | `sync_engine.py:1428-1456`; `usage_attribution.py:26,53`; `repositories/sessions.py:730-753` | Replace row-by-row INSERT loops with `executemany` in telemetry, usage_attribution, and session-log write paths | All three INSERT paths use executemany; no regression in inserted row count; sync INSERT batch size measurably reduced (Python round-trips down 10–50×) | M | python-backend-engineer | — | — | 0 |
| P1-011 | Postgres atomic upsert_logs/file_updates | `repositories/postgres/sessions.py:88+`; `_transactions.py` | Wrap `upsert_logs` and `upsert_file_updates` in `postgres_transaction` (DELETE+N-INSERT atomicity) | Both operations are atomic under Postgres; partial failures roll back; `_transactions.py` utility is used; no change to SQLite path | M | data-layer-expert | — | — | 0 |
| P1-012 | Postgres entity_links UNIQUE into initial DDL | `postgres_migrations.py:1491-1498` | Move the `entity_links` UNIQUE constraint into the initial `_TABLES` DDL block (not a post-DDL ALTER) | Fresh Postgres install creates entity_links with UNIQUE constraint from DDL; existing installs upgraded via the existing migration; no duplicate-insert errors on concurrent upserts | M | data-layer-expert | — | — | 0 |
| P1-017 | Manifest JSONL session-scan skip | `sync_engine.py:4107-4119,4239-4278` | Add inode/mtime manifest-based skip for session JSONL scan (parity with existing .md light-mode skip) | Sessions at unchanged inodes/mtimes are skipped in the scan pass; manifest is updated on change; STARTUP_SYNC_LIGHT_MODE path benefits; no regression in changed-file detection | M | python-backend-engineer | — | — | 0 |
| P1-018 | Batch startup backfill loops | `sync_engine.py:2058-2095` | Replace sequential single-row SELECT loops in startup backfill with batched queries | Startup backfill issues batched queries (not 37K single-row SELECTs); batch size configurable; functional output identical | M | python-backend-engineer | — | — | 0 |
| P1-019 | entity_links.project_id + idx_links_project (Phase 2 prereq) | `sqlite_migrations.py:37-56`; pg entity_links DDL; `entity_graph.py` | Add `project_id` column to `entity_links` and `idx_links_project` index (both SQLite and Postgres migrations) | `entity_links` table has `project_id` column in both SQLite and Postgres; `idx_links_project` index exists; `entity_graph.py` populates project_id on upsert; column is nullable with default null for existing rows; Phase 2 can consume it for scoped fingerprint | M | data-layer-expert | — | P1-008 | 1 |
| P1-010 | Materialize session badge columns | `api.py:624-660`; `services/sessions.py:87-118`; sessions DDL; `repositories/sessions.py` | Add materialized columns (`models_used_json`, `agents_used_json`, `skills_used_json`, `command_slug`, `latest_summary`, `subagent_type`) to sessions table; populate at sync time; `GET /api/sessions` reads from columns instead of per-session log fetch | Materialized columns present on sessions table (SQLite + Postgres DDL); populated correctly at sync; `GET /api/sessions` does not issue per-session log fetches; session list badge latency measurably reduced; **FE handles missing/null badge columns** — frontend renders gracefully when any badge column is null or absent (resilience-by-default; R-P2) | L | python-backend-engineer | data-layer-expert (DDL) | batch_0 | 1 |
| P0-012 | Canonical-source-key delete path | `sync_engine.py:3939` (delete), `:4135` (upsert canonical), `:1292` (_canonical_source_key) | Change session + document delete to use `_canonical_source_key(project_id, path, kind)` matching the upsert key; fixes orphaned rows on watcher-triggered deletes | Delete and upsert use identical canonical key; no orphaned session/document rows after a watcher-triggered delete+re-ingest cycle; test with a fixture rename confirms no ghost row | M | python-backend-engineer | — | batch_0 | 1 |
| P1-001 | analytics_entries retention DELETE + ON CONFLICT upsert | `analytics.py:20,47`; `sync_engine.py:5802-5812`; `base.py` Protocol | Add 90-day retention DELETE (batched by `captured_at`, `batch_size=1000`) to analytics repository; add `ON CONFLICT (project_id, metric_type, date(captured_at)) DO UPDATE` to upsert; add `analytics_entity_links` pruning in same job; gate behind `CCDASH_ANALYTICS_RETENTION_ENABLED` (default OFF) | **DESTRUCTIVE — flag-gated default OFF; DB snapshot required before first enable** | S | data-layer-expert | CCDASH_ANALYTICS_RETENTION_ENABLED (default OFF) | — | 2 |
| P1-001 (cont.) | | | | Retention DELETE runs in batches of 1000 rows; `analytics_entries` row count drops ~50× (1.8M → ~30–90K) after a full retention pass; `ON CONFLICT` upsert avoids duplicate rows; worker-scheduled (not on request path); `CCDASH_ANALYTICS_RETENTION_DAYS` controls window (default 90); `analytics_entity_links` pruned in same job | | | | | |
| P1-003 | telemetry_events TTL retention | `sqlite_migrations.py:501-542`; `sync_engine.py:1428-1456,1495-1527` | Add TTL-based DELETE on `telemetry_events` where `payload_json` age > 30d; gate behind `CCDASH_TELEMETRY_RETENTION_ENABLED` (default OFF) | **DESTRUCTIVE — flag-gated default OFF; DB snapshot required before first enable** | M | data-layer-expert | CCDASH_TELEMETRY_RETENTION_ENABLED (default OFF) | — | 2 |
| P1-003 (cont.) | | | | Telemetry retention DELETE runs in batches; rows older than `CCDASH_TELEMETRY_RETENTION_DAYS` (default 30) are deleted; 1.6 GB `payload_json` blob storage reclaimed over time; worker-scheduled | | | | | |
| P1-013 | get_latest_entries HAVING fix | `analytics.py:57-83` | Fix the HAVING anti-pattern in `get_latest_entries` query (now at :57-83, corrected from drifted :103-121 anchor) | `get_latest_entries` query uses WHERE/subquery instead of HAVING for period filter; EXPLAIN shows no full-table HAVING scan; query correct after P1-001 retention runs | S | data-layer-expert | — | P1-001 | 2 |
| P1-014 | Partial indexes (analytics period='point', telemetry event_type) | `analytics.py:57-83`; index sections | Add partial index `WHERE period='point'` on `analytics_entries`; add partial index on `telemetry_events.event_type` | Partial indexes created via `_ensure_index` (idempotent); EXPLAIN on `get_latest_entries` shows partial index use; telemetry event_type queries show index use | S | data-layer-expert | — | P1-001 | 2 |
| P1-007 | _capture_analytics N+1 → batched CTE/JOIN | `sync_engine.py:5787,5876-5972`; `analytics.py` | Rewrite `_capture_analytics` to batch task/link/session loads via CTE/JOIN (12–15K queries/snapshot → ~3 batched queries) | Per-snapshot query count drops from 12–15K to single digits (measured by query counter at sync_engine.py:5787); functional output (analytics rows written) is identical; no regression in analytics accuracy | L | python-backend-engineer | — | P1-004 | 3 |
| P1-002 | Drop session_logs (staged, flag-gated default-OFF) | `sqlite_migrations.py:165-220`; `services/sessions.py:87-118`; 6 consumers: `api.py:626,660,812,844,956`; `_client_v1_features.py:814,849`; `feature_forensics.py:167`; `skillmeat_memory_drafts.py:269` | Stage: (1) migrate all 6 consumers off session_logs to session_messages; (2) stop populating session_logs at sync; (3) backfill-DROP session_logs; gate entire staged sequence behind `CCDASH_DROP_SESSION_LOGS_ENABLED` (default OFF) | **DESTRUCTIVE — flag-gated default OFF; DB snapshot required before enable; filesystem JSONL is re-derivable SoT** | XL | python-backend-engineer | data-layer-expert (DDL) | CCDASH_DROP_SESSION_LOGS_ENABLED (default OFF) | P1-010 + all 6 consumers migrated | 4 |
| P1-002 (cont.) | | | | All 6 consumers (`api.py:626,660,812,844,956`; `_client_v1_features.py:814,849`; `feature_forensics.py:167`; `skillmeat_memory_drafts.py:269`) read from `session_messages`, not `session_logs`; session_logs no longer populated at sync; DROP migration runs cleanly; ~1.75 GB reclaimed; no consumer reads dropped rows; **FE handles missing session_logs fields** — frontend renders gracefully when legacy fields absent (R-P2) | | | | | |
| P1-016 | FTS5/tsvector on session_messages.content | session_messages DDL; LIKE path | Add FTS5 virtual table (SQLite) / tsvector column + GIN index (Postgres) on session_messages.content; replace LIKE full-scan search | FTS5/tsvector search returns correct results; no SCAN session_messages for content search; DEFER if P1-002 staging incomplete | L | data-layer-expert | — | P1-002 | 4 |
| P1-015 | Reconcile SQLite(27)/Postgres(28) SCHEMA_VERSION | `sqlite_migrations.py:16`; `postgres_migrations.py:11` | Advance whichever version lags after all additive DDL from batch_0/1/2/3/4 lands; ensure both report the same version | SQLite and Postgres report identical SCHEMA_VERSION after all Phase 1 DDL runs; `_ensure_index` idempotency confirmed on existing DBs; version bump is the last migration applied | M | data-layer-expert | — | P1-004, P1-005, P1-010, P1-012, P1-014, P1-019 | 5 |

## Seam Task

| Task ID | Title | Change | Acceptance Criteria | Cplx | Assigned To | Batch |
|---------|-------|--------|---------------------|------|-------------|-------|
| P1-SEAM-1 | DDL↔repo↔service integration verification | Review that P1-010 materialized columns, P1-002 consumer migration, and P1-019 entity_links column are coherent: DDL in both SQLite and Postgres migrations, repository reads use the new columns, service layer does not re-derive materialized data, and no consumer still reads session_logs after P1-002 staging | All 6 session_logs consumers confirmed migrated; sessions DDL (SQLite + Postgres) matches repository column reads; entity_links.project_id populated at upsert; integration_owner (data-layer-expert) signs off | S | data-layer-expert | after batch_3, before batch_4 |

## Runtime Smoke Task (R-P4)

P1-010 changes `api.py:624-660`, which directly backs the session list view in the frontend. Per R-P4, a runtime smoke task is required.

| Task ID | Title | Change | Acceptance Criteria | Cplx | Assigned To | Batch |
|---------|-------|--------|---------------------|------|-------------|-------|
| P1-SMOKE | Session list runtime smoke | After P1-010 badge materialization lands, start the dev server and verify the session list view renders correctly | target_surfaces: [`components/Dashboard.tsx` (session list), `components/SessionInspector.tsx` (session badges)]; Session list renders without console errors; badge columns (model, agent, skill, command) display or show graceful fallback when null; `npm run dev` smoke confirms no regression; runtime_smoke: verified | S | python-backend-engineer | after P1-010 |

## FE-Fallback Acceptance Criteria (R-P2)

Two Phase 1 tasks introduce new backend fields with downstream frontend surfaces. Per R-P2, explicit FE-fallback ACs are required.

### P1-010 Materialized Badge Columns — FE Fallback AC

#### AC P1-010-FE: Frontend handles missing/null badge columns

- target_surfaces:
    - components/Dashboard.tsx
    - components/SessionInspector.tsx
- propagation_contract: badge columns (`models_used_json`, `agents_used_json`, `skills_used_json`, `command_slug`, `latest_summary`, `subagent_type`) are populated at sync time on the `sessions` table and returned by `GET /api/sessions`; frontend reads them from the API response
- resilience: when any badge column is null or absent, the UI renders a graceful empty/fallback state (no crash, no undefined error, no spinner-forever); `models_used_json` null → badge omitted; `latest_summary` null → no summary chip
- visual_evidence_required: false (internal infrastructure change; no visual regression expected beyond badge display)
- verified_by: [P1-SMOKE]

### P1-019 entity_links.project_id — FE Fallback AC

#### AC P1-019-FE: Frontend handles absent entity_links.project_id filtering

- target_surfaces:
    - components/Dashboard.tsx
    - components/Planning/PlanningGraphPanel.tsx (if it consumes entity_links-derived data)
- propagation_contract: `entity_links.project_id` is a new column populated at upsert; Phase 2 will use it for scoped fingerprint; Phase 1 only adds the column (nullable, default null for existing rows)
- resilience: frontend and API endpoints that read entity_links do not break when `project_id` is null on existing rows; no query that requires project_id to be non-null is issued in Phase 1 (that is Phase 2's contract)
- visual_evidence_required: false
- verified_by: [P1-SEAM-1]

## Measurable Exit Assertions

These are the quantitative commitments for Phase 1 completion. Each must be measured before the phase is marked complete.

| Metric | Before | Target After | Measurement Method |
|--------|--------|--------------|-------------------|
| DB total size | ~9.5 GB | ≤ 6.5 GB (≥ 3 GB reclaimed) | `dbstat` byte total before/after |
| `analytics_entries` row count | ~1.8M | ~30–90K (~50× reduction) | `SELECT COUNT(*) FROM analytics_entries` |
| `_capture_analytics` queries/snapshot | 12–15K | single digits (≤ 9) | query counter at `sync_engine.py:5787` |
| `entity_graph` commits/rebuild | ~25K | 1 | counter at `entity_graph.py:40` |
| `session_logs` size (after P1-002) | ~1.75 GB | 0 (dropped) | `dbstat` on session_logs table |
| `telemetry_events` size (after P1-003) | ~1.6 GB | < 0.1 GB (TTL passes) | `dbstat` on telemetry_events |
| SQLite SCHEMA_VERSION | 27 | matches Postgres (28 or higher) | both DBs report same value |
| Postgres SCHEMA_VERSION | 28 | matches SQLite (same target) | both DBs report same value |

## Phase 1 Quality Gates

- [ ] DB shrinks ≥ 3 GB (dbstat measured before and after)
- [ ] `analytics_entries` COUNT drops ~50× after retention pass (flag enabled in test environment)
- [ ] `_capture_analytics` query count ≤ 9 per snapshot
- [ ] `entity_graph` rebuild = 1 commit
- [ ] `GET /api/sessions` serves materialized badge columns; no per-session log fetch
- [ ] All four indexes (`idx_sessions_project_status_updated`, `idx_sessions_source_file`, `idx_sessions_project_source_file`, `idx_links_project`) present via `_ensure_index` backfill in live DB
- [ ] `entity_links.project_id` column and index present (Phase 2 prereq confirmed)
- [ ] Postgres `upsert_logs`/`upsert_file_updates` atomic; UNIQUE constraint in fresh-install DDL
- [ ] SQLite and Postgres report identical SCHEMA_VERSION
- [ ] SQLite pragmas applied on dev/SQLite path only; Postgres path skipped
- [ ] Canonical delete path (`P0-012`) confirmed: no orphaned rows after fixture rename
- [ ] All 6 `session_logs` consumers migrated before P1-002 flag enabled
- [ ] FE-fallback ACs for P1-010 and P1-019 verified (R-P2)
- [ ] P1-SMOKE runtime smoke: session list renders correctly with materialized badges
- [ ] P1-SEAM-1 integration verification signed off by `data-layer-expert`
- [ ] Destructive tasks (P1-001, P1-002, P1-003): DB snapshot taken before first flag enable; rollback path documented
- [ ] `task-completion-validator` sign-off

## Key Files

| File | Tasks | Notes |
|------|-------|-------|
| `backend/db/sqlite_migrations.py` | P1-004, P1-005, P1-010, P1-012 (pg only), P1-014, P1-015, P1-019 | Multiple tasks; P1-015 must be last |
| `backend/db/postgres_migrations.py` | P1-011, P1-012, P1-015, P1-019 | Multiple tasks; P1-015 must be last |
| `backend/db/sync_engine.py` | P0-012, P1-007, P1-009, P1-017, P1-018 | High-touch file; batch carefully |
| `backend/db/entity_graph.py` | P1-008, P1-019 | executemany + project_id population |
| `backend/db/repositories/analytics.py` | P1-001, P1-013, P1-014 | Retention + HAVING fix + partial index |
| `backend/db/repositories/sessions.py` | P1-005, P1-009, P1-010 | index + executemany + badge columns |
| `backend/db/repositories/postgres/sessions.py` | P1-011 | atomic transaction wrap |
| `backend/db/repositories/postgres/_transactions.py` | P1-011 | postgres_transaction utility |
| `backend/db/connection.py` | P1-006 | SQLite pragma block |
| `backend/routers/api.py` | P1-010 | session list endpoint (:624-660); runtime smoke target |
| `backend/services/sessions.py` | P1-002, P1-010 | consumer migration + badge service |
| `backend/services/usage_attribution.py` | P1-009 | executemany |
| `backend/_client_v1_features.py` | P1-002 | consumer migration (:814,849) |
| `backend/application/services/feature_forensics.py` | P1-002 | consumer migration (:167) |
| `backend/services/skillmeat_memory_drafts.py` | P1-002 | consumer migration (:269) |

## Rollback

- **Non-destructive tasks** (pragmas, indexes, executemany, batching, N+1 rewrites, P0-012, P1-017, P1-018, P1-019): code-revert safe; data untouched.
- **P1-001 / P1-003** (retention): flag-gated default-OFF; DB snapshot before first enable; deleted rows cannot be recovered from DB but filesystem JSONL is re-derivable source of truth.
- **P1-002** (session_logs drop): flag-gated `CCDASH_DROP_SESSION_LOGS_ENABLED` default-OFF; staged (confirm consumers → stop populating → backfill-DROP); DB snapshot required before DROP; filesystem JSONL remains re-derivable SoT; DO NOT enable flag until P1-SEAM-1 confirms all 6 consumers migrated.
- **P1-015** (schema version): forward-only; no downgrade path; coordinate with P1-012 (UNIQUE-in-DDL).
