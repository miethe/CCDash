import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.test_results import (
    _extract_error_fingerprint,
    generate_test_id,
    parse_junit_xml,
    parse_junit_xml_file,
)


class TestResultsParserTests(unittest.TestCase):
    def test_parse_junit_xml_maps_statuses(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite" tests="4">
  <testcase classname="tests.test_sample.TestSample" name="test_pass" time="0.010"/>
  <testcase classname="tests.test_sample.TestSample" name="test_fail" time="0.025">
    <failure message="assert 1 == 2">Traceback line 42</failure>
  </testcase>
  <testcase classname="tests.test_sample.TestSample" name="test_skip" time="0.000">
    <skipped message="explicit skip"/>
  </testcase>
  <testcase classname="tests.test_sample.TestSample" name="test_error" time="0.004">
    <error message="boom">stack trace line 77</error>
  </testcase>
</testsuite>
"""
        payload = parse_junit_xml(xml, "project-1", {"run_id": "run-1", "timestamp": "2026-02-28T10:00:00Z"})

        self.assertEqual(payload["run"]["run_id"], "run-1")
        self.assertEqual(payload["run"]["total_tests"], 4)
        self.assertEqual(payload["run"]["passed_tests"], 1)
        self.assertEqual(payload["run"]["failed_tests"], 2)
        self.assertEqual(payload["run"]["skipped_tests"], 1)
        self.assertEqual(len(payload["test_definitions"]), 4)
        statuses = [row["status"] for row in payload["test_results"]]
        self.assertEqual(statuses, ["passed", "failed", "skipped", "error"])
        self.assertTrue(payload["test_results"][1]["error_fingerprint"])

    def test_parse_junit_xml_handles_nested_and_parameterized_cases(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="outer">
    <testsuite name="inner">
      <testcase classname="tests.unit.test_math.TestMath" name="test_add[1-2]" time="0.020"/>
      <testcase classname="tests.unit.test_math.TestMath" name="test_add[2-3]" time="0.021"/>
      <testcase classname="tests.unit.test_math.TestMath" name="test_subtract" time="0.010"/>
    </testsuite>
  </testsuite>
</testsuites>
"""
        payload = parse_junit_xml(xml, "project-2", {"run_id": "run-2"})
        definitions = payload["test_definitions"]

        self.assertEqual(payload["run"]["total_tests"], 3)
        self.assertEqual(len(definitions), 3)
        ids = {row["test_id"] for row in definitions}
        self.assertEqual(len(ids), 3)

        first = payload["test_results"][0]
        second = payload["test_results"][1]
        self.assertNotEqual(first["test_id"], second["test_id"])
        self.assertEqual(first["base_name"], "test_add")
        self.assertEqual(first["parameters"], ["1", "2"])
        self.assertEqual(first["path"], "tests/unit/test_math.py")

    def test_parse_junit_xml_file_merges_sidecar_and_overrides(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite">
  <testcase classname="tests.api.test_auth.TestAuth" name="test_login[happy-path]" time="0.010"/>
</testsuite>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "results.xml"
            xml_path.write_text(xml, encoding="utf-8")

            inferred_test_id = generate_test_id(
                "tests/api/test_auth.py",
                "test_login[happy-path]",
                framework="pytest",
            )
            sidecar = {
                "run_id": "run-from-sidecar",
                "git_sha": "abc1234",
                "branch": "feat/test-visualizer",
                "agent_session_id": "session-1",
                "env_fingerprint": "py311-macos",
                "trigger": "ci",
                "test_overrides": {
                    inferred_test_id: {
                        "tags": ["auth", "critical"],
                        "owner": "qa@example.com",
                    }
                },
            }
            sidecar_path = Path(f"{xml_path}.meta.json")
            sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

            payload = parse_junit_xml_file(xml_path, "project-3", {"timestamp": "2026-02-28T12:00:00Z"})

        self.assertEqual(payload["run"]["run_id"], "run-from-sidecar")
        self.assertEqual(payload["run"]["git_sha"], "abc1234")
        self.assertEqual(payload["run"]["trigger"], "ci")
        self.assertTrue(payload.get("sidecar_file", "").endswith(".meta.json"))
        self.assertEqual(payload["test_definitions"][0]["tags"], ["auth", "critical"])
        self.assertEqual(payload["test_definitions"][0]["owner"], "qa@example.com")

    def test_parse_junit_xml_file_without_sidecar_is_graceful(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite">
  <testcase classname="tests.core.test_ping.TestPing" name="test_ping" time="0.001"/>
</testsuite>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "report.xml"
            xml_path.write_text(xml, encoding="utf-8")
            payload = parse_junit_xml_file(xml_path, "project-4", {})

        self.assertEqual(payload["run"]["project_id"], "project-4")
        self.assertEqual(payload["run"]["total_tests"], 1)
        self.assertTrue(payload["run"]["run_id"].startswith("project-4-"))

    def test_malformed_xml_returns_empty_payload_with_error(self) -> None:
        payload = parse_junit_xml("<testsuite><testcase>", "project-5", {"run_id": "bad-run"})

        self.assertEqual(payload["run"]["run_id"], "bad-run")
        self.assertEqual(payload["run"]["total_tests"], 0)
        self.assertEqual(payload["test_definitions"], [])
        self.assertEqual(payload["test_results"], [])
        self.assertEqual(len(payload["errors"]), 1)
        self.assertIn("Malformed JUnit XML", payload["errors"][0])

    def test_error_fingerprint_strips_line_numbers_and_addresses(self) -> None:
        first = "Assertion failed at line 42 in /tmp/test.py:42 object 0xABCDEF 2026-02-28T10:00:00Z"
        second = "Assertion failed at line 108 in /tmp/test.py:108 object 0x123456 2026-02-28T10:02:00Z"

        fp_one = _extract_error_fingerprint(first)
        fp_two = _extract_error_fingerprint(second)

        self.assertTrue(fp_one)
        self.assertEqual(fp_one, fp_two)


if __name__ == "__main__":
    unittest.main()
