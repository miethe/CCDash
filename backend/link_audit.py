"""Shared link-audit analyzer used by API and CLI tooling."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


def canonical_slug(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return ""
    if "-v" in token:
        base, _, suffix = token.rpartition("-v")
        if base and suffix.replace(".", "").isdigit():
            return base
    return token


def normalize_path(path: str) -> str:
    value = (path or "").strip().strip("\"'`<>[](),;")
    if not value:
        return ""
    return value.replace("\\", "/").lower()


def contains_feature_hint(feature_id: str, text: str) -> bool:
    blob = (text or "").lower()
    if not blob:
        return False
    feature_token = feature_id.lower()
    base_token = canonical_slug(feature_token)
    return feature_token in blob or (base_token and base_token in blob)


def to_float(raw: Any) -> float:
    try:
        return float(raw or 0.0)
    except Exception:
        return 0.0


@dataclass
class LinkAuditSuspect:
    feature_id: str
    session_id: str
    confidence: float
    ambiguity_share: float
    title: str
    signal_type: str
    signal_path: str
    commands: list[str]
    reason: str
    fanout_count: int


def analyze_suspect_links(
    rows: list[dict[str, Any]],
    fanout_map: dict[str, int],
    primary_floor: float,
    fanout_floor: int,
) -> list[LinkAuditSuspect]:
    """Return suspect feature<->session links from raw entity link rows."""
    suspects: list[LinkAuditSuspect] = []
    for row in rows:
        feature_id = str(row.get("feature_id") or "")
        session_id = str(row.get("session_id") or "")
        confidence = to_float(row.get("confidence"))
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        commands = metadata.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        commands = [str(cmd) for cmd in commands if isinstance(cmd, str)]

        signals = metadata.get("signals", [])
        if not isinstance(signals, list):
            signals = []
        primary_signal = signals[0] if signals and isinstance(signals[0], dict) else {}
        signal_type = str(primary_signal.get("type") or "")
        signal_path = normalize_path(str(primary_signal.get("path") or ""))
        title = str(metadata.get("title") or "")
        ambiguity_share = to_float(metadata.get("ambiguityShare"))
        fanout_count = fanout_map.get(session_id, 0)

        has_feature_path_hint = contains_feature_hint(feature_id, signal_path)
        has_feature_title_hint = contains_feature_hint(feature_id, title)
        primary_like = confidence >= primary_floor
        key_command = any(
            cmd.startswith("/dev:execute-phase")
            or cmd.startswith("/dev:quick-feature")
            or cmd.startswith("/plan:plan-feature")
            for cmd in commands
        )

        reasons: list[str] = []
        if fanout_count >= fanout_floor:
            reasons.append(f"high_fanout({fanout_count})")
        if primary_like and not has_feature_path_hint and signal_type == "command_args_path":
            reasons.append("primary_like_command_path_mismatch")
        if primary_like and key_command and not has_feature_title_hint and not has_feature_path_hint:
            reasons.append("primary_like_title_path_mismatch")

        if reasons:
            suspects.append(
                LinkAuditSuspect(
                    feature_id=feature_id,
                    session_id=session_id,
                    confidence=round(confidence, 3),
                    ambiguity_share=round(ambiguity_share, 3),
                    title=title,
                    signal_type=signal_type,
                    signal_path=signal_path,
                    commands=commands[:5],
                    reason=";".join(reasons),
                    fanout_count=fanout_count,
                )
            )
    suspects.sort(key=lambda item: (item.fanout_count, item.confidence), reverse=True)
    return suspects


def suspects_as_dicts(suspects: list[LinkAuditSuspect]) -> list[dict[str, Any]]:
    return [asdict(item) for item in suspects]
