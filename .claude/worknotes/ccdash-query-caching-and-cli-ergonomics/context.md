---
schema_version: 2
doc_type: context
type: context
prd: "ccdash-query-caching-and-cli-ergonomics"
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
title: "CCDash Query Caching and CLI Ergonomics - Development Context"
status: active
created: 2026-04-14
updated: 2026-04-14 (phase-2.5 and phase-3.5 progress files created; phase-2/5 expanded)
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
critical_notes_count: 3
implementation_decisions_count: 3
active_gotchas_count: 0
agent_contributors: ["python-backend-engineer"]
agents:
  - agent: "python-backend-engineer"
    note_count: 3
    last_contribution: "2026-04-14"
---

# CCDash Query Caching and CLI Ergonomics - Development Context

**Status**: Active Development
**Created**: 2026-04-14
**Last Updated**: 2026-04-14

> Shared worknotes for all agents working on this feature. Three targeted enhancements to CCDash CLI and MCP ergonomics.

---

## Feature Summary

Five targeted enhancements to CCDash CLI/MCP ergonomics (informed by Pass 2/3 CLI findings): (E1) configurable HTTP timeout via `--timeout` flag and `CCDASH_TIMEOUT` env var; (E2) TTL-based in-process query caching for four heavy endpoints with data-version fingerprint invalidation; (E2.5) top-level `name`, `status`, and `telemetry_available` alias fields on `FeatureForensicsDTO`; (E2.6) reconciliation of `feature_show.linked_sessions` with `feature sessions` endpoint; (E3) feature-list default limit raised to 200 with truncation hints and keyword filtering.

**Enhancement tags**: `cli-timeout` / `query-caching` / `dto-alias` / `linked-sessions-reconciliation` / `pagination-filtering`

---

## Quick Reference

**Agent Notes**: 3 notes from 1 agent
**Critical Items**: 3 resolved open questions (OQ-1, OQ-2, OQ-3)
**Last Contribution**: python-backend-engineer on 2026-04-14

---

## Open Questions — Resolved During Planning

| OQ | Question | Answer |
|----|----------|--------|
| OQ-1 | Does RuntimeClient use a shared httpx.Client or per-request clients? | Shared `httpx.Client` constructed once; timeout is passed at construction. |
| OQ-2 | Is `cachetools` already in `backend/requirements.txt`? | No. `cachetools>=5.3.0` must be added. `functools.lru_cache` rejected — no TTL support. |
| OQ-3 | Is FeatureForensicsDTO feature_status a union type or optional? | Straightforward `feature_status: str`. Alias fields are simple `str = ""`, no Optional needed. |

---

## Key Files Per Enhancement

### E1 — CLI Timeout

| File | Role |
|------|------|
| `packages/ccdash_cli/src/ccdash_cli/runtime/client.py` | `RuntimeClient` construction; timeout passed here |
| `packages/ccdash_cli/src/ccdash_cli/cli.py` (or equivalent root) | Typer root group; `--timeout` flag added here |
| `backend/config.py` | `CCDASH_TIMEOUT` env var read here (or CLI-side config) |

### E2 — Query Caching

| File | Role |
|------|------|
| `backend/application/services/agent_queries/cache.py` | New file: TTLCache instance, `@memoized_query`, fingerprint helper |
| `backend/requirements.txt` | `cachetools>=5.3.0` added |
| `backend/config.py` | `CCDASH_QUERY_CACHE_TTL_SECONDS`, `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` |
| `backend/observability/otel.py` | `agent_query.cache.hit` / `.miss` counters |
| `backend/routers/agent.py` | `?bypass_cache=true` query param |
| `backend/adapters/jobs/` | `cache_warming_job()` registration |
| `packages/ccdash_cli/src/ccdash_cli/` | `--no-cache` flag on relevant commands |

### E3 — DTO Alias Fields

| File | Role |
|------|------|
| `backend/application/services/agent_queries/models.py` | `FeatureForensicsDTO`: `name: str` and `status: str` added |
| `backend/application/services/agent_queries/feature_forensics.py` | Alias fields populated in `get_forensics()` |
| `packages/ccdash_cli/src/ccdash_cli/` | Formatters updated to use top-level fields |
| `backend/mcp/server.py` | MCP tool schema updated |
| `backend/tests/` | Parity regression test |

---

## Phase → Progress File Index

| Phase | Title | Progress File | Duration |
|-------|-------|--------------|----------|
| 1 | CLI Timeout Plumbing | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-1-progress.md` | 1–1.5 days |
| 2 | DTO Alias Fields + telemetry_available | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-2-progress.md` | 1.5–2 days |
| 2.5 | linked_sessions Reconciliation | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-2.5-progress.md` | 0.5–0.75 days |
| 3 | Cache Foundation | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-3-progress.md` | 2–2.5 days |
| 3.5 | Feature List Pagination & Filtering | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-3.5-progress.md` | 0.75–1 days |
| 4 | Background Materialization | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-4-progress.md` | 1–1.5 days |
| 5 | Testing, Observability, Docs, Skills | `.claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-5-progress.md` | 1.5–2 days |

**Total**: ~9–11 days focused work (expanded from original 5 phases ~10–12 days, but with more parallelization opportunity)

**Parallelization note**: Phases 1 and 2 are independent and can run concurrently. Phase 2.5 starts after Phase 2. Phase 3 and 3.5 are independent and can run in parallel. Phase 4 depends on Phase 3. Phase 5 depends on all prior phases.

---

## Dependencies and Risks

### Internal Dependencies (all in-place)

- `backend/application/services/agent_queries/` — transport-neutral layer; E2 and E3 implemented here
- `backend/adapters/jobs/` — background job adapter; E2 materialization job registered here
- `backend/observability/` — OTel setup; E2 cache counters emitted here
- `backend/config.py` — env-var config pattern; E1 and E2 config vars added here
- `packages/ccdash_cli/src/ccdash_cli/runtime/client.py` — E1 timeout wired here

### Key Risks (from PRD §9)

| Risk | Mitigation |
|------|-----------|
| Cache invalidation lag (fingerprint not atomic with sync) | Short TTL (60 s default) + bypass flag available |
| Fingerprint query adds overhead | Single lightweight `MAX(updated_at)` aggregate; negligible |
| Background job competes with sync for DB | 5 min cadence; can be disabled (`REFRESH_INTERVAL=0`) |
| DTO alias divergence from nested values | Regression test in every CI run |
| CLI `--timeout` breaks existing scripts | Default unchanged; flag and env are opt-in |

---

## Implementation Decisions

### 2026-04-14 - python-backend-engineer - cachetools over functools.lru_cache

**Decision**: Add `cachetools>=5.3.0` as a backend dependency for `TTLCache`.

**Rationale**: `functools.lru_cache` does not support TTL expiration, which is a hard requirement for cache invalidation. `cachetools` is lightweight, well-maintained, and permissive-licensed.

**Location**: `backend/requirements.txt`

**Impact**: New dependency; adds ~15 KB installed size. No other backend changes needed for the library itself.

---

### 2026-04-14 - python-backend-engineer - Alias fields in service layer, not Pydantic model

**Decision**: Populate `name` and `status` alias fields in `FeatureForensicsQueryService.get_forensics()` rather than using a Pydantic `@model_validator` or `Field(alias=...)`.

**Rationale**: Keeps model validation simple; makes the population site visible and grep-able. OQ-3 confirmed no union types that would require complex validator logic.

**Location**: `backend/application/services/agent_queries/feature_forensics.py`

**Impact**: Single population site; routers/CLI/MCP read the DTO as-is without any special handling.

---

### 2026-04-14 - python-backend-engineer - Timeout at RuntimeClient construction, not per-request

**Decision**: Resolved timeout value (flag > env > default) is passed to `RuntimeClient(timeout=...)` once at construction in the CLI context setup.

**Rationale**: OQ-1 confirmed RuntimeClient uses a shared `httpx.Client` constructed once. Per-request overrides would require API changes to all callers.

**Location**: `packages/ccdash_cli/src/ccdash_cli/runtime/client.py`

**Impact**: Clean single construction point; no scattered per-call overrides needed.

---

## Pass 2/3 Findings Folded In

**Source**: `/Users/miethe/Documents/Other/PKM/MeatyBrain/Blogs/Dev Stories/Bonus B2/notes/ccdash/ccdash-skill-findings.md`

**Key findings incorporated**:
1. **E2.5 extension** — Feature-show DTO extended with `telemetry_available` indicator to surface data gaps (Pass 2 #2).
2. **E2.6 new phase** — Reconciliation task for `feature show.linked_sessions` disagreement with `feature sessions` endpoint, plus hint nudging to authoritative endpoint (Pass 3 #1).
3. **E3 new phase** — Feature-list pagination default (50→200), truncation hint, and keyword filtering to avoid full-list client-side scans (Pass 2 #1, #3).
4. **Skill layer expansions** — Extend Phase 5 DOC tasks to include .claude/skills/ccdash/ SKILL.md gotchas section and new recipes for feature-retrospective and task-attribution patterns.
5. **Deferred** — Document body retrieval (`ccdash doc show`) deferred to future SPIKE/design spec phase (no blocker on current plan).

**Effort impact**: Original 28–34 pts → Revised 36–44 pts (two new sub-phases + skill expansion).

## References

**PRD**: `docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md` (updated 2026-04-14)
**Implementation Plan**: `docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md` (updated 2026-04-14)
**Related PRD**: `docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md`
**Findings source**: `/Users/miethe/Documents/Other/PKM/MeatyBrain/Blogs/Dev Stories/Bonus B2/notes/ccdash/ccdash-skill-findings.md` (Pass 2/3)
**Observability guide**: `docs/guides/telemetry-exporter-guide.md`
**Deferred items & findings policy**: `.claude/skills/planning/references/deferred-items-and-findings.md`
