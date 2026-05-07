"""Compute persisted artifact ranking rows from attribution and snapshot evidence."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from backend import config
from backend.db.factory import get_artifact_ranking_repository, get_artifact_snapshot_repository
from backend.models import SkillMeatArtifactSnapshot, SnapshotArtifact
from backend.services.artifact_recommendation_service import ArtifactRecommendationService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, value)), 4)


def _period_start(period: str, computed_at: datetime) -> str | None:
    if period.endswith("d") and period[:-1].isdigit():
        return _iso(computed_at - timedelta(days=int(period[:-1])))
    return None


def _collection_for_artifact(artifact: SnapshotArtifact | None, fallback: str | None) -> str:
    if artifact and artifact.collection_ids:
        return artifact.collection_ids[0]
    return fallback or ""


def _artifact_external_name(artifact: SnapshotArtifact) -> str:
    if ":" in artifact.external_id:
        return artifact.external_id.split(":", 1)[1]
    return artifact.display_name


def _snapshot_indexes(snapshot: SkillMeatArtifactSnapshot | None) -> dict[str, SnapshotArtifact]:
    indexes: dict[str, SnapshotArtifact] = {}
    if snapshot is None:
        return indexes
    for artifact in snapshot.artifacts:
        keys = {
            artifact.artifact_uuid,
            artifact.external_id,
            artifact.display_name,
            _artifact_external_name(artifact),
            artifact.content_hash,
        }
        for key in keys:
            if key:
                indexes[str(key)] = artifact
    return indexes


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


class ArtifactRankingService:
    """Aggregate attribution, effectiveness, identity, and snapshot state into rankings."""

    def __init__(self, *, min_sample_size: int | None = None) -> None:
        self.min_sample_size = min_sample_size or config.CCDASH_RANKING_MIN_SAMPLE_SIZE

    async def compute_rankings(
        self,
        db: Any,
        *,
        project_id: str,
        period: str = "30d",
        collection_id: str | None = None,
        user_scope: str = "all",
        computed_at: datetime | None = None,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        current_time = computed_at or _now()
        start = _period_start(period, current_time)
        snapshot_repo = get_artifact_snapshot_repository(db)
        ranking_repo = get_artifact_ranking_repository(db)
        snapshot = await snapshot_repo.get_latest_snapshot(project_id)
        snapshot_fetched_at = _iso(snapshot.freshness.fetched_at) if snapshot else ""
        identity_rows = await snapshot_repo.list_identity_mappings(project_id)
        identity_by_name = {str(row.get("ccdash_name") or ""): row for row in identity_rows}
        snapshot_by_key = _snapshot_indexes(snapshot)
        usage_rows = await self._load_usage_rows(db, project_id=project_id, start=start)
        effectiveness = await self._load_effectiveness(db, project_id=project_id, period=period)
        project_session_count = len(
            {str(row.get("session_id") or "") for row in usage_rows if str(row.get("session_id") or "")}
        )

        buckets = self._usage_buckets(usage_rows)
        if snapshot:
            for artifact in snapshot.artifacts:
                key = _artifact_external_name(artifact)
                buckets.setdefault(
                    key,
                    {
                        "artifact_type": artifact.definition_type,
                        "sessions": set(),
                        "workflows": set(),
                        "events": set(),
                        "exclusive_tokens": 0,
                        "supporting_tokens": 0,
                        "cost_usd": 0.0,
                        "confidence_total": 0.0,
                        "confidence_count": 0,
                        "last_observed_at": None,
                        "context_pressure_values": [],
                        "status_counts": defaultdict(int),
                        "workflow_buckets": {},
                    },
                )

        rows: list[dict[str, Any]] = []
        for artifact_id, bucket in buckets.items():
            snapshot_artifact = self._resolve_snapshot_artifact(artifact_id, bucket, snapshot_by_key, identity_by_name)
            identity = identity_by_name.get(artifact_id, {})
            rows.append(
                self._build_row(
                    project_id=project_id,
                    collection_id=collection_id,
                    user_scope=user_scope,
                    period=period,
                    artifact_id=artifact_id,
                    bucket=bucket,
                    snapshot_artifact=snapshot_artifact,
                    identity=identity,
                    snapshot_fetched_at=snapshot_fetched_at,
                    effectiveness=effectiveness,
                    computed_at=current_time,
                    project_session_count=project_session_count,
                    workflow_id="",
                )
            )
            for workflow_id, workflow_bucket in bucket["workflow_buckets"].items():
                rows.append(
                    self._build_row(
                        project_id=project_id,
                        collection_id=collection_id,
                        user_scope=user_scope,
                        period=period,
                        artifact_id=artifact_id,
                        bucket=workflow_bucket,
                        snapshot_artifact=snapshot_artifact,
                        identity=identity,
                        snapshot_fetched_at=snapshot_fetched_at,
                        effectiveness=effectiveness,
                        computed_at=current_time,
                        project_session_count=project_session_count,
                        workflow_id=workflow_id,
                    )
                )

        rows.sort(key=lambda item: (-item["exclusive_tokens"], -item["supporting_tokens"], item["artifact_id"], item["workflow_id"]))
        self._annotate_recommendation_types(rows, computed_at=current_time)
        if persist:
            await ranking_repo.replace_rankings(project_id, period, rows)
        return rows

    async def _load_usage_rows(self, db: Any, *, project_id: str, start: str | None) -> list[dict[str, Any]]:
        sqlite_filters = ["sue.project_id = ?"]
        sqlite_params: list[Any] = [project_id]
        postgres_filters = ["sue.project_id = $1"]
        postgres_params: list[Any] = [project_id]
        if start:
            sqlite_filters.append("sue.captured_at >= ?")
            sqlite_params.append(start)
            postgres_filters.append("sue.captured_at >= $2")
            postgres_params.append(start)
        sqlite_query = f"""
            SELECT
                sue.id AS event_id,
                sue.session_id,
                sue.captured_at,
                sue.delta_tokens,
                sue.cost_usd_model_io,
                sua.entity_type,
                sua.entity_id,
                sua.attribution_role,
                sua.confidence,
                COALESCE(s.status, '') AS session_status,
                COALESCE(s.quality_rating, 0) AS quality_rating,
                COALESCE(s.current_context_tokens, 0) AS current_context_tokens,
                COALESCE(s.context_window_size, 0) AS context_window_size,
                COALESCE(sso.workflow_ref, '') AS workflow_ref
            FROM session_usage_events sue
            JOIN session_usage_attributions sua ON sua.event_id = sue.id
            LEFT JOIN sessions s ON s.id = sue.session_id AND s.project_id = sue.project_id
            LEFT JOIN session_stack_observations sso ON sso.session_id = sue.session_id AND sso.project_id = sue.project_id
            WHERE {' AND '.join(sqlite_filters)}
              AND sua.entity_type IN ('artifact', 'skill', 'context_module', 'agent')
            ORDER BY sue.captured_at ASC, sue.id ASC
        """
        postgres_query = f"""
            SELECT
                sue.id AS event_id,
                sue.session_id,
                sue.captured_at,
                sue.delta_tokens,
                sue.cost_usd_model_io,
                sua.entity_type,
                sua.entity_id,
                sua.attribution_role,
                sua.confidence,
                COALESCE(s.status, '') AS session_status,
                COALESCE(s.quality_rating, 0) AS quality_rating,
                COALESCE(s.current_context_tokens, 0) AS current_context_tokens,
                COALESCE(s.context_window_size, 0) AS context_window_size,
                COALESCE(sso.workflow_ref, '') AS workflow_ref
            FROM session_usage_events sue
            JOIN session_usage_attributions sua ON sua.event_id = sue.id
            LEFT JOIN sessions s ON s.id = sue.session_id AND s.project_id = sue.project_id
            LEFT JOIN session_stack_observations sso ON sso.session_id = sue.session_id AND sso.project_id = sue.project_id
            WHERE {' AND '.join(postgres_filters)}
              AND sua.entity_type IN ('artifact', 'skill', 'context_module', 'agent')
            ORDER BY sue.captured_at ASC, sue.id ASC
        """
        return await _query_rows(
            db,
            sqlite_query=sqlite_query,
            sqlite_params=tuple(sqlite_params),
            postgres_query=postgres_query,
            postgres_params=tuple(postgres_params),
        )

    async def _load_effectiveness(self, db: Any, *, project_id: str, period: str) -> dict[str, dict[str, Any]]:
        rows = await _query_rows(
            db,
            sqlite_query="""
                SELECT scope_type, scope_id, metrics_json
                FROM effectiveness_rollups
                WHERE project_id = ? AND period = ?
            """,
            sqlite_params=(project_id, period),
            postgres_query="""
                SELECT scope_type, scope_id, metrics_json
                FROM effectiveness_rollups
                WHERE project_id = $1 AND period = $2
            """,
            postgres_params=(project_id, period),
        )
        return {
            str(row.get("scope_id") or ""): _safe_json(row.get("metrics_json"), {})
            for row in rows
            if str(row.get("scope_id") or "")
        }

    def _usage_buckets(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            artifact_id = str(row.get("entity_id") or "").strip()
            if not artifact_id:
                continue
            bucket = buckets.setdefault(
                artifact_id,
                {
                    "artifact_type": str(row.get("entity_type") or ""),
                    "sessions": set(),
                    "workflows": set(),
                    "events": set(),
                    "exclusive_tokens": 0,
                    "supporting_tokens": 0,
                    "cost_usd": 0.0,
                    "confidence_total": 0.0,
                    "confidence_count": 0,
                    "last_observed_at": None,
                    "context_pressure_values": [],
                    "status_counts": defaultdict(int),
                    "workflow_buckets": {},
                },
            )
            self._add_usage(bucket, row)
            workflow_id = str(row.get("workflow_ref") or "").strip()
            if workflow_id:
                workflow_bucket = bucket["workflow_buckets"].setdefault(
                    workflow_id,
                    {
                        "artifact_type": bucket["artifact_type"],
                        "sessions": set(),
                        "workflows": set(),
                        "events": set(),
                        "exclusive_tokens": 0,
                        "supporting_tokens": 0,
                        "cost_usd": 0.0,
                        "confidence_total": 0.0,
                        "confidence_count": 0,
                        "last_observed_at": None,
                        "context_pressure_values": [],
                        "status_counts": defaultdict(int),
                        "workflow_buckets": {},
                    },
                )
                self._add_usage(workflow_bucket, row)
        return buckets

    def _add_usage(self, bucket: dict[str, Any], row: dict[str, Any]) -> None:
        event_id = str(row.get("event_id") or "")
        session_id = str(row.get("session_id") or "")
        workflow_id = str(row.get("workflow_ref") or "").strip()
        captured_at = _parse_dt(row.get("captured_at"))
        role = str(row.get("attribution_role") or "")
        delta_tokens = _safe_int(row.get("delta_tokens"))
        confidence = _safe_float(row.get("confidence"))
        bucket["events"].add(event_id)
        bucket["sessions"].add(session_id)
        if workflow_id:
            bucket["workflows"].add(workflow_id)
        if role == "primary":
            bucket["exclusive_tokens"] += delta_tokens
            bucket["cost_usd"] += _safe_float(row.get("cost_usd_model_io"))
        elif role == "supporting":
            bucket["supporting_tokens"] += delta_tokens
        bucket["confidence_total"] += confidence
        bucket["confidence_count"] += 1
        if captured_at and (bucket["last_observed_at"] is None or captured_at > bucket["last_observed_at"]):
            bucket["last_observed_at"] = captured_at
        context_window = _safe_int(row.get("context_window_size"))
        current_context = _safe_int(row.get("current_context_tokens"))
        if context_window > 0 and current_context >= 0:
            bucket["context_pressure_values"].append(min(1.0, current_context / context_window))
        bucket["status_counts"][str(row.get("session_status") or "")] += 1

    def _resolve_snapshot_artifact(
        self,
        artifact_id: str,
        bucket: dict[str, Any],
        snapshot_by_key: dict[str, SnapshotArtifact],
        identity_by_name: dict[str, dict[str, Any]],
    ) -> SnapshotArtifact | None:
        if artifact_id in snapshot_by_key:
            return snapshot_by_key[artifact_id]
        identity = identity_by_name.get(artifact_id) or {}
        for key in (identity.get("skillmeat_uuid"), identity.get("content_hash")):
            if key and str(key) in snapshot_by_key:
                return snapshot_by_key[str(key)]
        return None

    def _build_row(
        self,
        *,
        project_id: str,
        collection_id: str | None,
        user_scope: str,
        period: str,
        artifact_id: str,
        bucket: dict[str, Any],
        snapshot_artifact: SnapshotArtifact | None,
        identity: dict[str, Any],
        snapshot_fetched_at: str,
        effectiveness: dict[str, dict[str, Any]],
        computed_at: datetime,
        project_session_count: int,
        workflow_id: str,
    ) -> dict[str, Any]:
        sample_size = len(bucket["sessions"])
        avg_confidence = None
        if bucket["confidence_count"]:
            avg_confidence = round(bucket["confidence_total"] / max(1, bucket["confidence_count"]), 4)
        confidence = avg_confidence if sample_size >= self.min_sample_size else None
        metrics = effectiveness.get(artifact_id) or effectiveness.get(str(snapshot_artifact.artifact_uuid if snapshot_artifact else "")) or {}
        context_values = bucket["context_pressure_values"]
        context_pressure = round(sum(context_values) / max(1, len(context_values)), 4) if context_values else None
        success_score = self._metric_score(metrics, "successScore", "success_score")
        efficiency_score = self._metric_score(metrics, "efficiencyScore", "efficiency_score")
        quality_score = self._metric_score(metrics, "qualityScore", "quality_score")
        risk_score = self._metric_score(metrics, "riskScore", "risk_score")
        if success_score is None and sample_size:
            completed = bucket["status_counts"].get("completed", 0) + bucket["status_counts"].get("done", 0) + bucket["status_counts"].get("succeeded", 0)
            success_score = _score(completed / max(1, sample_size))
        if efficiency_score is None and sample_size:
            efficiency_score = _score(1.0 / (1.0 + (bucket["exclusive_tokens"] / max(1, sample_size)) / 20000.0))
        if quality_score is None and success_score is not None:
            quality_score = success_score
        if risk_score is None and success_score is not None:
            risk_score = _score(1.0 - success_score)

        snapshot_payload = {}
        if snapshot_artifact:
            snapshot_payload = snapshot_artifact.model_dump(mode="json", by_alias=True)
        identity_confidence = identity.get("confidence")
        if identity_confidence is None and snapshot_artifact is not None:
            identity_confidence = 1.0
        return {
            "project_id": project_id,
            "collection_id": _collection_for_artifact(snapshot_artifact, collection_id),
            "user_scope": user_scope,
            "artifact_type": snapshot_artifact.definition_type if snapshot_artifact else str(bucket.get("artifact_type") or ""),
            "artifact_id": artifact_id,
            "artifact_uuid": snapshot_artifact.artifact_uuid if snapshot_artifact else str(identity.get("skillmeat_uuid") or ""),
            "version_id": snapshot_artifact.version_id if snapshot_artifact else "",
            "workflow_id": workflow_id,
            "period": period,
            "exclusive_tokens": int(bucket["exclusive_tokens"]),
            "supporting_tokens": int(bucket["supporting_tokens"]),
            "cost_usd": round(float(bucket["cost_usd"]), 6),
            "session_count": sample_size,
            "workflow_count": len(bucket["workflows"]),
            "last_observed_at": _iso(bucket["last_observed_at"]),
            "avg_confidence": avg_confidence,
            "confidence": confidence,
            "success_score": success_score,
            "efficiency_score": efficiency_score,
            "quality_score": quality_score,
            "risk_score": risk_score,
            "context_pressure": context_pressure,
            "sample_size": sample_size,
            "identity_confidence": _score(_safe_float(identity_confidence)) if identity_confidence is not None else None,
            "snapshot_fetched_at": snapshot_fetched_at,
            "recommendation_types_json": [],
            "evidence_json": {
                "eventCount": len(bucket["events"]),
                "projectSessionCount": project_session_count,
                "snapshot": snapshot_payload,
                "identity": identity,
            },
            "computed_at": _iso(computed_at),
        }

    def _metric_score(self, metrics: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            if key in metrics and metrics[key] is not None:
                return _score(_safe_float(metrics[key]))
        return None

    def _annotate_recommendation_types(self, rows: list[dict[str, Any]], *, computed_at: datetime) -> None:
        if not rows:
            return
        service = ArtifactRecommendationService(min_sample_size=self.min_sample_size)
        recommendations = service.generate_recommendations(rows, now=computed_at)
        by_artifact: dict[str, set[str]] = defaultdict(set)
        for recommendation in recommendations:
            for artifact_id in recommendation.affected_artifact_ids:
                if artifact_id:
                    by_artifact[artifact_id].add(recommendation.recommendation_type)
        for row in rows:
            keys = {
                str(row.get("artifact_uuid") or ""),
                str(row.get("artifact_id") or ""),
            }
            types: set[str] = set()
            for key in keys:
                types.update(by_artifact.get(key, set()))
            row["recommendation_types_json"] = sorted(types)
