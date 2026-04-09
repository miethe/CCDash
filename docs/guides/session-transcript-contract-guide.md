# Session Transcript Contract Guide

## Purpose

Phase 1 freezes the canonical transcript contract that later enterprise transcript, embedding, and intelligence work depends on.

## Canonical Row Semantics

`session_messages` is the canonical transcript store. Each row must preserve these meanings:

| Field | Meaning |
| --- | --- |
| `source_log_id` | Stable compatibility identifier for the legacy session log payload and router DTOs. |
| `message_id` | Platform-native message identity when available. Claude tool logs use the tool-use ID, Codex tool logs use `call_id`, and other Codex events synthesize a deterministic `codex-*` ID when the source transcript has no native message identifier. |
| `message_index` | Per-session ordering used for deterministic transcript replay. |
| `role` | Canonical author role. `agent` input is normalized to `assistant`; user and system remain unchanged. |
| `message_type` | Compatibility-safe transcript event type (`message`, `tool`, `thought`, `command`, `system`, `subagent_start`, and future compatible variants). |
| `source_provenance` | Origin of the canonical row. Parser-stamped metadata wins (`claude_code_jsonl`, `codex.user_message`, `codex.function_call`, `codex.agent_reasoning`, etc.); otherwise platform defaults apply, then `session_log_projection`. |
| `entry_uuid` / `parent_entry_uuid` | Entry-level lineage links from the source transcript when present. |
| `root_session_id` | Root of the session family tree. |
| `conversation_family_id` | Family identifier for cross-session transcript analysis. |
| `thread_session_id` | Concrete session thread the row belongs to. |
| `parent_session_id` | Parent thread when the current session is derived or forked. |

## Compatibility Projection Rules

Current session detail APIs remain stable by projecting canonical rows back into the legacy log shape:

| Canonical field | API field |
| --- | --- |
| `source_log_id` | `id` |
| `event_timestamp` | `timestamp` |
| `role=assistant` | `speaker=agent` |
| `role=user/system` | same `speaker` value |
| `message_type` | `type` |
| `content` | `content` |
| `agent_name` | `agentName` |
| `linked_session_id` | `linkedSessionId` |
| `related_tool_call_id` | `relatedToolCallId` |

Metadata rules:

1. `sourceProvenance` is always present in the API payload.
2. `entryUuid`, `parentUuid`, and `rawMessageId` are backfilled from canonical columns when absent in `metadata_json`.
3. Tool payloads continue to use the legacy `toolCall` object so current consumers do not need a DTO migration.
4. If a session has no canonical rows, the service falls back to legacy `session_logs`.

## Ingest Normalization Rules

Normalization happens before persistence when session logs are projected into canonical rows:

1. Metadata is copied before enrichment so projection does not mutate parser-owned log payloads.
2. Parsers stamp `sourceProvenance`, `messageRole`, and a stable `messageId` before the projection layer persists canonical rows.
3. Tool calls populate `toolArgs`, `toolOutput`, and `toolStatus` on parser-owned logs and remain available in canonical metadata when present.
4. Canonical `role` is derived from the parser log speaker, not stored ad hoc per platform.
5. Provenance defaults are inferred from `platformType` only when explicit parser metadata does not already provide a source.

## Embedding Block Strategy

Phase 2 uses a mixed transcript block strategy so semantic search can stay precise without losing local context:

| Block kind | Embedding unit | Purpose |
| --- | --- | --- |
| `message` | One substantive canonical `session_messages` row | Preserves exact source evidence for prompts, replies, and tool-bearing turns. |
| `window` | Five consecutive canonical rows in the same session thread | Captures nearby context for search recall around decisions, corrections, and tool usage. |

Block identity rules:

1. Block hashes are content-addressed from session identity, block kind, ordered row membership, normalized content, provenance, role, message type, and canonical message IDs.
2. Identical block hashes dedupe to one stored embedding row.
3. When a canonical row changes, its direct message block is recomputed and any overlapping window block is regenerated with a new hash.
4. Stale hashes are superseded, not mutated in place, so backfills remain restart-safe.
5. The embedding table is enterprise-only; local SQLite keeps canonical transcript rows but does not require `pgvector` or materialize embeddings.

## Testing Expectations

Contract coverage must verify:

1. canonical row projection preserves lineage and provenance;
2. compatibility payloads still expose the current API speaker and metadata shape;
3. parser-owned Claude and Codex logs stamp deterministic provenance, role, identity, and tool metadata before projection;
4. platform-specific provenance defaults are deterministic when parser metadata is absent;
5. canonical reads still fall back to legacy logs when no canonical rows exist;
6. the Phase 2 mixed block strategy stays deterministic, additive, and enterprise-scoped.
