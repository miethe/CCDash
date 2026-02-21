"""Parse JSONL session log files into AgentSession models."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.models import (
    AgentSession,
    ImpactPoint,
    SessionArtifact,
    SessionFileUpdate,
    SessionLog,
    ToolCallInfo,
    ToolUsage,
)
from backend.date_utils import file_metadata_dates, make_date_value

_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_COMMAND_NAME_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_COMMIT_BRACKET_PATTERN = re.compile(r"\[[^\]\n]*\s([0-9a-f]{7,40})\]", re.IGNORECASE)
_COMMIT_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
_REQ_ID_PATTERN = re.compile(r"\bREQ-\d{8}-[A-Za-z0-9-]+-\d+\b")
_VERSION_SUFFIX_PATTERN = re.compile(r"-v\d+(?:\.\d+)?$", re.IGNORECASE)
_PLACEHOLDER_PATH_PATTERN = re.compile(r"(\*|\$\{[^}]+\}|<[^>]+>|\{[^{}]+\})")
_ASYNC_TASK_AGENT_ID_PATTERN = re.compile(r"\bagentid\s*:\s*([A-Za-z0-9_-]+)\b", re.IGNORECASE)
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


def _parse_task_notification(raw_text: str) -> dict[str, str]:
    details: dict[str, str] = {}
    if not raw_text:
        return details
    for key in ("task-id", "status", "summary"):
        match = re.search(rf"<{key}>\s*([\s\S]*?)\s*</{key}>", raw_text, re.IGNORECASE)
        if match and match.group(1).strip():
            details[key] = match.group(1).strip()
    return details


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
    is_subagent = path.parent.name == "subagents"
    session_type = "subagent" if is_subagent else "session"

    parent_session_id = ""
    if is_subagent:
        parent_session_id = _normalize_session_id(path.parent.parent.name)

    root_session_id = parent_session_id or session_id
    agent_id: str | None = None
    if is_subagent and path.stem.startswith("agent-"):
        agent_id = path.stem.split("agent-", 1)[-1]

    task_id = ""
    model = ""
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
    impacts: list[ImpactPoint] = []

    file_changes: list[SessionFileUpdate] = []
    artifacts: dict[str, SessionArtifact] = {}

    tool_logs_by_id: dict[str, int] = {}
    subagent_link_by_parent_tool: dict[str, str] = {}
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
    ) -> None:
        if not title:
            return
        artifact_id = _hash_artifact_id(session_id, kind, title, source_log_id)
        if artifact_id in artifacts:
            return
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

    def add_command_artifacts_from_text(text: str, source_log_id: str) -> None:
        command_names = [m.group(1).strip() for m in _COMMAND_NAME_PATTERN.finditer(text) if m.group(1).strip()]
        command_args = [m.group(1).strip() for m in _COMMAND_ARGS_PATTERN.finditer(text)]

        for idx, command_name in enumerate(command_names):
            args_text = command_args[idx] if idx < len(command_args) else ""
            metadata = {"origin": "command-tag"}
            if args_text:
                metadata["args"] = args_text[:4000]
            parsed = _parse_command_context(command_name, args_text)
            if parsed:
                metadata["parsedCommand"] = parsed

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

            command_log_id = logs[command_log_idx].id
            if parsed.get("featurePath"):
                feature_path = str(parsed.get("featurePath"))
                add_artifact(
                    kind="command_path",
                    title=feature_path,
                    description=f"Path referenced by {command_name}",
                    source="command-tag",
                    source_log_id=command_log_id,
                    source_tool_name=None,
                )
            if parsed.get("featureSlug"):
                feature_slug = str(parsed.get("featureSlug"))
                add_artifact(
                    kind="feature_slug",
                    title=feature_slug,
                    description=f"Feature slug inferred from {command_name}",
                    source="command-tag",
                    source_log_id=command_log_id,
                    source_tool_name=None,
                )
            if parsed.get("phaseToken"):
                phase_token = str(parsed.get("phaseToken"))
                add_artifact(
                    kind="command_phase",
                    title=phase_token,
                    description=f"Phase token parsed from {command_name}",
                    source="command-tag",
                    source_log_id=command_log_id,
                    source_tool_name=None,
                )
            if parsed.get("requestId"):
                request_id = str(parsed.get("requestId"))
                add_artifact(
                    kind="request",
                    title=request_id,
                    description=f"Request ID referenced by {command_name}",
                    source="command-tag",
                    source_log_id=command_log_id,
                    source_tool_name=None,
                )

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

    for entry in entries:
        entry_type = entry.get("type", "")
        current_ts = entry.get("timestamp", "")
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
            idx = append_log(
                timestamp=current_ts,
                speaker="system",
                type="system",
                content=summary,
                metadata={"eventType": "queue-operation", **details},
            )
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

        if isinstance(message, dict) and speaker == "agent":
            msg_model = message.get("model")
            if isinstance(msg_model, str) and msg_model.strip():
                current_message_model = msg_model.strip()
                if not model:
                    model = current_message_model
            usage = message.get("usage", {})
            if isinstance(usage, dict):
                tokens_in += int(usage.get("input_tokens", 0) or 0)
                tokens_out += int(usage.get("output_tokens", 0) or 0)

        if isinstance(message, str):
            content = message.strip()
            if content:
                idx = append_log(
                    timestamp=current_ts,
                    speaker=speaker,
                    type="message",
                    content=content[:4000],
                    agentName=agent_name,
                    metadata={"model": current_message_model} if current_message_model else {},
                )
                if speaker == "user":
                    add_command_artifacts_from_text(content, logs[idx].id)
            continue

        content_blocks = message.get("content", []) if isinstance(message, dict) else []
        if isinstance(content_blocks, str):
            content = content_blocks.strip()
            if content:
                idx = append_log(
                    timestamp=current_ts,
                    speaker=speaker,
                    type="message",
                    content=content[:4000],
                    agentName=agent_name,
                    metadata={"model": current_message_model} if current_message_model else {},
                )
                if speaker == "user":
                    add_command_artifacts_from_text(content, logs[idx].id)
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
                    metadata={"toolInputKeys": list(tool_input.keys()) if isinstance(tool_input, dict) else []},
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
                        add_artifact(
                            kind="skill",
                            title=skill_name,
                            description="Skill invocation in transcript",
                            source="tool",
                            source_log_id=tool_log.id,
                            source_tool_name=tool_name,
                        )
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
                    if related_log.toolCall:
                        related_log.toolCall.output = output_text[:20000]
                        related_log.toolCall.status = "error" if is_error else "success"
                        related_log.toolCall.isError = is_error
                    related_log.relatedToolCallId = related_id
                    if is_error and related_log.toolCall:
                        tool_success[related_log.toolCall.name] -= 1

                    tool_name = related_log.toolCall.name if related_log.toolCall else None
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
            idx = append_log(
                timestamp=current_ts,
                speaker=speaker,
                type="message",
                content=message_text[:8000],
                agentName=agent_name,
                metadata={"model": current_message_model} if current_message_model else {},
            )
            if speaker == "user":
                add_command_artifacts_from_text(message_text, logs[idx].id)

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
        tools_used.append(ToolUsage(name=name, count=count, successRate=round(rate, 2)))

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

    return AgentSession(
        id=session_id,
        taskId=task_id,
        status=session_status,
        model=model,
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
