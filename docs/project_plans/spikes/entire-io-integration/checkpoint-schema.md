---
schema_version: 2
doc_type: spike
title: "Entire.io Checkpoint Schema — Canonical Reference (SPIKE-B / RQ-1, E3)"
description: "Reverse-engineered canonical schema for Entire.io CLI checkpoint JSON, with required/optional/agent-specific markers and provenance."
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
parent_spike: docs/project_plans/spikes/entire-io-integration.md
related_documents:
  - docs/project_plans/spikes/remote-ccdash-streaming.md
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-011-entire-ingest-path-decision.md
  - docs/project_plans/adrs/adr-012-entire-session-identity-unification.md
upstream_source: https://github.com/entireio/cli
upstream_branch_layout: "entire/checkpoints/v1/<XX>/<12hex-id>.json"
---

# Entire.io Checkpoint Schema — Canonical Reference

> **Status of this document.** This SPIKE could not exhaustively diff every field across all seven supported agents (claude-code, codex, gemini, opencode, cursor, factoryai-droid, copilot-cli) without a multi-day captive corpus run. What is in scope here is the **stable union of fields** that the upstream Agent Hooks lifecycle guarantees plus the per-agent extension surfaces that the upstream documentation describes. Field-level provenance points at upstream source locations to be verified in Phase 5 implementation; **a Phase 5 acceptance gate (E3-CONFORMANCE) re-runs the diff against a live corpus and updates this doc before `EntireCheckpointSource` is marked ready.**

## 1. Branch Layout & On-Disk Form

| Item | Value | Provenance |
|---|---|---|
| Branch | `entire/checkpoints/v1` | charter §2; [entireio/cli](https://github.com/entireio/cli) README |
| Path sharding | First 2 chars of 12-hex ID | charter §2 |
| Path template | `entire/checkpoints/v1/<xx>/<12hex>.json` | charter §2 |
| Encoding | UTF-8 JSON (single object per file) | inferred from agent-hooks lifecycle |
| Companion shadow branches | `entire/<sessionID>-<worktreeID>` (ephemeral per-session working state) | charter §2 |
| Commit trailer linkage | `Entire-Checkpoint: <12hex-id>` on each commit produced during the session | charter §2; informs RQ-6 |

## 2. Lifecycle (the contract the schema serves)

Per upstream Agent Hooks documentation, every supported agent maps its native event stream into Entire's shared lifecycle:

| Lifecycle event | Fires when | Persists to checkpoint? |
|---|---|---|
| `session.start` | Agent process begins a session | Yes — opens the checkpoint object |
| `prompt.submit` | User submits a prompt to the agent | Yes — appended to `turns[]` |
| `turn.end` | Agent completes a turn (model finished, optionally tools ran) | Yes — closes a turn entry in `turns[]` |
| `subagent.exec` | Agent spawns a subagent (Claude Code, Gemini delegations) | Yes — appended as a nested turn or `subagents[]` entry |
| `session.end` | Agent exits / session closes | Yes — finalizes the checkpoint object |

A checkpoint **file** is the on-disk projection of one fully-finalized session. Mid-session state lives on the shadow branch (`entire/<sessionID>-<worktreeID>`) and is **not** read by CCDash (it is volatile and may be pruned by `entire` itself).

## 3. Canonical Top-Level Schema

> Marker key: **R** = required (always present), **O** = optional (may be absent), **A** = agent-specific (only present for some `agent.kind` values).

### 3.1 Core identity & timing

| Field | Type | Marker | Notes |
|---|---|---|---|
| `id` | string (12-hex) | R | Matches filename without `.json`. Primary checkpoint identifier. |
| `sessionId` | string (`YYYY-MM-DD-<UUID>`) | R | Stable across rewind/resume. Charter §2 confirms format. |
| `schemaVersion` | string | R | Expected to be `"v1"` while branch is `entire/checkpoints/v1`. Forward-compat sentinel — CCDash MUST `warn-and-strip` on unknown minor extensions and reject on unknown majors. |
| `createdAt` | string (RFC3339) | R | When the checkpoint object was first written. |
| `updatedAt` | string (RFC3339) | R | Last mutation timestamp (turn appends update this). |
| `startedAt` | string (RFC3339) | R | When the agent session began. |
| `endedAt` | string (RFC3339) | O | Present once `session.end` fires. Absent for crashed/abandoned sessions. |

### 3.2 Agent identity

| Field | Type | Marker | Notes |
|---|---|---|---|
| `agent.kind` | enum string | R | One of: `claude-code`, `codex`, `gemini`, `opencode`, `cursor`, `factoryai-droid`, `copilot-cli`. |
| `agent.version` | string | O | Agent's reported version. |
| `agent.model` | string | O | Primary model used (e.g. `claude-sonnet-4-7`, `gemini-3.1-pro`). May change mid-session — see `agent.modelTransitions`. |
| `agent.modelTransitions` | array of `{at, from, to}` | O | Present when model switched mid-session. |
| `agent.plugin` | string | A | Present only for external-plugin agents (charter §7 / RQ-7). |

### 3.3 Repo / worktree context

| Field | Type | Marker | Notes |
|---|---|---|---|
| `repo.remoteUrl` | string | O | Git remote URL of the repo when the session ran. |
| `repo.branch` | string | R | Branch active at session start. |
| `repo.worktreeId` | string | R | Stable opaque ID for the worktree; appears in shadow-branch name. |
| `repo.commitBefore` | string (40-hex) | R | HEAD SHA at session start. |
| `repo.commitAfter` | string (40-hex) | O | HEAD SHA at session end (absent on abandoned sessions). |
| `repo.commits` | array of strings (40-hex) | O | Every commit produced during the session, in order. Each one has the `Entire-Checkpoint: <id>` trailer pointing back to this file. Source of truth for RQ-6 `session_commit_links`. |

### 3.4 Conversation (turns)

| Field | Type | Marker | Notes |
|---|---|---|---|
| `turns` | array of turn objects | R | Ordered. Length ≥ 1 once `prompt.submit` has fired at least once. |
| `turns[].id` | string | R | Stable within the session. |
| `turns[].submittedAt` | string (RFC3339) | R | Maps to `prompt.submit`. |
| `turns[].endedAt` | string (RFC3339) | O | Maps to `turn.end`. Absent for in-flight or aborted turns. |
| `turns[].prompt` | string \| ref | R | The user prompt text. May be a transcript pointer for very long prompts (see §3.6). |
| `turns[].response` | string \| ref | O | Final assistant response. May be a transcript pointer. |
| `turns[].toolCalls` | array of tool-call objects | O | Tool/function invocations during the turn. See §3.5. |
| `turns[].tokens` | `{in, out, cached?}` | O | Per-turn token usage. |
| `turns[].subagents` | array | A | Present for Claude Code (Task tool), Gemini delegations, etc. |

### 3.5 Tool calls (per turn)

| Field | Type | Marker | Notes |
|---|---|---|---|
| `toolCalls[].name` | string | R | Tool name as the agent reported it. |
| `toolCalls[].at` | string (RFC3339) | R | Invocation timestamp. |
| `toolCalls[].inputDigest` | string (sha256) | O | Hash of inputs — Entire may elide raw inputs for size/privacy. |
| `toolCalls[].outputDigest` | string (sha256) | O | Hash of outputs. |
| `toolCalls[].fileTouches` | array of `{path, op}` | O | Files read/written during the call. Drives the "files touched" view. |
| `toolCalls[].errored` | bool | O | True if the tool reported an error. |

### 3.6 Transcript references

Transcripts can be MBs per session (charter RQ-5). Entire stores them by reference; the inline `prompt`/`response` fields above MAY be replaced with reference objects:

| Field | Type | Marker | Notes |
|---|---|---|---|
| `<ref>.kind` | enum: `"git-blob"` \| `"file"` | R when ref | `git-blob` = stored as a blob on the shadow branch; `file` = stored under `~/.local/share/entire/transcripts/` (or platform equivalent). |
| `<ref>.locator` | string | R when ref | For `git-blob`: blob SHA on shadow branch. For `file`: agent-specific path. |
| `<ref>.size` | int (bytes) | O | When known. Drives the eager/lazy resolution decision (see ADR-011 §Transcript Resolution). |
| `<ref>.agentNative` | string | A | Agent-specific transcript format hint (`gemini-session-shortid-json`, `claude-jsonl`, etc.). |

### 3.7 Token & cost summary

| Field | Type | Marker | Notes |
|---|---|---|---|
| `totals.tokensIn` | int | O | Sum across turns; convenience field. |
| `totals.tokensOut` | int | O | Sum across turns; convenience field. |
| `totals.cacheCreationTokens` | int | A | Anthropic-specific (Claude Code). |
| `totals.cacheReadTokens` | int | A | Anthropic-specific (Claude Code). |
| `totals.cost` | number (USD) | O | Sum where the agent reports cost (Claude Code, sometimes Codex). |

### 3.8 Redaction & privacy metadata

| Field | Type | Marker | Notes |
|---|---|---|---|
| `redaction.applied` | bool | O | True if Entire applied any redaction rules. |
| `redaction.rulesetVersion` | string | O | Version tag of the upstream redaction ruleset (best-effort; see RQ-9). |
| `redaction.matches` | int | O | Count of redacted spans across the checkpoint. |

CCDash treats redaction metadata as advisory only. The CCDash-side second-pass redactor (see privacy memo) re-scans on ingest.

## 4. Per-Agent Extension Surface (A markers)

The fields below are observed/expected to appear only for specific agents. They land in a single nested `agentSpecific.<kind>` object so CCDash can carry them through without typing every variant.

| `agent.kind` | Likely extension fields (under `agentSpecific.<kind>.*`) | Source-of-truth (verify at E3-CONFORMANCE gate) |
|---|---|---|
| `claude-code` | `cacheCreationTokens`, `cacheReadTokens`, `cwd`, `transcriptPath` (JSONL pointer), thinking/extended-thinking metadata if surfaced | Upstream `internal/agents/claudecode/` (path inferred) |
| `gemini` | `transcriptPath` (`session-*-<shortid>.json`), `googleGenerativeApiVersion` | Upstream `internal/agents/gemini/` (path inferred) |
| `codex` | `codexSessionId`, codex-specific tool taxonomy | TBD |
| `opencode` | `pluginVersion`, model-router metadata | TBD |
| `cursor` | `cursorChatId`, `mcpServersUsed[]` | TBD |
| `factoryai-droid` | `droidId`, `pipelineId` | TBD |
| `copilot-cli` | `copilotConversationId` | TBD |

**Conformance gate E3-CONFORMANCE (Phase 5 acceptance).** Before `EntireCheckpointSource` ships, run paired sessions against at least three agents (mandatory: `claude-code`, `gemini`; one of [`codex`, `cursor`, `opencode`]), capture checkpoint JSON, diff against this schema, and:

- Promote any A-marker field that appears under all three to R or O.
- Demote any R-marker field that is missing in any of the three to O (with `CCDash-resilient: handle-missing` AC).
- File a follow-up issue against upstream for any structural break that cannot be absorbed by `warn-and-strip`.

## 5. Schema Stability & Versioning Posture

| Risk | Stance |
|---|---|
| Field added by upstream | Forward-compatible. CCDash parser uses Pydantic with `extra="allow"`, logs unknown fields once per `(agent.kind, field-path)` per process, ingests normally. |
| Field renamed by upstream | Treated as breaking. Parser raises; ingest source marks the checkpoint dead-lettered (mirrors F-5 from SPIKE-A) and surfaces upstream issue. |
| New `agent.kind` | Ingested with `agentSpecific.<kind>` opaque blob; no parser change required to land the session. Per-agent extensions can be added incrementally. |
| Branch path rename (`entire/checkpoints/v2`) | Major upstream version. Triggers schema-version bump (`schemaVersion: "v2"`) and a new `EntireCheckpointSource` variant under feature flag `CCDASH_ENTIRE_SCHEMA_V2_ENABLED`. v1 continues to read v1 branch. |
| Sharding scheme change | Detected at branch enumeration time (path glob mismatch); parser bails with `ingest_schema_warning_total{event_type="branch-layout"}` metric. |

## 6. CCDash Mapping Crib Sheet

The minimal CCDash session row (`backend/db/repositories/sessions.py`) is populated from a checkpoint as follows:

| CCDash column | Entire source |
|---|---|
| `id` | `sessionId` (`YYYY-MM-DD-<UUID>`) — already globally unique |
| `source_ref` | `"entire:" + checkpoint.id` (12-hex) — per ADR-012 |
| `source_file` | NULL (no filesystem path; legacy column tolerated as nullable per ADR-009) |
| `project_id` | Resolved from `repo.remoteUrl` / current project binding (request-scoped per ADR-010) |
| `workspace_id` | From `AuthContext.workspace_id` (ADR-008) |
| `model` | `agent.model` (with `agent.modelTransitions` populating `platform_version_transitions_json`) |
| `platform_type` | Mapped from `agent.kind` → CCDash platform string (e.g. `claude-code` → `"Claude Code"`) |
| `platform_version` | `agent.version` |
| `tokens_in` / `tokens_out` | `totals.tokensIn` / `totals.tokensOut`, fallback to sum-over-turns |
| `cache_creation_input_tokens` / `cache_read_input_tokens` | `agentSpecific.claude-code.cacheCreationTokens` / `cacheReadTokens` |
| `total_cost` | `totals.cost` |
| `git_commit_hash` | `repo.commitAfter` |
| `git_commit_hashes_json` | `repo.commits` |
| `git_branch` | `repo.branch` |
| `started_at` / `ended_at` | `startedAt` / `endedAt` |
| `created_at` / `updated_at` | `createdAt` / `updatedAt` |
| `session_forensics_json` | `agentSpecific` opaque blob (preserves agent-specific fields without typing each one) |

Transcript content (turns + tool calls) is materialized by an existing CCDash service path (`backend/services/session_transcript_projection.py`) once the `EntireCheckpointSource` lands events via the standard `SessionIngestSource` port.

## 7. Open Items for Phase 5 Implementation

1. **E3-CONFORMANCE corpus.** Stand up a scratch repo with `entire enable`, run paired sessions across at least three agents, capture checkpoints, diff, and update §4 of this doc.
2. **Transcript fidelity decision.** Eager-fetch vs lazy-fetch vs git-native-pointer is decided in ADR-011 §Transcript Resolution; this document is the field reference, not the resolution policy.
3. **Per-agent platform-string mapping table.** The `agent.kind → platform_type` mapping above needs an explicit constant in `backend/services/source_identity.py` matching CCDash's existing platform naming.

## 8. Sources

- [entireio/cli on GitHub](https://github.com/entireio/cli)
- [Entire docs — Installation](https://docs.entire.io/cli/installation)
- [Agent Hooks blog post](https://entire.io/blog/agent-hooks-the-integration-layer-between-entire-cli-and-your-agent)
- [Mager.co — Entire CLI: Version Control for Your Agent Sessions (2026-02-10)](https://www.mager.co/blog/2026-02-10-entire-cli/)
- Charter: `docs/project_plans/spikes/entire-io-integration-charter.md`
- Sister SPIKE: `docs/project_plans/spikes/remote-ccdash-streaming.md`
- ADR-009: `docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md`
