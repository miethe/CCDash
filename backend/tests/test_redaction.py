"""Unit tests for backend/application/services/agent_queries/redaction.py.

Phase 1 / T1-003 + T1-005 evidence.

Covers:
  * Layer 1 — positive: each secret pattern fires on matching strings.
  * Layer 1 — negative: clean content passes through without modification.
  * Layer 2 — tool-name-aware: Bash commands with env assignments get redacted.
  * Layer 2 — tool-name-aware: Write/Edit content fields get scanned.
  * Layer 2 — unknown tool: still applies Layer 1 pattern scan (fail-closed).
  * Env-config: CCDASH_REDACTION_PATTERNS_ENABLED=false disables Layer 1.
  * Env-config: CCDASH_REDACTION_TOOL_AWARE_ENABLED=false disables Layer 2.
  * Both layers disabled: content passes through unchanged.
  * redact_entries: aggregate list processing, count accumulation, no mutation.
  * Output contract: REDACTED_PLACEHOLDER used; original keys preserved.
  * redact_entries emits DEBUG log when count > 0.

Run as named module:
    backend/.venv/bin/python -m pytest backend/tests/test_redaction.py -v
"""
from __future__ import annotations

import os
import unittest

from backend.application.services.agent_queries.redaction import (
    REDACTED_PLACEHOLDER,
    redact_entries,
    redact_log_entry,
    _redact_string_layer1,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry(content: str = "", tool_name: str | None = None, tool_args: str | None = None,
           tool_output: str | None = None) -> dict:
    e: dict = {"content": content, "type": "assistant"}
    if tool_name is not None:
        e["toolCall"] = {
            "id": "tc-1",
            "name": tool_name,
            "args": tool_args or "",
            "output": tool_output,
            "status": "success",
        }
    return e


# ── Layer 1 — Pattern coverage tests ─────────────────────────────────────────

class TestLayer1Patterns(unittest.TestCase):
    """Layer 1 positive and negative pattern tests."""

    def _redact(self, text: str) -> tuple[str, int]:
        return _redact_string_layer1(text)

    # --- Positive (should fire) ---

    def test_api_key_assignment_fires(self) -> None:
        text = "api_key=ABCDEF1234567890ABCDEF1234567890"
        result, count = self._redact(text)
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", result)
        self.assertIn(REDACTED_PLACEHOLDER, result)
        self.assertGreater(count, 0)

    def test_bearer_token_fires(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result, count = self._redact(text)
        self.assertNotIn("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9", result)
        self.assertGreater(count, 0)

    def test_aws_access_key_id_fires(self) -> None:
        text = "key = AKIAIOSFODNN7EXAMPLE"
        result, count = self._redact(text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", result)
        self.assertGreater(count, 0)

    def test_aws_secret_access_key_fires(self) -> None:
        text = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result, count = self._redact(text)
        self.assertNotIn("wJalrXUtnFEMI", result)
        self.assertGreater(count, 0)

    def test_openai_sk_key_fires(self) -> None:
        text = "key: sk-abc123def456ghi789jkl012mno345pqr678"
        result, count = self._redact(text)
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", result)
        self.assertGreater(count, 0)

    def test_github_pat_fires(self) -> None:
        text = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result, count = self._redact(text)
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", result)
        self.assertGreater(count, 0)

    def test_pem_private_key_header_fires(self) -> None:
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        result, count = self._redact(text)
        # Header line should be redacted
        self.assertNotIn("-----BEGIN RSA PRIVATE KEY-----", result)
        self.assertGreater(count, 0)

    def test_dotenv_assignment_fires(self) -> None:
        text = "DATABASE_PASSWORD=supersecretpass123\n"
        result, count = self._redact(text)
        self.assertNotIn("supersecretpass123", result)
        self.assertGreater(count, 0)

    def test_hex_64_fires(self) -> None:
        """64-char hex string (e.g. SHA-256 secret) is redacted."""
        secret = "a" * 64
        text = f"hash: {secret}"
        result, count = self._redact(text)
        self.assertNotIn("a" * 64, result)
        self.assertGreater(count, 0)

    # --- Negative (should NOT fire) ---

    def test_clean_plain_text_unchanged(self) -> None:
        text = "The session completed successfully with 3 tool calls."
        result, count = self._redact(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_short_hex_not_redacted(self) -> None:
        """Hex strings shorter than 64 chars (e.g. normal git hashes) are safe."""
        text = "commit abc123def456 modified 2 files"
        result, count = self._redact(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_numeric_only_string_unchanged(self) -> None:
        text = "duration_seconds: 3600"
        result, count = self._redact(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_short_api_value_not_redacted(self) -> None:
        """api_key= with value < 20 chars does not fire the api_key pattern."""
        text = "api_key=shortval"
        result, count = self._redact(text)
        # Short value (< 20 chars) should not be caught
        self.assertEqual(count, 0)

    def test_empty_string_unchanged(self) -> None:
        result, count = self._redact("")
        self.assertEqual(result, "")
        self.assertEqual(count, 0)


# ── Layer 1 on log entries via redact_log_entry ───────────────────────────────

class TestRedactLogEntryLayer1(unittest.TestCase):
    """Layer 1 pattern scan on log entry content field."""

    def test_api_key_in_content_redacted(self) -> None:
        e = _entry(content="Using api_key=ABCDEF1234567890ABCDEF1234567890 for auth")
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=False)
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", result["content"])
        self.assertGreater(count, 0)

    def test_clean_content_unchanged(self) -> None:
        e = _entry(content="Session started at 09:00 UTC")
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=False)
        self.assertEqual(result["content"], "Session started at 09:00 UTC")
        self.assertEqual(count, 0)

    def test_patterns_disabled_secret_not_redacted(self) -> None:
        """When Layer 1 is disabled, known secrets in content pass through."""
        e = _entry(content="api_key=ABCDEF1234567890ABCDEF1234567890")
        result, count = redact_log_entry(e, patterns_enabled=False, tool_aware_enabled=False)
        self.assertEqual(result["content"], "api_key=ABCDEF1234567890ABCDEF1234567890")
        self.assertEqual(count, 0)

    def test_original_entry_not_mutated(self) -> None:
        """redact_log_entry must return a new dict without mutating the input."""
        e = _entry(content="api_key=ABCDEF1234567890ABCDEF1234567890")
        original_content = e["content"]
        redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        self.assertEqual(e["content"], original_content)


# ── Layer 2 — Tool-name-aware field redaction ─────────────────────────────────

class TestRedactLogEntryLayer2(unittest.TestCase):
    """Tool-name-aware payload field redaction (Layer 2)."""

    def test_bash_command_with_env_var_redacted(self) -> None:
        e = _entry(
            tool_name="Bash",
            tool_args="export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCY && ./deploy.sh",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        tc = result["toolCall"]
        self.assertNotIn("wJalrXUtnFEMI", str(tc.get("args", "")))
        self.assertGreater(count, 0)

    def test_bash_sk_key_in_args_redacted(self) -> None:
        e = _entry(
            tool_name="Bash",
            tool_args="curl -H 'Authorization: Bearer sk-abc123def456ghi789jkl012mno345pqr678' https://api.example.com",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        tc = result["toolCall"]
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", str(tc.get("args", "")))
        self.assertGreater(count, 0)

    def test_write_tool_content_scanned(self) -> None:
        e = _entry(
            tool_name="Write",
            tool_args="DATABASE_URL=postgresql://user:secretpassword1234@localhost/db",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        tc = result["toolCall"]
        # The .env assignment DATABASE_URL= should trigger Layer 1 pattern
        self.assertGreater(count, 0)
        self.assertNotIn("secretpassword1234", str(tc.get("args", "")))

    def test_unknown_tool_still_runs_layer1_on_args(self) -> None:
        """Unknown tool names fall back to Layer 1 scan — never fail-open."""
        e = _entry(
            tool_name="UnknownCustomTool",
            tool_args="AKIAIOSFODNN7EXAMPLE",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        tc = result["toolCall"]
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", str(tc.get("args", "")))
        self.assertGreater(count, 0)

    def test_tool_output_with_secret_redacted(self) -> None:
        e = _entry(
            tool_name="Bash",
            tool_args="echo $TOKEN",
            tool_output="sk-abc123def456ghi789jkl012mno345pqr678",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        tc = result["toolCall"]
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", str(tc.get("output", "")))
        self.assertGreater(count, 0)

    def test_tool_aware_disabled_layer2_skipped(self) -> None:
        """Tool-aware layer disabled: Layer 1 still runs (fail-closed)."""
        # A secret embedded in a bearer header should still be caught by Layer 1
        e = _entry(
            tool_name="Bash",
            tool_args="curl -H 'Authorization: Bearer sk-abc123def456ghi789jkl012mno345pqr678' url",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=False)
        tc = result["toolCall"]
        # Layer 1 runs on args string even without Layer 2
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", str(tc.get("args", "")))

    def test_both_layers_disabled_nothing_redacted(self) -> None:
        """Explicit both-off: content and tool args pass through untouched."""
        secret = "sk-abc123def456ghi789jkl012mno345pqr678"
        e = _entry(
            content=f"token={secret}",
            tool_name="Bash",
            tool_args=f"export API_KEY={secret}",
        )
        result, count = redact_log_entry(e, patterns_enabled=False, tool_aware_enabled=False)
        self.assertIn(secret, result["content"])
        self.assertIn(secret, str(result["toolCall"]["args"]))
        self.assertEqual(count, 0)

    def test_clean_tool_call_unchanged(self) -> None:
        e = _entry(
            tool_name="Bash",
            tool_args="ls -la /tmp",
        )
        result, count = redact_log_entry(e, patterns_enabled=True, tool_aware_enabled=True)
        self.assertEqual(result["toolCall"]["args"], "ls -la /tmp")
        self.assertEqual(count, 0)


# ── Env-config toggle tests ───────────────────────────────────────────────────

class TestEnvConfig(unittest.TestCase):
    """CCDASH_REDACTION_* env var controls both layers."""

    def setUp(self) -> None:
        # Ensure clean env state
        os.environ.pop("CCDASH_REDACTION_PATTERNS_ENABLED", None)
        os.environ.pop("CCDASH_REDACTION_TOOL_AWARE_ENABLED", None)

    def tearDown(self) -> None:
        os.environ.pop("CCDASH_REDACTION_PATTERNS_ENABLED", None)
        os.environ.pop("CCDASH_REDACTION_TOOL_AWARE_ENABLED", None)

    def test_default_both_enabled(self) -> None:
        """Without env vars set, both layers default to enabled (fail-closed)."""
        e = _entry(content="api_key=ABCDEF1234567890ABCDEF1234567890")
        result, count = redact_log_entry(e)  # uses env defaults
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", result["content"])
        self.assertGreater(count, 0)

    def test_patterns_disabled_via_env(self) -> None:
        """CCDASH_REDACTION_PATTERNS_ENABLED=false disables Layer 1."""
        os.environ["CCDASH_REDACTION_PATTERNS_ENABLED"] = "false"
        os.environ["CCDASH_REDACTION_TOOL_AWARE_ENABLED"] = "false"
        e = _entry(content="api_key=ABCDEF1234567890ABCDEF1234567890")
        result, count = redact_log_entry(e)  # reads env
        self.assertEqual(result["content"], e["content"])
        self.assertEqual(count, 0)

    def test_patterns_enabled_via_env_true(self) -> None:
        """CCDASH_REDACTION_PATTERNS_ENABLED=true enables Layer 1."""
        os.environ["CCDASH_REDACTION_PATTERNS_ENABLED"] = "true"
        e = _entry(content="token: sk-abc123def456ghi789jkl012mno345pqr678")
        result, count = redact_log_entry(e)
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", result["content"])
        self.assertGreater(count, 0)

    def test_tool_aware_disabled_via_env(self) -> None:
        """CCDASH_REDACTION_TOOL_AWARE_ENABLED=false disables Layer 2 but Layer 1 still runs."""
        os.environ["CCDASH_REDACTION_PATTERNS_ENABLED"] = "true"
        os.environ["CCDASH_REDACTION_TOOL_AWARE_ENABLED"] = "false"
        # Bash args with a bearer token — Layer 1 catches it even without Layer 2
        e = _entry(
            tool_name="Bash",
            tool_args="curl -H 'Authorization: Bearer sk-abc123def456ghi789jkl012mno345pqr678' url",
        )
        result, count = redact_log_entry(e)
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678",
                         str(result["toolCall"]["args"]))


# ── redact_entries: list-level tests ─────────────────────────────────────────

class TestRedactEntries(unittest.TestCase):
    """redact_entries aggregate list processing."""

    def test_empty_list_returns_empty(self) -> None:
        result, count = redact_entries([])
        self.assertEqual(result, [])
        self.assertEqual(count, 0)

    def test_single_clean_entry_count_zero(self) -> None:
        e = _entry(content="Hello world")
        result, count = redact_entries([e])
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)

    def test_multiple_entries_counts_accumulated(self) -> None:
        entries = [
            _entry(content="api_key=ABCDEF1234567890ABCDEF1234567890"),
            _entry(content="clean message here"),
            _entry(
                tool_name="Bash",
                tool_args="export TOKEN=sk-abc123def456ghi789jkl012mno345pqr678 && run",
            ),
        ]
        result, count = redact_entries(
            entries, patterns_enabled=True, tool_aware_enabled=True
        )
        self.assertEqual(len(result), 3)
        self.assertGreater(count, 0)
        # Secrets must not appear in any output entry
        all_text = str(result)
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", all_text)
        self.assertNotIn("sk-abc123def456ghi789jkl012mno345pqr678", all_text)

    def test_input_list_not_mutated(self) -> None:
        original = "api_key=ABCDEF1234567890ABCDEF1234567890"
        entries = [_entry(content=original)]
        redact_entries(entries, patterns_enabled=True, tool_aware_enabled=True)
        self.assertEqual(entries[0]["content"], original)

    def test_placeholder_present_in_redacted_output(self) -> None:
        entries = [_entry(content="API_TOKEN=sk-abc123def456ghi789jkl012mno345pqr678")]
        result, count = redact_entries(entries, patterns_enabled=True, tool_aware_enabled=True)
        self.assertIn(REDACTED_PLACEHOLDER, result[0]["content"])

    def test_all_entries_disabled_zero_count(self) -> None:
        entries = [
            _entry(content="aws_secret_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
            _entry(content="AKIAIOSFODNN7EXAMPLE"),
        ]
        result, count = redact_entries(
            entries, patterns_enabled=False, tool_aware_enabled=False
        )
        self.assertEqual(count, 0)
        self.assertEqual(result[0]["content"], entries[0]["content"])
        self.assertEqual(result[1]["content"], entries[1]["content"])


# ── Secret-never-egresses fixture ─────────────────────────────────────────────

class TestSecretNeverEgresses(unittest.TestCase):
    """Fixture: embedded secrets must never appear in redacted output."""

    KNOWN_SECRETS = [
        "sk-abc123def456ghi789jkl012mno345pqr678",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
    ]

    def test_secrets_absent_from_redacted_entries(self) -> None:
        entries = [_entry(content=s) for s in self.KNOWN_SECRETS]
        result, _ = redact_entries(entries, patterns_enabled=True, tool_aware_enabled=True)
        output_text = str(result)
        for secret in self.KNOWN_SECRETS:
            self.assertNotIn(secret, output_text, f"Secret leaked: {secret!r}")

    def test_secrets_absent_from_tool_args(self) -> None:
        entries = [
            _entry(tool_name="Bash", tool_args=f"export KEY={s}")
            for s in self.KNOWN_SECRETS
        ]
        result, _ = redact_entries(entries, patterns_enabled=True, tool_aware_enabled=True)
        output_text = str(result)
        for secret in self.KNOWN_SECRETS:
            self.assertNotIn(secret, output_text, f"Secret leaked in tool args: {secret!r}")


if __name__ == "__main__":
    unittest.main()
