"""Git-metadata attribution for Claude project dirs without a marker slug."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.project_paths.worktree_parent_resolution import (
    first_cwd_from_session_dir,
    resolve_git_worktree_parent,
    resolve_unmarked_worktree_child,
)


def _make_unmarked_worktree(
    tmp_path: Path, sessions_dirname: str, checkout_dirname: str
) -> tuple[Path, Path, Path]:
    repo = tmp_path / "fixture-repo"
    checkout = tmp_path / ".wt" / checkout_dirname
    worktree_admin = repo / ".git" / "worktrees" / checkout_dirname
    worktree_admin.mkdir(parents=True)
    checkout.mkdir(parents=True)
    (checkout / ".git").write_text(f"gitdir: {worktree_admin}\n", encoding="utf-8")

    sessions_dir = tmp_path / "claude-projects" / sessions_dirname
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "abc.jsonl").write_text(
        f'{{"cwd": "{checkout}", "sessionId": "abc"}}\n', encoding="utf-8"
    )
    return repo, checkout, sessions_dir


def test_sibling_hub_slug_resolves_parent_and_stable_checkout_label(tmp_path: Path) -> None:
    repo, checkout, sessions_dir = _make_unmarked_worktree(
        tmp_path,
        "-Users-miethe-dev-homelab-development--wt-dendro-r3b-0906",
        "fixture-worktree",
    )

    assert first_cwd_from_session_dir(sessions_dir) == checkout
    assert resolve_git_worktree_parent(checkout) == repo
    assert resolve_unmarked_worktree_child(sessions_dir, {"parent": repo}) == (
        "parent",
        "fixture-worktree",
    )


def test_repo_wt_suffix_uses_identical_git_metadata_resolution(tmp_path: Path) -> None:
    repo, checkout, sessions_dir = _make_unmarked_worktree(
        tmp_path,
        "-tmp-fixture-repo-wt-fix-watcher-timeout",
        "fixture-repo-wt-fix-watcher-timeout",
    )

    assert resolve_unmarked_worktree_child(sessions_dir, {"parent": repo}) == (
        "parent",
        "fixture-repo-wt-fix-watcher-timeout",
    )
    assert checkout.name == "fixture-repo-wt-fix-watcher-timeout"


@pytest.mark.parametrize("git_text", ["", "not-gitdir: /tmp/nope\n", "gitdir: /tmp/nope/.git/elsewhere\n"])
def test_unrecognised_git_metadata_returns_none(tmp_path: Path, git_text: str) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text(git_text, encoding="utf-8")

    assert resolve_git_worktree_parent(checkout) is None


def test_main_repo_git_directory_is_not_a_child(tmp_path: Path) -> None:
    repo = tmp_path / "ordinary-repo"
    (repo / ".git").mkdir(parents=True)
    assert resolve_git_worktree_parent(repo) is None


def test_missing_cwd_or_unknown_parent_never_guesses(tmp_path: Path) -> None:
    repo, _checkout, sessions_dir = _make_unmarked_worktree(
        tmp_path, "-unmarked-sibling-hub", "fixture-worktree"
    )
    assert resolve_unmarked_worktree_child(sessions_dir, {"other": tmp_path / "other-repo"}) is None

    empty_sessions = tmp_path / "empty-sessions"
    empty_sessions.mkdir()
    (empty_sessions / "no-cwd.jsonl").write_text('{"sessionId": "no-cwd"}\n', encoding="utf-8")
    assert first_cwd_from_session_dir(empty_sessions) is None
    assert resolve_unmarked_worktree_child(empty_sessions, {"parent": repo}) is None


def test_child_session_scan_targets_parent_id_and_stamps_registered_label(tmp_path: Path) -> None:
    """M2: child transcript persistence is parent-scoped, with a label retained."""
    from backend.db.sync_engine import SyncEngine

    sessions_dir = tmp_path / "unmarked-child"
    sessions_dir.mkdir()
    session_file = sessions_dir / "abc.jsonl"
    session_file.write_text("{}\n", encoding="utf-8")

    engine = SyncEngine.__new__(SyncEngine)
    engine._rglob_cache = {}
    engine.scan_manifest_repo = MagicMock()
    engine._light_mode_scan_skip = AsyncMock(return_value=False)
    engine._update_manifest_for_roots = AsyncMock()
    engine._sync_single_session = AsyncMock(return_value=True)

    result = asyncio.run(
        engine._sync_sessions(
            "parent-project",
            sessions_dir,
            force=True,
            worktree_label="fixture-worktree",
        )
    )

    assert result["synced"] == 1
    engine._sync_single_session.assert_awaited_once_with(
        "parent-project", session_file, True, worktree_label="fixture-worktree"
    )
