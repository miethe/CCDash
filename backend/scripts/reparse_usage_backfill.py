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

This script re-parses each already-ingested session with the now-fixed parser
and re-upserts the row. The upsert is the SAME one every ingest path uses
(``ON CONFLICT(project_id, id) DO UPDATE`` — see
``backend/db/repositories/{sessions.py,postgres/sessions.py}``), so a session
whose totals were already correct (ingested after the fix, or never affected)
is an idempotent no-op.

IMPORTANT — the stored ``source_file`` column is NOT a reparseable filesystem
path for most rows (verified live 2026-09-05): the local filesystem-ingestion
worker (``backend/worker.py``, run from a laptop against the node's Postgres
over the network — see ``deploy/local-streaming/``) writes a synthetic
``ccdash-source:v1/<project>/session/opaque/<hash>`` identifier via
``compute_source_ref``, not the real path; only the ~116 rows the node-local
``ccdash-cli daemon`` (packages/ccdash_cli) ingests directly carry a blank
``source_file``. Trusting ``source_file`` as a path would report ~99.6% of
rows "unreachable" and re-parse nothing. Instead this script resolves each
candidate's real file by REGISTRY, not by the stored column:

  1. Read the project's ``sessions_path`` from the ``projects`` table.
  2. Expand it through ``session_scan_roots`` (the SAME worktree-fan-out
     helper CCDash's own scan path uses — ``backend/services/project_paths/
     worktree_fanout.py``) so a session under a git-worktree sibling
     directory is found too.
  3. ``rglob`` each root for ``<session_id with its leading 'S-' stripped>.jsonl``
     (Claude Code writes the file as ``<uuid>.jsonl`` / ``agent-<hash>.jsonl``;
     CCDash's own session id is that stem with an ``S-`` prefix prepended).

This only finds sessions whose source file still exists on THE MACHINE this
script runs on — run it on the machine that machine's project sessions
actually live on (this laptop for `/Users/miethe/...` projects; the node
itself for the ``ccp-e9ae9bcf8f6b`` node-local project). A session whose
source file has since been rotated/deleted is correctly reported unreachable,
not guessed at.

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

Run wherever the project's session files actually live and set
``CCDASH_DATABASE_URL``/``CCDASH_DB_BACKEND=postgres`` to reach the node's
Postgres directly (same pattern as ``deploy/local-streaming``'s
``stream.env``), e.g. from this laptop:

    CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash \\
    CCDASH_DB_BACKEND=postgres \\
    python -m backend.scripts.reparse_usage_backfill --since-days 7 --apply

Or from inside the node's api container, for the node-local project only
(same route as ``ccdash token mint`` — see token_provisioning.py's module
docstring for the three ways to reach the CLI):

    podman exec -it ccdash_api_1 python -m backend.scripts.reparse_usage_backfill --project ccp-e9ae9bcf8f6b --apply
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
from backend.services.project_paths.worktree_fanout import session_scan_roots

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
    """Return [{id, project_id, workspace_id, usage fields...}].

    Deliberately does NOT filter on ``source_file`` — see module docstring
    for why that column is not a reliable "this row has a reparseable
    source" signal. Every row in scope is a candidate; local-path resolution
    (``_resolve_local_path``) is what actually decides reachability.
    """
    cutoff_iso: str | None = None
    if since_days is not None:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    cols = "id, project_id, workspace_id, " + ", ".join(_USAGE_FIELDS)
    where: list[str] = []
    params: list[Any] = []

    if _is_sqlite(db):
        if project_id:
            params.append(project_id)
            where.append("project_id = ?")
        if cutoff_iso:
            params.append(cutoff_iso)
            where.append("COALESCE(NULLIF(updated_at, ''), created_at) >= ?")
        sql = f"SELECT {cols} FROM sessions"
        if where:
            sql += f" WHERE {' AND '.join(where)}"
        sql += " ORDER BY id"
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
    sql = f"SELECT {cols} FROM sessions"
    if where:
        sql += f" WHERE {' AND '.join(where)}"
    sql += " ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = await db.fetch(sql, *params)
    return [dict(r) for r in rows]


async def _project_sessions_paths(db: Any) -> dict[str, Path]:
    """Return {project_id: sessions_path} for every project with a non-blank one."""
    if _is_sqlite(db):
        async with db.execute(
            "SELECT id, sessions_path FROM projects WHERE sessions_path IS NOT NULL AND sessions_path != ''"
        ) as cur:
            rows = await cur.fetchall()
        return {r[0]: Path(r[1]) for r in rows}

    rows = await db.fetch(
        "SELECT id, sessions_path FROM projects WHERE sessions_path IS NOT NULL AND sessions_path != ''"
    )
    return {r["id"]: Path(r["sessions_path"]) for r in rows}


class _LocalResolver:
    """Resolves a session_id to a local file path via the project registry.

    Caches each project's expanded scan roots (``session_scan_roots`` —
    sessions_path itself plus any git-worktree sibling directories) so an
    N-session backfill costs one filesystem listing per PROJECT, not one per
    session.
    """

    def __init__(self, project_paths: dict[str, Path]) -> None:
        self._project_paths = project_paths
        self._roots_cache: dict[str, list[Path]] = {}

    def resolve(self, session_id: str, project_id: str) -> Path | None:
        base = self._project_paths.get(project_id)
        if base is None:
            return None

        roots = self._roots_cache.get(project_id)
        if roots is None:
            roots = session_scan_roots(base)
            self._roots_cache[project_id] = roots

        stem = session_id[2:] if session_id.startswith("S-") else session_id
        target = f"{stem}.jsonl"
        for root in roots:
            try:
                for candidate in root.rglob(target):
                    return candidate
            except OSError:
                continue
        return None


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
        project_paths = await _project_sessions_paths(db)
        resolver = _LocalResolver(project_paths)
        _LOG.info(
            "reparse_usage_backfill: %d session row(s) in scope "
            "(project=%s, since_days=%s, limit=%s, %d project(s) with a resolvable sessions_path)",
            len(candidates),
            project_id or "ALL",
            since_days if since_days is not None else "ALL",
            limit if limit is not None else "none",
            len(project_paths),
        )

        changed = 0
        unchanged = 0
        unreachable = 0
        parse_failed = 0
        shown = 0

        for row in candidates:
            path = resolver.resolve(row["id"], row["project_id"])
            if path is None or not path.exists():
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

            # Guard (node_01M1S9RR6X6KWV7TB1T7T50W02): the parser never wires
            # cacheCreationInputTokens/cacheReadInputTokens to the top-level
            # AgentSession fields (they're only tracked in a diagnostic
            # sidecar), so a fresh parse ALWAYS reports 0 for both —
            # regardless of what the file actually contains. Never let that
            # 0 overwrite an existing nonzero DB value: that would replace a
            # wrong-but-nonzero number with a confidently-wrong zero, which
            # is worse for a viewer than today's inflation. Re-parsing IS
            # still correct and safe for tokens_in/tokens_out (verified: PR
            # #79 wires those to real accumulators), so only the two cache
            # columns get this floor.
            for cache_field in ("cache_creation_input_tokens", "cache_read_input_tokens"):
                if after[cache_field] == 0 and (before.get(cache_field) or 0) != 0:
                    payload_key = "cacheCreationInputTokens" if cache_field == "cache_creation_input_tokens" else "cacheReadInputTokens"
                    payload[payload_key] = before[cache_field]
                    after[cache_field] = before[cache_field]

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
