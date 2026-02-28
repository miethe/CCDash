"""PostgreSQL implementation of TestDefinitionRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg


class PostgresTestDefinitionRepository:
    """PostgreSQL-backed test definition storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, definition_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = (
            project_id or definition_data.get("project_id") or definition_data.get("projectId", "")
        )
        tags = definition_data.get("tags", definition_data.get("tags_json", []))
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []

        query = """
            INSERT INTO test_definitions (
                test_id, project_id, path, name, framework, tags_json, owner, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            ON CONFLICT(test_id) DO UPDATE SET
                project_id=EXCLUDED.project_id,
                path=EXCLUDED.path,
                name=EXCLUDED.name,
                framework=EXCLUDED.framework,
                tags_json=EXCLUDED.tags_json,
                owner=EXCLUDED.owner,
                updated_at=EXCLUDED.updated_at
        """
        await self.db.execute(
            query,
            definition_data["test_id"],
            resolved_project_id,
            definition_data.get("path", ""),
            definition_data.get("name", ""),
            definition_data.get("framework", "pytest"),
            json.dumps(tags or []),
            definition_data.get("owner", ""),
            definition_data.get("created_at", now),
            definition_data.get("updated_at", now),
        )

    async def get_by_id(self, test_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM test_definitions WHERE test_id = $1", test_id)
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_definitions
                WHERE project_id = $1
                ORDER BY path ASC, name ASC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM test_definitions ORDER BY path ASC, name ASC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
