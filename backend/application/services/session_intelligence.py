"""Application services for session intelligence query surfaces."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project
from backend.db.factory import (
    get_document_repository,
    get_session_embedding_repository,
    get_session_intelligence_repository,
    get_session_message_repository,
    get_session_repository,
)
from backend.models import (
    SessionCodeChurnFact,
    SessionIntelligenceCapability,
    SessionIntelligenceConcern,
    SessionIntelligenceConcernSummary,
    SessionIntelligenceDetailResponse,
    SessionIntelligenceDrilldownItem,
    SessionIntelligenceDrilldownResponse,
    SessionIntelligenceListResponse,
    SessionIntelligenceSessionRollup,
    SessionScopeDriftFact,
    SessionSemanticSearchMatch,
    SessionSemanticSearchResponse,
    SessionSentimentFact,
)
from backend.services.session_churn_facts import build_session_code_churn_facts
from backend.services.session_scope_drift import build_session_scope_drift_facts
from backend.services.session_sentiment_facts import build_session_sentiment_facts
from backend.services.session_transcript_projection import project_session_messages


SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY = "session_intelligence_historical_backfill_v1"


class SessionIntelligenceQueryService:
    async def search(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        query: str,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionSemanticSearchResponse:
        return await self.search_semantic_transcripts(
            context,
            ports,
            query=query,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            root_session_id=root_session_id,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    async def search_semantic_transcripts(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        query: str,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionSemanticSearchResponse:
        project = resolve_project(context, ports)
        capability = _capability_payload(ports)
        if project is None or not query.strip() or not capability.supported:
            return SessionSemanticSearchResponse(
                query=query,
                total=0,
                offset=offset,
                limit=limit,
                capability=capability,
                items=[],
            )

        rows = await ports.storage.session_messages().search_messages(
            project.id,
            query,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            session_id=session_id,
            limit=max(limit + offset, limit),
        )
        if root_session_id:
            rows = [row for row in rows if str(row.get("root_session_id") or "") == root_session_id]
        ranked_rows = sorted(
            rows,
            key=lambda row: (
                -_search_score(row, query),
                -int(row.get("message_index") or 0),
                str(row.get("event_timestamp") or ""),
            ),
        )
        paged_rows = ranked_rows[offset : offset + limit]
        return SessionSemanticSearchResponse(
            query=query,
            total=len(ranked_rows),
            offset=offset,
            limit=limit,
            capability=capability,
            items=[_search_match_from_row(row, query) for row in paged_rows],
        )

    async def list_session_intelligence(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
        include_subagents: bool = True,
        session_id: str | None = None,
    ) -> SessionIntelligenceListResponse:
        project = resolve_project(context, ports)
        if project is None:
            return SessionIntelligenceListResponse(generatedAt=_now(), total=0, offset=offset, limit=limit, items=[])

        sessions = await self._load_sessions(
            ports,
            project.id,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            root_session_id=root_session_id,
            offset=offset,
            limit=limit,
            include_subagents=include_subagents,
            session_id=session_id,
        )
        items = [await self._build_rollup(ports, session_row) for session_row in sessions]
        return SessionIntelligenceListResponse(
            generatedAt=_now(),
            total=len(items),
            offset=offset,
            limit=limit,
            items=items,
        )

    async def get_session_intelligence_detail(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        session_id: str,
    ) -> SessionIntelligenceDetailResponse | None:
        project = resolve_project(context, ports)
        session_row = await ports.storage.sessions().get_by_id(session_id)
        if project is None or not session_row or str(session_row.get("project_id") or "") != project.id:
            return None

        sentiment_rows, churn_rows, scope_rows = await _load_facts(ports, session_id)
        rollup = _rollup_from_facts(session_row, sentiment_rows, churn_rows, scope_rows)
        return SessionIntelligenceDetailResponse(
            sessionId=session_id,
            featureId=rollup.featureId,
            rootSessionId=rollup.rootSessionId,
            summary=rollup,
            sentimentFacts=[_sentiment_fact(row) for row in sentiment_rows],
            churnFacts=[_churn_fact(row) for row in churn_rows],
            scopeDriftFacts=[_scope_fact(row) for row in scope_rows],
        )

    async def get_session_detail(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        session_id: str,
    ) -> SessionIntelligenceDetailResponse | None:
        detail = await self.get_session_intelligence_detail(context, ports, session_id=session_id)
        return detail if detail.summary is not None else None

    async def get_session_intelligence_drilldown(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        concern: SessionIntelligenceConcern,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
        include_subagents: bool = True,
        session_id: str | None = None,
    ) -> SessionIntelligenceDrilldownResponse:
        project = resolve_project(context, ports)
        if project is None:
            return SessionIntelligenceDrilldownResponse(
                concern=concern,
                generatedAt=_now(),
                total=0,
                offset=offset,
                limit=limit,
                items=[],
            )

        sessions = await self._load_sessions(
            ports,
            project.id,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            root_session_id=root_session_id,
            offset=0,
            limit=max(offset + limit, 200),
            include_subagents=include_subagents,
            session_id=session_id,
        )
        items: list[SessionIntelligenceDrilldownItem] = []
        for session_row in sessions:
            items.extend(await self._build_drilldown_items(ports, session_row, concern))
        paged_items = items[offset : offset + limit]
        return SessionIntelligenceDrilldownResponse(
            concern=concern,
            generatedAt=_now(),
            total=len(items),
            offset=offset,
            limit=limit,
            items=paged_items,
        )

    async def search_transcript(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        query: str,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionSemanticSearchResponse:
        return await self.search_semantic_transcripts(
            context,
            ports,
            query=query,
            feature_id=feature_id,
            root_session_id=root_session_id,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    async def list_rollups(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionIntelligenceListResponse:
        if session_id:
            detail = await self.get_session_intelligence_detail(context, ports, session_id=session_id)
            items = [detail.summary] if detail and detail.summary else []
            return SessionIntelligenceListResponse(
                generatedAt=_now(),
                total=len(items),
                offset=offset,
                limit=limit,
                items=items,
            )
        return await self.list_session_intelligence(
            context,
            ports,
            feature_id=feature_id,
            root_session_id=root_session_id,
            offset=offset,
            limit=limit,
        )

    async def get_session_detail(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        session_id: str,
    ) -> SessionIntelligenceDetailResponse | None:
        return await self.get_session_intelligence_detail(context, ports, session_id=session_id)

    async def list_drilldown(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        concern: SessionIntelligenceConcern,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionIntelligenceDrilldownResponse:
        if session_id:
            read_service = SessionIntelligenceReadService()
            detail = await read_service.drilldown(
                context,
                ports,
                concern=concern,
                session_id=session_id,
                offset=offset,
                limit=limit,
            )
            if detail is not None:
                return detail
        return await self.get_session_intelligence_drilldown(
            context,
            ports,
            concern=concern,
            feature_id=feature_id,
            root_session_id=root_session_id,
            offset=offset,
            limit=limit,
        )

    async def list_rollups(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionIntelligenceListResponse:
        return await self.list_session_intelligence(
            context,
            ports,
            feature_id=feature_id,
            root_session_id=root_session_id,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    async def list_drilldown(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        concern: SessionIntelligenceConcern,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> SessionIntelligenceDrilldownResponse:
        return await self.get_session_intelligence_drilldown(
            context,
            ports,
            concern=concern,
            feature_id=feature_id,
            root_session_id=root_session_id,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    async def _load_sessions(
        self,
        ports: CorePorts,
        project_id: str,
        *,
        feature_id: str | None,
        conversation_family_id: str | None,
        root_session_id: str | None,
        offset: int,
        limit: int,
        include_subagents: bool,
        session_id: str | None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"include_subagents": include_subagents}
        if conversation_family_id:
            filters["conversation_family_id"] = conversation_family_id
        if root_session_id:
            filters["root_session_id"] = root_session_id
        bounded_limit = max(offset + limit, 200) if feature_id else limit
        rows = await ports.storage.sessions().list_paginated(
            0 if feature_id else offset,
            bounded_limit,
            project_id,
            "started_at",
            "desc",
            filters,
        )
        if session_id:
            rows = [row for row in rows if str(row.get("id") or "") == session_id]
        if feature_id:
            rows = [row for row in rows if _feature_id(row) == feature_id]
            rows = rows[offset : offset + limit]
        return rows

    async def _build_rollup(
        self,
        ports: CorePorts,
        session_row: dict[str, Any],
    ) -> SessionIntelligenceSessionRollup:
        sentiment_rows, churn_rows, scope_rows = await _load_facts(ports, str(session_row.get("id") or ""))
        return _rollup_from_facts(session_row, sentiment_rows, churn_rows, scope_rows)

    async def _build_drilldown_items(
        self,
        ports: CorePorts,
        session_row: dict[str, Any],
        concern: SessionIntelligenceConcern,
    ) -> list[SessionIntelligenceDrilldownItem]:
        session_id = str(session_row.get("id") or "")
        root_session_id = str(session_row.get("root_session_id") or session_id)
        base_kwargs = {
            "concern": concern,
            "sessionId": session_id,
            "featureId": _feature_id(session_row),
            "rootSessionId": root_session_id,
            "startedAt": str(session_row.get("started_at") or ""),
            "endedAt": str(session_row.get("ended_at") or ""),
        }
        if concern == "sentiment":
            rows = await ports.storage.session_intelligence().list_session_sentiment_facts(session_id)
            return [
                SessionIntelligenceDrilldownItem(
                    **base_kwargs,
                    label=str(row.get("sentiment_label") or "neutral"),
                    score=float(row.get("sentiment_score") or 0.0),
                    confidence=float(row.get("confidence") or 0.0),
                    messageIndex=int(row.get("message_index") or 0),
                    sourceMessageId=str(row.get("source_message_id") or ""),
                    sourceLogId=str(row.get("source_log_id") or ""),
                    evidence=_evidence(row),
                )
                for row in rows
            ]
        if concern == "churn":
            rows = await ports.storage.session_intelligence().list_session_code_churn_facts(session_id)
            return [
                SessionIntelligenceDrilldownItem(
                    **base_kwargs,
                    label="low_progress_loop" if bool(row.get("low_progress_loop")) else "churn",
                    score=float(row.get("churn_score") or 0.0),
                    confidence=float(row.get("confidence") or 0.0),
                    messageIndex=int(row.get("last_message_index") or 0),
                    sourceLogId=str(row.get("last_source_log_id") or ""),
                    filePath=str(row.get("file_path") or ""),
                    evidence=_evidence(row),
                )
                for row in rows
            ]
        rows = await ports.storage.session_intelligence().list_session_scope_drift_facts(session_id)
        return [
            SessionIntelligenceDrilldownItem(
                **base_kwargs,
                label="out_of_scope" if int(row.get("out_of_scope_path_count") or 0) > 0 else "in_scope",
                score=float(row.get("drift_ratio") or 0.0),
                confidence=float(row.get("confidence") or 0.0),
                evidence=_evidence(row),
            )
            for row in rows
        ]


async def _load_facts(
    ports: CorePorts,
    session_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    session_intelligence_repo_getter = getattr(ports.storage, "session_intelligence", None)
    if not callable(session_intelligence_repo_getter):
        return [], [], []
    repo = session_intelligence_repo_getter()
    return await asyncio.gather(
        repo.list_session_sentiment_facts(session_id),
        repo.list_session_code_churn_facts(session_id),
        repo.list_session_scope_drift_facts(session_id),
    )


def _rollup_from_facts(
    session_row: dict[str, Any],
    sentiment_rows: list[dict[str, Any]],
    churn_rows: list[dict[str, Any]],
    scope_rows: list[dict[str, Any]],
) -> SessionIntelligenceSessionRollup:
    session_id = str(session_row.get("id") or "")
    return SessionIntelligenceSessionRollup(
        sessionId=session_id,
        featureId=_feature_id(session_row) or _first_fact_feature_id(sentiment_rows, churn_rows, scope_rows),
        rootSessionId=str(session_row.get("root_session_id") or session_id),
        startedAt=str(session_row.get("started_at") or ""),
        endedAt=str(session_row.get("ended_at") or ""),
        sentiment=_summarize_sentiment(sentiment_rows),
        churn=_summarize_churn(churn_rows),
        scopeDrift=_summarize_scope(scope_rows),
    )


def _capability_payload(ports: CorePorts) -> SessionIntelligenceCapability:
    descriptor = ports.storage.session_embeddings().describe_capability()
    return SessionIntelligenceCapability(
        supported=True,
        authoritative=bool(getattr(descriptor, "authoritative", False)),
        storageProfile=str(getattr(descriptor, "storage_profile", "")),
        searchMode="canonical_lexical",
        detail=(
            "Canonical transcript search is lexical today; "
            f"{str(getattr(descriptor, 'notes', '') or '').strip()}"
        ).strip(),
    )


def _search_match_from_row(row: dict[str, Any], query: str) -> SessionSemanticSearchMatch:
    content = str(row.get("content") or "")
    matched_terms = [term for term in _query_terms(query) if term in content.lower()]
    score = _search_score(row, query)
    return SessionSemanticSearchMatch(
        sessionId=str(row.get("session_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        rootSessionId=str(row.get("root_session_id") or ""),
        threadSessionId=str(row.get("thread_session_id") or row.get("session_id") or ""),
        blockKind="message",
        blockIndex=int(row.get("message_index") or 0),
        eventTimestamp=str(row.get("event_timestamp") or ""),
        score=round(float(score), 4),
        matchedTerms=matched_terms,
        messageIds=[str(row.get("message_id") or "")] if str(row.get("message_id") or "").strip() else [],
        sourceLogIds=[str(row.get("source_log_id") or "")] if str(row.get("source_log_id") or "").strip() else [],
        content=content,
        snippet=_snippet(content, matched_terms),
    )


def _search_score(row: dict[str, Any], query: str) -> float:
    content = str(row.get("content") or "").lower()
    score = float(sum(1 for term in _query_terms(query) if term in content))
    if str(row.get("message_type") or "") == "tool":
        score += 0.25
    return round(score, 4)


def _feature_id(session_row: dict[str, Any]) -> str:
    return str(session_row.get("task_id") or session_row.get("taskId") or "")


def _query_terms(query: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for part in query.lower().split():
        term = part.strip()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _snippet(content: str, matched_terms: list[str]) -> str:
    if not content:
        return ""
    lowered = content.lower()
    start = 0
    for term in matched_terms:
        idx = lowered.find(term)
        if idx >= 0:
            start = max(0, idx - 60)
            break
    snippet = content[start : start + 240].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if start + 240 < len(content):
        snippet = f"{snippet}..."
    return snippet


def _first_fact_feature_id(*collections: list[dict[str, Any]]) -> str:
    for rows in collections:
        for row in rows:
            feature_id = str(row.get("feature_id") or "")
            if feature_id:
                return feature_id
    return ""


def _summarize_sentiment(rows: list[dict[str, Any]]) -> SessionIntelligenceConcernSummary:
    if not rows:
        return SessionIntelligenceConcernSummary(label="neutral")
    avg_score = sum(float(row.get("sentiment_score") or 0.0) for row in rows) / len(rows)
    if avg_score <= -0.2:
        label = "negative"
    elif avg_score >= 0.2:
        label = "positive"
    else:
        label = "neutral"
    return SessionIntelligenceConcernSummary(
        label=label,
        score=round(avg_score, 4),
        confidence=round(sum(float(row.get("confidence") or 0.0) for row in rows) / len(rows), 4),
        factCount=len(rows),
        flaggedCount=sum(
            1
            for row in rows
            if str(row.get("sentiment_label") or "") == "negative" or float(row.get("sentiment_score") or 0.0) <= -0.5
        ),
    )


def _summarize_churn(rows: list[dict[str, Any]]) -> SessionIntelligenceConcernSummary:
    if not rows:
        return SessionIntelligenceConcernSummary(label="stable")
    avg_score = sum(float(row.get("churn_score") or 0.0) for row in rows) / len(rows)
    flagged_count = sum(
        1
        for row in rows
        if bool(row.get("low_progress_loop")) or float(row.get("churn_score") or 0.0) >= 0.6
    )
    return SessionIntelligenceConcernSummary(
        label="high_churn" if flagged_count else "stable",
        score=round(avg_score, 4),
        confidence=round(sum(float(row.get("confidence") or 0.0) for row in rows) / len(rows), 4),
        factCount=len(rows),
        flaggedCount=flagged_count,
    )


def _summarize_scope(rows: list[dict[str, Any]]) -> SessionIntelligenceConcernSummary:
    if not rows:
        return SessionIntelligenceConcernSummary(label="in_scope")
    avg_drift = sum(float(row.get("drift_ratio") or 0.0) for row in rows) / len(rows)
    flagged_count = sum(
        1
        for row in rows
        if float(row.get("drift_ratio") or 0.0) >= 0.35 or float(row.get("adherence_score") or 1.0) < 0.7
    )
    return SessionIntelligenceConcernSummary(
        label="drifting" if flagged_count else "in_scope",
        score=round(avg_drift, 4),
        confidence=round(sum(float(row.get("confidence") or 0.0) for row in rows) / len(rows), 4),
        factCount=len(rows),
        flaggedCount=flagged_count,
    )


def _sentiment_fact(row: dict[str, Any]) -> SessionSentimentFact:
    return SessionSentimentFact(
        sessionId=str(row.get("session_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        rootSessionId=str(row.get("root_session_id") or ""),
        threadSessionId=str(row.get("thread_session_id") or ""),
        sourceMessageId=str(row.get("source_message_id") or ""),
        sourceLogId=str(row.get("source_log_id") or ""),
        messageIndex=int(row.get("message_index") or 0),
        sentimentLabel=str(row.get("sentiment_label") or "neutral"),
        sentimentScore=float(row.get("sentiment_score") or 0.0),
        confidence=float(row.get("confidence") or 0.0),
        heuristicVersion=str(row.get("heuristic_version") or ""),
        evidence=_evidence(row),
    )


def _churn_fact(row: dict[str, Any]) -> SessionCodeChurnFact:
    return SessionCodeChurnFact(
        sessionId=str(row.get("session_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        rootSessionId=str(row.get("root_session_id") or ""),
        threadSessionId=str(row.get("thread_session_id") or ""),
        filePath=str(row.get("file_path") or ""),
        firstSourceLogId=str(row.get("first_source_log_id") or ""),
        lastSourceLogId=str(row.get("last_source_log_id") or ""),
        firstMessageIndex=int(row.get("first_message_index") or 0),
        lastMessageIndex=int(row.get("last_message_index") or 0),
        touchCount=int(row.get("touch_count") or 0),
        distinctEditTurnCount=int(row.get("distinct_edit_turn_count") or 0),
        repeatTouchCount=int(row.get("repeat_touch_count") or 0),
        rewritePassCount=int(row.get("rewrite_pass_count") or 0),
        additionsTotal=int(row.get("additions_total") or 0),
        deletionsTotal=int(row.get("deletions_total") or 0),
        netDiffTotal=int(row.get("net_diff_total") or 0),
        churnScore=float(row.get("churn_score") or 0.0),
        progressScore=float(row.get("progress_score") or 0.0),
        lowProgressLoop=bool(row.get("low_progress_loop")),
        confidence=float(row.get("confidence") or 0.0),
        heuristicVersion=str(row.get("heuristic_version") or ""),
        evidence=_evidence(row),
    )


def _scope_fact(row: dict[str, Any]) -> SessionScopeDriftFact:
    return SessionScopeDriftFact(
        sessionId=str(row.get("session_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        rootSessionId=str(row.get("root_session_id") or ""),
        threadSessionId=str(row.get("thread_session_id") or ""),
        plannedPathCount=int(row.get("planned_path_count") or 0),
        actualPathCount=int(row.get("actual_path_count") or 0),
        matchedPathCount=int(row.get("matched_path_count") or 0),
        outOfScopePathCount=int(row.get("out_of_scope_path_count") or 0),
        driftRatio=float(row.get("drift_ratio") or 0.0),
        adherenceScore=float(row.get("adherence_score") or 0.0),
        confidence=float(row.get("confidence") or 0.0),
        heuristicVersion=str(row.get("heuristic_version") or ""),
        evidence=_evidence(row),
    )


def _evidence(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence_json")
    return evidence if isinstance(evidence, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_session_embedding_blocks(canonical_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    substantive_rows = [row for row in canonical_rows if _embedding_row_content(row)]
    if not substantive_rows:
        return []

    blocks: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for row in substantive_rows:
        block = _embedding_block("message", int(row.get("messageIndex") or 0), [row])
        content_hash = str(block.get("content_hash") or "")
        if not content_hash or content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        blocks.append(block)

    window_size = min(5, len(substantive_rows))
    for start in range(0, len(substantive_rows) - window_size + 1):
        window_rows = substantive_rows[start : start + window_size]
        block = _embedding_block("window", start, window_rows)
        content_hash = str(block.get("content_hash") or "")
        if not content_hash or content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        blocks.append(block)
    return blocks


def session_intelligence_backfill_operator_guidance(payload: dict[str, Any]) -> list[str]:
    checkpoint = payload.get("checkpoint") if isinstance(payload.get("checkpoint"), dict) else {}
    checkpoint_key = str(payload.get("checkpointKey") or SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY)
    guidance = [
        f"Re-run with the same checkpoint key `{checkpoint_key}` to continue from the last committed session cursor.",
        "Use `--reset-session-intelligence-checkpoint` to restart from the oldest eligible session.",
    ]
    if bool(payload.get("completed")):
        guidance[0] = f"Checkpoint `{checkpoint_key}` is complete; reset it only if you want to rebuild history from the beginning."
    if not bool(payload.get("embeddingWriteSupported")):
        guidance.append("Embedding rows are skipped on unsupported storage profiles; transcript and fact backfill can still complete.")
    elif int(payload.get("embeddingBlocksBackfilled") or 0) == 0:
        guidance.append("Embedding storage is available; this batch did not materialize any substantive transcript blocks.")
    if checkpoint:
        last_session_id = str(checkpoint.get("lastSessionId") or "")
        last_started_at = str(checkpoint.get("lastStartedAt") or "")
        if last_session_id and last_started_at and not bool(payload.get("completed")):
            guidance.append(
                f"Current cursor is `{last_started_at}` / `{last_session_id}`; the next run starts strictly after that pair."
            )
    return guidance


class HistoricalSessionIntelligenceBackfillService:
    async def backfill(
        self,
        db: Any,
        *,
        project_id: str,
        limit: int = 200,
        checkpoint_key: str = SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY,
        reset_checkpoint: bool = False,
    ) -> dict[str, Any]:
        session_repo = get_session_repository(db)
        session_message_repo = get_session_message_repository(db)
        session_embedding_repo = get_session_embedding_repository(db)
        intelligence_repo = get_session_intelligence_repository(db)
        document_repo = get_document_repository(db)

        if reset_checkpoint:
            await intelligence_repo.delete_backfill_checkpoint(project_id, checkpoint_key=checkpoint_key)

        checkpoint = await intelligence_repo.load_backfill_checkpoint(project_id, checkpoint_key=checkpoint_key)
        if not isinstance(checkpoint, dict):
            checkpoint = {}
        after_started_at = str(checkpoint.get("lastStartedAt") or "")
        after_session_id = str(checkpoint.get("lastSessionId") or "")

        session_rows = await intelligence_repo.list_backfill_sessions(
            project_id,
            after_started_at=after_started_at,
            after_session_id=after_session_id,
            limit=max(1, limit),
        )
        embedding_capability = session_embedding_repo.describe_capability()
        warnings: list[dict[str, Any]] = []
        progress = {
            "sessionsProcessed": int(checkpoint.get("sessionsProcessed") or 0),
            "transcriptSessionsBackfilled": int(checkpoint.get("transcriptSessionsBackfilled") or 0),
            "derivedFactSessionsBackfilled": int(checkpoint.get("derivedFactSessionsBackfilled") or 0),
            "embeddingSessionsBackfilled": int(checkpoint.get("embeddingSessionsBackfilled") or 0),
            "embeddingBlocksBackfilled": int(checkpoint.get("embeddingBlocksBackfilled") or 0),
        }
        batch_counts = {
            "sessionsProcessed": 0,
            "transcriptSessionsBackfilled": 0,
            "derivedFactSessionsBackfilled": 0,
            "embeddingSessionsBackfilled": 0,
            "embeddingBlocksBackfilled": 0,
        }
        last_started_at = after_started_at
        last_session_id = after_session_id

        for session_row in session_rows:
            session_id = str(session_row.get("id") or "")
            if not session_id:
                continue
            logs = await session_repo.get_logs(session_id)
            canonical_rows = project_session_messages(session_row, logs) if logs else []
            if not canonical_rows:
                canonical_rows = _normalize_canonical_rows(await session_message_repo.list_by_session(session_id))
            file_updates = await session_repo.get_file_updates(session_id)
            linked_docs = await _linked_documents(document_repo, project_id, session_row)

            await session_message_repo.replace_session_messages(session_id, canonical_rows)
            await _replace_session_intelligence_facts(
                intelligence_repo,
                session_id,
                session_row,
                canonical_rows,
                file_updates,
                linked_docs,
            )

            embedding_blocks = build_session_embedding_blocks(canonical_rows)
            if bool(getattr(embedding_capability, "supported", False)):
                await session_embedding_repo.replace_session_embeddings(session_id, embedding_blocks)
                batch_counts["embeddingSessionsBackfilled"] += 1
                batch_counts["embeddingBlocksBackfilled"] += len(embedding_blocks)

            batch_counts["sessionsProcessed"] += 1
            batch_counts["transcriptSessionsBackfilled"] += 1
            batch_counts["derivedFactSessionsBackfilled"] += 1
            progress["sessionsProcessed"] += 1
            progress["transcriptSessionsBackfilled"] += 1
            progress["derivedFactSessionsBackfilled"] += 1
            if bool(getattr(embedding_capability, "supported", False)):
                progress["embeddingSessionsBackfilled"] += 1
                progress["embeddingBlocksBackfilled"] += len(embedding_blocks)

            last_started_at = _session_cursor_value(session_row)
            last_session_id = session_id
            checkpoint = _build_backfill_checkpoint(
                checkpoint_key=checkpoint_key,
                last_started_at=last_started_at,
                last_session_id=last_session_id,
                completed=False,
                progress=progress,
            )
            await intelligence_repo.save_backfill_checkpoint(project_id, checkpoint, checkpoint_key=checkpoint_key)

        completed = len(session_rows) < max(1, limit)
        if session_rows and not completed:
            remaining = await intelligence_repo.list_backfill_sessions(
                project_id,
                after_started_at=last_started_at,
                after_session_id=last_session_id,
                limit=1,
            )
            completed = not remaining
        checkpoint = _build_backfill_checkpoint(
            checkpoint_key=checkpoint_key,
            last_started_at=last_started_at,
            last_session_id=last_session_id,
            completed=completed,
            progress=progress,
        )
        await intelligence_repo.save_backfill_checkpoint(project_id, checkpoint, checkpoint_key=checkpoint_key)

        payload = {
            "projectId": project_id,
            "checkpointKey": checkpoint_key,
            "storageProfile": str(getattr(embedding_capability, "storage_profile", "") or ""),
            "embeddingWriteSupported": bool(getattr(embedding_capability, "supported", False)),
            "authoritative": bool(getattr(embedding_capability, "authoritative", False)),
            "limit": max(1, limit),
            "sessionsProcessed": batch_counts["sessionsProcessed"],
            "transcriptSessionsBackfilled": batch_counts["transcriptSessionsBackfilled"],
            "derivedFactSessionsBackfilled": batch_counts["derivedFactSessionsBackfilled"],
            "embeddingSessionsBackfilled": batch_counts["embeddingSessionsBackfilled"],
            "embeddingBlocksBackfilled": batch_counts["embeddingBlocksBackfilled"],
            "sessionsProcessedTotal": progress["sessionsProcessed"],
            "transcriptSessionsBackfilledTotal": progress["transcriptSessionsBackfilled"],
            "derivedFactSessionsBackfilledTotal": progress["derivedFactSessionsBackfilled"],
            "embeddingSessionsBackfilledTotal": progress["embeddingSessionsBackfilled"],
            "embeddingBlocksBackfilledTotal": progress["embeddingBlocksBackfilled"],
            "completed": completed,
            "checkpoint": checkpoint,
            "warnings": warnings,
            "generatedAt": _now(),
        }
        payload["operatorGuidance"] = session_intelligence_backfill_operator_guidance(payload)
        return payload


def _embedding_row_content(row: dict[str, Any]) -> str:
    content = str(row.get("content") or "").strip()
    if content:
        return content
    tool_name = str(row.get("toolName") or "").strip()
    if tool_name:
        return f"[tool] {tool_name}"
    return ""


def _embedding_block(block_kind: str, block_index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    message_ids = [str(row.get("messageId") or f"message-{idx}") for idx, row in enumerate(rows)]
    content = "\n".join(
        f"{str(row.get('role') or 'unknown').strip()}: {_embedding_row_content(row)}"
        for row in rows
    ).strip()
    metadata = {
        "sourceProvenance": [str(row.get("sourceProvenance") or "") for row in rows],
        "roles": [str(row.get("role") or "") for row in rows],
        "messageTypes": [str(row.get("messageType") or "") for row in rows],
        "messageIndexes": [int(row.get("messageIndex") or 0) for row in rows],
    }
    content_hash = hashlib.sha256(
        json.dumps(
            {
                "blockKind": block_kind,
                "blockIndex": block_index,
                "messageIds": message_ids,
                "content": content,
                "metadata": metadata,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "block_kind": block_kind,
        "block_index": block_index,
        "message_ids": message_ids,
        "content": content,
        "content_hash": content_hash,
        "embedding_model": "",
        "embedding_dimensions": 0,
        "metadata_json": metadata,
    }


async def _linked_documents(document_repo: Any, project_id: str, session_row: dict[str, Any]) -> list[dict[str, Any]]:
    feature_id = _feature_id(session_row)
    if not feature_id:
        return []
    return await document_repo.list_paginated(
        project_id,
        0,
        200,
        filters={"feature": feature_id, "include_progress": True},
    )


async def _replace_session_intelligence_facts(
    intelligence_repo: Any,
    session_id: str,
    session_row: dict[str, Any],
    canonical_rows: list[dict[str, Any]],
    file_updates: list[dict[str, Any]],
    linked_docs: list[dict[str, Any]],
) -> None:
    sentiment_facts = build_session_sentiment_facts(session_row, canonical_rows)
    churn_facts = build_session_code_churn_facts(session_row, canonical_rows, file_updates)
    scope_drift_facts = build_session_scope_drift_facts(session_row, linked_docs, file_updates)
    await intelligence_repo.replace_session_sentiment_facts(session_id, sentiment_facts)
    await intelligence_repo.replace_session_code_churn_facts(session_id, churn_facts)
    await intelligence_repo.replace_session_scope_drift_facts(session_id, scope_drift_facts)


def _normalize_canonical_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raw_metadata = row.get("metadata_json")
            if isinstance(raw_metadata, str) and raw_metadata.strip():
                try:
                    parsed = json.loads(raw_metadata)
                except Exception:
                    parsed = {}
                metadata = parsed if isinstance(parsed, dict) else {}
            else:
                metadata = {}
        normalized.append(
            {
                "messageIndex": int(row.get("message_index") or row.get("messageIndex") or 0),
                "sourceLogId": str(row.get("source_log_id") or row.get("sourceLogId") or ""),
                "messageId": str(row.get("message_id") or row.get("messageId") or ""),
                "role": str(row.get("role") or ""),
                "messageType": str(row.get("message_type") or row.get("messageType") or ""),
                "content": str(row.get("content") or ""),
                "timestamp": str(row.get("event_timestamp") or row.get("timestamp") or ""),
                "agentName": str(row.get("agent_name") or row.get("agentName") or ""),
                "toolName": str(row.get("tool_name") or row.get("toolName") or ""),
                "rootSessionId": str(row.get("root_session_id") or row.get("rootSessionId") or ""),
                "conversationFamilyId": str(row.get("conversation_family_id") or row.get("conversationFamilyId") or ""),
                "threadSessionId": str(row.get("thread_session_id") or row.get("threadSessionId") or ""),
                "parentSessionId": str(row.get("parent_session_id") or row.get("parentSessionId") or ""),
                "sourceProvenance": str(row.get("source_provenance") or row.get("sourceProvenance") or ""),
                "metadata": metadata,
            }
        )
    return normalized


def _session_cursor_value(session_row: dict[str, Any]) -> str:
    return str(session_row.get("started_at") or session_row.get("startedAt") or session_row.get("created_at") or "")


def _build_backfill_checkpoint(
    *,
    checkpoint_key: str,
    last_started_at: str,
    last_session_id: str,
    completed: bool,
    progress: dict[str, int],
) -> dict[str, Any]:
    return {
        "checkpointKey": checkpoint_key,
        "version": 1,
        "lastStartedAt": last_started_at,
        "lastSessionId": last_session_id,
        "sessionsProcessed": int(progress.get("sessionsProcessed") or 0),
        "transcriptSessionsBackfilled": int(progress.get("transcriptSessionsBackfilled") or 0),
        "derivedFactSessionsBackfilled": int(progress.get("derivedFactSessionsBackfilled") or 0),
        "embeddingSessionsBackfilled": int(progress.get("embeddingSessionsBackfilled") or 0),
        "embeddingBlocksBackfilled": int(progress.get("embeddingBlocksBackfilled") or 0),
        "completed": bool(completed),
        "updatedAt": _now(),
    }


class TranscriptSearchService:
    async def search(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        query: str,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> SessionSemanticSearchResponse:
        project = resolve_project(context, ports)
        if project is None or not query.strip():
            return SessionSemanticSearchResponse(
                query=query,
                offset=offset,
                limit=limit,
                capability=SessionIntelligenceCapability(
                    supported=True,
                    authoritative=False,
                    storageProfile="unknown",
                    searchMode="canonical_lexical",
                    detail="Canonical transcript search is unavailable.",
                ),
            )

        rows = await ports.storage.session_messages().search_messages(
            project.id,
            query,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            session_id=session_id,
            limit=max(limit + offset, limit),
        )
        if root_session_id:
            rows = [row for row in rows if str(row.get("root_session_id") or "") == root_session_id]
        matches = [_search_match_from_row(row, query) for row in rows]
        matches.sort(key=lambda item: (-item.score, item.sessionId, item.blockIndex))
        paged_matches = matches[offset : offset + limit]
        return SessionSemanticSearchResponse(
            query=query,
            total=len(matches),
            offset=offset,
            limit=limit,
            capability=SessionIntelligenceCapability(
                supported=True,
                authoritative=False,
                storageProfile=str(getattr(ports.storage.session_embeddings().describe_capability(), "storage_profile", "")),
                searchMode="canonical_lexical",
                detail="Canonical transcript rows are ranked lexically from session_messages.",
            ),
            items=paged_matches,
        )


class SessionIntelligenceReadService:
    async def list_sessions(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str | None = None,
        conversation_family_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        include_subagents: bool = True,
        offset: int = 0,
        limit: int = 20,
    ) -> SessionIntelligenceListResponse:
        if session_id:
            return await SessionIntelligenceQueryService().list_rollups(
                context,
                ports,
                session_id=session_id,
                offset=offset,
                limit=limit,
            )
        return await SessionIntelligenceQueryService().list_session_intelligence(
            context,
            ports,
            feature_id=feature_id,
            conversation_family_id=conversation_family_id,
            root_session_id=root_session_id,
            offset=offset,
            limit=limit,
            include_subagents=include_subagents,
        )

    async def get_session_detail(
        self,
        context: RequestContext,
        ports: CorePorts,
        session_id: str,
    ) -> Optional[SessionIntelligenceDetailResponse]:
        return await SessionIntelligenceQueryService().get_session_intelligence_detail(
            context,
            ports,
            session_id=session_id,
        )

    async def drilldown(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        concern: str,
        feature_id: str | None = None,
        root_session_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Optional[SessionIntelligenceDrilldownResponse]:
        if not session_id:
            return await SessionIntelligenceQueryService().list_drilldown(
                context,
                ports,
                concern=concern,
                feature_id=feature_id,
                root_session_id=root_session_id,
                offset=offset,
                limit=limit,
            )
        detail = await self.get_session_detail(context, ports, session_id)
        if detail is None:
            return None

        items: list[SessionIntelligenceDrilldownItem] = []
        if concern == "sentiment":
            items = [
                SessionIntelligenceDrilldownItem(
                    concern="sentiment",
                    sessionId=fact.sessionId,
                    featureId=fact.featureId,
                    rootSessionId=fact.rootSessionId,
                    label=fact.sentimentLabel,
                    score=fact.sentimentScore,
                    confidence=fact.confidence,
                    messageIndex=fact.messageIndex,
                    sourceMessageId=fact.sourceMessageId,
                    sourceLogId=fact.sourceLogId,
                    evidence=fact.evidence,
                )
                for fact in detail.sentimentFacts
            ]
        elif concern == "churn":
            items = [
                SessionIntelligenceDrilldownItem(
                    concern="churn",
                    sessionId=fact.sessionId,
                    featureId=fact.featureId,
                    rootSessionId=fact.rootSessionId,
                    label="low_progress_loop" if fact.lowProgressLoop else "iterative",
                    score=fact.churnScore,
                    confidence=fact.confidence,
                    messageIndex=fact.lastMessageIndex,
                    sourceLogId=fact.lastSourceLogId,
                    filePath=fact.filePath,
                    evidence=fact.evidence,
                )
                for fact in detail.churnFacts
            ]
        elif concern == "scope_drift":
            items = [
                SessionIntelligenceDrilldownItem(
                    concern="scope_drift",
                    sessionId=fact.sessionId,
                    featureId=fact.featureId,
                    rootSessionId=fact.rootSessionId,
                    label="out_of_scope" if fact.outOfScopePathCount > 0 else "in_scope",
                    score=fact.driftRatio,
                    confidence=fact.confidence,
                    evidence=fact.evidence,
                )
                for fact in detail.scopeDriftFacts
            ]
        else:
            return None

        return SessionIntelligenceDrilldownResponse(
            concern=concern,
            generatedAt=_now(),
            total=len(items),
            offset=offset,
            limit=limit,
            items=items[offset : offset + limit],
        )


__all__ = [
    "SessionIntelligenceQueryService",
    "SessionIntelligenceReadService",
    "TranscriptSearchService",
]
