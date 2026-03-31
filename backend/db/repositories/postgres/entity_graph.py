"""Observed-entity graph repositories for Postgres links and tags."""
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

        try:
            return await self.db.fetchval(
                "INSERT INTO tags (name, color) VALUES ($1, $2) RETURNING id",
                name, color
            )
        except asyncpg.UniqueViolationError:
            return await self.db.fetchval("SELECT id FROM tags WHERE name = $1", name)

    async def tag_entity(self, entity_type: str, entity_id: str, tag_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO entity_tags (entity_type, entity_id, tag_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (entity_type, entity_id, tag_id) DO NOTHING
            """,
            entity_type, entity_id, tag_id,
        )

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
