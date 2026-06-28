"""WAL durability tests for the CCDash daemon write-ahead log."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccdash_cli.daemon.wal import WalBuffer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wal_dir(tmp_path: Path) -> Path:
    return tmp_path / "wal"


@pytest.fixture()
def wal(wal_dir: Path) -> WalBuffer:
    return WalBuffer(wal_dir, max_segment_lines=5, max_segment_bytes=10 * 1024 * 1024)


def _event(idx: int) -> dict:
    return {"event_id": f"evt-{idx:04d}", "payload": {"n": idx}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAppendAndPending:
    def test_single_append_creates_segment(self, wal: WalBuffer, wal_dir: Path) -> None:
        wal.append(_event(0))
        segs = wal.pending_segments()
        assert len(segs) == 1
        assert segs[0].suffix == ".ndjson"

    def test_append_within_limit_single_segment(self, wal: WalBuffer) -> None:
        for i in range(5):
            wal.append(_event(i))
        assert len(wal.pending_segments()) == 1

    def test_rotate_at_line_limit(self, wal: WalBuffer) -> None:
        """Writing more than max_segment_lines (5) must produce a second segment."""
        for i in range(6):
            wal.append(_event(i))
        segs = wal.pending_segments()
        assert len(segs) == 2, f"Expected 2 segments after 6 events, got {len(segs)}"

    def test_pending_segments_sorted_ascending(self, wal: WalBuffer) -> None:
        """Segments must be sorted chronologically (oldest first)."""
        for i in range(12):  # 3 segments of 5, 5, 2
            wal.append(_event(i))
        segs = wal.pending_segments()
        names = [s.name for s in segs]
        assert names == sorted(names), f"Segments not sorted: {names}"


class TestPeekSegment:
    def test_peek_round_trips(self, wal: WalBuffer) -> None:
        for i in range(3):
            wal.append(_event(i))
        seg = wal.pending_segments()[0]
        events = wal.peek_segment(seg)
        assert len(events) == 3
        for i, ev in enumerate(events):
            assert ev["event_id"] == f"evt-{i:04d}"

    def test_peek_does_not_delete(self, wal: WalBuffer) -> None:
        wal.append(_event(0))
        seg = wal.pending_segments()[0]
        wal.peek_segment(seg)
        assert seg.exists()

    def test_peek_missing_file(self, wal: WalBuffer, tmp_path: Path) -> None:
        ghost = tmp_path / "ghost.ndjson"
        assert wal.peek_segment(ghost) == []


class TestAckSegment:
    def test_ack_removes_segment(self, wal: WalBuffer) -> None:
        wal.append(_event(0))
        seg = wal.pending_segments()[0]
        wal.ack_segment(seg)
        assert not seg.exists()
        assert wal.pending_segments() == []

    def test_ack_missing_is_noop(self, wal: WalBuffer, tmp_path: Path) -> None:
        ghost = tmp_path / "ghost.ndjson"
        # Should not raise.
        wal.ack_segment(ghost)


class TestPartialAck:
    def test_partial_ack_rewrites_subset(self, wal: WalBuffer) -> None:
        for i in range(4):
            wal.append(_event(i))
        seg = wal.pending_segments()[0]

        # Accept events 0 and 2; events 1 and 3 should remain.
        wal.partial_ack(seg, accepted_event_ids={"evt-0000", "evt-0002"})

        assert seg.exists()
        remaining = wal.peek_segment(seg)
        ids = {e["event_id"] for e in remaining}
        assert ids == {"evt-0001", "evt-0003"}

    def test_partial_ack_all_removes_segment(self, wal: WalBuffer) -> None:
        for i in range(3):
            wal.append(_event(i))
        seg = wal.pending_segments()[0]
        all_ids = {f"evt-{i:04d}" for i in range(3)}
        wal.partial_ack(seg, accepted_event_ids=all_ids)
        assert not seg.exists()


class TestDepth:
    def test_depth_counts_all_lines(self, wal: WalBuffer) -> None:
        for i in range(7):  # 5 in seg1, 2 in seg2
            wal.append(_event(i))
        assert wal.depth() == 7

    def test_depth_decreases_after_ack(self, wal: WalBuffer) -> None:
        for i in range(7):
            wal.append(_event(i))
        segs = wal.pending_segments()
        wal.ack_segment(segs[0])
        assert wal.depth() == 2

    def test_depth_empty(self, wal: WalBuffer) -> None:
        assert wal.depth() == 0


class TestDurability:
    def test_write_kill_reopen_peek(self, wal_dir: Path) -> None:
        """Events persisted in one WalBuffer instance must survive re-open."""
        wal1 = WalBuffer(wal_dir, max_segment_lines=5, max_segment_bytes=10 * 1024 * 1024)
        for i in range(3):
            wal1.append(_event(i))
        # Simulate process restart: create a new WalBuffer pointing to same dir.
        wal2 = WalBuffer(wal_dir, max_segment_lines=5, max_segment_bytes=10 * 1024 * 1024)
        segs = wal2.pending_segments()
        assert segs, "No segments found after re-open"
        events = wal2.peek_segment(segs[0])
        assert len(events) == 3
        assert events[0]["event_id"] == "evt-0000"

    def test_byte_limit_rotation(self, wal_dir: Path) -> None:
        """Segments should rotate when byte limit is exceeded."""
        # Set a tiny byte limit of 100 bytes.
        wal = WalBuffer(wal_dir, max_segment_lines=10_000, max_segment_bytes=100)
        # Each event is ~30-40 bytes.
        for i in range(10):
            wal.append(_event(i))
        segs = wal.pending_segments()
        assert len(segs) > 1, "Expected byte-limit rotation to create multiple segments"
