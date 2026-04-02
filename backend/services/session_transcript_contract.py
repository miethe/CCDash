"""Canonical transcript contract helpers."""
from __future__ import annotations

from typing import Any


_PLATFORM_PROVENANCE_DEFAULTS = {
    "claude code": "claude_code_jsonl",
    "codex": "codex_jsonl",
}

_ROLE_ALIASES = {
    "agent": "assistant",
    "assistant": "assistant",
    "user": "user",
    "system": "system",
}

_COMPATIBILITY_SPEAKER_ALIASES = {
    "assistant": "agent",
    "agent": "agent",
    "user": "user",
    "system": "system",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def canonical_role_from_log(log: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    role = _normalized_text(log.get("role") or log.get("speaker") or metadata.get("messageRole")).lower()
    if role:
        return _ROLE_ALIASES.get(role, role)
    if _normalized_text(log.get("type")).lower() == "tool":
        return "assistant"
    return ""


def compatibility_speaker_from_role(role: Any) -> str:
    normalized = _normalized_text(role).lower()
    if not normalized:
        return ""
    return _COMPATIBILITY_SPEAKER_ALIASES.get(normalized, normalized)


def canonical_message_type_from_log(log: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    return _normalized_text(log.get("type") or metadata.get("messageType"))


def canonical_message_id(
    source_log_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    for key in ("rawMessageId", "entryUuid", "messageId"):
        value = _normalized_text(metadata.get(key))
        if value:
            return value
    return source_log_id


def canonical_source_provenance(
    session_row: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    for key in ("source_provenance",):
        value = _normalized_text(session_row.get(key))
        if value:
            return value
    for key in ("sourceProvenance", "entrySource", "source"):
        value = _normalized_text(metadata.get(key))
        if value:
            return value

    platform_type = _normalized_text(
        session_row.get("platformType") or session_row.get("platform_type")
    ).lower()
    if platform_type:
        return _PLATFORM_PROVENANCE_DEFAULTS.get(platform_type, platform_type.replace(" ", "_"))
    return "session_log_projection"
