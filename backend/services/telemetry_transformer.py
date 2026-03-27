"""Telemetry payload normalization and anonymization guards."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend import config
from backend.model_identity import model_family_name
from backend.models import ExecutionOutcomePayload

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UNIX_PATH_PATTERN = re.compile(r"^/")
_WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:\\")
_HOSTNAME_PATTERN = re.compile(
    r"^(?:localhost|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}|[A-Za-z0-9-]+\.local)(?::\d{1,5})?$",
    re.IGNORECASE,
)
_STACK_TRACE_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r'File ".*", line \d+', re.IGNORECASE),
    re.compile(r"\bat\s+[A-Za-z0-9_$./<>:-]+\s+\(", re.IGNORECASE),
]
_SENSITIVE_FIELD_TOKENS = {"password", "token", "secret", "key", "credential", "auth"}
_USERNAME_FIELD_TOKENS = {"user", "username", "owner", "author", "login"}
_ALLOWED_FIELD_NAMES = {
    "token_input",
    "token_output",
    "token_cache_read",
    "token_cache_write",
}
_STATUS_ERROR_PATTERN = re.compile(r"\b(error|failed|failure|exception)\b", re.IGNORECASE)


class AnonymizationError(ValueError):
    """Raised when telemetry payloads appear to contain sensitive content."""


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_present(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return None


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = _normalize_string(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _tool_counts(row: dict[str, Any], metadata: dict[str, Any]) -> tuple[int, int | None]:
    explicit_count = _first_present(metadata, "tool_call_count", "toolCallCount")
    explicit_success = _first_present(metadata, "tool_call_success_count", "toolCallSuccessCount")
    if explicit_count is not None:
        count = _safe_int(explicit_count)
        success = _safe_int(explicit_success) if explicit_success is not None else None
        return count, success

    tools = _safe_list(_first_present(row, "toolsUsed", "tools_used"))
    if tools:
        count = sum(_safe_int(tool.get("count")) for tool in tools if isinstance(tool, dict))
        success_values = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            if "successCount" in tool:
                success_values.append(_safe_int(tool.get("successCount")))
        success = sum(success_values) if success_values else None
        return count, success

    forensics = _safe_dict(_first_present(row, "sessionForensics", "session_forensics_json"))
    usage_summary = _safe_dict(forensics.get("usageSummary"))
    count = _safe_int(
        _first_present(usage_summary, "toolCallCount", "tool_call_count"),
        default=0,
    )
    success = _first_present(usage_summary, "toolCallSuccessCount", "tool_call_success_count")
    return count, _safe_int(success) if success is not None else None


def _message_count(row: dict[str, Any], metadata: dict[str, Any]) -> int:
    explicit = _first_present(metadata, "message_count", "messageCount")
    if explicit is not None:
        return _safe_int(explicit)
    stored = _first_present(row, "message_count", "messageCount")
    if stored is not None:
        return _safe_int(stored)
    logs = _safe_list(row.get("logs"))
    if logs:
        return len(logs)
    forensics = _safe_dict(_first_present(row, "sessionForensics", "session_forensics_json"))
    sidecars = _safe_dict(forensics.get("sidecars"))
    teams = _safe_dict(sidecars.get("teams"))
    return _safe_int(_first_present(teams, "totalMessages", "messageCount"))


def _test_pass_rate(row: dict[str, Any], metadata: dict[str, Any]) -> float | None:
    explicit = _first_present(metadata, "test_pass_rate", "testPassRate")
    if explicit is not None:
        return round(max(0.0, min(1.0, _safe_float(explicit))), 4)

    forensics = _safe_dict(_first_present(row, "sessionForensics", "session_forensics_json"))
    test_execution = _safe_dict(forensics.get("testExecution"))
    result_counts = _safe_dict(test_execution.get("resultCounts"))
    passed = _safe_int(_first_present(metadata, "passed_tests", "passedTests", "passed"))
    failed = _safe_int(_first_present(metadata, "failed_tests", "failedTests", "failed"))
    if passed == 0 and failed == 0:
        passed = _safe_int(result_counts.get("passed"))
        failed = _safe_int(result_counts.get("failed"))
    total = passed + failed
    if total <= 0:
        return None
    return round(passed / total, 4)


def _derive_outcome_status(status: str) -> str:
    normalized = _normalize_string(status).lower()
    if normalized in {"interrupted", "cancelled", "canceled", "stopped", "aborted"}:
        return "interrupted"
    if normalized in {"errored", "error", "failed", "failure"}:
        return "errored"
    return "completed"


class AnonymizationVerifier:
    """Validate that outbound telemetry fields are free of obvious secrets or identifiers."""

    @staticmethod
    def verify(payload: dict[str, Any] | ExecutionOutcomePayload) -> None:
        payload_dict = payload.event_dict() if isinstance(payload, ExecutionOutcomePayload) else payload
        AnonymizationVerifier._walk(payload_dict, [])

    @staticmethod
    def _walk(value: Any, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = _normalize_string(key).lower()
                if key_text not in _ALLOWED_FIELD_NAMES and any(token in key_text for token in _SENSITIVE_FIELD_TOKENS):
                    raise AnonymizationError(f"sensitive field name blocked at {'.'.join(path + [str(key)])}")
                if any(token in key_text for token in _USERNAME_FIELD_TOKENS):
                    raise AnonymizationError(f"username field blocked at {'.'.join(path + [str(key)])}")
                AnonymizationVerifier._walk(item, path + [str(key)])
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                AnonymizationVerifier._walk(item, path + [str(index)])
            return
        if not isinstance(value, str):
            return

        text = value.strip()
        if not text:
            return
        if _EMAIL_PATTERN.search(text):
            raise AnonymizationError(f"email-like content blocked at {'.'.join(path)}")
        if _UNIX_PATH_PATTERN.match(text) or _WINDOWS_PATH_PATTERN.match(text):
            raise AnonymizationError(f"absolute path blocked at {'.'.join(path)}")
        if _HOSTNAME_PATTERN.match(text):
            raise AnonymizationError(f"hostname blocked at {'.'.join(path)}")
        if any(pattern.search(text) for pattern in _STACK_TRACE_PATTERNS):
            raise AnonymizationError(f"stack trace blocked at {'.'.join(path)}")
        if ".".join(path).endswith("last_error") and _STATUS_ERROR_PATTERN.search(text):
            raise AnonymizationError(f"raw error text blocked at {'.'.join(path)}")


class TelemetryTransformer:
    """Build export-safe SAM telemetry payloads from session records."""

    def transform_session(
        self,
        session_row: dict[str, Any],
        analytics_metadata: dict[str, Any] | None = None,
    ) -> ExecutionOutcomePayload:
        row = session_row if isinstance(session_row, dict) else {}
        metadata = analytics_metadata if isinstance(analytics_metadata, dict) else {}

        session_id = _normalize_string(_first_present(row, "id", "session_id", "sessionId"))
        project_slug = _normalize_string(_first_present(metadata, "project_slug", "projectSlug"))
        if not project_slug:
            project_slug = _normalize_string(_first_present(row, "project_slug", "project_id", "projectId"))
        model = _normalize_string(_first_present(row, "model", "model_id", "modelId"))
        tool_call_count, tool_call_success_count = _tool_counts(row, metadata)
        timestamp = (
            _timestamp(_first_present(metadata, "timestamp"))
            or _timestamp(_first_present(row, "ended_at", "endedAt", "updated_at", "updatedAt", "created_at", "createdAt"))
            or datetime.now(timezone.utc)
        )
        workflow_type = _first_present(metadata, "workflow_type", "workflowType")
        if workflow_type in (None, ""):
            workflow_type = _first_present(row, "workflow_type", "sessionType", "session_type")
        context_utilization_peak = _first_present(
            metadata, "context_utilization_peak", "contextUtilizationPeak"
        )
        if context_utilization_peak in (None, ""):
            context_utilization_peak = _first_present(row, "context_utilization_pct", "contextUtilizationPct")
        feature_slug = _first_present(metadata, "feature_slug", "featureSlug")
        if feature_slug in (None, ""):
            feature_slug = _first_present(row, "feature_slug", "featureSlug")
        cost_usd = _first_present(metadata, "cost_usd", "costUsd")
        if cost_usd in (None, ""):
            cost_usd = _first_present(
                row,
                "display_cost_usd",
                "reported_cost_usd",
                "recalculated_cost_usd",
                "total_cost",
                "totalCost",
            )

        payload = ExecutionOutcomePayload(
            event_id=_first_present(metadata, "event_id", "eventId") or str(uuid4()),
            project_slug=project_slug or "unknown-project",
            session_id=session_id,
            workflow_type=workflow_type,
            model_family=model_family_name(model),
            token_input=_safe_int(_first_present(row, "tokens_in", "tokensIn")),
            token_output=_safe_int(_first_present(row, "tokens_out", "tokensOut")),
            token_cache_read=_safe_int(
                _first_present(row, "cache_read_input_tokens", "cacheReadInputTokens"),
                default=0,
            ),
            token_cache_write=_safe_int(
                _first_present(row, "cache_creation_input_tokens", "cacheCreationInputTokens"),
                default=0,
            ),
            cost_usd=round(_safe_float(cost_usd), 4),
            tool_call_count=tool_call_count,
            tool_call_success_count=tool_call_success_count,
            duration_seconds=_safe_int(_first_present(row, "duration_seconds", "durationSeconds")),
            message_count=_message_count(row, metadata),
            outcome_status=_derive_outcome_status(_normalize_string(_first_present(row, "status"))),
            test_pass_rate=_test_pass_rate(row, metadata),
            context_utilization_peak=context_utilization_peak,
            feature_slug=feature_slug,
            timestamp=timestamp,
            ccdash_version=_normalize_string(
                _first_present(metadata, "ccdash_version", "ccdashVersion")
            )
            or config.CCDASH_VERSION,
        )

        AnonymizationVerifier.verify(payload)
        return payload
