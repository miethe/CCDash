"""Phase 11 (T11-004): launch-time capture sidecar ingestion tests.

Covers:
- ``backend/parsers/capture_sidecar.py`` — pure parse_capture_sidecar logic
- ``backend/parsers/platforms/claude_code/parser.py`` — _collect_capture_sidecar
  integration (sidecar present → fields populated; absent → all null; partial → partial)
- Model → session_data camelCase mapping assertion (confirms sync_engine seam)

Run as a NAMED file::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_capture_sidecar_ingestion.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.capture_sidecar import CaptureSidecar, parse_capture_sidecar
from backend.parsers.sessions import parse_session_file


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_SESSION_ID = "3e67572b-dc6b-4750-a09e-14a4e34f67a5"

_MINIMAL_JSONL_ENTRY = {
    "type": "assistant",
    "timestamp": "2026-06-11T18:30:00Z",
    "uuid": "msg-uuid-001",
    "parentUuid": None,
    "message": {
        "role": "assistant",
        "model": "claude-opus-4-5",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "content": [{"type": "text", "text": "hello"}],
    },
}

_ICA_SIDECAR_FULL = {
    "schemaVersion": 1,
    "sessionId": _SESSION_ID,
    "launcher": "ica-claude.sh",
    "profile": "ica-delegate",
    "effortTier": None,
    "modelVariant": "claude-opus-4-8[1m]",
    "capturedAt": "2026-06-11T18:30:00Z",
}


def _write_jsonl(directory: Path, stem: str, entries: list[dict]) -> Path:
    path = directory / f"{stem}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


def _write_json(directory: Path, name: str, content: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Unit tests: pure capture_sidecar module
# ──────────────────────────────────────────────────────────────────────────────

class CaptureSidecarParserTests(unittest.TestCase):
    def _tmpdir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    # ── happy path ────────────────────────────────────────────────────────────

    def test_full_sidecar_returns_all_fields(self) -> None:
        d = self._tmpdir()
        path = _write_json(d, f"{_SESSION_ID}.capture.json", _ICA_SIDECAR_FULL)
        result = parse_capture_sidecar(path)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.launcher, "ica-claude.sh")
        self.assertEqual(result.profile, "ica-delegate")
        self.assertIsNone(result.effort_tier)          # null in fixture
        self.assertEqual(result.model_variant, "claude-opus-4-8[1m]")
        self.assertEqual(result.session_id, _SESSION_ID)
        self.assertEqual(result.schema_version, 1)

    def test_partial_sidecar_only_present_fields_populated(self) -> None:
        """Partial sidecars are valid — only present fields populate."""
        d = self._tmpdir()
        partial = {
            "schemaVersion": 1,
            "sessionId": _SESSION_ID,
            "profile": "ica-delegate",
            # launcher / effortTier / modelVariant absent
        }
        path = _write_json(d, f"{_SESSION_ID}.capture.json", partial)
        result = parse_capture_sidecar(path)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.profile, "ica-delegate")
        self.assertIsNone(result.launcher)
        self.assertIsNone(result.effort_tier)
        self.assertIsNone(result.model_variant)

    # ── resilience ────────────────────────────────────────────────────────────

    def test_missing_file_returns_none(self) -> None:
        d = self._tmpdir()
        result = parse_capture_sidecar(d / "nonexistent.capture.json")
        self.assertIsNone(result)

    def test_malformed_json_returns_none(self) -> None:
        d = self._tmpdir()
        path = d / "bad.capture.json"
        path.write_text("{not valid json", encoding="utf-8")
        result = parse_capture_sidecar(path)
        self.assertIsNone(result)

    def test_json_array_root_returns_none(self) -> None:
        d = self._tmpdir()
        path = d / "array.capture.json"
        path.write_text("[]", encoding="utf-8")
        result = parse_capture_sidecar(path)
        self.assertIsNone(result)

    def test_unsupported_schema_version_returns_none(self) -> None:
        d = self._tmpdir()
        content = dict(_ICA_SIDECAR_FULL)
        content["schemaVersion"] = 99
        path = _write_json(d, "sid.capture.json", content)
        result = parse_capture_sidecar(path)
        self.assertIsNone(result)

    def test_missing_schema_version_returns_none(self) -> None:
        d = self._tmpdir()
        content = {k: v for k, v in _ICA_SIDECAR_FULL.items() if k != "schemaVersion"}
        path = _write_json(d, "sid.capture.json", content)
        result = parse_capture_sidecar(path)
        self.assertIsNone(result)

    def test_never_raises_on_unreadable_file(self) -> None:
        """parse_capture_sidecar must never raise — even on read errors."""
        result = parse_capture_sidecar(Path("/no/such/path/at/all.capture.json"))
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────────────
# Integration tests: parser → AgentSession field promotion
# ──────────────────────────────────────────────────────────────────────────────

class CaptureIngestionParserTests(unittest.TestCase):
    def _tmpdir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_sidecar_present_fields_promoted_to_session(self) -> None:
        """Co-located sidecar → 4 fields present on AgentSession (profile=ica-delegate)."""
        d = self._tmpdir()
        jsonl_path = _write_jsonl(d, _SESSION_ID, [_MINIMAL_JSONL_ENTRY])
        _write_json(d, f"{_SESSION_ID}.capture.json", _ICA_SIDECAR_FULL)

        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.launcher, "ica-claude.sh")
        self.assertEqual(session.profile, "ica-delegate")
        self.assertIsNone(session.effortTier)            # null in fixture
        self.assertEqual(session.modelVariant, "claude-opus-4-8[1m]")

    def test_no_sidecar_all_capture_fields_null(self) -> None:
        """Missing sidecar → launcher/profile/effortTier/modelVariant are all null."""
        d = self._tmpdir()
        jsonl_path = _write_jsonl(d, _SESSION_ID, [_MINIMAL_JSONL_ENTRY])
        # No .capture.json written.

        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertIsNone(session.launcher)
        self.assertIsNone(session.profile)
        self.assertIsNone(session.effortTier)
        self.assertIsNone(session.modelVariant)

    def test_partial_sidecar_only_present_fields_on_session(self) -> None:
        """Partial sidecar → only populated fields appear; others stay null."""
        d = self._tmpdir()
        jsonl_path = _write_jsonl(d, _SESSION_ID, [_MINIMAL_JSONL_ENTRY])
        partial = {
            "schemaVersion": 1,
            "sessionId": _SESSION_ID,
            "launcher": "ica-claude.sh",
            # profile / effortTier / modelVariant absent
        }
        _write_json(d, f"{_SESSION_ID}.capture.json", partial)

        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.launcher, "ica-claude.sh")
        self.assertIsNone(session.profile)
        self.assertIsNone(session.effortTier)
        self.assertIsNone(session.modelVariant)

    def test_session_id_mismatch_fields_remain_null(self) -> None:
        """Sidecar sessionId != JSONL stem → sidecar ignored, all fields null."""
        d = self._tmpdir()
        jsonl_path = _write_jsonl(d, _SESSION_ID, [_MINIMAL_JSONL_ENTRY])
        mismatched = dict(_ICA_SIDECAR_FULL)
        mismatched["sessionId"] = "00000000-0000-0000-0000-000000000000"
        _write_json(d, f"{_SESSION_ID}.capture.json", mismatched)

        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertIsNone(session.launcher)
        self.assertIsNone(session.profile)
        self.assertIsNone(session.effortTier)
        self.assertIsNone(session.modelVariant)


# ──────────────────────────────────────────────────────────────────────────────
# Mapping tests: AgentSession.model_dump() → session_data camelCase seam
# ──────────────────────────────────────────────────────────────────────────────

class AgentSessionModelDumpMappingTests(unittest.TestCase):
    """Confirm the model_dump() output carries the correct camelCase keys that
    the session repo reads with session_data.get("launcher") etc. (T11-003/004
    seam).  If these keys are wrong the DB never sees the values despite the
    COALESCE guard — so we make this contract explicit.
    """

    def _tmpdir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_model_dump_carries_camel_case_capture_keys(self) -> None:
        """model_dump() must include launcher/profile/effortTier/modelVariant."""
        d = self._tmpdir()
        jsonl_path = _write_jsonl(d, _SESSION_ID, [_MINIMAL_JSONL_ENTRY])
        _write_json(d, f"{_SESSION_ID}.capture.json", _ICA_SIDECAR_FULL)

        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session)
        assert session is not None

        dumped = session.model_dump()
        # Confirm camelCase keys are present (repo uses these exact keys).
        self.assertIn("launcher", dumped)
        self.assertIn("profile", dumped)
        self.assertIn("effortTier", dumped)
        self.assertIn("modelVariant", dumped)

        # Confirm values survived the round-trip.
        self.assertEqual(dumped["launcher"], "ica-claude.sh")
        self.assertEqual(dumped["profile"], "ica-delegate")
        self.assertIsNone(dumped["effortTier"])
        self.assertEqual(dumped["modelVariant"], "claude-opus-4-8[1m]")

        # Confirm snake_case variants are NOT the keys the repo reads.
        # (They would be silently dropped if present as a separate key;
        # this guard catches a future accidental double-write.)
        self.assertNotIn("effort_tier", dumped)
        self.assertNotIn("model_variant", dumped)


if __name__ == "__main__":
    unittest.main()
