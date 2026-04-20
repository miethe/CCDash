---
schema_version: 2
doc_type: implementation_plan
title: "CCDash Runtime Performance Hardening v1 - Implementation Plan"
status: draft
created: 2026-04-20
updated: 2026-04-20
feature_slug: runtime-performance-hardening
feature_version: "v1"
prd_ref: /docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
plan_ref: null
scope: "Frontend memory hardening, link rebuild dedup, cached query cold windows, and performance observability"
effort_estimate: "38 story points"
architecture_summary: "Frontend polling/transcript lifecycle hardening, backend link-rebuild scope resolution with incremental rebuild support, query cache TTL alignment with warmer cycle, batch workflow diagnostics query, and Prometheus observability instrumentation."
related_documents:
  - docs/project_plans/design-specs/runtime-performance-hardening-v1.md
  - docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
  - docs/project_plans/meta_plans/performance-and-reliability-v1.md
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
  - docs/guides/query-cache-tuning-guide.md
references:
  user_docs:
    - docs/guides/operator-setup-user-guide.md
  context: []
  specs: []
  related_prds: []
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
owner: nick
contributors: []
priority: high
risk_level: medium
category: infrastructure
tags: [performance, memory, reliability, sync, cache, frontend, backend]
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Implementation Plan: CCDash Runtime Performance Hardening v1

**Plan ID**: `IMPL-2026-04-20-runtime-performance-hardening`
**Date**: 2026-04-20
**Complexity**: Medium | **Total Estimated Effort**: 38 story points | **Target Timeline**: 3-4 weeks

## Executive Summary

This implementation plan addresses three operator-visible performance and reliability problems not resolved by concurrent infrastructure initiatives: frontend tab memory growth (2GB+), redundant startup link rebuilds, and cached query cold windows combined with N+1 workflow fetches. The plan delivers memory-hardened polling/transcript lifecycle teardown, incremental link-rebuild scoping, TTL/warmer alignment, and observability counters. Delivered changes are gated behind feature flags for safe rollout. Success metrics: tab memory flat within ±50MB over 60-min idle, ≤1 full rebuild per boot, ≥95% cache hit rate, single-batch workflow detail query.

---

## Implementation Strategy

### Architecture Sequence

Following CCDash layered architecture (Database → Repository → Service → API → UI → Testing → Documentation → Deployment):

1. **Frontend Memory Hardening** — Polling lifecycle teardown, transcript windowing, document pagination cap, in-flight request cache TTL
2. **Link Rebuild Dedup & Throttling** — Scope resolution, incremental rebuild dispatch, filesystem scan manifest caching
3. **Cached Query Alignment** — TTL default raise, batch workflow diagnostics query
4. **Observability & Telemetry** — Four new Prometheus counters, `/api/health` runtimePerfDefaults block
5. **Testing & Validation** — Vitest + pytest coverage, load-test harness, cold-start benchmark
6. **Documentation Finalization** — Operator guide updates, CHANGELOG entry, feature flag docs

### Parallel Work Opportunities

- **Phase 1 & 2 in parallel**: Frontend and backend changes are independent; can start simultaneously
- **Phase 3 alongside Phases 1-2**: Query cache changes do not block polling hardening or link rebuild work
- **Phase 4 alongside Phases 1-3**: Observability instrumentation can be wired in as each phase completes
- **Phase 5 batched with Phases 1-4**: Testing harness can be prepared once the feature is stabilized

### Critical Path

1. Phase 1 (Frontend) — 5-6 days
2. Phase 2 (Link Rebuild) — 4-5 days (parallel with Phase 1)
3. Phase 3 (Cached Query) — 2-3 days
4. Phase 4 (Observability) — 1-2 days
5. Phase 5 (Testing & Validation) — 3-4 days
6. Phase 6 (Documentation) — 1-2 days

**Critical Chain**: Phases 1-3 must complete before comprehensive testing (Phase 5) can begin. Documentation (Phase 6) seals after testing succeeds.

### Phase Summary

At-a-glance orchestration index for all phases. Every phase includes point estimate, target subagents, model designation, and dependencies.

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 1 | Frontend Memory Hardening | 10 pts | ui-engineer-enhanced, frontend-developer, react-performance-optimizer | sonnet | Polling teardown, transcript windowing, doc pagination cap, in-flight request GC |
| 2 | Link Rebuild Dedup & Throttling | 9 pts | python-backend-engineer, data-layer-expert, backend-architect | sonnet | Scope resolution, incremental rebuild, rglob memoization, manifest caching |
| 3 | Cached Query Alignment | 6 pts | python-backend-engineer, data-layer-expert | sonnet | TTL default, batch workflow query, repository helper |
| 4 | Observability & Telemetry | 4 pts | python-backend-engineer, backend-architect | sonnet | Prometheus counters, /api/health runtimePerfDefaults |
| 5 | Testing & Validation | 7 pts | testing specialist, python-backend-engineer, frontend-developer, react-performance-optimizer | sonnet | Vitest, pytest, load-test harness, cold-start benchmark |
| 6 | Documentation Finalization | 2 pts | changelog-generator, documentation-writer, ai-artifacts-engineer | haiku (sonnet for changelogs) | Operator guide, CHANGELOG, feature flag docs, plan finalization |
| **Total** | — | **38 pts** | — | — | Delivery target: 3-4 weeks |

**Model column conventions:**
- Default model: `sonnet` for implementation, `haiku` for documentation
- No external models required for this feature
- Effort level: `adaptive` for all tasks (standard depth)

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

Three open questions from the PRD are intentionally deferred pending further research or soak after v1 delivery:

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| OQ-1 | research | Transcript truncation UX — on-demand fetch vs "older hidden" | Operator feedback after v1 soak (1+ minor versions) | docs/project_plans/design-specs/transcript-fetch-on-demand-v1.md |
| OQ-2 | tech-debt | EntityLinksRepository.rebuild_for_entities existence — audit repo at impl start | Implementation phase PR review; method added if missing | N/A — implementation contingent, not post-delivery |
| OQ-3 | enhancement | Soft-eviction LRU policy on agent query cache — defer if TTL raise proves sufficient | Monitor cache metrics post-release; revisit if hit rate < 90% | docs/project_plans/design-specs/agent-query-cache-lru-v1.md |

**Note on OQ-2**: This is a contingent discovery, not a deferred item. The implementation plan for Phase 2 includes an audit task to determine if the repository method exists; if not, it will be added as part of Phase 2 delivery.

#### Design-Spec Authoring (DOC-006)

For OQ-1 and OQ-3 (deferred research items), Phase 6 includes a DOC-006 task to author design specs at the target paths. OQ-2 is not a post-delivery deferred item and therefore has no spec task.

### In-Flight Findings

Findings doc is **not pre-created**. If agents discover plan/reality mismatches or schema gaps during execution, create `.claude/findings/runtime-performance-hardening-findings.md` on first discovery and update `findings_doc_ref` here.

### Quality Gate

Phase 6 cannot be sealed until:
- OQ-1 and OQ-3 design-specs are authored (or explicitly marked "N/A" with rationale if findings alter scope)
- `deferred_items_spec_refs` frontmatter is updated with all authored spec paths
- If `findings_doc_ref` is populated: findings doc status is set to `accepted`

---

## Phase Breakdown

### Phase 1: Frontend Memory Hardening

**Duration**: 5-6 days
**Dependencies**: None
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer, react-performance-optimizer

**Key Objectives**:
- Implement transcript ring-buffer cap (5000 rows) with truncation marker
- Add virtualized rendering to session log list
- Introduce document pagination cap (2000 docs) with lazy loading
- Tear down polling/EventSource on sustained backend unreachability
- Clear in-flight request cache entries on rejection and add 30s TTL + GC
- Gate all changes behind `VITE_CCDASH_MEMORY_GUARD_ENABLED` feature flag (default `true`)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| FE-101 | Transcript ring-buffer cap | Cap `session.logs` to 5000 rows; emit `transcriptTruncated` marker on drop | Ring buffer drops oldest rows; marker rendered in UI showing "older messages hidden" | 3 pts | react-performance-optimizer, ui-engineer-enhanced | sonnet | None |
| FE-102 | Session log virtualization | Add react-virtual to log list rendering | DOM node count constant; virtualization reduces memory footprint of large logs | 2 pts | frontend-developer, ui-engineer-enhanced | sonnet | FE-101 |
| FE-103 | Document pagination cap | Introduce MAX_DOCUMENTS_IN_MEMORY (2000); lazy-load beyond cap | Loop stops at 2000; subsequent pages fetch on scroll/filter; no unbounded pagination | 3 pts | frontend-developer | sonnet | None |
| FE-104 | Polling lifecycle teardown | Teardown `setInterval` and `EventSource` after N=3 consecutive unreachable checks | Polling stopped after 3 failures; "backend disconnected" banner shown; manual retry button works | 2 pts | frontend-developer | sonnet | None |
| FE-105 | In-flight request GC | Clear entries on rejection; add 30s TTL to sessionDetailRequestsRef; GC on insert | Map size bounded; no growth after network failures; memory does not leak | 2 pts | react-performance-optimizer | sonnet | None |
| FE-106 | Memory guard feature flag | Gate all changes behind VITE_CCDASH_MEMORY_GUARD_ENABLED (default true) | Flag disabled → original behavior; flag enabled → all memory hardening active | 1 pt | frontend-developer | sonnet | FE-101, FE-102, FE-103, FE-104, FE-105 |
| FE-107 | Load-test harness setup (frontend) | Create test harness for 60-min idle + worker running memory profile | Harness measures tab memory at 1-min intervals; exports JSON for analysis | 2 pts | react-performance-optimizer, frontend-developer | sonnet | FE-101 through FE-106 |

**Phase 1 Quality Gates:**
- [ ] FE-101: Transcript truncation marker appears in UI; log array capped at 5000 rows
- [ ] FE-102: Virtual list rendering reduces DOM nodes; no memory spike from large logs
- [ ] FE-103: Document array capped at 2000; lazy-load verified on scroll
- [ ] FE-104: Polling stops after 3 unreachable checks; banner visible and persistent
- [ ] FE-105: `sessionDetailRequestsRef` entries cleared on error; no memory growth after network failures
- [ ] FE-106: Feature flag disables all memory hardening without breaking existing behavior
- [ ] FE-107: Load-test harness runs successfully; baseline metrics captured

---

### Phase 2: Link Rebuild Dedup & Throttling

**Duration**: 4-5 days
**Dependencies**: None (parallel with Phase 1)
**Assigned Subagent(s)**: python-backend-engineer, data-layer-expert, backend-architect

**Key Objectives**:
- Change `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` default from `true` to `false`
- Extend `_should_rebuild_links_after_full_sync()` to return scope object (`full | entities_changed | none`)
- Implement or verify `EntityLinksRepository.rebuild_for_entities(ids)` method
- Add incremental rebuild dispatch when scope is `entities_changed`
- Memoize `rglob` results per sync-run lifetime
- Add `filesystem_scan_manifest` table and manifest-based scan skip (light mode)
- Gate incremental rebuild behind `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (default `false`)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| BE-201 | Audit EntityLinksRepository | Determine if `rebuild_for_entities(ids)` method exists; document findings | Method exists with signature `rebuild_for_entities(ids: list[str])` OR task BE-203 required | 1 pt | data-layer-expert | sonnet | None |
| BE-202 | Default deferred-rebuild to false | Change `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` env var default from `true` to `false` | Default changed in `backend/config.py`; boot with default config triggers at most 1 full rebuild | 1 pt | python-backend-engineer | sonnet | None |
| BE-203 | Implement rebuild_for_entities | If BE-201 finds method missing: add `rebuild_for_entities(ids)` to EntityLinksRepository; if exists: skip this task | Method added to repository (or skip if exists); method accepts list of entity IDs; rebuilds inbound/outbound edges | 2 pts | data-layer-expert | sonnet | BE-201 |
| BE-204 | Extend scope resolver | Refactor `_should_rebuild_links_after_full_sync()` to return scope object instead of boolean | Method signature changed to return `Literal['full', 'entities_changed', 'none']`; logic determines scope based on sync deltas | 2 pts | backend-architect | sonnet | None |
| BE-205 | Incremental rebuild dispatch | Wire scope resolver output into rebuild dispatch; call `rebuild_for_entities()` when scope is `entities_changed` | Scope `entities_changed` triggers partial rebuild; scope `full` triggers full rebuild; scope `none` skips rebuild | 2 pts | python-backend-engineer | sonnet | BE-204, BE-203 |
| BE-206 | Gate incremental rebuild | Gate incremental rebuild dispatch behind `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (default `false`) | Flag disabled → scope resolver returns `full` always; flag enabled → scope resolver returns actual scope | 1 pt | python-backend-engineer | sonnet | BE-205 |
| BE-207 | rglob memoization | Memoize `rglob(root, pattern)` results for the life of a sync run | Per-sync memoization dict prevents redundant directory traversals; sessions/docs/progress scans share one walk | 2 pts | python-backend-engineer | sonnet | None |
| BE-208 | Filesystem scan manifest table | Add `filesystem_scan_manifest` migration (path, mtime, size); implement manifest diff logic | Migration creates table successfully on SQLite and PostgreSQL; diff logic detects unchanged paths | 2 pts | data-layer-expert | sonnet | None |
| BE-209 | Light-mode scan skip | Implement manifest-based scan skip when `CCDASH_STARTUP_SYNC_LIGHT_MODE=true` and inode stats unchanged | Light mode enabled → skip re-walk if manifest match; disabled or manifest miss → full walk | 1 pt | python-backend-engineer | sonnet | BE-208 |

**Phase 2 Quality Gates:**
- [ ] BE-201: Method existence audit documented; decision point cleared
- [ ] BE-202: Default changed; verified via `backend/config.py`
- [ ] BE-203: Repository method added (if needed) with correct signature
- [ ] BE-204: Scope resolver logic sound; returns correct scope in test cases
- [ ] BE-205: Incremental dispatch wired; partial rebuild verified on small entity changes
- [ ] BE-206: Feature flag gates incremental logic correctly
- [ ] BE-207: Memoization reduces directory traversal count to 1 per sync run
- [ ] BE-208: Migration runs cleanly; manifest table populated
- [ ] BE-209: Light mode enabled → scan skipped on unchanged manifests

---

### Phase 3: Cached Query Alignment & Batch Workflow Diagnostics

**Duration**: 2-3 days
**Dependencies**: Phases 1-2 complete (but can start in parallel)
**Assigned Subagent(s)**: python-backend-engineer, data-layer-expert

**Key Objectives**:
- Change `CCDASH_QUERY_CACHE_TTL_SECONDS` default from 60s to 600s (aligns with 300s warmer interval)
- Add `fetch_workflow_details(ids: list[str])` batch repository helper
- Replace N+1 loop in `workflow_intelligence.py:157` with single batch call
- Retain single-item `get_workflow_registry_detail(id)` for backward compatibility

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| BE-301 | Raise TTL default | Change `CCDASH_QUERY_CACHE_TTL_SECONDS` default from 60 to 600 in `backend/config.py` | Default updated; warmer cycle (300s) now completes 2 full TTL lifetimes; cache hit rate improves | 0.5 pts | python-backend-engineer | sonnet | None |
| BE-302 | Workflow batch repository helper | Add `fetch_workflow_details(ids: list[str])` method to repository; returns list of detail dicts | Method signature accepts list of workflow IDs; returns detail rows in single query; no N+1 loop | 2 pts | data-layer-expert | sonnet | None |
| BE-303 | Replace N+1 loop with batch | Refactor `workflow_intelligence.py:157` loop to call `fetch_workflow_details()` once | N+1 loop removed; single batch query replaces loop; output structure matches original for downstream compatibility | 2 pts | python-backend-engineer | sonnet | BE-302 |
| BE-304 | Retain single-item query | Keep `get_workflow_registry_detail(id)` method in repository for backward compatibility | Single-item method unchanged; internal delegation to `fetch_workflow_details([id])` allowed | 1 pt | python-backend-engineer | sonnet | BE-302 |

**Phase 3 Quality Gates:**
- [ ] BE-301: TTL default updated; verified in config.py
- [ ] BE-302: Batch helper method added; accepts list and returns list of details
- [ ] BE-303: N+1 loop replaced; query count verified (1 batch query vs. N single queries)
- [ ] BE-304: Single-item method still available; no breaking changes

---

### Phase 4: Observability & Telemetry

**Duration**: 1-2 days
**Dependencies**: Phases 1-3 complete
**Assigned Subagent(s)**: python-backend-engineer, backend-architect

**Key Objectives**:
- Register four new Prometheus counters: `ccdash_frontend_poll_teardown_total`, `ccdash_link_rebuild_scope{scope}`, `ccdash_filesystem_scan_cached_total`, `ccdash_workflow_detail_batch_rows`
- Add `runtimePerfDefaults` block to `/api/health` response reporting resolved values of TTL, deferred-rebuild, and scan-light-mode knobs
- Wire counters into each phase's instrumentation points

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| OBS-401 | Register Prometheus counters | Define and register four new counters in `backend/observability/` | All four counters appear in `/metrics` output; labels correct (e.g., scope=full, scope=entities_changed) | 1.5 pts | backend-architect | sonnet | None |
| OBS-402 | Wire teardown counter | Increment `ccdash_frontend_poll_teardown_total` when polling stops in Phase 1 | Counter incremented after 3 unreachable checks; verifiable in `/metrics` | 0.5 pts | python-backend-engineer | sonnet | OBS-401, FE-104 |
| OBS-403 | Wire rebuild-scope counter | Increment `ccdash_link_rebuild_scope{scope}` with correct label in Phase 2 dispatch | Counter incremented for each rebuild with scope=full or entities_changed or none | 0.5 pts | python-backend-engineer | sonnet | OBS-401, BE-205 |
| OBS-404 | Wire scan-cache counter | Increment `ccdash_filesystem_scan_cached_total` when light-mode scan skipped (Phase 2) | Counter incremented when manifest match skips walk | 0.5 pts | python-backend-engineer | sonnet | OBS-401, BE-209 |
| OBS-405 | Wire batch-rows counter | Increment `ccdash_workflow_detail_batch_rows` with batch size in Phase 3 | Counter incremented with row count on each batch call | 0.5 pts | python-backend-engineer | sonnet | OBS-401, BE-303 |
| OBS-406 | Add health runtimePerfDefaults block | Extend `/api/health` response with `runtimePerfDefaults` block reporting TTL, deferred-rebuild, light-mode knobs | Block present; resolves env vars correctly; shows effective values (after overrides) | 1 pt | backend-architect | sonnet | None |

**Phase 4 Quality Gates:**
- [ ] OBS-401: All four counters registered; `/metrics` response valid
- [ ] OBS-402: Teardown counter increments on polling stop
- [ ] OBS-403: Rebuild-scope counter increments with correct label
- [ ] OBS-404: Scan-cache counter increments on light-mode skips
- [ ] OBS-405: Batch-rows counter increments with batch size
- [ ] OBS-406: Health endpoint includes runtimePerfDefaults with accurate values

---

### Phase 5: Testing & Validation

**Duration**: 3-4 days
**Dependencies**: Phases 1-4 complete
**Assigned Subagent(s)**: testing specialist, python-backend-engineer, frontend-developer, react-performance-optimizer

**Key Objectives**:
- Write Vitest coverage for transcript windowing, document pagination, polling teardown, in-flight request GC
- Write pytest coverage for scope resolver, manifest diff, batch workflow query
- Execute load-test harness: 60-min idle + worker running → verify tab memory flat within ±50MB
- Execute cold-start benchmark: boot → GET /api/project-status → verify p95 < 500ms on 50k-session workspace
- Verify cache hit rate ≥ 95% during steady-state operation

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| TEST-501 | Vitest: transcript windowing | Test FE-101 ring-buffer cap and truncation marker | Tests verify cap enforcement, marker emission, no memory unbounding | 1 pt | frontend-developer | sonnet | FE-101 |
| TEST-502 | Vitest: document pagination | Test FE-103 pagination cap and lazy-load | Tests verify cap at 2000, lazy-load on scroll | 1 pt | frontend-developer | sonnet | FE-103 |
| TEST-503 | Vitest: polling teardown | Test FE-104 polling stop after N=3 unreachable checks | Tests verify teardown; banner rendered; retry works | 1 pt | frontend-developer | sonnet | FE-104 |
| TEST-504 | Vitest: in-flight request GC | Test FE-105 rejection clearing and 30s TTL | Tests verify rejection clearing, TTL expiry, no unbounded growth | 1 pt | react-performance-optimizer | sonnet | FE-105 |
| TEST-505 | Pytest: scope resolver | Test BE-204 scope resolution logic on various sync deltas | Tests verify correct scope (full, entities_changed, none) on small/large entity changes | 1 pt | python-backend-engineer | sonnet | BE-204 |
| TEST-506 | Pytest: manifest diff | Test BE-208 manifest-based scan skip on unchanged/changed paths | Tests verify manifest match skips walk; mismatch triggers walk | 1 pt | data-layer-expert | sonnet | BE-208 |
| TEST-507 | Pytest: batch workflow query | Test BE-303 batch query returns correct detail rows; replaces N+1 | Tests verify single query with N workflows returns N rows; output matches original | 1 pt | python-backend-engineer | sonnet | BE-303 |
| TEST-508 | Load-test harness execution | Run 60-min idle + worker running; measure memory at 1-min intervals | Tab memory starts at baseline; after 60 min, memory within ±50MB of baseline | 1 pt | react-performance-optimizer | sonnet | FE-101 through FE-107, OBS-402 |
| TEST-509 | Cold-start benchmark | Boot → GET /api/project-status on 50k-session workspace; measure p95 latency | p95 latency < 500ms with new defaults (TTL=600s, deferred_rebuild=false) | 1 pt | python-backend-engineer | sonnet | BE-301, BE-202 |
| TEST-510 | Cache hit rate validation | Steady-state operation load test; measure cache hit rate | Hit rate ≥ 95% during 10-min steady-state period (queries at warmer interval 300s, TTL now 600s) | 0.5 pts | python-backend-engineer | sonnet | BE-301, OBS-405 |

**Phase 5 Quality Gates:**
- [ ] TEST-501 through TEST-504: All Vitest coverage >80% for FE changes
- [ ] TEST-505 through TEST-507: All pytest coverage for BE changes; tests passing
- [ ] TEST-508: Load test succeeds; memory flat within ±50MB
- [ ] TEST-509: Cold-start benchmark p95 < 500ms
- [ ] TEST-510: Cache hit rate ≥ 95% in steady-state

---

### Phase 6: Documentation Finalization

**Duration**: 1-2 days
**Dependencies**: Phases 1-5 complete, testing gates passed
**Assigned Subagent(s)**: changelog-generator, documentation-writer, ai-artifacts-engineer

**Key Objectives**:
- Update operator documentation for changed defaults with deprecation note
- Document new feature flags in `backend/config.py` and setup-user-guide
- Author design specs for deferred items (OQ-1, OQ-3)
- Add CHANGELOG `[Unreleased]` entry
- Update plan frontmatter with final status and committed refs

#### Required Evaluation Areas

| Area | Inclusion Rationale | Delegation Target |
|------|-------------------|-------------------|
| CHANGELOG.md | User-facing changes: new feature flags, changed defaults (TTL, deferred-rebuild), observable behavior changes (polling teardown, "backend disconnected" banner) | changelog-generator agent |
| README.md | No README changes (feature is internal performance hardening, not user-facing capability) | Skip |
| User/dev docs | New feature flags and changed defaults warrant operator documentation update | documentation-writer agent |
| Context files | Changes affect operator deployment guidance and monitoring; update CLAUDE.md pointer + key-context | documentation-writer agent |
| Project-level custom skills | No custom skill domain affected (no new CLI commands, capability changes are internal) | Skip |

#### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------------|
| DOC-601 | Update CHANGELOG | Add entry for user-facing changes under `[Unreleased]`. Cover new feature flags, default changes, observable improvements (polling teardown, memory stability). Follow Keep A Changelog format and `.claude/specs/changelog-spec.md` categorization rules. | Entry exists under `[Unreleased]`; includes feature flags, defaults, improvements; categorized correctly | 0.5 pts | changelog-generator | haiku | All phases 1-5 |
| DOC-602 | Update operator docs | Update `docs/guides/operator-setup-user-guide.md` with documentation of `VITE_CCDASH_MEMORY_GUARD_ENABLED`, `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`, `CCDASH_STARTUP_SYNC_LIGHT_MODE` flags. Add one-minor-version deprecation note for default changes (TTL 60s→600s, deferred-rebuild true→false). | Docs cover all three new flags; deprecation note present; examples show env-var usage | 0.5 pts | documentation-writer | haiku | All phases 1-5 |
| DOC-603 | Update backend config docstrings | Update `backend/config.py` docstrings for CCDASH_STARTUP_DEFERRED_REBUILD_LINKS, CCDASH_QUERY_CACHE_TTL_SECONDS, and new flags with defaults and rationale | Config docstrings updated; new flags documented; defaults explained | 0.5 pts | documentation-writer | haiku | All phases 1-5 |
| DOC-604 | Author design spec for OQ-1 | Author design_spec at `docs/project_plans/design-specs/transcript-fetch-on-demand-v1.md` for on-demand transcript fetch capability. Set maturity=shaping (direction known, needs detailed design). Set prd_ref to parent PRD. Include open_questions and explored_alternatives. | Spec file exists; frontmatter complete; problem statement clear; shaping maturity | 0.5 pts | documentation-writer | sonnet | All phases 1-5 |
| DOC-605 | Author design spec for OQ-3 | Author design_spec at `docs/project_plans/design-specs/agent-query-cache-lru-v1.md` for soft-eviction LRU policy on agent query cache. Set maturity=shaping. Set prd_ref to parent PRD. Include open_questions on LRU eviction policy options. | Spec file exists; frontmatter complete; problem statement clear; shaping maturity | 0.5 pts | documentation-writer | sonnet | All phases 1-5 |
| DOC-606 | Update context files | Add one-liner pointers to CLAUDE.md (root level) for new feature flags and changed defaults. Create or update key-context file for runtime performance monitoring (if needed). | CLAUDE.md updated with ≤3-line pointers per addition; key-context accurate | 0.5 pts | documentation-writer | haiku | All phases 1-5 |
| DOC-607 | Finalize plan frontmatter | Set status=completed; populate commit_refs, files_affected, updated date. Append OQ-1 and OQ-3 spec paths to deferred_items_spec_refs. | Frontmatter complete; all fields populated per lifecycle spec | 0.5 pts | documentation-writer | haiku | DOC-601 through DOC-606 |

**Phase 6 Quality Gates:**
- [ ] DOC-601: CHANGELOG `[Unreleased]` entry present and correctly categorized
- [ ] DOC-602: Operator guide updated with flag documentation and deprecation notes
- [ ] DOC-603: Config.py docstrings updated for all new/changed defaults
- [ ] DOC-604 & DOC-605: Design specs authored for OQ-1 and OQ-3 at target paths
- [ ] DOC-606: Context files updated with progressive disclosure pointers
- [ ] DOC-607: Plan frontmatter complete; `deferred_items_spec_refs` populated with spec paths

---

## Risk Mitigation

### Technical Risks

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| Transcript truncation loses diagnostic data operators need for debugging | Medium | Medium | Expose truncation marker prominently in UI; document 5000-row default as configurable in future; create OQ-1 design spec for on-demand fetch |
| Incremental link rebuild produces stale/incorrect edges if scope resolver has a bug | High | Low | Default flag to `false`; validate graph correctness against fixture workspace before flipping default; comprehensive pytest coverage on scope logic |
| Raising TTL to 600s causes stale data if warmer fails silently | Medium | Low | Surface `runtimePerfDefaults` in `/api/health` so operators can detect misconfiguration; document override path in operator guide |
| rglob memoization uses stale results if filesystem changes mid-sync | Low | Low | Scope memoization to single sync-run lifetime; do not share across runs; document assumption in code comments |
| react-virtual conflicts with React 19 environment | Medium | Low | Verify compatibility in feature branch before merging; fallback is CSS-overflow with DOM cap (FE-102 task can be deferred if needed) |
| Polling teardown hides connectivity issues from operators who don't notice banner | Medium | Medium | Banner is persistent and prominent; manual retry always available; log teardown event to OTEL counters (OBS-402); include in operator docs |

### Schedule Risks

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| Scope creep from concurrent infrastructure work | Medium | Medium | This plan is explicitly scoped to performance hardening only; db-caching-layer, data-platform-modularization, deployment-runtime-modularization are separate |
| Test harness takes longer than estimated | Low | Low | Load-test harness can be simplified to single data-point measurement (end-of-60-min) rather than 1-min intervals if needed |
| Fixture workspace unavailable for benchmarking | Medium | Medium | Use existing test workspace or generate synthetic 50k-session dataset if real workspace unavailable |

---

## Resource Requirements

### Team Composition

- **Frontend Engineer**: 1 FTE (Phase 1), part-time (testing in Phase 5) — ui-engineer-enhanced, frontend-developer
- **Backend Engineer**: 1.5 FTE (Phases 2-3), part-time (Phase 4, testing Phase 5) — python-backend-engineer, data-layer-expert
- **Backend Architect**: Part-time (Phase 2 scope resolver, Phase 4 observability) — backend-architect
- **Performance Specialist**: Part-time (Phase 1 react optimization, Phase 5 load-test execution) — react-performance-optimizer
- **Testing Specialist**: Part-time (Phase 5 test harness, framework) — testing specialist
- **Documentation Specialist**: Part-time (Phase 6) — changelog-generator, documentation-writer

### Skill Requirements

- **Frontend**: React 19, TypeScript, Vitest, memory profiling, virtualization libraries (react-virtual)
- **Backend**: Python, FastAPI, SQLAlchemy, pytest, Prometheus instrumentation, query optimization
- **DevOps/Observability**: OpenTelemetry, Prometheus counters, environment configuration
- **Data**: SQLite and PostgreSQL migration testing, query optimization, indexing

---

## Success Metrics

### Delivery Metrics

- On-time delivery (3-4 weeks target) with all phase gates passing
- Code coverage >80% for all modified files (Vitest + pytest)
- Zero P0/P1 bugs at release (Phase 5 comprehensive testing)
- All four feature flags gate changes correctly (QA validation)

### Business Metrics

- **Frontend memory**: Tab memory flat within ±50MB over 60-min idle with worker running (baseline: 2GB+ growth observed)
- **Cache hit rate**: ≥95% during steady-state operation (baseline: <80% with 60s TTL < 300s warmer)
- **Cold-start latency**: `GET /api/project-status` p95 < 500ms on 50k-session workspace with new defaults
- **Link rebuilds per boot**: ≤1 (baseline: 2 with old defaults)
- **Workflow detail queries**: 1 batch query per diagnostics call (baseline: N per-workflow queries)

### Technical Metrics

- 100% of new Prometheus counters emitting correctly
- `/api/health` runtimePerfDefaults block accurate on all platforms (SQLite + PostgreSQL)
- Feature flags (`VITE_CCDASH_MEMORY_GUARD_ENABLED`, `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`, `CCDASH_STARTUP_SYNC_LIGHT_MODE`) enable/disable changes cleanly
- Operator documentation covers all new flags and default changes with deprecation notes

---

## Communication Plan

### Ongoing

- **Daily**: Brief slack updates on phase completion (blocking issues if any)
- **Phase-end**: Phase quality gate validation documented; sign-off before next phase
- **Weekly**: Stakeholder sync on overall progress toward 3-4 week delivery target

### Stakeholders

- **Project Owner** (Nick Miethe): Daily visibility on phase progress; final sign-off on acceptance criteria
- **Frontend Team**: Visibility on Phase 1 + 5 progress; early testing feedback
- **Backend Team**: Visibility on Phases 2-4; scope resolver validation; query optimization sign-off
- **Operations**: Early review of operator documentation changes (Phase 6)

### Escalation

- **Technical blocker** (e.g., react-virtual incompatibility): Escalate to `ui-engineer-enhanced` immediately; identify fallback path
- **Schedule risk** (phase over estimate by >20%): Escalate to project owner; adjust timeline or defer non-critical tasks
- **Scope ambiguity** (e.g., OQ-2 repository method not found): Flag immediately; do not block Phase 2; add contingent task

---

## Wrap-Up: Feature Guide & PR

**Triggered**: After Phase 5 testing gates pass and Phase 6 documentation is sealed. This is the post-implementation close-out step.

### Step 1 — Feature Guide

After final phase quality gate sign-off, create `.claude/worknotes/runtime-performance-hardening/feature-guide.md` with:

**Required sections** (total <200 lines):
1. **What Was Built** — 2-4 sentences: frontend memory hardening, link rebuild dedup, query cache alignment, observability counters
2. **Architecture Overview** — key files: `components/SessionInspector.tsx`, `services/live/sessionTranscriptLive.ts`, `contexts/AppEntityDataContext.tsx`, `contexts/AppRuntimeContext.tsx`, `backend/db/sync_engine.py`, `backend/application/services/agent_queries/workflow_intelligence.py`
3. **How to Test** — load-test harness command, cold-start benchmark command, feature flag toggles
4. **Test Coverage Summary** — Vitest >80%, pytest >80%, load-test + benchmark passing
5. **Known Limitations** — OQ-1 (transcript fetch on-demand deferred), OQ-3 (LRU policy deferred)

**Audience**: Developer/operator reference; future supplement to CHANGELOG for users who want more detail.

### Step 2 — Open PR

After feature guide is committed, open pull request with:

```bash
gh pr create \
  --title "perf: harden CCDash runtime (memory, link rebuild, query cache)" \
  --body "$(cat <<'EOF'
## Summary
- Frontend memory hardening: polling teardown, transcript windowing, doc pagination cap, in-flight request GC
- Link rebuild dedup: scope resolution, incremental rebuild, filesystem manifest caching
- Query cache alignment: TTL raised to 600s, workflow batch diagnostics replacing N+1 loop
- Observability: four new Prometheus counters, /api/health runtimePerfDefaults block

## Feature Guide
.claude/worknotes/runtime-performance-hardening/feature-guide.md

## Test Plan
- [x] Vitest coverage for transcript windowing, polling teardown, document pagination, in-flight request GC
- [x] Pytest coverage for scope resolver, manifest diff, batch workflow query
- [x] Load-test harness: 60-min idle + worker running, memory flat within ±50MB
- [x] Cold-start benchmark: GET /api/project-status p95 < 500ms on 50k-session workspace
- [x] Cache hit rate ≥ 95% in steady-state operation

🤖 Generated with Claude Code
EOF
)"
```

PR title should summarize the three major outcomes (memory, rebuild, query cache); PR body bullets match Feature Guide sections.

---

## Appendices & References

### Related Documentation

- **Design spec**: `docs/project_plans/design-specs/runtime-performance-hardening-v1.md`
- **Meta-plan**: `docs/project_plans/meta_plans/performance-and-reliability-v1.md`
- **DB caching layer plan**: `docs/project_plans/implementation_plans/db-caching-layer-v1.md`
- **Deployment runtime modularization plan**: `docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md`
- **Data platform modularization plan**: `docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md`
- **Query cache tuning guide**: `docs/guides/query-cache-tuning-guide.md`
- **Operator setup guide**: `docs/guides/operator-setup-user-guide.md`

### Key Files Affected

**Frontend**:
- `components/SessionInspector.tsx` — FE-101, FE-102, FE-107
- `services/live/sessionTranscriptLive.ts` — FE-101
- `contexts/AppEntityDataContext.tsx` — FE-103
- `contexts/AppRuntimeContext.tsx` — FE-104
- `services/apiClient.ts` — FE-105

**Backend**:
- `backend/config.py` — BE-202, BE-206, BE-301, BE-309, DOC-603
- `backend/db/sync_engine.py` — BE-202, BE-204, BE-205, BE-207, BE-208, BE-209
- `backend/db/migrations.py` — BE-208
- `backend/db/repositories/links.py` (or equivalent) — BE-201, BE-203
- `backend/application/services/agent_queries/workflow_intelligence.py` — BE-302, BE-303, BE-304
- `backend/observability/otel.py` — OBS-401 through OBS-406
- `backend/routers/health.py` (or main.py) — OBS-406

**Documentation**:
- `docs/guides/operator-setup-user-guide.md` — DOC-602
- `CHANGELOG.md` — DOC-601
- `docs/project_plans/design-specs/transcript-fetch-on-demand-v1.md` — DOC-604
- `docs/project_plans/design-specs/agent-query-cache-lru-v1.md` — DOC-605

---

**Progress Tracking:**

See `.claude/progress/runtime-performance-hardening/all-phases-progress.md`

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-04-20
