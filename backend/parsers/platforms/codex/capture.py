"""Bounded native metadata identity and capture joins, without an ID migration."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.parsers.capture_sidecar import CaptureSidecar, parse_capture_sidecar

_SAFE_ID = re.compile(r"[A-Za-z0-9._:-]{1,200}\Z")
_HEADER_LINES = 32
_HEADER_BYTES = 64 * 1024


def safe_session_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if value not in {".", ".."} and _SAFE_ID.fullmatch(value) else ""


def session_metadata_id(entries: list[dict[str, Any]]) -> str:
    """Exactly one recorded session_meta ID is required; ambiguity withholds."""
    ids = {safe_session_id(e.get("payload", {}).get("id")) for e in entries
           if e.get("type") == "session_meta" and isinstance(e.get("payload"), dict)}
    ids.discard("")
    return next(iter(ids)) if len(ids) == 1 else ""


def read_session_metadata_id(path: Path) -> str:
    """Inspect only the bounded rollout header; never derive identity by filename."""
    entries = []
    remaining = _HEADER_BYTES
    try:
        with path.open("rb") as stream:
            for _ in range(_HEADER_LINES):
                line = stream.readline(remaining + 1)
                if not line or len(line) > remaining:
                    break
                remaining -= len(line)
                try:
                    entry = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(entry, dict) and entry.get("type") == "session_meta":
                    entries.append(entry)
    except OSError:
        return ""
    return session_metadata_id(entries)


def capture_sidecar_candidates(path: Path, session_id: str) -> tuple[Path, ...]:
    sid = safe_session_id(session_id)
    if not sid:
        return ()
    return (
        path.with_name(f"{sid}.capture.json"),
        path.parent.parent / "data" / "capture" / f"{sid}.capture.json",
    )


def collect_capture_sidecar(path: Path, session_id: str) -> CaptureSidecar | None:
    for candidate in capture_sidecar_candidates(path, session_id):
        sidecar = parse_capture_sidecar(candidate)
        # Native joins require a matching explicit ID, including older schemas.
        if (sidecar is not None and sidecar.session_id == session_id
                and sidecar.platform_type == "Codex"):
            return sidecar
    return None


def resolve_session_path(directory: Path, session_id: str, *, exclude: Path | None = None) -> Path | None:
    """Bounded same-directory lookup; recorded metadata must confirm filename candidates."""
    sid = safe_session_id(session_id)
    if not sid:
        return None
    candidates = []
    try:
        for candidate in directory.glob(f"*{sid}.jsonl"):
            # A symlink is not an independently confirmed same-source rollout.
            if candidate.is_symlink():
                continue
            candidates.append(candidate)
            if len(candidates) > 16:
                return None
    except OSError:
        return None
    matches = [p for p in candidates if p != exclude and read_session_metadata_id(p) == sid]
    return matches[0] if len(matches) == 1 else None


def resolve_child_session(path: Path, child_id: str) -> str | None:
    """An observed spawn receipt is not liveness. Resolve an existing rollout
    using its actual DB ID only after same-source session_meta confirmation.
    Missing/multiple children withhold correlation; raw receipt ID is retained.
    """
    child = resolve_session_path(path.parent, child_id, exclude=path)
    return f"S-{child.stem}" if child else None
