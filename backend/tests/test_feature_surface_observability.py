"""Tests for feature-surface observability hooks (P5-003).

Verifies that:
1. record_feature_surface_request increments the OTEL counter and histogram
   when OTEL metrics are enabled.
2. The _result_count_bucket and _payload_bytes_bucket helpers produce the
   correct cardinality-safe bucket labels.
3. The instrument_feature_surface context manager calls
   record_feature_surface_request exactly once per use.
4. Budget warn-log is emitted when thresholds are exceeded.
"""
from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock, patch


class TestBucketHelpers(unittest.TestCase):
    """Unit-test the pure bucket-mapping functions in otel.py."""

    def setUp(self):
        from backend.observability import otel
        self.otel = otel

    def test_result_count_bucket_empty(self):
        self.assertEqual(self.otel._result_count_bucket(0), "empty")
        self.assertEqual(self.otel._result_count_bucket(-1), "empty")

    def test_result_count_bucket_small(self):
        self.assertEqual(self.otel._result_count_bucket(1), "small")
        self.assertEqual(self.otel._result_count_bucket(10), "small")

    def test_result_count_bucket_medium(self):
        self.assertEqual(self.otel._result_count_bucket(11), "medium")
        self.assertEqual(self.otel._result_count_bucket(100), "medium")

    def test_result_count_bucket_large(self):
        self.assertEqual(self.otel._result_count_bucket(101), "large")
        self.assertEqual(self.otel._result_count_bucket(10000), "large")

    def test_payload_bytes_bucket_empty(self):
        self.assertEqual(self.otel._payload_bytes_bucket(0), "empty")

    def test_payload_bytes_bucket_small(self):
        self.assertEqual(self.otel._payload_bytes_bucket(1), "small")
        self.assertEqual(self.otel._payload_bytes_bucket(9_999), "small")

    def test_payload_bytes_bucket_medium(self):
        self.assertEqual(self.otel._payload_bytes_bucket(10_000), "medium")
        self.assertEqual(self.otel._payload_bytes_bucket(99_999), "medium")

    def test_payload_bytes_bucket_large(self):
        self.assertEqual(self.otel._payload_bytes_bucket(100_000), "large")
        self.assertEqual(self.otel._payload_bytes_bucket(499_999), "large")

    def test_payload_bytes_bucket_xlarge(self):
        self.assertEqual(self.otel._payload_bytes_bucket(500_000), "xlarge")


class TestRecordFeatureSurfaceRequest(unittest.TestCase):
    """Verify counter + histogram are called when OTEL metrics are enabled."""

    def _make_mock_counter(self):
        m = MagicMock()
        m.add = MagicMock()
        return m

    def _make_mock_hist(self):
        m = MagicMock()
        m.record = MagicMock()
        return m

    def test_counter_and_histogram_incremented(self):
        """Counter.add and histogram.record are called once per invocation."""
        from backend.observability import otel

        mock_counter = self._make_mock_counter()
        mock_hist = self._make_mock_hist()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_feature_surface_requests_counter", mock_counter),
            patch.object(otel, "_feature_surface_latency_hist", mock_hist),
            patch.object(otel, "_prom_enabled", False),
        ):
            otel.record_feature_surface_request(
                endpoint="list",
                filter_kind="status_only",
                result_count=5,
                payload_bytes=4_000,
                duration_ms=42.0,
            )

        mock_counter.add.assert_called_once()
        call_args = mock_counter.add.call_args
        self.assertEqual(call_args[0][0], 1)  # count arg
        labels = call_args[0][1]
        self.assertEqual(labels["endpoint"], "list")
        self.assertEqual(labels["filter_kind"], "status_only")
        self.assertEqual(labels["result_count_bucket"], "small")
        self.assertEqual(labels["payload_bytes_bucket"], "small")

        mock_hist.record.assert_called_once()
        hist_args = mock_hist.record.call_args
        self.assertAlmostEqual(hist_args[0][0], 42.0)

    def test_no_error_when_otel_disabled(self):
        """record_feature_surface_request must not raise when OTEL is disabled."""
        from backend.observability import otel

        with (
            patch.object(otel, "_enabled", False),
            patch.object(otel, "_feature_surface_requests_counter", None),
            patch.object(otel, "_feature_surface_latency_hist", None),
            patch.object(otel, "_prom_enabled", False),
        ):
            # Should not raise
            otel.record_feature_surface_request(
                endpoint="detail",
                filter_kind="none",
                result_count=1,
                payload_bytes=8_000,
                duration_ms=10.0,
            )

    def test_negative_duration_clamped_to_zero(self):
        """Negative durations must be clamped to 0 before recording."""
        from backend.observability import otel

        mock_hist = self._make_mock_hist()
        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_feature_surface_requests_counter", self._make_mock_counter()),
            patch.object(otel, "_feature_surface_latency_hist", mock_hist),
            patch.object(otel, "_prom_enabled", False),
        ):
            otel.record_feature_surface_request(
                endpoint="list",
                filter_kind="none",
                result_count=0,
                payload_bytes=0,
                duration_ms=-5.0,
            )
        hist_args = mock_hist.record.call_args
        self.assertGreaterEqual(hist_args[0][0], 0.0)


class TestInstrumentFeatureSurface(unittest.TestCase):
    """Verify the context manager calls record_feature_surface_request."""

    def test_record_called_on_exit(self):
        from backend.observability.feature_surface import instrument_feature_surface
        from backend.observability import otel

        called_with: list[dict] = []

        def fake_record(**kwargs):
            called_with.append(kwargs)

        with (
            patch.object(otel, "record_feature_surface_request", fake_record),
            patch.object(otel, "_enabled", False),  # skip span creation
        ):
            with instrument_feature_surface("list", filter_kind="none") as ctx:
                ctx.set_result(items=3, payload_bytes=1200)

        self.assertEqual(len(called_with), 1)
        rec = called_with[0]
        self.assertEqual(rec["endpoint"], "list")
        self.assertEqual(rec["filter_kind"], "none")
        self.assertEqual(rec["result_count"], 3)
        self.assertEqual(rec["payload_bytes"], 1200)
        self.assertGreaterEqual(rec["duration_ms"], 0.0)

    def test_record_called_on_exception(self):
        """Metrics must still be recorded even when the body raises."""
        from backend.observability.feature_surface import instrument_feature_surface
        from backend.observability import otel

        called = []

        def fake_record(**kwargs):
            called.append(kwargs)

        with patch.object(otel, "record_feature_surface_request", fake_record):
            with patch.object(otel, "_enabled", False):
                try:
                    with instrument_feature_surface("detail", filter_kind="none") as ctx:
                        ctx.set_result(items=1, payload_bytes=500)
                        raise ValueError("simulated error")
                except ValueError:
                    pass

        self.assertEqual(len(called), 1)

    def test_budget_warn_emitted_on_latency_overrun(self):
        """A WARN log is emitted when the request exceeds the latency budget."""
        import time
        from backend.observability.feature_surface import instrument_feature_surface
        from backend.observability import otel

        with (
            patch.object(otel, "record_feature_surface_request", lambda **_: None),
            patch.object(otel, "_enabled", False),
        ):
            with self.assertLogs("ccdash.features.observability", level="WARNING") as log_ctx:
                with instrument_feature_surface(
                    "list",
                    filter_kind="none",
                    latency_budget_ms=0.001,  # extremely tight budget
                ) as ctx:
                    ctx.set_result(items=1, payload_bytes=100)
                    time.sleep(0.002)

        self.assertTrue(
            any("budget exceeded" in line for line in log_ctx.output),
            "Expected 'budget exceeded' warning in log output",
        )

    def test_no_warn_within_budget(self):
        """No WARN log when the request is within budget."""
        from backend.observability.feature_surface import instrument_feature_surface
        from backend.observability import otel

        with (
            patch.object(otel, "record_feature_surface_request", lambda **_: None),
            patch.object(otel, "_enabled", False),
        ):
            # assertLogs raises AssertionError if no logs at given level are emitted
            import logging as _logging
            with self.assertRaises(AssertionError):
                with self.assertLogs("ccdash.features.observability", level="WARNING"):
                    with instrument_feature_surface(
                        "list",
                        filter_kind="none",
                        latency_budget_ms=60_000,  # 60 s — will never trigger
                        payload_budget_bytes=10_000_000,
                    ) as ctx:
                        ctx.set_result(items=1, payload_bytes=100)


class TestClassifyFilterKind(unittest.TestCase):
    """Unit-test _classify_filter_kind helper added to features router."""

    def _fn(self, **kwargs):
        from backend.routers.features import _classify_filter_kind
        return _classify_filter_kind(**kwargs)

    def test_none(self):
        self.assertEqual(self._fn(), "none")
        self.assertEqual(self._fn(status=None, q=None), "none")
        self.assertEqual(self._fn(status="", q=""), "none")

    def test_status_only(self):
        self.assertEqual(self._fn(status="in-progress"), "status_only")

    def test_search_only(self):
        self.assertEqual(self._fn(q="auth"), "search_only")

    def test_both(self):
        self.assertEqual(self._fn(status="in-progress", q="auth"), "both")


if __name__ == "__main__":
    unittest.main()
