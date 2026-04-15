"""Smoke tests for agent-query cache OTel counter helpers (CACHE-008)."""
from __future__ import annotations


def test_record_cache_hit_importable_and_callable() -> None:
    """record_cache_hit must be importable and must not raise when called."""
    from backend.observability.otel import record_cache_hit

    # Telemetry is disabled in the test environment, so this is a safe no-op.
    record_cache_hit("project_status")
    record_cache_hit("feature_forensics")
    record_cache_hit("")  # empty endpoint should not raise


def test_record_cache_miss_importable_and_callable() -> None:
    """record_cache_miss must be importable and must not raise when called."""
    from backend.observability.otel import record_cache_miss

    record_cache_miss("project_status")
    record_cache_miss("feature_forensics")
    record_cache_miss("")  # empty endpoint should not raise


def test_both_helpers_importable_together() -> None:
    """Both helpers can be imported in the same statement without conflict."""
    from backend.observability.otel import record_cache_hit, record_cache_miss  # noqa: F401
