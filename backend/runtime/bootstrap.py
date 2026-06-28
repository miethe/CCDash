"""Shared FastAPI app builder for runtime profiles."""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("ccdash.runtime.bootstrap")

from backend.application.context import RequestContext
from backend import config
from backend.db import connection
from backend.db.migration_governance import SUPPORTED_STORAGE_COMPOSITIONS
from backend.routers.ai import ai_router
from backend.routers.analytics import analytics_router
from backend.routers.agent import agent_router
from backend.routers.auth import auth_router
from backend.routers.council import arc_router
from backend.routers.meatywiki import meatywiki_router
from backend.routers.client_v1 import client_v1_router
from backend.routers.ingest import ingest_router
from backend.routers.api import documents_router, sessions_router, tasks_router
from backend.routers.cache import cache_router, links_router
from backend.routers.codebase import codebase_router
from backend.routers.execution import execution_router
from backend.routers.features import features_router
from backend.routers.integrations import github_integrations_router, integrations_router
from backend.routers.live import live_router
from backend.routers.planning import planning_router
from backend.routers.pricing import pricing_router
from backend.routers.projects import projects_router
from backend.routers.observability import observability_router
from backend.routers.session_mappings import session_mappings_router
from backend.routers.telemetry import telemetry_router
from backend.routers.test_visualizer import test_visualizer_router
from backend.runtime.container import RuntimeContainer
from backend.runtime.dependencies import get_request_context
from backend.runtime.profiles import RuntimeProfile, RuntimeProfileName, get_runtime_profile


# ── T9-008: /readyz check helpers ────────────────────────────────────────────
# Module-level async functions so tests can patch them independently.

async def _readyz_check_db() -> tuple[bool, str | None]:
    """Return (ok, error_detail). ok=True if the DB connection is reachable.

    Attempts a lightweight SELECT 1 on the existing singleton connection.
    Returns False (with a detail string) if the connection is absent or the
    query raises an exception.  Never raises.
    """
    try:
        db = connection._connection
        if db is None:
            # Connection not yet established; return not-ready without creating one.
            # A readiness probe must observe state, not change it.
            return False, "db not connected"
        if isinstance(db, aiosqlite.Connection):
            await db.execute("SELECT 1")
        else:
            # asyncpg Pool — acquire and ping
            async with db.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return True, None
    except Exception as exc:
        return False, str(exc)[:200]


async def _readyz_check_migration_head() -> tuple[bool, str | None]:
    """Return (ok, error_detail). ok=True if the migration head version is applied.

    Queries the ``migrations_applied`` ledger table and verifies that the
    current SCHEMA_VERSION row exists.  Returns False with a detail string when
    the row is absent or the query fails.  Never raises.
    """
    try:
        db = connection._connection
        if db is None:
            return False, "db not connected"
        if config.DB_BACKEND == "postgres":
            from backend.db.postgres_migrations import SCHEMA_VERSION
        else:
            from backend.db.sqlite_migrations import SCHEMA_VERSION  # type: ignore[assignment]

        if isinstance(db, aiosqlite.Connection):
            cursor = await db.execute(
                "SELECT COUNT(*) FROM migrations_applied WHERE version = ?",
                (SCHEMA_VERSION,),
            )
            row = await cursor.fetchone()
            applied = bool(row and row[0] >= 1)
        else:
            async with db.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM migrations_applied WHERE version = $1",
                    SCHEMA_VERSION,
                )
                applied = bool(count and count >= 1)
        if applied:
            return True, None
        return False, f"migration head v{SCHEMA_VERSION} not found in migrations_applied"
    except Exception as exc:
        return False, str(exc)[:200]


async def _readyz_check_queue_backend() -> tuple[bool, str | None]:
    """Return (ok, error_detail). ok=True if the queue backend is reachable.

    * Memory backend (JOB_QUEUE_BACKEND=memory): always ok (no external dep).
    * SQLite/Postgres backends: probes the ``job_queue`` table with a cheap
      COUNT(*) query.  Returns False if the connection or query fails.
    Never raises.
    """
    queue_backend = getattr(config, "JOB_QUEUE_BACKEND", "memory").strip().lower()
    if queue_backend == "memory":
        return True, None
    try:
        db = connection._connection
        if db is None:
            return False, "db not connected"
        if isinstance(db, aiosqlite.Connection):
            await db.execute("SELECT 1 FROM job_queue LIMIT 1")
        else:
            async with db.acquire() as conn:
                await conn.fetchval("SELECT COUNT(*) FROM job_queue")
        return True, None
    except Exception as exc:
        return False, str(exc)[:200]


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

    # Dev CORS origins (localhost) are only included when running the local runtime profile
    # or when CCDASH_DEV_CORS=true is explicitly set. Enterprise/api profiles allow only
    # config.FRONTEND_ORIGIN so that hardcoded localhost origins are not present in prod.
    _dev_cors = runtime_profile.name in ("local",) or (
        os.getenv("CCDASH_DEV_CORS", "").strip().lower() in {"1", "true", "yes", "on"}
    )
    _cors_origins = [config.FRONTEND_ORIGIN]
    if _dev_cors:
        _cors_origins += ["http://localhost:3000", "http://127.0.0.1:3000"]
    # T10-003: merge CCDASH_CORS_ALLOWED_ORIGINS (LAN / IntentTree agent origins).
    # Additive only — existing origins are preserved; unset = no change.
    _extra_cors_origins = [
        o.strip()
        for o in getattr(config, "CCDASH_CORS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    # Safety: wildcard origins must not be used with allow_credentials=True — a
    # browser will refuse the response and CORS would silently break for all
    # credentialed callers.  Drop any "*" entries and warn the operator.
    _wildcard_dropped = [o for o in _extra_cors_origins if o == "*"]
    if _wildcard_dropped:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "CCDASH_CORS_ALLOWED_ORIGINS contained wildcard origin(s) ('*') which are "
            "not permitted when allow_credentials=True (browser security requirement). "
            "Wildcard entries were removed from the CORS allow-list.  "
            "Specify explicit origins instead."
        )
        _extra_cors_origins = [o for o in _extra_cors_origins if o != "*"]
    if _extra_cors_origins:
        _cors_origins = _cors_origins + _extra_cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routers(app)

    @app.get("/api/health/live")
    def health_live(
        _: Request,
        _request_context: RequestContext = Depends(get_request_context),
    ) -> JSONResponse:
        runtime_status = container.runtime_status()
        return JSONResponse(
            _build_live_probe_payload(runtime_status),
            status_code=status.HTTP_200_OK,
        )

    @app.get("/api/health/ready")
    def health_ready(
        _: Request,
        _request_context: RequestContext = Depends(get_request_context),
    ) -> JSONResponse:
        runtime_status = container.runtime_status()
        return JSONResponse(
            _build_ready_probe_payload(runtime_status),
            status_code=_probe_response_status_code(runtime_status),
        )

    @app.get("/api/health/detail")
    def health_detail(
        _: Request,
        _request_context: RequestContext = Depends(get_request_context),
    ) -> JSONResponse:
        runtime_status = container.runtime_status()
        return JSONResponse(
            _build_detail_probe_payload(runtime_status),
            status_code=_probe_response_status_code(runtime_status),
        )

    @app.get("/api/health")
    def health(
        _: Request,
        _request_context: RequestContext = Depends(get_request_context),
    ) -> dict[str, Any]:
        runtime_status = container.runtime_status()
        return _build_health_payload(runtime_status, runtime_profile)

    # T9-008: richer /readyz probe for the API runtime.
    # Checks DB connectivity, migration-head-applied, and queue-backend reachability.
    # Returns HTTP 200 only when all three checks pass. Non-200 (503) with a
    # structured reason payload naming the failing dependency on any failure.
    # The check functions are module-level so they can be patched in tests.
    @app.get("/readyz")
    async def readyz_api(resp: Response) -> dict[str, Any]:
        db_ok, db_err = await _readyz_check_db()
        mig_ok, mig_err = await _readyz_check_migration_head()
        queue_ok, queue_err = await _readyz_check_queue_backend()

        checks: dict[str, bool] = {
            "db_connected": db_ok,
            "migration_head_applied": mig_ok,
            "queue_reachable": queue_ok,
        }
        reasons: list[dict[str, str]] = []
        if not db_ok:
            reasons.append({"code": "db_unreachable", "detail": db_err or ""})
        if not mig_ok:
            reasons.append({"code": "migration_behind", "detail": mig_err or ""})
        if not queue_ok:
            reasons.append({"code": "queue_unreachable", "detail": queue_err or ""})

        ready = not reasons
        if not ready:
            resp.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "schemaVersion": "1",
            "runtimeProfile": str(getattr(runtime_profile, "name", "api")),
            "ready": ready,
            "checks": checks,
            "reasons": reasons,
            "reasonCodes": [r["code"] for r in reasons],
        }

    return app


def _build_health_payload(
    runtime_status: dict[str, Any],
    runtime_profile: RuntimeProfile,
) -> dict[str, Any]:
    probe_contract = _require_probe_contract(runtime_status)
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
        "storageComposition": str(runtime_status.get("storageComposition", "")),
        "deploymentMode": str(runtime_status.get("deploymentMode", "")),
        "recommendedStorageProfile": str(runtime_status.get("recommendedStorageProfile", "")),
        "supportedStorageProfiles": list(runtime_status.get("supportedStorageProfiles", ())),
        "filesystemSourceOfTruth": bool(runtime_status.get("filesystemSourceOfTruth", False)),
        "storageFilesystemRole": str(runtime_status.get("storageFilesystemRole", "")),
        "sharedPostgresEnabled": bool(runtime_status.get("sharedPostgresEnabled", False)),
        "storageIsolationMode": str(runtime_status.get("storageIsolationMode", "")),
        "supportedStorageIsolationModes": list(runtime_status.get("supportedStorageIsolationModes", ())),
        "storageCanonicalStore": str(runtime_status.get("storageCanonicalStore", "")),
        "auditStore": str(runtime_status.get("auditStore", "")),
        "auditWriteSupported": bool(runtime_status.get("auditWriteSupported", False)),
        "auditWriteAuthoritative": bool(runtime_status.get("auditWriteAuthoritative", False)),
        "auditWriteStatus": str(runtime_status.get("auditWriteStatus", "")),
        "auditWriteNotes": str(runtime_status.get("auditWriteNotes", "")),
        "sessionEmbeddingWriteSupported": bool(runtime_status.get("sessionEmbeddingWriteSupported", False)),
        "sessionEmbeddingWriteAuthoritative": bool(
            runtime_status.get("sessionEmbeddingWriteAuthoritative", False)
        ),
        "sessionEmbeddingWriteStatus": str(runtime_status.get("sessionEmbeddingWriteStatus", "")),
        "sessionEmbeddingWriteNotes": str(runtime_status.get("sessionEmbeddingWriteNotes", "")),
        "sessionIntelligenceProfile": str(runtime_status.get("sessionIntelligenceProfile", "")),
        "sessionIntelligenceAnalyticsLevel": str(
            runtime_status.get("sessionIntelligenceAnalyticsLevel", "")
        ),
        "sessionIntelligenceBackfillStrategy": str(
            runtime_status.get("sessionIntelligenceBackfillStrategy", "")
        ),
        "sessionIntelligenceMemoryDraftFlow": str(
            runtime_status.get("sessionIntelligenceMemoryDraftFlow", "")
        ),
        "sessionIntelligenceIsolationBoundary": str(
            runtime_status.get("sessionIntelligenceIsolationBoundary", "")
        ),
        "storageSchema": str(runtime_status.get("storageSchema", "")),
        "canonicalSessionStore": str(runtime_status.get("canonicalSessionStore", "")),
        "watchEnabled": bool(runtime_status.get("watchEnabled", False)),
        "syncEnabled": bool(runtime_status.get("syncEnabled", False)),
        "syncProvisioned": bool(runtime_status.get("syncProvisioned", False)),
        "jobsEnabled": bool(runtime_status.get("jobsEnabled", False)),
        "authEnabled": bool(runtime_status.get("authEnabled", False)),
        "authProvider": str(runtime_status.get("authProvider", "")),
        "authProviderConfigured": bool(runtime_status.get("authProviderConfigured", False)),
        "authProviderMissingRequiredVariables": list(
            runtime_status.get("authProviderMissingRequiredVariables", ())
        ),
        "authGuardrail": dict(runtime_status.get("authGuardrail", {})),
        # auth_mode: indicates which auth backend is active for operators to verify
        # post-migration state (ADR-008 §Migration Path, T4-006).
        # "workspace_token" — api/worker profiles using WorkspaceTokenAuthBackend.
        # "single_bearer"   — local profile using StaticBearerTokenIdentityProvider.
        # "test"            — test profile (no real auth; no-op backend).
        "auth_mode": _resolve_auth_mode(runtime_profile),
        "integrationsEnabled": bool(runtime_status.get("integrationsEnabled", False)),
        # Feature surface v2 rollout flag — readable by the FE from /api/health
        # to decide which data path to activate.  Defaults to True (v2 enabled).
        # Set CCDASH_FEATURE_SURFACE_V2_ENABLED=false to fall back to the v0 path.
        "featureSurfaceV2Enabled": config.CCDASH_FEATURE_SURFACE_V2_ENABLED,
        "allowedStorageProfiles": list(runtime_status.get("allowedStorageProfiles", ())),
        # Effective values of runtime-performance feature flags, surfaced to the FE
        # so operators can verify env-var overrides are applied without server logs.
        "runtimePerfDefaults": {
            "queryCacheTtlSeconds": int(config.CCDASH_QUERY_CACHE_TTL_SECONDS),
            "startupDeferredRebuildLinks": bool(config.STARTUP_DEFERRED_REBUILD_LINKS),
            "startupSyncLightMode": bool(config.STARTUP_SYNC_LIGHT_MODE),
            "incrementalLinkRebuildEnabled": bool(config.INCREMENTAL_LINK_REBUILD_ENABLED),
        },
        "runtimeSyncBehavior": str(runtime_status.get("runtimeSyncBehavior", "")),
        "runtimeJobBehavior": str(runtime_status.get("runtimeJobBehavior", "")),
        "runtimeAuthBehavior": str(runtime_status.get("runtimeAuthBehavior", "")),
        "runtimeIntegrationBehavior": str(runtime_status.get("runtimeIntegrationBehavior", "")),
        "environmentContract": dict(runtime_status.get("environmentContract", {})),
        "environmentContractValid": bool(runtime_status.get("environmentContractValid", False)),
        "environmentContractErrors": list(runtime_status.get("environmentContractErrors", ())),
        "environmentContractWarnings": list(runtime_status.get("environmentContractWarnings", ())),
        "environmentContractRequired": list(runtime_status.get("environmentContractRequired", ())),
        "environmentContractSecrets": list(runtime_status.get("environmentContractSecrets", ())),
        "telemetryExports": str(runtime_status.get("telemetryExports", "idle")),
        "requiredStorageGuarantees": list(runtime_status.get("requiredStorageGuarantees", ())),
        "storageProfileValidationMatrix": _serialize_storage_profile_validation_matrix(
            runtime_status.get("storageProfileValidationMatrix", ())
        ),
        "migrationGovernanceStatus": str(runtime_status.get("migrationGovernanceStatus", "")),
        "migrationStatus": str(runtime_status.get("migrationStatus", "")),
        "liveFanout": dict(runtime_status.get("liveFanout", {})),
        "supportedStorageCompositions": [contract.composition for contract in SUPPORTED_STORAGE_COMPOSITIONS],
        "probeContract": probe_contract,
        "probeSchemaVersion": str(probe_contract["schemaVersion"]),
        "probeLiveState": str(probe_contract["live"]["state"]),
        "probeLiveStatus": str(probe_contract["live"]["status"]),
        "probeReadyState": str(probe_contract["ready"]["state"]),
        "probeReadyStatus": str(probe_contract["ready"]["status"]),
        "probeDetailStatus": str(probe_contract["detail"]["status"]),
        "probeReady": bool(probe_contract["ready"]["ready"]),
        "probeDegraded": bool(probe_contract["ready"]["degraded"]),
        "degradedReasons": list(probe_contract["ready"]["reasons"]),
        "degradedReasonCodes": [
            str(reason["code"]) for reason in probe_contract["ready"]["reasons"]
        ],
        "probeDetailWarnings": list(runtime_status.get("probeDetailWarnings", ())),
        "probeDetailWarningCodes": list(runtime_status.get("probeDetailWarningCodes", ())),
    }


def _resolve_auth_mode(runtime_profile: RuntimeProfile) -> str:
    """Return the auth_mode string for the /api/health payload (ADR-008 §Migration Path).

    Values
    ------
    "workspace_token"
        api / worker profiles — WorkspaceTokenAuthBackend is active; tokens are
        validated against the workspace_tokens table using argon2id.
    "single_bearer"
        local profile — StaticBearerTokenIdentityProvider using CCDASH_AUTH_TOKEN.
    "test"
        test profile — no real auth backend; all auth is bypassed in tests.

    Note: the worker profile has ``capabilities.auth=False`` because it does not
    serve HTTP auth requests itself, but it shares the WorkspaceTokenAuthBackend
    for internal token resolution.  We classify it as ``workspace_token`` per the
    ADR-008 operator documentation contract.
    """
    if runtime_profile.name == "test":
        return "test"
    if runtime_profile.name in ("api", "worker", "worker-watch"):
        return "workspace_token"
    return "single_bearer"


# ---------------------------------------------------------------------------
# T2-003: Extended health-detail sub-builders
# Each section is wrapped in its own try/except so a transient failure yields
# null fields rather than a 500.
# ---------------------------------------------------------------------------

def _build_registry_detail() -> dict[str, Any]:
    """Return { project_count, last_flush_status } from the DB-backed project registry.

    last_flush_status derivation:
    - SqliteProjectRepository.count() is called on the configured DB path.
    - If the call succeeds → "ok".
    - If the DB is locked (OperationalError with "locked" in message) → "locked".
    - Any other exception → "failed".
    - If the DB path is not yet available (file missing + table not yet created) → "unknown".
    """
    project_count: int | None = None
    last_flush_status: str = "unknown"
    try:
        from backend.db.repositories.projects import SqliteProjectRepository
        repo = SqliteProjectRepository(db_path=str(config.DB_PATH))
        repo.ensure_table()
        project_count = repo.count()
        last_flush_status = "ok"
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "locked" in msg:
            last_flush_status = "locked"
        else:
            last_flush_status = "failed"
    except RuntimeError as exc:
        # ensure_table() raises RuntimeError when the projects table does not
        # exist (i.e. migrations have not run yet).  This is the documented
        # "table not yet created" → "unknown" path, not a genuine flush failure.
        if "migrations must run" in str(exc).lower() or "does not exist" in str(exc).lower():
            last_flush_status = "unknown"
        else:
            last_flush_status = "failed"
    except Exception:
        last_flush_status = "failed"
    return {
        "project_count": project_count,
        "last_flush_status": last_flush_status,
    }


def _build_db_detail() -> dict[str, Any]:
    """Return { size_bytes, freelist_bytes, backend } for the configured DB.

    For SQLite: reads file size from disk and PRAGMA freelist_count * page_size.
    For PostgreSQL: size_bytes and freelist_bytes are null (not applicable).
    backend is always populated from config.DB_BACKEND.
    """
    backend: str = str(getattr(config, "DB_BACKEND", "sqlite")).lower() or "sqlite"
    size_bytes: int | None = None
    freelist_bytes: int | None = None
    try:
        if backend == "sqlite":
            db_path = config.DB_PATH
            try:
                size_bytes = int(os.path.getsize(str(db_path)))
            except (OSError, TypeError):
                size_bytes = None
            try:
                conn = sqlite3.connect(str(db_path), timeout=5, check_same_thread=False)
                try:
                    conn.execute("PRAGMA busy_timeout = 30000")
                    freelist_count = conn.execute("PRAGMA freelist_count").fetchone()
                    page_size_row = conn.execute("PRAGMA page_size").fetchone()
                    if freelist_count and page_size_row:
                        freelist_bytes = int(freelist_count[0]) * int(page_size_row[0])
                finally:
                    conn.close()
            except Exception:
                freelist_bytes = None
    except Exception:
        size_bytes = None
        freelist_bytes = None
    return {
        "size_bytes": size_bytes,
        "freelist_bytes": freelist_bytes,
        "backend": backend,
    }


def _build_retention_detail(runtime_status: dict[str, Any]) -> dict[str, Any]:
    """Return { last_run, enabled } for the retention job.

    last_run is sourced from the retentionPrune job observation's last_success_at
    field recorded by RuntimeJobAdapter._mark_job_success() in
    backend/adapters/jobs/runtime.py.  It is null if the job has never
    completed successfully.

    enabled reflects config.RETENTION_PRUNE_ENABLED; it is always populated
    even if last_run retrieval fails.
    """
    enabled: bool = bool(getattr(config, "RETENTION_PRUNE_ENABLED", False))
    last_run: str | None = None
    try:
        worker_probe = runtime_status.get("workerProbe")
        if worker_probe:
            jobs = worker_probe.get("jobs", {})
            retention_job = jobs.get("retentionPrune", {})
            last_run = retention_job.get("lastSuccessAt") or None
        else:
            # Non-worker profile: attempt to read from job_observations via
            # the container stored in the runtime_status dict.
            job_obs = runtime_status.get("_job_observations")
            if job_obs and "retentionPrune" in job_obs:
                obs = job_obs["retentionPrune"]
                last_run = getattr(obs, "last_success_at", None)
    except Exception:
        last_run = None
    return {
        "last_run": last_run,
        "enabled": enabled,
    }


def _build_ingest_sources_detail() -> list[dict[str, Any]]:
    """Return per-source ingest health status from ``ingest_cursors``.

    Opens a dedicated synchronous SQLite connection (consistent with the
    ``_build_db_detail()`` pattern) so this helper can remain a plain
    ``def`` like the other health sub-builders.

    For PostgreSQL deployments the shared DB is async-only; we return ``[]``
    gracefully — the caller treats missing rows as a contract state, not an
    error, and the FE falls back to "ingest health unavailable".

    Resilience: any exception → returns ``[]`` (never raises).
    """
    backend: str = str(getattr(config, "DB_BACKEND", "sqlite")).lower() or "sqlite"
    if backend != "sqlite":
        # PostgreSQL detail is not available from a synchronous context here.
        # The transport-neutral get_ingest_sources_health() async function can
        # be called from async endpoints / CLI / MCP directly.
        return []
    try:
        db_path = config.DB_PATH
        conn = sqlite3.connect(str(db_path), timeout=5, check_same_thread=False)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT source_id, project_id, workspace_id, last_cursor, last_ingest_at"
                " FROM ingest_cursors"  # noqa: S608
            ).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        # Table absent (pre-v36 DB), locked, or missing file — return empty
        logger.debug("_build_ingest_sources_detail: query failed", exc_info=True)
        return []

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    fresh_s = float(getattr(config, "CCDASH_INGEST_SOURCE_FRESH_SECONDS", 300))
    stale_s = float(getattr(config, "CCDASH_INGEST_SOURCE_STALE_SECONDS", 900))

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            raw_ts = row["last_ingest_at"]
            lag_seconds: float | None = None
            if raw_ts:
                raw_str = str(raw_ts).strip().rstrip("Z")
                for fmt in (
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                ):
                    try:
                        dt = datetime.strptime(raw_str, fmt).replace(tzinfo=timezone.utc)
                        lag_seconds = (now - dt).total_seconds()
                        break
                    except ValueError:
                        continue

            if lag_seconds is None:
                state = "idle"
            elif lag_seconds < fresh_s:
                state = "connected"
            elif lag_seconds < stale_s:
                state = "backed_up"
            else:
                state = "disconnected"

            results.append({
                "source_id": str(row["source_id"]),
                "project_id": str(row["project_id"]),
                "workspace_id": str(row["workspace_id"]),
                "last_cursor": row["last_cursor"],
                "last_ingest_at": raw_ts,
                "lag_seconds": round(lag_seconds, 3) if lag_seconds is not None else None,
                "state": state,
            })
        except Exception:  # noqa: BLE001
            logger.debug(
                "_build_ingest_sources_detail: failed to parse row; skipping",
                exc_info=True,
            )
    return results


def _build_live_probe_payload(runtime_status: dict[str, Any]) -> dict[str, Any]:
    probe_contract = _require_probe_contract(runtime_status)
    live = _probe_contract_section(probe_contract, "live")
    detail = _probe_contract_section(probe_contract, "detail")
    return {
        "schemaVersion": str(probe_contract["schemaVersion"]),
        "runtimeProfile": str(probe_contract["runtimeProfile"]),
        "state": str(live["state"]),
        "status": str(live["status"]),
        "summary": str(live["summary"]),
        "recommendedCadence": dict(detail.get("recommendedCadence", {})),
    }


def _build_ready_probe_payload(runtime_status: dict[str, Any]) -> dict[str, Any]:
    probe_contract = _require_probe_contract(runtime_status)
    ready = _probe_contract_section(probe_contract, "ready")
    detail = _probe_contract_section(probe_contract, "detail")
    reasons = list(ready.get("reasons", ()))
    return {
        "schemaVersion": str(probe_contract["schemaVersion"]),
        "runtimeProfile": str(probe_contract["runtimeProfile"]),
        "state": str(ready["state"]),
        "status": str(ready["status"]),
        "ready": bool(ready["ready"]),
        "degraded": bool(ready["degraded"]),
        "summary": str(ready["summary"]),
        "recommendedCadence": dict(detail.get("recommendedCadence", {})),
        "requiredReadinessChecks": list(detail.get("requiredReadinessChecks", ())),
        "reasonCodes": [str(reason["code"]) for reason in reasons],
        "reasons": reasons,
        "checks": list(ready.get("checks", ())),
    }


def _build_detail_probe_payload(runtime_status: dict[str, Any]) -> dict[str, Any]:
    probe_contract = _require_probe_contract(runtime_status)
    live = _probe_contract_section(probe_contract, "live")
    ready = _probe_contract_section(probe_contract, "ready")
    detail = _probe_contract_section(probe_contract, "detail")
    reasons = list(ready.get("reasons", ()))
    return {
        "schemaVersion": str(probe_contract["schemaVersion"]),
        "runtimeProfile": str(probe_contract["runtimeProfile"]),
        "live": dict(live),
        "ready": {
            "state": str(ready["state"]),
            "status": str(ready["status"]),
            "ready": bool(ready["ready"]),
            "degraded": bool(ready["degraded"]),
            "summary": str(ready["summary"]),
            "reasonCodes": [str(reason["code"]) for reason in reasons],
            "reasons": reasons,
        },
        "detail": {
            "state": str(detail["state"]),
            "status": str(detail["status"]),
            "summary": str(detail["summary"]),
            "recommendedCadence": dict(detail.get("recommendedCadence", {})),
            "requiredReadinessChecks": list(detail.get("requiredReadinessChecks", ())),
            "runtime": dict(detail.get("runtime", {})),
            "storage": dict(detail.get("storage", {})),
            "database": dict(detail.get("database", {})),
            "environment": dict(detail.get("environment", {})),
            "auth": dict(detail.get("auth", {})),
            "warningCodes": list(detail.get("warningCodes", ())),
            "warnings": list(detail.get("warnings", ())),
            "binding": dict(detail.get("binding", {})),
            "activities": dict(detail.get("activities", {})),
            "watcher": dict(detail.get("watcher", {})),
            "liveFanout": dict(detail.get("liveFanout", {})),
            "checks": list(detail.get("checks", ())),
        },
        # Feature-surface v2 rollout flag exposed at the detail level so the FE
        # can read it from the same /api/health/detail probe it already polls.
        "featureSurfaceV2Enabled": config.CCDASH_FEATURE_SURFACE_V2_ENABLED,
        # T2-003: extended health detail fields — reuse sub-builders, no duplication
        "registry": _build_registry_detail(),
        "db": _build_db_detail(),
        "retention": _build_retention_detail(runtime_status),
        # Phase 6: ingest-source health rollup (additive, resilient — never raises)
        "ingest_sources": _build_ingest_sources_detail(),
    }


def _probe_response_status_code(runtime_status: dict[str, Any]) -> int:
    probe_contract = _require_probe_contract(runtime_status)
    ready = _probe_contract_section(probe_contract, "ready")
    return (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if str(ready["status"]) == "fail"
        else status.HTTP_200_OK
    )


def _require_probe_contract(runtime_status: dict[str, Any]) -> dict[str, Any]:
    probe_contract = runtime_status.get("probeContract")
    if not isinstance(probe_contract, dict):
        raise RuntimeError("Runtime status is missing probeContract metadata.")
    return probe_contract


def _probe_contract_section(probe_contract: dict[str, Any], section: str) -> dict[str, Any]:
    value = probe_contract.get(section)
    if not isinstance(value, dict):
        raise RuntimeError(f"Probe contract section '{section}' is unavailable.")
    return value


def _serialize_storage_profile_validation_matrix(entries: object) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for row in entries if isinstance(entries, (list, tuple)) else ():
        entry = dict(row)
        entry["supportedStorageIsolationModes"] = list(entry.get("supportedStorageIsolationModes", ()))
        entry["requiredStorageGuarantees"] = list(entry.get("requiredStorageGuarantees", ()))
        matrix.append(entry)
    return matrix


def _register_routers(app: FastAPI) -> None:
    app.include_router(ai_router)
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(documents_router)
    app.include_router(tasks_router)
    app.include_router(analytics_router)
    app.include_router(agent_router)
    app.include_router(planning_router)
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
    app.include_router(observability_router)
    app.include_router(client_v1_router)
    app.include_router(ingest_router)
    app.include_router(arc_router)
    app.include_router(meatywiki_router)
