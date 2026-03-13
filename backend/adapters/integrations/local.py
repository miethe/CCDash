"""Local integration adapter baselines."""
from __future__ import annotations

from typing import Any, Mapping


class NoopIntegrationClient:
    async def invoke(
        self,
        integration: str,
        operation: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        return {
            "integration": integration,
            "operation": operation,
            "payload": dict(payload or {}),
            "status": "not-configured",
        }
