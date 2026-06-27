---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: product_prd
status: draft
category: integrations
title: "PRD: IntentTree Session Correlation API v1"
description: "Add a programmatic session-registration and correlation API so external orchestrators (IntentTree) can pre-declare a dispatched task, have CCDash bind the matching transcript on ingest, and pull or receive session metrics keyed by the external reference — eliminating the current manual paste-the-sessionId step."
summary: "CCDash has no inbound session-registration surface today; sessions are discovered by filesystem ingestion and keyed by the platform-assigned sessionId, which is not known until the transcript file exists. This enhancement adds a lightweight correlation table, a POST /api/correlations/register handshake endpoint, a sync-engine binding hook that matches a pending registration to a newly-ingested session, and a GET /api/correlations/{external_ref}/session proxy so any caller can fetch metrics without knowing the platform sessionId. An optional webhook/push notification replaces polling."
author: claude-sonnet-4-6
created: 2026-06-03
updated: 2026-06-03
priority: high
risk_level: low
complexity: medium
track: Integrations
timeline_estimate: "2-3 weeks across 3 phases"
feature_slug: intenttree-session-correlation-v1
feature_family: intenttree-integration
feature_version: v1
lineage_family: intenttree-integration
lineage_parent:
  ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  kind: sibling
lineage_children: []
lineage_type: integration
problem_statement: "IntentTree dispatches agent tasks to external harnesses (Claude Code, Codex) and needs to pull session metrics from CCDash once the run completes. CCDash only exposes sessions by platform sessionId, which is not known at dispatch time. The current workaround is a manual user action: paste the sessionId into IntentTree after the transcript exists. This creates friction in the dispatch workflow and cannot be automated."
owner: platform-engineering
owners: [platform-engineering, backend-platform]
contributors: [ai-agents]
tags: [prd, integration, intenttree, correlation, session-registration, webhook, dispatch]
related_documents:
  - docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  - docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
context_files:
  - backend/db/sync_engine.py
  - backend/db/repositories/sessions.py
  - backend/routers/api.py
  - backend/routers/cache.py
  - backend/models.py
  - backend/config.py
  - backend/db/migrations.py
implementation_plan_ref: null
---

# PRD: IntentTree Session Correlation API v1

## Executive Summary

IntentTree v1 introduces a dispatch harness that synthesizes an agent task prompt and lets the user run it in Claude Code or another external harness. Post-dispatch, IntentTree wants to pull CCDash session metrics (tokens, cost, tool calls, duration, outcome) to attach to the agent run record — providing mission-control-level observability. Today this requires the user to paste a sessionId into IntentTree by hand, because CCDash sessions are keyed by the platform-generated `sessionId` that only exists after the transcript file appears on disk.

This PRD specifies the minimal CCDash changes needed to break that chicken-and-egg dependency:

1. A **session-registration handshake endpoint** (`POST /api/correlations/register`) that lets IntentTree pre-declare a pending dispatch using an opaque external reference (`external_ref`) plus context that helps CCDash identify the matching transcript.
2. A **sync-engine binding hook** that, on ingesting a new session, checks pending registrations and binds any match, persisting the `external_ref → sessionId` mapping.
3. A **lookup proxy** (`GET /api/correlations/{external_ref}/session`) that returns the bound session (or 404 if not yet matched), allowing IntentTree to poll without knowing the platform sessionId.
4. An optional **webhook/push notification** from CCDash to IntentTree once a bound session is updated, replacing polling for callers that can receive HTTP callbacks.

The `linked-features` endpoint (`POST /api/sessions/{id}/linked-features`) is NOT replaced; it remains the existing feature-linking surface. The correlation API is a parallel external-ref mechanism with different semantics: it is declared before the session exists, and the key is provided by the external caller.

Priority: HIGH (blocks IntentTree M1 CCDash seam from being fully programmatic).

---

## Problem Statement

### Chicken-and-egg

CCDash's ingestion model is filesystem-driven. A session enters the system when the file-watcher or sync engine parses `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl`. The `sessionId` is assigned by the Claude Code platform when the session starts, so it does not exist at the moment IntentTree dispatches the task. Concretely:

- **t=0**: IntentTree sends a prompt to the user (copy/paste) or to the CLI. `sessionId` is unknown.
- **t=5s**: Claude Code starts, assigns a `sessionId`, writes the first JSONL record.
- **t=N**: The session ends. The transcript is fully written. CCDash ingests it.
- **t=N+?**: The user manually discovers the `sessionId` (from the transcript path or the CCDash session list) and pastes it into IntentTree's link-session field.

IntentTree cannot call `GET /api/sessions/{sessionId}` until step t=N+? because it does not know the identifier.

### Why existing surfaces are insufficient

- `GET /api/sessions` supports filters but not filtering by "this session was started from cwd X within time window W by platform P" in a way reliable enough to automatically claim a single result without race conditions.
- `POST /api/sessions/{id}/linked-features` requires the sessionId to already be known.
- `GET /api/live/stream` (SSE) notifies subscribers of session updates, but IntentTree would need a persistent SSE connection open and would still need to disambiguate which session belongs to which dispatch.

---

## Proposed API

### 3.1 Registration endpoint

```
POST /api/correlations/register
Content-Type: application/json

{
  "external_ref":       "run_01J...",       // opaque; provided by IntentTree; must be unique
  "cwd":                "/Users/me/myrepo", // absolute cwd of the dispatched agent process
  "expected_platform":  "claude_code",      // "claude_code" | "codex" | "generic" (optional, default "claude_code")
  "dispatched_at":      "2026-06-03T10:00:00Z", // ISO-8601 UTC; defines the time window for session matching
  "handshake_token":    "tok_abc123",       // optional; embedded in the dispatch prompt (see §4)
  "ttl_seconds":        3600,               // how long CCDash should hold this pending registration (default 3600)
  "webhook_url":        "http://localhost:8080/api/internal/ccdash-notify", // optional; CCDash calls this on bind
  "metadata":           { "node_id": "node_xyz", "workspace_id": "ws_1" }   // arbitrary; returned on lookup
}

Response 202 Accepted:
{
  "status": "pending",
  "external_ref": "run_01J...",
  "correlation_id": "corr_...",   // CCDash-internal ID
  "expires_at": "2026-06-03T11:00:00Z"
}
```

- **Idempotent on `external_ref`**: re-posting the same `external_ref` updates `dispatched_at`, `ttl_seconds`, and `webhook_url` and returns 200 if the registration is already pending; returns 409 if already bound.
- **No auth required** in local profile (`CCDASH_CORRELATIONS_AUTH_REQUIRED=false` default). Hosted profile: validates `Authorization: Bearer <CCDASH_API_KEY>` (same as the existing per-router `require_http_authorization` gate).

### 3.2 Lookup proxy

```
GET /api/correlations/{external_ref}/session
  ?include_logs=false   // optional; forward to GET /api/sessions/{id}

Response 200: full AgentSession JSON (same shape as GET /api/sessions/{id})
Response 202: { "status": "pending", "external_ref": "...", "message": "session not yet bound" }
Response 404: { "status": "not_found", "external_ref": "..." }  // expired or unknown ref
```

- `202` is the "still waiting" state; `404` means the registration never existed or expired.
- The `include_logs` parameter proxies through to the session endpoint.

### 3.3 Correlation status

```
GET /api/correlations/{external_ref}

Response 200:
{
  "status": "pending" | "bound" | "expired",
  "external_ref": "run_01J...",
  "session_id": "abc123" | null,     // null if pending
  "bound_at": "..." | null,
  "dispatched_at": "...",
  "expires_at": "...",
  "metadata": { ... }
}
```

### 3.4 Webhook push (optional)

When a registration has a `webhook_url` and CCDash binds the session (at ingest time), CCDash fires a best-effort HTTP POST:

```
POST {webhook_url}
Content-Type: application/json

{
  "event": "session.bound",
  "external_ref": "run_01J...",
  "session_id": "abc123",
  "bound_at": "2026-06-03T10:05:00Z"
}
```

Delivery is fire-and-forget with one retry (exponential backoff, max 30s). Failures are logged; they do not affect session ingestion. IntentTree registers the webhook URL in the registration payload. The internal CCDash webhook dispatcher lives in `backend/services/integrations/` alongside the existing telemetry exporter.

---

## Session-Identification Strategy

### Options

**Option A — Handshake token embedded in the dispatch prompt (RECOMMENDED)**

IntentTree generates a unique short token (e.g. `ccdash-htk:tok_abc123`) and appends it to the rendered task prompt. The token is also included in the registration payload as `handshake_token`. When the sync engine ingests a new JSONL file, it scans the first user message (the prompt) for the token pattern. If found, the token matches the pending registration and the session is bound immediately, regardless of timing window or cwd ambiguity.

*Tradeoffs:* adds a one-liner to the user-facing prompt (invisible to the agent; can be embedded in a structured metadata block or a comment). Accurate. No race condition. Requires IntentTree to author the prompt (already planned). Fails if the harness strips injected text.

**Option B — Claim-newest-session-in-cwd-within-window**

On a forced sync trigger (IntentTree calls `POST /api/cache/sync` shortly after dispatch), CCDash queries for the newest session whose `cwd` matches the registration's `cwd` and whose `started_at` falls after `dispatched_at - 30s`. If exactly one candidate exists, it is bound. If zero or multiple, the registration stays pending.

*Tradeoffs:* works without prompt changes. Ambiguous if multiple sessions start in the same cwd within the window (unlikely for single-user local). Requires a brief delay after dispatch before the sync call. Sensitive to clock skew.

**Option C — Env/stdout capture when launcher owns the process**

Applicable only when IntentTree runs the CLI as a subprocess. The CLI emits `session_id` in its JSON output (`claude -p --output-format json`). IntentTree captures it from stdout and calls a `POST /api/correlations/{external_ref}/bind` endpoint directly with the `session_id`. CCDash stores the binding without needing a sync-time scan.

*Tradeoffs:* the cleanest path, but only available in the execution-tier sprint (not the current copy/paste MVP). Out of scope for M1 v1.

### Recommendation

**Implement Option A (handshake token) as the primary strategy; support Option B as the fallback**. The sync engine's ingest hook runs token-match first, then falls back to cwd+window matching if no handshake token is present or if the pattern is not found in the transcript. Option C is a natural follow-on that IntentTree adds when it gains CLI-exec capability — on the CCDash side, the `POST /api/correlations/{external_ref}/bind` endpoint is added in Phase 2 as a stub for future use.

---

## Data-Model and Migration

### New table: `session_correlations`

```sql
CREATE TABLE session_correlations (
    id             TEXT PRIMARY KEY,           -- CCDash-internal correlation ID (ccdash id-gen)
    external_ref   TEXT NOT NULL UNIQUE,       -- caller-supplied opaque key
    project_id     TEXT NOT NULL,              -- from the registered cwd → resolved project
    session_id     TEXT,                       -- NULL until bound; FK to sessions.id (optional)
    status         TEXT NOT NULL DEFAULT 'pending', -- pending | bound | expired
    expected_platform TEXT DEFAULT 'claude_code',
    cwd            TEXT NOT NULL,
    dispatched_at  TEXT NOT NULL,              -- ISO-8601 UTC
    bound_at       TEXT,                       -- ISO-8601 UTC, NULL until bound
    expires_at     TEXT NOT NULL,              -- ISO-8601 UTC
    handshake_token TEXT,                      -- NULL if not provided
    webhook_url    TEXT,                       -- NULL if not provided
    metadata_json  TEXT DEFAULT '{}',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX idx_session_correlations_status ON session_correlations(status);
CREATE INDEX idx_session_correlations_project_dispatched ON session_correlations(project_id, dispatched_at);
CREATE INDEX idx_session_correlations_token ON session_correlations(handshake_token) WHERE handshake_token IS NOT NULL;
CREATE INDEX idx_session_correlations_session ON session_correlations(session_id) WHERE session_id IS NOT NULL;
```

### Migration

Added to the existing SQLite migration runner in `backend/db/sqlite_migrations.py` as a new numbered migration. Postgres equivalent in `backend/db/postgres_migrations.py`. Both are guarded by the standard `IF NOT EXISTS` pattern already in use.

No change to the `sessions` table. The correlation table is a side-index; sessions are unmodified.

### Config additions to `backend/config.py`

| Variable | Default | Purpose |
|---|---|---|
| `CCDASH_CORRELATIONS_ENABLED` | `true` | Feature flag; returns 501 if false |
| `CCDASH_CORRELATIONS_AUTH_REQUIRED` | `false` | Require bearer auth on correlation endpoints |
| `CCDASH_CORRELATIONS_DEFAULT_TTL_SECONDS` | `3600` | Default registration TTL |
| `CCDASH_CORRELATIONS_WEBHOOK_MAX_RETRIES` | `1` | Webhook delivery retry count |
| `CCDASH_CORRELATIONS_WEBHOOK_TIMEOUT_SECONDS` | `10` | Per-webhook attempt timeout |

---

## Implementation Phases

### Phase 1 — Data layer + registration endpoint (5–7 pts)

Deliverables:
- `session_correlations` table migration (SQLite + Postgres).
- `backend/db/repositories/correlations.py` — `CorrelationRepository` with `create`, `get_by_external_ref`, `get_by_session_id`, `list_pending_by_project`, `bind`, `expire`.
- `backend/routers/correlations.py` — `correlations_router` at `/api/correlations`; `POST /register`, `GET /{external_ref}`, `GET /{external_ref}/session`. Wire into `backend/runtime/container.py` and the FastAPI app factory.
- `backend/config.py` — add the five config vars above.
- Tests: `backend/tests/test_correlations_api.py` — register, get-pending, get-expired, 202-while-pending, 200-after-bind; mock binding.

Acceptance criteria:
- `POST /api/correlations/register` → 202 with `correlation_id` and `expires_at`.
- `GET /api/correlations/{external_ref}` returns `status: pending` before any session is bound.
- `GET /api/correlations/{external_ref}/session` returns 202 while pending.
- Re-registering the same `external_ref` while pending → 200 (idempotent update).
- Re-registering after bind → 409.

### Phase 2 — Sync-engine binding hook (5–7 pts)

Deliverables:
- `backend/db/sync_engine.py` — after a session is upserted, call `_try_bind_correlations(project_id, session_payload)`. This method:
  1. Queries `list_pending_by_project(project_id)`.
  2. For each pending registration, checks (a) handshake token match in `session_payload`'s first user message, then (b) cwd match + `started_at` within `[dispatched_at - 30s, dispatched_at + ttl_seconds]`.
  3. On match: calls `correlation_repo.bind(external_ref, session_id)`, fires webhook (fire-and-forget asyncio task).
- `backend/services/integrations/correlation_webhook.py` — lightweight HTTP POST with one retry using `httpx.AsyncClient` (already in the dependency tree via the telemetry exporter).
- `POST /api/correlations/{external_ref}/bind` stub endpoint — accepts `{session_id: str}` directly; validates session exists; calls `bind()`. Intended for future use by the CLI-exec tier (Option C); returns 200 or 409 if already bound.
- Background expiry cleanup: add a scheduled job (reuse `backend/adapters/jobs/` scheduler pattern) that marks expired pending registrations hourly.
- Tests: `backend/tests/test_correlation_binding.py` — token-match binding, cwd+window fallback, no-match, double-bind idempotency, webhook fire-and-forget (mock httpx), expiry cleanup.

Acceptance criteria:
- After `POST /api/correlations/register` and a `POST /api/cache/sync`, a session whose first message contains the handshake token is bound; `GET /api/correlations/{ref}/session` returns 200 with full session JSON.
- cwd+window fallback binds the correct session when no token is present.
- Ambiguous cwd+window (two sessions, same cwd, same window) leaves the registration pending and logs a warning; does not bind either.
- Webhook fires within 5 seconds of bind (integration test with mock server).

### Phase 3 — Docs, config guide, and hardening (2–3 pts)

Deliverables:
- `docs/guides/intenttree-session-correlation.md` — operator guide: how IntentTree registers, how to configure, how to test with curl, webhook payload reference, troubleshooting.
- Frontend: no frontend changes in this PRD. CCDash UI can surface pending/bound correlations in a later enhancement.
- `CHANGELOG.md` entry via `/release:bump`.
- Security review: confirm that `external_ref` cannot be used to read session data belonging to a different project (project-scoping invariant: the registration's `cwd`-derived `project_id` must match the bound session's `project_id`).

---

## Auth

**Local profile** (`CCDASH_CORRELATIONS_AUTH_REQUIRED=false`): correlation endpoints accept all requests without a bearer token — consistent with the rest of the local API.

**Hosted profile** (`CCDASH_CORRELATIONS_AUTH_REQUIRED=true`): all correlation endpoints gate through `require_http_authorization` with action `correlation:register` / `correlation:read`. The webhook delivery adds an `Authorization: Bearer <CCDASH_API_KEY>` header on outbound calls so IntentTree can verify the callback.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Handshake token stripped by harness | Low | cwd+window fallback is always active; token scanning is additive, not required. |
| Clock skew causes cwd+window miss | Low | 30s pre-dispatch buffer; configurable. |
| Multiple sessions in same cwd+window | Low (single-user local) | Leave pending; log warning; user can use `POST /bind` stub manually. |
| Webhook target unreachable | Low | Fire-and-forget with one retry; failure is silent to the session ingest path. |
| Token pattern collides with real prompt content | Very low | Token is `ccdash-htk:<ulid>`; scanning with exact prefix. |

---

## Non-Goals

- No IntentTree-side code is specified here. IntentTree's CCDash client, its metric field migration, and its dispatch UI are separate IntentTree work items (M1 Phase 2 and Phase 3 in the IntentTree plan).
- No CCDash frontend changes. A future enhancement can add a "linked external runs" panel to the session inspector.
- No live SSE subscription management for external callers. Polling `GET /api/correlations/{ref}/session` or the webhook push are the only delivery mechanisms in v1.
- The correlation API does not replace `linked-features`. Both coexist.
- Multi-project correlation (one `external_ref` binding multiple sessions) is out of scope.

---

## Open Questions for the Maintainer

1. **Project resolution from `cwd`**: `project_manager.py` resolves a cwd to a project by matching against `projects.json`. Should `POST /api/correlations/register` fail with 422 if the cwd does not map to a known project, or store the registration pending and attempt project resolution at bind time? Recommendation: resolve at registration time and fail fast (422) so IntentTree knows immediately if the project is not registered.

2. **`external_ref` namespacing**: Should the `external_ref` be namespaced (e.g. `intenttree:run_01J...`) to avoid collisions if other orchestrators use the same API? Recommendation: yes — accept any string, but document a `<caller>:<id>` convention and add a `source_system` field (optional) to the registration for filtering.

3. **Token injection UX**: IntentTree appends the handshake token to the copy/paste prompt block. Should the token be placed in a structured metadata comment (invisible to the agent model) or as a trailing line? If CCDash scans only the first N bytes of the first user message, placement matters.

4. **Webhook auth on IntentTree's side**: IntentTree's internal `ccdash-notify` endpoint needs to validate that callbacks come from CCDash (not arbitrary callers). The plan proposes sending the bearer token on the outbound webhook request. IntentTree maintainers should confirm this is acceptable or prefer a shared-secret HMAC header instead.

5. **Expiry cleanup as a scheduled job vs. inline**: The hourly expiry sweep was proposed as a scheduled job. If the operator runs CCDash in API-only mode (no worker), the sweep will not run. Consider also expiring inline at read time (return 404 / `status: expired` if `expires_at < now`) as a complementary mechanism so clients are not blocked by stale pending registrations.
