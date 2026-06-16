"""
Contract test — lock the REAL SessionLog shape that persona_extract.py consumes.

This test parses the synthetic fixture via parse_session_file and asserts that
the resulting AgentSession and SessionLog objects have the exact field names
read by backend/application/services/agent_queries/persona_extract.py.

If a parser rename breaks persona extraction silently, this test will fail
loudly and point the developer to the right file.

Fields consumed by persona_extract.py (as of Phase 1/2):
  AgentSession:  .id   (used as session_id in CandidateLine)
  SessionLog:    .speaker, .content, .timestamp  (read directly in extract_candidates)

Fixture: backend/tests/fixtures/persona_extract/synthetic-session.jsonl
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "persona_extract"
SYNTHETIC_FIXTURE = FIXTURE_DIR / "synthetic-session.jsonl"


@pytest.fixture(scope="module")
def parsed_session():
    """Parse the synthetic fixture once for the whole module."""
    from backend.parsers.platforms.claude_code.parser import parse_session_file
    session = parse_session_file(SYNTHETIC_FIXTURE)
    assert session is not None, (
        f"parse_session_file returned None for {SYNTHETIC_FIXTURE}. "
        "The fixture may be malformed or the parser API changed."
    )
    return session


# ---------------------------------------------------------------------------
# AgentSession shape
# ---------------------------------------------------------------------------

def test_agent_session_has_id(parsed_session):
    """AgentSession must have .id — used as session_id in CandidateLine.

    If this fails, update backend/application/services/agent_queries/persona_extract.py
    to use the new field name (search for 'session.id').
    """
    assert hasattr(parsed_session, "id"), (
        "AgentSession lost its 'id' attribute. "
        "persona_extract.py reads session.id to populate CandidateLine['session_id']. "
        "Fix: update persona_extract.py if the field was renamed."
    )
    assert isinstance(parsed_session.id, str), (
        f"AgentSession.id must be a str, got {type(parsed_session.id).__name__!r}"
    )
    assert parsed_session.id, "AgentSession.id must be a non-empty string"


def test_agent_session_has_logs(parsed_session):
    """AgentSession must have .logs as a flat list — persona_extract iterates it directly.

    If this fails, the parser restructured session data. Check persona_extract.py
    line: `logs = session.logs`.
    """
    assert hasattr(parsed_session, "logs"), (
        "AgentSession lost its 'logs' attribute. "
        "persona_extract.py reads session.logs for the flat log list. "
        "Fix: update persona_extract.py if the field was renamed."
    )
    assert isinstance(parsed_session.logs, list), (
        f"AgentSession.logs must be a list, got {type(parsed_session.logs).__name__!r}. "
        "persona_extract.py iterates over session.logs directly — no nested .messages."
    )
    assert len(parsed_session.logs) > 0, (
        "Synthetic fixture should parse to a non-empty log list"
    )


# ---------------------------------------------------------------------------
# SessionLog shape — the exact attributes persona_extract.py reads
# ---------------------------------------------------------------------------

def test_session_log_has_speaker(parsed_session):
    """SessionLog must have .speaker — persona_extract.py filters on speaker == 'user'.

    If this fails, update persona_extract.py: search for getattr(log, 'speaker').
    """
    first_log = parsed_session.logs[0]
    assert hasattr(first_log, "speaker"), (
        "SessionLog lost its 'speaker' attribute. "
        "persona_extract.py gates extraction with: "
        "  if getattr(log, 'speaker', None) != 'user': continue\n"
        "Fix: update persona_extract.py if the field was renamed."
    )
    assert isinstance(first_log.speaker, str), (
        f"SessionLog.speaker must be a str, got {type(first_log.speaker).__name__!r}"
    )


def test_session_log_has_content(parsed_session):
    """SessionLog must have .content — persona_extract.py reads log.content for rule matching.

    If this fails, update persona_extract.py: search for 'log.content'.
    """
    first_log = parsed_session.logs[0]
    assert hasattr(first_log, "content"), (
        "SessionLog lost its 'content' attribute. "
        "persona_extract.py reads text = log.content or '' for rule matching. "
        "Fix: update persona_extract.py if the field was renamed."
    )
    # content may be an empty string — that is valid
    assert isinstance(first_log.content, str), (
        f"SessionLog.content must be a str, got {type(first_log.content).__name__!r}"
    )


def test_session_log_has_timestamp(parsed_session):
    """SessionLog must have .timestamp — persona_extract.py normalizes it for CandidateLine.ts.

    If this fails, update persona_extract.py: search for getattr(log, 'timestamp').
    """
    first_log = parsed_session.logs[0]
    assert hasattr(first_log, "timestamp"), (
        "SessionLog lost its 'timestamp' attribute. "
        "persona_extract.py normalizes it via: "
        "  ts = _normalize_ts(getattr(log, 'timestamp', '') or '')\n"
        "Fix: update persona_extract.py if the field was renamed."
    )
    # timestamp may be empty string — that is valid (CLI fills it)
    assert isinstance(first_log.timestamp, str), (
        f"SessionLog.timestamp must be a str, got {type(first_log.timestamp).__name__!r}"
    )


def test_no_nested_messages_field(parsed_session):
    """SessionLog must NOT have a .messages field — persona_extract.py uses the flat log list.

    The plan documents (incorrectly) mentioned logs[].messages[]; the real shape
    is a FLAT list of SessionLog objects. This test asserts the flat contract.

    If this unexpectedly fails (the parser adds .messages), consult
    backend/application/services/agent_queries/persona_extract.py before changing
    the persona service — it was designed for the flat shape.
    """
    first_log = parsed_session.logs[0]
    assert not hasattr(first_log, "messages"), (
        "SessionLog unexpectedly grew a 'messages' attribute. "
        "persona_extract.py consumes the FLAT log list (session.logs), not a nested "
        "messages list. If the parser now nests logs, update persona_extract.py."
    )


# ---------------------------------------------------------------------------
# Integration: fixture produces exactly 3 candidates (R1 + R2 + R3)
# ---------------------------------------------------------------------------

def test_synthetic_fixture_yields_three_candidates(parsed_session):
    """End-to-end: parse → extract_candidates should yield exactly 3 candidates.

    Fixture design:
      - Message index 4: R1 (op remember …)
      - Message index 6: R2 (from now on …)
      - Message index 8: R3 (I prefer …)

    If this count changes, the fixture or the rule set changed. Update accordingly.
    """
    from backend.application.services.agent_queries.persona_extract import extract_candidates
    candidates = extract_candidates(parsed_session)
    assert len(candidates) == 3, (
        f"Expected 3 candidates (R1+R2+R3) from synthetic fixture, got {len(candidates)}. "
        f"Candidates: {[(c['category'], c['text'][:50]) for c in candidates]}"
    )
    categories = {c["category"] for c in candidates}
    assert "from-args" in categories, "Expected R1 (from-args) candidate"
    assert "preference" in categories, "Expected R2/R3 (preference) candidates"
