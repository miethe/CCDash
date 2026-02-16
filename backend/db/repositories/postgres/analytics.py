"""PostgreSQL implementation of AnalyticsRepository."""
from __future__ import annotations

import json
from typing import Any
import asyncpg
from backend.db.repositories.base import AnalyticsRepository

class PostgresAnalyticsRepository(AnalyticsRepository):
    """PostgreSQL implementation of analytics storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def insert_entry(self, entry: dict) -> int:
        query = """
            INSERT INTO analytics_entries (
                project_id, metric_type, value, captured_at, period, metadata_json
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        metadata = entry.get("metadata_json")
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        id_val = await self.db.fetchval(
            query,
            entry["project_id"],
            entry["metric_type"],
            entry["value"],
            entry["captured_at"],
            entry.get("period", "point"),
            metadata,
        )
        return id_val

    async def link_to_entity(self, analytics_id: int, entity_type: str, entity_id: str) -> None:
        query = """
            INSERT INTO analytics_entity_links (
                analytics_id, entity_type, entity_id
            ) VALUES ($1, $2, $3)
            ON CONFLICT (analytics_id, entity_type, entity_id) DO NOTHING
        """
        await self.db.execute(query, analytics_id, entity_type, entity_id)

    async def get_trends(
        self,
        project_id: str,
        metric_type: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT captured_at, value, metadata_json
            FROM analytics_entries
            WHERE project_id = $1
              AND metric_type = $2
              AND period = $3
        """
        params = [project_id, metric_type, period]
        
        # In asyncpg, params are positional $1, $2, etc.
        # Need to dynamically build query with proper $n
        # Or simpler: just use generic count
        
        p_idx = 4
        if start:
            query += f" AND captured_at >= ${p_idx}"
            params.append(start)
            p_idx += 1
        if end:
            query += f" AND captured_at <= ${p_idx}"
            params.append(end)

        query += " ORDER BY captured_at ASC"

        rows = await self.db.fetch(query, *params)
        return [
            {
                "captured_at": row["captured_at"],
                "value": row["value"],
                "metadata": row["metadata_json"],
            }
            for row in rows
        ]

    async def get_metric_types(self) -> list[dict]:
        query = "SELECT id, display_name, unit, value_type, aggregation, description FROM metric_types"
        rows = await self.db.fetch(query)
        return [dict(r) for r in rows]

    async def get_latest_entries(self, project_id: str, metric_types: list[str]) -> dict[str, float]:
        if not metric_types:
            return {}

        # ANY($2) is how params work for arrays in Postgres usually, or separate args
        query = """
            SELECT metric_type, value
            FROM analytics_entries
            WHERE project_id = $1
              AND metric_type = ANY($2::text[])
              AND period = 'point'
            GROUP BY metric_type, value, captured_at
            HAVING captured_at = (
                SELECT MAX(sub.captured_at) 
                FROM analytics_entries sub 
                WHERE sub.metric_type = analytics_entries.metric_type 
                  AND sub.project_id = $1
                  AND sub.period = 'point'
            )
        """
        # The HAVING clause with MAX(captured_at) in standard SQL (SQLite/Postgres) 
        # normally works better with window functions for "latest per group", 
        # but the simple GROUP BY method in SQLite was:
        # GROUP BY metric_type HAVING captured_at = MAX(captured_at)
        # In Postgres, you must group by all non-aggregated columns if you select them, 
        # OR use DISTINCT ON.
        
        # Better query for Postgres: use DISTINCT ON
        query = """
            SELECT DISTINCT ON (metric_type) metric_type, value
            FROM analytics_entries
            WHERE project_id = $1
              AND metric_type = ANY($2::text[])
              AND period = 'point'
            ORDER BY metric_type, captured_at DESC
        """
        
        rows = await self.db.fetch(query, project_id, metric_types)
        return {row["metric_type"]: row["value"] for row in rows}
