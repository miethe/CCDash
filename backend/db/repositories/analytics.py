"""SQLite implementation of AnalyticsRepository."""
from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from backend.db.repositories.base import AnalyticsRepository

logger = logging.getLogger("ccdash.db.analytics")


class SqliteAnalyticsRepository(AnalyticsRepository):
    """SQLite implementation of analytics storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def insert_entry(self, entry: dict) -> int:
        """Insert a new analytics data point."""
        query = """
            INSERT INTO analytics_entries (
                project_id, metric_type, value, captured_at, period, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        # Ensure metadata is a JSON string if dict
        import json
        metadata = entry.get("metadata_json")
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        async with self.db.execute(
            query,
            (
                entry["project_id"],
                entry["metric_type"],
                entry["value"],
                entry["captured_at"],
                entry.get("period", "point"),
                metadata,
            ),
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def link_to_entity(self, analytics_id: int, entity_type: str, entity_id: str) -> None:
        """Link an analytics entry to a specific entity."""
        query = """
            INSERT OR IGNORE INTO analytics_entity_links (
                analytics_id, entity_type, entity_id
            ) VALUES (?, ?, ?)
        """
        await self.db.execute(query, (analytics_id, entity_type, entity_id))
        await self.db.commit()

    async def get_trends(
        self,
        project_id: str,
        metric_type: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Get time-series data for a metric."""
        query = """
            SELECT captured_at, value, metadata_json
            FROM analytics_entries
            WHERE project_id = ?
              AND metric_type = ?
              AND period = ?
        """
        params: list[Any] = [project_id, metric_type, period]

        if start:
            query += " AND captured_at >= ?"
            params.append(start)
        if end:
            query += " AND captured_at <= ?"
            params.append(end)

        query += " ORDER BY captured_at ASC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "captured_at": row[0],
                    "value": row[1],
                    "metadata": row[2],  # Client can parse JSON
                }
                for row in rows
            ]

    async def get_metric_types(self) -> list[dict]:
        """List all available metric definitions."""
        query = "SELECT id, display_name, unit, value_type, aggregation, description FROM metric_types"
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_latest_entries(self, project_id: str, metric_types: list[str]) -> dict[str, float]:
        """Get the most recent value for a list of metrics (helper for dashboards)."""
        if not metric_types:
            return {}
            
        placeholders = ",".join(["?"] * len(metric_types))
        query = f"""
            SELECT metric_type, value
            FROM analytics_entries
            WHERE project_id = ?
              AND metric_type IN ({placeholders})
              AND period = 'point'
            GROUP BY metric_type
            HAVING captured_at = MAX(captured_at)
        """
        params = [project_id] + metric_types
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
