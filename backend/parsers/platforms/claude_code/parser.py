"""Parse JSONL session log files into AgentSession models."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import time
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.models import (
    AgentSession,
    ImpactPoint,
    SessionArtifact,
    SessionFileUpdate,
    SessionLog,
    SessionPlatformTransition,
    ToolCallInfo,
    ToolUsage,
)
from backend.date_utils import file_metadata_dates, make_date_value
from backend.parsers.platforms.test_runs import (
    aggregate_test_runs,
    enrich_test_run_with_output,
    flatten_test_run_metadata,
    parse_test_run_from_command,
)

_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_COMMAND_NAME_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_SKILL_FORMAT_PATTERN = re.compile(r"<skill-format>\s*true\s*</skill-format>", re.IGNORECASE)
_SKILL_BASE_DIR_PATTERN = re.compile(r"^\s*Base directory for this skill:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_COMMIT_BRACKET_PATTERN = re.compile(r"\[[^\]\n]*\s([0-9a-f]{7,40})\]", re.IGNORECASE)
_COMMIT_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
_REQ_ID_PATTERN = re.compile(r"\bREQ-\d{8}-[A-Za-z0-9-]+-\d+\b")
_VERSION_SUFFIX_PATTERN = re.compile(r"-v\d+(?:\.\d+)?$", re.IGNORECASE)
_PLACEHOLDER_PATH_PATTERN = re.compile(r"(\*|\$\{[^}]+\}|<[^>]+>|\{[^{}]+\})")
_ASYNC_TASK_AGENT_ID_PATTERN = re.compile(r"\bagentid\s*:\s*([A-Za-z0-9_-]+)\b", re.IGNORECASE)
_TASK_ID_PATTERN = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z0-9]+)*-\d+(?:\.\d+)?)\b")
_BATCH_HEADER_PATTERN = re.compile(r"(?:\*\*)?\s*Batch\s+([A-Za-z0-9_-]+)\s*(?:\*\*)?", re.IGNORECASE)
_BATCH_BULLET_PATTERN = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*\s*:\s*(.+?)\s*$")
_MODEL_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,}$")
_HOOK_PATH_FRAGMENT_PATTERN = re.compile(r"\.claude/hooks/[A-Za-z0-9._-]+", re.IGNORECASE)
_MODEL_COMMAND_STOPWORDS = {"set", "to", "use", "default", "auto", "list", "show", "current", "model"}
_SUBAGENT_TOOL_NAMES = {"task", "agent"}

# Tools we treat as concrete file actions for session file tracking.
_FILE_ACTION_BY_TOOL: dict[str, str] = {
    "Read": "read",
    "ReadFile": "read",
    "Write": "update",
    "WriteFile": "update",
    "Edit": "update",
    "MultiEdit": "update",
    "Delete": "delete",
    "DeleteFile": "delete",
}

# Basenames we treat as structured artifacts/manifests.
_MANIFEST_BASENAMES = {
    "SKILL.md",
    "AGENTS.md",
    "automation.toml",
    "package.json",
    "pyproject.toml",
    "README.md",
}

_BASH_CATEGORY_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("git", "Git", ("git ",)),
    ("test", "Tests", ("pytest", "pnpm test", "npm test", "vitest", "jest", "go test", "cargo test")),
    ("lint", "Lint", ("eslint", "pnpm lint", "npm run lint", "flake8", "ruff", "mypy", "black ")),
    ("deploy", "Deploy", ("deploy", "release", "publish", "vercel", "netlify", "kubectl", "docker push")),
]

_FILE_PATH_KEYS = {
    "file_path",
    "path",
    "paths",
    "target_file",
    "source_file",
    "old_file",
    "new_file",
}

_CREATE_RESULT_MARKERS = (
    "created",
    "new file",
    "file did not exist",
    "wrote new",
)

# Treat recently modified session files without terminal metadata as in-flight.
_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60
_TERMINAL_SYSTEM_SUBTYPES = {
    "turn_duration",
    "compact_boundary",
    "microcompact_boundary",
    "informational",
}

_THINKING_LEVELS = {"low", "medium", "high"}

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}
_URL_PATTERN = re.compile(r"https?://([a-zA-Z0-9.-]+)(?::(\d+))?")
_SSH_TARGET_PATTERN = re.compile(r"\b(?:ssh|scp|rsync)\b[^\n]*?\b([A-Za-z0-9._-]+@[A-Za-z0-9.-]+)")
_DB_TOOL_PATTERN = re.compile(r"\b(psql|mysql|sqlite3|mongosh|mongo|redis-cli|pg_dump|pg_restore)\b")
_DOCKER_PATTERN = re.compile(r"\bdocker(?:\s+compose|[- ]compose|\s+\w+)")
_SERVICE_PATTERN = re.compile(r"\b(pm2|systemctl)\b")
_MAX_TOOL_RESULT_PREVIEW_BYTES = 1024 * 32
_RELAY_MIRROR_POLICY = "excluded_from_observed_tokens_until_attribution"


@lru_cache(maxsize=1)
def _load_forensics_schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parent / "schema" / "session_forensics.schema.json"
    try:
        raw = json.loads(schema_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_relay_mirror_usage(progress_data: Any) -> dict[str, int] | None:
    if not isinstance(progress_data, dict):
        return None
    progress_message = progress_data.get("message")
    if not isinstance(progress_message, dict):
        return None
    nested_message = progress_message.get("message")
    if not isinstance(nested_message, dict):
        return None
    usage = nested_message.get("usage")
    if not isinstance(usage, dict):
        return {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationInputTokens": 0,
            "cacheReadInputTokens": 0,
        }
    return {
        "inputTokens": _coerce_int(usage.get("input_tokens"), 0),
        "outputTokens": _coerce_int(usage.get("output_tokens"), 0),
        "cacheCreationInputTokens": _coerce_int(usage.get("cache_creation_input_tokens"), 0),
        "cacheReadInputTokens": _coerce_int(usage.get("cache_read_input_tokens"), 0),
    }


def _normalize_host(raw_host: str) -> str:
    return str(raw_host or "").strip().strip("[]").lower()


def _is_local_host(raw_host: str) -> bool:
    return _normalize_host(raw_host) in _LOCAL_HOSTS


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
            scope = "internal" if _is_local_host(host) or host == "docker" else "external"
            resources.append({
                "category": "database",
                "target": f"{db_system}:{host or 'localhost'}",
                "scope": scope,
                "dbSystem": db_system,
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
            resources.append({
                "category": "ssh",
                "target": ssh_match.group(1),
                "scope": "external",
            })

        if _DOCKER_PATTERN.search(segment):
            resources.append({
                "category": "docker",
                "target": "docker",
                "scope": "internal",
            })

        service_match = _SERVICE_PATTERN.search(segment)
        if service_match:
            resources.append({
                "category": "service",
                "target": service_match.group(1),
                "scope": "internal",
            })

    return resources


def _estimate_line_count(path: Path) -> int:
    try:
        size = path.stat().st_size
    except Exception:
        return 0
    if size > _MAX_TOOL_RESULT_PREVIEW_BYTES:
        return -1

    try:
        with path.open("rb") as handle:
            data = handle.read()
        if not data:
            return 0
        return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    except Exception:
        return -1


def _sha1_sample(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(_MAX_TOOL_RESULT_PREVIEW_BYTES)
        return hashlib.sha1(data).hexdigest()
    except Exception:
        return ""


def _parse_ts_epoch(value: str) -> float:
    raw = str(value or "").strip()
    if not raw:
        return float("inf")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")


def _message_is_tool_result_wrapper(entry: dict[str, Any]) -> bool:
    message = entry.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if not isinstance(content, list) or not content:
        return False
    saw_block = False
    for block in content:
        if not isinstance(block, dict):
            continue
        saw_block = True
        if str(block.get("type") or "").strip().lower() != "tool_result":
            return False
    return saw_block


def _is_conversational_entry(entry: dict[str, Any]) -> bool:
    entry_type = str(entry.get("type") or "").strip().lower()
    if entry_type in {"assistant", "user"}:
        if _message_is_tool_result_wrapper(entry):
            return False
        return True
    message = entry.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or "").strip().lower()
        if role in {"assistant", "user", "system"} and not _message_is_tool_result_wrapper(entry):
            return True
    return False


def _build_entry_graph(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, str]]:
    nodes_by_uuid: dict[str, dict[str, Any]] = {}
    children_by_parent: dict[str, list[str]] = {}
    parent_by_child: dict[str, str] = {}

    for index, entry in enumerate(entries):
        entry_uuid = str(entry.get("uuid") or "").strip()
        if not entry_uuid:
            continue
        parent_uuid = str(entry.get("parentUuid") or "").strip()
        node = {
            "uuid": entry_uuid,
            "parentUuid": parent_uuid,
            "timestamp": str(entry.get("timestamp") or ""),
            "index": index,
            "isConversational": _is_conversational_entry(entry),
        }
        nodes_by_uuid[entry_uuid] = node
        if parent_uuid:
            children_by_parent.setdefault(parent_uuid, []).append(entry_uuid)
            parent_by_child[entry_uuid] = parent_uuid

    for parent_uuid, children in children_by_parent.items():
        children.sort(
            key=lambda child_uuid: (
                _parse_ts_epoch(str(nodes_by_uuid.get(child_uuid, {}).get("timestamp") or "")),
                int(nodes_by_uuid.get(child_uuid, {}).get("index") or 0),
            )
        )
    return nodes_by_uuid, children_by_parent, parent_by_child


def _collect_subtree_uuids(root_uuid: str, children_by_parent: dict[str, list[str]]) -> set[str]:
    visited: set[str] = set()
    stack = [root_uuid]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for child_uuid in children_by_parent.get(current, []):
            if child_uuid not in visited:
                stack.append(child_uuid)
    return visited


def _make_fork_session_id(raw_session_id: str, fork_root_entry_uuid: str) -> str:
    signature = f"claude_code::{raw_session_id}::{fork_root_entry_uuid}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:20]
    return f"S-fork-{digest}"


def _make_relationship_id(
    parent_session_id: str,
    child_session_id: str,
    relationship_type: str,
    parent_entry_uuid: str,
    child_entry_uuid: str,
) -> str:
    signature = "::".join(
        [
            parent_session_id,
            child_session_id,
            relationship_type,
            parent_entry_uuid,
            child_entry_uuid,
        ]
    )
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:20]
    return f"REL-{digest}"


@lru_cache(maxsize=1)
def _load_global_claude_config() -> dict[str, Any]:
    config_path = Path.home() / ".claude.json"
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    payload["_path"] = str(config_path)
    return payload


def _detect_claude_root(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name == ".claude":
            return parent
    return None


def _extract_raw_session_id(path: Path, is_subagent: bool) -> str:
    if is_subagent:
        return path.parent.parent.name
    return path.stem


def _normalize_thinking_level(raw_level: str) -> str:
    cleaned = str(raw_level or "").strip().lower()
    return cleaned if cleaned in _THINKING_LEVELS else ""


def _thinking_level_from_tokens(max_tokens: int, schema: dict[str, Any]) -> str:
    thresholds = schema.get("thinking", {}).get("max_token_thresholds", {})
    low_max = _coerce_int(thresholds.get("low_max"), 8000)
    medium_max = _coerce_int(thresholds.get("medium_max"), 24000)
    if max_tokens <= 0:
        return ""
    if max_tokens <= low_max:
        return "low"
    if max_tokens <= medium_max:
        return "medium"
    return "high"


def _parse_task_notification(raw_text: str) -> dict[str, str]:
    details: dict[str, str] = {}
    if not raw_text:
        return details

    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            field_map = {
                "task_id": "task-id",
                "taskId": "task-id",
                "status": "status",
                "summary": "summary",
                "description": "description",
                "tool_use_id": "tool-use-id",
                "toolUseId": "tool-use-id",
                "task_type": "task-type",
                "taskType": "task-type",
                "output_file": "output-file",
                "outputFile": "output-file",
                "shell_id": "shell-id",
                "shellId": "shell-id",
            }
            for source_key, target_key in field_map.items():
                value = parsed.get(source_key)
                if isinstance(value, str) and value.strip():
                    details[target_key] = value.strip()

    for key in (
        "task-id",
        "tool-use-id",
        "output-file",
        "shell-id",
        "status",
        "summary",
        "description",
        "result",
        "task-type",
    ):
        match = re.search(rf"<{key}>\s*([\s\S]*?)\s*</{key}>", raw_text, re.IGNORECASE)
        if match and match.group(1).strip():
            details[key] = match.group(1).strip()
    return details


def _load_json_array(path: Path) -> list[Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return raw if isinstance(raw, list) else []


def _load_json_dict(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _parse_todo_filename(file_path: Path, session_id: str) -> tuple[str, str]:
    name = file_path.stem
    prefix = f"{session_id}-agent-"
    if name.startswith(prefix):
        return session_id, name[len(prefix):]
    parts = name.split("-agent-", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return session_id, ""


def _collect_todo_sidecar(
    claude_root: Path | None,
    raw_session_id: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not claude_root or not raw_session_id:
        return {"directory": "", "exists": False, "files": [], "fileCount": 0, "totalItems": 0, "counts": {}, "items": []}

    todo_cfg = schema.get("sidecars", {}).get("todos", {})
    todo_dir = claude_root / str(todo_cfg.get("dir") or "todos")
    todo_glob = str(todo_cfg.get("glob") or "{session_id}-agent-*.json").replace("{session_id}", raw_session_id)
    files = sorted(todo_dir.glob(todo_glob))
    items: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    file_details: list[dict[str, Any]] = []
    for file_path in files:
        parsed_session_id, parsed_agent_id = _parse_todo_filename(file_path, raw_session_id)
        file_items = _load_json_array(file_path)
        file_details.append({
            "path": str(file_path),
            "sessionId": parsed_session_id,
            "agentId": parsed_agent_id,
            "itemCount": len(file_items),
        })
        for index, item in enumerate(file_items):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower() or "unknown"
            counts[status] += 1
            items.append({
                "content": str(item.get("content") or "").strip(),
                "status": status,
                "activeForm": str(item.get("activeForm") or "").strip(),
                "index": index,
                "sessionId": parsed_session_id,
                "agentId": parsed_agent_id,
                "sourceFile": str(file_path),
            })
    return {
        "directory": str(todo_dir),
        "exists": todo_dir.exists(),
        "files": [str(path) for path in files],
        "fileCount": len(files),
        "fileDetails": file_details[:100],
        "totalItems": len(items),
        "counts": dict(counts),
        "items": items[:100],
    }


def _collect_task_sidecar(
    claude_root: Path | None,
    raw_session_id: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not claude_root or not raw_session_id:
        return {
            "directory": "",
            "exists": False,
            "highWatermark": "",
            "highWatermarkValue": 0,
            "lockPresent": False,
            "counts": {},
            "taskFileCount": 0,
            "tasks": [],
        }

    task_cfg = schema.get("sidecars", {}).get("tasks", {})
    task_dir = claude_root / str(task_cfg.get("dir") or "tasks/{session_id}").replace("{session_id}", raw_session_id)
    if not task_dir.exists():
        return {
            "directory": str(task_dir),
            "exists": False,
            "highWatermark": "",
            "highWatermarkValue": 0,
            "lockPresent": False,
            "counts": {},
            "taskFileCount": 0,
            "tasks": [],
        }

    task_glob = str(task_cfg.get("task_glob") or "*.json")
    high_watermark_file = task_dir / str(task_cfg.get("high_watermark_file") or ".highwatermark")
    lock_file = task_dir / str(task_cfg.get("lock_file") or ".lock")
    high_watermark = ""
    try:
        high_watermark = high_watermark_file.read_text(encoding="utf-8").strip()
    except Exception:
        high_watermark = ""
    high_watermark_value = _coerce_int(high_watermark, 0)

    task_files = sorted(task_dir.glob(task_glob), key=lambda p: p.name)
    tasks: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for task_file in task_files:
        payload = _load_json_dict(task_file)
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("status") or "").strip().lower() or "unknown"
        counts[status] += 1
        tasks.append({
            "id": str(payload.get("id") or task_file.stem),
            "subject": str(payload.get("subject") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "activeForm": str(payload.get("activeForm") or "").strip(),
            "status": status,
            "blocks": payload.get("blocks") if isinstance(payload.get("blocks"), list) else [],
            "blockedBy": payload.get("blockedBy") if isinstance(payload.get("blockedBy"), list) else [],
            "sourceFile": str(task_file),
        })

    return {
        "directory": str(task_dir),
        "exists": True,
        "highWatermark": high_watermark,
        "highWatermarkValue": high_watermark_value,
        "lockPresent": lock_file.exists(),
        "counts": dict(counts),
        "taskFileCount": len(task_files),
        "tasks": tasks[:200],
    }


def _collect_team_sidecar(
    claude_root: Path | None,
    raw_session_id: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not claude_root or not raw_session_id:
        return {"directory": "", "exists": False, "teamMembers": [], "inboxes": [], "totalMessages": 0, "unreadMessages": 0}

    team_cfg = schema.get("sidecars", {}).get("teams", {})
    inbox_dir = claude_root / str(team_cfg.get("dir") or "teams/{session_id}/inboxes").replace("{session_id}", raw_session_id)
    if not inbox_dir.exists():
        return {"directory": str(inbox_dir), "exists": False, "teamMembers": [], "inboxes": [], "totalMessages": 0, "unreadMessages": 0}

    inbox_glob = str(team_cfg.get("glob") or "*.json")
    inbox_files = sorted(inbox_dir.glob(inbox_glob))
    inboxes: list[dict[str, Any]] = []
    total_messages = 0
    unread_messages = 0
    for inbox_file in inbox_files:
        rows = _load_json_array(inbox_file)
        parsed_messages: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            total_messages += 1
            read_flag = bool(row.get("read", True))
            if not read_flag:
                unread_messages += 1
            text = str(row.get("text") or "")
            payload_type = ""
            payload: dict[str, Any] = {}
            if text.strip().startswith("{") and text.strip().endswith("}"):
                try:
                    candidate = json.loads(text)
                except Exception:
                    candidate = {}
                if isinstance(candidate, dict):
                    payload = candidate
                    payload_type = str(candidate.get("type") or "").strip().lower()
            parsed_messages.append({
                "from": str(row.get("from") or "").strip(),
                "timestamp": str(row.get("timestamp") or "").strip(),
                "read": read_flag,
                "payloadType": payload_type,
                "taskId": str(payload.get("taskId") or payload.get("task_id") or "").strip(),
                "subject": str(payload.get("subject") or "").strip(),
                "description": str(payload.get("description") or "").strip(),
                "assignedBy": str(payload.get("assignedBy") or payload.get("assigned_by") or "").strip(),
                "rawText": text[:4000],
                "sourceFile": str(inbox_file),
            })

        inboxes.append({
            "name": inbox_file.stem,
            "file": str(inbox_file),
            "messageCount": len(parsed_messages),
            "messages": parsed_messages[:100],
        })

    return {
        "directory": str(inbox_dir),
        "exists": True,
        "teamMembers": [inbox.get("name", "") for inbox in inboxes if inbox.get("name")],
        "inboxes": inboxes,
        "totalMessages": total_messages,
        "unreadMessages": unread_messages,
    }


def _collect_session_env_sidecar(
    claude_root: Path | None,
    raw_session_id: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not claude_root or not raw_session_id:
        return {"directory": "", "exists": False, "fileCount": 0, "files": []}

    env_cfg = schema.get("sidecars", {}).get("session_env", {})
    env_dir = claude_root / str(env_cfg.get("dir") or "session-env/{session_id}").replace("{session_id}", raw_session_id)
    if not env_dir.exists():
        return {"directory": str(env_dir), "exists": False, "fileCount": 0, "files": []}

    file_glob = str(env_cfg.get("glob") or "*")
    files = [p for p in sorted(env_dir.glob(file_glob)) if p.is_file()]
    return {
        "directory": str(env_dir),
        "exists": True,
        "fileCount": len(files),
        "files": [str(path) for path in files[:100]],
    }


def _resolve_session_sidecar_root(path: Path, raw_session_id: str, is_subagent: bool) -> Path:
    if is_subagent:
        return path.parent.parent
    return path.parent / raw_session_id


def _collect_tool_results_sidecar(
    path: Path,
    raw_session_id: str,
    is_subagent: bool,
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not raw_session_id:
        return {
            "directory": "",
            "exists": False,
            "fileCount": 0,
            "totalBytes": 0,
            "totalLines": 0,
            "maxFileBytes": 0,
            "avgFileBytes": 0.0,
            "largeFileCount": 0,
            "files": [],
            "largestFiles": [],
            "checksumSample": [],
        }

    root = _resolve_session_sidecar_root(path, raw_session_id, is_subagent)
    cfg = schema.get("sidecars", {}).get("tool_results", {})
    rel_dir = str(cfg.get("dir") or "tool-results").strip() or "tool-results"
    results_dir = root / rel_dir
    if not results_dir.exists():
        return {
            "directory": str(results_dir),
            "exists": False,
            "fileCount": 0,
            "totalBytes": 0,
            "totalLines": 0,
            "maxFileBytes": 0,
            "avgFileBytes": 0.0,
            "largeFileCount": 0,
            "files": [],
            "largestFiles": [],
            "checksumSample": [],
        }

    glob_pattern = str(cfg.get("glob") or "*.txt")
    max_files = _coerce_int(cfg.get("max_files"), 500)
    checksum_limit = _coerce_int(cfg.get("checksum_sample_limit"), 8)
    result_files = [item for item in sorted(results_dir.glob(glob_pattern)) if item.is_file()][:max(1, max_files)]

    total_bytes = 0
    total_lines = 0
    max_file_bytes = 0
    large_file_count = 0
    file_rows: list[dict[str, Any]] = []
    for file_path in result_files:
        try:
            size = int(file_path.stat().st_size)
        except Exception:
            size = 0
        total_bytes += size
        max_file_bytes = max(max_file_bytes, size)
        if size > _MAX_TOOL_RESULT_PREVIEW_BYTES:
            large_file_count += 1
        line_count = _estimate_line_count(file_path)
        if line_count >= 0:
            total_lines += line_count
        file_rows.append({
            "path": str(file_path),
            "name": file_path.name,
            "bytes": size,
            "lines": line_count,
        })

    checksum_rows: list[dict[str, Any]] = []
    for item in sorted(file_rows, key=lambda row: int(row.get("bytes") or 0), reverse=True)[: max(1, checksum_limit)]:
        sample_path = Path(str(item.get("path") or ""))
        checksum = _sha1_sample(sample_path)
        if checksum:
            checksum_rows.append({
                "name": str(item.get("name") or ""),
                "bytes": int(item.get("bytes") or 0),
                "sha1": checksum,
            })

    file_count = len(file_rows)
    avg_file_bytes = round(total_bytes / file_count, 2) if file_count else 0.0
    largest_files = sorted(file_rows, key=lambda row: int(row.get("bytes") or 0), reverse=True)[:20]

    return {
        "directory": str(results_dir),
        "exists": True,
        "fileCount": file_count,
        "totalBytes": total_bytes,
        "totalLines": total_lines,
        "maxFileBytes": max_file_bytes,
        "avgFileBytes": avg_file_bytes,
        "largeFileCount": large_file_count,
        "files": [str(item.get("path") or "") for item in file_rows[:120]],
        "largestFiles": largest_files,
        "checksumSample": checksum_rows,
    }


def _platform_telemetry_summary(working_directories: list[str]) -> dict[str, Any]:
    payload = _load_global_claude_config()
    if not payload:
        return {}

    projects = payload.get("projects")
    projects_dict = projects if isinstance(projects, dict) else {}
    project_match: dict[str, Any] = {}
    for cwd in working_directories:
        candidate = projects_dict.get(cwd)
        if isinstance(candidate, dict):
            project_match = candidate
            break

    mcp_servers = project_match.get("mcpServers") if isinstance(project_match.get("mcpServers"), dict) else {}
    disabled_servers = project_match.get("disabledMcpServers") if isinstance(project_match.get("disabledMcpServers"), list) else []
    enabled_mcpjson = project_match.get("enabledMcpjsonServers") if isinstance(project_match.get("enabledMcpjsonServers"), list) else []
    growth_features = payload.get("cachedGrowthBookFeatures") if isinstance(payload.get("cachedGrowthBookFeatures"), dict) else {}
    statsig_gates = payload.get("cachedStatsigGates") if isinstance(payload.get("cachedStatsigGates"), dict) else {}
    tips_history = payload.get("tipsHistory") if isinstance(payload.get("tipsHistory"), dict) else {}
    tool_usage = payload.get("toolUsage") if isinstance(payload.get("toolUsage"), dict) else {}
    skill_usage = payload.get("skillUsage") if isinstance(payload.get("skillUsage"), dict) else {}

    return {
        "source": str(payload.get("_path") or ""),
        "numStartups": _coerce_int(payload.get("numStartups")),
        "promptQueueUseCount": _coerce_int(payload.get("promptQueueUseCount")),
        "firstStartTime": str(payload.get("firstStartTime") or ""),
        "lastReleaseNotesSeen": str(payload.get("lastReleaseNotesSeen") or ""),
        "projectCount": len(projects_dict),
        "tipsCount": len(tips_history),
        "growthFeatureCount": len(growth_features),
        "statsigGateCount": len(statsig_gates),
        "toolUsageCount": len(tool_usage),
        "skillUsageCount": len(skill_usage),
        "project": {
            "path": str(next((cwd for cwd in working_directories if projects_dict.get(cwd)), "")),
            "mcpServerCount": len(mcp_servers),
            "mcpServerNames": sorted(str(name) for name in mcp_servers.keys())[:40],
            "disabledMcpServerCount": len(disabled_servers),
            "enabledMcpjsonServerCount": len(enabled_mcpjson),
            "lastTotalWebSearchRequests": _coerce_int(project_match.get("lastTotalWebSearchRequests")),
            "projectOnboardingSeenCount": _coerce_int(project_match.get("projectOnboardingSeenCount")),
            "hasCompletedProjectOnboarding": bool(project_match.get("hasCompletedProjectOnboarding", False)),
        },
    }


def _normalize_session_id(raw_id: str) -> str:
    """Normalize session IDs to a stable, URL-safe display format."""
    cleaned = raw_id.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("S-"):
        return cleaned

    if re.match(r"^[A-Za-z0-9._:-]+$", cleaned):
        return f"S-{cleaned}"

    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:20]
    return f"S-{digest}"


def _make_id(path: Path) -> str:
    """Derive a collision-safe session ID from the source filename."""
    return _normalize_session_id(path.stem) or f"S-{hashlib.sha1(path.stem.encode('utf-8')).hexdigest()[:20]}"


def _estimate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Rough cost estimate based on model pricing."""
    rates = {
        "claude-3-5-sonnet": (3.0, 15.0),
        "claude-3-7-sonnet": (3.0, 15.0),
        "claude-sonnet": (3.0, 15.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-opus": (15.0, 75.0),
        "claude-3-haiku": (0.25, 1.25),
        "claude-haiku": (0.25, 1.25),
    }
    model_lower = model.lower()
    in_rate, out_rate = 3.0, 15.0
    for key, (ir, outr) in rates.items():
        if key in model_lower:
            in_rate, out_rate = ir, outr
            break
    return (tokens_in / 1_000_000 * in_rate) + (tokens_out / 1_000_000 * out_rate)


def _parse_iso_ts(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _normalize_path(raw: str) -> str:
    path = raw.strip().strip('"\'`<>[](),;')
    if not path:
        return ""
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("../"):
        return ""
    if "node_modules/" in path or "/.git/" in path or "/coverage/" in path:
        return ""
    return path


def _looks_like_file_path(value: str) -> bool:
    if "/" not in value:
        return False
    basename = value.rsplit("/", 1)[-1]
    if basename in _MANIFEST_BASENAMES:
        return True
    if "." in basename:
        return True
    return value.startswith("/Users/")


def _extract_paths_from_text(text: str) -> list[str]:
    matches = []
    for raw in _PATH_PATTERN.findall(text):
        norm = _normalize_path(raw)
        if norm and _looks_like_file_path(norm):
            matches.append(norm)
    return matches


def _extract_paths_from_payload(payload: Any) -> list[str]:
    paths: list[str] = []

    if isinstance(payload, str):
        norm = _normalize_path(payload)
        if norm and _looks_like_file_path(norm):
            paths.append(norm)
        return paths

    if isinstance(payload, list):
        for item in payload:
            paths.extend(_extract_paths_from_payload(item))
        return paths

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FILE_PATH_KEYS:
                paths.extend(_extract_paths_from_payload(value))
            elif isinstance(value, (dict, list)):
                paths.extend(_extract_paths_from_payload(value))
            elif isinstance(value, str) and key.endswith("path"):
                paths.extend(_extract_paths_from_payload(value))
        return paths

    return paths


def _canonical_feature_slug(raw_slug: str) -> str:
    slug = raw_slug.strip().lower()
    if not slug:
        return ""
    return _VERSION_SUFFIX_PATTERN.sub("", slug)


def _feature_slug_from_path(raw_path: str) -> str:
    value = _normalize_path(raw_path)
    if not value:
        return ""
    return Path(value).stem.strip().lower()


def _is_noisy_feature_ref(path_value: str) -> bool:
    if not path_value:
        return True
    return bool(_PLACEHOLDER_PATH_PATTERN.search(path_value))


def _extract_phase_token(args_text: str) -> tuple[str, list[str]]:
    normalized = " ".join(args_text.strip().split())
    if not normalized:
        return "", []

    if normalized.lower().startswith("all"):
        return "all", ["all"]

    range_match = re.match(r"^(\d+)\s*-\s*(\d+)\b", normalized)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if start <= end:
            values = [str(v) for v in range(start, end + 1)]
        else:
            values = [str(start), str(end)]
        return f"{start}-{end}", values

    amp_match = re.match(r"^(\d+(?:\s*&\s*\d+)+)\b", normalized)
    if amp_match:
        values = [part.strip() for part in amp_match.group(1).split("&") if part.strip()]
        return " & ".join(values), values

    single_match = re.match(r"^(\d+)\b", normalized)
    if single_match:
        token = single_match.group(1)
        return token, [token]

    return "", []


def _pick_primary_feature_path(paths: list[str]) -> str:
    if not paths:
        return ""
    impl_candidates = [p for p in paths if "implementation_plans/" in p and p.lower().endswith(".md")]
    if impl_candidates:
        return impl_candidates[0]
    md_candidates = [p for p in paths if p.lower().endswith(".md")]
    if md_candidates:
        return md_candidates[0]
    return paths[0]


def _parse_command_context(command_name: str, args_text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    command = command_name.strip()
    args = args_text.strip()
    if not command:
        return parsed

    if args:
        req_match = _REQ_ID_PATTERN.search(args)
        if req_match:
            parsed["requestId"] = req_match.group(0).upper()

        paths = [p for p in _extract_paths_from_text(args) if p and not _is_noisy_feature_ref(p)]
        if paths:
            parsed["paths"] = paths[:8]
            primary_path = _pick_primary_feature_path(paths)
            if primary_path:
                parsed["featurePath"] = primary_path
                slug = _feature_slug_from_path(primary_path)
                if slug:
                    parsed["featureSlug"] = slug
                    parsed["featureSlugCanonical"] = _canonical_feature_slug(slug)

    lowered_command = command.lower()
    if "dev:execute-phase" in lowered_command:
        phase_token, phase_values = _extract_phase_token(args)
        if phase_token:
            parsed["phaseToken"] = phase_token
        if phase_values:
            parsed["phases"] = phase_values
    if lowered_command in {"/model", "model"} and args:
        for raw_token in re.split(r"[\s,;]+", args):
            token = raw_token.strip("`'\"").strip()
            if not token:
                continue
            if token.lower() in _MODEL_COMMAND_STOPWORDS:
                continue
            if token.startswith("-"):
                continue
            if _MODEL_TOKEN_PATTERN.match(token):
                parsed["model"] = token
                break

    return parsed


def _tool_result_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
                elif isinstance(block.get("content"), str):
                    chunks.append(block["content"])
        return "\n".join(chunks)
    try:
        return json.dumps(content)
    except Exception:
        return str(content)


def _hash_artifact_id(session_id: str, kind: str, title: str, source_log_id: str | None) -> str:
    raw = f"{session_id}|{kind}|{title}|{source_log_id or ''}"
    return f"{session_id}-art-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _classify_bash_command(command: str) -> tuple[str, str]:
    lowered = command.lower()
    for category, label, terms in _BASH_CATEGORY_RULES:
        if any(term in lowered for term in terms):
            return category, label
    return "bash", "Shell"


def _extract_commit_hashes(text: str) -> list[str]:
    commits: set[str] = set()
    if not text:
        return []

    for match in _COMMIT_BRACKET_PATTERN.finditer(text):
        commits.add(match.group(1))

    for line in text.splitlines():
        ll = line.lower()
        if not any(token in ll for token in ("git ", "commit ", "cherry-pick", "revert", "rebase", "checkout", "merge", "reset", "amend", "log")):
            continue
        for match in _COMMIT_PATTERN.finditer(line):
            candidate = match.group(0)
            if any(ch in candidate.lower() for ch in "abcdef"):
                commits.add(candidate)

    return sorted(commits)


def _coerce_text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=True).strip()
        except Exception:
            return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def _extract_task_id(*values: Any) -> str:
    for value in values:
        text = _coerce_text_blob(value)
        if not text:
            continue
        match = _TASK_ID_PATTERN.search(text)
        if match:
            return match.group(1).strip()
    return ""


def _is_subagent_tool_name(name: str) -> bool:
    return str(name or "").strip().lower() in _SUBAGENT_TOOL_NAMES


def _extract_hook_path(value: Any) -> str:
    text = _coerce_text_blob(value).replace("\\", "/")
    if not text:
        return ""
    match = _HOOK_PATH_FRAGMENT_PATTERN.search(text)
    if not match:
        return ""

    fragment_start = match.start()
    start = fragment_start
    while start > 0 and text[start - 1] not in {" ", "\t", "\n", "'", '"', "`", "|", "&", ";", "(", ")", "<", ">"}:
        start -= 1

    end = match.end()
    while end < len(text) and text[end] not in {" ", "\t", "\n", "'", '"', "`", "|", "&", ";", "(", ")", "<", ">"}:
        end += 1
    return text[start:end].strip().strip("'\"`")


def _parse_hook_progress(data: dict[str, Any]) -> dict[str, str]:
    command = _coerce_text_blob(data.get("command") or data.get("cmd") or data.get("script"))
    hook_name = str(data.get("hookName") or data.get("name") or "").strip()
    hook_event = str(data.get("hookEvent") or data.get("event") or "").strip()
    hook_path = _extract_hook_path(data.get("hookPath") or data.get("path"))
    if not hook_path:
        hook_path = _extract_hook_path(command)
    if not hook_path:
        hook_path = _extract_hook_path(hook_name)
    if not hook_name and hook_path:
        hook_name = Path(hook_path).name
    summary = command or hook_path or hook_name or hook_event or "Hook progress"
    return {
        "summary": summary,
        "command": command,
        "hookName": hook_name,
        "hookPath": hook_path,
        "hookEvent": hook_event,
    }


def _classify_bash_result(output_text: str, is_error: bool) -> str:
    if is_error:
        return "error"
    lowered = output_text.lower()
    if any(marker in lowered for marker in ("error", "failed", "traceback", "exception", "fatal:")):
        return "error"
    if any(marker in lowered for marker in ("passed", "success", "completed", "ok")):
        return "success"
    return "unknown"


def _extract_skill_payload(text: str) -> dict[str, str]:
    if not text:
        return {}

    payload: dict[str, str] = {}
    if not _SKILL_FORMAT_PATTERN.search(text) and "base directory for this skill:" not in text.lower():
        return payload

    command_names = [m.group(1).strip() for m in _COMMAND_NAME_PATTERN.finditer(text) if m.group(1).strip()]
    base_dir_match = _SKILL_BASE_DIR_PATTERN.search(text)
    if base_dir_match:
        base_dir = _normalize_path(base_dir_match.group(1).strip())
        if base_dir:
            payload["baseDirectory"] = base_dir
            payload["skill"] = Path(base_dir).name

        # Capture a concise skill synopsis from the first non-empty line after base-dir.
        tail = text[base_dir_match.end():].strip()
        summary = ""
        for line in tail.splitlines():
            stripped = line.strip().strip("#").strip()
            if not stripped:
                continue
            if stripped.startswith("-") or stripped.startswith("|") or stripped.startswith("```"):
                continue
            summary = stripped
            break
        if summary:
            payload["summary"] = summary[:500]

    if command_names:
        payload["commandName"] = command_names[0]
        if "skill" not in payload:
            candidate = command_names[0].strip()
            if candidate and not candidate.startswith("/"):
                payload["skill"] = candidate

    return payload


def _parse_manage_plan_status_command(command: str) -> dict[str, str]:
    if "manage-plan-status.py" not in command:
        return {}

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    details: dict[str, str] = {"script": "manage-plan-status.py"}
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        next_token = tokens[idx + 1] if idx + 1 < len(tokens) else ""

        if token in {"--file", "-f"} and next_token:
            details["file"] = _normalize_path(next_token)
            idx += 2
            continue
        if token == "--status" and next_token:
            details["status"] = next_token.strip().lower()
            idx += 2
            continue
        if token == "--field" and next_token:
            details["field"] = next_token.strip()
            idx += 2
            continue
        if token == "--value" and next_token:
            details["value"] = next_token.strip()
            idx += 2
            continue
        if token == "--read" and next_token:
            details["readFile"] = _normalize_path(next_token)
            idx += 2
            continue
        if token == "--query":
            details["query"] = "true"
        idx += 1

    if details.get("status") or details.get("field"):
        details["operation"] = "update"
    elif details.get("readFile"):
        details["operation"] = "read"
    elif details.get("query") == "true":
        details["operation"] = "query"
    else:
        details["operation"] = "run"

    return details


def _parse_batch_execution_message(text: str) -> dict[str, Any]:
    if "batch" not in text.lower():
        return {}

    header_match = _BATCH_HEADER_PATTERN.search(text)
    if not header_match:
        return {}

    batch_id = header_match.group(1).strip()
    if not batch_id:
        return {}

    tasks: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        match = _BATCH_BULLET_PATTERN.match(line)
        if not match:
            continue

        task_id = match.group(1).strip()
        if not task_id:
            continue
        body = match.group(2).strip()
        task_agent = ""
        agent_match = re.search(r"\(([^)]+)\)\s*$", body)
        if agent_match:
            task_agent = agent_match.group(1).strip().strip("`").strip()
            body = body[:agent_match.start()].strip()
        tasks.append({
            "taskId": task_id,
            "name": body[:240],
            "agent": task_agent[:120],
        })

    if not tasks:
        return {}

    return {
        "batchId": batch_id,
        "taskCount": len(tasks),
        "tasks": tasks[:20],
    }


def _derive_session_status(entries: list[dict[str, Any]], path: Path) -> str:
    """Infer session status from terminal metadata + file recency."""
    if not entries:
        return "completed"

    last = entries[-1]
    last_type = str(last.get("type") or "").strip().lower()
    last_subtype = str(last.get("subtype") or "").strip().lower()

    # Claude emits terminal system entries (for completed turns/sessions) with
    # duration/subtype metadata. Treat these as definitive completion signals.
    if last_type == "system":
        if "durationMs" in last:
            return "completed"
        if last_subtype in _TERMINAL_SYSTEM_SUBTYPES:
            return "completed"

    try:
        age_seconds = max(0.0, time.time() - float(path.stat().st_mtime))
    except Exception:
        age_seconds = float("inf")

    if age_seconds <= _ACTIVE_SESSION_WINDOW_SECONDS:
        return "active"
    return "completed"


def _detect_platform_type(entry: dict[str, Any]) -> str:
    for key in ("platformType", "platform", "clientName", "client", "agentPlatform"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Claude Code"


def _classify_file_type(path: str) -> str:
    lowered = path.lower()
    basename = lowered.rsplit("/", 1)[-1]

    if (
        lowered.endswith(".md")
        or lowered.endswith(".txt")
        or lowered.endswith(".rst")
        or basename in {"readme", "readme.md"}
    ):
        if any(token in lowered for token in ("docs/project_plans", "implementation_plan", "prd", "spec", "roadmap", "plan")):
            return "Plan"
        return "Document"

    if any(token in lowered for token in ("/components/", "/frontend/", "/src/")) and lowered.endswith((".tsx", ".jsx", ".css", ".scss", ".html")):
        return "Frontend code"

    if any(token in lowered for token in ("/backend/", "/server/", "/api/")) and lowered.endswith((".py", ".go", ".rb", ".java", ".cs", ".rs", ".php")):
        return "Backend code"

    if lowered.endswith((".tsx", ".jsx", ".css", ".scss", ".html")):
        return "Frontend code"

    if lowered.endswith((".py", ".go", ".rb", ".java", ".cs", ".rs", ".php")):
        return "Backend code"

    if lowered.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".test.py", ".spec.py")) or "/tests/" in lowered:
        return "Test code"

    if lowered.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".lock")) or basename in {"dockerfile", ".env", ".env.example"}:
        return "Config"

    if lowered.endswith((".csv", ".jsonl", ".parquet", ".sqlite", ".db")):
        return "Data"

    return "Other"


def _result_indicates_create(output_text: str) -> bool:
    if not output_text:
        return False
    lowered = output_text.lower()
    return any(marker in lowered for marker in _CREATE_RESULT_MARKERS)


def parse_session_file(path: Path) -> AgentSession | None:
    """Parse a single JSONL session log into an AgentSession."""
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        return None

    if not lines:
        return None

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        return None

    session_id = _make_id(path)
    session_status = _derive_session_status(entries, path)
    fs_dates = file_metadata_dates(path)
    forensics_schema = _load_forensics_schema()
    is_subagent = path.parent.name == "subagents"
    session_type = "subagent" if is_subagent else "session"
    raw_session_id = _extract_raw_session_id(path, is_subagent)
    claude_root = _detect_claude_root(path)

    parent_session_id = ""
    if is_subagent:
        parent_session_id = _normalize_session_id(path.parent.parent.name)

    root_session_id = parent_session_id or session_id
    agent_id: str | None = None
    if is_subagent and path.stem.startswith("agent-"):
        agent_id = path.stem.split("agent-", 1)[-1]

    task_id = ""
    model = ""
    platform_type = "Claude Code"
    platform_version = ""
    platform_versions: list[str] = []
    platform_versions_seen: set[str] = set()
    platform_version_transitions: list[SessionPlatformTransition] = []
    git_branch = ""
    git_author = ""
    git_commit = ""
    git_commits: set[str] = set()
    tokens_in = 0
    tokens_out = 0
    first_ts = ""
    last_ts = ""
    usage_message_totals: dict[str, int] = {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
    }
    relay_mirror_totals: dict[str, int] = {
        "excludedCount": 0,
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
    }
    usage_cache_creation_totals: dict[str, int] = {
        "ephemeral_5m_input_tokens": 0,
        "ephemeral_1h_input_tokens": 0,
    }
    usage_service_tier_counts: Counter[str] = Counter()
    usage_inference_geo_counts: Counter[str] = Counter()
    usage_speed_counts: Counter[str] = Counter()
    usage_server_tool_use_totals: Counter[str] = Counter()
    usage_iteration_count = 0
    tool_result_reported_totals: dict[str, int] = {
        "reportedCount": 0,
        "totalTokens": 0,
        "totalDurationMs": 0,
        "totalToolUseCount": 0,
    }
    tool_result_usage_totals: dict[str, int] = {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
    }
    tool_result_usage_cache_creation_totals: dict[str, int] = {
        "ephemeral_5m_input_tokens": 0,
        "ephemeral_1h_input_tokens": 0,
    }
    tool_result_usage_service_tier_counts: Counter[str] = Counter()
    tool_result_usage_inference_geo_counts: Counter[str] = Counter()
    tool_result_usage_speed_counts: Counter[str] = Counter()
    tool_result_usage_server_tool_use_totals: Counter[str] = Counter()
    tool_result_usage_iteration_count = 0
    assistant_message_count = 0
    assistant_messages_with_usage = 0

    logs: list[SessionLog] = []
    tool_counter: Counter[str] = Counter()
    tool_success: Counter[str] = Counter()
    tool_total: Counter[str] = Counter()
    tool_duration_ms: Counter[str] = Counter()
    impacts: list[ImpactPoint] = []

    file_changes: list[SessionFileUpdate] = []
    artifacts: dict[str, SessionArtifact] = {}

    thinking_level = ""
    thinking_meta: dict[str, Any] = {
        "source": "",
        "maxThinkingTokens": 0,
        "disabled": False,
        "explicitLevel": "",
    }
    embedded_todos: list[dict[str, str]] = []

    session_context: dict[str, Any] = {
        "workingDirectories": set(),
        "slugs": set(),
        "userTypes": set(),
        "permissionModes": set(),
        "versions": set(),
        "requestIds": set(),
        "sessionIds": set(),
        "entryUuids": set(),
        "parentUuids": set(),
        "messageIds": set(),
        "toolUseIDs": set(),
        "parentToolUseIDs": set(),
        "agentIds": set(),
        "sourceToolAssistantUUIDs": set(),
        "sourceToolUseIDs": set(),
        "entryTypeCounts": Counter(),
        "entryKeyCounts": Counter(),
        "messageRoleCounts": Counter(),
        "messageStopReasonCounts": Counter(),
        "messageStopSequenceCounts": Counter(),
        "messageTypeCounts": Counter(),
        "contentBlockTypeCounts": Counter(),
        "contentBlockKeyCounts": Counter(),
        "toolCallerTypeCounts": Counter(),
        "progressTypeCounts": Counter(),
        "progressDataKeyCounts": Counter(),
        "isSidechainCount": 0,
        "isSnapshotUpdateCount": 0,
        "snapshotCount": 0,
        "apiErrors": [],
        "queueOperations": [],
        "skillLoads": [],
        "planStatusUpdates": [],
        "batchExecutions": [],
        "hookInvocations": [],
    }
    resource_observations: list[dict[str, Any]] = []
    resource_observation_seen: set[tuple[str, str, str, str]] = set()

    tool_logs_by_id: dict[str, int] = {}
    tool_started_at_by_id: dict[str, str] = {}
    subagent_link_by_parent_tool: dict[str, str] = {}
    skill_invocations_by_tool_use_id: dict[str, dict[str, Any]] = {}
    emitted_subagent_starts: set[tuple[str, str]] = set()
    current_entry_lineage_metadata: dict[str, Any] = {}
    entry_log_indices_by_uuid: dict[str, list[int]] = {}
    derived_sessions: list[dict[str, Any]] = []
    session_relationships: list[dict[str, Any]] = []
    fork_descriptors_by_root: dict[str, dict[str, Any]] = {}
    fork_partitions_by_session_id: dict[str, dict[str, Any]] = {}

    log_idx = 0

    def append_log(**kwargs: Any) -> int:
        nonlocal log_idx
        metadata = kwargs.get("metadata")
        if metadata is None:
            kwargs["metadata"] = {}
        elif not isinstance(metadata, dict):
            kwargs["metadata"] = {}
        metadata = kwargs.get("metadata")
        if isinstance(metadata, dict) and current_entry_lineage_metadata:
            for key, value in current_entry_lineage_metadata.items():
                if key not in metadata and value is not None and str(value).strip():
                    metadata[key] = value
        log = SessionLog(id=f"log-{log_idx}", **kwargs)
        logs.append(log)
        entry_uuid = str(log.metadata.get("entryUuid") or "").strip() if isinstance(log.metadata, dict) else ""
        if entry_uuid:
            entry_log_indices_by_uuid.setdefault(entry_uuid, []).append(len(logs) - 1)
        log_idx += 1
        return len(logs) - 1

    def register_command_resources(
        command_text: str,
        source_log_id: str,
        source: str,
        timestamp: str,
    ) -> list[dict[str, str]]:
        stripped = str(command_text or "").strip()
        if not stripped:
            return []
        extracted = _extract_resources_from_command(stripped)
        for item in extracted:
            category = str(item.get("category") or "").strip()
            target = str(item.get("target") or "").strip()
            scope = str(item.get("scope") or "").strip()
            if not category or not target:
                continue
            unique_key = (category, target, scope, source_log_id)
            if unique_key in resource_observation_seen:
                continue
            resource_observation_seen.add(unique_key)
            resource_observations.append({
                "timestamp": timestamp,
                "source": source,
                "sourceLogId": source_log_id,
                "category": category,
                "target": target,
                "scope": scope or "unknown",
                "dbSystem": str(item.get("dbSystem") or ""),
            })
        return extracted

    def track_file(
        path_value: str,
        log_id: str,
        tool_name: str | None,
        current_agent: str | None,
        action: str,
        action_timestamp: str,
    ) -> None:
        norm = _normalize_path(path_value)
        if not norm or not _looks_like_file_path(norm):
            return
        file_changes.append(SessionFileUpdate(
            filePath=norm,
            additions=0,
            deletions=0,
            commits=[],
            agentName=current_agent or "",
            action=action,
            fileType=_classify_file_type(norm),
            timestamp=action_timestamp,
            sourceLogId=log_id,
            sourceToolName=tool_name,
            threadSessionId=session_id,
            rootSessionId=root_session_id,
        ))

        basename = norm.rsplit("/", 1)[-1]
        if basename in _MANIFEST_BASENAMES:
            add_artifact(
                kind="manifest",
                title=basename,
                description=f"Manifest referenced at {norm}",
                source="filesystem",
                source_log_id=log_id,
                source_tool_name=tool_name,
            )

    def track_files_from_payload(
        payload: Any,
        log_id: str,
        tool_name: str | None,
        current_agent: str | None,
        action: str,
        action_timestamp: str,
    ) -> None:
        for p in _extract_paths_from_payload(payload):
            track_file(p, log_id, tool_name, current_agent, action, action_timestamp)

    def add_artifact(
        kind: str,
        title: str,
        description: str,
        source: str,
        source_log_id: str | None,
        source_tool_name: str | None,
        url: str | None = None,
    ) -> str | None:
        if not title:
            return None
        artifact_id = _hash_artifact_id(session_id, kind, title, source_log_id)
        if artifact_id in artifacts:
            existing = artifacts[artifact_id]
            if url and not existing.url:
                existing.url = url
            if description and (not existing.description or existing.description == "Skill invocation in transcript"):
                existing.description = description
            if source_tool_name and not existing.sourceToolName:
                existing.sourceToolName = source_tool_name
            return artifact_id
        artifacts[artifact_id] = SessionArtifact(
            id=artifact_id,
            title=title,
            type=kind,
            description=description,
            source=source,
            url=url,
            sourceLogId=source_log_id,
            sourceToolName=source_tool_name,
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

        description_text = f"{framework} test run"
        if status:
            description_text = f"{description_text} ({status})"
        if passed > 0 or failed > 0:
            description_text = f"{description_text}: {passed} passed, {failed} failed-like"

        add_artifact(
            kind="test_run",
            title=title[:200],
            description=description_text[:500],
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

    def add_command_artifacts_from_text(text: str, source_log_id: str) -> None:
        command_names = [m.group(1).strip() for m in _COMMAND_NAME_PATTERN.finditer(text) if m.group(1).strip()]
        command_args = [m.group(1).strip() for m in _COMMAND_ARGS_PATTERN.finditer(text)]
        has_skill_format = bool(_SKILL_FORMAT_PATTERN.search(text))
        parsed_skill_payload = _extract_skill_payload(text) if has_skill_format else {}

        for idx, command_name in enumerate(command_names):
            args_text = command_args[idx] if idx < len(command_args) else ""
            metadata = {"origin": "command-tag"}
            if args_text:
                metadata["args"] = args_text[:4000]
            parsed = _parse_command_context(command_name, args_text)
            if parsed:
                metadata["parsedCommand"] = parsed
            if has_skill_format:
                metadata["skillFormat"] = True
                skill_name = str(parsed_skill_payload.get("skill") or command_name).strip()
                if skill_name and not skill_name.startswith("/"):
                    metadata["skill"] = skill_name

            command_log_idx = append_log(
                timestamp=current_ts,
                speaker="user",
                type="command",
                content=command_name,
                metadata=metadata,
            )
            add_artifact(
                kind="command",
                title=command_name,
                description="User command invoked in session transcript",
                source="command-tag",
                source_log_id=source_log_id,
                source_tool_name=None,
            )

    def process_skill_payload_from_message(text: str, source_log_id: str, source_tool_use_id: str) -> None:
        payload = _extract_skill_payload(text)
        if not payload:
            return

        linked_skill = skill_invocations_by_tool_use_id.get(source_tool_use_id, {}) if source_tool_use_id else {}
        skill_name = str(payload.get("skill") or linked_skill.get("skill") or "").strip()
        if not skill_name or skill_name.startswith("/"):
            return

        skill_summary = str(payload.get("summary") or "Skill loaded into context").strip()[:500]
        base_directory = str(payload.get("baseDirectory") or "").strip()

        source_log_for_artifact = str(linked_skill.get("sourceLogId") or source_log_id)
        source_tool_name = "Skill" if linked_skill else None
        linked_artifact_id = str(linked_skill.get("artifactId") or "")
        artifact_id = linked_artifact_id or add_artifact(
            kind="skill",
            title=skill_name,
            description=skill_summary,
            source="skill-load",
            source_log_id=source_log_for_artifact,
            source_tool_name=source_tool_name,
            url=base_directory or None,
        )

        if artifact_id and artifact_id in artifacts:
            existing = artifacts[artifact_id]
            if base_directory and not existing.url:
                existing.url = base_directory
            if skill_summary and (
                not existing.description
                or existing.description == "Skill invocation in transcript"
                or existing.source == "tool"
            ):
                existing.description = skill_summary
            if existing.source == "tool":
                existing.source = "tool+skill-load"

        session_context["skillLoads"].append({
            "timestamp": current_ts,
            "skill": skill_name,
            "baseDirectory": base_directory,
            "sourceToolUseId": source_tool_use_id,
            "sourceLogId": source_log_id,
        })

    def process_batch_metadata_for_message(log_index: int, text: str) -> None:
        parsed_batch = _parse_batch_execution_message(text)
        if not parsed_batch:
            return

        batch_id = str(parsed_batch.get("batchId") or "").strip()
        tasks = parsed_batch.get("tasks") if isinstance(parsed_batch.get("tasks"), list) else []
        if not batch_id or not tasks:
            return

        message_log = logs[log_index]
        message_log.metadata["batchExecution"] = {
            "batchId": batch_id,
            "taskCount": len(tasks),
            "tasks": tasks[:20],
        }
        session_context["batchExecutions"].append({
            "timestamp": current_ts,
            "batchId": batch_id,
            "taskCount": len(tasks),
            "tasks": tasks[:20],
            "sourceLogId": message_log.id,
        })

        add_artifact(
            kind="task_batch",
            title=f"Batch {batch_id}",
            description=f"Batch execution announced with {len(tasks)} task(s)",
            source="message",
            source_log_id=message_log.id,
            source_tool_name=None,
        )
        for task in tasks:
            task_id = str(task.get("taskId") or "").strip()
            task_name = str(task.get("name") or "").strip()
            task_agent = str(task.get("agent") or "").strip()
            if not task_id:
                continue
            description = task_name or "Batch task assignment"
            if task_agent:
                description = f"{description} ({task_agent})"
            add_artifact(
                kind="batch_task",
                title=task_id,
                description=description[:500],
                source="message",
                source_log_id=message_log.id,
                source_tool_name=None,
            )

    def postprocess_message_log(log_index: int, message_text: str, speaker_value: str, entry_payload: dict[str, Any]) -> None:
        source_log_id = logs[log_index].id
        if speaker_value == "user":
            add_command_artifacts_from_text(message_text, source_log_id)

        raw_source_tool_use_id = entry_payload.get("sourceToolUseID")
        source_tool_use_id = raw_source_tool_use_id.strip() if isinstance(raw_source_tool_use_id, str) else ""
        process_skill_payload_from_message(message_text, source_log_id, source_tool_use_id)

        if speaker_value == "agent":
            process_batch_metadata_for_message(log_index, message_text)

    def record_platform_version(version_value: str, timestamp: str) -> None:
        nonlocal platform_version
        normalized = str(version_value or "").strip()
        if not normalized:
            return
        if normalized not in platform_versions_seen:
            platform_versions_seen.add(normalized)
            platform_versions.append(normalized)
        if not platform_version:
            platform_version = normalized
            return
        if normalized == platform_version:
            return

        transition_timestamp = timestamp or last_ts or first_ts or ""
        transition = SessionPlatformTransition(
            timestamp=transition_timestamp,
            fromVersion=platform_version,
            toVersion=normalized,
        )
        transition_log_idx = append_log(
            timestamp=transition_timestamp,
            speaker="system",
            type="system",
            content=f"Platform version changed: {platform_version} -> {normalized}",
            metadata={
                "eventType": "platform-version-change",
                "platformType": platform_type,
                "fromVersion": platform_version,
                "toVersion": normalized,
            },
        )
        transition.sourceLogId = logs[transition_log_idx].id
        platform_version_transitions.append(transition)
        platform_version = normalized

    def extract_async_task_agent_id(tool_use_result: Any, output_text: str) -> str:
        if isinstance(tool_use_result, dict):
            raw_agent_id = tool_use_result.get("agentId")
            if isinstance(raw_agent_id, str) and raw_agent_id.strip():
                return raw_agent_id.strip()
        match = _ASYNC_TASK_AGENT_ID_PATTERN.search(output_text or "")
        if match:
            return match.group(1).strip()
        return ""

    def link_subagent_to_task_call(
        parent_tool_call_id: str,
        raw_agent_id: str,
        event_timestamp: str,
        source: str,
        source_tool_name: str | None = None,
    ) -> None:
        if not parent_tool_call_id:
            return
        clean_agent_id = (raw_agent_id or "").strip()
        if not clean_agent_id:
            return
        if clean_agent_id.lower().startswith("agent-"):
            clean_agent_id = clean_agent_id.split("agent-", 1)[-1] or clean_agent_id

        linked_session = _normalize_session_id(f"agent-{clean_agent_id}")
        subagent_link_by_parent_tool[parent_tool_call_id] = linked_session

        tool_log_idx = tool_logs_by_id.get(parent_tool_call_id)
        if tool_log_idx is not None:
            logs[tool_log_idx].linkedSessionId = linked_session
            logs[tool_log_idx].metadata["subagentAgentId"] = clean_agent_id

        emit_key = (parent_tool_call_id, linked_session)
        if emit_key in emitted_subagent_starts:
            return
        emitted_subagent_starts.add(emit_key)
        start_idx = append_log(
            timestamp=event_timestamp,
            speaker="system",
            type="subagent_start",
            content=f"Subagent started: {clean_agent_id}",
            linkedSessionId=linked_session,
            relatedToolCallId=parent_tool_call_id,
            metadata={"agentId": clean_agent_id},
        )
        start_log = logs[start_idx]
        add_artifact(
            kind="agent",
            title=f"agent-{clean_agent_id}",
            description="Subagent thread spawned from an Agent/Task tool call",
            source=source,
            source_log_id=start_log.id,
            source_tool_name=source_tool_name or "Task",
        )

    def record_entry_context(entry: dict[str, Any]) -> None:
        entry_type = str(entry.get("type") or "").strip().lower() or "unknown"
        session_context["entryTypeCounts"][entry_type] += 1
        for raw_key in entry.keys():
            key = str(raw_key or "").strip()
            if key:
                session_context["entryKeyCounts"][key] += 1

        cwd = entry.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            session_context["workingDirectories"].add(cwd.strip())
        slug = entry.get("slug")
        if isinstance(slug, str) and slug.strip():
            session_context["slugs"].add(slug.strip())
        user_type = entry.get("userType")
        if isinstance(user_type, str) and user_type.strip():
            session_context["userTypes"].add(user_type.strip())
        permission_mode = entry.get("permissionMode")
        if isinstance(permission_mode, str) and permission_mode.strip():
            session_context["permissionModes"].add(permission_mode.strip())
        version = entry.get("version")
        if isinstance(version, str) and version.strip():
            session_context["versions"].add(version.strip())
        request_id = entry.get("requestId")
        if isinstance(request_id, str) and request_id.strip():
            session_context["requestIds"].add(request_id.strip())
        session_id_value = entry.get("sessionId")
        if isinstance(session_id_value, str) and session_id_value.strip():
            session_context["sessionIds"].add(session_id_value.strip())
        entry_uuid = entry.get("uuid")
        if isinstance(entry_uuid, str) and entry_uuid.strip():
            session_context["entryUuids"].add(entry_uuid.strip())
        parent_uuid = entry.get("parentUuid")
        if isinstance(parent_uuid, str) and parent_uuid.strip():
            session_context["parentUuids"].add(parent_uuid.strip())
        top_level_message_id = entry.get("messageId")
        if isinstance(top_level_message_id, str) and top_level_message_id.strip():
            session_context["messageIds"].add(top_level_message_id.strip())
        tool_use_id = entry.get("toolUseID")
        if isinstance(tool_use_id, str) and tool_use_id.strip():
            session_context["toolUseIDs"].add(tool_use_id.strip())
        parent_tool_use_id = entry.get("parentToolUseID")
        if isinstance(parent_tool_use_id, str) and parent_tool_use_id.strip():
            session_context["parentToolUseIDs"].add(parent_tool_use_id.strip())
        entry_agent_id = entry.get("agentId")
        if isinstance(entry_agent_id, str) and entry_agent_id.strip():
            session_context["agentIds"].add(entry_agent_id.strip())
        source_tool_assistant_uuid = entry.get("sourceToolAssistantUUID")
        if isinstance(source_tool_assistant_uuid, str) and source_tool_assistant_uuid.strip():
            session_context["sourceToolAssistantUUIDs"].add(source_tool_assistant_uuid.strip())
        source_tool_use_id = entry.get("sourceToolUseID")
        if isinstance(source_tool_use_id, str) and source_tool_use_id.strip():
            session_context["sourceToolUseIDs"].add(source_tool_use_id.strip())
        if bool(entry.get("isSidechain", False)):
            session_context["isSidechainCount"] += 1
        if bool(entry.get("isSnapshotUpdate", False)):
            session_context["isSnapshotUpdateCount"] += 1
        if entry.get("snapshot") is not None:
            session_context["snapshotCount"] += 1

        message = entry.get("message")
        if isinstance(message, dict):
            message_id = message.get("id")
            if isinstance(message_id, str) and message_id.strip():
                session_context["messageIds"].add(message_id.strip())

            message_role = str(message.get("role") or "").strip().lower()
            if message_role:
                session_context["messageRoleCounts"][message_role] += 1

            stop_reason = str(message.get("stop_reason") or "").strip().lower()
            if stop_reason:
                session_context["messageStopReasonCounts"][stop_reason] += 1
            stop_sequence = str(message.get("stop_sequence") or "").strip()
            if stop_sequence:
                session_context["messageStopSequenceCounts"][stop_sequence] += 1

            message_type = str(message.get("type") or "").strip().lower()
            if message_type:
                session_context["messageTypeCounts"][message_type] += 1

            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = str(block.get("type") or "").strip().lower()
                    if block_type:
                        session_context["contentBlockTypeCounts"][block_type] += 1
                    for raw_block_key in block.keys():
                        block_key = str(raw_block_key or "").strip()
                        if block_key:
                            session_context["contentBlockKeyCounts"][block_key] += 1
                    if block_type == "tool_use":
                        caller_payload = block.get("caller")
                        caller_type = ""
                        if isinstance(caller_payload, dict):
                            caller_type = str(caller_payload.get("type") or "").strip().lower()
                        elif isinstance(caller_payload, str):
                            caller_type = caller_payload.strip().lower()
                        if caller_type:
                            session_context["toolCallerTypeCounts"][caller_type] += 1

        progress_data = entry.get("data")
        if isinstance(progress_data, dict):
            progress_type = str(progress_data.get("type") or "").strip().lower()
            if progress_type:
                session_context["progressTypeCounts"][progress_type] += 1
            for raw_progress_key in progress_data.keys():
                progress_key = str(raw_progress_key or "").strip()
                if progress_key:
                    session_context["progressDataKeyCounts"][progress_key] += 1

        is_api_error = bool(entry.get("isApiErrorMessage", False))
        error_payload = entry.get("error")
        if is_api_error or error_payload:
            error_msg = ""
            if isinstance(error_payload, str):
                error_msg = error_payload.strip()
            elif isinstance(error_payload, dict):
                error_msg = json.dumps(error_payload, ensure_ascii=True)[:1200]
            if error_msg:
                session_context["apiErrors"].append({
                    "timestamp": str(entry.get("timestamp") or ""),
                    "message": error_msg[:1200],
                })

        raw_thinking = entry.get("thinkingMetadata")
        if isinstance(raw_thinking, dict):
            explicit_level = _normalize_thinking_level(str(raw_thinking.get("level") or ""))
            disabled = bool(raw_thinking.get("disabled", False))
            max_tokens = _coerce_int(raw_thinking.get("maxThinkingTokens"), 0)

            nonlocal thinking_level
            if explicit_level:
                thinking_level = explicit_level
                thinking_meta["source"] = "thinkingMetadata.level"
                thinking_meta["explicitLevel"] = explicit_level
            elif max_tokens > 0:
                inferred = _thinking_level_from_tokens(max_tokens, forensics_schema)
                if inferred:
                    thinking_level = inferred
                    thinking_meta["source"] = "thinkingMetadata.maxThinkingTokens"

            if disabled:
                default_disabled = str(
                    forensics_schema.get("thinking", {}).get("defaults", {}).get("disabled_level", "low")
                ).strip().lower()
                normalized_disabled = _normalize_thinking_level(default_disabled) or "low"
                thinking_level = normalized_disabled
                thinking_meta["source"] = "thinkingMetadata.disabled"

            thinking_meta["maxThinkingTokens"] = max(thinking_meta.get("maxThinkingTokens", 0), max_tokens)
            thinking_meta["disabled"] = bool(thinking_meta.get("disabled", False) or disabled)

        todos = entry.get("todos")
        if isinstance(todos, list):
            for todo in todos:
                if not isinstance(todo, dict):
                    continue
                content = str(todo.get("content") or "").strip()
                if not content:
                    continue
                embedded_todos.append({
                    "content": content,
                    "status": str(todo.get("status") or "").strip().lower() or "unknown",
                    "activeForm": str(todo.get("activeForm") or "").strip(),
                })

    for entry in entries:
        record_entry_context(entry)
        entry_type = entry.get("type", "")
        current_ts = entry.get("timestamp", "")
        current_entry_lineage_metadata = {
            "threadKind": "subagent" if is_subagent else "root",
            "isSynthetic": False,
        }
        entry_uuid_value = str(entry.get("uuid") or "").strip()
        parent_uuid_value = str(entry.get("parentUuid") or "").strip()
        if entry_uuid_value:
            current_entry_lineage_metadata["entryUuid"] = entry_uuid_value
        if parent_uuid_value:
            current_entry_lineage_metadata["parentUuid"] = parent_uuid_value
        raw_message_id = str(entry.get("messageId") or "").strip()
        message_payload = entry.get("message")
        if not raw_message_id and isinstance(message_payload, dict):
            raw_message_id = str(message_payload.get("id") or "").strip()
        if raw_message_id:
            current_entry_lineage_metadata["rawMessageId"] = raw_message_id
        platform_type = _detect_platform_type(entry) or platform_type
        record_platform_version(str(entry.get("version") or ""), current_ts)
        if current_ts and not first_ts:
            first_ts = current_ts
        if current_ts:
            last_ts = current_ts

        if entry_type == "file-history-snapshot":
            git_branch = entry.get("gitBranch", git_branch)
            if isinstance(entry.get("gitAuthor"), str) and not git_author:
                git_author = entry.get("gitAuthor", "")
            if isinstance(entry.get("gitCommit"), str) and not git_commit:
                git_commit = entry.get("gitCommit", "")
            continue

        if isinstance(entry.get("gitBranch"), str) and not git_branch:
            git_branch = entry.get("gitBranch", "")
        if isinstance(entry.get("gitAuthor"), str) and not git_author:
            git_author = entry.get("gitAuthor", "")
        if isinstance(entry.get("gitCommit"), str) and not git_commit:
            git_commit = entry.get("gitCommit", "")

        entry_session_id = entry.get("sessionId")
        if isinstance(entry_session_id, str):
            normalized_parent = _normalize_session_id(entry_session_id)
            if not parent_session_id and normalized_parent and normalized_parent != session_id:
                parent_session_id = normalized_parent
                if not is_subagent:
                    root_session_id = normalized_parent
            if session_type == "subagent":
                root_session_id = parent_session_id or root_session_id

        if not task_id:
            if isinstance(entry.get("taskId"), str):
                task_id = entry.get("taskId", "")
            elif isinstance(entry.get("task_id"), str):
                task_id = entry.get("task_id", "")

        if not agent_id and isinstance(entry.get("agentId"), str):
            agent_id = entry.get("agentId")

        if entry_type == "progress":
            data = entry.get("data", {})
            relay_usage = _extract_relay_mirror_usage(data)
            if relay_usage is not None:
                relay_mirror_totals["excludedCount"] += 1
                relay_mirror_totals["inputTokens"] += relay_usage["inputTokens"]
                relay_mirror_totals["outputTokens"] += relay_usage["outputTokens"]
                relay_mirror_totals["cacheCreationInputTokens"] += relay_usage["cacheCreationInputTokens"]
                relay_mirror_totals["cacheReadInputTokens"] += relay_usage["cacheReadInputTokens"]
            if isinstance(data, dict) and data.get("type") == "agent_progress":
                parent_tool_call_id = entry.get("parentToolUseID")
                subagent_agent_id = data.get("agentId")
                if isinstance(parent_tool_call_id, str) and isinstance(subagent_agent_id, str):
                    link_subagent_to_task_call(parent_tool_call_id, subagent_agent_id, current_ts, "agent-progress")

            elif isinstance(data, dict) and data.get("type") == "bash_progress":
                parent_tool_call_id = entry.get("parentToolUseID")
                output_text = _tool_result_to_text(
                    data.get("output")
                    or data.get("stdout")
                    or data.get("content")
                    or data.get("message")
                    or ""
                )
                command_text = ""
                for key in ("command", "cmd", "script"):
                    raw_command = data.get(key)
                    if isinstance(raw_command, str) and raw_command.strip():
                        command_text = raw_command.strip()
                        break

                related_idx = tool_logs_by_id.get(parent_tool_call_id) if isinstance(parent_tool_call_id, str) else None
                if related_idx is not None:
                    related_log = logs[related_idx]
                    if command_text:
                        related_log.metadata["bashCommand"] = command_text[:4000]
                        resource_signals = register_command_resources(
                            command_text,
                            related_log.id,
                            "progress.bash_progress",
                            current_ts,
                        )
                        if resource_signals:
                            related_log.metadata["resourceSignals"] = resource_signals[:20]
                    bash_command = str(related_log.metadata.get("bashCommand") or command_text)
                    if bash_command:
                        category, label = _classify_bash_command(bash_command)
                        related_log.metadata["toolCategory"] = category
                        related_log.metadata["toolLabel"] = label
                        existing_test_run = related_log.metadata.get("testRun")
                        parsed_test_run = (
                            existing_test_run
                            if isinstance(existing_test_run, dict)
                            else parse_test_run_from_command(bash_command)
                        )
                        if isinstance(parsed_test_run, dict):
                            related_log.metadata["toolCategory"] = "test"
                            related_log.metadata["toolLabel"] = str(parsed_test_run.get("framework") or "test")
                            related_log.metadata.update(flatten_test_run_metadata(parsed_test_run))
                            add_test_run_artifacts(parsed_test_run, related_log.id, "Bash")
                    elapsed = data.get("elapsedTimeSeconds")
                    if isinstance(elapsed, (int, float)):
                        related_log.metadata["bashElapsedSeconds"] = round(float(elapsed), 3)
                    total_lines = data.get("totalLines")
                    if isinstance(total_lines, int):
                        related_log.metadata["bashTotalLines"] = total_lines
                    elif output_text:
                        related_log.metadata["bashTotalLines"] = len(output_text.splitlines())
                    related_log.metadata["bashProgressLinked"] = True

                    if output_text:
                        if related_log.toolCall:
                            existing_output = related_log.toolCall.output or ""
                            if not existing_output:
                                related_log.toolCall.output = output_text[:20000]
                            elif output_text not in existing_output:
                                merged_output = f"{existing_output}\n{output_text}".strip()
                                related_log.toolCall.output = merged_output[:20000]
                        result_state = _classify_bash_result(output_text, False)
                        related_log.metadata["bashResult"] = result_state
                        existing_test_run = related_log.metadata.get("testRun")
                        enriched_test_run = enrich_test_run_with_output(
                            existing_test_run if isinstance(existing_test_run, dict) else None,
                            output_text,
                            is_error=False,
                        )
                        if isinstance(enriched_test_run, dict):
                            related_log.metadata["toolCategory"] = "test"
                            related_log.metadata["toolLabel"] = str(enriched_test_run.get("framework") or "test")
                            related_log.metadata.update(flatten_test_run_metadata(enriched_test_run))
                            add_test_run_artifacts(enriched_test_run, related_log.id, "Bash")

                        commit_candidates = _extract_commit_hashes(f"{bash_command}\n{output_text}")
                        if commit_candidates:
                            existing = related_log.metadata.get("commitHashes")
                            existing_set = set(existing) if isinstance(existing, list) else set()
                            merged = sorted(existing_set.union(commit_candidates))
                            related_log.metadata["commitHashes"] = merged
                            for commit_hash in merged:
                                git_commits.add(commit_hash)
                                add_artifact(
                                    kind="git_commit",
                                    title=commit_hash,
                                    description="Git commit hash observed in Bash progress output",
                                    source="progress",
                                    source_log_id=related_log.id,
                                    source_tool_name="Bash",
                                )

            elif isinstance(data, dict) and data.get("type") == "hook_progress":
                hook_info = _parse_hook_progress(data)
                metadata = {
                    "eventType": "hook_progress",
                    "hook": hook_info.get("hookName", ""),
                    "hookName": hook_info.get("hookName", ""),
                    "hookPath": hook_info.get("hookPath", ""),
                    "hookEvent": hook_info.get("hookEvent", ""),
                    "hookCommand": hook_info.get("command", ""),
                }
                hook_log_idx = append_log(
                    timestamp=current_ts,
                    speaker="system",
                    type="system",
                    content=str(hook_info.get("summary") or "Hook progress"),
                    metadata=metadata,
                )
                hook_title = (
                    hook_info.get("hookName")
                    or (Path(hook_info["hookPath"]).name if hook_info.get("hookPath") else "")
                    or "hook"
                )
                hook_description_parts = [
                    "Hook invocation captured from progress event.",
                    f"Event: {hook_info['hookEvent']}" if hook_info.get("hookEvent") else "",
                    f"Path: {hook_info['hookPath']}" if hook_info.get("hookPath") else "",
                ]
                add_artifact(
                    kind="hook",
                    title=hook_title,
                    description=" ".join(part for part in hook_description_parts if part).strip(),
                    source="hook_progress",
                    source_log_id=logs[hook_log_idx].id,
                    source_tool_name="Hook",
                )
                session_context["hookInvocations"].append({
                    "timestamp": current_ts,
                    "hookName": hook_info.get("hookName", ""),
                    "hookPath": hook_info.get("hookPath", ""),
                    "hookEvent": hook_info.get("hookEvent", ""),
                    "hookCommand": hook_info.get("command", ""),
                    "sourceLogId": logs[hook_log_idx].id,
                })

            label = data.get("message") if isinstance(data, dict) else "Progress event"
            if isinstance(label, str) and label:
                impacts.append(ImpactPoint(timestamp=current_ts, label=label[:200], type="info"))
            continue

        if entry_type == "summary":
            summary_text = str(entry.get("summary") or entry.get("content") or entry.get("message") or "").strip()
            if summary_text:
                idx = append_log(
                    timestamp=current_ts,
                    speaker="system",
                    type="system",
                    content=summary_text[:8000],
                    metadata={"eventType": "summary"},
                )
                add_artifact(
                    kind="summary",
                    title=summary_text[:120],
                    description="Session summary entry",
                    source="summary",
                    source_log_id=logs[idx].id,
                    source_tool_name=None,
                )
            continue

        if entry_type == "custom-title":
            title_text = str(entry.get("title") or entry.get("content") or entry.get("message") or "").strip()
            if title_text:
                idx = append_log(
                    timestamp=current_ts,
                    speaker="system",
                    type="system",
                    content=title_text[:8000],
                    metadata={"eventType": "custom-title"},
                )
                add_artifact(
                    kind="custom_title",
                    title=title_text,
                    description="Custom title assigned to session",
                    source="custom-title",
                    source_log_id=logs[idx].id,
                    source_tool_name=None,
                )
            continue

        if entry_type == "pr-link":
            pr_number = entry.get("prNumber") or entry.get("pr_number")
            pr_url = entry.get("prUrl") or entry.get("pr_url") or entry.get("url")
            pr_repo = entry.get("prRepository") or entry.get("repository")
            if isinstance(entry.get("data"), dict):
                data = entry.get("data", {})
                pr_number = pr_number or data.get("prNumber") or data.get("pr_number")
                pr_url = pr_url or data.get("prUrl") or data.get("pr_url") or data.get("url")
                pr_repo = pr_repo or data.get("prRepository") or data.get("repository")

            title = f"PR #{pr_number}" if pr_number else "PR Link"
            if isinstance(pr_repo, str) and pr_repo.strip():
                title = f"{title} ({pr_repo.strip()})"

            idx = append_log(
                timestamp=current_ts,
                speaker="system",
                type="system",
                content=title,
                metadata={
                    "eventType": "pr-link",
                    "prNumber": pr_number,
                    "prUrl": pr_url,
                    "prRepository": pr_repo,
                },
            )
            add_artifact(
                kind="pr_link",
                title=title,
                description="Pull request linked from session metadata",
                source="pr-link",
                source_log_id=logs[idx].id,
                source_tool_name=None,
                url=pr_url if isinstance(pr_url, str) and pr_url.strip() else None,
            )
            continue

        if entry_type == "queue-operation":
            raw_content = entry.get("content") or entry.get("message") or ""
            if isinstance(entry.get("data"), dict):
                raw_content = raw_content or json.dumps(entry["data"], ensure_ascii=True)
            details = _parse_task_notification(str(raw_content))
            summary = details.get("summary") or str(raw_content)[:240]
            queue_operation = str(entry.get("operation") or "").strip().lower()
            idx = append_log(
                timestamp=current_ts,
                speaker="system",
                type="system",
                content=summary,
                metadata={"eventType": "queue-operation", "operation": queue_operation, **details},
            )
            session_context["queueOperations"].append({
                "timestamp": current_ts,
                "operation": queue_operation,
                "taskId": details.get("task-id", ""),
                "status": details.get("status", ""),
                "summary": summary[:240],
                "toolUseId": details.get("tool-use-id", ""),
                "taskType": details.get("task-type", ""),
                "outputFile": details.get("output-file", ""),
                "shellId": details.get("shell-id", ""),
                "result": details.get("result", "")[:240],
                "description": details.get("description", "")[:240],
            })
            if details:
                title = details.get("task-id", "Task Notification")
                add_artifact(
                    kind="task_notification",
                    title=title,
                    description=summary,
                    source="queue-operation",
                    source_log_id=logs[idx].id,
                    source_tool_name=None,
                )
                output_file = details.get("output-file", "")
                if output_file:
                    add_artifact(
                        kind="task_output",
                        title=output_file,
                        description="Background task output file referenced by queue operation",
                        source="queue-operation",
                        source_log_id=logs[idx].id,
                        source_tool_name=None,
                    )
            continue

        if entry_type not in ("user", "assistant"):
            continue

        message = entry.get("message", {})
        message_role = entry_type
        if isinstance(message, dict) and isinstance(message.get("role"), str):
            message_role = message.get("role")

        speaker = "agent" if message_role == "assistant" else "user"
        agent_name = entry.get("agentName") if speaker == "agent" else None
        current_message_model = ""
        current_message_id = ""
        current_message_type = ""
        current_stop_reason = ""
        current_stop_sequence = ""
        message_usage_in = 0
        message_usage_out = 0
        message_usage_extra: dict[str, Any] = {}

        if isinstance(message, dict):
            message_id = message.get("id")
            if isinstance(message_id, str) and message_id.strip():
                current_message_id = message_id.strip()
            message_type = message.get("type")
            if isinstance(message_type, str) and message_type.strip():
                current_message_type = message_type.strip()
            stop_reason = message.get("stop_reason")
            if isinstance(stop_reason, str) and stop_reason.strip():
                current_stop_reason = stop_reason.strip()
            stop_sequence = message.get("stop_sequence")
            if isinstance(stop_sequence, str) and stop_sequence.strip():
                current_stop_sequence = stop_sequence.strip()
        if isinstance(message, dict) and speaker == "agent":
            assistant_message_count += 1
            msg_model = message.get("model")
            if isinstance(msg_model, str) and msg_model.strip():
                current_message_model = msg_model.strip()
                if not model:
                    model = current_message_model
            usage = message.get("usage", {})
            if isinstance(usage, dict):
                assistant_messages_with_usage += 1
                message_usage_in = int(usage.get("input_tokens", 0) or 0)
                message_usage_out = int(usage.get("output_tokens", 0) or 0)
                usage_message_totals["inputTokens"] += message_usage_in
                usage_message_totals["outputTokens"] += message_usage_out
                for key in (
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                    "service_tier",
                    "inference_geo",
                ):
                    value = usage.get(key)
                    if isinstance(value, (str, int, float)) and str(value).strip():
                        message_usage_extra[key] = value
                cache_creation_input_tokens = _coerce_int(usage.get("cache_creation_input_tokens"), 0)
                cache_read_input_tokens = _coerce_int(usage.get("cache_read_input_tokens"), 0)
                usage_message_totals["cacheCreationInputTokens"] += cache_creation_input_tokens
                usage_message_totals["cacheReadInputTokens"] += cache_read_input_tokens
                service_tier = str(usage.get("service_tier") or "").strip()
                if service_tier:
                    usage_service_tier_counts[service_tier] += 1
                inference_geo = str(usage.get("inference_geo") or "").strip()
                if inference_geo:
                    usage_inference_geo_counts[inference_geo] += 1
                speed = str(usage.get("speed") or "").strip()
                if speed:
                    usage_speed_counts[speed] += 1
                    message_usage_extra["speed"] = speed
                server_tool_use = usage.get("server_tool_use")
                if isinstance(server_tool_use, dict):
                    server_tool_payload: dict[str, int] = {}
                    for key, value in server_tool_use.items():
                        amount = _coerce_int(value, 0)
                        if amount < 0:
                            continue
                        safe_key = str(key or "").strip()
                        if not safe_key:
                            continue
                        server_tool_payload[safe_key] = amount
                        usage_server_tool_use_totals[safe_key] += amount
                    if server_tool_payload:
                        message_usage_extra["server_tool_use"] = server_tool_payload
                iterations = usage.get("iterations")
                iteration_count = len(iterations) if isinstance(iterations, list) else _coerce_int(iterations, 0)
                if iteration_count > 0:
                    usage_iteration_count += iteration_count
                    message_usage_extra["iterationCount"] = iteration_count
                nested_cache = usage.get("cache_creation")
                if isinstance(nested_cache, dict):
                    cache_payload = {}
                    for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
                        value = nested_cache.get(key)
                        if isinstance(value, (int, float)):
                            amount = int(value)
                            cache_payload[key] = amount
                            usage_cache_creation_totals[key] += amount
                    if cache_payload:
                        message_usage_extra["cache_creation"] = cache_payload
                tokens_in += message_usage_in
                tokens_out += message_usage_out

        if isinstance(message, str):
            content = message.strip()
            if content:
                message_metadata: dict[str, Any] = {}
                if current_message_model:
                    message_metadata["model"] = current_message_model
                if current_message_id:
                    message_metadata["messageId"] = current_message_id
                if current_message_type:
                    message_metadata["messageType"] = current_message_type
                if current_stop_reason:
                    message_metadata["stopReason"] = current_stop_reason
                if current_stop_sequence:
                    message_metadata["stopSequence"] = current_stop_sequence
                if speaker == "agent" and (message_usage_in or message_usage_out):
                    message_metadata["inputTokens"] = message_usage_in
                    message_metadata["outputTokens"] = message_usage_out
                    message_metadata["totalTokens"] = message_usage_in + message_usage_out
                if message_usage_extra:
                    message_metadata.update(message_usage_extra)
                idx = append_log(
                    timestamp=current_ts,
                    speaker=speaker,
                    type="message",
                    content=content[:4000],
                    agentName=agent_name,
                    metadata=message_metadata,
                )
                postprocess_message_log(idx, content, speaker, entry)
            continue

        content_blocks = message.get("content", []) if isinstance(message, dict) else []
        if isinstance(content_blocks, str):
            content = content_blocks.strip()
            if content:
                message_metadata: dict[str, Any] = {}
                if current_message_model:
                    message_metadata["model"] = current_message_model
                if current_message_id:
                    message_metadata["messageId"] = current_message_id
                if current_message_type:
                    message_metadata["messageType"] = current_message_type
                if current_stop_reason:
                    message_metadata["stopReason"] = current_stop_reason
                if current_stop_sequence:
                    message_metadata["stopSequence"] = current_stop_sequence
                if speaker == "agent" and (message_usage_in or message_usage_out):
                    message_metadata["inputTokens"] = message_usage_in
                    message_metadata["outputTokens"] = message_usage_out
                    message_metadata["totalTokens"] = message_usage_in + message_usage_out
                if message_usage_extra:
                    message_metadata.update(message_usage_extra)
                idx = append_log(
                    timestamp=current_ts,
                    speaker=speaker,
                    type="message",
                    content=content[:4000],
                    agentName=agent_name,
                    metadata=message_metadata,
                )
                postprocess_message_log(idx, content, speaker, entry)
            continue

        if not isinstance(content_blocks, list):
            continue

        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, str):
                text_parts.append(block)
                continue

            if not isinstance(block, dict):
                continue

            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text)
            elif block_type == "thinking":
                thinking = block.get("thinking", "")
                if isinstance(thinking, str) and thinking.strip():
                    append_log(
                        timestamp=current_ts,
                        speaker="agent",
                        type="thought",
                        content=thinking[:8000],
                        agentName=agent_name,
                    )
            elif block_type == "tool_use":
                tool_name = str(block.get("name", "unknown"))
                tool_id = block.get("id")
                tool_input = block.get("input", {})
                tool_args = json.dumps(tool_input, indent=2, ensure_ascii=True)[:12000]
                tool_metadata: dict[str, Any] = {
                    "toolInputKeys": list(tool_input.keys()) if isinstance(tool_input, dict) else [],
                    "signature": str(block.get("signature") or "").strip(),
                }
                caller_payload = block.get("caller")
                if isinstance(caller_payload, dict):
                    caller_meta: dict[str, Any] = {}
                    for key, value in caller_payload.items():
                        safe_key = str(key or "").strip()
                        if not safe_key:
                            continue
                        if isinstance(value, str):
                            if value.strip():
                                caller_meta[safe_key] = value.strip()
                        elif isinstance(value, (int, float, bool)):
                            caller_meta[safe_key] = value
                    if caller_meta:
                        tool_metadata["caller"] = caller_meta
                        caller_type = str(caller_meta.get("type") or "").strip()
                        if caller_type:
                            tool_metadata["callerType"] = caller_type
                elif isinstance(caller_payload, str) and caller_payload.strip():
                    caller_text = caller_payload.strip()
                    tool_metadata["caller"] = caller_text
                    tool_metadata["callerType"] = caller_text

                linked_session = None
                if isinstance(tool_id, str):
                    linked_session = subagent_link_by_parent_tool.get(tool_id)

                idx = append_log(
                    timestamp=current_ts,
                    speaker="agent",
                    type="tool",
                    content=f"Called {tool_name}",
                    agentName=agent_name,
                    linkedSessionId=linked_session,
                    metadata=tool_metadata,
                    toolCall=ToolCallInfo(
                        id=tool_id if isinstance(tool_id, str) else None,
                        name=tool_name,
                        args=tool_args,
                        status="success",
                        isError=False,
                    ),
                )
                tool_log = logs[idx]
                if isinstance(tool_id, str):
                    tool_logs_by_id[tool_id] = idx
                    tool_started_at_by_id[tool_id] = current_ts

                tool_counter[tool_name] += 1
                tool_total[tool_name] += 1
                tool_success[tool_name] += 1

                if tool_name == "Bash" and isinstance(tool_input, dict):
                    command_text = ""
                    for key in ("command", "cmd", "script"):
                        raw = tool_input.get(key)
                        if isinstance(raw, str) and raw.strip():
                            command_text = raw.strip()
                            break
                    if command_text:
                        category, label = _classify_bash_command(command_text)
                        tool_log.metadata["bashCommand"] = command_text[:4000]
                        tool_log.metadata["toolCategory"] = category
                        tool_log.metadata["toolLabel"] = label
                        resource_signals = register_command_resources(
                            command_text,
                            tool_log.id,
                            "tool.Bash",
                            current_ts,
                        )
                        if resource_signals:
                            tool_log.metadata["resourceSignals"] = resource_signals[:20]
                        plan_status_details = _parse_manage_plan_status_command(command_text)
                        if plan_status_details:
                            tool_log.metadata["planStatus"] = plan_status_details
                            plan_file = str(plan_status_details.get("file") or plan_status_details.get("readFile") or "").strip()
                            status_value = str(plan_status_details.get("status") or "").strip()
                            operation = str(plan_status_details.get("operation") or "run").strip()

                            session_context["planStatusUpdates"].append({
                                "timestamp": current_ts,
                                "operation": operation,
                                "status": status_value,
                                "file": plan_file,
                                "sourceLogId": tool_log.id,
                            })
                            summary = f"{operation} plan status"
                            if status_value:
                                summary = f"{summary}: {status_value}"
                            if plan_file:
                                summary = f"{summary} ({Path(plan_file).name})"
                            add_artifact(
                                kind="plan_status_update",
                                title=summary,
                                description="manage-plan-status.py command observed in Bash tool call",
                                source="tool",
                                source_log_id=tool_log.id,
                                source_tool_name=tool_name,
                            )
                            if plan_file:
                                add_artifact(
                                    kind="plan_file",
                                    title=plan_file,
                                    description="Plan/progress file targeted by manage-plan-status.py",
                                    source="tool",
                                    source_log_id=tool_log.id,
                                    source_tool_name=tool_name,
                                )
                        test_run = parse_test_run_from_command(
                            command_text,
                            description=tool_input.get("description"),
                            timeout=tool_input.get("timeout"),
                        )
                        if test_run:
                            tool_log.metadata["toolCategory"] = "test"
                            tool_log.metadata["toolLabel"] = str(test_run.get("framework") or "test")
                            tool_log.metadata.update(flatten_test_run_metadata(test_run))
                            add_test_run_artifacts(test_run, tool_log.id, tool_name)

                file_action = _FILE_ACTION_BY_TOOL.get(tool_name)
                if file_action:
                    track_files_from_payload(
                        tool_input,
                        tool_log.id,
                        tool_name,
                        agent_name,
                        file_action,
                        current_ts,
                    )

                if tool_name == "Skill" and isinstance(tool_input, dict):
                    skill_name = tool_input.get("skill")
                    if isinstance(skill_name, str) and skill_name:
                        tool_log.metadata["toolCategory"] = "skill"
                        tool_log.metadata["toolLabel"] = skill_name
                        artifact_id = add_artifact(
                            kind="skill",
                            title=skill_name,
                            description="Skill invocation in transcript",
                            source="tool",
                            source_log_id=tool_log.id,
                            source_tool_name=tool_name,
                        )
                        if isinstance(tool_id, str):
                            skill_invocations_by_tool_use_id[tool_id] = {
                                "skill": skill_name,
                                "sourceLogId": tool_log.id,
                                "artifactId": artifact_id or "",
                            }
                if _is_subagent_tool_name(tool_name) and isinstance(tool_input, dict):
                    sub_type = tool_input.get("subagent_type")
                    if not isinstance(sub_type, str) or not sub_type.strip():
                        sub_type = tool_input.get("subagentType")
                    fallback_title = f"{tool_name} subagent" if tool_name else "Task subagent"
                    title = str(sub_type) if isinstance(sub_type, str) and sub_type else fallback_title
                    add_artifact(
                        kind="agent",
                        title=title,
                        description=f"{tool_name} tool invocation that may spawn a subagent",
                        source="tool",
                        source_log_id=tool_log.id,
                        source_tool_name=tool_name,
                    )
                    task_name = str(tool_input.get("name") or "").strip()
                    task_description = str(tool_input.get("description") or "").strip()
                    task_prompt = _coerce_text_blob(tool_input.get("prompt"))
                    task_mode = str(tool_input.get("mode") or "").strip()
                    task_model = str(tool_input.get("model") or "").strip()
                    task_run_in_background = tool_input.get("run_in_background")

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
                    if isinstance(task_run_in_background, bool):
                        tool_log.metadata["taskRunInBackground"] = task_run_in_background
                    elif isinstance(task_run_in_background, str):
                        lowered = task_run_in_background.strip().lower()
                        if lowered in {"true", "false"}:
                            tool_log.metadata["taskRunInBackground"] = lowered == "true"

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
                    if isinstance(sub_type, str) and sub_type.strip():
                        tool_log.metadata["taskSubagentType"] = sub_type.strip()
                        tool_log.metadata["toolCategory"] = "agent"
                        tool_log.metadata["toolLabel"] = sub_type.strip()

            elif block_type == "tool_result":
                related_id = block.get("tool_use_id")
                output_text = _tool_result_to_text(block.get("content", ""))
                is_error = bool(block.get("is_error", False))
                related_idx = tool_logs_by_id.get(related_id) if isinstance(related_id, str) else None
                tool_use_result = entry.get("toolUseResult")
                launch_agent_id = extract_async_task_agent_id(tool_use_result, output_text)
                launch_status = ""
                if isinstance(tool_use_result, dict):
                    launch_status = str(tool_use_result.get("status") or "").strip().lower()
                    reported_total_tokens = _coerce_int(tool_use_result.get("totalTokens"), 0)
                    reported_duration_ms = _coerce_int(
                        tool_use_result.get("totalDurationMs") or tool_use_result.get("durationMs"),
                        0,
                    )
                    reported_tool_use_count = _coerce_int(tool_use_result.get("totalToolUseCount"), 0)
                    if reported_total_tokens > 0 or reported_duration_ms > 0 or reported_tool_use_count > 0:
                        tool_result_reported_totals["reportedCount"] += 1
                        tool_result_reported_totals["totalTokens"] += reported_total_tokens
                        tool_result_reported_totals["totalDurationMs"] += reported_duration_ms
                        tool_result_reported_totals["totalToolUseCount"] += reported_tool_use_count
                    nested_usage = tool_use_result.get("usage")
                    if isinstance(nested_usage, dict):
                        nested_input_tokens = _coerce_int(nested_usage.get("input_tokens"), 0)
                        nested_output_tokens = _coerce_int(nested_usage.get("output_tokens"), 0)
                        nested_cache_creation_tokens = _coerce_int(nested_usage.get("cache_creation_input_tokens"), 0)
                        nested_cache_read_tokens = _coerce_int(nested_usage.get("cache_read_input_tokens"), 0)
                        tool_result_usage_totals["inputTokens"] += nested_input_tokens
                        tool_result_usage_totals["outputTokens"] += nested_output_tokens
                        tool_result_usage_totals["cacheCreationInputTokens"] += nested_cache_creation_tokens
                        tool_result_usage_totals["cacheReadInputTokens"] += nested_cache_read_tokens
                        nested_service_tier = str(nested_usage.get("service_tier") or "").strip()
                        if nested_service_tier:
                            tool_result_usage_service_tier_counts[nested_service_tier] += 1
                        nested_inference_geo = str(nested_usage.get("inference_geo") or "").strip()
                        if nested_inference_geo:
                            tool_result_usage_inference_geo_counts[nested_inference_geo] += 1
                        nested_speed = str(nested_usage.get("speed") or "").strip()
                        if nested_speed:
                            tool_result_usage_speed_counts[nested_speed] += 1
                        nested_server_tool_use = nested_usage.get("server_tool_use")
                        if isinstance(nested_server_tool_use, dict):
                            for key, value in nested_server_tool_use.items():
                                amount = _coerce_int(value, 0)
                                if amount < 0:
                                    continue
                                safe_key = str(key or "").strip()
                                if not safe_key:
                                    continue
                                tool_result_usage_server_tool_use_totals[safe_key] += amount
                        nested_iterations = nested_usage.get("iterations")
                        nested_iteration_count = (
                            len(nested_iterations)
                            if isinstance(nested_iterations, list)
                            else _coerce_int(nested_iterations, 0)
                        )
                        if nested_iteration_count > 0:
                            tool_result_usage_iteration_count += nested_iteration_count
                        nested_cache = nested_usage.get("cache_creation")
                        if isinstance(nested_cache, dict):
                            for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
                                amount = _coerce_int(nested_cache.get(key), 0)
                                if amount < 0:
                                    continue
                                tool_result_usage_cache_creation_totals[key] += amount

                if related_idx is not None:
                    related_log = logs[related_idx]
                    if isinstance(related_log.metadata, dict):
                        if isinstance(tool_use_result, dict):
                            for key, value in tool_use_result.items():
                                if value is None:
                                    continue
                                safe_key = str(key or "").strip()
                                if not safe_key:
                                    continue
                                if safe_key in {"stdout", "stderr"} and isinstance(value, str):
                                    related_log.metadata[f"toolUseResult_{safe_key}"] = value[:4000]
                                    continue
                                if isinstance(value, (str, int, float, bool)):
                                    related_log.metadata[f"toolUseResult_{safe_key}"] = value
                                    continue
                                if isinstance(value, (dict, list)):
                                    try:
                                        related_log.metadata[f"toolUseResult_{safe_key}"] = json.dumps(value, ensure_ascii=True)[:4000]
                                    except Exception:
                                        continue
                        elif isinstance(tool_use_result, str) and tool_use_result.strip():
                            related_log.metadata["toolUseResult_text"] = tool_use_result.strip()[:4000]
                    if related_log.toolCall:
                        related_log.toolCall.output = output_text[:20000]
                        related_log.toolCall.status = "error" if is_error else "success"
                        related_log.toolCall.isError = is_error
                    related_log.relatedToolCallId = related_id
                    if is_error and related_log.toolCall:
                        tool_success[related_log.toolCall.name] -= 1

                    tool_name = related_log.toolCall.name if related_log.toolCall else None
                    if tool_name and isinstance(related_id, str):
                        started_at = tool_started_at_by_id.get(related_id, "")
                        started_ts = _parse_iso_ts(started_at)
                        finished_ts = _parse_iso_ts(current_ts)
                        if started_ts and finished_ts:
                            elapsed_ms = max(0, int((finished_ts - started_ts).total_seconds() * 1000))
                            tool_duration_ms[tool_name] += elapsed_ms
                            if isinstance(related_log.metadata, dict):
                                related_log.metadata["durationMs"] = elapsed_ms
                    if tool_name in _FILE_ACTION_BY_TOOL and is_error:
                        file_changes = [f for f in file_changes if f.sourceLogId != related_log.id]
                    elif tool_name in {"Write", "WriteFile"} and _result_indicates_create(output_text):
                        for file_update in file_changes:
                            if file_update.sourceLogId == related_log.id and file_update.action == "update":
                                file_update.action = "create"
                    if (
                        _is_subagent_tool_name(str(tool_name or ""))
                        and isinstance(related_id, str)
                        and launch_agent_id
                        and (launch_status == "async_launched" or "agentid:" in output_text.lower())
                    ):
                        link_subagent_to_task_call(
                            related_id,
                            launch_agent_id,
                            current_ts,
                            "tool-result",
                            source_tool_name=str(tool_name or "Task"),
                        )
                        if isinstance(related_log.metadata, dict):
                            related_log.metadata["taskLaunchStatus"] = launch_status
                            if isinstance(tool_use_result, dict):
                                related_log.metadata["taskIsAsyncLaunch"] = bool(tool_use_result.get("isAsync", False))
                    if tool_name == "Bash":
                        command_text = ""
                        if isinstance(related_log.metadata, dict):
                            raw = related_log.metadata.get("bashCommand")
                            if isinstance(raw, str):
                                command_text = raw
                        if command_text:
                            existing_test_run = related_log.metadata.get("testRun")
                            parsed_test_run = (
                                existing_test_run
                                if isinstance(existing_test_run, dict)
                                else parse_test_run_from_command(command_text)
                            )
                            if isinstance(parsed_test_run, dict):
                                related_log.metadata["toolCategory"] = "test"
                                related_log.metadata["toolLabel"] = str(parsed_test_run.get("framework") or "test")
                                related_log.metadata.update(flatten_test_run_metadata(parsed_test_run))
                                add_test_run_artifacts(parsed_test_run, related_log.id, str(tool_name or "Bash"))
                        if command_text:
                            resource_signals = register_command_resources(
                                command_text,
                                related_log.id,
                                "tool_result.Bash",
                                current_ts,
                            )
                            if resource_signals and "resourceSignals" not in related_log.metadata:
                                related_log.metadata["resourceSignals"] = resource_signals[:20]
                        related_log.metadata["bashResult"] = _classify_bash_result(output_text, is_error)
                        existing_test_run = related_log.metadata.get("testRun")
                        enriched_test_run = enrich_test_run_with_output(
                            existing_test_run if isinstance(existing_test_run, dict) else None,
                            output_text,
                            is_error=is_error,
                        )
                        if isinstance(enriched_test_run, dict):
                            related_log.metadata["toolCategory"] = "test"
                            related_log.metadata["toolLabel"] = str(enriched_test_run.get("framework") or "test")
                            related_log.metadata.update(flatten_test_run_metadata(enriched_test_run))
                            add_test_run_artifacts(enriched_test_run, related_log.id, str(tool_name or "Bash"))
                        commit_candidates = _extract_commit_hashes(f"{command_text}\n{output_text}")
                        if commit_candidates:
                            existing = related_log.metadata.get("commitHashes")
                            existing_set = set(existing) if isinstance(existing, list) else set()
                            merged = sorted(existing_set.union(commit_candidates))
                            related_log.metadata["commitHashes"] = merged
                            for commit_hash in merged:
                                git_commits.add(commit_hash)
                                add_artifact(
                                    kind="git_commit",
                                    title=commit_hash,
                                    description="Git commit hash observed in Bash output",
                                    source="tool",
                                    source_log_id=related_log.id,
                                    source_tool_name=tool_name,
                                )
                else:
                    append_log(
                        timestamp=current_ts,
                        speaker="system",
                        type="system",
                        content=(f"Unmatched tool result for {related_id}: " if related_id else "Unmatched tool result: ")
                        + output_text[:1000],
                        relatedToolCallId=related_id if isinstance(related_id, str) else None,
                        metadata={"isError": is_error},
                    )

        message_text = "\n".join(part for part in text_parts if part and part.strip()).strip()
        if message_text:
            message_metadata: dict[str, Any] = {}
            if current_message_model:
                message_metadata["model"] = current_message_model
            if current_message_id:
                message_metadata["messageId"] = current_message_id
            if current_message_type:
                message_metadata["messageType"] = current_message_type
            if current_stop_reason:
                message_metadata["stopReason"] = current_stop_reason
            if current_stop_sequence:
                message_metadata["stopSequence"] = current_stop_sequence
            if speaker == "agent" and (message_usage_in or message_usage_out):
                message_metadata["inputTokens"] = message_usage_in
                message_metadata["outputTokens"] = message_usage_out
                message_metadata["totalTokens"] = message_usage_in + message_usage_out
            if message_usage_extra:
                message_metadata.update(message_usage_extra)
            idx = append_log(
                timestamp=current_ts,
                speaker=speaker,
                type="message",
                content=message_text[:8000],
                agentName=agent_name,
                metadata=message_metadata,
            )
            postprocess_message_log(idx, message_text, speaker, entry)

    if not is_subagent:
        nodes_by_uuid, children_by_parent, parent_by_child = _build_entry_graph(entries)
        fork_candidates: list[dict[str, Any]] = []
        for parent_uuid, children in children_by_parent.items():
            conversational_children = [
                child_uuid
                for child_uuid in children
                if bool(nodes_by_uuid.get(child_uuid, {}).get("isConversational", False))
            ]
            if len(conversational_children) <= 1:
                continue
            primary_child_uuid = conversational_children[0]
            for child_uuid in conversational_children[1:]:
                child_node = nodes_by_uuid.get(child_uuid, {})
                fork_candidates.append(
                    {
                        "parentEntryUuid": parent_uuid,
                        "childEntryUuid": child_uuid,
                        "primaryChildEntryUuid": primary_child_uuid,
                        "childTimestamp": str(child_node.get("timestamp") or ""),
                        "childIndex": int(child_node.get("index") or 0),
                    }
                )

        fork_candidates.sort(key=lambda row: (int(row.get("childIndex") or 0), str(row.get("childEntryUuid") or "")))

        if fork_candidates:
            fork_session_id_by_root: dict[str, str] = {}
            fork_depth_by_root: dict[str, int] = {}
            fork_subtree_by_root: dict[str, set[str]] = {}

            for candidate in fork_candidates:
                child_entry_uuid = str(candidate.get("childEntryUuid") or "").strip()
                parent_entry_uuid = str(candidate.get("parentEntryUuid") or "").strip()
                if not child_entry_uuid or child_entry_uuid in fork_session_id_by_root:
                    continue

                ancestor_fork_root = ""
                cursor = parent_entry_uuid
                while cursor:
                    if cursor in fork_session_id_by_root:
                        ancestor_fork_root = cursor
                        break
                    cursor = parent_by_child.get(cursor, "")

                parent_session_for_fork = fork_session_id_by_root.get(ancestor_fork_root, session_id)
                parent_depth = fork_depth_by_root.get(ancestor_fork_root, 0) if ancestor_fork_root else 0
                fork_depth = parent_depth + 1 if parent_session_for_fork else 1
                fork_session_id = _make_fork_session_id(raw_session_id, child_entry_uuid)
                subtree = _collect_subtree_uuids(child_entry_uuid, children_by_parent)

                fork_session_id_by_root[child_entry_uuid] = fork_session_id
                fork_depth_by_root[child_entry_uuid] = fork_depth
                fork_subtree_by_root[child_entry_uuid] = subtree
                fork_descriptors_by_root[child_entry_uuid] = {
                    "forkSessionId": fork_session_id,
                    "parentSessionId": parent_session_for_fork or session_id,
                    "parentEntryUuid": parent_entry_uuid,
                    "childEntryUuid": child_entry_uuid,
                    "childTimestamp": str(candidate.get("childTimestamp") or ""),
                    "contextInheritance": "full",
                    "forkDepth": fork_depth,
                    "entryCount": len(subtree),
                    "detectorConfidence": 1.0,
                }

            if fork_descriptors_by_root:
                entry_owner_by_uuid: dict[str, str] = {entry_uuid: session_id for entry_uuid in nodes_by_uuid}
                ordered_roots = sorted(
                    fork_descriptors_by_root.keys(),
                    key=lambda root_uuid: int(nodes_by_uuid.get(root_uuid, {}).get("index") or 0),
                )
                for root_uuid in ordered_roots:
                    owner_session_id = str(fork_descriptors_by_root[root_uuid]["forkSessionId"])
                    for entry_uuid in fork_subtree_by_root.get(root_uuid, set()):
                        entry_owner_by_uuid[entry_uuid] = owner_session_id

                all_session_ids = [session_id] + [
                    str(fork_descriptors_by_root[root_uuid]["forkSessionId"])
                    for root_uuid in ordered_roots
                ]
                logs_by_session_id: dict[str, list[SessionLog]] = {sid: [] for sid in all_session_ids}
                old_log_ids_by_session_id: dict[str, set[str]] = {sid: set() for sid in all_session_ids}

                for log in logs:
                    metadata = log.metadata if isinstance(log.metadata, dict) else {}
                    entry_uuid = str(metadata.get("entryUuid") or "").strip()
                    target_session_id = session_id
                    if entry_uuid:
                        target_session_id = entry_owner_by_uuid.get(entry_uuid, session_id)
                    if not entry_uuid and target_session_id != session_id:
                        continue
                    if target_session_id not in logs_by_session_id:
                        continue
                    cloned_log = SessionLog(**log.model_dump())
                    logs_by_session_id[target_session_id].append(cloned_log)
                    old_log_ids_by_session_id[target_session_id].add(str(log.id))

                for root_uuid in ordered_roots:
                    descriptor = fork_descriptors_by_root[root_uuid]
                    parent_session_for_fork = str(descriptor.get("parentSessionId") or session_id)
                    parent_logs = logs_by_session_id.get(parent_session_for_fork, [])
                    parent_entry_uuid = str(descriptor.get("parentEntryUuid") or "")
                    fork_session_id = str(descriptor.get("forkSessionId") or "")
                    insertion_index = len(parent_logs)
                    if parent_entry_uuid:
                        for idx, parent_log in enumerate(parent_logs):
                            metadata = parent_log.metadata if isinstance(parent_log.metadata, dict) else {}
                            if str(metadata.get("entryUuid") or "").strip() == parent_entry_uuid:
                                insertion_index = idx + 1
                    first_fork_log = logs_by_session_id.get(fork_session_id, [None])[0]
                    preview_text = ""
                    if isinstance(first_fork_log, SessionLog):
                        preview_text = str(first_fork_log.content or "").strip()[:180]
                    fork_note_id = f"fork-note-{root_uuid}"
                    fork_note_metadata = {
                        "eventType": "fork_start",
                        "threadKind": "fork",
                        "contextInheritance": "full",
                        "isSynthetic": True,
                        "syntheticEventType": "fork_start",
                        "forkSessionId": fork_session_id,
                        "forkPointEntryUuid": root_uuid,
                        "forkPointParentEntryUuid": parent_entry_uuid,
                        "forkPointTimestamp": str(descriptor.get("childTimestamp") or ""),
                        "forkPointPreview": preview_text,
                    }
                    if parent_entry_uuid:
                        fork_note_metadata["entryUuid"] = parent_entry_uuid
                    note_log = SessionLog(
                        id=fork_note_id,
                        timestamp=str(descriptor.get("childTimestamp") or ""),
                        speaker="system",
                        type="system",
                        content=f"Fork created: {fork_session_id} (inherits full parent context)",
                        metadata=fork_note_metadata,
                        linkedSessionId=fork_session_id,
                    )
                    parent_logs.insert(insertion_index, note_log)
                    descriptor["forkPointLogId"] = fork_note_id
                    descriptor["forkPointPreview"] = preview_text

                lineage_root_session_id = session_id
                root_id_map: dict[str, str] = {}
                for target_session_id, target_logs in logs_by_session_id.items():
                    id_map: dict[str, str] = {}
                    for idx, target_log in enumerate(target_logs):
                        old_log_id = str(target_log.id or "")
                        new_log_id = f"log-{idx}"
                        target_log.id = new_log_id
                        id_map[old_log_id] = new_log_id
                        metadata = target_log.metadata if isinstance(target_log.metadata, dict) else {}
                        if target_session_id == lineage_root_session_id:
                            metadata["threadKind"] = "root"
                        else:
                            metadata["threadKind"] = "fork"
                            root_entry_uuid = next(
                                (
                                    root_uuid
                                    for root_uuid, descriptor in fork_descriptors_by_root.items()
                                    if str(descriptor.get("forkSessionId") or "") == target_session_id
                                ),
                                "",
                            )
                            if root_entry_uuid:
                                metadata.setdefault("branchRootEntryUuid", root_entry_uuid)
                    if target_session_id == lineage_root_session_id:
                        root_id_map = id_map
                    else:
                        fork_partitions_by_session_id[target_session_id] = {
                            "idMap": id_map,
                        }

                for root_uuid, descriptor in fork_descriptors_by_root.items():
                    parent_session_for_fork = str(descriptor.get("parentSessionId") or session_id)
                    fork_point_log_id = str(descriptor.get("forkPointLogId") or "")
                    if parent_session_for_fork == lineage_root_session_id:
                        descriptor["forkPointLogId"] = root_id_map.get(fork_point_log_id, fork_point_log_id)
                    else:
                        parent_partition = fork_partitions_by_session_id.get(parent_session_for_fork, {})
                        parent_id_map = parent_partition.get("idMap", {})
                        descriptor["forkPointLogId"] = parent_id_map.get(fork_point_log_id, fork_point_log_id)

                    relationship_metadata = {
                        "label": f"Fork at {root_uuid[:12]}",
                        "forkPointTimestamp": str(descriptor.get("childTimestamp") or ""),
                        "forkPointPreview": str(descriptor.get("forkPointPreview") or ""),
                        "entryCount": int(descriptor.get("entryCount") or 0),
                        "forkDepth": int(descriptor.get("forkDepth") or 0),
                        "detectorConfidence": float(descriptor.get("detectorConfidence") or 1.0),
                    }
                    session_relationships.append(
                        {
                            "id": _make_relationship_id(
                                str(descriptor.get("parentSessionId") or ""),
                                str(descriptor.get("forkSessionId") or ""),
                                "fork",
                                str(descriptor.get("parentEntryUuid") or ""),
                                str(descriptor.get("childEntryUuid") or ""),
                            ),
                            "relationshipType": "fork",
                            "parentSessionId": str(descriptor.get("parentSessionId") or ""),
                            "childSessionId": str(descriptor.get("forkSessionId") or ""),
                            "contextInheritance": "full",
                            "sourcePlatform": "claude_code",
                            "parentEntryUuid": str(descriptor.get("parentEntryUuid") or ""),
                            "childEntryUuid": str(descriptor.get("childEntryUuid") or ""),
                            "sourceLogId": str(descriptor.get("forkPointLogId") or ""),
                            "metadata": relationship_metadata,
                        }
                    )

                logs = logs_by_session_id.get(lineage_root_session_id, [])
                original_file_changes = [SessionFileUpdate(**update.model_dump()) for update in file_changes]
                original_artifacts = [SessionArtifact(**artifact.model_dump()) for artifact in artifacts.values()]

                root_old_ids = old_log_ids_by_session_id.get(lineage_root_session_id, set())
                root_updates: list[SessionFileUpdate] = []
                for update in original_file_changes:
                    source_log_id = str(update.sourceLogId or "")
                    if source_log_id and source_log_id not in root_old_ids:
                        continue
                    cloned_update = SessionFileUpdate(**update.model_dump())
                    if source_log_id:
                        cloned_update.sourceLogId = root_id_map.get(source_log_id, source_log_id)
                    cloned_update.threadSessionId = lineage_root_session_id
                    cloned_update.rootSessionId = lineage_root_session_id
                    root_updates.append(cloned_update)
                file_changes = root_updates

                root_artifacts: dict[str, SessionArtifact] = {}
                for artifact in original_artifacts:
                    source_log_id = str(artifact.sourceLogId or "")
                    if source_log_id and source_log_id not in root_old_ids:
                        continue
                    cloned_artifact = SessionArtifact(**artifact.model_dump())
                    if source_log_id:
                        cloned_artifact.sourceLogId = root_id_map.get(source_log_id, source_log_id)
                    root_artifacts[cloned_artifact.id] = cloned_artifact
                artifacts = root_artifacts

                for root_uuid, descriptor in fork_descriptors_by_root.items():
                    fork_session_id = str(descriptor.get("forkSessionId") or "")
                    fork_logs = logs_by_session_id.get(fork_session_id, [])
                    fork_old_ids = old_log_ids_by_session_id.get(fork_session_id, set())
                    fork_id_map = fork_partitions_by_session_id.get(fork_session_id, {}).get("idMap", {})

                    # Build fork updates/artifacts from original collections.
                    fork_updates_payload: list[dict[str, Any]] = []
                    for original_update in original_file_changes:
                        source_log_id = str(original_update.sourceLogId or "")
                        if source_log_id and source_log_id not in fork_old_ids:
                            continue
                        cloned_update = SessionFileUpdate(**original_update.model_dump())
                        if source_log_id:
                            cloned_update.sourceLogId = fork_id_map.get(source_log_id, source_log_id)
                        cloned_update.threadSessionId = fork_session_id
                        cloned_update.rootSessionId = fork_session_id
                        fork_updates_payload.append(cloned_update.model_dump())

                    fork_artifacts_payload: list[dict[str, Any]] = []
                    for original_artifact in original_artifacts:
                        source_log_id = str(original_artifact.sourceLogId or "")
                        if not source_log_id or source_log_id not in fork_old_ids:
                            continue
                        cloned_artifact = SessionArtifact(**original_artifact.model_dump())
                        cloned_artifact.sourceLogId = fork_id_map.get(source_log_id, source_log_id)
                        fork_artifacts_payload.append(cloned_artifact.model_dump())

                    fork_tokens_in = 0
                    fork_tokens_out = 0
                    fork_tool_counter: Counter[str] = Counter()
                    fork_tool_success: Counter[str] = Counter()
                    fork_tool_total: Counter[str] = Counter()
                    fork_tool_duration: Counter[str] = Counter()
                    fork_first_ts = ""
                    fork_last_ts = ""
                    for fork_log in fork_logs:
                        if fork_log.timestamp and not fork_first_ts:
                            fork_first_ts = fork_log.timestamp
                        if fork_log.timestamp:
                            fork_last_ts = fork_log.timestamp
                        if fork_log.type == "message" and fork_log.speaker == "agent":
                            metadata = fork_log.metadata if isinstance(fork_log.metadata, dict) else {}
                            fork_tokens_in += _coerce_int(metadata.get("inputTokens"), 0)
                            fork_tokens_out += _coerce_int(metadata.get("outputTokens"), 0)
                        if fork_log.type == "tool" and fork_log.toolCall:
                            tool_name = str(fork_log.toolCall.name or "").strip()
                            if not tool_name:
                                continue
                            fork_tool_counter[tool_name] += 1
                            fork_tool_total[tool_name] += 1
                            if str(fork_log.toolCall.status or "").strip().lower() != "error":
                                fork_tool_success[tool_name] += 1
                            metadata = fork_log.metadata if isinstance(fork_log.metadata, dict) else {}
                            fork_tool_duration[tool_name] += _coerce_int(metadata.get("durationMs"), 0)

                    fork_tools_used: list[dict[str, Any]] = []
                    for tool_name, count in fork_tool_counter.most_common():
                        total = max(1, _coerce_int(fork_tool_total.get(tool_name), count))
                        success = max(0, _coerce_int(fork_tool_success.get(tool_name), count))
                        fork_tools_used.append(
                            ToolUsage(
                                name=tool_name,
                                count=count,
                                successRate=round(success / total, 2),
                                totalMs=max(0, _coerce_int(fork_tool_duration.get(tool_name), 0)),
                            ).model_dump()
                        )

                    fork_duration = 0
                    if fork_first_ts and fork_last_ts:
                        try:
                            ts_a = datetime.fromisoformat(fork_first_ts.replace("Z", "+00:00"))
                            ts_b = datetime.fromisoformat(fork_last_ts.replace("Z", "+00:00"))
                            fork_duration = max(0, int((ts_b - ts_a).total_seconds()))
                        except Exception:
                            fork_duration = 0

                    fork_partitions_by_session_id[fork_session_id] = {
                        "idMap": fork_id_map,
                        "logs": [log.model_dump() for log in fork_logs],
                        "oldLogIds": list(fork_old_ids),
                        "updatedFiles": fork_updates_payload,
                        "linkedArtifacts": fork_artifacts_payload,
                        "toolsUsed": fork_tools_used,
                        "tokensIn": fork_tokens_in,
                        "tokensOut": fork_tokens_out,
                        "durationSeconds": fork_duration,
                        "startedAt": fork_first_ts,
                        "endedAt": fork_last_ts,
                        "descriptor": descriptor,
                        "rootEntryUuid": root_uuid,
                    }

                # Recalculate root counters after branch extraction so metrics remain direct-session scoped.
                first_ts = ""
                last_ts = ""
                tokens_in = 0
                tokens_out = 0
                tool_counter = Counter()
                tool_success = Counter()
                tool_total = Counter()
                tool_duration_ms = Counter()
                extracted_commit_hashes: set[str] = set()
                for log in logs:
                    if log.timestamp and not first_ts:
                        first_ts = log.timestamp
                    if log.timestamp:
                        last_ts = log.timestamp
                    if log.type == "message" and log.speaker == "agent":
                        metadata = log.metadata if isinstance(log.metadata, dict) else {}
                        tokens_in += _coerce_int(metadata.get("inputTokens"), 0)
                        tokens_out += _coerce_int(metadata.get("outputTokens"), 0)
                    if log.type == "tool" and log.toolCall:
                        tool_name = str(log.toolCall.name or "").strip()
                        if tool_name:
                            tool_counter[tool_name] += 1
                            tool_total[tool_name] += 1
                            if str(log.toolCall.status or "").strip().lower() != "error":
                                tool_success[tool_name] += 1
                            metadata = log.metadata if isinstance(log.metadata, dict) else {}
                            tool_duration_ms[tool_name] += _coerce_int(metadata.get("durationMs"), 0)
                    metadata = log.metadata if isinstance(log.metadata, dict) else {}
                    commit_hashes = metadata.get("commitHashes")
                    if isinstance(commit_hashes, list):
                        for commit_hash in commit_hashes:
                            clean_hash = str(commit_hash or "").strip()
                            if clean_hash:
                                extracted_commit_hashes.add(clean_hash)
                git_commits.update(extracted_commit_hashes)

    duration = 0
    if first_ts and last_ts:
        try:
            t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration = max(0, int((t2 - t1).total_seconds()))
        except (ValueError, TypeError):
            duration = 0

    tools_used = []
    for name, count in tool_counter.most_common():
        total = tool_total.get(name, count)
        success = max(0, tool_success.get(name, count))
        rate = success / total if total > 0 else 1.0
        tools_used.append(ToolUsage(
            name=name,
            count=count,
            successRate=round(rate, 2),
            totalMs=max(0, int(tool_duration_ms.get(name, 0))),
        ))

    cost = _estimate_cost(tokens_in, tokens_out, model)
    if git_commit:
        git_commits.add(git_commit)
    sorted_commits = sorted(git_commits)
    primary_commit = git_commit or (sorted_commits[0] if sorted_commits else None)
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
    for index, transition in enumerate(platform_version_transitions):
        if not transition.timestamp:
            continue
        timeline.append({
            "id": f"platform-version-change-{index + 1}",
            "timestamp": transition.timestamp,
            "label": f"Platform Version Changed ({transition.fromVersion} -> {transition.toVersion})",
            "kind": "platform-version-change",
            "confidence": "high",
            "source": "session",
            "description": "Session event stream reported a platform version change",
        })

    todo_sidecar = _collect_todo_sidecar(claude_root, raw_session_id, forensics_schema)
    task_sidecar = _collect_task_sidecar(claude_root, raw_session_id, forensics_schema)
    team_sidecar = _collect_team_sidecar(claude_root, raw_session_id, forensics_schema)
    session_env_sidecar = _collect_session_env_sidecar(claude_root, raw_session_id, forensics_schema)
    tool_results_sidecar = _collect_tool_results_sidecar(path, raw_session_id, is_subagent, forensics_schema)

    if embedded_todos:
        embedded_counts: Counter[str] = Counter(item.get("status", "unknown") for item in embedded_todos)
        if not todo_sidecar.get("items"):
            todo_sidecar["items"] = embedded_todos[:100]
            todo_sidecar["totalItems"] = len(embedded_todos)
            todo_sidecar["counts"] = dict(embedded_counts)
        else:
            todo_sidecar["embeddedItems"] = embedded_todos[:100]
            todo_sidecar["embeddedCounts"] = dict(embedded_counts)

    for todo_file in todo_sidecar.get("files", [])[:20]:
        add_artifact(
            kind="todo_file",
            title=Path(todo_file).name,
            description=f"Session-linked todo sidecar ({todo_file})",
            source="sidecar",
            source_log_id=None,
            source_tool_name=None,
            url=todo_file,
        )

    if task_sidecar.get("exists", False):
        add_artifact(
            kind="task_dir",
            title=Path(str(task_sidecar.get("directory", ""))).name,
            description="Session-linked task queue directory",
            source="sidecar",
            source_log_id=None,
            source_tool_name=None,
            url=str(task_sidecar.get("directory", "")),
        )

    for inbox in team_sidecar.get("inboxes", [])[:20]:
        inbox_name = str(inbox.get("name") or "team-inbox")
        add_artifact(
            kind="team_inbox",
            title=inbox_name,
            description="Session-linked Claude Team inbox",
            source="sidecar",
            source_log_id=None,
            source_tool_name=None,
            url=str(inbox.get("file") or ""),
        )
    if session_env_sidecar.get("exists", False):
        add_artifact(
            kind="session_env",
            title=Path(str(session_env_sidecar.get("directory", ""))).name,
            description="Session-linked environment snapshot directory",
            source="sidecar",
            source_log_id=None,
            source_tool_name=None,
            url=str(session_env_sidecar.get("directory", "")),
        )
        for env_file in session_env_sidecar.get("files", [])[:20]:
            add_artifact(
                kind="session_env_file",
                title=Path(str(env_file)).name,
                description="Session environment sidecar file",
                source="sidecar",
                source_log_id=None,
                source_tool_name=None,
                url=str(env_file),
            )
    if tool_results_sidecar.get("exists", False):
        add_artifact(
            kind="tool_results",
            title=Path(str(tool_results_sidecar.get("directory", ""))).name or "tool-results",
            description="Session-linked tool results directory",
            source="sidecar",
            source_log_id=None,
            source_tool_name=None,
            url=str(tool_results_sidecar.get("directory", "")),
        )
        for item in tool_results_sidecar.get("largestFiles", [])[:20]:
            row = item if isinstance(item, dict) else {}
            file_name = str(row.get("name") or "")
            file_path = str(row.get("path") or "")
            file_size = _coerce_int(row.get("bytes"), 0)
            if not file_name:
                continue
            add_artifact(
                kind="tool_result_file",
                title=file_name,
                description=f"Tool result sidecar file ({file_size} bytes)",
                source="sidecar",
                source_log_id=None,
                source_tool_name=None,
                url=file_path or None,
            )

    if not thinking_level and int(thinking_meta.get("maxThinkingTokens") or 0) > 0:
        thinking_level = _thinking_level_from_tokens(int(thinking_meta.get("maxThinkingTokens") or 0), forensics_schema)

    if not thinking_level and bool(thinking_meta.get("disabled", False)):
        default_disabled = str(
            forensics_schema.get("thinking", {}).get("defaults", {}).get("disabled_level", "low")
        ).strip().lower()
        thinking_level = _normalize_thinking_level(default_disabled) or "low"

    resource_category_counts: Counter[str] = Counter()
    resource_scope_counts: Counter[str] = Counter()
    resource_target_counts: Counter[str] = Counter()
    for observation in resource_observations:
        category = str(observation.get("category") or "").strip()
        target = str(observation.get("target") or "").strip()
        scope = str(observation.get("scope") or "").strip()
        if category:
            resource_category_counts[category] += 1
        if scope:
            resource_scope_counts[scope] += 1
        if category and target:
            resource_target_counts[f"{category}:{target}"] += 1

    queue_operation_counts: Counter[str] = Counter()
    queue_status_counts: Counter[str] = Counter()
    queue_task_type_counts: Counter[str] = Counter()
    distinct_queue_tasks: set[str] = set()
    for operation in session_context.get("queueOperations", []):
        if not isinstance(operation, dict):
            continue
        operation_name = str(operation.get("operation") or "").strip().lower() or "unknown"
        status_name = str(operation.get("status") or "").strip().lower() or "unknown"
        task_type = str(operation.get("taskType") or "").strip().lower() or "unknown"
        task_id_value = str(operation.get("taskId") or "").strip()
        queue_operation_counts[operation_name] += 1
        queue_status_counts[status_name] += 1
        queue_task_type_counts[task_type] += 1
        if task_id_value:
            distinct_queue_tasks.add(task_id_value)

    waiting_for_task_count = _coerce_int(
        session_context.get("progressTypeCounts", Counter()).get("waiting_for_task", 0),
        0,
    )

    task_tool_logs = [
        log for log in logs
        if log.type == "tool" and log.toolCall and _is_subagent_tool_name(str(log.toolCall.name or ""))
    ]
    linked_subagent_ids = {
        str(log.linkedSessionId)
        for log in logs
        if log.type == "subagent_start" and str(log.linkedSessionId or "").strip()
    }
    linked_task_tool_count = sum(1 for log in task_tool_logs if str(log.linkedSessionId or "").strip())
    subagent_root_dir = _resolve_session_sidecar_root(path, raw_session_id, is_subagent)
    subagent_transcript_files = [
        item for item in sorted((subagent_root_dir / "subagents").glob("*.jsonl"))
        if item.is_file()
    ] if (subagent_root_dir / "subagents").exists() else []

    tool_result_file_count = _coerce_int(tool_results_sidecar.get("fileCount"), 0)
    tool_result_total_bytes = _coerce_int(tool_results_sidecar.get("totalBytes"), 0)
    tool_result_max_file_bytes = _coerce_int(tool_results_sidecar.get("maxFileBytes"), 0)
    tool_result_avg_file_bytes = _coerce_float(tool_results_sidecar.get("avgFileBytes"), 0.0)
    tool_result_large_file_count = _coerce_int(tool_results_sidecar.get("largeFileCount"), 0)

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

    platform_telemetry = _platform_telemetry_summary(sorted(session_context.get("workingDirectories", set())))
    fork_cards_by_parent_session: dict[str, list[dict[str, Any]]] = {}
    fork_children_count_by_parent: Counter[str] = Counter()
    for root_uuid, descriptor in fork_descriptors_by_root.items():
        parent_session_for_fork = str(descriptor.get("parentSessionId") or "")
        child_session_id = str(descriptor.get("forkSessionId") or "")
        fork_card = {
            "sessionId": child_session_id,
            "label": f"Fork {root_uuid[:8]}",
            "forkPointTimestamp": str(descriptor.get("childTimestamp") or ""),
            "forkPointPreview": str(descriptor.get("forkPointPreview") or ""),
            "entryCount": int(descriptor.get("entryCount") or 0),
            "contextInheritance": "full",
        }
        if parent_session_for_fork and child_session_id:
            fork_cards_by_parent_session.setdefault(parent_session_for_fork, []).append(fork_card)
            fork_children_count_by_parent[parent_session_for_fork] += 1
    root_fork_cards = fork_cards_by_parent_session.get(session_id, [])
    fork_max_depth = max((int(descriptor.get("forkDepth") or 0) for descriptor in fork_descriptors_by_root.values()), default=0)
    branch_topology = {
        "forkCount": len(fork_descriptors_by_root),
        "maxForkDepth": fork_max_depth,
        "forkSessionIds": sorted(
            str(descriptor.get("forkSessionId") or "")
            for descriptor in fork_descriptors_by_root.values()
            if str(descriptor.get("forkSessionId") or "")
        ),
        "forkRootEntryUuids": sorted(fork_descriptors_by_root.keys()),
    }
    root_session_relationships = [
        relationship
        for relationship in session_relationships
        if str(relationship.get("parentSessionId") or "") == session_id
        or str(relationship.get("childSessionId") or "") == session_id
    ]

    session_forensics = {
        "platform": str(forensics_schema.get("platform") or "claude_code"),
        "schemaVersion": _coerce_int(forensics_schema.get("schema_version"), 1),
        "rawSessionId": raw_session_id,
        "sessionFile": str(path),
        "claudeRoot": str(claude_root) if claude_root else "",
        "thinking": {
            "level": thinking_level,
            "source": str(thinking_meta.get("source") or ""),
            "maxThinkingTokens": int(thinking_meta.get("maxThinkingTokens") or 0),
            "disabled": bool(thinking_meta.get("disabled", False)),
            "explicitLevel": str(thinking_meta.get("explicitLevel") or ""),
        },
        "entryContext": {
            "workingDirectories": sorted(session_context.get("workingDirectories", set())),
            "slugs": sorted(session_context.get("slugs", set())),
            "userTypes": sorted(session_context.get("userTypes", set())),
            "permissionModes": sorted(session_context.get("permissionModes", set())),
            "versions": sorted(session_context.get("versions", set())),
            "requestIds": sorted(session_context.get("requestIds", set())),
            "sessionIds": sorted(session_context.get("sessionIds", set())),
            "entryUuids": sorted(session_context.get("entryUuids", set())),
            "parentUuids": sorted(session_context.get("parentUuids", set())),
            "messageIds": sorted(session_context.get("messageIds", set())),
            "toolUseIDs": sorted(session_context.get("toolUseIDs", set())),
            "parentToolUseIDs": sorted(session_context.get("parentToolUseIDs", set())),
            "agentIds": sorted(session_context.get("agentIds", set())),
            "sourceToolAssistantUUIDs": sorted(session_context.get("sourceToolAssistantUUIDs", set())),
            "sourceToolUseIDs": sorted(session_context.get("sourceToolUseIDs", set())),
            "entryTypeCounts": dict(session_context.get("entryTypeCounts", Counter())),
            "entryKeyCounts": dict(session_context.get("entryKeyCounts", Counter())),
            "messageRoleCounts": dict(session_context.get("messageRoleCounts", Counter())),
            "messageStopReasonCounts": dict(session_context.get("messageStopReasonCounts", Counter())),
            "messageStopSequenceCounts": dict(session_context.get("messageStopSequenceCounts", Counter())),
            "messageTypeCounts": dict(session_context.get("messageTypeCounts", Counter())),
            "contentBlockTypeCounts": dict(session_context.get("contentBlockTypeCounts", Counter())),
            "contentBlockKeyCounts": dict(session_context.get("contentBlockKeyCounts", Counter())),
            "toolCallerTypeCounts": dict(session_context.get("toolCallerTypeCounts", Counter())),
            "progressTypeCounts": dict(session_context.get("progressTypeCounts", Counter())),
            "progressDataKeyCounts": dict(session_context.get("progressDataKeyCounts", Counter())),
            "isSidechainCount": int(session_context.get("isSidechainCount", 0)),
            "isSnapshotUpdateCount": int(session_context.get("isSnapshotUpdateCount", 0)),
            "snapshotCount": int(session_context.get("snapshotCount", 0)),
            "apiErrors": list(session_context.get("apiErrors", []))[:50],
            "queueOperations": list(session_context.get("queueOperations", []))[:200],
            "skillLoads": list(session_context.get("skillLoads", []))[:200],
            "planStatusUpdates": list(session_context.get("planStatusUpdates", []))[:400],
            "batchExecutions": list(session_context.get("batchExecutions", []))[:200],
            "hookInvocations": list(session_context.get("hookInvocations", []))[:400],
        },
        "sidecars": {
            "todos": todo_sidecar,
            "tasks": task_sidecar,
            "teams": team_sidecar,
            "sessionEnv": session_env_sidecar,
            "toolResults": tool_results_sidecar,
        },
        "subagentTopology": {
            "isSubagentSession": bool(is_subagent),
            "taskToolCallCount": len(task_tool_logs),
            "linkedTaskToolCallCount": linked_task_tool_count,
            "orphanTaskToolCallCount": max(0, len(task_tool_logs) - linked_task_tool_count),
            "subagentStartCount": len(linked_subagent_ids),
            "linkedSessionIds": sorted(linked_subagent_ids)[:200],
            "agentIdsSeen": sorted(session_context.get("agentIds", set())),
            "subagentTranscriptFileCount": len(subagent_transcript_files),
        },
        "queuePressure": {
            "queueOperationCount": sum(queue_operation_counts.values()),
            "waitingForTaskCount": waiting_for_task_count,
            "distinctTaskCount": len(distinct_queue_tasks),
            "operationCounts": dict(queue_operation_counts),
            "statusCounts": dict(queue_status_counts),
            "taskTypeCounts": dict(queue_task_type_counts),
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
        "toolResultIntensity": {
            "fileCount": tool_result_file_count,
            "totalBytes": tool_result_total_bytes,
            "maxFileBytes": tool_result_max_file_bytes,
            "avgFileBytes": tool_result_avg_file_bytes,
            "largeFileCount": tool_result_large_file_count,
            "largestFiles": list(tool_results_sidecar.get("largestFiles") or [])[:20],
        },
        "usageSummary": {
            "assistantMessageCount": assistant_message_count,
            "assistantMessagesWithUsage": assistant_messages_with_usage,
            "messageTotals": {
                **usage_message_totals,
                "allInputTokens": (
                    usage_message_totals["inputTokens"]
                    + usage_message_totals["cacheCreationInputTokens"]
                    + usage_message_totals["cacheReadInputTokens"]
                ),
                "allTokens": (
                    usage_message_totals["inputTokens"]
                    + usage_message_totals["outputTokens"]
                    + usage_message_totals["cacheCreationInputTokens"]
                    + usage_message_totals["cacheReadInputTokens"]
                ),
            },
            "relayMirrorTotals": {
                **relay_mirror_totals,
                "allInputTokens": (
                    relay_mirror_totals["inputTokens"]
                    + relay_mirror_totals["cacheCreationInputTokens"]
                    + relay_mirror_totals["cacheReadInputTokens"]
                ),
                "allTokens": (
                    relay_mirror_totals["inputTokens"]
                    + relay_mirror_totals["outputTokens"]
                    + relay_mirror_totals["cacheCreationInputTokens"]
                    + relay_mirror_totals["cacheReadInputTokens"]
                ),
                "policy": _RELAY_MIRROR_POLICY,
            },
            "cacheCreationTotals": usage_cache_creation_totals,
            "serviceTierCounts": dict(usage_service_tier_counts),
            "inferenceGeoCounts": dict(usage_inference_geo_counts),
            "speedCounts": dict(usage_speed_counts),
            "serverToolUseTotals": dict(usage_server_tool_use_totals),
            "iterationCount": usage_iteration_count,
            "toolResultReportedTotals": tool_result_reported_totals,
            "toolResultUsageTotals": {
                **tool_result_usage_totals,
                "allInputTokens": (
                    tool_result_usage_totals["inputTokens"]
                    + tool_result_usage_totals["cacheCreationInputTokens"]
                    + tool_result_usage_totals["cacheReadInputTokens"]
                ),
                "allTokens": (
                    tool_result_usage_totals["inputTokens"]
                    + tool_result_usage_totals["outputTokens"]
                    + tool_result_usage_totals["cacheCreationInputTokens"]
                    + tool_result_usage_totals["cacheReadInputTokens"]
                ),
            },
            "toolResultCacheCreationTotals": tool_result_usage_cache_creation_totals,
            "toolResultServiceTierCounts": dict(tool_result_usage_service_tier_counts),
            "toolResultInferenceGeoCounts": dict(tool_result_usage_inference_geo_counts),
            "toolResultSpeedCounts": dict(tool_result_usage_speed_counts),
            "toolResultServerToolUseTotals": dict(tool_result_usage_server_tool_use_totals),
            "toolResultIterationCount": tool_result_usage_iteration_count,
        },
        "forkSummary": {
            "threadKind": "subagent" if is_subagent else "root",
            "conversationFamilyId": root_session_id if is_subagent and root_session_id else session_id,
            "forkCount": len(fork_descriptors_by_root),
            "detectorConfidence": 1.0 if fork_descriptors_by_root else 0.0,
            "forks": root_fork_cards[:200],
            "relationshipCount": len(session_relationships),
        },
        "branchTopology": branch_topology,
        "testExecution": test_execution,
        "platformTelemetry": platform_telemetry,
        "analysisSignals": {
            "hasQueuePressureSignals": bool(waiting_for_task_count > 0 or queue_operation_counts),
            "hasResourceSignals": bool(resource_observations),
            "hasToolResultSignals": bool(tool_result_file_count > 0),
            "hasSubagentSignals": bool(task_tool_logs or linked_subagent_ids),
            "hasTestRunSignals": bool(_coerce_int(test_execution.get("runCount"), 0) > 0),
        },
    }

    for fork_session_id, partition in fork_partitions_by_session_id.items():
        if not isinstance(partition, dict):
            continue
        descriptor = partition.get("descriptor", {})
        if not isinstance(descriptor, dict):
            descriptor = {}
        fork_started_at = str(partition.get("startedAt") or "")
        fork_ended_at = str(partition.get("endedAt") or "")
        fork_dates: dict[str, Any] = {}
        for key, candidate in (
            ("createdAt", make_date_value(fs_dates.get("createdAt", ""), "high", "filesystem", "session_file_created")),
            ("updatedAt", make_date_value(fs_dates.get("updatedAt", ""), "high", "filesystem", "session_file_modified")),
            ("startedAt", make_date_value(fork_started_at, "high", "session", "fork_first_log_event")),
            ("completedAt", make_date_value(fork_ended_at, "high", "session", "fork_last_log_event")),
            ("endedAt", make_date_value(fork_ended_at, "high", "session", "fork_last_log_event")),
            ("lastActivityAt", make_date_value(fork_ended_at or fs_dates.get("updatedAt", ""), "high", "session", "fork_last_activity")),
        ):
            if candidate:
                fork_dates[key] = candidate
        fork_timeline: list[dict[str, Any]] = []
        if fork_started_at:
            fork_timeline.append(
                {
                    "id": "session-started",
                    "timestamp": fork_started_at,
                    "label": "Fork Started",
                    "kind": "started",
                    "confidence": "high",
                    "source": "session",
                    "description": "First fork log event",
                }
            )
        if fork_ended_at:
            fork_timeline.append(
                {
                    "id": "session-completed",
                    "timestamp": fork_ended_at,
                    "label": "Fork Completed",
                    "kind": "completed",
                    "confidence": "high",
                    "source": "session",
                    "description": "Last fork log event",
                }
            )

        fork_session_relationships = [
            relationship
            for relationship in session_relationships
            if str(relationship.get("parentSessionId") or "") == fork_session_id
            or str(relationship.get("childSessionId") or "") == fork_session_id
        ]
        fork_forensics = {
            "platform": str(forensics_schema.get("platform") or "claude_code"),
            "schemaVersion": _coerce_int(forensics_schema.get("schema_version"), 1),
            "rawSessionId": raw_session_id,
            "sessionFile": str(path),
            "threadKind": "fork",
            "conversationFamilyId": session_id,
            "forkSummary": {
                "forkSessionId": fork_session_id,
                "parentSessionId": str(descriptor.get("parentSessionId") or ""),
                "forkPointEntryUuid": str(descriptor.get("childEntryUuid") or ""),
                "forkPointParentEntryUuid": str(descriptor.get("parentEntryUuid") or ""),
                "entryCount": int(descriptor.get("entryCount") or 0),
                "forkDepth": int(descriptor.get("forkDepth") or 0),
                "forkCount": int(fork_children_count_by_parent.get(fork_session_id, 0)),
            },
            "branchTopology": {
                "branchRootEntryUuid": str(partition.get("rootEntryUuid") or ""),
                "entryCount": int(descriptor.get("entryCount") or 0),
                "forkDepth": int(descriptor.get("forkDepth") or 0),
            },
        }

        derived_sessions.append(
            AgentSession(
                id=fork_session_id,
                title=f"Fork from {str(descriptor.get('parentSessionId') or session_id)}",
                taskId=task_id,
                status=session_status,
                model=model,
                platformType=platform_type,
                platformVersion=platform_version,
                platformVersions=platform_versions,
                platformVersionTransitions=[],
                sessionType="fork",
                parentSessionId=None,
                rootSessionId=fork_session_id,
                agentId=agent_id,
                threadKind="fork",
                conversationFamilyId=session_id,
                contextInheritance="full",
                forkParentSessionId=str(descriptor.get("parentSessionId") or ""),
                forkPointLogId=str(descriptor.get("forkPointLogId") or ""),
                forkPointEntryUuid=str(descriptor.get("childEntryUuid") or ""),
                forkPointParentEntryUuid=str(descriptor.get("parentEntryUuid") or ""),
                forkDepth=int(descriptor.get("forkDepth") or 0),
                forkCount=int(fork_children_count_by_parent.get(fork_session_id, 0)),
                durationSeconds=_coerce_int(partition.get("durationSeconds"), 0),
                tokensIn=_coerce_int(partition.get("tokensIn"), 0),
                tokensOut=_coerce_int(partition.get("tokensOut"), 0),
                totalCost=round(
                    _estimate_cost(
                        _coerce_int(partition.get("tokensIn"), 0),
                        _coerce_int(partition.get("tokensOut"), 0),
                        model,
                    ),
                    4,
                ),
                startedAt=fork_started_at,
                endedAt=fork_ended_at,
                createdAt=fs_dates.get("createdAt", ""),
                updatedAt=fs_dates.get("updatedAt", ""),
                gitBranch=git_branch or None,
                gitAuthor=git_author or None,
                gitCommitHash=primary_commit,
                gitCommitHashes=sorted_commits,
                updatedFiles=partition.get("updatedFiles", []),
                linkedArtifacts=partition.get("linkedArtifacts", []),
                toolsUsed=partition.get("toolsUsed", []),
                impactHistory=[],
                logs=partition.get("logs", []),
                thinkingLevel=thinking_level,
                sessionForensics=fork_forensics,
                forks=fork_cards_by_parent_session.get(fork_session_id, []),
                sessionRelationships=fork_session_relationships,
                dates=fork_dates,
                timeline=fork_timeline,
            ).model_dump()
        )

    return AgentSession(
        id=session_id,
        taskId=task_id,
        status=session_status,
        model=model,
        platformType=platform_type,
        platformVersion=platform_version,
        platformVersions=platform_versions,
        platformVersionTransitions=platform_version_transitions,
        sessionType=session_type,
        parentSessionId=parent_session_id or None,
        rootSessionId=root_session_id,
        agentId=agent_id,
        threadKind="subagent" if is_subagent else "root",
        conversationFamilyId=root_session_id if is_subagent and root_session_id else session_id,
        contextInheritance="fresh",
        forkParentSessionId=None,
        forkPointLogId=None,
        forkPointEntryUuid=None,
        forkPointParentEntryUuid=None,
        forkDepth=0,
        forkCount=int(fork_children_count_by_parent.get(session_id, 0)),
        durationSeconds=duration,
        tokensIn=tokens_in,
        tokensOut=tokens_out,
        totalCost=round(cost, 4),
        startedAt=first_ts,
        endedAt=last_ts,
        createdAt=fs_dates.get("createdAt", ""),
        updatedAt=fs_dates.get("updatedAt", ""),
        gitBranch=git_branch or None,
        gitAuthor=git_author or None,
        gitCommitHash=primary_commit,
        gitCommitHashes=sorted_commits,
        updatedFiles=file_changes,
        linkedArtifacts=list(artifacts.values()),
        toolsUsed=tools_used,
        impactHistory=impacts,
        logs=logs,
        thinkingLevel=thinking_level,
        sessionForensics=session_forensics,
        forks=root_fork_cards,
        sessionRelationships=root_session_relationships,
        derivedSessions=derived_sessions,
        dates=session_dates,
        timeline=timeline,
    )


def scan_sessions(sessions_dir: Path, max_files: int = 50) -> list[AgentSession]:
    """Scan a directory for JSONL session files and parse them.

    To avoid excessive load with large session directories, only the
    *max_files* most recently modified files are parsed.
    """
    sessions = []
    if not sessions_dir.exists():
        return sessions

    jsonl_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:max_files]

    for path in jsonl_files:
        session = parse_session_file(path)
        if session:
            sessions.append(session)

    return sessions
