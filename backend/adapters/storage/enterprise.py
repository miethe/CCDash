"""Enterprise storage adapter.

For now this adapter reuses the factory-backed implementation to preserve
behavior while making the selection explicit in runtime composition.
"""
from __future__ import annotations

from typing import Any

from .local import FactoryStorageUnitOfWork


class EnterpriseStorageUnitOfWork(FactoryStorageUnitOfWork):
    pass
