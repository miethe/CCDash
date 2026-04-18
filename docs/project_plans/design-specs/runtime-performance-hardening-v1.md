---
schema_version: "1.0"
doc_type: design-spec
title: "CCDash Runtime Performance Hardening v1"
status: draft
created: "2026-04-17"
feature_slug: "runtime-performance-hardening"
meta_plan_ref: "docs/project_plans/meta_plans/performance-and-reliability-v1.md"
related_plans:
  - "docs/project_plans/implementation_plans/db-caching-layer-v1.md"
  - "docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md"
  - "docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md"
tags: [performance, memory, reliability, sync, cache]
---

# CCDash Runtime Performance Hardening v1

Covers performance and reliability work **not** already captured in the three
existing initiatives (data-platform-modularization, deployment-runtime-modularization,
db-caching-layer). Those plans deliver the foundation (storage profiles, runtime
separation, TTL query cache, sync engine). This spec addresses the residual
issues operators still observe after those foundations land.

## 1. Problem Statement

Three operator-visible symptoms are **not** addressed by the linked plans:

1. **Frontend tab memory growth (2GB+)** — polling loops, unbounded session-log
   arrays, unbounded document pagination, and an in-flight request map that
   leaks on network failure. Live updates keep firing after the backend
   terminates.
2. **Startup link-rebuild double-work + redundant full filesystem scans** — on
   every boot the scheduler runs a full sync, then (with defaults) runs a
   second deferred full link rebuild. Any downstream entity change also triggers
   a full rebuild.
3. **Cold windows in cached agent queries + N+1 workflow detail fetches** —
   default TTL (60s) expires four times per warmer cycle (300s), and
   `get_workflow_registry_detail()` is called per-workflow in a loop.

## 2. Non-goals

- Rebuilding the sync engine (covered by db-caching-layer).
- Changing storage profile contracts (covered by data-platform-modularization).
- Runtime/worker packaging (covered by deployment-runtime-modularization phases 4-6).

## 3. Design

### 3.1 Frontend memory hardening

**3.1.1 Transcript log windowing (`components/SessionInspector.tsx`,
`services/live/sessionTranscriptLive.ts`)**

- Cap `session.logs` to a soft max (default 5000 rows) using a ring buffer
  semantics on live append; when the cap is exceeded, drop oldest rows and
  emit a `transcriptTruncated` marker so the UI can show "older messages hidden".
- Add virtualized rendering for the log list (react-virtual) to cap DOM nodes.

**3.1.2 Document pagination cap (`contexts/AppEntityDataContext.tsx`)**

- Introduce `MAX_DOCUMENTS_IN_MEMORY` (default 2000). When total exceeds cap,
  load the first page and fetch subsequent pages lazily on scroll/filter.
- Stop the current `while (offset < total)` loop at the cap.

**3.1.3 Polling lifecycle + EventSource teardown**

- Teardown `setInterval` and `EventSource` reconnect loops when the runtime
  health probe reports unreachable for N consecutive checks (suggest N=3).
- Surface a user-facing "backend disconnected" banner with a manual retry button
  instead of silent infinite retry.
- Clear `sessionDetailRequestsRef` entries on rejection, not only on resolve.

**3.1.4 In-flight request cache TTL**

- Add a 30s TTL to `sessionDetailRequestsRef` Map entries; GC on every insert.

### 3.2 Backend link-rebuild scoping

**3.2.1 Make deferred rebuild opt-in**

- Change default of `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` from `true` to
  `false`. Document the cold-start cost of leaving it on.

**3.2.2 Incremental link rebuild**

- Extend `_should_rebuild_links_after_full_sync()` to return a **scope** object
  (`full | entities_changed | none`) instead of a boolean.
- When only a small set of entities changed, rebuild only their inbound/outbound
  edges via `EntityLinksRepository.rebuild_for_entities(ids)`.
- Preserve full rebuild on `CCDASH_LINKING_LOGIC_VERSION` bump.

**3.2.3 Cache the full-workspace scan**

- Memoize `rglob` results per (root, pattern) tuple for the life of a sync run
  so sessions/docs/progress scans share one directory traversal.
- Persist a `filesystem_scan_manifest` table keyed on (path, mtime, size). Full
  scans compare manifest rather than re-walking when inode stats are unchanged
  since last scan and `CCDASH_STARTUP_SYNC_LIGHT_MODE=true`.

### 3.3 Query cache + workflow diagnostics

**3.3.1 Default TTL >= warmer interval**

- Change `CCDASH_QUERY_CACHE_TTL_SECONDS` default from 60 to 600 so the
  shipped warmer actually keeps entries warm. Document the override for fresh
  dashboards.

**3.3.2 Workflow diagnostics batching
(`backend/application/services/agent_queries/workflow_intelligence.py:157`)**

- Replace the per-workflow `get_workflow_registry_detail()` loop with a single
  batch query returning detail rows for all active workflows.
- Add a repository-level helper `fetch_workflow_details(ids: list[str])`.
- Keep `get_workflow_registry_detail(id)` for single-item queries.

### 3.4 Observability for each of the above

- Add counters: `ccdash_frontend_poll_teardown_total`,
  `ccdash_link_rebuild_scope{scope}`, `ccdash_filesystem_scan_cached_total`,
  `ccdash_workflow_detail_batch_rows`.
- Extend `/api/health` with a `runtimePerfDefaults` block reporting resolved
  values of the knobs in §3.3.1 and §3.2.1 so operators can verify the
  effective posture.

## 4. Rollout

1. Ship §3.1 (frontend) behind a `VITE_CCDASH_MEMORY_GUARD_ENABLED` flag
   default `true` for new tabs.
2. Ship §3.3.1 and §3.2.1 as default changes with a one-minor-version
   deprecation note in setup-user-guide.
3. Ship §3.2.2, §3.2.3 behind `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`
   default `false`, flip to `true` after one minor-version soak.
4. §3.3.2 is a straight replacement (no flag); covered by unit + integration
   tests.

## 5. Validation

- Vitest coverage for transcript windowing and polling teardown.
- Backend unit tests for scope resolver, manifest diff, batch query.
- Load-test harness: 60-min idle with worker running — memory must stay flat
  within ±50MB and cache hit rate must exceed 95%.
- Cold-start benchmark: `boot → GET /api/project-status p95 < 500ms` on a
  reference 50k-session workspace with the new defaults applied.

## 6. Open questions

- Should transcript truncation persist a pointer so users can fetch older rows
  on demand, or is "older messages hidden" with a manual refresh sufficient?
- Is `EntityLinksRepository.rebuild_for_entities` already available or does it
  need a new repository method?
- Do we want a soft-eviction policy on the agent query cache (LRU + max size)
  in addition to TTL, now that we are raising the default lifetime?
