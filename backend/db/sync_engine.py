"""Incremental file → DB sync engine.

Scans filesystem for changed files (mtime-based), parses them using
existing parsers, and upserts the results into the DB cache.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import yaml

from backend import config
from backend.models import Project
from backend.parsers.sessions import parse_session_file
from backend.parsers.documents import parse_document_file
from backend.parsers.progress import parse_progress_file
from backend.parsers.features import scan_features
from backend.document_linking import (
    alias_tokens_from_path,
    canonical_project_path,
    canonical_slug,
    classify_doc_category,
    classify_doc_type,
    extract_frontmatter_references,
    feature_slug_from_path,
    infer_project_root,
    is_generic_alias_token,
    is_generic_phase_progress_slug,
    is_feature_like_token,
    normalize_ref_path,
    slug_from_path,
)
from backend.link_audit import analyze_suspect_links, suspects_as_dicts

from backend.db.factory import (
    get_session_repository,
    get_document_repository,
    get_task_repository,
    get_analytics_repository,
    get_entity_link_repository,
    get_sync_state_repository,
    get_tag_repository,
    get_feature_repository, # Added in factory
)

logger = logging.getLogger("ccdash.sync")

_COMMAND_NAME_TAG_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_TAG_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_NON_CONSEQUENTIAL_COMMAND_PREFIXES = {"/clear", "/model"}
_KEY_WORKFLOW_COMMANDS = (
    "/dev:execute-phase",
    "/recovering-sessions",
    "/dev:quick-feature",
    "/plan:plan-feature",
    "/dev:implement-story",
    "/dev:complete-user-story",
    "/fix:debug",
)
_LINK_STATE_METADATA_KEY = "entity_link_state"
_PULL_REQUEST_RE = re.compile(r"(?:/pull/|/pulls/|#)(\d+)")


def _file_hash(path: Path) -> str:
    """Compute a fast hash of file content for change detection."""
    h = hashlib.md5()
    try:
        h.update(path.read_bytes())
    except Exception:
        return ""
    return h.hexdigest()


def _canonical_task_source(path: Path, progress_dir: Path) -> str:
    """Store task source paths relative to project root for stable linking."""
    project_root = infer_project_root(None, progress_dir)
    return canonical_project_path(path, project_root)


def _task_storage_id(task_id: str, source_file: str) -> str:
    """Create a deterministic DB key for tasks.

    Task IDs in progress files are often reused across features/phases
    (for example, TASK-1.1), so a global PK on raw ID causes collisions.
    """
    raw = f"{source_file}::{task_id}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:20]
    return f"T-{digest}"


def _prepare_task_for_storage(task_dict: dict) -> dict:
    """Convert parser task shape into collision-safe DB row shape."""
    raw_task_id = str(task_dict.get("rawTaskId") or task_dict.get("id") or "").strip()
    source_file = str(task_dict.get("sourceFile") or "").strip()
    if not raw_task_id:
        return task_dict

    if not source_file:
        fallback_scope = f"{task_dict.get('featureId', '')}::{task_dict.get('phaseId', '')}"
        source_file = fallback_scope if fallback_scope != "::" else "unknown"

    task_dict["rawTaskId"] = raw_task_id
    task_dict["id"] = _task_storage_id(raw_task_id, source_file)
    return task_dict


def _normalize_command_label(command_name: str) -> str:
    return " ".join((command_name or "").strip().split())


def _command_token(command_name: str) -> str:
    normalized = _normalize_command_label(command_name).lower()
    if not normalized:
        return ""
    return normalized.split()[0]


def _is_non_consequential_command(command_name: str) -> bool:
    return _command_token(command_name) in _NON_CONSEQUENTIAL_COMMAND_PREFIXES


def _command_priority_rank(command_name: str) -> int:
    lowered = _normalize_command_label(command_name).lower()
    if not lowered:
        return len(_KEY_WORKFLOW_COMMANDS) + 1
    for idx, marker in enumerate(_KEY_WORKFLOW_COMMANDS):
        if marker in lowered:
            return idx
    return len(_KEY_WORKFLOW_COMMANDS)


def _select_linking_commands(command_names: set[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in command_names:
        normalized = _normalize_command_label(raw)
        if not normalized or _is_non_consequential_command(normalized):
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    unique.sort(key=lambda value: (_command_priority_rank(value), value.lower()))
    return unique


def _select_preferred_command_event(command_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    meaningful = [
        event
        for event in command_events
        if isinstance(event, dict) and not _is_non_consequential_command(str(event.get("name") or ""))
    ]
    if not meaningful:
        return None

    for marker in _KEY_WORKFLOW_COMMANDS:
        for event in meaningful:
            command_name = _normalize_command_label(str(event.get("name") or ""))
            if marker in command_name.lower():
                return event
    return meaningful[0]


def _extract_tagged_commands_from_message(content: str) -> list[tuple[str, str]]:
    if not content:
        return []
    command_names = [
        _normalize_command_label(match.group(1))
        for match in _COMMAND_NAME_TAG_PATTERN.finditer(content)
        if _normalize_command_label(match.group(1))
    ]
    if not command_names:
        return []

    command_args = [match.group(1).strip() for match in _COMMAND_ARGS_TAG_PATTERN.finditer(content)]
    pairs: list[tuple[str, str]] = []
    for idx, command_name in enumerate(command_names):
        args_text = command_args[idx] if idx < len(command_args) else ""
        pairs.append((command_name, args_text))
    return pairs


def _pop_matching_tagged_command(
    tagged_commands: list[dict[str, Any]],
    command_name: str,
) -> dict[str, Any] | None:
    token = _command_token(command_name)
    if not token:
        return None
    for idx, tagged in enumerate(tagged_commands):
        if _command_token(str(tagged.get("name") or "")) == token:
            return tagged_commands.pop(idx)
    return None


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


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


def _first_phase(session_payload: dict[str, Any]) -> str:
    metadata = session_payload.get("sessionMetadata")
    if isinstance(metadata, dict):
        related = metadata.get("relatedPhases")
        if isinstance(related, list):
            for phase in related:
                raw = str(phase).strip()
                if raw:
                    return raw
        raw_phase = metadata.get("phase")
        if raw_phase is not None:
            phase = str(raw_phase).strip()
            if phase:
                return phase
    return _first_non_empty(session_payload, "phase")


def _extract_pr_number_from_artifacts(artifacts: list[dict[str, Any]]) -> str:
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        for key in ("url", "source", "title"):
            value = artifact.get(key)
            if value is None:
                continue
            match = _PULL_REQUEST_RE.search(str(value))
            if match:
                return match.group(1)
    return ""


def _build_session_telemetry_events(
    project_id: str,
    session_payload: dict[str, Any],
    logs: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    files: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    *,
    source: str,
) -> list[dict[str, Any]]:
    session_id = _first_non_empty(session_payload, "id")
    if not session_id:
        return []

    root_session_id = _first_non_empty(
        session_payload,
        "rootSessionId",
        "root_session_id",
        default=session_id,
    )
    task_id = _first_non_empty(session_payload, "taskId", "task_id")
    commit_hash = _first_non_empty(session_payload, "gitCommitHash", "git_commit_hash", "commit_hash")
    model = _first_non_empty(session_payload, "model")
    status = _first_non_empty(session_payload, "status")
    occurred_at = _first_non_empty(
        session_payload,
        "startedAt",
        "started_at",
        "createdAt",
        "created_at",
        default=datetime.now(timezone.utc).isoformat(),
    )
    phase = _first_phase(session_payload)
    pr_number = _first_non_empty(session_payload, "prNumber", "pr_number")
    if not pr_number:
        pr_number = _extract_pr_number_from_artifacts(artifacts)

    common = {
        "project_id": project_id,
        "session_id": session_id,
        "root_session_id": root_session_id,
        "feature_id": _first_non_empty(session_payload, "featureId", "feature_id"),
        "task_id": task_id,
        "commit_hash": commit_hash,
        "pr_number": pr_number,
        "phase": phase,
        "model": model,
        "source": source,
    }
    events: list[dict[str, Any]] = []

    def push(
        *,
        source_key: str,
        event_type: str,
        occurred: str,
        payload: dict[str, Any],
        seq: int,
        tool_name: str = "",
        agent: str = "",
        skill: str = "",
        event_status: str = "",
        duration_ms: int = 0,
        token_input: int = 0,
        token_output: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        events.append(
            {
                **common,
                "event_type": event_type,
                "tool_name": tool_name,
                "agent": agent,
                "skill": skill,
                "status": event_status,
                "duration_ms": max(0, duration_ms),
                "token_input": max(0, token_input),
                "token_output": max(0, token_output),
                "cost_usd": max(0.0, cost_usd),
                "occurred_at": occurred or occurred_at,
                "sequence_no": max(0, seq),
                "source_key": source_key,
                "payload_json": json.dumps(payload or {}),
            }
        )

    push(
        source_key=f"session:{session_id}",
        event_type="session.lifecycle",
        occurred=occurred_at,
        payload={
            "durationSeconds": _coerce_int(session_payload.get("durationSeconds") or session_payload.get("duration_seconds")),
            "tokensIn": _coerce_int(session_payload.get("tokensIn") or session_payload.get("tokens_in")),
            "tokensOut": _coerce_int(session_payload.get("tokensOut") or session_payload.get("tokens_out")),
            "totalCost": _coerce_float(session_payload.get("totalCost") or session_payload.get("total_cost")),
            "sessionType": _first_non_empty(session_payload, "sessionType", "session_type"),
        },
        seq=0,
        event_status=status,
        token_input=_coerce_int(session_payload.get("tokensIn") or session_payload.get("tokens_in")),
        token_output=_coerce_int(session_payload.get("tokensOut") or session_payload.get("tokens_out")),
        cost_usd=_coerce_float(session_payload.get("totalCost") or session_payload.get("total_cost")),
    )

    for idx, log in enumerate(logs, start=1):
        metadata = _safe_json_dict(log.get("metadata_json") or log.get("metadata"))
        tool_call = log.get("toolCall") if isinstance(log.get("toolCall"), dict) else {}
        log_type = _first_non_empty(log, "type", default="log")
        tool_name = _first_non_empty(log, "tool_name", "toolName")
        if not tool_name and isinstance(tool_call, dict):
            tool_name = _first_non_empty(tool_call, "name")
        agent = _first_non_empty(log, "agent_name", "agentName")
        tool_status = _first_non_empty(log, "tool_status")
        if not tool_status and isinstance(tool_call, dict):
            tool_status = _first_non_empty(tool_call, "status")
        skill = ""
        if tool_name.lower() == "skill":
            skill = _first_non_empty(metadata, "toolLabel", "skill")
        input_tokens = _coerce_int(
            metadata.get("inputTokens")
            or metadata.get("input_tokens")
            or metadata.get("promptTokens")
            or metadata.get("prompt_tokens")
        )
        output_tokens = _coerce_int(
            metadata.get("outputTokens")
            or metadata.get("output_tokens")
            or metadata.get("completionTokens")
            or metadata.get("completion_tokens")
        )
        duration_ms = _coerce_int(
            metadata.get("durationMs")
            or metadata.get("duration_ms")
            or (tool_call.get("durationMs") if isinstance(tool_call, dict) else 0)
        )
        source_index = log.get("log_index")
        if source_index is None:
            source_index = log.get("logIndex")
        if source_index is None:
            source_index = idx
        timestamp = _first_non_empty(log, "timestamp", default=occurred_at)
        push(
            source_key=f"log:{session_id}:{source_index}",
            event_type=f"log.{log_type}",
            occurred=timestamp,
            payload={
                "speaker": _first_non_empty(log, "speaker"),
                "content": _first_non_empty(log, "content"),
                "metadata": metadata,
            },
            seq=idx,
            tool_name=tool_name,
            agent=agent,
            skill=skill,
            event_status=tool_status or _first_non_empty(log, "status"),
            duration_ms=duration_ms,
            token_input=input_tokens,
            token_output=output_tokens,
        )

    seq_cursor = len(logs) + 1
    for idx, tool in enumerate(tools, start=1):
        tool_name = _first_non_empty(tool, "name", "tool_name", default="unknown")
        count = _coerce_int(tool.get("count") or tool.get("call_count"))
        success_count = _coerce_int(tool.get("success_count"))
        success_rate = _coerce_float(tool.get("successRate"))
        if count > 0 and success_count <= 0 and success_rate > 0:
            success_count = int(round(count * (success_rate / 100 if success_rate > 1 else success_rate)))
        total_ms = _coerce_int(tool.get("totalMs") or tool.get("total_ms"))
        push(
            source_key=f"tool:{session_id}:{tool_name}:{idx}",
            event_type="tool.aggregate",
            occurred=occurred_at,
            payload={
                "callCount": count,
                "successCount": max(0, success_count),
                "successRate": success_rate,
                "totalMs": total_ms,
            },
            seq=seq_cursor,
            tool_name=tool_name,
            event_status="error" if count > 0 and success_count == 0 else "success",
            duration_ms=total_ms,
        )
        seq_cursor += 1

    for idx, update in enumerate(files, start=1):
        file_path = _first_non_empty(update, "filePath", "file_path")
        timestamp = _first_non_empty(update, "timestamp", "action_timestamp", default=occurred_at)
        push(
            source_key=f"file:{session_id}:{file_path}:{idx}",
            event_type="file.update",
            occurred=timestamp,
            payload={
                "filePath": file_path,
                "action": _first_non_empty(update, "action", default="update"),
                "fileType": _first_non_empty(update, "fileType", "file_type"),
                "additions": _coerce_int(update.get("additions")),
                "deletions": _coerce_int(update.get("deletions")),
            },
            seq=seq_cursor,
            tool_name=_first_non_empty(update, "sourceToolName", "source_tool_name"),
            agent=_first_non_empty(update, "agentName", "agent_name"),
            event_status=_first_non_empty(update, "action", default="update"),
        )
        seq_cursor += 1

    for idx, artifact in enumerate(artifacts, start=1):
        artifact_id = _first_non_empty(artifact, "id", default=str(idx))
        push(
            source_key=f"artifact:{session_id}:{artifact_id}:{idx}",
            event_type="artifact.linked",
            occurred=occurred_at,
            payload={
                "title": _first_non_empty(artifact, "title"),
                "type": _first_non_empty(artifact, "type", default="document"),
                "source": _first_non_empty(artifact, "source"),
                "url": _first_non_empty(artifact, "url"),
            },
            seq=seq_cursor,
            tool_name=_first_non_empty(artifact, "sourceToolName", "source_tool_name"),
            event_status=_first_non_empty(artifact, "type", default="document"),
        )
        seq_cursor += 1

    return events


class SyncEngine:
    """Incremental mtime-based file → DB synchronization.

    Uses existing parsers to read files, then upserts parsed data
    into the SQLite/Postgres cache via repositories.
    """

    def __init__(self, db: Any): # db is Union[aiosqlite.Connection, asyncpg.Pool]
        self.db = db
        self.session_repo = get_session_repository(db)
        self.document_repo = get_document_repository(db)
        self.task_repo = get_task_repository(db)
        self.feature_repo = get_feature_repository(db)
        self.link_repo = get_entity_link_repository(db)
        self.sync_repo = get_sync_state_repository(db)
        self.tag_repo = get_tag_repository(db)
        self.analytics_repo = get_analytics_repository(db)
        self._ops_lock = asyncio.Lock()
        self._operations: dict[str, dict[str, Any]] = {}
        self._operation_order: list[str] = []
        self._active_operation_ids: set[str] = set()
        self._max_operation_history = 40
        self._git_doc_dates_cache_key = ""
        self._git_doc_dates_cache_index: dict[str, dict[str, str]] = {}
        self._git_doc_dates_cache_dirty: set[str] = set()
        self._linking_logic_version = str(getattr(config, "LINKING_LOGIC_VERSION", "1")).strip() or "1"

    async def _replace_session_telemetry_events(
        self,
        project_id: str,
        session_payload: dict[str, Any],
        logs: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        files: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
        *,
        source: str,
    ) -> int:
        session_id = _first_non_empty(session_payload, "id")
        if not session_id:
            return 0

        events = _build_session_telemetry_events(
            project_id,
            session_payload,
            logs,
            tools,
            files,
            artifacts,
            source=source,
        )

        if isinstance(self.db, aiosqlite.Connection):
            await self.db.execute(
                "DELETE FROM telemetry_events WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            )
            insert_query = """
                INSERT INTO telemetry_events (
                    project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                    pr_number, phase, event_type, tool_name, model, agent, skill, status,
                    duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                    source, source_key, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            for event in events:
                await self.db.execute(
                    insert_query,
                    (
                        event["project_id"],
                        event["session_id"],
                        event["root_session_id"],
                        event["feature_id"],
                        event["task_id"],
                        event["commit_hash"],
                        event["pr_number"],
                        event["phase"],
                        event["event_type"],
                        event["tool_name"],
                        event["model"],
                        event["agent"],
                        event["skill"],
                        event["status"],
                        event["duration_ms"],
                        event["token_input"],
                        event["token_output"],
                        event["cost_usd"],
                        event["occurred_at"],
                        event["sequence_no"],
                        event["source"],
                        event["source_key"],
                        event["payload_json"],
                    ),
                )
            await self.db.commit()
            return len(events)

        await self.db.execute(
            "DELETE FROM telemetry_events WHERE project_id = $1 AND session_id = $2",
            project_id,
            session_id,
        )
        insert_query = """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20,
                $21, $22, $23
            )
        """
        for event in events:
            await self.db.execute(
                insert_query,
                event["project_id"],
                event["session_id"],
                event["root_session_id"],
                event["feature_id"],
                event["task_id"],
                event["commit_hash"],
                event["pr_number"],
                event["phase"],
                event["event_type"],
                event["tool_name"],
                event["model"],
                event["agent"],
                event["skill"],
                event["status"],
                event["duration_ms"],
                event["token_input"],
                event["token_output"],
                event["cost_usd"],
                event["occurred_at"],
                event["sequence_no"],
                event["source"],
                event["source_key"],
                event["payload_json"],
            )
        return len(events)

    async def _telemetry_event_count(self, project_id: str) -> int:
        if isinstance(self.db, aiosqlite.Connection):
            async with self.db.execute(
                "SELECT COUNT(*) FROM telemetry_events WHERE project_id = ?",
                (project_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0] or 0) if row else 0
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS count FROM telemetry_events WHERE project_id = $1",
            project_id,
        )
        return int(row["count"] or 0) if row else 0

    async def _session_count(self, project_id: str) -> int:
        if isinstance(self.db, aiosqlite.Connection):
            async with self.db.execute(
                "SELECT COUNT(*) FROM sessions WHERE project_id = ?",
                (project_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0] or 0) if row else 0
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS count FROM sessions WHERE project_id = $1",
            project_id,
        )
        return int(row["count"] or 0) if row else 0

    async def _backfill_telemetry_events_for_project(self, project_id: str, batch_size: int = 200) -> dict[str, int]:
        offset = 0
        sessions_backfilled = 0
        events_written = 0

        while True:
            sessions = await self.session_repo.list_paginated(
                offset,
                batch_size,
                project_id,
                sort_by="started_at",
                sort_order="desc",
                filters={"include_subagents": True},
            )
            if not sessions:
                break
            for session in sessions:
                session_id = _first_non_empty(session, "id")
                if not session_id:
                    continue
                logs = await self.session_repo.get_logs(session_id)
                tools = await self.session_repo.get_tool_usage(session_id)
                files = await self.session_repo.get_file_updates(session_id)
                artifacts = await self.session_repo.get_artifacts(session_id)
                events_written += await self._replace_session_telemetry_events(
                    project_id,
                    session,
                    logs,
                    tools,
                    files,
                    artifacts,
                    source="backfill",
                )
                sessions_backfilled += 1
            offset += len(sessions)

        return {"sessions": sessions_backfilled, "events": events_written}

    async def _maybe_backfill_telemetry_events(self, project_id: str) -> dict[str, int]:
        existing_events = await self._telemetry_event_count(project_id)
        if existing_events > 0:
            return {"sessions": 0, "events": 0}
        if await self._session_count(project_id) == 0:
            return {"sessions": 0, "events": 0}
        return await self._backfill_telemetry_events_for_project(project_id)

    async def _delete_tasks_for_feature(self, feature_id: str) -> None:
        """Delete all task rows attached to a feature id."""
        if config.DB_BACKEND == "postgres":
            await self.db.execute("DELETE FROM tasks WHERE feature_id = $1", feature_id)
            return
        await self.db.execute("DELETE FROM tasks WHERE feature_id = ?", (feature_id,))
        await self.db.commit()

    def _to_git_scope(self, project_root: Path, value: Path | str) -> str:
        raw = str(value)
        try:
            path = value if isinstance(value, Path) else Path(raw)
            if path.is_absolute():
                rel = path.resolve().relative_to(project_root.resolve())
                raw = str(rel)
        except Exception:
            pass
        return normalize_ref_path(raw)

    def _build_git_doc_dates(
        self,
        project_root: Path,
        scopes: list[Path | str],
    ) -> tuple[dict[str, dict[str, str]], set[str]]:
        if not project_root.exists():
            return {}, set()

        scope_tokens: list[str] = []
        for scope in scopes:
            token = self._to_git_scope(project_root, scope)
            if token:
                scope_tokens.append(token)
        scope_tokens = sorted(set(scope_tokens))
        if not scope_tokens:
            return {}, set()

        try:
            repo_check = subprocess.run(
                ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=False,
            )
            if repo_check.returncode != 0 or repo_check.stdout.strip().lower() != "true":
                return {}, set()
            head = subprocess.run(
                ["git", "-C", str(project_root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if head.returncode != 0:
                return {}, set()
            head_sha = head.stdout.strip()
        except Exception:
            return {}, set()

        cache_key = f"{project_root.resolve()}::{head_sha}::{'|'.join(scope_tokens)}"
        index: dict[str, dict[str, str]]
        if cache_key == self._git_doc_dates_cache_key:
            index = dict(self._git_doc_dates_cache_index)
        else:
            index = {}
            try:
                log_cmd = [
                    "git",
                    "-C",
                    str(project_root),
                    "log",
                    "--format=%ct",
                    "--name-only",
                    "--date-order",
                    "--",
                    *scope_tokens,
                ]
                result = subprocess.run(log_cmd, capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    current_epoch = ""
                    for raw_line in result.stdout.splitlines():
                        line = raw_line.strip()
                        if not line:
                            continue
                        if line.isdigit():
                            current_epoch = line
                            continue
                        if not current_epoch:
                            continue
                        normalized = normalize_ref_path(line)
                        if not normalized:
                            continue
                        epoch = int(current_epoch)
                        iso = datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
                        row = index.setdefault(normalized, {})
                        if "updatedAt" not in row:
                            row["updatedAt"] = iso
                        row["createdAt"] = iso
            except Exception:
                return {}, set()

            self._git_doc_dates_cache_key = cache_key
            self._git_doc_dates_cache_index = dict(index)

        dirty_paths: set[str] = set()
        try:
            status_cmd = [
                "git",
                "-C",
                str(project_root),
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                *scope_tokens,
            ]
            status_result = subprocess.run(status_cmd, capture_output=True, text=True, check=False)
            if status_result.returncode == 0:
                for raw_line in status_result.stdout.splitlines():
                    line = raw_line.rstrip()
                    if len(line) < 4:
                        continue
                    payload = line[3:].strip()
                    if " -> " in payload:
                        payload = payload.split(" -> ", 1)[1].strip()
                    normalized = normalize_ref_path(payload)
                    if normalized:
                        dirty_paths.add(normalized)
        except Exception:
            dirty_paths = set()

        self._git_doc_dates_cache_dirty = set(dirty_paths)
        return dict(index), set(dirty_paths)

    async def _load_link_state(self, project_id: str) -> dict[str, Any]:
        raw_value: str | None = None
        if isinstance(self.db, aiosqlite.Connection):
            async with self.db.execute(
                """
                SELECT value
                FROM app_metadata
                WHERE entity_type = ? AND entity_id = ? AND key = ?
                LIMIT 1
                """,
                ("project", project_id, _LINK_STATE_METADATA_KEY),
            ) as cur:
                row = await cur.fetchone()
                raw_value = row[0] if row else None
        else:
            row = await self.db.fetchrow(
                """
                SELECT value
                FROM app_metadata
                WHERE entity_type = $1 AND entity_id = $2 AND key = $3
                LIMIT 1
                """,
                "project",
                project_id,
                _LINK_STATE_METADATA_KEY,
            )
            raw_value = row["value"] if row else None

        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def _save_link_state(
        self,
        project_id: str,
        *,
        trigger: str,
        reason: str,
        links_created: int,
    ) -> None:
        payload = json.dumps(
            {
                "logicVersion": self._linking_logic_version,
                "lastRebuildAt": datetime.now(timezone.utc).isoformat(),
                "trigger": trigger,
                "reason": reason,
                "linksCreated": int(links_created),
            }
        )
        if isinstance(self.db, aiosqlite.Connection):
            await self.db.execute(
                """
                INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                ("project", project_id, _LINK_STATE_METADATA_KEY, payload),
            )
            await self.db.commit()
        else:
            await self.db.execute(
                """
                INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
                VALUES ($1, $2, $3, $4, NOW()::text)
                ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                "project",
                project_id,
                _LINK_STATE_METADATA_KEY,
                payload,
            )

    def _is_link_logic_version_stale(self, link_state: dict[str, Any]) -> bool:
        last_version = str(link_state.get("logicVersion") or "").strip()
        return last_version != self._linking_logic_version

    def _should_rebuild_links_after_full_sync(
        self,
        *,
        force: bool,
        link_state: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[bool, str]:
        if force:
            return True, "force"
        if self._is_link_logic_version_stale(link_state):
            return True, "logic_version_changed"
        if any(
            int(stats.get(key, 0)) > 0
            for key in ("sessions_synced", "documents_synced", "tasks_synced", "features_synced")
        ):
            return True, "entities_changed"
        return False, "up_to_date"

    async def start_operation(
        self,
        kind: str,
        project_id: str,
        trigger: str = "api",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create an observable operation and return its ID."""
        return await self._start_operation(kind, project_id, trigger, metadata or {})

    async def list_operations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return latest operation snapshots, newest first."""
        async with self._ops_lock:
            op_ids = self._operation_order[: max(1, limit)]
            return [copy.deepcopy(self._operations[op_id]) for op_id in op_ids if op_id in self._operations]

    async def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        """Return a single operation snapshot."""
        async with self._ops_lock:
            op = self._operations.get(operation_id)
            if not op:
                return None
            return copy.deepcopy(op)

    async def get_observability_snapshot(self) -> dict[str, Any]:
        """Return live sync/linking observability payload for API status."""
        async with self._ops_lock:
            active = [
                copy.deepcopy(self._operations[op_id])
                for op_id in self._operation_order
                if op_id in self._active_operation_ids and op_id in self._operations
            ]
            latest = [
                copy.deepcopy(self._operations[op_id])
                for op_id in self._operation_order[:5]
                if op_id in self._operations
            ]
            return {
                "activeOperationCount": len(active),
                "activeOperations": active,
                "recentOperations": latest,
                "trackedOperationCount": len(self._operations),
            }

    async def _start_operation(
        self,
        kind: str,
        project_id: str,
        trigger: str,
        metadata: dict[str, Any],
    ) -> str:
        op_id = f"OP-{uuid.uuid4()}"
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": op_id,
            "kind": kind,
            "projectId": project_id,
            "trigger": trigger,
            "status": "running",
            "phase": "queued",
            "message": "",
            "startedAt": now,
            "updatedAt": now,
            "finishedAt": "",
            "durationMs": 0,
            "progress": {},
            "counters": {},
            "stats": {},
            "metadata": metadata,
            "error": "",
        }
        async with self._ops_lock:
            self._operations[op_id] = payload
            self._operation_order.insert(0, op_id)
            self._active_operation_ids.add(op_id)
            if len(self._operation_order) > self._max_operation_history:
                stale_ids = self._operation_order[self._max_operation_history :]
                self._operation_order = self._operation_order[: self._max_operation_history]
                for stale_id in stale_ids:
                    self._operations.pop(stale_id, None)
                    self._active_operation_ids.discard(stale_id)
        logger.info("Operation started [%s] %s (project=%s trigger=%s)", op_id, kind, project_id, trigger)
        return op_id

    async def _update_operation(
        self,
        operation_id: str | None,
        *,
        phase: str | None = None,
        message: str | None = None,
        progress: dict[str, Any] | None = None,
        counters: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        if not operation_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        log_needed = False
        log_phase = ""
        log_message = ""
        async with self._ops_lock:
            operation = self._operations.get(operation_id)
            if not operation:
                return
            if phase and phase != operation.get("phase"):
                operation["phase"] = phase
                log_needed = True
                log_phase = phase
            if message is not None:
                operation["message"] = message
                if message:
                    log_needed = True
                    log_message = message
            if progress:
                operation.setdefault("progress", {}).update(progress)
            if counters:
                operation.setdefault("counters", {}).update(counters)
            if stats:
                operation.setdefault("stats", {}).update(stats)
            operation["updatedAt"] = now

        if log_needed:
            if log_message:
                logger.info("Operation update [%s] %s - %s", operation_id, log_phase or "progress", log_message)
            else:
                logger.info("Operation update [%s] %s", operation_id, log_phase)

    async def _finish_operation(
        self,
        operation_id: str | None,
        *,
        status: str,
        stats: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        if not operation_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        async with self._ops_lock:
            operation = self._operations.get(operation_id)
            if not operation:
                return
            operation["status"] = status
            operation["updatedAt"] = now
            operation["finishedAt"] = now
            if stats:
                operation.setdefault("stats", {}).update(stats)
            if error:
                operation["error"] = error
            try:
                started_at = datetime.fromisoformat(str(operation.get("startedAt") or "").replace("Z", "+00:00"))
                finished_at = datetime.fromisoformat(now.replace("Z", "+00:00"))
                operation["durationMs"] = max(
                    0,
                    int((finished_at - started_at).total_seconds() * 1000),
                )
            except Exception:
                operation["durationMs"] = 0
            self._active_operation_ids.discard(operation_id)

        if status == "failed":
            logger.error("Operation failed [%s]: %s", operation_id, error)
        else:
            logger.info("Operation finished [%s] status=%s", operation_id, status)

    async def sync_project(
        self,
        project: Project,
        sessions_dir: Path,
        docs_dir: Path,
        progress_dir: Path,
        force: bool = False,
        operation_id: str | None = None,
        trigger: str = "api",
    ) -> dict:
        """Full incremental sync for a project.

        Returns stats dict with counts of synced entities.
        """
        stats = {
            "sessions_synced": 0,
            "sessions_skipped": 0,
            "telemetry_backfilled_sessions": 0,
            "telemetry_backfilled_events": 0,
            "documents_synced": 0,
            "documents_skipped": 0,
            "tasks_synced": 0,
            "tasks_skipped": 0,
            "features_synced": 0,
            "links_created": 0,
            "duration_ms": 0,
            "operation_id": "",
        }
        if not operation_id:
            operation_id = await self._start_operation(
                "full_sync",
                project.id,
                trigger,
                {
                    "force": bool(force),
                    "sessionsDir": str(sessions_dir),
                    "docsDir": str(docs_dir),
                    "progressDir": str(progress_dir),
                    "projectName": project.name,
                },
            )
        should_finalize_operation = bool(operation_id)
        stats["operation_id"] = operation_id

        t0 = time.monotonic()
        await self._update_operation(
            operation_id,
            phase="sessions",
            message="Syncing sessions",
        )

        try:
            # Phase 1: Sessions
            s_stats = await self._sync_sessions(project.id, sessions_dir, force)
            stats["sessions_synced"] = s_stats["synced"]
            stats["sessions_skipped"] = s_stats["skipped"]
            backfill_stats = await self._maybe_backfill_telemetry_events(project.id)
            stats["telemetry_backfilled_sessions"] = int(backfill_stats.get("sessions", 0))
            stats["telemetry_backfilled_events"] = int(backfill_stats.get("events", 0))
            await self._update_operation(
                operation_id,
                phase="documents",
                message="Syncing documents",
                counters={
                    "sessionsSynced": stats["sessions_synced"],
                    "sessionsSkipped": stats["sessions_skipped"],
                    "telemetryBackfilledSessions": stats["telemetry_backfilled_sessions"],
                },
            )

            # Phase 2: Documents
            d_stats = await self._sync_documents(project.id, docs_dir, progress_dir, force)
            stats["documents_synced"] = d_stats["synced"]
            stats["documents_skipped"] = d_stats["skipped"]
            await self._update_operation(
                operation_id,
                phase="tasks",
                message="Syncing progress tasks",
                counters={
                    "documentsSynced": stats["documents_synced"],
                    "documentsSkipped": stats["documents_skipped"],
                },
            )

            # Phase 3: Tasks (progress files)
            t_stats = await self._sync_progress(project.id, progress_dir, force)
            stats["tasks_synced"] = t_stats["synced"]
            stats["tasks_skipped"] = t_stats["skipped"]
            await self._update_operation(
                operation_id,
                phase="features",
                message="Syncing derived features",
                counters={
                    "tasksSynced": stats["tasks_synced"],
                    "tasksSkipped": stats["tasks_skipped"],
                },
            )

            # Phase 4: Features (derived from docs + progress)
            f_stats = await self._sync_features(project.id, docs_dir, progress_dir)
            stats["features_synced"] = f_stats["synced"]
            link_state = await self._load_link_state(project.id)
            should_rebuild_links, rebuild_reason = self._should_rebuild_links_after_full_sync(
                force=force,
                link_state=link_state,
                stats=stats,
            )
            if should_rebuild_links:
                await self._update_operation(
                    operation_id,
                    phase="links",
                    message="Rebuilding entity links",
                    counters={"featuresSynced": stats["features_synced"]},
                )

                # Phase 5: Auto-discover cross-references
                l_stats = await self._rebuild_entity_links(
                    project.id,
                    docs_dir,
                    progress_dir,
                    operation_id=operation_id,
                )
                stats["links_created"] = l_stats["created"]
                await self._save_link_state(
                    project.id,
                    trigger=trigger,
                    reason=rebuild_reason,
                    links_created=stats["links_created"],
                )
            else:
                await self._update_operation(
                    operation_id,
                    phase="links",
                    message="Skipping entity link rebuild (no relevant changes)",
                    counters={"featuresSynced": stats["features_synced"]},
                    stats={"links_created": 0},
                )
            await self._update_operation(
                operation_id,
                phase="analytics",
                message="Capturing analytics snapshot",
                counters={"linksCreated": stats["links_created"]},
            )

            # Phase 6: Analytics Snapshot
            await self._capture_analytics(project.id)

            elapsed = int((time.monotonic() - t0) * 1000)
            stats["duration_ms"] = elapsed
            await self._update_operation(
                operation_id,
                phase="completed",
                message="Sync completed",
                stats=stats,
            )
            if should_finalize_operation:
                await self._finish_operation(operation_id, status="completed", stats=stats)

            logger.info(
                f"Sync complete for {project.name}: "
                f"{stats['sessions_synced']} sessions, "
                f"{stats['telemetry_backfilled_sessions']} telemetry-backfilled sessions, "
                f"{stats['documents_synced']} docs, "
                f"{stats['tasks_synced']} tasks, "
                f"{stats['features_synced']} features, "
                f"{stats['links_created']} links "
                f"in {elapsed}ms"
            )
            return stats
        except Exception as exc:
            if should_finalize_operation:
                await self._finish_operation(
                    operation_id,
                    status="failed",
                    stats=stats,
                    error=str(exc),
                )
            raise

    async def rebuild_links(
        self,
        project_id: str,
        docs_dir: Path | None = None,
        progress_dir: Path | None = None,
        *,
        operation_id: str | None = None,
        trigger: str = "api",
        capture_analytics: bool = False,
    ) -> dict[str, Any]:
        """Rebuild entity links only, with optional analytics capture."""
        stats: dict[str, Any] = {"created": 0, "duration_ms": 0, "operation_id": ""}
        if not operation_id:
            operation_id = await self._start_operation(
                "rebuild_links",
                project_id,
                trigger,
                {
                    "docsDir": str(docs_dir) if docs_dir else "",
                    "progressDir": str(progress_dir) if progress_dir else "",
                    "captureAnalytics": bool(capture_analytics),
                },
            )
        should_finalize_operation = bool(operation_id)
        stats["operation_id"] = operation_id
        t0 = time.monotonic()
        await self._update_operation(
            operation_id,
            phase="links",
            message="Rebuilding entity links",
        )
        try:
            l_stats = await self._rebuild_entity_links(
                project_id,
                docs_dir,
                progress_dir,
                operation_id=operation_id,
            )
            stats["created"] = int(l_stats.get("created", 0))
            await self._save_link_state(
                project_id,
                trigger=trigger,
                reason="explicit_rebuild",
                links_created=stats["created"],
            )
            if capture_analytics:
                await self._update_operation(
                    operation_id,
                    phase="analytics",
                    message="Capturing analytics snapshot",
                )
                await self._capture_analytics(project_id)

            stats["duration_ms"] = int((time.monotonic() - t0) * 1000)
            await self._update_operation(
                operation_id,
                phase="completed",
                message="Link rebuild completed",
                stats=stats,
            )
            if should_finalize_operation:
                await self._finish_operation(operation_id, status="completed", stats=stats)
            return stats
        except Exception as exc:
            if should_finalize_operation:
                await self._finish_operation(
                    operation_id,
                    status="failed",
                    stats=stats,
                    error=str(exc),
                )
            raise

    async def run_link_audit(
        self,
        project_id: str,
        *,
        feature_id: str = "",
        primary_floor: float = 0.55,
        fanout_floor: int = 10,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Audit feature->session links and return likely suspect mappings."""
        feature_id = feature_id.strip()

        sqlite_rows_query = """
            SELECT
                el.source_id AS feature_id,
                el.target_id AS session_id,
                el.confidence AS confidence,
                el.metadata_json AS metadata_json
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND (json_extract(el.metadata_json, '$.linkStrategy') = 'session_evidence' OR el.metadata_json LIKE '%session_evidence%')
                AND f.project_id = ?
        """
        sqlite_fanout_query = """
            SELECT el.target_id AS session_id, COUNT(*) AS feature_count
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND f.project_id = ?
            GROUP BY el.target_id
        """

        pg_rows_query = """
            SELECT
                el.source_id AS feature_id,
                el.target_id AS session_id,
                el.confidence AS confidence,
                el.metadata_json AS metadata_json
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND (el.metadata_json::jsonb->>'linkStrategy' = 'session_evidence' OR el.metadata_json LIKE '%session_evidence%')
                AND f.project_id = $1
        """
        pg_fanout_query = """
            SELECT el.target_id AS session_id, COUNT(*) AS feature_count
            FROM entity_links el
            JOIN features f ON f.id = el.source_id
            WHERE
                el.source_type = 'feature'
                AND el.target_type = 'session'
                AND el.link_type = 'related'
                AND f.project_id = $1
            GROUP BY el.target_id
        """

        rows: list[dict[str, Any]] = []
        fanout_rows: list[dict[str, Any]] = []
        if isinstance(self.db, aiosqlite.Connection):
            row_params: list[Any] = [project_id]
            fanout_params: list[Any] = [project_id]
            rows_query = sqlite_rows_query
            if feature_id:
                rows_query += " AND el.source_id = ?"
                row_params.append(feature_id)
            async with self.db.execute(rows_query, tuple(row_params)) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            async with self.db.execute(sqlite_fanout_query, tuple(fanout_params)) as cur:
                fanout_rows = [dict(r) for r in await cur.fetchall()]
        else:
            rows_query = pg_rows_query
            row_params: list[Any] = [project_id]
            if feature_id:
                rows_query += " AND el.source_id = $2"
                row_params.append(feature_id)
            raw_rows = await self.db.fetch(rows_query, *row_params)
            rows = [dict(r) for r in raw_rows]

            raw_fanout = await self.db.fetch(pg_fanout_query, project_id)
            fanout_rows = [dict(r) for r in raw_fanout]

        fanout_map = {str(row.get("session_id") or ""): int(row.get("feature_count") or 0) for row in fanout_rows}
        parsed_rows: list[dict[str, Any]] = []
        for row in rows:
            metadata_raw = row.get("metadata_json")
            metadata: dict[str, Any] = {}
            if isinstance(metadata_raw, dict):
                metadata = metadata_raw
            elif isinstance(metadata_raw, str) and metadata_raw:
                try:
                    loaded = json.loads(metadata_raw)
                    if isinstance(loaded, dict):
                        metadata = loaded
                except Exception:
                    metadata = {}
            parsed_rows.append({
                "feature_id": str(row.get("feature_id") or ""),
                "session_id": str(row.get("session_id") or ""),
                "confidence": row.get("confidence"),
                "metadata": metadata,
            })

        suspects = analyze_suspect_links(parsed_rows, fanout_map, primary_floor, fanout_floor)
        suspects = suspects[: max(1, int(limit))]
        return {
            "project_id": project_id,
            "feature_filter": feature_id or None,
            "row_count": len(parsed_rows),
            "suspect_count": len(suspects),
            "primary_floor": float(primary_floor),
            "fanout_floor": int(fanout_floor),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "suspects": suspects_as_dicts(suspects),
        }

    async def sync_changed_files(
        self, project_id: str, changed_files: list[tuple[str, Path]],
        sessions_dir: Path, docs_dir: Path, progress_dir: Path,
        operation_id: str | None = None,
        trigger: str = "watcher",
    ) -> dict:
        """Sync only specific changed files. Used by file watcher.

        changed_files: list of (change_type, path) where change_type is 'modified'|'added'|'deleted'
        """
        stats = {"sessions": 0, "documents": 0, "tasks": 0, "features": 0, "links_created": 0, "operation_id": ""}
        if not operation_id and trigger != "watcher":
            operation_id = await self._start_operation(
                "sync_changed_files",
                project_id,
                trigger,
                {"changedCount": len(changed_files)},
            )
        should_finalize_operation = bool(operation_id)
        stats["operation_id"] = operation_id or ""

        if operation_id:
            await self._update_operation(
                operation_id,
                phase="changed-files",
                message=f"Processing {len(changed_files)} changed file(s)",
                counters={"changedFilesTotal": len(changed_files)},
            )

        should_resync_features = False
        should_rebuild_links = False
        project_root = infer_project_root(docs_dir, progress_dir)
        root_scopes: list[Path] = []
        if docs_dir.exists():
            root_scopes.append(docs_dir)
        if progress_dir.exists():
            root_scopes.append(progress_dir)
        needs_doc_git_context = False
        dirty_overrides: set[str] = set()

        for change_type, path in changed_files:
            if path.suffix != ".md":
                continue
            in_docs_scope = docs_dir in path.parents or progress_dir in path.parents
            if not in_docs_scope:
                continue
            needs_doc_git_context = True
            if change_type != "deleted":
                dirty_overrides.add(canonical_project_path(path, project_root))

        git_date_index: dict[str, dict[str, str]] = {}
        dirty_paths: set[str] = set(dirty_overrides)
        if needs_doc_git_context and root_scopes:
            git_date_index, indexed_dirty = self._build_git_doc_dates(project_root, root_scopes)
            dirty_paths.update(indexed_dirty)

        try:
            for index, (change_type, path) in enumerate(changed_files, start=1):
                if change_type == "deleted":
                    # Remove sync state and associated entities
                    await self.sync_repo.delete_sync_state(str(path))
                    if path.suffix == ".jsonl":
                        await self.session_repo.delete_by_source(str(path))
                        stats["sessions"] += 1
                        should_rebuild_links = True
                    elif path.suffix == ".md":
                        await self.document_repo.delete_by_source(str(path))
                        await self.task_repo.delete_by_source(str(path))
                        if progress_dir in path.parents:
                            await self.task_repo.delete_by_source(_canonical_task_source(path, progress_dir))
                        stats["documents"] += 1
                        should_rebuild_links = True
                        if docs_dir in path.parents or progress_dir in path.parents:
                            should_resync_features = True
                else:
                    # Modified or added
                    if path.suffix == ".jsonl" and sessions_dir in path.parents:
                        if await self._sync_single_session(project_id, path):
                            stats["sessions"] += 1
                            should_rebuild_links = True
                    elif path.suffix == ".md":
                        if docs_dir in path.parents:
                            synced = await self._sync_single_document(
                                project_id,
                                path,
                                docs_dir,
                                progress_dir,
                                project_root=project_root,
                                git_date_index=git_date_index,
                                dirty_paths=dirty_paths,
                            )
                            if synced:
                                stats["documents"] += 1
                                should_resync_features = True
                                should_rebuild_links = True
                        if progress_dir in path.parents:
                            doc_synced = await self._sync_single_document(
                                project_id,
                                path,
                                docs_dir,
                                progress_dir,
                                project_root=project_root,
                                git_date_index=git_date_index,
                                dirty_paths=dirty_paths,
                            )
                            task_synced = await self._sync_single_progress(project_id, path, progress_dir)
                            if doc_synced:
                                stats["documents"] += 1
                            if task_synced:
                                stats["tasks"] += 1
                            if doc_synced or task_synced:
                                should_resync_features = True
                                should_rebuild_links = True

                if operation_id and (index == len(changed_files) or index % 10 == 0):
                    await self._update_operation(
                        operation_id,
                        phase="changed-files",
                        message=f"Processed {index}/{len(changed_files)} changed file(s)",
                        progress={
                            "processedChangedFiles": index,
                            "totalChangedFiles": len(changed_files),
                        },
                        counters={
                            "sessionsSynced": stats["sessions"],
                            "documentsSynced": stats["documents"],
                            "tasksSynced": stats["tasks"],
                        },
                    )

            if should_resync_features:
                if operation_id:
                    await self._update_operation(
                        operation_id,
                        phase="features",
                        message="Resyncing derived features after changed files",
                    )
                f_stats = await self._sync_features(
                    project_id,
                    docs_dir,
                    progress_dir,
                    project_root=project_root,
                    git_date_index=git_date_index,
                    dirty_paths=dirty_paths,
                )
                stats["features"] = f_stats.get("synced", 0)
                if stats["features"] > 0:
                    should_rebuild_links = True

            link_state = await self._load_link_state(project_id)
            should_rebuild_for_version = self._is_link_logic_version_stale(link_state)
            if should_rebuild_links or should_rebuild_for_version:
                rebuild_reason = "changed_files" if should_rebuild_links else "logic_version_changed"
                if operation_id:
                    await self._update_operation(
                        operation_id,
                        phase="links",
                        message="Rebuilding entity links after changed-file sync",
                    )
                l_stats = await self._rebuild_entity_links(
                    project_id,
                    docs_dir,
                    progress_dir,
                    operation_id=operation_id,
                )
                stats["links_created"] = int(l_stats.get("created", 0))
                await self._save_link_state(
                    project_id,
                    trigger=trigger,
                    reason=rebuild_reason,
                    links_created=stats["links_created"],
                )

            if operation_id:
                await self._update_operation(
                    operation_id,
                    phase="completed",
                    message="Changed-file sync completed",
                    stats=stats,
                )
            if should_finalize_operation:
                await self._finish_operation(operation_id, status="completed", stats=stats)
            return stats
        except Exception as exc:
            if should_finalize_operation:
                await self._finish_operation(
                    operation_id,
                    status="failed",
                    stats=stats,
                    error=str(exc),
                )
            raise

    # ── Session Sync ────────────────────────────────────────────────

    async def _sync_sessions(self, project_id: str, sessions_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        if not sessions_dir.exists():
            return stats

        for jsonl_file in sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            synced = await self._sync_single_session(project_id, jsonl_file, force)
            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

        return stats

    async def _sync_single_session(self, project_id: str, path: Path, force: bool = False) -> bool:
        """Parse and upsert a single session file. Returns True if actually synced."""
        file_path = str(path)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False  # unchanged

        t0 = time.monotonic()
        session = parse_session_file(path)
        parse_ms = int((time.monotonic() - t0) * 1000)

        # Always clear existing rows for this source file before re-inserting.
        # This prevents stale duplicates when session ID derivation changes.
        await self.session_repo.delete_by_source(file_path)

        if session:
            session_dict = session.model_dump()
            session_dict["sourceFile"] = file_path
            await self.session_repo.upsert(session_dict, project_id)

            # Detail tables
            logs = [log.model_dump() for log in session.logs]
            await self.session_repo.upsert_logs(session.id, logs)

            tools = [t.model_dump() for t in session.toolsUsed]
            await self.session_repo.upsert_tool_usage(session.id, tools)

            files = [f.model_dump() for f in session.updatedFiles]
            await self.session_repo.upsert_file_updates(session.id, files)

            artifacts = [a.model_dump() for a in session.linkedArtifacts]
            await self.session_repo.upsert_artifacts(session.id, artifacts)

            await self._replace_session_telemetry_events(
                project_id,
                session_dict,
                logs,
                tools,
                files,
                artifacts,
                source="sync",
            )

        # Update sync state
        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "session",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Document Sync ───────────────────────────────────────────────

    async def _sync_documents(self, project_id: str, docs_dir: Path, progress_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        roots: list[Path] = []
        if docs_dir.exists():
            roots.append(docs_dir)
        if progress_dir.exists():
            roots.append(progress_dir)
        if not roots:
            return stats

        project_root = infer_project_root(docs_dir, progress_dir)
        git_date_index, dirty_paths = self._build_git_doc_dates(project_root, roots)

        for root in roots:
            for md_file in sorted(root.rglob("*.md")):
                if md_file.name.startswith("."):
                    continue
                synced = await self._sync_single_document(
                    project_id,
                    md_file,
                    docs_dir,
                    progress_dir,
                    force,
                    project_root=project_root,
                    git_date_index=git_date_index,
                    dirty_paths=dirty_paths,
                )
                if synced:
                    stats["synced"] += 1
                else:
                    stats["skipped"] += 1

        return stats

    async def _sync_single_document(
        self,
        project_id: str,
        path: Path,
        docs_dir: Path,
        progress_dir: Path,
        force: bool = False,
        project_root: Path | None = None,
        git_date_index: dict[str, dict[str, str]] | None = None,
        dirty_paths: set[str] | None = None,
    ) -> bool:
        file_path = str(path)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False

        project_root = project_root or infer_project_root(docs_dir, progress_dir)
        base_dir = progress_dir if progress_dir in path.parents else docs_dir
        t0 = time.monotonic()
        doc = parse_document_file(
            path,
            base_dir,
            project_root=project_root,
            git_date_index=git_date_index,
            dirty_paths=dirty_paths,
        )
        parse_ms = int((time.monotonic() - t0) * 1000)

        if doc:
            doc_dict = doc.model_dump()
            doc_dict["sourceFile"] = file_path
            await self.document_repo.upsert(doc_dict, project_id)

            fm = doc_dict.get("frontmatter", {})
            fm_tags = fm.get("tags", []) if isinstance(fm, dict) else []
            for tag_name in fm_tags:
                if tag_name:
                    tag_id = await self.tag_repo.get_or_create(str(tag_name))
                    await self.tag_repo.tag_entity("document", doc.id, tag_id)

        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "document",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Progress / Task Sync ────────────────────────────────────────

    async def _sync_progress(self, project_id: str, progress_dir: Path, force: bool) -> dict:
        stats = {"synced": 0, "skipped": 0}
        if not progress_dir.exists():
            return stats

        for md_file in sorted(progress_dir.rglob("*progress*.md")):
            if md_file.name.startswith("."):
                continue
            synced = await self._sync_single_progress(project_id, md_file, progress_dir, force)
            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

        return stats

    async def _sync_single_progress(
        self, project_id: str, path: Path, progress_dir: Path, force: bool = False,
    ) -> bool:
        file_path = str(path)
        canonical_source = _canonical_task_source(path, progress_dir)
        mtime = path.stat().st_mtime

        if not force:
            cached = await self.sync_repo.get_sync_state(file_path)
            if cached and cached["file_mtime"] == mtime:
                return False

        t0 = time.monotonic()
        tasks = parse_progress_file(path, progress_dir)
        parse_ms = int((time.monotonic() - t0) * 1000)

        # Delete old tasks from this source first (legacy absolute + canonical relative)
        await self.task_repo.delete_by_source(file_path)
        if canonical_source != file_path:
            await self.task_repo.delete_by_source(canonical_source)

        for task in tasks:
            task_dict = task.model_dump()
            task_dict["sourceFile"] = canonical_source
            task_dict = _prepare_task_for_storage(task_dict)
            await self.task_repo.upsert(task_dict, project_id)

            # Auto-tag
            for tag_name in task.tags:
                if tag_name:
                    tag_id = await self.tag_repo.get_or_create(str(tag_name))
                    await self.tag_repo.tag_entity("task", task.id, tag_id)

        await self.sync_repo.upsert_sync_state({
            "file_path": file_path,
            "file_hash": _file_hash(path),
            "file_mtime": mtime,
            "entity_type": "task",
            "project_id": project_id,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "parse_ms": parse_ms,
        })

        return True

    # ── Feature Sync ────────────────────────────────────────────────

    async def _sync_features(
        self,
        project_id: str,
        docs_dir: Path,
        progress_dir: Path,
        *,
        project_root: Path | None = None,
        git_date_index: dict[str, dict[str, str]] | None = None,
        dirty_paths: set[str] | None = None,
    ) -> dict:
        """Re-derive features from docs + progress and upsert all."""
        stats = {"synced": 0, "pruned_aliases": 0}

        project_root = project_root or infer_project_root(docs_dir, progress_dir)
        resolved_dirty_paths = set(dirty_paths or set())
        if git_date_index is None:
            roots: list[Path] = []
            if docs_dir.exists():
                roots.append(docs_dir)
            if progress_dir.exists():
                roots.append(progress_dir)
            if roots:
                resolved_git_date_index, indexed_dirty = self._build_git_doc_dates(project_root, roots)
                resolved_dirty_paths.update(indexed_dirty)
            else:
                resolved_git_date_index = {}
        else:
            resolved_git_date_index = dict(git_date_index)

        features = scan_features(
            docs_dir,
            progress_dir,
            git_date_index=resolved_git_date_index,
            dirty_paths=resolved_dirty_paths,
        )
        for feature in features:
            try:
                f_dict = feature.model_dump()
                await self.feature_repo.upsert(f_dict, project_id)

                # Upsert phases and link tasks
                phases = []
                for idx, p in enumerate(feature.phases):
                    p_dict = p.model_dump()
                    
                    # Generate deterministic phase_id (mirroring repo logic)
                    phase_id = p_dict.get("id")
                    if not phase_id:
                        phase_id = f"{feature.id}:phase-{str(p_dict.get('phase', '0'))}-{idx}"
                        p_dict["id"] = phase_id
                    
                    phases.append(p_dict)
                    
                    # Link tasks in this phase to feature and phase
                    for task in p.tasks:
                        task_dict = task.model_dump()
                        if not task_dict.get("sourceFile"):
                            task_dict["sourceFile"] = f"progress/{feature.id}"
                        task_dict["featureId"] = feature.id
                        task_dict["phaseId"] = phase_id
                        task_dict = _prepare_task_for_storage(task_dict)
                        await self.task_repo.upsert(task_dict, project_id)

                await self.feature_repo.upsert_phases(feature.id, phases)

                # Auto-tag
                for tag_name in feature.tags:
                    if tag_name:
                        tag_id = await self.tag_repo.get_or_create(str(tag_name))
                        await self.tag_repo.tag_entity("feature", feature.id, tag_id)

                stats["synced"] += 1
            except Exception as e:
                logger.error(f"Failed to sync feature {feature.id}: {e}")

        # Remove stale alias rows that share a canonical slug with newly scanned
        # features but are no longer emitted by scan_features().
        scanned_ids = {str(feature.id or "") for feature in features if str(feature.id or "").strip()}
        scanned_bases = {canonical_slug(feature_id) for feature_id in scanned_ids}
        if scanned_bases:
            existing_rows = await self.feature_repo.list_all(project_id)
            stale_feature_ids = [
                str(row.get("id") or "")
                for row in existing_rows
                if str(row.get("id") or "")
                and str(row.get("id") or "") not in scanned_ids
                and canonical_slug(str(row.get("id") or "")) in scanned_bases
            ]
            for stale_feature_id in stale_feature_ids:
                stale_tasks = await self.task_repo.list_by_feature(stale_feature_id)
                for task_row in stale_tasks:
                    task_id = str(task_row.get("id") or "")
                    if task_id:
                        await self.link_repo.delete_auto_links("task", task_id)
                await self._delete_tasks_for_feature(stale_feature_id)
                await self.link_repo.delete_auto_links("feature", stale_feature_id)
                await self.feature_repo.delete(stale_feature_id)
                stats["pruned_aliases"] += 1

        return stats

    # ── Entity Link Discovery ───────────────────────────────────────

    async def _rebuild_entity_links(
        self,
        project_id: str,
        docs_dir: Path | None = None,
        progress_dir: Path | None = None,
        operation_id: str | None = None,
    ) -> dict:
        """Auto-discover cross-references between entities."""
        stats = {"created": 0}
        await self._update_operation(
            operation_id,
            phase="links:init",
            message="Preparing link rebuild",
        )

        path_pattern = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
        req_id_pattern = re.compile(r"\bREQ-\d{8}-[A-Za-z0-9-]+-\d+\b")

        def _normalize_ref_path(raw: str) -> str:
            return normalize_ref_path(raw)

        def _canonical_slug(slug: str) -> str:
            return canonical_slug(slug)

        def _slug_from_path(path_value: str) -> str:
            return slug_from_path(path_value)

        def _extract_paths_from_text(text: str) -> list[str]:
            if not text:
                return []
            values: list[str] = []
            for raw in path_pattern.findall(text):
                normalized = _normalize_ref_path(raw)
                if normalized:
                    values.append(normalized)
            return values

        def _extract_phase_token(args_text: str) -> tuple[str, list[str]]:
            normalized = " ".join((args_text or "").strip().split())
            if not normalized:
                return "", []

            if normalized.lower().startswith("all"):
                return "all", ["all"]

            range_match = re.match(r"^(\d+)\s*-\s*(\d+)\b", normalized)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                if start <= end:
                    phases = [str(v) for v in range(start, end + 1)]
                else:
                    phases = [str(start), str(end)]
                return f"{start}-{end}", phases

            amp_match = re.match(r"^(\d+(?:\s*&\s*\d+)+)\b", normalized)
            if amp_match:
                phases = [part.strip() for part in amp_match.group(1).split("&") if part.strip()]
                return " & ".join(phases), phases

            single_match = re.match(r"^(\d+)\b", normalized)
            if single_match:
                token = single_match.group(1)
                return token, [token]

            return "", []

        def _parse_command_context(command_name: str, args_text: str) -> dict[str, Any]:
            context: dict[str, Any] = {}
            command = (command_name or "").strip()
            args = (args_text or "").strip()
            if not command:
                return context

            if args:
                req_match = req_id_pattern.search(args)
                if req_match:
                    context["requestId"] = req_match.group(0).upper()
                paths = _extract_paths_from_text(args)
                if paths:
                    context["paths"] = paths[:8]
                    primary_path = paths[0]
                    impl_paths = [p for p in paths if "implementation_plans/" in p and p.lower().endswith(".md")]
                    if impl_paths:
                        primary_path = impl_paths[0]
                    context["featurePath"] = primary_path
                    feature_slug = feature_slug_from_path(primary_path) or _slug_from_path(primary_path)
                    if feature_slug and not is_generic_alias_token(feature_slug):
                        context["featureSlug"] = feature_slug
                        context["featureSlugCanonical"] = _canonical_slug(feature_slug)

            if "dev:execute-phase" in command.lower():
                phase_token, phases = _extract_phase_token(args)
                if phase_token:
                    context["phaseToken"] = phase_token
                if phases:
                    context["phases"] = phases
            return context

        def _path_matches(candidate: str, ref: str) -> bool:
            candidate_norm = _normalize_ref_path(candidate)
            ref_norm = _normalize_ref_path(ref)
            if not candidate_norm or not ref_norm:
                return False
            if candidate_norm == ref_norm:
                return True
            if candidate_norm.endswith(f"/{ref_norm}"):
                return True
            if ref_norm.endswith(f"/{candidate_norm}"):
                return True
            return False

        def _source_weight(tool_name: str) -> tuple[float, str]:
            name = (tool_name or "").strip().lower()
            if name in {"command"}:
                return 0.96, "command_args_path"
            if name in {"write", "writefile", "edit", "multiedit"}:
                return 0.95, "file_write"
            if name in {"bash", "exec"}:
                return 0.84, "shell_reference"
            if name in {"grep", "glob"}:
                return 0.66, "search_reference"
            if name in {"read", "readfile"}:
                return 0.46, "file_read"
            return 0.52, "file_reference"

        def _confidence_from_signals(
            weights: list[float],
            has_command_path: bool,
            has_command_hint: bool,
            has_write: bool,
        ) -> float:
            if not weights:
                return 0.0
            peak = max(weights)
            score = 0.35
            if has_command_path and has_write:
                score = 0.90
            elif has_command_path:
                score = 0.75
            elif has_write and peak >= 0.84:
                score = 0.75
            elif has_write:
                score = 0.62
            elif peak >= 0.84:
                score = 0.55

            if len(weights) >= 3:
                score += 0.05
            elif len(weights) >= 2:
                score += 0.03

            if has_command_hint:
                score += 0.03
            if has_write:
                score += 0.02
            return round(min(0.95, score), 3)

        def _derive_session_title(
            feature_id: str,
            custom_title: str,
            latest_summary: str,
            command_events: list[dict[str, Any]],
            command_names: set[str],
            candidate_evidence: list[dict[str, Any]],
            file_updates: list[dict[str, Any]],
        ) -> tuple[str, str, float]:
            def _feature_slug_from_paths(paths: list[str]) -> str:
                for raw_path in paths:
                    path_slug = feature_slug_from_path(raw_path)
                    if path_slug:
                        return path_slug
                return ""

            evidence_paths = [
                str(signal.get("path") or "")
                for signal in candidate_evidence
                if isinstance(signal, dict)
            ]
            evidence_feature_slug = _feature_slug_from_paths(evidence_paths)

            if custom_title:
                return custom_title[:160], "custom-title", 1.0
            if latest_summary:
                return latest_summary[:160], "summary", 0.92

            preferred = _select_preferred_command_event(command_events)
            if preferred:
                command_name = str(preferred.get("name") or "")
                parsed = preferred.get("parsed") if isinstance(preferred.get("parsed"), dict) else {}
                parsed_feature_slug = str(parsed.get("featureSlug") or "").strip().lower()
                parsed_feature_path = str(parsed.get("featurePath") or "")
                parsed_path_feature_slug = feature_slug_from_path(parsed_feature_path)
                resolved_slug = (
                    evidence_feature_slug
                    or parsed_path_feature_slug
                    or parsed_feature_slug
                    or feature_slug_from_path(str(parsed.get("requestId") or ""))
                )

                if "dev:execute-phase" in command_name.lower():
                    phase = str(parsed.get("phaseToken") or "unknown")
                    slug = resolved_slug or feature_id
                    confidence = 0.90 if parsed.get("featurePath") else 0.75
                    return f"Execute Phase {phase} - {slug}", "command-template", confidence

                if "recovering-sessions" in command_name.lower():
                    basis = resolved_slug
                    if basis:
                        return f"Recover Session - {basis}", "command-template", 0.78
                    return "Recover Session", "command-template", 0.62

                if "dev:quick-feature" in command_name.lower():
                    quick_slug = ""
                    for update in file_updates:
                        update_path = str(update.get("file_path") or "")
                        if "/quick-features/" in update_path and update_path.lower().endswith(".md"):
                            quick_slug = Path(update_path).stem
                            break
                    if not quick_slug:
                        quick_slug = resolved_slug or str(parsed.get("requestId") or "")
                    confidence = 0.85 if quick_slug else 0.65
                    if quick_slug:
                        return f"Quick Feature - {quick_slug}", "command-template", confidence
                    return "Quick Feature", "command-template", confidence

                if "plan:plan-feature" in command_name.lower():
                    basis = resolved_slug or str(parsed.get("requestId") or "")
                    confidence = 0.88 if parsed.get("featurePath") or parsed.get("requestId") else 0.65
                    if basis:
                        return f"Plan Feature - {basis}", "command-template", confidence
                    return "Plan Feature", "command-template", confidence

                if "fix:debug" in command_name.lower():
                    basis = resolved_slug
                    if basis:
                        return f"Debug - {basis}", "command-template", 0.62
                    return "Debug", "command-template", 0.55

            ordered_commands = _select_linking_commands(command_names)
            if ordered_commands:
                primary = ordered_commands[0]
                if evidence_feature_slug:
                    return f"{primary} - {evidence_feature_slug}", "command-fallback", 0.55
                return primary, "command-fallback", 0.5
            return "Session", "feature-fallback", 0.35

        def _extract_frontmatter(text: str) -> dict[str, Any]:
            match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if not match:
                return {}
            try:
                parsed = yaml.safe_load(match.group(1)) or {}
            except Exception:
                parsed = {}
            return parsed if isinstance(parsed, dict) else {}

        async def _store_document_catalog_index() -> None:
            if not docs_dir or not progress_dir:
                return
            project_root = infer_project_root(docs_dir, progress_dir)
            field_counts: dict[str, int] = {}
            type_counts: dict[str, int] = {}
            entries: list[dict[str, Any]] = []
            total = 0

            for root in (docs_dir, progress_dir):
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*.md")):
                    if path.name.startswith("."):
                        continue
                    try:
                        text = path.read_text(encoding="utf-8")
                    except Exception:
                        continue
                    fm = _extract_frontmatter(text)
                    refs = extract_frontmatter_references(fm)
                    rel_path = canonical_project_path(path, project_root)
                    doc_type = classify_doc_type(rel_path, fm if isinstance(fm, dict) else {})
                    type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
                    total += 1
                    for key in fm.keys():
                        key_text = str(key)
                        field_counts[key_text] = field_counts.get(key_text, 0) + 1

                    entries.append({
                        "path": rel_path,
                        "docType": doc_type,
                        "slug": slug_from_path(rel_path),
                        "category": classify_doc_category(rel_path, fm if isinstance(fm, dict) else {}),
                        "frontmatterKeys": sorted(str(key) for key in fm.keys()),
                        "featureRefs": [str(v) for v in refs.get("featureRefs", []) if isinstance(v, str)],
                        "relatedRefs": [str(v) for v in refs.get("relatedRefs", []) if isinstance(v, str)],
                        "prd": str(refs.get("prd") or ""),
                    })

            payload = {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "documentsIndexed": total,
                "documentsByType": dict(sorted(type_counts.items())),
                "frontmatterFieldCounts": dict(sorted(field_counts.items(), key=lambda item: item[0])),
                "entries": entries[:600],
            }
            payload_json = json.dumps(payload)

            if isinstance(self.db, aiosqlite.Connection):
                await self.db.execute(
                    """
                    INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    ("project", project_id, "document_catalog", payload_json),
                )
                await self.db.commit()
            else:
                await self.db.execute(
                    """
                    INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
                    VALUES ($1, $2, $3, $4, NOW()::text)
                    ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
                    """,
                    "project",
                    project_id,
                    "document_catalog",
                    payload_json,
                )

        features = await self.feature_repo.list_all(project_id)
        await self._update_operation(
            operation_id,
            phase="links:feature-prep",
            message=f"Building feature evidence for {len(features)} feature(s)",
            progress={"featureCount": len(features)},
        )
        feature_ids = {str(row.get("id") or "") for row in features}
        feature_ids_by_base: dict[str, set[str]] = {}
        for feat_id in feature_ids:
            if not feat_id:
                continue
            feature_ids_by_base.setdefault(_canonical_slug(feat_id), set()).add(feat_id)

        def _feature_slug_matches_feature(feature_id: str, candidate_slug: str) -> bool:
            token = (candidate_slug or "").strip().lower()
            if not token:
                return False
            feature_token = feature_id.lower()
            return token == feature_token or _canonical_slug(token) == _canonical_slug(feature_token)

        feature_ref_paths: dict[str, set[str]] = {}
        feature_slug_aliases: dict[str, set[str]] = {}
        task_bound_feature_sessions: set[tuple[str, str]] = set()

        for feature_index, f in enumerate(features, start=1):
            feature_id = f["id"]
            await self.link_repo.delete_auto_links("feature", feature_id)
            feature_ref_paths[feature_id] = set()
            feature_slug_aliases[feature_id] = {feature_id.lower(), _canonical_slug(feature_id)}

            try:
                f_data = json.loads(f.get("data_json") or "{}")
            except Exception:
                f_data = {}

            for doc in f_data.get("linkedDocs", []):
                if not isinstance(doc, dict):
                    continue
                doc_path = _normalize_ref_path(str(doc.get("filePath") or ""))
                if doc_path:
                    doc_feature_slug = feature_slug_from_path(doc_path)
                    if not doc_feature_slug or _feature_slug_matches_feature(feature_id, doc_feature_slug):
                        feature_ref_paths[feature_id].add(doc_path)
                        feature_slug_aliases[feature_id].update(alias_tokens_from_path(doc_path))

                doc_slug = str(doc.get("slug") or "").strip().lower()
                if doc_slug and is_feature_like_token(doc_slug) and _feature_slug_matches_feature(feature_id, doc_slug):
                    feature_slug_aliases[feature_id].add(doc_slug)
                    feature_slug_aliases[feature_id].add(_canonical_slug(doc_slug))

                related_refs = doc.get("relatedRefs", [])
                if isinstance(related_refs, list):
                    for related_ref in related_refs:
                        if not isinstance(related_ref, str):
                            continue
                        related_value = related_ref.strip()
                        if not related_value:
                            continue
                        if "/" in related_value or related_value.lower().endswith(".md"):
                            related_path = _normalize_ref_path(related_value)
                            if related_path:
                                related_feature_slug = feature_slug_from_path(related_path)
                                if related_feature_slug and _feature_slug_matches_feature(feature_id, related_feature_slug):
                                    feature_ref_paths[feature_id].add(related_path)
                                    feature_slug_aliases[feature_id].update(alias_tokens_from_path(related_path))
                        else:
                            token = related_value.lower()
                            if token and is_feature_like_token(token) and _feature_slug_matches_feature(feature_id, token):
                                feature_slug_aliases[feature_id].add(token)
                                feature_slug_aliases[feature_id].add(_canonical_slug(token))

                prd_ref = str(doc.get("prdRef") or "").strip()
                if prd_ref:
                    if "/" in prd_ref or prd_ref.lower().endswith(".md"):
                        prd_path = _normalize_ref_path(prd_ref)
                        if prd_path:
                            prd_feature_slug = feature_slug_from_path(prd_path)
                            if prd_feature_slug and _feature_slug_matches_feature(feature_id, prd_feature_slug):
                                feature_ref_paths[feature_id].add(prd_path)
                                feature_slug_aliases[feature_id].update(alias_tokens_from_path(prd_path))
                    else:
                        token = prd_ref.lower()
                        if token and is_feature_like_token(token) and _feature_slug_matches_feature(feature_id, token):
                            feature_slug_aliases[feature_id].add(token)
                            feature_slug_aliases[feature_id].add(_canonical_slug(token))

            # Link feature → tasks
            tasks = await self.task_repo.list_by_feature(feature_id)
            for t in tasks:
                await self.link_repo.delete_auto_links("task", t["id"])

                source_file = _normalize_ref_path(str(t.get("source_file") or ""))
                if source_file:
                    feature_ref_paths[feature_id].add(source_file)
                    feature_slug_aliases[feature_id].update(alias_tokens_from_path(source_file))

                await self.link_repo.upsert({
                    "source_type": "feature",
                    "source_id": feature_id,
                    "target_type": "task",
                    "target_id": t["id"],
                    "link_type": "child",
                    "origin": "auto",
                })
                stats["created"] += 1

                # Link task → session if available
                if t.get("session_id"):
                    feature_session_metadata = {
                        "linkStrategy": "task_frontmatter",
                        "taskId": t.get("id"),
                        "taskSource": t.get("source_file"),
                        "commitHash": t.get("commit_hash") or "",
                    }
                    await self.link_repo.upsert({
                        "source_type": "feature",
                        "source_id": feature_id,
                        "target_type": "session",
                        "target_id": t["session_id"],
                        "link_type": "related",
                        "origin": "auto",
                        "confidence": 1.0,
                        "metadata_json": json.dumps(feature_session_metadata),
                    })
                    stats["created"] += 1
                    task_bound_feature_sessions.add((feature_id, str(t["session_id"])))

                    await self.link_repo.upsert({
                        "source_type": "task",
                        "source_id": t["id"],
                        "target_type": "session",
                        "target_id": t["session_id"],
                        "link_type": "related",
                        "origin": "auto",
                    })
                    stats["created"] += 1

            if operation_id and (feature_index == len(features) or feature_index % 20 == 0):
                await self._update_operation(
                    operation_id,
                    phase="links:feature-prep",
                    message=f"Prepared feature evidence {feature_index}/{len(features)}",
                    progress={
                        "featuresPrepared": feature_index,
                        "featureCount": len(features),
                    },
                    counters={"linksCreated": stats["created"]},
                )

        # Build feature ↔ session links from session evidence.
        total_sessions = await self.session_repo.count(project_id, {"include_subagents": True})
        await self._update_operation(
            operation_id,
            phase="links:session-evidence",
            message=f"Evaluating session evidence across {total_sessions} session(s)",
            progress={"sessionCount": int(total_sessions)},
        )
        sessions_data: list[dict[str, Any]] = []
        page_size = 250
        for offset in range(0, total_sessions, page_size):
            page = await self.session_repo.list_paginated(
                offset,
                page_size,
                project_id,
                "started_at",
                "desc",
                {"include_subagents": True},
            )
            sessions_data.extend(page)
            if operation_id:
                loaded = min(offset + page_size, total_sessions)
                await self._update_operation(
                    operation_id,
                    phase="links:session-evidence",
                    message=f"Loaded session page {loaded}/{total_sessions}",
                    progress={
                        "sessionPagesLoaded": loaded,
                        "sessionCount": int(total_sessions),
                    },
                )

        for session_index, s in enumerate(sessions_data, start=1):
            session_id = s["id"]
            file_updates = await self.session_repo.get_file_updates(session_id)
            artifacts = await self.session_repo.get_artifacts(session_id)
            logs = await self.session_repo.get_logs(session_id)

            command_events: list[dict[str, Any]] = []
            tagged_commands: list[dict[str, Any]] = []
            latest_summary = ""
            custom_title = ""
            queue_events: list[dict[str, str]] = []
            pr_links: list[dict[str, str]] = []

            for log in logs:
                log_type = str(log.get("type") or "")
                metadata_raw = log.get("metadata_json")
                try:
                    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) and metadata_raw else {}
                except Exception:
                    metadata = {}

                if log_type == "message":
                    content_text = str(log.get("content") or "")
                    for command_name, args_text in _extract_tagged_commands_from_message(content_text):
                        tagged_commands.append({
                            "name": command_name,
                            "args": args_text,
                            "parsed": _parse_command_context(command_name, args_text) if args_text else {},
                        })
                    continue

                if log_type == "command":
                    command_name = _normalize_command_label(str(log.get("content") or ""))
                    args_text = str(metadata.get("args") or "")
                    parsed = metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {}

                    if not args_text or not parsed:
                        tagged = _pop_matching_tagged_command(tagged_commands, command_name)
                        if tagged:
                            if not args_text:
                                args_text = str(tagged.get("args") or "")
                            if not parsed and isinstance(tagged.get("parsed"), dict):
                                parsed = tagged.get("parsed")

                    if not parsed and args_text:
                        parsed = _parse_command_context(command_name, args_text)
                    command_events.append({
                        "name": command_name,
                        "args": args_text,
                        "parsed": parsed if isinstance(parsed, dict) else {},
                    })
                    continue

                if log_type != "system":
                    continue

                event_type = str(metadata.get("eventType") or "").strip().lower()
                if event_type == "summary":
                    text = str(log.get("content") or "").strip()
                    if text:
                        latest_summary = text
                elif event_type == "custom-title":
                    text = str(log.get("content") or "").strip()
                    if text:
                        custom_title = text
                elif event_type == "queue-operation":
                    queue_event = {
                        "taskId": str(metadata.get("task-id") or ""),
                        "status": str(metadata.get("status") or ""),
                        "summary": str(metadata.get("summary") or log.get("content") or ""),
                    }
                    if queue_event["taskId"] or queue_event["summary"]:
                        queue_events.append(queue_event)
                elif event_type == "pr-link":
                    pr_link = {
                        "prNumber": str(metadata.get("prNumber") or ""),
                        "prUrl": str(metadata.get("prUrl") or ""),
                        "prRepository": str(metadata.get("prRepository") or ""),
                    }
                    if pr_link["prUrl"] or pr_link["prNumber"]:
                        pr_links.append(pr_link)

            for tagged in tagged_commands:
                command_name = _normalize_command_label(str(tagged.get("name") or ""))
                if not command_name:
                    continue
                command_events.append({
                    "name": command_name,
                    "args": str(tagged.get("args") or ""),
                    "parsed": tagged.get("parsed") if isinstance(tagged.get("parsed"), dict) else {},
                })

            command_name_candidates = {
                str(a.get("title") or "").strip()
                for a in artifacts
                if str(a.get("type") or "").strip().lower() == "command" and str(a.get("title") or "").strip()
            }
            command_name_candidates.update(
                event.get("name", "").strip()
                for event in command_events
                if isinstance(event.get("name"), str) and event.get("name", "").strip()
            )
            ordered_commands = _select_linking_commands(command_name_candidates)
            command_names = set(ordered_commands)

            session_commit_hashes: set[str] = set()
            if s.get("git_commit_hash"):
                session_commit_hashes.add(str(s["git_commit_hash"]))
            try:
                parsed_hashes = json.loads(s.get("git_commit_hashes_json") or "[]")
            except Exception:
                parsed_hashes = []
            if isinstance(parsed_hashes, list):
                for h in parsed_hashes:
                    if isinstance(h, str) and h.strip():
                        session_commit_hashes.add(h.strip())

            candidates: list[dict[str, Any]] = []
            for feature_id, refs in feature_ref_paths.items():
                feature_aliases = {alias for alias in feature_slug_aliases.get(feature_id, set()) if alias}
                signal_weights: list[float] = []
                evidence: list[dict[str, Any]] = []
                has_write = False
                has_command_path = False
                has_read_reference = False

                for update in file_updates:
                    update_path = str(update.get("file_path") or "")
                    if not update_path:
                        continue
                    if not any(_path_matches(update_path, ref_path) for ref_path in refs):
                        continue
                    update_feature_slug = feature_slug_from_path(update_path)
                    if (
                        update_feature_slug
                        and not (
                            update_feature_slug in feature_aliases
                            or _canonical_slug(update_feature_slug) in feature_aliases
                        )
                    ):
                        continue

                    weight, signal_type = _source_weight(str(update.get("source_tool_name") or ""))
                    signal_weights.append(weight)
                    if signal_type == "file_write":
                        has_write = True
                    if signal_type == "file_read":
                        has_read_reference = True
                    evidence.append({
                        "type": signal_type,
                        "path": update_path,
                        "sourceTool": update.get("source_tool_name"),
                        "weight": weight,
                    })

                if (feature_id, session_id) in task_bound_feature_sessions:
                    continue

                for command_event in command_events:
                    command_name = str(command_event.get("name") or "").strip()
                    if _is_non_consequential_command(command_name):
                        continue
                    parsed = command_event.get("parsed") if isinstance(command_event.get("parsed"), dict) else {}
                    command_slug = str(parsed.get("featureSlug") or "").lower()
                    command_slug_canonical = _canonical_slug(str(parsed.get("featureSlugCanonical") or command_slug))
                    command_paths = parsed.get("paths", [])
                    if not isinstance(command_paths, list):
                        command_paths = []

                    matched = False
                    if (
                        command_slug
                        and not is_generic_alias_token(command_slug)
                        and (command_slug in feature_aliases or command_slug_canonical in feature_aliases)
                    ):
                        matched = True
                    else:
                        for command_path in command_paths:
                            if not isinstance(command_path, str):
                                continue
                            normalized_command_path = _normalize_ref_path(command_path)
                            if not normalized_command_path:
                                continue
                            command_path_feature_slug = feature_slug_from_path(normalized_command_path)
                            if (
                                command_path_feature_slug
                                and not (
                                    command_path_feature_slug in feature_aliases
                                    or _canonical_slug(command_path_feature_slug) in feature_aliases
                                )
                            ):
                                continue
                            if any(_path_matches(normalized_command_path, ref_path) for ref_path in refs):
                                matched = True
                                break
                            path_aliases = alias_tokens_from_path(normalized_command_path)
                            if path_aliases.intersection(feature_aliases):
                                matched = True
                                break
                            path_slug = _slug_from_path(normalized_command_path)
                            if (
                                path_slug
                                and not is_generic_phase_progress_slug(path_slug)
                                and (_canonical_slug(path_slug) in feature_aliases or path_slug in feature_aliases)
                            ):
                                matched = True
                                break

                    if matched:
                        has_command_path = True
                        signal_weight = 0.96
                        lowered_command = command_name.lower()
                        if "dev:quick-feature" in lowered_command:
                            quick_feature_slug = feature_slug_from_path(str(parsed.get("featurePath") or ""))
                            signal_weight = 0.9 if (quick_feature_slug and _feature_slug_matches_feature(feature_id, quick_feature_slug)) else 0.7
                        elif "recovering-sessions" in lowered_command:
                            recover_feature_slug = feature_slug_from_path(str(parsed.get("featurePath") or ""))
                            signal_weight = 0.9 if (recover_feature_slug and _feature_slug_matches_feature(feature_id, recover_feature_slug)) else 0.72
                        signal_weights.append(signal_weight)
                        signal = {
                            "type": "command_args_path",
                            "path": str(parsed.get("featurePath") or (command_paths[0] if command_paths else "")),
                            "command": command_name,
                            "weight": signal_weight,
                        }
                        phase_token = parsed.get("phaseToken")
                        if isinstance(phase_token, str) and phase_token:
                            signal["phaseToken"] = phase_token
                        evidence.append(signal)

                base_confidence = _confidence_from_signals(signal_weights, has_command_path, False, has_write)
                if base_confidence <= 0:
                    continue

                raw_signal_weight = round(sum(signal_weights), 3)
                candidates.append({
                    "featureId": feature_id,
                    "baseConfidence": base_confidence,
                    "rawSignalWeight": raw_signal_weight,
                    "evidence": evidence,
                    "hasWrite": has_write,
                    "hasCommandPath": has_command_path,
                    "hasReadOnlySignals": has_read_reference and not has_write and not has_command_path,
                })

            total_signal_weight = sum(candidate["rawSignalWeight"] for candidate in candidates)
            for candidate in candidates:
                feature_id = candidate["featureId"]
                share = (
                    candidate["rawSignalWeight"] / total_signal_weight
                    if total_signal_weight > 0
                    else 0.0
                )
                confidence = float(candidate["baseConfidence"])
                if share < 0.50:
                    confidence -= 0.20
                elif share < 0.70:
                    confidence -= 0.10
                if candidate["hasReadOnlySignals"]:
                    confidence -= 0.08
                confidence = round(max(0.35, min(0.95, confidence)), 3)
                title, title_source, title_confidence = _derive_session_title(
                    feature_id,
                    custom_title,
                    latest_summary,
                    command_events,
                    command_names,
                    candidate["evidence"],
                    file_updates,
                )
                metadata = {
                    "linkStrategy": "session_evidence",
                    "signals": candidate["evidence"][:25],
                    "commands": ordered_commands[:15],
                    "commitHashes": sorted(session_commit_hashes),
                    "ambiguityShare": round(share, 3),
                    "title": title,
                    "titleSource": title_source,
                    "titleConfidence": round(title_confidence, 3),
                    "prLinks": pr_links[:10],
                    "queueEvents": queue_events[:10],
                }
                await self.link_repo.upsert({
                    "source_type": "feature",
                    "source_id": feature_id,
                    "target_type": "session",
                    "target_id": session_id,
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": confidence,
                    "metadata_json": json.dumps(metadata),
                })
                stats["created"] += 1

            if operation_id and (session_index == len(sessions_data) or session_index % 25 == 0):
                await self._update_operation(
                    operation_id,
                    phase="links:session-evidence",
                    message=f"Processed sessions {session_index}/{len(sessions_data)}",
                    progress={
                        "sessionsProcessed": session_index,
                        "sessionCount": len(sessions_data),
                    },
                    counters={"linksCreated": stats["created"]},
                )

        # Link documents ↔ features/tasks/sessions/documents from normalized metadata.
        docs = await self.document_repo.list_all(project_id)
        await self._update_operation(
            operation_id,
            phase="links:documents",
            message=f"Linking documents ({len(docs)} total)",
            progress={"documentCount": len(docs)},
        )
        tasks = await self.task_repo.list_all(project_id)
        sessions_by_id = {str(row.get("id") or ""): row for row in sessions_data}

        docs_by_path: dict[str, str] = {}
        for doc_row in docs:
            doc_path = normalize_ref_path(str(doc_row.get("file_path") or ""))
            if doc_path:
                docs_by_path[doc_path] = str(doc_row.get("id") or "")
                docs_by_path[doc_path.lstrip("/")] = str(doc_row.get("id") or "")

        tasks_by_source: dict[str, list[dict[str, Any]]] = {}
        for task_row in tasks:
            source_file = normalize_ref_path(str(task_row.get("source_file") or ""))
            if not source_file:
                continue
            tasks_by_source.setdefault(source_file, []).append(task_row)

        doc_feature_links: dict[str, set[str]] = {}
        doc_doc_links: dict[str, set[str]] = {}

        for doc_index, d in enumerate(docs, start=1):
            doc_id = str(d.get("id") or "")
            if not doc_id:
                continue
            await self.link_repo.delete_auto_links("document", doc_id)
            fm = d.get("frontmatter_json", "{}")
            try:
                fm_dict = json.loads(fm) if isinstance(fm, str) else fm
            except Exception:
                fm_dict = {}
            if not isinstance(fm_dict, dict):
                fm_dict = {}

            refs = extract_frontmatter_references(fm_dict)
            explicit_feature_refs: set[str] = set()
            linked_features = fm_dict.get("linkedFeatures", [])
            if isinstance(linked_features, str):
                linked_features = [linked_features]
            if isinstance(linked_features, list):
                for raw in linked_features:
                    if isinstance(raw, str) and raw.strip():
                        explicit_feature_refs.add(raw.strip())

            for raw in refs.get("featureRefs", []):
                if isinstance(raw, str) and raw.strip():
                    explicit_feature_refs.add(raw.strip())
            prd_ref = refs.get("prd")
            if isinstance(prd_ref, str) and prd_ref.strip():
                explicit_feature_refs.add(prd_ref.strip())

            path_hint_refs: set[str] = set()
            for token in (
                str(d.get("feature_slug_hint") or ""),
                str(d.get("feature_slug_canonical") or ""),
                feature_slug_from_path(str(d.get("file_path") or "")),
            ):
                if token:
                    path_hint_refs.add(token)

            resolved_feature_ids: set[str] = set()
            strategy = ""
            confidence = 0.0

            candidate_refs = list(explicit_feature_refs) if explicit_feature_refs else list(path_hint_refs)
            for raw_ref in candidate_refs:
                normalized = raw_ref.strip().lower()
                if not normalized:
                    continue
                candidate_slug = Path(normalized).stem.lower() if ("/" in normalized or normalized.endswith(".md")) else normalized
                inferred_slug = feature_slug_from_path(normalized)
                if inferred_slug:
                    candidate_slug = inferred_slug
                if not is_feature_like_token(candidate_slug):
                    continue
                if candidate_slug in feature_ids:
                    resolved_feature_ids.add(candidate_slug)
                base = _canonical_slug(candidate_slug)
                for resolved in feature_ids_by_base.get(base, set()):
                    resolved_feature_ids.add(resolved)

            if resolved_feature_ids:
                if explicit_feature_refs:
                    strategy = "explicit_frontmatter_ref"
                    confidence = 0.98
                else:
                    strategy = "path_feature_hint"
                    confidence = 0.74

            doc_feature_links[doc_id] = set()
            for feat_ref in sorted(resolved_feature_ids):
                doc_feature_links[doc_id].add(str(feat_ref))
                await self.link_repo.upsert({
                    "source_type": "document",
                    "source_id": doc_id,
                    "target_type": "feature",
                    "target_id": str(feat_ref),
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": confidence or 0.7,
                    "metadata_json": json.dumps({
                        "linkStrategy": strategy or "feature_ref",
                        "sourceFields": sorted(fm_dict.keys()),
                    }),
                })
                stats["created"] += 1

            # Document → Document links from path refs/file refs.
            linked_doc_ids: set[str] = set()
            for raw_ref in [*refs.get("pathRefs", []), *refs.get("fileRefs", [])]:
                if not isinstance(raw_ref, str):
                    continue
                normalized_ref = normalize_ref_path(raw_ref).lstrip("/")
                if not normalized_ref:
                    continue
                target_doc_id = docs_by_path.get(normalized_ref)
                if not target_doc_id:
                    # fallback: suffix match for mixed absolute vs relative references
                    for candidate_path, candidate_doc_id in docs_by_path.items():
                        if candidate_path.endswith(normalized_ref):
                            target_doc_id = candidate_doc_id
                            break
                if not target_doc_id or target_doc_id == doc_id:
                    continue
                linked_doc_ids.add(target_doc_id)
                await self.link_repo.upsert({
                    "source_type": "document",
                    "source_id": doc_id,
                    "target_type": "document",
                    "target_id": target_doc_id,
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": 0.9,
                    "metadata_json": json.dumps({
                        "linkStrategy": "document_ref_path",
                        "refPath": normalized_ref,
                    }),
                })
                stats["created"] += 1
            doc_doc_links[doc_id] = linked_doc_ids

            # Document → Task links (primarily progress documents).
            doc_source_path = normalize_ref_path(str(d.get("file_path") or "")).lstrip("/")
            for task_row in tasks_by_source.get(doc_source_path, []):
                task_id = str(task_row.get("id") or "")
                if not task_id:
                    continue
                await self.link_repo.upsert({
                    "source_type": "document",
                    "source_id": doc_id,
                    "target_type": "task",
                    "target_id": task_id,
                    "link_type": "child",
                    "origin": "auto",
                    "confidence": 1.0,
                    "metadata_json": json.dumps({
                        "linkStrategy": "progress_source_task",
                        "sourceFile": doc_source_path,
                    }),
                })
                stats["created"] += 1

                session_id = str(task_row.get("session_id") or "")
                if session_id:
                    await self.link_repo.upsert({
                        "source_type": "document",
                        "source_id": doc_id,
                        "target_type": "session",
                        "target_id": session_id,
                        "link_type": "related",
                        "origin": "auto",
                        "confidence": 0.96,
                        "metadata_json": json.dumps({
                            "linkStrategy": "task_session_ref",
                            "taskId": task_id,
                        }),
                    })
                    stats["created"] += 1

            # Explicit document → session refs.
            explicit_session_refs: set[str] = set()
            for raw in refs.get("sessionRefs", []):
                if isinstance(raw, str) and raw.strip():
                    explicit_session_refs.add(raw.strip())
            raw_linked_sessions = fm_dict.get("linkedSessions")
            if isinstance(raw_linked_sessions, str):
                explicit_session_refs.add(raw_linked_sessions.strip())
            elif isinstance(raw_linked_sessions, list):
                for raw in raw_linked_sessions:
                    if isinstance(raw, str) and raw.strip():
                        explicit_session_refs.add(raw.strip())

            for session_ref in sorted(explicit_session_refs):
                if session_ref not in sessions_by_id:
                    continue
                await self.link_repo.upsert({
                    "source_type": "document",
                    "source_id": doc_id,
                    "target_type": "session",
                    "target_id": session_ref,
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": 1.0,
                    "metadata_json": json.dumps({
                        "linkStrategy": "explicit_session_ref",
                    }),
                })
                stats["created"] += 1

            if operation_id and (doc_index == len(docs) or doc_index % 25 == 0):
                await self._update_operation(
                    operation_id,
                    phase="links:documents",
                    message=f"Linked documents {doc_index}/{len(docs)}",
                    progress={
                        "documentsProcessed": doc_index,
                        "documentCount": len(docs),
                    },
                    counters={"linksCreated": stats["created"]},
                )

        # Inherit feature links from referenced documents when direct refs are absent.
        for doc_id, linked_doc_ids in doc_doc_links.items():
            if doc_feature_links.get(doc_id):
                continue
            inherited: set[str] = set()
            for linked_doc_id in linked_doc_ids:
                inherited.update(doc_feature_links.get(linked_doc_id, set()))
            for feature_id in sorted(inherited):
                await self.link_repo.upsert({
                    "source_type": "document",
                    "source_id": doc_id,
                    "target_type": "feature",
                    "target_id": feature_id,
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": 0.64,
                    "metadata_json": json.dumps({
                        "linkStrategy": "referenced_document_inheritance",
                    }),
                })
                stats["created"] += 1
        await self._update_operation(
            operation_id,
            phase="links:catalog",
            message="Refreshing document catalog index",
            counters={"linksCreated": stats["created"]},
        )
        await _store_document_catalog_index()
        await self._update_operation(
            operation_id,
            phase="links:completed",
            message=f"Link rebuild generated {stats['created']} link(s)",
            stats={"links_created": stats["created"]},
        )
        return stats


    # ── Analytics Snapshot ──────────────────────────────────────────

    async def _capture_analytics(self, project_id: str) -> None:
        """Capture a point-in-time snapshot of project metrics."""
        now = datetime.now(timezone.utc).isoformat()
        
        async def insert_metric(
            metric_type: str,
            value: float | int,
            *,
            metadata: dict[str, Any] | None = None,
            entity_links: list[tuple[str, str]] | None = None,
        ) -> None:
            analytics_id = await self.analytics_repo.insert_entry({
                "project_id": project_id,
                "metric_type": metric_type,
                "value": value,
                "captured_at": now,
                "metadata_json": metadata or {},
            })
            links = entity_links or [("project", project_id)]
            for entity_type, entity_id in links:
                if entity_type and entity_id:
                    await self.analytics_repo.link_to_entity(analytics_id, entity_type, entity_id)

        # 1. Session Metrics
        s_stats = await self.session_repo.get_project_stats(project_id)
        
        await insert_metric("session_count", s_stats.get("count", 0), metadata={"scope": "project"})
        await insert_metric("session_cost", s_stats.get("cost", 0.0), metadata={"scope": "project", "unit": "usd"})
        await insert_metric("session_tokens", s_stats.get("tokens", 0), metadata={"scope": "project", "unit": "tokens"})
        await insert_metric("session_duration", s_stats.get("duration", 0.0), metadata={"scope": "project", "unit": "seconds"})

        # 2. Task Metrics
        t_stats = await self.task_repo.get_project_stats(project_id)

        await insert_metric(
            "task_velocity",
            t_stats.get("completed", 0),
            metadata={"scope": "project", "terminalStatuses": ["done", "deferred", "completed"]},
        )
        await insert_metric(
            "task_completion_pct",
            t_stats.get("completion_pct", 0.0),
            metadata={"scope": "project", "unit": "percent"},
        )

        # 3. Feature Progress
        f_stats = await self.feature_repo.get_project_stats(project_id)
        
        await insert_metric("feature_progress", f_stats.get("avg_progress", 0.0), metadata={"scope": "project", "unit": "percent"})

        # 4. Tool Usage
        tool_stats = await self.session_repo.get_tool_stats(project_id)
        
        await insert_metric("tool_call_count", tool_stats.get("calls", 0), metadata={"scope": "project"})
        await insert_metric("tool_success_rate", tool_stats.get("success_rate", 0.0), metadata={"scope": "project", "unit": "percent"})
