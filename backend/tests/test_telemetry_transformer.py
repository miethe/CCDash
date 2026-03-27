import unittest
from datetime import datetime, timezone
from uuid import uuid4

from backend.services.telemetry_transformer import (
    AnonymizationError,
    AnonymizationVerifier,
    TelemetryTransformer,
)


class TelemetryTransformerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transformer = TelemetryTransformer()

    def _session_row(self, **overrides) -> dict:
        row = {
            "id": str(uuid4()),
            "project_id": "ccdash-project",
            "status": "completed",
            "model": "claude-opus-4-5-20251101",
            "tokens_in": 48200,
            "tokens_out": 12800,
            "cache_read_input_tokens": 6400,
            "cache_creation_input_tokens": 3200,
            "display_cost_usd": 0.42,
            "duration_seconds": 1842,
            "ended_at": "2026-03-24T14:32:10Z",
            "context_utilization_pct": 0.78,
            "toolsUsed": [
                {"name": "rg", "count": 20, "successCount": 19},
                {"name": "apply_patch", "count": 17, "successCount": 15},
            ],
            "logs": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "session_forensics_json": {
                "testExecution": {"resultCounts": {"passed": 9, "failed": 1}},
            },
        }
        row.update(overrides)
        return row

    def test_transforms_completed_session(self) -> None:
        payload = self.transformer.transform_session(self._session_row())

        self.assertEqual(payload.project_slug, "ccdash-project")
        self.assertEqual(payload.model_family, "Opus")
        self.assertEqual(payload.tool_call_count, 37)
        self.assertEqual(payload.tool_call_success_count, 34)
        self.assertEqual(payload.outcome_status, "completed")
        self.assertEqual(payload.message_count, 3)
        self.assertAlmostEqual(payload.test_pass_rate or 0.0, 0.9)

    def test_maps_interrupted_status(self) -> None:
        payload = self.transformer.transform_session(self._session_row(status="interrupted"))
        self.assertEqual(payload.outcome_status, "interrupted")

    def test_maps_failed_status_to_errored(self) -> None:
        payload = self.transformer.transform_session(self._session_row(status="failed"))
        self.assertEqual(payload.outcome_status, "errored")

    def test_prefers_metadata_for_workflow_and_feature(self) -> None:
        payload = self.transformer.transform_session(
            self._session_row(),
            {"workflow_type": "feature-implementation", "feature_slug": "auth-token-refresh"},
        )
        self.assertEqual(payload.workflow_type, "feature-implementation")
        self.assertEqual(payload.feature_slug, "auth-token-refresh")

    def test_uses_metadata_counts_when_present(self) -> None:
        payload = self.transformer.transform_session(
            self._session_row(),
            {"tool_call_count": 5, "tool_call_success_count": 4, "message_count": 22},
        )
        self.assertEqual(payload.tool_call_count, 5)
        self.assertEqual(payload.tool_call_success_count, 4)
        self.assertEqual(payload.message_count, 22)

    def test_omits_zero_optional_cache_fields(self) -> None:
        payload = self.transformer.transform_session(
            self._session_row(cache_read_input_tokens=0, cache_creation_input_tokens=0)
        )
        self.assertIsNone(payload.token_cache_read)
        self.assertIsNone(payload.token_cache_write)

    def test_omits_optional_test_pass_rate_when_no_signals_exist(self) -> None:
        payload = self.transformer.transform_session(
            self._session_row(session_forensics_json={}, logs=[])
        )
        self.assertIsNone(payload.test_pass_rate)

    def test_uses_context_utilization_from_row(self) -> None:
        payload = self.transformer.transform_session(self._session_row(context_utilization_pct=0.61))
        self.assertAlmostEqual(payload.context_utilization_peak or 0.0, 0.61)

    def test_uses_generated_event_id_when_not_supplied(self) -> None:
        payload = self.transformer.transform_session(self._session_row())
        self.assertTrue(str(payload.event_id))

    def test_preserves_supplied_event_id(self) -> None:
        event_id = str(uuid4())
        payload = self.transformer.transform_session(self._session_row(), {"event_id": event_id})
        self.assertEqual(str(payload.event_id), event_id)

    def test_serializes_schema_wrapper(self) -> None:
        payload = self.transformer.transform_session(self._session_row())
        serialized = payload.to_json()
        self.assertIn('"schema_version":"1"', serialized)
        self.assertIn('"events":[', serialized)

    def test_normalizes_timestamp_when_timezone_missing(self) -> None:
        payload = self.transformer.transform_session(self._session_row(ended_at="2026-03-24T14:32:10"))
        self.assertEqual(payload.timestamp.tzinfo, timezone.utc)


class AnonymizationVerifierTests(unittest.TestCase):
    def _valid_payload(self) -> dict:
        return {
            "event_id": str(uuid4()),
            "project_slug": "auth-token-refresh",
            "session_id": str(uuid4()),
            "workflow_type": "feature-implementation",
            "model_family": "Opus",
            "token_input": 12,
            "token_output": 7,
            "cost_usd": 0.25,
            "tool_call_count": 3,
            "duration_seconds": 10,
            "message_count": 4,
            "outcome_status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "ccdash_version": "0.1.0",
        }

    def test_accepts_valid_payload(self) -> None:
        AnonymizationVerifier.verify(self._valid_payload())

    def test_rejects_unix_absolute_paths(self) -> None:
        payload = self._valid_payload()
        payload["feature_slug"] = "/Users/miethe/dev/project"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_windows_absolute_paths(self) -> None:
        payload = self._valid_payload()
        payload["workflow_type"] = r"C:\Users\miethe\project"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_email_addresses(self) -> None:
        payload = self._valid_payload()
        payload["project_slug"] = "miethe@example.com"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_sensitive_field_names(self) -> None:
        payload = self._valid_payload()
        payload["api_token"] = "secret"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_python_stack_trace(self) -> None:
        payload = self._valid_payload()
        payload["details"] = 'Traceback (most recent call last):\n  File "/tmp/app.py", line 1'
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_javascript_stack_trace(self) -> None:
        payload = self._valid_payload()
        payload["details"] = "at runTask (/Users/miethe/dev/app.js:10:2)"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_hostname_values(self) -> None:
        payload = self._valid_payload()
        payload["workflow_type"] = "devbox.internal"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_localhost_values(self) -> None:
        payload = self._valid_payload()
        payload["workflow_type"] = "localhost:3000"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_nested_email_values(self) -> None:
        payload = self._valid_payload()
        payload["nested"] = {"owner": "user@company.com"}
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_nested_paths_in_lists(self) -> None:
        payload = self._valid_payload()
        payload["nested"] = {"items": ["/tmp/private.log"]}
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_rejects_last_error_text(self) -> None:
        payload = self._valid_payload()
        payload["last_error"] = "Error: request failed in user workspace"
        with self.assertRaises(AnonymizationError):
            AnonymizationVerifier.verify(payload)

    def test_allows_uuid_timestamp_and_slug_values(self) -> None:
        payload = self._valid_payload()
        payload["feature_slug"] = "feature-rollup-v1"
        AnonymizationVerifier.verify(payload)


if __name__ == "__main__":
    unittest.main()
