"""Unit tests for the deterministic AAR review service (ccdash-aar-review-mvp).

Covers:
- AC-1..3: document->session correlation (explicit, two-hop, none).
- AC-4..7: the four deterministic flags, each independently testable as pure
  functions over already-fetched rows (per Implementation Notes step 3).
- AC-8: the verdict combinator's four quadrants.
- AC-12: the model-free ``aar_review_candidate`` observability log event.

No LLM/agent-invocation client is imported anywhere in this file or in
``aar_review.py`` (AC-13; verified by manual reviewer grep per the contract).
"""
import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.aar_review import (
    AARReviewQueryService,
    claimed_files_from_frontmatter,
    compute_verdict,
    evaluate_context_ballooning,
    evaluate_generic_agent_vs_specialist,
    evaluate_missing_artifacts,
    evaluate_stack_ineffectiveness,
    resolve_direct_session_links,
    resolve_feature_link,
    resolve_feature_session_ids,
)


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, documents_repo, sessions_repo, links_repo):
        self.db = object()
        self._documents_repo = documents_repo
        self._sessions_repo = sessions_repo
        self._links_repo = links_repo

    def documents(self):
        return self._documents_repo

    def sessions(self):
        return self._sessions_repo

    def entity_links(self):
        return self._links_repo


def _context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _ports(*, documents=None, sessions=None, links=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            documents_repo=documents or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            sessions_repo=sessions or types.SimpleNamespace(
                get_by_id=AsyncMock(return_value=None),
                get_file_updates=AsyncMock(return_value=[]),
            ),
            links_repo=links or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


def _doc_row(doc_id: str = "doc-1", frontmatter: dict | None = None, project_id: str = "project-1") -> dict:
    return {
        "id": doc_id,
        "project_id": project_id,
        "frontmatter_json": json.dumps(frontmatter or {}),
    }


class CorrelationTests(unittest.IsolatedAsyncioTestCase):
    """AC-1, AC-2, AC-3."""

    async def test_explicit_session_ref_via_entity_links(self) -> None:
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[
                    {
                        "source_type": "document",
                        "source_id": "doc-1",
                        "target_type": "session",
                        "target_id": "session-1",
                        "confidence": 1.0,
                        "metadata_json": json.dumps({"linkStrategy": "explicit_session_ref"}),
                    }
                ]
            )
        )
        documents_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=_doc_row()))
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "session-1"}),
            get_file_updates=AsyncMock(return_value=[]),
        )
        ports = _ports(documents=documents_repo, sessions=sessions_repo, links=links_repo)

        result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.correlation_confidence, 1.0)
        self.assertEqual(result.correlation_strategy, "explicit_session_ref")
        self.assertEqual(result.session_refs, ["session-1"])

    async def test_explicit_session_ref_falls_back_to_frontmatter_when_unsynced(self) -> None:
        documents_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=_doc_row(frontmatter={"session_id": "session-9"}))
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "session-9"}),
            get_file_updates=AsyncMock(return_value=[]),
        )
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(documents=documents_repo, sessions=sessions_repo, links=links_repo)

        result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.correlation_confidence, 1.0)
        self.assertEqual(result.correlation_strategy, "explicit_session_ref")
        self.assertEqual(result.session_refs, ["session-9"])

    async def test_two_hop_doc_feature_session_fallback(self) -> None:
        def _links_for(entity_type, entity_id, *_args, **_kwargs):
            if entity_type == "document":
                return [
                    {
                        "source_type": "document",
                        "source_id": "doc-1",
                        "target_type": "feature",
                        "target_id": "feature-1",
                        "confidence": 0.74,
                        "metadata_json": json.dumps({"linkStrategy": "path_feature_hint"}),
                    }
                ]
            if entity_type == "feature":
                return [
                    {
                        "source_type": "feature",
                        "source_id": "feature-1",
                        "target_type": "session",
                        "target_id": "session-2",
                        "confidence": 0.9,
                    }
                ]
            return []

        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(side_effect=_links_for))
        documents_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=_doc_row()))
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "session-2"}),
            get_file_updates=AsyncMock(return_value=[]),
        )
        ports = _ports(documents=documents_repo, sessions=sessions_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.aar_review.detect_failure_patterns",
            new=AsyncMock(return_value={"items": []}),
        ):
            result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.correlation_strategy, "two_hop_doc_feature_session")
        self.assertEqual(result.correlation_confidence, 0.74)
        self.assertGreaterEqual(result.correlation_confidence, 0.64)
        self.assertEqual(result.session_refs, ["session-2"])

    async def test_no_correlation_returns_surface_only_without_error(self) -> None:
        documents_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=_doc_row()))
        ports = _ports(documents=documents_repo)

        result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.session_refs, [])
        self.assertEqual(result.correlation_confidence, 0.0)
        self.assertEqual(result.verdict, "surface_only")
        self.assertIn("no correlated sessions found", result.reasons)

    async def test_document_not_found_returns_error_status(self) -> None:
        documents_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=None),
            get_by_path=AsyncMock(return_value=None),
        )
        ports = _ports(documents=documents_repo)

        result = await AARReviewQueryService().get_review(_context(), ports, "missing-doc")

        self.assertEqual(result.status, "error")
        self.assertIn("document not found", result.reasons)


class ObservabilityEventTests(unittest.IsolatedAsyncioTestCase):
    """AC-12."""

    async def test_successful_verdict_emits_exactly_one_log_event(self) -> None:
        documents_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=_doc_row()))
        ports = _ports(documents=documents_repo)

        with patch(
            "backend.application.services.agent_queries.aar_review.log_aar_review_candidate"
        ) as mock_log:
            result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        mock_log.assert_called_once()
        _, kwargs = mock_log.call_args
        self.assertEqual(kwargs["document_id"], "doc-1")
        self.assertEqual(kwargs["verdict"], result.verdict)
        self.assertEqual(kwargs["session_refs"], [])


class DirectLinkPureFunctionTests(unittest.TestCase):
    def test_resolve_direct_session_links_prefers_highest_confidence(self) -> None:
        links = [
            {
                "source_type": "document", "source_id": "doc-1",
                "target_type": "session", "target_id": "session-a",
                "confidence": 0.96,
                "metadata_json": json.dumps({"linkStrategy": "task_session_ref"}),
            },
            {
                "source_type": "document", "source_id": "doc-1",
                "target_type": "session", "target_id": "session-b",
                "confidence": 1.0,
                "metadata_json": json.dumps({"linkStrategy": "explicit_session_ref"}),
            },
        ]
        session_ids, confidence, strategy = resolve_direct_session_links("doc-1", links, [])
        self.assertEqual(session_ids, ["session-b"])
        self.assertEqual(confidence, 1.0)
        self.assertEqual(strategy, "explicit_session_ref")

    def test_resolve_feature_link_and_feature_session_ids(self) -> None:
        doc_links = [
            {
                "source_type": "document", "source_id": "doc-1",
                "target_type": "feature", "target_id": "feature-9",
                "confidence": 0.98,
                "metadata_json": json.dumps({"linkStrategy": "explicit_frontmatter_ref"}),
            },
        ]
        feature_id, confidence, strategy = resolve_feature_link("doc-1", doc_links)
        self.assertEqual(feature_id, "feature-9")
        self.assertEqual(confidence, 0.98)
        self.assertEqual(strategy, "explicit_frontmatter_ref")

        feature_links = [
            {"source_type": "feature", "source_id": "feature-9", "target_type": "session", "target_id": "session-x"},
        ]
        self.assertEqual(resolve_feature_session_ids("feature-9", feature_links), ["session-x"])


class FlagTests(unittest.TestCase):
    """AC-4..7: each flag as an independent pure-function test matrix."""

    # AC-4: context_ballooning
    def test_context_ballooning_triggers_above_threshold(self) -> None:
        flag = evaluate_context_ballooning(
            [{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 90.0}],
            threshold_pct=85.0,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "high")
        self.assertIn("s1", flag.evidence_refs[0])

    def test_context_ballooning_does_not_trigger_below_threshold(self) -> None:
        flag = evaluate_context_ballooning(
            [{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 40.0}],
            threshold_pct=85.0,
        )
        self.assertFalse(flag.triggered)

    def test_context_ballooning_missing_data_is_not_an_error(self) -> None:
        flag = evaluate_context_ballooning(
            [{"id": "s1", "context_window_size": 0, "context_utilization_pct": 0.0}],
            threshold_pct=85.0,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "insufficient token data")

    # AC-5: missing_artifacts
    def test_missing_artifacts_no_claim_is_not_an_error(self) -> None:
        flag = evaluate_missing_artifacts([], {})
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no claimed artifacts to check")

    def test_missing_artifacts_triggers_when_claim_not_produced(self) -> None:
        claimed = claimed_files_from_frontmatter({"files_affected": ["backend/foo.py", "backend/bar.py"]})
        flag = evaluate_missing_artifacts(claimed, {"session-1": ["backend/foo.py"]})
        self.assertTrue(flag.triggered)
        self.assertIn("backend/bar.py", flag.evidence_refs)

    def test_missing_artifacts_does_not_trigger_when_fully_covered(self) -> None:
        claimed = claimed_files_from_frontmatter({"files_affected": ["backend/foo.py"]})
        flag = evaluate_missing_artifacts(claimed, {"session-1": ["backend/foo.py"]})
        self.assertFalse(flag.triggered)

    # AC-6: generic_agent_vs_specialist
    def test_generic_agent_triggers_for_known_specialist_domain(self) -> None:
        flag = evaluate_generic_agent_vs_specialist(
            [{"id": "s1", "subagent_type": "general-purpose"}],
            {"s1": ["components/Widget.tsx"]},
        )
        self.assertTrue(flag.triggered)
        self.assertIn("ui-engineer-enhanced", flag.evidence_refs[0])

    def test_generic_agent_no_agent_data_is_not_an_error(self) -> None:
        flag = evaluate_generic_agent_vs_specialist([{"id": "s1"}], {})
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no agent-usage data")

    # AC-7: stack_ineffectiveness
    def test_stack_ineffectiveness_triggers_on_failure_pattern_hit(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"],
            {"s1": ["backend/foo.py"]},
            [{"title": "Debug loop", "severity": "high", "sessionIds": ["s1"]}],
            feature_scope_available=True,
        )
        self.assertTrue(flag.triggered)

    def test_stack_ineffectiveness_no_hit_below_threshold(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, [], feature_scope_available=True,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no failure/retry pattern detected for the resolved stack")

    def test_stack_ineffectiveness_unmapped_stack_is_not_an_error(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["README.unknownext"]}, [], feature_scope_available=True,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "stack unresolved")

    def test_stack_ineffectiveness_no_feature_scope_is_not_an_error(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, [], feature_scope_available=False,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no feature scope available for failure-pattern lookup")


class VerdictCombinatorTests(unittest.TestCase):
    """AC-8: all four quadrants."""

    def test_high_confidence_with_flags_recommends_deep_review(self) -> None:
        flags = [evaluate_context_ballooning([{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 95.0}], 85.0)]
        verdict, reasons = compute_verdict(0.9, True, flags, 0.64)
        self.assertEqual(verdict, "deep_review_recommended")
        self.assertTrue(reasons)

    def test_high_confidence_no_flags_is_surface_only(self) -> None:
        flags = [evaluate_context_ballooning([{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 10.0}], 85.0)]
        verdict, reasons = compute_verdict(0.9, True, flags, 0.64)
        self.assertEqual(verdict, "surface_only")
        self.assertIn("no flags triggered", reasons)

    def test_low_confidence_with_flags_is_forced_surface_only(self) -> None:
        flags = [evaluate_context_ballooning([{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 95.0}], 85.0)]
        verdict, reasons = compute_verdict(0.5, True, flags, 0.64)
        self.assertEqual(verdict, "surface_only")
        self.assertTrue(any("below the floor" in reason for reason in reasons))

    def test_no_evidence_is_surface_only(self) -> None:
        verdict, reasons = compute_verdict(0.0, False, [], 0.64)
        self.assertEqual(verdict, "surface_only")
        self.assertIn("no correlated sessions found", reasons)


if __name__ == "__main__":
    unittest.main()
