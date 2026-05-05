"""Shared persistence service for normalized session ingestion."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Awaitable, Callable

from backend import observability
from backend.db.repositories.base import SessionMessageRepository, SessionRepository
from backend.ingestion.models import MergePolicy, NormalizedSessionEnvelope, SessionIngestResult

logger = logging.getLogger("ccdash.ingestion.session")

SessionProjector = Callable[[dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]]
ApplyUsageFields = Callable[[dict[str, Any]], dict[str, int]]
ShouldWriteLegacyLogs = Callable[[list[dict[str, Any]]], bool]
DeriveObservabilityFields = Callable[
    [str, dict[str, Any], list[dict[str, Any]]],
    Awaitable[dict[str, Any]],
]
ReplaceUsageAttribution = Callable[
    [str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    Awaitable[Any],
]
ReplaceTelemetryEvents = Callable[
    [
        str,
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ],
    Awaitable[Any],
]
ReplaceCommitCorrelations = Callable[
    [str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    Awaitable[Any],
]
ReplaceIntelligenceFacts = Callable[
    [str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    Awaitable[Any],
]
MaybeEnqueueTelemetryExport = Callable[[str, dict[str, Any]], Awaitable[None]]
PublishTranscriptAppends = Callable[
    [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    Awaitable[bool],
]
PublishSessionSnapshot = Callable[[dict[str, Any], int, str], Awaitable[None]]


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


def _first_non_empty(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        raw = str(value).strip()
        if raw:
            return raw
    return default


class SessionIngestService:
    """Persist normalized session envelopes into canonical CCDash session rows."""

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        session_message_repo: SessionMessageRepository,
        project_session_messages: SessionProjector,
        apply_usage_fields: ApplyUsageFields,
        should_write_legacy_session_logs: ShouldWriteLegacyLogs,
        derive_session_observability_fields: DeriveObservabilityFields,
        replace_session_usage_attribution: ReplaceUsageAttribution,
        replace_session_telemetry_events: ReplaceTelemetryEvents,
        replace_session_commit_correlations: ReplaceCommitCorrelations,
        replace_session_intelligence_facts: ReplaceIntelligenceFacts,
        maybe_enqueue_telemetry_export: MaybeEnqueueTelemetryExport,
        publish_transcript_appends: PublishTranscriptAppends,
        publish_session_snapshot: PublishSessionSnapshot,
    ) -> None:
        self.session_repo = session_repo
        self.session_message_repo = session_message_repo
        self.project_session_messages = project_session_messages
        self.apply_usage_fields = apply_usage_fields
        self.should_write_legacy_session_logs = should_write_legacy_session_logs
        self.derive_session_observability_fields = derive_session_observability_fields
        self.replace_session_usage_attribution = replace_session_usage_attribution
        self.replace_session_telemetry_events = replace_session_telemetry_events
        self.replace_session_commit_correlations = replace_session_commit_correlations
        self.replace_session_intelligence_facts = replace_session_intelligence_facts
        self.maybe_enqueue_telemetry_export = maybe_enqueue_telemetry_export
        self.publish_transcript_appends = publish_transcript_appends
        self.publish_session_snapshot = publish_session_snapshot

    async def persist_envelope(
        self,
        project_id: str,
        envelope: NormalizedSessionEnvelope,
        *,
        observed_source_file: str = "",
        telemetry_source: str = "sync",
    ) -> SessionIngestResult:
        """Persist a complete session envelope and return write counts."""
        if envelope.merge_policy != MergePolicy.UPSERT_COMPLETE:
            return SessionIngestResult(
                source=envelope.source,
                merge_policy=envelope.merge_policy,
                accepted=False,
                warnings=[f"unsupported merge policy: {envelope.merge_policy.value}"],
                warning_count=1,
            )

        source_file = envelope.source_identity
        observed_source = observed_source_file or envelope.provenance.source_uri or source_file
        all_relationships: list[dict[str, Any]] = []
        pending_sessions: list[dict[str, Any]] = []

        def _collect_session_payload(payload: dict[str, Any]) -> None:
            session_payload = dict(payload)
            derived_sessions = session_payload.pop("derivedSessions", [])
            relationship_rows = session_payload.pop("sessionRelationships", [])
            if isinstance(relationship_rows, list):
                for row in relationship_rows:
                    if isinstance(row, dict):
                        all_relationships.append(dict(row))

            session_payload["sourceFile"] = source_file
            session_forensics = session_payload.get("sessionForensics")
            if not isinstance(session_forensics, dict):
                session_forensics = {}
            session_forensics.setdefault("observedSourceFile", observed_source)
            session_payload["sessionForensics"] = session_forensics
            self.apply_usage_fields(session_payload)
            pending_sessions.append(session_payload)

            if isinstance(derived_sessions, list):
                for derived in derived_sessions:
                    if isinstance(derived, dict):
                        _collect_session_payload(derived)

        if envelope.session:
            _collect_session_payload(envelope.session)

        result = SessionIngestResult(
            source=envelope.source,
            merge_policy=envelope.merge_policy,
        )

        for session_dict in pending_sessions:
            session_id = str(session_dict.get("id") or "").strip()
            if not session_id:
                continue

            await self.session_repo.upsert(session_dict, project_id)
            result.session_ids.append(session_id)
            result.updated_session_ids.append(session_id)

            logs = session_dict.get("logs", [])
            if not isinstance(logs, list):
                logs = []
            canonical_rows = self.project_session_messages(session_dict, logs)
            result.message_count += len(canonical_rows)
            result.log_count += len(logs)

            write_legacy_logs = self.should_write_legacy_session_logs(canonical_rows)
            if write_legacy_logs:
                previous_logs = await self.session_repo.get_logs(session_id)
                await self.session_repo.upsert_logs(session_id, logs)
            else:
                previous_logs = await self.session_message_repo.list_by_session(session_id)
                await self.session_repo.upsert_logs(session_id, [])
            await self.session_message_repo.replace_session_messages(session_id, canonical_rows)

            tools = session_dict.get("toolsUsed", [])
            if not isinstance(tools, list):
                tools = []
            await self.session_repo.upsert_tool_usage(session_id, tools)

            files = session_dict.get("updatedFiles", [])
            if not isinstance(files, list):
                files = []
            await self.session_repo.upsert_file_updates(session_id, files)

            artifacts = session_dict.get("linkedArtifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
            await self.session_repo.upsert_artifacts(session_id, artifacts)
            await self.session_repo.update_observability_fields(
                session_id,
                await self.derive_session_observability_fields(project_id, session_dict, logs),
            )

            await self.replace_session_usage_attribution(project_id, session_dict, logs, artifacts)
            await self.replace_session_telemetry_events(project_id, session_dict, logs, tools, files, artifacts)
            await self.replace_session_commit_correlations(project_id, session_dict, logs, files)
            await self.replace_session_intelligence_facts(project_id, session_dict, canonical_rows, files)
            await self.maybe_enqueue_telemetry_export(project_id, session_dict)
            append_published = await self.publish_transcript_appends(session_dict, previous_logs, logs)
            await self.publish_session_snapshot(session_dict, len(logs), telemetry_source)
            if not append_published and logs:
                logger.debug(
                    "session transcript append fallback to invalidation",
                    extra={
                        "session_id": session_id,
                        "project_id": project_id,
                        "log_count": len(logs),
                    },
                )

            self._record_session_observability(project_id, session_dict, tools)

        deduped_relationships = self._dedupe_relationships(project_id, all_relationships)
        if deduped_relationships:
            await self.session_repo.upsert_relationships(
                project_id,
                source_file,
                list(deduped_relationships.values()),
            )
        result.relationship_count = len(deduped_relationships)
        return result

    def _dedupe_relationships(
        self,
        project_id: str,
        relationships: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for relationship in relationships:
            parent_session_id = str(relationship.get("parentSessionId") or "").strip()
            child_session_id = str(relationship.get("childSessionId") or "").strip()
            relationship_type = str(relationship.get("relationshipType") or "").strip()
            if not parent_session_id or not child_session_id or not relationship_type:
                continue
            rel_id = str(relationship.get("id") or "").strip()
            if not rel_id:
                signature = "::".join(
                    [
                        project_id,
                        parent_session_id,
                        child_session_id,
                        relationship_type,
                        str(relationship.get("parentEntryUuid") or "").strip(),
                        str(relationship.get("childEntryUuid") or "").strip(),
                    ]
                )
                rel_id = f"REL-{hashlib.sha1(signature.encode('utf-8')).hexdigest()[:20]}"
                relationship["id"] = rel_id
            deduped[rel_id] = relationship
        return deduped

    def _record_session_observability(
        self,
        project_id: str,
        session_dict: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> None:
        model = _first_non_empty(session_dict, "model")
        feature_id = _first_non_empty(session_dict, "featureId", "feature_id")
        observability.record_token_cost(
            project_id=project_id,
            model=model,
            feature_id=feature_id,
            token_input=_coerce_int(session_dict.get("tokensIn") or session_dict.get("tokens_in")),
            token_output=_coerce_int(session_dict.get("tokensOut") or session_dict.get("tokens_out")),
            cost_usd=_coerce_float(session_dict.get("totalCost") or session_dict.get("total_cost")),
        )
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_name = _first_non_empty(tool, "name", "tool_name", default="unknown")
            call_count = _coerce_int(tool.get("count") or tool.get("call_count"))
            if call_count <= 0:
                continue
            success_count = _coerce_int(tool.get("success_count"))
            success_rate = _coerce_float(tool.get("successRate"))
            if success_count <= 0 and success_rate > 0:
                ratio = success_rate / 100.0 if success_rate > 1 else success_rate
                success_count = int(round(call_count * max(0.0, min(1.0, ratio))))
            success_count = max(0, min(call_count, success_count))
            failure_count = max(0, call_count - success_count)
            duration_ms = _coerce_float(tool.get("totalMs") or tool.get("total_ms"))
            if success_count > 0:
                observability.record_tool_result(
                    tool_name,
                    "success",
                    project_id=project_id,
                    count=success_count,
                    duration_ms=duration_ms,
                )
            if failure_count > 0:
                observability.record_tool_result(
                    tool_name,
                    "failure",
                    project_id=project_id,
                    count=failure_count,
                    duration_ms=duration_ms,
                )
