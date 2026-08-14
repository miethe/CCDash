# `ccdash session` — Session Intelligence

> **Transport note**: This reference covers two distinct surfaces.
> - **Standalone CLI** (`pipx install ccdash-cli` → `ccdash`): `list`, `show`, `search`, `drilldown`, `get`, `family` — HTTP transport to remote CCDash server.
> - **Repo CLI** (`backend/.venv/bin/ccdash`): `search`, `get`, `transcript` — lightweight local bootstrap, no HTTP server needed.
>
> Phase 3 (CCDash Core Remediation) added `get` to both CLIs and `transcript` to the repo CLI only. MCP tools `ccdash_session_search` / `ccdash_session_detail` / `ccdash_session_transcript` cover the same capabilities; see SKILL.md § Session Intelligence.

Standalone CLI subcommands: `list`, `show`, `search`, `drilldown`, `get`, `family`. All honor `--output {human|json|markdown}` with `--json` / `--md` shortcuts.

## `session list`

```text
ccdash session list [--feature ID] [--root-session ID] [--limit INT=50] [--offset INT=0] [--output ...]
```

Filters:

- `--feature` — sessions linked to a feature.
- `--root-session` — sessions sharing a root (cluster lens; see `session family` for a convenience wrapper).

### JSON shape

```json
{
  "sessions": [
    {
      "session_id": "...",
      "root_session_id": "...",
      "feature_id": "...",
      "started_at": "...",
      "ended_at": "...",
      "cost": 1.23,
      "model": "claude-opus-4-6",
      "title": "..."
    }
  ],
  "total": ...,
  "limit": 50,
  "offset": 0
}
```

## `session show SESSION_ID`

Detailed intelligence for a single session: tool-call summary, cost breakdown, message counts, linked feature/documents, risk signals.

```text
ccdash session show SESSION_ID [--output ...]
```

### JSON shape (key fields)

| Field | Meaning |
|---|---|
| `session_id`, `root_session_id`, `feature_id` | Stable identity + linkage. |
| `started_at`, `ended_at`, `duration_seconds` | Timing. |
| `cost`, `token_input`, `token_output`, `model` | Usage. |
| `tool_calls` | Array summarizing tool usage (counts + top tools). |
| `message_counts` | Human / assistant / system / tool totals. |
| `linked_documents` | `{document_id, doc_type, path}` entries. |
| `risk_signals` | `{signal, score, explanation}` — feeds `drilldown`. |
| `summary` | Server-curated narrative one-paragraph. |

## `session search QUERY`

Full-text search over session transcripts (min 2 characters).

```text
ccdash session search QUERY [--feature ID] [--root-session ID] [--session ID] [--limit INT=25] [--offset INT=0] [--output ...]
```

> **Repo CLI**: `ccdash session search QUERY [--project PROJECT] [--feature FEATURE] [--limit N]` — `--project` optional (defaults to active project).
> **MCP**: `ccdash_session_search` with `project_id` (required) and `query` (min 2 chars).

### JSON shape

```json
{
  "matches": [
    {
      "session_id": "...",
      "feature_id": "...",
      "timestamp": "...",
      "match_line": "...",
      "line_no": 1234,
      "role": "assistant"
    }
  ],
  "total": ...,
  "limit": 25,
  "offset": 0
}
```

Use `--feature` to scope to a feature's session set; `--session` to pin to a single session.

## `session get SESSION_ID --project PROJECT_ID` *(Phase 3 — transcript-bearing)*

Returns the full session detail bundle from the Phase 2 REST endpoint (`GET /api/v1/sessions/{id}/detail`).  `--project` is **required** — no active-project fallback.

```text
ccdash session get SESSION_ID --project PROJECT_ID [--include SEG]... [--cursor CUR] [--limit INT=50] [--output ...]
```

Segments (`--include`, repeatable): `transcript`, `tokens`, `subagents`, `artifacts`, `links`. Omit to return all.

> **Repo CLI equivalent**: `ccdash session get SESSION_ID --project PROJECT_ID` (same flag contract, local bootstrap).
> **MCP equivalent**: `ccdash_session_detail` with `project_id` and `session_id`.

### JSON shape (key fields)

| Field | Meaning |
|---|---|
| `session`, `sessionId`, `projectId` | Core identity + project scope. |
| `transcript.{items,cursor,limit,nextCursor}` | Cursor-paginated transcript page. `nextCursor` null on last page. |
| `tokens.{inputTokens,outputTokens,cacheReadTokens}` | Token telemetry. |
| `subagents[]` | Child sessions spawned by this session. |
| `artifacts[]`, `links[]` | Classified artifact and cross-entity links. |
| `redactedFieldCount` | Count of fields scrubbed by the layered redaction service. |

Redaction (Layer 1 secret patterns + Layer 2 tool-aware field scan) is applied by the Phase 1 service before any transport returns data.

## `session drilldown SESSION_ID --concern {sentiment|churn|scope_drift}`

Targeted analysis of a specific concern using session telemetry.

```text
ccdash session drilldown SESSION_ID --concern sentiment
ccdash session drilldown SESSION_ID --concern churn
ccdash session drilldown SESSION_ID --concern scope_drift
```

- `sentiment` — frustration / confusion / confidence indicators across the transcript.
- `churn` — file-edit thrash (same files modified repeatedly).
- `scope_drift` — deviation from the feature's stated scope.

JSON returns `{session_id, concern, findings: [...], evidence_line_refs: [...]}`.

## `session family SESSION_ID`

Lists all sessions sharing the same root as `SESSION_ID` (resumes, branches, parallel agents).

```text
ccdash session family SESSION_ID [--output ...]
```

JSON returns `{root_session_id, sessions: [...], feature_id}`.

## Default Output Mode

`--json` for all five. Use `--md` only when the user explicitly wants a narrative render.

## Recipes

- `recipes/workflow-failure-rootcause.md` — `workflow failures` → pick worst → `session drilldown`.
- `recipes/session-cluster-investigation.md` — `session show` → `session family` → per-sibling drilldown.
- `recipes/feature-retrospective.md` — uses `feature sessions` then `session show` for top-cost sessions.

## Repo-CLI Session Commands (Phase 3)

The repo CLI (`backend/.venv/bin/ccdash session`) ships three commands — `search`, `get`, `transcript` — backed by the same Phase 1 transport-neutral service as MCP. `--project` is required for `get` and `transcript`.

```bash
# Repo-CLI: search (active-project fallback or explicit --project)
ccdash session search "auth flow" --project proj-abc --json
# Repo-CLI: get (--project required)
ccdash session get sess-xyz --project proj-abc --include transcript --include tokens --json
# Repo-CLI: transcript (--project required; cursor pagination)
ccdash session transcript sess-xyz --project proj-abc --limit 50 --json
ccdash session transcript sess-xyz --project proj-abc --cursor <opaque> --json
```

See SKILL.md § Session Intelligence for full MCP tool contracts and payload-budget constants.

## Cross-Links

- MCP session tools: SKILL.md § Session Intelligence (MCP tools, payload budget, project_id requirement, redaction guarantee).
- Feature linkage: `command-feature.md`.
- Workflow linkage: `command-workflow.md`.
- Provenance echo list: `provenance.md`.
