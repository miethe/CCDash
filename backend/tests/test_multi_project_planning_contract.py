"""MPCC-603 — FE/BE contract tests: DTO drift guard.

Asserts that every snake_case field the FRONTEND adapter reads from the wire
response exists in the corresponding Pydantic response model.

Source of truth:
  - Frontend adapter: ``services/multiProjectPlanningCommandCenter.ts``
    (explicit snake_case field reads documented in WireShape interfaces +
    adapter function bodies)
  - Backend models: ``backend/models.py``
    (``MultiProjectCommandCenterResponse``, ``MultiProjectSessionBoardResponse``,
    and nested models)

These tests will FAIL if any model drops a field the adapter expects, preventing
silent DTO drift.

Test style mirrors test_multi_project_planning_command_center.py:
  - IsolatedAsyncioTestCase (no pytest-asyncio → avoids collection hang)
  - Model introspection via ``.model_fields`` (Pydantic v2)
  - Serialised example via ``.model_json_schema()`` / ``.model_dump()``
  - No DB, no filesystem, no network
"""
from __future__ import annotations

import unittest


# ---------------------------------------------------------------------------
# Field inventories extracted from the frontend adapter
# (services/multiProjectPlanningCommandCenter.ts)
#
# Each constant lists the exact snake_case keys the adapter reads from the wire
# shape.  Add new keys here whenever the adapter is extended — the test will
# catch the backend side dropping them.
# ---------------------------------------------------------------------------

# WireDisplayMetadata fields  (adaptDisplayMetadata)
FE_DISPLAY_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "color",
        "group",
        "sort_order",
        "label_override",
    }
)

# WireWorkItemCounts fields  (adaptWorkItemCounts)
FE_WORK_ITEM_COUNTS_FIELDS: frozenset[str] = frozenset(
    {
        "work_items",
        "blocked",
        "review",
        "stale",
        "active_sessions",
        "errors",
    }
)

# WireProjectSummary fields  (adaptProjectSummary)
FE_PROJECT_SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "project_id",
        "name",
        "display_metadata",
        "counts",
        "is_stale",
        "error",
        "last_updated",
        "freshness_seconds",
    }
)

# WireProjectIdentity fields  (adaptProjectIdentity)
FE_PROJECT_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "project_id",
        "project_name",
        "project_color",
        "project_group",
    }
)

# WireProjectWarning fields  (adaptProjectWarning)
FE_PROJECT_WARNING_FIELDS: frozenset[str] = frozenset(
    {
        "project_id",
        "message",
        "severity",
        "code",
    }
)

# WireAggregatePagination fields  (adaptPagination)
FE_PAGINATION_FIELDS: frozenset[str] = frozenset(
    {
        "page",
        "page_size",
        "total",
        "has_more",
    }
)

# WireWorkerSummary fields  (adaptWorkerSummary)
FE_WORKER_SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "session_id",
        "agent_name",
        "state",
        "model",
        "started_at",
        "last_activity_at",
        "duration_seconds",
    }
)

# Top-level MultiProjectCommandCenterResponse wire fields  (adaptMultiProjectCommandCenterResponse)
FE_COMMAND_CENTER_RESPONSE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "items",
        "project_summaries",
        "pagination",
        "warnings",
        "generated_at",
        "data_freshness",
    }
)

# Top-level MultiProjectSessionBoardResponse wire fields  (adaptMultiProjectSessionBoardResponse)
FE_SESSION_BOARD_RESPONSE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "grouping",
        "groups",
        "project_summaries",
        "pagination",
        "warnings",
        "total_card_count",
        "active_count",
        "completed_count",
        "generated_at",
        "data_freshness",
    }
)

# AggregateBoardGroup wire fields  (adaptBoardGroup)
FE_BOARD_GROUP_FIELDS: frozenset[str] = frozenset(
    {
        "group_key",
        "group_label",
        "group_type",
        "cards",
        "card_count",
    }
)

# AggregateWorkItem wire fields  (adaptAggregateWorkItem)
FE_AGGREGATE_WORK_ITEM_FIELDS: frozenset[str] = frozenset(
    {
        "project",
        "item",
    }
)

# AggregateSessionCard wire fields  (adaptAggregateSessionCard)
FE_AGGREGATE_SESSION_CARD_FIELDS: frozenset[str] = frozenset(
    {
        "project",
        "card",
        "workers",
    }
)


# ---------------------------------------------------------------------------
# Helper: extract all field names (including aliases) from a Pydantic model
# ---------------------------------------------------------------------------


def _model_field_names(model_cls) -> frozenset[str]:
    """Return the snake_case field names declared on a Pydantic v2 model.

    We use ``model_fields`` which maps field names (Python identifiers) to
    ``FieldInfo`` objects.  For models that declare ``alias`` or use
    ``model_config = ConfigDict(populate_by_name=True)`` we also collect
    aliases so the comparison is against wire-level names.

    In CCDash models.py all fields already use snake_case (no aliasing), so
    ``field_name`` is the wire name.
    """
    names: set[str] = set()
    for field_name, field_info in model_cls.model_fields.items():
        names.add(field_name)
        # If there's an alias, include it too (handles models that alias to camelCase)
        alias = getattr(field_info, "alias", None)
        if alias:
            names.add(str(alias))
        # serialization_alias (Pydantic v2)
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
    """Assert every field in expected_fields exists in model_cls.model_fields."""
    model_fields = _model_field_names(model_cls)
    missing = expected_fields - model_fields
    test.assertFalse(
        missing,
        f"FE adapter reads field(s) {sorted(missing)} from {label} wire shape "
        f"but {model_cls.__name__} does not declare them.\n"
        f"Declared fields: {sorted(model_fields)}",
    )


# ---------------------------------------------------------------------------
# CC-1  MultiProjectCommandCenterResponse top-level fields
# ---------------------------------------------------------------------------


class TestCommandCenterResponseContract(unittest.IsolatedAsyncioTestCase):
    """CC-1: Top-level command-center response fields present in the Pydantic model."""

    async def test_top_level_fields_present(self) -> None:
        from backend.models import MultiProjectCommandCenterResponse

        _assert_fields_present(
            self,
            FE_COMMAND_CENTER_RESPONSE_FIELDS,
            MultiProjectCommandCenterResponse,
            label="MultiProjectCommandCenterResponse",
        )

    async def test_model_instantiates_with_required_fields(self) -> None:
        """Model must instantiate without error and serialise all FE-required fields."""
        from backend.models import MultiProjectCommandCenterResponse

        instance = MultiProjectCommandCenterResponse()
        dump = instance.model_dump()
        for field in FE_COMMAND_CENTER_RESPONSE_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from MultiProjectCommandCenterResponse.model_dump()",
            )

    async def test_generated_at_field_serialises_correctly(self) -> None:
        """generated_at must appear in the dump even when None."""
        from backend.models import MultiProjectCommandCenterResponse

        r = MultiProjectCommandCenterResponse()
        dump = r.model_dump()
        # generated_at is Optional — its key must still be present (not omitted)
        self.assertIn("generated_at", dump)

    async def test_data_freshness_field_present(self) -> None:
        """data_freshness is an Optional str field the adapter reads."""
        from backend.models import MultiProjectCommandCenterResponse

        r = MultiProjectCommandCenterResponse()
        dump = r.model_dump()
        self.assertIn("data_freshness", dump)


# ---------------------------------------------------------------------------
# CC-2  MultiProjectSessionBoardResponse top-level fields
# ---------------------------------------------------------------------------


class TestSessionBoardResponseContract(unittest.IsolatedAsyncioTestCase):
    """CC-2: Top-level session-board response fields present in the Pydantic model."""

    async def test_top_level_fields_present(self) -> None:
        from backend.models import MultiProjectSessionBoardResponse

        _assert_fields_present(
            self,
            FE_SESSION_BOARD_RESPONSE_FIELDS,
            MultiProjectSessionBoardResponse,
            label="MultiProjectSessionBoardResponse",
        )

    async def test_model_instantiates_with_required_fields(self) -> None:
        from backend.models import MultiProjectSessionBoardResponse

        instance = MultiProjectSessionBoardResponse()
        dump = instance.model_dump()
        for field in FE_SESSION_BOARD_RESPONSE_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from MultiProjectSessionBoardResponse.model_dump()",
            )

    async def test_total_card_count_active_count_completed_count_present(self) -> None:
        """Numeric convenience tallies must be present for the header strip."""
        from backend.models import MultiProjectSessionBoardResponse

        dump = MultiProjectSessionBoardResponse().model_dump()
        for field in ("total_card_count", "active_count", "completed_count"):
            self.assertIn(field, dump, f"Field '{field}' missing from session-board response")


# ---------------------------------------------------------------------------
# CC-3  ProjectSummary fields
# ---------------------------------------------------------------------------


class TestProjectSummaryContract(unittest.IsolatedAsyncioTestCase):
    """CC-3: ProjectSummary fields match what the adapter reads."""

    async def test_project_summary_fields_present(self) -> None:
        from backend.models import ProjectSummary

        _assert_fields_present(
            self,
            FE_PROJECT_SUMMARY_FIELDS,
            ProjectSummary,
            label="ProjectSummary",
        )

    async def test_project_summary_dump_contains_all_fe_fields(self) -> None:
        from backend.models import ProjectSummary

        dump = ProjectSummary(project_id="p", name="N").model_dump()
        for field in FE_PROJECT_SUMMARY_FIELDS:
            self.assertIn(field, dump, f"Field '{field}' absent from ProjectSummary.model_dump()")


# ---------------------------------------------------------------------------
# CC-4  ProjectDisplayMetadata fields
# ---------------------------------------------------------------------------


class TestProjectDisplayMetadataContract(unittest.IsolatedAsyncioTestCase):
    """CC-4: ProjectDisplayMetadata fields match what the adapter reads."""

    async def test_display_metadata_fields_present(self) -> None:
        from backend.models import ProjectDisplayMetadata

        _assert_fields_present(
            self,
            FE_DISPLAY_METADATA_FIELDS,
            ProjectDisplayMetadata,
            label="ProjectDisplayMetadata",
        )

    async def test_display_metadata_dump_contains_all_fe_fields(self) -> None:
        from backend.models import ProjectDisplayMetadata

        dump = ProjectDisplayMetadata().model_dump()
        for field in FE_DISPLAY_METADATA_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from ProjectDisplayMetadata.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-5  ProjectWorkItemCounts fields
# ---------------------------------------------------------------------------


class TestProjectWorkItemCountsContract(unittest.IsolatedAsyncioTestCase):
    """CC-5: ProjectWorkItemCounts fields match what the adapter reads."""

    async def test_work_item_counts_fields_present(self) -> None:
        from backend.models import ProjectWorkItemCounts

        _assert_fields_present(
            self,
            FE_WORK_ITEM_COUNTS_FIELDS,
            ProjectWorkItemCounts,
            label="ProjectWorkItemCounts",
        )

    async def test_work_item_counts_dump_contains_all_fe_fields(self) -> None:
        from backend.models import ProjectWorkItemCounts

        dump = ProjectWorkItemCounts().model_dump()
        for field in FE_WORK_ITEM_COUNTS_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from ProjectWorkItemCounts.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-6  ProjectIdentityFields fields
# ---------------------------------------------------------------------------


class TestProjectIdentityFieldsContract(unittest.IsolatedAsyncioTestCase):
    """CC-6: ProjectIdentityFields fields match what the adapter reads."""

    async def test_project_identity_fields_present(self) -> None:
        from backend.models import ProjectIdentityFields

        _assert_fields_present(
            self,
            FE_PROJECT_IDENTITY_FIELDS,
            ProjectIdentityFields,
            label="ProjectIdentityFields",
        )

    async def test_project_identity_dump_contains_all_fe_fields(self) -> None:
        from backend.models import ProjectIdentityFields

        dump = ProjectIdentityFields(project_id="p").model_dump()
        for field in FE_PROJECT_IDENTITY_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from ProjectIdentityFields.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-7  ProjectWarning fields
# ---------------------------------------------------------------------------


class TestProjectWarningContract(unittest.IsolatedAsyncioTestCase):
    """CC-7: ProjectWarning fields match what the adapter reads."""

    async def test_project_warning_fields_present(self) -> None:
        from backend.models import ProjectWarning

        _assert_fields_present(
            self,
            FE_PROJECT_WARNING_FIELDS,
            ProjectWarning,
            label="ProjectWarning",
        )

    async def test_project_warning_dump_contains_all_fe_fields(self) -> None:
        from backend.models import ProjectWarning

        dump = ProjectWarning(project_id="p", message="m").model_dump()
        for field in FE_PROJECT_WARNING_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from ProjectWarning.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-8  AggregatePagination fields
# ---------------------------------------------------------------------------


class TestAggregatePaginationContract(unittest.IsolatedAsyncioTestCase):
    """CC-8: AggregatePagination fields match what the adapter reads."""

    async def test_pagination_fields_present(self) -> None:
        from backend.models import AggregatePagination

        _assert_fields_present(
            self,
            FE_PAGINATION_FIELDS,
            AggregatePagination,
            label="AggregatePagination",
        )

    async def test_pagination_dump_contains_all_fe_fields(self) -> None:
        from backend.models import AggregatePagination

        dump = AggregatePagination().model_dump()
        for field in FE_PAGINATION_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from AggregatePagination.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-9  AggregateSessionWorkerSummary fields
# ---------------------------------------------------------------------------


class TestAggregateSessionWorkerSummaryContract(unittest.IsolatedAsyncioTestCase):
    """CC-9: AggregateSessionWorkerSummary fields match what the adapter reads."""

    async def test_worker_summary_fields_present(self) -> None:
        from backend.models import AggregateSessionWorkerSummary

        _assert_fields_present(
            self,
            FE_WORKER_SUMMARY_FIELDS,
            AggregateSessionWorkerSummary,
            label="AggregateSessionWorkerSummary",
        )

    async def test_worker_summary_dump_contains_all_fe_fields(self) -> None:
        from backend.models import AggregateSessionWorkerSummary

        dump = AggregateSessionWorkerSummary(session_id="s").model_dump()
        for field in FE_WORKER_SUMMARY_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from AggregateSessionWorkerSummary.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-10  AggregateBoardGroup fields
# ---------------------------------------------------------------------------


class TestAggregateBoardGroupContract(unittest.IsolatedAsyncioTestCase):
    """CC-10: AggregateBoardGroup fields match what the adapter reads."""

    async def test_board_group_fields_present(self) -> None:
        from backend.models import AggregateBoardGroup

        _assert_fields_present(
            self,
            FE_BOARD_GROUP_FIELDS,
            AggregateBoardGroup,
            label="AggregateBoardGroup",
        )

    async def test_board_group_dump_contains_all_fe_fields(self) -> None:
        from backend.models import AggregateBoardGroup

        dump = AggregateBoardGroup(group_key="state", group_label="Running").model_dump()
        for field in FE_BOARD_GROUP_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from AggregateBoardGroup.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-11  AggregateWorkItem fields
# ---------------------------------------------------------------------------


class TestAggregateWorkItemContract(unittest.IsolatedAsyncioTestCase):
    """CC-11: AggregateWorkItem top-level fields match what the adapter reads."""

    async def test_aggregate_work_item_fields_present(self) -> None:
        from backend.models import AggregateWorkItem

        _assert_fields_present(
            self,
            FE_AGGREGATE_WORK_ITEM_FIELDS,
            AggregateWorkItem,
            label="AggregateWorkItem",
        )

    async def test_aggregate_work_item_dump_contains_all_fe_fields(self) -> None:
        from backend.models import AggregateWorkItem, ProjectIdentityFields

        dump = AggregateWorkItem(
            project=ProjectIdentityFields(project_id="p"),
            item={},
        ).model_dump()
        for field in FE_AGGREGATE_WORK_ITEM_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from AggregateWorkItem.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-12  AggregateSessionCard fields
# ---------------------------------------------------------------------------


class TestAggregateSessionCardContract(unittest.IsolatedAsyncioTestCase):
    """CC-12: AggregateSessionCard top-level fields match what the adapter reads."""

    async def test_aggregate_session_card_fields_present(self) -> None:
        from backend.models import AggregateSessionCard

        _assert_fields_present(
            self,
            FE_AGGREGATE_SESSION_CARD_FIELDS,
            AggregateSessionCard,
            label="AggregateSessionCard",
        )

    async def test_aggregate_session_card_dump_contains_all_fe_fields(self) -> None:
        from backend.models import AggregateSessionCard, ProjectIdentityFields

        dump = AggregateSessionCard(
            project=ProjectIdentityFields(project_id="p"),
            card={},
        ).model_dump()
        for field in FE_AGGREGATE_SESSION_CARD_FIELDS:
            self.assertIn(
                field,
                dump,
                f"Field '{field}' absent from AggregateSessionCard.model_dump()",
            )


# ---------------------------------------------------------------------------
# CC-13  Schema-drift regression: drop a field and test fails
# (This is a meta-test: it proves the harness catches drift.)
# ---------------------------------------------------------------------------


class TestDriftDetectionHarness(unittest.TestCase):
    """CC-13: Verify that the contract harness actually catches a dropped field.

    We construct a throwaway Pydantic model that is missing one field the FE
    expects and assert that ``_assert_fields_present`` raises AssertionError.
    This is the load-bearing smoke test for the entire contract suite.
    """

    def test_harness_catches_missing_field(self) -> None:
        """When a backend model drops 'is_stale', the harness must fail."""
        from pydantic import BaseModel as _BaseModel

        class _ProjectSummaryMissingIsStale(_BaseModel):
            project_id: str = ""
            name: str = ""
            # is_stale intentionally absent — drift simulation

        with self.assertRaises(AssertionError) as ctx:
            _assert_fields_present(
                self,
                frozenset({"project_id", "name", "is_stale"}),
                _ProjectSummaryMissingIsStale,
                label="ProjectSummary (drift simulation)",
            )

        self.assertIn("is_stale", str(ctx.exception))

    def test_harness_passes_when_all_fields_present(self) -> None:
        """No assertion raised when all expected fields exist."""
        from pydantic import BaseModel as _BaseModel

        class _Complete(_BaseModel):
            project_id: str = ""
            name: str = ""
            is_stale: bool = False

        # Must not raise
        _assert_fields_present(
            self,
            frozenset({"project_id", "name", "is_stale"}),
            _Complete,
            label="Complete model",
        )


if __name__ == "__main__":
    unittest.main()
