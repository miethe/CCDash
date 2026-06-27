"""SQLite/asyncpg-dual-path repository for OQ resolutions (P3-002).

The ``oq_resolutions`` table was created in SCHEMA_VERSION 30 with columns:
    id, project_id, feature_id, oq_id, question, answer_text, severity,
    resolved, pending_sync, source_document_id, source_document_path,
    resolved_by, created_at, updated_at
UNIQUE(project_id, feature_id, oq_id)

This module is the sole DB access layer for that table.  All callers should
import :class:`OQResolutionsRepository` and instantiate it with the raw
``aiosqlite.Connection`` or asyncpg pool/connection already used by planning.py.
"""
from __future__ import annotations

import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_UPSERT_SQLITE = """
    INSERT INTO oq_resolutions
        (project_id, feature_id, oq_id, question, answer_text, severity,
         resolved, pending_sync, source_document_id, source_document_path,
         resolved_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(project_id, feature_id, oq_id) DO UPDATE SET
        question            = excluded.question,
        answer_text         = excluded.answer_text,
        severity            = excluded.severity,
        resolved            = excluded.resolved,
        pending_sync        = excluded.pending_sync,
        source_document_id  = excluded.source_document_id,
        source_document_path= excluded.source_document_path,
        resolved_by         = excluded.resolved_by,
        updated_at          = excluded.updated_at
"""

_UPSERT_PG = """
    INSERT INTO oq_resolutions
        (project_id, feature_id, oq_id, question, answer_text, severity,
         resolved, pending_sync, source_document_id, source_document_path,
         resolved_by, created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    ON CONFLICT(project_id, feature_id, oq_id) DO UPDATE SET
        question             = EXCLUDED.question,
        answer_text          = EXCLUDED.answer_text,
        severity             = EXCLUDED.severity,
        resolved             = EXCLUDED.resolved,
        pending_sync         = EXCLUDED.pending_sync,
        source_document_id   = EXCLUDED.source_document_id,
        source_document_path = EXCLUDED.source_document_path,
        resolved_by          = EXCLUDED.resolved_by,
        updated_at           = EXCLUDED.updated_at
"""

_SELECT_FOR_FEATURE_SQLITE = """
    SELECT project_id, feature_id, oq_id, question, answer_text, severity,
           resolved, pending_sync, source_document_id, source_document_path,
           resolved_by, created_at, updated_at
    FROM oq_resolutions
    WHERE project_id = ? AND feature_id = ?
"""

_SELECT_FOR_FEATURE_PG = """
    SELECT project_id, feature_id, oq_id, question, answer_text, severity,
           resolved, pending_sync, source_document_id, source_document_path,
           resolved_by, created_at, updated_at
    FROM oq_resolutions
    WHERE project_id = $1 AND feature_id = $2
"""

_SELECT_ONE_SQLITE = _SELECT_FOR_FEATURE_SQLITE + " AND oq_id = ?"
_SELECT_ONE_PG = _SELECT_FOR_FEATURE_PG + " AND oq_id = $3"

_DELETE_FOR_PROJECT_SQLITE = "DELETE FROM oq_resolutions WHERE project_id = ?"
_DELETE_FOR_PROJECT_PG = "DELETE FROM oq_resolutions WHERE project_id = $1"


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Normalise a raw DB row to a plain dict regardless of driver."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    # aiosqlite Row (tuple-like with description); asyncpg Record
    try:
        return dict(row)
    except Exception:  # noqa: BLE001
        # Tuple positional fallback (column order must match SELECT)
        _COLS = (
            "project_id", "feature_id", "oq_id", "question", "answer_text",
            "severity", "resolved", "pending_sync", "source_document_id",
            "source_document_path", "resolved_by", "created_at", "updated_at",
        )
        return {col: row[i] for i, col in enumerate(_COLS) if i < len(row)}


class OQResolutionsRepository:
    """DB access layer for ``oq_resolutions``.

    Supports both SQLite (``aiosqlite.Connection``) and PostgreSQL
    (asyncpg pool or connection) via the same dual-path pattern used
    throughout ``backend/db/repositories/``.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    # ── Upsert ────────────────────────────────────────────────────────────────

    async def upsert(self, data: dict[str, Any]) -> None:
        """Insert or update a resolution row keyed by (project_id, feature_id, oq_id).

        All fields are optional except the three key fields.  Missing / falsy
        fields fall back to safe defaults so a partial update (e.g. setting only
        ``answer_text`` and ``resolved``) does not clobber existing metadata.
        """
        project_id = str(data.get("project_id") or "")
        feature_id = str(data.get("feature_id") or "")
        oq_id = str(data.get("oq_id") or "")
        if not (project_id and feature_id and oq_id):
            raise ValueError(
                "upsert requires non-empty project_id, feature_id, and oq_id"
            )

        question = str(data.get("question") or "")
        answer_text = str(data.get("answer_text") or "")
        severity = str(data.get("severity") or "medium")
        resolved = int(bool(data.get("resolved", False)))
        pending_sync = int(bool(data.get("pending_sync", False)))
        source_document_id = str(data.get("source_document_id") or "")
        source_document_path = str(data.get("source_document_path") or "")
        resolved_by = str(data.get("resolved_by") or "")
        created_at = str(data.get("created_at") or "")
        updated_at = str(data.get("updated_at") or "")

        try:
            if isinstance(self._db, aiosqlite.Connection):
                await self._db.execute(
                    _UPSERT_SQLITE,
                    (
                        project_id, feature_id, oq_id, question, answer_text,
                        severity, resolved, pending_sync, source_document_id,
                        source_document_path, resolved_by, created_at, updated_at,
                    ),
                )
                await self._db.commit()
            else:
                await self._db.execute(
                    _UPSERT_PG,
                    project_id, feature_id, oq_id, question, answer_text,
                    severity, resolved, pending_sync, source_document_id,
                    source_document_path, resolved_by, created_at, updated_at,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OQResolutionsRepository.upsert failed "
                "(project_id=%r, feature_id=%r, oq_id=%r): %s",
                project_id, feature_id, oq_id, exc,
            )
            raise

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def list_for_feature(
        self,
        project_id: str,
        feature_id: str,
    ) -> list[dict[str, Any]]:
        """Return all resolution rows for the given (project_id, feature_id) pair."""
        try:
            if isinstance(self._db, aiosqlite.Connection):
                async with self._db.execute(
                    _SELECT_FOR_FEATURE_SQLITE, (project_id, feature_id)
                ) as cur:
                    rows = await cur.fetchall()
                    return [_row_to_dict(r) for r in rows]
            else:
                rows = await self._db.fetch(
                    _SELECT_FOR_FEATURE_PG, project_id, feature_id
                )
                return [_row_to_dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OQResolutionsRepository.list_for_feature failed "
                "(project_id=%r, feature_id=%r): %s",
                project_id, feature_id, exc,
            )
            return []

    async def get_one(
        self,
        project_id: str,
        feature_id: str,
        oq_id: str,
    ) -> dict[str, Any] | None:
        """Return a single resolution row, or ``None`` if not found."""
        try:
            if isinstance(self._db, aiosqlite.Connection):
                async with self._db.execute(
                    _SELECT_ONE_SQLITE, (project_id, feature_id, oq_id)
                ) as cur:
                    row = await cur.fetchone()
                    return _row_to_dict(row) if row is not None else None
            else:
                row = await self._db.fetchrow(
                    _SELECT_ONE_PG, project_id, feature_id, oq_id
                )
                return _row_to_dict(row) if row is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OQResolutionsRepository.get_one failed "
                "(project_id=%r, feature_id=%r, oq_id=%r): %s",
                project_id, feature_id, oq_id, exc,
            )
            return None
