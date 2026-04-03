"""SQLite implementation of canonical session message storage."""
from __future__ import annotations

import json
from typing import Any

import aiosqlite


class SqliteSessionMessageRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def replace_session_messages(self, session_id: str, messages: list[dict[str, object]]) -> None:
        await self.db.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
        for message in messages:
            metadata = message.get("metadata")
            metadata_json = json.dumps(metadata) if isinstance(metadata, dict) else None
            await self.db.execute(
                """
                INSERT INTO session_messages (
                    session_id, message_index, source_log_id, message_id, role, message_type,
                    content, event_timestamp, agent_name, tool_name, tool_call_id,
                    related_tool_call_id, linked_session_id, entry_uuid, parent_entry_uuid,
                    root_session_id, conversation_family_id, thread_session_id,
                    parent_session_id, source_provenance, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                ),
            )
        await self.db.commit()

    async def list_by_session(self, session_id: str) -> list[dict[str, object]]:
        async with self.db.execute(
            "SELECT * FROM session_messages WHERE session_id = ? ORDER BY message_index ASC",
            (session_id,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

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
        clauses = ["s.project_id = ?", "TRIM(COALESCE(sm.content, '')) != ''"]
        params: list[Any] = [project_id]

        search_terms = [term.strip().lower() for term in query.split() if term.strip()]
        if search_terms:
            term_clauses = ["LOWER(sm.content) LIKE ?" for _ in search_terms]
            clauses.append("(" + " OR ".join(term_clauses) + ")")
            params.extend([f"%{term}%" for term in search_terms])

        if feature_id:
            clauses.append("s.task_id = ?")
            params.append(feature_id)
        if conversation_family_id:
            clauses.append("(sm.conversation_family_id = ? OR sm.root_session_id = ?)")
            params.extend([conversation_family_id, conversation_family_id])
        if session_id:
            clauses.append("sm.session_id = ?")
            params.append(session_id)

        params.append(limit)
        async with self.db.execute(
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
            LIMIT ?
            """,
            tuple(params),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]
