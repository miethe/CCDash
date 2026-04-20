---
schema_version: 2
doc_type: report
report_category: finding
title: "Remote CCDash + Entire.io Integration — Grounding Brief"
status: draft
source: agent
created: 2026-04-19
feature_slug: remote-ccdash-streaming
description: "Research brief consolidating CCDash runtime/transport state and Entire.io CLI integration surface. Consumed by design-spec, SPIKE charters, and downstream PRD."
---

# Grounding Brief — Remote CCDash + Entire.io Integration

Two research legs consolidated here for downstream authors (design-spec, SPIKE charters, PRD, impl plan). Treat this as the shared factual base; do not re-derive.

---

## Leg 1 — CCDash Current State (post deployment-runtime-modularization, PR #30, commit 451f958)

### Runtime profiles capability matrix
| Profile | Watch | Sync | Jobs | Auth | StorageProfile | Use |
|---------|-------|------|------|------|----------------|-----|
| `local` | yes | yes | yes | no | `local` | Desktop w/ auto-watch |
| `api` | no | no | no | yes | `enterprise` | Stateless HTTP server |
| `worker` | no | yes | yes | no | `enterprise` | Background ingest only |
| `test` | no | no | no | no | `local` | Test isolation |

- `RuntimeProfile` immutable dataclass: `backend/runtime/profiles.py:7-26`
- `RuntimeContainer.startup()` conditionally composes sync/watcher/scheduler/telemetry: `backend/runtime/container.py:63-117`
- `SyncEngine` gated on `capabilities.sync && storage_profile.filesystem_source_of_truth`: `container.py:169-179`
- File watcher gated on `capabilities.watch`: `backend/adapters/jobs/runtime.py:144-150`, `backend/db/file_watcher.py:30-57`
- `RuntimeJobAdapter` wires into `job_scheduler.schedule()`: `backend/adapters/jobs/runtime.py:78-103`, `backend/runtime/bootstrap.py:35-109`
- Telemetry exporter only on worker: `container.py:111-117`

**Key insight:** Watch and sync are decoupled from HTTP serving. `api` profile scales statelessly already; `worker` handles ingest.

### Sync + parse pipeline (filesystem → DB → API)
1. Parser entry `parse_session_file(path)`: `backend/parsers/sessions.py:11-13` (registry dispatches by ext)
2. Watcher uses `watchfiles`: `backend/db/file_watcher.py:75-100`
3. `SyncEngine._sync_incremental()`: `backend/db/sync_engine.py:1-50`; hashes content, calls parser, computes `_task_storage_id()` `:124-148`, calls repository upsert
4. `SqliteSessionRepository.upsert()`: `backend/db/repositories/sessions.py:17-82` (ON CONFLICT, 52 cols, JSON fields)
5. Response wrapped in `ClientV1PaginatedEnvelope`: served via `backend/routers/client_v1.py:138-149` or `backend/routers/agent.py:72-90`

**Filesystem coupling points (blockers for remote):**
- `sync_engine.py:28-63` reads absolute paths from `config.SESSIONS_DIR`, `config.DOCUMENTS_DIR`
- `file_watcher.py:86-99` watches only paths where `.exists()` locally
- `sync_engine.py:118-121` uses `infer_project_root()` + canonical path transforms — local-filesystem semantics
- `source_file` stored as canonical relative path: `repositories/sessions.py:59` — no analogue for remote events

**Storage abstraction gap:** Repositories are DB-agnostic (SQLite + Postgres); sync engine is **not** storage-agnostic — it couples to filesystem watchers and mtime-based change detection.

### Client transports (3 API surfaces)
1. **`/api/v1/` — standalone CLI endpoint** (`backend/routers/client_v1.py:59`)
   - `GET /instance`, `/project/status`, `/features?status=&limit=200&offset=0&q=`, `/sessions/search?q=`
   - Paginated envelopes, limit 1–200
   - Auth: optional bearer token, path-scoped (`backend/adapters/auth/bearer.py:22,74-109`)
   - **No streaming, no SSE, no WebSocket**
2. **`/api/agent/` — agent query services** (`backend/routers/agent.py:30`)
   - Singletons for project_status / feature_forensics / workflow_diagnostics / reporting / planning (`agent.py:45-50`)
   - Transport-neutral services in `backend/application/services/agent_queries/`
   - Query cache: `agent_queries/cache.py:350` (LRU + TTL)
   - No auth on agent routes (relies on network isolation or bearer guard)
3. **CLI HTTP client** (`packages/ccdash_cli/src/ccdash_cli/runtime/client.py:1-50`)
   - Sync httpx, retry on 502/503/504, default timeout 30s
   - Exit codes: 1=general, 2=auth, 3=forbidden, 4=network, 5=version mismatch
   - No streaming; serial paged GETs
   - Hardcoded `_EXPECTED_API_VERSION="v1"`

### Project model
- `projects.json` at `config.DATA_DIR/projects.json`
- Schema: `{ activeProjectId, projects: [{ id, name, path, description, repoUrl, agentPlatforms, planDocsPath, skillMeat, pathConfig, testConfig }] }`
- Each project binds to **one** local path: `backend/project_manager.py:84`
- Resolver: `ProjectPathResolver` in `services/project_paths/`
- **Scoped per-project:** sessions/documents/progress dirs, test config, features
- **Global:** DB backend, auth, storage profile, runtime profile
- **Project binding is startup-time only:** `container.py:67`, `runtime.py:107-127` (`resolve_project_binding()`) — no runtime switching

### Observability
- `TelemetryExportCoordinator`: `backend/services/integrations/telemetry_exporter.py:54-111`
- Queue: `backend/db/repositories/telemetry_queue.py`
- Health endpoint: `GET /api/health` returns `telemetryExports: "idle|running|failed"` (`bootstrap.py:180`)
- `SAMTelemetryClient` pushes batches to configurable endpoint: `backend/services/integrations/sam_telemetry_client.py:25` (max 10 retries)
- OTEL: `backend/observability/otel.py:298+`; spans tagged by runtime + storage profile; trace propagation via `traceparent`
- **No streaming telemetry — push-only batches**

### Concrete gaps for remote operation
1. **Parser source_file assumptions** (`sync_engine.py:118-121`, `document_linking.py`): canonical_project_path assumes local disk; remote ingest has no `__file__` analogue
2. **Sync engine fs+mtime coupling** (`sync_engine.py:1-7`, `file_watcher.py:30`): `watchfiles` + `_file_hash()` change detection; no cursor/watermark; remote sessions lack file identity
3. **File watcher only watches existing local paths** (`file_watcher.py:94-99`): no abstraction for "source changed" independent of filesystem
4. **Auth is static single-tenant bearer** (`bearer.py:84-104`): one env-var token, shared across clients; `x-ccdash-project-id` is unauthenticated hint; no per-workspace tokens, no OIDC
5. **No streaming transports**: REST pagination only; no NDJSON, SSE, WebSocket, gRPC; frontend polls `/api/health`
6. **Project binding is startup-only** (`container.py:67`): single-project-per-process; multi-tenant remote scenarios need runtime switching / `x-project-id` routing
7. **No resumable-sync state**: sync state implicit in mtime + DB; no explicit cursor/watermark table, no dead-letter queue, no backoff policy
8. **API version is hardcoded literal**: `/api/v1/` string; no negotiation, no forward/back-compat; server and CLI must match exactly

### Synthesis
CCDash is deeply local-first. Decomposing to remote-server + local-daemon requires: de-filesystem-coupling sync engine (cursor/watermark, remote event ingestion), transport-neutral session ingest (HTTP POST/NDJSON/gRPC, strip file-path assumptions), multi-tenant auth (per-workspace tokens, OIDC, RLS), streaming API (SSE/WS for live events), runtime project switching.

---

## Leg 2 — Entire.io Stack & CLI

### Product positioning
Entire.io: Git-integrated platform for capturing + indexing AI agent sessions alongside code commits. "Sessions indexed alongside commits, creating a searchable record of how code was written." $60M seed (Felicis lead). Agent-agnostic — supports Claude Code, Codex, Gemini CLI, Cursor, Copilot CLI.

### CLI repo inventory (github.com/entireio/cli)
- **Language:** Go (98%+)
- **License:** MIT, no CLA
- **Activity:** 3,989 stars, 305 forks, last commit 2026-04-18 (active)
- **Commands:** `enable` (install hooks), `status`, `rewind` (restore checkpoint), `resume <branch>` (context handoff), `configure`
- **Data model:**
  - Sessions: `YYYY-MM-DD-<UUID>`, full lifecycle
  - Checkpoints: 12-char hex IDs (e.g., `a3b2c4d5e6f7`), created on git commits; include transcript, token counts, agent-vs-human line attribution
  - Sharded storage: first-2-chars-of-ID subdirs (avoid fs hotspots)
- **Transport:**
  - **Local-first**, Git-native. No external DB required.
  - Metadata lives on dedicated git branch `entire/checkpoints/v1` as JSON files
  - Shadow branches (`entire/<sessionID>-<worktreeID>`) for active work state
  - Optional cloud: `ENTIRE_API_BASE_URL` env var
  - Merge-conflict-free via random 12-hex checkpoint IDs
  - Commit trailers link sessions to code (e.g., `Entire-Checkpoint: [ID]`)
- **Auth:** Local git identity; optional API key for cloud backend
- **Storage locations:**
  - Project-local: `.entire/` (mirrors `.git`)
  - Repo-remote: `entire/checkpoints/v1` branch (JSON files)
  - Transcripts: agent-specific (e.g., Gemini: `session-*-<shortid>.json` chunks; JSONL for others)
- **Plugin surface:** Per-agent hook system (`.claude/` for Claude Code, `.gemini/` for Gemini CLI); new agents implement an Agent interface with hook subcommands

### Session ingest surface for third parties
- **No documented consumer API.** No webhooks, no REST read endpoints.
- Primary path: **Read `entire/checkpoints/v1` branch JSON directly** (via git plumbing or `git show`)
- Secondary: Parse in-repo `.entire/` during active session (shadow branches are ephemeral)
- File layout: `entire/checkpoints/v1/<first-2-chars>/<checkpoint-id>.json`
- Git hooks drive capture (pre-commit, post-commit, pre-push)

### License + integration risk
- MIT — no restriction on competing or consuming tools
- No CLA
- Telemetry via PostHog (posthog-go in deps); best-effort secret redaction before branch write
- Phone-home is opt-in via `ENTIRE_API_BASE_URL`; local-only default
- **No competitive risk for CCDash integration**

### Comparable tools (one-line each)
- **Continue.dev:** CLI + IDE; logs to `~/.continue/logs/*.log` (plain text + core.log); no checkpoint/export
- **Cline:** Sessions at `~/.config/pi/agent/sessions/{encoded-cwd}/{ts}_{uuid}.jsonl`; typed events; no git integration
- **Aider:** JSONL session logs in `~/.aider/`; embedded in repo diffs; no checkpoint/rewind
- **Claude Code** (CCDash primary input today): JSONL per session dir; local-only

**Key differentiator of Entire:** coupling to Git via dedicated metadata branch — offline, merge-free, semantically linked to commits.

---

## Consolidated implications for design

1. **Both problems share the same foundation**: transport-neutral session ingest + de-filesystem-coupled sync engine. Build once, use for remote-CCDash daemon ingest AND Entire checkpoint ingest.
2. **Entire ingest has two plausible paths**:
   - (a) Parse the `entire/checkpoints/v1` branch (pull-mode, batch, works for historical)
   - (b) Hook into entire CLI via its agent-hook surface or cloud webhook (push-mode, live) — unclear if public API exists
3. **Remote daemon has two plausible paths**:
   - (a) HTTPS POST NDJSON to a new `/api/v1/ingest/sessions` endpoint (simplest, cache-friendly, no long-lived conns)
   - (b) WebSocket / gRPC streaming (better UX for live transcripts, more infra)
4. **Auth model is the hardest shared decision**: per-workspace token? OIDC? mTLS? Entire uses git identity — CCDash could piggyback if the daemon runs in a git repo
5. **Non-goals to call out loudly**: not rebuilding Entire; not becoming multi-tenant SaaS in v1; not replacing filesystem-based local mode

---

## References
- Entire docs: https://docs.entire.io/introduction, https://docs.entire.io/core-concepts
- Entire CLI repo: https://github.com/entireio/cli
- Entire launch: https://entire.io/blog/hello-entire-world
- CCDash runtime: PR #30, commit 451f958; `backend/runtime/`, `backend/adapters/jobs/`
- CCDash transports: `backend/routers/client_v1.py`, `backend/routers/agent.py`, `packages/ccdash_cli/`
