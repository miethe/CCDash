"""Postgres implementation of canonical session message storage."""
from __future__ import annotations

import json
from typing import Any

import asyncpg

from backend.db.repositories.postgres._transactions import postgres_transaction


class PostgresSessionMessageRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_session_messages(self, session_id: str, messages: list[dict[str, object]]) -> None:
        async with postgres_transaction(self.db) as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", session_id)
            await conn.execute("DELETE FROM session_messages WHERE session_id = $1", session_id)
            if not messages:
                return

            records = []
            for message in messages:
                metadata = message.get("metadata")
                metadata_json = json.dumps(metadata) if isinstance(metadata, dict) else None
                token_usage = message.get("tokenUsage")
                input_tokens: int | None = None
                output_tokens: int | None = None
                cache_read_input_tokens: int | None = None
                cache_creation_input_tokens: int | None = None
                if isinstance(token_usage, dict):
                    _in = token_usage.get("inputTokens")
                    _out = token_usage.get("outputTokens")
                    _cr = token_usage.get("cacheReadInputTokens")
                    _cc = token_usage.get("cacheCreationInputTokens")
                    input_tokens = int(_in) if isinstance(_in, (int, float)) else None
                    output_tokens = int(_out) if isinstance(_out, (int, float)) else None
                    cache_read_input_tokens = int(_cr) if isinstance(_cr, (int, float)) else None
                    cache_creation_input_tokens = int(_cc) if isinstance(_cc, (int, float)) else None
                records.append(
                    (
                        session_id,
                        int(message.get("messageIndex", 0) or 0),
                        str(message.get("sourceLogId", "") or ""),
                        str(message.get("messageId", "") or ""),
                        str(message.get("role", "") or ""),
                        str(message.get("messageType", "") or ""),
                        str(message.get("content", "") or ""),
                        str(message.get("timestamp", "") or ""),
                        str(message.get("agentName", "") or ""),
                        message.get("toolName"),
                        message.get("toolCallId"),
                        message.get("relatedToolCallId"),
                        message.get("linkedSessionId"),
                        message.get("entryUuid"),
                        message.get("parentEntryUuid"),
                        str(message.get("rootSessionId", "") or ""),
                        str(message.get("conversationFamilyId", "") or ""),
                        str(message.get("threadSessionId", "") or ""),
                        str(message.get("parentSessionId", "") or ""),
                        str(message.get("sourceProvenance", "session_log_projection") or "session_log_projection"),
                        metadata_json,
                        input_tokens,
                        output_tokens,
                        cache_read_input_tokens,
                        cache_creation_input_tokens,
                    )
                )
            await conn.executemany(
                """
                INSERT INTO session_messages (
                    session_id, message_index, source_log_id, message_id, role, message_type,
                    content, event_timestamp, agent_name, tool_name, tool_call_id,
                    related_tool_call_id, linked_session_id, entry_uuid, parent_entry_uuid,
                    root_session_id, conversation_family_id, thread_session_id,
                    parent_session_id, source_provenance, metadata_json,
                    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14, $15, $16, $17, $18, $19, $20, $21,
                    $22, $23, $24, $25
                )
                ON CONFLICT (session_id, message_index) DO UPDATE SET
                    source_log_id = EXCLUDED.source_log_id,
                    message_id = EXCLUDED.message_id,
                    role = EXCLUDED.role,
                    message_type = EXCLUDED.message_type,
                    content = EXCLUDED.content,
                    event_timestamp = EXCLUDED.event_timestamp,
                    agent_name = EXCLUDED.agent_name,
                    tool_name = EXCLUDED.tool_name,
                    tool_call_id = EXCLUDED.tool_call_id,
                    related_tool_call_id = EXCLUDED.related_tool_call_id,
                    linked_session_id = EXCLUDED.linked_session_id,
                    entry_uuid = EXCLUDED.entry_uuid,
                    parent_entry_uuid = EXCLUDED.parent_entry_uuid,
                    root_session_id = EXCLUDED.root_session_id,
                    conversation_family_id = EXCLUDED.conversation_family_id,
                    thread_session_id = EXCLUDED.thread_session_id,
                    parent_session_id = EXCLUDED.parent_session_id,
                    source_provenance = EXCLUDED.source_provenance,
                    metadata_json = EXCLUDED.metadata_json,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    cache_read_input_tokens = EXCLUDED.cache_read_input_tokens,
                    cache_creation_input_tokens = EXCLUDED.cache_creation_input_tokens
                """,
                records,
            )

    async def list_by_session(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_messages WHERE session_id = $1 ORDER BY message_index ASC LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(row) for row in rows]

    async def search_messages(
        self,
        project_id: str,
        query: str,
        *,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses = ["s.project_id = $1", "TRIM(COALESCE(sm.content, '')) != ''"]
        params: list[Any] = [project_id]
        idx = 2

        search_terms = [term.strip().lower() for term in query.split() if term.strip()]
        if search_terms:
            term_clauses: list[str] = []
            for term in search_terms:
                term_clauses.append(f"LOWER(sm.content) LIKE ${idx}")
                params.append(f"%{term}%")
                idx += 1
            clauses.append("(" + " OR ".join(term_clauses) + ")")

        if feature_id:
            clauses.append(f"s.task_id = ${idx}")
            params.append(feature_id)
            idx += 1
        if conversation_family_id:
            clauses.append(f"(sm.conversation_family_id = ${idx} OR sm.root_session_id = ${idx + 1})")
            params.extend([conversation_family_id, conversation_family_id])
            idx += 2
        if session_id:
            clauses.append(f"sm.session_id = ${idx}")
            params.append(session_id)
            idx += 1

        params.append(limit)
        rows = await self.db.fetch(
            f"""
            SELECT
                sm.*,
                s.project_id,
                s.task_id AS feature_id,
                s.status AS session_status,
                s.started_at AS session_started_at
            FROM session_messages sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE {" AND ".join(clauses)}
            ORDER BY sm.event_timestamp DESC, sm.message_index DESC
            LIMIT ${idx}
            """,
            *params,
        )
        return [dict(row) for row in rows]
