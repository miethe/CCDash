"""Phase 4 — Live Link Freshness tests.

Test suite for CCDash Core Remediation Phase 4:
- T4-005: Freshness — new JSONL linked within one watcher cycle (no restart)
- T4-006: No-global-scan assertion — watcher hot path with incremental rebuild enabled
          does NOT invoke _rebuild_entity_links directly; only rebuild_links_for_entities is called
- T4-004: Config default is True
- T4-002: Deferred rebuild when no session IDs resolved (orphan/empty JSONL)
- T4-007: document_linking.session_family_scope_key helper

AC references:
  AC-T4-002 — family-scoped rebuild, no-op when no IDs, no global fallback
  AC-T4-003 — _rebuild_entity_links NOT invoked on hot path when flag=True
  AC-T4-004 — config default is True; env override disables it
  AC-T4-005 — sync_changed_files drives scoped rebuild within one cycle
  AC-T4-006 — spy/patch proof: global scan absent, scoped rebuild called once
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_session_jsonl(session_id: str = "sess-abc123") -> str:
    """Minimal JSONL content representing a parsed session."""
    entry = {
        "type": "system",
        "message": {
            "role": "system",
            "content": [{"type": "text", "text": "Agent session start."}],
        },
        "session_id": session_id,
        "uuid": session_id,
    }
    return json.dumps(entry) + "\n"


def _make_engine_stub():
    """
    Build a minimal SyncEngine stub using SyncEngine.__new__ so we can
    inject mocked dependencies without a live DB.

    We import SyncEngine here (inside the function) so that import errors
    are turned into test errors rather than collection errors.
    """
    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine.__new__(SyncEngine)
    # Minimal attributes referenced by sync_changed_files
    engine._linking_logic_version = "test-1"
    engine._rglob_cache = {}
    engine._source_identity_policy = None

    # Mock all repo attributes that sync_changed_files touches
    engine.sync_repo = Mock()
    engine.session_repo = Mock()
    engine.document_repo = Mock()
    engine.task_repo = Mock()
    engine.feature_repo = Mock()
    engine.link_repo = Mock()
    engine.analytics_repo = Mock()
    engine.scan_manifest_repo = Mock()

    # session_repo.list_by_source returns empty by default (overridden per test)
    engine.session_repo.list_by_source = AsyncMock(return_value=[])
    engine.session_repo.delete_by_source = AsyncMock()
    engine.session_repo.delete_relationships_for_source = AsyncMock()

    # sync_repo stubs
    engine.sync_repo.get_sync_state = AsyncMock(return_value=None)
    engine.sync_repo.upsert_sync_state = AsyncMock()
    engine.sync_repo.delete_sync_state = AsyncMock()

    # document/task/feature stubs
    engine.document_repo.delete_by_source = AsyncMock()
    engine.task_repo.delete_by_source = AsyncMock()
    engine.task_repo.list_by_feature = AsyncMock(return_value=[])
    engine.feature_repo.list_all = AsyncMock(return_value=[])

    # link_repo stubs
    engine.link_repo.delete_auto_links = AsyncMock()
    engine.link_repo.upsert = AsyncMock()
    engine.link_repo.rebuild_for_entities = AsyncMock(
        return_value={"entities_processed": 1, "auto_links_rebuilt": 0}
    )

    return engine


# ── T4-004: Config default ────────────────────────────────────────────────────


class TestConfigDefaultTrue(unittest.TestCase):
    """AC-T4-004: CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED defaults to True."""

    def test_default_is_true_when_env_unset(self) -> None:
        """Import config with the env var absent → default must be True."""
        import importlib
        import sys

        # Strip env var if present, then reload config
        env_backup = os.environ.pop("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED", None)
        try:
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config as cfg

            self.assertTrue(
                cfg.INCREMENTAL_LINK_REBUILD_ENABLED,
                "INCREMENTAL_LINK_REBUILD_ENABLED must default to True (Phase 4 flip)",
            )
        finally:
            if env_backup is not None:
                os.environ["CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED"] = env_backup
            # Restore original module
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config  # re-import so other tests see a clean module

    def test_env_override_false_disables_flag(self) -> None:
        """AC-T4-004: setting CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED=false disables it."""
        import importlib
        import sys

        env_backup = os.environ.get("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED")
        try:
            os.environ["CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED"] = "false"
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config as cfg

            self.assertFalse(cfg.INCREMENTAL_LINK_REBUILD_ENABLED)
        finally:
            if env_backup is not None:
                os.environ["CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED"] = env_backup
            else:
                os.environ.pop("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED", None)
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config  # noqa: F401

    def test_env_override_zero_disables_flag(self) -> None:
        """AC-T4-004: setting CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED=0 disables it."""
        import importlib
        import sys

        env_backup = os.environ.get("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED")
        try:
            os.environ["CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED"] = "0"
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config as cfg

            self.assertFalse(cfg.INCREMENTAL_LINK_REBUILD_ENABLED)
        finally:
            if env_backup is not None:
                os.environ["CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED"] = env_backup
            else:
                os.environ.pop("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED", None)
            if "backend.config" in sys.modules:
                del sys.modules["backend.config"]
            import backend.config  # noqa: F401


# ── T4-007: document_linking.session_family_scope_key ────────────────────────


class TestSessionFamilyScopeKey(unittest.TestCase):
    """AC-T4-007 helper: session_family_scope_key returns a stable project/stem key."""

    def setUp(self) -> None:
        from backend.document_linking import session_family_scope_key
        self._fn = session_family_scope_key

    def test_returns_project_slash_stem(self) -> None:
        result = self._fn("/data/sessions/abc123.jsonl", "proj-1")
        self.assertEqual(result, "proj-1/abc123")

    def test_returns_empty_for_blank_path(self) -> None:
        result = self._fn("", "proj-1")
        self.assertEqual(result, "")

    def test_returns_empty_for_hidden_file(self) -> None:
        result = self._fn("/data/.hidden.jsonl", "proj-1")
        self.assertEqual(result, "")

    def test_project_id_appears_first(self) -> None:
        result = self._fn("sessions/my-session.jsonl", "my-project")
        self.assertTrue(result.startswith("my-project/"))

    def test_stem_without_extension(self) -> None:
        result = self._fn("s/deep/path/session-456.jsonl", "p")
        self.assertIn("session-456", result)
        self.assertNotIn(".jsonl", result)


# ── T4-006: No global scan on hot path ───────────────────────────────────────


class TestNoGlobalScanOnHotPath(unittest.IsolatedAsyncioTestCase):
    """AC-T4-003 / AC-T4-006: with INCREMENTAL_LINK_REBUILD_ENABLED=True, the watcher
    hot path does NOT call _rebuild_entity_links directly; only rebuild_links_for_entities
    is invoked (scoped path).

    Proof method: spy both methods; assert global NOT called, scoped called once.
    """

    async def asyncSetUp(self) -> None:
        self.engine = _make_engine_stub()
        # Set up a temp sessions dir with a real JSONL file
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self._tmp.name) / "sessions"
        self.sessions_dir.mkdir()
        self.docs_dir = Path(self._tmp.name) / "docs"
        self.docs_dir.mkdir()
        self.progress_dir = Path(self._tmp.name) / "progress"
        self.progress_dir.mkdir()
        self.jsonl_path = self.sessions_dir / "session-test.jsonl"
        self.jsonl_path.write_text(_make_session_jsonl("sess-test-001"), encoding="utf-8")

        # session_repo returns our test session for the sync key
        self.engine.session_repo.list_by_source = AsyncMock(
            return_value=[{"id": "sess-test-001"}]
        )

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_global_rebuild_not_called_scoped_rebuild_called_once(self) -> None:
        """
        AC-T4-006: With flag=True, a single JSONL watcher event must:
        - Call rebuild_links_for_entities exactly once (scoped path)
        - NOT call _rebuild_entity_links directly (no global scan)
        """
        from backend.db.sync_engine import SyncEngine

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 1, "auto_links_rebuilt": 0, "operation_id": "op-1"}
        )

        # Stub out all the methods sync_changed_files calls internally
        self.engine._sync_single_session = AsyncMock(return_value=True)
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:sessions/session-test.jsonl")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            changed_files = [("modified", self.jsonl_path)]
            await self.engine.sync_changed_files(
                "proj-1",
                changed_files,
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # AC-T4-006 core assertion: global rebuild NOT called
        global_rebuild_mock.assert_not_called()

        # AC-T4-006 core assertion: scoped rebuild called exactly once
        scoped_rebuild_mock.assert_called_once()
        _call_args = scoped_rebuild_mock.call_args
        # Should be called with project_id, "session", [session_ids], trigger=...
        self.assertEqual(_call_args.args[0], "proj-1")
        self.assertEqual(_call_args.args[1], "session")
        self.assertIn("sess-test-001", _call_args.args[2])

    async def test_global_rebuild_called_when_flag_disabled(self) -> None:
        """
        AC-T4-003 fallback: when flag=False, the global _rebuild_entity_links IS called
        (existing behaviour preserved as the escape hatch).
        """
        from backend.db.sync_engine import SyncEngine

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 0, "auto_links_rebuilt": 0, "operation_id": "op-2"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=True)
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:sessions/session-test.jsonl")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = False

            changed_files = [("modified", self.jsonl_path)]
            await self.engine.sync_changed_files(
                "proj-1",
                changed_files,
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # Flag=False → full rebuild path
        global_rebuild_mock.assert_called_once()
        scoped_rebuild_mock.assert_not_called()

    async def test_no_global_scan_when_version_stale_but_flag_on(self) -> None:
        """
        When link-logic version is stale AND flag=True, the full rebuild path runs
        (version staleness overrides the scoped path — correct behaviour).
        """
        from backend.db.sync_engine import SyncEngine

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 0, "auto_links_rebuilt": 0, "operation_id": "op-3"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=True)
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "old-version"})
        self.engine._is_link_logic_version_stale = Mock(return_value=True)  # stale!
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:sessions/session-test.jsonl")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            changed_files = [("modified", self.jsonl_path)]
            await self.engine.sync_changed_files(
                "proj-1",
                changed_files,
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # Version stale → full rebuild, even with flag=True
        global_rebuild_mock.assert_called_once()
        scoped_rebuild_mock.assert_not_called()


# ── T4-005: Freshness — no restart needed ────────────────────────────────────


class TestLinkFreshnessWithinOneCycle(unittest.IsolatedAsyncioTestCase):
    """AC-T4-005: New JSONL written under watched path → linked within one cycle.

    Uses deterministic watcher tick (direct sync_changed_files call) rather
    than wall-clock sleep to avoid flakiness.
    """

    async def asyncSetUp(self) -> None:
        self.engine = _make_engine_stub()
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self._tmp.name) / "sessions"
        self.sessions_dir.mkdir()
        self.docs_dir = Path(self._tmp.name) / "docs"
        self.docs_dir.mkdir()
        self.progress_dir = Path(self._tmp.name) / "progress"
        self.progress_dir.mkdir()

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_new_jsonl_triggers_scoped_rebuild_within_one_cycle(self) -> None:
        """
        AC-T4-005: Simulate 'watcher fires once' by calling sync_changed_files
        directly with the new JSONL path.  Assert:
          - rebuild_links_for_entities called (session becomes linked)
          - No server restart required (sync_changed_files completes without error)
        """
        from backend.db.sync_engine import SyncEngine

        session_id = "sess-fresh-001"
        jsonl_path = self.sessions_dir / "fresh-session.jsonl"
        jsonl_path.write_text(_make_session_jsonl(session_id), encoding="utf-8")

        # Return session from DB (as if just persisted)
        sync_key = f"session:{session_id}"
        self.engine.session_repo.list_by_source = AsyncMock(
            return_value=[{"id": session_id}]
        )

        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 1, "auto_links_rebuilt": 2, "operation_id": "op-fresh"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=True)
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value=sync_key)
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch.object(SyncEngine, "_rebuild_entity_links", AsyncMock(return_value={"created": 0})),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            # Simulate one watcher tick (deterministic, no wall-clock sleep)
            stats = await self.engine.sync_changed_files(
                "proj-1",
                [("modified", jsonl_path)],
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # Session was rebuilt within this single cycle
        scoped_rebuild_mock.assert_called_once()
        self.assertEqual(stats["links_created"], 2)

    async def test_empty_jsonl_defers_but_does_not_raise(self) -> None:
        """
        AC-T4-002 resilience: if a JSONL yields no session IDs (empty/malformed),
        sync_changed_files completes without error and performs NO global rebuild.
        """
        from backend.db.sync_engine import SyncEngine

        jsonl_path = self.sessions_dir / "empty-session.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        # list_by_source returns nothing (no session persisted from empty file)
        self.engine.session_repo.list_by_source = AsyncMock(return_value=[])

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 0, "auto_links_rebuilt": 0, "operation_id": "op-e"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=True)  # file processed but empty
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:sessions/empty-session.jsonl")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            stats = await self.engine.sync_changed_files(
                "proj-1",
                [("modified", jsonl_path)],
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # AC-T4-002: no global rebuild (no fallback to global scan)
        global_rebuild_mock.assert_not_called()
        # AC-T4-002: scoped rebuild is NO-OP (no IDs)
        scoped_rebuild_mock.assert_not_called()
        # No error, stats are clean
        self.assertEqual(stats["links_created"], 0)


# ── T4-002: Deferred rebuild for orphan JSONL ─────────────────────────────────


class TestDeferredRebuildForOrphanJsonl(unittest.IsolatedAsyncioTestCase):
    """AC-T4-002: When a JSONL cannot be resolved to a family, rebuild is deferred
    (no-op), NOT a fallback to the global scan.
    """

    async def asyncSetUp(self) -> None:
        self.engine = _make_engine_stub()
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self._tmp.name) / "sessions"
        self.sessions_dir.mkdir()
        self.docs_dir = Path(self._tmp.name) / "docs"
        self.docs_dir.mkdir()
        self.progress_dir = Path(self._tmp.name) / "progress"
        self.progress_dir.mkdir()

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_deferred_does_not_call_global_or_scoped_rebuild(self) -> None:
        from backend.db.sync_engine import SyncEngine

        orphan_jsonl = self.sessions_dir / "orphan.jsonl"
        orphan_jsonl.write_text('{"type":"unknown"}\n', encoding="utf-8")

        # No session ID in DB for this file
        self.engine.session_repo.list_by_source = AsyncMock(return_value=[])

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 0, "auto_links_rebuilt": 0, "operation_id": "op-d"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=True)
        self.engine._sync_single_document = AsyncMock(return_value=False)
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:sessions/orphan.jsonl")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            await self.engine.sync_changed_files(
                "proj-1",
                [("modified", orphan_jsonl)],
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # Neither rebuild path should fire — deferred no-op
        global_rebuild_mock.assert_not_called()
        scoped_rebuild_mock.assert_not_called()


# ── T4-006: No-global-scan with doc changes ───────────────────────────────────


class TestNoGlobalScanForDocChanges(unittest.IsolatedAsyncioTestCase):
    """AC-T4-003: When a .md file changes (not a session JSONL), the scoped rebuild
    is still NOT a global filesystem scan — it routes through the same flag check.

    When flag=True and the change is a .md doc (not a JSONL), the scoped path
    has no session IDs → no-op / deferred.  When flag=False the global path runs.
    """

    async def asyncSetUp(self) -> None:
        self.engine = _make_engine_stub()
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self._tmp.name) / "sessions"
        self.sessions_dir.mkdir()
        self.docs_dir = Path(self._tmp.name) / "docs"
        self.docs_dir.mkdir()
        self.progress_dir = Path(self._tmp.name) / "progress"
        self.progress_dir.mkdir()

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_doc_change_with_flag_on_does_not_invoke_global_rebuild(self) -> None:
        from backend.db.sync_engine import SyncEngine

        doc_path = self.docs_dir / "feature.md"
        doc_path.write_text("# Feature doc\n", encoding="utf-8")

        global_rebuild_mock = AsyncMock(return_value={"created": 0})
        scoped_rebuild_mock = AsyncMock(
            return_value={"entities_processed": 0, "auto_links_rebuilt": 0, "operation_id": "op-doc"}
        )

        self.engine._sync_single_session = AsyncMock(return_value=False)
        self.engine._sync_single_document = AsyncMock(return_value=True)  # doc synced
        self.engine._sync_single_progress = AsyncMock(return_value=False)
        self.engine._sync_single_test_source = AsyncMock(return_value={"synced": 0})
        self.engine._sync_features = AsyncMock(return_value={"synced": 0})
        self.engine._load_link_state = AsyncMock(return_value={"logicVersion": "test-1"})
        self.engine._is_link_logic_version_stale = Mock(return_value=False)
        self.engine._save_link_state = AsyncMock()
        self.engine._match_source_for_path = Mock(return_value=None)
        self.engine._canonical_source_key = Mock(return_value="sync:proj-1:docs/feature.md")
        self.engine._build_git_doc_dates = Mock(return_value=({}, set()))
        self.engine._start_operation = AsyncMock(return_value=None)
        self.engine._update_operation = AsyncMock()
        self.engine._finish_operation = AsyncMock()
        self.engine.session_repo.list_by_source = AsyncMock(return_value=[])

        with (
            patch.object(SyncEngine, "_rebuild_entity_links", global_rebuild_mock),
            patch.object(SyncEngine, "rebuild_links_for_entities", scoped_rebuild_mock),
            patch("backend.db.sync_engine.config") as mock_config,
            patch("backend.db.sync_engine.publish_feature_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.publish_planning_invalidation", AsyncMock()),
            patch("backend.db.sync_engine.observability"),
        ):
            mock_config.INCREMENTAL_LINK_REBUILD_ENABLED = True

            await self.engine.sync_changed_files(
                "proj-1",
                [("modified", doc_path)],
                self.sessions_dir,
                self.docs_dir,
                self.progress_dir,
            )

        # Doc-only change: no JSONL → no session IDs → no-op / deferred, no global scan
        global_rebuild_mock.assert_not_called()
        scoped_rebuild_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
