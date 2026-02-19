import unittest

from backend.link_audit import analyze_suspect_links


class LinkAuditTests(unittest.TestCase):
    def test_analyze_suspects_flags_high_fanout_and_mismatch(self) -> None:
        rows = [
            {
                "feature_id": "marketplace-source-detection-improvements-v1",
                "session_id": "S-1",
                "confidence": 0.8,
                "metadata": {
                    "title": "Quick Feature - unrelated-feature",
                    "ambiguityShare": 0.42,
                    "commands": ["/dev:quick-feature"],
                    "signals": [{"type": "command_args_path", "path": "docs/project_plans/implementation_plans/features/unrelated-feature-v1.md"}],
                },
            }
        ]
        fanout = {"S-1": 20}

        suspects = analyze_suspect_links(rows, fanout, primary_floor=0.55, fanout_floor=10)
        self.assertEqual(len(suspects), 1)
        self.assertIn("high_fanout(20)", suspects[0].reason)
        self.assertIn("primary_like_command_path_mismatch", suspects[0].reason)

    def test_analyze_suspects_ignores_good_match(self) -> None:
        rows = [
            {
                "feature_id": "marketplace-source-detection-improvements-v1",
                "session_id": "S-2",
                "confidence": 0.9,
                "metadata": {
                    "title": "Execute Phase 1 - marketplace-source-detection-improvements-v1",
                    "ambiguityShare": 0.9,
                    "commands": ["/dev:execute-phase"],
                    "signals": [{"type": "command_args_path", "path": "docs/project_plans/implementation_plans/features/marketplace-source-detection-improvements-v1.md"}],
                },
            }
        ]
        fanout = {"S-2": 1}

        suspects = analyze_suspect_links(rows, fanout, primary_floor=0.55, fanout_floor=10)
        self.assertEqual(suspects, [])


if __name__ == "__main__":
    unittest.main()
