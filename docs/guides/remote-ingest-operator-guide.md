---
title: "Remote Ingest Operator Guide"
description: "Operate remote session ingest (daemon) and Research Foundry telemetry ingest endpoints"
audience: operators, platform engineers
category: Operations
tags: [remote-ingest, daemon, ndjson, dead-letter, health-monitoring, research-foundry, adrs]
created: 2026-06-28
updated: 2026-07-21
status: stable
related: ["docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md", "docs/project_plans/adrs/adr-014-remote-session-ingest-transport-ndjson-http.md", "docs/project_plans/adrs/adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md"]
---

# Remote Ingest Operator Guide

This guide covers operating two ingest surfaces:
1. **Session remote ingest** — HTTP daemon for forwarding AI agent session logs (idempotent, dead-letter recovery)
2. **Research Foundry telemetry ingest** — Direct RF run telemetry POSTs with the same retry/recovery stack

For architecture and design rationale, see the ADRs linked in the frontmatter.

---

## Architecture Overview

The remote ingest system provides idempotent batch ingest of NDJSON session streams over HTTP,
with local daemon retry/dead-letter recovery and workspace-scoped auth.

**Key components:**

| Component | Role |
|-----------|------|
| `POST /api/v1/ingest/sessions` | Idempotent batch ingest endpoint (bearer auth required) |
| `ccdash-cli daemon` | Local retry/recovery daemon (subcommand group) |
| Dead-letter queue | Permanent-failure batch persistence at `~/.local/state/ccdash/deadletter/` |
| Health endpoint | `GET /api/health/detail` → `ingest_sources` array |

**Transport**: NDJSON (newline-delimited JSON), one record per line, max batch size configurable
(default enforced via `batch_limit_exceeded` 413 response).

**Idempotency**: By `event_id`. Duplicate POSTs with the same `event_id` are deduplicated server-side;
the response envelope always includes `accepted`, `rejected[]`, and `dead_lettered[]` counts.

---

## Research Foundry Telemetry Ingest

Research Foundry (RF) emits schema-validated per-run telemetry (`ccdash_event`) that can be POSTed to CCDash
for cost/quality analytics and session correlation. The RF ingest surface reuses the same idempotent
cursor/dead-letter stack as session ingest.

### Enabling RF Telemetry Ingest

**Feature flag**: `CCDASH_RF_TELEMETRY_ENABLED` (default: `true` — fail-open)

```bash
# Enable RF telemetry ingest (default)
export CCDASH_RF_TELEMETRY_ENABLED=true

# Disable RF telemetry ingest (returns 405 Method Not Allowed)
export CCDASH_RF_TELEMETRY_ENABLED=false
```

When disabled, `POST /api/v1/ingest/rf-events` returns a 405 error with hint to enable the flag.

### Ingest Endpoint

```
POST /api/v1/ingest/rf-events
Content-Type: application/json
Authorization: Bearer <token>

<rf-ccdash-event-json>
```

**Authentication**: Bearer token (workspace-scoped, same as session ingest).

**Idempotency**: By `event_id` field on the RF event payload.

**Response**: Same envelope as session ingest — `accepted`, `rejected`, `dead_lettered`, `cursor_advanced_to`.

### Health Monitoring

RF ingest is tracked as a distinct `source_id="rf"` in the ingest-sources health rollup:

```bash
curl http://localhost:8000/api/health/detail | jq '.ingest_sources[] | select(.source_id == "rf")'

# Output:
# {
#   "source_id": "rf",
#   "project_id": "main",
#   "workspace_id": "default-local",
#   "last_cursor": "550e8400-e29b-41d4-a716-446655440000",
#   "last_ingest_at": "2026-07-21T15:42:03Z",
#   "lag_seconds": 30,
#   "state": "connected"
# }
```

**State meanings** (same as session ingest):

| State | Meaning | Action |
|-------|---------|--------|
| `idle` | No RF events ingested yet | Monitor; expected until RF emits first event |
| `connected` | Recent activity; lag <300s | Nominal operation |
| `backed_up` | Lag 300–900s | RF ingest is slow; monitor server load |
| `disconnected` | No activity for >900s AND recent POST failures | Server/network issue; investigate server health |

### Capability Advertised

The server advertises RF telemetry capability via the capabilities endpoint:

```bash
curl http://localhost:8000/api/v1/capabilities | jq '.capabilities[]' | grep research
# "research-runs:*"
```

This capability string signals to agents (e.g., IntentTree) that the server supports RF run telemetry queries
and ingest. See `docs/guides/external-api-lan-deployment.md` for the full capability discovery contract.

---

## Daemon Lifecycle

### Starting the Daemon

```bash
ccdash-cli daemon start \
  --server http://localhost:8000 \
  --token <BEARER_TOKEN> \
  --poll-interval 30s
```

**Environment**:
- `CCDASH_DAEMON_SERVER` - Server base URL (default: `http://localhost:8000`)
- `CCDASH_DAEMON_TOKEN` - Bearer token (required; override `--token` flag)
- `CCDASH_DAEMON_POLL_INTERVAL` - Health/dead-letter poll interval (default: 30s)

**Output**:
- Logs → stderr (machine-readable JSON, `level`, `msg`, `timestamp`)
- Status file → `~/.local/state/ccdash/daemon.status.json` (updated every poll)

### Checking Daemon Status

```bash
ccdash-cli daemon status

# Output:
# Status: running (pid 12345)
# Server: http://localhost:8000
# Last poll: 2026-06-28T15:42:03Z (healthy)
# Stats:
#   Ingested: 4,821
#   Retried: 312
#   Abandoned: 8
#   Deadlettered: 42
```

Status file (`~/.local/state/ccdash/daemon.status.json`):

```json
{
  "state": "running",
  "pid": 12345,
  "server": "http://localhost:8000",
  "last_poll": "2026-06-28T15:42:03Z",
  "health_status": "healthy",
  "counters": {
    "ingested_total": 4821,
    "retry_total": 312,
    "abandoned_total": 8,
    "deadlettered_total": 42
  }
}
```

### Replaying Dead-Letter Files

Dead-letter files accumulate at `~/.local/state/ccdash/deadletter/` when batches permanently fail
(e.g., unrecoverable 4xx errors).

```bash
# Dry run (inspect, no mutation)
ccdash-cli daemon replay --dry-run

# Replay all dead-letter files
ccdash-cli daemon replay

# Replay from a specific directory
ccdash-cli daemon replay --dir ~/Archives/ccdash-deadletter/

# Purge successful replays (move to replayed/ subdirectory)
ccdash-cli daemon replay --purge
```

**Replay behavior**:
- Each dead-letter file is re-POSTed as-is to the ingest endpoint
- Successes move to `~/.local/state/ccdash/deadletter/replayed/` (timestamp-scoped subdirs)
- Failures remain in `deadletter/` (can be retried again later)
- `--dry-run` shows what would be replayed; no mutations

---

## Failure Scenarios & Troubleshooting

### Server Unreachable (Network Error)

**Symptom**: Daemon status shows `health_status: unhealthy`, repeated connection errors in logs.

**Behavior**:
- Retry: up to 10 attempts, exponential backoff capped at 60s
- After max retries, batch is **abandoned** (counter incremented; batch discarded)
- Logs each retry at INFO level with backoff duration

**Recovery**:
1. Verify server is reachable: `curl http://<server>:8000/api/health`
2. Check network connectivity: `ping`, `nc`, routing
3. Restart daemon once server is healthy: `ccdash-cli daemon start`
4. Dead-letter batches will be replayed on next poll

### 413 Batch Too Large

**Symptom**: Daemon logs show `413 batch_limit_exceeded` errors.

**Behavior**:
- Batch is split in half and re-submitted
- Recursive splits until each sub-batch is ≤ limit
- If a single record exceeds the limit, batch is dead-lettered (unrecoverable)

**Tuning**: Batch size limit is server-side; operators can adjust via `CCDASH_INGEST_BATCH_MAX_BYTES`
(default 10MB). Reconfiguring does NOT require daemon restart; the daemon queries `/api/health/detail`
for current batch limit on each poll.

### Permanent 4xx Errors (Invalid Auth, Bad Schema)

**Symptom**: Daemon logs show `401 Unauthorized` or `400 Bad Request`.

**Behavior**:
- After 1 attempt (no retry), batch is **dead-lettered** permanently
- File written to `~/.local/state/ccdash/deadletter/<timestamp>-<batch-id>.ndjson`
- Counter `deadlettered_total` incremented
- Operator must investigate and fix root cause (e.g., token expiry, schema mismatch)

**Debugging**:
```bash
# Inspect a dead-letter file
head -5 ~/.local/state/ccdash/deadletter/*.ndjson

# Re-POST one file manually with verbose output
curl -v \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @~/.local/state/ccdash/deadletter/2026-06-28T*.ndjson \
  http://localhost:8000/api/v1/ingest/sessions
```

### Cursor Lag Growing (Ingest Source Falling Behind)

**Symptom**: Via `/api/health/detail` → `ingest_sources[].state == "backed_up"` or `lag_seconds` > 300.

**Meaning**:
- Ingest source is not keeping up with local stream production
- `last_ingest_at` is stale; newer events are accumulating locally

**Debugging**:
```bash
# Check ingest source state (all sources)
curl http://localhost:8000/api/health/detail | jq '.ingest_sources'

# Check RF ingest source specifically
curl http://localhost:8000/api/health/detail | jq '.ingest_sources[] | select(.source_id == "rf")'

# Expected response:
# [
#   {
#     "source_id": "remote-agent-1",
#     "project_id": "main",
#     "workspace_id": "default-local",
#     "last_cursor": "2026-06-28T15:40:00Z",
#     "last_ingest_at": "2026-06-28T15:41:30Z",
#     "lag_seconds": 30,
#     "state": "connected"
#   },
#   {
#     "source_id": "rf",
#     "project_id": "main",
#     "workspace_id": "default-local",
#     "last_cursor": "550e8400-e29b-41d4-a716-446655440000",
#     "last_ingest_at": "2026-07-21T15:42:03Z",
#     "lag_seconds": 10,
#     "state": "connected"
#   }
# ]
```

**State meanings**:

| State | Meaning | Action |
|-------|---------|--------|
| `idle` | No ingest activity for >900s (15min) | Monitor; may be expected if stream is quiet |
| `connected` | Recent activity; lag <300s | Nominal operation |
| `backed_up` | Lag 300–900s | Ingest is slow; monitor server load and batch size |
| `disconnected` | No activity for >900s AND recent POST failures | Server/network issue; investigate server health |

**Common causes of lag**:
- Database writer contention (Postgres → connection pool saturation, SQLite → journal lock)
- Large batch processing (slow schema validation or foreign-key checks)
- Undersized batch submit interval on sender (increase `--poll-interval` to send fewer, larger batches)

**Mitigation**:
- Reduce batch frequency (increase poll interval on sender)
- Increase database connection pool (`CCDASH_DB_POOL_SIZE` for Postgres)
- Scale to Postgres if using SQLite (local SQLite is not designed for sustained high concurrency)

### RF Telemetry Feature Flag Disabled

**Symptom**: `POST /api/v1/ingest/rf-events` returns 405 Method Not Allowed.

**Meaning**: `CCDASH_RF_TELEMETRY_ENABLED` is set to `false`.

**Resolution**:
```bash
# Enable RF telemetry ingest
export CCDASH_RF_TELEMETRY_ENABLED=true
# Restart backend
npm run dev:backend
```

Once enabled, RF events can flow normally. Cursor state is preserved across restarts.

### RF Events Not Visible in Analytics Tab

**Symptom**: RF run telemetry ingest endpoint accepts events (202 responses), but the Provider Economics
analytics tab shows no data.

**Meaning**:
- Ingest is working but queries may be lagging (query cache TTL)
- Or RF events haven't been correlated to sessions yet (Phase 2 correlation logic)

**Debugging**:
```bash
# Verify RF events are stored (raw rf_events table)
sqlite3 data/ccdash_cache.db "SELECT COUNT(*) as rf_event_count FROM rf_events;"

# Verify research_runs rollup is computed (derived table)
sqlite3 data/ccdash_cache.db "SELECT COUNT(*) as research_run_count FROM research_runs;"

# Bypass client-side cache and force fresh fetch
curl http://localhost:8000/api/agent/research-runs?bypass_cache=true | jq '.runs | length'

# Check if RF telemetry is enabled
curl http://localhost:8000/api/health/detail | jq '.ingest_sources[] | select(.source_id == "rf")'
```

If `rf_events` count is 0, verify RF is POSTing events. If `research_runs` count is 0 but `rf_events` > 0,
the rollup derivation may be stale — check server logs for correlation errors.

---

## Health Monitoring

### Health Endpoint Overview

```bash
# Quick check
curl http://localhost:8000/api/health | jq '.'

# Response:
# {
#   "status": "ok",
#   "auth_mode": "workspace_token",
#   "version": "0.51.0"
# }
```

### Detailed Health (Ingest Source State)

```bash
curl http://localhost:8000/api/health/detail | jq '.ingest_sources'
```

**Freshness buckets** (configurable):
- `CCDASH_INGEST_SOURCE_FRESH_SECONDS` (default 300) - state is `connected` or `idle`
- `CCDASH_INGEST_SOURCE_STALE_SECONDS` (default 900) - state is `backed_up` or `disconnected`

### Daemon Metrics

Monitor daemon status file counters:

| Counter | Meaning | Threshold |
|---------|---------|-----------|
| `ingested_total` | Total sessions accepted | Baseline for performance tracking |
| `retry_total` | Temporary failures retried | Should be <5% of ingested; spikes indicate flakiness |
| `abandoned_total` | Max retries exceeded | Should be 0 in steady state; investigate if >0 |
| `deadlettered_total` | Permanent failures | Should be 0; indicates auth/schema issue or corrupt batch |

---

## Rollback: Fall Back to Filesystem-Only

If remote ingest fails catastrophically, disable ingest and revert to local filesystem mode.

**Steps**:

1. Stop the daemon:
   ```bash
   kill $(pgrep -f 'ccdash-cli daemon')
   ```

2. Disable ingest via env var:
   ```bash
   export CCDASH_INGEST_ENABLED=0
   # Restart backend
   npm run dev:backend
   ```

3. Worker resumes reading from local `.claude/` filesystem directly (no remote ingest)

4. Preserve dead-letter files for later recovery:
   ```bash
   cp -r ~/.local/state/ccdash/deadletter ~/Archives/ccdash-deadletter-backup-2026-06-28
   ```

5. Once issues are resolved, re-enable ingest:
   ```bash
   export CCDASH_INGEST_ENABLED=1
   ccdash-cli daemon start ...
   ccdash-cli daemon replay --dir ~/Archives/ccdash-deadletter-backup-2026-06-28
   ```

---

## Reference: Ingest Endpoints

### Session Remote Ingest

```
POST /api/v1/ingest/sessions
Content-Type: application/x-ndjson
Authorization: Bearer <token>

<session-event-line-1>\n
<session-event-line-2>\n
...
```

Each line is a JSON object with `event_id` (required, must be unique).

### Research Foundry Telemetry Ingest

```
POST /api/v1/ingest/rf-events
Content-Type: application/json
Authorization: Bearer <token>

<rf-ccdash-event-json>
```

Single JSON object (not NDJSON) with `event_id` (required, must be unique). Gated by `CCDASH_RF_TELEMETRY_ENABLED`.

### Response Codes

| Code | Meaning | Applies To |
|------|---------|-----------|
| 200 | Single RF event accepted; response body includes counts | `/api/v1/ingest/rf-events` |
| 202 | Batch accepted; response body includes counts | `/api/v1/ingest/sessions` |
| 400 | Bad JSON/NDJSON format or missing required field | Both |
| 401 | Invalid or missing bearer token | Both |
| 405 | Feature disabled (RF telemetry disabled via `CCDASH_RF_TELEMETRY_ENABLED=false`) | `/api/v1/ingest/rf-events` |
| 413 | Batch exceeds size limit (daemon will split and retry on sessions ingest) | `/api/v1/ingest/sessions` |
| 5xx | Server error (daemon will retry with backoff) | Both |

### Response Body (Success / 200 / 202)

```json
{
  "accepted": 1,
  "rejected": [],
  "dead_lettered": [],
  "cursor_advanced_to": "2026-07-21T15:42:03.123Z"
}
```

- `accepted` - Number of idempotent records stored (1 for RF events, N for session batches)
- `rejected` - List of record indices + errors for records that failed validation
- `dead_lettered` - Records deemed permanently unrecoverable (e.g., foreign-key constraint)
- `cursor_advanced_to` - Highest event ID or timestamp ingested (for source to track progress)

### Response Body (Error / 405 / 400)

```json
{
  "error": {
    "code": "RF_TELEMETRY_DISABLED",
    "message": "RF telemetry ingest is disabled.",
    "hint": "Set CCDASH_RF_TELEMETRY_ENABLED=true to enable."
  }
}
```

Or for validation errors:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Missing required field: event_id",
    "details": {
      "field": "event_id",
      "constraint": "required"
    }
  }
}
```

