"""SQLite implementation of SessionUsageRepository."""
from __future__ import annotations

import json

import aiosqlite

from backend.db.repositories.base import SessionUsageRepository


class SqliteSessionUsageRepository(SessionUsageRepository):
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def replace_session_usage(
        self,
        project_id: str,
        session_id: str,
        events: list[dict[str, object]],
        attributions: list[dict[str, object]],
    ) -> None:
        await self.db.execute(
            "DELETE FROM session_usage_events WHERE project_id = ? AND session_id = ?",
            (project_id, session_id),
        )
        for event in events:
            await self.db.execute(
                """
                INSERT INTO session_usage_events (
                    id, project_id, session_id, root_session_id, linked_session_id,
                    source_log_id, captured_at, event_kind, model, tool_name,
                    agent_name, token_family, delta_tokens, cost_usd_model_io, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("id", ""),
                    project_id,
                    session_id,
                    event.get("root_session_id", ""),
                    event.get("linked_session_id", ""),
                    event.get("source_log_id", ""),
                    event.get("captured_at", ""),
                    event.get("event_kind", ""),
                    event.get("model", ""),
                    event.get("tool_name", ""),
                    event.get("agent_name", ""),
                    event.get("token_family", ""),
                    int(event.get("delta_tokens", 0) or 0),
                    float(event.get("cost_usd_model_io", 0.0) or 0.0),
                    json.dumps(event.get("metadata_json") or {}),
                ),
            )
        for attribution in attributions:
            await self.db.execute(
                """
                INSERT INTO session_usage_attributions (
                    event_id, entity_type, entity_id, attribution_role,
                    weight, method, confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attribution.get("event_id", ""),
                    attribution.get("entity_type", ""),
                    attribution.get("entity_id", ""),
                    attribution.get("attribution_role", ""),
                    float(attribution.get("weight", 1.0) or 0.0),
                    attribution.get("method", ""),
                    float(attribution.get("confidence", 0.0) or 0.0),
                    json.dumps(attribution.get("metadata_json") or {}),
                ),
            )
        await self.db.commit()

    async def get_session_usage_events(self, session_id: str) -> list[dict[str, object]]:
        async with self.db.execute(
            "SELECT * FROM session_usage_events WHERE session_id = ? ORDER BY captured_at ASC, id ASC",
            (session_id,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def get_session_usage_attributions(self, session_id: str) -> list[dict[str, object]]:
        async with self.db.execute(
            """
            SELECT sua.*
            FROM session_usage_attributions sua
            JOIN session_usage_events sue ON sue.id = sua.event_id
            WHERE sue.session_id = ?
            ORDER BY sua.event_id ASC, sua.attribution_role ASC, sua.entity_type ASC, sua.entity_id ASC
            """,
            (session_id,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def count_usage_events(self, project_id: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM session_usage_events WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0] or 0) if row else 0
