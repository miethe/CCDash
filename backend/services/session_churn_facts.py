"""Derive deterministic per-file churn facts from canonical transcript and file updates."""
from __future__ import annotations

from typing import Any


HEURISTIC_VERSION = "sics-202-v1"
_REWRITE_ACTIONS = frozenset({"rewrite", "replace", "overwrite", "refactor", "rework"})
_UPDATE_ACTIONS = frozenset({"update", "modify", "edit", "patch"})


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
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize_path(raw: str) -> str:
    normalized = str(raw or "").strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _normalize_action(raw: str) -> str:
    return str(raw or "update").strip().lower() or "update"


def _resolve_message_index(row: dict[str, Any], by_source_log_id: dict[str, int]) -> int:
    if row.get("message_index") is not None:
        return _coerce_int(row.get("message_index"))
    if row.get("messageIndex") is not None:
        return _coerce_int(row.get("messageIndex"))
    source_log_id = _first_non_empty(row, "source_log_id", "sourceLogId")
    if source_log_id and source_log_id in by_source_log_id:
        return by_source_log_id[source_log_id]
    return -1


def _extract_additions(row: dict[str, Any]) -> int:
    for key in (
        "additions",
        "lines_added",
        "linesAdded",
        "insertions",
        "added",
    ):
        if row.get(key) is not None:
            return max(0, _coerce_int(row.get(key)))
    return 0


def _extract_deletions(row: dict[str, Any]) -> int:
    for key in (
        "deletions",
        "lines_deleted",
        "linesDeleted",
        "removed",
    ):
        if row.get(key) is not None:
            return max(0, _coerce_int(row.get(key)))
    return 0


def _build_canonical_index(canonical_rows: list[dict[str, Any]]) -> dict[str, int]:
    ordered = sorted(
        canonical_rows,
        key=lambda row: (
            _coerce_int(row.get("message_index") if row.get("message_index") is not None else row.get("messageIndex")),
            _first_non_empty(row, "source_log_id", "sourceLogId"),
        ),
    )
    by_source_log_id: dict[str, int] = {}
    for fallback_index, row in enumerate(ordered):
        source_log_id = _first_non_empty(row, "source_log_id", "sourceLogId")
        if not source_log_id:
            continue
        message_index = _resolve_message_index(row, {})
        if message_index < 0:
            message_index = fallback_index
        by_source_log_id[source_log_id] = message_index
    return by_source_log_id


def _ordered_updates(
    updates: list[dict[str, Any]],
    by_source_log_id: dict[str, int],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for original_index, row in enumerate(updates):
        source_log_id = _first_non_empty(row, "source_log_id", "sourceLogId")
        message_index = _resolve_message_index(row, by_source_log_id)
        additions = _extract_additions(row)
        deletions = _extract_deletions(row)
        net_diff = additions - deletions
        action = _normalize_action(_first_non_empty(row, "action", default="update"))
        enriched.append(
            {
                "source_log_id": source_log_id,
                "message_index": message_index,
                "action": action,
                "additions": additions,
                "deletions": deletions,
                "net_diff": net_diff,
                "timestamp": _first_non_empty(row, "action_timestamp", "timestamp", default=""),
                "original_index": original_index,
            }
        )
    enriched.sort(
        key=lambda row: (
            int(row["message_index"]) if int(row["message_index"]) >= 0 else 10**9,
            str(row["source_log_id"]),
            int(row["original_index"]),
        )
    )
    return enriched


def _rewrite_pass_count(rows: list[dict[str, Any]]) -> int:
    passes = 0
    previous_action = ""
    for row in rows:
        action = str(row["action"])
        is_rewrite = action in _REWRITE_ACTIONS
        if action in _UPDATE_ACTIONS:
            is_rewrite = False
        if is_rewrite and previous_action != action:
            passes += 1
        previous_action = action
    return passes


def _churn_score(
    *,
    touch_count: int,
    repeat_touch_count: int,
    rewrite_pass_count: int,
    additions_total: int,
    deletions_total: int,
) -> float:
    change_volume = additions_total + deletions_total
    repeat_ratio = repeat_touch_count / max(1, touch_count)
    rewrite_ratio = rewrite_pass_count / max(1, touch_count)
    net_ratio = abs(additions_total - deletions_total) / max(1, change_volume) if change_volume > 0 else 0.0
    low_progress_signal = (1.0 - net_ratio) if change_volume > 0 else 0.0
    score = 0.45 * repeat_ratio + 0.35 * rewrite_ratio + 0.2 * low_progress_signal
    return round(_clamp(score), 4)


def _progress_score(churn_score: float, additions_total: int, deletions_total: int) -> float:
    change_volume = additions_total + deletions_total
    net_gain = max(0, additions_total - deletions_total)
    net_gain_ratio = net_gain / max(1, change_volume) if change_volume > 0 else 0.0
    score = 0.65 * (1.0 - churn_score) + 0.35 * net_gain_ratio
    return round(_clamp(score), 4)


def _confidence(
    *,
    touch_count: int,
    known_message_indexes: int,
    known_source_logs: int,
    change_volume: int,
) -> float:
    score = 0.5
    if touch_count >= 2:
        score += 0.15
    if known_message_indexes > 0:
        score += 0.15
    if known_source_logs > 0:
        score += 0.1
    if change_volume > 0:
        score += 0.1
    return round(_clamp(score, 0.0, 0.99), 4)


def build_session_code_churn_facts(
    session_payload: dict[str, Any],
    canonical_rows: list[dict[str, Any]],
    file_updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic per-file churn facts for repository persistence."""
    session_id = _first_non_empty(session_payload, "id")
    if not session_id:
        return []

    root_session_id = _first_non_empty(session_payload, "rootSessionId", "root_session_id", default=session_id)
    thread_session_id = _first_non_empty(session_payload, "threadSessionId", "thread_session_id", default=session_id)
    feature_id = _first_non_empty(session_payload, "featureId", "feature_id", default="")

    canonical_by_log = _build_canonical_index(canonical_rows)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in file_updates:
        file_path = _normalize_path(_first_non_empty(row, "file_path", "filePath", "path"))
        if not file_path:
            continue
        grouped.setdefault(file_path, []).append(dict(row))

    facts: list[dict[str, Any]] = []
    for file_path in sorted(grouped.keys()):
        ordered = _ordered_updates(grouped[file_path], canonical_by_log)
        if not ordered:
            continue

        touch_count = len(ordered)
        distinct_edit_turn_count = len({int(row["message_index"]) for row in ordered if int(row["message_index"]) >= 0})
        repeat_touch_count = max(0, touch_count - 1)
        rewrite_pass_count = _rewrite_pass_count(ordered)
        additions_total = sum(max(0, int(row["additions"])) for row in ordered)
        deletions_total = sum(max(0, int(row["deletions"])) for row in ordered)
        net_diff_total = additions_total - deletions_total
        churn_score = _churn_score(
            touch_count=touch_count,
            repeat_touch_count=repeat_touch_count,
            rewrite_pass_count=rewrite_pass_count,
            additions_total=additions_total,
            deletions_total=deletions_total,
        )
        progress_score = _progress_score(churn_score, additions_total, deletions_total)
        low_progress_loop = (
            touch_count >= 4
            and repeat_touch_count >= 3
            and churn_score >= 0.65
            and progress_score <= 0.45
        )
        known_message_indexes = sum(1 for row in ordered if int(row["message_index"]) >= 0)
        known_source_logs = sum(1 for row in ordered if str(row["source_log_id"]))
        evidence_updates = [
            {
                "sourceLogId": row["source_log_id"],
                "messageIndex": int(row["message_index"]),
                "action": row["action"],
                "additions": int(row["additions"]),
                "deletions": int(row["deletions"]),
                "netDiff": int(row["net_diff"]),
                "timestamp": row["timestamp"],
            }
            for row in ordered[:80]
        ]
        touched_message_indexes = sorted({int(row["message_index"]) for row in ordered if int(row["message_index"]) >= 0})
        touched_source_log_ids: list[str] = []
        seen_source_log_ids: set[str] = set()
        for row in ordered:
            source_log_id = str(row["source_log_id"])
            if not source_log_id or source_log_id in seen_source_log_ids:
                continue
            touched_source_log_ids.append(source_log_id)
            seen_source_log_ids.add(source_log_id)

        evidence_json = {
            "touchedMessageIndexes": touched_message_indexes,
            "touchedSourceLogIds": touched_source_log_ids,
            "updateSummary": evidence_updates,
            "loopSignals": {
                "touchCount": touch_count,
                "distinctEditTurnCount": distinct_edit_turn_count,
                "repeatTouchCount": repeat_touch_count,
                "rewritePassCount": rewrite_pass_count,
            },
        }

        first_source_log_id = str(next((row["source_log_id"] for row in ordered if str(row["source_log_id"])), ""))
        last_source_log_id = str(next((row["source_log_id"] for row in reversed(ordered) if str(row["source_log_id"])), ""))
        first_message_index = int(next((row["message_index"] for row in ordered if int(row["message_index"]) >= 0), -1))
        last_message_index = int(next((row["message_index"] for row in reversed(ordered) if int(row["message_index"]) >= 0), -1))

        facts.append(
            {
                "session_id": session_id,
                "feature_id": feature_id,
                "file_path": file_path,
                "root_session_id": root_session_id,
                "thread_session_id": thread_session_id,
                "first_source_log_id": first_source_log_id,
                "last_source_log_id": last_source_log_id,
                "first_message_index": first_message_index,
                "last_message_index": last_message_index,
                "touch_count": touch_count,
                "distinct_edit_turn_count": distinct_edit_turn_count,
                "repeat_touch_count": repeat_touch_count,
                "rewrite_pass_count": rewrite_pass_count,
                "additions_total": additions_total,
                "deletions_total": deletions_total,
                "net_diff_total": net_diff_total,
                "churn_score": churn_score,
                "progress_score": progress_score,
                "low_progress_loop": bool(low_progress_loop),
                "confidence": _confidence(
                    touch_count=touch_count,
                    known_message_indexes=known_message_indexes,
                    known_source_logs=known_source_logs,
                    change_volume=additions_total + deletions_total,
                ),
                "heuristic_version": HEURISTIC_VERSION,
                "evidence_json": evidence_json,
            }
        )

    return facts


__all__ = ["HEURISTIC_VERSION", "build_session_code_churn_facts"]
