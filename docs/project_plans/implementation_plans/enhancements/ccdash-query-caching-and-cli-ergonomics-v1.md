---
title: 'Implementation Plan: CCDash Query Caching and CLI Ergonomics'
schema_version: 2
doc_type: implementation_plan
status: completed
created: '2026-04-14'
updated: '2026-04-27'
feature_slug: ccdash-query-caching-and-cli-ergonomics
feature_version: v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: null
scope: Add CLI timeout configuration, in-process query caching with TTL, DTO alias
  fields with telemetry indicators, feature-list pagination/filtering, and linked_sessions
  reconciliation for five targeted enhancements to CCDash CLI/MCP ergonomics
effort_estimate: 36-44 story points (expanded from 28-34 with new findings)
architecture_summary: 'Six-phase plan: (1) CLI timeout plumbing in RuntimeClient;
  (2) DTO alias fields + telemetry_available on FeatureForensicsDTO; (2.5) linked_sessions
  reconciliation; (3) cache foundation with TTL memoization in agent_queries layer;
  (3.5) feature-list pagination/filtering; (4) background materialization via runtime
  job adapter; (5) comprehensive testing, observability, documentation, and skill
  updates'
related_documents:
- docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
references:
  user_docs: []
  context:
  - CLAUDE.md (env vars, CLI flags)
  specs: []
  related_prds:
  - docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
charter_ref: null
changelog_ref: null
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: null
contributors: []
priority: medium
risk_level: low
category: product-planning
tags:
- implementation
- planning
- cli
- caching
- ergonomics
- phases
milestone: null
commit_refs:
- 04eb8f6
pr_refs: []
files_affected:
- packages/ccdash_cli/src/ccdash_cli/runtime/client.py
- packages/ccdash_cli/src/ccdash_cli/runtime/state.py
- packages/ccdash_cli/src/ccdash_cli/main.py
- packages/ccdash_cli/src/ccdash_cli/commands/doctor.py
- packages/ccdash_cli/src/ccdash_cli/commands/target.py
- packages/ccdash_cli/src/ccdash_cli/commands/feature.py
- packages/ccdash_cli/tests/test_timeout.py
- packages/ccdash_cli/tests/test_commands.py
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/cache.py
- backend/application/services/agent_queries/feature_forensics.py
- backend/application/services/agent_queries/feature_list.py
- backend/application/services/agent_queries/project_status.py
- backend/application/services/agent_queries/workflow_diagnostics.py
- backend/application/services/agent_queries/reporting.py
- backend/application/services/agent_queries/shared.py
- backend/adapters/jobs/cache_warming.py
- backend/adapters/jobs/runtime.py
- backend/config.py
- backend/requirements.txt
- backend/observability/otel.py
- backend/repositories/features.py
- backend/routers/agent.py
- backend/routers/features.py
- backend/cli/
- backend/mcp/server.py
- backend/tests/test_agent_query_cache.py
- backend/tests/test_agent_query_cache_ttl.py
- backend/tests/test_agent_query_cache_invalidation.py
- backend/tests/test_agent_query_bypass_cache.py
- backend/tests/test_agent_query_memoized_query.py
- backend/tests/test_cache_warming_job.py
- backend/tests/test_features_list_filter.py
- backend/tests/test_feature_forensics_aliases.py
- backend/tests/test_feature_forensics_endpoint_agreement.py
- backend/tests/test_agent_queries_feature_forensics.py
- backend/tests/test_cli_commands.py
- CHANGELOG.md
- CLAUDE.md
- docs/guides/query-cache-tuning-guide.md
- docs/guides/cli-timeout-debugging.md
- .claude/skills/ccdash/SKILL.md
- .claude/skills/ccdash/recipes/task-attribution.md
- .claude/skills/ccdash/recipes/feature-retrospective.md
- .claude/skills/ccdash/recipes/unreachable-server.md
- .claude/worknotes/ccdash-query-caching-and-cli-ergonomics/feature-guide.md
---

# Implementation Plan: CCDash Query Caching and CLI Ergonomics

**Plan ID**: `IMPL-2026-04-14-ccdash-query-caching-and-cli-ergonomics`
**Date**: 2026-04-14
**Author**: Implementation Planner (Orchestrator)
**Related Documents**:
- **PRD**: `/docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md`
- **Agent-Queries Foundation**: `/docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md`

**Complexity**: Medium–High
**Total Estimated Effort**: 36–44 story points (6 phases, sequential with some parallelization; expanded from original 28–34 with Pass 2/3 findings)
**Target Timeline**: 2.5–3.5 weeks (assuming dedicated single-engineer track) or 1.5–2 weeks (2-person parallel)

---

## Executive Summary

This implementation plan delivers five targeted enhancements to CCDash's CLI and MCP ergonomics, informed by real-world usage findings from Pass 2 and Pass 3 CLI runs:

1. **CLI timeout configuration** — Operators can extend HTTP request timeouts via `--timeout` flag or `CCDASH_TIMEOUT` env var, eliminating opaque transport failures on heavy analytics queries.
2. **In-process query caching** — Four expensive agent-query endpoints are memoized with TTL-based invalidation, reducing perceived latency on warm runs to near-zero.
3. **DTO alias fields + telemetry indicators** — Feature-show DTO gains top-level `name`, `status`, and `telemetry_available` fields, removing nested-access boilerplate and helping callers reason about data gaps.
4. **Feature-list pagination and filtering** — Default limit raised to 200 (from 50), truncation hints added, keyword filtering added to avoid full-list client-side scans.
5. **Feature-show linked_sessions reconciliation** — Inline `linked_sessions` array reconciled to match `feature sessions <id>` endpoint; hint added to nudge callers toward authoritative endpoint.

All five enhancements are low-to-medium risk, well-scoped changes that require no new infrastructure and preserve full backward compatibility. The work follows MeatyPrompts layered architecture, concentrating config and caching at the service layer and repository filters so all transports (REST, CLI, MCP) benefit automatically.

---

## Implementation Strategy

### Architecture Sequence

1. **Phase 1: CLI timeout plumbing** — Configure timeout in `RuntimeClient`; expose in CLI commands and doctor output.
2. **Phase 2: DTO alias fields + telemetry_available** — Add top-level fields to FeatureForensicsDTO; update CLI/MCP formatters.
3. **Phase 2.5: Feature-show linked_sessions reconciliation** — Reconcile inline array with endpoint; add hint and regression test.
4. **Phase 3: Cache foundation** — Implement TTL-based memoization in agent_queries layer; wire to four endpoints.
5. **Phase 3.5: Feature-list pagination and keyword filtering** — Raise default limit to 200; add truncation hint; add keyword filter at repository layer.
6. **Phase 4: Background materialization** — Register refresh job in background job adapter for heavy rollups.
7. **Phase 5: Testing, observability, documentation, and skill updates** — Comprehensive tests, OTel instrumentation, CHANGELOG, CLAUDE.md updates, operator guides, skill spec expansion.

### Parallel Work Opportunities

- **Phase 1 and Phase 2 can overlap**: Both are isolated, no dependencies.
- **Phase 2.5 can start after Phase 2 completes**: Lightweight data-integrity task.
- **Phase 3 and Phase 4 sequential**: Phase 4 depends on cache layer (Phase 3) being in place.
- **Phase 3.5 independent**: Can run in parallel with Phase 3 or Phase 4.
- **Phase 5 runs after implementation phases**: Documentation, testing, and finalization.

### Critical Path

Phase 3 (Cache foundation) is on the critical path. Phases 1–2 can complete in parallel. Phase 2.5 and 3.5 can be parallelized around Phase 3. Phase 5 is unblocked after Phase 4 completes.

**Estimated timeline**: ~13–17 days of focused work (expanded from 10–12 due to new phases).

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

One deferred item from findings pass:

- **Document body retrieval**: Net-new `ccdash doc show <doc_id>` endpoint and/or flag on `feature documents` to retrieve full document body (not just title). Requires design spec on document storage format and output strategy. Estimated for post-Phase-5 SPIKE. No blocker on current plan.

All five enhancements scoped for this plan. All open questions (OQ-1, OQ-2, OQ-3) have been resolved during planning:

- **OQ-1 (resolved)**: `RuntimeClient` uses a shared `httpx.Client` at construction; timeout is passed at client creation, not per-request.
- **OQ-2 (resolved)**: `cachetools` is not in `backend/requirements.txt`; will add as dependency (cleaner than stdlib `functools.lru_cache` for TTL support).
- **OQ-3 (resolved)**: FeatureForensicsDTO has straightforward `feature_status: str` field; no complex union types. Alias fields will be simple string types.

### Quality Gate

All phases must complete with:
- [ ] No deferred items (N/A confirmed above)
- [ ] No in-flight findings captured (findings doc creation is lazy — only created on first real finding)

---

## Phase Breakdown

### Phase 1: CLI Timeout Plumbing

**Duration**: 1–1.5 days
**Dependencies**: None
**Assigned Subagent(s)**: python-backend-engineer

#### Overview

Resolve the timeout constant in `RuntimeClient`, wire it to CLI flag and env var, and surface the active value in CLI commands.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| CLI-001 | Explore CLI and RuntimeClient timeout setup | Inspect `packages/ccdash_cli/src/ccdash_cli/runtime/client.py`, identify current `_DEFAULT_TIMEOUT`, verify it's set at client construction. Identify where CLI root command is defined (likely in a main or cli entry point). | Findings documented inline in first implementation task; no blockers identified | 1 pt | python-backend-engineer | haiku | low | None |
| CLI-002 | Add `--timeout` global flag to CLI root | Add `--timeout` flag to the CLI root command group in Typer. Flag is optional; default is current hardcoded value (30 s). Flag value is float or int seconds. Store resolved value in a context variable or config singleton passed to RuntimeClient construction. Flag > env var > default precedence. | CLI accepts `ccdash --timeout 120 <command>` and `ccdash --timeout 90.5 <command>`; invalid values rejected with clear error | 2 pts | python-backend-engineer | sonnet | low | CLI-001 |
| CLI-003 | Add `CCDASH_TIMEOUT` env var fallback | Read `CCDASH_TIMEOUT` from environment (standard pattern: use `os.getenv()` in CLI startup or config module). If neither flag nor env set, use hardcoded default (30 s). Implement standard precedence: flag > env > default. | `CCDASH_TIMEOUT=120 ccdash feature report FEAT-123` uses 120 s; flag overrides env | 1 pt | python-backend-engineer | sonnet | low | CLI-002 |
| CLI-004 | Wire resolved timeout into RuntimeClient construction | Resolve final timeout value (flag or env or default) and pass it to `RuntimeClient(timeout=...)` at the point of client construction (likely in a CLI context setup or command group handler). | All CLI commands use resolved timeout; no per-request timeout overrides needed | 1 pt | python-backend-engineer | sonnet | low | CLI-003 |
| CLI-005 | Update `ccdash doctor` and `ccdash target check` output | Add a line to the doctor/check output table showing active timeout + its source (flag, env, default). Example: `Timeout: 30 s (default)` or `Timeout: 120 s (env: CCDASH_TIMEOUT)`. | Both commands display timeout and source; output is human-readable | 1 pt | python-backend-engineer | sonnet | low | CLI-004 |
| CLI-006 | Regression test: default behavior unchanged | Write pytest test covering: (1) no flag, no env → uses default 30 s; (2) flag set → uses flag; (3) env set, no flag → uses env; (4) both flag and env → flag wins. Verify backward compat (older scripts with no timeout flag still work). | All four scenarios pass; no breaking change to existing scripts | 1.5 pts | python-backend-engineer | sonnet | low | CLI-005 |

**Phase 1 Quality Gates:**
- [ ] CLI accepts `--timeout` flag with valid values
- [ ] `CCDASH_TIMEOUT` env var respected
- [ ] Flag > env > default precedence enforced
- [ ] `ccdash doctor` / `ccdash target check` display active timeout
- [ ] Backward-compat test passes (no timeout specified = default 30 s)
- [ ] No breaking changes to existing CLI invocations

---

### Phase 2: DTO Alias Fields and Telemetry_available Indicator

**Duration**: 1.5–2 days
**Dependencies**: None (can overlap with Phase 1)
**Assigned Subagent(s)**: python-backend-engineer, backend-architect

#### Overview

Add top-level `name`, `status`, and `telemetry_available` fields to FeatureForensicsDTO, computed in the service layer. The `telemetry_available` object indicates whether tasks, documents, and sessions telemetry is populated (non-empty), helping callers reason about data gaps. Update CLI and MCP formatters to use top-level fields.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| DTO-001 | Inspect FeatureForensicsDTO and identify field sources | Read `backend/application/services/agent_queries/models.py` and `backend/application/services/agent_queries/feature_forensics.py`. Identify canonical sources for name, status, tasks, documents, sessions arrays. Document schema. | Findings documented inline; exact field names and structure confirmed | 1 pt | python-backend-engineer | haiku | low | None |
| DTO-002 | Add top-level alias fields to FeatureForensicsDTO | Edit `backend/application/services/agent_queries/models.py`. Add fields: `name: str = ""`, `status: str = ""`, `telemetry_available: {tasks: bool, documents: bool, sessions: bool}`. Add docstring: "Alias fields mirror canonical values and indicate data completeness." | DTO updated; Pydantic validation passes; fields serialize in JSON | 1 pt | python-backend-engineer | sonnet | low | DTO-001 |
| DTO-003 | Populate alias fields in FeatureForensicsQueryService | Edit `backend/application/services/agent_queries/feature_forensics.py`. After constructing the DTO, set: `name`, `status` from feature row; `telemetry_available.tasks = len(dto.linked_tasks) > 0`, etc. | Returned DTO includes populated alias fields and `telemetry_available`; values correct | 1.5 pts | python-backend-engineer | sonnet | low | DTO-002 |
| DTO-004 | Update CLI formatters to use top-level fields | Search `packages/ccdash_cli/src/ccdash_cli/` for nested access patterns. Update to use top-level `name`, `status` instead. Update MCP tool schema in `backend/mcp/` as well. Include telemetry_available in feature detail output (optional: "Session telemetry: available" or similar). | CLI output unchanged (backward compat); nested-access boilerplate removed; telemetry indicator visible in output | 1 pt | python-backend-engineer | sonnet | low | DTO-003 |
| DTO-005 | Add pytest regression test: alias field parity | Write test asserting `dto.name == dto.<nested name path>`, `dto.status == dto.<nested status path>`, and `telemetry_available.sessions = (len(dto.linked_sessions) > 0)`. Run on every CI pass. | Test passes; regression guard in place; CI enforces consistency | 1 pt | python-backend-engineer | sonnet | low | DTO-004 |
| DTO-006 | Verify backward compatibility | Manual check: old CLI/agent code that drills into nested structure still works. No schema-level breaking changes (nested fields preserved). | Nested fields still accessible; no deserialization errors on old code | 0.5 pts | python-backend-engineer | haiku | low | DTO-005 |

**Phase 2 Quality Gates:**
- [ ] FeatureForensicsDTO updated with `name`, `status`, and `telemetry_available` fields
- [ ] Fields populated correctly in service layer
- [ ] CLI and MPC formatters use top-level fields
- [ ] Regression test asserts parity between alias and nested values
- [ ] Backward compatibility: old nested access still works
- [ ] No schema-level breaking changes

---

### Phase 2.5: Feature-Show linked_sessions Reconciliation

**Duration**: 0.5–0.75 days
**Dependencies**: Phase 2 complete (DTO changes)
**Assigned Subagent(s)**: python-backend-engineer, backend-architect

#### Overview

Investigate and reconcile the data disagreement between `feature_show.linked_sessions` inline array and the dedicated `feature sessions <id>` endpoint. Add hint to nudge callers toward authoritative endpoint.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| REC-001 | Investigate linked_sessions disagreement | Read Pass 3 findings: inline array returns `[]` while `feature sessions <id>` returns 70+ sessions for same feature. Inspect `backend/routers/agent.py` feature-show endpoint and `feature sessions` endpoint. Determine if inline array is intentionally filtered (e.g., only explicit sessions) or a bug. Document findings. | Root cause identified (filter vs bug); if filter, document rationale; if bug, proceed to REC-002 | 1 pt | backend-architect | sonnet | medium | None |
| REC-002 | Reconcile endpoints to agree | If bug: update inline array construction to match endpoint. If filter: preserve behavior but document explicitly (see REC-004). Either way, both endpoints must return identical `linked_sessions` arrays for the same feature after this task. | Both `feature_show.linked_sessions` and `feature sessions` return same data for same feature; test verifies parity | 1 pt | python-backend-engineer | sonnet | low | REC-001 |
| REC-003 | Add hint to feature-show response | Feature-show response DTO includes a one-line hint: "sessions: N available — run `ccdash feature sessions <id>` for details" (displayed in CLI or MCP output). This nudges operators toward the authoritative endpoint when inline array is empty or ambiguous. | CLI displays hint when `linked_sessions` present; hint is actionable (includes command); users understand the relationship | 0.5 pts | python-backend-engineer | sonnet | low | REC-002 |
| REC-004 | Eventual-consistency documentation | If the reconciliation investigation reveals session linkage is eventually-consistent (background job), add documentation to `docs/guides/` explaining timing. If synchronous, note that in the DTO docstring. Operator guide `cli-timeout-debugging.md` should mention this. | Documentation present and clear; operators understand if queries may be premature or eventual | 0.5 pts | documentation-writer | haiku | low | REC-001 |
| REC-005 | Add integration test: endpoints agree | Write pytest test that loads a feature with sessions, calls both `feature_show` and `feature sessions`, asserts `linked_sessions` arrays are equal. Test runs on every CI pass to prevent future divergence. | Test passes; regression guard in place; CI enforces endpoint agreement | 1 pt | python-backend-engineer | sonnet | low | REC-003 |

**Phase 2.5 Quality Gates:**
- [ ] Root cause of linked_sessions disagreement investigated
- [ ] Inline array reconciled to match endpoint (or documented as filtered subset)
- [ ] Hint added to feature-show DTO
- [ ] Integration test asserts endpoint agreement
- [ ] Eventual-consistency behavior documented (if applicable)
- [ ] All tests pass

---

### Phase 3: Cache Foundation

**Duration**: 2–2.5 days
**Dependencies**: Phase 1 and Phase 2 complete (independent, but logically before Phase 4)
**Assigned Subagent(s)**: backend-architect, python-backend-engineer

#### Overview

Implement TTL-based in-process memoization for four agent-query endpoints. Add data-version fingerprinting for auto-invalidation. Wire bypass-cache flag/param for debug.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| CACHE-001 | Verify four target endpoints and inspect async patterns | Identify the four endpoints from the PRD (project status rollup, feature forensics/AAR, workflow failures, feature list). Inspect their signatures in `backend/application/services/agent_queries/` and `backend/routers/agent.py`. Confirm all are async methods returning a DTO. Document pattern for cache wrapper. | Findings: endpoint names, signatures, and proposed cache key construction strategy | 1 pt | backend-architect | haiku | low | None |
| CACHE-002 | Add `cachetools` dependency to `backend/requirements.txt` | Edit `backend/requirements.txt`; add `cachetools>=5.3.0` (provides `TTLCache` with key-based TTL and size limits). Rationale: stdlib `functools.lru_cache` does not support TTL; cachetools is lightweight and well-maintained. | `requirements.txt` updated; cachetools available in venv after install | 0.5 pts | python-backend-engineer | sonnet | low | None |
| CACHE-003 | Create cache utility module and fingerprinting helper | Create `backend/application/services/agent_queries/cache.py`. Implement: (1) `get_data_version_fingerprint(context, ports, project_id)` — async function that queries max `updated_at` from sessions/features tables to generate a cache-invalidation fingerprint; (2) `compute_cache_key(endpoint_name, project_id, params, fingerprint)` — deterministic key from inputs + fingerprint. Include graceful degradation: if fingerprint query fails, log warning and proceed with live query (cache miss). | Functions work correctly; fingerprint reflects data recency; cache key is stable | 2 pts | backend-architect | sonnet | medium | CACHE-002 |
| CACHE-004 | Implement cache wrapper and memoization decorator | Create cache instance (`cachetools.TTLCache`) at module level in `cache.py`. Implement `@memoized_query` async decorator (or wrapper function) that: (1) checks cache key; (2) if hit, return cached result; (3) if miss, await original coroutine, cache result, return; (4) increment OTel counters (hit/miss). Decorator is agnostic to endpoint; wraps any async function returning a DTO. | Decorator works on async functions; caches results with correct TTL; OTel instrumentation fires | 2 pts | backend-architect | sonnet | medium | CACHE-003 |
| CACHE-005 | Add cache config env vars to `backend/config.py` | Add: `CCDASH_QUERY_CACHE_TTL_SECONDS` (default 60, int); `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` (default 300, int, for background job use). Both read from env using existing `_env_int()` pattern. Document defaults in code comments. | Config module exposes new vars; defaults sensible | 0.5 pts | python-backend-engineer | sonnet | low | None |
| CACHE-006 | Apply cache decorator to four target endpoints | Edit each of the four service functions (project status, feature forensics, AAR, workflow diagnostics) to wrap with the memoization decorator. Update their signatures if needed (pass config at construction or read from module). Ensure fingerprint is fresh before cache lookup. | All four endpoints memoized; wrapped functions work identically to originals; cache hits/misses observable | 2 pts | python-backend-engineer | sonnet | medium | CACHE-004, CACHE-005 |
| CACHE-007 | Implement cache bypass via query param (REST) and flag (CLI) | REST: add `?bypass_cache=true` query param support in `backend/routers/agent.py`. When set, skip cache lookup, increment `agent_query.cache.miss` counter. CLI: add `--no-cache` flag to relevant CLI commands (`ccdash feature report`, `ccdash report aar`, etc.) in `packages/ccdash_cli/src/ccdash_cli/`. Wire flag to REST query param. | REST and CLI both respect bypass flag; cache hit counter shows miss on forced refresh | 1.5 pts | python-backend-engineer | sonnet | low | CACHE-006 |
| CACHE-008 | Instrument cache hit/miss OTel counters | Edit `backend/observability/otel.py` to add counters: `agent_query.cache.hit` and `agent_query.cache.miss`. Increment in the cache wrapper (CACHE-004). Optionally add cache size gauge. Ensure no performance overhead on hot path. | Counters incremented correctly; OTel dashboard shows hit/miss ratio; no measurable latency impact | 1.5 pts | backend-architect | sonnet | medium | CACHE-004 |
| CACHE-009 | Integration test: cache invalidation on sync write | Write test that: (1) calls endpoint (cache miss, caches result); (2) calls again immediately (cache hit); (3) writes new data to sessions/features (triggers sync); (4) calls endpoint again (fingerprint updated, cache miss, fresh result). Verify fingerprint-based invalidation. | Test passes; cache invalidation works correctly on data update | 1.5 pts | python-backend-engineer | sonnet | medium | CACHE-006 |
| CACHE-010 | Integration test: TTL expiry | Write test that: (1) calls endpoint (cache miss); (2) calls again within TTL (cache hit); (3) waits for TTL to expire; (4) calls again (cache miss, new result). Use short TTL (e.g., 2 s) for test. | Test passes; TTL-based expiry works correctly | 1 pt | python-backend-engineer | sonnet | low | CACHE-006 |
| CACHE-011 | Graceful degradation: fingerprint failure fallback | Write test that simulates fingerprint query failure (DB error). Verify: (1) error is caught and logged; (2) live query still executes; (3) no exception bubbles to caller. | Test passes; graceful fallback on fingerprint error | 1 pt | python-backend-engineer | sonnet | low | CACHE-004 |

**Phase 3 Quality Gates:**
- [ ] Cache utility module complete and tested
- [ ] Decorator wraps all four target endpoints
- [ ] OTel counters emit correctly
- [ ] Cache invalidation works on data update
- [ ] TTL expiry tested
- [ ] Graceful degradation on fingerprint failure
- [ ] `bypass_cache` flag/param works (REST + CLI)
- [ ] Config env vars respected
- [ ] All cache-related tests pass

---

### Phase 3.5: Feature List Pagination and Keyword Filtering

**Duration**: 0.75–1 days
**Dependencies**: Phase 3 (independent, but can run in parallel)
**Assigned Subagent(s)**: python-backend-engineer, backend-architect

#### Overview

Raise the default limit on `feature list` from 50 to 200, add truncation indicators, and implement keyword filtering at the repository layer to avoid full-list client-side scans.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| PAGINATE-001 | Update feature list endpoint default limit | Edit `backend/routers/agent.py` (or `backend/application/services/agent_queries/feature_list.py`) where default limit is set. Change from 50 to 200. Verify no performance regression (test on local target with 200 features). | Default limit is 200; `ccdash feature list` returns 200 results instead of 50 | 0.5 pts | python-backend-engineer | sonnet | low | None |
| PAGINATE-002 | Add `truncated` and `total` fields to feature-list response DTO | Edit `backend/application/services/agent_queries/models.py` (feature list response model). Add fields: `truncated: bool` (true if results exceed limit), `total: int` (total count of all features matching filter). These are computed by comparing `len(results)` to limit and fetching total count. | DTO updated; fields serialize in JSON; values correct | 1 pt | python-backend-engineer | sonnet | low | PAGINATE-001 |
| PAGINATE-003 | Add CLI truncation hint display | Edit `packages/ccdash_cli/src/ccdash_cli/` feature-list formatter. When `truncated: true`, display: "Showing 200 of {total} features. Use `--limit {total}` to see all." (or similar, user-friendly). | CLI output shows truncation hint when appropriate; users understand there are more features available | 0.5 pts | python-backend-engineer | sonnet | low | PAGINATE-002 |
| FILTER-001 | Add `--q <keyword>` CLI flag and `?q=keyword` REST param | Edit CLI command definitions (`packages/ccdash_cli/src/ccdash_cli/`) to add `--q` or `--name-contains` flag to `feature list` command. Edit `backend/routers/agent.py` to accept `?q=keyword` query param. Pass keyword to the service layer. | CLI accepts `ccdash feature list --q "repo"` and REST accepts `?q=repo`; parameter wired through | 0.75 pts | python-backend-engineer | sonnet | low | PAGINATE-001 |
| FILTER-002 | Implement keyword filter in repository layer | Edit `backend/repositories/features.py` (or feature query method) to accept an optional `keyword` parameter. Filter using case-insensitive substring match on feature name and slug: `WHERE name ILIKE '%keyword%' OR slug ILIKE '%keyword%'`. Filter applied at DB query layer, not post-fetch. | Repository method filters correctly; DB query uses `ILIKE` or equivalent case-insensitive match; test verifies filtering | 1 pt | python-backend-engineer | sonnet | low | FILTER-001 |
| FILTER-003 | Integration test: keyword filter effectiveness | Write test: call `feature list --q "repo"` and verify only features with "repo" in name/slug are returned. Test with multiple keywords on test data. Verify filter works case-insensitively. | Test passes; keyword filter returns expected features; case-insensitivity works | 0.75 pts | python-backend-engineer | sonnet | low | FILTER-002 |
| PAGINATE-004 | Integration test: pagination and truncation hint | Write test: (1) call `feature list` (default 200), verify `truncated` and `total` fields set correctly; (2) with 213 features, `truncated: true, total: 213`; (3) verify CLI formatter displays hint. | Test passes; truncation logic correct; hint displayed when expected | 0.75 pts | python-backend-engineer | sonnet | low | PAGINATE-003 |

**Phase 3.5 Quality Gates:**
- [ ] Feature-list default limit is 200
- [ ] `truncated` and `total` fields in response DTO
- [ ] CLI truncation hint displays correctly
- [ ] Keyword filter works via CLI (`--q`) and REST (`?q=`)
- [ ] Filter applied at repository layer (not client-side)
- [ ] Filter is case-insensitive substring match
- [ ] Integration tests for pagination and filtering pass

---

### Phase 4: Background Materialization

**Duration**: 1–1.5 days
**Dependencies**: Phase 3 complete
**Assigned Subagent(s)**: python-backend-engineer

#### Overview

Register a background job that refreshes the cache for the two heaviest rollups (project status and feature list aggregates) at a configurable cadence.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| BG-001 | Inspect background job adapter in `backend/adapters/jobs/` | Read `backend/adapters/jobs/` to understand registration pattern, scheduling, error handling. Identify how jobs are registered and run by the worker runtime. | Findings: job registration pattern, scheduling options, error handling strategy | 0.5 pts | python-backend-engineer | haiku | low | None |
| BG-002 | Create cache materialization job | Create a new async job function (e.g., `cache_warming_job()` or `refresh_agent_queries_cache()`) in `backend/adapters/jobs/`. Job loops over project IDs and calls the two heaviest endpoints (project status, feature list) to pre-warm the cache. Interval configurable via `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`. If interval is 0, job is disabled. Job runs at low priority; errors logged but do not block HTTP request path. | Job function complete, handles project enumeration, calls endpoints, logs results | 1.5 pts | python-backend-engineer | sonnet | medium | BG-001, CACHE-006 |
| BG-003 | Register job in the background job adapter | Wire the cache materialization job into `backend/adapters/jobs/` registration (likely in `__init__.py` or a jobs registry). Ensure job respects the interval config and can be disabled (interval = 0). | Job is registered and runs at configured interval; can be disabled via env var | 1 pt | python-backend-engineer | sonnet | low | BG-002 |
| BG-004 | Test: background job runs without blocking HTTP | Write integration test: (1) start HTTP server + worker with cache job enabled; (2) make HTTP request while job is running; (3) verify HTTP response is fast (not blocked by job). (4) Verify job completed and cache was refreshed. | Test passes; HTTP request latency unaffected by background job | 1 pt | python-backend-engineer | sonnet | low | BG-002, BG-003 |
| BG-005 | Test: job disablement via interval=0 | Write test: set `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=0`; verify job does not run; cache still works (on-demand). | Test passes; interval=0 disables job | 0.5 pts | python-backend-engineer | sonnet | low | BG-003 |

**Phase 4 Quality Gates:**
- [ ] Cache materialization job created and registered
- [ ] Job runs at configurable interval (default 300 s)
- [ ] Job can be disabled (interval=0)
- [ ] HTTP requests not blocked by background job
- [ ] Job errors logged but do not crash worker
- [ ] All background job tests pass

---

### Phase 5: Testing, Observability, and Documentation Finalization

**Duration**: 1.5–2 days
**Dependencies**: Phases 1–4 complete
**Assigned Subagent(s)**: python-backend-engineer, documentation-writer, changelog-generator, ai-artifacts-engineer

#### Overview

Comprehensive unit/integration tests across all three enhancements, OTel instrumentation summary, CHANGELOG entry, CLAUDE.md updates, operator guides, and project-level skill updates.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| TEST-001 | CLI timeout: comprehensive unit/integration tests | Write pytest tests in `backend/tests/` covering: (1) timeout precedence (flag > env > default); (2) invalid timeout values rejected; (3) timeout passed to RuntimeClient; (4) doctor/target-check display active timeout. | All tests pass; CLI timeout fully validated | 1.5 pts | python-backend-engineer | sonnet | low | CLI-006 |
| TEST-002 | DTO alias fields: comprehensive tests | Write pytest tests covering: (1) FeatureForensicsDTO deserialization includes `name`, `status`, `telemetry_available`; (2) alias fields populated correctly from service; (3) parity test (alias == nested); (4) backward compat (nested access still works); (5) telemetry_available semantics correct. | All tests pass; DTO alias fields fully validated | 1.5 pts | python-backend-engineer | sonnet | low | DTO-006 |
| TEST-002.5 | linked_sessions reconciliation: integration test | Write pytest test asserting `feature_show.linked_sessions` == `feature_sessions` endpoint result for same feature. Test runs on every CI pass. Also test the hint is displayed. | Test passes; endpoints agree; hint visible in output | 1 pt | python-backend-engineer | sonnet | low | REC-005 |
| TEST-003 | Cache: comprehensive unit + integration suite | Write pytest tests covering: (1) cache hit/miss on repeated calls; (2) TTL expiry; (3) fingerprint invalidation on data update; (4) bypass flag forces miss; (5) graceful degradation on fingerprint failure; (6) cache size limits. | All tests pass; cache fully validated; >80% coverage of cache module | 2 pts | python-backend-engineer | sonnet | medium | CACHE-011 |
| TEST-003.5 | Feature-list pagination and filtering: integration suite | Write pytest tests covering: (1) default limit is 200; (2) `truncated` and `total` fields correct; (3) keyword filter works (`--q` / `?q=`); (4) filter is case-insensitive substring match; (5) truncation hint displays correctly. | All tests pass; pagination and filtering fully validated | 1.5 pts | python-backend-engineer | sonnet | low | PAGINATE-004, FILTER-003 |
| TEST-004 | Background job: comprehensive suite | Write pytest tests covering: (1) job runs at configured interval; (2) job does not block HTTP; (3) job disablement (interval=0); (4) job errors handled gracefully; (5) cache is warm after job run. | All tests pass; background job fully validated | 1.5 pts | python-backend-engineer | sonnet | medium | BG-005 |
| TEST-005 | End-to-end CLI test: timeout on long query | Write an e2e test (or manual smoke test with documented procedure) covering: CLI invokes slow endpoint with extended timeout; query completes without timeout error. Document procedure for operators to reproduce. | E2E test passes; procedure documented; manual smoke test reproducible | 1 pt | python-backend-engineer | sonnet | low | CLI-005 |
| TEST-006 | All tests pass in CI/CD pipeline | Run full test suite (`backend/tests/`); ensure no regressions. Type-check (`mypy`) and lint (`ruff`) clean for all modified files. | CI/CD green; >80% code coverage on new modules; all test groups pass | 1 pt | python-backend-engineer | sonnet | low | TEST-001 through TEST-005 |
| DOC-001 | Update CHANGELOG.md | Add entry under "Enhancements" with bullets: (1) CLI timeout configurable via `--timeout` flag or `CCDASH_TIMEOUT` env var; (2) Query caching for four endpoints reduces latency on warm runs; (3) FeatureForensicsDTO alias fields + `telemetry_available` indicator; (4) Feature list defaults to 200 results with truncation hint and keyword filtering; (5) Feature-show `linked_sessions` reconciliation. Follow Keep A Changelog format. | CHANGELOG entry present and well-formatted; all five enhancements documented | 0.75 pts | changelog-generator | haiku | low | TEST-006 |
| DOC-002 | Update CLAUDE.md with new env vars, flags, and endpoints | Add section under "Commands & Configuration": (1) CLI flag: `--timeout SECONDS`; (2) Env vars: `CCDASH_TIMEOUT`, `CCDASH_QUERY_CACHE_TTL_SECONDS`, `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`; (3) CLI flags: `--no-cache`, `--q <keyword>`. Keep ≤15 lines; one-liners. | CLAUDE.md updated; pointers only (no verbose descriptions) | 0.5 pts | documentation-writer | haiku | low | TEST-006 |
| DOC-003 | Create operator guide: query cache tuning | Create `docs/guides/query-cache-tuning-guide.md` covering: (1) What queries are cached (4 endpoints); (2) TTL defaults and how to override; (3) Background materialization cadence; (4) How to disable cache (`--no-cache` / `bypass_cache=true`); (5) Observability: monitoring cache hit/miss via OTel; (6) Troubleshooting slow queries. Keep <500 words; focus on operations. | Guide created and published; examples include common use cases | 1 pt | documentation-writer | haiku | low | TEST-006 |
| DOC-004 | Create operator guide: CLI timeout debugging | Create `docs/guides/cli-timeout-debugging.md` covering: (1) What causes timeouts; (2) How to set `--timeout` or `CCDASH_TIMEOUT`; (3) How to diagnose via `ccdash doctor`; (4) Session linkage eventual-consistency note (if applicable); (5) When to escalate. Keep <400 words; actionable. | Guide created and published; troubleshooting flow clear | 0.5 pts | documentation-writer | haiku | low | TEST-006 |
| DOC-005 | Expand `.claude/skills/ccdash/` skill spec and recipes | Update SKILL.md: (1) Add "Known Gotchas" section covering default limits (50→200), dual linked_sessions fields, keyword search brittleness, timeout behavior; (2) Add new recipe `recipes/feature-retrospective.md` (feature list → filter → feature show → feature sessions pattern); (3) Add new recipe `recipes/task-attribution.md` (using linked_tasks[].owner for agent-role attribution); (4) Update `recipes/unreachable-server.md` to distinguish transport failures from endpoint-specific timeouts. Expand scope of existing DOC tasks; add skill context. | SKILL.md gotchas section added; two new recipes documented; CLI spec updated with new flags; skill context expanded | 1.5 pts | ai-artifacts-engineer | sonnet | medium | TEST-006 |
| DOC-006 | Update implementation plan frontmatter | Set `status: in-progress` → `completed` (or leave as `draft` if not yet fully merged). Populate `commit_refs` with commit SHAs from each phase, `pr_refs` with PR numbers, `files_affected` with all modified files, `updated` with final date. | Plan frontmatter complete per lifecycle spec | 0.5 pts | documentation-writer | haiku | low | DOC-001 through DOC-005 |
| DOC-007 | Finalize deferred items and findings doc | Check `deferred_items_spec_refs`: populate with placeholder design-spec path if "Document body retrieval" is deferred (or mark as resolved if implemented). Check `findings_doc_ref`: confirm null or update if findings doc was created during implementation. Update deferred items section in plan if needed. | Frontmatter fields correct per deferred-items-and-findings policy | 0.5 pts | documentation-writer | haiku | low | DOC-006 |
| DOC-008 | Feature guide: create `.claude/worknotes/[feature-slug]/feature-guide.md` | Create feature guide with sections: (1) What Was Built (4-5 sentences covering all five enhancements); (2) Architecture Overview (file/layer touches, phases); (3) How to Test (CLI + integration test instructions for each enhancement); (4) Test Coverage Summary (phases 2/2.5/3/3.5/4, coverage); (5) Known Limitations. Keep total <250 lines. | Guide created, concise, and actionable; all five enhancements summarized | 1.5 pts | documentation-writer | haiku | low | DOC-007 |

**Phase 5 Quality Gates:**
- [ ] All unit/integration tests pass (>80% coverage on new code)
- [ ] Type-check and lint clean on all modified files
- [ ] CHANGELOG entry added with all five enhancements documented
- [ ] CLAUDE.md updated with new CLI flags, env vars, and endpoints
- [ ] Operator guides created (cache tuning, timeout debugging)
- [ ] CLI skill spec updated with new commands and examples
- [ ] Skill SKILL.md expanded with gotchas section and new recipes
- [ ] Plan frontmatter populated (commit_refs, pr_refs, files_affected, status, updated)
- [ ] Deferred items finalized in plan (doc-retrieval placeholder or resolved)
- [ ] Findings doc confirmed null or finalized
- [ ] Feature guide created with all five enhancements summarized

---

## Wrap-Up: Feature Guide & PR

**Triggered**: After all phases complete and all quality gates pass.

### Feature Guide

Delegate to `documentation-writer` (haiku, low effort) to create `.claude/worknotes/ccdash-query-caching-and-cli-ergonomics/feature-guide.md` (task DOC-008 above).

**Frontmatter**:
```yaml
---
doc_type: feature_guide
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
created: 2026-04-14
---
```

**Required sections**: (1) What Was Built; (2) Architecture Overview; (3) How to Test; (4) Test Coverage Summary; (5) Known Limitations.

### Open PR

After feature guide is committed:

```bash
gh pr create \
  --title "feat(cli, cache): configurable timeout, query caching, DTO aliases" \
  --body "$(cat <<'EOF'
## Summary
- CLI timeout now configurable via `--timeout` flag and `CCDASH_TIMEOUT` env var
- In-process query caching with TTL-based invalidation for 4 agent-query endpoints
- FeatureForensicsDTO gains top-level `name` and `status` alias fields for simpler access

## Test plan
- [ ] All unit + integration tests pass (>80% coverage)
- [ ] CLI timeout functional test: extended timeout on slow query
- [ ] Cache hit/miss, TTL expiry, invalidation tests all pass
- [ ] Background materialization job runs without blocking HTTP
- [ ] Backward compatibility verified (existing nested DTO access still works)

🤖 Generated with Claude Code
EOF
)"
```

---

## Model & Effort Assignment

All tasks include Model and Effort columns:

### Model Guidance

- **`sonnet`** (Claude 3.5 Sonnet): Default for implementation, testing, architectural work
- **`haiku`** (Claude 3.5 Haiku): Documentation, exploration, simple configuration
- **External models**: Not used in this plan (no UI, web research, or image generation needed)

### Effort Levels

- **`low`**: Straightforward, well-defined, minimal reasoning
- **`medium`**: Moderate complexity, some design/trade-off analysis
- **`high`**: Not used in this plan (all tasks are medium or below)
- **`adaptive`** (default): Model applies adaptive thinking based on task complexity

All tasks default to `adaptive` effort unless specifically marked `low` or `medium`.

---

## Risk Mitigation

### Technical Risks

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| Cache key collision / staleness | Medium | Low | Deterministic key includes project ID + fingerprint; fingerprint refreshed on every call; short TTL (60 s default) bounds staleness |
| Fingerprint query overhead exceeds cache benefit | Low | Low | Fingerprint is single lightweight aggregate query; profile before exposing config; can be disabled via TTL=0 |
| Background job competes with sync for DB | Low | Low | Job runs on 5 min cadence (low frequency); can be disabled; runs at low priority |
| OTel instrumentation overhead | Low | Low | Counters are O(1) increments; no blocking calls; no measurable latency impact |
| Timeout plumbing breaks existing scripts | Low | Low | Default timeout unchanged; env var and flag are optional; full backward compatibility |
| DTO alias divergence from nested values | Medium | Low | Regression test asserts equality on every CI run; docstring makes intent explicit |

### Schedule Risks

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| Scope creep from new requirements | Medium | Low | Fixed scope; PRD is finalized; deferred items identified upfront |
| Unforeseen integration complexity | Medium | Medium | Phase 1–2 overlap reduces critical path; Phase 3–4 sequential but well-scoped; integration tests catch issues early |
| Dependency availability (cachetools) | Low | Very Low | cachetools is stable, well-maintained, permissive license; already in ecosystem |

---

## Resource Requirements

### Team Composition

- **Python Backend Engineer**: 1 FTE (all phases, primary implementation)
- **Backend Architect**: 0.25 FTE (Phase 3 cache design, Phase 4 job integration, Phase 5 review)
- **Documentation Writer**: 0.25 FTE (Phase 5 CHANGELOG, guides, context updates)
- **AI-Artifacts Engineer**: 0.1 FTE (Phase 5 skill spec update)

### Skill Requirements

- Python (async/await, FastAPI, Pydantic)
- Caching patterns and TTL-based invalidation
- OpenTelemetry instrumentation
- CLI development (Typer)
- SQLite/PostgreSQL querying
- Git, pytest, CI/CD

### Infrastructure

- No new infrastructure required
- Uses existing background job adapter and OTel setup
- Single-process in-memory cache (no distributed cache)

---

## Success Metrics

### Delivery Metrics

- [ ] On-time delivery (2–3 weeks target)
- [ ] Code coverage >80% on new modules (cache, CLI timeout)
- [ ] Zero P0/P1 bugs in first week post-launch
- [ ] All acceptance criteria from PRD met

### Business Metrics

- [ ] Zero CLI transport failures on standard analytics queries (post-implementation)
- [ ] Cache hit rate ≥80% on warm runs (observable via OTel)
- [ ] No regression in CLI backward compatibility

### Technical Metrics

- [ ] Cache lookup < 1 ms overhead (measured locally)
- [ ] Background job does not block HTTP requests (latency p99 unaffected)
- [ ] All tests pass in CI/CD
- [ ] Type-check and lint clean

---

## Communication Plan

- **Daily standups** (if concurrent work): Progress on Phase 1–2 parallelization, blockers
- **Phase gates**: Seal Phase 1–2 before starting Phase 3; seal Phase 3 before Phase 4
- **Documentation**: Inline code comments for cache key construction, fingerprinting strategy
- **Operator communication** (post-launch): Blog post or internal doc on cache tuning and timeout configuration

---

## Post-Implementation

- **Performance dashboards**: Monitor cache hit ratio via OTel (target ≥80%)
- **Error tracking**: Watch CLI timeout failures (should drop to zero)
- **Operator feedback**: Gather feedback on timeout UX and cache effectiveness
- **Iteration**: Tune TTL and refresh interval based on actual usage patterns
- **Tech debt**: Consider distributed cache if single-process cache becomes a bottleneck (future, out of scope)

---

**Progress Tracking:**

See `.claude/progress/ccdash-query-caching-and-cli-ergonomics/all-phases-progress.md` (to be created during phase 1 kickoff)

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-04-14
