"""CLI smoke tests for the 'ccdash daemon' sub-command group.

Uses Typer's CliRunner for end-to-end CLI invocation without a real server.
No real network calls are made.
"""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ccdash_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


def test_daemon_help() -> None:
    result = runner.invoke(app, ["daemon", "--help"])
    assert result.exit_code == 0, f"daemon --help failed:\n{result.output}"
    assert "daemon" in result.output.lower()


def test_daemon_start_help() -> None:
    result = runner.invoke(app, ["daemon", "start", "--help"])
    assert result.exit_code == 0, f"daemon start --help failed:\n{result.output}"
    assert "start" in result.output.lower() or "daemon" in result.output.lower()


def test_daemon_status_help() -> None:
    result = runner.invoke(app, ["daemon", "status", "--help"])
    assert result.exit_code == 0, f"daemon status --help failed:\n{result.output}"


def test_daemon_install_help() -> None:
    result = runner.invoke(app, ["daemon", "install", "--help"])
    assert result.exit_code == 0, f"daemon install --help failed:\n{result.output}"


def test_daemon_uninstall_help() -> None:
    result = runner.invoke(app, ["daemon", "uninstall", "--help"])
    assert result.exit_code == 0, f"daemon uninstall --help failed:\n{result.output}"


# ---------------------------------------------------------------------------
# status with no status file
# ---------------------------------------------------------------------------


def test_daemon_status_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the status file does not exist, print the 'never reported' message."""
    ghost_path = tmp_path / "nonexistent.status"
    result = runner.invoke(
        app, ["daemon", "status", "--status-file", str(ghost_path)]
    )
    assert result.exit_code == 0, f"Unexpected exit code:\n{result.output}"
    assert "never reported" in result.output.lower(), (
        f"Expected 'never reported' in output:\n{result.output}"
    )


def test_daemon_status_reads_file(tmp_path: Path) -> None:
    """When status file exists, output must include last_batch_at."""
    status_data = {
        "last_batch_at": "2026-05-19T12:00:00+00:00",
        "accepted_total": 42,
        "rejected_total": 1,
        "deadlettered_total": 0,
        "buffer_depth": 5,
        "last_error": None,
    }
    status_path = tmp_path / "daemon.status"
    status_path.write_text(json.dumps(status_data), encoding="utf-8")

    result = runner.invoke(
        app, ["daemon", "status", "--status-file", str(status_path)]
    )
    assert result.exit_code == 0, f"Unexpected exit code:\n{result.output}"
    assert "42" in result.output
    assert "2026-05-19" in result.output


def test_daemon_status_json_flag(tmp_path: Path) -> None:
    """--json flag must output raw JSON."""
    status_data = {
        "last_batch_at": "2026-05-19T12:00:00+00:00",
        "accepted_total": 7,
        "rejected_total": 0,
        "deadlettered_total": 0,
        "buffer_depth": 0,
        "last_error": None,
    }
    status_path = tmp_path / "daemon.status"
    status_path.write_text(json.dumps(status_data), encoding="utf-8")

    result = runner.invoke(
        app,
        ["daemon", "status", "--status-file", str(status_path), "--json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["accepted_total"] == 7


# ---------------------------------------------------------------------------
# install prints platform template
# ---------------------------------------------------------------------------


def test_daemon_install_prints_template() -> None:
    """install must print a non-empty supervisor template to stdout."""
    result = runner.invoke(app, ["daemon", "install"])
    # On supported platforms (darwin/linux/windows) this should succeed.
    system = platform.system().lower()
    if system in ("darwin", "linux", "windows"):
        assert result.exit_code == 0, (
            f"install exited with code {result.exit_code}:\n{result.output}"
        )
        assert len(result.output.strip()) > 20, "Template output seems too short"

        if system == "darwin":
            assert "launchd" in result.output.lower() or "plist" in result.output.lower()
        elif system == "linux":
            assert "systemd" in result.output.lower() or "[Unit]" in result.output
        elif system == "windows":
            assert "schtasks" in result.output.lower()


def test_daemon_uninstall_prints_commands() -> None:
    """uninstall must print removal commands."""
    result = runner.invoke(app, ["daemon", "uninstall"])
    system = platform.system().lower()
    if system in ("darwin", "linux", "windows"):
        assert result.exit_code == 0
        assert len(result.output.strip()) > 10
