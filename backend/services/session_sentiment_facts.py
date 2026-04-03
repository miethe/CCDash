"""Derive lightweight DX sentiment facts from canonical transcript rows."""
from __future__ import annotations

import re
from typing import Any


HEURISTIC_VERSION = "sics-201-v1"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Conservative lexical cues: strong words are weighted, but default remains neutral.
_POSITIVE_CUES: tuple[tuple[str, float], ...] = (
    ("fixed", 1.0),
    ("resolved", 1.0),
    ("works", 0.9),
    ("working", 0.85),
    ("success", 0.9),
    ("good", 0.6),
    ("great", 0.7),
    ("thanks", 0.6),
    ("thank you", 0.65),
    ("done", 0.55),
    ("completed", 0.7),
)

_NEGATIVE_CUES: tuple[tuple[str, float], ...] = (
    ("blocked", 1.0),
    ("broken", 1.0),
    ("failing", 1.0),
    ("failed", 1.0),
    ("error", 0.85),
    ("errors", 0.9),
    ("confused", 0.8),
    ("stuck", 0.95),
    ("frustrated", 0.95),
    ("issue", 0.7),
    ("problem", 0.75),
    ("does not work", 1.0),
    ("not working", 1.0),
)


def _first_non_empty(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_words(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def _matched_cues(normalized: str, cue_weights: tuple[tuple[str, float], ...]) -> list[dict[str, Any]]:
    if not normalized:
        return []
    padded = f" {normalized} "
    matches: list[dict[str, Any]] = []
    for cue, weight in cue_weights:
        cue_norm = _normalize_words(cue)
        if not cue_norm:
            continue
        if f" {cue_norm} " in padded:
            matches.append({"cue": cue, "weight": round(float(weight), 4)})
    return matches


def _message_sentiment(content: str, source_provenance: str) -> tuple[str, float, float, dict[str, Any]]:
    normalized = _normalize_words(content)
    positive_cues = _matched_cues(normalized, _POSITIVE_CUES)
    negative_cues = _matched_cues(normalized, _NEGATIVE_CUES)

    positive_weight = sum(float(item["weight"]) for item in positive_cues)
    negative_weight = sum(float(item["weight"]) for item in negative_cues)
    total_weight = positive_weight + negative_weight
    raw_balance = positive_weight - negative_weight
    sentiment_score = _clamp(raw_balance / 3.0, -1.0, 1.0)

    label = "neutral"
    confidence = 0.55

    if total_weight > 0:
        mixed_signal = positive_weight > 0 and negative_weight > 0 and min(positive_weight, negative_weight) >= 0.6
        if mixed_signal:
            label = "mixed"
            sentiment_score = 0.0
            confidence = min(0.9, 0.62 + 0.25 * min(1.0, total_weight / 3.0))
        elif abs(sentiment_score) < 0.2:
            label = "neutral"
            sentiment_score = 0.0
            confidence = 0.58
        elif sentiment_score > 0:
            label = "positive"
            strength = min(1.0, total_weight / 3.0)
            polarity = abs(raw_balance) / max(0.01, total_weight)
            confidence = min(0.95, 0.6 + 0.25 * strength + 0.1 * polarity)
        else:
            label = "negative"
            strength = min(1.0, total_weight / 3.0)
            polarity = abs(raw_balance) / max(0.01, total_weight)
            confidence = min(0.95, 0.6 + 0.25 * strength + 0.1 * polarity)

    evidence_json: dict[str, Any] = {
        "sourceProvenance": source_provenance,
        "contentSample": content[:220],
        "positiveCues": positive_cues,
        "negativeCues": negative_cues,
        "positiveWeight": round(positive_weight, 4),
        "negativeWeight": round(negative_weight, 4),
        "cueBalance": round(raw_balance, 4),
        "matchedCueCount": len(positive_cues) + len(negative_cues),
    }
    return label, round(float(sentiment_score), 4), round(float(confidence), 4), evidence_json


def build_session_sentiment_facts(
    session_payload: dict[str, Any],
    canonical_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic per-message sentiment facts for user-authored transcript rows."""
    session_id = _first_non_empty(session_payload, "id")
    if not session_id:
        return []

    root_session_id = _first_non_empty(
        session_payload,
        "rootSessionId",
        "root_session_id",
        default=session_id,
    )
    thread_session_id = _first_non_empty(
        session_payload,
        "threadSessionId",
        "thread_session_id",
        "id",
        default=session_id,
    )
    feature_id = _first_non_empty(
        session_payload,
        "featureId",
        "feature_id",
        "taskId",
        "task_id",
    )

    def _sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
        message_index = _coerce_int(row.get("message_index") if row.get("message_index") is not None else row.get("messageIndex"))
        source_log_id = _first_non_empty(row, "source_log_id", "sourceLogId", "id")
        message_id = _first_non_empty(row, "message_id", "messageId")
        return (message_index, source_log_id, message_id)

    facts: list[dict[str, Any]] = []
    for row in sorted(canonical_messages, key=_sort_key):
        role = _first_non_empty(row, "role", "speaker").lower()
        if role != "user":
            continue

        message_index = _coerce_int(row.get("message_index") if row.get("message_index") is not None else row.get("messageIndex"))
        source_message_id = _first_non_empty(
            row,
            "message_id",
            "messageId",
            "source_log_id",
            "sourceLogId",
            default=f"{session_id}:message:{message_index}",
        )
        source_log_id = _first_non_empty(row, "source_log_id", "sourceLogId", "id")
        source_provenance = _first_non_empty(
            row,
            "source_provenance",
            "sourceProvenance",
            default="session_log_projection",
        )
        content = _first_non_empty(row, "content")

        label, sentiment_score, confidence, evidence_json = _message_sentiment(content, source_provenance)
        fact = {
            "session_id": session_id,
            "feature_id": feature_id,
            "root_session_id": root_session_id,
            "thread_session_id": thread_session_id,
            "source_message_id": source_message_id,
            "source_log_id": source_log_id,
            "message_index": message_index,
            "sentiment_label": label,
            "sentiment_score": sentiment_score,
            "confidence": confidence,
            "heuristic_version": HEURISTIC_VERSION,
            "evidence_json": evidence_json,
        }
        facts.append(fact)

    return facts

