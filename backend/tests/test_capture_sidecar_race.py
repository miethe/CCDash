"""Regression: launch-capture sidecar written AFTER the session JSONL settles.

The relay/watcher tails a session ``*.jsonl`` on its first change and parses it.
The launch-capture sidecar (``<session-id>.capture.json``) is a SECOND input to
that parse, and SessionEnd rewrites it ~2s after the transcript stops growing to
add the closing ICA spend reading. Two independent defects made that capture
permanently invisible for fast/one-shot sessions:

1. ``FileWatcher._classify_changes`` dropped the sidecar: ``.capture.json`` has a
   ``.json`` suffix, which fell into ``artifact_suffixes`` and was ``continue``d
   unless it sat inside a test-results dir. A sidecar write triggered nothing.
2. ``SyncEngine._sync_single_session`` keyed its unchanged-skip on the JSONL's
   mtime alone, so even a forwarded event was skipped — the parse had already
   run. (A bare ``touch`` did not help: observed live as a link rebuild with no
   session re-upsert.)

Observed impact before the fix: session 2d7190c6 (JSONL 13:35:04, sidecar
13:35:06) landed in Postgres with ``launcher``/``ica_key``/``ica_spend_*`` all
NULL, while re-parsing the same file by hand returned ``icaKey='CC3'``.

Run as a NAMED file::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_capture_sidecar_race.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from watchfiles import Change

from backend.db.file_watcher import FileWatcher
from backend.db.sync_engine import _session_input_mtime
from backend.parsers.sessions import parse_session_file

SESSION_ID = "2d7190c6-98a5-40d5-b65a-171f4f874815"


def _write_jsonl(sessions_dir: Path, session_id: str) -> Path:
    """A minimal but real two-turn transcript the parser accepts."""
    path = sessions_dir / f"{session_id}.jsonl"
    rows = [
        {
            "type": "user",
            "timestamp": "2026-08-10T17:34:54.864Z",
            "uuid": "u1",
            "message": {"role": "user", "content": "reply with the single word: ok"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-08-10T17:35:04.000Z",
            "uuid": "a1",
            "parentUuid": "u1",
            "message": {
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [{"type": "text", "text": "ok"}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _write_sidecar(sessions_dir: Path, session_id: str, *, with_end: bool) -> Path:
    """Write a schemaVersion=3 sidecar; ``with_end`` mimics the SessionEnd pass."""
    path = sessions_dir / f"{session_id}.capture.json"
    payload = {
        "schemaVersion": 3,
        "sessionId": session_id,
        "launcher": "ica-claude.sh",
        "profile": "ica-delegate",
        "modelVariant": "claude-haiku-4-5",
        "icaKey": "CC3",
        "icaSpendStart": "10286.435116354993",
        "icaSpendEnd": "10285.725025579992" if with_end else None,
    }
    path.write_text(json.dumps(payload))
    return path


class SidecarFreshnessKeyTests(unittest.TestCase):
    """``_session_input_mtime`` must fold the sidecar into the skip's key."""

    def test_absent_sidecar_key_equals_plain_jsonl_mtime(self) -> None:
        """No sidecar must not change existing behaviour (or the key inflates)."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)
            self.assertEqual(_session_input_mtime(jsonl), jsonl.stat().st_mtime)

    def test_late_sidecar_advances_the_key(self) -> None:
        """The exact race: sidecar mtime strictly newer than the JSONL's."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)
            before = _session_input_mtime(jsonl)

            sidecar = _write_sidecar(sessions_dir, SESSION_ID, with_end=True)
            # Force the observed ordering deterministically rather than sleeping.
            os.utime(sidecar, (before + 2, before + 2))

            after = _session_input_mtime(jsonl)
            self.assertGreater(
                after,
                before,
                "A sidecar landing after the JSONL must advance the freshness key, "
                "otherwise _sync_single_session's unchanged-skip drops the capture "
                "forever.",
            )
            self.assertEqual(after, sidecar.stat().st_mtime)

    def test_key_is_stable_once_sidecar_is_accounted_for(self) -> None:
        """Must converge: re-reading the key twice yields the same value.

        Guards the churn failure mode — if the compare used max(...) while the
        store used the JSONL mtime, every pass would re-parse the file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)
            _write_sidecar(sessions_dir, SESSION_ID, with_end=True)
            self.assertEqual(_session_input_mtime(jsonl), _session_input_mtime(jsonl))


class SidecarWatcherRoutingTests(unittest.TestCase):
    """A sidecar write must be forwarded as its sibling JSONL — and only that."""

    def setUp(self) -> None:
        self.watcher = FileWatcher()

    def test_sidecar_write_is_routed_to_sibling_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)
            sidecar = _write_sidecar(sessions_dir, SESSION_ID, with_end=True)

            classified = self.watcher._classify_changes(
                {(Change.modified, str(sidecar))},
                None,
                None,
                sessions_dir=sessions_dir,
            )

            self.assertEqual(
                classified,
                [("modified", jsonl)],
                "A .capture.json write must be forwarded as its sibling JSONL so "
                "the session is re-parsed with capture available.",
            )

    def test_sidecar_itself_is_never_forwarded(self) -> None:
        """Nothing downstream parses a .capture.json as a session source."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            sidecar = _write_sidecar(sessions_dir, SESSION_ID, with_end=True)
            # No sibling JSONL on disk → nothing to re-parse, and the sidecar
            # must not be emitted in its place.
            classified = self.watcher._classify_changes(
                {(Change.modified, str(sidecar))},
                None,
                None,
                sessions_dir=sessions_dir,
            )
            self.assertEqual(classified, [])

    def test_sidecar_outside_sessions_scope_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions"
            sessions_dir.mkdir()
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            _write_jsonl(elsewhere, SESSION_ID)
            stray = _write_sidecar(elsewhere, SESSION_ID, with_end=True)

            classified = self.watcher._classify_changes(
                {(Change.modified, str(stray))},
                None,
                None,
                sessions_dir=sessions_dir,
            )
            self.assertEqual(classified, [])

    def test_ordinary_jsonl_change_still_classified(self) -> None:
        """The pre-existing path must be untouched by the sidecar branch."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)
            classified = self.watcher._classify_changes(
                {(Change.modified, str(jsonl))},
                None,
                None,
                sessions_dir=sessions_dir,
            )
            self.assertEqual(classified, [("modified", jsonl)])


class CaptureSurvivesLateSidecarTests(unittest.TestCase):
    """End-to-end: the two halves together mean capture is not lost."""

    def test_reparse_after_late_sidecar_recovers_all_capture_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            jsonl = _write_jsonl(sessions_dir, SESSION_ID)

            # 1. First ingest happens with NO sidecar — the losing race.
            first = parse_session_file(jsonl)
            self.assertIsNotNone(first)
            self.assertIsNone(getattr(first, "launcher", None))
            self.assertIsNone(getattr(first, "icaKey", None))
            key_at_first_ingest = _session_input_mtime(jsonl)

            # 2. SessionEnd writes the sidecar ~2s later.
            sidecar = _write_sidecar(sessions_dir, SESSION_ID, with_end=True)
            os.utime(sidecar, (key_at_first_ingest + 2, key_at_first_ingest + 2))

            # 3. The skip must now admit a re-parse...
            self.assertNotEqual(
                _session_input_mtime(jsonl),
                key_at_first_ingest,
                "Freshness key unchanged → _sync_single_session would skip and the "
                "capture would be lost permanently.",
            )

            # 4. ...and the re-parse must recover every capture field.
            second = parse_session_file(jsonl)
            self.assertIsNotNone(second)
            self.assertEqual(getattr(second, "launcher", None), "ica-claude.sh")
            self.assertEqual(getattr(second, "profile", None), "ica-delegate")
            self.assertEqual(getattr(second, "icaKey", None), "CC3")
            self.assertEqual(
                getattr(second, "icaSpendEnd", None), "10285.725025579992"
            )


if __name__ == "__main__":
    unittest.main()
