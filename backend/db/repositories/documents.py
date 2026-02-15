"""SQLite implementation of DocumentRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


class SqliteDocumentRepository:
    """SQLite-backed document storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, doc_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        frontmatter = doc_data.get("frontmatter", {})
        if isinstance(frontmatter, dict):
            fm_json = json.dumps(frontmatter)
        else:
            # If it's a Pydantic model, convert
            fm_json = json.dumps(frontmatter) if isinstance(frontmatter, dict) else str(frontmatter)

        await self.db.execute(
            """INSERT INTO documents (
                id, project_id, title, file_path, status, author, content,
                doc_type, category, parent_doc_id,
                created_at, updated_at, last_modified,
                frontmatter_json, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, file_path=excluded.file_path,
                status=excluded.status, author=excluded.author,
                content=excluded.content, doc_type=excluded.doc_type,
                category=excluded.category, parent_doc_id=excluded.parent_doc_id,
                updated_at=excluded.updated_at, last_modified=excluded.last_modified,
                frontmatter_json=excluded.frontmatter_json,
                source_file=excluded.source_file
            """,
            (
                doc_data["id"], project_id,
                doc_data.get("title", ""),
                doc_data.get("filePath", ""),
                doc_data.get("status", "active"),
                doc_data.get("author", ""),
                doc_data.get("content"),
                doc_data.get("docType", ""),
                doc_data.get("category", ""),
                doc_data.get("parentDocId"),
                doc_data.get("createdAt", now),
                now,
                doc_data.get("lastModified", ""),
                fm_json,
                doc_data.get("sourceFile", doc_data.get("filePath", "")),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, doc_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            async with self.db.execute(
                "SELECT * FROM documents WHERE project_id = ? ORDER BY title",
                (project_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM documents ORDER BY title"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM documents WHERE source_file = ?", (source_file,))
        await self.db.commit()
