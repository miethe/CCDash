"""Worker runtime bootstrap."""
from __future__ import annotations

import os
from typing import Any, cast

from fastapi import FastAPI, Response

from backend import config
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import RuntimeProfileName, get_runtime_profile


WORKER_RUNTIME_PROFILES: tuple[RuntimeProfileName, ...] = ("worker", "worker-watch")


def build_worker_runtime() -> RuntimeContainer:
    return RuntimeContainer(profile=get_runtime_profile(resolve_worker_runtime_profile()))


def resolve_worker_runtime_profile() -> RuntimeProfileName:
    requested_profile = os.getenv(config.CCDASH_RUNTIME_PROFILE_ENV, "worker").strip() or "worker"
    if requested_profile not in WORKER_RUNTIME_PROFILES:
        allowed = ", ".join(WORKER_RUNTIME_PROFILES)
        raise RuntimeError(
            f"{config.CCDASH_RUNTIME_PROFILE_ENV} must be one of: {allowed}."
        )
    return cast(RuntimeProfileName, requested_profile)


def build_worker_probe_app(container: RuntimeContainer | None = None) -> FastAPI:
    runtime_container = container or build_worker_runtime()
    app = FastAPI(
        title="CCDash Worker Probe",
        description="Lightweight liveness/readiness/detail probe surface for the CCDash worker runtime",
        version="0.1.0",
    )
    app.state.runtime_profile = runtime_container.profile
    app.state.runtime_container = runtime_container

    @app.get("/livez")
    def livez() -> dict[str, Any]:
        payload = _worker_probe_payload(runtime_container)
        return {
            "schemaVersion": payload["schemaVersion"],
            "runtimeProfile": payload["runtimeProfile"],
            "live": payload["live"],
        }

    @app.get("/readyz")
    def readyz(response: Response) -> dict[str, Any]:
        payload = _worker_probe_payload(runtime_container)
        ready = payload["ready"]
        if not bool(ready.get("ready", False)):
            response.status_code = 503
        return {
            "schemaVersion": payload["schemaVersion"],
            "runtimeProfile": payload["runtimeProfile"],
            "ready": ready,
            "worker": payload["detail"].get("worker", {}),
        }

    @app.get("/detailz")
    def detailz() -> dict[str, Any]:
        return _worker_probe_payload(runtime_container)

    return app


def _worker_probe_payload(container: RuntimeContainer) -> dict[str, Any]:
    runtime_status = container.runtime_status()
    probe_contract = runtime_status.get("probeContract", {}) if isinstance(runtime_status, dict) else {}
    detail = dict(probe_contract.get("detail", {})) if isinstance(probe_contract.get("detail", {}), dict) else {}
    worker_probe = runtime_status.get("workerProbe", {}) if isinstance(runtime_status, dict) else {}
    if worker_probe:
        detail["worker"] = worker_probe
    return {
        "schemaVersion": str(probe_contract.get("schemaVersion", "")),
        "runtimeProfile": str(probe_contract.get("runtimeProfile", runtime_status.get("profile", "worker"))),
        "live": dict(probe_contract.get("live", {})),
        "ready": dict(probe_contract.get("ready", {})),
        "detail": detail,
    }


container = build_worker_runtime()
