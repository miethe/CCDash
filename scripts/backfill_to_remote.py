#!/usr/bin/env python3
"""Backfill registered CCDash projects into the configured DB.

Drives the same SyncEngine.sync_project path the worker uses over every
registered project.  Intended use: backfill local Mac ~/.claude/projects
sessions into a remote Postgres node.  DB backend + DSN come from env
(CCDASH_DB_BACKEND / CCDASH_DATABASE_URL) — nothing is hardcoded here.

Usage (repo root, backend venv active):
    backend/.venv/bin/python scripts/backfill_to_remote.py [OPTIONS]
    backend/.venv/bin/python -m scripts.backfill_to_remote [OPTIONS]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.db import connection, migrations          # noqa: E402
from backend.db.sync_engine import SyncEngine          # noqa: E402
from backend.runtime_ports import build_workspace_registry  # noqa: E402

_DEFAULT_EXCLUDE_NAME = "default-skillmeat"
_CHILD_TABLES = (
    "session_messages",
    "session_tool_usage",
    "session_usage_events",
    "session_usage_attributions",
)


async def _fetchval(db: object, sql: str, *args: object) -> int:
    """COUNT query — handles SQLite (aiosqlite) or Postgres (asyncpg Pool).

    SQLite: $N markers are rewritten to ?.  asyncpg Pool: pool-level fetchrow
    (acquire is implicit).
    """
    try:
        import aiosqlite as _sl
        if isinstance(db, _sl.Connection):
            async with db.execute(re.sub(r"\$\d+", "?", sql), args) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
    except ImportError:
        pass
    row = await db.fetchrow(sql, *args)  # type: ignore[union-attr]
    return int(row[0]) if row else 0


async def _session_count(db: object, project_id: str) -> int:
    """Count sessions rows for a single project_id."""
    return await _fetchval(
        db,
        "SELECT COUNT(*) FROM sessions WHERE project_id=$1",
        project_id,
    )


async def run_backfill(
    *,
    only: list[str],
    exclude_default: bool,
    limit_projects: int | None,
    quiet: bool,
) -> int:
    """Bootstrap DB, sync selected projects, report integrity.  Returns 0/1."""
    # Lightweight bootstrap: mirrors container.py:112-139 without starting the
    # full worker runtime (no uvicorn probe, no job scheduler, no binding req).
    db = await connection.get_connection()
    await migrations.run_migrations(db)
    sync_engine = SyncEngine(db)

    # build_workspace_registry() returns a ProjectManagerWorkspaceRegistry backed
    # by db_project_manager (ADR-006 — registry/runtime_ports.py:133-147).
    registry = build_workspace_registry()
    all_projects = sorted(registry.list_projects(), key=lambda p: p.name)

    # Apply filters.
    selected = [
        p for p in all_projects
        if not (exclude_default and p.name == _DEFAULT_EXCLUDE_NAME)
        and (not only or any(s in p.id or s in p.name for s in only))
    ]
    if limit_projects is not None:
        selected = selected[:limit_projects]

    if not quiet:
        print(f"Backfilling {len(selected)} of {len(all_projects)} registered project(s)\n")

    failed: list[str] = []

    for project in selected:
        # ProjectBinding.paths.as_tuple() → (sessions_dir, docs_dir, progress_dir)
        # (services/project_paths/models.py:26)
        binding = registry.resolve_project_binding(project.id, allow_active_fallback=False)
        if binding is None:
            print(f"{project.id} | {project.name} | SKIPPED: binding could not be resolved")
            failed.append(project.id)
            continue

        sessions_dir, docs_dir, progress_dir = binding.paths.as_tuple()
        before = await _session_count(db, project.id)
        err: str | None = None

        try:
            # sync_project(project, sessions_dir, docs_dir, progress_dir,
            #   force=False, trigger="api", *, allow_writeback=True, ...)
            # db/sync_engine.py:3090
            await sync_engine.sync_project(
                project,
                sessions_dir,
                docs_dir,
                progress_dir,
                trigger="backfill",
                allow_writeback=True,
            )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            failed.append(project.id)
            if os.getenv("CCDASH_BACKFILL_TRACEBACK"):
                import traceback as _tb
                print(f"\n=== TRACEBACK for {project.id} ({project.name}) ===")
                _tb.print_exc()
                print("=== END TRACEBACK ===\n")

        after = await _session_count(db, project.id)
        status = f"FAILED: {err}" if err else "ok"
        if not quiet or err:
            print(
                f"{project.id} | {project.name} | "
                f"{before} -> {after} (Δ{after - before:+d}) | {status}"
            )

    # --- Integrity report ---
    print("\n--- Integrity ---")
    total = await _fetchval(db, "SELECT COUNT(*) FROM sessions")
    print(f"sessions total: {total}")

    for p in selected:
        n = await _session_count(db, p.id)
        print(f"  {p.id} ({p.name}): {n}")

    orphan_total = 0
    for table in _CHILD_TABLES:
        try:
            n = await _fetchval(
                db,
                f"SELECT COUNT(*) FROM {table} "
                "WHERE session_id NOT IN (SELECT id FROM sessions)",
            )
            print(f"FK orphans in {table}: {n}")
            orphan_total += n
        except Exception as exc:
            print(f"FK orphans in {table}: (table absent — {type(exc).__name__}: {exc})")

    await connection.close_connection()

    code = 0
    if failed:
        code = 1
        print(f"\nFAILED projects: {', '.join(failed)}")
    if orphan_total > 0:
        code = 1
        print(f"\nFK orphan violations: {orphan_total} total")
    return code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill registered CCDash projects into the configured DB.",
    )
    parser.add_argument(
        "--only", action="append", default=[], metavar="SUBSTR",
        help="Keep only projects whose id or name contains SUBSTR (repeatable).",
    )
    parser.add_argument(
        "--exclude-default", action="store_true", default=True, dest="exclude_default",
        help="Skip the default-skillmeat project (default: on).",
    )
    parser.add_argument(
        "--include-default", action="store_false", dest="exclude_default",
        help="Include the default-skillmeat project.",
    )
    parser.add_argument(
        "--limit-projects", type=int, default=None, metavar="N",
        help="Process at most N projects (sorted by name, after filter).",
    )
    parser.add_argument(
        "--quiet", action="store_true", default=False,
        help="Suppress per-project output except failures.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_backfill(
        only=args.only,
        exclude_default=args.exclude_default,
        limit_projects=args.limit_projects,
        quiet=args.quiet,
    )))


if __name__ == "__main__":
    main()
