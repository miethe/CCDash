"""PostgreSQL implementation of TestDomainRepository."""
from __future__ import annotations

from datetime import datetime, timezone

import asyncpg


class PostgresTestDomainRepository:
    """PostgreSQL-backed test domain storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, domain_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or domain_data.get("project_id") or domain_data.get("projectId", "")
        query = """
            INSERT INTO test_domains (
                domain_id, project_id, name, parent_id, description, tier, sort_order, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT(domain_id) DO UPDATE SET
                project_id=EXCLUDED.project_id,
                name=EXCLUDED.name,
                parent_id=EXCLUDED.parent_id,
                description=EXCLUDED.description,
                tier=EXCLUDED.tier,
                sort_order=EXCLUDED.sort_order,
                updated_at=EXCLUDED.updated_at
        """
        await self.db.execute(
            query,
            domain_data["domain_id"],
            resolved_project_id,
            domain_data.get("name", ""),
            domain_data.get("parent_id"),
            domain_data.get("description", ""),
            domain_data.get("tier", "core"),
            domain_data.get("sort_order", 0),
            domain_data.get("created_at", now),
            domain_data.get("updated_at", now),
        )

    async def get_by_id(self, domain_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM test_domains WHERE domain_id = $1", domain_id)
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_domains
                WHERE project_id = $1
                ORDER BY sort_order ASC, name ASC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM test_domains ORDER BY sort_order ASC, name ASC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
