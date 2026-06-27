"""T2-001 — Branch-aware planning intelligence: DTO contract tests.

Asserts that every new field added by Phase 1 (T1-001 through T1-004) is
present in the relevant Pydantic DTO models that back the planning REST
endpoints:

  - ``PlanningAgentSessionCardDTO.git_branch`` (T1-001)
  - ``PlanningAgentSessionCardDTO.git_commit_hash`` (T1-001)
  - ``PlanningCommandCenterItemDTO.active_sessions`` (T1-002)
  - ``FeatureSummaryItem.commit_refs`` (T1-003)
  - ``FeatureSummaryItem.pr_refs`` (T1-003)
  - ``PhaseContextItem.linked_sessions_by_phase`` (T1-004)
  - ``SessionLink`` nested model (T1-004)
  - ``AggregateWorkItemSession`` nested model (T1-002)

All new fields are additive and optional; this test also asserts:
  - Existing fields on each model are unchanged (old-shape consumer contract)
  - New fields default to None / empty-list (no missing-field error on
    pre-existing records that lack these keys)
  - Serialised dump contains all expected keys (wire shape check)

Test style mirrors test_multi_project_planning_contract.py:
  - IsolatedAsyncioTestCase (no pytest-asyncio)
  - Pydantic v2 model introspection via ``.model_fields`` and ``.model_dump()``
  - No DB, no filesystem, no network
"""
from __future__ import annotations

import unittest


# ---------------------------------------------------------------------------
# Expected new field inventories (T1-001 through T1-004)
# ---------------------------------------------------------------------------

# Fields added to PlanningAgentSessionCardDTO (T1-001)
NEW_SESSION_CARD_FIELDS: frozenset[str] = frozenset(
    {
        "git_branch",
        "git_commit_hash",
    }
)

# Existing core fields on PlanningAgentSessionCardDTO that must remain intact
EXISTING_SESSION_CARD_FIELDS: frozenset[str] = frozenset(
    {
        "session_id",
        "agent_name",
        "agent_type",
        "state",
        "model",
        "transcript_href",
        "started_at",
        "last_activity_at",
        "duration_seconds",
    }
)

# Fields added to PlanningCommandCenterItemDTO (T1-002)
NEW_COMMAND_CENTER_ITEM_FIELDS: frozenset[str] = frozenset(
    {
        "active_sessions",
    }
)

# Existing core fields on PlanningCommandCenterItemDTO that must remain intact
EXISTING_COMMAND_CENTER_ITEM_FIELDS: frozenset[str] = frozenset(
    {
        "feature",
        "status",
        "tier",
        "story_points",
        "phase",
        "artifacts",
        "worktree",
        "blockers",
    }
)

# Fields added to FeatureSummaryItem (T1-003)
NEW_FEATURE_SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "commit_refs",
        "pr_refs",
    }
)

# Existing core fields on FeatureSummaryItem that must remain intact
EXISTING_FEATURE_SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "feature_id",
        "feature_name",
        "raw_status",
        "effective_status",
        "is_mismatch",
        "phase_count",
    }
)

# Fields added to PhaseContextItem (T1-004)
NEW_PHASE_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        "linked_sessions_by_phase",
    }
)

# Existing core fields on PhaseContextItem that must remain intact
EXISTING_PHASE_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        "phase_id",
        "phase_token",
        "phase_title",
        "raw_status",
        "effective_status",
        "total_tasks",
        "completed_tasks",
    }
)

# Fields on SessionLink (T1-004 nested model)
SESSION_LINK_FIELDS: frozenset[str] = frozenset(
    {
        "session_id",
        "agent_name",
        "start_time",
        "transcript_href",
    }
)

# Fields on AggregateWorkItemSession (T1-002 nested model)
AGGREGATE_WORK_ITEM_SESSION_FIELDS: frozenset[str] = frozenset(
    {
        "session_id",
        "state",
        "model",
        "started_at",
        "agent_name",
    }
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _model_field_names(model_cls) -> frozenset[str]:
    """Return snake_case field names declared on a Pydantic v2 model."""
    names: set[str] = set()
    for field_name, field_info in model_cls.model_fields.items():
        names.add(field_name)
        alias = getattr(field_info, "alias", None)
        if alias:
            names.add(str(alias))
        s_alias = getattr(field_info, "serialization_alias", None)
        if s_alias:
            names.add(str(s_alias))
    return frozenset(names)


def _assert_fields_present(
    test: unittest.TestCase,
    expected_fields: frozenset[str],
    model_cls,
    *,
    label: str,
) -> None:
    model_fields = _model_field_names(model_cls)
    missing = expected_fields - model_fields
    test.assertFalse(
        missing,
        f"Expected field(s) {sorted(missing)} absent from {label} ({model_cls.__name__}).\n"
        f"Declared fields: {sorted(model_fields)}",
    )


# ---------------------------------------------------------------------------
# T2-001-A  PlanningAgentSessionCardDTO — git_branch / git_commit_hash
# ---------------------------------------------------------------------------


class TestSessionCardBranchFields(unittest.IsolatedAsyncioTestCase):
    """T2-001-A: New branch fields present on PlanningAgentSessionCardDTO."""

    async def test_new_branch_fields_present(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        _assert_fields_present(
            self,
            NEW_SESSION_CARD_FIELDS,
            PlanningAgentSessionCardDTO,
            label="PlanningAgentSessionCardDTO (branch fields)",
        )

    async def test_existing_fields_unchanged(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        _assert_fields_present(
            self,
            EXISTING_SESSION_CARD_FIELDS,
            PlanningAgentSessionCardDTO,
            label="PlanningAgentSessionCardDTO (existing fields)",
        )

    async def test_new_fields_default_to_none(self) -> None:
        """git_branch and git_commit_hash default to None — no ValidationError."""
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        card = PlanningAgentSessionCardDTO(session_id="s-001")
        self.assertIsNone(card.git_branch)
        self.assertIsNone(card.git_commit_hash)

    async def test_new_fields_in_model_dump(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        dump = PlanningAgentSessionCardDTO(session_id="s-001").model_dump()
        for field in NEW_SESSION_CARD_FIELDS:
            self.assertIn(field, dump, f"Field '{field}' absent from model_dump()")

    async def test_git_branch_populated_when_set(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        card = PlanningAgentSessionCardDTO(
            session_id="s-002",
            git_branch="feat/branch-aware",
            git_commit_hash="abc1234",
        )
        self.assertEqual(card.git_branch, "feat/branch-aware")
        self.assertEqual(card.git_commit_hash, "abc1234")

    async def test_model_dump_contains_null_for_absent_branch(self) -> None:
        """Wire shape: absent branch fields appear as null (not omitted)."""
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        dump = PlanningAgentSessionCardDTO(session_id="s-003").model_dump()
        self.assertIsNone(dump["git_branch"])
        self.assertIsNone(dump["git_commit_hash"])


# ---------------------------------------------------------------------------
# T2-001-B  AggregateWorkItemSession nested model
# ---------------------------------------------------------------------------


class TestAggregateWorkItemSessionModel(unittest.IsolatedAsyncioTestCase):
    """T2-001-B: AggregateWorkItemSession model fields (T1-002 nested DTO)."""

    async def test_all_fields_present(self) -> None:
        from backend.application.services.agent_queries.models import (
            AggregateWorkItemSession,
        )

        _assert_fields_present(
            self,
            AGGREGATE_WORK_ITEM_SESSION_FIELDS,
            AggregateWorkItemSession,
            label="AggregateWorkItemSession",
        )

    async def test_instantiates_with_session_id_only(self) -> None:
        from backend.application.services.agent_queries.models import (
            AggregateWorkItemSession,
        )

        s = AggregateWorkItemSession(session_id="sess-001")
        self.assertEqual(s.session_id, "sess-001")
        self.assertEqual(s.state, "running")
        self.assertIsNone(s.model)
        self.assertIsNone(s.agent_name)
        self.assertIsNone(s.started_at)

    async def test_model_dump_contains_all_fields(self) -> None:
        from backend.application.services.agent_queries.models import (
            AggregateWorkItemSession,
        )

        dump = AggregateWorkItemSession(session_id="sess-002").model_dump()
        for field in AGGREGATE_WORK_ITEM_SESSION_FIELDS:
            self.assertIn(field, dump, f"Field '{field}' absent from model_dump()")


# ---------------------------------------------------------------------------
# T2-001-C  PlanningCommandCenterItemDTO — active_sessions
# ---------------------------------------------------------------------------


class TestCommandCenterItemActiveSessions(unittest.IsolatedAsyncioTestCase):
    """T2-001-C: active_sessions field present on PlanningCommandCenterItemDTO."""

    async def test_new_active_sessions_field_present(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterItemDTO,
        )

        _assert_fields_present(
            self,
            NEW_COMMAND_CENTER_ITEM_FIELDS,
            PlanningCommandCenterItemDTO,
            label="PlanningCommandCenterItemDTO (active_sessions)",
        )

    async def test_existing_fields_unchanged(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterItemDTO,
        )

        _assert_fields_present(
            self,
            EXISTING_COMMAND_CENTER_ITEM_FIELDS,
            PlanningCommandCenterItemDTO,
            label="PlanningCommandCenterItemDTO (existing fields)",
        )

    async def test_active_sessions_defaults_to_empty_list(self) -> None:
        """active_sessions must default to [] (not None) when no sessions are running."""
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterFeatureDTO,
            PlanningCommandCenterItemDTO,
        )

        item = PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(feature_id="f-001")
        )
        self.assertEqual(item.active_sessions, [])

    async def test_active_sessions_in_model_dump(self) -> None:
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterFeatureDTO,
            PlanningCommandCenterItemDTO,
        )

        dump = PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(feature_id="f-002")
        ).model_dump()
        self.assertIn("active_sessions", dump)
        self.assertEqual(dump["active_sessions"], [])

    async def test_active_sessions_populated(self) -> None:
        from backend.application.services.agent_queries.models import (
            AggregateWorkItemSession,
            PlanningCommandCenterFeatureDTO,
            PlanningCommandCenterItemDTO,
        )

        session = AggregateWorkItemSession(
            session_id="s-running",
            state="running",
            agent_name="python-backend-engineer",
        )
        item = PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(feature_id="f-003"),
            active_sessions=[session],
        )
        self.assertEqual(len(item.active_sessions), 1)
        self.assertEqual(item.active_sessions[0].session_id, "s-running")
        self.assertEqual(item.active_sessions[0].state, "running")


# ---------------------------------------------------------------------------
# T2-001-D  FeatureSummaryItem — commit_refs / pr_refs
# ---------------------------------------------------------------------------


class TestFeatureSummaryCommitPrRefs(unittest.IsolatedAsyncioTestCase):
    """T2-001-D: commit_refs and pr_refs fields present on FeatureSummaryItem."""

    async def test_new_ref_fields_present(self) -> None:
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        _assert_fields_present(
            self,
            NEW_FEATURE_SUMMARY_FIELDS,
            FeatureSummaryItem,
            label="FeatureSummaryItem (commit/pr refs)",
        )

    async def test_existing_fields_unchanged(self) -> None:
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        _assert_fields_present(
            self,
            EXISTING_FEATURE_SUMMARY_FIELDS,
            FeatureSummaryItem,
            label="FeatureSummaryItem (existing fields)",
        )

    async def test_ref_fields_default_to_empty_list(self) -> None:
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        item = FeatureSummaryItem(feature_id="f-001")
        self.assertEqual(item.commit_refs, [])
        self.assertEqual(item.pr_refs, [])

    async def test_ref_fields_in_model_dump(self) -> None:
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        dump = FeatureSummaryItem(feature_id="f-002").model_dump()
        self.assertIn("commit_refs", dump)
        self.assertIn("pr_refs", dump)
        self.assertEqual(dump["commit_refs"], [])
        self.assertEqual(dump["pr_refs"], [])

    async def test_ref_fields_populated(self) -> None:
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        item = FeatureSummaryItem(
            feature_id="f-003",
            commit_refs=["abc123", "def456"],
            pr_refs=["#42", "#43"],
        )
        self.assertEqual(item.commit_refs, ["abc123", "def456"])
        self.assertEqual(item.pr_refs, ["#42", "#43"])


# ---------------------------------------------------------------------------
# T2-001-E  SessionLink nested model (T1-004)
# ---------------------------------------------------------------------------


class TestSessionLinkModel(unittest.IsolatedAsyncioTestCase):
    """T2-001-E: SessionLink model fields (T1-004 nested DTO)."""

    async def test_all_fields_present(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink

        _assert_fields_present(
            self,
            SESSION_LINK_FIELDS,
            SessionLink,
            label="SessionLink",
        )

    async def test_instantiates_with_session_id_only(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink

        link = SessionLink(session_id="s-link-001")
        self.assertEqual(link.session_id, "s-link-001")
        self.assertIsNone(link.agent_name)
        self.assertIsNone(link.start_time)
        self.assertIsNone(link.transcript_href)

    async def test_model_dump_contains_all_fields(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink

        dump = SessionLink(session_id="s-link-002").model_dump()
        for field in SESSION_LINK_FIELDS:
            self.assertIn(field, dump, f"Field '{field}' absent from SessionLink.model_dump()")

    async def test_all_fields_populated(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink

        link = SessionLink(
            session_id="s-link-003",
            agent_name="python-backend-engineer",
            start_time="2026-06-04T10:00:00Z",
            transcript_href="#/sessions/s-link-003",
        )
        self.assertEqual(link.session_id, "s-link-003")
        self.assertEqual(link.agent_name, "python-backend-engineer")
        self.assertEqual(link.start_time, "2026-06-04T10:00:00Z")
        self.assertEqual(link.transcript_href, "#/sessions/s-link-003")


# ---------------------------------------------------------------------------
# T2-001-F  PhaseContextItem — linked_sessions_by_phase
# ---------------------------------------------------------------------------


class TestPhaseContextLinkedSessions(unittest.IsolatedAsyncioTestCase):
    """T2-001-F: linked_sessions_by_phase field present on PhaseContextItem."""

    async def test_new_linked_sessions_field_present(self) -> None:
        from backend.application.services.agent_queries.models import PhaseContextItem

        _assert_fields_present(
            self,
            NEW_PHASE_CONTEXT_FIELDS,
            PhaseContextItem,
            label="PhaseContextItem (linked_sessions_by_phase)",
        )

    async def test_existing_fields_unchanged(self) -> None:
        from backend.application.services.agent_queries.models import PhaseContextItem

        _assert_fields_present(
            self,
            EXISTING_PHASE_CONTEXT_FIELDS,
            PhaseContextItem,
            label="PhaseContextItem (existing fields)",
        )

    async def test_linked_sessions_defaults_to_none(self) -> None:
        """linked_sessions_by_phase defaults to None (not an empty dict)."""
        from backend.application.services.agent_queries.models import PhaseContextItem

        item = PhaseContextItem()
        self.assertIsNone(item.linked_sessions_by_phase)

    async def test_linked_sessions_in_model_dump(self) -> None:
        from backend.application.services.agent_queries.models import PhaseContextItem

        dump = PhaseContextItem().model_dump()
        self.assertIn("linked_sessions_by_phase", dump)
        self.assertIsNone(dump["linked_sessions_by_phase"])

    async def test_linked_sessions_populated(self) -> None:
        from backend.application.services.agent_queries.models import (
            PhaseContextItem,
            SessionLink,
        )

        link = SessionLink(
            session_id="s-phase-001",
            agent_name="python-backend-engineer",
            start_time="2026-06-04T10:00:00Z",
            transcript_href="#/sessions/s-phase-001",
        )
        item = PhaseContextItem(linked_sessions_by_phase={1: [link]})
        self.assertIsNotNone(item.linked_sessions_by_phase)
        self.assertIn(1, item.linked_sessions_by_phase)
        self.assertEqual(len(item.linked_sessions_by_phase[1]), 1)
        self.assertEqual(item.linked_sessions_by_phase[1][0].session_id, "s-phase-001")


# ---------------------------------------------------------------------------
# T2-001-G  OpenAPI schema smoke: endpoint response models include new fields
#
# This validates that the FastAPI OpenAPI schema (generated from the Pydantic
# response_model= annotations on the router endpoints) exposes the new fields.
# We check the JSON schema for the relevant response model refs.
# ---------------------------------------------------------------------------


class TestOpenApiSchemaReflectsNewFields(unittest.TestCase):
    """T2-001-G: OpenAPI schema emitted by FastAPI includes new optional fields."""

    def _get_openapi_schema(self):
        from backend.runtime.bootstrap import build_runtime_app

        app = build_runtime_app("test")
        return app.openapi()

    def test_session_board_endpoint_registered(self) -> None:
        schema = self._get_openapi_schema()
        paths = schema["paths"]
        self.assertIn("/api/agent/planning/session-board", paths)
        self.assertIn("get", paths["/api/agent/planning/session-board"])

    def test_command_center_endpoint_registered(self) -> None:
        schema = self._get_openapi_schema()
        paths = schema["paths"]
        self.assertIn("/api/agent/planning/command-center", paths)
        self.assertIn("get", paths["/api/agent/planning/command-center"])

    def test_planning_summary_endpoint_registered(self) -> None:
        """planning/summary exposes FeatureSummaryItem (commit_refs, pr_refs)."""
        schema = self._get_openapi_schema()
        paths = schema["paths"]
        self.assertIn("/api/agent/planning/summary", paths)

    def test_planning_feature_context_endpoint_registered(self) -> None:
        """planning/features/{id} exposes PhaseContextItem (linked_sessions_by_phase)."""
        schema = self._get_openapi_schema()
        paths = schema["paths"]
        self.assertIn("/api/agent/planning/features/{feature_id}", paths)

    def test_new_fields_present_in_planning_agent_session_card_schema(self) -> None:
        """PlanningAgentSessionCardDTO schema must include git_branch and git_commit_hash."""
        schema = self._get_openapi_schema()
        components = schema.get("components", {}).get("schemas", {})
        card_schema = components.get("PlanningAgentSessionCardDTO")
        self.assertIsNotNone(
            card_schema,
            "PlanningAgentSessionCardDTO not in OpenAPI components/schemas",
        )
        card_props = card_schema.get("properties", {})
        self.assertIn("git_branch", card_props, "git_branch absent from PlanningAgentSessionCardDTO schema")
        self.assertIn("git_commit_hash", card_props, "git_commit_hash absent from PlanningAgentSessionCardDTO schema")

    def test_active_sessions_present_in_command_center_item_schema(self) -> None:
        """PlanningCommandCenterItemDTO schema must include active_sessions."""
        schema = self._get_openapi_schema()
        components = schema.get("components", {}).get("schemas", {})
        item_schema = components.get("PlanningCommandCenterItemDTO")
        self.assertIsNotNone(
            item_schema,
            "PlanningCommandCenterItemDTO not in OpenAPI components/schemas",
        )
        item_props = item_schema.get("properties", {})
        self.assertIn("active_sessions", item_props, "active_sessions absent from PlanningCommandCenterItemDTO schema")

    def test_commit_pr_refs_present_in_feature_summary_schema(self) -> None:
        """FeatureSummaryItem schema must include commit_refs and pr_refs."""
        schema = self._get_openapi_schema()
        components = schema.get("components", {}).get("schemas", {})
        summary_schema = components.get("FeatureSummaryItem")
        self.assertIsNotNone(
            summary_schema,
            "FeatureSummaryItem not in OpenAPI components/schemas",
        )
        props = summary_schema.get("properties", {})
        self.assertIn("commit_refs", props, "commit_refs absent from FeatureSummaryItem schema")
        self.assertIn("pr_refs", props, "pr_refs absent from FeatureSummaryItem schema")

    def test_linked_sessions_by_phase_present_in_phase_context_schema(self) -> None:
        """PhaseContextItem schema must include linked_sessions_by_phase."""
        schema = self._get_openapi_schema()
        components = schema.get("components", {}).get("schemas", {})
        phase_schema = components.get("PhaseContextItem")
        self.assertIsNotNone(
            phase_schema,
            "PhaseContextItem not in OpenAPI components/schemas",
        )
        props = phase_schema.get("properties", {})
        self.assertIn(
            "linked_sessions_by_phase",
            props,
            "linked_sessions_by_phase absent from PhaseContextItem schema",
        )


# ---------------------------------------------------------------------------
# T2-001-H  Additive-only regression: old-shape consumers unaffected
#
# Proves that existing required fields are still present and old-contract
# instantiation patterns work without keyword arguments for the new fields.
# ---------------------------------------------------------------------------


class TestOldShapeConsumersUnaffected(unittest.IsolatedAsyncioTestCase):
    """T2-001-H: Old-shape instantiation (without new fields) must not fail."""

    async def test_session_card_old_shape(self) -> None:
        """session cards created without git_branch still work fine."""
        from backend.application.services.agent_queries.models import (
            PlanningAgentSessionCardDTO,
        )

        card = PlanningAgentSessionCardDTO(session_id="legacy-s-001", state="running")
        self.assertEqual(card.session_id, "legacy-s-001")
        self.assertIsNone(card.git_branch)
        self.assertIsNone(card.git_commit_hash)

    async def test_command_center_item_old_shape(self) -> None:
        """command-center items created without active_sessions still work fine."""
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterFeatureDTO,
            PlanningCommandCenterItemDTO,
        )

        item = PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(feature_id="legacy-f-001")
        )
        self.assertEqual(item.feature.feature_id, "legacy-f-001")
        self.assertEqual(item.active_sessions, [])

    async def test_feature_summary_item_old_shape(self) -> None:
        """FeatureSummaryItem created without commit_refs/pr_refs still works."""
        from backend.application.services.agent_queries.models import FeatureSummaryItem

        item = FeatureSummaryItem(
            feature_id="legacy-f-002",
            feature_name="Legacy Feature",
            raw_status="active",
            effective_status="active",
        )
        self.assertEqual(item.feature_id, "legacy-f-002")
        self.assertEqual(item.commit_refs, [])
        self.assertEqual(item.pr_refs, [])

    async def test_phase_context_item_old_shape(self) -> None:
        """PhaseContextItem created without linked_sessions_by_phase still works."""
        from backend.application.services.agent_queries.models import PhaseContextItem

        item = PhaseContextItem(
            phase_id="p1",
            phase_token="P1",
            phase_title="Phase 1",
            raw_status="completed",
            effective_status="completed",
        )
        self.assertEqual(item.phase_id, "p1")
        self.assertIsNone(item.linked_sessions_by_phase)


if __name__ == "__main__":
    unittest.main()
