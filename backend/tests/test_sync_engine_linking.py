import unittest

from backend.db.sync_engine import (
    SyncEngine,
    _extract_tagged_commands_from_message,
    _select_linking_commands,
    _select_preferred_command_event,
)


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
        should_rebuild, reason = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state={"logicVersion": "1"},
            stats={
                "sessions_synced": 0,
                "documents_synced": 0,
                "tasks_synced": 0,
                "features_synced": 0,
            },
        )

        self.assertTrue(should_rebuild)
        self.assertEqual(reason, "logic_version_changed")

    def test_should_skip_rebuild_after_full_sync_when_unchanged_and_version_matches(self) -> None:
        engine = self._build_engine_stub("1")
        should_rebuild, reason = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state={"logicVersion": "1"},
            stats={
                "sessions_synced": 0,
                "documents_synced": 0,
                "tasks_synced": 0,
                "features_synced": 0,
            },
        )

        self.assertFalse(should_rebuild)
        self.assertEqual(reason, "up_to_date")


if __name__ == "__main__":
    unittest.main()
