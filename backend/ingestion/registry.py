"""Source-neutral ingestion adapter contracts and lookup helpers."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.ingestion.models import IngestSource, NormalizedSessionEnvelope


@runtime_checkable
class IngestSourceAdapter(Protocol):
    """Adapter contract for converting upstream payloads into ingest envelopes."""

    source: IngestSource

    def can_accept(self, payload: object) -> bool:
        """Return whether this adapter can normalize the given payload."""

    def to_envelopes(self, payload: object) -> list[NormalizedSessionEnvelope]:
        """Normalize a supported payload into one or more session envelopes."""


class IngestAdapterRegistry:
    """Small source-neutral registry for ingestion adapters."""

    def __init__(self, adapters: Iterable[IngestSourceAdapter] = ()) -> None:
        self._adapters: list[IngestSourceAdapter] = []
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: IngestSourceAdapter) -> IngestSourceAdapter:
        """Register an adapter and return it for decorator-friendly usage."""
        self._adapters.append(adapter)
        return adapter

    def adapters(self, *, source: IngestSource | None = None) -> tuple[IngestSourceAdapter, ...]:
        """Return registered adapters, optionally limited to one source family."""
        if source is None:
            return tuple(self._adapters)
        return tuple(adapter for adapter in self._adapters if adapter.source == source)

    def find_adapter(
        self,
        payload: object,
        *,
        source: IngestSource | None = None,
    ) -> IngestSourceAdapter | None:
        """Find the first registered adapter that accepts the payload."""
        for adapter in self.adapters(source=source):
            if adapter.can_accept(payload):
                return adapter
        return None


__all__ = [
    "IngestAdapterRegistry",
    "IngestSourceAdapter",
]
