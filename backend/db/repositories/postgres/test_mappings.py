"""PostgreSQL implementation of TestMappingRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg


class PostgresTestMappingRepository:
    """PostgreSQL-backed test mapping storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, mapping_data: dict, project_id: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = (
            project_id or mapping_data.get("project_id") or mapping_data.get("projectId", "")
        )
        metadata = mapping_data.get("metadata", mapping_data.get("metadata_json", {}))
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        query = """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source,
                confidence, version, snapshot_hash, is_primary, metadata_json, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            ON CONFLICT(test_id, feature_id, provider_source, version) DO UPDATE SET
                project_id=EXCLUDED.project_id,
                domain_id=EXCLUDED.domain_id,
                confidence=EXCLUDED.confidence,
                snapshot_hash=EXCLUDED.snapshot_hash,
                metadata_json=EXCLUDED.metadata_json
            RETURNING mapping_id
        """
        row = await self.db.fetchrow(
            query,
            resolved_project_id,
            mapping_data["test_id"],
            mapping_data["feature_id"],
            mapping_data.get("domain_id"),
            mapping_data.get("provider_source", "repo_heuristics"),
            float(mapping_data.get("confidence", 0.5)),
            int(mapping_data.get("version", 1)),
            mapping_data.get("snapshot_hash", ""),
            int(mapping_data.get("is_primary", 0)),
            json.dumps(metadata or {}),
            mapping_data.get("created_at", now),
        )
        return int(row["mapping_id"]) if row else 0

    async def get_by_id(self, mapping_id: int) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM test_feature_mappings WHERE mapping_id = $1",
            mapping_id,
        )
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = $1
                ORDER BY created_at DESC, mapping_id DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                ORDER BY created_at DESC, mapping_id DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
