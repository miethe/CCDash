import unittest

from backend.session_mappings import (
    classify_bash_command,
    classify_key_command,
    classify_session_key_metadata,
    default_session_mappings,
)


class SessionMappingsTests(unittest.TestCase):
    def test_defaults_include_key_command_mapping(self) -> None:
        mappings = default_session_mappings()
        execute_phase = next((item for item in mappings if item.get("id") == "key-dev-execute-phase"), None)
        self.assertIsNotNone(execute_phase)
        assert execute_phase is not None
        self.assertEqual(execute_phase.get("mappingType"), "key_command")
        self.assertEqual(execute_phase.get("sessionTypeLabel"), "Phased Execution")

    def test_classify_key_command_extracts_related_fields(self) -> None:
        mappings = default_session_mappings()
        classified = classify_key_command(
            "/dev:execute-phase",
            "4 docs/project_plans/implementation_plans/features/example-v1.md",
            {},
            mappings,
        )

        self.assertIsNotNone(classified)
        assert classified is not None
        self.assertEqual(classified.get("sessionTypeLabel"), "Phased Execution")
        self.assertEqual(classified.get("relatedPhases"), ["4"])
        fields = {item["id"]: item["value"] for item in classified.get("fields", [])}
        self.assertEqual(fields.get("related-command"), "/dev:execute-phase")
        self.assertEqual(fields.get("related-phases"), "4")

    def test_classify_session_key_metadata_uses_highest_priority_match(self) -> None:
        mappings = default_session_mappings()
        result = classify_session_key_metadata(
            [
                {"name": "/dev:quick-feature", "args": "foo", "parsedCommand": {}},
                {"name": "/dev:execute-phase", "args": "2 docs/project_plans/implementation_plans/features/example-v1.md", "parsedCommand": {}},
            ],
            mappings,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("sessionTypeId"), "key-dev-execute-phase")
        self.assertEqual(result.get("sessionTypeLabel"), "Phased Execution")

    def test_classify_bash_command_ignores_key_command_rules(self) -> None:
        mappings = default_session_mappings()
        self.assertIsNone(classify_bash_command("/dev:execute-phase 1 plan.md", mappings))


if __name__ == "__main__":
    unittest.main()
