"""Topic naming and cursor helpers for live updates."""
from __future__ import annotations

import base64
import json
import re
from typing import Iterable

from backend.application.live_updates.contracts import LiveTopicAuthorization, LiveTopicCursor


_TOPIC_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def normalize_topic(topic: str) -> str:
    candidate = str(topic or "").strip().lower()
    if not candidate:
        raise ValueError("Topic must not be empty.")
    segments = candidate.split(".")
    if any(not _TOPIC_SEGMENT_RE.fullmatch(segment) for segment in segments):
        raise ValueError(f"Invalid live topic '{topic}'.")
    return ".".join(segments)


def normalize_topics(topics: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        normalized = normalize_topic(topic)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    if not ordered:
        raise ValueError("At least one live topic is required.")
    return tuple(ordered)


def join_topic(*segments: str) -> str:
    return normalize_topic(".".join(str(segment or "").strip().lower() for segment in segments))


def encode_cursor(cursor: LiveTopicCursor) -> str:
    payload = json.dumps(
        {"topic": normalize_topic(cursor.topic), "sequence": max(0, int(cursor.sequence))},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(raw: str) -> LiveTopicCursor:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("Cursor must not be empty.")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:  # pragma: no cover - exercised by invalid cursor tests
        raise ValueError("Cursor is not valid base64url JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Cursor payload must be a JSON object.")
    topic = normalize_topic(str(payload.get("topic") or ""))
    try:
        sequence = int(payload.get("sequence"))
    except Exception as exc:
        raise ValueError("Cursor sequence must be an integer.") from exc
    if sequence < 0:
        raise ValueError("Cursor sequence must be non-negative.")
    return LiveTopicCursor(topic=topic, sequence=sequence)


def parse_cursor_map(raw_cursors: Iterable[str]) -> dict[str, LiveTopicCursor]:
    cursor_map: dict[str, LiveTopicCursor] = {}
    for raw_cursor in raw_cursors:
        cursor = decode_cursor(raw_cursor)
        existing = cursor_map.get(cursor.topic)
        if existing is not None and existing.sequence != cursor.sequence:
            raise ValueError(f"Conflicting cursors were provided for topic '{cursor.topic}'.")
        cursor_map[cursor.topic] = cursor
    return cursor_map


def topic_authorization(topic: str, *, project_id: str | None) -> LiveTopicAuthorization:
    normalized = normalize_topic(topic)
    parts = normalized.split(".")
    resource = ".".join(parts[:2]) if len(parts) >= 2 else normalized
    return LiveTopicAuthorization(topic=normalized, project_id=project_id, resource=resource)


def execution_run_topic(run_id: str) -> str:
    return join_topic("execution", "run", run_id)


def session_topic(session_id: str) -> str:
    return join_topic("session", session_id)


def session_transcript_topic(session_id: str) -> str:
    return join_topic("session", session_id, "transcript")


def feature_topic(feature_id: str) -> str:
    return join_topic("feature", feature_id)


def project_features_topic(project_id: str) -> str:
    return join_topic("project", project_id, "features")


def project_tests_topic(project_id: str) -> str:
    return join_topic("project", project_id, "tests")


def project_ops_topic(project_id: str) -> str:
    return join_topic("project", project_id, "ops")
