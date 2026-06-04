---
title: "ADR-007: DB-Write Failure-Surfacing Standard"
type: "adr"
status: "accepted"
created: "2026-06-03"
parent_prd: "docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md"
depends_on_spike: "docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md"
tags: ["adr", "database", "observability", "reliability", "error-handling", "monitoring", "persistence"]
---

# ADR-007: DB-Write Failure-Surfacing Standard

## Status

**Accepted** — Ratified by operator 2026-06-03 following audit and findings review (see Findings F-01, F-06, F-09, RQ7).

**Ratification Note (2026-06-03):** Phase 2 enforcement mechanisms shipped and verified:
- Shared retry helpers `retry_on_locked()` and `retry_on_locked_sync()` deployed in `backend/db/repositories/base.py` (lines 109–179, 33–108)
- Prometheus counter `ccdash_db_write_failures_total` (with `repo` and `reason` labels) instrumented in `backend/observability/otel.py` (lines 408–409, 660–661, 1616–1619)
- Health detail fields added to `/api/health/detail` per §3 above
- Registry and queue repositories retrofitted to use the shared helper and surface failures via observability
- Retrofit of remaining legacy repositories (`tasks`, `features`, `documents`) is tracked in `docs/project_plans/design-specs/retry-on-locked-repo-retrofit.md`; all NEW write paths must use `retry_on_locked` per CLAUDE.md convention.

## Context

CCDash's database write-failure handling is inconsistent and largely invisible:

**Inconsistency (Finding F-06):**
- Most async repositories propagate write failures (log-then-`raise`)
- Four high-contention queue repositories (execution, job_queue, telemetry_queue, worktree_contexts) have a `_commit_with_retry` helper that retries on `locked` exceptions
- The project registry sync path (`SqliteProjectRepository._flush_snapshot_to_db`) swallows write exceptions entirely with `except Exception: logger.error(...)` and silently continues (Finding F-01)
- Independent sync connections (`SqliteProjectRepository`, sync `sessions.py` helpers) lack the `PRAGMA busy_timeout` pragma that the async singleton provides

**Invisibility (Finding F-09):**
- `/api/health` exposes only singleton-connection existence, not registry flush status or DB-write failures
- No Prometheus counter for swallowed or retried writes
- Registry persistence test passes even when the flush fails (Finding F-11), making failures undetectable in CI

**Root cause (new):**
- No unified contract for write-path behavior: should a locked error be retried? surfaced? swallowed? Different repos answer differently.
- No shared helper; each repo that retries reimplements the logic (violation of DRY, inconsistent timeouts and backoff strategies)
- Write-failure visibility relies on process-level logging, which does not propagate to operators/dashboards

This inconsistency creates latent correctness issues (especially in the registry path) and delays incident detection.

## Decision

**Establish a uniform contract for every database write path:**

### 1. Never Silently Swallow Write Failures

A caught write exception must either:
- **(a) Retry via the shared locked-retry helper** (see #2 below), then re-raise if still failing, **or**
- **(b) Record to a surfaced status field** (e.g., `registry.last_flush_status`) — never log-and-continue with a success-shaped return

The registry bootstrap flush (F-01) is the canonical example of a failure that must not be swallowed. On exception:
- Do **not** set `_snapshot_loaded=True` (which signals success to callers)
- Do **not** return a bare `True` (treating it as success)
- Do **raise** (propagate) or retry and then raise, **or** set a failure-status field and later expose it via health

### 2. One Shared Locked-Retry Helper in `repositories/base.py`

Create a single, reusable helper (generalize the existing `execution.py:_commit_with_retry` pattern):

```python
async def commit_with_retry(
    connection,
    max_retries: int = 5,
    initial_backoff_ms: int = 100
) -> None:
    """
    Commit, retrying on 'database is locked' up to max_retries times.
    Raises OperationalError if still locked after retries.
    Increments ccdash_db_write_failures_total counter on retry.
    """
```

**Apply this helper to:**
- All new write paths (repositories, scripts, migrations)
- The registry sync write path (`SqliteProjectRepository._flush_snapshot_to_db`)
- Sync `sessions.py` helpers that write
- Any independent sync connection (ensure `PRAGMA busy_timeout` is also set on the connection)

**Consequences for independent connections:**
- Every `sqlite3.connect()` that writes must issue `PRAGMA busy_timeout=<ms>` to match the async singleton's `busy_timeout=30000`
- Use the shared helper instead of ad-hoc retry logic

### 3. Surface Failures via Observability

**Prometheus counter:**
```python
ccdash_db_write_failures_total{repo, reason}
```
- `repo`: e.g., `projects`, `sessions`, `analytics`, `execution_queue`
- `reason`: e.g., `locked`, `disk_full`, `constraint_violation`
- Incremented when a write is retried (or when a surfaced failure is recorded)

**Health field additions** (`/api/health/detail`, Finding F-09):
- `registry.project_count`: number of rows in `projects` table (verifies the bootstrap read succeeded)
- `registry.last_flush_status`: `"ok"` / `"failed"` / `"locked"` (from `DbProjectManager._last_flush_status` field)
- `db.size_bytes`: physical file size in bytes (from `PRAGMA page_count * page_size`)
- `db.freelist_bytes`: reclaimable pages (from `PRAGMA freelist_count * page_size`)
- `retention.last_run`: ISO timestamp of the last retention/VACUUM job (if enabled)

These fields make DB-write and storage health observable without process logs.

### 4. Test Contract: Persistence Assertion + Lock-Injection

**Every new write path ships with:**
- A **direct persistence assertion**: `SELECT COUNT(*)` or `repo.count()` immediately after the write, verifying data reached the DB (not just a return value)
- For contention-prone paths (registry, queue repos), a **lock-injection test** that holds a write-lock in a second connection, triggers the write, and asserts the helper either retries-and-succeeds or raises (never succeeds silently)

**Example (registry):**
```python
def test_registry_flush_retries_on_locked():
    """Reproduces F-01: flush must retry, not swallow."""
    registry = DbProjectManager(...)
    # Insert a project via registry
    # Hold a lock in a second connection
    with lock_holder_connection():
        # This must not silently fail; it retries and eventually succeeds
        # or raises (never returns True with project_count=0)
        registry._flush_snapshot_to_db()
    # Verify the project made it to the DB
    assert repo.count() == 1
```

This test directly reproduces and prevents F-01 regression.

## Decision Drivers

1. **Correctness**: Silent failures hide data-loss bugs (F-01 persisted undetected for months); a uniform contract prevents this class of defect
2. **Observability**: Operators cannot respond to invisible failures; surfacing via health + counters enables early detection and incident response
3. **Consistency**: Reimplementing retry logic in each repo creates divergence in timeouts, backoff, and error semantics; a shared helper enforces uniform behavior
4. **Enterprise readiness**: Production database systems require visible failure modes; silent swallows are unacceptable at scale
5. **Test coverage**: Lock-injection tests prevent regressions by reproducing the contention scenarios that cause failures; direct assertions catch data that doesn't actually persist

## Alternatives Considered

### Alternative: Retry at Call-Site, Not in Write Path

Each router/service that calls a write path implements retry logic and handles `OperationalError`.

**Disadvantages:**
- Responsibility is diffuse; easy to miss a call-site
- Write-path logic duplicates across routers, services, and CLI
- No single source of truth for timeout/backoff strategy
- Health/Prometheus integration must happen at every call-site

**Rejected:** Inconsistency and maintenance burden outweigh flexibility.

### Alternative: Log and Continue (Status Quo)

Catch write exceptions, log them, and return a success code, letting the caller assume the write succeeded.

**Disadvantages:**
- Latent data-loss (the F-01 failure mode)
- Invisible to operators (no Prometheus counter, no health field)
- Regression tests cannot catch the failure (tests pass even when data doesn't persist, as in F-11)
- Contradicts enterprise durability expectations

**Rejected:** Fundamental correctness issue; unacceptable for a persistence layer.

## Consequences

### Positive

- **Fail-fast on write errors**: Exceptions are never swallowed; callers and operators know immediately when a write fails
- **Observable**: Prometheus counter + health fields enable monitoring and alerting
- **Consistent**: All repos follow the same retry/failure contract; no surprises
- **Testable**: Lock-injection tests directly reproduce contention scenarios, preventing regressions like F-01
- **Enterprise-grade**: Durability failures are visible and actionable

### Negative

- **Small refactor required**: The registry sync path and independent sync connections must be updated to use the shared helper
- **Test burden**: Contention-prone paths require lock-injection tests (not just functional tests); adds CI complexity
- **Backoff tuning**: The initial backoff and max-retries constants must be set appropriately; tuning may be needed after deployment

### Risks

- **Cascading failures**: If a write path is heavily contended and retries max out, it will block the caller; may cascade to other operations. Mitigate: monitor `ccdash_db_write_failures_total` and alarm on high counts.
- **Test flakiness**: Lock-injection tests may be sensitive to timing and thread scheduling. Mitigate: use a deterministic lock pattern (e.g., acquire lock first, then trigger write in isolated thread/process).

## Related Decisions and Dependencies

- **ADR-006** mandates that the registry write must be reliable; this ADR provides the standard that makes the registry write reliable
- **F-01 Remediation** (P0-1 through P0-3) applies this contract to the registry specifically
- **F-06 Remediation** (P1-4) applies the shared helper to other sync paths
- **F-09 Remediation** (P3-1, P3-2) adds the health fields and Prometheus counter

## Implementation Checklist

- [ ] Create `repositories/base.py:commit_with_retry()` helper (generalize `execution.py:_commit_with_retry`)
- [ ] Update all independent sync connections to issue `PRAGMA busy_timeout`
- [ ] Apply the helper to registry sync write path (`SqliteProjectRepository._flush_snapshot_to_db`)
- [ ] Apply the helper to sync `sessions.py` helpers
- [ ] Add `ccdash_db_write_failures_total{repo,reason}` Prometheus counter at retry/surface sites
- [ ] Add health fields to `/api/health/detail`: `registry.project_count`, `registry.last_flush_status`, `db.size_bytes`, `db.freelist_bytes`, `retention.last_run`
- [ ] Write lock-injection test for registry flush (reproduces F-01)
- [ ] Write lock-injection tests for contention-prone queue repos
- [ ] Verify existing registry persistence test now includes direct `repo.count()` assertion post-flush
- [ ] CI: add a failure-injection lane that holds locks and triggers writes (validates retry behavior)
