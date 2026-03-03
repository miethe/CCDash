"""Execution policy evaluation for local terminal runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
from typing import Literal


ExecutionPolicyVerdict = Literal["allow", "requires_approval", "deny"]
ExecutionRiskLevel = Literal["low", "medium", "high"]


_RISK_ORDER: dict[ExecutionRiskLevel, int] = {"low": 0, "medium": 1, "high": 2}
_ALLOWED_ENV_PROFILES = {"default", "minimal", "project", "ci"}
_BLOCKED_ENV_PROFILES = {"host", "inherit", "unrestricted"}

_SHELL_CONTROL_TOKENS = {"&&", "||", ";", "|"}
_BLOCKED_ROOT_COMMANDS = {"mkfs", "shutdown", "reboot", "halt", "poweroff"}
_NETWORK_COMMANDS = {"curl", "wget", "ssh", "scp", "rsync", "telnet", "nc", "ncat", "netcat"}
_READ_ONLY_ROOT_COMMANDS = {"cat", "head", "tail", "less", "ls", "pwd", "echo", "grep", "rg", "find"}
_ALLOWED_ROOT_COMMANDS = {
    *_READ_ONLY_ROOT_COMMANDS,
    "awk",
    "bash",
    "git",
    "make",
    "npm",
    "node",
    "pnpm",
    "python",
    "pytest",
    "sed",
    "sh",
    "uv",
    "yarn",
    "zsh",
}
_GIT_LOW_RISK_SUBCOMMANDS = {"status", "diff", "log", "show", "rev-parse"}
_GIT_HIGH_RISK_SUBCOMMANDS = {
    "reset",
    "clean",
    "rebase",
    "push",
    "checkout",
    "restore",
    "cherry-pick",
    "revert",
}
_DESTRUCTIVE_ROOT_COMMANDS = {"rm", "dd", "chmod", "chown", "truncate"}
_BLOCKED_PATTERNS = (
    re.compile(r":\(\)\s*\{"),  # fork bomb
    re.compile(r"\brm\s+-[^\n]*\b(?:rf|fr|r\b[^\n]*\bf)\s+/\s*$", re.IGNORECASE),
    re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE),
)


@dataclass(frozen=True)
class ExecutionPolicyResult:
    verdict: ExecutionPolicyVerdict
    risk_level: ExecutionRiskLevel
    requires_approval: bool
    normalized_command: str
    command_tokens: list[str]
    resolved_cwd: str
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class _Classification:
    risk_level: ExecutionRiskLevel = "low"
    requires_approval: bool = False
    deny: bool = False
    reason_codes: list[str] = field(default_factory=list)

    def add_reason(self, code: str) -> None:
        if code not in self.reason_codes:
            self.reason_codes.append(code)

    def escalate_risk(self, level: ExecutionRiskLevel) -> None:
        if _RISK_ORDER[level] > _RISK_ORDER[self.risk_level]:
            self.risk_level = level


def _resolve_workspace_root(workspace_root: str | Path) -> Path:
    return Path(workspace_root).expanduser().resolve(strict=False)


def _resolve_cwd(workspace_root: Path, cwd: str | Path | None) -> tuple[Path, list[str]]:
    reasons: list[str] = []
    raw = Path(cwd).expanduser() if cwd is not None and str(cwd).strip() else workspace_root
    candidate = raw if raw.is_absolute() else (workspace_root / raw)
    resolved = candidate.resolve(strict=False)

    if not resolved.exists():
        reasons.append("cwd_not_found")
        return resolved, reasons
    if not resolved.is_dir():
        reasons.append("cwd_not_directory")
        return resolved, reasons

    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        reasons.append("workspace_boundary_violation")
    return resolved, reasons


def _tokenize(command: str) -> tuple[list[str], str, list[str]]:
    if not command.strip():
        return [], "", ["empty_command"]
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return [], "", ["invalid_command_syntax"]
    if not tokens:
        return [], "", ["empty_command"]
    normalized = " ".join(shlex.quote(token) for token in tokens)
    return tokens, normalized, []


def _classify_command(command: str, tokens: list[str]) -> _Classification:
    classification = _Classification()
    lowered_command = command.strip().lower()
    lowered_tokens = [token.lower() for token in tokens]
    root = lowered_tokens[0]
    sub = lowered_tokens[1] if len(lowered_tokens) > 1 else ""

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(lowered_command):
            classification.deny = True
            classification.escalate_risk("high")
            classification.add_reason("blocked_command_pattern")
            return classification

    if root in _BLOCKED_ROOT_COMMANDS:
        classification.deny = True
        classification.escalate_risk("high")
        classification.add_reason("blocked_command_class")
        return classification

    if root == "sudo":
        classification.requires_approval = True
        classification.escalate_risk("high")
        classification.add_reason("privileged_command")

    if root in _DESTRUCTIVE_ROOT_COMMANDS:
        classification.requires_approval = True
        classification.escalate_risk("high")
        classification.add_reason("destructive_command")

    if root in _NETWORK_COMMANDS:
        classification.requires_approval = True
        classification.escalate_risk("high")
        classification.add_reason("network_command")

    if any(token in _SHELL_CONTROL_TOKENS for token in lowered_tokens):
        classification.requires_approval = True
        classification.escalate_risk("high")
        classification.add_reason("compound_shell_command")

    if root == "git":
        if sub in _GIT_HIGH_RISK_SUBCOMMANDS:
            classification.requires_approval = True
            classification.escalate_risk("high")
            classification.add_reason("destructive_command")
        elif sub in _GIT_LOW_RISK_SUBCOMMANDS:
            classification.escalate_risk("low")
            classification.add_reason("safe_read_only_command")
        else:
            classification.escalate_risk("medium")
            classification.add_reason("standard_dev_command")
        return classification

    if root in _READ_ONLY_ROOT_COMMANDS:
        classification.escalate_risk("low")
        classification.add_reason("safe_read_only_command")
        return classification

    if root in _ALLOWED_ROOT_COMMANDS:
        classification.escalate_risk("medium")
        classification.add_reason("standard_dev_command")
        return classification

    classification.requires_approval = True
    classification.escalate_risk("medium")
    classification.add_reason("unknown_command")
    return classification


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def evaluate_execution_policy(
    *,
    command: str,
    workspace_root: str | Path,
    cwd: str | Path | None = None,
    env_profile: str = "default",
) -> ExecutionPolicyResult:
    """Return allow/approval/deny verdict for a command in a workspace context."""
    workspace = _resolve_workspace_root(workspace_root)
    resolved_cwd, cwd_reasons = _resolve_cwd(workspace, cwd)

    reasons: list[str] = []
    reasons.extend(cwd_reasons)
    deny = bool(cwd_reasons)

    env_token = str(env_profile or "default").strip().lower()
    if env_token in _BLOCKED_ENV_PROFILES or env_token not in _ALLOWED_ENV_PROFILES:
        reasons.append("unsupported_env_profile")
        deny = True

    tokens, normalized_command, tokenize_reasons = _tokenize(command)
    reasons.extend(tokenize_reasons)
    if tokenize_reasons:
        deny = True

    classification = _Classification()
    if tokens:
        classification = _classify_command(command, tokens)
        reasons.extend(classification.reason_codes)
        deny = deny or classification.deny

    risk: ExecutionRiskLevel = classification.risk_level
    if deny and _RISK_ORDER[risk] < _RISK_ORDER["high"]:
        risk = "high"

    verdict: ExecutionPolicyVerdict
    if deny:
        verdict = "deny"
    elif classification.requires_approval:
        verdict = "requires_approval"
    else:
        verdict = "allow"

    return ExecutionPolicyResult(
        verdict=verdict,
        risk_level=risk,
        requires_approval=verdict == "requires_approval",
        normalized_command=normalized_command,
        command_tokens=tokens,
        resolved_cwd=str(resolved_cwd),
        reason_codes=_dedupe_preserve_order(reasons),
    )
