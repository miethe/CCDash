"""Concrete repositories for the ``rf_events`` raw append-only table.

``rf_events`` is a raw, append-only mirror of Research Foundry's schema-validated
``ccdash_event`` payload (T1-001; see ``backend/db/sqlite_migrations.py`` /
``backend/db/postgres_migrations.py`` v40 for the dual DDL). This module owns
the single idempotent write path used by ``RfEventsIngestService``
(``backend/application/services/ingest/rf_events_ingest.py``, T1-003).

Idempotency contract: ``event_id`` is the primary key. ``insert_if_not_exists``
is a no-op (returns ``False``) when the row already exists — re-POSTing an
identical ``event_id`` never produces a duplicate row (AC-1).

Both implementations share the exact same ordered column list
(``RF_EVENTS_COLUMNS``) so the two DDLs and the two INSERT statements cannot
silently drift apart (ADR-007 dual-DDL parity discipline).
"""
from __future__ import annotations

import logging
from typing import Any

import aiosqlite

logger = logging.getLogger("ccdash.db.rf_events")


# ── Shared column contract ───────────────────────────────────────────────────
#
# Ordered list of every column written by an insert (excludes ``created_at``,
# which both DDLs default server-side). Both repository implementations below
# build their INSERT statements from this single source of truth.

RF_EVENTS_COLUMNS: tuple[str, ...] = (
    "event_id",
    "workspace_id",
    "project_id",
    "event_timestamp",
    "rf_project",
    "run_id",
    "intent_id",
    "task_node_id",
    "agent_postures_json",
    "skillbom_ids_json",
    "tools_json",
    "input_artifacts_json",
    "output_artifacts_json",
    "metric_source_cards_created",
    "metric_claims_total",
    "metric_claims_supported",
    "metric_claims_mixed",
    "metric_claims_contradicted",
    "metric_claims_inference",
    "metric_claims_speculation",
    "metric_unsupported_claims",
    "metric_verification_passed",
    "metric_tokens_estimated",
    "metric_cost_estimated_usd",
    "metric_latency_minutes",
    "metric_rework_count",
    "metric_drift_score",
    "metric_quality_score",
    "metric_queries_executed",
    "metric_urls_extracted",
    "metric_useful_source_count",
    "metric_duplicate_rate",
    "metric_extraction_failure_rate",
    "metric_citation_coverage",
    "metric_estimated_cost_usd",
    "metric_latency_ms",
    "governance_sensitivity",
    "governance_key_profile_used",
    "governance_key_fingerprint",
    "governance_policy_passed",
    "governance_violations_json",
    "reuse_meatywiki_writeback_candidate",
    "reuse_skillbom_candidate",
    "reuse_reusable_source_pack_candidate",
    "human_review_required",
    "human_review_status",
    "human_review_reviewer",
    "raw_payload_json",
)


def _row_values(row: dict[str, Any]) -> tuple[Any, ...]:
    """Return *row*'s values in ``RF_EVENTS_COLUMNS`` order.

    Missing keys resolve to ``None`` — every RF-sourced column is nullable
    (unknown == null, never a fabricated default), except ``raw_payload_json``
    which the caller (the ingest service) always supplies.
    """
    return tuple(row.get(col) for col in RF_EVENTS_COLUMNS)


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteRfEventsRepository:
    """aiosqlite-backed writer for ``rf_events``."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        """Insert *row* (keyed by the ``RF_EVENTS_COLUMNS`` contract).

        Returns ``True`` when a new row was inserted, ``False`` when
        ``event_id`` already existed (idempotent no-op).
        """
        columns_sql = ", ".join(RF_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(RF_EVENTS_COLUMNS))
        cursor = await self.db.execute(
            f"INSERT OR IGNORE INTO rf_events ({columns_sql}) VALUES ({placeholders_sql})",
            _row_values(row),
        )
        await self.db.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


# ── PostgreSQL ──────────────────────────────────────────────────────────────


class PostgresRfEventsRepository:
    """asyncpg-backed writer for ``rf_events``."""

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    async def insert_if_not_exists(self, row: dict[str, Any]) -> bool:
        """Insert *row* (keyed by the ``RF_EVENTS_COLUMNS`` contract).

        Returns ``True`` when a new row was inserted, ``False`` when
        ``event_id`` already existed (idempotent no-op).
        """
        columns_sql = ", ".join(RF_EVENTS_COLUMNS)
        placeholders_sql = ", ".join(f"${i}" for i in range(1, len(RF_EVENTS_COLUMNS) + 1))
        status = await self.db.execute(
            f"INSERT INTO rf_events ({columns_sql}) VALUES ({placeholders_sql}) "
            "ON CONFLICT (event_id) DO NOTHING",
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
    "RF_EVENTS_COLUMNS",
    "SqliteRfEventsRepository",
    "PostgresRfEventsRepository",
]
