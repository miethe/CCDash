"""PostgreSQL implementation of entity links, tags, sync state, alerts."""
from __future__ import annotations

from datetime import datetime, timezone
import asyncpg

class PostgresEntityLinkRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, link_data: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        return await self.db.fetchval(
            """
            INSERT INTO entity_links (
                source_type, source_id, target_type, target_id,
                link_type, origin, confidence, depth, sort_order,
                metadata_json, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO UPDATE SET
                origin = EXCLUDED.origin,
                confidence = EXCLUDED.confidence,
                depth = EXCLUDED.depth,
                sort_order = EXCLUDED.sort_order,
                metadata_json = EXCLUDED.metadata_json
            RETURNING id
            """,
            link_data["source_type"],
            link_data["source_id"],
            link_data["target_type"],
            link_data["target_id"],
            link_data.get("link_type", "related"),
            link_data.get("origin", "auto"),
            link_data.get("confidence", 1.0),
            link_data.get("depth", 0),
            link_data.get("sort_order", 0),
            link_data.get("metadata_json"),
            now,
        )

    async def get_links_for(
        self, entity_type: str, entity_id: str, link_type: str | None = None,
    ) -> list[dict]:
        if link_type:
            rows = await self.db.fetch(
                """SELECT * FROM entity_links
                   WHERE ((source_type = $1 AND source_id = $2)
                       OR (target_type = $3 AND target_id = $4))
                     AND link_type = $5""",
                entity_type, entity_id, entity_type, entity_id, link_type
            )
        else:
            rows = await self.db.fetch(
                """SELECT * FROM entity_links
                   WHERE (source_type = $1 AND source_id = $2)
                      OR (target_type = $3 AND target_id = $4)""",
                entity_type, entity_id, entity_type, entity_id
            )
        return [dict(r) for r in rows]

    async def get_tree(self, entity_type: str, entity_id: str) -> dict:
        children = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE source_type = $1 AND source_id = $2 AND link_type = 'child'
               ORDER BY depth, sort_order""",
            entity_type, entity_id
        )
        parents = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE target_type = $1 AND target_id = $2 AND link_type = 'child'""",
            entity_type, entity_id
        )
        related = await self.db.fetch(
            """SELECT * FROM entity_links
               WHERE ((source_type = $1 AND source_id = $2)
                   OR (target_type = $3 AND target_id = $4))
                 AND link_type = 'related'""",
            entity_type, entity_id, entity_type, entity_id
        )
        return {
            "children": [dict(r) for r in children],
            "parents": [dict(r) for r in parents],
            "related": [dict(r) for r in related],
        }

    async def delete_auto_links(self, source_type: str, source_id: str) -> None:
        await self.db.execute(
            "DELETE FROM entity_links WHERE source_type = $1 AND source_id = $2 AND origin = 'auto'",
            source_type, source_id,
        )

    async def delete_link(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        link_type: str = "related",
    ) -> None:
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE source_type = $1 AND source_id = $2
                 AND target_type = $3 AND target_id = $4
                 AND link_type = $5""",
            source_type, source_id, target_type, target_id, link_type,
        )

    async def delete_all_for(self, entity_type: str, entity_id: str) -> None:
        await self.db.execute(
            """DELETE FROM entity_links
               WHERE (source_type = $1 AND source_id = $2)
                  OR (target_type = $3 AND target_id = $4)""",
            entity_type, entity_id, entity_type, entity_id
        )


class PostgresTagRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def get_or_create(self, name: str, color: str = "") -> int:
        row = await self.db.fetchrow("SELECT id FROM tags WHERE name = $1", name)
        if row:
            return row["id"]

        # Insert handles conflict if unique index exists
        # Postgres migration has UNIQUE(name) on tags
        # so we can use ON CONFLICT DO NOTHING RETURNING id? 
        # But RETURNING returns null on conflict do nothing.
        # Check-then-insert or INSERT ON CONFLICT DO UPDATE...
        
        try:
            val = await self.db.fetchval(
                "INSERT INTO tags (name, color) VALUES ($1, $2) RETURNING id",
                name, color
            )
            return val
        except asyncpg.UniqueViolationError:
            val = await self.db.fetchval("SELECT id FROM tags WHERE name = $1", name)
            return val

    async def tag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        # Entity tags PK is (entity_type, entity_id, tag_id)
        query = """
            INSERT INTO entity_tags (entity_type, entity_id, tag_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (entity_type, entity_id, tag_id) DO NOTHING
        """
        await self.db.execute(query, entity_type, entity_id, tag_id)

    async def untag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            "DELETE FROM entity_tags WHERE entity_type = $1 AND entity_id = $2 AND tag_id = $3",
            entity_type, entity_id, tag_id
        )

    async def get_tags_for(self, entity_type: str, entity_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT t.id, t.name, t.color FROM tags t
               JOIN entity_tags et ON t.id = et.tag_id
               WHERE et.entity_type = $1 AND et.entity_id = $2""",
            entity_type, entity_id
        )
        return [dict(r) for r in rows]

    async def get_entities_for_tag(self, tag_id: int) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT entity_type, entity_id FROM entity_tags WHERE tag_id = $1",
            tag_id
        )
        return [dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM tags ORDER BY name")
        return [dict(r) for r in rows]


class PostgresSyncStateRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def get_sync_state(self, file_path: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM sync_state WHERE file_path = $1", file_path)
        return dict(row) if row else None

    async def upsert_sync_state(self, state: dict) -> None:
        # sync_state has PRIMARY KEY file_path
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
        # alert_configs has PRIMARY KEY id
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
