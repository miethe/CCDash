"""Helpers for deriving session-card badge metadata from session logs."""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from backend.model_identity import derive_model_identity

_MODEL_TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,}$", re.IGNORECASE)
_MODEL_COMMAND_STOPWORDS = {
    "set",
    "to",
    "use",
    "default",
    "auto",
    "list",
    "show",
    "current",
    "switch",
    "model",
}
_TOOL_SUMMARY_LIMIT = 6


def _safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_space(value: str) -> str:
    return " ".join((value or "").strip().split())


def _add_unique(items: list[str], seen: set[str], value: str) -> None:
    normalized = _normalize_space(value)
    if not normalized:
        return
    key = normalized.lower()
    if key in seen:
        return
    seen.add(key)
    items.append(normalized)


def _command_token(command_name: str) -> str:
    normalized = _normalize_space(command_name).lower()
    if not normalized:
        return ""
    return normalized.split()[0]


def _looks_like_model_token(token: str) -> bool:
    normalized = token.strip("`'\"").strip()
    if not normalized:
        return False
    if normalized.startswith("-"):
        return False
    if normalized.lower() in _MODEL_COMMAND_STOPWORDS:
        return False
    if not _MODEL_TOKEN_PATTERN.match(normalized):
        return False
    if any(ch.isdigit() for ch in normalized):
        return True
    return "-" in normalized or "_" in normalized or normalized.lower() in {"claude", "openai", "gpt", "gemini"}


def _extract_model_from_command(command_name: str, args_text: str, parsed_command: dict[str, Any]) -> str:
    parsed_model = parsed_command.get("model")
    if isinstance(parsed_model, str) and parsed_model.strip():
        return parsed_model.strip()

    token = _command_token(command_name)
    if token not in {"/model", "model"}:
        return ""

    for raw_token in re.split(r"[\s,;]+", args_text or ""):
        if _looks_like_model_token(raw_token):
            return raw_token.strip("`'\"").strip()
    return ""


def _extract_skill_name(tool_args_raw: Any) -> str:
    payload = _safe_json(tool_args_raw)
    if not payload:
        return ""
    candidate = payload.get("skill") or payload.get("name")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def derive_session_badges(
    logs: list[dict[str, Any]],
    primary_model: str = "",
    session_agent_id: str | None = None,
) -> dict[str, Any]:
    """Derive model/agent/skill/tool badge metadata from DB log rows."""
    models_raw: list[str] = []
    models_seen: set[str] = set()
    agents: list[str] = []
    agents_seen: set[str] = set()
    skills: list[str] = []
    skills_seen: set[str] = set()
    tool_counter: Counter[str] = Counter()

    _add_unique(models_raw, models_seen, primary_model)
    if isinstance(session_agent_id, str):
        _add_unique(agents, agents_seen, session_agent_id)

    for log in logs:
        metadata = _safe_json(log.get("metadata_json") or log.get("metadata"))
        log_type = str(log.get("type") or "").strip().lower()

        agent_name = str(log.get("agent_name") or log.get("agentName") or "").strip()
        if agent_name:
            _add_unique(agents, agents_seen, agent_name)

        if isinstance(metadata.get("agentId"), str):
            _add_unique(agents, agents_seen, str(metadata.get("agentId")))
        if isinstance(metadata.get("subagentAgentId"), str):
            _add_unique(agents, agents_seen, str(metadata.get("subagentAgentId")))

        metadata_model = metadata.get("model")
        if isinstance(metadata_model, str) and metadata_model.strip():
            _add_unique(models_raw, models_seen, metadata_model)

        if log_type == "command":
            command_name = str(log.get("content") or "").strip()
            command_args = str(metadata.get("args") or "")
            parsed_command = metadata.get("parsedCommand")
            parsed = parsed_command if isinstance(parsed_command, dict) else {}
            command_model = _extract_model_from_command(command_name, command_args, parsed)
            if command_model:
                _add_unique(models_raw, models_seen, command_model)

        if log_type == "tool":
            tool_name = _normalize_space(str(log.get("tool_name") or ""))
            if not tool_name:
                tc = log.get("toolCall")
                if isinstance(tc, dict):
                    tool_name = _normalize_space(str(tc.get("name") or ""))
            if tool_name:
                tool_counter[tool_name] += 1
            if tool_name.lower() == "skill":
                skill_name = _extract_skill_name(log.get("tool_args"))
                if not skill_name and isinstance(log.get("toolCall"), dict):
                    skill_name = _extract_skill_name(log["toolCall"].get("args"))
                if skill_name:
                    _add_unique(skills, skills_seen, skill_name)

    models_used: list[dict[str, str]] = []
    for raw in models_raw:
        identity = derive_model_identity(raw)
        models_used.append({
            "raw": raw,
            "modelDisplayName": identity["modelDisplayName"],
            "modelProvider": identity["modelProvider"],
            "modelFamily": identity["modelFamily"],
            "modelVersion": identity["modelVersion"],
        })

    tool_summary = [
        f"{name} x{count}"
        for name, count in sorted(tool_counter.items(), key=lambda item: (-item[1], item[0].lower()))[:_TOOL_SUMMARY_LIMIT]
    ]

    return {
        "modelsUsed": models_used,
        "agentsUsed": agents,
        "skillsUsed": skills,
        "toolSummary": tool_summary,
    }
