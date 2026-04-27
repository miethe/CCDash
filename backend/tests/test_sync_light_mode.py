"""Tests for CCDASH_STARTUP_SYNC_LIGHT_MODE document/progress scan short-circuit.

Four cases are covered:
  1. flag=False  → full walk regardless of manifest state.
  2. flag=True + empty manifest → full walk + manifest populated at end.
  3. flag=True + matching manifest → walk skipped entirely.
  4. flag=True + diff (one file changed) → full walk re-runs (not skipped).
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_FACTORIES = [
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
    "backend.db.sync_engine.get_scan_manifest_repository",
]


def _make_engine(manifest_repo: MagicMock | None = None):
    """Return a SyncEngine with all repository deps mocked out.

    If *manifest_repo* is provided it replaces the default mock for
    ``get_scan_manifest_repository`` so tests can inspect/configure it.
    """
    db = MagicMock()
    sentinel = object()  # unique sentinel so we can replace the right mock below

    patches = [patch(f, return_value=MagicMock()) for f in _REPO_FACTORIES]
    pricing_patch = patch(
        "backend.db.sync_engine.PricingCatalogService", return_value=MagicMock()
    )

    mocks = [p.start() for p in patches]
    pricing_patch.start()

    # Replace scan_manifest mock if caller supplied their own.
    if manifest_repo is not None:
        manifest_factory_idx = _REPO_FACTORIES.index(
            "backend.db.sync_engine.get_scan_manifest_repository"
        )
        mocks[manifest_factory_idx].return_value = manifest_repo

    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine(db)

    for p in patches:
        p.stop()
    pricing_patch.stop()

    # Inject manifest repo directly so tests can interact with it.
    if manifest_repo is not None:
        engine.scan_manifest_repo = manifest_repo

    return engine


def _make_manifest_repo(
    stored: dict[str, tuple[float, int]] | None = None,
) -> MagicMock:
    """Build a mock SqliteScanManifestRepository.

    *stored* is the manifest the repo returns from ``fetch_manifest`` /
    ``diff_against``.  If None an empty manifest is used (empty table).
    """
    repo = MagicMock()
    stored = stored or {}

    async def _diff_against(current: dict[str, tuple[float, int]]) -> dict:
        stored_paths = set(stored)
        current_paths = set(current)
        added = sorted(current_paths - stored_paths)
        removed = sorted(stored_paths - current_paths)
        changed = sorted(
            p for p in stored_paths & current_paths if stored[p] != current[p]
        )
        return {"added": added, "removed": removed, "changed": changed}

    repo.diff_against = _diff_against
    repo.upsert_manifest = AsyncMock()
    return repo


def _create_md_files(directory: Path, names: list[str]) -> list[Path]:
    files = []
    for name in names:
        p = directory / name
        p.write_text(f"# {name}")
        files.append(p)
    return files


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLightModeSkip:
    """Unit tests for the light-mode scan short-circuit in _sync_documents."""

    # -- Case 1: flag disabled → full walk always ---------------------------

    def test_flag_false_always_full_walk(self, tmp_path: Path):
        """When STARTUP_SYNC_LIGHT_MODE=False the walk runs even if manifest matches."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        _create_md_files(docs_dir, ["plan.md"])

        # Build a manifest that would match (mtime+size identical).
        md_file = docs_dir / "plan.md"
        st = md_file.stat()
        stored = {str(md_file): (st.st_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)

        rglob_call_count = 0
        orig_rglob = engine._rglob

        def counting_rglob(root, pattern):
            nonlocal rglob_call_count
            rglob_call_count += 1
            return orig_rglob(root, pattern)

        engine._rglob = counting_rglob

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = False
                # Stub out expensive sub-calls so we only measure the rglob path.
                engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
                engine._sync_single_document = AsyncMock(return_value=False)
                engine._update_manifest_for_roots = AsyncMock()
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)

        asyncio.get_event_loop().run_until_complete(run())

        assert rglob_call_count >= 1, (
            "Expected at least one _rglob call when light mode is disabled; "
            f"got {rglob_call_count}"
        )

    # -- Case 2: flag=True + empty manifest → full walk + manifest written ---

    def test_flag_true_empty_manifest_full_walk_and_upsert(self, tmp_path: Path):
        """Empty manifest forces a full walk; manifest is written at the end."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        _create_md_files(docs_dir, ["spec.md", "plan.md"])

        manifest_repo = _make_manifest_repo(stored={})  # empty → diff has "added" entries
        engine = _make_engine(manifest_repo=manifest_repo)

        rglob_call_count = 0
        orig_rglob = engine._rglob

        def counting_rglob(root, pattern):
            nonlocal rglob_call_count
            rglob_call_count += 1
            return orig_rglob(root, pattern)

        engine._rglob = counting_rglob

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
                engine._sync_single_document = AsyncMock(return_value=True)
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)

        asyncio.get_event_loop().run_until_complete(run())

        assert rglob_call_count >= 1, "Full walk must run when manifest is empty"
        assert manifest_repo.upsert_manifest.called, (
            "upsert_manifest must be called after a full walk to refresh the manifest"
        )
        entries_arg = manifest_repo.upsert_manifest.call_args[0][0]
        assert len(entries_arg) >= 1, "Manifest must contain at least one entry after the walk"

    # -- Case 3: flag=True + matching manifest → walk skipped ---------------

    def test_flag_true_matching_manifest_skip(self, tmp_path: Path):
        """When manifest exactly matches on-disk stats the walk is skipped."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        md = _create_md_files(docs_dir, ["readme.md"])[0]
        st = md.stat()
        stored = {str(md): (st.st_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)

        rglob_call_count = 0
        orig_rglob = engine._rglob

        def counting_rglob(root, pattern):
            nonlocal rglob_call_count
            rglob_call_count += 1
            return orig_rglob(root, pattern)

        engine._rglob = counting_rglob

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
                engine._sync_single_document = AsyncMock(return_value=False)
                engine._update_manifest_for_roots = AsyncMock()
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)

        asyncio.get_event_loop().run_until_complete(run())

        assert rglob_call_count == 0, (
            "Expected zero _rglob calls when light mode skips the walk; "
            f"got {rglob_call_count}"
        )
        # Manifest must NOT be re-written when walk is skipped.
        engine._update_manifest_for_roots.assert_not_called()

    # -- Case 4: flag=True + diff (one file changed) → full walk re-runs ----

    def test_flag_true_diff_triggers_full_walk(self, tmp_path: Path):
        """When one file's mtime differs the manifest diff is non-empty → full walk."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        md = _create_md_files(docs_dir, ["notes.md"])[0]
        st = md.stat()
        # Store a stale mtime so the diff reports a change.
        stale_mtime = st.st_mtime - 10.0
        stored = {str(md): (stale_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)

        rglob_call_count = 0
        orig_rglob = engine._rglob

        def counting_rglob(root, pattern):
            nonlocal rglob_call_count
            rglob_call_count += 1
            return orig_rglob(root, pattern)

        engine._rglob = counting_rglob

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
                engine._sync_single_document = AsyncMock(return_value=True)
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)

        asyncio.get_event_loop().run_until_complete(run())

        assert rglob_call_count >= 1, (
            "Expected a full walk when one file's mtime changed in the manifest; "
            f"got {rglob_call_count}"
        )
        assert manifest_repo.upsert_manifest.called, (
            "Manifest must be refreshed after a full walk triggered by a diff"
        )


class TestLightModeSkipObservability:
    """Verify that record_filesystem_scan_cached() is called on the skip path only."""

    def test_manifest_match_records_cached_counter(self, tmp_path: Path):
        """Counter fires exactly once when light-mode skips due to manifest match."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        md = _create_md_files(docs_dir, ["README.md"])[0]
        st = md.stat()
        stored = {str(md): (st.st_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)
        engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
        engine._sync_single_document = AsyncMock(return_value=False)
        engine._update_manifest_for_roots = AsyncMock()

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config, \
                 patch("backend.observability.otel.record_filesystem_scan_cached") as mock_counter:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)
                return mock_counter

        mock_counter = asyncio.get_event_loop().run_until_complete(run())
        mock_counter.assert_called_once()

    def test_manifest_mismatch_does_not_record_cached_counter(self, tmp_path: Path):
        """Counter must NOT fire when manifest differs (full walk taken)."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        md = _create_md_files(docs_dir, ["changed.md"])[0]
        st = md.stat()
        # Stale mtime → diff is non-empty → skip NOT taken.
        stored = {str(md): (st.st_mtime - 10.0, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)
        engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
        engine._sync_single_document = AsyncMock(return_value=True)

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config, \
                 patch("backend.observability.otel.record_filesystem_scan_cached") as mock_counter:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)
                return mock_counter

        mock_counter = asyncio.get_event_loop().run_until_complete(run())
        mock_counter.assert_not_called()

    def test_light_mode_disabled_does_not_record_cached_counter(self, tmp_path: Path):
        """Counter must NOT fire when light-mode is disabled entirely."""
        docs_dir = tmp_path / "docs"
        progress_dir = tmp_path / "progress"
        docs_dir.mkdir()
        progress_dir.mkdir()
        md = _create_md_files(docs_dir, ["plan.md"])[0]
        st = md.stat()
        stored = {str(md): (st.st_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)
        engine._build_git_doc_dates = MagicMock(return_value=({}, set()))
        engine._sync_single_document = AsyncMock(return_value=False)
        engine._update_manifest_for_roots = AsyncMock()

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config, \
                 patch("backend.observability.otel.record_filesystem_scan_cached") as mock_counter:
                mock_config.STARTUP_SYNC_LIGHT_MODE = False
                await engine._sync_documents("proj", docs_dir, progress_dir, force=False)
                return mock_counter

        mock_counter = asyncio.get_event_loop().run_until_complete(run())
        mock_counter.assert_not_called()


class TestLightModeProgressSync:
    """Unit tests for the light-mode short-circuit in _sync_progress."""

    def test_progress_flag_true_matching_manifest_skip(self, tmp_path: Path):
        """_sync_progress skips the walk when manifest matches for progress files."""
        progress_dir = tmp_path / "progress"
        progress_dir.mkdir()
        pf = progress_dir / "phase-1-progress.md"
        pf.write_text("# progress")
        st = pf.stat()
        stored = {str(pf): (st.st_mtime, st.st_size)}
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)
        engine._sync_single_progress = AsyncMock(return_value=False)
        engine._update_manifest_for_roots = AsyncMock()

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                return await engine._sync_progress("proj", progress_dir, force=False)

        stats = asyncio.get_event_loop().run_until_complete(run())

        engine._sync_single_progress.assert_not_called()
        engine._update_manifest_for_roots.assert_not_called()
        assert stats == {"synced": 0, "skipped": 0}

    def test_progress_flag_true_diff_triggers_walk(self, tmp_path: Path):
        """_sync_progress does a full walk when a progress file changed."""
        progress_dir = tmp_path / "progress"
        progress_dir.mkdir()
        pf = progress_dir / "phase-1-progress.md"
        pf.write_text("# progress")
        st = pf.stat()
        stored = {str(pf): (st.st_mtime - 5.0, st.st_size)}  # stale mtime
        manifest_repo = _make_manifest_repo(stored=stored)

        engine = _make_engine(manifest_repo=manifest_repo)
        engine._sync_single_progress = AsyncMock(return_value=True)

        async def run():
            with patch("backend.db.sync_engine.config") as mock_config:
                mock_config.STARTUP_SYNC_LIGHT_MODE = True
                return await engine._sync_progress("proj", progress_dir, force=False)

        stats = asyncio.get_event_loop().run_until_complete(run())

        engine._sync_single_progress.assert_called_once()
        assert manifest_repo.upsert_manifest.called
        assert stats["synced"] == 1
