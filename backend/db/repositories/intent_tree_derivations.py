"""Concrete repositories for the M2-part-B derived-cache tables.

``intent_tree_reopened_events`` and ``intent_tree_self_caught_buckets`` (are-
we-winning-dashboard-v1 M2 part B; see ``backend/db/sqlite_migrations.py`` /
``backend/db/postgres_migrations.py`` v56 for the dual DDL). Both tables are
written **only** by the derivation services under
``backend/application/services/ingest/`` (``intenttree_reopened_derivation.py``,
``intenttree_self_caught_derivation.py``) -- never by the query-service render
path (``backend/application/services/agent_queries/are_we_winning.py``), which
reads them read-only via ``list_all()``.

Idempotency contracts
----------------------
* ``intent_tree_reopened_events.id`` is the **upstream IntentTree
  NodeHistory row id**, verbatim -- exactly the same "reuse the upstream id
  as our primary key" idempotency pattern as
  ``intent_tree_events.id`` (``backend/db/repositories/intent_tree_events.py``).
  Re-deriving from the same history row is a no-op.
* ``intent_tree_self_caught_buckets.node_id`` is the primary key (one bucket
  verdict per node). ``insert_if_not_exists`` is a no-op once a node has been
  bucketed -- see the self-caught derivation service module docstring for why
  re-bucketing is deliberately NOT performed on every pass.

Both implementations share the exact same ordered column lists so the two
DDLs and the two INSERT statements cannot silently drift apart (ADR-007
dual-DDL parity discipline; mirrors ``intent_tree_events.py`` exactly).
"""
from __future__ import annotations

from typing import Any

import aiosqlite

# ── Shared column contracts ─────────────────────────────────────────────────

REOPENED_EVENTS_COLUMNS: tuple[str, ...] = (
    "id",
    "node_id",
    "from_status",
    "to_status",
    "occurred_at",
)

SELF_CAUGHT_BUCKETS_COLUMNS: tuple[str, ...] = (
    "node_id",
    "bucket",
    "reason",
)


def _row_values(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[Any, ...]:
    """Return *row*'s values in *columns* order. Missing keys resolve to ``None``."""
    return tuple(row.get(col) for col in columns)


# ── Reopened events ──────────────────────────────────────────────────────────


class SqliteIntentTreeReopenedEventsRepository:
    """aiosqlite-backed writer/reader for ``intent_tree_reopened_events``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        columns_sql = ", ".join(REOPENED_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(REOPENED_EVENTS_COLUMNS))
        cursor = await self.db.execute(
            f"INSERT OR IGNORE INTO intent_tree_reopened_events ({columns_sql}) "
            f"VALUES ({placeholders_sql})",
            _row_values(row, REOPENED_EVENTS_COLUMNS),
        )
        await self.db.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT id, node_id, from_status, to_status, occurred_at "
            "FROM intent_tree_reopened_events ORDER BY occurred_at ASC"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


class PostgresIntentTreeReopenedEventsRepository:
    """asyncpg-backed writer/reader for ``intent_tree_reopened_events``."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        columns_sql = ", ".join(REOPENED_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(REOPENED_EVENTS_COLUMNS) + 1))
        status = await self.db.execute(
            f"INSERT INTO intent_tree_reopened_events ({columns_sql}) VALUES ({placeholders_sql}) "
            "ON CONFLICT (id) DO NOTHING",
            *_row_values(row, REOPENED_EVENTS_COLUMNS),
        )
        try:
            affected = int(status.split()[-1])
        except (AttributeError, ValueError, IndexError):
            affected = 0
        return affected > 0

    async def list_all(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT id, node_id, from_status, to_status, occurred_at "
            "FROM intent_tree_reopened_events ORDER BY occurred_at ASC"
        )
        return [dict(r) for r in rows]


# ── Self-caught buckets ──────────────────────────────────────────────────────


class SqliteIntentTreeSelfCaughtBucketsRepository:
    """aiosqlite-backed writer/reader for ``intent_tree_self_caught_buckets``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        columns_sql = ", ".join(SELF_CAUGHT_BUCKETS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(SELF_CAUGHT_BUCKETS_COLUMNS))
        cursor = await self.db.execute(
            f"INSERT OR IGNORE INTO intent_tree_self_caught_buckets ({columns_sql}) "
            f"VALUES ({placeholders_sql})",
            _row_values(row, SELF_CAUGHT_BUCKETS_COLUMNS),
        )
        await self.db.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)

    async def get_bucketed_node_ids(self) -> set[str]:
        """Node ids already bucketed -- the derivation service's incremental skip-set."""
        async with self.db.execute("SELECT node_id FROM intent_tree_self_caught_buckets") as cur:
            rows = await cur.fetchall()
        return {str(r["node_id"]) for r in rows}

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT node_id, bucket, reason FROM intent_tree_self_caught_buckets ORDER BY node_id ASC"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


class PostgresIntentTreeSelfCaughtBucketsRepository:
    """asyncpg-backed writer/reader for ``intent_tree_self_caught_buckets``."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        columns_sql = ", ".join(SELF_CAUGHT_BUCKETS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(SELF_CAUGHT_BUCKETS_COLUMNS) + 1))
        status = await self.db.execute(
            f"INSERT INTO intent_tree_self_caught_buckets ({columns_sql}) VALUES ({placeholders_sql}) "
            "ON CONFLICT (node_id) DO NOTHING",
            *_row_values(row, SELF_CAUGHT_BUCKETS_COLUMNS),
        )
        try:
            affected = int(status.split()[-1])
        except (AttributeError, ValueError, IndexError):
            affected = 0
        return affected > 0

    async def get_bucketed_node_ids(self) -> set[str]:
        rows = await self.db.fetch("SELECT node_id FROM intent_tree_self_caught_buckets")
        return {str(r["node_id"]) for r in rows}

    async def list_all(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT node_id, bucket, reason FROM intent_tree_self_caught_buckets ORDER BY node_id ASC"
        )
        return [dict(r) for r in rows]


__all__ = [
    "REOPENED_EVENTS_COLUMNS",
    "SELF_CAUGHT_BUCKETS_COLUMNS",
    "SqliteIntentTreeReopenedEventsRepository",
    "PostgresIntentTreeReopenedEventsRepository",
    "SqliteIntentTreeSelfCaughtBucketsRepository",
    "PostgresIntentTreeSelfCaughtBucketsRepository",
]
