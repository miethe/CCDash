"""cwd_resolver.py — Codex session attribution resolver.

Resolves a filesystem working directory (cwd) to a CCDash project_id by
matching against the ``repo_path`` column on registered projects.

Algorithm (D1-a from codex-session-ingestion-v1 plan):
  1. Normalize both paths with os.path.normpath to remove trailing slashes
     and redundant separators.
  2. Exact match: cwd == repo_path → return project_id immediately.
  3. Longest-prefix match: cwd starts with repo_path + os.sep.  The project
     with the longest matching prefix wins (handles nested worktrees correctly).
  4. No match → return None.

The module is intentionally pure (no IO): ``resolve_project_for_cwd`` accepts
a list of project dicts (as returned by SqliteProjectRepository.list_all or
PostgresProjectRepository.list_all).  Callers are responsible for fetching
projects from the DB via the existing project repository.
"""
from __future__ import annotations

import os
from typing import Optional


def resolve_project_for_cwd(
    cwd: str,
    projects: list[dict],
) -> Optional[str]:
    """Resolve a filesystem cwd to a CCDash project_id.

    Args:
        cwd: Absolute path of the working directory to resolve.  Empty string
            or paths that do not match any registered repo_path return None.
        projects: Sequence of project dicts as returned by the project
            repository's ``list_all()`` method.  Each dict must have at least
            an ``"id"`` key and an optional ``"repo_path"`` key.

    Returns:
        The ``project_id`` of the best-matching registered project, or None if
        no project's ``repo_path`` matches or covers ``cwd``.

    Examples:
        >>> projects = [{"id": "p1", "repo_path": "/a/b/repo"}]
        >>> resolve_project_for_cwd("/a/b/repo", projects)
        'p1'
        >>> resolve_project_for_cwd("/a/b/repo/sub/dir", projects)
        'p1'
        >>> resolve_project_for_cwd("/a/b/other", projects)
    """
    if not cwd:
        return None

    norm_cwd = os.path.normpath(cwd)

    best_project_id: Optional[str] = None
    best_prefix_len: int = -1

    for project in projects:
        raw_repo = (project.get("repo_path") or "").strip()
        if not raw_repo:
            continue

        norm_repo = os.path.normpath(raw_repo)

        # ── Exact match (highest priority) ──────────────────────────────────
        if norm_cwd == norm_repo:
            return project["id"]

        # ── Prefix match: cwd must start with repo_path + separator ─────────
        # Using os.sep prevents false matches like /a/b/repo2 matching /a/b/repo.
        prefix = norm_repo + os.sep
        if norm_cwd.startswith(prefix):
            prefix_len = len(norm_repo)
            if prefix_len > best_prefix_len:
                best_prefix_len = prefix_len
                best_project_id = project["id"]

    return best_project_id
