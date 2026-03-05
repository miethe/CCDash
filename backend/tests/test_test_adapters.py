import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.test_adapters import parse_test_artifact


class TestAdaptersTests(unittest.TestCase):
    def test_parse_jest_results_json(self) -> None:
        payload = {
            "testResults": [
                {
                    "name": "skillmeat/web/components/foo.test.tsx",
                    "assertionResults": [
                        {"title": "renders", "ancestorTitles": ["Foo"], "status": "passed"},
                        {
                            "title": "handles error",
                            "ancestorTitles": ["Foo"],
                            "status": "failed",
                            "failureMessages": ["Expected true to be false"],
                        },
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "jest-results.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            parsed = parse_test_artifact("jest", path, "project-1")

        self.assertIsNotNone(parsed.run_payload)
        assert parsed.run_payload is not None
        self.assertEqual(len(parsed.run_payload.test_results), 2)
        self.assertEqual(parsed.run_payload.test_results[0]["framework"], "jest")

    def test_parse_playwright_results_json(self) -> None:
        payload = {
            "suites": [
                {
                    "title": "root",
                    "specs": [
                        {
                            "title": "login flow",
                            "file": "tests/login.spec.ts",
                            "tests": [{"results": [{"status": "passed", "duration": 15}]}],
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "results.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            parsed = parse_test_artifact("playwright", path, "project-2")

        self.assertIsNotNone(parsed.run_payload)
        assert parsed.run_payload is not None
        self.assertEqual(len(parsed.run_payload.test_results), 1)
        self.assertEqual(parsed.run_payload.test_results[0]["framework"], "playwright")

    def test_parse_coverage_xml_metrics(self) -> None:
        xml = """<?xml version="1.0" ?>
<coverage line-rate="0.8" branch-rate="0.6"></coverage>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "coverage.xml"
            path.write_text(xml, encoding="utf-8")
            parsed = parse_test_artifact("coverage", path, "project-3")

        self.assertIsNone(parsed.run_payload)
        self.assertGreaterEqual(len(parsed.metrics), 2)
        metric_names = {item["metric_name"] for item in parsed.metrics}
        self.assertIn("line_pct", metric_names)


if __name__ == "__main__":
    unittest.main()
