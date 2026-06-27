---
schema_version: 2
doc_type: report
report_category: findings
title: "CCDash DB Design Audit & Remediation Readiness — Findings"
status: accepted
source: agent
created: 2026-06-03
feature_slug: ccdash-db-design-remediation
risk_level: high
owner: Nick Miethe
spike_charter_ref: docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md
findings_output: docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md
related_documents:
  - docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
  - docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
verdict: conditional
---

# CCDash DB Design Audit & Remediation Readiness — Findings

> **Scope of this document.** Severity-ranked audit of *all* CCDash DB designs against documented
> intent + runtime truth (code in `backend/db/**`, `backend/project_manager.py`, `backend/runtime/**`,
> and the live `data/ccdash_cache.db` probed read-only on 2026-06-03). The charter's six "Confirmed
> evidence" items are treated as proven and are *expanded*, not re-derived. Evidence is `file:line` and
> live-DB probe output. No production code, migrations, or live DB were modified.

## 0. Verdict

**CONDITIONAL GO.** The remediation is safe to plan now as a Tier 3 PRD. The audit *narrowed* the blast
radius rather than widening it: the broad-`except`-swallows-writes anti-pattern the charter feared is
**not systemic** — the async repository layer overwhelmingly *propagates* write failures (often
log-then-`raise`), and a real retry-on-locked helper already exists in the highest-contention queue
repos. The silent-no-op is **localized to the synchronous project-registry path** (`project_manager.py`
+ `SqliteProjectRepository`), which (a) lacks `PRAGMA busy_timeout`, (b) swallows its flush failure, and
(c) is the only sync writer that fights the async singleton for the single WAL write-lock during the
startup window. That is a tractable, bounded P0.

**Preconditions before the destructive parts of remediation execute** (hence *conditional*, not
unconditional go):

1. **Snapshot-before-touch.** The live DB is 11.26 GB with a 10 GB stale `.bak`. Any VACUUM /
   retention-prune / `session_logs` drop in remediation must be snapshot-protected and flag-gated
   (the liveness PRD already sequences this — do not duplicate).
2. **Do not couple registry-fix to storage-hygiene.** The P0 registry correctness fix (small, reversible)
   must ship independently of the multi-GB reclaim work (slow, lock-heavy). They share a root cause
   (lock contention) but have opposite risk profiles.
3. **Resolve the JSON↔DB authority model (ADR-006) before writing the registry code**, because the fix
   shape (writeback vs import-only vs single-manager) depends on the ratified contract.

No scope change is required. The charter's RQs are all answerable from runtime truth; nothing is "unassessed."

---

## 1. Live-DB probe summary (2026-06-03, read-only)

| Metric | Value | Source |
|---|---|---|
| Physical file | 11.26 GB (`ccdash_cache.db`) + 10 GB `.bak` + 2.1 MB WAL | `data/` listing |
| `page_size` / `page_count` | 4096 / 2,748,612 → 11.26 GB logical | `PRAGMA` probe |
| `freelist_count` | 543,926 pages = **2.23 GB reclaimable (19.8% dead)** | `PRAGMA` probe |
| `auto_vacuum` | **0 (NONE)** — no automatic page reclaim | `PRAGMA` probe |
| `journal_mode` | `wal` | `PRAGMA` probe |
| `schema_version` rows | 1–33 with **gaps: 16, 29, 31 absent** | `SELECT * FROM schema_version` |
| `projects` rows | 5 (active = `3df0ff70…` "SkillMeat") | manual interim fix 2026-06-03 |
| `projects.json` | 5 projects, active = `3df0ff70…` — **currently coincidentally in sync** | `projects.json` read |

**Top tables by bytes (`dbstat`):**

| Bytes | Rows | Table | Notes |
|---|---|---|---|
| 2.485 GB | 556,821 | `session_logs` | Dead-duplicate transcript table (liveness PRD §5 "destructive drop, flag-gated"). |
| 2.003 GB | 934,841 | `telemetry_events` | Unbounded; retention default-OFF. |
| 1.539 GB | 396,286 | `session_messages` | Canonical transcript store. |
| 0.762 GB | 108,764 | `session_usage_attributions` (+ its autoindex 0.317 GB) | Heavy per-entity attribution. |
| ~1.3 GB | — | `idx_telemetry_*` (10+ indexes) | Index bloat tracks `telemetry_events`. |

`session_logs` + `telemetry_events` alone = **4.49 GB (40%)** of the file and are the two highest-value
reclaim targets. The `schema_version` gaps are **expected and benign** (see Finding F-07), not corruption.

---

## 2. Findings (severity-ranked)

Severity scale: **S0** data-loss/correctness now · **S1** design incoherence / latent data-loss ·
**S2** durability/ops · **S3** observability/tests. Blast radius is the surface that breaks if the
finding fires.

### F-01 — [S0] Project-registry flush is a silent no-op; registry only survives by accident

- **Subsystem:** Project registry (`DbProjectManager` + `SqliteProjectRepository`).
- **Intended design:** Enterprise-liveness PRD §4/§8 — *DB authoritative*, registry persistence
  *survives restarts and replicas*; `build_workspace_registry` comment "prefer the DB-backed registry
  so persistence survives restarts" (`backend/runtime_ports.py:137-140`).
- **Actual behavior:** `DbProjectManager._flush_snapshot_to_db` wraps all upserts in
  `except Exception: logger.error(...)` and returns (`backend/project_manager.py:447-460`). On the
  contended startup window the flush raises `database is locked`, is swallowed, and `_snapshot_loaded`
  is set `True` (`:392`) so the flush is **never retried in-process**. Every fresh process re-bootstraps
  from JSON and re-fails. Proven standalone-succeeds / in-app-fails (charter evidence #1). The 5 rows now
  present were inserted manually on 2026-06-03.
- **Root-cause nuance (new):** `SqliteProjectRepository._get_conn` passes `timeout=30` to
  `sqlite3.connect` (`backend/db/repositories/projects.py:45`) but sets **only** `journal_mode=WAL` and
  `foreign_keys=ON` (`:48-49`) — it never issues `PRAGMA busy_timeout`. The `timeout=` driver param
  *does* install a busy handler, so a *simple* lock should wait 30s. The flush still fails, which means
  the contention is a **WAL write-lock held >30s by the async sync engine** (or a checkpoint stall), not
  a momentary blip. busy_timeout alone will not fix this — the registry writer and the sync engine are
  two independent connections fighting SQLite's single-writer rule.
- **Severity:** S0 (registry data is the spine of every project-scoped query).
- **Blast radius:** Entire app (UI shows only the default example; worker project-binding resolution).
- **Remediation:** (1) Make the bootstrap flush *fail loud* — on exception, do **not** set
  `_snapshot_loaded=True`; surface via health + log at ERROR with the locked reason; retry with backoff
  on next access. (2) Serialize registry writes against the sync-engine writer (shared write-lock /
  retry-on-locked helper, reusing the `execution.py` pattern). (3) Decouple bootstrap from the heavy
  startup-sync window (lazy-on-first-request, or run bootstrap before sync starts). Final shape depends
  on ADR-006.
- **Effort:** ~3–5 pts (code small; the design decision in ADR-006 is the gating work).

### F-02 — [S1] Two project managers, two stores, no reconciliation; no DB→JSON writeback

- **Subsystem:** Project registry dual-manager wiring.
- **Intended design (per liveness PRD §4 "DB authoritative, JSON import-only"):** one authoritative store.
- **Actual behavior:** Both managers are instantiated at import time —
  `project_manager = ProjectManager(...)` (JSON, atomic writeback at `project_manager.py:141-160`) and
  `db_project_manager = DbProjectManager(...)` (DB, **no JSON writeback anywhere**) at
  `backend/project_manager.py:658` and `:663`. `build_workspace_registry` prefers the DB manager
  (`runtime_ports.py:140`) but falls back to the JSON manager when a caller passes one explicitly
  (`:134-136`). Result: writes can land in *either* store with no reconciliation. They are *coincidentally*
  in sync today (both list the same 5 ids) only because the DB was hand-populated to match JSON.
- **Severity:** S1 (latent split-brain; UI-added projects via the DB path never persist to JSON, and a
  table wipe loses them since bootstrap re-reads stale JSON — charter evidence #2).
- **Blast radius:** Registry consistency across processes/replicas; operator confusion.
- **Remediation:** Ratify ADR-006 authority model, then collapse to a single manager (or make JSON
  strictly import-only with an explicit `export`/writeback hook). Remove or repurpose the legacy
  `ProjectManager` (RQ3 question).
- **Effort:** ~3–5 pts (after ADR-006).

### F-03 — [S2] 11 GB cache DB: 2.23 GB dead pages, `auto_vacuum=0`, retention default-OFF

- **Subsystem:** Cache DB size / retention / maintenance.
- **Intended design:** Liveness PRD §3 goal "DB shrinks ≥3 GB via retention + transcript dedupe"; a full
  retention/prune/VACUUM subsystem exists in config (`backend/config.py:1074-1102`,
  `RETENTION_PRUNE_ENABLED`, `ANALYTICS_RETENTION_DAYS=90`, `TELEMETRY_RETENTION_DAYS=90`,
  `RETENTION_VACUUM_ENABLED=True`) and a scheduled job (`backend/adapters/jobs/runtime.py:1394-1418`,
  "P6-002 scheduled retention prune + VACUUM/ANALYZE").
- **Actual behavior:** `RETENTION_PRUNE_ENABLED` defaults **False** (`config.py:1079`); the prune job
  early-returns `None` when disabled (`adapters/jobs/runtime.py:1414-1415`). So the subsystem is built
  but dormant. Live DB: `auto_vacuum=0`, `freelist_count=543,926` (2.23 GB reclaimable),
  `telemetry_events` 934K rows (2 GB) and `session_logs` 556K rows (2.5 GB dead-duplicate) both unbounded.
- **Severity:** S2 (durability/ops — also a *contributing cause* of F-01: a larger DB and more WAL churn
  widens the lock-contention window).
- **Blast radius:** Startup contention amplification, disk, query latency, backup size (10 GB `.bak`).
- **Remediation:** Operationalize the existing subsystem — flip `RETENTION_PRUNE_ENABLED` on (snapshot
  first), run a one-time `VACUUM` to reclaim the 2.23 GB freelist, land the flag-gated `session_logs`
  dedupe/drop (already scoped in liveness PRD §5 — *reference, do not re-scope*). Consider a
  WAL-checkpoint strategy distinct from the default `wal_autocheckpoint=1000`.
- **Effort:** ~5–8 pts (mostly the destructive `session_logs` staging already in the liveness plan;
  marginal new work is enabling retention + the one-time VACUUM runbook).

### F-04 — [S1] SQLite migrations have no first-boot concurrency guard (Postgres has one)

- **Subsystem:** Migration system concurrency.
- **Intended design:** Migrations are idempotent + forward-only; safe under concurrent processes. Postgres
  acquires `pg_advisory_lock` around all DDL (`backend/db/postgres_migrations.py:2278-2294`).
- **Actual behavior:** The SQLite runner (`backend/db/sqlite_migrations.py:2641-2659`) has **no advisory
  lock, file lock, or in-process mutex** — it relies entirely on the connection's `busy_timeout`. In the
  local multi-process scenario (api + worker, both `RuntimeProfile.capabilities` may run migrations on
  boot via `backend/db/migrations.py:run_migrations`), two processes can race the monolithic
  `executescript(_TABLES)` and the per-version `_ensure_column`/`_ensure_index` blocks. The DDL is
  `CREATE TABLE IF NOT EXISTS` / `IF NOT EXISTS` so collisions are *mostly* benign, but a concurrent
  table-rebuild migration (e.g. v31 `sessions_new` swap, `:1565-1722`) racing a second runner is
  undefined behavior and can throw `locked`/`schema changed`.
- **Severity:** S1 (correctness under concurrency; latent, not currently firing on single-process dev).
- **Blast radius:** Local dual-process boot; any future replicated SQLite (not recommended).
- **Remediation:** Add a SQLite-side first-boot guard — a file lock (`flock`) or an in-process/inter-process
  mutex around `run_migrations`, mirroring the Postgres advisory-lock intent.
- **Effort:** ~2–3 pts.

### F-05 — [S1] Migration parity is asserted at TABLE-SET level only; column/constraint drift is uncaught

- **Subsystem:** SQLite↔Postgres schema parity.
- **Intended design:** "Schema version history (keep in lockstep with postgres_migrations.py)"
  (`sqlite_migrations.py:6`); governance layer exists to enforce parity.
- **Actual behavior (good news first):** `migration_governance.py` extracts table blocks per backend and
  `test_migration_governance.py:23-27` (`test_shared_migration_tables_match_across_backends`) **does**
  assert `get_sqlite_migration_tables() == get_postgres_migration_tables() - enterprise_only`. Table-set
  parity is genuinely guarded. **Gap:** the assertion is set-equality on table *names* only. There is no
  test comparing **columns, types, NOT NULL, DEFAULT, UNIQUE, or index definitions** for the same logical
  table across backends. A divergence like a UNIQUE constraint present in one backend's DDL but not the
  other (the kind the liveness PRD P1 "Postgres atomic upserts + UNIQUE-in-DDL" work touches) would pass
  CI. Both backends also only record a single final `schema_version` row, so version *progression* parity
  is unverifiable from the table.
- **Severity:** S1 (drift class is silent until it produces divergent runtime behavior on one backend).
- **Blast radius:** Enterprise (Postgres) vs dev (SQLite) behavior divergence; upsert semantics.
- **Remediation:** Extend governance to a column/constraint-level diff (parse each table block into a
  normalized `{column: (type, nullable, default)}` + index/constraint set per backend; assert structural
  equality for shared tables). Add an idempotency test (run `run_migrations` twice on a populated DB,
  assert no error + stable schema).
- **Effort:** ~3–5 pts.

### F-06 — [S2] Independent sync connections on the WAL DB beyond the registry (contention catalog)

- **Subsystem:** Connection lifecycle / WAL contention (RQ1).
- **Intended design:** One async singleton (`backend/db/connection.py:34-64`) with `busy_timeout=30000`,
  `synchronous=NORMAL`, `wal_autocheckpoint=1000`, 128 MB cache.
- **Actual behavior — full catalog of non-singleton SQLite writers/readers:**
  - `SqliteProjectRepository` — stdlib `sqlite3`, `check_same_thread=False`, `timeout=30`, **no
    busy_timeout pragma** (`repositories/projects.py:42-49`). The F-01 contender.
  - `backend/db/repositories/sessions.py` — imports `sqlite3` (sync) in addition to the async path
    (used for specific sync read/maintenance helpers; confirm scope before assuming write contention).
  - `backend/db/sqlite_migrations.py` — uses stdlib `sqlite3` for the synchronous FK-check path
    (`:2539-2564`), runs during migration only.
  - `backend/scripts/link_audit.py`, `backend/tests/test_features_list_filter.py` — sync, out-of-band /
    test only (not runtime hot path).
  - PostgresProjectRepository uses **psycopg2 (sync)** with `autocommit=False`
    (`repositories/postgres/projects.py:37-49`) — sync, but Postgres MVCC tolerates concurrent writers,
    so this is not a contention hazard the way SQLite WAL is.
- **Async-layer health (refutes the charter's systemic-swallow hypothesis):** A grep for broad-`except`
  wrapping `commit()`/`execute()` in the async repos returned **zero swallow-on-write sites**. The
  broad-`except` blocks that exist are around (a) JSON-decode of optional columns, (b) reads of
  possibly-missing tables (`scan_manifest.py:87` `# pragma: no cover – table missing`), or they
  **log-then-`raise`** (e.g. `oq_resolutions.py:157-163` upsert). Write failures propagate.
- **Retry-on-locked already present** in the four highest-contention queue repos: `execution.py`
  (`_commit_with_retry`/`_is_locked`, `:33,45,59,64`), `job_queue.py`, `telemetry_queue.py`,
  `worktree_contexts.py:25,36`. **Absent** in: the registry sync path (F-01), and all other write repos
  (they rely on the singleton's `busy_timeout=30000`, which is generally sufficient because they share the
  *same* connection and serialize naturally).
- **Severity:** S2 (the only acute case is F-01; the rest is a consistency/standardization concern).
- **Remediation:** Standardize a single locked-retry helper in `repositories/base.py` and apply it to the
  registry sync path + the sync `sessions.py` helpers; ensure every independent sync connection issues
  `PRAGMA busy_timeout` to match the singleton.
- **Effort:** ~3 pts.

### F-07 — [S3] schema_version table records only the final version per run (gaps are benign but misleading)

- **Subsystem:** Migration version tracking.
- **Intended design:** A version ledger.
- **Actual behavior:** Both runners gate on `MAX(version) < SCHEMA_VERSION` and insert a **single** row at
  the end (`sqlite_migrations.py:2645-2652, 3585-3589`; `postgres_migrations.py:2300-2312, 3134`). Live DB
  shows rows 1–33 with 16/29/31 absent — because those versions shipped *bundled* into a single migration
  run that recorded only its terminal version. This is **not corruption** and migrations did apply
  (the per-version `_ensure_*` blocks are unconditional). But it makes the ledger unreliable for "which
  versions ran" auditing and complicates F-05's progression-parity goal.
- **Severity:** S3 (observability/auditability).
- **Remediation:** Record each applied version (insert per step, or a richer `migrations_applied`
  ledger with applied_at). Optional; low priority.
- **Effort:** ~2 pts.

### F-08 — [S1] Safety-net `ensure_table` DDL duplicates canonical migration DDL (drift surface)

- **Subsystem:** Application-side DDL vs canonical migration DDL.
- **Intended design:** Canonical DDL lives in `sqlite_migrations.py` (v30); `ensure_table` is "a
  safety-net so the repository works even when the async migration path hasn't run yet"
  (`repositories/projects.py:64-97`).
- **Actual behavior:** `SqliteProjectRepository.ensure_table` (`:72-96`) **and**
  `PostgresProjectRepository.ensure_table` (`postgres/projects.py:63-91`) each hard-code a full `projects`
  CREATE TABLE + index. These are maintained by hand in parallel with the v30 migration DDL. Any future
  column add to `projects` must be edited in **three** places (sqlite migration, sqlite ensure_table,
  postgres ensure_table) or they silently drift; the drift is invisible because `IF NOT EXISTS` means the
  first writer wins and the others no-op.
- **Severity:** S1 (drift hazard; same class as F-05 but app-side).
- **Blast radius:** `projects` schema; any other repo using the ensure_table-vs-migration dual-DDL pattern.
- **Remediation:** Make `ensure_table` *call into* the canonical migration DDL (single source of truth) or
  delete the safety-net once the bootstrap ordering guarantees migrations ran first (preferred — ties to
  F-01 ordering fix). Audit for other `CREATE TABLE IF NOT EXISTS` safety-nets (e.g.
  `_ensure_test_visualizer_tables`, `_ensure_planning_worktree_contexts_table` in both migration modules).
- **Effort:** ~2–3 pts.

### F-09 — [S3] No DB-write or registry observability in /api/health; flush failure is invisible

- **Subsystem:** Observability (RQ7).
- **Intended design (charter #4):** flush failure should be visible (health field / metric).
- **Actual behavior:** `_build_health_payload` (`backend/runtime/bootstrap.py:124-191`) exposes
  `"db": "connected" if connection._connection else "disconnected"` (`:131`) — pure singleton-existence,
  plus storage-profile metadata. **No** registry row count, **no** last-flush status, **no** freelist /
  DB-size gauge, **no** retention-job last-run. There is no Prometheus counter for swallowed DB write
  failures. The F-01 silent no-op is therefore undetectable from outside the process.
- **Severity:** S3 (it *enabled* the F-01 incident to persist undetected).
- **Remediation:** Add to `/api/health/detail`: `registry.project_count`, `registry.last_flush_status`
  (`ok`/`failed`/`locked`), `db.size_bytes`, `db.freelist_bytes`, `retention.last_run`. Emit a
  `ccdash_db_write_failures_total{repo,reason}` counter wherever a write is retried/swallowed. This is the
  enforcement mechanism for ADR-007.
- **Effort:** ~3–5 pts.

### F-10 — [S3] Dead/duplicate config: `config.DB_PATH` default `.ccdash.db` is unused

- **Subsystem:** Config hygiene (charter #3).
- **Actual behavior:** `backend/config.py:57` `DB_PATH` defaults to `.ccdash.db`; the registry and async
  layer use `backend/db/connection.py:25` `DB_PATH = data/ccdash_cache.db` (env `CCDASH_DB_PATH`). The
  `config.DB_PATH` value is dead — a foot-gun for anyone who edits it expecting an effect.
- **Severity:** S3.
- **Remediation:** Delete the dead default or make `connection.py` derive from it (single source).
- **Effort:** ~1 pt.

### F-11 — [S3] Registry persistence test passes even when the flush fails (charter #5, expanded)

- **Subsystem:** Test posture (RQ7).
- **Intended design:** persistence asserted.
- **Actual behavior:** `backend/tests/test_db_project_registry.py` asserts "restart survival" via a
  *second* `DbProjectManager` instance reading the same path (`:107-145`,
  `test_rows_survive_new_instance`, `test_multiple_projects_all_survive_restart`). Because the second
  instance re-bootstraps from JSON when the DB is empty, the test passes **even if the first instance's
  flush silently failed** — exactly the F-01 failure mode. There is **no** direct
  `SqliteProjectRepository.count()` assertion against the DB after a flush, and **no** contention /
  lock-injection test that reproduces F-01.
- **Severity:** S3 (the test gap is *why* F-01 shipped).
- **Remediation:** Add a direct `repo.count()`/`SELECT COUNT(*)` assertion immediately after flush; add a
  failure-injection test (hold a write-lock on the DB in a second connection, assert the flush either
  retries-and-succeeds or surfaces a loud failure — never a silent True). See coverage matrix §4.
- **Effort:** ~2–3 pts.

---

## 3. RQ-by-RQ resolution (every RQ answered)

| RQ | Verdict | Evidence anchor |
|---|---|---|
| **RQ1** Repository write integrity | **Mostly to-spec.** Async repos commit + propagate; swallow-on-write is **not** systemic (0 sites). Locked-retry exists in 4 queue repos. Only acute defect is the registry sync path (F-01). Sync-connection catalog in F-06. | `connection.py:34-64`; `oq_resolutions.py:157-163`; `execution.py:33-69`; `repositories/projects.py:42-49` |
| **RQ2** Migration correctness & parity | **To-spec on idempotency/forward-only; gaps on concurrency (F-04), column-parity (F-05), version ledger (F-07).** v31 rebuild is idempotent (`sqlite_migrations.py:1587-1597`). Data-migrations are guarded. | `sqlite_migrations.py:2641-2659,3585-3591,1565-1722`; `postgres_migrations.py:2278-2294` |
| **RQ3** Registry & JSON↔DB contract | **Defective.** F-01 (silent no-op), F-02 (dual manager, no writeback). Target contract → ADR-006 (recommend Option B: DB authoritative, JSON import/export-only). | `project_manager.py:447-460,658,663`; `runtime_ports.py:127-140` |
| **RQ4** Size, retention, contention | **Subsystem built but dormant (F-03).** 2.23 GB dead pages, `auto_vacuum=0`, retention default-OFF; `session_logs`+`telemetry_events`=40% of file. Size amplifies F-01 contention. | `config.py:1074-1102`; `adapters/jobs/runtime.py:1394-1418`; live `dbstat`/`PRAGMA` probe |
| **RQ5** Sync engine & startup sequencing | **Contention confirmed.** `container.py:1203` triggers lazy registry bootstrap in the same window the `SyncEngine` (`container.py:211-214`) writes heavily (`sync_engine.py` `_replace_*`/backfill commit paths). Startup ordering is non-deterministic w.r.t. registry bootstrap → F-01. `STARTUP_SYNC_LIGHT_MODE`/`INCREMENTAL_LINK_REBUILD` are the mitigations already in flight (liveness PRD). | `container.py:1195-1219`; `sync_engine.py:1455-2617` |
| **RQ6** SQLite/Postgres & profile parity | **Table-set parity enforced; column parity NOT (F-05). Migration concurrency guard only on PG (F-04).** Both backends share logical migrations; psycopg2 sync repo for PG registry is benign (MVCC). | `test_migration_governance.py:23-27`; `postgres/projects.py:37-49` |
| **RQ7** Observability & test posture | **Weakest area.** No registry/DB-write health surfacing (F-09); registry test passes through failure (F-11). Coverage matrix §4. | `bootstrap.py:124-191`; `test_db_project_registry.py:107-145` |

---

## 4. RQ7 Test-Coverage Matrix

Legend: ✅ direct row/count/restart-survival assertion · ⚠️ functional-only (would pass through a silent
failure) · ❌ none · 💉 failure-injection / contention test.

| DB subsystem | Persistence asserted? | Failure-injection? | Highest-value gap |
|---|---|---|---|
| Project registry | ⚠️ two-instance read (`test_db_project_registry.py:107-145`) — **passes through F-01** | ❌ | Direct `repo.count()` post-flush **+ lock-contention injection** (the F-01 reproducer). **Top priority.** |
| Migration idempotency | ⚠️ `test_sqlite_migrations.py` runs once | ❌ | Run `run_migrations` twice on a populated DB; assert stable schema + no error. |
| Migration parity | ✅ table-set (`test_migration_governance.py:23-27`) | ❌ | **Column/constraint-level** sqlite↔postgres diff (F-05). |
| Migration concurrency | ❌ | ❌ | Two concurrent `run_migrations` on one SQLite file (F-04). |
| Retention / VACUUM | partial (`test_phase_1_*`, `test_composite_index_migration.py`) | ❌ | Prune-then-`COUNT` boundary; VACUUM reclaim assertion (freelist→0). |
| Sync-engine writes | ✅ broad (`test_sync_engine_*` suite, ~10 files incl. `_jsonl_persistence_regressions`, `_telemetry`) | ❌ | Contention test: registry flush *during* a sync write (the F-01 seam). |
| Queue repos (execution/job/telemetry/worktree) | ✅ + retry helper exercised | ⚠️ partial | Assert retry actually fires under injected `locked`. |
| Analytics repo | ✅ (`test_analytics_repo_lastrowid.py`, `test_analytics_scope_migration.py`) | ❌ | — adequate. |
| Storage-profile/backend parity | ✅ contract shape (`test_verify_db_layer.py:15-123`) | n/a | Does not assert column parity (covered by F-05 gap). |
| /api/health DB surfacing | ❌ (no registry/DB-write fields exist to test) | ❌ | Add fields (F-09) then assert them. |

**Top 3 test gaps to close in P0/P3:** (1) registry direct-count + lock-injection reproducer for F-01;
(2) column-level migration parity; (3) migration idempotency-on-rerun + concurrency.

---

## 5. ADR Recommendations (proposals for human ratification — ADR-006, ADR-007)

> Drafted as proposals (`status: proposed`). Inlined here per charter (not separate files) until ratified.

### ADR-006 (proposed) — Project Registry Authority Model: DB-authoritative, JSON import/export-only

- **Status:** proposed · **Context:** F-01, F-02, F-03 (RQ3). Two managers, two stores, no reconciliation;
  silent flush failure; intent already states "DB authoritative."
- **Options:** (A) JSON authoritative + DB derived write-through cache; (B) **DB authoritative + JSON
  import/export-only** (recommended); (C) status quo (rejected — split-brain).
- **Decision (recommended):** **Option B.** The registry is small, rarely written (admin ops), and must be
  consistent across the api+worker processes and (future) replicas — properties the DB provides and a
  per-process JSON file cannot. JSON becomes a *seed/import* artifact and an *export* target, never a live
  store. Consequences: (1) remove the dual instantiation (`project_manager.py:658` legacy manager retired
  or demoted to an `import_from_json()` helper); (2) the DB write **must be reliable** — bootstrap fails
  loud (F-01 fix), retries on locked, and is sequenced before/outside the heavy sync window; (3) provide
  an explicit `export_to_json()` for portability/backup; (4) `config.PROJECTS_FILE` becomes the import
  source only.
- **Why not A (write-through JSON-authoritative):** keeps the per-process-file consistency problem and
  conflicts with the stated enterprise multi-replica direction.
- **Reversibility:** export-to-JSON preserves the escape hatch; the change is code + ordering, no
  destructive data step.

### ADR-007 (proposed) — DB-Write Failure-Surfacing Standard

- **Status:** proposed · **Context:** F-01, F-06, F-09 (RQ7). Write-failure handling is inconsistent
  (registry swallows; queue repos retry; most propagate) and invisible externally.
- **Decision:** A uniform contract for every DB write path:
  1. **Never silently swallow a write failure.** A caught write exception must either (a) be retried via
     the shared locked-retry helper, then (b) re-raised if still failing, **or** (c) recorded to a
     surfaced status field — never logged-and-continued with a success-shaped return.
  2. **One locked-retry helper** in `repositories/base.py` (generalize `execution.py:_commit_with_retry`),
     applied to all writers including independent sync connections; every connection sets `busy_timeout`.
  3. **Surface failures:** increment `ccdash_db_write_failures_total{repo,reason}`; expose
     `registry.last_flush_status` and DB size/freelist gauges in `/api/health/detail` (F-09).
  4. **Test contract:** any new write path ships with a persistence assertion (direct count) and, for
     contention-prone paths, a lock-injection test.
- **Consequences:** small refactor of the registry + a shared helper; CI gains a failure-injection lane.
- **Enforcement:** F-09 health fields + the F-11 test become the regression guard.

---

## 6. Remediation Backlog (scopes the downstream Tier 3 PRD + Plan)

Grouped P0→P3. Sizing in story points (rough). Items reference findings/ADRs so the planner needs no
re-investigation. Items already owned by the **enterprise-liveness PRD** are marked `[liveness]` — *reference,
do not duplicate*.

### P0 — Correctness / data-loss (ship first, independently, reversible)

| ID | Item | Findings | Pts |
|---|---|---|---|
| P0-1 | Registry bootstrap **fails loud**: on flush exception do not set `_snapshot_loaded=True`; log ERROR with locked reason; retry-with-backoff on next access. | F-01 | 2 |
| P0-2 | Apply shared **locked-retry** to the registry sync write path; set `PRAGMA busy_timeout` on `SqliteProjectRepository`. | F-01, F-06 | 2 |
| P0-3 | **Sequence** registry bootstrap outside the heavy startup-sync window (lazy-on-first-request or pre-sync), removing the F-01 contention seam. | F-01, RQ5 | 2 |
| P0-4 | Ratify **ADR-006** (DB-authoritative); collapse dual managers / retire legacy `ProjectManager` or demote to `import_from_json`; add `export_to_json`. | F-02, ADR-006 | 3 |
| P0-5 | Registry **persistence test hardening**: direct `repo.count()` post-flush + lock-injection reproducer (the F-01 regression guard). | F-11 | 2 |

**P0 subtotal ≈ 11 pts.**

### P1 — Design coherence

| ID | Item | Findings | Pts |
|---|---|---|---|
| P1-1 | SQLite migration **first-boot concurrency guard** (flock / inter-process mutex), mirroring PG advisory lock. | F-04 | 3 |
| P1-2 | **Column/constraint-level parity** check in `migration_governance` + test (normalized per-table diff). | F-05 | 4 |
| P1-3 | Make `ensure_table` safety-nets call canonical migration DDL (single source) or delete after P0-3 ordering guarantees migrations-first. | F-08 | 3 |
| P1-4 | Standardize the **locked-retry helper** in `repositories/base.py`; apply to sync `sessions.py` helpers; audit all sync connections for `busy_timeout`. | F-06, ADR-007 | 3 |

**P1 subtotal ≈ 13 pts.**

### P2 — Durability / ops

| ID | Item | Findings | Pts |
|---|---|---|---|
| P2-1 | Enable retention (`RETENTION_PRUNE_ENABLED`) + one-time `VACUUM` runbook to reclaim 2.23 GB; document WAL-checkpoint strategy. | F-03 | 3 |
| P2-2 | `session_logs` dedupe/drop (flag-gated, staged). `[liveness P1-002/016]` — reference only. | F-03 | (liveness) |
| P2-3 | `telemetry_events` bounded growth + index-bloat review. `[liveness P1]` — reference; verify after retention on. | F-03 | 2 |

**P2 subtotal ≈ 5 pts new (rest owned by liveness PRD).**

### P3 — Observability / tests

| ID | Item | Findings | Pts |
|---|---|---|---|
| P3-1 | `/api/health/detail`: `registry.project_count`, `registry.last_flush_status`, `db.size_bytes`, `db.freelist_bytes`, `retention.last_run`. | F-09, ADR-007 | 3 |
| P3-2 | `ccdash_db_write_failures_total{repo,reason}` counter at retry/surface sites. | F-09, ADR-007 | 2 |
| P3-3 | Migration **idempotency-on-rerun** + **concurrency** tests. | F-04, F-07 | 3 |
| P3-4 | Record per-version migration ledger (or `migrations_applied` with applied_at). | F-07 | 2 |
| P3-5 | Remove dead `config.DB_PATH` default (or unify with `connection.py`). | F-10 | 1 |

**P3 subtotal ≈ 11 pts.**

**Total new remediation ≈ 40 pts (Tier 3)**, excluding liveness-PRD-owned destructive storage items.
Critical path: **P0-1→P0-2→P0-3** (registry correctness) gated by **P0-4/ADR-006**; ship before any P2
destructive reclaim. P1/P3 parallelize after P0.

---

## 7. What this audit changed vs the charter's hypotheses

- **Refuted (good news):** "broad exception swallowing around writes" is **not** a systemic repository
  pattern — 0 swallow-on-write sites in the async layer; failures propagate; retry exists in queue repos.
  The defect is **localized** to the sync registry path. This *shrinks* the P0 surface.
- **Confirmed + quantified:** DB bloat (2.23 GB dead pages, 40% of file in two unbounded tables),
  retention subsystem exists but is dormant, no registry/DB-write observability, registry test passes
  through the failure.
- **New findings beyond the charter:** F-04 (no SQLite migration concurrency guard vs PG advisory lock),
  F-05 (parity asserted at table-set but not column level), F-08 (triple-maintained `ensure_table` DDL),
  F-07 (single-row version ledger explains the live `schema_version` gaps — benign).
- **Root-cause sharpening of F-01:** the registry connection's `timeout=30` should survive a *simple*
  lock; its failure implies a **>30s WAL writer hold or checkpoint stall** from the sync engine — so
  `busy_timeout` tuning alone is insufficient; write-serialization/ordering (P0-3) is the real fix.
