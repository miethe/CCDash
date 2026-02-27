"""Feature execution workbench service helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.db.factory import get_document_repository
from backend.models import (
    ExecutionRecommendation,
    ExecutionRecommendationEvidence,
    ExecutionRecommendationOption,
    Feature,
    FeatureExecutionAnalyticsSummary,
    FeatureExecutionContext,
    FeatureExecutionWarning,
    LinkedDocument,
)

_TERMINAL_PHASE_STATUSES = {"done", "deferred", "completed"}
_FINAL_FEATURE_STATUSES = {"done", "deferred", "completed"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _coerce_phase_number(raw: str) -> int | None:
    token = str(raw or "").strip().lower()
    if not token:
        return None
    if token.startswith("phase"):
        pieces = token.split()
        token = pieces[-1] if pieces else ""
    if token.isdigit():
        return int(token)
    return None


def _normalize_doc_type(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _document_to_linked(row: dict[str, Any]) -> LinkedDocument:
    return LinkedDocument(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or row.get("file_path") or "Untitled"),
        filePath=str(row.get("file_path") or ""),
        docType=str(row.get("doc_type") or "").strip() or "spec",
        category=str(row.get("category") or ""),
        prdRef=str(row.get("prd_ref") or ""),
    )


def _phase_is_terminal(status: str) -> bool:
    return str(status or "").strip().lower() in _TERMINAL_PHASE_STATUSES


def _feature_is_finalized(status: str) -> bool:
    return str(status or "").strip().lower() in _FINAL_FEATURE_STATUSES


def _plan_documents(documents: list[LinkedDocument]) -> list[LinkedDocument]:
    return [doc for doc in documents if _normalize_doc_type(doc.docType) == "implementation_plan"]


def _find_planning_seed(documents: list[LinkedDocument]) -> LinkedDocument | None:
    candidates = [
        doc
        for doc in documents
        if _normalize_doc_type(doc.docType) in {"prd", "report"}
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda doc: (doc.docType != "prd", doc.filePath))[0]


def _phase_snapshot(feature: Feature) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for phase in feature.phases:
        number = _coerce_phase_number(phase.phase)
        status = str(phase.status or "backlog").strip().lower()
        is_terminal = _phase_is_terminal(status)

        # Count deferred tasks as completed for progression detection.
        completed = _safe_int(getattr(phase, "completedTasks", 0), 0)
        deferred = _safe_int(getattr(phase, "deferredTasks", 0), 0)
        total = _safe_int(getattr(phase, "totalTasks", 0), 0)
        effectively_completed = max(completed, deferred)
        if total > 0:
            effectively_completed = min(total, effectively_completed)

        has_completed_work = is_terminal or (
            total > 0 and effectively_completed >= total
        )

        snapshots.append(
            {
                "token": str(phase.phase),
                "number": number,
                "status": status,
                "terminal": is_terminal,
                "completed": has_completed_work,
            }
        )
    return snapshots


def build_execution_recommendation(
    feature: Feature,
    documents: list[LinkedDocument],
) -> ExecutionRecommendation:
    plan_docs = _plan_documents(documents)
    plan_doc = sorted(plan_docs, key=lambda doc: doc.filePath)[0] if plan_docs else None
    planning_seed_doc = _find_planning_seed(documents)

    phases = _phase_snapshot(feature)
    completed_numbers = sorted(
        {
            int(row["number"])
            for row in phases
            if row["number"] is not None and bool(row["completed"])
        }
    )
    active_numbers = sorted(
        {
            int(row["number"])
            for row in phases
            if row["number"] is not None and row["status"] in {"in-progress", "review"}
        }
    )

    highest_completed = completed_numbers[-1] if completed_numbers else None
    next_phase: int | None = None
    if highest_completed is not None:
        candidate = highest_completed + 1
        for row in phases:
            if row["number"] == candidate and not bool(row["terminal"]):
                next_phase = candidate
                break

    def make_option(
        rule_id: str,
        command: str,
        confidence: float,
        explanation: str,
        evidence_refs: list[str],
    ) -> ExecutionRecommendationOption:
        return ExecutionRecommendationOption(
            command=command,
            ruleId=rule_id,
            confidence=confidence,
            explanation=explanation,
            evidenceRefs=evidence_refs,
        )

    candidates: list[ExecutionRecommendationOption] = []

    # R1
    if plan_doc is None and planning_seed_doc is not None:
        candidates.append(
            make_option(
                "R1_PLAN_FROM_PRD_OR_REPORT",
                f"/plan:plan-feature {planning_seed_doc.filePath}",
                0.96,
                "Implementation plan is missing but a PRD/report exists, so planning should be generated first.",
                [planning_seed_doc.filePath, "missing:implementation_plan"],
            )
        )

    # R2
    if plan_doc is not None and not completed_numbers:
        candidates.append(
            make_option(
                "R2_START_PHASE_1",
                f"/dev:execute-phase 1 {plan_doc.filePath}",
                0.92,
                "Implementation plan exists and no completed phases were detected, so Phase 1 should start.",
                [plan_doc.filePath, "completed_phases:0"],
            )
        )

    # R3
    if plan_doc is not None and highest_completed is not None and next_phase is not None:
        candidates.append(
            make_option(
                "R3_ADVANCE_TO_NEXT_PHASE",
                f"/dev:execute-phase {next_phase} {plan_doc.filePath}",
                0.9,
                "A completed phase was found and the next phase is not terminal, so advance to the next phase.",
                [
                    plan_doc.filePath,
                    f"highest_completed_phase:{highest_completed}",
                    f"next_phase:{next_phase}",
                ],
            )
        )

    # R4
    if plan_doc is not None and active_numbers:
        active_phase = active_numbers[0]
        candidates.append(
            make_option(
                "R4_RESUME_ACTIVE_PHASE",
                f"/dev:execute-phase {active_phase} {plan_doc.filePath}",
                0.89,
                "An in-progress/review phase is active, so work should resume in that phase.",
                [plan_doc.filePath, f"active_phase:{active_phase}"],
            )
        )

    # R5
    all_terminal = bool(phases) and all(bool(row["terminal"]) for row in phases)
    if all_terminal and not _feature_is_finalized(feature.status):
        candidates.append(
            make_option(
                "R5_COMPLETE_STORY",
                f"/dev:complete-user-story {feature.id}",
                0.9,
                "All phases are terminal but feature status is not finalized, so story completion should run.",
                [f"feature:{feature.id}", "all_phases_terminal:true"],
            )
        )

    # R6 fallback
    fallback_confidence = 0.66 if documents else 0.45
    candidates.append(
        make_option(
            "R6_FALLBACK_QUICK_FEATURE",
            f"/dev:quick-feature {feature.id}",
            fallback_confidence,
            "Evidence is insufficient or ambiguous for a deterministic phase command.",
            [f"feature:{feature.id}", "evidence:insufficient"],
        )
    )

    primary = candidates[0]
    alternatives: list[ExecutionRecommendationOption] = []
    seen_commands = {primary.command}
    for candidate in candidates[1:]:
        if candidate.command in seen_commands:
            continue
        alternatives.append(candidate)
        seen_commands.add(candidate.command)
        if len(alternatives) >= 2:
            break

    evidence: list[ExecutionRecommendationEvidence] = []
    for idx, ref in enumerate(primary.evidenceRefs):
        source_type = "context"
        if ref.endswith(".md"):
            source_type = "document"
        elif ref.startswith("active_phase") or ref.startswith("next_phase") or ref.startswith("highest_completed_phase"):
            source_type = "phase"
        elif ref.startswith("feature:"):
            source_type = "feature"
        evidence.append(
            ExecutionRecommendationEvidence(
                id=f"EV-{idx + 1}",
                label=ref.split(":", 1)[0].replace("_", " ").title(),
                value=ref,
                sourceType=source_type,
                sourcePath=ref if ref.endswith(".md") else "",
            )
        )

    return ExecutionRecommendation(
        primary=primary,
        alternatives=alternatives,
        ruleId=primary.ruleId,
        confidence=primary.confidence,
        explanation=primary.explanation,
        evidenceRefs=primary.evidenceRefs,
        evidence=evidence,
    )


async def load_execution_documents(
    db: Any,
    project_id: str,
    feature_id: str,
    fallback_documents: list[LinkedDocument] | None = None,
) -> list[LinkedDocument]:
    repo = get_document_repository(db)
    rows = await repo.list_paginated(
        project_id,
        0,
        250,
        {
            "feature": feature_id,
            "include_progress": True,
        },
    )
    docs = [_document_to_linked(row) for row in rows]

    if not docs and fallback_documents:
        docs = list(fallback_documents)

    deduped: dict[str, LinkedDocument] = {}
    for doc in docs:
        key = (doc.filePath or doc.id or doc.title).strip().lower()
        if not key:
            continue
        deduped[key] = doc

    return sorted(deduped.values(), key=lambda doc: (doc.docType, doc.filePath, doc.title))


def _session_value(session: Any, key: str, default: Any = None) -> Any:
    if isinstance(session, dict):
        return session.get(key, default)
    return getattr(session, key, default)


async def load_execution_analytics(
    db: Any,
    project_id: str,
    feature_id: str,
    sessions: list[Any],
) -> FeatureExecutionAnalyticsSummary:
    model_tokens = {
        str(_session_value(session, "modelDisplayName") or _session_value(session, "model") or "").strip()
        for session in sessions
        if str(_session_value(session, "modelDisplayName") or _session_value(session, "model") or "").strip()
    }

    summary = FeatureExecutionAnalyticsSummary(
        sessionCount=len(sessions),
        primarySessionCount=sum(1 for session in sessions if bool(_session_value(session, "isPrimaryLink", False))),
        totalSessionCost=round(sum(_safe_float(_session_value(session, "totalCost"), 0.0) for session in sessions), 4),
        modelCount=len(model_tokens),
    )

    if isinstance(db, aiosqlite.Connection):
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN event_type = 'artifact.linked' THEN 1 ELSE 0 END), 0) AS artifact_events,
                COALESCE(SUM(CASE WHEN event_type = 'log.command' THEN 1 ELSE 0 END), 0) AS command_events,
                COALESCE(MAX(occurred_at), '') AS last_event_at
            FROM telemetry_events
            WHERE project_id = ? AND feature_id = ?
        """
        async with db.execute(query, (project_id, feature_id)) as cur:
            row = await cur.fetchone()
            if row:
                summary.artifactEventCount = _safe_int(row[0], 0)
                summary.commandEventCount = _safe_int(row[1], 0)
                summary.lastEventAt = str(row[2] or "")
        return summary

    row = await db.fetchrow(
        """
            SELECT
                COALESCE(SUM(CASE WHEN event_type = 'artifact.linked' THEN 1 ELSE 0 END), 0) AS artifact_events,
                COALESCE(SUM(CASE WHEN event_type = 'log.command' THEN 1 ELSE 0 END), 0) AS command_events,
                COALESCE(MAX(occurred_at), '') AS last_event_at
            FROM telemetry_events
            WHERE project_id = $1 AND feature_id = $2
        """,
        project_id,
        feature_id,
    )
    if row:
        summary.artifactEventCount = _safe_int(row.get("artifact_events"), 0)
        summary.commandEventCount = _safe_int(row.get("command_events"), 0)
        summary.lastEventAt = str(row.get("last_event_at") or "")
    return summary


def build_execution_context(
    feature: Feature,
    documents: list[LinkedDocument],
    sessions: list[Any],
    analytics: FeatureExecutionAnalyticsSummary,
    warnings: list[FeatureExecutionWarning] | None = None,
) -> FeatureExecutionContext:
    recommendation = build_execution_recommendation(feature, documents)
    return FeatureExecutionContext(
        feature=feature,
        documents=documents,
        sessions=[session.model_dump() if hasattr(session, "model_dump") else dict(session) for session in sessions],
        analytics=analytics,
        recommendations=recommendation,
        warnings=warnings or [],
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
