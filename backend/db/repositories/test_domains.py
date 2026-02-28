"""SQLite implementation of TestDomainRepository."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import aiosqlite


class SqliteTestDomainRepository:
    """SQLite-backed test domain storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, domain_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or domain_data.get("project_id") or domain_data.get("projectId", "")
        await self.db.execute(
            """
            INSERT INTO test_domains (
                domain_id, project_id, name, parent_id, description, tier, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain_id) DO UPDATE SET
                project_id=excluded.project_id,
                name=excluded.name,
                parent_id=excluded.parent_id,
                description=excluded.description,
                tier=excluded.tier,
                sort_order=excluded.sort_order,
                updated_at=excluded.updated_at
            """,
            (
                domain_data["domain_id"],
                resolved_project_id,
                domain_data.get("name", ""),
                domain_data.get("parent_id"),
                domain_data.get("description", ""),
                domain_data.get("tier", "core"),
                domain_data.get("sort_order", 0),
                domain_data.get("created_at", now),
                domain_data.get("updated_at", now),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, domain_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM test_domains WHERE domain_id = ?",
            (domain_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            async with self.db.execute(
                """
                SELECT *
                FROM test_domains
                WHERE project_id = ?
                ORDER BY sort_order ASC, name ASC
                LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self.db.execute(
                "SELECT * FROM test_domains ORDER BY sort_order ASC, name ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def list_tree(self, project_id: str) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_domains
            WHERE project_id = ?
            ORDER BY sort_order ASC, name ASC
            """,
            (project_id,),
        ) as cur:
            rows = [dict(row) for row in await cur.fetchall()]

        nodes: dict[str, dict] = {}
        roots: list[dict] = []
        for row in rows:
            item = dict(row)
            item["children"] = []
            nodes[item["domain_id"]] = item

        for row in rows:
            domain_id = row["domain_id"]
            parent_id = row.get("parent_id")
            node = nodes[domain_id]
            if parent_id and parent_id in nodes:
                nodes[parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    async def get_or_create_by_name(
        self,
        project_id: str,
        name: str,
        parent_id: str | None = None,
        tier: str = "core",
        description: str = "",
    ) -> dict:
        async with self.db.execute(
            """
            SELECT *
            FROM test_domains
            WHERE project_id = ?
              AND name = ?
              AND ((parent_id IS NULL AND ? IS NULL) OR parent_id = ?)
            LIMIT 1
            """,
            (project_id, name, parent_id, parent_id),
        ) as cur:
            existing = await cur.fetchone()
            if existing:
                return dict(existing)

        domain_id = self._build_domain_id(project_id, name, parent_id)
        await self.upsert(
            {
                "domain_id": domain_id,
                "project_id": project_id,
                "name": name,
                "parent_id": parent_id,
                "description": description,
                "tier": tier,
            },
            project_id=project_id,
        )
        created = await self.get_by_id(domain_id)
        return created or {
            "domain_id": domain_id,
            "project_id": project_id,
            "name": name,
            "parent_id": parent_id,
            "description": description,
            "tier": tier,
            "sort_order": 0,
            "children": [],
        }

    def _build_domain_id(self, project_id: str, name: str, parent_id: str | None) -> str:
        seed = f"{project_id}::{parent_id or ''}::{name.strip().lower()}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"dom_{digest}"
