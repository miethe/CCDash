# Session Transcript Contract Guide

## Purpose

Phase 1 freezes the canonical transcript contract that later enterprise transcript, embedding, and intelligence work depends on.

## Canonical Row Semantics

`session_messages` is the canonical transcript store. Each row must preserve these meanings:

| Field | Meaning |
| --- | --- |
| `source_log_id` | Stable compatibility identifier for the legacy session log payload and router DTOs. |
| `message_id` | Platform-native message identity when available. Fallback order is `rawMessageId`, `entryUuid`, `messageId`, then `source_log_id`. |
| `message_index` | Per-session ordering used for deterministic transcript replay. |
| `role` | Canonical author role. `agent` input is normalized to `assistant`; user and system remain unchanged. |
| `message_type` | Compatibility-safe transcript event type (`message`, `tool`, `thought`, `command`, `system`, `subagent_start`, and future compatible variants). |
| `source_provenance` | Origin of the canonical row. Explicit metadata wins; otherwise platform defaults apply (`claude_code_jsonl`, `codex_jsonl`), then `session_log_projection`. |
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
2. Tool calls populate `toolArgs`, `toolOutput`, and `toolStatus` in canonical metadata when present.
3. Canonical `role` is derived from the parser log speaker, not stored ad hoc per platform.
4. Provenance defaults are inferred from `platformType` only when explicit metadata does not already provide a source.

## Testing Expectations

Phase 1 contract coverage must verify:

1. canonical row projection preserves lineage and provenance;
2. compatibility payloads still expose the current API speaker and metadata shape;
3. platform-specific provenance defaults are deterministic;
4. canonical reads still fall back to legacy logs when no canonical rows exist.
