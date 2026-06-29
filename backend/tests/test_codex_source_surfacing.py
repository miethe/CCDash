"""Phase 3 (codex-session-ingestion-v1) — source surfacing tests.

Tests:
  1. ``derive_session_source`` returns ``'codex'`` for platform_type=='Codex'.
  2. Existing branches (filesystem/remote/entire/unknown) are unchanged.
  3. Codex parser title derivation: non-empty first user message populates
     ``badgeLatestSummary`` on the returned AgentSession.
  4. Empty first user message → ``badgeLatestSummary`` is None (no spurious title).
  5. Optional DTO fields (``source``, ``projectId``) serialize correctly and are
     absent/None for models built without them (backward-compat).

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_codex_source_surfacing.py -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.application.services.agent_queries.session_detail import derive_session_source
from backend.models import AgentSession


# ── 1 & 2: derive_session_source ─────────────────────────────────────────────

class TestDeriveSessionSource:
    """derive_session_source contract."""

    def test_codex_platform_type_returns_codex(self) -> None:
        payload = {"platform_type": "Codex", "source_ref": ""}
        assert derive_session_source(payload) == "codex"

    def test_codex_platform_type_ignores_source_ref(self) -> None:
        """platform_type == 'Codex' wins over any source_ref prefix."""
        payload = {"platform_type": "Codex", "source_ref": "fs:/some/path"}
        assert derive_session_source(payload) == "codex"

    def test_codex_platform_type_case_sensitive(self) -> None:
        """Only the exact string 'Codex' (capital C) triggers the codex branch."""
        payload = {"platform_type": "codex", "source_ref": ""}
        # lowercase should fall through to filesystem (empty source_ref)
        assert derive_session_source(payload) == "filesystem"

    # ── Existing branches unchanged ───────────────────────────────────────────

    def test_claude_code_empty_source_ref_returns_filesystem(self) -> None:
        payload = {"platform_type": "Claude Code", "source_ref": ""}
        assert derive_session_source(payload) == "filesystem"

    def test_none_source_ref_returns_filesystem(self) -> None:
        payload = {"platform_type": "Claude Code", "source_ref": None}
        assert derive_session_source(payload) == "filesystem"

    def test_no_keys_returns_filesystem(self) -> None:
        assert derive_session_source({}) == "filesystem"

    def test_entire_prefix_returns_entire(self) -> None:
        payload = {"platform_type": "Claude Code", "source_ref": "entire:workspace-abc"}
        assert derive_session_source(payload) == "entire"

    def test_remote_prefix_returns_remote(self) -> None:
        payload = {"platform_type": "", "source_ref": "remote:10.42.10.76"}
        assert derive_session_source(payload) == "remote"

    def test_fs_prefix_returns_filesystem(self) -> None:
        payload = {"source_ref": "fs:/Users/miethe/.claude/projects/foo"}
        assert derive_session_source(payload) == "filesystem"

    def test_filesystem_prefix_returns_filesystem(self) -> None:
        payload = {"source_ref": "filesystem:/path"}
        assert derive_session_source(payload) == "filesystem"

    def test_unknown_prefix_returns_unknown(self) -> None:
        payload = {"source_ref": "s3://bucket/path"}
        assert derive_session_source(payload) == "unknown"

    def test_missing_platform_type_falls_back_to_source_ref(self) -> None:
        payload = {"source_ref": "remote:nuc"}
        assert derive_session_source(payload) == "remote"


# ── 3 & 4: Codex parser — title derivation via badgeLatestSummary ─────────────

def _minimal_codex_jsonl(user_text: str | None, *, include_agent_msg: bool = False) -> list[str]:
    """Build a minimal valid Codex JSONL transcript."""
    lines: list[str] = [
        # context entry so _looks_like_codex recognises the file
        json.dumps({
            "type": "turn_context",
            "timestamp": "2026-06-28T10:00:00Z",
            "payload": {"model": "gpt-4o", "codex_version": "0.1.0"},
        }),
    ]
    if user_text is not None:
        lines.append(json.dumps({
            "type": "input",
            "timestamp": "2026-06-28T10:00:01Z",
            "payload": {
                "type": "user_message",
                "role": "user",
                "content": user_text,
            },
        }))
    if include_agent_msg:
        lines.append(json.dumps({
            "type": "output",
            "timestamp": "2026-06-28T10:00:02Z",
            "payload": {
                "type": "agent_message",
                "role": "assistant",
                "content": "Sure, I can help.",
            },
        }))
    return lines


class TestCodexTitleDerivation:
    """Codex parser populates badgeLatestSummary from the first user message."""

    def _parse(self, lines: list[str]) -> AgentSession | None:
        from backend.parsers.platforms.codex.parser import parse_session_file

        content = "\n".join(lines)
        with tempfile.NamedTemporaryFile(
            suffix=".jsonl",
            prefix="rollout-test-",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            return parse_session_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_first_user_message_populates_badge_latest_summary(self) -> None:
        user_text = "Implement the auth flow in the signup page"
        session = self._parse(_minimal_codex_jsonl(user_text))
        assert session is not None, "parser returned None for valid fixture"
        assert session.badgeLatestSummary == user_text[:200].strip()

    def test_long_user_message_is_clipped_to_200_chars(self) -> None:
        long_text = "x" * 500
        session = self._parse(_minimal_codex_jsonl(long_text))
        assert session is not None
        assert session.badgeLatestSummary is not None
        assert len(session.badgeLatestSummary) <= 200

    def test_no_user_message_gives_none_badge(self) -> None:
        """If the transcript has only an agent message, badgeLatestSummary is None."""
        session = self._parse(_minimal_codex_jsonl(None, include_agent_msg=True))
        # The session may or may not be returned depending on whether _looks_like_codex
        # still matches (it needs a model in turn_context).
        if session is None:
            pytest.skip("fixture not recognised as Codex — adjust fixture if parser changes")
        assert session.badgeLatestSummary is None

    def test_only_first_user_message_is_captured(self) -> None:
        """Only the FIRST user message is captured; subsequent ones are ignored."""
        lines = _minimal_codex_jsonl("First message")
        # Append a second user message
        lines.append(json.dumps({
            "type": "input",
            "timestamp": "2026-06-28T10:01:00Z",
            "payload": {"type": "user_message", "role": "user", "content": "Second message"},
        }))
        session = self._parse(lines)
        assert session is not None
        assert session.badgeLatestSummary == "First message"

    def test_codex_platform_type_is_set(self) -> None:
        session = self._parse(_minimal_codex_jsonl("Do something"))
        assert session is not None
        assert session.platformType == "Codex"


# ── 5: Optional DTO field serialisation ──────────────────────────────────────

class TestAgentSessionOptionalFields:
    """source and projectId are optional; absent for legacy sessions, present for Codex."""

    def _minimal_session(self, **overrides: object) -> AgentSession:
        base = dict(
            id="test-session-1",
            durationSeconds=0,
            tokensIn=0,
            tokensOut=0,
            totalCost=0.0,
            startedAt="2026-06-28T10:00:00Z",
            toolsUsed=[],
            logs=[],
        )
        base.update(overrides)
        return AgentSession(**base)  # type: ignore[arg-type]

    def test_source_absent_by_default(self) -> None:
        s = self._minimal_session()
        assert s.source is None

    def test_project_id_absent_by_default(self) -> None:
        s = self._minimal_session()
        assert s.projectId is None

    def test_codex_source_serialises_correctly(self) -> None:
        s = self._minimal_session(source="codex", projectId="some-project")
        dumped = s.model_dump()
        assert dumped["source"] == "codex"
        assert dumped["projectId"] == "some-project"

    def test_unattributed_project_id_is_empty_string(self) -> None:
        """FE detects Unattributed bucket when projectId === ''."""
        s = self._minimal_session(source="codex", projectId="")
        dumped = s.model_dump()
        assert dumped["projectId"] == ""

    def test_filesystem_source_serialises_correctly(self) -> None:
        s = self._minimal_session(source="filesystem", projectId="project-abc")
        dumped = s.model_dump()
        assert dumped["source"] == "filesystem"

    def test_badge_latest_summary_not_surfaced_when_none(self) -> None:
        s = self._minimal_session()
        assert s.badgeLatestSummary is None
