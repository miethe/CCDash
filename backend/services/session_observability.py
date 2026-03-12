"""Helpers for session context observability fields."""
from __future__ import annotations

import json
from typing import Any

from backend.model_identity import canonical_model_name


def _coerce_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _log_attr(log: Any, key: str, default: Any = None) -> Any:
    if isinstance(log, dict):
        return log.get(key, default)
    return getattr(log, key, default)


def _log_metadata(log: Any) -> dict[str, Any]:
    metadata = _log_attr(log, "metadata")
    if isinstance(metadata, dict):
        return metadata
    metadata_json = _log_attr(log, "metadata_json")
    if isinstance(metadata_json, str) and metadata_json.strip():
        try:
            parsed = json.loads(metadata_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def default_context_window_size(model: str) -> int:
    normalized = canonical_model_name(model)
    if normalized.startswith("claude-"):
        return 200_000
    return 0


def calculate_context_utilization(current_tokens: int, context_window_size: int) -> float:
    if current_tokens <= 0 or context_window_size <= 0:
        return 0.0
    return round((current_tokens / context_window_size) * 100.0, 2)


def derive_context_observability(
    logs: list[Any],
    model: str,
    hook_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context_window = hook_snapshot.get("contextWindow") if isinstance(hook_snapshot, dict) else None
    captured_at = str(hook_snapshot.get("capturedAt") or "") if isinstance(hook_snapshot, dict) else ""
    if isinstance(context_window, dict):
        current_tokens = _coerce_int(
            context_window.get("totalInputTokens", context_window.get("total_input_tokens"))
        )
        context_window_size = _coerce_int(
            context_window.get("contextWindowSize", context_window.get("context_window_size"))
        )
        if context_window_size <= 0:
            context_window_size = default_context_window_size(model)
        if current_tokens > 0:
            return {
                "current_context_tokens": current_tokens,
                "context_window_size": context_window_size,
                "context_utilization_pct": calculate_context_utilization(current_tokens, context_window_size),
                "context_measurement_source": "hook_context_window",
                "context_measured_at": captured_at,
            }

    for log in reversed(logs or []):
        if str(_log_attr(log, "type") or "").strip().lower() != "message":
            continue
        if str(_log_attr(log, "speaker") or "").strip().lower() != "agent":
            continue
        metadata = _log_metadata(log)
        input_tokens = _coerce_int(metadata.get("inputTokens", metadata.get("input_tokens")))
        cache_creation_tokens = _coerce_int(
            metadata.get("cacheCreationInputTokens", metadata.get("cache_creation_input_tokens"))
        )
        cache_read_tokens = _coerce_int(
            metadata.get("cacheReadInputTokens", metadata.get("cache_read_input_tokens"))
        )
        current_tokens = input_tokens + cache_creation_tokens + cache_read_tokens
        if current_tokens <= 0:
            continue
        context_window_size = default_context_window_size(model)
        return {
            "current_context_tokens": current_tokens,
            "context_window_size": context_window_size,
            "context_utilization_pct": calculate_context_utilization(current_tokens, context_window_size),
            "context_measurement_source": "transcript_latest_assistant_usage",
            "context_measured_at": str(_log_attr(log, "timestamp") or ""),
        }

    return {
        "current_context_tokens": 0,
        "context_window_size": 0,
        "context_utilization_pct": 0.0,
        "context_measurement_source": "",
        "context_measured_at": "",
    }
