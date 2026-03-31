"""Workspace and ingestion runtime state repositories."""
from __future__ import annotations

import aiosqlite


class SqliteSyncStateRepository:
    """Track file sync state for incremental scanning."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_sync_state(self, file_path: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM sync_state WHERE file_path = ?", (file_path,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def upsert_sync_state(self, state: dict) -> None:
        await self.db.execute(
            """INSERT INTO sync_state (file_path, file_hash, file_mtime, entity_type, project_id, last_synced, parse_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                 file_hash=excluded.file_hash, file_mtime=excluded.file_mtime,
                 last_synced=excluded.last_synced, parse_ms=excluded.parse_ms""",
            (
                state["file_path"], state["file_hash"], state["file_mtime"],
                state["entity_type"], state["project_id"],
                state["last_synced"], state.get("parse_ms", 0),
            ),
        )
        await self.db.commit()

    async def delete_sync_state(self, file_path: str) -> None:
        await self.db.execute("DELETE FROM sync_state WHERE file_path = ?", (file_path,))
        await self.db.commit()

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM sync_state WHERE project_id = ?", (project_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with self.db.execute("SELECT * FROM sync_state") as cur:
            return [dict(r) for r in await cur.fetchall()]


class SqliteAlertConfigRepository:
    """Persisted alert configurations."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM alert_configs WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with self.db.execute("SELECT * FROM alert_configs") as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def upsert(self, config_data: dict) -> None:
        await self.db.execute(
            """INSERT INTO alert_configs (id, project_id, name, metric, operator, threshold, is_active, scope)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, metric=excluded.metric, operator=excluded.operator,
                 threshold=excluded.threshold, is_active=excluded.is_active, scope=excluded.scope""",
            (
                config_data["id"], config_data.get("project_id"),
                config_data["name"], config_data["metric"],
                config_data["operator"], config_data["threshold"],
                1 if config_data.get("is_active", True) else 0,
                config_data.get("scope", "session"),
            ),
        )
        await self.db.commit()

    async def delete(self, config_id: str) -> None:
        await self.db.execute("DELETE FROM alert_configs WHERE id = ?", (config_id,))
        await self.db.commit()
