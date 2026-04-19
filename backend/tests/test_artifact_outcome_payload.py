"""Unit tests for ArtifactOutcomePayload and ArtifactVersionOutcomePayload (CC-4)."""
import uuid
import unittest
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models import ArtifactOutcomePayload, ArtifactVersionOutcomePayload


_VALID_HASH = "sha256:" + "a" * 64  # 71 chars total (max allowed)
_BARE_HEX_HASH = "f" * 64           # 64 chars bare hex (min allowed)

_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
_END = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)


def _base_payload(**overrides) -> dict:
    return {
        "event_id": uuid.uuid4(),
        "definition_type": "skill",
        "external_id": "skill:my-skill",
        "period_label": "7d",
        "period_start": _START,
        "period_end": _END,
        "execution_count": 10,
        "success_count": 8,
        "failure_count": 2,
        "token_input": 1000,
        "token_output": 500,
        "cost_usd": 0.05,
        "duration_ms": 3000,
        "timestamp": _NOW,
        **overrides,
    }


class TestArtifactOutcomePayloadHappyPath(unittest.TestCase):
    def test_valid_payload_constructs(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        assert payload.definition_type == "skill"
        assert payload.external_id == "skill:my-skill"
        assert payload.execution_count == 10
        assert payload.cost_usd == 0.05

    def test_optional_fields_default_to_none(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        assert payload.content_hash is None
        assert payload.attributed_tokens is None
        assert payload.ccdash_client_version is None
        assert payload.extra_metrics is None

    def test_with_optional_content_hash(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload(content_hash=_VALID_HASH))
        assert payload.content_hash == _VALID_HASH

    def test_with_bare_hex_content_hash(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload(content_hash=_BARE_HEX_HASH))
        assert payload.content_hash == _BARE_HEX_HASH

    def test_zero_counts_accepted(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload(
            execution_count=0, success_count=0, failure_count=0,
            token_input=0, token_output=0, cost_usd=0.0, duration_ms=0,
        ))
        assert payload.execution_count == 0


class TestArtifactOutcomePayloadValidationErrors(unittest.TestCase):
    def test_rejects_negative_execution_count(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(execution_count=-1))

    def test_rejects_negative_success_count(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(success_count=-1))

    def test_rejects_negative_failure_count(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(failure_count=-1))

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(cost_usd=-0.01))

    def test_rejects_negative_token_input(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(token_input=-1))

    def test_rejects_negative_token_output(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(token_output=-1))

    def test_rejects_negative_duration_ms(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(duration_ms=-1))

    def test_rejects_empty_definition_type(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(definition_type=""))

    def test_rejects_empty_external_id(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(external_id=""))

    def test_rejects_empty_period_label(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(period_label=""))

    def test_rejects_content_hash_too_short(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(content_hash="abc"))

    def test_rejects_content_hash_too_long(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactOutcomePayload(**_base_payload(content_hash="x" * 72))


class TestArtifactOutcomePayloadDatetimeSerialization(unittest.TestCase):
    def test_period_start_serialized_with_z_suffix(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        d = payload.event_dict()
        assert d["period_start"].endswith("Z"), f"expected Z suffix, got: {d['period_start']}"
        assert "+" not in d["period_start"]

    def test_period_end_serialized_with_z_suffix(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        d = payload.event_dict()
        assert d["period_end"].endswith("Z"), f"expected Z suffix, got: {d['period_end']}"

    def test_timestamp_serialized_with_z_suffix(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        d = payload.event_dict()
        assert d["timestamp"].endswith("Z"), f"expected Z suffix, got: {d['timestamp']}"

    def test_microseconds_stripped(self) -> None:
        ts_with_micros = datetime(2026, 4, 17, 12, 0, 0, 123456, tzinfo=timezone.utc)
        payload = ArtifactOutcomePayload(**_base_payload(timestamp=ts_with_micros))
        d = payload.event_dict()
        assert "." not in d["timestamp"], "microseconds should be stripped"


class TestEventDictExcludesNoneFields(unittest.TestCase):
    def test_none_optional_fields_excluded(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload())
        d = payload.event_dict()
        assert "content_hash" not in d
        assert "attributed_tokens" not in d
        assert "ccdash_client_version" not in d
        assert "extra_metrics" not in d

    def test_present_optional_fields_included(self) -> None:
        payload = ArtifactOutcomePayload(**_base_payload(
            content_hash=_VALID_HASH,
            attributed_tokens=42,
            ccdash_client_version="1.2.3",
            extra_metrics={"custom_key": "value"},
        ))
        d = payload.event_dict()
        assert d["content_hash"] == _VALID_HASH
        assert d["attributed_tokens"] == 42
        assert d["ccdash_client_version"] == "1.2.3"
        assert d["extra_metrics"] == {"custom_key": "value"}


class TestArtifactVersionOutcomePayload(unittest.TestCase):
    def test_requires_content_hash(self) -> None:
        """content_hash is required on ArtifactVersionOutcomePayload."""
        with pytest.raises(ValidationError):
            ArtifactVersionOutcomePayload(**_base_payload())  # no content_hash

    def test_requires_content_hash_not_none(self) -> None:
        """Passing content_hash=None explicitly should also fail."""
        with pytest.raises(ValidationError):
            ArtifactVersionOutcomePayload(**_base_payload(content_hash=None))

    def test_valid_with_content_hash(self) -> None:
        payload = ArtifactVersionOutcomePayload(**_base_payload(content_hash=_VALID_HASH))
        assert payload.content_hash == _VALID_HASH

    def test_inherits_validation_from_parent(self) -> None:
        """ArtifactVersionOutcomePayload still rejects negative counts."""
        with pytest.raises(ValidationError):
            ArtifactVersionOutcomePayload(**_base_payload(
                content_hash=_VALID_HASH, execution_count=-1
            ))

    def test_event_dict_includes_content_hash(self) -> None:
        payload = ArtifactVersionOutcomePayload(**_base_payload(content_hash=_BARE_HEX_HASH))
        d = payload.event_dict()
        assert d["content_hash"] == _BARE_HEX_HASH

    def test_is_subclass_of_artifact_outcome_payload(self) -> None:
        assert issubclass(ArtifactVersionOutcomePayload, ArtifactOutcomePayload)


if __name__ == "__main__":
    unittest.main()
