"""Session parser registry for platform-specific implementations."""
from __future__ import annotations

from pathlib import Path

from backend.models import AgentSession
from backend.parsers.platforms.claude_code import parser as claude_code_parser


def parse_session_file(path: Path) -> AgentSession | None:
    """Parse a session file by delegating to the matching platform parser.

    Current implementation routes Claude Code `.jsonl` transcripts to the
    Claude-specific parser module. Additional platforms can be registered here.
    """
    if path.suffix.lower() == ".jsonl":
        return claude_code_parser.parse_session_file(path)
    return None


def scan_sessions(sessions_dir: Path, max_files: int = 50) -> list[AgentSession]:
    """Scan and parse recent session files using the registry parser."""
    sessions: list[AgentSession] = []
    if not sessions_dir.exists():
        return sessions

    jsonl_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:max_files]

    for path in jsonl_files:
        session = parse_session_file(path)
        if session:
            sessions.append(session)

    return sessions

