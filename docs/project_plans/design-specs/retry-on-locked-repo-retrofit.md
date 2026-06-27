---
schema_version: 2
doc_type: design_spec
title: "retry_on_locked Retrofit for Legacy Write Repositories"
maturity: shaping
status: draft
created: '2026-06-03'
updated: '2026-06-03'
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
tags: [database, reliability, observability, retrofit, technical-debt]
---

# retry_on_locked Retrofit for Legacy Write Repositories

## Problem

Three repositories still call raw `await self.db.commit()` at their write sites,
bypassing the shared `retry_on_locked` helper introduced in P2 (T2-002).
This means:

- Locked-retry behaviour is absent: a transient SQLite lock yields an immediate
  `OperationalError` rather than being retried.
- Failures are invisible to `ccdash_db_write_failures_total`: the Prometheus
  counter is never incremented, so operators have no signal when writes fail in
  these paths.

### Affected locations (raw `await self.db.commit()` call-sites)

| File | Lines | Write operations |
|------|-------|-----------------|
| `backend/db/repositories/tasks.py` | 67, 130 | task create, task update |
| `backend/db/repositories/features.py` | 244, 379, 475 | feature upsert, status update, delete |
| `backend/db/repositories/documents.py` | 346, 481 | document upsert, delete |

**Completed in this commit:** `backend/db/repositories/worktree_contexts.py`
(all three write paths: create, update, delete) was the fourth affected
repository and has been retrofitted as part of the P4/P5 pre-merge remediation.

## Proposed Approach

Mechanical adoption of the `retry_on_locked` convention established by ADR-007
and already in use by `sessions.py`, `execution.py`, and `projects.py`.

For each affected file:

1. Add `from backend.db.repositories.base import retry_on_locked` to imports.
2. Introduce `_REPO_NAME = "<repo>"` constant for the Prometheus label.
3. Replace raw `await self.db.execute(sql, params)` with a `_execute_write`
   helper that delegates to `retry_on_locked`.
4. Replace raw `await self.db.commit()` with a `_commit_with_retry` helper
   that delegates to `retry_on_locked`.
5. Remove any inline duplicate lock-detection logic (`_is_locked_error`,
   local `_LOCK_RETRY_ATTEMPTS`, etc.) if present.

Reference implementation: `backend/db/repositories/execution.py` lines 54-70.

## Acceptance Criteria

- No raw `await self.db.commit()` remains in tasks.py, features.py, or
  documents.py.
- All three repos import and call `retry_on_locked` from `base.py`.
- `ccdash_db_write_failures_total` is incremented on locked retries for each
  repo (verified by lock-injection unit tests per ADR-007 §4).
- Existing tests for all three repos pass without modification.

## Effort Estimate

Low — purely mechanical; ~30 minutes per file. No API or schema changes.

## Deferred Rationale

T2-002 (P2) scoped the initial `retry_on_locked` rollout to the three
highest-contention "sync writer" repositories: `sessions`, `execution`, and
`projects`. The remaining repos (`tasks`, `features`, `documents`,
`worktree_contexts`) were consciously deferred to avoid scope creep on a
high-risk phase. `worktree_contexts` was completed in the P4/P5 pre-merge
pass; the remaining three are captured here for the next remediation sprint.
