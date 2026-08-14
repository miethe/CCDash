---
name: ccdash
description: Answer CCDash project-intelligence questions using the shipped MCP tools when available and the in-repo `ccdash` CLI otherwise. Use when the operator or another agent asks about project status, feature forensics, workflow failure patterns, after-action reports, session intelligence (transcripts, search, detail), artifact intelligence, live agent counts, system metrics, project registration, runtime validation posture, CLI timeout or caching behavior, container project onboarding, watcher binding, or how to troubleshoot the shipped CCDash API/worker/MCP surfaces. Keep routing aligned with the current shipped runtime contract and repo docs.
version: 2.3
app_version: "2026-06-11"
updated: 2026-08-14
surface_verified_against: "CCDash 670bcc9 (2026-08-14) — surface inventory only; full runtime alignment still pending, see CHANGELOG"
---

# ccdash Skill

Route CCDash questions to the shipped agent-facing surfaces that exist in this repo today:

- MCP stdio server via [`.mcp.json`](/Users/miethe/dev/homelab/development/CCDash/.mcp.json)
- In-repo `ccdash` CLI (`status`, `feature`, `workflow`, `report`, `artifact`, `live`, `system`, `session`, plus `routing`, `persona`, `provider`, `token`, `research-run` — see Confidence Anchor)
- Standalone CLI (`ccdash-cli` package, HTTP transport to remote server)
- Runtime-validation docs for API health and worker probes

The business logic is transport-neutral. CLI and MCP are adapters over `backend/application/services/agent_queries/`.

## When To Use

Trigger on intents such as:

- "What's the state of this project?" / "project status" / "project summary"
- "Why did FEAT-X take so long?" / "retrospective on FEAT-X" / "AAR for FEAT-X"
- "Which workflows are failing?" / "failure burden" / "workflow diagnostics"
- "Show me the feature forensics for FEAT-X" / "list features matching X"
- "Is the hosted runtime healthy?" / "how do I validate API vs worker?" / "which probe should I hit?"
- "Is the MCP server shipped here?" / "should I use MCP or CLI for this?"
- "Why is my CLI timing out?" / "results look stale"
- "Prepare this project for the container stack" / "generate watcher env" / "bind worker-watch to a project"

## When NOT To Use

- General coding tasks unrelated to CCDash observability or runtime posture.
- Inventing runtime behaviors that contradict the split API/worker contract.

## Confidence Anchor

Repo-verified current surfaces. Every entry below was re-derived from `backend/cli/commands/*.py`,
`backend/cli/main.py` and `backend/mcp/tools/*.py` at commit `670bcc9` — do not trust a memory of this
list over those files.

**In-repo CLI commands** (`backend/.venv/bin/ccdash`; groups registered in `backend/cli/main.py`):
- `ccdash status project`
- `ccdash feature report <feature_id>` — the **only** `feature` subcommand in the in-repo CLI
- `ccdash workflow failures`
- `ccdash report aar --feature <feature_id>`
- `ccdash report aar-review <document_id>`
- `ccdash artifact rankings` / `ccdash artifact recommendations`
- `ccdash live active-count`
- `ccdash system active-count`
- `ccdash session search <query> [--project PROJECT] [--feature FEATURE] [--limit N]`
- `ccdash session get <session_id> --project <project_id> [--include SEG]... [--cursor CUR] [--limit N]`
- `ccdash session transcript <session_id> --project <project_id> [--cursor CUR] [--limit N]`

Global flags (all in-repo commands): `--timeout N`, `--no-cache`, `--json`, `--md`

⚠️ **Registered in-repo but NOT yet documented by this skill**: the `routing`, `persona`, `provider`,
`token`, and `research-run` groups. They exist in `backend/cli/main.py`; the Routing Table and
`references/` below do not cover them. Read the CLI's own `--help` before routing to them, and do not
infer their flags from the documented groups.

**Standalone-CLI-only groups** (not available in the in-repo CLI): `target`, `doctor`, `project`, `daemon`, the
`session list` / `show` / `family` / `drilldown` subcommands, `feature list` / `show` / `sessions` /
`documents`, and `report feature`.

⚠️ **`report feature` and `feature report` are different commands on different surfaces** — `ccdash report feature <id>` is standalone-only (narrative render), `ccdash feature report <id>` is in-repo-only. Verifying either against a single CLI surface makes the other look like a phantom; check both
`backend/cli/commands/` and `packages/ccdash_cli/src/ccdash_cli/commands/` before calling anything nonexistent.

**MCP tools** (14 registered in `backend/mcp/tools/`):
`ccdash_project_status`, `ccdash_feature_forensics`, `ccdash_workflow_failure_patterns`,
`ccdash_generate_aar`, `ccdash_aar_review`, `artifact_recommendations`, `ccdash_live_active_count`,
`ccdash_system_active_count`, `ccdash_session_search`, `ccdash_session_detail`,
`ccdash_session_transcript`, `ccdash_routing_rollup`, `ccdash_research_runs_list`,
`ccdash_research_run_detail`

Note: `artifact_recommendations` has no `ccdash_` prefix — do not normalize this name.

**Runtime entrypoints**: hosted API via `backend.runtime.bootstrap_api:app`; worker via `python -m backend.worker`

## Session Intelligence (Phase 3 — Transport-Neutral)

The session surfaces (MCP, repo-CLI, standalone-CLI, REST) are all backed by the same
transport-neutral Phase 1 service at
`backend/application/services/agent_queries/session_detail.py`.

### MCP tools

| Tool | Parameters | Notes |
|---|---|---|
| `ccdash_session_search` | `project_id` (required), `query` (required, min 2 chars), `feature_id`, `limit` (max 100), `offset` | Full-text / semantic search across session transcripts |
| `ccdash_session_detail` | `project_id` (required), `session_id` (required), `include[]`, `cursor`, `limit` (max 200) | Full detail bundle with transcript, tokens, subagents, artifacts, links |
| `ccdash_session_transcript` | `project_id` (required), `session_id` (required), `cursor`, `limit` (max 200) | Cursor-paginated transcript page only |

**`project_id` is required for all three tools.** Missing project_id → structured `status: "error"` response.
Unknown session_id → `status: "not_found"`.  Empty optional segments → empty list (not an error).

### MCP Payload Budget (T3-004)

| Constant | Value | Purpose |
|---|---|---|
| `MCP_TRANSCRIPT_DEFAULT_LIMIT` | 50 items | Default page size for MCP tool calls |
| `MCP_TRANSCRIPT_MAX_LIMIT` | 200 items | Per-call hard ceiling (below service max of 1 000) |
| `MCP_ENVELOPE_MAX_BYTES` | 1 048 576 (1 MiB) | Hard byte ceiling for MCP stdio envelopes |

When the serialised response exceeds `MCP_ENVELOPE_MAX_BYTES`, transcript items are trimmed
from the tail and the response metadata carries:
- `meta.truncated: true`
- `meta.truncated_reason` with cursor guidance
- `meta.payload_bytes` with the final byte count

Use `data.transcript.nextCursor` to retrieve the next page of a truncated transcript.

### Repo-CLI session commands

```bash
# Search sessions (defaults to active project if --project omitted)
ccdash session search "authentication flow" --json
ccdash session search "timeout" --project proj-abc --feature FEAT-123 --limit 10

# Full detail (--project required, no active-project fallback)
ccdash session get sess-abc123 --project proj-abc --json
ccdash session get sess-abc123 --project proj-abc --include transcript --include tokens

# Paginated transcript
ccdash session transcript sess-abc123 --project proj-abc --limit 50 --json
# Use nextCursor from previous output:
ccdash session transcript sess-abc123 --project proj-abc --cursor <opaque> --json
```

### Standalone CLI (ccdash-cli, HTTP transport)

```bash
# Transcript-bearing detail (Phase 2 REST endpoint, --project required)
ccdash session get sess-abc123 --project proj-abc --json
ccdash session get sess-abc123 --project proj-abc --include transcript --include tokens

# Existing commands (unchanged)
ccdash session list --feature FEAT-123
ccdash session search "authentication"
ccdash session show sess-abc123   # legacy endpoint, no transcript
```

### Redaction note

All transcript payloads are redacted by the Phase 1 service **before** egress.
Every transport (MCP, CLI, REST) inherits the same secret-scrubbing guarantee automatically.
Layer 1 (pattern scan: API keys, AWS/GCP creds, bearer tokens) and Layer 2 (tool-name-aware
field scan) are both applied.  `redactedFieldCount` in the response indicates how many fields
were redacted.

### project_id usage note

The `project_id` parameter is **the owning project** of the session, not the currently active
project.  This enables cross-project session forensics without switching the active project.
All three transports enforce this invariant — there is no silent active-project fallback.

## Routing Posture

Use the following transport order:

1. **Prefer MCP for in-workspace agent reasoning** when the repo `.mcp.json` is present and the question maps cleanly to one of the registered tools (14 today — see Confidence Anchor). This avoids shelling out and matches the current Claude Code posture.
2. **Use the in-repo CLI as the fallback adapter** when MCP is unavailable, when you need explicit output modes, or when validating parity against the command surface.
3. **Use the standalone CLI** when the user is operating against a remote CCDash server rather than local data. See [Standalone CLI vs In-Repo CLI](#standalone-cli-vs-in-repo-cli) below.
4. **Use runtime docs and HTTP probes for deployment/runtime troubleshooting.** Do not invent CLI transport-management commands that are not shipped.

Current shipped posture: MCP is discoverable, but not the only path. CLI remains valid. Runtime validation is a separate concern handled through the API/worker contract.

## Standalone CLI vs In-Repo CLI

| Dimension | In-Repo CLI | Standalone CLI |
|---|---|---|
| Install | `backend/.venv/bin/ccdash` | `pipx install ccdash-cli` → `ccdash` |
| Transport | Local data / lightweight bootstrap | HTTP to remote CCDash server (`/api/v1/`) |
| Auth | None | Bearer token via OS keyring or `CCDASH_TOKEN` |
| Config | None | `~/.config/ccdash/config.toml` (named targets) |
| Command groups | `status`, `feature` (`report` only), `workflow`, `report`, `artifact`, `live`, `system`, `session` (`search`/`get`/`transcript` only), `routing`, `persona`, `provider`, `token`, `research-run` | `status`, `feature` (`list`/`show`/`sessions`/`documents`), `workflow`, `report`, `session` (`list`/`show`/`search`/`drilldown`/`get`/`family`), `project`, `target`, `doctor`, `diagnostics`, `version` |
| Use when | Querying local project data | Operating against hosted/remote server |

**Do not** suggest `target`, `doctor`, `target login`, or `project` commands to a user running only the
in-repo CLI — those groups exist only in the standalone CLI. `session` is **split**: `search`, `get` and
`transcript` are in-repo (Phase 3), while `list`, `show`, `family` and `drilldown` are standalone-only.
Likewise `feature` is split: only `report` is in-repo.

## Query Caching

All four query services (project-status, feature-forensics, workflow-diagnostics, aar-report) use an in-process TTL cache:

| Config | Default | Effect |
|---|---|---|
| `CCDASH_QUERY_CACHE_TTL_SECONDS` | 60 | Cache lifetime; set to 0 to disable |
| `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` | 300 | Background warming interval; 0 disables |
| `--no-cache` CLI flag | off | Force cache miss for one invocation |
| `bypass_cache=true` query param | off | Force cache miss via HTTP |

**Guidance**: Use `--no-cache` when debugging stale data. Do not disable the cache in production — background warming reduces cold-path latency. OpenTelemetry counters are emitted per cache event.

## CLI Timeout

The standalone CLI exposes a global timeout on every command:

| Config | Default | Notes |
|---|---|---|
| `--timeout N` flag | 30s | Precedence: flag > env > default |
| `CCDASH_TIMEOUT` env var | 30s | Applied when flag is absent |

Commands that can be slow on large projects: `status project`, `report aar`, `workflow failures`. Consider `--timeout 60` or higher when these time out. See `/Users/miethe/dev/homelab/development/CCDash/docs/guides/cli-timeout-debugging.md` for diagnosis patterns.

## Routing Table

| Intent | Preferred MCP Tool | CLI Fallback | Notes |
|---|---|---|---|
| Project status | `ccdash_project_status` | `ccdash status project` | Use MCP first for agent reasoning; CLI `--json`/`--md` modes useful |
| Feature forensics | `ccdash_feature_forensics` | `ccdash feature report FEATURE_ID` | Top-level `name`, `status`, `telemetry_available`, `sessions_note` fields available |
| Feature listing | `ccdash_feature_forensics` (list mode) | *(standalone only)* `ccdash feature list [--q TEXT]` | Paginated; max 200 results; `truncated`/`total` in response. Not in the in-repo CLI |
| Feature sessions | none | *(standalone only)* `ccdash feature sessions FEATURE_ID` | Canonical fresh-sessions surface; prefer over `feature show`'s `linked_sessions` |
| Workflow failures | `ccdash_workflow_failure_patterns` | `ccdash workflow failures` | Same query service behind both surfaces |
| AAR / retrospective | `ccdash_generate_aar` | `ccdash report aar --feature FEATURE_ID` | Render markdown/human output as requested |
| Session transcript search | `ccdash_session_search` | `ccdash session search <query> --project P` | project_id required for MCP; optional (active-project fallback) for CLI |
| Session full detail | `ccdash_session_detail` | `ccdash session get ID --project P` | project_id required; transcript cursor-paginated; redaction auto-applied |
| Session transcript page | `ccdash_session_transcript` | `ccdash session transcript ID --project P` | Cursor pagination; use nextCursor for subsequent pages |
| AAR review | `ccdash_aar_review` | `ccdash report aar-review DOCUMENT_ID` | Reviews an existing AAR document |
| Artifact rankings | none | `ccdash artifact rankings` | In-repo only; no standalone-CLI equivalent yet |
| Artifact recommendations | `artifact_recommendations` | `ccdash artifact recommendations` | In-repo and MCP; no standalone-CLI equivalent yet |
| Live active count | `ccdash_live_active_count` | `ccdash live active-count` | In-repo and MCP; no standalone-CLI equivalent yet |
| System active count | `ccdash_system_active_count` | `ccdash system active-count` | In-repo and MCP; no standalone-CLI equivalent yet |
| Project registration | none | *(standalone only)* `ccdash project add \| list \| use` | Registers projects against a named target via `/api/projects` |
| Narrative feature report | none | *(standalone only)* `ccdash report feature FEATURE_ID` | Markdown by default. Distinct from the in-repo `ccdash feature report` |
| Runtime validation | none | none | Route to `/api/health`, worker probes, and runbook docs |
| MCP setup/troubleshooting | shipped stdio server | CLI parity checks only | Follow `docs/guides/mcp-setup-guide.md` and `docs/guides/mcp-troubleshooting.md` |

## Runtime Contract

Hosted validation assumes a split runtime:

- API runtime serves HTTP and canonical reads.
- Worker runtime owns sync, refresh, and scheduled jobs.
- `local` is a convenience runtime and is not the hosted validation posture.
- `test` is for lightweight CLI/MCP bootstrap and automated coverage.

Canonical hosted entrypoints:

```bash
backend/.venv/bin/python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port 8000
backend/.venv/bin/python -m backend.worker
```

Local helpers like `npm run dev:backend` and `npm run start:worker` are wrappers around the same contract; the bootstrap modules are the canonical reference.

**Containerized deployment**: Docker/Podman compose profiles (`local`, `enterprise`, `postgres`, `live-watch`) are supported. Rootless Podman is supported. Single-command deployment via `docker compose` or `podman-compose`. Reference: `/Users/miethe/dev/homelab/development/CCDash/docs/guides/containerized-deployment-quickstart.md`.

**Project onboarding and watcher binding**: container roles resolve projects from mounted `projects.json`. Use `/Users/miethe/dev/homelab/development/CCDash/backend/scripts/container_project_onboarding.py` to prepare the registry entry and optional per-watcher env overlay. In v1, `worker-watch` binds one project at startup via `CCDASH_WORKER_WATCH_PROJECT_ID`; UI project switching, standalone CLI `--project`, and target defaults do not rebind a running watcher.

## Probe Semantics

- `GET /api/health` — primary API/runtime contract check.
- Worker probe: `CCDASH_WORKER_PROBE_HOST:CCDASH_WORKER_PROBE_PORT` (default `127.0.0.1:9465`).
  - `/livez` — basic process liveness
  - `/readyz` — readiness after worker binding contract is satisfied
  - `/detailz` — backlog/freshness detail and worker posture

A healthy API does not prove worker ownership is functioning; a ready worker does not replace the API health contract.

## Lightweight Bootstrap Invariant

CLI and MCP use lightweight `test`-profile bootstrap paths. They do not stand up the full hosted runtime and do not own background jobs.

- CLI bootstrap: `backend/cli/runtime.py`
- MCP bootstrap: `backend/mcp/bootstrap.py`
- MCP transport: stdio via [`.mcp.json`](/Users/miethe/dev/homelab/development/CCDash/.mcp.json)

Do not claim that CLI or MCP validates the hosted deployment by themselves.

## Output Guidance

- For agent reasoning: prefer structured MCP responses or CLI `--json`.
- For user-facing narrative deliverables: use CLI `--md` where available, especially `report aar`.
- For runtime validation: summarize relevant health/probe fields rather than dumping the entire payload unless the user asks for raw output.

## Multi-Step Flows (Recipes)

- `recipes/feature-retrospective.md` — feature forensics + AAR with MCP-first/CLI-fallback posture.
- `recipes/task-attribution.md` — infer work ownership from feature forensics and evidence rather than stale task/session commands.
- `recipes/unreachable-server.md` — troubleshoot the API/worker/MCP runtime contract and probe semantics.
- `recipes/container-project-onboarding.md` — prepare `projects.json`, generate watcher env overlays, and validate container project visibility without implying remote watcher orchestration.

Prefer a recipe whenever the user's question spans transport choice plus interpretation.

## Do Not Say

- "MCP is deferred until a later phase."
- "Use `ccdash doctor` / `ccdash target show` / `ccdash target login`." (standalone CLI only — not available in the in-repo CLI)
- "Hosted validation should run against `backend.main:app` or `npm run dev`."
- "CLI or MCP starts the full runtime or proves worker ownership on its own."
- "The CLI has no timeout configuration." (it does: `--timeout` flag and `CCDASH_TIMEOUT` env var)
- "Session transcript search is only available in the standalone CLI." (Phase 3: in-repo CLI also has `ccdash session search/get/transcript`)
- "There is no active-project fallback for session get/transcript." (correct — by design; `--project` is required)
- "project_id is optional for session tools." (it is required for both MCP tools and CLI get/transcript)
- "Query results are always fresh." (they are cached; use `--no-cache` to bypass)
- "Changing the active project or CLI target rebinds a running `worker-watch` container."
- "The CCDash API/CLI/skill can remotely scale, start, or rebind watcher containers in the compose examples."

## Key References

- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/enterprise-session-intelligence-runbook.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/setup-user-guide.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/mcp-setup-guide.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/mcp-troubleshooting.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/cli-timeout-debugging.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/query-cache-tuning-guide.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/standalone-cli-guide.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/containerized-deployment-quickstart.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/design-specs/container-project-onboarding-and-watchers-v1.md`
- `/Users/miethe/dev/homelab/development/CCDash/deploy/runtime/README.md`
- `/Users/miethe/dev/homelab/development/CCDash/backend/scripts/container_project_onboarding.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/cli/main.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/mcp/server.py`
- `/Users/miethe/dev/homelab/development/CCDash/packages/ccdash_cli/`
