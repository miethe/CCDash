"""SQLite implementation of TestDefinitionRepository."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import aiosqlite


def _parse_json(value: object, default: list | dict) -> list | dict:
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (list, dict)):
                return parsed
        except Exception:
            return default
    return default


class SqliteTestDefinitionRepository:
    """SQLite-backed test definition storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, definition_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = (
            project_id or definition_data.get("project_id") or definition_data.get("projectId", "")
        )
        tags = _parse_json(definition_data.get("tags", definition_data.get("tags_json", [])), [])
        await self.db.execute(
            """
            INSERT INTO test_definitions (
                test_id, project_id, path, name, framework, tags_json, owner, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(test_id) DO UPDATE SET
                project_id=excluded.project_id,
                path=excluded.path,
                name=excluded.name,
                framework=excluded.framework,
                tags_json=excluded.tags_json,
                owner=excluded.owner,
                updated_at=excluded.updated_at
            """,
            (
                definition_data["test_id"],
                resolved_project_id,
                definition_data.get("path", ""),
                definition_data.get("name", ""),
                definition_data.get("framework", "pytest"),
                json.dumps(tags),
                definition_data.get("owner", ""),
                definition_data.get("created_at", now),
                definition_data.get("updated_at", now),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, test_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM test_definitions WHERE test_id = ?",
            (test_id,),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            return await self.list_by_project(project_id=project_id, limit=limit, offset=offset)
        async with self.db.execute(
            "SELECT * FROM test_definitions ORDER BY updated_at DESC, test_id LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def list_by_project(self, project_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_definitions
            WHERE project_id = ?
            ORDER BY path ASC, name ASC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_or_create(
        self,
        project_id: str,
        path: str,
        name: str,
        framework: str = "pytest",
        tags: list[str] | None = None,
        owner: str = "",
    ) -> dict:
        test_id = hashlib.sha256(f"{path}::{name}::{framework}".encode("utf-8")).hexdigest()
        existing = await self.get_by_id(test_id)
        if existing:
            return existing
        await self.upsert(
            {
                "test_id": test_id,
                "project_id": project_id,
                "path": path,
                "name": name,
                "framework": framework,
                "tags": tags or [],
                "owner": owner,
            },
            project_id=project_id,
        )
        created = await self.get_by_id(test_id)
        return created or {
            "test_id": test_id,
            "project_id": project_id,
            "path": path,
            "name": name,
            "framework": framework,
            "tags_json": tags or [],
            "owner": owner,
        }

    def _row_to_dict(self, row: aiosqlite.Row | None) -> dict:
        if row is None:
            return {}
        data = dict(row)
        data["tags_json"] = _parse_json(data.get("tags_json", []), [])
        return data
