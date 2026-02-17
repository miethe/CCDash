"""Parse JSONL session log files into AgentSession models."""
from __future__ import annotations

import hashlib
import json
import re
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

_PATH_PATTERN = re.compile(r"(?:/[^\s\"'<>]+|\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b)")
_COMMAND_NAME_PATTERN = re.compile(r"<command-name>\s*([^<\n]+)\s*</command-name>", re.IGNORECASE)
_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>\s*([\s\S]*?)\s*</command-args>", re.IGNORECASE)
_COMMIT_BRACKET_PATTERN = re.compile(r"\[[^\]\n]*\s([0-9a-f]{7,40})\]", re.IGNORECASE)
_COMMIT_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)

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

            append_log(
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
                    linked_session = _normalize_session_id(f"agent-{subagent_agent_id}")
                    subagent_link_by_parent_tool[parent_tool_call_id] = linked_session

                    tool_log_idx = tool_logs_by_id.get(parent_tool_call_id)
                    if tool_log_idx is not None:
                        logs[tool_log_idx].linkedSessionId = linked_session
                        logs[tool_log_idx].metadata["subagentAgentId"] = subagent_agent_id

                    emit_key = (parent_tool_call_id, linked_session)
                    if emit_key not in emitted_subagent_starts:
                        emitted_subagent_starts.add(emit_key)
                        start_idx = append_log(
                            timestamp=current_ts,
                            speaker="system",
                            type="subagent_start",
                            content=f"Subagent started: {subagent_agent_id}",
                            linkedSessionId=linked_session,
                            relatedToolCallId=parent_tool_call_id,
                            metadata={"agentId": subagent_agent_id},
                        )
                        start_log = logs[start_idx]
                        add_artifact(
                            kind="agent",
                            title=f"agent-{subagent_agent_id}",
                            description="Subagent thread spawned from a Task tool call",
                            source="agent-progress",
                            source_log_id=start_log.id,
                            source_tool_name="Task",
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

        if entry_type not in ("user", "assistant"):
            continue

        message = entry.get("message", {})
        message_role = entry_type
        if isinstance(message, dict) and isinstance(message.get("role"), str):
            message_role = message.get("role")

        speaker = "agent" if message_role == "assistant" else "user"
        agent_name = entry.get("agentName") if speaker == "agent" else None

        if isinstance(message, dict) and speaker == "agent":
            msg_model = message.get("model")
            if isinstance(msg_model, str) and msg_model and not model:
                model = msg_model
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
                    if tool_name == "Bash":
                        command_text = ""
                        if isinstance(related_log.metadata, dict):
                            raw = related_log.metadata.get("bashCommand")
                            if isinstance(raw, str):
                                command_text = raw
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

    return AgentSession(
        id=session_id,
        taskId=task_id,
        status="completed",
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
        gitBranch=git_branch or None,
        gitAuthor=git_author or None,
        gitCommitHash=primary_commit,
        gitCommitHashes=sorted_commits,
        updatedFiles=file_changes,
        linkedArtifacts=list(artifacts.values()),
        toolsUsed=tools_used,
        impactHistory=impacts,
        logs=logs,
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
