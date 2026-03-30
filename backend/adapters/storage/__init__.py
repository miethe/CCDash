"""Storage adapters.

This package exposes explicit StorageUnitOfWork adapters for local and
enterprise profiles. The previous FactoryStorageUnitOfWork remains as an
internal, transitional bridge in ``backend.adapters.storage.local`` but is not
exported here and must not be used as an architectural control point.
"""

from backend.adapters.storage.local_uow import LocalStorageUnitOfWork
from backend.adapters.storage.enterprise_uow import EnterpriseStorageUnitOfWork

__all__ = ["LocalStorageUnitOfWork", "EnterpriseStorageUnitOfWork"]
