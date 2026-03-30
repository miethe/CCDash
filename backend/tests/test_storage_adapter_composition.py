import unittest

from backend import config
from backend.application.ports import (
    IngestionStateStorage,
    IntegrationSnapshotStorage,
    ObservedProductStorage,
    OperationalStateStorage,
    WorkspaceMetadataStorage,
)
from backend.adapters.storage import EnterpriseStorageUnitOfWork, LocalStorageUnitOfWork
from backend.runtime.profiles import get_runtime_profile
from backend.runtime_ports import build_core_ports


class StorageAdapterCompositionTests(unittest.TestCase):
    def test_local_profile_uses_local_storage_adapter(self) -> None:
        ports = build_core_ports(
            object(),
            runtime_profile=get_runtime_profile("test"),
            storage_profile=config.StorageProfileConfig(
                profile="local",
                db_backend="sqlite",
                database_url="",
                filesystem_source_of_truth=True,
                shared_postgres_enabled=False,
                isolation_mode="dedicated",
                schema_name="ccdash",
            ),
        )

        self.assertIsInstance(ports.storage, LocalStorageUnitOfWork)

    def test_enterprise_profile_uses_enterprise_storage_adapter(self) -> None:
        ports = build_core_ports(
            object(),
            runtime_profile=get_runtime_profile("test"),
            storage_profile=config.StorageProfileConfig(
                profile="enterprise",
                db_backend="postgres",
                database_url="postgresql://example/test",
                filesystem_source_of_truth=False,
                shared_postgres_enabled=False,
                isolation_mode="dedicated",
                schema_name="ccdash",
            ),
        )

        self.assertIsInstance(ports.storage, EnterpriseStorageUnitOfWork)

    def test_local_adapter_exposes_domain_grouped_storage_views(self) -> None:
        adapter = LocalStorageUnitOfWork(object())

        self.assertIsInstance(adapter.workspace_metadata(), WorkspaceMetadataStorage)
        self.assertIsInstance(adapter.observed_product(), ObservedProductStorage)
        self.assertIsInstance(adapter.ingestion_state(), IngestionStateStorage)
        self.assertIsInstance(adapter.integration_snapshots(), IntegrationSnapshotStorage)
        self.assertIsInstance(adapter.operational_state(), OperationalStateStorage)
        self.assertIs(adapter.workspace_metadata().alert_configs(), adapter.alert_configs())
        self.assertIs(adapter.observed_product().sessions(), adapter.sessions())
        self.assertIs(adapter.observed_product().session_messages(), adapter.session_messages())
        self.assertIs(adapter.observed_product().documents(), adapter.documents())
        self.assertIs(adapter.observed_product().tasks(), adapter.tasks())
        self.assertIs(adapter.observed_product().session_usage(), adapter.session_usage())
        self.assertIs(adapter.observed_product().entity_links(), adapter.entity_links())
        self.assertIs(adapter.observed_product().tags(), adapter.tags())
        self.assertIs(adapter.observed_product().features(), adapter.features())
        self.assertIs(adapter.ingestion_state().sync_state(), adapter.sync_state())
        self.assertIs(adapter.integration_snapshots().pricing_catalog(), adapter.pricing_catalog())
        self.assertIs(adapter.operational_state().analytics(), adapter.analytics())
        self.assertIs(adapter.operational_state().test_runs(), adapter.test_runs())
        self.assertIs(adapter.operational_state().test_definitions(), adapter.test_definitions())
        self.assertIs(adapter.operational_state().test_results(), adapter.test_results())
        self.assertIs(adapter.operational_state().test_domains(), adapter.test_domains())
        self.assertIs(adapter.operational_state().test_mappings(), adapter.test_mappings())
        self.assertIs(adapter.operational_state().test_integrity(), adapter.test_integrity())
        self.assertIs(adapter.operational_state().execution(), adapter.execution())
        self.assertIs(
            adapter.operational_state().agentic_intelligence(),
            adapter.agentic_intelligence(),
        )

    def test_enterprise_adapter_exposes_domain_grouped_storage_views(self) -> None:
        adapter = EnterpriseStorageUnitOfWork(object())

        self.assertIsInstance(adapter.workspace_metadata(), WorkspaceMetadataStorage)
        self.assertIsInstance(adapter.observed_product(), ObservedProductStorage)
        self.assertIsInstance(adapter.ingestion_state(), IngestionStateStorage)
        self.assertIsInstance(adapter.integration_snapshots(), IntegrationSnapshotStorage)
        self.assertIsInstance(adapter.operational_state(), OperationalStateStorage)
        self.assertIs(adapter.workspace_metadata().alert_configs(), adapter.alert_configs())
        self.assertIs(adapter.observed_product().sessions(), adapter.sessions())
        self.assertIs(adapter.observed_product().session_messages(), adapter.session_messages())
        self.assertIs(adapter.observed_product().documents(), adapter.documents())
        self.assertIs(adapter.observed_product().tasks(), adapter.tasks())
        self.assertIs(adapter.observed_product().session_usage(), adapter.session_usage())
        self.assertIs(adapter.observed_product().entity_links(), adapter.entity_links())
        self.assertIs(adapter.observed_product().tags(), adapter.tags())
        self.assertIs(adapter.observed_product().features(), adapter.features())
        self.assertIs(adapter.ingestion_state().sync_state(), adapter.sync_state())
        self.assertIs(adapter.integration_snapshots().pricing_catalog(), adapter.pricing_catalog())
        self.assertIs(adapter.operational_state().analytics(), adapter.analytics())
        self.assertIs(adapter.operational_state().test_runs(), adapter.test_runs())
        self.assertIs(adapter.operational_state().test_definitions(), adapter.test_definitions())
        self.assertIs(adapter.operational_state().test_results(), adapter.test_results())
        self.assertIs(adapter.operational_state().test_domains(), adapter.test_domains())
        self.assertIs(adapter.operational_state().test_mappings(), adapter.test_mappings())
        self.assertIs(adapter.operational_state().test_integrity(), adapter.test_integrity())
        self.assertIs(adapter.operational_state().execution(), adapter.execution())
        self.assertIs(
            adapter.operational_state().agentic_intelligence(),
            adapter.agentic_intelligence(),
        )
