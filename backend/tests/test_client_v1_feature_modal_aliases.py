from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.application.services.feature_surface import ModalSectionResult
from backend.routers import _client_v1_features as client_v1_features


class _FakeFeatureRepo:
    def __init__(self):
        self.requested_ids: list[str] = []
        self.rows = [
            {
                "id": "artifact-page-consolidation-v1",
                "name": "Artifact Page Consolidation",
                "status": "done",
                "category": "refactor",
                "total_tasks": 7,
                "completed_tasks": 7,
                "updated_at": "2026-04-24T10:00:00Z",
                "data_json": "{}",
            }
        ]

    async def get_by_id(self, feature_id: str):
        self.requested_ids.append(feature_id)
        for row in self.rows:
            if row["id"] == feature_id:
                return row
        return None

    async def list_all(self, project_id: str):
        return self.rows


class _FakeStorage:
    def __init__(self):
        self.feature_repo = _FakeFeatureRepo()

    def features(self):
        return self.feature_repo


class ClientV1FeatureModalAliasTests(unittest.IsolatedAsyncioTestCase):
    async def test_modal_overview_resolves_base_slug_alias_before_loading(self) -> None:
        storage = _FakeStorage()
        app_request = SimpleNamespace(
            context=SimpleNamespace(project=SimpleNamespace(project_id="project-1")),
            ports=SimpleNamespace(storage=storage),
        )

        service = SimpleNamespace(
            get_overview=AsyncMock(
                return_value=ModalSectionResult(
                    section="overview",
                    cost_profile="feature_lookup",
                    data={"description": "Resolved description"},
                )
            )
        )

        with (
            patch.object(client_v1_features, "_resolve_app_request", AsyncMock(return_value=app_request)),
            patch.object(client_v1_features, "_feature_modal_detail_service", service),
        ):
            envelope = await client_v1_features.get_feature_modal_overview_v1(
                "artifact-page-consolidation",
                request_context=app_request.context,
                core_ports=app_request.ports,
            )

        service.get_overview.assert_awaited_once()
        self.assertEqual(service.get_overview.await_args.args[2], "artifact-page-consolidation-v1")
        self.assertEqual(envelope.data.feature_id, "artifact-page-consolidation-v1")


if __name__ == "__main__":
    unittest.main()
