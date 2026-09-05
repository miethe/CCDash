#!/usr/bin/env python3
"""Re-parse already-ingested sessions to clear pre-PR#79 inflated usage totals.

Root cause and fix background (node_01M1S7WQETVF7Q7APB6FYB44HQ, parent
node_01M1S6DSTN0P841PF5P8YNC03H): PR miethe/CCDash#79 (commit 4da7f2d) gated
every usage-aggregate counter in the Claude Code parser behind first-seen
non-blank ``message.id``, fixing a systematic over-count (Claude Code writes
one JSONL line per content block for a multi-block assistant turn, each
carrying the identical cumulative ``message.usage`` — the old parser summed
every line). The fix is PARSE-TIME ONLY: a session row already written to the
``sessions`` table by the old parser keeps its inflated totals until the row
is re-derived from its source JSONL and re-written.

This script re-parses each already-ingested session (identified by its stored
``source_file`` path) with the now-fixed parser and re-upserts the row. The
upsert is the SAME one every ingest path uses
(``ON CONFLICT(project_id, id) DO UPDATE`` — see
``backend/db/repositories/{sessions.py,postgres/sessions.py}``), so a session
whose totals were already correct (ingested after the fix, or never affected)
is an idempotent no-op.

Deliberately mirrors ``backend/application/services/auth/token_provisioning.py``'s
safety posture (see that module's docstring): this script NEVER runs
migrations. It probes the sessions table's readability and aborts with a
clear message if the schema is not there, rather than assuming and repairing.

Usage
-----
    # Dry run (default): report counts + a sample of before/after totals,
    # write nothing.
    python -m backend.scripts.reparse_usage_backfill

    # Scope to the last N days by the row's stored updated_at (falls back to
    # created_at when updated_at is blank). Use this for a bounded first pass.
    python -m backend.scripts.reparse_usage_backfill --since-days 7

    # Actually write the corrected totals.
    python -m backend.scripts.reparse_usage_backfill --since-days 7 --apply

    # Scope to one project.
    python -m backend.scripts.reparse_usage_backfill --project ccp-e9ae9bcf8f6b --apply

Run from inside the api container (same route as ``ccdash token mint`` — see
token_provisioning.py's module docstring for the three ways to reach the CLI,
and why ``python -m backend.cli.main`` requires the ``__main__`` guard):

    podman exec -it ccdash_api_1 python -m backend.scripts.reparse_usage_backfill --since-days 7 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend import config
from backend.db import connection
from backend.db.factory import get_session_repository
from backend.parsers.sessions import parse_session_file

logging.basicConfig(level=logging.INFO, format="%(message)s")
_LOG = logging.getLogger("reparse_usage_backfill")

_USAGE_FIELDS = (
    "tokens_in",
    "tokens_out",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


class SchemaNotReadyError(RuntimeError):
    """Raised when the sessions table is absent or unreadable. Never repaired here."""


def _is_sqlite(db: Any) -> bool:
    return isinstance(db, aiosqlite.Connection)


async def _assert_schema_ready(db: Any) -> None:
    probe = "SELECT 1 FROM sessions LIMIT 1"
    try:
        if _is_sqlite(db):
            async with db.execute(probe) as cur:
                await cur.fetchone()
        else:
            await db.fetch(probe)
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see token_provisioning.py.
        raise SchemaNotReadyError(
            f"sessions table is not readable ({type(exc).__name__}: {exc}). "
            "Refusing to proceed — this script never runs migrations."
        ) from exc


async def _fetch_candidates(
    db: Any,
    *,
    project_id: str | None,
    since_days: int | None,
    limit: int | None,
) -> list[dict]:
    """Return [{id, project_id, workspace_id, source_file, usage fields...}]."""
    cutoff_iso: str | None = None
    if since_days is not None:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    cols = "id, project_id, workspace_id, source_file, " + ", ".join(_USAGE_FIELDS)
    where = ["source_file IS NOT NULL", "source_file != ''"]
    params: list[Any] = []

    if _is_sqlite(db):
        if project_id:
            params.append(project_id)
            where.append("project_id = ?")
        if cutoff_iso:
            params.append(cutoff_iso)
            where.append("COALESCE(NULLIF(updated_at, ''), created_at) >= ?")
        sql = f"SELECT {cols} FROM sessions WHERE {' AND '.join(where)} ORDER BY id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            col_names = [d[0] for d in cur.description]
        return [dict(zip(col_names, r)) for r in rows]

    # Postgres.
    idx = 1
    if project_id:
        where.append(f"project_id = ${idx}")
        params.append(project_id)
        idx += 1
    if cutoff_iso:
        where.append(f"COALESCE(NULLIF(updated_at, ''), created_at) >= ${idx}")
        params.append(cutoff_iso)
        idx += 1
    sql = f"SELECT {cols} FROM sessions WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = await db.fetch(sql, *params)
    return [dict(r) for r in rows]


async def _run(
    *,
    project_id: str | None,
    since_days: int | None,
    limit: int | None,
    apply: bool,
    sample: int,
) -> int:
    db = await connection.get_connection()
    try:
        await _assert_schema_ready(db)
        repo = get_session_repository(db)

        candidates = await _fetch_candidates(
            db, project_id=project_id, since_days=since_days, limit=limit
        )
        _LOG.info(
            "reparse_usage_backfill: %d session row(s) with a stored source_file "
            "(project=%s, since_days=%s, limit=%s)",
            len(candidates),
            project_id or "ALL",
            since_days if since_days is not None else "ALL",
            limit if limit is not None else "none",
        )

        changed = 0
        unchanged = 0
        unreachable = 0
        parse_failed = 0
        shown = 0

        for row in candidates:
            path = Path(str(row["source_file"]))
            if not path.exists():
                unreachable += 1
                continue

            try:
                session = await asyncio.to_thread(parse_session_file, path)
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the run.
                _LOG.warning("parse failed for %s (%s): %s", row["id"], path, exc)
                parse_failed += 1
                continue

            if session is None:
                parse_failed += 1
                continue

            payload = session.model_dump()
            before = {f: row.get(f) for f in _USAGE_FIELDS}
            after = {
                "tokens_in": payload.get("tokensIn", 0),
                "tokens_out": payload.get("tokensOut", 0),
                "cache_creation_input_tokens": payload.get("cacheCreationInputTokens", 0),
                "cache_read_input_tokens": payload.get("cacheReadInputTokens", 0),
            }

            if before == after:
                unchanged += 1
                continue

            changed += 1
            if shown < sample:
                _LOG.info(
                    "%s  before=%s  after=%s", row["id"], before, after
                )
                shown += 1

            if apply:
                await repo.upsert(
                    payload,
                    row["project_id"],
                    workspace_id=row["workspace_id"],
                    source_ref=None,  # COALESCE-preserved by the upsert (capture-once).
                )

        _LOG.info(
            "reparse_usage_backfill: changed=%d unchanged=%d unreachable_source=%d "
            "parse_failed=%d  mode=%s",
            changed,
            unchanged,
            unreachable,
            parse_failed,
            "APPLIED" if apply else "DRY-RUN (pass --apply to write)",
        )
        return 0
    finally:
        await connection.close_connection()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=None, help="Scope to one project_id.")
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only rows touched in the last N days (default: all rows).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of rows scanned.")
    parser.add_argument("--apply", action="store_true", help="Write corrected totals (default: dry-run).")
    parser.add_argument("--sample", type=int, default=5, help="How many before/after diffs to log.")
    args = parser.parse_args()

    try:
        return asyncio.run(
            _run(
                project_id=args.project,
                since_days=args.since_days,
                limit=args.limit,
                apply=args.apply,
                sample=args.sample,
            )
        )
    except SchemaNotReadyError as exc:
        _LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
