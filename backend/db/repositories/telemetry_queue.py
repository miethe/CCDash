"""SQLite repository for outbound telemetry queue rows."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import aiosqlite


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


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class SqliteTelemetryQueueRepository:
    """SQLite-backed outbound telemetry queue storage."""

    def __init__(self, db: aiosqlite.Connection):
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
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (queue_id, session_id, project_slug, payload_json, now),
        )
        await self.db.commit()
        row = await self._get_by_session_id(session_id)
        return row or {}

    async def fetch_pending_batch(self, batch_size: int) -> list[dict[str, Any]]:
        size = max(1, int(batch_size))
        async with self.db.execute(
            """
            SELECT *
            FROM outbound_telemetry_queue
            WHERE status IN ('pending', 'failed')
            ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END, created_at ASC, id ASC
            LIMIT ?
            """,
            (max(size * 10, 200),),
        ) as cur:
            rows = await cur.fetchall()
        eligible: list[dict[str, Any]] = []
        for row in rows:
            item = self._row_to_dict(row)
            if item.get("status") == "pending" or self._retry_due(item):
                eligible.append(item)
            if len(eligible) >= size:
                break
        return eligible

    async def mark_synced(self, queue_id: str) -> dict[str, Any] | None:
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'synced',
                last_attempt_at = ?,
                attempt_count = attempt_count + 1,
                last_error = NULL
            WHERE id = ?
            """,
            (_now_iso(), queue_id),
        )
        await self.db.commit()
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
                    last_attempt_at = ?,
                    attempt_count = attempt_count + 1,
                    last_error = ?
                WHERE id = ?
                """,
                (now, error, queue_id),
            )
        else:
            next_attempt = max(1, int(attempt_count))
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'failed',
                    last_attempt_at = ?,
                    attempt_count = CASE
                        WHEN ? > attempt_count THEN ?
                        ELSE attempt_count + 1
                    END,
                    last_error = ?
                WHERE id = ?
                """,
                (now, next_attempt, next_attempt, error, queue_id),
            )
        await self.db.commit()
        return await self._get_by_id(queue_id)

    async def mark_abandoned(
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
                SET status = 'abandoned',
                    last_attempt_at = ?,
                    attempt_count = attempt_count + 1,
                    last_error = ?
                WHERE id = ?
                """,
                (now, error, queue_id),
            )
        else:
            next_attempt = max(1, int(attempt_count))
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'abandoned',
                    last_attempt_at = ?,
                    attempt_count = CASE
                        WHEN ? > attempt_count THEN ?
                        ELSE attempt_count + 1
                    END,
                    last_error = ?
                WHERE id = ?
                """,
                (now, next_attempt, next_attempt, error, queue_id),
            )
        await self.db.commit()
        return await self._get_by_id(queue_id)

    async def get_queue_stats(self) -> dict[str, Any]:
        async with self.db.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM outbound_telemetry_queue
            GROUP BY status
            """
        ) as cur:
            rows = await cur.fetchall()

        counts = {str(row[0]): int(row[1]) for row in rows}
        pending = counts.get("pending", 0)
        synced = counts.get("synced", 0)
        failed = counts.get("failed", 0)
        abandoned = counts.get("abandoned", 0)
        async with self.db.execute(
            """
            SELECT last_attempt_at
            FROM outbound_telemetry_queue
            WHERE status = 'synced' AND last_attempt_at IS NOT NULL
            ORDER BY last_attempt_at DESC
            LIMIT 1
            """
        ) as cur:
            last_push_row = await cur.fetchone()
        async with self.db.execute(
            """
            SELECT COUNT(*)
            FROM outbound_telemetry_queue
            WHERE status = 'synced' AND last_attempt_at IS NOT NULL
              AND julianday(last_attempt_at) >= julianday(?)
            """,
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
        ) as cur:
            pushed_row = await cur.fetchone()
        async with self.db.execute(
            """
            SELECT status, last_error, COALESCE(last_attempt_at, created_at) AS error_at
            FROM outbound_telemetry_queue
            WHERE last_error IS NOT NULL AND TRIM(last_error) <> ''
            ORDER BY julianday(COALESCE(last_attempt_at, created_at)) DESC
            LIMIT 1
            """
        ) as cur:
            error_row = await cur.fetchone()
        return {
            "pending": pending,
            "synced": synced,
            "failed": failed,
            "abandoned": abandoned,
            "total": pending + synced + failed + abandoned,
            "last_push_timestamp": str(last_push_row[0]) if last_push_row else "",
            "events_pushed_24h": int(pushed_row[0]) if pushed_row else 0,
            "last_error_status": str(error_row[0]) if error_row else "",
            "last_error": str(error_row[1]) if error_row else "",
            "last_error_at": str(error_row[2]) if error_row else "",
        }

    async def purge_old_synced(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, int(retention_days)))).isoformat()
        async with self.db.execute(
            """
            SELECT COUNT(*)
            FROM outbound_telemetry_queue
            WHERE status = 'synced' AND julianday(created_at) < julianday(?)
            """,
            (cutoff,),
        ) as cur:
            row = await cur.fetchone()
            count = int(row[0]) if row else 0

        if count <= 0:
            return 0

        await self.db.execute(
            """
            DELETE FROM outbound_telemetry_queue
            WHERE status = 'synced' AND julianday(created_at) < julianday(?)
            """,
            (cutoff,),
        )
        await self.db.commit()
        return count

    async def _get_by_id(self, queue_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM outbound_telemetry_queue WHERE id = ? LIMIT 1",
            (queue_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def _get_by_session_id(self, session_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM outbound_telemetry_queue WHERE session_id = ? LIMIT 1",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload_json"] = _parse_payload(data.get("payload_json"))
        return data

    def _retry_due(self, row: dict[str, Any]) -> bool:
        if str(row.get("status") or "") != "failed":
            return False
        attempt_count = max(1, int(row.get("attempt_count") or 1))
        delay_seconds = min(60 * (2 ** max(0, attempt_count - 1)), 14400)
        last_attempt = _parse_timestamp(row.get("last_attempt_at"))
        if last_attempt is None:
            return True
        return (datetime.now(timezone.utc) - last_attempt).total_seconds() >= delay_seconds
