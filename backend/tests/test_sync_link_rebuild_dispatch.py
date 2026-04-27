"""Tests for SyncEngine._dispatch_link_rebuild (BE-205 / BE-206).

Covers all four scope branches:
  1. kind="full"                               → _rebuild_entity_links called once
  2. kind="entities_changed" + non-empty ids  → rebuild_links_for_entities called
  3. kind="entities_changed" + empty ids      → falls back to full rebuild + WARNING
  4. kind="none"                               → neither rebuild method called

BE-206 flag tests:
  5. flag=False + entities_changed            → coerces to full rebuild; rebuild_links_for_entities NOT called
  6. flag=True  + entities_changed            → routes to rebuild_links_for_entities (incremental path)
"""

import logging
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import backend.config as _config
from backend.db.sync_engine import RebuildScope, SyncEngine


def _make_engine() -> SyncEngine:
    """Return a minimal SyncEngine instance with async mocks for the two rebuild methods."""
    engine = SyncEngine.__new__(SyncEngine)
    engine._linking_logic_version = "1"
    engine._rglob_cache = {}

    # Repos needed for rebuild_links_for_entities's operation tracking; stub them out.
    engine.session_repo = MagicMock()
    engine.document_repo = MagicMock()
    engine.task_repo = MagicMock()
    engine.feature_repo = MagicMock()
    engine.link_repo = MagicMock()
    engine.sync_repo = MagicMock()
    engine.session_message_repo = MagicMock()

    # Stub the two concrete rebuild methods that _dispatch_link_rebuild calls.
    engine._rebuild_entity_links = AsyncMock(return_value={"created": 7})
    engine.rebuild_links_for_entities = AsyncMock(
        return_value={"entities_processed": 2, "auto_links_rebuilt": 3}
    )

    # Stub internal operation helpers used by the dispatch helper (no-op).
    engine._start_operation = AsyncMock(return_value="op-fake")
    engine._update_operation = AsyncMock()
    engine._finish_operation = AsyncMock()

    return engine


class TestDispatchLinkRebuildFull(unittest.IsolatedAsyncioTestCase):
    """kind='full' → _rebuild_entity_links called; rebuild_links_for_entities NOT called."""

    async def test_full_scope_calls_full_rebuild(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="full")

        result = await engine._dispatch_link_rebuild(scope, "proj-1")

        engine._rebuild_entity_links.assert_awaited_once()
        engine.rebuild_links_for_entities.assert_not_awaited()
        self.assertEqual(result["created"], 7)

    async def test_full_scope_passes_dirs_through(self) -> None:
        engine = _make_engine()
        docs = Path("/tmp/docs")
        prog = Path("/tmp/progress")
        scope = RebuildScope(kind="full")

        await engine._dispatch_link_rebuild(scope, "proj-1", docs_dir=docs, progress_dir=prog)

        _, kwargs = engine._rebuild_entity_links.call_args
        self.assertEqual(kwargs.get("docs_dir") or engine._rebuild_entity_links.call_args[0][1], docs)


class TestDispatchLinkRebuildEntitiesChanged(unittest.IsolatedAsyncioTestCase):
    """kind='entities_changed' with non-empty ids → rebuild_links_for_entities called (flag=True)."""

    async def test_non_empty_ids_routes_to_scoped_rebuild(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=["sess-abc", "sess-def"])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            result = await engine._dispatch_link_rebuild(scope, "proj-2")

        engine.rebuild_links_for_entities.assert_awaited_once()
        engine._rebuild_entity_links.assert_not_awaited()
        self.assertEqual(result["auto_links_rebuilt"], 3)

    async def test_non_empty_ids_passes_correct_ids(self) -> None:
        engine = _make_engine()
        ids = ["sess-111", "sess-222", "sess-333"]
        scope = RebuildScope(kind="entities_changed", entity_ids=ids)

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            await engine._dispatch_link_rebuild(scope, "proj-2")

        call_args = engine.rebuild_links_for_entities.call_args
        # positional: (project_id, entity_type, ids)
        passed_ids = call_args[0][2] if len(call_args[0]) >= 3 else call_args[1].get("ids")
        self.assertEqual(passed_ids, ids)


class TestDispatchLinkRebuildEntitiesChangedEmptyFallback(unittest.IsolatedAsyncioTestCase):
    """kind='entities_changed' with empty ids → falls back to full rebuild + WARNING log (flag=True)."""

    async def test_empty_ids_falls_back_to_full_rebuild(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=[])

        # flag=True so the guard passes and the empty-ids branch is reached
        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            result = await engine._dispatch_link_rebuild(scope, "proj-3")

        engine._rebuild_entity_links.assert_awaited_once()
        engine.rebuild_links_for_entities.assert_not_awaited()
        self.assertEqual(result["created"], 7)

    async def test_empty_ids_emits_warning(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=[])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            with self.assertLogs("ccdash.sync", level=logging.WARNING) as cm:
                await engine._dispatch_link_rebuild(scope, "proj-3")

        warning_lines = [line for line in cm.output if "WARNING" in line]
        self.assertTrue(warning_lines, "Expected at least one WARNING log line")
        self.assertTrue(
            any("entities_changed" in line for line in warning_lines),
            "Warning should mention scope=entities_changed",
        )

    async def test_none_entity_ids_also_falls_back(self) -> None:
        """entity_ids=None is treated the same as empty list (flag=True to reach that branch)."""
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=None)

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            result = await engine._dispatch_link_rebuild(scope, "proj-3")

        engine._rebuild_entity_links.assert_awaited_once()
        engine.rebuild_links_for_entities.assert_not_awaited()
        self.assertIn("created", result)


class TestDispatchLinkRebuildNone(unittest.IsolatedAsyncioTestCase):
    """kind='none' → neither rebuild method called; zero stats returned."""

    async def test_none_scope_skips_rebuild(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="none")

        result = await engine._dispatch_link_rebuild(scope, "proj-4")

        engine._rebuild_entity_links.assert_not_awaited()
        engine.rebuild_links_for_entities.assert_not_awaited()
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["auto_links_rebuilt"], 0)


class TestDispatchLinkRebuildIncrementalFlagOff(unittest.IsolatedAsyncioTestCase):
    """BE-206: flag=False + entities_changed → coerces to full rebuild."""

    async def test_flag_off_entities_changed_coerces_to_full(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=["sess-aaa", "sess-bbb"])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", False):
            result = await engine._dispatch_link_rebuild(scope, "proj-flag-off")

        engine._rebuild_entity_links.assert_awaited_once()
        engine.rebuild_links_for_entities.assert_not_awaited()
        self.assertIn("created", result)

    async def test_flag_off_emits_info_log(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=["sess-xyz"])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", False):
            with self.assertLogs("ccdash.sync", level=logging.INFO) as cm:
                await engine._dispatch_link_rebuild(scope, "proj-flag-off-log")

        self.assertTrue(
            any("incremental_rebuild_gated_off" in line for line in cm.output),
            "Expected info log mentioning incremental_rebuild_gated_off",
        )


class TestDispatchLinkRebuildIncrementalFlagOn(unittest.IsolatedAsyncioTestCase):
    """BE-206: flag=True + entities_changed → incremental path (rebuild_links_for_entities)."""

    async def test_flag_on_entities_changed_routes_to_scoped_rebuild(self) -> None:
        engine = _make_engine()
        ids = ["sess-111", "sess-222"]
        scope = RebuildScope(kind="entities_changed", entity_ids=ids)

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            result = await engine._dispatch_link_rebuild(scope, "proj-flag-on")

        engine.rebuild_links_for_entities.assert_awaited_once()
        engine._rebuild_entity_links.assert_not_awaited()
        self.assertEqual(result["auto_links_rebuilt"], 3)

    async def test_flag_on_passes_entity_ids(self) -> None:
        engine = _make_engine()
        ids = ["sess-aaa", "sess-bbb", "sess-ccc"]
        scope = RebuildScope(kind="entities_changed", entity_ids=ids)

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            await engine._dispatch_link_rebuild(scope, "proj-flag-on-ids")

        call_args = engine.rebuild_links_for_entities.call_args
        passed_ids = call_args[0][2] if len(call_args[0]) >= 3 else call_args[1].get("ids")
        self.assertEqual(passed_ids, ids)


class TestDispatchLinkRebuildScopeMetric(unittest.IsolatedAsyncioTestCase):
    """OBS-403: record_link_rebuild_scope is called with the correct label for every dispatch path."""

    _PATCH_TARGET = "backend.observability.record_link_rebuild_scope"

    async def test_full_scope_records_full(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="full")

        with patch(self._PATCH_TARGET) as mock_record:
            await engine._dispatch_link_rebuild(scope, "proj-metric-full")

        mock_record.assert_called_once_with("full")

    async def test_none_scope_records_none(self) -> None:
        engine = _make_engine()
        scope = RebuildScope(kind="none")

        with patch(self._PATCH_TARGET) as mock_record:
            await engine._dispatch_link_rebuild(scope, "proj-metric-none")

        mock_record.assert_called_once_with("none")

    async def test_entities_changed_flag_off_records_full(self) -> None:
        """When BE-206 flag is off, entities_changed coerces to full rebuild — records 'full'."""
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=["sess-aaa"])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", False):
            with patch(self._PATCH_TARGET) as mock_record:
                await engine._dispatch_link_rebuild(scope, "proj-metric-flag-off")

        mock_record.assert_called_once_with("full")

    async def test_entities_changed_empty_ids_records_none(self) -> None:
        """entities_changed with empty ids records 'none' (no entity scope executed)."""
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=[])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            with patch(self._PATCH_TARGET) as mock_record:
                await engine._dispatch_link_rebuild(scope, "proj-metric-empty-ids")

        mock_record.assert_called_once_with("none")

    async def test_entities_changed_non_empty_ids_records_entities_changed(self) -> None:
        """entities_changed with non-empty ids records 'entities_changed'."""
        engine = _make_engine()
        scope = RebuildScope(kind="entities_changed", entity_ids=["sess-1", "sess-2"])

        with patch.object(_config, "INCREMENTAL_LINK_REBUILD_ENABLED", True):
            with patch(self._PATCH_TARGET) as mock_record:
                await engine._dispatch_link_rebuild(scope, "proj-metric-scoped")

        mock_record.assert_called_once_with("entities_changed")


if __name__ == "__main__":
    unittest.main()
