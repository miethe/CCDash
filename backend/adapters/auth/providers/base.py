"""Shared contracts for hosted auth providers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.application.context import Principal


@dataclass(frozen=True, slots=True)
class HostedAuthValidationContext:
    """Per-request validation values captured during hosted auth flows."""

    expected_nonce: str | None = None
    expected_state: str | None = None
    presented_state: str | None = None
    authorized_party: str | None = None


class HostedAuthProvider(Protocol):
    """Hosted token verifier contract shared by OIDC-like providers."""

    @property
    def provider_id(self) -> str:
        """Stable provider identifier used in normalized subjects."""

    async def verify(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ) -> Principal:
        """Validate a hosted provider token and convert it to a Principal."""

    async def resolve(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ) -> Principal:
        """Alias for verify, named for higher-level session resolution flows."""
