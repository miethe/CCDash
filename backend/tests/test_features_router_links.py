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

    def test_primary_link_does_not_promote_low_confidence_key_command(self) -> None:
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.55,
            {"file_read"},
            ["/dev:execute-phase"],
        )

        self.assertFalse(is_primary)

    def test_primary_link_accepts_high_confidence_command_path(self) -> None:
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.8,
            {"command_args_path"},
            ["/dev:execute-phase"],
        )

        self.assertTrue(is_primary)

    def test_primary_link_workflow_command_overrides_low_confidence(self) -> None:
        # confidence 0.68 is below both 0.75 and 0.9 gates, but command_args_path +
        # workflow verb should still promote to Primary.
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.68,
            {"command_args_path"},
            ["/dev:execute-phase phase 4 docs/plans/feature-v1.md"],
        )

        self.assertTrue(is_primary)

    def test_primary_link_workflow_command_no_prefix_variant(self) -> None:
        # "execute-phase foo" without any /dev: prefix should also match.
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.68,
            {"command_args_path"},
            ["execute-phase foo"],
        )

        self.assertTrue(is_primary)

    def test_primary_link_workflow_command_plan_feature_variant(self) -> None:
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.68,
            {"command_args_path"},
            ["/planning:plan-feature docs/plans/alpha.md"],
        )

        self.assertTrue(is_primary)

    def test_primary_link_workflow_command_negative_unrecognized_command(self) -> None:
        # command_args_path present but command does not match any workflow verb.
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.68,
            {"command_args_path"},
            ["/some-other-command"],
        )

        self.assertFalse(is_primary)

    def test_primary_link_workflow_command_requires_command_args_path_signal(self) -> None:
        # Correct workflow verb but signal does NOT include command_args_path — must
        # fall through to the confidence gates and fail.
        is_primary = features_router._is_primary_session_link(
            "session_evidence",
            0.68,
            {"file_read"},
            ["/dev:execute-phase"],
        )

        self.assertFalse(is_primary)


if __name__ == "__main__":
    unittest.main()
