import unittest

from backend.db.sync_engine import (
    _extract_tagged_commands_from_message,
    _select_linking_commands,
    _select_preferred_command_event,
)


class SyncEngineLinkingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
