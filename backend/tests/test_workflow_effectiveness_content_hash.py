"""Unit tests for _artifact_reference_from_definition content_hash forwarding (CC-1)."""
import unittest

from backend.services.workflow_effectiveness import _artifact_reference_from_definition


class ArtifactReferenceContentHashTests(unittest.TestCase):
    """Verify _artifact_reference_from_definition surfaces content_hash from definition."""

    _base_definition: dict = {
        "external_id": "skill:my-skill",
        "definition_type": "skill",
        "display_name": "My Skill",
        "source_url": "https://example.com/skill",
    }

    def test_content_hash_from_definition_added_to_metadata(self) -> None:
        """content_hash present in definition is forwarded into metadata."""
        definition = {
            **self._base_definition,
            "content_hash": "sha256:" + "a" * 64,
        }
        ref = _artifact_reference_from_definition(definition, kind="skill")
        assert ref.metadata["content_hash"] == "sha256:" + "a" * 64

    def test_content_hash_not_in_definition_leaves_metadata_empty(self) -> None:
        """When definition has no content_hash, metadata stays empty (or caller-supplied)."""
        ref = _artifact_reference_from_definition(dict(self._base_definition), kind="skill")
        assert "content_hash" not in ref.metadata

    def test_caller_content_hash_not_overwritten(self) -> None:
        """A content_hash already in caller-supplied metadata is NOT overwritten by definition."""
        definition = {
            **self._base_definition,
            "content_hash": "sha256:" + "b" * 64,
        }
        caller_hash = "sha256:" + "c" * 64
        ref = _artifact_reference_from_definition(
            definition, kind="skill", metadata={"content_hash": caller_hash}
        )
        assert ref.metadata["content_hash"] == caller_hash

    def test_caller_metadata_not_mutated(self) -> None:
        """The function must not mutate the caller's metadata dict (copy-on-write)."""
        definition = {
            **self._base_definition,
            "content_hash": "sha256:" + "d" * 64,
        }
        original_metadata: dict = {}
        _artifact_reference_from_definition(definition, kind="skill", metadata=original_metadata)
        assert original_metadata == {}, "caller's metadata dict was mutated"

    def test_content_hash_none_in_definition_not_forwarded(self) -> None:
        """A None content_hash in definition is treated as absent (falsy guard)."""
        definition = {**self._base_definition, "content_hash": None}
        ref = _artifact_reference_from_definition(definition, kind="skill")
        assert "content_hash" not in ref.metadata

    def test_extra_metadata_preserved_alongside_content_hash(self) -> None:
        """Caller metadata keys beyond content_hash are preserved in the output."""
        definition = {
            **self._base_definition,
            "content_hash": "sha256:" + "e" * 64,
        }
        ref = _artifact_reference_from_definition(
            definition, kind="skill", metadata={"source": "github"}
        )
        assert ref.metadata["source"] == "github"
        assert ref.metadata["content_hash"] == "sha256:" + "e" * 64


if __name__ == "__main__":
    unittest.main()
