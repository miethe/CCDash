"""Parsers for test platform output artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from backend.models import IngestRunRequest
from backend.parsers.test_results import generate_test_id, parse_junit_xml_file


FAILED_STATUSES = {"failed", "error", "xpassed"}
SKIPPED_STATUSES = {"skipped", "xfailed"}
JEST_STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "pending": "skipped",
    "skipped": "skipped",
    "todo": "skipped",
}
PLAYWRIGHT_FAILED = {"failed", "timedOut"}
PLAYWRIGHT_SKIPPED = {"skipped", "interrupted"}


@dataclass
class ParsedTestArtifact:
    run_payload: IngestRunRequest | None
    metrics: list[dict[str, Any]]
    errors: list[str]


def _default_run_id(project_id: str, platform_id: str, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
    return f"{project_id}-{platform_id}-{digest}"


def _file_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _status_counts(test_results: list[dict[str, Any]]) -> tuple[int, int, int]:
    passed = 0
    failed = 0
    skipped = 0
    for row in test_results:
        status = str(row.get("status") or "passed").strip().lower()
        if status in FAILED_STATUSES:
            failed += 1
        elif status in SKIPPED_STATUSES:
            skipped += 1
        else:
            passed += 1
    return passed, failed, skipped


def _finalize_run_payload(
    *,
    project_id: str,
    run_id: str,
    timestamp: str,
    trigger: str,
    test_definitions: list[dict[str, Any]],
    test_results: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> IngestRunRequest:
    passed, failed, skipped = _status_counts(test_results)
    return IngestRunRequest(
        run_id=run_id,
        project_id=project_id,
        timestamp=timestamp,
        git_sha="",
        branch="",
        agent_session_id="",
        env_fingerprint="",
        trigger=trigger,
        test_definitions=test_definitions,
        test_results=test_results,
        metadata=metadata or {
            "status": "failed" if failed > 0 else "complete",
            "total_tests": len(test_results),
            "passed_tests": passed,
            "failed_tests": failed,
            "skipped_tests": skipped,
        },
    )


def _metric(
    platform_id: str,
    metric_type: str,
    metric_name: str,
    metric_value: float,
    *,
    unit: str = "",
    metadata: dict[str, Any] | None = None,
    source_file: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    return {
        "platform": platform_id,
        "metric_type": metric_type,
        "metric_name": metric_name,
        "metric_value": float(metric_value),
        "unit": unit,
        "metadata": metadata or {},
        "source_file": source_file,
        "run_id": run_id,
    }


def parse_test_artifact(platform_id: str, path: Path, project_id: str) -> ParsedTestArtifact:
    if platform_id == "pytest":
        return _parse_pytest_artifact(path=path, project_id=project_id)
    if platform_id == "jest":
        return _parse_jest_artifact(path=path, project_id=project_id)
    if platform_id == "playwright":
        return _parse_playwright_artifact(path=path, project_id=project_id)
    if platform_id == "coverage":
        return _parse_coverage_artifact(path=path, project_id=project_id)
    if platform_id == "benchmark":
        return _parse_benchmark_artifact(path=path, project_id=project_id)
    if platform_id == "lighthouse":
        return _parse_lighthouse_artifact(path=path, project_id=project_id)
    if platform_id == "locust":
        return _parse_locust_artifact(path=path, project_id=project_id)
    if platform_id == "triage":
        return _parse_triage_artifact(path=path, project_id=project_id)
    return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"Unsupported platform: {platform_id}"])


def _parse_pytest_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    try:
        parsed = parse_junit_xml_file(
            path,
            project_id,
            run_metadata={
                "run_id": _default_run_id(project_id, "pytest", path),
                "timestamp": _file_timestamp(path),
                "framework": "pytest",
                "trigger": "file_watcher",
            },
        )
    except Exception as exc:
        return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"pytest parse failed: {exc}"])

    run = parsed.get("run", {})
    payload = IngestRunRequest(
        run_id=str(run.get("run_id") or _default_run_id(project_id, "pytest", path)).strip(),
        project_id=str(run.get("project_id") or project_id).strip(),
        timestamp=str(run.get("timestamp") or _file_timestamp(path)).strip(),
        git_sha=str(run.get("git_sha") or "").strip(),
        branch=str(run.get("branch") or "").strip(),
        agent_session_id=str(run.get("agent_session_id") or "").strip(),
        env_fingerprint=str(run.get("env_fingerprint") or "").strip(),
        trigger=str(run.get("trigger") or "file_watcher").strip() or "file_watcher",
        test_definitions=parsed.get("test_definitions", []) if isinstance(parsed.get("test_definitions"), list) else [],
        test_results=parsed.get("test_results", []) if isinstance(parsed.get("test_results"), list) else [],
        metadata=run.get("metadata", {}) if isinstance(run.get("metadata"), dict) else {},
    )
    errors = [str(err) for err in parsed.get("errors", []) if str(err).strip()]
    return ParsedTestArtifact(run_payload=payload, metrics=[], errors=errors)


def _parse_jest_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"jest parse failed: {exc}"])

    if isinstance(data, dict) and isinstance(data.get("testResults"), list):
        run_id = _default_run_id(project_id, "jest", path)
        timestamp = _file_timestamp(path)
        test_definitions: dict[str, dict[str, Any]] = {}
        test_results: list[dict[str, Any]] = []
        for suite in data.get("testResults", []):
            if not isinstance(suite, dict):
                continue
            file_path = str(suite.get("name") or "jest/unknown.test.ts").strip() or "jest/unknown.test.ts"
            for assertion in suite.get("assertionResults", []) or []:
                if not isinstance(assertion, dict):
                    continue
                title = str(assertion.get("title") or "unknown_test").strip() or "unknown_test"
                ancestors = [str(item).strip() for item in assertion.get("ancestorTitles", []) if str(item).strip()]
                test_name = " > ".join([*ancestors, title]) if ancestors else title
                status = JEST_STATUS_MAP.get(str(assertion.get("status") or "").strip(), "unknown")
                duration_ms = int(assertion.get("duration") or 0) if isinstance(assertion.get("duration"), int) else 0
                failure_messages = assertion.get("failureMessages", [])
                error_message = ""
                if isinstance(failure_messages, list) and failure_messages:
                    error_message = "\n".join(str(item) for item in failure_messages if str(item).strip())[:12000]
                test_id = generate_test_id(file_path, test_name, framework="jest")
                test_definitions[test_id] = {
                    "test_id": test_id,
                    "project_id": project_id,
                    "path": file_path,
                    "name": test_name,
                    "framework": "jest",
                    "tags": [],
                    "owner": "",
                }
                test_results.append(
                    {
                        "run_id": run_id,
                        "test_id": test_id,
                        "status": status,
                        "duration_ms": max(0, duration_ms),
                        "error_fingerprint": hashlib.sha256(error_message.encode("utf-8")).hexdigest()[:16] if error_message else "",
                        "error_message": error_message,
                        "artifact_refs": [],
                        "stdout_ref": "",
                        "stderr_ref": "",
                        "path": file_path,
                        "name": test_name,
                        "framework": "jest",
                        "tags": [],
                        "owner": "",
                    }
                )

        payload = _finalize_run_payload(
            project_id=project_id,
            run_id=run_id,
            timestamp=timestamp,
            trigger="file_watcher",
            test_definitions=list(test_definitions.values()),
            test_results=test_results,
        )
        return ParsedTestArtifact(run_payload=payload, metrics=[], errors=[])

    metrics = _parse_coverage_metrics(path, project_id, platform_id="jest")
    return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])


def _walk_playwright_suites(suite: dict[str, Any], bucket: list[tuple[str, str, str, int, str]]) -> None:
    for spec in suite.get("specs", []) or []:
        if not isinstance(spec, dict):
            continue
        title = str(spec.get("title") or "unknown_test").strip() or "unknown_test"
        file_path = str(spec.get("file") or "tests/e2e/unknown.spec.ts").strip() or "tests/e2e/unknown.spec.ts"
        tests = spec.get("tests", []) or []
        aggregate_status = "passed"
        duration_ms = 0
        error_message = ""
        for test in tests:
            if not isinstance(test, dict):
                continue
            for result in test.get("results", []) or []:
                if not isinstance(result, dict):
                    continue
                status = str(result.get("status") or "unknown").strip()
                duration_ms = max(duration_ms, int(result.get("duration") or 0))
                if status in PLAYWRIGHT_FAILED:
                    aggregate_status = "failed"
                    err = result.get("error", {})
                    if isinstance(err, dict):
                        error_message = str(err.get("message") or "").strip()[:12000]
                elif status in PLAYWRIGHT_SKIPPED and aggregate_status != "failed":
                    aggregate_status = "skipped"
        bucket.append((file_path, title, aggregate_status, duration_ms, error_message))
    for child in suite.get("suites", []) or []:
        if isinstance(child, dict):
            _walk_playwright_suites(child, bucket)


def _parse_playwright_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"playwright parse failed: {exc}"])

    run_id = _default_run_id(project_id, "playwright", path)
    timestamp = _file_timestamp(path)
    cases: list[tuple[str, str, str, int, str]] = []
    for suite in data.get("suites", []) or []:
        if isinstance(suite, dict):
            _walk_playwright_suites(suite, cases)

    definitions: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for file_path, title, status, duration_ms, error_message in cases:
        test_id = generate_test_id(file_path, title, framework="playwright")
        definitions[test_id] = {
            "test_id": test_id,
            "project_id": project_id,
            "path": file_path,
            "name": title,
            "framework": "playwright",
            "tags": [],
            "owner": "",
        }
        results.append(
            {
                "run_id": run_id,
                "test_id": test_id,
                "status": status,
                "duration_ms": max(0, duration_ms),
                "error_fingerprint": hashlib.sha256(error_message.encode("utf-8")).hexdigest()[:16] if error_message else "",
                "error_message": error_message,
                "artifact_refs": [],
                "stdout_ref": "",
                "stderr_ref": "",
                "path": file_path,
                "name": title,
                "framework": "playwright",
                "tags": [],
                "owner": "",
            }
        )
    payload = _finalize_run_payload(
        project_id=project_id,
        run_id=run_id,
        timestamp=timestamp,
        trigger="file_watcher",
        test_definitions=list(definitions.values()),
        test_results=results,
    )
    return ParsedTestArtifact(run_payload=payload, metrics=[], errors=[])


def _parse_coverage_metrics(path: Path, project_id: str, platform_id: str = "coverage") -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    run_id = _default_run_id(project_id, platform_id, path)
    source = str(path)

    if path.suffix.lower() == ".xml":
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
            line_rate = float(root.attrib.get("line-rate", 0) or 0)
            branch_rate = float(root.attrib.get("branch-rate", 0) or 0)
            metrics.append(_metric(platform_id, "coverage", "line_pct", line_rate * 100, unit="percent", source_file=source, run_id=run_id))
            metrics.append(_metric(platform_id, "coverage", "branch_pct", branch_rate * 100, unit="percent", source_file=source, run_id=run_id))
        except Exception:
            return metrics
        return metrics

    if path.name == "lcov.info":
        lines_found = 0.0
        lines_hit = 0.0
        branches_found = 0.0
        branches_hit = 0.0
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("LF:"):
                lines_found += float(line.split(":", 1)[1] or 0)
            elif line.startswith("LH:"):
                lines_hit += float(line.split(":", 1)[1] or 0)
            elif line.startswith("BRF:"):
                branches_found += float(line.split(":", 1)[1] or 0)
            elif line.startswith("BRH:"):
                branches_hit += float(line.split(":", 1)[1] or 0)
        if lines_found > 0:
            metrics.append(_metric(platform_id, "coverage", "line_pct", (lines_hit / lines_found) * 100.0, unit="percent", source_file=source, run_id=run_id))
        if branches_found > 0:
            metrics.append(_metric(platform_id, "coverage", "branch_pct", (branches_hit / branches_found) * 100.0, unit="percent", source_file=source, run_id=run_id))
        metrics.append(_metric(platform_id, "coverage", "lines_found", lines_found, source_file=source, run_id=run_id))
        return metrics

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return metrics

    if isinstance(data, dict) and isinstance(data.get("totals"), dict):
        totals = data.get("totals", {})
        pct = totals.get("percent_covered")
        if isinstance(pct, (int, float)):
            metrics.append(_metric(platform_id, "coverage", "line_pct", float(pct), unit="percent", source_file=source, run_id=run_id))
        lines_total = totals.get("num_statements")
        if isinstance(lines_total, (int, float)):
            metrics.append(_metric(platform_id, "coverage", "statements_total", float(lines_total), source_file=source, run_id=run_id))
        return metrics

    if isinstance(data, dict) and data and all(isinstance(v, dict) for v in data.values()):
        total_statements = 0
        covered = 0
        for file_cov in data.values():
            statement_counts = file_cov.get("s", {}) if isinstance(file_cov, dict) else {}
            if not isinstance(statement_counts, dict):
                continue
            for value in statement_counts.values():
                if isinstance(value, (int, float)):
                    total_statements += 1
                    if float(value) > 0:
                        covered += 1
        if total_statements > 0:
            metrics.append(_metric(platform_id, "coverage", "line_pct", (covered / total_statements) * 100.0, unit="percent", source_file=source, run_id=run_id))
            metrics.append(_metric(platform_id, "coverage", "statements_total", float(total_statements), source_file=source, run_id=run_id))
        return metrics

    return metrics


def _parse_coverage_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    return ParsedTestArtifact(
        run_payload=None,
        metrics=_parse_coverage_metrics(path, project_id, platform_id="coverage"),
        errors=[],
    )


def _flatten_numeric(prefix: str, value: Any, out: list[tuple[str, float]], *, limit: int = 120) -> None:
    if len(out) >= limit:
        return
    if isinstance(value, (int, float)):
        out.append((prefix, float(value)))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten_numeric(child, item, out, limit=limit)
    elif isinstance(value, list):
        for idx, item in enumerate(value[:15]):
            child = f"{prefix}.{idx}" if prefix else str(idx)
            _flatten_numeric(child, item, out, limit=limit)


def _parse_benchmark_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"benchmark parse failed: {exc}"])

    run_id = _default_run_id(project_id, "benchmark", path)
    source = str(path)
    metrics: list[dict[str, Any]] = []

    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    if isinstance(endpoints, list):
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            endpoint_name = str(endpoint.get("endpoint") or endpoint.get("name") or "unknown")
            for metric_name in ("mean", "p95", "p99", "success_rate", "requests_per_second"):
                value = endpoint.get(metric_name)
                if isinstance(value, (int, float)):
                    metrics.append(
                        _metric(
                            "benchmark",
                            "benchmark",
                            f"{endpoint_name}.{metric_name}",
                            float(value),
                            source_file=source,
                            run_id=run_id,
                        )
                    )

    flattened: list[tuple[str, float]] = []
    _flatten_numeric("", data, flattened)
    existing = {item["metric_name"] for item in metrics}
    for name, value in flattened:
        if name in existing:
            continue
        metrics.append(_metric("benchmark", "benchmark", name, value, source_file=source, run_id=run_id))
    return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])


def _parse_lighthouse_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    metrics: list[dict[str, Any]] = []
    run_id = _default_run_id(project_id, "lighthouse", path)
    source = str(path)
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"lighthouse parse failed: {exc}"])
        categories = data.get("categories", {}) if isinstance(data, dict) else {}
        if isinstance(categories, dict):
            for category, payload in categories.items():
                if not isinstance(payload, dict):
                    continue
                score = payload.get("score")
                if isinstance(score, (int, float)):
                    metrics.append(
                        _metric(
                            "lighthouse",
                            "lighthouse",
                            f"category.{category}.score",
                            float(score) * 100.0,
                            unit="percent",
                            source_file=source,
                            run_id=run_id,
                        )
                    )
        audits = data.get("audits", {}) if isinstance(data, dict) else {}
        for audit_key in ("first-contentful-paint", "largest-contentful-paint", "interactive"):
            payload = audits.get(audit_key) if isinstance(audits, dict) else None
            if isinstance(payload, dict):
                value = payload.get("numericValue")
                if isinstance(value, (int, float)):
                    metrics.append(
                        _metric(
                            "lighthouse",
                            "lighthouse",
                            f"audit.{audit_key}.numeric_value",
                            float(value),
                            source_file=source,
                            run_id=run_id,
                        )
                    )
    else:
        metrics.append(
            _metric(
                "lighthouse",
                "lighthouse",
                "report.size_bytes",
                float(path.stat().st_size),
                source_file=source,
                run_id=run_id,
            )
        )
    return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])


def _parse_locust_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    run_id = _default_run_id(project_id, "locust", path)
    source = str(path)
    if path.suffix.lower() == ".csv":
        metrics: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
        except Exception as exc:
            return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"locust csv parse failed: {exc}"])

        request_count = 0.0
        failure_count = 0.0
        response_time_sum = 0.0
        response_time_rows = 0.0
        for row in rows:
            for key in ("Request Count", "request_count"):
                value = row.get(key)
                if value and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
                    request_count += float(value)
                    break
            for key in ("Failure Count", "failure_count"):
                value = row.get(key)
                if value and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
                    failure_count += float(value)
                    break
            for key in ("Average Response Time", "avg_response_time", "average_response_time"):
                value = row.get(key)
                if value and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
                    response_time_sum += float(value)
                    response_time_rows += 1
                    break
        metrics.append(_metric("locust", "load", "request_count", request_count, source_file=source, run_id=run_id))
        metrics.append(_metric("locust", "load", "failure_count", failure_count, source_file=source, run_id=run_id))
        if response_time_rows > 0:
            metrics.append(
                _metric(
                    "locust",
                    "load",
                    "avg_response_time",
                    response_time_sum / response_time_rows,
                    unit="ms",
                    source_file=source,
                    run_id=run_id,
                )
            )
        return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])

    return ParsedTestArtifact(
        run_payload=None,
        metrics=[_metric("locust", "load", "report.size_bytes", float(path.stat().st_size), source_file=source, run_id=run_id)],
        errors=[],
    )


def _parse_triage_artifact(path: Path, project_id: str) -> ParsedTestArtifact:
    run_id = _default_run_id(project_id, "triage", path)
    source = str(path)
    metrics: list[dict[str, Any]] = []
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ParsedTestArtifact(run_payload=None, metrics=[], errors=[f"triage parse failed: {exc}"])
        total = data.get("total_failures")
        if isinstance(total, (int, float)):
            metrics.append(_metric("triage", "triage", "total_failures", float(total), source_file=source, run_id=run_id))
        by_framework = data.get("by_framework", {})
        if isinstance(by_framework, dict):
            for framework, value in by_framework.items():
                if isinstance(value, (int, float)):
                    metrics.append(
                        _metric(
                            "triage",
                            "triage",
                            f"framework.{framework}.failures",
                            float(value),
                            source_file=source,
                            run_id=run_id,
                        )
                    )
        return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])

    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"^([A-Za-z0-9_.-]+):\s+(\d+)\s+failures$", text, flags=re.MULTILINE):
            framework = match.group(1)
            value = float(match.group(2))
            metrics.append(
                _metric(
                    "triage",
                    "triage",
                    f"framework.{framework}.failures",
                    value,
                    source_file=source,
                    run_id=run_id,
                )
            )
        return ParsedTestArtifact(run_payload=None, metrics=metrics, errors=[])

    return ParsedTestArtifact(
        run_payload=None,
        metrics=[_metric("triage", "triage", "artifact.size_bytes", float(path.stat().st_size), source_file=source, run_id=run_id)],
        errors=[],
    )
