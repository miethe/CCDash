"""Test Visualizer API router (Phase 2 ingestion surface)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend import config
from backend.db import connection
from backend.models import IngestRunRequest, IngestRunResponse
from backend.parsers.test_results import parse_junit_xml
from backend.project_manager import project_manager
from backend.services.test_ingest import ingest_run


logger = logging.getLogger("ccdash.test_visualizer")
test_visualizer_router = APIRouter(prefix="/api/tests", tags=["test-visualizer"])


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
    if not config.CCDASH_TEST_VISUALIZER_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Test Visualizer is disabled. Set CCDASH_TEST_VISUALIZER_ENABLED=true.",
        )

    content_type = str(request.headers.get("content-type") or "").lower()
    parser_errors: list[str] = []
    if "multipart/form-data" in content_type:
        payload, parser_errors = await _request_payload_from_multipart(request)
    else:
        payload = await _request_payload_from_json(request)

    db = await connection.get_connection()
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

