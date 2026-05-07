"""PostgreSQL repository for artifact ranking rows."""
from __future__ import annotations

import json
from typing import Any

import asyncpg

from backend.db.repositories.artifact_ranking_repository import _COLUMNS, _column_value, _row_to_dict, _safe_limit, _safe_offset
from backend.db.repositories.artifact_ranking_repository import decode_cursor, encode_cursor


def _json_payload(value: Any, default: Any) -> str:
    return json.dumps(value if value is not None else default, sort_keys=True)


class PostgresArtifactRankingRepository:
    """PostgreSQL-backed artifact ranking storage and query surface."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_rankings(self, project_id: str, period: str, rows: list[dict[str, Any]]) -> None:
        await self.delete_rankings(project_id, period)
        if rows:
            await self.upsert_rankings(rows)

    async def delete_rankings(self, project_id: str, period: str) -> None:
        await self.db.execute("DELETE FROM artifact_ranking WHERE project_id = $1 AND period = $2", project_id, period)

    async def upsert_rankings(self, rows: list[dict[str, Any]]) -> None:
        placeholders = ", ".join(f"${idx}" for idx in range(1, len(_COLUMNS) + 1))
        updates = ", ".join(
            f"{column}=EXCLUDED.{column}"
            for column in _COLUMNS
            if column not in {"project_id", "collection_id", "user_scope", "artifact_id", "artifact_uuid", "version_id", "workflow_id", "period"}
        )
        query = f"""
            INSERT INTO artifact_ranking ({", ".join(_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(project_id, collection_id, user_scope, artifact_id, artifact_uuid, version_id, workflow_id, period)
            DO UPDATE SET {updates}
        """
        for row in rows:
            values = [
                _json_payload(_column_value(row, column), [] if column == "recommendation_types_json" else {})
                if column in {"recommendation_types_json", "evidence_json"}
                else _column_value(row, column)
                for column in _COLUMNS
            ]
            await self.db.execute(query, *values)

    async def list_rankings(
        self,
        *,
        project_id: str,
        period: str | None = None,
        collection_id: str | None = None,
        user_scope: str | None = None,
        artifact_uuid: str | None = None,
        artifact_id: str | None = None,
        version_id: str | None = None,
        workflow_id: str | None = None,
        artifact_type: str | None = None,
        recommendation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = _safe_limit(limit)
        safe_offset = decode_cursor(cursor) if cursor else _safe_offset(offset)
        where = ["project_id = $1"]
        params: list[Any] = [project_id]
        idx = 2
        for column, value in (
            ("period", period),
            ("collection_id", collection_id),
            ("user_scope", user_scope),
            ("artifact_uuid", artifact_uuid),
            ("artifact_id", artifact_id),
            ("version_id", version_id),
            ("workflow_id", workflow_id),
            ("artifact_type", artifact_type),
        ):
            if value is not None:
                where.append(f"{column} = ${idx}")
                params.append(value)
                idx += 1
        if recommendation_type:
            where.append(f"recommendation_types_json ? ${idx}")
            params.append(recommendation_type)
            idx += 1
        where_sql = " AND ".join(where)
        total = int(await self.db.fetchval(f"SELECT COUNT(*) FROM artifact_ranking WHERE {where_sql}", *params) or 0)
        rows = await self.db.fetch(
            f"""
            SELECT *
            FROM artifact_ranking
            WHERE {where_sql}
            ORDER BY exclusive_tokens DESC, supporting_tokens DESC, session_count DESC, artifact_id ASC, workflow_id ASC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
            safe_limit,
            safe_offset,
        )
        shaped = [_row_to_dict(dict(row)) for row in rows]
        next_offset = safe_offset + len(shaped)
        return {
            "rows": shaped,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "next_cursor": encode_cursor(next_offset) if next_offset < total else None,
        }

    async def get_rankings_by_project(self, project_id: str, period: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.list_rankings(project_id=project_id, period=period, **(filters or {}))

    async def get_rankings_by_artifact(self, artifact_uuid: str, period: str) -> dict[str, Any]:
        row = await self.db.fetchrow(
            "SELECT project_id FROM artifact_ranking WHERE artifact_uuid = $1 AND period = $2 LIMIT 1",
            artifact_uuid,
            period,
        )
        if row is None:
            return {"rows": [], "total": 0, "limit": 50, "offset": 0, "next_cursor": None}
        return await self.list_rankings(project_id=row["project_id"], artifact_uuid=artifact_uuid, period=period)

    async def get_rankings_by_workflow(self, workflow_id: str, period: str) -> dict[str, Any]:
        row = await self.db.fetchrow(
            "SELECT project_id FROM artifact_ranking WHERE workflow_id = $1 AND period = $2 LIMIT 1",
            workflow_id,
            period,
        )
        if row is None:
            return {"rows": [], "total": 0, "limit": 50, "offset": 0, "next_cursor": None}
        return await self.list_rankings(project_id=row["project_id"], workflow_id=workflow_id, period=period)

    async def get_rankings_by_user_scope(self, project_id: str, user_scope: str, period: str) -> dict[str, Any]:
        return await self.list_rankings(project_id=project_id, user_scope=user_scope, period=period)
