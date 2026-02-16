"""Database migration dispatcher.

Routes migration calls to the appropriate backend implementation (SQLite or Postgres).
"""
from __future__ import annotations

import logging
from typing import Any

import aiosqlite
# Try importing asyncpg, handle missing
try:
    import asyncpg
except ImportError:
    asyncpg = None

from backend.db import sqlite_migrations
try:
    from backend.db import postgres_migrations
except ImportError:
    postgres_migrations = None

logger = logging.getLogger("ccdash.db")


async def run_migrations(db: Any) -> None:
    """Run migrations on the provided database connection."""
    if isinstance(db, aiosqlite.Connection):
        logger.info("Running SQLite migrations...")
        await sqlite_migrations.run_migrations(db)
        return

    # Check for asyncpg Pool or Connection
    if asyncpg and (isinstance(db, asyncpg.Pool) or isinstance(db, asyncpg.Connection)):
        if not postgres_migrations:
            logger.error("Postgres migrations module not found!")
            raise ImportError("backend.db.postgres_migrations not found")
        
        logger.info("Running Postgres migrations...")
        # If db is a Pool, we might need to acquire a connection or pass the pool 
        # if the migration runner handles it.
        # postgres_migrations.run_migrations expects Pool (based on my implementation)
        await postgres_migrations.run_migrations(db)
        return

    logger.warning(f"Unknown database connection type: {type(db)}")
