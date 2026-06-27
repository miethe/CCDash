"""Thin dry-run test for the IntentTree example client (T10-007).

Verifies that the client script runs end-to-end in ``--dry`` mode without
connecting to a live server.  The orchestrator exercises the live smoke
separately; this test covers importability + dry execution.
"""
from __future__ import annotations

import io
import sys
import unittest

# Add the examples directory to sys.path so the import works when run from any cwd.
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import client as _client_module


class TestClientDryRun(unittest.TestCase):
    """Smoke-tests for dry-run execution of the IntentTree example client."""

    def test_dry_run_completes_without_error(self) -> None:
        """run() with dry=True must complete without raising."""
        _client_module.run(
            base_url="http://localhost:8000",
            project_id="",
            token="",
            dry=True,
            limit=5,
            search_query="test",
        )

    def test_dry_run_with_project_id(self) -> None:
        """run() with dry=True and a project_id uses the dry-detail mock."""
        _client_module.run(
            base_url="http://localhost:8000",
            project_id="my-project",
            token="",
            dry=True,
            limit=5,
            search_query="auth",
        )

    def test_check_capability_true_when_present(self) -> None:
        body = {"data": {"capabilities": ["sessions:cross-project", "sessions:detail"]}}
        self.assertTrue(_client_module._check_capability(body, "sessions:cross-project"))
        self.assertTrue(_client_module._check_capability(body, "sessions:detail"))

    def test_check_capability_false_when_absent(self) -> None:
        body = {"data": {"capabilities": ["sessions:cross-project"]}}
        self.assertFalse(_client_module._check_capability(body, "sessions:detail"))

    def test_check_capability_false_on_empty(self) -> None:
        self.assertFalse(_client_module._check_capability({}, "anything"))

    def test_dry_response_contracts_are_valid(self) -> None:
        """The built-in dry responses must have the expected envelope shape."""
        for name, mock in [
            ("capability", _client_module._DRY_CAPABILITY),
            ("sessions", _client_module._DRY_SESSIONS),
            ("search", _client_module._DRY_SEARCH),
            ("detail", _client_module._DRY_DETAIL),
        ]:
            with self.subTest(mock=name):
                self.assertIn("status", mock)
                self.assertIn("data", mock)
                self.assertEqual(mock["status"], "ok")


if __name__ == "__main__":
    unittest.main()
