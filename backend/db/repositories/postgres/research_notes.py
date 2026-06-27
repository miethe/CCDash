"""PostgreSQL implementation of ResearchNoteRepository (P5-013 MeatyWiki scaffold)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresResearchNoteRepository:
    """PostgreSQL-backed MeatyWiki research note storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
    ) -> list[dict[str, Any]]:
        """Return all research_notes rows for the given project+feature."""
        rows = await self.db.fetch(
            """
            SELECT id, project_id, feature_id, title, url, body, source, created_at
            FROM research_notes
            WHERE project_id = $1 AND feature_id = $2
            ORDER BY created_at ASC
            """,
            str(project_id or ""),
            str(feature_id or ""),
        )
        return [dict(row) for row in rows]

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a research note record."""
        now = _now_iso()
        row_id = str(data.get("id") or uuid.uuid4().hex)
        project_id = str(data.get("project_id") or "")
        feature_id = str(data.get("feature_id") or "")
        title = str(data.get("title") or "")
        url = str(data.get("url") or "")
        body = str(data.get("body") or "")
        source = str(data.get("source") or "")
        created_at = str(data.get("created_at") or now)

        await self.db.execute(
            """
            INSERT INTO research_notes (
                id, project_id, feature_id, title, url, body, source, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT(id) DO UPDATE SET
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                body = EXCLUDED.body,
                source = EXCLUDED.source
            """,
            row_id, project_id, feature_id, title, url, body, source, created_at,
        )
        return {
            "id": row_id,
            "project_id": project_id,
            "feature_id": feature_id,
            "title": title,
            "url": url,
            "body": body,
            "source": source,
            "created_at": created_at,
        }
