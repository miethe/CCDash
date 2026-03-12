"""PostgreSQL repository for project-scoped pricing catalog entries."""
from __future__ import annotations

from datetime import datetime, timezone

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresPricingCatalogRepository:
    """PostgreSQL-backed pricing catalog storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def list_entries(self, project_id: str, platform_type: str | None = None) -> list[dict]:
        if platform_type:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM pricing_catalog_entries
                WHERE project_id = $1 AND platform_type = $2
                ORDER BY platform_type ASC, model_id ASC, id ASC
                """,
                project_id,
                platform_type,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM pricing_catalog_entries
                WHERE project_id = $1
                ORDER BY platform_type ASC, model_id ASC, id ASC
                """,
                project_id,
            )
        return [dict(row) for row in rows]

    async def get_entry(self, project_id: str, platform_type: str, model_id: str = "") -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT *
            FROM pricing_catalog_entries
            WHERE project_id = $1 AND platform_type = $2 AND model_id = $3
            LIMIT 1
            """,
            project_id,
            platform_type,
            model_id,
        )
        return dict(row) if row else None

    async def upsert_entry(self, entry_data: dict, project_id: str) -> dict:
        now = _now_iso()
        platform_type = str(entry_data.get("platform_type") or entry_data.get("platformType") or "")
        model_id = str(entry_data.get("model_id") or entry_data.get("modelId") or "")
        row = await self.db.fetchrow(
            """
            INSERT INTO pricing_catalog_entries (
                project_id, platform_type, model_id, context_window_size,
                input_cost_per_million, output_cost_per_million,
                cache_creation_cost_per_million, cache_read_cost_per_million,
                speed_multiplier_fast, source_type, source_updated_at,
                override_locked, sync_status, sync_error, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT(project_id, platform_type, model_id) DO UPDATE SET
                context_window_size=EXCLUDED.context_window_size,
                input_cost_per_million=EXCLUDED.input_cost_per_million,
                output_cost_per_million=EXCLUDED.output_cost_per_million,
                cache_creation_cost_per_million=EXCLUDED.cache_creation_cost_per_million,
                cache_read_cost_per_million=EXCLUDED.cache_read_cost_per_million,
                speed_multiplier_fast=EXCLUDED.speed_multiplier_fast,
                source_type=EXCLUDED.source_type,
                source_updated_at=EXCLUDED.source_updated_at,
                override_locked=EXCLUDED.override_locked,
                sync_status=EXCLUDED.sync_status,
                sync_error=EXCLUDED.sync_error,
                updated_at=EXCLUDED.updated_at
            RETURNING *
            """,
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
            bool(entry_data.get("override_locked", entry_data.get("overrideLocked", False))),
            str(entry_data.get("sync_status") or entry_data.get("syncStatus") or "never"),
            str(entry_data.get("sync_error") or entry_data.get("syncError") or ""),
            str(entry_data.get("created_at") or entry_data.get("createdAt") or now),
            str(entry_data.get("updated_at") or entry_data.get("updatedAt") or now),
        )
        return dict(row) if row else {}

    async def delete_entry(self, project_id: str, platform_type: str, model_id: str = "") -> None:
        await self.db.execute(
            """
            DELETE FROM pricing_catalog_entries
            WHERE project_id = $1 AND platform_type = $2 AND model_id = $3
            """,
            project_id,
            platform_type,
            model_id,
        )
