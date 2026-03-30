"""Compatibility exports for split Postgres entity graph and runtime state repositories."""
from backend.db.repositories.postgres.entity_graph import PostgresEntityLinkRepository, PostgresTagRepository
from backend.db.repositories.postgres.runtime_state import (
    PostgresAlertConfigRepository,
    PostgresSyncStateRepository,
)

__all__ = [
    "PostgresAlertConfigRepository",
    "PostgresEntityLinkRepository",
    "PostgresSyncStateRepository",
    "PostgresTagRepository",
]
