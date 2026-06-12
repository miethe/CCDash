---
schema_version: 2
doc_type: phase_plan
title: "CCDash Core Remediation v1 — Phases 7 & 8: Sync Coalescing + Cross-Project Freshness"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 7
phase_title: "Sync coalescing + recent-first + startup hygiene; Cross-project freshness hardening"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
feature_version: "v1"
priority: high
risk_level: high
changelog_required: true
entry_criteria:
  - "Phase 0 (cross-project session correctness) is green: project_id enforced on get_by_id/get_many_by_ids in both backends."
  - "Postgres durable-queue backend reachable for coalescing validation (JOB_QUEUE_BACKEND != memory); SQLite/memory path also exercisable."
  - "No other phase holds an open edit lock on backend/db/sync_engine.py, backend/runtime/*.py, or backend/config.py (shared-file single-threading — see Shared-File Ownership below)."
exit_criteria:
  - "Zero duplicate full-sync events per project per trigger under Postgres durable queue (unit test + log assertion)."
  - "Recent sessions queryable within seconds of startup via recent-first window; backfill count == baseline full-scan count (no silent partial)."
  - "A plan/doc added to a non-active project appears within one reconcile interval; crashed watcher self-heals within one reconcile interval; non-active writeback stays off."
  - "task-completion-validator signs off both phases; ultrathink-debugger concurrency review (Phase 7) signed off."
---

# Implementation Plan — Phases 7 & 8: Sync Coalescing + Cross-Project Freshness Hardening

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION-P7-8`
**Parent plan**: `docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md`
**PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
**Decisions block**: `.claude/worknotes/ccdash-core-remediation/decisions-block.md`

> This file expands **Phase 7** and **Phase 8** only. Architecture, layered conventions, ADR-006/007 invariants, and the transport-neutral pattern are defined in root `CLAUDE.md` and are referenced, not restated. Root-cause evidence is in `docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md` — do not restate.

## Executive Summary

Phase 7 adds a `project_id`-keyed sync **coalescing/idempotency guard** at the sync-dispatch level (in-process *and* durable-queue), so the genuine double-scan that exists only under `JOB_QUEUE_BACKEND != memory` (Postgres) is eliminated; it adds **recent-first parse + lazy backfill** so recent sessions are queryable within seconds, and reduces `--reload` boot cost. Phase 8 hardens **cross-project freshness**: a periodic all-projects reconcile, watcher liveness **self-heal**, `SYNC_ALL_PROJECTS=False` + post-boot directory registration, and docs/plans freshness parity. Cross-project watchers already register for all projects and survive active-switch (verified) — Phase 8 is **hardening, not a rebuild**.

## Shared-File Ownership (CRITICAL — single-threaded)

Per the decisions block Risk Hotspots and PRD §9: **Phases 5, 7, and 8 all edit `backend/db/sync_engine.py`, `backend/runtime/*.py` (runtime.py family), and `backend/config.py`.** These files MUST be edited under **sequential ownership** — never run parallel agents on them.

| File | P5 (Detection) | P7 (this file) | P8 (this file) | Ownership rule |
|------|:--------------:|:--------------:|:--------------:|----------------|
| `backend/db/sync_engine.py` | yes | yes | yes | One agent at a time. P7 lands coalescing + recent-first before P8 touches reconcile paths. |
| `backend/runtime/runtime.py` (+ runtime/ package) | yes | yes | yes | P7 owns boot-cost reduction edit; P8 owns reconcile-scheduler registration. Serialize: P7 → P8. |
| `backend/config.py` | yes | yes | yes | Additive env vars only; each phase appends its own block. Serialize edits; no concurrent writes. |

**Orchestration constraint**: within this wave, **execute Phase 7 fully (incl. validator sign-off) before starting Phase 8.** Both are in the parent plan's Wave 2/Wave 3 split, but their shared `sync_engine.py`/`runtime.py`/`config.py` surface forces in-order execution relative to each other and to Phase 5. Confirm no Phase 5 agent holds these files before either phase begins.

## Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Provider | Profile | Notes |
|-------|-------|----------|--------------------|---------:|----------|---------|-------|
| 7 | Sync coalescing + recent-first + startup hygiene | ~5 pts | python-backend-engineer / backend-architect; ultrathink-debugger (concurrency) | sonnet | claude | — | Concurrency-sensitive; Codex debug-escalation only if guard stalls >2 cycles |
| 8 | Cross-project freshness hardening | ~5 pts | python-backend-engineer; data-layer-expert | sonnet | claude | — | Hardening of existing all-projects watcher; not a rebuild |

**Effort/Model conventions** per parent plan + template §"Phase Breakdown" column conventions: executors `sonnet`/`adaptive`; docs `haiku`/`adaptive`. Effort is reasoning budget, never a size estimate.

---

## Phase 7: Sync Coalescing + Recent-First + Startup Hygiene

### Overview

The default-dev path is a single scan per project (active skipped by the all-projects loop, `runtime.py:811`). The pain is `uvicorn --reload` re-running the always-on startup sweep, and a **real** double-scan that exists **only** when `JOB_QUEUE_BACKEND != memory` (Postgres durable queue) because there is no dispatch-level coalescing. Phase 7 introduces a `project_id`-keyed coalescing/idempotency guard at sync dispatch covering both the in-process scheduler and the durable queue, plus recent-first parse with lazy backfill and a `--reload` boot-cost reduction. OQ-3 (recent-first window definition) is resolved here.

### Entry Criteria

- Phase 0 green (project_id enforcement) — coalescing key is `(project_id, trigger)`; correctness depends on project_id integrity.
- Durable-queue backend reachable so the guard's durable path is testable (memory path always testable).
- Shared files (`sync_engine.py`, `runtime.py`, `config.py`) not held by Phase 5 or Phase 8 agents.

### Exit Criteria

- Zero duplicate full-sync per `(project_id, trigger)` under Postgres durable queue (unit test + log assertion; no silent dedupe — coalesced events logged).
- Recent sessions queryable within seconds of startup (recent-first window populated first).
- Backfill count == baseline full-scan count (deferred/dropped counts logged, never silently capped).
- `--reload` boot cost measurably reduced vs. baseline (no re-running of an unchanged full sweep on reload).
- ultrathink-debugger concurrency review + task-completion-validator signed off.

### Files Affected (from decisions block / PRD key-files — NOT read)

- `backend/db/sync_engine.py` — dispatch-level coalescing guard insertion point; recent-first parse ordering.
- `backend/runtime/runtime.py` (all-projects startup loop, `runtime.py:811`) — `--reload` boot-cost reduction; dispatch wiring.
- `backend/adapters/jobs/` (in-process scheduler + runtime background job adapter) — in-proc coalescing key; durable-queue dedupe seam.
- `backend/config.py` — new env vars: coalescing toggle/window, recent-first window definition (OQ-3), reload-skip toggle.
- `backend/parsers/sessions.py` — recent-first ordering input (mtime/recency sort); lazy-backfill cursor (read for ordering contract only by the executor — Opus does NOT read it here).
- `backend/db/repositories/sessions.py` — backfill upsert path must use `repositories/base.py:retry_on_locked` per ADR-007; SQLite connections issue `PRAGMA busy_timeout = 30000`.
- `backend/tests/` — coalescing unit test, recent-first/backfill-parity test, reload boot-cost assertion.

### Task Table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|--------------------|----------|-------------|-------|--------|
| T7-001 | Design coalescing key + resolve OQ-3 | Define the dispatch-level idempotency contract: coalescing key `(project_id, trigger, scope)`; in-proc guard (dict/lock keyed by key) + durable-queue dedupe (queue-level idempotency token). Resolve OQ-3: choose recent-first window (recommend last-K-days OR N-most-recent with mtime tiebreak) and document the choice + rationale inline. No code yet — produce the seam contract the executor tasks implement. | See **AC 7.1** | 1 pt | backend-architect | sonnet | extended |
| T7-002 | In-process coalescing guard | Implement the in-proc coalescing/idempotency guard at sync dispatch in `sync_engine.py` + `adapters/jobs/` so concurrent/duplicate dispatches for the same `(project_id, trigger)` collapse to one in-flight run. Coalesced events MUST be logged (count + key), never silently dropped. | See **AC 7.2** | 1 pt | python-backend-engineer | sonnet | adaptive |
| T7-003 | Durable-queue coalescing guard | Extend the guard to the durable queue path (`JOB_QUEUE_BACKEND != memory`): idempotency token / dedupe on enqueue so Postgres-backed dispatch cannot double-scan a project per trigger. Write path uses `retry_on_locked` (ADR-007); new independent connections set `PRAGMA busy_timeout = 30000` where SQLite is involved. | See **AC 7.2** (durable variant) | 1 pt | python-backend-engineer | sonnet | adaptive |
| T7-004 | Recent-first parse + lazy backfill | Reorder parse so the recent-first window (per T7-001) populates first and is queryable in seconds; remaining sessions backfill lazily behind a flag (`CCDASH_SYNC_RECENT_FIRST_ENABLED`). Assert backfill total equals the baseline full-scan count; log deferred/dropped counts. No silent caps. | See **AC 7.3** | 1 pt | python-backend-engineer | sonnet | adaptive |
| T7-005 | Reload boot-cost reduction | Reduce `uvicorn --reload` boot cost: skip re-running the always-on startup sweep when inputs are unchanged (reuse/coordinate with existing `CCDASH_STARTUP_SYNC_LIGHT_MODE` manifest-skip rather than introducing a parallel mechanism). Gate behind a config toggle; default preserves current behavior unless explicitly enabled. | See **AC 7.4** | 0.5 pts | python-backend-engineer | sonnet | adaptive |
| T7-006 | Concurrency proof + tests | Author: (a) coalescing unit test asserting one full-sync per `(project_id, trigger)` under durable queue with N concurrent dispatches; (b) recent-first/backfill-parity test (`backfill_count == baseline_full_scan_count`); (c) reload boot-cost assertion (sweep skipped on unchanged reload). Run under both memory and durable-queue backends. | See **AC 7.5** | 1 pt | python-backend-engineer | sonnet | adaptive |
| T7-007 | Concurrency review (gate) | ultrathink-debugger reviews the guard for race conditions (TOCTOU on the in-proc key, durable token uniqueness under contention, lock scope vs. project_id). Escalate to gpt-5.3-codex only if unresolved after 2 cycles (per decisions block). | Concurrency review signed off; no unresolved race finding | 0.5 pts | ultrathink-debugger | sonnet | extended |

### Structured Acceptance Criteria — Phase 7

#### AC 7.1: Coalescing contract + recent-first window resolved (OQ-3)
- resilience: >
    When `JOB_QUEUE_BACKEND == memory`, the in-proc guard is authoritative; when `!= memory`, the durable
    dedupe token is authoritative and the in-proc guard is a fast-path. The contract MUST define behavior when
    the project_id is NULL/'' (Phase 0 tolerance): such a key is treated as a single degenerate bucket, never
    merged across distinct projects.
- propagation_contract: >
    Coalescing key `(project_id, trigger, scope)` is computed at the single dispatch entry point in
    sync_engine.py and threaded to both the in-proc scheduler (adapters/jobs/) and the durable-queue enqueue.
    Recent-first window value is sourced from backend/config.py (env-configurable) and read by parsers/sessions.py.
- visual_evidence_required: false
- verified_by:
    - T7-006
    - T7-007

#### AC 7.2: No duplicate full-sync per (project_id, trigger)
- resilience: >
    Coalesced/deduped dispatches are LOGGED (structured: key + coalesced count), never silently dropped.
    Under durable-queue contention, at-most-one full-sync per key holds; a second concurrent enqueue is a no-op
    that logs the dedupe, not an error.
- propagation_contract: >
    Guard applies identically across in-proc (memory backend) and durable-queue (postgres backend) paths;
    same key derivation, divergent enforcement primitive (lock vs. idempotency token).
- visual_evidence_required: false
- verified_by:
    - T7-006
    - T7-007

#### AC 7.3: Recent-first + lazy backfill is complete (no silent partial)
- resilience: >
    If the recent-first window is empty or the flag is off, behavior falls back to baseline full-scan ordering
    (no regression). Lazy backfill MUST log deferred and dropped counts; the run is not "complete" until
    backfill_count == baseline_full_scan_count. A partial backfill surfaces as a logged warning + non-complete
    status, never a silent cap.
- propagation_contract: >
    `CCDASH_SYNC_RECENT_FIRST_ENABLED` (config.py) gates the ordering; parsers/sessions.py emits recent window
    first, then enqueues backfill; backfill upserts go through repositories/sessions.py using retry_on_locked.
- visual_evidence_required: false
- verified_by:
    - T7-006

#### AC 7.4: Reload boot-cost reduction (no double-sweep on unchanged reload)
- resilience: >
    Reduction is opt-in via config toggle; when disabled, current `--reload` behavior is preserved exactly.
    When enabled and inputs ARE changed, the sweep still runs (no stale skip). Coordinates with existing
    CCDASH_STARTUP_SYNC_LIGHT_MODE manifest mechanism — does not introduce a parallel skip path.
- propagation_contract: >
    runtime.py startup loop consults the manifest/light-mode skip before dispatching the all-projects sweep on
    a reload-triggered boot.
- visual_evidence_required: false
- verified_by:
    - T7-006

#### AC 7.5: Tests pass under both backends
- resilience: >
    The coalescing test runs under memory AND durable-queue (postgres) backends; a backend that is unavailable
    in the test env is skipped with an explicit skip reason, not a silent pass.
- propagation_contract: >
    Tests live under backend/tests/ and exercise the dispatch entry point, not internal helpers, so the seam
    contract (AC 7.1) is verified end-to-end.
- visual_evidence_required: false
- verified_by:
    - T7-006
    - T7-007

### Phase 7 Quality Gate

- [ ] **ultrathink-debugger** concurrency review signed off (T7-007) — mandatory for the guard.
- [ ] **task-completion-validator** confirms all AC 7.1–7.5 met with evidence.
- [ ] All new write paths use `retry_on_locked`; independent SQLite connections set `PRAGMA busy_timeout = 30000` (ADR-007 + CLAUDE.md).
- [ ] No silent caps or silent dedupe — coalesced/deferred/dropped counts logged.

---

## Phase 8: Cross-Project Freshness Hardening

### Overview

Cross-project watchers already register for all projects and survive active-switch (verified in the diagnostic) — Phase 8 is **hardening**, moderated priority. It adds: a periodic **all-projects reconcile** sweep (catches missed filesystem events and post-boot directory additions), **watcher liveness self-heal** (a crashed/dead watcher is detected and re-bound within one reconcile interval), `SYNC_ALL_PROJECTS=False` semantics + **post-boot directory registration** (projects/dirs added after boot are picked up without restart), and docs/plans freshness parity (a plan added to a non-active project appears within the reconcile interval). Non-active project **writeback** must stay off (regression-tested). OQ-4 (reconcile cadence + registry-change-event-driven feasibility) is resolved here.

### Entry Criteria

- **Phase 7 complete and validator-signed-off** — Phase 8 edits the same `sync_engine.py`/`runtime.py`/`config.py` surface and depends on Phase 7's dispatch coalescing existing (reconcile dispatches must coalesce, not double-scan).
- Phase 0 green (project_id enforcement) — reconcile reads/writes are per-project.

### Exit Criteria

- A plan/doc added to a **non-active** project appears within one reconcile interval (no restart).
- A crashed/dead watcher self-heals (re-binds) within one reconcile interval.
- `SYNC_ALL_PROJECTS=False` honored; post-boot directories registered without restart.
- Non-active project writeback remains **off** (regression test).
- Docs/plans parity verified for a non-active project.
- task-completion-validator signed off.

### Files Affected (from decisions block / PRD key-files — NOT read)

- `backend/db/sync_engine.py` — periodic reconcile sweep entry; dispatches through Phase 7's coalescing guard.
- `backend/runtime/runtime.py` — reconcile scheduler registration; post-boot directory registration hook; `SYNC_ALL_PROJECTS` honoring at the all-projects loop (`runtime.py:811`).
- `backend/db/file_watcher.py` — watcher liveness check + self-heal re-bind; post-boot directory add.
- `backend/config.py` — new env vars: `CCDASH_SYNC_ALL_PROJECTS` (default False), reconcile cadence (OQ-4), watcher-heal interval.
- `backend/project_manager.py` / DB-authoritative registry (ADR-006) — reconcile enumerates projects from the **DB registry**, not `projects.json` (ADR-006 invariant); registry-change detection for post-boot dirs.
- `backend/adapters/jobs/` — periodic reconcile job registration on the scheduler.
- `backend/tests/` — reconcile-freshness test, watcher self-heal test, post-boot dir test, non-active writeback regression test.

### Task Table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|--------------------|----------|-------------|-------|--------|
| T8-001 | Resolve OQ-4 + reconcile design | Decide reconcile cadence (recommend interval-based now; note registry-change-event feasibility for a fast-follow if cheap). Define the reconcile sweep: enumerate all projects from the **DB-authoritative registry** (ADR-006), dispatch a per-project freshness pass **through Phase 7's coalescing guard** (no double-scan). Document `SYNC_ALL_PROJECTS=False` semantics. Seam contract only. | See **AC 8.1** | 1 pt | python-backend-engineer | sonnet | extended |
| T8-002 | Periodic all-projects reconcile | Implement the periodic reconcile job (register on scheduler in `adapters/jobs/` + `runtime.py`). Each tick enumerates DB-registry projects and dispatches a coalesced freshness pass so missed FS events / post-boot changes are caught. Reconcile dispatch MUST go through the Phase 7 guard (AC dependency). | See **AC 8.2** | 1.5 pts | python-backend-engineer | sonnet | adaptive |
| T8-003 | Watcher liveness self-heal | Add a liveness check in `file_watcher.py` (and reconcile tick): detect a dead/crashed watcher and re-bind it within one reconcile interval. Self-heal events logged. | See **AC 8.3** | 1 pt | data-layer-expert | sonnet | adaptive |
| T8-004 | SYNC_ALL_PROJECTS + post-boot dirs | Add `CCDASH_SYNC_ALL_PROJECTS` (default False) honored at the all-projects loop; register directories/projects added **after boot** (via reconcile enumeration of the DB registry) without requiring a restart. Non-active writeback stays off. | See **AC 8.4** | 1 pt | python-backend-engineer | sonnet | adaptive |
| T8-005 | Docs/plans parity + writeback regression | Author tests: (a) plan/doc added to a non-active project appears within one reconcile interval; (b) crashed watcher self-heals within one interval; (c) post-boot directory picked up without restart; (d) **regression**: non-active project writeback remains off. | See **AC 8.5** | 1 pt | python-backend-engineer | sonnet | adaptive |

### Structured Acceptance Criteria — Phase 8

#### AC 8.1: Reconcile cadence resolved (OQ-4) + DB-registry-sourced
- resilience: >
    Reconcile enumerates projects from the DB-authoritative registry (ADR-006) — never from projects.json
    directly. If the registry is empty or a project row is malformed, reconcile skips that entry with a logged
    warning and continues (one bad project never stalls the whole sweep).
- propagation_contract: >
    Cadence value lives in backend/config.py (env-configurable); the reconcile scheduler in adapters/jobs/ +
    runtime.py reads it; each per-project pass is dispatched through the Phase 7 coalescing guard.
- visual_evidence_required: false
- verified_by:
    - T8-005

#### AC 8.2: Non-active project freshness within reconcile interval
- resilience: >
    A plan/doc added to a non-active project becomes visible within one reconcile interval with NO server
    restart and NO active-project switch. If the reconcile pass coincides with a watcher event for the same
    project, the Phase 7 guard coalesces them (no double-scan).
- propagation_contract: >
    Reconcile sweep (sync_engine.py) → per-project freshness pass (coalesced via Phase 7 guard) →
    repositories upsert (retry_on_locked) → queryable via existing read paths (Phase 0 project_id-scoped).
- visual_evidence_required: false
- verified_by:
    - T8-005

#### AC 8.3: Watcher self-heal within reconcile interval
- resilience: >
    A crashed/dead watcher is detected and re-bound within one reconcile interval. Self-heal events are logged
    (project + reason). If re-bind fails, the failure is logged and retried on the next tick — never a silent
    permanently-dead watcher.
- propagation_contract: >
    file_watcher.py exposes a liveness predicate; the reconcile tick (or a dedicated heal job in adapters/jobs/)
    polls it and re-registers dead watchers from the DB registry.
- visual_evidence_required: false
- verified_by:
    - T8-005

#### AC 8.4: SYNC_ALL_PROJECTS=False + post-boot dirs, writeback stays off
- resilience: >
    When CCDASH_SYNC_ALL_PROJECTS=False, only the active project is swept on the hot path, BUT reconcile still
    provides cross-project freshness (decoupled from the hot-path sweep). Directories/projects added after boot
    are registered via the next reconcile tick without restart. Non-active project writeback remains OFF — a
    non-active reconcile pass is read/ingest-only.
- propagation_contract: >
    Config flag (config.py) is honored at runtime.py:811 all-projects loop; post-boot registration flows from
    the DB-registry enumeration in the reconcile sweep.
- visual_evidence_required: false
- verified_by:
    - T8-005

#### AC 8.5: Freshness + self-heal + writeback regression tests pass
- resilience: >
    Tests assert positive freshness (doc appears), self-heal (watcher re-binds), post-boot pickup, AND the
    negative writeback contract (non-active writeback off). The writeback-off assertion is a permanent
    regression fixture — missing writeback guard is a contract failure, not a warning.
- propagation_contract: >
    Tests under backend/tests/ exercise reconcile + watcher self-heal end-to-end against a two-project fixture
    (active + non-active).
- visual_evidence_required: false
- verified_by:
    - T8-005

### Phase 8 Quality Gate

- [ ] **task-completion-validator** confirms all AC 8.1–8.5 met with evidence.
- [ ] Reconcile enumerates projects from the **DB-authoritative registry** (ADR-006) — no direct `projects.json` use.
- [ ] All reconcile dispatches go through the **Phase 7 coalescing guard** (no double-scan reintroduced).
- [ ] Non-active writeback-off regression fixture present and green.
- [ ] New write paths use `retry_on_locked`; independent SQLite connections set `PRAGMA busy_timeout = 30000`.

---

## Cross-Phase Notes

- **Sequential ownership** of `sync_engine.py` / `runtime.py` / `config.py` across Phases 5 → 7 → 8 is mandatory (see Shared-File Ownership). Phase 8 depends on Phase 7's coalescing guard existing; do not start Phase 8 until Phase 7 is validator-signed-off.
- **No FE surfaces** in either phase — R-P4 (runtime smoke) and R-P3 (integration_owner) do not apply; both phases are backend-only.
- **R-P1 applied**: ACs referencing "any project" / "all projects" / freshness "within interval" were expanded with explicit propagation_contract + resilience clauses above (no multi-`.tsx`-surface lists needed because there are no UI surfaces; the "surfaces" here are backend dispatch paths, documented in propagation_contract).
- **Resilience-by-default** (CLAUDE.md): new env-gated behaviors (recent-first, reload-skip, SYNC_ALL_PROJECTS) all preserve baseline behavior when disabled; missing/empty inputs are logged contract states, not errors.
- **Observability**: coalesced/deferred/dropped counts (P7) and self-heal events (P8) are structured-logged; full watcher-liveness freshness probes are added in Phase 12 (out of scope here, referenced).
- **changelog_required: true** — user-facing changes (faster startup, cross-project freshness without restart) land a CHANGELOG `[Unreleased]` entry in Phase 12.

## Progress Tracking

- Phase 7: `.claude/progress/ccdash-core-remediation/phase-7-progress.md`
- Phase 8: `.claude/progress/ccdash-core-remediation/phase-8-progress.md`
