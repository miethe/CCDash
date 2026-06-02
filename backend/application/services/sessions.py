"""Application services for session read paths."""
from __future__ import annotations

import json
import logging

import backend.config as config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_model_identity
from backend.session_badges import derive_session_badges
from backend.services.session_transcript_contract import (
    canonical_source_provenance,
    compatibility_speaker_from_role,
)

from backend.application.services.common import resolve_project

logger = logging.getLogger("ccdash.services.sessions")


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
        *,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        """Return session log entries, canonical-first.

        session_messages is always the authoritative source and is queried
        first.  When DROP_SESSION_LOGS_ENABLED is True the legacy session_logs
        fallback is skipped entirely — this is the read-path gate that allows
        the migration agent to safely issue the DROP TABLE.  When the flag is
        False (default) the legacy fallback is preserved for back-compat.

        NOTE: The actual data backfill (un-projected session_logs rows →
        session_messages) is the migration agent's responsibility (P1-002 DDL
        half).  This service only governs the READ path.
        """
        session_id = str(session_row.get("id") or "")
        safe_limit = max(1, min(int(limit or 5000), 5001))
        safe_offset = max(0, int(offset or 0))
        try:
            canonical_rows = await ports.storage.session_messages().list_by_session(
                session_id,
                limit=safe_limit,
                offset=safe_offset,
            )
        except TypeError:
            canonical_rows = await ports.storage.session_messages().list_by_session(session_id)
            canonical_rows = canonical_rows[safe_offset:safe_offset + safe_limit]

        if canonical_rows:
            return [self._canonical_log_payload(row) for row in canonical_rows]

        # --- legacy session_logs fallback ---
        # Skipped when DROP_SESSION_LOGS_ENABLED=true so the migration agent
        # can safely DROP session_logs without any reader depending on it.
        if getattr(config, "DROP_SESSION_LOGS_ENABLED", False):
            # Flag is ON: session_logs is being staged for removal; return
            # the empty canonical result rather than touching the legacy table.
            return []

        try:
            raw_logs = await ports.storage.sessions().get_logs(
                session_id,
                limit=safe_limit,
                offset=safe_offset,
            )
        except TypeError:
            raw_logs = await ports.storage.sessions().get_logs(session_id)
            raw_logs = raw_logs[safe_offset:safe_offset + safe_limit]
        return [self._legacy_log_payload(row) for row in raw_logs]

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

        # Build tokenUsage from dedicated columns first; fall back to metadata for
        # rows written before the per-message token migration.
        token_usage: dict[str, int] | None = None
        _in = row.get("input_tokens")
        _out = row.get("output_tokens")
        if isinstance(_in, (int, float)) and isinstance(_out, (int, float)):
            _cr = row.get("cache_read_input_tokens")
            _cc = row.get("cache_creation_input_tokens")
            token_usage = {
                "inputTokens": int(_in),
                "outputTokens": int(_out),
                "cacheReadInputTokens": int(_cr) if isinstance(_cr, (int, float)) else 0,
                "cacheCreationInputTokens": int(_cc) if isinstance(_cc, (int, float)) else 0,
            }
        elif isinstance(metadata.get("inputTokens"), (int, float)) and isinstance(metadata.get("outputTokens"), (int, float)):
            # Legacy rows: token data stored only in metadata_json (pre-migration).
            _m_in = metadata.get("inputTokens")
            _m_out = metadata.get("outputTokens")
            _m_cr = metadata.get("cache_read_input_tokens")
            _m_cc = metadata.get("cache_creation_input_tokens")
            token_usage = {
                "inputTokens": int(_m_in),  # type: ignore[arg-type]
                "outputTokens": int(_m_out),  # type: ignore[arg-type]
                "cacheReadInputTokens": int(_m_cr) if isinstance(_m_cr, (int, float)) else 0,
                "cacheCreationInputTokens": int(_m_cc) if isinstance(_m_cc, (int, float)) else 0,
            }

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
            "tokenUsage": token_usage,
            "toolCall": self._tool_call_payload(
                name=row.get("tool_name"),
                tool_call_id=row.get("tool_call_id"),
                args=metadata.get("toolArgs"),
                output=metadata.get("toolOutput"),
                status=metadata.get("toolStatus"),
            ),
        }

    # ── Badge computation & persistence ──────────────────────────────────

    @staticmethod
    def _derive_command_slug(logs: list[dict[str, object]]) -> str:
        """Return the first command-type log's content as the session command slug."""
        for log in logs:
            if str(log.get("type") or "").strip().lower() == "command":
                name = str(log.get("content") or "").strip()
                if name:
                    return name
        return ""

    @staticmethod
    def _derive_latest_summary(logs: list[dict[str, object]]) -> str:
        """Return the last system/summary event's content as latest_summary."""
        latest = ""
        for log in logs:
            if str(log.get("type") or "").strip().lower() != "system":
                continue
            meta = log.get("metadata") or {}
            if not isinstance(meta, dict):
                try:
                    meta = json.loads(str(meta)) if meta else {}
                except Exception:
                    meta = {}
            if str(meta.get("eventType") or "").strip().lower() == "summary":
                text = str(log.get("content") or "").strip()
                if text:
                    latest = text
        return latest

    async def compute_and_persist_badges(
        self,
        session_row: dict[str, object],
        ports: CorePorts,
    ) -> dict[str, object]:
        """Compute badge values from logs and persist them to the sessions row.

        Returns the computed badge dict (same shape as derive_session_badges).
        This is the integration point for sync_engine.py to call after session
        messages are written.  The method is self-contained: it fetches logs,
        derives badges, and persists in one operation.

        Integration note for sync_engine (NOT owned by this agent):
            After writing session messages for a session, call:
                await session_transcript_service.compute_and_persist_badges(
                    session_row, ports
                )
            where session_transcript_service is an instance of SessionTranscriptService.
        """
        session_id = str(session_row.get("id") or "")
        if not session_id:
            return {"modelsUsed": [], "agentsUsed": [], "skillsUsed": [], "toolSummary": []}

        logs = await self.list_session_logs(session_row, ports)
        badge_data = derive_session_badges(
            logs,
            primary_model=str(session_row.get("model") or ""),
            session_agent_id=session_row.get("agent_id"),
        )

        command_slug = self._derive_command_slug(logs)
        latest_summary = self._derive_latest_summary(logs)

        # subagent_type is not derived here (needs parent-log context which
        # requires session_type — the caller in api.py handles that separately).
        # We persist what we can derive from this session's own logs.
        subagent_type = ""

        try:
            repo = ports.storage.sessions()
            _badge_project_id = str(session_row.get("project_id") or "")
            await repo.update_session_badges(
                session_id,
                command_slug=command_slug,
                latest_summary=latest_summary,
                subagent_type=subagent_type,
                models_used=badge_data["modelsUsed"],
                agents_used=badge_data["agentsUsed"],
                skills_used=badge_data["skillsUsed"],
                project_id=_badge_project_id,
            )
        except Exception:
            logger.warning(
                "compute_and_persist_badges: failed to persist badges for session_id=%r",
                session_id,
                exc_info=True,
            )

        return badge_data

    async def backfill_session_badges(
        self,
        session_id: str,
        ports: CorePorts,
    ) -> dict[str, object]:
        """Backfill badges for a single session by id.

        Fetches the session row, computes badges from logs, persists them.
        Returns the computed badge dict.  Safe to call multiple times (idempotent).
        """
        repo = ports.storage.sessions()
        session_row = await repo.get_by_id(session_id)
        if not session_row:
            logger.warning("backfill_session_badges: session_id=%r not found", session_id)
            return {"modelsUsed": [], "agentsUsed": [], "skillsUsed": [], "toolSummary": []}
        return await self.compute_and_persist_badges(session_row, ports)

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
