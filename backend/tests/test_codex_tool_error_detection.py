"""DI-4d — Codex tool-result error detection must fire on real payloads.

Regression guard for the defect measured 2026-08-03 on the node Postgres:
``session_tool_usage`` recorded ``call_count == success_count`` exactly for every
GPT/Codex model (190,450 all-time tool calls, 0 errors) because the Codex parser
looked for ``payload["status"] in {"error","failed","failure"}`` and real Codex
``function_call_output`` / ``custom_tool_call_output`` payloads carry no
``status`` key at all.

Every payload exercised here is **verbatim real data** captured from
``~/.codex/sessions/**/*.jsonl``. Provenance for each line is recorded in
``fixtures/codex_tool_error_payloads.provenance.json``; no payload shape in the
fixture was hand-invented.

Scope: parse-time detection only. This test asserts nothing about
``routing_rollup`` ``success_rate``, which stays ``null`` (DI-4e).
"""

import json
import unittest
from pathlib import Path

from backend.parsers.platforms.codex.tool_outcome import (
    SOURCE_EMPTY_OUTPUT,
    SOURCE_ENVELOPE_EXIT_CODE,
    SOURCE_EXIT_CODE_LINE,
    SOURCE_FAILURE_MARKER,
    SOURCE_IN_FLIGHT,
    SOURCE_PAYLOAD_STATUS,
    SOURCE_SCRIPT_LIFECYCLE,
    SOURCE_STRUCTURED_OK,
    SOURCE_UNKNOWN,
    classify_tool_outcome,
)
from backend.parsers.sessions import parse_session_file

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_FIXTURE = _FIXTURE_DIR / "codex_tool_error_payloads.jsonl"
_PROVENANCE = _FIXTURE_DIR / "codex_tool_error_payloads.provenance.json"


class CodexToolErrorFixtureTests(unittest.TestCase):
    """End-to-end: real Codex error payloads must produce nonzero error counts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.session = parse_session_file(_FIXTURE)
        cls.provenance = json.loads(_PROVENANCE.read_text(encoding="utf-8"))

    def test_fixture_is_real_codex_data_with_no_status_field(self) -> None:
        """The whole point of the defect: real payloads have no `status` key."""
        outputs = 0
        for raw_line in _FIXTURE.read_text(encoding="utf-8").splitlines():
            entry = json.loads(raw_line)
            payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else entry
            if str(payload.get("type") or "").endswith("call_output"):
                outputs += 1
                self.assertIsNone(
                    payload.get("status"),
                    "real Codex tool-result payloads carry no status field; "
                    "a fixture with one would not reproduce the defect",
                )
        self.assertGreaterEqual(outputs, 7)

    def test_session_parses(self) -> None:
        self.assertIsNotNone(self.session)
        self.assertTrue(self.session.logs)

    def test_error_detection_is_nonzero(self) -> None:
        """The headline assertion: NONZERO errors detected on real Codex payloads."""
        errored = [log for log in self.session.logs if log.toolCall and log.toolCall.isError]
        expected_errors = sum(1 for p in self.provenance["pairs"] if p["expect"] == "error")
        self.assertEqual(len(errored), expected_errors)
        self.assertGreater(len(errored), 0)

    def test_successful_calls_are_not_flagged(self) -> None:
        """Guard the other direction — detection must not blanket-fail every call."""
        succeeded = [
            log
            for log in self.session.logs
            if log.toolCall and not log.toolCall.isError and log.toolCall.output
        ]
        expected_successes = sum(1 for p in self.provenance["pairs"] if p["expect"] == "success")
        self.assertEqual(len(succeeded), expected_successes)
        self.assertGreater(len(succeeded), 0)

    def test_tool_usage_success_rate_is_below_one(self) -> None:
        """`session_tool_usage.success_count` is derived from ToolUsage.successRate."""
        rates = {tool.name: tool.successRate for tool in self.session.toolsUsed}
        self.assertTrue(rates, "fixture produced no ToolUsage rows")
        self.assertTrue(
            any(rate < 1.0 for rate in rates.values()),
            f"every tool still reports successRate 1.0 — the defect is not fixed: {rates}",
        )

    def test_every_detected_outcome_records_its_source(self) -> None:
        sources = {
            log.metadata.get("toolStatusSource")
            for log in self.session.logs
            if log.toolCall and log.toolCall.output
        }
        self.assertNotIn(None, sources)
        self.assertIn(SOURCE_EXIT_CODE_LINE, sources)
        self.assertIn(SOURCE_ENVELOPE_EXIT_CODE, sources)
        self.assertIn(SOURCE_FAILURE_MARKER, sources)
        self.assertIn(SOURCE_SCRIPT_LIFECYCLE, sources)


class CodexToolOutcomeClassifierTests(unittest.TestCase):
    """Unit coverage of each real payload shape the classifier must recognise.

    Every string below is copied from a real rollout log (see the module
    docstring for the corpus); none is a speculative schema.
    """

    def test_exit_code_line_nonzero_is_error(self) -> None:
        raw = (
            "Exit code: 1\nWall time: 0 seconds\nOutput:\n"
            "sed: docs/project_plans/artifact-version-tracking-sync-prd.md: No such file or directory\n"
        )
        self.assertEqual(classify_tool_outcome(raw), (True, SOURCE_EXIT_CODE_LINE))

    def test_exit_code_line_zero_is_success(self) -> None:
        raw = "Exit code: 0\nWall time: 0.1 seconds\nOutput:\nfine\n"
        self.assertEqual(classify_tool_outcome(raw), (False, SOURCE_EXIT_CODE_LINE))

    def test_process_exited_with_code_nonzero_is_error(self) -> None:
        raw = (
            "Chunk ID: beb018\nWall time: 0.0513 seconds\n"
            "Process exited with code 1\nOriginal token count: 0\nOutput:\n"
        )
        self.assertEqual(classify_tool_outcome(raw), (True, SOURCE_EXIT_CODE_LINE))

    def test_multiline_command_echo_does_not_hide_the_exit_line(self) -> None:
        """`Command:` echoes can span many lines; the exit line still wins."""
        raw = (
            "Command: /bin/zsh -lc 'python - <<PY\n"
            "print(1)\nprint(2)\nprint(3)\nprint(4)\nprint(5)\nPY'\n"
            "Chunk ID: 0110d9\nWall time: 0.2 seconds\n"
            "Process exited with code 2\nOriginal token count: 12\nOutput:\nboom\n"
        )
        self.assertEqual(classify_tool_outcome(raw), (True, SOURCE_EXIT_CODE_LINE))

    def test_output_body_error_text_is_not_a_failure_marker(self) -> None:
        """A succeeding command whose stdout mentions errors must stay a success."""
        raw = (
            "Exit code: 0\nWall time: 0.3 seconds\nOutput:\n"
            "error: pathspec 'nope' did not match\nfailed to open: whatever\n"
        )
        self.assertEqual(classify_tool_outcome(raw), (False, SOURCE_EXIT_CODE_LINE))

    def test_metadata_envelope_exit_code(self) -> None:
        err = json.dumps(
            {
                "output": "/Users/x/.bash_profile: line 3: source: command not found\n",
                "metadata": {"exit_code": 2, "duration_seconds": 0.0},
            }
        )
        ok = json.dumps(
            {
                "output": "Success. Updated the following files:\nM backend/config.py\n",
                "metadata": {"exit_code": 0, "duration_seconds": 0.1},
            }
        )
        self.assertEqual(classify_tool_outcome(err), (True, SOURCE_ENVELOPE_EXIT_CODE))
        self.assertEqual(classify_tool_outcome(ok), (False, SOURCE_ENVELOPE_EXIT_CODE))

    def test_script_lifecycle_from_custom_tool_call_output_blocks(self) -> None:
        """`custom_tool_call_output.output` is a list of text blocks, not a string."""
        failed = [
            {"type": "input_text", "text": "Script failed\nWall time 0.2 seconds\nOutput:\n"},
            {"type": "input_text", "text": "Script error:\nexec cell 231 not found"},
        ]
        completed = [
            {"type": "input_text", "text": "Script completed\nWall time 0.4 seconds\nOutput:\n"},
        ]
        terminated = [{"type": "input_text", "text": "Script terminated\nWall time 0.0 seconds\nOutput:\n"}]
        running = [{"type": "input_text", "text": "Script running with cell ID 4"}]
        self.assertEqual(classify_tool_outcome(failed), (True, SOURCE_SCRIPT_LIFECYCLE))
        self.assertEqual(classify_tool_outcome(completed), (False, SOURCE_SCRIPT_LIFECYCLE))
        self.assertEqual(classify_tool_outcome(terminated), (True, SOURCE_SCRIPT_LIFECYCLE))
        self.assertEqual(classify_tool_outcome(running), (False, SOURCE_SCRIPT_LIFECYCLE))

    def test_bare_failure_markers(self) -> None:
        cases = [
            "write_stdin failed: stdin is closed for this session; rerun exec_command with tty=true",
            "apply_patch verification failed: Failed to find expected lines in /tmp/a.py:\n    def f",
            "collab spawn failed: agent thread limit reached (max 6)",
            "failed to parse function arguments: missing field `input` at line 1 column 944",
            "failed in sandbox MacosSeatbelt with execution error: sandbox denied exec error, exit code: 2",
            "failed to spawn code-mode host /Users/x/.local/bin/codex-code-mode-host: No such file",
            "unsupported call: spawn_agent",
            "execution error: Io(Os { code: 20, kind: NotADirectory })",
            "Blocked by robots.txt\nThe following domains cannot be accessed: orkg.org",
            "exec command rejected by user",
            "exec_command failed for `/bin/zsh -lc 'PYTHONPATH=. uv run pytest'`: CreateProcess { }",
        ]
        for raw in cases:
            with self.subTest(raw=raw[:48]):
                self.assertEqual(classify_tool_outcome(raw), (True, SOURCE_FAILURE_MARKER))

    def test_in_flight_launch_is_not_an_error(self) -> None:
        raw = (
            "Chunk ID: 6ac2c5\nWall time: 1.0016 seconds\n"
            "Process running with session ID 47488\nOriginal token count: 29\nOutput:\n"
        )
        self.assertEqual(classify_tool_outcome(raw), (False, SOURCE_IN_FLIGHT))

    def test_structured_results_are_successes(self) -> None:
        cases = [
            '{"agent_id":"019d066b-91e0-74d3-9787-f0d84dd19c13","nickname":"Franklin"}',
            '{"status":{},"timed_out":true}',
            '{"message":"Wait timed out.","timed_out":true}',
            '{"previous_status":"running"}',
            '{"submission_id":"019d0e05-bda8-7b52-abb2-4ff0ce808230"}',
            '{"agents":[{"agent_name":"/root","agent_status":"running"}]}',
        ]
        for raw in cases:
            with self.subTest(raw=raw[:40]):
                self.assertEqual(classify_tool_outcome(raw), (False, SOURCE_STRUCTURED_OK))

    def test_empty_output_is_not_an_error(self) -> None:
        self.assertEqual(classify_tool_outcome(""), (False, SOURCE_EMPTY_OUTPUT))
        self.assertEqual(classify_tool_outcome(None), (False, SOURCE_EMPTY_OUTPUT))

    def test_unclassifiable_output_is_unknown_not_error(self) -> None:
        is_error, source = classify_tool_outcome("No app terminal session is attached to this thread yet.")
        self.assertIsNone(is_error)
        self.assertEqual(source, SOURCE_UNKNOWN)

    def test_legacy_status_field_still_honoured(self) -> None:
        """Older/synthetic fixtures do carry `status`; keep them working."""
        self.assertEqual(
            classify_tool_outcome("boom", payload_status="failed"),
            (True, SOURCE_PAYLOAD_STATUS),
        )
        self.assertEqual(
            classify_tool_outcome("wrote file", payload_status="success"),
            (False, SOURCE_PAYLOAD_STATUS),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
