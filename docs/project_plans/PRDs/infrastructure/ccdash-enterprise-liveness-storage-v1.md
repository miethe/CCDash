---
schema_version: 2
doc_type: prd
title: "CCDash Enterprise Liveness Hotfix & Storage Hygiene (Phase 0 + Phase 1)"
status: approved
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
priority: P0
risk_level: high
owner: nick
contributors: [Claude Opus 4.8]
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md
changelog_required: true
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/00-executive-summary.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/03-enterprise-edition-gap-analysis.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
  - .claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md
---

# CCDash Enterprise Liveness Hotfix & Storage Hygiene — PRD

> **This PRD is a thin contract over an existing analysis bundle.** The full forensic analysis,
> root-cause evidence (file:line), and per-task acceptance criteria live in the 7-document
> [enterprise-edition planning bundle](../../planning/ccdash-enterprise-edition-v1/README.md). Per the
> "decisions block is the delta" rule, this PRD does **not** restate that analysis — it scopes the work,
> records the resolved decisions, and points to the bundle. Anchors here are the **re-verified** current
> file:line locations (verify-state pass, 2026-05-30), which correct several drifted/incorrect anchors in
> the original bundle.

## 1. Executive Summary

A default containerized CCDash deploy (`docker compose --profile enterprise --profile postgres up`) reaches a
**healthy API serving an empty dashboard** — it ingests zero live session data and fails **silently**. This
PRD covers the two-phase fix:

- **Phase 0 — Enterprise Liveness Hotfix**: make a default enterprise deploy ingest live sessions with **zero
  extra flags**, and make any misconfiguration **fail loud** (worker `readyz` fails) instead of silently
  serving empty. No new subsystems — defaults, wiring, and a fail-loud readiness contract.
- **Phase 1 — Storage Hygiene & DB Performance**: shrink the 9.5 GB DB (retention/TTL, transcript dedupe),
  add missing indexes + SQLite pragmas, and kill the worst N+1 query storms (`_capture_analytics`,
  session-list badge derivation, `entity_graph` per-link commits).

## 2. Problem Statement

Verified root cause (gap-analysis §2): **three independent, compounding defects**, each alone sufficient to
leave the container DB empty: (a) ingestion disabled by default + worker-watch behind an opt-in profile;
(b) host-absolute `projects.json` paths unresolvable in-container with no auto-derived alias; (c) inotify
dead on bind mounts + a read-only `projects.json` that crashes on the startup migration write. All three pass
`readyz`. Compounding slowness (perf-forensics): unbounded `analytics_entries`/`telemetry_events`, ~1.75 GB
dead duplicate `session_logs`, an 8 MB page cache for a 9.5 GB DB, and ~12–15K queries per analytics snapshot.

## 3. Goals & Success Metrics

1. **Default enterprise compose ingests live sessions with zero extra flags** — `GET /api/sessions` returns
   ≥1 row after a fixture `.jsonl` is dropped into a watched path.
2. **Fail-loud readiness** — worker `readyz` returns 200 **iff** resolved watch-paths > 0; zero paths return
   503 with an actionable `configured_no_paths` reason.
3. **Live updates fire on Docker Desktop bind mounts** (`WATCHFILES_FORCE_POLLING=true` default for the watch
   worker).
4. **CI e2e smoke gate** is green on every PR touching `deploy/runtime/**` or `backend/runtime/**`.
5. **DB shrinks ≥ 3 GB** (Phase 1) via retention + transcript dedupe; `analytics_entries` bounded (~50×
   reduction); `_capture_analytics` issues single-digit batched queries per snapshot.

## 4. Scope

**In (Phase 0):** P0-001…P0-015 — default flips, path-alias auto-derivation, fail-loud `readyz`, force-polling,
writable/atomic `projects.json`, `entrypoint.sh` worker-watch dispatch, `frontend depends_on: api`,
`pg_advisory_lock` around migrations, canonical-source-key delete path, `STARTUP_SYNC_LIGHT_MODE`
reconciliation, CORS dev-gate, `CCDASH_PROJECTS_FILE` reconcile, `compose.hosted.yml` repair, startup
fail-loud log, and the CI e2e smoke gate.

**In (Phase 1):** P1-001…P1-018 — retention/TTL, transcript dedupe (flag-gated, staged), SQLite pragmas
(dev-only), backfilled indexes, `entity_links.project_id` column (Phase 2 prereq), N+1 rewrites,
`executemany` batching, materialized session badges, Postgres atomic upserts + UNIQUE-in-DDL,
schema-version reconcile, manifest scan skip, batch backfill.

**Out:** shared cache (Phase 2), DB-backed project registry / multi-project worker (Phase 3), frontend
performance (Phase 4), command center (Phase 5), observability/load-test (Phase 6).

## 5. Resolved Decisions (synthesis §8)

These §8 human decisions are touched by this scope and are **resolved** as follows (user-approved direction:
"include phase 1; reversible-by-default"):

| Decision | Gates | Resolution for this PRD |
|----------|-------|-------------------------|
| **Worker topology** | P0-001/008/013 | **watch-all in default enterprise topology** (fold worker-watch into `enterprise` profile). Mandated by the GOAL. Per-project isolation remains available via opt-in. |
| **Transcript storage** | P1-002, P1-016 | **Canonical `session_messages` + filesystem source-of-truth.** The destructive `session_logs` DROP ships **behind a default-OFF flag** (`CCDASH_SESSION_LOGS_DEDUPE_ENABLED`) and is **staged** (migrate consumers → stop populating → backfill-drop). Reversible until the operator opts in. |
| **SQLite future** | P1-006 | **SQLite stays dev-only.** Aggressive pragmas are **dev/SQLite-profile-gated**; enterprise = Postgres. |
| **STARTUP_SYNC_LIGHT_MODE** | P0-015 | `config.py` is the single source of truth (default False = full/local); align the two getattr fallbacks (`runtime.py`, `sync_engine.py`) to False; in-container worker/worker-watch default `CCDASH_STARTUP_SYNC_LIGHT_MODE=true` via compose so heavy passes defer to the worker loop. |
| **pgvector image** | P0-HOSTED-COMPOSE | Conservatively keep `pgvector:pg17` for the hosted variant (preserves vector support); `pg_advisory_lock` uses core Postgres and needs no pgvector. |

## 6. Verify-State Anchor Corrections (vs. bundle, 2026-05-30)

The verify-state pass corrected three load-bearing anchors the implementation must respect:

1. **`CCDASH_WORKER_STARTUP_SYNC_ENABLED` is compose-only — NOT read by `backend/config.py`.** Worker sync is
   gated by `CCDASH_STARTUP_SYNC_ENABLED` + worker `RuntimeProfile.capabilities.sync=True`. Flipping the
   phantom var alone has no backend effect.
2. **No active three-way light-mode mismatch today.** `config.py:966` always defines the attribute
   (default False), so the getattr fallbacks (`runtime.py` →True, `sync_engine.py` →False) never fire — the
   default startup currently runs **FULL/heavy**. The real consumer is `adapters/jobs/runtime.py` (not
   `bootstrap.py:188`, which is only a status-payload field).
3. **worker-watch overrides ingestion** via `CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED` (compose
   `:169`) — an additional lever for the default-on flip.

## 7. Acceptance Criteria

Phase 0 and Phase 1 acceptance criteria are enumerated per-task in the implementation plan and tracked in the
phase progress files. The **feature-level exit gate** is the CI `docker compose up` e2e smoke test (P0-013):
drop a fixture `.jsonl`, assert `GET /api/sessions` returns ≥1 row **and** worker `readyz` is 200 iff
watch-paths > 0. Phase 1 adds measurable DB-size/row-count/query-count assertions. Mandatory
`task-completion-validator` review before commit; `karen` at feature end (Tier 3).

## 8. Risks & Mitigations

- **Default-on ingestion triggers a heavy blocking startup sync** → mitigated by the P0-015 light-mode
  reconciliation (in-container light mode defers heavy passes to the worker loop).
- **Destructive Phase 1 ops** (`session_logs` drop, retention DELETE) → flag-gated default-OFF, staged, DB
  snapshot before first run, filesystem JSONL remains the re-derivable source of truth.
- **Schema migrations on a large DB** → `_ensure_index` backfills are `IF NOT EXISTS`/idempotent; advisory
  lock (P0-011) lands first.
- **Seam integrity** (cross-owner phases): every new optional backend field carries an explicit FE-fallback AC
  (resilience-by-default); UI-touching changes carry a runtime-smoke task.

## 9. Rollback

Phase 0 is entirely default flips / compose edits / additive guards — revert env defaults + compose anchors;
no schema migration, no data change. Phase 1 non-destructive items (pragmas, indexes, executemany, N+1
rewrites) are code-revert-safe; destructive items are flag-gated and snapshot-protected.
