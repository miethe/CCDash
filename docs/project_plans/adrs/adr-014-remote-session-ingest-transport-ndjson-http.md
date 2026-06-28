---
title: "ADR-014: Remote Session Ingest Transport — Chunked NDJSON over HTTPS POST"
type: "adr"
status: "accepted"
created: "2026-05-10"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
tags: ["adr", "transport", "ingest", "ndjson", "remote", "streaming"]
---

# ADR-014: Remote Session Ingest Transport — Chunked NDJSON over HTTPS POST

## Status

Accepted (SPIKE-resolved 2026-05-10)

## Context

CCDash today exposes only request/response REST surfaces for clients (`/api/v1/`, `/api/agent/`) and a separate **outbound** SSE push surface (`/api/live/stream`) consumed by the frontend (see ADR-001). It has no inbound streaming-ingest endpoint. To enable a remote CCDash deployment that accepts session events from a developer's local daemon (see design-spec `remote-ccdash-streaming.md`), v1 needs a transport that is:

1. Operationally simple (no proxy/firewall surprises, no long-lived connection state on the server).
2. Cheap on the server when N daemons are idle.
3. Has a mature client library in both Python and Go (the daemon's two candidate languages — see ADR-015).
4. Symmetric in shape with the **outbound** telemetry exporter pattern that already ships in `backend/services/integrations/telemetry_exporter.py` (worker pushes batches outbound via `SAMTelemetryClient` with up to 10 retries) — inverting that shape (server accepts inbound batches) reuses operational mental model.

Four options were evaluated.

## Decision

**Use chunked NDJSON over HTTPS POST as the ingest transport for v1.**

Endpoint: `POST /api/v1/ingest/sessions`
- Body: NDJSON (one JSON-encoded `IngestSessionEvent` per line); `Content-Type: application/x-ndjson`.
- Server reads the request body as a stream and processes events line-by-line as they arrive (chunked transfer encoding). The daemon may flush each batch as a single chunked POST or open a long-running POST and stream lines in until it chooses to close.
- Response: structured JSON acknowledging accepted / rejected / dead-lettered counts plus per-event status when partial failures occur. Status code is `200` for fully accepted, `207`-equivalent JSON envelope for partial acceptance, `4xx` for malformed batch, `5xx` for server error.
- Idempotency: every event carries a daemon-generated `event_id` (UUID v7 recommended for monotonic ordering) plus a `batch_id`. The server deduplicates on `(workspace_id, event_id)` via the `ingest_cursors` row plus an `ingest_dedup_recent` LRU keyed by `event_id`.

## Decision Drivers

1. **Reuses existing HTTP stack** — no new server runtime, no socket lifecycle, no new auth surface. Auth is a Bearer header per workspace (see ADR-008), which already plugs into `backend/adapters/auth/bearer.py`.
2. **Stateless on the server** — every request stands alone; no per-client subscription state. Survives restarts, rolling deploys, and load-balancer reshuffles without resync.
3. **Symmetric with the existing outbound telemetry pattern** — `SAMTelemetryClient` already pushes batched JSON outbound with retries; a reversed shape on the server is conceptually obvious to operators.
4. **Cache-friendly + proxy-friendly** — chunked POST is fully supported by every reverse proxy (Nginx, Caddy, ALB, GFE) without buffering quirks, sticky sessions, or `proxy_buffering off` tuning.
5. **Mature client libraries in both languages** — `httpx` (Python) and `net/http` (Go stdlib) both speak chunked POST natively; no third-party dependency.
6. **No backpressure invisibility** — the client receives an HTTP status per batch; server can return `429` to throttle without socket games.
7. **Latency is acceptable for v1** — 5–30s flush interval is the v1 target ("near-live", explicitly not sub-second; see design-spec §7 Non-Goals).

## Decision Matrix

Scored 1 (worst) to 5 (best). Weights reflect what matters for CCDash's local-first product context.

| Criterion (weight) | NDJSON POST (chunked) | SSE | WebSocket | gRPC |
|---|---|---|---|---|
| Operational simplicity (×3) | **5** | 3 | 2 | 2 |
| Server statelessness (×2) | **5** | 3 | 2 | 3 |
| Proxy/firewall friendliness (×2) | **5** | 4 | 3 | 2 |
| Backpressure signaling (×1) | 4 | 3 | 4 | **5** |
| Client lib maturity (Python+Go) (×2) | **5** | 4 | 4 | 4 |
| Symmetry w/ existing telemetry exporter (×1) | **5** | 2 | 2 | 2 |
| Latency for v1 target (×1) | 4 | 5 | **5** | **5** |
| Reconnect/retry simplicity (×2) | **5** | 4 | 3 | 4 |
| **Weighted total** | **64** | 47 | 41 | 42 |

NDJSON POST wins decisively on the criteria CCDash actually cares about (operational simplicity, server statelessness, proxy compatibility, symmetry). SSE is strictly inferior for **inbound** ingest because EventSource is one-way server→client. WebSocket and gRPC trade per-message latency improvements for substantial new infrastructure (socket auth, backpressure plumbing, proto schema management) that v1 explicitly does not need.

## Alternatives Considered

1. **SSE (server-sent events).** Already used outbound (`/api/live/stream`, ADR-001). For inbound this would mean the **server** subscribes to a daemon-hosted SSE feed — inverting the topology and requiring every workstation to expose an HTTP endpoint to the server. Operationally a non-starter for laptops behind NAT and intermittent VPNs.
2. **WebSocket.** Bidirectional, low per-message overhead. Costs: per-socket auth (every reconnect), explicit reconnect/replay logic, server-side socket-state lifecycle, and reverse-proxy quirks (idle-timeout reaping). Worth revisiting **only** if a future requirement demands sub-second push (Alt-C in the design-spec).
3. **gRPC bidi-stream.** Excellent backpressure (HTTP/2 flow control) and schema enforcement (proto). Costs: proto schema management, tooling burden, less laptop-firewall friendly, and disproportionate operational complexity for a 5–30s flush cadence. Revisit if v2 needs per-event sub-100ms latency or strong typed-schema evolution guarantees.
4. **Single-shot JSON POST per batch (non-chunked).** Simpler client code, but caps batch size at the proxy's body limit (~1–10MB) and prevents incremental processing. Chunked NDJSON is strictly more flexible at zero implementation cost.

## Consequences

### Positive

- Zero new server-side connection state. Existing FastAPI request lifecycle handles everything.
- Existing bearer auth (`backend/adapters/auth/bearer.py:74-109`) extends to this endpoint by adding workspace-scoped tokens (ADR-008); no new auth code path.
- Operators already understand the failure modes from the outbound telemetry exporter — same retries, same status codes.
- The endpoint is fully testable with `httpx` in `backend/tests/` without additional fixtures.

### Negative

- The server cannot push to a daemon. Daemon-side commands (e.g., "rotate token", "backfill range") require a separate poll-mode endpoint (`GET /api/v1/ingest/control/{daemon_id}`) — out of scope for v1.
- p99 ingest latency is bounded by daemon flush interval (5–30s configurable). Not suitable for live-transcript UX (explicitly out of scope for v1).
- Without a long-lived connection, the daemon cannot detect server unreachability instantly; it discovers it on the next batch attempt.

### Risks

| Risk | Mitigation |
|---|---|
| Duplicate events on retry-after-partial-success | Idempotency: `(workspace_id, event_id)` upsert with conflict-update; server-side dedup LRU sized to flush_interval × peak_throughput |
| Unbounded request body / OOM | Hard limit max-events-per-batch (recommend 500) enforced server-side; reject `413` for batches over limit |
| Schema skew between daemon release N and server N−1 | Endpoint versioned at `/v1/`; events carry `schema_version`; unknown fields are warn-and-continue (forward-compat); breaking changes require new endpoint version |
| Backpressure invisibility (server slow-but-accepting → daemon buffers forever) | Daemon enforces local disk buffer cap (recommend 500MB) and back-off based on `429`; server returns `429` with `Retry-After` when behind |

## Performance Targets (Hard Gates from E1)

The implementation must meet these targets before v1 ships. They are not measured in this SPIKE; they are the floor that downstream load testing (Phase 3 of the implementation plan) must validate.

| Metric | Target | Rationale |
|---|---|---|
| Sustained ingest throughput | ≥ 500 events/sec on a single `worker` process | Covers a team of ~20 active developers at conservative 25 events/sec/person |
| p99 latency per batch (100-event batches) | < 200ms | Daemon flush latency must be dominated by network + flush interval, not server work |
| Reconnect after forced TCP reset | Daemon resumes within 5s of network restore | Per design-spec §8 (Risks) and grounding brief retry pattern |
| Memory high-water-mark on server (10 concurrent daemons, 500 evt/s each) | ≤ 2× single-daemon-idle baseline | Validates streaming parse path; if heap grows linearly w/ batch size, the parse path is buffering instead of streaming |

If E1 implementation misses any target, **revisit this ADR** before unblocking Phase 3. The most likely re-evaluation outcome would be (a) introducing batch size caps and parallel ingest workers, not (b) switching transports.

## Related

- Design spec: `docs/project_plans/design-specs/remote-ccdash-streaming.md` §4.3
- SPIKE findings: `docs/project_plans/SPIKEs/remote-ccdash-streaming.md`
- ADR-001 (outbound SSE for VSCode extension) — establishes that CCDash uses SSE *outbound*; this ADR keeps the **inbound** path on plain HTTP for symmetry with the telemetry exporter
- ADR-015 (daemon packaging)
- ADR-008 (workspace auth)
- ADR-009 (sync engine port)
- Telemetry exporter precedent: `backend/services/integrations/telemetry_exporter.py`, `backend/services/integrations/sam_telemetry_client.py:25`
