"""Phase 5 detection — parser-level facts (T5-001, T5-004, T5-005).

Covers:
  * Canonical bare model slug normalization (variant suffixes stripped).
  * Log-derived workflow grouping + subagent linkage that SURVIVES an absent
    sidecar (the parser never consults a sidecar — AC-5.2).
  * Skill attribution: a skill-load message → ``skillName`` set; otherwise None
    (explicit null contract state, never an empty-string sentinel — T5-005).

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_phase5_detection_parser.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.sessions import parse_session_file
from backend.parsers.platforms.claude_code import parser as claude_parser


class CanonicalModelSlugTests(unittest.TestCase):
    def test_strips_1m_variant_suffix_lowercase(self) -> None:
        self.assertEqual(
            claude_parser._canonical_model_slug("claude-sonnet-4-5[1m]"),
            "claude-sonnet-4-5",
        )

    def test_strips_uppercase_variant_and_lowercases(self) -> None:
        self.assertEqual(
            claude_parser._canonical_model_slug("Claude-Opus-4-8[1M]"),
            "claude-opus-4-8",
        )

    def test_bare_slug_unchanged_except_case(self) -> None:
        self.assertEqual(
            claude_parser._canonical_model_slug("claude-sonnet-4-6"),
            "claude-sonnet-4-6",
        )

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(claude_parser._canonical_model_slug(""), "")
        self.assertEqual(claude_parser._canonical_model_slug("   "), "")


class PrimarySkillNameTests(unittest.TestCase):
    def test_returns_first_named_skill(self) -> None:
        loads = [{"skill": "planning"}, {"skill": "debugging"}]
        self.assertEqual(claude_parser._primary_skill_name(loads), "planning")

    def test_absent_returns_none_not_empty_string(self) -> None:
        self.assertIsNone(claude_parser._primary_skill_name([]))
        self.assertIsNone(claude_parser._primary_skill_name(None))

    def test_skips_slash_command_sentinels(self) -> None:
        loads = [{"skill": "/model"}, {"skill": "release"}]
        self.assertEqual(claude_parser._primary_skill_name(loads), "release")


class ParserDetectionFieldTests(unittest.TestCase):
    def _write_jsonl(self, lines: list[dict], relative_path: str = "session.jsonl") -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        return path

    def _basic_session_lines(self) -> list[dict]:
        return [
            {
                "type": "assistant",
                "timestamp": "2026-02-16T10:00:00Z",
                "uuid": "a1",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-5[1m]",
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                    "content": [{"type": "text", "text": "hello"}],
                },
            }
        ]

    def test_model_slug_is_canonical_bare_value(self) -> None:
        session = parse_session_file(self._write_jsonl(self._basic_session_lines()))
        self.assertIsNotNone(session)
        assert session is not None
        # Raw model retains its variant suffix; modelSlug is the canonical bare slug.
        self.assertEqual(session.modelSlug, "claude-sonnet-4-5")

    def test_root_session_workflow_id_is_self_no_subagent_parent(self) -> None:
        session = parse_session_file(self._write_jsonl(self._basic_session_lines()))
        assert session is not None
        # Root session: workflowId groups by its own id; not a subagent.
        self.assertEqual(session.workflowId, session.id)
        self.assertIsNone(session.subagentParentId)

    def test_linkage_present_without_any_sidecar(self) -> None:
        """The parser derives linkage from logs only — no workflow.json exists.

        This is the AC-5.2 invariant at the source: linkage never depends on a
        sidecar, so it is identical whether or not one is later joined.
        """
        path = self._write_jsonl(self._basic_session_lines())
        # Deliberately assert no sidecar sits next to the session file.
        self.assertFalse((path.parent / "workflow.json").exists())
        session = parse_session_file(path)
        assert session is not None
        self.assertEqual(session.workflowId, session.id)
        # contextWindow is a sidecar-only fact → null at parse time.
        self.assertIsNone(session.contextWindow)

    def test_skill_name_absent_is_none(self) -> None:
        session = parse_session_file(self._write_jsonl(self._basic_session_lines()))
        assert session is not None
        self.assertIsNone(session.skillName)

    def test_skill_name_attributed_from_skill_load_message(self) -> None:
        lines = self._basic_session_lines()
        lines.append(
            {
                "type": "user",
                "timestamp": "2026-02-16T10:00:02Z",
                "uuid": "u2",
                "message": {
                    "role": "user",
                    "content": (
                        "<skill-format>true</skill-format>\n"
                        "Base directory for this skill: /Users/x/.claude/skills/planning\n"
                        "Planning skill loaded."
                    ),
                },
            }
        )
        session = parse_session_file(self._write_jsonl(lines))
        assert session is not None
        self.assertEqual(session.skillName, "planning")


if __name__ == "__main__":
    unittest.main()
