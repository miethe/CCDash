"""PostgreSQL repository for SkillMeat artifact snapshot cache data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from backend.db.repositories.artifact_snapshot_repository import (
    _freshness_from_row,
    _iso_utc,
    _payload_from_raw,
    _snapshot_from_row,
    _utc_now,
)
from backend.models import SkillMeatArtifactSnapshot, SnapshotFreshnessMeta


def _snapshot_payload(snapshot: SkillMeatArtifactSnapshot, fetched_at: datetime) -> dict[str, Any]:
    payload = snapshot.snapshot_dict()
    freshness = dict(payload.get("freshness") or {})
    freshness.setdefault("snapshotSource", "skillmeat")
    freshness.setdefault("sourceGeneratedAt", payload["generatedAt"])
    freshness["fetchedAt"] = _iso_utc(fetched_at)
    payload["freshness"] = freshness
    return payload


class PostgresArtifactSnapshotRepository:
    """PostgreSQL-backed SkillMeat artifact snapshot storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def save_snapshot(self, snapshot: SkillMeatArtifactSnapshot) -> None:
        fetched_at = snapshot.freshness.fetched_at or _utc_now()
        payload = _snapshot_payload(snapshot, fetched_at)
        await self.db.execute(
            """
            INSERT INTO artifact_snapshot_cache (
                project_id, collection_id, schema_version, generated_at,
                fetched_at, artifact_count, status, raw_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            snapshot.project_id,
            snapshot.collection_id or "",
            snapshot.schema_version,
            _iso_utc(snapshot.generated_at),
            _iso_utc(fetched_at),
            len(snapshot.artifacts),
            "fetched",
            json.dumps(payload, sort_keys=True),
        )

    async def get_latest_snapshot(self, project_id: str) -> SkillMeatArtifactSnapshot | None:
        row = await self.db.fetchrow(
            """
            SELECT *
            FROM artifact_snapshot_cache
            WHERE project_id = $1
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            project_id,
        )
        if row is not None:
            raw_payload = _payload_from_raw(row["raw_json"])
            if isinstance(raw_payload, dict) and raw_payload:
                row = dict(row)
                row["raw_json"] = raw_payload
        return _snapshot_from_row(row) if row else None

    async def get_snapshot_freshness(self, project_id: str) -> SnapshotFreshnessMeta:
        row = await self.db.fetchrow(
            """
            SELECT generated_at, fetched_at
            FROM artifact_snapshot_cache
            WHERE project_id = $1
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            project_id,
        )
        return _freshness_from_row(row)

    async def get_unresolved_identity_count(self, project_id: str) -> int:
        count = await self.db.fetchval(
            """
            SELECT COUNT(*) AS count
            FROM artifact_identity_map
            WHERE project_id = $1 AND match_tier = 'unresolved'
            """,
            project_id,
        )
        return int(count or 0)

    async def save_identity_mapping(self, mapping: dict[str, Any]) -> None:
        await self.db.execute(
            """
            DELETE FROM artifact_identity_map
            WHERE project_id = $1 AND ccdash_name = $2 AND ccdash_type = $3
            """,
            mapping["project_id"],
            mapping["ccdash_name"],
            mapping.get("ccdash_type") or "",
        )
        await self.db.execute(
            """
            INSERT INTO artifact_identity_map (
                project_id, ccdash_name, ccdash_type, skillmeat_uuid,
                content_hash, match_tier, confidence, resolved_at, unresolved_reason
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            mapping["project_id"],
            mapping["ccdash_name"],
            mapping.get("ccdash_type") or "",
            mapping.get("skillmeat_uuid") or "",
            mapping.get("content_hash") or "",
            mapping["match_tier"],
            mapping.get("confidence"),
            mapping.get("resolved_at") or "",
            mapping.get("unresolved_reason") or "",
        )

    async def list_identity_mappings(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT project_id, ccdash_name, ccdash_type, skillmeat_uuid,
                   content_hash, match_tier, confidence, resolved_at, unresolved_reason
            FROM artifact_identity_map
            WHERE project_id = $1
            ORDER BY ccdash_name, ccdash_type
            """,
            project_id,
        )
        return [dict(row) for row in rows]
