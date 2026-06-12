"""Phase 5 (T5-002): workflow.json sidecar parser.

Resilience contract (AC-5.1 / T5-002): every parse path tolerates malformed JSON,
partial/missing fields, and a missing file by returning ``None`` (or a record with
``None`` attributes) — it never raises.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_workflow_sidecar_parser.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.workflow_sidecar import (
    WorkflowSidecar,
    parse_workflow_sidecar,
    scan_workflow_sidecars,
)


class WorkflowSidecarParserTests(unittest.TestCase):
    def _tmpdir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _write(self, directory: Path, name: str, content: str) -> Path:
        path = directory / name
        path.write_text(content, encoding="utf-8")
        return path

    # ── valid ─────────────────────────────────────────────────────────
    def test_valid_sidecar_extracts_correlation_ids(self) -> None:
        d = self._tmpdir()
        path = self._write(
            d,
            "workflow.json",
            json.dumps({"runId": "run-123", "taskId": "task-abc", "workflowId": "wf-9"}),
        )
        record = parse_workflow_sidecar(path)
        self.assertIsInstance(record, WorkflowSidecar)
        assert record is not None
        self.assertEqual(record.run_id, "run-123")
        self.assertEqual(record.task_id, "task-abc")
        self.assertEqual(record.workflow_id, "wf-9")
        self.assertIsNotNone(record.mtime)

    def test_snake_case_keys_accepted(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", json.dumps({"run_id": "r1", "task_id": "t1"}))
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.run_id, "r1")
        self.assertEqual(record.task_id, "t1")

    # ── 1M normalization ───────────────────────────────────────────────
    def test_context_window_1m_explicit_label(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", json.dumps({"runId": "r", "contextWindow": "1m"}))
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.context_window, "1M")

    def test_context_window_1m_from_model_variant_suffix(self) -> None:
        d = self._tmpdir()
        path = self._write(
            d, "workflow.json", json.dumps({"runId": "r", "model": "claude-opus-4-8[1m]"})
        )
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.context_window, "1M")

    def test_context_window_1m_from_numeric_token_window(self) -> None:
        d = self._tmpdir()
        path = self._write(
            d, "workflow.json", json.dumps({"runId": "r", "context_window": "1000000"})
        )
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.context_window, "1M")

    def test_non_1m_context_window_preserved_verbatim(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", json.dumps({"runId": "r", "contextWindow": "200K"}))
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.context_window, "200K")

    # ── partial / missing fields ────────────────────────────────────────
    def test_partial_sidecar_missing_fields_are_none(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", json.dumps({"runId": "only-run"}))
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertEqual(record.run_id, "only-run")
        self.assertIsNone(record.task_id)
        self.assertIsNone(record.workflow_id)
        self.assertIsNone(record.context_window)

    def test_empty_object_yields_all_none_no_raise(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", "{}")
        record = parse_workflow_sidecar(path)
        assert record is not None
        self.assertIsNone(record.run_id)
        self.assertIsNone(record.task_id)
        self.assertIsNone(record.context_window)

    # ── malformed / missing file → None, never raise ────────────────────
    def test_malformed_json_returns_none(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", "{not valid json,,,")
        self.assertIsNone(parse_workflow_sidecar(path))

    def test_non_object_root_returns_none(self) -> None:
        d = self._tmpdir()
        path = self._write(d, "workflow.json", json.dumps(["a", "b"]))
        self.assertIsNone(parse_workflow_sidecar(path))

    def test_missing_file_returns_none(self) -> None:
        d = self._tmpdir()
        self.assertIsNone(parse_workflow_sidecar(d / "does-not-exist.json"))

    # ── scan ─────────────────────────────────────────────────────────────
    def test_scan_finds_nested_sidecars_and_skips_malformed(self) -> None:
        d = self._tmpdir()
        (d / "a").mkdir()
        (d / "b").mkdir()
        self._write(d / "a", "workflow.json", json.dumps({"runId": "ra"}))
        self._write(d / "b", "workflow.json", "{malformed")
        records = scan_workflow_sidecars(d)
        run_ids = {r.run_id for r in records}
        # The malformed one is skipped (None), the valid one is present.
        self.assertIn("ra", run_ids)
        self.assertNotIn(None, run_ids)

    def test_scan_missing_directory_returns_empty(self) -> None:
        d = self._tmpdir()
        self.assertEqual(scan_workflow_sidecars(d / "nope"), [])


if __name__ == "__main__":
    unittest.main()
