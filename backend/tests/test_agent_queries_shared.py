import unittest
from datetime import datetime, timezone

from backend.application.services.agent_queries import (
    FeatureForensicsQueryService,
    ProjectStatusQueryService,
    ReportingQueryService,
    WorkflowDiagnosticsQueryService,
    collect_source_refs,
    derive_data_freshness,
    normalize_entity_ids,
    resolve_time_window,
)


class AgentQuerySharedTests(unittest.TestCase):
    def test_collect_source_refs_deduplicates_and_sorts(self) -> None:
        result = collect_source_refs("session-2", ["session-1", "session-2"], None, "feature-1")
        self.assertEqual(result, ["feature-1", "session-1", "session-2"])

    def test_derive_data_freshness_returns_latest_timestamp(self) -> None:
        latest = derive_data_freshness(
            "2026-04-11T10:00:00+00:00",
            datetime(2026, 4, 11, 10, 5, tzinfo=timezone.utc),
            "2026-04-11T09:30:00+00:00",
        )
        self.assertEqual(latest, datetime(2026, 4, 11, 10, 5, tzinfo=timezone.utc))

    def test_resolve_time_window_normalizes_order(self) -> None:
        start, end = resolve_time_window("2026-04-11T12:00:00+00:00", "2026-04-10T12:00:00+00:00")
        self.assertLessEqual(start, end)

    def test_normalize_entity_ids_flattens_scalars_and_iterables(self) -> None:
        result = normalize_entity_ids("feature-2", ["feature-1", ""], ("feature-2", "feature-3"))
        self.assertEqual(result, ["feature-1", "feature-2", "feature-3"])

    def test_package_exports_service_classes(self) -> None:
        self.assertTrue(ProjectStatusQueryService)
        self.assertTrue(FeatureForensicsQueryService)
        self.assertTrue(WorkflowDiagnosticsQueryService)
        self.assertTrue(ReportingQueryService)
