"""Phase 2 ("Full-Metadata Evidence Enrichment") tests for the AAR review flags.

Covers:
- T2-002 / AC-P2.2: session_detail-sourced enrichment reads
  (``gather_session_metadata``), including resilient degrade-to-empty on
  fetch failure or missing project scope.
- T2-003: the doc->feature->plan/progress->task frontmatter traversal
  (``resolve_linked_task_evidence``), including the ``None`` fallback signal
  for every "no link resolves" branch.
- T2-004..T2-007: each of the four flags exercised twice -- once with a
  resolved plan/task link (sharpened-evidence path) and once with no link at
  all (the exact Phase 1 fallback path, asserted byte-identical to the P1
  fixture in ``test_agent_queries_aar_review.py``).

Per the Phase 2 hard AC, every fallback-path assertion below checks that
``triggered``/``severity``/``rationale`` are UNCHANGED from Phase 1 -- only
``evidence_refs`` may gain additional deterministic lines when a link
resolves.
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
    evaluate_context_ballooning,
    evaluate_generic_agent_vs_specialist,
    evaluate_missing_artifacts,
    evaluate_stack_ineffectiveness,
)
from backend.application.services.agent_queries.aar_review_enrichment import (
    LinkedTaskEvidence,
    gather_session_metadata,
    resolve_linked_task_evidence,
    session_detail_bits,
)
from backend.application.services.agent_queries.session_detail import SessionDetailBundle


def _bundle(
    session_id: str,
    *,
    session: dict | None = None,
    subagents: list | None = None,
    tokens: dict | None = None,
    artifacts: list | None = None,
    links: list | None = None,
) -> SessionDetailBundle:
    return SessionDetailBundle(
        session_id=session_id,
        project_id="project-1",
        session=session or {},
        transcript=None,
        subagents=subagents,
        tokens=tokens,
        artifacts=artifacts,
        links=links,
    )


# ── T2-003: resolve_linked_task_evidence traversal ───────────────────────────


class ResolveLinkedTaskEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_none_when_feature_id_missing(self) -> None:
        ports = types.SimpleNamespace(storage=types.SimpleNamespace())
        self.assertIsNone(await resolve_linked_task_evidence(ports, None))
        self.assertIsNone(await resolve_linked_task_evidence(ports, ""))

    async def test_returns_none_when_no_document_link_resolves(self) -> None:
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = types.SimpleNamespace(
            storage=types.SimpleNamespace(entity_links=lambda: links_repo)
        )
        self.assertIsNone(await resolve_linked_task_evidence(ports, "feature-1"))

    async def test_returns_none_when_linked_docs_have_no_eligible_fields(self) -> None:
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[
                    {
                        "source_type": "feature", "source_id": "feature-1",
                        "target_type": "document", "target_id": "doc-plan-1",
                    }
                ]
            )
        )
        documents_repo = types.SimpleNamespace(
            get_many_by_ids=AsyncMock(
                return_value={"doc-plan-1": {"id": "doc-plan-1", "frontmatter_json": json.dumps({"title": "x"})}}
            )
        )
        ports = types.SimpleNamespace(
            storage=types.SimpleNamespace(
                entity_links=lambda: links_repo, documents=lambda: documents_repo
            )
        )
        self.assertIsNone(await resolve_linked_task_evidence(ports, "feature-1"))

    async def test_returns_none_on_repository_failure(self) -> None:
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(side_effect=RuntimeError("boom")))
        ports = types.SimpleNamespace(storage=types.SimpleNamespace(entity_links=lambda: links_repo))
        self.assertIsNone(await resolve_linked_task_evidence(ports, "feature-1"))

    async def test_extracts_doc_level_and_task_level_fields(self) -> None:
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[
                    {
                        "source_type": "feature", "source_id": "feature-1",
                        "target_type": "document", "target_id": "doc-plan-1",
                    }
                ]
            )
        )
        frontmatter = {
            "phase": 7,
            "files_modified": ["backend/foo.py"],
            "tasks": [
                {
                    "id": "T7-001",
                    "assigned_to": ["backend-typescript-architect"],
                    "model": "sonnet-4-6",
                    "estimated_effort": "3 pts",
                    "acceptance_criteria": ["Endpoint returns 200"],
                    "files_affected": ["backend/bar.py"],
                }
            ],
        }
        documents_repo = types.SimpleNamespace(
            get_many_by_ids=AsyncMock(
                return_value={
                    "doc-plan-1": {"id": "doc-plan-1", "frontmatter_json": json.dumps(frontmatter)}
                }
            )
        )
        ports = types.SimpleNamespace(
            storage=types.SimpleNamespace(
                entity_links=lambda: links_repo, documents=lambda: documents_repo
            )
        )

        evidence = await resolve_linked_task_evidence(ports, "feature-1")

        self.assertIsNotNone(evidence)
        self.assertIn("backend-typescript-architect", evidence.assigned_to)
        self.assertIn("sonnet-4-6", evidence.assigned_model)
        self.assertIn("3 pts", evidence.effort)
        self.assertIn("7", evidence.phase)
        self.assertIn("backend/foo.py", evidence.files_affected)
        self.assertIn("backend/bar.py", evidence.files_affected)
        self.assertIn("Endpoint returns 200", evidence.acceptance_criteria)
        self.assertEqual(evidence.source_document_ids, ("doc-plan-1",))


# ── T2-002 / AC-P2.2: gather_session_metadata ────────────────────────────────


class GatherSessionMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_when_project_id_missing(self) -> None:
        ports = types.SimpleNamespace()
        result = await gather_session_metadata(ports, None, ["session-1"])
        self.assertEqual(result, {})

    async def test_degrades_to_empty_mapping_on_fetch_failure(self) -> None:
        ports = types.SimpleNamespace()
        with patch(
            "backend.application.services.agent_queries.aar_review_enrichment.get_session_detail",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await gather_session_metadata(ports, "project-1", ["session-1"])
        self.assertEqual(result, {})

    async def test_populates_bundle_per_session_id(self) -> None:
        ports = types.SimpleNamespace()
        bundle = _bundle("session-1", session={"id": "session-1", "model_slug": "sonnet-4-6"})

        async def _fake_get_session_detail(project_id, session_id, ports_arg, **kwargs):
            return bundle if session_id == "session-1" else None

        with patch(
            "backend.application.services.agent_queries.aar_review_enrichment.get_session_detail",
            new=AsyncMock(side_effect=_fake_get_session_detail),
        ):
            result = await gather_session_metadata(ports, "project-1", ["session-1", "session-2"])
        self.assertEqual(set(result.keys()), {"session-1"})
        self.assertIs(result["session-1"], bundle)


class SessionDetailBitsTests(unittest.TestCase):
    def test_cites_context_window_model_and_observed_tokens(self) -> None:
        bundle = _bundle(
            "session-1",
            session={"context_window": "200k", "model_slug": "sonnet-4-6", "skill_name": "dev-execution"},
            tokens={"observedTokens": 145000},
        )
        bits = session_detail_bits(bundle)
        joined = ", ".join(bits)
        self.assertIn("context_window=200k", joined)
        self.assertIn("model=sonnet-4-6", joined)
        self.assertIn("skill=dev-execution", joined)
        self.assertIn("observedTokens=145000", joined)

    def test_empty_bundle_yields_no_bits(self) -> None:
        self.assertEqual(session_detail_bits(_bundle("session-1")), [])


# ── T2-004..T2-007: sharpened-evidence vs P1-fallback fixtures ──────────────


_LINKED = LinkedTaskEvidence(
    acceptance_criteria=("Endpoint returns 200",),
    assigned_to=("ui-engineer-enhanced",),
    assigned_model=("sonnet-4-6",),
    effort=("3 pts",),
    phase=("7",),
    files_affected=("components/Widget.tsx", "backend/bar.py"),
    source_document_ids=("doc-plan-1",),
)


class ContextBallooningEnrichmentTests(unittest.TestCase):
    _ROWS = [{"id": "s1", "context_window_size": 200000, "context_utilization_pct": 90.0}]

    def test_p1_fallback_matches_phase1_exactly(self) -> None:
        flag = evaluate_context_ballooning(self._ROWS, threshold_pct=85.0)
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "high")
        self.assertEqual(flag.evidence_refs, ["s1: 90.0% context utilization"])
        self.assertEqual(flag.rationale, "context utilization reached 90.0% (threshold 85.0%)")

    def test_sharpened_evidence_adds_plan_context_and_session_detail_without_changing_verdict(self) -> None:
        session_metadata = {
            "s1": _bundle(
                "s1",
                session={"context_window": "200k", "model_slug": "sonnet-4-6"},
                tokens={"observedTokens": 190000},
            )
        }
        flag = evaluate_context_ballooning(
            self._ROWS, threshold_pct=85.0, linked_evidence=_LINKED, session_metadata=session_metadata,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "high")
        self.assertEqual(flag.rationale, "context utilization reached 90.0% (threshold 85.0%)")
        self.assertIn("context_window=200k", flag.evidence_refs[0])
        self.assertTrue(any("linked plan context" in ref for ref in flag.evidence_refs))

    def test_no_link_and_no_metadata_falls_back_cleanly(self) -> None:
        flag = evaluate_context_ballooning(self._ROWS, threshold_pct=85.0, linked_evidence=None, session_metadata=None)
        self.assertEqual(flag.evidence_refs, ["s1: 90.0% context utilization"])


class MissingArtifactsEnrichmentTests(unittest.TestCase):
    _CLAIMED = ["backend/foo.py", "backend/bar.py"]
    _PRODUCED = {"session-1": ["backend/foo.py"]}

    def test_p1_fallback_matches_phase1_exactly(self) -> None:
        flag = evaluate_missing_artifacts(self._CLAIMED, self._PRODUCED)
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.evidence_refs, ["backend/bar.py"])

    def test_sharpened_evidence_adds_plan_gap_without_changing_verdict(self) -> None:
        flag = evaluate_missing_artifacts(self._CLAIMED, self._PRODUCED, linked_evidence=_LINKED)
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "medium")
        self.assertIn("backend/bar.py", flag.evidence_refs)
        self.assertTrue(any("plan-declared file" in ref and "components/Widget.tsx" in ref for ref in flag.evidence_refs))

    def test_no_claim_fallback_is_unaffected_by_linked_evidence(self) -> None:
        # Hard AC: linked_evidence must never manufacture a trigger when the
        # AAR doc itself claimed nothing -- this stays the exact P1 branch.
        flag = evaluate_missing_artifacts([], {}, linked_evidence=_LINKED)
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no claimed artifacts to check")

    def test_fully_covered_fallback_is_unaffected_by_linked_evidence(self) -> None:
        flag = evaluate_missing_artifacts(
            ["backend/foo.py"], {"session-1": ["backend/foo.py"]}, linked_evidence=_LINKED,
        )
        self.assertFalse(flag.triggered)


class GenericAgentEnrichmentTests(unittest.TestCase):
    _ROWS = [{"id": "s1", "subagent_type": "general-purpose"}]
    _FILES = {"s1": ["components/Widget.tsx"]}

    def test_p1_fallback_matches_phase1_exactly(self) -> None:
        flag = evaluate_generic_agent_vs_specialist(self._ROWS, self._FILES)
        self.assertTrue(flag.triggered)
        self.assertEqual(
            flag.evidence_refs,
            ["s1: general-purpose used for .tsx work (expected ui-engineer-enhanced)"],
        )

    def test_sharpened_evidence_adds_plan_assignee_mismatch_and_subagents(self) -> None:
        mismatched = LinkedTaskEvidence(assigned_to=("backend-typescript-architect",))
        session_metadata = {"s1": _bundle("s1", subagents=[{"subagent_type": "general-purpose"}])}
        flag = evaluate_generic_agent_vs_specialist(
            self._ROWS, self._FILES, linked_evidence=mismatched, session_metadata=session_metadata,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "medium")
        line = flag.evidence_refs[0]
        self.assertIn("plan declared assignee(s)", line)
        self.assertIn("backend-typescript-architect", line)
        self.assertIn("subagents observed: general-purpose", line)

    def test_matching_plan_assignee_adds_no_mismatch_note(self) -> None:
        matched = LinkedTaskEvidence(assigned_to=("ui-engineer-enhanced",))
        flag = evaluate_generic_agent_vs_specialist(self._ROWS, self._FILES, linked_evidence=matched)
        self.assertTrue(flag.triggered)
        self.assertNotIn("plan declared assignee(s)", flag.evidence_refs[0])

    def test_no_agent_data_fallback_is_unaffected_by_linked_evidence(self) -> None:
        flag = evaluate_generic_agent_vs_specialist([{"id": "s1"}], {}, linked_evidence=_LINKED)
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no agent-usage data")


class StackIneffectivenessEnrichmentTests(unittest.TestCase):
    _SESSION_IDS = ["s1"]
    _FILES = {"s1": ["backend/foo.py"]}
    _FAILURE_ITEMS = [{"title": "Debug loop", "severity": "high", "sessionIds": ["s1"]}]

    def test_p1_fallback_matches_phase1_exactly(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            self._SESSION_IDS, self._FILES, self._FAILURE_ITEMS, feature_scope_available=True,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.evidence_refs, ["s1: python stack, Debug loop (high)"])

    def test_sharpened_evidence_adds_linked_plan_context(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            self._SESSION_IDS, self._FILES, self._FAILURE_ITEMS,
            feature_scope_available=True, linked_evidence=_LINKED,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "high")
        self.assertEqual(flag.evidence_refs[0], "s1: python stack, Debug loop (high)")
        self.assertTrue(any("linked plan context" in ref and "phase=7" in ref for ref in flag.evidence_refs))

    def test_no_feature_scope_fallback_is_unaffected_by_linked_evidence(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            self._SESSION_IDS, self._FILES, [], feature_scope_available=False, linked_evidence=_LINKED,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no feature scope available for failure-pattern lookup")

    def test_no_hit_fallback_is_unaffected_by_linked_evidence(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            self._SESSION_IDS, self._FILES, [], feature_scope_available=True, linked_evidence=_LINKED,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.rationale, "no failure/retry pattern detected for the resolved stack")


# ── End-to-end wiring: get_review() with a linked plan vs no link at all ────
# Exercises the full service method (not just the pure flag functions) to
# prove the T2-002/T2-003 plumbing (doc->feature->plan traversal +
# session_detail enrichment reads) is actually wired into `get_review`, and
# that the two-hop-only `feature_id` used for `detect_failure_patterns`
# scoping is untouched by the independently-resolved `enrichment_feature_id`.


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


def _context() -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id="project-1",
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _ports(*, documents, sessions, links) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(documents_repo=documents, sessions_repo=sessions, links_repo=links),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


def _links_for_factory(*, feature_id: str, doc_plan_id: str | None):
    """entity_links().get_links_for stub covering the document/feature/session hops."""

    async def _links_for(entity_type, entity_id, *_args, **_kwargs):
        if entity_type == "document" and entity_id == "doc-1":
            return [
                {
                    "source_type": "document", "source_id": "doc-1",
                    "target_type": "feature", "target_id": feature_id,
                    "confidence": 0.9,
                    "metadata_json": json.dumps({"linkStrategy": "explicit_frontmatter_ref"}),
                }
            ]
        if entity_type == "feature" and entity_id == feature_id:
            links = [
                {
                    "source_type": "feature", "source_id": feature_id,
                    "target_type": "session", "target_id": "session-2",
                    "confidence": 0.9,
                }
            ]
            if doc_plan_id:
                links.append(
                    {
                        "source_type": "feature", "source_id": feature_id,
                        "target_type": "document", "target_id": doc_plan_id,
                    }
                )
            return links
        return []

    return _links_for


class EndToEndEnrichmentWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_linked_plan_document_sharpens_flag_evidence(self) -> None:
        plan_frontmatter = {
            "phase": 3,
            "tasks": [
                {
                    "id": "T3-001",
                    "assigned_to": ["backend-typescript-architect"],
                    "estimated_effort": "5 pts",
                }
            ],
        }
        documents_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "doc-1", "project_id": "project-1",
                    "frontmatter_json": json.dumps({}),
                }
            ),
            get_many_by_ids=AsyncMock(
                return_value={
                    "doc-plan-1": {"id": "doc-plan-1", "frontmatter_json": json.dumps(plan_frontmatter)}
                }
            ),
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={"id": "session-2", "context_window_size": 200000, "context_utilization_pct": 92.0}
            ),
            get_file_updates=AsyncMock(return_value=[]),
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                side_effect=_links_for_factory(feature_id="feature-1", doc_plan_id="doc-plan-1")
            )
        )
        ports = _ports(documents=documents_repo, sessions=sessions_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.aar_review.detect_failure_patterns",
            new=AsyncMock(return_value={"items": []}),
        ):
            result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.correlation.feature_id, "feature-1")
        ballooning = next(f for f in result.flags if f.flag_id == "context_ballooning")
        self.assertTrue(ballooning.triggered)
        self.assertTrue(any("linked plan context" in ref and "phase=3" in ref for ref in ballooning.evidence_refs))

    async def test_no_linked_plan_document_falls_back_to_phase1_evidence(self) -> None:
        documents_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "doc-1", "project_id": "project-1",
                    "frontmatter_json": json.dumps({}),
                }
            ),
            get_many_by_ids=AsyncMock(return_value={}),
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={"id": "session-2", "context_window_size": 200000, "context_utilization_pct": 92.0}
            ),
            get_file_updates=AsyncMock(return_value=[]),
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(side_effect=_links_for_factory(feature_id="feature-1", doc_plan_id=None))
        )
        ports = _ports(documents=documents_repo, sessions=sessions_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.aar_review.detect_failure_patterns",
            new=AsyncMock(return_value={"items": []}),
        ):
            result = await AARReviewQueryService().get_review(_context(), ports, "doc-1")

        self.assertEqual(result.status, "ok")
        ballooning = next(f for f in result.flags if f.flag_id == "context_ballooning")
        self.assertTrue(ballooning.triggered)
        self.assertEqual(ballooning.evidence_refs, ["session-2: 92.0% context utilization"])
        self.assertFalse(any("linked plan context" in ref for ref in ballooning.evidence_refs))


if __name__ == "__main__":
    unittest.main()
