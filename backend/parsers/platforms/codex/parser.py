"""Parse Codex JSONL session logs into AgentSession models."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.date_utils import file_metadata_dates, make_date_value
from backend.models import AgentSession, ImpactPoint, SessionLog, ToolCallInfo, ToolUsage
from backend.parsers.platforms.test_runs import (
    aggregate_test_runs,
    enrich_test_run_with_output,
    flatten_test_run_metadata,
    parse_test_run_from_command,
)

_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60
_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}
_URL_PATTERN = re.compile(r"https?://([a-zA-Z0-9.-]+)(?::(\d+))?")
_SSH_TARGET_PATTERN = re.compile(r"\b(?:ssh|scp|rsync)\b[^\n]*?\b([A-Za-z0-9._-]+@[A-Za-z0-9.-]+)")
_DB_TOOL_PATTERN = re.compile(r"\b(psql|mysql|sqlite3|mongosh|mongo|redis-cli|pg_dump|pg_restore)\b")
_DOCKER_PATTERN = re.compile(r"\bdocker(?:\s+compose|[- ]compose|\s+\w+)")
_SERVICE_PATTERN = re.compile(r"\b(pm2|systemctl)\b")
_COMMAND_TOOL_NAMES = {"exec_command", "shell_command", "shell"}
_SUBAGENT_TOOL_NAMES = {"task", "agent"}
_COMMAND_NAME_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_SLASH_COMMAND_LINE_PATTERN = re.compile(
    r"(?m)^\s*(/[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)?)\b(?:\s+([^\n]+))?\s*$",
    re.IGNORECASE,
)
_TASK_ID_PATTERN = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z0-9]+)*-\d+(?:\.\d+)?)\b")
_AGENT_ID_OUTPUT_PATTERN = re.compile(r"\bagentid\s*:\s*([A-Za-z0-9._:-]+)\b", re.IGNORECASE)
_FILE_READ_MARKERS = ("cat ", "sed -n", "head ", "tail ", "grep ", "rg ")
_FILE_UPDATE_MARKERS = ("apply_patch", "tee ", "echo ", "printf ", "cp ", "mv ", "touch ")
_FILE_DELETE_MARKERS = ("rm ", "unlink ")


def _canonical_message_role(speaker: Any) -> str:
    normalized = str(speaker or "").strip().lower()
    if normalized == "agent":
        return "assistant"
    if normalized in {"user", "system", "assistant"}:
        return normalized
    return ""


def _codex_source_provenance(metadata: dict[str, Any]) -> str:
    payload_type = str(metadata.get("payloadType") or "").strip().lower()
    if payload_type in {"user_message", "agent_message", "message"}:
        return f"codex.{payload_type}"
    if payload_type in {"function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"}:
        return f"codex.{payload_type}"
    if payload_type in {"agent_reasoning", "reasoning"}:
        return f"codex.{payload_type}"
    entry_type = str(metadata.get("entryType") or "").strip().lower()
    if entry_type:
        return f"codex.{entry_type}"
    return "codex_jsonl"


def _codex_message_id(
    *,
    timestamp: str,
    speaker: Any,
    log_type: Any,
    content: Any,
    metadata: dict[str, Any],
    tool_call: ToolCallInfo | None,
    related_tool_call_id: Any,
) -> str:
    for key in ("rawMessageId", "entryUuid", "messageId"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    if tool_call and str(tool_call.id or "").strip():
        return str(tool_call.id).strip()
    related_id = str(related_tool_call_id or "").strip()
    if related_id:
        return related_id
    digest = hashlib.sha1(
        "|".join(
            [
                str(timestamp or "").strip(),
                str(speaker or "").strip().lower(),
                str(log_type or "").strip().lower(),
                str(metadata.get("entryType") or "").strip().lower(),
                str(metadata.get("payloadType") or "").strip().lower(),
                str(content or "").strip()[:200],
            ]
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"codex-{digest}"


def _normalize_session_id(raw_id: str) -> str:
    cleaned = str(raw_id or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("S-"):
        return cleaned
    if re.match(r"^[A-Za-z0-9._:-]+$", cleaned):
        return f"S-{cleaned}"
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:20]
    return f"S-{digest}"


def _make_id(path: Path) -> str:
    return _normalize_session_id(path.stem) or f"S-{hashlib.sha1(path.stem.encode('utf-8')).hexdigest()[:20]}"


def _parse_iso_ts(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_host(raw_host: str) -> str:
    return str(raw_host or "").strip().strip("[]").lower()


def _is_local_host(raw_host: str) -> bool:
    return _normalize_host(raw_host) in _LOCAL_HOSTS


def _normalize_path(raw_path: str) -> str:
    path = str(raw_path or "").strip().strip('"\'`<>[](),;')
    if not path:
        return ""
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("../"):
        return ""
    return path


def _extract_paths_from_text(text: str) -> list[str]:
    matches: list[str] = []
    for raw in _PATH_PATTERN.findall(str(text or "")):
        normalized = _normalize_path(raw)
        if normalized and "/" in normalized:
            matches.append(normalized)
    return matches


def _coerce_text_blob(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=True).strip()
    except Exception:
        return str(value).strip()


def _extract_task_id(*values: Any) -> str:
    for value in values:
        text = _coerce_text_blob(value)
        if not text:
            continue
        match = _TASK_ID_PATTERN.search(text)
        if match and match.group(1):
            return match.group(1)
    return ""


def _is_subagent_tool_name(name: str) -> bool:
    return str(name or "").strip().lower() in _SUBAGENT_TOOL_NAMES


def _extract_subagent_identifier(*values: Any) -> str:
    key_candidates = (
        "agent_session_id",
        "agentSessionId",
        "agent_id",
        "agentId",
        "subagent_id",
        "subagentId",
    )
    seen_ids: set[int] = set()
    queue: list[Any] = list(values)
    while queue:
        current = queue.pop(0)
        marker = id(current)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)

        if isinstance(current, dict):
            for key in key_candidates:
                raw = current.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            queue.extend(current.values())
            continue

        if isinstance(current, list):
            queue.extend(current)
            continue

        if isinstance(current, str):
            text = current.strip()
            if not text:
                continue
            if text.startswith("{") or text.startswith("["):
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if parsed is not None:
                    queue.append(parsed)
            for key in key_candidates:
                pattern = re.compile(rf'(?i)"{re.escape(key)}"\s*:\s*"([^"]+)"')
                match = pattern.search(text)
                if match and match.group(1).strip():
                    return match.group(1).strip()
            match = _AGENT_ID_OUTPUT_PATTERN.search(text)
            if match and match.group(1).strip():
                return match.group(1).strip()

    return ""


def _split_command_segments(command: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    depth = 0

    for ch in command:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            continue
        if in_single or in_double:
            current.append(ch)
            continue
        if ch in "({":
            depth += 1
            current.append(ch)
            continue
        if ch in ")}":
            depth = max(0, depth - 1)
            current.append(ch)
            continue
        if depth == 0 and ch in ";|":
            chunk = "".join(current).strip()
            if chunk:
                segments.append(chunk)
            current = []
            continue
        current.append(ch)

    chunk = "".join(current).strip()
    if chunk:
        segments.append(chunk)
    return segments


def _extract_resources_from_command(command: str) -> list[dict[str, str]]:
    resources: list[dict[str, str]] = []
    if not command.strip():
        return resources

    for segment in _split_command_segments(command):
        db_match = _DB_TOOL_PATTERN.search(segment)
        if db_match:
            tool = db_match.group(1)
            db_system_map = {
                "psql": "postgresql",
                "pg_dump": "postgresql",
                "pg_restore": "postgresql",
                "mysql": "mysql",
                "sqlite3": "sqlite",
                "mongosh": "mongodb",
                "mongo": "mongodb",
                "redis-cli": "redis",
            }
            db_system = db_system_map.get(tool, tool)
            host_match = re.search(r"(?:-h|--host)\s+([^\s]+)", segment)
            host = _normalize_host(host_match.group(1)) if host_match else "localhost"
            if "docker exec" in segment:
                host = "docker"
            resources.append({
                "category": "database",
                "target": f"{db_system}:{host or 'localhost'}",
                "scope": "internal" if _is_local_host(host) or host == "docker" else "external",
            })

        for url_match in _URL_PATTERN.finditer(segment):
            host = _normalize_host(url_match.group(1))
            port = url_match.group(2)
            target = f"{host}:{port}" if port else host
            resources.append({
                "category": "api",
                "target": target,
                "scope": "internal" if _is_local_host(host) else "external",
            })

        for ssh_match in _SSH_TARGET_PATTERN.finditer(segment):
            resources.append({"category": "ssh", "target": ssh_match.group(1), "scope": "external"})

        if _DOCKER_PATTERN.search(segment):
            resources.append({"category": "docker", "target": "docker", "scope": "internal"})

        service_match = _SERVICE_PATTERN.search(segment)
        if service_match:
            resources.append({
                "category": "service",
                "target": service_match.group(1),
                "scope": "internal",
            })

    return resources


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        for key in ("text", "content", "summary"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
                break
    return "\n".join(parts).strip()


def _extract_command_invocations(text: str) -> list[tuple[str, str]]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return []

    tag_names = [
        str(match.group(1) or "").strip()
        for match in _COMMAND_NAME_PATTERN.finditer(raw_text)
        if str(match.group(1) or "").strip()
    ]
    if tag_names:
        tag_args = [str(match.group(1) or "").strip() for match in _COMMAND_ARGS_PATTERN.finditer(raw_text)]
        pairs: list[tuple[str, str]] = []
        for idx, command_name in enumerate(tag_names):
            if not command_name.startswith("/"):
                continue
            args_text = tag_args[idx] if idx < len(tag_args) else ""
            pairs.append((command_name, args_text))
        if pairs:
            return pairs

    pairs = []
    seen: set[tuple[str, str]] = set()
    for match in _SLASH_COMMAND_LINE_PATTERN.finditer(raw_text):
        command_name = str(match.group(1) or "").strip()
        args_text = str(match.group(2) or "").strip()
        if not command_name.startswith("/"):
            continue
        key = (command_name.lower(), args_text)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((command_name, args_text))
    return pairs


def _looks_like_codex(path: Path, entries: list[dict[str, Any]]) -> bool:
    path_lower = str(path).lower()
    if "/.codex/sessions/" in path_lower:
        return True
    for entry in entries[:5]:
        payload = entry.get("payload")
        if entry.get("type") in {"response_item", "turn_context", "event_msg", "session_meta"} and isinstance(payload, dict):
            return True
    return False


def _derive_status(entries: list[dict[str, Any]], path: Path) -> str:
    for entry in reversed(entries[-20:]):
        payload = entry.get("payload")
        payload_type = str(payload.get("type") or "").strip().lower() if isinstance(payload, dict) else ""
        if payload_type in {"task_complete", "turn_aborted"}:
            return "completed"

    try:
        age_seconds = max(0.0, time.time() - float(path.stat().st_mtime))
    except Exception:
        age_seconds = float("inf")
    return "active" if age_seconds <= _ACTIVE_SESSION_WINDOW_SECONDS else "completed"


def parse_session_file(path: Path) -> AgentSession | None:
    """Parse a Codex JSONL transcript file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    if not lines:
        return None

    entries: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    if not entries:
        return None
    if not _looks_like_codex(path, entries):
        return None

    fs_dates = file_metadata_dates(path)
    session_status = _derive_status(entries, path)
    session_id = _make_id(path)
    raw_session_id = path.stem
    model = ""
    platform_version = ""
    platform_versions: list[str] = []
    platform_versions_seen: set[str] = set()
    tokens_in = 0
    tokens_out = 0
    first_ts = ""
    last_ts = ""

    logs: list[SessionLog] = []
    tool_counter: Counter[str] = Counter()
    tool_success: Counter[str] = Counter()
    tool_total: Counter[str] = Counter()
    tool_duration_ms: Counter[str] = Counter()
    impacts: list[ImpactPoint] = []
    updated_files: list[dict[str, Any]] = []
    linked_artifacts: list[dict[str, Any]] = []

    entry_type_counts: Counter[str] = Counter()
    payload_type_counts: Counter[str] = Counter()
    payload_key_counts: Counter[str] = Counter()
    content_type_counts: Counter[str] = Counter()
    working_directories: set[str] = set()
    models_seen: set[str] = set()
    call_ids: set[str] = set()

    resource_observations: list[dict[str, Any]] = []
    resource_seen: set[tuple[str, str, str, str]] = set()
    tool_logs_by_call_id: dict[str, int] = {}
    tool_started_at_by_call_id: dict[str, str] = {}
    emitted_subagent_starts: set[tuple[str, str]] = set()
    log_idx = 0

    def append_log(**kwargs: Any) -> int:
        nonlocal log_idx
        metadata = kwargs.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        speaker = kwargs.get("speaker")
        role = _canonical_message_role(speaker)
        if role:
            metadata.setdefault("messageRole", role)
        metadata.setdefault("sourceProvenance", _codex_source_provenance(metadata))
        tool_call = kwargs.get("toolCall")
        if isinstance(tool_call, ToolCallInfo):
            if tool_call.args not in (None, ""):
                metadata.setdefault("toolArgs", tool_call.args)
            if tool_call.output not in (None, ""):
                metadata.setdefault("toolOutput", tool_call.output)
            resolved_status = str(tool_call.status or ("error" if tool_call.isError else "success")).strip()
            if resolved_status:
                metadata.setdefault("toolStatus", resolved_status)
        metadata.setdefault(
            "messageId",
            _codex_message_id(
                timestamp=str(kwargs.get("timestamp") or ""),
                speaker=speaker,
                log_type=kwargs.get("type"),
                content=kwargs.get("content"),
                metadata=metadata,
                tool_call=tool_call if isinstance(tool_call, ToolCallInfo) else None,
                related_tool_call_id=kwargs.get("relatedToolCallId"),
            ),
        )
        kwargs["metadata"] = metadata
        log = SessionLog(id=f"log-{log_idx}", **kwargs)
        logs.append(log)
        log_idx += 1
        return len(logs) - 1

    def register_resources(command_text: str, source_log_id: str, source: str, timestamp: str) -> list[dict[str, str]]:
        extracted = _extract_resources_from_command(command_text)
        for item in extracted:
            category = str(item.get("category") or "")
            target = str(item.get("target") or "")
            scope = str(item.get("scope") or "")
            unique = (category, target, scope, source_log_id)
            if unique in resource_seen:
                continue
            resource_seen.add(unique)
            resource_observations.append({
                "timestamp": timestamp,
                "source": source,
                "sourceLogId": source_log_id,
                "category": category,
                "target": target,
                "scope": scope,
            })
        return extracted

    def track_file_actions_from_command(command_text: str, source_log_id: str, timestamp: str, tool_name: str) -> None:
        command = command_text.strip()
        if not command:
            return
        normalized = command.lower()
        action = ""
        if any(marker in normalized for marker in _FILE_DELETE_MARKERS):
            action = "delete"
        elif any(marker in normalized for marker in _FILE_UPDATE_MARKERS):
            action = "update"
        elif any(marker in normalized for marker in _FILE_READ_MARKERS):
            action = "read"
        if not action:
            return
        for file_path in _extract_paths_from_text(command)[:8]:
            updated_files.append(
                {
                    "filePath": file_path,
                    "additions": 0,
                    "deletions": 0,
                    "commits": [],
                    "agentName": "",
                    "action": action,
                    "fileType": "Other",
                    "timestamp": timestamp,
                    "sourceLogId": source_log_id,
                    "sourceToolName": tool_name,
                    "threadSessionId": session_id,
                    "rootSessionId": session_id,
                }
            )

    def add_artifact(
        kind: str,
        title: str,
        description: str,
        source: str,
        source_log_id: str | None,
        source_tool_name: str | None,
        url: str | None = None,
    ) -> str | None:
        clean_title = str(title or "").strip()
        if not clean_title:
            return None
        artifact_id = hashlib.sha1(
            f"{session_id}|{kind}|{clean_title}|{source_log_id or ''}".encode("utf-8")
        ).hexdigest()[:24]
        existing = next((item for item in linked_artifacts if str(item.get("id") or "") == artifact_id), None)
        if existing:
            if description and not existing.get("description"):
                existing["description"] = description
            if source_tool_name and not existing.get("sourceToolName"):
                existing["sourceToolName"] = source_tool_name
            if url and not existing.get("url"):
                existing["url"] = url
            return artifact_id
        linked_artifacts.append(
            {
                "id": artifact_id,
                "title": clean_title,
                "type": kind,
                "description": description,
                "source": source,
                "url": url,
                "sourceLogId": source_log_id,
                "sourceToolName": source_tool_name,
            }
        )
        return artifact_id

    def add_test_run_artifacts(test_run: dict[str, Any], source_log_id: str, source_tool_name: str) -> None:
        framework = str(test_run.get("framework") or "test").strip() or "test"
        primary_domain = str(test_run.get("primaryDomain") or "").strip()
        target_count = _coerce_int(test_run.get("targetCount"), 0)
        targets = test_run.get("targets") if isinstance(test_run.get("targets"), list) else []
        result = test_run.get("result") if isinstance(test_run.get("result"), dict) else {}
        status = str(result.get("status") or "").strip().lower()
        counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
        passed = _coerce_int(counts.get("passed"), 0)
        failed = _coerce_int(counts.get("failed"), 0) + _coerce_int(counts.get("error"), 0) + _coerce_int(counts.get("xpassed"), 0)

        title_parts = [framework]
        if primary_domain:
            title_parts.append(primary_domain)
        if target_count > 0:
            title_parts.append(f"{target_count} target(s)")
        title = " | ".join(title_parts)

        description = f"{framework} test run"
        if status:
            description = f"{description} ({status})"
        if passed > 0 or failed > 0:
            description = f"{description}: {passed} passed, {failed} failed-like"

        add_artifact(
            kind="test_run",
            title=title[:200],
            description=description[:500],
            source="tool",
            source_log_id=source_log_id,
            source_tool_name=source_tool_name,
        )

        domains = test_run.get("domains") if isinstance(test_run.get("domains"), list) else []
        for domain in domains[:8]:
            domain_name = str(domain or "").strip()
            if not domain_name:
                continue
            add_artifact(
                kind="test_domain",
                title=domain_name,
                description=f"Test domain inferred from {framework} command",
                source="tool",
                source_log_id=source_log_id,
                source_tool_name=source_tool_name,
            )

        for target in targets[:16]:
            target_name = str(target or "").strip()
            if not target_name:
                continue
            add_artifact(
                kind="test_target",
                title=target_name[:300],
                description=f"Test target executed via {framework}",
                source="tool",
                source_log_id=source_log_id,
                source_tool_name=source_tool_name,
            )

    def link_subagent_to_tool_call(
        call_id: str,
        raw_agent_id: str,
        event_timestamp: str,
        source: str,
    ) -> None:
        clean = str(raw_agent_id or "").strip()
        if not clean:
            return
        if clean.lower().startswith("agent-"):
            clean = clean.split("agent-", 1)[-1] or clean

        linked_session = _normalize_session_id(f"agent-{clean}")
        tool_log_idx = tool_logs_by_call_id.get(call_id)
        subagent_name = ""
        source_tool_name = "Agent"
        if tool_log_idx is not None:
            tool_log = logs[tool_log_idx]
            tool_log.linkedSessionId = linked_session
            tool_log.metadata["subagentAgentId"] = clean
            subagent_name = str(tool_log.metadata.get("taskSubagentType") or "").strip()
            if tool_log.toolCall and tool_log.toolCall.name:
                source_tool_name = str(tool_log.toolCall.name)

        emit_key = (call_id, linked_session)
        if emit_key in emitted_subagent_starts:
            return
        emitted_subagent_starts.add(emit_key)

        metadata: dict[str, Any] = {"agentId": clean}
        if subagent_name:
            metadata["subagentName"] = subagent_name
            metadata["subagentType"] = subagent_name

        start_idx = append_log(
            timestamp=event_timestamp,
            speaker="system",
            type="subagent_start",
            content=f"Subagent started: {clean}",
            linkedSessionId=linked_session,
            relatedToolCallId=call_id,
            metadata=metadata,
        )
        start_title = subagent_name or f"agent-{clean}"
        add_artifact(
            kind="agent",
            title=start_title,
            description="Subagent thread spawned from an Agent/Task tool call",
            source=source,
            source_log_id=logs[start_idx].id,
            source_tool_name=source_tool_name,
        )

    for entry in entries:
        entry_type = str(entry.get("type") or "").strip()
        entry_type_lower = entry_type.lower() or "unknown"
        entry_type_counts[entry_type_lower] += 1

        timestamp = str(entry.get("timestamp") or "").strip()
        if timestamp and not first_ts:
            first_ts = timestamp
        if timestamp:
            last_ts = timestamp

        payload = entry.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        payload_type = str(payload_dict.get("type") or "").strip().lower()
        if payload_type:
            payload_type_counts[payload_type] += 1
        for key in payload_dict.keys():
            payload_key_counts[str(key)] += 1

        cwd = str(payload_dict.get("cwd") or "").strip()
        if cwd:
            working_directories.add(cwd)
        model_value = str(payload_dict.get("model") or "").strip()
        if model_value:
            model = model_value
            models_seen.add(model_value)
        model_provider = str(payload_dict.get("model_provider") or "").strip()
        if model_provider:
            models_seen.add(model_provider)
        cli_version = str(payload_dict.get("cli_version") or "").strip()
        if cli_version:
            platform_version = cli_version
            if cli_version not in platform_versions_seen:
                platform_versions_seen.add(cli_version)
                platform_versions.append(cli_version)

        if entry_type_lower == "turn_context":
            line_model = str(payload_dict.get("model") or "").strip()
            if line_model:
                model = line_model
                models_seen.add(line_model)

        if payload_type in {"message", "agent_message", "user_message"}:
            role = str(payload_dict.get("role") or "").strip().lower()
            speaker = "agent" if role in {"assistant", "agent"} else "user"
            text = _extract_message_text(payload_dict.get("content"))
            if not text:
                text = str(payload_dict.get("message") or payload_dict.get("text") or "").strip()
            if text:
                if isinstance(payload_dict.get("content"), list):
                    for block in payload_dict.get("content", []):
                        if isinstance(block, dict):
                            block_type = str(block.get("type") or "").strip()
                            if block_type:
                                content_type_counts[block_type] += 1
                append_log(
                    timestamp=timestamp,
                    speaker=speaker,
                    type="message",
                    content=text[:8000],
                    metadata={"entryType": entry_type_lower, "payloadType": payload_type},
                )
                command_invocations = _extract_command_invocations(text)
                for command_name, args_text in command_invocations:
                    command_metadata: dict[str, Any] = {
                        "entryType": entry_type_lower,
                        "payloadType": payload_type,
                        "origin": "codex-message",
                    }
                    if args_text:
                        command_metadata["args"] = args_text[:4000]
                    append_log(
                        timestamp=timestamp,
                        speaker=speaker,
                        type="command",
                        content=command_name[:200],
                        metadata=command_metadata,
                    )
            continue

        if payload_type in {"agent_reasoning", "reasoning"}:
            reasoning_text = str(payload_dict.get("text") or payload_dict.get("summary") or "").strip()
            if reasoning_text:
                append_log(
                    timestamp=timestamp,
                    speaker="agent",
                    type="thought",
                    content=reasoning_text[:8000],
                    metadata={"entryType": entry_type_lower, "payloadType": payload_type},
                )
            continue

        is_tool_call = payload_type in {"function_call", "custom_tool_call"} or entry_type_lower == "function_call"
        if is_tool_call:
            tool_name = str(payload_dict.get("name") or entry.get("name") or "tool").strip()
            call_id = str(payload_dict.get("call_id") or entry.get("call_id") or payload_dict.get("id") or "").strip()
            if call_id:
                call_ids.add(call_id)
            args_raw = payload_dict.get("arguments")
            if args_raw is None:
                args_raw = payload_dict.get("input")

            args_payload = args_raw
            if isinstance(args_raw, str):
                try:
                    args_payload = json.loads(args_raw)
                except Exception:
                    args_payload = args_raw

            args_text = ""
            if isinstance(args_payload, (dict, list)):
                try:
                    args_text = json.dumps(args_payload, ensure_ascii=True, indent=2)[:12000]
                except Exception:
                    args_text = str(args_payload)[:12000]
            else:
                args_text = str(args_payload or "")[:12000]

            idx = append_log(
                timestamp=timestamp,
                speaker="agent",
                type="tool",
                content=f"Called {tool_name}",
                metadata={"entryType": entry_type_lower, "payloadType": payload_type},
                toolCall=ToolCallInfo(
                    id=call_id or None,
                    name=tool_name,
                    args=args_text,
                    status="success",
                    isError=False,
                ),
            )
            tool_log = logs[idx]
            if call_id:
                tool_logs_by_call_id[call_id] = idx
                tool_started_at_by_call_id[call_id] = timestamp

            tool_counter[tool_name] += 1
            tool_total[tool_name] += 1
            tool_success[tool_name] += 1

            if tool_name in _COMMAND_TOOL_NAMES and isinstance(args_payload, dict):
                command = str(args_payload.get("command") or args_payload.get("cmd") or "").strip()
                if command:
                    tool_log.metadata["bashCommand"] = command[:4000]
                    resource_signals = register_resources(command, tool_log.id, "tool.call", timestamp)
                    if resource_signals:
                        tool_log.metadata["resourceSignals"] = resource_signals[:20]
                    track_file_actions_from_command(command, tool_log.id, timestamp, tool_name)
                    test_run = parse_test_run_from_command(
                        command,
                        description=args_payload.get("description"),
                        timeout=args_payload.get("timeout"),
                    )
                    if test_run:
                        tool_log.metadata["toolCategory"] = "test"
                        tool_log.metadata["toolLabel"] = str(test_run.get("framework") or "test")
                        tool_log.metadata.update(flatten_test_run_metadata(test_run))
                        add_test_run_artifacts(test_run, tool_log.id, tool_name)

            if str(tool_name or "").strip().lower() == "skill" and isinstance(args_payload, dict):
                skill_name = str(args_payload.get("skill") or args_payload.get("name") or "").strip()
                if skill_name:
                    tool_log.metadata["toolCategory"] = "skill"
                    tool_log.metadata["toolLabel"] = skill_name
                    add_artifact(
                        kind="skill",
                        title=skill_name,
                        description="Skill invocation in transcript",
                        source="tool",
                        source_log_id=tool_log.id,
                        source_tool_name=tool_name,
                    )

            if _is_subagent_tool_name(tool_name) and isinstance(args_payload, dict):
                subagent_type = str(
                    args_payload.get("subagent_type")
                    or args_payload.get("subagentType")
                    or args_payload.get("agent_name")
                    or args_payload.get("agentName")
                    or ""
                ).strip()
                task_name = str(args_payload.get("name") or "").strip()
                task_description = str(args_payload.get("description") or "").strip()
                task_prompt = _coerce_text_blob(args_payload.get("prompt"))
                task_mode = str(args_payload.get("mode") or "").strip()
                task_model = str(args_payload.get("model") or "").strip()

                if subagent_type:
                    tool_log.metadata["taskSubagentType"] = subagent_type
                    tool_log.metadata["toolCategory"] = "agent"
                    tool_log.metadata["toolLabel"] = subagent_type
                if task_name:
                    tool_log.metadata["taskName"] = task_name[:240]
                if task_description:
                    tool_log.metadata["taskDescription"] = task_description[:500]
                if task_prompt:
                    tool_log.metadata["taskPromptPreview"] = task_prompt[:500]
                    tool_log.metadata["taskPromptLength"] = len(task_prompt)
                if task_mode:
                    tool_log.metadata["taskMode"] = task_mode[:120]
                if task_model:
                    tool_log.metadata["taskModel"] = task_model[:120]

                run_in_background = args_payload.get("run_in_background")
                if isinstance(run_in_background, bool):
                    tool_log.metadata["taskRunInBackground"] = run_in_background
                elif isinstance(run_in_background, str):
                    lowered = run_in_background.strip().lower()
                    if lowered in {"true", "false"}:
                        tool_log.metadata["taskRunInBackground"] = lowered == "true"

                add_artifact(
                    kind="agent",
                    title=subagent_type or "Agent subagent",
                    description=f"{tool_name} tool invocation that may spawn a subagent",
                    source="tool",
                    source_log_id=tool_log.id,
                    source_tool_name=tool_name,
                )

                task_id = _extract_task_id(task_name, task_description, task_prompt)
                if task_id:
                    tool_log.metadata["taskId"] = task_id
                    task_summary = task_description or task_name or task_prompt
                    add_artifact(
                        kind="task",
                        title=task_id,
                        description=(task_summary or "Task tool invocation")[:500],
                        source="tool",
                        source_log_id=tool_log.id,
                        source_tool_name=tool_name,
                    )
            continue

        is_tool_result = payload_type in {"function_call_output", "custom_tool_call_output"} or entry_type_lower == "function_call_output"
        if is_tool_result:
            call_id = str(payload_dict.get("call_id") or entry.get("call_id") or "").strip()
            output_raw = payload_dict.get("output")
            if output_raw is None:
                output_raw = entry.get("output")
            output_text = _coerce_text_blob(output_raw)
            status = str(payload_dict.get("status") or "").strip().lower()
            is_error = status in {"error", "failed", "failure"}
            related_idx = tool_logs_by_call_id.get(call_id)
            if related_idx is not None:
                related_log = logs[related_idx]
                if related_log.toolCall:
                    related_log.toolCall.output = output_text[:20000]
                    related_log.toolCall.status = "error" if is_error else "success"
                    related_log.toolCall.isError = is_error
                related_log.metadata["toolOutput"] = output_text[:20000]
                related_log.metadata["toolStatus"] = "error" if is_error else "success"
                related_log.relatedToolCallId = call_id or None
                if is_error and related_log.toolCall:
                    tool_success[related_log.toolCall.name] -= 1
                started_at = tool_started_at_by_call_id.get(call_id, "")
                started_ts = _parse_iso_ts(started_at)
                finished_ts = _parse_iso_ts(timestamp)
                if started_ts and finished_ts and related_log.toolCall:
                    elapsed_ms = max(0, int((finished_ts - started_ts).total_seconds() * 1000))
                    tool_duration_ms[related_log.toolCall.name] += elapsed_ms
                    related_log.metadata["durationMs"] = elapsed_ms
                if (
                    call_id
                    and related_log.toolCall
                    and _is_subagent_tool_name(str(related_log.toolCall.name or ""))
                ):
                    launched_agent_id = _extract_subagent_identifier(payload_dict, output_raw, output_text)
                    if launched_agent_id:
                        link_subagent_to_tool_call(call_id, launched_agent_id, timestamp, "tool-result")
                    related_log.metadata["taskLaunchStatus"] = status
                    is_async = payload_dict.get("is_async")
                    if is_async is None:
                        is_async = payload_dict.get("isAsync")
                    if isinstance(is_async, bool):
                        related_log.metadata["taskIsAsyncLaunch"] = is_async
                if related_log.toolCall and str(related_log.toolCall.name or "").strip().lower() in _COMMAND_TOOL_NAMES:
                    command_text = str(related_log.metadata.get("bashCommand") or "").strip()
                    if not command_text and isinstance(related_log.toolCall.args, str):
                        try:
                            raw_args = json.loads(related_log.toolCall.args)
                        except Exception:
                            raw_args = {}
                        if isinstance(raw_args, dict):
                            command_text = str(raw_args.get("command") or raw_args.get("cmd") or "").strip()
                    base_test_run = related_log.metadata.get("testRun")
                    if not isinstance(base_test_run, dict) and command_text:
                        base_test_run = parse_test_run_from_command(command_text)
                    enriched_test_run = enrich_test_run_with_output(
                        base_test_run if isinstance(base_test_run, dict) else None,
                        output_text,
                        is_error=is_error,
                    )
                    if enriched_test_run:
                        related_log.metadata["toolCategory"] = "test"
                        related_log.metadata["toolLabel"] = str(enriched_test_run.get("framework") or "test")
                        related_log.metadata.update(flatten_test_run_metadata(enriched_test_run))
                        add_test_run_artifacts(
                            enriched_test_run,
                            related_log.id,
                            str(related_log.toolCall.name or "tool"),
                        )
                        if timestamp:
                            result_payload = enriched_test_run.get("result") if isinstance(enriched_test_run.get("result"), dict) else {}
                            framework = str(enriched_test_run.get("framework") or "test").strip() or "test"
                            status_label = str(result_payload.get("status") or "").strip().lower() or ("failed" if is_error else "completed")
                            total = _coerce_int(result_payload.get("total"), 0)
                            failed_count = _coerce_int((result_payload.get("counts") or {}).get("failed") if isinstance(result_payload.get("counts"), dict) else 0, 0)
                            error_count = _coerce_int((result_payload.get("counts") or {}).get("error") if isinstance(result_payload.get("counts"), dict) else 0, 0)
                            impact_type = "error" if status_label in {"failed", "error"} else "success"
                            suffix = []
                            if total > 0:
                                suffix.append(f"{total} tests")
                            if failed_count > 0 or error_count > 0:
                                suffix.append(f"{failed_count + error_count} failing")
                            label = f"{framework} run {status_label}"
                            if suffix:
                                label = f"{label} ({', '.join(suffix)})"
                            impacts.append(
                                ImpactPoint(
                                    timestamp=timestamp,
                                    label=label[:200],
                                    type=impact_type,
                                )
                            )
            else:
                append_log(
                    timestamp=timestamp,
                    speaker="system",
                    type="system",
                    content=f"Unmatched tool result for {call_id}: {output_text[:200]}",
                    metadata={"entryType": entry_type_lower, "payloadType": payload_type, "isError": is_error},
                )
                if timestamp:
                    impacts.append(
                        ImpactPoint(
                            timestamp=timestamp,
                            label=f"Unmatched tool result for {call_id}"[:200],
                            type="warning" if is_error else "info",
                        )
                    )
            continue

        if entry_type_lower == "event_msg":
            summary_text = str(payload_dict.get("summary") or payload_dict.get("message") or payload_dict.get("text") or "").strip()
            if payload_type in {"task_started", "task_complete", "turn_aborted", "context_compacted", "item_completed", "thread_rolled_back"}:
                append_log(
                    timestamp=timestamp,
                    speaker="system",
                    type="system",
                    content=summary_text or payload_type,
                    metadata={"entryType": entry_type_lower, "payloadType": payload_type},
                )
            if timestamp and (summary_text or payload_type):
                impact_type = "info"
                if payload_type in {"turn_aborted"}:
                    impact_type = "error"
                elif payload_type in {"task_complete", "item_completed"}:
                    impact_type = "success"
                elif payload_type in {"context_compacted", "thread_rolled_back"}:
                    impact_type = "warning"
                impacts.append(
                    ImpactPoint(
                        timestamp=timestamp,
                        label=(summary_text or payload_type)[:200],
                        type=impact_type,
                    )
                )
            continue

    duration = 0
    if first_ts and last_ts:
        started_ts = _parse_iso_ts(first_ts)
        ended_ts = _parse_iso_ts(last_ts)
        if started_ts and ended_ts:
            duration = max(0, int((ended_ts - started_ts).total_seconds()))

    tools_used: list[ToolUsage] = []
    for tool_name, count in tool_counter.most_common():
        total = tool_total.get(tool_name, count)
        success = max(0, tool_success.get(tool_name, count))
        success_rate = success / total if total > 0 else 1.0
        tools_used.append(
            ToolUsage(
                name=tool_name,
                count=count,
                successRate=round(success_rate, 2),
                totalMs=max(0, int(tool_duration_ms.get(tool_name, 0))),
            )
        )

    resource_category_counts: Counter[str] = Counter()
    resource_scope_counts: Counter[str] = Counter()
    resource_target_counts: Counter[str] = Counter()
    for item in resource_observations:
        category = str(item.get("category") or "").strip()
        target = str(item.get("target") or "").strip()
        scope = str(item.get("scope") or "").strip()
        if category:
            resource_category_counts[category] += 1
        if scope:
            resource_scope_counts[scope] += 1
        if category and target:
            resource_target_counts[f"{category}:{target}"] += 1

    extracted_test_runs: list[dict[str, Any]] = []
    for log in logs:
        if log.type != "tool":
            continue
        metadata = log.metadata if isinstance(log.metadata, dict) else {}
        raw_test_run = metadata.get("testRun")
        if not isinstance(raw_test_run, dict):
            continue
        test_run = dict(raw_test_run)
        test_run["sourceLogId"] = log.id
        if log.toolCall and log.toolCall.name:
            test_run["toolName"] = str(log.toolCall.name)
        extracted_test_runs.append(test_run)
    test_execution = aggregate_test_runs(extracted_test_runs)

    session_forensics = {
        "platform": "codex",
        "schemaVersion": 1,
        "rawSessionId": raw_session_id,
        "sessionFile": str(path),
        "entryContext": {
            "workingDirectories": sorted(working_directories),
            "models": sorted(models_seen),
            "callIds": sorted(call_ids)[:400],
            "entryTypeCounts": dict(entry_type_counts),
            "payloadTypeCounts": dict(payload_type_counts),
            "payloadKeyCounts": dict(payload_key_counts),
            "contentBlockTypeCounts": dict(content_type_counts),
            "toolNames": {tool.name: tool.count for tool in tools_used},
        },
        "resourceFootprint": {
            "totalObservations": len(resource_observations),
            "categories": dict(resource_category_counts),
            "scopes": dict(resource_scope_counts),
            "topTargets": [
                {"target": target, "count": count}
                for target, count in resource_target_counts.most_common(40)
            ],
            "observations": resource_observations[:200],
        },
        "testExecution": test_execution,
        "codexPayloadSignals": {
            "payloadTypeCounts": dict(payload_type_counts),
            "toolNameCounts": {tool.name: tool.count for tool in tools_used},
        },
        "analysisSignals": {
            "hasResourceSignals": bool(resource_observations),
            "hasTestRunSignals": bool(_coerce_int(test_execution.get("runCount"), 0) > 0),
        },
    }

    session_dates: dict[str, Any] = {}
    for key, candidate in (
        ("createdAt", make_date_value(fs_dates.get("createdAt", ""), "high", "filesystem", "session_file_created")),
        ("updatedAt", make_date_value(fs_dates.get("updatedAt", ""), "high", "filesystem", "session_file_modified")),
        ("startedAt", make_date_value(first_ts, "high", "session", "first_log_event")),
        ("completedAt", make_date_value(last_ts, "high", "session", "last_log_event")),
        ("endedAt", make_date_value(last_ts, "high", "session", "last_log_event")),
        ("lastActivityAt", make_date_value(last_ts or fs_dates.get("updatedAt", ""), "high", "session", "last_activity")),
    ):
        if candidate:
            session_dates[key] = candidate

    timeline = []
    if first_ts:
        timeline.append({
            "id": "session-started",
            "timestamp": first_ts,
            "label": "Session Started",
            "kind": "started",
            "confidence": "high",
            "source": "session",
            "description": "First session log event",
        })
    if last_ts:
        timeline.append({
            "id": "session-completed",
            "timestamp": last_ts,
            "label": "Session Completed",
            "kind": "completed",
            "confidence": "high",
            "source": "session",
            "description": "Last session log event",
        })

    return AgentSession(
        id=session_id,
        taskId="",
        status=session_status,
        model=model,
        platformType="Codex",
        platformVersion=platform_version,
        platformVersions=platform_versions,
        sessionType="session",
        parentSessionId=None,
        rootSessionId=session_id,
        agentId=None,
        durationSeconds=duration,
        tokensIn=tokens_in,
        tokensOut=tokens_out,
        totalCost=0.0,
        startedAt=first_ts,
        endedAt=last_ts,
        createdAt=fs_dates.get("createdAt", ""),
        updatedAt=fs_dates.get("updatedAt", ""),
        gitBranch=None,
        gitAuthor=None,
        gitCommitHash=None,
        gitCommitHashes=[],
        updatedFiles=updated_files,
        linkedArtifacts=linked_artifacts,
        toolsUsed=tools_used,
        impactHistory=impacts,
        logs=logs,
        thinkingLevel="",
        sessionForensics=session_forensics,
        dates=session_dates,
        timeline=timeline,
    )
