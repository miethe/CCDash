"""Test Visualizer API router."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend import config
from backend.db import connection
from backend.db.factory import (
    get_test_definition_repository,
    get_test_integrity_repository,
    get_test_mapping_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.models import (
    BackfillTestMappingsRequest,
    BackfillTestMappingsResponse,
    CursorPaginatedResponse,
    DomainHealthRollupDTO,
    FeatureTestHealthDTO,
    FeatureTimelineResponseDTO,
    Project,
    TestMetricSummaryDTO,
    IngestRunRequest,
    IngestRunResponse,
    SyncTestsRequest,
    SyncTestsResponse,
    TestCorrelationResponseDTO,
    TestVisualizerConfigDTO,
    TestDefinitionDTO,
    TestIntegritySignalDTO,
    TestResultDTO,
    TestResultHistoryDTO,
    TestRunDTO,
    TestRunDetailDTO,
    TestSourceStatusDTO,
)
from backend.observability import start_span
from backend.parsers.test_results import parse_junit_xml
from backend.project_manager import project_manager
from backend.services.test_config import (
    effective_test_flags,
    parser_health_map,
    resolve_test_sources,
)
from backend.services.integrity_detector import IntegrityDetector
from backend.services.mapping_resolver import (
    MappingResolver,
    SemanticLLMProvider,
    validate_semantic_mapping_file,
)
from backend.services.test_health import TestHealthService
from backend.services.test_ingest import ingest_run


logger = logging.getLogger("ccdash.test_visualizer")
test_visualizer_router = APIRouter(prefix="/api/tests", tags=["test-visualizer"])


def _error(status_code: int, *, error: str, message: str, hint: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, "hint": hint},
    )


def _require_env_feature_enabled() -> None:
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        raise _error(
            503,
            error="feature_disabled",
            message="Test Visualizer is not enabled.",
            hint="Set CCDASH_TEST_VISUALIZER_ENABLED=true in environment.",
        )


def _resolve_project(project_id: str | None) -> Any:
    if project_id:
        project = project_manager.get_project(project_id)
        if not project:
            project = Project(
                id=project_id,
                name=f"Project {project_id}",
                path=config.CCDASH_PROJECT_ROOT,
                description="",
                repoUrl="",
                agentPlatforms=["Claude Code"],
                planDocsPath="docs/project_plans/",
                sessionsPath="",
                progressPath="progress",
            )
        return project
    active = project_manager.get_active_project()
    if not active:
        raise _error(
            404,
            error="project_not_found",
            message="No active project is configured.",
            hint="Select an active project in Settings.",
        )
    return active


def _require_feature_enabled(project_id: str | None) -> tuple[Any, Any]:
    _require_env_feature_enabled()
    project = _resolve_project(project_id)
    flags = effective_test_flags(project)
    if not flags.testVisualizerEnabled:
        raise _error(
            503,
            error="feature_disabled",
            message="Test Visualizer is disabled for this project.",
            hint="Enable Test Visualizer in Project Settings > Testing.",
        )
    return project, flags


def _discover_source_files(base_dir: Path, patterns: list[str], max_scan: int = 400) -> list[Path]:
    if not base_dir.exists():
        return []
    found: list[Path] = []
    if patterns:
        for pattern in patterns:
            for path in base_dir.glob(pattern):
                if path.is_file():
                    found.append(path)
                if len(found) >= max_scan:
                    break
            if len(found) >= max_scan:
                break
    else:
        for path in base_dir.rglob("*"):
            if path.is_file():
                found.append(path)
            if len(found) >= max_scan:
                break
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _source_status_rows(project: Any, request: Request | None = None) -> list[TestSourceStatusDTO]:
    sources = resolve_test_sources(project, include_disabled=True)
    sync = getattr(request.app.state, "sync_engine", None) if request else None
    rows: list[TestSourceStatusDTO] = []
    for source in sources:
        files = _discover_source_files(source.resolved_dir, source.patterns, max_scan=250)
        last_error = ""
        last_synced = ""
        if sync and hasattr(sync, "get_source_runtime_state"):
            try:
                last_error, last_synced = sync.get_source_runtime_state(source)
            except Exception:
                last_error = ""
                last_synced = ""
        rows.append(
            TestSourceStatusDTO(
                platformId=source.platform_id,
                enabled=source.enabled,
                watch=source.watch,
                resultsDir=source.results_dir,
                resolvedDir=str(source.resolved_dir),
                patterns=source.patterns,
                exists=source.resolved_dir.exists(),
                readable=os.access(source.resolved_dir, os.R_OK) if source.resolved_dir.exists() else False,
                matchedFiles=len(files),
                sampleFiles=[str(path) for path in files[:8]],
                lastError=last_error,
                lastSyncedAt=last_synced,
            )
        )
    return rows


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


async def _load_definitions_for_test_ids(
    db: Any,
    *,
    project_id: str,
    test_ids: list[str],
) -> dict[str, dict[str, Any]]:
    unique_ids = sorted({str(test_id).strip() for test_id in test_ids if str(test_id).strip()})
    if not unique_ids:
        return {}

    import aiosqlite

    if isinstance(db, aiosqlite.Connection):
        placeholders = ",".join("?" for _ in unique_ids)
        query = f"""
            SELECT *
            FROM test_definitions
            WHERE project_id = ?
              AND test_id IN ({placeholders})
        """
        params: list[Any] = [project_id, *unique_ids]
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return {
            str(dict(row).get("test_id") or ""): dict(row)
            for row in rows
            if str(dict(row).get("test_id") or "").strip()
        }

    rows = await db.fetch(
        """
        SELECT *
        FROM test_definitions
        WHERE project_id = $1
          AND test_id = ANY($2::text[])
        """,
        project_id,
        unique_ids,
    )
    return {
        str(dict(row).get("test_id") or ""): dict(row)
        for row in rows
        if str(dict(row).get("test_id") or "").strip()
    }


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


async def _load_metric_summary(project_id: str, db: Any) -> TestMetricSummaryDTO:
    by_platform: dict[str, int] = {}
    by_metric_type: dict[str, int] = {}
    latest_collected_at = ""
    total_metrics = 0

    import aiosqlite

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(
            "SELECT COUNT(*) AS count, MAX(collected_at) AS latest FROM test_metrics WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                total_metrics = int(row[0] or 0)
                latest_collected_at = str(row[1] or "")
        async with db.execute(
            "SELECT platform, COUNT(*) AS count FROM test_metrics WHERE project_id = ? GROUP BY platform",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
            by_platform = {str(item[0] or ""): int(item[1] or 0) for item in rows if str(item[0] or "").strip()}
        async with db.execute(
            "SELECT metric_type, COUNT(*) AS count FROM test_metrics WHERE project_id = ? GROUP BY metric_type",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
            by_metric_type = {str(item[0] or ""): int(item[1] or 0) for item in rows if str(item[0] or "").strip()}
    else:
        row = await db.fetchrow(
            "SELECT COUNT(*)::int AS count, MAX(collected_at) AS latest FROM test_metrics WHERE project_id = $1",
            project_id,
        )
        if row:
            total_metrics = int(row.get("count") or 0)
            latest_collected_at = str(row.get("latest") or "")
        rows = await db.fetch(
            "SELECT platform, COUNT(*)::int AS count FROM test_metrics WHERE project_id = $1 GROUP BY platform",
            project_id,
        )
        by_platform = {str(item["platform"] or ""): int(item["count"] or 0) for item in rows if str(item["platform"] or "").strip()}
        rows = await db.fetch(
            "SELECT metric_type, COUNT(*)::int AS count FROM test_metrics WHERE project_id = $1 GROUP BY metric_type",
            project_id,
        )
        by_metric_type = {str(item["metric_type"] or ""): int(item["count"] or 0) for item in rows if str(item["metric_type"] or "").strip()}

    return TestMetricSummaryDTO(
        project_id=project_id,
        total_metrics=total_metrics,
        by_platform=by_platform,
        by_metric_type=by_metric_type,
        latest_collected_at=latest_collected_at,
    )


async def _trigger_mapping_resolution(run_id: str, project_id: str, db: Any) -> None:
    """Background hook for domain mapping resolution."""
    try:
        resolver = MappingResolver(db)
        result = await resolver.resolve_for_run(run_id=run_id, project_id=project_id)
        logger.info(
            "Mapping resolution completed run_id=%s project_id=%s stored=%s primary=%s errors=%s",
            run_id,
            project_id,
            result.stored_count,
            result.primary_count,
            len(result.errors),
        )
    except Exception as exc:
        logger.warning("Mapping resolution failed run_id=%s project_id=%s: %s", run_id, project_id, exc)


async def _trigger_integrity_check(
    run_id: str,
    git_sha: str,
    project_id: str,
    db: Any,
    *,
    enabled: bool,
) -> None:
    """Background hook for integrity signal detection."""
    if not enabled:
        logger.info("Integrity signals disabled; skipping run_id=%s", run_id)
        return
    try:
        detector = IntegrityDetector(db)
        signals = await detector.check_run(run_id=run_id, git_sha=git_sha, project_id=project_id)
        logger.info(
            "Integrity check completed run_id=%s project_id=%s git_sha=%s signals=%s",
            run_id,
            project_id,
            git_sha,
            len(signals),
        )
    except Exception as exc:
        logger.warning(
            "Integrity check failed run_id=%s project_id=%s git_sha=%s: %s",
            run_id,
            project_id,
            git_sha,
            exc,
        )


@test_visualizer_router.get("/config", response_model=TestVisualizerConfigDTO)
async def get_test_config(request: Request, project_id: str | None = None) -> TestVisualizerConfigDTO:
    project = _resolve_project(project_id)
    flags = effective_test_flags(project)
    cfg = project.testConfig
    return TestVisualizerConfigDTO(
        projectId=project.id,
        flags=cfg.flags,
        effectiveFlags=flags,
        autoSyncOnStartup=cfg.autoSyncOnStartup,
        maxFilesPerScan=cfg.maxFilesPerScan,
        maxParseConcurrency=cfg.maxParseConcurrency,
        instructionProfile=cfg.instructionProfile,
        instructionNotes=cfg.instructionNotes,
        parserHealth=parser_health_map(),
        sources=_source_status_rows(project, request),
    )


@test_visualizer_router.get("/sources/status", response_model=list[TestSourceStatusDTO])
async def get_source_status(request: Request, project_id: str | None = None) -> list[TestSourceStatusDTO]:
    project = _resolve_project(project_id)
    return _source_status_rows(project, request)


@test_visualizer_router.post("/sync", response_model=SyncTestsResponse)
async def sync_test_sources_endpoint(request: Request, body: SyncTestsRequest) -> SyncTestsResponse:
    project, flags = _require_feature_enabled(body.project_id)
    if not flags.testVisualizerEnabled:
        raise _error(
            503,
            error="feature_disabled",
            message="Test Visualizer is disabled for this project.",
            hint="Enable Test Visualizer in Project Settings > Testing.",
        )
    sync = getattr(request.app.state, "sync_engine", None)
    if sync is None:
        db = await connection.get_connection()
        from backend.db.sync_engine import SyncEngine
        sync = SyncEngine(db)
    selected = set(body.platforms or [])
    sources = resolve_test_sources(project, platform_filter=selected or None)
    stats = await sync.sync_test_sources(
        project.id,
        sources,
        force=body.force,
        max_files_per_scan=project.testConfig.maxFilesPerScan,
        max_parse_concurrency=project.testConfig.maxParseConcurrency,
    )
    return SyncTestsResponse(project_id=project.id, stats=stats, sources=_source_status_rows(project, request))


@test_visualizer_router.get("/metrics/summary", response_model=TestMetricSummaryDTO)
async def get_metrics_summary(request: Request, project_id: str) -> TestMetricSummaryDTO:
    _ = request
    _require_feature_enabled(project_id)
    db = await connection.get_connection()
    return await _load_metric_summary(project_id, db)


@test_visualizer_router.post("/ingest", response_model=IngestRunResponse)
async def ingest_test_run(request: Request) -> IngestRunResponse:
    """Ingest test results from JSON payload or multipart JUnit XML upload."""
    _require_env_feature_enabled()

    content_type = str(request.headers.get("content-type") or "").lower()
    parser_errors: list[str] = []
    if "multipart/form-data" in content_type:
        payload, parser_errors = await _request_payload_from_multipart(request)
    else:
        payload = await _request_payload_from_json(request)
    _, flags = _require_feature_enabled(payload.project_id)

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

    if flags.integritySignalsEnabled and payload.git_sha:
        try:
            asyncio.create_task(
                _trigger_integrity_check(
                    payload.run_id,
                    payload.git_sha,
                    payload.project_id,
                    db,
                    enabled=flags.integritySignalsEnabled,
                )
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
    _require_feature_enabled(project_id)
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
    _require_feature_enabled(project_id)
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
    _require_env_feature_enabled()
    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)
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
        _require_feature_enabled(str(run.get("project_id") or ""))

        results = await result_repo.get_by_run(run_id)
        project_id = str(run.get("project_id") or "")
        test_ids = [str(row.get("test_id") or "").strip() for row in results]
        definition_rows = await _load_definitions_for_test_ids(
            db,
            project_id=project_id,
            test_ids=test_ids,
        )
        definitions = {
            test_id: _to_test_definition_dto(row)
            for test_id, row in definition_rows.items()
        }

        signals = await integrity_repo.list_by_sha(
            project_id=project_id,
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


@test_visualizer_router.post("/mappings/import")
async def import_mappings(request: Request) -> dict[str, Any]:
    """Import externally generated semantic mappings."""
    _require_env_feature_enabled()

    try:
        body = await request.json()
    except Exception as exc:
        raise _error(
            400,
            error="invalid_body",
            message="Invalid JSON body.",
            hint="Send a JSON object with project_id and mapping_file.",
        ) from exc

    if not isinstance(body, dict):
        raise _error(
            400,
            error="invalid_body",
            message="Body must be a JSON object.",
            hint="Send a JSON object with project_id and mapping_file.",
        )

    project_id = str(body.get("project_id") or "").strip()
    mapping_file = body.get("mapping_file")
    if not project_id:
        raise _error(
            400,
            error="missing_project_id",
            message="project_id is required.",
            hint="Set project_id to the active project identifier.",
        )
    _, flags = _require_feature_enabled(project_id)
    if not flags.semanticMappingEnabled:
        raise _error(
            503,
            error="semantic_mapping_disabled",
            message="Semantic mapping import is disabled for this project.",
            hint="Enable Semantic Mapping in Project Settings > Testing.",
        )
    valid, error = validate_semantic_mapping_file(mapping_file if isinstance(mapping_file, dict) else {})
    if not valid:
        raise _error(
            400,
            error="invalid_mapping_file",
            message=error,
            hint="Provide mapping_file with a mappings array and required fields.",
        )

    db = await connection.get_connection()
    definition_repo = get_test_definition_repository(db)
    definitions: list[dict[str, Any]] = []
    offset = 0
    page_size = 200
    while True:
        page = await definition_repo.list_by_project(project_id=project_id, limit=page_size, offset=offset)
        if not page:
            break
        definitions.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)

    provider = SemanticLLMProvider(mapping_file)
    resolver = MappingResolver(db, providers=[provider])
    with start_span(
        "test_visualizer.import_mappings",
        attributes={"project_id": project_id, "definition_count": len(definitions)},
    ):
        result = await resolver.resolve(
            project_id=project_id,
            test_definitions=definitions,
            context={"source": "import_api", "version": 1},
        )

    return {
        "project_id": project_id,
        "provider": provider.name,
        "stored_count": result.stored_count,
        "primary_count": result.primary_count,
        "candidate_count": result.candidate_count,
        "errors": result.errors,
    }


@test_visualizer_router.post("/mappings/backfill", response_model=BackfillTestMappingsResponse)
async def backfill_mappings(request: Request, body: BackfillTestMappingsRequest) -> BackfillTestMappingsResponse:
    _ = request
    _require_feature_enabled(body.project_id)

    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)
    mapping_repo = get_test_mapping_repository(db)

    runs = await run_repo.list_by_project(project_id=body.project_id, limit=body.run_limit, offset=0)
    resolver = MappingResolver(db)
    runs_processed = 0
    mappings_stored = 0
    primary_mappings = 0
    errors: list[str] = []

    for run in runs:
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            continue
        run_results = await result_repo.get_by_run(run_id)
        if not run_results:
            continue

        test_ids = [str(row.get("test_id") or "").strip() for row in run_results if str(row.get("test_id") or "").strip()]
        existing_primary = 0
        if test_ids:
            for test_id in sorted(set(test_ids)):
                existing_primary += len(await mapping_repo.get_primary_for_test(body.project_id, test_id))
        if existing_primary > 0:
            continue

        result = await resolver.resolve_for_run(run_id=run_id, project_id=body.project_id)
        runs_processed += 1
        mappings_stored += int(result.stored_count or 0)
        primary_mappings += int(result.primary_count or 0)
        errors.extend(result.errors or [])

    return BackfillTestMappingsResponse(
        project_id=body.project_id,
        run_limit=body.run_limit,
        runs_processed=runs_processed,
        mappings_stored=mappings_stored,
        primary_mappings=primary_mappings,
        total_errors=len(errors),
        errors=errors[:100],
    )


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
    _require_feature_enabled(project_id)
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
    _require_feature_enabled(project_id)
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
    _require_feature_enabled(project_id)
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
    _require_feature_enabled(project_id)
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
    _require_feature_enabled(project_id)

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
