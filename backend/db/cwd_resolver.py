"""cwd_resolver.py — Codex session attribution resolver.

Resolves a filesystem working directory (cwd) to a CCDash project_id by
matching against the ``repo_path`` column on registered projects.

Algorithm (D1-a from codex-session-ingestion-v1 plan):
  1. Recognize known worktree layouts before generic prefix matching. Claude
     worktrees resolve through their filesystem parent; Codex's ephemeral
     worktrees resolve to a uniquely registered repository with the same name.
     Unknown Codex worktrees remain unattributed so a home-directory catch-all
     cannot absorb them.
  2. Normalize both paths with os.path.normpath to remove trailing slashes
     and redundant separators.
  3. Exact match: cwd == repo_path → return project_id immediately.
  4. Longest-prefix match: cwd starts with repo_path + os.sep.  The project
     with the longest matching prefix wins (handles nested worktrees correctly).
  5. No match → return None.

The module is intentionally pure (no IO): ``resolve_project_for_cwd`` accepts
a list of project dicts (as returned by SqliteProjectRepository.list_all or
PostgresProjectRepository.list_all).  Callers are responsible for fetching
projects from the DB via the existing project repository.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _project_id_for_repo_path(repo_path: str, projects: list[dict]) -> Optional[str]:
    """Return the project registered at *repo_path*, if any."""
    for project in projects:
        raw_repo = (project.get("repo_path") or "").strip()
        if raw_repo and os.path.normpath(raw_repo) == repo_path:
            return project["id"]
    return None


def _worktree_project_id(cwd: str, projects: list[dict]) -> tuple[bool, Optional[str]]:
    """Resolve known worktree paths without probing the filesystem.

    The boolean records that *cwd* is a recognized Codex layout even if it
    cannot be mapped.  That prevents generic prefix matching from assigning an
    unknown ephemeral worktree to a catch-all project rooted at the home dir.
    """
    parts = Path(cwd).parts
    for index, segment in enumerate(parts):
        if segment == ".claude" and parts[index + 1 : index + 2] == ("worktrees",):
            # Preserve an explicit project registration for this worktree.
            # The parent fallback is for the normal one-project-per-repo
            # registry layout.
            explicit = _longest_prefix_project_id(cwd, projects)
            if explicit is not None:
                explicit_path = next(
                    os.path.normpath((project.get("repo_path") or "").strip())
                    for project in projects
                    if project["id"] == explicit
                )
                if ".claude" + os.sep + "worktrees" in explicit_path:
                    return True, explicit
            parent = os.path.normpath(str(Path(*parts[:index])))
            return True, _project_id_for_repo_path(parent, projects)

        if (
            segment == ".codex"
            and parts[index + 1 : index + 2] == ("worktrees",)
            and len(parts) > index + 3
        ):
            repo_name = parts[index + 3]
            matches = [
                project["id"]
                for project in projects
                if (raw_repo := (project.get("repo_path") or "").strip())
                and os.path.basename(os.path.normpath(raw_repo)) == repo_name
            ]
            return True, matches[0] if len(matches) == 1 else None

    return False, None


def _longest_prefix_project_id(cwd: str, projects: list[dict]) -> Optional[str]:
    """Return the generic longest-prefix result without worktree handling."""
    best_project_id: Optional[str] = None
    best_prefix_len = -1
    for project in projects:
        raw_repo = (project.get("repo_path") or "").strip()
        if not raw_repo:
            continue
        norm_repo = os.path.normpath(raw_repo)
        if cwd == norm_repo:
            return project["id"]
        if cwd.startswith(norm_repo + os.sep) and len(norm_repo) > best_prefix_len:
            best_prefix_len = len(norm_repo)
            best_project_id = project["id"]
    return best_project_id


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

    is_worktree, worktree_project_id = _worktree_project_id(norm_cwd, projects)
    if is_worktree:
        return worktree_project_id

    return _longest_prefix_project_id(norm_cwd, projects)
