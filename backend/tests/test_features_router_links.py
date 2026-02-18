import unittest

from backend.routers import features as features_router


class FeatureRouterLinkHelpersTests(unittest.TestCase):
    def test_normalize_link_commands_filters_noise_and_prioritizes(self) -> None:
        commands = ["/clear", "/model", "/fix:debug", "/dev:execute-phase", "/dev:quick-feature"]

        normalized = features_router._normalize_link_commands(commands)

        self.assertEqual(normalized[0], "/dev:execute-phase")
        self.assertNotIn("/clear", normalized)
        self.assertNotIn("/model", normalized)

    def test_normalize_link_title_rewrites_noise_title(self) -> None:
        title = features_router._normalize_link_title(
            "/clear - marketplace-source-detection-improvements-v1",
            ["/dev:execute-phase"],
            "marketplace-source-detection-improvements-v1",
        )

        self.assertEqual(title, "/dev:execute-phase - marketplace-source-detection-improvements-v1")

    def test_primary_link_accepts_key_command_with_moderate_confidence(self) -> None:
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.55,
            {"file_read"},
            ["/dev:execute-phase"],
        )

        self.assertTrue(is_primary)


if __name__ == "__main__":
    unittest.main()
