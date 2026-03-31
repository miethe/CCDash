"""Compatibility exports for split entity graph and runtime state repositories."""
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository, SqliteTagRepository
from backend.db.repositories.runtime_state import SqliteAlertConfigRepository, SqliteSyncStateRepository

__all__ = [
    "SqliteAlertConfigRepository",
    "SqliteEntityLinkRepository",
    "SqliteSyncStateRepository",
    "SqliteTagRepository",
]
