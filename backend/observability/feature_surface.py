"""Instrumentation helpers for the feature-surface hot paths.

Usage in a router endpoint::

    from backend.observability.feature_surface import instrument_feature_surface

    @features_router.get("")
    async def list_features(...):
        with instrument_feature_surface("list", filter_kind="status_only") as ctx:
            ...
            ctx.set_result(items=results, payload_bytes=len(body_bytes))
        return response

The context manager handles:
- OTEL span creation (when OTEL is enabled)
- Counter + histogram recording via otel.record_feature_surface_request
- Budget warn-log when latency or payload exceeds the documented thresholds
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

from backend.observability import otel

logger = logging.getLogger("ccdash.features.observability")

# ── Budget thresholds (warn when crossed) ─────────────────────────────────────
#
# These are intentionally documented here so operators know what to tune via
# CCDASH_FEATURE_SURFACE_LATENCY_BUDGET_MS and _PAYLOAD_BUDGET_BYTES if the
# defaults are too tight / too loose for their deployment.

_DEFAULT_LATENCY_BUDGET_MS: float = 500.0   # 500 ms p95 target
_DEFAULT_PAYLOAD_BUDGET_BYTES: int = 200_000  # 200 KB serialised response


class FeatureSurfaceInstrumentContext:
    """Mutable context populated by the endpoint before the `with` block exits."""

    __slots__ = ("endpoint", "filter_kind", "_result_count", "_payload_bytes", "_started_at")

    def __init__(self, endpoint: str, filter_kind: str) -> None:
        self.endpoint = endpoint
        self.filter_kind = filter_kind
        self._result_count: int = 0
        self._payload_bytes: int = 0
        self._started_at: float = time.monotonic()

    def set_result(self, *, items: int = 0, payload_bytes: int = 0) -> None:
        """Call once the endpoint knows how many items it returned and the serialised size."""
        self._result_count = max(0, items)
        self._payload_bytes = max(0, payload_bytes)

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._started_at) * 1000.0


@contextmanager
def instrument_feature_surface(
    endpoint: str,
    *,
    filter_kind: str = "none",
    latency_budget_ms: float = _DEFAULT_LATENCY_BUDGET_MS,
    payload_budget_bytes: int = _DEFAULT_PAYLOAD_BUDGET_BYTES,
) -> Generator[FeatureSurfaceInstrumentContext, None, None]:
    """Context manager that wraps a feature-surface request with observability.

    Args:
        endpoint: Short endpoint name (``list``, ``detail``, ``execution_context``,
                  ``linked_sessions``, ``activity``).  Added as an OTEL/Prom label.
        filter_kind: Cardinality-safe description of the applied filters
                     (``status_only``, ``search_only``, ``both``, ``none``).
        latency_budget_ms: Warn when the request exceeds this threshold (ms).
        payload_budget_bytes: Warn when the serialised response exceeds this (bytes).
    """
    ctx = FeatureSurfaceInstrumentContext(endpoint=endpoint, filter_kind=filter_kind)
    span_name = f"ccdash.feature_surface.{endpoint}"
    span_attrs = {
        "feature_surface.endpoint": endpoint,
        "feature_surface.filter_kind": filter_kind,
    }

    with otel.start_span(span_name, attributes=span_attrs):
        try:
            yield ctx
        finally:
            elapsed = ctx.elapsed_ms
            otel.record_feature_surface_request(
                endpoint=ctx.endpoint,
                filter_kind=ctx.filter_kind,
                result_count=ctx._result_count,
                payload_bytes=ctx._payload_bytes,
                duration_ms=elapsed,
            )
            _maybe_warn_budget(ctx, elapsed, latency_budget_ms, payload_budget_bytes)


def _maybe_warn_budget(
    ctx: FeatureSurfaceInstrumentContext,
    elapsed_ms: float,
    latency_budget_ms: float,
    payload_budget_bytes: int,
) -> None:
    """Emit a structured WARN log when a budget is exceeded."""
    latency_over = elapsed_ms > latency_budget_ms
    payload_over = ctx._payload_bytes > payload_budget_bytes and ctx._payload_bytes > 0

    if not latency_over and not payload_over:
        return

    reasons: list[str] = []
    if latency_over:
        reasons.append(f"latency={elapsed_ms:.1f}ms > budget={latency_budget_ms:.0f}ms")
    if payload_over:
        reasons.append(
            f"payload={ctx._payload_bytes / 1024:.1f}KB > budget={payload_budget_bytes / 1024:.0f}KB"
        )

    logger.warning(
        "feature_surface budget exceeded",
        extra={
            "endpoint": ctx.endpoint,
            "filter_kind": ctx.filter_kind,
            "result_count_bucket": otel._result_count_bucket(ctx._result_count),
            "payload_bytes_bucket": otel._payload_bytes_bucket(ctx._payload_bytes),
            "elapsed_ms": round(elapsed_ms, 2),
            "payload_bytes": ctx._payload_bytes,
            "reasons": reasons,
        },
    )
