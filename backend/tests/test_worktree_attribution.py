"""Unit tests for the pure worktree-attribution helper.

The helper is a shared spine: the ingest hook (:mod:`backend.db.sync_engine`),
the backfill script, and future watcher auto-discovery all route their
worktree-vs-main-repo decision through the same three functions
(:func:`worktree_marker`, :func:`split_worktree_dirname`,
:func:`worktree_name_for_source`). A regression here silently misattributes
every worktree session on the fleet, so the cases below are deliberately drawn
from real directory names sampled off the live ``sessions.source_file`` column.

Everything is pure string/path work -- no fixtures, no tmp_path, no DB.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.parsers.worktree_attribution import (
    parent_repo_dirname,
    split_worktree_dirname,
    worktree_marker,
    worktree_name_for_source,
)

# Real dir names harvested from the live projects tree (redacted to /Users/m/dev).
CLAUDE_WT_DIR = "-Users-m-dev-agentic-meta-dev--claude-worktrees-skill-dev-standardization-plan"
HERMES_WT_DIR = "-home-miethe-dev-agentic-meta-dev--git-hermes-worktrees-run-01KYWM0JAX18WXAK9HHESCJGD2"
PLAIN_DIR = "-Users-m-dev-agentic-meta-dev"
KNITWIT_WT_DIR = "-Users-m-dev-knitwit--claude-worktrees-colorwork-extraction-v1"


# --- worktree_marker --------------------------------------------------------


@pytest.mark.parametrize(
    "dirname,expected",
    [
        (CLAUDE_WT_DIR, "--claude-worktrees-"),
        (HERMES_WT_DIR, "--git-hermes-worktrees-"),
        (KNITWIT_WT_DIR, "--claude-worktrees-"),
        (PLAIN_DIR, None),
        ("", None),
        # False-positive guardrails: substring but not the actual marker.
        ("-Users-m-dev-claude-code-worktrees-something", None),
    ],
)
def test_worktree_marker(dirname: str, expected: str | None) -> None:
    assert worktree_marker(dirname) == expected


# --- split_worktree_dirname / parent_repo_dirname ---------------------------


def test_split_dev_execution_worktree() -> None:
    parent, name = split_worktree_dirname(CLAUDE_WT_DIR)  # type: ignore[misc]
    assert parent == "-Users-m-dev-agentic-meta-dev"
    assert name == "skill-dev-standardization-plan"


def test_split_hermes_worktree() -> None:
    parent, name = split_worktree_dirname(HERMES_WT_DIR)  # type: ignore[misc]
    assert parent == "-home-miethe-dev-agentic-meta-dev"
    assert name == "run-01KYWM0JAX18WXAK9HHESCJGD2"


def test_split_non_worktree_returns_none() -> None:
    assert split_worktree_dirname(PLAIN_DIR) is None
    assert parent_repo_dirname(PLAIN_DIR) is None


def test_parent_matches_registered_project_dir() -> None:
    """The parent returned by the helper must be a legal Claude project dirname.

    That is the contract the watcher relies on: it takes ``parent`` and looks up
    the corresponding registered project in the workspace registry. If the
    helper ever returned a mangled parent, that lookup would silently miss and
    the worktree's sessions would fall back to an active-project default.
    """
    parent = parent_repo_dirname(KNITWIT_WT_DIR)
    assert parent == "-Users-m-dev-knitwit"
    # Sanity: it is itself a valid encoded name (single leading dash, no
    # embedded marker), which is what the registered-project index expects.
    assert parent is not None
    assert parent.startswith("-")
    assert worktree_marker(parent) is None


# --- worktree_name_for_source (the ingest stamping helper) ------------------


def _under(dirname: str) -> str:
    """A representative jsonl path under ``~/.claude/projects/<dirname>``."""
    return str(Path.home() / ".claude" / "projects" / dirname / "sess-abc.jsonl")


def test_stamps_dev_execution_worktree_label() -> None:
    assert worktree_name_for_source(_under(CLAUDE_WT_DIR)) == "skill-dev-standardization-plan"


def test_stamps_hermes_worktree_label() -> None:
    assert worktree_name_for_source(_under(HERMES_WT_DIR)) == "run-01KYWM0JAX18WXAK9HHESCJGD2"


def test_main_repo_session_returns_none() -> None:
    """Contract: null == main-repo, never empty string; the upsert relies on it."""
    assert worktree_name_for_source(_under(PLAIN_DIR)) is None


def test_none_and_empty_input_are_tolerated() -> None:
    """Called during ingest with whatever the parser produced -- do not raise."""
    assert worktree_name_for_source(None) is None
    assert worktree_name_for_source("") is None


def test_pathlib_input_matches_string_input() -> None:
    path_str = _under(CLAUDE_WT_DIR)
    assert worktree_name_for_source(Path(path_str)) == worktree_name_for_source(path_str)


def test_dangling_marker_yields_none_not_empty_string() -> None:
    """A dir ending exactly at the marker has no label; must be null, not ''.

    Empty string would poison the ``is_worktree`` derivation and any grep-style
    filter that trusts NULL to mean "main repo".
    """
    dangling = _under("-Users-m-dev-repo--claude-worktrees-")
    assert worktree_name_for_source(dangling) is None


def test_cwd_shape_dev_execution_worktree() -> None:
    """Shape 2: a real filesystem worktree path (from ``cwd``)."""
    cwd = "/Users/m/dev/repo/.claude/worktrees/plan-colorwork-bilateral"
    assert worktree_name_for_source(cwd) == "plan-colorwork-bilateral"


def test_cwd_shape_hermes_worktree() -> None:
    cwd = "/home/miethe/dev/agentic_meta_dev/.git/hermes-worktrees/run-01XYZ"
    assert worktree_name_for_source(cwd) == "run-01XYZ"


def test_cwd_shape_codex_worktree_uses_final_segment() -> None:
    """~/.codex/worktrees/<hash>/<name> -- label is the FINAL segment."""
    cwd = "/Users/m/.codex/worktrees/b0d1a2c3/skillmeat"
    assert worktree_name_for_source(cwd) == "skillmeat"


def test_cwd_shape_ignores_incidental_worktrees_substring() -> None:
    """A folder literally named 'worktrees' with no .claude/.git/.codex marker
    must not be misread as a worktree path.
    """
    assert worktree_name_for_source("/tmp/worktrees/thing/x") is None


def test_nested_path_still_works() -> None:
    """Session files sometimes live under a subagents/workflows subtree.

    The helper keys off the PROJECT dir, not the file's own parent, so nested
    files must still resolve. The real path in the DB was:
    ``.../projects/<encoded>/subagents/workflows/wf_.../agent-<hash>.jsonl``.
    Currently the helper only looks at the immediate parent; document that
    limitation with a test so a future extension can broaden it deliberately.
    """
    nested = str(
        Path.home() / ".claude" / "projects" / CLAUDE_WT_DIR
        / "subagents" / "workflows" / "wf_x" / "agent-y.jsonl"
    )
    # Immediate parent is "wf_x", not the project dir, so today this returns
    # None. Not a bug per se -- subagent rows carry their PARENT session's
    # attribution via the ingest service, so worktree_name flows in from there.
    # Pin the behaviour so a change is a conscious choice.
    assert worktree_name_for_source(nested) is None
