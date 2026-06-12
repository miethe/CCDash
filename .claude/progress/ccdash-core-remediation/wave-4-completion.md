---
type: report
schema_version: 2
doc_type: report
report_category: wave-completion
prd: ccdash-core-remediation
feature_slug: ccdash-core-remediation
wave: 4
title: "Wave 4 Completion — P3 (session exposure) · P10 (external API) · P9 (Postgres/container)"
status: completed
created: 2026-06-11
updated: 2026-06-11
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs: [ca5a557]
merge_commit: ca5a557
merge_branch: epic/ccdash-core-remediation
phases: [3, 10, 9]
---

# Wave 4 Completion Report

**Scope:** Wave 4 = phases **P3, P10, P9** (run P3 → P10 → P9 within the worktree).
**Branch:** `wave4/ccdash-core-remediation` (off `epic/ccdash-core-remediation`), squash-merged to epic.
**Squash commit:** `ca5a557`.
**Pre-squash phased commits:** `9b3f52e` (P3) · `1db997c` (P10) · `c4e0237` (P9) · `db96365` (review hardening).

## Per-phase outcome

| Phase | Title | Verdict | runtime_smoke |
|-------|-------|---------|---------------|
| P3 | MCP session tools + repo-CLI session group + standalone CLI + 3-surface parity | ✅ completed | verified (MCP/CLI/REST parity + live REST sessions) |
| P10 | External `/api/v1` contract (capability, CORS/bind, optional bearer, OpenAPI, example client) | ✅ completed | verified (live api + example-client/LAN smoke) |
| P9 | Postgres parity + container/compose + durable coalescing + `/readyz` fail-loud | ✅ completed | verified (live pgvector compose stack) |

## Reviewer gates

- **senior-code-reviewer (read-only, ICA opus[1m]):** Initial verdict **CHANGES_REQUESTED** — the five P9
  fixes and P10 auth verified functionally correct (it traced the `_acquire()` Pool/Connection handling
  and the `left(captured_at,10)` index semantics in detail), but flagged compose security defaults + LOW
  hardening items. All **8 findings addressed** (commit `db96365`) and re-validated live → effectively
  APPROVED.
- **karen (read-only, ICA opus[1m]):** **PASS** on all three phases — no stubs/TODOs, tests assert real
  behavior, OpenAPI byte-identical to its regen script, example client matches shipped endpoints, auth
  additive/optional. Remaining items were process-closeout only (this report + progress files) plus the
  ADR-007 note below.

## PG/container defects surfaced by the live smoke gate (P9) and fixed

The unit suite passed while the running stack was broken — the live smoke gate caught five real defects:

1. **Functional-index IMMUTABLE violation** — `(captured_at::date)` on a TEXT column is STABLE → migrations
   aborted. Replaced with `left(captured_at, 10)` (IMMUTABLE) at 5 sites.
2. **pgvector required** — plain `postgres:15` lacks the `vector` extension used by enterprise
   session-intelligence → `CREATE EXTENSION` crashed. Compose pins `pgvector/pgvector:pg15`.
3. **`RuntimeJobState(@dataclass(slots=True))`** rejected `setattr(_drain_task)` → AttributeError aborted
   api/worker startup on the durable queue. Declared the `_drain_task` slot.
4. **`PostgresJobQueueRepository.transaction()` on an asyncpg `Pool`** (no `.transaction()`; per-statement
   calls would also span separate pooled connections, breaking `FOR UPDATE SKIP LOCKED`). Added `_acquire()`
   yielding a single Connection for the whole transaction.
5. **Worker crash-loop** — pinned to `CCDASH_WORKER_PROJECT_ID=smoke-stack` but the DB-authoritative
   registry (ADR-006) only looks up; a fresh DB could not resolve the binding. Added a one-shot compose
   `seed` service (POST `/api/projects`, tolerant of 200/201/409) gated by `service_completed_successfully`.

## Review-driven hardening (8 fixes, commit db96365)

HIGH — postgres host port bound to `127.0.0.1` by default (was `0.0.0.0` + default creds = LAN exposure).
MEDIUM — api (8000) + worker probe (9465) host ports bound to `127.0.0.1` by default; documented
`left(captured_at,10)` v34 upgrade-path invariant + added PG-gated `UpgradePathLeftCapturedAtTests`.
LOW — constant-time bearer compare (`hmac.compare_digest`); reject `"*"` CORS origins with
`allow_credentials=True`; `_readyz_check_db` observes connectivity instead of establishing it; seed reads
`CCDASH_WORKER_PROJECT_ID` via `os.environ`; fixed a migration doc-comment typo.

## Live evidence (pgvector/pgvector:pg15, loopback binds, host port 5433)

- `seed` → `SEED_OK 200 smoke-stack`; **api + worker + postgres all healthy**.
- api `/readyz` 200 `{db_connected, migration_head_applied, queue_reachable}`.
- worker `/readyz` 200 (ops-201 ready envelope, `db_connection` pass).
- `GET /api/v1/sessions` 200 (cross-project session against Postgres, AC-3); `GET /api/v1/capabilities` 200.
- PG-gated suite green against the live compose Postgres: migration governance + live schema parity +
  durable coalescing + readyz health + the 3 new upgrade-path tests.

## ADR-007 clarification (karen gap #3)

The new PostgreSQL `backend/db/repositories/postgres/job_queue.py` write paths satisfy the ADR-007
write-failure-surfacing standard via **transactional `FOR UPDATE SKIP LOCKED` concurrency** rather than the
SQLite-specific `retry_on_locked` helper (the two backends have different concurrency models). The
count-style coverage ADR-007 requires is provided by `test_pg_coalescing.py`. A one-line note to ADR-007
recording this equivalence is a recommended (non-blocking) follow-up so future reviewers do not flag it.

## Follow-ups (non-blocking)

- Add the ADR-007 equivalence note above to `docs/project_plans/adrs/adr-007-*.md`.
- LAN-exposure runbook: when overriding the loopback binds, operators must also set a strong
  `CCDASH_POSTGRES_PASSWORD` and `CCDASH_API_TOKEN` (already cross-referenced in
  `docs/guides/external-api-lan-deployment.md`).
- Independent reviewers reproducing P9 evidence must run `scripts/compose_smoke.sh` against
  `pgvector/pgvector:pg15` (the PG-gated tests skip without `CCDASH_DATABASE_URL`).

## Process notes

- Agent tool overflows on this repo's CLAUDE.md → all delegation ran via ICA `--bare` bash
  (`claude-sonnet-4-6[1m]` for edits, `claude-opus-4-8[1m]` for reviews) with root CLAUDE.md re-injection.
- The orchestrator (Opus) drove the live compose stack directly (not via a mutating delegate) to avoid
  mid-cutover kills, satisfying the T9-009 "Bash-enabled PG review" intent; reviewers ran read-only.
