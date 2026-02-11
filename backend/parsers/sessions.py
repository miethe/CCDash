"""Parse JSONL session log files into AgentSession models."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime

from backend.models import (
    AgentSession, SessionLog, ToolCallInfo, ToolUsage,
    SessionFileUpdate, ImpactPoint,
)


def _make_id(path: Path) -> str:
    """Derive a short session ID from the filename (UUID)."""
    stem = path.stem  # e.g. ff9e2c59-3b21-4291-b483-7f5f6303ecf5
    short = stem[:8]
    return f"S-{short}"


def _parse_timestamp(ts: str | None) -> str:
    """Normalize a timestamp to ISO format, return empty string if None."""
    if not ts:
        return ""
    return ts


def _estimate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Rough cost estimate based on model pricing."""
    # Approximate per-million-token rates
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
    in_rate, out_rate = 3.0, 15.0  # default sonnet pricing
    for key, (ir, outr) in rates.items():
        if key in model_lower:
            in_rate, out_rate = ir, outr
            break
    return (tokens_in / 1_000_000 * in_rate) + (tokens_out / 1_000_000 * out_rate)


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
    model = ""
    git_branch = ""
    git_author = ""
    git_commit = ""
    tokens_in = 0
    tokens_out = 0
    first_ts = ""
    last_ts = ""
    logs: list[SessionLog] = []
    tool_counter: Counter[str] = Counter()
    tool_success: Counter[str] = Counter()
    tool_total: Counter[str] = Counter()
    file_changes: dict[str, SessionFileUpdate] = {}
    impacts: list[ImpactPoint] = []
    log_idx = 0

    for entry in entries:
        entry_type = entry.get("type", "")
        ts = entry.get("timestamp", "")
        if ts and not first_ts:
            first_ts = ts
        if ts:
            last_ts = ts

        # Extract git info from initial snapshot
        if entry_type == "file-history-snapshot":
            git_branch = entry.get("gitBranch", git_branch)
            continue

        # Extract session metadata
        if "sessionId" in entry and not git_branch:
            git_branch = entry.get("gitBranch", "")

        # Process messages
        if entry_type in ("user", "assistant"):
            message = entry.get("message", {})
            if isinstance(message, str):
                content = message
                speaker = entry_type
                agent_name = None
            else:
                content_blocks = message.get("content", [])
                if isinstance(content_blocks, str):
                    content = content_blocks
                elif isinstance(content_blocks, list):
                    text_parts = []
                    tool_calls = []
                    for block in content_blocks:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                tool_calls.append(block)
                            elif block.get("type") == "tool_result":
                                # tool result feedback
                                result_content = block.get("content", "")
                                if isinstance(result_content, list):
                                    result_content = " ".join(
                                        r.get("text", "") for r in result_content if isinstance(r, dict)
                                    )
                                text_parts.append(f"[Tool result: {result_content[:200]}]")
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "\n".join(text_parts) if text_parts else ""

                    # Create tool log entries
                    for tc in tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_input = tc.get("input", {})
                        tool_counter[tool_name] += 1
                        tool_total[tool_name] += 1
                        tool_success[tool_name] += 1  # assume success unless we see an error

                        tool_log = SessionLog(
                            id=f"log-{log_idx}",
                            timestamp=ts,
                            speaker="agent",
                            type="tool",
                            content=f"Called {tool_name}",
                            agentName=entry.get("agentName"),
                            toolCall=ToolCallInfo(
                                name=tool_name,
                                args=json.dumps(tool_input, indent=2)[:500],
                                status="success",
                            ),
                        )
                        logs.append(tool_log)
                        log_idx += 1
                else:
                    content = str(content_blocks)

                speaker = "user" if entry_type == "user" else "agent"
                agent_name = entry.get("agentName")

                # Extract model info
                if entry_type == "assistant":
                    msg_model = message.get("model", "")
                    if msg_model and not model:
                        model = msg_model
                    usage = message.get("usage", {})
                    tokens_in += usage.get("input_tokens", 0)
                    tokens_out += usage.get("output_tokens", 0)

            if content.strip():
                log_entry = SessionLog(
                    id=f"log-{log_idx}",
                    timestamp=ts,
                    speaker=speaker,
                    type="message",
                    content=content[:2000],  # truncate very long messages
                    agentName=agent_name if speaker == "agent" else None,
                )
                logs.append(log_entry)
                log_idx += 1

        # Track progress events
        elif entry_type == "progress":
            label = entry.get("message", "Progress event")
            impacts.append(ImpactPoint(
                timestamp=ts,
                label=label[:200],
                type="info",
            ))

    # Calculate duration
    duration = 0
    if first_ts and last_ts:
        try:
            t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration = max(0, int((t2 - t1).total_seconds()))
        except (ValueError, TypeError):
            duration = 0

    # Build tool usage summary
    tools_used = []
    for name, count in tool_counter.most_common():
        total = tool_total.get(name, count)
        success = tool_success.get(name, count)
        rate = success / total if total > 0 else 1.0
        tools_used.append(ToolUsage(name=name, count=count, successRate=round(rate, 2)))

    cost = _estimate_cost(tokens_in, tokens_out, model)

    return AgentSession(
        id=session_id,
        taskId="",
        status="completed",
        model=model,
        durationSeconds=duration,
        tokensIn=tokens_in,
        tokensOut=tokens_out,
        totalCost=round(cost, 4),
        startedAt=first_ts,
        gitBranch=git_branch or None,
        gitAuthor=git_author or None,
        gitCommitHash=git_commit or None,
        updatedFiles=list(file_changes.values()),
        toolsUsed=tools_used,
        impactHistory=impacts,
        logs=logs,
    )


def scan_sessions(sessions_dir: Path) -> list[AgentSession]:
    """Scan a directory for JSONL session files and parse them all."""
    sessions = []
    if not sessions_dir.exists():
        return sessions

    for path in sorted(sessions_dir.glob("*.jsonl")):
        session = parse_session_file(path)
        if session:
            sessions.append(session)

    return sessions
