"""OpenTelemetry + Prometheus fallback wiring for CCDash backend."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI

from backend import config

logger = logging.getLogger("ccdash.observability")


_initialized = False
_enabled = False
_tracer: Any | None = None
_trace_provider: Any | None = None
_meter_provider: Any | None = None
_fastapi_instrumentor: Any | None = None

_ingestion_counter: Any | None = None
_ingestion_latency_hist: Any | None = None
_parser_failure_counter: Any | None = None
_tool_calls_counter: Any | None = None
_tool_duration_hist: Any | None = None
_tokens_counter: Any | None = None
_cost_counter: Any | None = None

_prom_enabled = False
_prom_ingestion_counter: Any | None = None
_prom_ingestion_latency_hist: Any | None = None
_prom_parser_failure_counter: Any | None = None
_prom_tool_calls_counter: Any | None = None
_prom_tool_duration_hist: Any | None = None
_prom_tokens_counter: Any | None = None
_prom_cost_counter: Any | None = None


def _normalize_otlp_endpoint(base_endpoint: str, signal_path: str) -> str:
    endpoint = (base_endpoint or "").strip()
    if not endpoint:
        return ""
    if endpoint.endswith(signal_path):
        return endpoint
    if endpoint.endswith("/"):
        endpoint = endpoint[:-1]
    if endpoint.endswith("/v1"):
        return f"{endpoint}{signal_path[3:]}"
    return f"{endpoint}{signal_path}"


def _prom_labels(*, project_id: str, **extra: str) -> dict[str, str]:
    labels = {"project": project_id or "unknown"}
    for key, value in extra.items():
        labels[key] = (value or "").strip() or "unknown"
    return labels


def initialize(app: FastAPI | None = None) -> None:
    global _initialized, _enabled, _tracer, _trace_provider, _meter_provider, _fastapi_instrumentor
    global _ingestion_counter, _ingestion_latency_hist, _parser_failure_counter
    global _tool_calls_counter, _tool_duration_hist, _tokens_counter, _cost_counter
    global _prom_enabled
    global _prom_ingestion_counter, _prom_ingestion_latency_hist, _prom_parser_failure_counter
    global _prom_tool_calls_counter, _prom_tool_duration_hist, _prom_tokens_counter, _prom_cost_counter

    if _initialized:
        if _enabled and app and _fastapi_instrumentor:
            _fastapi_instrumentor.instrument_app(app)
        return

    _initialized = True

    if not config.OTEL_ENABLED:
        logger.info("OpenTelemetry disabled (CCDASH_OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("OpenTelemetry dependencies unavailable: %s", exc)
        return

    traces_endpoint = _normalize_otlp_endpoint(config.OTEL_ENDPOINT, "/v1/traces")
    metrics_endpoint = _normalize_otlp_endpoint(config.OTEL_ENDPOINT, "/v1/metrics")
    service_name = config.OTEL_SERVICE_NAME or "ccdash-backend"

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "ccdash",
        }
    )

    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=traces_endpoint or None)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer("ccdash.backend")

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=metrics_endpoint or None)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("ccdash.backend")

    _ingestion_counter = meter.create_counter(
        "ccdash_ingestion_events_total",
        unit="1",
        description="Count of telemetry ingestion operations",
    )
    _ingestion_latency_hist = meter.create_histogram(
        "ccdash_ingestion_latency_ms",
        unit="ms",
        description="Latency for parser and sync ingestion operations",
    )
    _parser_failure_counter = meter.create_counter(
        "ccdash_parser_failures_total",
        unit="1",
        description="Count of parser failures",
    )
    _tool_calls_counter = meter.create_counter(
        "ccdash_tool_calls_total",
        unit="1",
        description="Tool call outcomes observed while ingesting sessions",
    )
    _tool_duration_hist = meter.create_histogram(
        "ccdash_tool_duration_ms",
        unit="ms",
        description="Observed tool execution durations",
    )
    _tokens_counter = meter.create_counter(
        "ccdash_tokens_total",
        unit="1",
        description="Token totals by model and feature context",
    )
    _cost_counter = meter.create_counter(
        "ccdash_cost_usd_total",
        unit="usd",
        description="Cost totals by model and feature context",
    )

    _trace_provider = trace_provider
    _meter_provider = meter_provider
    _tracer = tracer
    _fastapi_instrumentor = FastAPIInstrumentor()
    _enabled = True

    if app:
        _fastapi_instrumentor.instrument_app(app)

    if config.PROM_PORT > 0:
        try:
            from prometheus_client import Counter, Histogram, start_http_server

            start_http_server(config.PROM_PORT)
            _prom_enabled = True
            _prom_ingestion_counter = Counter(
                "ccdash_ingestion_events_total",
                "Count of telemetry ingestion operations",
                ["entity", "result", "project"],
            )
            _prom_ingestion_latency_hist = Histogram(
                "ccdash_ingestion_latency_ms",
                "Latency for parser and sync ingestion operations",
                ["entity", "result", "project"],
            )
            _prom_parser_failure_counter = Counter(
                "ccdash_parser_failures_total",
                "Count of parser failures",
                ["parser", "project"],
            )
            _prom_tool_calls_counter = Counter(
                "ccdash_tool_calls_total",
                "Tool call outcomes observed while ingesting sessions",
                ["tool", "status", "project"],
            )
            _prom_tool_duration_hist = Histogram(
                "ccdash_tool_duration_ms",
                "Observed tool execution durations",
                ["tool", "project"],
            )
            _prom_tokens_counter = Counter(
                "ccdash_tokens_total",
                "Token totals by model and feature context",
                ["model", "feature", "direction", "project"],
            )
            _prom_cost_counter = Counter(
                "ccdash_cost_usd_total",
                "Cost totals by model and feature context",
                ["model", "feature", "project"],
            )
            logger.info("Prometheus fallback metrics server listening on port %s", config.PROM_PORT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Prometheus fallback not started: %s", exc)
            _prom_enabled = False

    logger.info(
        "OpenTelemetry initialized (service=%s endpoint=%s)",
        service_name,
        config.OTEL_ENDPOINT,
    )


def shutdown(app: FastAPI | None = None) -> None:
    global _enabled
    if not _initialized:
        return
    try:
        if app and _fastapi_instrumentor:
            _fastapi_instrumentor.uninstrument_app(app)
    except Exception:
        pass
    try:
        if _meter_provider is not None:
            _meter_provider.shutdown()
    except Exception:
        pass
    try:
        if _trace_provider is not None:
            _trace_provider.shutdown()
    except Exception:
        pass
    _enabled = False


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None):
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span


def record_ingestion(entity: str, result: str, duration_ms: float, *, project_id: str) -> None:
    labels = {
        "entity": entity or "unknown",
        "result": result or "unknown",
        "project_id": project_id or "unknown",
    }
    if _enabled and _ingestion_counter is not None:
        _ingestion_counter.add(1, labels)
    if _enabled and _ingestion_latency_hist is not None:
        _ingestion_latency_hist.record(max(0.0, float(duration_ms)), labels)
    if _prom_enabled and _prom_ingestion_counter is not None:
        prom = _prom_labels(project_id=project_id, entity=entity, result=result)
        _prom_ingestion_counter.labels(**prom).inc()
    if _prom_enabled and _prom_ingestion_latency_hist is not None:
        prom = _prom_labels(project_id=project_id, entity=entity, result=result)
        _prom_ingestion_latency_hist.labels(**prom).observe(max(0.0, float(duration_ms)))


def record_parser_failure(parser: str, *, project_id: str) -> None:
    labels = {
        "parser": parser or "unknown",
        "project_id": project_id or "unknown",
    }
    if _enabled and _parser_failure_counter is not None:
        _parser_failure_counter.add(1, labels)
    if _prom_enabled and _prom_parser_failure_counter is not None:
        prom = _prom_labels(project_id=project_id, parser=parser)
        _prom_parser_failure_counter.labels(**prom).inc()


def record_tool_result(tool: str, status: str, *, project_id: str, count: int = 1, duration_ms: float = 0.0) -> None:
    safe_count = max(0, int(count))
    if safe_count == 0:
        return
    labels = {
        "tool": tool or "unknown",
        "status": status or "unknown",
        "project_id": project_id or "unknown",
    }
    if _enabled and _tool_calls_counter is not None:
        _tool_calls_counter.add(safe_count, labels)
    if _enabled and _tool_duration_hist is not None and duration_ms > 0:
        _tool_duration_hist.record(float(duration_ms), labels)
    if _prom_enabled and _prom_tool_calls_counter is not None:
        prom = _prom_labels(project_id=project_id, tool=tool, status=status)
        _prom_tool_calls_counter.labels(**prom).inc(safe_count)
    if _prom_enabled and _prom_tool_duration_hist is not None and duration_ms > 0:
        prom = _prom_labels(project_id=project_id, tool=tool)
        _prom_tool_duration_hist.labels(**prom).observe(float(duration_ms))


def record_token_cost(
    *,
    project_id: str,
    model: str,
    feature_id: str,
    token_input: int,
    token_output: int,
    cost_usd: float,
) -> None:
    labels_base = {
        "model": (model or "unknown").strip() or "unknown",
        "feature_id": (feature_id or "none").strip() or "none",
        "project_id": project_id or "unknown",
    }
    in_tokens = max(0, int(token_input))
    out_tokens = max(0, int(token_output))
    if _enabled and _tokens_counter is not None:
        if in_tokens > 0:
            _tokens_counter.add(in_tokens, {**labels_base, "direction": "input"})
        if out_tokens > 0:
            _tokens_counter.add(out_tokens, {**labels_base, "direction": "output"})
    if _enabled and _cost_counter is not None and cost_usd > 0:
        _cost_counter.add(float(cost_usd), labels_base)

    if _prom_enabled and _prom_tokens_counter is not None:
        prom_base = _prom_labels(project_id=project_id, model=model, feature=feature_id or "none")
        if in_tokens > 0:
            _prom_tokens_counter.labels(**{**prom_base, "direction": "input"}).inc(in_tokens)
        if out_tokens > 0:
            _prom_tokens_counter.labels(**{**prom_base, "direction": "output"}).inc(out_tokens)
    if _prom_enabled and _prom_cost_counter is not None and cost_usd > 0:
        prom_base = _prom_labels(project_id=project_id, model=model, feature=feature_id or "none")
        _prom_cost_counter.labels(**prom_base).inc(float(cost_usd))
