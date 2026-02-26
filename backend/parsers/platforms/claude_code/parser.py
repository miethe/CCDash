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
_TASK_ID_PATTERN = re.compile(r"\b([A-Z]{2,10}-[A-Z0-9]+-\d{1,4})\b")
_BATCH_HEADER_PATTERN = re.compile(r"(?:\*\*)?\s*Batch\s+([A-Za-z0-9_-]+)\s*(?:\*\*)?", re.IGNORECASE)
_BATCH_BULLET_PATTERN = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*\s*:\s*(.+?)\s*$")
_MODEL_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,}$")
_MODEL_COMMAND_STOPWORDS = {"set", "to", "use", "default", "auto", "list", "show", "current", "model"}

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
        "messageTypeCounts": Counter(),
        "contentBlockTypeCounts": Counter(),
        "contentBlockKeyCounts": Counter(),
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
    }

    tool_logs_by_id: dict[str, int] = {}
    tool_started_at_by_id: dict[str, str] = {}
    subagent_link_by_parent_tool: dict[str, str] = {}
    skill_invocations_by_tool_use_id: dict[str, dict[str, Any]] = {}
    emitted_subagent_starts: set[tuple[str, str]] = set()

    log_idx = 0

    def append_log(**kwargs: Any) -> int:
        nonlocal log_idx
        metadata = kwargs.get("metadata")
        if metadata is None:
            kwargs["metadata"] = {}
        elif not isinstance(metadata, dict):
            kwargs["metadata"] = {}
        log = SessionLog(id=f"log-{log_idx}", **kwargs)
        logs.append(log)
        log_idx += 1
        return len(logs) - 1

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
            description="Subagent thread spawned from a Task tool call",
            source=source,
            source_log_id=start_log.id,
            source_tool_name="Task",
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
                    bash_command = str(related_log.metadata.get("bashCommand") or command_text)
                    if bash_command:
                        category, label = _classify_bash_command(bash_command)
                        related_log.metadata["toolCategory"] = category
                        related_log.metadata["toolLabel"] = label
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
                msg = data.get("command") or data.get("hookName") or data.get("hookEvent") or "Hook progress"
                append_log(
                    timestamp=current_ts,
                    speaker="system",
                    type="system",
                    content=str(msg),
                    metadata={"hook": data.get("hookName", "")},
                )

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
            msg_model = message.get("model")
            if isinstance(msg_model, str) and msg_model.strip():
                current_message_model = msg_model.strip()
                if not model:
                    model = current_message_model
            usage = message.get("usage", {})
            if isinstance(usage, dict):
                message_usage_in = int(usage.get("input_tokens", 0) or 0)
                message_usage_out = int(usage.get("output_tokens", 0) or 0)
                for key in (
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                    "service_tier",
                    "inference_geo",
                ):
                    value = usage.get(key)
                    if isinstance(value, (str, int, float)) and str(value).strip():
                        message_usage_extra[key] = value
                nested_cache = usage.get("cache_creation")
                if isinstance(nested_cache, dict):
                    cache_payload = {}
                    for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
                        value = nested_cache.get(key)
                        if isinstance(value, (int, float)):
                            cache_payload[key] = int(value)
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
                    metadata={
                        "toolInputKeys": list(tool_input.keys()) if isinstance(tool_input, dict) else [],
                        "caller": str(block.get("caller") or "").strip(),
                        "signature": str(block.get("signature") or "").strip(),
                    },
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
                if tool_name == "Task" and isinstance(tool_input, dict):
                    sub_type = tool_input.get("subagent_type")
                    title = str(sub_type) if isinstance(sub_type, str) and sub_type else "Task subagent"
                    add_artifact(
                        kind="agent",
                        title=title,
                        description="Task tool invocation that may spawn a subagent",
                        source="tool",
                        source_log_id=tool_log.id,
                        source_tool_name=tool_name,
                    )
                    task_name = str(tool_input.get("name") or "").strip()
                    if task_name:
                        task_id_match = _TASK_ID_PATTERN.search(task_name)
                        if task_id_match:
                            task_id = task_id_match.group(1)
                            tool_log.metadata["taskId"] = task_id
                            add_artifact(
                                kind="task",
                                title=task_id,
                                description=task_name[:500],
                                source="tool",
                                source_log_id=tool_log.id,
                                source_tool_name=tool_name,
                            )
                        tool_log.metadata["taskName"] = task_name[:240]
                    if isinstance(sub_type, str) and sub_type.strip():
                        tool_log.metadata["taskSubagentType"] = sub_type.strip()

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
                        tool_name == "Task"
                        and isinstance(related_id, str)
                        and launch_agent_id
                        and (launch_status == "async_launched" or "agentid:" in output_text.lower())
                    ):
                        link_subagent_to_task_call(related_id, launch_agent_id, current_ts, "tool-result")
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
                        related_log.metadata["bashResult"] = _classify_bash_result(output_text, is_error)
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

    if not thinking_level and int(thinking_meta.get("maxThinkingTokens") or 0) > 0:
        thinking_level = _thinking_level_from_tokens(int(thinking_meta.get("maxThinkingTokens") or 0), forensics_schema)

    if not thinking_level and bool(thinking_meta.get("disabled", False)):
        default_disabled = str(
            forensics_schema.get("thinking", {}).get("defaults", {}).get("disabled_level", "low")
        ).strip().lower()
        thinking_level = _normalize_thinking_level(default_disabled) or "low"

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
            "messageTypeCounts": dict(session_context.get("messageTypeCounts", Counter())),
            "contentBlockTypeCounts": dict(session_context.get("contentBlockTypeCounts", Counter())),
            "contentBlockKeyCounts": dict(session_context.get("contentBlockKeyCounts", Counter())),
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
        },
        "sidecars": {
            "todos": todo_sidecar,
            "tasks": task_sidecar,
            "teams": team_sidecar,
            "sessionEnv": session_env_sidecar,
        },
    }

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
