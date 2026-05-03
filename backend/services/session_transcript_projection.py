"""Projection helpers for canonical session transcript storage."""
from __future__ import annotations

from typing import Any

from backend.services.session_transcript_contract import (
    canonical_message_id,
    canonical_message_type_from_log,
    canonical_role_from_log,
    canonical_source_provenance,
)


def project_session_messages(
    session_row: dict[str, Any],
    logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    session_id = str(session_row.get("id") or "")
    root_session_id = str(session_row.get("rootSessionId") or session_row.get("root_session_id") or session_id)
    conversation_family_id = str(
        session_row.get("conversationFamilyId")
        or session_row.get("conversation_family_id")
        or root_session_id
        or session_id
    )
    parent_session_id = str(session_row.get("parentSessionId") or session_row.get("parent_session_id") or "")

    projected: list[dict[str, Any]] = []
    for index, log in enumerate(logs):
        metadata = log.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        tool_call = log.get("toolCall")
        tool_name = None
        tool_call_id = None
        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name")
            tool_call_id = tool_call.get("id")
            if tool_call.get("args") not in (None, ""):
                metadata.setdefault("toolArgs", tool_call.get("args"))
            if tool_call.get("output") not in (None, ""):
                metadata.setdefault("toolOutput", tool_call.get("output"))
            if tool_call.get("status") not in (None, ""):
                metadata.setdefault("toolStatus", tool_call.get("status"))

        source_log_id = str(log.get("id") or f"log-{index}")
        source_provenance = canonical_source_provenance(session_row, metadata)
        metadata.setdefault("sourceProvenance", source_provenance)
        message_id = canonical_message_id(source_log_id, metadata)
        message_type = canonical_message_type_from_log(log, metadata)

        # Extract per-message token usage from metadata (populated by the Claude Code parser).
        # All four fields must be present (at least as 0) for tokenUsage to be non-null;
        # if none are present, tokenUsage is None (no data).
        token_usage: dict[str, int] | None = None
        _in = metadata.get("inputTokens")
        _out = metadata.get("outputTokens")
        _cr = metadata.get("cache_read_input_tokens")
        _cc = metadata.get("cache_creation_input_tokens")
        if isinstance(_in, (int, float)) and isinstance(_out, (int, float)):
            token_usage = {
                "inputTokens": int(_in),
                "outputTokens": int(_out),
                "cacheReadInputTokens": int(_cr) if isinstance(_cr, (int, float)) else 0,
                "cacheCreationInputTokens": int(_cc) if isinstance(_cc, (int, float)) else 0,
            }

        projected.append(
            {
                "messageIndex": index,
                "sourceLogId": source_log_id,
                "messageId": message_id,
                "role": canonical_role_from_log(log, metadata),
                "messageType": message_type,
                "content": str(log.get("content") or ""),
                "timestamp": str(log.get("timestamp") or ""),
                "agentName": str(log.get("agentName") or ""),
                "toolName": tool_name,
                "toolCallId": tool_call_id,
                "relatedToolCallId": log.get("relatedToolCallId"),
                "linkedSessionId": log.get("linkedSessionId"),
                "entryUuid": metadata.get("entryUuid"),
                "parentEntryUuid": metadata.get("parentUuid"),
                "rootSessionId": root_session_id,
                "conversationFamilyId": conversation_family_id,
                "threadSessionId": session_id,
                "parentSessionId": parent_session_id,
                "sourceProvenance": source_provenance,
                "metadata": metadata,
                "tokenUsage": token_usage,
            }
        )
    return projected
