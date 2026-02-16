"""PostgreSQL implementation of DocumentRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import asyncpg

class PostgresDocumentRepository:
    """PostgreSQL-backed document storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, doc_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        frontmatter = doc_data.get("frontmatter", {})
        if isinstance(frontmatter, dict):
            fm_json = json.dumps(frontmatter)
        else:
            fm_json = json.dumps(frontmatter) if isinstance(frontmatter, dict) else str(frontmatter)

        # Postgres Upsert
        query = """
            INSERT INTO documents (
                id, project_id, title, file_path, status, author, content,
                doc_type, category, parent_doc_id,
                created_at, updated_at, last_modified,
                frontmatter_json, source_file
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT(id) DO UPDATE SET
                title=EXCLUDED.title, file_path=EXCLUDED.file_path,
                status=EXCLUDED.status, author=EXCLUDED.author,
                content=EXCLUDED.content, doc_type=EXCLUDED.doc_type,
                category=EXCLUDED.category, parent_doc_id=EXCLUDED.parent_doc_id,
                updated_at=EXCLUDED.updated_at, last_modified=EXCLUDED.last_modified,
                frontmatter_json=EXCLUDED.frontmatter_json,
                source_file=EXCLUDED.source_file
        """
        await self.db.execute(
            query,
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
        )

    async def get_by_id(self, doc_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM documents WHERE id = $1", doc_id)
        return dict(row) if row else None

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                "SELECT * FROM documents WHERE project_id = $1 ORDER BY title",
                project_id,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM documents ORDER BY title")
        return [dict(r) for r in rows]

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM documents WHERE source_file = $1", source_file)
