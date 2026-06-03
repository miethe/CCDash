"""Tests for backend.env_bootstrap — .env auto-load module.

Coverage:
- load_local_env loads a .env written to a tmp dir and sets a new var into os.environ
- override=False semantics: pre-set env vars are not overridden by .env values
- .env.local precedence over .env: .env.local value wins for an unset var
- Missing files: load_local_env on an empty tmp dir returns [] without raising
- dotenv_autoload_enabled returns False while running under pytest (pytest in sys.modules)
- dotenv_autoload_enabled returns False when CCDASH_DISABLE_DOTENV=1
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


# Unique env var name used across all tests to avoid collisions
_TEST_VAR = "CCDASH_TEST_DOTENV_XYZ"
_TEST_VAR2 = "CCDASH_TEST_DOTENV_ABC"


class LoadLocalEnvTests(unittest.TestCase):
    """Tests for load_local_env()."""

    def setUp(self) -> None:
        # Ensure variables are absent before each test
        os.environ.pop(_TEST_VAR, None)
        os.environ.pop(_TEST_VAR2, None)

    def tearDown(self) -> None:
        os.environ.pop(_TEST_VAR, None)
        os.environ.pop(_TEST_VAR2, None)

    def test_loads_env_file_and_sets_var(self) -> None:
        """load_local_env reads .env and injects a new var into os.environ."""
        from backend.env_bootstrap import load_local_env

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".env").write_text(f"{_TEST_VAR}=hello_from_dotenv\n")

            loaded = load_local_env(root=tmp_path)

        self.assertIn(str(tmp_path / ".env"), loaded)
        self.assertEqual(os.environ.get(_TEST_VAR), "hello_from_dotenv")

    def test_override_false_does_not_overwrite_existing_var(self) -> None:
        """Pre-set env vars must not be overridden by .env (override=False)."""
        from backend.env_bootstrap import load_local_env

        os.environ[_TEST_VAR] = "real"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".env").write_text(f"{_TEST_VAR}=from_dotenv\n")

            load_local_env(root=tmp_path)

        self.assertEqual(os.environ[_TEST_VAR], "real")

    def test_env_local_wins_over_env(self) -> None:
        """.env.local value takes precedence over .env for an unset variable."""
        from backend.env_bootstrap import load_local_env

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".env").write_text(f"{_TEST_VAR}=from_env\n")
            (tmp_path / ".env.local").write_text(f"{_TEST_VAR}=from_env_local\n")

            loaded = load_local_env(root=tmp_path)

        # Both files should have been loaded
        self.assertIn(str(tmp_path / ".env"), loaded)
        self.assertIn(str(tmp_path / ".env.local"), loaded)
        # .env.local loads first with override=False, so its value wins
        self.assertEqual(os.environ.get(_TEST_VAR), "from_env_local")

    def test_missing_files_returns_empty_list(self) -> None:
        """load_local_env on an empty directory returns [] without raising."""
        from backend.env_bootstrap import load_local_env

        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_local_env(root=Path(tmp))

        self.assertEqual(loaded, [])

    def test_only_existing_files_appear_in_loaded_list(self) -> None:
        """Only files that actually exist are included in the returned list."""
        from backend.env_bootstrap import load_local_env

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Only create .env, not .env.local
            (tmp_path / ".env").write_text(f"{_TEST_VAR}=exists\n")

            loaded = load_local_env(root=tmp_path)

        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0].endswith(".env"))


class DotenvAutoloadEnabledTests(unittest.TestCase):
    """Tests for dotenv_autoload_enabled()."""

    def test_returns_false_under_pytest(self) -> None:
        """Must return False when pytest is in sys.modules (test-safety guard)."""
        from backend.env_bootstrap import dotenv_autoload_enabled

        # pytest is in sys.modules right now because we ARE running under pytest
        self.assertIn("pytest", sys.modules)
        result = dotenv_autoload_enabled()
        self.assertFalse(result)

    def test_returns_false_when_disabled_via_env_var(self) -> None:
        """Must return False when CCDASH_DISABLE_DOTENV=1."""
        from backend.env_bootstrap import dotenv_autoload_enabled

        for truthy_value in ("1", "true", "yes", "on", "TRUE", "YES", "ON"):
            with self.subTest(value=truthy_value):
                result = dotenv_autoload_enabled({"CCDASH_DISABLE_DOTENV": truthy_value})
                self.assertFalse(result)

    def test_returns_true_for_empty_disable_flag(self) -> None:
        """Must return True when CCDASH_DISABLE_DOTENV is absent or empty (ignoring pytest guard)."""
        from backend.env_bootstrap import dotenv_autoload_enabled

        # Pass an explicit environ dict to bypass the sys.modules check indirectly —
        # note: dotenv_autoload_enabled also checks sys.modules unconditionally,
        # so we patch sys.modules temporarily for this case.
        saved = sys.modules.pop("pytest", None)
        saved_pytest_runner = sys.modules.pop("_pytest", None)
        try:
            result = dotenv_autoload_enabled({})
            self.assertTrue(result)
        finally:
            if saved is not None:
                sys.modules["pytest"] = saved
            if saved_pytest_runner is not None:
                sys.modules["_pytest"] = saved_pytest_runner


class AutoloadLocalEnvIdempotencyTests(unittest.TestCase):
    """Tests for autoload_local_env() idempotency guard."""

    def setUp(self) -> None:
        os.environ.pop(_TEST_VAR, None)

    def tearDown(self) -> None:
        os.environ.pop(_TEST_VAR, None)

    def test_autoload_is_no_op_under_pytest(self) -> None:
        """autoload_local_env() must not load files when running under pytest."""
        import backend.env_bootstrap as eb
        from backend.env_bootstrap import autoload_local_env

        # Reset internal state so we can test the guard path
        original_loaded = eb._loaded
        eb._loaded = False
        try:
            result = autoload_local_env()
            # Under pytest dotenv_autoload_enabled() returns False, so result must be []
            self.assertEqual(result, [])
        finally:
            eb._loaded = original_loaded


if __name__ == "__main__":
    unittest.main()
