"""Shared FastAPI app builder for runtime profiles."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.application.context import RequestContext
from backend import config
from backend.db import connection
from backend.db.migration_governance import SUPPORTED_STORAGE_COMPOSITIONS
from backend.routers.analytics import analytics_router
from backend.routers.api import documents_router, sessions_router, tasks_router
from backend.routers.cache import cache_router, links_router
from backend.routers.codebase import codebase_router
from backend.routers.execution import execution_router
from backend.routers.features import features_router
from backend.routers.integrations import github_integrations_router, integrations_router
from backend.routers.live import live_router
from backend.routers.pricing import pricing_router
from backend.routers.projects import projects_router
from backend.routers.session_mappings import session_mappings_router
from backend.routers.telemetry import telemetry_router
from backend.routers.test_visualizer import test_visualizer_router
from backend.runtime.container import RuntimeContainer
from backend.runtime.dependencies import get_request_context
from backend.runtime.profiles import RuntimeProfile, RuntimeProfileName, get_runtime_profile


def build_runtime_app(profile: RuntimeProfile | RuntimeProfileName) -> FastAPI:
    runtime_profile = get_runtime_profile(profile) if isinstance(profile, str) else profile
    container = RuntimeContainer(profile=runtime_profile)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await container.startup(app)
        yield
        await container.shutdown(app)

    app = FastAPI(
        title="CCDash API",
        description="Backend API for the CCDash agentic analytics dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.runtime_profile = runtime_profile
    app.state.runtime_container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            config.FRONTEND_ORIGIN,
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routers(app)

    @app.get("/api/health")
    def health(
        _: Request,
        _request_context: RequestContext = Depends(get_request_context),
    ) -> dict[str, Any]:
        runtime_status = container.runtime_status()
        return {
            "status": "ok",
            "db": "connected" if connection._connection else "disconnected",
            "watcher": str(runtime_status.get("watcher", "unknown")),
            "profile": str(runtime_status.get("profile", runtime_profile.name)),
            "startupSync": str(runtime_status.get("startupSync", "idle")),
            "analyticsSnapshots": str(runtime_status.get("analyticsSnapshots", "idle")),
            "storageMode": str(runtime_status.get("storageMode", "")),
            "storageProfile": str(runtime_status.get("storageProfile", "")),
            "storageBackend": str(runtime_status.get("storageBackend", "")),
            "recommendedStorageProfile": str(runtime_status.get("recommendedStorageProfile", "")),
            "supportedStorageProfiles": list(runtime_status.get("supportedStorageProfiles", ())),
            "filesystemSourceOfTruth": bool(runtime_status.get("filesystemSourceOfTruth", False)),
            "sharedPostgresEnabled": bool(runtime_status.get("sharedPostgresEnabled", False)),
            "storageIsolationMode": str(runtime_status.get("storageIsolationMode", "")),
            "supportedStorageIsolationModes": list(runtime_status.get("supportedStorageIsolationModes", ())),
            "storageCanonicalStore": str(runtime_status.get("storageCanonicalStore", "")),
            "storageSchema": str(runtime_status.get("storageSchema", "")),
            "canonicalSessionStore": str(runtime_status.get("canonicalSessionStore", "")),
            "watchEnabled": bool(runtime_status.get("watchEnabled", False)),
            "syncEnabled": bool(runtime_status.get("syncEnabled", False)),
            "syncProvisioned": bool(runtime_status.get("syncProvisioned", False)),
            "jobsEnabled": bool(runtime_status.get("jobsEnabled", False)),
            "telemetryExports": str(runtime_status.get("telemetryExports", "idle")),
            "requiredStorageGuarantees": list(runtime_status.get("requiredStorageGuarantees", ())),
            "supportedStorageCompositions": [contract.composition for contract in SUPPORTED_STORAGE_COMPOSITIONS],
        }

    return app


def _register_routers(app: FastAPI) -> None:
    app.include_router(sessions_router)
    app.include_router(documents_router)
    app.include_router(tasks_router)
    app.include_router(analytics_router)
    app.include_router(projects_router)
    app.include_router(features_router)
    app.include_router(cache_router)
    app.include_router(links_router)
    app.include_router(session_mappings_router)
    app.include_router(codebase_router)
    app.include_router(test_visualizer_router)
    app.include_router(execution_router)
    app.include_router(live_router)
    app.include_router(integrations_router)
    app.include_router(github_integrations_router)
    app.include_router(telemetry_router)
    app.include_router(pricing_router)
