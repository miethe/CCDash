---
title: "ADR-013: Entire.io Live-Update Mechanism — fs-watch on Local Ref, git-fetch Poll for Remote"
type: "adr"
status: "accepted"
created: "2026-05-11"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/spikes/entire-io-integration.md"
related_adrs:
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-011-entire-ingest-path-decision.md
tags: ["adr", "live-update", "fs-watch", "git-fetch", "entire"]
---

# ADR-013: Entire.io Live-Update Mechanism — fs-watch Primary, git-fetch Fallback

## Status

Accepted (SPIKE-B resolved 2026-05-11)

## Context

ADR-011 fixes the read path. ADR-013 fixes **how often the read path is invoked** to keep latency from checkpoint creation to CCDash visibility within budget.

The charter (RQ-3) targets p50 < 30s. The three candidate triggers are:

1. **fs-watch on `.git/refs/heads/entire/checkpoints/v1`** — Local repo case: when `entire` writes a new checkpoint, the ref file is updated; watchdog/`watchfiles` fires within tens of milliseconds.
2. **Periodic `git fetch`** — Remote/clone case (CCDash is on a different machine than the repo where `entire` runs, OR the user works on a worktree CCDash doesn't host). Configurable interval (default 30s).
3. **Upstream-registered hook (CCDash as Entire "agent plugin")** — Push-based event delivery; eliminates polling.

## Decision

**fs-watch is the primary live-update mechanism for the local-repo case. git-fetch polling is the fallback for the cross-machine case.** The upstream-hook path is **declined for v1** — see RQ-7 analysis below — and remains a v2 consideration.

The dispatch logic:

```python
class EntireCheckpointSource:
    def __init__(self, repo_path: Path, *, mode: Literal["watch","poll","auto"] = "auto"):
        # auto: if repo_path is a local working directory, use fs-watch;
        #       if repo_path is a bare clone or unreadable for events, use git-fetch poll.
        ...
```

Controlled by env: `CCDASH_ENTIRE_LIVE_MODE=auto|watch|poll` (default `auto`).

### fs-watch specifics

- Watch path: `{repo}/.git/refs/heads/entire/checkpoints/v1`. On packed refs (Entire may pack older refs), also watch `{repo}/.git/packed-refs`.
- Library: `watchfiles` (already a CCDash dependency via the sync engine).
- Coalesce: events within 250ms are batched into one "ref changed → re-enumerate from cursor" cycle. Bounds CPU on rapid-fire checkpoint creation.
- On event: invoke `GitReader.list_new_checkpoints_since(cursor)`, parse each, emit `IngestEvent`s through the port.

### git-fetch poll specifics

- Interval: `CCDASH_ENTIRE_FETCH_INTERVAL_SECONDS` (default `30`; min `10`, max `600`).
- Fetch command (equivalent; never shells out): `pygit2.Remote.fetch(['+refs/heads/entire/checkpoints/v1:refs/remotes/<remote>/entire/checkpoints/v1'])` — refspec-restricted to keep the fetch payload minimal.
- Auth: inherited from the user's git config (SSH agent, credential helper). No CCDash-managed credentials.
- On detect: same path as fs-watch (`list_new_checkpoints_since(cursor)`).

### Why not the upstream-hook path

Per the WebSearch review of Agent Hooks (charter §2 / RQ-7), the upstream "external agent plugin interface" is a **write-side** integration: it lets CCDash *register an agent* whose sessions are captured into Entire. It is not a **read-side** "subscribe to new checkpoints" surface for third-party consumers watching what other agents have written. Filing an upstream feature request for a read-side webhook is the recommended v2 path; see [upstream-feedback memo](../spikes/entire-io-integration/upstream-feedback-memo.md).

Until that lands, branch-watch is the correct mechanism: it is the only thing upstream actually contracts (`entire/checkpoints/v1` is `v1`-versioned).

## Decision Matrix

Scored 0–5; higher is better. Weights reflect that p50 latency is the dominant criterion (charter §3.3 explicit target).

| Criterion (weight) | fs-watch (local) | git-fetch poll (remote) | Upstream hook |
|---|---|---|---|
| p50 latency (w=3) | 5 (sub-second on local writes) | 2 (mean = interval/2; 15s at default 30s) | 5 (push) |
| Cross-machine support (w=3) | 0 (local only) | 5 | 5 |
| Setup complexity (w=2) | 5 (zero config) | 4 (one env var) | 1 (requires upstream change) |
| CPU at idle (w=2) | 5 (inotify/fsevents wake on event) | 3 (interval-driven syscall + network) | 5 |
| Network cost (w=1) | 5 (none) | 3 (one git fetch per interval) | 4 (push payload only) |
| Robustness to upstream change (w=2) | 5 (ref file format is git-stable) | 5 | 1 (hook API does not exist yet) |
| **Weighted total (when applicable)** | **52 (local only)** | **45 (cross-machine)** | **45 (blocked on upstream)** |

The matrix supports the auto-dispatch decision: fs-watch where it works, polling where it must. The upstream hook is competitive once it exists, but cannot be relied on for v1.

## Hard Gates (E2 acceptance criteria for Phase 5)

| Gate | Mode | Target |
|---|---|---|
| End-to-end latency (checkpoint write → CCDash row visible) p50 | fs-watch | < 10s |
| End-to-end latency p95 | fs-watch | < 30s |
| End-to-end latency p50 | git-fetch poll @ 30s interval | < 30s (interval/2 + parse + upsert) |
| End-to-end latency p95 | git-fetch poll @ 30s interval | < 45s |
| CPU at 1-hour idle (no checkpoints) | fs-watch | < 0.5% on M-series Mac equivalent |
| CPU at 1-hour idle (no checkpoints) | git-fetch poll @ 30s | < 2% (one fetch per interval) |
| Rapid-fire: 50 checkpoints in 30s | both | All ingested; no duplicate rows; cursor advances monotonically |
| Mode auto-selection (local repo) | auto | fs-watch chosen |
| Mode auto-selection (bare clone / no `.git/refs/heads/...` accessible) | auto | poll chosen |
| Manual override `CCDASH_ENTIRE_LIVE_MODE=poll` honored even on local repo | both | poll engaged |

Fallback if fs-watch p50 misses 10s: **stay on fs-watch**, investigate watchfiles tuning. The 30s ceiling is the charter requirement and is met at p95 even with poor watch latency.

Fallback if poll p50 misses 30s at the default interval: **lower default to 15s**; if CPU at idle exceeds 4%, raise to 60s and accept the latency relaxation in the cross-machine case (clearly labeled in operator docs).

## Coexistence with the Sync Engine

`EntireCheckpointSource` is a `SessionIngestSource` per ADR-009. The sync engine drives it the same as any other source:

```python
# SyncEngine.run loop (existing)
for source in self._sources:
    cursor = await self._cursor_repo.get_or_create(source.source_id, project_id, workspace_id)
    async for event in source.stream(since=cursor):
        await self._session_repo.upsert(...)
        await source.ack(event)
        await self._cursor_repo.advance(...)
```

`EntireCheckpointSource.stream()` is an `AsyncIterator` whose internal driver is either the fs-watch event loop or the polling loop, depending on mode. The engine does not care which. This keeps ADR-013's complexity inside the source and avoids leaking it into the engine.

### Initial backfill

On first registration, the cursor is unset → the source enumerates the full `entire/checkpoints/v1` branch from epoch and emits events oldest-first. This is the same shape as `FilesystemSource`'s initial scan; no new machinery required. A `CCDASH_ENTIRE_BACKFILL_BATCH_SIZE` (default `200`) bounds memory during cold start.

## Consequences

### Positive

- Latency target met for both common cases without new infrastructure.
- The mode is opaque to the engine — auto-dispatch keeps the operator-facing surface tiny.
- Polling case is bounded by a single integer env var; debugging is one config check.

### Negative

- Two driver loops to maintain. Mitigated by a shared `_ingest_since(cursor)` private method; the loop variants are just trigger sources.
- Polling case loses the latency advantage but is unavoidable for cross-machine setups. Documented in the operator guide.
- A new env var surface (`CCDASH_ENTIRE_LIVE_MODE`, `CCDASH_ENTIRE_FETCH_INTERVAL_SECONDS`, `CCDASH_ENTIRE_BACKFILL_BATCH_SIZE`). Three knobs is the floor.

### Risks

| Risk | Mitigation |
|---|---|
| fs-watch silently drops events under macOS fsevents resource pressure | Backstop: a low-frequency periodic "re-enumerate from cursor" (default 5min) reconciles. Configurable via `CCDASH_ENTIRE_WATCH_RECONCILE_SECONDS`. |
| `git fetch` requires auth that prompts interactively | Daemon process is non-interactive; configure git credentials in advance. Document in operator guide. Polling source surfaces `ingest_sources[i].error_count` on auth failures. |
| Upstream packs `entire/checkpoints/v1` and removes the loose ref file | Watch `packed-refs` too; documented above |
| Network blips during polling | Polling source enters error_count back-off (same pattern as F-3 in SPIKE-A failure matrix) |

## Health Endpoint Integration

`EntireCheckpointSource` participates in the `/api/health.ingest_sources[]` block already specified in SPIKE-A Phase 7. Per-source health entry:

```json
{
  "source_id": "entire",
  "mode": "watch",
  "last_ingest_at": "2026-05-11T14:32:01Z",
  "cursor_lag_seconds": 4,
  "error_count": 0,
  "branch_head_sha": "<40-hex>",
  "last_cursor": "<40-hex>:<12-hex>"
}
```

UI surface (chip + badge) is unchanged from SPIKE-A RQ-7 — the `entire` source-ref chip simply joins `fs` and `remote`.

## Alternatives Considered

1. **Polling only.** Rejected — fails p50 latency budget at any reasonable interval; wastes CPU/network in the local case where fs-watch is free.
2. **fs-watch only.** Rejected — leaves cross-machine deployments unsupported.
3. **Wait for upstream webhook API.** Rejected — blocks v1 on an upstream change with no committed timeline. Filed as v2 feedback.
4. **Periodic polling without `git fetch` (just re-read the local branch).** Rejected — wouldn't pick up checkpoints that originated on another machine; defeats the cross-machine case.

## Related

- ADR-009 (port + cursor model)
- ADR-011 (read mechanism; this ADR fixes the trigger)
- Charter: `docs/project_plans/spikes/entire-io-integration-charter.md`
- Upstream-feedback memo: `docs/project_plans/spikes/entire-io-integration/upstream-feedback-memo.md`
