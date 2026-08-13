"""Transport-neutral ingest-source health rollup (Phase 6 / Deliverable A).

Reads all ``ingest_cursors`` rows and returns a per-source status list.
Designed as a pure read path — no writes, no side effects.

State derivation
----------------
Each row is classified by lag = now - last_ingest_at (seconds):

  ``idle``          — last_ingest_at is NULL (source registered but never ingested)
  ``connected``     — lag < CCDASH_INGEST_SOURCE_FRESH_SECONDS (default 300)
  ``backed_up``     — FRESH_SECONDS <= lag < CCDASH_INGEST_SOURCE_STALE_SECONDS (default 900)
  ``disconnected``  — lag >= CCDASH_INGEST_SOURCE_STALE_SECONDS

Resilience
----------
- Missing ``ingest_cursors`` table (pre-v36 DB) → returns ``[]``.
- Empty table → returns ``[]``.
- Any per-row parse error → row is skipped with a warning.
- Any DB error → returns ``[]`` (never raises).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend import config

logger = logging.getLogger("ccdash.agent_queries.ingest_sources")

# ── SQL ───────────────────────────────────────────────────────────────────────

_SQLITE_SELECT_ALL = """
    SELECT source_id, project_id, workspace_id, last_cursor, last_ingest_at
    FROM ingest_cursors
"""  # noqa: S608

_PG_SELECT_ALL = """
    SELECT source_id, project_id, workspace_id, last_cursor, last_ingest_at
    FROM ingest_cursors
"""  # noqa: S608

# ── Helpers ───────────────────────────────────────────────────────────────────


def parse_iso(raw: Any) -> datetime | None:
    """Parse a stored ``last_ingest_at`` value to a UTC datetime.

    The production writer (``backend/db/repositories/ingest_cursors.py``) is
    ``datetime.now(timezone.utc).isoformat()``, which produces an
    OFFSET-BEARING ISO-8601 string (e.g. ``2026-08-13T19:07:18.250600+00:00``).
    That is the canonical production form. A handful of legacy naive-form
    values (no offset, produced before that writer existed) may still be
    present in an older DB, so both forms are accepted.

    Accepts:
      - A ``datetime`` instance directly (defensive: the column is TEXT
        today, but a driver returning a real datetime must not silently
        become "idle").
      - Any ISO-8601 string ``datetime.fromisoformat`` understands on
        Python 3.12+ — offset-bearing, trailing ``Z``, space-separated,
        variable-width fractional seconds.
      - The four legacy naive ``strptime`` formats, as a fallback, for
        values already stored before the writer emitted offsets.

    The result is always normalized to UTC: a naive result is treated as
    already-UTC (``tzinfo=timezone.utc``); an aware result is converted via
    ``astimezone(timezone.utc)``.

    Returns ``None`` when *raw* is None/empty or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)

    raw_str = str(raw).strip()
    if not raw_str:
        return None

    # Try the production (offset-bearing) form first. Do NOT strip a
    # trailing "Z" before this attempt — fromisoformat() parses "Z" natively
    # on Python 3.12+, and rstrip("Z") is also wrong in principle (it would
    # strip a run of trailing "Z" characters, not one suffix).
    try:
        parsed = datetime.fromisoformat(raw_str)
    except ValueError:
        parsed = None

    if parsed is None:
        # Fall back to the legacy naive strptime formats for values stored
        # before the production writer emitted UTC offsets.
        legacy_str = raw_str.rstrip("Z")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(legacy_str, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        logger.debug("ingest_sources: unparseable last_ingest_at %r", raw_str)
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# Backward-compatible alias — the function was renamed from a private name
# (`_parse_iso`) to a public one (`parse_iso`) so `backend/runtime/bootstrap.py`
# can import it without reaching into a private module member. Existing
# internal call sites in this module keep using the private alias.
_parse_iso = parse_iso


def derive_state(lag_seconds: float | None) -> str:
    """Map a lag in seconds to a source state string."""
    if lag_seconds is None:
        return "idle"
    fresh = float(config.CCDASH_INGEST_SOURCE_FRESH_SECONDS)
    stale = float(config.CCDASH_INGEST_SOURCE_STALE_SECONDS)
    if lag_seconds < fresh:
        return "connected"
    if lag_seconds < stale:
        return "backed_up"
    return "disconnected"


# Backward-compatible alias (see `parse_iso` above for rationale).
_derive_state = derive_state


def _row_to_status(row: Any) -> dict[str, Any] | None:
    """Convert a DB row (aiosqlite.Row or asyncpg Record) to a status dict.

    Returns ``None`` on parse error (caller skips the row).
    """
    try:
        # Support both aiosqlite.Row (index / key access) and asyncpg Record
        if isinstance(row, (list, tuple)):
            source_id, project_id, workspace_id, last_cursor, last_ingest_at_raw = row
        else:
            source_id = row["source_id"]
            project_id = row["project_id"]
            workspace_id = row["workspace_id"]
            last_cursor = row["last_cursor"]
            last_ingest_at_raw = row["last_ingest_at"]

        last_ingest_dt = _parse_iso(last_ingest_at_raw)

        if last_ingest_dt is not None:
            lag_seconds: float | None = (
                datetime.now(timezone.utc) - last_ingest_dt
            ).total_seconds()
        else:
            lag_seconds = None

        state = _derive_state(lag_seconds)

        return {
            "source_id": str(source_id),
            "project_id": str(project_id),
            "workspace_id": str(workspace_id),
            "last_cursor": last_cursor,
            "last_ingest_at": last_ingest_at_raw,
            "lag_seconds": round(lag_seconds, 3) if lag_seconds is not None else None,
            "state": state,
        }
    except Exception:  # noqa: BLE001
        logger.warning(
            "ingest_sources: failed to parse row %r",
            row,
            exc_info=True,
        )
        return None


# ── Public query function ─────────────────────────────────────────────────────


async def get_ingest_sources_health(db: Any) -> list[dict[str, Any]]:
    """Return per-source ingest health status from ``ingest_cursors``.

    Parameters
    ----------
    db:
        The shared async DB connection — either an ``aiosqlite.Connection``
        or an asyncpg ``Pool``/``Connection``.

    Returns
    -------
    List of status dicts (one per row in ``ingest_cursors``).  Returns ``[]``
    when the table is missing, empty, or any DB error occurs.  Never raises.
    """
    try:
        if isinstance(db, aiosqlite.Connection):
            rows = await _fetch_sqlite(db)
        else:
            rows = await _fetch_pg(db)

        results: list[dict[str, Any]] = []
        for row in rows:
            status = _row_to_status(row)
            if status is not None:
                results.append(status)
        return results

    except Exception:  # noqa: BLE001
        logger.warning(
            "ingest_sources: failed to query ingest_cursors; returning []",
            exc_info=True,
        )
        return []


async def _fetch_sqlite(db: aiosqlite.Connection) -> list[Any]:
    """SELECT all rows from ingest_cursors via aiosqlite."""
    try:
        async with db.execute(_SQLITE_SELECT_ALL) as cur:
            return list(await cur.fetchall())
    except Exception as exc:  # noqa: BLE001
        # Table absent (pre-v36) or other SQL error — treat as empty
        logger.debug(
            "ingest_sources: SQLite query failed (%s); returning empty list", exc
        )
        return []


async def _fetch_pg(db: Any) -> list[Any]:
    """SELECT all rows from ingest_cursors via asyncpg."""
    try:
        return list(await db.fetch(_PG_SELECT_ALL))
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "ingest_sources: PG query failed (%s); returning empty list", exc
        )
        return []
