---
title: "Remote Ingest Operator Guide"
description: "Operate the remote session ingest endpoint, daemon, and failure recovery workflows"
audience: operators, platform engineers
category: Operations
tags: [remote-ingest, daemon, ndjson, dead-letter, health-monitoring, adrs]
created: 2026-06-28
updated: 2026-06-28
status: stable
related: ["docs/project_plans/adrs/adr-009-ingest-source-routing-schema-and-cursors.md", "docs/project_plans/adrs/adr-014-ndjson-as-transport-encoding.md", "docs/project_plans/adrs/adr-015-local-daemon-ccdash-cli-subcommand-group.md"]
---

# Remote Ingest Operator Guide

This guide covers operating the remote session ingest endpoint, the local daemon, and
troubleshooting failure scenarios. For architecture and design rationale, see the ADRs linked
in the frontmatter.

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
# Check ingest source state
curl http://localhost:8000/api/health/detail | jq '.ingest_sources'

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

## Reference: Ingest Endpoint

### Request

```
POST /api/v1/ingest/sessions
Content-Type: application/x-ndjson
Authorization: Bearer <token>

<session-event-line-1>\n
<session-event-line-2>\n
...
```

Each line is a JSON object with `event_id` (required, must be unique).

### Response Codes

| Code | Meaning |
|------|---------|
| 202 | Batch accepted; response body includes counts |
| 400 | Bad NDJSON format or missing required field |
| 401 | Invalid or missing bearer token |
| 413 | Batch exceeds size limit (daemon will split and retry) |
| 5xx | Server error (daemon will retry with backoff) |

### Response Body (202, 400)

```json
{
  "accepted": 100,
  "rejected": [],
  "dead_lettered": [],
  "cursor_advanced_to": "2026-06-28T15:42:03Z"
}
```

- `accepted` - Number of idempotent records stored
- `rejected` - List of record indices + errors for records that failed validation
- `dead_lettered` - Records deemed permanently unrecoverable (e.g., foreign-key constraint)
- `cursor_advanced_to` - Highest timestamp ingested (for source to track progress)

