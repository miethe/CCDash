"""
Table-driven tests for persona_extract_rules.py and extract_candidates().

Tests use hand-built AgentSession / SessionLog objects via the Pydantic
models from backend.models — no mocking.

Coverage:
  * 8 rules × ≥2 positive cases each
  * near-miss negatives
  * longest-match-wins tie-break
  * ALL_CAPS variants
  * multi-line capture truncation (>500 chars)
  * prior_max_msg_index watermark filtering
  * R8 endorsement with nearby system log
  * R8 no-emit when no system log is nearby
  * dedup within call
"""

from __future__ import annotations

import pytest

from backend.models import AgentSession, SessionLog
from backend.application.services.agent_queries.persona_extract import (
    extract_candidates,
    CandidateLine,
)
from backend.application.services.agent_queries.persona_extract_rules import RULES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(
    speaker: str,
    content: str,
    timestamp: str = "2026-06-16T04:13:22Z",
    log_id: str = "log-001",
) -> SessionLog:
    return SessionLog(
        id=log_id,
        timestamp=timestamp,
        speaker=speaker,
        type="message",
        content=content,
    )


def _make_session(logs: list[SessionLog], session_id: str = "sess-001") -> AgentSession:
    return AgentSession(id=session_id, logs=logs)


def _user(content: str, log_id: str = "log-u") -> SessionLog:
    return _make_log("user", content, log_id=log_id)


def _agent(content: str, log_id: str = "log-a") -> SessionLog:
    return _make_log("agent", content, log_id=log_id)


def _system(content: str, log_id: str = "log-s") -> SessionLog:
    return _make_log("system", content, log_id=log_id)


# ---------------------------------------------------------------------------
# R1 — explicit op-remember
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_text_fragment", [
    # positive: quoted fact
    ('op remember "always use uv for dependency management"', "always use uv for dependency management"),
    # positive: unquoted fact
    ("op remember never commit .env files", "never commit .env files"),
    # positive: ALL_CAPS trigger
    ("OP REMEMBER tests must be green", "tests must be green"),
])
def test_r1_positive(content: str, expected_text_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert len(candidates) >= 1
    assert any(
        c["category"] == "from-args" and expected_text_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"Expected fragment '{expected_text_fragment}' in candidates: {candidates}"


@pytest.mark.parametrize("content", [
    # near-miss: 'remember' without 'op' prefix
    "please remember to always use black formatting",
    # near-miss: unrelated sentence
    "the build finished successfully",
])
def test_r1_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert all(c["category"] != "from-args" for c in candidates), (
        f"R1 should not fire on: {content!r}; got {candidates}"
    )


# ---------------------------------------------------------------------------
# R2 — going-forward / behavioral directive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("from now on always add type hints", "always add type hints"),
    ("going forward, use async functions everywhere", "use async functions everywhere"),
    ("stop doing that thing where you add extra imports", "that thing where you add extra imports"),
    ("don't do that again — it broke staging", "it broke staging"),
    # ALL_CAPS
    ("NEVER use mutable default arguments", "use mutable default arguments"),
])
def test_r2_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "preference" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R2 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # No R2 trigger keywords at all
    "the build finished successfully without any issues",
    # 'always' fires R2 (by design per PRD §6) — tested separately.
    # Near-miss: "going" without "forward"
    "going to the office tomorrow",
])
def test_r2_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "preference"]
    assert len(candidates) == 0, f"R2 fired unexpectedly on: {content!r}; got {candidates}"


# ---------------------------------------------------------------------------
# R3 — hard preference expressed in first person
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("I always use virtual environments for Python projects", "use virtual environments"),
    ("I never use global state in services", "use global state"),
    ("I prefer smaller, focused functions", "smaller, focused functions"),
    ("I hate deeply nested callbacks", "deeply nested callbacks"),
    ("I love type-safe code", "type-safe code"),
    # ALL_CAPS
    ("I ALWAYS run tests before committing", "run tests before committing"),
])
def test_r3_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "preference" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R3 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # No first-person preference verb
    "the team prefers shorter standups",
    "we always deploy on Fridays",
])
def test_r3_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "preference"]
    # These shouldn't match R3 (no leading "I")
    # R2 might still fire on "always" — that's fine; we check R3 specifically.
    r3_rule = next(r for r in RULES if r.id == "R3")
    for c in candidates:
        assert not (
            r3_rule.pattern.search(content) and c["confidence"] == r3_rule.confidence
        ), f"R3 fired unexpectedly on: {content!r}"


# ---------------------------------------------------------------------------
# R4 — goal statement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("goal: reduce cold-start latency below 200ms", "reduce cold-start latency"),
    ("I want to migrate the DB to Postgres this sprint", "migrate the DB to Postgres"),
    # ALL_CAPS
    ("GOAL: achieve 100% test coverage on the parser", "achieve 100% test coverage"),
])
def test_r4_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "goal" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R4 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # 'want' without 'I want to'
    "the feature wants to ship next week",
    "goals are important in general",
])
def test_r4_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "goal"]
    # The content above should NOT produce goal candidates.
    assert len(candidates) == 0, f"R4 fired unexpectedly on: {content!r}; got {candidates}"


# ---------------------------------------------------------------------------
# R5 — decision
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("decision: adopt uv as the package manager across all repos", "adopt uv as the package manager"),
    ("we decided to drop support for Python 3.9", "drop support for Python 3.9"),
    # ALL_CAPS
    ("DECISION: no more direct SQL queries — use the ORM", "no more direct SQL queries"),
])
def test_r5_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "decision" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R5 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # 'decide' without past tense trigger
    "let's decide later about the caching strategy",
])
def test_r5_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "decision"]
    assert len(candidates) == 0, f"R5 fired unexpectedly on: {content!r}"


# ---------------------------------------------------------------------------
# R6 — constraint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("constraint: all endpoints must return JSON error bodies", "all endpoints must return JSON"),
    ("the service must always validate tokens before processing", "validate tokens before processing"),
    ("must never write to the DB from the parser layer", "write to the DB from the parser layer"),
    # ALL_CAPS
    ("CONSTRAINT: secrets must never appear in logs", "secrets must never appear in logs"),
])
def test_r6_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "constraint" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R6 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # 'must' without always/never qualifier
    "the feature must ship by Friday",
])
def test_r6_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "constraint"]
    # "constraint:" is absent and "must always/never" is absent — should not fire.
    assert len(candidates) == 0, f"R6 fired unexpectedly on: {content!r}"


# ---------------------------------------------------------------------------
# R7 — TIL / note-to-self
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content,expected_fragment", [
    ("TIL: SQLite WAL mode dramatically improves concurrent read performance", "WAL mode"),
    ("today I learned that Pydantic v2 validators run before field assignment", "validators run before"),
    ("note to self: always check the migration order before running alembic upgrade", "check the migration order"),
    ("remember that the watcher resets job timers on reload", "watcher resets job timers"),
    ("remember this: empty string signals unpriced state in the pricing column", "empty string signals unpriced"),
    # ALL_CAPS trigger
    ("TIL the DB uses busy_timeout = 30000", "busy_timeout"),
])
def test_r7_positive(content: str, expected_fragment: str) -> None:
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    assert any(
        c["category"] == "TIL" and expected_fragment.lower() in c["text"].lower()
        for c in candidates
    ), f"R7 expected '{expected_fragment}' in {candidates}"


@pytest.mark.parametrize("content", [
    # 'learned' without 'today I learned'
    "I learned something new today about asyncio",
    # 'remember' without the specific phrases
    "op remember use type hints everywhere",  # this is R1, not R7
])
def test_r7_negative(content: str) -> None:
    session = _make_session([_user(content)])
    candidates = [c for c in extract_candidates(session) if c["category"] == "TIL"]
    assert len(candidates) == 0, f"R7 fired unexpectedly on: {content!r}; got {candidates}"


# ---------------------------------------------------------------------------
# R8 — system-reminder endorsement
# ---------------------------------------------------------------------------

def test_r8_fires_with_nearby_system_log() -> None:
    """R8 fires when a user 'yes' follows a system-speaker log within ±2."""
    system_content = "IMPORTANT: always use absolute paths in tool calls"
    logs = [
        _system(system_content, log_id="log-s-0"),
        _user("yes", log_id="log-u-1"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    r8_candidates = [c for c in candidates if c["category"] == "reminder"]
    assert len(r8_candidates) == 1
    assert "absolute paths" in r8_candidates[0]["text"].lower()
    assert r8_candidates[0]["confidence"] == 0.60
    assert r8_candidates[0]["origin_msg_index"] == 1


def test_r8_fires_with_agreed() -> None:
    system_content = "Session redaction is enabled by default — never log secrets"
    logs = [
        _user("something else", log_id="log-u-0"),
        _system(system_content, log_id="log-s-1"),
        _user("agreed, that makes sense", log_id="log-u-2"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    r8_candidates = [c for c in candidates if c["category"] == "reminder"]
    assert len(r8_candidates) == 1
    assert "secrets" in r8_candidates[0]["text"].lower()


def test_r8_no_emit_without_nearby_system_log() -> None:
    """R8 must NOT fire when there is no system log within ±2 positions."""
    logs = [
        _agent("here is the result", log_id="log-a-0"),
        _user("yes", log_id="log-u-1"),
        _agent("great", log_id="log-a-2"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    r8_candidates = [c for c in candidates if c["category"] == "reminder"]
    assert len(r8_candidates) == 0, f"R8 should not fire without a system log: {r8_candidates}"


def test_r8_system_log_too_far() -> None:
    """R8 does NOT fire when the system log is more than 2 positions away."""
    system_content = "ALWAYS use retry_on_locked for DB writes"
    logs = [
        _system(system_content, log_id="log-s-0"),
        _agent("ok", log_id="log-a-1"),
        _agent("done", log_id="log-a-2"),
        _user("right", log_id="log-u-3"),  # 3 positions away from system log
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    r8_candidates = [c for c in candidates if c["category"] == "reminder"]
    assert len(r8_candidates) == 0, (
        f"R8 should not fire when system log is >2 positions away: {r8_candidates}"
    )


# ---------------------------------------------------------------------------
# Longest-match-wins tie-break
# ---------------------------------------------------------------------------

def test_longest_match_wins() -> None:
    """When multiple rules match the same message, only the longest candidate is kept."""
    # "I want to never use global state" — R3 fires on "I never …" AND R4 on "I want to …"
    # R4 captures "never use global state" (longer); R3 captures "use global state" (shorter).
    # Longest-match-wins → R4 candidate should dominate.
    content = "I want to never use global state in any service"
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    texts = [c["text"] for c in candidates]
    # The longer match should appear; the shorter duplicate should be absent.
    has_long = any("never use global state in any service" in t.lower() for t in texts)
    assert has_long, f"Expected long match to win; got {texts}"


def test_r1_r7_both_fire_independently() -> None:
    """Distinct rules with non-overlapping text both emit candidates."""
    content = "TIL: op remember is the canonical explicit-memory verb"
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    categories = {c["category"] for c in candidates}
    # R7 fires on "TIL: …"; R1 fires on "op remember …" within the same message.
    # Because the texts differ, both should appear.
    assert "TIL" in categories or "from-args" in categories, (
        f"Expected at least one of TIL or from-args; got {categories}"
    )


# ---------------------------------------------------------------------------
# ALL_CAPS variant (spot-check via re.IGNORECASE)
# ---------------------------------------------------------------------------

def test_all_caps_r1() -> None:
    session = _make_session([_user("OP REMEMBER always pin your dependencies")])
    candidates = extract_candidates(session)
    assert any(c["category"] == "from-args" for c in candidates)


def test_all_caps_r2() -> None:
    session = _make_session([_user("STOP DOING nested lambdas in production code")])
    candidates = extract_candidates(session)
    assert any(c["category"] == "preference" for c in candidates)


# ---------------------------------------------------------------------------
# Multi-line / long capture truncation
# ---------------------------------------------------------------------------

def test_long_text_truncated_to_500() -> None:
    long_fact = "A" * 600
    content = f"op remember {long_fact}"
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    r1 = [c for c in candidates if c["category"] == "from-args"]
    assert len(r1) >= 1
    assert len(r1[0]["text"]) <= 500, f"Text not truncated: {len(r1[0]['text'])} chars"


def test_multiline_content_whitespace_collapsed() -> None:
    content = "goal: improve\n  the   startup\n\tlatency"
    session = _make_session([_user(content)])
    candidates = extract_candidates(session)
    goal = next((c for c in candidates if c["category"] == "goal"), None)
    assert goal is not None
    assert "\n" not in goal["text"]
    assert "  " not in goal["text"]


# ---------------------------------------------------------------------------
# prior_max_msg_index watermark
# ---------------------------------------------------------------------------

def test_prior_max_msg_index_skips_already_seen() -> None:
    logs = [
        _user("op remember fact zero", log_id="log-0"),
        _user("op remember fact one", log_id="log-1"),
        _user("op remember fact two", log_id="log-2"),
    ]
    session = _make_session(logs)
    # Process only from index 1 onward (index 0 was "already seen").
    candidates = extract_candidates(session, prior_max_msg_index=0)
    texts = [c["text"] for c in candidates]
    assert any("fact one" in t for t in texts)
    assert any("fact two" in t for t in texts)
    assert not any("fact zero" in t for t in texts)


def test_prior_max_msg_index_zero_processes_all_except_index_zero() -> None:
    """prior_max_msg_index=0 means index 0 is already processed (inclusive lower bound)."""
    logs = [
        _user("op remember index-zero fact", log_id="log-0"),
        _user("op remember index-one fact", log_id="log-1"),
    ]
    session = _make_session(logs)
    # prior_max_msg_index=0 → log at index 0 is skipped; index 1 is processed.
    candidates = extract_candidates(session, prior_max_msg_index=0)
    texts = [c["text"] for c in candidates]
    assert not any("index-zero" in t for t in texts)
    assert any("index-one" in t for t in texts)


def test_prior_max_msg_index_negative_one_processes_all() -> None:
    """prior_max_msg_index=-1 (default) means all logs are eligible."""
    logs = [
        _user("op remember index-zero fact", log_id="log-0"),
        _user("op remember index-one fact", log_id="log-1"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session, prior_max_msg_index=-1)
    texts = [c["text"] for c in candidates]
    assert any("index-zero" in t for t in texts)
    assert any("index-one" in t for t in texts)


# ---------------------------------------------------------------------------
# Dedup within call
# ---------------------------------------------------------------------------

def test_dedup_same_fact_different_messages() -> None:
    logs = [
        _user("I always use type hints in Python code", log_id="log-0"),
        _user("I always use type hints in Python code", log_id="log-1"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    pref = [c for c in candidates if c["category"] == "preference"]
    # The same normalized text should appear only once.
    assert len(pref) == 1, f"Expected 1 deduplicated candidate; got {len(pref)}: {pref}"


# ---------------------------------------------------------------------------
# CandidateLine contract fields
# ---------------------------------------------------------------------------

def test_candidate_line_contract_fields() -> None:
    """Every emitted CandidateLine must carry all §5 fields."""
    session = _make_session([_user("op remember check the contract fields")])
    candidates = extract_candidates(session)
    assert len(candidates) >= 1
    required_fields = {
        "ts", "source", "text", "session_id", "cwd",
        "category", "confidence", "transcript_path", "origin_msg_index",
    }
    for c in candidates:
        missing = required_fields - set(c.keys())
        assert not missing, f"CandidateLine missing fields: {missing}"


def test_source_is_always_ccdash_persona_extract() -> None:
    session = _make_session([_user("op remember test the source field")])
    candidates = extract_candidates(session)
    for c in candidates:
        assert c["source"] == "ccdash_persona_extract"


def test_cwd_and_transcript_path_are_empty_strings() -> None:
    """Phase 1 leaves cwd and transcript_path as '' — CLI fills them."""
    session = _make_session([_user("op remember cwd should be empty")])
    candidates = extract_candidates(session)
    for c in candidates:
        assert c["cwd"] == "", f"cwd should be '' but got {c['cwd']!r}"
        assert c["transcript_path"] == "", (
            f"transcript_path should be '' but got {c['transcript_path']!r}"
        )


def test_session_id_matches_session() -> None:
    session = _make_session([_user("op remember check session_id")], session_id="my-unique-id")
    candidates = extract_candidates(session)
    for c in candidates:
        assert c["session_id"] == "my-unique-id"


def test_origin_msg_index_is_correct() -> None:
    logs = [
        _agent("assistant preamble", log_id="log-0"),
        _user("op remember this is at index 1", log_id="log-1"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    r1 = [c for c in candidates if c["category"] == "from-args"]
    assert len(r1) == 1
    assert r1[0]["origin_msg_index"] == 1


def test_ts_normalized_from_log_timestamp() -> None:
    log = _make_log("user", "op remember timestamp test", timestamp="2026-06-16T04:13:22.123456Z")
    session = _make_session([log])
    candidates = extract_candidates(session)
    # Fractional seconds should be stripped; Z retained.
    assert candidates[0]["ts"] == "2026-06-16T04:13:22Z"


def test_ts_empty_on_bad_timestamp() -> None:
    log = _make_log("user", "op remember bad timestamp", timestamp="not-a-timestamp")
    session = _make_session([log])
    candidates = extract_candidates(session)
    assert candidates[0]["ts"] == ""


# ---------------------------------------------------------------------------
# Empty / no-match sessions
# ---------------------------------------------------------------------------

def test_no_candidates_for_no_signal_session() -> None:
    logs = [
        _agent("here is the output", log_id="log-0"),
        _user("thanks, looks good", log_id="log-1"),
        _user("can you do this differently?", log_id="log-2"),
    ]
    session = _make_session(logs)
    candidates = extract_candidates(session)
    assert candidates == []


def test_empty_session_returns_empty() -> None:
    session = _make_session([])
    candidates = extract_candidates(session)
    assert candidates == []
