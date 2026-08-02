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


@pytest.fixture(autouse=True)
def _isolate_settings_lookup(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Isolate the `effortLevel` settings fallback from real machine state.

    Without this, `_settings_effort_level` falls through to the real
    `~/.claude/settings.json` on the machine running the tests (which may
    carry a real `effortLevel`), silently breaking any test asserting
    `effortTier is None`. Applied to every test in this module — including
    the ones written before this fallback existed.

    Isolated dirs are allocated OUTSIDE the per-test `tmp_path` (via
    `tmp_path_factory`) so they don't show up in assertions like
    ``list(tmp_path.iterdir()) == []``.

    Covers both lookup paths: `Path.home()` is stubbed directly (for tests
    that pass a literal env dict with no `CLAUDE_CONFIG_DIR` key), and
    `CLAUDE_CONFIG_DIR` is also exported into `os.environ` (for tests that
    pass `dict(os.environ)`). `Path.cwd()` is pinned to `tmp_path` so the
    project-settings probe (`.claude/settings.local.json` / `.claude/settings.json`)
    never sees this repo's own `.claude/` directory.

    Returns the isolated home dir so tests can write a conflicting
    `<home>/.claude/settings.json` into it to prove precedence/exclusion
    behavior (see AC4 exclusion/positive tests below).
    """
    isolated_home = tmp_path_factory.mktemp("isolated_home")
    isolated_config_dir = tmp_path_factory.mktemp("isolated_claude_config")
    monkeypatch.setattr(_mod.Path, "home", staticmethod(lambda: isolated_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(isolated_config_dir))
    monkeypatch.chdir(tmp_path)
    return isolated_home


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


class TestSettingsEffortLevelFallback:
    """AC1-AC10: `effortLevel` settings.json fallback for `effortTier`."""

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_ac1_env_var_wins_over_settings(self, tmp_path: Path) -> None:
        """CCDASH_LAUNCH_EFFORT set + settings has effortLevel → env wins."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        project_dir = tmp_path / "project"
        self._write_json(
            project_dir / ".claude" / "settings.json", {"effortLevel": "low"}
        )

        result = write_capture_sidecar(
            {**_make_payload(_ICA_SESSION_ID, str(jsonl)), "cwd": str(project_dir)},
            {"CCDASH_LAUNCH_EFFORT": "high"},
        )
        data = json.loads(result.read_text())
        assert data["effortTier"] == "high"

    def test_ac2_user_settings_used_when_env_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No env var + user settings.json has effortLevel → used."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        self._write_json(config_dir / "settings.json", {"effortLevel": "medium"})
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        data = json.loads(result.read_text())
        assert data["effortTier"] == "medium"

    def test_ac3_precedence_local_over_project_over_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings.local.json > settings.json (project) > user settings.json."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        project_dir = tmp_path / "project"
        config_dir = tmp_path / "user_config"
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        # Hop 1: only user settings.json → user value wins
        self._write_json(config_dir / "settings.json", {"effortLevel": "user-tier"})
        result = write_capture_sidecar(
            {**_make_payload(_ICA_SESSION_ID, str(jsonl)), "cwd": str(project_dir)},
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] == "user-tier"

        # Hop 2: add project settings.json → project value wins over user
        self._write_json(
            project_dir / ".claude" / "settings.json", {"effortLevel": "project-tier"}
        )
        result = write_capture_sidecar(
            {**_make_payload(_ICA_SESSION_ID, str(jsonl)), "cwd": str(project_dir)},
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] == "project-tier"

        # Hop 3: add project settings.local.json → local value wins over project
        self._write_json(
            project_dir / ".claude" / "settings.local.json",
            {"effortLevel": "local-tier"},
        )
        result = write_capture_sidecar(
            {**_make_payload(_ICA_SESSION_ID, str(jsonl)), "cwd": str(project_dir)},
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] == "local-tier"

    def test_ac4_claude_config_dir_overrides_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE_CONFIG_DIR set → user settings read from there, not ~/.claude."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        custom_config_dir = tmp_path / "custom_config"
        self._write_json(
            custom_config_dir / "settings.json", {"effortLevel": "custom-dir-tier"}
        )
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(custom_config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] == "custom-dir-tier"

    def test_ac4b_claude_config_dir_set_excludes_home_settings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _isolate_settings_lookup: Path,
    ) -> None:
        """CLAUDE_CONFIG_DIR set → ~/.claude/settings.json is NEVER consulted,
        even when it holds a conflicting effortLevel value.

        Proves exclusion (not just "a custom dir also works"): a regression
        that checked both CLAUDE_CONFIG_DIR and home would leak the home
        value here and fail this assertion.
        """
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        isolated_home = _isolate_settings_lookup
        self._write_json(
            isolated_home / ".claude" / "settings.json",
            {"effortLevel": "HOME_SHOULD_BE_IGNORED"},
        )

        # CLAUDE_CONFIG_DIR points at a dir whose settings.json is absent.
        empty_config_dir = tmp_path / "empty_config_dir_no_settings"
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty_config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert result is not None
        assert json.loads(result.read_text())["effortTier"] is None

    def test_ac4c_home_settings_used_when_config_dir_key_absent_from_env(
        self,
        tmp_path: Path,
        _isolate_settings_lookup: Path,
    ) -> None:
        """No CLAUDE_CONFIG_DIR key in the passed env dict → falls back to
        the plain `Path.home() / ".claude" / "settings.json"` branch.

        Restores coverage of that branch, which the autouse isolation
        fixture otherwise removes entirely (every other test either sets
        CLAUDE_CONFIG_DIR explicitly or passes an env dict lacking it only
        incidentally).
        """
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        isolated_home = _isolate_settings_lookup
        self._write_json(
            isolated_home / ".claude" / "settings.json",
            {"effortLevel": "home-tier"},
        )

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {},  # no CLAUDE_CONFIG_DIR key at all
        )
        assert result is not None
        assert json.loads(result.read_text())["effortTier"] == "home-tier"

    def test_ac5_malformed_settings_nulls_only_effort_tier(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Malformed settings JSON → effortTier None, other fields still written."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            {
                "CCDASH_LAUNCHER": "ica-claude.sh",
                "CCDASH_LAUNCH_PROFILE": "ica-delegate",
                "CCDASH_LAUNCH_MODEL": "claude-opus-4-8[1m]",
                "CLAUDE_CONFIG_DIR": str(config_dir),
            },
        )
        assert result is not None
        data = json.loads(result.read_text())
        assert data["effortTier"] is None
        assert data["launcher"] == "ica-claude.sh"
        assert data["profile"] == "ica-delegate"
        assert data["modelVariant"] == "claude-opus-4-8[1m]"

    def test_ac6_no_settings_files_effort_tier_none(self, tmp_path: Path) -> None:
        """No settings files at all → effortTier None."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] is None

    @pytest.mark.parametrize("raw_value", ["", "   "])
    def test_ac7_empty_or_whitespace_effort_level_is_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_value: str
    ) -> None:
        """effortLevel of "" or "   " → None, never passed through."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        self._write_json(config_dir / "settings.json", {"effortLevel": raw_value})
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] is None

    def test_ac8_unknown_tier_value_passes_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """effortLevel: "ultra" (not in any fixed allowlist) → passes through."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        self._write_json(config_dir / "settings.json", {"effortLevel": "ultra"})
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] == "ultra"

    @pytest.mark.parametrize("raw_value", [123, {"a": 1}, None, True, [], ["high"]])
    def test_ac9_non_string_effort_level_is_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_value
    ) -> None:
        """Non-string effortLevel (int/dict/null/bool/list) → None."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        self._write_json(config_dir / "settings.json", {"effortLevel": raw_value})
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        assert json.loads(result.read_text())["effortTier"] is None

    def test_ac10_sidecar_still_has_exactly_seven_keys_in_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding the fallback must not change the pinned sidecar key set OR
        their order — a set comparison would miss a reordering regression."""
        jsonl = tmp_path / f"{_ICA_SESSION_ID}.jsonl"
        jsonl.touch()
        config_dir = tmp_path / "user_config"
        self._write_json(config_dir / "settings.json", {"effortLevel": "medium"})
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

        result = write_capture_sidecar(
            _make_payload(_ICA_SESSION_ID, str(jsonl)),
            dict(os.environ),
        )
        data = json.loads(result.read_text())
        assert list(data.keys()) == [
            "schemaVersion", "sessionId", "launcher", "profile",
            "effortTier", "modelVariant", "capturedAt",
        ]
        assert data["schemaVersion"] == 1


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
