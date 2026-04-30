"""PostgreSQL implementation of SessionUsageRepository."""
from __future__ import annotations

import json

import asyncpg

from backend.db.repositories.base import SessionUsageRepository


class PostgresSessionUsageRepository(SessionUsageRepository):
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_session_usage(
        self,
        project_id: str,
        session_id: str,
        events: list[dict[str, object]],
        attributions: list[dict[str, object]],
    ) -> None:
        await self.db.execute(
            "DELETE FROM session_usage_events WHERE project_id = $1 AND session_id = $2",
            project_id,
            session_id,
        )
        if events:
            await self.db.executemany(
                """
                INSERT INTO session_usage_events (
                    id, project_id, session_id, root_session_id, linked_session_id,
                    source_log_id, captured_at, event_kind, model, tool_name,
                    agent_name, token_family, delta_tokens, cost_usd_model_io, metadata_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                [
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
                    )
                    for event in events
                ],
            )
        if attributions:
            await self.db.executemany(
                """
                INSERT INTO session_usage_attributions (
                    event_id, entity_type, entity_id, attribution_role,
                    weight, method, confidence, metadata_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        attribution.get("event_id", ""),
                        attribution.get("entity_type", ""),
                        attribution.get("entity_id", ""),
                        attribution.get("attribution_role", ""),
                        float(attribution.get("weight", 1.0) or 0.0),
                        attribution.get("method", ""),
                        float(attribution.get("confidence", 0.0) or 0.0),
                        json.dumps(attribution.get("metadata_json") or {}),
                    )
                    for attribution in attributions
                ],
            )

    async def get_session_usage_events(self, session_id: str, limit: int = 5000, offset: int = 0) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        rows = await self.db.fetch(
            "SELECT * FROM session_usage_events WHERE session_id = $1 ORDER BY captured_at ASC, id ASC LIMIT $2 OFFSET $3",
            session_id,
            safe_limit,
            safe_offset,
        )
        return [dict(row) for row in rows]

    async def get_session_usage_attributions(self, session_id: str) -> list[dict[str, object]]:
        rows = await self.db.fetch(
            """
            SELECT sua.*
            FROM session_usage_attributions sua
            JOIN session_usage_events sue ON sue.id = sua.event_id
            WHERE sue.session_id = $1
            ORDER BY sua.event_id ASC, sua.attribution_role ASC, sua.entity_type ASC, sua.entity_id ASC
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    async def count_usage_events(self, project_id: str) -> int:
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS count FROM session_usage_events WHERE project_id = $1",
            project_id,
        )
        return int(row["count"] or 0) if row else 0
