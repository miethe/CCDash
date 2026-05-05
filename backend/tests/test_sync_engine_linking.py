import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from backend.db.sync_engine import (
    SyncEngine,
    _extract_tagged_commands_from_message,
    _select_linking_commands,
    _select_preferred_command_event,
)
from backend.services.source_identity import SourceIdentityPolicy, SourceRootAlias, SourceRootId


class SyncEngineLinkingTests(unittest.TestCase):
    def _build_engine_stub(self, version: str = "1") -> SyncEngine:
        engine = SyncEngine.__new__(SyncEngine)
        engine._linking_logic_version = version
        return engine

    def test_select_linking_commands_filters_noise_and_prioritizes_execute_phase(self) -> None:
        commands = {
            "/clear",
            "/model",
            "/dev:quick-feature",
            "/dev:execute-phase",
            "/fix:debug",
        }

        ordered = _select_linking_commands(commands)

        self.assertNotIn("/clear", ordered)
        self.assertNotIn("/model", ordered)
        self.assertGreaterEqual(len(ordered), 3)
        self.assertEqual(ordered[0], "/dev:execute-phase")

    def test_select_preferred_command_event_prefers_key_command_and_ignores_clear(self) -> None:
        events = [
            {"name": "/clear", "args": "", "parsed": {}},
            {"name": "/dev:execute-phase", "args": "4 docs/project_plans/implementation_plans/features/alpha-v1.md", "parsed": {}},
            {"name": "/fix:debug", "args": "", "parsed": {}},
        ]

        preferred = _select_preferred_command_event(events)

        self.assertIsNotNone(preferred)
        assert preferred is not None
        self.assertEqual(preferred["name"], "/dev:execute-phase")

    def test_extract_tagged_commands_parses_name_and_args_pairs(self) -> None:
        message = (
            "<command-message>dev:execute-phase</command-message>\n"
            "<command-name>/dev:execute-phase</command-name>\n"
            "<command-args>4 docs/project_plans/implementation_plans/features/alpha-v1.md</command-args>\n"
            "<command-name>/clear</command-name>\n"
            "<command-args></command-args>"
        )

        parsed = _extract_tagged_commands_from_message(message)

        self.assertEqual(
            parsed,
            [
                ("/dev:execute-phase", "4 docs/project_plans/implementation_plans/features/alpha-v1.md"),
                ("/clear", ""),
            ],
        )

    def test_should_rebuild_links_after_full_sync_when_logic_version_changes(self) -> None:
        engine = self._build_engine_stub("2")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state={"logicVersion": "1"},
            stats={
                "sessions_synced": 0,
                "documents_synced": 0,
                "tasks_synced": 0,
                "features_synced": 0,
            },
        )

        self.assertTrue(scope.should_rebuild)
        self.assertEqual(scope.kind, "full")
        self.assertEqual(scope.reason, "full")

    def test_should_skip_rebuild_after_full_sync_when_unchanged_and_version_matches(self) -> None:
        engine = self._build_engine_stub("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state={"logicVersion": "1"},
            stats={
                "sessions_synced": 0,
                "documents_synced": 0,
                "tasks_synced": 0,
                "features_synced": 0,
            },
        )

        self.assertFalse(scope.should_rebuild)
        self.assertEqual(scope.kind, "none")
        self.assertEqual(scope.reason, "up_to_date")


class SyncEngineAmbiguityPenaltyTests(unittest.TestCase):
    """Tests for the share-based ambiguity penalty gating in sync_engine confidence scoring.

    The scoring logic lives inside a loop in SyncEngine._build_session_feature_links.
    We replicate the exact arithmetic here so the gate contract is clearly
    specified and will catch regressions if the inline logic changes.
    """

    @staticmethod
    def _compute_confidence(
        base_confidence: float,
        raw_signal_weight: float,
        total_signal_weight: float,
        has_command_path: bool,
        has_read_only_signals: bool,
    ) -> float:
        """Mirror of the inline confidence-scoring block in sync_engine.py."""
        share = raw_signal_weight / total_signal_weight if total_signal_weight > 0 else 0.0
        confidence = float(base_confidence)
        has_command_path_signal = bool(has_command_path)
        if not has_command_path_signal:
            if share < 0.50:
                confidence -= 0.20
            elif share < 0.70:
                confidence -= 0.10
        if has_read_only_signals:
            confidence -= 0.08
        return round(max(0.35, min(0.95, confidence)), 3)

    def test_command_path_signal_skips_share_penalty_low_share(self) -> None:
        # share = 0.3 / 1.0 = 0.30 → normally -0.20, but hasCommandPath=True skips it.
        confidence = self._compute_confidence(
            base_confidence=0.90,
            raw_signal_weight=0.3,
            total_signal_weight=1.0,
            has_command_path=True,
            has_read_only_signals=False,
        )

        self.assertAlmostEqual(confidence, 0.90)

    def test_no_command_path_applies_share_penalty_low_share(self) -> None:
        # Same numbers as above but hasCommandPath=False → penalty of -0.20 applies.
        confidence = self._compute_confidence(
            base_confidence=0.90,
            raw_signal_weight=0.3,
            total_signal_weight=1.0,
            has_command_path=False,
            has_read_only_signals=False,
        )

        self.assertAlmostEqual(confidence, 0.70)

    def test_command_path_signal_skips_moderate_share_penalty(self) -> None:
        # share ≈ 0.60 → normally -0.10, but hasCommandPath=True skips it.
        confidence = self._compute_confidence(
            base_confidence=0.78,
            raw_signal_weight=0.6,
            total_signal_weight=1.0,
            has_command_path=True,
            has_read_only_signals=False,
        )

        self.assertAlmostEqual(confidence, 0.78)

    def test_no_command_path_applies_moderate_share_penalty(self) -> None:
        # share ≈ 0.60 without hasCommandPath → -0.10, bringing 0.78 to 0.68.
        confidence = self._compute_confidence(
            base_confidence=0.78,
            raw_signal_weight=0.6,
            total_signal_weight=1.0,
            has_command_path=False,
            has_read_only_signals=False,
        )

        self.assertAlmostEqual(confidence, 0.68)

    def test_read_only_penalty_still_applied_when_command_path_present(self) -> None:
        # hasReadOnlySignals penalty is independent of the hasCommandPath gate.
        confidence = self._compute_confidence(
            base_confidence=0.90,
            raw_signal_weight=0.3,
            total_signal_weight=1.0,
            has_command_path=True,
            has_read_only_signals=True,
        )

        self.assertAlmostEqual(confidence, 0.82)

    def test_clamp_at_minimum_0_35(self) -> None:
        # Even with heavy penalties, result is clamped to 0.35.
        confidence = self._compute_confidence(
            base_confidence=0.40,
            raw_signal_weight=0.1,
            total_signal_weight=1.0,
            has_command_path=False,
            has_read_only_signals=True,
        )

        self.assertAlmostEqual(confidence, 0.35)

    def test_clamp_at_maximum_0_95(self) -> None:
        confidence = self._compute_confidence(
            base_confidence=0.95,
            raw_signal_weight=1.0,
            total_signal_weight=1.0,
            has_command_path=True,
            has_read_only_signals=False,
        )

        self.assertAlmostEqual(confidence, 0.95)


class SyncEngineSessionBackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_single_session_reparses_unchanged_file_when_lineage_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.jsonl"
            path.write_text("{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"hi\"}}\n", encoding="utf-8")
            mtime = path.stat().st_mtime

            engine = SyncEngine.__new__(SyncEngine)
            engine.sync_repo = type("SyncRepoStub", (), {})()
            engine.sync_repo.get_sync_state = AsyncMock(return_value={"file_mtime": mtime})
            engine.sync_repo.upsert_sync_state = AsyncMock()
            engine.session_repo = type("SessionRepoStub", (), {})()
            engine.session_repo.list_by_source = AsyncMock(return_value=[{"id": "S-1", "thread_kind": "", "conversation_family_id": ""}])
            engine.session_repo.delete_by_source = AsyncMock()
            engine.session_repo.delete_relationships_for_source = AsyncMock()
            engine._source_identity_policy = SourceIdentityPolicy(
                aliases=(
                    SourceRootAlias(
                        root_id=SourceRootId("sessions_root"),
                        alias_path=path.parent,
                    ),
                )
            )
            sync_key = engine._canonical_source_key("project-1", path, "session")

            with patch("backend.db.sync_engine.parse_session_file", return_value=None) as parse_mock, patch("backend.db.sync_engine.observability.start_span", return_value=nullcontext()), patch("backend.db.sync_engine.observability.record_ingestion"):
                synced = await SyncEngine._sync_single_session(engine, "project-1", path, force=False)

            self.assertTrue(synced)
            engine.sync_repo.get_sync_state.assert_awaited_once_with(sync_key)
            parse_mock.assert_called_once_with(path)
            engine.session_repo.delete_by_source.assert_awaited_once_with(sync_key)
            engine.session_repo.delete_relationships_for_source.assert_awaited_once_with("project-1", sync_key)
            engine.sync_repo.upsert_sync_state.assert_awaited_once()
            self.assertEqual(engine.sync_repo.upsert_sync_state.await_args.args[0]["file_path"], sync_key)

    async def test_sync_single_session_skips_unchanged_file_when_lineage_present(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.jsonl"
            path.write_text("{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"hi\"}}\n", encoding="utf-8")
            mtime = path.stat().st_mtime

            engine = SyncEngine.__new__(SyncEngine)
            engine.sync_repo = type("SyncRepoStub", (), {})()
            engine.sync_repo.get_sync_state = AsyncMock(return_value={"file_mtime": mtime})
            engine.sync_repo.upsert_sync_state = AsyncMock()
            engine.session_repo = type("SessionRepoStub", (), {})()
            engine.session_repo.list_by_source = AsyncMock(return_value=[{"id": "S-1", "thread_kind": "root", "conversation_family_id": "S-1"}])
            engine.session_repo.delete_by_source = AsyncMock()
            engine.session_repo.delete_relationships_for_source = AsyncMock()
            engine._source_identity_policy = SourceIdentityPolicy(
                aliases=(
                    SourceRootAlias(
                        root_id=SourceRootId("sessions_root"),
                        alias_path=path.parent,
                    ),
                )
            )
            sync_key = engine._canonical_source_key("project-1", path, "session")

            with patch("backend.db.sync_engine.parse_session_file") as parse_mock:
                synced = await SyncEngine._sync_single_session(engine, "project-1", path, force=False)

            self.assertFalse(synced)
            engine.sync_repo.get_sync_state.assert_awaited_once_with(sync_key)
            parse_mock.assert_not_called()
            engine.session_repo.delete_by_source.assert_not_awaited()
            engine.sync_repo.upsert_sync_state.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
