"""Storage adapters."""

from backend.adapters.storage.local import FactoryStorageUnitOfWork, LocalStorageUnitOfWork
from backend.adapters.storage.enterprise import EnterpriseStorageUnitOfWork

# Export the explicit adapters; keep FactoryStorageUnitOfWork as a
# compatibility alias for call sites still importing it directly.
__all__ = [
    "LocalStorageUnitOfWork",
    "EnterpriseStorageUnitOfWork",
    "FactoryStorageUnitOfWork",
]
