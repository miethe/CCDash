"""automatic-session-naming M1 (T1-002) — provider ingest into the parsers.

Covers the parser-level half of FR-3/FR-4/FR-5 that ``test_session_name_provenance.py``
(T1-001) deliberately left unasserted:

1. **Claude Code `ai-title` ingest** — a self-referential record (``sessionId`` ==
   the file's own session id) populates ``AgentSession.sessionName`` /
   ``sessionNameSource`` with ``provider_persisted``.
2. **The sessionId-mismatch skip case** — the plan's highest-consequence named
   risk ("wrong name on the wrong session"). A record whose ``sessionId``
   differs from the file's own session id must be skipped, not stored.
3. **The `.orphaned-<ts>-<hash>` filename-suffix case** — the one measured
   near-miss (tech-claude-spike.md §5): the base UUID before the suffix is
   still the file's real session id, so a self-referential record there must
   still be accepted.
4. **Idempotent re-emission / "latest wins"** — a later verified record
   overwrites an earlier one from the same file.
5. **Codex `thread_name_updated` ingest** — the ``event_msg`` branch stops
   discarding ``payload.thread_name`` (FR-4).
6. **Codex `session_meta.payload.git.branch` ingest** — no longer hardcoded
   ``None`` (FR-5); this is M2's deterministic fallback source for
   ``codex_exec`` sessions.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.platforms.claude_code import parser as claude_parser
from backend.parsers.platforms.codex import parser as codex_parser
from backend.parsers.session_name_provenance import (
    SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
    SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
    may_overwrite,
    session_name_rank,
)


def _write_jsonl(lines: list[dict], relative_path: str) -> Path:
    # ``mkdtemp`` (not ``TemporaryDirectory``) deliberately: these directories
    # are left for the OS to reclaim rather than tracked for cleanup, since a
    # ``Path`` cannot carry an attribute referencing the cleanup handle.
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


_SESSION_UUID = "c783f44a-1111-2222-3333-444455556666"
_OTHER_SESSION_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class ClaudeCodeAiTitleIngestTests(unittest.TestCase):
    def _basic_entries(self, ai_title_entries: list[dict]) -> list[dict]:
        return [
            {
                "type": "user",
                "timestamp": "2026-02-16T10:00:00Z",
                "message": {"role": "user", "content": "hello"},
            },
            *ai_title_entries,
        ]

    def test_ai_title_self_referential_record_is_ingested(self) -> None:
        path = _write_jsonl(
            self._basic_entries(
                [
                    {
                        "type": "ai-title",
                        "aiTitle": "phase-6 validation corpus squash",
                        "sessionId": _SESSION_UUID,
                    }
                ]
            ),
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "phase-6 validation corpus squash")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_ai_title_with_mismatched_session_id_is_skipped(self) -> None:
        path = _write_jsonl(
            self._basic_entries(
                [
                    {
                        "type": "ai-title",
                        "aiTitle": "a name from a different session",
                        "sessionId": _OTHER_SESSION_UUID,
                    }
                ]
            ),
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        # Named risk "wrong name on the wrong session": the mismatched record
        # must never be stored, not even as a lower-confidence guess. The
        # session is not left nameless, though -- M2/T2-003's rank-4 fallback
        # ("first user message, truncated") fills the gap the skipped
        # ai-title left behind, from this fixture's "hello" user message.
        self.assertNotEqual(session.sessionName, "a name from a different session")
        self.assertEqual(session.sessionName, "hello")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_ai_title_missing_session_id_is_skipped(self) -> None:
        path = _write_jsonl(
            self._basic_entries(
                [
                    {
                        "type": "ai-title",
                        "aiTitle": "no sessionId on this record",
                    }
                ]
            ),
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        # Same reasoning as the mismatched-sessionId case above: the invalid
        # ai-title record is skipped, and the rank-4 fallback fills the gap.
        self.assertNotEqual(session.sessionName, "no sessionId on this record")
        self.assertEqual(session.sessionName, "hello")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_ai_title_survives_orphaned_filename_suffix(self) -> None:
        # tech-claude-spike.md §5: the single measured near-miss was a
        # filename-suffix artifact of orphan recovery, not a real
        # cross-session pointer -- the base UUID before the suffix is still
        # the file's real session id.
        path = _write_jsonl(
            self._basic_entries(
                [
                    {
                        "type": "ai-title",
                        "aiTitle": "orphan-recovered session name",
                        "sessionId": _SESSION_UUID,
                    }
                ]
            ),
            relative_path=f"{_SESSION_UUID}.orphaned-1785631141454-be039dde.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "orphan-recovered session name")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_ai_title_re_emission_is_idempotent_last_write_wins(self) -> None:
        path = _write_jsonl(
            self._basic_entries(
                [
                    {
                        "type": "ai-title",
                        "aiTitle": "first draft title",
                        "sessionId": _SESSION_UUID,
                    },
                    {
                        "type": "ai-title",
                        "aiTitle": "revised final title",
                        "sessionId": _SESSION_UUID,
                    },
                ]
            ),
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "revised final title")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_no_ai_title_record_falls_back_to_first_user_message(self) -> None:
        # Superseded by M2/T2-003: this fixture's ``_basic_entries([])`` still
        # carries a "hello" user message and no ai-title record, so the
        # rank-4 deterministic fallback ("first user message, truncated" --
        # see LastPromptAndFirstMessageFallbackTests below) now closes the
        # gap this test originally asserted stayed null. The genuinely
        # signal-less case (no ai-title, no last-prompt, no user message at
        # all) is covered separately by
        # LastPromptAndFirstMessageFallbackTests.test_no_signal_at_all_stays_null.
        path = _write_jsonl(
            self._basic_entries([]),
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "hello")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)


class CodexThreadNameAndGitBranchIngestTests(unittest.TestCase):
    def test_thread_name_updated_is_ingested(self) -> None:
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {"branch": "feature/harden-nginx"},
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "thread_name_updated",
                        "thread_id": "thread-1",
                        "thread_name": "Harden frontend nginx runtime",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "hello",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-thread.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "Harden frontend nginx runtime")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)
        # FR-5: session_meta.payload.git.branch, previously hardcoded None.
        self.assertEqual(session.gitBranch, "feature/harden-nginx")

    def test_thread_name_updated_replace_in_place_last_write_wins(self) -> None:
        path = _write_jsonl(
            [
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "thread_name_updated",
                        "thread_id": "thread-1",
                        "thread_name": "first thread name",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "hello",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:02Z",
                    "payload": {
                        "type": "thread_name_updated",
                        "thread_id": "thread-1",
                        "thread_name": "renamed thread",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-thread-rename.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "renamed thread")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_no_thread_name_updated_leaves_session_name_null_and_git_branch_none(self) -> None:
        # Subject: absence of session_meta means no git.branch, and absence of
        # thread_name_updated means no provider name. With no user message either,
        # nothing in the M2 fallback chain can fire, so both fields stay null.
        # (The user_message this fixture originally carried was removed when the
        # first-message fallback landed at the M2 gate -- see the sibling test
        # test_codex_falls_back_to_truncated_first_message_when_no_branch.)
        path = _write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {"type": "turn_context", "model": "gpt-5-codex"},
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-unnamed.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertIsNone(session.sessionName)
        self.assertIsNone(session.sessionNameSource)
        self.assertIsNone(session.gitBranch)

    def test_codex_exec_headless_falls_back_to_git_branch(self) -> None:
        # T2-002 (FR-7): codex_exec headless sessions never emit
        # thread_name_updated (0/960 measured, tech-codex-spike.md Finding 2).
        # session_meta.payload.git.branch (already read for FR-5) becomes the
        # M2 deterministic, zero-model-call fallback.
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "originator": "codex_exec",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {"branch": "automatic-session-naming-v1"},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "hello",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-codex-exec.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.gitBranch, "automatic-session-naming-v1")
        self.assertEqual(session.sessionName, "automatic-session-naming-v1")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_codex_falls_back_to_truncated_first_message_when_no_branch(self) -> None:
        # Gap closed at the M2 milestone gate: T2-003 implemented the plan's
        # "last-prompt then a truncated first message" tail only in the Claude
        # parser, but M2's plan text is provider-agnostic about "the remainder".
        # `last-prompt` has no Codex equivalent; the first-message tail does, and
        # without it a Codex session with neither a thread_name nor a git.branch
        # (session_meta present but carrying no branch) reached the FE unnamed.
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "originator": "codex_exec",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "refactor the retry helper to share one backoff policy",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-codex-nobranch.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertFalse(session.gitBranch)
        self.assertEqual(
            session.sessionName,
            "refactor the retry helper to share one backoff policy",
        )
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_codex_first_message_fallback_truncates_at_120(self) -> None:
        # Matches the 120-char bound the Claude parser's equivalent rank-4 write
        # uses (itself reusing that file's pre-existing summary_text[:120]).
        long_message = "x" * 400
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "originator": "codex_exec",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": long_message,
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-codex-long.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "x" * 120)
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_codex_git_branch_outranks_first_message_fallback(self) -> None:
        # Ordering WITHIN the shared derived_deterministic tier: git.branch is the
        # plan's named codex_exec fallback, so it must win over the first-message
        # tail. Enforced by an emptiness gate, not may_overwrite (equal ranks are
        # mutually overwritable by design).
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "originator": "codex_exec",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {"branch": "feat/branch-wins"},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "this message must not become the session name",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-codex-branch-wins.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "feat/branch-wins")

    def test_codex_provider_name_survives_first_message_fallback(self) -> None:
        # A weaker source must never overwrite provider_persisted, even when the
        # branch is absent so the first-message tail is the one that would fire.
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {},
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "thread_name_updated",
                        "thread_name": "Provider set this name",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "this message must not become the session name",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-codex-provider-wins.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.sessionName, "Provider set this name")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_thread_name_updated_outranks_git_branch_fallback(self) -> None:
        # A weaker source (derived_deterministic git.branch) must never
        # overwrite a stronger one (provider_persisted thread_name) even
        # when both are present in the same file.
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "cwd": "/tmp/ccdash/workspace",
                        "git": {"branch": "main"},
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "thread_name_updated",
                        "thread_id": "thread-1",
                        "thread_name": "Harden frontend nginx runtime",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-both-sources.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.gitBranch, "main")
        self.assertEqual(session.sessionName, "Harden frontend nginx runtime")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_no_thread_name_and_no_git_branch_stays_null(self) -> None:
        # No provider name AND no git.branch AND no user message -- session_name
        # must stay null (a fallback with nothing to fall back to is not written),
        # not an empty string or a guessed value. This is the contract state M3's
        # sweep job selects on (session_name IS NULL) and the state the offline CLI
        # is specified to leave behind, so it must remain reachable.
        # NOTE: the user_message this fixture originally carried was removed when the
        # first-message fallback landed (M2 gate) -- with a message present there IS
        # something to fall back to, so the assertion below would no longer be
        # testing "nothing to fall back to". That path is covered by
        # test_codex_falls_back_to_truncated_first_message_when_no_branch.
        path = _write_jsonl(
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-02-17T09:59:59Z",
                    "payload": {
                        "type": "session_meta",
                        "cwd": "/tmp/ccdash/workspace",
                    },
                },
                {
                    "type": "turn_context",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {"type": "turn_context", "model": "gpt-5-codex"},
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-no-name-no-branch.jsonl",
        )

        session = codex_parser.parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertIsNone(session.gitBranch)
        self.assertIsNone(session.sessionName)
        self.assertIsNone(session.sessionNameSource)


class ProvenanceRankOrderingTests(unittest.TestCase):
    """T1-005 (this task) — the "weaker source never overwrites a stronger one"
    contract exercised through the ingest-layer's own imports, complementing
    (not duplicating) the exhaustive unit coverage in
    ``test_session_name_provenance.py`` (T1-001).
    """

    def test_provider_persisted_outranks_derived_deterministic(self) -> None:
        self.assertLess(
            session_name_rank(SESSION_NAME_SOURCE_PROVIDER_PERSISTED),
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )

    def test_derived_deterministic_outranks_derived_generative(self) -> None:
        self.assertLess(
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_GENERATIVE),
        )

    def test_weaker_never_overwrites_stronger(self) -> None:
        # A later derived_deterministic (M2 fallback) or derived_generative
        # (M3 sweep) record must never clobber a provider-set name already
        # ingested by this milestone's parsers.
        self.assertFalse(
            may_overwrite(SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)
        )
        self.assertFalse(
            may_overwrite(SESSION_NAME_SOURCE_DERIVED_GENERATIVE, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)
        )

    def test_provider_persisted_may_overwrite_a_weaker_incumbent(self) -> None:
        # The inverse holds too: a later-arriving provider name (e.g. a
        # Claude Code session that only writes ai-title after some turns)
        # must be able to replace an earlier deterministic/generative guess.
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_PROVIDER_PERSISTED, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)
        )
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_PROVIDER_PERSISTED, SESSION_NAME_SOURCE_DERIVED_GENERATIVE)
        )

    def test_equal_provider_persisted_rank_may_overwrite_itself(self) -> None:
        # A re-emitted ai-title / thread_name_updated record ("latest wins",
        # exercised end-to-end above) is same-rank-overwrites-same-rank.
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_PROVIDER_PERSISTED, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)
        )


class SessionNameColumnParityTests(unittest.TestCase):
    """T1-005 (this task) — column-parity assertion for ``sessions.session_name``
    / ``sessions.session_name_source`` scoped to this file, so the M1
    ingest-test file is self-contained evidence for the plan's
    "Dual DDL + parity" AC row without relying solely on
    ``test_session_name_provenance.py``.
    """

    def test_session_name_columns_are_parity_clean_across_backends(self) -> None:
        from backend.db.migration_governance import (
            COLUMN_PARITY_DRIFT_ALLOWLIST,
            column_parity_diff,
        )

        diff = column_parity_diff("sessions")
        for column in ("session_name", "session_name_source"):
            with self.subTest(column=column):
                self.assertNotIn(
                    column,
                    diff,
                    msg=f"sessions.{column} differs across SQLite/Postgres DDL: {diff.get(column)!r}",
                )
                self.assertNotIn(
                    ("sessions", column),
                    COLUMN_PARITY_DRIFT_ALLOWLIST,
                    msg=f"sessions.{column} must be parity-clean by construction, not allowlisted",
                )


class SubagentSessionNameInheritanceTests(unittest.IsolatedAsyncioTestCase):
    """T2-001 — the one-hop subagent-inheritance call site

    (``backend/db/repositories/sessions.py::backfill_skill_name_inheritance``,
    reused verbatim rather than a new mechanism per the plan's rubric) also
    carries ``session_name`` from a parent session onto its subagent
    sidechain, stamping ``session_name_source = derived_deterministic``.

    Mirrors ``test_skill_name_source_provenance.py``'s real-DB round-trip
    shape for the sibling ``skill_name`` inheritance pass.
    """

    PROJECT_A = "proj-a"
    PROJECT_B = "proj-b"

    _BASE = {
        "taskId": "",
        "status": "completed",
        "sessionType": "subagent",
        "model": "claude-sonnet-5",
        "platformType": "Claude Code",
        "platformVersion": "2.1.52",
        "platformVersions": ["2.1.52"],
        "platformVersionTransitions": [],
        "durationSeconds": 1,
        "tokensIn": 1,
        "tokensOut": 1,
        "modelIOTokens": 2,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheInputTokens": 0,
        "observedTokens": 0,
        "toolReportedTokens": 0,
        "toolResultInputTokens": 0,
        "toolResultOutputTokens": 0,
        "toolResultCacheCreationInputTokens": 0,
        "toolResultCacheReadInputTokens": 0,
        "totalCost": 0.0,
        "qualityRating": 0,
        "frictionRating": 0,
        "gitCommitHash": None,
        "gitAuthor": None,
        "gitBranch": None,
        "startedAt": "2026-08-05T00:00:00Z",
        "endedAt": "2026-08-05T00:01:00Z",
        "sourceFile": "",
        "parentSessionId": None,
        "rootSessionId": "root-1",
        "agentId": None,
        "threadKind": "subagent",
        "conversationFamilyId": "root-1",
        "contextInheritance": "fresh",
    }

    async def asyncSetUp(self) -> None:
        import aiosqlite

        from backend.db.repositories.sessions import SqliteSessionRepository
        from backend.db.sqlite_migrations import run_migrations

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    def _session(self, sid: str, **overrides) -> dict:
        return {**self._BASE, "id": sid, **overrides}

    async def _read_name(self, project_id: str, sid: str) -> tuple[str | None, str | None]:
        async with self.db.execute(
            "SELECT session_name, session_name_source FROM sessions"
            " WHERE project_id = ? AND id = ?",
            (project_id, sid),
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, msg=f"session {sid} not persisted")
        return row[0], row[1]

    async def test_subagent_inherits_parent_session_name(self) -> None:
        await self.repo.upsert(
            self._session(
                "parent-1", sessionType="session", sessionName="rf-work",
                sessionNameSource=SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            ),
            self.PROJECT_A,
        )
        await self.repo.upsert(
            self._session("child-1", subagentParentId="parent-1"),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(result["session_name_rows"], 1)
        self.assertEqual(
            await self._read_name(self.PROJECT_A, "child-1"),
            ("rf-work", SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )

    async def test_no_parent_name_falls_back_to_own_agent_name_record(self) -> None:
        # Parent has no session_name at all; the child still carries its own
        # subagent_type ("badgeSubagentType" -- the existing agent-name
        # record already used as this session's title fallback elsewhere).
        await self.repo.upsert(
            self._session("parent-2", sessionType="session"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-2", subagentParentId="parent-2",
                badgeSubagentType="general-purpose",
            ),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(result["session_name_rows"], 1)
        self.assertEqual(
            await self._read_name(self.PROJECT_A, "child-2"),
            ("general-purpose", SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )

    async def test_no_parent_name_and_no_own_agent_name_stays_null(self) -> None:
        await self.repo.upsert(
            self._session("parent-3", sessionType="session"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session("child-3", subagentParentId="parent-3"),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(result["session_name_rows"], 0)
        self.assertEqual(await self._read_name(self.PROJECT_A, "child-3"), (None, None))

    async def test_provider_persisted_name_never_overwritten(self) -> None:
        # Highest-consequence invariant: a derived_deterministic write must
        # never clobber a provider_persisted name already on the child,
        # even though the parent also has a (weaker-ranked-if-it-mattered)
        # name available to inherit.
        await self.repo.upsert(
            self._session("parent-4", sessionType="session", sessionName="parent title"),
            self.PROJECT_A,
        )
        await self.repo.upsert(
            self._session(
                "child-4",
                subagentParentId="parent-4",
                sessionName="already named by the provider",
                sessionNameSource=SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            ),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(
            result["session_name_rows"],
            0,
            msg="backfill must not touch a session with a provider_persisted name",
        )
        self.assertEqual(
            await self._read_name(self.PROJECT_A, "child-4"),
            ("already named by the provider", SESSION_NAME_SOURCE_PROVIDER_PERSISTED),
        )

    async def test_backfill_is_idempotent_second_pass_zero_rows(self) -> None:
        await self.repo.upsert(
            self._session("parent-5", sessionType="session", sessionName="rf-work"),
            self.PROJECT_A,
        )
        await self.repo.upsert(
            self._session("child-5", subagentParentId="parent-5"),
            self.PROJECT_A,
        )

        first = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(first["session_name_rows"], 1)

        second = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(
            second["session_name_rows"],
            0,
            msg="second backfill pass must change zero session_name rows",
        )
        self.assertEqual(
            await self._read_name(self.PROJECT_A, "child-5"),
            ("rf-work", SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )

    async def test_project_scoped_join_no_cross_project_leak(self) -> None:
        # Same shape as the skill_name precedent's AC 8: duplicate ids across
        # two projects must never cross-contaminate the (id, project_id) join.
        await self.repo.upsert(
            self._session("parent-dup", sessionType="session", sessionName="proj-a name"),
            self.PROJECT_A,
        )
        await self.repo.upsert(
            self._session("child-dup", subagentParentId="parent-dup"),
            self.PROJECT_A,
        )
        await self.repo.upsert(
            self._session("parent-dup", sessionType="session", sessionName="proj-b name"),
            self.PROJECT_B,
        )
        await self.repo.upsert(
            self._session("child-dup", subagentParentId="parent-dup"),
            self.PROJECT_B,
        )

        result_a = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        result_b = await self.repo.backfill_skill_name_inheritance(self.PROJECT_B)

        self.assertEqual(result_a["session_name_rows"], 1)
        self.assertEqual(result_b["session_name_rows"], 1)
        self.assertEqual(
            await self._read_name(self.PROJECT_A, "child-dup"),
            ("proj-a name", SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )
        self.assertEqual(
            await self._read_name(self.PROJECT_B, "child-dup"),
            ("proj-b name", SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC),
        )


def _user_message_entry(text: str, timestamp: str = "2026-02-16T10:00:00Z") -> dict:
    return {
        "type": "user",
        "timestamp": timestamp,
        "message": {"role": "user", "content": text},
    }


def _last_prompt_entry(text: str, session_id: str = _SESSION_UUID) -> dict:
    return {"type": "last-prompt", "lastPrompt": text, "sessionId": session_id}


class LastPromptAndFirstMessageFallbackTests(unittest.TestCase):
    """M2/T2-003 — the remaining deterministic fallback chain for any
    interactive (non-subagent) Claude Code session still unnamed after
    ``ai-title`` (rank 1): ``last-prompt`` (rank 3) then a truncated first
    user message (rank 4, ~100%-coverage floor). Every write in this chain
    must carry ``derived_deterministic`` and must never overwrite a
    stronger-ranked incumbent, regardless of in-file record order.
    """

    def test_last_prompt_self_referential_record_is_ingested(self) -> None:
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                _last_prompt_entry("write a fix for the flaky test"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "write a fix for the flaky test")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_last_prompt_with_mismatched_session_id_falls_back_to_first_message(self) -> None:
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                _last_prompt_entry("a prompt from a different session", session_id=_OTHER_SESSION_UUID),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        # Same "wrong name on the wrong session" risk as ai-title: the
        # mismatched record must never be stored, so the chain falls through
        # to rank 4.
        self.assertNotEqual(session.sessionName, "a prompt from a different session")
        self.assertEqual(session.sessionName, "hello")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_last_prompt_re_emission_is_idempotent_last_write_wins(self) -> None:
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                _last_prompt_entry("first draft prompt"),
                _last_prompt_entry("revised final prompt"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "revised final prompt")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_last_prompt_truncated_to_max_length(self) -> None:
        long_prompt = "x" * 500
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                _last_prompt_entry(long_prompt),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(len(session.sessionName or ""), claude_parser._SESSION_NAME_FALLBACK_TRUNCATION_LEN)
        self.assertEqual(session.sessionName, long_prompt[: claude_parser._SESSION_NAME_FALLBACK_TRUNCATION_LEN])
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_ai_title_outranks_last_prompt_regardless_of_in_file_order(self) -> None:
        # last-prompt appears BEFORE ai-title in the file -- mean relative
        # position of ai-title is 0.577 (tech-claude-spike.md §3), so order is
        # not guaranteed. The stronger provider_persisted source must win
        # either way, not "whichever record the parser saw last".
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                _last_prompt_entry("a deterministic guess"),
                {
                    "type": "ai-title",
                    "aiTitle": "the real provider title",
                    "sessionId": _SESSION_UUID,
                },
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "the real provider title")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_last_prompt_never_overwrites_an_earlier_ai_title(self) -> None:
        # ai-title appears BEFORE last-prompt this time -- the weaker source
        # must not clobber it on the other order either.
        path = _write_jsonl(
            [
                _user_message_entry("hello"),
                {
                    "type": "ai-title",
                    "aiTitle": "the real provider title",
                    "sessionId": _SESSION_UUID,
                },
                _last_prompt_entry("a deterministic guess"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "the real provider title")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_first_user_message_fallback_when_no_ai_title_and_no_last_prompt(self) -> None:
        path = _write_jsonl(
            [_user_message_entry("please fix the flaky auth test")],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "please fix the flaky auth test")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_first_user_message_captures_first_not_later_message(self) -> None:
        path = _write_jsonl(
            [
                _user_message_entry("first message wins"),
                _user_message_entry("a much later message must not be used"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "first message wins")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_first_user_message_truncated_to_max_length(self) -> None:
        long_message = "y" * 500
        path = _write_jsonl(
            [_user_message_entry(long_message)],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(len(session.sessionName or ""), claude_parser._SESSION_NAME_FALLBACK_TRUNCATION_LEN)
        self.assertEqual(session.sessionName, long_message[: claude_parser._SESSION_NAME_FALLBACK_TRUNCATION_LEN])
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_last_prompt_outranks_first_user_message_fallback(self) -> None:
        # Both rank-3 and rank-4 candidates are available (no ai-title). Since
        # both share the same derived_deterministic token, may_overwrite
        # cannot arbitrate between them -- the parser must prefer last-prompt
        # over the first-message fallback by construction (see the "Gated on
        # not session_name" comment at the fallback's call site).
        path = _write_jsonl(
            [
                _user_message_entry("the first message, should lose"),
                _last_prompt_entry("the last prompt, should win"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "the last prompt, should win")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC)

    def test_ai_title_preserved_when_only_first_message_fallback_available(self) -> None:
        # T2-003 added TWO fallback writes: last-prompt (rank 3) and the
        # truncated first-user-message (rank 4). The two "ai-title outranks
        # last-prompt" tests above only exercise the rank-3 path; this
        # exercises the rank-4 path directly by omitting last-prompt entirely
        # so the first-user-message fallback is the only deterministic
        # candidate in the file, and it must still lose to the already-
        # present provider_persisted name.
        path = _write_jsonl(
            [
                {
                    "type": "ai-title",
                    "aiTitle": "the real provider title",
                    "sessionId": _SESSION_UUID,
                },
                _user_message_entry("a first message that must not overwrite the title"),
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertEqual(session.sessionName, "the real provider title")
        self.assertEqual(session.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_no_signal_at_all_stays_null(self) -> None:
        # No ai-title, no last-prompt, no user message of any kind -- the
        # genuinely unnameable case. Must render the defined null contract
        # state, never a guess.
        path = _write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {"role": "assistant", "content": "acknowledged"},
                }
            ],
            relative_path=f"{_SESSION_UUID}.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertIsNone(session.sessionName)
        self.assertIsNone(session.sessionNameSource)

    def test_subagent_file_excluded_from_last_prompt_and_first_message_fallback(self) -> None:
        # Scope note (T2-003 dispatch): subagent sidechains are already owned
        # by T2-001's parent-title inheritance at sync_engine.py:3307. This
        # parser-level fallback chain must not race that mechanism with a
        # second, weaker one for the same population -- a subagent file with
        # both a last-prompt record and a user message must stay null here.
        path = _write_jsonl(
            [
                _user_message_entry("hello from a subagent"),
                _last_prompt_entry("a subagent's own last prompt"),
            ],
            relative_path="subagents/agent-aaa111.jsonl",
        )

        session = claude_parser.parse_session_file(path)
        assert session is not None
        self.assertIsNone(session.sessionName)
        self.assertIsNone(session.sessionNameSource)


if __name__ == "__main__":
    unittest.main()
