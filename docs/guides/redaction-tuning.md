---
title: "Redaction Tuning Guide"
description: "Configure CCDash session-transcript redaction: secret patterns and tool-aware payload scrubbing"
category: guides
tags: [redaction, security, privacy, session-detail, operator]
updated: 2026-06-12
---

# Redaction Tuning Guide

CCDash applies a two-layer redaction pass to every session transcript before
egress — at the `session_detail` service boundary — so REST, MCP, and CLI
transports all inherit the same scrubbing without per-transport code.

Redaction is **fail-closed**: if an env var is absent or unrecognised the safer
default (enabled) applies.  Redaction-event logs record a field **count** only —
never payload contents.

> **Source**: `backend/application/services/agent_queries/redaction.py` (both layers)
> and `backend/application/services/agent_queries/session_detail.py` (egress call site).

---

## Env var controls

| Variable | Default | Effect |
|---|---|---|
| `CCDASH_REDACTION_PATTERNS_ENABLED` | `true` | Layer 1 — regex scan on `content` and raw arg strings |
| `CCDASH_REDACTION_TOOL_AWARE_ENABLED` | `true` | Layer 2 — tool-name-aware per-field scrubbing |

Set either to `0` / `false` / `no` / `off` to disable that layer.  Both off means
no redaction; use only on a fully air-gapped, personal-use instance.

```dotenv
# Disable Layer 2 only (keep the pattern scan):
CCDASH_REDACTION_TOOL_AWARE_ENABLED=false

# Disable both layers (NOT recommended):
CCDASH_REDACTION_PATTERNS_ENABLED=false
CCDASH_REDACTION_TOOL_AWARE_ENABLED=false
```

---

## Layer 1 — Known-secret pattern scan

Applied to the `content` field of every log entry.  Patterns and their labels:

| Label | What it matches |
|---|---|
| `api_key_assignment` | `api_key=…` / `api-token: …` style key-value pairs (≥ 20 char values) |
| `bearer_token` | `Bearer <token>` in Authorization headers (≥ 20 chars) |
| `aws_access_key_id` | `AKIA…` 20-char uppercase AWS Access Key IDs |
| `aws_secret_key` | `aws_secret_access_key=…` / `aws_secret=…` (40-char base64) |
| `gcp_private_key` | JSON `"private_key": "-----BEGIN…"` blocks |
| `pem_private_key_header` | `-----BEGIN … PRIVATE KEY-----` PEM block headers |
| `sk_key` | `sk-…` style keys (OpenAI / Anthropic / similar; ≥ 20 chars after `sk-`) |
| `github_pat` | `ghp_…` / `gho_…` / `ghs_…` / `ghu_…` / `ghr_…` GitHub PATs (36+ chars) |
| `dotenv_assignment` | `UPPER_KEY=value` lines where value is ≥ 8 non-whitespace chars |
| `hex_64` | Bare 64-character lowercase hex strings (potential secrets/hashes) |

Each match is replaced with the literal string `[REDACTED]`.

---

## Layer 2 — Tool-name-aware payload field redaction

Applied to the `toolCall` object when `CCDASH_REDACTION_TOOL_AWARE_ENABLED=true`.

### Sensitive argument keys per tool

| Tool name(s) | Fields scanned |
|---|---|
| `Bash`, `bash` | `command`, `cmd`, `script` |
| `Shell` | `command`, `cmd` |
| `Write` | `content`, `new_string`, `old_string` |
| `Edit` | `new_string`, `old_string` |
| `MultiEdit` | `edits` |
| `computer_use` | `text`, `command` |

**Shell-specific addition**: for `Bash`/`bash`/`Shell` tools, an extra
environment-variable assignment pattern (`export KEY=value` or `KEY=value` with
value ≥ 8 non-whitespace chars) is applied over the command string after Layer 1.

**Unknown tools** fall through to a Layer 1 pattern scan on the raw `args` and
`output` strings — they are never left unredacted.

### `output` field

The `output` field of any `toolCall` dict is always scanned with Layer 1
regardless of the tool name, because command output can echo secrets.

---

## Local-trust scope

Redaction applies at the `session_detail` egress boundary.  This boundary is
reached by every transport:

- **REST** → `GET /api/v1/sessions/{id}/detail`
- **MCP** → `session_detail` / `session_transcript` tools
- **CLI** → `ccdash session detail` subcommand

Sessions stored in the local SQLite/Postgres cache are **not** modified — only
the in-flight response is scrubbed.

---

## Response contract

The bundle response includes a `redactedFieldCount` integer:

```json
{
  "sessionId": "…",
  "redactedFieldCount": 3,
  "transcript": { … }
}
```

`redactedFieldCount > 0` is a **contract state**, not a bug.  Consumers MUST
handle `[REDACTED]` placeholders gracefully; field values may be partially
replaced inline.

---

## Failure behaviour

If a redaction call raises unexpectedly, the affected transcript page is
returned **as-is** (unredacted for that page) and the error is logged.
Fail-safe delivery (no data loss) takes priority over a guaranteed scrub in edge
cases.  The `redactedFieldCount` for that page will be 0.
