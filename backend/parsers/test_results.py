"""Parse JUnit XML test reports into CCDash ingestion payloads."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


logger = logging.getLogger("ccdash.parsers.test_results")

_LINE_NUMBER_RE = re.compile(r"(?::|\bline\s+)\d+\b", re.IGNORECASE)
_MEMORY_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
_DURATION_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds)\b", re.IGNORECASE)
_PARAM_TEST_RE = re.compile(r"^(?P<base>[^\[]+)\[(?P<params>.+)\]$")


def generate_test_id(path: str, name: str, framework: str = "pytest") -> str:
    """Generate a stable 32-char test identifier."""
    raw = f"{path}::{name}::{framework}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _tag_name(tag: str) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _coerce_duration_ms(raw: str) -> int:
    if not raw:
        return 0
    try:
        return max(0, int(float(raw) * 1000))
    except Exception:
        return 0


def _split_parameterized_name(name: str) -> tuple[str, list[str]]:
    match = _PARAM_TEST_RE.match(name.strip())
    if not match:
        return name.strip(), []
    base = match.group("base").strip()
    params_raw = match.group("params").strip()
    if not params_raw:
        return base, []
    return base, [token.strip() for token in params_raw.split("-") if token.strip()]


def _framework_default_ext(framework: str) -> str:
    token = framework.strip().lower()
    if token in {"junit", "maven"}:
        return ".java"
    if token in {"xunit", "dotnet", ".net"}:
        return ".cs"
    return ".py"


def _infer_test_path(file_attr: str, classname: str, framework: str) -> str:
    file_value = (file_attr or "").strip()
    if file_value:
        return file_value.replace("\\", "/")

    class_value = (classname or "").strip()
    if not class_value:
        return f"unknown{_framework_default_ext(framework)}"

    if "/" in class_value:
        normalized = class_value.replace("\\", "/")
        if "." not in Path(normalized).name:
            return f"{normalized}{_framework_default_ext(framework)}"
        return normalized

    parts = [token for token in class_value.replace("\\", ".").split(".") if token]
    if not parts:
        return f"unknown{_framework_default_ext(framework)}"

    if parts and parts[-1][:1].isupper():
        parts = parts[:-1]
    if not parts:
        return f"unknown{_framework_default_ext(framework)}"
    return f"{'/'.join(parts)}{_framework_default_ext(framework)}"


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    text_chunks = [node.text or ""]
    for child in node:
        text_chunks.append(child.text or "")
        text_chunks.append(child.tail or "")
    return " ".join(chunk.strip() for chunk in text_chunks if chunk and chunk.strip()).strip()


def _extract_status(testcase_el: ET.Element) -> str:
    """Map JUnit testcase child nodes into canonical status."""
    failure_el: ET.Element | None = None
    error_el: ET.Element | None = None
    skipped_el: ET.Element | None = None
    system_out_el: ET.Element | None = None
    system_err_el: ET.Element | None = None

    for child in testcase_el:
        name = _tag_name(child.tag)
        if name == "failure":
            failure_el = child
        elif name == "error":
            error_el = child
        elif name == "skipped":
            skipped_el = child
        elif name == "system-out":
            system_out_el = child
        elif name == "system-err":
            system_err_el = child

    if failure_el is not None:
        message = f"{failure_el.attrib.get('message', '')} {_node_text(failure_el)}".lower()
        if "xpass" in message:
            return "xpassed"
        return "failed"
    if error_el is not None:
        return "error"
    if skipped_el is not None:
        message = f"{skipped_el.attrib.get('message', '')} {_node_text(skipped_el)}".lower()
        if "xfail" in message:
            return "xfailed"
        return "skipped"

    # Fallback for reporters that encode XPASS in stdout/stderr text.
    side_output = f"{_node_text(system_out_el)} {_node_text(system_err_el)}".lower()
    if "xpass" in side_output:
        return "xpassed"
    return "passed"


def _extract_error_message(testcase_el: ET.Element) -> str:
    for child in testcase_el:
        tag = _tag_name(child.tag)
        if tag not in {"failure", "error"}:
            continue
        message = child.attrib.get("message", "").strip()
        body = _node_text(child)
        combined = " ".join(token for token in [message, body] if token).strip()
        if combined:
            return combined[:12000]
    return ""


def _extract_error_fingerprint(message: str) -> str:
    """Normalize noisy values and return stable short fingerprint hash."""
    if not message:
        return ""
    normalized = message.strip().lower()
    if not normalized:
        return ""

    normalized = _LINE_NUMBER_RE.sub(":<line>", normalized)
    normalized = _MEMORY_ADDRESS_RE.sub("<addr>", normalized)
    normalized = _TIMESTAMP_RE.sub("<timestamp>", normalized)
    normalized = _DURATION_RE.sub("<duration>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _count_result_statuses(test_results: list[dict[str, Any]]) -> tuple[int, int, int]:
    passed = 0
    failed = 0
    skipped = 0
    for row in test_results:
        status = str(row.get("status") or "passed").strip().lower()
        if status in {"failed", "error", "xpassed"}:
            failed += 1
        elif status in {"skipped", "xfailed"}:
            skipped += 1
        else:
            passed += 1
    return passed, failed, skipped


def parse_junit_xml(xml_content: str, project_id: str, run_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse JUnit XML text and return normalized ingestion payload."""
    metadata = dict(run_metadata or {})
    now_iso = datetime.now(timezone.utc).isoformat()

    run_id = str(metadata.get("run_id") or metadata.get("runId") or "").strip()
    if not run_id:
        run_id = f"run-{hashlib.sha256(xml_content.encode('utf-8')).hexdigest()[:20]}"

    timestamp = str(metadata.get("timestamp") or metadata.get("created_at") or now_iso).strip() or now_iso
    framework = str(metadata.get("framework") or "pytest").strip() or "pytest"
    errors: list[str] = []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.warning("Malformed JUnit XML for project %s: %s", project_id, exc)
        return {
            "run": {
                "run_id": run_id,
                "project_id": project_id,
                "timestamp": timestamp,
                "git_sha": str(metadata.get("git_sha") or ""),
                "branch": str(metadata.get("branch") or ""),
                "agent_session_id": str(metadata.get("agent_session_id") or ""),
                "env_fingerprint": str(metadata.get("env_fingerprint") or ""),
                "trigger": str(metadata.get("trigger") or "local"),
                "status": "invalid",
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "skipped_tests": 0,
                "duration_ms": 0,
                "metadata": _safe_dict(metadata.get("metadata")),
            },
            "test_definitions": [],
            "test_results": [],
            "errors": [f"Malformed JUnit XML: {exc}"],
        }

    test_definitions_by_id: dict[str, dict[str, Any]] = {}
    test_results: list[dict[str, Any]] = []
    overrides = _safe_dict(metadata.get("test_overrides"))
    default_tags = [str(tag).strip() for tag in _safe_list(metadata.get("default_tags")) if str(tag).strip()]
    default_owner = str(metadata.get("owner") or "").strip()

    for testcase_el in root.iter():
        if _tag_name(testcase_el.tag) != "testcase":
            continue

        test_name = str(testcase_el.attrib.get("name") or "").strip() or "unknown_test"
        base_name, parameters = _split_parameterized_name(test_name)
        class_name = str(testcase_el.attrib.get("classname") or "").strip()
        inferred_path = _infer_test_path(str(testcase_el.attrib.get("file") or ""), class_name, framework)
        test_id = generate_test_id(inferred_path, test_name, framework=framework)

        status = _extract_status(testcase_el)
        duration_ms = _coerce_duration_ms(str(testcase_el.attrib.get("time") or "0"))
        error_message = _extract_error_message(testcase_el)
        error_fingerprint = (
            _extract_error_fingerprint(error_message)
            if status in {"failed", "error", "xpassed"} and error_message
            else ""
        )

        override = _safe_dict(overrides.get(test_id) or overrides.get(test_name))
        tags = [str(tag).strip() for tag in _safe_list(override.get("tags", default_tags)) if str(tag).strip()]
        owner = str(override.get("owner") or default_owner).strip()

        test_definitions_by_id[test_id] = {
            "test_id": test_id,
            "project_id": project_id,
            "path": inferred_path,
            "name": test_name,
            "framework": framework,
            "tags": tags,
            "owner": owner,
            "base_name": base_name,
            "parameters": parameters,
        }
        test_results.append(
            {
                "run_id": run_id,
                "test_id": test_id,
                "status": status,
                "duration_ms": duration_ms,
                "error_fingerprint": error_fingerprint,
                "error_message": error_message,
                "artifact_refs": [],
                "stdout_ref": "",
                "stderr_ref": "",
                "path": inferred_path,
                "name": test_name,
                "framework": framework,
                "base_name": base_name,
                "parameters": parameters,
                "tags": tags,
                "owner": owner,
            }
        )

    passed_tests, failed_tests, skipped_tests = _count_result_statuses(test_results)
    run_status = "failed" if failed_tests > 0 else "complete"
    duration_ms = sum(int(row.get("duration_ms") or 0) for row in test_results)

    return {
        "run": {
            "run_id": run_id,
            "project_id": project_id,
            "timestamp": timestamp,
            "git_sha": str(metadata.get("git_sha") or ""),
            "branch": str(metadata.get("branch") or ""),
            "agent_session_id": str(metadata.get("agent_session_id") or ""),
            "env_fingerprint": str(metadata.get("env_fingerprint") or ""),
            "trigger": str(metadata.get("trigger") or "local"),
            "status": run_status,
            "total_tests": len(test_results),
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests,
            "duration_ms": duration_ms,
            "metadata": _safe_dict(metadata.get("metadata")),
        },
        "test_definitions": list(test_definitions_by_id.values()),
        "test_results": test_results,
        "errors": errors,
    }


def _load_sidecar(path: Path) -> tuple[dict[str, Any], str]:
    candidates = [
        Path(f"{path}.meta.json"),
        path.with_suffix(".meta.json"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse sidecar metadata for %s: %s", path, exc)
            return {}, str(candidate)
        if isinstance(payload, dict):
            return payload, str(candidate)
        return {}, str(candidate)
    return {}, ""


def parse_junit_xml_file(
    xml_path: Path, project_id: str, run_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse JUnit XML from disk and merge optional sidecar metadata."""
    metadata = dict(run_metadata or {})
    xml_content = xml_path.read_text(encoding="utf-8")

    sidecar_data, sidecar_path = _load_sidecar(xml_path)
    if sidecar_data:
        metadata.update(sidecar_data)

    if not metadata.get("run_id"):
        content_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()[:20]
        metadata["run_id"] = f"{project_id}-{content_hash}"
    if not metadata.get("timestamp"):
        metadata["timestamp"] = datetime.fromtimestamp(
            xml_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()

    parsed = parse_junit_xml(xml_content, project_id, metadata)
    parsed["source_file"] = str(xml_path)
    if sidecar_path:
        parsed["sidecar_file"] = sidecar_path
    return parsed


__all__ = [
    "generate_test_id",
    "parse_junit_xml",
    "parse_junit_xml_file",
]
