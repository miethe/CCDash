"""Layered redaction module for session detail egress (Phase 1 / OQ-1 resolution).

Layer 1 — Known-secret pattern scan:
    Regex patterns for API keys, bearer tokens, AWS/GCP creds, and .env-style
    ``KEY=secret`` assignments.

Layer 2 — Tool-name-aware payload field redaction:
    For tools whose arguments can carry secrets (e.g. ``Bash`` command strings,
    file-write content), specific argument/output fields are pattern-scanned and
    redacted.

Both layers are configurable via env vars:
    CCDASH_REDACTION_PATTERNS_ENABLED   (default: true)  — Layer 1
    CCDASH_REDACTION_TOOL_AWARE_ENABLED (default: true)  — Layer 2

Fail-closed: if a layer env var is absent or unrecognised the safer default
(enabled) applies. Unknown tool names fall through to Layer 1 pattern scan —
never fail-open.

Redaction-event logs record redacted field COUNT only — never payload contents.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("ccdash.redaction")

# ── Redaction placeholder ─────────────────────────────────────────────────────
REDACTED_PLACEHOLDER: str = "[REDACTED]"


# ── Env helpers (fail-closed: default=True) ───────────────────────────────────

def _redaction_env_bool(name: str, default: bool = True) -> bool:
    """Read a boolean env var. Returns ``default`` on missing/unrecognised."""
    val = os.environ.get(name, "")
    if not val:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ── Layer 1: Known-secret patterns ───────────────────────────────────────────
#
# Each entry: (label, compiled_regex)
# The regex MUST match the secret itself (not surrounding context) so the
# full match string can be replaced with REDACTED_PLACEHOLDER.

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # API key / token assignment (key=value or key: value)
    (
        "api_key_assignment",
        re.compile(
            r"(?i)(?:api[_\-]?key|apikey|api[_\-]?token|access[_\-]?token)"
            r"\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
        ),
    ),
    # Bearer token in Authorization headers
    (
        "bearer_token",
        re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-_.]{20,})"),
    ),
    # AWS Access Key ID
    (
        "aws_access_key_id",
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    ),
    # AWS Secret Access Key assignment
    (
        "aws_secret_key",
        re.compile(
            r"(?i)(?:aws[_\-]?secret[_\-]?access[_\-]?key|aws[_\-]?secret)\s*[=:]\s*"
            r"['\"]?([A-Za-z0-9/+]{40})['\"]?",
        ),
    ),
    # GCP private key block
    (
        "gcp_private_key",
        re.compile(r'"private_key"\s*:\s*"-----BEGIN[^"]{10,}"'),
    ),
    # Generic PEM private key block header
    (
        "pem_private_key_header",
        re.compile(r"-----BEGIN\s+(?:[A-Z ]+\s+)?PRIVATE\s+KEY-----"),
    ),
    # OpenAI / Anthropic "sk-" style keys
    (
        "sk_key",
        re.compile(r"\b(sk-[A-Za-z0-9\-_]{20,})\b"),
    ),
    # GitHub personal access tokens
    (
        "github_pat",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,})\b"),
    ),
    # .env-style: UPPER_KEY=value (value ≥8 non-whitespace chars)
    # Matches only when the key looks like an env var name (all-caps + digits/_)
    (
        "dotenv_assignment",
        re.compile(
            r"(?m)^([A-Z][A-Z0-9_]{3,})\s*=\s*(['\"]?)([^\s'\"]{8,})\2\s*$",
        ),
    ),
    # Generic 64-char hex string (potential secrets/hashes — conservative)
    (
        "hex_64",
        re.compile(r"\b([0-9a-f]{64})\b"),
    ),
]


def _redact_string_layer1(text: str) -> tuple[str, int]:
    """Apply Layer 1 pattern scan to a plain string.

    Returns:
        (redacted_text, redacted_match_count)
        Count is the number of *distinct patterns* that fired (≥1 match each),
        not the total number of individual match replacements.
    """
    result = text
    fired = 0
    for _label, pattern in _SECRET_PATTERNS:
        new_result = pattern.sub(REDACTED_PLACEHOLDER, result)
        if new_result != result:
            fired += 1
            result = new_result
    return result, fired


# ── Layer 2: Tool-name-aware field redaction ──────────────────────────────────

# Tool names whose *argument* fields may carry secrets
_TOOL_SENSITIVE_ARG_KEYS: dict[str, list[str]] = {
    "Bash": ["command", "cmd", "script"],
    "bash": ["command", "cmd", "script"],
    "Shell": ["command", "cmd"],
    "Write": ["content", "new_string", "old_string"],
    "Edit": ["new_string", "old_string"],
    "MultiEdit": ["edits"],
    "computer_use": ["text", "command"],
}

# Environment-variable assignment pattern inside Bash command strings
_ENV_ASSIGN_IN_CMD = re.compile(
    r"(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=\s*(['\"]?)([^\s'\"\n;]{8,})\2"
)


def _redact_tool_call(tool_call: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Apply Layer 2 tool-name-aware redaction to a ``toolCall`` dict.

    Falls back to Layer 1 pattern scan on the raw ``args`` string for unknown
    tool names (fail-closed: unknown does not mean unredacted).

    Returns:
        (redacted_tool_call, redacted_field_count)
    """
    if not tool_call:
        return tool_call, 0

    tool_name: str = str(tool_call.get("name") or "")
    result = dict(tool_call)
    count = 0

    sensitive_keys = _TOOL_SENSITIVE_ARG_KEYS.get(tool_name, [])
    args = result.get("args")

    if isinstance(args, str):
        # Layer 1 scan on the raw args string
        new_args, c = _redact_string_layer1(args)
        # Extra: env-var assignment redaction for shell-like tools
        if tool_name.lower() in {"bash", "shell"}:
            before = new_args
            new_args = _ENV_ASSIGN_IN_CMD.sub(
                lambda m: f"{m.group(1)}={REDACTED_PLACEHOLDER}", new_args
            )
            if new_args != before:
                c += 1
        if new_args != args:
            result["args"] = new_args
            count += c
    elif isinstance(args, dict):
        keys_to_scan = sensitive_keys if sensitive_keys else list(args.keys())
        new_args_dict = dict(args)
        for key in keys_to_scan:
            val = new_args_dict.get(key)
            if isinstance(val, str):
                new_val, c = _redact_string_layer1(val)
                if new_val != val:
                    new_args_dict[key] = new_val
                    count += c
        result["args"] = new_args_dict

    # Redact ``output`` field (may echo command output containing secrets)
    output = result.get("output")
    if isinstance(output, str):
        new_output, c = _redact_string_layer1(output)
        if new_output != output:
            result["output"] = new_output
            count += c

    return result, count


# ── Public API ────────────────────────────────────────────────────────────────

def redact_log_entry(
    entry: dict[str, Any],
    *,
    patterns_enabled: bool | None = None,
    tool_aware_enabled: bool | None = None,
) -> tuple[dict[str, Any], int]:
    """Redact a single log entry dict (returns a new dict, does not mutate).

    Applies:
        Layer 1 — pattern scan on ``content`` when ``patterns_enabled``.
        Layer 2 — tool-name-aware field redaction on ``toolCall`` when
                   ``tool_aware_enabled``.

    Secure defaults: both layers ON when env vars are absent.

    Args:
        entry:              The log entry dict to redact.
        patterns_enabled:   Override for Layer 1. ``None`` → read env var.
        tool_aware_enabled: Override for Layer 2. ``None`` → read env var.

    Returns:
        (redacted_entry, total_redacted_field_count)
    """
    if patterns_enabled is None:
        patterns_enabled = _redaction_env_bool("CCDASH_REDACTION_PATTERNS_ENABLED", True)
    if tool_aware_enabled is None:
        tool_aware_enabled = _redaction_env_bool("CCDASH_REDACTION_TOOL_AWARE_ENABLED", True)

    result = dict(entry)
    total_count = 0

    # Layer 1: pattern scan on ``content`` field
    if patterns_enabled:
        content = result.get("content")
        if isinstance(content, str):
            new_content, c = _redact_string_layer1(content)
            if new_content != content:
                result["content"] = new_content
                total_count += c

    # Layers 1+2 on ``toolCall``
    tool_call = result.get("toolCall")
    if isinstance(tool_call, dict):
        if tool_aware_enabled:
            new_tc, c = _redact_tool_call(tool_call)
        else:
            # Layer 2 disabled: fall back to Layer 1 on args/output only
            new_tc = dict(tool_call)
            c = 0
            if patterns_enabled:
                for field_name in ("args", "output"):
                    val = new_tc.get(field_name)
                    if isinstance(val, str):
                        new_val, fc = _redact_string_layer1(val)
                        if new_val != val:
                            new_tc[field_name] = new_val
                            c += fc
        if c > 0:
            result["toolCall"] = new_tc
            total_count += c

    return result, total_count


def redact_entries(
    entries: list[dict[str, Any]],
    *,
    patterns_enabled: bool | None = None,
    tool_aware_enabled: bool | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Redact a list of log entries.

    Returns:
        (redacted_entries, total_redacted_field_count)

    Emits a single DEBUG log with the aggregate count (never payload contents).
    """
    if patterns_enabled is None:
        patterns_enabled = _redaction_env_bool("CCDASH_REDACTION_PATTERNS_ENABLED", True)
    if tool_aware_enabled is None:
        tool_aware_enabled = _redaction_env_bool("CCDASH_REDACTION_TOOL_AWARE_ENABLED", True)

    redacted: list[dict[str, Any]] = []
    total = 0
    for entry in entries:
        new_entry, c = redact_log_entry(
            entry,
            patterns_enabled=patterns_enabled,
            tool_aware_enabled=tool_aware_enabled,
        )
        redacted.append(new_entry)
        total += c

    if total > 0:
        logger.debug(
            "redact_entries: redacted %d field(s) across %d entries "
            "(patterns=%s tool_aware=%s)",
            total,
            len(entries),
            patterns_enabled,
            tool_aware_enabled,
        )

    return redacted, total


def redact_json_payload_layer1(
    value: Any,
    *,
    patterns_enabled: bool | None = None,
) -> tuple[Any, int]:
    """Recursively apply the Layer 1 known-secret pattern scan to any JSON value.

    Unlike :func:`redact_log_entry` / :func:`redact_entries` (which target the
    session-log entry shape — ``content`` / ``toolCall`` — specifically), this
    walks an arbitrary JSON-serialisable structure (dict/list/str/scalar) and
    pattern-scans every string leaf. Intended for free-form ingest payloads
    whose shape is not a session log entry but still deserves defensive
    secret-pattern coverage (e.g. Research Foundry ``ccdash_event`` bodies —
    FR-14 of the research-foundry-run-telemetry-v1 PRD).

    Does not mutate *value*; returns a new structure.

    Args:
        value:             Any JSON-serialisable value (dict, list, str, or scalar).
        patterns_enabled:  Override for Layer 1. ``None`` → read env var
                            (fail-closed default: enabled).

    Returns:
        (redacted_value, total_redacted_match_count)
    """
    if patterns_enabled is None:
        patterns_enabled = _redaction_env_bool("CCDASH_REDACTION_PATTERNS_ENABLED", True)

    if not patterns_enabled:
        return value, 0

    total = 0

    def _walk(node: Any) -> Any:
        nonlocal total
        if isinstance(node, str):
            new_node, c = _redact_string_layer1(node)
            total += c
            return new_node
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    redacted = _walk(value)
    return redacted, total
