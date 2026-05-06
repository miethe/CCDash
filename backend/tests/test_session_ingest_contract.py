from __future__ import annotations

from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from backend.ingestion.models import (
    IngestSource,
    MergePolicy,
    NormalizedSessionEnvelope,
    SourceProvenance,
)
from backend.ingestion.registry import IngestAdapterRegistry, IngestSourceAdapter
from backend.ingestion.source_keys import (
    UNRESOLVED_AGGREGATE_SCOPE,
    aggregate_source_key,
    session_event_source_key,
)


def _provenance(
    *,
    source: IngestSource,
    source_identity: str,
    platform_type: str = "claude_code",
    confidence: float = 1.0,
) -> SourceProvenance:
    return SourceProvenance(
        source=source,
        platform_type=platform_type,
        source_identity=source_identity,
        confidence=confidence,
        observed_at=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        attributes={"ingest_adapter": "test"},
    )


def _envelope(
    *,
    session_id: str = "session-123",
    source: IngestSource = IngestSource.JSONL,
    source_identity: str = "claude-jsonl:/sessions/session-123.jsonl",
    platform_type: str = "claude_code",
    confidence: float = 1.0,
    merge_policy: MergePolicy = MergePolicy.UPSERT_COMPLETE,
    provenance: SourceProvenance | None = None,
) -> NormalizedSessionEnvelope:
    return NormalizedSessionEnvelope(
        session_id=session_id,
        source=source,
        merge_policy=merge_policy,
        platform_type=platform_type,
        source_identity=source_identity,
        confidence=confidence,
        provenance=provenance
        or _provenance(
            source=source,
            source_identity=source_identity,
            platform_type=platform_type,
            confidence=confidence,
        ),
        session={"id": session_id, "platformType": "Claude Code"},
        messages=[{"type": "assistant", "timestamp": "2026-05-05T12:00:01Z"}],
        metrics={"tokens.input": 120},
        raw_refs=[source_identity],
    )


class SessionIngestEnvelopeContractTests(unittest.TestCase):
    def test_accepts_valid_claude_code_jsonl_source_metadata(self) -> None:
        envelope = _envelope()

        self.assertEqual(envelope.source, IngestSource.JSONL)
        self.assertEqual(envelope.merge_policy, MergePolicy.UPSERT_COMPLETE)
        self.assertEqual(envelope.platform_type, "claude_code")
        self.assertEqual(envelope.provenance.source_identity, envelope.source_identity)
        self.assertEqual(envelope.messages[0]["type"], "assistant")

    def test_accepts_valid_otel_source_metadata(self) -> None:
        source_identity = "otel:collector-a:resource/session-123"
        envelope = _envelope(
            source=IngestSource.OTEL,
            source_identity=source_identity,
            merge_policy=MergePolicy.PATCH_METRICS,
            provenance=_provenance(
                source=IngestSource.OTEL,
                source_identity=source_identity,
                platform_type="claude_code",
                confidence=0.84,
            ),
            confidence=0.84,
        )

        self.assertEqual(envelope.source, IngestSource.OTEL)
        self.assertEqual(envelope.merge_policy, MergePolicy.PATCH_METRICS)
        self.assertAlmostEqual(envelope.confidence, 0.84)
        self.assertEqual(envelope.provenance.attributes["ingest_adapter"], "test")

    def test_rejects_missing_or_blank_session_ids(self) -> None:
        with self.assertRaises(ValidationError):
            NormalizedSessionEnvelope(
                source=IngestSource.JSONL,
                source_identity="claude-jsonl:/sessions/missing.jsonl",
                provenance=_provenance(
                    source=IngestSource.JSONL,
                    source_identity="claude-jsonl:/sessions/missing.jsonl",
                ),
            )

        with self.assertRaises(ValidationError):
            _envelope(session_id="")

    def test_rejects_provenance_mismatch(self) -> None:
        with self.assertRaisesRegex(ValidationError, "provenance.source must match"):
            _envelope(
                source=IngestSource.JSONL,
                provenance=_provenance(
                    source=IngestSource.OTEL,
                    source_identity="claude-jsonl:/sessions/session-123.jsonl",
                ),
            )

        with self.assertRaisesRegex(ValidationError, "provenance.source_identity must match"):
            _envelope(
                source_identity="claude-jsonl:/sessions/session-123.jsonl",
                provenance=_provenance(
                    source=IngestSource.JSONL,
                    source_identity="claude-jsonl:/sessions/other.jsonl",
                ),
            )


class SessionIngestSourceKeyContractTests(unittest.TestCase):
    def test_session_source_keys_are_deterministic_for_replayed_payloads(self) -> None:
        first = session_event_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            session_id="session-123",
            event_kind="metric.tokens",
            event={
                "timeUnixNano": "1799040000000000000",
                "name": "tokens.input",
                "attributes": {"model": "claude-sonnet", "phase": "phase-1"},
                "value": 120,
            },
        )
        replay = session_event_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            session_id="session-123",
            event_kind="metric.tokens",
            event={
                "value": 120,
                "attributes": {"phase": "phase-1", "model": "claude-sonnet"},
                "name": "tokens.input",
                "timeUnixNano": "1799040000000000000",
            },
        )

        self.assertEqual(first, replay)
        self.assertTrue(str(first).startswith("ccdash-ingest-source:v1/claude_code/otel/session/session-123/metric.tokens/"))

    def test_session_source_keys_change_for_different_signal_or_source_timestamp(self) -> None:
        base_event = {
            "timeUnixNano": "1799040000000000000",
            "name": "tokens.input",
            "value": 120,
        }

        base_key = session_event_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            session_id="session-123",
            event_kind="metric.tokens",
            event=base_event,
        )
        different_signal = session_event_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            session_id="session-123",
            event_kind="metric.cost",
            event={**base_event, "name": "cost.usd"},
        )
        different_timestamp = session_event_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            session_id="session-123",
            event_kind="metric.tokens",
            event={**base_event, "timeUnixNano": "1799040000000000001"},
        )

        self.assertNotEqual(base_key, different_signal)
        self.assertNotEqual(base_key, different_timestamp)

    def test_unresolved_aggregate_source_keys_are_explicit_and_not_session_scoped(self) -> None:
        unresolved = aggregate_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            aggregate_kind="metric.process",
            aggregate_id=None,
            event={"name": "process.cpu.time", "timeUnixNano": "1799040000000000000"},
        )
        blank = aggregate_source_key(
            platform_type="claude_code",
            source=IngestSource.OTEL,
            aggregate_kind="metric.process",
            aggregate_id=" ",
            event={"timeUnixNano": "1799040000000000000", "name": "process.cpu.time"},
        )

        self.assertEqual(unresolved, blank)
        self.assertIn(f"/aggregate/{UNRESOLVED_AGGREGATE_SCOPE}/metric.process/", str(unresolved))
        self.assertNotIn("/session/", str(unresolved))

    def test_session_source_keys_require_resolved_session_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "session_id cannot be blank"):
            session_event_source_key(
                platform_type="claude_code",
                source=IngestSource.OTEL,
                session_id=" ",
                event_kind="metric.tokens",
                event={"name": "tokens.input"},
            )


class IngestAdapterRegistryContractTests(unittest.TestCase):
    def test_registry_uses_adapter_protocol_semantics(self) -> None:
        envelope = _envelope()

        class JsonlAdapter:
            source = IngestSource.JSONL

            def can_accept(self, payload: object) -> bool:
                return isinstance(payload, dict) and payload.get("format") == "jsonl"

            def to_envelopes(self, payload: object) -> list[NormalizedSessionEnvelope]:
                if not self.can_accept(payload):
                    return []
                return [envelope]

        class OtelAdapter:
            source = IngestSource.OTEL

            def can_accept(self, payload: object) -> bool:
                return isinstance(payload, dict) and payload.get("format") == "otel"

            def to_envelopes(self, payload: object) -> list[NormalizedSessionEnvelope]:
                if not self.can_accept(payload):
                    return []
                return [
                    _envelope(
                        source=IngestSource.OTEL,
                        source_identity="otel:collector-a:resource/session-123",
                        merge_policy=MergePolicy.PATCH_METRICS,
                    )
                ]

        jsonl_adapter = JsonlAdapter()
        otel_adapter = OtelAdapter()
        registry = IngestAdapterRegistry([jsonl_adapter, otel_adapter])

        self.assertIsInstance(jsonl_adapter, IngestSourceAdapter)
        self.assertEqual(registry.adapters(source=IngestSource.JSONL), (jsonl_adapter,))
        self.assertIs(registry.find_adapter({"format": "jsonl"}), jsonl_adapter)
        self.assertIs(registry.find_adapter({"format": "otel"}, source=IngestSource.JSONL), None)
        otel_match = registry.find_adapter({"format": "otel"})
        self.assertIsNotNone(otel_match)
        assert otel_match is not None
        self.assertEqual(otel_match.to_envelopes({"format": "otel"})[0].source, IngestSource.OTEL)


if __name__ == "__main__":
    unittest.main()
