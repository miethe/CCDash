---
schema_version: 2
doc_type: report
report_category: plan-completion
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
status: completed
created: 2026-06-28
updated: 2026-06-28
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
commit_refs: [037f03f, b94e633, 6710b92, 1b8acad]
---

# Remote CCDash Streaming v1 — Plan Completion Report

## Outcome

Remote CCDash session streaming v1 is **complete**. Phases 1–4 landed prior to this run
(transport-neutral ingest port, NDJSON ingest endpoint + local daemon, workspace-scoped
bearer auth, single-process multi-project routing). This run reconciled the feature branch
against 99 commits of `main` drift and delivered the remaining phases (6, 7, 8). Phase 5
(Entire.io checkpoint ingest) was **extracted** to its own standalone plan so v1 could close.

## Reconciliation (merge)

- `feat/remote-ccdash-streaming` was merged with `main` (merge commit `037f03f`), resolving a
  migration version collision (branch v28/v29 → renumbered v36/v37, `SCHEMA_VERSION = 37`,
  gated blocks placed **after** main's v31 sessions-PK rebuild so workspace/source columns
  survive) and pervasive `workspace_id` Protocol drift (made keyword-only with
  `DEFAULT_WORKSPACE_ID = "default-local"` so main's 99 commits of callers compile unchanged).
- Validated in isolation: migrations (v28/v29 renumber suites), ingest endpoint (10/10),
  workspace auth (6/6), repo + parser suites green. Two FK-mismatch failures in
  `test_sqlite_migrations` were verified pre-existing on clean `main` (not a regression).

## Phases delivered this run

| Phase | Scope | Commit | Evidence |
|-------|-------|--------|----------|
| 5 (extract) | Entire.io ingest moved to `entire-io-checkpoint-ingest-v1.md`; parent plan phase table / critical path updated | b94e633 | new plan file; parent Phase 5 marked EXTRACTED |
| 6 | `ingest_sources` health rollup (`/api/health/detail`) + session `source` discriminator; FE `SessionSourceChip` + `IngestHealthBadge` | 6710b92 | 8 backend + 28 FE tests pass |
| 7 | Daemon dead-letter `replay` CLI + `retry_total`/`abandoned_total`/`deadlettered_total` counters; operator + v1→v2 migration guides | 1b8acad (code) + docs commit | 12 replay tests pass |
| 8 | CHANGELOG `[Unreleased]`, README, CLAUDE.md pointers, ADR collision renumber (006/007 streaming → 014/015), plan finalize | docs commit | this report |

## Reconciliation against merged reality (what was already done)

The merge brought much of the original Phase 7 scope forward: the daemon already had
retry/backoff (max 10, exp backoff capped 60 s, `Retry-After`-aware), 413 batch-splitting,
and local dead-letter NDJSON files; `auth_mode` was already in `/api/health`. Phase 7 was
therefore scoped down to the genuine gaps: dead-letter **replay** + counter exposure + the
operator/migration guides. Server-side dead-letter persistence was assessed as gold-plating
for v1 (the client-side dead-letter + replay satisfies the "dead-letter OR observability"
exit criterion) and is noted as a future item.

## ADR collision resolution

The branch introduced `adr-006-remote-session-ingest-*` and `adr-007-local-daemon-*`, which
collided with main's canonical `adr-006-db-authoritative-project-registry` and
`adr-007-db-write-failure-surfacing-standard`. The streaming pair was renumbered to
**ADR-014** (transport) and **ADR-015** (daemon); all full-stem links and in-set bare
references (adr-008/009/010 + the two renamed files) were updated. DB ADR-006/007 references
were left untouched.

## Deferred

- Phase 5 / Entire.io → `docs/project_plans/implementation_plans/features/entire-io-checkpoint-ingest-v1.md` (draft).
- DEF-001..DEF-005 (cloud-Entire, live transcript streaming, record-level merge, SaaS
  multi-tenant, bidirectional sync) carried to the entire-io plan; design specs remain
  unauthored (targets, not blockers) per the v1 deferral policy.
- Server-side dead-letter table + query API (operator visibility beyond client-side files).

## Runtime smoke

`runtime_smoke: skipped` — UI changes (SessionSourceChip, IngestHealthBadge) verified via
`tsc --noEmit` (no errors in changed files) + 38 Vitest tests; a live browser smoke was not
run in the worktree. The new components render null/neutral on absent optional fields
(resilience-by-default), bounding visual risk.
