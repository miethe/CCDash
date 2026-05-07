"""Regression tests for the shared session-feature correlation pipeline (P3-004).

Covers the seven acceptance-criteria edge cases for ``correlate_session()``:
1. Explicit links (entity_links) → ``high`` confidence
2. Inferred links via phase hints → ``high`` confidence
3. Inferred links via task hints → ``medium`` confidence
4. Command token matching → ``medium`` confidence
5. Subagent sessions (lineage) → ``low`` confidence, inherited from parent
6. Missing feature links → ``unknown`` confidence, no evidence
7. Ambiguous hints — session hinting at multiple features picks highest confidence
"""
from __future__ import annotations

import json
import unittest

from backend.application.services.agent_queries.session_correlation import correlate_session
from backend.application.services.agent_queries.models import SessionCorrelation


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _session(
    sid: str = "session-1",
    *,
    name: str = "some session",
    status: str = "completed",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    task_id: str | None = None,
    session_forensics_json: dict | None = None,
) -> dict:
    """Minimal session dict matching the DB row shape read by correlate_session."""
    return {
        "id": sid,
        "name": name,
        "status": status,
        "start_time": "2026-01-01T00:00:00Z",
        "parent_session_id": parent_session_id,
        "root_session_id": root_session_id,
        "task_id": task_id,
        "session_forensics_json": json.dumps(session_forensics_json) if session_forensics_json else None,
    }


def _link(
    *,
    source_type: str = "session",
    source_id: str = "session-1",
    target_type: str = "feature",
    target_id: str = "FEAT-001",
    link_type: str = "explicit",
) -> dict:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
        "link_type": link_type,
    }


def _feature(
    fid: str = "FEAT-001",
    *,
    name: str = "Authentication Flow",
    status: str = "active",
) -> dict:
    return {"id": fid, "name": name, "status": status}


# ── Tests ─────────────────────────────────────────────────────────────────────


class ExplicitLinkTests(unittest.IsolatedAsyncioTestCase):
    """AC-1: Explicit entity_links produce high confidence."""

    async def test_session_to_feature_link_yields_high_confidence(self) -> None:
        session = _session("sess-link")
        link = _link(source_type="session", source_id="sess-link", target_type="feature", target_id="FEAT-001")
        features = [_feature("FEAT-001")]

        result = await correlate_session(session, [link], features)

        self.assertIsInstance(result, SessionCorrelation)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.feature_id, "FEAT-001")
        self.assertEqual(result.feature_name, "Authentication Flow")
        self.assertTrue(any(ev.source_type == "explicit_link" for ev in result.evidence))

    async def test_reverse_link_feature_to_session_also_yields_high_confidence(self) -> None:
        """entity_links can be stored in either direction; both must resolve."""
        session = _session("sess-rev")
        link = _link(source_type="feature", source_id="FEAT-002", target_type="session", target_id="sess-rev")
        features = [_feature("FEAT-002", name="Reverse Feature")]

        result = await correlate_session(session, [link], features)

        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.feature_id, "FEAT-002")

    async def test_link_for_different_session_is_ignored(self) -> None:
        """Links that reference a different session ID must not match."""
        session = _session("sess-mine")
        link = _link(source_type="session", source_id="sess-other", target_type="feature", target_id="FEAT-001")
        features = [_feature("FEAT-001")]

        result = await correlate_session(session, [link], features)

        self.assertEqual(result.confidence, "unknown")
        self.assertIsNone(result.feature_id)

    async def test_link_to_unknown_feature_is_ignored(self) -> None:
        """A link whose target_id is not in the features list must be skipped."""
        session = _session("sess-x")
        link = _link(source_type="session", source_id="sess-x", target_type="feature", target_id="FEAT-GHOST")
        features = [_feature("FEAT-001")]

        result = await correlate_session(session, [link], features)

        self.assertEqual(result.confidence, "unknown")


class PhaseHintTests(unittest.IsolatedAsyncioTestCase):
    """AC-2: Phase hints in session_forensics_json produce high confidence."""

    async def test_phase_hints_produce_high_confidence(self) -> None:
        session = _session(
            "sess-phase",
            session_forensics_json={"phaseHints": ["Phase 3 — DB migrations"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "high")
        phase_ev = [ev for ev in result.evidence if ev.source_type == "phase_hint"]
        self.assertEqual(len(phase_ev), 1)
        self.assertIn("Phase 3", phase_ev[0].source_label)

    async def test_phase_number_extracted_from_hint(self) -> None:
        session = _session(
            "sess-pnum",
            session_forensics_json={"phaseHints": ["Phase 7 — auth refactor"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.phase_number, 7)
        self.assertIsNotNone(result.phase_title)

    async def test_snake_case_phase_hints_key_also_works(self) -> None:
        """Forensics payload may use phase_hints (snake_case) or phaseHints (camelCase)."""
        session = _session(
            "sess-snake",
            session_forensics_json={"phase_hints": ["Phase 2"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "high")

    async def test_no_phase_hints_returns_unknown(self) -> None:
        session = _session("sess-nophase", session_forensics_json={})

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "unknown")


class TaskHintTests(unittest.IsolatedAsyncioTestCase):
    """AC-3: Task hints in session_forensics_json produce medium confidence."""

    async def test_task_hints_produce_medium_confidence(self) -> None:
        session = _session(
            "sess-task",
            session_forensics_json={"taskHints": ["T3-007"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "medium")
        task_ev = [ev for ev in result.evidence if ev.source_type == "task_hint"]
        self.assertEqual(len(task_ev), 1)
        self.assertEqual(task_ev[0].source_label, "T3-007")

    async def test_task_id_and_title_resolved_from_hint(self) -> None:
        session = _session(
            "sess-tidtitle",
            session_forensics_json={"taskHints": ["T1-002"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.task_id, "T1-002")
        self.assertEqual(result.task_title, "T1-002")

    async def test_snake_case_task_hints_key_also_works(self) -> None:
        session = _session(
            "sess-task-snake",
            session_forensics_json={"task_hints": ["T5-010"]},
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "medium")

    async def test_multiple_task_hints_accumulate_evidence(self) -> None:
        session = _session(
            "sess-multitask",
            session_forensics_json={"taskHints": ["T1-001", "T1-002"]},
        )

        result = await correlate_session(session, [], [])

        task_ev = [ev for ev in result.evidence if ev.source_type == "task_hint"]
        self.assertEqual(len(task_ev), 2)


class CommandTokenTests(unittest.IsolatedAsyncioTestCase):
    """AC-4: Feature slug tokens in session task_id or forensics produce medium confidence."""

    async def test_feature_id_token_in_task_id_matches(self) -> None:
        """Session task_id containing the feature slug should match at medium confidence."""
        session = _session("sess-cmd", task_id="feat-auth-flow-implement")
        features = [_feature("feat-auth-flow", name="Auth Flow")]

        result = await correlate_session(session, [], features)

        self.assertEqual(result.confidence, "medium")
        cmd_ev = [ev for ev in result.evidence if ev.source_type == "command_token"]
        self.assertEqual(len(cmd_ev), 1)
        self.assertEqual(cmd_ev[0].source_id, "feat-auth-flow")

    async def test_feature_name_token_in_initial_prompt_matches(self) -> None:
        """Feature name normalised to slug must also match when found in forensics initialPrompt."""
        session = _session(
            "sess-prompt",
            session_forensics_json={"initialPrompt": "implement the auth-flow feature now"},
        )
        features = [_feature("FEAT-99", name="auth-flow")]

        result = await correlate_session(session, [], features)

        self.assertEqual(result.confidence, "medium")

    async def test_short_token_under_4_chars_is_ignored(self) -> None:
        """Tokens shorter than 4 characters must not produce spurious matches."""
        session = _session("sess-short", task_id="do run xyz")
        features = [_feature("xyz", name="xyz")]

        result = await correlate_session(session, [], features)

        # "xyz" is 3 chars → below threshold; should not match
        cmd_ev = [ev for ev in result.evidence if ev.source_type == "command_token"]
        self.assertEqual(len(cmd_ev), 0)

    async def test_no_task_id_and_no_forensics_yields_unknown(self) -> None:
        session = _session("sess-notok")
        features = [_feature("FEAT-001")]

        result = await correlate_session(session, [], features)

        self.assertEqual(result.confidence, "unknown")

    async def test_snake_case_command_keys_in_forensics_matched(self) -> None:
        """command or task_description key (snake_case) should also be searched."""
        session = _session(
            "sess-cmd-snake",
            session_forensics_json={"command": "work on feat-auth-flow"},
        )
        features = [_feature("feat-auth-flow", name="Auth Flow Feature")]

        result = await correlate_session(session, [], features)

        self.assertEqual(result.confidence, "medium")


class LineageTests(unittest.IsolatedAsyncioTestCase):
    """AC-5: Child sessions inherit parent correlation at low confidence."""

    async def test_child_inherits_parent_correlation_at_low_confidence(self) -> None:
        parent_corr = SessionCorrelation(
            feature_id="FEAT-001",
            feature_name="Authentication Flow",
            confidence="high",
            evidence=[],
        )
        child = _session("sess-child", parent_session_id="sess-parent")

        result = await correlate_session(
            child,
            links=[],
            features=[_feature("FEAT-001")],
            prior_correlations={"sess-parent": parent_corr},
        )

        self.assertEqual(result.confidence, "low")
        lineage_ev = [ev for ev in result.evidence if ev.source_type == "lineage"]
        self.assertEqual(len(lineage_ev), 1)
        self.assertIn("sess-parent", lineage_ev[0].detail)

    async def test_child_uses_root_session_when_no_direct_parent_correlation(self) -> None:
        """Root session correlation is used if parent is not in prior_correlations."""
        root_corr = SessionCorrelation(
            feature_id="FEAT-002",
            feature_name="Session Board",
            confidence="medium",
            evidence=[],
        )
        child = _session("sess-child2", root_session_id="sess-root")

        result = await correlate_session(
            child,
            links=[],
            features=[_feature("FEAT-002", name="Session Board")],
            prior_correlations={"sess-root": root_corr},
        )

        self.assertEqual(result.confidence, "low")
        self.assertIsNotNone(result.evidence)

    async def test_lineage_not_inherited_when_ancestor_confidence_is_low(self) -> None:
        """An ancestor with only 'low' confidence itself must NOT propagate lineage."""
        weak_corr = SessionCorrelation(
            feature_id="FEAT-003",
            feature_name="Weak Feature",
            confidence="low",
            evidence=[],
        )
        child = _session("sess-weak-child", parent_session_id="sess-weak-parent")

        result = await correlate_session(
            child,
            links=[],
            features=[_feature("FEAT-003", name="Weak Feature")],
            prior_correlations={"sess-weak-parent": weak_corr},
        )

        lineage_ev = [ev for ev in result.evidence if ev.source_type == "lineage"]
        self.assertEqual(len(lineage_ev), 0)

    async def test_lineage_not_inherited_when_ancestor_has_no_feature_id(self) -> None:
        """Ancestor correlation without a feature_id provides no useful lineage."""
        no_feat_corr = SessionCorrelation(
            feature_id=None,
            confidence="high",
            evidence=[],
        )
        child = _session("sess-nofeat-child", parent_session_id="sess-nofeat-parent")

        result = await correlate_session(
            child,
            links=[],
            features=[],
            prior_correlations={"sess-nofeat-parent": no_feat_corr},
        )

        lineage_ev = [ev for ev in result.evidence if ev.source_type == "lineage"]
        self.assertEqual(len(lineage_ev), 0)

    async def test_self_reference_does_not_create_lineage_loop(self) -> None:
        """A session whose parent_session_id equals its own id must not produce lineage."""
        corr = SessionCorrelation(
            feature_id="FEAT-001",
            confidence="high",
            evidence=[],
        )
        session = _session("sess-self", parent_session_id="sess-self")

        result = await correlate_session(
            session,
            links=[],
            features=[_feature("FEAT-001")],
            prior_correlations={"sess-self": corr},
        )

        lineage_ev = [ev for ev in result.evidence if ev.source_type == "lineage"]
        self.assertEqual(len(lineage_ev), 0)


class MissingLinksTests(unittest.IsolatedAsyncioTestCase):
    """AC-6: Session with no matching heuristics returns unknown confidence."""

    async def test_session_with_no_links_no_hints_returns_unknown(self) -> None:
        session = _session("sess-empty")

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "unknown")
        self.assertIsNone(result.feature_id)
        self.assertEqual(result.evidence, [])

    async def test_session_with_unrelated_links_returns_unknown(self) -> None:
        """Links for other sessions must not affect the result."""
        session = _session("sess-nolink")
        unrelated_link = _link(source_type="session", source_id="sess-other", target_type="feature", target_id="FEAT-001")
        features = [_feature("FEAT-001")]

        result = await correlate_session(session, [unrelated_link], features)

        self.assertEqual(result.confidence, "unknown")

    async def test_empty_features_list_with_task_id_yields_unknown(self) -> None:
        """Command token matching against an empty features list cannot find any match."""
        session = _session("sess-nofeat", task_id="some-feature-slug-here")

        result = await correlate_session(session, [], [])

        # no features to match against → unknown
        self.assertEqual(result.confidence, "unknown")

    async def test_none_prior_correlations_defaults_gracefully(self) -> None:
        """Passing prior_correlations=None must not raise."""
        session = _session("sess-no-prior")

        result = await correlate_session(session, [], [], prior_correlations=None)

        self.assertEqual(result.confidence, "unknown")


class AmbiguousHintsTests(unittest.IsolatedAsyncioTestCase):
    """AC-7: Session matching multiple features selects highest-confidence evidence."""

    async def test_explicit_link_wins_over_command_token(self) -> None:
        """When a session has both an explicit link (high) and a command token (medium),
        overall confidence is high and the feature from the explicit link is primary."""
        session = _session(
            "sess-multi",
            task_id="feat-search-index-task",
        )
        link = _link(
            source_type="session",
            source_id="sess-multi",
            target_type="feature",
            target_id="FEAT-EXPLICIT",
        )
        features = [
            _feature("FEAT-EXPLICIT", name="Explicit Feature"),
            _feature("feat-search-index", name="Search Index"),
        ]

        result = await correlate_session(session, [link], features)

        self.assertEqual(result.confidence, "high")
        # Explicit link takes priority in feature binding
        self.assertEqual(result.feature_id, "FEAT-EXPLICIT")

    async def test_phase_hint_wins_over_task_hint(self) -> None:
        """Phase hints (high) outrank task hints (medium) in overall confidence."""
        session = _session(
            "sess-pht",
            session_forensics_json={
                "phaseHints": ["Phase 4 — integration"],
                "taskHints": ["T4-003"],
            },
        )

        result = await correlate_session(session, [], [])

        self.assertEqual(result.confidence, "high")

    async def test_two_command_token_matches_both_present_in_evidence(self) -> None:
        """Both features matching via command tokens should each produce evidence."""
        session = _session(
            "sess-two-tokens",
            task_id="feat-alpha and feat-beta work",
        )
        features = [
            _feature("feat-alpha", name="Alpha"),
            _feature("feat-beta", name="Beta"),
        ]

        result = await correlate_session(session, [], features)

        cmd_ev = [ev for ev in result.evidence if ev.source_type == "command_token"]
        matched_ids = {ev.source_id for ev in cmd_ev}
        self.assertEqual(matched_ids, {"feat-alpha", "feat-beta"})
        # Overall confidence still medium (best among command_token evidence)
        self.assertEqual(result.confidence, "medium")

    async def test_lineage_does_not_override_direct_evidence(self) -> None:
        """When a session has its own evidence, lineage provides additional but lower evidence;
        the higher-confidence direct evidence governs the final confidence level."""
        parent_corr = SessionCorrelation(
            feature_id="FEAT-PARENT",
            feature_name="Parent Feature",
            confidence="high",
            evidence=[],
        )
        session = _session(
            "sess-own-ev",
            parent_session_id="sess-parent",
            session_forensics_json={"taskHints": ["T2-005"]},
        )

        result = await correlate_session(
            session,
            links=[],
            features=[_feature("FEAT-PARENT", name="Parent Feature")],
            prior_correlations={"sess-parent": parent_corr},
        )

        # Task hint = medium; lineage = low; overall should be medium (best direct)
        self.assertEqual(result.confidence, "medium")
        sources = {ev.source_type for ev in result.evidence}
        self.assertIn("task_hint", sources)
        self.assertIn("lineage", sources)


class ModelImportTests(unittest.TestCase):
    """Smoke tests: the public imports resolve correctly."""

    def test_correlate_session_importable(self) -> None:
        from backend.application.services.agent_queries.session_correlation import correlate_session  # noqa: F401

    def test_session_correlation_model_importable(self) -> None:
        from backend.application.services.agent_queries.models import (  # noqa: F401
            SessionCorrelation,
            SessionCorrelationEvidence,
        )

    def test_correlate_session_in_package_all(self) -> None:
        import backend.application.services.agent_queries.session_correlation as mod
        self.assertIn("correlate_session", mod.__all__)


if __name__ == "__main__":
    unittest.main()
