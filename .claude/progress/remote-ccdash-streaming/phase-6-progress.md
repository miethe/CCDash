---
schema_version: 2
doc_type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 6
status: completed
created: 2026-06-28
updated: 2026-06-28
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
commit_refs: [6710b92]
owners: [python-backend-engineer, ui-engineer-enhanced]
tasks:
  - id: T6-001
    status: completed
    assigned_to: [python-backend-engineer]
    evidence: ["commit:6710b92", "test:backend/tests/test_ingest_sources_health.py"]
  - id: T6-002
    status: completed
    assigned_to: [python-backend-engineer]
    evidence: ["commit:6710b92"]
  - id: T6-003
    status: completed
    assigned_to: [ui-engineer-enhanced]
    evidence: ["commit:6710b92", "test:components/__tests__/SessionSourceChip.test.tsx"]
  - id: T6-004
    status: completed
    assigned_to: [ui-engineer-enhanced]
    evidence: ["commit:6710b92", "test:components/__tests__/IngestHealthBadge.test.tsx"]
---

# Phase 6 — Frontend Source Attribution + Daemon/Ingest Health

- **T6-001** `ingest_sources` health rollup query (`agent_queries/ingest_sources.py`) reading
  `ingest_cursors` → per-source `{last_ingest_at, lag_seconds, state}`; wired into
  `/api/health/detail`. State buckets via `CCDASH_INGEST_SOURCE_FRESH_SECONDS` (300) /
  `_STALE_SECONDS` (900). Resilient: missing table / error → `[]`.
- **T6-002** Session `source` discriminator (`filesystem`/`remote`/`entire`/`unknown`) derived
  from `source_ref` prefix, added additively to session-detail payload + `AgentSession` type.
- **T6-003** `SessionSourceChip` (rendered in `SessionCard` + `SessionInspector`); renders null
  when `source` absent (resilience-by-default).
- **T6-004** `IngestHealthBadge` (worst-state-wins over `ingestSources[]`; neutral "Local only"
  when empty), mounted alongside `SystemMetricsChip` in `Dashboard`; `ingestSources` threaded
  through `RuntimeStatus` normalization.

**Verification**: 8 backend + 28 FE tests pass; `tsc --noEmit` clean for changed files.
`runtime_smoke: skipped` — live browser smoke not run in worktree; components fail safe on
absent optional fields. See `plan-completion.md`.
