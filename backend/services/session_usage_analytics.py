"""Aggregate session usage events and attributions into analytics-friendly views."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import aiosqlite


_MODEL_IO_FAMILIES = {"model_input", "model_output"}
_CACHE_INPUT_FAMILIES = {"cache_creation_input", "cache_read_input"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _family_buckets(token_family: str) -> tuple[int, int]:
    if token_family in _MODEL_IO_FAMILIES:
        return (1, 0)
    if token_family in _CACHE_INPUT_FAMILIES:
        return (0, 1)
    return (0, 0)


def _confidence_band(value: float) -> str:
    if value >= 0.85:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


async def _query_rows(
    db: Any,
    *,
    sqlite_query: str,
    sqlite_params: tuple[Any, ...],
    postgres_query: str,
    postgres_params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_query, sqlite_params) as cur:
            return [dict(row) for row in await cur.fetchall()]
    rows = await db.fetch(postgres_query, *postgres_params)
    return [dict(row) for row in rows]


def _build_usage_queries(
    *,
    project_id: str,
    start: str | None = None,
    end: str | None = None,
    session_id: str | None = None,
    session_ids: list[str] | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> tuple[str, tuple[Any, ...], str, tuple[Any, ...]]:
    sqlite_filters = ["sue.project_id = ?"]
    sqlite_params: list[Any] = [project_id]
    postgres_filters = ["sue.project_id = $1"]
    postgres_params: list[Any] = [project_id]
    pg_idx = 2

    if start:
        sqlite_filters.append("sue.captured_at >= ?")
        sqlite_params.append(start)
        postgres_filters.append(f"sue.captured_at >= ${pg_idx}")
        postgres_params.append(start)
        pg_idx += 1
    if end:
        sqlite_filters.append("sue.captured_at <= ?")
        sqlite_params.append(end)
        postgres_filters.append(f"sue.captured_at <= ${pg_idx}")
        postgres_params.append(end)
        pg_idx += 1
    if session_id:
        sqlite_filters.append("sue.session_id = ?")
        sqlite_params.append(session_id)
        postgres_filters.append(f"sue.session_id = ${pg_idx}")
        postgres_params.append(session_id)
        pg_idx += 1
    if session_ids:
        cleaned = [value for value in session_ids if value]
        if cleaned:
            sqlite_filters.append(f"sue.session_id IN ({', '.join('?' for _ in cleaned)})")
            sqlite_params.extend(cleaned)
            pg_placeholders = ", ".join(f"${pg_idx + offset}" for offset in range(len(cleaned)))
            postgres_filters.append(f"sue.session_id IN ({pg_placeholders})")
            postgres_params.extend(cleaned)
            pg_idx += len(cleaned)
    if entity_type:
        sqlite_filters.append("sua.entity_type = ?")
        sqlite_params.append(entity_type)
        postgres_filters.append(f"sua.entity_type = ${pg_idx}")
        postgres_params.append(entity_type)
        pg_idx += 1
    if entity_id:
        sqlite_filters.append("sua.entity_id = ?")
        sqlite_params.append(entity_id)
        postgres_filters.append(f"sua.entity_id = ${pg_idx}")
        postgres_params.append(entity_id)
        pg_idx += 1

    sqlite_query = f"""
        SELECT
            sue.id AS event_id,
            sue.project_id,
            sue.session_id,
            sue.root_session_id,
            COALESCE(sue.linked_session_id, '') AS linked_session_id,
            COALESCE(sue.source_log_id, '') AS source_log_id,
            COALESCE(sue.captured_at, '') AS captured_at,
            COALESCE(sue.event_kind, '') AS event_kind,
            COALESCE(sue.model, '') AS model,
            COALESCE(sue.tool_name, '') AS tool_name,
            COALESCE(sue.agent_name, '') AS agent_name,
            COALESCE(sue.token_family, '') AS token_family,
            COALESCE(sue.delta_tokens, 0) AS delta_tokens,
            COALESCE(sue.cost_usd_model_io, 0) AS cost_usd_model_io,
            COALESCE(sue.metadata_json, '{{}}') AS event_metadata_json,
            COALESCE(sua.entity_type, '') AS entity_type,
            COALESCE(sua.entity_id, '') AS entity_id,
            COALESCE(sua.attribution_role, '') AS attribution_role,
            COALESCE(sua.weight, 0) AS weight,
            COALESCE(sua.method, '') AS method,
            COALESCE(sua.confidence, 0) AS confidence,
            COALESCE(sua.metadata_json, '{{}}') AS attribution_metadata_json,
            COALESCE(s.session_type, '') AS session_type,
            COALESCE(s.parent_session_id, '') AS parent_session_id,
            COALESCE(s.status, '') AS session_status,
            COALESCE(s.model_io_tokens, 0) AS session_model_io_tokens,
            COALESCE(s.cache_input_tokens, 0) AS session_cache_input_tokens
        FROM session_usage_events sue
        LEFT JOIN session_usage_attributions sua
            ON sua.event_id = sue.id
        LEFT JOIN sessions s
            ON s.id = sue.session_id AND s.project_id = sue.project_id
        WHERE {' AND '.join(sqlite_filters)}
        ORDER BY sue.captured_at DESC, sue.id DESC, sua.attribution_role ASC, sua.entity_type ASC, sua.entity_id ASC
    """
    postgres_query = f"""
        SELECT
            sue.id AS event_id,
            sue.project_id,
            sue.session_id,
            sue.root_session_id,
            COALESCE(sue.linked_session_id, '') AS linked_session_id,
            COALESCE(sue.source_log_id, '') AS source_log_id,
            COALESCE(sue.captured_at, '') AS captured_at,
            COALESCE(sue.event_kind, '') AS event_kind,
            COALESCE(sue.model, '') AS model,
            COALESCE(sue.tool_name, '') AS tool_name,
            COALESCE(sue.agent_name, '') AS agent_name,
            COALESCE(sue.token_family, '') AS token_family,
            COALESCE(sue.delta_tokens, 0) AS delta_tokens,
            COALESCE(sue.cost_usd_model_io, 0) AS cost_usd_model_io,
            COALESCE(sue.metadata_json, '{{}}') AS event_metadata_json,
            COALESCE(sua.entity_type, '') AS entity_type,
            COALESCE(sua.entity_id, '') AS entity_id,
            COALESCE(sua.attribution_role, '') AS attribution_role,
            COALESCE(sua.weight, 0) AS weight,
            COALESCE(sua.method, '') AS method,
            COALESCE(sua.confidence, 0) AS confidence,
            COALESCE(sua.metadata_json, '{{}}') AS attribution_metadata_json,
            COALESCE(s.session_type, '') AS session_type,
            COALESCE(s.parent_session_id, '') AS parent_session_id,
            COALESCE(s.status, '') AS session_status,
            COALESCE(s.model_io_tokens, 0) AS session_model_io_tokens,
            COALESCE(s.cache_input_tokens, 0) AS session_cache_input_tokens
        FROM session_usage_events sue
        LEFT JOIN session_usage_attributions sua
            ON sua.event_id = sue.id
        LEFT JOIN sessions s
            ON s.id = sue.session_id AND s.project_id = sue.project_id
        WHERE {' AND '.join(postgres_filters)}
        ORDER BY sue.captured_at DESC, sue.id DESC, sua.attribution_role ASC, sua.entity_type ASC, sua.entity_id ASC
    """
    return sqlite_query, tuple(sqlite_params), postgres_query, tuple(postgres_params)


async def _load_usage_rows(
    db: Any,
    *,
    project_id: str,
    start: str | None = None,
    end: str | None = None,
    session_id: str | None = None,
    session_ids: list[str] | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> list[dict[str, Any]]:
    sqlite_query, sqlite_params, postgres_query, postgres_params = _build_usage_queries(
        project_id=project_id,
        start=start,
        end=end,
        session_id=session_id,
        session_ids=session_ids,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return await _query_rows(
        db,
        sqlite_query=sqlite_query,
        sqlite_params=sqlite_params,
        postgres_query=postgres_query,
        postgres_params=postgres_params,
    )


def _summarize_grouped_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    included_event_ids: set[str] = set()
    all_session_ids: set[str] = set()

    for row in rows:
        entity_type = str(row.get("entity_type") or "").strip()
        entity_id = str(row.get("entity_id") or "").strip()
        if not entity_type or not entity_id:
            continue

        key = (entity_type, entity_id)
        bucket = grouped.setdefault(
            key,
            {
                "entityType": entity_type,
                "entityId": entity_id,
                "entityLabel": entity_id,
                "exclusiveTokens": 0,
                "supportingTokens": 0,
                "exclusiveModelIOTokens": 0,
                "exclusiveCacheInputTokens": 0,
                "supportingModelIOTokens": 0,
                "supportingCacheInputTokens": 0,
                "exclusiveCostUsdModelIO": 0.0,
                "supportingCostUsdModelIO": 0.0,
                "eventIds": set(),
                "primaryEventIds": set(),
                "supportingEventIds": set(),
                "sessionIds": set(),
                "confidenceTotal": 0.0,
                "confidenceCount": 0,
                "methods": defaultdict(lambda: {"method": "", "tokens": 0, "eventIds": set(), "confidenceTotal": 0.0, "confidenceCount": 0}),
            },
        )
        event_id = str(row.get("event_id") or "")
        session_id = str(row.get("session_id") or "")
        role = str(row.get("attribution_role") or "")
        token_family = str(row.get("token_family") or "")
        delta_tokens = _safe_int(row.get("delta_tokens"))
        cost_usd = _safe_float(row.get("cost_usd_model_io"))
        confidence = _safe_float(row.get("confidence"))
        method = str(row.get("method") or "")

        model_io_marker, cache_marker = _family_buckets(token_family)
        bucket["eventIds"].add(event_id)
        bucket["sessionIds"].add(session_id)
        all_session_ids.add(session_id)
        included_event_ids.add(event_id)
        bucket["confidenceTotal"] += confidence
        bucket["confidenceCount"] += 1

        if role == "primary":
            bucket["exclusiveTokens"] += delta_tokens
            bucket["exclusiveModelIOTokens"] += delta_tokens if model_io_marker else 0
            bucket["exclusiveCacheInputTokens"] += delta_tokens if cache_marker else 0
            bucket["exclusiveCostUsdModelIO"] += cost_usd
            bucket["primaryEventIds"].add(event_id)
        elif role == "supporting":
            bucket["supportingTokens"] += delta_tokens
            bucket["supportingModelIOTokens"] += delta_tokens if model_io_marker else 0
            bucket["supportingCacheInputTokens"] += delta_tokens if cache_marker else 0
            bucket["supportingCostUsdModelIO"] += cost_usd
            bucket["supportingEventIds"].add(event_id)

        method_bucket = bucket["methods"][method]
        method_bucket["method"] = method
        method_bucket["tokens"] += delta_tokens
        method_bucket["eventIds"].add(event_id)
        method_bucket["confidenceTotal"] += confidence
        method_bucket["confidenceCount"] += 1

    items: list[dict[str, Any]] = []
    for bucket in grouped.values():
        methods = sorted(
            (
                {
                    "method": method_bucket["method"],
                    "tokens": method_bucket["tokens"],
                    "eventCount": len(method_bucket["eventIds"]),
                    "averageConfidence": round(
                        method_bucket["confidenceTotal"] / max(1, method_bucket["confidenceCount"]),
                        4,
                    ),
                }
                for method_bucket in bucket["methods"].values()
                if method_bucket["method"]
            ),
            key=lambda item: (-_safe_int(item.get("tokens")), -_safe_int(item.get("eventCount")), str(item.get("method"))),
        )
        items.append(
            {
                "entityType": bucket["entityType"],
                "entityId": bucket["entityId"],
                "entityLabel": bucket["entityLabel"],
                "exclusiveTokens": bucket["exclusiveTokens"],
                "supportingTokens": bucket["supportingTokens"],
                "exclusiveModelIOTokens": bucket["exclusiveModelIOTokens"],
                "exclusiveCacheInputTokens": bucket["exclusiveCacheInputTokens"],
                "supportingModelIOTokens": bucket["supportingModelIOTokens"],
                "supportingCacheInputTokens": bucket["supportingCacheInputTokens"],
                "exclusiveCostUsdModelIO": round(bucket["exclusiveCostUsdModelIO"], 6),
                "supportingCostUsdModelIO": round(bucket["supportingCostUsdModelIO"], 6),
                "eventCount": len(bucket["eventIds"]),
                "primaryEventCount": len(bucket["primaryEventIds"]),
                "supportingEventCount": len(bucket["supportingEventIds"]),
                "sessionCount": len(bucket["sessionIds"]),
                "averageConfidence": round(bucket["confidenceTotal"] / max(1, bucket["confidenceCount"]), 4),
                "methods": methods,
            }
        )

    items.sort(
        key=lambda item: (
            -_safe_int(item.get("exclusiveTokens")),
            -_safe_int(item.get("supportingTokens")),
            -_safe_int(item.get("eventCount")),
            str(item.get("entityType")),
            str(item.get("entityId")),
        )
    )

    summary = {
        "entityCount": len(items),
        "sessionCount": len(all_session_ids),
        "eventCount": len(included_event_ids),
        "totalExclusiveTokens": sum(_safe_int(item.get("exclusiveTokens")) for item in items),
        "totalSupportingTokens": sum(_safe_int(item.get("supportingTokens")) for item in items),
        "totalExclusiveModelIOTokens": sum(_safe_int(item.get("exclusiveModelIOTokens")) for item in items),
        "totalExclusiveCacheInputTokens": sum(_safe_int(item.get("exclusiveCacheInputTokens")) for item in items),
        "totalExclusiveCostUsdModelIO": round(sum(_safe_float(item.get("exclusiveCostUsdModelIO")) for item in items), 6),
        "averageConfidence": round(
            sum(_safe_float(item.get("averageConfidence")) for item in items) / max(1, len(items)),
            4,
        ),
    }
    return {"rows": items, "summary": summary}


def _build_event_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if event_id in by_event:
            continue
        by_event[event_id] = {
            "id": event_id,
            "projectId": str(row.get("project_id") or ""),
            "sessionId": str(row.get("session_id") or ""),
            "rootSessionId": str(row.get("root_session_id") or ""),
            "linkedSessionId": str(row.get("linked_session_id") or ""),
            "sourceLogId": str(row.get("source_log_id") or ""),
            "capturedAt": str(row.get("captured_at") or ""),
            "eventKind": str(row.get("event_kind") or ""),
            "model": str(row.get("model") or ""),
            "toolName": str(row.get("tool_name") or ""),
            "agentName": str(row.get("agent_name") or ""),
            "tokenFamily": str(row.get("token_family") or ""),
            "deltaTokens": _safe_int(row.get("delta_tokens")),
            "costUsdModelIO": round(_safe_float(row.get("cost_usd_model_io")), 6),
            "metadata": _safe_dict(row.get("event_metadata_json")),
        }
    return list(by_event.values())


def _build_attribution_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        entity_type = str(row.get("entity_type") or "").strip()
        entity_id = str(row.get("entity_id") or "").strip()
        if not entity_type or not entity_id:
            continue
        key = (
            str(row.get("event_id") or ""),
            entity_type,
            entity_id,
            str(row.get("attribution_role") or ""),
            str(row.get("method") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "eventId": str(row.get("event_id") or ""),
                "entityType": entity_type,
                "entityId": entity_id,
                "attributionRole": str(row.get("attribution_role") or ""),
                "weight": _safe_float(row.get("weight"), 1.0),
                "method": str(row.get("method") or ""),
                "confidence": round(_safe_float(row.get("confidence")), 4),
                "metadata": _safe_dict(row.get("attribution_metadata_json")),
            }
        )
    return items


def _build_calibration_summary(rows: list[dict[str, Any]], *, project_id: str) -> dict[str, Any]:
    event_state: dict[str, dict[str, Any]] = {}
    session_totals: dict[str, dict[str, int]] = {}
    confidence_bands = {"high": 0, "medium": 0, "low": 0}
    method_mix: dict[str, dict[str, Any]] = {}
    confidence_total = 0.0
    confidence_count = 0

    for row in rows:
        event_id = str(row.get("event_id") or "")
        session_id = str(row.get("session_id") or "")
        entity_type = str(row.get("entity_type") or "").strip()
        role = str(row.get("attribution_role") or "")
        method = str(row.get("method") or "")
        confidence = _safe_float(row.get("confidence"))
        token_family = str(row.get("token_family") or "")
        delta_tokens = _safe_int(row.get("delta_tokens"))

        session_totals.setdefault(
            session_id,
            {
                "modelIOTokens": _safe_int(row.get("session_model_io_tokens")),
                "cacheInputTokens": _safe_int(row.get("session_cache_input_tokens")),
            },
        )
        state = event_state.setdefault(
            event_id,
            {
                "hasSupporting": False,
                "hasPrimary": False,
                "supportingCount": 0,
                "primaryCount": 0,
                "exclusiveModelIOTokens": 0,
                "exclusiveCacheInputTokens": 0,
            },
        )
        model_io_marker, cache_marker = _family_buckets(token_family)

        if entity_type:
            state["hasSupporting"] = True
            state["supportingCount"] += 1
            band = _confidence_band(confidence)
            confidence_bands[band] += 1
            confidence_total += confidence
            confidence_count += 1
            method_bucket = method_mix.setdefault(
                method,
                {"method": method, "tokens": 0, "eventIds": set(), "confidenceTotal": 0.0, "confidenceCount": 0},
            )
            method_bucket["tokens"] += delta_tokens
            method_bucket["eventIds"].add(event_id)
            method_bucket["confidenceTotal"] += confidence
            method_bucket["confidenceCount"] += 1

        if role == "primary":
            state["hasPrimary"] = True
            state["primaryCount"] += 1
            state["exclusiveModelIOTokens"] += delta_tokens if model_io_marker else 0
            state["exclusiveCacheInputTokens"] += delta_tokens if cache_marker else 0

    exclusive_model_io = sum(_safe_int(item.get("exclusiveModelIOTokens")) for item in event_state.values())
    exclusive_cache_input = sum(_safe_int(item.get("exclusiveCacheInputTokens")) for item in event_state.values())
    session_model_io = sum(item["modelIOTokens"] for item in session_totals.values())
    session_cache_input = sum(item["cacheInputTokens"] for item in session_totals.values())
    event_count = len(event_state)
    supporting_covered = sum(1 for item in event_state.values() if item["hasSupporting"])
    primary_covered = sum(1 for item in event_state.values() if item["hasPrimary"])
    ambiguous_count = sum(1 for item in event_state.values() if item["supportingCount"] > 1 or item["primaryCount"] > 1)

    return {
        "projectId": project_id,
        "sessionCount": len(session_totals),
        "eventCount": event_count,
        "attributedEventCount": supporting_covered,
        "primaryAttributedEventCount": primary_covered,
        "ambiguousEventCount": ambiguous_count,
        "unattributedEventCount": max(0, event_count - supporting_covered),
        "primaryCoverage": round(primary_covered / max(1, event_count), 4),
        "supportingCoverage": round(supporting_covered / max(1, event_count), 4),
        "sessionModelIOTokens": session_model_io,
        "exclusiveModelIOTokens": exclusive_model_io,
        "modelIOGap": session_model_io - exclusive_model_io,
        "sessionCacheInputTokens": session_cache_input,
        "exclusiveCacheInputTokens": exclusive_cache_input,
        "cacheGap": session_cache_input - exclusive_cache_input,
        "averageConfidence": round(confidence_total / max(1, confidence_count), 4),
        "confidenceBands": [
            {"band": band, "count": count}
            for band, count in (("high", confidence_bands["high"]), ("medium", confidence_bands["medium"]), ("low", confidence_bands["low"]))
        ],
        "methodMix": sorted(
            (
                {
                    "method": payload["method"],
                    "tokens": payload["tokens"],
                    "eventCount": len(payload["eventIds"]),
                    "averageConfidence": round(payload["confidenceTotal"] / max(1, payload["confidenceCount"]), 4),
                }
                for payload in method_mix.values()
                if payload["method"]
            ),
            key=lambda item: (-_safe_int(item.get("tokens")), -_safe_int(item.get("eventCount")), str(item.get("method"))),
        ),
        "generatedAt": _now_iso(),
    }


async def get_usage_attribution_rollup(
    db: Any,
    *,
    project_id: str,
    start: str | None = None,
    end: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await _load_usage_rows(
        db,
        project_id=project_id,
        start=start,
        end=end,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    payload = _summarize_grouped_rows(rows)
    items = payload["rows"]
    total = len(items)
    return {
        "generatedAt": _now_iso(),
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": items[offset : offset + limit],
        "summary": payload["summary"],
    }


async def get_usage_attribution_drilldown(
    db: Any,
    *,
    project_id: str,
    entity_type: str,
    entity_id: str,
    start: str | None = None,
    end: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    rows = await _load_usage_rows(
        db,
        project_id=project_id,
        start=start,
        end=end,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        current_entity_type = str(row.get("entity_type") or "").strip()
        current_entity_id = str(row.get("entity_id") or "").strip()
        if current_entity_type != entity_type or current_entity_id != entity_id:
            continue
        items.append(
            {
                "eventId": str(row.get("event_id") or ""),
                "sessionId": str(row.get("session_id") or ""),
                "rootSessionId": str(row.get("root_session_id") or ""),
                "linkedSessionId": str(row.get("linked_session_id") or ""),
                "sessionType": str(row.get("session_type") or ""),
                "parentSessionId": str(row.get("parent_session_id") or ""),
                "sourceLogId": str(row.get("source_log_id") or ""),
                "capturedAt": str(row.get("captured_at") or ""),
                "eventKind": str(row.get("event_kind") or ""),
                "tokenFamily": str(row.get("token_family") or ""),
                "deltaTokens": _safe_int(row.get("delta_tokens")),
                "costUsdModelIO": round(_safe_float(row.get("cost_usd_model_io")), 6),
                "model": str(row.get("model") or ""),
                "toolName": str(row.get("tool_name") or ""),
                "agentName": str(row.get("agent_name") or ""),
                "entityType": current_entity_type,
                "entityId": current_entity_id,
                "entityLabel": current_entity_id,
                "attributionRole": str(row.get("attribution_role") or ""),
                "weight": _safe_float(row.get("weight"), 1.0),
                "method": str(row.get("method") or ""),
                "confidence": round(_safe_float(row.get("confidence")), 4),
                "metadata": _safe_dict(row.get("attribution_metadata_json")),
            }
        )
    summary = _summarize_grouped_rows(rows)["summary"]
    return {
        "generatedAt": _now_iso(),
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "items": items[offset : offset + limit],
        "summary": summary,
    }


async def get_usage_attribution_calibration(
    db: Any,
    *,
    project_id: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    rows = await _load_usage_rows(
        db,
        project_id=project_id,
        start=start,
        end=end,
    )
    return _build_calibration_summary(rows, project_id=project_id)


async def get_session_usage_attribution_details(
    db: Any,
    *,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    rows = await _load_usage_rows(
        db,
        project_id=project_id,
        session_id=session_id,
    )
    grouped = _summarize_grouped_rows(rows)
    return {
        "usageEvents": _build_event_payload(rows),
        "usageAttributions": _build_attribution_payload(rows),
        "usageAttributionSummary": {
            "generatedAt": _now_iso(),
            "total": len(grouped["rows"]),
            "offset": 0,
            "limit": len(grouped["rows"]),
            "rows": grouped["rows"],
            "summary": grouped["summary"],
        },
        "usageAttributionCalibration": _build_calibration_summary(rows, project_id=project_id),
    }


async def get_session_scope_attribution_metrics(
    db: Any,
    *,
    project_id: str,
    session_ids: list[str],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows = await _load_usage_rows(
        db,
        project_id=project_id,
        session_ids=session_ids,
    )
    metrics: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        session_id = str(row.get("session_id") or "")
        entity_type = str(row.get("entity_type") or "").strip()
        entity_id = str(row.get("entity_id") or "").strip()
        if not session_id or not entity_type or not entity_id:
            continue
        key = (session_id, entity_type, entity_id)
        bucket = metrics.setdefault(
            key,
            {
                "exclusiveTokens": 0,
                "supportingTokens": 0,
                "exclusiveModelIOTokens": 0,
                "exclusiveCacheInputTokens": 0,
                "exclusiveCostUsdModelIO": 0.0,
                "confidenceTotal": 0.0,
                "confidenceCount": 0,
                "sessionModelIOTokens": _safe_int(row.get("session_model_io_tokens")),
            },
        )
        delta_tokens = _safe_int(row.get("delta_tokens"))
        cost_usd = _safe_float(row.get("cost_usd_model_io"))
        confidence = _safe_float(row.get("confidence"))
        token_family = str(row.get("token_family") or "")
        role = str(row.get("attribution_role") or "")
        model_io_marker, cache_marker = _family_buckets(token_family)

        bucket["confidenceTotal"] += confidence
        bucket["confidenceCount"] += 1
        if role == "primary":
            bucket["exclusiveTokens"] += delta_tokens
            bucket["exclusiveModelIOTokens"] += delta_tokens if model_io_marker else 0
            bucket["exclusiveCacheInputTokens"] += delta_tokens if cache_marker else 0
            bucket["exclusiveCostUsdModelIO"] += cost_usd
        elif role == "supporting":
            bucket["supportingTokens"] += delta_tokens

    for bucket in metrics.values():
        bucket["averageConfidence"] = round(bucket["confidenceTotal"] / max(1, bucket["confidenceCount"]), 4)
        bucket["attributionCoverage"] = round(
            bucket["exclusiveModelIOTokens"] / max(1, bucket["sessionModelIOTokens"]),
            4,
        )
        bucket["attributionCacheShare"] = round(
            bucket["exclusiveCacheInputTokens"] / max(1, bucket["exclusiveTokens"]),
            4,
        )
        bucket["exclusiveCostUsdModelIO"] = round(bucket["exclusiveCostUsdModelIO"], 6)
    return metrics
