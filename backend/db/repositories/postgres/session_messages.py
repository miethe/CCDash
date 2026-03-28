"""Postgres implementation of canonical session message storage."""
from __future__ import annotations

import json

import asyncpg


class PostgresSessionMessageRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_session_messages(self, session_id: str, messages: list[dict[str, object]]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM session_messages WHERE session_id = $1", session_id)
            if not messages:
                return

            records = []
            for message in messages:
                metadata = message.get("metadata")
                metadata_json = json.dumps(metadata) if isinstance(metadata, dict) else None
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
                    )
                )
            await self.db.executemany(
                """
                INSERT INTO session_messages (
                    session_id, message_index, source_log_id, message_id, role, message_type,
                    content, event_timestamp, agent_name, tool_name, tool_call_id,
                    related_tool_call_id, linked_session_id, entry_uuid, parent_entry_uuid,
                    root_session_id, conversation_family_id, thread_session_id,
                    parent_session_id, source_provenance, metadata_json
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
                )
                """,
                records,
            )

    async def list_by_session(self, session_id: str) -> list[dict[str, object]]:
        rows = await self.db.fetch(
            "SELECT * FROM session_messages WHERE session_id = $1 ORDER BY message_index ASC",
            session_id,
        )
        return [dict(row) for row in rows]
