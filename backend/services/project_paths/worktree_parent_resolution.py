"""Fail-closed parent resolution for Claude sessions from unmarked worktrees.

Unlike the established Claude/Hermes worktree markers, sibling-hub checkouts
and ``<repo>-wt-<suffix>`` checkouts cannot be attributed from their slug.
Their ``.git`` *file* is the authoritative relationship to the main checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

_MAX_SESSION_FILES = 3
_MAX_SESSION_LINES = 50


def resolve_git_worktree_parent(checkout_path: Path) -> Path | None:
    """Return the main repository root recorded by a git-worktree ``.git`` file.

    A normal repository has a ``.git`` directory and is deliberately not a
    child.  Unknown file contents and every filesystem failure fail closed.
    """
    git_path = checkout_path / ".git"
    try:
        if git_path.is_dir() or not git_path.is_file():
            return None
        first_line = git_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError, UnicodeError):
        return None

    prefix = "gitdir:"
    if not first_line.startswith(prefix):
        return None
    raw_gitdir = first_line[len(prefix):].strip()
    if not raw_gitdir:
        return None

    try:
        gitdir = Path(raw_gitdir)
        if not gitdir.is_absolute():
            gitdir = git_path.parent / gitdir
        gitdir = gitdir.resolve(strict=False)
    except OSError:
        return None

    # Expected shape is <repo>/.git/worktrees/<worktree-name>.  Do not accept
    # a merely similar path: a false parent is worse than an unregistered child.
    if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
        return None
    return gitdir.parent.parent.parent


def first_cwd_from_session_dir(sessions_dir: Path) -> Path | None:
    """Read the first top-level ``cwd`` from a bounded Claude session scan."""
    try:
        files = list(sessions_dir.glob("*.jsonl"))[:_MAX_SESSION_FILES]
    except OSError:
        return None

    for session_file in files:
        try:
            with session_file.open(encoding="utf-8") as handle:
                for _ in range(_MAX_SESSION_LINES):
                    line = handle.readline()
                    if not line:
                        break
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    cwd = record.get("cwd")
                    if isinstance(cwd, str) and cwd.strip():
                        return Path(cwd)
        except (OSError, UnicodeError):
            continue
    return None


def resolve_unmarked_worktree_child(
    sessions_dir: Path, candidate_parent_paths: dict[str, Path]
) -> tuple[str, str] | None:
    """Resolve an unmarked Claude directory to ``(parent_id, worktree_label)``.

    Parent matching is exact after non-strict path resolution.  In particular,
    this does not infer a parent from a slug, basename, prefix, or substring.
    """
    checkout_path = first_cwd_from_session_dir(sessions_dir)
    if checkout_path is None:
        return None
    parent_path = resolve_git_worktree_parent(checkout_path)
    if parent_path is None:
        return None
    try:
        resolved_parent = parent_path.resolve(strict=False)
    except OSError:
        return None

    for project_id, candidate_path in candidate_parent_paths.items():
        try:
            if resolved_parent == candidate_path.resolve(strict=False):
                label = checkout_path.name
                return (project_id, label) if label else None
        except OSError:
            continue
    return None
