"""Analytics router for overview, rollups, correlation, and exports."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from backend.models import AnalyticsMetric, AlertConfig, Notification
from backend.model_identity import canonical_model_name, model_family_name
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

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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
            SELECT session_id, model, agent, occurred_at, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_sqlite)} AND TRIM(COALESCE(agent, '')) != ''
            ORDER BY occurred_at DESC
        """,
        sqlite_params=tuple(event_params_sqlite),
        postgres_query=f"""
            SELECT session_id, model, agent, occurred_at, payload_json
            FROM telemetry_events
            WHERE {" AND ".join(event_filters_pg)} AND TRIM(COALESCE(agent, '')) != ''
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

    if not records:
        return {
            "totals": {
                "artifactCount": 0,
                "artifactTypes": 0,
                "sessions": 0,
                "features": 0,
                "models": 0,
                "modelFamilies": 0,
                "tools": 0,
                "sources": 0,
                "agents": 0,
                "skills": 0,
                "commands": 0,
                "kindTotals": {
                    "agents": 0,
                    "skills": 0,
                    "commands": 0,
                    "manifests": 0,
                    "requests": 0,
                },
            },
            "byType": [],
            "bySource": [],
            "byTool": [],
            "bySession": [],
            "byFeature": [],
            "modelArtifact": [],
            "artifactTool": [],
            "modelArtifactTool": [],
            "modelFamilies": [],
            "commandModel": [],
            "agentModel": [],
            "tokenUsage": {
                "byArtifactType": [],
                "byModel": [],
                "byModelArtifact": [],
                "byModelFamily": [],
            },
            "detailLimit": detail_limit,
        }

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
        agent_name = str(row.get("agent") or "").strip()
        if not agent_name:
            continue
        entry = agent_model.setdefault(
            (agent_name, model_dims["canonical"]),
            {
                "agent": agent_name,
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
        agent_model_session_pairs.add((session_id, agent_name, model_dims["canonical"]))

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

    types = [
        "session_cost", "session_tokens", "session_count",
        "task_velocity", "task_completion_pct",
    ]
    latest = await repo.get_latest_entries(project.id, types)
    return [
        AnalyticsMetric(name="Total Cost", value=round(latest.get("session_cost", 0.0), 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=int(latest.get("session_tokens", 0)), unit="tokens"),
        AnalyticsMetric(name="Sessions", value=int(latest.get("session_count", 0)), unit="count"),
        AnalyticsMetric(name="Tasks Done", value=int(latest.get("task_velocity", 0)), unit="count"),
        AnalyticsMetric(name="Completion", value=round(latest.get("task_completion_pct", 0.0), 1), unit="%"),
    ]


@analytics_router.get("/overview")
async def get_overview(
    start: str | None = None,
    end: str | None = None,
):
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

    return {
        "kpis": {
            "sessionCost": float(latest.get("session_cost", 0.0)),
            "sessionTokens": int(latest.get("session_tokens", 0)),
            "sessionCount": int(latest.get("session_count", 0)),
            "sessionDurationAvg": float(latest.get("session_duration", 0.0)),
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
            delta = max(0, in_tokens + out_tokens)
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
                    "agent": log.get("agent_name") or "",
                },
            })
        return {"items": points[offset:offset + limit], "total": len(points), "offset": offset, "limit": limit}

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

    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "tokens": 0, "cost": 0.0})
    if dimension in {"model", "model_family", "session_type"}:
        for row in sessions:
            if dimension == "model":
                key = canonical_model_name(str(row.get("model") or "").strip()) or "unknown"
            elif dimension == "session_type":
                key = str(row.get("session_type") or "session")
            else:
                key = model_family_name(str(row.get("model") or "").strip()) or "Unknown"
            counts[key]["count"] += 1
            counts[key]["tokens"] += int(row.get("tokens_in") or 0) + int(row.get("tokens_out") or 0)
            counts[key]["cost"] += float(row.get("total_cost") or 0.0)
    elif dimension == "tool":
        for row in sessions:
            tools = await session_repo.get_tool_usage(str(row.get("id") or ""))
            for tool in tools:
                key = str(tool.get("tool_name") or "unknown")
                counts[key]["count"] += int(tool.get("call_count") or 0)
    elif dimension in {"agent", "skill"}:
        for row in sessions:
            logs = await session_repo.get_logs(str(row.get("id") or ""))
            for log in logs:
                if dimension == "agent":
                    key = str(log.get("agent_name") or "").strip()
                    if not key:
                        continue
                    counts[key]["count"] += 1
                else:
                    metadata = _safe_json(log.get("metadata_json"))
                    if str(log.get("tool_name") or "") == "Skill":
                        key = str(metadata.get("toolLabel") or metadata.get("skill") or "").strip()
                        if key:
                            counts[key]["count"] += 1
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
        links = await link_repo.get_links_for("session", session_id, "related")
        feature_links = [link for link in links if link.get("source_type") == "feature"]
        if not feature_links:
            model_dims = _model_dimensions(row.get("model"))
            items.append({
                "sessionId": session_id,
                "featureId": "",
                "featureName": "",
                "confidence": 0.0,
                "commitHash": row.get("git_commit_hash") or "",
                "model": model_dims["canonical"],
                "modelRaw": model_dims["raw"],
                "modelFamily": model_dims["family"],
                "status": row.get("status") or "",
                "startedAt": row.get("started_at") or "",
                "endedAt": row.get("ended_at") or "",
            })
            continue
        for link in feature_links:
            feature_id = str(link.get("source_id") or "")
            feature_row = await feature_repo.get_by_id(feature_id)
            metadata = _safe_json(link.get("metadata_json"))
            model_dims = _model_dimensions(row.get("model"))
            items.append({
                "sessionId": session_id,
                "featureId": feature_id,
                "featureName": (feature_row or {}).get("name", ""),
                "confidence": float(link.get("confidence") or 0.0),
                "linkStrategy": metadata.get("linkStrategy") or "",
                "commitHash": row.get("git_commit_hash") or "",
                "model": model_dims["canonical"],
                "modelRaw": model_dims["raw"],
                "modelFamily": model_dims["family"],
                "status": row.get("status") or "",
                "startedAt": row.get("started_at") or "",
                "endedAt": row.get("ended_at") or "",
            })

    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


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
async def get_notifications():
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    sessions = await repo.list_paginated(0, 5, project.id, sort_by="started_at", sort_order="desc")

    notifications: list[Notification] = []
    for i, s in enumerate(sessions):
        notifications.append(Notification(
            id=f"notif-{s['id']}",
            alertId="alert-cost",
            message=f"Session {s['id']}: Model={s['model']}, Cost=${s['total_cost']:.4f}",
            timestamp=s["started_at"] or "",
            isRead=i > 0,
        ))
    return notifications


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
