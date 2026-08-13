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

### Operator note — minting a workspace token inside the api container

`ccdash token mint` is the single supported provisioning path (ADR-008;
`backend/application/services/auth/token_provisioning.py`). In a containerised
deployment the token must be minted **in the container that holds the Postgres
connection**, and the invocation there is **not** the bare `ccdash` script:

```bash
# Reachable route (verified on rocket-fedora against the node's Postgres, 2026-08-13).
# CCDASH_AUTH_TOKEN is NOT part of the compose env allowlist, so pass it explicitly;
# source it from a 0600 file rather than typing the secret on the command line.
set -a; . ~/.config/aos/secrets.env; set +a
podman exec -e CCDASH_AUTH_TOKEN="$CCDASH_TOKEN" ccdash_api_1 \
    python -m backend.cli token mint --project <project-id>
```

Two details make the obvious invocations fail, both **silently**:

- **`ccdash` is not on `PATH` inside the image.** `pyproject.toml` declares the
  console script (`ccdash = "backend.cli.main:app"`), but the runtime image
  **copies** `backend/` in rather than `pip install`ing the project, so the
  entry point is never generated. `which ccdash` → not found. `typer` itself
  **is** present (it is in `backend/requirements.txt`; measured 0.27.1 in
  `ccdash_api_1`) — a `ModuleNotFoundError: No module named 'typer'` therefore
  means the image predates that requirement and needs a **rebuild**, not that
  the CLI is unavailable in containers.
- **`python -m backend.cli.main` used to exit 0 printing nothing.** The module
  had no `if __name__ == "__main__"` guard, so `-m` imported it, registered every
  sub-app, and exited successfully having done nothing — indistinguishable from
  success. The guard is now present, so `python -m backend.cli.main` and
  `python -m backend.cli` are equivalent. On an image built before that fix, use
  `python -m backend.cli`.

Verified behaviour of the reachable route against the node's Postgres:

```
SUCCESS: minted token_id=<uuid>      # first run — writes one workspace_tokens row
NO-OP: token already present as token_id=<uuid>   # re-run, same plaintext — writes nothing
```

**Host-venv alternative** (equally supported, for work done from a checkout
rather than inside the container) — repoint the DSN at the published Postgres
port and use the repo venv, which does have the console script installed:

```bash
CCDASH_DB_BACKEND=postgres \
CCDASH_DATABASE_URL=postgresql+asyncpg://<user>:<pw>@127.0.0.1:5440/ccdash \
backend/.venv/bin/ccdash token mint --project <project-id>
```

Provisioning **never runs migrations** — it asserts the schema is present and
aborts with an actionable error if `workspace_tokens` is missing. Bring the
schema up by starting the `api`/`worker` runtime once before minting.

---

## Hosted LLM egress consent (`CCDASH_LLM_EGRESS_CONSENT`)

CCDash has **two** hosted-LLM egress lanes, and both are gated by the **same
two-level consent model** — both levels must be true, or nothing egresses:

1. **Deployment-wide switch** — `CCDASH_LLM_EGRESS_CONSENT` (env var).
   Defaults `false`; fail-closed. Setting it `true` merely *permits* the
   hosted/anthropic backends to be constructed at all — it does not, by
   itself, cause anything to be sent off-box.
2. **Per-project switch** — the `projects.llm_egress_consent` DB column.
   A project defaults to no consent; an operator must explicitly opt that
   project in (see *Granting the per-project half* below).

Both gates are independent and additive — `CCDASH_LLM_EGRESS_CONSENT=true`
with a project's `llm_egress_consent` left `false` (the default) egresses
nothing for that project on either lane.

### Per-lane consent shape

There is **no per-lane exception**: every hosted-LLM egress path requires both
dimensions. The lanes differ only in *where* the project comes from and in what
happens when there isn't one.

| Lane | Global flag | Per-project flag | Project comes from | No project available |
|---|---|---|---|---|
| Derived-session-naming sweep (Lane B / anthropic-ICA) | required | required | the registry fan-out — one project per unit of work | n/a; the sweep always has a project row, and re-reads consent **every tick** |
| Dashboard insight (`POST /api/ai/insight`) | required | required | `project_id` on the request body (the FE sends `activeProject.id`) | **REFUSED** — returns the `disabled` contract state |

The insight lane's refusal on a missing `project_id` is a **decision, not a
default**: falling back to the global flag alone was considered and rejected,
because it would restore a one-dimension egress path through a side door. With
no project selected the dashboard has no project-scoped data to summarise
anyway, so nothing is lost. Refusal covers every case where consent cannot be
*confirmed* — absent `project_id`, unknown project, or an unreadable registry —
and is always the route's normal `200` + `disabled`, never a `404` or a `500`,
so a caller that only checks the `disabled` flag still behaves correctly.

### Granting the per-project half

A brand-new project is registered with `llm_egress_consent` **false** — there
is no inheritance from any other project and no "default on" path.  Granting it
is an explicit write:

```bash
# grant (per-project half only — the env flag is still independently required)
ccdash-cli project consent <project-id> --grant

# revoke
ccdash-cli project consent <project-id> --revoke
```

Exactly one of `--grant` / `--revoke` is required; passing both or neither is a
usage error (exit 2) rather than a silent default.  On `--grant` the CLI prints
a reminder that `CCDASH_LLM_EGRESS_CONSENT` must also be true.

The transport-neutral equivalent — for agents, scripts, and any non-CLI caller:

```bash
curl -sS -X POST "http://<host>:8000/api/projects/<project-id>/egress-consent" \
  -H 'Content-Type: application/json' \
  -d '{"granted": true}'
```

The request body carries the single required boolean `granted`.  The response is
the full updated `Project` object (HTTP 200), or HTTP 404 when the project id is
unknown.  Read the current state back off any project payload — the field is
`llm_egress_consent` on the `Project` model:

```bash
# every project's current state (reads only — no write involved)
curl -sS "http://<host>:8000/api/projects" \
  | jq -r '.[] | "\(.id)\t\(.name)\t\(.llm_egress_consent)"'
```

`ccdash-cli project list` also works for read-back. It previously crashed on any
array-returning endpoint (`AttributeError: 'list' object has no attribute 'get'`
in the shared client's envelope unwrap, in both human and `--output json` modes);
that was a pre-existing client bug unrelated to the consent surface, fixed in
`3558bea` (`node_01KZRSSP4MM8V8FTT7KPST56A1`, closed). If you are running a build
older than that commit, prefer the REST form above.

`ccdash-cli project consent ... --json` also emits the full updated project, so
a grant/revoke can be verified in the same call that performs it — but prefer the
REST read-back above when you only want to *read* the current state.

Operationally fail-closed facts worth restating:

- A brand-new project **always** defaults to no consent; registration never
  grants it.
- **Both** levels are required.  Granting the per-project half on a deployment
  where `CCDASH_LLM_EGRESS_CONSENT` is unset (or false) changes nothing
  observable — that project's sessions still go through the local, zero-egress
  naming backend.
- **Revoking either level stops egress.**  `--revoke` on the project, or
  flipping the env flag off (plus the restart/rebuild the compose allowlist note
  below requires), is sufficient on its own.
- The per-project flag is re-read **every sweep tick** inside
  `SessionNamingSweepJob`'s fan-out loop, so a revoke takes effect on the next
  tick without a restart.  The env flag is read at construction time and does
  need a restart.
- On the **insight lane** the per-project flag is read **per request**, so a
  revoke takes effect on the very next call — no tick to wait for, no restart.
- Granting the per-project half enables *both* lanes for that project. There is
  no way to consent to the sweep but not the dashboard insight (or vice versa);
  consent is per-project, not per-project-per-lane. If you need that split,
  treat it as a contract change rather than assuming the column already carries
  it.

### Same compose-allowlist gap as `CCDASH_API_TOKEN`

Both `CCDASH_LLM_EGRESS_CONSENT` and the anthropic-lane credential vars
(`CCDASH_LLM_SESSION_NAMING_LANE`, `CCDASH_LLM_ANTHROPIC_BASE_URL`,
`CCDASH_LLM_ANTHROPIC_API_KEY`, `CCDASH_LLM_ANTHROPIC_MODEL`,
`CCDASH_LLM_GEMINI_API_KEY`) are subject to the **exact same explicit-allowlist
gap** described above for `CCDASH_API_TOKEN`: setting any of them in the host
shell, `.env`, or an `--env-file` is a silent no-op unless the var is also
listed as a key in the compose stack's `environment:` map for the service
that needs it (`docker-compose.yml`'s `x-shared-backend-env` anchor, or
`deploy/runtime/compose.yaml`'s `x-backend-service` → `environment:
&backend-shared-env` anchor — the file the agentic node deploys). Both
files already carry all six keys with defaults mirroring
`backend/config.py` exactly. `CCDASH_LLM_ANTHROPIC_MODEL` deliberately has
**no default anywhere** (env, compose, or `backend/config.py`) — empty means
the anthropic naming lane is unreachable at derive-time; do not add one.
`CCDASH_LLM_ANTHROPIC_BASE_URL` defaults to ICA
(`https://api.nextgen-beta.ica.ibm.com/ica`) per ADR-017 — the trust
boundary is already crossed and ICA's free tier makes a systematic sweep
affordable. Explicitly pointing this var at `https://api.anthropic.com`
selects the **paid** Anthropic-direct lane instead; that is an intentional
opt-in, not something to do "helpfully".

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
