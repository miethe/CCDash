"""Database connection factory.

Provides singleton async connection to SQLite (default) with WAL mode.
Backend selection via CCDASH_DB_BACKEND env var.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Union, Any

import aiosqlite
try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from backend import config

logger = logging.getLogger("ccdash.db")

# Database file location
DB_DIR = config.PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("CCDASH_DB_PATH", str(DB_DIR / "ccdash_cache.db")))

# Type alias for DB connection/pool
DbConnection = Union[aiosqlite.Connection, Any] # Any to support asyncpg.Pool

_connection: DbConnection | None = None


async def get_connection() -> DbConnection:
    """Return the singleton database connection/pool, creating it if needed."""
    global _connection
    if _connection is not None:
        return _connection

    if config.DB_BACKEND == "postgres":
        if not asyncpg:
            raise ImportError("asyncpg is required for Postgres backend.")
        
        logger.info(f"Connecting to PostgreSQL: {config.DATABASE_URL}")
        _connection = await asyncpg.create_pool(config.DATABASE_URL)
        return _connection
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(DB_PATH))
        conn.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrent read performance
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=5000")
        logger.info(f"Database connection established: {DB_PATH}")
        _connection = conn
        return _connection


async def close_connection() -> None:
    """Close the database connection."""
    global _connection
    if _connection is not None:
        if config.DB_BACKEND == "postgres":
            await _connection.close() # asyncpg Pool has close()
        else:
            await _connection.close()
        _connection = None
        logger.info("Database connection closed")
