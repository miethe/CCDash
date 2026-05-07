"""SQLite repository for artifact ranking rows."""
from __future__ import annotations

import base64
import json
from typing import Any

import aiosqlite


_COLUMNS = (
    "project_id",
    "collection_id",
    "user_scope",
    "artifact_type",
    "artifact_id",
    "artifact_uuid",
    "version_id",
    "workflow_id",
    "period",
    "exclusive_tokens",
    "supporting_tokens",
    "cost_usd",
    "session_count",
    "workflow_count",
    "last_observed_at",
    "avg_confidence",
    "confidence",
    "success_score",
    "efficiency_score",
    "quality_score",
    "risk_score",
    "context_pressure",
    "sample_size",
    "identity_confidence",
    "snapshot_fetched_at",
    "recommendation_types_json",
    "evidence_json",
    "computed_at",
)

_JSON_COLUMNS = {"recommendation_types_json", "evidence_json"}


def _json_dumps(value: Any, default: Any) -> str:
    payload = value if value is not None else default
    return json.dumps(payload, sort_keys=True)


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _row_to_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["recommendation_types"] = _decode_json(item.pop("recommendation_types_json", "[]"), [])
    item["evidence"] = _decode_json(item.pop("evidence_json", "{}"), {})
    return item


def _column_value(row: dict[str, Any], column: str) -> Any:
    if column == "recommendation_types_json":
        return row.get("recommendation_types_json", row.get("recommendation_types"))
    if column == "evidence_json":
        return row.get("evidence_json", row.get("evidence"))
    return row.get(column)


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or 50), 500))


def _safe_offset(offset: int) -> int:
    return max(0, int(offset or 0))


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(max(0, offset)).encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid_cursor") from exc


class SqliteArtifactRankingRepository:
    """SQLite-backed artifact ranking storage and query surface."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def replace_rankings(self, project_id: str, period: str, rows: list[dict[str, Any]]) -> None:
        await self.delete_rankings(project_id, period)
        if rows:
            await self.upsert_rankings(rows)

    async def delete_rankings(self, project_id: str, period: str) -> None:
        await self.db.execute(
            "DELETE FROM artifact_ranking WHERE project_id = ? AND period = ?",
            (project_id, period),
        )
        await self.db.commit()

    async def upsert_rankings(self, rows: list[dict[str, Any]]) -> None:
        values = []
        for row in rows:
            values.append(
                tuple(
                    _json_dumps(_column_value(row, column), [] if column == "recommendation_types_json" else {})
                    if column in _JSON_COLUMNS
                    else _column_value(row, column)
                    for column in _COLUMNS
                )
            )
        placeholders = ", ".join("?" for _ in _COLUMNS)
        updates = ", ".join(f"{column}=excluded.{column}" for column in _COLUMNS if column not in {"project_id", "collection_id", "user_scope", "artifact_id", "artifact_uuid", "version_id", "workflow_id", "period"})
        await self.db.executemany(
            f"""
            INSERT INTO artifact_ranking ({", ".join(_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(project_id, collection_id, user_scope, artifact_id, artifact_uuid, version_id, workflow_id, period)
            DO UPDATE SET {updates}
            """,
            values,
        )
        await self.db.commit()

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
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
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
                where.append(f"{column} = ?")
                params.append(value)
        if recommendation_type:
            where.append("recommendation_types_json LIKE ?")
            params.append(f'%"{recommendation_type}"%')

        where_sql = " AND ".join(where)
        async with self.db.execute(
            f"SELECT COUNT(*) AS count FROM artifact_ranking WHERE {where_sql}",
            tuple(params),
        ) as cur:
            count_row = await cur.fetchone()
        total = int(count_row["count"] if count_row else 0)
        async with self.db.execute(
            f"""
            SELECT *
            FROM artifact_ranking
            WHERE {where_sql}
            ORDER BY exclusive_tokens DESC, supporting_tokens DESC, session_count DESC, artifact_id ASC, workflow_id ASC
            LIMIT ? OFFSET ?
            """,
            tuple([*params, safe_limit, safe_offset]),
        ) as cur:
            rows = [_row_to_dict(row) for row in await cur.fetchall()]
        next_offset = safe_offset + len(rows)
        return {
            "rows": rows,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "next_cursor": encode_cursor(next_offset) if next_offset < total else None,
        }

    async def get_rankings_by_project(self, project_id: str, period: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.list_rankings(project_id=project_id, period=period, **(filters or {}))

    async def get_rankings_by_artifact(self, artifact_uuid: str, period: str) -> dict[str, Any]:
        async with self.db.execute(
            "SELECT project_id FROM artifact_ranking WHERE artifact_uuid = ? AND period = ? LIMIT 1",
            (artifact_uuid, period),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return {"rows": [], "total": 0, "limit": 50, "offset": 0, "next_cursor": None}
        return await self.list_rankings(project_id=row["project_id"], artifact_uuid=artifact_uuid, period=period)

    async def get_rankings_by_workflow(self, workflow_id: str, period: str) -> dict[str, Any]:
        async with self.db.execute(
            "SELECT project_id FROM artifact_ranking WHERE workflow_id = ? AND period = ? LIMIT 1",
            (workflow_id, period),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return {"rows": [], "total": 0, "limit": 50, "offset": 0, "next_cursor": None}
        return await self.list_rankings(project_id=row["project_id"], workflow_id=workflow_id, period=period)

    async def get_rankings_by_user_scope(self, project_id: str, user_scope: str, period: str) -> dict[str, Any]:
        return await self.list_rankings(project_id=project_id, user_scope=user_scope, period=period)
