"""Unit tests for scripts/hooks/ccdash_capture_session_start.py (T11-002).

Covers:
- Synthetic payload + env → sidecar JSON matches schema with profile=ica-delegate
- Missing env vars → null fields (no defaults synthesised)
- Unwritable target directory → process exits 0, no exception raised
- Fallback path (no transcript_path) → data/capture/<sid>.capture.json
- Empty/missing session_id → None returned, no sidecar written
- Partial env → only set vars populated, rest null
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the hook module from the scripts/hooks directory.
# We use importlib so the test does not require scripts/hooks/__init__.py and
# the module never needs to be on sys.path permanently.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOK_PATH = _REPO_ROOT / "scripts" / "hooks" / "ccdash_capture_session_start.py"

spec = importlib.util.spec_from_file_location(
    "ccdash_capture_session_start", _HOOK_PATH
)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

write_capture_sidecar = _mod.write_capture_sidecar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ICA_SESSION_ID = "3e67572b-dc6b-4750-a09e-14a4e34f67a5"

_FULL_ENV: dict[str, str] = {
    "CCDASH_LAUNCH_PROFILE": "ica-delegate",
    "CCDASH_LAUNCHER": "ica-claude.sh",
    "CCDASH_LAUNCH_EFFORT": "high",
    "CCDASH_LAUNCH_MODEL": "claude-opus-4-8[1m]",
}


def _make_payload(session_id: str, transcript_path: str | None = None) -> dict:
    p: dict = {"session_id": session_id}
    if transcript_path is not None:
        p["transcript_path"] = transcript_path
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteCaptureSidecar:
    """Core writer tests."""

    def test_full_env_produces_valid_schema(self, tmp_path: Path) -> None:
        """Synthetic payload + full env → sidecar matches schema exactly."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            _FULL_ENV,
        )

        assert result is not None
        assert result == tmp_path / f"{_ICA_SESSION_ID}.capture.json"
        assert result.exists()

        data = json.loads(result.read_text())

        # Required structure
        assert data["schemaVersion"] == 1
        assert data["sessionId"] == _ICA_SESSION_ID

        # ica-delegate profile MUST be present
        assert data["profile"] == "ica-delegate"
        assert data["launcher"] == "ica-claude.sh"
        assert data["effortTier"] == "high"
        assert data["modelVariant"] == "claude-opus-4-8[1m]"

        # capturedAt must be an ISO-8601 UTC string
        captured_at = data["capturedAt"]
        assert isinstance(captured_at, str)
        assert captured_at.endswith("Z")

        # No extra top-level keys beyond the seven schema fields
        schema_keys = {
            "schemaVersion", "sessionId", "launcher", "profile",
            "effortTier", "modelVariant", "capturedAt",
        }
        assert set(data.keys()) == schema_keys

    def test_missing_env_produces_null_fields(self, tmp_path: Path) -> None:
        """Empty env dict → all optional fields are null, never defaulted."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {},  # no env vars at all
        )

        assert result is not None
        data = json.loads(result.read_text())

        assert data["schemaVersion"] == 1
        assert data["sessionId"] == _ICA_SESSION_ID
        assert data["launcher"] is None
        assert data["profile"] is None
        assert data["effortTier"] is None
        assert data["modelVariant"] is None

    def test_partial_env_only_set_vars_populated(self, tmp_path: Path) -> None:
        """Only CCDASH_LAUNCH_PROFILE set → only profile is non-null."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {"CCDASH_LAUNCH_PROFILE": "ica-delegate"},
        )

        assert result is not None
        data = json.loads(result.read_text())

        assert data["profile"] == "ica-delegate"
        assert data["launcher"] is None
        assert data["effortTier"] is None
        assert data["modelVariant"] is None

    def test_missing_session_id_returns_none(self, tmp_path: Path) -> None:
        """Payload without session_id → returns None, writes nothing."""
        result = write_capture_sidecar(
            {"transcript_path": str(tmp_path / "something.jsonl")},
            _FULL_ENV,
        )
        assert result is None
        assert list(tmp_path.iterdir()) == []

    def test_empty_session_id_returns_none(self, tmp_path: Path) -> None:
        """Empty string session_id → treated as absent → returns None."""
        result = write_capture_sidecar(
            {"session_id": "   ", "transcript_path": str(tmp_path / "x.jsonl")},
            _FULL_ENV,
        )
        assert result is None

    def test_fallback_path_used_when_no_transcript_path(self, tmp_path: Path) -> None:
        """No transcript_path → sidecar lands in data/capture/<sid>.capture.json."""
        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID),  # no transcript_path
            {"CCDASH_LAUNCH_PROFILE": "ica-delegate"},
            fallback_base=tmp_path,
        )

        assert result is not None
        expected = tmp_path / "data" / "capture" / f"{_ICA_SESSION_ID}.capture.json"
        assert result == expected
        assert result.exists()

        data = json.loads(result.read_text())
        assert data["sessionId"] == _ICA_SESSION_ID
        assert data["profile"] == "ica-delegate"

    def test_unwritable_directory_returns_none_exits_zero(self, tmp_path: Path) -> None:
        """Write to a read-only directory → returns None, does NOT raise."""
        locked_dir = tmp_path / "locked"
        locked_dir.mkdir()
        # Create a fake JSONL path inside the locked dir (file need not exist)
        fake_jsonl = locked_dir / f"{_ICA_SESSION_ID}.jsonl"

        # Make the directory read-only (no write permission)
        os.chmod(locked_dir, stat.S_IRUSR | stat.S_IXUSR)

        try:
            # Must not raise; must return None
            result = write_capture_sidecar(
                _make_payload(_ICA_SESSION_ID, str(fake_jsonl)),
                _FULL_ENV,
            )
            assert result is None
        finally:
            # Restore permissions so pytest can clean up tmp_path
            os.chmod(locked_dir, stat.S_IRWXU)

    def test_sidecar_uses_camelcase_transcript_path_key(self, tmp_path: Path) -> None:
        """Hook payload may use camelCase transcriptPath field."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        payload = {
            "session_id": _ICA_SESSION_ID,
            "transcriptPath": str(jsonl),  # camelCase variant
        }
        result = write_capture_sidecar(payload, {"CCDASH_LAUNCH_PROFILE": "ica-delegate"})

        assert result is not None
        assert result == tmp_path / f"{_ICA_SESSION_ID}.capture.json"

    def test_camelcase_sessionid_key_accepted(self, tmp_path: Path) -> None:
        """Hook payload may use camelCase sessionId field."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        payload = {
            "sessionId": _ICA_SESSION_ID,  # camelCase
            "transcript_path": str(jsonl),
        }
        result = write_capture_sidecar(payload, _FULL_ENV)
        assert result is not None
        data = json.loads(result.read_text())
        assert data["sessionId"] == _ICA_SESSION_ID

    def test_idempotent_overwrite(self, tmp_path: Path) -> None:
        """Writing twice with same session_id overwrites the first sidecar."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {"CCDASH_LAUNCH_PROFILE": "first-write"},
        )
        write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {"CCDASH_LAUNCH_PROFILE": "second-write"},
        )

        sidecar = tmp_path / f"{_ICA_SESSION_ID}.capture.json"
        data = json.loads(sidecar.read_text())
        assert data["profile"] == "second-write"


class TestMainEntrypoint:
    """Tests for the __main__ stdin entrypoint."""

    def test_main_exits_zero_on_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin → exits 0 (fail-open)."""
        import io
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))

        with pytest.raises(SystemExit) as exc_info:
            _mod._main()

        assert exc_info.value.code == 0

    def test_main_exits_zero_on_garbage_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Malformed JSON on stdin → exits 0 (fail-open)."""
        import io
        monkeypatch.setattr(sys, "stdin", io.StringIO("NOT-JSON{{{"))

        with pytest.raises(SystemExit) as exc_info:
            _mod._main()

        assert exc_info.value.code == 0

    def test_main_writes_sidecar_from_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid JSON payload on stdin → sidecar written."""
        import io

        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        payload = {
            "session_id": _ICA_SESSION_ID,
            "transcript_path": str(jsonl),
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        monkeypatch.setenv("CCDASH_LAUNCH_PROFILE", "ica-delegate")
        monkeypatch.setenv("CCDASH_LAUNCHER", "ica-claude.sh")
        # Remove keys that should not be set to confirm null semantics
        monkeypatch.delenv("CCDASH_LAUNCH_EFFORT", raising=False)
        monkeypatch.delenv("CCDASH_LAUNCH_MODEL", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            _mod._main()

        assert exc_info.value.code == 0
        sidecar = tmp_path / f"{_ICA_SESSION_ID}.capture.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text())
        assert data["profile"] == "ica-delegate"
        assert data["launcher"] == "ica-claude.sh"
        assert data["effortTier"] is None
        assert data["modelVariant"] is None
