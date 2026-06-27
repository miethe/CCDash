"""Job queue repository — PostgreSQL / asyncpg implementation (P3-006-FU).

Mirrors ``SqliteJobQueueRepository`` method-for-method.  Uses
``FOR UPDATE SKIP LOCKED`` in ``claim()`` for concurrency-safe
multi-worker claiming (no deadlocks when N workers race).  JSONB
columns for ``payload`` and ``checkpoint``.

Timestamps (available_at / locked_at / created_at / updated_at) are stored as
``TEXT`` (ISO-8601), NOT ``TIMESTAMPTZ``: the repo binds ISO ``str`` values and
asyncpg's default timestamptz codec rejects ``str`` binds (DataError). TEXT keeps
parity with the SQLite schema and the rest of the repo layer. See the durable-
queue DDL and ``_ensure_durable_queue_text_timestamps`` in postgres_migrations.py.

Columns (matching the SQLite schema):
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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("ccdash.db.repositories.postgres.job_queue")

# ─── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _backoff_seconds(attempts: int, base: float = 5.0, cap: float = 300.0) -> float:
    """Exponential backoff: base * 2^attempts, capped at cap seconds."""
    return min(base * (2 ** attempts), cap)


def _available_at_iso(delay_seconds: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return dt.isoformat().replace("+00:00", "Z")


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an asyncpg Record (or mapping-compatible row) to a plain dict.

    asyncpg Records support attribute access and dict-like iteration.
    JSONB columns are already decoded by asyncpg as Python objects; we
    normalise payload to a dict for parity with the SQLite repo.
    """
    d: dict[str, Any] = dict(row)
    # Normalise payload: asyncpg returns JSONB as a Python object already,
    # but accept str fallback (shouldn't happen with JSONB).
    payload = d.get("payload")
    if isinstance(payload, str):
        try:
            d["payload"] = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            pass
    elif payload is None:
        d["payload"] = {}
    # Timestamps: asyncpg may return datetime objects for TIMESTAMPTZ; convert
    # to ISO-8601 strings so callers get the same shape as the SQLite repo.
    for col in ("available_at", "locked_at", "created_at", "updated_at"):
        val = d.get(col)
        if isinstance(val, datetime):
            d[col] = val.isoformat().replace("+00:00", "Z")
    return d


# ─── PostgreSQL implementation ─────────────────────────────────────────────────


class PostgresJobQueueRepository:
    """Async job queue over an asyncpg connection or pool.

    The repository is stateless beyond the ``db`` handle; all state lives
    in the ``job_queue`` table.

    ``db`` must expose an ``execute`` / ``fetch`` / ``fetchrow`` interface
    compatible with asyncpg ``Connection`` or ``Pool``.
    """

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool (or protocol-compatible)
        self._db = db

    @asynccontextmanager
    async def _acquire(self):
        """Yield a single asyncpg Connection for a multi-statement transaction.

        ``self._db`` may be a Pool (exposes ``.acquire()``) or an
        already-acquired Connection (no ``.acquire()``). A transaction and its
        ``FOR UPDATE SKIP LOCKED`` queries MUST share one connection, so acquire
        once here and run the whole block against the yielded connection.
        """
        if hasattr(self._db, "acquire"):
            async with self._db.acquire() as conn:
                yield conn
        else:
            yield self._db

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
        payload_json = json.dumps(payload)
        await self._db.execute(
            """
            INSERT INTO job_queue
                (id, project_id, job_type, payload, status,
                 priority, attempts, max_attempts,
                 available_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, 'pending', $5, 0, $6, $7, $8, $9)
            """,
            jid,
            project_id,
            job_type,
            payload_json,
            priority,
            max_attempts,
            av,
            now,
            now,
        )
        logger.debug("Enqueued job id=%s type=%s project=%s", jid, job_type, project_id)
        return jid

    # ── claim (FOR UPDATE SKIP LOCKED) ────────────────────────────────────────

    async def claim(
        self,
        job_type: str | None = None,
        project_id: str | None = None,
        *,
        worker_id: str,
        max_in_flight: int = 5,
    ) -> dict[str, Any] | None:
        """Claim the next available pending job.

        Uses ``SELECT … FOR UPDATE SKIP LOCKED`` inside a transaction for
        concurrency-safe multi-worker claiming — no two workers will claim
        the same job even under simultaneous contention.

        Returns the full row dict, or None if the queue is empty or the
        backpressure limit is reached.
        """
        now = _now_iso()

        async with self._acquire() as conn:
            async with conn.transaction():
                # Backpressure: count how many jobs this worker currently holds.
                in_flight = await conn.fetchval(
                    "SELECT COUNT(*) FROM job_queue WHERE status = 'running' AND locked_by = $1",
                    worker_id,
                )
                in_flight = int(in_flight or 0)
                if in_flight >= max_in_flight:
                    logger.debug(
                        "Worker '%s' at in-flight limit (%d/%d) — skipping claim",
                        worker_id,
                        in_flight,
                        max_in_flight,
                    )
                    return None

                # Build dynamic WHERE clause
                where_clauses = ["status = 'pending'", "available_at <= $1"]
                params: list[Any] = [now]
                idx = 2
                if job_type is not None:
                    where_clauses.append(f"job_type = ${idx}")
                    params.append(job_type)
                    idx += 1
                if project_id is not None:
                    where_clauses.append(f"project_id = ${idx}")
                    params.append(project_id)
                    idx += 1

                where = " AND ".join(where_clauses)
                select_sql = f"""
                    SELECT id FROM job_queue
                    WHERE {where}
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """
                row = await conn.fetchrow(select_sql, *params)
                if row is None:
                    return None

                job_id = row["id"]
                await conn.execute(
                    """
                    UPDATE job_queue
                       SET status     = 'running',
                           locked_by  = $1,
                           locked_at  = $2,
                           updated_at = $3
                     WHERE id = $4 AND status = 'pending'
                    """,
                    worker_id,
                    now,
                    now,
                    job_id,
                )

        return await self.get(job_id)

    # ── complete / fail / retry / checkpoint ──────────────────────────────────

    async def complete(self, job_id: str) -> None:
        """Mark a running job as done."""
        now = _now_iso()
        await self._db.execute(
            "UPDATE job_queue SET status='done', updated_at=$1 WHERE id=$2",
            now,
            job_id,
        )

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
        row = await self._db.fetchrow(
            "SELECT attempts, max_attempts FROM job_queue WHERE id = $1",
            job_id,
        )
        if row is None:
            logger.warning("fail() called for unknown job id=%s", job_id)
            return

        attempts = (int(row["attempts"] or 0)) + 1
        max_attempts = int(row["max_attempts"] or 3)

        if attempts < max_attempts:
            delay = _backoff_seconds(attempts)
            new_available_at = _available_at_iso(delay)
            new_status = "pending"
        else:
            new_available_at = now
            new_status = "dead"

        if checkpoint is not None:
            await self._db.execute(
                """
                UPDATE job_queue
                   SET status       = $1,
                       attempts     = $2,
                       last_error   = $3,
                       available_at = $4,
                       updated_at   = $5,
                       checkpoint   = $6::jsonb
                 WHERE id = $7
                """,
                new_status,
                attempts,
                error,
                new_available_at,
                now,
                checkpoint,
                job_id,
            )
        else:
            await self._db.execute(
                """
                UPDATE job_queue
                   SET status       = $1,
                       attempts     = $2,
                       last_error   = $3,
                       available_at = $4,
                       updated_at   = $5
                 WHERE id = $6
                """,
                new_status,
                attempts,
                error,
                new_available_at,
                now,
                job_id,
            )
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
                   last_error = $1,
                   updated_at = $2
             WHERE id = $3
            """,
            error,
            now,
            job_id,
        )

    async def save_checkpoint(self, job_id: str, checkpoint: str) -> None:
        """Persist a serialised checkpoint so a crash resume can pick up mid-progress."""
        now = _now_iso()
        await self._db.execute(
            "UPDATE job_queue SET checkpoint=$1::jsonb, updated_at=$2 WHERE id=$3",
            checkpoint,
            now,
            job_id,
        )

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
        async with self._acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id FROM job_queue
                     WHERE status='crashed'
                     ORDER BY updated_at ASC
                     LIMIT 1
                     FOR UPDATE SKIP LOCKED
                    """
                )
                if row is None:
                    return None
                job_id = row["id"]
                await conn.execute(
                    """
                    UPDATE job_queue
                       SET status    = 'running',
                           locked_by = $1,
                           locked_at = $2,
                           updated_at= $3
                     WHERE id = $4 AND status = 'crashed'
                    """,
                    worker_id,
                    now,
                    now,
                    job_id,
                )
        return await self.get(job_id)

    # ── reads ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """Return one job row as a dict, or None."""
        row = await self._db.fetchrow(
            "SELECT * FROM job_queue WHERE id = $1",
            job_id,
        )
        if row is None:
            return None
        return _row_to_dict(row)

    async def depth(
        self,
        project_id: str | None = None,
        job_type: str | None = None,
        status: str = "pending",
    ) -> int:
        """Return the number of jobs in *status* (queue depth / backpressure metric)."""
        where_clauses = ["status = $1"]
        params: list[Any] = [status]
        idx = 2
        if project_id is not None:
            where_clauses.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if job_type is not None:
            where_clauses.append(f"job_type = ${idx}")
            params.append(job_type)
            idx += 1
        where = " AND ".join(where_clauses)
        count = await self._db.fetchval(
            f"SELECT COUNT(*) FROM job_queue WHERE {where}",
            *params,
        )
        return int(count or 0)

    async def depth_by_status(
        self,
        project_id: str | None = None,
    ) -> dict[str, int]:
        """Return counts keyed by status for backpressure/metrics reporting."""
        if project_id is not None:
            rows = await self._db.fetch(
                "SELECT status, COUNT(*) AS cnt FROM job_queue WHERE project_id = $1 GROUP BY status",
                project_id,
            )
        else:
            rows = await self._db.fetch(
                "SELECT status, COUNT(*) AS cnt FROM job_queue GROUP BY status"
            )
        return {row["status"]: int(row["cnt"]) for row in rows}
