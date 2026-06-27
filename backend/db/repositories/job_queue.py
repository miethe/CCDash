"""Job queue repository — SQLite implementation (P3-006).

Provides enqueue / claim / complete / fail / retry / checkpoint operations
against the ``job_queue`` table (SCHEMA_VERSION 30).

Columns:
    id, project_id, job_type, payload, status
    (pending/running/done/dead/crashed),
    priority, attempts, max_attempts, available_at,
    locked_by, locked_at, last_error, checkpoint,
    created_at, updated_at
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("ccdash.db.job_queue")

# ─── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _backoff_seconds(attempts: int, base: float = 5.0, cap: float = 300.0) -> float:
    """Exponential backoff: base * 2^attempts, capped at cap seconds."""
    return min(base * (2 ** attempts), cap)


def _available_at_iso(delay_seconds: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return dt.isoformat().replace("+00:00", "Z")


# ─── SQLite implementation ─────────────────────────────────────────────────────


class SqliteJobQueueRepository:
    """Async job queue over an aiosqlite connection.

    The repository is stateless beyond the ``db`` handle; all state lives
    in the ``job_queue`` table.
    """

    def __init__(self, db: Any) -> None:
        # db is an aiosqlite.Connection (or protocol-compatible object)
        self._db = db

    # ── enqueue ────────────────────────────────────────────────────────────────

    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        project_id: str,
        *,
        priority: int = 0,
        max_attempts: int = 3,
        available_at: str | None = None,
        job_id: str | None = None,
    ) -> str:
        """Insert a new pending job.  Returns the job id."""
        jid = job_id or str(uuid.uuid4())
        now = _now_iso()
        av = available_at or now
        await self._db.execute(
            """
            INSERT INTO job_queue
                (id, project_id, job_type, payload, status,
                 priority, attempts, max_attempts,
                 available_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?)
            """,
            (
                jid,
                project_id,
                job_type,
                json.dumps(payload),
                priority,
                max_attempts,
                av,
                now,
                now,
            ),
        )
        await self._db.commit()
        logger.debug("Enqueued job id=%s type=%s project=%s", jid, job_type, project_id)
        return jid

    # ── claim (optimistic lock) ────────────────────────────────────────────────

    async def claim(
        self,
        job_type: str | None = None,
        project_id: str | None = None,
        *,
        worker_id: str,
        max_in_flight: int = 5,
    ) -> dict[str, Any] | None:
        """Claim the next available pending job.

        Uses a ``status=running`` UPDATE + re-read for atomicity under
        SQLite's serialised write lock.  Returns the full row dict, or
        None if the queue is empty / backpressure limit reached.
        """
        now = _now_iso()

        # Backpressure: count how many jobs this worker currently holds.
        async with self._db.execute(
            "SELECT COUNT(*) FROM job_queue WHERE status = 'running' AND locked_by = ?",
            (worker_id,),
        ) as cur:
            row = await cur.fetchone()
            in_flight = row[0] if row else 0

        if in_flight >= max_in_flight:
            logger.debug(
                "Worker '%s' at in-flight limit (%d/%d) — skipping claim",
                worker_id,
                in_flight,
                max_in_flight,
            )
            return None

        # Find the next eligible job (pending, available_at <= now)
        where_clauses = ["status = 'pending'", "available_at <= ?"]
        params: list[Any] = [now]
        if job_type is not None:
            where_clauses.append("job_type = ?")
            params.append(job_type)
        if project_id is not None:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        where = " AND ".join(where_clauses)
        select_sql = f"""
            SELECT id FROM job_queue
            WHERE {where}
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """
        async with self._db.execute(select_sql, params) as cur:
            row = await cur.fetchone()
        if row is None:
            return None

        job_id = row[0]
        await self._db.execute(
            """
            UPDATE job_queue
               SET status     = 'running',
                   locked_by  = ?,
                   locked_at  = ?,
                   updated_at = ?
             WHERE id = ? AND status = 'pending'
            """,
            (worker_id, now, now, job_id),
        )
        await self._db.commit()

        return await self.get(job_id)

    # ── complete / fail / retry / checkpoint ──────────────────────────────────

    async def complete(self, job_id: str) -> None:
        """Mark a running job as done."""
        now = _now_iso()
        await self._db.execute(
            "UPDATE job_queue SET status='done', updated_at=? WHERE id=?",
            (now, job_id),
        )
        await self._db.commit()

    async def fail(
        self,
        job_id: str,
        error: str,
        *,
        checkpoint: str | None = None,
    ) -> None:
        """Record failure and either reschedule (retry) or mark terminal.

        - If ``attempts < max_attempts``: status → pending, available_at
          bumped by exponential backoff.
        - If ``attempts >= max_attempts``: status → dead.
        A crash (container restart mid-job) sets status → crashed via
        ``mark_crashed``.
        """
        now = _now_iso()
        # Fetch current attempts and max_attempts
        async with self._db.execute(
            "SELECT attempts, max_attempts FROM job_queue WHERE id = ?",
            (job_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            logger.warning("fail() called for unknown job id=%s", job_id)
            return

        attempts = (row[0] or 0) + 1
        max_attempts = row[1] or 3

        if attempts < max_attempts:
            delay = _backoff_seconds(attempts)
            new_available_at = _available_at_iso(delay)
            new_status = "pending"
        else:
            new_available_at = now
            new_status = "dead"

        ckpt_clause = ", checkpoint = ?" if checkpoint is not None else ""
        ckpt_params: list[Any] = []
        if checkpoint is not None:
            ckpt_params.append(checkpoint)

        await self._db.execute(
            f"""
            UPDATE job_queue
               SET status       = ?,
                   attempts     = ?,
                   last_error   = ?,
                   available_at = ?,
                   updated_at   = ?
                   {ckpt_clause}
             WHERE id = ?
            """,
            [new_status, attempts, error, new_available_at, now] + ckpt_params + [job_id],
        )
        await self._db.commit()
        logger.debug(
            "Job id=%s failed (attempt %d/%d) → status=%s",
            job_id,
            attempts,
            max_attempts,
            new_status,
        )

    async def mark_crashed(self, job_id: str, error: str) -> None:
        """Set status=crashed (used when a container restart mid-job is detected).

        Crashed jobs can be re-claimed by a new worker; they resume from
        ``checkpoint`` if set.
        """
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE job_queue
               SET status     = 'crashed',
                   last_error = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (error, now, job_id),
        )
        await self._db.commit()

    async def save_checkpoint(self, job_id: str, checkpoint: str) -> None:
        """Persist a serialised checkpoint so a crash resume can pick up mid-progress."""
        now = _now_iso()
        await self._db.execute(
            "UPDATE job_queue SET checkpoint=?, updated_at=? WHERE id=?",
            (checkpoint, now, job_id),
        )
        await self._db.commit()

    async def reclaim_crashed(
        self,
        worker_id: str,
        *,
        max_in_flight: int = 5,
    ) -> dict[str, Any] | None:
        """Reclaim a crashed job so it can resume from its checkpoint.

        Returns the job dict (with ``checkpoint`` populated) or None.
        """
        now = _now_iso()
        async with self._db.execute(
            "SELECT id FROM job_queue WHERE status='crashed' ORDER BY updated_at ASC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        job_id = row[0]
        await self._db.execute(
            """
            UPDATE job_queue
               SET status    = 'running',
                   locked_by = ?,
                   locked_at = ?,
                   updated_at= ?
             WHERE id = ? AND status = 'crashed'
            """,
            (worker_id, now, now, job_id),
        )
        await self._db.commit()
        return await self.get(job_id)

    # ── reads ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """Return one job row as a dict, or None."""
        async with self._db.execute(
            "SELECT * FROM job_queue WHERE id = ?", (job_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(cur, row)

    async def depth(
        self,
        project_id: str | None = None,
        job_type: str | None = None,
        status: str = "pending",
    ) -> int:
        """Return the number of jobs in *status* (queue depth / backpressure metric)."""
        where_clauses = ["status = ?"]
        params: list[Any] = [status]
        if project_id is not None:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if job_type is not None:
            where_clauses.append("job_type = ?")
            params.append(job_type)
        where = " AND ".join(where_clauses)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM job_queue WHERE {where}", params
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def depth_by_status(
        self, project_id: str | None = None
    ) -> dict[str, int]:
        """Return counts keyed by status for backpressure/metrics reporting."""
        where = "WHERE project_id = ?" if project_id is not None else ""
        params = [project_id] if project_id is not None else []
        async with self._db.execute(
            f"SELECT status, COUNT(*) FROM job_queue {where} GROUP BY status",
            params,
        ) as cur:
            rows = await cur.fetchall()
        return {r[0]: int(r[1]) for r in rows}


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    """Convert an aiosqlite row to a plain dict using cursor.description."""
    if hasattr(cursor, "description") and cursor.description:
        keys = [d[0] for d in cursor.description]
        d = dict(zip(keys, row))
    else:
        # Fallback: positional mapping for known columns
        cols = (
            "id", "project_id", "job_type", "payload", "status",
            "priority", "attempts", "max_attempts", "available_at",
            "locked_by", "locked_at", "last_error", "checkpoint",
            "created_at", "updated_at",
        )
        d = dict(zip(cols, row))
    # Deserialise payload JSON
    if isinstance(d.get("payload"), str):
        try:
            d["payload"] = json.loads(d["payload"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
