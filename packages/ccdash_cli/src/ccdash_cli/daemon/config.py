"""Daemon configuration loader.

Config file location: ``~/.config/ccdash/daemon.toml`` (XDG-compliant).
All fields can be overridden by environment variables (see :func:`load_config`).

Required fields (no default):
    server_url, token, project_id, sessions_dir

Optional fields with defaults:
    flush_interval_seconds (5.0), max_batch_events (100), max_retries (10),
    buffer_root, deadletter_root, status_path
"""
from __future__ import annotations

import dataclasses
import os
import tomllib
from pathlib import Path
from typing import Any


class DaemonConfigError(Exception):
    """Raised when the daemon configuration is missing required fields."""


_STATE_ROOT = Path.home() / ".local" / "state" / "ccdash"
_CONFIG_ROOT = Path.home() / ".config" / "ccdash"


@dataclasses.dataclass
class DaemonConfig:
    """Resolved daemon configuration.

    Attributes:
        server_url:             Base URL of the remote CCDash server.
        token:                  Bearer token for authentication.
        project_id:             CCDash project identifier sent in the
                                ``x-ccdash-project-id`` request header.
        sessions_dir:           Directory to watch for JSONL session files.
        flush_interval_seconds: How often to flush the in-memory queue (default 5s).
        max_batch_events:       Maximum events per POST batch (default 100).
        buffer_root:            On-disk WAL buffer directory.
        deadletter_root:        Directory for events that permanently failed delivery.
        status_path:            Path to the JSON status file written after each flush.
        max_retries:            Maximum POST retry attempts per batch (default 10).
    """

    server_url: str
    token: str
    project_id: str
    sessions_dir: Path
    flush_interval_seconds: float = 5.0
    max_batch_events: int = 100
    buffer_root: Path = dataclasses.field(
        default_factory=lambda: _STATE_ROOT / "buffer"
    )
    deadletter_root: Path = dataclasses.field(
        default_factory=lambda: _STATE_ROOT / "deadletter"
    )
    status_path: Path = dataclasses.field(
        default_factory=lambda: _STATE_ROOT / "daemon.status"
    )
    max_retries: int = 10

    def __post_init__(self) -> None:
        # Coerce Path fields if they arrived as strings (e.g. from TOML)
        if not isinstance(self.sessions_dir, Path):
            self.sessions_dir = Path(self.sessions_dir)
        if not isinstance(self.buffer_root, Path):
            self.buffer_root = Path(self.buffer_root)
        if not isinstance(self.deadletter_root, Path):
            self.deadletter_root = Path(self.deadletter_root)
        if not isinstance(self.status_path, Path):
            self.status_path = Path(self.status_path)


def load_config(config_path: Path | None = None) -> DaemonConfig:
    """Load :class:`DaemonConfig` from TOML + environment variable overrides.

    Resolution order (highest priority first):
        1. Environment variables (``CCDASH_DAEMON_*``).
        2. ``~/.config/ccdash/daemon.toml`` (or *config_path*).
        3. Dataclass defaults.

    Environment variable overrides:
        ``CCDASH_DAEMON_SERVER_URL``   → server_url
        ``CCDASH_DAEMON_TOKEN``        → token
        ``CCDASH_DAEMON_PROJECT_ID``   → project_id
        ``CCDASH_DAEMON_SESSIONS_DIR`` → sessions_dir
        ``CCDASH_DAEMON_FLUSH_SECONDS`` → flush_interval_seconds

    Args:
        config_path: Explicit path to the TOML file.  Defaults to
            ``~/.config/ccdash/daemon.toml``.

    Returns:
        A fully-resolved :class:`DaemonConfig`.

    Raises:
        DaemonConfigError: When required fields are absent from both the TOML
            file and the environment.
    """
    resolved_path = config_path or (_CONFIG_ROOT / "daemon.toml")

    toml_data: dict[str, Any] = {}
    if resolved_path.exists():
        try:
            with resolved_path.open("rb") as fh:
                toml_data = tomllib.load(fh)
        except Exception as exc:
            raise DaemonConfigError(
                f"Cannot read daemon config at {resolved_path}: {exc}"
            ) from exc

    daemon_section: dict[str, Any] = toml_data.get("daemon", toml_data)

    def _get(field: str, env_var: str, *, required: bool = False) -> str | None:
        env_val = os.environ.get(env_var)
        if env_val:
            return env_val
        val = daemon_section.get(field)
        if val is not None:
            return str(val)
        if required:
            raise DaemonConfigError(
                f"Required daemon config field '{field}' is missing.\n"
                f"  Set it in {resolved_path} under [daemon] or via the "
                f"{env_var} environment variable."
            )
        return None

    server_url = _get("server_url", "CCDASH_DAEMON_SERVER_URL", required=True)
    token = _get("token", "CCDASH_DAEMON_TOKEN", required=True)
    project_id = _get("project_id", "CCDASH_DAEMON_PROJECT_ID", required=True)
    sessions_dir_raw = _get("sessions_dir", "CCDASH_DAEMON_SESSIONS_DIR", required=True)

    assert server_url and token and project_id and sessions_dir_raw

    # Optional numeric fields
    flush_raw = os.environ.get("CCDASH_DAEMON_FLUSH_SECONDS") or daemon_section.get(
        "flush_interval_seconds"
    )
    flush_interval = float(flush_raw) if flush_raw is not None else 5.0

    max_batch = int(daemon_section.get("max_batch_events", 100))
    max_retries = int(daemon_section.get("max_retries", 10))

    # Optional path fields
    def _path(field: str, default: Path) -> Path:
        val = daemon_section.get(field)
        return Path(val) if val else default

    buffer_root = _path("buffer_root", _STATE_ROOT / "buffer")
    deadletter_root = _path("deadletter_root", _STATE_ROOT / "deadletter")
    status_path = _path("status_path", _STATE_ROOT / "daemon.status")

    return DaemonConfig(
        server_url=server_url.rstrip("/"),
        token=token,
        project_id=project_id,
        sessions_dir=Path(sessions_dir_raw),
        flush_interval_seconds=flush_interval,
        max_batch_events=max_batch,
        buffer_root=buffer_root,
        deadletter_root=deadletter_root,
        status_path=status_path,
        max_retries=max_retries,
    )
