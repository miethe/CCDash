"""Application services for session read paths."""
from __future__ import annotations

import json

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_model_identity
from backend.services.session_transcript_contract import (
    canonical_source_provenance,
    compatibility_speaker_from_role,
)

from backend.application.services.common import resolve_project


class SessionFacetService:
    async def get_model_facets(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        include_subagents: bool = True,
    ) -> list[dict[str, str | int]]:
        project = resolve_project(context, ports)
        if project is None:
            return []

        rows = await ports.storage.sessions().get_model_facets(
            project.id,
            include_subagents=include_subagents,
        )
        items: list[dict[str, str | int]] = []
        for row in rows:
            raw_model = str(row.get("model") or "")
            identity = derive_model_identity(raw_model)
            items.append(
                {
                    "raw": raw_model,
                    "modelDisplayName": identity["modelDisplayName"],
                    "modelProvider": identity["modelProvider"],
                    "modelFamily": identity["modelFamily"],
                    "modelVersion": identity["modelVersion"],
                    "count": int(row.get("count") or 0),
                }
            )
        return items

    async def get_platform_facets(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        include_subagents: bool = True,
    ) -> list[dict[str, str | int]]:
        project = resolve_project(context, ports)
        if project is None:
            return []

        rows = await ports.storage.sessions().get_platform_facets(
            project.id,
            include_subagents=include_subagents,
        )
        return [
            {
                "platformType": str(row.get("platform_type") or "Claude Code").strip() or "Claude Code",
                "platformVersion": str(row.get("platform_version") or "").strip(),
                "count": int(row.get("count") or 0),
            }
            for row in rows
        ]


def _safe_json(raw: str | dict | None) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class SessionTranscriptService:
    async def list_session_logs(
        self,
        session_row: dict[str, object],
        ports: CorePorts,
    ) -> list[dict[str, object]]:
        session_id = str(session_row.get("id") or "")
        canonical_rows = await ports.storage.session_messages().list_by_session(session_id)
        if not canonical_rows:
            raw_logs = await ports.storage.sessions().get_logs(session_id)
            return [self._legacy_log_payload(row) for row in raw_logs]
        return [self._canonical_log_payload(row) for row in canonical_rows]

    def _legacy_log_payload(self, row: dict[str, object]) -> dict[str, object]:
        metadata = _safe_json(row.get("metadata_json"))
        return {
            "id": row.get("source_log_id") or f"log-{row.get('log_index', 0)}",
            "timestamp": row.get("timestamp", ""),
            "speaker": row.get("speaker", ""),
            "type": row.get("type", ""),
            "content": row.get("content", ""),
            "agentName": row.get("agent_name"),
            "linkedSessionId": row.get("linked_session_id"),
            "relatedToolCallId": row.get("related_tool_call_id"),
            "metadata": metadata,
            "toolCall": self._tool_call_payload(
                name=row.get("tool_name"),
                tool_call_id=row.get("tool_call_id"),
                args=row.get("tool_args"),
                output=row.get("tool_output"),
                status=row.get("tool_status"),
            ),
        }

    def _canonical_log_payload(self, row: dict[str, object]) -> dict[str, object]:
        metadata = _safe_json(row.get("metadata_json"))
        metadata.setdefault("sourceProvenance", canonical_source_provenance(row, metadata))
        if row.get("entry_uuid"):
            metadata.setdefault("entryUuid", row.get("entry_uuid"))
        if row.get("parent_entry_uuid"):
            metadata.setdefault("parentUuid", row.get("parent_entry_uuid"))
        if row.get("message_id"):
            metadata.setdefault("rawMessageId", row.get("message_id"))
        return {
            "id": row.get("source_log_id") or f"log-{row.get('message_index', 0)}",
            "timestamp": row.get("event_timestamp", ""),
            "speaker": compatibility_speaker_from_role(row.get("role")),
            "type": row.get("message_type", ""),
            "content": row.get("content", ""),
            "agentName": row.get("agent_name"),
            "linkedSessionId": row.get("linked_session_id"),
            "relatedToolCallId": row.get("related_tool_call_id"),
            "metadata": metadata,
            "toolCall": self._tool_call_payload(
                name=row.get("tool_name"),
                tool_call_id=row.get("tool_call_id"),
                args=metadata.get("toolArgs"),
                output=metadata.get("toolOutput"),
                status=metadata.get("toolStatus"),
            ),
        }

    def _tool_call_payload(
        self,
        *,
        name: object,
        tool_call_id: object,
        args: object,
        output: object,
        status: object,
    ) -> dict[str, object] | None:
        if not any(value not in (None, "") for value in (name, tool_call_id, args, output, status)):
            return None
        resolved_status = str(status or "success")
        return {
            "id": tool_call_id,
            "name": name,
            "args": args or "",
            "output": output,
            "status": resolved_status,
            "isError": resolved_status == "error",
        }
