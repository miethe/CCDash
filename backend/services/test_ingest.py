"""Service layer for idempotent test run ingestion."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.db.factory import (
    get_test_definition_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.models import IngestRunRequest, IngestRunResponse
from backend.parsers.test_results import generate_test_id


_FAILED_STATUSES = {"failed", "error", "xpassed"}
_SKIPPED_STATUSES = {"skipped", "xfailed"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        return int(value)
    except Exception:
        return default


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_status(value: Any) -> str:
    token = str(value or "passed").strip().lower()
    if token in {"pass", "ok", "success"}:
        return "passed"
    if token in {"failure", "fail"}:
        return "failed"
    if token in {"skip"}:
        return "skipped"
    if token in {"xfail"}:
        return "xfailed"
    if token in {"xpass"}:
        return "xpassed"
    if not token:
        return "passed"
    return token


def _coerce_test_result_row(row: dict[str, Any], run_id: str) -> dict[str, Any]:
    path = str(row.get("path") or row.get("file") or "").strip()
    name = str(row.get("name") or row.get("test_name") or "").strip()
    framework = str(row.get("framework") or "pytest").strip() or "pytest"

    test_id = str(row.get("test_id") or "").strip()
    if not test_id and path and name:
        test_id = generate_test_id(path, name, framework=framework)
    if not test_id and name:
        # Keep deterministic behavior when path is absent in caller payload.
        fallback_key = hashlib.sha256(f"{name}::{framework}".encode("utf-8")).hexdigest()[:32]
        test_id = fallback_key

    return {
        "run_id": run_id,
        "test_id": test_id,
        "status": _normalize_status(row.get("status")),
        "duration_ms": max(0, _safe_int(row.get("duration_ms"))),
        "error_fingerprint": str(row.get("error_fingerprint") or "").strip(),
        "error_message": str(row.get("error_message") or "").strip(),
        "artifact_refs": [str(value) for value in _safe_list(row.get("artifact_refs")) if str(value).strip()],
        "stdout_ref": str(row.get("stdout_ref") or "").strip(),
        "stderr_ref": str(row.get("stderr_ref") or "").strip(),
        "path": path,
        "name": name,
        "framework": framework,
        "tags": [str(value).strip() for value in _safe_list(row.get("tags")) if str(value).strip()],
        "owner": str(row.get("owner") or "").strip(),
    }


def _coerce_test_definition_row(row: dict[str, Any], project_id: str) -> dict[str, Any]:
    return {
        "test_id": str(row.get("test_id") or "").strip(),
        "project_id": project_id,
        "path": str(row.get("path") or "").strip(),
        "name": str(row.get("name") or "").strip(),
        "framework": str(row.get("framework") or "pytest").strip() or "pytest",
        "tags": [str(value).strip() for value in _safe_list(row.get("tags")) if str(value).strip()],
        "owner": str(row.get("owner") or "").strip(),
    }


def _build_definition_map(payload: IngestRunRequest, normalized_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}

    for row in payload.test_definitions:
        source = _coerce_test_definition_row(_safe_dict(row), payload.project_id)
        test_id = source["test_id"]
        if not test_id:
            continue
        definitions[test_id] = source

    for row in normalized_results:
        test_id = str(row.get("test_id") or "").strip()
        if not test_id:
            continue
        definitions[test_id] = {
            "test_id": test_id,
            "project_id": payload.project_id,
            "path": str(row.get("path") or "").strip(),
            "name": str(row.get("name") or "").strip(),
            "framework": str(row.get("framework") or "pytest").strip() or "pytest",
            "tags": [str(value).strip() for value in _safe_list(row.get("tags")) if str(value).strip()],
            "owner": str(row.get("owner") or "").strip(),
        }

    return definitions


async def _session_exists(db: Any, session_id: str) -> bool:
    if not session_id:
        return False
    if isinstance(db, aiosqlite.Connection):
        async with db.execute("SELECT 1 FROM sessions WHERE id = ? LIMIT 1", (session_id,)) as cur:
            row = await cur.fetchone()
            return row is not None
    row = await db.fetchrow("SELECT 1 FROM sessions WHERE id = $1 LIMIT 1", session_id)
    return row is not None


async def _load_existing_result_ids(db: Any, run_id: str) -> set[str]:
    if isinstance(db, aiosqlite.Connection):
        async with db.execute("SELECT test_id FROM test_results WHERE run_id = ?", (run_id,)) as cur:
            rows = await cur.fetchall()
        return {str(row[0]) for row in rows}
    rows = await db.fetch("SELECT test_id FROM test_results WHERE run_id = $1", run_id)
    return {str(row["test_id"]) for row in rows}


async def _load_status_counts(db: Any, run_id: str) -> tuple[int, int, int, int]:
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(
            "SELECT status, COUNT(*) AS count FROM test_results WHERE run_id = ? GROUP BY status",
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
        grouped = {str(row[0]).strip().lower(): int(row[1]) for row in rows}
    else:
        rows = await db.fetch(
            "SELECT status, COUNT(*)::int AS count FROM test_results WHERE run_id = $1 GROUP BY status",
            run_id,
        )
        grouped = {str(row["status"]).strip().lower(): int(row["count"]) for row in rows}

    total = sum(grouped.values())
    passed = 0
    failed = 0
    skipped = 0
    for status, count in grouped.items():
        if status in _FAILED_STATUSES:
            failed += count
        elif status in _SKIPPED_STATUSES:
            skipped += count
        else:
            passed += count
    return total, passed, failed, skipped


async def ingest_run(payload: IngestRunRequest, db: Any) -> IngestRunResponse:
    """Idempotently persist a test run and associated result rows."""
    errors: list[str] = []
    run_id = str(payload.run_id or "").strip()
    project_id = str(payload.project_id or "").strip()
    timestamp = str(payload.timestamp or "").strip()

    if not run_id or not project_id or not timestamp:
        return IngestRunResponse(
            run_id=run_id or "",
            status="skipped",
            errors=["Missing required fields: run_id, project_id, timestamp"],
        )

    run_repo = get_test_run_repository(db)
    definition_repo = get_test_definition_repository(db)
    result_repo = get_test_result_repository(db)

    existing_run = await run_repo.get_by_id(run_id)
    existing_result_ids = await _load_existing_result_ids(db, run_id)
    inserted = 0
    skipped = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    normalized_results: list[dict[str, Any]] = []
    for raw_row in payload.test_results:
        row = _coerce_test_result_row(_safe_dict(raw_row), run_id)
        if not row["test_id"]:
            errors.append("Skipped test result row with missing test_id/path/name.")
            continue
        normalized_results.append(row)

    definitions = _build_definition_map(payload, normalized_results)
    definition_upserts = 0
    for row in definitions.values():
        if not row["test_id"]:
            continue
        await definition_repo.upsert(row, project_id=project_id)
        definition_upserts += 1

    # Ensure parent run row exists before inserting child test_results rows.
    # In production SQLite connections we enforce PRAGMA foreign_keys=ON.
    await run_repo.upsert(
        {
            "run_id": run_id,
            "project_id": project_id,
            "timestamp": timestamp,
            "git_sha": str(payload.git_sha or "").strip(),
            "branch": str(payload.branch or "").strip(),
            "agent_session_id": str(payload.agent_session_id or "").strip(),
            "env_fingerprint": str(payload.env_fingerprint or "").strip(),
            "trigger": str(payload.trigger or "local").strip() or "local",
            "status": "ingesting",
            "total_tests": int((existing_run or {}).get("total_tests") or 0),
            "passed_tests": int((existing_run or {}).get("passed_tests") or 0),
            "failed_tests": int((existing_run or {}).get("failed_tests") or 0),
            "skipped_tests": int((existing_run or {}).get("skipped_tests") or 0),
            "duration_ms": int((existing_run or {}).get("duration_ms") or 0),
            "metadata": payload.metadata,
            "created_at": str((existing_run or {}).get("created_at") or now_iso),
        },
        project_id=project_id,
    )

    for row in normalized_results:
        test_id = row["test_id"]
        if test_id in existing_result_ids:
            skipped += 1
            continue
        await result_repo.upsert(row)
        existing_result_ids.add(test_id)
        inserted += 1

    session_id = str(payload.agent_session_id or "").strip()
    if session_id and not await _session_exists(db, session_id):
        errors.append(f"Unknown agent_session_id '{session_id}' (ingestion accepted).")

    total_tests, passed_tests, failed_tests, skipped_tests = await _load_status_counts(db, run_id)
    run_status = "failed" if failed_tests > 0 else "complete"
    duration_ms = sum(_safe_int(row.get("duration_ms")) for row in normalized_results)

    await run_repo.upsert(
        {
            "run_id": run_id,
            "project_id": project_id,
            "timestamp": timestamp,
            "git_sha": str(payload.git_sha or "").strip(),
            "branch": str(payload.branch or "").strip(),
            "agent_session_id": session_id,
            "env_fingerprint": str(payload.env_fingerprint or "").strip(),
            "trigger": str(payload.trigger or "local").strip() or "local",
            "status": run_status,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests,
            "duration_ms": duration_ms,
            "metadata": payload.metadata,
            "created_at": str((existing_run or {}).get("created_at") or now_iso),
        },
        project_id=project_id,
    )

    ingest_status = "created"
    if existing_run and inserted == 0:
        ingest_status = "skipped"
    elif existing_run and inserted > 0:
        ingest_status = "updated"

    return IngestRunResponse(
        run_id=run_id,
        status=ingest_status,
        test_definitions_upserted=definition_upserts,
        test_results_inserted=inserted,
        test_results_skipped=skipped,
        mapping_trigger_queued=False,
        integrity_check_queued=False,
        errors=errors,
    )
