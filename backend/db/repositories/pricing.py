"""SQLite repository for project-scoped pricing catalog entries."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_bool(value: object) -> int:
    return 1 if bool(value) else 0


class SqlitePricingCatalogRepository:
    """SQLite-backed pricing catalog storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def list_entries(self, project_id: str, platform_type: str | None = None) -> list[dict]:
        if platform_type:
            query = """
                SELECT *
                FROM pricing_catalog_entries
                WHERE project_id = ? AND platform_type = ?
                ORDER BY platform_type ASC, model_id ASC, id ASC
            """
            params: tuple[object, ...] = (project_id, platform_type)
        else:
            query = """
                SELECT *
                FROM pricing_catalog_entries
                WHERE project_id = ?
                ORDER BY platform_type ASC, model_id ASC, id ASC
            """
            params = (project_id,)
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_entry(self, project_id: str, platform_type: str, model_id: str = "") -> dict | None:
        async with self.db.execute(
            """
            SELECT *
            FROM pricing_catalog_entries
            WHERE project_id = ? AND platform_type = ? AND model_id = ?
            LIMIT 1
            """,
            (project_id, platform_type, model_id),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def upsert_entry(self, entry_data: dict, project_id: str) -> dict:
        now = _now_iso()
        platform_type = str(entry_data.get("platform_type") or entry_data.get("platformType") or "")
        model_id = str(entry_data.get("model_id") or entry_data.get("modelId") or "")
        await self.db.execute(
            """
            INSERT INTO pricing_catalog_entries (
                project_id, platform_type, model_id, context_window_size,
                input_cost_per_million, output_cost_per_million,
                cache_creation_cost_per_million, cache_read_cost_per_million,
                speed_multiplier_fast, source_type, source_updated_at,
                override_locked, sync_status, sync_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, platform_type, model_id) DO UPDATE SET
                context_window_size=excluded.context_window_size,
                input_cost_per_million=excluded.input_cost_per_million,
                output_cost_per_million=excluded.output_cost_per_million,
                cache_creation_cost_per_million=excluded.cache_creation_cost_per_million,
                cache_read_cost_per_million=excluded.cache_read_cost_per_million,
                speed_multiplier_fast=excluded.speed_multiplier_fast,
                source_type=excluded.source_type,
                source_updated_at=excluded.source_updated_at,
                override_locked=excluded.override_locked,
                sync_status=excluded.sync_status,
                sync_error=excluded.sync_error,
                updated_at=excluded.updated_at
            """,
            (
                project_id,
                platform_type,
                model_id,
                entry_data.get("context_window_size", entry_data.get("contextWindowSize")),
                entry_data.get("input_cost_per_million", entry_data.get("inputCostPerMillion")),
                entry_data.get("output_cost_per_million", entry_data.get("outputCostPerMillion")),
                entry_data.get("cache_creation_cost_per_million", entry_data.get("cacheCreationCostPerMillion")),
                entry_data.get("cache_read_cost_per_million", entry_data.get("cacheReadCostPerMillion")),
                entry_data.get("speed_multiplier_fast", entry_data.get("speedMultiplierFast")),
                str(entry_data.get("source_type") or entry_data.get("sourceType") or "bundled"),
                str(entry_data.get("source_updated_at") or entry_data.get("sourceUpdatedAt") or ""),
                _coerce_bool(entry_data.get("override_locked", entry_data.get("overrideLocked", False))),
                str(entry_data.get("sync_status") or entry_data.get("syncStatus") or "never"),
                str(entry_data.get("sync_error") or entry_data.get("syncError") or ""),
                str(entry_data.get("created_at") or entry_data.get("createdAt") or now),
                str(entry_data.get("updated_at") or entry_data.get("updatedAt") or now),
            ),
        )
        await self.db.commit()
        row = await self.get_entry(project_id, platform_type, model_id)
        return row or {}

    async def delete_entry(self, project_id: str, platform_type: str, model_id: str = "") -> None:
        await self.db.execute(
            """
            DELETE FROM pricing_catalog_entries
            WHERE project_id = ? AND platform_type = ? AND model_id = ?
            """,
            (project_id, platform_type, model_id),
        )
        await self.db.commit()

    def _row_to_dict(self, row: aiosqlite.Row) -> dict:
        return dict(row)
