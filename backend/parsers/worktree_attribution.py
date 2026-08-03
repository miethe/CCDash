"""Worktree attribution — a pure helper shared by ingest and the backfill script.

Claude Code stores every project's sessions under a directory whose name is the
absolute repo path with '/', '_' and '.' collapsed to '-':

    ~/.claude/projects/-Users-miethe-dev-repo/<session-id>.jsonl

When the repo has a git worktree, Claude records the WORKTREE's path the same
way, which appends one of two markers to the encoded name:

    <parent>--claude-worktrees-<name>        # created by dev-execution
    <parent>--git-hermes-worktrees-<name>    # created by Hermes on the node

So the *parent-repo* project dir is always the substring left of the first
marker, and the worktree's LABEL is everything after it. This lets us:

* Recognise a session file as belonging to a worktree from the file path alone,
  with no filesystem probe (no ``os.path.isdir``, no encoding round-trip).
* Recover the parent repo's project dir so the watcher can ingest worktree
  session files under the PARENT's ``project_id`` -- keeping the registry at
  one row per repo, not one per worktree.
* Derive a stable ``worktree_name`` label for the session detail view.

The functions here are pure: no I/O, no globals, no side effects. That is
deliberate -- the ingest hook, the discovery pass in the watcher, the backfill
script, and their unit tests all get the SAME behaviour without touching the
filesystem.

Note: :func:`worktree_marker` and :func:`parent_repo_dirname` are duplicated in
``scripts/register_claude_projects.py`` for that script's stdlib-only stance
(no ``backend.*`` imports). The definitions must stay in lockstep; a divergence
would attribute sessions to the wrong parent. A shared import boundary would
break the script's ``python3 scripts/...`` entry point, so keep them literal.
"""
from __future__ import annotations

from pathlib import Path

# Markers appearing in a Claude project dir name when it belongs to a git
# worktree. Order does not matter -- a single dir cannot carry both.
_WORKTREE_MARKERS: tuple[str, ...] = (
    "--claude-worktrees-",
    "--git-hermes-worktrees-",
)


def worktree_marker(dirname: str) -> str | None:
    """Return the worktree marker present in ``dirname``, or ``None``.

    ``dirname`` is a Claude project directory basename (the encoded absolute
    path). Returns the FIRST marker found; a single dir cannot legitimately
    contain both (the markers are mutually exclusive on the filesystem).
    """
    for marker in _WORKTREE_MARKERS:
        if marker in dirname:
            return marker
    return None


def split_worktree_dirname(dirname: str) -> tuple[str, str] | None:
    """Split ``dirname`` into (parent-project-dir, worktree-name), or ``None``.

    Returns ``None`` when ``dirname`` is not a worktree. The worktree name is
    everything after the marker (empty string if the marker sits at the tail).
    """
    marker = worktree_marker(dirname)
    if marker is None:
        return None
    parent, _, suffix = dirname.partition(marker)
    return parent, suffix


def parent_repo_dirname(dirname: str) -> str | None:
    """Return the parent-repo project dir for a worktree dirname, or ``None``.

    Convenience wrapper over :func:`split_worktree_dirname`. Returns ``None``
    when ``dirname`` is not a worktree so callers can branch cheaply.
    """
    split = split_worktree_dirname(dirname)
    return split[0] if split else None


def worktree_name_for_source(source_path: str | Path | None) -> str | None:
    """Derive the worktree label from a session's ``source_file`` path.

    Handles the two shapes ``source_file`` takes on in the DB:

    * **Claude Code jsonl** — a real path whose enclosing directory is a Claude
      project dir. If that dir carries a worktree marker
      (``…--claude-worktrees-<name>`` or ``…--git-hermes-worktrees-<name>``)
      the label is the suffix.
    * **Codex rollout jsonl** — an untimestamped path under ``~/.codex/sessions``
      whose ``cwd`` field (not ``source_file``) is the actual worktree path.
      For that shape callers pass the ``cwd`` string instead of the source path,
      and we recognise ``/.claude/worktrees/<name>``, ``/.git/hermes-worktrees/<name>``,
      or ``/.codex/worktrees/<hash>/<name>`` layouts.

    Returns ``None`` for main-repo sessions and for inputs we cannot classify.
    Never returns an empty string -- callers rely on NULL == main-repo.
    """
    if source_path is None:
        return None
    text = str(source_path)
    if not text:
        return None

    # Shape 1: Claude project dir with an embedded worktree marker.
    parent = Path(text).parent.name
    if parent:
        split = split_worktree_dirname(parent)
        if split is not None:
            _, name = split
            return name or None

    # Shape 2: a real filesystem worktree path (from ``cwd``). Match on the
    # KNOWN worktree directory shapes rather than on any occurrence of
    # "worktrees" -- overly loose regexes are how "clever" backfills silently
    # relabel unrelated rows. Recognised layouts:
    #   <repo>/.claude/worktrees/<name>          (dev-execution)
    #   <repo>/.git/hermes-worktrees/<name>      (Hermes on the node)
    #   ~/.codex/worktrees/<hash>/<name>         (Codex CLI)
    parts = Path(text).parts
    for i, seg in enumerate(parts):
        if seg in ("worktrees", "hermes-worktrees") and i > 0 and i + 1 < len(parts):
            container = parts[i - 1]
            if container == ".claude" and seg == "worktrees":
                return parts[i + 1] or None
            if container == ".git" and seg == "hermes-worktrees":
                return parts[i + 1] or None
            if container == ".codex" and seg == "worktrees":
                # <hash>/<name> follows -- label is the final segment.
                return parts[-1] or None
    return None
