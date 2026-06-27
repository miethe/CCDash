---
title: "Phase 0 Call-Site Audit — project_id Threading"
doc_type: worknote
created: 2026-06-11
feature_slug: ccdash-core-remediation
task_ref: T0-003
---

# Phase 0 — Call-Site Audit: project_id Threading

Scope: all invocations of `session_repo.get_by_id()` and `session_repo.get_many_by_ids()`
found via grep across the backend. Primary audit scope is `_client_v1_sessions.py`,
`routers/agent.py`, and `application/services/agent_queries/`. All call sites in
modified files are documented regardless of scope.

## Audit Table — Primary Scope Files

| File:Line | Function | project_id source | Decision |
|-----------|----------|-------------------|----------|
| `backend/routers/_client_v1_sessions.py:263` | `get_session_family_v1` | `app_request.context.project.project_id` (active) → then `anchor.get("project_id")` for family members | **THREADED** (T0-004): anchor looked up with `project_id=requested_project_id`; family members scoped via anchor-derived `project_id`. Anchor-not-found-in-project → 404, no active-project fallback. |
| `backend/routers/agent.py` | (all) | N/A | **NO session repo calls** — agent.py has zero direct `get_by_id`/`get_many_by_ids` invocations on the session repo. |
| `backend/application/services/agent_queries/feature_evidence_summary.py:254` | feature evidence loop | `scope.project.id` from `resolve_project_scope(context, ports)` | **THREADED**: `project_id=scope.project.id` forwarded to `get_many_by_ids`. |
| `backend/application/services/agent_queries/feature_forensics.py:139` | `_load_feature_session_rows` | `scope.project.id` from caller | **THREADED**: function signature extended with `project_id` param; caller passes `scope.project.id`. |
| `backend/application/services/agent_queries/planning.py:2415` | next-run preview context refs | `project.id` from scope | **THREADED**: `project_id=project.id` forwarded to `get_many_by_ids`. |

## Audit Table — Out-of-Scope Call Sites (Also Threaded in Phase 0)

| File:Line | Function | Status |
|-----------|----------|--------|
| `backend/application/services/session_intelligence.py:174` | `get_session_detail` | **THREADED** — `project_id=project.id` |
| `backend/routers/api.py:930` | `get_session` | **THREADED** — `project_id=project.id if project else None` |
| `backend/routers/api.py:1275` | `get_session_linked_features` | **THREADED** — `project_id=project.id if project else None` |
| `backend/application/services/documents.py:403` | document cross-ref | **THREADED** — `project_id=project.id` |
| `backend/services/integrations/skillmeat_memory_drafts.py:247` | draft candidate rows | **THREADED** — `project_id=str(project.id)` |

## Intentionally Active-Bound (Pass None / No project_id available)

| File:Line | Function | Reason |
|-----------|----------|--------|
| `backend/routers/api.py:899` | `get_session_logs` | No project scope resolved at call site; logs endpoint, active-project OK |
| `backend/routers/api.py:960` | fork child lookup in `get_session` | Child fork looked up within same active-project session handler |
| `backend/routers/api.py:1377` | `upsert_session_linked_feature` | Mutation endpoint; no project_id threaded (Phase 0 scope) |
| `backend/routers/api.py:1477` | `delete_session_linked_feature` | Mutation endpoint; no project_id threaded (Phase 0 scope) |
| `backend/routers/features.py:1772` | feature session lookup | Active-project bound (Phase 0) |
| `backend/application/services/sessions.py:327` | `backfill_session_badges` | Badge backfill; active-project bound (Phase 0) |
| `backend/services/stack_recommendations.py:1114` | recommendation session | Active-project bound (Phase 0) |

## Protocol Update

`backend/db/repositories/base.py` — `SessionRepository` Protocol updated to reflect new
signatures: `get_by_id(session_id, project_id=None)` and `get_many_by_ids(ids, project_id=None)`.

## Summary

- **Threaded with explicit project_id**: 10 call sites
- **Intentionally active-bound (pass None / default)**: 7 sites  
- **No session repo calls**: `routers/agent.py`
- **Silent drops**: 0 — every call site's decision is documented above

All active-project-bound sites retain identical hot-path behavior via `project_id=None` (default).
