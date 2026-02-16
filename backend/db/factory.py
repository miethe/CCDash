"""Repository factory to abstract DB backend (SQLite vs Postgres)."""
from __future__ import annotations

from typing import Any
import aiosqlite

try:
    import asyncpg
except ImportError:
    asyncpg = None

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.tasks import SqliteTaskRepository
from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.repositories.links import (
    SqliteEntityLinkRepository,
    SqliteTagRepository,
    SqliteSyncStateRepository,
    SqliteAlertConfigRepository,
)

def get_session_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteSessionRepository(db)
    from backend.db.repositories.postgres.sessions import PostgresSessionRepository
    return PostgresSessionRepository(db)

def get_document_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteDocumentRepository(db)
    from backend.db.repositories.postgres.documents import PostgresDocumentRepository
    return PostgresDocumentRepository(db)

def get_task_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteTaskRepository(db)
    from backend.db.repositories.postgres.tasks import PostgresTaskRepository
    return PostgresTaskRepository(db)

def get_analytics_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteAnalyticsRepository(db)
    from backend.db.repositories.postgres.analytics import PostgresAnalyticsRepository
    return PostgresAnalyticsRepository(db)

def get_entity_link_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteEntityLinkRepository(db)
    from backend.db.repositories.postgres.links import PostgresEntityLinkRepository
    return PostgresEntityLinkRepository(db)

def get_tag_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteTagRepository(db)
    from backend.db.repositories.postgres.links import PostgresTagRepository
    return PostgresTagRepository(db)


def get_feature_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        from backend.db.repositories.features import SqliteFeatureRepository
        return SqliteFeatureRepository(db)
    from backend.db.repositories.postgres.features import PostgresFeatureRepository
    return PostgresFeatureRepository(db)

def get_sync_state_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteSyncStateRepository(db)
    from backend.db.repositories.postgres.links import PostgresSyncStateRepository
    return PostgresSyncStateRepository(db)

def get_alert_config_repository(db: Any):
    if isinstance(db, aiosqlite.Connection):
        return SqliteAlertConfigRepository(db)
    from backend.db.repositories.postgres.links import PostgresAlertConfigRepository
    return PostgresAlertConfigRepository(db)
