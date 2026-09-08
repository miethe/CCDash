"""Positive controls for the journal-egress exclusion predicate.

Every test here plants journal-shaped content into a synthetic transcript and asserts it
produces **zero** indexed rows. The planted text is the agreed fake sentinel
``PLANTED-TEST-ENTRY`` — no real journal text appears in this repo, and none may be added.

Why positive controls specifically: a filter that silently stops matching is indistinguishable
from a filter that has nothing to match, and the 208 rows already in ``session_messages``
(``node_01M1YV12EH7AQSXSMSFSKQJXM8``) are what a non-firing filter looks like from the outside.
So each of the five rules gets a control that FAILS if the rule stops firing, plus a negative
control proving the filter is not simply dropping everything.

Three shapes are covered because CCDash has three ways a record becomes a row:

1. ``parse_session_file`` — the raw-record choke point, shared by both write paths.
2. ``project_session_messages`` — the last gate before ``session_messages``.
3. ``filter_session_logs`` — the backstop for already-parsed payloads a remote client sent.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from backend.parsers.sessions import parse_session_file
from backend.services.session_transcript_projection import project_session_messages
from backend.services.transcript_egress import (
    REASONS,
    EgressFilterResult,
    filter_session_logs,
    filter_transcript_records,
    log_to_record,
)

#: The agreed fake sentinel. Never a real entry.
PLANTED = "PLANTED-TEST-ENTRY"
PLANTED_COMMAND = f'op journal write "{PLANTED}" --kind felt'
PLANTED_ENTRY_ID = "jrn_20260907_a1b2c3d4"
MARKER = "JOURNAL ENTRY START"


def _blob_of(obj: object) -> str:
    return json.dumps(obj, default=str)


class _TranscriptCase(unittest.TestCase):
    def _write_jsonl(self, lines: list[dict], relative_path: str = "session.jsonl") -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        return path

    def _benign_pair(self, *, uid: str = "toolu_ok", ts: str = "2026-09-07T10:00:00Z") -> list[dict]:
        """An ordinary Bash call + result. Must always survive."""
        return [
            {
                "type": "assistant",
                "uuid": f"{uid}-a",
                "timestamp": ts,
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet",
                    "content": [
                        {"type": "tool_use", "id": uid, "name": "Bash", "input": {"command": "git status"}}
                    ],
                },
            },
            {
                "type": "user",
                "uuid": f"{uid}-u",
                "timestamp": ts,
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": uid, "is_error": False, "content": "clean"}
                    ],
                },
            },
        ]

    def assertNoJournalTrace(self, obj: object) -> None:
        """Nothing anywhere in the serialized object may carry a planted sentinel."""
        blob = _blob_of(obj)
        for needle in (PLANTED, PLANTED_ENTRY_ID, MARKER):
            self.assertNotIn(needle, blob, f"{needle!r} survived into an indexed structure")
        self.assertIsNone(
            re.search(r"\bop\s+journal\s+(?:write|read|surface)\b", blob),
            "an `op journal` command line survived into an indexed structure",
        )


class ParseSessionFileControls(_TranscriptCase):
    """Rule-by-rule positive controls at the raw-record choke point."""

    def test_planted_journal_write_and_its_tool_result_are_never_indexed(self) -> None:
        path = self._write_jsonl(
            self._benign_pair()
            + [
                {
                    "type": "assistant",
                    "uuid": "jw-a",
                    "timestamp": "2026-09-07T10:01:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_journal",
                                "name": "Bash",
                                "input": {"command": PLANTED_COMMAND, "description": "write a journal entry"},
                            }
                        ],
                    },
                },
                {
                    # The wrapper echoes the entry text back. This record carries NO marker and
                    # NO entry id — it survives on the tool_use_id pairing alone, which is why
                    # taint must be registered before the verdict.
                    "type": "user",
                    "uuid": "jw-u",
                    "timestamp": "2026-09-07T10:01:01Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_journal",
                                "is_error": False,
                                "content": f"recorded: {PLANTED}",
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertNoJournalTrace(session.model_dump())

        rows = project_session_messages(session.model_dump(), [log.model_dump() for log in session.logs])
        self.assertNoJournalTrace(rows)

        # Negative control in the same fixture: the benign pair must have survived, or this
        # test would pass just as well against a filter that drops every record.
        self.assertIn("git status", _blob_of(session.model_dump()))

    def test_quoted_journal_entry_id_in_assistant_text_is_never_indexed(self) -> None:
        path = self._write_jsonl(
            self._benign_pair()
            + [
                {
                    "type": "assistant",
                    "uuid": "id-a",
                    "timestamp": "2026-09-07T10:02:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "content": [{"type": "text", "text": f"Recorded as {PLANTED_ENTRY_ID}."}],
                    },
                }
            ]
        )
        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertNoJournalTrace(session.model_dump())
        self.assertIn("git status", _blob_of(session.model_dump()))

    def test_journal_marker_anywhere_in_a_record_is_never_indexed(self) -> None:
        path = self._write_jsonl(
            self._benign_pair()
            + [
                {
                    "type": "user",
                    "uuid": "mk-u",
                    "timestamp": "2026-09-07T10:03:00Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": f"{MARKER}\n{PLANTED}"}],
                    },
                }
            ]
        )
        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertNoJournalTrace(session.model_dump())

    def test_metis_cwd_abandons_the_whole_transcript(self) -> None:
        """A session whose cwd is under ~/.metis IS a journal session — none of it is ingested.

        Note the transcript PATH carries no `.metis` component (Claude Code stores every
        transcript under ~/.claude/projects regardless of where the session ran), so a
        path-based filter would let this through. The record's own `cwd` field is the signal.
        """
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "uuid": "cw-u",
                    "cwd": "/Users/miethe/.metis/journal",
                    "timestamp": "2026-09-07T10:04:00Z",
                    "message": {"role": "user", "content": [{"type": "text", "text": "an ordinary sentence"}]},
                }
            ]
            + self._benign_pair(),
            relative_path="-Users-miethe--metis-journal/session.jsonl",
        )
        self.assertIsNone(parse_session_file(path), "a ~/.metis session must not be ingested at all")

    def test_dotmetis_lookalike_directories_are_not_excluded(self) -> None:
        """Component match, not substring: `dotmetis` / `metis-notes` are ordinary projects."""
        path = self._write_jsonl(
            [
                dict(entry, cwd="/Users/miethe/dev/metis-notes")
                for entry in self._benign_pair()
            ]
        )
        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertIn("git status", _blob_of(session.model_dump()))

    def test_ordinary_transcript_is_untouched(self) -> None:
        """The filter must be inert on a session with no journal content at all."""
        entries = self._benign_pair(uid="t1") + self._benign_pair(uid="t2", ts="2026-09-07T10:05:00Z")
        kept, result = filter_transcript_records(entries)
        self.assertEqual(len(kept), len(entries))
        self.assertEqual(result.dropped, 0)
        self.assertIsNone(result.abandoned)
        self.assertEqual(result.by_reason, {})


class SessionLogBackstopControls(_TranscriptCase):
    """The path a remote client running pre-fix code takes: already-parsed logs, no records."""

    def _journal_log_pair(self) -> list[dict]:
        return [
            {
                "id": "log-1",
                "timestamp": "2026-09-07T10:01:00Z",
                "speaker": "agent",
                "type": "tool",
                "content": "Bash",
                "toolCall": {"id": "toolu_journal", "name": "Bash", "args": {"command": PLANTED_COMMAND}},
                "metadata": {},
            },
            {
                # No marker, no entry id — caught only by the rebuilt tool_use/tool_result
                # pairing. This is the case the projected shape would otherwise lose.
                "id": "log-2",
                "timestamp": "2026-09-07T10:01:01Z",
                "speaker": "user",
                "type": "message",
                "content": f"recorded: {PLANTED}",
                "relatedToolCallId": "toolu_journal",
                "metadata": {},
            },
        ]

    def _benign_log(self) -> dict:
        return {
            "id": "log-0",
            "timestamp": "2026-09-07T10:00:00Z",
            "speaker": "agent",
            "type": "tool",
            "content": "Bash",
            "toolCall": {"id": "toolu_ok", "name": "Bash", "args": {"command": "git status"}},
            "metadata": {},
        }

    def test_parsed_journal_logs_and_their_echo_are_dropped(self) -> None:
        logs = [self._benign_log()] + self._journal_log_pair()
        kept, result = filter_session_logs(logs)
        self.assertEqual(len(kept), 1)
        self.assertEqual(result.dropped, 2)
        self.assertEqual(result.by_reason.get(REASONS.JOURNAL_COMMAND), 1)
        self.assertEqual(result.by_reason.get(REASONS.JOURNAL_COMMAND_RESULT), 1)
        self.assertNoJournalTrace(kept)

    def test_tool_args_carried_only_in_metadata_are_dropped(self) -> None:
        """CCDash puts tool input in ``metadata.toolArgs`` on the projected shape.

        This is the exact column the first enumeration missed — it scanned ``content`` alone,
        which averages 11 characters on Bash rows, and returned a false clean.
        """
        logs = [
            self._benign_log(),
            {
                "id": "log-9",
                "timestamp": "2026-09-07T10:06:00Z",
                "speaker": "agent",
                "type": "tool",
                "content": "Bash",
                "metadata": {"toolArgs": {"command": PLANTED_COMMAND}},
            },
        ]
        kept, result = filter_session_logs(logs)
        self.assertEqual(len(kept), 1)
        self.assertEqual(result.by_reason.get(REASONS.JOURNAL_COMMAND), 1)
        self.assertNoJournalTrace(kept)

    def test_forbidden_session_cwd_drops_every_log(self) -> None:
        logs = [self._benign_log()]
        kept, result = filter_session_logs(logs, session_row={"cwd": "~/.metis/journal"})
        self.assertEqual(kept, [])
        self.assertEqual(result.abandoned, REASONS.METIS_CWD)

    def test_projection_drops_journal_rows_before_session_messages(self) -> None:
        session_row = {"id": "sess-1", "rootSessionId": "sess-1"}
        rows = project_session_messages(session_row, [self._benign_log()] + self._journal_log_pair())
        self.assertEqual(len(rows), 1)
        self.assertNoJournalTrace(rows)

    def test_non_dict_logs_pass_through_rather_than_being_silently_lost(self) -> None:
        kept, result = filter_session_logs(["not-a-dict", self._benign_log()])
        self.assertEqual(len(kept), 2)
        self.assertEqual(result.dropped, 0)


class ReshapingContracts(unittest.TestCase):
    def test_log_to_record_only_changes_shape(self) -> None:
        log = {
            "id": "log-1",
            "content": "hello",
            "toolCall": {"id": "t1", "name": "Bash", "args": {"command": "ls"}},
            "relatedToolCallId": "t0",
            "metadata": {"toolArgs": {"command": "ls"}},
        }
        record = log_to_record(log, cwd="/tmp/x")
        self.assertEqual(record["cwd"], "/tmp/x")
        self.assertIs(record["_ccdash_log"], log)
        blocks = record["message"]["content"]
        self.assertEqual(blocks[0]["type"], "tool_use")
        self.assertEqual(blocks[0]["id"], "t1")
        self.assertEqual(blocks[0]["input"], {"command": "ls"})
        self.assertEqual(blocks[-1], {"type": "tool_result", "tool_use_id": "t0"})

    def test_result_summary_is_content_free(self) -> None:
        result = EgressFilterResult(kept=3)
        result.record_drop(REASONS.JOURNAL_COMMAND)
        summary = result.summary()
        self.assertIn(REASONS.JOURNAL_COMMAND, summary)
        for needle in (PLANTED, PLANTED_ENTRY_ID, MARKER):
            self.assertNotIn(needle, summary)


class VendoredCopyIntegrity(unittest.TestCase):
    """The vendored predicate is a COPY; this is the drift guard that works offline.

    CCDash must not import agentic_meta_dev at runtime, so the upstream bytes are unreachable
    from a test. What IS checkable here is that the body below the provenance header still
    hashes to the sha the header claims — which catches the failure mode that actually happens:
    someone fixing a rule in the copy instead of upstream. Re-vendoring updates both together.
    """

    PATH = Path(__file__).resolve().parents[1] / "services" / "transcript_filter.py"

    def test_body_matches_the_sha_recorded_in_the_header(self) -> None:
        text = self.PATH.read_text(encoding="utf-8")
        marker = "# =============================================================================\n"
        # The header is the first two banner lines and everything between them.
        end = text.index(marker, text.index(marker) + len(marker)) + len(marker)
        header, body = text[:end], text[end:]
        claimed = re.search(r"Upstream sha256:\s*([0-9a-f]{64})", header)
        self.assertIsNotNone(claimed, "vendored copy lost its provenance header")
        assert claimed is not None
        actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.assertEqual(
            actual,
            claimed.group(1),
            "the vendored predicate body was edited locally — fix the rule UPSTREAM "
            "(agentic_meta_dev/scripts/aos_transcript_filter.py) and re-vendor",
        )

    def test_all_five_rules_are_present(self) -> None:
        from backend.services.transcript_filter import REASONS as R

        self.assertEqual(
            set(R.ALL),
            {
                "metis_cwd",
                "journal_marker",
                "journal_command",
                "journal_command_result",
                "journal_entry_id",
            },
        )


if __name__ == "__main__":
    unittest.main()
