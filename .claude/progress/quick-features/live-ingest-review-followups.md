---
slug: live-ingest-review-followups
status: in-progress
parent_feature: enterprise-live-session-ingest-v1
source: senior-code-reviewer report (2026-05-02)
points: 4
pyright_fixes: completed-2026-05-02
---

# Live Ingest Review Follow-ups (Quick Feature)

Surgical fixes from the post-implementation review of `enterprise-live-session-ingest-v1`. Larger items (listener reconnect FU-2, real wire-boundary smoke FU-4) are deferred to dedicated planning.

## Tasks

### FU-1 — Compose healthcheck env var + README polling consistency
- **Files**: `deploy/runtime/compose.yaml`, `deploy/runtime/README.md`
- **Owner**: devops-architect
- Fix `worker-watch` healthcheck to read `CCDASH_WORKER_WATCH_PROBE_PORT` (currently reads `CCDASH_WORKER_PROBE_PORT`).
- Resolve doc/code mismatch on `WATCHFILES_FORCE_POLLING`: README claims it's passed to `worker-watch`, compose passes it only to default `worker`. Fix the compose file (pass to `worker-watch`) and align README.

### FU-3 — Publish exception isolation audit + test
- **Files**: `backend/db/sync_engine.py` (and any other publish call sites), `backend/tests/test_postgres_live_fanout.py` (or sibling test)
- **Owner**: python-backend-engineer
- Audit every `LiveEventBus.publish(...)` call site for try/except around `LiveEventBusPayloadTooLarge` + general publish failures. Confirm publish failures cannot abort a sync write.
- Add a targeted test: simulate publisher raising → assert sync write commits and ingestion path returns success.

### FU-5 — OTel instruments for fanout + watcher latency
- **Files**: `backend/observability/otel.py`, `backend/adapters/live_updates/postgres_notify.py`, `backend/adapters/live_updates/postgres_listener.py`, `backend/db/file_watcher.py`
- **Owner**: python-backend-engineer (same task as FU-3 — same domain)
- Register and emit:
  - `ccdash_live_fanout_publish_latency_ms` (histogram)
  - `ccdash_live_fanout_delivered_total` (counter, labels: result=ok|error|too_large)
  - `ccdash_live_fanout_listener_received_total` (counter)
  - `ccdash_watcher_sync_latency_ms` (histogram)
- Follow existing instrument-registration pattern in `otel.py`.

### FU-7 — Document `_COMPACT_PAYLOAD_KEYS` extension contract
- **Files**: `backend/application/live_updates/bus.py`
- **Owner**: python-backend-engineer (bundled with FU-3/FU-5 task)
- Add a short comment above `_COMPACT_PAYLOAD_KEYS` explaining: any field a downstream consumer wants to receive cross-process must be added here. Note `runtimeProfile`/`agentId` as candidates.

### FU-6 — Refresh phase-4/5 progress narrative
- **Files**: `.claude/progress/enterprise-live-session-ingest-v1/phase-4-progress.md`, `.claude/progress/enterprise-live-session-ingest-v1/phase-5-progress.md`
- **Owner**: documentation-writer
- Both files have `status: completed` in YAML but stale "pending" narrative bodies. Update body sections to reflect actual completion (use phase YAML + git log as source of truth).

## Out of scope — defer

- **FU-2** (listener reconnect with exponential backoff): needs `/plan:plan-feature`. Design decisions: supervisor placement, lifecycle integration with `container.py`, retry policy, observability on retry state.
- **FU-4** (real wire-boundary smoke for SessionInspector): needs `/plan:plan-feature`. Requires new test infra (MSW SSE stub or backend-driven integration harness) and reconnect scenario.

## Quality Gates

- `backend/.venv/bin/python -m pytest backend/tests/test_postgres_live_fanout.py backend/tests/test_file_watcher.py backend/tests/test_runtime_bootstrap.py -v`
- `docker compose -f deploy/runtime/compose.yaml --profile live-watch config` (validates compose changes)
- Manual: review `_COMPACT_PAYLOAD_KEYS` comment for clarity.
