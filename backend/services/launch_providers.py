"""Static provider capability catalog for plan-driven launch preparation.

V1 ships with a local provider only; future providers plug in here without
changing callers. Capabilities are advisory — actual enforcement of approval
and command routing stays in execution_policy + ExecutionApplicationService.
"""
from __future__ import annotations

from backend.models import LaunchProviderCapabilityDTO


LOCAL_PROVIDER = "local"


def default_provider_catalog() -> list[LaunchProviderCapabilityDTO]:
    return [
        LaunchProviderCapabilityDTO(
            provider=LOCAL_PROVIDER,
            label="Local Terminal",
            supported=True,
            supportsWorktrees=True,
            supportsModelSelection=False,
            defaultModel="",
            availableModels=[],
            requiresApproval=False,
            unsupportedReason="",
            metadata={"transport": "subprocess"},
        ),
    ]


def resolve_provider(
    providers: list[LaunchProviderCapabilityDTO],
    preference: str,
) -> LaunchProviderCapabilityDTO:
    if preference:
        for entry in providers:
            if entry.provider == preference:
                return entry
    # Fall back to the first supported provider, else first entry.
    for entry in providers:
        if entry.supported:
            return entry
    return providers[0]
