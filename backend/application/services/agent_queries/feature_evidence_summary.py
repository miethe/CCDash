"""Bounded feature evidence summary service — no transcript enrichment.

Session discovery
-----------------
This service discovers sessions for a feature through two successive paths:

1. **Explicit entity links** — the ``entity_links`` DB table is queried for
   ``feature→session`` relationships already established by the link-rebuild
   pipeline.  This is the primary and authoritative path.

2. **Feature-scoped session list** (fallback) — when no explicit links exist,
   ``SessionIntelligenceReadService.list_sessions`` is called with the
   ``feature_id`` filter.  This relies on DB-stored ``feature_id`` / ``task_id``
   columns on session rows, NOT on any heuristic slug-matching.

Heuristic correlation (slug tokens, phase hints, command token scanning, lineage
inheritance) is deliberately **not** performed here.  That logic lives entirely
in :mod:`.session_correlation` and is consumed only by the planning session board
(``planning_sessions.py``).  This separation ensures the two surfaces do not
duplicate correlation heuristics (P3-003 acceptance criterion).

The ``_feature_slug`` helper below extracts a display slug string from a feature
row dict for DTO population; it is unrelated to
:func:`.session_correlation._feature_slug_tokens`, which tokenises a slug for
substring matching during heuristic correlation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_model_identity

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import (
    FeatureEvidenceSummary,
    SessionRef,
    TelemetryAvailability,
    TokenUsageByModel,
)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _feature_slug(row: dict[str, Any]) -> str:
    return str(
        row.get("feature_slug")
        or row.get("featureSlug")
        or row.get("name")
        or row.get("id")
        or ""
    )


def _counterpart_id(
    link: dict[str, Any],
    entity_type: str,
    entity_id: str,
    counterpart_type: str,
) -> str:
    if (
        str(link.get("source_type") or "") == entity_type
        and str(link.get("source_id") or "") == entity_id
    ):
        if str(link.get("target_type") or "") == counterpart_type:
            return str(link.get("target_id") or "")
    if (
        str(link.get("target_type") or "") == entity_type
        and str(link.get("target_id") or "") == entity_id
    ):
        if str(link.get("source_type") or "") == counterpart_type:
            return str(link.get("source_id") or "")
    return ""


def _session_ref_from_row(row: dict[str, Any]) -> SessionRef:
    return SessionRef(
        session_id=str(row.get("id") or row.get("sessionId") or ""),
        feature_id=str(
            row.get("feature_id")
            or row.get("featureId")
            or row.get("task_id")
            or row.get("taskId")
            or ""
        ),
        root_session_id=str(row.get("root_session_id") or row.get("rootSessionId") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or ""),
        started_at=str(row.get("started_at") or row.get("startedAt") or ""),
        ended_at=str(row.get("ended_at") or row.get("endedAt") or ""),
        model=str(row.get("model") or ""),
        total_cost=_safe_float(row.get("total_cost") or row.get("totalCost")),
        total_tokens=_safe_int(
            row.get("observed_tokens")
            or row.get("observedTokens")
            or row.get("model_io_tokens")
            or row.get("modelIOTokens")
        ),
        duration_seconds=_safe_float(row.get("duration_seconds") or row.get("durationSeconds")),
        tool_names=[],
        workflow_refs=[],
        source_ref=str(row.get("id") or row.get("sessionId") or ""),
    )


def _aggregate_token_usage_by_model(session_refs: list[SessionRef]) -> TokenUsageByModel:
    counts = {
        "opus": 0,
        "sonnet": 0,
        "haiku": 0,
        "other": 0,
    }
    for ref in session_refs:
        family = str(derive_model_identity(ref.model).get("modelFamily") or "").strip().lower()
        bucket = family if family in counts else "other"
        counts[bucket] += _safe_int(ref.total_tokens)
    counts["total"] = sum(counts.values())
    return TokenUsageByModel(**counts)


def _derive_latest_activity(session_rows: list[dict[str, Any]]) -> datetime | None:
    candidates: list[datetime] = []
    for row in session_rows:
        for key in ("ended_at", "endedAt", "started_at", "startedAt", "updated_at", "updatedAt"):
            raw = row.get(key)
            if raw:
                try:
                    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    candidates.append(parsed)
                except (ValueError, TypeError):
                    pass
    return max(candidates) if candidates else None


def _evidence_summary_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    feature_id: str,
    **_: Any,
) -> dict[str, Any]:
    return {"feature_id": feature_id}


class FeatureEvidenceSummaryService:
    """Bounded evidence summary — no transcript enrichment.

    Returns a :class:`FeatureEvidenceSummary` DTO aggregated from repository
    data only.  Unlike :class:`FeatureForensicsQueryService`, this service
    does not open session log files or perform any transcript-level analysis.
    It is intentionally lighter and suitable for high-frequency planning
    surface calls where full forensics would be too expensive.

    Cache policy
    ------------
    Results are memoized via :func:`.cache.memoized_query` under the key
    ``feature-evidence-summary`` with the project-scoped ``feature_id``
    parameter.  The TTL follows ``CCDASH_QUERY_CACHE_TTL_SECONDS`` (default
    600 s).  The fingerprint covers ``sessions``, ``entity_links``, and the
    other planning tables tracked by ``get_data_version_fingerprint``, so any
    session ingest or link rebuild will naturally produce a new fingerprint and
    cause a cache miss on the next call.  Error responses (``status="error"``)
    are NOT cached — the decorator will store whatever the method returns, but
    because ``get_data_version_fingerprint`` returns ``None`` when the DB is
    unavailable (the only scenario that would produce an error early), the
    decorator bypasses the cache store entirely in that case.
    """

    @memoized_query("feature-evidence-summary", param_extractor=_evidence_summary_params)
    async def get_summary(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> FeatureEvidenceSummary:
        """Return bounded evidence summary for a feature.

        Args:
            context: The request context carrying project scope and principal.
            ports: Core infrastructure ports (storage, workspace registry).
            feature_id: The canonical feature identifier to summarise.

        Returns:
            A :class:`FeatureEvidenceSummary` with ``status`` set to
            ``"ok"``, ``"partial"``, or ``"error"``.
        """
        scope = resolve_project_scope(context, ports)
        if scope is None:
            return FeatureEvidenceSummary(
                status="error",
                feature_id=feature_id,
                telemetry_available=TelemetryAvailability(),
                source_refs=[feature_id],
            )

        # --- Resolve feature row ---
        feature_row: dict[str, Any] | None = None
        try:
            feature_row = await ports.storage.features().get_by_id(feature_id)
        except Exception:
            pass

        if feature_row is None:
            return FeatureEvidenceSummary(
                status="error",
                feature_id=feature_id,
                telemetry_available=TelemetryAvailability(),
                source_refs=[feature_id],
            )

        partial = False

        # --- Resolve linked session IDs via entity links ---
        links: list[dict[str, Any]] = []
        try:
            links = await ports.storage.entity_links().get_links_for(
                "feature", feature_id, "related"
            )
        except Exception:
            partial = True

        session_ids = sorted(
            {
                counterpart
                for link in links
                if (
                    counterpart := _counterpart_id(link, "feature", feature_id, "session")
                )
            }
        )

        # --- Fetch session rows (no transcript enrichment) ---
        session_rows: list[dict[str, Any]] = []
        if session_ids:
            try:
                fetched = await ports.storage.sessions().get_many_by_ids(session_ids)
                session_rows = [fetched[sid] for sid in session_ids if sid in fetched]
            except Exception:
                partial = True

        # Fall back to feature-scoped session list when links yield nothing.
        # This uses the DB-stored feature_id/task_id column filter — NOT heuristic
        # slug matching.  Heuristic correlation is deferred to session_correlation.py.
        if not session_rows and not session_ids:
            try:
                from backend.application.services.session_intelligence import (
                    SessionIntelligenceReadService,
                )

                response = await SessionIntelligenceReadService().list_sessions(
                    context,
                    ports,
                    feature_id=feature_id,
                    include_subagents=True,
                    offset=0,
                    limit=100,
                )
                for item in response.items:
                    if hasattr(item, "model_dump"):
                        session_rows.append(item.model_dump())
                    elif isinstance(item, dict):
                        session_rows.append(item)
            except Exception:
                partial = True

        # --- Aggregate metrics from session rows (no log parsing) ---
        session_refs = [_session_ref_from_row(row) for row in session_rows]

        workflow_counter: Counter[str] = Counter()
        total_cost = 0.0
        total_tokens = 0
        for ref in session_refs:
            total_cost += ref.total_cost
            total_tokens += ref.total_tokens
            for workflow in ref.workflow_refs:
                workflow_counter[workflow] += 1

        workflow_mix = {
            workflow: round(count / max(sum(workflow_counter.values()), 1), 4)
            for workflow, count in workflow_counter.items()
        }

        latest_activity = _derive_latest_activity(session_rows)
        token_usage_by_model = _aggregate_token_usage_by_model(session_refs)

        # --- Telemetry availability ---
        telemetry_available = TelemetryAvailability(
            sessions=len(session_refs) > 0,
            # documents and tasks are not fetched in this bounded service;
            # report False so callers know they are not populated.
            documents=False,
            tasks=False,
        )

        # --- Data freshness ---
        data_freshness = derive_data_freshness(
            feature_row.get("updated_at") or feature_row.get("updatedAt"),
            *[
                row.get("updated_at")
                or row.get("updatedAt")
                or row.get("ended_at")
                or row.get("endedAt")
                or row.get("started_at")
                or row.get("startedAt")
                for row in session_rows
            ],
        )

        name = str(
            feature_row.get("name")
            or feature_row.get("title")
            or _feature_slug(feature_row)
            or feature_id
        )

        status = "partial" if partial else "ok"

        return FeatureEvidenceSummary(
            status=status,
            feature_id=feature_id,
            feature_slug=_feature_slug(feature_row),
            feature_status=str(feature_row.get("status") or ""),
            name=name,
            session_count=len(session_refs),
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            token_usage_by_model=token_usage_by_model,
            workflow_mix=workflow_mix,
            latest_activity=latest_activity,
            telemetry_available=telemetry_available,
            data_freshness=data_freshness,
            source_refs=collect_source_refs(
                feature_id,
                [ref.session_id for ref in session_refs],
            ),
        )
