---
title: "External API & LAN Deployment Guide"
description: "Configure CCDash /api/v1 for IntentTree and LAN agent access"
category: guides
tags: [api, lan, intenttree, cors, auth, deployment]
updated: 2026-06-11
---

# External API & LAN Deployment Guide

This guide covers exposing the CCDash `/api/v1` surface to IntentTree agents and
other LAN clients.  The surface is built for local-first, local-trust deployments;
security controls are opt-in additive layers.

> **Architecture reference**: `CLAUDE.md` §Architecture for the overall stack.
> This guide covers only the operator-facing configuration for external access.

---

## Capability discovery

All agents MUST call `GET /api/v1/capabilities` before using capability-dependent
endpoints.  The server returns a `CapabilityV1` payload:

```json
{
  "status": "ok",
  "data": {
    "api_version": "1",
    "capabilities": ["sessions:cross-project", "sessions:detail", "research-runs:*"],
    "instance_id": "ccdash-local",
    "server_time": "2026-06-11T12:00:00Z"
  },
  "meta": { ... }
}
```

| Capability | Meaning |
|---|---|
| `sessions:cross-project` | List/search/detail/transcript accept an explicit `project_id`; detail + transcript REQUIRE it (HTTP 400 if absent — no active-project fallback). |
| `sessions:detail` | Full transcript-bearing bundle available at `/sessions/{id}/detail`. |
| `research-runs:*` | Research Foundry run telemetry ingest (`POST /api/v1/ingest/rf-events`); wildcard placeholder — the eventual query surface lands in a later phase. |
| `intent-nodes:cost` | IntentTree node ↔ session cost attribution: `POST /intent-nodes/{id}/sessions` declares bindings, `GET /intent-nodes/{id}/cost` rolls up token/cost totals. |
| `sessions:tool-calls` | `GET /sessions/{id}/tool-calls` makes `session_logs` rows reachable over HTTP without direct postgres access. |

**Consumer rule**: treat an unknown capability string as a future addition — do
NOT error on strings you don't recognise.  `api_version` is a string; a mismatch
should warn but not hard-fail.

---

## Server bind (`CCDASH_HOST` / `CCDASH_PORT`)

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_HOST` | `0.0.0.0` | Bind address.  `0.0.0.0` accepts connections from all interfaces (LAN-permissive default). |
| `CCDASH_PORT` | `8000` | Listening port. |

The defaults allow any machine on the same network to reach CCDash.  No change
is needed for LAN access when the host is already listening on `0.0.0.0`.

---

## CORS origins (`CCDASH_CORS_ALLOWED_ORIGINS`)

By default, CCDash allows CORS from `CCDASH_FRONTEND_ORIGIN`
(`http://localhost:3000`) and, in the `local` runtime profile, the two dev
localhost origins.  This is permissive enough for local browser UIs.

To allow browser-based UIs from other LAN hosts, set:

```dotenv
# Comma-separated list of additional allowed CORS origins.
# Merged with CCDASH_FRONTEND_ORIGIN; no existing deployment is affected when absent.
CCDASH_CORS_ALLOWED_ORIGINS=http://192.168.1.100:3000,http://mylan.local:3000
```

- Unset (default) → only existing `FRONTEND_ORIGIN` + dev-localhost origins.
- Python/CLI agents calling the API directly (non-browser) are unaffected by CORS.

---

## Bearer auth (`CCDASH_API_TOKEN`)

CCDash is designed for local-trust deployments.  Auth on `/api/v1` is opt-in.

| Variable | Default | Behaviour |
|---|---|---|
| `CCDASH_API_TOKEN` | (empty) | **No auth** — all `/api/v1` requests are allowed without a token (local-trust default). |
| `CCDASH_API_TOKEN=my-secret` | set | Every `/api/v1` request must include `Authorization: Bearer my-secret`; missing → **HTTP 401**; wrong → **HTTP 403**. |

### Setting the token

```dotenv
# .env (or export in your shell)
CCDASH_API_TOKEN=my-secret-token
```

### Calling with the token

```bash
curl http://192.168.1.50:8000/api/v1/capabilities \
  -H "Authorization: Bearer my-secret-token"
```

### Error responses

All auth errors use the standard `detail` field:

```json
{ "detail": "Bearer token required for /api/v1 requests." }   // 401
{ "detail": "Bearer token rejected for /api/v1 request." }    // 403
```

### Relationship to hosted-API auth

`CCDASH_API_TOKEN` is **separate** from the hosted-API `CCDASH_API_BEARER_TOKEN`
/ `static_bearer` provider (which applies only to `runtime_profile=api`).  The
two mechanisms coexist independently.

**Forward-compat (ADR-008)**: all auth for `/api/v1` is resolved in a single
injectable `Depends` function (`backend/routers/_client_v1_auth.py:require_v1_auth`).
A future workspace-scoped resolver replaces that function without touching any
handler body.

### Operator note — containerised deployments (compose env allowlists)

Every CCDash compose stack (`docker-compose.yml` at the repo root and
`deploy/runtime/compose.yaml`, the file the agentic node actually deploys)
declares an **explicit environment allowlist** per service, not a passthrough
of the host environment. A variable set only in the host shell, `.env`, or an
`--env-file` — but not listed as a key in the compose file's `environment:`
map for that service — **never reaches the container namespace**, no matter
how it is set outside the container. For `CCDASH_API_TOKEN` specifically this
means: the var must be present as a key (even with an empty default, e.g.
`CCDASH_API_TOKEN: "${CCDASH_API_TOKEN:-}"`) on every service that mounts
`client_v1_router` — currently the `local`/`backend` and `api` runtime
profiles only; `worker`/`worker-watch` never serve `/api/v1` and do not need
the key. If it is missing from the allowlist, setting `CCDASH_API_TOKEN` on
the host is a **silent no-op**: `require_v1_auth` stays in its no-op branch
and `/api/v1` stays reachable with no credential, with no error or log line
to indicate why.

Also note: a `git reset`/`git pull` followed by a plain container **restart**
runs the **stale, already-built image** — `docker compose up -d` (or the
podman equivalent) reuses the existing image layer and does not pick up
source changes. Any change to `backend/` or to the compose files themselves
requires a **rebuild** (`docker compose build` / `up -d --build`) before the
new behaviour takes effect on a running deployment.

---

## Cross-project session access

The `/sessions/{id}/detail` and `/sessions/{id}/transcript` endpoints are the
cross-project surface.  `project_id` is **required** (HTTP 400 if absent):

```bash
# ✓ correct
GET /api/v1/sessions/{id}/detail?project_id=my-project-uuid

# ✗ returns HTTP 400
GET /api/v1/sessions/{id}/detail
```

There is NO active-project fallback.  This is by design — cross-project reads
must be explicit so agents cannot accidentally read the wrong project's data.

Redacted fields: the Phase 1 redaction layer scrubs secrets before serialisation.
`redactedFieldCount > 0` is a contract state, not a bug.  Consumers must handle
missing/null fields gracefully.

---

## IntentTree node ↔ session cost attribution (`intent-nodes:cost`)

Joins a completed IntentTree node to its session token/cost totals purely by
query — no manual correlation, no schema migration.  The binding is stored as
an `entity_links` row (`source_type='intent_node'`, `origin='declared'`); the
rollup sums `tokens_in`/`tokens_out`/`total_cost` from `sessions`.

**1. Declare which sessions belong to a node** (idempotent — re-declaring the
same node/session pair updates the existing binding, never duplicates it):

```bash
curl -X POST http://<host>:8000/api/v1/intent-nodes/<node-id>/sessions \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<project-id>", "session_ids": ["<session-id-1>", "<session-id-2>"]}'
```

**2. Read the cost rollup:**

```bash
GET /api/v1/intent-nodes/<node-id>/cost?project_id=<project-id>
GET /api/v1/intent-nodes/<node-id>/cost?project_id=<project-id>&expand_family=true
```

`project_id` is **required** (HTTP 400 if absent).  A node with no declared
bindings returns the explicit zero-workload response
(`totals.sessionCount == 0`), never a 404 — "not yet attributed" is a valid
state.

`attributionScope` in the response tells you which claim you're looking at:

| Scope | `expand_family` | Meaning |
|---|---|---|
| `"declared"` | `false` (default) | EXACT — only the sessions explicitly bound via step 1. |
| `"family"` | `true` | WIDENED — every session sharing a declared session's `workflow_id` within the project (e.g. subagent children of the same orchestrator run) is folded in too. |

The caller owns the decision to trust the wider `"family"` claim — the server
never silently widens the default.

---

## Tool-call `session_logs` access (`sessions:tool-calls`)

`GET /sessions/{id}/tool-calls` makes `session_logs` rows reachable by an
external script over HTTP, without direct postgres access:

```bash
GET /api/v1/sessions/<session-id>/tool-calls?project_id=<project-id>
GET /api/v1/sessions/<session-id>/tool-calls?project_id=<project-id>&tool=Bash
```

`project_id` is **required** (HTTP 400 if absent) — same cross-project
convention as `/transcript`.  `items` is narrowed to log entries carrying a
non-empty `toolCall.name`, and further narrowed to an exact `toolCall.name`
match when `tool` is supplied.  Uses the same `{items, cursor, limit,
nextCursor}` cursor-pagination envelope as `/transcript`; redaction is applied
identically.  A page may legitimately contain fewer than `limit` items even
when more raw log rows remain downstream (the tool-call filter is applied
after a raw page is fetched) — keep following `nextCursor` until it is `null`.

---

## OpenAPI specification

A pre-generated OpenAPI v3.1 specification for the `/api/v1` surface lives at:

```
docs/openapi/ccdash-v1.json
```

To regenerate (e.g. after adding a new endpoint):

```bash
backend/.venv/bin/python scripts/regen-openapi-v1.py
```

Commit the updated file alongside your code change.

---

## Example client

A working example client lives at `examples/intenttree-client/client.py`.

```bash
# Dry run (no server needed):
python examples/intenttree-client/client.py --dry

# Live:
python examples/intenttree-client/client.py \
    --base-url http://192.168.1.50:8000 \
    --project-id <project-id> \
    --token <token-if-set>
```

---

## Quick-start checklist for LAN deployment

1. CCDash is running: `npm run dev:backend` (or uvicorn in production).
2. Host is bound to `0.0.0.0` (default) — reachable from LAN.
3. Optionally set `CCDASH_CORS_ALLOWED_ORIGINS` if browser UIs need cross-origin access.
4. Optionally set `CCDASH_API_TOKEN` for a simple shared bearer-token gate.
5. Agents call `GET /api/v1/capabilities` first; feature-detect before using endpoints.
6. Detail/transcript calls always include `?project_id=<id>`.
