"""PostgreSQL implementation of WorktreeContextRepository (PCP-501)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


class PostgresWorktreeContextRepository:
    """PostgreSQL-backed planning worktree context storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def create(self, data: dict) -> dict:
        now = _now_iso()
        context_id = str(data.get("id") or uuid.uuid4().hex)
        metadata = _parse_json_dict(data.get("metadata_json", data.get("metadata", {})))
        await self.db.execute(
            """
            INSERT INTO planning_worktree_contexts (
                id, project_id, feature_id, phase_number, batch_id,
                branch, worktree_path, base_branch, base_commit_sha,
                status, last_run_id, provider, notes, metadata_json,
                created_by, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, $13, $14::jsonb,
                $15, $16, $17
            )
            """,
            context_id,
            str(data.get("project_id") or ""),
            str(data.get("feature_id") or ""),
            data.get("phase_number"),
            str(data.get("batch_id") or ""),
            str(data.get("branch") or ""),
            str(data.get("worktree_path") or ""),
            str(data.get("base_branch") or ""),
            str(data.get("base_commit_sha") or ""),
            str(data.get("status") or "draft"),
            str(data.get("last_run_id") or ""),
            str(data.get("provider") or "local"),
            str(data.get("notes") or ""),
            json.dumps(metadata),
            str(data.get("created_by") or ""),
            str(data.get("created_at") or now),
            str(data.get("updated_at") or now),
        )
        return await self.get_by_id(context_id) or {}

    async def update(self, context_id: str, updates: dict) -> dict | None:
        normalized = dict(updates or {})
        if not normalized:
            return await self.get_by_id(context_id)

        if "metadata" in normalized and "metadata_json" not in normalized:
            normalized["metadata_json"] = normalized.pop("metadata")

        if "metadata_json" in normalized:
            raw = json.dumps(_parse_json_dict(normalized.get("metadata_json")))
            normalized["metadata_json"] = raw

        normalized.setdefault("updated_at", _now_iso())

        set_clauses: list[str] = []
        values: list[Any] = []
        for i, (col, val) in enumerate(normalized.items(), start=1):
            if col == "metadata_json":
                set_clauses.append(f"{col} = ${i}::jsonb")
            else:
                set_clauses.append(f"{col} = ${i}")
            values.append(val)
        values.append(context_id)
        await self.db.execute(
            f"UPDATE planning_worktree_contexts SET {', '.join(set_clauses)} WHERE id = ${len(values)}",
            *values,
        )
        return await self.get_by_id(context_id)

    async def get_by_id(self, context_id: str) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM planning_worktree_contexts WHERE id = $1", context_id
        )
        return self._row_to_dict(row) if row else None

    async def list(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        phase_number: int | None = None,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["project_id = $1"]
        params: list[Any] = [project_id]
        idx = 2
        if feature_id is not None:
            conditions.append(f"feature_id = ${idx}")
            params.append(feature_id)
            idx += 1
        if phase_number is not None:
            conditions.append(f"phase_number = ${idx}")
            params.append(phase_number)
            idx += 1
        if batch_id is not None:
            conditions.append(f"batch_id = ${idx}")
            params.append(batch_id)
            idx += 1
        if status is not None:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        params.extend([max(1, int(limit)), max(0, int(offset))])
        rows = await self.db.fetch(
            f"""
            SELECT * FROM planning_worktree_contexts
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )
        return [self._row_to_dict(row) for row in rows]

    async def count(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        phase_number: int | None = None,
        batch_id: str | None = None,
        status: str | None = None,
    ) -> int:
        conditions = ["project_id = $1"]
        params: list[Any] = [project_id]
        idx = 2
        if feature_id is not None:
            conditions.append(f"feature_id = ${idx}")
            params.append(feature_id)
            idx += 1
        if phase_number is not None:
            conditions.append(f"phase_number = ${idx}")
            params.append(phase_number)
            idx += 1
        if batch_id is not None:
            conditions.append(f"batch_id = ${idx}")
            params.append(batch_id)
            idx += 1
        if status is not None:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        row = await self.db.fetchrow(
            f"SELECT COUNT(*) FROM planning_worktree_contexts WHERE {' AND '.join(conditions)}",
            *params,
        )
        return int((row[0] if row else 0) or 0)

    async def delete(self, context_id: str) -> bool:
        existing = await self.db.fetchrow(
            "SELECT id FROM planning_worktree_contexts WHERE id = $1", context_id
        )
        if not existing:
            return False
        await self.db.execute(
            "DELETE FROM planning_worktree_contexts WHERE id = $1", context_id
        )
        return True

    def _row_to_dict(self, row: asyncpg.Record) -> dict:
        data = dict(row)
        raw_meta = data.pop("metadata_json", {})
        data["metadata"] = _parse_json_dict(raw_meta) if not isinstance(raw_meta, dict) else raw_meta
        return data
