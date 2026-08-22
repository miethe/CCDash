"""Regression tests for worktree session-directory fan-out.

Claude Code slugifies a session's cwd, not the repo root, so a session
launched from ``<repo>/.claude/worktrees/<name>`` lands in a SIBLING Claude
project dir that a registered project's single ``sessions_dir`` never
reaches. ``backend.services.project_paths.worktree_fanout`` is the discovery
helper that closes that gap; these tests exercise it directly plus its two
callers (the watcher's ``_resolve_watch_paths`` and the fan-out-off default
path).

Everything uses ``tmp_path`` -- never touches the real ``~/.claude/projects``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend import config
from backend.db.file_watcher import FileWatcher
from backend.services.project_paths.worktree_fanout import (
    session_scan_roots,
    sibling_worktree_session_dirs,
)


def _mkdirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


class TestSiblingWorktreeSessionDirs:
    def test_claude_worktrees_marker_is_discovered(self, tmp_path: Path) -> None:
        parent = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(parent, sibling)

        result = sibling_worktree_session_dirs(parent)

        assert result == [sibling]

    def test_git_hermes_worktrees_marker_is_discovered(self, tmp_path: Path) -> None:
        parent = tmp_path / "-home-miethe-dev-CCDash"
        sibling = tmp_path / "-home-miethe-dev-CCDash--git-hermes-worktrees-run-01ABC"
        _mkdirs(parent, sibling)

        result = sibling_worktree_session_dirs(parent)

        assert result == [sibling]

    def test_prefix_only_sibling_without_marker_is_excluded(self, tmp_path: Path) -> None:
        # AC: a genuinely different repo whose slug happens to EXTEND the
        # parent's must never be folded in just because it shares a prefix.
        # Only the marker-based match (parent_repo_dirname) is safe.
        parent = tmp_path / "-Users-m-dev-CCDash"
        false_sibling = tmp_path / "-Users-m-dev-CCDash-Sibling-Repo"
        _mkdirs(parent, false_sibling)

        result = sibling_worktree_session_dirs(parent)

        assert result == []

    def test_sessions_dir_itself_is_never_duplicated(self, tmp_path: Path) -> None:
        parent = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(parent, sibling)

        result = sibling_worktree_session_dirs(parent)

        assert parent not in result

    def test_missing_parent_dir_returns_empty_not_raise(self, tmp_path: Path) -> None:
        absent = tmp_path / "does-not-exist" / "-Users-m-dev-CCDash"

        result = sibling_worktree_session_dirs(absent)

        assert result == []

    def test_unreadable_parent_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        parent = tmp_path / "-Users-m-dev-CCDash"
        parent.mkdir()

        def _raise_scandir(path):
            raise PermissionError("denied")

        monkeypatch.setattr("backend.services.project_paths.worktree_fanout.os.scandir", _raise_scandir)

        result = sibling_worktree_session_dirs(parent)

        assert result == []

    def test_empty_worktree_name_suffix_is_excluded(self, tmp_path: Path) -> None:
        # A dir literally named "<parent>--claude-worktrees-" (marker present,
        # nothing after it) is not a real worktree -- there is no name to
        # label it with -- so folding its sessions into the parent would
        # silently attribute them with no worktree label. Must be excluded.
        parent = tmp_path / "-Users-m-dev-CCDash"
        malformed = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-"
        _mkdirs(parent, malformed)

        result = sibling_worktree_session_dirs(parent)

        assert result == []

    def test_symlinked_marker_dir_is_excluded(self, tmp_path: Path) -> None:
        # A marker-named symlink pointing at an UNRELATED directory must not
        # be scanned as if it belonged to this project -- Path.is_dir()
        # follows symlinks, so this guards against false attribution into
        # the wrong project.
        parent = tmp_path / "-Users-m-dev-CCDash"
        unrelated_target = tmp_path / "unrelated-real-dir"
        _mkdirs(parent, unrelated_target)
        symlinked_marker = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-evil"
        symlinked_marker.symlink_to(unrelated_target, target_is_directory=True)

        result = sibling_worktree_session_dirs(parent)

        assert result == []


class TestSessionScanRoots:
    def test_flag_on_includes_siblings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        parent = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(parent, sibling)

        roots = session_scan_roots(parent)

        assert roots == [parent, sibling]

    def test_flag_off_returns_sessions_dir_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", False)
        parent = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(parent, sibling)

        roots = session_scan_roots(parent)

        assert roots == [parent]


class TestWatcherResolveWatchPaths:
    def test_resolve_watch_paths_includes_existing_sibling_worktree_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        root = tmp_path
        sessions_dir = root / "-Users-m-dev-CCDash"
        sibling = root / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        docs_dir = root / "docs"
        progress_dir = root / "progress"
        _mkdirs(sessions_dir, sibling, docs_dir, progress_dir)

        watcher = FileWatcher()
        watch_paths = watcher._resolve_watch_paths(sessions_dir, docs_dir, progress_dir)

        assert sibling in watch_paths
        assert sessions_dir in watch_paths
        # No duplicates.
        assert len(watch_paths) == len(set(watch_paths))

    def test_watch_root_cap_truncates_and_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_MAX_WATCH_ROOTS", 2)
        root = tmp_path
        sessions_dir = root / "-Users-m-dev-CCDash"
        docs_dir = root / "docs"
        progress_dir = root / "progress"
        _mkdirs(sessions_dir, docs_dir, progress_dir)
        siblings = []
        for i in range(5):
            sibling = root / f"-Users-m-dev-CCDash--claude-worktrees-wt{i}"
            sibling.mkdir()
            siblings.append(sibling)

        watcher = FileWatcher()
        with caplog.at_level("WARNING"):
            watch_paths = watcher._resolve_watch_paths(
                sessions_dir, docs_dir, progress_dir, project_id="proj-1"
            )

        watched_siblings = [p for p in watch_paths if p in siblings]
        assert len(watched_siblings) == 2
        assert sessions_dir in watch_paths
        assert any("watch-root cap truncated" in r.message for r in caplog.records)

    def test_sync_sessions_full_scan_is_never_capped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The cap applies ONLY to the watcher's watch paths; the full scan
        # (session_scan_roots itself, which _sync_sessions consumes directly
        # with no cap of its own) must still return every sibling.
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_MAX_WATCH_ROOTS", 2)
        sessions_dir = tmp_path / "-Users-m-dev-CCDash"
        _mkdirs(sessions_dir)
        for i in range(5):
            (tmp_path / f"-Users-m-dev-CCDash--claude-worktrees-wt{i}").mkdir()

        roots = session_scan_roots(sessions_dir)

        assert len(roots) == 6  # sessions_dir + all 5 siblings, uncapped


class TestSyncSessionsScanDiscoversSiblingTranscripts:
    """AC3: a transcript in a sibling worktree-slug dir is discovered by the scan.

    Exercises the EXACT mechanism `SyncEngine._sync_sessions` uses to build its
    file list: union `_rglob(root, "*.jsonl")` over `session_scan_roots(...)`.
    `_rglob` is SyncEngine's real per-run-memoized traversal helper (same
    instance method `_sync_sessions` calls), constructed via a SyncEngine with
    all repository dependencies mocked out -- following the same pattern as
    `test_sync_rglob_memoization.py`. This test would FAIL if the fan-out
    were removed (i.e. if `_sync_sessions` scanned only `sessions_dir`) --
    verified by the companion `test_...disabled_only_finds_parent_transcript`
    test below, which reproduces exactly that condition via the feature flag.
    """

    def test_union_scan_finds_parent_and_sibling_transcripts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        sessions_dir = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(sessions_dir, sibling)
        parent_transcript = sessions_dir / "session-parent.jsonl"
        parent_transcript.write_text("{}\n")
        sibling_transcript = sibling / "session-sibling.jsonl"
        sibling_transcript.write_text("{}\n")

        engine = _make_sync_engine()
        resolved_roots = [r for r in session_scan_roots(sessions_dir) if r.exists()]
        all_files = {f for root in resolved_roots for f in engine._rglob(root, "*.jsonl")}

        assert parent_transcript in all_files
        assert sibling_transcript in all_files

    def test_fanout_disabled_only_finds_parent_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Reproduces the pre-fix condition (fan-out removed/disabled): the
        # sibling transcript must NOT be discoverable, proving the test above
        # is actually sensitive to the fan-out mechanism rather than trivially
        # passing regardless of it.
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", False)
        sessions_dir = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(sessions_dir, sibling)
        parent_transcript = sessions_dir / "session-parent.jsonl"
        parent_transcript.write_text("{}\n")
        sibling_transcript = sibling / "session-sibling.jsonl"
        sibling_transcript.write_text("{}\n")

        engine = _make_sync_engine()
        resolved_roots = [r for r in session_scan_roots(sessions_dir) if r.exists()]
        all_files = {f for root in resolved_roots for f in engine._rglob(root, "*.jsonl")}

        assert parent_transcript in all_files
        assert sibling_transcript not in all_files


class TestSyncChangedFilesScopeCheck:
    """Defect #1 regression: the watcher's incremental hot-path scope test.

    `sync_changed_files` widens its `.jsonl` in-scope check from
    `sessions_dir in path.parents` to membership across
    `set(session_scan_roots(sessions_dir))` -- this exercises that exact
    membership expression against a sibling-worktree path (must be in scope)
    and a genuinely unrelated path (must stay out of scope).
    """

    def test_sibling_worktree_jsonl_is_in_scope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        sessions_dir = tmp_path / "-Users-m-dev-CCDash"
        sibling = tmp_path / "-Users-m-dev-CCDash--claude-worktrees-fix-foo"
        _mkdirs(sessions_dir, sibling)
        sibling_file = sibling / "abc123.jsonl"
        sibling_file.touch()

        session_scan_root_set = set(session_scan_roots(sessions_dir))

        assert any(root in sibling_file.parents for root in session_scan_root_set)

    def test_unrelated_project_jsonl_stays_out_of_scope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "WORKTREE_SESSION_FANOUT_ENABLED", True)
        sessions_dir = tmp_path / "-Users-m-dev-CCDash"
        unrelated = tmp_path / "-Users-m-dev-SomeOtherRepo"
        _mkdirs(sessions_dir, unrelated)
        unrelated_file = unrelated / "xyz789.jsonl"
        unrelated_file.touch()

        session_scan_root_set = set(session_scan_roots(sessions_dir))

        assert not any(root in unrelated_file.parents for root in session_scan_root_set)


def _make_sync_engine():
    """Return a SyncEngine instance with all repository deps mocked out.

    Mirrors the helper in ``test_sync_rglob_memoization.py`` -- SyncEngine's
    constructor pulls in a full repository roster, and this project's tests
    for the pure-traversal helper (`_rglob`) do not need a real DB.
    """
    from unittest.mock import MagicMock, patch

    db = MagicMock()
    repo_factories = [
        "backend.db.sync_engine.get_session_repository",
        "backend.db.sync_engine.get_document_repository",
        "backend.db.sync_engine.get_task_repository",
        "backend.db.sync_engine.get_feature_repository",
        "backend.db.sync_engine.get_entity_link_repository",
        "backend.db.sync_engine.get_sync_state_repository",
        "backend.db.sync_engine.get_tag_repository",
        "backend.db.sync_engine.get_analytics_repository",
        "backend.db.sync_engine.get_session_usage_repository",
        "backend.db.sync_engine.get_session_message_repository",
        "backend.db.sync_engine.get_session_intelligence_repository",
        "backend.db.sync_engine.get_telemetry_queue_repository",
        "backend.db.sync_engine.get_pricing_catalog_repository",
    ]
    patches = [patch(f, return_value=MagicMock()) for f in repo_factories]
    pricing_patch = patch(
        "backend.db.sync_engine.PricingCatalogService", return_value=MagicMock()
    )
    for p in patches:
        p.start()
    pricing_patch.start()

    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine(db)

    for p in patches:
        p.stop()
    pricing_patch.stop()

    return engine
