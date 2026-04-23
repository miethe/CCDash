"""
Unit tests for backend/db/repositories/feature_queries.py.

Covers:
- 100-ID cap validator on FeatureRollupQuery
- Default sort direction logic on FeatureSortKey / FeatureListQuery
- DateRange rejects from_date > to_date
- RollupFieldGroup validator accepts valid groups and rejects unknown ones
"""

from typing import cast

import pytest

from backend.db.repositories.feature_queries import (
    DateRange,
    FeatureListQuery,
    FeatureRollupQuery,
    FeatureSortKey,
    RollupFieldGroup,
    SortDirection,
)


# ---------------------------------------------------------------------------
# FeatureRollupQuery — 100-ID cap
# ---------------------------------------------------------------------------

class TestFeatureRollupQueryIdCap:
    def test_exactly_100_ids_is_accepted(self):
        ids = [f"FEAT-{i:04d}" for i in range(100)]
        q = FeatureRollupQuery(feature_ids=ids)
        assert len(q.feature_ids) == 100

    def test_101_ids_raises_value_error(self):
        ids = [f"FEAT-{i:04d}" for i in range(101)]
        with pytest.raises(ValueError, match="maximum batch size of 100"):
            FeatureRollupQuery(feature_ids=ids)

    def test_error_message_includes_received_count(self):
        ids = [f"FEAT-{i:04d}" for i in range(150)]
        with pytest.raises(ValueError, match="150"):
            FeatureRollupQuery(feature_ids=ids)

    def test_duplicates_are_silently_deduped(self):
        ids = ["FEAT-001", "FEAT-001", "FEAT-002"]
        q = FeatureRollupQuery(feature_ids=ids)
        assert q.feature_ids == ["FEAT-001", "FEAT-002"]

    def test_single_id_is_accepted(self):
        q = FeatureRollupQuery(feature_ids=["FEAT-001"])
        assert q.feature_ids == ["FEAT-001"]

    def test_empty_list_raises(self):
        with pytest.raises(Exception):
            FeatureRollupQuery(feature_ids=[])


# ---------------------------------------------------------------------------
# FeatureSortKey — default direction
# ---------------------------------------------------------------------------

class TestFeatureSortKeyDefaults:
    def test_name_defaults_to_asc(self):
        assert FeatureSortKey.NAME.default_direction == SortDirection.ASC

    def test_updated_date_defaults_to_desc(self):
        assert FeatureSortKey.UPDATED_DATE.default_direction == SortDirection.DESC

    def test_latest_activity_defaults_to_desc(self):
        assert FeatureSortKey.LATEST_ACTIVITY.default_direction == SortDirection.DESC

    def test_session_count_defaults_to_desc(self):
        assert FeatureSortKey.SESSION_COUNT.default_direction == SortDirection.DESC

    def test_progress_defaults_to_desc(self):
        assert FeatureSortKey.PROGRESS.default_direction == SortDirection.DESC

    def test_task_count_defaults_to_desc(self):
        assert FeatureSortKey.TASK_COUNT.default_direction == SortDirection.DESC


class TestFeatureListQuerySortDefaults:
    def test_default_sort_key_is_updated_date(self):
        q = FeatureListQuery()
        assert q.sort_by == FeatureSortKey.UPDATED_DATE

    def test_default_effective_direction_is_desc(self):
        q = FeatureListQuery()
        assert q.effective_sort_direction == SortDirection.DESC

    def test_name_sort_effective_direction_is_asc(self):
        q = FeatureListQuery(sort_by=FeatureSortKey.NAME)
        assert q.effective_sort_direction == SortDirection.ASC

    def test_explicit_direction_overrides_default(self):
        q = FeatureListQuery(sort_by=FeatureSortKey.NAME, sort_direction=SortDirection.DESC)
        assert q.effective_sort_direction == SortDirection.DESC


# ---------------------------------------------------------------------------
# DateRange — ordering constraint
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_valid_range_is_accepted(self):
        dr = DateRange(from_date="2026-01-01", to_date="2026-12-31")
        assert dr.from_date == "2026-01-01"

    def test_same_date_is_accepted(self):
        dr = DateRange(from_date="2026-06-01", to_date="2026-06-01")
        assert dr.from_date == dr.to_date

    def test_only_from_is_accepted(self):
        dr = DateRange(from_date="2026-01-01")
        assert dr.to_date is None

    def test_only_to_is_accepted(self):
        dr = DateRange(to_date="2026-12-31")
        assert dr.from_date is None

    def test_neither_bound_is_accepted(self):
        dr = DateRange()
        assert dr.from_date is None and dr.to_date is None

    def test_from_after_to_raises_value_error(self):
        with pytest.raises(ValueError, match="from_date"):
            DateRange(from_date="2026-12-31", to_date="2026-01-01")


# ---------------------------------------------------------------------------
# FeatureRollupQuery — include_fields validation
# ---------------------------------------------------------------------------

class TestRollupFieldGroupValidation:
    def test_valid_groups_are_accepted(self):
        q = FeatureRollupQuery(
            feature_ids=["FEAT-001"],
            include_fields={
                "session_counts",
                "token_cost_totals",
                "model_provider_summary",
                "latest_activity",
                "task_metrics",
                "doc_metrics",
                "test_metrics",
                "freshness",
            },
        )
        assert "session_counts" in q.include_fields

    def test_unknown_group_raises_value_error(self):
        # cast bypasses static type checking intentionally — we're testing that
        # the runtime field_validator rejects values not in _VALID_ROLLUP_GROUPS.
        with pytest.raises(ValueError, match="Unknown rollup field group"):
            FeatureRollupQuery(
                feature_ids=["FEAT-001"],
                include_fields=cast(set[RollupFieldGroup], {"session_counts", "nonexistent_group"}),
            )

    def test_error_message_lists_unknown_group(self):
        # cast bypasses static type checking intentionally — runtime validator test.
        with pytest.raises(ValueError, match="bad_group"):
            FeatureRollupQuery(
                feature_ids=["FEAT-001"],
                include_fields=cast(set[RollupFieldGroup], {"bad_group"}),
            )

    def test_empty_include_fields_is_accepted(self):
        q = FeatureRollupQuery(feature_ids=["FEAT-001"], include_fields=set())
        assert q.include_fields == set()

    def test_default_include_fields_are_all_valid(self):
        q = FeatureRollupQuery(feature_ids=["FEAT-001"])
        from backend.db.repositories.feature_queries import _VALID_ROLLUP_GROUPS
        assert q.include_fields.issubset(_VALID_ROLLUP_GROUPS)
