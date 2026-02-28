"""SQLite implementation of TestMappingRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


def _parse_json(value: object, default: dict | list) -> dict | list:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            return default
    return default


class SqliteTestMappingRepository:
    """SQLite-backed test mapping storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, mapping_data: dict, project_id: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = (
            project_id or mapping_data.get("project_id") or mapping_data.get("projectId", "")
        )
        test_id = mapping_data["test_id"]
        feature_id = mapping_data["feature_id"]
        provider_source = mapping_data.get("provider_source", "repo_heuristics")
        version = int(mapping_data.get("version", 1))
        metadata = _parse_json(mapping_data.get("metadata", mapping_data.get("metadata_json", {})), {})

        await self.db.execute(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source,
                confidence, version, snapshot_hash, is_primary, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(test_id, feature_id, provider_source, version) DO UPDATE SET
                project_id=excluded.project_id,
                domain_id=excluded.domain_id,
                confidence=excluded.confidence,
                snapshot_hash=excluded.snapshot_hash,
                metadata_json=excluded.metadata_json
            """,
            (
                resolved_project_id,
                test_id,
                feature_id,
                mapping_data.get("domain_id"),
                provider_source,
                float(mapping_data.get("confidence", 0.5)),
                version,
                mapping_data.get("snapshot_hash", ""),
                int(mapping_data.get("is_primary", 0)),
                json.dumps(metadata),
                mapping_data.get("created_at", now),
            ),
        )

        async with self.db.execute(
            """
            SELECT mapping_id
            FROM test_feature_mappings
            WHERE project_id = ? AND test_id = ? AND feature_id = ?
              AND provider_source = ? AND version = ?
            LIMIT 1
            """,
            (resolved_project_id, test_id, feature_id, provider_source, version),
        ) as cur:
            row = await cur.fetchone()
            mapping_id = int(row[0]) if row else 0

        await self._refresh_primary(
            project_id=resolved_project_id,
            test_id=test_id,
            feature_id=feature_id,
        )
        await self.db.commit()
        return mapping_id

    async def get_by_id(self, mapping_id: int) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM test_feature_mappings WHERE mapping_id = ?",
            (mapping_id,),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            async with self.db.execute(
                """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = ?
                ORDER BY created_at DESC, mapping_id DESC
                LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self.db.execute(
                """
                SELECT *
                FROM test_feature_mappings
                ORDER BY created_at DESC, mapping_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def list_by_test(self, project_id: str, test_id: str) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = ? AND test_id = ?
            ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
            """,
            (project_id, test_id),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_feature(
        self,
        project_id: str,
        feature_id: str,
        is_primary_only: bool = False,
    ) -> list[dict]:
        if is_primary_only:
            query = """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = ? AND feature_id = ? AND is_primary = 1
                ORDER BY confidence DESC, mapping_id DESC
            """
            params = (project_id, feature_id)
        else:
            query = """
                SELECT *
                FROM test_feature_mappings
                WHERE project_id = ? AND feature_id = ?
                ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
            """
            params = (project_id, feature_id)
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_domain(self, project_id: str, domain_id: str) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = ? AND domain_id = ?
            ORDER BY is_primary DESC, confidence DESC, mapping_id DESC
            """,
            (project_id, domain_id),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_primary_for_test(self, project_id: str, test_id: str) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_feature_mappings
            WHERE project_id = ? AND test_id = ? AND is_primary = 1
            ORDER BY confidence DESC, mapping_id DESC
            """,
            (project_id, test_id),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def _refresh_primary(self, project_id: str, test_id: str, feature_id: str) -> None:
        async with self.db.execute(
            """
            SELECT mapping_id
            FROM test_feature_mappings
            WHERE project_id = ? AND test_id = ? AND feature_id = ?
            ORDER BY confidence DESC, mapping_id DESC
            """,
            (project_id, test_id, feature_id),
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return
        primary_id = int(rows[0][0])
        await self.db.execute(
            """
            UPDATE test_feature_mappings
            SET is_primary = CASE WHEN mapping_id = ? THEN 1 ELSE 0 END
            WHERE project_id = ? AND test_id = ? AND feature_id = ?
            """,
            (primary_id, project_id, test_id, feature_id),
        )

    def _row_to_dict(self, row: aiosqlite.Row | None) -> dict:
        if row is None:
            return {}
        data = dict(row)
        data["metadata_json"] = _parse_json(data.get("metadata_json", {}), {})
        return data
