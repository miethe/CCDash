"""Runtime profile definitions for CCDash process modes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RuntimeProfileName = Literal["local", "api", "worker", "test"]
StorageProfileName = Literal["local", "enterprise"]


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    watch: bool
    sync: bool
    jobs: bool
    auth: bool
    integrations: bool


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    name: RuntimeProfileName
    capabilities: RuntimeCapabilities
    recommended_storage_profile: StorageProfileName
    description: str


_RUNTIME_PROFILES: dict[RuntimeProfileName, RuntimeProfile] = {
    "local": RuntimeProfile(
        name="local",
        capabilities=RuntimeCapabilities(
            watch=True,
            sync=True,
            jobs=True,
            auth=False,
            integrations=True,
        ),
        recommended_storage_profile="local",
        description="Desktop-style local profile with automatic sync, watcher, and in-process jobs.",
    ),
    "api": RuntimeProfile(
        name="api",
        capabilities=RuntimeCapabilities(
            watch=False,
            sync=False,
            jobs=False,
            auth=True,
            integrations=True,
        ),
        recommended_storage_profile="enterprise",
        description="HTTP-serving profile without incidental watcher or startup sync work.",
    ),
    "worker": RuntimeProfile(
        name="worker",
        capabilities=RuntimeCapabilities(
            watch=False,
            sync=True,
            jobs=True,
            auth=False,
            integrations=True,
        ),
        recommended_storage_profile="enterprise",
        description="Background worker profile for sync, refresh, and scheduled job execution without HTTP serving.",
    ),
    "test": RuntimeProfile(
        name="test",
        capabilities=RuntimeCapabilities(
            watch=False,
            sync=False,
            jobs=False,
            auth=False,
            integrations=False,
        ),
        recommended_storage_profile="local",
        description="Stripped test profile with background work disabled by default.",
    ),
}


def get_runtime_profile(name: RuntimeProfileName) -> RuntimeProfile:
    return _RUNTIME_PROFILES[name]


def iter_runtime_profiles() -> tuple[RuntimeProfile, ...]:
    return tuple(_RUNTIME_PROFILES.values())
