"""Concrete repositories for the ``aar_reviews`` rollup table.

``aar_reviews`` (T1-005/T1-006/T1-007, ``ccdash-automated-aar-review-v1``
Phase 1, v42) persists one row per ``(aar_document_id, session_id)`` pairing
computed by the deterministic AAR-document-to-session triage service
(``backend/application/services/agent_queries/aar_review.py`` ::
``AARReviewQueryService``). A single AAR document that correlates to N
sessions fans out into N rows -- each row carries the SAME
correlation/flags/triage_verdict snapshot but a distinct ``session_id``. The
composite ``PRIMARY KEY (aar_document_id, session_id)`` declared in both
DDL files (``backend/db/sqlite_migrations.py`` / ``backend/db/postgres_migrations.py``,
v42) is both the natural dedup key (recomputing the same document never
duplicates a pairing already on file) and the upsert conflict target used by
every write below.

HARD INVARIANT: this module never computes a triage verdict, a correlation,
or a flag -- it is pure persistence. All derivation logic lives in
``aar_review.py`` and is reused verbatim, never reimplemented here (see
``build_aar_review_row``, which maps an already-computed ``AARReviewDTO``
onto a persistable row and is the ONLY place this module reads that DTO's
shape).

Both repository implementations below build their upsert statements from the
same ordered ``AAR_REVIEWS_COLUMNS`` contract so the two DDLs and the two
INSERT column lists cannot silently drift apart (ADR-007 dual-DDL parity
discipline) -- mirrors ``backend/db/repositories/research_runs.py`` /
``backend/db/repositories/rf_events.py`` exactly.

Every write on both backends is wrapped in
``backend.db.repositories.base.retry_on_locked`` per this phase's explicit
ADR-007 write-path requirement.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Mapping

import aiosqlite

from backend.db.repositories.base import retry_on_locked

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a hard import cycle
    from backend.application.services.agent_queries.models import AARReviewDTO

logger = logging.getLogger("ccdash.db.aar_reviews")

_REPO_NAME = "aar_reviews"


# ── Shared column contract ───────────────────────────────────────────────────
#
# Ordered list of every column written by an upsert (excludes ``created_at``/
# ``updated_at``, which the DDL defaults server-side on insert and the SET
# clause below sets explicitly to "now" on conflict).

AAR_REVIEWS_COLUMNS: tuple[str, ...] = (
    "aar_document_id",
    "session_id",
    "project_id",
    "aar_document_path",
    "correlation",
    "flags",
    "triage_verdict",
    "triage_reasons",
    "evidence_refs",
    "generated_at",
    "provenance_skill_name",
    "provenance_workflow_id",
)

# Columns updated on conflict (everything except the dedup key itself).
_UPDATE_COLUMNS: tuple[str, ...] = tuple(
    col for col in AAR_REVIEWS_COLUMNS if col not in ("aar_document_id", "session_id")
)


def _row_values(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return *row*'s values in ``AAR_REVIEWS_COLUMNS`` order."""
    return tuple(row.get(col) for col in AAR_REVIEWS_COLUMNS)


def build_aar_review_row(
    dto: "AARReviewDTO",
    session_id: str,
    *,
    project_id: str,
    aar_document_path: str = "",
    provenance_skill_name: str | None = None,
    provenance_workflow_id: str | None = None,
) -> dict[str, Any]:
    """Map one already-computed ``AARReviewDTO`` onto a single persistable row.

    *session_id* MUST be one of ``dto.correlation.session_ids`` -- callers
    (e.g. the T1-008 backfill hook) fan a single DTO out into one row per
    resolved session. ``triage_reasons``/``evidence_refs`` map from the DTO's
    ``reasons``/``source_refs`` fields respectively (see PRD §7.2 field
    naming vs. this table's column naming -- the mapping is deliberate, not a
    typo). Guard-input provenance columns default to ``None`` (unenforced
    until Phase 6) -- unknown == null, never a fabricated default.

    This function performs zero derivation: every value it writes already
    exists on *dto*, verbatim or JSON-encoded.
    """
    return {
        "aar_document_id": dto.document_id,
        "session_id": session_id,
        "project_id": project_id,
        "aar_document_path": aar_document_path,
        "correlation": json.dumps(dto.correlation.model_dump()),
        "flags": json.dumps([flag.model_dump() for flag in dto.flags]),
        "triage_verdict": dto.triage_verdict,
        "triage_reasons": json.dumps(list(dto.reasons)),
        "evidence_refs": json.dumps(list(dto.source_refs)),
        "generated_at": dto.generated_at,
        "provenance_skill_name": provenance_skill_name,
        "provenance_workflow_id": provenance_workflow_id,
    }


def build_aar_review_rows(
    dto: "AARReviewDTO",
    *,
    project_id: str,
    aar_document_path: str = "",
    provenance_skill_name: str | None = None,
    provenance_workflow_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fan *dto* out into one row per ``dto.correlation.session_ids`` entry.

    Returns an empty list when correlation resolved zero sessions -- there is
    no ``(aar_document_id, session_id)`` pairing to persist in that case
    (e.g. ``human_triage_required`` with a missing/null confidence). This is
    the contract the T1-008 backfill hook relies on: "row count matches the
    discoverable pair count" means documents with no discoverable session
    pairing contribute zero rows, not a placeholder row.
    """
    return [
        build_aar_review_row(
            dto,
            session_id,
            project_id=project_id,
            aar_document_path=aar_document_path,
            provenance_skill_name=provenance_skill_name,
            provenance_workflow_id=provenance_workflow_id,
        )
        for session_id in dto.correlation.session_ids
    ]


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteAarReviewsRepository:
    """aiosqlite-backed writer/reader for ``aar_reviews``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def upsert(self, row: Mapping[str, Any]) -> None:
        """Upsert one ``AAR_REVIEWS_COLUMNS``-shaped row by ``(aar_document_id, session_id)``."""
        columns_sql = ", ".join(AAR_REVIEWS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(AAR_REVIEWS_COLUMNS))
        set_clause = ",\n                ".join(
            f"{col} = excluded.{col}" for col in _UPDATE_COLUMNS
        )
        values = _row_values(row)

        async def _write() -> None:
            await self.db.execute(
                f"INSERT INTO aar_reviews ({columns_sql}) VALUES ({placeholders_sql}) "
                f"ON CONFLICT(aar_document_id, session_id) DO UPDATE SET\n"
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

    async def get_one(self, aar_document_id: str, session_id: str) -> dict[str, Any] | None:
        cursor = await self.db.execute(
            "SELECT * FROM aar_reviews WHERE aar_document_id = ? AND session_id = ?",
            (aar_document_id, session_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_by_document(self, aar_document_id: str) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT * FROM aar_reviews WHERE aar_document_id = ? ORDER BY session_id",
            (aar_document_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_by_project(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT * FROM aar_reviews WHERE project_id = ? "
            "ORDER BY generated_at DESC, aar_document_id, session_id LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count_by_project(self, project_id: str) -> int:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM aar_reviews WHERE project_id = ?", (project_id,)
        )
        (count,) = await cursor.fetchone()
        return int(count)

    async def list_document_session_pairs(self, project_id: str) -> list[dict[str, Any]]:
        """Phase 6 (T6-004) dedup-ledger read: every persisted ``(aar_document_id, session_id)``
        pair for *project_id*, WITHOUT the JSON correlation/flags/evidence columns.

        Read-only, no derivation -- a lighter projection of ``get_by_project`` for callers
        (``AARReviewSweepJob``) that only need the ledger's key columns, not the full row.
        """
        cursor = await self.db.execute(
            "SELECT aar_document_id, session_id, generated_at FROM aar_reviews WHERE project_id = ?",
            (project_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ── PostgreSQL ──────────────────────────────────────────────────────────────


class PostgresAarReviewsRepository:
    """asyncpg-backed writer/reader for ``aar_reviews``."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def upsert(self, row: Mapping[str, Any]) -> None:
        columns_sql = ", ".join(AAR_REVIEWS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(AAR_REVIEWS_COLUMNS) + 1))
        set_clause = ",\n                ".join(
            f"{col} = excluded.{col}" for col in _UPDATE_COLUMNS
        )
        values = _row_values(row)

        async def _write() -> None:
            await self.db.execute(
                f"INSERT INTO aar_reviews ({columns_sql}) VALUES ({placeholders_sql}) "
                f"ON CONFLICT(aar_document_id, session_id) DO UPDATE SET\n"
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

    async def get_one(self, aar_document_id: str, session_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM aar_reviews WHERE aar_document_id = $1 AND session_id = $2",
            aar_document_id,
            session_id,
        )
        return dict(row) if row else None

    async def get_by_document(self, aar_document_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM aar_reviews WHERE aar_document_id = $1 ORDER BY session_id",
            aar_document_id,
        )
        return [dict(row) for row in rows]

    async def get_by_project(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM aar_reviews WHERE project_id = $1 "
            "ORDER BY generated_at DESC, aar_document_id, session_id LIMIT $2 OFFSET $3",
            project_id,
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def count_by_project(self, project_id: str) -> int:
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM aar_reviews WHERE project_id = $1", project_id
        )

    async def list_document_session_pairs(self, project_id: str) -> list[dict[str, Any]]:
        """Phase 6 (T6-004) dedup-ledger read -- see SqliteAarReviewsRepository's docstring."""
        rows = await self.db.fetch(
            "SELECT aar_document_id, session_id, generated_at FROM aar_reviews WHERE project_id = $1",
            project_id,
        )
        return [dict(row) for row in rows]


__all__ = [
    "AAR_REVIEWS_COLUMNS",
    "build_aar_review_row",
    "build_aar_review_rows",
    "SqliteAarReviewsRepository",
    "PostgresAarReviewsRepository",
]
