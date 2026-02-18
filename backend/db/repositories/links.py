"""SQLite implementation of EntityLinkRepository, TagRepository, SyncStateRepository, AlertConfigRepository."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite


class SqliteEntityLinkRepository:
    """Entity links with tree queries and bidirectional lookups."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, link_data: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.execute(
            """INSERT INTO entity_links (
                source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin=excluded.origin, confidence=excluded.confidence,
                depth=excluded.depth, sort_order=excluded.sort_order,
                metadata_json=excluded.metadata_json
            """,
            (
                link_data["source_type"], link_data["source_id"],
                link_data["target_type"], link_data["target_id"],
                link_data.get("link_type", "related"),
                link_data.get("origin", "auto"),
                link_data.get("confidence", 1.0),
                link_data.get("depth", 0),
                link_data.get("sort_order", 0),
                link_data.get("metadata_json"),
                now,
            ),
        ) as cur:
            await self.db.commit()
            return cur.lastrowid or 0

    async def get_links_for(
        self, entity_type: str, entity_id: str, link_type: str | None = None,
    ) -> list[dict]:
        if link_type:
            query = """SELECT * FROM entity_links
                       WHERE ((source_type = ? AND source_id = ?)
                           OR (target_type = ? AND target_id = ?))
                         AND link_type = ?"""
            params = (entity_type, entity_id, entity_type, entity_id, link_type)
        else:
            query = """SELECT * FROM entity_links
                       WHERE (source_type = ? AND source_id = ?)
                          OR (target_type = ? AND target_id = ?)"""
            params = (entity_type, entity_id, entity_type, entity_id)

        async with self.db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_tree(self, entity_type: str, entity_id: str) -> dict:
        """Get full tree: parents, children, siblings."""
        # Children
        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE source_type = ? AND source_id = ? AND link_type = 'child'
               ORDER BY depth, sort_order""",
            (entity_type, entity_id),
        ) as cur:
            children = [dict(r) for r in await cur.fetchall()]

        # Parents (who has this entity as child)
        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE target_type = ? AND target_id = ? AND link_type = 'child'""",
            (entity_type, entity_id),
        ) as cur:
            parents = [dict(r) for r in await cur.fetchall()]

        # Related
        async with self.db.execute(
            """SELECT * FROM entity_links
               WHERE ((source_type = ? AND source_id = ?)
                   OR (target_type = ? AND target_id = ?))
                 AND link_type = 'related'""",
            (entity_type, entity_id, entity_type, entity_id),
        ) as cur:
            related = [dict(r) for r in await cur.fetchall()]

        return {"children": children, "parents": parents, "related": related}

    async def delete_auto_links(self, source_type: str, source_id: str) -> None:
        await self.db.execute(
            "DELETE FROM entity_links WHERE source_type = ? AND source_id = ? AND origin = 'auto'",
            (source_type, source_id),
        )
        await self.db.commit()

    async def delete_all_for(self, entity_type: str, entity_id: str) -> None:
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE (source_type = ? AND source_id = ?)
                  OR (target_type = ? AND target_id = ?)""",
            (entity_type, entity_id, entity_type, entity_id),
        )
        await self.db.commit()


class SqliteTagRepository:
    """Cross-entity tag management."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_or_create(self, name: str, color: str = "") -> int:
        async with self.db.execute("SELECT id FROM tags WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]

        async with self.db.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color)
        ) as cur:
            await self.db.commit()
            return cur.lastrowid or 0

    async def tag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO entity_tags (entity_type, entity_id, tag_id) VALUES (?, ?, ?)",
            (entity_type, entity_id, tag_id),
        )
        await self.db.commit()

    async def untag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "DELETE FROM entity_tags WHERE entity_type = ? AND entity_id = ? AND tag_id = ?",
            (entity_type, entity_id, tag_id),
        )
        await self.db.commit()

    async def get_tags_for(self, entity_type: str, entity_id: str) -> list[dict]:
        async with self.db.execute(
            """SELECT t.id, t.name, t.color FROM tags t
               JOIN entity_tags et ON t.id = et.tag_id
               WHERE et.entity_type = ? AND et.entity_id = ?""",
            (entity_type, entity_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_entities_for_tag(self, tag_id: int) -> list[dict]:
        async with self.db.execute(
            "SELECT entity_type, entity_id FROM entity_tags WHERE tag_id = ?",
            (tag_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_all(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM tags ORDER BY name") as cur:
            return [dict(r) for r in await cur.fetchall()]


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
        else:
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
        else:
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
