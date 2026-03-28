"""HTTP client for outbound SAM telemetry export."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from backend.config import TelemetryExporterConfig
from backend.models import ExecutionOutcomePayload

logger = logging.getLogger("ccdash.integrations.sam_telemetry")


@dataclass(slots=True)
class SAMTelemetryClient:
    endpoint_url: str
    api_key: str
    timeout_seconds: float = 30.0
    allow_insecure: bool = False

    def __post_init__(self) -> None:
        self.endpoint_url = str(self.endpoint_url or "").strip()
        self.api_key = str(self.api_key or "").strip()
        timeout = self.timeout_seconds if self.timeout_seconds is not None else 30.0
        self.timeout_seconds = max(1.0, float(timeout))
        parsed = urlparse(self.endpoint_url)
        if not self.endpoint_url:
            raise ValueError("Telemetry exporter endpoint is required")
        if not self.api_key:
            raise ValueError("Telemetry exporter API key is required")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Telemetry exporter endpoint must use http or https")
        if parsed.scheme != "https" and not self.allow_insecure:
            raise ValueError("Telemetry exporter requires HTTPS unless allow_insecure=true")

    @classmethod
    def from_config(cls, exporter_config: TelemetryExporterConfig) -> "SAMTelemetryClient":
        return cls(
            endpoint_url=exporter_config.sam_endpoint,
            api_key=exporter_config.sam_api_key,
            timeout_seconds=exporter_config.timeout_seconds,
            allow_insecure=exporter_config.allow_insecure,
        )

    async def push_batch(self, events: list[ExecutionOutcomePayload]) -> tuple[bool, str | None]:
        if not events:
            return True, None
        payload = {
            "schema_version": "1",
            "events": [event.event_dict() for event in events],
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        request_kwargs: dict[str, object] = {}
        if self.allow_insecure and self.endpoint_url.startswith("https://"):
            request_kwargs["ssl"] = False

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.endpoint_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    **request_kwargs,
                ) as response:
                    response_text = await response.text()
                    if response.status in {200, 202}:
                        return True, None
                    if response.status == 429:
                        logger.warning(
                            "SAM telemetry export rate limited: status=%s body=%s",
                            response.status,
                            response_text,
                        )
                        return False, "rate_limited"
                    if 400 <= response.status < 500:
                        message = response_text.strip() or f"HTTP {response.status}"
                        logger.error(
                            "SAM telemetry export abandoned: status=%s body=%s",
                            response.status,
                            response_text,
                        )
                        return False, f"abandoned:{message}"
                    logger.warning(
                        "SAM telemetry export failed: status=%s body=%s",
                        response.status,
                        response_text,
                    )
                    return False, (response_text.strip() or f"HTTP {response.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("SAM telemetry export request failed: %s", exc)
            return False, (str(exc) or exc.__class__.__name__)


__all__ = ["SAMTelemetryClient"]
