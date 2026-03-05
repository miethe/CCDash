from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.services.execution_policy import evaluate_execution_policy


class ExecutionPolicyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name).resolve()
        self.workspace_root = self._tmp_path / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (self._tmp_path / "outside").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_allows_low_risk_read_only_command(self) -> None:
        result = evaluate_execution_policy(
            command="git status",
            workspace_root=self.workspace_root,
            cwd=".",
            env_profile="default",
        )

        self.assertEqual(result.verdict, "allow")
        self.assertEqual(result.risk_level, "low")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.normalized_command, "git status")
        self.assertIn("safe_read_only_command", result.reason_codes)

    def test_requires_approval_for_destructive_command(self) -> None:
        result = evaluate_execution_policy(
            command="rm -rf build",
            workspace_root=self.workspace_root,
            cwd="src",
        )

        self.assertEqual(result.verdict, "requires_approval")
        self.assertEqual(result.risk_level, "high")
        self.assertTrue(result.requires_approval)
        self.assertIn("destructive_command", result.reason_codes)

    def test_denies_blocked_command_pattern(self) -> None:
        result = evaluate_execution_policy(
            command="rm -rf /",
            workspace_root=self.workspace_root,
            cwd=".",
        )

        self.assertEqual(result.verdict, "deny")
        self.assertEqual(result.risk_level, "high")
        self.assertIn("blocked_command_pattern", result.reason_codes)

    def test_denies_when_cwd_escapes_workspace(self) -> None:
        result = evaluate_execution_policy(
            command="git status",
            workspace_root=self.workspace_root,
            cwd="../outside",
        )

        self.assertEqual(result.verdict, "deny")
        self.assertIn("workspace_boundary_violation", result.reason_codes)

    def test_denies_when_cwd_missing(self) -> None:
        result = evaluate_execution_policy(
            command="git status",
            workspace_root=self.workspace_root,
            cwd="missing/subdir",
        )

        self.assertEqual(result.verdict, "deny")
        self.assertIn("cwd_not_found", result.reason_codes)

    def test_denies_unsupported_env_profile(self) -> None:
        result = evaluate_execution_policy(
            command="git status",
            workspace_root=self.workspace_root,
            cwd=".",
            env_profile="host",
        )

        self.assertEqual(result.verdict, "deny")
        self.assertIn("unsupported_env_profile", result.reason_codes)

    def test_requires_approval_for_compound_shell_command(self) -> None:
        result = evaluate_execution_policy(
            command="npm test && npm run lint",
            workspace_root=self.workspace_root,
            cwd=".",
        )

        self.assertEqual(result.verdict, "requires_approval")
        self.assertEqual(result.risk_level, "high")
        self.assertIn("compound_shell_command", result.reason_codes)

    def test_denies_invalid_command_syntax(self) -> None:
        result = evaluate_execution_policy(
            command="echo 'unterminated",
            workspace_root=self.workspace_root,
            cwd=".",
        )

        self.assertEqual(result.verdict, "deny")
        self.assertIn("invalid_command_syntax", result.reason_codes)

    def test_requires_approval_for_unknown_command(self) -> None:
        result = evaluate_execution_policy(
            command="custom-tool run --now",
            workspace_root=self.workspace_root,
            cwd=".",
        )

        self.assertEqual(result.verdict, "requires_approval")
        self.assertEqual(result.risk_level, "medium")
        self.assertIn("unknown_command", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
