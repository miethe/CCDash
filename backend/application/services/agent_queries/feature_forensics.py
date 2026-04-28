"""Feature-level development history and forensics service."""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.session_intelligence import SessionIntelligenceReadService
from backend.application.services.sessions import SessionTranscriptService
from backend.model_identity import derive_model_identity

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import (
    DocumentRef,
    FeatureForensicsDTO,
    SessionRef,
    TaskRef,
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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


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


def _feature_slug(row: dict[str, Any]) -> str:
    return str(
        row.get("feature_slug")
        or row.get("featureSlug")
        or row.get("name")
        or row.get("id")
        or ""
    )


def _counterpart_id(link: dict[str, Any], entity_type: str, entity_id: str, counterpart_type: str) -> str:
    if str(link.get("source_type") or "") == entity_type and str(link.get("source_id") or "") == entity_id:
        if str(link.get("target_type") or "") == counterpart_type:
            return str(link.get("target_id") or "")
    if str(link.get("target_type") or "") == entity_type and str(link.get("target_id") or "") == entity_id:
        if str(link.get("source_type") or "") == counterpart_type:
            return str(link.get("source_id") or "")
    return ""


def _session_ref_from_row(row: dict[str, Any]) -> SessionRef:
    return SessionRef(
        session_id=str(row.get("id") or row.get("sessionId") or ""),
        feature_id=str(row.get("feature_id") or row.get("featureId") or row.get("task_id") or row.get("taskId") or ""),
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


def _document_ref_from_row(row: dict[str, Any]) -> DocumentRef:
    return DocumentRef(
        document_id=str(row.get("id") or ""),
        title=str(row.get("title") or ""),
        file_path=str(row.get("file_path") or row.get("filePath") or ""),
        canonical_path=str(row.get("canonical_path") or row.get("canonicalPath") or ""),
        doc_type=str(row.get("doc_type") or row.get("docType") or ""),
        status=str(row.get("status") or ""),
        updated_at=str(row.get("updated_at") or row.get("updatedAt") or ""),
        feature_slug=str(row.get("feature_slug_canonical") or row.get("featureSlugCanonical") or ""),
    )


def _task_ref_from_row(row: dict[str, Any]) -> TaskRef:
    return TaskRef(
        task_id=str(row.get("id") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or ""),
        priority=str(row.get("priority") or ""),
        owner=str(row.get("owner") or ""),
        phase_id=str(row.get("phase_id") or row.get("phaseId") or ""),
        updated_at=str(row.get("updated_at") or row.get("updatedAt") or ""),
    )


async def _load_feature_session_rows(
    context: RequestContext,
    ports: CorePorts,
    feature_id: str,
    linked_session_ids: list[str],
) -> list[dict[str, Any]]:
    if linked_session_ids:
        fetched = await ports.storage.sessions().get_many_by_ids(linked_session_ids)
        # Preserve input order and drop missing ids
        rows: list[dict[str, Any]] = [fetched[sid] for sid in linked_session_ids if sid in fetched]
        if rows:
            return rows

    response = await SessionIntelligenceReadService().list_sessions(
        context,
        ports,
        feature_id=feature_id,
        include_subagents=True,
        offset=0,
        limit=100,
    )
    return [_as_dict(item) for item in response.items]


async def _enrich_session_refs(
    session_rows: list[dict[str, Any]],
    ports: CorePorts,
) -> tuple[list[SessionRef], list[str], list[str]]:
    refs: list[SessionRef] = []
    rework_signals: list[str] = []
    failure_patterns: list[str] = []
    transcript_service = SessionTranscriptService()

    async def _safe_fetch_logs(row: dict[str, Any]) -> list[dict]:
        try:
            return await transcript_service.list_session_logs(row, ports)
        except Exception:
            return []

    all_logs: list[list[dict]] = await asyncio.gather(
        *[_safe_fetch_logs(row) for row in session_rows]
    )

    for row, logs in zip(session_rows, all_logs):
        ref = _session_ref_from_row(row)

        workflow_tokens: list[str] = []
        tool_names: list[str] = []
        for log in logs:
            content = str(log.get("content") or "").strip()
            if content.startswith("/"):
                workflow_tokens.append(content.split()[0])
            tool_call = log.get("toolCall")
            if isinstance(tool_call, dict):
                tool_name = str(tool_call.get("name") or "").strip()
                if tool_name:
                    tool_names.append(tool_name)
                if bool(tool_call.get("isError")):
                    failure_patterns.append("tool_error")
            if str(log.get("type") or "").strip().lower() == "thought" and "retry" in content.lower():
                rework_signals.append("retry_loop")

        ref.workflow_refs = sorted(set(workflow_tokens))
        ref.tool_names = sorted(set(tool_names))
        refs.append(ref)

    if len(refs) > 1:
        rework_signals.append("multiple_sessions")
    if any(ref.duration_seconds >= 7200 for ref in refs):
        rework_signals.append("long_running_session")
    if any(str(ref.status).lower() not in {"completed", "done", "success"} for ref in refs):
        failure_patterns.append("non_completed_session")

    return refs, sorted(set(rework_signals)), sorted(set(failure_patterns))


def _feature_forensics_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    feature_id: str,
    **_: Any,
) -> dict[str, Any]:
    return {"feature_id": feature_id}


class FeatureForensicsQueryService:
    """Assemble feature execution history from linked entities."""

    @memoized_query("feature_forensics", param_extractor=_feature_forensics_params)
    async def get_forensics(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> FeatureForensicsDTO:
        """Assemble and return the full forensic DTO for a feature.

        ``linked_sessions`` in the returned DTO is the single authoritative
        session list for a feature.  Both ``GET /v1/features/{id}`` and
        ``GET /v1/features/{id}/sessions`` consume this same field via
        ``_get_forensics()`` in the router — the two endpoints are structurally
        incapable of disagreeing on the session array.

        Session linkage is eventually-consistent: links are written by the
        background filesystem sync job (``sync_engine._build_feature_session_links``)
        and read back via ``entity_links.get_links_for("feature", id, "related")``.
        A freshly-imported session may not appear until the next sync cycle.
        """
        scope = resolve_project_scope(context, ports)
        if scope is None:
            return FeatureForensicsDTO(
                status="error",
                feature_id=feature_id,
                name=feature_id,
                telemetry_available=TelemetryAvailability(),
                source_refs=[feature_id],
            )

        partial = False
        feature_row = await ports.storage.features().get_by_id(feature_id)
        if feature_row is None:
            return FeatureForensicsDTO(
                status="error",
                feature_id=feature_id,
                name=feature_id,
                telemetry_available=TelemetryAvailability(),
                source_refs=[feature_id],
            )

        links: list[dict[str, Any]] = []
        try:
            links = await ports.storage.entity_links().get_links_for("feature", feature_id, "related")
        except Exception:
            partial = True

        session_ids = sorted(
            {
                counterpart
                for link in links
                if (counterpart := _counterpart_id(link, "feature", feature_id, "session"))
            }
        )

        document_rows: list[dict[str, Any]] = []
        try:
            document_rows = await ports.storage.documents().list_paginated(
                scope.project.id,
                0,
                100,
                {"feature": feature_id, "include_progress": True},
            )
        except Exception:
            partial = True

        task_rows: list[dict[str, Any]] = []
        try:
            task_rows = await ports.storage.tasks().list_by_feature(feature_id)
        except Exception:
            partial = True

        session_rows: list[dict[str, Any]] = []
        try:
            session_rows = await _load_feature_session_rows(context, ports, feature_id, session_ids)
        except Exception:
            partial = True

        session_refs, rework_signals, failure_patterns = await _enrich_session_refs(session_rows, ports)
        if not session_refs and session_rows:
            session_refs = [_session_ref_from_row(row) for row in session_rows]

        workflow_counter = Counter()
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

        document_refs = [_document_ref_from_row(row) for row in document_rows]
        task_refs = [_task_ref_from_row(row) for row in task_rows]
        representative_sessions = sorted(
            session_refs,
            key=lambda item: (item.total_cost, item.duration_seconds, item.total_tokens),
            reverse=True,
        )[:3]

        data_freshness = derive_data_freshness(
            feature_row.get("updated_at") or feature_row.get("updatedAt"),
            *[row.get("updated_at") or row.get("updatedAt") or row.get("started_at") or row.get("startedAt") for row in session_rows],
            *[row.get("updated_at") or row.get("updatedAt") for row in document_rows],
            *[row.get("updated_at") or row.get("updatedAt") for row in task_rows],
        )

        summary_narrative = (
            f"Feature {_feature_slug(feature_row)} has {len(session_refs)} linked sessions, "
            f"{len(document_refs)} linked documents, and {len(task_refs)} linked tasks. "
            f"Observed cost is {total_cost:.2f} across {total_tokens} tokens."
        )

        name = str(
            feature_row.get("name")
            or feature_row.get("title")
            or _feature_slug(feature_row)
            or feature_id
        )
        telemetry_available = TelemetryAvailability(
            tasks=len(task_refs) > 0,
            documents=len(document_refs) > 0,
            sessions=len(session_refs) > 0,
        )

        status = "ok"
        if partial:
            status = "partial"

        return FeatureForensicsDTO(
            status=status,
            feature_id=feature_id,
            feature_slug=_feature_slug(feature_row),
            feature_status=str(feature_row.get("status") or ""),
            name=name,
            telemetry_available=telemetry_available,
            linked_sessions=session_refs,
            linked_documents=document_refs,
            linked_tasks=task_refs,
            iteration_count=len(session_refs),
            total_cost=round(total_cost, 6),
            total_tokens=total_tokens,
            token_usage_by_model=_aggregate_token_usage_by_model(session_refs),
            workflow_mix=workflow_mix,
            rework_signals=rework_signals,
            failure_patterns=failure_patterns,
            representative_sessions=representative_sessions,
            summary_narrative=summary_narrative,
            data_freshness=data_freshness,
            source_refs=collect_source_refs(
                feature_id,
                [ref.session_id for ref in session_refs],
                [ref.document_id for ref in document_refs],
                [ref.task_id for ref in task_refs],
            ),
        )
