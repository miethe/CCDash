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
        mapping_id = int(row["mapping_id"]) if row else 0
        await self._refresh_primary(
            project_id=resolved_project_id,
            test_id=str(mapping_data.get("test_id") or ""),
        )
        return mapping_id

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

    async def list_by_test(self, project_id: str, test_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = $1 AND test_id = $2
            ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
            """,
            project_id,
            test_id,
        )
        return [dict(row) for row in rows]

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
        is_primary_only: bool = False,
    ) -> list[dict]:
        if is_primary_only:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = $1 AND feature_id = $2 AND is_primary = 1
                ORDER BY confidence DESC, mapping_id DESC
                """,
                project_id,
                feature_id,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = $1 AND feature_id = $2
                ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
                """,
                project_id,
                feature_id,
            )
        return [dict(row) for row in rows]

    async def list_by_domain(self, project_id: str, domain_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = $1 AND domain_id = $2
            ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
            """,
            project_id,
            domain_id,
        )
        return [dict(row) for row in rows]

    async def get_primary_for_test(self, project_id: str, test_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = $1 AND test_id = $2 AND is_primary = 1
            ORDER BY confidence DESC, mapping_id DESC
            """,
            project_id,
            test_id,
        )
        return [dict(row) for row in rows]

    async def list_primary_by_project(self, project_id: str, domain_id: str | None = None) -> list[dict]:
        if domain_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = $1 AND is_primary = 1 AND domain_id = $2
                ORDER BY feature_id ASC, test_id ASC
                """,
                project_id,
                domain_id,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = $1 AND is_primary = 1
                ORDER BY feature_id ASC, test_id ASC
                """,
                project_id,
            )
        return [dict(row) for row in rows]

    async def list_primary_for_run(self, project_id: str, run_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT m.*
            FROM test_feature_mappings m
            JOIN test_results r ON r.test_id = m.test_id
            WHERE m.project_id = $1 AND m.is_primary = 1 AND r.run_id = $2
            ORDER BY m.feature_id ASC, m.test_id ASC
            """,
            project_id,
            run_id,
        )
        return [dict(row) for row in rows]

    async def _refresh_primary(self, project_id: str, test_id: str) -> None:
        rows = await self.db.fetch(
            """
            SELECT mapping_id
            FROM test_feature_mappings
            WHERE project_id = $1 AND test_id = $2 AND confidence >= 0.5
            ORDER BY confidence DESC, mapping_id DESC
            """,
            project_id,
            test_id,
        )
        if not rows:
            await self.db.execute(
                """
                UPDATE test_feature_mappings
                SET is_primary = 0
                WHERE project_id = $1 AND test_id = $2
                """,
                project_id,
                test_id,
            )
            return
        primary_id = int(rows[0]["mapping_id"])
        await self.db.execute(
            """
            UPDATE test_feature_mappings
            SET is_primary = CASE WHEN mapping_id = $1 THEN 1 ELSE 0 END
            WHERE project_id = $2 AND test_id = $3
            """,
            primary_id,
            project_id,
            test_id,
        )
