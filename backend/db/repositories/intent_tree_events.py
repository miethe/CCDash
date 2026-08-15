"""Concrete repositories for the ``intent_tree_events`` raw append-only table.

``intent_tree_events`` mirrors ``node.created``/``node.completed`` rows pulled
from IntentTree's ``GET /api/v1/events`` domain event log (are-we-winning-
dashboard-v1 M1; see ``backend/db/sqlite_migrations.py`` / ``backend/db/
postgres_migrations.py`` for the dual DDL). This module owns the single
idempotent write path used by ``IntentTreeEventsIngestService``
(``backend/application/services/ingest/intenttree_events_ingest.py``).

Idempotency contract: ``id`` (the IntentTree event id) is the primary key.
``insert_if_not_exists`` is a no-op (returns ``False``) when the row already
exists -- re-ingesting an overlapping page never produces a duplicate row.

Both implementations share the exact same ordered column list
(``INTENT_TREE_EVENTS_COLUMNS``) so the two DDLs and the two INSERT
statements cannot silently drift apart (ADR-007 dual-DDL parity discipline;
mirrors ``backend/db/repositories/rf_events.py`` exactly).
"""
from __future__ import annotations

from typing import Any

import aiosqlite

# ── Shared column contract ───────────────────────────────────────────────────
#
# Ordered list of every column written by an insert (excludes ``ingested_at``,
# which both DDLs default server-side).

INTENT_TREE_EVENTS_COLUMNS: tuple[str, ...] = (
    "id",
    "workspace_id",
    "tree_id",
    "node_id",
    "event_type",
    "actor_type",
    "actor_id",
    "occurred_at",
    "payload_json",
)


def _row_values(row: dict[str, Any]) -> tuple[Any, ...]:
    """Return *row*'s values in ``INTENT_TREE_EVENTS_COLUMNS`` order.

    Missing keys resolve to ``None`` -- unknown == null, never a fabricated
    default (same convention as ``rf_events.py``).
    """
    return tuple(row.get(col) for col in INTENT_TREE_EVENTS_COLUMNS)


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteIntentTreeEventsRepository:
    """aiosqlite-backed writer for ``intent_tree_events``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        """Insert *row* (keyed by the ``INTENT_TREE_EVENTS_COLUMNS`` contract).

        Returns ``True`` when a new row was inserted, ``False`` when ``id``
        already existed (idempotent no-op).
        """
        columns_sql = ", ".join(INTENT_TREE_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(INTENT_TREE_EVENTS_COLUMNS))
        cursor = await self.db.execute(
            f"INSERT OR IGNORE INTO intent_tree_events ({columns_sql}) VALUES ({placeholders_sql})",
            _row_values(row),
        )
        await self.db.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


# ── PostgreSQL ──────────────────────────────────────────────────────────────


class PostgresIntentTreeEventsRepository:
    """asyncpg-backed writer for ``intent_tree_events``."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        """Insert *row* (keyed by the ``INTENT_TREE_EVENTS_COLUMNS`` contract).

        Returns ``True`` when a new row was inserted, ``False`` when ``id``
        already existed (idempotent no-op).
        """
        columns_sql = ", ".join(INTENT_TREE_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(INTENT_TREE_EVENTS_COLUMNS) + 1))
        status = await self.db.execute(
            f"INSERT INTO intent_tree_events ({columns_sql}) VALUES ({placeholders_sql}) "
            "ON CONFLICT (id) DO NOTHING",
            *_row_values(row),
        )
        # asyncpg Connection.execute() returns a command-status string, e.g.
        # "INSERT 0 1" (inserted) or "INSERT 0 0" (conflict, no-op).
        try:
            affected = int(status.split()[-1])
        except (AttributeError, ValueError, IndexError):
            affected = 0
        return affected > 0


__all__ = [
    "INTENT_TREE_EVENTS_COLUMNS",
    "SqliteIntentTreeEventsRepository",
    "PostgresIntentTreeEventsRepository",
]
