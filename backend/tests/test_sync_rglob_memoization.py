"""Tests for per-run rglob memoization in SyncEngine.

Verifies that _rglob() performs exactly one filesystem traversal per
(root, pattern) pair within a sync run and returns cached results on
subsequent calls with the same key.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    """Return a SyncEngine instance with all repository deps mocked out."""
    db = MagicMock()

    # Patch every get_*_repository function so __init__ doesn't need a real DB.
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRglobMemoization:
    """Unit tests for SyncEngine._rglob() per-run cache."""

    def setup_method(self):
        self.engine = _make_engine()

    def test_cache_populated_on_first_call(self, tmp_path: Path):
        """First call with a key populates _rglob_cache."""
        (tmp_path / "a.md").touch()
        assert not self.engine._rglob_cache
        result = self.engine._rglob(tmp_path, "*.md")
        assert len(result) == 1
        assert (str(tmp_path.resolve()), "*.md") in self.engine._rglob_cache

    def test_second_call_returns_cached_result(self, tmp_path: Path):
        """Second call with same (root, pattern) hits the cache — no re-traversal."""
        (tmp_path / "a.md").touch()

        call_count = 0
        original_rglob = Path.rglob

        def counting_rglob(self_path, pattern):
            nonlocal call_count
            call_count += 1
            return original_rglob(self_path, pattern)

        with patch.object(Path, "rglob", counting_rglob):
            self.engine._rglob(tmp_path, "*.md")
            self.engine._rglob(tmp_path, "*.md")

        assert call_count == 1, (
            "Path.rglob should be called exactly once per (root, pattern) per run; "
            f"got {call_count} calls"
        )

    def test_different_patterns_traverse_separately(self, tmp_path: Path):
        """Different patterns on the same root each trigger one traversal."""
        (tmp_path / "a.md").touch()
        (tmp_path / "b.jsonl").touch()

        call_count = 0
        original_rglob = Path.rglob

        def counting_rglob(self_path, pattern):
            nonlocal call_count
            call_count += 1
            return original_rglob(self_path, pattern)

        with patch.object(Path, "rglob", counting_rglob):
            self.engine._rglob(tmp_path, "*.md")
            self.engine._rglob(tmp_path, "*.jsonl")
            # Second calls — should not increment
            self.engine._rglob(tmp_path, "*.md")
            self.engine._rglob(tmp_path, "*.jsonl")

        assert call_count == 2, (
            "Expected exactly 2 traversals (one per distinct pattern); "
            f"got {call_count}"
        )

    def test_different_roots_traverse_separately(self, tmp_path: Path):
        """Different roots with the same pattern each trigger one traversal."""
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        (root_a / "x.md").touch()
        (root_b / "y.md").touch()

        call_count = 0
        original_rglob = Path.rglob

        def counting_rglob(self_path, pattern):
            nonlocal call_count
            call_count += 1
            return original_rglob(self_path, pattern)

        with patch.object(Path, "rglob", counting_rglob):
            self.engine._rglob(root_a, "*.md")
            self.engine._rglob(root_b, "*.md")
            self.engine._rglob(root_a, "*.md")
            self.engine._rglob(root_b, "*.md")

        assert call_count == 2, (
            "Expected exactly 2 traversals (one per distinct root); "
            f"got {call_count}"
        )

    def test_cache_cleared_between_invocations(self, tmp_path: Path):
        """Manually clearing the cache (as sync_project does) causes re-traversal."""
        (tmp_path / "a.md").touch()

        call_count = 0
        original_rglob = Path.rglob

        def counting_rglob(self_path, pattern):
            nonlocal call_count
            call_count += 1
            return original_rglob(self_path, pattern)

        with patch.object(Path, "rglob", counting_rglob):
            self.engine._rglob(tmp_path, "*.md")
            # Simulate what sync_project does at the start of a new run
            self.engine._rglob_cache = {}
            self.engine._rglob(tmp_path, "*.md")

        assert call_count == 2, (
            "After cache is cleared a fresh traversal should occur; "
            f"got {call_count} calls"
        )

    def test_returns_tuple_of_paths(self, tmp_path: Path):
        """_rglob() always returns a tuple (consistent, hashable container)."""
        (tmp_path / "f.md").touch()
        result = self.engine._rglob(tmp_path, "*.md")
        assert isinstance(result, tuple)
        assert all(isinstance(p, Path) for p in result)

    def test_empty_directory_returns_empty_tuple(self, tmp_path: Path):
        """Empty directory yields empty tuple, not None or generator."""
        result = self.engine._rglob(tmp_path, "*.md")
        assert result == ()
