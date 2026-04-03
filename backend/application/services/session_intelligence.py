"""Application services for session intelligence query surfaces."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project
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
