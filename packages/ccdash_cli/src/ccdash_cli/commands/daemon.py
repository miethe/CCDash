"""Typer sub-commands for the CCDash local ingest daemon.

Sub-commands
------------
start       Run the daemon in the foreground (use a supervisor to background it).
status      Show last-reported daemon state from the local status file.
install     Print a platform-appropriate supervisor unit template to stdout.
uninstall   Print the matching disable/remove commands for the current platform.
"""
from __future__ import annotations

import asyncio
import json
import platform
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

daemon_app = typer.Typer(help="Local session ingest daemon.")

# Status file default (mirrors DaemonConfig default).
_DEFAULT_STATUS_PATH = Path.home() / ".local" / "state" / "ccdash" / "daemon.status"


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


@daemon_app.command("start")
def daemon_start(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to daemon.toml config file."),
    ] = None,
) -> None:
    """Start the ingest daemon in the foreground.

    The daemon tails JSONL session files and POSTs NDJSON batches to the
    remote CCDash server.  For production use, wrap this command in a
    launchd/systemd/Task-Scheduler supervisor unit (see: ccdash daemon install).

    Configuration is read from ``~/.config/ccdash/daemon.toml`` by default.
    Required fields: server_url, token, project_id, sessions_dir.
    """
    from ccdash_cli.daemon.config import DaemonConfigError, load_config
    from ccdash_cli.daemon.runner import run_daemon

    try:
        config = load_config(config_path)
    except DaemonConfigError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"starting daemon on {config.sessions_dir} → {config.server_url}",
        err=True,
    )

    try:
        asyncio.run(run_daemon(config))
    except KeyboardInterrupt:
        typer.echo("Daemon stopped.", err=True)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@daemon_app.command("status")
def daemon_status(
    status_path: Annotated[
        Optional[Path],
        typer.Option("--status-file", help="Path to daemon status file."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON instead of human-readable text."),
    ] = False,
) -> None:
    """Show the last-reported daemon status.

    Reads the local status file written by the daemon after each flush batch.
    If the daemon has never run, prints an informational message.
    """
    path = status_path or _DEFAULT_STATUS_PATH

    if not path.exists():
        typer.echo("daemon has never reported status")
        return

    try:
        raw = path.read_text(encoding="utf-8")
        data: dict = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(f"Error reading status file {path}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    # Human-readable output.
    last_batch = data.get("last_batch_at", "unknown")
    accepted = data.get("accepted_total", 0)
    rejected = data.get("rejected_total", 0)
    deadlettered = data.get("deadlettered_total", 0)
    buffer_depth = data.get("buffer_depth", 0)
    last_error = data.get("last_error")

    typer.echo(f"Last batch at:     {last_batch}")
    typer.echo(f"Accepted total:    {accepted}")
    typer.echo(f"Rejected total:    {rejected}")
    typer.echo(f"Dead-lettered:     {deadlettered}")
    typer.echo(f"Buffer depth:      {buffer_depth} event(s) pending")
    if last_error:
        typer.echo(f"Last error:        {last_error}")
    else:
        typer.echo("Last error:        none")


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


@daemon_app.command("install")
def daemon_install() -> None:
    """Print a supervisor unit template for the current platform.

    Output is printed to stdout so you can review it before installing.
    CCDash does NOT auto-write system files — copy the template to the
    location indicated in the comments and follow the activation instructions.

    Supported platforms:
        macOS   → launchd plist (~/Library/LaunchAgents/)
        Linux   → systemd --user service (~/.config/systemd/user/)
        Windows → schtasks command (Task Scheduler)
    """
    system = platform.system().lower()

    if system == "darwin":
        _print_launchd_template()
    elif system == "linux":
        _print_systemd_template()
    elif system == "windows":
        _print_schtasks_template()
    else:
        typer.echo(
            f"Unsupported platform: {platform.system()}. "
            "Manually configure your supervisor to run: ccdash daemon start",
            err=True,
        )
        raise typer.Exit(code=1)


def _print_launchd_template() -> None:
    """Print a launchd plist for macOS."""
    python_path = sys.executable
    typer.echo(
        f"""# macOS launchd plist for the CCDash ingest daemon.
#
# Installation:
#   1. Save this file to: ~/Library/LaunchAgents/io.ccdash.daemon.plist
#   2. Load it:           launchctl bootstrap gui/$UID ~/Library/LaunchAgents/io.ccdash.daemon.plist
#   3. Verify:            launchctl print gui/$UID/io.ccdash.daemon
#
# To stop:
#   launchctl bootout gui/$UID/io.ccdash.daemon
#
# Logs are written to ~/Library/Logs/ccdash-daemon.log

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.ccdash.daemon</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>ccdash_cli.main</string>
        <string>daemon</string>
        <string>start</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${{HOME}}/Library/Logs/ccdash-daemon.log</string>

    <key>StandardErrorPath</key>
    <string>${{HOME}}/Library/Logs/ccdash-daemon.log</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
"""
    )


def _print_systemd_template() -> None:
    """Print a systemd --user service unit for Linux."""
    python_path = sys.executable
    typer.echo(
        f"""# systemd --user service unit for the CCDash ingest daemon.
#
# Installation:
#   1. Create the directory (if needed):
#        mkdir -p ~/.config/systemd/user/
#   2. Save this file to:
#        ~/.config/systemd/user/ccdash-daemon.service
#   3. Enable and start:
#        systemctl --user daemon-reload
#        systemctl --user enable --now ccdash-daemon
#
# To stop:
#   systemctl --user stop ccdash-daemon
#   systemctl --user disable ccdash-daemon
#
# View logs:
#   journalctl --user -u ccdash-daemon -f

[Unit]
Description=CCDash local ingest daemon
After=network.target

[Service]
Type=simple
ExecStart={python_path} -m ccdash_cli.main daemon start
Restart=on-failure
RestartSec=10s
# Logs go to the systemd journal automatically.
# To redirect to a file, add:
#   StandardOutput=append:%{{home}}/.local/state/ccdash/daemon.log
#   StandardError=append:%{{home}}/.local/state/ccdash/daemon.log

[Install]
WantedBy=default.target
"""
    )


def _print_schtasks_template() -> None:
    """Print schtasks commands for Windows Task Scheduler."""
    python_path = sys.executable
    typer.echo(
        f"""# Windows Task Scheduler setup for the CCDash ingest daemon.
#
# Run the following commands in an elevated (Administrator) PowerShell
# or Command Prompt to register a logon task:
#
# NOTE: The daemon runs only while a user session is active.
#       For unattended operation consider a Windows Service instead.

:: Create the task (runs at logon for the current user):
schtasks /create ^
  /tn "CCDash Daemon" ^
  /tr "\"{python_path}\" -m ccdash_cli.main daemon start" ^
  /sc onlogon ^
  /ru "%USERNAME%" ^
  /rl limited ^
  /f

:: Start it immediately (optional):
schtasks /run /tn "CCDash Daemon"

:: To stop:
schtasks /end /tn "CCDash Daemon"

:: To remove:
schtasks /delete /tn "CCDash Daemon" /f
"""
    )


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@daemon_app.command("uninstall")
def daemon_uninstall() -> None:
    """Print the supervisor disable/remove commands for the current platform.

    Like ``install``, this command prints instructions only — it does NOT
    modify any system files.
    """
    system = platform.system().lower()

    if system == "darwin":
        typer.echo(
            """# macOS — unload and remove the launchd plist:

launchctl bootout gui/$UID/io.ccdash.daemon
rm ~/Library/LaunchAgents/io.ccdash.daemon.plist
"""
        )
    elif system == "linux":
        typer.echo(
            """# Linux — disable and remove the systemd --user unit:

systemctl --user stop ccdash-daemon
systemctl --user disable ccdash-daemon
rm ~/.config/systemd/user/ccdash-daemon.service
systemctl --user daemon-reload
"""
        )
    elif system == "windows":
        typer.echo(
            """:: Windows — delete the scheduled task:

schtasks /end /tn "CCDash Daemon"
schtasks /delete /tn "CCDash Daemon" /f
"""
        )
    else:
        typer.echo(
            "Unsupported platform. Manually remove the supervisor unit you created.",
            err=True,
        )
