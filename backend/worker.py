"""Worker process entrypoint for background-only runtime profiles."""
from __future__ import annotations

import asyncio
import signal
from types import SimpleNamespace

from backend.runtime.bootstrap_worker import build_worker_runtime
from backend.runtime.container import RuntimeContainer


class WorkerRuntimeApp:
    def __init__(self) -> None:
        self.state = SimpleNamespace()


async def serve_worker(
    *,
    container: RuntimeContainer | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    runtime = container or build_worker_runtime()
    app = WorkerRuntimeApp()
    shutdown_event = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    registered_signals: list[signal.Signals] = []

    if stop_event is None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown_event.set)
                registered_signals.append(sig)
            except NotImplementedError:
                pass

    await runtime.startup(app)
    try:
        await shutdown_event.wait()
    finally:
        for sig in registered_signals:
            loop.remove_signal_handler(sig)
        await runtime.shutdown(app)


def main() -> None:
    asyncio.run(serve_worker())


if __name__ == "__main__":
    main()
