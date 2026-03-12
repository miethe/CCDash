"""Worker runtime bootstrap."""
from __future__ import annotations

from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile


def build_worker_runtime() -> RuntimeContainer:
    return RuntimeContainer(profile=get_runtime_profile("worker"))


container = build_worker_runtime()
