"""SQLite repository for SkillMeat artifact snapshot cache data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.models import SkillMeatArtifactSnapshot, SnapshotFreshnessMeta


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_payload(snapshot: SkillMeatArtifactSnapshot, fetched_at: datetime) -> dict[str, Any]:
    payload = snapshot.snapshot_dict()
    freshness = dict(payload.get("freshness") or {})
    freshness.setdefault("snapshotSource", "skillmeat")
    freshness.setdefault("sourceGeneratedAt", payload["generatedAt"])
    freshness["fetchedAt"] = _iso_utc(fetched_at)
    payload["freshness"] = freshness
    return payload


def _payload_from_raw(raw_json: object) -> dict[str, Any]:
    if isinstance(raw_json, dict):
        return raw_json
    if isinstance(raw_json, str) and raw_json.strip():
        return json.loads(raw_json)
    return {}


def _row_value(row: Any, key: str) -> Any:
    return row[key]


def _snapshot_from_row(row: Any) -> SkillMeatArtifactSnapshot:
    payload = _payload_from_raw(_row_value(row, "raw_json"))
    freshness = dict(payload.get("freshness") or {})
    freshness.setdefault("snapshotSource", "skillmeat")
    freshness.setdefault("sourceGeneratedAt", _row_value(row, "generated_at"))
    freshness.setdefault("fetchedAt", _row_value(row, "fetched_at"))
    payload["freshness"] = freshness
    payload.setdefault("schemaVersion", _row_value(row, "schema_version"))
    payload.setdefault("generatedAt", _row_value(row, "generated_at"))
    payload.setdefault("projectId", _row_value(row, "project_id"))
    collection_id = _row_value(row, "collection_id")
    if collection_id:
        payload.setdefault("collectionId", collection_id)
    return SkillMeatArtifactSnapshot.model_validate(payload)


def _freshness_from_row(row: Any | None) -> SnapshotFreshnessMeta:
    if row is None:
        return SnapshotFreshnessMeta(warnings=["snapshot_not_found"])
    return SnapshotFreshnessMeta(
        snapshotSource="skillmeat",
        sourceGeneratedAt=_row_value(row, "generated_at"),
        fetchedAt=_row_value(row, "fetched_at"),
    )


class SqliteArtifactSnapshotRepository:
    """SQLite-backed SkillMeat artifact snapshot storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_snapshot(self, snapshot: SkillMeatArtifactSnapshot) -> None:
        fetched_at = snapshot.freshness.fetched_at or _utc_now()
        payload = _snapshot_payload(snapshot, fetched_at)
        await self.db.execute(
            """
            INSERT INTO artifact_snapshot_cache (
                project_id, collection_id, schema_version, generated_at,
                fetched_at, artifact_count, status, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.project_id,
                snapshot.collection_id or "",
                snapshot.schema_version,
                _iso_utc(snapshot.generated_at),
                _iso_utc(fetched_at),
                len(snapshot.artifacts),
                "fetched",
                json.dumps(payload, sort_keys=True),
            ),
        )
        await self.db.commit()

    async def get_latest_snapshot(self, project_id: str) -> SkillMeatArtifactSnapshot | None:
        async with self.db.execute(
            """
            SELECT *
            FROM artifact_snapshot_cache
            WHERE project_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return _snapshot_from_row(row) if row else None

    async def get_snapshot_freshness(self, project_id: str) -> SnapshotFreshnessMeta:
        async with self.db.execute(
            """
            SELECT generated_at, fetched_at
            FROM artifact_snapshot_cache
            WHERE project_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return _freshness_from_row(row)

    async def get_unresolved_identity_count(self, project_id: str) -> int:
        async with self.db.execute(
            """
            SELECT COUNT(*) AS count
            FROM artifact_identity_map
            WHERE project_id = ? AND match_tier = 'unresolved'
            """,
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row["count"] or 0) if row else 0
