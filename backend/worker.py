"""Worker process entrypoint for background-only runtime profiles."""
from __future__ import annotations

import asyncio
import os
import signal
from types import SimpleNamespace

import uvicorn

from backend.runtime.bootstrap_worker import build_worker_probe_app, build_worker_runtime
from backend.runtime.container import RuntimeContainer

DEFAULT_WORKER_PROBE_HOST = "127.0.0.1"
DEFAULT_WORKER_PROBE_PORT = 9465


class WorkerRuntimeApp:
    def __init__(self) -> None:
        self.state = SimpleNamespace()


async def serve_worker(
    *,
    container: RuntimeContainer | None = None,
    stop_event: asyncio.Event | None = None,
    probe_host: str | None = None,
    probe_port: int | None = None,
) -> None:
    runtime = container or build_worker_runtime()
    app = WorkerRuntimeApp()
    shutdown_event = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    registered_signals: list[signal.Signals] = []
    probe_server: uvicorn.Server | None = None
    probe_task: asyncio.Task[bool] | None = None

    if stop_event is None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown_event.set)
                registered_signals.append(sig)
            except NotImplementedError:
                pass

    await runtime.startup(app)
    probe_binding = _resolve_probe_binding(probe_host=probe_host, probe_port=probe_port)
    if probe_binding is not None:
        resolved_host, resolved_port = probe_binding
        probe_app = build_worker_probe_app(runtime)
        probe_server = uvicorn.Server(
            uvicorn.Config(
                probe_app,
                host=resolved_host,
                port=resolved_port,
                access_log=False,
                lifespan="off",
                log_level="warning",
            )
        )
        probe_task = asyncio.create_task(
            probe_server.serve(),
            name=f"ccdash:worker:probe:{resolved_host}:{resolved_port}",
        )
        await asyncio.sleep(0)
    try:
        await shutdown_event.wait()
    finally:
        try:
            if probe_server is not None:
                probe_server.should_exit = True
            if probe_task is not None:
                await probe_task
        finally:
            for sig in registered_signals:
                loop.remove_signal_handler(sig)
            await runtime.shutdown(app)


def _resolve_probe_binding(*, probe_host: str | None, probe_port: int | None) -> tuple[str, int] | None:
    resolved_port = probe_port
    if resolved_port is None:
        raw_port = os.getenv("CCDASH_WORKER_PROBE_PORT", "").strip()
        if not raw_port:
            resolved_port = DEFAULT_WORKER_PROBE_PORT
        else:
            try:
                resolved_port = int(raw_port)
            except ValueError as exc:
                raise RuntimeError(
                    "CCDASH_WORKER_PROBE_PORT must be an integer greater than 0."
                ) from exc
    if resolved_port <= 0:
        raise RuntimeError("CCDASH_WORKER_PROBE_PORT must be an integer greater than 0.")
    resolved_host = (
        probe_host
        or os.getenv("CCDASH_WORKER_PROBE_HOST", DEFAULT_WORKER_PROBE_HOST).strip()
        or DEFAULT_WORKER_PROBE_HOST
    )
    return resolved_host, resolved_port


def main() -> None:
    asyncio.run(serve_worker())


if __name__ == "__main__":
    main()
