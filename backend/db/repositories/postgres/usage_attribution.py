"""PostgreSQL implementation of SessionUsageRepository."""
from __future__ import annotations

import json
from typing import Any

import asyncpg

from backend.db.repositories.base import SessionUsageRepository
from backend.db.repositories.postgres._transactions import postgres_transaction


def _to_int(v: object, default: int = 0) -> int:
    """Type-safe int coercion for dict.get() values typed as object."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default
    return default


def _to_float(v: object, default: float = 0.0) -> float:
    """Type-safe float coercion for dict.get() values typed as object."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default
    return default


class PostgresSessionUsageRepository(SessionUsageRepository):
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_session_usage(
        self,
        project_id: str,
        session_id: str,
        events: list[dict[str, object]],
        attributions: list[dict[str, object]],
        *,
        conn: Any = None,
    ) -> None:
        """Replace all usage events and attributions for a session atomically.

        When ``conn`` is provided (Postgres path inside a parent transaction) the
        three write operations (DELETE events, INSERT events, INSERT attributions)
        execute directly on ``conn`` — no new transaction is opened.

        When ``conn`` is ``None`` (standalone caller) a new transaction is
        acquired from the pool so the three operations are atomic, fixing the
        original three-separate-acquisitions bug.
        """
        if conn is not None:
            await self._replace_usage_impl(conn, project_id, session_id, events, attributions)
        else:
            async with postgres_transaction(self.db) as _conn:
                await self._replace_usage_impl(_conn, project_id, session_id, events, attributions)

    async def _replace_usage_impl(
        self,
        conn: Any,
        project_id: str,
        session_id: str,
        events: list[dict[str, object]],
        attributions: list[dict[str, object]],
    ) -> None:
        """Execute the three-table write sequence on an already-acquired connection."""
        await conn.execute(
            "DELETE FROM session_usage_events WHERE project_id = $1 AND session_id = $2",
            project_id,
            session_id,
        )
        if events:
            await conn.executemany(
                """
                INSERT INTO session_usage_events (
                    id, project_id, session_id, root_session_id, linked_session_id,
                    source_log_id, captured_at, event_kind, model, tool_name,
                    agent_name, token_family, delta_tokens, cost_usd_model_io, metadata_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (id) DO NOTHING
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
                        _to_int(event.get("delta_tokens")),
                        _to_float(event.get("cost_usd_model_io")),
                        json.dumps(event.get("metadata_json") or {}),
                    )
                    for event in events
                ],
            )
        if attributions:
            await conn.executemany(
                """
                INSERT INTO session_usage_attributions (
                    event_id, entity_type, entity_id, attribution_role,
                    weight, method, confidence, metadata_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (event_id, entity_type, entity_id, attribution_role, method) DO NOTHING
                """,
                [
                    (
                        attribution.get("event_id", ""),
                        attribution.get("entity_type", ""),
                        attribution.get("entity_id", ""),
                        attribution.get("attribution_role", ""),
                        _to_float(attribution.get("weight"), default=1.0),
                        attribution.get("method", ""),
                        _to_float(attribution.get("confidence")),
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
