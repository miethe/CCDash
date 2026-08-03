"""Concrete repositories for the ``routing_rollup`` table.

``routing_rollup`` (T2-002/T2-003, ``proof-to-routing-loop-v1`` Phase 2, v43)
persists one row per ``(project_id, source_skill_name, model)`` key, computed
by the deterministic Rollup Compute Service
(``backend/application/services/agent_queries/routing_rollup.py``, Phase 3 --
not yet built as of this module). The composite
``PRIMARY KEY (project_id, source_skill_name, model)`` declared in both DDL
files (``backend/db/sqlite_migrations.py`` / ``backend/db/postgres_migrations.py``,
v43) is both the natural dedup key and the upsert conflict target used by
every write below. ``window_start``/``window_end`` are ordinary,
UPDATE-in-place columns reflecting the CURRENT rolling window -- they are
deliberately excluded from the key (see the DDL header comment block and
Phase 2's design notes) so a re-sweep of the same key updates the row in
place rather than growing the table unboundedly.

HARD INVARIANT: this module never computes a rollup metric, a ``task_class``,
or a ``provider`` -- it is pure persistence. All derivation logic belongs to
the Phase 3 query/compute service.

**Deliberate deviation from the ``aar_reviews.py`` clone anchor**: unlike
``aar_reviews.py``, this module has no ``build_routing_rollup_row()``
mapping helper. ``aar_reviews.py`` has one because the AAR-document triage
compute service (and its DTO, ``AARReviewDTO``) already existed before its
persistence layer shipped. Here, the compute service
(``RoutingRollupQueryService``) and its DTOs (``RoutingRollupKeyDTO`` /
``RoutingRollupResponseDTO`` in ``backend/application/services/agent_queries/models.py``)
do not exist yet -- they are Phase 3's deliverable, which *depends on* this
phase, not the other way around. ``routing_rollup.py`` therefore accepts
already-shaped ``Mapping[str, Any]`` rows keyed by ``ROUTING_ROLLUP_COLUMNS``
rather than a DTO object; ``ROUTING_ROLLUP_COLUMNS`` (exported in
``__all__``) is the explicit row-shape contract Phase 3 must satisfy when it
calls ``upsert()``/``upsert_many()``. A future Phase 3 implementer should not
go looking for a ``build_routing_rollup_row()`` helper -- it does not exist
here by design.

Both repository implementations below build their upsert statements from the
same ordered ``ROUTING_ROLLUP_COLUMNS`` contract so the two DDLs and the two
INSERT column lists cannot silently drift apart (ADR-007 dual-DDL parity
discipline) -- mirrors ``backend/db/repositories/aar_reviews.py`` /
``backend/db/repositories/research_runs.py`` / ``backend/db/repositories/rf_events.py``
exactly.

Every write on both backends is wrapped in
``backend.db.repositories.base.retry_on_locked`` per ADR-007's write-path
requirement.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import aiosqlite

from backend.db.repositories.base import retry_on_locked

logger = logging.getLogger("ccdash.db.routing_rollup")

_REPO_NAME = "routing_rollup"


# ── Shared column contract ───────────────────────────────────────────────────
#
# Ordered list of every column written by an upsert (excludes ``created_at``/
# ``updated_at``, which the DDL defaults server-side on insert and the SET
# clause below sets explicitly to "now" on conflict). Order matches the DDL
# column order exactly in both ``sqlite_migrations.py`` and
# ``postgres_migrations.py`` (v43; extended in v45 by DI-4c's three effort
# columns, inserted mid-list to keep this DDL-order correspondence -- safe
# because every statement built below names its columns explicitly, so nothing
# on this path is positional. Existing databases get the columns appended
# physically by ``_ensure_column``; that physical/declared order divergence is
# invisible for the same reason.)

ROUTING_ROLLUP_COLUMNS: tuple[str, ...] = (
    "project_id",
    "source_skill_name",
    "model",
    "window_start",
    "window_end",
    "task_class",
    "provider",
    "sample_count",
    "success_rate",
    "cost_index",
    "regression_rate",
    "effort_tier",
    "effort_tier_source",
    "authoritative_effort_fraction",
    "confidence",
    "eligible_for_adjustment",
    "freshness_ts",
    "contract_version",
    "taxonomy_version",
    "mapping_version",
)

# Natural grain key -- the upsert conflict target. Never
# ``(task_class, model)`` and never including ``window_start``/``window_end``
# (see module docstring + DDL header comment for the unbounded-row-growth
# rationale).
_NATURAL_KEY_COLUMNS: tuple[str, ...] = ("project_id", "source_skill_name", "model")

# Columns updated on conflict (everything except the natural key itself).
# ``window_start``/``window_end`` ARE included here -- they are ordinary,
# UPDATE-in-place columns, not key columns.
_UPDATE_COLUMNS: tuple[str, ...] = tuple(
    col for col in ROUTING_ROLLUP_COLUMNS if col not in _NATURAL_KEY_COLUMNS
)


def _row_values(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return *row*'s values in ``ROUTING_ROLLUP_COLUMNS`` order."""
    return tuple(row.get(col) for col in ROUTING_ROLLUP_COLUMNS)


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteRoutingRollupRepository:
    """aiosqlite-backed writer/reader for ``routing_rollup``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def upsert(self, row: Mapping[str, Any]) -> None:
        """Upsert one ``ROUTING_ROLLUP_COLUMNS``-shaped row by the natural grain key.

        Re-upserting the same ``(project_id, source_skill_name, model)`` key
        updates the existing row in place (including a new
        ``window_start``/``window_end`` reflecting the latest sweep's rolling
        window) -- ``COUNT(*)`` never increases on a repeat call for the same
        key.
        """
        columns_sql = ", ".join(ROUTING_ROLLUP_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(ROUTING_ROLLUP_COLUMNS))
        conflict_target = ", ".join(_NATURAL_KEY_COLUMNS)
        set_clause = ",\n                ".join(
            f"{col} = excluded.{col}" for col in _UPDATE_COLUMNS
        )
        values = _row_values(row)

        async def _write() -> None:
            await self.db.execute(
                f"INSERT INTO routing_rollup ({columns_sql}) VALUES ({placeholders_sql}) "
                f"ON CONFLICT({conflict_target}) DO UPDATE SET\n"
                f"                {set_clause},\n"
                f"                updated_at = datetime('now')",
                values,
            )
            await self.db.commit()

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def upsert_many(self, rows: list[Mapping[str, Any]]) -> int:
        """Upsert every row in *rows*; returns the number of rows written."""
        written = 0
        for row in rows:
            await self.upsert(row)
            written += 1
        return written

    async def get_by_project(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Project-scoped read, for the REST/CLI transports (Phase 5) and operator debugging."""
        cursor = await self.db.execute(
            "SELECT * FROM routing_rollup WHERE project_id = ? "
            "ORDER BY source_skill_name, model LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_all(self, *, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        """Full-table, cross-project read for Phase 3's ``RoutingRollupQueryService``
        to assemble the response envelope. The query service, not this repository,
        applies any project scoping the caller's ``AuthContext`` requires.
        """
        cursor = await self.db.execute(
            "SELECT * FROM routing_rollup "
            "ORDER BY project_id, source_skill_name, model LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count_by_project(self, project_id: str) -> int:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM routing_rollup WHERE project_id = ?", (project_id,)
        )
        (count,) = await cursor.fetchone()
        return int(count)


# ── PostgreSQL ──────────────────────────────────────────────────────────────


class PostgresRoutingRollupRepository:
    """asyncpg-backed writer/reader for ``routing_rollup``."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def upsert(self, row: Mapping[str, Any]) -> None:
        """Upsert one ``ROUTING_ROLLUP_COLUMNS``-shaped row by the natural grain key.

        See ``SqliteRoutingRollupRepository.upsert`` for the idempotency
        contract -- identical here, dialect differences aside.
        """
        columns_sql = ", ".join(ROUTING_ROLLUP_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(ROUTING_ROLLUP_COLUMNS) + 1))
        conflict_target = ", ".join(_NATURAL_KEY_COLUMNS)
        set_clause = ",\n                ".join(
            f"{col} = excluded.{col}" for col in _UPDATE_COLUMNS
        )
        values = _row_values(row)

        async def _write() -> None:
            await self.db.execute(
                f"INSERT INTO routing_rollup ({columns_sql}) VALUES ({placeholders_sql}) "
                f"ON CONFLICT({conflict_target}) DO UPDATE SET\n"
                f"                {set_clause},\n"
                f"                updated_at = CURRENT_TIMESTAMP",
                *values,
            )

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def upsert_many(self, rows: list[Mapping[str, Any]]) -> int:
        written = 0
        for row in rows:
            await self.upsert(row)
            written += 1
        return written

    async def get_by_project(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM routing_rollup WHERE project_id = $1 "
            "ORDER BY source_skill_name, model LIMIT $2 OFFSET $3",
            project_id,
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def get_all(self, *, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM routing_rollup "
            "ORDER BY project_id, source_skill_name, model LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def count_by_project(self, project_id: str) -> int:
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM routing_rollup WHERE project_id = $1", project_id
        )


__all__ = [
    "ROUTING_ROLLUP_COLUMNS",
    "SqliteRoutingRollupRepository",
    "PostgresRoutingRollupRepository",
]
