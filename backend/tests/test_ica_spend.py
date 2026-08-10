"""Unit tests for the ICA key + spend attribution logic (v51).

Covers the pure module (:mod:`backend.parsers.ica_spend`), the capture-sidecar
v3 reader path, and the SQLite repository's ``backfill_ica_spend_attribution``
against a live migrated in-memory DB.

Contract anchors:
  * "never silently divided" (AC3) is enforced structurally --
    ``concurrent_shared_key`` and ``key_changed`` verdicts carry ``delta=None``.
  * ``ica_key`` unset stays NULL, never defaulted to CC1 (AC1).
  * Raw start/end readings are stored verbatim (AC2).
  * ``_apply_launch_capture`` surfaces every field camelCase for the API/TS
    contract, with ``None`` == "Not captured" (AC4 fallback).
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.ica_spend import (
    ICA_SPEND_ATTRIBUTED,
    ICA_SPEND_ATTRIBUTION_VOCAB,
    ICA_SPEND_CONCURRENT_SHARED_KEY,
    ICA_SPEND_INCOMPLETE_READINGS,
    ICA_SPEND_KEY_CHANGED,
    decide_attribution,
    parse_spend_reading,
    windows_overlap,
)
from backend.parsers.capture_sidecar import parse_capture_sidecar


class ParseSpendReadingTests(unittest.TestCase):
    def test_parses_positive_float(self) -> None:
        self.assertEqual(parse_spend_reading("9783.87190178"), 9783.87190178)

    def test_none_and_empty_are_null(self) -> None:
        self.assertIsNone(parse_spend_reading(None))
        self.assertIsNone(parse_spend_reading(""))
        self.assertIsNone(parse_spend_reading("   "))

    def test_garbage_is_null(self) -> None:
        self.assertIsNone(parse_spend_reading("x"))

    def test_negative_is_rejected(self) -> None:
        # A cumulative counter cannot be negative -- corrupt, not a small spend.
        self.assertIsNone(parse_spend_reading("-1"))


class DecideAttributionTests(unittest.TestCase):
    def test_attributed_computes_delta(self) -> None:
        v = decide_attribution(start_reading="100.0", end_reading="100.5")
        self.assertEqual(v.attribution, ICA_SPEND_ATTRIBUTED)
        self.assertEqual(v.delta, 0.5)
        self.assertEqual(v.delta_str, "0.5")

    def test_missing_readings_are_incomplete(self) -> None:
        self.assertEqual(
            decide_attribution(start_reading=None, end_reading="100").attribution,
            ICA_SPEND_INCOMPLETE_READINGS,
        )
        self.assertIsNone(
            decide_attribution(start_reading=None, end_reading="100").delta
        )

    def test_counter_backwards_is_incomplete(self) -> None:
        # end < start on the same key -> corrupt reading, not a negative spend.
        v = decide_attribution(start_reading="200", end_reading="100")
        self.assertEqual(v.attribution, ICA_SPEND_INCOMPLETE_READINGS)
        self.assertIsNone(v.delta)

    def test_key_changed_beats_overlap(self) -> None:
        # AC3 shape: if the identity itself moved, that's the reason -- not
        # sibling contamination. Precedence prevents mislabelling.
        v = decide_attribution(
            start_reading="1", end_reading="2",
            key_changed=True, shared_key_overlap=True,
        )
        self.assertEqual(v.attribution, ICA_SPEND_KEY_CHANGED)
        self.assertIsNone(v.delta)

    def test_shared_overlap_yields_null_delta(self) -> None:
        v = decide_attribution(
            start_reading="100", end_reading="105", shared_key_overlap=True,
        )
        self.assertEqual(v.attribution, ICA_SPEND_CONCURRENT_SHARED_KEY)
        # "Never silently divided" is structural: no code path emits a partial
        # attributable delta on a contaminated window.
        self.assertIsNone(v.delta)
        self.assertIsNone(v.delta_str)

    def test_attribution_vocab_is_closed(self) -> None:
        # Writers only emit these four; consumers must still tolerate unknown
        # tokens (documented in module docstring).
        self.assertEqual(
            ICA_SPEND_ATTRIBUTION_VOCAB,
            frozenset({
                ICA_SPEND_ATTRIBUTED,
                ICA_SPEND_CONCURRENT_SHARED_KEY,
                ICA_SPEND_KEY_CHANGED,
                ICA_SPEND_INCOMPLETE_READINGS,
            }),
        )


class WindowsOverlapTests(unittest.TestCase):
    def test_true_overlap(self) -> None:
        self.assertTrue(
            windows_overlap(
                "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z",
                "2026-01-01T00:30:00Z", "2026-01-01T02:00:00Z",
            )
        )

    def test_touching_is_not_overlap(self) -> None:
        # Half-open [start, end): A ends exactly when B begins -> no overlap.
        self.assertFalse(
            windows_overlap(
                "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z",
                "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z",
            )
        )

    def test_missing_start_is_conservative(self) -> None:
        # Cannot establish separation -> assume overlap (fail-safe).
        self.assertTrue(windows_overlap(None, "x", "2026", "2027"))


class CaptureSidecarV3Tests(unittest.TestCase):
    """The reader must accept v3 sidecars and expose the new fields; v1/v2
    stay parseable with the new fields null (forward-compat contract)."""

    def _write(self, payload: dict) -> Path:
        td = Path(tempfile.mkdtemp())
        p = td / "sess.capture.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_v3_parses_ica_fields(self) -> None:
        p = self._write({
            "schemaVersion": 3,
            "sessionId": "sid",
            "icaKey": "CC3",
            "icaSpendStart": "100.0",
            "icaSpendEnd": "100.5",
        })
        sc = parse_capture_sidecar(p)
        self.assertIsNotNone(sc)
        assert sc is not None
        self.assertEqual(sc.ica_key, "CC3")
        self.assertEqual(sc.ica_spend_start, "100.0")
        self.assertEqual(sc.ica_spend_end, "100.5")

    def test_v2_still_parses_with_null_ica(self) -> None:
        # A pre-v3 sidecar keeps working; ica_* fields simply stay None.
        p = self._write({
            "schemaVersion": 2,
            "sessionId": "sid",
            "launcher": "ica-claude.sh",
        })
        sc = parse_capture_sidecar(p)
        self.assertIsNotNone(sc)
        assert sc is not None
        self.assertIsNone(sc.ica_key)
        self.assertIsNone(sc.ica_spend_start)
        self.assertIsNone(sc.ica_spend_end)

    def test_empty_ica_key_string_is_null(self) -> None:
        # Empty string in the sidecar must not defeat AC1 (never defaulted).
        p = self._write({"schemaVersion": 3, "sessionId": "sid", "icaKey": "   "})
        sc = parse_capture_sidecar(p)
        assert sc is not None
        self.assertIsNone(sc.ica_key)


class RepoBackfillAttributionTests(unittest.TestCase):
    """End-to-end: real migrated SQLite, real upsert path, real backfill."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def setUp(self) -> None:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_attribution_and_idempotency(self) -> None:
        import aiosqlite
        from backend.db.sqlite_migrations import run_migrations
        from backend.db.repositories.sessions import SqliteSessionRepository

        async def go():
            td = Path(tempfile.mkdtemp())
            db = await aiosqlite.connect(str(td / "t.db"))
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout = 30000")
            await run_migrations(db)
            repo = SqliteSessionRepository(db)
            pid = "proj1"

            def sess(sid, key, start, end, s0, s1):
                return {
                    "id": sid, "task_id": "", "status": "completed", "model": "m",
                    "started_at": start, "ended_at": end,
                    "icaKey": key, "icaSpendStart": s0, "icaSpendEnd": s1,
                }

            # A: exclusive key -> attributed delta.
            await repo.upsert(sess("A", "CC1", "2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z", "100.0", "100.5"), pid)
            # B, C: share key with overlap -> both unattributable.
            await repo.upsert(sess("B", "CC2", "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", "200.0", "205.0"), pid)
            await repo.upsert(sess("C", "CC2", "2026-01-01T00:10:00Z", "2026-01-01T00:20:00Z", "205.0", "205.5"), pid)
            # D: null key -> ignored (AC1: never defaulted).
            await repo.upsert(sess("D", None, "2026-01-01T01:00:00Z", "2026-01-01T01:05:00Z", None, None), pid)
            # E: no end reading -> untouched (incomplete).
            await repo.upsert(sess("E", "CC3", "2026-01-01T02:00:00Z", "2026-01-01T02:05:00Z", "300.0", None), pid)

            r1 = await repo.backfill_ica_spend_attribution(pid)
            r2 = await repo.backfill_ica_spend_attribution(pid)

            async def get(sid):
                async with db.execute(
                    "SELECT ica_key, ica_spend_delta, ica_spend_attribution "
                    "FROM sessions WHERE project_id=? AND id=?",
                    (pid, sid),
                ) as c:
                    return await c.fetchone()

            a = await get("A"); b = await get("B"); c = await get("C")
            d = await get("D"); e = await get("E")
            await db.close()
            return r1, r2, a, b, c, d, e

        r1, r2, a, b, c, d, e = self._run(go())
        self.assertGreater(r1["rows"], 0)
        self.assertEqual(r2["rows"], 0, "backfill must be idempotent")
        assert a is not None and b is not None and c is not None and d is not None and e is not None
        self.assertEqual(a["ica_spend_attribution"], "attributed")
        self.assertEqual(a["ica_spend_delta"], "0.5")
        # AC3: contaminated windows never divide -- delta stays NULL.
        self.assertEqual(b["ica_spend_attribution"], "concurrent_shared_key")
        self.assertIsNone(b["ica_spend_delta"])
        self.assertEqual(c["ica_spend_attribution"], "concurrent_shared_key")
        self.assertIsNone(c["ica_spend_delta"])
        # AC1: unset key stays NULL (never defaulted to CC1).
        self.assertIsNone(d["ica_key"])
        # Incomplete readings -> untouched by backfill (not falsely attributed).
        self.assertIsNone(e["ica_spend_delta"])
        self.assertIsNone(e["ica_spend_attribution"])


class SessionDetailExposureTests(unittest.TestCase):
    """AC4: session detail exposes camelCase with null == "Not captured"."""

    def test_populated_row_surfaces_camelcase(self) -> None:
        from backend.application.services.agent_queries.session_detail import (
            _apply_launch_capture,
        )
        payload = {
            "ica_key": "CC1",
            "ica_spend_start": "100.0",
            "ica_spend_end": "100.5",
            "ica_spend_delta": "0.5",
            "ica_spend_attribution": "attributed",
        }
        _apply_launch_capture(payload)
        self.assertEqual(payload["icaKey"], "CC1")
        self.assertEqual(payload["icaSpendStart"], "100.0")
        self.assertEqual(payload["icaSpendEnd"], "100.5")
        self.assertEqual(payload["icaSpendDelta"], "0.5")
        self.assertEqual(payload["icaSpendAttribution"], "attributed")

    def test_absent_fields_stay_null(self) -> None:
        from backend.application.services.agent_queries.session_detail import (
            _apply_launch_capture,
        )
        empty: dict = {}
        _apply_launch_capture(empty)
        # None == "Not captured" -- FE renders the fallback (AC4).
        self.assertIsNone(empty["icaKey"])
        self.assertIsNone(empty["icaSpendStart"])
        self.assertIsNone(empty["icaSpendEnd"])
        self.assertIsNone(empty["icaSpendDelta"])
        self.assertIsNone(empty["icaSpendAttribution"])


if __name__ == "__main__":
    unittest.main()
