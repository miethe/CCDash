"""Database connection factory.

Provides singleton async connection to SQLite (default) with WAL mode.
Backend selection via CCDASH_DB_BACKEND env var.
"""
from __future__ import annotations

import logging
import os
from typing import Union, Any

import aiosqlite
try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from backend import config

logger = logging.getLogger("ccdash.db")

# Database file location — path is owned by config.DB_PATH (single env-var read point)
DB_PATH = config.DB_PATH
SQLITE_BUSY_TIMEOUT_MS = max(1000, int(os.getenv("CCDASH_SQLITE_BUSY_TIMEOUT_MS", "30000")))

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
        await conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        # Performance tuning pragmas (SQLite / dev-only; Postgres path returns early above)
        _cache_size_kb = int(os.getenv("CCDASH_SQLITE_CACHE_SIZE_KB", "-131072"))  # 128 MB negative=KB
        await conn.execute(f"PRAGMA cache_size={_cache_size_kb}")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute(f"PRAGMA mmap_size={int(os.getenv('CCDASH_SQLITE_MMAP_SIZE', '268435456'))}")  # 256 MB
        await conn.execute("PRAGMA wal_autocheckpoint=1000")
        await conn.execute("PRAGMA temp_store=MEMORY")
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
