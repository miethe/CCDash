---
slug: ccdash-db-design-remediation
title: "CCDash DB Design Audit & Remediation Readiness"
type: spike-charter
status: completed
completed_date: 2026-06-03
verdict: conditional
verdict_rationale: >-
  Remediation is safe to plan as a Tier 3 PRD now. The audit narrowed the blast radius: the
  swallow-on-write anti-pattern is NOT systemic (0 sites in the async repo layer; failures propagate,
  queue repos already retry). The silent no-op is localized to the synchronous project-registry path
  (project_manager.py + SqliteProjectRepository). Conditional preconditions: (1) snapshot-before-touch
  for any VACUUM/retention/session_logs-drop on the 11 GB live DB; (2) ship the small reversible registry
  fix independently of the multi-GB reclaim work; (3) ratify ADR-006 (DB-authoritative JSON-import-only)
  before writing the registry fix, since the fix shape depends on it.
risk_level: high
owner: Nick Miethe
created: 2026-06-03
tier_target: 3
related_documents:
  - docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/05-target-architecture-proposal.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/02-performance-forensics.md
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
  - docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
  - docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md
findings_output: docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md
adr_output: docs/project_plans/adrs/   # propose ADR-006+ as warranted
---

# Charter: CCDash DB Design Audit & Remediation Readiness

## Motivation

A 2026-06-03 incident ("projects no longer showing, only the example") exposed that
CCDash's **DB-backed project registry (P3-001) silently fails its bootstrap on every
startup** and the app has been running accidentally JSON-backed. Investigation proved the
failure was a swallowed `database is locked` during a contended startup window — not a
code or schema bug. This is almost certainly **not an isolated defect**: it is a symptom of
systemic patterns (broad exception swallowing around writes, sync/async connection
contention on a 10–11 GB WAL DB, design-intent vs. implementation drift, and persistence
asserted only indirectly in tests).

This SPIKE audits **all CCDash DB designs** against their documented intent and current
runtime behavior, producing a severity-ranked findings report + ADR recommendations that
scope a Tier 3 remediation PRD. Goal: every DB subsystem is provably up to spec and
functioning as intended — or has a tracked remediation item.

## Confirmed evidence (do NOT re-derive — start here, then expand)

1. **Project registry flush is a silent no-op in-app.** `DbProjectManager._flush_snapshot_to_db`
   (`backend/project_manager.py:447-460`) wraps all upserts in `except Exception: logger.error(...)`.
   `container.py:1203` calls `list_projects()` during startup composition → lazy `_load_snapshot`
   → bootstrap flush runs *in the same window the sync engine writes heavily to the shared
   11 GB WAL* → `database is locked` → swallowed. `_snapshot_loaded` then stays True, so the
   flush is never retried in-process; every fresh process re-bootstraps from JSON and re-fails.
   Proven: the identical flush succeeds standalone (0→5 rows); fails in-app (table stayed 0
   across reloads). The `projects` table schema matches the repo INSERT exactly (migration v30).
   The table was manually populated to 5 rows on 2026-06-03 as an interim fix.
2. **No writeback to `projects.json`.** After (intended) DB bootstrap, the JSON goes stale
   permanently; UI-added projects would not survive a table wipe. Intent (per
   enterprise-liveness-storage PRD): DB authoritative, JSON import-only.
3. **Dead/duplicate config.** `backend/config.py:57` `DB_PATH` default `.ccdash.db` is unused;
   the registry uses `backend/db/connection.py` `DB_PATH` = `data/ccdash_cache.db`.
4. **Observability gap.** Flush failure is invisible: no `/api/health` registry field, no metric.
5. **Test gap.** `backend/tests/test_db_project_registry.py` asserts persistence via a second
   instance read — which passes even when the flush fails (JSON re-bootstraps). No direct
   `repo.count()` assertion; no contention/failure-surfacing test.
6. **DB bloat smell.** `data/ccdash_cache.db` ~11 GB + a ~10 GB `.bak`; WAL present. Likely both
   a cause (amplifies lock contention) and a symptom (retention/VACUUM gap).

## Research questions

### RQ1 — Repository layer integrity (all of `backend/db/repositories/**`)
- Inventory every repository (sqlite + postgres). For each write path: does it commit? Are
  write failures swallowed by broad `except Exception: logger.*` that hide data loss
  (grep this anti-pattern across the layer)? Which are sync `sqlite3` vs async `aiosqlite`?
- Where do independent sync connections coexist with the async singleton on the same WAL DB?
  Catalog every place this contention can occur (not just the registry).
- Connection lifecycle/thread-safety: `check_same_thread=False` usages, connection reuse,
  busy_timeout settings, retry-on-locked presence/absence.

### RQ2 — Migration system correctness & parity
- Map `backend/db/sqlite_migrations.py` (current v33) and the postgres migration path. Is there
  schema/DDL drift between sqlite and postgres for the same logical tables? Is `schema_version`
  tracking consistent? Are migrations idempotent and forward-only? Any data-migration steps
  (vs. DDL-only), and are they tested?
- Are there tables created by application "safety-net" DDL (like `SqliteProjectRepository.ensure_table`)
  that can drift from the canonical migration DDL?

### RQ3 — Project registry & the JSON↔DB contract (deepen, don't re-derive)
- Define the *correct* target contract for a local-first + optional-multi-replica tool. Evaluate:
  (A) JSON authoritative + DB as derived cache/index (write-through); (B) DB authoritative +
  JSON import/export only; (C) status quo. Recommend one with rationale tied to actual usage.
- Eager-at-startup vs lazy-on-first-request bootstrap; retry/backoff on locked; failure surfacing.
- Should the legacy JSON `ProjectManager` (`project_manager.py:658`) be removed, or repurposed?

### RQ4 — Cache DB size, retention & contention
- Root-cause the ~11 GB size: which tables/rows dominate (sessions/messages/embeddings/telemetry
  queues)? Is there a retention/pruning policy? VACUUM/auto_vacuum/WAL-checkpoint strategy?
- Quantify how DB size + WAL state contribute to the startup-window lock contention. Recommend
  retention + maintenance + (if needed) write-serialization or `busy_timeout`/WAL-checkpoint tuning.

### RQ5 — Sync engine & startup sequencing
- `backend/db/sync_engine.py` + file_watcher + startup sync: what writes during startup, and does
  it serialize/conflict with other writers? Interaction of `CCDASH_STARTUP_SYNC_LIGHT_MODE` and
  `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`. Is startup ordering deterministic w.r.t. registry bootstrap?

### RQ6 — SQLite vs PostgreSQL parity & runtime profiles
- Does every DB design function on both backends across runtime profiles (local/api/worker/test)?
  Identify sqlite-only or postgres-only code paths, and any behavior that silently differs.

### RQ7 — Observability & test posture (cross-cutting)
- Which DB write paths surface failures (health/metrics/logs) vs swallow them? Propose a consistent
  failure-surfacing standard.
- Which DB designs have persistence-asserting tests (direct row/count assertions, restart-survival,
  failure-injection) vs functional-only? Produce a coverage matrix and the highest-value test gaps.

## Scope

**In scope:** All backend DB designs — repositories, migrations (sqlite+postgres), connection
lifecycle, the project registry, sync engine startup interaction, cache DB retention/maintenance,
runtime-profile/backend parity, and DB-failure observability + test coverage.

**Out of scope:** Frontend data layer (TanStack Query), agent-query service business logic (except
where it owns DB writes), new product features. Vector/embeddings *storage mechanics* are in scope
for size/parity; embedding *quality/semantics* are not.

## Required outputs

1. `docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md` — severity-ranked
   findings (each: subsystem, intended design w/ citation, actual behavior w/ file:line evidence,
   severity, blast radius, recommended remediation, effort estimate). Include the RQ7 coverage matrix.
2. ADR recommendation(s) for any architectural decision the remediation forces — at minimum the
   JSON↔DB authority model (RQ3) and the failure-surfacing standard (RQ7). Draft as ADR-006+ proposals.
3. A **remediation backlog** (candidate phases/epics with rough sizing) that directly scopes the
   downstream Tier 3 PRD + Implementation Plan. Group by: P0 correctness/data-loss, P1 design
   coherence, P2 durability/ops, P3 observability/tests.
4. A short **verdict** section: is the remediation safe to plan now (go), or are there preconditions
   (conditional), or should scope change (set charter `verdict` accordingly).

## Success criteria

- Every RQ answered with concrete file:line evidence and intended-vs-actual deltas.
- No DB subsystem left "unassessed"; each is either ✅ to-spec or has a tracked finding.
- The backlog is granular enough that `prd-writer` + `implementation-planner` can build the PRD/plan
  without re-investigating the codebase.
- Evidence grounded in runtime truth (code + live DB), not stale plans.
