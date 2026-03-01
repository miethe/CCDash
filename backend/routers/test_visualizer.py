"""Test Visualizer API router."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend import config
from backend.db import connection
from backend.db.factory import (
    get_test_definition_repository,
    get_test_integrity_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.models import (
    CursorPaginatedResponse,
    DomainHealthRollupDTO,
    FeatureTestHealthDTO,
    FeatureTimelineResponseDTO,
    IngestRunRequest,
    IngestRunResponse,
    TestCorrelationResponseDTO,
    TestDefinitionDTO,
    TestIntegritySignalDTO,
    TestResultDTO,
    TestResultHistoryDTO,
    TestRunDTO,
    TestRunDetailDTO,
)
from backend.observability import start_span
from backend.parsers.test_results import parse_junit_xml
from backend.project_manager import project_manager
from backend.services.test_health import TestHealthService
from backend.services.test_ingest import ingest_run


logger = logging.getLogger("ccdash.test_visualizer")
test_visualizer_router = APIRouter(prefix="/api/tests", tags=["test-visualizer"])


def _error(status_code: int, *, error: str, message: str, hint: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, "hint": hint},
    )


def _require_feature_enabled() -> None:
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        raise _error(
            503,
            error="feature_disabled",
            message="Test Visualizer is not enabled.",
            hint="Set CCDASH_TEST_VISUALIZER_ENABLED=true in environment.",
        )


def _extract_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("`meta` must be a JSON object.")


def _encode_cursor(offset: int, **kwargs: Any) -> str:
    payload = {"offset": max(0, int(offset))}
    payload.update(kwargs)
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {"offset": 0}
    try:
        raw = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
    except Exception as exc:
        raise _error(
            400,
            error="invalid_cursor",
            message="Cursor is malformed.",
            hint="Provide next_cursor from the previous response.",
        ) from exc

    if not isinstance(payload, dict):
        raise _error(
            400,
            error="invalid_cursor",
            message="Cursor payload is invalid.",
            hint="Provide next_cursor from the previous response.",
        )
    try:
        payload["offset"] = max(0, int(payload.get("offset", 0)))
    except Exception as exc:
        raise _error(
            400,
            error="invalid_cursor",
            message="Cursor offset is invalid.",
            hint="Provide next_cursor from the previous response.",
        ) from exc
    return payload


def _page(items: list[Any], *, offset: int, limit: int, total: int) -> tuple[list[Any], str | None]:
    paged = items[offset: offset + limit]
    next_offset = offset + len(paged)
    next_cursor = _encode_cursor(next_offset) if next_offset < total else None
    return paged, next_cursor


def _to_test_run_dto(row: dict[str, Any]) -> TestRunDTO:
    return TestRunDTO(
        run_id=str(row.get("run_id") or ""),
        project_id=str(row.get("project_id") or ""),
        timestamp=str(row.get("timestamp") or ""),
        git_sha=str(row.get("git_sha") or ""),
        branch=str(row.get("branch") or ""),
        agent_session_id=str(row.get("agent_session_id") or ""),
        env_fingerprint=str(row.get("env_fingerprint") or ""),
        trigger=str(row.get("trigger") or "local"),
        status=str(row.get("status") or "complete"),
        total_tests=int(row.get("total_tests") or 0),
        passed_tests=int(row.get("passed_tests") or 0),
        failed_tests=int(row.get("failed_tests") or 0),
        skipped_tests=int(row.get("skipped_tests") or 0),
        duration_ms=int(row.get("duration_ms") or 0),
        metadata=row.get("metadata_json", {}) if isinstance(row.get("metadata_json", {}), dict) else {},
        created_at=str(row.get("created_at") or ""),
    )


def _to_test_result_dto(row: dict[str, Any]) -> TestResultDTO:
    refs = row.get("artifact_refs_json", [])
    if not isinstance(refs, list):
        refs = []
    return TestResultDTO(
        run_id=str(row.get("run_id") or ""),
        test_id=str(row.get("test_id") or ""),
        status=str(row.get("status") or ""),
        duration_ms=int(row.get("duration_ms") or 0),
        error_fingerprint=str(row.get("error_fingerprint") or ""),
        error_message=str(row.get("error_message") or ""),
        artifact_refs=[str(item) for item in refs if str(item).strip()],
        stdout_ref=str(row.get("stdout_ref") or ""),
        stderr_ref=str(row.get("stderr_ref") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _to_test_history_dto(row: dict[str, Any], run: dict[str, Any] | None) -> TestResultHistoryDTO:
    refs = row.get("artifact_refs_json", [])
    if not isinstance(refs, list):
        refs = []
    run_row = run or {}
    return TestResultHistoryDTO(
        run_id=str(row.get("run_id") or ""),
        test_id=str(row.get("test_id") or ""),
        status=str(row.get("status") or ""),
        duration_ms=int(row.get("duration_ms") or 0),
        error_fingerprint=str(row.get("error_fingerprint") or ""),
        error_message=str(row.get("error_message") or ""),
        artifact_refs=[str(item) for item in refs if str(item).strip()],
        stdout_ref=str(row.get("stdout_ref") or ""),
        stderr_ref=str(row.get("stderr_ref") or ""),
        created_at=str(row.get("created_at") or ""),
        run_timestamp=str(run_row.get("timestamp") or row.get("run_timestamp") or ""),
        git_sha=str(run_row.get("git_sha") or ""),
        agent_session_id=str(run_row.get("agent_session_id") or ""),
    )


def _to_test_definition_dto(row: dict[str, Any]) -> TestDefinitionDTO:
    tags = row.get("tags_json", [])
    if not isinstance(tags, list):
        tags = []
    return TestDefinitionDTO(
        test_id=str(row.get("test_id") or ""),
        project_id=str(row.get("project_id") or ""),
        path=str(row.get("path") or ""),
        name=str(row.get("name") or ""),
        framework=str(row.get("framework") or "pytest"),
        tags=[str(item) for item in tags if str(item).strip()],
        owner=str(row.get("owner") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _to_test_signal_dto(row: dict[str, Any]) -> TestIntegritySignalDTO:
    details = row.get("details_json", {}) if isinstance(row.get("details_json"), dict) else {}
    linked = row.get("linked_run_ids_json", [])
    if not isinstance(linked, list):
        linked = []
    return TestIntegritySignalDTO(
        signal_id=str(row.get("signal_id") or ""),
        project_id=str(row.get("project_id") or ""),
        git_sha=str(row.get("git_sha") or ""),
        file_path=str(row.get("file_path") or ""),
        test_id=str(row.get("test_id") or "") or None,
        signal_type=str(row.get("signal_type") or ""),
        severity=str(row.get("severity") or "medium"),
        details=details,
        linked_run_ids=[str(item) for item in linked if str(item).strip()],
        agent_session_id=str(row.get("agent_session_id") or ""),
        created_at=str(row.get("created_at") or ""),
    )


async def _request_payload_from_multipart(request: Request) -> tuple[IngestRunRequest, list[str]]:
    form = await request.form()
    xml_file = form.get("xml_file")
    if not isinstance(xml_file, UploadFile):
        raise HTTPException(status_code=400, detail="Missing required multipart field: xml_file")

    try:
        meta = _extract_meta(form.get("meta"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active_project = project_manager.get_active_project()
    project_id = str(meta.get("project_id") or (active_project.id if active_project else "")).strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required (meta.project_id or active project).")

    xml_bytes = await xml_file.read()
    xml_text = xml_bytes.decode("utf-8", errors="replace")
    parsed = parse_junit_xml(xml_text, project_id=project_id, run_metadata=meta)
    run_data = parsed.get("run", {}) if isinstance(parsed.get("run"), dict) else {}
    parser_errors = [str(err) for err in parsed.get("errors", []) if str(err).strip()]

    payload = IngestRunRequest(
        run_id=str(run_data.get("run_id") or "").strip(),
        project_id=str(run_data.get("project_id") or project_id).strip(),
        timestamp=str(run_data.get("timestamp") or "").strip(),
        git_sha=str(run_data.get("git_sha") or "").strip(),
        branch=str(run_data.get("branch") or "").strip(),
        agent_session_id=str(run_data.get("agent_session_id") or "").strip(),
        env_fingerprint=str(run_data.get("env_fingerprint") or "").strip(),
        trigger=str(run_data.get("trigger") or "local").strip() or "local",
        test_definitions=parsed.get("test_definitions", []) if isinstance(parsed.get("test_definitions"), list) else [],
        test_results=parsed.get("test_results", []) if isinstance(parsed.get("test_results"), list) else [],
        metadata=run_data.get("metadata", {}) if isinstance(run_data.get("metadata"), dict) else {},
    )
    return payload, parser_errors


async def _request_payload_from_json(request: Request) -> IngestRunRequest:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc

    try:
        return IngestRunRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc


async def _trigger_mapping_resolution(run_id: str, project_id: str, db: Any) -> None:
    """Background hook stub for domain mapping resolution (Phase 7)."""
    _ = db
    logger.info("Queued mapping resolution stub run_id=%s project_id=%s", run_id, project_id)


async def _trigger_integrity_check(run_id: str, git_sha: str, project_id: str, db: Any) -> None:
    """Background hook stub for integrity signal detection (Phase 7)."""
    _ = db
    logger.info(
        "Queued integrity check stub run_id=%s project_id=%s git_sha=%s",
        run_id,
        project_id,
        git_sha,
    )


@test_visualizer_router.post("/ingest", response_model=IngestRunResponse)
async def ingest_test_run(request: Request) -> IngestRunResponse:
    """Ingest test results from JSON payload or multipart JUnit XML upload."""
    _require_feature_enabled()

    content_type = str(request.headers.get("content-type") or "").lower()
    parser_errors: list[str] = []
    if "multipart/form-data" in content_type:
        payload, parser_errors = await _request_payload_from_multipart(request)
    else:
        payload = await _request_payload_from_json(request)

    db = await connection.get_connection()
    with start_span(
        "test_visualizer.ingest",
        attributes={"project_id": payload.project_id, "run_id": payload.run_id},
    ):
        response = await ingest_run(payload, db)
    errors = list(response.errors)
    errors.extend(parser_errors)

    mapping_queued = False
    integrity_queued = False

    try:
        asyncio.create_task(_trigger_mapping_resolution(payload.run_id, payload.project_id, db))
        mapping_queued = True
    except Exception as exc:
        logger.warning("Failed to queue mapping resolution: %s", exc)
        errors.append(f"Failed to queue mapping resolution: {exc}")

    if config.CCDASH_INTEGRITY_SIGNALS_ENABLED and payload.git_sha:
        try:
            asyncio.create_task(
                _trigger_integrity_check(payload.run_id, payload.git_sha, payload.project_id, db)
            )
            integrity_queued = True
        except Exception as exc:
            logger.warning("Failed to queue integrity check: %s", exc)
            errors.append(f"Failed to queue integrity check: {exc}")

    return response.model_copy(
        update={
            "mapping_trigger_queued": mapping_queued,
            "integrity_check_queued": integrity_queued,
            "errors": errors,
        }
    )


@test_visualizer_router.get("/health/domains", response_model=list[DomainHealthRollupDTO])
async def get_domain_health(
    request: Request,
    project_id: str,
    since: str | None = None,
    include_children: bool = True,
) -> list[DomainHealthRollupDTO]:
    _ = request
    _require_feature_enabled()
    db = await connection.get_connection()
    service = TestHealthService(db)
    with start_span(
        "test_visualizer.get_domain_health",
        attributes={"project_id": project_id, "since": since or "", "domain_id": "*"},
    ) as span:
        rows = await service.get_domain_rollups(project_id=project_id, since=since, include_children=include_children)
        if span is not None:
            span.set_attribute("result_count", len(rows))
    return rows


@test_visualizer_router.get("/health/features", response_model=CursorPaginatedResponse[FeatureTestHealthDTO])
async def get_feature_health(
    request: Request,
    project_id: str,
    domain_id: str | None = None,
    since: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> CursorPaginatedResponse[FeatureTestHealthDTO]:
    _ = request
    _require_feature_enabled()
    page = _decode_cursor(cursor)
    offset = int(page.get("offset", 0))

    db = await connection.get_connection()
    service = TestHealthService(db)
    with start_span(
        "test_visualizer.get_feature_health",
        attributes={"project_id": project_id, "domain_id": domain_id or "", "since": since or ""},
    ) as span:
        items, total = await service.list_feature_health(
            project_id=project_id,
            domain_id=domain_id,
            since=since,
            offset=0,
            limit=10000,
        )
        paged, next_cursor = _page(items, offset=offset, limit=limit, total=total)
        if span is not None:
            span.set_attribute("result_count", len(paged))

    return CursorPaginatedResponse[FeatureTestHealthDTO](
        items=paged,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@test_visualizer_router.get("/runs/{run_id}", response_model=TestRunDetailDTO)
async def get_run_detail(request: Request, run_id: str) -> TestRunDetailDTO:
    _ = request
    _require_feature_enabled()
    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)
    definition_repo = get_test_definition_repository(db)
    integrity_repo = get_test_integrity_repository(db)

    with start_span("test_visualizer.get_run_detail", attributes={"run_id": run_id}) as span:
        run = await run_repo.get_by_id(run_id)
        if run is None:
            raise _error(
                404,
                error="run_not_found",
                message=f"No run found with id={run_id}",
                hint="Check run_id is correct and was ingested successfully.",
            )

        results = await result_repo.get_by_run(run_id)
        test_ids = [str(row.get("test_id") or "").strip() for row in results]
        definitions: dict[str, TestDefinitionDTO] = {}
        for test_id in test_ids:
            if not test_id:
                continue
            definition = await definition_repo.get_by_id(test_id)
            if definition:
                definitions[test_id] = _to_test_definition_dto(definition)

        signals = await integrity_repo.list_by_sha(
            project_id=str(run.get("project_id") or ""),
            git_sha=str(run.get("git_sha") or ""),
            limit=500,
        )
        run_signal_rows = []
        for signal in signals:
            linked = signal.get("linked_run_ids_json", [])
            if isinstance(linked, list) and run_id in [str(item) for item in linked]:
                run_signal_rows.append(signal)

        response = TestRunDetailDTO(
            run=_to_test_run_dto(run),
            results=[_to_test_result_dto(row) for row in results],
            definitions=definitions,
            integrity_signals=[_to_test_signal_dto(row) for row in run_signal_rows],
        )
        if span is not None:
            span.set_attribute("result_count", len(response.results))
        return response


@test_visualizer_router.get("/runs", response_model=CursorPaginatedResponse[TestRunDTO])
async def list_runs(
    request: Request,
    project_id: str,
    agent_session_id: str | None = None,
    feature_id: str | None = None,
    git_sha: str | None = None,
    since: str | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=200),
) -> CursorPaginatedResponse[TestRunDTO]:
    _ = request
    _require_feature_enabled()
    cursor_data = _decode_cursor(cursor)
    offset = int(cursor_data.get("offset", 0))

    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)
    service = TestHealthService(db)

    with start_span(
        "test_visualizer.list_runs",
        attributes={"project_id": project_id, "feature_id": feature_id or "", "session_id": agent_session_id or ""},
    ) as span:
        runs = await run_repo.list_by_project(project_id=project_id, limit=5000, offset=0)
        if agent_session_id:
            runs = [row for row in runs if str(row.get("agent_session_id") or "") == agent_session_id]
        if git_sha:
            runs = [row for row in runs if str(row.get("git_sha") or "") == git_sha]
        if since:
            runs = [row for row in runs if str(row.get("timestamp") or "") >= since]

        if feature_id:
            filtered: list[dict[str, Any]] = []
            for run in runs:
                run_id = str(run.get("run_id") or "")
                if not run_id:
                    continue
                mappings = await service._list_mappings_for_run(project_id=project_id, run_id=run_id)
                if any(str(row.get("feature_id") or "") == feature_id for row in mappings):
                    filtered.append(run)
            runs = filtered

        total = len(runs)
        paged, next_cursor = _page(runs, offset=offset, limit=limit, total=total)
        items = [_to_test_run_dto(row) for row in paged]
        if span is not None:
            span.set_attribute("result_count", len(items))

    return CursorPaginatedResponse[TestRunDTO](items=items, total=total, limit=limit, next_cursor=next_cursor)


@test_visualizer_router.get("/{test_id}/history", response_model=CursorPaginatedResponse[TestResultHistoryDTO])
async def get_test_history(
    request: Request,
    test_id: str,
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    since: str | None = None,
    cursor: str | None = None,
) -> CursorPaginatedResponse[TestResultHistoryDTO]:
    _ = request
    _require_feature_enabled()
    cursor_data = _decode_cursor(cursor)
    offset = int(cursor_data.get("offset", 0))

    db = await connection.get_connection()
    result_repo = get_test_result_repository(db)
    run_repo = get_test_run_repository(db)

    with start_span(
        "test_visualizer.get_test_history",
        attributes={"project_id": project_id, "test_id": test_id, "since": since or ""},
    ) as span:
        history = await result_repo.get_history_for_test(test_id=test_id, limit=5000)
        filtered: list[dict[str, Any]] = []
        run_cache: dict[str, dict[str, Any] | None] = {}
        for row in history:
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            if run_id not in run_cache:
                run_cache[run_id] = await run_repo.get_by_id(run_id)
            run = run_cache.get(run_id)
            if run is None:
                continue
            if str(run.get("project_id") or "") != project_id:
                continue
            if since and str(run.get("timestamp") or "") < since:
                continue
            filtered.append(row)

        total = len(filtered)
        page_rows, next_cursor = _page(filtered, offset=offset, limit=limit, total=total)
        items = [_to_test_history_dto(row, run_cache.get(str(row.get("run_id") or ""))) for row in page_rows]
        if span is not None:
            span.set_attribute("result_count", len(items))

    return CursorPaginatedResponse[TestResultHistoryDTO](
        items=items,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@test_visualizer_router.get("/features/{feature_id}/timeline", response_model=FeatureTimelineResponseDTO)
async def get_feature_timeline(
    request: Request,
    feature_id: str,
    project_id: str,
    since: str | None = None,
    until: str | None = None,
    include_signals: bool = True,
) -> FeatureTimelineResponseDTO:
    _ = request
    _require_feature_enabled()
    db = await connection.get_connection()
    service = TestHealthService(db)
    with start_span(
        "test_visualizer.get_feature_timeline",
        attributes={
            "project_id": project_id,
            "feature_id": feature_id,
            "since": since or "",
            "until": until or "",
        },
    ) as span:
        payload = await service.get_feature_timeline(
            project_id=project_id,
            feature_id=feature_id,
            since=since,
            until=until,
            include_signals=include_signals,
        )
        if span is not None:
            span.set_attribute("result_count", len(payload.timeline))
    return payload


@test_visualizer_router.get("/integrity/alerts", response_model=CursorPaginatedResponse[TestIntegritySignalDTO])
async def list_integrity_alerts(
    request: Request,
    project_id: str,
    since: str | None = None,
    signal_type: str | None = None,
    severity: str | None = None,
    agent_session_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> CursorPaginatedResponse[TestIntegritySignalDTO]:
    _ = request
    _require_feature_enabled()
    cursor_data = _decode_cursor(cursor)
    offset = int(cursor_data.get("offset", 0))

    db = await connection.get_connection()
    integrity_repo = get_test_integrity_repository(db)

    with start_span(
        "test_visualizer.list_integrity_alerts",
        attributes={"project_id": project_id, "signal_type": signal_type or "", "severity": severity or ""},
    ) as span:
        if since:
            rows = await integrity_repo.list_since(project_id=project_id, since=since, limit=5000)
        else:
            rows = await integrity_repo.list_by_project(project_id=project_id, limit=5000, offset=0)

        if signal_type:
            rows = [row for row in rows if str(row.get("signal_type") or "") == signal_type]
        if severity:
            rows = [row for row in rows if str(row.get("severity") or "") == severity]
        if agent_session_id:
            rows = [row for row in rows if str(row.get("agent_session_id") or "") == agent_session_id]

        total = len(rows)
        page_rows, next_cursor = _page(rows, offset=offset, limit=limit, total=total)
        items = [_to_test_signal_dto(row) for row in page_rows]
        if span is not None:
            span.set_attribute("result_count", len(items))

    return CursorPaginatedResponse[TestIntegritySignalDTO](
        items=items,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@test_visualizer_router.get("/correlate", response_model=TestCorrelationResponseDTO)
async def correlate_run(
    request: Request,
    run_id: str,
    project_id: str,
) -> TestCorrelationResponseDTO:
    _ = request
    _require_feature_enabled()

    db = await connection.get_connection()
    service = TestHealthService(db)
    with start_span(
        "test_visualizer.correlate",
        attributes={"project_id": project_id, "run_id": run_id},
    ):
        payload = await service.get_correlation(run_id=run_id, project_id=project_id)

    if payload is None:
        raise _error(
            404,
            error="run_not_found",
            message=f"No run found with id={run_id}",
            hint="Check run_id is correct and was ingested successfully.",
        )
    return payload
