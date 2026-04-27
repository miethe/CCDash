"""OpenTelemetry + Prometheus fallback wiring for CCDash backend."""
from __future__ import annotations

import logging
import os
import socket
from contextlib import contextmanager
from typing import Any, Mapping
from uuid import uuid4

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
_telemetry_export_events_counter: Any | None = None
_telemetry_export_latency_hist: Any | None = None
_telemetry_export_queue_depth_gauge: Any | None = None
_telemetry_export_errors_counter: Any | None = None
_telemetry_export_disabled_gauge: Any | None = None
_worker_job_freshness_gauge: Any | None = None
_worker_job_backpressure_gauge: Any | None = None
_agent_query_cache_hit_counter: Any | None = None
_agent_query_cache_miss_counter: Any | None = None

# ── Feature-surface hot-path metrics ─────────────────────────────────────────
_feature_surface_requests_counter: Any | None = None
_feature_surface_latency_hist: Any | None = None
_prom_feature_surface_requests_counter: Any | None = None
_prom_feature_surface_latency_hist: Any | None = None

# ── Runtime-performance-hardening metrics (OBS-401) ──────────────────────────
_frontend_poll_teardown_counter: Any | None = None
_link_rebuild_scope_counter: Any | None = None
_filesystem_scan_cached_counter: Any | None = None
_workflow_detail_batch_rows_hist: Any | None = None
_prom_frontend_poll_teardown_counter: Any | None = None
_prom_link_rebuild_scope_counter: Any | None = None
_prom_filesystem_scan_cached_counter: Any | None = None
_prom_workflow_detail_batch_rows_hist: Any | None = None

_prom_enabled = False
_prom_ingestion_counter: Any | None = None
_prom_ingestion_latency_hist: Any | None = None
_prom_parser_failure_counter: Any | None = None
_prom_tool_calls_counter: Any | None = None
_prom_tool_duration_hist: Any | None = None
_prom_tokens_counter: Any | None = None
_prom_cost_counter: Any | None = None
_prom_telemetry_export_events_counter: Any | None = None
_prom_telemetry_export_latency_hist: Any | None = None
_prom_telemetry_export_queue_depth_gauge: Any | None = None
_prom_telemetry_export_errors_counter: Any | None = None
_prom_telemetry_export_disabled_gauge: Any | None = None
_prom_worker_job_freshness_gauge: Any | None = None
_prom_worker_job_backpressure_gauge: Any | None = None

_telemetry_queue_depth_state: dict[tuple[str, str, str, str, str], int] = {}
_telemetry_export_disabled_state = 1
_worker_job_freshness_state: dict[tuple[str, str, str, str, str], float] = {}
_worker_job_backpressure_state: dict[tuple[str, str, str, str, str], float] = {}

_RUNTIME_PROM_LABEL_NAMES = ("runtime_profile", "deployment_mode", "storage_profile")
_RESOURCE_INSTANCE_ID = os.getenv("OTEL_SERVICE_INSTANCE_ID", "").strip() or str(uuid4())
_RESOURCE_HOSTNAME = socket.gethostname().strip() or "unknown"


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


def _runtime_metric_dimensions(runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, str]:
    metadata = runtime_metadata or {}
    return {
        "runtime_profile": _clean_runtime_dimension(
            metadata.get("runtime_profile") or metadata.get("runtimeProfile") or metadata.get("profile")
        ),
        "deployment_mode": _clean_runtime_dimension(
            metadata.get("deployment_mode") or metadata.get("deploymentMode")
        ),
        "storage_profile": _clean_runtime_dimension(
            metadata.get("storage_profile") or metadata.get("storageProfile")
        ),
    }


def _runtime_span_attributes(runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, str]:
    dimensions = _runtime_metric_dimensions(runtime_metadata)
    return {
        "ccdash.runtime.profile": dimensions["runtime_profile"],
        "ccdash.runtime.deployment_mode": dimensions["deployment_mode"],
        "ccdash.runtime.storage_profile": dimensions["storage_profile"],
    }


def _clean_runtime_dimension(value: Any) -> str:
    clean = str(value or "").strip()
    return clean or "unknown"


def _metric_prom_labels(
    *,
    project_id: str,
    runtime_metadata: Mapping[str, Any] | None = None,
    **extra: str,
) -> dict[str, str]:
    return _prom_labels(project_id=project_id, **_runtime_metric_dimensions(runtime_metadata), **extra)


def _worker_metric_key(
    *,
    job_name: str,
    project_id: str,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> tuple[str, str, str, str, str]:
    dimensions = _runtime_metric_dimensions(runtime_metadata)
    return (
        _clean_runtime_dimension(job_name),
        _clean_runtime_dimension(project_id),
        dimensions["runtime_profile"],
        dimensions["deployment_mode"],
        dimensions["storage_profile"],
    )


def initialize(app: FastAPI | None = None) -> None:
    global _initialized, _enabled, _tracer, _trace_provider, _meter_provider, _fastapi_instrumentor
    global _ingestion_counter, _ingestion_latency_hist, _parser_failure_counter
    global _tool_calls_counter, _tool_duration_hist, _tokens_counter, _cost_counter
    global _telemetry_export_events_counter, _telemetry_export_latency_hist
    global _telemetry_export_queue_depth_gauge, _telemetry_export_errors_counter
    global _telemetry_export_disabled_gauge, _worker_job_freshness_gauge, _worker_job_backpressure_gauge
    global _agent_query_cache_hit_counter, _agent_query_cache_miss_counter
    global _feature_surface_requests_counter, _feature_surface_latency_hist
    global _frontend_poll_teardown_counter, _link_rebuild_scope_counter
    global _filesystem_scan_cached_counter, _workflow_detail_batch_rows_hist
    global _prom_enabled
    global _prom_ingestion_counter, _prom_ingestion_latency_hist, _prom_parser_failure_counter
    global _prom_tool_calls_counter, _prom_tool_duration_hist, _prom_tokens_counter, _prom_cost_counter
    global _prom_telemetry_export_events_counter, _prom_telemetry_export_latency_hist
    global _prom_telemetry_export_queue_depth_gauge, _prom_telemetry_export_errors_counter
    global _prom_feature_surface_requests_counter, _prom_feature_surface_latency_hist
    global _prom_telemetry_export_disabled_gauge
    global _prom_worker_job_freshness_gauge, _prom_worker_job_backpressure_gauge
    global _prom_frontend_poll_teardown_counter, _prom_link_rebuild_scope_counter
    global _prom_filesystem_scan_cached_counter, _prom_workflow_detail_batch_rows_hist

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
        from opentelemetry.metrics import Observation
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
            "service.instance.id": _RESOURCE_INSTANCE_ID,
            "host.name": _RESOURCE_HOSTNAME,
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
    _telemetry_export_events_counter = meter.create_counter(
        "ccdash_telemetry_export_events_total",
        unit="1",
        description="Count of telemetry exporter batch outcomes",
    )
    _telemetry_export_latency_hist = meter.create_histogram(
        "ccdash_telemetry_export_latency_ms",
        unit="ms",
        description="Latency for telemetry export batches",
    )
    _telemetry_export_errors_counter = meter.create_counter(
        "ccdash_telemetry_export_errors_total",
        unit="1",
        description="Telemetry export errors by class",
    )
    _agent_query_cache_hit_counter = meter.create_counter(
        "agent_query.cache.hit",
        unit="1",
        description="Agent-query cache hit count",
    )
    _agent_query_cache_miss_counter = meter.create_counter(
        "agent_query.cache.miss",
        unit="1",
        description="Agent-query cache miss count",
    )
    _feature_surface_requests_counter = meter.create_counter(
        "ccdash_feature_surface_requests_total",
        unit="1",
        description="Feature-surface endpoint request count by endpoint, filter_kind, and result_count_bucket",
    )
    _feature_surface_latency_hist = meter.create_histogram(
        "ccdash_feature_surface_latency_ms",
        unit="ms",
        description="Feature-surface endpoint latency in milliseconds",
    )
    _telemetry_export_queue_depth_gauge = meter.create_observable_gauge(
        "ccdash_telemetry_export_queue_depth",
        callbacks=[_observe_telemetry_queue_depth(Observation)],
        unit="1",
        description="Telemetry export queue depth by status and project",
    )
    _telemetry_export_disabled_gauge = meter.create_observable_gauge(
        "ccdash_telemetry_export_disabled",
        callbacks=[_observe_telemetry_disabled(Observation)],
        unit="1",
        description="Whether telemetry export is disabled",
    )
    _worker_job_freshness_gauge = meter.create_observable_gauge(
        "ccdash_worker_job_freshness_ms",
        callbacks=[_observe_worker_job_freshness(Observation)],
        unit="ms",
        description="Age since the last successful worker job execution by job and runtime metadata",
    )
    _worker_job_backpressure_gauge = meter.create_observable_gauge(
        "ccdash_worker_job_backpressure_ratio",
        callbacks=[_observe_worker_job_backpressure(Observation)],
        unit="1",
        description="Worker job backlog pressure ratio by job and runtime metadata",
    )

    # ── Runtime-performance-hardening metrics (OBS-401) ───────────────────────
    _frontend_poll_teardown_counter = meter.create_counter(
        "ccdash_frontend_poll_teardown_total",
        unit="1",
        description="Frontend polling teardown events triggered after sustained unreachability.",
    )
    _link_rebuild_scope_counter = meter.create_counter(
        "ccdash_link_rebuild_scope",
        unit="1",
        description="Link rebuild dispatches by resolved scope.",
    )
    _filesystem_scan_cached_counter = meter.create_counter(
        "ccdash_filesystem_scan_cached_total",
        unit="1",
        description="Filesystem scan invocations skipped via light-mode manifest cache.",
    )
    _workflow_detail_batch_rows_hist = meter.create_histogram(
        "ccdash_workflow_detail_batch_rows",
        unit="1",
        description="Workflow-detail batch query row counts.",
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
            from prometheus_client import Counter, Gauge, Histogram, start_http_server

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
            _prom_telemetry_export_events_counter = Counter(
                "ccdash_telemetry_export_events_total",
                "Count of telemetry exporter batch outcomes",
                ["status", "project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_telemetry_export_latency_hist = Histogram(
                "ccdash_telemetry_export_latency_ms",
                "Latency for telemetry export batches",
                ["project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_telemetry_export_queue_depth_gauge = Gauge(
                "ccdash_telemetry_export_queue_depth",
                "Telemetry export queue depth by status and project",
                ["status", "project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_telemetry_export_errors_counter = Counter(
                "ccdash_telemetry_export_errors_total",
                "Telemetry export errors by class",
                ["error_type", "project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_telemetry_export_disabled_gauge = Gauge(
                "ccdash_telemetry_export_disabled",
                "Whether telemetry export is disabled",
            )
            _prom_worker_job_freshness_gauge = Gauge(
                "ccdash_worker_job_freshness_ms",
                "Age since the last successful worker job execution by job and runtime metadata",
                ["job", "project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_worker_job_backpressure_gauge = Gauge(
                "ccdash_worker_job_backpressure_ratio",
                "Worker job backlog pressure ratio by job and runtime metadata",
                ["job", "project", *_RUNTIME_PROM_LABEL_NAMES],
            )
            _prom_feature_surface_requests_counter = Counter(
                "ccdash_feature_surface_requests_total",
                "Feature-surface endpoint request count",
                ["endpoint", "filter_kind", "result_count_bucket", "payload_bytes_bucket"],
            )
            _prom_feature_surface_latency_hist = Histogram(
                "ccdash_feature_surface_latency_ms",
                "Feature-surface endpoint latency in milliseconds",
                ["endpoint", "filter_kind"],
            )
            # ── Runtime-performance-hardening metrics (OBS-401) ───────────────
            _prom_frontend_poll_teardown_counter = Counter(
                "ccdash_frontend_poll_teardown_total",
                "Frontend polling teardown events triggered after sustained unreachability.",
            )
            _prom_link_rebuild_scope_counter = Counter(
                "ccdash_link_rebuild_scope",
                "Link rebuild dispatches by resolved scope.",
                ["scope"],
            )
            _prom_filesystem_scan_cached_counter = Counter(
                "ccdash_filesystem_scan_cached_total",
                "Filesystem scan invocations skipped via light-mode manifest cache.",
            )
            _prom_workflow_detail_batch_rows_hist = Histogram(
                "ccdash_workflow_detail_batch_rows",
                "Workflow-detail batch query row counts.",
                ["endpoint"],
                buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
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
def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    runtime_metadata: Mapping[str, Any] | None = None,
):
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        for key, value in {**_runtime_span_attributes(runtime_metadata), **(attributes or {})}.items():
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


def record_telemetry_export_event(
    *,
    project_id: str,
    status: str,
    count: int = 1,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    safe_count = max(0, int(count))
    if safe_count == 0:
        return
    labels = {
        "status": (status or "unknown").strip() or "unknown",
        "project_id": project_id or "unknown",
        **_runtime_metric_dimensions(runtime_metadata),
    }
    if _enabled and _telemetry_export_events_counter is not None:
        _telemetry_export_events_counter.add(safe_count, labels)
    if _prom_enabled and _prom_telemetry_export_events_counter is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata, status=status)
        _prom_telemetry_export_events_counter.labels(**prom).inc(safe_count)


def record_telemetry_export_latency(
    *,
    project_id: str,
    duration_ms: float,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    value = max(0.0, float(duration_ms))
    labels = {"project_id": project_id or "unknown", **_runtime_metric_dimensions(runtime_metadata)}
    if _enabled and _telemetry_export_latency_hist is not None:
        _telemetry_export_latency_hist.record(value, labels)
    if _prom_enabled and _prom_telemetry_export_latency_hist is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata)
        _prom_telemetry_export_latency_hist.labels(**prom).observe(value)


def set_telemetry_export_queue_depth(
    *,
    project_id: str,
    status: str,
    depth: int,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    dimensions = _runtime_metric_dimensions(runtime_metadata)
    key = (
        _clean_runtime_dimension(project_id),
        _clean_runtime_dimension(status),
        dimensions["runtime_profile"],
        dimensions["deployment_mode"],
        dimensions["storage_profile"],
    )
    _telemetry_queue_depth_state[key] = max(0, int(depth))
    if _prom_enabled and _prom_telemetry_export_queue_depth_gauge is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata, status=status)
        _prom_telemetry_export_queue_depth_gauge.labels(**prom).set(max(0, int(depth)))


def record_telemetry_export_error(
    *,
    project_id: str,
    error_type: str,
    count: int = 1,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    safe_count = max(0, int(count))
    if safe_count == 0:
        return
    labels = {
        "error_type": (error_type or "unknown").strip() or "unknown",
        "project_id": project_id or "unknown",
        **_runtime_metric_dimensions(runtime_metadata),
    }
    if _enabled and _telemetry_export_errors_counter is not None:
        _telemetry_export_errors_counter.add(safe_count, labels)
    if _prom_enabled and _prom_telemetry_export_errors_counter is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata, error_type=error_type)
        _prom_telemetry_export_errors_counter.labels(**prom).inc(safe_count)


def set_telemetry_export_disabled(disabled: bool) -> None:
    global _telemetry_export_disabled_state
    _telemetry_export_disabled_state = 1 if disabled else 0
    if _prom_enabled and _prom_telemetry_export_disabled_gauge is not None:
        _prom_telemetry_export_disabled_gauge.set(_telemetry_export_disabled_state)


def set_worker_job_freshness(
    *,
    job_name: str,
    project_id: str,
    freshness_ms: float | None,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    key = _worker_metric_key(job_name=job_name, project_id=project_id, runtime_metadata=runtime_metadata)
    if freshness_ms is None:
        _worker_job_freshness_state.pop(key, None)
        return
    value = max(0.0, float(freshness_ms))
    _worker_job_freshness_state[key] = value
    if _prom_enabled and _prom_worker_job_freshness_gauge is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata, job=job_name)
        _prom_worker_job_freshness_gauge.labels(**prom).set(value)


def set_worker_job_backpressure(
    *,
    job_name: str,
    project_id: str,
    backpressure_ratio: float | None,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    key = _worker_metric_key(job_name=job_name, project_id=project_id, runtime_metadata=runtime_metadata)
    if backpressure_ratio is None:
        _worker_job_backpressure_state.pop(key, None)
        return
    value = max(0.0, float(backpressure_ratio))
    _worker_job_backpressure_state[key] = value
    if _prom_enabled and _prom_worker_job_backpressure_gauge is not None:
        prom = _metric_prom_labels(project_id=project_id, runtime_metadata=runtime_metadata, job=job_name)
        _prom_worker_job_backpressure_gauge.labels(**prom).set(value)


def _result_count_bucket(count: int) -> str:
    """Map a raw result count to a cardinality-safe bucket label."""
    if count <= 0:
        return "empty"
    if count <= 10:
        return "small"
    if count <= 100:
        return "medium"
    return "large"


def _payload_bytes_bucket(bytes_: int) -> str:
    """Map a raw byte count to a cardinality-safe bucket label."""
    if bytes_ <= 0:
        return "empty"
    if bytes_ < 10_000:
        return "small"     # < 10 KB
    if bytes_ < 100_000:
        return "medium"    # 10–100 KB
    if bytes_ < 500_000:
        return "large"     # 100–500 KB
    return "xlarge"        # >= 500 KB


def record_feature_surface_request(
    *,
    endpoint: str,
    filter_kind: str,
    result_count: int,
    payload_bytes: int,
    duration_ms: float,
) -> None:
    """Record a feature-surface endpoint request with cardinality-safe bucketed labels."""
    result_count_bucket = _result_count_bucket(result_count)
    payload_bytes_bucket = _payload_bytes_bucket(payload_bytes)
    safe_endpoint = (endpoint or "unknown").strip() or "unknown"
    safe_filter = (filter_kind or "none").strip() or "none"
    labels = {
        "endpoint": safe_endpoint,
        "filter_kind": safe_filter,
        "result_count_bucket": result_count_bucket,
        "payload_bytes_bucket": payload_bytes_bucket,
    }
    try:
        if _enabled and _feature_surface_requests_counter is not None:
            _feature_surface_requests_counter.add(1, labels)
        if _enabled and _feature_surface_latency_hist is not None:
            _feature_surface_latency_hist.record(max(0.0, float(duration_ms)), labels)
        if _prom_enabled and _prom_feature_surface_requests_counter is not None:
            _prom_feature_surface_requests_counter.labels(
                endpoint=safe_endpoint,
                filter_kind=safe_filter,
                result_count_bucket=result_count_bucket,
                payload_bytes_bucket=payload_bytes_bucket,
            ).inc()
        if _prom_enabled and _prom_feature_surface_latency_hist is not None:
            _prom_feature_surface_latency_hist.labels(
                endpoint=safe_endpoint,
                filter_kind=safe_filter,
            ).observe(max(0.0, float(duration_ms)))
    except Exception:
        logger.debug("feature_surface metrics unavailable", exc_info=True)


def record_cache_hit(endpoint: str) -> None:
    """Increment the agent-query cache hit counter for the given endpoint."""
    try:
        if _enabled and _agent_query_cache_hit_counter is not None:
            _agent_query_cache_hit_counter.add(1, {"endpoint": endpoint or "unknown"})
    except Exception:  # never let observability break a request
        logger.debug("cache.hit counter unavailable", exc_info=True)


def record_cache_miss(endpoint: str) -> None:
    """Increment the agent-query cache miss counter for the given endpoint."""
    try:
        if _enabled and _agent_query_cache_miss_counter is not None:
            _agent_query_cache_miss_counter.add(1, {"endpoint": endpoint or "unknown"})
    except Exception:  # never let observability break a request
        logger.debug("cache.miss counter unavailable", exc_info=True)


# ── Runtime-performance-hardening helpers (OBS-401) ──────────────────────────

_VALID_LINK_REBUILD_SCOPES = frozenset({"full", "entities_changed", "none"})


def record_frontend_poll_teardown() -> None:
    """Increment the frontend polling teardown counter (no labels)."""
    if not _initialized:
        return
    try:
        if _enabled and _frontend_poll_teardown_counter is not None:
            _frontend_poll_teardown_counter.add(1)
        if _prom_enabled and _prom_frontend_poll_teardown_counter is not None:
            _prom_frontend_poll_teardown_counter.inc()
    except Exception:
        logger.warning("record_frontend_poll_teardown: metric unavailable", exc_info=True)


def record_link_rebuild_scope(scope: str) -> None:
    """Increment the link-rebuild dispatch counter for the given scope.

    Valid scope values are ``full``, ``entities_changed``, and ``none``.
    Unknown values are coerced to ``full`` with a warning so that the metric
    is never silently dropped.
    """
    if not _initialized:
        return
    safe_scope = (scope or "").strip()
    if safe_scope not in _VALID_LINK_REBUILD_SCOPES:
        logger.warning(
            "record_link_rebuild_scope: unknown scope %r — defaulting to 'full'", scope
        )
        safe_scope = "full"
    try:
        if _enabled and _link_rebuild_scope_counter is not None:
            _link_rebuild_scope_counter.add(1, {"scope": safe_scope})
        if _prom_enabled and _prom_link_rebuild_scope_counter is not None:
            _prom_link_rebuild_scope_counter.labels(scope=safe_scope).inc()
    except Exception:
        logger.warning("record_link_rebuild_scope: metric unavailable", exc_info=True)


def record_filesystem_scan_cached() -> None:
    """Increment the filesystem scan cache-skip counter (no labels)."""
    if not _initialized:
        return
    try:
        if _enabled and _filesystem_scan_cached_counter is not None:
            _filesystem_scan_cached_counter.add(1)
        if _prom_enabled and _prom_filesystem_scan_cached_counter is not None:
            _prom_filesystem_scan_cached_counter.inc()
    except Exception:
        logger.warning("record_filesystem_scan_cached: metric unavailable", exc_info=True)


def record_workflow_detail_batch_rows(rows: int) -> None:
    """Record a workflow-detail batch query row count observation."""
    if not _initialized:
        return
    safe_rows = max(0, int(rows))
    labels = {"endpoint": "workflow_detail"}
    try:
        if _enabled and _workflow_detail_batch_rows_hist is not None:
            _workflow_detail_batch_rows_hist.record(safe_rows, labels)
        if _prom_enabled and _prom_workflow_detail_batch_rows_hist is not None:
            _prom_workflow_detail_batch_rows_hist.labels(endpoint="workflow_detail").observe(safe_rows)
    except Exception:
        logger.warning("record_workflow_detail_batch_rows: metric unavailable", exc_info=True)


def _observe_telemetry_queue_depth(observation_type: Any):
    def _callback(_options: Any) -> list[Any]:
        return [
            observation_type(
                value,
                {
                    "project_id": project_id,
                    "status": status,
                    "runtime_profile": runtime_profile,
                    "deployment_mode": deployment_mode,
                    "storage_profile": storage_profile,
                },
            )
            for (
                project_id,
                status,
                runtime_profile,
                deployment_mode,
                storage_profile,
            ), value in sorted(_telemetry_queue_depth_state.items())
        ]

    return _callback


def _observe_worker_job_freshness(observation_type: Any):
    def _callback(_options: Any) -> list[Any]:
        return [
            observation_type(
                value,
                {
                    "job_name": job_name,
                    "project_id": project_id,
                    "runtime_profile": runtime_profile,
                    "deployment_mode": deployment_mode,
                    "storage_profile": storage_profile,
                },
            )
            for (
                job_name,
                project_id,
                runtime_profile,
                deployment_mode,
                storage_profile,
            ), value in sorted(_worker_job_freshness_state.items())
        ]

    return _callback


def _observe_worker_job_backpressure(observation_type: Any):
    def _callback(_options: Any) -> list[Any]:
        return [
            observation_type(
                value,
                {
                    "job_name": job_name,
                    "project_id": project_id,
                    "runtime_profile": runtime_profile,
                    "deployment_mode": deployment_mode,
                    "storage_profile": storage_profile,
                },
            )
            for (
                job_name,
                project_id,
                runtime_profile,
                deployment_mode,
                storage_profile,
            ), value in sorted(_worker_job_backpressure_state.items())
        ]

    return _callback


def _observe_telemetry_disabled(observation_type: Any):
    def _callback(_options: Any) -> list[Any]:
        return [observation_type(_telemetry_export_disabled_state)]

    return _callback
