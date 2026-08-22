"""Discovery of sibling git-worktree session directories.

Claude Code slugifies a session's **cwd**, not the repo root. A session
launched from ``<repo>/.claude/worktrees/<name>`` is written to a SIBLING
top-level Claude project dir, not into the registered project's
``sessions_dir``:

    ~/.claude/projects/-Users-miethe-dev-repo/                         <- registered sessions_dir
    ~/.claude/projects/-Users-miethe-dev-repo--claude-worktrees-foo/   <- sibling, never scanned

``ResolvedProjectPaths`` computes exactly ONE literal ``sessions_dir`` per
project, so nothing recurses into these siblings today. This module supplies
the filesystem enumeration needed to fan a scan out across them, reusing the
pure marker/parsing primitives in ``backend.parsers.worktree_attribution``
rather than re-deriving the marker logic here.

``worktree_attribution.py`` is deliberately pure (no I/O) so the ingest hook,
the backfill script, and their tests all share identical marker semantics
without touching the filesystem. The actual directory enumeration has to live
somewhere, and it belongs here, next to the other project-path resolution
code -- not in the pure module.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from backend.parsers.worktree_attribution import split_worktree_dirname

logger = logging.getLogger(__name__)


def sibling_worktree_session_dirs(sessions_dir: Path) -> list[Path]:
    """Sibling Claude project dirs that are git worktrees of ``sessions_dir``.

    A sibling is included iff its dirname carries a worktree marker
    (``--claude-worktrees-`` / ``--git-hermes-worktrees-``) whose PARENT
    portion equals ``sessions_dir.name`` exactly.

    This is deliberately MARKER-BASED, not prefix-based. Matching by
    ``name.startswith(sessions_dir.name)`` would silently fold a genuinely
    different repo whose slug happens to extend this one's (e.g.
    ``-Users-me-CCDash`` vs. ``-Users-me-CCDash-Sibling-Repo``) into the
    wrong project -- a false-attribution bug that's invisible until someone
    notices sessions from an unrelated repo showing up here. Only the two
    known worktree markers are safe to match on, and
    :func:`split_worktree_dirname` already encodes exactly that rule, so this
    function never re-implements it.

    Never raises: a missing/unreadable parent directory (or any other
    ``OSError`` while listing it) returns ``[]``. Resilience-by-default --
    an absent or pathless project contributes zero siblings, it does not
    poison the caller's scan.

    Two additional guards, both defending against a WRONG-PROJECT ingest
    (sessions silently attributed to the wrong repo, not merely a missed
    session):

    * A dirname like ``<parent>--claude-worktrees-`` (marker present, but an
      EMPTY suffix after it) is not a real worktree -- there is no worktree
      name to label it with -- so it is excluded rather than folded into the
      parent with no worktree label.
    * Marker-named entries that are SYMLINKS are skipped without following
      them. ``Path.is_dir()`` follows symlinks, so a marker-named symlink
      pointing at an unrelated directory would otherwise pass the directory
      check and get scanned as if it belonged to this project. We use
      ``os.scandir`` so ``is_dir(follow_symlinks=False)`` is available
      directly, without a second stat.
    """
    parent = sessions_dir.parent
    try:
        scandir_iter = os.scandir(parent)
    except OSError:
        logger.debug(
            "worktree fan-out: cannot list parent dir, treating as no siblings",
            extra={"sessions_dir": str(sessions_dir), "parent": str(parent)},
        )
        return []

    siblings: list[Path] = []
    try:
        for entry in scandir_iter:
            if entry.path == str(sessions_dir) or entry.name == sessions_dir.name:
                continue
            try:
                # follow_symlinks=False: a marker-named symlink pointing at
                # an unrelated directory must not be treated as this
                # project's worktree -- see docstring.
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            split = split_worktree_dirname(entry.name)
            if split is None:
                continue
            candidate_parent, worktree_name = split
            if candidate_parent != sessions_dir.name:
                continue
            if not worktree_name:
                # Empty suffix (dirname ends exactly at the marker) -- not a
                # real worktree, exclude rather than fold into the parent.
                continue
            siblings.append(Path(entry.path))
    finally:
        scandir_iter.close()

    return sorted(siblings)


def session_scan_roots(sessions_dir: Path) -> list[Path]:
    """``sessions_dir`` first, then its worktree siblings (flag-aware).

    Returns ``[sessions_dir]`` unchanged when
    ``CCDASH_WORKTREE_SESSION_FANOUT_ENABLED`` is off, so callers can adopt
    fan-out without a separate code path for the disabled case.
    """
    from backend import config as _config

    if not getattr(_config, "WORKTREE_SESSION_FANOUT_ENABLED", True):
        return [sessions_dir]

    return [sessions_dir, *sibling_worktree_session_dirs(sessions_dir)]
