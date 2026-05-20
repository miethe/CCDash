"""Tests for the minimal UUID v7 generator."""
from __future__ import annotations

import re

from ccdash_cli.daemon.uuid7 import uuid7

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_uuid7_format() -> None:
    """Generated UUID must match the 8-4-4-4-12 hex format."""
    uid = uuid7()
    assert _UUID_RE.match(uid), f"UUID format mismatch: {uid!r}"


def test_uuid7_version_bits() -> None:
    """Bits 48-51 (version nibble) must equal 7."""
    uid = uuid7()
    # The version nibble is the first character of the third group.
    hex_no_hyphens = uid.replace("-", "")
    version_nibble = hex_no_hyphens[12]
    assert version_nibble == "7", f"Expected version nibble '7', got {version_nibble!r}"


def test_uuid7_variant_bits() -> None:
    """Bits 64-65 (variant) must be 0b10 — i.e. the high byte of group 4 must be 8, 9, a, or b."""
    uid = uuid7()
    # 4th group starts after 8+4+4 = 16 hex chars (plus 3 hyphens) in the string
    fourth_group = uid.split("-")[3]
    high_char = fourth_group[0]
    assert high_char in "89ab", f"Variant bits mismatch: first char of group 4 is {high_char!r}"


def test_uuid7_monotonic_within_process() -> None:
    """1000 consecutive UUIDs must be non-decreasing (lexicographic = chronological)."""
    uids = [uuid7() for _ in range(1000)]
    # Compare as strings: UUID v7 hex strings sort lexicographically = temporally.
    for i in range(1, len(uids)):
        # Allow equal (same ms tick) but not decreasing.
        assert uids[i] >= uids[i - 1], (
            f"UUID at position {i} ({uids[i]!r}) is less than "
            f"previous ({uids[i-1]!r}) — monotonicity violated"
        )


def test_uuid7_uniqueness() -> None:
    """1000 generated UUIDs must all be distinct."""
    uids = [uuid7() for _ in range(1000)]
    assert len(set(uids)) == len(uids), "Duplicate UUIDs detected"


def test_uuid7_lowercase() -> None:
    """Output must be entirely lowercase hex with hyphens."""
    uid = uuid7()
    assert uid == uid.lower(), f"UUID is not lowercase: {uid!r}"
