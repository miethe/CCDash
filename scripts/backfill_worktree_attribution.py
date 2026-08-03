#!/usr/bin/env python3
"""One-shot backfill of ``sessions.worktree_name`` + parent-repo re-attribution.

New sessions arrive with ``worktree_name`` stamped by the ingest hook (see
:mod:`backend.parsers.worktree_attribution`), but the ~19,148 rows already in
the DB predate that hook, so historical analytics remain misattributed until
we walk them once.

For every session whose ``source_file`` is under a Claude project dir carrying
a worktree marker, this script:

  1. Derives the worktree label from the enclosing project dir name (a pure
     string operation via :func:`worktree_name_for_source` — no filesystem
     probe, no dependence on ``cwd`` which is NULL for 82% of rows).
  2. Resolves the *parent* project id (the registered project whose sessions
     path is the parent-repo dir).
  3. If a parent project row exists, moves the session's ``project_id`` to that
     parent AND stamps ``worktree_name``. If no parent row exists, only
     stamps ``worktree_name`` — never orphans a row.

Correctness invariants (checked before AND after the write pass):

  * Row-count MUST NOT drop. This is the tripwire from the Phase 0 plan.
  * Every re-pointed row's new ``project_id`` MUST exist in the ``projects``
    table before the UPDATE runs. Rows with no resolvable parent are labeled
    but not moved.

Usage:

    python scripts/backfill_worktree_attribution.py \\
        --database-url postgres://ccdash:...@10.42.10.76:5440/ccdash \\
        [--apply]        # default: dry-run, prints a plan
        [--batch 500]    # commit every N rows (default 500)
        [--limit N]      # process at most N candidate rows (testing)

Idempotent: re-running is a no-op — ``COALESCE`` on the upsert never wipes a
prior label, and rows already on the parent id are skipped by the WHERE clause.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow ``python3 scripts/backfill_worktree_attribution.py`` to import
# ``backend.*`` without requiring a package install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.parsers.worktree_attribution import (  # noqa: E402
    parent_repo_dirname,
    worktree_name_for_source,
)


# ---------------------------------------------------------------------------
# Pure derivation (unit-tested; DB pass drives this over every candidate row)
# ---------------------------------------------------------------------------


def _stable_project_id(dirname: str) -> str:
    """Mirror of ``scripts/register_claude_projects.stable_project_id``.

    Kept literal (not imported) so this script keeps its stdlib-only stance
    and stays independent of the register script's import graph. If the hash
    scheme ever changes, both places must change together -- the parity is
    unit-tested via ``test_backfill_worktree_attribution``.
    """
    import hashlib

    return "ccp-" + hashlib.sha1(dirname.encode()).hexdigest()[:12]


def _encode_repo_path(abs_path: str) -> str:
    """Encode a real absolute repo path to its Claude project dirname.

    Applies Claude Code's own encoding: '/', '_' and '.' all collapse to '-'.
    Reused for both DB shapes (``source_file`` derived and ``cwd`` derived).
    """
    return "".join("-" + _encode_segment(part) for part in Path(abs_path).parts[1:])


def _encode_segment(name: str) -> str:
    import re

    return re.sub(r"[/_.]", "-", name)


def parent_project_id_for_row(source_file: str | None, cwd: str | None) -> str | None:
    """Return the stable project id of the PARENT repo for a session row.

    Two shapes, mirrored from :func:`worktree_name_for_source`:

    * ``source_file`` names a Claude project dir with a worktree marker --
      strip the marker to get the parent's project dirname, then hash it.
    * ``cwd`` is a filesystem worktree path (``…/repo/.claude/worktrees/x``,
      ``…/repo/.git/hermes-worktrees/x``, or ``~/.codex/worktrees/<hash>/x``).
      Take the segment BEFORE the worktree marker as the repo root and encode
      it the way Claude Code does.

    Returns None when neither shape produces a repo path -- e.g. a Codex
    session whose cwd was ``~/.codex/worktrees/<hash>/<repo>`` where the
    ``<repo>`` slot names a repo but we cannot recover its absolute path
    without a filesystem probe (kept out of this script deliberately).
    """
    # Shape 1: Claude project dir with worktree marker
    if source_file:
        parent_name = Path(source_file).parent.name
        parent_dir = parent_repo_dirname(parent_name)
        if parent_dir is not None:
            return _stable_project_id(parent_dir)

    # Shape 2: a real fs worktree path in cwd. Match on the same known layouts
    # as worktree_name_for_source; the ROOT is everything left of the container
    # (``.claude`` or ``.git``).
    if cwd:
        parts = Path(cwd).parts
        for i, seg in enumerate(parts):
            if seg in ("worktrees", "hermes-worktrees") and i > 0:
                container = parts[i - 1]
                if container == ".claude" and seg == "worktrees":
                    repo_root = str(Path(*parts[: i - 1]))
                    return _stable_project_id(_encode_repo_path(repo_root))
                if container == ".git" and seg == "hermes-worktrees":
                    repo_root = str(Path(*parts[: i - 1]))
                    return _stable_project_id(_encode_repo_path(repo_root))
                # .codex worktrees are keyed by hash/name, not to a specific
                # repo path we can resolve -- leave for label-only.
                return None
    return None


# ---------------------------------------------------------------------------
# DB pass
# ---------------------------------------------------------------------------


def _fetch_candidates(cur, limit: int | None):
    """Fetch every session that might belong to a worktree.

    Two shapes are candidates:
      * ``source_file`` names a Claude project dir with a worktree marker.
      * ``cwd`` is a filesystem worktree path (Codex sessions run under a
        git worktree). In the live DB this is where 100% of today's
        historical evidence sits -- source_file is a rewritten canonical id
        for those rows, not the raw jsonl path.

    Returns rows as (id, project_id, source_file, cwd, worktree_name). The
    planner decides which shape actually matched for each row.
    """
    sql = """
        SELECT id, project_id, source_file, cwd, worktree_name
        FROM sessions
        WHERE source_file LIKE '%--claude-worktrees-%'
           OR source_file LIKE '%--git-hermes-worktrees-%'
           OR cwd LIKE '%/.claude/worktrees/%'
           OR cwd LIKE '%/.git/hermes-worktrees/%'
           OR cwd LIKE '%/.codex/worktrees/%'
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


def _known_project_ids(cur) -> set[str]:
    cur.execute("SELECT id FROM projects")
    return {row[0] for row in cur.fetchall()}


def plan(rows, known_project_ids: set[str]) -> dict:
    """Turn candidate rows into a change plan. Pure: no DB, no I/O.

    Each row is (session_id, project_id, source_file, cwd, worktree_name).
    Derivation prefers ``source_file`` shape 1 (Claude project dir marker) but
    falls back to ``cwd`` shape 2 for rows that lack it -- which today is 100%
    of the DB's worktree evidence.
    """
    label_only: list[tuple[str, str, str]] = []           # (session_id, project_id, label)
    move_and_label: list[tuple[str, str, str, str]] = []  # + parent_id
    skip_already_done: list[str] = []
    skip_no_label: list[str] = []

    for session_id, project_id, source_file, cwd, worktree_name in rows:
        # Try source_file (Claude-shape) first, then cwd (Codex/fs shape).
        label = worktree_name_for_source(source_file) or worktree_name_for_source(cwd)
        if not label:
            skip_no_label.append(session_id)
            continue
        parent_id = parent_project_id_for_row(source_file, cwd)
        parent_is_registered = bool(parent_id) and parent_id in known_project_ids

        already_labeled = (worktree_name == label)
        already_on_parent = parent_is_registered and (project_id == parent_id)
        if already_labeled and already_on_parent:
            skip_already_done.append(session_id)
            continue

        if parent_is_registered and parent_id != project_id:
            move_and_label.append((session_id, project_id, label, parent_id))  # type: ignore[arg-type]
        else:
            label_only.append((session_id, project_id, label))

    return {
        "move_and_label": move_and_label,
        "label_only": label_only,
        "skip_already_done": skip_already_done,
        "skip_no_label": skip_no_label,
    }


def _apply(cur, changes: dict, batch: int) -> None:
    """Execute the change plan against the cursor. Batches per ``batch`` rows.

    The invariant checked here: an UPDATE that would change project_id must
    target an EXISTING project row -- we pre-filtered in :func:`plan`, so this
    is a belt-and-braces assertion via a WHERE EXISTS guard on the SQL side.
    """
    move_sql = """
        UPDATE sessions SET
            project_id = %s,
            worktree_name = COALESCE(worktree_name, %s)
        WHERE id = %s
          AND project_id = %s
          AND EXISTS (SELECT 1 FROM projects WHERE id = %s)
    """
    label_sql = """
        UPDATE sessions SET
            worktree_name = COALESCE(worktree_name, %s)
        WHERE id = %s
          AND project_id = %s
    """

    def _flush(items, sql, extract):
        if not items:
            return
        cur.executemany(sql, [extract(x) for x in items])

    for start in range(0, len(changes["move_and_label"]), batch):
        chunk = changes["move_and_label"][start:start + batch]
        _flush(chunk, move_sql, lambda x: (x[3], x[2], x[0], x[1], x[3]))
    for start in range(0, len(changes["label_only"]), batch):
        chunk = changes["label_only"][start:start + batch]
        _flush(chunk, label_sql, lambda x: (x[2], x[0], x[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--database-url", default=os.environ.get("CCDASH_DATABASE_URL"),
                    help="Postgres DSN. Defaults to $CCDASH_DATABASE_URL.")
    ap.add_argument("--apply", action="store_true",
                    help="Commit changes. Default is dry-run (prints the plan).")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap candidates to N rows (testing).")
    args = ap.parse_args()

    if not args.database_url:
        print("ERROR: no --database-url and CCDASH_DATABASE_URL is unset", file=sys.stderr)
        return 2

    try:
        import psycopg  # type: ignore
    except ImportError:
        print("ERROR: psycopg (v3) is required. `uv pip install psycopg[binary]`.",
              file=sys.stderr)
        return 2

    with psycopg.connect(args.database_url) as conn:
        cur = conn.cursor()

        # Precondition: the v46 migration must have run. If sessions.worktree_name
        # is missing, we would fail on the very first SELECT below with an
        # UndefinedColumn traceback -- surface a legible error instead.
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='sessions' "
            "AND column_name='worktree_name'"
        )
        if cur.fetchone() is None:
            print(
                "ERROR: sessions.worktree_name is missing. Run the API startup "
                "migration to v46 (or `_ensure_column`) before this backfill.",
                file=sys.stderr,
            )
            return 2

        cur.execute("SELECT COUNT(*) FROM sessions")
        row = cur.fetchone()
        assert row is not None  # count(*) always returns one row
        pre_total = int(row[0])
        print(f"pre-check: sessions total = {pre_total}")

        rows = _fetch_candidates(cur, args.limit)
        known = _known_project_ids(cur)
        changes = plan(rows, known)

        print(
            f"candidates: {len(rows)} | "
            f"move_and_label: {len(changes['move_and_label'])} | "
            f"label_only: {len(changes['label_only'])} | "
            f"skip_already_done: {len(changes['skip_already_done'])} | "
            f"skip_no_label: {len(changes['skip_no_label'])}"
        )

        if not args.apply:
            print("dry-run: no changes committed. Re-run with --apply to commit.")
            for row in changes["move_and_label"][:5]:
                sid, old_pid, label, new_pid = row
                print(f"  MOVE  {sid}  {old_pid} -> {new_pid}  wt={label!r}")
            for row in changes["label_only"][:5]:
                sid, pid, label = row
                print(f"  LABEL {sid}  {pid}  wt={label!r}")
            return 0

        _apply(cur, changes, args.batch)

        # Post-write invariant: row count must not drop.
        cur.execute("SELECT COUNT(*) FROM sessions")
        row = cur.fetchone()
        assert row is not None
        post_total = int(row[0])
        if post_total < pre_total:
            conn.rollback()
            print(
                f"ABORT: sessions total dropped from {pre_total} to {post_total}. "
                "Rolled back.", file=sys.stderr,
            )
            return 1

        conn.commit()
        print(f"post-check: sessions total = {post_total} (delta = {post_total - pre_total})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
