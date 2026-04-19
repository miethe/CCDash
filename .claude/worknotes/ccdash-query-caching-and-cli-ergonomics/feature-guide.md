---
doc_type: feature_guide
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
created: 2026-04-15
---

# CCDash Query Caching & CLI Ergonomics — Feature Guide

## 1. What Was Built

Five integrated enhancements shipped across phases 1–4:

1. **CLI timeout configuration**: `--timeout` flag + `CCDASH_TIMEOUT` env var (default 30s), displayed in `ccdash doctor` output for visibility and debugging.

2. **In-process TTL query cache**: Four agent-query endpoints (project-status, feature-forensics, workflow-diagnostics, reports/aar) backed by configurable TTL caching (default 60s) with fingerprint-based invalidation, `--no-cache` bypass flag, and OTel hit/miss counters.

3. **FeatureForensicsDTO ergonomics**: Top-level `name` and `status` alias fields for backward compatibility, `telemetry_available: bool` flag, and `sessions_note` eventual-consistency hint to operators.

4. **Feature-list pagination + keyword filter**: Default limit increased to 200 (from 50), response includes `truncated`/`total` fields, `--q TEXT` case-insensitive substring filter on name/title, CLI truncation hint when results overflow.

5. **linked_sessions reconciliation**: `feature_show.linked_sessions` now matches the `feature_sessions` endpoint, with CI regression guard and CLI/MCP output hints surfacing the invariant.

## 2. Architecture Overview

| Phase | Enhancement | Layers Touched |
|-------|-------------|----------------|
| **1** | CLI timeout | `packages/ccdash_cli/src/ccdash_cli/runtime/`, `main.py`, `commands/doctor.py`, `commands/target.py` |
| **2** | DTO aliases | `backend/application/services/agent_queries/models.py`, `feature_forensics.py` |
| **2.5** | linked_sessions invariant | `models.py`, `routers/features.py`, CLI/MCP output hints |
| **3** | Cache foundation | New `backend/application/services/agent_queries/cache.py` (TTL + memoization + fingerprint), `backend/observability/otel.py` (counters), `config.py`, `requirements.txt` (cachetools) |
| **3.5** | Pagination/filter | `feature_list.py`, `repositories/features.py`, `routers/features.py`, CLI `feature list` |
| **4** | Background cache warming | `backend/adapters/jobs/cache_warming.py`, `backend/adapters/jobs/runtime.py` registration |

## 3. How to Test

### CLI Timeout
```bash
backend/.venv/bin/python -m pytest packages/ccdash_cli/tests/test_timeout.py -v
```
Smoke test: `ccdash --timeout 120 feature list` completes within custom timeout.

### Query Cache
```bash
backend/.venv/bin/python -m pytest backend/tests/test_agent_query_cache*.py backend/tests/test_agent_query_memoized_query.py -v
```
Verify fingerprint invalidation, hit/miss metrics, and `--no-cache` bypass.

### DTO Aliases & linked_sessions
```bash
backend/.venv/bin/python -m pytest backend/tests/test_feature_forensics_aliases.py backend/tests/test_features_router_aliases.py backend/tests/test_feature_forensics_endpoint_agreement.py backend/tests/test_features_router_linked_sessions.py -v
```
Confirm top-level `name`/`status` fields, `telemetry_available`, and `linked_sessions` consistency.

### Pagination & Keyword Filter
```bash
backend/.venv/bin/python -m pytest backend/tests/test_features_list_filter.py packages/ccdash_cli/tests/test_commands.py -v
```
Smoke test: `ccdash feature list --q "auth" --limit 100` returns filtered results with correct pagination.

### Background Cache Warming
```bash
backend/.venv/bin/python -m pytest backend/tests/test_cache_warming_job.py backend/tests/test_cache_router.py -v
```
Verify job enqueues, warms cache, and respects active-project scope.

## 4. Test Coverage Summary

- **Cache module**: 98% line coverage (`backend/application/services/agent_queries/cache.py`)
- **Full suite**: 948 tests pass; zero new regressions
- **Per-phase**: All phases (2–4) unit and integration tests passing

## 5. Known Limitations

- **Single-process in-memory**: No distributed or Redis backend yet; cache lost on restart.
- **Keyword filter scope**: Case-insensitive substring match on name/title only; multi-word queries require exact substring (skill gotcha documented).
- **eventual-consistent linked_sessions**: Brief staleness after new sessions land; `sessions_note` hint surfaces this.
- **Active-project scoping**: Background cache warming warms only the active project (not all projects in `projects.json`).
- **Local OTel metrics**: Cache hit/miss counters are local-only; no dashboard shipped yet.

---

**Cross-links**: CHANGELOG.md (2026-04-15), `docs/guides/query-cache-tuning-guide.md`, `docs/guides/cli-timeout-debugging.md`, SKILL.md "Known Gotchas".
