# Query Cache Tuning Guide

Last updated: 2026-04-15

CCDash caches four high-traffic agent query endpoints using an in-process TTL cache (cachetools). This guide covers configuration, warming, bypassing, and troubleshooting for operators.

## What Is Cached

Four endpoints are cached in a single-process scope:

- `GET /api/agent/project-status` — Project overview with session counts, feature status, workflow health.
- `GET /api/agent/feature-forensics/{id}` — Feature execution history, tool usage, token metrics.
- `GET /api/agent/workflow-diagnostics` — Workflow run diagnostics, step outcomes, failure patterns.
- `GET /api/agent/reports/aar` — After-action reports for features and workflows.

Cache is **in-process only**: restarts clear it, and multi-process deployments (multiple API servers) do not share cache state.

## TTL & Configuration

Set `CCDASH_QUERY_CACHE_TTL_SECONDS` to control cache lifetime:

- **Default:** 60 seconds
- **Recommended ranges:**
  - **Fresh data (10–30s):** High-traffic dashboards with frequent user checks; higher CPU load.
  - **Warm dashboards (60–300s):** Standard deployments; balances freshness with query cost.
  - **Disable (0):** Set to `0` to bypass cache entirely; use for debugging or ultra-fresh reads.

Example:
```bash
export CCDASH_QUERY_CACHE_TTL_SECONDS=120
npm run dev  # or restart worker/API runtime
```

## Background Cache Warming

Set `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` to warm the cache proactively:

- **Default:** 300 seconds (5 minutes)
- **Behavior:** Worker runtime periodically refreshes `project-status` and `workflow-diagnostics` for the active project.
- **Disable (0):** Set to `0` to disable warming; cache fills on-demand.

Example:
```bash
export CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS=180
npm run dev:worker  # warming runs in background
```

When disabled, the first user request to each endpoint warms that entry. Subsequent requests within the TTL window hit the cache.

## Bypassing the Cache

### CLI

Most query commands accept `--no-cache`:

```bash
ccdash status project --no-cache
ccdash feature report FEAT-123 --no-cache
ccdash workflow failures --no-cache
```

### HTTP

Append `?bypass_cache=true` to any cached endpoint:

```bash
curl http://localhost:8000/api/agent/project-status?bypass_cache=true
curl http://localhost:8000/api/agent/feature-forensics/FEAT-123?bypass_cache=true
```

Use for on-demand fresh reads during debugging or incident response.

## Observability

Cache hit/miss counters are emitted as OpenTelemetry metrics:

- Metric names and attributes are defined in `backend/observability/otel.py`.
- Wire these into your existing OTel pipeline (Prometheus, Datadog, etc.) to monitor cache effectiveness.
- Low hit rates may indicate TTL is too short or data is changing rapidly.

No cache-specific dashboard is included; correlate hit/miss rates with query latency to tune.

## Troubleshooting

**Stale data:** Data is older than expected.
- Reduce `CCDASH_QUERY_CACHE_TTL_SECONDS` (e.g., 30s for fresh reads).
- Use `--no-cache` to bypass for a single query.
- Verify warming is enabled: `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS > 0` and worker is running.

**Fingerprint errors:** Logs show "cache fingerprint mismatch" or invalidation failures.
- Cache gracefully degrades; queries still work.
- No operator action required; underlying data inconsistency is transient.

**High memory usage:** Process memory grows over time.
- Reduce `CCDASH_QUERY_CACHE_TTL_SECONDS` to evict stale entries sooner.
- Or set to `0` to disable caching entirely.
- Monitor with `ps aux | grep python` (backend process resident memory).

**Warmer not running:** Background refresh doesn't appear to be active.
- Confirm `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS > 0`.
- Verify worker runtime is running: `npm run dev:worker` or equivalent in production.
- Check logs for errors from the refresh job.

## Related Documentation

- `/Users/miethe/dev/homelab/development/CCDash/CLAUDE.md` — Runtime profiles, worker runtime, config patterns.
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/cli-timeout-debugging.md` — Query timeout tuning.
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/agent-query-surfaces-guide.md` — Query service architecture.

## Code References

- `backend/config.py` — Cache config validation and env var defaults.
- `backend/application/services/agent_queries/` — Query service implementations and caching logic.
- `backend/observability/otel.py` — OTel counter definitions.
- `backend/routers/agent.py` — Cache bypass query param handling.
