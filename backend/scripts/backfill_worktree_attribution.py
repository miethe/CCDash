#!/usr/bin/env python3
"""Reversibly move Codex worktree sessions off the two catch-all projects.

The default is a dry-run.  ``--apply`` writes an ``undo-<timestamp>.jsonl``
file before committing the re-attribution; ``--undo FILE`` restores exactly
the rows recorded in that file.  Neither mode deletes rows or project records.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

from backend.db.cwd_resolver import resolve_project_for_cwd


CATCH_ALL_PROJECT_IDS = ("ccp-61d5a4bb0de5", "ccp-3f61311bd972")
UNATTRIBUTED_PROJECT_ID = ""  # Existing CCDash convention; no project row is needed.


@dataclass(frozen=True)
class Change:
    session_id: str
    old_project_id: str
    new_project_id: str


@dataclass
class Totals:
    moved: int = 0
    ambiguous: int = 0
    skipped: int = 0


def is_worktree_cwd(cwd: str | None) -> bool:
    """Return whether *cwd* has one of the resolver's supported layouts."""
    if not cwd:
        return False
    parts = Path(cwd).parts
    return any(
        segment in {".codex", ".claude"}
        and parts[index + 1 : index + 2] == ("worktrees",)
        for index, segment in enumerate(parts)
    )


def plan_changes(rows: list[dict[str, Any]], projects: list[dict[str, Any]]) -> tuple[list[Change], Totals]:
    """Resolve candidate rows using the shared cwd resolver, without DB I/O."""
    changes: list[Change] = []
    totals = Totals()
    for row in rows:
        cwd = row.get("cwd")
        if not is_worktree_cwd(cwd):
            totals.skipped += 1
            continue
        target = resolve_project_for_cwd(str(cwd), projects)
        if target is None:
            # ``project_id=''`` is CCDash's established Unattributed bucket.
            target = UNATTRIBUTED_PROJECT_ID
            totals.ambiguous += 1
        if target == row["project_id"]:
            totals.skipped += 1
            continue
        changes.append(Change(str(row["id"]), str(row["project_id"]), target))
    totals.moved = len(changes)
    return changes, totals


async def fetch_plan(connection: Any) -> tuple[list[Change], Totals]:
    """Fetch catch-all Codex candidates and calculate the non-mutating plan."""
    projects = [dict(row) for row in await connection.fetch("SELECT id, repo_path FROM projects")]
    rows = [
        dict(row)
        for row in await connection.fetch(
            """
            SELECT id, project_id, cwd
            FROM sessions
            WHERE platform_type = 'Codex'
              AND project_id = ANY($1::text[])
              AND (cwd LIKE '%/.codex/worktrees/%' OR cwd LIKE '%/.claude/worktrees/%')
            """,
            list(CATCH_ALL_PROJECT_IDS),
        )
    ]
    return plan_changes(rows, projects)


async def apply_changes(connection: Any, changes: list[Change]) -> int:
    """Apply only planned moves that still have the expected old project id."""
    applied = 0
    for change in changes:
        result = await connection.execute(
            """
            UPDATE sessions
            SET project_id = $1
            WHERE id = $2 AND project_id = $3
              AND NOT EXISTS (
                SELECT 1 FROM sessions AS target
                WHERE target.id = $2 AND target.project_id = $1
              )
            """,
            change.new_project_id,
            change.session_id,
            change.old_project_id,
        )
        applied += int(result.rsplit(" ", 1)[-1])
    return applied


def write_undo_file(changes: list[Change], directory: Path = Path(".")) -> Path:
    """Write the exact inverse input before applying a transaction."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"undo-{timestamp}.jsonl"
    with path.open("x", encoding="utf-8") as handle:
        for change in changes:
            handle.write(json.dumps(change.__dict__, sort_keys=True) + "\n")
    return path


def read_undo_file(path: Path) -> list[Change]:
    """Read and validate an undo manifest produced by :func:`write_undo_file`."""
    changes: list[Change] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            changes.append(Change(str(row["session_id"]), str(row["old_project_id"]), str(row["new_project_id"])))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid undo row {line_number} in {path}") from exc
    return changes


async def undo_changes(connection: Any, changes: list[Change]) -> int:
    """Restore only rows still at each manifest's recorded new project id."""
    inverse = [Change(change.session_id, change.new_project_id, change.old_project_id) for change in changes]
    return await apply_changes(connection, inverse)


async def run(database_url: str, *, apply: bool, undo_file: Path | None) -> Totals:
    connection = await asyncpg.connect(database_url, timeout=10)
    try:
        async with connection.transaction():
            if undo_file is not None:
                restored = await undo_changes(connection, read_undo_file(undo_file))
                print(f"restored={restored}")
                return Totals(moved=restored)
            changes, totals = await fetch_plan(connection)
            print(f"moved={totals.moved} ambiguous={totals.ambiguous} skipped={totals.skipped}")
            if not apply:
                return totals
            undo_path = write_undo_file(changes)
            applied = await apply_changes(connection, changes)
            if applied != len(changes):
                raise RuntimeError(f"applied {applied} of {len(changes)} planned changes; rolling back")
            print(f"undo_file={undo_path} applied={applied}")
            return totals
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CCDASH_DATABASE_URL", ""))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write changes; default is dry-run.")
    mode.add_argument("--undo", type=Path, metavar="FILE", help="Restore a prior --apply manifest.")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or CCDASH_DATABASE_URL is required")
    asyncio.run(run(args.database_url, apply=args.apply, undo_file=args.undo))


if __name__ == "__main__":
    main()
