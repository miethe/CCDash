"""Test Visualizer API router."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend import config
from backend.application.live_updates.domain_events import publish_test_invalidation
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
    MappingResolverDetailResponseDTO,
    MappingResolverRunDetailDTO,
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
    RunResultPageDTO,
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
_MAPPING_BACKFILL_OPERATION_KIND = "test_mapping_backfill"


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
    project_root = project_manager.get_project_root(project)
    sources = resolve_test_sources(project, include_disabled=True, project_root=project_root)
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


async def _prune_unmapped_leaf_domains(db: Any, project_id: str) -> int:
    """Remove leaf domains that have no mapped primary tests."""
    normalized_project = str(project_id or "").strip()
    if not normalized_project:
        return 0

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(
            """
            SELECT d.domain_id
            FROM test_domains d
            LEFT JOIN test_feature_mappings m
              ON m.project_id = d.project_id
             AND m.domain_id = d.domain_id
            LEFT JOIN test_domains child
              ON child.project_id = d.project_id
             AND child.parent_id = d.domain_id
            WHERE d.project_id = ?
            GROUP BY d.domain_id
            HAVING COUNT(m.mapping_id) = 0 AND COUNT(child.domain_id) = 0
            """,
            (normalized_project,),
        ) as cur:
            leaf_ids = [str(row[0]) for row in await cur.fetchall() if str(row[0]).strip()]
        if not leaf_ids:
            return 0
        for domain_id in leaf_ids:
            await db.execute(
                "DELETE FROM test_domains WHERE project_id = ? AND domain_id = ?",
                (normalized_project, domain_id),
            )
        await db.commit()
        return len(leaf_ids)

    rows = await db.fetch(
        """
        SELECT d.domain_id
        FROM test_domains d
        LEFT JOIN test_feature_mappings m
          ON m.project_id = d.project_id
         AND m.domain_id = d.domain_id
        LEFT JOIN test_domains child
          ON child.project_id = d.project_id
         AND child.parent_id = d.domain_id
        WHERE d.project_id = $1
        GROUP BY d.domain_id
        HAVING COUNT(m.mapping_id) = 0 AND COUNT(child.domain_id) = 0
        """,
        normalized_project,
    )
    leaf_ids = [str(row.get("domain_id") or "").strip() for row in rows if str(row.get("domain_id") or "").strip()]
    if not leaf_ids:
        return 0
    for domain_id in leaf_ids:
        await db.execute(
            "DELETE FROM test_domains WHERE project_id = $1 AND domain_id = $2",
            normalized_project,
            domain_id,
        )
    return len(leaf_ids)


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
        git_sha=str(run_row.get("git_sha") or row.get("run_git_sha") or row.get("git_sha") or ""),
        agent_session_id=str(
            run_row.get("agent_session_id")
            or row.get("run_agent_session_id")
            or row.get("agent_session_id")
            or ""
        ),
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


def _backfill_stats_payload(payload: BackfillTestMappingsResponse) -> dict[str, Any]:
    data = payload.model_dump()
    # Include camelCase aliases for easier frontend consumption from generic operation snapshots.
    data["runLimit"] = int(data.get("run_limit") or 0)
    data["runsProcessed"] = int(data.get("runs_processed") or 0)
    data["testsConsidered"] = int(data.get("tests_considered") or 0)
    data["testsResolved"] = int(data.get("tests_resolved") or 0)
    data["testsReusedCached"] = int(data.get("tests_reused_cached") or 0)
    data["mappingsStored"] = int(data.get("mappings_stored") or 0)
    data["primaryMappings"] = int(data.get("primary_mappings") or 0)
    data["resolverVersion"] = str(data.get("resolver_version") or "")
    data["totalErrors"] = int(data.get("total_errors") or 0)
    return data


def _backfill_completion_message(payload: BackfillTestMappingsResponse) -> str:
    return (
        f"Backfill completed: processed {int(payload.runs_processed)} runs, "
        f"stored {int(payload.mappings_stored)} mappings "
        f"({int(payload.primary_mappings)} primary, {int(payload.total_errors)} errors)"
    )


async def _execute_backfill_mappings(
    body: BackfillTestMappingsRequest,
    *,
    sync_engine: Any | None = None,
    operation_id: str | None = None,
) -> BackfillTestMappingsResponse:
    _require_feature_enabled(body.project_id)

    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    definition_repo = get_test_definition_repository(db)
    result_repo = get_test_result_repository(db)

    if sync_engine and operation_id:
        await sync_engine.update_operation(
            operation_id,
            phase="load_runs",
            message="Loading recent test runs",
            progress={"percent": 2, "runsScanned": 0, "runsTotal": 0, "runsProcessed": 0},
            counters={"runLimit": int(body.run_limit)},
        )

    runs = await run_repo.list_by_project(project_id=body.project_id, limit=body.run_limit, offset=0)
    resolver = MappingResolver(db, provider_sources=body.provider_sources or None)
    runs_processed = 0
    definitions: dict[str, dict[str, Any]] = {}
    total_runs = len(runs)

    if sync_engine and operation_id:
        await sync_engine.update_operation(
            operation_id,
            phase="collect_definitions",
            message=f"Collecting test definitions from {total_runs} runs",
            progress={"percent": 8, "runsScanned": 0, "runsTotal": total_runs, "runsProcessed": 0},
            counters={"runLimit": int(body.run_limit), "runsTotal": total_runs, "definitionsCollected": 0},
        )

    for index, run in enumerate(runs, start=1):
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            continue
        run_results = await result_repo.get_by_run(run_id)
        if not run_results:
            continue
        runs_processed += 1

        for row in run_results:
            test_id = str(row.get("test_id") or "").strip()
            if not test_id or test_id in definitions:
                continue
            definition = await definition_repo.get_by_id(test_id)
            if definition is not None:
                definitions[test_id] = definition
                continue
            definitions[test_id] = {
                "test_id": test_id,
                "project_id": body.project_id,
                "path": str(row.get("path") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "framework": str(row.get("framework") or "pytest").strip() or "pytest",
                "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
                "owner": str(row.get("owner") or "").strip(),
            }

        if sync_engine and operation_id and (
            index == total_runs
            or index == 1
            or index % max(1, total_runs // 20) == 0
        ):
            collect_pct = 8 + int((index / max(1, total_runs)) * 52)
            await sync_engine.update_operation(
                operation_id,
                phase="collect_definitions",
                message=f"Analyzing runs ({index}/{total_runs})",
                progress={
                    "percent": min(60, collect_pct),
                    "runsScanned": index,
                    "runsTotal": total_runs,
                    "runsProcessed": runs_processed,
                },
                counters={
                    "runsTotal": total_runs,
                    "runsProcessed": runs_processed,
                    "definitionsCollected": len(definitions),
                },
            )

    if sync_engine and operation_id:
        await sync_engine.update_operation(
            operation_id,
            phase="resolve_mappings",
            message=f"Resolving mappings for {len(definitions)} tests",
            progress={
                "percent": 70,
                "runsScanned": total_runs,
                "runsTotal": total_runs,
                "runsProcessed": runs_processed,
            },
            counters={
                "runsTotal": total_runs,
                "runsProcessed": runs_processed,
                "definitionsCollected": len(definitions),
            },
        )

    result = await resolver.resolve(
        project_id=body.project_id,
        test_definitions=list(definitions.values()),
        context={
            "version": 2,
            "source": str(body.source or "backfill_api").strip() or "backfill_api",
            "force_recompute": bool(body.force_recompute),
            "project_root": str(config.CCDASH_PROJECT_ROOT or "").strip(),
        },
    )
    cache_state = dict(result.cache_state or {})
    cache_state["runs_processed"] = runs_processed
    cache_state["run_limit"] = body.run_limit
    if body.provider_sources:
        cache_state["provider_sources"] = [str(source).strip() for source in body.provider_sources if str(source).strip()]
    cache_state["pruned_unmapped_leaf_domains"] = await _prune_unmapped_leaf_domains(db, body.project_id)

    payload = BackfillTestMappingsResponse(
        project_id=body.project_id,
        run_limit=body.run_limit,
        runs_processed=runs_processed,
        tests_considered=result.tests_considered,
        tests_resolved=result.tests_resolved,
        tests_reused_cached=result.tests_reused_cached,
        mappings_stored=result.stored_count,
        primary_mappings=result.primary_count,
        resolver_version=result.resolver_version,
        cache_state=cache_state,
        total_errors=len(result.errors),
        errors=result.errors[:100],
    )

    if sync_engine and operation_id:
        await sync_engine.update_operation(
            operation_id,
            phase="finalizing",
            message="Finalizing mapping backfill",
            progress={
                "percent": 95,
                "runsScanned": total_runs,
                "runsTotal": total_runs,
                "runsProcessed": runs_processed,
            },
            counters={
                "runsTotal": total_runs,
                "runsProcessed": runs_processed,
                "definitionsCollected": len(definitions),
                "testsResolved": int(payload.tests_resolved),
                "mappingsStored": int(payload.mappings_stored),
            },
            stats=_backfill_stats_payload(payload),
        )

    return payload


async def _run_backfill_mappings_background(
    body: BackfillTestMappingsRequest,
    sync_engine: Any,
    operation_id: str,
) -> None:
    try:
        payload = await _execute_backfill_mappings(
            body,
            sync_engine=sync_engine,
            operation_id=operation_id,
        )
        stats = _backfill_stats_payload(payload)
        await sync_engine.update_operation(
            operation_id,
            phase="completed",
            message=_backfill_completion_message(payload),
            progress={"percent": 100},
            stats=stats,
        )
        await sync_engine.finish_operation(
            operation_id,
            status="completed",
            stats=stats,
        )
        await publish_test_invalidation(
            body.project_id,
            reason="mapping_backfill_completed",
            source="tests_api",
            payload={
                "operationId": operation_id,
                "runsProcessed": int(payload.runs_processed),
                "mappingsStored": int(payload.mappings_stored),
            },
        )
    except Exception as exc:
        error = str(exc) or "Unknown mapping backfill failure"
        logger.exception("Background mapping backfill failed operation_id=%s: %s", operation_id, error)
        try:
            await sync_engine.update_operation(
                operation_id,
                phase="failed",
                message=f"Mapping backfill failed: {error}",
                progress={"percent": 100},
            )
            await sync_engine.finish_operation(
                operation_id,
                status="failed",
                error=error,
            )
            await publish_test_invalidation(
                body.project_id,
                reason="mapping_backfill_failed",
                source="tests_api",
                payload={"operationId": operation_id, "error": error},
            )
        except Exception:
            logger.exception("Failed to finalize mapping backfill operation state operation_id=%s", operation_id)


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
    project_root = project_manager.get_project_root(project)
    sources = resolve_test_sources(project, platform_filter=selected or None, project_root=project_root)
    stats = await sync.sync_test_sources(
        project.id,
        sources,
        force=body.force,
        max_files_per_scan=project.testConfig.maxFilesPerScan,
        max_parse_concurrency=project.testConfig.maxParseConcurrency,
    )
    await publish_test_invalidation(
        project.id,
        reason="sync_test_sources",
        source="tests_api",
        payload={"stats": stats},
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

    updated_response = response.model_copy(
        update={
            "mapping_trigger_queued": mapping_queued,
            "integrity_check_queued": integrity_queued,
            "errors": errors,
        }
    )
    await publish_test_invalidation(
        payload.project_id,
        reason="ingest_run",
        source="tests_api",
        payload={
            "runId": payload.run_id,
            "mappingQueued": mapping_queued,
            "integrityQueued": integrity_queued,
            "status": response.status,
        },
    )
    return updated_response


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
            offset=offset,
            limit=limit,
        )
        next_offset = offset + len(items)
        next_cursor = _encode_cursor(next_offset) if next_offset < total else None
        if span is not None:
            span.set_attribute("result_count", len(items))
            span.set_attribute("total_count", total)
            span.set_attribute("query_mode", "db_native")

    return CursorPaginatedResponse[FeatureTestHealthDTO](
        items=items,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@test_visualizer_router.get("/runs/{run_id}", response_model=TestRunDetailDTO)
async def get_run_detail(
    request: Request,
    run_id: str,
    project_id: str | None = None,
    include_results: bool = True,
) -> TestRunDetailDTO:
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
        resolved_project_id = str(run.get("project_id") or "")
        if project_id and project_id != resolved_project_id:
            raise _error(
                404,
                error="run_not_found",
                message=f"No run found with id={run_id} for project_id={project_id}",
                hint="Check project_id is correct for the selected run.",
            )

        _require_feature_enabled(resolved_project_id)

        results: list[dict[str, Any]] = []
        definitions: dict[str, TestDefinitionDTO] = {}
        if include_results:
            results = await result_repo.get_by_run(run_id)
            test_ids = [str(row.get("test_id") or "").strip() for row in results]
            definition_rows = await _load_definitions_for_test_ids(
                db,
                project_id=resolved_project_id,
                test_ids=test_ids,
            )
            definitions = {
                test_id: _to_test_definition_dto(row)
                for test_id, row in definition_rows.items()
            }

        signals = await integrity_repo.list_by_sha(
            project_id=resolved_project_id,
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


@test_visualizer_router.get("/runs/{run_id}/results", response_model=RunResultPageDTO)
async def list_run_results(
    request: Request,
    run_id: str,
    project_id: str | None = None,
    domain_id: str | None = None,
    statuses: str | None = None,
    query: str | None = None,
    sort_by: str = Query("status", pattern="^(status|duration|name|test_id)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> RunResultPageDTO:
    _ = request
    _require_env_feature_enabled()
    cursor_data = _decode_cursor(cursor)
    offset = int(cursor_data.get("offset", 0))

    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)

    with start_span(
        "test_visualizer.list_run_results",
        attributes={
            "run_id": run_id,
            "project_id": project_id or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    ) as span:
        run = await run_repo.get_by_id(run_id)
        if run is None:
            raise _error(
                404,
                error="run_not_found",
                message=f"No run found with id={run_id}",
                hint="Check run_id is correct and was ingested successfully.",
            )

        resolved_project_id = str(run.get("project_id") or "")
        if project_id and project_id != resolved_project_id:
            raise _error(
                404,
                error="run_not_found",
                message=f"No run found with id={run_id} for project_id={project_id}",
                hint="Check project_id is correct for the selected run.",
            )
        _require_feature_enabled(resolved_project_id)

        status_tokens = [
            token.strip().lower()
            for token in str(statuses or "").split(",")
            if token.strip()
        ]
        rows, total = await result_repo.list_by_run_filtered(
            run_id,
            domain_id=domain_id,
            statuses=status_tokens or None,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
        next_offset = offset + len(rows)
        next_cursor = _encode_cursor(next_offset) if next_offset < total else None

        definition_rows = await _load_definitions_for_test_ids(
            db,
            project_id=resolved_project_id,
            test_ids=[str(row.get("test_id") or "").strip() for row in rows],
        )
        definitions = {
            test_id: _to_test_definition_dto(row)
            for test_id, row in definition_rows.items()
        }

        if span is not None:
            span.set_attribute("result_count", len(rows))
            span.set_attribute("total_count", total)

    return RunResultPageDTO(
        items=[_to_test_result_dto(row) for row in rows],
        total=total,
        limit=limit,
        next_cursor=next_cursor,
        definitions=definitions,
    )


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
            context={"source": "import_api", "version": 2, "force_recompute": True},
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
    return await _execute_backfill_mappings(body)


@test_visualizer_router.post("/mappings/backfill/start")
async def start_backfill_mappings(
    request: Request,
    background_tasks: BackgroundTasks,
    body: BackfillTestMappingsRequest,
) -> dict[str, Any]:
    _require_feature_enabled(body.project_id)
    app_state = getattr(getattr(request, "app", None), "state", None)
    sync_engine = getattr(app_state, "sync_engine", None)
    if sync_engine is None:
        raise _error(
            503,
            error="sync_engine_unavailable",
            message="Background operations are unavailable.",
            hint="Ensure CCDash backend sync engine is initialized.",
        )

    operation_id = await sync_engine.start_operation(
        _MAPPING_BACKFILL_OPERATION_KIND,
        body.project_id,
        trigger="tests-api",
        metadata={
            "runLimit": int(body.run_limit),
            "forceRecompute": bool(body.force_recompute),
            "providerSources": [str(source).strip() for source in body.provider_sources if str(source).strip()],
            "source": str(body.source or "backfill").strip() or "backfill",
        },
    )
    await sync_engine.update_operation(
        operation_id,
        phase="queued",
        message="Mapping backfill queued",
        progress={"percent": 0, "runsScanned": 0, "runsTotal": 0, "runsProcessed": 0},
        counters={"runLimit": int(body.run_limit)},
    )
    await publish_test_invalidation(
        body.project_id,
        reason="mapping_backfill_started",
        source="tests_api",
        payload={"operationId": operation_id, "runLimit": int(body.run_limit)},
    )
    background_tasks.add_task(_run_backfill_mappings_background, body, sync_engine, operation_id)
    return {
        "status": "ok",
        "mode": "background",
        "message": "Mapping backfill started in background",
        "operationId": operation_id,
    }


@test_visualizer_router.get("/mappings/resolver-detail", response_model=MappingResolverDetailResponseDTO)
async def mapping_resolver_detail(
    request: Request,
    project_id: str,
    run_limit: int = Query(30, ge=1, le=500),
) -> MappingResolverDetailResponseDTO:
    _ = request
    _require_feature_enabled(project_id)

    db = await connection.get_connection()
    run_repo = get_test_run_repository(db)
    result_repo = get_test_result_repository(db)
    mapping_repo = get_test_mapping_repository(db)

    runs = await run_repo.list_by_project(project_id=project_id, limit=run_limit, offset=0)
    detail_rows: list[MappingResolverRunDetailDTO] = []

    for run in runs:
        run_id = str(run.get("run_id") or "").strip()
        results = await result_repo.get_by_run(run_id) if run_id else []
        test_ids = sorted({str(row.get("test_id") or "").strip() for row in results if str(row.get("test_id") or "").strip()})

        mapped_primary = 0
        for test_id in test_ids:
            primary = await mapping_repo.get_primary_for_test(project_id, test_id)
            if primary:
                mapped_primary += 1

        total_results = len(test_ids)
        unmapped = max(0, total_results - mapped_primary)
        coverage = round((mapped_primary / total_results), 4) if total_results > 0 else 0.0

        detail_rows.append(
            MappingResolverRunDetailDTO(
                run_id=run_id,
                timestamp=str(run.get("timestamp") or ""),
                branch=str(run.get("branch") or ""),
                git_sha=str(run.get("git_sha") or ""),
                agent_session_id=str(run.get("agent_session_id") or ""),
                total_results=total_results,
                mapped_primary_tests=mapped_primary,
                unmapped_tests=unmapped,
                coverage=coverage,
            )
        )

    return MappingResolverDetailResponseDTO(
        project_id=project_id,
        run_limit=run_limit,
        generated_at=datetime.now(timezone.utc).isoformat(),
        runs=detail_rows,
    )


@test_visualizer_router.get("/runs", response_model=CursorPaginatedResponse[TestRunDTO])
async def list_runs(
    request: Request,
    project_id: str,
    agent_session_id: str | None = None,
    feature_id: str | None = None,
    domain_id: str | None = None,
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

    with start_span(
        "test_visualizer.list_runs",
        attributes={"project_id": project_id, "feature_id": feature_id or "", "session_id": agent_session_id or ""},
    ) as span:
        rows, total = await run_repo.list_filtered(
            project_id=project_id,
            agent_session_id=agent_session_id,
            feature_id=feature_id,
            domain_id=domain_id,
            git_sha=git_sha,
            since=since,
            limit=limit,
            offset=offset,
        )
        next_offset = offset + len(rows)
        next_cursor = _encode_cursor(next_offset) if next_offset < total else None
        items = [_to_test_run_dto(row) for row in rows]
        if span is not None:
            span.set_attribute("result_count", len(items))
            span.set_attribute("total_count", total)
            span.set_attribute("query_mode", "db_native")

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

    with start_span(
        "test_visualizer.get_test_history",
        attributes={"project_id": project_id, "test_id": test_id, "since": since or ""},
    ) as span:
        rows, total = await result_repo.list_history_for_test(
            project_id=project_id,
            test_id=test_id,
            since=since,
            limit=limit,
            offset=offset,
        )
        next_offset = offset + len(rows)
        next_cursor = _encode_cursor(next_offset) if next_offset < total else None
        items = [_to_test_history_dto(row, None) for row in rows]
        if span is not None:
            span.set_attribute("result_count", len(items))
            span.set_attribute("total_count", total)
            span.set_attribute("query_mode", "db_native")

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
        rows, total = await integrity_repo.list_filtered(
            project_id=project_id,
            since=since,
            signal_type=signal_type,
            severity=severity,
            agent_session_id=agent_session_id,
            limit=limit,
            offset=offset,
        )
        next_offset = offset + len(rows)
        next_cursor = _encode_cursor(next_offset) if next_offset < total else None
        items = [_to_test_signal_dto(row) for row in rows]
        if span is not None:
            span.set_attribute("result_count", len(items))
            span.set_attribute("total_count", total)
            span.set_attribute("query_mode", "db_native")

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
