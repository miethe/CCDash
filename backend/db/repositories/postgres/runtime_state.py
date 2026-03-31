"""Workspace and ingestion runtime state repositories for Postgres."""
from __future__ import annotations

import asyncpg


class PostgresSyncStateRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def get_sync_state(self, file_path: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM sync_state WHERE file_path = $1", file_path)
        return dict(row) if row else None

    async def upsert_sync_state(self, state: dict) -> None:
        await self.db.execute(
            """INSERT INTO sync_state (file_path, file_hash, file_mtime, entity_type, project_id, last_synced, parse_ms)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT(file_path) DO UPDATE SET
                 file_hash=EXCLUDED.file_hash, file_mtime=EXCLUDED.file_mtime,
                 last_synced=EXCLUDED.last_synced, parse_ms=EXCLUDED.parse_ms""",
            state["file_path"], state["file_hash"], state["file_mtime"],
            state["entity_type"], state["project_id"],
            state["last_synced"], state.get("parse_ms", 0),
        )

    async def delete_sync_state(self, file_path: str) -> None:
        await self.db.execute("DELETE FROM sync_state WHERE file_path = $1", file_path)

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch("SELECT * FROM sync_state WHERE project_id = $1", project_id)
        else:
            rows = await self.db.fetch("SELECT * FROM sync_state")
        return [dict(r) for r in rows]


class PostgresAlertConfigRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM alert_configs WHERE project_id = $1 OR project_id IS NULL",
                project_id,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM alert_configs")
        return [dict(r) for r in rows]

    async def upsert(self, config_data: dict) -> None:
        await self.db.execute(
            """INSERT INTO alert_configs (id, project_id, name, metric, operator, threshold, is_active, scope)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT(id) DO UPDATE SET
                 name=EXCLUDED.name, metric=EXCLUDED.metric, operator=EXCLUDED.operator,
                 threshold=EXCLUDED.threshold, is_active=EXCLUDED.is_active, scope=EXCLUDED.scope""",
            config_data["id"], config_data.get("project_id"),
            config_data["name"], config_data["metric"],
            config_data["operator"], config_data["threshold"],
            1 if config_data.get("is_active", True) else 0,
            config_data.get("scope", "session"),
        )

    async def delete(self, config_id: str) -> None:
        await self.db.execute("DELETE FROM alert_configs WHERE id = $1", config_id)
