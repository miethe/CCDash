"""Telemetry export status and control endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.application.context import RequestContext
from backend.models import PushNowResponse, TelemetryExportSettingsUpdateRequest, TelemetryExportStatusResponse
from backend.request_scope import get_request_context
from backend.services.integrations.telemetry_exporter import TelemetryExportBusyError, TelemetryExportCoordinator
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore

telemetry_router = APIRouter(prefix="/api/telemetry/export", tags=["telemetry"])


def _exporter_from_request(request: Request) -> TelemetryExportCoordinator:
    exporter = getattr(request.app.state, "telemetry_exporter", None)
    if not isinstance(exporter, TelemetryExportCoordinator):
        raise HTTPException(status_code=500, detail="Telemetry exporter is unavailable")
    return exporter


def _settings_store_from_request(request: Request) -> TelemetrySettingsStore:
    store = getattr(request.app.state, "telemetry_settings_store", None)
    if not isinstance(store, TelemetrySettingsStore):
        raise HTTPException(status_code=500, detail="Telemetry settings store is unavailable")
    return store


@telemetry_router.get("/status", response_model=TelemetryExportStatusResponse)
async def get_telemetry_export_status(
    request: Request,
    _: RequestContext = Depends(get_request_context),
) -> TelemetryExportStatusResponse:
    exporter = _exporter_from_request(request)
    return await exporter.status()


@telemetry_router.patch("/settings", response_model=TelemetryExportStatusResponse)
async def update_telemetry_export_settings(
    req: TelemetryExportSettingsUpdateRequest,
    request: Request,
    _: RequestContext = Depends(get_request_context),
) -> TelemetryExportStatusResponse:
    exporter = _exporter_from_request(request)
    if not exporter.runtime_config.enabled:
        raise HTTPException(status_code=400, detail="Telemetry exporter is disabled by environment configuration")
    store = _settings_store_from_request(request)
    store.save(req)
    return await exporter.status()


@telemetry_router.post("/push-now", response_model=PushNowResponse)
async def push_telemetry_now(
    request: Request,
    _: RequestContext = Depends(get_request_context),
) -> PushNowResponse:
    exporter = _exporter_from_request(request)
    status = await exporter.status()
    if not status.configured:
        raise HTTPException(status_code=400, detail="Telemetry exporter is not configured")
    if not status.enabled:
        raise HTTPException(status_code=400, detail="Telemetry exporter is disabled")
    try:
        outcome = await exporter.execute(trigger="manual", raise_on_busy=True)
    except TelemetryExportBusyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return outcome.to_push_now_response()
