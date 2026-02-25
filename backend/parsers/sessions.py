"""Compatibility wrapper around platform-specific session parsers."""
from __future__ import annotations

from pathlib import Path

from backend.models import AgentSession
from backend.parsers.platforms.registry import parse_session_file as _parse_session_file
from backend.parsers.platforms.registry import scan_sessions as _scan_sessions


def parse_session_file(path: Path) -> AgentSession | None:
    """Parse a single session log file via the parser registry."""
    return _parse_session_file(path)


def scan_sessions(sessions_dir: Path, max_files: int = 50) -> list[AgentSession]:
    """Scan and parse recent session files via the parser registry."""
    return _scan_sessions(sessions_dir, max_files=max_files)
