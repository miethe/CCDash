"""PostgreSQL repository for outbound telemetry queue rows."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_payload(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _parse_payload(payload_json: Any) -> Any:
    if isinstance(payload_json, str) and payload_json.strip():
        try:
            return json.loads(payload_json)
        except Exception:
            return payload_json
    return payload_json


class PostgresTelemetryQueueRepository:
    """Postgres-backed outbound telemetry queue storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def enqueue(
        self,
        session_id: str,
        project_slug: str,
        payload: dict[str, Any] | str,
        queue_id: str | None = None,
    ) -> dict[str, Any]:
        payload_json = _serialize_payload(payload)
        if not queue_id and isinstance(payload, dict):
            queue_id = str(payload.get("event_id") or "").strip() or None
        queue_id = queue_id or str(uuid4())
        now = _now_iso()

        await self.db.execute(
            """
            INSERT INTO outbound_telemetry_queue (
                id, session_id, project_slug, payload_json, status, created_at
            ) VALUES ($1, $2, $3, $4, 'pending', $5)
            ON CONFLICT(session_id) DO NOTHING
            """,
            queue_id,
            session_id,
            project_slug,
            payload_json,
            now,
        )
        row = await self._get_by_session_id(session_id)
        return row or {}

    async def fetch_pending_batch(self, batch_size: int) -> list[dict[str, Any]]:
        size = max(1, int(batch_size))
        rows = await self.db.fetch(
            """
            SELECT *
            FROM outbound_telemetry_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT $1
            """,
            size,
        )
        return [self._row_to_dict(row) for row in rows]

    async def mark_synced(self, queue_id: str) -> dict[str, Any] | None:
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'synced',
                last_attempt_at = $1,
                attempt_count = attempt_count + 1,
                last_error = NULL
            WHERE id = $2
            """,
            _now_iso(),
            queue_id,
        )
        return await self._get_by_id(queue_id)

    async def mark_failed(
        self,
        queue_id: str,
        error: str,
        attempt_count: int | None = None,
    ) -> dict[str, Any] | None:
        now = _now_iso()
        if attempt_count is None:
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'failed',
                    last_attempt_at = $1,
                    attempt_count = attempt_count + 1,
                    last_error = $2
                WHERE id = $3
                """,
                now,
                error,
                queue_id,
            )
        else:
            next_attempt = max(1, int(attempt_count))
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'failed',
                    last_attempt_at = $1,
                    attempt_count = CASE
                        WHEN $2 > attempt_count THEN $2
                        ELSE attempt_count + 1
                    END,
                    last_error = $3
                WHERE id = $4
                """,
                now,
                next_attempt,
                error,
                queue_id,
            )
        return await self._get_by_id(queue_id)

    async def mark_abandoned(self, queue_id: str, error: str) -> dict[str, Any] | None:
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'abandoned',
                last_attempt_at = $1,
                attempt_count = attempt_count + 1,
                last_error = $2
            WHERE id = $3
            """,
            _now_iso(),
            error,
            queue_id,
        )
        return await self._get_by_id(queue_id)

    async def get_queue_stats(self) -> dict[str, Any]:
        rows = await self.db.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM outbound_telemetry_queue
            GROUP BY status
            """
        )
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        pending = counts.get("pending", 0)
        synced = counts.get("synced", 0)
        failed = counts.get("failed", 0)
        abandoned = counts.get("abandoned", 0)
        return {
            "pending": pending,
            "synced": synced,
            "failed": failed,
            "abandoned": abandoned,
            "total": pending + synced + failed + abandoned,
        }

    async def purge_old_synced(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, int(retention_days)))).isoformat()
        deleted_rows = await self.db.fetch(
            """
            DELETE FROM outbound_telemetry_queue
            WHERE status = 'synced' AND (created_at::timestamptz) < ($1::timestamptz)
            RETURNING id
            """,
            cutoff,
        )
        return len(deleted_rows)

    async def _get_by_id(self, queue_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM outbound_telemetry_queue WHERE id = $1 LIMIT 1",
            queue_id,
        )
        return self._row_to_dict(row) if row else None

    async def _get_by_session_id(self, session_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM outbound_telemetry_queue WHERE session_id = $1 LIMIT 1",
            session_id,
        )
        return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: asyncpg.Record) -> dict[str, Any]:
        data = dict(row)
        data["payload_json"] = _parse_payload(data.get("payload_json"))
        return data

