"""Phase 5 (T5-003 / AC-5.1, AC-5.2): sidecar → session context-window join.

Covers the localized, additive join in ``sync_engine``:
  * A matching workflow.json within the ±1 min window sets context_window.
  * No matching sidecar (wrong id, out of window, flag off, no ids) leaves it null.
  * Workflow grouping/linkage is IDENTICAL with and without the sidecar — only
    context_window differs (AC-5.2: linkage survives a null/absent sidecar).

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_phase5_sidecar_join.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.parsers.sessions import parse_session_file
from backend.db import sync_engine


def _set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


class SidecarJoinHelperTests(unittest.TestCase):
    def _tmpdir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _session_file(self, directory: Path) -> Path:
        path = directory / "session.jsonl"
        path.write_text("{}\n", encoding="utf-8")
        return path

    def _sidecar(self, directory: Path, payload: dict) -> Path:
        path = directory / "workflow.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_match_within_window_sets_context_window(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        sidecar = self._sidecar(d, {"taskId": "task-1", "contextWindow": "1m"})
        base = 1_000_000.0
        _set_mtime(session_path, base)
        _set_mtime(sidecar, base + 30)  # within ±60s
        result = sync_engine._join_sidecar_context_window({"taskId": "task-1"}, session_path)
        self.assertEqual(result, "1M")

    def test_match_on_run_id(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        sidecar = self._sidecar(d, {"runId": "run-9", "contextWindow": "1M"})
        base = 1_000_000.0
        _set_mtime(session_path, base)
        _set_mtime(sidecar, base)
        result = sync_engine._join_sidecar_context_window({"runId": "run-9"}, session_path)
        self.assertEqual(result, "1M")

    def test_no_id_match_returns_none(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        sidecar = self._sidecar(d, {"taskId": "other", "contextWindow": "1M"})
        base = 1_000_000.0
        _set_mtime(session_path, base)
        _set_mtime(sidecar, base)
        self.assertIsNone(
            sync_engine._join_sidecar_context_window({"taskId": "task-1"}, session_path)
        )

    def test_out_of_window_returns_none(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        sidecar = self._sidecar(d, {"taskId": "task-1", "contextWindow": "1M"})
        base = 1_000_000.0
        _set_mtime(session_path, base)
        _set_mtime(sidecar, base + 120)  # > ±60s
        self.assertIsNone(
            sync_engine._join_sidecar_context_window({"taskId": "task-1"}, session_path)
        )

    def test_no_correlation_ids_returns_none(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        self._sidecar(d, {"taskId": "task-1", "contextWindow": "1M"})
        self.assertIsNone(sync_engine._join_sidecar_context_window({}, session_path))

    def test_flag_disabled_returns_none(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        sidecar = self._sidecar(d, {"taskId": "task-1", "contextWindow": "1M"})
        base = 1_000_000.0
        _set_mtime(session_path, base)
        _set_mtime(sidecar, base)
        with patch.object(sync_engine.config, "SIDECAR_CONTEXT_JOIN_ENABLED", False):
            self.assertIsNone(
                sync_engine._join_sidecar_context_window({"taskId": "task-1"}, session_path)
            )

    def test_missing_sidecar_returns_none_no_raise(self) -> None:
        d = self._tmpdir()
        session_path = self._session_file(d)
        # No workflow.json written at all.
        self.assertIsNone(
            sync_engine._join_sidecar_context_window({"taskId": "task-1"}, session_path)
        )


class LinkageSurvivesNullSidecarTests(unittest.TestCase):
    """AC-5.2: grouping is identical with and without a sidecar (modulo ctx window)."""

    def _write_session(self, directory: Path) -> Path:
        path = directory / "session.jsonl"
        lines = [
            {
                "type": "assistant",
                "timestamp": "2026-02-16T10:00:00Z",
                "uuid": "a1",
                "taskId": "task-1",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-4-8[1m]",
                    "usage": {"input_tokens": 5, "output_tokens": 7},
                    "content": [{"type": "text", "text": "hi"}],
                },
            }
        ]
        path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        return path

    def test_grouping_identical_with_and_without_sidecar(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        session_path = self._write_session(d)

        # WITHOUT sidecar: parse + (attempted) join finds nothing.
        session = parse_session_file(session_path)
        assert session is not None
        payload_without = session.model_dump()
        cw_without = sync_engine._join_sidecar_context_window(payload_without, session_path)
        self.assertIsNone(cw_without)

        # WITH sidecar: same session file, now a matching workflow.json exists.
        sidecar = d / "workflow.json"
        sidecar.write_text(json.dumps({"taskId": "task-1", "contextWindow": "1m"}), encoding="utf-8")
        base = os.stat(session_path).st_mtime
        _set_mtime(sidecar, base)
        cw_with = sync_engine._join_sidecar_context_window(payload_without, session_path)
        self.assertEqual(cw_with, "1M")

        # Linkage fields are IDENTICAL; only context_window changes.
        for field in ("id", "rootSessionId", "workflowId", "subagentParentId", "parentSessionId"):
            self.assertEqual(
                payload_without.get(field),
                session.model_dump().get(field),
                msg=f"{field} must not depend on the sidecar",
            )
        self.assertNotEqual(cw_without, cw_with)


if __name__ == "__main__":
    unittest.main()
