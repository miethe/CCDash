import unittest

from backend import config
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

