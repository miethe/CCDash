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
from backend.models import AgentSession, SessionLog, ToolCallInfo, ToolUsage

_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60
_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}
_URL_PATTERN = re.compile(r"https?://([a-zA-Z0-9.-]+)(?::(\d+))?")
_SSH_TARGET_PATTERN = re.compile(r"\b(?:ssh|scp|rsync)\b[^\n]*?\b([A-Za-z0-9._-]+@[A-Za-z0-9.-]+)")
_DB_TOOL_PATTERN = re.compile(r"\b(psql|mysql|sqlite3|mongosh|mongo|redis-cli|pg_dump|pg_restore)\b")
_DOCKER_PATTERN = re.compile(r"\bdocker(?:\s+compose|[- ]compose|\s+\w+)")
_SERVICE_PATTERN = re.compile(r"\b(pm2|systemctl)\b")
_COMMAND_TOOL_NAMES = {"exec_command", "shell_command", "shell"}
_FILE_READ_MARKERS = ("cat ", "sed -n", "head ", "tail ", "grep ", "rg ")
_FILE_UPDATE_MARKERS = ("apply_patch", "tee ", "echo ", "printf ", "cp ", "mv ", "touch ")
_FILE_DELETE_MARKERS = ("rm ", "unlink ")


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
    log_idx = 0

    def append_log(**kwargs: Any) -> int:
        nonlocal log_idx
        metadata = kwargs.get("metadata")
        if metadata is None or not isinstance(metadata, dict):
            kwargs["metadata"] = {}
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
            continue

        is_tool_result = payload_type in {"function_call_output", "custom_tool_call_output"} or entry_type_lower == "function_call_output"
        if is_tool_result:
            call_id = str(payload_dict.get("call_id") or entry.get("call_id") or "").strip()
            output_text = str(payload_dict.get("output") or entry.get("output") or "").strip()
            status = str(payload_dict.get("status") or "").strip().lower()
            is_error = status in {"error", "failed", "failure"}
            related_idx = tool_logs_by_call_id.get(call_id)
            if related_idx is not None:
                related_log = logs[related_idx]
                if related_log.toolCall:
                    related_log.toolCall.output = output_text[:20000]
                    related_log.toolCall.status = "error" if is_error else "success"
                    related_log.toolCall.isError = is_error
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
            else:
                append_log(
                    timestamp=timestamp,
                    speaker="system",
                    type="system",
                    content=f"Unmatched tool result for {call_id}: {output_text[:200]}",
                    metadata={"entryType": entry_type_lower, "payloadType": payload_type, "isError": is_error},
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
        "codexPayloadSignals": {
            "payloadTypeCounts": dict(payload_type_counts),
            "toolNameCounts": {tool.name: tool.count for tool in tools_used},
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
        impactHistory=[],
        logs=logs,
        thinkingLevel="",
        sessionForensics=session_forensics,
        dates=session_dates,
        timeline=timeline,
    )

