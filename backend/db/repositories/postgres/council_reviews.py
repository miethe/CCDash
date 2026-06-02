"""PostgreSQL implementation of CouncilReviewRepository (P5-012 ARC scaffold)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresCouncilReviewRepository:
    """PostgreSQL-backed ARC council review storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
    ) -> list[dict[str, Any]]:
        """Return all council_reviews rows for the given project+feature."""
        rows = await self.db.fetch(
            """
            SELECT id, project_id, feature_id, status, summary, created_at, updated_at
            FROM council_reviews
            WHERE project_id = $1 AND feature_id = $2
            ORDER BY created_at ASC
            """,
            str(project_id or ""),
            str(feature_id or ""),
        )
        return [dict(row) for row in rows]

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a council review record."""
        now = _now_iso()
        row_id = str(data.get("id") or uuid.uuid4().hex)
        project_id = str(data.get("project_id") or "")
        feature_id = str(data.get("feature_id") or "")
        status = str(data.get("status") or "pending")
        summary = str(data.get("summary") or "")
        created_at = str(data.get("created_at") or now)
        updated_at = now

        await self.db.execute(
            """
            INSERT INTO council_reviews (
                id, project_id, feature_id, status, summary, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT(id) DO UPDATE SET
                status = EXCLUDED.status,
                summary = EXCLUDED.summary,
                updated_at = EXCLUDED.updated_at
            """,
            row_id, project_id, feature_id, status, summary, created_at, updated_at,
        )
        return {
            "id": row_id,
            "project_id": project_id,
            "feature_id": feature_id,
            "status": status,
            "summary": summary,
            "created_at": created_at,
            "updated_at": updated_at,
        }
