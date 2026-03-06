"""Helpers for extracting structured test run metadata from tool commands and outputs."""
from __future__ import annotations

import re
import shlex
from collections import Counter
from typing import Any

_CONTROL_OPERATOR_PATTERN = re.compile(r"\s*(?:\|\||&&|;|\|)\s*")
_PYTEST_SESSION_PATTERN = re.compile(r"=+\s*test session starts\s*=+", re.IGNORECASE)
_PYTEST_VERSION_PATTERN = re.compile(r"pytest-([0-9A-Za-z_.-]+)", re.IGNORECASE)
_PYTHON_VERSION_PATTERN = re.compile(r"Python\s+([0-9]+(?:\.[0-9]+){1,3})", re.IGNORECASE)
_PYTEST_SUMMARY_PATTERN = re.compile(
    r"=+\s*(?P<summary>[^\n]*?)\s+in\s+(?P<duration>[0-9]+(?:\.[0-9]+)?)s\s*=+",
    re.IGNORECASE,
)
_PYTEST_COUNT_TOKEN_PATTERN = re.compile(r"(?P<count>\d+)\s+(?P<label>[A-Za-z][A-Za-z _-]+)", re.IGNORECASE)
_PYTEST_FAILURE_LINE_PATTERN = re.compile(r"(?m)^(FAILED|ERROR)\s+.+$")
_PYTEST_SHORT_SUMMARY_HEADER_PATTERN = re.compile(r"(?m)^=+\s*short test summary info\s*=+\s*$", re.IGNORECASE)
_PYTEST_COLLECTED_PATTERN = re.compile(r"(?m)^\s*collected\s+(\d+)\s+items?\b")
_PYTEST_WORKERS_ITEMS_PATTERN = re.compile(r"(?m)^\s*(\d+)\s+workers\s*\[(\d+)\s+items?\]\s*$")
_PYTEST_CREATED_WORKERS_PATTERN = re.compile(r"(?m)^\s*created:\s*(\d+)\s*/\s*(\d+)\s+workers\s*$", re.IGNORECASE)
_PYTEST_ROOTDIR_PATTERN = re.compile(r"(?m)^\s*rootdir:\s*(.+)$", re.IGNORECASE)
_PYTEST_CONFIGFILE_PATTERN = re.compile(r"(?m)^\s*configfile:\s*(.+)$", re.IGNORECASE)
_PYTEST_PLUGINS_PATTERN = re.compile(r"(?m)^\s*plugins:\s*(.+)$", re.IGNORECASE)
_PYTEST_TIMEOUT_PATTERN = re.compile(r"(?m)^\s*timeout:\s*([0-9]+(?:\.[0-9]+)?)s\s*$", re.IGNORECASE)
_TAIL_CAPTURE_PATTERN = re.compile(r"\|\s*tail\s+(?:-n\s*)?-(?P<lines>\d+)\b", re.IGNORECASE)
_HEAD_CAPTURE_PATTERN = re.compile(r"\|\s*head\s+(?:-n\s*)?(?P<lines>\d+)\b", re.IGNORECASE)

_REDIRECTION_TOKEN_PATTERN = re.compile(r"^(?:\d*[<>].*|\d*>&\d+|\d*<<?\S+)$")

_FLAG_TAKES_VALUE = {
    "-k",
    "-m",
    "-n",
    "-c",
    "-o",
    "--maxfail",
    "--tb",
    "--capture",
    "--rootdir",
    "--dist",
    "--timeout",
    "--durations",
    "--junitxml",
    "--cov",
    "--cov-report",
    "--ignore",
    "--deselect",
    "--log-level",
    "--log-format",
    "--log-date-format",
    "--max-worker-restart",
    "--basetemp",
    "--import-mode",
    "--lfnf",
    "--last-failed-no-failures",
}

_STATUS_KEYS = (
    "passed",
    "failed",
    "error",
    "skipped",
    "xfailed",
    "xpassed",
    "deselected",
    "rerun",
)


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


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_jsonable(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _command_segment(command: str) -> str:
    text = _safe_text(command)
    if not text:
        return ""
    parts = _CONTROL_OPERATOR_PATTERN.split(text, maxsplit=1)
    return parts[0].strip() if parts else text


def _tokenize(command: str) -> list[str]:
    text = _safe_text(command)
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return [token for token in text.split() if token]


def _detect_framework(tokens: list[str], segment: str) -> tuple[str, int]:
    lowered_tokens = [token.lower() for token in tokens]
    lowered_segment = segment.lower()

    for idx, token in enumerate(lowered_tokens):
        if token in {"pytest", "py.test"}:
            return "pytest", idx
        if token == "vitest":
            return "vitest", idx
        if token == "jest":
            return "jest", idx
        if token == "go" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "test":
            return "go-test", idx + 1
        if token == "cargo" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "test":
            return "cargo-test", idx + 1
        if token in {"npm", "pnpm", "yarn"} and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "test":
            return f"{token}-test", idx + 1
        if token == "npx" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] in {"pytest", "vitest", "jest"}:
            framework = lowered_tokens[idx + 1]
            return framework if framework != "pytest" else "pytest", idx + 1
        if token.startswith("python") and idx + 2 < len(lowered_tokens):
            if lowered_tokens[idx + 1] == "-m" and lowered_tokens[idx + 2] in {"pytest", "py.test"}:
                return "pytest", idx + 2

    if "pytest" in lowered_segment:
        return "pytest", -1
    if "vitest" in lowered_segment:
        return "vitest", -1
    if re.search(r"\b(?:pnpm|npm|yarn)\s+test\b", lowered_segment):
        for manager in ("pnpm", "npm", "yarn"):
            if re.search(rf"\b{manager}\s+test\b", lowered_segment):
                return f"{manager}-test", -1
    if re.search(r"\bgo\s+test\b", lowered_segment):
        return "go-test", -1
    if re.search(r"\bcargo\s+test\b", lowered_segment):
        return "cargo-test", -1
    return "", -1


def _looks_like_test_target(token: str) -> bool:
    value = _safe_text(token)
    if not value:
        return False
    if value.startswith("-"):
        return False
    if _REDIRECTION_TOKEN_PATTERN.match(value):
        return False
    lowered = value.lower()
    if "::" in value:
        return True
    if lowered.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs")):
        return True
    if "/" in value and ("test" in lowered or "spec" in lowered):
        return True
    if lowered.startswith("tests") or lowered.startswith("test"):
        return True
    if "[" in value and "]" in value and "test" in lowered:
        return True
    return False


def _collect_flags_and_targets(tokens: list[str], start_index: int) -> tuple[list[str], dict[str, str], list[str]]:
    if not tokens:
        return [], {}, []
    begin = start_index + 1 if start_index >= 0 else 0
    if begin >= len(tokens):
        return [], {}, []

    flags: list[str] = []
    flag_values: dict[str, str] = {}
    targets: list[str] = []

    idx = begin
    while idx < len(tokens):
        token = tokens[idx]
        lowered = token.lower()
        if lowered in {"|", "||", "&&", ";"}:
            break
        if _REDIRECTION_TOKEN_PATTERN.match(token):
            idx += 1
            continue

        if token.startswith("-"):
            flags.append(token)
            if token.startswith("--") and "=" in token:
                key, _, value = token.partition("=")
                if key.strip() and value.strip():
                    flag_values[key.strip()] = value.strip()
                idx += 1
                continue
            if lowered in _FLAG_TAKES_VALUE and idx + 1 < len(tokens):
                next_token = tokens[idx + 1]
                if not next_token.startswith("-") and not _REDIRECTION_TOKEN_PATTERN.match(next_token):
                    flag_values[token] = next_token
                    idx += 2
                    continue
            idx += 1
            continue

        if _looks_like_test_target(token):
            targets.append(token)
        idx += 1

    unique_flags = list(dict.fromkeys(flags))
    unique_targets = list(dict.fromkeys(targets))
    return unique_flags, flag_values, unique_targets


def infer_test_domains(targets: list[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for raw_target in targets:
        target = _safe_text(raw_target)
        if not target:
            continue
        base = target.split("::", 1)[0].strip().strip("\"'`")
        base = base.lstrip("./")
        parts = [part for part in base.split("/") if part and part not in {".", ".."}]
        if not parts:
            continue

        candidate = ""
        if "tests" in parts:
            idx = parts.index("tests")
            if idx + 1 < len(parts):
                after = parts[idx + 1]
                if "." not in after and not after.startswith("test"):
                    candidate = after
                elif idx > 0:
                    candidate = parts[idx - 1]
            elif idx > 0:
                candidate = parts[idx - 1]
        elif parts[0] in {"tests", "test"} and len(parts) > 1:
            candidate = parts[1]
        elif len(parts) > 1:
            candidate = parts[0]

        normalized = _safe_text(candidate).lower().strip("._-")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        domains.append(normalized)
    return domains


def _parse_capture_hint(command: str) -> dict[str, Any]:
    text = _safe_text(command)
    if not text:
        return {}

    tail = _TAIL_CAPTURE_PATTERN.search(text)
    if tail:
        return {
            "kind": "tail",
            "lines": _coerce_int(tail.group("lines"), 0),
        }

    head = _HEAD_CAPTURE_PATTERN.search(text)
    if head:
        return {
            "kind": "head",
            "lines": _coerce_int(head.group("lines"), 0),
        }

    return {}


def parse_test_run_from_command(
    command: str,
    *,
    description: Any = None,
    timeout: Any = None,
) -> dict[str, Any] | None:
    raw_command = _safe_text(command)
    if not raw_command:
        return None

    segment = _command_segment(raw_command)
    tokens = _tokenize(segment)
    framework, framework_index = _detect_framework(tokens, segment)
    if not framework:
        return None

    flags, flag_values, targets = _collect_flags_and_targets(tokens, framework_index)
    domains = infer_test_domains(targets)
    capture_hint = _parse_capture_hint(raw_command)

    payload: dict[str, Any] = {
        "framework": framework,
        "command": raw_command[:4000],
        "commandSegment": segment[:2000],
        "description": _safe_jsonable(description)[:500],
        "flags": flags[:80],
        "flagValues": {key: value[:200] for key, value in flag_values.items()},
        "targets": targets[:120],
        "targetCount": len(targets),
        "domains": domains[:20],
        "primaryDomain": domains[0] if domains else "",
        "timeoutMs": _coerce_int(timeout, 0),
        "capturedOutput": capture_hint,
    }
    return payload


def _normalize_status_key(label: str) -> str:
    normalized = _safe_text(label).lower().replace("-", " ").replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    mapping = {
        "pass": "passed",
        "passed": "passed",
        "fail": "failed",
        "failed": "failed",
        "failure": "failed",
        "failures": "failed",
        "error": "error",
        "errors": "error",
        "skip": "skipped",
        "skipped": "skipped",
        "xfailed": "xfailed",
        "xfail": "xfailed",
        "xpassed": "xpassed",
        "xpass": "xpassed",
        "deselected": "deselected",
        "rerun": "rerun",
        "reruns": "rerun",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


def _parse_pytest_output(output_text: str) -> dict[str, Any]:
    text = _safe_text(output_text)
    counts: Counter[str] = Counter()
    duration_seconds = 0.0
    summary_line = ""

    summary_matches = list(_PYTEST_SUMMARY_PATTERN.finditer(text))
    if summary_matches:
        last = summary_matches[-1]
        summary_line = _safe_text(last.group("summary"))
        duration_seconds = _coerce_float(last.group("duration"), 0.0)
        for token in _PYTEST_COUNT_TOKEN_PATTERN.finditer(summary_line):
            key = _normalize_status_key(token.group("label"))
            if key:
                counts[key] += _coerce_int(token.group("count"), 0)
    else:
        # Fallback for truncated pytest output (for example tail/head pipelines)
        # where the session header is missing but failure lines are still present.
        for match in _PYTEST_FAILURE_LINE_PATTERN.finditer(text):
            label = _safe_text(match.group(1)).upper()
            if label == "FAILED":
                counts["failed"] += 1
            elif label == "ERROR":
                counts["error"] += 1

    collected = 0
    workers = 0

    collected_match = _PYTEST_COLLECTED_PATTERN.search(text)
    if collected_match:
        collected = _coerce_int(collected_match.group(1), 0)

    worker_items_match = _PYTEST_WORKERS_ITEMS_PATTERN.search(text)
    if worker_items_match:
        workers = _coerce_int(worker_items_match.group(1), 0)
        if collected <= 0:
            collected = _coerce_int(worker_items_match.group(2), 0)

    created_workers_match = _PYTEST_CREATED_WORKERS_PATTERN.search(text)
    if created_workers_match and workers <= 0:
        workers = _coerce_int(created_workers_match.group(2), 0)

    rootdir_match = _PYTEST_ROOTDIR_PATTERN.search(text)
    configfile_match = _PYTEST_CONFIGFILE_PATTERN.search(text)
    plugins_match = _PYTEST_PLUGINS_PATTERN.search(text)
    timeout_match = _PYTEST_TIMEOUT_PATTERN.search(text)
    pytest_version_match = _PYTEST_VERSION_PATTERN.search(text)
    python_version_match = _PYTHON_VERSION_PATTERN.search(text)

    plugins: list[str] = []
    if plugins_match:
        plugins = [item.strip() for item in plugins_match.group(1).split(",") if item.strip()]

    tracked_counts = {key: _coerce_int(counts.get(key), 0) for key in _STATUS_KEYS}

    total = collected
    if total <= 0:
        total = sum(tracked_counts.values())

    failed_like = tracked_counts.get("failed", 0) + tracked_counts.get("error", 0) + tracked_counts.get("xpassed", 0)
    status = "failed" if failed_like > 0 else ("passed" if total > 0 else "unknown")
    pass_rate = round((_coerce_float(tracked_counts.get("passed", 0)) / total), 4) if total > 0 else 0.0
    has_signal = bool(
        summary_matches
        or collected > 0
        or workers > 0
        or sum(tracked_counts.values()) > 0
        or _PYTEST_SESSION_PATTERN.search(text)
        or _PYTEST_VERSION_PATTERN.search(text)
        or _PYTEST_SHORT_SUMMARY_HEADER_PATTERN.search(text)
        or _PYTEST_FAILURE_LINE_PATTERN.search(text)
    )

    return {
        "framework": "pytest",
        "status": status,
        "durationSeconds": round(duration_seconds, 3) if duration_seconds > 0 else 0.0,
        "counts": tracked_counts,
        "total": total,
        "passRate": pass_rate,
        "collected": collected,
        "workers": workers,
        "rootdir": _safe_text(rootdir_match.group(1) if rootdir_match else ""),
        "configfile": _safe_text(configfile_match.group(1) if configfile_match else ""),
        "pythonVersion": _safe_text(python_version_match.group(1) if python_version_match else ""),
        "pytestVersion": _safe_text(pytest_version_match.group(1) if pytest_version_match else ""),
        "plugins": plugins[:40],
        "timeoutSeconds": _coerce_float(timeout_match.group(1), 0.0) if timeout_match else 0.0,
        "summary": summary_line[:500],
        "hasSignal": has_signal,
    }


def parse_test_run_output(output_text: str, framework: str = "") -> dict[str, Any] | None:
    text = _safe_text(output_text)
    if not text:
        return None

    normalized_framework = _safe_text(framework).lower()
    if normalized_framework in {"", "pytest"}:
        parsed = _parse_pytest_output(text)
        has_signal = bool(parsed.pop("hasSignal", False))
        if has_signal:
            return parsed
    return None


def enrich_test_run_with_output(test_run: dict[str, Any] | None, output_text: str, *, is_error: bool = False) -> dict[str, Any] | None:
    base: dict[str, Any] = dict(test_run or {})
    framework = _safe_text(base.get("framework") or "")
    parsed_result = parse_test_run_output(output_text, framework)
    if parsed_result is None and not base:
        return None

    if parsed_result is not None:
        result = dict(parsed_result)
    else:
        result = dict(base.get("result") or {})

    if is_error and _safe_text(result.get("status")) not in {"failed", "error"}:
        result["status"] = "failed"

    if result:
        base["result"] = result

    return base if base else None


def flatten_test_run_metadata(test_run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(test_run or {})
    result = dict(payload.get("result") or {})
    counts = dict(result.get("counts") or {})

    metadata: dict[str, Any] = {
        "testRun": payload,
        "testFramework": _safe_text(payload.get("framework")),
        "testDomain": _safe_text(payload.get("primaryDomain")),
        "testDomains": payload.get("domains") if isinstance(payload.get("domains"), list) else [],
        "testTargets": payload.get("targets") if isinstance(payload.get("targets"), list) else [],
        "testFlags": payload.get("flags") if isinstance(payload.get("flags"), list) else [],
        "testTargetCount": _coerce_int(payload.get("targetCount"), 0),
        "testDescription": _safe_text(payload.get("description")),
        "testTimeoutMs": _coerce_int(payload.get("timeoutMs"), 0),
    }

    if result:
        metadata["testStatus"] = _safe_text(result.get("status"))
        metadata["testDurationSeconds"] = _coerce_float(result.get("durationSeconds"), 0.0)
        metadata["testTotal"] = _coerce_int(result.get("total"), 0)
        metadata["testPassRate"] = _coerce_float(result.get("passRate"), 0.0)
        metadata["testCounts"] = {key: _coerce_int(value, 0) for key, value in counts.items()}
        metadata["testCollected"] = _coerce_int(result.get("collected"), 0)
        metadata["testWorkers"] = _coerce_int(result.get("workers"), 0)
        metadata["testRootdir"] = _safe_text(result.get("rootdir"))
        metadata["testPytestVersion"] = _safe_text(result.get("pytestVersion"))
        metadata["testPythonVersion"] = _safe_text(result.get("pythonVersion"))

    return metadata


def aggregate_test_runs(test_runs: list[dict[str, Any]]) -> dict[str, Any]:
    framework_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()

    total_duration = 0.0
    run_rows: list[dict[str, Any]] = []

    for run in test_runs:
        if not isinstance(run, dict):
            continue
        framework = _safe_text(run.get("framework")).lower()
        if framework:
            framework_counts[framework] += 1

        domains_raw = run.get("domains") if isinstance(run.get("domains"), list) else []
        domains = []
        for value in domains_raw:
            normalized = _safe_text(value).lower()
            if normalized and normalized not in domains:
                domains.append(normalized)
                domain_counts[normalized] += 1

        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        status = _safe_text(result.get("status") or "unknown").lower() or "unknown"
        status_counts[status] += 1

        counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
        normalized_counts: dict[str, int] = {}
        for key, value in counts.items():
            status_key = _normalize_status_key(_safe_text(key))
            if not status_key:
                continue
            count_value = _coerce_int(value, 0)
            if count_value <= 0:
                continue
            result_counts[status_key] += count_value
            normalized_counts[status_key] = count_value

        duration_seconds = _coerce_float(result.get("durationSeconds"), 0.0)
        if duration_seconds > 0:
            total_duration += duration_seconds

        run_rows.append(
            {
                "framework": framework,
                "status": status,
                "domain": _safe_text(run.get("primaryDomain")).lower(),
                "primaryDomain": _safe_text(run.get("primaryDomain")).lower(),
                "domains": domains,
                "targetCount": _coerce_int(run.get("targetCount"), 0),
                "targets": list(run.get("targets") or [])[:20] if isinstance(run.get("targets"), list) else [],
                "flags": list(run.get("flags") or [])[:30] if isinstance(run.get("flags"), list) else [],
                "description": _safe_text(run.get("description"))[:300],
                "command": _safe_text(run.get("command"))[:4000],
                "commandSegment": _safe_text(run.get("commandSegment"))[:2000],
                "sourceLogId": _safe_text(run.get("sourceLogId")),
                "toolName": _safe_text(run.get("toolName")),
                "timeoutMs": _coerce_int(run.get("timeoutMs"), 0),
                "durationSeconds": round(duration_seconds, 3) if duration_seconds > 0 else 0.0,
                "counts": normalized_counts,
                "total": _coerce_int(result.get("total"), 0),
                "passRate": _coerce_float(result.get("passRate"), 0.0),
                "workers": _coerce_int(result.get("workers"), 0),
                "collected": _coerce_int(result.get("collected"), 0),
                "rootdir": _safe_text(result.get("rootdir")),
                "pytestVersion": _safe_text(result.get("pytestVersion")),
                "pythonVersion": _safe_text(result.get("pythonVersion")),
                "summary": _safe_text(result.get("summary"))[:300],
            }
        )

    totals = {key: _coerce_int(result_counts.get(key), 0) for key in _STATUS_KEYS}
    total_tests = sum(totals.values())
    pass_rate = round((_coerce_float(totals.get("passed", 0)) / total_tests), 4) if total_tests > 0 else 0.0

    return {
        "runCount": len(run_rows),
        "frameworkCounts": dict(framework_counts),
        "domainCounts": dict(domain_counts),
        "statusCounts": dict(status_counts),
        "resultCounts": totals,
        "totalTests": total_tests,
        "passRate": pass_rate,
        "totalDurationSeconds": round(total_duration, 3) if total_duration > 0 else 0.0,
        "runs": run_rows,
    }
