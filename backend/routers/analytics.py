"""Analytics router for overview, rollups, correlation, and exports."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.analytics import AnalyticsOverviewService
from backend.models import (
    AlertConfig,
    AnalyticsMetric,
    FailurePatternResponse,
    SessionCostCalibrationGroup,
    SessionCostCalibrationMismatchBand,
    SessionCostCalibrationProvenanceCount,
    SessionCostCalibrationSummary,
    SessionUsageAggregateResponse,
    SessionUsageCalibrationSummary,
    SessionUsageDrilldownResponse,
    Notification,
    WorkflowEffectivenessResponse,
)
from backend.model_identity import canonical_model_name, derive_model_identity, model_family_name
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.factory import (
    get_analytics_repository,
    get_alert_config_repository,
    get_entity_link_repository,
    get_feature_repository,
    get_session_repository,
    get_task_repository,
)
from backend.request_scope import get_core_ports, get_request_context
from backend.services.agentic_intelligence_flags import require_workflow_analytics_enabled
from backend.services.agentic_intelligence_flags import require_usage_attribution_enabled
from backend.services.session_usage_analytics import (
    get_usage_attribution_calibration,
    get_usage_attribution_drilldown,
    get_usage_attribution_rollup,
)
from backend.services.workflow_effectiveness import detect_failure_patterns, get_workflow_effectiveness

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])
analytics_overview_service = AnalyticsOverviewService()


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_iso(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _bucket_ts(ts: datetime, period: str) -> str:
    if period == "hourly":
        return ts.replace(minute=0, second=0, microsecond=0).isoformat()
    if period == "daily":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if period == "weekly":
        start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - timedelta(days=start.weekday())
        return start.isoformat()
    return ts.isoformat()


def _rollup_mode(metric: str) -> str:
    lowered = metric.lower()
    if lowered.endswith("_pct") or lowered.endswith("_rate") or "progress" in lowered or "duration" in lowered:
        return "avg"
    return "sum"


def _prom_label(value: Any) -> str:
    raw = str(value if value is not None else "")
    return raw.replace("\\", "\\\\").replace("\"", "\\\"")


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


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _session_usage_metrics(row: dict[str, Any]) -> dict[str, float | int]:
    token_input = _coerce_int(row.get("tokens_in") or row.get("tokensIn"))
    token_output = _coerce_int(row.get("tokens_out") or row.get("tokensOut"))
    model_io_tokens = _coerce_int(row.get("model_io_tokens") or row.get("modelIOTokens"))
    if model_io_tokens <= 0:
        model_io_tokens = token_input + token_output
    cache_creation_input_tokens = _coerce_int(
        row.get("cache_creation_input_tokens") or row.get("cacheCreationInputTokens")
    )
    cache_read_input_tokens = _coerce_int(
        row.get("cache_read_input_tokens") or row.get("cacheReadInputTokens")
    )
    cache_input_tokens = _coerce_int(row.get("cache_input_tokens") or row.get("cacheInputTokens"))
    if cache_input_tokens <= 0:
        cache_input_tokens = cache_creation_input_tokens + cache_read_input_tokens
    observed_tokens = _coerce_int(row.get("observed_tokens") or row.get("observedTokens"))
    if observed_tokens <= 0:
        observed_tokens = model_io_tokens + cache_input_tokens
    if observed_tokens <= 0:
        observed_tokens = token_input + token_output
    tool_reported_tokens = _coerce_int(row.get("tool_reported_tokens") or row.get("toolReportedTokens"))
    cache_share = round(cache_input_tokens / observed_tokens, 4) if observed_tokens > 0 else 0.0
    output_share = round(token_output / model_io_tokens, 4) if model_io_tokens > 0 else 0.0
    return {
        "tokenInput": token_input,
        "tokenOutput": token_output,
        "modelIOTokens": model_io_tokens,
        "cacheCreationInputTokens": cache_creation_input_tokens,
        "cacheReadInputTokens": cache_read_input_tokens,
        "cacheInputTokens": cache_input_tokens,
        "observedTokens": observed_tokens,
        "toolReportedTokens": tool_reported_tokens,
        "cacheShare": cache_share,
        "outputShare": output_share,
        "totalTokens": observed_tokens,
    }


def _session_cost_metrics(row: dict[str, Any]) -> dict[str, Any]:
    reported_cost_usd = _maybe_float(row.get("reported_cost_usd") or row.get("reportedCostUsd"))
    recalculated_cost_usd = _maybe_float(row.get("recalculated_cost_usd") or row.get("recalculatedCostUsd"))
    display_cost_usd = _maybe_float(row.get("display_cost_usd") or row.get("displayCostUsd"))
    if display_cost_usd is None:
        display_cost_usd = _maybe_float(row.get("total_cost") or row.get("totalCost"))
    cost_confidence = _coerce_float(row.get("cost_confidence") or row.get("costConfidence"))
    cost_mismatch_pct = _maybe_float(row.get("cost_mismatch_pct") or row.get("costMismatchPct"))
    if cost_mismatch_pct is None and reported_cost_usd is not None and recalculated_cost_usd is not None:
        baseline = max(abs(reported_cost_usd), abs(recalculated_cost_usd), 1e-9)
        cost_mismatch_pct = round(abs(reported_cost_usd - recalculated_cost_usd) / baseline, 4)
    return {
        "reportedCostUsd": reported_cost_usd,
        "recalculatedCostUsd": recalculated_cost_usd,
        "displayCostUsd": display_cost_usd,
        "costProvenance": str(row.get("cost_provenance") or row.get("costProvenance") or "unknown"),
        "costConfidence": cost_confidence,
        "costMismatchPct": cost_mismatch_pct,
        "pricingModelSource": str(row.get("pricing_model_source") or row.get("pricingModelSource") or ""),
    }


def _session_context_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "currentContextTokens": _coerce_int(row.get("current_context_tokens") or row.get("currentContextTokens")),
        "contextWindowSize": _coerce_int(row.get("context_window_size") or row.get("contextWindowSize")),
        "contextUtilizationPct": round(
            _coerce_float(row.get("context_utilization_pct") or row.get("contextUtilizationPct")),
            2,
        ),
        "contextMeasurementSource": str(row.get("context_measurement_source") or row.get("contextMeasurementSource") or ""),
        "contextMeasuredAt": str(row.get("context_measured_at") or row.get("contextMeasuredAt") or ""),
    }


def _cost_mismatch_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.01:
        return "<1%"
    if value < 0.05:
        return "1-5%"
    if value < 0.1:
        return "5-10%"
    return "10%+"


def _serialize_provenance_counts(counts: dict[str, dict[str, Any]]) -> list[SessionCostCalibrationProvenanceCount]:
    rows = [
        SessionCostCalibrationProvenanceCount(
            provenance=provenance,
            count=int(values.get("count") or 0),
            displayCostUsd=round(_coerce_float(values.get("displayCostUsd")), 4),
        )
        for provenance, values in counts.items()
    ]
    return sorted(rows, key=lambda row: (-row.count, row.provenance))


def _build_cost_calibration_groups(
    rows: list[dict[str, Any]],
    labeler,
) -> list[SessionCostCalibrationGroup]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = str(labeler(row) or "unknown").strip() or "unknown"
        cost = _session_cost_metrics(row)
        current = groups.setdefault(
            label,
            {
                "sessionCount": 0,
                "comparableSessionCount": 0,
                "mismatchSum": 0.0,
                "maxMismatchPct": 0.0,
                "confidenceSum": 0.0,
                "displayCostUsd": 0.0,
                "reportedCostUsd": 0.0,
                "recalculatedCostUsd": 0.0,
                "provenanceCounts": defaultdict(lambda: {"count": 0, "displayCostUsd": 0.0}),
            },
        )
        current["sessionCount"] += 1
        current["confidenceSum"] += _coerce_float(cost["costConfidence"])
        if cost["displayCostUsd"] is not None:
            current["displayCostUsd"] += float(cost["displayCostUsd"])
        if cost["reportedCostUsd"] is not None:
            current["reportedCostUsd"] += float(cost["reportedCostUsd"])
        if cost["recalculatedCostUsd"] is not None:
            current["recalculatedCostUsd"] += float(cost["recalculatedCostUsd"])
        provenance = str(cost["costProvenance"] or "unknown")
        current["provenanceCounts"][provenance]["count"] += 1
        current["provenanceCounts"][provenance]["displayCostUsd"] += _coerce_float(cost["displayCostUsd"])
        if cost["reportedCostUsd"] is not None and cost["recalculatedCostUsd"] is not None and cost["costMismatchPct"] is not None:
            current["comparableSessionCount"] += 1
            current["mismatchSum"] += float(cost["costMismatchPct"])
            current["maxMismatchPct"] = max(current["maxMismatchPct"], float(cost["costMismatchPct"]))

    results: list[SessionCostCalibrationGroup] = []
    for label, values in groups.items():
        session_count = int(values["sessionCount"])
        comparable_session_count = int(values["comparableSessionCount"])
        avg_confidence = round(values["confidenceSum"] / max(session_count, 1), 4)
        avg_mismatch_pct = round(values["mismatchSum"] / comparable_session_count, 4) if comparable_session_count > 0 else 0.0
        results.append(
            SessionCostCalibrationGroup(
                label=label,
                sessionCount=session_count,
                comparableSessionCount=comparable_session_count,
                avgMismatchPct=avg_mismatch_pct,
                maxMismatchPct=round(_coerce_float(values["maxMismatchPct"]), 4),
                avgConfidence=avg_confidence,
                displayCostUsd=round(_coerce_float(values["displayCostUsd"]), 4),
                reportedCostUsd=round(_coerce_float(values["reportedCostUsd"]), 4),
                recalculatedCostUsd=round(_coerce_float(values["recalculatedCostUsd"]), 4),
                provenanceCounts=_serialize_provenance_counts(values["provenanceCounts"]),
            )
        )
    return sorted(results, key=lambda row: (-row.comparableSessionCount, -row.sessionCount, row.label))


def _normalize_artifact_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    return raw.replace(" ", "_")


def _model_dimensions(raw_model: Any) -> dict[str, str]:
    raw = str(raw_model or "").strip()
    canonical = canonical_model_name(raw) or raw or "unknown"
    family = model_family_name(raw) or "Unknown"
    return {
        "raw": raw or "unknown",
        "canonical": canonical,
        "family": family,
    }


def _operation_kind_label(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized == "full_sync":
        return "Full sync"
    if normalized == "rebuild_links":
        return "Link rebuild"
    if normalized == "sync_changed_files":
        return "Changed-path sync"
    if normalized == "test_mapping_backfill":
        return "Mapping backfill"
    return (normalized.replace("_", " ").strip().title() or "Operation")


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


async def _fetch_artifact_analytics_rows(
    db: Any,
    *,
    project_id: str,
    start: str | None,
    end: str | None,
    artifact_type: str | None,
    tool: str | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    artifact_filters_sqlite = [
        "project_id = ?",
        "event_type = 'artifact.linked'",
    ]
    artifact_params_sqlite: list[Any] = [project_id]
    if start:
        artifact_filters_sqlite.append("occurred_at >= ?")
        artifact_params_sqlite.append(start)
    if end:
        artifact_filters_sqlite.append("occurred_at <= ?")
        artifact_params_sqlite.append(end)
    if artifact_type:
        artifact_filters_sqlite.append("LOWER(COALESCE(json_extract(payload_json, '$.type'), status, 'unknown')) = ?")
        artifact_params_sqlite.append(str(artifact_type).strip().lower())
    if tool:
        artifact_filters_sqlite.append("LOWER(COALESCE(tool_name, 'unknown')) = ?")
        artifact_params_sqlite.append(str(tool).strip().lower())

    artifact_filters_pg = [
        "project_id = $1",
        "event_type = 'artifact.linked'",
    ]
    artifact_params_pg: list[Any] = [project_id]
    pg_idx = 2
    if start:
        artifact_filters_pg.append(f"occurred_at >= ${pg_idx}")
        artifact_params_pg.append(start)
        pg_idx += 1
    if end:
        artifact_filters_pg.append(f"occurred_at <= ${pg_idx}")
        artifact_params_pg.append(end)
        pg_idx += 1
    if artifact_type:
        artifact_filters_pg.append(f"LOWER(COALESCE(payload_json::jsonb->>'type', status, 'unknown')) = ${pg_idx}")
        artifact_params_pg.append(str(artifact_type).strip().lower())
        pg_idx += 1
    if tool:
        artifact_filters_pg.append(f"LOWER(COALESCE(tool_name, 'unknown')) = ${pg_idx}")
        artifact_params_pg.append(str(tool).strip().lower())
        pg_idx += 1

    artifact_rows = await _query_rows(
        db,
        sqlite_query=f"""
            SELECT
                session_id,
                feature_id,
                model,
                tool_name,
                agent,
                skill,
                status,
                occurred_at,
                payload_json
            FROM telemetry_events
            WHERE {" AND ".join(artifact_filters_sqlite)}
            ORDER BY occurred_at DESC
        """,
        sqlite_params=tuple(artifact_params_sqlite),
        postgres_query=f"""
            SELECT
                session_id,
                feature_id,
                model,
                tool_name,
                agent,
                skill,
                status,
                occurred_at,
                payload_json
            FROM telemetry_events
            WHERE {" AND ".join(artifact_filters_pg)}
            ORDER BY occurred_at DESC
        """,
        postgres_params=tuple(artifact_params_pg),
    )

    lifecycle_filters_sqlite = [
        "project_id = ?",
        "event_type = 'session.lifecycle'",
    ]
    lifecycle_params_sqlite: list[Any] = [project_id]
    if start:
        lifecycle_filters_sqlite.append("occurred_at >= ?")
        lifecycle_params_sqlite.append(start)
    if end:
        lifecycle_filters_sqlite.append("occurred_at <= ?")
        lifecycle_params_sqlite.append(end)

    lifecycle_filters_pg = [
        "project_id = $1",
        "event_type = 'session.lifecycle'",
    ]
    lifecycle_params_pg: list[Any] = [project_id]
    pg_idx = 2
    if start:
        lifecycle_filters_pg.append(f"occurred_at >= ${pg_idx}")
        lifecycle_params_pg.append(start)
        pg_idx += 1
    if end:
        lifecycle_filters_pg.append(f"occurred_at <= ${pg_idx}")
        lifecycle_params_pg.append(end)
        pg_idx += 1

    lifecycle_rows = await _query_rows(
        db,
        sqlite_query=f"""
            SELECT
                session_id,
                feature_id,
                model,
                status,
                occurred_at,
                token_input,
                token_output,
                cost_usd,
                payload_json
            FROM telemetry_events
            WHERE {" AND ".join(lifecycle_filters_sqlite)}
            ORDER BY occurred_at DESC
        """,
        sqlite_params=tuple(lifecycle_params_sqlite),
        postgres_query=f"""
            SELECT
                session_id,
                feature_id,
                model,
                status,
                occurred_at,
                token_input,
                token_output,
                cost_usd,
                payload_json
            FROM telemetry_events
            WHERE {" AND ".join(lifecycle_filters_pg)}
            ORDER BY occurred_at DESC
        """,
        postgres_params=tuple(lifecycle_params_pg),
    )

    feature_link_rows = await _query_rows(
        db,
        sqlite_query="""
            SELECT
                el.target_id AS session_id,
                el.source_id AS feature_id
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND f.project_id = ?
        """,
        sqlite_params=(project_id,),
        postgres_query="""
            SELECT
                el.target_id AS session_id,
                el.source_id AS feature_id
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND f.project_id = $1
        """,
        postgres_params=(project_id,),
    )

    feature_rows = await _query_rows(
        db,
        sqlite_query="SELECT id, name FROM features WHERE project_id = ?",
        sqlite_params=(project_id,),
        postgres_query="SELECT id, name FROM features WHERE project_id = $1",
        postgres_params=(project_id,),
    )

    event_filters_sqlite = ["project_id = ?"]
    event_params_sqlite: list[Any] = [project_id]
    if start:
        event_filters_sqlite.append("occurred_at >= ?")
        event_params_sqlite.append(start)
    if end:
        event_filters_sqlite.append("occurred_at <= ?")
        event_params_sqlite.append(end)

    event_filters_pg = ["project_id = $1"]
    event_params_pg: list[Any] = [project_id]
    pg_idx = 2
    if start:
        event_filters_pg.append(f"occurred_at >= ${pg_idx}")
        event_params_pg.append(start)
        pg_idx += 1
    if end:
        event_filters_pg.append(f"occurred_at <= ${pg_idx}")
        event_params_pg.append(end)
        pg_idx += 1

    command_rows = await _query_rows(
        db,
        sqlite_query=f"""
            SELECT session_id, model, occurred_at, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_sqlite)} AND event_type = 'log.command'
            ORDER BY occurred_at DESC
        """,
        sqlite_params=tuple(event_params_sqlite),
        postgres_query=f"""
            SELECT session_id, model, occurred_at, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_pg)} AND event_type = 'log.command'
            ORDER BY occurred_at DESC
        """,
        postgres_params=tuple(event_params_pg),
    )

    agent_rows = await _query_rows(
        db,
        sqlite_query=f"""
            SELECT session_id, model, agent, occurred_at, event_type, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_sqlite)} AND event_type LIKE 'log.%'
            ORDER BY occurred_at DESC
        """,
        sqlite_params=tuple(event_params_sqlite),
        postgres_query=f"""
            SELECT session_id, model, agent, occurred_at, event_type, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_pg)} AND event_type LIKE 'log.%'
            ORDER BY occurred_at DESC
        """,
        postgres_params=tuple(event_params_pg),
    )

    return artifact_rows, lifecycle_rows, feature_link_rows, feature_rows, command_rows, agent_rows


def _build_artifact_analytics_payload(
    *,
    artifact_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    feature_link_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    agent_rows: list[dict[str, Any]],
    detail_limit: int,
    feature_filter: str | None,
    model_filter: str | None,
    model_family_filter: str | None,
) -> dict[str, Any]:
    detail_limit = max(10, min(int(detail_limit or 100), 500))
    feature_filter_norm = str(feature_filter or "").strip()
    model_filter_norm = canonical_model_name(model_filter).strip().lower() if model_filter else ""
    model_family_filter_norm = str(model_family_filter or "").strip().lower()

    feature_name_by_id: dict[str, str] = {}
    for row in feature_rows:
        feature_id = str(row.get("id") or "").strip()
        if not feature_id:
            continue
        feature_name_by_id[feature_id] = str(row.get("name") or "").strip() or feature_id

    lifecycle_by_session: dict[str, dict[str, Any]] = {}
    for row in lifecycle_rows:
        session_id = str(row.get("session_id") or "").strip()
        if not session_id or session_id in lifecycle_by_session:
            continue
        model_dims = _model_dimensions(row.get("model"))
        lifecycle_by_session[session_id] = {
            "feature_id": str(row.get("feature_id") or "").strip(),
            "model": model_dims["canonical"],
            "model_raw": model_dims["raw"],
            "model_family": model_dims["family"],
            "status": str(row.get("status") or "").strip(),
            "occurred_at": str(row.get("occurred_at") or ""),
            "token_input": _coerce_int(row.get("token_input")),
            "token_output": _coerce_int(row.get("token_output")),
            "cost_usd": _coerce_float(row.get("cost_usd")),
            "metadata": _safe_json(row.get("payload_json")),
        }

    session_feature_map: dict[str, set[str]] = defaultdict(set)
    for row in feature_link_rows:
        session_id = str(row.get("session_id") or "").strip()
        feature_id = str(row.get("feature_id") or "").strip()
        if session_id and feature_id:
            session_feature_map[session_id].add(feature_id)
    for session_id, lifecycle in lifecycle_by_session.items():
        feature_id = str(lifecycle.get("feature_id") or "").strip()
        if feature_id:
            session_feature_map[session_id].add(feature_id)

    records: list[dict[str, Any]] = []
    unique_agents: set[str] = set()
    unique_skills: set[str] = set()

    for row in artifact_rows:
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        payload = _safe_json(row.get("payload_json"))
        artifact_type = _normalize_artifact_type(payload.get("type") or row.get("status"))
        lifecycle = lifecycle_by_session.get(session_id, {})
        model_dims = _model_dimensions(str(row.get("model") or "").strip() or str(lifecycle.get("model_raw") or lifecycle.get("model") or "unknown"))
        model = model_dims["canonical"]
        model_family = model_dims["family"]
        tool_name = str(row.get("tool_name") or "").strip() or "unknown"
        source = str(payload.get("source") or "unknown").strip() or "unknown"
        agent = str(row.get("agent") or "").strip()
        skill = str(row.get("skill") or "").strip()

        feature_ids = set(session_feature_map.get(session_id, set()))
        direct_feature_id = str(row.get("feature_id") or "").strip()
        if direct_feature_id:
            feature_ids.add(direct_feature_id)

        if feature_filter_norm and feature_filter_norm not in feature_ids:
            continue
        if model_filter_norm and model_filter_norm != model.lower():
            continue
        if model_family_filter_norm and model_family_filter_norm != model_family.lower():
            continue
        if agent:
            unique_agents.add(agent)
        if skill:
            unique_skills.add(skill)

        records.append(
            {
                "session_id": session_id,
                "feature_ids": sorted(feature_ids),
                "model": model,
                "model_raw": model_dims["raw"],
                "model_family": model_family,
                "tool_name": tool_name,
                "source": source,
                "artifact_type": artifact_type,
                "title": str(payload.get("title") or "").strip(),
                "url": str(payload.get("url") or "").strip(),
                "occurred_at": str(row.get("occurred_at") or ""),
                "agent": agent,
                "skill": skill,
            }
        )

    def session_metrics(session_id: str) -> dict[str, Any]:
        lifecycle = lifecycle_by_session.get(session_id, {})
        token_input = _coerce_int(lifecycle.get("token_input"))
        token_output = _coerce_int(lifecycle.get("token_output"))
        return {
            "token_input": token_input,
            "token_output": token_output,
            "cost_usd": _coerce_float(lifecycle.get("cost_usd")),
            "status": str(lifecycle.get("status") or ""),
            "occurred_at": str(lifecycle.get("occurred_at") or ""),
            "total_tokens": token_input + token_output,
        }

    by_type: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_tool: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_model_family: dict[str, dict[str, Any]] = {}
    model_artifact: dict[tuple[str, str], dict[str, Any]] = {}
    artifact_tool: dict[tuple[str, str], dict[str, Any]] = {}
    model_artifact_tool: dict[tuple[str, str, str], dict[str, Any]] = {}
    by_session: dict[str, dict[str, Any]] = {}
    by_feature: dict[str, dict[str, Any]] = {}

    type_session_pairs: set[tuple[str, str]] = set()
    model_session_pairs: set[tuple[str, str]] = set()
    model_family_session_pairs: set[tuple[str, str]] = set()
    model_artifact_session_pairs: set[tuple[str, str, str]] = set()
    model_artifact_tool_session_pairs: set[tuple[str, str, str, str]] = set()
    feature_session_pairs: set[tuple[str, str]] = set()

    for record in records:
        session_id = record["session_id"]
        artifact_type = record["artifact_type"]
        model = record["model"] or "unknown"
        model_raw = record.get("model_raw") or model
        model_family = record.get("model_family") or "Unknown"
        tool_name = record["tool_name"] or "unknown"
        source = record["source"] or "unknown"
        feature_ids = record["feature_ids"]

        type_entry = by_type.setdefault(
            artifact_type,
            {
                "artifactType": artifact_type,
                "count": 0,
                "sessionSet": set(),
                "featureSet": set(),
                "modelSet": set(),
                "toolSet": set(),
                "sourceSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        type_entry["count"] += 1
        type_entry["sessionSet"].add(session_id)
        type_entry["modelSet"].add(model)
        type_entry["toolSet"].add(tool_name)
        type_entry["sourceSet"].add(source)
        for feature_id in feature_ids:
            if feature_id:
                type_entry["featureSet"].add(feature_id)

        source_entry = by_source.setdefault(
            source,
            {"source": source, "count": 0, "sessionSet": set(), "artifactTypeSet": set()},
        )
        source_entry["count"] += 1
        source_entry["sessionSet"].add(session_id)
        source_entry["artifactTypeSet"].add(artifact_type)

        tool_entry = by_tool.setdefault(
            tool_name,
            {"toolName": tool_name, "count": 0, "sessionSet": set(), "artifactTypeSet": set(), "modelSet": set()},
        )
        tool_entry["count"] += 1
        tool_entry["sessionSet"].add(session_id)
        tool_entry["artifactTypeSet"].add(artifact_type)
        tool_entry["modelSet"].add(model)

        model_entry = by_model.setdefault(
            model,
            {
                "model": model,
                "modelRawSet": set(),
                "modelFamily": model_family,
                "count": 0,
                "sessionSet": set(),
                "artifactTypeSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        model_entry["count"] += 1
        model_entry["modelRawSet"].add(model_raw)
        model_entry["sessionSet"].add(session_id)
        model_entry["artifactTypeSet"].add(artifact_type)

        model_family_entry = by_model_family.setdefault(
            model_family,
            {
                "modelFamily": model_family,
                "count": 0,
                "sessionSet": set(),
                "modelSet": set(),
                "artifactTypeSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        model_family_entry["count"] += 1
        model_family_entry["sessionSet"].add(session_id)
        model_family_entry["modelSet"].add(model)
        model_family_entry["artifactTypeSet"].add(artifact_type)

        model_artifact_entry = model_artifact.setdefault(
            (model, artifact_type),
            {
                "model": model,
                "modelRawSet": set(),
                "modelFamily": model_family,
                "artifactType": artifact_type,
                "count": 0,
                "sessionSet": set(),
                "toolSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        model_artifact_entry["count"] += 1
        model_artifact_entry["modelRawSet"].add(model_raw)
        model_artifact_entry["sessionSet"].add(session_id)
        model_artifact_entry["toolSet"].add(tool_name)

        artifact_tool_entry = artifact_tool.setdefault(
            (artifact_type, tool_name),
            {
                "artifactType": artifact_type,
                "toolName": tool_name,
                "count": 0,
                "sessionSet": set(),
                "modelSet": set(),
            },
        )
        artifact_tool_entry["count"] += 1
        artifact_tool_entry["sessionSet"].add(session_id)
        artifact_tool_entry["modelSet"].add(model)

        model_artifact_tool_entry = model_artifact_tool.setdefault(
            (model, artifact_type, tool_name),
            {
                "model": model,
                "modelRawSet": set(),
                "modelFamily": model_family,
                "artifactType": artifact_type,
                "toolName": tool_name,
                "count": 0,
                "sessionSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        model_artifact_tool_entry["count"] += 1
        model_artifact_tool_entry["modelRawSet"].add(model_raw)
        model_artifact_tool_entry["sessionSet"].add(session_id)

        lifecycle = session_metrics(session_id)
        session_entry = by_session.setdefault(
            session_id,
            {
                "sessionId": session_id,
                "model": model,
                "modelRaw": model_raw,
                "modelFamily": model_family,
                "status": lifecycle["status"],
                "startedAt": lifecycle["occurred_at"],
                "artifactCount": 0,
                "artifactTypeCounts": defaultdict(int),
                "toolSet": set(),
                "sourceSet": set(),
                "featureSet": set(),
                "featureNameSet": set(),
                "tokenInput": lifecycle["token_input"],
                "tokenOutput": lifecycle["token_output"],
                "totalCost": lifecycle["cost_usd"],
            },
        )
        session_entry["artifactCount"] += 1
        session_entry["artifactTypeCounts"][artifact_type] += 1
        session_entry["toolSet"].add(tool_name)
        session_entry["sourceSet"].add(source)
        for feature_id in feature_ids:
            if not feature_id:
                continue
            session_entry["featureSet"].add(feature_id)
            session_entry["featureNameSet"].add(feature_name_by_id.get(feature_id, feature_id))

        if feature_ids:
            for feature_id in feature_ids:
                feature_entry = by_feature.setdefault(
                    feature_id,
                    {
                        "featureId": feature_id,
                        "featureName": feature_name_by_id.get(feature_id, feature_id),
                        "artifactCount": 0,
                        "sessionSet": set(),
                        "modelSet": set(),
                        "toolSet": set(),
                        "artifactTypeCounts": defaultdict(int),
                        "tokenInput": 0,
                        "tokenOutput": 0,
                        "totalCost": 0.0,
                    },
                )
                feature_entry["artifactCount"] += 1
                feature_entry["sessionSet"].add(session_id)
                feature_entry["modelSet"].add(model)
                feature_entry["toolSet"].add(tool_name)
                feature_entry["artifactTypeCounts"][artifact_type] += 1
                feature_session_pairs.add((session_id, feature_id))

        type_session_pairs.add((session_id, artifact_type))
        model_session_pairs.add((session_id, model))
        model_family_session_pairs.add((session_id, model_family))
        model_artifact_session_pairs.add((session_id, model, artifact_type))
        model_artifact_tool_session_pairs.add((session_id, model, artifact_type, tool_name))

    for session_id, artifact_type in type_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = by_type.get(artifact_type)
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    for session_id, model in model_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = by_model.get(model)
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    for session_id, model_family in model_family_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = by_model_family.get(model_family)
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    for session_id, model, artifact_type in model_artifact_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = model_artifact.get((model, artifact_type))
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    for session_id, model, artifact_type, tool_name in model_artifact_tool_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = model_artifact_tool.get((model, artifact_type, tool_name))
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    for session_id, feature_id in feature_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = by_feature.get(feature_id)
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    by_type_items = sorted(
        [
            {
                "artifactType": entry["artifactType"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "features": len(entry["featureSet"]),
                "models": sorted(str(v) for v in entry["modelSet"]),
                "tools": sorted(str(v) for v in entry["toolSet"]),
                "sources": sorted(str(v) for v in entry["sourceSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in by_type.values()
        ],
        key=lambda row: (int(row["count"]), str(row["artifactType"])),
        reverse=True,
    )

    by_source_items = sorted(
        [
            {
                "source": entry["source"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "artifactTypes": sorted(str(v) for v in entry["artifactTypeSet"]),
            }
            for entry in by_source.values()
        ],
        key=lambda row: (int(row["count"]), str(row["source"])),
        reverse=True,
    )

    by_tool_items = sorted(
        [
            {
                "toolName": entry["toolName"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "artifactTypes": sorted(str(v) for v in entry["artifactTypeSet"]),
                "models": sorted(str(v) for v in entry["modelSet"]),
            }
            for entry in by_tool.values()
        ],
        key=lambda row: (int(row["count"]), str(row["toolName"])),
        reverse=True,
    )

    model_items = sorted(
        [
            {
                "model": entry["model"],
                "modelRaw": sorted(str(v) for v in entry["modelRawSet"])[0] if entry["modelRawSet"] else entry["model"],
                "modelFamily": entry["modelFamily"],
                "artifactCount": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "artifactTypes": sorted(str(v) for v in entry["artifactTypeSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in by_model.values()
        ],
        key=lambda row: (int(row["artifactCount"]), str(row["model"])),
        reverse=True,
    )

    model_family_items = sorted(
        [
            {
                "modelFamily": entry["modelFamily"],
                "artifactCount": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "models": sorted(str(v) for v in entry["modelSet"]),
                "artifactTypes": sorted(str(v) for v in entry["artifactTypeSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in by_model_family.values()
        ],
        key=lambda row: (int(row["artifactCount"]), str(row["modelFamily"])),
        reverse=True,
    )

    model_artifact_items = sorted(
        [
            {
                "model": entry["model"],
                "modelRaw": sorted(str(v) for v in entry["modelRawSet"])[0] if entry["modelRawSet"] else entry["model"],
                "modelFamily": entry["modelFamily"],
                "artifactType": entry["artifactType"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "tools": sorted(str(v) for v in entry["toolSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in model_artifact.values()
        ],
        key=lambda row: (int(row["count"]), str(row["model"]), str(row["artifactType"])),
        reverse=True,
    )

    artifact_tool_items = sorted(
        [
            {
                "artifactType": entry["artifactType"],
                "toolName": entry["toolName"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "models": sorted(str(v) for v in entry["modelSet"]),
            }
            for entry in artifact_tool.values()
        ],
        key=lambda row: (int(row["count"]), str(row["artifactType"]), str(row["toolName"])),
        reverse=True,
    )

    model_artifact_tool_items = sorted(
        [
            {
                "model": entry["model"],
                "modelRaw": sorted(str(v) for v in entry["modelRawSet"])[0] if entry["modelRawSet"] else entry["model"],
                "modelFamily": entry["modelFamily"],
                "artifactType": entry["artifactType"],
                "toolName": entry["toolName"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in model_artifact_tool.values()
        ],
        key=lambda row: (int(row["count"]), str(row["model"]), str(row["artifactType"]), str(row["toolName"])),
        reverse=True,
    )

    by_session_items = sorted(
        [
            {
                "sessionId": entry["sessionId"],
                "model": entry["model"],
                "modelRaw": entry["modelRaw"],
                "modelFamily": entry["modelFamily"],
                "status": entry["status"],
                "startedAt": entry["startedAt"],
                "artifactCount": entry["artifactCount"],
                "artifactTypes": sorted(
                    [
                        {"artifactType": artifact_type, "count": count}
                        for artifact_type, count in entry["artifactTypeCounts"].items()
                    ],
                    key=lambda row: (int(row["count"]), str(row["artifactType"])),
                    reverse=True,
                ),
                "toolNames": sorted(str(v) for v in entry["toolSet"]),
                "sources": sorted(str(v) for v in entry["sourceSet"]),
                "featureIds": sorted(str(v) for v in entry["featureSet"]),
                "featureNames": sorted(str(v) for v in entry["featureNameSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in by_session.values()
        ],
        key=lambda row: (int(row["artifactCount"]), str(row["startedAt"])),
        reverse=True,
    )

    by_feature_items = sorted(
        [
            {
                "featureId": entry["featureId"],
                "featureName": entry["featureName"],
                "artifactCount": entry["artifactCount"],
                "sessions": len(entry["sessionSet"]),
                "models": sorted(str(v) for v in entry["modelSet"]),
                "tools": sorted(str(v) for v in entry["toolSet"]),
                "artifactTypes": sorted(
                    [
                        {"artifactType": artifact_type, "count": count}
                        for artifact_type, count in entry["artifactTypeCounts"].items()
                    ],
                    key=lambda row: (int(row["count"]), str(row["artifactType"])),
                    reverse=True,
                ),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in by_feature.values()
        ],
        key=lambda row: (int(row["artifactCount"]), str(row["featureName"])),
        reverse=True,
    )

    kind_totals = {
        "agents": sum(1 for row in records if row["artifact_type"] == "agent"),
        "skills": sum(1 for row in records if row["artifact_type"] == "skill"),
        "commands": sum(1 for row in records if str(row["artifact_type"]).startswith("command")),
        "manifests": sum(1 for row in records if row["artifact_type"] == "manifest"),
        "requests": sum(1 for row in records if row["artifact_type"] == "request"),
    }

    command_model: dict[tuple[str, str], dict[str, Any]] = {}
    command_model_session_pairs: set[tuple[str, str, str]] = set()
    for row in command_rows:
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        feature_ids = set(session_feature_map.get(session_id, set()))
        if feature_filter_norm and feature_filter_norm not in feature_ids:
            continue
        model_dims = _model_dimensions(str(row.get("model") or "").strip() or str(lifecycle_by_session.get(session_id, {}).get("model_raw") or "unknown"))
        if model_filter_norm and model_filter_norm != model_dims["canonical"].lower():
            continue
        if model_family_filter_norm and model_family_filter_norm != model_dims["family"].lower():
            continue
        payload = _safe_json(row.get("payload_json"))
        metadata = payload.get("metadata")
        command_name = ""
        if isinstance(metadata, dict):
            parsed = metadata.get("parsedCommand")
            if isinstance(parsed, dict):
                command_name = str(parsed.get("command") or "").strip()
        if not command_name:
            command_name = str(payload.get("content") or "").strip()
        if not command_name:
            continue
        entry = command_model.setdefault(
            (command_name, model_dims["canonical"]),
            {
                "command": command_name,
                "model": model_dims["canonical"],
                "modelRawSet": set(),
                "modelFamily": model_dims["family"],
                "count": 0,
                "sessionSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        entry["count"] += 1
        entry["modelRawSet"].add(model_dims["raw"])
        entry["sessionSet"].add(session_id)
        command_model_session_pairs.add((session_id, command_name, model_dims["canonical"]))

    for session_id, command_name, model in command_model_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = command_model.get((command_name, model))
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    command_model_items = sorted(
        [
            {
                "command": entry["command"],
                "model": entry["model"],
                "modelRaw": sorted(str(v) for v in entry["modelRawSet"])[0] if entry["modelRawSet"] else entry["model"],
                "modelFamily": entry["modelFamily"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in command_model.values()
        ],
        key=lambda row: (int(row["count"]), str(row["command"]), str(row["model"])),
        reverse=True,
    )

    agent_model: dict[tuple[str, str], dict[str, Any]] = {}
    agent_model_session_pairs: set[tuple[str, str, str]] = set()

    def add_agent_model_observation(session_id: str, model_dims: dict[str, str], agent_name: str) -> None:
        normalized_agent = str(agent_name or "").strip()
        if not session_id or not normalized_agent:
            return
        entry = agent_model.setdefault(
            (normalized_agent, model_dims["canonical"]),
            {
                "agent": normalized_agent,
                "model": model_dims["canonical"],
                "modelRawSet": set(),
                "modelFamily": model_dims["family"],
                "count": 0,
                "sessionSet": set(),
                "tokenInput": 0,
                "tokenOutput": 0,
                "totalCost": 0.0,
            },
        )
        entry["count"] += 1
        entry["modelRawSet"].add(model_dims["raw"])
        entry["sessionSet"].add(session_id)
        agent_model_session_pairs.add((session_id, normalized_agent, model_dims["canonical"]))

    def extract_agent_name(
        *,
        row_agent: Any,
        event_type: Any,
        payload: dict[str, Any],
    ) -> str:
        if row_agent:
            return str(row_agent).strip()
        metadata = payload.get("metadata") if isinstance(payload, dict) else {}
        if isinstance(metadata, dict):
            resolved = str(
                metadata.get("agentName")
                or metadata.get("agent_name")
                or metadata.get("subagentName")
                or metadata.get("taskSubagentType")
                or metadata.get("subagentType")
                or metadata.get("subagent_type")
                or metadata.get("subagentAgentId")
                or metadata.get("agentId")
                or ""
            ).strip()
            if resolved:
                return resolved
        if isinstance(payload, dict):
            resolved = str(
                payload.get("agentName")
                or payload.get("agent_name")
                or payload.get("subagentName")
                or payload.get("subagentType")
                or payload.get("subagent_type")
                or ""
            ).strip()
            if resolved:
                return resolved
        speaker = str((payload.get("speaker") if isinstance(payload, dict) else "") or "").strip().lower()
        if speaker == "agent":
            return "Main Session"
        if str(event_type or "").strip().lower() == "log.subagent_start":
            return "Subagent"
        return ""

    for row in agent_rows:
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        feature_ids = set(session_feature_map.get(session_id, set()))
        if feature_filter_norm and feature_filter_norm not in feature_ids:
            continue
        model_dims = _model_dimensions(str(row.get("model") or "").strip() or str(lifecycle_by_session.get(session_id, {}).get("model_raw") or "unknown"))
        if model_filter_norm and model_filter_norm != model_dims["canonical"].lower():
            continue
        if model_family_filter_norm and model_family_filter_norm != model_dims["family"].lower():
            continue
        payload = _safe_json(row.get("payload_json"))
        agent_name = extract_agent_name(
            row_agent=row.get("agent"),
            event_type=row.get("event_type"),
            payload=payload if isinstance(payload, dict) else {},
        )
        if not agent_name:
            continue
        add_agent_model_observation(session_id, model_dims, agent_name)

    for record in records:
        session_id = str(record.get("session_id") or "").strip()
        if not session_id:
            continue
        model_dims = _model_dimensions(str(record.get("model_raw") or record.get("model") or "unknown"))
        if model_filter_norm and model_filter_norm != model_dims["canonical"].lower():
            continue
        if model_family_filter_norm and model_family_filter_norm != model_dims["family"].lower():
            continue
        agent_name = str(record.get("agent") or "").strip()
        if not agent_name and str(record.get("artifact_type") or "") == "agent":
            agent_name = str(record.get("title") or "").strip()
        if not agent_name:
            continue
        add_agent_model_observation(session_id, model_dims, agent_name)

    for session_id, agent_name, model in agent_model_session_pairs:
        lifecycle = session_metrics(session_id)
        entry = agent_model.get((agent_name, model))
        if not entry:
            continue
        entry["tokenInput"] += lifecycle["token_input"]
        entry["tokenOutput"] += lifecycle["token_output"]
        entry["totalCost"] += lifecycle["cost_usd"]

    agent_model_items = sorted(
        [
            {
                "agent": entry["agent"],
                "model": entry["model"],
                "modelRaw": sorted(str(v) for v in entry["modelRawSet"])[0] if entry["modelRawSet"] else entry["model"],
                "modelFamily": entry["modelFamily"],
                "count": entry["count"],
                "sessions": len(entry["sessionSet"]),
                "tokenInput": entry["tokenInput"],
                "tokenOutput": entry["tokenOutput"],
                "totalTokens": entry["tokenInput"] + entry["tokenOutput"],
                "totalCost": round(entry["totalCost"], 6),
            }
            for entry in agent_model.values()
        ],
        key=lambda row: (int(row["count"]), str(row["agent"]), str(row["model"])),
        reverse=True,
    )

    return {
        "totals": {
            "artifactCount": len(records),
            "artifactTypes": len(by_type_items),
            "sessions": len(by_session),
            "features": len(by_feature),
            "models": len(by_model),
            "modelFamilies": len(by_model_family),
            "tools": len(by_tool),
            "sources": len(by_source),
            "agents": len(unique_agents),
            "skills": len(unique_skills),
            "commands": kind_totals["commands"],
            "kindTotals": kind_totals,
        },
        "byType": by_type_items,
        "bySource": by_source_items,
        "byTool": by_tool_items,
        "bySession": by_session_items[:detail_limit],
        "byFeature": by_feature_items[:detail_limit],
        "modelArtifact": model_artifact_items,
        "modelFamilies": model_family_items,
        "artifactTool": artifact_tool_items,
        "modelArtifactTool": model_artifact_tool_items,
        "commandModel": command_model_items,
        "agentModel": agent_model_items,
        "tokenUsage": {
            "byArtifactType": [
                {
                    "artifactType": row["artifactType"],
                    "tokenInput": row["tokenInput"],
                    "tokenOutput": row["tokenOutput"],
                    "totalTokens": row["totalTokens"],
                    "totalCost": row["totalCost"],
                }
                for row in by_type_items
            ],
            "byModel": model_items,
            "byModelArtifact": model_artifact_items,
            "byModelFamily": model_family_items,
        },
        "detailLimit": detail_limit,
    }


async def _load_artifact_analytics_payload(
    db: Any,
    *,
    project_id: str,
    start: str | None,
    end: str | None,
    artifact_type: str | None,
    model: str | None,
    model_family: str | None,
    tool: str | None,
    feature_filter: str | None,
    detail_limit: int,
) -> dict[str, Any]:
    artifact_rows, lifecycle_rows, feature_link_rows, feature_rows, command_rows, agent_rows = await _fetch_artifact_analytics_rows(
        db,
        project_id=project_id,
        start=start,
        end=end,
        artifact_type=artifact_type,
        tool=tool,
    )
    return _build_artifact_analytics_payload(
        artifact_rows=artifact_rows,
        lifecycle_rows=lifecycle_rows,
        feature_link_rows=feature_link_rows,
        feature_rows=feature_rows,
        command_rows=command_rows,
        agent_rows=agent_rows,
        detail_limit=detail_limit,
        feature_filter=feature_filter,
        model_filter=model,
        model_family_filter=model_family,
    )


class AlertConfigCreate(BaseModel):
    id: str | None = None
    name: str
    metric: str
    operator: str
    threshold: float
    isActive: bool = True
    scope: str = "session"


class AlertConfigPatch(BaseModel):
    name: str | None = None
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    isActive: bool | None = None
    scope: str | None = None


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
async def get_metrics():
    """Legacy metrics endpoint."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    session_repo = get_session_repository(db)

    types = [
        "session_cost", "session_tokens", "session_count",
        "task_velocity", "task_completion_pct",
    ]
    latest = await repo.get_latest_entries(project.id, types)
    session_stats = await session_repo.get_project_stats(project.id)
    return [
        AnalyticsMetric(name="Total Cost", value=round(session_stats.get("cost", latest.get("session_cost", 0.0)), 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=int(session_stats.get("tokens", latest.get("session_tokens", 0))), unit="tokens"),
        AnalyticsMetric(name="Sessions", value=int(session_stats.get("count", latest.get("session_count", 0))), unit="count"),
        AnalyticsMetric(name="Tasks Done", value=int(latest.get("task_velocity", 0)), unit="count"),
        AnalyticsMetric(name="Completion", value=round(latest.get("task_completion_pct", 0.0), 1), unit="%"),
    ]


@analytics_router.get("/overview")
async def get_overview(
    start: str | None = None,
    end: str | None = None,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    if isinstance(request_context, RequestContext) or isinstance(core_ports, CorePorts):
        db = await connection.get_connection()
        app_request = await resolve_application_request(request_context, core_ports, db)
        return await analytics_overview_service.get_overview(
            app_request.context,
            app_request.ports,
            start=start,
            end=end,
        )

    project = project_manager.get_active_project()
    if not project:
        return {"kpis": {}, "generatedAt": datetime.now(timezone.utc).isoformat()}

    db = await connection.get_connection()
    analytics_repo = get_analytics_repository(db)
    task_repo = get_task_repository(db)
    session_repo = get_session_repository(db)

    latest = await analytics_repo.get_latest_entries(
        project.id,
        [
            "session_cost",
            "session_tokens",
            "session_count",
            "session_duration",
            "task_velocity",
            "task_completion_pct",
            "tool_call_count",
            "tool_success_rate",
            "feature_progress",
        ],
    )
    task_stats = await task_repo.get_project_stats(project.id)
    session_stats = await session_repo.get_project_stats(project.id)
    session_filters: dict[str, Any] = {"include_subagents": True}
    if start:
        session_filters["start_date"] = start
    if end:
        session_filters["end_date"] = end
    recent_sessions = await session_repo.list_paginated(0, 250, project.id, "started_at", "desc", session_filters)

    model_counts: dict[str, int] = defaultdict(int)
    for row in recent_sessions:
        model = canonical_model_name(str(row.get("model") or "").strip())
        if model:
            model_counts[model] += 1
    top_models = [
        {"name": name, "usage": count}
        for name, count in sorted(model_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    ]
    context_rows = [row for row in recent_sessions if _coerce_int(row.get("current_context_tokens")) > 0]
    avg_context_utilization_pct = round(
        sum(_coerce_float(row.get("context_utilization_pct")) for row in context_rows) / len(context_rows),
        2,
    ) if context_rows else 0.0

    return {
        "kpis": {
            "sessionCost": float(session_stats.get("cost", latest.get("session_cost", 0.0))),
            "sessionTokens": int(session_stats.get("tokens", latest.get("session_tokens", 0))),
            "sessionCount": int(session_stats.get("count", latest.get("session_count", 0))),
            "sessionDurationAvg": float(session_stats.get("duration", latest.get("session_duration", 0.0))),
            "modelIOTokens": sum(_session_usage_metrics(row)["modelIOTokens"] for row in recent_sessions),
            "cacheInputTokens": sum(_session_usage_metrics(row)["cacheInputTokens"] for row in recent_sessions),
            "observedTokens": sum(_session_usage_metrics(row)["observedTokens"] for row in recent_sessions),
            "toolReportedTokens": sum(_session_usage_metrics(row)["toolReportedTokens"] for row in recent_sessions),
            "contextSessionCount": len(context_rows),
            "avgContextUtilizationPct": avg_context_utilization_pct,
            "taskVelocity": int(latest.get("task_velocity", task_stats.get("completed", 0))),
            "taskCompletionPct": float(latest.get("task_completion_pct", task_stats.get("completion_pct", 0.0))),
            "featureProgress": float(latest.get("feature_progress", 0.0)),
            "toolCallCount": int(latest.get("tool_call_count", 0)),
            "toolSuccessRate": float(latest.get("tool_success_rate", 0.0)),
        },
        "topModels": top_models,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "range": {"start": start or "", "end": end or ""},
    }


@analytics_router.get("/series")
async def get_series(
    metric: str = Query(..., description="Metric type ID"),
    period: str = Query("daily", pattern="^(point|hourly|daily|weekly)$"),
    start: str | None = None,
    end: str | None = None,
    group_by: str | None = None,
    session_id: str | None = None,
    offset: int = 0,
    limit: int = 500,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    analytics_repo = get_analytics_repository(db)

    if metric == "session_tokens" and session_id:
        logs = await session_repo.get_logs(session_id)
        points: list[dict[str, Any]] = []
        cumulative = 0
        for log in logs:
            metadata = _safe_json(log.get("metadata_json"))
            in_tokens = int(metadata.get("inputTokens") or 0)
            out_tokens = int(metadata.get("outputTokens") or 0)
            cache_creation_tokens = int(metadata.get("cacheCreationInputTokens") or 0)
            cache_read_tokens = int(metadata.get("cacheReadInputTokens") or 0)
            delta = max(0, in_tokens + out_tokens + cache_creation_tokens + cache_read_tokens)
            if delta == 0:
                continue
            cumulative += delta
            points.append({
                "captured_at": log.get("timestamp") or "",
                "value": cumulative,
                "metadata": {
                    "stepTokens": delta,
                    "inputTokens": in_tokens,
                    "outputTokens": out_tokens,
                    "cacheInputTokens": cache_creation_tokens + cache_read_tokens,
                    "observedTokens": delta,
                    "agent": log.get("agent_name") or "",
                },
            })
        return {"items": points[offset:offset + limit], "total": len(points), "offset": offset, "limit": limit}

    if metric == "session_tokens":
        filters: dict[str, Any] = {"include_subagents": True}
        if start:
            filters["start_date"] = start
        if end:
            filters["end_date"] = end
        sessions = await session_repo.list_paginated(0, 2000, project.id, "started_at", "desc", filters)
        if period == "point" and not group_by:
            items: list[dict[str, Any]] = []
            for row in sessions:
                ts = str(row.get("started_at") or "")
                if not ts:
                    continue
                usage = _session_usage_metrics(row)
                items.append(
                    {
                        "captured_at": ts,
                        "value": usage["observedTokens"],
                        "metadata": {
                            "sessionId": str(row.get("id") or ""),
                            "modelIOTokens": usage["modelIOTokens"],
                            "cacheInputTokens": usage["cacheInputTokens"],
                            "observedTokens": usage["observedTokens"],
                            "toolReportedTokens": usage["toolReportedTokens"],
                        },
                    }
                )
            items.sort(key=lambda row: str(row.get("captured_at") or ""))
            total = len(items)
            return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}

        aggregates: dict[tuple[str, str], dict[str, Any]] = {}
        for row in sessions:
            ts = _parse_iso(str(row.get("started_at") or ""))
            if not ts:
                continue
            bucket = _bucket_ts(ts, period)
            if group_by == "model":
                group_value = canonical_model_name(str(row.get("model") or "").strip()) or "unknown"
            elif group_by == "model_family":
                group_value = model_family_name(str(row.get("model") or "").strip()) or "Unknown"
            elif group_by == "session_type":
                group_value = str(row.get("session_type") or "session")
            else:
                group_value = "all"
            key = (bucket, group_value)
            current = aggregates.setdefault(
                key,
                {
                    "captured_at": bucket,
                    "group": group_value,
                    "observedTokens": 0,
                    "modelIOTokens": 0,
                    "cacheInputTokens": 0,
                    "toolReportedTokens": 0,
                },
            )
            usage = _session_usage_metrics(row)
            current["observedTokens"] += usage["observedTokens"]
            current["modelIOTokens"] += usage["modelIOTokens"]
            current["cacheInputTokens"] += usage["cacheInputTokens"]
            current["toolReportedTokens"] += usage["toolReportedTokens"]

        items = []
        for row in aggregates.values():
            payload = {
                "captured_at": row["captured_at"],
                "value": row["observedTokens"],
                "metadata": {
                    "modelIOTokens": row["modelIOTokens"],
                    "cacheInputTokens": row["cacheInputTokens"],
                    "observedTokens": row["observedTokens"],
                    "toolReportedTokens": row["toolReportedTokens"],
                },
            }
            if group_by:
                payload["metadata"][group_by] = row["group"]
            items.append(payload)
        items.sort(key=lambda row: str(row.get("captured_at") or ""))
        total = len(items)
        return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}

    raw_points = await analytics_repo.get_trends(project.id, metric, period="point", start=start, end=end)
    if period == "point" and not group_by:
        total = len(raw_points)
        return {"items": raw_points[offset:offset + limit], "total": total, "offset": offset, "limit": limit}

    mode = _rollup_mode(metric)
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for point in raw_points:
        ts = _parse_iso(str(point.get("captured_at") or ""))
        if not ts:
            continue
        if start and ts < (_parse_iso(start) or ts):
            continue
        if end and ts > (_parse_iso(end) or ts):
            continue
        bucket = _bucket_ts(ts, period)
        metadata = _safe_json(point.get("metadata"))
        group_value = str(metadata.get(group_by or "") or "all") if group_by else "all"
        key = (bucket, group_value)
        current = aggregates.get(key)
        if not current:
            aggregates[key] = {
                "captured_at": bucket,
                "value_sum": 0.0,
                "value_count": 0,
                "group": group_value,
            }
            current = aggregates[key]
        current["value_sum"] += float(point.get("value") or 0.0)
        current["value_count"] += 1

    items: list[dict[str, Any]] = []
    for row in aggregates.values():
        value = row["value_sum"]
        if mode == "avg" and row["value_count"] > 0:
            value = value / row["value_count"]
        payload = {"captured_at": row["captured_at"], "value": value}
        if group_by:
            payload["metadata"] = {group_by: row["group"]}
        items.append(payload)
    items.sort(key=lambda row: str(row.get("captured_at") or ""))
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/breakdown")
async def get_breakdown(
    dimension: str = Query("model", pattern="^(model|model_family|session_type|tool|agent|skill|feature)$"),
    start: str | None = None,
    end: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    link_repo = get_entity_link_repository(db)

    filters: dict[str, Any] = {"include_subagents": True}
    if start:
        filters["start_date"] = start
    if end:
        filters["end_date"] = end
    sessions = await session_repo.list_paginated(0, 2000, project.id, "started_at", "desc", filters)

    counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "tokens": 0,
            "tokenInput": 0,
            "tokenOutput": 0,
            "modelIOTokens": 0,
            "cacheInputTokens": 0,
            "observedTokens": 0,
            "toolReportedTokens": 0,
            "totalTokens": 0,
            "cost": 0.0,
        }
    )
    counted_usage_pairs: set[tuple[str, str]] = set()

    def add_usage(key: str, row: dict[str, Any]) -> None:
        session_id = str(row.get("id") or "")
        if not key or not session_id or (key, session_id) in counted_usage_pairs:
            return
        counted_usage_pairs.add((key, session_id))
        usage = _session_usage_metrics(row)
        counts[key]["tokens"] += int(usage["observedTokens"])
        counts[key]["tokenInput"] += int(usage["tokenInput"])
        counts[key]["tokenOutput"] += int(usage["tokenOutput"])
        counts[key]["modelIOTokens"] += int(usage["modelIOTokens"])
        counts[key]["cacheInputTokens"] += int(usage["cacheInputTokens"])
        counts[key]["observedTokens"] += int(usage["observedTokens"])
        counts[key]["toolReportedTokens"] += int(usage["toolReportedTokens"])
        counts[key]["totalTokens"] += int(usage["totalTokens"])
        counts[key]["cost"] += float(row.get("total_cost") or 0.0)

    if dimension in {"model", "model_family", "session_type"}:
        for row in sessions:
            if dimension == "model":
                key = canonical_model_name(str(row.get("model") or "").strip()) or "unknown"
            elif dimension == "session_type":
                key = str(row.get("session_type") or "session")
            else:
                key = model_family_name(str(row.get("model") or "").strip()) or "Unknown"
            counts[key]["count"] += 1
            add_usage(key, row)
    elif dimension == "tool":
        for row in sessions:
            tools = await session_repo.get_tool_usage(str(row.get("id") or ""))
            for tool in tools:
                key = str(tool.get("tool_name") or "unknown")
                counts[key]["count"] += int(tool.get("call_count") or 0)
                add_usage(key, row)
    elif dimension in {"agent", "skill"}:
        for row in sessions:
            logs = await session_repo.get_logs(str(row.get("id") or ""))
            for log in logs:
                if dimension == "agent":
                    key = str(log.get("agent_name") or "").strip()
                    if not key:
                        continue
                    counts[key]["count"] += 1
                    add_usage(key, row)
                else:
                    metadata = _safe_json(log.get("metadata_json"))
                    if str(log.get("tool_name") or "") == "Skill":
                        key = str(metadata.get("toolLabel") or metadata.get("skill") or "").strip()
                        if key:
                            counts[key]["count"] += 1
                            add_usage(key, row)
    else:
        # feature correlation count via feature -> session links
        for row in sessions:
            session_id = str(row.get("id") or "")
            if not session_id:
                continue
            links = await link_repo.get_links_for("session", session_id, "related")
            for link in links:
                if link.get("source_type") != "feature":
                    continue
                feature_id = str(link.get("source_id") or "").strip()
                if not feature_id:
                    continue
                counts[feature_id]["count"] += 1
                add_usage(feature_id, row)

    items = [
        {"name": name, **values}
        for name, values in sorted(counts.items(), key=lambda item: item[1]["count"], reverse=True)
    ]
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/correlation")
async def get_correlation(
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    link_repo = get_entity_link_repository(db)
    feature_repo = get_feature_repository(db)

    sessions = await session_repo.list_paginated(0, 1200, project.id, "started_at", "desc", {"include_subagents": True})
    items: list[dict[str, Any]] = []
    for row in sessions:
        session_id = str(row.get("id") or "")
        if not session_id:
            continue
        links = await link_repo.get_links_for("session", session_id, "related")
        feature_links = [link for link in links if link.get("source_type") == "feature"]
        model_dims = _model_dimensions(row.get("model"))
        session_type = str(row.get("session_type") or "")
        usage = _session_usage_metrics(row)
        context = _session_context_metrics(row)
        cost = _session_cost_metrics(row)
        model_identity = derive_model_identity(row.get("model"))
        base_payload = {
            "sessionId": session_id,
            "commitHash": row.get("git_commit_hash") or "",
            "model": model_dims["canonical"],
            "modelRaw": model_dims["raw"],
            "modelFamily": model_dims["family"],
            "modelVersion": model_identity["modelVersion"],
            "status": row.get("status") or "",
            "startedAt": row.get("started_at") or "",
            "endedAt": row.get("ended_at") or "",
            "rootSessionId": row.get("root_session_id") or "",
            "parentSessionId": row.get("parent_session_id") or "",
            "sessionType": session_type or "",
            "platformVersion": str(row.get("platform_version") or ""),
            "durationSeconds": int(row.get("duration_seconds") or 0),
            **usage,
            **context,
            **cost,
            "totalCost": float(cost["displayCostUsd"] if cost["displayCostUsd"] is not None else row.get("total_cost") or 0.0),
            "linkedFeatureCount": len(feature_links),
            "isSubagent": session_type == "subagent",
        }
        if not feature_links:
            items.append({
                **base_payload,
                "featureId": "",
                "featureName": "",
                "confidence": 0.0,
                "linkStrategy": "",
            })
            continue
        for link in feature_links:
            feature_id = str(link.get("source_id") or "")
            feature_row = await feature_repo.get_by_id(feature_id)
            metadata = _safe_json(link.get("metadata_json"))
            items.append({
                **base_payload,
                "featureId": feature_id,
                "featureName": (feature_row or {}).get("name", ""),
                "confidence": float(link.get("confidence") or 0.0),
                "linkStrategy": metadata.get("linkStrategy") or "",
            })

    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/session-cost-calibration", response_model=SessionCostCalibrationSummary)
async def get_session_cost_calibration(
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    project = project_manager.get_active_project()
    if not project:
        return SessionCostCalibrationSummary(generatedAt=datetime.now(timezone.utc).isoformat())

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    filters: dict[str, Any] = {"include_subagents": True}
    if start:
        filters["start_date"] = start
    if end:
        filters["end_date"] = end
    sessions = await session_repo.list_paginated(0, 2000, project.id, "started_at", "desc", filters)

    provenance_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "displayCostUsd": 0.0})
    mismatch_band_counts: dict[str, int] = defaultdict(int)
    comparable_rows: list[dict[str, Any]] = []
    total_display_cost = 0.0
    total_reported_cost = 0.0
    total_recalculated_cost = 0.0
    confidence_sum = 0.0
    reported_session_count = 0
    recalculated_session_count = 0
    mismatch_session_count = 0
    max_mismatch_pct = 0.0

    for row in sessions:
        cost = _session_cost_metrics(row)
        confidence_sum += _coerce_float(cost["costConfidence"])
        provenance = str(cost["costProvenance"] or "unknown")
        provenance_counts[provenance]["count"] += 1
        provenance_counts[provenance]["displayCostUsd"] += _coerce_float(cost["displayCostUsd"])
        if cost["displayCostUsd"] is not None:
            total_display_cost += float(cost["displayCostUsd"])
        if cost["reportedCostUsd"] is not None:
            reported_session_count += 1
            total_reported_cost += float(cost["reportedCostUsd"])
        if cost["recalculatedCostUsd"] is not None:
            recalculated_session_count += 1
            total_recalculated_cost += float(cost["recalculatedCostUsd"])
        if cost["reportedCostUsd"] is not None and cost["recalculatedCostUsd"] is not None and cost["costMismatchPct"] is not None:
            comparable_rows.append(row)
            mismatch_session_count += 1
            mismatch_value = float(cost["costMismatchPct"])
            max_mismatch_pct = max(max_mismatch_pct, mismatch_value)
            mismatch_band_counts[_cost_mismatch_band(mismatch_value)] += 1
        else:
            mismatch_band_counts[_cost_mismatch_band(None)] += 1

    session_count = len(sessions)
    comparable_session_count = len(comparable_rows)
    avg_cost_confidence = round(confidence_sum / max(session_count, 1), 4)
    avg_mismatch_pct = round(
        sum(_coerce_float(_session_cost_metrics(row)["costMismatchPct"]) for row in comparable_rows) / comparable_session_count,
        4,
    ) if comparable_session_count > 0 else 0.0

    return SessionCostCalibrationSummary(
        projectId=project.id,
        sessionCount=session_count,
        comparableSessionCount=comparable_session_count,
        reportedSessionCount=reported_session_count,
        recalculatedSessionCount=recalculated_session_count,
        mismatchSessionCount=mismatch_session_count,
        comparableCoveragePct=round(comparable_session_count / max(session_count, 1), 4),
        avgCostConfidence=avg_cost_confidence,
        avgMismatchPct=avg_mismatch_pct,
        maxMismatchPct=round(max_mismatch_pct, 4),
        totalDisplayCostUsd=round(total_display_cost, 4),
        totalReportedCostUsd=round(total_reported_cost, 4),
        totalRecalculatedCostUsd=round(total_recalculated_cost, 4),
        provenanceCounts=_serialize_provenance_counts(provenance_counts),
        mismatchBands=[
            SessionCostCalibrationMismatchBand(band=band, count=count)
            for band, count in sorted(mismatch_band_counts.items(), key=lambda item: item[0])
        ],
        byModel=_build_cost_calibration_groups(
            sessions,
            lambda row: canonical_model_name(str(row.get("model") or "").strip()) or "unknown",
        ),
        byModelVersion=_build_cost_calibration_groups(
            sessions,
            lambda row: derive_model_identity(str(row.get("model") or "")).get("modelVersion") or "unknown",
        ),
        byPlatformVersion=_build_cost_calibration_groups(
            sessions,
            lambda row: str(row.get("platform_version") or "unknown"),
        ),
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )


@analytics_router.get("/usage-attribution", response_model=SessionUsageAggregateResponse)
async def get_usage_attribution(
    start: str | None = Query(None),
    end: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project")
    require_usage_attribution_enabled(project)
    db = await connection.get_connection()
    payload = await get_usage_attribution_rollup(
        db,
        project_id=project.id,
        start=start,
        end=end,
        entity_type=entity_type,
        entity_id=entity_id,
        offset=offset,
        limit=limit,
    )
    return SessionUsageAggregateResponse(**payload)


@analytics_router.get("/usage-attribution/drilldown", response_model=SessionUsageDrilldownResponse)
async def get_usage_attribution_drilldown_view(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project")
    require_usage_attribution_enabled(project)
    db = await connection.get_connection()
    payload = await get_usage_attribution_drilldown(
        db,
        project_id=project.id,
        entity_type=entity_type,
        entity_id=entity_id,
        start=start,
        end=end,
        offset=offset,
        limit=limit,
    )
    return SessionUsageDrilldownResponse(**payload)


@analytics_router.get("/usage-attribution/calibration", response_model=SessionUsageCalibrationSummary)
async def get_usage_attribution_calibration_view(
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project")
    require_usage_attribution_enabled(project)
    db = await connection.get_connection()
    payload = await get_usage_attribution_calibration(
        db,
        project_id=project.id,
        start=start,
        end=end,
    )
    return SessionUsageCalibrationSummary(**payload)


@analytics_router.get("/artifacts")
async def get_artifacts(
    start: str | None = None,
    end: str | None = None,
    artifact_type: str | None = Query(None, description="Filter by artifact type"),
    model: str | None = Query(None, description="Filter by model"),
    model_family: str | None = Query(None, description="Filter by model family (e.g. Opus)"),
    tool: str | None = Query(None, description="Filter by source tool"),
    feature_id: str | None = Query(None, description="Filter by feature ID"),
    limit: int = Query(120, ge=10, le=500),
):
    """Artifact-centric analytics across all tracked sessions."""
    project = project_manager.get_active_project()
    if not project:
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "range": {"start": start or "", "end": end or ""},
            "totals": {},
            "byType": [],
            "bySource": [],
            "byTool": [],
            "bySession": [],
            "byFeature": [],
            "modelArtifact": [],
            "modelFamilies": [],
            "artifactTool": [],
            "modelArtifactTool": [],
            "commandModel": [],
            "agentModel": [],
            "tokenUsage": {
                "byArtifactType": [],
                "byModel": [],
                "byModelArtifact": [],
                "byModelFamily": [],
            },
            "detailLimit": limit,
        }

    db = await connection.get_connection()
    payload = await _load_artifact_analytics_payload(
        db,
        project_id=project.id,
        start=start,
        end=end,
        artifact_type=artifact_type,
        model=model,
        model_family=model_family,
        tool=tool,
        feature_filter=feature_id,
        detail_limit=limit,
    )
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["range"] = {"start": start or "", "end": end or ""}
    return payload


@analytics_router.get("/workflow-effectiveness", response_model=WorkflowEffectivenessResponse)
async def workflow_effectiveness(
    period: str = Query("all", pattern="^(all|daily|weekly)$"),
    scope_type: str | None = Query(
        None,
        alias="scopeType",
        pattern="^(workflow|effective_workflow|agent|skill|context_module|bundle|stack)$",
    ),
    scope_id: str | None = Query(None, alias="scopeId"),
    feature_id: str | None = Query(None, alias="featureId"),
    start: str | None = None,
    end: str | None = None,
    recompute: bool = False,
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return WorkflowEffectivenessResponse(
            projectId="",
            period=period,
            total=0,
            offset=offset,
            limit=limit,
            generatedAt=datetime.now(timezone.utc).isoformat(),
        )
    require_workflow_analytics_enabled(project)

    db = await connection.get_connection()
    payload = await get_workflow_effectiveness(
        db,
        project,
        period=period,
        scope_type=scope_type,
        scope_id=scope_id,
        feature_id=feature_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        recompute=recompute,
    )
    return WorkflowEffectivenessResponse(**payload)


@analytics_router.get("/failure-patterns", response_model=FailurePatternResponse)
async def failure_patterns(
    scope_type: str | None = Query(
        None,
        alias="scopeType",
        pattern="^(workflow|effective_workflow|agent|skill|context_module|bundle|stack)$",
    ),
    scope_id: str | None = Query(None, alias="scopeId"),
    feature_id: str | None = Query(None, alias="featureId"),
    start: str | None = None,
    end: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return FailurePatternResponse(
            projectId="",
            total=0,
            offset=offset,
            limit=limit,
            generatedAt=datetime.now(timezone.utc).isoformat(),
        )
    require_workflow_analytics_enabled(project)

    db = await connection.get_connection()
    payload = await detect_failure_patterns(
        db,
        project,
        scope_type=scope_type,
        scope_id=scope_id,
        feature_id=feature_id,
        start=start,
        end=end,
        offset=offset,
        limit=limit,
    )
    return FailurePatternResponse(**payload)


@analytics_router.get("/alerts", response_model=list[AlertConfig])
async def get_alerts():
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    configs = await repo.list_all(project.id if project else None)
    return [
        AlertConfig(
            id=c["id"],
            name=c["name"],
            metric=c["metric"],
            operator=c["operator"],
            threshold=c["threshold"],
            isActive=bool(c["is_active"]),
            scope=c["scope"],
        )
        for c in configs
    ]


@analytics_router.post("/alerts", response_model=AlertConfig)
async def create_alert(payload: AlertConfigCreate):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    alert_id = payload.id or f"alert-{uuid.uuid4().hex[:8]}"
    data = {
        "id": alert_id,
        "project_id": project.id if project else None,
        "name": payload.name,
        "metric": payload.metric,
        "operator": payload.operator,
        "threshold": payload.threshold,
        "is_active": payload.isActive,
        "scope": payload.scope,
    }
    await repo.upsert(data)
    return AlertConfig(
        id=alert_id,
        name=payload.name,
        metric=payload.metric,
        operator=payload.operator,
        threshold=payload.threshold,
        isActive=payload.isActive,
        scope=payload.scope,
    )


@analytics_router.patch("/alerts/{alert_id}", response_model=AlertConfig)
async def update_alert(alert_id: str, payload: AlertConfigPatch):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    configs = await repo.list_all(project.id if project else None)
    current = next((c for c in configs if c.get("id") == alert_id), None)
    if not current:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    merged = {
        "id": alert_id,
        "project_id": current.get("project_id"),
        "name": payload.name if payload.name is not None else current.get("name", ""),
        "metric": payload.metric if payload.metric is not None else current.get("metric", ""),
        "operator": payload.operator if payload.operator is not None else current.get("operator", ">"),
        "threshold": payload.threshold if payload.threshold is not None else float(current.get("threshold") or 0.0),
        "is_active": payload.isActive if payload.isActive is not None else bool(current.get("is_active")),
        "scope": payload.scope if payload.scope is not None else current.get("scope", "session"),
    }
    await repo.upsert(merged)
    return AlertConfig(
        id=alert_id,
        name=str(merged["name"]),
        metric=str(merged["metric"]),
        operator=str(merged["operator"]),
        threshold=float(merged["threshold"]),
        isActive=bool(merged["is_active"]),
        scope=str(merged["scope"]),
    )


@analytics_router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    await repo.delete(alert_id)
    return {"status": "ok", "id": alert_id}


@analytics_router.get("/notifications", response_model=list[Notification])
async def get_notifications(request: Request):
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    sessions = await repo.list_paginated(0, 5, project.id, sort_by="started_at", sort_order="desc")

    notifications: list[Notification] = []
    for s in sessions:
        notifications.append(Notification(
            id=f"session-{s['id']}",
            alertId="alert-cost",
            message=f"Session {s['id']}: Model={s['model']}, Cost=${s['total_cost']:.4f}",
            timestamp=s["started_at"] or "",
            isRead=True,
        ))

    sync_engine = getattr(request.app.state, "sync_engine", None)
    if sync_engine and hasattr(sync_engine, "list_operations"):
        try:
            operations = await sync_engine.list_operations(limit=50)
        except Exception:
            operations = []
        for op in operations:
            if str(op.get("projectId") or "") != project.id:
                continue
            status = str(op.get("status") or "").strip().lower()
            if status not in {"completed", "failed"}:
                continue
            kind = str(op.get("kind") or "").strip().lower()
            label = _operation_kind_label(kind)
            stats = op.get("stats", {}) if isinstance(op.get("stats"), dict) else {}
            finished_at = str(op.get("finishedAt") or op.get("updatedAt") or op.get("startedAt") or "")
            if status == "failed":
                error = str(op.get("error") or "").strip()
                message = f"{label} failed{f': {error}' if error else ''}"
            else:
                mappings_stored = int(stats.get("mappings_stored") or stats.get("mappingsStored") or 0)
                runs_processed = int(stats.get("runs_processed") or stats.get("runsProcessed") or 0)
                if kind == "test_mapping_backfill":
                    message = f"{label} completed: {runs_processed} runs, {mappings_stored} mappings stored."
                else:
                    message = f"{label} completed."
            notifications.append(Notification(
                id=f"op-{op.get('id')}",
                alertId=f"op-{kind or 'generic'}",
                message=message,
                timestamp=finished_at,
                isRead=False,
            ))

    def _notif_sort_key(item: Notification) -> float:
        parsed = _parse_iso(item.timestamp)
        if parsed is None:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    notifications.sort(key=_notif_sort_key, reverse=True)
    for idx, item in enumerate(notifications):
        item.isRead = idx > 0
    return notifications[:20]


@analytics_router.get("/trends")
async def get_trends(
    metric: str = Query(..., description="Metric type ID"),
    period: str = "daily",
    start: str | None = None,
    end: str | None = None,
):
    """Legacy trends endpoint."""
    payload = await get_series(metric=metric, period=period, start=start, end=end, group_by=None, session_id=None, offset=0, limit=500)
    return payload["items"]


@analytics_router.get("/export/prometheus")
async def export_prometheus():
    project = project_manager.get_active_project()
    if not project:
        return Response("", media_type="text/plain")

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    types = [
        "session_cost", "session_tokens", "session_count",
        "task_velocity", "task_completion_pct", "tool_call_count", "tool_success_rate",
    ]
    latest = await repo.get_latest_entries(project.id, types)

    lines: list[str] = []
    for metric, value in latest.items():
        safe_name = f"ccdash_{metric}"
        lines.append(f"# TYPE {safe_name} gauge")
        lines.append(f'{safe_name}{{project="{_prom_label(project.id)}"}} {value}')

    # Richer fallbacks from telemetry fact rows (labels by tool/model/status/event dimensions).
    tool_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    try:
        if isinstance(db, aiosqlite.Connection):
            async with db.execute(
                """
                SELECT
                    tool_name,
                    status,
                    SUM(CAST(COALESCE(json_extract(payload_json, '$.callCount'), 0) AS INTEGER)) AS calls,
                    AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
                FROM telemetry_events
                WHERE project_id = ? AND event_type = 'tool.aggregate'
                GROUP BY tool_name, status
                ORDER BY calls DESC
                """,
                (project.id,),
            ) as cur:
                tool_rows = [dict(row) for row in await cur.fetchall()]

            async with db.execute(
                """
                SELECT
                    model,
                    SUM(COALESCE(token_input, 0)) AS input_tokens,
                    SUM(COALESCE(token_output, 0)) AS output_tokens,
                    SUM(COALESCE(cost_usd, 0)) AS total_cost
                FROM telemetry_events
                WHERE project_id = ? AND event_type = 'session.lifecycle'
                GROUP BY model
                ORDER BY (input_tokens + output_tokens) DESC
                """,
                (project.id,),
            ) as cur:
                model_rows = [dict(row) for row in await cur.fetchall()]

            async with db.execute(
                """
                SELECT
                    event_type,
                    status,
                    tool_name,
                    model,
                    agent,
                    skill,
                    phase,
                    source,
                    COUNT(*) AS event_count
                FROM telemetry_events
                WHERE project_id = ?
                GROUP BY event_type, status, tool_name, model, agent, skill, phase, source
                ORDER BY event_count DESC
                """,
                (project.id,),
            ) as cur:
                event_rows = [dict(row) for row in await cur.fetchall()]
        else:
            tool_rows = [
                dict(row)
                for row in await db.fetch(
                    """
                    SELECT
                        tool_name,
                        status,
                        SUM(COALESCE((payload_json::jsonb->>'callCount')::INTEGER, 0)) AS calls,
                        AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
                    FROM telemetry_events
                    WHERE project_id = $1 AND event_type = 'tool.aggregate'
                    GROUP BY tool_name, status
                    ORDER BY calls DESC
                    """,
                    project.id,
                )
            ]
            model_rows = [
                dict(row)
                for row in await db.fetch(
                    """
                    SELECT
                        model,
                        SUM(COALESCE(token_input, 0)) AS input_tokens,
                        SUM(COALESCE(token_output, 0)) AS output_tokens,
                        SUM(COALESCE(cost_usd, 0)) AS total_cost
                    FROM telemetry_events
                    WHERE project_id = $1 AND event_type = 'session.lifecycle'
                    GROUP BY model
                    ORDER BY (SUM(COALESCE(token_input, 0)) + SUM(COALESCE(token_output, 0))) DESC
                    """,
                    project.id,
                )
            ]
            event_rows = [
                dict(row)
                for row in await db.fetch(
                    """
                    SELECT
                        event_type,
                        status,
                        tool_name,
                        model,
                        agent,
                        skill,
                        phase,
                        source,
                        COUNT(*) AS event_count
                    FROM telemetry_events
                    WHERE project_id = $1
                    GROUP BY event_type, status, tool_name, model, agent, skill, phase, source
                    ORDER BY event_count DESC
                    """,
                    project.id,
                )
            ]
    except Exception:
        tool_rows = []
        model_rows = []
        event_rows = []

    if model_rows:
        canonical_model_rows: dict[str, dict[str, Any]] = {}
        for row in model_rows:
            dims = _model_dimensions(row.get("model"))
            key = dims["canonical"]
            current = canonical_model_rows.setdefault(
                key,
                {
                    "model": key,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost": 0.0,
                },
            )
            current["input_tokens"] += _coerce_int(row.get("input_tokens"))
            current["output_tokens"] += _coerce_int(row.get("output_tokens"))
            current["total_cost"] += _coerce_float(row.get("total_cost"))
        model_rows = sorted(
            list(canonical_model_rows.values()),
            key=lambda row: (_coerce_int(row.get("input_tokens")) + _coerce_int(row.get("output_tokens"))),
            reverse=True,
        )

    if tool_rows:
        lines.append("# TYPE ccdash_tool_calls_total counter")
        lines.append("# TYPE ccdash_tool_duration_ms gauge")
    for row in tool_rows:
        tool_name = _prom_label(row.get("tool_name") or "unknown")
        status = _prom_label(row.get("status") or "unknown")
        calls = int(row.get("calls") or 0)
        avg_duration = float(row.get("avg_duration_ms") or 0.0)
        lines.append(
            f'ccdash_tool_calls_total{{project="{_prom_label(project.id)}",tool="{tool_name}",status="{status}"}} {calls}'
        )
        lines.append(
            f'ccdash_tool_duration_ms{{project="{_prom_label(project.id)}",tool="{tool_name}"}} {avg_duration}'
        )

    if model_rows:
        lines.append("# TYPE ccdash_tokens_total counter")
        lines.append("# TYPE ccdash_cost_usd_total counter")
    for row in model_rows:
        model = _prom_label(row.get("model") or "unknown")
        input_tokens = int(row.get("input_tokens") or 0)
        output_tokens = int(row.get("output_tokens") or 0)
        total_cost = float(row.get("total_cost") or 0.0)
        lines.append(
            f'ccdash_tokens_total{{project="{_prom_label(project.id)}",model="{model}",direction="input"}} {input_tokens}'
        )
        lines.append(
            f'ccdash_tokens_total{{project="{_prom_label(project.id)}",model="{model}",direction="output"}} {output_tokens}'
        )
        lines.append(
            f'ccdash_cost_usd_total{{project="{_prom_label(project.id)}",model="{model}"}} {total_cost}'
        )

    if event_rows:
        lines.append("# TYPE ccdash_telemetry_events_total counter")
    for row in event_rows:
        event_type = _prom_label(row.get("event_type") or "unknown")
        status = _prom_label(row.get("status") or "unknown")
        tool_name = _prom_label(row.get("tool_name") or "unknown")
        model = _prom_label(row.get("model") or "unknown")
        agent = _prom_label(row.get("agent") or "unknown")
        skill = _prom_label(row.get("skill") or "unknown")
        phase = _prom_label(row.get("phase") or "unknown")
        source = _prom_label(row.get("source") or "unknown")
        count = int(row.get("event_count") or 0)
        lines.append(
            f'ccdash_telemetry_events_total{{project="{_prom_label(project.id)}",event_type="{event_type}",status="{status}",tool="{tool_name}",model="{model}",agent="{agent}",skill="{skill}",phase="{phase}",source="{source}"}} {count}'
        )

    artifact_payload: dict[str, Any] = {}
    try:
        artifact_payload = await _load_artifact_analytics_payload(
            db,
            project_id=project.id,
            start=None,
            end=None,
            artifact_type=None,
            model=None,
            model_family=None,
            tool=None,
            feature_filter=None,
            detail_limit=200,
        )
    except Exception:
        artifact_payload = {}

    artifact_totals = artifact_payload.get("totals") if isinstance(artifact_payload, dict) else {}
    if isinstance(artifact_totals, dict):
        lines.append("# TYPE ccdash_artifacts_total gauge")
        lines.append("# TYPE ccdash_artifact_types_total gauge")
        lines.append("# TYPE ccdash_artifact_sessions_total gauge")
        lines.append("# TYPE ccdash_artifact_features_total gauge")
        lines.append("# TYPE ccdash_artifact_models_total gauge")
        lines.append("# TYPE ccdash_artifact_tools_total gauge")
        lines.append("# TYPE ccdash_artifact_sources_total gauge")
        lines.append(
            f'ccdash_artifacts_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("artifactCount"))}'
        )
        lines.append(
            f'ccdash_artifact_types_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("artifactTypes"))}'
        )
        lines.append(
            f'ccdash_artifact_sessions_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("sessions"))}'
        )
        lines.append(
            f'ccdash_artifact_features_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("features"))}'
        )
        lines.append(
            f'ccdash_artifact_models_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("models"))}'
        )
        lines.append(
            f'ccdash_artifact_tools_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("tools"))}'
        )
        lines.append(
            f'ccdash_artifact_sources_total{{project="{_prom_label(project.id)}"}} {_coerce_int(artifact_totals.get("sources"))}'
        )
        kind_totals = artifact_totals.get("kindTotals", {})
        if isinstance(kind_totals, dict):
            lines.append("# TYPE ccdash_artifact_kind_total gauge")
            for kind, count in kind_totals.items():
                lines.append(
                    f'ccdash_artifact_kind_total{{project="{_prom_label(project.id)}",kind="{_prom_label(kind)}"}} {_coerce_int(count)}'
                )

    by_type_rows = artifact_payload.get("byType", []) if isinstance(artifact_payload, dict) else []
    if isinstance(by_type_rows, list) and by_type_rows:
        lines.append("# TYPE ccdash_artifact_events_total gauge")
        lines.append("# TYPE ccdash_artifact_session_coverage_total gauge")
        lines.append("# TYPE ccdash_artifact_feature_coverage_total gauge")
        lines.append("# TYPE ccdash_artifact_tokens_total gauge")
        lines.append("# TYPE ccdash_artifact_cost_usd_total gauge")
        for row in by_type_rows:
            artifact_type = _prom_label(row.get("artifactType") or "unknown")
            lines.append(
                f'ccdash_artifact_events_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}"}} {_coerce_int(row.get("count"))}'
            )
            lines.append(
                f'ccdash_artifact_session_coverage_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}"}} {_coerce_int(row.get("sessions"))}'
            )
            lines.append(
                f'ccdash_artifact_feature_coverage_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}"}} {_coerce_int(row.get("features"))}'
            )
            lines.append(
                f'ccdash_artifact_tokens_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_artifact_tokens_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_artifact_cost_usd_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}"}} {_coerce_float(row.get("totalCost"))}'
            )

    model_artifact_rows = artifact_payload.get("modelArtifact", []) if isinstance(artifact_payload, dict) else []
    if isinstance(model_artifact_rows, list) and model_artifact_rows:
        lines.append("# TYPE ccdash_model_artifact_events_total gauge")
        lines.append("# TYPE ccdash_model_artifact_tokens_total gauge")
        lines.append("# TYPE ccdash_model_artifact_cost_usd_total gauge")
        for row in model_artifact_rows:
            artifact_type = _prom_label(row.get("artifactType") or "unknown")
            model_name = _prom_label(row.get("model") or "unknown")
            lines.append(
                f'ccdash_model_artifact_events_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}"}} {_coerce_int(row.get("count"))}'
            )
            lines.append(
                f'ccdash_model_artifact_tokens_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_model_artifact_tokens_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_model_artifact_cost_usd_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}"}} {_coerce_float(row.get("totalCost"))}'
            )

    artifact_tool_rows = artifact_payload.get("artifactTool", []) if isinstance(artifact_payload, dict) else []
    if isinstance(artifact_tool_rows, list) and artifact_tool_rows:
        lines.append("# TYPE ccdash_artifact_tool_events_total gauge")
        for row in artifact_tool_rows:
            artifact_type = _prom_label(row.get("artifactType") or "unknown")
            tool_name = _prom_label(row.get("toolName") or "unknown")
            lines.append(
                f'ccdash_artifact_tool_events_total{{project="{_prom_label(project.id)}",artifact_type="{artifact_type}",tool="{tool_name}"}} {_coerce_int(row.get("count"))}'
            )

    model_artifact_tool_rows = artifact_payload.get("modelArtifactTool", []) if isinstance(artifact_payload, dict) else []
    if isinstance(model_artifact_tool_rows, list) and model_artifact_tool_rows:
        lines.append("# TYPE ccdash_model_artifact_tool_events_total gauge")
        lines.append("# TYPE ccdash_model_artifact_tool_tokens_total gauge")
        lines.append("# TYPE ccdash_model_artifact_tool_cost_usd_total gauge")
        for row in model_artifact_tool_rows:
            model_name = _prom_label(row.get("model") or "unknown")
            artifact_type = _prom_label(row.get("artifactType") or "unknown")
            tool_name = _prom_label(row.get("toolName") or "unknown")
            lines.append(
                f'ccdash_model_artifact_tool_events_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",tool="{tool_name}"}} {_coerce_int(row.get("count"))}'
            )
            lines.append(
                f'ccdash_model_artifact_tool_tokens_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",tool="{tool_name}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_model_artifact_tool_tokens_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",tool="{tool_name}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_model_artifact_tool_cost_usd_total{{project="{_prom_label(project.id)}",model="{model_name}",artifact_type="{artifact_type}",tool="{tool_name}"}} {_coerce_float(row.get("totalCost"))}'
            )

    model_family_rows = artifact_payload.get("modelFamilies", []) if isinstance(artifact_payload, dict) else []
    if isinstance(model_family_rows, list) and model_family_rows:
        lines.append("# TYPE ccdash_model_family_artifact_events_total gauge")
        lines.append("# TYPE ccdash_model_family_artifact_tokens_total gauge")
        lines.append("# TYPE ccdash_model_family_artifact_cost_usd_total gauge")
        for row in model_family_rows:
            family = _prom_label(row.get("modelFamily") or "unknown")
            lines.append(
                f'ccdash_model_family_artifact_events_total{{project="{_prom_label(project.id)}",model_family="{family}"}} {_coerce_int(row.get("artifactCount"))}'
            )
            lines.append(
                f'ccdash_model_family_artifact_tokens_total{{project="{_prom_label(project.id)}",model_family="{family}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_model_family_artifact_tokens_total{{project="{_prom_label(project.id)}",model_family="{family}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_model_family_artifact_cost_usd_total{{project="{_prom_label(project.id)}",model_family="{family}"}} {_coerce_float(row.get("totalCost"))}'
            )

    command_model_rows = artifact_payload.get("commandModel", []) if isinstance(artifact_payload, dict) else []
    if isinstance(command_model_rows, list) and command_model_rows:
        lines.append("# TYPE ccdash_command_model_events_total gauge")
        lines.append("# TYPE ccdash_command_model_tokens_total gauge")
        lines.append("# TYPE ccdash_command_model_cost_usd_total gauge")
        for row in command_model_rows:
            command_name = _prom_label(row.get("command") or "unknown")
            model_name = _prom_label(row.get("model") or "unknown")
            family = _prom_label(row.get("modelFamily") or "unknown")
            lines.append(
                f'ccdash_command_model_events_total{{project="{_prom_label(project.id)}",command="{command_name}",model="{model_name}",model_family="{family}"}} {_coerce_int(row.get("count"))}'
            )
            lines.append(
                f'ccdash_command_model_tokens_total{{project="{_prom_label(project.id)}",command="{command_name}",model="{model_name}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_command_model_tokens_total{{project="{_prom_label(project.id)}",command="{command_name}",model="{model_name}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_command_model_cost_usd_total{{project="{_prom_label(project.id)}",command="{command_name}",model="{model_name}"}} {_coerce_float(row.get("totalCost"))}'
            )

    agent_model_rows = artifact_payload.get("agentModel", []) if isinstance(artifact_payload, dict) else []
    if isinstance(agent_model_rows, list) and agent_model_rows:
        lines.append("# TYPE ccdash_agent_model_events_total gauge")
        lines.append("# TYPE ccdash_agent_model_tokens_total gauge")
        lines.append("# TYPE ccdash_agent_model_cost_usd_total gauge")
        for row in agent_model_rows:
            agent_name = _prom_label(row.get("agent") or "unknown")
            model_name = _prom_label(row.get("model") or "unknown")
            family = _prom_label(row.get("modelFamily") or "unknown")
            lines.append(
                f'ccdash_agent_model_events_total{{project="{_prom_label(project.id)}",agent="{agent_name}",model="{model_name}",model_family="{family}"}} {_coerce_int(row.get("count"))}'
            )
            lines.append(
                f'ccdash_agent_model_tokens_total{{project="{_prom_label(project.id)}",agent="{agent_name}",model="{model_name}",direction="input"}} {_coerce_int(row.get("tokenInput"))}'
            )
            lines.append(
                f'ccdash_agent_model_tokens_total{{project="{_prom_label(project.id)}",agent="{agent_name}",model="{model_name}",direction="output"}} {_coerce_int(row.get("tokenOutput"))}'
            )
            lines.append(
                f'ccdash_agent_model_cost_usd_total{{project="{_prom_label(project.id)}",agent="{agent_name}",model="{model_name}"}} {_coerce_float(row.get("totalCost"))}'
            )

    link_stats = {"avg_confidence": 0.0, "low_confidence": 0, "total_links": 0}
    thread_stats = {"avg_fanout": 0.0, "max_fanout": 0}
    try:
        if isinstance(db, aiosqlite.Connection):
            async with db.execute(
                """
                SELECT
                    AVG(confidence) AS avg_confidence,
                    SUM(CASE WHEN confidence < 0.6 THEN 1 ELSE 0 END) AS low_confidence,
                    COUNT(*) AS total_links
                FROM entity_links el
                JOIN features f ON f.id = el.source_id
                WHERE
                    el.source_type = 'feature'
                    AND el.target_type = 'session'
                    AND el.link_type = 'related'
                    AND f.project_id = ?
                """,
                (project.id,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    link_stats = {
                        "avg_confidence": float(row[0] or 0.0),
                        "low_confidence": int(row[1] or 0),
                        "total_links": int(row[2] or 0),
                    }
            async with db.execute(
                """
                SELECT
                    AVG(child_count) AS avg_fanout,
                    MAX(child_count) AS max_fanout
                FROM (
                    SELECT COUNT(*) AS child_count
                    FROM sessions
                    WHERE project_id = ?
                    GROUP BY root_session_id
                )
                """,
                (project.id,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    thread_stats = {
                        "avg_fanout": float(row[0] or 0.0),
                        "max_fanout": int(row[1] or 0),
                    }
        else:
            row = await db.fetchrow(
                """
                SELECT
                    AVG(confidence) AS avg_confidence,
                    SUM(CASE WHEN confidence < 0.6 THEN 1 ELSE 0 END) AS low_confidence,
                    COUNT(*) AS total_links
                FROM entity_links el
                JOIN features f ON f.id = el.source_id
                WHERE
                    el.source_type = 'feature'
                    AND el.target_type = 'session'
                    AND el.link_type = 'related'
                    AND f.project_id = $1
                """,
                project.id,
            )
            if row:
                link_stats = {
                    "avg_confidence": float(row["avg_confidence"] or 0.0),
                    "low_confidence": int(row["low_confidence"] or 0),
                    "total_links": int(row["total_links"] or 0),
                }
            row = await db.fetchrow(
                """
                SELECT
                    AVG(child_count) AS avg_fanout,
                    MAX(child_count) AS max_fanout
                FROM (
                    SELECT COUNT(*) AS child_count
                    FROM sessions
                    WHERE project_id = $1
                    GROUP BY root_session_id
                ) fanout
                """,
                project.id,
            )
            if row:
                thread_stats = {
                    "avg_fanout": float(row["avg_fanout"] or 0.0),
                    "max_fanout": int(row["max_fanout"] or 0),
                }
    except Exception:
        link_stats = {"avg_confidence": 0.0, "low_confidence": 0, "total_links": 0}
        thread_stats = {"avg_fanout": 0.0, "max_fanout": 0}

    lines.append("# TYPE ccdash_link_confidence_avg gauge")
    lines.append("# TYPE ccdash_unresolved_entity_links gauge")
    lines.append("# TYPE ccdash_session_thread_fanout_avg gauge")
    lines.append("# TYPE ccdash_session_thread_fanout_max gauge")
    lines.append(
        f'ccdash_link_confidence_avg{{project="{_prom_label(project.id)}",source_type="feature",target_type="session"}} {link_stats["avg_confidence"]}'
    )
    lines.append(
        f'ccdash_unresolved_entity_links{{project="{_prom_label(project.id)}"}} {link_stats["low_confidence"]}'
    )
    lines.append(
        f'ccdash_session_thread_fanout_avg{{project="{_prom_label(project.id)}"}} {thread_stats["avg_fanout"]}'
    )
    lines.append(
        f'ccdash_session_thread_fanout_max{{project="{_prom_label(project.id)}"}} {thread_stats["max_fanout"]}'
    )
    return Response("\n".join(lines) + "\n", media_type="text/plain")
