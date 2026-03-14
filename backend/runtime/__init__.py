"""Runtime composition helpers for CCDash.

This module intentionally avoids eager imports so submodules like
``backend.runtime.profiles`` can be imported without pulling in the full runtime
bootstrap tree. That prevents router/bootstrap cycles during isolated test
imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RuntimeCapabilities",
    "RuntimeContainer",
    "RuntimeProfile",
    "RuntimeProfileName",
    "build_api_app",
    "build_local_app",
    "build_runtime_app",
    "build_test_app",
    "build_worker_runtime",
    "get_core_ports",
    "get_request_context",
    "get_runtime_container",
    "get_runtime_profile",
    "iter_runtime_profiles",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "RuntimeCapabilities": ("backend.runtime.profiles", "RuntimeCapabilities"),
    "RuntimeContainer": ("backend.runtime.container", "RuntimeContainer"),
    "RuntimeProfile": ("backend.runtime.profiles", "RuntimeProfile"),
    "RuntimeProfileName": ("backend.runtime.profiles", "RuntimeProfileName"),
    "build_api_app": ("backend.runtime.bootstrap_api", "build_api_app"),
    "build_local_app": ("backend.runtime.bootstrap_local", "build_local_app"),
    "build_runtime_app": ("backend.runtime.bootstrap", "build_runtime_app"),
    "build_test_app": ("backend.runtime.bootstrap_test", "build_test_app"),
    "build_worker_runtime": ("backend.runtime.bootstrap_worker", "build_worker_runtime"),
    "get_core_ports": ("backend.runtime.dependencies", "get_core_ports"),
    "get_request_context": ("backend.runtime.dependencies", "get_request_context"),
    "get_runtime_container": ("backend.runtime.dependencies", "get_runtime_container"),
    "get_runtime_profile": ("backend.runtime.profiles", "get_runtime_profile"),
    "iter_runtime_profiles": ("backend.runtime.profiles", "iter_runtime_profiles"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_IMPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
