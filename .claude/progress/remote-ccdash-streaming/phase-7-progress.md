---
schema_version: 2
doc_type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 7
status: completed
created: 2026-06-28
updated: 2026-06-28
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
commit_refs: [1b8acad]
owners: [python-backend-engineer, documentation-writer]
tasks:
  - id: T7-001
    status: completed
    assigned_to: [python-backend-engineer]
    evidence: ["commit:1b8acad", "test:packages/ccdash_cli/tests/test_daemon_replay.py"]
  - id: T7-002
    status: completed
    assigned_to: [python-backend-engineer]
    evidence: ["commit:1b8acad"]
  - id: T7-003
    status: completed
    assigned_to: [documentation-writer]
    evidence: ["doc:docs/guides/remote-ingest-operator-guide.md"]
  - id: T7-004
    status: completed
    assigned_to: [documentation-writer]
    evidence: ["doc:docs/guides/remote-streaming-v1-to-v2-migration.md"]
---

# Phase 7 — Hardening, Migration Guides, Telemetry

Scope reconciled against merged reality: the daemon already shipped retry/backoff (max 10,
exp backoff capped 60 s, `Retry-After`-aware), 413 batch-splitting, and dead-letter NDJSON
files; `auth_mode` already in `/api/health`. Remaining gaps closed here:

- **T7-001** `ccdash-cli daemon replay` — re-POSTs dead-letter `*.ndjson` via the existing
  `_post_batch` path (`--dir`, `--dry-run`, `--purge`); successes → `replayed/`, permanent
  failures stay in place; missing dir exits 0.
- **T7-002** `retry_total` / `abandoned_total` counters added to `_Counters`, surfaced in the
  status-file JSON and `daemon status` output (alongside `deadlettered_total`).
- **T7-003** Operator guide: failure scenarios, troubleshooting, cursor-lag interpretation via
  `/api/health/detail` `ingest_sources` state, rollback.
- **T7-004** v1→v2 migration guide: local single-user → remote multi-workspace; additive
  schema v35→v37 (no manual steps; `default-local` workspace), auth progression, rollback.

**Deferred**: server-side dead-letter persistence + query API (client-side dead-letter +
replay satisfies the "dead-letter OR observability" exit criterion). 12 replay tests pass.
